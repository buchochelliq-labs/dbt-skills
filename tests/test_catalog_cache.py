import unittest
from unittest.mock import patch
from dbt_skills.catalog import Claim, ProviderResult


class Provider:
    id = 'remote'
    capabilities = ('columns',)
    def __init__(self):
        self.calls = 0
        self.status = 'available'
    def fetch_fresh(self, asset_id, fields):
        self.calls += 1
        return ProviderResult(self.status, (Claim('columns', [], {'retrieved_at': 'original'}),) if self.status == 'available' else ())
    def cache_access(self):
        return self.status
    def cache_identity(self):
        return ('host', 'principal', 'scope')
    def project_bindings(self):
        return {'asset': {'relation': None}}


class CacheTests(unittest.TestCase):
    def cache(self, provider=None, **options):
        from dbt_skills.catalog_cache import CachedProvider
        return CachedProvider(provider or Provider(), {'ttl_seconds': 60, 'permission_ttl_seconds': 120, **options})

    def test_hit_preserves_original_claim_and_expiry_requires_new_snapshot(self):
        with patch('dbt_skills.catalog_cache.time.monotonic', return_value=0) as clock:
            p = Provider()
            cache = self.cache(p)
            first = cache.fetch('asset', ['columns'])
            clock.return_value = 59
            self.assertEqual(cache.fetch('asset', ['columns']), first)
            self.assertEqual(p.calls, 1)
            clock.return_value = 60
            self.assertEqual(cache.fetch('asset', ['columns']).status, 'error')
            self.assertEqual(p.calls, 1)
            fresh = self.cache(p)
            fresh.carry_observations(cache, {'asset'})
            self.assertEqual(fresh.fetch('asset', ['columns']).status, 'available')
            self.assertEqual(p.calls, 2)

    def test_permission_expiry_and_revocation_never_serve_cached_claims(self):
        with patch('dbt_skills.catalog_cache.time.monotonic', return_value=0) as clock:
            p = Provider()
            cache = self.cache(p, ttl_seconds=86400, permission_ttl_seconds=30)
            cache.fetch('asset', ['columns'])
            clock.return_value = 30
            self.assertEqual(cache.fetch('asset', ['columns']).status, 'error')
            p.status = 'denied'
            self.assertEqual(cache.fetch('asset', ['columns']).status, 'denied')

    def test_removed_assets_and_changed_identity_not_reused(self):
        p = Provider()
        cache = self.cache(p)
        cache.fetch('asset', ['columns'])
        fresh = self.cache(p)
        fresh.carry_observations(cache, set())
        self.assertEqual(fresh.entries, {})
        other = Provider()
        other.cache_identity = lambda: ('different',)
        fresh = self.cache(other)
        fresh.carry_observations(cache, {'asset'})
        fresh.fetch('asset', ['columns'])
        self.assertEqual(other.calls, 1)

    def test_ttl_suggestion_is_bounded_review_only_and_never_changes_settings(self):
        with patch('dbt_skills.catalog_cache.time.monotonic', return_value=0) as clock:
            p = Provider()
            cache = self.cache(p, permission_ttl_seconds=86400)
            cache.fetch('asset', ['columns'])
            for tick in (61, 122, 183):
                clock.return_value = tick
                fresh = self.cache(p, permission_ttl_seconds=86400)
                fresh.carry_observations(cache, {'asset'})
                fresh.fetch('asset', ['columns'])
                cache = fresh
            report = cache.cache_report()
            self.assertEqual(report['suggestion']['status'], 'pending_review')
            self.assertEqual(report['suggestion']['proposed_ttl_seconds'], 120)
            self.assertEqual(cache.options['ttl_seconds'], 60)
            self.assertNotIn('original', str(report))

    def test_invalid_config_rejected(self):
        from dbt_skills.catalog import CatalogError
        for options in [{'ttl_seconds': True}, {'ttl_seconds': 86401}, {'permission_ttl_seconds': 0}, {'extra': 1}]:
            with self.assertRaises(CatalogError):
                self.cache(**options)

    def test_no_metadata_ttl_still_obeys_permission_lifetime(self):
        with patch('dbt_skills.catalog_cache.time.monotonic', return_value=0) as clock:
            cache = self.cache(ttl_seconds=None, permission_ttl_seconds=86400)
            cache.fetch('asset', ['columns'])
            clock.return_value = 86399
            self.assertEqual(cache.fetch('asset', ['columns']).status, 'available')
            clock.return_value = 86400
            self.assertEqual(cache.fetch('asset', ['columns']).status, 'error')
            self.assertIsNone(cache.cache_report()['suggestion'])

    def test_project_switch_discards_memory_observations(self):
        p = Provider()
        cache = self.cache(p)
        cache.bind_project('one', {'asset': 'a'})
        cache.fetch('asset', ['columns'])
        cache.bind_project('two', {'asset': 'a'})
        cache.fetch('asset', ['columns'])
        self.assertEqual(p.calls, 2)

    def test_evicted_observation_requires_sync_and_is_refetched_after_carry(self):
        p = Provider()
        p.project_bindings = lambda: {'asset': {}, 'other': {}}
        cache = self.cache(p, max_objects=1)
        cache.fetch('asset', ['columns'])
        cache.fetch('other', ['columns'])
        self.assertEqual(cache.fetch('asset', ['columns']).status, 'error')
        fresh = self.cache(p, max_objects=1)
        fresh.carry_observations(cache, {'asset', 'other'})
        self.assertTrue(fresh.needs_refresh('asset'))
        self.assertEqual(fresh.fetch('asset', ['columns']).status, 'available')
        self.assertEqual(p.calls, 3)

    def test_changed_binding_or_project_cannot_reuse_observations(self):
        p = Provider()
        cache = self.cache(p)
        cache.bind_project('one', {'asset': 'a'})
        cache.fetch('asset', ['columns'])
        cache.bind_project('one', {'asset': 'b'})
        cache.fetch('asset', ['columns'])
        fresh = self.cache(p)
        fresh.bind_project('two', {'asset': 'b'})
        fresh.carry_observations(cache, {'asset'})
        fresh.fetch('asset', ['columns'])
        self.assertEqual(p.calls, 3)

    def test_accepting_longer_ttl_does_not_reset_original_age(self):
        with patch('dbt_skills.catalog_cache.time.monotonic', return_value=0) as clock:
            p = Provider()
            cache = self.cache(p, permission_ttl_seconds=86400)
            first = cache.fetch('asset', ['columns'])
            clock.return_value = 70
            fresh = self.cache(p, ttl_seconds=120, permission_ttl_seconds=86400)
            fresh.carry_observations(cache, {'asset'})
            self.assertEqual(fresh.fetch('asset', ['columns']), first)
            self.assertEqual(fresh.entries['asset']['at'], 0)
            clock.return_value = 120
            self.assertEqual(fresh.fetch('asset', ['columns']).status, 'error')
            self.assertEqual(p.calls, 1)

    def test_carry_enforces_reduced_capacity_and_tracks_evictions(self):
        p = Provider()
        p.project_bindings = lambda: {'asset': {}, 'other': {}}
        old = self.cache(p, max_objects=2)
        old.fetch('asset', ['columns'])
        old.fetch('other', ['columns'])
        fresh = self.cache(p, max_objects=1)
        fresh.carry_observations(old, {'asset', 'other'})
        self.assertEqual(list(fresh.entries), ['other'])
        self.assertTrue(fresh.needs_refresh('asset'))
