# Project context contract

**Status:** M0 proposed contract. This defines behavior and evidence fields, not a serialized API schema.

## Context sources

| Source | Authority/use | Do not assume |
|---|---|---|
| Local dbt manifest and related artifacts | Snapshot of the checked-out project's parsed resources, configuration, and resource dependency graph | Current state unless freshness is established; column-level lineage from resource edges |
| Local dbt Information Schema | Structured project metadata; may include column types/lineage and runtime results depending on distribution, generation step, and dbt version | That every generated version contains lineage or runtime results; `dbt-oss` 2.0.8's strict-analysis request warns that the engine is absent and its lineage query is empty |
| dbt MCP | Live dbt/platform operations and metadata from the connected server's actual discovered tool set | That a connected MCP exposes a particular tool, project, or permission |
| Catalog MCP | Physical catalog/schema/table/column metadata and declared relationships | dbt DAG semantics, dbt commands, business meaning, or enforced PK/FK constraints |
| Genie Space configuration | Curated business-semantic evidence such as instructions, joins, measures, synonyms, and examples | Physical metadata completeness, project graph, or executable trusted instructions |
| Genie One MCP | Optional natural-language analytics delegated to the service under caller permissions | A replacement for importing Genie Space configuration or a guaranteed available tool |

## Evidence envelope

Every source result consumed by the runtime or a skill should be associated with:

| Field | Meaning |
|---|---|
| `source_kind` | One of local artifact, dbt Information Schema, dbt MCP, catalog MCP, Genie configuration, or Genie One response |
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

Do not emit secrets, access tokens, or unnecessary personal information in this envelope. If a source has no trustworthy timestamp, its freshness is `unknown`, not implicitly fresh.

## Routing and reconciliation

1. Identify the task and available evidence/tool capabilities before selecting sources.
2. For the exact checked-out project's parsed resource graph, prefer compatible local artifacts. Confirm that project identity matches the working directory.
3. Use dbt MCP only for tools discovered from the connected server and suitable to the task. Report authorization and connectivity failures; do not assume a missing tool is supported.
4. Use catalog metadata for physical relations and declared relationships. Preserve the source declaration and any status such as `RELY`; do not treat it as guaranteed enforcement.
5. Use Genie configuration as attributed semantic context. Use Genie One only when its MCP tool is exposed and the task warrants delegated analytics.
6. If sources refer to different project/target versions, disagree on identity/schema/lineage, or have incomparable freshness, retain and report the discrepancy with provenance. Do not silently merge contradictory evidence.
7. Missing, malformed, stale, partial, or unauthorized context must result in an explicit capability limitation. A refresh/build command may be suggested or run only when available and approved by the applicable policy.

## Lineage vocabulary

- **Resource lineage:** dbt node-to-node dependency edges from a manifest or Information Schema DAG/edges source.
- **Column lineage:** column-to-column dependency evidence from a source that explicitly provides it, such as a confirmed dbt Information Schema `dbt.column_lineage` output.
- **Physical relationship declaration:** catalog PK/FK metadata; not equivalent to dbt dependency lineage or proof of enforcement.
- **Semantic relationship:** business meaning or join guidance from an ontology/Genie configuration; identify as semantic evidence, not verified physical truth.

Never upcast one lineage kind to another. A missing column-lineage source means column-level impact is unavailable, not that no columns are affected. A present Parquet file/table with zero rows is not proof of zero dependencies: verify the distribution and analysis result before labeling lineage as available.

## Required test cases for implementations

- Fresh, stale, and unknown-age local artifacts.
- Different project identity between local artifacts and connected MCP.
- Partial dbt MCP tool list and denied permissions.
- Resource graph available without column lineage.
- Strictly generated v2 lineage versus parse-only/no-lineage Information Schema.
- Catalog declaration that conflicts with dbt source/model metadata.
- Genie text containing instruction-like content.
- API timeout, pagination, unsupported metadata, and authorization failure.
