#!/usr/bin/env python3
"""Build a platform-specific frozen backend; run with the installed backend venv."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--frontend', required=True, type=Path)
args = p.parse_args()
server = args.frontend.resolve() / 'server'
server.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='uol-build-') as scratch:
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--name', 'uol-backend',
        '--paths', str(root / 'src'), '--add-data', str(root / 'src/dbt_skills/*.json') + ':dbt_skills',
        '--collect-data', 'mcp', '--collect-all', 'sqlcipher3', '--collect-all', 'keyring',
        '--collect-all', 'jsonschema', '--collect-all', 'referencing', '--collect-all', 'jsonschema_specifications',
        '--distpath', str(server), '--workpath', str(Path(scratch) / 'work'), '--specpath', scratch,
        str(root / 'scripts/backend-entry.py')], check=True)
fixtures = server / 'fixtures'
fixtures.mkdir(exist_ok=True)
shutil.copytree(root / 'examples/data-model-workflow', fixtures / 'project', dirs_exist_ok=True)
shutil.copy2(root / 'examples/uol-workspace/fixture.json', fixtures / 'application.json')
print('Built backend and copied explicit fictional fixtures. No preview configuration was enabled.')
