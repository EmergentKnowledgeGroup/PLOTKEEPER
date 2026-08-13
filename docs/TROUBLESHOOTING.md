# Troubleshooting

## Dashboard does not open

Check the health endpoint:

```powershell
$connector = Get-Content .\runtime\plotkeeper-connector.json -Raw | ConvertFrom-Json
Invoke-RestMethod "$($connector.url)/health"
```

If the port is unavailable, start on another one:

```powershell
.\scripts\start.ps1 -Port 48731
```

## `No module named plotkeeper`

Install the checkout into its environment again:

```powershell
.\.venv\Scripts\python -m pip install -e .
```

## A run was not enrolled

- Confirm Plotkeeper was running before the `$specswarm` invocation.
- Confirm the invocation was in a root session, not only a child.
- Confirm `PLOTKEEPER_SESSIONS` points to the active Codex sessions directory.
- Historical bytes before Plotkeeper's first activation are deliberately
  ignored; start a new root run after activation.

## A child is missing

Native children need a recorded parent session ID. Independent roots need the
exact `Plotkeeper-Run-ID: <RUN_ID>` marker while the target run remains open.

## A run will not close

This is normally a proof result, not a dashboard defect. Confirm the root
emitted `PK:GOAL_COMPLETE_REQUEST`, the root turn completed, review injection
succeeded, and the injected reviewer emitted `PASS` with zero open items.

## Reset the evaluation demo

Running the demo again recreates only `examples/.demo-runtime/`:

```powershell
.\.venv\Scripts\python examples\demo.py --serve
```

It does not read or modify your real Codex sessions.
### Pop out joins an existing browser session

Current Plotkeeper versions first launch Edge or Chrome in app mode with `runtime/plotkeeper-browser-profile/`. This creates a standalone window isolated from the normal browser profile. If the machine has neither supported Chromium executable, Plotkeeper falls back to the registered default browser and that browser may choose a tab.

### An active run has one Codex task instead of its checklist

The run is enrolled, but SpecSwarm's checklist was never synchronized. The single row is a truthful thread-level fallback, not a fabricated plan. Re-run the documented `sync-plan` command with the locked spec/checklist/blockerboard to populate the real workstreams.

Alternatively, choose **Reconstruct plan**. The enrolled Codex task—not Plotkeeper's filename matcher—will identify its original artifacts, synchronize them into the exact run, read the rows back, and report any correction. Missing or invalid enrolled directories fail closed.
