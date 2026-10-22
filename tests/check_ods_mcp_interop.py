import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class StdioMCPClient:
    def __init__(self, command):
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Could not open the ODS stdio pipes")
        self._stdin = self.process.stdin
        self._lines = queue.Queue()
        self._next_id = 1
        threading.Thread(target=self._collect_lines, daemon=True).start()

    def _collect_lines(self):
        for line in self.process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, message):
        self._stdin.write(json.dumps(message) + "\n")
        self._stdin.flush()

    def _response(self, request_id):
        while True:
            try:
                line = self._lines.get(timeout=15)
            except queue.Empty as error:
                raise TimeoutError("Timed out waiting for an ODS MCP response") from error
            if line is None:
                raise RuntimeError("ODS MCP exited before returning a response")
            message = json.loads(line)
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"ODS MCP request failed: {message['error']}")
                return message.get("result", {})

    def request(self, method, params):
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        return self._response(request_id)

    def notify(self, method):
        self._send({"jsonrpc": "2.0", "method": method})

    def call_tool(self, name, arguments):
        result = self.request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        if result.get("isError"):
            raise RuntimeError(f"ODS MCP tool {name} returned an error: {result}")
        payload = result.get("structuredContent")
        if not isinstance(payload, dict):
            raise RuntimeError(f"ODS MCP tool {name} returned no structured content")
        return payload

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)


def check_artifact_mode(ods, project, target, artifacts):
    client = StdioMCPClient(
        [
            ods,
            "mcp",
            "--project-dir",
            str(project),
            "--target-dir",
            str(target),
            "--artifacts",
            artifacts,
            "--log-level",
            "off",
        ]
    )
    try:
        initialized = client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "dbt-skills-compat-check", "version": "0.0.1"},
            },
        )
        if initialized.get("protocolVersion") != "2025-06-18":
            raise RuntimeError(
                f"Unexpected negotiated MCP protocol: {initialized.get('protocolVersion')}"
            )
        server = initialized.get("serverInfo", {})
        if server.get("name") != "ods" or server.get("version") != "0.0.2":
            raise RuntimeError(f"Unexpected ODS server identity: {server}")
        client.notify("notifications/initialized")

        tools = client.request("tools/list", {}).get("tools", [])
        tool_by_name = {tool["name"]: tool for tool in tools}
        names = set(tool_by_name)
        required = {
            "ods_project_summary",
            "ods_lineage",
            "ods_impact",
            "ods_list_opaque",
        }
        if not required.issubset(names):
            raise RuntimeError(f"ODS MCP is missing tools: {sorted(required - names)}")
        lineage_schema = tool_by_name["ods_lineage"].get("inputSchema", {})
        if "focus" not in lineage_schema.get("required", []):
            raise RuntimeError(f"Unexpected ods_lineage input schema: {lineage_schema}")
        impact_schema = tool_by_name["ods_impact"].get("inputSchema", {})
        if "columns" not in impact_schema.get("properties", {}):
            raise RuntimeError(f"Unexpected ods_impact input schema: {impact_schema}")

        summary = client.call_tool("ods_project_summary", {})
        if summary.get("dbt_version") != "2.0.8":
            raise RuntimeError(f"ODS did not report dbt-oss 2.0.8: {summary}")
        expected_artifacts = {
            "json": "manifest.json",
            "info-schema": "dbt Information Schema (Parquet)",
        }[artifacts]
        if summary.get("artifacts") != expected_artifacts:
            raise RuntimeError(f"ODS selected an unexpected artifact source: {summary}")
        if summary.get("adapter_type") != "duckdb":
            raise RuntimeError(f"ODS reported an unexpected adapter: {summary}")
        if summary.get("counts", {}).get("models") != 4:
            raise RuntimeError(f"ODS reported unexpected model count: {summary}")
        if summary.get("lineage", {}).get("models_opaque") != 1:
            raise RuntimeError(f"ODS reported unexpected opaque models: {summary}")

        lineage = client.call_tool(
            "ods_lineage", {"focus": ["customer_summary.normalized_name"]}
        )
        expected_edge = any(
            edge["from"]["column"] == "customer_name"
            and edge["to"]["column"] == "normalized_name"
            and edge["kind"]["subtype"] == "transformation"
            for edge in lineage.get("column_edges", [])
        )
        if not expected_edge:
            raise RuntimeError(f"ODS did not return the expected lineage edge: {lineage}")

        impact = client.call_tool(
            "ods_impact",
            {"columns": ["base_customers.customer_name=modified"]},
        )
        if "model.ods_dbt_compat.customer_metrics" not in impact.get(
            "impact", {}
        ).get("nodes", {}):
            raise RuntimeError(f"ODS did not return the expected downstream impact: {impact}")

        opaque = client.call_tool("ods_list_opaque", {})
        opaque_nodes = opaque.get("opaque", [])
        if len(opaque_nodes) != 1 or opaque_nodes[0].get("name") != "opaque_passthrough":
            raise RuntimeError(f"Expected the unexpanded source wildcard to be opaque: {opaque}")
        if not any("columns are unknown" in item for item in opaque_nodes[0].get("diagnostics", [])):
            raise RuntimeError(f"ODS did not explain the opaque source columns: {opaque}")
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Compile and contract-check the optional ODS MCP provider."
    )
    parser.add_argument("--dbt", default="dbt", help="Path to the dbt CLI")
    parser.add_argument("--ods", default="ods", help="Path to the ODS CLI")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).parent / "fixtures" / "ods-dbt-oss-2.0.8",
        help="dbt project fixture to compile",
    )
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    if not (fixture / "dbt_project.yml").is_file():
        parser.error(f"dbt fixture not found: {fixture}")

    with tempfile.TemporaryDirectory(prefix="dbt-ods-compat-") as temp_dir:
        target = Path(temp_dir)
        command = [
            args.dbt,
            "compile",
            "--generate-info-schema",
            "--static-analysis",
            "strict",
            "--project-dir",
            str(fixture),
            "--profiles-dir",
            str(fixture),
            "--target-path",
            str(target),
            "--log-path",
            str(target / "logs"),
            "--no-version-check",
        ]
        compiled = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        sys.stdout.write(compiled.stdout)
        sys.stderr.write(compiled.stderr)
        if compiled.returncode:
            raise RuntimeError(f"dbt compile failed with exit code {compiled.returncode}")
        if not (target / "manifest.json").is_file():
            raise RuntimeError("dbt compile did not produce manifest.json")
        if not (target / "info_schema" / "v1" / "dbt.models.parquet").is_file():
            raise RuntimeError("dbt compile did not produce the v2 Parquet Information Schema")

        for artifacts in ("json", "info-schema"):
            check_artifact_mode(args.ods, fixture, target, artifacts)
            print(f"ODS MCP {artifacts} contract: passed")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, TimeoutError, json.JSONDecodeError) as error:
        print(f"ODS interoperability check failed: {error}", file=sys.stderr)
        sys.exit(1)
