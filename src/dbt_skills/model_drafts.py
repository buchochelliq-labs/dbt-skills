"""Review-only source projections and an operator-only create-file command."""
import argparse
from copy import deepcopy
import difflib
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
import re
import sys

import yaml

from .catalog import CatalogError, FIELDS, _document, _raw, load_catalog
from .modelling_naming import NamingError, NamingRule, resolve_name
from .modelling_policy import PolicyError, _Loader, load_document
from .project import discover_project
from .project_artifacts import MAX_ARTIFACT_BYTES, inspect_artifacts


class DraftError(ValueError):
    """Static error messages; do not echo untrusted source content."""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _bounded(draft):
    if len(json.dumps(draft, indent=2, ensure_ascii=True, allow_nan=False).encode()) > 1024 * 1024:
        raise DraftError('Draft exceeds the review document byte limit')
    pending, count = [(draft, 0)], 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 16 or count > 20000:
            raise DraftError('Draft exceeds review document structural limits')
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)


def _file_hash(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise DraftError('Draft input must be a regular file')
        total, digest = 0, hashlib.sha256()
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > MAX_ARTIFACT_BYTES:
                raise DraftError('Draft input exceeds artifact size limit')
            digest.update(block)
    return digest.hexdigest()


def _config(project):
    try:
        raw = _raw(project.config_path)
        config = yaml.load(raw.decode('utf-8'), Loader=_Loader)
        paths = config.get('model-paths', ['models'])
        if config.get('name') != project.name or not isinstance(paths, list) or not 1 <= len(paths) <= 32:
            raise DraftError('Invalid project model path configuration')
        for path in paths:
            _relative(path)
        return paths, {'path': str(project.config_path), 'sha256': hashlib.sha256(raw).hexdigest()}
    except (OSError, UnicodeError, yaml.YAMLError, PolicyError, AttributeError, TypeError, CatalogError):
        raise DraftError('Cannot inspect project model paths') from None


def _relative(path):
    if not isinstance(path, str) or not 1 <= len(path) <= 512:
        raise DraftError('Invalid relative model path')
    parts = path.split('/')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*(?:\.(?:sql|yml|yaml))?', p)
           or p.split('.')[0].upper() in reserved for p in parts):
        raise DraftError('Use portable relative model paths')
    return parts


def _target(project, path, model_paths):
    parts = _relative(path)
    if not any(path.startswith(p + '/') for p in model_paths):
        raise DraftError('Draft path must be inside a configured model directory')
    target = project.root
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise DraftError('Symlink model paths are not supported')
        if target != project.root / path and target.exists() and not target.is_dir():
            raise DraftError('Model parent path is not a directory')
    if target.exists():
        raise DraftError('Draft targets must not already exist')
    return target



def _model_inventory(project, model_paths):
    """Names only, never SQL contents; include unparsed SQL and Python models."""
    pending, names, scanned = [], set(), 0
    try:
        for relative in model_paths:
            current = project.root
            for part in _relative(relative):
                current = current / part
                if current.is_symlink():
                    raise DraftError('Symlink model directories are not supported')
            if current.exists():
                if not current.is_dir():
                    raise DraftError('Configured model path is not a directory')
                pending.append(current)
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > 10000:
                        raise DraftError('Model inventory exceeds 10000 entries')
                    if entry.is_symlink():
                        raise DraftError('Symlinks in model directories require manual review')
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif Path(entry.name).suffix.lower() in ('.sql', '.py'):
                        if not entry.is_file(follow_symlinks=False):
                            raise DraftError('Model files must be regular files')
                        names.add(Path(entry.path).relative_to(project.root).as_posix())
    except OSError:
        raise DraftError('Cannot inspect model inventory') from None
    return sorted(names)


def _questions(message, **evidence):
    return {'status': 'needs_clarification', 'questions': [message], **evidence}


