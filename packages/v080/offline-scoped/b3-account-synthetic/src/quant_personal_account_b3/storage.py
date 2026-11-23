"""Separate B3 local private SQLite store and append-only B3 overlay journal."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    ACCOUNT_REALITY_BANNER,
    CONNECTION_MODE_FIXTURE,
    EVIDENCE_CLASS_SYNTHETIC,
    LAYER3_STATUS,
    SCHEMA_CHECKPOINT,
    SCHEMA_JOURNAL_EVENT,
    SCHEMA_MANUAL_LINK,
    AccountB3Error,
    check,
    digest,
    encode,
    parse_int,
    parse_symbol,
)
from .normalize import (
    EndpointCoverage,
    NormalizedAccount,
    NormalizedAlgoOrder,
    NormalizedFill,
    NormalizedIncome,
    NormalizedOrder,
    PrivateAccountSnapshot,
    normalize_account,
    normalize_algo_orders,
    normalize_fills,
    normalize_income,
    normalize_orders,
    normalize_positions,
)

PRIVATE_STORE_APP_ID = 0x51423341  # 'QB3A'
OVERLAY_JOURNAL_APP_ID = 0x5142334A  # 'QB3J'

STORAGE_PRIVACY_POLICY = {
    "storage_scope": "LOCAL_PRIVATE_ONLY_SEPARATE_FROM_B1_B2",
    "filesystem_dir_mode": "0o700",
    "filesystem_file_mode": "0o600",
    "encryption_at_rest": "NOT_IMPLEMENTED_IN_SQLITE_RELY_ON_OS_FULL_DISK_AND_BACKUP_ENCRYPTION",
    "retention_policy": "OWNER_CONTROLLED_NO_AUTOMATIC_24H_PURGE",
    "evidence_class": EVIDENCE_CLASS_SYNTHETIC,
    "connection_mode": CONNECTION_MODE_FIXTURE,
    "account_reality_banner": ACCOUNT_REALITY_BANNER,
    "layer3_trade_execution": LAYER3_STATUS,
}

MANUAL_TARGET_TYPES = frozenset({"ORDER", "ALGO_ORDER", "TRADE"})

PRIVATE_STORE_SCHEMA = (
    """CREATE TABLE store_identity (
        schema_version INTEGER NOT NULL,
        evidence_class TEXT NOT NULL,
        connection_mode TEXT NOT NULL,
        policy_json TEXT NOT NULL
    )""",
    """CREATE TABLE snapshots (
        snapshot_id TEXT PRIMARY KEY,
        as_of_venue_ms INTEGER NOT NULL,
        symbol_scope TEXT,
        overall_status TEXT NOT NULL,
        snapshot_mode TEXT NOT NULL,
        evidence_class TEXT NOT NULL,
        connection_mode TEXT NOT NULL,
        recorded_wall_ms INTEGER NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL
    )""",
    """CREATE TABLE endpoint_coverage (
        snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
        endpoint TEXT NOT NULL,
        symbol TEXT NOT NULL,
        status TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY (snapshot_id, endpoint, symbol)
    )""",
    """CREATE TABLE accounts (
        snapshot_id TEXT PRIMARY KEY REFERENCES snapshots(snapshot_id),
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL
    )""",
    """CREATE TABLE positions (
        snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
        symbol TEXT NOT NULL,
        position_side TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY (snapshot_id, symbol, position_side)
    )""",
    """CREATE TABLE ordinary_orders (
        symbol TEXT NOT NULL,
        order_id INTEGER NOT NULL,
        source_endpoint TEXT NOT NULL,
        update_time_ms INTEGER NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL,
        PRIMARY KEY (symbol, order_id, source_endpoint)
    )""",
    """CREATE TABLE algo_orders (
        symbol TEXT NOT NULL,
        algo_id INTEGER NOT NULL,
        source_endpoint TEXT NOT NULL,
        update_time_ms INTEGER NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL,
        PRIMARY KEY (symbol, algo_id, source_endpoint)
    )""",
    """CREATE TABLE fills (
        symbol TEXT NOT NULL,
        trade_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        trade_time_ms INTEGER NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL,
        PRIMARY KEY (symbol, trade_id)
    )""",
    """CREATE TABLE income_rows (
        tran_id TEXT NOT NULL,
        income_type TEXT NOT NULL,
        asset TEXT NOT NULL,
        time_ms INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL,
        PRIMARY KEY (tran_id, income_type, asset, time_ms)
    )""",
    """CREATE TABLE pagination_checkpoints (
        endpoint TEXT NOT NULL,
        symbol TEXT NOT NULL,
        window_start_ms INTEGER NOT NULL,
        window_end_ms INTEGER NOT NULL,
        schema_version TEXT NOT NULL,
        cursor_type TEXT NOT NULL,
        cursor_value TEXT,
        last_accepted_id TEXT,
        last_accepted_time_ms INTEGER,
        pages_completed INTEGER NOT NULL,
        status TEXT NOT NULL,
        gap_windows_json TEXT NOT NULL,
        retention_warnings_json TEXT NOT NULL,
        error_code TEXT,
        updated_wall_ms INTEGER NOT NULL,
        PRIMARY KEY (endpoint, symbol, window_start_ms, window_end_ms, schema_version)
    )""",
    """CREATE TABLE manual_associations (
        operator_id TEXT PRIMARY KEY,
        association_id TEXT NOT NULL UNIQUE,
        b2_episode_id TEXT NOT NULL,
        b2_card_id TEXT,
        symbol TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        owner_reported_venue_ms INTEGER NOT NULL,
        recorded_wall_ms INTEGER NOT NULL,
        note TEXT NOT NULL,
        evidence TEXT NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL
    )""",
)

OVERLAY_JOURNAL_SCHEMA = (
    """CREATE TABLE journal_identity (
        schema_version INTEGER NOT NULL,
        evidence_class TEXT NOT NULL,
        connection_mode TEXT NOT NULL,
        policy_json TEXT NOT NULL
    )""",
    """CREATE TABLE overlays (
        overlay_id TEXT PRIMARY KEY,
        b2_card_id TEXT NOT NULL,
        b2_episode_id TEXT,
        b2_card_sha256 TEXT NOT NULL,
        symbol TEXT NOT NULL,
        snapshot_id TEXT,
        market_setup_status TEXT NOT NULL,
        account_context_status TEXT NOT NULL,
        recorded_wall_ms INTEGER NOT NULL,
        payload TEXT NOT NULL,
        payload_sha TEXT NOT NULL
    )""",
    "CREATE INDEX overlays_by_card ON overlays(b2_card_id, recorded_wall_ms DESC)",
    "CREATE INDEX overlays_by_episode ON overlays(b2_episode_id, recorded_wall_ms DESC)",
    """CREATE TABLE overlay_events (
        seq INTEGER PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        overlay_id TEXT NOT NULL REFERENCES overlays(overlay_id),
        b2_card_id TEXT NOT NULL,
        b2_episode_id TEXT,
        kind TEXT NOT NULL,
        evidence TEXT NOT NULL,
        payload TEXT NOT NULL,
        prior_sha TEXT,
        sha TEXT NOT NULL
    )""",
)


def apply_restrictive_permissions(db_path: Path) -> dict[str, str]:
    """Apply restrictive 0o700 directory and 0o600 file permissions for private local storage."""
    parent = db_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass
    for suffix in ("", "-journal", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                pass
    dir_mode = oct(stat.S_IMODE(parent.stat().st_mode))
    file_mode = oct(stat.S_IMODE(db_path.stat().st_mode)) if db_path.exists() else "NOT_CREATED"
    return {"directory_mode": dir_mode, "file_mode": file_mode}


@contextmanager
def sqlite_connection(path: Path, *, write: bool) -> Iterator[sqlite3.Connection]:
    target = str(path) if write else path.as_uri() + "?mode=ro"
    conn = sqlite3.connect(target, uri=not write, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if write:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
        else:
            conn.execute("PRAGMA query_only=ON")
        yield conn
        if write:
            conn.commit()
    except BaseException:
        if write:
            conn.rollback()
        raise
    finally:
        conn.close()


@dataclass(frozen=True)
class PaginationCheckpoint:
    endpoint: str
    symbol: str
    window_start_ms: int
    window_end_ms: int
    schema_version: str
    cursor_type: str
    cursor_value: str | None
    last_accepted_id: str | None
    last_accepted_time_ms: int | None
    pages_completed: int
    status: str  # IN_PROGRESS | COMPLETE | PARTIAL | GAP | ERROR
    gap_windows: tuple[dict[str, Any], ...] = ()
    retention_warnings: tuple[str, ...] = ()
    error_code: str | None = None
    updated_wall_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_CHECKPOINT,
            "endpoint": self.endpoint,
            "symbol": self.symbol,
            "window_start_ms": self.window_start_ms,
            "window_end_ms": self.window_end_ms,
            "schema_version": self.schema_version,
            "cursor_type": self.cursor_type,
            "cursor_value": self.cursor_value,
            "last_accepted_id": self.last_accepted_id,
            "last_accepted_time_ms": self.last_accepted_time_ms,
            "pages_completed": self.pages_completed,
            "status": self.status,
            "gap_windows": list(self.gap_windows),
            "retention_warnings": list(self.retention_warnings),
            "error_code": self.error_code,
            "updated_wall_ms": self.updated_wall_ms,
        }


@dataclass(frozen=True)
class ManualAssociation:
    operator_id: str
    association_id: str
    b2_episode_id: str
    b2_card_id: str | None
    symbol: str
    target_type: str
    target_id: str
    owner_reported_venue_ms: int
    recorded_wall_ms: int
    note: str
    evidence: str = "OWNER_ENTERED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_MANUAL_LINK,
            "operator_id": self.operator_id,
            "association_id": self.association_id,
            "b2_episode_id": self.b2_episode_id,
            "b2_card_id": self.b2_card_id,
            "symbol": self.symbol,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "owner_reported_venue_ms": self.owner_reported_venue_ms,
            "recorded_wall_ms": self.recorded_wall_ms,
            "note": self.note,
            "evidence": self.evidence,
        }


class PrivateAccountStore:
    """Dedicated local B3 SQLite store for private snapshots, normalized records, checkpoints, and manual links."""

    def __init__(self, path: Path, *, create: bool = False) -> None:
        self.path = path.resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.path.parent, 0o700)
            except OSError:
                pass
        with sqlite_connection(self.path, write=create) as db:
            app_id = db.execute("PRAGMA application_id").fetchone()[0]
            if create and app_id == 0:
                existing = db.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                check(existing is None, "B3_PRIVATE_STORE_WRONG_SCHEMA", "Non-empty DB without B3 application_id")
                for stmt in PRIVATE_STORE_SCHEMA:
                    db.execute(stmt)
                for op in ("UPDATE", "DELETE"):
                    db.execute(
                        f"CREATE TRIGGER lock_manual_associations_{op} BEFORE {op} ON manual_associations "
                        "BEGIN SELECT RAISE(ABORT,'B3_OWNER_LINK_APPEND_ONLY'); END"
                    )
                    db.execute(
                        f"CREATE TRIGGER lock_store_identity_{op} BEFORE {op} ON store_identity "
                        "BEGIN SELECT RAISE(ABORT,'B3_IDENTITY_IMMUTABLE'); END"
                    )
                db.execute(f"PRAGMA application_id={PRIVATE_STORE_APP_ID}")
                db.execute("PRAGMA user_version=1")
                db.execute(
                    "INSERT INTO store_identity VALUES (?,?,?,?)",
                    (1, EVIDENCE_CLASS_SYNTHETIC, CONNECTION_MODE_FIXTURE, encode(STORAGE_PRIVACY_POLICY)),
                )
                app_id = PRIVATE_STORE_APP_ID
            version = db.execute("PRAGMA user_version").fetchone()[0]
            check(app_id == PRIVATE_STORE_APP_ID and version == 1, "B3_PRIVATE_STORE_WRONG_SCHEMA")
        if create:
            apply_restrictive_permissions(self.path)

    def permissions(self) -> dict[str, str]:
        parent_mode = oct(stat.S_IMODE(self.path.parent.stat().st_mode))
        file_mode = oct(stat.S_IMODE(self.path.stat().st_mode))
        return {"directory_mode": parent_mode, "file_mode": file_mode}

    def save_snapshot(
        self,
        snapshot: PrivateAccountSnapshot,
        *,
        before_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Persist a NON_ATOMIC snapshot and upsert all normalized rows transactionally."""
        payload_dict = snapshot.to_dict()
        payload_text = encode(payload_dict)
        payload_sha = digest(payload_dict)
        wall_ms = time.time_ns() // 1_000_000

        with sqlite_connection(self.path, write=True) as db:
            existing = db.execute(
                "SELECT payload_sha FROM snapshots WHERE snapshot_id=?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if existing is not None:
                check(existing["payload_sha"] == payload_sha, "B3_SNAPSHOT_DIGEST_CONFLICT")
                return payload_dict

            db.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot.snapshot_id,
                    snapshot.as_of_venue_ms,
                    snapshot.symbol_scope,
                    snapshot.overall_status,
                    snapshot.snapshot_mode,
                    EVIDENCE_CLASS_SYNTHETIC,
                    CONNECTION_MODE_FIXTURE,
                    wall_ms,
                    payload_text,
                    payload_sha,
                ),
            )
            for ep, cov in sorted(snapshot.endpoint_coverage.items()):
                db.execute(
                    "INSERT OR REPLACE INTO endpoint_coverage VALUES (?,?,?,?,?)",
                    (snapshot.snapshot_id, ep, cov.symbol or "", cov.status, encode(cov.to_dict())),
                )
            if snapshot.account is not None:
                acc_dict = snapshot.account.to_dict()
                db.execute(
                    "INSERT INTO accounts VALUES (?,?,?)",
                    (snapshot.snapshot_id, encode(acc_dict), digest(acc_dict)),
                )
            for pos in snapshot.positions:
                db.execute(
                    "INSERT OR REPLACE INTO positions VALUES (?,?,?,?)",
                    (snapshot.snapshot_id, pos.symbol, pos.position_side, encode(pos.to_dict())),
                )
            self._upsert_orders_tx(db, snapshot.open_orders)
            self._upsert_orders_tx(db, snapshot.all_orders)
            self._upsert_algo_orders_tx(db, snapshot.open_algo_orders)
            self._upsert_algo_orders_tx(db, snapshot.all_algo_orders)
            self._upsert_fills_tx(db, snapshot.fills)
            self._upsert_income_tx(db, snapshot.income_rows)
            if before_commit is not None:
                before_commit()
        apply_restrictive_permissions(self.path)
        return payload_dict

    @staticmethod
    def _upsert_orders_tx(db: sqlite3.Connection, orders: tuple[NormalizedOrder, ...]) -> None:
        for order in orders:
            data = order.to_dict()
            db.execute(
                """INSERT INTO ordinary_orders(symbol,order_id,source_endpoint,update_time_ms,payload,payload_sha)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(symbol,order_id,source_endpoint) DO UPDATE SET
                     update_time_ms=excluded.update_time_ms,
                     payload=excluded.payload,
                     payload_sha=excluded.payload_sha
                   WHERE excluded.update_time_ms >= ordinary_orders.update_time_ms""",
                (
                    order.symbol,
                    order.order_id,
                    order.source_endpoint,
                    order.update_time_ms or 0,
                    encode(data),
                    digest(data),
                ),
            )

    @staticmethod
    def _upsert_algo_orders_tx(db: sqlite3.Connection, orders: tuple[NormalizedAlgoOrder, ...]) -> None:
        for order in orders:
            data = order.to_dict()
            db.execute(
                """INSERT INTO algo_orders(symbol,algo_id,source_endpoint,update_time_ms,payload,payload_sha)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(symbol,algo_id,source_endpoint) DO UPDATE SET
                     update_time_ms=excluded.update_time_ms,
                     payload=excluded.payload,
                     payload_sha=excluded.payload_sha
                   WHERE excluded.update_time_ms >= algo_orders.update_time_ms""",
                (
                    order.symbol,
                    order.algo_id,
                    order.source_endpoint,
                    order.update_time_ms or 0,
                    encode(data),
                    digest(data),
                ),
            )

    @staticmethod
    def _upsert_fills_tx(db: sqlite3.Connection, fills: tuple[NormalizedFill, ...]) -> None:
        for fill in fills:
            data = fill.to_dict()
            sha = digest(data)
            existing = db.execute(
                "SELECT payload_sha FROM fills WHERE symbol=? AND trade_id=?",
                (fill.symbol, fill.trade_id),
            ).fetchone()
            if existing is not None:
                check(existing["payload_sha"] == sha, "FILL_CONFLICTING_DUPLICATE", f"{fill.symbol}:{fill.trade_id}")
                continue
            db.execute(
                "INSERT INTO fills VALUES (?,?,?,?,?,?)",
                (fill.symbol, fill.trade_id, fill.order_id, fill.trade_time_ms, encode(data), sha),
            )

    @staticmethod
    def _upsert_income_tx(db: sqlite3.Connection, rows: tuple[NormalizedIncome, ...]) -> None:
        for row in rows:
            data = row.to_dict()
            sha = digest(data)
            existing = db.execute(
                "SELECT payload_sha FROM income_rows WHERE tran_id=? AND income_type=? AND asset=? AND time_ms=?",
                (row.tran_id, row.income_type, row.asset, row.time_ms),
            ).fetchone()
            if existing is not None:
                check(existing["payload_sha"] == sha, "INCOME_CONFLICTING_DUPLICATE", row.tran_id)
                continue
            db.execute(
                "INSERT INTO income_rows VALUES (?,?,?,?,?,?,?)",
                (row.tran_id, row.income_type, row.asset, row.time_ms, row.symbol, encode(data), sha),
            )

    def commit_paginated_page(
        self,
        checkpoint: PaginationCheckpoint,
        *,
        orders: tuple[NormalizedOrder, ...] = (),
        algo_orders: tuple[NormalizedAlgoOrder, ...] = (),
        fills: tuple[NormalizedFill, ...] = (),
        income_rows: tuple[NormalizedIncome, ...] = (),
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        """Atomically persist one paginated page of records together with its checkpoint."""
        wall_ms = time.time_ns() // 1_000_000
        with sqlite_connection(self.path, write=True) as db:
            self._upsert_orders_tx(db, orders)
            self._upsert_algo_orders_tx(db, algo_orders)
            self._upsert_fills_tx(db, fills)
            self._upsert_income_tx(db, income_rows)
            db.execute(
                """INSERT INTO pagination_checkpoints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(endpoint,symbol,window_start_ms,window_end_ms,schema_version) DO UPDATE SET
                     cursor_type=excluded.cursor_type,
                     cursor_value=excluded.cursor_value,
                     last_accepted_id=excluded.last_accepted_id,
                     last_accepted_time_ms=excluded.last_accepted_time_ms,
                     pages_completed=excluded.pages_completed,
                     status=excluded.status,
                     gap_windows_json=excluded.gap_windows_json,
                     retention_warnings_json=excluded.retention_warnings_json,
                     error_code=excluded.error_code,
                     updated_wall_ms=excluded.updated_wall_ms""",
                (
                    checkpoint.endpoint,
                    checkpoint.symbol,
                    checkpoint.window_start_ms,
                    checkpoint.window_end_ms,
                    checkpoint.schema_version,
                    checkpoint.cursor_type,
                    checkpoint.cursor_value,
                    checkpoint.last_accepted_id,
                    checkpoint.last_accepted_time_ms,
                    checkpoint.pages_completed,
                    checkpoint.status,
                    encode(list(checkpoint.gap_windows)),
                    encode(list(checkpoint.retention_warnings)),
                    checkpoint.error_code,
                    wall_ms,
                ),
            )
            if before_commit is not None:
                before_commit()
        apply_restrictive_permissions(self.path)

    def load_checkpoint(
        self,
        *,
        endpoint: str,
        symbol: str,
        window_start_ms: int,
        window_end_ms: int,
        schema_version: str = SCHEMA_CHECKPOINT,
    ) -> PaginationCheckpoint | None:
        with sqlite_connection(self.path, write=False) as db:
            row = db.execute(
                """SELECT * FROM pagination_checkpoints
                   WHERE endpoint=? AND symbol=? AND window_start_ms=? AND window_end_ms=? AND schema_version=?""",
                (endpoint, symbol, window_start_ms, window_end_ms, schema_version),
            ).fetchone()
            if row is None:
                return None
            return PaginationCheckpoint(
                endpoint=row["endpoint"],
                symbol=row["symbol"],
                window_start_ms=row["window_start_ms"],
                window_end_ms=row["window_end_ms"],
                schema_version=row["schema_version"],
                cursor_type=row["cursor_type"],
                cursor_value=row["cursor_value"],
                last_accepted_id=row["last_accepted_id"],
                last_accepted_time_ms=row["last_accepted_time_ms"],
                pages_completed=row["pages_completed"],
                status=row["status"],
                gap_windows=tuple(json.loads(row["gap_windows_json"])),
                retention_warnings=tuple(json.loads(row["retention_warnings_json"])),
                error_code=row["error_code"],
                updated_wall_ms=row["updated_wall_ms"],
            )

    def list_checkpoints(self) -> list[PaginationCheckpoint]:
        with sqlite_connection(self.path, write=False) as db:
            rows = db.execute(
                "SELECT * FROM pagination_checkpoints ORDER BY endpoint, symbol, window_start_ms"
            ).fetchall()
            return [
                PaginationCheckpoint(
                    endpoint=row["endpoint"],
                    symbol=row["symbol"],
                    window_start_ms=row["window_start_ms"],
                    window_end_ms=row["window_end_ms"],
                    schema_version=row["schema_version"],
                    cursor_type=row["cursor_type"],
                    cursor_value=row["cursor_value"],
                    last_accepted_id=row["last_accepted_id"],
                    last_accepted_time_ms=row["last_accepted_time_ms"],
                    pages_completed=row["pages_completed"],
                    status=row["status"],
                    gap_windows=tuple(json.loads(row["gap_windows_json"])),
                    retention_warnings=tuple(json.loads(row["retention_warnings_json"])),
                    error_code=row["error_code"],
                    updated_wall_ms=row["updated_wall_ms"],
                )
                for row in rows
            ]

    def load_all_fills(self, *, symbol: str | None = None) -> tuple[NormalizedFill, ...]:
        with sqlite_connection(self.path, write=False) as db:
            if symbol is not None:
                rows = db.execute(
                    "SELECT payload, payload_sha FROM fills WHERE symbol=? ORDER BY trade_time_ms, trade_id",
                    (symbol,),
                ).fetchall()
            else:
                rows = db.execute("SELECT payload, payload_sha FROM fills ORDER BY symbol, trade_time_ms, trade_id").fetchall()
            raw_list = []
            for r in rows:
                data = json.loads(r["payload"])
                check(digest(data) == r["payload_sha"], "B3_FILL_DIGEST_MISMATCH")
                raw_list.append(_fill_dict_to_exchange_shape(data))
            return normalize_fills(raw_list)

    def load_all_income(self, *, symbol: str | None = None) -> tuple[NormalizedIncome, ...]:
        with sqlite_connection(self.path, write=False) as db:
            if symbol is not None:
                rows = db.execute(
                    "SELECT payload, payload_sha FROM income_rows WHERE symbol=? ORDER BY time_ms, tran_id",
                    (symbol,),
                ).fetchall()
            else:
                rows = db.execute("SELECT payload, payload_sha FROM income_rows ORDER BY time_ms, tran_id").fetchall()
            raw_list = []
            for r in rows:
                data = json.loads(r["payload"])
                check(digest(data) == r["payload_sha"], "B3_INCOME_DIGEST_MISMATCH")
                raw_list.append(_income_dict_to_exchange_shape(data))
            return normalize_income(raw_list)

    def load_all_orders(
        self, *, symbol: str | None = None, source_endpoint: str | None = None
    ) -> tuple[NormalizedOrder, ...]:
        clauses: list[str] = []
        args: list[Any] = []
        if symbol is not None:
            clauses.append("symbol=?")
            args.append(symbol)
        if source_endpoint is not None:
            clauses.append("source_endpoint=?")
            args.append(source_endpoint)
        sql = "SELECT source_endpoint, payload, payload_sha FROM ordinary_orders"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY update_time_ms, order_id"
        with sqlite_connection(self.path, write=False) as db:
            rows = db.execute(sql, tuple(args)).fetchall()
            out: list[NormalizedOrder] = []
            for r in rows:
                data = json.loads(r["payload"])
                check(digest(data) == r["payload_sha"], "B3_ORDER_DIGEST_MISMATCH")
                out.extend(
                    normalize_orders(
                        [_order_dict_to_exchange_shape(data)],
                        source_endpoint=r["source_endpoint"],
                    )
                )
            return tuple(out)

    def load_all_algo_orders(
        self, *, symbol: str | None = None, source_endpoint: str | None = None
    ) -> tuple[NormalizedAlgoOrder, ...]:
        clauses: list[str] = []
        args: list[Any] = []
        if symbol is not None:
            clauses.append("symbol=?")
            args.append(symbol)
        if source_endpoint is not None:
            clauses.append("source_endpoint=?")
            args.append(source_endpoint)
        sql = "SELECT source_endpoint, payload, payload_sha FROM algo_orders"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY update_time_ms, algo_id"
        with sqlite_connection(self.path, write=False) as db:
            rows = db.execute(sql, tuple(args)).fetchall()
            out: list[NormalizedAlgoOrder] = []
            for r in rows:
                data = json.loads(r["payload"])
                check(digest(data) == r["payload_sha"], "B3_ALGO_ORDER_DIGEST_MISMATCH")
                out.extend(
                    normalize_algo_orders(
                        [_algo_dict_to_exchange_shape(data)],
                        source_endpoint=r["source_endpoint"],
                    )
                )
            return tuple(out)

    def load_snapshot(self, snapshot_id: str | None = None) -> PrivateAccountSnapshot | None:
        """Reload a verified snapshot (latest if snapshot_id is None)."""
        with sqlite_connection(self.path, write=False) as db:
            if snapshot_id is not None:
                row = db.execute("SELECT payload, payload_sha FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            else:
                row = db.execute(
                    "SELECT payload, payload_sha FROM snapshots ORDER BY as_of_venue_ms DESC, recorded_wall_ms DESC LIMIT 1"
                ).fetchone()
            if row is None:
                return None
            data = json.loads(row["payload"])
            check(digest(data) == row["payload_sha"], "B3_SNAPSHOT_DIGEST_MISMATCH")
            return snapshot_from_dict(data)

    def record_manual_association(
        self,
        *,
        operator_id: str,
        b2_episode_id: str,
        b2_card_id: str | None,
        symbol: str,
        target_type: str,
        target_id: str,
        owner_reported_venue_ms: int,
        note: str = "",
    ) -> ManualAssociation:
        """Record an immutable, auditable, idempotent OWNER_ENTERED manual association."""
        check(0 < len(operator_id) <= 120, "INVALID_OPERATOR_ID")
        check(0 < len(b2_episode_id) <= 128, "INVALID_EPISODE_ID")
        check(target_type in MANUAL_TARGET_TYPES, "INVALID_TARGET_TYPE", target_type)
        check(0 < len(target_id) <= 128, "INVALID_TARGET_ID")
        check(len(note) <= 2000, "NOTE_TOO_LONG")
        parse_symbol(symbol, "symbol")
        parse_int(owner_reported_venue_ms, "owner_reported_venue_ms", minimum=1)

        canonical_claim = {
            "operator_id": operator_id,
            "b2_episode_id": b2_episode_id,
            "b2_card_id": b2_card_id,
            "symbol": symbol,
            "target_type": target_type,
            "target_id": target_id,
            "owner_reported_venue_ms": owner_reported_venue_ms,
            "note": note,
            "evidence": "OWNER_ENTERED",
        }
        assoc_id = digest(["OWNER_ENTERED_ASSOC", operator_id])

        with sqlite_connection(self.path, write=True) as db:
            existing = db.execute(
                "SELECT payload, payload_sha FROM manual_associations WHERE operator_id=?",
                (operator_id,),
            ).fetchone()
            if existing is not None:
                prev = json.loads(existing["payload"])
                check(digest(prev) == existing["payload_sha"], "B3_MANUAL_LINK_DIGEST_MISMATCH")
                for k, v in canonical_claim.items():
                    check(prev.get(k) == v, "MANUAL_ASSOCIATION_IDEMPOTENCY_CONFLICT", k)
                return ManualAssociation(
                    operator_id=prev["operator_id"],
                    association_id=prev["association_id"],
                    b2_episode_id=prev["b2_episode_id"],
                    b2_card_id=prev["b2_card_id"],
                    symbol=prev["symbol"],
                    target_type=prev["target_type"],
                    target_id=prev["target_id"],
                    owner_reported_venue_ms=prev["owner_reported_venue_ms"],
                    recorded_wall_ms=prev["recorded_wall_ms"],
                    note=prev["note"],
                    evidence=prev["evidence"],
                )

            wall_ms = time.time_ns() // 1_000_000
            assoc = ManualAssociation(
                operator_id=operator_id,
                association_id=assoc_id,
                b2_episode_id=b2_episode_id,
                b2_card_id=b2_card_id,
                symbol=symbol,
                target_type=target_type,
                target_id=target_id,
                owner_reported_venue_ms=owner_reported_venue_ms,
                recorded_wall_ms=wall_ms,
                note=note,
            )
            payload_dict = assoc.to_dict()
            db.execute(
                "INSERT INTO manual_associations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    assoc.operator_id,
                    assoc.association_id,
                    assoc.b2_episode_id,
                    assoc.b2_card_id,
                    assoc.symbol,
                    assoc.target_type,
                    assoc.target_id,
                    assoc.owner_reported_venue_ms,
                    assoc.recorded_wall_ms,
                    assoc.note,
                    assoc.evidence,
                    encode(payload_dict),
                    digest(payload_dict),
                ),
            )
            return assoc

    def list_manual_associations(self, *, b2_episode_id: str | None = None) -> tuple[ManualAssociation, ...]:
        with sqlite_connection(self.path, write=False) as db:
            if b2_episode_id is not None:
                rows = db.execute(
                    "SELECT payload, payload_sha FROM manual_associations WHERE b2_episode_id=? ORDER BY recorded_wall_ms, operator_id",
                    (b2_episode_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT payload, payload_sha FROM manual_associations ORDER BY recorded_wall_ms, operator_id"
                ).fetchall()
            result: list[ManualAssociation] = []
            for r in rows:
                data = json.loads(r["payload"])
                check(digest(data) == r["payload_sha"], "B3_MANUAL_LINK_DIGEST_MISMATCH")
                result.append(
                    ManualAssociation(
                        operator_id=data["operator_id"],
                        association_id=data["association_id"],
                        b2_episode_id=data["b2_episode_id"],
                        b2_card_id=data["b2_card_id"],
                        symbol=data["symbol"],
                        target_type=data["target_type"],
                        target_id=data["target_id"],
                        owner_reported_venue_ms=data["owner_reported_venue_ms"],
                        recorded_wall_ms=data["recorded_wall_ms"],
                        note=data["note"],
                        evidence=data["evidence"],
                    )
                )
            return tuple(result)


class OverlayJournal:
    """Separate append-only, SHA-linked B3 overlay journal linked to immutable B2 cards/episodes."""

    def __init__(self, path: Path, *, create: bool = False) -> None:
        self.path = path.resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.path.parent, 0o700)
            except OSError:
                pass
        with sqlite_connection(self.path, write=create) as db:
            app_id = db.execute("PRAGMA application_id").fetchone()[0]
            if create and app_id == 0:
                existing = db.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
                check(existing is None, "B3_OVERLAY_JOURNAL_WRONG_SCHEMA")
                for stmt in OVERLAY_JOURNAL_SCHEMA:
                    db.execute(stmt)
                for table in ("journal_identity", "overlays", "overlay_events"):
                    for op in ("UPDATE", "DELETE"):
                        db.execute(
                            f"CREATE TRIGGER lock_{table}_{op} BEFORE {op} ON {table} "
                            "BEGIN SELECT RAISE(ABORT,'B3_APPEND_ONLY'); END"
                        )
                db.execute(f"PRAGMA application_id={OVERLAY_JOURNAL_APP_ID}")
                db.execute("PRAGMA user_version=1")
                db.execute(
                    "INSERT INTO journal_identity VALUES (?,?,?,?)",
                    (1, EVIDENCE_CLASS_SYNTHETIC, CONNECTION_MODE_FIXTURE, encode(STORAGE_PRIVACY_POLICY)),
                )
                app_id = OVERLAY_JOURNAL_APP_ID
            version = db.execute("PRAGMA user_version").fetchone()[0]
            check(app_id == OVERLAY_JOURNAL_APP_ID and version == 1, "B3_OVERLAY_JOURNAL_WRONG_SCHEMA")
        if create:
            apply_restrictive_permissions(self.path)

    def permissions(self) -> dict[str, str]:
        return {
            "directory_mode": oct(stat.S_IMODE(self.path.parent.stat().st_mode)),
            "file_mode": oct(stat.S_IMODE(self.path.stat().st_mode)),
        }

    def publish(
        self,
        overlay: dict[str, Any],
        *,
        events: list[tuple[str, dict[str, Any]]] | None = None,
        before_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Transactionally append an immutable overlay and SHA-linked events; idempotent on exact overlay_id."""
        overlay_id = str(overlay["overlay_id"])
        payload_text = encode(overlay)
        payload_sha = digest(overlay)
        wall_ms = int(overlay.get("journal_recorded_wall_ms") or (time.time_ns() // 1_000_000))

        with sqlite_connection(self.path, write=True) as db:
            existing = db.execute(
                "SELECT payload, payload_sha FROM overlays WHERE overlay_id=?",
                (overlay_id,),
            ).fetchone()
            if existing is not None:
                prev = json.loads(existing["payload"])
                check(digest(prev) == existing["payload_sha"], "B3_OVERLAY_DIGEST_MISMATCH")
                check(existing["payload_sha"] == payload_sha, "B3_OVERLAY_IDEMPOTENCY_CONFLICT")
                return prev

            db.execute(
                "INSERT INTO overlays VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    overlay_id,
                    overlay["b2_card_id"],
                    overlay["b2_episode_id"],
                    overlay["b2_card_sha256"],
                    overlay["symbol"],
                    overlay.get("snapshot_id"),
                    overlay["market_setup_status"],
                    overlay["account_context_status"],
                    wall_ms,
                    payload_text,
                    payload_sha,
                ),
            )
            event_list = events if events is not None else [
                (
                    "OVERLAY_PUBLISHED",
                    {
                        "market_setup_status": overlay["market_setup_status"],
                        "account_context_status": overlay["account_context_status"],
                        "position_relation": overlay["position_relation"],
                        "protection_status": overlay["protection_status"],
                        "signal_trade_match": overlay["signal_trade_match"],
                        "snapshot_id": overlay.get("snapshot_id"),
                    },
                )
            ]
            for idx, (kind, detail) in enumerate(event_list):
                self._append_event_tx(db, overlay, kind, detail, index=idx)
            if before_commit is not None:
                before_commit()
        apply_restrictive_permissions(self.path)
        return json.loads(payload_text)

    @staticmethod
    def _append_event_tx(
        db: sqlite3.Connection,
        overlay: dict[str, Any],
        kind: str,
        detail: dict[str, Any],
        *,
        index: int,
    ) -> None:
        prior = db.execute("SELECT sha FROM overlay_events ORDER BY seq DESC LIMIT 1").fetchone()
        prev_sha = prior["sha"] if prior is not None else None
        event_id = digest([overlay["overlay_id"], kind, index])
        envelope = {
            "schema": SCHEMA_JOURNAL_EVENT,
            "id": event_id,
            "kind": kind,
            "overlay_id": overlay["overlay_id"],
            "b2_card_id": overlay["b2_card_id"],
            "b2_episode_id": overlay["b2_episode_id"],
            "evidence": EVIDENCE_CLASS_SYNTHETIC,
            "detail": detail,
            "prior_sha": prev_sha,
        }
        event_sha = digest(envelope)
        db.execute(
            """INSERT INTO overlay_events(event_id,overlay_id,b2_card_id,b2_episode_id,kind,evidence,payload,prior_sha,sha)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                overlay["overlay_id"],
                overlay["b2_card_id"],
                overlay["b2_episode_id"],
                kind,
                EVIDENCE_CLASS_SYNTHETIC,
                encode(detail),
                prev_sha,
                event_sha,
            ),
        )

    def read(
        self,
        *,
        overlay_id: str | None = None,
        b2_card_id: str | None = None,
        b2_episode_id: str | None = None,
    ) -> dict[str, Any] | None:
        clauses: list[str] = []
        args: list[Any] = []
        if overlay_id is not None:
            clauses.append("overlay_id=?")
            args.append(overlay_id)
        if b2_card_id is not None:
            clauses.append("b2_card_id=?")
            args.append(b2_card_id)
        if b2_episode_id is not None:
            clauses.append("b2_episode_id=?")
            args.append(b2_episode_id)
        sql = "SELECT payload, payload_sha FROM overlays"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY recorded_wall_ms DESC, overlay_id DESC LIMIT 1"
        with sqlite_connection(self.path, write=False) as db:
            row = db.execute(sql, tuple(args)).fetchone()
            if row is None:
                return None
            data = json.loads(row["payload"])
            check(digest(data) == row["payload_sha"], "B3_OVERLAY_DIGEST_MISMATCH")
            return data

    def list_overlays(self) -> list[dict[str, Any]]:
        with sqlite_connection(self.path, write=False) as db:
            rows = db.execute(
                "SELECT payload, payload_sha FROM overlays ORDER BY recorded_wall_ms ASC, overlay_id ASC"
            ).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                data = json.loads(r["payload"])
                check(digest(data) == r["payload_sha"], "B3_OVERLAY_DIGEST_MISMATCH")
                out.append(data)
            return out

    def events(self) -> list[dict[str, Any]]:
        """Read and verify the complete SHA-linked overlay event chain."""
        with sqlite_connection(self.path, write=False) as db:
            rows = db.execute("SELECT * FROM overlay_events ORDER BY seq ASC").fetchall()
            out: list[dict[str, Any]] = []
            prior: str | None = None
            for r in rows:
                envelope = {
                    "schema": SCHEMA_JOURNAL_EVENT,
                    "id": r["event_id"],
                    "kind": r["kind"],
                    "overlay_id": r["overlay_id"],
                    "b2_card_id": r["b2_card_id"],
                    "b2_episode_id": r["b2_episode_id"],
                    "evidence": r["evidence"],
                    "detail": json.loads(r["payload"]),
                    "prior_sha": r["prior_sha"],
                }
                check(r["prior_sha"] == prior and digest(envelope) == r["sha"], "B3_OVERLAY_EVENT_CHAIN_TAMPERED")
                prior = r["sha"]
                out.append({**envelope, "sequence": r["seq"], "sha256": prior})
            return out

    def replay(self) -> dict[str, Any]:
        """Verify all overlay digests and the entire SHA-linked event chain for deterministic replay."""
        overlays = self.list_overlays()
        events = self.events()
        overlay_ids = {item["overlay_id"] for item in overlays}
        for ev in events:
            if ev["overlay_id"] not in overlay_ids:
                raise AccountB3Error("B3_OVERLAY_EVENT_ORPHAN", ev["overlay_id"])
        return {
            "journal_path": str(self.path),
            "verified": True,
            "overlay_count": len(overlays),
            "event_count": len(events),
            "tail_event_sha256": events[-1]["sha256"] if events else None,
            "overlays": overlays,
            "events": events,
        }


