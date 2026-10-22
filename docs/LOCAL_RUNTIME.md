# Local runtime prototype

The first runtime is intentionally small: it discovers a local dbt project, stores a non-secret model endpoint profile in that project, and sends one scripted prompt plus minimal project metadata to a configured model provider. It does not execute shell commands, read model SQL, invoke MCP tools, or make changes to the dbt project.

## Requirements and runtime selection

- Python 3.11 or newer.
- Python standard library for CLI, TOML, HTTP, and SQLite functionality.
- PyYAML 6.0.3 (MIT) for safe parsing of `dbt_project.yml`; see `requirements.txt`.
- An OpenAI Chat Completions-compatible model endpoint. The default endpoint is a local Ollama-compatible endpoint; hosted endpoints can be configured with HTTPS and an environment variable for the API key.

The CLI uses `argparse`; no general-purpose agent framework or model SDK is selected. `ModelProvider` in `src/dbt_skills/providers.py` is the replaceable provider seam. The first adapter sends text-only prompts and does not support tool calls. dbt MCP remains the route for dbt platform operations; this runtime does not duplicate those tools.

This is a source-tree prototype, not an installable distribution. The repository currently has no declared license metadata, so package/distribution work must wait for the licensing decision. The official MCP Python SDK pinned in `requirements.txt` is used by the optional ODS MCP adapter, not by this CLI's model-provider adapter.

## Setup

From the repository root in PowerShell:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m dbt_skills.cli --help
```

Initialize a dbt project. This only writes a new `.dbt-skills/config.toml`; it refuses to overwrite an existing config and does not change `dbt_project.yml`, profiles, or `.gitignore`.

```powershell
python -m dbt_skills.cli init --project-dir C:\path\to\dbt-project
python -m dbt_skills.cli inspect --project-dir C:\path\to\dbt-project
```

Set a local model name in `.dbt-skills/config.toml`, for example:

```toml
[model]
provider = "openai-compatible"
base_url = "http://127.0.0.1:11434/v1"
model = "qwen3:8b"
api_key_env = "OPENAI_API_KEY"
timeout_seconds = 60
```

Then run a scripted prompt:

```powershell
python -m dbt_skills.cli ask "Summarize the configured dbt project." --project-dir C:\path\to\dbt-project
```

For a hosted endpoint, set an HTTPS `base_url` and place the API key in the configured environment variable. For example:

```powershell
$env:OPENAI_API_KEY = "<your key>"
python -m dbt_skills.cli ask "Summarize the configured dbt project." --project-dir C:\path\to\dbt-project --base-url https://api.openai.com/v1 --model <model>
```

The secret is never accepted as a command-line value or written to the project config. HTTPS is required for non-loopback endpoints; plaintext HTTP is accepted only for `localhost` or an IP loopback address. Redirects are not followed, and the provider response is capped at 8 MiB. Model prompts send project name, version, profile name, project root, and whether `target/manifest.json` exists. They do not include manifest contents or credentials. The endpoint receives the prompt and that metadata, so use only a provider and project context appropriate for the data handling policy.

## Scope and limitations

- `inspect` searches upward from the selected directory for `dbt_project.yml`, parses it with PyYAML `safe_load`, and reports its name/version/profile and manifest-file presence. It does not open `profiles.yml`, inspect artifacts, or run dbt.
- `ask` requires a project-local config created by `init`; CLI flags and `DBT_SKILLS_MODEL` / `DBT_SKILLS_BASE_URL` environment variables can override non-secret defaults.
- Provider errors are surfaced without echoing response bodies or credentials.
- Retrieved project metadata is marked untrusted in the system prompt. This prompt instruction is a defense-in-depth hint, not a security boundary or substitute for reviewing provider data handling.
- There is no tool use, interactive conversation memory, streaming, automatic file editing, approvals, or warehouse access. Tool execution must wait for policy/approval controls (issue #11).
- The text-only `dbt-skills ask` runtime does not query the UOL. A separate local stdio MCP bridge exposes the UOL cache to compatible agent hosts, including manifest resource lineage and optional ODS column-lineage claims; keep these evidence types distinct. See [the UOL guide](UOL_LOCAL.md) for setup and boundaries.

## Validation evidence

The runtime tests exercise nested project discovery, invalid/missing config, safe initialization, injected-provider execution without a hosted account, OpenAI-compatible request shape, API-key environment lookup, local-only HTTP restrictions, response-size limits, redirect rejection, and sanitized HTTP errors. No live model endpoint is contacted by tests.
