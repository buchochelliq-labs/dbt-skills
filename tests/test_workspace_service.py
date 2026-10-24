"""Independent HTTP acceptance: real loopback handler and real MCP core bridge."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from dbt_skills.project import discover_project
from dbt_skills.workspace_service import Application, CoreBridge, make_handler
from dbt_skills.workspace_store import WorkspaceStore
from tests.cache_test_support import MemoryKeyStore

FIXTURE = Path(__file__).resolve().parents[1] / 'examples/data-model-workflow'

class WorkspaceServiceAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = CoreBridge(discover_project(FIXTURE, target_path='artifacts'), policy_path='modelling.yml', catalog_path='catalogs.json')

    @classmethod
    def tearDownClass(cls):
        cls.bridge.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.keys = MemoryKeyStore()
        self.path = Path(self.temp.name) / 'workspace.db'
        self.store = WorkspaceStore(self.path, key_store=self.keys)
        self.token = 'independent-http-acceptance-token-32chars'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(Application(self.bridge, self.store), self.token, {'http://localhost:5173'}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temp.cleanup()

    def request(self, path, value=None, *, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        merged = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        for key, val in (headers or {}).items():
            if val is None:
                merged.pop(key, None)
            else:
                merged[key] = val
        connection.request('POST', path, body=raw if raw is not None else json.dumps(value or {}), headers=merged)
        response = connection.getresponse()
        status, payload = response.status, json.loads(response.read())
        self.assertEqual(response.getheader('Cache-Control'), 'no-store')
        connection.close()
        return status, payload

    def test_real_context_design_and_stale_id(self):
        status, context = self.request('/api/context')
        self.assertEqual(status, 200)
        cid = context['context_id']
        status, tools = self.request('/api/tools')
        self.assertEqual(status, 200)
        self.assertFalse(tools['simulation'])
        self.assertFalse(tools['source_records'])
        self.assertIn('model_plan', tools['tools'])
        self.assertFalse(any(name in tools['tools'] for name in ['query', 'sql', 'execute_sql', 'fetch_rows']))
        design = json.loads((FIXTURE / 'design-request.json').read_text())
        status, plan = self.request('/api/tool', {'name': 'model_plan', 'arguments': {'context_id': cid, 'request': design}})
        self.assertEqual(status, 200)
        self.assertEqual(plan['context_id'], cid)
        self.assertEqual(len(plan['entities']), 2)
        self.assertEqual(plan['status'], 'needs_clarification')
        self.assertEqual(plan['relationships'][0]['cardinality'], 'unverified')
        self.assertIn('provenance', plan['entities'][0]['grain'])
        status, refreshed = self.request('/api/tool', {'name': 'modelling_refresh', 'arguments': {}})
        self.assertEqual(status, 200)
        self.assertNotEqual(refreshed['context_id'], cid)
        status, rejected = self.request('/api/tool', {'name': 'model_plan', 'arguments': {'context_id': cid, 'request': design}})
        self.assertEqual(status, 400)
        self.assertNotIn('entities', rejected)
        status, _ = self.request('/api/tool', {'name': 'fetch_rows', 'arguments': {}})
        self.assertEqual(status, 400)

    def test_auth_host_and_origin(self):
        self.assertEqual(self.request('/api/context', headers={'Authorization': None})[0], 401)
        self.assertEqual(self.request('/api/context', headers={'Authorization': 'Bearer wrong'})[0], 401)
        self.assertEqual(self.request('/api/context', headers={'Origin': 'https://attacker.invalid'})[0], 403)
        self.assertEqual(self.request('/api/context', headers={'Host': 'attacker.invalid'})[0], 403)
        self.assertEqual(self.request('/api/context', headers={'Origin': 'http://localhost:5173'})[0], 200)
        # Missing Origin is explicitly supported for authenticated CLI clients.
        self.assertEqual(self.request('/api/context')[0], 200)

    def test_invalid_json_and_content_type(self):
        for raw in ['{', '{"x":1,"x":2}', '{"x":NaN}', '[]', 'null']:
            with self.subTest(raw=raw):
                self.assertEqual(self.request('/api/context', raw=raw)[0], 400)
        self.assertEqual(self.request('/api/context', headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.store.read()['revision'], 0)

    def test_persisted_save_and_import_conflict(self):
        document = {'schema_version': 1, 'records': [{'id': 'customer-design', 'kind': 'design', 'title': 'Customer draft', 'content': 'Review grain with owner', 'references': [], 'evidence': [], 'approval': 'reviewed'}]}
        status, saved = self.request('/api/workspace/save', {'document': document, 'expected_revision': 0})
        self.assertEqual((status, saved['revision']), (200, 1))
        reopened = WorkspaceStore(self.path, key_store=self.keys)
        self.assertEqual(reopened.read()['document'], document)
        self.assertNotIn(b'Review grain with owner', self.path.read_bytes())
        self.assertEqual(self.request('/api/workspace/save', {'document': document, 'expected_revision': 0})[0], 409)
        status, exported = self.request('/api/workspace/export')
        self.assertEqual(status, 200)
        status, preview = self.request('/api/workspace/import/preview', exported)
        self.assertEqual(status, 200)
        self.assertTrue(preview['approval_reset'])
        self.assertEqual(preview['document']['records'][0]['approval'], 'draft')
        self.assertEqual(self.request('/api/workspace/save', {'document': document, 'expected_revision': 1})[0], 200)
        self.assertEqual(self.request('/api/workspace/import/apply', {'preview_id': preview['preview_id']})[0], 409)
        status, preview = self.request('/api/workspace/import/preview', exported)
        self.assertEqual(status, 200)
        status, imported = self.request('/api/workspace/import/apply', {'preview_id': preview['preview_id']})
        self.assertEqual((status, imported['revision']), (200, 3))
        status, state = self.request('/api/workspace/read')
        self.assertEqual(status, 200)
        self.assertEqual(state['document']['records'][0]['approval'], 'draft')
        self.assertEqual(len(state['history']), 4)
        self.assertEqual(self.request('/api/workspace/import/preview', {'schema_version': 99})[0], 400)
        self.assertEqual(reopened.read()['revision'], 3)

if __name__ == '__main__':
    unittest.main()
