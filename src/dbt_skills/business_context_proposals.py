"""Read-only, explicit record proposals for operator-selected business context."""
from copy import deepcopy

from .business_context import BusinessContextError, load_business_context, validate_business_context
from .context_limits import check_bounds
from .local_context_updates import prepare_update


def prepare_business_update(loaded, request):
    try:
        check_bounds(request)
        if not isinstance(request, dict) or set(request) - {'section', 'record', 'replace_record_id'} or not {'section', 'record'} <= set(request):
            raise ValueError
        section, record = request['section'], request['record']
        if section not in ('concepts', 'relationships') or not isinstance(record, dict):
            raise ValueError
        validate_business_context(loaded['document'])
        current = load_business_context(loaded['provenance']['document'])
        if current != loaded:
            raise ValueError
        document = deepcopy(loaded['document'])
        records = document[section]
        replacement = request.get('replace_record_id')
        if 'replace_record_id' in request:
            if replacement != record.get('id'):
                raise ValueError
            matches = [i for i, item in enumerate(records) if item['id'] == replacement]
            if len(matches) != 1:
                raise ValueError
            index = matches[0]
            patch = [{'op': 'test', 'path': f'/{section}/{index}', 'value': deepcopy(records[index])},
                     {'op': 'replace', 'path': f'/{section}/{index}', 'value': deepcopy(record)}]
            records[index] = deepcopy(record)
        else:
            records.append(deepcopy(record))
            patch = [{'op': 'add', 'path': f'/{section}/-', 'value': deepcopy(record)}]
        validate_business_context(document)
        if document == loaded['document']:
            return {'status': 'unchanged', 'business_context_patch': [], 'limitations': ['No changes or save payload; retain existing attribution and timestamps']}
        result = {'status': 'pending_review', 'proposed_document': document, 'business_context_patch': patch,
                  'local_update': prepare_update(loaded, document),
                  'review_requirements': ['Review the full scoped record, diff and exact proposal digest before explicit operator acceptance',
                                          'An answer in conversation is not permission to save; decline or defer leaves it conversational',
                                          'Refresh MCP context and read the record back after saving'],
                  'limitations': ['No files are written or approved by this tool',
                                  'Supplied review status and attribution do not authenticate approval or prove business meaning']}
        check_bounds(result)
        return result
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise BusinessContextError('Use a complete scoped record and explicit matching replacement ID against unchanged selected business context') from None
