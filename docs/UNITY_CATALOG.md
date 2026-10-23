# Unity Catalog metadata context

The `unity_catalog` provider retrieves relation and column declarations for explicitly
mapped tables. The same provider works through the Python catalog resolver, planner
CLI and modelling MCP server; no UOL store is required. It never runs SQL, queries
rows, requests samples or performs warehouse profiling.

## Configuration

Select the config with `--catalog-config catalogs.json`. This example places Unity
Catalog first and a hand-written catalog second:

```json
{
  "schema_version": 1,
  "providers": [
    {
      "id": "uc",
      "type": "unity_catalog",
      "scope": "development",
      "host": "https://your-workspace.cloud.databricks.com",
      "token_env": "DBT_CONTEXT_UC_TOKEN",
      "assets": {"urn:example:customer": "demo.xyz.customers"}
    },
    {"id": "curated", "type": "file", "scope": "development", "path": "curated.json"}
  ]
}
```

Set the named environment variable in the local process running the CLI/MCP server.
Use an operator-managed bearer token with appropriate metadata permissions; the
adapter does not acquire, refresh or store credentials on disk. Do not put token
values in JSON or agent prompts. Configure only trusted HTTPS workspace origins;
paths, embedded credentials, query strings and redirects are rejected. System TLS
verification and standard Python proxy settings apply.

Mappings assert identity between the shared asset ID and the selected three-part
Unity Catalog name. One to 100 unique mappings are supported, using the portable
ASCII identifier subset of the catalog contract. Facts report the returned table
UUID as `native_id`; replacing a table under the same name changes its evidence
fingerprint. Mappings are human assertions, not automatic cross-catalog matches.

## Retrieval and priority

Reads use the [official Get a table API](https://docs.databricks.com/api/uc-tables/v1/get-table).
The adapter validates the returned identity and extracts only catalog/schema/table
names and columns' names, normalized types and nullable flags. Unknown types remain
`unknown`; absent columns remain unavailable. Nested type shape and decimal
precision are not currently represented. Keys and relationships are unsupported
by this initial adapter, allowing subsequent file providers to supply them.

Responses are bounded to 1 MiB, 256 columns, 16 levels and 20,000 structural nodes,
with a 10-second socket timeout. Comments, SQL definitions, properties, literal
values, raw native type strings and backend error bodies never reach agent output
or the in-memory fact snapshot. The HTTP metadata response is parsed locally to
perform this projection. No raw response is written to disk or logged.

An unmapped asset or unsupported-only request needs no remote call or credential.
For applicable reads, missing/changed credentials and HTTP 401/403 stop resolution;
404 records `not_found` and allows fallback. A 404 is not proof of global absence
or permission. Other HTTP/network/validation errors stop resolution without partial
claims or raw error text. Browse-only responses are withheld. Provider priority
and encountered-conflict rules remain those of the shared resolver.

## Provenance and refresh

Each fact includes provider/scope, shared asset ID, returned table UUID, endpoint,
locator, SHA-256 of the projected facts and UUID, and original retrieval time.
The hash is a **projection fingerprint**, not an upstream revision or whole-response
hash. `source_at` and `verified_at` remain null. No metadata declaration proves
business semantics, key enforcement, normal form or data quality.

Retrieval is lazy: the first applicable read of each mapped asset is pinned in the
provider instance, including negative/error outcomes. Repeated reads do not make
network calls. This is a set of per-asset observations, not an atomic remote catalog
snapshot. `modelling_refresh` creates new providers; the next read fetches again.
CLI invocations create fresh providers. Failed reads require refresh before retry.

Pinned metadata does not revalidate remote permissions or detect remote changes.
Changing/removing the local token blocks reuse immediately; permission changes
behind an unchanged token are visible only on a fresh retrieval. The status tool
reports configuration/credential readiness, not a remote authorization check.
Use short sessions and explicit refresh when freshness or access changes matter.
Persistent caching, TTL configuration/recommendations and cross-session reuse are
not implemented here. No TTL is silently chosen or extended.

## Current limits and validation

Catalog-wide search is explicitly `unsupported`; callers select configured shared
asset IDs. Additional catalog adapters, remote discovery, key/relationship extraction,
and automatic authentication refresh remain outstanding. Automated tests cover
HTTP outcomes, filtering, provenance, fallback and MCP refresh with simulated
responses. No live Databricks workspace or live Copilot UI has been validated.

## Project boundary

In MCP and planning, configured mappings are additionally intersected with the
validated project manifest. Configuration alone cannot expand the agent's scope.
See [project membership and quarantine](CATALOG.md#project-membership-delta-sync-and-quarantine)
for delta sync after source additions. Ambiguous mappings are quarantined before
HTTP access; independent project assets continue to work. Normal refresh discards
observations; delta sync retains unchanged observations without resetting freshness.
