# Current-state model drafts

Goal: extend the existing shared prepare/review/apply/validate workflow with a bounded
one-source current-row model, before joins/full history/existing-file edits.

Contract: history=current requires current_row with order_by (1..16 distinct portable
source-column identifiers, direction asc/desc and nulls first/last), ties=assert_unique,
deletions=retain_latest and non-empty rationale. Grain identifies the business entity.
Caller asserts that ordering uniquely identifies a row within grain; no metadata or
SQL shape proves this. Retain deletion markers in the latest row, never silently
resurrect an older row. Other deletion/tie strategies clarify. Source_rows cannot
carry current_row. Ordering may use catalog columns not projected in the output.

Implementation: add focused current_rows module for validation/rendering; reuse
column naming, aliases, source mapping, sealed file application and validation.
Portable nested ROW_NUMBER window rather than dialect-specific QUALIFY. Choose an
internal rank name that does not collide with projected source/output names. Preserve
explicit output projection and omit helper/order-only columns. Existing projections
remain byte-compatible. Recompute contract in applied validation.

Checks: missing/unsafe/unknown/conflicting rules, aliases/helper collisions, synthetic
SQL execution for newest/tie/null behavior (no warehouse), apply/validation tampering,
CLI/MCP and real dbt parse. Full suite, independent review, PR/CI; no merge/release.

Review: no critical/important rendering defects. Fixed a demonstrated metadata-consistency gap: source-row drafts now reject injected current-row design metadata (regression test failed before fix). Live host verification remains deferred.
