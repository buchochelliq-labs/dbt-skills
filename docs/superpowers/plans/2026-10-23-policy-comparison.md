# Policy comparison implementation plan

Goal: Compare manifest model file paths against an explicitly selected policy without
promoting inference, assuming scope, applying exceptions or changing files.
Spec: docs/ARCHITECTURE.md. Execute inline and independently review before PR.

1. Add tests for literal/dynamic/repeated tokens, fixed bindings, scope uncertainty,
   overlapping rules, counterexamples, stale/missing artifacts, provenance and bounds.
2. Add policy_comparison.py: compare_model_names(project, policy_path, snapshot=None,
   model_id=None, context=None). Only directory scope is observed; other dimensions
   require explicit per-model context. Missing scope asks questions; overlapping
   applicable rules conflict. No hidden precedence. Match templates using a bounded
   iterative search, not an unbounded regex; exhaustion is indeterminate, never mismatch.
3. Add compare CLI with --policy, --model and per-model --context. Report model_file
   checks only, with policy/source hashes and locators. Other targets remain unchecked.
4. Document semantics and limits; full suite, independent review, CI, PR against main.
