import copy
import json
import unittest

import test_design_decision_proposals
from dbt_skills.design_decisions import DesignDecisionError


class RelatedDesignContextTests(unittest.TestCase):
    def setUp(self):
        self.f = test_design_decision_proposals.DesignDecisionProposalTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.fixture.fixture.add_orders()
        self.customer = 'urn:demo:xyz:customers'
        self.order = 'urn:demo:xyz:orders'
        self.f.request['plan']['assets'] = [
            {'asset_id': self.order, 'grain': ['order_id'], 'history': 'source_rows'},
            {'asset_id': self.customer, 'grain': ['customer_id']}]
        self.f.request['record']['answers'] = [{
            'question_code': 'confirm_relationship', 'target_asset': self.customer,
            'columns': ['customer_id'], 'target_columns': ['customer_id'],
            'answer': 'An order belongs to one customer; retain separate entities.',
            'rationale': 'Different business lifecycles; physical integrity is unverified.'}]

    def save_and_plan(self):
        proposal = self.f.propose()
        self.assertEqual(proposal['status'], 'pending_review')
        records = proposal['proposed_document']['records']
        decisions = self.f.fixture.save(records)
        self.f.fixture.request = copy.deepcopy(self.f.request['plan'])
        return records, decisions, self.f.fixture.plan(decisions)

    def test_related_answer_roundtrip_and_provenance(self):
        records, _, plan = self.save_and_plan()
        related = records[0]['related_contexts']
        self.assertEqual([r['asset_id'] for r in related], [self.customer])
        self.assertEqual(len(related[0]['evidence']['catalog_facts_sha256']), 64)
        q = next(q for q in plan['questions'] if q['code'] == 'confirm_relationship')
        self.assertEqual(q['recorded_answer']['target_asset'], self.customer)
        self.assertFalse(q['recorded_answer']['verified'])
        self.assertEqual(q['recorded_answer']['provenance']['locator'], '/records/0/answers/0')
        self.assertEqual(plan['relationships'][0]['cardinality'], 'unverified')

    def test_missing_related_asset_prevents_reuse(self):
        _, decisions, _ = self.save_and_plan()
        self.f.fixture.request['assets'] = [{'asset_id': self.order}]
        plan = self.f.fixture.plan(decisions)
        self.assertIn('incomplete_design_decision', {q['code'] for q in plan['questions']})
        self.assertEqual(plan['entities'][0]['decision']['status'], 'incomplete')
        self.assertFalse(any('recorded_answer' in q for q in plan['questions']))
        self.assertIn('confirm_grain', {q['code'] for q in plan['questions']})

    def test_target_assertion_conflict_prevents_reuse(self):
        _, decisions, _ = self.save_and_plan()
        self.f.fixture.request['assets'][1]['grain'] = ['customer_name']
        plan = self.f.fixture.plan(decisions)
        self.assertIn('design_decision_conflict', {q['code'] for q in plan['questions']})
        self.assertFalse(any('recorded_answer' in q for q in plan['questions']))

    def test_target_scope_or_evidence_change_is_stale(self):
        records, decisions, _ = self.save_and_plan()
        # Change only the saved target fingerprint, leaving the anchor valid.
        records[0]['related_contexts'][0]['evidence']['catalog_facts_sha256'] = '0'*64
        plan = self.f.fixture.plan(self.f.fixture.save(records))
        self.assertIn('stale_design_decision', {q['code'] for q in plan['questions']})
        self.f.fixture.request['assets'][1]['scope'] = {'layer': 'different'}
        plan = self.f.fixture.plan(decisions)
        self.assertIn('stale_design_decision', {q['code'] for q in plan['questions']})

    def test_wrong_answer_target_does_not_create_record(self):
        self.f.request['record']['answers'][0]['target_asset'] = 'urn:other'
        result = self.f.propose()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertIsNone(result['proposed_document'])

    def test_duplicate_or_unbound_dependencies_rejected(self):
        records, _, _ = self.save_and_plan()
        duplicate = copy.deepcopy(records)
        duplicate[0]['related_contexts'] *= 2
        with self.assertRaises(DesignDecisionError):
            self.f.fixture.save(duplicate)
        records[0]['answers'][0]['target_asset'] = 'urn:other'
        with self.assertRaises(DesignDecisionError):
            self.f.fixture.save(records)

    def test_distinct_relationships_between_same_entities_do_not_share_answers(self):
        path = self.f.root / 'physical.json'
        doc = json.loads(path.read_text())
        order = doc['assets'][1]['facts']
        order['columns'].append({'name': 'billing_customer_id', 'type': 'int64', 'nullable': False})
        order['foreign_keys'].append(dict(order['foreign_keys'][0], columns=['billing_customer_id']))
        path.write_text(json.dumps(doc))
        _, _, plan = self.save_and_plan()
        questions = [q for q in plan['questions'] if q['code'] == 'confirm_relationship']
        self.assertEqual(len(questions), 2)
        self.assertEqual([q['columns'] for q in questions if 'recorded_answer' in q], [['customer_id']])
        self.f.request['record']['answers'][0]['columns'] = ['order_id']
        self.assertEqual(self.f.propose()['status'], 'needs_clarification')

    def test_denied_related_catalog_withholds_all_context(self):
        from dbt_skills.catalog import CatalogResolver, ProviderResult, load_catalog
        provider = load_catalog(self.f.root / 'catalogs.json').providers[0]
        target = self.customer
        class Denied:
            id = 'denied'
            def fetch(self, asset_id, fields):
                return ProviderResult('denied') if asset_id == target else provider.fetch(asset_id, fields)
        result = self.f.propose(catalog=CatalogResolver([Denied()]))
        self.assertEqual(result['status'], 'blocked')
        self.assertIsNone(result['proposed_document'])
        self.assertEqual(result['planning']['evidence'], {})

    def test_stdio_related_proposal_refresh_and_reuse(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, StdioServerParameters
        f = self.f.fixture
        f.save([])
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=[
                '-m', 'dbt_skills.modelling_mcp', '--project-dir', str(f.root),
                '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json',
                '--design-decisions', f.path.name],
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')))
            async with Client(params, read_timeout_seconds=20) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                result = (await client.call_tool('model_propose_decision',
                    {'context_id': key, 'request': self.f.request})).structured_content
                self.assertEqual(result['status'], 'pending_review')
                f.save(result['proposed_document']['records'])
                key = (await client.call_tool('modelling_refresh', {})).structured_content['context_id']
                plan = (await client.call_tool('model_plan',
                    {'context_id': key, 'request': self.f.request['plan']})).structured_content
                question = next(q for q in plan['questions'] if q['code'] == 'confirm_relationship')
                self.assertEqual(question['recorded_answer']['target_asset'], self.customer)
                self.assertEqual(question['recorded_answer']['columns'], ['customer_id'])
                self.assertFalse(question['recorded_answer']['verified'])
        asyncio.run(exercise())
