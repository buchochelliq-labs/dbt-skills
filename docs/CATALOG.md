# Metadata catalog providers

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
no dynamic module loading; `file` and `unity_catalog` are configured explicitly.
See [Unity Catalog setup](UNITY_CATALOG.md) for remote metadata, authentication,
explicit asset mappings and refresh semantics.

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

Remote observations now use a bounded cache with optional encrypted persistence.
Reads never reset source/retrieval times. See [cache configuration and freshness](CATALOG_CACHE.md)
for TTLs, permission revalidation, eviction and review-only TTL suggestions.

## Privacy and remaining work

No SQL execution, rows, samples, distinct values, min/max, grouped data, statistics,
free-text descriptions or query error text are accepted. Unknown fields fail closed.
Providers must only supply approved metadata; a schema cannot detect source values
mislabelled as identifiers. Treat identifiers and declared metadata as untrusted
context, not instructions. File access uses the local user's permissions and does
not imply authorization to re-export remote metadata. No credentials go in JSON.

The Unity Catalog HTTP adapter is implemented; live-provider validation, an
OpenMetadata adapter and additional reviewed identity mappings remain follow-ups.
The example connects discovery/resolution and naming calls to an illustrative
SQL/YAML artifact. General model generation and execution are outside this context
product; the host agent uses the metadata to reason about the full data model.

## Project membership, delta sync and quarantine

The modelling MCP server and shared planner wrap catalog resolution in a
`ProjectCatalog` boundary. Only physical relations declared as sources in the
validated project manifest, or models/seeds/snapshots produced by the selected
project, are eligible. Ephemeral models are excluded. Missing/mismatched manifests
and unresolved identifiers grant no scope. Foreign-key endpoints do not widen it.

A provider supplies local `project_bindings()` metadata: shared asset ID to an
explicit relation (or null for curated facts that inherit a shared mapping), with
a stable configuration/fact signature. This method must not perform remote reads.
Providers without bindings receive no project access. Scoped search is opt-in via
`search_scoped`; otherwise it is unsupported. The low-level resolver remains a
provider contract, so Python project workflows should use `scope_catalog` just as
the planner and MCP do.

Two different concrete relations for one shared asset identity cause **quarantine**,
even when both relations belong to the project. Quarantined identities are excluded
from normal search, resolution, remote fetches and design evidence. `catalog_status`
reports the count; `catalog_quarantine` returns a bounded review page with the
configured claims, provider IDs, binding hashes and configuration provenance. These
are local mapping diagnostics, not remotely fetched table facts. Other assets remain
usable. Correct the configuration or local catalog declaration and sync to release
an identity; provider priority never silently resolves identity ambiguity.

`catalog_sync(context_id)` re-reads selected inputs and replaces the context ID.
It reports added, changed, removed and quarantined asset IDs, unchanged count and
per-delta resolution status. Only added/changed eligible assets are fetched, through
normal ordered resolution. Unchanged Unity Catalog observations retain their
original timestamps/provenance; removed identities lose access. Changes to mappings,
provider order, scope or relevant local facts invalidate reuse. Changed credentials
prevent observation transfer. Expired cached observations are also refreshed; see [cache lifecycle](CATALOG_CACHE.md).

After adding a source, regenerate the dbt manifest using existing dbt tooling, then
invoke `catalog_sync`. Include its explicit catalog mapping if needed. YAML edits
alone do not establish resolved physical identity. There is no background watcher or
automatic dbt execution; the host agent can invoke sync after artifact regeneration.
Initial reads remain lazy. Use `modelling_refresh` to discard all observations and
retry/recheck remote metadata, including failures for unchanged assets. Delta sync
does not revalidate unchanged remote permissions or schema.

## Configurable conflict resolution

The optional catalog configuration `resolution` object defaults to:

```json
{
  "planning_mode": "conservative",
  "type_compatibility": "compatible",
  "provider_priority": {"enabled": false, "order": []}
}
```

See [catalog configuration schema](../src/dbt_skills/catalog-config.schema.json),
which is separate from the provider metadata document schema. Runtime also checks
provider-specific options and cross-field constraints.

By default, the first sufficient providers supply facts; encountered conflicts
remain unresolved, and unqueried providers imply no agreement or disagreement.
Disabled priority order has no effect. Enable priority with an order containing
**every configured provider ID exactly once** to read all active providers in that
order and select the first claim per field. Claims, provenance and conflicts remain
visible in `resolved_conflicts` and `unresolved_conflicts`. Resolution is an operator
selection policy, not proof of correctness. Any encountered denial/error clears all
facts; priority cannot override project scope, scope mismatch or identity quarantine.
Application-disabled providers stay disabled during planning.

`conservative` planning stops candidate generation on unresolved catalog conflicts.
`partial` planning returns unaffected entities and `withheld_assets`, with affected
relationship targets marked `blocked_conflict`. Permissions still block the entire
response. `type_compatibility` controls advisory relationship type warnings; see
[model planning](MODEL_PLANNING.md). Neither setting executes casts or verifies joins.

## Read-only resolution previews and native type evidence

`catalog_resolution_preview` takes `context_id` and a typed `request` with
`asset_ids` (1–8), `fields` and candidate `settings` in the existing resolution
format. It reports current/proposed facts, retained conflicts, missing fields,
unqueried providers, attempt traces and planner withholding. It never applies
settings. A denied/error provider or out-of-project asset clears both result
sets for the whole request. Conservative mode withholds all selected entities
on unresolved conflict; partial mode withholds conflicted entities. Unknown
providers imply neither agreement nor disagreement. Failed resolution outputs
include the same effective policy used on success.

The normalized column `type` enum remains unchanged. Optional `type_descriptor`
is version 1 evidence: required `schema_version: 1`, `native` (1–1024 characters),
`family` (the normalized enum), optional `parameters` (`precision`, `scale`,
`length`, integers 0–65535), optional `name`, and optional `children` descriptors.
Only these keys are allowed. Limits are four child levels, 32 children per node
and 64 total nodes. File catalogs may supply structured nesting; Unity Catalog
and OpenMetadata preserve their native type spelling, with decimal parameters
when available. Native syntax is retained as untrusted evidence, not parsed into
SQL or executed. Unknown grammar remains unverified.

Planning preserves descriptors and provenance through `native_type_evidence`.
Normalized exact matching remains a normalized-label assessment. Different
native descriptors add a review warning even when normalized labels match;
identical descriptors are only an `unverified_match`. This does not prove native
equivalence, casting safety or join safety. The adapters do not promise complete
provider-specific nested parsing.
