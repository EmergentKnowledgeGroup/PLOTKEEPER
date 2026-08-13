# Codex integration

This integration makes the complete Plotkeeper workflow locally installable.
All required skill code is carried in this repository.

## Install

From the repository root, run:

```powershell
.\integrations\codex\install.ps1
```

The installer:

1. installs the EKG-owned `specswarm`, `production-goal-contract`,
   `production-goal-review`, and `adaptive-execution` skills;
2. installs the vendored Slopware `msw` and `timebox` skills;
3. merges the vendored MSW `SessionStart` hook and Plotkeeper's
   `UserPromptSubmit` and `Stop` hooks into
   `%USERPROFILE%\.codex\hooks.json` without removing unrelated hooks.
4. writes a portable Plotkeeper location record used by SpecSwarm;
5. installs the managed `plotkeeper-guard` plugin, whose `PreToolUse` hook
   blocks push, merge, deployment, publication, and repository-metadata
   commands until an independent `DEPLOY_READY PASS` receipt matches the
   active contract and exact Git `HEAD`.

It deliberately does **not** alter Codex hook trust. In Codex, run `/hooks`,
inspect the four effective hooks, and trust them:

- `SessionStart` — supplied by upstream `msw-hook`;
- `UserPromptSubmit` — starts or routes the turn receipt;
- `Stop` — refuses silent closeout while the receipt is missing or open;
- `PreToolUse` — blocks unreviewed production release side effects.

Codex does not automatically trust plugin-bundled hooks. It binds trust to the
reviewed hook content. If a hook changes, review and trust
the new version again. That is a safety boundary, not an installation defect.

To make the policy available in every repository, merge
[`AGENTS.snippet.md`](AGENTS.snippet.md) into your user-level Codex instructions.
The hooks still enforce the loop when an agent overlooks the prose policy.

SpecSwarm resolves the current connector through Plotkeeper's CLI instead of
assuming a fixed port, so the sidebar and run-bound dashboard URLs use the same
persisted loopback origin.

## Timing behavior

The first task of a kind is an untimed calibration. Its measured result enters
the local execution ledger. Later tasks use a timebox only when a sufficiently
comparable completed record exists. No duration is invented, and Timebox never
reduces the acceptance criteria selected by MSW.

## Ownership and trust

SpecSwarm and the production governance skills are EKG-owned Apache-2.0
material. The bundled Slopware packages retain their original CC BY 4.0
license and attribution; they are not relicensed as Plotkeeper code. See
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

The exact bundled component inventory and platform requirements are recorded in
[`bundled/dependencies.json`](bundled/dependencies.json). Codex, Python, Git,
native subagent/tool support, and Sol model access are platform requirements;
they are not redistributable skill dependencies.

Official hook behavior and trust details are documented in the
[Codex hooks guide](https://learn.chatgpt.com/docs/hooks).
