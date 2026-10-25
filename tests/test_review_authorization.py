"""Real stdio regressions for complete linked-record gates and valid continuation."""
import asyncio
import copy
import json
import os
import sys
import unittest
from mcp import Client, StdioServerParameters
import test_followup as fixtures

ASSET='urn:demo:xyz:customers'
RELATED='urn:demo:xyz:orders'


class ReviewAuthorizationTests(unittest.TestCase):
    setUp=fixtures.CatalogReviewMCPTests.setUp

    def mapping(self, **changes):
        record={'record_type':'metadata_mapping','id':'mapping','record_ids':['identifier'],'asset_id':ASSET,'columns':['customer_id'],'meaning':'represents','scope':{'domain':'example'},'rationale':'PRIVATE_RETAINED_ASSERTION','recorded_by':'operator','recorded_at':'2026-10-25T00:00:00Z','supporting_evidence':['Declared evidence'],'alternatives':[],'status':'proposed','evidence':{'business_context_sha256':'a'*64,'catalog_facts_sha256':'b'*64}}
        return dict(record,**changes)

    def write_records(self, records):
        (self.root/'decisions.json').write_text(json.dumps({'schema_version':1,'kind':'design_decisions','records':records}))

    def client(self):
        return Client(StdioServerParameters(command=sys.executable,args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--policy','modelling.yml','--catalog-config','catalogs.json','--business-context','business.json','--design-decisions','decisions.json'],env=dict(os.environ,PYTHONPATH='src:tests')),read_timeout_seconds=30)

    async def key(self,client):
        return (await client.call_tool('modelling_context',{})).structured_content['context_id']

    async def invoke(self,client,name,key,request):
        return (await client.call_tool(name,{'context_id':key,'request':request})).structured_content

    def test_review_deletion_and_mapping_replacement_gate_removed_base_evidence(self):
        from dbt_skills.design_decisions import load_design_decisions
        from dbt_skills.local_context_updates import prepare_update
        self.write_records([self.mapping(alternatives=['outside_project'])])
        loaded=load_design_decisions(self.root/'decisions.json')
        deletion=prepare_update(loaded,dict(loaded['document'],records=[]))
        replacement={k:v for k,v in self.mapping(rationale='Allowed replacement').items() if k not in ('record_type','status','evidence')}
        replacement['replace_record_id']='mapping'
        self.assertNotIn('PRIVATE_',json.dumps(replacement))
        self.assertNotIn('outside_project',json.dumps(replacement))
        async def exercise():
            async with self.client() as client:
                key=await self.key(client)
                for name,request in [('context_update_review',{'proposal':deletion}),('metadata_mapping_propose',replacement)]:
                    with self.subTest(tool=name):
                        result=await self.invoke(client,name,key,request)
                        self.assertEqual(result['status'],'denied')
                        self.assertNotIn('PRIVATE_',json.dumps(result))
                        self.assertNotIn('outside_project',json.dumps(result))
                        self.assertNotIn('local_update',result)
        asyncio.run(exercise())

    def test_stale_rebase_gates_old_record_after_its_scope_is_removed(self):
        from test_model_planning import ModelPlanningTests
        from dbt_skills.design_decisions import load_design_decisions
        from dbt_skills.local_context_updates import prepare_update
        ModelPlanningTests.add_orders(self)
        self.write_records([self.mapping(asset_id=RELATED)])
        loaded=load_design_decisions(self.root/'decisions.json')
        deletion=prepare_update(loaded,dict(loaded['document'],records=[]))
        async def exercise():
            async with self.client() as client:
                await self.key(client)
                # Preserve the old record; concurrently add unrelated allowed context.
                self.write_records([self.mapping(asset_id=RELATED),self.mapping(id='unrelated',rationale='Allowed concurrent assertion')])
                manifest=json.loads(self.fixture.manifest.read_text())
                manifest['sources'].pop('source.catalog_workflow.xyz.orders')
                self.fixture.manifest.write_text(json.dumps(manifest))
                key=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                result=await self.invoke(client,'context_update_review',key,{'proposal':deletion,'rebase':True})
                self.assertEqual(result['status'],'denied')
                self.assertNotIn('PRIVATE_',json.dumps(result))
                self.assertNotIn(RELATED,json.dumps(result))
                self.assertNotIn('rebased_update',result)
                # Business-only reviews remain independent of inaccessible decisions.
                from dbt_skills.business_context import load_business_context
                business=load_business_context(self.root/'business.json')
                changed=copy.deepcopy(business['document'])
                changed['concepts'][0]['definition']='Clarified local meaning.'
                result=await self.invoke(client,'context_update_review',key,{'proposal':prepare_update(business,changed)})
                self.assertEqual(result['status'],'ready')
        asyncio.run(exercise())

    def test_diff_filters_cannot_disclose_ungated_records_and_business_only_stays_usable(self):
        from test_model_planning import ModelPlanningTests
        ModelPlanningTests.add_orders(self)
        self.write_records([self.mapping()])
        async def exercise():
            async with self.client() as client:
                old=await self.key(client)
                self.write_records([self.mapping(rationale='PRIVATE_CHANGED_ASSERTION')])
                self.business['concepts'][0]['definition']='Updated local vocabulary.'
                (self.root/'business.json').write_text(json.dumps(self.business))
                new=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                unrelated=await self.invoke(client,'modelling_context_diff',new,{'before':old,'after':new,'asset_ids':[RELATED]})
                self.assertEqual(unrelated['status'],'available')
                self.assertNotIn('PRIVATE_',json.dumps(unrelated))
                self.assertEqual(unrelated['affected_decisions'],[])
                (self.root/'physical.json').unlink()
                denied=await self.invoke(client,'modelling_context_diff',new,{'before':old,'after':new})
                self.assertEqual(denied['status'],'denied')
                self.assertNotIn('PRIVATE_',json.dumps(denied))
                for asset_ids in ([],['unrelated']):
                    result=await self.invoke(client,'modelling_context_diff',new,{'before':old,'after':new,'asset_ids':asset_ids})
                    self.assertNotIn('PRIVATE_',json.dumps(result))
                    self.assertNotIn('mapping',json.dumps(result))
                    if not asset_ids:
                        self.assertEqual(result['status'],'available')
                        self.assertTrue(any('business' in c['path'] for c in result['changes']))
        asyncio.run(exercise())

    def test_removed_scope_blocks_retained_records_even_without_observations(self):
        self.write_records([self.mapping()])
        async def exercise():
            async with self.client() as client:
                old=await self.key(client)
                self.write_records([self.mapping(rationale='PRIVATE_CHANGED_ASSERTION')])
                manifest=json.loads(self.fixture.manifest.read_text())
                manifest['sources']={}
                self.fixture.manifest.write_text(json.dumps(manifest))
                new=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                result=await self.invoke(client,'modelling_context_diff',new,{'before':old,'after':new})
                self.assertEqual(result['status'],'denied')
                self.assertNotIn('PRIVATE_',json.dumps(result))
                result=await self.invoke(client,'modelling_context_diff',new,{'before':old,'after':new,'asset_ids':[]})
                self.assertEqual(result['affected_decisions'],[])
                self.assertNotIn('PRIVATE_',json.dumps(result))
        asyncio.run(exercise())

    def test_saved_alternatives_and_record_id_impact_gate_every_link(self):
        self.write_records([self.mapping(alternatives=['outside_project'])])
        async def exercise():
            async with self.client() as client:
                key=await self.key(client)
                for name,request in [('context_records_search',{'kind':'mappings'}),('model_change_impact',{'asset_ids':[ASSET],'record_ids':['mapping'],'change':'Review change'})]:
                    result=await self.invoke(client,name,key,request)
                    self.assertEqual(result['status'],'denied')
                    self.assertNotIn('mapping',json.dumps(result))
                    self.assertNotIn('outside_project',json.dumps(result))
                from dbt_skills.design_decisions import load_design_decisions
                from dbt_skills.local_context_updates import prepare_update
                loaded=load_design_decisions(self.root/'decisions.json')
                changed=copy.deepcopy(loaded['document'])
                changed['records'][0]['rationale']='Revised assertion'
                proposal=prepare_update(loaded,changed)
                result=await self.invoke(client,'context_update_review',key,{'proposal':proposal})
                self.assertEqual(result['status'],'denied')
                request={k:v for k,v in self.mapping(id='new_mapping').items() if k not in ('record_type','status','evidence')}
                result=await self.invoke(client,'metadata_mapping_propose',key,request)
                self.assertEqual(result['status'],'denied')
                self.assertNotIn('PRIVATE_',json.dumps(result))

        asyncio.run(exercise())

    def test_impact_explicit_record_id_cannot_expose_an_unselected_anchor(self):
        self.write_records([self.mapping(id='outside_decision',asset_id='outside_project')])
        async def exercise():
            async with self.client() as client:
                key=await self.key(client)
                result=await self.invoke(client,'model_change_impact',key,{'asset_ids':[ASSET],'record_ids':['outside_decision'],'change':'Review explicit record'})
                self.assertEqual(result['status'],'denied')
                self.assertEqual(result['affected_decisions'],[])
                self.assertNotIn('outside_decision',json.dumps(result))
        asyncio.run(exercise())

    def test_related_context_provider_failure_and_removal_block_search_and_impact(self):
        from test_model_planning import ModelPlanningTests
        path,document=ModelPlanningTests.add_orders(self)
        order=document['assets'].pop()
        path.write_text(json.dumps(document))
        (self.root/'related.json').write_text(json.dumps({'schema_version':1,'generated_at':'2026-10-25T00:00:00Z','assets':[order]}))
        config=json.loads((self.root/'catalogs.json').read_text())
        config['providers'].append({'id':'related','type':'file','path':'related.json','scope':'demo'})
        (self.root/'catalogs.json').write_text(json.dumps(config))
        evidence={k:'a'*64 for k in ['policy_sha256','manifest_sha256','catalog_config_sha256','catalog_facts_sha256']}
        record={'id':'design','intent':'Design review','asset_id':ASSET,'scope':{},'grain':['customer_id'],'history':'current','rationale':'PRIVATE_RETAINED_ASSERTION','recorded_by':'operator','recorded_at':'2026-10-25T00:00:00Z','evidence':evidence,'related_contexts':[{'asset_id':RELATED,'scope':{},'evidence':evidence}], 'answers':[{'question_code':'confirm_relationship','answer':'Review link','rationale':'Declared context','target_asset':RELATED,'columns':['customer_id'],'target_columns':['customer_id']}]}
        self.write_records([record])
        async def exercise():
            async with self.client() as client:
                key=await self.key(client)
                self.assertEqual((await self.invoke(client,'context_records_search',key,{'kind':'decisions'}))['status'],'available')
                raw=(self.root/'related.json').read_bytes()
                (self.root/'related.json').unlink()
                for name,request in [('context_records_search',{'kind':'decisions'}),('model_change_impact',{'asset_ids':[ASSET],'record_ids':['design'],'change':'Review linked change'})]:
                    result=await self.invoke(client,name,key,request)
                    self.assertEqual(result['status'],'denied')
                    self.assertNotIn('design',json.dumps(result))
                (self.root/'related.json').write_bytes(raw)
                manifest=json.loads(self.fixture.manifest.read_text())
                manifest['sources'].pop('source.catalog_workflow.xyz.orders')
                self.fixture.manifest.write_text(json.dumps(manifest))
                fresh=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                result=await self.invoke(client,'context_records_search',fresh,{'kind':'decisions'})
                self.assertEqual(result['status'],'denied')
        asyncio.run(exercise())

    def test_large_diff_and_impact_next_offsets_are_usable(self):
        # Existing manifest bounds allow >1024 resource edges; both pages must continue.
        manifest=json.loads(self.fixture.manifest.read_text())
        for i in range(1100):
            manifest['nodes'][f'model.catalog_workflow.m{i}']={'resource_type':'model','package_name':'catalog_workflow','name':f'm{i}','depends_on':{'nodes':['source.catalog_workflow.xyz.customers']}}
        self.fixture.manifest.write_text(json.dumps(manifest))
        async def exercise():
            async with self.client() as client:
                old=await self.key(client)
                for node in manifest['nodes'].values():
                    node['name']='changed_'+node['name']
                self.fixture.manifest.write_text(json.dumps(manifest))
                new=(await client.call_tool('modelling_refresh',{})).structured_content['context_id']
                for name,request,list_key in [('modelling_context_diff',{'before':old,'after':new},'changes'),('model_change_impact',{'asset_ids':[ASSET],'change':'Review change'},'resource_lineage')]:
                    result=await self.invoke(client,name,new,dict(request,offset=1020,limit=20))
                    self.assertEqual(result['next_offset'],1040)
                    next_page=await self.invoke(client,name,new,dict(request,offset=result['next_offset'],limit=20))
                    self.assertTrue(next_page[list_key])
                    if name=='model_change_impact':
                        self.assertTrue(next_page['resource_ids_truncated'])
                        self.assertEqual(next_page['resource_ids_total'],1101)
        asyncio.run(exercise())
