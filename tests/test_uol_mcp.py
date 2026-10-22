import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import Client, MCPError, StdioServerParameters

from dbt_skills.ontology import LocalOntologyStore, OntologyClaim
from dbt_skills.ontology_sources import DBT_MANIFEST_PROVIDER, manifest_source_id
from dbt_skills.project import discover_project


ROOT = Path(__file__).resolve().parents[1]


class UOLMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.project_dir = self.root / "project"
        self.project_dir.mkdir()
        (self.project_dir / "dbt_project.yml").write_text(
            "name: mcp_fixture\nversion: '1.0'\n",
            encoding="utf-8",
        )
        target = self.project_dir / "target"
        target.mkdir()
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "metadata": {
                        "project_name": "mcp_fixture",
                        "dbt_version": "1.9.0",
                        "dbt_schema_version": "manifest-v1",
                        "generated_at": "2026-10-22T12:00:00Z",
                    },
                    "nodes": {
                        "model.mcp_fixture.orders": {
                            "name": "orders",
                            "resource_type": "model",
                            "depends_on": {"nodes": ["source.mcp_fixture.raw.orders"]},
                        }
                    },
                    "sources": {
                        "source.mcp_fixture.raw.orders": {
                            "name": "orders",
                            "resource_type": "source",
                            "depends_on": {"nodes": []},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.database = self.root / "uol.sqlite3"

    async def _client(self):
        env = os.environ.copy()
        src = str(ROOT / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "dbt_skills.uol_mcp",
                "--db",
                str(self.database),
                "--project-dir",
                str(self.project_dir),
            ],
            cwd=ROOT,
            env=env,
        )
        client = Client(parameters, read_timeout_seconds=15)
        return client

    def test_stdio_tools_ingest_manifest_preserve_provenance_and_enforce_bounds(self):
        project = discover_project(self.project_dir)
        source_id = manifest_source_id(project)
        store = LocalOntologyStore(self.database)
        store.register_source(
            source_id,
            DBT_MANIFEST_PROVIDER,
            options={
                "project_dir": str(self.project_dir),
                "manifest_path": str(project.manifest_path),
            },
            enabled=True,
        )
        store.add_overlay_claim(
            OntologyClaim(
                claim_id="local-note",
                subject_id="analyst",
                predicate="note",
                object_value="analyst-only-context",
            ),
            author="fixture",
        )

        async def exercise():
            async with await self._client() as client:
                tool_list = await client.list_tools()
                tools = {tool.name: tool for tool in tool_list.tools}
                self.assertTrue(tools["uol_search"].annotations.read_only_hint)
                self.assertTrue(tools["uol_status"].annotations.read_only_hint)
                self.assertFalse(tools["uol_full_refresh_source"].annotations.read_only_hint)
                self.assertTrue(tools["uol_purge_all_sources"].annotations.destructive_hint)

                with self.assertRaisesRegex(MCPError, "does not support incremental sync"):
                    await client.call_tool(
                        "uol_sync_source",
                        {"source_id": source_id},
                    )
                result = await client.call_tool(
                    "uol_full_refresh_source",
                    {"source_id": source_id, "page_size": 2},
                )
                self.assertFalse(result.is_error, result.content)
                self.assertEqual(result.structured_content["status"], "current")

                searched = await client.call_tool(
                    "uol_search",
                    {"query": "orders", "limit": 20},
                )
                self.assertFalse(searched.is_error, searched.content)
                claims = searched.structured_content["claims"]
                self.assertTrue(claims)
                self.assertTrue(
                    any(claim["provenance"]["sync_generation"] for claim in claims)
                )
                self.assertTrue(
                    all(claim["provenance"]["local_sync_status"] == "current" for claim in claims)
                )

                with self.assertRaisesRegex(MCPError, "depth must be between 1 and 4"):
                    await client.call_tool(
                        "uol_neighbors",
                        {"entity_id": "model.mcp_fixture.orders", "depth": 5},
                    )

                manifest_path = project.manifest_path
                manifest_path.write_text("{invalid", encoding="utf-8")
                with self.assertRaisesRegex(MCPError, "invalid JSON"):
                    await client.call_tool(
                        "uol_full_refresh_source",
                        {"source_id": source_id},
                    )
                stale_status = await client.call_tool("uol_status", {})
                stale_source = next(
                    source
                    for source in stale_status.structured_content["sources"]
                    if source["source_id"] == source_id
                )
                self.assertEqual(stale_source["sync_status"], "stale")
                last_good = await client.call_tool(
                    "uol_search",
                    {"query": "orders"},
                )
                self.assertTrue(last_good.structured_content["claims"])
                self.assertEqual(
                    last_good.structured_content["claims"][0]["provenance"]["local_sync_status"],
                    "stale",
                )

                disabled = await client.call_tool(
                    "uol_set_cache_reads_enabled",
                    {"enabled": False},
                )
                self.assertFalse(disabled.is_error, disabled.content)
                hidden = await client.call_tool(
                    "uol_search",
                    {"query": "orders"},
                )
                self.assertFalse(hidden.is_error, hidden.content)
                self.assertEqual(hidden.structured_content["claims"], [])
                overlay = await client.call_tool(
                    "uol_search",
                    {"query": "analyst-only-context"},
                )
                self.assertEqual(
                    overlay.structured_content["claims"][0]["source_kind"],
                    "local_overlay",
                )
                status = await client.call_tool("uol_status", {})
                self.assertFalse(status.structured_content["cache_protection"]["encrypted_at_rest"])

                purged = await client.call_tool(
                    "uol_purge_source",
                    {"source_id": source_id},
                )
                self.assertFalse(purged.is_error, purged.content)
                self.assertTrue(store.source_status(source_id)["claim_count"] == 0)

        asyncio.run(exercise())

    def test_disabled_source_is_not_synced(self):
        project = discover_project(self.project_dir)
        source_id = manifest_source_id(project)
        store = LocalOntologyStore(self.database)
        store.register_source(
            source_id,
            DBT_MANIFEST_PROVIDER,
            options={
                "project_dir": str(self.project_dir),
                "manifest_path": str(project.manifest_path),
            },
            enabled=False,
        )

        async def exercise():
            async with await self._client() as client:
                with self.assertRaisesRegex(MCPError, "disabled"):
                    await client.call_tool(
                        "uol_full_refresh_source",
                        {"source_id": source_id},
                    )

                enabled = await client.call_tool(
                    "uol_set_source_enabled",
                    {"source_id": source_id, "enabled": True},
                )
                self.assertFalse(enabled.is_error, enabled.content)
                refreshed = await client.call_tool(
                    "uol_full_refresh_source",
                    {"source_id": source_id},
                )
                self.assertFalse(refreshed.is_error, refreshed.content)

        asyncio.run(exercise())

    def test_manifest_source_must_match_selected_project(self):
        project = discover_project(self.project_dir)
        source_id = manifest_source_id(project)
        store = LocalOntologyStore(self.database)
        store.register_source(
            source_id,
            DBT_MANIFEST_PROVIDER,
            options={
                "project_dir": str(self.project_dir),
                "manifest_path": str(project.manifest_path),
            },
            enabled=True,
        )
        other_project = self.root / "other"
        other_project.mkdir()
        (other_project / "dbt_project.yml").write_text(
            "name: other_project\nversion: '1.0'\n",
            encoding="utf-8",
        )

        async def exercise():
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-m",
                    "dbt_skills.uol_mcp",
                    "--db",
                    str(self.database),
                    "--project-dir",
                    str(other_project),
                ],
                cwd=ROOT,
                env=env,
            )
            async with Client(parameters, read_timeout_seconds=15) as client:
                with self.assertRaisesRegex(MCPError, "does not match the selected dbt project"):
                    await client.call_tool(
                        "uol_full_refresh_source",
                        {"source_id": source_id},
                    )

        asyncio.run(exercise())

if __name__ == "__main__":
    unittest.main()
