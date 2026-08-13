# Architecture and trust boundaries

```text
Codex session JSONL (read-only)
          |
          v
 SessionScanner -- byte watermarks --> PlotkeeperService
                                         |       |
                                         v       v
                                   SQLite ledger  review/check-in injection
                                         |
                                         v
                                  local HTTP dashboard
```

## Components

- `plotkeeper/sessions.py` parses complete JSONL lines and tolerates partial or
  malformed trailing writes.
- `plotkeeper/ledger.py` stores derived runs, watermarks, task snapshots,
  reports, child links, and review receipts in SQLite.
- `plotkeeper/service.py` applies enrollment and closure rules and exposes the
  local HTTP API.
- `plotkeeper/web/` is a dependency-free dashboard packaged with the Python
  distribution.
- `scripts/` contains Windows current-user installation and convenience entry
  points.

## Source of truth

Session JSONL remains Codex-owned input. Plotkeeper stores observations and
agent-reported claims; neither is automatically equivalent to verified truth.
Goal contracts are displayed, not authorized, by Plotkeeper. Git, tests,
review receipts, and live attestations remain the relevant proof authorities.

## State machine

```text
OPEN -> REVIEW_REQUIRED -> REVIEW_PENDING -> REVIEWED -> CLOSED
```

The transition to `REVIEWED` requires a terminal, injected receipt with
`verdict=PASS` and `open_items=0`. `CLOSED` runs do not absorb later child work.

## Local security boundary

The server binds only to `127.0.0.1` using one persisted high private connector
chosen during installation. A fixed port is never silently taken over; owned-
listener checks remain the safety boundary. There is no authentication or TLS
layer. Session contents may contain sensitive project context, so do not expose
the dashboard to another interface without adding an appropriate access layer.
### Codex identity and fallback task

`ThreadCatalog` reads both `state_5.sqlite` and `session_index.jsonl` without writing either. The session index's explicit `thread_name` is authoritative for display; the database prompt fields are compatibility fallbacks. Persisted Plotkeeper tasks remain authoritative for the execution board. Only when that list is empty does the API synthesize one clearly sourced `codex:thread-title` row.

External pop-out uses a dedicated machine-local Chromium profile and app-window arguments. Same-origin validation remains at the HTTP boundary before any process is launched.
