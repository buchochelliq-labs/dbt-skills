import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dbt_skills.ods_mcp import ODSAnalysis, ODSMCPConfig, ODSUnavailable, analyze_ods


async def check_artifact_mode(dbt, ods, fixture, artifacts):
    with tempfile.TemporaryDirectory(prefix="dbt-ods-sdk-") as temp_dir:
        target = Path(temp_dir)
        command = [
            dbt,
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

        config = ODSMCPConfig(
            command=ods,
            project_dir=fixture,
            target_dir=target,
            artifacts=artifacts,
        )
        analysis = await analyze_ods(
            config,
            focus=["customer_summary.normalized_name"],
            changes=["base_customers.customer_name=modified"],
        )
        if isinstance(analysis, ODSUnavailable):
            raise RuntimeError(f"ODS did not analyze the fixture: {analysis.reason}")
        if not isinstance(analysis, ODSAnalysis):
            raise RuntimeError(f"Unexpected ODS response: {analysis}")
        if analysis.coverage != "complete":
            raise RuntimeError(
                f"Expected complete focus coverage, got {analysis.coverage}: {analysis.reason}"
            )
        if analysis.project_summary.get("dbt_version") != "2.0.8":
            raise RuntimeError(f"ODS reported unexpected project version: {analysis.project_summary}")
        if analysis.protocol_version == "":
            raise RuntimeError("The MCP SDK did not expose the negotiated protocol version")
        if not any(
            edge["from"]["column"] == "customer_name"
            and edge["to"]["column"] == "normalized_name"
            and edge["kind"]["subtype"] == "transformation"
            for edge in analysis.lineage.get("column_edges", [])
        ):
            raise RuntimeError(f"Expected column lineage edge was absent: {analysis.lineage}")
        if "model.ods_dbt_compat.customer_metrics" not in analysis.impact.get(
            "impact", {}
        ).get("nodes", {}):
            raise RuntimeError(f"Expected downstream impact was absent: {analysis.impact}")
        if not any(
            node.get("name") == "opaque_passthrough"
            for node in analysis.opaque.get("opaque", [])
        ):
            raise RuntimeError("ODS did not preserve the opaque source-wildcard model")

        opaque_analysis = await analyze_ods(
            config,
            focus=["opaque_passthrough"],
            changes=["base_customers.customer_name=modified"],
        )
        if not isinstance(opaque_analysis, ODSAnalysis):
            raise RuntimeError(f"ODS failed to report opaque analysis: {opaque_analysis}")
        if opaque_analysis.coverage != "unavailable":
            raise RuntimeError(
                f"Opaque focus was not reported unavailable: {opaque_analysis.coverage}"
            )
        if not opaque_analysis.reason or "columns are unknown" not in opaque_analysis.reason:
            raise RuntimeError(f"Opaque reason was not preserved: {opaque_analysis.reason}")

        mixed_analysis = await analyze_ods(
            config,
            focus=["customer_summary.normalized_name", "opaque_passthrough"],
            changes=["base_customers.customer_name=modified"],
        )
        if not isinstance(mixed_analysis, ODSAnalysis):
            raise RuntimeError(f"ODS failed to report mixed coverage: {mixed_analysis}")
        if mixed_analysis.coverage != "partial" or not mixed_analysis.reason:
            raise RuntimeError(
                f"Mixed analyzable/opaque focus was not reported partial: {mixed_analysis}"
            )

        missing_provider = await analyze_ods(
            ODSMCPConfig(
                command=str(fixture / "missing-ods.exe"),
                project_dir=fixture,
                target_dir=target,
                artifacts=artifacts,
            ),
            focus=["customer_summary.normalized_name"],
            changes=["base_customers.customer_name=modified"],
        )
        if not isinstance(missing_provider, ODSUnavailable):
            raise RuntimeError("A missing optional ODS provider was not reported unavailable")
        print(f"Official MCP SDK {artifacts} adapter contract: passed")


def main():
    parser = argparse.ArgumentParser(
        description="Compile and test the ODS adapter using the official MCP Python SDK."
    )
    parser.add_argument("--dbt", default="dbt", help="Path to the dbt CLI")
    parser.add_argument("--ods", default="ods", help="Path to the ODS CLI")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "ods-dbt-oss-2.0.8",
        help="dbt project fixture to compile",
    )
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    if not (fixture / "dbt_project.yml").is_file():
        parser.error(f"dbt fixture not found: {fixture}")
    asyncio.run(check_artifact_mode(args.dbt, args.ods, fixture, "json"))
    asyncio.run(check_artifact_mode(args.dbt, args.ods, fixture, "info-schema"))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f"ODS SDK adapter check failed: {error}", file=sys.stderr)
        sys.exit(1)
