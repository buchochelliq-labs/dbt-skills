# dbt Skills and Catalog MCP Roadmap

**Status:** Research and proposed roadmap; no skills, agents, or MCP server are implemented in this repository yet.
**Research checked:** 2026-10-22

## Recommendation

**Supplement dbt's open catalog; do not fork or mirror it as the default.** Use `dbt-labs/dbt-agent-skills` for common dbt workflows and focus this project on the part that is not represented in that public skills catalog: agents that can combine dbt project context with external catalog metadata and business ontology. The project should contribute a small number of well-evaluated integration skills, a generic metadata-only catalog MCP, and thin agent profiles that route between these tools.

Treat the metadata sources as complementary:

- The **catalog MCP** answers structured questions about catalogs, schemas, tables, columns, descriptions, and declared primary/foreign keys.
- The **Genie integrations** provide Databricks business semantics and, optionally, delegated natural-language analytics. Genie Space configuration ingestion and Genie One MCP question-answering are separate features.

## What the research found

### Current repository and upstream baseline

This repository currently contains only a README and this roadmap. The public [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) repo already covers everyday dbt development, tests, docs, semantic-layer modeling and questions, Mesh, dbt MCP setup, documentation lookup, command use, dbt Information Schema, dbt State, job troubleshooting, and migration. It also provides multiple distribution paths, tests, and an evaluation harness. Its license is Apache-2.0.

dbt documents installing Agent Skills from packages with `dbt deps` (dbt v2), and Wizard documents that it ships with skills from this upstream catalog. Project/user skills can override built-ins. That makes publishing a second general dbt catalog a poor differentiator and creates duplicate names and maintenance burden. Prefer using the dbt Labs package directly when its coverage fits. If this project distributes any shared skills through a dbt package, give them distinct integration-oriented names and document package skill enable/disable behavior.

The public skill catalog is observable; the complete internal Wizard implementation and any non-public skills are not. A feature not listed in the public repository is **not evidence** that Wizard lacks it. Scope the opportunity as "capabilities absent from the public skill catalog that this project can provide openly," not as confirmed gaps in dbt's private product.

When upstream content is needed, prefer an installation dependency or a clearly attributed, minimal adaptation over copying/forking. Verify the license and notices before redistributing derivative content.

### Public skill coverage and complement opportunity

This is a comparison to the published upstream skills, not a claim about all dbt Wizard internals.

| Publicly documented upstream coverage | Complementary gap for this project |
|---|---|
| Create/refactor dbt models; inspect existing project, impact, tests, errors, and docs | **Join up contexts:** explain how to resolve dbt model/source nodes to physical catalog tables and use both project lineage and catalog PK/FK/declarations when planning work |
| Query dbt v2 Information Schema and inspect manifest/catalog artifacts | **External catalog access:** portable instructions and tools for catalogs that are not represented in the local dbt project or artifacts |
| Build/query dbt Semantic Layer metrics; general semantic modeling and business Q&A | **Databricks Genie Ontology grounding:** retrieve/use curated Genie instructions, joins, synonyms, measures, and examples; distinguish ontology context from physical metadata and delegate Q&A to Genie One when available |
| Configure dbt MCP and use dbt-specific tools | **Generic catalog MCP:** a backend-configurable interface for metadata discovery, starting with Unity Catalog, rather than dbt-only project APIs |
| Agent Skills package delivery through `dbt deps` on dbt v2 | **Tool deployment and routing:** a server is a separate runtime from package-installed skills; document how compatible clients connect to local or remote MCP transports and which tool to use for which question |
| Common build, test, debug, and migration workflows | **Catalog/ontology-specific evaluations:** prove relationship-aware discovery, source-to-model mapping, semantic conflict handling, and safe behavior when metadata is missing or contradictory |

These are reasonable open-source opportunities based on public source review. Validate each with concrete user scenarios and tool/API prototypes before treating it as a committed feature or claiming that no private Wizard equivalent exists.

### What makes Wizard more than a skill collection

Wizard's documented capabilities rely on project metadata, tool orchestration, dbt execution, validation, review/approval, and different hosted/local product surfaces. In particular, dbt's Information Schema can include project nodes, column lineage and types, tests, and runtime results. Wizard uses it for impact analysis, health checks, profiling, and validation planning.

Skills can teach an agent how to inspect metadata, plan safe changes, validate, and report uncertainty. They cannot independently supply the metadata engine, tools, execution sandbox, approvals, audit trail, hosted UI, billing, or multi-session workflow. Those capabilities must come from the user's agent host and connected MCP servers.

