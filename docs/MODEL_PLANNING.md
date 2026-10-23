# Catalog-grounded design planning

Before generating SQL, use `model_plan(context_id, request)` in the modelling MCP
server configured with policy and catalogs. The same core is available from the CLI.
It assembles evidence and targeted questions; the host agent and human still interpret
business intent and decide the design. No additional model-provider runtime is required.

A request contains business `intent` and one to eight distinct `assets`. Each asset has
an explicit `asset_id`, optional `scope` dimensions matching the team's modelling rules,
optional asserted `grain` column names and optional `history`: `source_rows`, `current`
or `historical`. Scope and naming tokens remain team-defined; this tool does not invent
filenames or impose a universal staging/intermediate convention.

```json
{
  "intent": "Model customers and their orders",
  "assets": [
    {"asset_id": "urn:demo:xyz:customers", "scope": {"layer": "core"}},
    {"asset_id": "urn:demo:xyz:orders", "scope": {"layer": "core"}}
  ]
}
```

These IDs must exist in the selected catalogs. A relationship target is never fetched
implicitly: explicitly select it on the next request when it is relevant and authorized.
Provider order, first-sufficient resolution, scope checks and conflict handling come
from the existing catalog contract. Denial/error withholds all collected design evidence;
conflicts retain their provenance but block entity/relationship suggestions.

## What the report means

- **Entity candidates:** one per selected asset, not a claim that physical tables are
  the correct business entities. Declared primary keys suggest a grain for discussion.
  Caller-supplied grain is separately labelled and checked against column metadata;
  neither is verified against source rows.
- **Standards:** only rules with satisfied scopes are applied. Missing scope dimensions
  produce questions; incompatible overlapping style/normal-form targets are surfaced
  without silently preferring a rule. Principles remain explicit human review items.
- **Normalisation:** applicable targets trigger dependency questions. 3NF needs candidate
  key/functional-dependency reasoning; 4NF adds multivalued-dependency and lossless
  decomposition review; 5NF adds join-dependency review. No SQL shape or naming pattern
  certifies any normal form. The planner does not calculate a decomposition.
- **Relationships:** declared FK columns are checked against both selected endpoints.
  A match to a declared target primary key is labelled as such, not as proven uniqueness
  or safe join cardinality. Valid endpoints suggest reviewing separate entity models;
  business boundaries, optionality, cardinality and temporal alignment remain questions.
- **Existing design:** exact physical-relation matches identify dbt source candidates.
  Resource descendants identify existing models to consider reusing or changing. Ambiguous
  mappings are questions. Up to 100 source candidates and 100 existing models are returned
  per asset with truncation flags. Missing edges never imply no impact; column lineage is
  not inferred. No files are read for SQL contents or modified.

Full selected/conflicting catalog evidence retains its original provenance and freshness.
Reports are bounded to 1 MiB / 20,000 nodes; oversized reports fail explicitly rather than
silently dropping facts. Use fewer selected assets or a narrower policy. Text from policy,
intent and metadata remains untrusted evidence, not instructions.

## Local walkthrough

Using the repository's synthetic metadata-only example:

```sh
PYTHONPATH=src python -m dbt_skills.model_planning \
  --project-dir examples/catalog-workflow --target-path artifacts \
  --policy modelling.yml --catalog-config catalogs.json \
  --request design-request.json
```

The report suggests `customer_id` from the curated key declaration, preserves its
provenance, finds the existing customer model in the synthetic manifest and asks for
row grain, history, missing relationships and functional-dependency evidence for the
configured 3NF target. Exit 2 means clarification is needed, 0 means pending review,
and 1 means blocked/error; none means an approved design or validated warehouse.

Answer questions with the human. Grain/history/scope can be supplied on the next request;
other semantic answers still require human/host reasoning and a reviewed decision record.
This tool does not persist answers, promote learned standards, apply exceptions or mark
dependency evidence as proved. It does not parse arbitrary business prose into SQL.

Once the human has selected a supported source-row projection, use the existing
[prepare/review/apply/validate workflow](MODEL_DRAFTS.md). Joins, current/history transforms,
changes to existing files and automatic conversion of design answers remain follow-ups.
There is no automatic plan-to-apply shortcut and no warehouse execution.

## Reuse reviewed grain and history decisions

After discussing the questions, a human can save choices in an explicitly selected
`design-decisions.json`. Add `--design-decisions design-decisions.json` to the CLI
command above or to the MCP server launch arguments (policy and catalogs are required).
No file is auto-discovered or written by these tools. The host can prepare the file
for normal human review; the human controls whether the reviewed file is selected.

Copy an entity's complete `decision_context` object from the current report into
`records`, then add `id`, `grain`, `history`, `rationale`, `recorded_by` and
`recorded_at`. The enclosing document is:

```json
{"schema_version": 1, "kind": "design_decisions", "records": []}
```

For each copied context, the added fields could be:

```json
{
  "id": "customer_source_rows",
  "grain": ["customer_id"],
  "history": "source_rows",
  "rationale": "One source customer per row; preserve all received rows.",
  "recorded_by": "project_owner",
  "recorded_at": "2026-10-23T12:00:00Z"
}
```

The two objects must be combined into one record: retain the returned `intent`,
`asset_id`, `scope` and `evidence` fields verbatim. Do not invent hashes. Files use
strict JSON, unique record IDs, at most 128 records and a 1 MiB limit; unsupported
fields, duplicate keys, invalid timestamps and unsupported choices are rejected.
An empty records list is valid. This is separate from policy exception/standard-change
records, which retain their own review process.

A record is reused only for the exact intent, asset and scope, with matching policy,
manifest, catalog configuration and resolved-fact fingerprints. Hashes include source
revisions and provenance; retrieval/verification clocks alone do not invalidate reuse.
Even whitespace changes to source files change their revision. Moving source files
can also require reconfirmation because provenance locations are part of the context.
Multiple matching records, stale evidence or an explicit conflicting request produce
questions; no part of a conflicting record is silently applied. Replace obsolete
records deliberately after review rather than accumulating competing records.

The entity returns the record and its file/hash/JSON locator as provenance. Attribution
and timestamp are assertions in a local file, **not authenticated approval**. Reused
grain is labelled `recorded_design_decision` and remains unverified. Column existence,
current/history transformation rules, relationship meaning and normal-form dependency
questions still apply. A saved choice never promotes a standard or proves a key.

MCP pins the selected decisions file alongside project context. If it changes,
`model_plan` requires `modelling_refresh`; old context IDs then become invalid.
The planner does not persist arbitrary semantic answers yet, and drafting still
requires an explicit reviewed request. There is no automatic plan-to-apply shortcut.
