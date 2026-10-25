"""Provider-neutral, metadata-only catalog contracts and ordered fact resolution.

Identifiers are curated metadata, not arbitrary free text. File providers are local
human assertions, not proof of upstream authorization or constraint enforcement.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Literal, Protocol

from jsonschema import Draft202012Validator, FormatChecker

_FORMATS = FormatChecker()


@_FORMATS.checks('date-time')
def _timestamp(value):
    # jsonschema's built-in date-time checker needs optional dependencies. Keep
    # provenance validation effective on every supported installation.
    if not isinstance(value, str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False


Field = Literal['relation', 'columns', 'primary_key', 'foreign_keys']
Status = Literal['available', 'not_found', 'unsupported', 'denied', 'error']
FIELDS = ('relation', 'columns', 'primary_key', 'foreign_keys')
_SCHEMA = json.loads(Path(__file__).with_name('catalog.schema.json').read_text())
_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=_FORMATS)
_FACTS = _SCHEMA['properties']['assets']['items']['properties']['facts']
_MAX_BYTES = 1024 * 1024
_ID = _SCHEMA['properties']['assets']['items']['properties']['id']
_NAME = _FACTS['properties']['relation']['properties']['name']
_TIME = {'type': 'string', 'format': 'date-time', 'maxLength': 64}
_PROVENANCE_FIELDS = {
    'provider': _NAME, 'asset_id': _ID, 'native_id': _ID,
    'document': {'type': 'string', 'minLength': 1, 'maxLength': 4096},
    'locator': {'type': 'string', 'minLength': 1, 'maxLength': 512},
    'revision': {'type': 'string', 'pattern': '^[a-f0-9]{64}$', 'maxLength': 64},
    'source_at': {'anyOf': [_TIME, {'type': 'null'}]}, 'retrieved_at': _TIME,
    'verified_at': {'anyOf': [_TIME, {'type': 'null'}]}, 'scope': _NAME,
    'evidence_type': {'enum': ['declaration']}, 'derivation': {'type': 'array', 'maxItems': 0}
}
_PROVENANCE = Draft202012Validator({'type': 'object', 'additionalProperties': False,
    'required': list(_PROVENANCE_FIELDS), 'properties': _PROVENANCE_FIELDS}, format_checker=_FORMATS)


_SEARCH = Draft202012Validator({'type': 'object', 'additionalProperties': False,
    'required': ['status', 'assets', 'next_offset'], 'properties': {
        'status': {'enum': ['available', 'not_found', 'unsupported', 'denied', 'error']},
        'provider': _NAME, 'revision': _PROVENANCE_FIELDS['revision'],
        'next_offset': {'type': ['integer', 'null'], 'minimum': 0, 'maximum': 100},
        'assets': {'type': 'array', 'maxItems': 50, 'items': {'type': 'object',
            'additionalProperties': False, 'required': ['asset_id', 'native_id', 'relation', 'provenance'],
            'properties': {'asset_id': _ID, 'native_id': _ID, 'provenance': _PROVENANCE.schema,
                'relation': {'anyOf': [_FACTS['properties']['relation'], {'type': 'null'}]}}}}
    }}, format_checker=_FORMATS)
_DESCRIPTION_FIELDS = {k: _PROVENANCE_FIELDS[k] for k in
    ('scope', 'document', 'revision', 'source_at', 'retrieved_at', 'verified_at')}
_DESCRIPTION_FIELDS.update({'id': _NAME, 'type': _NAME,
    'status': {'enum': ['available', 'not_found', 'unsupported', 'denied', 'error']},
    'capabilities': {'type': 'array', 'uniqueItems': True, 'maxItems': 4, 'items': {'enum': list(FIELDS)}}})
_DESCRIPTION = Draft202012Validator({'type': 'object', 'additionalProperties': False,
    'required': list(_DESCRIPTION_FIELDS), 'properties': _DESCRIPTION_FIELDS}, format_checker=_FORMATS)


class CatalogError(ValueError):
    """Safe static messages only: never include source contents or backend errors."""


@dataclass(frozen=True)
class Claim:
    field: Field
    value: object
    provenance: dict


@dataclass(frozen=True)
class ProviderResult:
    status: Status
    claims: tuple[Claim, ...] = ()


class CatalogProvider(Protocol):
    id: str
    capabilities: tuple[str, ...]

    def fetch(self, asset_id: str, fields: list[Field]) -> ProviderResult: ...
    def search(self, query: str, *, offset: int = 0, limit: int = 20) -> dict: ...
    def describe(self) -> dict: ...
    def project_bindings(self) -> dict: ...


def _identifier(value, *, asset=False):
    pattern = r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}' if asset else r'[A-Za-z_][A-Za-z0-9_]{0,127}'
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise CatalogError('Invalid catalog identifier')


def _fields(fields):
    if not isinstance(fields, list) or not 1 <= len(fields) <= len(FIELDS) or any(f not in FIELDS for f in fields) or len(set(fields)) != len(fields):
        raise CatalogError('Request one to four distinct supported fact fields')


def _search_args(query, offset, limit):
    if not isinstance(query, str) or len(query) > 128 or not query.isascii() or any(ord(c) < 32 for c in query):
        raise CatalogError('Use a bounded identifier search string')
    if type(offset) is not int or not 0 <= offset <= 100 or type(limit) is not int or not 1 <= limit <= 50:
        raise CatalogError('Use offset 0..100 and limit 1..50')


def _raw(path):
    # Nonblocking open + descriptor check avoids blocking on special files.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise CatalogError('Catalog input must be a regular file')
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise CatalogError('Catalog input exceeds 1 MiB')
    return raw


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError('Duplicate JSON keys are not supported')
        result[key] = value
    return result


def _document(path):
    try:
        raw = _raw(path)
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(CatalogError('Non-finite JSON value')))
        pending, count = [(doc, 0)], 0
        while pending:
            value, depth = pending.pop()
            count += 1
            if depth > 16 or count > 20000:
                raise CatalogError('Catalog input exceeds structural limits')
            if isinstance(value, dict):
                pending.extend((v, depth + 1) for v in value.values())
            elif isinstance(value, list):
                pending.extend((v, depth + 1) for v in value)
        return doc, hashlib.sha256(raw).hexdigest()
    except CatalogError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise CatalogError('Cannot read a valid catalog JSON document') from None


def _validate_facts(facts):
    from .metadata_types import validate_descriptor
    for column in facts.get("columns", []):
        if isinstance(column, dict) and "type_descriptor" in column:
            try:
                validate_descriptor(column["type_descriptor"])
            except ValueError:
                raise CatalogError("Invalid bounded native type descriptor") from None
    if not Draft202012Validator(_FACTS).is_valid(facts):
        raise CatalogError('Unsupported or invalid catalog metadata')
    if 'columns' in facts:
        names = [c['name'] for c in facts['columns']]
        if len(names) != len(set(names)):
            raise CatalogError('Duplicate catalog column identifiers')
    for fk in facts.get('foreign_keys', []):
        if len(fk['columns']) != len(fk['target_columns']):
            raise CatalogError('Relationship column counts differ')


class FileCatalogProvider:
    capabilities = FIELDS

    def __init__(self, provider_id: str, path: Path, scope: str):
        _identifier(provider_id)
        _identifier(scope)
        self.id, self.path, self.scope = provider_id, Path(path).resolve(), scope
        doc, self.revision = _document(self.path)
        if not _VALIDATOR.is_valid(doc):
            raise CatalogError('Document does not match catalog schema version 1')
        ids = [a['id'] for a in doc['assets']]
        if len(ids) != len(set(ids)):
            raise CatalogError('Duplicate catalog asset identifiers')
        for asset in doc['assets']:
            _validate_facts(asset['facts'])
        self._assets = {a['id']: (i, a) for i, a in enumerate(doc['assets'])}
        self.source_at = doc['generated_at']
        self.retrieved_at = datetime.now(timezone.utc).isoformat()

    def project_bindings(self):
        return {key: {'relation': deepcopy(asset['facts'].get('relation')),
                      'signature': {'scope': self.scope, 'document': str(self.path),
                                    'native_id': asset['native_id'], 'facts': deepcopy(asset['facts'])}}
                for key, (_, asset) in self._assets.items()}

    def search_scoped(self, allowed, query, *, offset=0, limit=20):
        from copy import copy
        scoped = copy(self)
        scoped._assets = {key: value for key, value in self._assets.items() if key in allowed}
        return scoped.search(query, offset=offset, limit=limit)

    def _access(self):
        try:
            return 'available' if hashlib.sha256(_raw(self.path)).hexdigest() == self.revision else 'error'
        except PermissionError:
            return 'denied'
        except (OSError, CatalogError):
            return 'error'

    def describe(self):
        return {'id': self.id, 'type': 'file', 'scope': self.scope, 'status': self._access(),
                'capabilities': list(self.capabilities), 'document': str(self.path),
                'revision': self.revision, 'source_at': self.source_at, 'retrieved_at': self.retrieved_at,
                'verified_at': None}

    def fetch(self, asset_id: str, fields: list[Field]) -> ProviderResult:
        _identifier(asset_id, asset=True)
        _fields(fields)
        access = self._access()
        if access != 'available':
            return ProviderResult(access)
        if asset_id not in self._assets:
            return ProviderResult('not_found')
        index, asset = self._assets[asset_id]
        claims = tuple(Claim(field, deepcopy(asset['facts'][field]),
                            self._provenance(asset, f'/assets/{index}/facts/{field}'))
                       for field in fields if field in asset['facts'])
        return ProviderResult('available', claims)

    def _provenance(self, asset, locator):
        return {'provider': self.id, 'asset_id': asset['id'], 'native_id': asset['native_id'],
                'document': str(self.path), 'locator': locator, 'revision': self.revision,
                'source_at': self.source_at, 'retrieved_at': self.retrieved_at, 'verified_at': None,
                'scope': self.scope, 'evidence_type': 'declaration', 'derivation': []}

    def search(self, query: str, *, offset=0, limit=20):
        _search_args(query, offset, limit)
        access = self._access()
        if access != 'available':
            return {'status': access, 'assets': [], 'next_offset': None}
        matches = [a for _, a in sorted(self._assets.values(), key=lambda item: item[1]['id'])
                   if query.lower() in ' '.join([a['id'], a['native_id'], *a['facts'].get('relation', {}).values()]).lower()]
        return {'status': 'available', 'provider': self.id, 'revision': self.revision,
                'assets': [{'asset_id': a['id'], 'native_id': a['native_id'], 'relation': deepcopy(a['facts'].get('relation')),
                            'provenance': self._provenance(a, f"/assets/{self._assets[a['id']][0]}")}
                           for a in matches[offset:offset + limit]],
                'next_offset': offset + limit if offset + limit < len(matches) else None}


def resolution_options(value=None, provider_ids=()):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {'planning_mode', 'type_compatibility', 'provider_priority'}:
        raise CatalogError('Invalid catalog resolution configuration')
    result = {'planning_mode': 'conservative', 'type_compatibility': 'compatible',
              'provider_priority': {'enabled': False, 'order': []}}
    result.update(deepcopy(value))
    priority = result['provider_priority']
    if (result['planning_mode'] not in ('conservative', 'partial') or
            result['type_compatibility'] not in ('compatible', 'exact') or
            not isinstance(priority, dict) or set(priority) - {'enabled', 'order'}):
        raise CatalogError('Invalid catalog resolution configuration')
    priority = {'enabled': False, 'order': [], **priority}
    order = priority['order']
    if type(priority['enabled']) is not bool or not isinstance(order, list) or len(order) > 8:
        raise CatalogError('Invalid provider priority')
    for identifier in order:
        _identifier(identifier)
    if priority['enabled'] and (len(order) != len(set(order)) or set(order) != set(provider_ids)):
        raise CatalogError('Enabled priority must name every configured provider exactly once')
    result['provider_priority'] = priority
    return result


class CatalogResolver:
    """First sufficient facts by default; explicit priority reads all active providers.

    Both modes preserve encountered claims and conflicts.

    Provider plugins are trusted code. Their structured result values are validated
    here; exceptions are never returned. A denial/error withholds all partial claims.
    """
    def __init__(self, providers: list[CatalogProvider], resolution=None):
        if not 1 <= len(providers) <= 8:
            raise CatalogError('Configure one to eight catalog providers')
        for p in providers:
            _identifier(p.id)
        if len({p.id for p in providers}) != len(providers):
            raise CatalogError('Provider IDs must be unique')
        self.resolution = resolution_options(resolution, [p.id for p in providers])
        self.providers = tuple(providers)
        self.config = None

    def _check_config(self):
        if self.config is not None:
            try:
                unchanged = hashlib.sha256(_raw(self.config['document'])).hexdigest() == self.config['revision']
            except (OSError, CatalogError):
                unchanged = False
            if not unchanged:
                raise CatalogError('Catalog configuration changed or inaccessible; refresh context')

    def describe(self):
        self._check_config()
        providers = []
        for provider in self.providers:
            try:
                info = provider.describe()
                if not _DESCRIPTION.is_valid(info) or info['id'] != provider.id:
                    raise CatalogError('Invalid provider description')
                providers.append(deepcopy(info))
            except Exception:
                providers.append({'id': provider.id, 'status': 'error', 'capabilities': []})
        return {'config': deepcopy(self.config), 'providers': providers, 'resolution': deepcopy(self.resolution)}

    def search(self, provider_id: str, query: str, *, offset=0, limit=20):
        self._check_config()
        _search_args(query, offset, limit)
        for provider in self.providers:
            if provider.id == provider_id:
                try:
                    page = provider.search(query, offset=offset, limit=limit)
                    if not _SEARCH.is_valid(page) or len(page['assets']) > limit:
                        raise CatalogError('Invalid provider search result')
                    if page['status'] == 'available':
                        if page.get('provider') != provider.id or 'revision' not in page:
                            raise CatalogError('Missing search provenance')
                        if any(a['provenance']['provider'] != provider.id or a['provenance']['asset_id'] != a['asset_id'] or a['provenance']['native_id'] != a['native_id'] or a['provenance']['revision'] != page['revision'] for a in page['assets']):
                            raise CatalogError('Search provenance mismatch')
                        if page['next_offset'] is not None and page['next_offset'] <= offset:
                            raise CatalogError('Invalid search continuation')
                    elif page['assets'] or page['next_offset'] is not None:
                        raise CatalogError('Unavailable search returned metadata')
                    return deepcopy(page)
                except Exception:
                    return {'status': 'error', 'assets': [], 'next_offset': None}
        raise CatalogError('Select a configured provider ID')

    def resolve(self, asset_id: str, fields: list[Field]) -> dict:
        self._check_config()
        _identifier(asset_id, asset=True)
        _fields(fields)
        selected, claims, attempts, conflicts = {}, {}, [], []
        priority = self.resolution['provider_priority']
        providers = sorted(self.providers, key=lambda p: priority['order'].index(p.id)) if priority['enabled'] else self.providers
        result = {'asset_id': asset_id, 'status': 'partial', 'selected': selected, 'claims': claims,
                  'missing': list(fields), 'conflicts': conflicts, 'resolved_conflicts': [], 'unresolved_conflicts': [], 'attempts': attempts,
                  'unqueried': [p.id for p in providers],
                  'effective_policy': deepcopy(self.resolution),
                  'selection': ('First claim in explicit provider priority; all encountered claims retained' if priority['enabled'] else 'First configured claim per fact; conflicts require clarification'),
                  'limitations': ['Unqueried providers imply neither agreement nor disagreement',
                                  'Declared keys and relationships are not proof of enforcement or normal form']}
        for provider in providers:
            result['unqueried'].remove(provider.id)
            try:
                response = provider.fetch(asset_id, fields)
                if response.status not in ('available', 'not_found', 'unsupported', 'denied', 'error'):
                    raise CatalogError('Invalid provider status')
                if response.status != 'available' and response.claims:
                    raise CatalogError('Non-available provider returned claims')
                seen = set()
                scopes = {c['provenance']['scope'] for c in selected.values()}
                native_ids = set()
                if len(response.claims) > 4:
                    raise CatalogError('Too many provider claims')
                for claim in response.claims:
                    if claim.field not in fields or claim.field in seen:
                        raise CatalogError('Unexpected provider fact')
                    seen.add(claim.field)
                    _validate_facts({claim.field: claim.value})
                    provenance = claim.provenance
                    if not _PROVENANCE.is_valid(provenance):
                        raise CatalogError('Invalid provider provenance')
                    if scopes and provenance['scope'] not in scopes:
                        raise CatalogError('Provider scope mismatch')
                    scopes.add(provenance['scope'])
                    native_ids.add(provenance['native_id'])
                    if len(native_ids) != 1:
                        raise CatalogError('Provider native identity mismatch')
                    if provenance.get('provider') != provider.id or provenance.get('asset_id') != asset_id:
                        raise CatalogError('Provider identity mismatch')
            except Exception:
                response = ProviderResult('error')
            attempts.append({'provider': provider.id, 'status': response.status})
            if response.status in ('denied', 'error'):
                result.update(status=response.status, selected={}, claims={}, conflicts=[], resolved_conflicts=[], unresolved_conflicts=[], missing=list(fields))
                return result
            for claim in response.claims:
                item = {'value': deepcopy(claim.value), 'provenance': deepcopy(claim.provenance)}
                claims.setdefault(claim.field, []).append(item)
                if claim.field not in selected:
                    selected[claim.field] = item
                elif selected[claim.field]['value'] != item['value'] and claim.field not in conflicts:
                    conflicts.append(claim.field)
            result['missing'] = [f for f in fields if f not in selected]
            if not result['missing'] and not priority['enabled']:
                break
        result['resolved_conflicts' if priority['enabled'] else 'unresolved_conflicts'] = list(conflicts)
        if priority['enabled']:
            result['selection'] = 'First claim in explicit provider priority; all encountered claims retained'
        result['status'] = 'conflict' if result['unresolved_conflicts'] else ('partial' if result['missing'] else 'complete')
        return result


def load_catalog(path: Path) -> CatalogResolver:
    """Operator-selected config; JSON paths are relative to that config file."""
    path = Path(path).resolve()
    doc, revision = _document(path)
    if not isinstance(doc, dict) or not {'schema_version', 'providers'} <= set(doc) or set(doc) - {'schema_version', 'providers', 'cache', 'resolution'} or type(doc['schema_version']) is not int or doc['schema_version'] != 1 or not isinstance(doc['providers'], list) or not 1 <= len(doc['providers']) <= 8:
        raise CatalogError('Invalid catalog configuration')
    if 'resolution' in doc and not isinstance(doc['resolution'], dict):
        raise CatalogError('Invalid catalog resolution configuration')
    from .catalog_cache import cache_options, CachedProvider
    defaults = cache_options(doc.get('cache', {}))
    providers = []
    for entry in doc['providers']:
        if not isinstance(entry, dict):
            raise CatalogError('Invalid catalog provider configuration')
        entry = dict(entry)
        options = cache_options({**defaults, **entry.pop('cache', {})}) if isinstance(entry.get('cache', {}), dict) else None
        if options is None:
            raise CatalogError('Invalid provider cache configuration')
        if entry.get('type') == 'unity_catalog':
            from .unity_catalog import UnityCatalogProvider
            providers.append(CachedProvider(UnityCatalogProvider(entry), options, disk_path=path.parent / '.dbt-skills-catalog-cache' / (entry['id'] + '.db')))
        elif entry.get('type') == 'openmetadata':
            from .openmetadata import OpenMetadataProvider
            providers.append(CachedProvider(OpenMetadataProvider(entry), options, disk_path=path.parent / '.dbt-skills-catalog-cache' / (entry['id'] + '.db')))
        elif (set(entry) == {'id', 'type', 'path', 'scope'} and entry['type'] == 'file'
              and isinstance(entry['path'], str) and 1 <= len(entry['path']) <= 4096):
            providers.append(FileCatalogProvider(entry['id'], path.parent / entry['path'], entry['scope']))
        else:
            raise CatalogError('Invalid or unsupported catalog provider configuration')
    resolver = CatalogResolver(providers, doc.get('resolution'))
    resolver.config = {'document': str(path), 'revision': revision}
    return resolver
