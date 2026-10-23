import copy
import json
import unittest
import yaml

import test_model_drafts
from dbt_skills.model_drafts import apply_draft, _digest
from dbt_skills.model_validation import validate_applied


class WarehouseAliasTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.path = self.root / 'modelling.yml'
        self.policy = yaml.safe_load(self.path.read_text())
        self.policy['tokens']['relation'] = 'Which warehouse relation name?'
        self.request = copy.deepcopy(self.fixture.request)
        self.request['values']['relation'] = 'customer_stage'
        self.rule = {'id': 'relation_name', 'target': 'warehouse_alias', 'template': '{relation}'}

    def draft(self, rules=None):
        policy = copy.deepcopy(self.policy)
        policy['naming'].extend(copy.deepcopy(r) for r in (rules if rules is not None else [self.rule]))
        self.path.write_text(yaml.safe_dump(policy))
        return self.fixture.draft(self.request)

    def test_alias_config_preserves_model_and_properties_identity(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertTrue(draft['files'][0]['content'].startswith("{{ config(alias='customer_stage') }}\n\nselect"))
        self.assertEqual(draft['files'][0]['path'], 'models/staging/stg_xyz_customer.sql')
        props = yaml.safe_load(draft['files'][1]['content'])
        self.assertEqual(props['models'][0]['name'], 'stg_xyz_customer')
        self.assertEqual(draft['design']['warehouse_alias']['value'], 'customer_stage')
        self.assertIn('locator', draft['design']['warehouse_alias']['provenance'])
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')

    def test_missing_tokens_scope_and_overlaps_clarify(self):
        del self.request['values']['relation']
        result = self.draft()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertEqual(result['naming']['questions'][0]['token'], 'relation')
        self.request['values']['relation'] = 'customer_stage'
        for rules in [[dict(self.rule, scope={'layer': 'staging'})], [self.rule, dict(self.rule, id='other')]]:
            self.assertEqual(self.draft(rules)['status'], 'needs_clarification')

    def test_unrelated_alias_rule_does_not_change_sql(self):
        self.request['scope'] = {'layer': 'staging'}
        draft = self.draft([dict(self.rule, scope={'layer': 'mart'})])
        self.assertEqual(draft['status'], 'pending_review')
        self.assertTrue(draft['files'][0]['content'].startswith('select'))
        self.assertIsNone(draft['design']['warehouse_alias'])

    def test_known_alias_and_model_name_collisions_clarify(self):
        doc = json.loads(self.fixture.manifest.read_text())
        for alias, name in [('CUSTOMER_STAGE', 'other'), (None, 'customer_stage')]:
            doc['nodes']['model.other.existing'] = {'resource_type': 'model', 'package_name': 'other', 'name': name, 'alias': alias}
            self.fixture.manifest.write_text(json.dumps(doc))
            result = self.draft()
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertIn('collision', result['questions'][0].lower())
            self.assertNotIn('files', result)

    def test_unsafe_alias_never_reaches_sql(self):
        for alias in ["x'); run_query('bad", 'space name', '123bad', 'x' * 129]:
            self.request['values']['relation'] = alias
            result = self.draft()
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertNotIn('files', result)

    def test_resealed_alias_metadata_disagreement_fails_validation(self):
        draft = self.draft()
        draft['design']['warehouse_alias']['value'] = 'changed'
        draft['draft_id'] = _digest({k:v for k,v in draft.items() if k != 'draft_id'})
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_unparsed_model_name_collision_is_not_ignored(self):
        path = self.root / 'models/other/customer_stage.sql'
        path.parent.mkdir(parents=True)
        path.write_text('select 1')
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_alias_can_equal_its_own_model_name_after_apply(self):
        self.request['values']['relation'] = 'stg_xyz_customer'
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')

    def test_real_dbt_parses_literal_alias(self):
        import os
        from dbt_skills.model_validation import run_parse
        executable = os.environ.get('DBT_SKILLS_REAL_DBT')
        if not executable:
            self.skipTest('optional isolated dbt executable required')
        draft = self.draft()
        (self.root / 'models').mkdir()
        (self.root / 'models/sources.yml').write_text('version: 2\nsources:\n  - name: xyz\n    database: demo\n    schema: xyz\n    tables:\n      - name: customers\n')
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        profiles = self.root / 'profiles'
        profiles.mkdir()
        (profiles / 'profiles.yml').write_text("catalog_workflow:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
        self.assertEqual(run_parse(self.fixture.project, draft, draft['draft_id'], executable=executable, profiles_dir=profiles)['status'], 'passed')

    def test_mcp_alias_draft_and_validation(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, StdioServerParameters
        self.draft()
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')))
            async with Client(params, read_timeout_seconds=20) as client:
                context = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                draft = (await client.call_tool('model_draft', {'context_id': context, 'request': self.request})).structured_content
                self.assertEqual(draft['design']['warehouse_alias']['value'], 'customer_stage')
                apply_draft(self.fixture.project, draft, draft['draft_id'])
                result = (await client.call_tool('model_validate', {'context_id': context, 'draft_id': draft['draft_id']})).structured_content
                self.assertEqual(result['status'], 'passed')
        asyncio.run(exercise())

    def test_warehouse_and_column_aliases_combine_without_identity_changes(self):
        self.policy['tokens']['attribute'] = 'Which output attribute?'
        self.request['column_context'] = {'customer_id': {'values': {'attribute': 'customer_key'}}, 'customer_name': {'values': {'attribute': 'customer_label'}}}
        draft = self.draft([self.rule, {'id': 'column_name', 'target': 'column', 'template': '{attribute}'}])
        self.assertEqual(draft['status'], 'pending_review')
        self.assertIn("config(alias='customer_stage')", draft['files'][0]['content'])
        self.assertIn("adapter.quote('customer_key')", draft['files'][0]['content'])
        self.assertEqual(draft['design']['output_grain'], ['customer_key'])
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')
