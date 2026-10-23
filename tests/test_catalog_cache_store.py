from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cache_test_support import MemoryKeyStore
from dbt_skills.catalog_cache_store import CatalogCacheStore


class StoreTests(unittest.TestCase):
    def test_persistent_encrypted_lru_and_size_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cache' / 'catalog.db'
            keys = MemoryKeyStore()
            store = CatalogCacheStore(path, max_objects=2, max_bytes=30, key_store=keys)
            namespace = store.namespace('project/provider/credential')
            with patch('dbt_skills.catalog_cache_store.time.time', side_effect=[1, 2, 3, 4]):
                store.put(namespace, 'a', b'PRIVATE_A')
                store.put(namespace, 'b', b'PRIVATE_B')
                self.assertEqual(store.get(namespace, 'a'), b'PRIVATE_A')
                store.put(namespace, 'c', b'PRIVATE_C')
            self.assertIsNone(store.get(namespace, 'b'))
            reopened = CatalogCacheStore(path, max_objects=2, max_bytes=30, key_store=keys)
            self.assertEqual(reopened.get(namespace, 'a'), b'PRIVATE_A')
            self.assertNotIn(b'PRIVATE', path.read_bytes())
            store.put(namespace, 'big', b'x' * 31)
            self.assertIsNone(store.get(namespace, 'big'))
            store.prune(namespace, {'c'})
            self.assertIsNone(store.get(namespace, 'a'))
            self.assertEqual(store.get(namespace, 'c'), b'PRIVATE_C')

    def test_reopening_with_smaller_limits_evicts_before_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cache.db'
            keys = MemoryKeyStore()
            store = CatalogCacheStore(path, max_objects=3, max_bytes=3000, key_store=keys)
            with patch('dbt_skills.catalog_cache_store.time.time', side_effect=[1, 2, 3]):
                for key in ('a', 'b', 'c'):
                    store.put('scope', key, b'x' * 600)
            smaller = CatalogCacheStore(path, max_objects=1, max_bytes=1024, key_store=keys)
            self.assertIsNone(smaller.get('scope', 'a'))
            self.assertIsNone(smaller.get('scope', 'b'))
            self.assertEqual(smaller.get('scope', 'c'), b'x' * 600)
