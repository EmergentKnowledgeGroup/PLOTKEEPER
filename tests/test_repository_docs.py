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


if __name__ == "__main__":
    unittest.main()
