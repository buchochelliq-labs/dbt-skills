import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from tests.cache_test_support import MemoryKeyStore
from dbt_skills.ontology import (
    LocalOntologyStore,
    OntologyClaim,
    ProviderContractError,
    SourceDisabledError,
    SyncPage,
    SyncScope,
    claim_reference,
)


class MemoryProvider:
    provider_name = "memory"
    supports_incremental = True

    def __init__(self, claims, *, page_size=500, fail_cursor=None):
        self.claims = list(claims)
        self.page_size = page_size
        self.fail_cursor = fail_cursor
        self.failed = False
        self.deleted_claim_ids = []

    async def fetch_page(self, *, cursor, page_size, full_refresh):
        del full_refresh
        if self.fail_cursor is not None and cursor == self.fail_cursor and not self.failed:
            self.failed = True
            raise OSError("temporary provider outage")
        offset = int(cursor or "0")
        selected = self.claims[offset : offset + min(page_size, self.page_size)]
        next_offset = offset + len(selected)
        done = next_offset >= len(self.claims)
        return SyncPage(
            claims=selected,
            next_cursor=None if done else str(next_offset),
            done=done,
            deleted_claim_ids=self.deleted_claim_ids if done else (),
        )


def claim(
    claim_id,
    subject,
    predicate,
    value,
    *,
    kind="literal",
    namespace="finance",
    entity_type="measure",
    native_id=None,
    evidence=None,
):
    return OntologyClaim(
        claim_id=claim_id,
        subject_id=subject,
        predicate=predicate,
        object_value=value,
        object_kind=kind,
        native_id=native_id or claim_id,
        namespace=namespace,
        entity_type=entity_type,
        source_version="v1",
        observed_at="2026-10-22T00:00:00Z",
        evidence=evidence or {"record": claim_id},
    )


class LocalOntologyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Path(self.temp_dir.name) / "uol.sqlite3"
        self.store = LocalOntologyStore(self.database, key_store=MemoryKeyStore())

    def register(self, *, enabled=True, scope=None):
        self.store.register_source(
            "source-a",
            "memory",
            scope=scope,
            enabled=enabled,
        )

    def test_sync_is_disabled_until_user_enables_source_and_honors_scope(self):
        self.register(
            enabled=False,
            scope=SyncScope(
                include_namespaces=frozenset({"finance"}),
                exclude_record_ids=frozenset({"excluded"}),
            ),
        )
        provider = MemoryProvider(
            [
                claim("kept", "bookings", "definition", "Net bookings"),
                claim("excluded", "bookings", "definition", "Internal note"),
                claim(
                    "other-namespace",
                    "orders",
                    "definition",
                    "Orders",
                    namespace="operations",
                ),
            ],
            page_size=1,
        )
        with self.assertRaises(SourceDisabledError):
            asyncio.run(self.store.sync_source("source-a", provider))

        self.store.set_source_enabled("source-a", True)
        result = asyncio.run(
            self.store.sync_source("source-a", provider, page_size=1)
        )
        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["status"], "current")
        self.assertEqual(self.store.source_status("source-a")["claim_count"], 1)
        self.assertEqual(len(self.store.search("Net bookings")), 1)
        self.assertEqual(self.store.search("Internal note"), [])

    def test_failed_full_refresh_keeps_last_good_snapshot_and_can_resume(self):
        self.register()
        original = claim("old", "bookings", "definition", "Original bookings")
        asyncio.run(
            self.store.sync_source(
                "source-a", MemoryProvider([original]), full_refresh=True
            )
        )
        replacement = [
            claim("new-1", "bookings", "definition", "New bookings"),
            claim("new-2", "bookings", "formula", "Gross minus cancellations"),
        ]
        provider = MemoryProvider(replacement, page_size=1, fail_cursor="1")

        with self.assertRaisesRegex(OSError, "temporary provider outage"):
            asyncio.run(
                self.store.sync_source(
                    "source-a", provider, full_refresh=True, page_size=1
                )
            )
        status = self.store.source_status("source-a")
        self.assertEqual(status["sync_status"], "stale")
        self.assertIsNotNone(status["last_error"])
        self.assertEqual(len(self.store.search("Original bookings")), 1)
        self.assertEqual(self.store.search("New bookings"), [])

        resumed = asyncio.run(
            self.store.sync_source(
                "source-a", provider, full_refresh=True, page_size=1
            )
        )
        self.assertEqual(resumed["status"], "current")
        self.assertEqual(self.store.search("Original bookings"), [])
        self.assertEqual(len(self.store.search("New bookings")), 1)
        self.assertEqual(self.store.source_status("source-a")["claim_count"], 2)

    def test_incremental_updates_and_deletions_are_published_together(self):
        self.register()
        original = [
            claim("keep", "bookings", "definition", "Current bookings"),
            claim("remove", "bookings", "description", "Old wording"),
        ]
        provider = MemoryProvider(original, page_size=1)
        asyncio.run(
            self.store.sync_source("source-a", provider, page_size=1)
        )
        provider.claims = [
            claim("keep", "bookings", "definition", "Updated bookings")
        ]
        provider.deleted_claim_ids = ["remove"]
        result = asyncio.run(
            self.store.sync_source("source-a", provider, page_size=1)
        )
        self.assertEqual(result["mode"], "incremental")
        self.assertEqual(self.store.search("Current bookings"), [])
        self.assertEqual(self.store.search("Old wording"), [])
        self.assertEqual(len(self.store.search("Updated bookings")), 1)
        self.assertEqual(self.store.source_status("source-a")["claim_count"], 1)

    def test_incremental_scope_exclusion_removes_previously_cached_claim(self):
        self.register(
            scope=SyncScope(include_namespaces=frozenset({"finance"}))
        )
        provider = MemoryProvider(
            [claim("fact", "bookings", "definition", "Finance bookings")],
            page_size=1,
        )
        asyncio.run(self.store.sync_source("source-a", provider, page_size=1))
        provider.claims = [
            claim(
                "fact",
                "bookings",
                "definition",
                "Restricted operations bookings",
                namespace="operations",
            )
        ]

        result = asyncio.run(self.store.sync_source("source-a", provider, page_size=1))

        self.assertEqual(result["mode"], "incremental")
        self.assertEqual(self.store.source_status("source-a")["claim_count"], 0)
        self.assertEqual(self.store.search("Finance bookings"), [])
        self.assertEqual(self.store.search("Restricted operations bookings"), [])

    def test_reconfiguring_provider_discards_its_old_snapshot(self):
        self.register()
        asyncio.run(
            self.store.sync_source(
                "source-a",
                MemoryProvider([claim("fact", "bookings", "definition", "Old source")]),
            )
        )

        self.store.register_source(
            "source-a",
            "replacement",
            options={"endpoint": "local-fixture"},
            enabled=True,
        )

        self.assertEqual(self.store.source_status("source-a")["claim_count"], 0)
        self.assertEqual(self.store.source_status("source-a")["sync_status"], "unknown")
        self.assertEqual(self.store.search("Old source"), [])

    def test_overlay_link_provenance_and_provider_purge_are_separate(self):
        self.register()
        claims = [
            claim("term", "net_bookings", "definition", "Sales after adjustments"),
            claim(
                "column",
                "analytics.fact_orders.net",
                "business_term",
                "net_bookings",
            ),
        ]
        asyncio.run(
            self.store.sync_source("source-a", MemoryProvider(claims))
        )
        overlay = self.store.add_overlay_claim(
            claim(
                "local-note",
                "net_bookings",
                "owner_note",
                "Reviewed with finance",
                namespace="local",
                entity_type="note",
            ),
            author="analyst",
            rationale="Team decision",
        )
        self.assertEqual(overlay.source_kind, "local_overlay")
        self.assertFalse(overlay.authorship["provider_endorsement"])

        link = self.store.create_link(
            "source-a",
            "term",
            "same_as",
            "source-a",
            "column",
            evidence={"stable_identifier": "net_bookings"},
            author="analyst",
        )
        self.assertEqual(link.claim.predicate, "same_as")
        self.assertEqual(link.claim.evidence["link_review_status"], "user_reviewed")
        self.assertIn("stable_identifier", link.provenance["evidence"])
        linked_neighborhood = self.store.neighborhood(
            claim_reference("source-a", "term"), depth=2
        )
        linked_ids = {record.claim.claim_id for record in linked_neighborhood}
        self.assertTrue({"term", "column", link.claim.claim_id}.issubset(linked_ids))

        self.store.set_cache_reads_enabled(False)
        local_results = self.store.search("Reviewed with finance")
        self.assertTrue(all(record.source_kind == "local_overlay" for record in local_results))
        self.assertIsNone(self.store.get_claim("source-a", "term"))
        self.store.set_cache_reads_enabled(True)

        self.store.purge_provider_cache()
        self.assertEqual(self.store.source_status("source-a")["claim_count"], 0)
        self.assertEqual(len(self.store.search("Reviewed with finance")), 1)
        self.assertEqual(len(self.store.search("same_as")), 1)

    def test_reconfiguring_scope_discards_old_cache_but_not_overlay(self):
        self.register()
        asyncio.run(
            self.store.sync_source(
                "source-a",
                MemoryProvider([claim("fact", "bookings", "definition", "Bookings")]),
            )
        )
        local = self.store.add_overlay_claim(
            claim("note", "bookings", "note", "Local overlay", namespace="local"),
            author="analyst",
        )
        self.store.configure_source_scope(
            "source-a",
            SyncScope(include_namespaces=frozenset({"finance"})),
        )
        self.assertEqual(self.store.source_status("source-a")["sync_status"], "unknown")
        self.assertEqual(self.store.search("Original"), [])
        provider_matches = self.store.search("Bookings")
        self.assertTrue(
            all(record.source_kind == "local_overlay" for record in provider_matches)
        )
        self.assertIsNotNone(
            self.store.get_claim("_local_overlay", local.claim.claim_id)
        )

    def test_bad_provider_cursor_fails_explicitly_and_marks_source(self):
        class RepeatingCursorProvider:
            provider_name = "memory"
            supports_incremental = True

            async def fetch_page(self, *, cursor, page_size, full_refresh):
                del page_size, full_refresh
                return SyncPage(
                    claims=[],
                    next_cursor="same",
                    done=False,
                )

        self.register()
        with self.assertRaises(ProviderContractError):
            asyncio.run(
                self.store.sync_source(
                    "source-a", RepeatingCursorProvider(), full_refresh=True
                )
            )
        self.assertEqual(self.store.source_status("source-a")["sync_status"], "partial")

    def test_concurrent_sync_calls_for_one_source_are_serialized(self):
        class TrackingProvider(MemoryProvider):
            def __init__(self, claims):
                super().__init__(claims)
                self.active_fetches = 0
                self.maximum_active_fetches = 0

            async def fetch_page(self, *, cursor, page_size, full_refresh):
                self.active_fetches += 1
                self.maximum_active_fetches = max(
                    self.maximum_active_fetches, self.active_fetches
                )
                try:
                    await asyncio.sleep(0.01)
                    return await super().fetch_page(
                        cursor=cursor,
                        page_size=page_size,
                        full_refresh=full_refresh,
                    )
                finally:
                    self.active_fetches -= 1

        self.register()
        provider = TrackingProvider(
            [claim("fact", "bookings", "definition", "Current bookings")]
        )
        async def sync_twice():
            return await asyncio.gather(
                self.store.sync_source("source-a", provider),
                self.store.sync_source("source-a", provider),
            )

        first, second = asyncio.run(sync_twice())
        self.assertEqual(first["status"], "current")
        self.assertEqual(second["status"], "current")
        self.assertEqual(provider.maximum_active_fetches, 1)

    def test_json_snapshot_provider_and_page_contract(self):
        from dbt_skills.ontology import JSONSnapshotProvider

        path = Path(self.temp_dir.name) / "snapshot.json"
        path.write_text(
            json.dumps(
                {
                    "version": "fixture-v1",
                    "claims": [
                        {
                            "claim_id": f"claim-{index}",
                            "subject_id": "bookings",
                            "predicate": "definition",
                            "object_value": f"Bookings term {index}",
                        }
                        for index in range(3)
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.store.register_source(
            "source-a",
            "json_snapshot",
            enabled=True,
        )
        result = asyncio.run(
            self.store.sync_source(
                "source-a", JSONSnapshotProvider(path), page_size=2
            )
        )
        self.assertEqual(result["pages"], 2)
        self.assertEqual(self.store.source_status("source-a")["claim_count"], 3)
        record = self.store.get_claim("source-a", "claim-0")
        self.assertEqual(record.claim.source_version, "fixture-v1")
        self.assertTrue(record.provenance["sync_generation"])

    def test_json_snapshot_change_rejects_resume_and_pending_sync_can_restart(self):
        from dbt_skills.ontology import JSONSnapshotProvider

        path = Path(self.temp_dir.name) / "snapshot.json"

        def write_snapshot(version, claim_ids):
            path.write_text(
                json.dumps(
                    {
                        "version": version,
                        "claims": [
                            {
                                "claim_id": claim_id,
                                "subject_id": "bookings",
                                "predicate": "definition",
                                "object_value": f"Bookings term {claim_id}",
                            }
                            for claim_id in claim_ids
                        ],
                    }
                ),
                encoding="utf-8",
            )

        write_snapshot("v1", ["original"])
        self.store.register_source("source-a", "json_snapshot", enabled=True)
        asyncio.run(
            self.store.sync_source(
                "source-a", JSONSnapshotProvider(path), full_refresh=True
            )
        )
        write_snapshot("v2", ["replacement-1", "replacement-2"])

        class ChangingSnapshotProvider(JSONSnapshotProvider):
            async def fetch_page(self, *, cursor, page_size, full_refresh):
                page = await super().fetch_page(
                    cursor=cursor, page_size=page_size, full_refresh=full_refresh
                )
                if not page.done:
                    write_snapshot("v3", ["latest"])
                return page

        with self.assertRaisesRegex(ProviderContractError, "changed during"):
            asyncio.run(
                self.store.sync_source(
                    "source-a",
                    ChangingSnapshotProvider(path),
                    full_refresh=True,
                    page_size=1,
                )
            )
        self.assertEqual(len(self.store.search("Bookings term original")), 1)
        self.store.discard_pending_sync("source-a")
        self.assertEqual(self.store.source_status("source-a")["sync_status"], "stale")

        result = asyncio.run(
            self.store.sync_source(
                "source-a",
                JSONSnapshotProvider(path),
                full_refresh=True,
                page_size=1,
            )
        )
        self.assertEqual(result["status"], "current")
        self.assertEqual(self.store.search("Bookings term original"), [])
        self.assertEqual(len(self.store.search("Bookings term latest")), 1)


if __name__ == "__main__":
    unittest.main()
