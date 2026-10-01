"""Shared durable SQLite boundary for concurrent Live V1 services."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connection(path: str | Path, busy_timeout_ms: int = 10000) -> Iterator[sqlite3.Connection]:
    if busy_timeout_ms <= 0 or str(path) == ":memory:":
        raise ValueError("Live V1 requires durable storage and a positive busy timeout")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000)
    db.row_factory = sqlite3.Row
    try:
        db.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        if (
            db.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
            and db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal"
        ):
            raise RuntimeError("LIVE_WAL_REQUIRED")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
