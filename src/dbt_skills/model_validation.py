"""Read-only applied-draft checks and an explicit operator-only parse runner."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .catalog import _document
from .lookup_joins import lookup_request, lookup_column_request, lookup_design
from .current_rows import current_row_design
from .model_drafts import (_bounded, _config, _digest, _file_hash,
                           _model_inventory, _relative, _names, column_mapping, warehouse_alias, render_projection)
from .project import discover_project
from .project_artifacts import inspect_artifacts


def validate_applied(project, draft):
    """Report fixed check codes only; never return file contents or exceptions."""
    checks = []

    def check(name, operation):
        try:
            passed = bool(operation())
        except (ValueError, OSError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
            passed = False
        checks.append({'check': name, 'status': 'passed' if passed else 'failed'})
        return passed

    def envelope():
        _bounded(draft)
        return (draft['schema_version'] == 1 and draft['status'] == 'pending_review'
                and draft['project_root'] == str(project.root) and draft['project_name'] == project.name
                and draft['draft_id'] == _digest({k: v for k, v in draft.items() if k != 'draft_id'}))

    if check('draft_integrity', envelope):
        def revisions():
            _, config = _config(project)
            inputs = draft['preconditions']
            return (isinstance(inputs, list) and 3 <= len(inputs) <= 40 and config in inputs
                    and all(set(i) == {'path', 'sha256'} and _file_hash(i['path']) == i['sha256'] for i in inputs))
        check('input_revisions', revisions)

        def files():
            paths, _ = _config(project)
            entries = draft['files']
            if len(entries) != 2:
                return False
            for entry in entries:
                path = entry['path']
                parts = _relative(path)
                if entry['operation'] != 'create' or not any(path.startswith(p + '/') for p in paths):
                    return False
                target = project.root
                for part in parts:
                    target /= part
                    if target.is_symlink():
                        return False
                content = entry['content'].encode('utf-8')
                if len(content) > 65536 or _file_hash(target) != hashlib.sha256(content).hexdigest():
                    return False
            return True
        check('applied_files', files)

        def inventory():
            paths, _ = _config(project)
            names = _model_inventory(project, paths)
            names.remove(draft['files'][0]['path'])
            return draft['model_inventory'] == {'sha256': _digest(names), 'count': len(names)}
        check('model_inventory', inventory)

        def projection():
            request = draft['request']
            available = {c['name']: c for c in draft['catalog']['selected']['columns']['value']}
            temporal = current_row_design(request, available)
            if temporal is not None and temporal.get('status') == 'needs_clarification':
                return False
            if (temporal is not None or 'current_row' in draft['design']) and draft['design'].get('current_row') != temporal:
                return False
            if draft['design'].get('history') != request['history']:
                return False
            for key in ('columns', 'grain'):
                values = request[key]
                if not isinstance(values, list) or not 1 <= len(values) <= 256 or len(set(values)) != len(values) or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', v) for v in values):
                    return False
            if not set(request['grain']) <= set(request['columns']):
                return False
            manifest = inspect_artifacts(replace(project, manifest_path=Path(draft['source']['path'])))['manifest']
            if manifest.get('status') != 'available' or manifest.get('identity') != 'matched' or manifest.get('sha256') != draft['source']['sha256']:
                return False
            sources = [s for s in manifest['resources'] if s.get('unique_id') == request['source_id'] and s.get('resource_type') == 'source' and s.get('package_name') == project.name]
            if len(sources) != 1 or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', sources[0].get(k, '')) for k in ('source_name', 'name')):
                return False
            entries = draft['files']
            if _names(draft['policy'], request) != [f['path'] for f in entries]:
                return False
            mapping = column_mapping(draft['policy'], request, entries[0]['path'])
            if isinstance(mapping, dict):
                return False
            if 'column_mapping' in draft['design'] or 'column_context' in request:
                output_grain = [next(m['output'] for m in mapping if m['source'] == c) for c in request['grain']]
                if draft['design'].get('column_mapping') != mapping or draft['design'].get('output_grain') != output_grain:
                    return False
            model_paths, _ = _config(project)
            alias = warehouse_alias(draft['policy'], request, entries[0]['path'], manifest, _model_inventory(project, model_paths))
            if alias is not None and alias['status'] != 'resolved':
                return False
            if alias is not None or 'warehouse_alias' in draft['design']:
                if draft['design'].get('warehouse_alias') != alias:
                    return False
            joined = None
            if lookup_request(request):
                return False
            if 'lookup' in request:
                added = column_mapping(draft['policy'], lookup_column_request(request), entries[0]['path'])
                if isinstance(added, dict):
                    return False
                joined = lookup_design(project, manifest, request, draft['catalog'], draft['lookup_catalog'], mapping, added)
                if joined.get('status') == 'needs_clarification' or draft['design'].get('lookup') != joined:
                    return False
            elif 'lookup' in draft['design'] or 'lookup_catalog' in draft:
                return False
            expected = render_projection(request, sources[0], Path(entries[0]['path']).stem, mapping, alias, joined)
            return [f['content'] for f in entries] == list(expected)
        check('projection_contract', projection)
    return {'status': 'passed' if all(c['status'] == 'passed' for c in checks) else 'failed',
            'checks': checks, 'warehouse_validated': False, 'semantic_validation': 'not_performed'}


def run_parse(project, draft, approved_digest, *, executable, profiles_dir, timeout=60):
    """Execute trusted local dbt/project code, not a sandbox or agent tool."""
    def report(status):
        return {'status': status, 'operation': 'dbt_parse', 'warehouse_validated': False}
    if not isinstance(draft, dict) or not approved_digest or draft.get('draft_id') != approved_digest or validate_applied(project, draft)['status'] != 'passed':
        return report('blocked')
    try:
        executable, profiles_dir = Path(executable), Path(profiles_dir)
        if not executable.is_absolute() or not executable.is_file() or not profiles_dir.is_absolute() or not profiles_dir.is_dir() or type(timeout) not in (int, float) or not 1 <= timeout <= 300:
            return report('blocked')
        with tempfile.TemporaryDirectory(prefix='dbt-skills-parse-') as temporary:
            result = subprocess.run([str(executable), 'parse', '--project-dir', str(project.root),
                                     '--profiles-dir', str(profiles_dir), '--target-path', str(Path(temporary) / 'target'),
                                     '--log-path', str(Path(temporary) / 'logs'), '--no-partial-parse',
                                     '--no-send-anonymous-usage-stats'], cwd=project.root, shell=False,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=timeout)
        return report('passed' if result.returncode == 0 and validate_applied(project, draft)['status'] == 'passed' else 'failed')
    except subprocess.TimeoutExpired:
        return report('timeout')
    except (OSError, ValueError, TypeError):
        return report('unavailable')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'parse'])
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--draft', required=True)
    parser.add_argument('--approve')
    parser.add_argument('--dbt-executable')
    parser.add_argument('--profiles-dir')
    parser.add_argument('--timeout', type=int, default=60)
    args = parser.parse_args(argv)
    try:
        project = discover_project(args.project_dir)
        draft, _ = _document(args.draft)
        result = (validate_applied(project, draft) if args.command == 'check' else
                  run_parse(project, draft, args.approve, executable=args.dbt_executable,
                            profiles_dir=args.profiles_dir, timeout=args.timeout))
    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
        result = {'status': 'failed', 'warehouse_validated': False}
    print(json.dumps(result))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