def _names(loaded, request):
    document = loaded['document']
    result = []
    for key, target in [('model_rule', 'model_file'), ('properties_rule', 'properties_file')]:
        matches = [r for r in document['naming'] if r['id'] == request[key] and r['target'] == target]
        if len(matches) != 1:
            return _questions('Select a declared naming rule for each output file')
        rule = matches[0]
        name = resolve_name(NamingRule(rule['id'], rule['template'], document['tokens'], loaded['provenance'], rule.get('bindings', {})), request['values'])
        if name['status'] != 'resolved':
            return _questions('Supply the missing naming tokens', naming=name)
        path = name['value']
        directory = str(PurePosixPath(path).parent)
        if 'directory' in request.get('scope', {}) and request['scope']['directory'] != directory:
            return _questions('Explicit directory scope differs from the rendered output path')
        context = {**request.get('scope', {}), 'directory': directory}
        applicable = []
        for candidate in document['naming']:
            if candidate['target'] != target:
                continue
            scope = candidate.get('scope', {})
            if any(k in context and context[k] != v for k, v in scope.items()):
                continue
            if any(k not in context for k in scope):
                return _questions('Clarify naming rule scope before choosing between rules')
            applicable.append(candidate['id'])
        if applicable != [rule['id']]:
            return _questions('The selected naming rule is out of scope or overlaps another rule')
        result.append(path)
    # Additional conventions constrain the rendered SQL model; never rename it
    # silently or infer applicability from a rule's position in the policy.
    directory = str(PurePosixPath(result[0]).parent)
    context = {**request.get('scope', {}), 'directory': directory}
    groups = {}
    for index, rule in enumerate(document['naming']):
        if rule['target'] in ('model_file', 'properties_file', 'column', 'warehouse_alias'):
            continue
        scope = rule.get('scope', {})
        if any(k in context and context[k] != v for k, v in scope.items()):
            continue
        if any(k not in context for k in scope):
            return _questions('Clarify naming rule scope before checking additional conventions')
        groups.setdefault(rule['target'], []).append((index, rule))
    for target, rules in groups.items():
        if target not in ('model_id', 'directory'):
            return _questions('This projection generator cannot yet enforce the applicable naming target', unsupported_target=target)
        if len(rules) != 1:
            return _questions('Applicable naming constraints overlap; clarify the policy before drafting')
        index, rule = rules[0]
        provenance = {**loaded['provenance'], 'locator': f'/naming/{index}'}
        name = resolve_name(NamingRule(rule['id'], rule['template'], document['tokens'], provenance, rule.get('bindings', {})), request['values'])
        if name['status'] != 'resolved':
            return _questions('Supply the missing naming tokens', naming=name)
        actual = PurePosixPath(result[0]).stem if target == 'model_id' else directory
        if name['value'] != actual:
            return _questions('Rendered model path disagrees with an applicable naming constraint; reconcile the rules or token values',
                              naming_constraint={'target': target, 'rule_id': rule['id'], 'expected': name['value'], 'actual': actual, 'provenance': provenance})
    return result


