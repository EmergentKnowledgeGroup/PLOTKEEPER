"""Codex PreToolUse guard for production release commands."""

from __future__ import annotations

import json
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


def latest_active_contract(cwd: Path) -> dict | None:
    folder = cwd / "runtime" / "goal-contracts"
    candidates = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True) if folder.is_dir() else []
    for path in candidates:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if document.get("status") == "ACTIVE" and document.get("contract_hash"):
            document["_path"] = str(path)
            return document
    return None


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
