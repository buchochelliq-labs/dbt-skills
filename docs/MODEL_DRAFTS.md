# Source projection drafts and reviewed file creation

This first generation workflow turns explicit model intent, a matched dbt source,
catalog metadata and naming policy into a reviewable SQL model and properties YAML.
It supports a new **source-row projection only**. It does not design joins, aggregate,
deduplicate, implement SCD history, alter existing files or prove 3NF/4NF.

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
Applicable `warehouse_alias` conventions still block generation because this
projection generator cannot enforce them; unrelated scoped rules do not block it.
Column conventions are resolved separately for each projected source column below.
Applied-file validation checks these same constraints using the reviewed policy.

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
claim. Follow the review/apply/validate steps below in a disposable project copy.

## Request and evidence

See [model-request.json](../examples/catalog-workflow/model-request.json). Requests
include business intent, an explicit catalog asset ID, current-project manifest source
ID, projection columns, grain columns, history=`source_rows`, model/properties naming
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
warehouse alias naming targets, existing-file changes, composite-key tests and warehouse-backed
validation remain follow-ups. An applicable unsupported naming target blocks
this generator rather than being silently ignored. General policy principles and
inherited dbt materialization/configuration require human review. Manifest freshness
and local catalog export timestamps do not prove current warehouse state.