# Round-trip deserialization helpers from canonical B3 dict back to normalized dataclasses.
def _account_dict_to_exchange_shape(d: dict[str, Any]) -> dict[str, Any]:
    assets = [
        {
            "asset": a["asset"],
            "walletBalance": a["wallet_balance"],
            "availableBalance": a["available_balance"],
            "marginBalance": a["margin_balance"],
            "unrealizedProfit": a["unrealized_profit"],
            "crossWalletBalance": a["cross_wallet_balance"],
            "maxWithdrawAmount": a["max_withdraw_amount"],
            "marginAvailable": a["margin_available"],
            "updateTime": a["update_time_ms"],
            **a.get("raw_unknown_fields", {}),
        }
        for a in d.get("assets", [])
    ]
    positions = [
        {"symbol": sym, "positionAmt": "0" if sym in d.get("embedded_positions_zero_symbols", []) else "1"}
        for sym in d.get("embedded_position_symbols", [])
    ]
    return {
        "totalWalletBalance": d["wallet_balance"],
        "availableBalance": d["available_balance"],
        "totalMarginBalance": d["margin_balance"],
        "totalUnrealizedProfit": d["total_unrealized_profit"],
        "totalInitialMargin": d["total_initial_margin"],
        "totalMaintMargin": d["total_maint_margin"],
        "totalPositionInitialMargin": d["total_position_initial_margin"],
        "totalOpenOrderInitialMargin": d["total_open_order_initial_margin"],
        "totalCrossWalletBalance": d["total_cross_wallet_balance"],
        "totalCrossUnPnl": d["total_cross_un_pnl"],
        "maxWithdrawAmount": d["max_withdraw_amount"],
        "multiAssetsMargin": d["multi_assets_margin"],
        "feeTier": d["fee_tier"],
        "canTrade": d["can_trade"],
        "canDeposit": d["can_deposit"],
        "canWithdraw": d["can_withdraw"],
        "updateTime": d["update_time_ms"],
        "assets": assets,
        "positions": positions,
        **d.get("raw_unknown_fields", {}),
    }


