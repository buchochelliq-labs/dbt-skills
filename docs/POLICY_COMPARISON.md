# Compare project filenames with a selected policy

```bash
PYTHONPATH=src python -m dbt_skills.policy_cli compare /path/to/project --policy /path/to/modelling.yml
PYTHONPATH=src python -m dbt_skills.policy_cli compare /path/to/project --policy /path/to/modelling.yml --model model.project.customer --context layer=staging
```

PowerShell users set `$env:PYTHONPATH = "src"` before the command. `--target-path`
selects the artifact directory as in `infer`. Context requires one explicit model,
so a supplied layer/domain cannot silently apply to the entire project.

This read-only command uses the shared validated manifest snapshot and an explicitly
selected schema-v1 policy. It does not apply inferred drafts or recorded exceptions,
change files, query data, or authenticate who approved a policy. Hosts may reuse a
snapshot with `compare_model_names(project, policy_path, snapshot, model_id=..., context=...)`.

Only `model_file` rules are checked. Templates without `/` match the basename; templates containing `/` match the
full project-relative path. `compared_value` records which representation was checked.
The manifest supplies exact parent-directory
scope; directory matching is literal and non-recursive. Other scope dimensions
require caller-supplied context. Caller context cannot contradict the observed
directory. The report labels each scope value's source. No naming-based inference
is used to decide that a model is staging or belongs to a particular domain.

| Model status | Meaning |
| --- | --- |
| `matches` | Filename structurally fits the one applicable rule |
| `mismatch` | Filename does not fit; asks about a model change, scoped exception or wider policy change |
| `needs_scope` | A potentially applicable rule has unknown scope dimensions |
| `rule_conflict` | Multiple rules apply; no implicit priority is selected |
| `uncovered` | No model-file rule applies under the known scope |
| `not_evaluated` | Model path is missing or invalid |
| `indeterminate` | Template comparison exceeded bounded work |

Unknown scope prevents a compliance decision even when another rule already
matches. Known scope mismatches eliminate a rule. Multiple applicable rules are
reported as a conflict even if their templates happen to agree: precedence is a
human policy decision. Fixed bindings must match; repeated occurrences of a token
must contain the same value. Adjacent tokens may match structurally, but captured
values are not returned or treated as semantic facts.

The report includes exact policy and manifest hashes, source generation and observation
times (when available), resource/rule locators,
filename and caller/manifest scope attribution. Its top-level status stays
`needs_review`; a structural match does not prove source semantics, approved intent,
normalisation or complete compliance. Missing/mismatched manifests or a missing
selected model return `needs_context`. Stale or unknown-age evidence asks about
refreshing. Even a fresh manifest may differ from current files.

At most 200 sorted current-project model resources are reported, with `truncated`
when more exist. Policies with more than 64 model-file rules return `needs_context`
instead of comparing an incomplete rule set. Template search schedules at most
2,048 states and supports at most 64 token occurrences, 4,096 filename characters
and 1,024 characters per token. Budget exhaustion is never a mismatch. Other naming
targets are listed in `unchecked_targets`; design principles, 3NF/4NF and exception
records are not evaluated. No SQL or compiled source text is returned.

Next onboarding work is a host conversation that resolves these questions and
prepares reviewable scoped decision or policy diffs. This command makes no edits.
