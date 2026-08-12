---
name: specswarm
description: >-
  Run a full multi-agent specification hardening workflow covering gap and
  edge-case review, implementation touchpoint mapping, over-engineering and
  reward-hacking prevention, final QA consolidation, then lock the spec,
  execution checklist, and blockerboard. Use when the user says "$specswarm",
  "run specswarm", "harden this spec", "lock this spec", or requests
  implementation-ready spec/checklist/blockerboard artifacts.
---

# SpecSwarm

Turn an approved plan or draft spec into three decision-complete, internally consistent implementation artifacts. Do not implement application code.

## Output Contract

Unless the user explicitly requests review-only mode, create or update exactly these durable artifacts:

1. Hardened, locked specification.
2. Execution or phase checklist.
3. Blockerboard.

Keep raw reviewer output in native agent messages or a project-local ignored temporary directory. Do not add a fourth report unless requested. Summarize material findings in chat.

The parent may edit only planning artifacts, checkpoint files required by repo SOP, and this skill when explicitly requested. Review subagents are read-only.

## Required Model And Effort Policy

Use GPT-5.6 Sol (`gpt-5.6-sol`) for every SpecSwarm reviewer and the final QA consolidator. Do not silently substitute another model and do not describe a run as Sol unless the launch surface confirms or inherits Sol.

Before launching reviewers, score the spec on five axes, one point each:

- More than one implementation subsystem or product surface.
- External service, model, runtime, data, security, or privacy boundary.
- Migration, compatibility, rollout, backout, or destructive-state risk.
- Release claim requiring real-world evidence rather than unit tests alone.
- Material ambiguity, novelty, or unresolved tradeoffs.

Select effort from the total:

| Score | Class | Gap reviewer | Mapper | Guardrail reviewer | Final QA |
|---:|---|---|---|---|---|
| 0-1 | Easy | medium | medium | medium | medium |
| 2-3 | Standard | high | medium | high | high |
| 4-5 | Hard | xhigh | high | xhigh | xhigh |

Never use low effort for SpecSwarm. Escalate one reviewer from medium to high when its lane contains the dominant risk even if the overall score is easy. Record the score, class, and selected efforts in the locked spec or final summary.

Official Codex guidance treats Sol as the strongest GPT-5.6 choice for complex open-ended work and recommends medium for ordinary planning, high/xhigh for difficult review work. Keep this policy dynamic; do not burn xhigh on a narrow, obvious spec.

## Agent Launch Order

Use the highest-fidelity available path:

1. Native in-app subagents configured for or inheriting GPT-5.6 Sol.
2. Codex CLI only when native launch cannot pin/inherit Sol cleanly and the installed CLI successfully preflights `gpt-5.6-sol`.
3. If neither launch path can run Sol, mark the run `REVIEW_INCOMPLETE`, preserve the evidence, and stop. Do not simulate independent Sol review, lock a production-ready spec, or produce a production goal contract.

For native agents, give each a clean, clear, concise goal prompt containing the target paths, its one review lane, read-only scope, required output shape, and a self-review instruction. Record a launch receipt with actual model, effort, run identity, target-input hashes, and read-only scope. Do not ask one agent to perform multiple first-pass lanes.

For CLI fallback, preflight before the real swarm:

```powershell
codex exec --ephemeral --skip-git-repo-check --sandbox read-only -C $PWD.Path `
  -m gpt-5.6-sol -c 'model_reasoning_effort="medium"' 'Reply exactly SOL_OK.'
```

If the CLI reports unknown metadata, fallback metadata, or that Sol requires a newer Codex version, treat the CLI path as unavailable. Never continue a claimed Sol run through fallback metadata.

CLI review pattern:

```powershell
codex exec --ephemeral --skip-git-repo-check --sandbox read-only -C $PWD.Path `
  -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -o $outFile $prompt
```

Replace `high` with the selected effort. Put `$outFile` under a project-local ignored temporary directory, never a tracked docs directory.

## Workflow

### 0. Require Plotkeeper Enrollment And Visible Surface

