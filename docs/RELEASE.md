# Release and rollback

## First public release

The first public release target is `EmergentKnowledgeGroup/PLOTKEEPER`, with
local `main` pushed as the GitHub default branch only after an exact-SHA
independent `DEPLOY_READY` review passes.

Pre-push checks:

```powershell
git status --short --branch
git diff a0d23403f9b3d0cab13e8f3ea0a695bc17826018..HEAD --check
py -3 -m unittest discover -s tests -v
```

## Rollback

The protected enforcement baseline for this release is
`a0d23403f9b3d0cab13e8f3ea0a695bc17826018`. If the dependency-bundle release is
defective, preserve the failed release commit for audit and
restore the public branch to that baseline with a lease-bound update:

```powershell
git fetch origin main
git push --force-with-lease=refs/heads/main:<REMOTE_FAILED_SHA> origin `
  a0d23403f9b3d0cab13e8f3ea0a695bc17826018:refs/heads/main
```

Replace `<REMOTE_FAILED_SHA>` with the SHA independently read from GitHub. Do
not use an unqualified force push. Then verify that GitHub's default branch
resolves to the baseline and record a new live attestation. This rollback
removes only the dependency-bundle correction from the public branch; it does
not delete the hardened public release, repository, or audit history.
