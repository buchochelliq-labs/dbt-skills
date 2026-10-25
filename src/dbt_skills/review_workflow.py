"""Read-only MCP review surfaces; historical evidence never grants access."""
from collections import OrderedDict
from copy import copy, deepcopy

from mcp import MCPError
from .catalog import CatalogError, resolution_options
from .context_limits import check_bounds
from .context_review import field_changes, page, review_update, search_records
from .local_context_updates import _digest, prepare_update
from .planning_contracts import (SearchInput, PreviewInput, DiffInput, ReviewInput, MappingInput, ImpactInput,
    RecordsSearchRequest, ResolutionPreviewRequest, DiffRequest, UpdateReviewRequest, MappingRequest, ImpactRequest, validate_request)


class EvidenceHistory:
    """Eight bounded snapshots; catalog facts recorded only on explicit review calls."""
    def __init__(self):
        self.snapshots = OrderedDict()

    def retain(self, state):
        # inspect_artifacts projects resource metadata and strips raw/compiled SQL.
        snapshot = {key:deepcopy(state[key]) for key in ('business','policy','proposals','design_decisions')}
        snapshot['manifest'] = deepcopy(state['snapshot']['manifest'])
        catalog = state.get('catalog')
        snapshot['catalog'] = {'config':deepcopy(catalog.config), 'resolution':deepcopy(catalog.resolution), 'assets':{}} if catalog else None
        check_bounds(snapshot)
        self.snapshots[state['context_id']] = snapshot
        while len(self.snapshots) > 8:
            self.snapshots.popitem(last=False)

    def observe(self, state, facts):
        snapshot = self.snapshots[state['context_id']]
        assets = snapshot['catalog']['assets']
        if facts['asset_id'] in assets or len(assets) < 32:
            candidate = deepcopy(snapshot)
            retained = deepcopy(facts)
            previous = assets.get(facts['asset_id'])
            fields = set(facts.get('selected',{})) | set(facts.get('claims',{})) | set(facts.get('missing',[]))
            retained['observed_fields'] = sorted(fields | set(previous.get('observed_fields',[]))) if previous else sorted(fields)
            if previous and facts['status'] not in ('denied','error') and previous['status'] not in ('denied','error'):
                for key in ('selected','claims'):
                    retained[key] = {**{k:deepcopy(v) for k,v in previous[key].items() if k not in fields}, **retained[key]}
                for key in ('missing','conflicts','resolved_conflicts','unresolved_conflicts'):
                    retained[key] = sorted((set(previous[key]) - fields) | set(retained[key]))
            candidate['catalog']['assets'][facts['asset_id']] = retained
            try:
                check_bounds(candidate)
            except ValueError:
                return
            self.snapshots[state['context_id']] = candidate


def without_observation_clocks(value):
    if isinstance(value,dict):
        return {k:without_observation_clocks(v) for k,v in value.items() if k not in ('retrieved_at','verified_at','observed_at','age_seconds')}
    if isinstance(value,list):
        return [without_observation_clocks(v) for v in value]
    return value


def referenced_assets(records):
    """Every catalog evidence identity in a reviewed record, never just its anchor."""
    identifiers = set()
    for record in records:
        if record.get('asset_id'):
            identifiers.add(record['asset_id'])
        identifiers.update(record.get('alternatives', []))
        identifiers.update(context['asset_id'] for context in record.get('related_contexts', []))
        identifiers.update(answer['target_asset'] for answer in record.get('answers', []) if answer.get('target_asset'))
    return identifiers


def selected_records(loaded, asset_ids=None, record_ids=None):
    if not loaded:
        return []
    return [record for record in loaded['document']['records']
            if (record_ids is None or record['id'] in record_ids)
            and (asset_ids is None or bool(referenced_assets([record]) & set(asset_ids)))]


