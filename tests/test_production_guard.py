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
            key_path = cwd / "review.key"
            key_path.write_text("test-review-key", encoding="utf-8")
            payload = self.payload(cwd, "gh repo edit owner/repo --description ready")
            with mock.patch.object(GUARD, "git_head", return_value="f" * 40), mock.patch.dict("os.environ", {"PLOTKEEPER_REVIEW_KEY_FILE": str(key_path)}):
                self.assertFalse(GUARD.evaluate(payload)[0])
                (reviews / "candidate-DEPLOY_READY.bundle.json").write_text("{}", encoding="utf-8")
                completed = mock.Mock(returncode=0, stdout="verified", stderr="")
                with mock.patch.object(GUARD.subprocess, "run", return_value=completed):
                    self.assertTrue(GUARD.evaluate(payload)[0])

    def test_signed_headline_receipt_without_full_bundle_is_blocked(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            cwd = Path(folder)
            contracts = cwd / "runtime" / "goal-contracts"
            reviews = cwd / "runtime" / "goal-reviews"
            contracts.mkdir(parents=True)
            reviews.mkdir(parents=True)
            (contracts / "active.json").write_text(json.dumps({"status": "ACTIVE", "contract_hash": "abc"}), encoding="utf-8")
            (reviews / "deploy.json").write_text(json.dumps({"phase": "DEPLOY_READY", "verdict": "PASS"}), encoding="utf-8")
            key_path = cwd / "review.key"
            key_path.write_text("test-review-key", encoding="utf-8")
            with mock.patch.object(GUARD, "git_head", return_value="f" * 40), mock.patch.dict("os.environ", {"PLOTKEEPER_REVIEW_KEY_FILE": str(key_path)}):
                self.assertFalse(GUARD.evaluate(self.payload(cwd, "git push origin main"))[0])


if __name__ == "__main__":
    unittest.main()
