# Product requirements

**Status:** M0 baseline for implementation planning; compatibility and runtime decisions remain subject to prototype evidence.

## Product goal

Build an open-source, self-hostable, local-first assistant for dbt analytics engineering. It should help a user understand a checked-out dbt project, ground work in available dbt and external business context, propose reviewable changes, and report validation accurately without requiring dbt Wizard or its hosted services.

This project focuses on dbt workflows and integration skills. Common dbt modeling, testing, documentation, and migration instructions should be consumed from [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) where appropriate, not copied by default. Databricks catalog and ontology providers are optional integrations, not prerequisites for the local workflow.

## In-scope capabilities

1. Select and inspect a local dbt project and report its version and available context.
2. Read supported local dbt artifacts and, when present, dbt Information Schema with source and freshness information.
3. Discover the capabilities actually exposed by an optional dbt MCP server; do not rebuild its operations.
4. Combine project evidence with optional physical-catalog metadata and the **Unified Ontology Layer (UOL)**, without conflating their meaning.
5. Provide portable Agent Skills for integration workflows that complement the public dbt skill catalog.
6. Support an open, configurable model-provider path and local command workflow without a dbt Wizard account.
7. Make tool execution and file changes visible and controllable through policy, approvals, reviewable diffs, and explicit validation results.
8. Preserve replaceable boundaries and dependency/license provenance so an upstream license or maintenance change does not force a proprietary dependency.
9. Keep ontology augmentation available to the local agent through a user-controlled local cache, with explicit source/scope selection, pause/disable, incremental sync, full refresh, status, and purge controls.
10. Preserve claim-level provenance and let users add attributed local facts, relationships, and verified cross-source links without mutating provider sources.

## Out of scope for the initial product

- Reproducing dbt Wizard's private implementation, hosted UI, billing, or account services.
- Replacing dbt Core/Fusion, dbt MCP, warehouse-native query engines, or the upstream general-purpose dbt skill catalog.
- Treating catalog PK/FK declarations as proof of enforcement or inferring column lineage from table/column metadata.
- Making Databricks, Genie, a hosted model provider, or a dbt platform account mandatory.
- Claiming that absence from public documentation proves a capability is absent from Wizard.
- Broadening this repository beyond dbt. OpenDataSuite remains a sibling project and is not bundled or required; an optional ODS MCP connection may supply column-lineage and impact evidence for dbt projects.

## Compatibility baseline

This is a target matrix for discovery and evaluation, not a promise that every listed combination is already implemented.

| Environment | Required behavior | Evidence/limitations |
|---|---|---|
| dbt v1 project | Read the project manifest and use its resource-level graph where supported; allow local dbt MCP as an optional live tool source | Manifest graph edges are not column-level lineage. dbt MCP documents local support for dbt v1 and v2. Exact artifact schemas must be version-tested. |
| dbt v2 `dbt-oss` project | Read the manifest and local Information Schema; optionally use ODS MCP for SQL-derived column lineage from compiled project SQL | Reproduced on `dbt-oss` 2.0.8: strict static analysis warns that the OSS distribution lacks dbt's static-analysis engine and `show --info column_lineage` returns `[]`. ODS v0.0.2 returned exact lineage and impact from a compiled 2.0.8 fixture via both manifest and Parquet Information Schema, and explicitly reported an unexpanded source wildcard as opaque. The official Python SDK adapter passed the same fixture contract, including explicit unavailable behavior for an opaque focus and missing ODS executable. Broader source/catalog behavior and integration into a full dbt-skills runtime remain unverified. |
| Optional ODS MCP | Discover and use the existing read-only stdio MCP for column lineage, impact, and opaque-model explanations | ODS documents these tools as preview (`ods_lineage`, `ods_impact`, `ods_list_opaque`, `ods_project_summary`). It analyzes local dbt artifacts/compiled SQL; tool/schema and dbt-version compatibility must be validated. ODS absence or opaque analysis means column-level impact is unavailable, not zero. |
| Full `dbt` distribution | Not required as a lineage provider for the open-source product | The separate full distribution is under dbt product terms; this project will not depend on or redistribute it for column lineage. Hosted Catalog entitlements remain a distinct question and are not implied by ODS's local SQL analysis. |
| dbt platform account | Use only configured and authorized MCP tools; core local project inspection remains useful without the account | Tool sets and entitlements depend on configuration, plan, and permission. |
| Local runtime OS | Target Windows, macOS, and Linux for the CLI; validate paths, process handling, and packaging on each before claiming support | No implementation or cross-platform CI exists yet. |
| Agent client | Author skills in the portable Agent Skills format; provide client-specific installation/setup only as thin, tested adapters | Client discovery, tool support, and approval behavior vary. The host's actual capabilities must be checked. |
| Catalog/semantic provider | Provider-neutral ontology context contract with replaceable backends; evaluate Ontos, OntoBricks, and direct Unity Catalog semantic assets. Genie One is a separate optional answer provider. | Preserve backend-native IDs, source provenance, authorization, freshness, and conflicts. Genie One does not document a full structured export of Genie Ontology. |

