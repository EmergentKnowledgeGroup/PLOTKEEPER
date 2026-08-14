from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts" / "install.ps1"
START = ROOT / "scripts" / "start.ps1"


FOREIGN_SERVER = r'''
import http.server
import sys

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'<html data-testid="plotkeeper-app">spoof</html>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass

http.server.ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), Handler).serve_forever()
'''


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def listener_pid(port: int) -> int | None:
    command = (
        "(Get-NetTCPConnection -State Listen "
        f"-LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    return int(value) if value.isdigit() else None


def process_command_line(pid: int) -> str:
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


class ListenerOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.foreign = None
        if os.name != "nt" or not shutil.which("powershell.exe"):
            self.skipTest("requires Windows PowerShell process-boundary tools")
        self.port = free_port()
        self.foreign = subprocess.Popen(
            [sys.executable, "-c", FOREIGN_SERVER, str(self.port), "plotkeeper.cli"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{self.port}/", timeout=0.2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"data-testid=\"plotkeeper-app\"", response.read())
                    break
            except OSError:
                if self.foreign.poll() is not None:
                    self.fail("controlled foreign listener exited before binding")
                time.sleep(0.05)
        else:
            self.fail("controlled foreign listener did not become ready")
        self.assertEqual(listener_pid(self.port), self.foreign.pid)
        self.assertIn("plotkeeper.cli", process_command_line(self.foreign.pid))

    def tearDown(self):
        if self.foreign is not None and self.foreign.poll() is None:
            self.foreign.terminate()
            self.foreign.wait(timeout=5)

    def run_script(self, script: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Python",
                sys.executable,
                "-Port",
                str(self.port),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def assert_foreign_survives(self, script: Path):
        result = self.run_script(script)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unknown or foreign listener", result.stderr + result.stdout)
        self.assertIsNone(self.foreign.poll(), result.stdout + result.stderr)
        self.assertEqual(listener_pid(self.port), self.foreign.pid)

    def test_start_rejects_spoofed_argv_and_html_without_touching_pid(self):
        self.assert_foreign_survives(START)

    def test_install_rejects_spoofed_argv_and_html_before_install_mutation(self):
        self.assert_foreign_survives(INSTALL)


class ListenerOwnerSchemaTests(unittest.TestCase):
    def test_owner_record_schema_is_explicitly_bound(self):
        for script in (INSTALL, START):
            source = script.read_text(encoding="utf-8")
            for field in ("pid", "host", "port", "root", "connector_path", "executable", "creation_time", "command_line_sha256"):
                self.assertIn(field, source)
            self.assertNotIn("Test-Dashboard", source)
            self.assertNotIn("plotkeeper\\.cli", source)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_creation_time_identity_is_locale_independent_and_fail_closed(self):
        for script in (INSTALL, START):
            source = script.read_text(encoding="utf-8")
            match = re.search(
                r"function Get-CreationTimeUtcTicks\(\$Value\) \{.*?\n\}",
                source,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match, script)
            probe = match.group(0) + r'''
$a = Get-CreationTimeUtcTicks "08/13/2026 23:06:49"
$b = Get-CreationTimeUtcTicks "8/13/2026 11:06:49 PM"
$c = Get-CreationTimeUtcTicks "2026-08-14T04:06:49.0000000Z"
$bad = Get-CreationTimeUtcTicks "not-a-time"
$badText = if ($null -eq $bad) { "NULL" } else { [string]$bad }
Write-Output "${a}|${b}|${c}|${badText}"
'''
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", probe],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            a, b, c, bad = result.stdout.strip().split("|")
            self.assertEqual(a, b)
            self.assertEqual(b, c)
            self.assertEqual(bad, "NULL")

        start = START.read_text(encoding="utf-8")
        self.assertIn('ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)', start)


if __name__ == "__main__":
    unittest.main()
