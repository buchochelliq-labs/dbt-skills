# ADR 0001: retain encrypted SQLite-family storage

Date: 2026-10-23. Status: recorded direction following the maintainer's instruction
to continue with the recommendations; repository integration remains subject to PR review.

## Decision

Retain SQLCipher as the canonical local persistence technology. Use SQLite lexical
search and indexed relationships as the first retrieval baseline when a concrete
workflow needs improvement. Do not implement multiple production backends now.

Keep catalog-provider selection independent of persistence and retrieval. Core code
owns project scope, provenance, conflicts/quarantine, permission freshness, reviewed
standards and decisions. Human records must not inherit provider-cache eviction.
UOL remains optional. No source rows, generated SQL or execution runner is added.

The current ontology and catalog cache remain distinct stores/components. This ADR
does not merge them into a universal database or claim all spike functionality is
implemented. Existing ontology search is not relabelled as a shipped FTS5 feature.

## Alternatives and evidence

The [selection comparison](../../experiments/offline_backends/SELECTION.md) records
advantages, drawbacks and pinned-version evidence for SQLite, optional Cognee,
direct Ladybug, DuckDB and Cognee-owned persistence/retrieval.

SQLCipher earned the default through existing encryption/key-management integration,
competitive project-shaped benchmarks and observed generation recovery. The latest
small lexical/path probe demonstrates useful baseline behavior and explicit limits,
not real-user relevance quality or general engine superiority.

Cognee remains a credible optional retrieval candidate: graph-only ingestion,
source ownership, deletion and explicit dataset permissions passed the tested cases.
The tested setup also stores plaintext in input, relational and graph files, and
graph-only deletion depends on pre-staged tokenizer artifacts. Complete protection,
retrieval benefit and net maintenance reduction are not established.

Direct Ladybug and DuckDB have not demonstrated sufficient benefit for the current
workflow. Tested FTS and process-ownership findings are version-specific, not blanket
rejections of those engines. RDF/vector options require an actual interoperability
or semantic-retrieval need before further implementation work.

## Consequences

- Stop expanding the backend spike. Preserve its evidence and limitations.
- Prefer one encrypted transactional store for a component's canonical data and
  indexes where practical. A separate projection must earn its additional build,
  activation, revision and cleanup complexity.
- Keep future interfaces capability-specific: bounded search and evidence paths,
  explicit generations, completeness and unsupported states. Do not expose generic
  database query execution to the agent or build an unused abstraction framework.
- Optional adapters must demonstrate encryption coverage, policy/generation parity,
  recovery and supported-platform behavior before adoption. These are conditional
  adoption gates, not a prerequisite for continuing with the existing backend.
- No automatic migration, new dependency, merged PR, tag or release follows from
  this decision.

## Reconsider when

Representative user queries establish a retrieval gap, an alternative demonstrably
improves it after lifecycle costs, and it satisfies the same evidence and protection
contract. Cognee can also earn adoption by removing more maintenance than integration
adds. Reconsider DuckDB for a concrete analytical workload or RDF storage for a real
RDF/SPARQL interchange requirement.

## Next product milestone

Verify an individual Copilot/VS Code data-model design session using the shared tools,
including clarification, missing/conflicting evidence and a scoped exception. Use
[the host acceptance script](../COPILOT_ACCEPTANCE.md). Protocol tests are supporting
evidence and do not establish live UI behavior.
