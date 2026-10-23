# dbt-skills

**Start here:** [Run locally with Northwind and Copilot](docs/RUN_LOCALLY.md).

Try the read-only [modelling policy CLI](docs/MODELLING_POLICY.md) to validate
standards, resolve team-defined naming templates and locate existing policy files.
Use [convention discovery](docs/CONVENTION_DISCOVERY.md) to propose naming layouts
from a validated manifest with evidence, counterexamples and clarification questions.
[Compare filenames with a selected policy](docs/POLICY_COMPARISON.md) to identify
structural matches, mismatches and unresolved rule scope.
[Prepare pending decision proposals](docs/DECISION_PROPOSALS.md) for a model exception
or an explicit template change, with evidence and reviewable patches.

> **2026-10-23 direction:** See the [agreed architecture](docs/ARCHITECTURE.md) for the current workflow and delivery order: Copilot in VS Code first, shared project/catalog context, optional UOL, and modelling policy before a standalone agent runtime. Earlier sequencing below is historical.


Roadmap for an open-source, local-first alternative to dbt Wizard, focused on dbt skills, project context, MCP integrations, and catalog/ontology grounding. OpenDataSuite is a broader sibling project, not a bundled dependency or scope expansion. This project will evaluate optional interoperability with ODS's read-only MCP for open-source column-lineage and impact evidence; the core must remain useful without ODS.

See [ROADMAP.md](ROADMAP.md) for the product goals, architecture, upstream dbt skill strategy, generic catalog MCP, Unity Catalog and Genie integration plan, compatibility considerations, and priorities.

For local artifact status, freshness, and manifest resource dependencies, use the opt-in [artifact inspector](docs/ARTIFACT_INSPECTION.md).

See [docs/HANDOVER.md](docs/HANDOVER.md) for the current implementation baseline, repository map, remaining dependencies, and recommended execution sequence.

The local Unified Ontology Layer cache, manifest/ODS sources, stdio MCP tools, encrypted storage, and migration/security boundaries are documented in [docs/UOL_LOCAL.md](docs/UOL_LOCAL.md). Third-party notices for distributed dependencies are in [docs/THIRD_PARTY_NOTICES.md](docs/THIRD_PARTY_NOTICES.md). The initial source-tree CLI/runtime is described in [docs/LOCAL_RUNTIME.md](docs/LOCAL_RUNTIME.md); it can inspect a dbt project and send a scripted prompt through an OpenAI-compatible local or hosted endpoint, but remains separate from agent-tool orchestration. GitHub Copilot CLI setup and host-integration boundaries are described in [docs/COPILOT_CLI.md](docs/COPILOT_CLI.md). The UOL MCP bridge does not replace dbt MCP, and remains separate from the [Unity Catalog metadata adapter](docs/UNITY_CATALOG.md).

Local Copilot integration: [VS Code modelling MCP setup](docs/COPILOT_VSCODE.md).

Structured metadata: [catalog providers and ordered resolution](docs/CATALOG.md), with a [local customer model-design walkthrough](examples/catalog-workflow/README.md).

The agent creates or revises a data-model design across entities and relationships.
This repository supplies its grounding context; it does not generate or apply dbt SQL.

The shared [design planner](docs/MODEL_PLANNING.md) assembles entity/key/relationship candidates, applicable modelling standards and targeted questions from selected catalog assets and the same project snapshot. It identifies existing models for reuse review; no normal-form proof or automatic semantic design is claimed.

Before physical assets exist, provide [business concepts and relationships](docs/BUSINESS_CONTEXT.md)
through a human-owned context file. The agent can use definitions, rationale and
provenance to reason about the complete data model without requiring UOL or a catalog.

Catalog context supports [bounded local caching](docs/CATALOG_CACHE.md), including optional encrypted persistence and no metadata TTL.
