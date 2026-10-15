# 0.1.13 qualification scope

This release addresses three observed helper defects, not a diagnosis of a host
crash. Development and install tests use an isolated source copy, synthetic
sessions/ledgers and startup-disabled Windows installs. No LP launch is required.

| Requirement | Pre-fix evidence | Smallest correction | Regression proof |
| --- | --- | --- | --- |
| Stop needless transcript rereads | Quiet scans opened every transcript and queried its watermark; changed backlog used `read()` + decode + split | Stat-cache quiet files; stream complete lines; stat-first title cache | `test_scanner_resources.py`: quiet, append, partial UTF-8, truncation, replacement, head rewrite, backlog iterator and index refresh |
| Stop unused reviewer-output accumulation | `communicate()` retained stdout/stderr although service only consumed exit status | OS null-device streams + wait/reap; no spool or new output cap | `test_launch_resources.py`: real child emits both streams beyond pipe capacity, callback failure reaps child |
| Reconcile source/installed copies | Supported launch paths could import from cwd while console used stale site-packages | Installed-only `-I` launchers, read-only doctor, forced clean-stage/wheel install | `test_repository_docs.py`: deliberate drift rejected, repeated install repairs, removed build module not repackaged, console/outside-cwd identity |
| Preserve existing one-worker controls | Deployed local guards/UI were not in public main | Include the owner-authorized deployed baseline; preserve explicit retry and receipt authority | Cross-connection launch claim, retry latch, noninterference tests; synthetic desktop/mobile Retry UI |
| Safe repeat upgrade / rollback | Old environments could retain unrecorded extra modules | Hash-checked source+wheel bundle; move private env to restricted backup, preserve unknown source/runtime | `test_upgrade_bundle.py`: fresh/repeat/orphan cleanup, rollback, private sentinel/connector/unrelated-work preservation and tamper rejection |

Tests use the existing Windows listener identity proof (PID, executable, creation
instant, command hash, root/connector/port), not process-name or HTML ownership.
The prior unsafe installer test that touched real sign-in registration now uses
`-NoStartup`, an empty session root and a disposable checkout. Foreign listener
regressions remain required. No release guard or verifier has been weakened.

The only UI diff is the already-deployed launch-status/Retry-review strip,
explicitly included by the owner. Synthetic browser QA at 1440×1000 and 390×844
shows readable controls without horizontal overflow. Retry receives a deliberately
mocked reviewer exit 23/HTTP409 and restores its error/retry state; no real agent
is launched. The only console error in that interaction is the expected 409,
not a JavaScript exception.

Boundaries: quiet tree discovery still enumerates/stats; a single huge JSONL
record and actual extracted evidence can still consume memory; metadata-preserving
rewrites are not an append-only transcript guarantee. See `AGENT_REPAIR.md`.
Installer qualification is not live user-installation attestation. Public merge
requires actual CodeRabbit/CI disposition and the enforced signed release chain.
