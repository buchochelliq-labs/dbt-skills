"""Project membership gates catalog calls before provider access, with delta sync."""
from copy import deepcopy
import hashlib
import json

from .catalog import CatalogError, CatalogResolver, FIELDS, ProviderResult, _identifier


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _relations(snapshot):
    manifest = snapshot.get('manifest', {})
    if manifest.get('status') != 'available' or manifest.get('identity') != 'matched':
        return {}
    relations = {}
    for resource in manifest.get('resources', []):
        kind = resource.get('resource_type')
        if kind not in ('source', 'model', 'seed', 'snapshot') or resource.get('materialized') == 'ephemeral':
            continue
        # Sources from dependency packages are inputs too; produced relations must
        # belong to the selected project, not every installed package.
        if kind != 'source' and resource.get('package_name') != manifest.get('project_name'):
            continue
        name = (resource.get('identifier') if kind == 'source' else resource.get('alias')) or resource.get('name')
        relation = (resource.get('database'), resource.get('schema'), name)
        try:
            for part in relation:
                _identifier(part)
        except CatalogError:
            continue
        relations.setdefault(relation, []).append(resource)
    return relations


class _ScopedProvider:
    def __init__(self, provider, allowed):
        self.original = provider
        self.id, self.capabilities = provider.id, getattr(provider, 'capabilities', ())
        self.allowed = frozenset(allowed)

    def describe(self):
        return self.original.describe()

    def fetch(self, asset_id, fields):
        if asset_id not in self.allowed:
            return ProviderResult('not_found')
        return self.original.fetch(asset_id, fields)

    def search(self, query, *, offset=0, limit=20):
        # Only providers implementing an explicitly scoped search can expose a
        # page. Never traverse a remote catalog to filter it after retrieval.
        search = getattr(self.original, 'search_scoped', None)
        if search is None:
            return {'status': 'unsupported', 'assets': [], 'next_offset': None}
        return search(self.allowed, query, offset=offset, limit=limit)


