import copy
import json
import re
import sqlite3
import unittest

import test_model_drafts
from dbt_skills.catalog import load_catalog
from dbt_skills.model_drafts import apply_draft, _digest
from dbt_skills.model_validation import validate_applied


class LookupJoinTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.request = self.fixture.request
        self.lookup_asset = 'urn:demo:xyz:details'
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'].append({'id': self.lookup_asset, 'native_id': 'details', 'facts': {
            'relation': {'catalog':'demo','schema':'xyz','name':'details'},
            'columns': [{'name':'customer_id','type':'int64','nullable':False}, {'name':'segment','type':'string','nullable':True}],
            'primary_key': {'columns':['customer_id'],'enforcement':'not_enforced','rely':False}}})
        path.write_text(json.dumps(doc))
        manifest = json.loads(self.fixture.manifest.read_text())
        manifest['sources']['source.catalog_workflow.xyz.details'] = {
            'resource_type':'source','package_name':'catalog_workflow','name':'details','source_name':'xyz','identifier':'details','database':'demo','schema':'xyz'}
        self.fixture.manifest.write_text(json.dumps(manifest))
        self.reload()
        self.request['lookup'] = {'asset_id':self.lookup_asset,'source_id':'source.catalog_workflow.xyz.details',
                                  'type':'left','on':[{'left':'customer_id','right':'customer_id'}], 'columns':['segment'],
                                  'cardinality':'many_to_one','nulls':'never_match','rationale':'One reviewed segment record per customer key.'}

    def reload(self):
        self.fixture.catalog = load_catalog(self.root / 'catalogs.json')

    def draft(self):
        return self.fixture.draft(self.request)

    def test_draft_apply_and_recompute_join(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertFalse(draft['design']['lookup']['verified'])
        self.assertEqual(draft['design']['output_grain'], ['customer_id'])
        self.assertEqual(draft['lookup_catalog']['asset_id'], self.lookup_asset)
        self.assertIn('segment', draft['files'][1]['content'])
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')
        draft['request']['lookup']['type'] = 'inner'
        draft['draft_id'] = _digest({k:v for k,v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_synthetic_left_inner_and_null_keys(self):
        for kind, expected in [('left',[(None,'null',None),(1,'one','A'),(2,'two',None)]), ('inner',[(1,'one','A')])]:
            self.request['lookup']['type'] = kind
            draft = self.draft()
            self.assertEqual(draft['status'], 'pending_review')
            sql = re.sub(r"\{\{ adapter.quote\('([A-Za-z_][A-Za-z0-9_]*)'\) \}\}", lambda m: '"'+m[1]+'"', draft['files'][0]['content'])
            sql = sql.replace("{{ source('xyz', 'customers') }}", 'customers').replace("{{ source('xyz', 'details') }}", 'details')
            with sqlite3.connect(':memory:') as conn:
                conn.execute('create table customers(customer_id integer, customer_name text)')
                conn.execute('create table details(customer_id integer, segment text)')
                conn.executemany('insert into customers values (?,?)',[(1,'one'),(2,'two'),(None,'null')])
                conn.executemany('insert into details values (?,?)',[(1,'A'),(None,'never')])
                self.assertCountEqual(conn.execute(sql).fetchall(), expected)

    def test_invalid_assumptions_columns_and_output_collision_clarify(self):
        original = copy.deepcopy(self.request['lookup'])
        for change in [{'cardinality':'many_to_many'}, {'nulls':'match'}, {'rationale':''}, {'type':'left;drop'},
                       {'columns':['customer_id']}, {'columns':['missing']}, {'on':[{'left':'missing','right':'customer_id'}]}]:
            self.request['lookup'] = {**original, **change}
            result = self.draft()
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertNotIn('files', result)

    def test_missing_key_or_wrong_source_mapping_clarifies(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        del doc['assets'][1]['facts']['primary_key']
        path.write_text(json.dumps(doc)); self.reload()
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        self.request['lookup']['source_id'] = self.request['source_id']
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_lookup_denial_withholds_base_metadata(self):
        from dbt_skills.catalog import CatalogResolver, FileCatalogProvider, ProviderResult
        provider = FileCatalogProvider('physical', self.root / 'physical.json', 'demo')
        class Guard:
            id = 'physical'
            def fetch(inner, asset_id, fields):
                return ProviderResult('denied') if asset_id == self.lookup_asset else provider.fetch(asset_id, fields)
        self.fixture.catalog = CatalogResolver([Guard()])
        result = self.draft()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertNotIn('customer_name', json.dumps(result))
        self.assertNotIn('catalog', result)

    def test_declared_relationship_provenance_and_conflict(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        fk = {'columns':['customer_id'], 'target_asset':self.lookup_asset, 'target_columns':['customer_id'], 'enforcement':'not_enforced','rely':False}
        doc['assets'][0]['facts']['foreign_keys'] = [fk]
        path.write_text(json.dumps(doc)); self.reload()
        result = self.draft()
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['design']['lookup']['relationship_provenance']['provider'], 'physical')
        fk['target_asset'] = 'urn:other'
        path.write_text(json.dumps(doc)); self.reload()
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_lookup_only_provider_revision_is_pinned(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        lookup = doc['assets'].pop()
        doc['assets'][0]['facts']['primary_key'] = {'columns':['customer_id'],'enforcement':'not_enforced','rely':False}
        doc['assets'][0]['facts']['foreign_keys'] = []
        path.write_text(json.dumps(doc))
        lookup_path = self.root / 'lookup.json'
        lookup_path.write_text(json.dumps({**doc, 'assets':[lookup]}))
        config_path = self.root / 'catalogs.json'
        config = json.loads(config_path.read_text())
        config['providers'].append({'id':'lookup','type':'file','path':'lookup.json','scope':'demo'})
        config_path.write_text(json.dumps(config)); self.reload()
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertIn(str(lookup_path.resolve()), [p['path'] for p in draft['preconditions']])
        lookup_path.write_text(lookup_path.read_text() + '\n')
        from dbt_skills.model_drafts import DraftError
        with self.assertRaises(DraftError):
            apply_draft(self.fixture.project, draft, draft['draft_id'])

    def test_key_type_mismatch_and_temporal_join_clarify(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][1]['facts']['columns'][0]['type'] = 'string'
        path.write_text(json.dumps(doc)); self.reload()
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        self.request['history'] = 'current'
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_real_mcp_join_apply_validate(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, StdioServerParameters
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--policy','modelling.yml','--catalog-config','catalogs.json'], env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src')))
            async with Client(params, read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                draft = (await client.call_tool('model_draft', {'context_id':key,'request':self.request})).structured_content
                self.assertEqual(draft['status'], 'pending_review')
                apply_draft(self.fixture.project, draft, draft['draft_id'])
                result = (await client.call_tool('model_validate', {'context_id':key,'draft_id':draft['draft_id']})).structured_content
                self.assertEqual(result['status'], 'passed')
        asyncio.run(exercise())

    def test_real_dbt_parse_join(self):
        import os
        from dbt_skills.model_validation import run_parse
        executable = os.environ.get('DBT_SKILLS_REAL_DBT')
        if not executable:
            self.skipTest('optional isolated dbt executable required')
        (self.root / 'models').mkdir()
        (self.root / 'models/sources.yml').write_text('version: 2\nsources:\n  - name: xyz\n    database: demo\n    schema: xyz\n    tables:\n      - name: customers\n      - name: details\n')
        draft = self.draft()
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        profiles = self.root / 'profiles'; profiles.mkdir()
        (profiles / 'profiles.yml').write_text("catalog_workflow:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
        self.assertEqual(run_parse(self.fixture.project, draft, draft['draft_id'], executable=executable, profiles_dir=profiles)['status'], 'passed')

    def test_denied_lookup_with_bad_base_mapping_withholds_all_metadata(self):
        manifest = json.loads(self.fixture.manifest.read_text())
        manifest['sources'][self.request['source_id']]['identifier'] = 'different'
        self.fixture.manifest.write_text(json.dumps(manifest))
        self.test_lookup_denial_withholds_base_metadata()

    def test_distinct_ids_cannot_disguise_physical_self_join(self):
        self.request['columns'] = ['customer_id']
        self.request['lookup']['columns'] = ['customer_name']
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][1]['facts']['relation']['name'] = 'customers'
        doc['assets'][1]['facts']['columns'] = copy.deepcopy(doc['assets'][0]['facts']['columns'])
        path.write_text(json.dumps(doc)); self.reload()
        manifest = json.loads(self.fixture.manifest.read_text())
        manifest['sources'][self.request['lookup']['source_id']]['identifier'] = 'customers'
        self.fixture.manifest.write_text(json.dumps(manifest))
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_lookup_output_uses_declared_column_conventions(self):
        import yaml
        path = self.root / 'modelling.yml'
        policy = yaml.safe_load(path.read_text())
        policy['tokens']['field'] = 'Output field concept'
        policy['naming'].append({'id':'field_name','target':'column','template':'{field}'})
        path.write_text(yaml.safe_dump(policy))
        self.request['column_context'] = {'customer_id':{'values':{'field':'customer_key'}}, 'customer_name':{'values':{'field':'customer_label'}}}
        self.request['lookup']['column_context'] = {'segment':{'values':{'field':'customer_segment'}}}
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertIn("lookup_rows.{{ adapter.quote('segment') }} as {{ adapter.quote('customer_segment') }}", draft['files'][0]['content'])
        self.assertEqual(draft['design']['output_grain'], ['customer_key'])
        self.assertEqual(draft['design']['lookup']['column_mapping'][0]['rule_id'], 'field_name')
