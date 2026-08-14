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
            matcher = re.search(
                r"function Test-CreationTimeMatch\(\$IdentityValue, \$RecordValue\) \{.*?\n\}",
                source,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(matcher, script)
            probe = match.group(0) + "\n" + matcher.group(0) + r'''
$a = Get-CreationTimeUtcTicks "08/13/2026 23:06:49"
$b = Get-CreationTimeUtcTicks "8/13/2026 11:06:49 PM"
$local = [DateTime]::ParseExact("08/13/2026 23:06:49", "MM/dd/yyyy HH:mm:ss", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeLocal)
$iso = $local.ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)
$c = Get-CreationTimeUtcTicks $iso
$bad = Get-CreationTimeUtcTicks "not-a-time"
$priorCulture = [Globalization.CultureInfo]::CurrentCulture
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo("de-DE")
$legacyNonUs = Get-CreationTimeUtcTicks "13.08.2026 23:06:49"
$expectedNonUs = ([DateTime]::Parse("13.08.2026 23:06:49", [Globalization.CultureInfo]::GetCultureInfo("de-DE"), [Globalization.DateTimeStyles]::AssumeLocal)).ToUniversalTime().Ticks
[Threading.Thread]::CurrentThread.CurrentCulture = $priorCulture
$identityWithFraction = $local.AddTicks(7362380)
$legacyFractionMatch = Test-CreationTimeMatch $identityWithFraction "08/13/2026 23:06:49"
$exactFractionMatch = Test-CreationTimeMatch $identityWithFraction $identityWithFraction.ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)
$exactMismatch = Test-CreationTimeMatch $identityWithFraction $local.ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)
$badText = if ($null -eq $bad) { "NULL" } else { [string]$bad }
Write-Output "${a}|${b}|${c}|${badText}|${legacyNonUs}|${expectedNonUs}|${legacyFractionMatch}|${exactFractionMatch}|${exactMismatch}"
'''
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", probe],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            a, b, c, bad, legacy_non_us, expected_non_us, legacy_fraction, exact_fraction, exact_mismatch = result.stdout.strip().split("|")
            self.assertEqual(a, b)
            self.assertEqual(b, c)
            self.assertEqual(bad, "NULL")
            self.assertEqual(legacy_non_us, expected_non_us)
            self.assertEqual(legacy_fraction, "True")
            self.assertEqual(exact_fraction, "True")
            self.assertEqual(exact_mismatch, "False")

        start = START.read_text(encoding="utf-8")
        self.assertIn('ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)', start)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "requires Windows PowerShell")
    def test_legacy_wrapper_record_requires_exact_direct_listener_child(self):
        source = INSTALL.read_text(encoding="utf-8")
        names = (
            "Get-TextSha256",
            "Test-SamePath",
            "Get-CreationTimeUtcTicks",
            "Test-CreationTimeMatch",
            "Test-PlotkeeperOwner",
        )
        functions = []
        for name in names:
            match = re.search(rf"function {name}\([^)]*\) \{{.*?\n\}}", source, flags=re.DOTALL)
            self.assertIsNotNone(match, name)
            functions.append(match.group(0))
        probe = "\n".join(functions) + r'''
$Root = "Z:\Fixture"
$connectorPath = "Z:\Fixture\runtime\plotkeeper-connector.json"
$command = '"Z:\Fixture\.venv\Scripts\python.exe" -m plotkeeper.cli serve --port 53327'
$script:parentId = 100
$script:childParentId = 100
$script:record = [pscustomobject]@{
  pid = 100; port = 53327; host = "127.0.0.1"; root = $Root; connector_path = $connectorPath
  executable = "Z:\Fixture\.venv\Scripts\python.exe"; creation_time = "08/13/2026 23:06:49"
  command_line_sha256 = Get-TextSha256 $command
}
function Read-OwnerRecord { return $script:record }
function Get-ProcessIdentity([int]$ListenerProcessId) {
  if ($ListenerProcessId -eq 100) { return [pscustomobject]@{ ProcessId=100; ParentProcessId=1; ExecutablePath="Z:\Fixture\.venv\Scripts\python.exe"; CreationDate=[datetime]"2026-08-13T23:06:49.736"; CommandLine=$command } }
  if ($ListenerProcessId -eq 200) { return [pscustomobject]@{ ProcessId=200; ParentProcessId=$script:childParentId; ExecutablePath="C:\Python\python.exe"; CreationDate=[datetime]"2026-08-13T23:06:49.736"; CommandLine=$command } }
  return $null
}
$accepted = Test-PlotkeeperOwner 200 53327
$script:childParentId = 999
$wrongParent = Test-PlotkeeperOwner 200 53327
$script:childParentId = 100
$script:record.command_line_sha256 = "00"
$wrongCommand = Test-PlotkeeperOwner 200 53327
Write-Output "${accepted}|${wrongParent}|${wrongCommand}"
'''
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", probe],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "True|False|False")

        start = START.read_text(encoding="utf-8")
        self.assertIn("pid = [int]$listenerProcessId", start)
        self.assertIn("Get-ListenerPid", start)

    def test_installer_waits_for_authoritative_owner_record(self):
        source = INSTALL.read_text(encoding="utf-8")
        self.assertIn("did not publish a valid owner record", source)
        health_gate = source.index('if (-not $healthy)')
        owner_gate = source.index('if (-not $owned) { throw')
        success = source.index('Write-Output "Plotkeeper installed')
        self.assertLess(health_gate, owner_gate)
        self.assertLess(owner_gate, success)


if __name__ == "__main__":
    unittest.main()