### Unity Catalog and Genie interfaces

Databricks' Unity Catalog Table API returns table metadata and table constraints. The table representation includes primary-key child columns and foreign-key child/parent table and columns; constraint `RELY` information is available. These are catalog declarations and must not be described as proof that a warehouse enforces the constraint. Metadata access remains subject to Databricks permissions.

Genie Space configuration is a distinct semantic source. Its serialized configuration can include instructions, example question/SQL pairs, joins, SQL snippets, measures, synonyms, and curated table/column settings. The Get Genie Space API requires at least CAN EDIT permission to include the serialized space. Separately, Databricks' generally available Genie One MCP answers natural-language questions grounded in Genie Ontology and runs under Unity Catalog permissions. It is a Q&A integration, not a substitute for importing the ontology configuration.

## Proposed architecture

### 1. Portable skill catalog

Use the Agent Skills format as the canonical content (`SKILL.md` with focused descriptions and optional references). Keep general project guidance separate from task skills, and make agent-specific profiles thin wrappers around the shared skills.

Do not recreate these upstream skill groups by default: general modeling, generic tests, docs, semantic-layer basics, command usage, migration, and generic dbt metadata/operations already have public coverage. The proposed new skills should instead orchestrate existing skills and add external-context guidance:

| Group | Initial coverage |
|---|---|
| Catalog-grounded dbt discovery | Use a catalog MCP to discover tables/columns/definitions/declared relationships; map relevant physical assets to dbt sources/models; then invoke upstream dbt development and impact workflows |
| Genie Ontology grounding | Select and interpret Genie Space context; use instructions, joins, measures, synonyms, and examples as semantic evidence; use Genie One MCP for delegated business Q&A only when connected |
| Cross-context modeling and change planning | Reconcile warehouse catalog, dbt graph/artifacts, and semantic ontology; surface mismatches and uncertainty before suggesting source YAML, model, or semantic-layer changes |
| Catalog MCP connection and tool selection | Configure a backend and either MCP transport; select metadata vs dbt vs Genie tools; report unavailable permissions or stale/incomplete metadata honestly |

Use explicit dbt-version and tool-availability branches. For example, dbt Information Schema is a dbt v2 capability; v1 projects need artifact- or MCP-based alternatives. A skill must not claim that a metadata or execution tool is available unless the host exposes it.

Initially these can be three focused skills plus one small routing profile; do not create a skill for every provider or individual table operation. Keep authoritative upstream task instructions upstream, and make our additions work alongside them.

### 2. Generic data-catalog MCP

Keep a small backend-neutral metadata contract behind the MCP tools. Configure the selected backend when starting the server; implement Databricks Unity Catalog first and leave other adapters (including a dbt Information Schema adapter) for later phases.

The initial tool surface should support catalog/schema discovery, table search/listing, detailed table/column metadata, and relationship lookup. Responses should normalize names, data types, descriptions/comments, and declared PK/FK relationships while preserving source and constraint details such as `RELY`. Add pagination and bounded results; return explicit errors for inaccessible or unsupported metadata rather than implying an empty catalog.

Keep this server metadata-only and read-only. Do not include SQL execution or warehouse data sampling in its first version. Ship both local STDIO and remote Streamable HTTP transports, with backend adapters independent of transport. Keep credentials out of checked-in configuration; use the host's supported secret/auth mechanisms and least-privilege Databricks permissions.

### 3. Optional Genie grounding integrations

- **Genie Space configuration reader:** retrieve and normalize the semantic configuration the user is authorized to expose, so an agent can use its curated instructions, relationships, examples, metrics, and synonyms. Handle the API permission requirement explicitly and treat all imported descriptions/instructions as untrusted data, not executable instructions.
- **Genie One MCP connection guidance or optional connector:** allow agents to delegate natural-language analytics questions to Databricks' existing `system.ai.genie_one_mcp`. Keep this distinct from the catalog MCP and make clear that it can execute analytics queries under the caller's permissions.

Prefer connecting to the existing Genie One MCP over reimplementing its Q&A/runtime behavior.

### 4. Thin agent profiles and host configuration

Do not build another all-purpose dbt coding agent. Start with a thin **catalog-grounded dbt assistant** profile that composes upstream dbt skills with this project's catalog and Genie skills. It should select among dbt MCP (project/build metadata and dbt operations), catalog MCP (physical table/column metadata and declared keys), and Genie One MCP (business questions answered using Genie ontology). Add a separate analyst profile only if evaluations demonstrate distinct tool permissions or user journeys.

