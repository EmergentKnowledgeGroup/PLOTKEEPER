from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Run, RunState


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Ledger:
    """Small transactional SQLite ledger; session files remain read-only inputs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=3000")
        self._schema()

    def _schema(self) -> None:
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS watermarks (
                    path TEXT PRIMARY KEY, byte_offset INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    root_session_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    cwd TEXT,
                    dashboard_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    review_injected_at TEXT,
                    review_receipt TEXT,
                    closed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS children (
                    run_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    PRIMARY KEY(run_id, session_id),
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, session_id TEXT,
                    kind TEXT NOT NULL, text TEXT NOT NULL,
                    evidence TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    run_id TEXT NOT NULL, task_id TEXT NOT NULL, title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', owner TEXT,
                    parent_task_id TEXT, workstream TEXT, source TEXT,
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(run_id, task_id)
                );
            """)

    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock, self.db:
            self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def watermark(self, path: str) -> int:
        row = self.db.execute("SELECT byte_offset FROM watermarks WHERE path=?", (path,)).fetchone()
        return int(row[0]) if row else 0

    def set_watermark(self, path: str, offset: int) -> None:
        with self._lock, self.db:
            self.db.execute("INSERT INTO watermarks(path,byte_offset) VALUES(?,?) ON CONFLICT(path) DO UPDATE SET byte_offset=excluded.byte_offset", (path, max(0, int(offset))))

    def enroll(self, root_session_id: str, cwd: str | None, dashboard_url: str) -> Run:
        with self._lock, self.db:
            row = self.db.execute("SELECT * FROM runs WHERE root_session_id=?", (root_session_id,)).fetchone()
            if row:
                return self._row(row)
            stamp = now_iso()
            run_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)", (run_id, root_session_id, RunState.OPEN.value, cwd, dashboard_url, stamp, stamp, None, None, None))
            return self.get(run_id)  # type: ignore[return-value]

    def get(self, run_id: str) -> Run | None:
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._row(row) if row else None

    def by_root(self, session_id: str) -> Run | None:
        row = self.db.execute("SELECT * FROM runs WHERE root_session_id=?", (session_id,)).fetchone()
        return self._row(row) if row else None

    def list_runs(self, active_only: bool = False) -> list[Run]:
        query = "SELECT * FROM runs"
        if active_only:
            query += " WHERE state != 'CLOSED'"
        query += " ORDER BY created_at DESC"
        return [self._row(row) for row in self.db.execute(query)]

    def attach_child(self, run_id: str, session_id: str) -> None:
        with self._lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO children(run_id,session_id) VALUES(?,?)", (run_id, session_id))

    def add_report(self, run_id: str, kind: str, text: str, *, session_id: str | None = None, evidence: Iterable[str] = ()) -> int:
        with self._lock, self.db:
            cur = self.db.execute("INSERT INTO reports(run_id,session_id,kind,text,evidence,created_at) VALUES(?,?,?,?,?,?)", (run_id, session_id, kind, text, json.dumps(list(evidence)), now_iso()))
            self.db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (now_iso(), run_id))
            return int(cur.lastrowid)

    def reports(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM reports WHERE run_id=? ORDER BY id", (run_id,))
        return [dict(row) for row in rows]

    def has_report_kind(self, run_id: str, kind: str) -> bool:
        return self.db.execute("SELECT 1 FROM reports WHERE run_id=? AND kind=? LIMIT 1", (run_id, kind)).fetchone() is not None

    def replace_tasks(self, run_id: str, tasks: list[dict[str, Any]]) -> None:
        with self._lock, self.db:
            self.db.execute("DELETE FROM tasks WHERE run_id=?", (run_id,))
            for i, task in enumerate(tasks):
                self.db.execute("INSERT INTO tasks(run_id,task_id,title,status,owner,parent_task_id,workstream,source,ordinal) VALUES(?,?,?,?,?,?,?,?,?)",
                    (run_id, task["task_id"], task["title"], task.get("status", "pending"), task.get("owner"), task.get("parent_task_id"), task.get("workstream"), task.get("source"), i))
            self.db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (now_iso(), run_id))

    def tasks(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY ordinal", (run_id,))]

    def mark_review_pending(self, run_id: str) -> bool:
        with self._lock, self.db:
            row = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or row[0] == RunState.CLOSED.value:
                return False
            self.db.execute("UPDATE runs SET state=?,updated_at=?,review_injected_at=? WHERE run_id=?", (RunState.REVIEW_PENDING.value, now_iso(), now_iso(), run_id))
            return True

    def mark_review_required(self, run_id: str) -> bool:
        with self._lock, self.db:
            row = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or row[0] == RunState.CLOSED.value:
                return False
            self.db.execute("UPDATE runs SET state=?,updated_at=? WHERE run_id=?", (RunState.REVIEW_REQUIRED.value, now_iso(), run_id))
            return True

    def record_receipt(self, run_id: str, receipt: dict[str, Any]) -> bool:
        if (not receipt.get("terminal") or not receipt.get("injected") or
                str(receipt.get("verdict", "")).upper() != "PASS" or
                int(receipt.get("open_items", -1)) != 0):
            return False
        with self._lock, self.db:
            row = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or row[0] not in {RunState.REVIEW_PENDING.value, RunState.REVIEW_REQUIRED.value}:
                return False
            self.db.execute("UPDATE runs SET state=?,review_receipt=?,updated_at=? WHERE run_id=?", (RunState.REVIEWED.value, json.dumps(receipt, sort_keys=True), now_iso(), run_id))
            return True

    def close(self, run_id: str) -> bool:
        with self._lock, self.db:
            row = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or row[0] != RunState.REVIEWED.value:
                return False
            self.db.execute("UPDATE runs SET state=?,closed_at=?,updated_at=? WHERE run_id=?", (RunState.CLOSED.value, now_iso(), now_iso(), run_id))
            return True

    def _row(self, row: sqlite3.Row) -> Run:
        children = tuple(r[0] for r in self.db.execute("SELECT session_id FROM children WHERE run_id=? ORDER BY session_id", (row["run_id"],)))
        return Run(row["run_id"], row["root_session_id"], RunState(row["state"]), row["cwd"], row["dashboard_url"], row["created_at"], row["updated_at"], row["review_injected_at"], json.loads(row["review_receipt"]) if row["review_receipt"] else None, row["closed_at"], children)

    def close_db(self) -> None:
        self.db.close()
