# Open-Source dbt Wizard Alternative Roadmap

**Status:** Research and proposed roadmap for an open-source dbt Wizard alternative; no CLI, skills, agents, or MCP server are implemented in this repository yet.
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
- The **Genie integrations** provide Databricks business semantics and, optionally, delegated natural-language analytics. Genie Space configuration ingestion and Genie One MCP question-answering are separate features.

## What the research found

### Current repository and upstream baseline

This repository currently contains only a README and this roadmap. The public [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) repo already covers everyday dbt development, tests, docs, semantic-layer modeling and questions, Mesh, dbt MCP setup, documentation lookup, command use, dbt Information Schema, dbt State, job troubleshooting, and migration. It also provides multiple distribution paths, tests, and an evaluation harness. Its license is Apache-2.0.

dbt documents installing Agent Skills from packages with `dbt deps` (dbt v2), and Wizard documents that it ships with skills from this upstream catalog. Project/user skills can override built-ins. That makes publishing a second general dbt catalog a poor differentiator and creates duplicate names and maintenance burden. Prefer using the dbt Labs package directly when its coverage fits. If this project distributes any shared skills through a dbt package, give them distinct integration-oriented names and document package skill enable/disable behavior.

The public skill catalog is observable; the complete internal Wizard implementation and any non-public skills are not. A feature not listed in the public repository is **not evidence** that Wizard lacks it. Scope the opportunity as an openly implementable alternative to documented user workflows and as additions to the public skill catalog, not as confirmed gaps in dbt's private product.

When upstream content is needed, prefer an installation dependency or a clearly attributed, minimal adaptation over copying/forking. Verify the license and notices before redistributing derivative content.

### Related project: OpenDataSuite

