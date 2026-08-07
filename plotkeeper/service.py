from __future__ import annotations

import json
import os
import subprocess
import threading
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .ledger import Ledger
from .models import RunState, SessionObservation
from .sessions import SessionScanner


class PlotkeeperService:
    def __init__(self, *, ledger_path: str | os.PathLike[str] = "runtime/plotkeeper.sqlite3",
                 sessions_root: str | os.PathLike[str] = r"C:\Users\UltariumV3\.codex\sessions",
                 dashboard_url: str = "http://127.0.0.1:47831"):
        self.ledger = Ledger(ledger_path)
        self.dashboard_url = dashboard_url.rstrip("/")
        self.scanner = SessionScanner(sessions_root, self.ledger.watermark, self.ledger.set_watermark)
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
            run = self.ledger.by_root(obs.session_id)
            if obs.invoked_specswarm and obs.is_root:
                if run is None:
                    run = self.ledger.enroll(obs.session_id, obs.cwd, self.dashboard_url)
                    events.append({"type": "run_enrolled", "run_id": run.run_id, "session_id": obs.session_id})
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

    def current(self, cwd: str | None = None) -> dict[str, Any] | None:
        runs = self.ledger.list_runs(active_only=True)
        if cwd:
            normalized = os.path.normcase(os.path.abspath(cwd))
            matching = [r for r in runs if r.cwd and os.path.normcase(os.path.abspath(r.cwd)) == normalized]
            if matching:
                runs = matching
        run = runs[0] if runs else None
        return run.to_dict() if run else None

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
        web_root = Path(__file__).resolve().parent.parent / "web"

        class Handler(BaseHTTPRequestHandler):
            def _json(self, body: Any, status: int = 200) -> None:
                raw = json.dumps(body, sort_keys=True).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> dict[str, Any]:
                n = int(self.headers.get("Content-Length", "0"))
                try:
                    return json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return {}

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._json({"ok": True, "service": "plotkeeper"})
                elif parsed.path == "/favicon.ico":
                    self.send_response(HTTPStatus.NO_CONTENT); self.end_headers()
                elif parsed.path in {"/", "/dashboard", "/web/styles.css", "/web/app.js"}:
                    target = web_root / ("index.html" if parsed.path in {"/", "/dashboard"} else parsed.path.rsplit("/", 1)[-1])
                    raw = target.read_bytes()
                    content_type = "text/html; charset=utf-8" if target.suffix == ".html" else ("text/css; charset=utf-8" if target.suffix == ".css" else "text/javascript; charset=utf-8")
                    self.send_response(HTTPStatus.OK); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                elif parsed.path == "/api/runs":
                    self._json([r.to_dict() for r in service.ledger.list_runs()])
                elif parsed.path.startswith("/api/runs/"):
                    rid = parsed.path.rsplit("/", 1)[-1]
                    run = service.ledger.get(rid)
                    if run:
                        reports = service.ledger.reports(rid)
                        sessions = [{"session_id": run.root_session_id, "status": run.state.value, "task_id": None}]
                        sessions.extend({"session_id": sid, "status": "observed", "task_id": None} for sid in run.children)
                        events = [{"kind": item["kind"], "text": item["text"], "timestamp": item["created_at"], "session_id": item["session_id"], "evidence": json.loads(item["evidence"] or "[]")} for item in reports]
                        self._json({"run": run.to_dict(), "contract": service.ledger.goal_contract(rid), "reports": reports, "tasks": service.ledger.tasks(rid), "events": events, "sessions": sessions})
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
