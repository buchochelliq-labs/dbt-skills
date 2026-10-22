# dbt-skills

Roadmap for an open-source, local-first alternative to dbt Wizard, focused on dbt skills, project context, MCP integrations, and catalog/ontology grounding. OpenDataSuite is a broader sibling project, not a bundled dependency or scope expansion. This project will evaluate optional interoperability with ODS's read-only MCP for open-source column-lineage and impact evidence; the core must remain useful without ODS.

See [ROADMAP.md](ROADMAP.md) for the product goals, architecture, upstream dbt skill strategy, generic catalog MCP, Unity Catalog and Genie integration plan, compatibility considerations, and priorities.

The local-first ontology cache prototype and its current limitations are documented in [docs/UOL_LOCAL.md](docs/UOL_LOCAL.md). It currently supports offline JSON snapshots only; remote ontology adapters and agent-runtime integration are follow-up work.