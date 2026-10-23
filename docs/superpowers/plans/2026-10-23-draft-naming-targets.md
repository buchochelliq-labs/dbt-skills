# Enforce model ID and directory naming during drafting

Spec: agreed dynamic team-defined naming architecture; #16/#37. Started independently of planning PR #49 on merged #48; rebased onto #49
after it merged during implementation. No SQL shape or approval behavior change.

Current generator rejects any additional naming target, including model_id/directory
rules that could be checked deterministically. Extend shared _names to evaluate these
against the rendered SQL file stem and parent directory. Keep arbitrary token names,
fixed bindings and original policy provenance. The directory target is the SQL model's
parent; properties paths remain governed by their own properties_file rule.

1. Tests first: matching additional rules succeed; mismatches, unresolved tokens,
   unknown scope and overlapping rules clarify; unrelated scoped rules do not block;
   applicable unsupported warehouse_alias/column rules still block. Validate an applied
   draft under the same constraints. No request/schema changes or silent renaming.
2. Implement shared scoped selection and enforcement without changing literal rendering.
3. Document exact scope behavior and boundaries. Full suite including real parse,
   independent review, publish focused PR and verify CI. No merge/tag/release.

Verification: nine focused tests passed; independent review found no important issues.
The rebase retained both planning and naming handover sections.