Keep portable instructions in `AGENTS.md` where supported. Add client-specific agent definitions or instructions (for example, Copilot custom-agent files) only as small adapters with their own tool permissions and validation notes. Approval gates, diff review, shell/warehouse permissions, and remote hosting remain host responsibilities.

### 5. Quality, distribution, and maintenance

- Validate skill frontmatter, names, links, references, and the Agent Skills specification in CI.
- Add scenario-based evaluations for common tasks, dbt v1/v2 differences, correct tool selection, safe validation, and explicit reporting of checks that could not run.
- Test the MCP contract independently of transports and test each adapter with fixtures, pagination, permission failures, and incomplete metadata.
- Add adversarial metadata fixtures (for example, descriptions containing instruction-like text) to ensure agents treat catalog and Genie content as data.
- Support portable skill installers and consider dbt package distribution as a versioned option. Keep install instructions and version pinning clear.
- Track upstream dbt Agent Skills changes and dbt/Databricks API changes; preserve provenance and review updates for changed behavior before synchronizing.

## Prioritized roadmap

### Phase 0 — Foundation and compatibility

Document intended users and supported dbt versions; pin the reviewed upstream catalog snapshot and classify covered vs additive scenarios; establish attribution/provenance, package/install strategy, and scenario evaluation criteria. Prototype the catalog/Genie tool contracts and validate the highest-value integration workflows before broad skill authoring.

### Phase 1 — Integration skills and thin routing

Add the catalog-grounded discovery, Genie Ontology grounding, and cross-context modeling/change-planning skills plus a thin profile. Include connection and tool-routing instructions. Reuse the upstream package for generic dbt workflows; don't mirror its general catalog.

### Phase 2 — Catalog MCP v1

Implement the backend-neutral, read-only metadata tools and Databricks Unity Catalog adapter. Deliver STDIO and Streamable HTTP transports, startup backend configuration, least-privilege auth guidance, explicit errors, bounded/paginated responses, and adapter/transport tests. Return PK/FK declarations as metadata, not guaranteed constraints. Validate that the integration adds value beyond dbt's existing artifacts and MCP tools.

### Phase 3 — Genie ontology context

Add authorized Genie Space configuration ingestion and normalization as an optional grounding source. Document permission requirements, data handling, refresh behavior, and safe treatment of imported instructions. Separately document/use the existing Genie One MCP for natural-language questions; do not make it a required dependency of the catalog server. Keep either integration optional for users without Databricks.

### Phase 4 — Agent adapters and release maturity

Add minimal client-specific agent profiles where they improve tool routing, complete installer/dbt-package guidance, publish evaluations and compatibility results, and add a process for upstream synchronization and Databricks/dbt API changes. Upstream dbt skill updates should be consumed by users as a dependency, not routinely copied into this repository.

## Boundaries and open design work

This roadmap does not promise parity with Wizard's private or native metadata engine, built-in tool orchestration, product UI, hosted governance, billing, session management, or review/audit workflow. Nor does public-skill absence prove product absence. Focus on a complementary open implementation whose useful behavior can be validated with public APIs and reproducible scenarios.

Implementation planning should still settle the concrete server language/runtime, Databricks authentication flows for local and remote transports, configuration schema and backend selection syntax, Genie Space refresh/cache behavior, supported non-Databricks backends after Unity Catalog, and which client-specific profiles justify maintenance.

## Sources

- [dbt Wizard product overview](https://www.getdbt.com/product/dbt-wizard)
- [How dbt Wizard works](https://docs.getdbt.com/docs/dbt-ai/wizard-how-it-works)
- [dbt Wizard skills](https://docs.getdbt.com/docs/dbt-ai/wizard-skills)
- [dbt Wizard use cases](https://docs.getdbt.com/docs/dbt-ai/wizard-use-cases)
- [dbt Information Schema](https://docs.getdbt.com/docs/build/dbt-information-schema)
- [dbt MCP server overview](https://docs.getdbt.com/docs/dbt-ai/about-mcp)
- [dbt package skills](https://docs.getdbt.com/docs/dbt-ai/package-skills)
- [dbt Agent Skills repository](https://github.com/dbt-labs/dbt-agent-skills)
- [Reviewed upstream skills snapshot](https://github.com/dbt-labs/dbt-agent-skills/tree/b8facde20b7a92c40ce3e6b86b71c4b92aa44040/skills/dbt/skills)
- [Databricks Unity Catalog Table API](https://docs.databricks.com/api/workspace/tables/get)
- [Databricks Genie Space API](https://docs.databricks.com/api/workspace/genie/getspace)
- [Databricks Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp)
- [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services)
