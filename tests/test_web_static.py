import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class PlotkeeperStaticSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (WEB / "index.html").read_text(encoding="utf-8")
        cls.css = (WEB / "styles.css").read_text(encoding="utf-8")
        cls.js = (WEB / "app.js").read_text(encoding="utf-8")

    def test_static_files_exist_and_are_linked(self):
        self.assertTrue((WEB / "index.html").is_file())
        self.assertTrue((WEB / "styles.css").is_file())
        self.assertTrue((WEB / "app.js").is_file())
        self.assertIn('href="/web/styles.css"', self.index)
        self.assertIn('src="/web/app.js"', self.index)

    def test_dashboard_has_required_human_workflow_regions(self):
        for marker in ("Working now", "Request check-in", "Collapse all", "Summary", "Timeline", "Evidence", "Reports", "Agents"):
            self.assertIn(marker, self.index)
        for marker in ("run-progress-bar", "workstreams", "detail-timeline", "detail-evidence", "detail-reports", "detail-agents"):
            self.assertIn(f'id="{marker}"', self.index)
        for marker in ("goal-contract", "contract-goal", "contract-invariants"):
            self.assertIn(f'id="{marker}"', self.index)

    def test_api_contract_and_truthful_missing_state_are_present(self):
        self.assertIn("/api/runs", self.js)
        self.assertIn("/api/runs/${encodeURIComponent(id)}", self.js)
        self.assertIn("No evidence attached. Plotkeeper will not infer success.", self.js)
        self.assertIn("No agent identities attached.", self.js)
        self.assertIn("payload?.tasks", self.js)
        self.assertIn("payload?.events", self.js)
        self.assertIn("payload?.sessions", self.js)
        self.assertIn("payload?.contract", self.js)

    def test_accessibility_and_mobile_contract(self):
        self.assertIn('aria-live="polite"', self.index)
        self.assertGreaterEqual(len(re.findall(r'aria-expanded', self.index + self.js)), 2)
        self.assertIn("@media (max-width: 47.99rem)", self.css)
        self.assertIn("min-height: 2.75rem", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_no_external_runtime_dependency(self):
        self.assertNotRegex(self.index, r"(?:https?:)?//[^\"']+(?:script|stylesheet)")
        self.assertNotIn("React", self.js)
        self.assertNotIn("innerHTML = user", self.js)


if __name__ == "__main__":
    unittest.main()
