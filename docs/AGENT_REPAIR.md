# Agent runbook: diagnose and repair one Plotkeeper installation

Do not launch a second watcher to diagnose the first. Plotkeeper is an independent
background service: closing Codex/LP does not stop it. Do not infer that it caused
a system crash from that fact, and do not kill every Python/Codex/Docker process.

## Identify the code before running service commands

Replace `<checkout>` with the intended installation directory. Run the installed
interpreter in isolated import mode, even if your current directory is the repo:

```powershell
& '<checkout>/.venv/Scripts/python.exe' -I -m plotkeeper.cli doctor --source-root '<checkout>'
```

`doctor` is read-only: no connector creation, ledger opening, session scan,
backend launch, startup change, credentials or transcript contents. It reports
the interpreter, active package, distribution package/version and mismatched
package filenames. Exit 0 means parity; exit 2 means repair is needed. It checks
package Python and web assets, not private runtime data or every global Python.

`scripts/start.ps1` and `scripts/pk.ps1` require this check too. They use
`python -I -m plotkeeper.cli`, so source cwd/PYTHONPATH cannot quietly select
different code. For development source imports are allowed, but are not the
installed service identity. Reinstall after editing source before using the
supported service launchers.

## Known old-copy locations and safe cleanup

1. `<checkout>/plotkeeper`: editable source; **do not delete**. Preserve dirty
   changes. Compare them with the intended public commit before upgrading.
2. `<checkout>/.venv/Lib/site-packages/plotkeeper` and its `plotkeeper-*.dist-info`:
   installed package. `scripts/install.ps1` force-reinstalls only this checkout's
   private environment and checks all package files before stopping a listener.
   Do not use the global `pip`, manually mix package files, or remove other
   distributions just because they mention Codex.
3. `<checkout>/build` and `plotkeeper.egg-info`: generated build copies, **not
   runtime authority**. Direct install builds from a clean staging copy, so old
   `build/lib/plotkeeper` modules cannot get repackaged accidentally.
4. Prior installer payloads, extra checkouts and old virtual environments are
   rollback/source copies, not automatically safe to delete. First establish
   their owner, startup target and dirty Git state. Never recursively delete
   another checkout or a directory containing unapplied work.

For ordinary parity repair:

```powershell
& '<checkout>/scripts/install.ps1'
& '<checkout>/.venv/Scripts/python.exe' -I -m plotkeeper.cli doctor --source-root '<checkout>'
```

An unrecorded orphan module can survive pip's RECORD-managed uninstall. If doctor
still reports extra files, prefer the packaged upgrade: it moves the old private
`.venv` into an access-restricted backup and creates a fresh one. Nothing in the
old environment is permanently deleted. Do not remove a busy environment by hand.

## Upgrade / rollback

The source+wheel bundle is made with `scripts/build-installer.py`. Run its
`Install-Plotkeeper.ps1 -TargetRoot '<checkout>'` or the supplied double-click
launcher. Select **1** to install. Payload and wheel hashes are checked first;
only the exact owned listener is stopped, source files being overwritten are
backed up, and the old `.venv` is moved into that private backup. Unknown source
files, `.git`, ledger, connector, credentials, browser profile and transcripts
are not deleted or overwritten. A failed install attempts source/environment
restoration and leaves the service stopped; keep the printed backup path. The
target-bound `runtime/plotkeeper-install.json` marker is retained so an interrupted
fresh installation can be repaired in place. Preserve it with the runtime.

Select **2** and supply that backup path to restore the previous source and
environment. Runtime data is deliberately **not** rolled back: this preserves
new writes and avoids restoring stale SQLite/WAL state. This release adds no
destructive data migration. For an older release with incompatible schema,
do not open the current ledger with old code without a separate data plan.
Restart explicitly with the restored `scripts/start.ps1` after inspecting it.
Rollback restores/removes the exact sign-in value saved before upgrade, but
refuses to overwrite a foreign replacement. Reapplying a successfully restored
backup is a no-op; it cannot move the restored environment out a second time.

The installer never opens/closes LP. Normal install registers the same owned
checkout for Windows sign-in. `-NoStartup` skips registry access; ordinary service
tests use it and an empty `-Sessions` directory. Startup rollback tests use only a
disposable test registry key, never the actual Windows sign-in key. A command belonging to another
checkout or foreign listener must be reconciled explicitly, not overwritten.

To stop this checkout without changing packages or startup:

```powershell
& '<checkout>/scripts/install.ps1' -StopOnly
```

Ownership requires the persisted listener identity: PID, process creation instant,
executable, command-line hash, root, connector and loopback port. A foreign,
unverifiable or reused PID is a stop condition. Do not delete the owner record
to force a takeover. `scripts/uninstall.ps1` historically removes sign-in
registration, not the watcher; do not mistake it for a process shutdown tool.

## Scanning and reviewer diagnostics

Quiet scans still enumerate/stat the session tree for portable discovery; they
do not reopen unchanged transcripts, re-read their heads, or repeatedly query
watermarks. Changed files stream complete JSONL lines. An unfinished final line
is not committed; ordinary appends resume at the exact complete-line watermark.
Memory scales with a JSON record and the observations actually extracted, not
the whole unread byte tail. This is not a general-purpose bounded JSON parser.
Truncation/replacement/head rewrites reset scanning; a same-size timestamp change
also rescans. Files edited while preserving all stat metadata or arbitrary
in-place growth with an unchanged head are outside the append-only transcript
contract. The title index is stat-cached and streamed on change.

Review transport stdout/stderr are discarded, not buffered or spooled. Review
authority still comes from verified receipt markers in Codex session history.
The ledger/UI records exit status and privacy-safe diagnostic codes (not prompts
or arbitrary exception text). A failure latches: automatic polls cannot create
a new reviewer. The existing **Retry review** action is explicit. Unknown child
identity is not permission to retry an orphan. One root's review and plan
reconstruction share the persistent single-flight launch guard.

Optional LocalTools lazy-MCP proxies remain process-scoped. Set
`PLOTKEEPER_LAZY_MCP_ROOT` to an installed, catalog-pinned proxy directory when
needed. The legacy `Z:/codexlp-lazy-mcp` directory is recognized if present;
public users without it keep their normal Codex tool configuration. An explicitly
selected but invalid proxy fails closed, without exposing secrets.

When reporting a bug include doctor JSON, intended commit, exact error/exit code,
owned startup/launcher path and a synthetic reproduction. Do not attach real
ledger, connector, API keys or full session transcripts. Separate observed
resource measurements from hypotheses about a crash.
