# Convention discovery implementation plan

> Execute inline with superpowers:executing-plans; independently review before PR.

Goal: Generate reviewable naming-policy candidates and evidence-bearing observations
from the shared validated manifest snapshot, with bounded questions and no source SQL.
Spec: docs/ARCHITECTURE.md; issue #38. No automatic standards changes.

1. Tests first: custom separators and token counts, repeated prefix, mixed patterns,
   absent/unsupported/stale manifest, dependency packages, invalid paths, deterministic
   output, output bounds and absence of SQL sentinel. New module convention_discovery.py
   exposes infer_conventions(project, snapshot=None) -> dict. Default consumes existing
   inspect_artifacts(project); supplied snapshots let hosts share one inspection.
2. Infer a dominant delimiter layout per directory from current-project model file
   paths. Keep common parts literal; varying parts receive neutral token_N names.
   Require at least two distinct names. Ties ask a question, never select arbitrarily.
   Observations conform to v1 observations schema; proposed_policy is explicitly a
   non-authoritative draft. Preserve manifest digest/resource locators and counterexamples.
   Cap directories/proposals/questions and evidence counts and report truncation.
3. Add infer CLI with project and target override. Locate existing policy/doc/config
   references without ingesting their prose; ask which authority applies before proposing
   adoption. No SQL dependency interpretation, normal-form inference or file writes.
4. Document examples/limits; full suite, independent review and CI. Publish against main.

Review focus: missing resource identity, external/unsafe paths, partial scans, repeated
layout ties, source text leakage. Missing/stale evidence is not proof of project norms.