SpecSwarm is the sole automatic Plotkeeper enrollment gate. Before launching
reviewers:

1. Verify `http://127.0.0.1:47831/health` returns healthy. If it does not, stop
   and report `PLOTKEEPER_UNAVAILABLE`; do not continue an untracked SpecSwarm.
2. Fetch `http://127.0.0.1:47831/` and require HTTP 200, a non-empty body, an
   `<html` element, and the exact `data-testid="plotkeeper-app"` dashboard
   marker. If any check fails,
   stop and report `PLOTKEEPER_UNAVAILABLE`; do not open the panel or emit its
   receipt.
3. Resolve the exact run before opening the panel. Prefer the current
   `CODEX_SESSION_ID`/`CODEX_THREAD_ID` when available:
   `py -3 "$codexHome\skills\specswarm\scripts\plotkeeper_cli.py" current --session-id <id>`;
   otherwise use an explicit `--run-id` from locked artifacts. The command
   must return one active run and a `dashboard_url` containing its locator.
   Use the CodexApp `open_in_codex` tool with that run-bound URL and placement
   `right`; a bare root URL is permitted only when no local identity exists and
   the command reports exactly one active run. Re-check the same valid HTML
   response after the tool returns; an open tool call alone is not proof of a
   visible panel.
4. Only after the valid HTML check succeeds, emit the exact commentary marker
   `PK:PANEL_OPENED cwd=<absolute-project-path>` so the watcher can record the
   visible-surface receipt.
5. Wait for enrollment, then run
   `$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }`, then
   `py -3 "$codexHome\skills\specswarm\scripts\plotkeeper_cli.py" current --cwd "$PWD"` only when no
   session identity is available. Write the returned `run_id` as
   `Plotkeeper-Run-ID` into the locked spec, checklist,
   blockerboard, checkpoint, and final report. Never mutate the sealed
   production goal contract; pass its path to Plotkeeper instead.

Never reopen or overwrite a closed Plotkeeper run. If the same Codex task has
follow-up work after closeout, Plotkeeper enrollment creates one OPEN successor
linked to the immediate predecessor; repeated enrollment returns that active
successor. Later agents resolve the exact active successor and attach their
session to it, while the immutable predecessor remains available by explicit
run ID for history.

### 1. Ground The Work

- Read repo instructions and checkpoint files.
- Capture immutable verbatim user-goal evidence: source locator, exact text, hash, and time. Keep it separate from the draft spec and preserve every user constraint.
- Verify branch, head, worktree, and dirty state.
- Read the complete target spec and directly relevant companion docs.
- Inspect existing implementation touchpoints enough to resolve discoverable facts.
- Locate existing checklist and blockerboard, if any.
- Score complexity and select reviewer efforts.
- Write the required phase-start checkpoint before planning-artifact edits when repo SOP requires it.

If no spec path or pasted spec exists, ask exactly: `Which spec file should I run SpecSwarm on?` and stop.

### 2. Run Three Independent First Passes

Launch these lanes in parallel when possible:

#### Gap And Edge-Case Reviewer

```text
[ROLE]
You are the SpecSwarm gap and edge-case reviewer.

[GOAL]
Read the target spec and relevant repo truth. Find missing requirements, contradictions, ambiguous terms, edge cases, safety or integrity failures, data-loss risks, test/eval holes, rollout/backout gaps, and unclear ownership.

[SCOPE]
Read-only. Do not edit or implement. Preserve intentional product choices. Prefer the smallest decision-complete fix.

[OUTPUT]
Blocking Issues; Edge Cases; Minimal Spec Fixes; Open Questions. Cite paths/sections. End with a self-review removing speculation and duplicates.
```

#### Implementation Touchpoint Mapper

```text
[ROLE]
You are the SpecSwarm implementation touchpoint mapper.

[GOAL]
Map each spec subsystem to current files, modules, routes, schemas, configs, tests, migration/rollout hooks, ownership boundaries, and no-touch zones. Verify mappings from the repo; label remaining hypotheses.

[SCOPE]
Read-only. Do not edit or implement. Report the smallest realistic blast radius.

[OUTPUT]
Table: spec area | verified touchpoints | tests/gates | risks/no-touch zones. End with a self-review for unsupported mappings.
```

