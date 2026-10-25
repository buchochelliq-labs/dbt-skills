import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from mcp import Client, MCPError, StdioServerParameters
import metadata_fixture
from test_local_context_updates import document, concept


class PlanningContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = metadata_fixture.MetadataFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        (self.root / 'business.json').write_text(json.dumps(document()))

    def client(self, business=True):
        args = ['-m', 'dbt_skills.modelling_mcp', '--project-dir', str(self.root), '--policy', 'modelling.yml', '--catalog-config', 'catalogs.json']
        if business:
            args += ['--business-context', 'business.json']
        return Client(StdioServerParameters(command=sys.executable, args=args, env=dict(os.environ)), read_timeout_seconds=20)

    def test_visible_inlined_schemas_and_sanitized_inputs(self):
        async def exercise():
            async with self.client() as client:
                tools = {t.name: t for t in (await client.list_tools()).tools}
                request = tools['model_plan'].input_schema['properties']['request']
                self.assertEqual(request['required'], ['intent', 'assets'])
                self.assertEqual(request['properties']['assets']['items']['properties']['history']['enum'], ['source_rows', 'current', 'historical'])
                self.assertIn('record', tools['model_propose_decision'].input_schema['properties']['request']['properties'])
                business = tools['business_context_propose']
                self.assertTrue(business.annotations.read_only_hint)
                self.assertEqual(business.input_schema['properties']['request']['properties']['section']['enum'], ['concepts', 'relationships'])
                for name in ['model_plan', 'model_propose_decision', 'business_context_propose']:
                    self.assertNotIn('$ref', json.dumps(tools[name].input_schema))
                    self.assertNotIn('path', tools[name].input_schema['properties'])
                self.assertFalse(any('accept' in name or 'write' in name for name in tools))
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                for name in ['model_plan', 'model_propose_decision', 'business_context_propose']:
                    for request in ['PRIVATE_SENTINEL', {'unexpected': 'PRIVATE_SENTINEL'}, ['PRIVATE_SENTINEL']]:
                        with self.assertRaises(MCPError) as caught:
                            await client.call_tool(name, {'context_id': key, 'request': request})
                        self.assertNotIn('PRIVATE_SENTINEL', str(caught.exception))
            async with self.client(business=False) as client:
                self.assertNotIn('business_context_propose', {t.name for t in (await client.list_tools()).tools})
        asyncio.run(exercise())

    def test_real_propose_cli_accept_refresh_and_read_back(self):
        async def exercise():
            async with self.client() as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                before = (self.root / 'business.json').read_bytes()
                record = concept('customer')
                record['definition'] = 'A party that has placed an order in this scope.'
                args = {'context_id': key, 'request': {'section': 'concepts', 'record': record, 'replace_record_id': 'customer'}}
                result = (await client.call_tool('business_context_propose', args)).structured_content
                self.assertEqual(result['status'], 'pending_review')
                self.assertEqual(before, (self.root / 'business.json').read_bytes())
                proposal = result['local_update']
                proposal_path = self.root / 'proposal.json'
                proposal_path.write_text(json.dumps(proposal))
                accepted = subprocess.run([sys.executable, '-m', 'dbt_skills.local_context_updates', '--project-dir', str(self.root), '--target', 'business.json', '--proposal', str(proposal_path), '--accept-sha256', proposal['proposal_sha256']], capture_output=True, text=True)
                self.assertEqual(accepted.returncode, 0, accepted.stderr)
                with self.assertRaises(MCPError):
                    await client.call_tool('business_context_propose', args)
                refreshed = (await client.call_tool('modelling_refresh', {})).structured_content
                with self.assertRaises(MCPError):
                    await client.call_tool('business_context', {'context_id': key})
                readback = (await client.call_tool('business_context', {'context_id': refreshed['context_id']})).structured_content
                self.assertEqual(readback['records'][0]['record'], record)
                self.assertEqual(readback['records'][1]['record'], concept('order'))
        asyncio.run(exercise())