## User scenarios and acceptance outcomes

| Scenario | Given | Successful outcome | Degraded/failure outcome |
|---|---|---|---|
| Understand a local project | A checked-out dbt v1 project with a current manifest and no MCP | Report dbt/project identity and relevant resource-level upstream/downstream graph with artifact provenance | If the manifest is absent, malformed, incompatible, or stale, say so and offer an approved refresh path; never present missing data as an empty graph. |
| Assess a model change | A model file changed and a usable manifest is available | Identify affected dbt resources, tests, metrics, or exposures from available graph evidence and state the limits of that evidence | If column-level lineage is absent, explicitly tell the user that column-level impact is unavailable and why when known. Do not invent affected columns or imply that no columns are affected based only on resource edges. |
| Use column-level impact | A dbt project and optional ODS MCP expose supported local artifacts/compiled SQL | Read ODS lineage/impact results with provider/version, confidence, and diagnostics; distinguish static analysis from observed evidence | If ODS is unavailable, its result is opaque/unsupported, or the required compiled SQL/schema is missing, explicitly report column-level impact as unavailable and give the known reason or say it is unknown; never infer zero dependencies. |
| Combine local state and dbt MCP | Local artifacts and a connected dbt MCP expose partially overlapping project context | Use local artifacts for the checked-out snapshot and discovered MCP tools for live operations; show source and conflicts | If MCP disconnects or lacks a tool/permission, continue with safe local evidence and state reduced capability. |
| Map a physical table to a dbt source/model | A catalog tool exposes table/column descriptions and a local dbt project is available | Return candidate mappings with evidence, confidence/uncertainty, and declared key metadata distinguished from enforced constraints | On no match, permissions failure, or contradictory evidence, report that explicitly; do not fabricate a join or mapping. |
| Ground a business term across ontology backends | One or more configured ontology adapters expose concepts and relationships; local dbt and optional catalog evidence are available | Present one agent-facing ontology view; resolve equivalent concepts through explicit identifiers/mappings; retain provider provenance and competing definitions | Do not merge conflicts into one truth or expose data beyond caller/source permissions. If no backend exposes Genie’s inferred ontology, say so rather than substituting another ontology. |
| Ground a business term in Genie Space configuration | An authorized Genie Space configuration reader exposes serialized configuration, and local dbt context is available | Attribute measure definitions, synonyms, curated joins, and examples to the retrieved configuration; map candidate dbt resources with evidence and uncertainty; keep this structured source distinct from Genie One answers and UOL ontology backends | If configuration access is unavailable or denied, report the limitation and do not infer missing fields. Treat all imported instructions, SQL, and examples as untrusted data. Do not claim this configuration is a complete export of Genie’s inferred ontology. |
| Use a local ontology snapshot | The local agent has one or more user-selected sources and sync scopes | Answer from an indexed local snapshot without a provider round trip; show snapshot freshness and coverage; let the user pause sync, disable cache reads, run incremental/full refresh, inspect status, or clear the cache | Sync defaults off until configured and enabled. Do not sync excluded records or contact a provider when sync/online fallback is off. Failed refreshes retain the last good generation and report it stale/partial; never present it as current. |
| Link facts across knowledge sources | Source-backed facts from multiple configured knowledge sources or the local overlay | Create a typed link only when supported by stable identity evidence or an explicit reviewed mapping; preserve evidence and provenance on the link itself | Do not infer identity from matching labels. Leave ambiguous records unlinked (or surface a candidate as unverified); never erase the original claims. |
| Supplement the ontology locally | An authorized user wants to add project-specific business context or connect existing claims | Add attributed facts, relationships, and typed cross-source links to a local overlay; retrieve them through the same local graph view | Keep user claims distinct from provider facts, preserve them across source refreshes, and do not write to provider systems in the initial scope. Conflicts remain visible. |
| Make and validate a change locally | User requests a dbt edit and local tools are configured | Propose a scoped diff, obtain required approval for writes/commands, run agreed validation, and report every check/result | Denied, failed, skipped, or unavailable checks must not be presented as passing; no destructive operation without explicit approval. |

