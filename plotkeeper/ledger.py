from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

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
                    root_session_id TEXT NOT NULL,
                    root_key TEXT,
                    predecessor_run_id TEXT,
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
                CREATE TABLE IF NOT EXISTS goal_contracts (
                    run_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL,
                    path TEXT NOT NULL, status TEXT NOT NULL,
                    user_goal TEXT NOT NULL, contract_hash TEXT,
                    baseline_sha TEXT, payload TEXT NOT NULL,
                    synced_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
            """)
            self._migrate_runs_schema()

    def _migrate_runs_schema(self) -> None:
        """Upgrade pre-successor ledgers without rewriting their payloads.

        The original table declared ``root_session_id UNIQUE`` and also had a
        globally unique ``root_key`` index.  Both constraints made a closed
        run impossible to follow up.  Rebuild only that table (SQLite cannot
        drop an inline UNIQUE constraint), copying every historical value and
        leaving all dependent tables untouched.
        """
        columns = {str(row[1]) for row in self.db.execute("PRAGMA table_info(runs)")}
        sql_row = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='runs'"
        ).fetchone()
        table_sql = str(sql_row[0] or "") if sql_row else ""
        needs_rebuild = "root_session_id TEXT NOT NULL UNIQUE" in table_sql
        if "root_key" not in columns or "predecessor_run_id" not in columns:
            needs_rebuild = True
        if needs_rebuild:
            old_columns = columns
            # SQLite normally rewrites dependent FOREIGN KEY declarations
            # during ALTER TABLE ... RENAME.  Keep every dependent table
            # pointing at the canonical ``runs`` table while its rows table
            # is rebuilt; this avoids orphaning children/contracts.
            self.db.execute("PRAGMA legacy_alter_table=ON")
            self.db.execute("ALTER TABLE runs RENAME TO runs_legacy_migration")
            self.db.execute("""CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                root_session_id TEXT NOT NULL,
                root_key TEXT,
                predecessor_run_id TEXT,
                state TEXT NOT NULL,
                cwd TEXT,
                dashboard_url TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                review_injected_at TEXT,
                review_receipt TEXT,
                closed_at TEXT
            )""")
            def old_expr(name: str, fallback: str) -> str:
                return name if name in old_columns else fallback
            self.db.execute(f"""INSERT INTO runs(
                run_id,root_session_id,root_key,predecessor_run_id,state,cwd,
                dashboard_url,created_at,updated_at,review_injected_at,
                review_receipt,closed_at)
                SELECT run_id,root_session_id,
                       {old_expr('root_key', 'root_session_id')},
                       {old_expr('predecessor_run_id', 'NULL')},
                       state,cwd,dashboard_url,created_at,updated_at,
                       review_injected_at,review_receipt,closed_at
                  FROM runs_legacy_migration""")
            self.db.execute("DROP TABLE runs_legacy_migration")
            self.db.execute("PRAGMA legacy_alter_table=OFF")
        # A legacy unique index survives table rebuilds only when explicitly
        # recreated; remove it defensively for ledgers migrated in place.
        self.db.execute("DROP INDEX IF EXISTS runs_root_key_unique")
        self.db.execute("UPDATE runs SET root_key=root_session_id WHERE root_key IS NULL OR root_key='' ")
        self.db.execute("CREATE INDEX IF NOT EXISTS runs_root_key_idx ON runs(root_key)")
        self.db.execute("DROP INDEX IF EXISTS runs_active_root_unique")
        self.db.execute("CREATE UNIQUE INDEX runs_active_root_unique ON runs(root_key) WHERE state != 'CLOSED'")

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

    @staticmethod
    def valid_root_session_id(session_id: str | None) -> bool:
        """Reject the historical ``msg_`` parser artifact at enrollment time."""
        return bool(session_id and str(session_id).strip() and not str(session_id).startswith("msg_"))

    def enroll(self, root_session_id: str, cwd: str | None, dashboard_url: str,
               canonical_root_id: str | None = None) -> Run | None:
        if not self.valid_root_session_id(root_session_id):
            return None
        root_key = canonical_root_id or f"session:{root_session_id}"
        with self._lock, self.db:
            # Enrollment is idempotent while the canonical task is active.
            # Closed rows are historical predecessors, never candidates for
            # reopening or mutation.
            row = self.db.execute(
                "SELECT * FROM runs WHERE root_key=? AND state != ? ORDER BY created_at DESC LIMIT 1",
                (root_key, RunState.CLOSED.value),
            ).fetchone()
            if row:
                return self._row(row)
            predecessor = self.db.execute(
                "SELECT * FROM runs WHERE root_key=? AND state=? ORDER BY closed_at DESC, updated_at DESC, created_at DESC LIMIT 1",
                (root_key, RunState.CLOSED.value),
            ).fetchone()
            stamp = now_iso()
            run_id = uuid.uuid4().hex
            try:
                self.db.execute("INSERT INTO runs(run_id,root_session_id,root_key,predecessor_run_id,state,cwd,dashboard_url,created_at,updated_at,review_injected_at,review_receipt,closed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                (run_id, root_session_id, root_key,
                                 predecessor["run_id"] if predecessor else None,
                                 RunState.OPEN.value, cwd, dashboard_url, stamp, stamp, None, None, None))
            except sqlite3.IntegrityError:
                # Another process may have won the active-root race between
                # our read and insert.  Return that winner, never create a
                # second active successor and never touch the predecessor.
                winner = self.db.execute(
                    "SELECT * FROM runs WHERE root_key=? AND state != ? ORDER BY created_at DESC LIMIT 1",
                    (root_key, RunState.CLOSED.value),
                ).fetchone()
                if winner:
                    return self._row(winner)
                raise
            return self.get(run_id)  # type: ignore[return-value]

    def get(self, run_id: str) -> Run | None:
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._row(row) if row else None

    def by_root(self, session_id: str, *, active_only: bool = False) -> Run | None:
        query = "SELECT * FROM runs WHERE root_session_id=?"
        params: tuple[Any, ...] = (session_id,)
        if active_only:
            query += " AND state != ?"
            params += (RunState.CLOSED.value,)
        query += " ORDER BY (state != 'CLOSED') DESC, created_at DESC LIMIT 1"
        row = self.db.execute(query, params).fetchone()
        return self._row(row) if row else None

    def by_session(self, session_id: str, *, active_only: bool = False) -> list[Run]:
        """Return exact root/child matches without cwd or project inference."""
        query = (
            "SELECT r.* FROM runs r WHERE r.root_session_id=? "
            "UNION ALL SELECT r.* FROM runs r JOIN children c ON c.run_id=r.run_id WHERE c.session_id=?"
        )
        params: tuple[Any, ...] = (session_id, session_id)
        rows = list(self.db.execute(query, params))
        runs_by_id: dict[str, Run] = {}
        for row in rows:
            runs_by_id.setdefault(row["run_id"], self._row(row))
        runs = list(runs_by_id.values())
        if active_only:
            runs = [run for run in runs if run.state != RunState.CLOSED]
        return runs

    def by_canonical_root(self, canonical_root_id: str, *, active_only: bool = False) -> Run | None:
        query = "SELECT * FROM runs WHERE root_key=?"
        params: tuple[Any, ...] = (canonical_root_id,)
        if active_only:
            query += " AND state != ?"
            params += (RunState.CLOSED.value,)
        query += " ORDER BY (state != 'CLOSED') DESC, created_at DESC LIMIT 1"
        row = self.db.execute(query, params).fetchone()
        return self._row(row) if row else None

    def list_runs(self, active_only: bool = False) -> list[Run]:
        query = "SELECT * FROM runs"
        if active_only:
            query += " WHERE state != 'CLOSED'"
        query += " ORDER BY created_at DESC"
        return [self._row(row) for row in self.db.execute(query)]

    def attach_child(self, run_id: str, session_id: str) -> None:
        with self._lock, self.db:
            state = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not state or state[0] == RunState.CLOSED.value:
                return
            self.db.execute("INSERT OR IGNORE INTO children(run_id,session_id) VALUES(?,?)", (run_id, session_id))

    def add_report(self, run_id: str, kind: str, text: str, *, session_id: str | None = None, evidence: Iterable[str] = ()) -> int:
        with self._lock, self.db:
            state = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not state or state[0] == RunState.CLOSED.value:
                return 0
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
            state = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not state or state[0] == RunState.CLOSED.value:
                return
            self.db.execute("DELETE FROM tasks WHERE run_id=?", (run_id,))
            for i, task in enumerate(tasks):
                self.db.execute("INSERT INTO tasks(run_id,task_id,title,status,owner,parent_task_id,workstream,source,ordinal) VALUES(?,?,?,?,?,?,?,?,?)",
                    (run_id, task["task_id"], task["title"], task.get("status", "pending"), task.get("owner"), task.get("parent_task_id"), task.get("workstream"), task.get("source"), i))
            self.db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (now_iso(), run_id))

    def tasks(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY ordinal", (run_id,))]

    def set_goal_contract(self, run_id: str, path: str, payload: dict[str, Any]) -> None:
        baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}
        with self._lock, self.db:
            state = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not state or state[0] == RunState.CLOSED.value:
                return
            self.db.execute(
                """INSERT INTO goal_contracts(run_id,contract_id,path,status,user_goal,contract_hash,baseline_sha,payload,synced_at)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(run_id) DO UPDATE SET contract_id=excluded.contract_id,path=excluded.path,
                   status=excluded.status,user_goal=excluded.user_goal,contract_hash=excluded.contract_hash,
                   baseline_sha=excluded.baseline_sha,payload=excluded.payload,synced_at=excluded.synced_at""",
                (run_id, str(payload.get("id", "unknown")), path, str(payload.get("status", "unknown")),
                 str(payload.get("user_goal", "Goal not recorded")), payload.get("contract_hash"),
                 baseline.get("sha"), json.dumps(payload, sort_keys=True), now_iso()),
            )
            self.db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (now_iso(), run_id))

    def goal_contract(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM goal_contracts WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

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
        """Reject the pre-revalidation receipt shortcut.

        Kept as a compatibility-shaped method for callers that still import
        it, but deliberately cannot advance a run.  Only ``finalize_review``
        after service-owned canonical validation may persist a receipt.
        """
        return False

    @staticmethod
    def _is_final_review_task(task: sqlite3.Row) -> bool:
        """Return whether a task is the independent review closeout task.

        Task plans are user-owned text, so avoid a task-id or ordinal magic
        value.  The final task must explicitly identify itself as independent
        review/receipt work; a lone arbitrary pending task is not sufficient.
        """
        title = str(task["title"] or "").casefold()
        return "independent" in title and ("review" in title or "receipt" in title)

    def finalize_review(self, run_id: str, receipt: dict[str, Any], *,
                        failure_hook: Callable[[str], None] | None = None) -> bool:
        """Atomically persist a validated receipt and close its run.

        Receipt validation is deliberately owned by :class:`PlotkeeperService`;
        this narrow ledger primitive only accepts the already validated JSON
        and performs the final-task transition plus run close in one SQLite
        transaction.  ``failure_hook`` is test-only fault injection at named
        transaction boundaries and is never consulted by production callers.
        """
        if not isinstance(receipt, dict) or str(receipt.get("verdict", "")).upper() != "PASS":
            return False
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                row = self.db.execute(
                    "SELECT state,review_receipt FROM runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if not row or row[0] != RunState.REVIEW_PENDING.value or row[1] is not None:
                    self.db.rollback()
                    return False
                tasks = list(self.db.execute(
                    "SELECT * FROM tasks WHERE run_id=? ORDER BY ordinal", (run_id,)
                ))
                pending = [task for task in tasks if str(task["status"]).casefold() != "completed"]
                if len(pending) != 1 or not self._is_final_review_task(pending[0]):
                    self.db.rollback()
                    return False
                task = pending[0]
                changed = self.db.execute(
                    "UPDATE tasks SET status=? WHERE run_id=? AND task_id=? AND status<>?",
                    ("completed", run_id, task["task_id"], "completed"),
                )
                if changed.rowcount != 1:
                    self.db.rollback()
                    return False
                if failure_hook:
                    failure_hook("final_task_completed")
                stamp = now_iso()
                self.db.execute(
                    "UPDATE runs SET state=?,review_receipt=?,closed_at=?,updated_at=? "
                    "WHERE run_id=? AND state=? AND review_receipt IS NULL",
                    (RunState.CLOSED.value, json.dumps(receipt, sort_keys=True), stamp,
                     stamp, run_id, RunState.REVIEW_PENDING.value),
                )
                if self.db.execute("SELECT changes()").fetchone()[0] != 1:
                    self.db.rollback()
                    return False
                if failure_hook:
                    failure_hook("run_closed")
                self.db.commit()
                return True
            except Exception:
                self.db.rollback()
                return False

    def close(self, run_id: str) -> bool:
        with self._lock, self.db:
            row = self.db.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row or row[0] != RunState.REVIEWED.value:
                return False
            self.db.execute("UPDATE runs SET state=?,closed_at=?,updated_at=? WHERE run_id=?", (RunState.CLOSED.value, now_iso(), now_iso(), run_id))
            return True

    def _row(self, row: sqlite3.Row) -> Run:
        children = tuple(r[0] for r in self.db.execute("SELECT session_id FROM children WHERE run_id=? ORDER BY session_id", (row["run_id"],)))
        successor = self.db.execute(
            "SELECT run_id FROM runs WHERE predecessor_run_id=? ORDER BY created_at LIMIT 1",
            (row["run_id"],),
        ).fetchone()
        return Run(row["run_id"], row["root_session_id"], RunState(row["state"]), row["cwd"], row["dashboard_url"], row["created_at"], row["updated_at"], row["review_injected_at"], json.loads(row["review_receipt"]) if row["review_receipt"] else None, row["closed_at"], children, row["root_key"], row["predecessor_run_id"], successor[0] if successor else None)

    def close_db(self) -> None:
        self.db.close()
