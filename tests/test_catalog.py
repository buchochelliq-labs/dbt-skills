import copy
import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.catalog import CatalogError, FileCatalogProvider, CatalogResolver, load_catalog


ASSET = 'urn:example:customer'
COLUMNS = [{'name': 'customer_id', 'type': 'int64', 'nullable': False}]
RELATION = {'catalog': 'demo', 'schema': 'xyz', 'name': 'customers'}
KEY = {'columns': ['customer_id'], 'enforcement': 'unknown', 'rely': False}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def provider(self, name, facts, asset=ASSET):
        path = self.root / (name + '.json')
        path.write_text(json.dumps({'schema_version': 1, 'generated_at': '2026-10-23T08:00:00Z',
            'assets': [{'id': asset, 'native_id': name + '.customers', 'facts': facts}]}))
        return FileCatalogProvider(name, path, 'development')

    def test_first_sufficient_is_per_fact_and_keeps_provenance(self):
        first = self.provider('catalog', {'relation': RELATION, 'columns': COLUMNS})
        second = self.provider('curated', {'primary_key': KEY})
        result = CatalogResolver([first, second]).resolve(ASSET, ['columns', 'primary_key'])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['selected']['columns']['provenance']['provider'], 'catalog')
        self.assertEqual(result['selected']['primary_key']['provenance']['provider'], 'curated')
        provenance = result['selected']['columns']['provenance']
        self.assertEqual(provenance['source_at'], '2026-10-23T08:00:00Z')
        self.assertIsNotNone(provenance['retrieved_at'])
        self.assertIsNone(provenance['verified_at'])
        self.assertEqual(provenance['evidence_type'], 'declaration')
        self.assertEqual(len(provenance['revision']), 64)
        self.assertIn('/assets/0/facts/columns', provenance['locator'])
        self.assertEqual(result['missing'], [])

    def test_stops_without_querying_lower_provider(self):
        first = self.provider('one', {'columns': COLUMNS})
        second = self.provider('two', {'columns': []})
        second.path.unlink()
        result = CatalogResolver([first, second]).resolve(ASSET, ['columns'])
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['unqueried'], ['two'])
        self.assertEqual(len(result['attempts']), 1)

    def test_conflicts_preserved_but_never_reported_as_complete(self):
        first = self.provider('one', {'columns': COLUMNS})
        second = self.provider('two', {'columns': [], 'primary_key': KEY})
        result = CatalogResolver([first, second]).resolve(ASSET, ['columns', 'primary_key'])
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['conflicts'], ['columns'])
        self.assertEqual(len(result['claims']['columns']), 2)
        self.assertEqual(result['selected']['columns']['value'], COLUMNS)

    def test_matching_names_do_not_merge_distinct_asset_ids(self):
        first = self.provider('one', {'columns': COLUMNS})
        second = self.provider('two', {'primary_key': KEY}, asset='urn:other:customer')
        result = CatalogResolver([first, second]).resolve(ASSET, ['columns', 'primary_key'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['missing'], ['primary_key'])
        self.assertEqual(result['attempts'][1]['status'], 'not_found')

    def test_unknown_and_explicitly_empty_are_distinct(self):
        provider = self.provider('one', {'foreign_keys': []})
        result = CatalogResolver([provider]).resolve(ASSET, ['primary_key', 'foreign_keys'])
        self.assertEqual(result['missing'], ['primary_key'])
        self.assertEqual(result['selected']['foreign_keys']['value'], [])

    def test_changed_or_missing_file_requires_refresh_and_withholds_facts(self):
        first = self.provider('one', {'columns': COLUMNS})
        second = self.provider('two', {'primary_key': KEY})
        second.path.write_text('{}')
        result = CatalogResolver([first, second]).resolve(ASSET, ['columns', 'primary_key'])
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['selected'], {})
        self.assertEqual(result['claims'], {})
        second.path.unlink()
        self.assertEqual(second.fetch(ASSET, ['primary_key']).status, 'error')

    def test_search_paging_and_returned_values_cannot_mutate_snapshot(self):
        provider = self.provider('one', {'relation': RELATION, 'columns': COLUMNS})
        page = provider.search('customer', offset=0, limit=1)
        self.assertEqual(page['assets'][0]['asset_id'], ASSET)
        self.assertEqual(page['assets'][0]['provenance']['source_at'], provider.source_at)
        self.assertEqual(page['assets'][0]['provenance']['locator'], '/assets/0')
        self.assertIsNone(page['next_offset'])
        result = CatalogResolver([provider]).resolve(ASSET, ['columns'])
        result['selected']['columns']['value'].clear()
        self.assertEqual(len(CatalogResolver([provider]).resolve(ASSET, ['columns'])['selected']['columns']['value']), 1)
        for offset, limit in [(-1, 1), (0, 51), (0, 0)]:
            with self.assertRaises(CatalogError):
                provider.search('', offset=offset, limit=limit)

    def test_strict_privacy_schema_and_sanitized_errors(self):
        provider = self.provider('one', {'columns': COLUMNS})
        original = json.loads(provider.path.read_text())
        for field in ['samples', 'description', 'rows', 'min', 'sql']:
            doc = copy.deepcopy(original)
            doc['assets'][0]['facts'][field] = 'PRIVATE_SENTINEL'
            provider.path.write_text(json.dumps(doc))
            with self.assertRaises(CatalogError) as raised:
                FileCatalogProvider('one', provider.path, 'development')
            self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))
        provider.path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(CatalogError):
            FileCatalogProvider('one', provider.path, 'development')

    def test_config_order_relative_paths_and_invalid_provider(self):
        self.provider('one', {'columns': COLUMNS})
        self.provider('two', {'primary_key': KEY})
        config = self.root / 'catalogs.json'
        doc = {'schema_version': 1, 'providers': [{'id': name, 'type': 'file', 'path': name + '.json', 'scope': 'development'} for name in ['one', 'two']]}
        config.write_text(json.dumps(doc))
        resolver = load_catalog(config)
        self.assertEqual([p.id for p in resolver.providers], ['one', 'two'])
        self.assertEqual(resolver.resolve(ASSET, ['columns', 'primary_key'])['status'], 'complete')
        doc['providers'][0]['type'] = 'unknown'
        config.write_text(json.dumps(doc))
        with self.assertRaises(CatalogError):
            load_catalog(config)

    def test_denial_and_provider_exceptions_stop_fallback_and_suppress_values(self):
        from dbt_skills.catalog import ProviderResult
        class Denied:
            id = 'blocked'
            capabilities = ()
            def fetch(self, *_):
                return ProviderResult('denied')
        first = self.provider('one', {'columns': COLUMNS})
        last = self.provider('last', {'primary_key': KEY})
        result = CatalogResolver([first, Denied(), last]).resolve(ASSET, ['columns', 'primary_key'])
        self.assertEqual(result['status'], 'denied')
        self.assertEqual(result['claims'], {})
        self.assertEqual(result['unqueried'], ['last'])
        class Broken(Denied):
            def fetch(self, *_):
                raise RuntimeError('PRIVATE_SENTINEL')
        result = CatalogResolver([Broken(), last]).resolve(ASSET, ['columns'])
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))
        self.assertEqual(result['unqueried'], ['last'])

    def test_plugin_provenance_cannot_smuggle_unknown_fields_or_missing_evidence(self):
        from dbt_skills.catalog import Claim, ProviderResult
        base = self.provider('one', {'columns': COLUMNS})
        class Plugin:
            id = 'one'
            capabilities = ('columns',)
            def fetch(self, *_):
                return ProviderResult('available', (Claim('columns', COLUMNS, provenance),))
        for provenance in [dict(base.fetch(ASSET, ['columns']).claims[0].provenance, samples=['PRIVATE_SENTINEL']),
                           {'provider': 'one', 'asset_id': ASSET}]:
            result = CatalogResolver([Plugin()]).resolve(ASSET, ['columns'])
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('PRIVATE_SENTINEL', json.dumps(result))

    def test_same_asset_in_different_environment_scopes_is_not_combined(self):
        one = self.provider('one', {'columns': COLUMNS})
        two = self.provider('two', {'primary_key': KEY})
        two.scope = 'production'
        self.assertEqual(CatalogResolver([one, two]).resolve(ASSET, ['columns', 'primary_key'])['status'], 'error')

    def test_configuration_changes_fail_closed_until_reloaded(self):
        self.provider('one', {'columns': COLUMNS})
        config = self.root / 'catalogs.json'
        config.write_text(json.dumps({'schema_version': 1, 'providers': [{'id': 'one', 'type': 'file', 'path': 'one.json', 'scope': 'dev'}]}))
        resolver = load_catalog(config)
        config.write_text('{}')
        with self.assertRaises(CatalogError):
            resolver.resolve(ASSET, ['columns'])
        with self.assertRaises(CatalogError):
            resolver.search('one', '')

    def test_discovery_boundary_rejects_unstructured_provider_output(self):
        class Bad:
            id = 'bad'
            capabilities = ()
            def search(self, *args, **kwargs):
                return {'status': 'available', 'assets': [], 'next_offset': None, 'samples': ['PRIVATE_SENTINEL']}
            def describe(self):
                raise RuntimeError('PRIVATE_SENTINEL')
        resolver = CatalogResolver([Bad()])
        self.assertEqual(resolver.search('bad', '')['status'], 'error')
        status = resolver.describe()
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(status))
        self.assertEqual(status['providers'][0]['status'], 'error')

    def test_discovery_errors_do_not_echo_provider_messages(self):
        class Bad:
            id = 'bad'
            capabilities = ()
            def search(self, *args, **kwargs):
                raise CatalogError('PRIVATE_SENTINEL')
        self.assertEqual(CatalogResolver([Bad()]).search('bad', '')['status'], 'error')

    def test_customer_example_supports_reviewable_model_design(self):
        import yaml
        from dbt_skills.modelling_policy import resolve_policy_name
        example = Path(__file__).resolve().parents[1] / 'examples' / 'catalog-workflow'
        resolver = load_catalog(example / 'catalogs.json')
        found = resolver.search('physical', 'customers')['assets'][0]['asset_id']
        result = resolver.resolve(found, ['relation', 'columns', 'primary_key', 'foreign_keys'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['missing'], ['foreign_keys'])
        self.assertEqual(result['selected']['primary_key']['provenance']['provider'], 'curated')
        name = resolve_policy_name(example / 'modelling.yml', 'staging_file', {'system': 'xyz', 'concept': 'customer'})
        self.assertEqual(name['value'], 'models/staging/stg_xyz_customer.sql')
        sql = (example / name['value']).read_text()
        self.assertIn("source('xyz', 'customers')", sql)
        properties = yaml.safe_load((example / 'models' / 'staging' / 'customer.yml').read_text())
        self.assertEqual(properties['models'][0]['name'], Path(name['value']).stem)
        self.assertEqual(properties['models'][0]['columns'][0]['data_tests'], ['not_null', 'unique'])

    def test_file_permission_denial_is_distinct_from_missing_file(self):
        from unittest.mock import patch
        provider = self.provider('one', {'columns': COLUMNS})
        with patch('dbt_skills.catalog._raw', side_effect=PermissionError()):
            self.assertEqual(provider.fetch(ASSET, ['columns']).status, 'denied')
            self.assertEqual(provider.search('')['status'], 'denied')
        provider.path.unlink()
        self.assertEqual(provider.fetch(ASSET, ['columns']).status, 'error')

    def test_multiple_search_pages_and_null_key_declaration(self):
        provider = self.provider('one', {'primary_key': None})
        doc = json.loads(provider.path.read_text())
        doc['assets'].append({'id': 'urn:example:order', 'native_id': 'orders', 'facts': {}})
        provider.path.write_text(json.dumps(doc))
        provider = FileCatalogProvider('one', provider.path, 'development')
        resolver = CatalogResolver([provider])
        first = resolver.search('one', '', limit=1)
        self.assertEqual(first['next_offset'], 1)
        second = resolver.search('one', '', limit=1, offset=first['next_offset'])
        self.assertEqual(second['assets'][0]['asset_id'], 'urn:example:order')
        self.assertIsNone(second['next_offset'])
        result = resolver.resolve(ASSET, ['primary_key'])
        self.assertEqual(result['status'], 'complete')
        self.assertIsNone(result['selected']['primary_key']['value'])

    def test_document_bounds_and_invalid_metadata(self):
        provider = self.provider('one', {'columns': COLUMNS})
        original = json.loads(provider.path.read_text())
        bad = copy.deepcopy(original)
        bad['generated_at'] = '2026-99-99'
        duplicate = copy.deepcopy(original)
        duplicate['assets'].append(duplicate['assets'][0])
        bad_type = copy.deepcopy(original)
        bad_type['assets'][0]['facts']['columns'][0]['type'] = 'select RAW_SENTINEL'
        for doc in (bad, duplicate, bad_type):
            provider.path.write_text(json.dumps(doc))
            with self.assertRaises(CatalogError):
                FileCatalogProvider('one', provider.path, 'development')
        provider.path.write_bytes(b' ' * (1024 * 1024 + 1))
        with self.assertRaises(CatalogError):
            FileCatalogProvider('one', provider.path, 'development')

    def test_single_provider_response_cannot_mix_scope_or_native_identity(self):
        from dbt_skills.catalog import Claim, ProviderResult
        provider = self.provider('one', {'relation': RELATION, 'columns': COLUMNS})
        original = provider.fetch(ASSET, ['relation', 'columns']).claims
        class Mixed:
            id = 'one'
            capabilities = ('relation', 'columns')
            def fetch(self, *_):
                altered = dict(original[1].provenance, **change)
                return ProviderResult('available', (original[0], Claim('columns', COLUMNS, altered)))
        for change in ({'scope': 'production'}, {'native_id': 'another_asset'}):
            result = CatalogResolver([Mixed()]).resolve(ASSET, ['relation', 'columns'])
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['selected'], {})
