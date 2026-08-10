"""Install Plotkeeper's Codex integration without modifying hook trust state."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

SLOPWARE_COMMANDS = (
    ("codex", "plugin", "marketplace", "add", "transcendr/slopware-skills"),
    ("codex", "plugin", "add", "msw@slopware-skills"),
    ("codex", "plugin", "add", "msw-hook@slopware-skills"),
    ("codex", "plugin", "add", "timebox@slopware-skills"),
)


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
    return document


def install_plugins() -> None:
    for command in SLOPWARE_COMMANDS:
        subprocess.run(command, check=True)


def install(codex_home: Path, *, skip_plugins: bool = False) -> Path:
    source = Path(__file__).resolve().parent / "adaptive-execution"
    destination = codex_home / "skills" / "adaptive-execution"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Overlay only the distributed files. In particular, preserve the local
    # data/adaptive_execution.sqlite3 calibration history across upgrades.
    shutil.copytree(source, destination, dirs_exist_ok=True)

    hooks_path = codex_home / "hooks.json"
    document = json.loads(hooks_path.read_text(encoding="utf-8")) if hooks_path.exists() else {}
    merge_hooks(document, codex_home)
    hooks_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    if not skip_plugins:
        install_plugins()
    return hooks_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--skip-plugins", action="store_true", help="Install only Plotkeeper-owned files and hooks")
    args = parser.parse_args()
    hooks_path = install(args.codex_home.resolve(), skip_plugins=args.skip_plugins)
    print(f"Installed Plotkeeper Codex integration. Review and trust hooks with /hooks: {hooks_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
