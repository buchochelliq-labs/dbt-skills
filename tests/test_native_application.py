"""Real-mode application commands against an injected, HTTP-shaped native reader."""

import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
from dbt_skills.application_commands import execute
from dbt_skills.application_store import validate_state, ApplicationStore
from dbt_skills.application_api import OntologyApplication
from tests.cache_test_support import MemoryKeyStore
from dbt_skills.native_observation import adapter_from_config
from dbt_skills.workspace_store import WorkspaceError


class NativeApplicationTests(unittest.TestCase):
    def setUp(self):
        self.s = json.loads(
            (
                Path(__file__).parents[1] / "examples/uol-workspace/fixture.json"
            ).read_text()
        )
        self.s["proposals"] = []
        self.s["deliveries"] = []
        self.target = next(t for t in self.s["targets"] if t["id"] == "customers")
        self.origin = next(
            k for k in self.s["knowledge"] if k["id"] == "active-customer"
        )
        self.comment = "Observed native comment"
        self.audience = ["All analysts"]
        self.calls = []
        self.env = patch.dict("os.environ", {"TEST_NATIVE_TOKEN": "local-only"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.adapter = adapter_from_config(
            {
                "workspace_url": "https://native.example",
                "trusted_hosts": ["native.example"],
                "token_env": "TEST_NATIVE_TOKEN",
                "targets": [
                    {
                        "kind": "unity_catalog",
                        "id": self.target["name"],
                        "origin_id": self.origin["originId"],
                    }
                ],
            },
            origin_revision_reader=lambda _: str(self.origin["version"]),
            authorization_reader=lambda _: {"write": True, "audience": self.audience},
            transport=self.transport,
        )

    def transport(self, url, headers):
        self.calls.append(url)
        body = (
            {
                "tag_assignments": [
                    {
                        "entity_name": self.target["name"],
                        "entity_type": "tables",
                        "tag_key": "keep",
                        "tag_value": "untouched",
                    }
                ]
            }
            if url.endswith("/tags")
            else {"full_name": self.target["name"], "comment": self.comment}
        )
        return 200, json.dumps(body).encode()

    def command(self, name, payload):
        result = execute(self.s, name, payload, native_adapter=self.adapter)
        validate_state(self.s)
        return result

    def propose(self):
        self.command("target.refresh", {"id": "customers"})
        return self.command(
            "proposal.create",
            {
                "proposal": {
                    "originId": self.origin["id"],
                    "targetId": "customers",
                    "field": "description",
                    "after": "Proposed native comment",
                    "reason": "Reviewed meaning",
                }
            },
        )

    def test_refresh_pins_proposal_and_preflight_preserves_tags(self):
        p = self.propose()
        base = p["nativeBaseFingerprint"]
        result = self.command("proposal.check", {"id": p["id"]})
        self.assertEqual("export_only", result["status"])
        self.assertEqual(
            {"comment": "Proposed native comment", "tags": {"keep": "untouched"}},
            result["desired_document"],
        )
        self.assertEqual([], self.s["deliveries"])
        self.comment = "Changed independently"
        self.command("target.refresh", {"id": "customers"})
        self.assertEqual(base, p["nativeBaseFingerprint"])
        self.assertEqual(
            "conflict", self.command("proposal.check", {"id": p["id"]})["status"]
        )

    def test_fresh_readback_never_claims_delivery_or_acknowledgement(self):
        p = self.propose()
        self.assertEqual(
            "readback_mismatch",
            self.command("proposal.reconcile", {"id": p["id"]})["status"],
        )
        self.comment = "Proposed native comment"
        result = self.command("proposal.reconcile", {"id": p["id"]})
        self.assertEqual("readback_verified", result["status"])
        self.assertEqual("unknown", result["saved_acknowledgement"])
        self.assertEqual("Draft", p["state"])
        self.assertEqual([], self.s["deliveries"])
        self.audience = None
        self.assertEqual(
            "blocked", self.command("proposal.reconcile", {"id": p["id"]})["status"]
        )

    def test_unobserved_proposal_and_missing_adapter_block(self):
        with self.assertRaises(WorkspaceError):
            self.command(
                "proposal.create",
                {
                    "proposal": {
                        "originId": self.origin["id"],
                        "targetId": "customers",
                        "field": "description",
                        "after": "new",
                        "reason": "reason",
                    }
                },
            )
        with self.assertRaises(WorkspaceError):
            execute(self.s, "target.refresh", {"id": "customers"})

    def test_encrypted_application_roundtrip_and_import_clears_native_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            keys = MemoryKeyStore()
            path = Path(directory) / "app.db"
            store = ApplicationStore(path, key_store=keys, initial_state=self.s)
            app = OntologyApplication(store, native_adapter=self.adapter)
            snapshot = app.command(
                "target.refresh", {"id": "customers"}, expected_revision=0
            )
            self.assertEqual(
                "authenticated_native_get", snapshot["result"]["provenance"]["source"]
            )
            snapshot = app.command(
                "proposal.create",
                {
                    "proposal": {
                        "originId": self.origin["id"],
                        "targetId": "customers",
                        "field": "description",
                        "after": "Proposed native comment",
                        "reason": "Reviewed meaning",
                    }
                },
                expected_revision=1,
            )
            pid = snapshot["result"]["id"]
            snapshot = app.command("proposal.check", {"id": pid}, expected_revision=2)
            self.assertEqual("export_only", snapshot["result"]["status"])
            reopened = ApplicationStore(path, key_store=keys)
            p = next(p for p in reopened.read()["state"]["proposals"] if p["id"] == pid)
            self.assertTrue(p["nativeBaseFingerprint"])
            self.assertEqual("export_only", p["nativeResult"]["status"])
            preview = reopened.preview_import(reopened.export())
            self.assertNotIn(
                "nativeResult",
                next(p for p in preview["state"]["proposals"] if p["id"] == pid),
            )
            self.assertNotIn(
                "nativeObservation",
                next(t for t in preview["state"]["targets"] if t["id"] == "customers"),
            )