def _position_dict_to_exchange_shape(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": d["symbol"],
        "positionAmt": d["position_amt"],
        "positionSide": d["position_side"],
        "entryPrice": d["entry_price"],
        "breakEvenPrice": d["break_even_price"],
        "markPrice": d["mark_price"],
        "unRealizedProfit": d["unrealized_profit"],
        "liquidationPrice": d["liquidation_price"],
        "leverage": d["leverage"],
        "marginType": d["margin_type"],
        "isolatedMargin": d["isolated_margin"],
        "isolatedWallet": d["isolated_wallet"],
        "notional": d["notional"],
        "updateTime": d["update_time_ms"],
        **d.get("raw_unknown_fields", {}),
    }


def _order_dict_to_exchange_shape(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": d["symbol"],
        "orderId": d["order_id"],
        "clientOrderId": d["client_order_id"],
        "side": d["side"],
        "positionSide": d["position_side"],
        "type": d["order_type"],
        "origType": d["orig_type"],
        "status": d["status"],
        "origQty": d["orig_qty"],
        "executedQty": d["executed_qty"],
        "price": d["price"],
        "avgPrice": d["avg_price"],
        "stopPrice": d["stop_price"],
        "activatePrice": d["activate_price"],
        "priceRate": d["price_rate"],
        "workingType": d["working_type"],
        "closePosition": d["close_position"],
        "reduceOnly": d["reduce_only"],
        "timeInForce": d["time_in_force"],
        "time": d["create_time_ms"],
        "updateTime": d["update_time_ms"],
        **d.get("raw_unknown_fields", {}),
    }


