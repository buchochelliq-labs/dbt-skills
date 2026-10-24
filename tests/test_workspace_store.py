import tempfile, unittest
from pathlib import Path
from dbt_skills.workspace_store import WorkspaceStore, WorkspaceConflict, WorkspaceError
from tests.cache_test_support import MemoryKeyStore


class WorkspaceTests(unittest.TestCase):
    def test_restart_encryption_conflict_and_reviewed_import(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "store.db"
            keys = MemoryKeyStore()
            s = WorkspaceStore(path, key_store=keys)
            doc = {
                "schema_version": 1,
                "records": [
                    {
                        "id": "design-1",
                        "kind": "design",
                        "title": "Customer design",
                        "content": "PRIVATE_METADATA_SENTINEL",
                        "references": [],
                        "evidence": [],
                        "approval": "reviewed",
                    }
                ],
            }
            s.save(doc, 0)
            self.assertNotIn(b"PRIVATE_METADATA_SENTINEL", path.read_bytes())
            reopened = WorkspaceStore(path, key_store=keys)
            self.assertEqual(reopened.read()["document"], doc)
            with self.assertRaises(WorkspaceConflict):
                reopened.save(doc, 0)
            preview = reopened.preview_import(s.export())
            self.assertEqual(preview["document"]["records"][0]["approval"], "draft")
            reopened.save(doc, 1)
            with self.assertRaises(WorkspaceConflict):
                reopened.apply_import(preview["preview_id"])
            p = reopened.preview_import(s.export())
            self.assertEqual(reopened.apply_import(p["preview_id"])["revision"], 3)
            self.assertEqual(len(reopened.history()), 4)

    def test_invalid_import_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as d:
            s = WorkspaceStore(Path(d) / "store.db", key_store=MemoryKeyStore())
            with self.assertRaises(WorkspaceError):
                s.preview_import({"schema_version": 99})
            with self.assertRaises(WorkspaceError):
                s.save({"schema_version": 1, "records": [{"rows": []}]}, 0)
            self.assertEqual(s.read()["revision"], 0)
