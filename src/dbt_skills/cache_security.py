"""At-rest protection for the local UOL SQLite cache."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import shutil
import sqlite3 as plaintext_sqlite
import struct
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Protocol

from sqlcipher3 import dbapi2 as sqlcipher


class CacheProtectionError(RuntimeError):
    """Raised when encrypted cache protection cannot be established."""


class CacheKeyStore(Protocol):
    def get_or_create_key(self, database_path: Path, *, create: bool) -> bytes | None: ...


@contextmanager
def _key_creation_lock(database_path: Path):
    lock_path = Path(f"{database_path}.keylock")
    descriptor = None
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        secure_path(lock_path)
        lock_file = os.fdopen(descriptor, "r+b")
    except CacheProtectionError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise CacheProtectionError(
            "Cannot create a protected lock for the UOL encryption key."
        ) from error
    try:
        if lock_file.seek(0, os.SEEK_END) == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError as error:
        raise CacheProtectionError(
            "Cannot lock the UOL encryption key while accessing the credential store."
        ) from error
    finally:
        lock_file.close()


_cipher_checked = False
_cipher_check_lock = Lock()


class OSKeyringKeyStore:
    """Store one random SQLCipher key in the current user's native keychain."""

    _service = "dbt-skills.uol.sqlcipher.v1"
    _allowed_backend_modules = (
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
    )

    def __init__(self) -> None:
        try:
            import keyring
        except ImportError as error:
            raise CacheProtectionError(
                "The keyring dependency is unavailable; install requirements.txt."
            ) from error
        self._keyring = keyring
        backend = keyring.get_keyring()
        module = type(backend).__module__
        if not any(
            module == allowed or module.startswith(f"{allowed}.")
            for allowed in self._allowed_backend_modules
        ):
            raise CacheProtectionError(
                "No supported native credential-store backend is available. "
                "Configure Windows Credential Locker, macOS Keychain, or a Linux "
                "Secret Service/KWallet backend; plaintext fallback is disabled."
            )

    @staticmethod
    def _username(database_path: Path) -> str:
        identity = os.path.normcase(str(database_path.resolve()))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def get_or_create_key(self, database_path: Path, *, create: bool) -> bytes | None:
        username = self._username(database_path)
        with _key_creation_lock(database_path):
            try:
                stored = self._keyring.get_password(self._service, username)
                if stored is None:
                    if not create:
                        return None
                    self._keyring.set_password(
                        self._service,
                        username,
                        base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                    )
                    stored = self._keyring.get_password(self._service, username)
            except (OSError, RuntimeError, self._keyring.errors.KeyringError) as error:
                raise CacheProtectionError(
                    "The native credential store could not read or create the UOL key."
                ) from error
            if stored is None:
                raise CacheProtectionError(
                    "The native credential store did not retain the UOL encryption key."
                )
            try:
                key = base64.b64decode(stored, validate=True)
            except (ValueError, TypeError) as error:
                raise CacheProtectionError(
                    "The stored UOL encryption key is malformed; the database was not opened."
                ) from error
            if len(key) != 32:
                raise CacheProtectionError(
                    "The stored UOL encryption key has an invalid length; the database was not opened."
                )
            return key


def secure_path(path: Path, *, directory: bool = False) -> None:
    """Restrict an app-owned cache directory or one of its files to the user."""
    if os.name == "nt":
        _secure_windows_path(path, directory=directory)
        return
    try:
        path.chmod(0o700 if directory else 0o600)
        stat = path.stat()
        mode = stat.st_mode & 0o777
    except OSError as error:
        raise CacheProtectionError(
            f"Cannot secure UOL cache path {path}: {error}"
        ) from error
    if mode & 0o077:
        raise CacheProtectionError(
            f"UOL cache path permissions are not user-only: {path}"
        )
    if hasattr(os, "geteuid") and stat.st_uid != os.geteuid():
        raise CacheProtectionError(f"Current user does not own UOL cache path: {path}")


