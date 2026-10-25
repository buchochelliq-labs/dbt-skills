import copy
import json
import unittest
import test_business_context as business_fixture


class FollowupDiagnosticsTests(unittest.TestCase):
    setUp = business_fixture.BusinessContextTests.setUp
    write = business_fixture.BusinessContextTests.write

    def test_identical_replacement_is_unchanged_without_payload(self):
        from dbt_skills.business_context import load_business_context
        from dbt_skills.business_context_proposals import prepare_business_update
        before = self.path.read_bytes()
        result = prepare_business_update(load_business_context(self.path), {'section':'concepts', 'record':self.document['concepts'][0], 'replace_record_id':'customer'})
        self.assertEqual(result['status'], 'unchanged')
        self.assertNotIn('local_update', result)
        self.assertEqual(before, self.path.read_bytes())

    def test_acceptance_exposes_bounded_reason(self):
        from dbt_skills.local_context_updates import accept_update, ContextUpdateError
        with self.assertRaises(ContextUpdateError) as error:
            accept_update(self.root, 'business.json', {}, accepted_digest='PRIVATE_SENTINEL')
        self.assertEqual(error.exception.reason, 'digest_mismatch')
        self.assertEqual(str(error.exception), 'context_update_not_saved')

    def test_type_descriptor_is_bounded(self):
        from dbt_skills.metadata_types import validate_descriptor
        descriptor = {'schema_version':1, 'native':'decimal(18,2)', 'family':'decimal', 'parameters':{'precision':18, 'scale':2}}
        validate_descriptor(descriptor)
        for bad in [dict(descriptor, secret='PRIVATE_SENTINEL'), dict(descriptor, native='x'*1025), dict(descriptor, parameters={'precision':True})]:
            with self.assertRaises(ValueError):
                validate_descriptor(bad)

class ReviewToolsTests(unittest.TestCase):
    setUp = business_fixture.BusinessContextTests.setUp
    write = business_fixture.BusinessContextTests.write

    def test_search_filters_pages_and_invalid_are_bounded(self):
        from dbt_skills.context_review import search_records
        from dbt_skills.business_context import load_business_context
        state = {'business': load_business_context(self.path), 'design_decisions':None}
        first = search_records(state, {'kind':'concepts','limit':1})
        self.assertEqual(first['next_offset'], 1)
        self.assertEqual(search_records(state, {'kind':'concepts','record_id':'customer'})['records'][0]['record']['name'], 'Customer')
        for invalid in [{'kind':'concepts','limit':True},{'kind':'concepts','text':'x'*257},{'kind':'concepts','secret':'PRIVATE_SENTINEL'}]:
            with self.assertRaises(ValueError) as error:
                search_records(state, invalid)
            self.assertNotIn('PRIVATE_SENTINEL', str(error.exception))

    def test_review_stale_rebase_preserves_unrelated_and_conflicts(self):
        from dbt_skills.context_review import review_update
        from dbt_skills.local_context_updates import prepare_update
        from dbt_skills.business_context import load_business_context
        base = load_business_context(self.path)
        changed = copy.deepcopy(self.document)
        changed['concepts'][0]['definition'] = 'Reviewed changed definition.'
        proposal = prepare_update(base, changed)
        self.document['concepts'][1]['definition'] = 'Concurrent edit.'
        self.write()
        state = {'business':load_business_context(self.path), 'design_decisions':None}
        result = review_update(state, proposal, rebase=True, baseline=base['document'])
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['reason'], 'rebase_available')
        self.assertEqual(result['rebased_update']['proposed_document']['concepts'][1]['definition'], 'Concurrent edit.')
        self.document['concepts'][0]['definition'] = 'Competing change.'
        self.write()
        state['business'] = load_business_context(self.path)
        self.assertEqual(review_update(state, proposal, rebase=True, baseline=base['document'])['reason'], 'same_record_conflict')

    def test_mapping_record_validates_and_never_enters_design_selection(self):
        from dbt_skills.design_decisions import validate_decisions, select_decision
        record = {'record_type':'metadata_mapping','id':'mapping','record_ids':['customer'],'asset_id':'asset', 'columns':['id'], 'meaning':'represents', 'scope':{'domain':'sales'}, 'rationale':'Review scope.', 'recorded_by':'operator','recorded_at':'2026-10-25T00:00:00Z', 'supporting_evidence':['Reviewed declaration'], 'alternatives':['alternative'], 'status':'proposed', 'evidence':{'business_context_sha256':'a'*64,'catalog_facts_sha256':'b'*64}}
        document = {'schema_version':1,'kind':'design_decisions','records':[record]}
        validate_decisions(document)
        result = select_decision({'document':document}, {'intent':'design','asset_id':'asset','scope':{}}, {})
        self.assertEqual(result['status'],'none')
        for mutation in [dict(record,status='approved'), dict(record,columns=['bad name']),dict(record,meaning='PRIVATE_SENTINEL')]:
            with self.assertRaises(ValueError):
                validate_decisions(dict(document,records=[mutation]))

