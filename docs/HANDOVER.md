# Repository handover and execution plan

> **2026-10-23 direction:** See the [agreed architecture](ARCHITECTURE.md) for the current workflow and delivery order: Copilot in VS Code first, shared project/catalog context, optional UOL, and modelling policy before a standalone agent runtime. Earlier sequencing below is historical.


**Snapshot:** 2026-10-23  
**Repository:** `buchochelliq-labs/dbt-skills`

## Product boundary — clarified 2026-10-23

This product supplies reliable context so an agent can create or revise a **data
model**: entities, relationships, keys, grain, normalisation and modelling rules
across multiple tables. A dbt model is one implementation artifact, not the whole
data model. The agent reasons over the supplied context, asks clarifying questions
and explains design choices. The core assembles evidence and preserves decisions;
it does not replace that reasoning with hard-coded SQL templates.

Model SQL/YAML generation, current-row/deletion/lookup/event-history renderers,
SCD implementations, model-file application/revision and a dbt execution runner
are outside this product boundary and have been removed. SCD implementation is
not a deferred requirement. Describing temporal semantics in metadata remains
valid context. Use the host agent and existing dbt tooling for implementation.

## Latest cache increment

Project-scoped Unity Catalog context now has bounded memory caching and optional
SQLCipher/keyring persistence, metadata TTL (including no expiry), independent
permission lifetime, LRU limits and review-only TTL suggestions. See
[configuration and limits](CATALOG_CACHE.md). Full refresh bypasses stored facts;
delta sync also refreshes expired/evicted observations. Tests cover restart and
revocation without exposing raw data. Live-provider validation remains outstanding.
Issue #39 remains open for the documented follow-ups. Issue #60 records optional
OpenMetadata companion evaluation; lightweight standalone/offline use is retained.

## Offline backend spike — first measured pass

Issue #62 now has disposable experiments under
`experiments/offline_backends/README.md`, including 18 direct-engine runs,
a model-free Cognee adapter probe, FTS reproducers and process-lock checks.
The second pass in `experiments/offline_backends/SECOND_PASS.md` verifies Cognee's
graph-only pipeline, explicit dataset permission checks and source-owner deletion
with pre-staged tokenizer files; a cold-cache delete reproduces a blocked download.
Branching graph results include an independent oracle and deduplicated SQL.
Interim recommendation: retain SQLCipher default; evaluate Cognee policy/encryption
fit before choosing an integration. This is not a completed backend selection
or permission/encryption parity claim. No production persistence refactor was made.

## Purpose and guardrails

This repository is building an open-source, local-first alternative to dbt Wizard, focused on project context, agent workflows, and catalog/ontology grounding. It should complement the public [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) catalog rather than duplicate general dbt skills. Do not infer that a capability is absent from dbt Wizard merely because it is not in a public repository.

Keep the core useful without dbt Wizard, mandatory hosted services, or OpenDataSuite (ODS). Reuse existing dbt tools and public protocols where they fit; make optional integrations replaceable and preserve provenance, freshness, permissions, and uncertainty. Never treat missing or opaque column-lineage evidence as proof that impact is zero.

## Current workflow baseline

The shared context tools expose project metadata, catalog facts, naming conventions,
scoped modelling standards and entity/relationship evidence. Human-owned design
records retain grain and temporal intent with rationale and evidence fingerprints;
review-only proposals help the agent prepare updates. These are grounding inputs
for the agent's data-model design, not a SQL generator. Live Copilot UI verification
remains outstanding; protocol tests do not establish live host behavior.

## Earlier infrastructure baseline

