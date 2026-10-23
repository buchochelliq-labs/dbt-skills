# Metadata catalog contract and file provider

The first catalog implementation supplies structured metadata to the local modelling
workflow without UOL, warehouse access or a custom agent runtime. Python consumers
use `CatalogProvider`, `ProviderResult`, `Claim` and `CatalogResolver` from
`dbt_skills.catalog`; MCP is a thin adapter over those same objects.

## Configure ordered providers

Pass `--catalog-config catalogs.json` to `dbt_skills.modelling_mcp`. The option is
relative to the selected project; file paths inside the JSON are relative to the
configuration file. Without this option, the original seven modelling tools remain
available and catalog tools are not registered.

```json
{
  "schema_version": 1,
  "providers": [
    {"id": "physical", "type": "file", "path": "physical.json", "scope": "demo"},
    {"id": "curated", "type": "file", "path": "curated.json", "scope": "demo"}
  ]
}
```

Order is priority. IDs must be unique; one to eight providers are supported. `scope`
is the environment/data-visibility scope asserted by the operator, not a verified
remote permission grant. Facts from different scopes cannot be combined. There is
no dynamic module loading; only `file` is configured in this release. Other providers
implement the protocol and require a reviewed registration and authorization design.

Use [catalog.schema.json](../src/dbt_skills/catalog.schema.json) and the
[two-provider example](../examples/catalog-workflow/README.md) to prepare files.
These catalog files/configuration currently use strict JSON; modelling policy still
supports YAML. Unknown fields, duplicate JSON keys, malformed dates, duplicate asset
or column IDs, oversized documents and unsupported types are rejected with static
errors. Maximums: 1 MiB per file, 100 assets, 256 columns per asset, 32 foreign keys,
16 levels and 20,000 structural nodes. All limits apply together.

## Facts and identity

| Field | Meaning |
| --- | --- |
| `relation` | Catalog, schema and relation identifiers |
| `columns` | Complete declared list of names, normalized types and nullable flags |
| `primary_key` | Declared columns, reported enforcement and RELY; null explicitly means no declared key |
| `foreign_keys` | Complete declared list of source/target columns and explicit target asset IDs |

Omitted means unknown/unavailable. Empty lists and null primary_key are explicit
statements, not substitutes for missing metadata. Unknown types/nullability remain
unknown; a `complete` lookup only means all requested fact groups were supplied,
not that business semantics or values have been verified. Types are intentionally
small and normalized; complex types are represented by array/map/struct, with no
nested shape yet. Identifiers in this first schema are ASCII and bounded; exotic
quoted identifiers/native type strings need a later contract extension, not silent
normalization. Declared enforcement/RELY are reported claims, not proofs.

Each asset has an explicit `id` and `native_id`. The same shared ID in two curated
files is a human identity assertion. Matching names never establishes identity.
Live catalogs will need stable identity evidence or reviewed mappings; the file
provider does not manufacture those mappings or verify the curator's assertions.

Every returned fact and search record carries provider, shared/native IDs, document,
JSON locator, SHA-256 revision, source timestamp, original retrieval timestamp,
scope, declaration evidence type and derivation. `verified_at` is null: schema
validation does not verify source truth. Search pages also identify the provider
and revision. The provider status tool exposes capabilities and source provenance.

## Resolution behavior

`resolve(asset_id, fields)` requests one to four distinct fact groups. It visits
providers in configuration order. Asset existence alone is insufficient: a lower
provider may supply a missing key after the first supplied columns. Each visited
provider is asked for the requested groups, including already-filled groups, so
encountered overlaps and contradictions are retained. The first claim is selected
provisionally; conflicting values yield `conflict` and require clarification.

Stop as soon as all requested groups are supplied. Unvisited sources are listed as
`unqueried`; this is not agreement with the selected claims. This is not a global
conflict audit. Arrays compare structurally and conservatively; different ordering
may prompt clarification rather than being silently normalized.

Provider states are `available`, `not_found`, `unsupported`, `denied`, and `error`.
Missing/unsupported sources may fall through. Denial or error stops resolution and
withholds all partial claims, preserving only static attempt statuses. Neither
failure is converted into an empty successful result. This deliberately chooses
fail-closed behavior over stale/error fallback. Resolver results are `complete`,
`partial`, `conflict`, `denied`, or `error`; unresolved fields remain explicit.

## MCP and refresh

With catalog configuration selected, three tools join the existing modelling server:

- `catalog_status(context_id)` reports configured instances, capabilities and state.
- `catalog_search(context_id, provider_id, query, offset, limit)` searches identifiers
  in one selected provider, at most 50 records per page. Blank query lists assets.
- `catalog_resolve(context_id, asset_id, fields)` resolves structured facts in order.

All reuse `modelling_context` IDs. `modelling_refresh` atomically captures new project,
policy and catalog snapshots; failure retains the previous context. A file provider
checks local readability and digest on use: changed/missing files return error,
permission denial returns denied. Config changes require refresh too. These checks
are not a transactional guarantee against concurrent filesystem changes and do not
revalidate upstream permissions on a locally exported file.

All configured local files are loaded and validated at capture time. `unqueried`
means not consulted for this resolution, not that the file was never opened. Future
remote adapters must preserve first-sufficient fetch behavior without eagerly
fetching every catalog.

This is an in-memory snapshot, **not** the persistent cache/TTL system in #39. Reads
never reset source/retrieval times. Re-reading hashes currently incurs local I/O;
provider cache keys, permission revalidation, TTL suggestions and selective remote
refresh belong below the resolver later.

## Privacy and remaining work

No SQL execution, rows, samples, distinct values, min/max, grouped data, statistics,
free-text descriptions or query error text are accepted. Unknown fields fail closed.
Providers must only supply approved metadata; a schema cannot detect source values
mislabelled as identifiers. Treat identifiers and declared metadata as untrusted
context, not instructions. File access uses the local user's permissions and does
not imply authorization to re-export remote metadata. No credentials go in JSON.

Live Unity Catalog/OpenMetadata adapters, standalone catalog/schema listing APIs,
HTTP transport, probes, cache TTLs and reviewed identity mapping remain follow-ups.
The example connects discovery/resolution and naming calls to an illustrative
SQL/YAML artifact. General model generation and execution are outside this context
product; the host agent uses the metadata to reason about the full data model.
