# Explicit current-row deletion filtering

Extend #53's current-row contract with deletions={mode: exclude_marked, column:
is_deleted, nulls: retain|exclude}. Require a catalog-declared boolean column and
explicit null behavior. Keep retain_latest byte-compatible. Rank all source rows
before excluding a winning deletion marker; never resurrect older rows. Include
an unprojected marker in the inner query only; avoid helper-name collisions.

Test first: latest deleted/older active, latest active/older deleted, null marker
retain/exclude, invalid/unknown/nonboolean metadata, marker omitted from projection,
helper collision, applied validation and real dbt/MCP. Shared current_rows validation
and SQL rendering; pass column metadata from prepare/validation. No warehouse reads,
new writers, arbitrary predicates or claims of upstream delete semantics.

Update docs, run full suite and independent review, publish stacked PR and verify CI.
No merge/release. Joins/history/existing-file edits follow this slice.

Review: retain-latest byte compatibility confirmed; no blocking findings. Added and
fixed a failing regression for hidden marker/source case collisions, conservatively
clarifying across adapters. Other review coverage suggestions remain non-blocking.
