"""Durable, exact ownership of Testnet protective stops."""

from __future__ import annotations

import hashlib
import json
import math
import re
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
    confirmed_at_ms: int


def parse_protective_exchange_id(raw_stop: Any) -> str:
    """Parse provider ID aliases without coercing invalid JSON values into authority."""
    if not isinstance(raw_stop, dict):
        raise ExecutionBlocked("PROTECTION_ORDER_ID_INVALID")
    identifiers = []
    for field in ("algoId", "orderId"):
        if field not in raw_stop:
            continue
        value = raw_stop[field]
        if type(value) is int and value > 0:
            identifier = str(value)
        elif (isinstance(value, str) and value.lower() not in {"none", "null"}
              and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) and value != "0"):
            identifier = value
        else:
            raise ExecutionBlocked("PROTECTION_ORDER_ID_INVALID")
        identifiers.append(identifier)
    if not identifiers:
        raise ExecutionBlocked("PROTECTION_ORDER_ID_INVALID")
    if len(set(identifiers)) != 1:
        raise ExecutionBlocked("PROTECTION_ORDER_ID_CONFLICT")
    return identifiers[0]


def parse_protective_bool(value: Any) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ExecutionBlocked("PROTECTION_CONTRACT_MISMATCH")


def protective_field(raw: dict[str, Any], primary: str, alias: str) -> Any:
    """Missing or contradictory aliases are never confirmation defaults."""
    if primary in raw and alias in raw and raw[primary] != raw[alias]:
        raise ExecutionBlocked("PROTECTION_CONTRACT_MISMATCH")
    if primary in raw:
        return raw[primary]
    if alias in raw:
        return raw[alias]
    raise ExecutionBlocked("PROTECTION_CONTRACT_MISMATCH")


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
            db.execute("BEGIN IMMEDIATE")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(live_protection_owners)")}
            if "confirmed_at_ms" not in columns:
                db.execute("ALTER TABLE live_protection_owners ADD COLUMN confirmed_at_ms INTEGER NOT NULL DEFAULT 0")
                # Pre-R4 ACTIVE meant reservation/POST acceptance, not confirmed installation.
                db.execute("UPDATE live_protection_owners SET status=CASE WHEN protective_client_id IS NULL "
                           "THEN 'RESERVED' ELSE 'PENDING_CONFIRMATION' END WHERE status='ACTIVE'")
            db.execute("DROP INDEX IF EXISTS idx_active_protection_symbol")
            db.execute("DROP INDEX IF EXISTS idx_risk_protection_symbol")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_protection_symbol "
                       "ON live_protection_owners(symbol, position_side) "
                       "WHERE status IN ('RESERVED','PENDING_CONFIRMATION','ACTIVE','CANCEL_PENDING','TERMINAL_CONFIRMED')")

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
                "WHERE symbol=? AND position_side='BOTH' AND status IN ('RESERVED','PENDING_CONFIRMATION','ACTIVE','CANCEL_PENDING','TERMINAL_CONFIRMED') AND owner_key!=?",
                (intent.symbol, key),
            ).fetchone()
            if conflicting is not None:
                raise ExecutionBlocked("PROTECTION_OWNER_CONFLICT")
            row = db.execute("SELECT * FROM live_protection_owners WHERE owner_key=?", (key,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO live_protection_owners "
                    "(owner_key,intent_id,intent_hash,symbol,position_side,status,created_at_ms,updated_at_ms) "
                    "VALUES (?,?,?,?,?,'RESERVED',?,?)",
                    (key, intent.intent_id, intent.intent_hash, intent.symbol, "BOTH", now_ms, now_ms),
                )
            else:
                owner = self._owner(row)
                if (owner.intent_id, owner.intent_hash, owner.symbol, owner.position_side) != (
                    intent.intent_id, intent.intent_hash, intent.symbol, "BOTH"
                ):
                    raise ExecutionBlocked("PROTECTION_OWNER_IDENTITY_MISMATCH")
                if owner.status == "RELEASED":
                    raise ExecutionBlocked("PROTECTION_OWNER_RELEASED")
            row = db.execute("SELECT * FROM live_protection_owners WHERE owner_key=?", (key,)).fetchone()
            return self._owner(row)

    def next_client_id(self, intent: Any, now_ms: int, quantity: float = 0) -> str:
        owner = self.get_owner(intent)
        if owner is None or owner.status not in {"RESERVED", "PENDING_CONFIRMATION", "ACTIVE"}:
            raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
        if owner.protective_client_id is not None:
            raise ExecutionBlocked("PROTECTION_STOP_UNCERTAIN")
        generation = owner.generation + 1
        digest = hashlib.sha256(f"{owner.owner_key}:{generation}".encode()).hexdigest()
        client_id = f"bqa_stop_{digest[:26]}"
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT generation,protective_client_id FROM live_protection_owners WHERE owner_key=? AND status='RESERVED'",
                             (owner.owner_key,)).fetchone()
            if row is None or row["generation"] != owner.generation or row["protective_client_id"] is not None:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")
            db.execute(
                "UPDATE live_protection_owners SET generation=?,protective_client_id=?,exchange_id=NULL,"
                "status='PENDING_CONFIRMATION',quantity=?,confirmed_at_ms=0,updated_at_ms=? WHERE owner_key=?",
                (generation, client_id, quantity, now_ms, owner.owner_key),
            )
        return client_id

    def pending_exchange_id(self, intent: Any, client_id: str, exchange_id: str, now_ms: int) -> None:
        parse_protective_exchange_id({"algoId": exchange_id})
        with connection(self.path) as db:
            changed = db.execute(
                "UPDATE live_protection_owners SET exchange_id=?,updated_at_ms=? "
                "WHERE owner_key=? AND intent_id=? AND intent_hash=? "
                "AND status='PENDING_CONFIRMATION' AND protective_client_id=? "
                "AND (exchange_id IS NULL OR exchange_id=?)",
                (exchange_id, now_ms, _owner_key(intent), intent.intent_id,
                 intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")

    def begin_cancellation(self, intent: Any, client_id: str, exchange_id: str, now_ms: int) -> None:
        """Persist uncertainty before cancel can remove exchange-side protection."""
        with connection(self.path) as db:
            changed = db.execute(
                "UPDATE live_protection_owners SET status='CANCEL_PENDING',exchange_id=?,confirmed_at_ms=0,updated_at_ms=? "
                "WHERE owner_key=? AND intent_id=? AND intent_hash=? "
                "AND status IN ('ACTIVE','PENDING_CONFIRMATION') AND protective_client_id=? "
                "AND (exchange_id=? OR exchange_id IS NULL)",
                (exchange_id, now_ms, _owner_key(intent), intent.intent_id, intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")

    def record_stop(self, intent: Any, client_id: str, exchange_id: str, quantity: float, now_ms: int,
                    *, confirmed_order: dict[str, Any] | None = None) -> None:
        parse_protective_exchange_id({"algoId": exchange_id})
        if not math.isfinite(quantity) or quantity <= 0:
            raise ExecutionBlocked("PROTECTION_STOP_INVALID")
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE live_protection_owners SET exchange_id=?,quantity=?,status='ACTIVE',confirmed_at_ms=?,updated_at_ms=? "
                "WHERE owner_key=? AND intent_id=? AND intent_hash=? AND status IN ('ACTIVE','PENDING_CONFIRMATION') "
                "AND protective_client_id=? AND (exchange_id IS NULL OR exchange_id=?)",
                (exchange_id, quantity, now_ms, now_ms, _owner_key(intent), intent.intent_id,
                 intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")
            if confirmed_order is not None:
                # Owner confirmation and local protective order succeed or roll back together.
                row = db.execute("SELECT intent_id,client_order_id FROM live_execution_orders WHERE order_id=?",
                                 (exchange_id,)).fetchone()
                if row is not None and (row["intent_id"], row["client_order_id"]) != (intent.intent_id, client_id):
                    raise ExecutionBlocked("PROTECTION_ORDER_OWNER_CONFLICT")
                db.execute(
                    "INSERT INTO live_execution_orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(order_id) DO UPDATE SET requested_qty=excluded.requested_qty, "
                    "status=excluded.status,payload=excluded.payload,receipt_time_ms=excluded.receipt_time_ms",
                    (exchange_id, intent.intent_id, client_id, intent.symbol,
                     "SELL" if intent.side == "BUY" else "BUY", "NEW", quantity, 0.0, 0.0,
                     intent.stop_loss, 1, 1, now_ms, now_ms, json.dumps(confirmed_order)),
                )

    def confirm_terminal(self, intent: Any, client_id: str, exchange_id: str,
                         status: str, now_ms: int) -> None:
        if status not in {"CANCELED", "EXPIRED", "NOT_FOUND"}:
            raise ExecutionBlocked("PROTECTION_TERMINAL_INVALID")
        parse_protective_exchange_id({"algoId": exchange_id})
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE live_protection_owners SET status='TERMINAL_CONFIRMED',confirmed_at_ms=?,updated_at_ms=? "
                "WHERE owner_key=? AND intent_id=? AND intent_hash=? "
                "AND status IN ('ACTIVE','PENDING_CONFIRMATION','CANCEL_PENDING') "
                "AND protective_client_id=? AND exchange_id=?",
                (now_ms, now_ms, _owner_key(intent), intent.intent_id, intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")
            db.execute("UPDATE live_execution_orders SET status=? WHERE order_id=? AND intent_id=? "
                       "AND client_order_id=? AND is_protective=1",
                       (status, exchange_id, intent.intent_id, client_id))

    def clear_stop(self, intent: Any, client_id: str, exchange_id: str, now_ms: int,
                   *, cancelled_order: bool = False) -> None:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE live_protection_owners SET protective_client_id=NULL,exchange_id=NULL,"
                "quantity=0,status='RESERVED',confirmed_at_ms=0,updated_at_ms=? WHERE owner_key=? AND intent_id=? AND intent_hash=? "
                "AND status='TERMINAL_CONFIRMED' AND protective_client_id=? AND exchange_id=?",
                (now_ms, _owner_key(intent), intent.intent_id, intent.intent_hash, client_id, exchange_id),
            )
            if changed.rowcount != 1:
                raise ExecutionBlocked("PROTECTION_OWNER_CHANGED")
            if cancelled_order:
                db.execute("UPDATE live_execution_orders SET status='CANCELED' WHERE order_id=? AND intent_id=? "
                           "AND client_order_id=? AND is_protective=1",
                           (exchange_id, intent.intent_id, client_id))

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
            current = db.execute("SELECT status,protective_client_id,exchange_id FROM live_protection_owners "
                                 "WHERE owner_key=?", (owner.owner_key,)).fetchone()
            if current["status"] != "TERMINAL_CONFIRMED" and (
                current["protective_client_id"] is not None or current["exchange_id"] is not None
                or current["status"] not in {"RESERVED", "RELEASED"}
            ):
                raise ExecutionBlocked("PROTECTION_REMOTE_STATE_UNCERTAIN")
            db.execute("UPDATE live_protection_owners SET status='RELEASED',exchange_id=NULL,"
                       "protective_client_id=NULL,quantity=0,updated_at_ms=? WHERE owner_key=?", (now_ms, owner.owner_key))
