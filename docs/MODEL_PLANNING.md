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
