# Modelling policy implementation plan

> Execute inline with superpowers:executing-plans; independently review the branch.

Goal: Load versioned declarative modelling policy and separate observations/decisions,
then expose validation, naming and bounded discovery through a local CLI.
Spec: docs/ARCHITECTURE.md. Python, PyYAML and JSON Schema; no network or model calls.

## Constraints and review focus

Never promote observations or decisions automatically. Preserve exact file hash and
rule locator. Reject duplicate keys, YAML aliases, unknown fields/versions, excessive
size/depth and non-regular files without echoing document contents. No executable
format expressions. Unicode controls must be rejected. Scope is explicit per rule;
normal forms are declared intent, not proved by this tool. Discovery must not follow
symlinks or scan generated/vendor directories. No file edits or source data access.

## Tasks

1. Add regression for Unicode controls to test_modelling_naming.py; observe failure,
   fix _segment using Unicode printability; rerun naming tests.
2. Add tests/test_modelling_policy.py for version/shape enforcement, separated document
   kinds, 3NF/4NF, provenance, aliases/duplicates/depth/size, and naming resolution.
   Observe import failure. Add modelling-policy.schema.json (bundled beside module),
   modelling_policy.py load_document(path) and resolve_policy_name(path, rule_id, values).
   Pin the already-transitive jsonschema dependency explicitly and record provenance.
3. Add CLI tests for validation, render and bounded discovery; implement policy_cli.py
   and discover_policy_files(root). Discovery reports existing standard filenames and
   questions; SQL inference and interactive orchestration remain #38 follow-up.
4. Add example documents and user documentation, run full suite and compile checks,
   independent review, then publish a PR against current main. Do not merge.
