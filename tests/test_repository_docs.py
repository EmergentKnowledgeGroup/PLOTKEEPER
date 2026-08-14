from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
import uuid
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

    def test_release_authority_uses_tracked_pointer(self):
        pointer_path = ROOT / "runtime" / "goal-contracts" / "RELEASE_CONTRACT.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        self.assertEqual(pointer["purpose"], "PLOTKEEPER_PUBLIC_RELEASE")
        self.assertEqual(pointer["contract_id"], "PROD-20260814-plotkeeper-v0112-listener-pid-identity")
        expected_contract_path = "runtime/goal-contracts/PROD-20260814-plotkeeper-v0112-listener-pid-identity.json"
        self.assertEqual(pointer["contract_path"], expected_contract_path)
        contract = json.loads((ROOT / expected_contract_path).read_text(encoding="utf-8"))
        self.assertEqual(pointer["contract_id"], contract["id"])
        workflow = (ROOT / ".github" / "workflows" / "release-verifier.yml").read_text(encoding="utf-8")
        self.assertIn("PLOTKEEPER_CONTRACT_POINTER: runtime/goal-contracts/RELEASE_CONTRACT.json", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s*PLOTKEEPER_CONTRACT\s*:")
        release_docs = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        self.assertIn("filesystem mtime and contract filename ordering are never release authority", release_docs)

    def test_startup_scripts_gate_on_persisted_exact_listener_owner(self):
        install = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        start = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        for source in (install, start):
            self.assertIn("Get-NetTCPConnection", source)
            self.assertNotIn("-LocalAddress 127.0.0.1", source)
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

    def test_explicit_port_replacement_precedes_install_and_start_mutation(self):
        install = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        start = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        self.assertLess(install.index("$priorOwner = Read-OwnerRecord"), install.index("-m pip install"))
        self.assertLess(install.index("Stop-OwnedListener $priorListener"), install.index("ensure_connector"))
        self.assertLess(start.index("$priorOwner = Read-OwnerRecord"), start.index("$listener = Get-ListenerPid"))
        self.assertIn("Stop-OwnedListener $priorListener ([int]$priorOwner.port)", start)

    @unittest.skipUnless(
        os.name == "nt" and shutil.which("powershell.exe") and shutil.which("py"),
        "requires Windows PowerShell and the Python launcher",
    )
    def test_installer_without_port_persists_auto_selected_loopback_connector(self):
        temp_root = ROOT / "runtime" / "tmp" / "tests" / f"no-port-{uuid.uuid4().hex}"
        checkout = temp_root / "checkout"
        startup_key = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
        read_startup = f"(Get-ItemProperty -Path '{startup_key}' -Name Plotkeeper -ErrorAction SilentlyContinue).Plotkeeper"
        prior = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", read_startup],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        try:
            shutil.copytree(
                ROOT,
                checkout,
                ignore=shutil.ignore_patterns(".git", ".venv", "runtime", "__pycache__", "*.pyc"),
            )
            python = subprocess.check_output(
                ["py", "-3", "-c", "import sys; print(sys.executable)"], text=True,
            ).strip()
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(checkout / "scripts" / "install.ps1"), "-Python", python,
                ],
                capture_output=True, text=True, timeout=180, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            connector = json.loads(
                (checkout / "runtime" / "plotkeeper-connector.json").read_text(encoding="utf-8")
            )
            self.assertEqual(connector["host"], "127.0.0.1")
            self.assertGreater(int(connector["port"]), 0)
            self.assertEqual(connector["url"], f"http://127.0.0.1:{connector['port']}")
        finally:
            owner_path = checkout / "runtime" / "plotkeeper-owner.json"
            owner_pid = None
            if owner_path.is_file():
                try:
                    owner_pid = int(json.loads(owner_path.read_text(encoding="utf-8"))["pid"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    owner_pid = None
            uninstall = checkout / "scripts" / "uninstall.ps1"
            if uninstall.is_file():
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(uninstall)],
                    capture_output=True, text=True, timeout=60, check=False,
                )
            if owner_pid:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {owner_pid} -Force -ErrorAction SilentlyContinue"],
                    capture_output=True, text=True, check=False,
                )
            cleanup_env = os.environ.copy()
            cleanup_env["PLOTKEEPER_TEST_CHECKOUT"] = str(checkout)
            subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-Command",
                    "$root=[IO.Path]::GetFullPath($env:PLOTKEEPER_TEST_CHECKOUT); "
                    "Get-Process python,pythonw -ErrorAction SilentlyContinue | "
                    "Where-Object { $_.Path -and [IO.Path]::GetFullPath($_.Path).StartsWith($root,[StringComparison]::OrdinalIgnoreCase) } | "
                    "Stop-Process -Force -ErrorAction SilentlyContinue",
                ],
                env=cleanup_env, capture_output=True, text=True, check=False,
            )
            restore_env = os.environ.copy()
            restore_env["PLOTKEEPER_TEST_PRIOR_STARTUP"] = prior
            restore = (
                f"New-Item -Path '{startup_key}' -Force | Out-Null; "
                "if ($env:PLOTKEEPER_TEST_PRIOR_STARTUP) { "
                f"New-ItemProperty -Path '{startup_key}' -Name Plotkeeper -Value $env:PLOTKEEPER_TEST_PRIOR_STARTUP -PropertyType String -Force | Out-Null "
                f"}} else {{ Remove-ItemProperty -Path '{startup_key}' -Name Plotkeeper -ErrorAction SilentlyContinue }}"
            )
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", restore], env=restore_env, check=False)
            if temp_root.exists():
                shutil.rmtree(temp_root)
            for parent in (temp_root.parent, temp_root.parent.parent):
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()

    def test_panel_receipt_instructions_require_html_proof(self):
        skill = (ROOT / "integrations" / "codex" / "bundled" / "skills" / "specswarm" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("non-empty body", skill)
        self.assertIn('data-testid="plotkeeper-app"', skill)
        self.assertIn("Only after the valid HTML check succeeds", skill)
        self.assertIn("PK:PANEL_OPENED", skill)
        self.assertIn("plotkeeper_cli.py\" connector", skill)


if __name__ == "__main__":
    unittest.main()
