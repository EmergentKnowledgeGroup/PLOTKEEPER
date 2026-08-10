import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PATH = Path(__file__).parents[1] / "integrations" / "codex" / "plugins" / "plotkeeper-guard" / "scripts" / "production_guard.py"
SPEC = importlib.util.spec_from_file_location("production_guard", PATH)
GUARD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(GUARD)


class ProductionGuardTests(unittest.TestCase):
    def payload(self, cwd, command):
        return {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": command}}

    def test_safe_read_is_allowed_without_contract(self):
        allowed, _ = GUARD.evaluate(self.payload(Path("Z:/missing"), "git status --short"))
        self.assertTrue(allowed)

    def test_release_is_blocked_without_contract(self):
        allowed, reason = GUARD.evaluate(self.payload(Path("Z:/missing"), "git push origin main"))
        self.assertFalse(allowed)
        self.assertIn("contract", reason)

    def test_release_requires_exact_independent_receipt(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            cwd = Path(folder)
            contracts = cwd / "runtime" / "goal-contracts"
            reviews = cwd / "runtime" / "goal-reviews"
            contracts.mkdir(parents=True)
            reviews.mkdir(parents=True)
            (contracts / "active.json").write_text(json.dumps({"status": "ACTIVE", "contract_hash": "abc"}), encoding="utf-8")
            payload = self.payload(cwd, "gh repo edit owner/repo --description ready")
            with mock.patch.object(GUARD, "git_head", return_value="f" * 40):
                self.assertFalse(GUARD.evaluate(payload)[0])
                (reviews / "deploy.json").write_text(json.dumps({
                    "phase": "DEPLOY_READY", "verdict": "PASS", "contract_hash": "abc",
                    "candidate_sha": "f" * 40,
                    "reviewer": {"independent": True, "implemented_candidate": False}
                }), encoding="utf-8")
                self.assertTrue(GUARD.evaluate(payload)[0])


if __name__ == "__main__":
    unittest.main()
