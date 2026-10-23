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

The host agent uses this evidence to propose a data-model design across entities
and relationships. SQL generation, file application and dbt execution are not
provided by this context layer.

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
The planner reuses the bounded semantic answers described below. The agent uses
these records as context when discussing and revising the complete data-model design.

## Prepare a decision for review

To avoid assembling evidence hashes by hand, call
`model_propose_decision(context_id, request)` with policy and catalogs configured.
The equivalent CLI is:

```sh
PYTHONPATH=src python -m dbt_skills.design_decision_proposals \
  --project-dir examples/catalog-workflow --target-path artifacts \
  --policy modelling.yml --catalog-config catalogs.json \
  --request decision-request.json
```

A request contains exactly one asset and explicit grain/history choices:

```json
{
  "plan": {
    "intent": "Model customers and their orders",
    "assets": [{
      "asset_id": "urn:demo:xyz:customers",
      "grain": ["customer_id"],
      "history": "source_rows"
    }]
  },
  "record": {
    "id": "customer_design",
    "rationale": "Preserve each source customer row.",
    "recorded_by": "project_owner",
    "recorded_at": "2026-10-23T16:00:00Z"
  }
}
```

The operation derives fingerprints from the same planner context and returns
`proposed_document`, `decisions_patch`, `decisions_base` and the full `planning`
report. Review the proposed document, choices, attribution and remaining questions.
If adopting it, verify the source evidence and base file digest are still current,
then save **only `proposed_document`** through your normal reviewed file workflow.
The tool does not save, approve or authenticate anything. `pending_review` means a
record is ready for review, even when semantic/dependency questions remain open.
Missing grain columns, missing relation/column metadata, conflicting catalogs or
unavailable project evidence prevent a proposal; denied catalogs block it entirely.

When updating an existing file, select it using `--design-decisions` at CLI/server
startup. Unrelated records are preserved. A matching intent/asset/scope requires an
explicit top-level `replace_record_id`; replacement emits a test of the previous
record followed by its replacement. Competing matching records require manual
reconciliation. IDs cannot overwrite another decision, and replacement cannot change
the record's intent/asset/scope. The full base digest must be checked before saving
both additions and replacements; the patch alone is not a concurrent-write guard.

MCP takes no file path in the tool call. Changes to selected policy or decisions
require refresh, just as for `model_plan`. After saving an adopted proposal, refresh
and plan again to see the reused decision and its provenance. The agent remains responsible for reasoning about the complete data-model design.

## Retain semantic answers as design context

A design record may include `answers`, and `model_propose_decision` accepts the
same optional field inside `record`. Each answer has a stable `question_code`, an
`answer` and a `rationale`, for example:

```json
{
  "question_code": "functional_dependencies",
  "answer": "Customer ID determines the customer attributes within this source.",
  "rationale": "Reviewed business definition; physical uniqueness remains unverified."
}
```

Supported codes are `functional_dependencies`, `multivalued_dependencies`,
`join_dependencies`, `review_principles`, `relationships_unknown`,
`grain_key_difference`, `current_row_rule` and `history_rule`. These describe
semantic understanding, including temporal intent; they do not implement SCD or
other transformations. Proposals accept answers only for questions raised by the
selected plan. Up to 16 unique entries are allowed; answer text is bounded to 2048
characters and rationale to 4096. Do not put source rows or example values in these
metadata records. Old records without answers remain supported.

Review and save the proposed document using the existing human-owned file workflow.
The tool never saves it automatically. After refresh, an exact matching record
(intent, asset, scope and evidence) supplies `recorded_answer` on the relevant
planner question. This includes `verified: false` and document/hash/JSON-location
provenance; record-level attribution and evidence remain on the entity decision.
The host should acknowledge the prior answer and assess remaining gaps instead of
asking the user to repeat it. `review_required: true` keeps the question visible;
normal-form compliance remains unverified. Narrative memory is context, never a
catalog declaration, instruction, approved standard or executable SQL rule.

Stale, conflicting and ambiguous records never supply active answers. Their review
questions remain explicit. Replacing an answer requires the existing explicit
`replace_record_id` workflow and preserves the previous record in the review patch.
This first slice records answers within an existing single-asset grain/history
record. Cross-entity design records and arbitrary business-concept notes are not
implemented; the host agent still reasons about the complete data model.
