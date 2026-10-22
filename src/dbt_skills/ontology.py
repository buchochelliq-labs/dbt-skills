"""Local-first Unified Ontology Layer storage and synchronization primitives."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote, unquote


JsonObject = dict[str, object]
SyncStatus = Literal["unknown", "current", "stale", "partial", "paused"]
_LOCAL_SOURCE_ID = "_local_overlay"
_DIMENSIONS = ("namespaces", "entity_types", "properties", "record_ids")
_SECRET_KEY_PARTS = ("token", "secret", "password", "credential", "authorization")


class OntologyError(RuntimeError):
    """Base exception for local UOL operations."""


class SourceNotFoundError(OntologyError):
    """Raised when a configured source cannot be found."""


class SourceDisabledError(OntologyError):
    """Raised when sync is requested for a source that is not enabled."""


class SyncInProgressError(OntologyError):
    """Raised when a different sync mode is already resumable for a source."""


class ProviderContractError(OntologyError):
    """Raised when a provider returns malformed or inconsistent data."""


@dataclass(frozen=True, slots=True)
class OntologyClaim:
    """One source assertion; relationships use an entity-valued object."""

    claim_id: str
    subject_id: str
    predicate: str
    object_value: object
    object_kind: Literal["literal", "entity"] = "literal"
    native_id: str | None = None
    namespace: str | None = None
    entity_type: str | None = None
    source_version: str | None = None
    observed_at: str | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)
    derivation: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaimRecord:
    """A claim with local source and freshness provenance."""

    claim: OntologyClaim
    source_id: str
    source_kind: Literal["provider", "local_overlay"]
    provenance: JsonObject
    authorship: JsonObject | None = None


@dataclass(frozen=True, slots=True)
class SyncScope:
    """Include/exclude filters applied locally to every provider page."""

    include_namespaces: frozenset[str] = frozenset()
    exclude_namespaces: frozenset[str] = frozenset()
    include_entity_types: frozenset[str] = frozenset()
    exclude_entity_types: frozenset[str] = frozenset()
    include_properties: frozenset[str] = frozenset()
    exclude_properties: frozenset[str] = frozenset()
    include_record_ids: frozenset[str] = frozenset()
    exclude_record_ids: frozenset[str] = frozenset()

    def allows(self, claim: OntologyClaim) -> bool:
        values = {
            "namespaces": claim.namespace,
            "entity_types": claim.entity_type,
            "properties": claim.predicate,
            "record_ids": claim.native_id or claim.claim_id,
        }
        for dimension, value in values.items():
            include = getattr(self, f"include_{dimension}")
            exclude = getattr(self, f"exclude_{dimension}")
            if value in exclude:
                return False
            if include and value not in include:
                return False
        return True

    def to_json(self) -> str:
        return json.dumps(
            {
                f"{direction}_{dimension}": sorted(getattr(self, f"{direction}_{dimension}"))
                for dimension in _DIMENSIONS
                for direction in ("include", "exclude")
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> SyncScope:
        raw = json.loads(value)
        if not isinstance(raw, Mapping):
            raise OntologyError("Stored sync scope is invalid")
        parsed: dict[str, frozenset[str]] = {}
        for dimension in _DIMENSIONS:
            for direction in ("include", "exclude"):
                key = f"{direction}_{dimension}"
                items = raw.get(key, [])
                if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                    raise OntologyError(f"Stored sync scope has invalid {key}")
                parsed[key] = frozenset(items)
        return cls(**parsed)


@dataclass(frozen=True, slots=True)
class SyncPage:
    claims: Sequence[OntologyClaim]
    next_cursor: str | None
    done: bool
    deleted_claim_ids: Sequence[str] = ()


class OntologyProvider(Protocol):
    """Adapter seam for a paginated, read-only ontology source."""

    provider_name: str
    supports_incremental: bool

    async def fetch_page(
        self,
        *,
        cursor: str | None,
        page_size: int,
        full_refresh: bool,
    ) -> SyncPage: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object, label: str) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain JSON-serializable values: {error}") from error


def _object(value: object, label: str) -> JsonObject:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with string keys")
    result = dict(value)
    _json(result, label)
    return result


def _validate_claim(claim: OntologyClaim) -> None:
    for name, value in (
        ("claim_id", claim.claim_id),
        ("subject_id", claim.subject_id),
        ("predicate", claim.predicate),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if claim.object_kind not in ("literal", "entity"):
        raise ValueError("object_kind must be 'literal' or 'entity'")
    if claim.object_kind == "entity" and (
        not isinstance(claim.object_value, str) or not claim.object_value.strip()
    ):
        raise ValueError("entity-valued claims require a non-empty string object_value")
    for name, value in (
        ("native_id", claim.native_id),
        ("namespace", claim.namespace),
        ("entity_type", claim.entity_type),
        ("source_version", claim.source_version),
        ("observed_at", claim.observed_at),
    ):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be a string or null")
    _json(claim.object_value, "object_value")
    _object(claim.evidence, "evidence")
    _object(claim.derivation, "derivation")


def _tokens(claim: OntologyClaim) -> set[str]:
    content = " ".join(
        (
            claim.subject_id,
            claim.predicate,
            json.dumps(claim.object_value, ensure_ascii=False, sort_keys=True),
            claim.namespace or "",
            claim.entity_type or "",
        )
    ).casefold()
    return {token for token in re.findall(r"[^\W_]+", content, flags=re.UNICODE) if token}


def claim_reference(source_id: str, claim_id: str) -> str:
    """Return a stable, source-qualified reference suitable for graph links."""
    return f"{quote(source_id, safe='')}#{quote(claim_id, safe='')}"


def _split_claim_reference(reference: str) -> tuple[str, str] | None:
    if "#" not in reference:
        return None
    source_id, claim_id = reference.split("#", 1)
    if not source_id or not claim_id:
        return None
    return unquote(source_id), unquote(claim_id)


class LocalOntologyStore:
    """SQLite-backed local graph with atomic source snapshots and a separate overlay.

    The database is scoped to the current OS user by its path and filesystem
    permissions. This does not provide cryptographic encryption at rest.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._sync_locks: dict[str, asyncio.Lock] = {}
        if self.path.exists() and self.path.is_dir():
            raise ValueError(f"UOL database path is a directory: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._restrict_permissions(self.path.parent, directory=True)
        self._initialize()

    @staticmethod
    def _restrict_permissions(path: Path, *, directory: bool = False) -> None:
        if os.name != "nt":
            path.chmod(0o700 if directory else 0o600)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = FULL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = sqlite3.connect(self.path, timeout=30.0)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    scope_json TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    cursor TEXT,
                    active_run_id TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'unknown',
                    generation TEXT,
                    synced_at TEXT,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS provider_claims (
                    source_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_json TEXT NOT NULL,
                    object_kind TEXT NOT NULL,
                    object_ref TEXT,
                    native_id TEXT,
                    namespace TEXT,
                    entity_type TEXT,
                    source_version TEXT,
                    observed_at TEXT,
                    evidence_json TEXT NOT NULL,
                    derivation_json TEXT NOT NULL,
                    generation TEXT NOT NULL,
                    PRIMARY KEY (source_id, claim_id),
                    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS provider_subject_idx
                    ON provider_claims(source_id, subject_id);
                CREATE INDEX IF NOT EXISTS provider_object_idx
                    ON provider_claims(source_id, object_ref);
                CREATE TABLE IF NOT EXISTS overlay_claims (
                    claim_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_json TEXT NOT NULL,
                    object_kind TEXT NOT NULL,
                    object_ref TEXT,
                    namespace TEXT,
                    entity_type TEXT,
                    evidence_json TEXT NOT NULL,
                    derivation_json TEXT NOT NULL,
                    author TEXT NOT NULL,
                    rationale TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS overlay_subject_idx
                    ON overlay_claims(subject_id);
                CREATE INDEX IF NOT EXISTS overlay_object_idx
                    ON overlay_claims(object_ref);
                CREATE TABLE IF NOT EXISTS claim_tokens (
                    source_kind TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    PRIMARY KEY (source_kind, source_id, claim_id, token)
                );
                CREATE INDEX IF NOT EXISTS claim_token_search_idx
                    ON claim_tokens(token, source_kind, source_id, claim_id);
                CREATE TABLE IF NOT EXISTS sync_runs (
                    generation TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cursor TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error TEXT,
                    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS sync_stage (
                    generation TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    payload_json TEXT,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (generation, source_id, claim_id),
                    FOREIGN KEY (generation) REFERENCES sync_runs(generation) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO settings(key, value)
                    VALUES ('cache_reads_enabled', 'true');
                PRAGMA user_version = 1;
                """
            )
            connection.commit()
        finally:
            connection.close()
        self._restrict_permissions(self.path)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.path}{suffix}")
            if sidecar.exists():
                self._restrict_permissions(sidecar)

    def register_source(
        self,
        source_id: str,
        provider_name: str,
        *,
        scope: SyncScope | None = None,
        options: Mapping[str, object] | None = None,
        enabled: bool = False,
    ) -> None:
        if not source_id or source_id == _LOCAL_SOURCE_ID:
            raise ValueError("source_id must be non-empty and cannot use the reserved overlay ID")
        if not provider_name.strip():
            raise ValueError("provider_name must be non-empty")
        options_obj = _object(options or {}, "provider options")
        for key in options_obj:
            lowered = key.casefold()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                raise ValueError(f"provider option {key!r} may contain a secret")
        scope_json = (scope or SyncScope()).to_json()
        options_json = _json(options_obj, "provider options")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT provider_name, scope_json, options_json
                FROM sources WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()
            if existing and (
                existing["provider_name"] != provider_name
                or existing["scope_json"] != scope_json
                or existing["options_json"] != options_json
            ):
                self._discard_source_snapshot(connection, source_id)
            connection.execute(
                """
                INSERT INTO sources(source_id, provider_name, enabled, scope_json, options_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    provider_name=excluded.provider_name,
                    enabled=excluded.enabled,
                    scope_json=excluded.scope_json,
                    options_json=excluded.options_json,
                    sync_status=CASE
                        WHEN excluded.enabled=0 THEN 'paused'
                        WHEN sources.sync_status='paused' AND sources.generation IS NULL THEN 'unknown'
                        WHEN sources.sync_status='paused' AND sources.last_error IS NOT NULL THEN 'stale'
                        WHEN sources.sync_status='paused' THEN 'current'
                        ELSE sources.sync_status
                    END
                """,
                (source_id, provider_name, int(enabled), scope_json, options_json),
            )
            connection.commit()

    def configure_source_scope(self, source_id: str, scope: SyncScope) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                "SELECT 1 FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if source is None:
                raise SourceNotFoundError(f"Unknown ontology source: {source_id}")
            self._discard_source_snapshot(connection, source_id)
            connection.execute(
                "UPDATE sources SET scope_json=? WHERE source_id=?",
                (scope.to_json(), source_id),
            )
            connection.commit()

    @staticmethod
    def _discard_source_snapshot(connection: sqlite3.Connection, source_id: str) -> None:
        connection.execute("DELETE FROM claim_tokens WHERE source_kind='provider' AND source_id=?", (source_id,))
        connection.execute("DELETE FROM provider_claims WHERE source_id=?", (source_id,))
        connection.execute("DELETE FROM sync_runs WHERE source_id=?", (source_id,))
        connection.execute(
            """
            UPDATE sources SET cursor=NULL, active_run_id=NULL,
                sync_status=CASE WHEN enabled=0 THEN 'paused' ELSE 'unknown' END,
                generation=NULL, synced_at=NULL, last_error=NULL
            WHERE source_id=?
            """,
            (source_id,),
        )

    def set_source_enabled(self, source_id: str, enabled: bool) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sources SET enabled=?,
                    sync_status=CASE
                        WHEN ?=0 THEN 'paused'
                        WHEN sync_status='paused' AND generation IS NULL THEN 'unknown'
                        WHEN sync_status='paused' AND last_error IS NOT NULL THEN 'stale'
                        WHEN sync_status='paused' THEN 'current'
                        ELSE sync_status
                    END
                WHERE source_id=?
                """,
                (int(enabled), int(enabled), source_id),
            )
            if cursor.rowcount == 0:
                raise SourceNotFoundError(f"Unknown ontology source: {source_id}")

    def set_cache_reads_enabled(self, enabled: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value) VALUES ('cache_reads_enabled', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                ("true" if enabled else "false",),
            )

    def cache_reads_enabled(self) -> bool:
        with self._connect() as connection:
            return self._cache_reads_enabled(connection)

    def _cache_reads_enabled(self, connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT value FROM settings WHERE key='cache_reads_enabled'"
        ).fetchone()
        return row is not None and row["value"] == "true"

    async def sync_source(
        self,
        source_id: str,
        provider: OntologyProvider,
        *,
        full_refresh: bool = False,
        page_size: int = 500,
    ) -> JsonObject:
        lock = self._sync_locks.setdefault(source_id, asyncio.Lock())
        async with lock:
            return await self._sync_source(
                source_id,
                provider,
                full_refresh=full_refresh,
                page_size=page_size,
            )

    async def _sync_source(
        self,
        source_id: str,
        provider: OntologyProvider,
        *,
        full_refresh: bool = False,
        page_size: int = 500,
    ) -> JsonObject:
        if page_size < 1 or page_size > 10_000:
            raise ValueError("page_size must be between 1 and 10000")

        source = self._source(source_id)
        if source is None:
            raise SourceNotFoundError(f"Unknown ontology source: {source_id}")
        if source["enabled"] != 1:
            raise SourceDisabledError(f"Ontology source is disabled: {source_id}")
        if source["provider_name"] != provider.provider_name:
            raise ProviderContractError(
                f"Source {source_id} is configured for {source['provider_name']}, "
                f"not {provider.provider_name}"
            )

        mode = (
            "full"
            if full_refresh or not provider.supports_incremental or source["generation"] is None
            else "incremental"
        )
        generation, cursor = self._start_or_resume_run(source, mode)
        scope = SyncScope.from_json(source["scope_json"])
        visited_cursors: set[str | None] = set()
        page_count = 0
        try:
            while True:
                if cursor in visited_cursors:
                    raise ProviderContractError("Provider repeated a sync cursor")
                visited_cursors.add(cursor)
                requested_cursor = cursor
                page = await provider.fetch_page(
                    cursor=cursor,
                    page_size=page_size,
                    full_refresh=(mode == "full"),
                )
                self._validate_page(page, cursor)
                accepted: list[OntologyClaim] = []
                excluded_ids: list[str] = []
                for claim in page.claims:
                    if not isinstance(claim, OntologyClaim):
                        raise ProviderContractError("Provider page contains a non-claim value")
                    _validate_claim(claim)
                    if scope.allows(claim):
                        accepted.append(claim)
                    else:
                        excluded_ids.append(claim.claim_id)
                self._stage_page(
                    generation,
                    source_id,
                    accepted,
                    (*page.deleted_claim_ids, *excluded_ids),
                    page.next_cursor,
                    requested_cursor,
                )
                page_count += 1
                cursor = page.next_cursor
                if page.done:
                    break
            self._publish_generation(source_id, generation, mode, cursor)
        except SyncInProgressError:
            raise
        except Exception as error:
            self._mark_sync_failure(source_id, generation, error)
            raise

        status = self.source_status(source_id)
        return {
            "source_id": source_id,
            "generation": generation,
            "mode": mode,
            "status": status["sync_status"],
            "synced_at": status["synced_at"],
            "pages": page_count,
        }

    @staticmethod
    def _validate_page(page: SyncPage, prior_cursor: str | None) -> None:
        if not isinstance(page, SyncPage):
            raise ProviderContractError("Provider returned a value that is not SyncPage")
        if not isinstance(page.claims, Sequence) or isinstance(page.claims, (str, bytes)):
            raise ProviderContractError("Provider page claims must be a sequence")
        if not isinstance(page.done, bool):
            raise ProviderContractError("Provider page done flag must be boolean")
        if page.next_cursor is not None and not isinstance(page.next_cursor, str):
            raise ProviderContractError("Provider cursor must be a string or null")
        if not isinstance(page.deleted_claim_ids, Sequence) or isinstance(
            page.deleted_claim_ids, (str, bytes)
        ):
            raise ProviderContractError("Deleted claim IDs must be a sequence")
        if not page.done and (
            page.next_cursor is None or page.next_cursor == prior_cursor
        ):
            raise ProviderContractError("A non-final provider page must advance its cursor")
        if any(not isinstance(item, str) or not item for item in page.deleted_claim_ids):
            raise ProviderContractError("Deleted claim IDs must be non-empty strings")

    def _source(self, source_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()

    def _start_or_resume_run(
        self, source: sqlite3.Row, mode: str
    ) -> tuple[str, str | None]:
        source_id = source["source_id"]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            refreshed = connection.execute(
                "SELECT * FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if refreshed is None or refreshed["enabled"] != 1:
                raise SourceDisabledError(f"Ontology source is disabled: {source_id}")
            active_id = refreshed["active_run_id"]
            if active_id:
                run = connection.execute(
                    "SELECT * FROM sync_runs WHERE generation=?", (active_id,)
                ).fetchone()
                if run and run["status"] in ("running", "failed"):
                    if run["mode"] != mode:
                        raise SyncInProgressError(
                            f"Source {source_id} has a resumable {run['mode']} sync; "
                            "resume it or purge the staged sync before changing modes"
                        )
                    connection.execute(
                        "UPDATE sync_runs SET status='running', error=NULL, updated_at=? "
                        "WHERE generation=?",
                        (_now(), active_id),
                    )
                    connection.commit()
                    return active_id, run["cursor"]
            generation = str(uuid.uuid4())
            initial_cursor = None if mode == "full" else refreshed["cursor"]
            now = _now()
            connection.execute(
                """
                INSERT INTO sync_runs(generation, source_id, mode, status, cursor, started_at, updated_at)
                VALUES (?, ?, ?, 'running', ?, ?, ?)
                """,
                (generation, source_id, mode, initial_cursor, now, now),
            )
            connection.execute(
                "UPDATE sources SET active_run_id=?, last_error=NULL WHERE source_id=?",
                (generation, source_id),
            )
            connection.commit()
            return generation, initial_cursor

    def _stage_page(
        self,
        generation: str,
        source_id: str,
        claims: Sequence[OntologyClaim],
        deleted_claim_ids: Sequence[str],
        next_cursor: str | None,
        expected_cursor: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT mode, cursor FROM sync_runs WHERE generation=?", (generation,)
            ).fetchone()
            if run is None:
                raise OntologyError("Sync staging generation disappeared")
            if run["cursor"] != expected_cursor:
                raise SyncInProgressError(
                    f"Source {source_id} advanced while this sync page was being fetched"
                )
            for claim in claims:
                payload = _json(asdict(claim), "ontology claim")
                connection.execute(
                    """
                    INSERT INTO sync_stage(generation, source_id, claim_id, payload_json, deleted)
                    VALUES (?, ?, ?, ?, 0)
                    ON CONFLICT(generation, source_id, claim_id) DO UPDATE SET
                        payload_json=excluded.payload_json, deleted=0
                    """,
                    (generation, source_id, claim.claim_id, payload),
                )
            if run["mode"] == "incremental":
                for claim_id in deleted_claim_ids:
                    connection.execute(
                        """
                        INSERT INTO sync_stage(generation, source_id, claim_id, payload_json, deleted)
                        VALUES (?, ?, ?, NULL, 1)
                        ON CONFLICT(generation, source_id, claim_id) DO UPDATE SET
                            payload_json=NULL, deleted=1
                        """,
                        (generation, source_id, claim_id),
                    )
            connection.execute(
                "UPDATE sync_runs SET cursor=?, updated_at=? WHERE generation=?",
                (next_cursor, _now(), generation),
            )
            connection.commit()

    def _publish_generation(
        self, source_id: str, generation: str, mode: str, cursor: str | None
    ) -> None:
        synced_at = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT status FROM sync_runs WHERE generation=? AND source_id=?",
                (generation, source_id),
            ).fetchone()
            if run is None:
                raise OntologyError("Cannot publish a missing sync generation")
            source = connection.execute(
                "SELECT enabled, active_run_id FROM sources WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if source is None or source["enabled"] != 1 or source["active_run_id"] != generation:
                raise SourceDisabledError(
                    f"Source {source_id} was disabled or reconfigured during sync"
                )
            if mode == "full":
                connection.execute(
                    "DELETE FROM claim_tokens WHERE source_kind='provider' AND source_id=?",
                    (source_id,),
                )
                connection.execute("DELETE FROM provider_claims WHERE source_id=?", (source_id,))
            staged = connection.execute(
                "SELECT * FROM sync_stage WHERE generation=? AND source_id=? ORDER BY claim_id",
                (generation, source_id),
            ).fetchall()
            for row in staged:
                if row["deleted"]:
                    connection.execute(
                        "DELETE FROM provider_claims WHERE source_id=? AND claim_id=?",
                        (source_id, row["claim_id"]),
                    )
                    connection.execute(
                        "DELETE FROM claim_tokens WHERE source_kind='provider' AND source_id=? AND claim_id=?",
                        (source_id, row["claim_id"]),
                    )
                    continue
                if row["payload_json"] is None:
                    raise ProviderContractError("Staged claim payload is missing")
                claim_data = json.loads(row["payload_json"])
                claim = OntologyClaim(**claim_data)
                self._upsert_provider_claim(connection, source_id, claim, generation)
            connection.execute(
                """
                UPDATE sources SET cursor=?, active_run_id=NULL, sync_status='current',
                    generation=?, synced_at=?, last_error=NULL
                WHERE source_id=?
                """,
                (cursor, generation, synced_at, source_id),
            )
            connection.execute(
                "UPDATE sync_runs SET status='complete', cursor=?, updated_at=?, error=NULL "
                "WHERE generation=?",
                (cursor, synced_at, generation),
            )
            connection.execute("DELETE FROM sync_stage WHERE generation=?", (generation,))
            connection.execute(
                "DELETE FROM sync_runs WHERE source_id=? AND generation<>? AND status='complete'",
                (source_id, generation),
            )
            connection.commit()

    @staticmethod
    def _upsert_provider_claim(
        connection: sqlite3.Connection,
        source_id: str,
        claim: OntologyClaim,
        generation: str,
    ) -> None:
        object_json = _json(claim.object_value, "object_value")
        object_ref = (
            claim.object_value
            if claim.object_kind == "entity" and isinstance(claim.object_value, str)
            else None
        )
        connection.execute(
            """
            INSERT INTO provider_claims(
                source_id, claim_id, subject_id, predicate, object_json, object_kind,
                object_ref, native_id, namespace, entity_type, source_version, observed_at,
                evidence_json, derivation_json, generation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, claim_id) DO UPDATE SET
                subject_id=excluded.subject_id, predicate=excluded.predicate,
                object_json=excluded.object_json, object_kind=excluded.object_kind,
                object_ref=excluded.object_ref, native_id=excluded.native_id,
                namespace=excluded.namespace, entity_type=excluded.entity_type,
                source_version=excluded.source_version, observed_at=excluded.observed_at,
                evidence_json=excluded.evidence_json, derivation_json=excluded.derivation_json,
                generation=excluded.generation
            """,
            (
                source_id,
                claim.claim_id,
                claim.subject_id,
                claim.predicate,
                object_json,
                claim.object_kind,
                object_ref,
                claim.native_id,
                claim.namespace,
                claim.entity_type,
                claim.source_version,
                claim.observed_at,
                _json(claim.evidence, "evidence"),
                _json(claim.derivation, "derivation"),
                generation,
            ),
        )
        connection.execute(
            "DELETE FROM claim_tokens WHERE source_kind='provider' AND source_id=? AND claim_id=?",
            (source_id, claim.claim_id),
        )
        connection.executemany(
            "INSERT INTO claim_tokens(source_kind, source_id, claim_id, token) "
            "VALUES ('provider', ?, ?, ?)",
            [(source_id, claim.claim_id, token) for token in _tokens(claim)],
        )

    def _mark_sync_failure(
        self, source_id: str, generation: str, error: Exception
    ) -> None:
        message = f"{type(error).__name__}: {error}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE sync_runs SET status='failed', error=?, updated_at=? WHERE generation=?",
                (message, _now(), generation),
            )
            claim_count = connection.execute(
                "SELECT COUNT(*) FROM provider_claims WHERE source_id=?", (source_id,)
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE sources SET
                    sync_status=CASE
                        WHEN enabled=0 THEN 'paused'
                        WHEN ? > 0 THEN 'stale'
                        ELSE 'partial'
                    END,
                    last_error=?
                WHERE source_id=? AND active_run_id=?
                """,
                (claim_count, message, source_id, generation),
            )
            connection.commit()

    def source_status(self, source_id: str) -> JsonObject:
        source = self._source(source_id)
        if source is None:
            raise SourceNotFoundError(f"Unknown ontology source: {source_id}")
        with self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM provider_claims WHERE source_id=?", (source_id,)
            ).fetchone()[0]
        return {
            "source_id": source_id,
            "provider_name": source["provider_name"],
            "enabled": bool(source["enabled"]),
            "sync_status": source["sync_status"],
            "generation": source["generation"],
            "synced_at": source["synced_at"],
            "claim_count": count,
            "scope": json.loads(source["scope_json"]),
            "last_error": source["last_error"],
            "sync_enabled": bool(source["enabled"]),
        }

    def sources(self) -> list[JsonObject]:
        with self._connect() as connection:
            ids = [
                row["source_id"]
                for row in connection.execute("SELECT source_id FROM sources ORDER BY source_id")
            ]
        return [self.source_status(source_id) for source_id in ids]

    def source_config(self, source_id: str) -> JsonObject:
        source = self._source(source_id)
        if source is None:
            raise SourceNotFoundError(f"Unknown ontology source: {source_id}")
        return {
            "source_id": source_id,
            "provider_name": source["provider_name"],
            "enabled": bool(source["enabled"]),
            "options": json.loads(source["options_json"]),
            "scope": json.loads(source["scope_json"]),
        }

    def purge_source_cache(self, source_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if exists is None:
                raise SourceNotFoundError(f"Unknown ontology source: {source_id}")
            self._discard_source_snapshot(connection, source_id)
            connection.commit()

    def purge_provider_cache(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source_ids = [
                row["source_id"]
                for row in connection.execute("SELECT source_id FROM sources")
            ]
            for source_id in source_ids:
                self._discard_source_snapshot(connection, source_id)
            connection.commit()

    def discard_pending_sync(self, source_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                "SELECT active_run_id, generation, enabled FROM sources WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if source is None:
                raise SourceNotFoundError(f"Unknown ontology source: {source_id}")
            if source["active_run_id"] is None:
                connection.commit()
                return
            connection.execute(
                "DELETE FROM sync_runs WHERE generation=?", (source["active_run_id"],)
            )
            connection.execute(
                """
                UPDATE sources SET active_run_id=NULL, last_error=NULL,
                    sync_status=CASE
                        WHEN enabled=0 THEN 'paused'
                        WHEN generation IS NULL THEN 'unknown'
                        ELSE 'stale'
                    END
                WHERE source_id=?
                """,
                (source_id,),
            )
            connection.commit()

    def add_overlay_claim(
        self,
        claim: OntologyClaim,
        *,
        author: str,
        rationale: str | None = None,
    ) -> ClaimRecord:
        _validate_claim(claim)
        if not author.strip():
            raise ValueError("author must be a non-empty, non-secret identifier")
        claim_id = claim.claim_id
        created_at = _now()
        object_ref = (
            claim.object_value
            if claim.object_kind == "entity" and isinstance(claim.object_value, str)
            else None
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO overlay_claims(
                    claim_id, subject_id, predicate, object_json, object_kind, object_ref,
                    namespace, entity_type, evidence_json, derivation_json, author,
                    rationale, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    claim.subject_id,
                    claim.predicate,
                    _json(claim.object_value, "object_value"),
                    claim.object_kind,
                    object_ref,
                    claim.namespace,
                    claim.entity_type,
                    _json(claim.evidence, "evidence"),
                    _json(claim.derivation, "derivation"),
                    author,
                    rationale,
                    created_at,
                    created_at,
                ),
            )
            connection.executemany(
                "INSERT INTO claim_tokens(source_kind, source_id, claim_id, token) "
                "VALUES ('local_overlay', ?, ?, ?)",
                [
                    (_LOCAL_SOURCE_ID, claim_id, token)
                    for token in _tokens(claim)
                ],
            )
            connection.commit()
        return ClaimRecord(
            claim=claim,
            source_id=_LOCAL_SOURCE_ID,
            source_kind="local_overlay",
            provenance={
                "source_id": _LOCAL_SOURCE_ID,
                "claim_id": claim_id,
                "observed_at": created_at,
                "evidence": dict(claim.evidence),
                "derivation": dict(claim.derivation),
            },
            authorship={
                "author": author,
                "created_at": created_at,
                "rationale": rationale,
                "provider_endorsement": False,
            },
        )

    def create_link(
        self,
        subject_source_id: str,
        subject_claim_id: str,
        predicate: str,
        object_source_id: str,
        object_claim_id: str,
        *,
        evidence: Mapping[str, object],
        author: str,
        rationale: str | None = None,
    ) -> ClaimRecord:
        evidence_obj = _object(evidence, "link evidence")
        if not evidence_obj:
            raise ValueError("Cross-source links require explicit evidence")
        subject_ref = claim_reference(subject_source_id, subject_claim_id)
        object_ref = claim_reference(object_source_id, object_claim_id)
        if self.get_claim(subject_source_id, subject_claim_id) is None:
            raise SourceNotFoundError(f"Link subject claim does not exist: {subject_ref}")
        if self.get_claim(object_source_id, object_claim_id) is None:
            raise SourceNotFoundError(f"Link object claim does not exist: {object_ref}")
        return self.add_overlay_claim(
            OntologyClaim(
                claim_id=str(uuid.uuid4()),
                subject_id=subject_ref,
                predicate=predicate,
                object_value=object_ref,
                object_kind="entity",
                evidence={
                    **evidence_obj,
                    "link_review_status": "user_reviewed",
                    "subject_ref": subject_ref,
                    "object_ref": object_ref,
                },
                derivation={"kind": "user_authored_cross_source_link"},
            ),
            author=author,
            rationale=rationale,
        )

    def delete_overlay_claim(self, claim_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM claim_tokens WHERE source_kind='local_overlay' AND claim_id=?",
                (claim_id,),
            )
            cursor = connection.execute(
                "DELETE FROM overlay_claims WHERE claim_id=?", (claim_id,)
            )
            if cursor.rowcount == 0:
                raise SourceNotFoundError(f"Unknown local overlay claim: {claim_id}")
            connection.commit()

    def clear_overlay(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM claim_tokens WHERE source_kind='local_overlay'")
            connection.execute("DELETE FROM overlay_claims")
            connection.commit()

    def get_claim(self, source_id: str, claim_id: str) -> ClaimRecord | None:
        if source_id == _LOCAL_SOURCE_ID:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM overlay_claims WHERE claim_id=?", (claim_id,)
                ).fetchone()
            return self._overlay_record(row) if row else None
        with self._connect() as connection:
            if not self._cache_reads_enabled(connection):
                return None
            row = connection.execute(
                "SELECT * FROM provider_claims WHERE source_id=? AND claim_id=?",
                (source_id, claim_id),
            ).fetchone()
            source = connection.execute(
                "SELECT provider_name FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
        return self._provider_record(row, source["provider_name"]) if row and source else None

    def search(self, query: str, *, limit: int = 20) -> list[ClaimRecord]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        tokens = sorted(_tokens(OntologyClaim("_query", query, "", ""))) if query.strip() else []
        if not tokens:
            return []
        placeholders = ",".join("?" for _ in tokens)
        with self._connect() as connection:
            allow_cache = self._cache_reads_enabled(connection)
            source_kinds = ("local_overlay", "provider") if allow_cache else ("local_overlay",)
            kind_placeholders = ",".join("?" for _ in source_kinds)
            rows = connection.execute(
                f"""
                SELECT t.source_kind, t.source_id, t.claim_id, COUNT(DISTINCT t.token) AS hits
                FROM claim_tokens t
                WHERE t.token IN ({placeholders})
                    AND t.source_kind IN ({kind_placeholders})
                GROUP BY t.source_kind, t.source_id, t.claim_id
                HAVING COUNT(DISTINCT t.token)=?
                ORDER BY hits DESC, t.source_kind, t.source_id, t.claim_id
                LIMIT ?
                """,
                (*tokens, *source_kinds, len(tokens), limit),
            ).fetchall()
            records: list[ClaimRecord] = []
            for row in rows:
                if row["source_kind"] == "local_overlay":
                    claim_row = connection.execute(
                        "SELECT * FROM overlay_claims WHERE claim_id=?",
                        (row["claim_id"],),
                    ).fetchone()
                    record = self._overlay_record(claim_row)
                else:
                    claim_row = connection.execute(
                        "SELECT * FROM provider_claims WHERE source_id=? AND claim_id=?",
                        (row["source_id"], row["claim_id"]),
                    ).fetchone()
                    source = connection.execute(
                        "SELECT provider_name FROM sources WHERE source_id=?",
                        (row["source_id"],),
                    ).fetchone()
                    record = (
                        self._provider_record(claim_row, source["provider_name"])
                        if claim_row and source
                        else None
                    )
                if record:
                    records.append(record)
            return records

    def neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        max_claims: int = 500,
    ) -> list[ClaimRecord]:
        if depth < 1 or depth > 8:
            raise ValueError("depth must be between 1 and 8")
        if max_claims < 1 or max_claims > 10_000:
            raise ValueError("max_claims must be between 1 and 10000")
        with self._connect() as connection:
            allow_cache = self._cache_reads_enabled(connection)
            visited: set[str] = {entity_id}
            result: dict[tuple[str, str, str], ClaimRecord] = {}
            frontier = deque([(entity_id, 0)])
            while frontier and len(result) < max_claims:
                current, current_depth = frontier.popleft()
                if current_depth >= depth:
                    continue
                referenced = self._record_for_reference(connection, current, allow_cache)
                if referenced:
                    key = (
                        referenced.source_kind,
                        referenced.source_id,
                        referenced.claim.claim_id,
                    )
                    result.setdefault(key, referenced)
                    for target in self._claim_targets(referenced.claim):
                        if target not in visited:
                            visited.add(target)
                            frontier.append((target, current_depth + 1))
                provider_rows = (
                    connection.execute(
                        """
                        SELECT c.*, s.provider_name
                        FROM provider_claims c JOIN sources s USING(source_id)
                        WHERE c.subject_id=? OR c.object_ref=?
                        """,
                        (current, current),
                    ).fetchall()
                    if allow_cache
                    else []
                )
                overlay_rows = connection.execute(
                    "SELECT * FROM overlay_claims WHERE subject_id=? OR object_ref=?",
                    (current, current),
                ).fetchall()
                for row in provider_rows:
                    record = self._provider_record(row, row["provider_name"])
                    key = (record.source_kind, record.source_id, record.claim.claim_id)
                    if key not in result:
                        result[key] = record
                    targets = [record.claim.subject_id]
                    if record.claim.object_kind == "entity":
                        targets.append(record.claim.object_value)
                    for target in targets:
                        if isinstance(target, str) and target not in visited:
                            visited.add(target)
                            frontier.append((target, current_depth + 1))
                    if len(result) >= max_claims:
                        break
                if len(result) < max_claims:
                    for row in overlay_rows:
                        record = self._overlay_record(row)
                        key = (record.source_kind, record.source_id, record.claim.claim_id)
                        if key not in result:
                            result[key] = record
                        targets = [record.claim.subject_id]
                        if record.claim.object_kind == "entity":
                            targets.append(record.claim.object_value)
                        for target in targets:
                            if isinstance(target, str) and target not in visited:
                                visited.add(target)
                                frontier.append((target, current_depth + 1))
                        if len(result) >= max_claims:
                            break
            return list(result.values())

    def _record_for_reference(
        self,
        connection: sqlite3.Connection,
        reference: str,
        allow_cache: bool,
    ) -> ClaimRecord | None:
        parts = _split_claim_reference(reference)
        if parts is None:
            return None
        source_id, claim_id = parts
        if source_id == _LOCAL_SOURCE_ID:
            row = connection.execute(
                "SELECT * FROM overlay_claims WHERE claim_id=?", (claim_id,)
            ).fetchone()
            return self._overlay_record(row) if row else None
        if not allow_cache:
            return None
        row = connection.execute(
            """
            SELECT c.*, s.provider_name
            FROM provider_claims c JOIN sources s USING(source_id)
            WHERE c.source_id=? AND c.claim_id=?
            """,
            (source_id, claim_id),
        ).fetchone()
        return self._provider_record(row, row["provider_name"]) if row else None

    @staticmethod
    def _claim_targets(claim: OntologyClaim) -> list[str]:
        targets = [claim.subject_id]
        if claim.object_kind == "entity" and isinstance(claim.object_value, str):
            targets.append(claim.object_value)
        return targets

    @staticmethod
    def _provider_record(row: sqlite3.Row, provider_name: str) -> ClaimRecord:
        claim = OntologyClaim(
            claim_id=row["claim_id"],
            subject_id=row["subject_id"],
            predicate=row["predicate"],
            object_value=json.loads(row["object_json"]),
            object_kind=row["object_kind"],
            native_id=row["native_id"],
            namespace=row["namespace"],
            entity_type=row["entity_type"],
            source_version=row["source_version"],
            observed_at=row["observed_at"],
            evidence=json.loads(row["evidence_json"]),
            derivation=json.loads(row["derivation_json"]),
        )
        return ClaimRecord(
            claim=claim,
            source_id=row["source_id"],
            source_kind="provider",
            provenance={
                "provider": provider_name,
                "source_id": row["source_id"],
                "native_id": row["native_id"],
                "source_version": row["source_version"],
                "observed_at": row["observed_at"],
                "sync_generation": row["generation"],
                "evidence": dict(claim.evidence),
                "derivation": dict(claim.derivation),
            },
        )

    @staticmethod
    def _overlay_record(row: sqlite3.Row) -> ClaimRecord:
        claim = OntologyClaim(
            claim_id=row["claim_id"],
            subject_id=row["subject_id"],
            predicate=row["predicate"],
            object_value=json.loads(row["object_json"]),
            object_kind=row["object_kind"],
            namespace=row["namespace"],
            entity_type=row["entity_type"],
            evidence=json.loads(row["evidence_json"]),
            derivation=json.loads(row["derivation_json"]),
        )
        return ClaimRecord(
            claim=claim,
            source_id=_LOCAL_SOURCE_ID,
            source_kind="local_overlay",
            provenance={
                "source_id": _LOCAL_SOURCE_ID,
                "claim_id": claim.claim_id,
                "observed_at": row["created_at"],
                "updated_at": row["updated_at"],
                "evidence": dict(claim.evidence),
                "derivation": dict(claim.derivation),
            },
            authorship={
                "author": row["author"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "rationale": row["rationale"],
                "provider_endorsement": False,
            },
        )


class JSONSnapshotProvider:
    """Local JSON snapshot adapter for development and offline provider fixtures.

    Expected document shape: ``{"version": "...", "claims": [...]}``.
    This adapter is non-incremental and never performs network or source writes.
    """

    provider_name = "json_snapshot"
    supports_incremental = False

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._claims: list[OntologyClaim] | None = None
        self._revision: str | None = None

    async def fetch_page(
        self,
        *,
        cursor: str | None,
        page_size: int,
        full_refresh: bool,
    ) -> SyncPage:
        del full_refresh
        cursor_revision: str | None = None
        offset = 0
        if cursor is not None:
            try:
                cursor_revision, cursor_offset = cursor.split(":", 1)
                offset = int(cursor_offset)
            except ValueError as error:
                raise ProviderContractError("JSON snapshot cursor is invalid") from error
        try:
            content = await asyncio.to_thread(self.path.read_bytes)
        except OSError as error:
            raise ProviderContractError(
                f"Cannot read ontology snapshot {self.path}: {error}"
            ) from error
        revision = hashlib.sha256(content).hexdigest()
        if cursor_revision is not None and cursor_revision != revision:
            raise ProviderContractError(
                "JSON snapshot changed during a resumable sync; discard the pending sync and restart"
            )
        if self._claims is None:
            try:
                document = json.loads(content)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ProviderContractError(
                    f"Cannot read ontology snapshot {self.path}: {error}"
                ) from error
            if not isinstance(document, Mapping):
                raise ProviderContractError("JSON ontology snapshot must contain an object")
            raw_claims = document.get("claims")
            if not isinstance(raw_claims, list):
                raise ProviderContractError("JSON ontology snapshot must contain a claims array")
            version = document.get("version")
            if version is not None and not isinstance(version, str):
                raise ProviderContractError("JSON ontology snapshot version must be a string")
            claims: list[OntologyClaim] = []
            for item in raw_claims:
                if not isinstance(item, Mapping):
                    raise ProviderContractError("Every JSON snapshot claim must be an object")
                try:
                    claim = OntologyClaim(
                        claim_id=item["claim_id"],
                        subject_id=item["subject_id"],
                        predicate=item["predicate"],
                        object_value=item["object_value"],
                        object_kind=item.get("object_kind", "literal"),
                        native_id=item.get("native_id", item["claim_id"]),
                        namespace=item.get("namespace"),
                        entity_type=item.get("entity_type"),
                        source_version=item.get("source_version", version),
                        observed_at=item.get("observed_at"),
                        evidence=item.get("evidence", {}),
                        derivation=item.get("derivation", {}),
                    )
                except (KeyError, TypeError) as error:
                    raise ProviderContractError(
                        f"Invalid JSON snapshot claim: {error}"
                    ) from error
                _validate_claim(claim)
                claims.append(claim)
            self._claims = claims
        self._revision = revision
        claims = self._claims
        if offset < 0 or offset > len(claims):
            raise ProviderContractError("JSON snapshot cursor is outside the snapshot")
        selected = claims[offset : offset + page_size]
        next_offset = offset + len(selected)
        done = next_offset >= len(claims)
        return SyncPage(
            claims=selected,
            next_cursor=None if done else f"{self._revision}:{next_offset}",
            done=done,
        )


def default_store_path() -> Path:
    """Return the current user's application-data location for the UOL database."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        if not root:
            raise OSError("LOCALAPPDATA is unavailable; provide an explicit UOL database path")
        return Path(root) / "dbt-skills" / "uol" / "ontology.sqlite3"
    root = os.environ.get("XDG_DATA_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".local" / "share"
    return base / "dbt-skills" / "uol" / "ontology.sqlite3"
