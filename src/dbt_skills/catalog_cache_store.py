"""Optional encrypted bounded LRU storage, independent of the ontology store."""
from contextlib import contextmanager
import hashlib
import hmac
from pathlib import Path
import time

from .cache_security import OSKeyringKeyStore, open_encrypted_database, secure_path
from .catalog import CatalogError


class CatalogCacheStore:
    def __init__(self, path, *, max_objects, max_bytes, key_store=None):
        self.path = Path(path).resolve()
        self.max_objects, self.max_bytes = max_objects, max_bytes
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            secure_path(self.path.parent, directory=True)
            exists = self.path.exists()
            if exists:
                secure_path(self.path)
            self.key = (key_store or OSKeyringKeyStore()).get_or_create_key(self.path, create=not exists)
            if self.key is None:
                raise ValueError()
            with self.connection() as db:
                db.execute('CREATE TABLE IF NOT EXISTS catalog_claims (namespace TEXT, key TEXT, payload BLOB, size INTEGER, used REAL, PRIMARY KEY(namespace,key))')
            self.enforce_capacity()
            secure_path(self.path)
        except Exception:
            raise CatalogError('Cannot initialize protected catalog cache') from None

    @contextmanager
    def connection(self):
        db = open_encrypted_database(self.path, self.key)
        try:
            # Reuse encryption but avoid a long-lived growing WAL for this small cache.
            db.execute('PRAGMA journal_mode=DELETE')
            with db:
                yield db
        finally:
            db.close()

    def namespace(self, identity):
        return hmac.new(self.key, identity.encode(), hashlib.sha256).hexdigest()

    def get(self, namespace, key):
        with self.connection() as db:
            row = db.execute('SELECT payload FROM catalog_claims WHERE namespace=? AND key=? AND length(payload)<=1048576', (namespace, key)).fetchone()
            if row:
                db.execute('UPDATE catalog_claims SET used=? WHERE namespace=? AND key=?', (time.time(), namespace, key))
                return bytes(row[0])
        return None

    def touch(self, namespace, key):
        with self.connection() as db:
            db.execute('UPDATE catalog_claims SET used=? WHERE namespace=? AND key=?',
                       (time.time(), namespace, key))

    def enforce_capacity(self):
        removed = False
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            while True:
                count, size = db.execute('SELECT count(*),coalesce(sum(size),0) FROM catalog_claims').fetchone()
                if count <= self.max_objects and size <= self.max_bytes:
                    break
                db.execute('DELETE FROM catalog_claims WHERE rowid=(SELECT rowid FROM catalog_claims ORDER BY used,rowid LIMIT 1)')
                removed = True
        if removed:
            with self.connection() as db:
                db.execute('VACUUM')

    def put(self, namespace, key, payload):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM catalog_claims WHERE namespace=? AND key=?', (namespace, key))
            if len(payload) <= self.max_bytes:
                db.execute('INSERT INTO catalog_claims VALUES (?,?,?,?,?)', (namespace, key, payload, len(payload), time.time()))
            while True:
                count, size = db.execute('SELECT count(*),coalesce(sum(size),0) FROM catalog_claims').fetchone()
                if count <= self.max_objects and size <= self.max_bytes:
                    break
                db.execute('DELETE FROM catalog_claims WHERE rowid=(SELECT rowid FROM catalog_claims ORDER BY used,rowid LIMIT 1)')
        # Bound historical allocation too; max_bytes is the serialized-payload
        # budget, while SQLite pages/indexes add documented storage overhead.
        with self.connection() as db:
            db.execute('VACUUM')

    def prune(self, namespace, allowed):
        with self.connection() as db:
            keys = [r[0] for r in db.execute('SELECT key FROM catalog_claims WHERE namespace=?', (namespace,))]
            db.executemany('DELETE FROM catalog_claims WHERE namespace=? AND key=?',
                           [(namespace, key) for key in keys if key not in allowed])
