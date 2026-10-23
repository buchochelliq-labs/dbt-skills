# Policy-driven output column naming

Spec: dynamic naming requirements in docs/ARCHITECTURE.md and #16/#37. Continue the
naming work after #50; publish as an extension while open, or a new PR if merged.

Request gains optional column_context mapping selected source column names to
{values, scope}. Both mappings use arbitrary team-defined keys; no automatic
source/business-object token interpretation. Global values/scope and per-column
entries must agree on overlapping keys. Actual model directory supplies directory
scope; a contradictory supplied directory must clarify, never override it.

1. Tests first: dynamic rule rendering produces quoted aliases and YAML output names;
   grain assertions remain source columns, generated tests follow mapped output names.
   Missing tokens, conflicting values/scope, unknown scope, overlap, unsafe outputs,
   duplicate output identifiers, unexpected source keys and unsupported warehouse
   aliases fail/clarify. Scope-inapplicable column conventions leave identity names.
2. Shared column mapping core; prepare records mapping/provenance and output grain.
   Renderer accepts resolved mapping; applied validation recomputes it from policy
   and request. No expressions, transformations, schema changes, inferred metadata,
   source rows or warehouse execution. No silent fallback when applicable rule fails.
3. Real stdio draft/apply/validate and isolated real-dbt parse of aliased SQL/YAML;
   docs, full suite, independent review, publication and CI. No merge/tag/release.

## Verification record

Initial tests failed because column_context was rejected and column conventions were
unsupported. Fifteen focused tests now pass, including real stdio, real dbt parse,
composite grain, malformed contexts and pre-mapping draft compatibility. Example
customer_id/customer_key mapping was exercised with the synthetic manifest. No
warehouse rows or SQL execution beyond operator parse were involved.
