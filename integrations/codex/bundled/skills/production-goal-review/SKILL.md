---
name: production-goal-review
description: Independently audit a completed or proposed production goal against its original goal contract, actual diff, review signals, tests, deployment evidence, and live behavior; then add targeted anti-drift regression controls. Use before closing, merging, or calling green any production-affecting Codex task, after an incident/regression, and after SpecSwarm emits a production contract.
---

# Production Goal Review

Be the adversarial closeout pass. Test whether the work achieved the user's actual goal, not whether the implementer can produce green-looking artifacts.

Read [the adversarial fixture catalog](references/adversarial-fixtures.md) and select every fixture relevant to the goal before issuing a verdict.
Read [the review-receipt schema](references/review-receipt.md). Emit and validate one immutable review receipt with `scripts/validate_review_receipt.py <contract> <receipt> --repo-root . --receipt-dir <goal-receipt-dir>` for every verdict; prose is not a review receipt.

## 1. Establish the evidence set

Read the original user goal and the immutable contract before reading the implementation narrative. Collect:

- immutable raw user-goal evidence, full contract history, baseline and candidate SHAs, full structured diff, untracked/dirty-state evidence;
- PR title/body, generated walkthroughs, every review thread, checks, and replies;
- test commands, raw results, release/deployment receipts, and rollback evidence;
- read-only production artifact/config/data/version attestations and user-visible behavior proof;
- the final agent claim and any prior related incident records.

Missing evidence is not neutral. Mark the affected claim `UNPROVEN`.

Obtain the raw sources independently of the implementer's narrative. Independence requires a separate review run, no implementation/delegation/approval authorship, and a review receipt listing every inspected locator and hash. Curated evidence supplied by the implementer is supplementary, not authority.

## 2. Run the contract comparison

For each contract field, record `MET`, `VIOLATED`, or `UNPROVEN`:

```text
User outcome and acceptance behavior
Allowed and forbidden files/resources/semantic fields
Protected baseline and source-of-truth provenance
Invariants and compatibility promises
Required validation and independent-review evidence
Merge, deployment, rollback, and live-attestation obligations
```

Check the complete diff, not only staged files or the author’s file list. Compare semantic payloads where identifiers can remain stable while meaning changes. Treat a production/Git mismatch as a discrepancy to reconcile, not proof that one side is approved.

## 3. Attack false-green paths

Produce at least three concrete counterfactuals appropriate to the task:

```text
How could this pass every listed check while violating the user’s goal?
What dirty, fallback, generated, cached, or production-first path bypasses the test?
What prose, metric, fixture, baseline, or reviewer-triage trick hides the real delta?
```

Derive counterfactuals from every acceptance case, proof path, fallback/legacy route, deployment/data/configuration path, and protected invariant. Three is a floor, not coverage. For each counterfactual, identify the exact existing control that stops it or mark it an uncovered failure. Do not accept “the agent would not do that” or a general reminder as a control. An uncovered relevant path prohibits `PASS`.

For PRs, independently reconcile generated review summaries/walkthroughs with the diff even when the bot posts no actionable inline finding. “No actionable comments” is not a semantic review result.

## 4. Return a binding verdict

Use a phase-matched verdict only; a passing planning or local-validation review never authorizes merge, deployment, or closure. Use only these verdicts:

- `PASS`: every obligation for the named phase is met and counterfactuals are stopped by evidence.
- `PARTIAL`: the intended work may exist, but a required proof/invariant is missing or unproven.
- `FAIL`: scope drift, regression, false claim, unsafe release, or a violated contract occurred.
- `BLOCKED`: external information/action prevents a verdict.

Only a phase-matched `PASS` in a validated immutable review receipt with all required evidence permits that exact phase transition. `PARTIAL`, `FAIL`, and `BLOCKED` never permit closure, merge, or deployment. A user may authorize a new outcome only through a new append-only contract amendment; that authorization does not convert missing evidence into a pass.

## 5. Convert confirmed failures into regression controls

For every `PARTIAL` or `FAIL`, implement or schedule one smallest enforceable control at the failure boundary:

| Failure boundary | Required control class |
|---|---|
| Agent goal/scope drift | Goal-contract rule plus contract-diff assertion |
| Semantic data/content drift | Structured semantic diff and adversarial fixture |
| Incomplete review triage | PR-summary/diff reconciliation gate |
| False test green | Behavioral/integration regression test |
| Bad merge/deploy claim | Release receipt or live-attestation gate |
| Runtime/fallback bypass | Route-complete behavior test and fail-closed receipt |

Do not settle for a retrospective recommendation. Add the exact rule, test, CI/release condition, or skill control that would have stopped the confirmed failure. A scheduled control remains unresolved and cannot upgrade the originating verdict. If implementation requires a new product decision or authority, record it as an explicit blocker rather than fabricating a fix.

Every new control needs a red adversarial fixture containing: attacker move, expected stop point, pre-control failing artifact, post-control passing artifact, evidence hash, enforcing command/check, owner, and enforcement location. The fixture must fail against the pre-control behavior and pass only when the control truly blocks the bypass.

## 6. Preserve independent judgment

Every production-affecting closeout requires an independent read-only reviewer who did not implement, delegate, or approve the candidate. The parent remains responsible for the final decision but may not relabel an adverse result as a pass; it must collect new evidence and obtain a new review verdict.

## Final output

Start with the verdict. Include contract ID, met/violated/unproven table, actual scope, counterfactual results, regression controls added or blocked, production status, and exact next action. Keep raw logs out of the final report but preserve their paths.

When the review was requested by Plotkeeper, inspect the entire Plotkeeper run
surface before returning the verdict: every task, child report, blocker,
timeline entry, and open item. End with exactly one machine-readable line:

`PK:REVIEW_RESULT run_id=<id> verdict=<PASS|PARTIAL|FAIL|BLOCKED> open_items=<integer>`

Only `PASS` with `open_items=0` permits Plotkeeper to freeze the run. The
reviewing agent never issues or fabricates `PK:CLOSEOUT`; Plotkeeper owns that
state transition.
