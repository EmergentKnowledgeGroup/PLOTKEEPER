"""Server-side verifier for a Plotkeeper public release candidate."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def canonical_hash(document: dict, field: str) -> str:
    payload = dict(document)
    payload.pop(field, None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def receipt_signature(receipt: dict, review_key: str) -> str:
    return hmac.new(review_key.encode(), str(receipt.get("review_receipt_hash", "")).encode(), hashlib.sha256).hexdigest()


def target_fingerprint(target: dict) -> str:
    encoded = json.dumps(target, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
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
    review_key: str,
    signature: str,
    evidence_hashes: dict[str, str],
    evidence_policy: dict[str, str],
    candidate_timestamp: int,
) -> list[str]:
    errors: list[str] = []
    label = phase.lower().replace("_", "-")
    if canonical_hash(receipt, "review_receipt_hash") != receipt.get("review_receipt_hash"):
        errors.append(f"{label} receipt hash mismatch")
    if not review_key or not hmac.compare_digest(receipt_signature(receipt, review_key), signature):
        errors.append(f"{label} review signature mismatch")
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
    try:
        created_at = int(datetime.fromisoformat(str(receipt.get("created_at_utc", "")).replace("Z", "+00:00")).timestamp())
        if created_at < candidate_timestamp:
            errors.append(f"{label} receipt predates candidate")
    except (TypeError, ValueError):
        errors.append(f"{label} receipt timestamp invalid")
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
    if not required_kinds.issubset({item.get("kind") for item in evidence}):
        errors.append(f"{label} required source evidence is incomplete")
    expected_target_fingerprint = target_fingerprint(target)
    for item in evidence:
        binding = item.get("binding") or {}
        path = str(item.get("path", "")).replace("\\", "/")
        if (evidence_policy.get(str(item.get("kind", ""))) != path or
                not path or path.startswith("/") or ":" in path or ".." in Path(path).parts or
                evidence_hashes.get(path) != item.get("sha256") or
                binding.get("contract_hash") != contract.get("contract_hash") or
                binding.get("baseline_sha") != contract.get("baseline", {}).get("sha") or
                binding.get("candidate_sha") != candidate or
                binding.get("target_fingerprint") != expected_target_fingerprint):
            errors.append(f"{label} source evidence binding mismatch")
            break
    phase_rank = {
        "VALIDATED": 0,
        "MERGE_READY": 1,
        "DEPLOY_READY": 2,
        "ATTESTED": 3,
        "CLOSED": 4,
    }
    all_required = {
        "acceptance": {x["id"] for x in contract.get("acceptance_cases", [])},
        "proof": {x["id"] for x in contract.get("proof_requirements", [])},
        "review": {
            x["id"] for x in contract.get("review_requirements", [])
            if phase_rank.get(str(x.get("phase") or "DEPLOY_READY"), 2) <= phase_rank[phase]
        },
        "release": {
            x["id"] for x in contract.get("release_requirements", [])
            if phase_rank.get(str(x.get("phase") or "DEPLOY_READY"), 2) <= phase_rank[phase]
        },
    }
    if phase in {"VALIDATED", "MERGE_READY"}:
        required = {
            "acceptance": {"AC-1"} & all_required["acceptance"],
            "proof": {"PR-1", "PR-2"} & all_required["proof"],
            "review": set(), "release": set(),
        }
    else:
        required = all_required
    observed = {(x.get("kind"), x.get("id")) for x in receipt.get("obligation_results", []) if x.get("status") == "MET"}
    if any((kind, item) not in observed for kind, ids in required.items() for item in ids):
        errors.append(f"{label} required obligations are not all MET")
    delegation = receipt.get("delegation") or {}
    if delegation.get("declaration") not in {"NO_CHILDREN", "CHILDREN"}:
        errors.append(f"{label} delegation declaration missing")
    return errors


def verify(contract: dict, bundle: dict, candidate: str, changed_paths: list[str], diff_sha256: str,
           review_key: str, evidence_hashes: dict[str, str], evidence_policy: dict[str, str], candidate_timestamp: int = 0) -> list[str]:
    errors: list[str] = []
    receipt = bundle.get("deploy") or {}
    predecessors = bundle.get("predecessors") or []
    signatures = bundle.get("signatures") or {}
    if canonical_hash(contract, "contract_hash") != contract.get("contract_hash"):
        errors.append("contract hash mismatch")
    errors.extend(validate_receipt(receipt, "DEPLOY_READY", contract, candidate, diff_sha256,
                                   {"user-goal", "contract", "diff", "test", "review", "deploy"}, review_key,
                                   str(signatures.get(receipt.get("review_receipt_hash"), "")), evidence_hashes, evidence_policy, candidate_timestamp))
    predecessor_by_phase = {item.get("phase"): item for item in predecessors}
    if set(predecessor_by_phase) != {"VALIDATED", "MERGE_READY"}:
        errors.append("validated and merge-ready predecessors are required")
    else:
        expected_hashes = []
        for phase in ("VALIDATED", "MERGE_READY"):
            item = predecessor_by_phase[phase]
            errors.extend(validate_receipt(item, phase, contract, candidate, diff_sha256,
                                           {"user-goal", "contract", "diff", "test", "review"}, review_key,
                                           str(signatures.get(item.get("review_receipt_hash"), "")), evidence_hashes, evidence_policy, candidate_timestamp))
            expected_hashes.append(item.get("review_receipt_hash"))
        validated_hash = predecessor_by_phase["VALIDATED"].get("review_receipt_hash")
        if predecessor_by_phase["MERGE_READY"].get("predecessor_receipt_hashes") != [validated_hash]:
            errors.append("merge-ready predecessor hash chain mismatch")
        phase_times = [predecessor_by_phase[phase].get("created_at_utc", "") for phase in ("VALIDATED", "MERGE_READY")] + [receipt.get("created_at_utc", "")]
        if phase_times != sorted(phase_times) or len(set(phase_times)) != 3:
            errors.append("receipt phase timestamps are not strictly ordered")
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
    review_key = os.environ.get("PLOTKEEPER_REVIEW_KEY", "")
    if not candidate or not contract_path.is_file() or not receipt_text or not review_key:
        print("missing candidate, contract, deploy receipt, or review key", file=sys.stderr)
        return 2
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        bundle = json.loads(receipt_text)
        baseline = contract["baseline"]["sha"]
        changed = git("diff", "--name-only", f"{baseline}..{candidate}").splitlines()
        diff_bytes = subprocess.run(["git", "diff", "--name-status", f"{baseline}..{candidate}"], check=True, capture_output=True).stdout
        diff_sha256 = hashlib.sha256(diff_bytes).hexdigest()
        contract_rel = contract_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        evidence_policy = {
            "user-goal": contract_rel, "contract": contract_rel, "diff": "scripts/verify_public_release.py",
            "test": "tests/test_release_verifier.py", "review": "scripts/verify_public_release.py",
            "deploy": ".github/workflows/release-verifier.yml",
        }
        evidence_paths = {str(item.get("path", "")).replace("\\", "/") for document in [bundle.get("deploy") or {}, *(bundle.get("predecessors") or [])] for item in (document.get("source_evidence") or [])}
        evidence_hashes = {}
        for path in evidence_paths:
            if not path or path.startswith("/") or ":" in path or ".." in Path(path).parts:
                continue
            blob = subprocess.run(["git", "show", f"{candidate}:{path}"], check=True, capture_output=True).stdout
            evidence_hashes[path] = hashlib.sha256(blob).hexdigest()
        candidate_timestamp = int(git("show", "-s", "--format=%ct", candidate))
    except (json.JSONDecodeError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"invalid verification input: {exc}", file=sys.stderr)
        return 2
    errors = verify(contract, bundle, candidate, changed, diff_sha256, review_key, evidence_hashes, evidence_policy, candidate_timestamp)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print(f"verified Plotkeeper release {candidate} against {contract['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
