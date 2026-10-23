# Semantic design memory

Approved direction: provide the host agent context to create a complete data-model
design, not SQL generation machinery. Extend human-owned design decisions with
optional bounded answers to existing semantic questions. Every answer carries a
rationale and inherits the record's intent, asset, scope, attribution and evidence.
Reuse only exact current matches; stale/conflicting/ambiguous records never supply
active answers. Attach provenance to questions and keep review requirements visible.
Narrative statements never become catalog facts, proven normal forms or SQL rules.

Implementation: shared design_decisions validates optional unique question-code /
answer / rationale entries; proposal preparation allows only active question codes;
model_planning annotates matching questions. Old files remain compatible. CLI and
MCP use the same core. No automatic writes or standards promotion.

Checks: roundtrip/read-only, invalid/duplicate/oversized answers, inactive questions,
stale/conflicting/ambiguous decisions, CLI and real MCP save/refresh/reuse. Full
suite, independent review, docs and CI before completion. No merge/release.
