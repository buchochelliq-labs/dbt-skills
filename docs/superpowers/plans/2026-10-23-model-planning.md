# Catalog-grounded model design planning

Spec: docs/ARCHITECTURE.md and issue #16; user authorized continued implementation.

Deliver a deterministic review-only planning core before SQL generation. An agent
supplies business intent and 1–8 selected asset IDs, optional asserted grain/history,
and per-asset rule scope. Shared validated snapshot and existing catalog resolver
remain the sources of evidence. No provider-specific logic, source rows, SQL execution,
file application, implicit standards approval or automatic relationship traversal.

1. Add failing tests for candidate entities, declared key provenance, targeted grain/
   history/normalisation questions, scoped and conflicting standards, missing columns,
   FK endpoint validation and missing target selection, source mapping and downstream
   existing-model review. Explicitly distinguish declarations from assertions and
   hypotheses. Missing relationship metadata never implies no relationships.
2. Implement bounded planner. Stop on denied/error providers and withhold all plan
   evidence on those failures. Conflicts block suggestions and retain conflict evidence.
   Unknown scope stays a question. PKs never prove grain; FKs never prove join safety.
   3NF/4NF require functional/multivalued dependency review. No inferred decomposition
   from column names. Valid declared relationships suggest separate entity candidates
   for review; existing descendants suggest reviewing reuse before creating duplicates.
3. Expose CLI and thin model_plan MCP tool with pinned context/policy checking. Test
   real stdio, changed policy, stale IDs, malformed/bounded requests and CLI status.
4. Document walkthrough and limitations; full tests + independent review; publish a
   focused PR and verify cross-platform CI. Never merge/tag/release.

Implementation choice: deterministic evidence assembly and questions, with semantic
reasoning left to the host agent/human. This avoids a second model-provider runtime.
Richer transformations and automatic acceptance of design answers are future work.

## Verification record

Core tests began with missing planner implementation; MCP integration failed on the
missing model_plan tool before adapter implementation. Fourteen targeted tests pass,
including real stdio, CLI clarification, denial/error withholding, conflicts, scope,
FK endpoints, missing snapshot/key metadata and response bounds. Independent review
found no significant correctness/privacy issues. The synthetic customer walkthrough
identifies the existing model and asks grain/history/relationship/3NF questions.