def _algo_dict_to_exchange_shape(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": d["symbol"],
        "algoId": d["algo_id"],
        "clientAlgoId": d["client_algo_id"],
        "algoType": d["algo_type"],
        "orderType": d["order_type"],
        "algoStatus": d["algo_status"],
        "side": d["side"],
        "positionSide": d["position_side"],
        "quantity": d["quantity"],
        "triggerPrice": d["trigger_price"],
        "price": d["price"],
        "activatePrice": d["activate_price"],
        "callbackRate": d["callback_rate"],
        "workingType": d["working_type"],
        "closePosition": d["close_position"],
        "reduceOnly": d["reduce_only"],
        "timeInForce": d["time_in_force"],
        "createTime": d["create_time_ms"],
        "updateTime": d["update_time_ms"],
        "triggerTime": d["trigger_time_ms"],
        "actualOrderId": d["actual_order_id"],
        "actualPrice": d["actual_price"],
        "triggerResult": d["trigger_result"],
        **d.get("raw_unknown_fields", {}),
    }


def _fill_dict_to_exchange_shape(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": d["symbol"],
        "id": d["trade_id"],
        "orderId": d["order_id"],
        "side": d["side"],
        "positionSide": d["position_side"],
        "price": d["price"],
        "qty": d["qty"],
        "quoteQty": d["quote_qty"],
        "realizedPnl": d["realized_pnl"],
        "commission": d["commission"],
        "commissionAsset": d["commission_asset"],
        "time": d["trade_time_ms"],
        "maker": d["maker"],
        "buyer": d["buyer"],
        **d.get("raw_unknown_fields", {}),
    }


