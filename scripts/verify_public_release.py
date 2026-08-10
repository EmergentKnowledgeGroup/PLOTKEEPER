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


def validate_receipt(
    receipt: dict,
    phase: str,
    contract: dict,
    candidate: str,
    diff_sha256: str,
    required_kinds: set[str],
) -> list[str]:
    errors: list[str] = []
    label = phase.lower().replace("_", "-")
    if canonical_hash(receipt, "review_receipt_hash") != receipt.get("review_receipt_hash"):
        errors.append(f"{label} receipt hash mismatch")
    if receipt.get("contract_hash") != contract.get("contract_hash"):
        errors.append(f"{label} contract mismatch")
    if receipt.get("baseline_sha") != contract.get("baseline", {}).get("sha"):
        errors.append(f"{label} baseline mismatch")
    if receipt.get("candidate_sha") != candidate:
        errors.append(f"{label} candidate mismatch")
    if receipt.get("actual_diff_sha256") != diff_sha256:
        errors.append(f"{label} diff hash mismatch")
    if receipt.get("phase") != phase or receipt.get("verdict") != "PASS":
        errors.append(f"receipt is not {phase} PASS")
    reviewer = receipt.get("reviewer") or {}
    if any((reviewer.get("independent") is not True,
            reviewer.get("implemented_candidate") is not False,
            reviewer.get("delegated_candidate") is not False,
            reviewer.get("approved_candidate") is not False)):
        errors.append(f"{label} reviewer is not independent")
    target = receipt.get("target") or {}
    if target.get("artifact_digest") != f"git:{candidate}" or not target.get("environment") or not target.get("traffic_or_execution_path"):
        errors.append(f"{label} target artifact or execution path mismatch")
    evidence = receipt.get("source_evidence") or []
    if {item.get("kind") for item in evidence} < required_kinds:
        errors.append(f"{label} required source evidence is incomplete")
    for item in evidence:
        binding = item.get("binding") or {}
        if (len(str(item.get("sha256", ""))) != 64 or
                binding.get("contract_hash") != contract.get("contract_hash") or
                binding.get("baseline_sha") != contract.get("baseline", {}).get("sha") or
                binding.get("candidate_sha") != candidate or
                len(str(binding.get("target_fingerprint", ""))) != 64):
            errors.append(f"{label} source evidence binding mismatch")
            break
    required = {
        "acceptance": {x["id"] for x in contract.get("acceptance_cases", [])},
        "proof": {x["id"] for x in contract.get("proof_requirements", [])},
        "review": {x["id"] for x in contract.get("review_requirements", [])},
        "release": {x["id"] for x in contract.get("release_requirements", [])},
    }
    observed = {(x.get("kind"), x.get("id")) for x in receipt.get("obligation_results", []) if x.get("status") == "MET"}
    if any((kind, item) not in observed for kind, ids in required.items() for item in ids):
        errors.append(f"{label} required obligations are not all MET")
    delegation = receipt.get("delegation") or {}
    if delegation.get("declaration") not in {"NO_CHILDREN", "CHILDREN"}:
        errors.append(f"{label} delegation declaration missing")
    return errors


def verify(contract: dict, bundle: dict, candidate: str, changed_paths: list[str], diff_sha256: str) -> list[str]:
    errors: list[str] = []
    receipt = bundle.get("deploy") or {}
    predecessors = bundle.get("predecessors") or []
    if canonical_hash(contract, "contract_hash") != contract.get("contract_hash"):
        errors.append("contract hash mismatch")
    errors.extend(validate_receipt(receipt, "DEPLOY_READY", contract, candidate, diff_sha256,
                                   {"user-goal", "contract", "diff", "test", "review", "deploy"}))
    predecessor_by_phase = {item.get("phase"): item for item in predecessors}
    if set(predecessor_by_phase) != {"VALIDATED", "MERGE_READY"}:
        errors.append("validated and merge-ready predecessors are required")
    else:
        expected_hashes = []
        for phase in ("VALIDATED", "MERGE_READY"):
            item = predecessor_by_phase[phase]
            errors.extend(validate_receipt(item, phase, contract, candidate, diff_sha256,
                                           {"user-goal", "contract", "diff", "test", "review"}))
            expected_hashes.append(item.get("review_receipt_hash"))
        validated_hash = predecessor_by_phase["VALIDATED"].get("review_receipt_hash")
        if predecessor_by_phase["MERGE_READY"].get("predecessor_receipt_hashes") != [validated_hash]:
            errors.append("merge-ready predecessor hash chain mismatch")
        if set(receipt.get("predecessor_receipt_hashes") or []) != set(expected_hashes):
            errors.append("deploy predecessor hash chain mismatch")
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
        bundle = json.loads(receipt_text)
        baseline = contract["baseline"]["sha"]
        changed = git("diff", "--name-only", f"{baseline}..{candidate}").splitlines()
        diff_bytes = subprocess.run(["git", "diff", "--name-status", f"{baseline}..{candidate}"], check=True, capture_output=True).stdout
        diff_sha256 = hashlib.sha256(diff_bytes).hexdigest()
    except (json.JSONDecodeError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"invalid verification input: {exc}", file=sys.stderr)
        return 2
    errors = verify(contract, bundle, candidate, changed, diff_sha256)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print(f"verified Plotkeeper release {candidate} against {contract['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
