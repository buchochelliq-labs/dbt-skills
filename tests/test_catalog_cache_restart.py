import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import test_unity_catalog
from cache_test_support import MemoryKeyStore
from dbt_skills.project_catalog import scope_catalog


class RestartTests(unittest.TestCase):
    setUp = test_unity_catalog.UnityCatalogTests.setUp
    load = test_unity_catalog.UnityCatalogTests.load

    def scoped(self):
        return scope_catalog(self.load(), {'manifest': {'path': str(self.root / 'manifest.json'),
            'status': 'available', 'identity': 'matched', 'project_name': 'demo', 'resources': [{
                'resource_type': 'source', 'database': 'demo', 'schema': 'xyz', 'identifier': 'customers'}]}})

    def test_restart_reuses_provenance_but_forced_denial_removes_disk_claims(self):
        self.entry['cache'] = {'storage': 'disk', 'ttl_seconds': None}
        keys = MemoryKeyStore()
        with patch('dbt_skills.catalog_cache_store.OSKeyringKeyStore', return_value=keys):
            first = self.scoped()
            with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(test_unity_catalog.TABLE).encode())):
                initial = first.resolve('customers', ['columns'])
            self.assertEqual(initial['status'], 'complete')
            second = self.scoped()
            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('unexpected request')) as request:
                again = second.resolve('customers', ['columns'])
                self.assertEqual(again, initial)
                request.assert_not_called()
            forced = self.scoped()
            forced.providers[0].original.force_refresh()
            with patch('urllib.request.OpenerDirector.open', side_effect=HTTPError('x', 403, 'private', {}, None)):
                self.assertEqual(forced.resolve('customers', ['columns'])['status'], 'denied')
            reopened = self.scoped()
            with patch('urllib.request.OpenerDirector.open', side_effect=HTTPError('x', 403, 'private', {}, None)) as request:
                self.assertEqual(reopened.resolve('customers', ['columns'])['status'], 'denied')
                self.assertEqual(request.call_count, 1)
