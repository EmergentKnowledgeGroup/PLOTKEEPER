# Release and rollback

## First public release

The first public release target is `EmergentKnowledgeGroup/PLOTKEEPER`, with
local `main` pushed as the GitHub default branch only after an exact-SHA
independent `DEPLOY_READY` review passes.

Pre-push checks:

```powershell
git status --short --branch
git diff b36c6f3d0ffed1f5e919e49668e79cf8fe2adb7a..HEAD --check
py -3 -m unittest discover -s tests -v
```

## Rollback

The protected functional baseline for this release is
`b36c6f3d0ffed1f5e919e49668e79cf8fe2adb7a`. If the new Codex integration or
public release is defective, preserve the failed release commit for audit and
restore the public branch to that baseline with a lease-bound update:

```powershell
git fetch origin main
git push --force-with-lease=refs/heads/main:<REMOTE_FAILED_SHA> origin `
  b36c6f3d0ffed1f5e919e49668e79cf8fe2adb7a:refs/heads/main
```

Replace `<REMOTE_FAILED_SHA>` with the SHA independently read from GitHub. Do
not use an unqualified force push. Then verify that GitHub's default branch
resolves to the baseline and record a new live attestation. This rollback
removes the integration release from the public branch; it does not delete the
repository or its audit history.
