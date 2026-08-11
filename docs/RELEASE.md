# Release and rollback

## Panel reliability patch

This release is `0.1.1`. Before declaring the local dashboard ready, verify
that `/health` is healthy and `/` returns HTTP 200 with a non-empty HTML body
containing `<html` and the exact `data-testid="plotkeeper-app"` marker. The installer/startup scripts replace a
listener only when its process is Plotkeeper-owned; a foreign process on the
configured port is a hard stop.

## First public release

The first public release target is `EmergentKnowledgeGroup/PLOTKEEPER`, with
local `main` pushed as the GitHub default branch only after an exact-SHA
independent `DEPLOY_READY` review passes.

Pre-push checks:

```powershell
git status --short --branch
git diff 5c33658fe08ff73d661ca40c9e3c96194748a9f2..HEAD --check
py -3 -m unittest discover -s tests -v
```

## Rollback

The protected enforcement baseline for this release is
`5c33658fe08ff73d661ca40c9e3c96194748a9f2`. If the panel-reliability release is
defective, preserve the failed release commit for audit and
restore the public branch to that baseline with a lease-bound update:

```powershell
git fetch origin main
git push --force-with-lease=refs/heads/main:<REMOTE_FAILED_SHA> origin `
  5c33658fe08ff73d661ca40c9e3c96194748a9f2:refs/heads/main
```

Replace `<REMOTE_FAILED_SHA>` with the SHA independently read from GitHub. Do
not use an unqualified force push. Then verify that GitHub's default branch
resolves to the baseline and record a new live attestation. This rollback
removes only the panel-reliability patch from the public branch; it does not
delete the hardened dependency-bundle release, repository, or audit history.
