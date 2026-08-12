from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "integrations" / "codex" / "adaptive-execution" / "scripts" / "adaptive_execution.py"
spec = importlib.util.spec_from_file_location("plotkeeper_adaptive_execution", SCRIPT)
adaptive = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(adaptive)


class AdaptiveComparisonTests(unittest.TestCase):
    def test_incomplete_and_unproven_are_history_only_false_timebox_case(self):
        with tempfile.TemporaryDirectory() as td:
            db = adaptive.connect(Path(td) / "adaptive.sqlite3")
            base = {
                "session_id": "s", "cwd": td, "project": Path(td).name.lower(),
                "summary": "prior", "task_type": "implementation", "risk": "medium",
                "systems_json": json.dumps(["python"]), "validation_json": json.dumps(["tests"]),
                "route": "calibration", "comparison_json": "[]", "awt_seconds": None,
                "cgp_seconds": None, "confidence": "none", "started_at": "2026-01-01T00:00:00+00:00",
                "converged_at": None, "ended_at": "2026-01-01T00:01:00+00:00", "wall_seconds": 60,
                "substantive_seconds": 44, "closeout_seconds": 5, "blocked_seconds": 0,
                "status": "closed", "proof": "safety stop", "open_items": "blocked",
            }
            columns = list(base)
            for turn_id, outcome in (("incomplete", "incomplete"), ("unproven", "unproven"), ("verified", "complete_verified"), ("unverified", "complete_unverified")):
                row = dict(base, turn_id=turn_id, outcome=outcome,
                           open_items="" if outcome == "complete_verified" else ("still open" if outcome == "complete_unverified" else "blocked"),
                           proof="verified evidence" if outcome.startswith("complete") else "safety stop")
                names = ["turn_id"] + columns[:columns.index("status") + 1] + ["outcome"] + columns[columns.index("status") + 1:]
                db.execute(f"INSERT INTO executions ({','.join(names)}) VALUES ({','.join('?' for _ in names)})", [row.get(name) for name in names])
            db.commit()
            matches = adaptive.comparable(db, Path(td).name.lower(), "implementation", "medium", ["python"], ["tests"])
            self.assertEqual({item["turn_id"] for item in matches}, {"verified", "unverified"})
            self.assertNotIn("incomplete", {item["turn_id"] for item in matches})
            self.assertNotIn("unproven", {item["turn_id"] for item in matches})
            db.close()


if __name__ == "__main__":
    unittest.main()
