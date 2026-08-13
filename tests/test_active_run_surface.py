import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from plotkeeper.service import PlotkeeperService
from plotkeeper.sessions import ThreadCatalog


def _line(timestamp, event_type, payload):
    return json.dumps({"timestamp": timestamp, "type": event_type, "payload": payload}) + "\n"


class ActiveRunSurfaceTests(unittest.TestCase):
    def _temp_root(self):
        qa = Path("runtime") / "qa"
        qa.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=qa)

    def test_current_requires_exact_selection_when_cwd_is_ambiguous(self):
        with self._temp_root() as folder:
            folder = Path(folder)
            root = folder / "sessions"
            root.mkdir()
            rollout_paths = [root / "root-1.jsonl", root / "root-2.jsonl"]
            state = folder / "state.sqlite"
            db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT)")
            db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)", [
                (f"root-{index}", f"Task {index}", None, None, None, None, str(folder / "project"), str(rollout_paths[index - 1]))
                for index in (1, 2)
            ])
            db.commit(); db.close()
            service = PlotkeeperService(ledger_path=folder / "ledger.sqlite", sessions_root=root, codex_state_path=state)
            for index in (1, 2):
                rollout = rollout_paths[index - 1]
                rollout.write_text(
                    _line("1", "session_meta", {"id": f"root-{index}", "cwd": str(Path(folder) / "project"), "title": f"Task {index}"})
                    + _line("2", "message", {"role": "user", "content": "$specswarm"}), encoding="utf-8")
            service.poll_once()
            self.assertEqual(service.current()["error"], "selection_required")
            self.assertEqual(service.current(str(Path(folder) / "project"))["error"], "cwd_ambiguous")
            exact = service.current(session_id="root-1")
            self.assertTrue(exact["ok"])
            self.assertEqual(exact["run"]["task_label"], "Task 1")
            self.assertIn("run_id=", exact["run"]["dashboard_url"])
            service.close_db()

    def test_session_index_title_precedes_original_prompt_and_empty_run_gets_truthful_thread_task(self):
        with self._temp_root() as folder:
            folder = Path(folder)
            sessions = folder / "sessions"
            sessions.mkdir()
            session_id = "11111111-2222-4333-8444-555555555555"
            rollout = sessions / f"rollout-{session_id}.jsonl"
            rollout.write_text(_line("1", "session_meta", {"id": session_id, "cwd": "Z:\\MoonMarket"}) + _line("2", "response_item", {"type": "reasoning"}), encoding="utf-8")
            state = folder / "state.sqlite"
            db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT)")
            db.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)", (session_id, "okay Dex, so go ahead and read the core spec", None, "okay Dex", None, None, "Z:\\MoonMarket", str(rollout)))
            db.commit()
            db.close()
            index = folder / "session_index.jsonl"
            index.write_text(json.dumps({"id": session_id, "thread_name": "Review core spec"}) + "\n", encoding="utf-8")
            service = PlotkeeperService(ledger_path=folder / "ledger.sqlite", sessions_root=sessions, codex_state_path=state, session_index_path=index)
            run = service.ledger.enroll(session_id, "Z:\\MoonMarket", service.dashboard_url)
            payload = service._run_payload(run)
            self.assertEqual(payload["project_name"], "MoonMarket")
            self.assertEqual(payload["task_label"], "Review core spec")
            self.assertEqual(payload["current_task_id"], "THREAD")
            fallback = service._tasks_payload(run)
            self.assertEqual(len(fallback), 1)
            self.assertEqual(fallback[0]["title"], "Review core spec")
            self.assertEqual(fallback[0]["source"], "codex:thread-title")
            service.ledger.replace_tasks(run.run_id, [{"task_id": "T001", "title": "Real synced task", "status": "pending"}])
            self.assertEqual([task["title"] for task in service._tasks_payload(run)], ["Real synced task"])
            service.close_db()

    def test_session_title_refreshes_after_cached_lookup_and_missing_sqlite_row(self):
        with self._temp_root() as folder:
            folder = Path(folder)
            session_id = "11111111-2222-4333-8444-555555555557"
            state = folder / "state.sqlite"
            rollout = folder / "rollout.jsonl"
            rollout.write_text(_line("1", "session_meta", {"id": session_id}), encoding="utf-8")
            db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT)")
            db.commit()
            db.close()
            index = folder / "session_index.jsonl"
            index.write_text(json.dumps({"id": session_id, "thread_name": "First title"}) + "\n", encoding="utf-8")
            catalog = ThreadCatalog(state, folder, index)
            indexed_only = catalog.metadata(session_id)
            self.assertEqual(indexed_only["task_label"], "First title")
            self.assertEqual(indexed_only["project_name"], "Unknown project")

            db = sqlite3.connect(state)
            db.execute("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)", (session_id, "Database title", None, None, None, None, str(folder), str(rollout)))
            db.commit()
            db.close()
            self.assertEqual(catalog.metadata(session_id)["task_label"], "First title")

            index.write_text(json.dumps({"id": session_id, "thread_name": "Updated title"}) + "\n", encoding="utf-8")
            self.assertEqual(catalog.metadata(session_id)["task_label"], "Updated title")

    def test_legacy_message_roots_are_not_enrolled_or_picked(self):
        with self._temp_root() as folder:
            root = Path(folder) / "sessions"
            root.mkdir()
            service = PlotkeeperService(ledger_path=Path(folder) / "ledger.sqlite", sessions_root=root,
                                        codex_state_path=Path(folder) / "missing-state.sqlite")
            self.assertIsNone(service.ledger.enroll("msg_legacy", str(folder), service.dashboard_url))
            valid = service.ledger.enroll("root-valid", str(folder), service.dashboard_url)
            self.assertIsNotNone(valid)
            self.assertEqual(service._interactive_runs(), [])
            self.assertTrue(service.current(run_id=valid.run_id)["ok"])
            unknown_real = service.ledger.enroll("019abcdef-1234-5678-9abc-def012345678", str(folder), service.dashboard_url)
            self.assertIsNotNone(unknown_real)
            self.assertEqual(service._interactive_runs(), [])
            service.close_db()

    def test_thread_catalog_fails_closed_for_missing_or_terminal_transcript(self):
        with self._temp_root() as folder:
            folder = Path(folder)
            state = folder / "state.sqlite"
            active = folder / "active.jsonl"
            done = folder / "done.jsonl"
            aborted = folder / "aborted.jsonl"
            active.write_text(_line("1", "session_meta", {"id": "active"}) + _line("2", "response_item", {"type": "reasoning"}), encoding="utf-8")
            done.write_text(_line("1", "session_meta", {"id": "done"}) + _line("2", "event_msg", {"type": "task_complete"}), encoding="utf-8")
            aborted.write_text(_line("1", "session_meta", {"id": "aborted"}) + _line("2", "event_msg", {"type": "turn_aborted"}), encoding="utf-8")
            db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT)")
            db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)", [
                ("active", "Active task", None, None, None, None, str(folder), str(active)),
                ("done", "Done task", None, None, None, None, str(folder), str(done)),
                ("aborted", "Aborted task", None, None, None, None, str(folder), str(aborted)),
            ])
            db.commit(); db.close()
            catalog = ThreadCatalog(state, folder)
            self.assertTrue(catalog.is_active("active"))
            self.assertIsNone(catalog.metadata("active")["thread_source"])
            self.assertFalse(catalog.is_active("done"))
            self.assertFalse(catalog.is_active("aborted"))
            self.assertFalse(catalog.is_active("missing"))

    def test_delegation_prompt_uses_stable_task_id_instead_of_fake_title(self):
        label = ThreadCatalog._label({
            "id": "thread-42",
            "title": "<codex_delegation><input>Task 21 worker reporting to Dex. LANE D: do work</input></codex_delegation>",
        })
        self.assertEqual(label, "Task thread-42")

    def test_active_child_binds_existing_run_without_reverting_to_inactive_root(self):
        with self._temp_root() as folder:
            folder = Path(folder)
            sessions = folder / "sessions"; sessions.mkdir()
            root_rollout = folder / "root.jsonl"
            child_rollout = folder / "child.jsonl"
            root_rollout.write_text(_line("1", "session_meta", {"id": "root-old"}) + _line("2", "event_msg", {"type": "task_complete"}), encoding="utf-8")
            child_rollout.write_text(_line("1", "session_meta", {"id": "child-current"}) + _line("2", "response_item", {"type": "reasoning"}), encoding="utf-8")
            state = folder / "state.sqlite"
            db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT)")
            db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)", [
                ("root-old", "Old root", None, None, None, None, str(folder), str(root_rollout)),
                ("child-current", "Current child task", None, None, None, None, str(folder), str(child_rollout)),
            ])
            db.commit(); db.close()
            service = PlotkeeperService(ledger_path=folder / "ledger.sqlite", sessions_root=sessions, codex_state_path=state)
            run = service.ledger.enroll("root-old", str(folder), service.dashboard_url)
            service.ledger.attach_child(run.run_id, "child-current")
            current = service.current(run_id=run.run_id, session_id="child-current")
            self.assertTrue(current["ok"])
            self.assertEqual(current["run"]["task_label"], "Current child task")
            self.assertEqual(current["run"]["bound_session_id"], "child-current")
            self.assertIn("session_id=child-current", current["run"]["dashboard_url"])
            self.assertEqual(service.current(run_id=run.run_id, session_id="root-old")["error"], "run_inactive")
            service.close_db()

    def test_nested_subagent_does_not_make_inactive_owner_run_interactive(self):
        with self._temp_root() as folder:
            folder = Path(folder); sessions = folder / "sessions"; sessions.mkdir()
            root_rollout = folder / "root.jsonl"; child_rollout = folder / "child.jsonl"
            root_rollout.write_text(_line("1", "session_meta", {"id": "root"}) + _line("2", "event_msg", {"type": "task_complete"}), encoding="utf-8")
            child_rollout.write_text(_line("1", "session_meta", {"id": "worker"}) + _line("2", "response_item", {"type": "reasoning"}), encoding="utf-8")
            state = folder / "state.sqlite"; db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT)")
            db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?)", [
                ("root", "Owner", None, None, None, None, str(folder), str(root_rollout)),
                ("worker", "Worker", None, None, None, "/root/worker", str(folder), str(child_rollout)),
            ])
            db.commit(); db.close()
            service = PlotkeeperService(ledger_path=folder / "ledger.sqlite", sessions_root=sessions, codex_state_path=state)
            run = service.ledger.enroll("root", str(folder), service.dashboard_url); service.ledger.attach_child(run.run_id, "worker")
            self.assertEqual(service._interactive_runs(), [])
            self.assertEqual(service.current(run_id=run.run_id)["error"], "run_inactive")
            service.close_db()

    def test_thread_source_subagent_is_excluded_even_when_agent_path_is_null(self):
        with self._temp_root() as folder:
            folder = Path(folder); sessions = folder / "sessions"; sessions.mkdir()
            root_rollout = folder / "root.jsonl"; worker_rollout = folder / "worker.jsonl"
            root_rollout.write_text(_line("1", "session_meta", {"id": "owner"}) + _line("2", "event_msg", {"type": "task_complete"}), encoding="utf-8")
            worker_rollout.write_text(_line("1", "session_meta", {"id": "worker"}) + _line("2", "response_item", {"type": "reasoning"}), encoding="utf-8")
            state = folder / "state.sqlite"; db = sqlite3.connect(state)
            db.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, name TEXT, first_user_message TEXT, preview TEXT, agent_path TEXT, cwd TEXT, rollout_path TEXT, thread_source TEXT)")
            db.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?)", [
                ("owner", "Owner", None, None, None, None, str(folder), str(root_rollout), "user"),
                ("worker", "Task 21G", None, None, None, None, str(folder), str(worker_rollout), "subagent"),
            ])
            db.commit(); db.close()
            service = PlotkeeperService(ledger_path=folder / "ledger.sqlite", sessions_root=sessions, codex_state_path=state)
            run = service.ledger.enroll("owner", str(folder), service.dashboard_url); service.ledger.attach_child(run.run_id, "worker")
            self.assertEqual(service._interactive_runs(), [])
            self.assertEqual(service.current(run_id=run.run_id, session_id="worker")["error"], "run_subagent")
            self.assertEqual(service.thread_catalog.metadata("worker")["thread_source"], "subagent")
            service.close_db()


if __name__ == "__main__":
    unittest.main()