def _income_dict_to_exchange_shape(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "tranId": d["tran_id"],
        "symbol": d["symbol"],
        "incomeType": d["income_type"],
        "income": d["income"],
        "asset": d["asset"],
        "info": d["info"],
        "time": d["time_ms"],
        "tradeId": d["trade_id"],
        "orderId": d["order_id"],
        **d.get("raw_unknown_fields", {}),
    }


def snapshot_from_dict(data: dict[str, Any]) -> PrivateAccountSnapshot:
    account: NormalizedAccount | None = (
        normalize_account(_account_dict_to_exchange_shape(data["account"])) if data.get("account") else None
    )
    positions = normalize_positions([_position_dict_to_exchange_shape(p) for p in data.get("positions", [])])
    open_orders = normalize_orders(
        [_order_dict_to_exchange_shape(o) for o in data.get("open_orders", [])],
        source_endpoint="/fapi/v1/openOrders",
    )
    open_algo = normalize_algo_orders(
        [_algo_dict_to_exchange_shape(a) for a in data.get("open_algo_orders", [])],
        source_endpoint="/fapi/v1/openAlgoOrders",
    )
    all_orders = normalize_orders(
        [_order_dict_to_exchange_shape(o) for o in data.get("all_orders", [])],
        source_endpoint="/fapi/v1/allOrders",
    )
    all_algo = normalize_algo_orders(
        [_algo_dict_to_exchange_shape(a) for a in data.get("all_algo_orders", [])],
        source_endpoint="/fapi/v1/allAlgoOrders",
    )
    fills = normalize_fills([_fill_dict_to_exchange_shape(f) for f in data.get("fills", [])])
    income = normalize_income([_income_dict_to_exchange_shape(i) for i in data.get("income_rows", [])])
    coverage = {
        ep: EndpointCoverage(
            endpoint=cov["endpoint"],
            symbol=cov["symbol"],
            status=cov["status"],
            request_wall_ms=cov["request_wall_ms"],
            receive_wall_ms=cov["receive_wall_ms"],
            venue_time_estimate_ms=cov["venue_time_estimate_ms"],
            offset_uncertainty_ms=cov["offset_uncertainty_ms"],
            age_ms=cov["age_ms"],
            freshness_limit_ms=cov["freshness_limit_ms"],
            source_identity=cov["source_identity"],
            raw_sha256=cov["raw_sha256"],
            pages_fetched=cov["pages_fetched"],
            page_coverage_complete=cov["page_coverage_complete"],
            record_count=cov["record_count"],
            gap_windows=tuple(cov.get("gap_windows", [])),
            retention_warnings=tuple(cov.get("retention_warnings", [])),
            error_code=cov.get("error_code"),
            error_detail=cov.get("error_detail"),
        )
        for ep, cov in data.get("endpoint_coverage", {}).items()
    }
    return PrivateAccountSnapshot(
        snapshot_id=data["snapshot_id"],
        as_of_venue_ms=data["as_of_venue_ms"],
        symbol_scope=data.get("symbol_scope"),
        account=account,
        positions=positions,
        open_orders=open_orders,
        open_algo_orders=open_algo,
        all_orders=all_orders,
        all_algo_orders=all_algo,
        fills=fills,
        income_rows=income,
        endpoint_coverage=coverage,
        overall_status=data["overall_status"],
        snapshot_mode=data.get("snapshot_mode", "NON_ATOMIC"),
        notes=tuple(data.get("notes", [])),
    )
