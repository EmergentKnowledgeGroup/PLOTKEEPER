# Plotkeeper

Plotkeeper is a local, read-only observer for Codex App session JSONL. It enrolls
only new root sessions that invoke `$specswarm`, links observed child sessions,
stores agent-reported claims and evidence in SQLite, and displays the run at
<http://127.0.0.1:47831/>.

## Lifecycle

1. `$specswarm` enrolls the root session and opens the dashboard in Codex's
   right panel.
2. Specswarm writes `Plotkeeper-Run-ID` into its locked artifacts and runs
   `scripts/pk.ps1 sync-plan` to populate the task board.
3. Plotkeeper tails new session bytes; it never edits Codex session files.
4. `PK:GOAL_COMPLETE_REQUEST` followed by the root turn's completion triggers a
   mandatory injected review turn.
5. Only `PK:REVIEW_RESULT ... verdict=PASS open_items=0` closes the run. Closed
   runs cannot absorb later work.

Install/start for the current Windows user:

```powershell
& 'Z:\Plotkeeper\scripts\install.ps1'
```
