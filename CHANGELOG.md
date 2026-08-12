# Changelog

## 0.1.4 - 2026-08-12

- Preserve every closed run as immutable history and create a linked successor
  when later SpecSwarm work begins in the same Codex task.
- Enforce one active run per canonical task while keeping predecessor and
  successor IDs available for exact historical navigation.
- Migrate existing SQLite ledgers without losing runs, reports, children,
  tasks, contracts, watermarks, timestamps, or foreign-key integrity.
- Restore SpecSwarm's gate to exact active-run enrollment without the mistaken
  one-run-per-task restriction or any fallback to project-directory matching.
- Exclude incomplete and unproven execution receipts from adaptive timing
  comparisons so a blocked preflight cannot create an absurd implementation
  deadline.
- Include the previously validated owned-listener restart and project-drive
  installer-cache fixes from the unreleased 0.1.3 candidate.

## 0.1.3 - 2026-08-11

- Restart an existing Plotkeeper-owned listener after every package upgrade so
  the live process cannot keep serving stale imported modules.
- Reject foreign listeners even when they return Plotkeeper-shaped healthy HTML.
- Keep installer build temporaries inside the project runtime and remove them
  after installation.

## 0.1.2 - 2026-08-11

- Bind dashboard and CLI lookup to an exact run or Codex root/session identity;
  ambiguous and unavailable locators now fail closed.
- Keep closed and legacy `msg_` history out of the interactive picker, using
  read-only Codex thread titles and transcript terminal state for live labels.
- Group the responsive run selector by project and open run-bound dashboard
  URLs from the bundled SpecSwarm bridge.

## 0.1.1 - 2026-08-11

- Keep dashboard HTTP failures non-empty and diagnosable instead of dropping
  clients on an empty socket.
- Make installer/startup replacement fail closed for foreign listeners and wait
  for valid dashboard HTML before reporting readiness.
- Require valid dashboard HTML before the `PK:PANEL_OPENED` receipt and
  prevent ordinary message IDs from being mistaken for new root sessions.
- Reuse stable canonical task identities across legitimate session/worktree
  variants while retaining their child history.
