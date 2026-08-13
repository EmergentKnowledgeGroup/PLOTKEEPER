from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock

from plotkeeper.ledger import Ledger
from plotkeeper.connector import DYNAMIC_PORT_MAX, DYNAMIC_PORT_MIN, ensure_connector, read_connector
from plotkeeper.browser_launcher import IsolatedBrowserLauncher
from plotkeeper.models import RunState
from plotkeeper.service import PlotkeeperService
from plotkeeper.sessions import parse_session


def line(timestamp, typ, payload):
    return json.dumps({"timestamp": timestamp, "type": typ, "payload": payload}) + "\n"


def _ensure_connector_worker(path: str, results) -> None:
    try:
        results.put(("ok", ensure_connector(path)))
    except Exception as exc:
        results.put(("error", type(exc).__name__, str(exc)))


class BackendTests(unittest.TestCase):
    def test_plan_reconstruction_resumes_exact_root_in_enrolled_cwd_once_and_hides_after_sync(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=td)
            run = service.ledger.enroll("019dc5bc-9c57-7aa0-a007-18250d608ad3", str(root), service.dashboard_url)
            calls = []
            result = service.reconstruct_plan(run.run_id, runner=lambda args, **kwargs: calls.append((args, kwargs)) or mock.Mock(returncode=0))
            self.assertTrue(result["ok"])
            self.assertEqual(calls[0][0][2:4], ["resume", run.root_session_id])
            self.assertEqual(calls[0][1]["cwd"], str(root.resolve()))
            prompt = calls[0][0][4]
            for phrase in ("Do not guess by filename", "Verify artifact identity", "sync-plan", "Read back"):
                self.assertIn(phrase, prompt)
            self.assertTrue(service.reconstruct_plan(run.run_id, runner=lambda *_a, **_k: self.fail("must be idempotent"))["already_requested"])
            service.ledger.replace_tasks(run.run_id, [{"task_id": "T001", "title": "Synced", "status": "pending"}])
            self.assertEqual(service.reconstruct_plan(run.run_id)["error"], "plan_already_synced")
            service.close_db()

    def test_isolated_browser_launcher_uses_dedicated_profile_and_app_window(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            executable = Path(td) / "msedge.exe"
            executable.write_bytes(b"")
            launcher = IsolatedBrowserLauncher(
                Path(td) / "profile",
                candidates=lambda: [executable],
                process_launcher=lambda args, **kwargs: calls.append((args, kwargs)) or object(),
                fallback=lambda *_args, **_kwargs: self.fail("fallback should not run"),
            )
            url = "http://127.0.0.1:53327/?run_id=exact&session_id=root"
            self.assertTrue(launcher(url, new=1))
            args, kwargs = calls[0]
            self.assertIn(f"--app={url}", args)
            self.assertIn("--new-window", args)
            self.assertIn(f"--user-data-dir={Path(td) / 'profile'}", args)
            self.assertEqual(kwargs["cwd"], td)

    def test_browser_profile_root_is_independent_of_custom_ledger_location(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            sessions.mkdir()
            profile_root = base / "configured-root"
            service = PlotkeeperService(
                ledger_path=base / "arbitrary" / "state.sqlite",
                sessions_root=sessions,
                profile_root=profile_root,
            )
            try:
                self.assertEqual(
                    service.browser_opener.profile_dir.resolve(),
                    (profile_root / "runtime" / "plotkeeper-browser-profile").resolve(),
                )
            finally:
                service.close_db()

    def test_private_connector_is_persisted_and_malformed_records_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "runtime" / "plotkeeper-connector.json"
            first = ensure_connector(path)
            second = ensure_connector(path)
            self.assertEqual(first, second)
            self.assertEqual(first["host"], "127.0.0.1")
            self.assertGreaterEqual(first["port"], DYNAMIC_PORT_MIN)
            self.assertLessEqual(first["port"], DYNAMIC_PORT_MAX)
            path.write_text('{"host":"0.0.0.0","port":80}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_connector(path)

    def test_private_connector_first_creation_is_atomic_across_processes(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "runtime" / "plotkeeper-connector.json")
            context = multiprocessing.get_context("spawn")
            results = context.Queue()
            processes = [context.Process(target=_ensure_connector_worker, args=(path, results)) for _ in range(2)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
                if process.is_alive():
                    process.terminate()
                    process.join()
                self.assertEqual(process.exitcode, 0)
            values = [results.get(timeout=2) for _ in processes]
            self.assertTrue(all(value[0] == "ok" for value in values), values)
            self.assertEqual(values[0][1], values[1][1])
            self.assertEqual(values[0][1], read_connector(path))

    def test_private_connector_rejects_unsupported_hard_link_without_overwriting_winner(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "runtime" / "plotkeeper-connector.json"
            with mock.patch("plotkeeper.connector.os.link", side_effect=OSError("operation not supported")):
                with self.assertRaisesRegex(RuntimeError, "atomic create-only"):
                    ensure_connector(path)
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_running_reconstruction_process_is_reaped_by_daemon(self):
        class RunningProcess:
            returncode = None

            def __init__(self):
                self.reaped = threading.Event()
                self.wait_was_daemon = None

            def poll(self):
                return None

            def wait(self):
                self.wait_was_daemon = threading.current_thread().daemon
                self.reaped.set()
                return 0

        process = RunningProcess()
        self.assertIsNone(PlotkeeperService._runner_returncode(process))
        self.assertTrue(process.reaped.wait(2))
        self.assertTrue(process.wait_was_daemon)

    def test_plan_reconstruction_releases_lock_and_retries_after_immediate_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=td)
            run = service.ledger.enroll("019dc5bc-9c57-7aa0-a007-18250d608ad3", str(root), service.dashboard_url)
            started = threading.Event()
            release = threading.Event()

            def blocking_runner(*_args, **_kwargs):
                started.set()
                release.wait(2)
                return mock.Mock(returncode=0)

            worker = threading.Thread(target=service.reconstruct_plan, args=(run.run_id,), kwargs={"runner": blocking_runner})
            worker.start()
            self.assertTrue(started.wait(2))
            duplicate = service.reconstruct_plan(run.run_id, runner=lambda *_args, **_kwargs: self.fail("duplicate runner"))
            self.assertTrue(duplicate["already_requested"])
            release.set()
            worker.join(2)
            self.assertFalse(worker.is_alive())

            class FailedProcess:
                returncode = None

                def __init__(self):
                    self.reaped = False

                def poll(self):
                    return 23

                def wait(self, timeout=0):
                    self.reaped = True
                    return 23

            failed = FailedProcess()
            service2 = PlotkeeperService(ledger_path=Path(td) / "ledger-2.sqlite", sessions_root=td)
            run2 = service2.ledger.enroll("019dc5bc-9c57-7aa0-a007-18250d608ad4", str(root), service2.dashboard_url)
            first = service2.reconstruct_plan(run2.run_id, runner=lambda *_args, **_kwargs: failed)
            self.assertEqual(first["error"], "reconstruction_injection_failed")
            self.assertEqual(first["returncode"], 23)
            self.assertTrue(failed.reaped)
            second = service2.reconstruct_plan(run2.run_id, runner=lambda *_args, **_kwargs: mock.Mock(returncode=0))
            self.assertTrue(second["ok"])
            service.close_db()
            service2.close_db()

    def test_popout_opens_only_exact_same_origin_dashboard_path(self):
        with tempfile.TemporaryDirectory() as td:
            opened = []
            service = PlotkeeperService(
                ledger_path=Path(td) / "ledger.sqlite",
                sessions_root=td,
                browser_opener=lambda url, *, new=0: opened.append((url, new)) or True,
            )
            server = service.serve("127.0.0.1", 0)
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            try:
                body = json.dumps({"path": "/?run_id=exact&session_id=root"}).encode()
                request = Request(origin + "/api/open-browser", data=body, headers={"Content-Type": "application/json", "Origin": origin}, method="POST")
                with urlopen(request, timeout=2) as response:
                    result = json.load(response)
                self.assertTrue(result["ok"])
                self.assertEqual(opened, [(origin + "/?run_id=exact&session_id=root", 1)])
                attacks = [
                    ({"path": "https://example.com/"}, origin),
                    ({"path": "/api/runs"}, origin),
                    ({"path": "/?run_id=evil"}, "https://evil.example"),
                ]
                for payload, request_origin in attacks:
                    bad = Request(origin + "/api/open-browser", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Origin": request_origin}, method="POST")
                    with self.assertRaises(HTTPError):
                        urlopen(bad, timeout=2)
                self.assertEqual(len(opened), 1)
            finally:
                server.shutdown()
                server.server_close()
                service.close_db()

    def test_closed_root_enrolls_one_linked_successor_and_stays_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            first = ledger.enroll("root-original", td, "http://pk", "task-1")
            self.assertIsNotNone(first)
            assert first is not None
            self.assertTrue(ledger.mark_review_required(first.run_id))
            self.assertFalse(ledger.record_receipt(first.run_id, {"terminal": True, "injected": True, "verdict": "PASS", "open_items": 0}))
            self.assertTrue(ledger.mark_review_pending(first.run_id))
            ledger.replace_tasks(first.run_id, [
                {"task_id": "T001", "title": "implementation", "status": "completed"},
                {"task_id": "T002", "title": "independent review receipt", "status": "pending"},
            ])
            contract_path = Path(td) / "contract.json"
            contract_path.write_text("{}", encoding="utf-8")
            ledger.set_goal_contract(first.run_id, str(contract_path), {"id": "C1", "user_goal": "goal", "contract_hash": "h"})
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED"}), encoding="utf-8")
            self.assertFalse(ledger.finalize_review(first.run_id, {"verdict": "PASS"}))
            with mock.patch("plotkeeper.ledger.subprocess.run", return_value=mock.Mock(returncode=0)) as validator:
                self.assertTrue(ledger.finalize_review(first.run_id, str(receipt_path)))
            command = validator.call_args.args[0]
            self.assertIn("validate_review_receipt.py", command[1])
            self.assertTrue(Path(command[2]).samefile(contract_path))
            self.assertTrue(Path(command[3]).samefile(receipt_path))
            self.assertIn("--repo-root", command)
            before = ledger.get(first.run_id)
            self.assertEqual(before.state, RunState.CLOSED)
            successor = ledger.enroll("root-followup", td, "http://pk", "task-1")
            self.assertIsNotNone(successor)
            assert successor is not None
            self.assertNotEqual(successor.run_id, first.run_id)
            self.assertEqual(successor.state, RunState.OPEN)
            self.assertEqual(successor.predecessor_run_id, first.run_id)
            self.assertEqual(ledger.enroll("another-session", td, "http://pk", "task-1").run_id, successor.run_id)
            self.assertEqual(len([r for r in ledger.list_runs() if r.state != RunState.CLOSED]), 1)
            self.assertEqual(ledger.add_report(first.run_id, "late", "must reject"), 0)
            ledger.attach_child(first.run_id, "late-child")
            self.assertEqual(ledger.get(first.run_id).children, ())
            self.assertEqual(ledger.get(first.run_id).to_dict()["successor_run_id"], successor.run_id)
            self.assertEqual(ledger.get(first.run_id).state, before.state)
            ledger.close_db()

    def test_legacy_unique_root_schema_migrates_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy.sqlite"
            db = __import__("sqlite3").connect(path)
            db.executescript("""
                CREATE TABLE runs (
                    run_id TEXT PRIMARY KEY, root_session_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL, cwd TEXT, dashboard_url TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    review_injected_at TEXT, review_receipt TEXT, closed_at TEXT
                );
                CREATE TABLE children (run_id TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(run_id, session_id), FOREIGN KEY(run_id) REFERENCES runs(run_id));
                CREATE TABLE reports (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, session_id TEXT, kind TEXT NOT NULL, text TEXT NOT NULL, evidence TEXT, created_at TEXT NOT NULL);
                CREATE TABLE tasks (run_id TEXT NOT NULL, task_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, parent_task_id TEXT, workstream TEXT, source TEXT, ordinal INTEGER NOT NULL, PRIMARY KEY(run_id, task_id));
                CREATE TABLE goal_contracts (run_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL, user_goal TEXT NOT NULL, contract_hash TEXT, baseline_sha TEXT, payload TEXT NOT NULL, synced_at TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES runs(run_id));
                CREATE TABLE watermarks (path TEXT PRIMARY KEY, byte_offset INTEGER NOT NULL);
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", ("legacy-run", "legacy-root", "CLOSED", td, "http://pk", "2026-01-01", "2026-01-02", None, '{"verdict":"PASS"}', "2026-01-02"))
            db.execute("INSERT INTO children VALUES (?,?)", ("legacy-run", "legacy-child"))
            db.execute("INSERT INTO reports(run_id,session_id,kind,text,evidence,created_at) VALUES (?,?,?,?,?,?)", ("legacy-run", "legacy-root", "claim", "preserve", "[]", "2026-01-02"))
            db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", ("legacy-run", "T1", "Keep", "completed", "owner", None, "ws", "plan", 0))
            db.execute("INSERT INTO goal_contracts VALUES (?,?,?,?,?,?,?,?,?)", ("legacy-run", "C1", "contract.json", "ACTIVE", "goal", "hash", "base", "{}", "2026-01-02"))
            db.commit()
            db.close()
            ledger = Ledger(path)
            self.assertEqual(len(ledger.list_runs()), 1)
            historical = ledger.by_root("legacy-root")
            self.assertEqual(historical.run_id, "legacy-run")
            self.assertEqual(historical.children, ("legacy-child",))
            for dependent in ("children", "goal_contracts"):
                foreign_keys = [tuple(item) for item in ledger.db.execute(f"PRAGMA foreign_key_list({dependent})")]
                self.assertTrue(foreign_keys)
                self.assertEqual(foreign_keys[0][2], "runs")
            self.assertEqual(ledger.reports("legacy-run")[0]["text"], "preserve")
            self.assertEqual(ledger.tasks("legacy-run")[0]["title"], "Keep")
            successor = ledger.enroll("legacy-followup", td, "http://pk", historical.canonical_root_id)
            self.assertEqual(successor.predecessor_run_id, historical.run_id)
            ledger.close_db()

    def test_packaged_dashboard_is_served(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            server = service.serve("127.0.0.1", 0)
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:
                    body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                self.assertIn("PLOTKEEPER", body)
            finally:
                server.shutdown()
                server.server_close()
                service.close_db()

    def test_handler_errors_return_non_empty_response_instead_of_empty_socket(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            server = service.serve("127.0.0.1", 0)
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(Exception) as caught:
                    urlopen(f"http://127.0.0.1:{server.server_port}/api/events?since=not-a-number", timeout=2)
                response = caught.exception
                self.assertEqual(getattr(response, "status", None), 500)
                self.assertIn("Plotkeeper error", response.read().decode())
            finally:
                server.shutdown()
                server.server_close()
                service.close_db()

    def test_parser_identifies_root_invocation_and_terminal_events(self):
        obs = parse_session("root.jsonl", [
            line("2026-08-07T00:00:00Z", "session_meta", {"id": "root-1", "cwd": "Z:\\demo"}),
            line("2026-08-07T00:00:01Z", "message", {"role": "user", "content": [{"type": "input_text", "text": "$specswarm run"}]}),
            line("2026-08-07T00:00:02Z", "event_msg", {"type": "task_complete"}),
            line("2026-08-07T00:00:03Z", "message", {"role": "assistant", "content": "PK:REVIEW_RESULT run_id=run-1 verdict=PASS open_items=0 receipt_locator=Z:\\review\\receipt.json"}),
        ])
        self.assertTrue(obs and obs.is_root and obs.invoked_specswarm and obs.root_complete)
        self.assertEqual(obs.review_results[0]["receipt_locator"], "Z:\\review\\receipt.json")

    def test_historical_invocation_is_excluded_by_first_activation_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            source = root / "root.jsonl"
            source.write_text(line("1", "session_meta", {"id": "root-1", "cwd": td}) + line("2", "message", {"role": "user", "content": "$specswarm"}), encoding="utf-8")
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            self.assertEqual(service.poll_once(), [])
            with source.open("a", encoding="utf-8") as handle:
                handle.write(line("3", "event_msg", {"type": "task_complete"}))
            self.assertEqual(service.poll_once(), [])
            with source.open("a", encoding="utf-8") as handle:
                handle.write(line("4", "message", {"role": "user", "content": "run specswarm now"}))
            events = service.poll_once()
            self.assertEqual([e["type"] for e in events], ["run_enrolled"])
            service.close_db()

    def test_close_requires_injected_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            source = root / "root.jsonl"
            source.write_text(line("1", "session_meta", {"id": "root-1", "cwd": td}), encoding="utf-8")
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            with source.open("a", encoding="utf-8") as handle:
                handle.write(line("2", "message", {"role": "user", "content": "$specswarm"}) +
                             line("3", "message", {"role": "assistant", "content": "PK:GOAL_COMPLETE_REQUEST"}) +
                             line("4", "event_msg", {"type": "task_complete"}))
            service.poll_once()
            run = service.ledger.list_runs()[0]
            self.assertEqual(run.state, RunState.REVIEW_REQUIRED)
            self.assertFalse(service.close(run.run_id)["ok"])
            self.assertEqual(service.inject_review(run.run_id, runner=lambda _args, **_kwargs: 1)["error"], "injection_failed")
            self.assertEqual(service.ledger.get(run.run_id).state, RunState.REVIEW_REQUIRED)
            self.assertTrue(service.inject_review(run.run_id, runner=lambda _args, **_kwargs: 0)["ok"])
            self.assertFalse(service.close(run.run_id)["ok"])
            self.assertFalse(service.record_review_receipt(run.run_id, {"terminal": True, "injected": True, "verdict": "FAIL", "open_items": 1})["ok"])
            contract_path = Path(td) / "contract.json"
            contract_path.write_text(json.dumps({"id": "C1", "user_goal": "goal", "contract_hash": "contract-hash"}), encoding="utf-8")
            service.ledger.set_goal_contract(run.run_id, str(contract_path), {"id": "C1", "user_goal": "goal", "contract_hash": "contract-hash"})
            service.ledger.replace_tasks(run.run_id, [
                {"task_id": "T001", "title": "implementation", "status": "completed"},
                {"task_id": "T002", "title": "independent review receipt", "status": "pending"},
            ])
            receipt_path = Path(td) / "receipt.json"
            receipt = {"verdict": "PASS", "phase": "VALIDATED", "review_receipt_hash": "receipt-hash"}
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            self.assertFalse(service.record_review_receipt(run.run_id, {"terminal": True, "injected": True, "verdict": "PASS", "open_items": 0})["ok"])
            with mock.patch("plotkeeper.ledger.subprocess.run", return_value=mock.Mock(returncode=0)):
                self.assertTrue(service.record_review_receipt(run.run_id, {"terminal": True, "injected": True, "verdict": "PASS", "open_items": 0, "receipt_locator": str(receipt_path)})["ok"])
            self.assertFalse(service.close(run.run_id)["ok"])
            self.assertEqual(service.ledger.get(run.run_id).state, RunState.CLOSED)
            child = root / "child.jsonl"
            child.write_text(line("5", "session_meta", {"id": "child-1", "parent_session_id": "root-1"}) + line("6", "message", {"role": "assistant", "content": "claim: late"}), encoding="utf-8")
            service.poll_once()
            self.assertEqual(service.ledger.get(run.run_id).children, ())
            reports = service.ledger.reports(run.run_id)
            self.assertEqual([item["kind"] for item in reports], ["goal_complete"])
            service.close_db()

    def test_atomic_review_failure_rolls_back_task_receipt_and_run(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            run = ledger.enroll("root-1", td, "http://pk")
            assert run is not None
            ledger.replace_tasks(run.run_id, [
                {"task_id": "T001", "title": "implementation", "status": "completed"},
                {"task_id": "T002", "title": "independent review receipt", "status": "pending"},
            ])
            ledger.mark_review_pending(run.run_id)
            contract_path = Path(td) / "contract.json"
            contract_path.write_text("{}", encoding="utf-8")
            ledger.set_goal_contract(run.run_id, str(contract_path), {"id": "C1", "user_goal": "goal", "contract_hash": "h"})
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED"}), encoding="utf-8")
            def fail(_point):
                if _point == "run_closed":
                    raise RuntimeError("injected")
            with mock.patch("plotkeeper.ledger.subprocess.run", return_value=mock.Mock(returncode=0)):
                self.assertFalse(ledger.finalize_review(run.run_id, str(receipt_path), failure_hook=fail))
            self.assertEqual(ledger.get(run.run_id).state, RunState.REVIEW_PENDING)
            self.assertIsNone(ledger.get(run.run_id).review_receipt)
            self.assertEqual(ledger.tasks(run.run_id)[1]["status"], "pending")
            ledger.close_db()

    def test_direct_ledger_validator_failure_rolls_back_before_task_transition(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            run = ledger.enroll("root-1", td, "http://pk")
            assert run is not None
            ledger.replace_tasks(run.run_id, [
                {"task_id": "T001", "title": "implementation", "status": "completed"},
                {"task_id": "T002", "title": "independent review receipt", "status": "pending"},
            ])
            ledger.mark_review_pending(run.run_id)
            contract_path = Path(td) / "contract.json"
            contract_path.write_text("{}", encoding="utf-8")
            ledger.set_goal_contract(run.run_id, str(contract_path), {"id": "C1", "user_goal": "goal", "contract_hash": "h"})
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED"}), encoding="utf-8")
            self.assertFalse(ledger.finalize_review(run.run_id, ""))
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "CLOSED"}), encoding="utf-8")
            with mock.patch("plotkeeper.ledger.subprocess.run", return_value=mock.Mock(returncode=0)):
                self.assertFalse(ledger.finalize_review(run.run_id, str(receipt_path)))
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED"}), encoding="utf-8")
            with mock.patch("plotkeeper.ledger.subprocess.run", return_value=mock.Mock(returncode=2)):
                self.assertFalse(ledger.finalize_review(run.run_id, str(receipt_path)))
            current = ledger.get(run.run_id)
            self.assertEqual(current.state, RunState.REVIEW_PENDING)
            self.assertIsNone(current.review_receipt)
            self.assertEqual(ledger.tasks(run.run_id)[1]["status"], "pending")
            ledger.close_db()

    def test_direct_ledger_rejects_receipt_mutation_during_validator(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            run = ledger.enroll("root-1", td, "http://pk")
            assert run is not None
            ledger.replace_tasks(run.run_id, [
                {"task_id": "T001", "title": "implementation", "status": "completed"},
                {"task_id": "T002", "title": "independent review receipt", "status": "pending"},
            ])
            ledger.mark_review_pending(run.run_id)
            contract_path = Path(td) / "contract.json"
            contract_path.write_text("{}", encoding="utf-8")
            ledger.set_goal_contract(run.run_id, str(contract_path), {"id": "C1", "user_goal": "goal", "contract_hash": "h"})
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED"}), encoding="utf-8")
            def mutate(*_args, **_kwargs):
                receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED", "tampered": True}), encoding="utf-8")
                return mock.Mock(returncode=0)
            with mock.patch("plotkeeper.ledger.subprocess.run", side_effect=mutate):
                self.assertFalse(ledger.finalize_review(run.run_id, str(receipt_path)))
            self.assertEqual(ledger.get(run.run_id).state, RunState.REVIEW_PENDING)
            self.assertIsNone(ledger.get(run.run_id).review_receipt)
            self.assertEqual(ledger.tasks(run.run_id)[1]["status"], "pending")
            ledger.close_db()

    def test_atomic_review_rejects_multiple_pending_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            run = ledger.enroll("root-1", td, "http://pk")
            assert run is not None
            ledger.replace_tasks(run.run_id, [
                {"task_id": "T001", "title": "independent review receipt", "status": "pending"},
                {"task_id": "T002", "title": "another pending task", "status": "pending"},
            ])
            ledger.mark_review_pending(run.run_id)
            contract_path = Path(td) / "contract.json"
            contract_path.write_text("{}", encoding="utf-8")
            ledger.set_goal_contract(run.run_id, str(contract_path), {"id": "C1", "user_goal": "goal", "contract_hash": "h"})
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps({"verdict": "PASS", "phase": "VALIDATED"}), encoding="utf-8")
            with mock.patch("plotkeeper.ledger.subprocess.run", return_value=mock.Mock(returncode=0)):
                self.assertFalse(ledger.finalize_review(run.run_id, str(receipt_path)))
            self.assertEqual(ledger.get(run.run_id).state, RunState.REVIEW_PENDING)
            self.assertIsNone(ledger.get(run.run_id).review_receipt)
            ledger.close_db()

    def test_child_meta_prefers_child_id_over_root_session_id(self):
        obs = parse_session("child.jsonl", [
            line("1", "session_meta", {"id": "child-1", "session_id": "root-1", "parent_thread_id": "root-1"}),
        ])
        self.assertEqual(obs.session_id, "child-1")
        self.assertEqual(obs.parent_session_id, "root-1")

    def test_message_id_does_not_overwrite_session_or_canonical_identity(self):
        obs = parse_session("root.jsonl", [
            line("1", "session_meta", {"id": "session-1", "cwd": "Z:\\demo"}),
            line("2", "message", {"id": "message-1", "role": "user", "content": "$specswarm"}),
        ])
        self.assertEqual(obs.session_id, "session-1")
        self.assertEqual(obs.canonical_root_id, "session:session-1")

    def test_sync_plan_extracts_checkbox_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            run = service.ledger.enroll("root-1", td, service.dashboard_url)
            plan = Path(td) / "CHECKLIST.md"
            plan.write_text("- [ ] Preserve v1 route\n- [x] Add v2 adapter\n", encoding="utf-8")
            result = service.sync_plan(run.run_id, [str(plan)])
            self.assertEqual(result["count"], 2)
            self.assertEqual([t["status"] for t in service.ledger.tasks(run.run_id)], ["pending", "completed"])
            service.close_db()

    def test_injected_resumes_preserve_enrolled_cross_repository_identity(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            plotkeeper_repo = base / "Plotkeeper"
            moonmarket_repo = base / "MoonMarket"
            sessions = plotkeeper_repo / "sessions"
            sessions.mkdir(parents=True)
            moonmarket_repo.mkdir()
            __import__("subprocess").run(["git", "init", "--quiet", str(moonmarket_repo)], check=True)
            service = PlotkeeperService(ledger_path=plotkeeper_repo / "ledger.sqlite", sessions_root=sessions)
            run = service.ledger.enroll("moonmarket-root", str(moonmarket_repo), service.dashboard_url)
            assert run is not None
            service.ledger.mark_review_required(run.run_id)
            launches = []
            probe = (
                "import json, os, pathlib, subprocess; "
                "root=subprocess.run(['git','rev-parse','--show-toplevel'],capture_output=True,text=True,check=True).stdout.strip(); "
                "print(json.dumps({'cwd':os.getcwd(),'workspace_root':root,'project':pathlib.Path(root).name}))"
            )

            def capture(args, *, cwd):
                result = service._run_codex([sys.executable, "-c", probe], cwd=cwd)
                launches.append({"args": args, "child": json.loads(result.stdout)})
                return result

            self.assertNotEqual(Path.cwd().resolve(), moonmarket_repo.resolve())
            self.assertTrue(service.inject_review(run.run_id, runner=capture)["ok"])
            # Return to an open state only inside this disposable fixture so
            # the same enrolled run can exercise the check-in path.
            service.ledger.mark_review_required(run.run_id)
            self.assertTrue(service.inject_check_in(run.run_id, runner=capture)["ok"])

            self.assertEqual(len(launches), 2)
            for launch in launches:
                child = launch["child"]
                self.assertEqual(Path(child["cwd"]).resolve(), moonmarket_repo.resolve())
                self.assertEqual(Path(child["workspace_root"]).resolve(), moonmarket_repo.resolve())
                self.assertEqual(child["project"], "MoonMarket")
                self.assertNotEqual(Path(child["cwd"]).resolve(), Path.cwd().resolve())
                self.assertEqual(launch["args"][:4], ["codex.exe", "exec", "resume", "moonmarket-root"])
            service.close_db()

    def test_injected_resumes_fail_closed_for_invalid_enrolled_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sessions = base / "sessions"
            sessions.mkdir()
            service = PlotkeeperService(ledger_path=base / "ledger.sqlite", sessions_root=sessions)
            invalid_values = [None, "relative/path", str(base / "missing"), str(base / "not-a-directory.txt")]
            (base / "not-a-directory.txt").write_text("x", encoding="utf-8")
            for index, invalid in enumerate(invalid_values):
                run = service.ledger.enroll(f"root-{index}", invalid, service.dashboard_url, f"task-{index}")
                assert run is not None
                service.ledger.mark_review_required(run.run_id)
                runner = mock.Mock()
                before = service.ledger.get(run.run_id)
                self.assertEqual(service.inject_review(run.run_id, runner=runner), {"ok": False, "error": "run_cwd_invalid"})
                self.assertEqual(service.ledger.get(run.run_id).state, before.state)
                self.assertEqual(service.inject_check_in(run.run_id, runner=runner), {"ok": False, "error": "run_cwd_invalid"})
                self.assertFalse(service.ledger.has_report_kind(run.run_id, "check-in-injected"))
                runner.assert_not_called()
            service.close_db()

    def test_sync_plan_persists_goal_contract_and_closeout_invokes_review_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            run = service.ledger.enroll("root-1", td, service.dashboard_url)
            plan = Path(td) / "CHECKLIST.md"
            plan.write_text("- [ ] Ship safely\n", encoding="utf-8")
            contract = Path(td) / "contract.json"
            contract.write_text(json.dumps({"id": "PROD-1", "status": "ACTIVE", "user_goal": "Preserve v1 while adding v2", "contract_hash": "abc", "baseline": {"sha": "deadbeef"}, "invariants": ["v1 remains live"]}), encoding="utf-8")
            result = service.sync_plan(run.run_id, [str(plan)], str(contract))
            self.assertTrue(result["ok"])
            self.assertEqual(service.ledger.goal_contract(run.run_id)["user_goal"], "Preserve v1 while adding v2")
            prompt = service.review_prompt(run.run_id)
            self.assertIn("$production-goal-review", prompt)
            self.assertIn("contract PROD-1", prompt)
            self.assertIn("entire Plotkeeper run", prompt)
            service.close_db()

    def test_partial_jsonl_line_is_not_lost(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            source = root / "root.jsonl"
            source.write_text("", encoding="utf-8")
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            complete = line("1", "message", {"role": "user", "content": "$specswarm"})
            source.write_text(line("0", "session_meta", {"id": "root-1", "cwd": td}) + complete[:-2], encoding="utf-8")
            self.assertEqual(service.poll_once(), [])
            with source.open("a", encoding="utf-8") as handle: handle.write(complete[-2:])
            self.assertEqual(service.poll_once()[0]["type"], "run_enrolled")
            service.close_db()

    def test_independent_root_attaches_by_run_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            run = service.ledger.enroll("spec-root", td, service.dashboard_url)
            source = root / "implementation.jsonl"
            source.write_text(line("1", "session_meta", {"id": "implementation-root", "cwd": td}) + line("2", "message", {"role": "assistant", "content": f"Plotkeeper-Run-ID: {run.run_id}"}), encoding="utf-8")
            service.poll_once()
            self.assertIn("implementation-root", service.ledger.get(run.run_id).children)
            service.close_db()

    def test_child_session_maps_to_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            r = root / "root.jsonl"
            r.write_text(line("1", "session_meta", {"id": "root-1", "cwd": td}) + line("2", "message", {"role": "user", "content": "$specswarm"}), encoding="utf-8")
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            service.poll_once()
            with r.open("a", encoding="utf-8") as handle:
                handle.write(line("2", "message", {"role": "user", "content": "$specswarm"}))
            service.poll_once()
            child = root / "child.jsonl"
            child.write_text(line("3", "session_meta", {"id": "child-1", "parent_session_id": "root-1"}) + line("4", "message", {"role": "assistant", "content": "claim: child evidence https://example.test/x"}), encoding="utf-8")
            events = service.poll_once()
            run = service.ledger.list_runs()[0]
            self.assertIn("child-1", run.children)
            self.assertEqual(service.ledger.reports(run.run_id)[0]["kind"], "claim")
            self.assertTrue(any(e["type"] == "child_attached" for e in events))
            service.close_db()

    def test_canonical_root_task_deduplicates_worktree_variants_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            first = root / "root-a.jsonl"
            first.write_text(line("1", "session_meta", {"id": "session-a", "task_id": "task-42", "cwd": td}) +
                             line("2", "message", {"role": "user", "content": "$specswarm"}), encoding="utf-8")
            self.assertEqual([event["type"] for event in service.poll_once()], ["run_enrolled"])
            run = service.ledger.list_runs()[0]
            variant = root / "root-b.jsonl"
            variant.write_text(line("3", "session_meta", {"id": "session-b", "task_id": "task-42", "cwd": str(Path(td) / "worktree")}) +
                               line("4", "message", {"role": "assistant", "content": "claim: variant history"}), encoding="utf-8")
            events = service.poll_once()
            self.assertEqual(len(service.ledger.list_runs()), 1)
            self.assertIn("session-b", service.ledger.get(run.run_id).children)
            self.assertTrue(any(event["type"] == "root_variant_attached" for event in events))
            self.assertTrue(any(item["text"] == "variant history" for item in service.ledger.reports(run.run_id)))
            service.close_db()


if __name__ == "__main__":
    unittest.main()
