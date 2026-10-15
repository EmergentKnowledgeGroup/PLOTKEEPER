import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell.exe'), 'Windows installer boundary')
class UpgradeBundleTests(unittest.TestCase):
    def test_fresh_repeat_orphan_repair_rollback_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = os.environ.copy()
            env.update(TEMP=td, TMP=td, PIP_CACHE_DIR=td, PYTHONDONTWRITEBYTECODE='1')
            bundle = base / 'bundle'
            build = subprocess.run([sys.executable, str(ROOT / 'scripts/build-installer.py'),
                                    '--output', str(bundle)], cwd=ROOT, env=env,
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            target = base / 'installed copy'
            sessions = base / 'empty-sessions'
            sessions.mkdir()
            env['PLOTKEEPER_SESSIONS'] = str(sessions)
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                       str(bundle / 'Install-Plotkeeper.ps1'), '-TargetRoot', str(target),
                       '-NoStartup', '-Sessions', str(sessions), '-ConfirmInstall']
            try:
                first = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                connector = target / 'runtime/plotkeeper-connector.json'
                private = target / 'runtime/private-sentinel.txt'
                private.write_text('preserve', encoding='utf-8')
                unknown = target / 'my-local-work.md'
                unknown.write_text('unique work', encoding='utf-8')
                cli = target / 'plotkeeper/cli.py'
                old_cli = cli.read_bytes() + b'\n# previous local source\n'
                cli.write_bytes(old_cli)
                orphan = target / '.venv/Lib/site-packages/plotkeeper/obsolete.py'
                orphan.write_text('old module', encoding='utf-8')
                before_connector = connector.read_bytes()
                second = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertFalse(orphan.exists())
                self.assertEqual(connector.read_bytes(), before_connector)
                self.assertEqual(unknown.read_text(), 'unique work')
                self.assertEqual(private.read_text(), 'preserve')
                backup = max((base / 'Plotkeeper-upgrade-backups').iterdir(), key=lambda p: p.name)
                rollback = subprocess.run(command + ['-Action', 'Rollback', '-Backup', str(backup)],
                                          env=env, capture_output=True, text=True)
                self.assertEqual(rollback.returncode, 0, rollback.stdout + rollback.stderr)
                self.assertEqual(cli.read_bytes(), old_cli)
                self.assertTrue(orphan.exists())
                self.assertEqual(connector.read_bytes(), before_connector)
                self.assertEqual(private.read_text(), 'preserve')
                self.assertEqual(unknown.read_text(), 'unique work')
                # Hash rejection is before target mutation, not a rollback claim.
                (bundle / 'source/plotkeeper/cli.py').write_text('tampered', encoding='utf-8')
                denied = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn('hash mismatch', denied.stderr + denied.stdout)
                self.assertEqual(cli.read_bytes(), old_cli)
            finally:
                installer = bundle / 'source/scripts/install.ps1'
                subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                str(installer), '-InstallRoot', str(target), '-StopOnly'],
                               env=env, capture_output=True, check=True)
