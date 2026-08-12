from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

from plotkeeper.ledger import Ledger
from plotkeeper.models import RunState
from plotkeeper.service import PlotkeeperService
from plotkeeper.sessions import parse_session


def line(timestamp, typ, payload):
    return json.dumps({"timestamp": timestamp, "type": typ, "payload": payload}) + "\n"


class BackendTests(unittest.TestCase):
    def test_closed_root_enrolls_one_linked_successor_and_stays_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Ledger(Path(td) / "ledger.sqlite")
            first = ledger.enroll("root-original", td, "http://pk", "task-1")
            self.assertIsNotNone(first)
            assert first is not None
            self.assertTrue(ledger.mark_review_required(first.run_id))
            self.assertTrue(ledger.record_receipt(first.run_id, {"terminal": True, "injected": True, "verdict": "PASS", "open_items": 0}))
            self.assertTrue(ledger.close(first.run_id))
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
            db.commit(); db.close()
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
            root = Path(td) / "sessions"; root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            server = service.serve("127.0.0.1", 0)
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:
                    body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("PLOTKEEPER", body)
            finally:
                server.shutdown()
                server.server_close()
                service.close_db()

    def test_handler_errors_return_non_empty_response_instead_of_empty_socket(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"; root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            server = service.serve("127.0.0.1", 0)
            thread = __import__("threading").Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                with self.assertRaises(Exception) as caught:
                    urlopen(f"http://127.0.0.1:{server.server_port}/api/events?since=not-a-number", timeout=2)
                response = caught.exception
                self.assertEqual(getattr(response, "status", None), 500)
                self.assertIn("Plotkeeper error", response.read().decode())
            finally:
                server.shutdown(); server.server_close(); service.close_db()

    def test_parser_identifies_root_invocation_and_terminal_events(self):
        obs = parse_session("root.jsonl", [
            line("2026-08-07T00:00:00Z", "session_meta", {"id": "root-1", "cwd": "Z:\\demo"}),
            line("2026-08-07T00:00:01Z", "message", {"role": "user", "content": [{"type": "input_text", "text": "$specswarm run"}]}),
            line("2026-08-07T00:00:02Z", "event_msg", {"type": "task_complete"}),
        ])
        self.assertTrue(obs and obs.is_root and obs.invoked_specswarm and obs.root_complete)

    def test_historical_invocation_is_excluded_by_first_activation_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"; root.mkdir()
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
            root = Path(td) / "sessions"; root.mkdir()
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
            self.assertEqual(service.inject_review(run.run_id, runner=lambda _args: 1)["error"], "injection_failed")
            self.assertEqual(service.ledger.get(run.run_id).state, RunState.REVIEW_REQUIRED)
            self.assertTrue(service.inject_review(run.run_id, runner=lambda _args: 0)["ok"])
            self.assertFalse(service.close(run.run_id)["ok"])
            self.assertFalse(service.record_review_receipt(run.run_id, {"terminal": True, "injected": True, "verdict": "FAIL", "open_items": 1})["ok"])
            self.assertTrue(service.record_review_receipt(run.run_id, {"terminal": True, "injected": True, "verdict": "PASS", "open_items": 0})["ok"])
            self.assertTrue(service.close(run.run_id)["ok"])
            self.assertEqual(service.ledger.get(run.run_id).state, RunState.CLOSED)
            child = root / "child.jsonl"
            child.write_text(line("5", "session_meta", {"id": "child-1", "parent_session_id": "root-1"}) + line("6", "message", {"role": "assistant", "content": "claim: late"}), encoding="utf-8")
            service.poll_once()
            self.assertEqual(service.ledger.get(run.run_id).children, ())
            reports = service.ledger.reports(run.run_id)
            self.assertEqual([item["kind"] for item in reports], ["goal_complete"])
            service.close_db()

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
            root = Path(td) / "sessions"; root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            run = service.ledger.enroll("root-1", td, service.dashboard_url)
            plan = Path(td) / "CHECKLIST.md"
            plan.write_text("- [ ] Preserve v1 route\n- [x] Add v2 adapter\n", encoding="utf-8")
            result = service.sync_plan(run.run_id, [str(plan)])
            self.assertEqual(result["count"], 2)
            self.assertEqual([t["status"] for t in service.ledger.tasks(run.run_id)], ["pending", "completed"])
            service.close_db()

    def test_sync_plan_persists_goal_contract_and_closeout_invokes_review_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"; root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            run = service.ledger.enroll("root-1", td, service.dashboard_url)
            plan = Path(td) / "CHECKLIST.md"; plan.write_text("- [ ] Ship safely\n", encoding="utf-8")
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
            root = Path(td) / "sessions"; root.mkdir()
            source = root / "root.jsonl"; source.write_text("", encoding="utf-8")
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            complete = line("1", "message", {"role": "user", "content": "$specswarm"})
            source.write_text(line("0", "session_meta", {"id": "root-1", "cwd": td}) + complete[:-2], encoding="utf-8")
            self.assertEqual(service.poll_once(), [])
            with source.open("a", encoding="utf-8") as handle: handle.write(complete[-2:])
            self.assertEqual(service.poll_once()[0]["type"], "run_enrolled")
            service.close_db()

    def test_independent_root_attaches_by_run_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"; root.mkdir()
            service = PlotkeeperService(ledger_path=Path(td) / "ledger.sqlite", sessions_root=root)
            run = service.ledger.enroll("spec-root", td, service.dashboard_url)
            source = root / "implementation.jsonl"
            source.write_text(line("1", "session_meta", {"id": "implementation-root", "cwd": td}) + line("2", "message", {"role": "assistant", "content": f"Plotkeeper-Run-ID: {run.run_id}"}), encoding="utf-8")
            service.poll_once()
            self.assertIn("implementation-root", service.ledger.get(run.run_id).children)
            service.close_db()

    def test_child_session_maps_to_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"; root.mkdir()
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
            root = Path(td) / "sessions"; root.mkdir()
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
