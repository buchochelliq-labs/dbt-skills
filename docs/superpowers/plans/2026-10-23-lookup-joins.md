# First lookup join

Add optional lookup to source-row drafts: explicit asset_id/source_id, type left|inner,
on=[{left,right}], columns, cardinality=many_to_one, nulls=never_match, rationale,
optional column_context using existing naming rules. Require distinct assets, exact
source/relation mappings, declared lookup PK matching right keys, matching known key
types and no contradictory declared FK for the selected base-key tuple. Missing FK
is an explicit unverified caller join assertion. Duplicate lookup keys can multiply
rows; PK metadata does not prove uniqueness. Output grain remains base grain assertion.

Resolve both assets with the shared resolver; denial/error withholds collected join
context. Pin consulted providers for both lookups, including negative evidence.
Generate one new model with qualified equality predicates, no SQL expressions,
queries or data samples. Left preserves unmatched base rows; inner drops them;
null keys never match. Append lookup column mappings/YAML, reject output collisions.
No joins mixed with current-row transformations, self-joins, arbitrary predicates,
existing-file edits, model refs or multiple lookups in this slice.

Tests first: synthetic left/inner/null behavior, source mapping/keys/types/FK conflicts,
missing/unverified cardinality, collisions, denied lookup, input revision drift,
apply/validation, real MCP and dbt parse. Shared lookup module + draft renderer and
validation integration. Full suite, independent review, docs, PR and CI.

Review fixes: reproduced denied-lookup/base-mapping-error metadata exposure, then
moved lookup access resolution before catalog-bearing base clarification. Reproduced
distinct IDs mapping to one physical relation, then rejected physical self-joins.
Both fixes have regression tests; output naming convention coverage added.
