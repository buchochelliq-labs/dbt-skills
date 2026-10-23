# Source-backed model drafts and reviewed create-only application

Spec: ARCHITECTURE.md, #16/#11. Continue approved local model creation workflow.
Implement inline with TDD and a fresh final reviewer, using the execution/TDD skills.

1. Tests -> core read-only draft generation. Require a valid matched manifest, exact
   existing dbt source mapping to resolved catalog relation, explicit source-row grain
   and projection columns, dynamic model/properties naming rules and bounded intent.
   Ask for missing tokens/scope/design; block missing/conflicting/denied metadata.
   Preserve declared policy and catalog provenance; no normal-form certification.
2. Generate review-only SQL (adapter-quoted identifiers) and properties YAML plus
   create diffs, content digest and source preconditions. Support only simple source
   projection; no inferred joins, dedupe, history or silent policy exceptions.
3. Separate operator CLI apply requires exact reviewed digest, unchanged inputs,
   selected project identity, safe configured model paths, no symlinks/collisions,
   exclusive create and best-effort rollback. No agent-facing write or approval tool,
   no SQL execution or raw validation output. No claim of hostile-race transactional safety.
4. Wire draft into existing MCP when policy/catalog configured, retaining context ID
   and pinned snapshot/policy guard. Tests through real stdio; document walkthrough.
5. Full suite, independent review, fixes, focused PR, cross-platform CI. No merge/release.

Progress:
- Core/tests: projection draft, targeted clarification, quote/source rendering and no writes verified.
- Operator apply: exact digest, unchanged hashes, configured paths, exclusive create,
  rollback failure case and CLI round-trip verified. Large manifest hashing matches
  64 MiB inspector support; generated envelopes enforce CLI loader bounds.
- MCP: real stdio draft/context and changed-policy rejection verified.
- Independent review: negative catalog evidence and unparsed name collisions reproduced
  RED, fixed by pinning every consulted source and bounded SQL/Python filename inventory.
- Full local suite: 152 tests pass; compileall and diff checks pass. No deferred findings.
- Example CLI prepare/apply checked in a disposable copy; no warehouse/dbt execution.
- Remote PR and cross-platform CI follow publication.
