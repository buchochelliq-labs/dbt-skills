import copy
import json
import re
import sqlite3
import unittest

import test_current_rows
from dbt_skills.catalog import load_catalog
from dbt_skills.model_drafts import apply_draft, _digest
from dbt_skills.model_validation import validate_applied


class CurrentRowDeletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_current_rows.CurrentRowTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.request = self.fixture.request
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['columns'].append({'name': 'is_deleted', 'type': 'boolean', 'nullable': True})
        path.write_text(json.dumps(doc))
        self.fixture.fixture.catalog = load_catalog(self.root / 'catalogs.json')
        self.request['current_row']['deletions'] = {'mode': 'exclude_marked', 'column': 'is_deleted', 'nulls': 'retain'}

    def draft(self):
        return self.fixture.draft()

    def test_filter_after_ranking_never_resurrects_deleted_entity(self):
        for nulls, expected in [('retain', [(2,'active'), (3,'unknown')]), ('exclude', [(2,'active')])]:
            self.request['current_row']['deletions']['nulls'] = nulls
            draft = self.draft()
            self.assertEqual(draft['status'], 'pending_review')
            sql = re.sub(r"\{\{ adapter.quote\('([A-Za-z_][A-Za-z0-9_]*)'\) \}\}", lambda m: '"' + m[1] + '"', draft['files'][0]['content'])
            sql = sql.replace("{{ source('xyz', 'customers') }}", 'synthetic')
            with sqlite3.connect(':memory:') as connection:
                connection.execute('create table synthetic(customer_id integer, customer_name text, updated_at integer, event_id integer, is_deleted boolean)')
                connection.executemany('insert into synthetic values (?,?,?,?,?)', [(1,'old',1,1,False), (1,'deleted',2,2,True), (2,'deleted',1,3,True), (2,'active',2,4,False), (3,'unknown',2,5,None)])
                cursor = connection.execute(sql)
                self.assertEqual([c[0] for c in cursor.description], ['customer_id', 'customer_name'])
                self.assertEqual(sorted(cursor.fetchall()), expected)
            self.assertNotIn('is_deleted', draft['files'][1]['content'])
            self.assertEqual(draft['design']['current_row']['rule']['deletions'], self.request['current_row']['deletions'])

    def test_unknown_unsafe_missing_null_and_nonboolean_marker_clarify(self):
        original = copy.deepcopy(self.request['current_row']['deletions'])
        for deletion in [{'mode':'exclude_marked','column':'is_deleted'}, {**original,'nulls':'guess'},
                         {**original,'column':'unknown'}, {**original,'column':'is_deleted;drop'},
                         {**original,'column':'customer_name'}, {**original,'predicate':'PRIVATE_SENTINEL'}]:
            self.request['current_row']['deletions'] = deletion
            result = self.draft()
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertNotIn('files', result)
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_apply_validation_recomputes_deletion_rule(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        project = self.fixture.fixture.project
        apply_draft(project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(project, draft)['status'], 'passed')
        draft['request']['current_row']['deletions']['nulls'] = 'exclude'
        draft['draft_id'] = _digest({k:v for k,v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(project, draft)['status'], 'failed')

    def test_marker_colliding_with_helper_is_renamed_internally(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['columns'][-1]['name'] = '_dbt_skills_row_number'
        path.write_text(json.dumps(doc))
        self.fixture.fixture.catalog = load_catalog(self.root / 'catalogs.json')
        self.request['current_row']['deletions']['column'] = '_dbt_skills_row_number'
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertIn("as {{ adapter.quote('__dbt_skills_row_number') }}", draft['files'][0]['content'])
        self.assertIn("adapter.quote('_dbt_skills_row_number') }} = false", draft['files'][0]['content'])

    def test_projected_marker_is_not_duplicated(self):
        self.request['columns'].append('is_deleted')
        result = self.draft()
        self.assertEqual(result['status'], 'pending_review')
        inner = result['files'][0]['content'].split('from ranked_source')[0].split(')\nselect')[0]
        self.assertEqual(inner.count("adapter.quote('is_deleted')"), 1)
        self.assertIn('is_deleted', result['files'][1]['content'])

    def test_stdio_deletion_rule_remains_unverified(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, StdioServerParameters
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')))
            async with Client(params, read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                draft = (await client.call_tool('model_draft', {'context_id': key, 'request': self.request})).structured_content
                self.assertEqual(draft['status'], 'pending_review')
                self.assertFalse(draft['design']['current_row']['verified'])
                self.assertEqual(draft['design']['current_row']['rule']['deletions']['nulls'], 'retain')
        asyncio.run(exercise())

    def test_real_dbt_parse_filtered_current_model(self):
        import os
        from dbt_skills.model_validation import run_parse
        executable = os.environ.get('DBT_SKILLS_REAL_DBT')
        if not executable:
            self.skipTest('optional isolated dbt executable required')
        (self.root / 'models').mkdir()
        (self.root / 'models/sources.yml').write_text('version: 2\nsources:\n  - name: xyz\n    database: demo\n    schema: xyz\n    tables:\n      - name: customers\n')
        draft = self.draft()
        project = self.fixture.fixture.project
        apply_draft(project, draft, draft['draft_id'])
        profiles = self.root / 'profiles'
        profiles.mkdir()
        (profiles / 'profiles.yml').write_text("catalog_workflow:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
        self.assertEqual(run_parse(project, draft, draft['draft_id'], executable=executable, profiles_dir=profiles)['status'], 'passed')

    def test_hidden_marker_case_collision_clarifies(self):
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['columns'].append({'name': 'IS_DELETED', 'type': 'string', 'nullable': True})
        path.write_text(json.dumps(doc))
        self.fixture.fixture.catalog = load_catalog(self.root / 'catalogs.json')
        self.request['columns'].append('IS_DELETED')
        self.assertEqual(self.draft()['status'], 'needs_clarification')
