# Catalog cache and freshness

Unity Catalog metadata uses a bounded in-memory cache by default. Optional encrypted
local persistence supports reuse across process restarts without requiring UOL or
an OpenMetadata server. File catalogs remain a standalone offline option: they are
validated local documents, checked for changes on every use, rather than TTL cached.

Add `cache` at the catalog configuration root for defaults and/or on a Unity Catalog
provider for overrides. Other provider fields remain as described in
[Unity Catalog configuration](UNITY_CATALOG.md).

```json
{
  "storage": "disk",
  "ttl_seconds": null,
  "permission_ttl_seconds": 86400,
  "max_objects": 1000,
  "max_bytes": 67108864
}
```

This is the value of a `cache` object, not a complete catalog configuration.
`ttl_seconds: null` disables metadata expiry; integer lifetimes are 1–86400 seconds.
Permission lifetime is always finite. Defaults are provisional: memory storage,
3600-second metadata lifetime, 300-second permission lifetime, 1000 objects and
64 MiB of serialized payload. Provider overrides replace individual global settings.
Cache options do not change local file-provider validation.

## Retention, offline use and permissions

No metadata TTL means retained facts do not expire solely because of their age.
It does not mean permissions remain verified forever. Cached remote facts are usable
without a network request within both configured freshness and permission lifetimes,
provided the configured credential is still present and unchanged. After either
lifetime, remote verification must succeed before those facts are served again.
There is no stale-on-error fallback. A known denial or unavailable fresh response
invalidates persisted observations for that provider/project identity.

Thus this first remote-cache implementation supports bounded disconnected use, not
indefinite authorization while offline. Local file catalogs work independently of a
remote server. A broader explicit disconnected-use policy remains follow-up work in
[#60](https://github.com/buchochelliq-labs/dbt-skills/issues/60).

Cache hits preserve original retrieval timestamps and all claim provenance. A
successful remote read records a new observation; changing configuration to extend
a TTL does not reset the age of an existing observation. Credential changes, project
identity, provider host/scope, mapping changes and project membership isolate reuse.
Only project sources and produced relations are eligible; quarantine still applies.

## Capacity and storage

`max_objects` is 1–10000; `max_bytes` is 1024–1073741824. Limits apply independently
to each provider's memory cache and encrypted database. Least-recently-used entries
are evicted; an individual object larger than the budget is not retained. The byte
limit covers serialized payload, not SQLite pages, indexes or transient filesystem
allocation. Reads update usage without rewriting payloads or observation timestamps.

Disk mode writes `.dbt-skills-catalog-cache/<provider-id>.db` beside the catalog
configuration. Keep that directory out of version control. It reuses the existing
SQLCipher/native OS keyring storage primitives; there is no plaintext fallback and
no UOL service dependency. Tests substitute an in-memory key store; operators need
a working native keyring. Cache errors return unavailable evidence, never raw backend
errors, secrets or fabricated empty success.

## Context lifecycle and review

A context pins its observations. Expiry or eviction during its lifetime returns an
error instead of silently fetching different evidence. Call `catalog_sync` to rotate
the context and refresh added, changed, expired or evicted observations. Unchanged
fresh observations carry forward with original provenance. `modelling_refresh`
rotates the context and bypasses persisted entries on subsequent reads, allowing
explicit refresh even when metadata TTL is disabled. Removed or quarantined assets
cannot be served from the cache.

`catalog_status` exposes settings, bounded counters, latest fetch latency and expiry
counts. Repeated unchanged metadata-expiry fetches within a ten-minute observation
window can produce a `pending_review` TTL suggestion. Permission expiry and failures
suppress that suggestion. Acceptance means a human edits the provider configuration
and syncs; rejection requires no action. Suggestions never change configuration or
extend permission lifetime automatically. Cache reuse reduces remote round trips;
selective tool requests still control how much context reaches the agent.

Remaining #39 work includes per-fact-type lifetimes, richer cache diagnostics and
live-provider validation. This implementation has simulated HTTP and encrypted-store
regressions, not live Databricks or Copilot acceptance evidence.