#### Over-Engineering And Reward-Hacking Reviewer

```text
[ROLE]
You are the SpecSwarm over-engineering and reward-hacking prevention reviewer.

[GOAL]
Find unnecessary platform sprawl, duplicate systems, premature abstraction, hidden scope expansion, fake gates, weak assertions, test-only shortcuts, gameable metrics, and ways implementation could pass without delivering the real behavior.

[SCOPE]
Read-only. Preserve intentional product choices. Recommend the smallest enforceable guardrail.

[OUTPUT]
Over-Engineering Risks; Reward-Hacking Risks; Minimal Guardrails; Test/Eval Hardening. End with a self-review distinguishing blockers from optional polish.
```

### 3. Run Final QA Consolidation

After all first-pass results arrive, launch a fresh Sol final-QA agent with the spec and distilled first-pass findings:

```text
[ROLE]
You are the SpecSwarm final QA consolidator.

[GOAL]
Review the target spec and the three independent findings sets. Deduplicate and normalize severity; identify remaining contradictions, missing decisions, inconsistent acceptance gates, and ways an implementer could misread the final spec/checklist/blockerboard.

[SCOPE]
Read-only. Add no scope unless correctness requires it. Treat real behavior and evidence as authoritative over superficial test success.

[OUTPUT]
Executive Summary; Blocking Issues; Exact Minimal Fixes; Residual Risks; Lock Recommendation. End with a self-review confirming every blocker is actionable.
```

### 4. Lock The Three Artifacts

The parent folds accepted findings into the smallest coherent change set. Preserve every reviewer finding in a disposition ledger: source run/finding ID, accepted/rejected/deferred status, rationale, authority, and final artifact location. An unresolved product, policy, consent, ownership, compatibility, release, or safety decision remains blocking; do not convert it into an assumption or deferred non-blocker.

The locked spec must include:

- `Status: LOCKED`, lock date/version, source plan, and change-control rule.
- Goal, audience, in/out of scope, ownership, and no-touch zones.
- Interfaces, schemas, state transitions, data flow, error behavior, and migration compatibility.
- Security/privacy/consent boundaries and secret handling.
- Rollout, backout, observability, real-world proof, and release claims.
- Exact PASS/CONDITIONAL/FAIL semantics where applicable.
- Anti-reward-hacking rules that prevent mocks, smoke-only substitutes, weakened fixtures, or unverified claims from satisfying real gates.
- Explicit assumptions and genuine blockers.

The checklist must:

- Link to the locked spec and use atomic implementation tasks in dependency order.
- Include required tests, evidence, documentation, migration, packaging, and checkpoint steps.
- Use honest statuses only: `PENDING`, `IN PROGRESS`, `BLOCKED`, `DONE`.
- Start implementation work as `PENDING`; SpecSwarm review is not implementation evidence.

The blockerboard must:

- Link to the locked spec and checklist.
- Separate release blockers, implementation risks, external dependencies, and deferred non-blockers.
- State owner, detection evidence, unblock condition, and fallback/backout for each active blocker.
- Never downgrade a blocker merely because it is expensive or inconvenient.

Before final-lock review, allocate the production-contract ID and add that ID only (not its final hash/path) to all three draft artifacts. Then launch a fresh independent Sol final-lock reviewer against the exact hashes of the three edited artifacts, the immutable user-goal evidence, and the disposition ledger. It must confirm that the final artifacts preserve the original user constraints, all accepted findings landed, rejections are authorized, and no parent edit introduced new scope. If it cannot run, mark `REVIEW_INCOMPLETE`; do not set `Status: LOCKED`. Do not edit the three locked artifacts after this review.

### 5. Produce The Mandatory Production Goal Contract

