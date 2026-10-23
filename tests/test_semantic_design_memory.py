import copy
import unittest

import test_design_decision_proposals
from dbt_skills.design_decisions import DesignDecisionError


class SemanticMemoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_design_decision_proposals.DesignDecisionProposalTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.answer = {'question_code': 'functional_dependencies',
                       'answer': 'Customer ID determines the customer attributes.',
                       'rationale': 'Reviewed business rule; source uniqueness remains unverified.'}
        self.fixture.request['record']['answers'] = [copy.deepcopy(self.answer)]

    def test_roundtrip_attaches_answer_without_claiming_proof_or_writing(self):
        root = self.fixture.root
        before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        result = self.fixture.propose()
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(before, {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()})
        decisions = self.fixture.fixture.save(result['proposed_document']['records'])
        plan = self.fixture.fixture.plan(decisions)
        question = next(q for q in plan['questions'] if q['code'] == 'functional_dependencies')
        saved = question['recorded_answer']
        self.assertEqual(saved['answer'], self.answer['answer'])
        self.assertEqual(saved['rationale'], self.answer['rationale'])
        self.assertEqual(saved['provenance']['locator'], '/records/0/answers/0')
        self.assertFalse(saved['verified'])
        self.assertEqual(plan['entities'][0]['normal_form_status'], 'unverified')
        self.assertEqual(plan['status'], 'needs_clarification')

    def test_stale_conflicting_and_ambiguous_records_do_not_supply_answers(self):
        record = self.fixture.propose()['proposed_document']['records'][0]
        for records in ([dict(record, evidence=dict(record['evidence'], policy_sha256='0'*64))],
                        [record, dict(record, id='duplicate')]):
            plan = self.fixture.fixture.plan(self.fixture.fixture.save(records))
            self.assertFalse(any('recorded_answer' in q for q in plan['questions']))
        self.fixture.fixture.request['assets'][0]['history'] = 'historical'
        plan = self.fixture.fixture.plan(self.fixture.fixture.save([record]))
        self.assertFalse(any('recorded_answer' in q for q in plan['questions']))

    def test_invalid_answers_are_bounded_and_do_not_echo_values(self):
        invalid = [None, {}, [self.answer]*2, [dict(self.answer, question_code='PRIVATE_SENTINEL')],
                   [dict(self.answer, answer=' ')], [dict(self.answer, answer='x'*2049)],
                   [dict(self.answer, rationale='x'*4097)], [dict(self.answer, approved=True)]]
        for answers in invalid:
            with self.subTest(answers_type=type(answers).__name__):
                self.fixture.request['record']['answers'] = answers
                with self.assertRaises(DesignDecisionError) as caught:
                    self.fixture.propose()
                self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))

    def test_inactive_question_requires_clarification(self):
        self.fixture.request['record']['answers'][0]['question_code'] = 'join_dependencies'
        result = self.fixture.propose()
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertIsNone(result['proposed_document'])
        self.assertIn('inactive_design_answer', {q['code'] for q in result['questions']})

    def test_cli_proposes_answers(self):
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        root = self.fixture.root
        (root / 'request.json').write_text(json.dumps(self.fixture.request))
        result = subprocess.run([sys.executable, '-m', 'dbt_skills.design_decision_proposals',
            '--project-dir', str(root), '--request', 'request.json', '--policy', 'modelling.yml',
            '--catalog-config', 'catalogs.json'], capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src')))
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)['proposed_document']['records'][0]
        self.assertEqual(record['answers'], [self.answer])

    def test_stdio_save_refresh_reuses_answers_and_invalidates_changed_evidence(self):
        import asyncio
        import os
        from pathlib import Path
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        f = self.fixture.fixture
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
                    {'context_id': key, 'request': self.fixture.request})).structured_content
                self.assertEqual(result['status'], 'pending_review')
                f.save(result['proposed_document']['records'])
                with self.assertRaises(MCPError):
                    await client.call_tool('model_plan', {'context_id': key, 'request': f.request})
                key = (await client.call_tool('modelling_refresh', {})).structured_content['context_id']
                plan = (await client.call_tool('model_plan', {'context_id': key, 'request': f.request})).structured_content
                q = next(q for q in plan['questions'] if q['code'] == 'functional_dependencies')
                self.assertEqual(q['recorded_answer']['answer'], self.answer['answer'])
                self.assertTrue(q['review_required'])
                path = f.root / 'physical.json'
                path.write_text(path.read_text() + '\n')
                key = (await client.call_tool('modelling_refresh', {})).structured_content['context_id']
                plan = (await client.call_tool('model_plan', {'context_id': key, 'request': f.request})).structured_content
                self.assertIn('stale_design_decision', {q['code'] for q in plan['questions']})
                self.assertFalse(any('recorded_answer' in q for q in plan['questions']))
        asyncio.run(exercise())

    def test_explicit_replacement_updates_answer_without_mutating_old_record(self):
        original = self.fixture.propose()['proposed_document']['records']
        decisions = self.fixture.fixture.save(original)
        self.fixture.request['record']['answers'][0]['answer'] = 'Revised business understanding.'
        self.assertEqual(self.fixture.propose(decisions)['status'], 'needs_clarification')
        self.fixture.request['replace_record_id'] = original[0]['id']
        result = self.fixture.propose(decisions)
        self.assertEqual(result['status'], 'pending_review')
        self.assertEqual(result['decisions_patch'][0]['value']['answers'], [self.answer])
        self.assertEqual(decisions['document']['records'], original)
        self.assertEqual(result['proposed_document']['records'][0]['answers'][0]['answer'],
                         'Revised business understanding.')
