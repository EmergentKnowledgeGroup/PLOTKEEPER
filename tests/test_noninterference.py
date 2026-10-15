import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plotkeeper.models import RunState
from plotkeeper.service import PlotkeeperService


class NoninterferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cwd = self.base / "other-project"
        self.cwd.mkdir()
        self.sessions = self.base / "sessions"
        self.sessions.mkdir()
        self.service = PlotkeeperService(ledger_path=self.base / "ledger.sqlite", sessions_root=self.sessions,
                                        codex_state_path=self.base / "absent-state.sqlite")
        self.addCleanup(self.service.close_db)
        self.run = self.service.ledger.enroll("original-root", str(self.cwd), self.service.dashboard_url)

    def history(self, name="unrelated-filename.jsonl", sid="original-root", cwd=None, content=""):
        path = self.sessions / name
        path.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": str(cwd or self.cwd)}}) + "\n" + content, encoding="utf-8")
        return path

    def test_review_is_fresh_and_explicitly_bound(self):
        self.service.ledger.mark_review_required(self.run.run_id)
        calls = []
        result = self.service.inject_review(self.run.run_id, runner=lambda a, **k: calls.append((a, k)) or 0)
        self.assertTrue(result["ok"])
        args, kwargs = calls[0]
        self.assertEqual(args[:2], ["codex.exe", "exec"])
        self.assertNotIn("resume", args)
        self.assertIn(f"Plotkeeper-Run-ID: {self.run.run_id}", args[2])
        self.assertIn(self.run.root_session_id, args[2])
        self.assertEqual(kwargs["cwd"], str(self.cwd.resolve()))
        self.assertEqual(self.service.inject_review(self.run.run_id)["error"], "review_already_pending")

    def test_verified_history_compares_resolved_directory_identity(self):
        # CI's Windows TEMP uses RUNNER~1; validated cwd uses its long name.
        # Model that filesystem alias without requiring 8.3 creation on Linux.
        alias = self.base / 'SHORT~1'
        history = self.history(cwd=alias)
        original = Path.resolve
        def resolve(path, *args, **kwargs):
            if path == alias:
                return original(self.cwd, *args, **kwargs)
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'resolve', resolve):
            found = self.service.thread_catalog.verified_history('original-root', str(self.cwd))
        self.assertEqual(found, history.resolve())

    def test_failed_review_restores_required(self):
        self.service.ledger.mark_review_required(self.run.run_id)
        self.assertFalse(self.service.inject_review(self.run.run_id, runner=lambda *_a, **_k: 23)["ok"])
        self.assertEqual(self.service.ledger.get(self.run.run_id).state, RunState.REVIEW_REQUIRED)

    def test_checkin_never_spawns_and_remains_visible_once(self):
        runner = mock.Mock(return_value=mock.Mock(returncode=0))
        self.service.request_check_in(self.run.run_id)
        self.service.inject_check_in(self.run.run_id, runner=runner)
        self.service.inject_check_in(self.run.run_id, runner=runner)
        runner.assert_not_called()
        payload = self.service.current(run_id=self.run.run_id)
        self.assertEqual(payload["check_in"]["status"], "pending")
        self.assertIn("end", payload["check_in"]["instruction"])
        self.assertEqual(len(self.service.ledger.reports(self.run.run_id)), 1)
        self.service.report(self.run.run_id, "check-in-acknowledged", "Owner received the request")
        self.assertEqual(self.service.current(run_id=self.run.run_id)["check_in"]["status"], "acknowledged")

    def test_watcher_does_not_repeat_queue_writes_or_dispatch_checkin(self):
        self.service.request_check_in(self.run.run_id)
        with mock.patch.object(self.service, "poll_once"), mock.patch.object(self.service, "inject_check_in") as inject:
            with mock.patch.object(self.service._stop, "wait", side_effect=[False, False, True]):
                self.service.watch_forever()
            inject.assert_not_called()
        self.assertEqual(len(self.service.ledger.reports(self.run.run_id)), 1)

    def test_fresh_marker_precedes_specswarm_enrollment(self):
        text = f"Plotkeeper-Run-ID: {self.run.run_id}\nInvoke $specswarm only to read the original artifacts."
        self.history("fresh.jsonl", "fresh-review", content=json.dumps({"type": "message", "payload": {"role": "user", "content": text}}) + "\n")
        self.service.poll_once()
        self.assertEqual(len(self.service.ledger.list_runs()), 1)
        self.assertIn("fresh-review", self.service.ledger.get(self.run.run_id).children)

    def test_explicit_worktree_marker_preserves_existing_attachment_policy(self):
        text = f"Plotkeeper-Run-ID: {self.run.run_id}\n$specswarm"
        self.history("fresh.jsonl", "wrong-project-review", cwd=self.base,
                     content=json.dumps({"type": "message", "payload": {"role": "user", "content": text}}) + "\n")
        self.service.poll_once()
        self.assertEqual(len(self.service.ledger.list_runs()), 1)
        self.assertIn("wrong-project-review", self.service.ledger.get(self.run.run_id).children)

    def test_fresh_review_marker_does_not_bypass_receipt_gate(self):
        self.service.ledger.mark_review_pending(self.run.run_id)
        text = f"Plotkeeper-Run-ID: {self.run.run_id}\nPK:REVIEW_RESULT run_id={self.run.run_id} verdict=PASS open_items=0"
        self.history("fresh.jsonl", "fresh-review",
                     content=json.dumps({"type": "message", "payload": {"role": "assistant", "content": text}}) + "\n")
        self.service.poll_once()
        self.assertEqual(self.service.ledger.get(self.run.run_id).state, RunState.REVIEW_PENDING)

    def test_recovery_has_verified_history_and_exact_sync_target(self):
        history = self.history()
        calls = []
        result = self.service.reconstruct_plan(self.run.run_id, runner=lambda a, **k: calls.append((a, k)) or 0)
        self.assertTrue(result["ok"])
        args, kwargs = calls[0]
        self.assertNotIn("resume", args)
        prompt = args[2]
        for value in (str(history.resolve()), self.run.root_session_id, str(self.cwd.resolve()), str(self.service.ledger.path.resolve()), f"Plotkeeper-Run-ID: {self.run.run_id}", f"--run-id {self.run.run_id}", "read-only"):
            self.assertIn(value, prompt)
        self.assertEqual(kwargs["cwd"], str(self.cwd.resolve()))
        self.assertTrue(self.service.reconstruct_plan(self.run.run_id)["already_requested"])

    def test_missing_or_wrong_history_fails_without_spawn(self):
        runner = mock.Mock(return_value=0)
        self.assertEqual(self.service.reconstruct_plan(self.run.run_id, runner=runner)["error"], "root_history_unavailable")
        self.history("original-root.jsonl", "wrong-root")
        self.assertEqual(self.service.reconstruct_plan(self.run.run_id, runner=runner)["error"], "root_history_unavailable")
        self.history("original-root.jsonl", cwd=self.base)
        self.assertEqual(self.service.reconstruct_plan(self.run.run_id, runner=runner)["error"], "root_history_unavailable")
        runner.assert_not_called()

    def test_recovery_failed_runner_is_retryable(self):
        self.history()
        self.assertEqual(self.service.reconstruct_plan(self.run.run_id, runner=lambda *_a, **_k: 23)["returncode"], 23)
        self.assertFalse(self.service.ledger.has_report_kind(self.run.run_id, "plan-repair-injected"))
        self.assertTrue(self.service.reconstruct_plan(self.run.run_id, runner=lambda *_a, **_k: 0)["ok"])
