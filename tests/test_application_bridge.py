"""Real project-scoped bridge acceptance tests for durable application preferences."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dbt_skills.application_api import OntologyApplication
from dbt_skills.application_store import ApplicationStore
from dbt_skills.catalog_cache import CachedProvider
from dbt_skills.project import discover_project
from dbt_skills.workspace_service import CoreBridge
from tests.cache_test_support import MemoryKeyStore


class ApplicationBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'dbt_project.yml').write_text('name: demo\n')
        (self.root / 'target').mkdir()
        resource = dict(unique_id='source.demo.customers', resource_type='source',
                        package_name='demo', database='demo', schema='xyz', identifier='customers')
        (self.root / 'target/manifest.json').write_text(json.dumps({
            'metadata': {'project_name': 'demo', 'dbt_schema_version': 'https://schemas.getdbt.com/dbt/manifest/v12.json'},
            'nodes': {}, 'sources': {resource['unique_id']: resource}}))
        entries = [dict(id=name, type='unity_catalog', scope='dev',
                        host=f'https://{name}.example.com', token_env='TEST_UC_TOKEN',
                        assets={'customers': 'demo.xyz.customers', 'outside': 'demo.xyz.outside'})
                   for name in ['first', 'second']]
        (self.root / 'catalogs.json').write_text(json.dumps({'schema_version': 1, 'providers': entries}))
        env = patch.dict('os.environ', {'TEST_UC_TOKEN': 'token'})
        env.start(); self.addCleanup(env.stop)
        self.bridge = CoreBridge(discover_project(self.root), catalog_path='catalogs.json')
        self.addCleanup(self.bridge.close)
        self.store = ApplicationStore(self.root / 'app.db', key_store=MemoryKeyStore())
        self.app = OntologyApplication(self.store, bridge=self.bridge)
        self.fetches = []
        original = CachedProvider.fetch
        def tracked(provider, *args, **kwargs):
            self.fetches.append((provider.id, provider.options['ttl_seconds']))
            return original(provider, *args, **kwargs)
        mock = patch.object(CachedProvider, 'fetch', tracked)
        mock.start(); self.addCleanup(mock.stop)
        table = {'catalog_name':'demo', 'schema_name':'xyz', 'name':'customers',
                 'full_name':'demo.xyz.customers', 'table_id':'12345678-1234-1234-1234-123456789abc',
                 'columns':[{'name':'customer_id', 'type_name':'LONG', 'nullable':False}]}
        network = patch('urllib.request.OpenerDirector.open', side_effect=lambda *a, **k: io.BytesIO(json.dumps(table).encode()))
        network.start(); self.addCleanup(network.stop)

    def command(self, name, payload=None):
        return self.app.command(name, payload or {}, expected_revision=self.store.read()['revision'])

    def test_real_sync_snapshot_and_preferences_survive_sync_and_refresh(self):
        packet = self.command('catalog.sync')
        self.assertEqual(packet['result']['synced'], 1)
        self.assertEqual({p['id'] for p in packet['state']['providers']}, {'first','second'})
        self.assertEqual({p['kind'] for p in packet['state']['providers']}, {'uc'})
        # Persist the same preferences through the application's provider commands.
        self.command('provider.update', {'id':'first','patch':{'enabled':False}})
        self.command('provider.update', {'id':'second','patch':{'ttl':2}})
        self.command('provider.reorder', {'id':'second','delta':-1})
        self.fetches.clear()
        self.command('catalog.sync')
        self.bridge.call('modelling_refresh', {})
        snapshot = self.bridge.catalog_snapshot()
        self.assertEqual({p['id'] for p in snapshot['providers']}, {'first','second'})
        self.assertFalse(next(p for p in snapshot['providers'] if p['id']=='first')['enabled'])
        self.assertTrue(self.fetches)
        self.assertEqual(set(self.fetches), {('second',7200)})
        self.assertEqual([a['asset_id'] for a in snapshot['assets']], ['customers'])
        self.assertEqual(snapshot['assets'][0]['relation']['provenance']['provider'], 'second')
        self.assertEqual(snapshot['assets'][0]['columns']['value'][0]['name'], 'customer_id')

    def test_enabled_provider_order_survives_capture(self):
        self.command('catalog.sync')
        self.command('provider.reorder', {'id':'second','delta':-1})
        self.fetches.clear()
        self.command('catalog.sync')
        self.bridge.call('modelling_refresh', {})
        snapshot = self.bridge.catalog_snapshot()
        self.assertEqual(snapshot['assets'][0]['relation']['provenance']['provider'], 'second')
        self.assertEqual({identifier for identifier, _ in self.fetches}, {'second'})
        self.assertEqual([p['id'] for p in self.store.read()['state']['providers']], ['second','first'])

    def test_all_disabled_remain_configured_and_never_fetch(self):
        self.bridge.preferences([{'id':name,'enabled':False,'ttl':1} for name in ['first','second']])
        context = self.bridge.call('modelling_context', {})
        self.bridge.call('catalog_sync', {'context_id':context['context_id']})
        self.bridge.call('modelling_refresh', {})
        snapshot = self.bridge.catalog_snapshot()
        self.assertEqual(len(snapshot['providers']), 2)
        self.assertEqual(snapshot['assets'], [])
        self.assertEqual(self.fetches, [])
