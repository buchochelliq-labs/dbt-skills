"""Human-owned design assertions, bound to the evidence used to review them."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .catalog import CatalogError, _document, _timestamp


class DesignDecisionError(ValueError):
    """Bounded static diagnostic; never echoes document contents."""


ANSWER_CODES = frozenset({
    'functional_dependencies', 'multivalued_dependencies', 'join_dependencies',
    'review_principles', 'relationships_unknown', 'grain_key_difference',
    'current_row_rule', 'history_rule',
})


def validate_answers(answers):
    try:
        if not isinstance(answers, list) or len(answers) > 16:
            raise ValueError
        seen = set()
        for answer in answers:
            if not isinstance(answer, dict) or set(answer) != {'question_code', 'answer', 'rationale'}:
                raise ValueError
            code = answer['question_code']
            if not isinstance(code, str) or code not in ANSWER_CODES or code in seen:
                raise ValueError
            seen.add(code)
            for key, limit in [('answer', 2048), ('rationale', 4096)]:
                if not isinstance(answer[key], str) or not answer[key].strip() or len(answer[key]) > limit:
                    raise ValueError
    except (ValueError, TypeError, KeyError):
        raise DesignDecisionError('Use bounded unique semantic answers with supported question codes and rationale') from None


def validate_decisions(document):
    try:
        if not isinstance(document, dict) or set(document) != {'schema_version', 'kind', 'records'}:
            raise ValueError
        if type(document['schema_version']) is not int or document['schema_version'] != 1 or document['kind'] != 'design_decisions':
            raise ValueError
        records = document['records']
        if not isinstance(records, list) or len(records) > 128:
            raise ValueError
        ids = set()
        for record in records:
            if not isinstance(record, dict) or set(record) - {'answers'} != {'id', 'intent', 'asset_id', 'scope', 'grain', 'history', 'rationale', 'recorded_by', 'recorded_at', 'evidence'}:
                raise ValueError
            if 'answers' in record:
                validate_answers(record['answers'])
            for key, limit in [('id', 128), ('intent', 2048), ('rationale', 4096), ('recorded_by', 256)]:
                if not isinstance(record[key], str) or not record[key].strip() or len(record[key]) > limit:
                    raise ValueError
            if record['id'] in ids:
                raise ValueError
            ids.add(record['id'])
            if not isinstance(record['asset_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}', record['asset_id']):
                raise ValueError
            scope = record['scope']
            if not isinstance(scope, dict) or len(scope) > 32 or any(not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', k) or not isinstance(v, str) or not 1 <= len(v) <= 256 for k, v in scope.items()):
                raise ValueError
            grain = record['grain']
            if not isinstance(grain, list) or not 1 <= len(grain) <= 32 or any(not isinstance(c, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', c) for c in grain) or len(set(grain)) != len(grain):
                raise ValueError
            if record['history'] not in ('source_rows', 'current', 'historical') or not _timestamp(record['recorded_at']) or len(record['recorded_at']) > 64:
                raise ValueError
            evidence = record['evidence']
            if not isinstance(evidence, dict) or set(evidence) != {'policy_sha256', 'manifest_sha256', 'catalog_config_sha256', 'catalog_facts_sha256'}:
                raise ValueError
            for key, value in evidence.items():
                if key == 'catalog_config_sha256' and value is None:
                    continue
                if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
                    raise ValueError
        if len(json.dumps(document, allow_nan=False).encode()) > 1024 * 1024:
            raise ValueError
    except (ValueError, TypeError, KeyError, RecursionError):
        raise DesignDecisionError('Use a bounded design-decisions document with explicit choices, rationale, attribution and evidence fingerprints') from None


def load_design_decisions(path):
    try:
        path = Path(path).resolve()
        document, revision = _document(path)
        validate_decisions(document)
        return {'document': document, 'provenance': {'document': str(path), 'sha256': revision}}
    except (CatalogError, OSError, RuntimeError):
        raise DesignDecisionError('Cannot read a valid design-decisions document') from None


def decision_context(intent, asset, policy, manifest, facts, config):
    # Only observation-clock fields are excluded. Source revisions, scopes,
    # values and derivation remain binding, including negative lookup results.
    normalized = deepcopy(facts)
    for claim in list(normalized['selected'].values()) + [c for claims in normalized['claims'].values() for c in claims]:
        for key in ('retrieved_at', 'verified_at'):
            claim['provenance'].pop(key, None)
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return {'intent': intent, 'asset_id': asset['asset_id'], 'scope': deepcopy(asset.get('scope', {})),
            'evidence': {'policy_sha256': policy['provenance']['sha256'], 'manifest_sha256': manifest['sha256'],
                         'catalog_config_sha256': config['revision'] if config else None, 'catalog_facts_sha256': digest}}


def select_decision(decisions, context, asset):
    if decisions is None:
        return {'status': 'none'}
    matches = [(i, r) for i, r in enumerate(decisions['document']['records'])
               if all(r[k] == context[k] for k in ('intent', 'asset_id', 'scope'))]
    if not matches:
        return {'status': 'none'}
    if len(matches) > 1:
        return {'status': 'ambiguous'}
    index, record = matches[0]
    status = 'matched'
    if record['evidence'] != context['evidence']:
        status = 'stale'
    elif any(k in asset and asset[k] != record[k] for k in ('grain', 'history')):
        status = 'conflict'
    return {'status': status, 'record': deepcopy(record),
            'provenance': {**decisions['provenance'], 'locator': f'/records/{index}'}}
