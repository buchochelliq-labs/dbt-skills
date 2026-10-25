import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from dbt_skills.catalog import CatalogError, load_catalog, CatalogResolver, FileCatalogProvider


TABLE = {'name': 'customers', 'fullyQualifiedName': 'service.demo.xyz.customers',
         'id': '12345678-1234-1234-1234-123456789abc',
         'columns': [{'name': 'customer_id', 'dataType': 'BIGINT', 'constraint': 'NOT_NULL',
                      'description': 'PRIVATE', 'dataTypeDisplay': 'BIGINT'}],
         'sampleData': {'rows': [['PRIVATE']]}, 'description': 'PRIVATE', 'schemaDefinition': 'PRIVATE'}



class OpenMetadataTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.entry = {'id': 'om', 'type': 'openmetadata', 'scope': 'dev',
                      'host': 'https://workspace.example.com', 'token_env': 'TEST_OM_TOKEN',
                      'assets': {'customers': 'service.demo.xyz.customers'}}
        self.env = patch.dict(os.environ, {'TEST_OM_TOKEN': 'test-token'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def load(self):
        path = self.root / 'catalogs.json'
        path.write_text(json.dumps({'schema_version': 1, 'providers': [self.entry]}))
        return load_catalog(path)

    def test_config_registers_lazy_provider(self):
        try:
            resolver = self.load()
        except CatalogError:
            self.fail('OpenMetadata configuration must be supported')
        self.assertEqual(resolver.providers[0].capabilities, ('relation', 'columns'))
        self.assertEqual(resolver.search('om', '')['status'], 'unsupported')
        self.assertEqual(resolver.describe()['providers'][0]['type'], 'openmetadata')

    def test_metadata_projection_provenance_and_pinning(self):
        resolver = self.load()
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(TABLE).encode())) as request:
            result = resolver.resolve('customers', ['relation', 'columns'])
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['selected']['columns']['value'],
                             [{'name': 'customer_id', 'type': 'int64', 'nullable': False, 'type_descriptor':{'schema_version':1,'native':'BIGINT','family':'int64'}}])
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertNotIn('test-token', json.dumps(result))
            provenance = result['selected']['columns']['provenance']
            self.assertEqual(provenance['native_id'], TABLE['id'])
            self.assertIsNone(provenance['verified_at'])
            self.assertEqual(provenance['locator'], '/columns')
            self.assertIn('/tables/name/service.demo.xyz.customers', provenance['document'])
            self.assertEqual(resolver.resolve('customers', ['columns'])['selected']['columns'], result['selected']['columns'])
            self.assertEqual(request.call_count, 1)
            req = request.call_args.args[0]
            self.assertEqual(req.get_method(), 'GET')
            self.assertEqual(req.get_header('Authorization'), 'Bearer test-token')
            self.assertIn('fields=columns&include=non-deleted', req.full_url)

    def test_denials_errors_and_bad_payloads_withhold_facts(self):
        for code, status in [(401, 'denied'), (403, 'denied'), (404, 'not_found'), (429, 'error'), (500, 'error'), (302, 'error')]:
            with self.subTest(code=code):
                resolver = self.load()
                with patch('urllib.request.OpenerDirector.open', side_effect=HTTPError('secret', code, 'PRIVATE', {}, None)):
                    result = resolver.resolve('customers', ['columns'])
                self.assertEqual(result['attempts'][0]['status'], status)
                self.assertEqual(result['selected'], {})
                self.assertNotIn('PRIVATE', json.dumps(result))
        bad = [b'not JSON', b'{"name":1,"name":2}', b'x' * (1024 * 1024 + 1)]
        for change in [{'name': 'wrong'}, {'fullyQualifiedName': 'wrong'}, {'columns': [TABLE['columns'][0]] * 2}, {'columns': [{'name': 'bad name', 'constraint': 'NOT_NULL'}]}]:
            table = copy.deepcopy(TABLE)
            table.update(change)
            bad.append(json.dumps(table).encode())
        for raw in bad:
            resolver = self.load()
            with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(raw)):
                self.assertIn(resolver.resolve('customers', ['columns'])['status'], ('error', 'denied'))

    def test_unknown_and_unsupported_do_not_request_remote(self):
        resolver = self.load()
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')) as request:
            self.assertEqual(resolver.resolve('missing', ['columns'])['status'], 'partial')
            self.assertEqual(resolver.resolve('customers', ['primary_key'])['status'], 'partial')
            request.assert_not_called()

    def test_missing_columns_remain_unknown_and_curated_fallback(self):
        table = copy.deepcopy(TABLE)
        del table['columns']
        path = self.root / 'curated.json'
        path.write_text(json.dumps({'schema_version': 1, 'generated_at': '2026-10-23T00:00:00Z',
            'assets': [{'id': 'customers', 'native_id': 'curated.customers',
                        'facts': {'primary_key': None}}]}))
        resolver = CatalogResolver([self.load().providers[0], FileCatalogProvider('curated', path, 'dev')])
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(table).encode())):
            result = resolver.resolve('customers', ['relation', 'columns', 'primary_key'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['missing'], ['columns'])
        self.assertIsNone(result['selected']['primary_key']['value'])

    def test_invalid_configuration_rejected(self):
        for change in [{'host': 'http://example.com'}, {'host': 'https://user:pass@example.com'},
                       {'host': 'https://example.com/path'}, {'host': 'https://example.com?token=x'},
                       {'token_env': 'bad-name'}, {'assets': {'customers': 'a.b'}},
                       {'assets': {'customers': 's.a.b.c', 'other': 's.a.b.c'}}, {'token': 'secret'}]:
            with self.subTest(change=change):
                original = copy.deepcopy(self.entry)
                self.entry.update(change)
                with self.assertRaises(CatalogError):
                    self.load()
                self.entry = original

    def test_token_changes_require_refresh_and_no_secret_exposure(self):
        resolver = self.load()
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(TABLE).encode())):
            self.assertEqual(resolver.resolve('customers', ['columns'])['status'], 'complete')
        os.environ['TEST_OM_TOKEN'] = 'changed'
        self.assertEqual(resolver.resolve('customers', ['columns'])['status'], 'denied')
        del os.environ['TEST_OM_TOKEN']
        resolver = self.load()
        self.assertEqual(resolver.resolve('customers', ['columns'])['status'], 'denied')

    def test_mcp_refresh_reloads_remote_metadata(self):
        import asyncio
        from mcp import Client
        from dbt_skills.modelling_mcp import create_server
        from dbt_skills.project import discover_project
        self.load()
        (self.root / 'dbt_project.yml').write_text('name: demo\n')
        (self.root / 'target').mkdir()
        (self.root / 'target/manifest.json').write_text(json.dumps({
            'metadata': {'project_name': 'demo', 'dbt_schema_version': 'https://schemas.getdbt.com/dbt/manifest/v12.json'},
            'nodes': {}, 'sources': {'source.demo.customers': {'resource_type': 'source', 'package_name': 'demo',
                'database': 'demo', 'schema': 'xyz', 'identifier': 'customers'}}}))
        server = create_server(discover_project(self.root), catalog_path='catalogs.json')
        table = copy.deepcopy(TABLE)
        def response(*args, **kwargs):
            return io.BytesIO(json.dumps(table).encode())
        async def exercise():
            async with Client(server) as client:
                context = (await client.call_tool('modelling_context', {})).structured_content['context_id']
                args = {'context_id': context, 'asset_id': 'customers', 'fields': ['columns']}
                initial = (await client.call_tool('catalog_resolve', args)).structured_content
                table['columns'][0]['name'] = 'new_id'
                pinned = (await client.call_tool('catalog_resolve', args)).structured_content
                self.assertEqual(initial, pinned)
                refreshed = (await client.call_tool('modelling_refresh', {})).structured_content
                args['context_id'] = refreshed['context_id']
                changed = (await client.call_tool('catalog_resolve', args)).structured_content
                self.assertEqual(changed['selected']['columns']['value'][0]['name'], 'new_id')
                self.assertNotEqual(initial['selected']['columns']['provenance']['revision'], changed['selected']['columns']['provenance']['revision'])
        with patch('urllib.request.OpenerDirector.open', side_effect=response):
            asyncio.run(exercise())

    def test_no_redirect_and_terminal_failure_prevents_fallback(self):
        from dbt_skills.openmetadata import _NoRedirect
        from urllib.request import Request
        self.assertIsNone(_NoRedirect().redirect_request(Request('https://example.com'), None, 302, '', {}, 'https://other.example'))
        first = self.load().providers[0]
        second = self.load().providers[0]
        second.id = 'later'
        resolver = CatalogResolver([first, second])
        with patch('urllib.request.OpenerDirector.open', side_effect=HTTPError('secret', 403, 'secret', {}, None)), patch.object(second, 'fetch', side_effect=AssertionError('fallback')):
            result = resolver.resolve('customers', ['columns'])
            self.assertEqual(result['status'], 'denied')
            self.assertEqual(result['unqueried'], ['later'])

    def test_missing_token_does_not_block_inapplicable_provider_fallback(self):
        del os.environ['TEST_OM_TOKEN']
        provider = self.load().providers[0]
        self.assertEqual(provider.fetch('outside_mapping', ['columns']).status, 'not_found')
        self.assertEqual(provider.fetch('customers', ['primary_key']).status, 'unsupported')
        self.assertEqual(provider.fetch('customers', ['columns']).status, 'denied')

    def test_scope_blocks_outside_project_before_transport(self):
        from dbt_skills.project_catalog import scope_catalog
        snapshot = {'manifest': {'status': 'available', 'identity': 'matched', 'project_name': 'demo',
            'resources': [{'resource_type': 'source', 'database': 'other', 'schema': 'xyz', 'identifier': 'customers'}]}}
        scoped = scope_catalog(self.load(), snapshot)
        with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('network')) as request:
            self.assertEqual(scoped.resolve('customers', ['columns'])['status'], 'denied')
            request.assert_not_called()

    def test_nullability_unknown_types_and_service_identity(self):
        table = copy.deepcopy(TABLE)
        table['columns'] = [{'name': 'a', 'dataType': 'UNRECOGNIZED'},
                            {'name': 'b', 'dataType': 'VARCHAR', 'constraint': 'NULL'},
                            {'name': 'c', 'dataType': 'INT', 'constraint': 'PRIMARY_KEY'}]
        first = self.load().providers[0]
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(table).encode())):
            result = first.fetch('customers', ['columns'])
        self.assertEqual(result.status, 'available')
        self.assertEqual([{k:v for k,v in c.items() if k!='type_descriptor'} for c in result.claims[0].value], [{'name': 'a', 'type': 'unknown', 'nullable': None},
            {'name': 'b', 'type': 'string', 'nullable': True}, {'name': 'c', 'type': 'int64', 'nullable': False}])
        self.assertEqual([c['type_descriptor']['native'] for c in result.claims[0].value], ['UNRECOGNIZED','VARCHAR','INT'])
        self.entry['assets']['customers'] = 'other.demo.xyz.customers'
        second = self.load().providers[0]
        self.assertNotEqual(first.project_bindings(), second.project_bindings())

    def test_deleted_and_oversized_column_sets(self):
        for update, status in [({'deleted': True}, 'not_found'), ({'columns': [TABLE['columns'][0]] * 257}, 'error')]:
            table = {**TABLE, **update}
            with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(table).encode())):
                self.assertEqual(self.load().providers[0].fetch('customers', ['columns']).status, status)
