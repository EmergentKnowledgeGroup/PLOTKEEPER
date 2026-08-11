---
name: production-goal-contract
description: Bind every production-affecting Codex task to a durable, fail-closed goal contract before edits, commits, merges, deployments, migrations, configuration changes, data/content changes, or operational actions. Use whenever a request can change production behavior, data, infrastructure, availability, security, recoverability, or release state; also use when a task discovers unexpected drift or dirty state.
---

# Production Goal Contract

Treat the user's requested outcome as a contract, not a suggestion. Own the implementation, merge, deployment, and verification. Do not transfer routine operational work to the user.

## 1. Classify before mutating

Read the repository instructions, checkpoint state, branch/head, and dirty state. Classify the task as `READ_ONLY`, `LOCAL_ONLY`, or `PRODUCTION_AFFECTING`.

`PRODUCTION_AFFECTING` includes every change to application behavior, APIs, frontend, data, migrations, content, configuration, secrets references, permissions, infrastructure, services, deployment, build artifacts, feature flags, observability, backups, or recovery paths. If uncertain, classify upward.

For every substantive task, run `$adaptive-execution` first. For `PRODUCTION_AFFECTING`, create a goal contract before the first write, staging action, PR action, remote command, or service operation.

Read [the receipt schema](references/contract-receipt.md) before creating or amending a contract.
Use `references/valid-contract-receipt.json` and `references/invalid-empty-contract-receipt.json` to verify the receipt validator before relying on it.

## 2. Create the contract

Write one durable JSON receipt in the repository's checkpoint/receipt convention. If no project convention exists, use `runtime/goal-contracts/<id>.json`. The one exception to the no-write rule is authoring this initial receipt. Before any task mutation, run `py -3 "<skill>/scripts/validate_contract_receipt.py" <receipt> --write-hash --repo-root .`; an invalid or unsealed receipt cannot enter `ACTIVE`. SpecSwarm additionally runs the same validator with `--require-locked-artifacts`.

```text
Contract ID and immutable user goal
Verbatim immutable user-authority evidence, locator, hash, and capture time
Risk class and protected baseline SHA
Allowed production surfaces and exact no-touch surfaces
Semantic change class for each protected surface
Invariants that must remain true
Required proof, independent review, release checks, and live attestations
Known dirty/live discrepancies and their disposition
Explicit stop conditions
```

No required scope, forbidden declaration, invariant, acceptance case, proof, review, release requirement, or stop condition may be empty. Define atomic acceptance cases with promised behavior, forbidden behavior, actor/target, and linked proof IDs; free-text claims such as “fix access” do not authorize every semantic change in an allowed file.

Select and record a protected baseline SHA before the first task write. It must be an ancestor of the candidate, predate the task mutation, and record its release/ref, retrieval time, protection evidence, and selection reason. A baseline that already contains the reported regression is invalid unless the contract explicitly proves why the user goal is independent of that regression. Local dirt, another branch, a generated artifact, a database row, and current production state are evidence to investigate, never authority to widen scope.

For a narrow repair, state forbidden fields as well as allowed files. Example: a signature-only repair may permit signature metadata and its validator, while forbidding question text, options, readiness, route behavior, and deployment changes.

## 3. Enforce the state machine

Use only these contract states:

```text
DRAFT → ACTIVE
```

- `DRAFT`: no task mutation, staging, merge, or deployment is permitted.
- `ACTIVE`: the sealed immutable contract permits only its listed work.

Record `VALIDATED`, `MERGE_READY`, `DEPLOY_READY`, `ATTESTED`, `BREACHED`, and `CLOSED` as separate immutable phase receipts that name the active contract hash. Never rewrite the contract to advance it. `$production-goal-review` issues the only `CLOSED` receipt, and only an independent phase-matched `PASS` may do so. `PARTIAL`, `FAIL`, and `BLOCKED` cannot be overridden by documentation, scheduling, or implied authority.

Before each phase receipt, validate the sealed contract and validate the phase receipt. A phase receipt is valid only when it names the contract hash, candidate SHA, target identity, prerequisite receipt IDs, raw evidence paths and hashes, executor, and independent verifier where required. Compare the actual diff, changed resources, and deploy target against the contract. Check untracked files and pre-existing dirt, not only staged files. A clean staged set does not excuse an unreviewed dirty source file.

Every delegated prompt must include the active contract ID, allowed surface, forbidden surface, and read/write authority. No subagent may write, stage, push, merge, deploy, alter data/configuration, or run an operational command without an explicit delegated receipt. Collect each child’s mutation/activity receipt before a parent transition.

## 4. Handle discovery without drifting

When evidence reveals an unrelated defect, production/Git mismatch, a broader data change, a missing invariant, or a conflict with the stated goal:

1. Mark the current contract `BREACHED` or `BLOCKED`; do not absorb the change.
2. State the exact evidence, affected surface, and whether the original goal can still be safely completed.
3. Open a separate reconciliation/amendment only after the user explicitly changes the desired outcome.

An amendment is append-only and requires a durable, verbatim user-authority reference identifying the exact new outcome. Preserve the original goal evidence, baseline, and prior receipts; link the amendment to their hashes. Discovery, an agent interpretation, a locked spec, a parent-agent decision, or undocumented “user approval” does not authorize an amendment. Never silently overwrite the contract or call a discovered production state “approved.”

## 5. Require real proof

Proof must test the user-visible or operational behavior that the goal promised. For each acceptance case, map every claim to named proof IDs, required environment, exact target/actor, expected observation, candidate SHA or artifact digest, raw artifact hash, and verifier. No acceptance case is met until all linked proof is met. A helper-only, mocked, or self-authored assertion cannot satisfy a user-visible or live claim.

Reject false-green substitutes: mocked end-to-end proof for a live claim, weakened fixture/threshold, success of a helper while the caller is wrong, a CodeRabbit green check without reading its walkthrough, or a test that proves only the new code path while an old fallback bypasses it.

For a PR, reconcile the title, body, generated summaries, all review comments, and structured diff. Any contradiction is a blocker until explained in the contract and independently verified.

For every live, release, data, configuration, migration, security, or user-visible claim, name the exact environment, traffic/execution path, expected commit/artifact digest, actor, observation, and rollback/backout evidence. A version endpoint, pod, canary, staging target, or control-plane observation is not production attestation unless it proves the claimed user/operation path receives the approved artifact and data/config manifest.

## 6. Deploy as the responsible developer

When the contract permits a release, perform merge, Weboyee deployment, and verification yourself using the repository release gate. Do not ask the user to run routine commands or take custody of deployment credentials.

Stop instead of deploying when the target SHA, artifact, data/config manifest, required receipt, live-activity safety condition, or verification result is missing or inconsistent. An emergency may contain or roll back the approved failure; it may not become a hidden feature/data rewrite.

## 7. Close honestly

Report the contract ID, actual diff, evidence, production attestation, and open items. Use `PASS`, `PARTIAL`, `FAIL`, or `BLOCKED`; never call a task complete because the implementation feels plausible. Then invoke `$production-goal-review`.
