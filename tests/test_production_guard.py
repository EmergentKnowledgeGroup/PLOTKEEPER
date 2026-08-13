import importlib.util
import json
import os
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
    def test_release_authorization_rejects_placeholder_ids(self):
        for value in (None, "", "   ", 1, "RL-NONE"):
            self.assertFalse(GUARD._release_authorized({"release_requirements": [{"id": value, "phase": "DEPLOY_READY"}]}))
        self.assertTrue(GUARD._release_authorized({"release_requirements": [{"id": "RL-DEPLOY", "phase": "DEPLOY_READY"}]}))

    def payload(self, cwd, command):
        return {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": command}}

    def write_contract(self, cwd, filename="active.json", contract_id="release", release_id="RL-DEPLOY"):
        path = cwd / "runtime" / "goal-contracts" / filename
        contract = {
            "id": contract_id,
            "status": "ACTIVE",
            "contract_hash": "abc",
            "release_requirements": [{"id": release_id, "phase": "DEPLOY_READY"}],
        }
        path.write_text(json.dumps(contract), encoding="utf-8")
        pointer = {
            "schema_version": 1,
            "purpose": "PLOTKEEPER_PUBLIC_RELEASE",
            "contract_id": contract_id,
            "contract_path": f"runtime/goal-contracts/{filename}",
            "contract_sha256": GUARD.canonical_json_hash(contract),
        }
        (cwd / "runtime" / "goal-contracts" / "RELEASE_CONTRACT.json").write_text(json.dumps(pointer), encoding="utf-8")
        return path

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
            self.write_contract(cwd)
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
            self.write_contract(cwd)
            (reviews / "deploy.json").write_text(json.dumps({"phase": "DEPLOY_READY", "verdict": "PASS"}), encoding="utf-8")
            key_path = cwd / "review.key"
            key_path.write_text("test-review-key", encoding="utf-8")
            with mock.patch.object(GUARD, "git_head", return_value="f" * 40), mock.patch.dict("os.environ", {"PLOTKEEPER_REVIEW_KEY_FILE": str(key_path)}):
                self.assertFalse(GUARD.evaluate(self.payload(cwd, "git push origin main"))[0])

    def test_nested_deploy_bundle_is_discovered_inside_authorized_review_root(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            cwd = Path(folder)
            contracts = cwd / "runtime" / "goal-contracts"
            nested = cwd / "runtime" / "goal-reviews" / "review-run" / "evidence"
            contracts.mkdir(parents=True)
            nested.mkdir(parents=True)
            self.write_contract(cwd)
            (nested / "candidate-DEPLOY_READY.bundle.json").write_text("{}", encoding="utf-8")
            key_path = cwd / "review.key"
            key_path.write_text("test-review-key", encoding="utf-8")
            completed = mock.Mock(returncode=0, stdout="verified", stderr="")
            with mock.patch.object(GUARD, "git_head", return_value="f" * 40), mock.patch.dict("os.environ", {"PLOTKEEPER_REVIEW_KEY_FILE": str(key_path)}), mock.patch.object(GUARD.subprocess, "run", return_value=completed):
                self.assertTrue(GUARD.evaluate(self.payload(cwd, "git push origin main"))[0])

    def test_newer_nonrelease_successor_cannot_supersede_designated_release(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            cwd = Path(folder)
            contracts = cwd / "runtime" / "goal-contracts"
            reviews = cwd / "runtime" / "goal-reviews"
            contracts.mkdir(parents=True)
            reviews.mkdir(parents=True)
            release = self.write_contract(cwd, "release.json", "release")
            successor = contracts / "newer-listener.json"
            successor.write_text(json.dumps({
                "id": "listener-ownership",
                "status": "ACTIVE",
                "contract_hash": "successor",
                "release_requirements": [{"id": "RL-NONE", "phase": "DEPLOY_READY"}],
            }), encoding="utf-8")
            os.utime(successor, (release.stat().st_atime + 100, release.stat().st_mtime + 100))
            (reviews / "candidate-DEPLOY_READY.bundle.json").write_text("{}", encoding="utf-8")
            key_path = cwd / "review.key"
            key_path.write_text("test-review-key", encoding="utf-8")
            completed = mock.Mock(returncode=0, stdout="verified", stderr="")
            with mock.patch.object(GUARD, "git_head", return_value="f" * 40), mock.patch.dict("os.environ", {"PLOTKEEPER_REVIEW_KEY_FILE": str(key_path)}), mock.patch.object(GUARD.subprocess, "run", return_value=completed) as run:
                selected = GUARD.latest_active_contract(cwd)
                self.assertIsNotNone(selected)
                self.assertEqual(Path(selected["_path"]), Path("runtime/goal-contracts/release.json"))
                self.assertTrue(GUARD.evaluate(self.payload(cwd, "git push origin main"))[0])
                verifier_env = run.call_args.kwargs["env"]
                self.assertEqual(verifier_env["PLOTKEEPER_CONTRACT"], "runtime/goal-contracts/release.json")

    def test_pointer_to_nonrelease_successor_fails_closed(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            cwd = Path(folder)
            contracts = cwd / "runtime" / "goal-contracts"
            contracts.mkdir(parents=True)
            successor = self.write_contract(cwd, "listener.json", "listener-ownership", "RL-NONE")
            self.assertIsNone(GUARD.latest_active_contract(cwd))
            key_path = cwd / "review.key"
            key_path.write_text("test-review-key", encoding="utf-8")
            with mock.patch.dict("os.environ", {"PLOTKEEPER_REVIEW_KEY_FILE": str(key_path)}):
                self.assertFalse(GUARD.evaluate(self.payload(cwd, "git push origin main"))[0])

    def test_lf_and_crlf_contract_bytes_have_same_guard_hash(self):
        base = Path(__file__).parents[1] / "runtime" / "qa"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as folder:
            cwd = Path(folder)
            contracts = cwd / "runtime" / "goal-contracts"
            contracts.mkdir(parents=True)
            document = {
                "id": "release",
                "status": "ACTIVE",
                "contract_hash": "abc",
                "release_requirements": [{"id": "RL-DEPLOY", "phase": "DEPLOY_READY"}],
            }
            contract_path = contracts / "release.json"
            text = json.dumps(document, indent=2)
            pointer = {
                "schema_version": 1,
                "purpose": "PLOTKEEPER_PUBLIC_RELEASE",
                "contract_id": "release",
                "contract_path": "runtime/goal-contracts/release.json",
                "contract_sha256": GUARD.canonical_json_hash(document),
            }
            (contracts / "RELEASE_CONTRACT.json").write_text(json.dumps(pointer), encoding="utf-8")
            contract_path.write_text(text, encoding="utf-8", newline="\n")
            lf = GUARD.latest_active_contract(cwd)
            contract_path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
            crlf = GUARD.latest_active_contract(cwd)
            self.assertEqual(lf["contract_hash"], crlf["contract_hash"])


if __name__ == "__main__":
    unittest.main()
