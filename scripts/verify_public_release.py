"""Server-side verifier for a Plotkeeper public release candidate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def canonical_hash(document: dict, field: str) -> str:
    payload = dict(document)
    payload.pop(field, None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def path_allowed(path: str, allowed: list[str], forbidden: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    if any(normalized == item.rstrip("/") or normalized.startswith(item.rstrip("/") + "/") for item in forbidden):
        return False
    return any(normalized == item.rstrip("/") or normalized.startswith(item.rstrip("/") + "/") for item in allowed)


def verify(contract: dict, receipt: dict, candidate: str, changed_paths: list[str]) -> list[str]:
    errors: list[str] = []
    if canonical_hash(contract, "contract_hash") != contract.get("contract_hash"):
        errors.append("contract hash mismatch")
    if canonical_hash(receipt, "review_receipt_hash") != receipt.get("review_receipt_hash"):
        errors.append("review receipt hash mismatch")
    if receipt.get("contract_hash") != contract.get("contract_hash"):
        errors.append("receipt contract mismatch")
    if receipt.get("candidate_sha") != candidate:
        errors.append("receipt candidate mismatch")
    if receipt.get("phase") != "DEPLOY_READY" or receipt.get("verdict") != "PASS":
        errors.append("receipt is not DEPLOY_READY PASS")
    reviewer = receipt.get("reviewer") or {}
    if reviewer.get("independent") is not True or reviewer.get("implemented_candidate") is not False:
        errors.append("reviewer is not independent")
    allowed = contract.get("allowed", {}).get("paths", [])
    forbidden = contract.get("forbidden", {}).get("paths", [])
    for path in changed_paths:
        if not path_allowed(path, allowed, forbidden):
            errors.append(f"changed path outside contract: {path}")
    return errors


def main() -> int:
    candidate = os.environ.get("GITHUB_SHA", "").lower()
    contract_path = Path(os.environ.get("PLOTKEEPER_CONTRACT", ""))
    receipt_text = os.environ.get("PLOTKEEPER_DEPLOY_RECEIPT", "")
    if not candidate or not contract_path.is_file() or not receipt_text:
        print("missing candidate, contract, or deploy receipt", file=sys.stderr)
        return 2
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_text)
        baseline = contract["baseline"]["sha"]
        changed = git("diff", "--name-only", f"{baseline}..{candidate}").splitlines()
    except (json.JSONDecodeError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"invalid verification input: {exc}", file=sys.stderr)
        return 2
    errors = verify(contract, receipt, candidate, changed)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print(f"verified Plotkeeper release {candidate} against {contract['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