class FollowupMCPTests(unittest.TestCase):
    setUp = business_fixture.BusinessContextTests.setUp
    write = business_fixture.BusinessContextTests.write

    def test_actual_mcp_discovery_search_review_diff_and_eviction(self):
        import asyncio
        import os
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        async def exercise():
            params = StdioServerParameters(command=sys.executable,args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--business-context','business.json'],env=dict(os.environ,PYTHONPATH='src:tests'))
            async with Client(params,read_timeout_seconds=20) as client:
                tools = {t.name:t for t in (await client.list_tools()).tools}
                for name in ['modelling_context_diff','catalog_resolution_preview','context_update_review','context_records_search','metadata_mapping_propose','model_change_impact']:
                    self.assertIn(name,tools)
                    self.assertTrue(tools[name].annotations.read_only_hint)
                    self.assertFalse(tools[name].input_schema['properties']['request'].get('additionalProperties',True))
                key = (await client.call_tool('modelling_context',{})).structured_content['context_id']
                result = (await client.call_tool('context_records_search',{'context_id':key,'request':{'kind':'concepts','record_id':'customer'}})).structured_content
                self.assertEqual(result['records'][0]['record']['id'],'customer')
                before=self.path.read_bytes()
                request={'section':'concepts','record':dict(self.document['concepts'][0],definition='New definition.'),'replace_record_id':'customer'}
                proposal=(await client.call_tool('business_context_propose',{'context_id':key,'request':request})).structured_content['local_update']
                result=(await client.call_tool('context_update_review',{'context_id':key,'request':{'proposal':proposal}})).structured_content
                self.assertEqual(result['status'],'ready')
                self.assertEqual(before,self.path.read_bytes())
                self.document['concepts'][1]['definition']='Concurrent change.'
                self.write()
                fresh=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                diff=(await client.call_tool('modelling_context_diff',{'context_id':fresh,'request':{'before':key,'after':fresh}})).structured_content
                self.assertEqual(diff['status'],'available')
                self.assertTrue(any('business' in c['path'] for c in diff['changes']))
                review=(await client.call_tool('context_update_review',{'context_id':fresh,'request':{'proposal':proposal,'rebase':True}})).structured_content
                self.assertEqual(review['reason'],'rebase_available')
                for name in ['modelling_context_diff','catalog_resolution_preview','context_update_review','context_records_search','metadata_mapping_propose','model_change_impact']:
                    with self.assertRaises(MCPError) as error:
                        await client.call_tool(name,{'context_id':fresh,'request':{'secret':'PRIVATE_SENTINEL'}})
                    self.assertNotIn('PRIVATE_SENTINEL',str(error.exception))
                for invalid in [{'kind':'concepts','limit':True},{'kind':'concepts','secret':'PRIVATE_SENTINEL'}]:
                    with self.assertRaises(MCPError) as error:
                        await client.call_tool('context_records_search',{'context_id':fresh,'request':invalid})
                    self.assertNotIn('PRIVATE_SENTINEL',str(error.exception))
                for _ in range(8):
                    fresh=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                result=(await client.call_tool('modelling_context_diff',{'context_id':fresh,'request':{'before':key,'after':fresh}})).structured_content
                self.assertEqual(result['status'],'unavailable')
                self.assertEqual(result['reason'],'snapshot_not_retained')
        asyncio.run(exercise())

class CatalogReviewMCPTests(unittest.TestCase):
    def setUp(self):
        import metadata_fixture
        self.fixture=metadata_fixture.MetadataFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        common={'scope':{'domain':'example'},'status':'reviewed','rationale':'Explicit example vocabulary.','recorded_by':'operator','recorded_at':'2026-10-25T00:00:00Z'}
        self.business={'schema_version':1,'kind':'business_context','concepts':[dict(common,id='identifier',name='Identifier',definition='A declared identifier.')],'relationships':[]}
        (self.root/'business.json').write_text(json.dumps(self.business))
        (self.root/'decisions.json').write_text(json.dumps({'schema_version':1,'kind':'design_decisions','records':[]}))

    def test_preview_mapping_impact_historical_access_and_native_mcp_path(self):
        import asyncio, os, sys
        from mcp import Client, MCPError, StdioServerParameters
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--target-path','target','--policy','modelling.yml','--catalog-config','catalogs.json','--business-context','business.json','--design-decisions','decisions.json'],env=dict(os.environ,PYTHONPATH='src:tests'))
            async with Client(params,read_timeout_seconds=20) as client:
                async def invoke(name,key,request):
                    return (await client.call_tool(name,{'context_id':key,'request':request})).structured_content
                key=(await client.call_tool('modelling_context',{})).structured_content['context_id']
                asset='urn:demo:xyz:customers'
                config=(self.root/'catalogs.json').read_bytes()
                preview=await invoke('catalog_resolution_preview',key,{'asset_ids':[asset],'fields':['relation','columns'],'settings':{'provider_priority':{'enabled':True,'order':['physical','curated']},'planning_mode':'partial'}})
                self.assertEqual(preview['status'],'preview')
                self.assertFalse(preview['applied'])
                unobserved=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                unknown=await invoke('modelling_context_diff',unobserved,{'before':key,'after':unobserved,'asset_ids':[asset]})
                self.assertEqual(unknown['catalog_coverage']['unknown_assets'],[asset])
                self.assertFalse(any(c['path'].startswith('/catalog/assets/') for c in unknown['changes']))
                key=unobserved
                self.assertEqual(config,(self.root/'catalogs.json').read_bytes())
                optional=await invoke('catalog_resolution_preview',key,{'asset_ids':[asset],'fields':['relation','columns','primary_key','foreign_keys'],'settings':{}})
                self.assertIn('foreign_keys',optional['current'][asset]['missing'])
                self.assertEqual(optional['withheld']['current'],[])
                self.assertEqual(optional['withheld']['proposed'],[])
                request={'id':'identifier_mapping','record_ids':['identifier'],'asset_id':asset,'columns':['customer_id'],'meaning':'represents','scope':{'domain':'example'},'rationale':'Explicitly declared for review.','recorded_by':'operator','recorded_at':'2026-10-25T00:00:00Z','supporting_evidence':['Selected metadata declaration.']}
                before=(self.root/'decisions.json').read_bytes()
                mapping=await invoke('metadata_mapping_propose',key,request)
                self.assertEqual(mapping['status'],'pending_review')
                self.assertFalse(mapping['verified'])
                self.assertEqual(before,(self.root/'decisions.json').read_bytes())
                self.assertEqual((await invoke('context_update_review',key,{'proposal':mapping['local_update']}))['status'],'ready')
                impact=await invoke('model_change_impact',key,{'asset_ids':[asset],'columns':['customer_id'],'change':'Review identifier metadata change.'})
                self.assertEqual(impact['column_lineage']['status'],'unknown')
                self.assertFalse(impact['zero_impact_established'])
                self.assertIn('source.catalog_workflow.xyz.customers',impact['resource_ids'])
                for name, req in [('catalog_resolution_preview',{'asset_ids':[asset,'outside'],'fields':['columns'],'settings':{}}),('model_change_impact',{'asset_ids':['outside'],'change':'Check'}),('metadata_mapping_propose',dict(request,asset_id='outside'))]:
                    denied=await invoke(name,key,req)
                    self.assertEqual(denied['status'],'denied')
                    self.assertNotIn('customer_id',json.dumps(denied))
                # Provider-native details survive file ingestion and real planning.
                physical=self.root/'physical.json'
                doc=json.loads(physical.read_text())
                for column in doc['assets'][0]['facts']['columns']:
                    if column['name']=='customer_id':
                        column['type_descriptor']={'schema_version':1,'native':'decimal(18,2)','family':'decimal','parameters':{'precision':18,'scale':2}}
                physical.write_text(json.dumps(doc))
                fresh=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                plan=await invoke('model_plan',fresh,{'intent':'Review identifier','assets':[{'asset_id':asset}]})
                selected=plan['evidence'][asset]['selected']['columns']['value']
                self.assertEqual(next(c for c in selected if c['name']=='customer_id')['type_descriptor']['parameters']['precision'],18)
                # Current unavailable provider withholds every historical fact.
                physical.unlink()
                diff=await invoke('modelling_context_diff',fresh,{'before':key,'after':fresh,'asset_ids':[asset]})
                self.assertEqual(diff['status'],'denied')
                self.assertEqual(diff['changes'],[])
        asyncio.run(exercise())

class NativeAssessmentTests(unittest.TestCase):
    def test_native_precision_mismatch_requires_review_even_when_normalized_equal(self):
        from dbt_skills.metadata_types import assess_native_types
        left={'schema_version':1,'native':'decimal(18,2)','family':'decimal','parameters':{'precision':18,'scale':2}}
        right=dict(left,native='decimal(10,4)',parameters={'precision':10,'scale':4})
        result=assess_native_types(left,right)
        self.assertEqual(result['assessment'],'requires_review')
        self.assertFalse(result['verified'])
        self.assertEqual(assess_native_types(left,left)['assessment'],'unverified_match')
        self.assertEqual(assess_native_types(left,None)['assessment'],'unknown')

class EffectivePolicyTests(unittest.TestCase):
    def test_failed_provider_reports_enabled_or_disabled_effective_policy_without_facts(self):
        from dbt_skills.catalog import CatalogResolver, ProviderResult
        class FailingProvider:
            id='physical'
            def fetch(self,asset_id,fields):
                return ProviderResult('error')
        for enabled in (True,False):
            settings={'provider_priority':{'enabled':enabled,'order':['physical']}}
            result=CatalogResolver([FailingProvider()],settings).resolve('asset',['columns'])
            self.assertEqual(result['status'],'error')
            self.assertEqual(result['selected'],{})
            self.assertEqual(result['claims'],{})
            self.assertEqual(result['effective_policy']['provider_priority']['enabled'],enabled)
            self.assertEqual('explicit provider priority' in result['selection'],enabled)


class AcceptanceReasonsTests(unittest.TestCase):
    def setUp(self):
        from test_local_context_updates import LocalUpdateTests
        LocalUpdateTests.setUp(self)

    def test_actionable_reasons_preserve_bytes_and_do_not_echo_input(self):
        from dbt_skills.local_context_updates import accept_update, ContextUpdateError
        from unittest.mock import patch
        before=self.path.read_bytes()
        cases=[('digest_mismatch',dict(self.proposal,proposal_sha256='PRIVATE_SENTINEL'),None),
               ('target_conflict',self.proposal,'lock'),('write_failure',self.proposal,'write')]
        for expected,proposal,operation in cases:
            with self.subTest(reason=expected):
                if operation=='lock':
                    self.path.with_name('business.json.lock').touch()
                try:
                    if operation=='write':
                        with patch('dbt_skills.local_context_updates.os.replace',side_effect=OSError('PRIVATE_SENTINEL')):
                            with self.assertRaises(ContextUpdateError) as caught:
                                accept_update(self.root,'business.json',proposal,accepted_digest=self.proposal['proposal_sha256'])
                    else:
                        with self.assertRaises(ContextUpdateError) as caught:
                            accept_update(self.root,'business.json',proposal,accepted_digest=self.proposal['proposal_sha256'])
                    self.assertEqual(caught.exception.reason,expected)
                    self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))
                    self.assertEqual(before,self.path.read_bytes())
                finally:
                    self.path.with_name('business.json.lock').unlink(missing_ok=True)
        self.path.write_text(json.dumps(self.changed))
        with self.assertRaises(ContextUpdateError) as caught:
            accept_update(self.root,'business.json',self.proposal,accepted_digest=self.proposal['proposal_sha256'])
        self.assertEqual(caught.exception.reason,'stale_base')

