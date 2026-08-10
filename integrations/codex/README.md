# Codex integration

This integration makes evidence-calibrated execution automatic. It combines
three upstream Slopware packages with Plotkeeper's adaptive routing skill and
two lifecycle hooks.

## Install

From the repository root, run:

```powershell
.\integrations\codex\install.ps1
```

The installer:

1. adds the `transcendr/slopware-skills` marketplace;
2. installs `msw`, `msw-hook`, and `timebox` from that marketplace;
3. installs the bundled Plotkeeper `adaptive-execution` skill;
4. merges Plotkeeper's `UserPromptSubmit` and `Stop` hooks into
   `%USERPROFILE%\.codex\hooks.json` without removing unrelated hooks.
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

## Timing behavior

The first task of a kind is an untimed calibration. Its measured result enters
the local execution ledger. Later tasks use a timebox only when a sufficiently
comparable completed record exists. No duration is invented, and Timebox never
reduces the acceptance criteria selected by MSW.

## Ownership and trust

The Slopware packages are installed from their original marketplace and retain
their CC BY 4.0 license. Plotkeeper does not vendor or relicense them. The
adaptive skill and its hooks are Plotkeeper-owned Apache-2.0 material. See
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

Official hook behavior and trust details are documented in the
[Codex hooks guide](https://learn.chatgpt.com/docs/hooks).
