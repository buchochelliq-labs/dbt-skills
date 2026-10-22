# GitHub Copilot CLI integration

This repository provides a portable Agent Skill and a thin GitHub Copilot CLI custom agent:

- `.github/skills/dbt-context-routing/SKILL.md` contains host-neutral context-routing instructions.
- `.github/agents/dbt-analytics-engineer.agent.md` adds a Copilot CLI profile that points to the shared skill and does not declare a tool allowlist.

Copilot CLI discovers project skills under `.github/skills/` and project custom agents under `.github/agents/`. From the repository root, verify discovery in an interactive Copilot CLI session:

```text
/skills list
/skills info dbt-context-routing
/agent
```

Select `dbt-analytics-engineer` from `/agent`, or run it directly:

```powershell
copilot --agent dbt-analytics-engineer --prompt "Explain the selected dbt project's available context."
```

The general dbt workflows are intentionally not duplicated. Use the upstream [`dbt-labs/dbt-agent-skills`](https://github.com/dbt-labs/dbt-agent-skills) installation guidance for its modeling, test, documentation, migration, or command skills. To add a selected skill to Copilot CLI, its documented `copilot skill add <FILE | URL | DIRECTORY>` command accepts a local skill path or URL; verify discovery with `/skills list`. Installing dbt package skills with `dbt deps` does not by itself establish that they are installed in Copilot CLI. Skill availability and selection can vary by CLI version and local configuration.

## Local UOL MCP setup

Copilot CLI can load user-level MCP configuration and project-level configuration. For local project work, the CLI's supported setup options include `/mcp add`, the `copilot mcp add` subcommand, and project MCP configuration files. Consult the current [Copilot CLI MCP setup guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) for the file formats and trust behavior. Project MCP configuration is subject to repository trust; `.vscode/mcp.json` is not read by Copilot CLI.

The repository includes a local stdio MCP bridge for the UOL cache. From the repository root, install its pinned dependencies and register it with Copilot CLI:

```powershell
python -m pip install -r requirements.txt
copilot mcp add dbt-skills-uol --env PYTHONPATH=src -- python -m dbt_skills.uol_mcp --project-dir .
```

The bridge exposes local cache reads and separate source-sync, cache-read, and purge tools. Configure manifest/ODS sources and scopes through the UOL CLI first; details and the complete tool list are in [the UOL guide](UOL_LOCAL.md). Verify host discovery with `/mcp list`, `/mcp show dbt-skills-uol`, or `copilot mcp list`. Copilot CLI discovery and approval behavior have not been live-tested in this environment.

Configure other servers only when needed, using their vendor's current setup and authentication guidance. A server's name is not evidence that a particular tool, permission, or data source is available. This repository still does not provide a dbt MCP server, a physical-catalog MCP server, or remote ontology adapters such as Ontos, OntoBricks, Unity Catalog, or Genie.

## Credentials and permissions

- Do not commit credentials, authorization headers, user-specific endpoints, or populated MCP secrets in `.github/mcp.json`, `.mcp.json`, or any other repository file.
- Avoid placing secrets in shell history or command-line arguments. Copilot CLI supports MCP environment variables and headers, but their storage and exposure depend on the chosen configuration and server; use an approved credential mechanism and check where values persist.
- Use least-privilege credentials and expose only the tools required for the task. A client-side tool selection is not a replacement for server-side authorization.
- Treat project MCP configuration as executable integration setup: review server commands, packages, URLs, and requested permissions before trusting a repository.
- The UOL bridge's read-only/destructive annotations are hints, not access controls. Configure Copilot CLI to request per-call approval for state-changing UOL tools; do not add those tools to an auto-approval list. The custom agent profile and skill cannot enforce tool approval behavior.

## Current boundaries

The Python `dbt-skills ask` command sends one text prompt and minimal project metadata to a configured model endpoint. It does not provide agent tools, inspect model SQL, or execute dbt commands. The UOL stdio MCP bridge is a separate agent-facing service backed by the encrypted local cache; static manifest/ODS sources are available, but remote ontology providers are not implemented. Cache encryption protects files at rest, not data accessible to a compromised account or authorized process. See [the local runtime guide](LOCAL_RUNTIME.md), [the UOL guide](UOL_LOCAL.md), and issues #11 and #30 for the respective boundaries.

The supported skill and custom-agent conventions are documented by GitHub in [Adding agent skills for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) and [Creating and using custom agents for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli).
