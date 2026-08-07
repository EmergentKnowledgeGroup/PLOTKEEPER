from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .models import SessionObservation

SPEC_RE = re.compile(r"(?:\$specswarm\b|\brun\s+specswarm\b)", re.IGNORECASE)
CLAIM_RE = re.compile(r"(?:claim|report)\s*[:=]\s*(.+)", re.IGNORECASE)
EVIDENCE_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
GOAL_COMPLETE_RE = re.compile(r"(?:PK:GOAL_COMPLETE_REQUEST|\bgoal\s+(?:is\s+)?complete\b)", re.IGNORECASE)
REVIEW_RESULT_RE = re.compile(r"PK:REVIEW_RESULT\s+run_id=(\S+)\s+verdict=(PASS|PARTIAL|FAIL|BLOCKED)\s+open_items=(\d+)", re.IGNORECASE)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(_text(v) for v in value.values())
    return ""


def _payload(obj: dict[str, Any]) -> dict[str, Any]:
    payload = obj.get("payload")
    return payload if isinstance(payload, dict) else {}


def _meta(obj: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    p = _payload(obj)
    sid = p.get("id") or p.get("session_id") or obj.get("session_id")
    parent = (p.get("parent_session_id") or p.get("parent_id") or
              p.get("parent_thread_id") or p.get("parentThreadId"))
    return str(sid) if sid else None, str(parent) if parent else None, p.get("cwd")


def _is_user_specswarm(obj: dict[str, Any]) -> bool:
    p = _payload(obj)
    if p.get("role") != "user":
        return False
    content = p.get("content")
    return bool(SPEC_RE.search(_text(content)))


def _event_flags(obj: dict[str, Any]) -> tuple[bool, bool]:
    p = _payload(obj)
    text = _text(p)
    typ = str(p.get("type", ""))
    complete = typ in {"task_complete", "turn_complete"} or "task_complete" in text.lower()
    idle = typ in {"idle", "root_idle"} or "root idle" in text.lower()
    return complete, idle


@dataclass
class _Parsed:
    session_id: str
    path: str
    cwd: str | None
    parent: str | None
    root: bool
    invoked: bool = False
    complete: bool = False
    idle: bool = False
    goal_complete: bool = False
    review_results: list[dict[str, Any]] | None = None
    claims: list[dict[str, Any]] | None = None
    reports: list[dict[str, Any]] | None = None
    evidence: list[str] | None = None
    timestamp: str | None = None


def parse_session(path: str | os.PathLike[str], data: Iterable[str], *, delta_only: bool = False,
                  metadata: dict[str, Any] | None = None) -> SessionObservation | None:
    """Parse JSONL without ever writing to the source file.

    ``metadata`` is read from the stable session_meta line when only a byte delta
    is supplied. Malformed/partial lines are ignored so a writer can be tailed.
    """
    path = str(path)
    sid = str((metadata or {}).get("session_id") or (metadata or {}).get("id") or "")
    parent = (metadata or {}).get("parent_session_id") or (metadata or {}).get("parent_id")
    cwd = (metadata or {}).get("cwd")
    parsed: _Parsed | None = None
    for raw in data:
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        msid, mparent, mcwd = _meta(obj)
        if msid:
            sid = msid
        if mparent:
            parent = mparent
        if mcwd:
            cwd = mcwd
        if not sid:
            continue
        if parsed is None:
            parsed = _Parsed(sid, path, cwd, parent, not bool(parent), claims=[], reports=[], evidence=[], review_results=[])
        parsed.cwd = cwd
        parsed.parent = parent
        parsed.root = not bool(parent)
        parsed.invoked = parsed.invoked or _is_user_specswarm(obj)
        complete, idle = _event_flags(obj)
        parsed.complete = parsed.complete or complete
        parsed.idle = parsed.idle or idle
        parsed.timestamp = obj.get("timestamp") or parsed.timestamp
        p = _payload(obj)
        text = _text(p.get("content") if p.get("role") else p)
        if p.get("role") == "assistant" and GOAL_COMPLETE_RE.search(text):
            parsed.goal_complete = True
        for result in REVIEW_RESULT_RE.finditer(text):
            parsed.review_results.append({"run_id": result.group(1), "verdict": result.group(2).upper(), "open_items": int(result.group(3)), "timestamp": obj.get("timestamp")})
        match = CLAIM_RE.search(text)
        if match:
            parsed.claims.append({"text": match.group(1).strip(), "timestamp": obj.get("timestamp")})
        if str(p.get("type", "")).lower() in {"report", "agent_report"} or "report:" in text.lower():
            parsed.reports.append({"text": text.strip(), "timestamp": obj.get("timestamp")})
        parsed.evidence.extend(EVIDENCE_RE.findall(text))
    if parsed is None or not sid:
        return None
    return SessionObservation(
        session_id=parsed.session_id, path=parsed.path, cwd=parsed.cwd,
        parent_session_id=parsed.parent, is_root=parsed.root,
        invoked_specswarm=parsed.invoked, root_complete=parsed.complete,
        root_idle=parsed.idle, goal_complete_requested=parsed.goal_complete,
        review_results=parsed.review_results or [], claims=parsed.claims or [],
        reports=parsed.reports or [], evidence_links=parsed.evidence or [],
        last_timestamp=parsed.timestamp,
    )


class SessionScanner:
    """Byte-watermarked scanner for Codex session JSONL files."""

    def __init__(self, root: str | os.PathLike[str], watermark_get, watermark_set):
        self.root = Path(root)
        self._get = watermark_get
        self._set = watermark_set

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for path in self.root.rglob("*.jsonl"):
            try:
                self._set(str(path), path.stat().st_size)
            except OSError:
                continue

    def scan(self) -> list[SessionObservation]:
        found: list[SessionObservation] = []
        if not self.root.exists():
            return found
        for path in self.root.rglob("*.jsonl"):
            try:
                size = path.stat().st_size
                offset = int(self._get(str(path)) or 0)
                if size < offset:
                    offset = 0  # truncated/rotated file; process current contents
                with path.open("rb") as handle:
                    head = handle.readline()
                    metadata = {}
                    try:
                        obj = json.loads(head.decode("utf-8", "ignore"))
                        p = _payload(obj)
                        metadata = p
                    except (ValueError, UnicodeError):
                        pass
                    handle.seek(offset if offset > 0 else 0)
                    raw = handle.read()
                lines = raw.decode("utf-8", "ignore").splitlines()
                obs = parse_session(path, lines, delta_only=offset > 0, metadata=metadata)
                self._set(str(path), size)
                if obs:
                    found.append(obs)
            except (OSError, UnicodeError):
                continue
        return found
