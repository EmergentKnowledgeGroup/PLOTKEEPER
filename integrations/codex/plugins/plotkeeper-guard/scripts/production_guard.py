"""Codex PreToolUse guard for production release commands."""

from __future__ import annotations

import json
import hashlib
import hmac
import os
import re
import subprocess
import sys
from pathlib import Path

RELEASE_PATTERN = re.compile(
    r"\b(git\s+push|gh\s+pr\s+merge|gh\s+repo\s+edit|gh\s+api\b.*(?:PUT|PATCH|DELETE)|"
    r"kubectl\s+(?:apply|delete|rollout)|terraform\s+apply|vercel\s+(?:deploy|--prod)|"
    r"npm\s+publish|twine\s+upload)\b",
    re.IGNORECASE | re.DOTALL,
)
RELEASE_CONTRACT_POINTER = Path("runtime/goal-contracts/RELEASE_CONTRACT.json")


def canonical_json_hash(document: object) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def deny(reason: str) -> int:
    print(f"PLOTKEEPER GUARD: {reason}", file=sys.stderr)
    return 2


def command_from(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    if isinstance(tool_input, dict):
        return str(tool_input.get("command") or "")
    return ""


def git_head(cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=False
    )
    return result.stdout.strip().lower() if result.returncode == 0 else None


def _safe_contract_path(cwd: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    relative = Path(value)
    if ".." in relative.parts:
        return None
    candidate = (cwd / relative).resolve()
    try:
        candidate.relative_to(cwd.resolve())
    except ValueError:
        return None
    return candidate


def _release_authorized(document: dict) -> bool:
    requirements = document.get("release_requirements")
    return isinstance(requirements, list) and any(
        isinstance(item, dict)
        and item.get("phase") == "DEPLOY_READY"
        and isinstance(item.get("id"), str)
        and bool(item["id"].strip())
        and item["id"] == item["id"].strip()
        and item["id"] != "RL-NONE"
        for item in requirements
    )


def designated_release_contract(cwd: Path) -> dict | None:
    """Load only the tracked release contract named by the explicit pointer."""
    pointer_path = (cwd / RELEASE_CONTRACT_POINTER).resolve()
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if not isinstance(pointer, dict) or pointer.get("schema_version") != 1 or pointer.get("purpose") != "PLOTKEEPER_PUBLIC_RELEASE":
            return None
        contract_path = _safe_contract_path(cwd, pointer.get("contract_path"))
        if contract_path is None or not contract_path.is_file():
            return None
        contract_bytes = contract_path.read_bytes()
        contract = json.loads(contract_bytes.decode("utf-8"))
        if not hmac.compare_digest(canonical_json_hash(contract), str(pointer.get("contract_sha256", "")).lower()):
            return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(contract, dict)
        or contract.get("status") != "ACTIVE"
        or not contract.get("contract_hash")
        or contract.get("id") != pointer.get("contract_id")
        or not _release_authorized(contract)
    ):
        return None
    contract["_path"] = contract_path.relative_to(cwd.resolve()).as_posix()
    contract["_pointer_path"] = str(pointer_path)
    return contract


def latest_active_contract(cwd: Path) -> dict | None:
    # Kept as the hook's compatibility name; release authority is never mtime-selected.
    return designated_release_contract(cwd)


def matching_receipt(cwd: Path, contract: dict, candidate: str) -> bool:
    key_path = Path(os.environ.get("PLOTKEEPER_REVIEW_KEY_FILE", str(cwd / "runtime" / "qa" / "plotkeeper-review.key")))
    try:
        review_key = key_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    folders = (cwd / "runtime" / "goal-reviews", cwd / ".github" / "release-receipts")
    for folder in folders:
        if not folder.is_dir():
            continue
        # Review runs keep their immutable artifacts in per-review subfolders.
        # Search only inside the two authorized review roots, but recurse so a
        # correctly nested authoritative bundle is not made invisible.
        for path in folder.rglob("*DEPLOY_READY.bundle.json"):
            try:
                bundle_text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            env = dict(os.environ)
            env.update({"GITHUB_SHA": candidate, "PLOTKEEPER_CONTRACT": contract["_path"],
                        "PLOTKEEPER_DEPLOY_RECEIPT": bundle_text, "PLOTKEEPER_REVIEW_KEY": review_key})
            result = subprocess.run([sys.executable, str(cwd / "scripts" / "verify_public_release.py")], cwd=cwd,
                                    env=env, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return True
    return False


def evaluate(payload: dict) -> tuple[bool, str]:
    command = command_from(payload)
    if not RELEASE_PATTERN.search(command):
        return True, "not a production release command"
    cwd = Path(payload.get("cwd") or ".").resolve()
    contract = latest_active_contract(cwd)
    if not contract:
        return False, "no sealed ACTIVE production goal contract found"
    candidate = git_head(cwd)
    if not candidate:
        return False, "current Git candidate could not be resolved"
    if not matching_receipt(cwd, contract, candidate):
        return False, "no independent DEPLOY_READY PASS receipt matches the active contract and current HEAD"
    return True, "release evidence matches"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return deny("malformed hook input")
    allowed, reason = evaluate(payload)
    return 0 if allowed else deny(reason)


if __name__ == "__main__":
    raise SystemExit(main())
