"""Append-only offline decisions; duplicate replay is idempotent, revisions fail closed."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .core import fingerprint
from .swing import AdvisorySnapshot


class DecisionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError("UNTRUSTED_STORE_PATH")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS swing_decisions(
                sequence INTEGER PRIMARY KEY, symbol TEXT NOT NULL, trigger_ms INTEGER NOT NULL,
                decision_ms INTEGER NOT NULL, digest TEXT NOT NULL, value TEXT NOT NULL,
                UNIQUE(symbol, trigger_ms))""")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def append(self, snapshot: AdvisorySnapshot) -> str:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self.append_in_transaction(db, snapshot)

    @staticmethod
    def append_in_transaction(db: sqlite3.Connection, snapshot: AdvisorySnapshot) -> str:
        """Share the existing immutable append with the RC's receipt/decision transaction."""
        # Validate again at the persistence boundary, including model_copy/model_construct callers.
        snapshot = AdvisorySnapshot.model_validate_json(snapshot.model_dump_json())
        encoded = snapshot.model_dump_json()
        digest = fingerprint(json.loads(encoded))
        existing = db.execute(
                "SELECT digest FROM swing_decisions WHERE symbol=? AND trigger_ms=?",
                (snapshot.symbol, snapshot.trigger_close_ms),
            ).fetchone()
        if existing:
            if existing[0] != digest:
                raise ValueError("REVISION_REQUIRES_EXPLICIT_LT_B_POLICY")
            return digest
        latest = db.execute(
                "SELECT MAX(trigger_ms), MAX(decision_ms) FROM swing_decisions WHERE symbol=?",
                (snapshot.symbol,),
            ).fetchone()
        if latest[0] is not None and (snapshot.trigger_close_ms <= latest[0]
                                         or snapshot.decision_ms < latest[1]):
            raise ValueError("STALE_OR_REGRESSING_DECISION")
        db.execute(
                "INSERT INTO swing_decisions(symbol,trigger_ms,decision_ms,digest,value) VALUES (?,?,?,?,?)",
                (snapshot.symbol, snapshot.trigger_close_ms, snapshot.decision_ms, digest, encoded),
            )
        return digest

    def latest(self, symbol: str) -> AdvisorySnapshot | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT digest,value FROM swing_decisions WHERE symbol=? ORDER BY sequence DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        if row is None:
            return None
        if fingerprint(json.loads(row[1])) != row[0]:
            raise ValueError("PERSISTED_DECISION_DIGEST_MISMATCH")
        return AdvisorySnapshot.model_validate_json(row[1])
