# dbt Skills and Catalog MCP Roadmap

**Status:** Research and proposed roadmap; no skills, agents, or MCP server are implemented in this repository yet.
**Research checked:** 2026-10-22

## Recommendation

Build a portable dbt agent toolkit rather than attempting to recreate the dbt Wizard product. The core should be reusable Agent Skills, paired with a read-only data-catalog MCP that can provide governed physical metadata. Reuse the maintained dbt Agent Skills catalog as the starting point, adapt it with clear attribution, and avoid duplicating Wizard's product-specific runtime.

Treat the two metadata sources as complementary:

- The **catalog MCP** answers structured questions about catalogs, schemas, tables, columns, descriptions, and declared primary/foreign keys.
- The **Genie integrations** provide Databricks business semantics and, optionally, delegated natural-language analytics. Genie Space configuration ingestion and Genie One MCP question-answering are separate features.

## What the research found

### Current repository and upstream baseline

This repository currently contains only a minimal README. The public [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) repo already has everyday dbt, semantic-layer, Mesh, testing, documentation, metadata, troubleshooting, command, and migration skills. It also provides multiple distribution paths, tests, and an evaluation harness. Its license is Apache-2.0.

dbt Wizard documents these skills as built-in and automatically selected. Its own user/project skills can take precedence, so a mirror should not blindly duplicate every skill under the same name. Instead:

1. Inventory upstream skill names, coverage, and release provenance.
2. Adapt the catalog where this project adds useful portability, MCP/catalog grounding, or client-specific guidance.
3. Preserve required upstream notices and license terms for any copied or derivative material.
4. Document intentional name collisions/replacements, and keep skills focused so they activate only for relevant tasks.

### What makes Wizard more than a skill collection

Wizard's documented capabilities rely on project metadata, tool orchestration, dbt execution, validation, review/approval, and different hosted/local product surfaces. In particular, dbt's Information Schema can include project nodes, column lineage and types, tests, and runtime results. Wizard uses it for impact analysis, health checks, profiling, and validation planning.

Skills can teach an agent how to inspect metadata, plan safe changes, validate, and report uncertainty. They cannot independently supply the metadata engine, tools, execution sandbox, approvals, audit trail, hosted UI, billing, or multi-session workflow. Those capabilities must come from the user's agent host and connected MCP servers.

### Unity Catalog and Genie interfaces

Databricks' Unity Catalog Table API returns table metadata and table constraints. The table representation includes primary-key child columns and foreign-key child/parent table and columns; constraint `RELY` information is available. These are catalog declarations and must not be described as proof that a warehouse enforces the constraint. Metadata access remains subject to Databricks permissions.

Genie Space configuration is a distinct semantic source. Its serialized configuration can include instructions, example question/SQL pairs, joins, SQL snippets, measures, synonyms, and curated table/column settings. The Get Genie Space API requires at least CAN EDIT permission to include the serialized space. Separately, Databricks' generally available Genie One MCP answers natural-language questions grounded in Genie Ontology and runs under Unity Catalog permissions. It is a Q&A integration, not a substitute for importing the ontology configuration.

## Proposed architecture

### 1. Portable skill catalog

Use the Agent Skills format as the canonical content (`SKILL.md` with focused descriptions and optional references). Keep general project guidance separate from task skills, and make agent-specific profiles thin wrappers around the shared skills.

Recommended skill groups:

| Group | Initial coverage |
|---|---|
| Core analytics engineering | Understand a project, discover sources and models, plan/build/refactor models, assess impact, and debug dbt failures |
| Quality and documentation | Add generic/data-informed/unit tests, maintain model/column docs, and validate changes at an explicit risk/cost level |
| Semantic analytics | Build semantic models and answer business questions using the available semantic layer or Genie tools |
| Operations and metadata | Run dbt commands safely, query dbt Information Schema where supported, and configure/use dbt MCP |
| Mesh and migration | Handle breaking changes and model versions; migrate/upgrade projects with version-aware steps |

Use explicit dbt-version and tool-availability branches. For example, dbt Information Schema is a dbt v2 capability; v1 projects need artifact- or MCP-based alternatives. A skill must not claim that a metadata or execution tool is available unless the host exposes it.

