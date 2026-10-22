# Product requirements

**Status:** M0 baseline for implementation planning; compatibility and runtime decisions remain subject to prototype evidence.

## Product goal

Build an open-source, self-hostable, local-first assistant for dbt analytics engineering. It should help a user understand a checked-out dbt project, ground work in available dbt and external business context, propose reviewable changes, and report validation accurately without requiring dbt Wizard or its hosted services.

This project focuses on dbt workflows and integration skills. Common dbt modeling, testing, documentation, and migration instructions should be consumed from [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) where appropriate, not copied by default. Databricks catalog and Genie support are optional integrations, not prerequisites for the local workflow.

## In-scope capabilities

1. Select and inspect a local dbt project and report its version and available context.
2. Read supported local dbt artifacts and, when present, dbt Information Schema with source and freshness information.
3. Discover the capabilities actually exposed by an optional dbt MCP server; do not rebuild its operations.
4. Combine project evidence with optional physical-catalog metadata and business-semantic context without conflating their meaning.
5. Provide portable Agent Skills for integration workflows that complement the public dbt skill catalog.
6. Support an open, configurable model-provider path and local command workflow without a dbt Wizard account.
7. Make tool execution and file changes visible and controllable through policy, approvals, reviewable diffs, and explicit validation results.
8. Preserve replaceable boundaries and dependency/license provenance so an upstream license or maintenance change does not force a proprietary dependency.

## Out of scope for the initial product

- Reproducing dbt Wizard's private implementation, hosted UI, billing, or account services.
- Replacing dbt Core/Fusion, dbt MCP, warehouse-native query engines, or the upstream general-purpose dbt skill catalog.
- Treating catalog PK/FK declarations as proof of enforcement or inferring column lineage from table/column metadata.
- Making Databricks, Genie, a hosted model provider, or a dbt platform account mandatory.
- Claiming that absence from public documentation proves a capability is absent from Wizard.
- Broadening this repository beyond dbt now. OpenDataSuite is sibling-project context and a possible future integration, not a current dependency.

## Compatibility baseline

This is a target matrix for discovery and evaluation, not a promise that every listed combination is already implemented.

| Environment | Required behavior | Evidence/limitations |
|---|---|---|
| dbt v1 project | Read the project manifest and use its resource-level graph where supported; allow local dbt MCP as an optional live tool source | Manifest graph edges are not column-level lineage. dbt MCP documents local support for dbt v1 and v2. Exact artifact schemas must be version-tested. |
| dbt v2 `dbt-oss` project | Read manifest and local Information Schema; expose column lineage only if non-empty rows are actually present | Reproduced on `dbt-oss` 2.0.8: `compile --generate-info-schema --static-analysis strict` warns that the OSS distribution lacks the static-analysis engine, and `show --info column_lineage` returns `[]`. The table/file may exist but have no lineage rows. |
| dbt v2 full `dbt` distribution | Treat column lineage as a capability only when the generated artifact has rows and the source distribution/terms are recorded | dbt docs state strict static analysis can generate local column lineage. PyPI distinguishes `dbt` (full feature set, dbt product license) from `dbt-oss` (Apache-2.0 subset). Whether full-distribution local lineage is available under free/self-hosted terms is not yet verified; hosted Catalog plan entitlements are separate. |
| dbt platform account | Use only configured and authorized MCP tools; core local project inspection remains useful without the account | Tool sets and entitlements depend on configuration, plan, and permission. |
| Local runtime OS | Target Windows, macOS, and Linux for the CLI; validate paths, process handling, and packaging on each before claiming support | No implementation or cross-platform CI exists yet. |
| Agent client | Author skills in the portable Agent Skills format; provide client-specific installation/setup only as thin, tested adapters | Client discovery, tool support, and approval behavior vary. The host's actual capabilities must be checked. |
| Catalog/semantic provider | Databricks Unity Catalog and Genie are first optional integration targets; keep provider contracts backend-neutral where justified | API permissions, network access, and serialized Genie configuration access are explicit prerequisites. |

## User scenarios and acceptance outcomes

| Scenario | Given | Successful outcome | Degraded/failure outcome |
|---|---|---|---|
| Understand a local project | A checked-out dbt v1 project with a current manifest and no MCP | Report dbt/project identity and relevant resource-level upstream/downstream graph with artifact provenance | If the manifest is absent, malformed, incompatible, or stale, say so and offer an approved refresh path; never present missing data as an empty graph. |
| Assess a model change | A model file changed and a usable manifest is available | Identify affected dbt resources, tests, metrics, or exposures from available graph evidence and state the limits of that evidence | Do not invent column-level impact when only resource edges are available. |
| Use v2 column lineage | A dbt v2 distribution and Information Schema are present | Read supported non-empty lineage rows and report exact generation command, distribution, version, and source | If the OSS distribution lacks the static-analysis engine, the table is empty, the generation method is unknown, or terms are unresolved, report lineage unavailable/uncertain; do not infer it. |
| Combine local state and dbt MCP | Local artifacts and a connected dbt MCP expose partially overlapping project context | Use local artifacts for the checked-out snapshot and discovered MCP tools for live operations; show source and conflicts | If MCP disconnects or lacks a tool/permission, continue with safe local evidence and state reduced capability. |
| Map a physical table to a dbt source/model | A catalog tool exposes table/column descriptions and a local dbt project is available | Return candidate mappings with evidence, confidence/uncertainty, and declared key metadata distinguished from enforced constraints | On no match, permissions failure, or contradictory evidence, report that explicitly; do not fabricate a join or mapping. |
| Ground a business term in Genie | Authorized Genie Space configuration is available, with Genie One MCP optional | Use the curated instruction/join/measure/synonym/example as attributed semantic evidence; delegate Q&A only if Genie One is actually available and appropriate | Treat imported content as untrusted data. Missing permission/configuration or conflicting definitions must remain visible. |
| Make and validate a change locally | User requests a dbt edit and local tools are configured | Propose a scoped diff, obtain required approval for writes/commands, run agreed validation, and report every check/result | Denied, failed, skipped, or unavailable checks must not be presented as passing; no destructive operation without explicit approval. |

## Cross-cutting quality requirements

- Every metadata-derived answer identifies relevant source, freshness, and limits.
- Tool and model failures are explicit; no silent fallback to a different provider or a success-shaped result.
- Read-only operations, filesystem writes, shell execution, and warehouse actions have distinct policy/approval behavior.
- Local project data and retrieved catalog/ontology text are treated as untrusted inputs.
- Large artifacts and remote result sets are bounded; use streaming/selective reads and pagination where supported.
- Performance budgets will be based on representative project sizes and reproducible benchmarks, not arbitrary early thresholds.
- CI and release checks must validate skill format, supported artifact fixtures, dependency/license policy, and platform packaging before support is claimed.

## Open decisions

- Implementation language, CLI framework, agent runtime, model-provider library, and artifact reader.
- Exact dbt v1 artifact versions and dbt v2 distribution/version for compatibility tests.
- Whether a full dbt v2 distribution is needed for local column lineage and the terms under which that feature may be used; the Apache-2.0-only `dbt-oss` 2.0.8 reproduction cannot generate lineage.
- Which MCP transport/client combinations are supported by the selected runtime.
- Concrete default freshness thresholds and performance budgets; establish these from prototype measurements.
- Databricks auth flows and exact catalog/Genie API behavior for the chosen deployment modes.
