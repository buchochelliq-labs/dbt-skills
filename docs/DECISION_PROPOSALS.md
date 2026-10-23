# Pending decision proposals

Use the read-only `propose` command after reviewing a naming mismatch:

```bash
PYTHONPATH=src python -m dbt_skills.policy_cli propose /path/to/project --policy modelling.yml --rule staging-file --model model.project.customer --rationale "Legacy consumer requires this name"
```

This defaults to an exception for exactly the selected current-project model.
It returns a pending `kind: proposals` document, not an approved decision. The
proposal schema rejects approver and approval-time fields. No files are written.
On PowerShell, set `$env:PYTHONPATH = "src"` before invoking the module.

For a wider template change, add both `--decision standard_change` and
`--template 'stg_{source}_{concept}.sql'`. This proposes replacing only the selected
rule's template. It retains the rule ID, scope, bindings and token declarations;
new tokens must already be declared. It cannot silently broaden a model exception
into a team rule or alter scope. Scope changes and broader policy editing remain
future work.

`--proposals FILE` appends to a returned copy of an existing pending-proposals
file. Existing records remain intact; duplicate proposal IDs and schema limits
are enforced. Approved decisions are not accepted as an append target. Without
this option, the output describes a new document with no implied destination.
`--target-path` selects the manifest directory as in other project commands.
Generated documents also obey the loader's structural limits and 1 MiB canonical
JSON budget; an append that exceeds these limits fails before returning a candidate.

## Review contract

The result contains:

- `proposal_document`: pending records with rationale, trigger model, observed
  path, original rule scope/template, and source evidence.
- `policy_patch`: reviewable JSON Patch test/replace operations for a wider
  template change; empty for a one-model exception.
- `proposed_policy`: the validated candidate policy for a wider change.
- `proposals_patch`: JSON Patch to append a record or create the document root.
- `policy_base` and `proposals_base`: exact source hashes (null proposals base
  means a new document). A future applying host must check the entire base hash,
  not merely the template test operation.
- `source`: manifest digest, age/freshness and available generation/observation
  timestamps. Manifest timestamps also travel in the proposal's evidence records.

Patches are data for review, not executable authorization. The tool does not apply
patches, authenticate approvals, confirm scope applicability, or mark a proposal
approved. The reviewer must verify that the selected rule applies and that the
manifest is appropriate/current. Stale or unknown-age evidence remains labelled.
A fresh manifest does not prove current source-file consistency.

Exceptions contain one model ID. A `standard_change` proposal has an empty `models`
list because the change applies to the existing rule scope; `trigger_model` retains
the model that prompted it. Stable proposal IDs derive from the source revisions
and request, excluding observation time. They prevent duplicate requests against
the same revisions; they are not signatures or author identities.

Only model-file naming rules are supported. Semantic design, 3NF/4NF and other
policy changes are not covered. No source SQL/data values are returned. The next
host workflow must collect a human decision and produce the corresponding approved
record separately; changing the proposal's kind is not a valid approval conversion.
