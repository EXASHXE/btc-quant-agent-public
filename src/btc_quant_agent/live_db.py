"""Shared durable SQLite boundary for concurrent Live V1 services."""

from __future__ import annotations

import fcntl
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, Self


class SerializedInitializer:
    """Bounded repository-local serialized initializer boundary.

    Enforces that exactly one initializer performs schema initialization
    or migration for one DB path at a time. Concurrently contending cold-start
    processes/threads are mechanically serialized or fail closed upon timeout.
    """

    _registry_lock = threading.Lock()
    _instances: ClassVar[dict[str, SerializedInitializer]] = {}

    @classmethod
    def get(cls, path: str | Path) -> SerializedInitializer:
        canon = str(Path(path).resolve())
        with cls._registry_lock:
            if canon not in cls._instances:
                cls._instances[canon] = cls(canon)
            return cls._instances[canon]

    def __init__(self, canonical_path: str) -> None:
        self.path = canonical_path
        self.lock_path = Path(canonical_path).with_suffix(Path(canonical_path).suffix + ".init.lock")
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._owner_tid: int | None = None
        self._fd: int | None = None

    def acquire(self, timeout_seconds: float = 30.0) -> bool:
        if timeout_seconds <= 0:
            raise ValueError("Initializer lock timeout must be positive")
        deadline = time.monotonic() + timeout_seconds
        acquired_thread = self._thread_lock.acquire(timeout=max(0.01, timeout_seconds))
        if not acquired_thread:
            raise TimeoutError(f"INITIALIZER_THREAD_LOCK_TIMEOUT: {self.path}")

        cur_tid = threading.get_ident()
        if self._owner_tid == cur_tid:
            self._depth += 1
            return True

        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o666)
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        os.close(fd)
                        raise TimeoutError(f"INITIALIZER_PROCESS_LOCK_TIMEOUT: {self.path}") from None
                    time.sleep(0.01)

            self._fd = fd
            self._owner_tid = cur_tid
            self._depth = 1
            return True
        except Exception:
            self._thread_lock.release()
            raise

    def release(self) -> None:
        cur_tid = threading.get_ident()
        if self._owner_tid != cur_tid:
            raise RuntimeError("Current thread does not own initializer lock")
        self._depth -= 1
        if self._depth == 0:
            fd = self._fd
            self._fd = None
            self._owner_tid = None
            try:
                if fd is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                if fd is not None:
                    os.close(fd)
        self._thread_lock.release()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.release()


@contextmanager
def serialized_initializer(path: str | Path, timeout_seconds: float = 30.0) -> Iterator[SerializedInitializer]:
    """Context manager for the bounded single-runtime initializer boundary."""
    initializer = SerializedInitializer.get(path)
    initializer.acquire(timeout_seconds=timeout_seconds)
    try:
        yield initializer
    finally:
        initializer.release()


@contextmanager
def connection(path: str | Path, busy_timeout_ms: int = 10000) -> Iterator[sqlite3.Connection]:
    if busy_timeout_ms <= 0 or str(path) == ":memory:":
        raise ValueError("Live V1 requires durable storage and a positive busy timeout")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000)
    db.row_factory = sqlite3.Row
    try:
        db.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        deadline = time.monotonic() + (busy_timeout_ms / 1000.0)
        while True:
            try:
                current_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
                if current_mode == "wal":
                    break
                new_mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if new_mode == "wal":
                    break
                raise RuntimeError("LIVE_WAL_REQUIRED")
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() and time.monotonic() < deadline:
                    time.sleep(0.02)
                    continue
                raise
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA recursive_triggers=ON")
        if db.execute("PRAGMA recursive_triggers").fetchone()[0] != 1:
            raise RuntimeError("LIVE_RECURSIVE_TRIGGERS_REQUIRED")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
