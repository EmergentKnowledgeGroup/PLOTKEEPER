# SpecSwarm integration

Plotkeeper observes session output; integration is a small marker protocol, not
a direct write into Codex session storage.

The repository's Codex installer includes SpecSwarm and its EKG governance
skills. Install them once with `integrations\codex\install.ps1`; no separate
SpecSwarm installation or Slopware marketplace fetch is required.

## 1. Enroll the root

Start Plotkeeper before the task. A new root user message containing
`$specswarm` or `run specswarm` enrolls the run. The first activation watermark
intentionally excludes older session bytes.

## 2. Attach work

Normal Codex child sessions attach through their recorded parent session ID.
An independent root task can attach by emitting this exact marker:

```text
Plotkeeper-Run-ID: <RUN_ID>
```

Put the marker in locked artifacts and delegated prompts when a separate task
must remain visible under the same run.

## 3. Populate the task board

Use the run ID shown by `status` or the dashboard:

```powershell
.\scripts\pk.ps1 sync-plan --run-id <RUN_ID> `
  --file .\examples\specswarm-checklist.md `
  --contract .\runtime\goal-contracts\<CONTRACT>.json
```

## 4. Report progress

Session text matching `claim: ...` or `report: ...` is retained as an
agent-reported item. HTTP URLs on the same observed content are recorded as
evidence links. The explicit CLI form is preferred for deterministic tooling:

```powershell
.\scripts\pk.ps1 report --run-id <RUN_ID> --kind claim `
  --text 'Package smoke test passed' --evidence 'runtime/qa/install-smoke.txt'
```

## 5. Request closeout

The root emits:

```text
PK:GOAL_COMPLETE_REQUEST
```

When the root turn then completes, the run moves to `REVIEW_REQUIRED` and
Plotkeeper injects a Codex continuation requiring `$production-goal-review`.
Only its terminal marker can close the run:

```text
PK:REVIEW_RESULT run_id=<RUN_ID> verdict=PASS open_items=0
```

`PARTIAL`, `FAIL`, `BLOCKED`, a nonzero open-item count, a non-injected receipt,
or a missing receipt leaves the run open.

## Minimal integration checklist

- Start Plotkeeper before the new SpecSwarm root.
- Preserve the run ID in locked artifacts and independent task prompts.
- Sync the authoritative checklist and sealed production contract.
- Report evidence paths; do not report conclusions without evidence.
- Emit the completion request only after implementation evidence is complete.
- Let the independent review result determine closure.