After the three artifacts pass the fresh final-lock review, invoke `$production-goal-contract` before declaring SpecSwarm complete. This is required even when the user did not separately name that skill.

- Bind the locked spec, execution checklist, and blockerboard to one durable production goal contract with `origin: SPECSWARM`; the validators reject a SpecSwarm contract without all three locked-artifact hashes and a complete requirement trace.
- Bind the contract's requested outcome to immutable original user-goal evidence, not agent-authored planning prose. Trace each original user requirement to the exact locked artifact section and acceptance case.
- Treat locked artifacts as interpreted planning inputs only. `LOCKED` does not create implementation, merge, deployment, or product-decision authority. Set `execution_authority: AUTHORIZED` only when a verbatim original user request explicitly authorizes execution; “harden,” “lock,” “plan,” or an agent’s claim of unambiguous intent is never enough. Otherwise create a `PLANNING_ONLY` / `NOT_AUTHORIZED` contract and report execution `BLOCKED`.
- Declare protected baseline, allowed and no-touch surfaces, invariants, proof obligations, change-control, deployment/rollback conditions, and stop conditions.
- Record unresolved product decisions as blockers. Do not hide them inside a broad implementation contract.
- Bind the contract to the exact already-reviewed artifact hashes and require the validator to verify the on-disk hashes. Validate the resulting contract receipt with `--require-locked-artifacts` and record its ID, receipt hash, immutable user-authority reference, hashes of all three locked artifacts, `ACTIVE` status, non-empty scope/invariants/proof/stop conditions, and first required transition. If validation fails, report `BLOCKED`; do not call SpecSwarm complete or implementation-ready.
- Keep only the preallocated contract ID in the locked spec/checklist/blockerboard. Record path/hash in the checkpoint and final report so no post-review artifact edit invalidates the final-lock review.
- After the sealed contract validates, run
  `py -3 "$codexHome\skills\specswarm\scripts\plotkeeper_cli.py" sync-plan --run-id <id> --file <spec> --file <checklist> --file <blockerboard> --contract <goal-contract>`.
  This is the deterministic
  task-board and original-goal population gate. Do not declare SpecSwarm
  complete if Plotkeeper rejects the sync.

SpecSwarm remains planning-only: producing the contract must not implement application code, merge, or deploy. The future implementing agent must invoke the same contract skill at task start and `$production-goal-review` before claiming completion.

### 6. Verify And Checkpoint

- Re-read all three complete artifacts.
- Search for inconsistent status, schema, endpoint, model, threshold, ownership, and scope terms.
- Verify every checklist gate and blocker points to a spec requirement.
- Run Markdown/link/schema checks available in the repo.
- Run `git diff --check` and a diff-scope audit.
- Confirm only the intended planning artifacts plus required checkpoint state changed.
- Write the post-lock checkpoint with validations and the exact next implementation command.

Do not mark the spec locked while a product decision remains open. Implementation blockers may remain if the spec defines their detection and unblock conditions without asking the implementer to invent policy.

## Hard Rules

- Keep review agents read-only and require concise self-reviewed reports.
- Do not implement application code during SpecSwarm.
- Preserve user data and unrelated dirty state.
- Do not create branches/worktrees/stashes when the repo or user requires main-only work.
- Treat `zero reward hacking` literally: no fake services, mocked end-to-end proof, reduced fixtures, weakened thresholds, or undocumented manual bypasses.
- Do not let optional integrations become release-critical unless the approved spec says so.
- Do not let an AI judge replace a required human decision.
- Do not describe external, hardware, model, packaging, migration, or security claims as proven without corresponding evidence.

## Final Report

Start with the outcome, then report:

- Three locked artifact paths.
- Complexity score/class and actual reviewer efforts.
- Material blockers folded into the spec.
- Guardrails added against over-engineering and reward hacking.
- Validation/checkpoint result.
- Production goal-contract ID/path and the first contract stop condition.
- Exact next implementation command.
- Plotkeeper run ID and confirmation that the right-side live panel opened.

If review-only was requested, report findings without editing or locking artifacts.