class ProjectCatalog(CatalogResolver):
    def __init__(self, catalog, snapshot, previous=None):
        if isinstance(catalog, ProjectCatalog):
            catalog = catalog.original
        self.original = catalog
        relations = _relations(snapshot)
        bindings = []
        for provider in catalog.providers:
            method = getattr(provider, 'project_bindings', None)
            bindings.append(method() if method else {})
        allowed, identities = set(), {}
        for binding in bindings:
            for asset_id, value in binding.items():
                relation = value.get('relation')
                key = tuple(relation.get(k) for k in ('catalog', 'schema', 'name')) if relation else None
                if key in relations:
                    allowed.add(asset_id)
                    identities.setdefault(asset_id, []).extend(relations[key])
        providers = []
        self.blocked = set()
        for asset_id in allowed:
            targets = {tuple(value['relation'].get(k) for k in ('catalog', 'schema', 'name'))
                       for binding in bindings if (value := binding.get(asset_id)) and value.get('relation')}
            if len(targets) != 1:
                self.blocked.add(asset_id)
        self._quarantine = [{'asset_id': asset_id, 'status': 'quarantined',
            'reason': 'conflicting_relation_bindings', 'review_required': True,
            'bindings': [{'provider': provider.id, 'relation': deepcopy(binding[asset_id].get('relation')),
                          'binding_sha256': _hash(binding[asset_id]),
                          'config_provenance': deepcopy(catalog.config)}
                         for provider, binding in zip(catalog.providers, bindings) if asset_id in binding],
            'resolution': 'Correct the configured mappings or local catalog declarations, then sync; no automatic winner'}
            for asset_id in sorted(self.blocked)]
        self.fingerprints = {}
        for provider, binding in zip(catalog.providers, bindings):
            eligible = []
            for asset_id in allowed:
                value = binding.get(asset_id)
                if value is None:
                    continue
                relation = value.get('relation')
                key = tuple(relation.get(k) for k in ('catalog', 'schema', 'name')) if relation else None
                # Curated fact-only bindings inherit explicit shared identity from
                # a mapped in-project relation; conflicting relations are excluded.
                self.fingerprints.setdefault(asset_id, []).append([provider.id, value])
                if relation is not None and key not in relations:
                    self.blocked.add(asset_id)
                if relation is None or key in relations:
                    eligible.append(asset_id)
            providers.append(_ScopedProvider(provider, eligible))
        self.fingerprints = {a: _hash([identities[a], v]) for a, v in self.fingerprints.items()}
        self.allowed = frozenset(self.fingerprints)
        for provider in providers:
            provider.allowed = provider.allowed - self.blocked
        super().__init__(providers, catalog.resolution)
        self.config = deepcopy(catalog.config)
        for provider in self.providers:
            binder = getattr(provider.original, 'bind_project', None)
            if binder:
                binder(snapshot.get('manifest', {}).get('path'), {a: self.fingerprints[a] for a in provider.allowed})
        self.manifest = {k: snapshot.get('manifest', {}).get(k) for k in ('sha256', 'status', 'identity')}
        if previous is not None:
            prior = {p.id: p.original for p in previous.providers}
            for provider in self.providers:
                carry = getattr(provider.original, 'carry_observations', None)
                if carry and provider.id in prior:
                    unchanged = {a for a in provider.allowed if previous.fingerprints.get(a) == self.fingerprints[a]}
                    carry(prior[provider.id], unchanged)

    def describe(self):
        result = super().describe()
        result['project_scope'] = {'manifest': deepcopy(self.manifest),
                                   'active_count': len(self.allowed - self.blocked),
                                   'quarantined_count': len(self.blocked)}
        result['cache'] = [p.original.cache_report() for p in self.providers if hasattr(p.original, 'cache_report')]
        return result

    def quarantine(self, *, offset=0, limit=20):
        self._check_config()
        if type(offset) is not int or not 0 <= offset <= 800 or type(limit) is not int or not 1 <= limit <= 20:
            raise CatalogError('Use quarantine offset 0..800 and limit 1..20')
        return {'records': deepcopy(self._quarantine[offset:offset + limit]),
                'next_offset': offset + limit if offset + limit < len(self._quarantine) else None,
                'total': len(self._quarantine), 'manifest': deepcopy(self.manifest)}

    def resolve(self, asset_id, fields):
        # Let the shared resolver validate the request and produce its standard
        # shape. A scope-denied sentinel makes zero backend calls.
        if asset_id not in self.allowed or asset_id in self.blocked:
            class Denied:
                id = 'project_scope'
                def fetch(self, asset_id, fields):
                    return ProviderResult('denied')
            result = CatalogResolver([Denied()]).resolve(asset_id, fields)
            result['effective_policy'] = deepcopy(self.resolution)
            result['selection'] = ('First claim in explicit provider priority; all encountered claims retained' if self.resolution['provider_priority']['enabled'] else 'First configured claim per fact; conflicts require clarification')
            result['scope_reason'] = 'conflicting_bindings' if asset_id in self.blocked else 'outside_project'
            return result
        return super().resolve(asset_id, fields)

    def sync_delta(self, previous=None):
        old = previous.fingerprints if previous else {}
        added = sorted(set(self.fingerprints) - set(old))
        removed = sorted(set(old) - set(self.fingerprints))
        changed = sorted(a for a in set(old) & set(self.fingerprints) if old[a] != self.fingerprints[a])
        expired = sorted(a for a in self.allowed - self.blocked if any(
            a in p.allowed and getattr(p.original, 'needs_refresh', lambda _: False)(a) for p in self.providers))
        # Fetch only delta assets; the ordinary ordered resolver still governs
        # provider priority, denial and missing facts. No relationship expansion.
        results = {a: self.resolve(a, list(FIELDS))['status'] for a in sorted(set(added + changed + expired)) if a not in self.blocked}
        return {'added': added, 'changed': changed, 'removed': removed,
                'unchanged_count': len(set(old) & set(self.fingerprints)) - len(changed),
                'expired': expired, 'results': results, 'quarantined': sorted(self.blocked), 'manifest': deepcopy(self.manifest)}


def scope_catalog(catalog, snapshot, *, previous=None):
    if isinstance(catalog, ProjectCatalog) and previous is None and catalog.manifest == {
            k: snapshot.get('manifest', {}).get(k) for k in ('sha256', 'status', 'identity')}:
        return catalog
    return ProjectCatalog(catalog, snapshot, previous)
