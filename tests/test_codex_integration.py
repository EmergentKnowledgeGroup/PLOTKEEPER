import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "integrations" / "codex" / "install.py"
SPEC = importlib.util.spec_from_file_location("plotkeeper_codex_install", MODULE_PATH)
INSTALLER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(INSTALLER)


class CodexIntegrationTests(unittest.TestCase):
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
            self.assertEqual(history.read_bytes(), b"calibration-history")
            self.assertEqual(set(document["hooks"]), {"UserPromptSubmit", "Stop"})
            self.assertNotIn("trust", document)

    def test_all_canonical_slopware_packages_are_declared(self):
        rendered = [" ".join(command) for command in INSTALLER.SLOPWARE_COMMANDS]
        self.assertIn("codex plugin add msw@slopware-skills", rendered)
        self.assertIn("codex plugin add msw-hook@slopware-skills", rendered)
        self.assertIn("codex plugin add timebox@slopware-skills", rendered)

    def test_plugin_install_executes_every_canonical_command(self):
        with mock.patch.object(INSTALLER.subprocess, "run") as run:
            INSTALLER.install_plugins()
        self.assertEqual(
            run.call_args_list,
            [mock.call(command, check=True) for command in INSTALLER.SLOPWARE_COMMANDS],
        )

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
