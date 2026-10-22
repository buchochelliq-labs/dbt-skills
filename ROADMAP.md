# Open-Source dbt Wizard Alternative Roadmap

**Status:** The M0 documentation baseline is merged to `main` in #27. The local SQLite UOL core and a source-tree CLI/runtime prototype are implemented. A first portable dbt context-routing skill and thin GitHub Copilot CLI profile are now present, but Copilot CLI discovery has not been smoke-tested and no UOL tools are exposed to the host. No dbt-skills MCP server or provider-connected ontology adapter is validated. ODS v0.0.2 passes a minimal dbt-oss 2.0.8 manifest/Parquet and stdio MCP smoke test; a Python SDK adapter prototype passes the same fixture contract, including opaque and absent-provider behavior. The user selected an optional ODS MCP provider for open-source column lineage; this project will not rely on dbt's full product distribution for lineage. Missing or opaque column-level lineage must be called out as unavailable in user-facing impact analysis. Ontos and OntoBricks remain optional ontology sources; neither exposes Genie Ontology. Outstanding M0 work includes issue #5 component/license/security assessment, #6 ODS integration validation, and #8 provider/catalog validation.
**Research checked:** 2026-10-22

## Recommendation

**Build an open-source alternative to dbt Wizard, not merely an add-on.** Deliver a self-hostable, local-first CLI that provides the core agent workflow (project understanding, tool orchestration, safe edits, validation, and reviewable changes) while grounding its answers in dbt artifacts, dbt MCP, external catalog metadata, and business ontology. Supplement rather than fork dbt's open skill catalog: depend on `dbt-labs/dbt-agent-skills` for common dbt workflows and focus our original skills and services on integration and orchestration gaps.

The product should remain useful without a dbt Wizard account, hosted Wizard runtime, or paid Wizard-only features. Allow users to configure their own supported model provider (including local/self-hosted options where feasible); isolate optional hosted services behind adapters. Reuse open-source dbt components and public protocols where licensing permits, but do not copy or depend on proprietary Wizard implementation.

Wizard has a public-beta CLI, and its published docs describe account credits and token-metered usage; the hosted platform experience and some features are plan-dependent. So do not characterize every Wizard surface as wholly paywalled. The open-source alternative is valuable regardless: make core local development capabilities inspectable, self-hosted, and provider-flexible, with no required paid service.

**Reuse before building:** for each layer, first identify a maintained open-source project or standard that already solves the problem. Prefer adopting or integrating it over writing a replacement; build only the missing dbt-specific orchestration and catalog/ontology adapters. Check license compatibility, maintenance health, security posture, extensibility, and whether the component works in a self-hosted workflow before selecting it. Attribute and pin dependencies, and keep replaceable adapters around external components where practical.

**Dependency backout strategy:** no critical capability should depend on silently tracking an upstream default branch or an unreviewed license change. Pin versions/commits, record provenance and the applicable license for the exact version, and check dependency/license changes during upgrades. If an upstream project changes its license or becomes closed:

1. Stop automatic upgrades and block adoption of the newly licensed version until reviewed.
2. Keep using the last version under terms already approved for this project only where those terms permit continued use and distribution; preserve notices and seek legal review if scope is uncertain.
3. Because integrations are isolated behind adapters, evaluate an alternative open-source implementation first. If none fits, maintain a fork of the last suitable version only when its license allows that, or replace the capability with a clean implementation against public interfaces.
4. If no lawful, maintainable replacement exists, disable/remove the affected optional capability and clearly document the impact rather than making the core CLI depend on proprietary access.

Apply this policy to the dbt skills package, dbt MCP, CLI/agent framework, MCP SDKs, model-provider libraries, and catalog/ontology clients—not just direct runtime dependencies.

Treat the metadata sources as complementary:

- The **catalog MCP** answers structured questions about catalogs, schemas, tables, columns, descriptions, and declared primary/foreign keys.
- The **semantic sources** are distinct: Genie One can answer using Genie Ontology; Ontos and OntoBricks expose their own ontology/knowledge-graph data over MCP; direct Unity Catalog semantic assets expose curated definitions. None should be presented as a direct export of another source's ontology.

## What the research found

### Current repository and upstream baseline

This repository currently contains the README, research/product requirements, and this roadmap; software implementation has not started. The public [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) repo already covers everyday dbt development, tests, docs, semantic-layer modeling and questions, Mesh, dbt MCP setup, documentation lookup, command use, dbt Information Schema, dbt State, job troubleshooting, and migration. It also provides multiple distribution paths, tests, and an evaluation harness. Its license is Apache-2.0.