def _secure_windows_path(path: Path, *, directory: bool) -> None:
    try:
        import ntsecuritycon
        import win32api
        import win32security
        import pywintypes
    except ImportError as error:
        raise CacheProtectionError(
            "Windows ACL validation is unavailable; install requirements.txt."
        ) from error
    try:
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            ntsecuritycon.TOKEN_QUERY,
        )
        user_sid = win32security.GetTokenInformation(
            token,
            win32security.TokenUser,
        )[0]
        system_sid = win32security.CreateWellKnownSid(
            win32security.WinLocalSystemSid,
            None,
        )
        acl = win32security.ACL()
        inheritance = (
            win32security.OBJECT_INHERIT_ACE | win32security.CONTAINER_INHERIT_ACE
            if directory
            else 0
        )
        for sid in (user_sid, system_sid):
            acl.AddAccessAllowedAceEx(
                win32security.ACL_REVISION,
                inheritance,
                ntsecuritycon.FILE_ALL_ACCESS,
                sid,
            )
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
        descriptor = win32security.GetFileSecurity(
            str(path),
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        owner = descriptor.GetSecurityDescriptorOwner()
        actual_acl = descriptor.GetSecurityDescriptorDacl()
        control, _revision = descriptor.GetSecurityDescriptorControl()
        if not control & win32security.SE_DACL_PROTECTED or not actual_acl:
            raise CacheProtectionError(
                f"UOL cache path does not have a protected Windows ACL: {path}"
            )
        if win32security.ConvertSidToStringSid(owner) != win32security.ConvertSidToStringSid(
            user_sid
        ):
            raise CacheProtectionError(
                f"Current user is not the owner of UOL cache path: {path}"
            )
        allowed_sids = (user_sid, system_sid)
        for index in range(actual_acl.GetAceCount()):
            ace_info, access_mask, sid = actual_acl.GetAce(index)
            ace_type, _flags = ace_info
            if ace_type != win32security.ACCESS_ALLOWED_ACE_TYPE or not any(
                win32security.ConvertSidToStringSid(sid)
                == win32security.ConvertSidToStringSid(allowed)
                for allowed in allowed_sids
            ) or access_mask & ntsecuritycon.FILE_ALL_ACCESS != ntsecuritycon.FILE_ALL_ACCESS:
                raise CacheProtectionError(
                    f"UOL cache path ACL grants unexpected access: {path}"
                )
    except CacheProtectionError:
        raise
    except (OSError, RuntimeError, pywintypes.error) as error:
        raise CacheProtectionError(
            f"Cannot establish or verify a protected Windows ACL for {path}."
        ) from error


def _check_cipher_support() -> None:
    global _cipher_checked
    if _cipher_checked:
        return
    with _cipher_check_lock:
        if _cipher_checked:
            return
        connection = sqlcipher.connect(":memory:")
        try:
            row = connection.execute("PRAGMA cipher_version").fetchone()
        except sqlcipher.Error as error:
            raise CacheProtectionError("SQLCipher is unavailable.") from error
        finally:
            connection.close()
        if not row or not row[0]:
            raise CacheProtectionError("The SQLite runtime does not provide SQLCipher.")
        _cipher_checked = True


def open_encrypted_database(
    path: str | Path,
    key: bytes,
    *,
    timeout: float = 30.0,
):
    """Open a SQLCipher database and reject plaintext or invalid keys."""
    database_path = Path(path)
    if len(key) != 32:
        raise CacheProtectionError("The UOL encryption key must be 256 bits.")
    _check_cipher_support()
    connection = None
    try:
        connection = sqlcipher.connect(database_path, timeout=timeout)
        connection.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
        version = connection.execute("PRAGMA cipher_version").fetchone()
        if not version or not version[0]:
            raise CacheProtectionError("The SQLite runtime does not provide SQLCipher.")
        connection.execute("PRAGMA cipher_memory_security = ON")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return connection
    except CacheProtectionError:
        if connection is not None:
            connection.close()
        raise
    except sqlcipher.Error as error:
        if connection is not None:
            connection.close()
        if database_path.exists():
            try:
                with database_path.open("rb") as database_file:
                    header = database_file.read(16)
            except OSError:
                header = b""
            if header == b"SQLite format 3\x00":
                raise CacheProtectionError(
                    "This UOL cache is plaintext. Run the explicit "
                    "'protect-cache' migration before using the encrypted store."
                ) from error
        raise CacheProtectionError(
            "Cannot open the encrypted UOL cache with its stored key. "
            "The key may be missing or the cache may be damaged."
        ) from error


def migrate_plaintext_cache(
    path: str | Path,
    *,
    key_store: CacheKeyStore | None = None,
    backup_path: str | Path | None = None,
) -> Path:
    """Convert a plaintext SQLite cache and retain an encrypted recovery copy."""
    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise CacheProtectionError(f"Plaintext UOL cache does not exist: {source_path}")
    try:
        with source_path.open("rb") as database_file:
            header = database_file.read(16)
    except OSError as error:
        raise CacheProtectionError("Cannot read the selected UOL cache.") from error
    if header != b"SQLite format 3\x00":
        raise CacheProtectionError(
            "The selected file is not a recognizable plaintext SQLite cache."
        )
    secure_path(source_path.parent, directory=True)
    secure_path(source_path)
    key_provider = key_store or OSKeyringKeyStore()
    key = key_provider.get_or_create_key(source_path, create=True)
    if key is None:
        raise CacheProtectionError("The native credential store did not provide a UOL key.")

    recovery_path = (
        Path(backup_path).expanduser().resolve()
        if backup_path is not None
        else source_path.with_name(f"{source_path.name}.encrypted-backup")
    )
    if recovery_path == source_path or recovery_path.exists():
        raise CacheProtectionError(
            f"Encrypted recovery path already exists or conflicts with the cache: {recovery_path}"
        )

    stage_handle, stage_name = tempfile.mkstemp(
        prefix=f".{source_path.name}.encrypt-",
        suffix=".sqlite3",
        dir=source_path.parent,
    )
    os.close(stage_handle)
    stage_path = Path(stage_name)
    recovery_created = False
    replacement_complete = False
    try:
        source = plaintext_sqlite.connect(source_path, timeout=30.0)
        try:
            source.execute("PRAGMA busy_timeout = 30000")
            source.execute("PRAGMA temp_store = MEMORY")
            integrity = source.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise CacheProtectionError(
                    "The plaintext cache failed SQLite integrity_check; migration stopped."
                )
            journal_mode = source.execute("PRAGMA journal_mode").fetchone()[0]
            if journal_mode.casefold() == "wal":
                checkpoint = source.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if not checkpoint or checkpoint[0] != 0:
                    raise CacheProtectionError(
                        "The plaintext cache is busy; stop other UOL processes and retry migration."
                    )
            encrypted = open_encrypted_database(stage_path, key)
            try:
                encrypted.execute(
                    "ATTACH DATABASE ? AS plaintext KEY ?",
                    (str(source_path), ""),
                )
                encrypted.execute(
                    "SELECT sqlcipher_export('main', 'plaintext')"
                ).fetchone()
                encrypted.execute("DETACH DATABASE plaintext")
                encrypted.commit()
                checkpoint = encrypted.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if not checkpoint or checkpoint[0] != 0:
                    raise CacheProtectionError(
                        "Encrypted cache could not be checkpointed; plaintext cache was preserved."
                    )
                encrypted_integrity = encrypted.execute(
                    "PRAGMA integrity_check"
                ).fetchone()
                if not encrypted_integrity or encrypted_integrity[0] != "ok":
                    raise CacheProtectionError(
                        "Encrypted cache verification failed; plaintext cache was preserved."
                    )
                if _logical_database_digest(source) != _logical_database_digest(encrypted):
                    raise CacheProtectionError(
                        "Encrypted cache schema/data verification failed; "
                        "plaintext cache was preserved."
                    )
            finally:
                encrypted.close()
        finally:
            source.close()

        secure_path(stage_path)
        recovery_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        secure_path(recovery_path.parent, directory=True)
        with stage_path.open("rb") as staged, recovery_path.open("xb") as backup:
            recovery_created = True
            shutil.copyfileobj(staged, backup)
        secure_path(recovery_path)
        with recovery_path.open("rb") as backup:
            if backup.read(16) == b"SQLite format 3\x00":
                raise CacheProtectionError(
                    "Encrypted recovery copy unexpectedly contains a plaintext SQLite header."
                )
        encrypted_backup = open_encrypted_database(recovery_path, key)
        try:
            backup_integrity = encrypted_backup.execute("PRAGMA integrity_check").fetchone()
            if not backup_integrity or backup_integrity[0] != "ok":
                raise CacheProtectionError(
                    "Encrypted recovery copy failed integrity verification."
                )
            encrypted_backup.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            encrypted_backup.close()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{source_path}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        os.replace(stage_path, source_path)
        replacement_complete = True
        secure_path(source_path)
        return recovery_path
    except (OSError, plaintext_sqlite.Error, sqlcipher.Error) as error:
        raise CacheProtectionError(
            "Plaintext cache migration failed; the original cache was preserved."
        ) from error
    finally:
        for temporary_path in (
            stage_path,
            Path(f"{stage_path}-wal"),
            Path(f"{stage_path}-shm"),
        ):
            if temporary_path.exists():
                temporary_path.unlink()
        if recovery_created and not replacement_complete and recovery_path.exists():
            recovery_path.unlink()


def _logical_database_digest(connection) -> bytes:
    digest = hashlib.sha256()
    schema = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "ORDER BY type, name"
    ).fetchall()
    for schema_row in schema:
        _update_digest(digest, schema_row)
    for object_type, name, _table_name, statement in schema:
        if object_type != "table":
            continue
        escaped_name = name.replace('"', '""')
        columns = connection.execute(
            f'PRAGMA table_info("{escaped_name}")'
        ).fetchall()
        primary_key = [
            row[1]
            for row in sorted((row for row in columns if row[5]), key=lambda row: row[5])
        ]
        without_rowid = bool(statement and "WITHOUT ROWID" in statement.upper())
        if without_rowid and not primary_key:
            raise CacheProtectionError(
                f"Cannot verify rows in SQLite table without a primary key: {name}"
            )
        order_by = (
            ", ".join(f'"{column.replace(chr(34), chr(34) * 2)}"' for column in primary_key)
            if without_rowid
            else "rowid"
        )
        cursor = connection.execute(
            f'SELECT * FROM "{escaped_name}" ORDER BY {order_by}'
        )
        for row in cursor:
            _update_digest(digest, row)
    return digest.digest()


def _update_digest(digest, values) -> None:
    for value in values:
        if value is None:
            encoded = b"\x00"
        elif isinstance(value, int):
            encoded = b"\x01" + str(value).encode("ascii")
        elif isinstance(value, float):
            encoded = b"\x02" + struct.pack(">d", value)
        elif isinstance(value, str):
            encoded = b"\x03" + value.encode("utf-8")
        elif isinstance(value, bytes):
            encoded = b"\x04" + value
        else:
            raise CacheProtectionError(
                f"Cannot verify SQLite value of type {type(value).__name__}."
            )
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
