# Security

Plotkeeper reads local Codex session logs, which may contain confidential code,
paths, prompts, or evidence links. Its intended deployment boundary is one
trusted Windows user on loopback.

Report security issues privately to the repository owner rather than placing
sensitive reproduction data in a public issue. A future public repository
should add a project-specific private contact method before accepting reports.

Do not attach real session JSONL, runtime SQLite files, secrets, or personal
datasets to bug reports. Use the self-contained demo to reproduce dashboard
issues whenever possible.
