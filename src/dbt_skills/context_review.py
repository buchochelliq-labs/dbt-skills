"""Bounded read-only local record search, proposal review and historical evidence."""
from copy import deepcopy

from .context_limits import check_bounds
from .local_context_updates import _digest, _review_diff, _validate, prepare_update


def bounded_request(value, keys):
    check_bounds(value)
    if not isinstance(value, dict) or set(value) - set(keys):
        raise ValueError('Invalid bounded review request')


def page(request):
    offset, limit = request.get('offset', 0), request.get('limit', 20)
    if type(offset) is not int or not 0 <= offset <= 200000 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('Use offset 0..200000 and limit 1..20')
    return offset, limit


def search_records(state, request):
    bounded_request(request, {'kind', 'record_id', 'text', 'scope', 'status', 'offset', 'limit'})
    kind = request.get('kind')
    if kind not in ('concepts', 'relationships', 'decisions', 'mappings'):
        raise ValueError('Select a supported record kind')
    offset, limit = page(request)
    for key in ('record_id', 'text'):
        if key in request and (not isinstance(request[key], str) or not 1 <= len(request[key]) <= 256):
            raise ValueError('Use bounded record filters')
    scope = request.get('scope', {})
    if not isinstance(scope, dict) or len(scope) > 32 or any(not isinstance(k, str) or not 1 <= len(k) <= 256 or not isinstance(v, str) or not 1 <= len(v) <= 256 for k,v in scope.items()):
        raise ValueError('Use bounded scope filters')
    if request.get('status') not in (None, 'proposed', 'reviewed'):
        raise ValueError('Use a supported status filter')
    loaded = state.get('business' if kind in ('concepts','relationships') else 'design_decisions')
    records = []
    if loaded:
        section = kind if kind in ('concepts','relationships') else 'records'
        for index, record in enumerate(loaded['document'][section]):
            if section == 'records' and (record.get('record_type') == 'metadata_mapping') != (kind == 'mappings'):
                continue
            if request.get('record_id') is not None and record['id'] != request['record_id']:
                continue
            if any(record['scope'].get(k) != v for k,v in scope.items()):
                continue
            if request.get('status') is not None and record.get('status', 'proposed') != request['status']:
                continue
            text = request.get('text', '').casefold()
            if text and not any(text in record.get(k, '').casefold() for k in ('id','name','definition','intent','rationale','meaning')):
                continue
            records.append({'record':deepcopy(record), 'verified':False,
                'provenance':{**loaded['provenance'], 'locator':f'/{section}/{index}'},
                'freshness':'pinned_document_revision; upstream authorization and semantic verification unknown'})
    return {'status':'available' if loaded else 'unconfigured', 'records':records[offset:offset+limit],
            'total':len(records), 'next_offset':offset+limit if offset+limit<len(records) else None}


def review_update(state, proposal, *, rebase=False, baseline=None):
    """Verify digest/diff and selected target; optionally three-way merge records."""
    try:
        bounded_request(proposal, {'schema_version','base','proposed_document','review_diff','proposal_sha256'})
        if set(proposal) != {'schema_version','base','proposed_document','review_diff','proposal_sha256'} or type(proposal['schema_version']) is not int or proposal['schema_version'] != 1:
            raise ValueError
        if _digest({k:v for k,v in proposal.items() if k!='proposal_sha256'}) != proposal['proposal_sha256']:
            return {'status':'invalid','reason':'digest_mismatch'}
        proposed = proposal['proposed_document']
        _validate(proposed)
        loaded = state.get('business' if proposed['kind']=='business_context' else 'design_decisions')
        if loaded is None or not isinstance(proposal['base'], dict) or proposal['base'].get('document') != loaded['provenance']['document']:
            return {'status':'invalid','reason':'target_conflict'}
        if baseline is not None:
            _validate(baseline)
            if proposal['review_diff'] != _review_diff(baseline, proposed):
                return {'status':'invalid','reason':'invalid_diff'}
        if proposal['base'] == loaded['provenance']:
            if proposed == loaded['document']:
                return {'status':'unchanged','reason':'no_change'}
            if prepare_update(loaded, proposed) != proposal:
                return {'status':'invalid','reason':'invalid_diff'}
            return {'status':'ready','reason':'review_required','local_update':deepcopy(proposal), 'verified':False}
        result = {'status':'stale','reason':'stale_base'}
        if not rebase or baseline is None:
            return result
        if baseline['kind'] != proposed['kind']:
            raise ValueError
        merged = deepcopy(loaded['document'])
        sections = ('concepts','relationships') if proposed['kind']=='business_context' else ('records',)
        for section in sections:
            old = {r['id']:r for r in baseline[section]}
            new = {r['id']:r for r in proposed[section]}
            current = {r['id']:r for r in merged[section]}
            for identifier in old.keys() | new.keys():
                if old.get(identifier) == new.get(identifier):
                    continue
                if current.get(identifier) != old.get(identifier) and current.get(identifier) != new.get(identifier):
                    return {'status':'stale','reason':'same_record_conflict'}
                if identifier in new:
                    current[identifier] = deepcopy(new[identifier])
                else:
                    current.pop(identifier, None)
            merged[section] = list(current.values())
        _validate(merged)
        if merged == loaded['document']:
            return {'status':'unchanged','reason':'no_change'}
        return {**result, 'reason':'rebase_available', 'rebased_update':prepare_update(loaded, merged), 'fresh_acceptance_required':True}
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        return {'status':'invalid','reason':'invalid_proposal'}


def field_changes(before, after, path='', changes=None):
    """Bound both traversal and response through already bounded snapshot inputs."""
    changes = [] if changes is None else changes
    if before == after:
        return changes
    if isinstance(before, list) and isinstance(after, list) and all(isinstance(v,dict) for v in before+after):
        key = next((k for k in ('id','name','unique_id') if all(isinstance(v.get(k),str) for v in before+after)), None)
        if key is not None:
            return field_changes({v[key]:v for v in before},{v[key]:v for v in after},path,changes)
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            escaped = key.replace('~','~0').replace('/','~1')
            field_changes(before.get(key), after.get(key), path+'/'+escaped, changes)
    else:
        changes.append({'path':path, 'change':'added' if before is None else 'removed' if after is None else 'changed',
                        'before':deepcopy(before), 'after':deepcopy(after)})
    return changes
