# Decision proposal implementation plan

Goal: Prepare reviewable pending exceptions or explicit template changes without
writing files, manufacturing approval or changing scope. Extend PR #44.
Spec: docs/ARCHITECTURE.md. Execute inline, then independent review.

1. Fix PR #44 schema/context bound mismatch with a 256-dimension regression.
2. Add schema kind proposals, distinct from approved decisions. Reuse document
   validation through validate_document(document). Require rationale, rule, one
   trigger model, policy/manifest evidence, and the observed path. Exceptions default
   to one model; standard_change requires an explicit replacement template and retains
   the declared rule scope. No approver/time fields are allowed in proposals.
3. Add prepare_decision(project, policy_path, rule_id, model_id, rationale, ...):
   validate current-project manifest identity and selected model, produce proposal
   document and reviewable JSON Patch guarded by policy hash and old template.
   No apply operation. Optional existing proposals are appended in the returned copy
   only, with their own base hash; duplicate IDs and collection overflow fail.
4. Add propose CLI, examples/docs and tests for defaults, wider intent, evidence,
   existing records, invalid templates, missing model, raw-SQL sentinel and no writes.
5. Full tests, fresh independent review, push PR #44, check CI. No merge.
