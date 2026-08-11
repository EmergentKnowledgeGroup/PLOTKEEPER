# Changelog

## 0.1.1 - 2026-08-11

- Keep dashboard HTTP failures non-empty and diagnosable instead of dropping
  clients on an empty socket.
- Make installer/startup replacement fail closed for foreign listeners and wait
  for valid dashboard HTML before reporting readiness.
- Require valid dashboard HTML before the `PK:PANEL_OPENED` receipt and
  prevent ordinary message IDs from being mistaken for new root sessions.
- Reuse stable canonical task identities across legitimate session/worktree
  variants while retaining their child history.
