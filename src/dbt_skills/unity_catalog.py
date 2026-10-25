"""Bounded Unity Catalog metadata reads. No SQL, row access or raw response output."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from threading import RLock
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

from .metadata_types import native_descriptor

from .catalog import (CatalogError, Claim, ProviderResult, _identifier, _fields,
                      _search_args, _validate_facts, _pairs, _MAX_BYTES)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_TYPES = {'STRING': 'string', 'CHAR': 'string', 'VARCHAR': 'string',
          'BYTE': 'int64', 'SHORT': 'int64', 'INT': 'int64', 'LONG': 'int64',
          'FLOAT': 'float64', 'DOUBLE': 'float64', 'DECIMAL': 'decimal',
          'BOOLEAN': 'boolean', 'DATE': 'date', 'TIMESTAMP': 'timestamp',
          'TIMESTAMP_NTZ': 'timestamp', 'BINARY': 'binary', 'ARRAY': 'array',
          'MAP': 'map', 'STRUCT': 'struct'}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class UnityCatalogProvider:
    capabilities = ('relation', 'columns')

    def __init__(self, entry):
        if set(entry) != {'id', 'type', 'scope', 'host', 'token_env', 'assets'}:
            raise CatalogError('Invalid Unity Catalog configuration')
        _identifier(entry['id'])
        _identifier(entry['scope'])
        host, token_env, assets = entry['host'], entry['token_env'], entry['assets']
        # An operator-selected HTTPS origin only, never a URL supplied by an agent.
        if not isinstance(host, str) or len(host) > 2048 or re.fullmatch(r'https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?', host) is None:
            raise CatalogError('Unity Catalog requires an HTTPS origin')
        try:
            origin = urlsplit(host)
            if not origin.hostname or origin.port == 0:
                raise ValueError()
        except ValueError:
            raise CatalogError('Invalid Unity Catalog origin') from None
        if not isinstance(token_env, str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', token_env) is None:
            raise CatalogError('Select a token environment variable name')
        if not isinstance(assets, dict) or not 1 <= len(assets) <= 100:
            raise CatalogError('Configure one to one hundred explicit asset mappings')
        for asset_id, native in assets.items():
            _identifier(asset_id, asset=True)
            if not isinstance(native, str) or len(native) > 256 or len(native.split('.')) != 3:
                raise CatalogError('Use a three-part table identifier')
            for part in native.split('.'):
                _identifier(part)
        if len(set(assets.values())) != len(assets):
            raise CatalogError('Duplicate Unity Catalog table mappings')
        self.id, self.scope, self.host = entry['id'], entry['scope'], host
        self._assets, self._token_env = deepcopy(assets), token_env
        self._token = os.environ.get(token_env)
        self.revision = _digest(entry)
        self.retrieved_at = datetime.now(timezone.utc).isoformat()
        self._results, self._lock = {}, RLock()

    def project_bindings(self):
        return {asset_id: {'relation': dict(zip(('catalog', 'schema', 'name'), native.split('.'))),
                           'signature': {'host': self.host, 'scope': self.scope, 'token_env': self._token_env}}
                for asset_id, native in self._assets.items()}

    def carry_observations(self, previous, allowed):
        if not isinstance(previous, UnityCatalogProvider):
            return
        if (self.host, self.scope, self._token_env, self._token) != (previous.host, previous.scope, previous._token_env, previous._token):
            return
        with previous._lock:
            self._results = {a: deepcopy(result) for a, result in previous._results.items()
                             if a in allowed and self._assets.get(a) == previous._assets.get(a)}

    def cache_identity(self):
        # The credential is an in-memory isolation key only; never returned or persisted.
        return (self.id, self.host, self.scope, self._token_env, self._token)

    def cache_access(self):
        return self._access()

    def fetch_fresh(self, asset_id, fields):
        _identifier(asset_id, asset=True)
        _fields(fields)
        if asset_id not in self._assets:
            return ProviderResult('not_found')
        if not set(fields).intersection(self.capabilities):
            return ProviderResult('unsupported')
        if self._access() != 'available':
            return ProviderResult('denied')
        result = self._retrieve(asset_id)
        return ProviderResult(result.status, tuple(c for c in result.claims if c.field in fields))

    def _access(self):
        token = os.environ.get(self._token_env)
        if not token or token != self._token or len(token) > 8192 or not token.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in token):
            return 'denied'
        return 'available'

    def describe(self):
        # This describes configuration readiness, not remote permission verification.
        return {'id': self.id, 'type': 'unity_catalog', 'scope': self.scope,
                'status': self._access(), 'capabilities': list(self.capabilities),
                'document': self.host, 'revision': self.revision, 'source_at': None,
                'retrieved_at': self.retrieved_at, 'verified_at': None}

    def search(self, query, *, offset=0, limit=20):
        _search_args(query, offset, limit)
        return {'status': 'unsupported', 'assets': [], 'next_offset': None}

    def fetch(self, asset_id, fields):
        _identifier(asset_id, asset=True)
        _fields(fields)
        with self._lock:
            if asset_id not in self._assets:
                return ProviderResult('not_found')
            if not set(fields).intersection(self.capabilities):
                return ProviderResult('unsupported')
            if self._access() != 'available':
                return ProviderResult('denied')
            if asset_id not in self._results:
                self._results[asset_id] = self._retrieve(asset_id)
            result = self._results[asset_id]
            return ProviderResult(result.status, tuple(deepcopy(c) for c in result.claims if c.field in fields))

    def _retrieve(self, asset_id):
        native = self._assets[asset_id]
        endpoint = self.host + '/api/2.1/unity-catalog/tables/' + native
        request = Request(endpoint + '?include_delta_metadata=false&include_browse=false&include_manifest_capabilities=false',
                          headers={'Authorization': 'Bearer ' + self._token, 'Accept': 'application/json'})
        try:
            with build_opener(_NoRedirect()).open(request, timeout=10) as response:
                raw = response.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise CatalogError('Metadata response exceeds bounds')
            doc = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(doc, dict):
                raise ValueError()
            pending, count = [(doc, 0)], 0
            while pending:
                value, depth = pending.pop()
                count += 1
                if depth > 16 or count > 20000:
                    raise ValueError()
                if isinstance(value, dict):
                    pending.extend((v, depth + 1) for v in value.values())
                elif isinstance(value, list):
                    pending.extend((v, depth + 1) for v in value)
            if doc.get('browse_only', False) is not False:
                return ProviderResult('denied')
            relation = {k: doc[source] for k, source in
                        [('catalog', 'catalog_name'), ('schema', 'schema_name'), ('name', 'name')]}
            if '.'.join(relation.values()) != native or doc.get('full_name', native) != native:
                raise ValueError()
            table_id = doc['table_id']
            if not isinstance(table_id, str) or re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}', table_id) is None:
                raise ValueError()
            facts = {'relation': relation}
            if 'columns' in doc:
                if not isinstance(doc['columns'], list) or len(doc['columns']) > 256:
                    raise ValueError()
                facts['columns'] = [{'name': c['name'], 'type': _TYPES.get(c.get('type_name'), 'unknown'),
                                     'nullable': c.get('nullable')} for c in doc['columns']]
            for column, upstream in zip(facts.get('columns', []), doc.get('columns', [])):
                column['type_descriptor'] = native_descriptor(upstream.get('type_text', upstream.get('type_name', 'unknown')), column['type'])
            _validate_facts(facts)
            retrieved = datetime.now(timezone.utc).isoformat()
            revision = _digest({'table_id': table_id, 'facts': facts})
            return ProviderResult('available', tuple(Claim(field, value, {
                'provider': self.id, 'asset_id': asset_id, 'native_id': table_id,
                'document': endpoint, 'locator': '/columns' if field == 'columns' else '/',
                'revision': revision, 'source_at': None, 'retrieved_at': retrieved,
                'verified_at': None, 'scope': self.scope, 'evidence_type': 'declaration', 'derivation': []
            }) for field, value in facts.items()))
        except HTTPError as error:
            status = 'denied' if error.code in (401, 403) else ('not_found' if error.code == 404 else 'error')
            error.close()
            return ProviderResult(status)
        except Exception:
            # No backend bodies, URLs from errors, credentials or exception strings escape.
            return ProviderResult('error')
