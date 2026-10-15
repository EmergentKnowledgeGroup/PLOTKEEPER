import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell.exe'), 'Windows installer boundary')
class UpgradeBundleTests(unittest.TestCase):
    def test_fresh_repeat_orphan_repair_rollback_and_tamper(self):
        temporary_parent = ROOT / 'runtime/tmp'
        temporary_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_parent) as td:
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
                       '-NoStartup', '-StartupRegistryPath', 'UnusedProvider:\\NoRegistryAccess',
                       '-Sessions', str(sessions), '-ConfirmInstall']
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
                self.assertFalse((backup / 'startup.json').exists())
                rollback = subprocess.run(command + ['-Action', 'Rollback', '-Backup', str(backup)],
                                          env=env, capture_output=True, text=True)
                self.assertEqual(rollback.returncode, 0, rollback.stdout + rollback.stderr)
                self.assertEqual(cli.read_bytes(), old_cli)
                self.assertTrue(orphan.exists())
                again = subprocess.run(command + ['-Action', 'Rollback', '-Backup', str(backup)],
                                       env=env, capture_output=True, text=True)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertIn('already restored', again.stdout)
                self.assertTrue(orphan.exists())
                self.assertTrue((target / '.venv/Scripts/python.exe').is_file())
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

    def test_startup_snapshot_fresh_prior_failure_and_foreign_change(self):
        temporary_parent = ROOT / 'runtime/tmp'
        temporary_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_parent) as td:
            base = Path(td)
            env = os.environ.copy()
            registry_path = 'HKCU:\\Software\\Plotkeeper\\Tests\\' + uuid.uuid4().hex
            env.update(TEMP=td, TMP=td, PIP_CACHE_DIR=td, PYTHONDONTWRITEBYTECODE='1',
                       PLOTKEEPER_TEST_STARTUP_KEY=registry_path)

            def registry(script, value=None):
                registry_env = env.copy()
                if value is not None:
                    registry_env['PLOTKEEPER_TEST_STARTUP_VALUE'] = value
                result = subprocess.run(
                    ['powershell.exe', '-NoProfile', '-Command', script], env=registry_env,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout.strip()

            def read_startup():
                return json.loads(registry(
                    '$key=Get-Item -LiteralPath $env:PLOTKEEPER_TEST_STARTUP_KEY -ErrorAction SilentlyContinue; '
                    '$exists=$key -and ($key.GetValueNames() -contains "Plotkeeper"); '
                    '$value=if($exists){$key.GetValue("Plotkeeper")}else{$null}; '
                    '@{exists=[bool]$exists;value=$value}|ConvertTo-Json -Compress'
                ))

            def write_startup(value):
                registry(
                    'New-Item -Path $env:PLOTKEEPER_TEST_STARTUP_KEY -Force|Out-Null; '
                    'New-ItemProperty -LiteralPath $env:PLOTKEEPER_TEST_STARTUP_KEY -Name Plotkeeper '
                    '-Value $env:PLOTKEEPER_TEST_STARTUP_VALUE -PropertyType String -Force|Out-Null', value,
                )

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
                       '-StartupRegistryPath', registry_path, '-Sessions', str(sessions), '-ConfirmInstall']

            def run(*arguments):
                return subprocess.run(command + list(arguments), env=env, capture_output=True, text=True)

            def latest_backup():
                return max((base / 'Plotkeeper-upgrade-backups').iterdir(), key=lambda p: p.name)

            try:
                unowned = base / 'foreign-runtime'
                (unowned / 'runtime').mkdir(parents=True)
                sentinel = unowned / 'runtime/private.txt'
                sentinel.write_text('not Plotkeeper', encoding='utf-8')
                unowned_command = command.copy()
                unowned_command[unowned_command.index('-TargetRoot') + 1] = str(unowned)
                denied = subprocess.run(unowned_command, env=env, capture_output=True, text=True)
                self.assertNotEqual(denied.returncode, 0, denied.stdout + denied.stderr)
                self.assertIn('Nonempty target', denied.stdout + denied.stderr)
                self.assertEqual(sentinel.read_text(encoding='utf-8'), 'not Plotkeeper')
                self.assertFalse((unowned / 'runtime/plotkeeper-install.json').exists())
                self.assertFalse(read_startup()['exists'])
                fresh = run()
                self.assertEqual(fresh.returncode, 0, fresh.stdout + fresh.stderr)
                fresh_backup = latest_backup()
                snapshot = json.loads((fresh_backup / 'startup.json').read_text(encoding='utf-8-sig'))
                self.assertFalse(snapshot['existed'])
                self.assertEqual(read_startup()['value'], snapshot['installed_value'])
                rolled_back = run('-Action', 'Rollback', '-Backup', str(fresh_backup))
                self.assertEqual(rolled_back.returncode, 0, rolled_back.stdout + rolled_back.stderr)
                self.assertFalse(read_startup()['exists'])

                self.assertFalse((target / 'plotkeeper/cli.py').exists())
                marker = json.loads((target / 'runtime/plotkeeper-install.json').read_text(encoding='utf-8-sig'))
                self.assertEqual(marker['schema'], 'plotkeeper.install.v1')
                self.assertEqual(Path(marker['target']), target)
                # The prior command is an exact owned command but has distinct old arguments.
                prior = (f'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File '
                         f'"{target / "scripts/start.ps1"}" -Python "{target / ".venv/Scripts/python.exe"}" -Port 54321')
                write_startup(prior)
                installed = run()
                # Rerun must repair this same fresh-rollback target with retained runtime and no cli.py.
                self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
                prior_backup = latest_backup()
                installed_value = read_startup()['value']
                self.assertNotEqual(installed_value, prior)
                write_startup('foreign replacement command')
                refused = run('-Action', 'Rollback', '-Backup', str(prior_backup))
                self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
                self.assertIn('foreign entry', refused.stdout + refused.stderr)
                self.assertEqual(read_startup()['value'], 'foreign replacement command')
                self.assertTrue((target / 'plotkeeper/cli.py').is_file())
                write_startup(installed_value)
                restored = run('-Action', 'Rollback', '-Backup', str(prior_backup))
                self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
                self.assertEqual(read_startup()['value'], prior)

                # Hash-valid synthetic exception immediately after the real registration step.
                failed_installer = bundle / 'source/scripts/install.ps1'
                normal_installer = failed_installer.read_bytes()
                failed_installer.write_text(
                    normal_installer.decode('utf-8').replace(
                        'function Test-Health {', 'throw "Synthetic failure after startup registration"\nfunction Test-Health {'
                    ), encoding='utf-8',
                )
                manifest_path = bundle / 'manifest.json'
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                for entry in manifest['files']:
                    if entry['path'] == 'scripts/install.ps1':
                        entry['sha256'] = hashlib.sha256(failed_installer.read_bytes()).hexdigest()
                manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
                failed = run()
                self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
                self.assertIn('Synthetic failure after startup registration', failed.stdout + failed.stderr)
                self.assertEqual(read_startup()['value'], prior)
                self.assertFalse((target / 'plotkeeper/cli.py').exists())
                # The automatic failure restore also leaves a safely repairable marked target.
                failed_installer.write_bytes(normal_installer)
                for entry in manifest['files']:
                    if entry['path'] == 'scripts/install.ps1':
                        entry['sha256'] = hashlib.sha256(failed_installer.read_bytes()).hexdigest()
                manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
                repaired = run()
                self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
                self.assertTrue((target / 'plotkeeper/cli.py').is_file())
            finally:
                subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                str(bundle / 'source/scripts/install.ps1'), '-InstallRoot', str(target), '-StopOnly'],
                               env=env, capture_output=True, check=True)
                # Delete only this validated, UUID-named fixture key, never the real Run key.
                registry(
                    '$prefix="HKCU:\\Software\\Plotkeeper\\Tests\\"; $key=$env:PLOTKEEPER_TEST_STARTUP_KEY; '
                    'if(-not $key.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -or '
                    '$key.Substring($prefix.Length) -notmatch "^[0-9a-f]{32}$"){throw "Unsafe test key"}; '
                    'if(Test-Path -LiteralPath $key){Remove-Item -LiteralPath $key -Recurse -Force}'
                )
