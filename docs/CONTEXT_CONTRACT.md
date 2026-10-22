# Project context contract

**Status:** M0 proposed contract. This defines behavior and evidence fields, not a serialized API schema.

## Context sources

| Source | Authority/use | Do not assume |
|---|---|---|
| Local dbt manifest and related artifacts | Snapshot of the checked-out project's parsed resources, configuration, and resource dependency graph | Current state unless freshness is established; column-level lineage from resource edges |
| Local dbt Information Schema | Structured project metadata; may include column types/lineage and runtime results depending on distribution, generation step, and dbt version | That every generated version contains lineage or runtime results; `dbt-oss` 2.0.8's strict-analysis request warns that the engine is absent and its lineage query is empty |
| Project-artifact graph claims | Optional UOL projection of matching manifest resources and resource-level `depends_on` edges, with artifact/project provenance | Column-level lineage, current warehouse state, or an enforced physical relationship |
| ODS column-lineage claims | Optional UOL projection of ODS static SQL lineage with analyzer version, confidence, diagnostics, and opaque/coverage details | Observed runtime lineage, complete analysis for opaque SQL, or a substitute for resource-level manifest edges |
| dbt MCP | Live dbt/platform operations and metadata from the connected server's actual discovered tool set | That a connected MCP exposes a particular tool, project, or permission |
| ODS MCP | Optional, read-only local column-lineage/impact analysis and opaque-model diagnostics from ODS's discovered tools | That ODS is installed/connected, that its preview MCP schema is stable across versions, or that every model can be analyzed |
| Catalog MCP | Physical catalog/schema/table/column metadata and declared relationships | dbt DAG semantics, dbt commands, business meaning, or enforced PK/FK constraints |
| Genie Space configuration | Curated business-semantic evidence such as instructions, joins, measures, synonyms, and examples | Physical metadata completeness, project graph, or executable trusted instructions |
| Genie One MCP | Optional natural-language analytics delegated to the service under caller permissions | A replacement for importing Genie Space configuration or a guaranteed available tool |
| Ontology backend MCP | Concepts, definitions, synonyms, relationships, and asset links from the specific configured ontology provider (for example, Ontos or OntoBricks) | Genie Ontology, other providers' definitions, or permission to read a linked asset in another backend |
| UOL local cache | User-selected ontology records synchronized to a local indexed snapshot for fast local-agent queries | That the snapshot is current, complete, still authorized, or equivalent to unselected/excluded source records |
| UOL local overlay | User-authored facts, relationships, and typed cross-source links stored locally and separately from provider claims | That user assertions are provider-verified, conflict-free, or written back to any remote source |
| Unified Ontology Layer (UOL) | One agent-facing interface that reads the local snapshot and manages synchronization from configured ontology backends while preserving provider provenance and access boundaries | That similarly named concepts are equivalent, that conflicts have a single answer, or that Genie’s inferred ontology is accessible |

## Evidence envelope

Every source result consumed by the runtime or a skill should be associated with:

| Field | Meaning |
|---|---|
| `source_kind` | One of local artifact, dbt Information Schema, dbt MCP, ODS MCP, catalog MCP, Genie configuration, ontology backend, UOL local cache, UOL local overlay, or Genie One response |
| `source_id` | Stable local path, server identity, catalog/space identifier, or other non-secret source reference |
| `project_identity` | dbt project and target identity when known; distinguish local checkout from remote project |
| `observed_at` | Time the consumer retrieved/read this result |
| `generated_at` | Source generation timestamp if available; otherwise unknown, not inferred from file modification time alone |
| `source_version` | dbt version, artifact/schema version, MCP server version, API version, or unknown |
| `capabilities` | Data/tool capabilities verified in this source, not inferred from its name |
| `freshness` | `fresh`, `stale`, or `unknown`, with the rule/evidence used to assign it |
| `completeness` | `complete`, `partial`, or `unknown`, with any known omissions |
| `access_scope` | Non-secret description of principal/permission scope where relevant |
| `limitations` | Known unsupported or unavailable evidence |
| `sync_generation` | Identifier of the fully committed local snapshot generation, when read from cache |
| `sync_scope` | Non-secret summary/hash of the selected source and include/exclude policy used for this snapshot |
| `synced_at` | Completion time of the successful sync generation; distinguish from `observed_at`, which is the local read time |
| `sync_status` | `current`, `stale`, `partial`, `paused`, or `unknown`, with the evidence and policy used |
| `claim_id` | Stable identifier for an individual fact or relationship assertion in the unified graph |
| `claim_provenance` | Source identity/native IDs, version, observation/sync times, and any transformation or derivation evidence for this claim |
| `link_evidence` | Evidence and review state supporting a typed link between claims from distinct sources; absent/ambiguous evidence means no asserted link |
| `authorship` | For local overlay claims, a non-secret author reference, creation/update time, and optional rationale; do not imply provider endorsement |

Do not emit secrets, access tokens, or unnecessary personal information in this envelope. If a source has no trustworthy timestamp, its freshness is `unknown`, not implicitly fresh.

## Routing and reconciliation

