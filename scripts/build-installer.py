"""Build a source + wheel installer from this checkout, never from runtime data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--target', help='Optional target for the Windows double-click launcher')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.exists():
        parser.error('Choose a new output directory; existing bundles are never overwritten.')
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    # Runtime records and checkpoints are source-review artifacts, not install payload.
    files = [f for f in files if f and not f.startswith(('.github/', 'runtime/', 'tests/'))
             and f not in {'.gitignore', '.gitattributes'}]
    missing = [f for f in ('plotkeeper/doctor.py', 'plotkeeper/review_runner.py',
                           'scripts/upgrade.ps1', 'docs/AGENT_REPAIR.md') if f not in files]
    if missing:
        parser.error('Commit the new release source before building: ' + ', '.join(missing))
    # Only payload paths matter. Unrelated dirty checkpoints/tests and ignored
    # private runtime must not block a build, but the shipped files must be HEAD.
    dirty = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', *files], cwd=root,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if dirty.returncode:
        parser.error('Commit installer payload changes first; the manifest commit must match its source.')
    output.mkdir(parents=True)
    records = []
    for name in sorted(files):
        source = root / name
        destination = output / 'source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        records.append({'path': name, 'sha256': digest(destination)})
    wheels = output / 'wheels'
    wheels.mkdir()
    subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', str(wheels),
                    str(output / 'source')], check=True, cwd=root)
    wheel, = wheels.glob('plotkeeper-*.whl')
    for generated in (output / 'source' / 'build', output / 'source' / 'plotkeeper.egg-info'):
        if generated.is_dir():
            shutil.rmtree(generated)
    import tomllib
    version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    manifest = {'schema': 'plotkeeper.installer.v1', 'version': version,
                'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                'files': records, 'wheel': {'path': str(wheel.relative_to(output)).replace('\\', '/'),
                                            'sha256': digest(wheel)}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    shutil.copy2(root / 'scripts/upgrade.ps1', output / 'Install-Plotkeeper.ps1')
    if args.target:
        # Avoid shell interpolation for arbitrary targets. PowerShell receives
        # a literal JSON string from a private generated config, not a command.
        (output / 'target.json').write_text(json.dumps({'target': args.target}), encoding='utf-8')
        (output / 'Install-Plotkeeper.cmd').write_text(
            '@echo off\r\ncd /d "%~dp0"\r\n'
            'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '
            '"& .\\Install-Plotkeeper.ps1 -TargetRoot ((Get-Content -LiteralPath .\\target.json -Raw | ConvertFrom-Json).target)"\r\n'
            'pause\r\n', encoding='utf-8')
    print(json.dumps({'bundle': str(output), 'wheel_sha256': digest(wheel), 'files': len(records)}))


if __name__ == '__main__':
    main()