dbt documents installing Agent Skills from packages with `dbt deps` (dbt v2), and Wizard documents that it ships with skills from this upstream catalog. Project/user skills can override built-ins. That makes publishing a second general dbt catalog a poor differentiator and creates duplicate names and maintenance burden. Prefer using the dbt Labs package directly when its coverage fits. If this project distributes any shared skills through a dbt package, give them distinct integration-oriented names and document package skill enable/disable behavior.

The public skill catalog is observable; the complete internal Wizard implementation and any non-public skills are not. A feature not listed in the public repository is **not evidence** that Wizard lacks it. Scope the opportunity as an openly implementable alternative to documented user workflows and as additions to the public skill catalog, not as confirmed gaps in dbt's private product.

When upstream content is needed, prefer an installation dependency or a clearly attributed, minimal adaptation over copying/forking. Verify the license and notices before redistributing derivative content.

### Related project: OpenDataSuite

[`buchochelliq-labs/open-data-suite`](https://github.com/buchochelliq-labs/open-data-suite) is a broader analytics-engineering project in the same organization. It has adjacent work on a CLI, dbt and catalog context, lineage, MCP, and an agent runtime. This roadmap remains focused on the dbt-specific Wizard alternative; ODS is not bundled or mandatory and does not expand this project's remit beyond dbt. Per the user's direction, evaluate optional interoperability with ODS's read-only stdio MCP as the preferred open-source column-lineage provider rather than duplicating its analyzer or relying on dbt's full product distribution. Keep ODS lineage optional, pin/contract-test any adopted interface because it is preview and 0.0.x, and retain an explicit unavailable fallback. Keep skills and interfaces portable so a future broader product remains possible; share concrete, evidence-backed findings with ODS.

### Public skill coverage and complement opportunity

This is a comparison to the published upstream skills, not a claim about all dbt Wizard internals.

| Publicly documented upstream coverage | Complementary gap for this project |
|---|---|
| Create/refactor dbt models; inspect existing project, impact, tests, errors, and docs | **Join up contexts:** explain how to resolve dbt model/source nodes to physical catalog tables and use both project lineage and catalog PK/FK/declarations when planning work |
| Query dbt v2 Information Schema and inspect manifest/catalog artifacts | **Join up contexts:** combine the checked-out project's graph with connected dbt MCP context and external physical catalog metadata |
| Build/query dbt Semantic Layer metrics; general semantic modeling and business Q&A | **Provider-neutral ontology context:** one agent-facing contract over optional ontology backends; preserve source-specific authority, permissions, freshness, and conflicts |
| Configure dbt MCP and use dbt-specific tools | **Generic catalog MCP:** a backend-configurable interface for physical metadata, plus robust local artifact fallback and explicit routing across the two MCPs |
| Agent Skills package delivery through `dbt deps` on dbt v2 | **Tool deployment and routing:** a server is a separate runtime from package-installed skills; document how compatible clients connect to local or remote MCP transports and which tool to use for which question |
| Common build, test, debug, and migration workflows | **Catalog/ontology-specific evaluations:** prove relationship-aware discovery, source-to-model mapping, semantic conflict handling, and safe behavior when metadata is missing or contradictory |

These are reasonable open-source opportunities based on public source review. Validate each with concrete user scenarios and tool/API prototypes before treating it as a committed feature or claiming that no private Wizard equivalent exists.

### What an open alternative needs beyond skills

Wizard's documented capabilities rely on project metadata, tool orchestration, dbt execution, validation, review/approval, and different hosted/local product surfaces. In particular, dbt's Information Schema can include project nodes, column lineage and types, tests, and runtime results. Wizard uses it for impact analysis, health checks, profiling, and validation planning.

Skills can teach an agent how to inspect metadata, plan safe changes, validate, and report uncertainty, but they are only one layer. A standalone alternative also needs its own CLI/runtime for sessions, project context, tool discovery/orchestration, model-provider configuration, approval policy, sandbox boundaries, diff review, validation loops, and persistence. These core capabilities should be implemented openly rather than assumed to be supplied by a commercial agent host. Hosted UI, managed billing, and dbt's proprietary product surfaces are not required for a useful local-first alternative.

### Project understanding: local artifacts and dbt MCP

A Wizard-like CLI should support **both** a local project snapshot and dbt MCP from the start. They provide related but different capabilities, and neither should be a mandatory single point of failure.

| Source | Primary role | Important limitations |
|---|---|---|
| Local `manifest.json` and related dbt artifacts | Offline, reproducible snapshot of parsed resources, configs, and graph dependencies for the checked-out project; useful fallback for dbt v1 and when MCP is unavailable | May be missing or stale; parse-level state does not provide all runtime or column-lineage details |
| dbt Information Schema, when generated and supported | Structured, queryable dbt metadata; supported distributions can add column types/lineage with strict static analysis and runtime results after execution | dbt v2 feature; `dbt-oss` 2.0.8 does not include the static-analysis engine and produced zero lineage rows in a reproduction. Available detail depends on distribution, command, and artifact freshness. |
| Existing dbt MCP server | Live, tool-mediated dbt capabilities exposed by the configured server, such as supported project discovery, dbt commands, platform APIs, semantic queries, or job evidence | Actual tools vary by server type, configuration, permissions, account, and client; never assume a tool exists solely because MCP is connected |
| Data-catalog MCP proposed here | Physical catalog metadata not represented in, or sufficient from, the local dbt project graph: tables, columns, descriptions, and declared key relationships | Not a replacement for dbt dependency lineage, compiled state, dbt commands, or platform APIs |
| Genie One MCP | Answers grounded in Genie Ontology, including its selected curated and inferred context; optionally delegates natural-language analytics | Uses Genie One's answer workflow; no documented direct MCP/API exports the full inferred ontology |
| Ontos MCP | Ontos semantic-model knowledge graph, business terms, semantic links, and bounded SPARQL | Separate ontology that must be uploaded/curated; does not expose Genie Ontology. MCP token scopes and Ontos permissions both apply |
| OntoBricks MCP | OntoBricks ontology structure/OWL-Turtle and, when built, mapped graph/entity/GraphQL context | Separate ontology mapped to UC assets. App, SQL Warehouse, Lakebase, and graph lifecycle add setup and quota considerations |
| Direct Unity Catalog semantics | Explicit metric views, domains, Pages, comments, and catalog metadata through supported UC surfaces | Explicit modeled assets only; not Genie’s inferred snippets or its relevance/authority ranking |
| Optional ODS MCP | Existing read-only local column-lineage, impact, and opaque-model tools | Separate open-source preview; stdio transport and actual tools/schema must be discovered and version-checked; unavailable/opaque output is not zero impact |

The CLI should detect and report which sources/tools are present, and record source plus freshness/completeness for the metadata it uses. Prefer local artifacts for the exact checked-out project's graph and configuration; use dbt MCP for live dbt/platform operations and any capabilities it explicitly exposes. Enrich either with catalog and ontology context when relevant. If artifacts are stale or absent, offer a suitable parse/compile/build step when available and approved; do not present stale graph results as current. If MCP is missing, disconnected, or lacks permissions, continue from local artifacts when possible and state the reduced capability. If sources disagree, show the discrepancy with provenance instead of silently selecting one.

Do not implement a second dbt metadata/command service merely to duplicate the existing dbt MCP. Reuse the upstream dbt Agent Skills, dbt MCP server, compatible MCP SDKs, and a suitable open-source CLI/agent runtime where they meet requirements. Build only the missing generic catalog service and dbt-specific orchestration/glue. dbt MCP is a first-class, optional integration; local artifacts are the resilient project-context fallback. The CLI itself owns runtime discovery and freshness reporting, and remains useful when dbt MCP or hosted services are absent.

### Unity Catalog and Genie interfaces

Databricks' Unity Catalog Table API returns table metadata and table constraints. The table representation includes primary-key child columns and foreign-key child/parent table and columns; constraint `RELY` information is available. These are catalog declarations and must not be described as proof that a warehouse enforces the constraint. Metadata access remains subject to Databricks permissions.

Genie Space configuration is a distinct semantic source. Its serialized configuration can include instructions, example question/SQL pairs, joins, SQL snippets, measures, synonyms, and curated table/column settings. The Get Genie Space API requires at least CAN EDIT permission to include the serialized space. Separately, Databricks' generally available Genie One MCP answers natural-language questions grounded in Genie Ontology and runs under Unity Catalog permissions. It is a Q&A integration, not a substitute for importing the ontology configuration.

## Proposed architecture

### 1. Portable skill catalog

Use the Agent Skills format as the canonical content (`SKILL.md` with focused descriptions and optional references). Keep general project guidance separate from task skills, and make agent-specific profiles thin wrappers around the shared skills. Skills should work with this project's own CLI/runtime and compatible third-party clients; they must not require dbt Wizard.

Do not recreate these upstream skill groups by default: general modeling, generic tests, docs, semantic-layer basics, command usage, migration, and generic dbt metadata/operations already have public coverage. The proposed new skills should instead orchestrate existing skills and add external-context guidance:

| Group | Initial coverage |
|---|---|
| Catalog-grounded dbt discovery | Combine local project artifacts/Information Schema, available dbt MCP tools, and the catalog MCP to map physical assets to dbt sources/models; then invoke upstream dbt development and impact workflows |
| Ontology context layer | Query configured ontology adapters through a stable agent-facing contract; keep provider-native concept IDs, evidence, permissions, and conflicts |
| Cross-context modeling and change planning | Reconcile warehouse catalog, dbt graph/artifacts, dbt MCP evidence, and semantic ontology; surface mismatches and uncertainty before suggesting source YAML, model, or semantic-layer changes |
| MCP and project-context routing | Configure or diagnose dbt MCP and catalog MCP; choose local artifacts vs live dbt tools vs catalog vs Genie; report unavailable permissions, tools, or stale/incomplete metadata honestly |

Use explicit dbt-version and tool-availability branches. For example, dbt Information Schema is a dbt v2 capability; v1 projects need manifest- or MCP-based alternatives. A skill must not claim that a metadata or execution tool is available unless the host exposes it.

Initially these can be four focused skills plus one small routing profile; do not create a skill for every provider or individual table operation. Keep authoritative upstream task instructions upstream, and make our additions work alongside them.

### 2. Generic data-catalog MCP

Keep a small backend-neutral physical-catalog metadata contract behind the MCP tools. Configure the selected backend when starting the server; implement Databricks Unity Catalog first and leave other physical catalog adapters for later phases. Keep this service separate from local dbt artifact readers and the existing dbt MCP integration.

The initial tool surface should support catalog/schema discovery, table search/listing, detailed table/column metadata, and relationship lookup. Responses should normalize names, data types, descriptions/comments, and declared PK/FK relationships while preserving source and constraint details such as `RELY`. Add pagination and bounded results; return explicit errors for inaccessible or unsupported metadata rather than implying an empty catalog.

Keep this server metadata-only and read-only. Do not include SQL execution or warehouse data sampling in its first version. Ship both local STDIO and remote Streamable HTTP transports, with backend adapters independent of transport. Keep credentials out of checked-in configuration; use the host's supported secret/auth mechanisms and least-privilege Databricks permissions.

### 3. Unified Ontology Layer (UOL)

Define the Unified Ontology Layer as one agent-facing read contract for concept search, concept retrieval, relationship traversal, asset references, and configured source discovery. Put backend-specific authentication, tool schemas, pagination, and permission checks behind adapters. Ontos and OntoBricks are candidate backends with distinct knowledge models; Unity Catalog semantic assets are another potential source.

The local agent needs a fast, reliable local snapshot, so treat local caching and synchronization as first-class UOL capabilities rather than requiring a remote query for each answer. Keep source adapters, sync orchestration, local storage, and agent-facing reads behind a small interface. Sync is disabled until the user selects sources/scopes and enables it. Users can include and exclude sources, namespaces, entity types, properties, and explicit records; exclusions win. Provide distinct controls to pause syncing, disable cache reads, refresh incrementally, run a full refresh, inspect sync status, and clear synchronized data. Do not silently contact a provider when sync or online fallback is off.

Use the local indexed snapshot for agent queries. Run sync separately from interactive reads, resumably and idempotently; use provider cursors/change tracking when reliable, otherwise disclose that a refresh is a full scan. Apply each completed refresh atomically so failures leave the last known-good snapshot intact and visibly stale rather than partially replacing it. Preserve provider-native IDs, source attribution, permission scope, timestamps, sync coverage, and conflicting claims. Record provenance on every fact and relationship, including source identity, native IDs, sync/observation time, and any derivation or mapping evidence. Link facts across sources only through sufficiently strong evidence, such as matching stable identifiers or an explicitly reviewed mapping. Represent a link as a typed assertion with its own provenance/evidence; matching labels alone are insufficient, and ambiguous records remain unlinked.

Let users supplement the graph through a local overlay of attributed facts, relationships, and cross-source links. Keep overlay claims separate from provider claims so they do not overwrite source content or masquerade as provider truth. Preserve user additions across syncs and full refreshes; clearing synchronized provider data must not silently delete the overlay. Provider write-back is out of scope unless separately designed and approved. Do not let ontology visibility bypass permissions on a linked catalog asset. Cache data per local user/source identity, keep secrets out of the cache, and define TTL/revalidation and purge behavior for permission revocation before claiming cached records are current.

Optimize for local indexed concept lookup and bounded graph traversal; synchronization must not block agent reads. Establish measurable latency, dataset-size, and recovery targets from representative benchmarks before fixing numeric budgets. Keep a last successful generation available through transient failures, report stale/partial status, and make retry or full-refresh actions explicit.

Genie One MCP is a separate answer provider: use it only when Genie Ontology's curated and inferred context is specifically needed. Databricks does not document a direct endpoint to enumerate/export its full inferred ontology, so Genie One answers/citations may be retained as attributed response evidence but are not a structured Genie ontology backend today. If a permission-aware structured source becomes available later, add it behind the same adapter contract.

Ontos and OntoBricks use the Databricks License, not a permissive OSI license; keep them optional external services and review terms before redistributing code or derivatives. See the [provider comparison and cost/auth guardrails](docs/research/databricks-ontology-options.md). Do not promise zero cost for a live POC: Free Edition is no-cost but quota-limited, and OntoBricks uses App, SQL Warehouse, and Lakebase resources.

### 4. CLI agent profiles and host integrations

Build a first-party local CLI agent/runtime rather than another static profile alone. It should compose upstream dbt skills with this project's catalog and semantic-grounding skills, and choose local artifacts/Information Schema for checked-out project graph context, dbt MCP for supported live dbt/platform tools, catalog MCP for physical table/column metadata and declared keys, and the Unified Ontology Layer for business semantics. Genie One remains an optional answer tool only when the task specifically requires its ontology grounding. The core coding, review, and validation workflow must function without dbt Wizard; a separate analyst profile is optional if evaluations demonstrate distinct tool permissions or user journeys.

Keep portable instructions in `AGENTS.md` where supported. Add client-specific agent definitions or instructions (for example, Copilot custom-agent files) only as small adapters with their own tool permissions and validation notes. Approval gates, diff review, shell/warehouse permissions, and remote hosting remain host responsibilities.

### 5. Quality, distribution, and maintenance

- Validate skill frontmatter, names, links, references, and the Agent Skills specification in CI.
- Add scenario-based evaluations for common tasks, dbt v1/v2 differences, correct tool selection, safe validation, and explicit reporting of checks that could not run.
- Test the MCP contract independently of transports and test each adapter with fixtures, pagination, permission failures, and incomplete metadata.
- Add adversarial metadata fixtures (for example, descriptions containing instruction-like text) to ensure agents treat catalog and Genie content as data.
- Support portable skill installers and consider dbt package distribution as a versioned option. Keep install instructions and version pinning clear.
- Track upstream dbt Agent Skills changes and dbt/Databricks API changes; preserve provenance and review updates for changed behavior before synchronizing.
- Maintain a dependency inventory/SBOM with pinned versions, source URLs, and license identifiers; run license-policy and vulnerability checks in CI. Require explicit review for license/source changes, with CI failing closed for newly unapproved licenses.
- Exercise the dependency backout path in release planning: prove that optional integrations can be disabled/replaced and the local core still works without hosted or newly proprietary components.

## Prioritized roadmap

### Phase 0 — Foundation and compatibility

Document intended users and supported dbt versions; pin the reviewed upstream catalog snapshot and classify covered vs additive scenarios; establish attribution/provenance, package/install strategy, and scenario evaluation criteria. Define the dependency inventory, license allowlist/change gate, and backout process for every reused component. Specify local artifact/Information Schema, dbt MCP, optional ODS MCP, and Unified Ontology Layer provider contracts, capability/freshness reporting, fallback behavior, and conflict reporting. The `dbt-oss` 2.0.8 reproduction establishes that the OSS distribution lacks dbt's own static-analysis engine; the user selected ODS's Apache-2.0 SQL lineage implementation through its optional read-only MCP instead of relying on the full dbt distribution. Validate ODS artifact/compiled-SQL compatibility, exact tool/schema version, confidence/opaque behavior, and licensing/provenance. Distinguish local lineage from hosted dbt Catalog entitlements. Prototype catalog and ontology-provider tool contracts and validate the highest-value integration workflows before broad skill authoring.

### Phase 1 — Open CLI/runtime foundation

Evaluate and select maintained open-source CLI/agent runtimes, MCP SDKs, artifact readers, and model-provider adapters before implementing infrastructure; prefer adopting an existing stack and contribute upstream fixes where feasible. Confirm license compatibility and choose this project's license. Define provider/model configuration and fill only gaps needed for dbt-specific project selection, sessions, tool discovery, approval gates, workspace-scoped edits, diffs, and validation. Keep the core self-hostable and independent of dbt Wizard and its hosted services. Reuse the upstream dbt skills package for generic workflows; don't mirror its general catalog.

### Phase 2 — Project context, dbt MCP, and skills

Implement artifact discovery/parsing and Information Schema support where available, plus dbt MCP connection/tool discovery for supported MCP transports and server types. Report dbt version, source distribution, freshness, and available capabilities; retain useful read-only artifact fallback when MCP is unavailable. Use existing dbt MCP operations rather than rebuilding them. Discover and optionally connect to ODS MCP for local SQL-derived column lineage/impact; preserve its version, confidence, diagnostics, and opaque reasons, and do not duplicate its analyzer. ODS is a preview and stdio-only in the reviewed contract, so validate exact tool/result compatibility and leave the local workflow useful without it. Whenever column-lineage evidence is missing or opaque, explicitly tell the user column-level impact is unavailable, provide the known reason or say it is unknown, and do not imply zero affected columns from empty output or resource-level edges. Distinguish locally generated evidence from hosted dbt Catalog lineage and entitlements. Add catalog-grounded discovery, Unified Ontology Layer-based business-semantic grounding, cross-context modeling/change-planning, and MCP setup/routing skills. Test provider adapters behind the Unified Ontology Layer contract, plus absent/stale artifacts, partial MCP tool sets, authorization failures, opaque ODS output, and disagreement between sources.

### Phase 3 — Catalog MCP v1

Implement the backend-neutral, read-only metadata tools and Databricks Unity Catalog adapter. Deliver STDIO and Streamable HTTP transports, startup backend configuration, least-privilege auth guidance, explicit errors, bounded/paginated responses, and adapter/transport tests. Return PK/FK declarations as metadata, not guaranteed constraints. Verify it complements rather than duplicates dbt MCP/artifact metadata. Core local discovery must not require a hosted dbt plan.

### Phase 4 — Unified Ontology Layer

Specify and prototype the provider-neutral read and sync contracts before selecting a committed backend. Compare Ontos and OntoBricks against term resolution, asset linking, graph depth, read-only controls, deployment, costs/quotas, and license. Sync user-selected source scopes into a local indexed snapshot for fast agent reads; expose pause, disable-cache-use, incremental refresh, full refresh, status, and synchronized-data purge controls. Preserve provenance on every fact, edge, mapping, and user assertion. Allow only evidence-backed typed cross-source links; leave uncertain matches unlinked. Add a local user overlay for authored facts/relationships/links, preserve it across provider refreshes and synchronized-data purge, and keep it separate from provider truth; overlay deletion is a separate explicit action, and provider write-back is out of scope in this phase. Make refreshes resumable, idempotent, and atomic, retaining the last known-good snapshot after failure. Treat Genie One as a separate answer tool; add a Genie ontology adapter only if Databricks exposes structured, permission-aware ontology data. Keep all integrations optional and never equate cached visibility with current source authorization.

### Phase 5 — Agent adapters and release maturity

Add minimal client-specific agent profiles where they improve tool routing, complete installer/dbt-package guidance, publish evaluations and compatibility results, and add a process for upstream synchronization and Databricks/dbt API changes. Upstream dbt skill updates should be consumed by users as a dependency, not routinely copied into this repository.

## Boundaries and open design work

This roadmap aims to provide an open-source alternative for the core local dbt agent workflow, not to reproduce dbt Wizard's proprietary implementation or every hosted product surface. Public-skill absence does not prove product absence. Focus on independently implemented, inspectable capabilities that work with public APIs, open protocols, local artifacts, and user-configured providers. Hosted UI, managed billing, and private dbt platform features may remain integrations rather than requirements.

The initial source-tree runtime now uses Python 3.11+, `argparse`, standard-library HTTP/TOML, PyYAML `safe_load`, and a replaceable OpenAI-compatible text provider; no general-purpose agent framework or model SDK has been added. Its limitations and the repository's unresolved distribution-license status are recorded in the component assessment and runtime guide. Remaining design work includes dbt and ODS MCP configuration/transport support, supported local artifact versions/schema readers, Databricks authentication for catalog and ontology APIs, the UOL's canonical query/sync/provenance contract, cache format and user-scoped protection, provider change-feed reliability and permission-revocation policy, representative performance/recovery budgets, typed-link evidence rules, local-overlay editing/attribution/versioning/deletion behavior, catalog backend configuration, Genie One behavior, supported non-Databricks catalog backends after Unity Catalog, and which client-specific profiles justify maintenance. The user selected ODS's open-source analyzer as the optional local column-lineage path; manifest resource edges and ODS column edges must remain separate if projected into the UOL. The full dbt distribution is not a project dependency for column lineage. Hosted dbt Catalog entitlements remain separate.

## Sources

- [dbt Wizard product overview](https://www.getdbt.com/product/dbt-wizard)
- [dbt Wizard CLI install, prerequisites, and usage/billing](https://docs.getdbt.com/docs/dbt-ai/wizard-cli)
- [dbt Wizard CLI quickstart](https://docs.getdbt.com/docs/dbt-ai/wizard-quickstart)
- [How dbt Wizard works](https://docs.getdbt.com/docs/dbt-ai/wizard-how-it-works)
- [dbt Wizard skills](https://docs.getdbt.com/docs/dbt-ai/wizard-skills)
- [dbt Wizard use cases](https://docs.getdbt.com/docs/dbt-ai/wizard-use-cases)
- [dbt Information Schema](https://docs.getdbt.com/docs/build/dbt-information-schema)
- [dbt Information Schema tables](https://docs.getdbt.com/reference/info-schema)
- [dbt local installation and v2 distributions](https://docs.getdbt.com/docs/local/install-dbt?version=2)
- [`dbt-oss` v2.0.8 package description](https://pypi.org/project/dbt-oss/2.0.8/)
- [dbt v2 source and license notes](https://github.com/dbt-labs/dbt)
- [Local column-lineage reproduction record](docs/research/dbt-v2-column-lineage.md)
- [ODS column-lineage design at reviewed revision](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/adr/0008-column-level-lineage.md)
- [ODS MCP contract at reviewed revision](https://github.com/buchochelliq-labs/open-data-suite/blob/965527c4ab9b84d8b2a6c2f9707c00555aa7ad9a/docs/adr/0010-mcp-server.md)
- [dbt Product Licensing Agreement](https://www.getdbt.com/dbt-product-license-agreement)
- [dbt pricing and hosted Catalog feature tiers](https://www.getdbt.com/pricing)
- [dbt MCP server overview](https://docs.getdbt.com/docs/dbt-ai/about-mcp)
- [dbt MCP server setup](https://docs.getdbt.com/docs/dbt-ai/setup-local-mcp)
- [dbt package skills](https://docs.getdbt.com/docs/dbt-ai/package-skills)
- [dbt Agent Skills repository](https://github.com/dbt-labs/dbt-agent-skills)
- [Reviewed upstream skills snapshot](https://github.com/dbt-labs/dbt-agent-skills/tree/b8facde20b7a92c40ce3e6b86b71c4b92aa44040/skills/dbt/skills)
- [Product requirements and scenario matrix](docs/PRODUCT_REQUIREMENTS.md)
- [Project context contract](docs/CONTEXT_CONTRACT.md)
- [Reuse/component assessment](docs/COMPONENT_ASSESSMENT.md)
- [Catalog and semantic/Genie workflow prototypes](docs/WORKFLOW_PROTOTYPES.md)
- [Databricks ontology provider comparison](docs/research/databricks-ontology-options.md)
- [Databricks Unity Catalog Table API](https://docs.databricks.com/api/workspace/tables/get)
- [Databricks Genie Space API](https://docs.databricks.com/api/workspace/genie/getspace)
- [Databricks Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp)
- [Ontos MCP](https://github.com/databrickslabs/ontos/blob/development/docs/handbook/mcp-and-ask-ontos.md)
- [OntoBricks MCP](https://github.com/databrickslabs/ontobricks/blob/master/docs/mcp.md)
- [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services)
