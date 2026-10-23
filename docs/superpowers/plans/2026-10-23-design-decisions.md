# Reuse explicit design decisions during planning

Spec: #16/#37 and docs/ARCHITECTURE.md learning/authority boundaries. Base merged #50.
Human-owned JSON file selected by CLI/server operator, no implicit file discovery.
Records capture intent, selected asset, exact scope, grain/history choices, rationale,
attribution/time and evidence fingerprints. File metadata is not authentication.

1. Bounded strict loader and per-asset decision context emitted by planner. Evidence
   binds policy, manifest, catalog configuration and normalized resolved facts,
   excluding retrieval/verification timestamps so reads do not invalidate identical
   facts or reset freshness. Preserve existing source evidence separately.
2. Reuse unique exact intent/asset/scope records only when fingerprints match. Explicit
   conflicting request values, duplicate applicable records and stale revisions ask
   questions; do not silently promote/override. Grain/history remain assertions and
   still undergo column/history checks. Normal-form/principle questions stay open.
3. CLI --design-decisions and operator-selected MCP startup file; pinned context,
   changed-file checks, refresh. No MCP file paths/write/approval or auto-learning.
   Return auditable provenance for reused record. Emit a copyable decision context;
   humans/host save reviewed choices using their normal file-review workflow.
4. Tests core, stale/conflict/duplicate/malformed/bounds, CLI and real stdio; docs,
   full suite, independent review, focused PR and CI. No merge/tag/release.

This slice reuses grain/history, not arbitrary semantic prose or exceptions. Wider
standards changes and authenticated host approvals remain separate.
