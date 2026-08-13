import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "plotkeeper" / "web"


def media_blocks(stylesheet: str, condition: str) -> list[str]:
    """Return balanced @media bodies without relying on a brittle regex."""
    marker = f"@media {condition}"
    blocks: list[str] = []
    search_from = 0
    while True:
        start = stylesheet.find(marker, search_from)
        if start < 0:
            return blocks
        opening = stylesheet.find("{", start + len(marker))
        if opening < 0:
            raise ValueError(f"unterminated media rule: {condition}")
        depth = 1
        index = opening + 1
        quote: str | None = None
        escaped = False
        in_comment = False
        while index < len(stylesheet) and depth:
            char = stylesheet[index]
            next_char = stylesheet[index + 1] if index + 1 < len(stylesheet) else ""
            if in_comment:
                if char == "*" and next_char == "/":
                    in_comment = False
                    index += 2
                    continue
            elif quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char == "/" and next_char == "*":
                in_comment = True
                index += 2
                continue
            elif char in "'\"":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth:
            raise ValueError(f"unterminated media rule: {condition}")
        blocks.append(stylesheet[opening + 1:index - 1])
        search_from = index


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
        self.assertIn("Select an active run…", self.js)
        self.assertIn("/api/open-browser", self.js)
        self.assertIn('id="pop-out"', self.index)
        self.assertIn('aria-label="Open this exact Plotkeeper surface in a standalone window"', self.index)
        self.assertIn('title="Open this exact Plotkeeper surface in a standalone window"', self.index)
        self.assertNotIn("default browser", self.index)
        self.assertIn('id="reconstruct-plan"', self.index)
        self.assertIn('/reconstruct-plan', self.js)

    def test_accessibility_and_mobile_contract(self):
        self.assertIn('aria-live="polite"', self.index)
        self.assertGreaterEqual(len(re.findall(r'aria-expanded', self.index + self.js)), 2)
        self.assertIn("@media (max-width: 47.99rem)", self.css)
        self.assertIn("min-height: 2.75rem", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_run_picker_is_viewport_bounded_and_detail_stays_below_board(self):
        self.assertIn('role="listbox"', self.index)
        self.assertIn('aria-haspopup="listbox"', self.index)
        self.assertIn("max-width: 100%", self.css)
        self.assertIn("overflow-x: hidden", self.css)
        self.assertIn("overflow-wrap: anywhere", self.css)
        self.assertNotIn("word-break: break-word", self.css)
        self.assertNotIn("clip: rect", self.css)
        self.assertIn("-webkit-line-clamp: 2", self.css)
        self.assertRegex(self.css, r"\.goal-copy h1[^}]+-webkit-line-clamp:\s*2")
        desktop_rules = media_blocks(self.css, "(min-width: 48rem)")
        self.assertTrue(desktop_rules)
        self.assertTrue(all("grid-template-columns" not in rule for rule in desktop_rules))
        self.assertLess(self.index.index('id="board-shell"'), self.index.index('class="inspector"'))
        self.assertIn("setPickerOpen", self.js)
        self.assertIn("ArrowDown", self.js)
        self.assertIn("Escape", self.js)

    def test_no_external_runtime_dependency(self):
        self.assertNotRegex(self.index, r"(?:https?:)?//[^\"']+(?:script|stylesheet)")
        self.assertNotIn("React", self.js)
        self.assertNotIn("innerHTML = user", self.js)


if __name__ == "__main__":
    unittest.main()
