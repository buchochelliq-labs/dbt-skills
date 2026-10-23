import copy
import unittest
import yaml

import test_model_drafts
from dbt_skills.model_drafts import DraftError, apply_draft
from dbt_skills.model_validation import validate_applied


class ColumnNamingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.path = self.root / 'modelling.yml'
        self.policy = yaml.safe_load(self.path.read_text())
        self.policy['tokens'].update(attribute='What is the output attribute name?', prefix='Which prefix?')
        self.rule = {'id': 'attributes', 'target': 'column', 'template': '{prefix}_{attribute}', 'bindings': {'prefix': 'biz'}}
        self.request = copy.deepcopy(self.fixture.request)
        self.request['column_context'] = {'customer_id': {'values': {'attribute': 'id'}}, 'customer_name': {'values': {'attribute': 'name'}}}

    def draft(self, rules=None, request=None):
        doc = copy.deepcopy(self.policy)
        doc['naming'].extend(copy.deepcopy(rule) for rule in (rules if rules is not None else [self.rule]))
        self.path.write_text(yaml.safe_dump(doc))
        return self.fixture.draft(request if request is not None else self.request)

    def test_aliases_properties_and_grain_follow_declared_mapping(self):
        draft = self.draft()
        self.assertEqual(draft['status'], 'pending_review')
        self.assertIn("adapter.quote('customer_id') }} as {{ adapter.quote('biz_id')", draft['files'][0]['content'])
        props = yaml.safe_load(draft['files'][1]['content'])['models'][0]['columns']
        self.assertEqual(props, [{'name': 'biz_id', 'quote': True, 'data_tests': ['not_null', 'unique']}, {'name': 'biz_name', 'quote': True}])
        self.assertEqual(draft['design']['grain'], ['customer_id'])
        self.assertEqual(draft['design']['output_grain'], ['biz_id'])
        self.assertEqual(draft['design']['column_mapping'][0]['rule_id'], 'attributes')
        self.assertIn('locator', draft['design']['column_mapping'][0]['provenance'])
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')

    def test_missing_tokens_are_questions_for_the_specific_column(self):
        del self.request['column_context']['customer_name']
        result = self.draft()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertEqual(result['column'], 'customer_name')
        self.assertEqual(result['naming']['questions'][0]['token'], 'attribute')

    def test_collision_and_unsafe_names_never_generate_sql(self):
        for name in ['id', 'ID', "x'); select bad", 'path/name']:
            request = copy.deepcopy(self.request)
            request['column_context']['customer_name']['values']['attribute'] = name
            try:
                result = self.draft(request=request)
                self.assertEqual(result['status'], 'needs_clarification')
                self.assertNotIn('files', result)
            except ValueError:
                # Literal segment validation may reject unsafe token values earlier.
                self.assertIn(name, ["x'); select bad", 'path/name'])

    def test_per_column_scope_selects_rules_without_hiding_model_scope(self):
        rules = [dict(self.rule, scope={'role': 'key'}), {'id': 'labels', 'target': 'column', 'template': 'label_{attribute}', 'scope': {'role': 'label'}}]
        self.request['column_context']['customer_id']['scope'] = {'role': 'key'}
        self.request['column_context']['customer_name']['scope'] = {'role': 'label'}
        self.assertEqual(self.draft(rules)['status'], 'pending_review')
        self.request['scope'] = {'layer': 'staging'}
        self.request['column_context']['customer_id']['scope']['layer'] = 'mart'
        self.assertEqual(self.draft(rules)['status'], 'needs_clarification')

    def test_unknown_scope_overlap_and_global_value_conflicts_clarify(self):
        for rules in [[dict(self.rule, scope={'role': 'key'})], [self.rule, dict(self.rule, id='also')]]:
            self.assertEqual(self.draft(rules)['status'], 'needs_clarification')
        self.request['values']['attribute'] = 'global'
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_unknown_column_context_keys_fail(self):
        self.request['column_context']['absent'] = {'values': {'attribute': 'x'}}
        with self.assertRaises(DraftError):
            self.draft()

    def test_inapplicable_rules_preserve_original_names(self):
        request = copy.deepcopy(self.fixture.request)
        request['scope'] = {'layer': 'staging'}
        draft = self.draft([dict(self.rule, scope={'layer': 'mart'})], request)
        self.assertEqual(draft['status'], 'pending_review')
        self.assertNotIn(' as ', draft['files'][0]['content'])
        self.assertEqual(draft['design']['output_grain'], ['customer_id'])

    def test_request_cannot_supply_incorrect_directory_scope(self):
        self.request['column_context']['customer_id']['scope'] = {'directory': 'models/other'}
        self.assertEqual(self.draft()['status'], 'needs_clarification')

    def test_mapping_metadata_cannot_be_resealed_inconsistently(self):
        from dbt_skills.model_drafts import _digest
        draft = self.draft()
        draft['design']['column_mapping'][0]['output'] = 'other'
        draft['draft_id'] = _digest({k: v for k, v in draft.items() if k != 'draft_id'})
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'failed')

    def test_mcp_alias_draft_apply_validate(self):
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
                self.assertEqual(draft['status'], 'pending_review')
                self.assertEqual(draft['design']['output_grain'], ['biz_id'])
                apply_draft(self.fixture.project, draft, draft['draft_id'])
                report = (await client.call_tool('model_validate', {'context_id': context, 'draft_id': draft['draft_id']})).structured_content
                self.assertEqual(report['status'], 'passed')
        asyncio.run(exercise())

    def test_real_dbt_parses_aliased_columns_and_tests(self):
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
        report = run_parse(self.fixture.project, draft, draft['draft_id'], executable=executable, profiles_dir=profiles)
        self.assertEqual(report['status'], 'passed')
        self.assertFalse(report['warehouse_validated'])

    def test_composite_grain_preserves_source_assertion_and_output_order(self):
        self.request['grain'] = ['customer_name', 'customer_id']
        draft = self.draft()
        self.assertEqual(draft['design']['output_grain'], ['biz_name', 'biz_id'])
        self.assertEqual(draft['design']['grain'], self.request['grain'])
        columns = yaml.safe_load(draft['files'][1]['content'])['models'][0]['columns']
        self.assertEqual([c['data_tests'] for c in columns], [['not_null'], ['not_null']])

    def test_fixed_binding_conflict_and_unused_values_clarify(self):
        self.request['column_context']['customer_id']['values']['prefix'] = 'other'
        self.assertEqual(self.draft()['status'], 'needs_clarification')
        self.assertEqual(self.draft([])['status'], 'needs_clarification')

    def test_pre_mapping_draft_shape_still_validates(self):
        from dbt_skills.model_drafts import _digest
        draft = self.fixture.draft()
        draft['design'].pop('column_mapping')
        draft['design'].pop('output_grain')
        draft['design'].pop('warehouse_alias')
        draft['draft_id'] = _digest({k: v for k, v in draft.items() if k != 'draft_id'})
        apply_draft(self.fixture.project, draft, draft['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, draft)['status'], 'passed')

    def test_malformed_column_context_is_rejected(self):
        for value in [[], {'customer_id': 'bad'}, {'customer_id': {'extra': 'bad'}}, {'customer_id': {'values': {'attribute': 42}}}]:
            request = copy.deepcopy(self.request)
            request['column_context'] = value
            with self.assertRaises(DraftError):
                self.draft(request=request)
