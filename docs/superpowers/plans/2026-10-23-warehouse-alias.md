# Literal warehouse alias conventions

Continue #16/#37 naming coverage after column conventions. Resolve at most one
applicable warehouse_alias rule using declared literal tokens, fixed bindings,
model scope and actual SQL parent directory. Missing scope/tokens, overlaps,
unsafe identifiers or known manifest model-name/alias collisions clarify.

Render an explicit dbt config(alias=...) prefix only when a rule applies. Keep
SQL filename, model ID and YAML model name unchanged. Record alias value, rule and
provenance; applied validation recomputes alias and checks metadata and exact bytes.
Default no-alias drafts and earlier envelopes remain compatible. No warehouse
queries, implicit aliases, executable templates or custom macro evaluation.

Known model name/alias collisions are checked conservatively across manifest
schemas/packages. This cannot certify effective relation uniqueness: target
schema/database and generate_alias_name/config behavior require operator review.

Tests first: success/quoted-safe literal rendering, missing inputs/scope/overlap,
collisions, injection rejection, identity preservation, no-rule compatibility,
MCP/real-dbt parse. Full suite, independent review, publish and verify CI.

## Verification record

Tests first reproduced the unsupported-target blocker. Eleven focused tests cover
literal rendering, collisions, scope/tokens/overlap, injection rejection, metadata
consistency, own-name compatibility, combined column/warehouse aliases, real stdio
and optional real dbt parsing. The runnable synthetic example resolves the expected
stage_xyz_customer_projection alias. Full-suite and final review results are reported
in the PR.
