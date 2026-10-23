import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.convention_discovery import infer_conventions
from dbt_skills.modelling_policy import _VALIDATOR
from dbt_skills.project import discover_project


class ConventionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "dbt_project.yml").write_text("name: example\n")
        self.project = discover_project(self.root)

    def snapshot(self, paths):
        return {"manifest": {"status": "available", "identity": "matched", "project_name": "example",
                             "freshness": "fresh", "sha256": "abc", "path": str(self.root / "target/manifest.json"),
                             "resources": [{"unique_id": f"model.example.m{i}", "resource_type": "model",
                                            "package_name": "example", "original_file_path": path}
                                           for i, path in enumerate(paths)]}}

    def test_proposes_custom_tokens_with_evidence_and_no_authority(self):
        result = infer_conventions(self.project, self.snapshot([
            "models/staging/stg-xyz-customer.sql", "models/staging/stg-erp-order.sql", "models/staging/stg-abc-account.sql"]))
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["proposed_policy"]["naming"][0]["template"], "models/staging/stg-{candidate_1_token_1}-{candidate_1_token_2}.sql")
        self.assertEqual(result["observations"]["records"][0]["evidence"][0]["revision"], "abc")
        self.assertTrue(_VALIDATOR.is_valid(result["observations"]))
        self.assertTrue(_VALIDATOR.is_valid(result["proposed_policy"]))
        self.assertTrue(any("mean" in q["question"] for q in result["questions"]))
        self.assertEqual(result["proposed_policy"]["modelling"], [])

    def test_counterexamples_and_ties(self):
        result = infer_conventions(self.project, self.snapshot([
            "models/stg_a.sql", "models/stg_b.sql", "models/legacy.sql"]))
        self.assertEqual(len(result["observations"]["records"][0]["counterexamples"]), 1)
        tied = infer_conventions(self.project, self.snapshot([
            "models/stg_a.sql", "models/stg_b.sql", "models/old-a.sql", "models/old-b.sql"]))
        self.assertFalse(tied["proposed_policy"]["naming"])
        self.assertTrue(any(q["kind"] == "conflict" for q in tied["questions"]))

    def test_missing_snapshot_returns_context_question(self):
        result = infer_conventions(self.project)
        self.assertEqual(result["status"], "needs_context")
        self.assertFalse(result["proposed_policy"]["naming"])

    def test_stale_snapshot_keeps_freshness_visible(self):
        snapshot = self.snapshot(["models/a_x.sql", "models/a_y.sql"])
        snapshot["manifest"]["freshness"] = "stale"
        result = infer_conventions(self.project, snapshot)
        self.assertEqual(result["source"]["freshness"], "stale")
        self.assertTrue(any(q["kind"] == "freshness" for q in result["questions"]))
        self.assertEqual(result["observations"]["records"][0]["confidence"], "low")

    def test_excludes_packages_unsafe_paths_and_source_text(self):
        snapshot = self.snapshot(["models/stg_a.sql", "models/stg_b.sql", "../outside_a.sql", "../outside_b.sql"])
        snapshot["manifest"]["resources"][0]["compiled_code"] = "RAW_DATA_SENTINEL"
        snapshot["manifest"]["resources"][1]["package_name"] = "dependency"
        result = infer_conventions(self.project, snapshot)
        self.assertFalse(result["proposed_policy"]["naming"])
        self.assertNotIn("RAW_DATA_SENTINEL", json.dumps(result))
        self.assertNotIn("outside", json.dumps(result))

    def test_deterministic_and_bounded(self):
        paths = [f"models/d{i}/stg_{j}.sql" for i in range(30) for j in range(12)]
        first = infer_conventions(self.project, self.snapshot(paths))
        snapshot = self.snapshot(paths)
        snapshot["manifest"]["resources"].reverse()
        self.assertEqual(first, infer_conventions(self.project, snapshot))
        self.assertTrue(first["truncated"])
        self.assertLessEqual(len(first["proposed_policy"]["naming"]), 16)
        self.assertLessEqual(len(first["questions"]), 64)
        self.assertLessEqual(len(first["observations"]["records"][0]["evidence"]), 8)

    def test_existing_authorities_are_referenced_without_reading_prose(self):
        (self.root / "modelling.yml").write_text("PRIVATE_POLICY_SENTINEL")
        (self.root / "decisions.md").write_text("PRIVATE_DOC_SENTINEL")
        result = infer_conventions(self.project, self.snapshot(["models/a_x.sql", "models/a_y.sql"]))
        self.assertIn("modelling.yml", result["existing_documents"]["candidates"])
        self.assertIn("decisions.md", result["existing_documents"]["references"])
        self.assertNotIn("PRIVATE_", json.dumps(result))

    def test_preserves_extension_and_emits_loadable_policy(self):
        from dbt_skills.modelling_policy import load_document
        result = infer_conventions(self.project, self.snapshot(["models/a_x.SQL", "models/a_y.SQL"]))
        self.assertTrue(result["proposed_policy"]["naming"][0]["template"].endswith(".SQL"))
        path = self.root / "draft.json"
        path.write_text(json.dumps(result["proposed_policy"]))
        self.assertEqual(load_document(path)["document"]["kind"], "policy")

    def test_cli_infer_uses_selected_target_and_excludes_sql(self):
        import subprocess
        import sys
        target = self.root / "build"
        target.mkdir()
        snapshot = self.snapshot(["models/stg_a.sql", "models/stg_b.sql"])
        nodes = {r["unique_id"]: {**r, "compiled_code": "PRIVATE_SQL_SENTINEL"} for r in snapshot["manifest"]["resources"]}
        (target / "manifest.json").write_text(json.dumps({
            "metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "project_name": "example"},
            "nodes": nodes, "sources": {}}))
        result = subprocess.run([sys.executable, "-m", "dbt_skills.policy_cli", "infer", str(self.root), "--target-path", "build"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["proposed_policy"]["naming"]), 1)
        self.assertNotIn("PRIVATE_SQL_SENTINEL", result.stdout)
