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
            return document
    return None


def matching_receipt(cwd: Path, contract_hash: str, candidate: str) -> bool:
    key_path = Path(os.environ.get("PLOTKEEPER_REVIEW_KEY_FILE", str(cwd / "runtime" / "qa" / "plotkeeper-review.key")))
    try:
        review_key = key_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    folders = (cwd / "runtime" / "goal-reviews", cwd / ".github" / "release-receipts")
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.json"):
            try:
                receipt = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            reviewer = receipt.get("reviewer") or {}
            payload = dict(receipt)
            payload.pop("review_receipt_hash", None)
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            expected_hash = hashlib.sha256(encoded).hexdigest()
            expected_signature = hmac.new(review_key.encode(), str(receipt.get("review_receipt_hash", "")).encode(), hashlib.sha256).hexdigest()
            try:
                signature = path.with_suffix(path.suffix + ".sig").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if (
                receipt.get("phase") == "DEPLOY_READY"
                and receipt.get("verdict") == "PASS"
                and receipt.get("contract_hash") == contract_hash
                and receipt.get("candidate_sha") == candidate
                and reviewer.get("independent") is True
                and reviewer.get("implemented_candidate") is False
                and reviewer.get("delegated_candidate") is False
                and reviewer.get("approved_candidate") is False
                and receipt.get("review_receipt_hash") == expected_hash
                and hmac.compare_digest(signature, expected_signature)
            ):
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
    if not matching_receipt(cwd, contract["contract_hash"], candidate):
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
