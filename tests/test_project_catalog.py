import copy
import io
import json
import unittest
from unittest.mock import patch

import test_unity_catalog
TABLE = test_unity_catalog.TABLE
from dbt_skills.catalog import CatalogError


class ProjectCatalogTests(unittest.TestCase):
    setUp = test_unity_catalog.UnityCatalogTests.setUp
    load = test_unity_catalog.UnityCatalogTests.load
    def snapshot(self, names=('customers',)):
        return {'manifest': {'status': 'available', 'identity': 'matched', 'project_name': 'demo',
            'sha256': 'a'*64, 'resources': [dict(unique_id='source.demo.'+n, resource_type='source',
                package_name='demo', database='demo', schema='xyz', identifier=n) for n in names]}}

    def test_project_scope_blocks_unrelated_reads_before_network(self):
        from dbt_skills.project_catalog import scope_catalog
        self.entry['assets']['unrelated'] = 'demo.xyz.unrelated'
        scoped = scope_catalog(self.load(), self.snapshot())
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')) as request:
            self.assertEqual(scoped.resolve('unrelated', ['columns'])['status'], 'denied')
            request.assert_not_called()
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(TABLE).encode())):
            self.assertEqual(scoped.resolve('customers', ['columns'])['status'], 'complete')

    def test_missing_manifest_and_ephemeral_outputs_never_expand_scope(self):
        from dbt_skills.project_catalog import scope_catalog
        for snapshot in [{'manifest': {'status': 'missing'}}, self.snapshot(())]:
            scoped = scope_catalog(self.load(), snapshot)
            self.assertEqual(scoped.resolve('customers', ['columns'])['status'], 'denied')
        snapshot = self.snapshot()
        snapshot['manifest']['resources'][0].update(resource_type='model', materialized='ephemeral', alias='customers')
        self.assertEqual(scope_catalog(self.load(), snapshot).resolve('customers', ['columns'])['status'], 'denied')

    def test_delta_fetches_added_assets_and_discards_removed(self):
        from dbt_skills.project_catalog import scope_catalog
        first = scope_catalog(self.load(), self.snapshot())
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(TABLE).encode())):
            initial = first.resolve('customers', ['columns'])
        self.entry['assets']['orders'] = 'demo.xyz.orders'
        table = dict(TABLE, name='orders', full_name='demo.xyz.orders')
        second = scope_catalog(self.load(), self.snapshot(('customers', 'orders')), previous=first)
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(table).encode())) as request:
            result = second.sync_delta(first)
            self.assertEqual(result['added'], ['orders'])
            self.assertEqual(result['removed'], [])
            self.assertEqual(second.resolve('customers', ['columns'])['selected']['columns'], initial['selected']['columns'])
            self.assertEqual(request.call_count, 1)
        third = scope_catalog(self.load(), self.snapshot(('orders',)), previous=second)
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')):
            result = third.sync_delta(second)
            self.assertEqual(result['removed'], ['customers'])
            self.assertEqual(third.resolve('customers', ['columns'])['status'], 'denied')

    def test_conflicting_in_project_mappings_never_fetch(self):
        from dbt_skills.catalog import CatalogResolver
        from dbt_skills.project_catalog import scope_catalog
        first = self.load().providers[0]
        self.entry['id'] = 'second'
        self.entry['assets']['customers'] = 'demo.xyz.orders'
        second = self.load().providers[0]
        scoped = scope_catalog(CatalogResolver([first, second]), self.snapshot(('customers', 'orders')))
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')) as request:
            self.assertEqual(scoped.resolve('customers', ['columns'])['status'], 'denied')
            request.assert_not_called()

    def test_file_search_excludes_conflicting_and_unrelated_assets(self):
        from dbt_skills.catalog import CatalogResolver, FileCatalogProvider
        from dbt_skills.project_catalog import scope_catalog
        uc = self.load().providers[0]
        path = self.root / 'facts.json'
        path.write_text(json.dumps({'schema_version': 1, 'generated_at': '2026-10-23T00:00:00Z',
            'assets': [{'id': 'customers', 'native_id': 'local', 'facts': {
                'relation': {'catalog': 'demo', 'schema': 'xyz', 'name': 'orders'}}},
                       {'id': 'unrelated', 'native_id': 'other', 'facts': {
                'relation': {'catalog': 'demo', 'schema': 'xyz', 'name': 'outside'}}}]}))
        scoped = scope_catalog(CatalogResolver([uc, FileCatalogProvider('file', path, 'dev')]), self.snapshot(('customers', 'orders')))
        self.assertEqual(scoped.search('file', '')['assets'], [])
        self.assertEqual(scoped.resolve('customers', ['columns'])['scope_reason'], 'conflicting_bindings')

    def test_mcp_sync_fetches_only_new_source_and_rotates_context(self):
        import asyncio
        from mcp import Client, MCPError
        from dbt_skills.modelling_mcp import create_server
        from dbt_skills.project import discover_project
        self.load()
        (self.root / 'dbt_project.yml').write_text('name: demo\n')
        (self.root / 'target').mkdir()
        path = self.root / 'target/manifest.json'
        def write_manifest(names):
            resources = self.snapshot(names)['manifest']['resources']
            path.write_text(json.dumps({'metadata': {'project_name': 'demo',
                'dbt_schema_version': 'https://schemas.getdbt.com/dbt/manifest/v12.json'},
                'nodes': {}, 'sources': {r['unique_id']: r for r in resources}}))
        write_manifest(('customers',))
        server = create_server(discover_project(self.root), catalog_path='catalogs.json')
        requested = []
        def response(req, **kwargs):
            requested.append(req.full_url)
            table = copy.deepcopy(TABLE)
            if 'xyz.orders?' in req.full_url:
                table.update(name='orders', full_name='demo.xyz.orders')
            return io.BytesIO(json.dumps(table).encode())
        async def exercise():
            async with Client(server) as client:
                key = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                await client.call_tool('catalog_resolve', {'context_id': key, 'asset_id': 'customers', 'fields': ['columns']})
                self.entry['assets']['orders'] = 'demo.xyz.orders'
                self.load()
                write_manifest(('customers', 'orders'))
                synced = (await client.call_tool('catalog_sync', {'context_id': key})).structured_content
                self.assertEqual(synced['delta']['added'], ['orders'])
                self.assertEqual(synced['delta']['unchanged_count'], 1)
                self.assertEqual(len(requested), 2)
                with self.assertRaises(MCPError):
                    await client.call_tool('catalog_resolve', {'context_id': key, 'asset_id': 'customers', 'fields': ['columns']})
                key = synced['context_id']
                repeated = (await client.call_tool('catalog_sync', {'context_id': key})).structured_content
                self.assertEqual(repeated['delta']['results'], {})
                self.assertEqual(len(requested), 2)
        with patch('urllib.request.OpenerDirector.open', side_effect=response):
            asyncio.run(exercise())

    def test_quarantine_is_reviewable_and_unaffected_assets_keep_working(self):
        from dbt_skills.catalog import CatalogResolver
        from dbt_skills.project_catalog import scope_catalog
        self.entry['assets']['orders'] = 'demo.xyz.orders'
        first = self.load().providers[0]
        self.entry['id'] = 'second'
        self.entry['assets'] = {'customers': 'demo.xyz.orders'}
        second = self.load().providers[0]
        scoped = scope_catalog(CatalogResolver([first, second]), self.snapshot(('customers', 'orders')))
        review = scoped.quarantine(offset=0, limit=1)
        self.assertEqual(review['records'][0]['asset_id'], 'customers')
        self.assertEqual(review['records'][0]['status'], 'quarantined')
        self.assertEqual({b['provider'] for b in review['records'][0]['bindings']}, {'uc', 'second'})
        self.assertTrue(all(b['binding_sha256'] for b in review['records'][0]['bindings']))
        self.assertEqual(scoped.describe()['project_scope']['quarantined_count'], 1)
        table = dict(TABLE, name='orders', full_name='demo.xyz.orders')
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(table).encode())) as request:
            delta = scoped.sync_delta()
            self.assertEqual(delta['quarantined'], ['customers'])
            self.assertEqual(request.call_count, 1)
            self.assertEqual(scoped.resolve('orders', ['columns'])['status'], 'complete')
        repaired = scope_catalog(CatalogResolver([first]), self.snapshot(('customers', 'orders')), previous=scoped)
        self.assertEqual(repaired.quarantine()['records'], [])
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(TABLE).encode())):
            self.assertEqual(repaired.resolve('customers', ['columns'])['status'], 'complete')
