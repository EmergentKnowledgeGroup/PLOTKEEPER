# Plotkeeper

Plotkeeper is a local, read-only run ledger and dashboard for Codex SpecSwarm.
It watches newly written Codex session events, connects root and child agents,
shows tasks, claims, evidence, and goal-contract context, and refuses to call a
run closed until the independent review gate reports `PASS` with zero open
items.

![Plotkeeper desktop dashboard](docs/images/plotkeeper-desktop.png)

<details>
<summary>Mobile dashboard</summary>

![Plotkeeper mobile dashboard](docs/images/plotkeeper-mobile.png)

</details>

## Why Plotkeeper

Long agent runs are difficult to inspect from one chat window. Plotkeeper gives
the human operator a local control surface without becoming another writer of
session truth:

- enrolls only new root sessions that invoke `$specswarm`;
- tails session JSONL by byte watermark and never edits those files;
- attaches child sessions and explicitly marked independent sessions;
- displays the active production goal, invariant set, task board, reports, and
  evidence links;
- opens the exact active run by run/session locator, and groups the active
  picker by project with real task labels and IDs;
- preserves closed runs as immutable history and creates a predecessor-linked
  successor when the same Codex task begins genuinely new SpecSwarm work;
- injects the required closeout review after the root requests completion;
- closes only on `verdict=PASS open_items=0` from that injected review.
- resumes injected reviews and check-ins from the enrolled run repository, and
  fails closed instead of inheriting Plotkeeper's own working directory.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- Codex sessions stored under `%USERPROFILE%\.codex\sessions` (configurable)
- Codex CLI on `PATH` for automatic check-in and review injection

Plotkeeper has no third-party runtime Python or browser dependencies.

## Install and run

Clone or download the repository, open PowerShell in its root, then run:

```powershell
.\scripts\install.ps1
```

The installer creates an isolated `.venv`, installs Plotkeeper into it, starts
the local service, and registers it for the current Windows user at sign-in.
Open <http://127.0.0.1:47831/>.

For an evaluation that does not touch your Codex sessions:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python examples\demo.py --serve --open
```

The populated demo runs at <http://127.0.0.1:47832/>.

## Use with SpecSwarm

1. Start Plotkeeper before beginning a new SpecSwarm run.
2. Invoke `$specswarm` in the root Codex task. Plotkeeper enrolls that root or,
   when its previous run is closed, creates one active successor linked to the
   immutable predecessor. Historical sessions remain available by exact run ID.
3. Put the displayed `Plotkeeper-Run-ID` in locked artifacts and any independent
   task that must attach to the run.
4. Sync the approved checklist and goal contract:

   ```powershell
   .\scripts\pk.ps1 sync-plan --run-id <RUN_ID> `
     --file .\path\to\CHECKLIST.md `
     --contract .\runtime\goal-contracts\<CONTRACT>.json
   ```

5. Agents report claims or evidence through the CLI or session markers. When
   the root emits `PK:GOAL_COMPLETE_REQUEST` and completes its turn, Plotkeeper
   injects `$production-goal-review`.
6. Plotkeeper closes the run only after the injected task emits:

   ```text
   PK:REVIEW_RESULT run_id=<RUN_ID> verdict=PASS open_items=0
   ```

See [Integration](docs/INTEGRATION.md) for the complete marker contract and
[Usage](docs/USAGE.md) for every command.

## Documentation

- [Installation and configuration](docs/INSTALLATION.md)
- [Usage and CLI reference](docs/USAGE.md)
- [SpecSwarm integration](docs/INTEGRATION.md)
- [Architecture and trust boundaries](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Examples](examples/README.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Security](docs/SECURITY.md)
- [Release and rollback](docs/RELEASE.md)

## Automatic Codex execution gate

Plotkeeper includes an optional, one-command Codex integration that removes the
need to invoke MSW or invent a duration on every task:

```powershell
.\integrations\codex\install.ps1
```

It installs the bundled EKG-owned `specswarm`, `production-goal-contract`,
`production-goal-review`, and `adaptive-execution` skills, plus vendored copies
of Slopware's `msw`, `msw-hook`, and `timebox` packages. No required skill code
is downloaded from another marketplace. It then adds Plotkeeper's adaptive
`UserPromptSubmit` and `Stop` hooks. The first
unfamiliar task runs as an untimed calibration; later comparable work reuses
measured timing evidence from completed work. Incomplete or unproven preflights
remain in history but cannot seed a timebox. The stop hook loops an agent back when its execution
receipt is missing or incomplete.

After installation, run `/hooks` in Codex to inspect and trust the three
effective hooks. Trust cannot and should not be silently granted by an
installer. See the [complete Codex integration guide](integrations/codex/README.md).

Credit for MSW, MSW Hook, and Timebox belongs to **Slopware Engineer
(`@aienginerd`)** and upstream contributors. See
[third-party notices](THIRD_PARTY_NOTICES.md).

## Current scope

Plotkeeper is Windows-first and local-only. It binds to loopback by default,
uses SQLite for its derived ledger, and expects Codex's local JSONL session
format. It is not a remote collaboration server, a replacement for Git or CI,
or authority to bypass the production goal contract.

## License

Plotkeeper, SpecSwarm, and the bundled EKG governance skills are licensed under
the [Apache License 2.0](LICENSE). Vendored Slopware packages retain their
upstream CC BY 4.0 license and attribution.
