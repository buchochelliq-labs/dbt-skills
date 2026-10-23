import asyncio
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tests.cache_test_support import MemoryKeyStore
from dbt_skills.ods_mcp import ODSAnalysis, ODSMCPConfig, ODSUnavailable
from dbt_skills.ontology import LocalOntologyStore, ProviderContractError
from dbt_skills.ontology_cli import main as ontology_main
from dbt_skills.ontology_sources import (
    ManifestSnapshotProvider,
    ODSLineageProvider,
    ods_analysis_to_claims,
)
from dbt_skills.project import discover_project


class OntologySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name) / "analytics"
        self.root.mkdir()
        self.key_store = MemoryKeyStore()
        (self.root / "dbt_project.yml").write_text(
            "name: analytics_demo\nversion: '1.0'\n",
            encoding="utf-8",
        )
        target = self.root / "target"
        target.mkdir()
        self.manifest_path = target / "manifest.json"
        self._write_manifest("analytics_demo")
        self.project = discover_project(self.root)

    def _write_manifest(self, project_name):
        self.manifest_path.write_text(
            json.dumps(
                {
                    "metadata": {
                        "project_name": project_name,
                        "dbt_version": "2.0.8",
                        "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
                        "generated_at": "2026-10-22T12:00:00Z",
                        "invocation_id": "fixture-run",
                    },
                    "nodes": {
                        "model.analytics_demo.stg_orders": {
                            "name": "stg_orders",
                            "resource_type": "model",
                            "package_name": "analytics_demo",
                            "original_file_path": "models/stg_orders.sql",
                            "depends_on": {"nodes": ["source.analytics_demo.raw.orders"]},
                        },
                        "test.analytics_demo.not_null": {
                            "name": "not_null_stg_orders_id",
                            "resource_type": "test",
                            "depends_on": {"nodes": ["model.analytics_demo.stg_orders"]},
                        },
                    },
                    "sources": {
                        "source.analytics_demo.raw.orders": {
                            "name": "orders",
                            "resource_type": "source",
                            "source_name": "raw",
                            "depends_on": {"nodes": []},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_manifest_projects_resource_claims_and_distinct_resource_edges(self):
        provider = ManifestSnapshotProvider(self.root)
        page = asyncio.run(provider.fetch_page(cursor=None, page_size=100, full_refresh=True))

        resource = next(
            claim for claim in page.claims
            if claim.claim_id == "resource:model.analytics_demo.stg_orders"
        )
        dependency = next(
            claim for claim in page.claims
            if claim.claim_id
            == "depends:model.analytics_demo.stg_orders:source.analytics_demo.raw.orders"
        )
        self.assertEqual(resource.entity_type, "model")
        self.assertEqual(resource.source_version, "https://schemas.getdbt.com/dbt/manifest/v12.json")
        self.assertEqual(resource.evidence["manifest_generated_at"], "2026-10-22T12:00:00Z")
        self.assertEqual(dependency.predicate, "depends_on")
        self.assertEqual(dependency.entity_type, "resource_lineage")
        self.assertEqual(dependency.object_kind, "entity")
        self.assertEqual(dependency.object_value, "source.analytics_demo.raw.orders")
        self.assertFalse(any(claim.entity_type == "column_lineage" for claim in page.claims))
        self.assertTrue(page.done)

    def test_manifest_rejects_missing_or_mismatched_project_identity(self):
        self._write_manifest("different_project")
        provider = ManifestSnapshotProvider(self.root)
        with self.assertRaisesRegex(ProviderContractError, "does not match"):
            asyncio.run(provider.fetch_page(cursor=None, page_size=100, full_refresh=True))

        self._write_manifest("analytics_demo")
        document = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        del document["metadata"]["project_name"]
        self.manifest_path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ProviderContractError, "no project identity"):
            asyncio.run(provider.fetch_page(cursor=None, page_size=100, full_refresh=True))

    def test_explicit_manifest_bypasses_templated_target_and_preserves_path_evidence(self):
        (self.root / "dbt_project.yml").write_text(
            "name: analytics_demo\ntarget-path: \"{{ env_var('BUILD_DIR') }}\"\n",
            encoding="utf-8",
        )
        custom = self.root / "build" / "explicit.json"
        custom.parent.mkdir()
        custom.write_bytes(self.manifest_path.read_bytes())
        provider = ManifestSnapshotProvider(self.root, custom)
        page = asyncio.run(provider.fetch_page(cursor=None, page_size=100, full_refresh=True))
        self.assertEqual(page.claims[0].evidence["artifact"], str(custom.resolve()))

    def test_manifest_pagination_reuses_projection_and_rejects_changed_artifact(self):
        provider = ManifestSnapshotProvider(self.root)
        first = asyncio.run(
            provider.fetch_page(cursor=None, page_size=1, full_refresh=True)
        )
        self.assertIsNotNone(first.next_cursor)
        with patch(
            "dbt_skills.ontology_sources.json.loads",
            side_effect=AssertionError("manifest should not be parsed again"),
        ):
            second = asyncio.run(
                provider.fetch_page(
                    cursor=first.next_cursor,
                    page_size=1,
                    full_refresh=True,
                )
            )
        self.assertFalse(second.done)
        self._write_manifest("changed_project")
        with self.assertRaisesRegex(ProviderContractError, "changed during"):
            asyncio.run(
                provider.fetch_page(
                    cursor=second.next_cursor,
                    page_size=1,
                    full_refresh=True,
                )
            )

    def test_cli_registers_manifest_and_ods_sources_disabled_with_scopes(self):
        (self.root / "dbt_project.yml").write_text(
            "name: analytics_demo\ntarget-path: \"{{ env_var('BUILD_DIR') }}\"\n",
            encoding="utf-8",
        )
        database = Path(self.temp_dir.name) / "cli.sqlite3"
        with (
            patch(
                "dbt_skills.ontology_cli.LocalOntologyStore",
                side_effect=lambda path: LocalOntologyStore(
                    path,
                    key_store=self.key_store,
                ),
            ),
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(
                ontology_main(
                    [
                        "--db",
                        str(database),
                        "source",
                        "add-manifest",
                        "auto",
                        str(self.root),
                        "--manifest",
                        str(self.manifest_path),
                        "--include-entity-type",
                        "model",
                    ]
                ),
                0,
            )
            self.assertEqual(
                ontology_main(
                    [
                        "--db",
                        str(database),
                        "source",
                        "add-ods",
                        "auto",
                        "ods",
                        str(self.root),
                        str(self.root / "target"),
                        "--focus",
                        "stg_orders",
                        "--change",
                        "stg_orders.order_id=changed",
                    ]
                ),
                0,
            )
        store = LocalOntologyStore(database, key_store=self.key_store)
        sources = {item["provider_name"]: item for item in store.sources()}
        self.assertFalse(sources["dbt_manifest"]["enabled"])
        self.assertEqual(sources["dbt_manifest"]["scope"]["include_entity_types"], ["model"])
        self.assertFalse(sources["ods_column_lineage"]["enabled"])
        ods_config = store.source_config(sources["ods_column_lineage"]["source_id"])
        self.assertEqual(ods_config["options"]["focus"], ["stg_orders"])
        self.assertEqual(ods_config["options"]["changes"], ["stg_orders.order_id=changed"])

    def test_ods_projection_preserves_column_edge_direction_and_partial_diagnostics(self):
        analysis = ODSAnalysis(
            provider_version="0.0.2",
            protocol_version="2025-06-18",
            project_summary={
                "project_name": "analytics_demo",
                "dbt_version": "2.0.8",
                "target_dir": str(self.root / "target"),
                "artifacts": "manifest.json",
            },
            lineage={
                "column_edges": [
                    {
                        "from": {"model": "model.analytics_demo.stg_orders", "column": "order_id"},
                        "to": {"model": "model.analytics_demo.fct_orders", "column": "order_id"},
                        "kind": {"subtype": "transformation"},
                    }
                ]
            },
            impact={"impact": {"nodes": {}}},
            opaque={
                "opaque": [
                    {
                        "id": "model.analytics_demo.opaque_orders",
                        "name": "opaque_orders",
                        "reason": "dynamic SQL",
                        "diagnostics": ["columns are unknown"],
                    }
                ]
            },
            coverage="partial",
            reason="Some SQL is opaque.",
        )
        claims = ods_analysis_to_claims(analysis, self.project)

        edge = next(claim for claim in claims if claim.predicate == "column_depends_on")
        coverage = next(
            claim for claim in claims if claim.predicate == "column_lineage_coverage"
        )
        diagnostic = next(
            claim for claim in claims if claim.predicate == "column_lineage_unavailable"
        )
        self.assertEqual(edge.subject_id, "model.analytics_demo.fct_orders.order_id")
        self.assertEqual(edge.object_value, "model.analytics_demo.stg_orders.order_id")
        self.assertEqual(edge.entity_type, "column_lineage")
        self.assertEqual(edge.source_version, "0.0.2")
        self.assertEqual(edge.evidence["ods_edge"]["kind"]["subtype"], "transformation")
        self.assertEqual(coverage.object_value, "partial")
        self.assertEqual(coverage.evidence["analysis_reason"], "Some SQL is opaque.")
        self.assertIn("columns are unknown", diagnostic.object_value["diagnostics"])

    def test_ods_projection_rejects_project_mismatch_and_bad_edges(self):
        mismatch = ODSAnalysis(
            provider_version="0.0.2",
            protocol_version="2025-06-18",
            project_summary={"project_name": "other", "dbt_version": "2.0.8"},
            lineage={"column_edges": []},
            impact={"impact": {"nodes": {}}},
            opaque={"opaque": []},
            coverage="unavailable",
            reason="No lineage",
        )
        with self.assertRaisesRegex(ProviderContractError, "does not match"):
            ods_analysis_to_claims(mismatch, self.project)

        invalid = ODSAnalysis(
            provider_version="0.0.2",
            protocol_version="2025-06-18",
            project_summary={"project_name": "analytics_demo", "dbt_version": "2.0.8"},
            lineage={"column_edges": [{"from": "bad", "to": {}}]},
            impact={"impact": {"nodes": {}}},
            opaque={"opaque": []},
            coverage="partial",
            reason="Malformed",
        )
        with self.assertRaisesRegex(ProviderContractError, "from/to objects"):
            ods_analysis_to_claims(invalid, self.project)

    def test_unavailable_ods_is_explicit_and_does_not_publish_zero_lineage(self):
        provider = ODSLineageProvider(
            config=ODSMCPConfig(
                command="missing-ods",
                project_dir=self.root,
                target_dir=self.root / "target",
            ),
            project=self.project,
            focus=["stg_orders"],
            changes=["stg_orders.order_id=changed"],
        )
        with patch(
            "dbt_skills.ontology_sources.analyze_ods",
            return_value=ODSUnavailable("ODS MCP is not installed"),
        ):
            with self.assertRaisesRegex(ProviderContractError, "not installed"):
                asyncio.run(
                    provider.fetch_page(
                        cursor=None,
                        page_size=100,
                        full_refresh=True,
                    )
                )

        unavailable = ODSAnalysis(
            provider_version="0.0.2",
            protocol_version="2025-06-18",
            project_summary={"project_name": "analytics_demo", "dbt_version": "2.0.8"},
            lineage={"column_edges": []},
            impact={"impact": {"nodes": {}}},
            opaque={"opaque": []},
            coverage="unavailable",
            reason="No analysis for the requested focus.",
        )
        claims = ods_analysis_to_claims(unavailable, self.project)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].predicate, "column_lineage_coverage")
        self.assertEqual(claims[0].object_value, "unavailable")
        self.assertEqual(
            claims[0].evidence["analysis_reason"],
            "No analysis for the requested focus.",
        )


if __name__ == "__main__":
    unittest.main()
