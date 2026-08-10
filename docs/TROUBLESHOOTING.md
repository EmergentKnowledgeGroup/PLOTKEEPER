# Troubleshooting

## Dashboard does not open

Check the health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:47831/health
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