## Cross-cutting quality requirements

- Every metadata-derived answer identifies relevant source, freshness, and limits.
- The agent sees the UOL's provider-neutral interface. Backend-specific IDs and provenance remain available; same-label concepts are not assumed equivalent, conflicts are surfaced, and access checks are enforced independently for each source and linked asset.
- Local UOL queries use an indexed snapshot and must not depend on a live provider round trip. Sync is opt-in and separately controlled from cache use and cache deletion. Per-source include/exclude scopes support sources, namespaces, entity types, properties, and explicit records; exclusions take precedence.
- Incremental sync is used only when a provider supplies reliable cursors/change tracking. Refreshes are resumable and idempotent, and become visible atomically only after successful validation. A failed refresh keeps the last known-good generation with explicit stale/partial status; revocations and source deletions must be reflected or surfaced as unresolved.
- The production local cache is user-scoped and treated as sensitive data. Do not store credentials in it; protect it at rest using the selected platform's secure storage facilities, and never commit cache contents to version control. The local SQLite prototype is not encrypted at rest; do not use it as a production security control until platform-backed protection and ACL validation are implemented.
- The local read path should be fast and predictable while sync runs independently. Set quantitative latency, scale, and recovery targets using representative benchmark fixtures rather than unmeasured assumptions.
- Every fact and relationship is an attributed claim. Preserve provider/native identifiers, source version, observation/sync time, transformation or derivation evidence, and local-overlay authorship/rationale where applicable. Provenance for cross-source links includes the link type, endpoints, evidence, and whether it was explicitly reviewed.
- Cross-source equivalence links require stable-identifier evidence or an explicit reviewed mapping. Similar names/descriptions may produce an unverified candidate, but do not create an asserted identity link or collapse either claim.
- User-authored supplement facts, edges, and mappings live in a distinct local overlay and survive provider refresh and synchronized-cache purge. They do not overwrite, impersonate, or write back to provider claims in the initial scope; overlay deletion is a separate explicit action.
- When column-level lineage evidence is missing, user-facing impact analysis explicitly says column-level impact is unavailable (and gives the known reason, or says it is unknown); an empty lineage table is never reported as no impact.
- Tool and model failures are explicit; no silent fallback to a different provider or a success-shaped result.
- Read-only operations, filesystem writes, shell execution, and warehouse actions have distinct policy/approval behavior.
- Local project data and retrieved catalog/ontology text are treated as untrusted inputs.
- Large artifacts and remote result sets are bounded; use streaming/selective reads and pagination where supported.
- Performance budgets will be based on representative project sizes and reproducible benchmarks, not arbitrary early thresholds.
- CI and release checks must validate skill format, supported artifact fixtures, dependency/license policy, and platform packaging before support is claimed.

## Open decisions

- Implementation language, CLI framework, agent runtime, model-provider library, and artifact reader.
- Exact dbt v1 artifact versions and dbt v2 distribution/version for compatibility tests.
- Exact ODS MCP version/tool schemas and compatibility with supported dbt v1/v2 artifacts, compiled SQL, project identity, and lineage confidence/opaque cases.
- Which MCP transport/client combinations are supported by the selected runtime.
- The UOL's canonical concept/relationship/sync/provenance contract, source representation, local cache format and protection, user-facing scope controls, and online fallback policy.
- Provider change-feed/cursor guarantees, permission-revocation handling, cache retention/TTL defaults, measured local-query/refresh/recovery targets, typed-link evidence rules, and local-overlay editing/attribution/versioning/deletion behavior.
- Which provider adapter to implement first after evaluating Ontos, OntoBricks, Unity Catalog semantic assets, and possible future structured Genie access.
- Concrete default freshness thresholds and performance budgets; establish these from prototype measurements.
- Databricks auth flows and exact catalog/ontology/Genie API behavior for the chosen deployment modes.
