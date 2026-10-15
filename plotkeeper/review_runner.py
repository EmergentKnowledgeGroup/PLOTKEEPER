"""Per-process MCP transport overrides for fresh Plotkeeper CLI reviewers.

Only the two known eager transports are replaced. The installed proxy answers
discovery from its pinned catalog and starts its backend on an operational call.
This module never edits Codex configuration or changes review authority.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


LAZY_MCP_ROOT = Path("Z:/codexlp-lazy-mcp")
SCOPED_SERVERS = ("playwright", "MCP_DOCKER")


class ReviewToolsUnavailable(RuntimeError):
    """Installed scoped tools need installation or explicit catalog recapture."""


def _digest(value: Any) -> str:
    # Same canonical bytes as the installed lazy_mcp catalog format.
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _verify_runtime(root: Path) -> None:
    """Read-only preflight; never import/execute the proxy or a backend."""
    try:
        if not (root / "lazy_mcp.py").is_file():
            raise ValueError("missing proxy")
        for server in SCOPED_SERVERS:
            config = json.loads((root / f"{server}.json").read_text(encoding="utf-8-sig"))
            catalog = json.loads((root / f"{server}-catalog.json").read_text(encoding="utf-8-sig"))
            if (catalog.get("schema") != "codex.lazy-mcp.catalog.v1"
                    or catalog.get("configSha256") != _digest(config)
                    or catalog.get("catalogSha256") != _digest(catalog["discovery"])):
                raise ValueError("catalog mismatch")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Do not expose configuration values, backend arguments or credentials.
        raise ReviewToolsUnavailable(
            "Scoped review tools are unavailable; install the local-tools bundle "
            "or recapture its catalogs, then explicitly retry the review."
        ) from None


def scoped_review_args(args: list[str], *, lazy_root: Path | None = None) -> list[str]:
    """Return a fresh exec argv with scoped stdio overrides, without spawning.

    The caller still owns model/effort, cwd, hooks, permissions, enabled state,
    tool allowlists and timeout policy. No user or project config is rewritten.
    Reconstruction's asynchronous launcher should call this same builder.
    """
    if len(args) < 2 or args[1] != "exec":
        raise ValueError("Scoped reviewer requires a fresh Codex exec command")
    configured = os.environ.get("PLOTKEEPER_LAZY_MCP_ROOT")
    root = Path(lazy_root or configured or LAZY_MCP_ROOT)
    # Public installs need not have this workstation's optional LocalTools
    # proxy. An explicitly configured proxy must still pass the pinned check.
    if lazy_root is None and not configured and not root.exists():
        return list(args)
    _verify_runtime(root)
    overrides: list[str] = []
    for server in SCOPED_SERVERS:
        values = {
            "command": sys.executable,
            "args": ["-B", str(root / "lazy_mcp.py"), "--config", str(root / f"{server}.json"),
                     "--catalog", str(root / f"{server}-catalog.json")],
        }
        for field, value in values.items():
            # JSON strings/arrays of strings use TOML-compatible escaping here;
            # argv is passed directly, never through PowerShell or cmd quoting.
            overrides.extend(["-c", f"mcp_servers.{server}.{field}="
                              + json.dumps(value, ensure_ascii=False)])
    return [*args[:2], *overrides, *args[2:]]


def run_review(args: list[str], *, cwd: str,
               on_started: Callable[[Any], None] | None = None) -> subprocess.CompletedProcess:
    """Wait for one reviewer without capturing its unused transport transcript.

    Review authority arrives through session receipt markers, not stdout. Both
    streams go to the OS null device: no pipe deadlock, RAM accumulation or
    unbounded disk spool. The service records exit status and a diagnostic code.
    """
    scoped_args = scoped_review_args(args)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with subprocess.Popen(scoped_args, cwd=cwd, stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          creationflags=flags) as process:
        try:
            if on_started is not None:
                on_started(process)
            process.wait()
        except BaseException:
            # The callback can fail after the child started. Reap only that
            # owned Popen child; proxy parent-watch handles its owned backends.
            try:
                if process.poll() is None:
                    process.kill()
                process.wait()
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            raise
        return subprocess.CompletedProcess(scoped_args, process.returncode)
