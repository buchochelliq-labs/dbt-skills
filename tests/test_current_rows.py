import copy
import json
import unittest

import test_model_drafts
from dbt_skills.catalog import load_catalog
from dbt_skills.model_drafts import apply_draft, _digest
from dbt_skills.model_validation import validate_applied


class CurrentRowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['columns'] += [
            {'name': 'event_id', 'type': 'int64', 'nullable': False}]
        path.write_text(json.dumps(doc))
        self.fixture.catalog = load_catalog(self.root / 'catalogs.json')
        self.request = copy.deepcopy(self.fixture.request)
        self.request.update(history='current', current_row={
            'order_by': [{'column': 'updated_at', 'direction': 'desc', 'nulls': 'last'},
                         {'column': 'event_id', 'direction': 'desc', 'nulls': 'last'}],
            'ties': 'assert_unique', 'deletions': 'retain_latest',
            'rationale': 'Latest event per customer; event ID uniquely breaks timestamp ties. Keep deletion markers.'})

    def draft(self):
        return self.fixture.draft(self.request)

    def test_current_row_draft_preserves_assertions_and_validates(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertEqual(draft['design']['history'], 'current')
        self.assertEqual(draft['design']['current_row']['rule'], self.request['current_row'])
        self.assertFalse(draft['design']['current_row']['verified'])
        sql = draft['files'][0]['content']
        self.assertIn('row_number() over', sql)
        self.assertIn("adapter.quote('updated_at')", sql)
        self.assertIn('desc nulls last', sql)
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')
        draft['request']['current_row']['order_by'][0]['direction'] = 'asc'
        draft['draft_id'] = _digest({k: v for k, v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_missing_unsafe_and_unknown_rules_clarify(self):
        original = copy.deepcopy(self.request)
        changes = [None, {}, {**original['current_row'], 'ties': 'pick_any'},
                   {**original['current_row'], 'deletions': 'ignore'},
                   {**original['current_row'], 'rationale': ''},
                   {**original['current_row'], 'order_by': [{'column': 'unknown', 'direction': 'desc', 'nulls': 'last'}]},
                   {**original['current_row'], 'order_by': [{'column': 'updated_at', 'direction': 'desc;drop', 'nulls': 'last'}]}]
        for rule in changes:
            self.request = copy.deepcopy(original)
            if rule is None:
                self.request.pop('current_row')
            else:
                self.request['current_row'] = rule
            result = self.draft()
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertNotIn('files', result)
        self.request = original
        self.request['history'] = 'source_rows'
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_synthetic_sql_selects_latest_with_ties_and_null_ordering(self):
        import sqlite3
        import re
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        sql = re.sub(r"\{\{ adapter.quote\('([A-Za-z_][A-Za-z0-9_]*)'\) \}\}", lambda m: '"' + m[1] + '"', draft['files'][0]['content'])
        sql = sql.replace("{{ source('xyz', 'customers') }}", 'synthetic')
        with sqlite3.connect(':memory:') as connection:
            connection.execute('create table synthetic(customer_id integer, customer_name text, updated_at integer, event_id integer)')
            connection.executemany('insert into synthetic values (?,?,?,?)', [(1,'old',1,1),(1,'new',2,2),(1,'winner',2,3),(1,'null',None,4),(2,'only',None,5)])
            cursor = connection.execute(sql)
            self.assertEqual([c[0] for c in cursor.description], ['customer_id','customer_name'])
            self.assertEqual(sorted(cursor.fetchall()), [(1,'winner'),(2,'only')])

    def test_duplicate_sort_columns_and_unexpected_fields_clarify(self):
        rule = self.request['current_row']
        rule['order_by'].append(copy.deepcopy(rule['order_by'][0]))
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        rule['order_by'].pop()
        rule['sql'] = 'PRIVATE_SENTINEL'
        result = self.draft()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_helper_name_and_output_aliases_do_not_collide(self):
        from dbt_skills.model_drafts import render_projection
        mapping = [{'source': 'customer_id', 'output': '_dbt_skills_row_number'},
                   {'source': 'customer_name', 'output': 'display_name'}]
        sql, properties = render_projection(self.request, {'source_name': 'xyz', 'name': 'customers'}, 'customer', mapping, {'value': 'customer_current'})
        self.assertIn("as {{ adapter.quote('__dbt_skills_row_number') }}", sql)
        self.assertIn("where {{ adapter.quote('__dbt_skills_row_number') }} = 1", sql)
        self.assertIn("config(alias='customer_current')", sql)
        self.assertIn('display_name', properties)
        self.assertNotIn('updated_at', properties)

    def test_current_row_design_tampering_fails_validation(self):
        draft = self.draft()
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        draft['design']['current_row']['verified'] = True
        draft['draft_id'] = _digest({k: v for k, v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_stdio_current_model_apply_and_validate(self):
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
                apply_draft(self.fixture.project, draft, draft['draft_id'])
                result = (await client.call_tool('model_validate', {'context_id': key, 'draft_id': draft['draft_id']})).structured_content
                self.assertEqual(result['status'], 'passed')
                self.assertFalse(result['warehouse_validated'])
        asyncio.run(exercise())

    def test_real_dbt_parse_current_model(self):
        import os
        from dbt_skills.model_validation import run_parse
        executable = os.environ.get('DBT_SKILLS_REAL_DBT')
        if not executable:
            self.skipTest('optional isolated dbt executable required')
        (self.root / 'models').mkdir()
        (self.root / 'models/sources.yml').write_text('version: 2\nsources:\n  - name: xyz\n    database: demo\n    schema: xyz\n    tables:\n      - name: customers\n')
        draft = self.draft()
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        profiles = self.root / 'profiles'
        profiles.mkdir()
        (profiles / 'profiles.yml').write_text("catalog_workflow:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
        self.assertEqual(run_parse(self.fixture.project, draft, draft['draft_id'], executable=executable, profiles_dir=profiles)['status'], 'passed')

    def test_source_projection_rejects_injected_current_row_design(self):
        self.request = copy.deepcopy(self.fixture.request)
        draft = self.draft()
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        draft['design']['current_row'] = {'verified': True}
        draft['draft_id'] = _digest({k: v for k, v in draft.items() if k != 'draft_id'})
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')
