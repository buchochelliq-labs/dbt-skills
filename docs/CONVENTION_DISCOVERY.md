# Reviewable convention discovery

```bash
PYTHONPATH=src python -m dbt_skills.policy_cli infer /path/to/project
PYTHONPATH=src python -m dbt_skills.policy_cli infer /path/to/project --target-path build
```

On PowerShell, set `$env:PYTHONPATH = "src"` first. The command returns JSON without
writing files, changing standards or querying a warehouse. It consumes the same
validated manifest snapshot as artifact inspection. A host can call
`infer_conventions(project, snapshot)` to reuse one `inspect_artifacts(project)`
result. Supplied snapshots must come from that inspector; this API is not another
artifact deserializer.

## What it finds

Current-project model paths are grouped by their literal parent directory.
The most common underscore, hyphen or dot delimiter layout is a candidate only
when at least two distinct files support it. Tied top groups with at least two
files each produce a conflict question; singleton groups provide insufficient evidence. Repeated segments remain literal; varying segments get neutral,
rule-specific token names. File extension case is preserved.

For example, `stg-xyz-customer.sql`, `stg-erp-order.sql` and `stg-abc-account.sql`
can suggest `stg-{candidate_1_token_1}-{candidate_1_token_2}.sql`. The agent must ask
what each token means. It cannot conclude that a segment is a source or business
object from a filename alone. Each candidate also asks whether its layout and
scope are intended; a common literal can be incidental. The declared naming
engine supports arbitrary tokens/templates; inference is deliberately narrower.

## Output and authority

| Field | Meaning |
| --- | --- |
| `observations` | Schema-v1 inferred records with confidence, evidence and counterexamples |
| `proposed_policy` | Schema-v1 draft; no invented modelling intent |
| `existing_documents` | Policy, configuration and decision-document filename candidates |
| `source` | Manifest status, identity, freshness and exact hash |
| `questions` | Authority, freshness, modelling, conflicts, token meanings and scope |
| `truncated` | Inventory, groups, evidence or questions omitted by limits |

Evidence refers to the manifest path, exact digest and resource/field locator.
It describes the manifest, not proof that current files are unchanged. Confidence
is medium only with at least three matching filenames, no directory counterexamples
and a fresh manifest; otherwise low. These are heuristic labels, not approval or
statistical confidence. Candidate IDs are local to a report; assign stable IDs
when reviewing adoption as maintained standards.

SQL and document prose are not read or copied. Filename hints do not establish
authority. Ask which existing source governs the project before accepting a draft,
then review differences rather than replacing existing standards.

Missing, unsupported or mismatched manifests return `needs_context` without rules.
Stale/unknown-age manifests retain that status and ask about refreshing. An empty
draft does not mean there are no conventions.

## Bounds and remaining work

The existing inspector bounds resources to 10,000. Inference excludes dependency
packages, missing identities, unsafe paths and non-SQL files. It considers at most
16 sorted directories, eight evidence items and eight counterexamples per candidate,
64 questions and nine variable segments per layout, subject to policy length limits.
Inventory uses the policy scanner's bounds. Truncation never establishes complete
agreement or absence. Within inventory, configuration and decision filenames are
only hints; custom names may not be recognised.

No SQL/body or data-value inference is performed. This cannot establish 3NF/4NF,
grain, keys, dependencies, source mappings or whether a directory is a layer.
Full #38 onboarding still needs explicit YAML/meta and reviewed decision adapters,
incremental conversation and reviewable policy-update diffs. Copilot integration
remains separate.
