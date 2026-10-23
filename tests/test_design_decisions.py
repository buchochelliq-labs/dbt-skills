import copy
import json
import unittest

import test_model_planning
from dbt_skills.catalog import load_catalog
from dbt_skills.modelling_policy import load_document
from dbt_skills.model_planning import plan_model
from dbt_skills.design_decisions import load_design_decisions, DesignDecisionError


class DesignDecisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_model_planning.ModelPlanningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.project = self.fixture.fixture.project
        self.request = copy.deepcopy(self.fixture.request)
        self.path = self.root / 'design-decisions.json'

    def plan(self, decisions=None, catalog=None):
        return plan_model(self.project, load_document(self.root / 'modelling.yml'), catalog or load_catalog(self.root / 'catalogs.json'), self.request, decisions=decisions)

    def record(self):
        context = self.plan()['entities'][0]['decision_context']
        return {**context, 'id': 'customer_design', 'grain': ['customer_id'], 'history': 'source_rows',
                'rationale': 'One source customer per row; preserve all received rows.',
                'recorded_by': 'project_owner', 'recorded_at': '2026-10-23T12:00:00Z'}

    def save(self, records):
        self.path.write_text(json.dumps({'schema_version': 1, 'kind': 'design_decisions', 'records': records}))
        return load_design_decisions(self.path)

    def codes(self, plan):
        return {q['code'] for q in plan['questions']}

    def test_reuses_current_choices_with_record_provenance(self):
        record = self.record()
        result = self.plan(self.save([record]))
        entity = result['entities'][0]
        self.assertEqual(entity['grain']['basis'], 'recorded_design_decision')
        self.assertEqual(entity['grain']['suggested'], ['customer_id'])
        self.assertFalse(entity['grain']['verified'])
        self.assertEqual(entity['history'], 'source_rows')
        self.assertEqual(entity['decision']['record']['rationale'], record['rationale'])
        self.assertEqual(entity['decision']['provenance']['locator'], '/records/0')
        self.assertNotIn('confirm_grain', self.codes(result))
        self.assertNotIn('choose_history', self.codes(result))
        self.assertIn('functional_dependencies', self.codes(result))
        self.assertEqual(entity['normal_form_status'], 'unverified')

    def test_retrieval_time_changes_do_not_invalidate_facts(self):
        record = self.record()
        decisions = self.save([record])
        catalog = load_catalog(self.root / 'catalogs.json')
        for provider in catalog.providers:
            provider.retrieved_at = '2026-10-23T13:00:00+00:00'
        self.assertNotIn('stale_design_decision', self.codes(self.plan(decisions, catalog)))

    def test_changed_evidence_requires_reconfirmation(self):
        decisions = self.save([self.record()])
        path = self.root / 'physical.json'
        doc = json.loads(path.read_text())
        doc['assets'][0]['facts']['columns'][1]['nullable'] = False
        path.write_text(json.dumps(doc))
        result = self.plan(decisions)
        self.assertIn('stale_design_decision', self.codes(result))
        self.assertIn('confirm_grain', self.codes(result))

    def test_new_intent_or_scope_does_not_reuse_old_choice(self):
        decisions = self.save([self.record()])
        self.request['intent'] = 'Build historical customer versions'
        self.assertIn('confirm_grain', self.codes(self.plan(decisions)))
        self.request = copy.deepcopy(self.fixture.request)
        self.request['assets'][0]['scope'] = {'layer': 'core'}
        self.assertIn('confirm_grain', self.codes(self.plan(decisions)))

    def test_conflicting_explicit_choices_and_duplicate_records_clarify(self):
        record = self.record()
        decisions = self.save([record])
        self.request['assets'][0]['history'] = 'historical'
        result = self.plan(decisions)
        self.assertIn('design_decision_conflict', self.codes(result))
        self.assertIn('confirm_grain', self.codes(result))
        self.request = copy.deepcopy(self.fixture.request)
        other = dict(record, id='another')
        self.assertIn('ambiguous_design_decision', self.codes(self.plan(self.save([record, other]))))

    def test_missing_columns_and_current_history_still_need_review(self):
        record = self.record()
        record.update(grain=['missing'], history='current')
        result = self.plan(self.save([record]))
        self.assertIn('grain_columns_missing', self.codes(result))
        self.assertIn('current_row_rule', self.codes(result))

    def test_invalid_documents_do_not_echo_contents(self):
        record = self.record()
        for change in [{'recorded_at': 'not-a-date'}, {'history': 'PRIVATE_SENTINEL'}, {'approved': True}, {'grain': []}]:
            with self.assertRaises(DesignDecisionError) as caught:
                self.save([{**record, **change}])
            self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))

    def test_policy_manifest_and_provider_order_invalidate_choice(self):
        decisions = self.save([self.record()])
        for path in [self.root / 'modelling.yml', self.fixture.fixture.manifest, self.root / 'catalogs.json']:
            original = path.read_text()
            path.write_text(original + '\n')
            self.assertIn('stale_design_decision', self.codes(self.plan(decisions)))
            path.write_text(original)

    def test_loader_bounds_duplicate_keys_and_ids(self):
        record = self.record()
        with self.assertRaises(DesignDecisionError):
            self.save([record, record])
        for content in ['x' * (1024 * 1024 + 1), '{"kind":"design_decisions","kind":"design_decisions"}', '[' * 20 + '0' + ']' * 20]:
            self.path.write_text(content)
            with self.assertRaises(DesignDecisionError):
                load_design_decisions(self.path)

    def test_cli_reuses_reviewed_choices(self):
        import os
        import subprocess
        import sys
        from pathlib import Path
        self.save([self.record()])
        (self.root / 'plan.json').write_text(json.dumps(self.request))
        result = subprocess.run([sys.executable, '-m', 'dbt_skills.model_planning', '--project-dir', str(self.root), '--request', 'plan.json', '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json', '--design-decisions', self.path.name],
                                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')), capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)['entities'][0]['grain']['basis'], 'recorded_design_decision')

    def test_stdio_pins_file_and_refreshes_explicitly(self):
        import asyncio
        import os
        import sys
        from pathlib import Path
        from mcp import Client, MCPError, StdioServerParameters
        record = self.record()
        self.save([record])
        async def exercise():
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
            params = StdioServerParameters(command=sys.executable, args=['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json', '--design-decisions', self.path.name], env=env)
            async with Client(params, read_timeout_seconds=20) as client:
                context = (await client.call_tool('modelling_context', {})).structured_content
                self.assertEqual(context['design_decisions']['sha256'], load_design_decisions(self.path)['provenance']['sha256'])
                args = {'context_id': context['context_id'], 'request': self.request}
                result = (await client.call_tool('model_plan', args)).structured_content
                self.assertEqual(result['entities'][0]['grain']['basis'], 'recorded_design_decision')
                self.save([{**record, 'history': 'historical'}])
                with self.assertRaises(MCPError):
                    await client.call_tool('model_plan', args)
                context = (await client.call_tool('modelling_refresh', {})).structured_content
                with self.assertRaises(MCPError):
                    await client.call_tool('model_plan', args)
                args['context_id'] = context['context_id']
                result = (await client.call_tool('model_plan', args)).structured_content
                self.assertIn('history_rule', self.codes(result))
                self.assertEqual(result['entities'][0]['history'], 'historical')
        asyncio.run(exercise())
