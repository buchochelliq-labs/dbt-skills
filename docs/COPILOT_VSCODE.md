# Copilot in VS Code: local modelling tools

This first adapter exposes the shared modelling core over MCP stdio. It supports context, clarification, naming comparison and pending decision proposals. With policy and catalog configuration, `model_draft` also generates source-projection SQL/YAML for review; a separate operator CLI can create the reviewed files. It does not apply standards decisions, prove normal forms or access warehouses. See [model drafts](MODEL_DRAFTS.md). UOL is optional and is not imported by this adapter.

## Setup

Use Python 3.11+ and install this checkout's `requirements.txt` into a virtual environment. Prepare a local dbt project and its manifest using your normal dbt workflow. Select a validated policy document (see [modelling policy](MODELLING_POLICY.md)); omit `--policy` to use context and inference without declared rules.

Choose the example matching your VS Code harness:

| Harness | Example | Install location | Root key |
| --- | --- | --- | --- |
| Copilot portable configuration | [mcp.portable.json](../examples/vscode/mcp.portable.json) | project `.mcp.json` | `mcpServers` |
| VS Code Local | [mcp.local.json](../examples/vscode/mcp.local.json) | project `.vscode/mcp.json` | `servers` |

Replace all absolute path placeholders with paths on the machine running the server. `command` must be the virtual environment's Python executable; `PYTHONPATH` points to this checkout's `src`. Merge the server entry into existing configuration. Do not overwrite other servers. The examples use no interactive input variables. On Windows, JSON paths need escaped backslashes or forward slashes.

`--policy` and optional `--proposals` paths are relative to the selected project unless absolute. The proposals file must already exist and have kind `proposals`; it is never created or changed by the server. Use `--target-path` when artifacts are not in the project's configured target directory. Paths are operator-selected startup settings, never tool arguments.

Start/trust the configured server using the host's MCP controls, inspect its discovered tools, and enable only this server's tools for this workflow. For the Local harness, copy [dbt-modelling.agent.md](../.github/agents/dbt-modelling.agent.md) into the project's `.github/agents/` directory and select it. Its server wildcard allowlist targets Local; check harness-specific support before reuse. Host permissions and other enabled tools remain the operator's responsibility: annotations and prose are not a sandbox.

Optional structured catalog metadata: add `--catalog-config catalogs.json` to server arguments. This registers three additional read-only tools; see [catalog contract](CATALOG.md) and the [customer walkthrough](../examples/catalog-workflow/README.md).

## Workflow

| Tool | Result |
| --- | --- |
| `modelling_context` | Context ID, selected provenance and capability limits |
| `modelling_rules` | Bounded pages of declared rules and referenced token questions |
| `modelling_infer` | Naming hypotheses, evidence, counterexamples and questions |
| `modelling_render` | Resolved name or missing-token questions |
| `modelling_compare` | Naming matches, differences or unresolved scope |
| `modelling_propose` | Pending one-model exception or explicitly requested template-change proposal |
| `modelling_refresh` | New snapshot and context ID, invalidating old IDs |

Start with context and pass its ID to subsequent tools. The manifest and inferred document filename inventory remain pinned until explicit refresh. Rules are pinned too; operations that re-read the policy reject a changed hash before returning results. Pending proposal generation likewise checks its selected base. Refresh replaces context only after capture succeeds. Changes to project configuration or selected paths require a server restart.

Example request: “Read our modelling rules, ask about missing business intent, and compare this model's filename. If an exception is needed, prepare a one-model proposal with its rationale for review.” Inference is not approval. 3NF/4NF targets guide discussion but are not mechanically certified. This adapter emits no compiled SQL, source rows or samples; metadata and human-authored policy text remain untrusted context.

## Verification and remaining host check

Automated tests launch the real stdio process and exercise discovery, clarification, comparison, proposal generation, snapshot refresh, changed-policy rejection and no-write behavior. Run `PYTHONPATH=src python -m unittest discover -s tests -p test_modelling_mcp.py -v` from this checkout.

A live VS Code/Copilot session has **not** been verified in the implementation environment because VS Code is unavailable. Before rollout, verify in the intended harness: all seven base tools and the configured optional tools appear; context identifies the intended project; missing tokens produce questions; comparison cites evidence; a proposal remains pending and leaves files unchanged; refresh invalidates the old ID. Check the host's trust/approval prompts and that no unrelated data-access tools are enabled. Protocol tests do not establish UI compatibility or host permission behavior.

Configuration references (checked 2026-10-23): [MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers), [MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration), [custom agent files](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference).

### Validate an applied draft

After operator application, call `model_validate(context_id, draft_id)` for a draft returned by this server. Only the last four drafts are retained; context refresh invalidates them. The tool checks local integrity and the restricted projection contract, returning fixed statuses. It does not run dbt. For an explicitly approved local parse, follow the [operator CLI instructions](MODEL_DRAFTS.md#optional-operator-only-dbt-parse). A local or parse pass is not proof of warehouse correctness or normal form.

### Plan the data model before SQL

With policy and catalogs configured, call `model_plan(context_id, request)` to ground the design in selected assets, scoped standards, declared keys/relationships and existing resource lineage. Discuss the returned questions with the human before choosing grain/history or generating files. See the [request and walkthrough](MODEL_PLANNING.md). The tool returns design hypotheses and provenance, never writes or executes SQL.

To reuse reviewed grain/history choices, add `--design-decisions design-decisions.json`
to the server arguments alongside policy and catalogs. Copy each entity's
`decision_context` into a human-reviewed record as described in
[design planning](MODEL_PLANNING.md#reuse-reviewed-grain-and-history-decisions).
After changing the file, call `modelling_refresh` and use its new context ID. Saved
attribution is not authenticated approval; dependency questions still require review.
