# Ledger Schema

The helper owns `data/adaptive_execution.sqlite3`. Do not edit it manually.

Core execution fields include turn/session identity, normalized workspace and project identity, prompt hash, outcome summary, task type, risk, systems, validation, route, comparison IDs and scores, derived AWT/CGP, start/convergence/end timestamps, wall/substantive/closeout/blocked seconds, status, outcome, proof, open items, and variance.

The `turn_gate` table records whether `UserPromptSubmit` classified a turn as governed. The `executions` table is keyed by `turn_id`, preventing receipt reuse across turns. The `Stop` hook permits completion only when a governed turn has a closed, internally valid execution row.

The database uses SQLite transactions and WAL mode so concurrent Codex tasks do not interleave JSONL appends or corrupt the ledger.