def register_review_tools(server, state, history, call, read_annotation):
    def guarded(context_id, model, request, run):
        def checked():
            try:
                clean = validate_request(model, request)
                result = run(clean)
                check_bounds(result)
                return {**result,'context_id':context_id}
            except (ValueError, TypeError, KeyError, OSError, RecursionError):
                raise MCPError(-32602,'Invalid bounded review request or unavailable selected evidence') from None
        return call(context_id, checked)

    def authorize(identifiers, fields=None):
        catalog = state.get('catalog')
        if catalog is None:
            return None
        facts = {}
        for identifier in identifiers:
            result = catalog.resolve(identifier, fields or ['relation','columns'])
            if result['status'] in ('error','denied'):
                return None
            facts[identifier] = result
        # An all-or-nothing gate; do not retain a successful prefix of a denial.
        for result in facts.values():
            history.observe(state,result)
        return facts

    def current_local():
        from .business_context import load_business_context
        from .design_decisions import load_design_decisions
        current = dict(state)
        for key, loader in [('business',load_business_context),('design_decisions',load_design_decisions)]:
            loaded = state.get(key)
            if loaded:
                current[key] = loader(loaded['provenance']['document'])
        return current

    @server.tool(annotations=read_annotation, description='Compare two of eight retained metadata snapshots, with bounded field changes and affected decisions. Historical facts require current scope/provider access. Catalog evidence is limited to up to 32 explicitly observed assets per snapshot; missing observations are unknown. Never authorizes stale planning.')
    def modelling_context_diff(context_id: str, request: DiffInput) -> dict[str, object]:
        def run(req):
            before, after = history.snapshots.get(req['before']), history.snapshots.get(req['after'])
            if before is None or after is None:
                return {'status':'unavailable','reason':'snapshot_not_retained','changes':[]}
            left, right = deepcopy(before), deepcopy(after)
            asset_ids = req.get('asset_ids')
            observed = set()
            for snap in (left,right):
                if snap['catalog']:
                    observed.update(snap['catalog']['assets'])
            identifiers = asset_ids if asset_ids is not None else sorted(observed)
            exposed_records = []
            for snap in (left, right):
                records = selected_records(snap['design_decisions'], asset_ids, req.get('record_ids'))
                exposed_records.extend(records)
                if records:
                    snap['design_decisions']['document']['records'] = records
                else:
                    # Empty asset filters provide business/policy-only evidence,
                    # including no decision revision, locator or affected IDs.
                    snap['design_decisions'] = None
                if asset_ids == []:
                    snap['catalog'] = None
                    snap['manifest'] = None
            affected_records = selected_records(state.get('design_decisions'), asset_ids, req.get('record_ids'))
            authorization_ids = set(identifiers) | referenced_assets(exposed_records + affected_records)
            if authorization_ids and authorize(sorted(authorization_ids)) is None:
                return {'status':'denied','reason':'current_access_unavailable','changes':[], 'affected_decisions':[]}
            unknown = []
            compared_assets = {}
            for identifier in identifiers:
                values = [snap['catalog']['assets'].get(identifier) if snap['catalog'] else None for snap in (left,right)]
                if any(value is None for value in values):
                    unknown.append(identifier)
                    continue
                common = set(values[0].get('observed_fields',[])) & set(values[1].get('observed_fields',[]))
                if set(values[0].get('observed_fields',[])) != set(values[1].get('observed_fields',[])):
                    unknown.append(identifier)
                compared_assets[identifier] = [
                    {'selected':{k:v for k,v in value['selected'].items() if k in common},
                     'claims':{k:v for k,v in value['claims'].items() if k in common},
                     'missing':[k for k in value['missing'] if k in common]}
                    for value in values]
            for side,snap in enumerate((left,right)):
                if snap['catalog']:
                    snap['catalog']['assets'] = {identifier:values[side] for identifier,values in compared_assets.items()}
                if req.get('record_ids') is not None:
                    for key, sections in [('business',('concepts','relationships')),('design_decisions',('records',))]:
                        if snap[key]:
                            for section in sections:
                                snap[key]['document'][section] = [r for r in snap[key]['document'][section] if r['id'] in req['record_ids']]
            changes = field_changes(without_observation_clocks(left),without_observation_clocks(right))
            offset,limit = page(req)
            affected = [record['id'] for record in affected_records]
            return {'status':'available','before':req['before'],'after':req['after'],'historical_evidence_only':True,
                    'changes':changes[offset:offset+limit],'total':len(changes),'next_offset':offset+limit if offset+limit<len(changes) else None,
                    'affected_decisions':affected[:128], 'catalog_coverage':{'observed_assets':identifiers,'unknown_assets':unknown},
                    'limitations':['Unobserved facts are unknown; snapshot retention is process-local and bounded to eight contexts','Affected decisions are conservative candidates, not proven downstream effects']}
        return guarded(context_id,DiffRequest,request,run)

    @server.tool(annotations=read_annotation, description='Compare current and proposed resolution settings using the same scoped providers. Returns conflicts, missing facts and attempts, without changing configuration. Denial or failure clears both selections for all requested assets.')
    def catalog_resolution_preview(context_id: str, request: PreviewInput) -> dict[str, object]:
        def run(req):
            catalog = state.get('catalog')
            if catalog is None:
                return {'status':'unavailable','reason':'catalog_unconfigured','applied':False}
            settings = resolution_options(req['settings'],[p.id for p in catalog.providers])
            preview = copy(catalog)
            preview.resolution = settings
            current, proposed = {}, {}
            for identifier in req['asset_ids']:
                current[identifier] = catalog.resolve(identifier,req['fields'])
                proposed[identifier] = preview.resolve(identifier,req['fields'])
                if any(r['status'] in ('error','denied') for r in (current[identifier],proposed[identifier])):
                    return {'status':'denied','reason':'current_access_unavailable','applied':False,'current':{},'proposed':{}}
            for result in current.values():
                history.observe(state,result)
            def withheld(results,mode):
                conflicts = [identifier for identifier,r in results.items() if r['unresolved_conflicts']]
                if conflicts and mode == 'conservative':
                    return list(results)
                return conflicts
            return {'status':'preview','applied':False,'current_settings':deepcopy(catalog.resolution),'proposed_settings':settings,
                    'current':current,'proposed':proposed,
                    'withheld':{'current':withheld(current,catalog.resolution['planning_mode']),'proposed':withheld(proposed,settings['planning_mode'])},
                    'limitations':['No configuration is changed','Unqueried or unknown providers do not imply agreement; metadata is unverified']}
        return guarded(context_id,ResolutionPreviewRequest,request,run)

    @server.tool(annotations=read_annotation, description='Review a digest-bound local update as ready, unchanged, stale or invalid. Optional rebase uses a retained exact base and preserves unrelated records; same-record conflicts are explicit. New payloads require fresh operator digest acceptance. No writes.')
    def context_update_review(context_id: str, request: ReviewInput) -> dict[str, object]:
        def run(req):
            proposal = req['proposal']
            baseline = None
            for snapshot in history.snapshots.values():
                for key in ('business','design_decisions'):
                    loaded = snapshot.get(key)
                    if loaded and loaded['provenance'] == proposal.get('base'):
                        baseline = loaded['document']
            current = current_local()
            result = review_update(current,proposal,rebase=req['rebase'],baseline=baseline)
            records = []
            has_design_payload = any(result.get(key, {}).get('proposed_document', {}).get('kind') == 'design_decisions'
                                     for key in ('local_update', 'rebased_update'))
            if has_design_payload:
                # Full review diffs expose deletions/replacements on the before
                # side too. Rebase uses current as its new base; retain the exact
                # original baseline gate as well, never just the final records.
                documents = [baseline, proposal['proposed_document']]
                if current.get('design_decisions'):
                    documents.append(current['design_decisions']['document'])
                for document in documents:
                    if document and document.get('kind') == 'design_decisions':
                        records.extend(document['records'])
            for key in ('local_update', 'rebased_update'):
                document = result.get(key, {}).get('proposed_document', {})
                if document.get('kind') == 'design_decisions':
                    records.extend(document['records'])
            ids = referenced_assets(records)
            if ids and authorize(sorted(ids)) is None:
                return {'status':'denied','reason':'current_access_unavailable'}
            return result
        return guarded(context_id,UpdateReviewRequest,request,run)

    @server.tool(annotations=read_annotation, description='Search pinned local concepts, relationships, design decisions or explicit mappings by ID, bounded text, scope and status. Bounded pagination and provenance; supplied status is not verified approval. UOL is optional and not searched implicitly.')
    def context_records_search(context_id: str, request: SearchInput) -> dict[str, object]:
        def run(req):
            result = search_records(state,req)
            if req['kind'] in ('decisions','mappings'):
                ids = referenced_assets([item['record'] for item in result['records']])
                if ids and authorize(sorted(ids)) is None:
                    return {'status':'denied','records':[],'next_offset':None}
            return result
        return guarded(context_id,RecordsSearchRequest,request,run)

    @server.tool(annotations=read_annotation, description='Propose an explicit scope-bound concept/relationship to asset/column mapping in the selected design-decision store. Preserves alternatives and evidence; returns a pending digest-bound local update, never proof, inferred equivalence, approval or saving. Requires selected business and decisions documents.')
    def metadata_mapping_propose(context_id: str, request: MappingInput) -> dict[str, object]:
        def run(req):
            current = current_local()
            for key in ('business','design_decisions'):
                if current.get(key) is None or current[key] != state[key]:
                    raise ValueError
            facts = authorize([req['asset_id']]+req['alternatives'])
            if facts is None:
                return {'status':'denied','reason':'current_access_unavailable'}
            selected = facts[req['asset_id']]['selected']
            if 'relation' not in selected or 'columns' not in selected or facts[req['asset_id']]['unresolved_conflicts']:
                return {'status':'unavailable','reason':'mapping_evidence_incomplete'}
            if not set(req['columns']) <= {c['name'] for c in selected['columns']['value']}:
                raise ValueError
            local_records = {r['id']:r for section in ('concepts','relationships') for r in current['business']['document'][section]}
            if not req['scope'] or any(i not in local_records or local_records[i]['scope'] != req['scope'] for i in req['record_ids']):
                raise ValueError
            replacement = req.pop('replace_record_id',None)
            record = {**req,'record_type':'metadata_mapping','status':'proposed',
                      'evidence':{'business_context_sha256':current['business']['provenance']['sha256'],'catalog_facts_sha256':_digest(facts)}}
            document = deepcopy(current['design_decisions']['document'])
            matches = [i for i,r in enumerate(document['records']) if r['id']==record['id']]
            if matches:
                if replacement != record['id'] or len(matches)!=1 or document['records'][matches[0]].get('record_type')!='metadata_mapping':
                    raise ValueError
                document['records'][matches[0]]=record
            elif replacement is not None:
                raise ValueError
            else:
                document['records'].append(record)
            before_and_after = current['design_decisions']['document']['records'] + document['records']
            if authorize(sorted(referenced_assets(before_and_after))) is None:
                return {'status':'denied','reason':'current_access_unavailable'}
            if document==current['design_decisions']['document']:
                return {'status':'unchanged'}
            return {'status':'pending_review','mapping':record,'verified':False,'local_update':prepare_update(current['design_decisions'],document),
                    'limitations':['Explicit assertion only; alternatives remain unresolved','Only operator acceptance of the exact reviewed digest can save local context']}
        return guarded(context_id,MappingRequest,request,run)

    @server.tool(annotations=read_annotation, description='Report conservative affected decisions and known manifest resource lineage for explicitly selected metadata/design changes. Column lineage remains unknown; absent evidence is never zero impact. No joins, SQL or lineage edges are invented.')
    def model_change_impact(context_id: str, request: ImpactInput) -> dict[str, object]:
        def run(req):
            facts = authorize(req['asset_ids'])
            if facts is None:
                return {'status':'denied','reason':'current_access_unavailable','affected_decisions':[],'resource_lineage':[]}
            manifest = state['snapshot']['manifest']
            resources = manifest.get('resources',[])
            roots = set()
            for asset in facts.values():
                relation = asset['selected'].get('relation',{}).get('value',{})
                if not all(isinstance(relation.get(k),str) and relation[k] for k in ('catalog','schema','name')):
                    continue
                roots.update(r['unique_id'] for r in resources if (r.get('database'),r.get('schema'),(r.get('identifier') if r.get('resource_type')=='source' else r.get('alias')) or r.get('name'))==(relation.get('catalog'),relation.get('schema'),relation.get('name')))
            edges = manifest.get('resource_edges',[])
            reached = set(roots)
            for _ in range(len(resources)):
                added = {e['from'] for e in edges if e['to'] in reached} - reached
                if not added:
                    break
                reached.update(added)
            lineage = [deepcopy(e) for e in edges if e['from'] in reached and e['to'] in reached]
            decisions=state.get('design_decisions')
            affected_records = [r for r in decisions['document']['records'] if r['id'] in req['record_ids'] or referenced_assets([r]) & set(req['asset_ids']) or set(r.get('record_ids',[])) & set(req['record_ids'])] if decisions else []
            ids = referenced_assets(affected_records)
            if ids and authorize(sorted(ids)) is None:
                return {'status':'denied','reason':'current_access_unavailable','affected_decisions':[],'resource_lineage':[]}
            affected = [r['id'] for r in affected_records]
            offset,limit=page(req)
            return {'status':'review_required','change':req['change'],'affected_decisions':affected,'resource_lineage':lineage[offset:offset+limit],
                    'resource_ids':sorted(reached)[:128],'resource_ids_total':len(reached),'resource_ids_truncated':len(reached)>128,'total':len(lineage),'next_offset':offset+limit if offset+limit<len(lineage) else None,
                    'known':{'resource_lineage':bool(roots),'direct_decision_links':bool(decisions)},
                    'unknown':['column_lineage','unrecorded_semantic_dependencies','upstream_changes_outside_selected_project'],
                    'column_lineage':{'status':'unknown','edges':[]},'zero_impact_established':False,
                    'limitations':['Resource dependencies are not column lineage','Declared foreign keys and name similarity do not establish semantic mappings']}
        return guarded(context_id,ImpactRequest,request,run)
