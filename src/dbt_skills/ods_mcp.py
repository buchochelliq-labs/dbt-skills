import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mcp import Client, MCPError, StdioServerParameters
from mcp.types import TextContent


JsonObject = dict[str, object]
ArtifactMode = Literal["auto", "json", "info-schema"]
Coverage = Literal["complete", "partial", "unavailable"]


@dataclass(frozen=True, slots=True)
class ODSMCPConfig:
    command: str
    project_dir: Path
    target_dir: Path
    artifacts: ArtifactMode = "auto"
    expected_version: str = "0.0.2"
    read_timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class ODSUnavailable:
    reason: str
    provider_version: str | None = None


@dataclass(frozen=True, slots=True)
class ODSAnalysis:
    provider_version: str
    protocol_version: str
    project_summary: JsonObject
    lineage: JsonObject
    impact: JsonObject
    opaque: JsonObject
    coverage: Coverage
    reason: str | None


ODSResult = ODSAnalysis | ODSUnavailable


class ODSContractError(RuntimeError):
    pass


def _as_object(value: object, label: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise ODSContractError(f"ODS returned an invalid {label} object")
    return dict(value)


def _tool_error(result) -> str:
    details = [block.text for block in result.content if isinstance(block, TextContent)]
    return "; ".join(details) or "ODS returned a tool error without details"


async def _call_object(client: Client, name: str, arguments: JsonObject) -> JsonObject:
    result = await client.call_tool(name, arguments)
    if result.is_error:
        raise ODSContractError(f"ODS tool {name} failed: {_tool_error(result)}")
    return _as_object(result.structured_content, f"{name} result")


def _same_path(actual: object, expected: Path) -> bool:
    if not isinstance(actual, str):
        return False
    return os.path.normcase(str(Path(actual).resolve())) == os.path.normcase(
        str(expected.resolve())
    )


def _focus_models(focus: Sequence[str]) -> set[str]:
    return {item.split(".", 1)[0] for item in focus}


def _node_model(node: Mapping[str, object], model: str) -> bool:
    name = node.get("name")
    unique_id = node.get("id")
    return name == model or (
        isinstance(unique_id, str) and unique_id.endswith(f".{model}")
    )


def _diagnostics(nodes: Sequence[object]) -> list[str]:
    messages = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        reason = node.get("reason")
        if isinstance(reason, str) and reason:
            messages.append(reason)
        diagnostics = node.get("diagnostics", [])
        if isinstance(diagnostics, list):
            messages.extend(item for item in diagnostics if isinstance(item, str))
    return messages


def _coverage(
    focus: Sequence[str],
    lineage: Mapping[str, object],
    impact: Mapping[str, object],
    opaque: Mapping[str, object],
) -> tuple[Coverage, str | None]:
    models = _focus_models(focus)
    nodes_value = lineage.get("nodes")
    opaque_value = opaque.get("opaque")
    impact_value = impact.get("impact")
    if (
        not isinstance(nodes_value, list)
        or not isinstance(opaque_value, list)
        or not isinstance(impact_value, Mapping)
    ):
        raise ODSContractError("ODS returned an incompatible lineage or impact result")

    lineage_nodes = [node for node in nodes_value if isinstance(node, Mapping)]
    opaque_nodes = [node for node in opaque_value if isinstance(node, Mapping)]
    focused_nodes = [
        node
        for node in lineage_nodes
        if any(_node_model(node, model) for model in models)
    ]
    found_models = {
        model
        for model in models
        if any(_node_model(node, model) for node in focused_nodes)
    }
    missing_models = models - found_models
    if not focused_nodes:
        return (
            "unavailable",
            "ODS returned no lineage node for the requested focus; the reason is unknown.",
        )

    opaque_ids = {
        node.get("id")
        for node in opaque_nodes
        if isinstance(node.get("id"), str)
    }
    focused_opaque = [
        node
        for node in focused_nodes
        if node.get("opaque") is True or node.get("id") in opaque_ids
    ]
    if len(focused_opaque) == len(focused_nodes) and not missing_models:
        focused_opaque_ids = {
            node.get("id")
            for node in focused_opaque
            if isinstance(node.get("id"), str)
        }
        opaque_details = [
            node
            for node in opaque_nodes
            if node.get("id") in focused_opaque_ids
        ]
        reasons = _diagnostics([*focused_opaque, *opaque_details])
        reason = "; ".join(reasons) or "ODS reports opaque lineage; the reason is unknown."
        return "unavailable", reason

    impacted_nodes = impact_value.get("nodes", {})
    if not isinstance(impacted_nodes, Mapping):
        raise ODSContractError("ODS returned an incompatible impact.nodes object")
    relevant_ids = {
        node.get("id")
        for node in lineage_nodes
        if isinstance(node.get("id"), str)
    } | set(impacted_nodes)
    relevant_opaque = [
        node
        for node in opaque_nodes
        if node.get("id") in relevant_ids
    ]
    if missing_models or focused_opaque or relevant_opaque:
        reasons = _diagnostics([*focused_opaque, *relevant_opaque])
        if missing_models:
            reasons.append(
                f"ODS returned no analysis for: {', '.join(sorted(missing_models))}."
            )
        reason = "; ".join(reasons) or "Some requested lineage is unavailable; the reason is unknown."
        return "partial", reason

    return "complete", None


async def analyze_ods(
    config: ODSMCPConfig,
    *,
    focus: Sequence[str],
    changes: Sequence[str],
) -> ODSResult:
    if not focus or any(not isinstance(item, str) or not item.strip() for item in focus):
        raise ValueError("focus must contain at least one non-empty model or column")
    if not changes or any(
        not isinstance(item, str) or not item.strip() for item in changes
    ):
        raise ValueError("changes must contain at least one non-empty column change")
    if config.read_timeout_seconds <= 0:
        raise ValueError("read_timeout_seconds must be positive")

    project_dir = config.project_dir.resolve()
    target_dir = config.target_dir.resolve()
    if not project_dir.is_dir():
        return ODSUnavailable(f"dbt project directory is unavailable: {project_dir}")
    if not target_dir.is_dir():
        return ODSUnavailable(f"dbt target directory is unavailable: {target_dir}")

    parameters = StdioServerParameters(
        command=config.command,
        args=[
            "mcp",
            "--project-dir",
            str(project_dir),
            "--target-dir",
            str(target_dir),
            "--artifacts",
            config.artifacts,
            "--log-level",
            "off",
        ],
        cwd=project_dir,
    )
    provider_version = None
    try:
        async with Client(
            parameters,
            read_timeout_seconds=config.read_timeout_seconds,
        ) as client:
            server_info = client.server_info
            provider_version = server_info.version if server_info else None
            protocol_version = client.protocol_version
            if not server_info or server_info.name != "ods":
                return ODSUnavailable("The MCP server did not identify as ODS", provider_version)
            if provider_version != config.expected_version:
                return ODSUnavailable(
                    f"ODS {provider_version or 'unknown'} is unsupported; "
                    f"expected {config.expected_version}.",
                    provider_version,
                )
            if not protocol_version:
                return ODSUnavailable("ODS did not negotiate an MCP protocol version", provider_version)

            tools = (await client.list_tools()).tools
            tools_by_name = {tool.name: tool for tool in tools}
            required = {
                "ods_project_summary",
                "ods_lineage",
                "ods_impact",
                "ods_list_opaque",
            }
            missing_tools = required - tools_by_name.keys()
            if missing_tools:
                return ODSUnavailable(
                    f"ODS MCP is missing required tools: {', '.join(sorted(missing_tools))}.",
                    provider_version,
                )
            lineage_schema = tools_by_name["ods_lineage"].input_schema
            impact_schema = tools_by_name["ods_impact"].input_schema
            lineage_required = (
                lineage_schema.get("required")
                if isinstance(lineage_schema, Mapping)
                else None
            )
            impact_properties = (
                impact_schema.get("properties")
                if isinstance(impact_schema, Mapping)
                else None
            )
            if not isinstance(lineage_required, list) or "focus" not in lineage_required:
                return ODSUnavailable("ODS ods_lineage input schema is incompatible", provider_version)
            if not isinstance(impact_properties, Mapping) or "columns" not in impact_properties:
                return ODSUnavailable("ODS ods_impact input schema is incompatible", provider_version)

            summary = await _call_object(client, "ods_project_summary", {})
            if not _same_path(summary.get("target_dir"), target_dir):
                return ODSUnavailable(
                    "ODS analyzed a different target directory; lineage is unavailable.",
                    provider_version,
                )
            if not isinstance(summary.get("dbt_version"), str):
                return ODSUnavailable(
                    "ODS did not report the dbt project version; lineage is unavailable.",
                    provider_version,
                )

            lineage = await _call_object(
                client, "ods_lineage", {"focus": list(focus)}
            )
            impact = await _call_object(
                client, "ods_impact", {"columns": list(changes)}
            )
            opaque = await _call_object(client, "ods_list_opaque", {})
            coverage, reason = _coverage(focus, lineage, impact, opaque)
            return ODSAnalysis(
                provider_version=provider_version,
                protocol_version=protocol_version,
                project_summary=summary,
                lineage=lineage,
                impact=impact,
                opaque=opaque,
                coverage=coverage,
                reason=reason,
            )
    except (MCPError, OSError, RuntimeError, TimeoutError) as error:
        return ODSUnavailable(
            f"ODS MCP connection or contract failed: {error}",
            provider_version,
        )