def column_mapping(loaded, request, model_path):
    """Resolve per-column conventions without implicit tokens or scope overrides."""
    entries = request.get('column_context', {})
    if not isinstance(entries, dict) or len(entries) > 256 or set(entries) - set(request['columns']):
        raise DraftError('Column context must select only projected source columns')
    for entry in entries.values():
        if not isinstance(entry, dict) or set(entry) - {'values', 'scope'}:
            raise DraftError('Column context supports only values and scope mappings')
        for key in ('values', 'scope'):
            values = entry.get(key, {})
            if not isinstance(values, dict) or len(values) > 256 or any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
                raise DraftError('Column context values and scope require string mappings')
    document = loaded['document']
    directory = str(PurePosixPath(model_path).parent)
    global_scope = {**request.get('scope', {}), 'directory': directory}
    mapping = []
    for source in request['columns']:
        entry = entries.get(source, {})
        local_values, local_scope = entry.get('values', {}), entry.get('scope', {})
        if any(k in request['values'] and request['values'][k] != v for k, v in local_values.items()):
            return _questions('Per-column token values conflict with model token values', column=source)
        if any(k in global_scope and global_scope[k] != v for k, v in local_scope.items()):
            return _questions('Per-column scope conflicts with model scope', column=source)
        context = {**global_scope, **local_scope}
        applicable = []
        for index, rule in enumerate(document['naming']):
            if rule['target'] != 'column':
                continue
            scope = rule.get('scope', {})
            if any(k in context and context[k] != v for k, v in scope.items()):
                continue
            if any(k not in context for k in scope):
                return _questions('Clarify column naming rule scope', column=source, rule_id=rule['id'])
            applicable.append((index, rule))
        if len(applicable) > 1:
            return _questions('Applicable column naming rules overlap', column=source)
        if not applicable:
            if local_values:
                return _questions('No applicable column naming rule consumes these token values', column=source)
            mapping.append({'source': source, 'output': source, 'rule_id': None, 'provenance': None})
            continue
        index, rule = applicable[0]
        provenance = {**loaded['provenance'], 'locator': f'/naming/{index}'}
        try:
            name = resolve_name(NamingRule(rule['id'], rule['template'], document['tokens'], provenance, rule.get('bindings', {})), {**request['values'], **local_values})
        except NamingError:
            return _questions('Column token values conflict with bindings or literal naming constraints', column=source, rule_id=rule['id'])
        if name['status'] != 'resolved':
            return _questions('Supply the missing column naming tokens', column=source, naming=name)
        output = name['value']
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', output) is None:
            return _questions('Column rules must render portable SQL identifiers', column=source, rule_id=rule['id'])
        mapping.append({'source': source, 'output': output, 'rule_id': rule['id'], 'provenance': provenance})
    if len({m['output'].casefold() for m in mapping}) != len(mapping):
        return _questions('Output column names collide; choose distinct names before drafting')
    return mapping


def warehouse_alias(loaded, request, model_path, manifest, inventory=()):
    """Literal configured alias, not the adapter/macro-resolved warehouse relation."""
    context = {**request.get('scope', {}), 'directory': str(PurePosixPath(model_path).parent)}
    applicable = []
    for index, rule in enumerate(loaded['document']['naming']):
        if rule['target'] != 'warehouse_alias':
            continue
        scope = rule.get('scope', {})
        if any(k in context and context[k] != v for k, v in scope.items()):
            continue
        if any(k not in context for k in scope):
            return _questions('Clarify warehouse alias rule scope')
        applicable.append((index, rule))
    if not applicable:
        return None
    if len(applicable) != 1:
        return _questions('Applicable warehouse alias rules overlap')
    index, rule = applicable[0]
    provenance = {**loaded['provenance'], 'locator': f'/naming/{index}'}
    try:
        name = resolve_name(NamingRule(rule['id'], rule['template'], loaded['document']['tokens'], provenance, rule.get('bindings', {})), request['values'])
    except NamingError:
        return _questions('Warehouse alias tokens conflict with literal naming constraints or bindings')
    if name['status'] != 'resolved':
        return _questions('Supply the missing warehouse alias naming tokens', naming=name)
    value = name['value']
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', value) is None:
        return _questions('Warehouse alias must be a portable SQL identifier')
    known = {PurePosixPath(p).stem.casefold() for p in inventory if p != model_path}
    for resource in manifest.get('resources', []):
        if resource.get('resource_type') == 'model':
            known.update(v.casefold() for v in (resource.get('alias'), resource.get('name')) if isinstance(v, str))
    if value.casefold() in known:
        return _questions('Known model name or alias collision; choose another alias or review an existing-model change')
    return {'status': 'resolved', 'value': value, 'rule_id': rule['id'], 'provenance': provenance}


