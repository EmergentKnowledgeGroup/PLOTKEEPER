#!/usr/bin/env python3
"""Validate a review receipt, its raw evidence, and its predecessor chain."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SHA = re.compile(r"^[0-9a-f]{40,64}$")
PHASES = ["VALIDATED", "MERGE_READY", "DEPLOY_READY", "ATTESTED", "CLOSED"]
VERDICTS = {"PASS", "PARTIAL", "FAIL", "BLOCKED"}


def digest(value: dict[str, Any]) -> str:
    clone = copy.deepcopy(value)
    clone.pop("review_receipt_hash", None)
    return hashlib.sha256(json.dumps(clone, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def load_contract_validator() -> Any:
    path = Path(__file__).resolve().parents[2] / "production-goal-contract" / "scripts" / "validate_contract_receipt.py"
    spec = importlib.util.spec_from_file_location("contract_validator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def git_has_commit(root: Path, sha: str) -> bool:
    return subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0


def git_output(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def path_matches(rule: str, path: str) -> bool:
    # Rules are literal files or literal directory prefixes ending in '/'.
    return path.startswith(rule) if rule.endswith("/") else path == rule


def required_ids(contract: dict[str, Any], phase: str) -> dict[str, set[str]]:
    phase_index = PHASES.index(phase)
    return {
        "acceptance": {str(item["id"]) for item in contract.get("acceptance_cases", []) if isinstance(item, dict) and item.get("id") and str(item.get("phase") or "VALIDATED") in PHASES and PHASES.index(str(item.get("phase") or "VALIDATED")) <= phase_index},
        "proof": {str(item["id"]) for item in contract.get("proof_requirements", []) if isinstance(item, dict) and item.get("id") and str(item.get("phase") or "VALIDATED") in PHASES and PHASES.index(str(item.get("phase") or "VALIDATED")) <= phase_index},
        "review": {str(item["id"]) for item in contract.get("review_requirements", []) if isinstance(item, dict) and item.get("id") and item.get("phase") in PHASES and PHASES.index(str(item["phase"])) <= phase_index},
        "release": {str(item["id"]) for item in contract.get("release_requirements", []) if isinstance(item, dict) and item.get("id") and item.get("phase") in PHASES and PHASES.index(str(item["phase"])) <= phase_index},
    }


def source_kinds(phase: str) -> set[str]:
    required = {"user-goal", "contract", "diff", "test"}
    if phase in {"MERGE_READY", "DEPLOY_READY", "ATTESTED", "CLOSED"}:
        required.add("review")
    if phase in {"DEPLOY_READY", "ATTESTED", "CLOSED"}:
        required.add("deploy")
    if phase in {"ATTESTED", "CLOSED"}:
        required.add("live")
    return required


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    args = parser.parse_args()
    errors: list[str] = []
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: cannot read JSON: {exc}")
        return 2
    contract_validator = load_contract_validator()
    requires_locked = isinstance(contract, dict) and (bool(contract.get("locked_artifacts")) or contract.get("origin") == "SPECSWARM")
    errors.extend(contract_validator.validate(contract, args.repo_root, require_locked_artifacts=requires_locked))
    if isinstance(contract, dict) and contract.get("authority", {}).get("execution_authority") != "AUTHORIZED":
        errors.append("review receipt cannot advance a NOT_AUTHORIZED contract")
    if not isinstance(receipt, dict):
        errors.append("review receipt root must be an object")
    else:
        for field in ["review_receipt_hash", "contract_hash", "phase", "baseline_sha", "candidate_sha", "actual_diff_sha256", "verdict", "created_at_utc"]:
            if not receipt.get(field):
                errors.append(f"receipt.{field} must be non-empty")
        if receipt.get("review_receipt_hash") != digest(receipt):
            errors.append("review_receipt_hash does not match receipt contents")
        if receipt.get("contract_hash") != contract.get("contract_hash"):
            errors.append("receipt.contract_hash does not match sealed contract")
        phase = receipt.get("phase")
        if phase not in PHASES or receipt.get("verdict") not in VERDICTS:
            errors.append("receipt phase or verdict is invalid")
        if not SHA.fullmatch(str(receipt.get("candidate_sha", ""))) or not git_has_commit(args.repo_root, str(receipt.get("candidate_sha", ""))):
            errors.append("receipt.candidate_sha must be a commit in --repo-root")
        if receipt.get("baseline_sha") != contract.get("baseline", {}).get("sha"):
            errors.append("receipt.baseline_sha must equal the sealed contract baseline")
        if receipt.get("baseline_sha") == receipt.get("candidate_sha"):
            errors.append("candidate_sha must be a strict descendant of baseline_sha")
        elif SHA.fullmatch(str(receipt.get("baseline_sha", ""))) and SHA.fullmatch(str(receipt.get("candidate_sha", ""))):
            is_ancestor = subprocess.run(["git", "-C", str(args.repo_root), "merge-base", "--is-ancestor", str(receipt["baseline_sha"]), str(receipt["candidate_sha"])], capture_output=True)
            if is_ancestor.returncode != 0:
                errors.append("baseline_sha must be an ancestor of candidate_sha")
            else:
                try:
                    changed = git_output(args.repo_root, "diff", "--name-status", f"{receipt['baseline_sha']}..{receipt['candidate_sha']}")
                except RuntimeError as exc:
                    errors.append(f"cannot compute candidate diff: {exc}")
                    changed = b""
                if hashlib.sha256(changed).hexdigest() != receipt.get("actual_diff_sha256"):
                    errors.append("actual_diff_sha256 does not match Git baseline..candidate name-status diff")
                allowed_paths = contract.get("allowed", {}).get("paths", []) if isinstance(contract, dict) else []
                forbidden_paths = contract.get("forbidden", {}).get("paths", []) if isinstance(contract, dict) else []
                for line in changed.decode("utf-8", "replace").splitlines():
                    parts = line.split("\t")
                    paths = parts[1:] if len(parts) > 1 else []
                    for path in paths:
                        if any(path_matches(rule, path) for rule in forbidden_paths):
                            errors.append(f"actual candidate diff touches forbidden path: {path}")
                        if not any(path_matches(rule, path) for rule in allowed_paths):
                            errors.append(f"actual candidate diff touches unallowed path: {path}")
        reviewer = receipt.get("reviewer") if isinstance(receipt.get("reviewer"), dict) else {}
        if not reviewer.get("identity") or not reviewer.get("review_run_id"):
            errors.append("reviewer identity and run ID are required")
        if receipt.get("verdict") == "PASS" and (reviewer.get("independent") is not True or reviewer.get("implemented_candidate") is not False or reviewer.get("delegated_candidate") is not False or reviewer.get("approved_candidate") is not False):
            errors.append("PASS requires an independent reviewer with no implementation, delegation, or approval role")
        target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
        target_fingerprint = hashlib.sha256(json.dumps(target, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        sources = receipt.get("source_evidence")
        kinds: set[str] = set()
        if not isinstance(sources, list) or not sources:
            errors.append("source_evidence must be non-empty")
        else:
            for source in sources:
                binding = source.get("binding") if isinstance(source, dict) and isinstance(source.get("binding"), dict) else {}
                if not isinstance(source, dict) or not source.get("path") or not SHA.fullmatch(str(source.get("sha256", ""))) or not source.get("kind"):
                    errors.append("every source evidence entry needs path, SHA-256, and kind")
                    continue
                if binding.get("contract_hash") != receipt.get("contract_hash") or binding.get("baseline_sha") != receipt.get("baseline_sha") or binding.get("candidate_sha") != receipt.get("candidate_sha") or binding.get("target_fingerprint") != target_fingerprint:
                    errors.append("every source evidence entry must bind contract, baseline, candidate, and target")
                source_path = Path(str(source["path"]))
                try:
                    observed = hashlib.sha256(source_path.read_bytes()).hexdigest()
                except OSError:
                    errors.append(f"source evidence path cannot be read: {source_path}")
                else:
                    if observed != source["sha256"]:
                        errors.append(f"source evidence hash mismatch: {source_path}")
                kinds.add(str(source["kind"]))
            if phase in PHASES and not source_kinds(str(phase)) <= kinds:
                errors.append(f"phase {phase} lacks required raw evidence kinds")
        if phase in {"DEPLOY_READY", "ATTESTED", "CLOSED"}:
            for field in ["environment", "artifact_digest", "traffic_or_execution_path"]:
                if not target.get(field):
                    errors.append(f"target.{field} must be non-empty for this phase")

        obligation_ids = required_ids(contract, str(phase)) if isinstance(contract, dict) and phase in PHASES else {}
        results = receipt.get("obligation_results")
        seen: dict[str, set[str]] = {name: set() for name in obligation_ids}
        if not isinstance(results, list) or not results:
            errors.append("obligation_results must record every contract obligation")
        else:
            for item in results:
                if not isinstance(item, dict) or item.get("kind") not in seen or not item.get("id") or item.get("status") not in {"MET", "VIOLATED", "UNPROVEN"} or not SHA.fullmatch(str(item.get("source_sha256", ""))) or not item.get("observation"):
                    errors.append("every obligation result needs kind, ID, status, evidence hash, and observation")
                    continue
                seen[str(item["kind"])].add(str(item["id"]))
                if item["id"] not in obligation_ids[str(item["kind"])]:
                    errors.append("obligation result references an unknown or premature contract requirement")
                if receipt.get("verdict") == "PASS" and item["status"] != "MET":
                    errors.append("PASS may not contain VIOLATED or UNPROVEN obligations")
        for kind, required in obligation_ids.items():
            if seen.get(kind, set()) != required:
                errors.append(f"obligation_results must cover exactly the required {kind} IDs for this phase")

        children = receipt.get("delegation") if isinstance(receipt.get("delegation"), dict) else {}
        if children.get("declaration") not in {"NO_CHILDREN", "CHILDREN"} or not isinstance(children.get("children"), list):
            errors.append("delegation requires NO_CHILDREN/CHILDREN plus a children list")
        elif children["declaration"] == "NO_CHILDREN" and children["children"]:
            errors.append("NO_CHILDREN declaration may not list child activity")
        elif children["declaration"] == "CHILDREN":
            for child in children["children"]:
                if not isinstance(child, dict) or not child.get("run_id") or not child.get("allowed_surface") or child.get("write_authority") not in {"READ_ONLY", "WRITE"} or not SHA.fullmatch(str(child.get("activity_receipt_sha256", ""))):
                    errors.append("every child needs run identity, allowed surface, authority, and activity receipt hash")

        predecessor_hashes = receipt.get("predecessor_receipt_hashes")
        predecessor_index = PHASES.index(phase) - 1 if phase in PHASES else -1
        if predecessor_index >= 0:
            if not isinstance(predecessor_hashes, list) or not predecessor_hashes:
                errors.append("non-VALIDATED phases require predecessor receipt hashes")
            else:
                available: dict[str, dict[str, Any]] = {}
                for path in args.receipt_dir.glob("*.json"):
                    try:
                        item = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(item, dict) and item.get("review_receipt_hash") == digest(item):
                        available[str(item["review_receipt_hash"])] = item
                required_phase = PHASES[predecessor_index]
                matching = [available.get(str(h)) for h in predecessor_hashes]
                if not any(item and item.get("phase") == required_phase and item.get("verdict") == "PASS" and item.get("contract_hash") == receipt.get("contract_hash") and item.get("candidate_sha") == receipt.get("candidate_sha") and item.get("target") == target for item in matching):
                    errors.append(f"phase {phase} requires a matching PASS {required_phase} predecessor receipt")
    if errors:
        print("INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 2
    print(f"VALID phase={receipt['phase']} verdict={receipt['verdict']} hash={receipt['review_receipt_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
