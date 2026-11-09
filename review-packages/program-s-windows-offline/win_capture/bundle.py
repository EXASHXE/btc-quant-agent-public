"""Atomic Windows-safe bundle storage, exclusive locking, and hash-chained SQLite ledger."""

from __future__ import annotations

from contextlib import closing
import errno
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from .transport import CaptureError


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_digest(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def ensure_no_symlink_components(path: Path) -> Path:
    if ".." in path.parts:
        raise CaptureError("WIN_PATH_TRAVERSAL")
    resolved_parts = path.absolute()
    for p in (resolved_parts, *resolved_parts.parents):
        if p.exists() and os.name == "nt":
            import ctypes

            flags = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            if flags == 0xFFFFFFFF or flags & 0x400:
                raise CaptureError("WIN_REPARSE_POINT_FORBIDDEN")
        if p.exists() and p.is_symlink():
            raise CaptureError(f"WIN_SYMLINK_PATH_FORBIDDEN:{p}")
    return resolved_parts


def write_atomic_bytes(path: Path, data: bytes) -> None:
    """Create temp file in target directory, fsync bytes, and atomically replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_no_symlink_components(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=".part", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def acquire_exclusive_lock(lock_path: Path, *, create_new: bool = False):
    """Acquire non-blocking exclusive mandatory lock (requires native NTFS on Windows)."""
    ensure_no_symlink_components(lock_path.parent)
    flags = os.O_RDWR | os.O_CREAT | (os.O_EXCL if create_new else 0)
    try:
        fd = os.open(str(lock_path), flags, 0o600)
    except OSError as exc:
        raise CaptureError(f"WIN_EXCLUSIVE_LOCK_CONFLICT:{exc}") from exc
    handle = os.fdopen(fd, "a+b")
    try:
        if create_new:
            handle.write(f"{os.getpid()}\n".encode("ascii"))
            handle.flush()
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                setattr(handle, "_msvcrt_locked", True)
            except OSError as exc:
                if exc.errno == errno.EINVAL:
                    raise CaptureError("WIN_FILESYSTEM_LOCKING_UNSUPPORTED_USE_LOCAL_WINDOWS_NTFS") from exc
                raise
        else:  # pragma: no cover
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            setattr(handle, "_msvcrt_locked", True)
    except CaptureError:
        handle.close()
        raise
    except OSError as exc:
        handle.close()
        raise CaptureError(f"WIN_EXCLUSIVE_LOCK_CONFLICT:{exc}") from exc
    return handle


def release_exclusive_lock(handle) -> None:
    try:
        if getattr(handle, "_msvcrt_locked", False):
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class BundleLedger:
    """Append-only hash-chained SQLite ledger (journal_mode=DELETE, synchronous=FULL)."""

    def __init__(self, directory: Path, *, evidence_class: str):
        self.directory = ensure_no_symlink_components(directory)
        if os.name == "nt":
            verify_ntfs(self.directory.parent)
        if self.directory.exists():
            raise CaptureError("WIN_OUTPUT_DIR_MUST_BE_UNUSED")
        self.directory.mkdir(parents=False, exist_ok=False)
        (self.directory / "responses").mkdir(parents=False, exist_ok=False)
        self.lock_handle = acquire_exclusive_lock(self.directory / "capture.lock", create_new=True)
        self.db_path = self.directory / "ledger.sqlite"
        self.evidence_class = evidence_class
        try:
            with closing(self._connect()) as db:
                with db:
                    db.execute(
                        """
                        CREATE TABLE events (
                            seq INTEGER PRIMARY KEY AUTOINCREMENT,
                            kind TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            prev_sha256 TEXT NOT NULL,
                            entry_sha256 TEXT NOT NULL
                        )
                        """
                    )
            self.head_sha256 = "0" * 64
            self.append_event(
                "LEDGER_INIT",
                {
                    "evidence_class": evidence_class,
                    "filesystem": verify_ntfs(self.directory)
                    if os.name == "nt"
                    else {"kind": "LINUX_SYNTHETIC_QA_ONLY"},
                    "cache_policy": {
                        "max_hours": 24,
                        "automatic_cleanup": False,
                        "boot_change": "EXPIRED_OR_UNKNOWN_BLOCK_USE",
                        "copies": "Owner exact-path inventory required",
                    },
                },
            )
        except BaseException:
            release_exclusive_lock(self.lock_handle)
            raise

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def append_event(self, kind: str, payload: dict[str, Any]) -> str:
        payload_bytes = canonical_bytes(payload).decode("utf-8")
        entry_sha256 = canonical_digest({"kind": kind, "payload": payload, "prev_sha256": self.head_sha256})
        with closing(self._connect()) as db:
            with db:
                db.execute(
                    "INSERT INTO events(kind, payload_json, prev_sha256, entry_sha256) VALUES(?,?,?,?)",
                    (kind, payload_bytes, self.head_sha256, entry_sha256),
                )
        self.head_sha256 = entry_sha256
        return entry_sha256

    def persist_response(
        self, session: str, ordinal: int, wire: dict[str, Any], durable_sample: dict[str, Any]
    ) -> dict[str, Any]:
        rel = f"responses/{ordinal:03d}_{wire['body_sha256'][:12]}.bin"
        raw_path = self.directory / rel
        if raw_path.exists():
            raise CaptureError("WIN_DUPLICATE_RESPONSE_FILE")
        write_atomic_bytes(raw_path, wire["raw_bytes"])
        if callable(durable_sample):
            durable_sample = durable_sample()
        record = {
            "session": session,
            "ordinal": ordinal,
            "host": wire["host"],
            "route": wire["route"],
            "params": wire["params"],
            "status": wire["status"],
            "headers": wire["headers"],
            "response_complete": wire["response_complete"],
            "body_sha256": wire["body_sha256"],
            "raw_path": rel,
            "byte_len": len(wire["raw_bytes"]),
            "request_sample": wire["request_sample"],
            "receive_sample": wire["receive_sample"],
            "durable_sample": durable_sample,
            "durable_sample_semantics": "POST_RAW_FSYNC_ACK",
            "tls": wire["tls"],
        }
        self.append_event("HTTP_RESPONSE", record)
        return record

    def close(self) -> None:
        release_exclusive_lock(self.lock_handle)


def verify_ntfs(path):
    import ctypes

    if os.name != "nt":
        raise CaptureError("WINDOWS_NATIVE_FIXED_NTFS_REQUIRED")
    p = ensure_no_symlink_components(Path(path))
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    volume = ctypes.create_unicode_buffer(32768)
    fs = ctypes.create_unicode_buffer(64)
    if not k.GetVolumePathNameW(str(p), volume, len(volume)):
        raise CaptureError("WIN_VOLUME_PATH_FAILED")
    if k.GetDriveTypeW(volume.value) != 3:
        raise CaptureError("WIN_FIXED_VOLUME_REQUIRED")
    if (
        not k.GetVolumeInformationW(volume.value, None, 0, None, None, None, fs, len(fs))
        or fs.value != "NTFS"
    ):
        raise CaptureError("WIN_NTFS_REQUIRED")
    return {
        "kind": "FIXED_NTFS",
        "volume": volume.value,
        "filesystem": fs.value,
        "checked_by": "Windows_GetVolumeInformation_GetDriveType",
    }
