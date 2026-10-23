# Business concepts and relationship context

Goal: give the host agent context for a data model before catalog assets exist.
Keep UOL optional and avoid a new reasoning/storage engine. Add one explicit
human-owned JSON input, kind business_context, schema_version 1, with concepts and
relationships. Concepts: id, name, definition. Relationships: id, from, to,
predicate, definition. Both carry scope, status proposed/reviewed, rationale,
recorded_by/at. IDs and predicates are arbitrary bounded portable identifiers;
relationships must reference declared concepts. No name-based merging or inferred
physical joins. Conflicting statements remain separate records.

Implement bounded validation/load and paged section reads in business_context.py;
CLI selects project/document/section. Optional --business-context on modelling MCP
loads into the existing pinned snapshot, summary exposes digest, read-only
business_context tool pages concepts/relationships. Refresh rereads explicitly;
failed refresh retains previous context. No policy/catalog/manifest requirement,
SQL, automatic writes, data rows, authentication claims or UOL dependency.

Per-record provenance: file SHA256 + JSON locator, plus supplied attribution/status.
Text is untrusted metadata; reviewed is human-supplied, not verified/approved by tool.
Max 128 concepts, 256 relationships, 1 MiB document, 20 results/page, definition
2048, rationale 4096, scoped fields bounded. Reuse existing JSON reader/limits.

Tests: prephysical concepts, relationships, endpoint validation, duplicate/unknown
keys, bounds and safe errors; deterministic paging/provenance; real CLI and MCP
pin/refresh/failure/absent input behavior. Full suite and independent review. Publish
PR and check CI; do not merge/release.