### 2. Generic data-catalog MCP

Keep a small backend-neutral metadata contract behind the MCP tools. Configure the selected backend when starting the server; implement Databricks Unity Catalog first and leave other adapters (including a dbt Information Schema adapter) for later phases.

The initial tool surface should support catalog/schema discovery, table search/listing, detailed table/column metadata, and relationship lookup. Responses should normalize names, data types, descriptions/comments, and declared PK/FK relationships while preserving source and constraint details such as `RELY`. Add pagination and bounded results; return explicit errors for inaccessible or unsupported metadata rather than implying an empty catalog.

Keep this server metadata-only and read-only. Do not include SQL execution or warehouse data sampling in its first version. Ship both local STDIO and remote Streamable HTTP transports, with backend adapters independent of transport. Keep credentials out of checked-in configuration; use the host's supported secret/auth mechanisms and least-privilege Databricks permissions.

### 3. Optional Genie grounding integrations

- **Genie Space configuration reader:** retrieve and normalize the semantic configuration the user is authorized to expose, so an agent can use its curated instructions, relationships, examples, metrics, and synonyms. Handle the API permission requirement explicitly and treat all imported descriptions/instructions as untrusted data, not executable instructions.
- **Genie One MCP connection guidance or optional connector:** allow agents to delegate natural-language analytics questions to Databricks' existing `system.ai.genie_one_mcp`. Keep this distinct from the catalog MCP and make clear that it can execute analytics queries under the caller's permissions.

Prefer connecting to the existing Genie One MCP over reimplementing its Q&A/runtime behavior.

### 4. Thin agent profiles and host configuration

Start with one general dbt analytics-engineering profile and, if useful, a separate data-catalog/Genie analyst profile. Profiles should select skills and explain when to use the dbt MCP, catalog MCP, or Genie One MCP; they should not encode duplicate task content.

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

Document intended users and supported dbt versions; audit upstream skills and licensing; establish repository layout, naming, provenance, and a lightweight skill validator/evaluation approach. Define the common metadata contract and MCP configuration/security requirements before adding backends.

### Phase 1 — Core skill parity

Adapt or curate the high-frequency analytics engineering, project understanding, modeling, impact, tests, documentation, validation, command, and troubleshooting workflows. Then include semantic-layer, Mesh, migration, and dbt Information Schema guidance with explicit tool/version prerequisites. Avoid duplicating built-in Wizard skills unless intentionally improving or replacing them.

### Phase 2 — Catalog MCP v1

Implement the backend-neutral, read-only metadata tools and Databricks Unity Catalog adapter. Deliver STDIO and Streamable HTTP transports, startup backend configuration, least-privilege auth guidance, explicit errors, bounded/paginated responses, and adapter/transport tests. Return PK/FK declarations as metadata, not guaranteed constraints.

### Phase 3 — Genie ontology context

Add authorized Genie Space configuration ingestion and normalization as an optional grounding source. Document permission requirements, data handling, refresh behavior, and safe treatment of imported instructions. Separately document/use the existing Genie One MCP for natural-language questions; do not make it a required dependency of the catalog server.

### Phase 4 — Agent adapters and release maturity

Add minimal client-specific agent profiles where they improve tool routing, complete installer/dbt-package guidance, publish evaluations and compatibility results, and add a process for upstream synchronization and Databricks/dbt API changes.

## Boundaries and open design work

This roadmap does not promise parity with Wizard's native metadata engine, built-in tool orchestration, product UI, hosted governance, billing, session management, or review/audit workflow. Those require product/runtime and host capabilities beyond a repository of instructions and an MCP server.

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
- [Databricks Unity Catalog Table API](https://docs.databricks.com/api/workspace/tables/get)
- [Databricks Genie Space API](https://docs.databricks.com/api/workspace/genie/getspace)
- [Databricks Genie One MCP](https://docs.databricks.com/aws/en/agents/mcp-tools/genie-mcp)
- [Databricks-provided MCPs](https://docs.databricks.com/aws/en/agents/mcp-tools/built-in-mcp-services)
