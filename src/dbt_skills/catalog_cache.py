"""Bounded catalog cache with optional protected persistence. Expiry never mutates a pinned context silently."""
from copy import deepcopy
import hashlib
import json
from threading import RLock
import time
from dataclasses import asdict

from .catalog import CatalogError, Claim, ProviderResult, _fields, _identifier, _PROVENANCE, _validate_facts

DEFAULTS = {'ttl_seconds': 3600, 'permission_ttl_seconds': 300, 'storage': 'memory', 'max_objects': 1000, 'max_bytes': 67108864}


def cache_options(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise CatalogError('Invalid catalog cache configuration')
    result = {**DEFAULTS, **value}
    if (result['ttl_seconds'] is not None and (type(result['ttl_seconds']) is not int or not 1 <= result['ttl_seconds'] <= 86400)) or type(result['permission_ttl_seconds']) is not int or not 1 <= result['permission_ttl_seconds'] <= 86400:
        raise CatalogError('Cache lifetimes must be integer seconds from 1 to 86400')
    if result['storage'] not in ('memory', 'disk') or type(result['max_objects']) is not int or not 1 <= result['max_objects'] <= 10000 or type(result['max_bytes']) is not int or not 1024 <= result['max_bytes'] <= 1073741824:
        raise CatalogError('Invalid cache storage or capacity limits')
    return result


def _fingerprint(result):
    claims = [{'field': c.field, 'value': c.value,
               'provenance': {k: v for k, v in c.provenance.items() if k not in ('retrieved_at', 'verified_at')}}
              for c in result.claims]
    return hashlib.sha256(json.dumps(claims, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class CachedProvider:
    def __init__(self, provider, options, *, disk_path=None):
        self.original = provider
        self.id, self.capabilities = provider.id, provider.capabilities
        self.options = cache_options(options)
        self.identity = provider.cache_identity()
        self.entries, self.observed, self.refresh_pending = {}, set(), set()
        self.lock = RLock()
        self.stats = {k: 0 for k in ('hits', 'fetches', 'metadata_expiry', 'permission_expiry', 'unchanged_refreshes', 'failures')}
        self.started = time.monotonic()
        self.latency_ms = 0
        self.disk_path, self.disk = disk_path, None
        self.project_namespace, self.binding_keys = None, {}
        self.bypass_disk = False

    def project_bindings(self):
        return self.original.project_bindings()

    def describe(self):
        return self.original.describe()

    def search(self, query, *, offset=0, limit=20):
        return self.original.search(query, offset=offset, limit=limit)

    def _inc(self, name):
        if time.monotonic() - self.started > 600:
            self.stats = {key: 0 for key in self.stats}
            self.started = time.monotonic()
        self.stats[name] = min(self.stats[name] + 1, 2147483647)

    def _expiry(self, entry):
        age = time.monotonic() - entry['at']
        if age < 0 or age >= self.options['permission_ttl_seconds']:
            return 'permission_expiry'
        if self.options['ttl_seconds'] is not None and age >= self.options['ttl_seconds']:
            return 'metadata_expiry'
        return None

    def force_refresh(self):
        self.entries.clear()
        self.observed.clear()
        self.refresh_pending.clear()
        self.bypass_disk = True

    def bind_project(self, namespace, fingerprints):
        with self.lock:
            keys = {a: hashlib.sha256((a + fingerprint).encode()).hexdigest()
                    for a, fingerprint in fingerprints.items()}
            if self.project_namespace != namespace or self.binding_keys != keys:
                self.entries.clear()
                self.observed.clear()
                self.refresh_pending.clear()
                self.disk = None
            self.project_namespace, self.binding_keys = namespace, keys

    def _storage(self):
        if self.options['storage'] != 'disk':
            return None
        if not self.project_namespace or self.disk_path is None:
            raise CatalogError('Persistent cache requires project scope')
        if self.disk is None:
            from .catalog_cache_store import CatalogCacheStore
            self.disk = CatalogCacheStore(self.disk_path, max_objects=self.options['max_objects'], max_bytes=self.options['max_bytes'])
            self.disk_namespace = self.disk.namespace(json.dumps([self.project_namespace, self.identity]))
            self.disk.prune(self.disk_namespace, set(self.binding_keys.values()))
        return self.disk

    def _encode(self, entry):
        return json.dumps({'wall': entry['wall'], 'result': asdict(entry['result'])}, separators=(',', ':')).encode()

    def _read_disk(self, asset_id):
        storage = self._storage()
        if storage is None or self.bypass_disk or asset_id not in self.binding_keys:
            return None
        raw = storage.get(self.disk_namespace, self.binding_keys[asset_id])
        if raw is None:
            return None
        try:
            if len(raw) > 1048576:
                raise ValueError()
            value = json.loads(raw)
            age = time.time() - value['wall']
            if not 0 <= age < 315360000:
                raise ValueError()
            result = value['result']
            if result['status'] != 'available' or not isinstance(result['claims'], list) or len(result['claims']) > 4:
                raise ValueError()
            claims = tuple(Claim(**c) for c in result['claims'])
            if len({c.field for c in claims}) != len(claims):
                raise ValueError()
            for claim in claims:
                _validate_facts({claim.field: claim.value})
                if claim.field not in self.capabilities or not _PROVENANCE.is_valid(claim.provenance) or claim.provenance['provider'] != self.id or claim.provenance['asset_id'] != asset_id:
                    raise ValueError()
            return {'at': time.monotonic() - age, 'wall': value['wall'], 'result': ProviderResult('available', claims)}
        except Exception:
            return None

    def _evict(self):
        # Insertion order tracks LRU; evicted observations remain in the observed
        # set, so re-reading them cannot silently mutate this context.
        while self.entries and (len(self.entries) > self.options['max_objects'] or
                sum(len(self._encode(e)) for e in self.entries.values()) > self.options['max_bytes']):
            del self.entries[next(iter(self.entries))]

    def needs_refresh(self, asset_id):
        with self.lock:
            entry = self.entries.get(asset_id)
            return asset_id in self.refresh_pending or (entry is None and asset_id in self.observed) or (entry is not None and (self._expiry(entry) is not None or entry['result'].status != 'available'))

    def fetch(self, asset_id, fields):
        _identifier(asset_id, asset=True)
        _fields(fields)
        if asset_id not in self.project_bindings():
            return ProviderResult('not_found')
        if not set(fields).intersection(self.capabilities):
            return ProviderResult('unsupported')
        with self.lock:
            try:
                if self.original.cache_identity() != self.identity or self.original.cache_access() != 'available':
                    self.entries.clear()
                    storage = self._storage()
                    if storage is not None:
                        storage.prune(self.disk_namespace, set())
                    return ProviderResult('denied')
                entry = self.entries.pop(asset_id, None)
                if entry is None and asset_id in self.observed:
                    return ProviderResult('error')
                if entry is None:
                    entry = self._read_disk(asset_id)
                if entry is not None:
                    self.entries[asset_id] = entry
                reason = self._expiry(entry) if entry else None
                if entry and asset_id in self.observed and reason:
                    return ProviderResult('error')  # Explicit sync/refresh must rotate context first.
                fetched = False
                if entry and not reason and entry['result'].status == 'available':
                    self._inc('hits')
                    result = entry['result']
                elif entry and asset_id in self.observed:
                    result = entry['result']
                else:
                    if reason:
                        self._inc(reason)
                    start = time.monotonic()
                    fetched = True
                    result = self.original.fetch_fresh(asset_id, list(self.capabilities))
                    self.latency_ms = min(2147483647, max(0, int((time.monotonic() - start) * 1000)))
                    self._inc('fetches')
                    if result.status != 'available':
                        self._inc('failures')
                    elif entry and entry['result'].status == 'available' and _fingerprint(result) == _fingerprint(entry['result']):
                        self._inc('unchanged_refreshes')
                    self.entries[asset_id] = {'at': time.monotonic(), 'wall': time.time(), 'result': deepcopy(result)}
                storage = self._storage()
                if storage is not None and result.status != 'available':
                    storage.prune(self.disk_namespace, set())
                if storage is not None and result.status == 'available' and fetched:
                    storage.put(self.disk_namespace, self.binding_keys[asset_id], self._encode(self.entries[asset_id]))
                elif storage is not None and result.status == 'available':
                    storage.touch(self.disk_namespace, self.binding_keys[asset_id])
                self.refresh_pending.discard(asset_id)
                self._evict()
                self.observed.add(asset_id)
                return ProviderResult(result.status, tuple(deepcopy(c) for c in result.claims if c.field in fields))
            except Exception:
                self.entries.pop(asset_id, None)
                self.observed.add(asset_id)
                self._inc('failures')
                if self.disk is not None:
                    try:
                        self.disk.prune(self.disk_namespace, set())
                    except Exception:
                        pass
                return ProviderResult('error')

    def carry_observations(self, previous, allowed):
        if not isinstance(previous, CachedProvider) or self.identity != previous.identity or self.project_namespace != previous.project_namespace:
            return
        with previous.lock:
            self.entries = {a: deepcopy(entry) for a, entry in previous.entries.items() if a in allowed}
            self._evict()
            self.refresh_pending = (previous.observed | previous.refresh_pending) & set(allowed) - set(self.entries)
            self.stats = deepcopy(previous.stats)
            self.started = previous.started

    def cache_report(self):
        with self.lock:
            elapsed = max(0, time.monotonic() - self.started)
            suggestion = None
            candidate = min(86400, (self.options['ttl_seconds'] or 86400) * 2, self.options['permission_ttl_seconds'])
            # Permission checks and forced refreshes cannot be solved by a longer
            # metadata TTL. Require repeated unchanged expiry-driven reads only.
            if (self.options['ttl_seconds'] is not None and self.stats['metadata_expiry'] >= 3 and self.stats['unchanged_refreshes'] >= 3
                    and not self.stats['permission_expiry'] and not self.stats['failures']
                    and elapsed <= 600 and candidate > self.options['ttl_seconds']):
                suggestion = {'status': 'pending_review', 'provider': self.id,
                    'current_ttl_seconds': self.options['ttl_seconds'], 'proposed_ttl_seconds': candidate,
                    'reason': 'Repeated metadata-expiry fetches returned unchanged claims within ten minutes',
                    'acceptance': 'Human edits provider cache configuration then syncs; rejection requires no action',
                    'permission_ttl_changed': False}
            return {'provider': self.id, 'storage': self.options['storage'], 'settings': deepcopy(self.options),
                    'counters': deepcopy(self.stats), 'last_fetch_latency_ms': self.latency_ms,
                    'expired_count': sum(self._expiry(e) is not None for e in self.entries.values()),
                    'suggestion': suggestion, 'requires_refresh_on_expiry': True}
