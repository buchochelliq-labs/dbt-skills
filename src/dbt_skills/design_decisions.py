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
    'current_row_rule', 'history_rule', 'confirm_relationship',
})


def answer_identity(answer):
    return (answer.get('question_code', answer.get('code')), answer.get('target_asset'),
            tuple(answer.get('columns', [])), tuple(answer.get('target_columns', [])))


def validate_answers(answers):
    try:
        if not isinstance(answers, list) or len(answers) > 16:
            raise ValueError
        seen = set()
        for answer in answers:
            if not isinstance(answer, dict) or set(answer) - {'target_asset', 'columns', 'target_columns'} != {'question_code', 'answer', 'rationale'}:
                raise ValueError
            code = answer['question_code']
            if not isinstance(code, str) or code not in ANSWER_CODES:
                raise ValueError
            if code == 'confirm_relationship':
                if not isinstance(answer.get('target_asset'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}', answer['target_asset']):
                    raise ValueError
                for key in ('columns', 'target_columns'):
                    columns = answer.get(key)
                    if not isinstance(columns, list) or not 1 <= len(columns) <= 32 or any(not isinstance(c, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', c) for c in columns) or len(set(columns)) != len(columns):
                        raise ValueError
                if len(answer['columns']) != len(answer['target_columns']):
                    raise ValueError
            elif {'target_asset', 'columns', 'target_columns'} & set(answer):
                raise ValueError
            identity = answer_identity(answer)
            if identity in seen:
                raise ValueError
            seen.add(identity)
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
            if isinstance(record, dict) and record.get('record_type') == 'metadata_mapping':
                validate_mapping(record)
                if record['id'] in ids:
                    raise ValueError
                ids.add(record['id'])
                continue
            if not isinstance(record, dict) or set(record) - {'answers', 'related_contexts'} != {'id', 'intent', 'asset_id', 'scope', 'grain', 'history', 'rationale', 'recorded_by', 'recorded_at', 'evidence'}:
                raise ValueError
            if 'answers' in record:
                validate_answers(record['answers'])
            related = record.get('related_contexts', [])
            if not isinstance(related, list) or len(related) > 7:
                raise ValueError
            related_ids = {record['asset_id']}
            for context in related:
                if not isinstance(context, dict) or set(context) - {'grain', 'history'} != {'asset_id', 'scope', 'evidence'}:
                    raise ValueError
                if not isinstance(context['asset_id'], str) or context['asset_id'] in related_ids:
                    raise ValueError
                related_ids.add(context['asset_id'])
                # Reuse the same scope/assertion/fingerprint validation without
                # recursing into related contexts or duplicating its contract.
                candidate = {k: v for k, v in record.items() if k not in ('answers', 'related_contexts')}
                candidate.update(context)
                validate_decisions({'schema_version': 1, 'kind': 'design_decisions', 'records': [candidate]})
            if any(a.get('target_asset', record['asset_id']) not in related_ids for a in record.get('answers', [])):
                raise ValueError

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
            if not isinstance(evidence, dict) or set(evidence) - {'business_context_sha256'} != {'policy_sha256', 'manifest_sha256', 'catalog_config_sha256', 'catalog_facts_sha256'}:
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


def decision_context(intent, asset, policy, manifest, facts, config, business=None):
    # Only observation-clock fields are excluded. Source revisions, scopes,
    # values and derivation remain binding, including negative lookup results.
    normalized = deepcopy(facts)
    for claim in list(normalized['selected'].values()) + [c for claims in normalized['claims'].values() for c in claims]:
        for key in ('retrieved_at', 'verified_at'):
            claim['provenance'].pop(key, None)
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return {'intent': intent, 'asset_id': asset['asset_id'], 'scope': deepcopy(asset.get('scope', {})),
            'evidence': {'policy_sha256': policy['provenance']['sha256'], 'manifest_sha256': manifest['sha256'],
                         'catalog_config_sha256': config['revision'] if config else None, 'catalog_facts_sha256': digest,
                         **({'business_context_sha256': business['provenance']['sha256']} if business else {})}}


def select_decision(decisions, context, asset, contexts=None, assets=None):
    if decisions is None:
        return {'status': 'none'}
    matches = [(i, r) for i, r in enumerate(decisions['document']['records'])
               if r.get('record_type') != 'metadata_mapping' and all(r[k] == context[k] for k in ('intent', 'asset_id', 'scope'))]
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
    if status == 'matched':
        for related in record.get('related_contexts', []):
            current = (contexts or {}).get(related['asset_id'])
            if current is None:
                status = 'incomplete'
                break
            if any(current[k] != related[k] for k in ('scope', 'evidence')):
                status = 'stale'
                break
            supplied = (assets or {}).get(related['asset_id'], {})
            if any(k in supplied and k in related and supplied[k] != related[k] for k in ('grain', 'history')):
                status = 'conflict'
                break
    return {'status': status, 'record': deepcopy(record),
            'provenance': {**decisions['provenance'], 'locator': f'/records/{index}'}}


def validate_mapping(record):
    """Typed scope-bound mapping assertions share the reviewed decision store."""
    from .planning_contracts import MappingRequest, validate_request
    required = {'record_type','status','evidence'}
    if not required <= set(record) or record['record_type'] != 'metadata_mapping' or record['status'] not in ('proposed','reviewed'):
        raise ValueError('Invalid mapping record')
    request = {k:v for k,v in record.items() if k not in required}
    if 'replace_record_id' in request:
        raise ValueError('Invalid mapping record')
    validate_request(MappingRequest, request)
    if not _timestamp(record['recorded_at']) or not record['scope'] or len(set(record['record_ids'])) != len(record['record_ids']) or len(set(record['columns'])) != len(record['columns']):
        raise ValueError('Invalid mapping record')
    evidence = record['evidence']
    if not isinstance(evidence, dict) or set(evidence) != {'business_context_sha256','catalog_facts_sha256'} or any(not isinstance(v,str) or re.fullmatch('[a-f0-9]{64}',v) is None for v in evidence.values()):
        raise ValueError('Invalid mapping record')
