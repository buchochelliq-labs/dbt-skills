"""Local stdio MCP bridge for the Unified Ontology Layer."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from mcp import MCPError
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from dbt_skills.ontology import (
    ClaimRecord,
    LocalOntologyStore,
    OntologyError,
    default_store_path,
)
from dbt_skills.ontology_sources import configured_provider
from dbt_skills.project import ProjectError, ProjectInfo, discover_project


_READ_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_CHANGE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_EXTERNAL_CHANGE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
_DESTRUCTIVE_TOOL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


def _records_with_sync_status(
    store: LocalOntologyStore,
    records: Sequence[ClaimRecord],
) -> list[dict[str, object]]:
    statuses = {item["source_id"]: item for item in store.sources()}
    serialized: list[dict[str, object]] = []
    for record in records:
        item = asdict(record)
        if record.source_kind == "provider":
            source_status = statuses.get(record.source_id)
            if source_status is not None:
                provenance = item["provenance"]
                provenance["local_sync_status"] = source_status["sync_status"]
                provenance["synced_at"] = source_status["synced_at"]
                provenance["source_enabled"] = source_status["enabled"]
                provenance["sync_scope"] = source_status["scope"]
        serialized.append(item)
    return serialized


def create_server(
    store: LocalOntologyStore,
    *,
    selected_project: ProjectInfo | None = None,
) -> MCPServer:
    server = MCPServer(
        name="dbt-skills-uol",
        title="dbt-skills Unified Ontology Layer",
        version="0.1.0",
        instructions=(
            "Read tools use only the configured local SQLite snapshot and overlay. "
            "They never contact providers. State-changing tools are separate and "
            "must not be auto-approved by the host. Sources must be configured and "
            "enabled before sync; provider-specific capabilities are not implied."
        ),
    )

    @server.tool(
        description="Return local UOL cache-read state and configured source sync status. Read-only; does not contact providers.",
        annotations=_READ_TOOL,
    )
    def uol_status() -> dict[str, object]:
        return {
            "cache_reads_enabled": store.cache_reads_enabled(),
            "sources": store.sources(),
            "cache_protection": {
                "encrypted_at_rest": True,
                "cipher": "SQLCipher",
                "key_storage": "native OS credential store",
                "filesystem_access_control": "validated",
                "warning": (
                    "The cache is readable by authorized processes running as the "
                    "current user while the OS credential store is available."
                ),
            },
        }

    @server.tool(
        description="Search the indexed local UOL cache and user overlay. Bounded to 200 claims; does not contact providers.",
        annotations=_READ_TOOL,
    )
    def uol_search(query: str, limit: int = 20) -> dict[str, object]:
        if not query.strip():
            raise MCPError(-32602, "query must not be empty")
        if limit < 1 or limit > 200:
            raise MCPError(-32602, "limit must be between 1 and 200")
        records = _records_with_sync_status(
            store,
            store.search(query, limit=limit),
        )
        return {
            "query": query,
            "cache_reads_enabled": store.cache_reads_enabled(),
            "claims": records,
        }

    @server.tool(
        description="Traverse bounded local UOL relationships from an entity ID. Maximum depth 4 and 500 claims; does not contact providers.",
        annotations=_READ_TOOL,
    )
    def uol_neighbors(
        entity_id: str,
        depth: int = 1,
        max_claims: int = 100,
    ) -> dict[str, object]:
        if not entity_id.strip():
            raise MCPError(-32602, "entity_id must not be empty")
        if depth < 1 or depth > 4:
            raise MCPError(-32602, "depth must be between 1 and 4")
        if max_claims < 1 or max_claims > 500:
            raise MCPError(-32602, "max_claims must be between 1 and 500")
        return {
            "entity_id": entity_id,
            "depth": depth,
            "claims": _records_with_sync_status(
                store,
                store.neighborhood(
                    entity_id,
                    depth=depth,
                    max_claims=max_claims,
                ),
            ),
        }

    @server.tool(
        description="Synchronize one already-configured and enabled source incrementally. State-changing and may access an external provider; requires per-call user approval. Use the separate full-refresh tool for snapshot-only providers.",
        annotations=_EXTERNAL_CHANGE_TOOL,
    )
    async def uol_sync_source(source_id: str, page_size: int = 500) -> dict[str, object]:
        try:
            provider = configured_provider(
                store,
                source_id,
                selected_project=selected_project,
            )
            if not provider.supports_incremental:
                raise ValueError(
                    f"Source {source_id} does not support incremental sync; "
                    "use uol_full_refresh_source"
                )
            return await store.sync_source(
                source_id,
                provider,
                full_refresh=False,
                page_size=page_size,
            )
        except (OntologyError, ProjectError, ValueError) as error:
            raise MCPError(-32000, str(error)) from error

    @server.tool(
        description="Replace one already-configured and enabled source snapshot with a full refresh. State-changing; requires per-call user approval.",
        annotations=_EXTERNAL_CHANGE_TOOL,
    )
    async def uol_full_refresh_source(
        source_id: str,
        page_size: int = 500,
    ) -> dict[str, object]:
        try:
            provider = configured_provider(
                store,
                source_id,
                selected_project=selected_project,
            )
            return await store.sync_source(
                source_id,
                provider,
                full_refresh=True,
                page_size=page_size,
            )
        except (OntologyError, ProjectError, ValueError) as error:
            raise MCPError(-32000, str(error)) from error

    @server.tool(
        description="Enable or pause synchronization for a configured local source. Does not change its saved scope or contact the provider. State-changing; requires per-call user approval.",
        annotations=_CHANGE_TOOL,
    )
    def uol_set_source_enabled(source_id: str, enabled: bool) -> dict[str, object]:
        try:
            store.set_source_enabled(source_id, enabled)
            return store.source_status(source_id)
        except OntologyError as error:
            raise MCPError(-32000, str(error)) from error

    @server.tool(
        description="Enable or disable reads from all synchronized provider-cache claims; local overlay claims remain readable. State-changing; requires per-call user approval.",
        annotations=_CHANGE_TOOL,
    )
    def uol_set_cache_reads_enabled(enabled: bool) -> dict[str, object]:
        store.set_cache_reads_enabled(enabled)
        return {"cache_reads_enabled": store.cache_reads_enabled()}

    @server.tool(
        description="Delete synchronized cache data for one configured source without deleting local overlay claims. Destructive; requires per-call user approval.",
        annotations=_DESTRUCTIVE_TOOL,
    )
    def uol_purge_source(source_id: str) -> dict[str, object]:
        try:
            store.purge_source_cache(source_id)
            return {"purged_source_cache": source_id}
        except OntologyError as error:
            raise MCPError(-32000, str(error)) from error

    @server.tool(
        description="Delete all synchronized provider-cache data without deleting local overlay claims. Destructive; requires per-call user approval.",
        annotations=_DESTRUCTIVE_TOOL,
    )
    def uol_purge_all_sources() -> dict[str, object]:
        store.purge_provider_cache()
        return {"purged": "all_provider_cache", "overlay_preserved": True}

    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dbt-skills-uol-mcp",
        description="Expose the local UOL through a stdio MCP server.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path (default: current user's application-data folder)",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Optional selected dbt project directory for source identity checks",
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    project = discover_project(args.project_dir) if args.project_dir else None
    store = LocalOntologyStore(args.db or default_store_path())
    server = create_server(store, selected_project=project)
    await server.run_stdio_async()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except (OSError, ValueError, RuntimeError) as error:
        print(f"dbt-skills-uol-mcp: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
