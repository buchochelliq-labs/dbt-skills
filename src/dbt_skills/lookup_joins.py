"""One explicit source lookup; catalog keys remain declarations, not join proof."""
from copy import deepcopy
import re


def _name(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', value) is not None


def lookup_request(request):
    if 'lookup' not in request:
        return None
    try:
        rule = request['lookup']
        required = {'asset_id', 'source_id', 'type', 'on', 'columns', 'cardinality', 'nulls', 'rationale'}
        if not isinstance(rule, dict) or set(rule) - required - {'column_context'} or not required <= set(rule):
            raise ValueError
        if request['history'] != 'source_rows' or rule['asset_id'] == request['asset_id'] or rule['source_id'] == request['source_id']:
            raise ValueError
        for key in ('asset_id', 'source_id'):
            if not isinstance(rule[key], str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}', rule[key]) is None:
                raise ValueError
        if rule['type'] not in ('left', 'inner') or rule['cardinality'] != 'many_to_one' or rule['nulls'] != 'never_match':
            raise ValueError
        if not isinstance(rule['rationale'], str) or not rule['rationale'].strip() or len(rule['rationale']) > 4096:
            raise ValueError
        columns, pairs = rule['columns'], rule['on']
        if not isinstance(columns, list) or not 1 <= len(columns) <= 64 or any(not _name(c) for c in columns) or len(set(columns)) != len(columns):
            raise ValueError
        if not isinstance(pairs, list) or not 1 <= len(pairs) <= 16:
            raise ValueError
        for pair in pairs:
            if not isinstance(pair, dict) or set(pair) != {'left', 'right'} or any(not _name(v) for v in pair.values()):
                raise ValueError
        for side in ('left', 'right'):
            names = [p[side].casefold() for p in pairs]
            if len(names) != len(set(names)):
                raise ValueError
    except (KeyError, ValueError, TypeError):
        return {'status': 'needs_clarification', 'questions': ['Select one distinct source lookup, equality keys, left/inner type, columns, many-to-one and null-key assertions with rationale']}
    return None


def lookup_column_request(request):
    return {**request, 'columns': request['lookup']['columns'], 'column_context': request['lookup'].get('column_context', {})}


def lookup_design(project, manifest, request, base, facts, mapping, added):
    invalid = lookup_request(request)
    if invalid:
        return invalid
    rule = request['lookup']
    def question(message):
        return {'status': 'needs_clarification', 'questions': [message]}
    if facts['asset_id'] != rule['asset_id'] or facts['status'] in ('denied', 'error', 'conflict'):
        return question('Resolve lookup access, errors or conflicting metadata before drafting')
    selected = facts['selected']
    if any(k not in selected for k in ('relation', 'columns', 'primary_key')) or not selected['primary_key']['value']:
        return question('Supply lookup relation, columns and a declared lookup key')
    if selected['relation']['value'] == base['selected']['relation']['value']:
        return question('Select a different physical lookup relation; self-joins require a separate design')
    sources = [r for r in manifest['resources'] if r.get('unique_id') == rule['source_id'] and r.get('resource_type') == 'source' and r.get('package_name') == project.name]
    if len(sources) != 1 or any(not _name(sources[0].get(k)) for k in ('source_name', 'name')):
        return question('Select an existing current-project lookup source')
    source = sources[0]
    if selected['relation']['value'] != {'catalog': source.get('database'), 'schema': source.get('schema'), 'name': source.get('identifier', source.get('name'))}:
        return question('Lookup catalog relation and selected dbt source do not match')
    left = {c['name']: c for c in base['selected']['columns']['value']}
    right = {c['name']: c for c in selected['columns']['value']}
    if not set(rule['columns']) <= set(right) or any(p['left'] not in left or p['right'] not in right for p in rule['on']):
        return question('Join and lookup output columns must exist in catalog metadata')
    if any(left[p['left']]['type'] == 'unknown' or left[p['left']]['type'] != right[p['right']]['type'] for p in rule['on']):
        return question('Reconcile join-key types before drafting; implicit casts are not inferred')
    if set(selected['primary_key']['value']['columns']) != {p['right'] for p in rule['on']}:
        return question('Lookup equality keys must match the declared lookup primary key')
    outputs = [m['output'].casefold() for m in mapping + added]
    if len(outputs) != len(set(outputs)):
        return question('Resolve output column naming collisions between base and lookup projections')
    pairs = {p['left']: p['right'] for p in rule['on']}
    relationships = base['selected'].get('foreign_keys')
    supporting = []
    for fk in relationships['value'] if relationships else []:
        if set(fk['columns']) != set(pairs):
            continue
        if fk['target_asset'] != rule['asset_id'] or dict(zip(fk['columns'], fk['target_columns'])) != pairs:
            return question('Reconcile the join with a contradictory declared relationship for these base keys')
        supporting.append(deepcopy(fk))
    return {'rule': deepcopy(rule), 'source': {k: source[k] for k in ('unique_id', 'source_name', 'name')},
            'column_mapping': deepcopy(added), 'verified': False, 'basis': 'caller_assertion',
            'lookup_key': deepcopy(selected['primary_key']), 'relationships': supporting,
            'relationship_provenance': deepcopy(relationships['provenance']) if supporting else None,
            'limitations': ['Declared lookup uniqueness is not verified; duplicates can multiply base rows',
                            'Output grain is the caller-asserted base grain, not a proven join property',
                            'Equality never matches null keys; inner joins drop unmatched rows',
                            'Missing FK declarations require human review of relationship meaning']}


def render_lookup(request, source, mapping, lookup):
    def quote(name):
        return "{{ adapter.quote('" + name + "') }}"
    def relation(item):
        return "{{ source('" + item['source_name'] + "', '" + item['name'] + "') }}"
    expressions = [alias + '.' + quote(m['source']) + ' as ' + quote(m['output'])
                   for alias, entries in [('base_rows', mapping), ('lookup_rows', lookup['column_mapping'])] for m in entries]
    predicate = ' and '.join('base_rows.' + quote(p['left']) + ' = lookup_rows.' + quote(p['right']) for p in request['lookup']['on'])
    return ('select\n    ' + ',\n    '.join(expressions) + '\nfrom ' + relation(source) + ' as base_rows\n' +
            request['lookup']['type'] + ' join ' + relation(lookup['source']) + ' as lookup_rows\n    on ' + predicate + '\n')
