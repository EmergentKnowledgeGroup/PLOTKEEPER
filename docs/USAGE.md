# Usage

Run commands through `scripts\pk.ps1` after the standard installation, or use
`.\.venv\Scripts\plotkeeper.exe` directly.

## Inspect runs

```powershell
.\scripts\pk.ps1 status
.\scripts\pk.ps1 current --cwd 'Z:\YourProject'
```

`status` polls once and returns all runs as JSON. `current` returns the newest
open run, optionally restricted to an exact working directory.

## Add an explicit report

```powershell
.\scripts\pk.ps1 report `
  --run-id <RUN_ID> `
  --kind verification `
  --text 'Focused tests passed' `
  --evidence 'runtime/qa/test-results.txt'
```

Reports are claims with attached evidence references; the dashboard does not
interpret an evidence string as proof that a run passed.

## Sync a plan and goal contract

```powershell
.\scripts\pk.ps1 sync-plan `
  --run-id <RUN_ID> `
  --file .\SPEC.md `
  --file .\CHECKLIST.md `
  --contract .\runtime\goal-contracts\PROD-example.json
```

Checkbox lines (`- [ ]` and `- [x]`) and numbered task lines become dashboard
tasks. Syncing replaces the run's derived task list; it never edits the source
documents. Plotkeeper displays a supplied contract but does not validate or
authorize it—the production goal-contract workflow owns that decision.

## Run the service manually

```powershell
.\scripts\start.ps1
```

Health and data endpoints:

```powershell
$connector = Get-Content .\runtime\plotkeeper-connector.json -Raw | ConvertFrom-Json
Invoke-RestMethod "$($connector.url)/health"
Invoke-RestMethod "$($connector.url)/api/runs"
```

## Stop behavior

The foreground server stops with `Ctrl+C`. The current installer starts a
hidden process but does not install a Windows service. To stop that instance,
identify the process whose command line includes `plotkeeper.cli serve` using
normal Windows process tools, then stop that exact process.
