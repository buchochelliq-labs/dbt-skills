# Applied draft validation

Spec: #11/#16, architecture privacy boundary. Continue PR #47 while it remains open.
1. TDD read-only validation of generated draft integrity, exact applied file bytes,
   captured input hashes, model inventory and the restricted projection contract.
   Fixed check codes only; no source contents, arbitrary errors or raw paths in report.
2. Operator-only parse runner: explicit reviewed digest, successful local checks,
   absolute executable/profiles selection, fixed dbt parse arguments, no shell,
   timeout, stdin/stdout/stderr suppressed, temporary logs/target, no artifact release.
   dbt/project code is trusted operator code, not a sandbox. No compile/run/test/probes.
3. MCP validates only server-retained draft IDs (bounded cache), no arbitrary path or
   supplied envelope. Refresh invalidates cache. No execution tool exposed.
4. Real stdio/unit tests, optional real dbt-duckdb parse smoke in isolated fixture,
   docs, independent review, full suite and remote CI. Do not merge/release.
