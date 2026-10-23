# Unity Catalog context adapter

Implement a bounded read-only adapter through the existing CatalogProvider contract.
Explicit operator mappings, HTTPS bearer environment credentials, relation/column
projection, stable identity and provenance, ordered curated fallback, no SQL or rows.
Lazy per-asset observations remain pinned until refresh. Search and keys unsupported
in this slice; persistent TTL cache is separate work. See UNITY_CATALOG.md for limits.

- [x] Tests for configuration, projection, provenance, missing/denied/error outcomes.
- [x] Provider and config registration without host-specific planner logic.
- [x] MCP refresh integration and independent review; fix inapplicable-provider auth.
- [ ] Full suite and cross-platform CI; publish focused PR without merging.
