from __future__ import annotations

import csv
import hashlib
import json
import os
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
from ..evidence_epoch import EvidenceEpoch, resolve_formal_epoch
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
    trigger_source: str = "MANUAL"
    scheduled_slot_ms: int | None = None
    endpoint_telemetry: dict[str, Any] | None = None
    evidence_epoch_id: str | None = None

    @classmethod
    def from_collection(
        cls,
        symbol: str,
        collection_id: str,
        collection: DerivativeCollection,
        *,
        trigger_source: str = "MANUAL",
        evidence_epoch: EvidenceEpoch | None = None,
    ) -> ForwardDerivativeRecord:
        if collection.observed_at_ms < collection.collection_started_at_ms:
            raise ValueError("observed_at_ms must reflect final assembly after collection start")
        source_timestamps = (
            collection.snapshot.funding_time_ms,
            collection.snapshot.open_interest_time_ms,
            collection.snapshot.taker_time_ms,
            collection.snapshot.basis_time_ms,
            collection.snapshot.long_short_time_ms,
            collection.snapshot.order_book_time_ms,
        )
        if any(
            value is not None and value > collection.observed_at_ms
            for value in source_timestamps
        ):
            raise ValueError("source timestamp cannot be after observed_at_ms")
        payload = {
            "symbol": symbol.upper(),
            "observed_at_ms": collection.observed_at_ms,
            "collector_version": "0.3.14",
            **asdict(collection.snapshot),
            "field_availability": collection.field_availability,
            "endpoint_errors": collection.endpoint_errors,
            "attempted_fields": collection.attempted_fields,
            "endpoint_telemetry": collection.endpoint_telemetry or {},
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            symbol.upper(),
            collection_id,
            collection.collection_started_at_ms,
            collection.observed_at_ms,
            "0.3.14",
            collection.snapshot,
            collection.field_availability,
            collection.endpoint_errors,
            collection.attempted_fields,
            digest,
            trigger_source,
            (collection.collection_started_at_ms // CADENCE_MS) * CADENCE_MS,
            collection.endpoint_telemetry or {},
            (
                evidence_epoch.epoch_id
                if evidence_epoch is not None
                and trigger_source == "SCHEDULED"
                and (collection.collection_started_at_ms // CADENCE_MS) * CADENCE_MS
                >= evidence_epoch.epoch_start_ms
                else None
            ),
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
                    error_summary TEXT NOT NULL,
                    trigger_source TEXT NOT NULL DEFAULT 'LEGACY_UNKNOWN',
                    scheduled_slot_ms INTEGER,
                    endpoint_telemetry_json TEXT NOT NULL DEFAULT '{}',
                    evidence_epoch_id TEXT
                );
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(collection_runs)").fetchall()
            }
            if "trigger_source" not in columns:
                connection.execute(
                    "ALTER TABLE collection_runs ADD COLUMN trigger_source TEXT NOT NULL "
                    "DEFAULT 'LEGACY_UNKNOWN'"
                )
            if "scheduled_slot_ms" not in columns:
                connection.execute(
                    "ALTER TABLE collection_runs ADD COLUMN scheduled_slot_ms INTEGER"
                )
            if "endpoint_telemetry_json" not in columns:
                connection.execute(
                    "ALTER TABLE collection_runs ADD COLUMN endpoint_telemetry_json "
                    "TEXT NOT NULL DEFAULT '{}'"
                )
            if "evidence_epoch_id" not in columns:
                connection.execute(
                    "ALTER TABLE collection_runs ADD COLUMN evidence_epoch_id TEXT"
                )

    def append(self, record: ForwardDerivativeRecord) -> bool:
        snapshot = record.snapshot
        conflict = False
        successful = any(record.field_availability.values())
        with self._connect() as connection:
            if not successful:
                self._insert_run(connection, record, "FAILED")
                return False
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
            "INSERT OR IGNORE INTO collection_runs "
            "(run_id, started_at_ms, finished_at_ms, status, attempted_fields, "
            "successful_fields, error_summary, trigger_source, scheduled_slot_ms, "
            "endpoint_telemetry_json, evidence_epoch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.collection_id,
                record.collection_started_at_ms,
                record.observed_at_ms,
                status,
                json.dumps(record.attempted_fields),
                json.dumps(successful),
                json.dumps(record.endpoint_errors, sort_keys=True),
                record.trigger_source,
                record.scheduled_slot_ms,
                json.dumps(record.endpoint_telemetry or {}, sort_keys=True),
                record.evidence_epoch_id,
            ),
        )

    def evidence_epoch_metrics(
        self, epoch: EvidenceEpoch, *, now_ms: int | None = None
    ) -> dict[str, Any]:
        now = now_ms if now_ms is not None else int(time.time() * 1_000)
        cadence_ms = epoch.cadence_minutes * 60_000
        latest_expected = (
            (now - epoch.post_boundary_delay_seconds * 1_000) // cadence_ms
        ) * cadence_ms
        expected_slots = (
            list(range(epoch.epoch_start_ms, latest_expected + 1, cadence_ms))
            if latest_expected >= epoch.epoch_start_ms
            else []
        )
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM collection_runs WHERE evidence_epoch_id=? "
                "AND trigger_source='SCHEDULED' ORDER BY scheduled_slot_ms,finished_at_ms,run_id",
                (epoch.epoch_id,),
            ).fetchall()
        by_slot: dict[int, sqlite3.Row] = {}
        for row in rows:
            slot = int(row["scheduled_slot_ms"])
            by_slot.setdefault(slot, row)
        fully = {
            slot for slot, row in by_slot.items() if self._run_is_fully_available(row)
        }
        partial = {
            slot
            for slot, row in by_slot.items()
            if slot not in fully and bool(json.loads(str(row["successful_fields"])))
        }
        failed = set(by_slot) - fully - partial
        missing = set(expected_slots) - set(by_slot)
        bad_run = longest_bad = 0
        for slot in expected_slots:
            if slot in fully:
                bad_run = 0
            else:
                bad_run += 1
                longest_bad = max(longest_bad, bad_run)
        field_coverage = {
            field: (
                sum(
                    field in set(json.loads(str(by_slot[slot]["successful_fields"])))
                    for slot in expected_slots
                    if slot in by_slot
                )
                / len(expected_slots)
                if expected_slots
                else 0.0
            )
            for field in epoch.required_fields
        }
        age_days = max(0.0, (now - epoch.epoch_start_ms) / 86_400_000)
        eligible = (
            age_days >= epoch.minimum_days
            and len(fully) >= epoch.minimum_fully_available_snapshots
            and all(
                value >= epoch.minimum_required_field_availability
                for value in field_coverage.values()
            )
            and longest_bad
            <= epoch.maximum_consecutive_failed_or_missing_scheduled_slots
        )
        terminal_gap_failure = (
            longest_bad > epoch.maximum_consecutive_failed_or_missing_scheduled_slots
        )
        return {
            "active_epoch_id": epoch.epoch_id,
            "epoch_start_ms": epoch.epoch_start_ms,
            "epoch_start_rule": epoch.epoch_start_rule,
            "epoch_age_days": age_days,
            "expected_scheduled_slots": len(expected_slots),
            "recorded_scheduled_slots": len(set(by_slot) & set(expected_slots)),
            "fully_available_scheduled_slots": len(fully & set(expected_slots)),
            "partial_slots": len(partial & set(expected_slots)),
            "failed_slots": len(failed & set(expected_slots)),
            "missing_slots": len(missing),
            "active_epoch_success_rate": len(fully & set(expected_slots))
            / len(expected_slots)
            if expected_slots
            else 0.0,
            "required_field_coverage": field_coverage,
            "max_consecutive_bad_or_missing_slots": longest_bad,
            "snapshot_progress": len(fully & set(expected_slots))
            / epoch.minimum_fully_available_snapshots,
            "days_progress": min(1.0, age_days / epoch.minimum_days),
            "eligibility_state": (
                "FAILED_GAP_GATE_TERMINAL"
                if terminal_gap_failure
                else "ELIGIBLE_FOR_PREREGISTERED_RESEARCH"
                if eligible
                else "INITIALIZING"
                if not expected_slots
                else "ACCUMULATING"
            ),
            "terminal_failure": terminal_gap_failure,
            "terminal_reason": (
                "MAX_CONSECUTIVE_BAD_OR_MISSING_EXCEEDED"
                if terminal_gap_failure
                else None
            ),
            "manual_runs_count_for_eligibility": False,
            "legacy_runs_count_for_eligibility": False,
            "backfilled_rows": 0,
            "recent_endpoint_error_classes": [
                {
                    "scheduled_slot_ms": int(row["scheduled_slot_ms"]),
                    "classes": sorted(
                        {
                            str(value.get("final_error_class"))
                            for value in json.loads(str(row["endpoint_telemetry_json"])).values()
                            if value.get("final_error_class")
                        }
                    ),
                }
                for row in rows[-10:]
            ],
            "recent_endpoint_telemetry": [
                {
                    "scheduled_slot_ms": int(row["scheduled_slot_ms"]),
                    "endpoints": json.loads(str(row["endpoint_telemetry_json"])),
                }
                for row in rows[-3:]
            ],
        }

    def _run_rows(self) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM collection_runs ORDER BY finished_at_ms, run_id"
            ).fetchall()

    @staticmethod
    def _run_is_fully_available(row: sqlite3.Row) -> bool:
        fields = set(json.loads(str(row["successful_fields"])))
        return set(REQUIRED_RESEARCH_FIELDS).issubset(fields)

    def reliability_metrics(self) -> dict[str, Any]:
        runs = self._run_rows()
        fully = [row for row in runs if self._run_is_fully_available(row)]
        partial = [
            row
            for row in runs
            if str(row["status"]) == "PARTIAL" and not self._run_is_fully_available(row)
        ]
        failed = [row for row in runs if str(row["status"]) in {"FAILED", "CONFLICT"}]
        scheduled = [row for row in runs if str(row["trigger_source"]) == "SCHEDULED"]
        scheduled_full = [row for row in scheduled if self._run_is_fully_available(row)]
        denominator = scheduled if scheduled else runs
        numerator = scheduled_full if scheduled else fully
        consecutive = 0
        for row in reversed(runs):
            if self._run_is_fully_available(row):
                break
            consecutive += 1
        longest_failure_run = current_failure_run = 0
        for row in runs:
            if self._run_is_fully_available(row):
                current_failure_run = 0
            else:
                current_failure_run += 1
                longest_failure_run = max(longest_failure_run, current_failure_run)
        attempt_count = len(runs)
        required_availability = {
            field: (
                sum(field in set(json.loads(str(row["successful_fields"]))) for row in runs)
                / attempt_count
                if attempt_count
                else 0.0
            )
            for field in REQUIRED_RESEARCH_FIELDS
        }
        first = int(runs[0]["finished_at_ms"]) if runs else None
        last = int(runs[-1]["finished_at_ms"]) if runs else None
        coverage_days = (last - first) / 86_400_000 if first is not None and last is not None else 0
        remaining_slots = max(
            0, int((RESEARCH_MIN_DAYS - coverage_days) * 86_400_000 // CADENCE_MS)
        )
        projected_attempts = attempt_count + remaining_slots
        projected_full = len(fully) + remaining_slots
        reachable = (
            projected_full >= RESEARCH_MIN_SNAPSHOTS
            and (
                projected_full / projected_attempts >= RESEARCH_MIN_FIELD_AVAILABILITY
                if projected_attempts
                else False
            )
        )
        availability_successes_needed = max(
            0,
            int(
                (
                    RESEARCH_MIN_FIELD_AVAILABILITY * attempt_count - len(fully)
                )
                / (1 - RESEARCH_MIN_FIELD_AVAILABILITY)
                + 0.999999999
            ),
        )
        required_following_successes = max(
            RESEARCH_MIN_SNAPSHOTS - len(fully), availability_successes_needed
        )
        return {
            "total_attempt_count": attempt_count,
            "scheduled_attempt_count": len(scheduled),
            "manual_attempt_count": sum(str(row["trigger_source"]) == "MANUAL" for row in runs),
            "legacy_unknown_attempt_count": sum(
                str(row["trigger_source"]) == "LEGACY_UNKNOWN" for row in runs
            ),
            "fully_available_snapshot_count": len(fully),
            "partial_snapshot_count": len(partial),
            "failed_attempt_count": len(failed),
            "scheduled_slot_success_rate": len(numerator) / len(denominator) if denominator else 0,
            "scheduled_slot_success_rate_denominator": (
                "SCHEDULED_ONLY" if scheduled else "ALL_ATTEMPTS_FALLBACK"
            ),
            "required_field_availability": required_availability,
            "coverage_days": coverage_days,
            "largest_gap_slots": longest_failure_run,
            "last_success_at_ms": int(fully[-1]["finished_at_ms"]) if fully else None,
            "last_failure_at_ms": int(failed[-1]["finished_at_ms"]) if failed else None,
            "consecutive_failure_count": consecutive,
            "backfilled_rows": 0,
            "coverage_gate_projection": {
                "state": (
                    "RECOVERABLE_WITH_FUTURE_SUCCESS"
                    if reachable
                    else "CURRENT_WINDOW_GATE_MATHEMATICALLY_UNREACHABLE"
                ),
                "required_following_fully_available_successes": required_following_successes,
                "remaining_slots_before_30_days": remaining_slots,
                "best_case_fully_available_snapshots": projected_full,
                "best_case_required_field_availability": (
                    projected_full / projected_attempts if projected_attempts else 0
                ),
            },
        }

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
        reliability = self.reliability_metrics()
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
            "collection_ledger": reliability,
            "legacy_failed_rows_retained": sum(
                not any(json.loads(str(row["field_availability_json"])).values()) for row in rows
            ),
        }

    def status(
        self,
        *,
        scheduler: dict[str, Any] | None = None,
        evidence_epoch_path: str | Path = "configs/forward/v0.3.14_derivatives_evidence_epoch.json",
        evidence_epoch_registry_path: str
        | Path = "configs/forward/derivatives_evidence_epochs.json",
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        rows = self._rows()
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        first = int(rows[0]["observed_at_ms"]) if rows else None
        last = int(rows[-1]["observed_at_ms"]) if rows else None
        reliability = self.reliability_metrics()
        availability = reliability["required_field_availability"]
        audit = self.audit()
        duration_days = (
            (last - first) / 86_400_000 if first is not None and last is not None else 0.0
        )
        expected = (
            (last // CADENCE_MS - first // CADENCE_MS + 1)
            if first is not None and last is not None
            else 0
        )
        epoch, lifecycle = resolve_formal_epoch(
            now,
            registry_path=evidence_epoch_registry_path,
            fallback_epoch_path=evidence_epoch_path,
        )
        active_epoch = self.evidence_epoch_metrics(epoch, now_ms=now)
        active_epoch["lifecycle"] = lifecycle.__dict__.copy() if lifecycle is not None else None
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
            **reliability,
            "first_observed_at_ms": first,
            "last_observed_at_ms": last,
            "last_sample_age_seconds": (now - last) / 1000 if last is not None else None,
            "coverage_days": duration_days,
            "expected_samples": expected,
            "missing_cadence_slots": max(0, expected - len(rows)),
            "gap_count": audit["gap_count"],
            "legacy_snapshot_largest_gap_slots": audit["largest_gap_slots"],
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
            "active_epoch": active_epoch,
            "archive_pre_epoch": {
                **reliability,
                "classification": "NOT_FOR_ELIGIBILITY",
            },
            "research_eligibility": (
                active_epoch["eligibility_state"]
            ),
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
    trigger_source: str | None = None,
    evidence_epoch_path: str | Path = "configs/forward/v0.3.14_derivatives_evidence_epoch.json",
    evidence_epoch_registry_path: str
    | Path = "configs/forward/derivatives_evidence_epochs.json",
) -> ForwardDerivativeRecord:
    collection = client.collect_derivatives(symbol, include_order_book=include_order_book)
    identity = hashlib.sha256(
        f"{symbol}:{collection.collection_started_at_ms}:{collection.observed_at_ms}".encode()
    ).hexdigest()[:24]
    source = trigger_source or os.getenv("BTC_QUANT_TRIGGER_SOURCE") or "MANUAL"
    epoch, _ = resolve_formal_epoch(
        collection.collection_started_at_ms,
        registry_path=evidence_epoch_registry_path,
        fallback_epoch_path=evidence_epoch_path,
    )
    record = ForwardDerivativeRecord.from_collection(
        symbol, identity, collection, trigger_source=source, evidence_epoch=epoch
    )
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
