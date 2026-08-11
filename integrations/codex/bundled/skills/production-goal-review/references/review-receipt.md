# Review Receipt Schema

Create one separate JSON receipt per review phase. Keep it immutable after sealing and validate it against the sealed goal contract.

```json
{
  "review_receipt_hash": "sha256 of this receipt excluding review_receipt_hash",
  "contract_hash": "sealed active contract hash",
  "phase": "VALIDATED|MERGE_READY|DEPLOY_READY|ATTESTED|CLOSED",
  "baseline_sha": "sealed contract baseline SHA",
  "candidate_sha": "40-64 character lowercase hex Git SHA",
  "actual_diff_sha256": "sha256 of git diff --name-status baseline..candidate",
  "target": {"environment": "", "artifact_digest": "", "traffic_or_execution_path": ""},
  "reviewer": {"identity": "", "review_run_id": "", "independent": true, "implemented_candidate": false, "delegated_candidate": false, "approved_candidate": false},
  "source_evidence": [{"path": "absolute or repo-relative raw artifact path", "sha256": "", "kind": "user-goal|contract|diff|test|review|deploy|live", "binding": {"contract_hash": "", "baseline_sha": "", "candidate_sha": "", "target_fingerprint": "sha256 canonical target object"}}],
  "obligation_results": [{"kind": "acceptance|proof|review|release", "id": "AC-1|PR-1|RR-1|RL-1", "status": "MET|VIOLATED|UNPROVEN", "source_sha256": "", "observation": ""}],
  "delegation": {"declaration": "NO_CHILDREN|CHILDREN", "children": [{"run_id": "", "allowed_surface": "", "write_authority": "READ_ONLY|WRITE", "activity_receipt_sha256": ""}]},
  "predecessor_receipt_hashes": [],
  "verdict": "PASS|PARTIAL|FAIL|BLOCKED",
  "created_at_utc": "",
  "findings": []
}
```

Rules:

- A `PASS` requires the listed reviewer independence fields to be true/false exactly as shown, all required raw sources, every phase-relevant contract obligation as `MET`, a strict baseline-to-candidate Git ancestry chain, and phase-relevant target evidence. The validator computes the actual candidate diff and rejects changed files outside the literal allowed paths or inside forbidden paths.
- A nonlocal evidence locator is not automatically trusted; the reviewer must independently obtain it and record its immutable hash.
- `CLOSED` requires predecessors for every required execution phase and a matching `ATTESTED` predecessor. Evidence bindings must name the same contract, baseline, candidate, and target; a copied receipt from another run is invalid.
- The parent may reference a receipt but may not edit, reseal, or reinterpret it.
