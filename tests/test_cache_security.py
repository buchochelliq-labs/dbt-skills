import base64
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import keyring

from tests.cache_test_support import MemoryKeyStore
from dbt_skills.cache_security import (
    CacheProtectionError,
    OSKeyringKeyStore,
    migrate_plaintext_cache,
    open_encrypted_database,
    secure_path,
)
from dbt_skills.ontology import LocalOntologyStore


class CacheSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_cache_pages_are_encrypted_and_standard_sqlite_cannot_read_them(self):
        database = self.root / "cache.sqlite3"
        keys = MemoryKeyStore()
        store = LocalOntologyStore(database, key_store=keys)
        store.register_source("example", "fixture")

        with database.open("rb") as cache_file:
            self.assertNotEqual(cache_file.read(16), b"SQLite format 3\x00")

        with closing(sqlite3.connect(database)) as plain_connection:
            with self.assertRaises(sqlite3.DatabaseError):
                plain_connection.execute("SELECT * FROM sources").fetchall()

        with store._connect() as connection:
            self.assertEqual(
                connection.execute("SELECT source_id FROM sources").fetchone()[0],
                "example",
            )

    def test_wal_pages_are_encrypted_and_temporary_storage_is_memory_only(self):
        database = self.root / "wal-cache.sqlite3"
        keys = MemoryKeyStore()
        store = LocalOntologyStore(database, key_store=keys)
        with store._connect() as connection:
            self.assertEqual(connection.execute("PRAGMA temp_store").fetchone()[0], 2)
            connection.execute("PRAGMA wal_autocheckpoint = 0")
            connection.execute("CREATE TABLE private_values (value TEXT)")
            connection.execute(
                "INSERT INTO private_values VALUES ('wal-secret-identifier')"
            )
            connection.commit()
            wal_path = Path(f"{database}-wal")
            self.assertTrue(wal_path.is_file())
            secure_path(wal_path)
            self.assertNotIn(b"wal-secret-identifier", wal_path.read_bytes())

    def test_existing_plaintext_cache_is_not_opened_implicitly(self):
        database = self.root / "plain.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE secrets (value TEXT)")
            connection.execute("INSERT INTO secrets VALUES ('do not expose')")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(CacheProtectionError, "explicit 'protect-cache' migration"):
            LocalOntologyStore(database, key_store=MemoryKeyStore())

        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM secrets").fetchone()[0],
                "do not expose",
            )

    def test_plaintext_migration_verifies_encrypted_database_and_recovery_copy(self):
        database = self.root / "legacy.sqlite3"
        backup = self.root / "legacy.encrypted-backup"
        keys = MemoryKeyStore()
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("CREATE TABLE facts (name TEXT, value TEXT)")
            connection.execute(
                "INSERT INTO facts VALUES (?, ?)",
                ("definition", "confidential business meaning"),
            )
            connection.commit()
        finally:
            connection.close()

        result = migrate_plaintext_cache(
            database,
            key_store=keys,
            backup_path=backup,
        )
        self.assertEqual(result, backup.resolve())
        for path in (database, backup):
            with path.open("rb") as cache_file:
                self.assertNotEqual(cache_file.read(16), b"SQLite format 3\x00")
        with closing(sqlite3.connect(database)) as plain_connection:
            with self.assertRaises(sqlite3.DatabaseError):
                plain_connection.execute("SELECT * FROM facts").fetchall()

        store = LocalOntologyStore(database, key_store=keys)
        with store._connect() as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM facts").fetchone()[0],
                "confidential business meaning",
            )
        with self.assertRaises(CacheProtectionError):
            migrate_plaintext_cache(database, key_store=keys)

    def test_migration_failure_preserves_plaintext_source(self):
        database = self.root / "damaged.sqlite3"
        database.write_bytes(b"SQLite format 3\x00corrupt")
        with self.assertRaises(CacheProtectionError):
            migrate_plaintext_cache(database, key_store=MemoryKeyStore())
        self.assertEqual(database.read_bytes(), b"SQLite format 3\x00corrupt")

    def test_native_keyring_rejects_non_os_backends(self):
        import types

        unsupported = type(
            "PlaintextKeyring",
            (),
            {"__module__": "keyrings.alt.file"},
        )()
        with patch.object(keyring, "get_keyring", return_value=unsupported):
            with self.assertRaisesRegex(CacheProtectionError, "plaintext fallback is disabled"):
                OSKeyringKeyStore()

    def test_keyring_stores_a_random_32_byte_key_without_exposing_path(self):
        import types

        backend = type(
            "WinVaultKeyring",
            (),
            {"__module__": "keyring.backends.Windows"},
        )()
        saved = {}
        with (
            patch.object(keyring, "get_keyring", return_value=backend),
            patch.object(
                keyring,
                "get_password",
                side_effect=lambda service, user: saved.get((service, user)),
            ),
            patch.object(
                keyring,
                "set_password",
                side_effect=lambda service, user, value: saved.__setitem__(
                    (service, user), value
                ),
            ),
        ):
            provider = OSKeyringKeyStore()
            path = self.root / "private-name.sqlite3"
            first = provider.get_or_create_key(path, create=True)
            second = provider.get_or_create_key(path, create=False)

        self.assertEqual(len(first), 32)
        self.assertEqual(first, second)
        self.assertNotIn(str(path), repr(saved))
        stored = next(iter(saved.values()))
        self.assertEqual(len(base64.b64decode(stored)), 32)

    def test_cache_directory_and_file_permissions_are_restricted(self):
        directory = self.root / "private"
        directory.mkdir()
        file_path = directory / "cache"
        file_path.write_text("data", encoding="utf-8")
        secure_path(directory, directory=True)
        secure_path(file_path)

        if os.name != "nt":
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(file_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