1. Identify the task and available evidence/tool capabilities before selecting sources.
2. For the exact checked-out project's parsed resource graph, prefer compatible local artifacts. Confirm that project identity matches the working directory.
3. Use dbt MCP only for tools discovered from the connected server and suitable to the task. Report authorization and connectivity failures; do not assume a missing tool is supported.
4. Use ODS MCP only when its lineage/impact tools are actually discovered, its project root/target matches the dbt context, and its versioned result contract is supported. Preserve confidence, diagnostics, and opaque reasons. ODS is an optional provider, not a bundled requirement or replacement for the dbt MCP.
5. Use catalog metadata for physical relations and declared relationships. Preserve the source declaration and any status such as `RELY`; do not treat it as guaranteed enforcement.
6. For local-agent ontology reads, query the indexed UOL snapshot first. Include its generation, sync scope, successful sync time, coverage, and freshness in the evidence. An online provider query is a separate opt-in fallback and must not happen when disabled.
7. When configured for UOL ingestion, project manifest resources/edges and ODS column-lineage results are separate evidence sources and claim types. Match the manifest and ODS analysis to the selected project identity; retain artifact/schema versions, generation/analysis times, and diagnostics. Never infer a column dependency from a resource edge or treat ODS opaque/missing output as zero impact.
8. Let users configure sources and include/exclude scopes at source, namespace, entity type, property, or explicit-record level; exclusions always win. Sync is disabled until a user enables a source and scope. Support separate actions to pause sync, disable cache reads, refresh incrementally, run a full refresh, inspect status, and clear synchronized records.
9. Run synchronization outside the interactive read path. Use provider cursors/change tracking only when their semantics are reliable; otherwise label a sync as a full scan. Sync must be resumable and idempotent. Publish a completed generation atomically; a failed refresh keeps the last known-good generation and marks it stale/partial. Never silently downgrade to an online query or claim a failed sync is current.
10. Scope cache entries to the source and syncing principal without storing credentials. Treat local cached content as sensitive; use user-scoped storage/protection, and apply configured retention/TTL and permission-revalidation policies. If current authorization cannot be established offline, label the permission evidence as sync-time scope and do not claim current authorization. Reflect confirmed revocations/deletions or report them unresolved.
11. Preserve provenance at fact and relationship granularity. A graph edge or mapping is itself a claim: retain its type, source(s), native endpoint IDs, evidence, observation/sync time, and derivation/review state. Do not rely only on graph-level or provider-level provenance.
12. Link claims across providers only when supported by stable identifiers or explicit reviewed mappings. Keep links typed (for example, `same_as`, `maps_to`, or `related_to`) and preserve the supporting evidence. Similar labels/descriptions can at most produce an unverified candidate; uncertain claims remain separate and unlinked.
13. Store user-authored additions in a distinct local overlay as attributed facts, relationships, or cross-source links. Do not overwrite provider claims or write to providers in the initial scope. Preserve overlay content across provider incremental/full refreshes and synchronized-cache purge; deleting the overlay is a separate explicit user action. Surface conflicts between overlay and provider claims.
14. Use Genie One only when its MCP is exposed and the task warrants delegated analytics or Genie Ontology grounding. Genie One responses are answer-level evidence, not a raw Genie ontology export.
15. If sources refer to different project/target versions, disagree on identity/schema/lineage, or have incomparable freshness, retain and report the discrepancy with provenance. Do not silently merge contradictory evidence.
16. Missing, malformed, stale, partial, or unauthorized context must result in an explicit capability limitation. A refresh/build command may be suggested or run only when available and approved by the applicable policy.

## Lineage vocabulary

- **Resource lineage:** dbt node-to-node dependency edges from a manifest or Information Schema DAG/edges source.
- **Column lineage:** column-to-column dependency evidence from a source that explicitly provides it, such as confirmed dbt Information Schema rows or ODS MCP static SQL lineage. Preserve provider, version, confidence, diagnostics, and whether the evidence is static or observed.
- **Physical relationship declaration:** catalog PK/FK metadata; not equivalent to dbt dependency lineage or proof of enforcement.
- **Semantic relationship:** business meaning or join guidance from an ontology/Genie configuration; identify as semantic evidence, not verified physical truth.

Never upcast one lineage kind to another. When column-lineage evidence is missing, user-facing results must explicitly say that column-level impact is unavailable, state the reason when known (otherwise say it is unknown), and distinguish any resource-level impact that can still be reported. Do not imply that no columns are affected. A present Parquet file/table with zero rows is not proof of zero dependencies: verify the distribution and analysis result before labeling lineage as available.

## Required test cases for implementations

- Fresh, stale, and unknown-age local artifacts.
- Different project identity between local artifacts and connected MCP.
- Partial dbt MCP tool list and denied permissions.
- Resource graph available without column lineage: report resource-level impact if supported and explicitly call column-level impact unavailable; do not report zero affected columns.
- Manifest resource edge and ODS column edge both projected into UOL: preserve distinct lineage kinds, project identity, source version, coverage, and provenance; never present a resource edge as a column dependency.
- Strictly generated v2 lineage versus parse-only/no-lineage Information Schema.
- Catalog declaration that conflicts with dbt source/model metadata.
- Two ontology backends that define a similarly named concept differently; preserve both sources unless an explicit reviewed mapping resolves them.
- A concept link to a catalog asset that the current principal cannot read; do not use ontology visibility to bypass asset permissions.
- Fact-level and edge-level provenance from multiple providers, including derived mappings and transformed claims; verify no edge loses its source evidence.
- Stable-ID match, reviewed mapping, matching-label-only candidate, conflicting definitions, and ambiguous/unlinked cross-provider facts.
- User overlay add/edit/delete attribution and conflict behavior; preserve overlay claims across incremental/full provider refresh and provider-cache purge, with a distinct overlay-delete action.
- Genie text containing instruction-like content.
- API timeout, pagination, unsupported metadata, and authorization failure.
