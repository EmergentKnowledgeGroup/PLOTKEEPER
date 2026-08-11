"""Portable bridge from the installed SpecSwarm skill to Plotkeeper's CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    codex_home = Path(__file__).resolve().parents[3]
    config_path = codex_home / "plotkeeper.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        script = Path(config["repo_root"]) / "scripts" / "pk.ps1"
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"PLOTKEEPER_UNAVAILABLE: invalid {config_path}: {exc}", file=sys.stderr)
        return 2
    if not script.is_file():
        print(f"PLOTKEEPER_UNAVAILABLE: missing {script}", file=sys.stderr)
        return 2
    return subprocess.run([
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script), *sys.argv[1:],
    ], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
