from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryDocumentationTests(unittest.TestCase):
    def test_readme_local_links_resolve(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^]]+\]\((?!https?://|#)([^)]+)\)", readme)
        self.assertTrue(links)
        for link in links:
            self.assertTrue((ROOT / link).is_file(), link)

    def test_documented_entry_points_exist(self):
        for relative in (
            "scripts/install.ps1",
            "scripts/start.ps1",
            "scripts/uninstall.ps1",
            "scripts/pk.ps1",
            "examples/demo.py",
            "examples/specswarm-checklist.md",
            "examples/goal-contract.example.json",
            "docs/images/plotkeeper-desktop.png",
            "docs/images/plotkeeper-mobile.png",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_machine_specific_source_path_is_not_documented_as_install(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Z:\\Plotkeeper\\scripts\\install.ps1", readme)

    def test_complete_codex_bundle_is_documented_truthfully(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        integration = (ROOT / "integrations" / "codex" / "README.md").read_text(encoding="utf-8")
        for name in ("specswarm", "production-goal-contract", "production-goal-review", "msw", "timebox"):
            self.assertIn(name, (readme + integration).lower())
        self.assertNotIn("adds the `transcendr/slopware-skills` marketplace", integration)
        self.assertTrue((ROOT / "integrations" / "codex" / "bundled" / "dependencies.json").is_file())

    def test_startup_scripts_gate_on_persisted_exact_listener_owner(self):
        install = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        start = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        for source in (install, start):
            self.assertIn("Get-NetTCPConnection", source)
            self.assertIn("Get-CimInstance Win32_Process", source)
            self.assertIn("plotkeeper-owner.json", source)
            self.assertIn("command_line_sha256", source)
            self.assertIn("creation_time", source)
            self.assertIn("unknown or foreign listener", source)
            self.assertNotIn("Test-Dashboard", source)
            self.assertNotIn("plotkeeper-app", source)
            self.assertNotIn("plotkeeper\\.cli", source)
            self.assertNotIn("-match", source)
        self.assertIn("if ($listener) {", install)
        self.assertIn("Stop-OwnedListener $listener", install)
        self.assertIn("runtime\\tmp\\install", install)
        self.assertIn("PIP_CACHE_DIR", install)
        self.assertIn("plotkeeper-connector.json", install)
        self.assertIn("plotkeeper-connector.json", start)
        self.assertNotIn("$legacyPort", install)
        self.assertNotIn("$legacyListener", install)
        self.assertNotIn("[int]$Port = 47831", install)
        self.assertNotIn("[int]$Port = 47831", start)

    def test_panel_receipt_instructions_require_html_proof(self):
        skill = (ROOT / "integrations" / "codex" / "bundled" / "skills" / "specswarm" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("non-empty body", skill)
        self.assertIn('data-testid="plotkeeper-app"', skill)
        self.assertIn("Only after the valid HTML check succeeds", skill)
        self.assertIn("PK:PANEL_OPENED", skill)
        self.assertIn("plotkeeper_cli.py\" connector", skill)


if __name__ == "__main__":
    unittest.main()
