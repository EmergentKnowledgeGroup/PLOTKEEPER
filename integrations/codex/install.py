"""Install Plotkeeper's complete Codex skill bundle without network fetches."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

BUNDLED_SKILLS = (
    ("adaptive-execution", "adaptive-execution"),
    ("bundled/skills/specswarm", "specswarm"),
    ("bundled/skills/production-goal-contract", "production-goal-contract"),
    ("bundled/skills/production-goal-review", "production-goal-review"),
    ("bundled/upstream/slopware/msw/skills/msw", "msw"),
    ("bundled/upstream/slopware/timebox/skills/timebox", "timebox"),
)


def load_connector(repo_root: Path) -> dict:
    connector_path = repo_root / "runtime" / "plotkeeper-connector.json"
    try:
        connector = json.loads(connector_path.read_text(encoding="utf-8"))
        if not isinstance(connector, dict):
            raise ValueError("connector must be an object")
        port = int(connector.get("port", 0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Plotkeeper connector: {connector_path}") from exc
    if connector.get("host") != "127.0.0.1" or not 1 <= port <= 65535:
        raise ValueError(f"invalid Plotkeeper connector: {connector_path}")
    return {**connector, "url": f"http://127.0.0.1:{port}", "path": str(connector_path)}


def hook_command(codex_home: Path) -> str:
    script = codex_home / "skills" / "adaptive-execution" / "scripts" / "adaptive_execution.py"
    return f'py -3 "{script}" hook'


def required_hooks(codex_home: Path) -> dict[str, list[dict]]:
    command = hook_command(codex_home)
    return {
        "UserPromptSubmit": [{"hooks": [{
            "type": "command", "command": command, "timeout": 10,
            "statusMessage": "Routing adaptive execution", "additionalContextLimit": 1200,
        }]}],
        "Stop": [{"hooks": [{
            "type": "command", "command": command, "timeout": 10,
            "statusMessage": "Validating execution receipt",
        }]}],
    }


def merge_hooks(document: dict, codex_home: Path) -> dict:
    hooks = document.setdefault("hooks", {})
    wanted = required_hooks(codex_home)
    command = hook_command(codex_home)
    for event, entries in wanted.items():
        current = hooks.setdefault(event, [])
        already_present = any(
            hook.get("command") == command
            for group in current if isinstance(group, dict)
            for hook in group.get("hooks", []) if isinstance(hook, dict)
        )
        if not already_present:
            current.extend(entries)
    upstream_path = Path(__file__).resolve().parent / "bundled" / "upstream" / "slopware" / "msw-hook" / "hooks" / "hooks.json"
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))["hooks"]
    for event, entries in upstream.items():
        current = hooks.setdefault(event, [])
        existing_commands = {
            hook.get("command") for group in current if isinstance(group, dict)
            for hook in group.get("hooks", []) if isinstance(hook, dict)
        }
        for group in entries:
            commands = {hook.get("command") for hook in group.get("hooks", []) if isinstance(hook, dict)}
            if not commands.issubset(existing_commands):
                current.append(group)
                existing_commands.update(commands)
    return document


def install_bundled_skills(codex_home: Path) -> None:
    integration_root = Path(__file__).resolve().parent
    skills_root = codex_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    for relative_source, name in BUNDLED_SKILLS:
        source = integration_root / relative_source
        if not (source / "SKILL.md").is_file():
            raise FileNotFoundError(f"incomplete bundled skill: {source}")
        destination = skills_root / name
        # Overlay distributed files and preserve local runtime data such as
        # adaptive-execution calibration history.
        shutil.copytree(source, destination, dirs_exist_ok=True)


def install_guard_plugin() -> None:
    marketplace_root = Path(__file__).resolve().parent
    subprocess.run(("codex", "plugin", "marketplace", "add", str(marketplace_root)), check=True)
    subprocess.run(("codex", "plugin", "add", "plotkeeper-guard@plotkeeper"), check=True)


def install(codex_home: Path, *, skip_plugins: bool = False) -> Path:
    install_bundled_skills(codex_home)

    config_path = codex_home / "plotkeeper.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    repo_root = Path(__file__).resolve().parents[2]
    connector = load_connector(repo_root)
    config["repo_root"] = str(repo_root)
    config["connector_path"] = connector["path"]
    config["dashboard_url"] = connector["url"]
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    hooks_path = codex_home / "hooks.json"
    document = json.loads(hooks_path.read_text(encoding="utf-8")) if hooks_path.exists() else {}
    merge_hooks(document, codex_home)
    hooks_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    if not skip_plugins:
        install_guard_plugin()
    return hooks_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--skip-plugins", action="store_true", help="Skip only the managed guard plugin; bundled skills and hooks are always installed")
    args = parser.parse_args()
    hooks_path = install(args.codex_home.resolve(), skip_plugins=args.skip_plugins)
    print(f"Installed Plotkeeper Codex integration. Review and trust hooks with /hooks: {hooks_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
