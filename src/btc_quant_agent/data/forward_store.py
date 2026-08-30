from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from ..domain import DerivativesSnapshot
from .binance import BinancePublicClient, DerivativeCollection
from .derivatives import DERIVATIVE_FIELDS

CADENCE_MS = 15 * 60_000
POST_BOUNDARY_DELAY_MS = 20_000
RESEARCH_MIN_DAYS = 30
RESEARCH_MIN_SNAPSHOTS = 2_500
RESEARCH_MIN_FIELD_AVAILABILITY = 0.95
RESEARCH_MAX_PERSISTENT_GAP_SLOTS = 4
REQUIRED_RESEARCH_FIELDS = (
    "funding_rate",
    "open_interest",
    "taker_buy_sell_ratio",
    "basis_rate",
    "long_short_account_ratio",
)


class ForwardStoreConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ForwardDerivativeRecord:
    symbol: str
    collection_id: str
    collection_started_at_ms: int
    observed_at_ms: int
    collector_version: str
    snapshot: DerivativesSnapshot
    field_availability: dict[str, bool]
    endpoint_errors: dict[str, str]
    attempted_fields: tuple[str, ...]
    payload_hash: str

    @classmethod
    def from_collection(
        cls, symbol: str, collection_id: str, collection: DerivativeCollection
    ) -> ForwardDerivativeRecord:
        payload = {
            "symbol": symbol.upper(),
            "observed_at_ms": collection.observed_at_ms,
            "collector_version": "0.3.11",
            **asdict(collection.snapshot),
            "field_availability": collection.field_availability,
            "endpoint_errors": collection.endpoint_errors,
            "attempted_fields": collection.attempted_fields,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            symbol.upper(),
            collection_id,
            collection.collection_started_at_ms,
            collection.observed_at_ms,
            "0.3.11",
            collection.snapshot,
            collection.field_availability,
            collection.endpoint_errors,
            collection.attempted_fields,
            digest,
        )


class ForwardDerivativeStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS derivative_snapshots (
                    symbol TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    collection_started_at_ms INTEGER NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    collector_version TEXT NOT NULL,
                    mark_price REAL,
                    index_price REAL,
                    premium_bps REAL,
                    funding_rate REAL,
                    funding_time_ms INTEGER,
                    open_interest REAL,
                    open_interest_time_ms INTEGER,
                    open_interest_change_pct REAL,
                    taker_buy_sell_ratio REAL,
                    taker_time_ms INTEGER,
                    basis_rate REAL,
                    basis_time_ms INTEGER,
                    long_short_account_ratio REAL,
                    long_short_time_ms INTEGER,
                    order_book_imbalance REAL,
                    spread_bps REAL,
                    order_book_time_ms INTEGER,
                    field_availability_json TEXT NOT NULL,
                    endpoint_errors_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    PRIMARY KEY(symbol, observed_at_ms)
                );
                CREATE TABLE IF NOT EXISTS collection_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at_ms INTEGER NOT NULL,
                    finished_at_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    attempted_fields TEXT NOT NULL,
                    successful_fields TEXT NOT NULL,
                    error_summary TEXT NOT NULL
                );
                """
            )

    def append(self, record: ForwardDerivativeRecord) -> bool:
        snapshot = record.snapshot
        conflict = False
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT payload_hash FROM derivative_snapshots WHERE symbol=? AND observed_at_ms=?",
                (record.symbol, record.observed_at_ms),
            ).fetchone()
            if existing is not None:
                exact = str(existing["payload_hash"]) == record.payload_hash
                self._insert_run(connection, record, "DUPLICATE" if exact else "CONFLICT")
                conflict = not exact
            else:
                values = asdict(snapshot)
                connection.execute(
                    "INSERT INTO derivative_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        record.symbol,
                        record.collection_id,
                        record.collection_started_at_ms,
                        record.observed_at_ms,
                        record.collector_version,
                        values["mark_price"],
                        values["index_price"],
                        values["premium_bps"],
                        values["funding_rate"],
                        values["funding_time_ms"],
                        values["open_interest"],
                        values["open_interest_time_ms"],
                        values["open_interest_change_pct"],
                        values["taker_buy_sell_ratio"],
                        values["taker_time_ms"],
                        values["basis_rate"],
                        values["basis_time_ms"],
                        values["long_short_account_ratio"],
                        values["long_short_time_ms"],
                        values["order_book_imbalance"],
                        values["spread_bps"],
                        values["order_book_time_ms"],
                        json.dumps(record.field_availability, sort_keys=True),
                        json.dumps(record.endpoint_errors, sort_keys=True),
                        record.payload_hash,
                    ),
                )
                successful = any(record.field_availability.values())
                run_status = (
                    "COMPLETE"
                    if not record.endpoint_errors
                    else "PARTIAL" if successful else "FAILED"
                )
                self._insert_run(connection, record, run_status)
        if conflict:
            raise ForwardStoreConflict("conflicting duplicate PIT snapshot; existing row preserved")
        return existing is None

    @staticmethod
    def _insert_run(
        connection: sqlite3.Connection, record: ForwardDerivativeRecord, status: str
    ) -> None:
        successful = sorted(key for key, value in record.field_availability.items() if value)
        connection.execute(
            "INSERT OR IGNORE INTO collection_runs VALUES (?,?,?,?,?,?,?)",
            (
                record.collection_id,
                record.collection_started_at_ms,
                record.observed_at_ms,
                status,
                json.dumps(record.attempted_fields),
                json.dumps(successful),
                json.dumps(record.endpoint_errors, sort_keys=True),
            ),
        )

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS n FROM derivative_snapshots").fetchone()
        return int(row["n"] if row else 0)

    def _rows(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM derivative_snapshots ORDER BY observed_at_ms"
            ).fetchall()

    def audit(self) -> dict[str, Any]:
        rows = self._rows()
        timestamps = [int(row["observed_at_ms"]) for row in rows]
        gaps = [
            {
                "previous_ms": left,
                "next_ms": right,
                "missing_slots": max(0, (right // CADENCE_MS) - (left // CADENCE_MS) - 1),
            }
            for left, right in pairwise(timestamps)
            if right // CADENCE_MS - left // CADENCE_MS > 1
        ]
        source_fields = (
            "funding_time_ms",
            "open_interest_time_ms",
            "taker_time_ms",
            "basis_time_ms",
            "long_short_time_ms",
            "order_book_time_ms",
        )
        future_sources = [
            {"observed_at_ms": int(row["observed_at_ms"]), "field": field, "value": int(row[field])}
            for row in rows
            for field in source_fields
            if row[field] is not None and int(row[field]) > int(row["observed_at_ms"])
        ]
        impossible = [
            int(row["observed_at_ms"])
            for row in rows
            if (row["mark_price"] is not None and float(row["mark_price"]) <= 0)
            or (row["index_price"] is not None and float(row["index_price"]) <= 0)
            or (row["open_interest"] is not None and float(row["open_interest"]) < 0)
            or (row["taker_buy_sell_ratio"] is not None and float(row["taker_buy_sell_ratio"]) < 0)
            or (
                row["long_short_account_ratio"] is not None
                and float(row["long_short_account_ratio"]) < 0
            )
        ]
        with self._connect() as connection:
            conflicts = connection.execute(
                "SELECT COUNT(*) AS n FROM collection_runs WHERE status='CONFLICT'"
            ).fetchone()
        return {
            "path": str(self.path),
            "sample_count": len(rows),
            "timestamp_ordered": timestamps == sorted(timestamps),
            "duplicate_count": len(timestamps) - len(set(timestamps)),
            "conflict_count": int(conflicts["n"] if conflicts else 0),
            "gap_count": len(gaps),
            "largest_gap_slots": max((item["missing_slots"] for item in gaps), default=0),
            "gaps": gaps,
            "source_timestamp_after_observed_at": future_sources,
            "impossible_value_timestamps": impossible,
            "backfilled_rows": 0,
        }

    def status(self, *, scheduler: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = self._rows()
        now = int(time.time() * 1000)
        first = int(rows[0]["observed_at_ms"]) if rows else None
        last = int(rows[-1]["observed_at_ms"]) if rows else None
        availability = {
            field: sum(row[field] is not None for row in rows) / len(rows) if rows else 0.0
            for field in REQUIRED_RESEARCH_FIELDS
        }
        audit = self.audit()
        duration_days = (
            (last - first) / 86_400_000 if first is not None and last is not None else 0.0
        )
        expected = (
            (last // CADENCE_MS - first // CADENCE_MS + 1)
            if first is not None and last is not None
            else 0
        )
        eligible = (
            duration_days >= RESEARCH_MIN_DAYS
            and len(rows) >= RESEARCH_MIN_SNAPSHOTS
            and all(value >= RESEARCH_MIN_FIELD_AVAILABILITY for value in availability.values())
            and int(audit["largest_gap_slots"]) <= RESEARCH_MAX_PERSISTENT_GAP_SLOTS
        )
        with self._connect() as connection:
            errors = connection.execute(
                "SELECT run_id, finished_at_ms, error_summary FROM collection_runs "
                "WHERE error_summary != '{}' ORDER BY finished_at_ms DESC LIMIT 10"
            ).fetchall()
            latest_run = connection.execute(
                "SELECT run_id, finished_at_ms, status FROM collection_runs "
                "ORDER BY finished_at_ms DESC LIMIT 1"
            ).fetchone()
        scheduler_active = bool((scheduler or {}).get("active", False))
        latest_run_status = str(latest_run["status"]) if latest_run else None
        if scheduler_active and latest_run_status in {"PARTIAL", "FAILED", "CONFLICT"}:
            collection_status = "COLLECTING_DEGRADED"
        elif scheduler_active:
            collection_status = "COLLECTING"
        elif rows:
            collection_status = "SCHEDULER_NOT_ACTIVE"
        else:
            collection_status = "NOT_COLLECTING"
        forward_health = (
            "OK"
            if scheduler_active
            and bool(rows)
            and latest_run_status in {"COMPLETE", "DUPLICATE"}
            and last is not None
            and now - last <= 2 * CADENCE_MS
            else "DEGRADED"
        )
        return {
            "store_path": str(self.path),
            "store_exists": self.path.exists(),
            "health": forward_health,
            "sample_count": len(rows),
            "first_observed_at_ms": first,
            "last_observed_at_ms": last,
            "last_sample_age_seconds": (now - last) / 1000 if last is not None else None,
            "coverage_days": duration_days,
            "expected_samples": expected,
            "missing_cadence_slots": max(0, expected - len(rows)),
            "gap_count": audit["gap_count"],
            "largest_gap_slots": audit["largest_gap_slots"],
            "required_field_coverage": availability,
            "recent_endpoint_errors": [
                {
                    "run_id": row["run_id"],
                    "finished_at_ms": row["finished_at_ms"],
                    "errors": json.loads(row["error_summary"]),
                }
                for row in errors
            ],
            "scheduler_detected": bool((scheduler or {}).get("detected", False)),
            "scheduler_active": scheduler_active,
            "collection_status": collection_status,
            "latest_collection_run": {
                "run_id": str(latest_run["run_id"]),
                "finished_at_ms": int(latest_run["finished_at_ms"]),
                "status": latest_run_status,
            }
            if latest_run
            else None,
            "research_eligibility": "ELIGIBLE_FOR_PREREGISTERED_RESEARCH"
            if eligible
            else "INSUFFICIENT_FORWARD_HISTORY",
            "research_gate": {
                "minimum_days": RESEARCH_MIN_DAYS,
                "minimum_snapshots": RESEARCH_MIN_SNAPSHOTS,
                "minimum_required_field_availability": RESEARCH_MIN_FIELD_AVAILABILITY,
                "maximum_persistent_gap_slots": RESEARCH_MAX_PERSISTENT_GAP_SLOTS,
                "alpha_claim": "NONE",
            },
            "next_planned_collection_ms": next_collection_time_ms(now),
        }

    def export(self, csv_path: str | Path, manifest_path: str | Path) -> dict[str, Any]:
        target = Path(csv_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = self._rows()
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=DERIVATIVE_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row[field] for field in DERIVATIVE_FIELDS})
        checksum = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest = {
            "schema_version": "1.0.0",
            "source": str(self.path),
            "format": "HistoricalDerivativeStore-compatible CSV",
            "row_count": len(rows),
            "checksum_sha256": checksum,
            "first_observed_at_ms": int(rows[0]["observed_at_ms"]) if rows else None,
            "last_observed_at_ms": int(rows[-1]["observed_at_ms"]) if rows else None,
            "backfilled_rows": 0,
        }
        Path(manifest_path).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return manifest


def collect_once(
    client: BinancePublicClient,
    store: ForwardDerivativeStore,
    *,
    symbol: str = "BTCUSDT",
    include_order_book: bool = False,
) -> ForwardDerivativeRecord:
    collection = client.collect_derivatives(symbol, include_order_book=include_order_book)
    identity = hashlib.sha256(
        f"{symbol}:{collection.collection_started_at_ms}:{collection.observed_at_ms}".encode()
    ).hexdigest()[:24]
    record = ForwardDerivativeRecord.from_collection(symbol, identity, collection)
    store.append(record)
    return record


def next_collection_time_ms(now_ms: int, *, delay_ms: int = POST_BOUNDARY_DELAY_MS) -> int:
    return ((now_ms // CADENCE_MS) + 1) * CADENCE_MS + delay_ms


def scheduler_status() -> dict[str, Any]:
    unit = "btc-quant-forward-derivatives.timer"
    try:
        detected = (
            subprocess.run(
                ["systemctl", "--user", "is-enabled", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).returncode
            == 0
        )
        active = (
            subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            ).returncode
            == 0
        )
        return {"unit": unit, "detected": detected, "active": active}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"unit": unit, "detected": False, "active": False, "error": str(exc)}
