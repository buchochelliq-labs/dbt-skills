# Source projection drafts and reviewed file creation

This first generation workflow turns explicit model intent, a matched dbt source,
catalog metadata and naming policy into a reviewable SQL model and properties YAML.
It supports new **source-row projections and explicitly ordered current-row models**.
It also supports one explicitly specified lookup join and event-history intervals. It does not aggregate,
capture stateful SCD snapshots, alter existing files or
prove 3NF/4NF. See [current-row models](#current-row-models) for the selection contract.

`prepare_model` is shared by the CLI and the read-only MCP `model_draft` tool. The
MCP tool appears only when both policy and catalog configuration are selected. It
requires the existing context ID and uses the pinned manifest; changed policy is
rejected. Catalog provider digest/access checks remain in force. No MCP write or
approval tool is added.

## Additional naming constraints

The selected `model_file` and `properties_file` rules produce the output paths.
Applicable `model_id` rules must match the SQL filename stem, and applicable
`directory` rules must match its parent directory. The directory target concerns
the SQL model; the properties path remains governed by `properties_file`.

```yaml
- id: staging_identifier
  target: model_id
  template: stg_{system}_{concept}
  scope:
    directory: models/staging
- id: staging_directory
  target: directory
  template: models/staging
```

These entries go in the policy's `naming` list and reuse its declared team-defined
tokens and fixed bindings. No particular token names or number of tokens are required.
The model ID here is the dbt model name (SQL filename stem), not the manifest's
`model.package.name` unique ID. Rules never silently rename the generated files.
Mismatches return the expected/actual value plus rule provenance for clarification.

Additional rules use supplied scope plus the rendered SQL parent directory. Rules
with a known scope mismatch are inapplicable; rules with unresolved scope ask a
question. Multiple applicable constraints for the same target require clarification,
even if their templates agree. Missing values return the configured token questions.
Warehouse aliases and column conventions are resolved separately below.
Unrelated scoped rules do not block generation.
Applied-file validation checks these same constraints using the reviewed policy.

## Warehouse alias conventions

An applicable `warehouse_alias` rule resolves a literal relation-name configuration:

```yaml
- id: staging_relation
  target: warehouse_alias
  template: stage_{system}_{concept}
  scope:
    directory: models/staging
```

The generator adds `{{ config(alias='stage_xyz_customer') }}` before the projection.
The SQL filename, dbt model name and YAML model name remain unchanged. Tokens use the
same team-defined values and fixed bindings as file rules. Missing tokens/scope,
overlapping rules and non-portable SQL identifiers require clarification. If no alias
rule applies, no alias config is generated. `design.warehouse_alias` records the
configured value and rule provenance; applied validation recomputes it.

Known model names/aliases in the manifest and SQL/Python filenames in the local model
inventory are checked case-insensitively for collisions. This check is conservative
across schemas and packages; the new model's own filename is excluded. It cannot prove
that a warehouse relation is free: unparsed models can contain custom aliases, and target
database/schema or `generate_alias_name` macros may change the effective relation.
Review inherited configuration and custom naming macros before execution. This feature
sets the literal alias configuration; it never evaluates project macros or queries the
warehouse to certify the final name. An operator-only parse can check project parsing.

## Column conventions and output names

Optional request `column_context` maps **selected source column names** to per-column
`values` and `scope` string mappings. Token and scope keys are team-defined. No token is
implicitly filled from a source name, business concept or position.

For a declared `attribute` token and a column rule with `template: "{attribute}"`:

```json
"column_context": {
  "customer_id": {"values": {"attribute": "customer_key"}},
  "customer_name": {"values": {"attribute": "customer_name"}}
}
```

Each column combines model scope with its own scope and the actual SQL parent directory.
A known scope mismatch excludes a rule; unknown scope and multiple applicable rules ask
for clarification. For example, team-defined `role: key` and `role: label` scopes can
select different column templates. Overlapping model/per-column token values and scope
must agree; per-column input cannot silently override model context or fixed bindings.

The selected rule resolves literal tokens using the existing naming engine. Output names
must be portable SQL identifiers, and case-insensitive output collisions block drafting.
Columns without applicable rules keep their source name. Supplied per-column token values
without an applicable rule produce clarification rather than being silently discarded.
Unknown source-column keys or malformed contexts fail validation. The complete request,
including column context, remains bounded to 16 KiB.

SQL quotes both the original source identifier and any changed output alias with
`adapter.quote`. YAML column names and proposed tests use output names. Requested `columns`
and `grain` always refer to source identifiers; `design.output_grain` and
`design.column_mapping` show the output names and rule provenance. No expressions, casts,
row transformations or catalog fact rewriting are introduced. Composite grain uniqueness
still needs a separate reviewed test. Applied validation recomputes the mapping from the
reviewed policy/request and checks both file content and recorded mapping metadata.

Try the separate example policy/request with the same synthetic manifest:

```sh
PYTHONPATH=src python -m dbt_skills.model_drafts prepare \
  --project-dir examples/catalog-workflow --target-path artifacts \
  --policy modelling-columns.yml --catalog-config catalogs.json \
  --request model-request-columns.json > draft.json
```

The example renames `customer_id` to `customer_key` without changing the original catalog
claim and sets the configured relation alias to `stage_xyz_customer_projection`. Follow the review/apply/validate steps below in a disposable project copy.

## Request and evidence

See [model-request.json](../examples/catalog-workflow/model-request.json). Requests
include business intent, an explicit catalog asset ID, current-project manifest source
ID, projection columns, grain columns, history=`source_rows` (or `current` with its explicit rule), model/properties naming
rule IDs, arbitrary configured token values and any extra rule-scope dimensions.
Missing design inputs, tokens, unknown scopes, overlapping rules, unavailable catalog
facts and source mapping disagreements return clarification without output files.

The catalog relation must exactly match the selected source's database, schema and
physical identifier. Names passed into generated Jinja are restricted identifiers.
Column expressions use dbt's documented [adapter.quote](https://docs.getdbt.com/reference/dbt-jinja-functions/adapter#quote)
so the configured adapter handles SQL quoting. The generated model uses the existing
`source()` declaration and never invents a new source. Project artifacts now preserve
source_name and identifier metadata for this mapping.

Grain is an explicit caller assertion, not a catalog-derived proof or an authenticated
human approval. SQL preserves every source row; it does not ensure the asserted grain.
The properties YAML proposes not-null checks on grain columns and a unique check for
a single-column grain. Composite uniqueness needs a separate reviewed test. Catalog
keys, unknown relationships and every modelling principle/normal-form target remain
visible as review evidence. No policy compliance certification is issued.

## Prepare and review

From the repository root, use a disposable copy of the example project. Its
`artifacts/manifest.json` is a **synthetic test fixture**, not live dbt output. For a
real project, use its genuine generated manifest and omit the fixture target override.

```sh
PYTHONPATH=src python -m dbt_skills.model_drafts prepare \
  --project-dir /path/to/copied-catalog-workflow \
  --target-path artifacts --policy modelling.yml \
  --catalog-config catalogs.json --request model-request.json > draft.json
```

Request/policy/catalog paths are relative to the selected project (absolute paths
also work). CLI returns 0 for a pending review draft, 2 for clarification JSON, and 1
for an error. Prepare writes only JSON to stdout; shell redirection saves it at your
chosen location. In Copilot, call `model_draft(context_id, request)` and save the exact
structured result, without the surrounding MCP response wrapper.

Read the complete draft: intent/grain assertions, source mapping, policy, selected and
conflicting catalog evidence, input revisions, file content and create diffs. It has a
`draft_id` SHA-256 covering the complete payload, including content and provenance.
The ID detects changes; it is **not** a signature, an identity check or proof of approval.
The envelope is limited to 1 MiB, 16 levels and 20,000 structural nodes so the apply
loader can consume every successfully generated draft.

## Explicit operator application

After reviewing the exact draft, the operator runs:

```sh
PYTHONPATH=src python -m dbt_skills.model_drafts apply \
  --project-dir /path/to/copied-catalog-workflow \
  --draft draft.json --approve THE_REVIEWED_DRAFT_ID
```

`--draft` is relative to the shell's current directory. Approval is the operator's
explicit command with the reviewed digest, not a boolean supplied by an agent. Do not
auto-extract the digest and chain prepare/apply without review. Hosts with shell tools
must enforce their own approval boundary; MCP annotations and agent prose cannot do so.

Apply verifies the digest, project identity and all captured input hashes (including consulted providers that returned no facts), and
a bounded inventory of SQL/Python model filenames, then creates
exactly the two approved files with exclusive creation. Inputs are hashed without
returning their contents; supported manifest size remains 64 MiB. Outputs must be in
configured model directories, use portable paths, and have SQL/YAML extensions.
Existing targets, symlinks, directory conflicts, duplicate unparsed model names and
changed inputs block application. Inventory traversal is capped at 10,000 entries; it
reads names, not model contents. Any SQL/Python model filename inventory change requires
a new draft, even if the manifest has not been regenerated.
Failure attempts to remove files created by this invocation; empty directories may
remain. Concurrent hostile filesystem mutation is outside this local CLI contract;
this is not a cross-file transactional filesystem service.

Editing a draft invalidates its digest; regenerate and review it. Creation is not
semantic validation. `validation_executed` remains empty. No dbt command, project
macro, warehouse query or source-data validation output is executed/released. The separate checks below return fixed statuses instead of forwarding subprocess output.

## Validate applied files

After application, check the exact files and captured evidence without executing dbt:

```sh
PYTHONPATH=src python -m dbt_skills.model_validation check \
  --project-dir /path/to/copied-catalog-workflow --draft draft.json
```

Checks cover envelope integrity, captured input revisions, applied bytes, model filename
inventory and the restricted source-projection rendering contract. Reports contain fixed
check names/statuses, no file contents, raw errors or source values. A pass does not prove
keys, normal forms, warehouse SQL validity or business semantics.

With policy and catalog configured, MCP exposes `model_validate(context_id, draft_id)`.
It accepts only one of the last four drafts generated by that server context; it cannot
accept arbitrary file paths or draft envelopes. Refresh clears retained drafts. This tool
runs local checks only; it never launches dbt.

## Optional operator-only dbt parse

An operator may explicitly select an installed dbt executable and profiles directory:

```sh
PYTHONPATH=src python -m dbt_skills.model_validation parse \
  --project-dir /path/to/copied-catalog-workflow --draft draft.json \
  --approve THE_REVIEWED_DRAFT_ID \
  --dbt-executable /absolute/path/to/dbt --profiles-dir /absolute/path/to/profiles
```

On Windows select the absolute path to `dbt.exe`. The reviewed digest and passing local
checks are required. Timeout defaults to 60 seconds (allowed range 1–300). The fixed command
uses `dbt parse --no-partial-parse`, isolated temporary target/log directories, no shell,
closed stdin and discarded stdout/stderr. Temporary artifacts are deleted without being
returned. Exit status and post-run local checks determine the fixed result:
`passed`, `failed`, `timeout`, `unavailable` or `blocked`. CLI exit is zero only for a pass.

[dbt parse](https://docs.getdbt.com/reference/commands/parse) checks project parsing;
compile/run/test/probes are excluded. This executes a **trusted local executable and
trusted project/package code**, not a sandbox. Arbitrary custom code can have side effects;
normal output suppression is not containment. Timeout terminates the direct child, not a
promised process-tree sandbox. Review inherited macros/configuration and use an appropriately
restricted local environment. Hosts must enforce operator approval for shell access.
No report claims warehouse validation. The isolated real-dbt test uses dbt-core 1.11.7 and
dbt-duckdb 1.10.0 with an in-memory profile and no source rows.

## Remaining work

Full business-model reasoning, joins/history, approved exceptions during generation,
effective warehouse relation checks, existing-file changes, composite-key tests and warehouse-backed
validation remain follow-ups. An applicable unsupported naming target blocks
this generator rather than being silently ignored. General policy principles and
inherited dbt materialization/configuration require human review. Manifest freshness
and local catalog export timestamps do not prove current warehouse state.

## Current-row models

Set `history` to `current` and provide an explicit `current_row` rule:

```json
{
  "order_by": [
    {"column": "updated_at", "direction": "desc", "nulls": "last"},
    {"column": "event_id", "direction": "desc", "nulls": "last"}
  ],
  "ties": "assert_unique",
  "deletions": "retain_latest",
  "rationale": "Latest event per business key; event ID uniquely breaks timestamp ties. Retain deletion markers."
}
```

`grain` is the business key used to partition rows. The tool renders a nested
`row_number()` window and keeps rank 1. Sort columns must exist in catalog metadata,
with explicit direction and null placement; they need not be projected into output.
Naming rules, literal warehouse aliases and output-column mappings work as before.
The helper rank column never appears in the output and avoids projected-name collisions.

`assert_unique` is the caller's assertion that the complete ordering distinguishes
rows within each business key. It is not a warehouse check: if ties remain, selection
can be nondeterministic. Confirm a stable final tie-break column before adoption.
`retain_latest` keeps the winning row even if it is a deletion marker. It never filters
deletions or resurrects an older row. For active-only output, use the explicit boolean-marker policy below; other deletion/tie
policies ask for clarification.
Null business keys group together and require the proposed not-null tests to be run.
The generated uniqueness test on a single output key does not test input ordering ties.

The complete rule and rationale are recorded as unverified caller assertions in
`design.current_row`. Applied validation recomputes the rule and rendered files;
operator-only dbt parse remains available. Parsing does not execute the SQL or prove
warehouse semantics. This supports a single-source current-row model, not incremental
merge, SCD2 history, joins or existing-model edits. `source_rows` requests cannot carry
a current-row rule. Existing source-row projections retain their previous rendering.

### Exclude latest deletion markers

Replace `deletions: "retain_latest"` with:

```json
{"mode": "exclude_marked", "column": "is_deleted", "nulls": "retain"}
```

The marker must exist in catalog metadata with normalized type `boolean`. Choose
`nulls: "retain"` to keep unknown flags or `nulls: "exclude"` to exclude them. This
choice is required even if metadata declares the column non-null. `true` marks a
deletion and `false` an active row; these meanings are caller assertions, not facts
inferred from a column name. String codes, numeric flags and arbitrary SQL predicates
are unsupported and require clarification.

Selection ranks **all** source rows before filtering the winner. If the latest row
is marked deleted, the entity is absent; an older active row is never restored. A
later active event can restore an entity. The marker need not be in `columns`; when
omitted, it is used internally and does not appear in SQL output or generated YAML.
If projected, normal column naming still applies. Marker/source identifiers that differ
only by case require clarification to avoid ambiguous inner columns across adapters. The complete deletion/null policy
is retained in the unverified design record and recomputed during applied validation.

This does not infer hard deletions from missing source rows or implement incremental
deletes. Correctness depends on the selected source retaining the required events
and the human confirming ordering and marker semantics. No source data is queried.

## One explicit lookup join

A `source_rows` request can add one `lookup` object:

```json
{
  "asset_id": "urn:demo:xyz:customer_segments",
  "source_id": "source.my_project.xyz.customer_segments",
  "type": "left",
  "on": [{"left": "customer_id", "right": "customer_id"}],
  "columns": ["segment"],
  "cardinality": "many_to_one",
  "nulls": "never_match",
  "rationale": "One reviewed segment record per customer key."
}
```

Replace IDs with explicitly selected catalog and current-project dbt source IDs.
The lookup relation must exactly match its manifest source mapping. Right-side join
keys must match a declared primary key; both sides need matching known normalized
key types. A conflicting FK declaration for the selected base-key tuple requires
clarification. Matching FK declarations retain provenance; missing FK declarations
leave relationship meaning as a human assertion. No relationship targets are fetched
unless selected in the request.

`left` retains unmatched base rows with null lookup attributes. `inner` drops unmatched
rows. Equality never matches null keys. The lookup primary key and `many_to_one`
statement are declarations/assertions, **not uniqueness proof**: duplicate lookup
keys can multiply rows and invalidate the asserted base grain. The generated base-grain
tests do not verify lookup uniqueness before execution. Review cardinality, optionality
and the business meaning of the join before adopting it.

Base `columns` and `grain` retain their meaning. Lookup `columns` are appended; grain
must remain in the base projection. Optional `lookup.column_context` uses the same
values/scope structure as base `column_context` and the same declared naming rules.
Output names must be unique across both projections; collisions ask for clarification.
There are no implicit prefixes, suffixes or inferred aliases. Both catalog reports,
source mapping, lookup key, relationship provenance and complete join rationale remain
in the sealed draft. Consulted provider revisions from both resolutions are pinned.

This creates a new model from two distinct dbt sources. It does not yet accept model
`ref()` inputs, self-joins, multiple lookups, current-row/temporal joins, expressions,
implicit casts, arbitrary predicates or existing-model edits. Denial/error on the
lookup withholds collected join context. MCP remains read-only; the same explicit
operator apply and output-safe parse workflow is used. No warehouse queries occur.

## Event-history validity intervals

For a source that already retains complete historical events, use `history: historical`
and an explicit `history_rule`:

```json
{
  "effective_at": "updated_at",
  "events": "assert_complete",
  "ordering": "assert_unique_non_null",
  "deletions": "retain_events",
  "materialization": "table",
  "rationale": "Source retains every event; effective time uniquely identifies a version per customer."
}
```

The effective column must be catalog-declared `date` or `timestamp`, and cannot be
part of the business `grain`. The human must confirm it is non-null and unique within
each business key, and that the source contains all required events. These assertions
are recorded with column provenance, not verified against warehouse data. Duplicate
effective times can create zero-length/ambiguous intervals; null times invalidate the
design. No arbitrary ordering expression or automatic tie-break is inferred.

The generated model retains every event and uses `lead(effective_at)` within each
business key to produce half-open `[valid_from, valid_to)` intervals. The latest known
event has null `valid_to`. Deletion events stay in the output; an open-ended latest
interval does not imply the entity is active. Project a source deletion marker when
consumers need it. Unchanged payloads are not compressed into fewer versions.

Generated `valid_from` and `valid_to` fields use the same declared column conventions
as source projections. Set `history_rule.column_context` with entries keyed by those
two logical fields and the usual `values`/`scope` mappings. Without applicable column
rules they retain those names. Any output-name collision requires clarification.
The proposed output grain is the mapped business key plus mapped validity start.
Business keys and validity start get not-null tests; single-business-key uniqueness
is not generated for history. Composite event-key uniqueness remains a separate check.

Choose `materialization: table` or `view` explicitly; generated config overrides
inherited incremental materialization. This rebuilds/reads intervals from the full
available event source. A late event changes adjacent intervals on recomputation,
and source retention loss removes history. It is **not** dbt snapshot capture or a
stateful SCD2 merge that preserves overwritten/disappearing source rows. Temporal
joins, incremental history maintenance, hard-delete inference and existing-file edits
remain separate workflows. Current-row/lookup settings cannot be combined with this
history rule. The same review/apply/validate and operator-only parse path is used.

## Revising a generated model

An unchanged, previously applied draft can be revised at the same SQL and YAML
paths. The base files, generation contract, model inventory and pinned evidence
must still validate. Manual edits, renames, changed policy/catalog/manifest inputs
and arbitrary existing models require a future adoption workflow; this command
will not infer a safe replacement for them. An explicitly selected alternate
policy or catalog is allowed when both the original pinned inputs and proposed
inputs still validate.

Prepare a complete new request and retain the original applied draft JSON:

```sh
python -m dbt_skills.model_revisions prepare \
  --project-dir /path/to/project --base-draft base.json \
  --request revised-request.json --policy modelling.yml \
  --catalog-config catalogs.json > revision.json
```

Paths to documents resolve from the selected project (absolute paths also work).
Preparation is read-only and returns either clarification questions or a sealed
revision containing both drafts, before/after hashes and unified diffs. Review the
complete revision, then explicitly apply its exact `revision_id`:

```sh
python -m dbt_skills.model_revisions apply \
  --project-dir /path/to/project --revision revision.json \
  --approve REVIEWED_REVISION_ID
```

Both files are staged before replacement, existing modes are preserved and the
base is checked again before writes. Replacements are validated locally. Failure
attempts rollback only for files still matching this operation's replacement
bytes. The pair is **not an atomic transaction**: interruption or incomplete
rollback requires workspace inspection. Concurrent hostile filesystem mutation
is outside this local operator contract. No warehouse validation is implied.
Save the successful revision's `proposed` object as the new base draft for later
revisions or explicit isolated dbt parse validation.
