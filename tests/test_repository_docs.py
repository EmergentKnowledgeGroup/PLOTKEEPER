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
        expected_contract_path = pointer["contract_path"]
        self.assertEqual(expected_contract_path, f"runtime/goal-contracts/{pointer['contract_id']}.json")
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

    def test_package_verification_precedes_listener_and_start_mutation(self):
        install = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        start = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        self.assertLess(install.index("$priorOwner = Read-OwnerRecord"), install.index("-m pip install"))
        self.assertLess(install.index("doctor --source-root"), install.index("Stop-OwnedListener $priorListener"))
        self.assertLess(install.index("Stop-OwnedListener $priorListener"), install.index("ensure_connector"))
        self.assertLess(start.index("doctor --source-root"), start.index("ensure_connector"))
        self.assertLess(start.index("$priorOwner = Read-OwnerRecord"), start.index("$listener = Get-ListenerPid"))
        self.assertIn("Stop-OwnedListener $priorListener ([int]$priorOwner.port)", start)

    def test_supported_launchers_use_verified_installed_package(self):
        for name in ("install.ps1", "start.ps1", "pk.ps1"):
            source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("-I -m plotkeeper.cli doctor --source-root", source)
            self.assertNotIn(" -m plotkeeper.cli", source.replace("-I -m plotkeeper.cli", ""))
        install = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("--force-reinstall --no-deps", install)
        self.assertIn("if (-not $NoStartup)", install)
        self.assertIn("if ($StopOnly)", install)

    @unittest.skipUnless(
        os.name == "nt" and shutil.which("powershell.exe") and shutil.which("py"),
        "requires Windows PowerShell and the Python launcher",
    )
    def test_installer_without_port_persists_auto_selected_loopback_connector(self):
        temp_root = ROOT / "runtime" / "tmp" / "tests" / f"no-port-{uuid.uuid4().hex}"
        checkout = temp_root / "checkout"
        sessions = temp_root / "empty-sessions"
        sessions.mkdir(parents=True)
        process_temp = temp_root / "process-temp"
        process_temp.mkdir()
        env = os.environ.copy()
        env.update(TEMP=str(process_temp), TMP=str(process_temp), PIP_CACHE_DIR=str(process_temp),
                   PLOTKEEPER_SESSIONS=str(sessions))
        env.pop("PYTHONPATH", None)
        try:
            shutil.copytree(
                ROOT,
                checkout,
                ignore=shutil.ignore_patterns(".git", ".venv", "runtime", "build", "*.egg-info", "__pycache__", "*.pyc"),
            )
            python = subprocess.check_output(
                ["py", "-3", "-I", "-c", "import sys; print(sys.executable)"], text=True, env=env,
            ).strip()
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(checkout / "scripts" / "install.ps1"), "-Python", python,
                    "-NoStartup", "-Sessions", str(sessions),
                ],
                capture_output=True, text=True, timeout=180, check=False, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            connector = json.loads(
                (checkout / "runtime" / "plotkeeper-connector.json").read_text(encoding="utf-8")
            )
            self.assertEqual(connector["host"], "127.0.0.1")
            self.assertGreater(int(connector["port"]), 0)
            self.assertEqual(connector["url"], f"http://127.0.0.1:{connector['port']}")
            owner_path = checkout / "runtime" / "plotkeeper-owner.json"
            first_owner = json.loads(owner_path.read_text(encoding="utf-8-sig"))
            first_pid = int(first_owner["pid"])
            tcp_pid_command = (
                "(Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 "
                f"-LocalPort {int(connector['port'])} -ErrorAction Stop | "
                "Select-Object -First 1).OwningProcess"
            )
            first_tcp_pid = int(subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command", tcp_pid_command], text=True, env=env,
            ).strip())
            self.assertEqual(first_owner["port"], connector["port"])
            self.assertEqual(first_pid, first_tcp_pid)

            connector_bytes = (checkout / "runtime" / "plotkeeper-connector.json").read_bytes()
            failed_package = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(checkout / "scripts" / "install.ps1"),
                 "-NoStartup", "-Sessions", str(sessions), "-WheelPath", str(temp_root / "missing.whl")],
                cwd=temp_root, env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertNotEqual(failed_package.returncode, 0, failed_package.stdout + failed_package.stderr)
            self.assertEqual((checkout / "runtime" / "plotkeeper-connector.json").read_bytes(), connector_bytes)
            self.assertEqual(json.loads(owner_path.read_text(encoding="utf-8-sig")), first_owner)

            venv_python = checkout / ".venv" / "Scripts" / "python.exe"
            installed_cli = checkout / ".venv" / "Lib" / "site-packages" / "plotkeeper" / "cli.py"
            installed_cli.write_text(installed_cli.read_text(encoding="utf-8") + "\n# synthetic stale copy\n", encoding="utf-8")
            doctor_args = [str(venv_python), "-I", "-m", "plotkeeper.cli", "doctor", "--source-root", str(checkout)]
            stale = subprocess.run(doctor_args, cwd=temp_root, env=env, capture_output=True, text=True, check=False)
            self.assertNotEqual(stale.returncode, 0, stale.stdout + stale.stderr)
            blocked = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(checkout / "scripts" / "start.ps1"), "-Sessions", str(sessions)],
                cwd=temp_root, env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
            self.assertIn("verification failed", blocked.stdout + blocked.stderr)
            self.assertEqual(json.loads(owner_path.read_text(encoding="utf-8-sig")), first_owner)
            blocked_cli = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(checkout / "scripts" / "pk.ps1"), "status"],
                cwd=temp_root, env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertNotEqual(blocked_cli.returncode, 0, blocked_cli.stdout + blocked_cli.stderr)
            self.assertIn("verification failed", blocked_cli.stdout + blocked_cli.stderr)
            # Old setuptools build output must not put removed files back into the wheel.
            stale_build = checkout / "build" / "lib" / "plotkeeper"
            stale_build.mkdir(parents=True)
            (stale_build / "obsolete.py").write_text("OBSOLETE = True\n", encoding="utf-8")

            second = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(checkout / "scripts" / "install.ps1"),
                    "-Python", python, "-Port", str(connector["port"]),
                    "-NoStartup", "-Sessions", str(sessions),
                ],
                capture_output=True, text=True, timeout=180, check=False, env=env,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            parity = subprocess.run(doctor_args, cwd=temp_root, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(parity.returncode, 0, parity.stdout + parity.stderr)
            self.assertTrue(json.loads(parity.stdout)["ok"])
            self.assertFalse((installed_cli.parent / "obsolete.py").exists())
            console = subprocess.run(
                [str(venv_python.parent / "plotkeeper.exe"), "doctor", "--source-root", str(checkout)],
                cwd=temp_root, env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(console.returncode, 0, console.stdout + console.stderr)
            self.assertEqual(json.loads(console.stdout)["active_package"], json.loads(parity.stdout)["active_package"])
            supported_cli = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(checkout / "scripts" / "pk.ps1"), "doctor"],
                cwd=temp_root, env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            self.assertEqual(supported_cli.returncode, 0, supported_cli.stdout + supported_cli.stderr)
            self.assertTrue(json.loads(supported_cli.stdout)["ok"])
            second_owner = json.loads(owner_path.read_text(encoding="utf-8-sig"))
            second_pid = int(second_owner["pid"])
            second_tcp_pid = int(subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command", tcp_pid_command], text=True, env=env,
            ).strip())
            self.assertEqual(second_pid, second_tcp_pid)
            self.assertNotEqual(first_pid, second_pid)
            first_alive = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-Command",
                    f"if (Get-Process -Id {first_pid} -ErrorAction SilentlyContinue) {{ exit 1 }}",
                ],
                capture_output=True, text=True, check=False, env=env,
            )
            self.assertEqual(first_alive.returncode, 0, first_alive.stdout + first_alive.stderr)
        finally:
            install_script = checkout / "scripts" / "install.ps1"
            if install_script.is_file():
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(install_script), "-StopOnly", "-NoStartup"],
                    capture_output=True, text=True, timeout=60, check=True, env=env,
                )
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
