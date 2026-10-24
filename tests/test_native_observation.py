import json
import os
import unittest
from unittest.mock import patch
from dbt_skills.native_observation import (
    adapter_from_config,
    ObservationError,
    MAX_BYTES,
)
from dbt_skills.native_publication import (
    validate_proposal,
    verify_readback,
)


class NativeObservationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"NATIVE_TEST_TOKEN": "local-test-only"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = {
            "workspace_url": "https://trusted.example",
            "trusted_hosts": ["trusted.example"],
            "token_env": "NATIVE_TEST_TOKEN",
            "targets": [{"kind": "genie", "id": "space1", "origin_id": "origin1"}],
        }
        self.native = {
            "space_id": "space1",
            "serialized_space": json.dumps(
                {"instructions": {"text": "old"}, "examples": ["keep"]}
            ),
            "etag": "actual-etag",
            "warehouse_id": "preserve",
        }
        self.calls = []
        self.status = 200
        self.auth = {"write": True, "audience": ["analysts"]}
        self.revision = "r1"
        self.adapter = adapter_from_config(
            self.config,
            origin_revision_reader=lambda _: self.revision,
            authorization_reader=lambda _: self.auth,
            transport=self.transport,
        )

    def transport(self, url, headers):
        self.calls.append(url)
        self.assertEqual("Bearer local-test-only", headers["Authorization"])
        return self.status, json.dumps(self.native).encode()

    def proposal(self):
        target = {"kind": "genie", "id": "space1"}
        return {
            "schema_version": 1,
            "target": target,
            "origin": {"id": "origin1", "revision": "r1"},
            "base_fingerprint": self.adapter.read_target(target)["fingerprint"],
            "changes": [
                {
                    "id": "c1",
                    "path": ["serialized_space", "instructions", "text"],
                    "value": "new",
                }
            ],
            "selected_change_ids": ["c1"],
            "intended_audience": ["analysts"],
        }

    def test_native_read_validation_preserves_configuration_and_etag(self):
        p = self.proposal()
        result = validate_proposal(p, self.adapter)
        self.assertEqual("review_ready", result["status"])
        self.assertEqual(
            ["keep"], result["desired_document"]["serialized_space"]["examples"]
        )
        self.assertEqual("preserve", result["desired_document"]["warehouse_id"])
        self.assertEqual("unknown", result["saved_acknowledgement"])
        self.assertTrue(
            all(
                url
                == "https://trusted.example/api/2.0/genie/spaces/space1?include_serialized_space=true"
                for url in self.calls
            )
        )
        del self.native["etag"]
        self.assertEqual("export_only", validate_proposal(p, self.adapter)["status"])

    def test_permission_identity_origin_and_audience_fail_closed(self):
        p = self.proposal()
        for code in (401, 403, 302):
            self.status = code
            self.assertEqual("blocked", validate_proposal(p, self.adapter)["status"])
        self.status = 200
        self.native["space_id"] = "other"
        self.assertEqual("blocked", validate_proposal(p, self.adapter)["status"])
        self.native["space_id"] = "space1"
        self.auth = {"write": True}
        self.assertEqual("blocked", validate_proposal(p, self.adapter)["status"])
        self.auth = {"write": True, "audience": ["analysts"]}
        self.revision = "r2"
        self.assertEqual("conflict", validate_proposal(p, self.adapter)["status"])

    def test_actual_readback_and_drift(self):
        p = self.proposal()
        self.assertEqual(
            "readback_mismatch", verify_readback(p, self.adapter)["status"]
        )
        self.native["serialized_space"] = json.dumps(
            {"instructions": {"text": "new"}, "examples": ["keep"]}
        )
        self.assertEqual("conflict", validate_proposal(p, self.adapter)["status"])
        result = verify_readback(p, self.adapter)
        self.assertEqual("readback_verified", result["status"])
        self.assertEqual("unknown", result["saved_acknowledgement"])

    def test_config_and_request_allowlist(self):
        for url in (
            "http://trusted.example",
            "https://evil.example",
            "https://trusted.example/path",
            "https://x@trusted.example",
        ):
            config = dict(self.config, workspace_url=url)
            with self.assertRaises(ObservationError):
                adapter_from_config(config, origin_revision_reader=lambda _: "r1")
        with self.assertRaises(ObservationError):
            self.adapter.read_target({"kind": "genie", "id": "other"})
        self.assertEqual([], self.calls)

    def test_uc_metadata_only_and_no_conditional_token(self):
        config = dict(
            self.config,
            targets=[{"kind": "unity_catalog", "id": "c.s.t", "origin_id": "origin1"}],
        )

        def transport(url, headers):
            if url.endswith("/tags"):
                body = {
                    "tag_assignments": [
                        {
                            "entity_type": "tables",
                            "entity_name": "c.s.t",
                            "tag_key": "owner",
                            "tag_value": "team",
                        }
                    ]
                }
            else:
                body = {
                    "full_name": "c.s.t",
                    "comment": "old",
                    "storage_location": "never exposed",
                    "columns": [],
                }
            return 200, json.dumps(body).encode()

        adapter = adapter_from_config(
            config, origin_revision_reader=lambda _: "r1", transport=transport
        )
        observed = adapter.read_target({"kind": "unity_catalog", "id": "c.s.t"})
        self.assertEqual(
            {"comment": "old", "tags": {"owner": "team"}}, observed["document"]
        )
        self.assertIsNone(observed["revision_token"])
        self.assertFalse(observed["permissions"]["write"])
        self.assertIsNone(observed["audience"])

    def test_bounded_response(self):
        self.adapter.transport = lambda *_: (200, b" " * (MAX_BYTES + 1))
        with self.assertRaises(ObservationError):
            self.adapter.read_target({"kind": "genie", "id": "space1"})
