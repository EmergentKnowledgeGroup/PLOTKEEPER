"""Read-only runtime identity checks. Never open a ledger or session root."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys


def _files(root: Path) -> dict[str, str]:
    """Only package code/assets, never runtime or credentials."""
    return {str(path.relative_to(root)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file() and (path.suffix == ".py" or
                                  (path.parent.name == "web" and path.suffix in {".html", ".css", ".js"}))}


def diagnose(source_root: Path | None = None) -> dict:
    from . import __version__
    active = Path(__file__).resolve().parent
    try:
        distribution = importlib.metadata.distribution("plotkeeper")
        installed = Path(distribution.locate_file("plotkeeper")).resolve()
        installed_version = distribution.version
    except importlib.metadata.PackageNotFoundError:
        installed, installed_version = None, None
    source = source_root.resolve() / "plotkeeper" if source_root else None
    issues: list[str] = []
    differences: list[str] = []
    if installed is None:
        issues.append("package_not_installed")
    elif installed != active:
        issues.append("source_shadows_installed_package")
    if installed_version != __version__:
        issues.append("package_version_mismatch")
    if source is not None:
        if not source.is_dir():
            issues.append("source_package_missing")
        else:
            expected, actual = _files(source), _files(active)
            differences = sorted(key for key in expected.keys() | actual.keys()
                                 if expected.get(key) != actual.get(key))
            if differences:
                issues.append("package_content_mismatch")
    return {
        "ok": not issues, "version": __version__, "installed_version": installed_version,
        "interpreter": sys.executable, "active_package": str(active),
        "installed_package": str(installed) if installed else None,
        "source_package": str(source) if source else None,
        "issues": issues, "different_files": differences,
        "repair": "Run scripts/install.ps1 from the intended checkout, then rerun doctor. "
                  "It force-reinstalls only that checkout's .venv package. Do not delete runtime, "
                  "user transcripts, global packages, other checkouts or startup entries by name. "
                  "See docs/AGENT_REPAIR.md for identity and legacy cleanup.",
    }


def main(source_root: str | None = None) -> int:
    try:
        result = diagnose(Path(source_root) if source_root else None)
    except OSError as exc:
        result = {"ok": False, "issues": ["package_unreadable"], "error_type": type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2
