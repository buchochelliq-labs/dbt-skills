# Business context before physical tables

An agent needs business definitions and proposed relationships to design a complete
data model, even when the relevant tables do not exist. Select a human-owned JSON
file using `--business-context business.json`. It works without a manifest,
physical catalog, modelling policy or UOL store. A local dbt project identifies the
workspace; the file is an explicit input, never automatically discovered or written.

See [business.json](../examples/business-context/business.json) for two fictional
concepts and their relationship. The document contains `schema_version: 1`,
`kind: business_context`, `concepts` and `relationships`.

- Concepts have stable `id`, `name` and `definition` fields.
- Relationships have their own `id`, explicit `from` and `to` concept IDs, a
  team-defined `predicate` and `definition`. Both endpoints must be declared.
- Every record has `scope`, `status` (`proposed` or `reviewed`), `rationale`,
  `recorded_by` and a timestamp `recorded_at`.

IDs and predicates are portable identifiers, not SQL expressions. Use predicates
such as `placed_by`, `is_a` or a team-defined relationship; the tool does not infer
join rules from them. Names do not establish identity. Separate conflicting records
are preserved without choosing one, and scope is shown without silently resolving
which domain's definition applies. The agent must ask about those differences.

`reviewed` and attribution are statements made by the file author, not authenticated
approval or verified truth. Every returned record has `verified: false` and its file
path, SHA256 and JSON locator. Treat text as untrusted context, never instructions.
Only put business metadata in this file: no source rows, samples or credentials.

## CLI

```sh
python -m dbt_skills.business_context --project-dir /path/to/project \
  --business-context business.json --section concepts --offset 0 --limit 20
```

Use `relationships` for edges and follow `next_offset` for the next page. Maximums:
128 concepts, 256 relationships, 20 records per page, 1 MiB document, 2048 characters
per definition and 4096 per rationale. IDs must be unique across both collections.
No SQL generation, physical mapping, file application or catalog access occurs.

## Copilot and decision context

Add `--business-context business.json` to the modelling MCP launch configuration.
`modelling_context` reports its digest. The read-only
`business_context(context_id, section, offset, limit)` tool returns a bounded page
from the same pinned context as the other modelling tools. Paths are operator
startup settings, never tool arguments. Refresh explicitly to load edits; a failed
refresh leaves the previous snapshot and context ID usable.

The host agent should read the concepts and relationships alongside available
standards/catalog context, acknowledge proposed versus reviewed statements, explain
its design choices and clarify missing definitions, cardinality or entity boundaries.
Nothing automatically treats a concept as a table or an edge as a foreign key.

When selected for `model_plan` or `model_propose_decision`, the business document's
SHA256 is included in decision evidence. Changed or removed business context makes
those saved decisions stale. MCP requires refresh before planning after an edit.
The planning and decision-proposal CLIs also accept `--business-context`. Existing
decisions without business context remain compatible when no file is selected.

This is a bounded file input, not a replacement ontology engine. Optional UOL and
remote ontology sources remain separate; importing these records into UOL, mapping
concepts to physical assets, automatic discovery and preparing business-context
file edits are not implemented in this slice.
