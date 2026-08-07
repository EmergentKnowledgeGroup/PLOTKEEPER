from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plotkeeper.ledger import Ledger
from plotkeeper.models import RunState
from plotkeeper.service import PlotkeeperService
from plotkeeper.sessions import parse_session


def line(timestamp, typ, payload):
    return json.dumps({"timestamp": timestamp, "type": typ, "payload": payload}) + "\n"


class BackendTests(unittest.TestCase):
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
            self.assertTrue(service.record_review_receipt(run.run_id, {"terminal": True, "injected": True, "summary": "ok"})["ok"])
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


if __name__ == "__main__":
    unittest.main()