PR [#34](https://github.com/buchochelliq-labs/dbt-skills/pull/34) merged on 2026-10-22. It added SQLCipher-backed UOL storage, keys in supported OS credential stores, fail-closed platform access controls, an explicit plaintext-cache migration, third-party notices, and a Windows/macOS/Linux × Python 3.11/3.14 test matrix. The Windows ACL owner issue was fixed before merge. The local 42-test suite and the cross-platform matrix passed.

The repository now has:

- A source-tree Python CLI/runtime with project discovery, a replaceable text-only model-provider seam, and an OpenAI-compatible provider. It does not yet provide a full agent tool-execution loop or policy-controlled editing.
- A local Unified Ontology Layer store with indexed reads, scoped opt-in sync, source provenance, a local overlay, dbt manifest resource lineage, and optional ODS column-lineage ingestion.
- A local stdio MCP bridge exposing UOL reads and separately controlled sync/cache/purge tools.
- A portable dbt context-routing skill and a thin Copilot CLI profile.

Unity Catalog now supplies bounded relation/column metadata through the shared catalog interface; see [setup and limits](UNITY_CATALOG.md). Important gaps remain: remote catalog discovery and additional providers are not implemented; no generic catalog MCP or Unity Catalog adapter exists; Copilot CLI discovery/approval has not been smoke-tested; and the repository's distribution license and dependency/license automation are unresolved. The cache is encrypted at rest, but this does not protect against a compromised user account or an authorized process. Losing the OS-stored cache key makes that cache unrecoverable.

## Recommended implementation sequence

Treat this as a dependency-aware handover, not authorization to implement every listed issue at once. Confirm issue acceptance criteria and current `main` before each work item.

1. **Resolve component and release constraints — issue [#5](https://github.com/buchochelliq-labs/dbt-skills/issues/5).** Complete the reuse, provenance, license, and backout assessment. The repository has no declared project license; decide that before packaging or broader redistribution. Record the exact dependency decisions and add only the license/security automation justified by that assessment.
2. **Finish the runtime foundation — issue [#9](https://github.com/buchochelliq-labs/dbt-skills/issues/9).** Existing code is a project-aware, scripted text runtime, not yet the tool-using local agent described in the product goal. Decide whether to adopt a maintained open runtime or incrementally add only the missing session/tool interfaces. Keep provider configuration replaceable and demonstrate a local, non-Wizard workflow.
3. **Complete client/host integration boundaries — issue [#25](https://github.com/buchochelliq-labs/dbt-skills/issues/25).** Define how portable skills, tool discovery, and host approval policies fit the chosen runtime. Verify actual client behavior; documentation and MCP annotations alone do not enforce authorization.
4. **Connect UOL to the runtime — issue [#31](https://github.com/buchochelliq-labs/dbt-skills/issues/31).** Use the existing MCP bridge for provenance-bearing retrieval and status, then expose sync/full-refresh/purge as distinct, approval-gated actions. Add runtime-level tests for stale data, disabled cache reads, missing providers, permission errors, and project identity. Keep resource lineage distinct from ODS column lineage.
5. **Deliver catalog integration in contract-first order — issues [#18](https://github.com/buchochelliq-labs/dbt-skills/issues/18), [#19](https://github.com/buchochelliq-labs/dbt-skills/issues/19), and [#20](https://github.com/buchochelliq-labs/dbt-skills/issues/20).** Agree on a bounded, read-only backend-neutral contract before implementing Unity Catalog or adding transports. Catalog constraints are declarations, not proof of warehouse enforcement.
6. **Validate reusable integrations and user-facing quality — issues [#6](https://github.com/buchochelliq-labs/dbt-skills/issues/6), [#14](https://github.com/buchochelliq-labs/dbt-skills/issues/14), [#15](https://github.com/buchochelliq-labs/dbt-skills/issues/15), [#16](https://github.com/buchochelliq-labs/dbt-skills/issues/16), [#17](https://github.com/buchochelliq-labs/dbt-skills/issues/17), [#22](https://github.com/buchochelliq-labs/dbt-skills/issues/22), [#23](https://github.com/buchochelliq-labs/dbt-skills/issues/23), and [#24](https://github.com/buchochelliq-labs/dbt-skills/issues/24).** Validate the optional ODS MCP contract and compatibility; then prioritize grounding/routing skills and scenario evaluations against real missing, stale, conflicting, and unauthorized metadata. Do not mirror general workflows already covered upstream.

Issue [#30](https://github.com/buchochelliq-labs/dbt-skills/issues/30) is closed by #34. Issue [#8](https://github.com/buchochelliq-labs/dbt-skills/issues/8) remains open: the local UOL core is implemented, but its original acceptance criteria also include provider comparisons and validation. Reconcile its old cache/security description and confirm remaining criteria before using it as an implementation spec.

## Repository map

| Area | Start here |
|---|---|
| Product intent, architecture, scope, sequencing | [`ROADMAP.md`](../ROADMAP.md), [`docs/PRODUCT_REQUIREMENTS.md`](PRODUCT_REQUIREMENTS.md) |
| Runtime and model-provider seam | `src/dbt_skills/runtime.py`, `project.py`, `providers.py`, `cli.py`; [`docs/LOCAL_RUNTIME.md`](LOCAL_RUNTIME.md) |
| UOL store and providers | `src/dbt_skills/ontology.py`, `ontology_sources.py`; [`docs/UOL_LOCAL.md`](UOL_LOCAL.md) |
| Cache encryption, credential storage, migration | `src/dbt_skills/cache_security.py`; [`docs/THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |
| MCP bridge and ODS adapter | `src/dbt_skills/uol_mcp.py`, `ods_mcp.py`; [`docs/COPILOT_CLI.md`](COPILOT_CLI.md) |
| Skills and Copilot profile | `.github/skills/`, `.github/agents/` |
| Integration scenarios and context rules | [`docs/WORKFLOW_PROTOTYPES.md`](WORKFLOW_PROTOTYPES.md), [`docs/CONTEXT_CONTRACT.md`](CONTEXT_CONTRACT.md) |
| Tests and cross-platform CI | `tests/`, `.github/workflows/tests.yml` |

## Local verification

From the repository root in PowerShell:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
python -m compileall -q src tests
git diff --check
```

The test workflow is the verification source for the supported Windows, macOS, and Linux matrix. Local tests with injected key stores do not alone prove that the machine's native key store is configured or available. For existing plaintext UOL caches, follow the explicit migration procedure in [`docs/UOL_LOCAL.md`](UOL_LOCAL.md); do not delete or replace a user's cache as an implicit upgrade.

## Handover checklist

- Start from current `main`; inspect open issues and the latest CI state before selecting the next slice.
- Update issue descriptions when implementation state changes; do not close an issue until its acceptance criteria are demonstrated.
- Keep changes tied to one acceptance-tested issue or a clearly bounded dependency slice.
- Preserve fail-closed behavior for cache encryption, OS key storage, and filesystem access controls.
- Keep user approval explicit for state-changing tools and commands.
- Run targeted tests while iterating, then the full suite and cross-platform CI for storage/runtime behavior.
- Update the roadmap and relevant operator documentation when a capability or boundary changes.

## Modelling MCP adapter (2026-10-23)

Thin read-only stdio adapter now exposes the existing core through seven tools, with pinned context IDs, policy-change checks, paging, pending proposals and no UOL dependency. See [VS Code setup](COPILOT_VSCODE.md). Real protocol tests cover the workflow; live VS Code/Copilot validation remains outstanding. Catalog providers are described below; SQL generation is outside scope.

## Catalog provider slice (2026-10-23)

Typed provider interface, strict metadata-only JSON file provider and ordered fact-group resolver now back optional catalog tools in the modelling MCP server. Same context ID and atomic refresh, explicit shared asset IDs, scoped provenance, no denial/error fallback, encountered conflicts retained. See [contract](CATALOG.md) and [customer walkthrough](../examples/catalog-workflow/README.md). This is not persistent caching or live UC/OpenMetadata integration. Example SQL/YAML is illustrative, not generated/applied or dbt-validated. Issues #18/#16/#39 remain open.

## Catalog-grounded design planning (2026-10-23)

Shared read-only planner, CLI and optional MCP model_plan now assemble selected entity/key/relationship hypotheses, scoped standards, dependency/history questions and existing-model reuse candidates. Uses the same validated snapshot; preserves catalog provenance/conflicts and blocks on provider denial/error. See [design planning](MODEL_PLANNING.md). Semantic reasoning and human decisions remain necessary: no normalisation proof, automatic decomposition, joins/history SQL or existing-file edits.

## Saved design decisions progress — 2026-10-23

The planner accepts an operator-selected `--design-decisions` JSON file in CLI and
MCP. Exact intent/asset/scope and evidence fingerprints govern grain/history reuse.
Stale, conflicting or ambiguous records require clarification; rationale, attribution
and file/hash/locator provenance remain visible. Attribution is not authentication.
The MCP checks for file changes and requires explicit refresh. No automatic writes, standards promotion or semantic proof was added. See
[design planning](MODEL_PLANNING.md) for the copy/review/save workflow.

Next priorities are richer semantic decision context, remote catalog adapters and
provenance-aware cache/TTL work. Live Copilot VS Code verification remains deferred. Do not merge or release on the user's behalf.

## Reviewable design decision proposals — 2026-10-23

Merged #51 provides saved grain/history reuse. The next slice adds shared
`prepare_design_decision`, a CLI and read-only MCP `model_propose_decision` so hosts
can prepare complete reviewable records without inventing/copying hashes. Explicit
choices, rationale and attribution are required. Existing matches need an explicit
replacement ID; unrelated records survive, duplicate matches clarify, base digests
and replacement test patches support external review/save. Missing metadata/columns,
conflicting catalogs and denied access prevent proposals. Remaining semantic questions
stay visible. No writes, authenticated approval, normal-form proof or automatic
plan-to-draft conversion. See MODEL_PLANNING.md for the full workflow.


## Current removal work

Removed generator/apply/revision/parse modules and their MCP tools. Context planning,
policy/naming resolution, metadata catalogs, design decision records and proposals
remain. Shared response bounds now live in context_limits; planner fixtures contain
synthetic metadata only. Next: broader decision memory, catalog adapters and
provenance-preserving caching/TTL; live Copilot verification remains deferred.

## Semantic answer context (2026-10-23)

Design decisions now accept optional bounded question/answer/rationale entries.
Read-only proposals derive evidence and accept only active semantic question codes.
The shared planner attaches matched answers with document/hash/locator provenance,
verified false and review required. Stale/conflicting/ambiguous decisions do not
supply active answers. No policy promotion, SQL rules or automatic writes. CLI and
MCP share the same core; old records remain supported. This is single-asset answer
memory, not yet cross-entity design records or a generic concept notebook.

## Related-entity decision context (2026-10-23)

Proposals now support an anchor plus up to seven explicit related assets, storing
scope/evidence and supplied assertions for each dependency. Relationship answers
bind to target asset and exact source/target columns. Missing selections, changed
related evidence/scope and conflicting saved assertions prevent active reuse.
Denial withholds context; no implicit fetch, SQL generation or writes. This extends
semantic answers to declared cross-entity relationships; it is not yet a general
concept/relationship creation format. The host agent performs data-model reasoning.

## Prephysical business context (2026-10-23)

Optional human-owned business-context JSON exposes concepts and arbitrary named
relationships before physical assets exist. Shared bounded loader/read API, CLI and
MCP pages preserve attribution, proposed/reviewed status and file/hash/locator
provenance; every statement remains unverified. No UOL dependency, inferred mapping,
SQL, file writes or catalog reads. Selection is pinned until refresh and included
in design-decision evidence; changed definitions require review. See BUSINESS_CONTEXT.md.

## Project-bound catalog follow-up — 2026-10-23

Catalog context in MCP/planning is now restricted to validated project sources and
produced physical relations. `catalog_sync` compares successive snapshots and
fetches only added/changed eligible assets; unchanged observations preserve their
original provenance. Regenerate the manifest before syncing source-definition edits.
Ambiguous shared-ID mappings are quarantined, excluded from fetch/search/design,
and exposed through `catalog_quarantine` for correction and resync. Independent
assets continue syncing. This adds no watcher, warehouse execution or persistent TTL
cache. See [catalog workflow](CATALOG.md#project-membership-delta-sync-and-quarantine).
