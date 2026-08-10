---
name: adaptive-execution
description: Automatically govern substantive Codex work with an MSW contract, evidence-calibrated timing, fail-closed execution receipts, and verified closeout. Use for implementation, debugging, audits, research, planning, QA, documentation, release work, repository actions, or any non-trivial task. Also use when a global or project policy requires adaptive execution, calibration, comparable-task timing, MSW, Timebox, completion proof, or anti-churn enforcement. Do not require the user to name this skill.
---

# Adaptive Execution

Route every substantive turn through a durable execution receipt. Treat the receipt as a gate, not optional reporting.

## Start the turn

Run this before substantive tools or recommendations:

```powershell
py -3 "$env:USERPROFILE\.codex\skills\adaptive-execution\scripts\adaptive_execution.py" begin --turn-id "<turn_id>" --session-id "<session_id>" --cwd "<cwd>" --summary "<requested outcome>" --task-type "<type>" --risk "<low|medium|high>" --systems "<comma-separated>" --validation "<comma-separated>"
```

Use the turn and session IDs supplied by hook context when present. If unavailable outside a hooked Codex host, generate stable local identifiers and disclose that enforcement is advisory.

The command returns one route:

- `calibration`: no sufficiently comparable completed record exists. Work without an invented deadline and measure the result.
- `timebox`: comparable evidence exists. Use the returned AWT and CGP exactly with the installed canonical `$timebox` skill.

In both routes, apply the installed canonical `$msw` skill to bind the requested outcome and smallest sufficient proof. Never weaken required acceptance criteria to meet a clock.

## Prevent route-skipping

Do not:

- call a task conversational, trivial, or already complete after substantive work began;
- reuse another turn's receipt;
- close before evidence exists;
- label partial or unverified work `complete_verified`;
- fabricate systems, validation, blockers, comparison strength, or timestamps;
- omit a timing record because the task ended incomplete;
- create a persisted Codex goal unless the user explicitly requested durable continuation.

If the route or metadata is wrong, rerun `begin` for the same turn with corrected metadata before proceeding. The ledger preserves the latest route decision and audit timestamps.

## Converge and close

When substantive work has converged and only closeout remains, run:

```powershell
py -3 "$env:USERPROFILE\.codex\skills\adaptive-execution\scripts\adaptive_execution.py" converge --turn-id "<turn_id>"
```

After validation, close the receipt:

```powershell
py -3 "$env:USERPROFILE\.codex\skills\adaptive-execution\scripts\adaptive_execution.py" close --turn-id "<turn_id>" --outcome "complete_verified" --proof "<specific evidence>" --open-items "" --variance "<material variance or none>" --blocked-seconds 0
```

Allowed outcomes are `complete_verified`, `complete_unverified`, `incomplete`, and `unproven`. `complete_verified` requires non-empty proof and no open required items. Every other outcome requires explicit open items.

The global `Stop` hook checks the receipt. If it is missing or open, it returns a continuation prompt that sends the agent back through this workflow without asking the user.

## Comparability

Read [references/comparison-policy.md](references/comparison-policy.md) when interpreting a derived route or correcting classification. Read [references/ledger-schema.md](references/ledger-schema.md) only when debugging or extending the ledger.

## Persisted goals

Use the receipt's task contract for normal turns. Create or update a persisted Codex goal only when the user explicitly requests a goal, automatic continuation, or a durable multi-turn outcome. Do not use goal creation as a substitute for this receipt.
