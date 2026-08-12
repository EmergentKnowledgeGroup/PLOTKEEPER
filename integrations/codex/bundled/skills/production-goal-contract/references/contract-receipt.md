# Contract Receipt Schema

Use this JSON schema as the minimum immutable contract. `scripts/validate_contract_receipt.py` validates its structure, seal, authority-text hash, path conflicts, acceptance/proof links, and optional Git baseline. It does not replace semantic review or CI/release enforcement.

```json
{
  "id": "PROD-<date>-<slug>",
  "status": "ACTIVE",
  "contract_hash": "sha256 of this receipt excluding contract_hash",
  "origin": "DIRECT|SPECSWARM",
  "user_goal": "immutable requested outcome",
  "authority": {
    "original_request_ref": "immutable conversation/issue locator",
    "original_request_hash": "sha256 of verbatim_text",
    "verbatim_text": "exact user request",
    "captured_at_utc": "",
    "execution_authority": "AUTHORIZED|NOT_AUTHORIZED",
    "source_kind": "CODEX_CONVERSATION_EXPORT|ISSUE_EXPORT|SIGNED_CHANGE_REQUEST",
    "immutable_locator": "host/issue receipt locator that another verifier can retrieve"
  },
  "baseline": {"protected_ref": "", "sha": "", "retrieved_at_utc": "", "protection_evidence": "", "selection_reason": ""},
  "classification": "PRODUCTION_AFFECTING|PLANNING_ONLY",
  "allowed": {"paths": [], "resources": [], "semantic_changes": []},
  "forbidden": {"paths": [], "semantic_changes": []},
  "invariants": [],
  "acceptance_cases": [{"id": "AC-1", "phase": "VALIDATED", "promised_behavior": "", "forbidden_behavior": "", "target_and_actor": "", "required_proof_ids": ["PR-1"]}],
  "proof_requirements": [{"id": "PR-1", "phase": "VALIDATED", "acceptance_case_ids": ["AC-1"], "claim": "", "required_environment": "", "command_or_read_only_check": "", "expected_observation": ""}],
  "review_requirements": [{"id": "RR-1", "phase": "MERGE_READY", "required_role": "independent reviewer"}],
  "release_requirements": [{"id": "RL-1", "phase": "DEPLOY_READY", "required_receipt": "release attestation"}],
  "stop_conditions": [],
  "known_discrepancies": [],
  "delegation": {"contract_id_required_in_child_prompts": true, "allowed_surfaces_must_be_explicit": true},
  "locked_artifacts": {"spec": {"path": "", "sha256": ""}, "checklist": {"path": "", "sha256": ""}, "blockerboard": {"path": "", "sha256": ""}},
  "requirement_trace": [],
  "previous_contract": null
}
```

Rules:

- `ACTIVE` contracts are sealed. Do not reseal or edit one. A scope change creates a new contract with a different ID, `previous_contract` path/hash, and new verbatim user authority. A `SPECSWARM` origin always requires all three locked-artifact bindings; this is not optional.
- The authority hash is the SHA-256 of the stored verbatim user text. The contract copy is not a substitute for independently reading its immutable source locator. Local schema validation proves consistency, not that an agent invented neither the user request nor a retained conversation export; that provenance must be independently checked by the app/CI gate.
- A path allowance is not semantic permission to change every field in that path; an allowed and forbidden path/semantic value may not overlap.
- `PLANNING_ONLY` plus `NOT_AUTHORIZED` may record a SpecSwarm contract but cannot authorize implementation, merge, or deployment.
- Acceptance and proof `phase` values use the same lifecycle as review and release requirements. They are optional for backward compatibility and default to `VALIDATED`; use `ATTESTED` for outcomes or proofs that can only exist after deployment. Invalid phase names are rejected.
- Phase receipts are separate JSON artifacts. They must reference this sealed contract hash and carry their own evidence hashes, candidate/target identity, verifier, and predecessor phase receipt IDs.
