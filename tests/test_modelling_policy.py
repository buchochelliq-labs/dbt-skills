import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml
from jsonschema import Draft202012Validator

from dbt_skills.modelling_policy import PolicyError, load_document, resolve_policy_name, discover_policy_files


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "modelling.yml"
        self.policy = {
            "schema_version": 1, "kind": "policy",
            "tokens": {"source": "Which source?", "concept": "Which concept?"},
            "naming": [{"id": "staging", "target": "model_file", "template": "stg_{source}_{concept}.sql",
                        "scope": {"layer": "staging"}}],
            "modelling": [{"id": "core", "scope": {"layer": "core"}, "style": "relational", "normal_form": "4NF"}],
        }
        self.write(self.policy)

    def write(self, data):
        self.path.write_text(yaml.safe_dump(data), encoding="utf-8")

    def test_load_and_resolve_with_exact_provenance(self):
        result = load_document(self.path)
        self.assertEqual(result["document"]["modelling"][0]["normal_form"], "4NF")
        self.assertEqual(result["provenance"]["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        result = resolve_policy_name(self.path, "staging", {"source": "xyz"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["questions"][0]["token"], "concept")
        self.assertEqual(result["provenance"]["locator"], "/naming/0")
        result = resolve_policy_name(self.path, "staging", {"source": "xyz", "concept": "customer"})
        self.assertEqual(result["value"], "stg_xyz_customer.sql")

    def test_invalid_schema_and_cross_field_rules(self):
        for field, value in (("schema_version", 2), ("schema_version", True), ("extra", "secret")):
            with self.subTest(field=field):
                data = dict(self.policy, **{field: value})
                self.write(data)
                with self.assertRaises(PolicyError): load_document(self.path)
        self.policy["naming"].append(dict(self.policy["naming"][0]))
        self.write(self.policy)
        with self.assertRaises(PolicyError): load_document(self.path)

    def test_schema_is_valid_and_unknown_normal_forms_are_rejected(self):
        import dbt_skills.modelling_policy as module
        Draft202012Validator.check_schema(module._SCHEMA)
        self.policy["modelling"][0]["normal_form"] = "6ishNF"
        self.write(self.policy)
        with self.assertRaises(PolicyError): load_document(self.path)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "Requires POSIX FIFO")
    def test_fifo_is_rejected_without_blocking(self):
        self.path.unlink()
        os.mkfifo(self.path)
        result = subprocess.run([sys.executable, "-m", "dbt_skills.policy_cli", "validate", str(self.path)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)

    def test_discovery_does_not_follow_directory_links(self):
        outside = self.root / "elsewhere"
        outside.mkdir()
        (outside / "modelling.yml").write_text("not policy")
        scan = self.root / "scan"
        scan.mkdir()
        try:
            (scan / "linked").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertEqual(discover_policy_files(scan)["candidates"], [])

    def test_cli_render_and_discover(self):
        command = [sys.executable, "-m", "dbt_skills.policy_cli"]
        result = subprocess.run(command + ["render", str(self.path), "--rule", "staging", "--value", "source=xyz"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "needs_clarification")
        result = subprocess.run(command + ["discover", str(self.root)], capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["candidates"], ["modelling.yml"])

    def test_rejects_yaml_ambiguity_and_excessive_inputs_without_echo(self):
        for text in ("kind: policy\nkind: secret", "x: &x [*x]", "x: !!python/object:secret {}",
                     "[" * 40 + "]" * 40, "x: " + "x" * 1048576):
            self.path.write_text(text, encoding="utf-8")
            with self.assertRaises(PolicyError) as error: load_document(self.path)
            self.assertNotIn("secret", str(error.exception))

    def test_observations_and_decisions_are_not_policy(self):
        evidence = [{"document": "models/a.sql", "revision": "abc", "locator": "line:1"}]
        for kind, record in (
            ("observations", {"id": "o1", "statement": "Uses source prefix", "confidence": "low", "evidence": evidence}),
            ("decisions", {"id": "d1", "rule_id": "staging", "decision": "exception", "models": ["model.project.a"],
                           "rationale": "Legacy consumer", "approved_by": "maintainer", "approved_at": "2026-10-23T12:00:00Z", "evidence": evidence}),
        ):
            self.write({"schema_version": 1, "kind": kind, "records": [record]})
            self.assertEqual(load_document(self.path)["document"]["kind"], kind)
            with self.assertRaises(PolicyError): resolve_policy_name(self.path, "staging", {})

    def test_discovery_is_bounded_excludes_generated_files_and_asks(self):
        (self.root / "target").mkdir()
        (self.root / "target" / "modelling.yml").write_text("secret")
        result = discover_policy_files(self.root)
        self.assertEqual(result["candidates"], ["modelling.yml"])
        self.assertTrue(result["questions"])
        self.assertFalse(result["truncated"])
        self.assertTrue(discover_policy_files(self.root, max_entries=1)["truncated"])

    def test_cli_returns_json_and_nonzero_for_invalid_policy(self):
        command = [sys.executable, "-m", "dbt_skills.policy_cli", "validate", str(self.path)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "valid")
        self.path.write_text("secret: invalid", encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("secret", result.stderr)

    def test_constructor_errors_never_escape_cli(self):
        for document in ("x: !!int PRIVATE_SENTINEL", "x: !!float PRIVATE_SENTINEL", "x: " + "9" * 5000):
            self.path.write_text(document, encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "dbt_skills.policy_cli", "validate", str(self.path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("PRIVATE_SENTINEL", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(json.loads(result.stderr)["status"], "error")

    def test_approval_timestamp_validation_does_not_need_optional_checker(self):
        from unittest.mock import patch
        from dbt_skills import modelling_policy
        record = {"id": "d1", "rule_id": "rule", "decision": "exception", "models": ["model.p.x"],
                  "rationale": "Legacy", "approved_by": "maintainer", "approved_at": "invalid",
                  "evidence": [{"document": "decision.md", "revision": "abc", "locator": "1"}]}
        for timestamp in ("invalid", "2026-02-30T12:00:00Z", "2026-10-23T12:00:00", "2026-10-23", "2026-10-23T12:00:00+00:99"):
            record["approved_at"] = timestamp
            self.write({"schema_version": 1, "kind": "decisions", "records": [record]})
            with patch.object(modelling_policy._VALIDATOR, "format_checker", None):
                with self.assertRaises(PolicyError): load_document(self.path)
