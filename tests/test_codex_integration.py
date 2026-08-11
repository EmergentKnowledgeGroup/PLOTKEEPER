import importlib.util
import hashlib
import json
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


class CodexIntegrationTests(unittest.TestCase):
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
