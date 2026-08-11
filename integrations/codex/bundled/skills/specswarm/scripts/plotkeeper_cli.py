"""Portable bridge from the installed SpecSwarm skill to Plotkeeper's CLI."""

from __future__ import annotations

import json
import os
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
    args = list(sys.argv[1:])
    # Codex exposes the current task identity through one of these environment
    # variables on installed surfaces. Bind ``current`` to it when available;
    # callers may still pass an explicit --run-id/--session-id, which wins.
    if args and args[0] == "current" and "--run-id" not in args and "--session-id" not in args:
        session_id = os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
        if session_id:
            args[1:1] = ["--session-id", session_id]
    return subprocess.run([
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(script), *args,
    ], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
