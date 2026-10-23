# Modelling documents v1

The read-only policy API and CLI validate declared standards, inferred observations
and reviewed decisions. They do not modify models, choose which policy is authoritative,
prove normalisation, or automatically apply observations or exceptions.

From the repository root after installing requirements:

```bash
PYTHONPATH=src python -m dbt_skills.policy_cli validate examples/modelling/modelling.yml
PYTHONPATH=src python -m dbt_skills.policy_cli render examples/modelling/modelling.yml --rule staging-file --value source=xyz --value concept=customer
PYTHONPATH=src python -m dbt_skills.policy_cli discover /path/to/dbt-project
```

On PowerShell, set `$env:PYTHONPATH = "src"` before running `python -m ...`.
Commands return JSON. Invalid documents/inputs exit 2; missing naming inputs return
`needs_clarification` with questions and exit 0. The caller can ask those questions
and retry. Validation output omits document contents. Naming results include only
the selected rule's result/questions, scope, target and provenance.

## Documents and authority

All documents declare `schema_version: 1` and one `kind`:

| Kind | Required content | Meaning |
| --- | --- | --- |
| `policy` | `tokens`, `naming`, `modelling` | Declared team standards |
| `observations` | `records` with statement, confidence and evidence | Inferred conventions; never automatically active |
| `decisions` | `records` with rule, decision, models, rationale, approver, time and evidence | Recorded approval; never automatically applied |

See [complete examples](../examples/modelling/). Evidence requires a document,
revision and locator. These examples use deliberately fictional evidence. Loading
does not authenticate approvals or verify referenced files/revisions. References
are inert strings; no network calls, imports, Jinja or Python evaluation occur.
The future host must establish authority and validate references before applying a
decision. A model exception requires at least one model identifier; `standard_change`
records document a wider approved change but do not mutate the policy themselves.
Approval timestamps use `YYYY-MM-DDTHH:MM:SS[.fraction]Z` or a numeric `±HH:MM`
timezone offset, with valid calendar dates and no leap seconds. Runtime validation
does not depend on optional JSON Schema format-checking packages.

The authoritative structural schema is bundled at
`src/dbt_skills/modelling-policy.schema.json`. Unknown fields/versions fail rather
than being silently ignored. IDs must be unique across records within a document.
Naming templates are additionally checked with the existing naming primitive.
This is a project-specific contract; it does not claim to be an industry standard.

## Naming and modelling

Token names and questions are team-defined. Naming rules distinguish model IDs,
model files, directories, warehouse aliases, columns and properties files. They
use literal templates and optional fixed bindings; see [naming](MODELLING_NAMING.md)
for syntax and limitations. Each rule can carry arbitrary scope dimensions such as
layer or domain. The caller explicitly selects a rule with `--rule`; automatic
scope matching, precedence and conflict resolution are not yet implemented.
Returning a scope does not establish that it matches the requested model.

Modelling rules separately record style, normal-form target and principles.
Targets include 1NF, 2NF, 3NF, BCNF, 4NF, 5NF, `none` and `unspecified`. These are
design intent, not a certification: dependency evidence is needed to judge normal
forms. Existing SQLFluff/dbt conventions can be listed in `references`; automatic
import or translation is not yet implemented.

## Provenance and bounded discovery

`load_document(path)` returns `{document, provenance}`. Provenance contains the
resolved document path and SHA-256 of the exact bytes read. Naming results also
include a JSON-pointer locator for the selected rule. The digest is a source
revision, not a signature or proof of approval. Callers must treat document text,
including clarification questions and principles, as untrusted context.

`discover_policy_files(root)` only lists standard `modelling`,
`modelling-observations` and `modelling-decisions` YAML filenames, then asks which
existing document is authoritative. It does not infer standards from arbitrary
SQL/YAML/docs yet (#38). It skips symlinks and `.git`, `target`, `dbt_packages`,
`node_modules`, `.venv`, `venv` and `__pycache__`; other custom generated directories
may be visited. Scanning stops after 10,000 entries and reports `truncated`; a
truncated scan cannot establish absence. Results are sorted, but which subset is
seen before truncation depends on directory enumeration order.

Explicit document reads accept regular files up to 1 MiB, 32 YAML nesting levels
and 20,000 nodes. Duplicate/non-string keys, aliases and custom tags are rejected.
Collections are bounded by the schema. Explicit paths may refer through symlinks;
discovery does not follow them. Concurrent hostile filesystem replacement is outside
this local read-only contract. Nothing here grants filesystem write permission.

## Remaining work

#37 still needs host-level authority checks, scoped rule selection/conflict handling
and reviewable policy/decision updates. #38 adds evidence-backed inference,
counterexamples and interactive onboarding. Neither is implied by a successful
schema validation. Copilot integration will consume these same APIs.