def render_projection(request, source, model_name, mapping=None, alias=None):
    mapping = mapping if mapping is not None else [{'source': c, 'output': c} for c in request['columns']]
    expressions, columns = [], []
    for item in mapping:
        source_column, output = item['source'], item['output']
        expression = "{{ adapter.quote('" + source_column + "') }}"
        if output != source_column:
            expression += " as {{ adapter.quote('" + output + "') }}"
        expressions.append(expression)
        column = {'name': output, 'quote': True}
        if source_column in request['grain']:
            column['data_tests'] = ['not_null'] + (['unique'] if len(request['grain']) == 1 else [])
        columns.append(column)
    sql = 'select\n    ' + ',\n    '.join(expressions) + "\nfrom {{ source('" + source['source_name'] + "', '" + source['name'] + "') }}\n"
    if alias is not None:
        sql = "{{ config(alias='" + alias['value'] + "') }}\n\n" + sql
    properties = yaml.safe_dump({'version': 2, 'models': [{'name': model_name, 'columns': columns}]}, sort_keys=False)
    return sql, properties


def prepare_model(project, policy_path, catalog, request, *, snapshot=None, context_id=None):
    """Create no files. Caller-supplied intent/grain are assertions, never approval."""
    allowed = {'intent', 'asset_id', 'source_id', 'model_rule', 'properties_rule', 'values', 'columns', 'grain', 'history', 'scope', 'column_context'}
    if not isinstance(request, dict) or set(request) - allowed or len(json.dumps(request)) > 16384:
        raise DraftError('Invalid or oversized model request')
    required = allowed - {'scope', 'column_context'}
    if any(k not in request or request[k] in ('', [], None) for k in required):
        return _questions('Specify intent, asset/source, both naming rules, token values, projection columns, grain and history')
    for key in ('intent', 'asset_id', 'source_id', 'model_rule', 'properties_rule', 'history'):
        if not isinstance(request[key], str) or not 1 <= len(request[key]) <= 2048:
            raise DraftError('Model request text must be bounded strings')
    for key in ('values', 'scope'):
        values = request.get(key, {})
        if not isinstance(values, dict) or len(values) > 256 or any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
            raise DraftError('Naming values and scope require string mappings')
    for key in ('columns', 'grain'):
        values = request[key]
        if not isinstance(values, list) or not 1 <= len(values) <= 256 or any(not isinstance(v, str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', v) is None for v in values) or len(set(values)) != len(values):
            raise DraftError('Select distinct portable column identifiers')
    if request['history'] != 'source_rows':
        return _questions('Only source-row projection is supported; joins, deduplication and history require a different design')
    loaded = load_document(policy_path)
    if loaded['document']['kind'] != 'policy':
        raise DraftError('Select a declared modelling policy')
    names = _names(loaded, request)
    if isinstance(names, dict):
        return names
    mapping = column_mapping(loaded, request, names[0])
    if isinstance(mapping, dict):
        return mapping
    paths, project_input = _config(project)
    try:
        inventory = _model_inventory(project, paths)
        for name in names:
            _target(project, name, paths)
    except DraftError as error:
        return _questions(str(error))
    model_name = PurePosixPath(names[0]).stem
    if not names[0].endswith('.sql') or PurePosixPath(names[1]).suffix not in ('.yml', '.yaml') or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', model_name):
        return _questions('Choose a SQL model path and YAML properties path with a valid model identifier')
    if any(PurePosixPath(path).stem.casefold() == model_name.casefold() for path in inventory):
        return _questions('A model file with this identifier already exists in the project')
    snapshot = inspect_artifacts(project) if snapshot is None else snapshot
    manifest = snapshot['manifest']
    if manifest.get('status') != 'available' or manifest.get('identity') != 'matched' or not manifest.get('sha256'):
        return _questions('Provide a supported manifest matching the selected project')
    resources = manifest.get('resources', [])
    if any(r.get('resource_type') == 'model' and r.get('package_name') == project.name and r.get('name', '').casefold() == model_name.casefold() for r in resources):
        return _questions('A model with this identifier already exists; choose a new name or a change workflow')
    sources = [r for r in resources if r.get('unique_id') == request['source_id'] and r.get('resource_type') == 'source' and r.get('package_name') == project.name]
    if len(sources) != 1:
        return _questions('Select an existing source from this project manifest')
    source = sources[0]
    if any(not isinstance(source.get(k), str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', source[k]) is None for k in ('source_name', 'name')):
        return _questions('Source names are missing or unsupported; refresh the manifest or select another source')
    facts = catalog.resolve(request['asset_id'], list(FIELDS))
    if facts['status'] in ('denied', 'error', 'conflict') or any(k in facts['missing'] for k in ('relation', 'columns')):
        return _questions('Resolve required catalog facts, errors or conflicts before drafting', catalog=facts)
    relation = facts['selected']['relation']['value']
    if relation != {'catalog': source.get('database'), 'schema': source.get('schema'), 'name': source.get('identifier', source.get('name'))}:
        return _questions('Catalog asset and selected dbt source physical relation do not match', catalog=facts)
    available = {c['name'] for c in facts['selected']['columns']['value']}
    if not set(request['columns']) <= available or not set(request['grain']) <= set(request['columns']):
        return _questions('Projection columns must exist in the catalog; grain columns must be included')
    alias = warehouse_alias(loaded, request, names[0], manifest, inventory)
    if alias is not None and alias['status'] != 'resolved':
        return alias
    sql, properties = render_projection(request, source, model_name, mapping, alias)
    files = [{'path': path, 'content': content, 'operation': 'create', 'diff': ''.join(difflib.unified_diff([], content.splitlines(keepends=True), fromfile='/dev/null', tofile=path))}
             for path, content in zip(names, (sql, properties))]
    inputs = [project_input, {'path': manifest['path'], 'sha256': manifest['sha256']},
              {'path': loaded['provenance']['document'], 'sha256': loaded['provenance']['sha256']}]
    if catalog.config:
        inputs.append({'path': catalog.config['document'], 'sha256': catalog.config['revision']})
    # Negative evidence affects the decision too: pin every consulted provider,
    # not only providers that contributed positive claims.
    consulted = {attempt['provider'] for attempt in facts['attempts']}
    for provider in catalog.describe()['providers']:
        if provider['id'] in consulted:
            if provider['status'] != 'available':
                raise DraftError('Consulted catalog evidence changed; refresh before drafting')
            item = {'path': provider['document'], 'sha256': provider['revision']}
            if item not in inputs:
                inputs.append(item)
    draft = {'schema_version': 1, 'status': 'pending_review', 'project_root': str(project.root), 'project_name': project.name,
             'context_id': context_id, 'model_inventory': {'sha256': _digest(inventory), 'count': len(inventory)}, 'request': deepcopy(request), 'files': files, 'preconditions': inputs,
             'policy': loaded, 'catalog': facts,
             'source': {k: manifest.get(k) for k in ('path', 'sha256', 'generated_at', 'observed_at', 'freshness')},
             'design': {'warehouse_alias': alias, 'grain': request['grain'], 'output_grain': [next(m['output'] for m in mapping if m['source'] == c) for c in request['grain']], 'column_mapping': mapping, 'grain_evidence': 'caller_assertion', 'history': 'source_rows',
                        'normal_form_status': 'unverified', 'standards': loaded['document']['modelling']},
             'validation': {'executed': [], 'proposed': ['Review source mapping, grain, modelling principles and inherited dbt configuration', 'Validate with dbt only through a separately authorized output-safe runner'],
                            'limitations': ['No SQL/database execution or proof of key/normal form', 'Composite grain uniqueness test is not generated', 'No existing properties/model files are modified', 'Effective warehouse alias, schema/database and custom naming macros require operator review; known-name checks do not prove uniqueness', 'Manifest/source freshness is evidence, not live warehouse verification']}}
    draft['draft_id'] = _digest(draft)
    _bounded(draft)
    return draft


def apply_draft(project, draft, approved_digest):
    """Operator explicitly approves the exact bytes; no agent-side approval tool."""
    if not isinstance(draft, dict) or draft.get('status') != 'pending_review' or draft.get('schema_version') != 1:
        raise DraftError('Select a pending model draft')
    _bounded(draft)
    payload = {k: v for k, v in draft.items() if k != 'draft_id'}
    if draft.get('draft_id') != approved_digest or _digest(payload) != approved_digest:
        raise DraftError('Approval digest must match the complete reviewed draft')
    if draft.get('project_root') != str(project.root) or draft.get('project_name') != project.name:
        raise DraftError('Draft belongs to a different project')
    paths, project_input = _config(project)
    inventory = _model_inventory(project, paths)
    if draft.get('model_inventory') != {'sha256': _digest(inventory), 'count': len(inventory)}:
        raise DraftError('Model inventory changed; regenerate and review again')
    inputs = draft.get('preconditions')
    if not isinstance(inputs, list) or not 3 <= len(inputs) <= 40 or project_input not in inputs:
        raise DraftError('Draft is missing project preconditions')
    try:
        for item in inputs:
            if set(item) != {'path', 'sha256'} or _file_hash(item['path']) != item['sha256']:
                raise DraftError('Draft inputs changed; regenerate and review again')
    except (OSError, CatalogError, TypeError, KeyError):
        raise DraftError('Cannot verify draft inputs') from None
    files = draft.get('files')
    if not isinstance(files, list) or len(files) != 2 or any(not isinstance(f, dict) or f.get('operation') != 'create' or not isinstance(f.get('path'), str) or not isinstance(f.get('content'), str) or len(f['content'].encode('utf-8')) > 65536 for f in files):
        raise DraftError('Expected two bounded create-only draft files')
    if not files[0]['path'].endswith('.sql') or PurePosixPath(files[1]['path']).suffix not in ('.yml', '.yaml') or files[0]['path'].casefold() == files[1]['path'].casefold():
        raise DraftError('Expected distinct SQL and YAML file paths')
    targets = [_target(project, f['path'], paths) for f in files]
    created = []
    try:
        for file, target in zip(files, targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            _target(project, file['path'], paths)
            with target.open('x', encoding='utf-8', newline='') as stream:
                created.append(target)
                stream.write(file['content'])
    except (OSError, DraftError):
        for target in reversed(created):
            try:
                target.unlink()
            except OSError:
                pass
        raise DraftError('Could not create draft files; inspect workspace after rollback attempt') from None
    return {'status': 'created', 'draft_id': approved_digest, 'paths': [f['path'] for f in files], 'validation_executed': []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'apply'])
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--draft')
    parser.add_argument('--request')
    parser.add_argument('--policy')
    parser.add_argument('--catalog-config')
    parser.add_argument('--target-path')
    parser.add_argument('--approve', help='Exact digest of the reviewed draft; explicit operator approval')
    args = parser.parse_args(argv)
    try:
        project = discover_project(args.project_dir, target_path=args.target_path)
        if args.command == 'prepare':
            if not all((args.request, args.policy, args.catalog_config)) or args.approve is not None:
                raise DraftError('Prepare requires request, policy and catalog configuration')
            request, _ = _document(project.root / args.request)
            result = prepare_model(project, project.root / args.policy, load_catalog(project.root / args.catalog_config), request)
        else:
            if not args.draft or not args.approve:
                raise DraftError('Apply requires a draft and explicit reviewed digest')
            draft, _ = _document(args.draft)
            result = apply_draft(project, draft, args.approve)
        print(json.dumps(result, indent=2))
        return 2 if result['status'] == 'needs_clarification' else 0
    except (ValueError, OSError, RuntimeError, TypeError, KeyError):
        print('Cannot process draft: verify project, request, policy, catalog, reviewed digest and file paths', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
