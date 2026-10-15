# Release and rollback

## Current patch

This candidate is `0.1.13`. See [agent upgrade and rollback instructions](AGENT_REPAIR.md).
The installer bundle is qualified in an isolated Windows checkout; it does not
claim the user's live installation has been upgraded. Before declaring the local dashboard ready, verify
that `/health` is healthy and `/` returns HTTP 200 with a non-empty HTML body
containing `<html` and the exact `data-testid="plotkeeper-app"` marker. The installer/startup scripts replace a
listener only when its process is Plotkeeper-owned; a foreign process on the
configured port is a hard stop.

The cumulative release line includes immutable predecessor/successor chains.
Version `0.1.7` added project-grouped active-run selection, canonical Codex task
titles, truthful fallback tasks, evidence-gated plan reconstruction, isolated
Chromium app-window pop-out, and an atomic persisted private connector. It also
keeps every injected Codex resume bound to the enrolled run repository.
Rollback may restore an older executable, but it must never downgrade or rewrite
a ledger after a successor has been created. Preserve a copy of the migrated
ledger before any executable rollback.

Version `0.1.8` fixes the default installer path discovered during the v0.1.7
live installation: PowerShell now supplies an explicit zero sentinel when no
`-Port` was requested, so the connector-selection helper receives a stable
argument vector. The v0.1.7 tag remains immutable and is superseded by v0.1.8.

Version `0.1.9` keeps the generated listener owner record machine-local and
restores cross-platform CI by skipping only Windows PowerShell process-boundary
tests where those tools do not exist. The portable owner-schema checks still run.

Version `0.1.10` canonicalizes the process creation instant used by the listener
ownership proof. Equivalent legacy 12-hour, 24-hour, and new invariant UTC
representations match the same process, while malformed or mismatched records
continue to fail closed.

Version `0.1.11` preserves the whole-second precision of legacy owner records
while requiring full fractional-tick equality for new invariant ISO records.

Version `0.1.12` records the process that actually owns the TCP listener. A
legacy virtual-environment wrapper record migrates only when the listener is
its direct child and all applicable recorded identity fields still match.

## Release contract authority

Release authority is selected by the tracked pointer at
`runtime/goal-contracts/RELEASE_CONTRACT.json`. It names one contract path,
contract ID, and SHA-256 of the canonical JSON contract content. The host guard and
`scripts/verify_public_release.py` both resolve and validate this pointer;
filesystem mtime and contract filename ordering are never release authority.
The GitHub workflow passes the same pointer through
`PLOTKEEPER_CONTRACT_POINTER`. A successor contract that is not itself an
authorized release contract (including an `RL-NONE` lane) cannot unlock or
supersede the designated release contract.

## First public release

The first public release target is `EmergentKnowledgeGroup/PLOTKEEPER`, with
local `main` pushed as the GitHub default branch only after an exact-SHA
independent `DEPLOY_READY` review passes.

Pre-push checks:

```powershell
git status --short --branch
git diff b13dd6fdfde56f09bf3f07da78002970fcdbe744..HEAD --check
py -3 -m unittest discover -s tests -v
```

## Rollback

The protected public baseline for this release is
`b13dd6fdfde56f09bf3f07da78002970fcdbe744` (public main before 0.1.13,
including v0.1.12). If the `v0.1.13` release is defective, preserve its exact
commit for audit and prepare a reviewed revert PR restoring that baseline's
code. Do not use the historical v0.1.11 force-push recipe for this candidate.
Requalify the revert under the active release gate and verify public main after
merging it. A source revert does not authorize overwriting a newer live ledger.
Use the private installer backup for a local environment/source rollback as
described in `AGENT_REPAIR.md`; retain current runtime data and any post-upgrade
work. The old 2026-10-05 local-only contract remains immutable historical evidence;
only the tracked release pointer selects the current 2026-10-14 authority.
