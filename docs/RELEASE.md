# Release and rollback

## Current patch

This release is `0.1.9`. Before declaring the local dashboard ready, verify
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
git diff 73c89e7d402a0c498207e07299685ac729ecfde7..HEAD --check
py -3 -m unittest discover -s tests -v
```

## Rollback

The protected public baseline for this release is
`de8274ff2c52c69d9c297a7a5004486d48ecfb90` (`v0.1.8`). If the `v0.1.9` release
is defective, preserve the failed release commit for audit and
restore the public branch to that baseline with a lease-bound update:

```powershell
git fetch origin main
git push --force-with-lease=refs/heads/main:<REMOTE_FAILED_SHA> origin `
  de8274ff2c52c69d9c297a7a5004486d48ecfb90:refs/heads/main
```

Replace `<REMOTE_FAILED_SHA>` with the SHA independently read from GitHub. Do
not use an unqualified force push. Then verify that GitHub's default branch
resolves to the baseline and record a new live attestation. This rollback
returns public code to `v0.1.8`. It does not authorize opening a migrated ledger
with the older schema after successors exist; retain the failed release and
migrated ledger for audit and restore the pre-release ledger copy only if no
post-release run data must be preserved.
