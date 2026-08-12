import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "integrations" / "codex" / "install.py"
BUNDLED_ROOT = MODULE_PATH.parent / "bundled"
SPEC = importlib.util.spec_from_file_location("plotkeeper_codex_install", MODULE_PATH)
INSTALLER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(INSTALLER)

REVIEW_VALIDATOR_PATH = BUNDLED_ROOT / "skills" / "production-goal-review" / "scripts" / "validate_review_receipt.py"
REVIEW_SPEC = importlib.util.spec_from_file_location("plotkeeper_review_validator", REVIEW_VALIDATOR_PATH)
REVIEW_VALIDATOR = importlib.util.module_from_spec(REVIEW_SPEC)
assert REVIEW_SPEC.loader
_previous_bytecode = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    REVIEW_SPEC.loader.exec_module(REVIEW_VALIDATOR)
finally:
    sys.dont_write_bytecode = _previous_bytecode

CONTRACT_VALIDATOR_PATH = BUNDLED_ROOT / "skills" / "production-goal-contract" / "scripts" / "validate_contract_receipt.py"
CONTRACT_SPEC = importlib.util.spec_from_file_location("plotkeeper_contract_validator", CONTRACT_VALIDATOR_PATH)
CONTRACT_VALIDATOR = importlib.util.module_from_spec(CONTRACT_SPEC)
assert CONTRACT_SPEC.loader
sys.dont_write_bytecode = True
try:
    CONTRACT_SPEC.loader.exec_module(CONTRACT_VALIDATOR)
finally:
    sys.dont_write_bytecode = _previous_bytecode


