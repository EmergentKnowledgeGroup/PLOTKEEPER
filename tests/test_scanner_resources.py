from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from plotkeeper.sessions import SessionScanner, ThreadCatalog, parse_session


def record(typ, payload):
    return (json.dumps({"timestamp": "2026-10-14T12:00:00Z", "type": typ,
                        "payload": payload}, ensure_ascii=False) + "\n").encode("utf-8")


def metadata(sid="session-a", **extra):
    return record("session_meta", {"id": sid, "cwd": "Z:/example", **extra})


def message(text):
    return record("response_item", {"type": "message", "role": "user",
                                     "content": [{"type": "input_text", "text": text}]})


class _StreamingFile:
    def __init__(self, handle):
        self.handle = handle

    def __enter__(self):
        self.handle.__enter__()
        return self

    def __exit__(self, *args):
        return self.handle.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.handle, name)

    def read(self, *args):
        raise AssertionError("scanner must not buffer the unread tail")

    def readlines(self, *args):
        raise AssertionError("scanner must not collect the unread lines")

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.handle)


class ScannerResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "rollout-example.jsonl"
        self.watermarks = {}
        self.get = mock.Mock(side_effect=lambda path: self.watermarks.get(path, 0))
        self.set = mock.Mock(side_effect=lambda path, offset: self.watermarks.__setitem__(path, offset))
        self.scanner = SessionScanner(self.root, self.get, self.set)

    def append(self, content):
        with self.path.open("ab") as handle:
            handle.write(content)

    def test_quiet_files_do_not_reopen_or_read_ledger_watermarks(self):
        self.path.write_bytes(metadata() + message("run specswarm"))
        self.assertTrue(self.scanner.scan()[0].invoked_specswarm)
        self.get.reset_mock()
        self.set.reset_mock()
        with mock.patch.object(Path, "open", side_effect=AssertionError("quiet file reopened")):
            self.assertEqual(self.scanner.scan(), [])
            self.assertEqual(self.scanner.scan(), [])
        self.get.assert_not_called()
        self.set.assert_not_called()

    def test_changed_files_stream_lines_and_preserve_delta_identity(self):
        self.path.write_bytes(metadata(thread_id="thread-a", parent_thread_id="parent-a", title="A title"))
        self.scanner.scan()
        self.append(message("run specswarm") + record("event_msg", {"type": "task_complete"}))
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            return _StreamingFile(original_open(path, *args, **kwargs))

        def guarded_parse(path, lines, **kwargs):
            self.assertNotIsInstance(lines, (list, tuple, str, bytes))
            return parse_session(path, lines, **kwargs)

        with mock.patch.object(Path, "open", guarded_open), mock.patch(
                "plotkeeper.sessions.parse_session", side_effect=guarded_parse):
            observations = self.scanner.scan()
        self.assertEqual(len(observations), 1)
        obs = observations[0]
        self.assertEqual((obs.session_id, obs.canonical_root_id, obs.task_id),
                         ("session-a", "task:thread-a", "thread-a"))
        self.assertEqual((obs.parent_session_id, obs.task_label, obs.cwd),
                         ("parent-a", "A title", "Z:/example"))
        self.assertFalse(obs.is_root)
        self.assertTrue(obs.invoked_specswarm)
        self.assertTrue(obs.root_complete)
        self.assertEqual(self.watermarks[str(self.path)], self.path.stat().st_size)
        self.assertEqual(self.scanner.scan(), [])

    def test_new_large_backlog_streams_without_collecting_lines(self):
        # Many ordinary transport records, then an actual observation. The
        # scanner may retain the observation, not the irrelevant backlog.
        self.path.write_bytes(metadata() + message("ordinary transport text") * 3000 +
                              message("run specswarm"))
        original_open = Path.open
        with mock.patch.object(Path, "open", lambda path, *args, **kwargs:
                               _StreamingFile(original_open(path, *args, **kwargs))):
            self.assertTrue(self.scanner.scan()[0].invoked_specswarm)

    def test_partial_utf8_record_waits_for_newline_without_skipping_or_replay(self):
        self.path.write_bytes(metadata())
        self.scanner.scan()
        complete = message("run specswarm café")
        split = complete.index("é".encode("utf-8")) + 1
        self.append(complete[:split])
        self.assertEqual(self.scanner.scan(), [])
        self.assertEqual(self.watermarks[str(self.path)], len(metadata()))
        self.append(complete[split:-1])
        self.assertEqual(self.scanner.scan(), [])
        self.assertEqual(self.watermarks[str(self.path)], len(metadata()))
        self.append(b"\n")
        self.assertTrue(self.scanner.scan()[0].invoked_specswarm)
        self.assertEqual(self.watermarks[str(self.path)], self.path.stat().st_size)
        self.assertEqual(self.scanner.scan(), [])

    def test_append_emits_only_new_observations(self):
        self.path.write_bytes(metadata() + message("claim: first"))
        self.assertEqual(self.scanner.scan()[0].claims[0]["text"], "first")
        self.append(message("claim: second"))
        obs = self.scanner.scan()[0]
        self.assertEqual([item["text"] for item in obs.claims], ["second"])
        self.assertEqual(obs.session_id, "session-a")
        self.assertEqual(self.scanner.scan(), [])

    def test_truncation_and_replacement_are_processed_from_start(self):
        self.path.write_bytes(metadata() + message("ordinary text" * 20))
        self.scanner.scan()
        self.path.write_bytes(metadata("session-b") + message("run specswarm"))
        obs = self.scanner.scan()[0]
        self.assertEqual(obs.session_id, "session-b")
        self.assertTrue(obs.invoked_specswarm)
        replacement = self.root / "replacement.tmp"
        replacement.write_bytes(metadata("session-c") + message("claim: replacement") * 2)
        os.replace(replacement, self.path)
        obs = self.scanner.scan()[0]
        self.assertEqual(obs.session_id, "session-c")
        self.assertEqual(len(obs.claims), 2)

    def test_in_place_rewrite_with_changed_head_and_growth_resets_identity(self):
        self.path.write_bytes(metadata() + message("claim: old"))
        self.scanner.scan()
        self.path.write_bytes(metadata("session-b", thread_id="new-thread") +
                              message("claim: replacement longer than old") * 2)
        obs = self.scanner.scan()[0]
        self.assertEqual(obs.session_id, "session-b")
        self.assertEqual(obs.canonical_root_id, "task:new-thread")
        self.assertEqual(len(obs.claims), 2)

    def test_same_size_in_place_rewrite_is_not_mistaken_for_append(self):
        self.path.write_bytes(metadata() + message("claim: old"))
        self.scanner.scan()
        old = self.path.stat()
        self.path.write_bytes(metadata() + message("claim: new"))
        os.utime(self.path, ns=(old.st_atime_ns, old.st_mtime_ns + 1000000))
        self.assertEqual(self.scanner.scan()[0].claims[0]["text"], "new")

    def test_initialize_skips_history_without_open_then_observes_append_and_new_file(self):
        self.path.write_bytes(metadata() + message("claim: historical"))
        with mock.patch.object(Path, "open", side_effect=AssertionError("initialize opened history")):
            self.scanner.initialize()
            self.assertEqual(self.scanner.scan(), [])
        self.append(message("claim: new"))
        self.assertEqual([item["text"] for item in self.scanner.scan()[0].claims], ["new"])
        other = self.root / "new.jsonl"
        other.write_bytes(metadata("new-session") + message("run specswarm"))
        self.assertEqual(self.scanner.scan()[0].session_id, "new-session")

    def test_title_cache_checks_stat_before_reading_and_refreshes_on_change(self):
        index = self.root / "session_index.jsonl"
        index.write_text(json.dumps({"id": "session-a", "thread_name": "Old title"}) + "\n", encoding="utf-8")
        catalog = ThreadCatalog(path=self.root / "absent.sqlite", sessions_root=self.root,
                                session_index_path=index)
        self.assertEqual(catalog._thread_titles(), {"session-a": "Old title"})
        with mock.patch.object(Path, "open", side_effect=AssertionError("cached index reopened")):
            self.assertEqual(catalog._thread_titles(), {"session-a": "Old title"})
        index.write_text(json.dumps({"id": "session-a", "thread_name": "New longer title"}) + "\n", encoding="utf-8")
        self.assertEqual(catalog._thread_titles(), {"session-a": "New longer title"})
        index.unlink()
        self.assertEqual(catalog._thread_titles(), {})


if __name__ == "__main__":
    unittest.main()
