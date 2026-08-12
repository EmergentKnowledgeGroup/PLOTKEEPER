# Release and rollback

## Current patch

This release is `0.1.6`. Before declaring the local dashboard ready, verify
that `/health` is healthy and `/` returns HTTP 200 with a non-empty HTML body
containing `<html` and the exact `data-testid="plotkeeper-app"` marker. The installer/startup scripts replace a
listener only when its process is Plotkeeper-owned; a foreign process on the
configured port is a hard stop.

The cumulative release line includes immutable predecessor/successor chains.
Version `0.1.6` additionally makes closeout validation atomic at the ledger
boundary and launches injected Codex resumes from the enrolled run repository.
Rollback may restore an older executable, but it must never downgrade or rewrite
a ledger after a successor has been created. Preserve a copy of the migrated
ledger before any executable rollback.

## First public release

The first public release target is `EmergentKnowledgeGroup/PLOTKEEPER`, with
local `main` pushed as the GitHub default branch only after an exact-SHA
independent `DEPLOY_READY` review passes.

Pre-push checks:

```powershell
git status --short --branch
git diff 3dc3488cbfaa55df13e6abebf4b1ca395c319916..HEAD --check
py -3 -m unittest discover -s tests -v
```

## Rollback

The protected public baseline for this release is
`3dc3488cbfaa55df13e6abebf4b1ca395c319916` (`v0.1.5`). If the `v0.1.6` release
is defective, preserve the failed release commit for audit and
restore the public branch to that baseline with a lease-bound update:

```powershell
git fetch origin main
git push --force-with-lease=refs/heads/main:<REMOTE_FAILED_SHA> origin `
  3dc3488cbfaa55df13e6abebf4b1ca395c319916:refs/heads/main
```

Replace `<REMOTE_FAILED_SHA>` with the SHA independently read from GitHub. Do
not use an unqualified force push. Then verify that GitHub's default branch
resolves to the baseline and record a new live attestation. This rollback
returns public code to `v0.1.5`. It does not authorize opening a migrated ledger
with the older schema after successors exist; retain the failed release and
migrated ledger for audit and restore the pre-release ledger copy only if no
post-release run data must be preserved.
