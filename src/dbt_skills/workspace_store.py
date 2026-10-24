"""Encrypted authored workspace revisions; independent of expiring provider caches."""

from contextlib import contextmanager
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import secrets
from threading import RLock
from jsonschema import Draft202012Validator
from .cache_security import OSKeyringKeyStore, open_encrypted_database, secure_path
from .context_limits import check_bounds


class WorkspaceError(ValueError):
    pass


class WorkspaceConflict(WorkspaceError):
    pass


RECORD = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "kind", "title", "content", "references", "evidence"],
    "properties": {
        "id": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"},
        "kind": {
            "enum": [
                "domain",
                "knowledge",
                "mapping",
                "configuration",
                "review",
                "design",
            ]
        },
        "title": {"type": "string", "minLength": 1, "maxLength": 256},
        "content": {"type": "string", "maxLength": 32000},
        "references": {
            "type": "array",
            "maxItems": 100,
            "uniqueItems": True,
            "items": {"type": "string", "maxLength": 256},
        },
        "evidence": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["origin", "revision"],
                "properties": {
                    "origin": {"type": "string", "maxLength": 1024},
                    "revision": {"type": "string", "maxLength": 256},
                },
            },
        },
        "approval": {"enum": ["draft", "reviewed"]},
    },
}
DOCUMENT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "records"],
    "properties": {
        "schema_version": {"const": 1},
        "records": {"type": "array", "maxItems": 1000, "items": RECORD},
    },
}


def validate_document(value):
    try:
        check_bounds(value)
        if len(json.dumps(value).encode()) > 1048576 or list(
            Draft202012Validator(DOCUMENT).iter_errors(value)
        ):
            raise ValueError()
        ids = [r["id"] for r in value["records"]]
        if len(ids) != len(set(ids)):
            raise ValueError()
    except Exception:
        raise WorkspaceError(
            "Invalid workspace: use schema version 1, unique record IDs and bounded metadata records"
        ) from None
    return deepcopy(value)


class EnvironmentKeyStore:
    """Headless alternative: externally managed base64 key; never generated or stored here."""

    def __init__(self, name):
        self.name = name

    def get_or_create_key(self, path, *, create):
        try:
            key = base64.b64decode(os.environ[self.name], validate=True)
            if len(key) != 32:
                raise ValueError()
            return key
        except Exception:
            raise WorkspaceError(
                "Configured workspace encryption key is unavailable or invalid"
            ) from None


class WorkspaceStore:
    def __init__(self, path, *, key_store=None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        secure_path(self.path.parent, directory=True)
        self.key = (key_store or OSKeyringKeyStore()).get_or_create_key(
            self.path, create=not self.path.exists()
        )
        if not self.key:
            raise WorkspaceError("Workspace encryption key unavailable")
        self.lock = RLock()
        self.previews = {}
        with self.connection() as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS workspace_revisions (revision INTEGER PRIMARY KEY, document TEXT NOT NULL, reason TEXT NOT NULL)"
            )
            c.execute(
                "INSERT OR IGNORE INTO workspace_revisions VALUES (0,?,?)",
                (json.dumps({"schema_version": 1, "records": []}), "initial"),
            )
        secure_path(self.path)

    @contextmanager
    def connection(self):
        c = open_encrypted_database(self.path, self.key)
        try:
            with c:
                yield c
        finally:
            c.close()

    def read(self):
        with self.lock, self.connection() as c:
            row = c.execute(
                "SELECT revision, document FROM workspace_revisions ORDER BY revision DESC LIMIT 1"
            ).fetchone()
            return {"revision": row[0], "document": json.loads(row[1])}

    def save(self, document, expected_revision, reason="workspace edit"):
        value = validate_document(document)
        if type(expected_revision) != int or expected_revision < 0:
            raise WorkspaceError("Expected revision required")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 256:
            raise WorkspaceError("Bounded review reason required")
        with self.lock, self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            current = c.execute(
                "SELECT MAX(revision) FROM workspace_revisions"
            ).fetchone()[0]
            if current != expected_revision:
                raise WorkspaceConflict(
                    "Workspace changed; reload and review before saving"
                )
            c.execute(
                "INSERT INTO workspace_revisions VALUES (?,?,?)",
                (current + 1, json.dumps(value), reason),
            )
        return {"revision": current + 1, "document": value}

    def history(self):
        with self.connection() as c:
            return [
                {"revision": r[0], "reason": r[1]}
                for r in c.execute(
                    "SELECT revision,reason FROM workspace_revisions ORDER BY revision DESC LIMIT 100"
                )
            ]

    def export(self):
        return {
            "schema_version": 1,
            "kind": "uol-authored-workspace",
            "simulation": False,
            **self.read(),
        }

    def preview_import(self, envelope):
        if (
            not isinstance(envelope, dict)
            or set(envelope)
            != {"schema_version", "kind", "simulation", "revision", "document"}
            or envelope["schema_version"] != 1
            or envelope["kind"] != "uol-authored-workspace"
            or envelope["simulation"] is not False
            or type(envelope["revision"]) != int
        ):
            raise WorkspaceError("Invalid workspace export envelope")
        document = validate_document(envelope["document"])
        current = self.read()
        token = secrets.token_urlsafe(24)
        # Imported review claims never grant approval; re-review in the destination workspace.
        for r in document["records"]:
            r["approval"] = "draft"
        old = {r["id"]: r for r in current["document"]["records"]}
        new = {r["id"]: r for r in document["records"]}
        diff = {
            "added": [i for i in new if i not in old],
            "removed": [i for i in old if i not in new],
            "changed": [i for i in new if i in old and new[i] != old[i]],
        }
        with self.lock:
            if len(self.previews) >= 16:
                self.previews.clear()
            self.previews[token] = (current["revision"], deepcopy(document))
        return {
            "preview_id": token,
            "expected_revision": current["revision"],
            "diff": diff,
            "document": document,
            "approval_reset": True,
        }

    def apply_import(self, preview_id):
        with self.lock:
            if preview_id not in self.previews:
                raise WorkspaceError("Import preview unavailable; preview again")
            revision, document = self.previews.pop(preview_id)
            return self.save(
                document, revision, "Reviewed import; imported approvals reset"
            )
