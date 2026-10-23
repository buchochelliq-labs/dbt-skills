# Revisions of unchanged generated models

Extend prepare/review/apply/validate to revise exactly the SQL/YAML pair from a saved,
previously applied generated draft. Validate the old draft (bytes, evidence, inventory,
contract) before proposing. New request reuses existing renderer through an internal
replacement-path allowance; paths cannot change. No arbitrary file adoption or SQL
patch interpretation. Evidence/inventory changes or hand edits require a separate
future workflow, not silent rebasing.

Return a bounded model_revision envelope with base/proposed drafts, exact old/new
hashes and unified diffs, sealed revision_id. CLI applies only exact operator-approved
revision digest. Check base and proposed contracts before writes, stage both files,
replace with per-file baseline checks, preserve modes, validate afterwards; on failure
restore only files still matching this operation's output and report failure. Two-file
replacement is not atomic; hostile concurrent mutations remain out of contract.
MCP model_revise uses only a retained draft ID + request; no apply/write/path tool.

Tests first: read-only proposal, changed bytes/evidence/path rejection, wrong approval,
success/repeated revisions, second-write failure rollback, symlinks, CLI and MCP.
Full suite, independent review, docs/PR/CI. Target main; do not merge/release.
