# Project catalog scope and delta sync

User direction: fetch only sources and relations produced by the project. Sync the
delta when a source is added; quarantine ambiguous mappings for review.

- [x] Shared manifest-derived boundary before provider calls, used by planner/MCP.
- [x] Provider-local binding interface; scoped file search; no remote traversal.
- [x] Delta added/changed/removed sets and unchanged observation transfer.
- [x] Separate paged quarantine diagnostics, no automatic winner, unaffected assets continue.
- [x] Regression tests for missing scope, ephemeral output, identity conflicts,
  search exclusion, delta fetch counts, MCP context rotation, and quarantine repair.
- [x] Independent review; fix in-project identity ambiguity and blocked search leak.

Source YAML changes require a regenerated supported manifest. No watcher, SQL,
source rows, model generation or persistent cache is introduced. Full refresh
remains the explicit mechanism for retrying/revalidating unchanged remote assets.
