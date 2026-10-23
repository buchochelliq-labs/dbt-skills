# Event history intervals

Goal: generate one row per source event, business key plus validity start as output
grain, [valid_from, valid_to) intervals using LEAD(effective_at) partitioned by grain.
Latest valid_to is null. Require complete source events and unique/non-null effective
time per key as explicit assertions; date/timestamp metadata only. Retain deletion
events, no filtering/deduplication or inferred snapshot capture. Explicit table/view
materialization prevents inherited incremental append semantics.

Request history=historical and history_rule with effective_at, events=assert_complete,
ordering=assert_unique_non_null, deletions=retain_events, materialization=table|view,
rationale, optional column_context for synthetic valid_from/valid_to fields. Use
existing column naming resolver for generated fields; output collisions clarify.
Reject effective_at as a business grain key; grain describes entity not event.
Reject combination with lookup/current_row and misplaced history_rule.

Keep business key not-null tests, remove single-business-key uniqueness for history.
Generated valid_from has not-null test; composite event-grain uniqueness and ordering
assertions remain unverified. Shared prepare/render/validate; unchanged projections.
Test interval execution on synthetic out-of-order events, partitions/null final bounds,
naming/collisions/metadata/assumptions, apply validation, MCP and real dbt parse.
Full suite, independent review, PR/CI. No warehouse data, merge or release.

Review fix: historical output-grain validation is mandatory even if optional mapping
metadata is removed. Reproduced the bypass with a failing applied-validation test.
Integration: target main with reviewed stacked changes from #53–#55, which were
merged into feature branches but not main as of the repository check.
