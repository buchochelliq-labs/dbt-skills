"""Test-only key stores; never used by the shipped CLI or MCP server."""

from __future__ import annotations

import base64
import json
import secrets
from pathlib import Path
from threading import Lock


class MemoryKeyStore:
    def __init__(self):
        self._keys: dict[Path, bytes] = {}
        self._lock = Lock()

    def get_or_create_key(self, database_path: Path, *, create: bool) -> bytes | None:
        key_path = database_path.resolve()
        with self._lock:
            key = self._keys.get(key_path)
            if key is None and create:
                key = secrets.token_bytes(32)
                self._keys[key_path] = key
            return key


class FileKeyStore:
    """A temporary test fixture to share a key between a test and child process."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get_or_create_key(self, database_path: Path, *, create: bool) -> bytes | None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return base64.b64decode(data["key"], validate=True)
        if not create:
            return None
        self.path.write_text(
            json.dumps({"key": base64.b64encode(secrets.token_bytes(32)).decode("ascii")}),
            encoding="utf-8",
        )
        if self.path.stat().st_mode & 0o077:
            self.path.chmod(0o600)
        return self.get_or_create_key(database_path, create=False)
