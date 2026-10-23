import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from dbt_skills.decision_proposals import prepare_decision
from dbt_skills.modelling_policy import PolicyError, validate_document
from dbt_skills.project import discover_project


class DecisionProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "dbt_project.yml").write_text("name: example\n")
        self.project = discover_project(self.root)
        self.policy = self.root / "modelling.json"
        self.document = {"schema_version": 1, "kind": "policy", "tokens": {"concept": "Concept?"},
                         "naming": [{"id": "staging", "target": "model_file", "template": "stg_{concept}.sql", "scope": {"layer": "staging"}}], "modelling": []}
        self.policy.write_text(json.dumps(self.document))
        self.snapshot = {"manifest": {"status": "available", "identity": "matched", "project_name": "example",
                                      "sha256": "abc", "path": "manifest.json", "freshness": "fresh",
                                      "observed_at": "2026-10-23T10:00:00Z", "generated_at": "2026-10-23T09:00:00Z",
                                      "resources": [{"unique_id": "model.example.customer", "resource_type": "model",
                                                     "package_name": "example", "original_file_path": "models/legacy_customer.sql",
                                                     "compiled_code": "PRIVATE_SQL_SENTINEL"}]}}

    def propose(self, **kwargs):
        return prepare_decision(self.project, self.policy, "staging", "model.example.customer", "Legacy consumer depends on this name", snapshot=self.snapshot, **kwargs)

    def test_default_is_pending_single_model_exception_and_no_writes(self):
        before = self.policy.read_bytes()
        result = self.propose()
        record = result["proposal_document"]["records"][0]
        self.assertEqual(record["decision"], "exception")
        self.assertEqual(record["models"], ["model.example.customer"])
        self.assertEqual(result["status"], "pending_review")
        self.assertNotIn("approved_by", record)
        self.assertNotIn("approved_at", record)
        self.assertFalse(result["policy_patch"])
        validate_document(result["proposal_document"])
        self.assertEqual(before, self.policy.read_bytes())
        self.assertNotIn("PRIVATE_SQL_SENTINEL", json.dumps(result))
        self.assertEqual(result["source"]["observed_at"], "2026-10-23T10:00:00Z")

    def test_standard_change_is_explicit_preserves_scope_and_has_guarded_patch(self):
        result = self.propose(decision="standard_change", template="legacy_{concept}.sql")
        self.assertEqual(result["proposal_document"]["records"][0]["models"], [])
        self.assertEqual(result["proposed_policy"]["naming"][0]["scope"], {"layer": "staging"})
        self.assertEqual(result["policy_patch"][0], {"op": "test", "path": "/naming/0/template", "value": "stg_{concept}.sql"})
        self.assertEqual(result["policy_patch"][1]["value"], "legacy_{concept}.sql")
        self.assertTrue(result["policy_base"]["sha256"])
        validate_document(result["proposed_policy"])

    def test_invalid_or_ambiguous_requests_fail(self):
        for kwargs in ({"decision": "standard_change"}, {"template": "other.sql"},
                       {"decision": "standard_change", "template": "{undeclared}.sql"},
                       {"decision": "standard_change", "template": "../{concept}.sql"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PolicyError): self.propose(**kwargs)
        self.snapshot["manifest"]["resources"] = []
        with self.assertRaises(PolicyError): self.propose()

    def test_existing_proposals_preserved_and_duplicates_rejected(self):
        first = self.propose()
        path = self.root / "proposals.json"
        path.write_text(json.dumps(first["proposal_document"]))
        before = path.read_bytes()
        with self.assertRaises(PolicyError): self.propose(proposals_path=path)
        second = self.propose(proposals_path=path, decision="standard_change", template="legacy_{concept}.sql")
        self.assertEqual(second["proposal_document"]["records"][0], first["proposal_document"]["records"][0])
        self.assertEqual(second["proposals_base"]["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(path.read_bytes(), before)

    def test_proposal_cannot_masquerade_as_approved_decision(self):
        document = self.propose()["proposal_document"]
        document["records"][0]["approved_by"] = "agent"
        with self.assertRaises(PolicyError): validate_document(document)
        document = self.propose()["proposal_document"]
        document["kind"] = "decisions"
        with self.assertRaises(PolicyError): validate_document(document)

    def test_cli_proposes_without_writing(self):
        import subprocess
        import sys
        target = self.root / "target"
        target.mkdir()
        model = self.snapshot["manifest"]["resources"][0]
        (target / "manifest.json").write_text(json.dumps({"metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "project_name": "example"},
            "nodes": {model["unique_id"]: model}, "sources": {}}))
        before = sorted(str(p) for p in self.root.rglob("*"))
        command = [sys.executable, "-m", "dbt_skills.policy_cli", "propose", str(self.root), "--policy", str(self.policy),
                   "--rule", "staging", "--model", "model.example.customer", "--rationale", "Legacy consumer"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pending_review")
        self.assertNotIn("PRIVATE_SQL_SENTINEL", result.stdout)
        self.assertEqual(sorted(str(p) for p in self.root.rglob("*")), before)

    def test_hashes_guard_reviewed_inputs_and_patch_preserves_other_rules(self):
        result = self.propose(decision="standard_change", template="legacy_{concept}.sql")
        proposed = json.loads(self.policy.read_text())
        self.assertEqual(proposed["naming"][0]["template"], result["policy_patch"][0]["value"])
        proposed["naming"][0]["template"] = result["policy_patch"][1]["value"]
        self.assertEqual(proposed, result["proposed_policy"])
        self.assertEqual(result["proposal_document"]["records"][0]["evidence"][1]["generated_at"], "2026-10-23T09:00:00Z")

    def test_append_cannot_produce_an_unloadable_oversized_document(self):
        self.document["naming"][0]["scope"] = {f"k{i}": "x" * 1100 for i in range(256)}
        self.policy.write_text(json.dumps(self.document))
        path = self.root / "proposals.json"
        for index in range(3):
            result = prepare_decision(self.project, self.policy, "staging", "model.example.customer", str(index),
                                      snapshot=self.snapshot, proposals_path=path if path.exists() else None)
            path.write_text(json.dumps(result["proposal_document"], indent=2))
        with self.assertRaises(PolicyError):
            prepare_decision(self.project, self.policy, "staging", "model.example.customer", "fourth", snapshot=self.snapshot, proposals_path=path)

    def test_in_memory_validation_enforces_yaml_node_budget(self):
        record = {"id": "x", "statement": "x", "confidence": "low",
                  "evidence": [{"document": "x", "revision": "x", "locator": "x"} for _ in range(60)]}
        document = {"schema_version": 1, "kind": "observations", "records": [{**record, "id": str(i)} for i in range(50)]}
        with self.assertRaises(PolicyError): validate_document(document)
