# OpenMetadata catalog adapter

The `openmetadata` provider reads schema declarations for explicitly mapped tables.
It uses `GET /api/v1/tables/name/{fqn}?fields=columns&include=non-deleted` on an
operator-selected HTTPS origin, with a Bearer token from the named environment variable.
No request occurs while loading configuration or describing provider readiness.

```json
{
  "schema_version": 1,
  "providers": [{
    "id": "om",
    "type": "openmetadata",
    "scope": "dev",
    "host": "https://metadata.example.com",
    "token_env": "OPENMETADATA_TOKEN",
    "assets": {"customers": "warehouse.demo.xyz.customers"}
  }]
}
```

Use existing project-scoped catalog resolution (`scope_catalog`): the database,
schema and table portion must match a relation in the selected dbt manifest.
The service prefix remains part of the binding fingerprint, so changing services
invalidates observations even if the physical relation name stays the same.
Unknown asset IDs and unsupported key-only requests make no remote requests.

The projection contains relation names, top-level column names, normalized types
and declared nullability. `NOT_NULL`/`PRIMARY_KEY` yield false, `NULL` yields true,
and absent/other constraints yield unknown (`null`). This is declaration evidence,
not a warehouse verification. Unknown types become `unknown`. Table UUIDs identify
native provenance; local hashes cover the projected facts. Descriptions, tags,
SQL definitions, samples, profiles and other response fields never become claims.

Safety bounds match Unity Catalog: 100 explicit mappings, 1 MiB response, 256
columns, 10-second request timeout, bounded parsed depth/node count, no redirects,
strict JSON and identifier checks. HTTP 401/403 terminate resolution with denial;
other errors withhold facts, and 404 permits fallback. Missing or changed tokens
are denied before transport. Keys and search are unsupported; configured curated
providers can supply missing keys. No SQL, list/search, sample, profiler, query,
lineage or write endpoints are called.

`CachedProvider` supplies the existing memory/disk cache policy, permission TTL,
project binding and explicit refresh behavior. The identity includes provider type,
origin, scope and credential identity; tokens are not returned as claims. Remote
permission revocation is observed on the next permission revalidation, not on every
cache hit. Disk cache requires existing protected project-scoped storage support.

Limitations: four simple unquoted FQN components only; no names containing embedded
dots or spaces, custom API path prefixes, nested-column flattening, key extraction,
OAuth refresh, service discovery or pagination. Catalog authorization does not prove
warehouse access. No live server or real credential was used in the tests; deployment
compatibility and permissions require an operator-authorized integration check.

Official references checked 2026-10-24:

- [Retrieve a Table](https://docs.open-metadata.org/v2.0.x/api-reference/data-assets/tables/retrieve): FQN endpoint, `/api` base path, Bearer authentication and optional fields.
- [Create a Table schema](https://docs.open-metadata.org/v1.12.x/api-reference/data-assets/tables/create): column datatype and constraint enum.

Run fake-transport tests with `PYTHONPATH=src python -m unittest discover -s tests -p test_openmetadata.py`.