[`buchochelliq-labs/open-data-suite`](https://github.com/buchochelliq-labs/open-data-suite) is a broader analytics-engineering project in the same organization. It has adjacent work on a CLI, dbt and catalog context, lineage, MCP, and an agent runtime; its current README describes the project as pre-alpha, with agent capabilities planned. This roadmap remains focused on the dbt-specific Wizard alternative; ODS is not a current dependency, does not replace the planned scope here, and does not expand this project's remit beyond dbt. The work may be integrated into a broader product later. Keep skills and interfaces portable so that remains possible, and evaluate ODS capabilities, maturity, and licensing if a concrete integration is pursued.

### Public skill coverage and complement opportunity

This is a comparison to the published upstream skills, not a claim about all dbt Wizard internals.

| Publicly documented upstream coverage | Complementary gap for this project |
|---|---|
| Create/refactor dbt models; inspect existing project, impact, tests, errors, and docs | **Join up contexts:** explain how to resolve dbt model/source nodes to physical catalog tables and use both project lineage and catalog PK/FK/declarations when planning work |
| Query dbt v2 Information Schema and inspect manifest/catalog artifacts | **Join up contexts:** combine the checked-out project's graph with connected dbt MCP context and external physical catalog metadata |
| Build/query dbt Semantic Layer metrics; general semantic modeling and business Q&A | **Databricks Genie Ontology grounding:** retrieve/use curated Genie instructions, joins, synonyms, measures, and examples; distinguish ontology context from physical metadata and delegate Q&A to Genie One when available |
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
| dbt Information Schema, when generated and supported | Structured, queryable dbt metadata; can add column types/lineage with strict static analysis and runtime results after execution | dbt v2 feature; available detail depends on the command that generated it and the artifact's freshness |
| Existing dbt MCP server | Live, tool-mediated dbt capabilities exposed by the configured server, such as supported project discovery, dbt commands, platform APIs, semantic queries, or job evidence | Actual tools vary by server type, configuration, permissions, account, and client; never assume a tool exists solely because MCP is connected |
| Data-catalog MCP proposed here | Physical catalog metadata not represented in, or sufficient from, the local dbt project graph: tables, columns, descriptions, and declared key relationships | Not a replacement for dbt dependency lineage, compiled state, dbt commands, or platform APIs |
| Genie Space / Genie One | Curated business definitions and ontology; optionally delegate natural-language analytics to Genie One | Semantic/business context is not the project DAG or a complete physical catalog |

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
| Genie Ontology grounding | Select and interpret Genie Space context; use instructions, joins, measures, synonyms, and examples as semantic evidence; use Genie One MCP for delegated business Q&A only when connected |
| Cross-context modeling and change planning | Reconcile warehouse catalog, dbt graph/artifacts, dbt MCP evidence, and semantic ontology; surface mismatches and uncertainty before suggesting source YAML, model, or semantic-layer changes |
| MCP and project-context routing | Configure or diagnose dbt MCP and catalog MCP; choose local artifacts vs live dbt tools vs catalog vs Genie; report unavailable permissions, tools, or stale/incomplete metadata honestly |

Use explicit dbt-version and tool-availability branches. For example, dbt Information Schema is a dbt v2 capability; v1 projects need manifest- or MCP-based alternatives. A skill must not claim that a metadata or execution tool is available unless the host exposes it.

Initially these can be four focused skills plus one small routing profile; do not create a skill for every provider or individual table operation. Keep authoritative upstream task instructions upstream, and make our additions work alongside them.

### 2. Generic data-catalog MCP

Keep a small backend-neutral physical-catalog metadata contract behind the MCP tools. Configure the selected backend when starting the server; implement Databricks Unity Catalog first and leave other physical catalog adapters for later phases. Keep this service separate from local dbt artifact readers and the existing dbt MCP integration.

The initial tool surface should support catalog/schema discovery, table search/listing, detailed table/column metadata, and relationship lookup. Responses should normalize names, data types, descriptions/comments, and declared PK/FK relationships while preserving source and constraint details such as `RELY`. Add pagination and bounded results; return explicit errors for inaccessible or unsupported metadata rather than implying an empty catalog.

Keep this server metadata-only and read-only. Do not include SQL execution or warehouse data sampling in its first version. Ship both local STDIO and remote Streamable HTTP transports, with backend adapters independent of transport. Keep credentials out of checked-in configuration; use the host's supported secret/auth mechanisms and least-privilege Databricks permissions.

### 3. Optional Genie grounding integrations

- **Genie Space configuration reader:** retrieve and normalize the semantic configuration the user is authorized to expose, so an agent can use its curated instructions, relationships, examples, metrics, and synonyms. Handle the API permission requirement explicitly and treat all imported descriptions/instructions as untrusted data, not executable instructions.
- **Genie One MCP connection guidance or optional connector:** allow agents to delegate natural-language analytics questions to Databricks' existing `system.ai.genie_one_mcp`. Keep this distinct from the catalog MCP and make clear that it can execute analytics queries under the caller's permissions.

Prefer connecting to the existing Genie One MCP over reimplementing its Q&A/runtime behavior.

### 4. CLI agent profiles and host integrations

Build a first-party local CLI agent/runtime rather than another static profile alone. It should compose upstream dbt skills with this project's catalog and Genie skills, and choose local artifacts/Information Schema for checked-out project graph context, dbt MCP for supported live dbt/platform tools, catalog MCP for physical table/column metadata and declared keys, and Genie One MCP for business questions answered using Genie ontology. The core coding, review, and validation workflow must function without dbt Wizard; a separate analyst profile is optional if evaluations demonstrate distinct tool permissions or user journeys.

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

Document intended users and supported dbt versions; pin the reviewed upstream catalog snapshot and classify covered vs additive scenarios; establish attribution/provenance, package/install strategy, and scenario evaluation criteria. Define the dependency inventory, license allowlist/change gate, and backout process for every reused component. Specify the local artifact/Information Schema and dbt MCP provider contract, capability/freshness reporting, fallback behavior, and conflict reporting. Explicitly investigate column-lineage availability and licensing: distinguish locally generated dbt v2 `dbt.column_lineage` Information Schema from column-level lineage in hosted dbt Catalog, verify whether the former can be generated/read with the self-hosted product under its applicable terms, and document the exact version, command, static-analysis requirements, limitations, and any plan/API entitlements. Prototype the catalog/Genie tool contracts and validate the highest-value integration workflows before broad skill authoring.

### Phase 1 — Open CLI/runtime foundation

Evaluate and select maintained open-source CLI/agent runtimes, MCP SDKs, artifact readers, and model-provider adapters before implementing infrastructure; prefer adopting an existing stack and contribute upstream fixes where feasible. Confirm license compatibility and choose this project's license. Define provider/model configuration and fill only gaps needed for dbt-specific project selection, sessions, tool discovery, approval gates, workspace-scoped edits, diffs, and validation. Keep the core self-hostable and independent of dbt Wizard and its hosted services. Reuse the upstream dbt skills package for generic workflows; don't mirror its general catalog.

### Phase 2 — Project context, dbt MCP, and skills

Implement artifact discovery/parsing and Information Schema support where available, plus dbt MCP connection/tool discovery for supported MCP transports and server types. Report dbt version, source, freshness, and available capabilities; retain useful read-only artifact fallback when MCP is unavailable. Use the existing dbt MCP server for its provided operations rather than rebuilding them. Treat column lineage as a capability only when the detected source actually provides it; distinguish local Information Schema results from hosted dbt Catalog lineage and honor their separate license, plan, and API access requirements. Add the catalog-grounded discovery, Genie Ontology grounding, cross-context modeling/change-planning, and dbt MCP setup/routing skills. Test absent/stale artifacts, partial MCP tool sets, authorization failures, and disagreement between sources.

### Phase 3 — Catalog MCP v1

Implement the backend-neutral, read-only metadata tools and Databricks Unity Catalog adapter. Deliver STDIO and Streamable HTTP transports, startup backend configuration, least-privilege auth guidance, explicit errors, bounded/paginated responses, and adapter/transport tests. Return PK/FK declarations as metadata, not guaranteed constraints. Verify it complements rather than duplicates dbt MCP/artifact metadata. Core local discovery must not require a hosted dbt plan.

### Phase 4 — Genie ontology context

Add authorized Genie Space configuration ingestion and normalization as an optional grounding source. Document permission requirements, data handling, refresh behavior, and safe treatment of imported instructions. Separately document/use the existing Genie One MCP for natural-language questions; do not make it a required dependency of the catalog server. Keep either integration optional for users without Databricks.

### Phase 5 — Agent adapters and release maturity

Add minimal client-specific agent profiles where they improve tool routing, complete installer/dbt-package guidance, publish evaluations and compatibility results, and add a process for upstream synchronization and Databricks/dbt API changes. Upstream dbt skill updates should be consumed by users as a dependency, not routinely copied into this repository.

## Boundaries and open design work

This roadmap aims to provide an open-source alternative for the core local dbt agent workflow, not to reproduce dbt Wizard's proprietary implementation or every hosted product surface. Public-skill absence does not prove product absence. Focus on independently implemented, inspectable capabilities that work with public APIs, open protocols, local artifacts, and user-configured providers. Hosted UI, managed billing, and private dbt platform features may remain integrations rather than requirements.

Implementation planning should still select reused open-source CLI/agent/MCP components and verify license compatibility, then settle dbt MCP connection/configuration and transport support, supported local artifact versions/schema readers, Databricks authentication flows for local and remote transports, catalog backend configuration, Genie Space refresh/cache behavior, supported non-Databricks catalog backends after Unity Catalog, and which client-specific profiles justify maintenance. Confirm local dbt v2 Information Schema column-lineage availability and terms independently from the Enterprise-plan column-lineage feature advertised for dbt Catalog; do not assume that a locally generated artifact requires the hosted entitlement without verifying product/version terms.

## Sources

- [dbt Wizard product overview](https://www.getdbt.com/product/dbt-wizard)
- [dbt Wizard CLI install, prerequisites, and usage/billing](https://docs.getdbt.com/docs/dbt-ai/wizard-cli)
- [dbt Wizard CLI quickstart](https://docs.getdbt.com/docs/dbt-ai/wizard-quickstart)
- [How dbt Wizard works](https://docs.getdbt.com/docs/dbt-ai/wizard-how-it-works)
- [dbt Wizard skills](https://docs.getdbt.com/docs/dbt-ai/wizard-skills)
- [dbt Wizard use cases](https://docs.getdbt.com/docs/dbt-ai/wizard-use-cases)
- [dbt Information Schema](https://docs.getdbt.com/docs/build/dbt-information-schema)
- [dbt Information Schema tables](https://docs.getdbt.com/reference/info-schema)
- [dbt v2 source and license notes](https://github.com/dbt-labs/dbt)
- [dbt pricing and hosted Catalog feature tiers](https://www.getdbt.com/pricing)
- [dbt MCP server overview](https://docs.getdbt.com/docs/dbt-ai/about-mcp)
- [dbt MCP server setup](https://docs.getdbt.com/docs/dbt-ai/setup-local-mcp)
- [dbt package skills](https://docs.getdbt.com/docs/dbt-ai/package-skills)
- [dbt Agent Skills repository](https://github.com/dbt-labs/dbt-agent-skills)
- [Reviewed upstream skills snapshot](https://github.com/dbt-labs/dbt-agent-skills/tree/b8facde20b7a92c40ce3e6b86b71c4b92aa44040/skills/dbt/skills)
- [Databricks Unity Catalog Table API](https://docs.databricks.com/api/workspace/tables/get)
- [Databricks Genie Space API](https://docs.databricks.com/api/workspace/genie/getspace)
- [Databricks Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp)
- [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services)
