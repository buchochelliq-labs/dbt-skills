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
macro, warehouse query or source-data validation output is executed/released. A future
validation runner must provide bounded, value-safe results rather than forwarding
ordinary test output, which can contain source values.

## Remaining work

Full business-model reasoning, joins/history, approved exceptions during generation,
additional naming targets, existing-file changes, composite-key tests and output-safe
dbt validation remain follow-ups. A policy declaring unsupported naming targets blocks
this generator rather than silently ignoring them. General policy principles and
inherited dbt materialization/configuration require human review. Manifest freshness
and local catalog export timestamps do not prove current warehouse state.
