# Catalog provider and local model-design example

Spec: docs/ARCHITECTURE.md and issues #18/#16. User approved file provider first,
ordered fact resolution, metadata-only context and a concrete model-creation example.

1. Add failing contract tests, then a typed provider seam, strict bounded JSON file
   provider and ordered resolver. Exact explicitly shared asset IDs only; no name-based
   joins. Fact groups: relation, columns, primary_key, foreign_keys. Unknown differs
   from explicitly empty. Stop when sufficient; preserve encountered overlaps/conflicts;
   denial/error stops resolution without releasing partial facts. No arbitrary text,
   sample values, SQL or error excerpts. Track document digest, locator, native ID,
   source/retrieval time, scope and declared evidence. Never claim truth verification.
2. Add tests then optional startup catalog configuration to modelling MCP, using the
   same context ID/refresh boundary. Bounded provider-specific discovery, status and
   fact resolution tools. No new runtime, warehouse access, UOL dependency or writes.
3. Add a small metadata-only two-provider example and executable walkthrough from
   source discovery to naming/design questions, plus explicitly illustrative SQL/YAML.
   Do not claim automated model generation or successful dbt/warehouse validation.
4. Run full tests, compilation/diff checks and independent whole-change review. Publish
   a focused PR and verify cross-platform CI. Keep #18 open for broader discovery/
   provider contracts; #16 remains open for generation and reviewed application.

Design choices: strict JSON for this initial catalog/config format; modelling policy
continues to support YAML. Free-text descriptions omitted until explicit release policy.
Simple normalized types only, unknown supported. Shared IDs in curated files are human
identity assertions; live providers must use stable IDs or reviewed mapping later.
No persistent cache/TTL in this slice. Pinned metadata checks source digest/access on
use; changed files require refresh, deletion/errors fail closed. Optional HTTP and
remote catalogs remain follow-ups. Existing main source tree retained, isolated branch.

Progress:
- Contract/file provider/resolver implemented after failing import and behavior tests.
- Optional MCP catalog tools implemented after real stdio startup failed for the new option.
- Two-provider customer example exercises real resolution/naming; SQL/YAML remains an
  illustrative review draft, not automated generation or executed validation.
- Independent review found mixed scopes in a single provider response; regression
  reproduced, fixed with per-response scope/native-ID consistency checks.
- Extra invalid-date test exposed optional jsonschema date-time validation; replaced
  with a local mandatory ISO timestamp checker and verified the regression passes.
- Final local verification: 135 tests pass; compileall and git diff --check pass.
- No deferred review findings. Remote PR/CI verification follows publication.
