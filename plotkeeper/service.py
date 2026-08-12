from __future__ import annotations

import json
import os
import subprocess
import threading
import re
from urllib.parse import quote
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .ledger import Ledger
from .models import RunState, SessionObservation
from .sessions import SessionScanner, ThreadCatalog


class PlotkeeperService:
    def __init__(self, *, ledger_path: str | os.PathLike[str] = "runtime/plotkeeper.sqlite3",
                 sessions_root: str | os.PathLike[str] = Path.home() / ".codex" / "sessions",
                 dashboard_url: str = "http://127.0.0.1:47831",
                 codex_state_path: str | os.PathLike[str] | None = None,
                 thread_catalog: ThreadCatalog | None = None):
        self.ledger = Ledger(ledger_path)
        self.dashboard_url = dashboard_url.rstrip("/")
        self.scanner = SessionScanner(sessions_root, self.ledger.watermark, self.ledger.set_watermark)
        self.thread_catalog = thread_catalog or ThreadCatalog(codex_state_path, sessions_root)
        self._session_identity: dict[str, dict[str, Any]] = {}
        if self.ledger.get_meta("activation_at") is None:
            self.ledger.set_meta("activation_at", self._now())
            self.scanner.initialize()
        self._events: list[dict[str, Any]] = []
        self._event_lock = threading.Lock()
        self._stop = threading.Event()

    @staticmethod
    def _now() -> str:
        from .ledger import now_iso
        return now_iso()

    def poll_once(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for obs in self.scanner.scan():
            self._session_identity[obs.session_id] = {
                "task_id": obs.task_id or obs.session_id,
                "task_label": obs.task_label or obs.task_id or obs.session_id,
                "project_name": self._project_name(obs.cwd),
            }
            # Closed roots are historical only.  A follow-up with the same
            # canonical task identity must enroll through ``Ledger.enroll`` so
            # it receives a fresh successor rather than reopening history.
            run = self.ledger.by_root(obs.session_id, active_only=True)
            # A root task can have multiple Codex session files (worktree or
            # message-id variants). Resolve those to the same ledger run before
            # considering enrollment, then retain the variant as a child so
            # its reports/history remain visible.
            if run is None and obs.canonical_root_id:
                run = self.ledger.by_canonical_root(obs.canonical_root_id, active_only=True)
                if run and run.root_session_id != obs.session_id:
                    self.ledger.attach_child(run.run_id, obs.session_id)
                    events.append({"type": "root_variant_attached", "run_id": run.run_id, "session_id": obs.session_id})
            if obs.invoked_specswarm and obs.is_root:
                if run is None and self.ledger.valid_root_session_id(obs.session_id):
                    run = self.ledger.enroll(obs.session_id, obs.cwd, self.dashboard_url, obs.canonical_root_id)
                    if run is None:
                        continue
                    event = {"type": "run_enrolled", "run_id": run.run_id, "session_id": obs.session_id}
                    if run.predecessor_run_id:
                        event["predecessor_run_id"] = run.predecessor_run_id
                    events.append(event)
            if run is None and obs.attach_run_ids:
                candidate = self.ledger.get(obs.attach_run_ids[-1])
                if candidate and candidate.state != RunState.CLOSED:
                    run = candidate
                    self.ledger.attach_child(run.run_id, obs.session_id)
                    events.append({"type": "session_attached", "run_id": run.run_id, "session_id": obs.session_id})
            if run is None and obs.parent_session_id:
                parent = self.ledger.by_root(obs.parent_session_id)
                if parent:
                    run = parent
                    if run.state == RunState.CLOSED:
                        continue
                    self.ledger.attach_child(run.run_id, obs.session_id)
                    events.append({"type": "child_attached", "run_id": run.run_id, "session_id": obs.session_id})
            if run is None:
                continue
            if run.state == RunState.CLOSED:
                continue
            if obs.parent_session_id and obs.session_id != run.root_session_id:
                self.ledger.attach_child(run.run_id, obs.session_id)
            for claim in obs.claims:
                self.ledger.add_report(run.run_id, "claim", claim["text"], session_id=obs.session_id, evidence=obs.evidence_links)
            for report in obs.reports:
                self.ledger.add_report(run.run_id, "report", report["text"], session_id=obs.session_id, evidence=obs.evidence_links)
            if obs.session_id == run.root_session_id and obs.goal_complete_requested and not self.ledger.has_report_kind(run.run_id, "goal_complete"):
                self.ledger.add_report(run.run_id, "goal_complete", "Root agent reported goal complete", session_id=obs.session_id)
            for result in obs.review_results:
                if result["run_id"] == run.run_id and run.state in {RunState.REVIEW_PENDING, RunState.REVIEW_REQUIRED}:
                    receipt = {"terminal": True, "injected": True, **result}
                    if self.ledger.record_receipt(run.run_id, receipt) and result["verdict"] == "PASS" and result["open_items"] == 0:
                        self.ledger.close(run.run_id)
                        events.append({"type": "run_closed", "run_id": run.run_id})
            if obs.session_id == run.root_session_id and obs.root_complete and self.ledger.has_report_kind(run.run_id, "goal_complete") and run.state == RunState.OPEN:
                self.ledger.mark_review_required(run.run_id)
                events.append({"type": "review_required", "run_id": run.run_id})
        self._append_events(events)
        return events

    @staticmethod
    def _project_name(cwd: str | None) -> str:
        if not cwd:
            return "Plotkeeper run"
        value = str(cwd).replace("\\\\?\\", "")
        if "\\" in value:
            return value.rstrip("\\/").rsplit("\\", 1)[-1] or value
        return Path(value).name or value

    @staticmethod
    def _same_cwd(left: str | None, right: str | None) -> bool:
        if not left or not right:
            return False
        normalize = lambda value: os.path.normcase(os.path.normpath(str(value).replace("\\\\?\\", "")))
        return normalize(left) == normalize(right)

    @staticmethod
    def _session_ids(run) -> list[str]:
        return list(dict.fromkeys((run.root_session_id, *run.children)))

    @staticmethod
    def _is_subagent(metadata: dict[str, Any] | None) -> bool:
        return bool(metadata and str(metadata.get("thread_source") or "").strip().lower() == "subagent")

    def _active_session_ids(self, run) -> list[str]:
        active: list[str] = []
        for session_id in self._session_ids(run):
            metadata = self.thread_catalog.metadata(session_id)
            # Nested native subagents are implementation details of their
            # owning task, not separate user-facing run surfaces.
            if (metadata is not None and not self._is_subagent(metadata) and
                    not metadata.get("agent_path") and self.thread_catalog.is_active(session_id)):
                active.append(session_id)
        return active

    def _identity(self, run, session_id: str | None = None) -> dict[str, Any]:
        bound_session_id = session_id or next(iter(self._active_session_ids(run)), run.root_session_id)
        identity = dict(self._session_identity.get(bound_session_id, {}))
        catalog = self.thread_catalog.metadata(bound_session_id)
        if catalog:
            identity.update({key: catalog[key] for key in ("task_label", "project_name", "agent_path") if catalog.get(key)})
            identity["task_id"] = catalog.get("id") or identity.get("task_id") or bound_session_id
        identity.setdefault("task_id", bound_session_id)
        identity.setdefault("task_label", bound_session_id)
        identity.setdefault("project_name", self._project_name(run.cwd))
        return identity

    def _dashboard_url(self, run, session_id: str | None = None) -> str:
        bound_session_id = session_id or next(iter(self._active_session_ids(run)), run.root_session_id)
        return f"{run.dashboard_url.rstrip('/')}/?run_id={quote(run.run_id)}&session_id={quote(bound_session_id)}"

    def _run_payload(self, run, session_id: str | None = None) -> dict[str, Any]:
        bound_session_id = session_id or next(iter(self._active_session_ids(run)), run.root_session_id)
        payload = run.to_dict(self._identity(run, bound_session_id))
        payload["bound_session_id"] = bound_session_id
        payload["dashboard_url"] = self._dashboard_url(run, bound_session_id)
        catalog = self.thread_catalog.metadata(bound_session_id)
        if catalog and catalog.get("thread_source"):
            payload["thread_source"] = str(catalog["thread_source"])
        return payload

    def _interactive_runs(self) -> list[Any]:
        runs: list[Any] = []
        for run in self.ledger.list_runs(active_only=True):
            # ``msg_`` roots are legacy message ids, not stable task/session
            # locators. Keep the ledger row intact but never expose it here.
            if not self.ledger.valid_root_session_id(run.root_session_id):
                continue
            if not self._active_session_ids(run):
                continue
            runs.append(run)
        return runs

    def resolve_active_run(self, *, run_id: str | None = None,
                           session_id: str | None = None,
                           cwd: str | None = None) -> tuple[Any | None, dict[str, Any] | None]:
        """Resolve one active run, never falling through to a project guess."""
        if run_id and session_id:
            by_run = self.ledger.get(run_id)
            matches = self.ledger.by_session(session_id, active_only=True)
            if not by_run or all(match.run_id != run_id for match in matches):
                return None, {"ok": False, "error": "locator_conflict"}
            metadata = self.thread_catalog.metadata(session_id)
            if self._is_subagent(metadata):
                return None, {"ok": False, "error": "run_subagent"}
            if metadata is not None and not self.thread_catalog.is_active(session_id):
                return None, {"ok": False, "error": "run_inactive"}
            if metadata is None and self.thread_catalog.available and re.fullmatch(r"[0-9a-fA-F-]{20,}", session_id):
                return None, {"ok": False, "error": "run_identity_unavailable"}
        if run_id:
            run = self.ledger.get(run_id)
            if not run:
                return None, {"ok": False, "error": "run_not_found"}
            if run.state.value == RunState.CLOSED.value:
                return None, {"ok": False, "error": "run_closed"}
            if not self.ledger.valid_root_session_id(run.root_session_id):
                return None, {"ok": False, "error": "run_identity_invalid"}
            if self.thread_catalog.available and not self._active_session_ids(run):
                return None, {"ok": False, "error": "run_inactive"}
            return run, None
        if session_id:
            matches = self.ledger.by_session(session_id, active_only=True)
            if len(matches) != 1:
                return None, {"ok": False, "error": "session_ambiguous" if len(matches) > 1 else "session_not_found"}
            if not self.ledger.valid_root_session_id(matches[0].root_session_id):
                return None, {"ok": False, "error": "run_identity_invalid"}
            metadata = self.thread_catalog.metadata(session_id)
            if self._is_subagent(metadata):
                return None, {"ok": False, "error": "run_subagent"}
            if metadata is None and self.thread_catalog.available and re.fullmatch(r"[0-9a-fA-F-]{20,}", session_id):
                return None, {"ok": False, "error": "run_identity_unavailable"}
            if metadata is not None and not self.thread_catalog.is_active(session_id):
                return None, {"ok": False, "error": "run_inactive"}
            return matches[0], None
        runs = self._interactive_runs()
        if cwd:
            matches = [run for run in runs if self._same_cwd(run.cwd, cwd)]
            if len(matches) != 1:
                return None, {"ok": False, "error": "cwd_ambiguous" if len(matches) > 1 else "cwd_not_found", "matches": [self._run_payload(run) for run in matches]}
            return matches[0], None
        if len(runs) != 1:
            return None, {"ok": False, "error": "selection_required" if len(runs) > 1 else "no_active_run", "matches": [self._run_payload(run) for run in runs]}
        return runs[0], None

    def current(self, cwd: str | None = None, *, run_id: str | None = None,
                session_id: str | None = None) -> dict[str, Any]:
        run, error = self.resolve_active_run(run_id=run_id, session_id=session_id, cwd=cwd)
        if error:
            return error
        payload = self._run_payload(run, session_id=session_id)
        return {"ok": True, "run": payload, **payload}

    def inject_review(self, run_id: str, *, runner: Callable[[list[str]], Any] | None = None) -> dict[str, Any]:
        run = self.ledger.get(run_id)
        if not run or run.state == RunState.CLOSED:
            return {"ok": False, "error": "run_not_open"}
        if run.state not in {RunState.REVIEW_REQUIRED, RunState.REVIEW_PENDING}:
            return {"ok": False, "error": "root_not_complete"}
        if run.state == RunState.REVIEW_PENDING:
            return {"ok": False, "error": "review_already_pending"}
        args = ["codex.exe", "exec", "resume", run.root_session_id, self.review_prompt(run_id), "--json", "--skip-git-repo-check"]
        runner = runner or self._run_codex
        self.ledger.mark_review_pending(run_id)
        try:
            result = runner(args)
            code = getattr(result, "returncode", result if isinstance(result, int) else 0)
        except Exception as exc:
            self.ledger.mark_review_required(run_id)
            return {"ok": False, "error": "injection_failed", "detail": str(exc)}
        if code != 0:
            self.ledger.mark_review_required(run_id)
            return {"ok": False, "error": "injection_failed", "returncode": code}
        return {"ok": True, "state": RunState.REVIEW_PENDING.value, "run_id": run_id}

    @staticmethod
    def _run_codex(args: list[str]):
        return subprocess.run(args, capture_output=True, text=True, check=False)

    def review_prompt(self, run_id: str) -> str:
        contract = self.ledger.goal_contract(run_id)
        contract_ref = (f"contract {contract['contract_id']} at {contract['path']}" if contract else
                        "the original production goal contract (if missing, treat that as an explicit blocker)")
        return (f"Plotkeeper closeout gate for run {run_id}. Invoke $production-goal-review and follow that skill fully. "
                f"Run its independent adversarial review against {contract_ref} AND inspect the entire Plotkeeper run: "
                "every task, child report, blocker, timeline entry, and evidence link. Do not substitute a generic PK review "
                "for the production goal review. Resolve anything still open. End with exactly: "
                f"PK:REVIEW_RESULT run_id={run_id} verdict=<PASS|PARTIAL|FAIL|BLOCKED> open_items=<integer>")

    def sync_plan(self, run_id: str, paths: list[str], contract_path: str | None = None) -> dict[str, Any]:
        run = self.ledger.get(run_id)
        if not run or run.state == RunState.CLOSED:
            return {"ok": False, "error": "run_closed_or_missing"}
        tasks: list[dict[str, Any]] = []
        ordinal = 0
        checkbox = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+?)\s*$")
        numbered = re.compile(r"^\s*(?:Task\s+)?(\d+)[.):]\s+(.+?)\s*$", re.I)
        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_file():
                continue
            workstream = path.stem.replace("_", " ").title()
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                match = checkbox.match(line) or numbered.match(line)
                if not match:
                    continue
                ordinal += 1
                done = checkbox.match(line)
                title = match.group(2).strip()
                tasks.append({"task_id": f"T{ordinal:03d}", "title": title, "status": "completed" if done and match.group(1).strip() else "pending", "owner": "unassigned", "workstream": workstream, "source": str(path)})
        self.ledger.replace_tasks(run_id, tasks)
        contract = None
        if contract_path:
            path = Path(contract_path)
            if not path.is_file():
                return {"ok": False, "error": "contract_not_found", "path": str(path)}
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                return {"ok": False, "error": "contract_invalid_json", "detail": str(exc)}
            if not isinstance(payload, dict) or not payload.get("id") or not payload.get("user_goal"):
                return {"ok": False, "error": "contract_missing_required_fields"}
            self.ledger.set_goal_contract(run_id, str(path.resolve()), payload)
            contract = self.ledger.goal_contract(run_id)
        return {"ok": True, "count": len(tasks), "contract": contract}

    def request_check_in(self, run_id: str) -> dict[str, Any]:
        run = self.ledger.get(run_id)
        if not run or run.state == RunState.CLOSED:
            return {"ok": False, "error": "run_closed_or_missing"}
        if self.ledger.has_report_kind(run_id, "check-in-request"):
            return {"ok": True, "already_requested": True}
        self.ledger.add_report(run_id, "check-in-request", "Human requested: complete the current objective, report status, and end the turn.")
        return {"ok": True, "queued": True}

    def inject_check_in(self, run_id: str) -> dict[str, Any]:
        run = self.ledger.get(run_id)
        if not run or run.state == RunState.CLOSED:
            return {"ok": False, "error": "run_closed_or_missing"}
        args = ["codex.exe", "exec", "resume", run.root_session_id,
                "PLOTKEEPER CHECK-IN REQUEST: Complete only your current bounded objective, update Plotkeeper with your status/evidence, then check in with the human and end this turn. Do not begin another task.",
                "--json", "--skip-git-repo-check"]
        try:
            result = self._run_codex(args)
            if result.returncode == 0:
                self.ledger.add_report(run_id, "check-in-injected", "Check-in turn injected into the root session.")
            return {"ok": result.returncode == 0, "returncode": result.returncode}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def record_review_receipt(self, run_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        ok = self.ledger.record_receipt(run_id, receipt)
        return {"ok": ok, "run": self.ledger.get(run_id).to_dict() if self.ledger.get(run_id) else None}

    def close(self, run_id: str) -> dict[str, Any]:
        ok = self.ledger.close(run_id)
        return {"ok": ok, "run": self.ledger.get(run_id).to_dict() if self.ledger.get(run_id) else None}

    def report(self, run_id: str, kind: str, text: str, *, evidence: list[str] | None = None) -> dict[str, Any]:
        run = self.ledger.get(run_id)
        if not run or run.state == RunState.CLOSED:
            return {"ok": False, "error": "run_closed_or_missing"}
        report_id = self.ledger.add_report(run_id, kind, text, evidence=evidence or [])
        return {"ok": True, "report_id": report_id}

    def _append_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        with self._event_lock:
            self._events.extend(events)
            del self._events[:-1000]

    def events_since(self, index: int = 0) -> tuple[int, list[dict[str, Any]]]:
        with self._event_lock:
            return len(self._events), self._events[index:]

    def serve(self, host: str = "127.0.0.1", port: int = 47831) -> ThreadingHTTPServer:
        service = self
        web_root = Path(__file__).resolve().parent / "web"

        class Handler(BaseHTTPRequestHandler):
            def _json(self, body: Any, status: int = 200) -> None:
                raw = json.dumps(body, sort_keys=True).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(raw)

            def _error(self, status: int, detail: str) -> None:
                """Always terminate failures with a non-empty HTTP response.

                Static-file and query parsing failures used to escape the
                handler and leave clients with an empty socket, which made a
                stale dashboard indistinguishable from a dead listener.
                """
                raw = (f"Plotkeeper error {status}: {detail}\n").encode("utf-8", "replace")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    return

            def _body(self) -> dict[str, Any]:
                n = int(self.headers.get("Content-Length", "0"))
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return {}

            def do_GET(self) -> None:
                try:
                    self._do_GET()
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

            def _do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._json({"ok": True, "service": "plotkeeper"})
                elif parsed.path == "/favicon.ico":
                    self.send_response(HTTPStatus.NO_CONTENT); self.end_headers()
                elif parsed.path in {"/", "/dashboard", "/web/styles.css", "/web/app.js"}:
                    target = web_root / ("index.html" if parsed.path in {"/", "/dashboard"} else parsed.path.rsplit("/", 1)[-1])
                    if not target.is_file():
                        self._error(HTTPStatus.NOT_FOUND, "dashboard asset is unavailable")
                        return
                    raw = target.read_bytes()
                    content_type = "text/html; charset=utf-8" if target.suffix == ".html" else ("text/css; charset=utf-8" if target.suffix == ".css" else "text/javascript; charset=utf-8")
                    self.send_response(HTTPStatus.OK); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                elif parsed.path == "/api/runs":
                    # Interactive inventory is intentionally active-only. The
                    # ledger remains the source of historical detail, but
                    # closed/legacy rows never enter the chooser.
                    self._json([service._run_payload(r) for r in service._interactive_runs()])
                elif parsed.path == "/api/current":
                    query = parse_qs(parsed.query)
                    result = service.current(
                        cwd=query.get("cwd", [None])[0],
                        run_id=query.get("run_id", [None])[0],
                        session_id=query.get("session_id", [None])[0],
                    )
                    status = 200 if result.get("ok") else (404 if result.get("error") in {"run_not_found", "session_not_found", "cwd_not_found", "no_active_run", "run_closed", "run_inactive", "run_identity_invalid", "run_identity_unavailable", "run_subagent"} else 409)
                    self._json(result, status)
                elif parsed.path.startswith("/api/runs/"):
                    rid = parsed.path.rsplit("/", 1)[-1]
                    run = service.ledger.get(rid)
                    if run and run.state != RunState.CLOSED:
                        reports = service.ledger.reports(rid)
                        root_identity = service._identity(run)
                        sessions = [{"session_id": run.root_session_id, "status": run.state.value,
                                     "task_id": root_identity.get("task_id"),
                                     "agent_path": root_identity.get("agent_path"),
                                     "task_label": root_identity.get("task_label")}]
                        sessions.extend({"session_id": sid, "status": "observed", "task_id": sid,
                                         "task_label": sid} for sid in run.children)
                        events = [{"kind": item["kind"], "text": item["text"], "timestamp": item["created_at"], "session_id": item["session_id"], "evidence": json.loads(item["evidence"] or "[]")} for item in reports]
                        self._json({"run": service._run_payload(run), "contract": service.ledger.goal_contract(rid), "reports": reports, "tasks": service.ledger.tasks(rid), "events": events, "sessions": sessions})
                    elif run and run.state == RunState.CLOSED:
                        self._json({"error": "run_closed"}, 410)
                    else:
                        self._json({"error": "not_found"}, 404)
                elif parsed.path == "/api/events":
                    idx = int(parse_qs(parsed.query).get("since", ["0"])[0])
                    _, events = service.events_since(idx)
                    raw = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()
                    self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                else:
                    self._json({"error": "not_found"}, 404)

            def do_POST(self) -> None:
                try:
                    self._do_POST()
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

            def _do_POST(self) -> None:
                parsed = urlparse(self.path)
                body = self._body()
                if parsed.path == "/api/poll":
                    self._json({"events": service.poll_once()})
                    return
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "inject-review":
                    self._json(service.inject_review(parts[2]), 200)
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "close":
                    self._json(service.close(parts[2]), 200)
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "reports":
                    self._json(service.report(parts[2], str(body.get("kind", "report")), str(body.get("text", "")), evidence=body.get("evidence", [])), 200)
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "check-in":
                    self._json(service.request_check_in(parts[2]), 200)
                elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "receipt":
                    self._json(service.record_review_receipt(parts[2], body), 200)
                else:
                    self._json({"error": "not_found"}, 404)

            def log_message(self, *_args):
                return

        return ThreadingHTTPServer((host, port), Handler)

    def watch_forever(self, interval: float = 1.0) -> None:
        while not self._stop.wait(interval):
            try:
                self.poll_once()
                for run in self.ledger.list_runs(active_only=True):
                    if (self.ledger.has_report_kind(run.run_id, "check-in-request") and
                            not self.ledger.has_report_kind(run.run_id, "check-in-injected")):
                        self.inject_check_in(run.run_id)
                    if run.state == RunState.REVIEW_REQUIRED:
                        result = self.inject_review(run.run_id)
                        if result.get("ok"):
                            self._append_events([{"type": "review_injected", "run_id": run.run_id}])
            except Exception as exc:
                self._append_events([{"type": "watch_error", "detail": str(exc)}])

    def close_db(self) -> None:
        self.ledger.close_db()
