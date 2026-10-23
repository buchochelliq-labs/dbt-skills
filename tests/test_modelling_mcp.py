import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mcp import Client, MCPError, StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]


class ModellingMCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "dbt_project.yml").write_text("name: fixture\n")
        self.target = self.root / "build"
        self.target.mkdir()
        self.manifest = self.target / "manifest.json"
        self.manifest.write_text(json.dumps({"metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "project_name": "fixture"},
            "nodes": {"model.fixture.customer": {"resource_type": "model", "package_name": "fixture",
                       "original_file_path": "models/legacy_customer.sql", "compiled_code": "RAW_DATA_SENTINEL"}}, "sources": {}}))
        self.policy = self.root / "modelling.json"
        self.policy.write_text(json.dumps({"schema_version": 1, "kind": "policy", "tokens": {"concept": "Which concept?"},
            "naming": [{"id": "staging", "target": "model_file", "template": "stg_{concept}.sql", "scope": {"directory": "models"}}],
            "modelling": [{"id": "design", "style": "relational", "normal_form": "4NF"}]}))
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(ROOT / "src")

    def client(self, with_policy=True, mode="auto"):
        args = ["-m", "dbt_skills.modelling_mcp", "--project-dir", str(self.root), "--target-path", "build"]
        if with_policy:
            args += ["--policy", str(self.policy)]
        return Client(StdioServerParameters(command=sys.executable, args=args, env=self.env, cwd=ROOT), read_timeout_seconds=20, mode=mode)

    def test_real_stdio_workflow_and_snapshot_refresh(self):
        async def exercise():
            async with self.client() as client:
                listed = await client.list_tools()
                tools = {t.name: t for t in listed.tools}
                self.assertEqual(set(tools), {"modelling_context", "modelling_refresh", "modelling_rules", "modelling_infer", "modelling_render", "modelling_compare", "modelling_propose"})
                self.assertTrue(all(t.annotations.read_only_hint for t in tools.values()))
                self.assertTrue(all(not t.annotations.destructive_hint for t in tools.values()))
                context = (await client.call_tool("modelling_context", {})).structured_content
                self.assertEqual(context["project_root"], str(self.root))
                self.assertEqual(context["source"]["path"], str(self.manifest))
                key = context["context_id"]
                rules = (await client.call_tool("modelling_rules", {"context_id": key})).structured_content
                self.assertEqual(rules["rules"][0]["id"], "staging")
                missing = (await client.call_tool("modelling_render", {"context_id": key, "rule_id": "staging", "values": {}})).structured_content
                self.assertEqual(missing["status"], "needs_clarification")
                rendered = (await client.call_tool("modelling_render", {"context_id": key, "rule_id": "staging", "values": {"concept": "customer"}})).structured_content
                self.assertEqual(rendered["value"], "stg_customer.sql")
                before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
                comparison = (await client.call_tool("modelling_compare", {"context_id": key, "model_id": "model.fixture.customer"})).structured_content
                self.assertEqual(comparison["models"][0]["status"], "mismatch")
                proposal = (await client.call_tool("modelling_propose", {"context_id": key, "rule_id": "staging", "model_id": "model.fixture.customer", "rationale": "Legacy consumer"})).structured_content
                self.assertEqual(proposal["status"], "pending_review")
                self.assertEqual(proposal["proposal_document"]["records"][0]["models"], ["model.fixture.customer"])
                self.assertNotIn("RAW_DATA_SENTINEL", json.dumps([context, rules, comparison, proposal]))
                self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
                old_hash = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
                self.manifest.write_text("{}")
                (self.root / "modelling.yml").write_text("{}")
                inferred = (await client.call_tool("modelling_infer", {"context_id": key})).structured_content
                self.assertEqual(inferred["source"]["sha256"], old_hash)
                self.assertEqual(inferred["source"]["observed_at"], context["source"]["observed_at"])
                self.assertNotIn("modelling.yml", json.dumps(inferred["existing_documents"]))
                refreshed = (await client.call_tool("modelling_refresh", {})).structured_content
                self.assertNotEqual(refreshed["context_id"], key)
                new_inference = (await client.call_tool("modelling_infer", {"context_id": refreshed["context_id"]})).structured_content
                self.assertIn("modelling.yml", json.dumps(new_inference["existing_documents"]))
                with self.assertRaises(MCPError):
                    await client.call_tool("modelling_compare", {"context_id": key})
        asyncio.run(exercise())

    def test_policy_change_and_unconfigured_policy_fail_closed(self):
        async def exercise():
            async with self.client() as client:
                key = (await client.call_tool("modelling_context", {})).structured_content["context_id"]
                document = json.loads(self.policy.read_text())
                document["naming"][0]["template"] = "changed_{concept}.sql"
                self.policy.write_text(json.dumps(document))
                with self.assertRaises(MCPError):
                    await client.call_tool("modelling_render", {"context_id": key, "rule_id": "staging", "values": {"concept": "customer"}})
                with self.assertRaises(MCPError):
                    await client.call_tool("modelling_rules", {"context_id": key, "limit": 51})
            async with self.client(with_policy=False) as client:
                key = (await client.call_tool("modelling_context", {})).structured_content["context_id"]
                with self.assertRaises(MCPError):
                    await client.call_tool("modelling_compare", {"context_id": key})
        asyncio.run(exercise())

    def test_startup_error_is_sanitized(self):
        self.policy.write_text("x: !!int PRIVATE_SENTINEL")
        result = subprocess.run([sys.executable, "-m", "dbt_skills.modelling_mcp", "--project-dir", str(self.root), "--policy", str(self.policy)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("PRIVATE_SENTINEL", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_legacy_handshake_and_modelling_rules(self):
        async def exercise():
            async with self.client(mode="legacy") as client:
                self.assertEqual(len((await client.list_tools()).tools), 7)
                key = (await client.call_tool("modelling_context", {})).structured_content["context_id"]
                rules = (await client.call_tool("modelling_rules", {"context_id": key, "section": "modelling"})).structured_content
                self.assertEqual(rules["rules"][0]["normal_form"], "4NF")
                self.policy.write_text("invalid: [")
                with self.assertRaises(MCPError):
                    await client.call_tool("modelling_refresh", {})
                self.assertEqual((await client.call_tool("modelling_context", {})).structured_content["context_id"], key)
        asyncio.run(exercise())

    def test_configuration_examples_launch_real_server(self):
        async def exercise():
            for filename, root_key in [("mcp.portable.json", "mcpServers"), ("mcp.local.json", "servers")]:
                config = json.loads((ROOT / "examples" / "vscode" / filename).read_text())[root_key]["dbt-modelling"]
                args = [s.replace("/absolute/path/to/dbt-project", str(self.root)).replace("modelling.yml", self.policy.name) for s in config["args"]]
                args += ["--target-path", "build"]
                env = {k: v.replace("/absolute/path/to/dbt-skills", str(ROOT)) for k, v in config["env"].items()}
                async with Client(StdioServerParameters(command=sys.executable, args=args, env=env), read_timeout_seconds=20) as client:
                    context = (await client.call_tool("modelling_context", {})).structured_content
                    self.assertEqual(context["project_name"], "fixture")
                    self.assertIsNotNone(context["policy"])
        asyncio.run(exercise())
