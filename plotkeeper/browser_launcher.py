from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Callable, Iterable


def chromium_candidates() -> Iterable[Path]:
    seen: set[str] = set()
    for name in ("msedge.exe", "chrome.exe"):
        found = shutil.which(name)
        if found:
            path = Path(found)
            key = os.path.normcase(str(path))
            if key not in seen:
                seen.add(key)
                yield path
    roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
    relatives = [
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Google/Chrome/Application/chrome.exe"),
    ]
    for root in filter(None, roots):
        for relative in relatives:
            path = Path(str(root)) / relative
            key = os.path.normcase(str(path))
            if path.is_file() and key not in seen:
                seen.add(key)
                yield path


class IsolatedBrowserLauncher:
    """Open Plotkeeper as a standalone Chromium app with its own profile."""

    def __init__(self, profile_dir: str | os.PathLike[str], *,
                 candidates: Callable[[], Iterable[Path]] = chromium_candidates,
                 process_launcher: Callable[..., object] = subprocess.Popen,
                 fallback: Callable[..., bool] = webbrowser.open):
        self.profile_dir = Path(profile_dir)
        self._candidates = candidates
        self._process_launcher = process_launcher
        self._fallback = fallback

    def __call__(self, url: str, *, new: int = 1) -> bool:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        for executable in self._candidates():
            try:
                self._process_launcher(
                    [str(executable), f"--app={url}", "--new-window", "--no-first-run",
                     "--no-default-browser-check", f"--user-data-dir={self.profile_dir}"],
                    cwd=str(self.profile_dir.parent),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    close_fds=True,
                )
                return True
            except OSError:
                continue
        return bool(self._fallback(url, new=new))
