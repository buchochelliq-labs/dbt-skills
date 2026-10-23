# Related-entity decision context

Extend existing human-owned decisions with optional related_contexts for up to
seven other explicitly selected assets. Each stores asset ID, scope, evidence and
any supplied grain/history assertions. First asset remains the decision's anchor;
other assets are evidence dependencies, not independently approved decisions.

Add confirm_relationship answers targeted by target_asset. Require an active
relationship question on the anchor, bind its target to a selected related context,
and never transfer an answer between targets. Preserve old single-asset records.
Proposals collect fingerprints from the shared planner, never caller hashes.

Planner reuse checks every dependency. Missing selections => incomplete; changed
scope/evidence => stale; changed explicit saved assertions => conflict. None of
these may supply active answers or saved grain/history. No implicit catalog fetch,
SQL generation, writes, semantic proof or global policy updates.

Test multi-asset roundtrip/provenance, target drift, missing target, wrong answer
target, explicit assertion conflicts, duplicate dependencies, denial and MCP
refresh. Full suite, independent review, publish and CI; no merge or release.
