import copy
import unittest
import yaml

import test_model_drafts
from dbt_skills.model_drafts import apply_draft
from dbt_skills.model_validation import validate_applied


class DraftNamingTargetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_drafts.ModelDraftTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.root / 'modelling.yml'
        self.policy = yaml.safe_load(self.path.read_text())

    def draft(self, rules, request=None):
        doc = copy.deepcopy(self.policy)
        doc['naming'].extend(rules)
        self.path.write_text(yaml.safe_dump(doc))
        return self.fixture.draft(request)

    def test_matching_model_id_and_directory_apply_and_validate(self):
        result = self.draft([
            {'id': 'identifier', 'target': 'model_id', 'template': 'stg_{system}_{concept}'},
            {'id': 'folder', 'target': 'directory', 'template': 'models/staging'}])
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['files'][0]['path'], 'models/staging/stg_xyz_customer.sql')
        apply_draft(self.fixture.project, result, result['draft_id'])
        self.assertEqual(validate_applied(self.fixture.project, result)['status'], 'passed')

    def test_mismatched_constraints_clarify_without_renaming(self):
        for target, template in [('model_id', '{concept}'), ('directory', 'models/core')]:
            result = self.draft([{'id': 'constraint', 'target': target, 'template': template}])
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertIn('naming_constraint', result)
            self.assertEqual(result['naming_constraint']['target'], target)
            self.assertNotIn('files', result)

    def test_missing_token_returns_its_team_defined_question(self):
        self.policy['tokens']['business_area'] = 'Which business area owns this model?'
        result = self.draft([{'id': 'identifier', 'target': 'model_id', 'template': '{business_area}_{concept}'}])
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertEqual(result['naming']['questions'][0]['token'], 'business_area')

    def test_unrelated_rules_do_not_block_but_unknown_scope_does(self):
        rules = [{'id': 'alias_elsewhere', 'target': 'warehouse_alias', 'template': '{concept}', 'scope': {'layer': 'mart'}}]
        request = copy.deepcopy(self.fixture.request)
        request['scope'] = {'layer': 'staging'}
        self.assertEqual(self.draft(rules, request)['status'], 'pending_review')
        result = self.draft(rules)
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertIn('scope', result['questions'][0].lower())

    def test_overlapping_constraints_are_not_silently_preferred(self):
        result = self.draft([
            {'id': 'identifier', 'target': 'model_id', 'template': 'stg_{system}_{concept}'},
            {'id': 'identifier_also', 'target': 'model_id', 'template': 'stg_{system}_{concept}'}])
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertIn('overlap', result['questions'][0].lower())

    def test_applicable_unsupported_targets_still_block(self):
        for target in ('warehouse_alias',):
            result = self.draft([{'id': 'unsupported', 'target': target, 'template': '{concept}'}])
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertNotIn('files', result)

    def test_directory_rule_uses_model_parent_not_properties_parent(self):
        for rule in self.policy['naming']:
            if rule['target'] == 'properties_file':
                rule['template'] = 'models/properties/{concept}.yml'
        result = self.draft([{'id': 'folder', 'target': 'directory', 'template': 'models/staging', 'scope': {'directory': 'models/staging'}}])
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['files'][1]['path'], 'models/properties/customer.yml')

    def test_literal_fixed_binding_and_custom_token_names_remain_supported(self):
        self.policy['tokens']['prefix'] = 'Which prefix?'
        self.policy['tokens']['object'] = 'Which object?'
        request = copy.deepcopy(self.fixture.request)
        request['values'].update(object='customer')
        result = self.draft([{'id': 'identifier', 'target': 'model_id', 'template': '{prefix}_{system}_{object}', 'bindings': {'prefix': 'stg'}}], request)
        self.assertEqual(result['status'], 'pending_review')

    def test_mcp_drafts_with_additional_constraints(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, StdioServerParameters
        self.draft([{'id': 'identifier', 'target': 'model_id', 'template': 'stg_{system}_{concept}'}])
        async def exercise():
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.fixture.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'], env=env)
            async with Client(params, read_timeout_seconds=20) as client:
                context = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                draft = (await client.call_tool('model_draft', {'context_id': context, 'request': self.fixture.request})).structured_content
                self.assertEqual(draft['status'], 'pending_review')
                apply_draft(self.fixture.project, draft, draft['draft_id'])
                report = (await client.call_tool('model_validate', {'context_id': context, 'draft_id': draft['draft_id']})).structured_content
                self.assertEqual(report['status'], 'passed')
        asyncio.run(exercise())