class DescriptorBoundaryTests(unittest.TestCase):
    def test_nested_descriptor_rejects_depth_nodes_unknown_keys_and_nan(self):
        from dbt_skills.metadata_types import validate_descriptor
        from dbt_skills.catalog import _validate_facts, CatalogError
        leaf={'schema_version':1,'native':'string','family':'string','name':'id'}
        nested={'schema_version':1,'native':'struct<id:string>','family':'struct','children':[leaf]}
        _validate_facts({'columns':[{'name':'payload','type':'struct','nullable':None,'type_descriptor':nested}]})
        invalid=[]
        deep=copy.deepcopy(leaf)
        for _ in range(5):
            deep={'schema_version':1,'native':'array<string>','family':'array','children':[deep]}
        invalid.extend([deep,dict(nested,children=[leaf]*33),dict(leaf,family=[]),dict(leaf,parameters={'scale':float('nan')}),dict(leaf,unknown='PRIVATE_SENTINEL')])
        for descriptor in invalid:
            with self.assertRaises((ValueError,TypeError)):
                validate_descriptor(descriptor)
            with self.assertRaises(CatalogError) as caught:
                _validate_facts({'columns':[{'name':'payload','type':'struct','nullable':None,'type_descriptor':descriptor}]})
            self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))

class HistoryEvidenceTests(unittest.TestCase):
    def test_sparse_reads_preserve_superset_and_clock_changes_are_ignored(self):
        from dbt_skills.review_workflow import EvidenceHistory
        class Catalog:
            config=None
            resolution={}
        state={'context_id':'a'*32,'business':None,'design_decisions':None,'policy':None,'proposals':None,'snapshot':{'manifest':{}},'catalog':Catalog()}
        history=EvidenceHistory()
        history.retain(state)
        broad={'asset_id':'asset','status':'complete','selected':{'relation':{'value':{'name':'asset'},'provenance':{'retrieved_at':'old'}},'columns':{'value':[],'provenance':{'retrieved_at':'old'}}},'claims':{},'missing':[],'conflicts':[],'resolved_conflicts':[],'unresolved_conflicts':[]}
        history.observe(state,broad)
        sparse=copy.deepcopy(broad)
        sparse['selected'].pop('relation')
        sparse['selected']['columns']['provenance']['retrieved_at']='new'
        history.observe(state,sparse)
        self.assertIn('relation',history.snapshots[state['context_id']]['catalog']['assets']['asset']['selected'])

