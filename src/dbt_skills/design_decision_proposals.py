"""Prepare review-only saved design choices; never write or approve a record."""
from copy import deepcopy

from .local_context_updates import prepare_update
from .design_decisions import DesignDecisionError, validate_decisions, validate_answers, answer_identity
from .context_limits import ContextLimitError, check_bounds
from .model_planning import PlanningError, _request, plan_model


def prepare_design_decision(project, policy, catalog, request, *, decisions=None, snapshot=None, business=None):
    """Derive evidence from the selected context, never from caller-supplied hashes."""
    try:
        check_bounds(request)
        if not isinstance(request, dict) or set(request) - {'plan', 'record', 'replace_record_id'}:
            raise ValueError
        plan_request = request['plan']
        _request(plan_request)
        if not {'grain', 'history'} <= set(plan_request['assets'][0]):
            raise ValueError
        metadata = request['record']
        if not isinstance(metadata, dict) or set(metadata) - {'answers'} != {'id', 'rationale', 'recorded_by', 'recorded_at'}:
            raise ValueError
        if 'answers' in metadata:
            validate_answers(metadata['answers'])
        replacement = request.get('replace_record_id')
        if 'replace_record_id' in request and (not isinstance(replacement, str) or not replacement.strip() or len(replacement) > 128):
            raise ValueError
    except (ValueError, TypeError, KeyError, ContextLimitError, PlanningError):
        raise DesignDecisionError('Supply an explicit anchor grain/history choice, selected related assets, record attribution and optional replacement ID') from None
    if decisions is not None:
        validate_decisions(decisions['document'])
    # Do not let existing records supply choices: a new proposal must be explicit.
    planning = plan_model(project, policy, catalog, plan_request, snapshot=snapshot, business=business)
    result = {'status': 'needs_clarification', 'planning': planning, 'questions': [],
              'proposed_document': None, 'decisions_patch': [], 'local_update': None,
              'decisions_base': deepcopy(decisions['provenance']) if decisions else None,
              'review_requirements': ['Review the complete record and unresolved planning questions before saving',
                                      'Verify the decisions base digest and source evidence have not changed before saving',
                                      'Attribution is caller-supplied, not authenticated approval; saving does not prove grain or normal form'],
              'limitations': ['No files or standards are changed; this proposal is not an approved decision',
                              'Explicit choices and semantic answers are assertions; review questions remain open']}
    if planning['status'] == 'blocked':
        result['status'] = 'blocked'
        return result
    blocking = {'required_metadata', 'catalog_conflict', 'project_snapshot', 'grain_columns_missing'}
    if not planning['entities'] or any(q['code'] in blocking for q in planning['questions']):
        return result
    anchor_id = plan_request['assets'][0]['asset_id']
    active_codes = {answer_identity(q) for q in planning['questions'] if q.get('asset_id') == anchor_id}
    if any(answer_identity(a) not in active_codes for a in metadata.get('answers', [])):
        result['questions'].append({'code': 'inactive_design_answer', 'message': 'Record answers only for questions raised by this plan.'})
        return result
    context = planning['entities'][0]['decision_context']
    asset = plan_request['assets'][0]
    record = {**deepcopy(context), **deepcopy(metadata), 'grain': deepcopy(asset['grain']), 'history': asset['history']}
    if len(plan_request['assets']) > 1:
        contexts = {e['asset_id']: e['decision_context'] for e in planning['entities']}
        record['related_contexts'] = [
            {**{k: deepcopy(contexts[a['asset_id']][k]) for k in ('asset_id', 'scope', 'evidence')},
             **{k: deepcopy(a[k]) for k in ('grain', 'history') if k in a}}
            for a in plan_request['assets'][1:]]
    validate_decisions({'schema_version': 1, 'kind': 'design_decisions', 'records': [record]})
    document = deepcopy(decisions['document']) if decisions else {'schema_version': 1, 'kind': 'design_decisions', 'records': []}
    records = document['records']
    matches = [(i, r) for i, r in enumerate(records) if all(r[k] == context[k] for k in ('intent', 'asset_id', 'scope'))]
    selected = [(i, r) for i, r in matches if r['id'] == replacement]
    # An explicit replacement must name the sole record in this exact context.
    if (replacement is not None and (len(matches) != 1 or len(selected) != 1)) or (replacement is None and matches):
        result['questions'].append({'code': 'select_design_record', 'message': 'Explicitly select the sole matching record for replacement, or reconcile competing records in the file.'})
        return result
    index = selected[0][0] if selected else None
    if any(r['id'] == record['id'] and i != index for i, r in enumerate(records)):
        result['questions'].append({'code': 'design_record_id_collision', 'message': 'Choose a record ID not used by another decision.'})
        return result
    if index is None:
        records.append(record)
        patch = [{'op': 'add', 'path': '/records/-', 'value': record}]
    else:
        patch = [{'op': 'test', 'path': f'/records/{index}', 'value': deepcopy(records[index])},
                 {'op': 'replace', 'path': f'/records/{index}', 'value': record}]
        records[index] = record
    validate_decisions(document)
    result.update(status='pending_review', proposed_document=document,
                  decisions_patch=patch if decisions else [{'op': 'add', 'path': '', 'value': document}])
    if decisions is None or document != decisions['document']:
        result['local_update'] = prepare_update(decisions, document)
    try:
        check_bounds(result)
    except ContextLimitError:
        raise DesignDecisionError('Design proposal exceeds response limits; select a smaller decisions file or narrower policy') from None
    return result


def main(argv=None):
    import argparse
    import json
    from .catalog import _document, load_catalog
    from .business_context import load_business_context
    from .design_decisions import load_design_decisions
    from .modelling_policy import load_document
    from .project import discover_project
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--policy', required=True)
    parser.add_argument('--catalog-config', required=True)
    parser.add_argument('--design-decisions')
    parser.add_argument('--business-context')
    parser.add_argument('--target-path')
    args = parser.parse_args(argv)
    try:
        project = discover_project(args.project_dir, target_path=args.target_path)
        request, _ = _document(project.root / args.request)
        result = prepare_design_decision(project, load_document(project.root / args.policy), load_catalog(project.root / args.catalog_config), request,
                                         decisions=load_design_decisions(project.root / args.design_decisions) if args.design_decisions else None,
                                         business=load_business_context(project.root / args.business_context) if args.business_context else None)
        print(json.dumps(result, indent=2))
        return {'pending_review': 0, 'needs_clarification': 2, 'blocked': 1}[result['status']]
    except (ValueError, OSError, TypeError, KeyError, RuntimeError):
        print(json.dumps({'status': 'error', 'code': 'invalid_design_proposal_context'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
