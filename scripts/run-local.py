#!/usr/bin/env python3
"""Start the original React UI and actual encrypted Python application backend."""
import argparse
import base64
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser


def main():
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frontend', type=Path, default=root.parent / 'frontend')
    p.add_argument('--project-dir', type=Path)
    p.add_argument('--demo', action='store_true', help='Explicit fictional fixture, in its own database')
    p.add_argument('--ephemeral', action='store_true', help='Demo only: discard encrypted storage when stopped')
    p.add_argument('--data-dir', type=Path, default=Path.home() / '.uol-workspace')
    p.add_argument('--key-env', help='Environment variable holding a base64 32-byte encryption key; otherwise native keyring')
    p.add_argument('--backend-port', type=int, default=8765)
    p.add_argument('--port', type=int, default=5173)
    p.add_argument('--no-browser', action='store_true')
    args = p.parse_args()
    frontend = args.frontend.resolve()
    if not (frontend / 'package.json').exists(): p.error('Set --frontend to the provided frontend folder')
    if not args.demo and args.project_dir is None: p.error('Choose --project-dir or explicitly enable --demo')
    if args.ephemeral and not args.demo: p.error('--ephemeral is only allowed with --demo')
    if not shutil.which('npm'): p.error('Node.js/npm is required')
    if args.port == args.backend_port: p.error('Frontend and backend ports must be different')
    for name, number, option in [('Frontend', args.port, '--port'), ('Backend', args.backend_port, '--backend-port')]:
        if not 1 <= number <= 65535: p.error(f'{name} port must be between 1 and 65535')
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                # A just-stopped local server may leave accepted connections in
                # TIME_WAIT; match the servers' normal restart semantics.
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', number))
        except OSError:
            p.error(f'{name} port {number} is already in use or unavailable; choose another {option}')
    project = (args.project_dir or root / 'examples/data-model-workflow').resolve()
    runtime = tempfile.TemporaryDirectory(prefix='uol-demo-') if args.ephemeral else None
    data_dir = Path(runtime.name) if runtime else args.data_dir / ('demo' if args.demo else 'live')
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = os.environ.copy()
    env['UOL_LOCAL_TOKEN'] = secrets.token_urlsafe(48)
    env['UOL_BACKEND_PORT'] = str(args.backend_port)
    # Override optional packaged preview config: this launcher owns backend lifecycle.
    env['UOL_PREVIEW_CONFIG'] = str(data_dir / 'disabled-preview-config.json')
    env['PYTHONPATH'] = str(root / 'src') + os.pathsep + env.get('PYTHONPATH', '')
    key_env = args.key_env
    if runtime:
        key_env = 'UOL_EPHEMERAL_KEY'
        env[key_env] = base64.b64encode(secrets.token_bytes(32)).decode()
    command = [sys.executable, '-m', 'dbt_skills.workspace_service', '--project-dir', str(project),
               '--policy', str(project / 'modelling.yml'), '--catalog-config', str(project / 'catalogs.json'),
               '--store', str(data_dir / 'workspace.db'), '--application-store', str(data_dir / 'application.db'),
               '--port', str(args.backend_port)]
    if key_env: command += ['--key-env', key_env]
    if args.demo: command += ['--fixture-state', str(root / 'examples/uol-workspace/fixture.json')]
    backend = frontend_process = None
    try:
        backend = subprocess.Popen(command, env=env, cwd=root)
        for attempt in range(120):
            if backend.poll() is not None: raise RuntimeError('Backend failed; inspect the diagnostic above')
            request = urllib.request.Request(f'http://127.0.0.1:{args.backend_port}/api/application/read', data=b'{}', headers={'Authorization': 'Bearer ' + env['UOL_LOCAL_TOKEN'], 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    if response.status == 200: break
            except OSError: time.sleep(.25)
        else: raise RuntimeError('Backend did not become ready')
        if not (frontend / 'node_modules').exists():
            subprocess.run(['npm', 'ci'], cwd=frontend, check=True)
        frontend_process = subprocess.Popen(['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(args.port), '--strictPort'], cwd=frontend, env=env)
        url = f'http://127.0.0.1:{args.port}'
        # The frontend process starting does not mean its port or API proxy is ready.
        for attempt in range(120):
            if frontend_process.poll() is not None:
                raise RuntimeError(f'Frontend failed to start (exit {frontend_process.returncode}); inspect the diagnostic above')
            if backend.poll() is not None:
                raise RuntimeError('Backend stopped before the frontend became ready')
            request = urllib.request.Request(url + '/api/application/read', data=b'{}', headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError('Frontend API proxy did not become ready')
        print(f'UOL is available at {url}. ' + ('Fictional simulation.' if args.demo else 'Live local workspace.'), flush=True)
        if not args.no_browser: webbrowser.open(url)
        while frontend_process.poll() is None:
            if backend.poll() is not None: raise RuntimeError('Backend stopped; no fallback was used')
            time.sleep(.5)
        if frontend_process.returncode:
            raise RuntimeError(f'Frontend stopped with exit {frontend_process.returncode}')
    except KeyboardInterrupt:
        pass
    finally:
        for child in (frontend_process, backend):
            if child and child.poll() is None:
                child.terminate()
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill(); child.wait()
        if runtime: runtime.cleanup()


if __name__ == '__main__':
    main()