class NativeRelationshipMCPTests(unittest.TestCase):
    setUp = CatalogReviewMCPTests.setUp
    def test_native_parameters_reach_relationship_assessment_and_invalid_refresh_fails_closed(self):
        import asyncio, os, sys
        from mcp import Client, MCPError, StdioServerParameters
        from test_model_planning import ModelPlanningTests
        path,document=ModelPlanningTests.add_orders(self)
        for asset in document['assets']:
            for column in asset['facts'].get('columns',[]):
                if column['name']=='customer_id':
                    precision=18 if asset['id'].endswith('customers') else 10
                    column['type']='decimal'
                    column['type_descriptor']={'schema_version':1,'native':f'decimal({precision},2)','family':'decimal','parameters':{'precision':precision,'scale':2}}
        path.write_text(json.dumps(document))
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--policy','modelling.yml','--catalog-config','catalogs.json'],env=dict(os.environ,PYTHONPATH='src:tests'))
            async with Client(params,read_timeout_seconds=20) as client:
                key=(await client.call_tool('modelling_context',{})).structured_content['context_id']
                request={'intent':'Review type declaration','assets':[{'asset_id':'urn:demo:xyz:customers'},{'asset_id':'urn:demo:xyz:orders'}]}
                plan=(await client.call_tool('model_plan',{'context_id':key,'request':request})).structured_content
                assessment=plan['relationships'][0]['type_assessments'][0]
                self.assertEqual(assessment['assessment'],'exact')
                self.assertEqual(assessment['native_type_evidence']['assessment'],'requires_review')
                self.assertEqual(assessment['severity'],'warning')
                self.assertFalse(assessment['native_type_evidence']['verified'])
                document['assets'][0]['facts']['columns'][0]['type_descriptor']={'schema_version':1,'native':'PRIVATE_SENTINEL','family':'int64','secret':'PRIVATE_SENTINEL'}
                path.write_text(json.dumps(document))
                with self.assertRaises(MCPError) as caught:
                    await client.call_tool('modelling_refresh',{})
                self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))
                plan=(await client.call_tool('model_plan',{'context_id':key,'request':request})).structured_content
                self.assertEqual(plan['status'],'blocked')
                self.assertEqual(plan['evidence'],{})
        asyncio.run(exercise())
