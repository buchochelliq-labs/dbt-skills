"""Bounded current-row selection rules; ordering uniqueness is a human assertion."""
from copy import deepcopy
import re


def current_row_design(request, available=None):
    history = request.get('history')
    if history == 'source_rows' and 'current_row' not in request:
        return None
    message = 'Current models require explicit ordering, null placement, unique-tie assertion, retain-latest deletion policy and rationale'
    try:
        rule = request['current_row']
        if history != 'current' or not isinstance(rule, dict) or set(rule) != {'order_by', 'ties', 'deletions', 'rationale'}:
            raise ValueError
        if rule['ties'] != 'assert_unique' or rule['deletions'] != 'retain_latest':
            raise ValueError
        if not isinstance(rule['rationale'], str) or not rule['rationale'].strip() or len(rule['rationale']) > 4096:
            raise ValueError
        order = rule['order_by']
        if not isinstance(order, list) or not 1 <= len(order) <= 16:
            raise ValueError
        names = []
        for item in order:
            if not isinstance(item, dict) or set(item) != {'column', 'direction', 'nulls'}:
                raise ValueError
            name = item['column']
            if not isinstance(name, str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', name) is None:
                raise ValueError
            if item['direction'] not in ('asc', 'desc') or item['nulls'] not in ('first', 'last'):
                raise ValueError
            if available is not None and name not in available:
                raise ValueError
            names.append(name.casefold())
        if len(names) != len(set(names)):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return {'status': 'needs_clarification', 'questions': [message]}
    return {'rule': deepcopy(rule), 'basis': 'caller_assertion', 'verified': False,
            'limitations': ['Ordering must uniquely identify a row within each grain; ties are not checked',
                            'The latest row is retained even if it is a deletion marker; no older row is resurrected',
                            'Null business keys group together; generated not-null tests require separate execution']}


def render_current(request, source, mapping):
    def quote(name):
        return "{{ adapter.quote('" + name + "') }}"
    used = {m[k].casefold() for m in mapping for k in ('source', 'output')}
    rank = '_dbt_skills_row_number'
    while rank.casefold() in used:
        rank = '_' + rank
    projection = [quote(m['source']) + (' as ' + quote(m['output']) if m['source'] != m['output'] else '') for m in mapping]
    selected = [quote(m['source']) for m in mapping]
    partition = ', '.join(quote(c) for c in request['grain'])
    ordering = ', '.join(quote(o['column']) + ' ' + o['direction'] + ' nulls ' + o['nulls'] for o in request['current_row']['order_by'])
    return ('with ranked_source as (\n    select\n        ' + ',\n        '.join(selected) +
            ',\n        row_number() over (partition by ' + partition + ' order by ' + ordering + ') as ' + quote(rank) +
            "\n    from {{ source('" + source['source_name'] + "', '" + source['name'] + "') }}\n)\n" +
            'select\n    ' + ',\n    '.join(projection) + '\nfrom ranked_source\nwhere ' + quote(rank) + ' = 1\n')
