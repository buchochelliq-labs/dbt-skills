# Run locally: Northwind to a grounded data-model design

This walkthrough builds a fictional source database, exports schema metadata, and
connects that metadata to Copilot in VS Code. No Databricks account, warehouse, dbt
installation or model API key is needed for the local CLI walkthrough. Copilot itself
requires your normal VS Code/Copilot access and connectivity; local context does not
make the hosted assistant offline. The MCP server receives metadata, never database rows.

## 1. Get the checkout and Python environment

Use Git and Python 3.11 or newer. Until PR #64 is merged, use its branch:

```sh
git clone --branch feat/northwind-source-fixture https://github.com/buchochelliq-labs/dbt-skills.git
cd dbt-skills
python -m venv .venv
```

After the fixture is merged, a normal clone of `main` works instead. In an existing
checkout, preserve your changes before switching branches. Activate the environment:

```sh
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Then, on either platform:

```sh
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of
`python`; activation is a convenience. These are source-checkout commands: the
package is loaded through `PYTHONPATH`, not an editable package install.

## 2. Build the source outside the checkout

Run from the repository root:

```sh
python examples/northwind-source/build.py --output-dir ../northwind-demo
```

The destination must not already exist. For another run choose a new directory.
The result contains eight tables and 472 fictional rows in `northwind.sqlite3`,
plus schema-only catalog metadata, policy, request and a synthetic manifest.
No dbt execution is required; the manifest is a test fixture, not real lineage.

For the agent's workspace, create a second directory named `northwind-context`
next to `northwind-demo`. Copy these generated files into it:

- `catalog.json`, `catalogs.json`, `modelling.yml`, `dbt_project.yml`, `design-request.json`
- the `artifacts` directory (including `manifest.json`)

Keep `northwind.sqlite3` in the source directory; do not copy it into the agent's
workspace. The MCP server needs only the context files. Workspace separation is
helpful but is not a sandbox: restrict the agent to this server's tools below.

## 3. Try the planner without Copilot

Set the source import path from the repository root:

```sh
# macOS / Linux
export PYTHONPATH="$PWD/src"
```

```powershell
# Windows PowerShell
$env:PYTHONPATH = (Join-Path $PWD 'src')
```

Run this command on either platform (one line):

```sh
python -m dbt_skills.model_planning --project-dir ../northwind-context --target-path artifacts --policy modelling.yml --catalog-config catalogs.json --request design-request.json
```

Expect JSON with four selected entity candidates (customers, orders, order details,
products), three relationships whose selected endpoints resolve, provenance and
clarification questions. Exit **2** means `needs_clarification`, which is expected;
exit 0 means pending review, and exit 1 means blocked/error. Neither means the
business design is approved. Other relationship targets are not silently fetched.
Key declarations do not prove cardinality, uniqueness or 3NF.

## 4. Connect VS Code / Copilot

Open **northwind-context** as the VS Code folder. Create `.vscode/mcp.json` there,
or merge this server into its existing `servers` object:

```json
{
  "servers": {
    "dbt-modelling": {
      "type": "stdio",
      "command": "/absolute/path/to/dbt-skills/.venv/bin/python",
      "args": [
        "-m", "dbt_skills.modelling_mcp",
        "--project-dir", "/absolute/path/to/northwind-context",
        "--target-path", "artifacts",
        "--policy", "modelling.yml",
        "--catalog-config", "catalogs.json"
      ],
      "env": {"PYTHONPATH": "/absolute/path/to/dbt-skills/src"}
    }
  }
}
```

Replace all three absolute paths. On Windows use the venv's
`.venv/Scripts/python.exe`; forward slashes in JSON avoid backslash escaping.
Copy the repository's `.github/agents/dbt-modelling.agent.md` into
`northwind-context/.github/agents/`. Start/trust the MCP server through VS Code's
MCP controls, select the **dbt modelling** agent, and inspect enabled tools. Enable
this server's tools for the session; do not add database, terminal or unrestricted
file tools. See [host setup](COPILOT_VSCODE.md) for configuration variants.

Paste this prompt into the agent chat:

> Use modelling_context first and pass its context ID to subsequent tools. Design
> a customer/order data model using urn:northwind:customers, urn:northwind:orders,
> urn:northwind:order_details and urn:northwind:products, with layer=core scope for
> each. Read the applicable modelling rules and call model_plan. Explain entities,
> candidate keys, grain and relationships with provenance. Ask me about missing
> business intent, cardinality and functional dependencies before recommending a
> 3NF design. Only fetch explicitly selected project assets. Do not access source
> rows or generate implementation SQL. Present assumptions separately from facts.

Discuss the returned questions. Add another asset explicitly only if the design
requires it. Use `modelling_render` to discuss names under the configured token
rules. Standards changes and exceptions remain reviewable pending proposals;
the server does not save or approve them.

After you edit selected context files, call `modelling_refresh` and use its new
context ID. Restart the server after changing startup paths or project configuration.
For saved decisions, follow [decision records](MODEL_PLANNING.md#reuse-reviewed-grain-and-history-decisions).

## 5. Optional: load the source into Unity Catalog

Build a separate fixture with your intended physical names:

```sh
python examples/northwind-source/build.py --output-dir ../northwind-uc --catalog your_catalog --schema northwind_demo
```

Upload its SQLite file to an existing UC volume. Import
`examples/northwind-source/load_unity_catalog.py` as a Databricks Python notebook,
set `catalog`, `schema` and `sqlite_path`, then run on suitable UC-enabled compute.
Use a fresh destination: the loader refuses to overwrite tables and partial failures
can leave some tables created. The [source README](../examples/northwind-source/README.md#load-the-same-source-into-unity-catalog)
covers permissions, paths and constraint limitations. Loading data does not configure
the agent's live catalog provider; that is a separate [Unity Catalog setup](UNITY_CATALOG.md).

## Troubleshooting and acceptance

| Symptom | Check |
| --- | --- |
| `No module named dbt_skills` | Set `PYTHONPATH` to this checkout's `src`; MCP needs its own `env` entry. |
| Dependency import fails | Install requirements using the same Python executable selected in MCP. |
| Build refuses destination | Select a new output directory; the builder intentionally refuses overwrite. |
| No tools in VS Code | Check absolute paths, server startup output and host trust/tool settings. |
| Server appears to wait in a terminal | MCP stdio waits for protocol messages; use the planner CLI for terminal output. |
| Missing manifest or policy | Verify the context copy, `artifacts/manifest.json`, and configured paths. |
| Planner exits 2 | Read and answer clarification questions; this is expected for the fixture. |
| Stale context ID | Refresh and pass the new ID; restart for startup configuration changes. |

The fixture and real MCP protocol workflow have automated coverage. Live Copilot
UI/reasoning and live Databricks loading remain acceptance checks; this guide does
not claim those have passed. Record results with the [acceptance checklist](COPILOT_ACCEPTANCE.md).
