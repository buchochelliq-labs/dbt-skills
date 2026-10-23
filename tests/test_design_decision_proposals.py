import copy
import json
import unittest

import test_design_decisions
from dbt_skills.catalog import load_catalog, CatalogResolver, ProviderResult
from dbt_skills.modelling_policy import load_document
from dbt_skills.design_decisions import load_design_decisions, DesignDecisionError
from dbt_skills.design_decision_proposals import prepare_design_decision


class DesignDecisionProposalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_design_decisions.DesignDecisionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.request = {'plan': copy.deepcopy(self.fixture.request), 'record': {
            'id': 'customer_design', 'rationale': 'Preserve each source customer row.',
            'recorded_by': 'project_owner', 'recorded_at': '2026-10-23T16:00:00Z'}}
        self.request['plan']['assets'][0].update(grain=['customer_id'], history='source_rows')

    def propose(self, decisions=None, catalog=None):
        return prepare_design_decision(self.fixture.project, load_document(self.root / 'modelling.yml'),
                                       catalog or load_catalog(self.root / 'catalogs.json'), self.request, decisions=decisions)

    def test_complete_document_roundtrip_no_writes_or_mutation(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        request = copy.deepcopy(self.request)
        result = self.propose()
        self.assertEqual(result['status'], 'pending_review')
        self.assertIsNone(result['decisions_base'])
        self.assertEqual(result['decisions_patch'][0]['path'], '')
        self.assertEqual(request, self.request)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        loaded = self.fixture.save(result['proposed_document']['records'])
        plan = self.fixture.plan(loaded)
        self.assertEqual(plan['entities'][0]['grain']['basis'], 'recorded_design_decision')
        self.assertIn('functional_dependencies', self.fixture.codes(result['planning']))

    def test_existing_match_requires_explicit_replacement(self):
        decisions = self.fixture.save([self.fixture.record()])
        result = self.propose(decisions)
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertIsNone(result['proposed_document'])
        self.request['replace_record_id'] = 'customer_design'
        self.request['plan']['assets'][0]['history'] = 'historical'
        result = self.propose(decisions)
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['decisions_base'], decisions['provenance'])
        self.assertEqual(result['decisions_patch'][0], {'op': 'test', 'path': '/records/0', 'value': decisions['document']['records'][0]})
        self.assertEqual(result['proposed_document']['records'][0]['history'], 'historical')
        self.assertEqual(decisions['document']['records'][0]['history'], 'source_rows')
        self.assertIn('history_rule', self.fixture.codes(result['planning']))

    def test_unrelated_replacement_and_id_collision_clarify(self):
        other = self.fixture.record()
        other['intent'] = 'Unrelated design'
        decisions = self.fixture.save([other])
        for replacement in [None, 'customer_design', 'missing']:
            if replacement:
                self.request['replace_record_id'] = replacement
            result = self.propose(decisions)
            self.assertEqual(result['status'], 'needs_clarification')
            self.assertIsNone(result['proposed_document'])

    def test_missing_columns_does_not_prepare_reusable_assertion(self):
        self.request['plan']['assets'][0]['grain'] = ['missing']
        result = self.propose()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertIsNone(result['proposed_document'])
        self.assertIn('grain_columns_missing', self.fixture.codes(result['planning']))

    def test_denied_provider_withholds_record(self):
        class Denied:
            id = 'denied'
            def fetch(self, asset_id, fields):
                return ProviderResult('denied')
        result = self.propose(catalog=CatalogResolver([Denied()]))
        self.assertEqual(result['status'], 'blocked')
        self.assertIsNone(result['proposed_document'])
        self.assertNotIn('project_owner', json.dumps(result))

    def test_missing_choices_or_invalid_attribution_fail_closed(self):
        original = copy.deepcopy(self.request)
        for field in ['grain', 'history']:
            self.request = copy.deepcopy(original)
            del self.request['plan']['assets'][0][field]
            with self.assertRaises(DesignDecisionError):
                self.propose()
        self.request = copy.deepcopy(original)
        self.request['record']['recorded_at'] = 'PRIVATE_SENTINEL'
        with self.assertRaises(DesignDecisionError) as caught:
            self.propose()
        self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))

    def test_cli_prepares_complete_document(self):
        import os
        from pathlib import Path
        import subprocess
        import sys
        (self.root / 'proposal.json').write_text(json.dumps(self.request))
        result = subprocess.run([sys.executable, '-m', 'dbt_skills.design_decision_proposals', '--project-dir', str(self.root), '--request', 'proposal.json', '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json'],
                                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout, 'CLI must return a reviewable proposal')
        result = json.loads(result.stdout)
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['proposed_document']['records'][0]['grain'], ['customer_id'])

    def test_stdio_proposes_then_rejects_changed_file(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        self.fixture.save([])
        async def exercise():
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json', '--design-decisions', self.fixture.path.name], env=env)
            async with Client(params, read_timeout_seconds=20) as client:
                tools = {t.name: t for t in (await client.list_tools()).tools}
                self.assertIn('model_propose_decision', tools)
                tool = tools['model_propose_decision']
                self.assertTrue(tool.annotations.read_only_hint)
                self.assertEqual(set(tool.input_schema['properties']), {'context_id', 'request'})
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                args = {'context_id': key, 'request': self.request}
                result = (await client.call_tool('model_propose_decision', args)).structured_content
                self.assertEqual(result['status'], 'pending_review')
                self.assertEqual(load_design_decisions(self.fixture.path)['document']['records'], [])
                self.fixture.save(result['proposed_document']['records'])
                with self.assertRaises(MCPError):
                    await client.call_tool('model_propose_decision', args)
                key = (await client.call_tool('modelling_refresh', {})).structured_content['context_id']
                args['context_id'] = key
                result = (await client.call_tool('model_propose_decision', args)).structured_content
                self.assertEqual(result['status'], 'needs_clarification')
                policy = self.root / 'modelling.yml'
                policy.write_text(policy.read_text() + '\n# changed after capture\n')
                with self.assertRaises(MCPError):
                    await client.call_tool('model_propose_decision', args)
        asyncio.run(exercise())

    def test_append_preserves_unrelated_record_and_duplicate_context_clarifies(self):
        record = self.fixture.record()
        unrelated = {**record, 'id': 'other', 'intent': 'Different intent'}
        decisions = self.fixture.save([unrelated])
        result = self.propose(decisions)
        self.assertEqual(result['proposed_document']['records'][0], unrelated)
        self.assertEqual(len(result['proposed_document']['records']), 2)
        self.request['replace_record_id'] = record['id']
        decisions = self.fixture.save([record, {**record, 'id': 'duplicate'}])
        self.assertEqual(self.propose(decisions)['status'], 'needs_clarification')

    def test_record_capacity_fails_explicitly(self):
        record = self.fixture.record()
        records = [{**record, 'id': f'other{i}', 'intent': f'Other intent {i}'} for i in range(128)]
        with self.assertRaises(DesignDecisionError):
            self.propose(self.fixture.save(records))

    def test_combined_output_limit_rejects_large_valid_inputs(self):
        import yaml
        record = self.fixture.record()
        records = [{**record, 'id': f'other{i}', 'intent': f'Other intent {i}', 'rationale': 'x' * 4096} for i in range(127)]
        decisions = self.fixture.save(records)
        path = self.root / 'modelling.yml'
        policy = yaml.safe_load(path.read_text())
        policy['modelling'][0]['principles'] = ['p' * 4096] * 120
        path.write_text(yaml.safe_dump(policy))
        with self.assertRaisesRegex(DesignDecisionError, 'response limits'):
            self.propose(decisions)

    def test_conflicting_catalog_prevents_proposal(self):
        path = self.root / 'curated.json'
        catalog = json.loads(path.read_text())
        catalog['assets'][0]['facts']['relation'] = {'catalog': 'different', 'schema': 'xyz', 'name': 'customers'}
        path.write_text(json.dumps(catalog))
        result = self.propose()
        self.assertIsNone(result['proposed_document'])
        self.assertIn('catalog_conflict', self.fixture.codes(result['planning']))
