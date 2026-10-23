import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.policy_comparison import compare_model_names, match_template
from dbt_skills.project import discover_project


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "dbt_project.yml").write_text("name: example\n")
        self.project = discover_project(self.root)
        self.policy = self.root / "modelling.json"
        self.rules = [{"id": "staging", "target": "model_file", "template": "models/stg_{source}_{concept}.sql", "scope": {"directory": "models"}}]
        self.write()

    def write(self):
        self.policy.write_text(json.dumps({"schema_version": 1, "kind": "policy", "tokens": {"source": "Source?", "concept": "Concept?"}, "naming": self.rules, "modelling": []}))

    def snapshot(self, path="models/stg_xyz_customer.sql"):
        return {"manifest": {"status": "available", "identity": "matched", "project_name": "example", "freshness": "fresh", "sha256": "abc", "path": "manifest.json",
                             "resources": [{"unique_id": "model.example.customer", "package_name": "example", "resource_type": "model", "original_file_path": path}]}}

    def test_dynamic_repeated_and_fixed_tokens(self):
        self.assertEqual(match_template("a_{x}_{x}.sql", "a_foo_foo.sql", {}), "matches")
        self.assertEqual(match_template("a_{x}_{x}.sql", "a_foo_bar.sql", {}), "mismatch")
        self.assertEqual(match_template("{x}.sql", "abc.sql", {"x": "xyz"}), "mismatch")
        self.assertEqual(match_template("{x}.sql", "a/b.sql", {}), "mismatch")
        self.assertEqual(match_template("{x}{y}.sql", "abc.sql", {}), "matches")

    def test_matches_mismatches_and_provenance(self):
        good = compare_model_names(self.project, self.policy, self.snapshot())
        self.assertEqual(good["models"][0]["status"], "matches")
        self.assertEqual(good["models"][0]["rule_provenance"]["locator"], "/naming/0")
        self.assertEqual(good["source"]["sha256"], "abc")
        bad = compare_model_names(self.project, self.policy, self.snapshot("models/legacy.sql"))
        self.assertEqual(bad["models"][0]["status"], "mismatch")
        self.assertTrue(bad["models"][0]["question"])

    def test_basename_rule_does_not_require_a_directory_prefix(self):
        self.rules[0]["template"] = "stg_{source}_{concept}.sql"
        self.write()
        result = compare_model_names(self.project, self.policy, self.snapshot())
        self.assertEqual(result["models"][0]["status"], "matches")

    def test_preserves_manifest_source_and_observation_times(self):
        snapshot = self.snapshot()
        snapshot["manifest"].update(generated_at="2026-10-23T10:00:00Z", observed_at="2026-10-23T11:00:00Z", age_seconds=3600)
        result = compare_model_names(self.project, self.policy, snapshot)
        self.assertEqual(result["source"]["generated_at"], "2026-10-23T10:00:00Z")
        self.assertEqual(result["source"]["observed_at"], "2026-10-23T11:00:00Z")

    def test_unknown_scope_and_explicit_context(self):
        self.rules[0]["scope"] = {"layer": "staging"}
        self.write()
        self.assertEqual(compare_model_names(self.project, self.policy, self.snapshot())["models"][0]["status"], "needs_scope")
        result = compare_model_names(self.project, self.policy, self.snapshot(), model_id="model.example.customer", context={"layer": "staging"})
        self.assertEqual(result["models"][0]["status"], "matches")

    def test_overlapping_rules_have_no_hidden_precedence(self):
        self.rules.append({**self.rules[0], "id": "other"})
        self.write()
        self.assertEqual(compare_model_names(self.project, self.policy, self.snapshot())["models"][0]["status"], "rule_conflict")

    def test_unavailable_and_stale_do_not_claim_compliance(self):
        self.assertEqual(compare_model_names(self.project, self.policy)["status"], "needs_context")
        snapshot = self.snapshot()
        snapshot["manifest"]["freshness"] = "stale"
        result = compare_model_names(self.project, self.policy, snapshot)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("refresh", result["questions"][0].lower())

    def test_search_exhaustion_is_not_mismatch(self):
        self.assertEqual(match_template("{a}{b}{c}{d}z", "a" * 100, {}, max_states=10), "indeterminate")

    def test_unknown_model_and_no_silent_context_override(self):
        from dbt_skills.modelling_policy import PolicyError
        result = compare_model_names(self.project, self.policy, self.snapshot(), model_id="missing")
        self.assertEqual(result["status"], "needs_context")
        with self.assertRaises(PolicyError): compare_model_names(self.project, self.policy, self.snapshot(), context={"layer": "staging"})
        with self.assertRaises(PolicyError): compare_model_names(self.project, self.policy, self.snapshot(), model_id="model.example.customer", context={"directory": "wrong"})

    def test_model_limit_is_explicit_and_order_deterministic(self):
        snapshot = self.snapshot()
        source = snapshot["manifest"]["resources"][0]
        snapshot["manifest"]["resources"] = [{**source, "unique_id": f"model.example.m{i:03}"} for i in range(210)]
        first = compare_model_names(self.project, self.policy, snapshot)
        snapshot["manifest"]["resources"].reverse()
        self.assertEqual(first, compare_model_names(self.project, self.policy, snapshot))
        self.assertTrue(first["truncated"])
        self.assertEqual(len(first["models"]), 200)

    def test_cli_comparison_and_sanitized_context_errors(self):
        import subprocess
        import sys
        target = self.root / "target"
        target.mkdir()
        resource = self.snapshot()["manifest"]["resources"][0]
        (target / "manifest.json").write_text(json.dumps({"metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "project_name": "example"},
            "nodes": {resource["unique_id"]: {**resource, "compiled_code": "RAW_VALUE_SENTINEL"}}, "sources": {}}))
        command = [sys.executable, "-m", "dbt_skills.policy_cli", "compare", str(self.root), "--policy", str(self.policy)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["models"][0]["status"], "matches")
        self.assertNotIn("RAW_VALUE_SENTINEL", result.stdout)
        result = subprocess.run(command + ["--context", "layer=PRIVATE_SENTINEL"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("PRIVATE_SENTINEL", result.stderr)

    def test_missing_paths_and_unchecked_targets_are_explicit(self):
        self.rules[0]["target"] = "model_id"
        self.write()
        result = compare_model_names(self.project, self.policy, self.snapshot())
        self.assertEqual(result["models"][0]["status"], "uncovered")
        self.assertEqual(result["unchecked_targets"], ["model_id"])
        result = compare_model_names(self.project, self.policy, self.snapshot(None))
        self.assertEqual(result["models"][0]["status"], "not_evaluated")
