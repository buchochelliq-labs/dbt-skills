import copy
import json
from pathlib import Path
import tempfile
import unittest


class BusinessContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'dbt_project.yml').write_text('name: conceptual_project\n')
        self.path = self.root/'business.json'
        common = {'scope': {'domain': 'sales'}, 'status': 'reviewed',
                  'rationale': 'Confirmed business vocabulary.', 'recorded_by': 'domain_owner',
                  'recorded_at': '2026-10-23T18:00:00Z'}
        self.document = {'schema_version': 1, 'kind': 'business_context', 'concepts': [
            dict(common, id='customer', name='Customer', definition='A party buying our services.'),
            dict(common, id='order', name='Order', definition='A commitment to purchase services.')],
            'relationships': [dict(common, id='order_customer', **{'from': 'order', 'to': 'customer'},
                                   predicate='placed_by', definition='An order is placed by a customer.')]}
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.document))

    def test_metadata_without_physical_assets_and_record_provenance(self):
        from dbt_skills.business_context import load_business_context, read_business_context
        before = self.path.read_bytes()
        loaded = load_business_context(self.path)
        result = read_business_context(loaded, 'relationships')
        self.assertEqual(result['records'][0]['record']['from'], 'order')
        self.assertEqual(result['records'][0]['provenance']['locator'], '/relationships/0')
        self.assertEqual(result['records'][0]['provenance']['sha256'], loaded['provenance']['sha256'])
        self.assertFalse(result['records'][0]['verified'])
        self.assertEqual(before, self.path.read_bytes())

    def test_paging_and_copy_isolation(self):
        from dbt_skills.business_context import load_business_context, read_business_context
        loaded = load_business_context(self.path)
        first = read_business_context(loaded, 'concepts', limit=1)
        self.assertEqual(first['next_offset'], 1)
        first['records'][0]['record']['name'] = 'mutated'
        self.assertEqual(read_business_context(loaded, 'concepts')['records'][0]['record']['name'], 'Customer')
        self.assertIsNone(read_business_context(loaded, 'concepts', offset=1, limit=1)['next_offset'])

    def test_invalid_documents_and_endpoints_fail_without_echo(self):
        from dbt_skills.business_context import load_business_context, BusinessContextError
        original = copy.deepcopy(self.document)
        for mutate in [
            lambda d: d['relationships'][0].update(to='unknown'),
            lambda d: d['concepts'].append(copy.deepcopy(d['concepts'][0])),
            lambda d: d['concepts'][0].update(status='PRIVATE_SENTINEL'),
            lambda d: d['concepts'][0].update(recorded_at='bad'),
            lambda d: d['concepts'][0].update(recorded_at='2026-10-23T18:00:00.'+'1'*100+'Z'),
            lambda d: d['concepts'][0].update(definition='x'*2049),
            lambda d: d['relationships'][0].update(sample_rows=[]),
            lambda d: d.update(schema_version=True),
        ]:
            self.document = copy.deepcopy(original)
            mutate(self.document)
            self.write()
            with self.assertRaises(BusinessContextError) as caught:
                load_business_context(self.path)
            self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))

    def test_invalid_page_and_section(self):
        from dbt_skills.business_context import load_business_context, read_business_context, BusinessContextError
        loaded = load_business_context(self.path)
        for args in [{'section':'unknown'}, {'section':'concepts','limit':21},
                     {'section':'concepts','offset':-1}, {'section':'concepts','limit':True}]:
            with self.assertRaises(BusinessContextError):
                read_business_context(loaded, **args)

    def test_cli_reads_relationships_without_manifest_or_catalog(self):
        import os
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-m', 'dbt_skills.business_context',
            '--project-dir', str(self.root), '--business-context', 'business.json',
            '--section', 'relationships'], capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src')))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['records'][0]['record']['predicate'], 'placed_by')

    def test_mcp_pins_refreshes_and_retains_context_after_failed_refresh(self):
        import asyncio
        import os
        import sys
        from mcp import Client, MCPError, StdioServerParameters
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=[
                '-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root),
                '--business-context', 'business.json'],
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src')))
            async with Client(params, read_timeout_seconds=20) as client:
                tools = {t.name:t for t in (await client.list_tools()).tools}
                self.assertTrue(tools['business_context'].annotations.read_only_hint)
                self.assertNotIn('path', tools['business_context'].input_schema['properties'])
                summary = (await client.call_tool('modelling_context', {})).structured_content
                key = summary['context_id']
                args = {'context_id': key, 'section': 'concepts'}
                initial = (await client.call_tool('business_context', args)).structured_content
                self.assertEqual(initial['records'][0]['record']['name'], 'Customer')
                self.document['concepts'][0]['name'] = 'Buyer'
                self.write()
                pinned = (await client.call_tool('business_context', args)).structured_content
                self.assertEqual(pinned, initial)
                refreshed = (await client.call_tool('modelling_refresh', {})).structured_content
                self.assertNotEqual(refreshed['business_context']['sha256'], summary['business_context']['sha256'])
                with self.assertRaises(MCPError):
                    await client.call_tool('business_context', args)
                args['context_id'] = refreshed['context_id']
                updated = (await client.call_tool('business_context', args)).structured_content
                self.assertEqual(updated['records'][0]['record']['name'], 'Buyer')
                self.path.write_text('{"PRIVATE_SENTINEL":true}')
                with self.assertRaises(MCPError) as caught:
                    await client.call_tool('modelling_refresh', {})
                self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))
                retained = (await client.call_tool('business_context', args)).structured_content
                self.assertEqual(retained, updated)
        asyncio.run(exercise())

    def test_duplicate_json_keys_and_size_limits(self):
        from dbt_skills.business_context import load_business_context, BusinessContextError
        for content in ['{"kind":"x","kind":"y"}', 'x'*(1024*1024+1), '['*20+'0'+']'*20]:
            self.path.write_text(content)
            with self.assertRaises(BusinessContextError):
                load_business_context(self.path)

    def test_proposed_conflicting_statements_remain_distinct(self):
        from dbt_skills.business_context import load_business_context, read_business_context
        other = dict(self.document['relationships'][0], id='alternative', status='proposed',
                     definition='An order may be attributed to several customers.', rationale='Awaiting domain review.')
        self.document['relationships'].append(other)
        self.write()
        result = read_business_context(load_business_context(self.path), 'relationships')
        self.assertEqual([r['record']['status'] for r in result['records']], ['reviewed', 'proposed'])
        self.assertTrue(all(r['verified'] is False for r in result['records']))

    def test_business_definition_change_invalidates_saved_design(self):
        import test_design_decision_proposals
        from dbt_skills.business_context import load_business_context
        from dbt_skills.catalog import load_catalog
        from dbt_skills.modelling_policy import load_document
        from dbt_skills.model_planning import plan_model
        from dbt_skills.design_decision_proposals import prepare_design_decision
        f = test_design_decision_proposals.DesignDecisionProposalTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        args = (f.fixture.project, load_document(f.root/'modelling.yml'), load_catalog(f.root/'catalogs.json'))
        business = load_business_context(self.path)
        proposed = prepare_design_decision(*args, f.request, business=business)
        decisions = f.fixture.save(proposed['proposed_document']['records'])
        plan = plan_model(*args, f.fixture.request, decisions=decisions, business=business)
        self.assertEqual(plan['entities'][0]['decision']['status'], 'matched')
        self.document['concepts'][0]['definition'] = 'Revised business meaning.'
        self.write()
        plan = plan_model(*args, f.fixture.request, decisions=decisions, business=load_business_context(self.path))
        self.assertEqual(plan['entities'][0]['decision']['status'], 'stale')
        plan = plan_model(*args, f.fixture.request, decisions=decisions)
        self.assertEqual(plan['entities'][0]['decision']['status'], 'stale')

    def test_mcp_planning_requires_refresh_after_business_edit(self):
        import asyncio
        import os
        import sys
        import test_design_decision_proposals
        from mcp import Client, MCPError, StdioServerParameters
        f = test_design_decision_proposals.DesignDecisionProposalTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.fixture.save([])
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=[
                '-m', 'dbt_skills.modelling_mcp', '--project-dir', str(f.root),
                '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json',
                '--design-decisions', f.fixture.path.name, '--business-context', str(self.path)],
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src')))
            async with Client(params, read_timeout_seconds=20) as client:
                context = (await client.call_tool('modelling_context', {})).structured_content
                proposal = (await client.call_tool('model_propose_decision',
                    {'context_id': context['context_id'], 'request': f.request})).structured_content
                record = proposal['proposed_document']['records'][0]
                self.assertEqual(record['evidence']['business_context_sha256'], context['business_context']['sha256'])
                f.fixture.save([record])
                context = (await client.call_tool('modelling_refresh', {})).structured_content
                args = {'context_id': context['context_id'], 'request': f.fixture.request}
                result = (await client.call_tool('model_plan', args)).structured_content
                self.assertEqual(result['entities'][0]['decision']['status'], 'matched')
                self.document['concepts'][0]['definition'] = 'Updated meaning.'
                self.write()
                with self.assertRaises(MCPError):
                    await client.call_tool('model_plan', args)
                context = (await client.call_tool('modelling_refresh', {})).structured_content
                args['context_id'] = context['context_id']
                result = (await client.call_tool('model_plan', args)).structured_content
                self.assertEqual(result['entities'][0]['decision']['status'], 'stale')
        asyncio.run(exercise())
