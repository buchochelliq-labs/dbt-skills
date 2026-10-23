"""Full-source event intervals, not a stateful snapshot or change-capture process."""
from copy import deepcopy
import re


def history_request(request, available=None):
    if request.get('history') != 'historical' and 'history_rule' not in request:
        return None
    try:
        rule = request['history_rule']
        required = {'effective_at','events','ordering','deletions','materialization','rationale'}
        if request['history'] != 'historical' or 'current_row' in request or 'lookup' in request:
            raise ValueError
        if not isinstance(rule, dict) or set(rule) - required - {'column_context'} or not required <= set(rule):
            raise ValueError
        column = rule['effective_at']
        if not isinstance(column, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', column) or column.casefold() in {c.casefold() for c in request['grain']}:
            raise ValueError
        if rule['events'] != 'assert_complete' or rule['ordering'] != 'assert_unique_non_null' or rule['deletions'] != 'retain_events' or rule['materialization'] not in ('table','view'):
            raise ValueError
        if not isinstance(rule['rationale'], str) or not rule['rationale'].strip() or len(rule['rationale']) > 4096:
            raise ValueError
        if available is not None and available.get(column, {}).get('type') not in ('date','timestamp'):
            raise ValueError
    except (TypeError, KeyError, ValueError):
        return {'status':'needs_clarification','questions':['History requires complete retained events, unique non-null effective time per business key, explicit table/view materialization, retained deletion events and rationale']}
    return None


def history_column_request(request):
    return {**request, 'columns':['valid_from','valid_to'], 'column_context':request['history_rule'].get('column_context', {})}


def history_design(request, mapping, generated, effective_claim):
    names = [m['output'].casefold() for m in mapping + generated]
    if len(names) != len(set(names)):
        return {'status':'needs_clarification','questions':['Resolve generated history/output column naming collisions']}
    return {'rule':deepcopy(request['history_rule']), 'column_mapping':deepcopy(generated),
            'effective_column':deepcopy(effective_claim), 'basis':'caller_assertion', 'verified':False,
            'limitations':['Complete retained events and unique non-null effective time per key are not verified',
                           'Intervals are half-open; the latest known event has no end, including deletion events',
                           'All events remain, including unchanged values; no snapshot capture or hard-delete inference',
                           'Late events recompute intervals from the full source; retention loss removes history',
                           'Null business keys group together; proposed tests require separate execution']}


def render_history(request, source, mapping, history):
    def quote(name):
        return "{{ adapter.quote('" + name + "') }}"
    generated = {m['source']:m['output'] for m in history['column_mapping']}
    expressions = [quote(m['source']) + ' as ' + quote(m['output']) for m in mapping]
    effective = quote(request['history_rule']['effective_at'])
    partition = ', '.join(quote(c) for c in request['grain'])
    expressions += [effective + ' as ' + quote(generated['valid_from']),
                    'lead(' + effective + ') over (partition by ' + partition + ' order by ' + effective + ' asc) as ' + quote(generated['valid_to'])]
    return ("{{ config(materialized='" + request['history_rule']['materialization'] + "') }}\n\nselect\n    " +
            ',\n    '.join(expressions) + "\nfrom {{ source('" + source['source_name'] + "', '" + source['name'] + "') }}\n")
