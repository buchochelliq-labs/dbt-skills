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

## MCP setup

Copilot CLI can load user-level MCP configuration and project-level configuration. For local project work, the CLI's supported setup options include `/mcp add`, the `copilot mcp add` subcommand, and project MCP configuration files. Consult the current [Copilot CLI MCP setup guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers) for the file formats and trust behavior. Project MCP configuration is subject to repository trust; `.vscode/mcp.json` is not read by Copilot CLI.

Configure only the servers you need, using their vendor's current setup and authentication guidance. Check the live server and tool list with `/mcp list`, `/mcp show <server-name>`, or `copilot mcp list`. A server's name is not evidence that a particular tool, permission, or data source is available.

This repository does not provide a dbt MCP server, a physical-catalog MCP server, or an ontology-provider MCP adapter. It also does not currently expose the local UOL cache or sync controls to Copilot. Those capabilities must be installed and configured separately; UOL-to-agent integration is tracked in issue #31.

## Credentials and permissions

- Do not commit credentials, authorization headers, user-specific endpoints, or populated MCP secrets in `.github/mcp.json`, `.mcp.json`, or any other repository file.
- Avoid placing secrets in shell history or command-line arguments. Copilot CLI supports MCP environment variables and headers, but their storage and exposure depend on the chosen configuration and server; use an approved credential mechanism and check where values persist.
- Use least-privilege credentials and expose only the tools required for the task. A client-side tool selection is not a replacement for server-side authorization.
- Treat project MCP configuration as executable integration setup: review server commands, packages, URLs, and requested permissions before trusting a repository.
- Copilot CLI's approval prompts and tool policies are the effective controls. The custom agent profile and skill cannot enforce read-only access or approval behavior.

## Current boundaries

The Python `dbt-skills ask` command sends one text prompt and minimal project metadata to a configured model endpoint. It does not provide agent tools, connect Copilot to the UOL, inspect model SQL, or execute dbt commands. The UOL CLI remains a separate local interface; provider-backed ontology synchronization is not implemented. See [the local runtime guide](LOCAL_RUNTIME.md), [the UOL guide](UOL_LOCAL.md), and issues #11, #30, and #31 for the respective follow-up boundaries.

The supported skill and custom-agent conventions are documented by GitHub in [Adding agent skills for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills) and [Creating and using custom agents for Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli).
