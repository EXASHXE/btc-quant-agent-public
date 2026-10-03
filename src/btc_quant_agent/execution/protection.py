"""Durable, exact ownership of Testnet protective stops."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..live_db import connection
from .guard import ExecutionBlocked


@dataclass(frozen=True)
class ProtectionOwner:
    owner_key: str
    intent_id: str
    intent_hash: str
    symbol: str
    position_side: str
    protective_client_id: str | None
    exchange_id: str | None
    status: str
    quantity: float
    generation: int


def _owner_key(intent: Any) -> str:
    raw = f"{intent.intent_hash}:{intent.symbol}:{intent.side}:BOTH:STOP:1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ProtectionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_protection_owners (
                    owner_key TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    intent_hash TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    position_side TEXT NOT NULL,
                    protective_client_id TEXT UNIQUE,
                    exchange_id TEXT,
                    status TEXT NOT NULL,
                    quantity REAL NOT NULL DEFAULT 0,
                    generation INTEGER NOT NULL DEFAULT 0,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_active_protection_symbol
                    ON live_protection_owners(symbol, position_side)
                    WHERE status = 'ACTIVE';
            """)

    @staticmethod
    def _owner(row: Any) -> ProtectionOwner:
        return ProtectionOwner(**{key: row[key] for key in ProtectionOwner.__dataclass_fields__})

    def get_owner(self, intent: Any) -> ProtectionOwner | None:
        with connection(self.path) as db:
            row = db.execute("SELECT * FROM live_protection_owners WHERE owner_key=?",
                             (_owner_key(intent),)).fetchone()
        if row is None:
            return None
        owner = self._owner(row)
        if (owner.intent_id, owner.intent_hash, owner.symbol, owner.position_side) != (
            intent.intent_id, intent.intent_hash, intent.symbol, "BOTH"
        ):
            raise ExecutionBlocked("PROTECTION_OWNER_IDENTITY_MISMATCH")
        return owner

    def reserve_owner(self, intent: Any, now_ms: int) -> ProtectionOwner:
        key = _owner_key(intent)
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            conflicting = db.execute(
                "SELECT owner_key FROM live_protection_owners "
                "WHERE symbol=? AND position_side='BOTH' AND status='ACTIVE' AND owner_key!=?",
                (intent.symbol, key),
            ).fetchone()
            if conflicting is not None:
                raise ExecutionBlocked("PROTECTION_OWNER_CONFLICT")
            row = db.execute("SELECT * FROM live_protection_owners WHERE owner_key=?", (key,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO live_protection_owners "
                    "(owner_key,intent_id,intent_hash,symbol,position_side,status,created_at_ms,updated_at_ms) "
                    "VALUES (?,?,?,?,?,'ACTIVE',?,?)",
                    (key, intent.intent_id, intent.intent_hash, intent.symbol, "BOTH", now_ms, now_ms),
                )
            else:
                owner = self._owner(row)
                if (owner.intent_id, owner.intent_hash, owner.symbol, owner.position_side) != (
                    intent.intent_id, intent.intent_hash, intent.symbol, "BOTH"
                ):
                    raise ExecutionBlocked("PROTECTION_OWNER_IDENTITY_MISMATCH")
                db.execute("UPDATE live_protection_owners SET status='ACTIVE',updated_at_ms=? WHERE owner_key=?",
                           (now_ms, key))
            row = db.execute("SELECT * FROM live_protection_owners WHERE owner_key=?", (key,)).fetchone()
            return self._owner(row)

    def next_client_id(self, intent: Any, now_ms: int) -> str:
        owner = self.get_owner(intent)
        if owner is None or owner.status != "ACTIVE":
            raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
        if owner.protective_client_id is not None:
            raise ExecutionBlocked("PROTECTION_STOP_UNCERTAIN")
        generation = owner.generation + 1
        digest = hashlib.sha256(f"{owner.owner_key}:{generation}".encode()).hexdigest()
        client_id = f"bqa_stop_{digest[:26]}"
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT generation,protective_client_id FROM live_protection_owners WHERE owner_key=? AND status='ACTIVE'",
                             (owner.owner_key,)).fetchone()
            if row is None or row["generation"] != owner.generation or row["protective_client_id"] is not None:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")
            db.execute(
                "UPDATE live_protection_owners SET generation=?,protective_client_id=?,exchange_id=NULL,"
                "status='ACTIVE',updated_at_ms=? WHERE owner_key=?",
                (generation, client_id, now_ms, owner.owner_key),
            )
        return client_id

    def record_stop(self, intent: Any, client_id: str, exchange_id: str, quantity: float, now_ms: int) -> None:
        if not exchange_id or quantity <= 0:
            raise ExecutionBlocked("PROTECTION_STOP_INVALID")
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE live_protection_owners SET exchange_id=?,quantity=?,updated_at_ms=? "
                "WHERE owner_key=? AND intent_id=? AND intent_hash=? AND status='ACTIVE' "
                "AND protective_client_id=? AND (exchange_id IS NULL OR exchange_id=?)",
                (exchange_id, quantity, now_ms, _owner_key(intent), intent.intent_id,
                 intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")

    def clear_stop(self, intent: Any, client_id: str, exchange_id: str, now_ms: int) -> None:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE live_protection_owners SET protective_client_id=NULL,exchange_id=NULL,"
                "quantity=0,updated_at_ms=? WHERE owner_key=? AND intent_id=? AND intent_hash=? "
                "AND status='ACTIVE' AND protective_client_id=? "
                "AND (exchange_id=? OR exchange_id IS NULL)",
                (now_ms, _owner_key(intent), intent.intent_id, intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")

    def release_flat(self, intent: Any, now_ms: int) -> None:
        owner = self.get_owner(intent)
        if owner is None:
            return
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute(
                "SELECT 1 FROM live_execution_orders WHERE intent_id=? AND is_protective=0 "
                "AND status IN ('SUBMITTING','UNKNOWN','NEW','PARTIALLY_FILLED') LIMIT 1",
                (intent.intent_id,),
            ).fetchone()
            if pending is not None:
                return
            db.execute("UPDATE live_protection_owners SET status='RELEASED',exchange_id=NULL,"
                       "quantity=0,updated_at_ms=? WHERE owner_key=?", (now_ms, owner.owner_key))
