#!/usr/bin/env python3
"""Validate and seal an immutable production-goal contract JSON receipt."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SHA = re.compile(r"^[0-9a-f]{40,64}$")
PHASES = {"VALIDATED", "MERGE_READY", "DEPLOY_READY", "ATTESTED", "CLOSED"}


def canonical_hash(value: dict[str, Any]) -> str:
    clone = copy.deepcopy(value)
    clone.pop("contract_hash", None)
    return hashlib.sha256(json.dumps(clone, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def nonempty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def object_with(errors: list[str], value: Any, fields: list[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return {}
    for field in fields:
        if not nonempty(value.get(field)):
            errors.append(f"{name}.{field} must be non-empty")
    return value


def nonempty_strings(errors: list[str], value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
        errors.append(f"{name} must be a non-empty list of non-empty strings")
        return []
    return value


def git_has_commit(root: Path, sha: str) -> bool:
    result = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, text=True)
    return result.returncode == 0


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def validate(data: dict[str, Any], repo_root: Path | None, require_locked_artifacts: bool = False) -> list[str]:
    errors: list[str] = []
    for field in ["id", "status", "contract_hash", "user_goal", "classification", "origin"]:
        if not nonempty(data.get(field)):
            errors.append(f"receipt.{field} must be non-empty")
    if data.get("status") != "ACTIVE":
        errors.append("only a sealed ACTIVE contract is valid for task mutation")
    if data.get("classification") not in {"PRODUCTION_AFFECTING", "PLANNING_ONLY"}:
        errors.append("receipt.classification is invalid")
    if data.get("origin") not in {"DIRECT", "SPECSWARM"}:
        errors.append("receipt.origin is invalid")

    authority = object_with(errors, data.get("authority"), ["original_request_ref", "original_request_hash", "verbatim_text", "captured_at_utc", "execution_authority", "source_kind", "immutable_locator"], "authority")
    if authority and authority.get("execution_authority") not in {"AUTHORIZED", "NOT_AUTHORIZED"}:
        errors.append("authority.execution_authority is invalid")
    if authority and authority.get("original_request_hash") != hashlib.sha256(str(authority.get("verbatim_text", "")).encode("utf-8")).hexdigest():
        errors.append("authority.original_request_hash must hash authority.verbatim_text")
    if authority and authority.get("source_kind") not in {"CODEX_CONVERSATION_EXPORT", "ISSUE_EXPORT", "SIGNED_CHANGE_REQUEST"}:
        errors.append("authority.source_kind must identify an independently retained authority source")
    if data.get("classification") == "PLANNING_ONLY" and authority.get("execution_authority") != "NOT_AUTHORIZED":
        errors.append("PLANNING_ONLY contracts must be NOT_AUTHORIZED")
    if data.get("classification") == "PRODUCTION_AFFECTING" and authority.get("execution_authority") != "AUTHORIZED":
        errors.append("PRODUCTION_AFFECTING contracts must have explicit AUTHORIZED execution authority")

    baseline = object_with(errors, data.get("baseline"), ["protected_ref", "sha", "retrieved_at_utc", "protection_evidence", "selection_reason"], "baseline")
    if baseline and not SHA.fullmatch(str(baseline.get("sha", ""))):
        errors.append("baseline.sha must be a 40-64 character lowercase hex Git SHA")
    if repo_root and baseline and SHA.fullmatch(str(baseline.get("sha", ""))) and not git_has_commit(repo_root, str(baseline["sha"])):
        errors.append("baseline.sha is not a commit in --repo-root")

    allowed = object_with(errors, data.get("allowed"), ["paths", "semantic_changes"], "allowed")
    forbidden = object_with(errors, data.get("forbidden"), ["paths", "semantic_changes"], "forbidden")
    allowed_paths = nonempty_strings(errors, allowed.get("paths"), "allowed.paths") if allowed else []
    forbidden_paths = nonempty_strings(errors, forbidden.get("paths"), "forbidden.paths") if forbidden else []
    allowed_semantics = nonempty_strings(errors, allowed.get("semantic_changes"), "allowed.semantic_changes") if allowed else []
    forbidden_semantics = nonempty_strings(errors, forbidden.get("semantic_changes"), "forbidden.semantic_changes") if forbidden else []
    if set(allowed_paths) & set(forbidden_paths) or set(allowed_semantics) & set(forbidden_semantics):
        errors.append("allowed and forbidden declarations may not overlap")
    nonempty_strings(errors, data.get("invariants"), "receipt.invariants")
    nonempty_strings(errors, data.get("stop_conditions"), "receipt.stop_conditions")

    cases = data.get("acceptance_cases")
    proofs = data.get("proof_requirements")
    if not isinstance(cases, list) or not cases:
        errors.append("receipt.acceptance_cases must be non-empty")
        cases = []
    if not isinstance(proofs, list) or not proofs:
        errors.append("receipt.proof_requirements must be non-empty")
        proofs = []
    case_ids: set[str] = set()
    for case in cases:
        case = object_with(errors, case, ["id", "promised_behavior", "forbidden_behavior", "target_and_actor", "required_proof_ids"], "acceptance_case")
        if case:
            if case.get("phase", "VALIDATED") not in PHASES:
                errors.append("acceptance_case.phase must be a valid lifecycle phase")
            if case["id"] in case_ids:
                errors.append("acceptance case IDs must be unique")
            case_ids.add(case["id"])
            nonempty_strings(errors, case.get("required_proof_ids"), "acceptance_case.required_proof_ids")
    proof_ids: set[str] = set()
    for proof in proofs:
        proof = object_with(errors, proof, ["id", "acceptance_case_ids", "claim", "required_environment", "command_or_read_only_check", "expected_observation"], "proof_requirement")
        if proof:
            if proof.get("phase", "VALIDATED") not in PHASES:
                errors.append("proof_requirement.phase must be a valid lifecycle phase")
            if proof["id"] in proof_ids:
                errors.append("proof requirement IDs must be unique")
            proof_ids.add(proof["id"])
            links = nonempty_strings(errors, proof.get("acceptance_case_ids"), "proof_requirement.acceptance_case_ids")
            if not set(links) <= case_ids:
                errors.append("proof requirement references an unknown acceptance case")
    for case in cases:
        if isinstance(case, dict) and not set(case.get("required_proof_ids", [])) <= proof_ids:
            errors.append("acceptance case references an unknown proof requirement")

    for name, fields in {
        "review_requirements": ["id", "phase", "required_role"],
        "release_requirements": ["id", "phase", "required_receipt"],
    }.items():
        entries = data.get(name)
        if not isinstance(entries, list) or not entries:
            errors.append(f"receipt.{name} must be non-empty")
        else:
            for entry in entries:
                object_with(errors, entry, fields, name)
    delegation = object_with(errors, data.get("delegation"), ["contract_id_required_in_child_prompts", "allowed_surfaces_must_be_explicit"], "delegation")
    if delegation and (delegation.get("contract_id_required_in_child_prompts") is not True or delegation.get("allowed_surfaces_must_be_explicit") is not True):
        errors.append("delegation safeguards must be true")

    artifacts = data.get("locked_artifacts")
    if (require_locked_artifacts or data.get("origin") == "SPECSWARM") and not artifacts:
        errors.append("--require-locked-artifacts requires spec/checklist/blockerboard bindings")
    if artifacts:
        if not isinstance(artifacts, dict):
            errors.append("locked_artifacts must be an object")
        else:
            for name in ["spec", "checklist", "blockerboard"]:
                artifact = object_with(errors, artifacts.get(name), ["path", "sha256"], f"locked_artifacts.{name}")
                if artifact and not SHA.fullmatch(str(artifact["sha256"])):
                    errors.append(f"locked_artifacts.{name}.sha256 must be SHA-256")
                elif artifact:
                    artifact_path = Path(str(artifact["path"]))
                    try:
                        observed = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                    except OSError:
                        errors.append(f"locked_artifacts.{name}.path cannot be read")
                    else:
                        if observed != artifact["sha256"]:
                            errors.append(f"locked_artifacts.{name}.sha256 does not match file contents")
            trace = data.get("requirement_trace")
            if not isinstance(trace, list) or not trace:
                errors.append("locked artifact contracts require a non-empty requirement_trace")
            else:
                for entry in trace:
                    valid = object_with(errors, entry, ["user_constraint", "artifact", "section", "acceptance_case_id"], "requirement_trace")
                    if valid and valid["artifact"] not in {"spec", "checklist", "blockerboard"}:
                        errors.append("requirement_trace.artifact must be spec, checklist, or blockerboard")
                    if valid and valid["acceptance_case_id"] not in case_ids:
                        errors.append("requirement_trace references an unknown acceptance case")
    if data.get("previous_contract") is not None:
        previous = object_with(errors, data.get("previous_contract"), ["path", "sha256"], "previous_contract")
        if previous and not SHA.fullmatch(str(previous["sha256"])):
            errors.append("previous_contract.sha256 must be SHA-256")
        elif previous:
            previous_path = Path(str(previous["path"]))
            try:
                previous_bytes = previous_path.read_bytes()
                previous_data = json.loads(previous_bytes)
            except (OSError, json.JSONDecodeError):
                errors.append("previous_contract.path cannot be read as a JSON receipt")
            else:
                if hashlib.sha256(previous_bytes).hexdigest() != previous["sha256"]:
                    errors.append("previous_contract.sha256 does not match file contents")
                if not isinstance(previous_data, dict) or not previous_data.get("contract_hash"):
                    errors.append("previous_contract is not a sealed contract")
    if data.get("contract_hash") != canonical_hash(data):
        errors.append("contract_hash does not match receipt contents")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--write-hash", action="store_true")
    parser.add_argument("--require-locked-artifacts", action="store_true")
    args = parser.parse_args()
    try:
        data = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: cannot read JSON receipt: {exc}")
        return 2
    if not isinstance(data, dict):
        print("INVALID: receipt root must be an object")
        return 2
    if args.write_hash:
        if data.get("status") != "ACTIVE" or nonempty(data.get("contract_hash")):
            print("INVALID: --write-hash seals only a new ACTIVE receipt with an empty contract_hash")
            return 2
        data["contract_hash"] = canonical_hash(data)
        errors = validate(data, args.repo_root, args.require_locked_artifacts)
        if errors:
            print("INVALID")
            print("\n".join(f"- {error}" for error in errors))
            return 2
        args.receipt.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    errors = validate(data, args.repo_root, args.require_locked_artifacts)
    if errors:
        print("INVALID")
        print("\n".join(f"- {error}" for error in errors))
        return 2
    print(f"VALID active contract_id={data['id']} hash={data['contract_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
