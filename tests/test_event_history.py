import copy
import json
import re
import sqlite3
import unittest
import yaml

import test_model_drafts
from dbt_skills.catalog import load_catalog
from dbt_skills.model_drafts import apply_draft, _digest
from dbt_skills.model_validation import validate_applied


class EventHistoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.request = self.fixture.request
        self.request.update(history='historical', history_rule={
            'effective_at':'updated_at', 'events':'assert_complete', 'ordering':'assert_unique_non_null',
            'deletions':'retain_events', 'materialization':'table',
            'rationale':'Source retains every customer event; effective time uniquely identifies each version.'})

    def draft(self):
        return self.fixture.draft(self.request)

    def test_history_draft_has_event_grain_and_no_entity_unique_test(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertEqual(draft['design']['output_grain'], ['customer_id','valid_from'])
        self.assertFalse(draft['design']['event_history']['verified'])
        columns = yaml.safe_load(draft['files'][1]['content'])['models'][0]['columns']
        self.assertEqual(next(c for c in columns if c['name']=='customer_id')['data_tests'], ['not_null'])
        self.assertEqual(next(c for c in columns if c['name']=='valid_from')['data_tests'], ['not_null'])
        self.assertIn("config(materialized='table')", draft['files'][0]['content'])
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')
        draft['design']['event_history']['verified'] = True
        draft['draft_id'] = _digest({k:v for k,v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_synthetic_out_of_order_events_make_half_open_intervals(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        sql = re.sub(r"\{\{ adapter.quote\('([A-Za-z_][A-Za-z0-9_]*)'\) \}\}", lambda m:'"'+m[1]+'"',draft['files'][0]['content'])
        sql = sql.replace("{{ source('xyz', 'customers') }}",'events').replace("{{ config(materialized='table') }}",'')
        with sqlite3.connect(':memory:') as conn:
            conn.execute('create table events(customer_id integer,customer_name text,updated_at integer)')
            conn.executemany('insert into events values (?,?,?)',[(1,'last',30),(1,'first',10),(2,'only',5),(1,'middle',20)])
            self.assertCountEqual(conn.execute(sql).fetchall(),[(1,'first',10,20),(1,'middle',20,30),(1,'last',30,None),(2,'only',5,None)])

    def test_missing_invalid_and_misplaced_rules_clarify(self):
        original = copy.deepcopy(self.request)
        for change in [{'effective_at':'customer_name'},{'effective_at':'missing'},{'effective_at':'customer_id'},
                       {'events':'current_only'},{'ordering':'pick_any'},{'deletions':'drop'},{'materialization':'incremental'},{'rationale':''}]:
            self.request['history_rule'] = {**original['history_rule'],**change}
            self.assertEqual(self.draft()['status'],'needs_clarification')
        self.request.clear(); self.request.update(original)
        del self.request['history_rule']
        self.assertEqual(self.draft()['status'],'needs_clarification')
        self.request['history_rule'] = original['history_rule']
        self.request['history'] = 'source_rows'
        self.assertEqual(self.draft()['status'],'needs_clarification')

    def test_generated_columns_follow_policy_and_collisions_clarify(self):
        path = self.root / 'modelling.yml'
        policy = yaml.safe_load(path.read_text())
        policy['tokens']['field'] = 'Output field name'
        policy['naming'].append({'id':'field','target':'column','template':'{field}'})
        path.write_text(yaml.safe_dump(policy))
        self.request['column_context'] = {'customer_id':{'values':{'field':'customer_key'}},'customer_name':{'values':{'field':'customer_label'}}}
        self.request['history_rule']['column_context'] = {'valid_from':{'values':{'field':'effective_from'}},'valid_to':{'values':{'field':'effective_to'}}}
        draft = self.draft()
        self.assertEqual(draft['status'],'pending_review')
        self.assertEqual(draft['design']['output_grain'],['customer_key','effective_from'])
        self.request['history_rule']['column_context']['valid_to']['values']['field'] = 'customer_key'
        self.assertEqual(self.draft()['status'],'needs_clarification')

    def test_incompatible_modes_and_unknown_rule_fields_clarify(self):
        self.request['current_row'] = {}
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        del self.request['current_row']
        self.request['lookup'] = {}
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        del self.request['lookup']
        self.request['history_rule']['sql'] = 'PRIVATE_SENTINEL'
        result = self.draft()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_changed_effective_time_contract_fails_applied_validation(self):
        draft = self.draft()
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        draft['request']['history_rule']['effective_at'] = 'customer_name'
        draft['draft_id'] = _digest({k:v for k,v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_stdio_history_apply_validate(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, StdioServerParameters
        self.request['history_rule']['materialization'] = 'view'
        async def exercise():
            params = StdioServerParameters(command=sys.executable,args=['-m','dbt_skills.modelling_mcp','--project-dir',str(self.root),'--policy','modelling.yml','--catalog-config','catalogs.json'],env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src')))
            async with Client(params,read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context',{})).structured_content['context_id']
                draft = (await client.call_tool('model_draft',{'context_id':key,'request':self.request})).structured_content
                self.assertEqual(draft['status'],'pending_review')
                self.assertIn("config(materialized='view')",draft['files'][0]['content'])
                apply_draft(self.fixture.project,draft,draft['draft_id'])
                result = (await client.call_tool('model_validate',{'context_id':key,'draft_id':draft['draft_id']})).structured_content
                self.assertEqual(result['status'],'passed')
        asyncio.run(exercise())

    def test_real_dbt_parse_history_with_alias(self):
        import os
        from dbt_skills.model_validation import run_parse
        executable = os.environ.get('DBT_SKILLS_REAL_DBT')
        if not executable:
            self.skipTest('optional isolated dbt executable required')
        policy_path = self.root / 'modelling.yml'
        policy = yaml.safe_load(policy_path.read_text())
        policy['naming'].append({'id':'alias','target':'warehouse_alias','template':'customer_history'})
        policy_path.write_text(yaml.safe_dump(policy))
        (self.root/'models').mkdir()
        (self.root/'models/sources.yml').write_text('version: 2\nsources:\n  - name: xyz\n    database: demo\n    schema: xyz\n    tables:\n      - name: customers\n')
        draft = self.draft()
        self.assertIn("config(alias='customer_history')",draft['files'][0]['content'])
        apply_draft(self.fixture.project,draft,draft['draft_id'])
        profiles=self.root/'profiles'; profiles.mkdir()
        (profiles/'profiles.yml').write_text("catalog_workflow:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
        self.assertEqual(run_parse(self.fixture.project,draft,draft['draft_id'],executable=executable,profiles_dir=profiles)['status'],'passed')

    def test_historical_output_grain_cannot_skip_mapping_validation(self):
        draft = self.draft()
        apply_draft(self.fixture.project,draft,draft['draft_id'])
        del draft['design']['column_mapping']
        draft['design']['output_grain'] = ['customer_id']
        draft['draft_id'] = _digest({k:v for k,v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project,draft)['status'],'failed')