class CodexIntegrationTests(unittest.TestCase):
    def test_review_validator_allows_only_artifact_stable_attested_target_progression(self):
        isolated = {"environment": "isolated", "artifact_digest": "git:" + "a" * 40, "traffic_or_execution_path": "http://127.0.0.1:49100"}
        public = {"environment": "public", "artifact_digest": "git:" + "a" * 40, "traffic_or_execution_path": "https://github.com/o/r"}
        wrong = dict(public, artifact_digest="git:" + "b" * 40)
        self.assertTrue(REVIEW_VALIDATOR.predecessor_target_matches("ATTESTED", isolated, public))
        self.assertFalse(REVIEW_VALIDATOR.predecessor_target_matches("ATTESTED", isolated, wrong))
        self.assertFalse(REVIEW_VALIDATOR.predecessor_target_matches("DEPLOY_READY", isolated, public))

    def test_bundled_review_validator_defers_attested_acceptance_and_proof(self):
        contract = {
            "acceptance_cases": [
                {"id": "AC-NOW", "phase": "VALIDATED"},
                {"id": "AC-LIVE", "phase": "ATTESTED"},
            ],
            "proof_requirements": [
                {"id": "PR-NOW"},
                {"id": "PR-LIVE", "phase": "ATTESTED"},
            ],
            "review_requirements": [],
            "release_requirements": [],
        }
        deploy = REVIEW_VALIDATOR.required_ids(contract, "DEPLOY_READY")
        attested = REVIEW_VALIDATOR.required_ids(contract, "ATTESTED")
        self.assertEqual(deploy["acceptance"], {"AC-NOW"})
        self.assertEqual(deploy["proof"], {"PR-NOW"})
        self.assertEqual(attested["acceptance"], {"AC-NOW", "AC-LIVE"})
        self.assertEqual(attested["proof"], {"PR-NOW", "PR-LIVE"})

    def test_contract_validator_rejects_unknown_acceptance_or_proof_phase(self):
        source = json.loads((BUNDLED_ROOT / "skills" / "production-goal-contract" / "references" / "valid-contract-receipt.json").read_text(encoding="utf-8"))
        source["acceptance_cases"][0]["phase"] = "SOMEDAY"
        source["proof_requirements"][0]["phase"] = "LATER"
        source["contract_hash"] = CONTRACT_VALIDATOR.canonical_hash(source)
        errors = CONTRACT_VALIDATOR.validate(source, None)
        self.assertIn("acceptance_case.phase must be a valid lifecycle phase", errors)
        self.assertIn("proof_requirement.phase must be a valid lifecycle phase", errors)

    def test_bundle_contains_no_generated_python_cache(self) -> None:
        generated = [
            path
            for path in BUNDLED_ROOT.rglob("*")
            if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}
        ]
        self.assertEqual(generated, [])

    def test_merge_is_idempotent_and_preserves_unrelated_configuration(self):
        home = Path("Z:/example/.codex")
        document = {"custom": True, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
        first = INSTALLER.merge_hooks(document, home)
        second = INSTALLER.merge_hooks(first, home)
        self.assertTrue(second["custom"])
        self.assertEqual(second["hooks"]["Stop"][0]["hooks"][0]["command"], "other")
        command = INSTALLER.hook_command(home)
        for event in ("UserPromptSubmit", "Stop"):
            matches = [
                hook for group in second["hooks"][event]
                for hook in group["hooks"] if hook.get("command") == command
            ]
            self.assertEqual(len(matches), 1)

    def test_installer_writes_hooks_and_skill_without_plugin_side_effects(self):
        repo_temp = Path(__file__).parents[1] / "runtime" / "qa"
        repo_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=repo_temp) as folder:
            home = Path(folder) / ".codex"
            home.mkdir()
            (home / "hooks.json").write_text(json.dumps({"preserve": "yes"}), encoding="utf-8")
            history = home / "skills" / "adaptive-execution" / "data" / "adaptive_execution.sqlite3"
            history.parent.mkdir(parents=True)
            history.write_bytes(b"calibration-history")
            hooks_path = INSTALLER.install(home, skip_plugins=True)
            document = json.loads(hooks_path.read_text(encoding="utf-8"))
            self.assertEqual(document["preserve"], "yes")
            self.assertTrue((home / "skills" / "adaptive-execution" / "SKILL.md").is_file())
            for skill in ("specswarm", "production-goal-contract", "production-goal-review", "msw", "timebox"):
                self.assertTrue((home / "skills" / skill / "SKILL.md").is_file(), skill)
            self.assertEqual(history.read_bytes(), b"calibration-history")
            self.assertEqual(set(document["hooks"]), {"SessionStart", "UserPromptSubmit", "Stop"})
            self.assertNotIn("trust", document)
            config = json.loads((home / "plotkeeper.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(config["repo_root"]), MODULE_PATH.parents[2])

    def test_dependency_manifest_and_bundle_are_complete(self):
        integration = MODULE_PATH.parent
        manifest = json.loads((integration / "bundled" / "dependencies.json").read_text(encoding="utf-8"))
        names = {item["name"] for item in manifest["components"]}
        self.assertEqual(names, {"specswarm", "production-goal-contract", "production-goal-review", "adaptive-execution", "msw", "msw-hook", "timebox", "plotkeeper-guard"})
        declared_skills = {name for _, name in INSTALLER.BUNDLED_SKILLS}
        self.assertEqual(declared_skills, {"specswarm", "production-goal-contract", "production-goal-review", "adaptive-execution", "msw", "timebox"})
        for relative, _ in INSTALLER.BUNDLED_SKILLS:
            self.assertTrue((integration / relative / "SKILL.md").is_file(), relative)
        self.assertTrue((integration / "bundled" / "upstream" / "slopware" / "msw-hook" / "hooks" / "hooks.json").is_file())
        self.assertTrue((integration / "bundled" / "upstream" / "slopware" / "LICENSE").is_file())

    def test_bundled_only_install_never_runs_network_plugin_commands(self):
        repo_temp = Path(__file__).parents[1] / "runtime" / "qa"
        repo_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=repo_temp) as folder, mock.patch.object(INSTALLER.subprocess, "run") as run:
            INSTALLER.install(Path(folder) / ".codex", skip_plugins=True)
        run.assert_not_called()

    def test_isolated_install_matches_every_bundled_skill_file(self):
        repo_temp = Path(__file__).parents[1] / "runtime" / "qa"
        repo_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=repo_temp) as folder:
            home = Path(folder) / ".codex"
            INSTALLER.install(home, skip_plugins=True)
            integration = MODULE_PATH.parent
            for relative, name in INSTALLER.BUNDLED_SKILLS:
                source = integration / relative
                destination = home / "skills" / name
                source_files = {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()}
                installed_files = {path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.rglob("*") if path.is_file() and "data/" not in path.relative_to(destination).as_posix()}
                self.assertEqual(installed_files, source_files, name)

    def test_no_required_skill_depends_on_external_marketplace_install(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("plugin marketplace add transcendr/slopware-skills", source)
        self.assertNotIn("msw@slopware-skills", source)
        specswarm = (MODULE_PATH.parent / "bundled" / "skills" / "specswarm" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Z:\\Plotkeeper", specswarm)
        for required in ("$production-goal-contract", "$production-goal-review"):
            self.assertIn(required, specswarm)

    def test_guard_plugin_uses_repository_marketplace(self):
        with mock.patch.object(INSTALLER.subprocess, "run") as run:
            INSTALLER.install_guard_plugin()
        marketplace_root = str(MODULE_PATH.parent.resolve())
        self.assertEqual(run.call_args_list, [
            mock.call(("codex", "plugin", "marketplace", "add", marketplace_root), check=True),
            mock.call(("codex", "plugin", "add", "plotkeeper-guard@plotkeeper"), check=True),
        ])


if __name__ == "__main__":
    unittest.main()
