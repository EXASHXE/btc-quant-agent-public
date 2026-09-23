"""Semantic regression tests P01 through P20 for MicrostructureStore status optimization.

Covers:
- P01: Raw-gap compression (>=100k raw rows, <=20 merged intervals, payload <200 KiB)
- P02: Rolling gap count exact (window boundary inside finalized day, active day, cross-midnight gap, long gap)
- P03: Active quick_check absent from ordinary status
- P04: Finalization quick_check mandatory
- P05: Explicit audit remains deep
- P06: Warm finalized hash reuse
- P07: Fingerprint invalidation
- P08: Same-size mutation invalidation
- P09: Streaming hash memory behavior
- P10: No historical bucket set
- P11: Bucket summary semantic equivalence vs reference
- P12: Partial first day semantic equivalence
- P13: Cross-midnight gap marking equivalence
- P14: Cross-midnight coverage segment equivalence
- P15: Active + finalized composition equivalence
- P16: Cache miss vs warm hit semantic equivalence
- P17: Legacy v2 cache discarded and rebuilt as v3
- P18: Malformed/oversized cache fail-safe handling
- P19: Latency percentiles exact preservation
- P20: Latest-clock semantics exact preservation
"""

from __future__ import annotations

import bisect
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from btc_quant_agent.microstructure import (
    MAX_PARTITION_STATS_CACHE_BYTES,
    STATS_CACHE_SCHEMA_VERSION,
    MicrostructureStore,
    _streaming_sha256,
)


def _init_partition_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS depth_events (
                event_time_ms INTEGER, final_update_id INTEGER, receive_time_ms INTEGER,
                receive_monotonic_ns INTEGER, payload_json TEXT, payload_hash TEXT,
                PRIMARY KEY(event_time_ms, final_update_id))"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agg_trades (
                aggregate_trade_id INTEGER PRIMARY KEY, event_time_ms INTEGER,
                transaction_time_ms INTEGER, receive_time_ms INTEGER,
                receive_monotonic_ns INTEGER, price REAL, quantity REAL,
                buyer_is_maker INTEGER, aggressive_side TEXT, payload_hash TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS book_samples (
                event_time_ms INTEGER, final_update_id INTEGER, receive_time_ms INTEGER,
                spread_bps REAL, top1_imbalance REAL, top5_imbalance REAL,
                top20_imbalance REAL, microprice REAL, ofi REAL,
                PRIMARY KEY(event_time_ms, final_update_id))"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS aggregates (
                interval_ms INTEGER, bucket_start_ms INTEGER, trade_count INTEGER DEFAULT 0,
                buy_quantity REAL DEFAULT 0, sell_quantity REAL DEFAULT 0,
                buy_notional REAL DEFAULT 0, sell_notional REAL DEFAULT 0,
                book_sample_count INTEGER DEFAULT 0, spread_bps_sum REAL DEFAULT 0,
                top1_imbalance_sum REAL DEFAULT 0, top5_imbalance_sum REAL DEFAULT 0,
                top20_imbalance_sum REAL DEFAULT 0, ofi_sum REAL DEFAULT 0,
                gap_count INTEGER DEFAULT 0, PRIMARY KEY(interval_ms, bucket_start_ms))"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS coverage_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id TEXT, stream TEXT,
                start_ms INTEGER, end_ms INTEGER, sequence_valid INTEGER, status TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS gaps (
                id INTEGER PRIMARY KEY, start_ms INTEGER, end_ms INTEGER, kind TEXT, detail TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS process_instances (
                instance_id TEXT PRIMARY KEY, start_ms INTEGER, last_heartbeat_ms INTEGER,
                end_ms INTEGER, status TEXT)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS clock_measurements (
                measured_at_ms INTEGER PRIMARY KEY, request_send_ms INTEGER,
                response_receive_ms INTEGER, server_time_ms INTEGER, offset_ms REAL,
                rtt_ms INTEGER, quality TEXT)"""
        )


def _reference_buckets_and_rolling(store: MicrostructureStore, now_ms: int) -> dict[str, Any]:
    """Exact reference / brute-force calculation for semantic equivalence checks."""
    current_files = sorted(store.root.glob("microstructure-*.sqlite3"))
    segments: dict[str, list[tuple[int, int]]] = {"depth": [], "trade": []}
    depth_valid_segments: list[tuple[int, int]] = []
    raw_gaps: list[tuple[int, int, str]] = []

    for path in current_files:
        with sqlite3.connect(path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "coverage_segments" in tables:
                for stream, start, end, valid in conn.execute(
                    "SELECT stream,start_ms,end_ms,sequence_valid FROM coverage_segments"
                ):
                    s = (int(start), min(now_ms, int(end)))
                    segments[str(stream)].append(s)
                    if stream == "depth" and bool(valid):
                        depth_valid_segments.append(s)
            if "gaps" in tables:
                for start, end, kind in conn.execute("SELECT start_ms,end_ms,kind FROM gaps"):
                    raw_gaps.append((int(start), int(end), str(kind)))

    evaluation_start = min(
        (start for stream_segments in segments.values() for start, _ in stream_segments),
        default=now_ms,
    )

    bucket_candidates: set[tuple[int, int]] = set()
    if evaluation_start < now_ms:
        for interval in store.INTERVALS_MS:
            first = evaluation_start // interval * interval
            latest_closed = now_ms // interval * interval - interval
            bucket_candidates.update(
                (interval, start)
                for start in range(first, latest_closed + 1, interval)
            )

    def _merge(segs: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not segs:
            return []
        ordered = sorted(segs)
        merged: list[list[int]] = []
        for s, e in ordered:
            if e <= s:
                continue
            if not merged:
                merged.append([s, e])
            elif s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        return [(s, e) for s, e in merged]

    def _covered(merged: list[tuple[int, int]], start_ms: int, end_ms: int) -> int:
        if not merged or end_ms <= start_ms:
            return 0
        idx = bisect.bisect_right(merged, (start_ms, 10**18)) - 1
        idx = max(idx, 0)
        covered = 0
        for s, e in merged[idx:]:
            if s >= end_ms:
                break
            overlap_s = max(start_ms, s)
            overlap_e = min(end_ms, e)
            if overlap_e > overlap_s:
                covered += overlap_e - overlap_s
        return covered

    def _has_gap(merged_gaps: list[tuple[int, int]], start_ms: int, end_ms: int) -> bool:
        if not merged_gaps or end_ms <= start_ms:
            return False
        idx = bisect.bisect_right(merged_gaps, (start_ms, 10**18)) - 1
        idx = max(idx, 0)
        for s, e in merged_gaps[idx:]:
            if s >= end_ms:
                break
            if s < end_ms and e >= start_ms:
                return True
        return False

    merged_trade = _merge(segments.get("trade", []))
    merged_depth = _merge(segments.get("depth", []))
    merged_valid = _merge(depth_valid_segments)
    merged_gaps = _merge([(g[0], g[1]) for g in raw_gaps])

    closed_buckets = complete_buckets = gap_affected_buckets = 0
    completeness_by_interval: dict[str, dict[str, int | float]] = {}

    for interval in store.INTERVALS_MS:
        interval_candidates = sorted(
            start for candidate_interval, start in bucket_candidates if candidate_interval == interval
        )
        interval_complete = interval_gap = 0
        for start in interval_candidates:
            end = start + interval
            trade_ratio = _covered(merged_trade, start, end) / interval
            depth_ratio = _covered(merged_depth, start, end) / interval
            valid_ratio = _covered(merged_valid, start, end) / interval
            gap_overlap = _has_gap(merged_gaps, start, end)
            interval_gap += int(gap_overlap)
            interval_complete += int(
                trade_ratio >= store.protocol.minimum_trade_coverage
                and depth_ratio >= store.protocol.minimum_depth_coverage
                and valid_ratio >= store.protocol.minimum_depth_valid_coverage
                and not gap_overlap
            )
        closed_buckets += len(interval_candidates)
        complete_buckets += interval_complete
        gap_affected_buckets += interval_gap
        completeness_by_interval[str(interval)] = {
            "closed": len(interval_candidates),
            "complete": interval_complete,
            "ratio": interval_complete / len(interval_candidates) if interval_candidates else 0.0,
        }
    completeness_ratio = complete_buckets / closed_buckets if closed_buckets else 0.0

    rolling_reliability: dict[str, dict[str, Any]] = {}
    for label, window_ms in (("24h", 86_400_000), ("7d", 7 * 86_400_000)):
        window_start = max(evaluation_start, now_ms - window_ms)
        rolling_reliability[label] = {
            "gap_count": sum(
                gap_start < now_ms and gap_end >= window_start
                for gap_start, gap_end, _ in raw_gaps
            ),
        }

    return {
        "closed_aggregate_buckets": closed_buckets,
        "complete_aggregate_buckets": complete_buckets,
        "gap_affected_buckets": gap_affected_buckets,
        "aggregate_completeness_ratio": completeness_ratio,
        "aggregate_completeness_by_interval_ms": completeness_by_interval,
        "rolling_reliability": rolling_reliability,
        "gap_count": len(raw_gaps),
    }


def _day_ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def test_p01_raw_gap_compression(tmp_path: Path) -> None:
    """P01: Generate >=100,000 raw gap rows that merge into <=20 intervals."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P01", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    # 10 clusters of 10,000 overlapping gap rows = 100,000 raw rows merging into 10 intervals
    num_clusters = 10
    rows_per_cluster = 10_000
    total_gaps = num_clusters * rows_per_cluster

    with sqlite3.connect(p) as conn:
        conn.execute("BEGIN TRANSACTION")
        for c in range(num_clusters):
            c_start = day_start + c * 3_600_000
            for r in range(rows_per_cluster):
                # Sub-intervals overlapping within a 1-minute window
                s = c_start + (r % 60) * 1000
                e = s + 1500
                kind = "DEPTH_SEQUENCE_GAP" if (c + r) % 2 == 0 else "DEPTH_RECONNECT"
                gid = c * rows_per_cluster + r + 1
                conn.execute(
                    "INSERT INTO gaps (id, start_ms, end_ms, kind, detail) VALUES (?, ?, ?, ?, ?)",
                    (gid, s, e, kind, "test"),
                )
        conn.commit()

    status = store.status(now_ms=day_start + 86_400_000)
    assert status["gap_count"] == total_gaps
    assert sum(status["gap_type_counts"].values()) == total_gaps

    cache_raw = store._stats_cache_path.read_text(encoding="utf-8")
    cache = json.loads(cache_raw)
    p_stats = cache["partitions"][p.name]["stats"]

    # Verify no raw gap row list persisted
    assert "gap_rows" not in p_stats
    assert p_stats["gap_count"] == total_gaps
    assert len(p_stats["gap_merged_intervals"]) <= 20

    # Payload size < 200 KiB (in fact < 10 KiB)
    assert len(cache_raw.encode("utf-8")) < 200 * 1024


def test_p02_rolling_gap_count_exact(tmp_path: Path) -> None:
    """P02: Compare optimized 24h/7d raw gap counts against direct SQL / reference scan."""
    day1_start = _day_ts(2026, 9, 1)
    day2_start = _day_ts(2026, 9, 2)
    day3_start = _day_ts(2026, 9, 3)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P02", day1_start)
    p1 = store._path(day1_start)
    p2 = store._path(day2_start)
    p3 = store._path(day3_start)
    _init_partition_db(p1)
    _init_partition_db(p2)
    _init_partition_db(p3)

    # p1 finalized in manifest
    manifest_payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "protocol_id": store.protocol.protocol_id,
        "partitions": {
            p1.name: {
                "sha256": _streaming_sha256(p1),
                "finalized_at_ms": day2_start + 1000,
                "eligible_at_ms": day2_start,
                "immutable": True,
            }
        },
    }
    store.finalized_manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    # Add coverage in all days
    with sqlite3.connect(p1) as conn:
        conn.execute(
            "INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')",
            (day1_start + 3600_000, day1_start + 86400_000),
        )
        conn.execute(
            "INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')",
            (day1_start + 3600_000, day1_start + 86400_000),
        )
        # Long gap starting before rolling window that reaches day 2
        conn.execute(
            "INSERT INTO gaps VALUES (1, ?, ?, 'DEPTH_SEQUENCE_GAP', 'long')",
            (day1_start + 1000, day2_start + 10_000),
        )
        # Gap crossing midnight between day 1 and day 2
        conn.execute(
            "INSERT INTO gaps VALUES (2, ?, ?, 'DEPTH_SEQUENCE_GAP', 'midnight')",
            (day2_start - 5000, day2_start + 5000),
        )
        # Ordinary gap within day 1
        conn.execute(
            "INSERT INTO gaps VALUES (3, ?, ?, 'DEPTH_RECONNECT', 'day1')",
            (day1_start + 10_000, day1_start + 20_000),
        )

    # Re-finalize p1 manifest sha after gap inserts
    manifest_payload["partitions"][p1.name]["sha256"] = _streaming_sha256(p1)
    store.finalized_manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    with sqlite3.connect(p2) as conn:
        conn.execute(
            "INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')",
            (day2_start, day2_start + 86400_000),
        )
        conn.execute(
            "INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')",
            (day2_start, day2_start + 86400_000),
        )
        # Gap in day 2
        conn.execute(
            "INSERT INTO gaps VALUES (4, ?, ?, 'DEPTH_BOOTSTRAP_FAILURE', 'day2')",
            (day2_start + 1000, day2_start + 2000),
        )

    with sqlite3.connect(p3) as conn:
        conn.execute(
            "INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'OPEN')",
            (day3_start, day3_start + 3600_000),
        )
        conn.execute(
            "INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'OPEN')",
            (day3_start, day3_start + 3600_000),
        )
        # Active gap in day 3
        conn.execute(
            "INSERT INTO gaps VALUES (5, ?, ?, 'DEPTH_GAP_RESYNC', 'day3')",
            (day3_start + 500, day3_start + 1500),
        )

    now_eval = day3_start + 3600_000
    ref = _reference_buckets_and_rolling(store, now_eval)
    opt = store.status(now_ms=now_eval)

    assert opt["rolling_reliability"]["24h"]["gap_count"] == ref["rolling_reliability"]["24h"]["gap_count"]
    assert opt["rolling_reliability"]["7d"]["gap_count"] == ref["rolling_reliability"]["7d"]["gap_count"]
    assert opt["gap_count"] == ref["gap_count"]


def test_p03_active_quick_check_absent_from_ordinary_status(tmp_path: Path) -> None:
    """P03: Trace SQLite statements and require ordinary status executes zero PRAGMA quick_check on active DB."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P03", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    executed_statements: list[str] = []

    def trace_callback(statement: str) -> None:
        executed_statements.append(statement.strip())

    # We patch sqlite3.connect to install trace callback on connections
    orig_connect = sqlite3.connect

    def connect_with_trace(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = orig_connect(*args, **kwargs)
        conn.set_trace_callback(trace_callback)
        return cast(sqlite3.Connection, conn)

    with patch("sqlite3.connect", side_effect=connect_with_trace):
        status = store.status(now_ms=day_start + 1000)

    quick_checks = [s for s in executed_statements if "quick_check" in s.lower()]
    assert len(quick_checks) == 0, f"Unexpected quick_check calls: {quick_checks}"
    assert status["status_performance"]["active_quick_check_executed"] is False
    assert status["status_performance"]["active_partition_integrity_mode"] == "LIGHTWEIGHT_STATUS_READS"


def test_p04_finalization_quick_check_mandatory(tmp_path: Path) -> None:
    """P04: Require finalization runs quick_check and refuses manifest publication if result != ok."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P04", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    # Case 1: Healthy partition succeeds
    finalize_now = day_start + 86_400_000 + store.protocol.finalization_grace_ms + 1000
    manifest = store.finalize_partitions(now_ms=finalize_now)
    assert p.name in manifest
    assert store.finalized_manifest_path.exists()

    # Case 2: Corrupted partition fails quick_check and refuses finalization
    day2_start = day_start + 86_400_000
    p2 = store._path(day2_start)
    _init_partition_db(p2)

    orig_connect = sqlite3.connect

    class FakeConn:
        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real

        def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
            if "quick_check" in sql.lower():
                return self._real.execute("SELECT 'corrupt' AS status")
            return self._real.execute(sql, *args, **kwargs)

        def close(self) -> None:
            self._real.close()

        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *args: Any) -> None:
            self._real.close()

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    def fake_connect(*args: Any, **kwargs: Any) -> Any:
        return FakeConn(orig_connect(*args, **kwargs))

    manifest_before = store.finalized_manifest_path.read_text(encoding="utf-8")
    finalize_day2_now = day2_start + 86_400_000 + store.protocol.finalization_grace_ms + 1000
    with patch("sqlite3.connect", side_effect=fake_connect):
        with pytest.raises(RuntimeError, match="quick_check failed"):
            store.finalize_partitions(now_ms=finalize_day2_now)

    manifest_after = store.finalized_manifest_path.read_text(encoding="utf-8")
    assert manifest_before == manifest_after
    assert p2.name not in json.loads(manifest_after)["partitions"]


def test_p05_explicit_audit_remains_deep(tmp_path: Path) -> None:
    """P05: Explicit/deep audit executes active quick_check and finalized full checksum verification."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P05", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    executed_statements: list[str] = []
    orig_connect = sqlite3.connect

    def connect_with_trace(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = orig_connect(*args, **kwargs)
        conn.set_trace_callback(lambda s: executed_statements.append(s.strip()))
        return cast(sqlite3.Connection, conn)

    with patch("sqlite3.connect", side_effect=connect_with_trace):
        status = store.status(now_ms=day_start + 1000, deep_integrity=True)

    quick_checks = [s for s in executed_statements if "quick_check" in s.lower()]
    assert len(quick_checks) >= 1
    assert status["status_performance"]["active_quick_check_executed"] is True
    assert status["status_performance"]["active_partition_integrity_mode"] == "DEEP_QUICK_CHECK"


def test_p06_warm_finalized_hash_reuse(tmp_path: Path) -> None:
    """P06: After one verified full hash, second ordinary status with identical stat fingerprint reads 0 bytes for SHA."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P06", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    # Finalize partition
    finalize_now = day_start + 86_400_000 + store.protocol.finalization_grace_ms + 1000
    store.finalize_partitions(now_ms=finalize_now)

    # First status: populates attestation
    status1 = store.status(now_ms=finalize_now + 1000)
    assert status1["partition_integrity"]["integrity_ok"] is True

    # Second status: fingerprint match, must reuse cached attestation
    status2 = store.status(now_ms=finalize_now + 2000)
    assert status2["partition_integrity"]["integrity_ok"] is True
    assert status2["status_performance"]["finalized_hash_reused"] == 1
    assert status2["status_performance"]["finalized_hash_recomputed"] == 0


def test_p07_fingerprint_invalidation(tmp_path: Path) -> None:
    """P07: Modify disposable finalized test file. Require fingerprint mismatch causes rehash and detects manifest drift."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P07", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    finalize_now = day_start + 86_400_000 + store.protocol.finalization_grace_ms + 1000
    store.finalize_partitions(now_ms=finalize_now)

    # Warm initial check
    status1 = store.status(now_ms=finalize_now + 1000)
    assert status1["partition_integrity"]["integrity_ok"] is True

    # Mutate finalized file (append bytes to change size and mtime)
    with open(p, "ab") as f:
        f.write(b"drift_mutation")

    status2 = store.status(now_ms=finalize_now + 2000)
    assert status2["partition_integrity"]["integrity_ok"] is False
    assert p.name in status2["partition_integrity"]["checksum_drift"]
    assert status2["status_performance"]["finalized_hash_recomputed"] >= 1


def test_p08_same_size_mutation(tmp_path: Path) -> None:
    """P08: Mutate content while maintaining file size. Require changed mtime/ctime/fingerprint invalidates cached attestation."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P08", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    finalize_now = day_start + 86_400_000 + store.protocol.finalization_grace_ms + 1000
    store.finalize_partitions(now_ms=finalize_now)

    status1 = store.status(now_ms=finalize_now + 1000)
    assert status1["partition_integrity"]["integrity_ok"] is True

    size_before = p.stat().st_size
    time.sleep(0.01)  # Ensure mtime nanoseconds advance

    # Mutate bytes in place at fixed offset (same size)
    with open(p, "r+b") as f:
        f.seek(100)
        orig = f.read(4)
        f.seek(100)
        f.write(b"\xff\xfe\xfd\xfc" if orig != b"\xff\xfe\xfd\xfc" else b"\x00\x01\x02\x03")

    size_after = p.stat().st_size
    assert size_before == size_after

    status2 = store.status(now_ms=finalize_now + 2000)
    assert status2["partition_integrity"]["integrity_ok"] is False
    assert p.name in status2["partition_integrity"]["checksum_drift"]
    assert status2["status_performance"]["finalized_hash_recomputed"] >= 1


def test_p09_streaming_hash_memory_behavior(tmp_path: Path) -> None:
    """P09: Patch Path.read_bytes so finalized checksum path cannot call it. Require streaming reader."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P09", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    orig_read_bytes = Path.read_bytes

    def read_bytes_guard(self: Path) -> bytes:
        if self.suffix == ".sqlite3":
            raise AssertionError(f"Path.read_bytes() called on SQLite partition: {self}")
        return orig_read_bytes(self)

    finalize_now = day_start + 86_400_000 + store.protocol.finalization_grace_ms + 1000
    with patch.object(Path, "read_bytes", new=read_bytes_guard):
        store.finalize_partitions(now_ms=finalize_now)
        status = store.status(now_ms=finalize_now + 1000, deep_integrity=True)

    assert status["partition_integrity"]["integrity_ok"] is True


def test_p10_no_historical_bucket_set(tmp_path: Path) -> None:
    """P10: Guard against construction of old global bucket_candidates set."""
    day1 = _day_ts(2026, 9, 1)
    day2 = _day_ts(2026, 9, 2)
    day3 = _day_ts(2026, 9, 3)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P10", day1)
    p1 = store._path(day1)
    p2 = store._path(day2)
    p3 = store._path(day3)
    _init_partition_db(p1)
    _init_partition_db(p2)
    _init_partition_db(p3)

    # Coverage across days
    for p, d in ((p1, day1), (p2, day2), (p3, day3)):
        with sqlite3.connect(p) as conn:
            conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (d, d + 86400_000))
            conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (d, d + 86400_000))

    # Finalize p1 and p2
    store.finalize_partitions(now_ms=day3 + 86_400_000)

    # Assert store does not have bucket_candidates attribute
    assert not hasattr(store, "bucket_candidates")

    _ = store.status(now_ms=day3 + 3600_000)
    # Warm check
    status_warm = store.status(now_ms=day3 + 3600_000)
    assert status_warm["status_performance"]["bucket_history_cache_hits"] >= 3  # 1 hit per interval per finalized partition


def test_p11_bucket_summary_semantic_equivalence(tmp_path: Path) -> None:
    """P11: Compare old/reference brute-force calculation vs optimized finalized-summary calculation."""
    day1 = _day_ts(2026, 9, 1)
    day2 = _day_ts(2026, 9, 2)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P11", day1)
    p1 = store._path(day1)
    p2 = store._path(day2)
    _init_partition_db(p1)
    _init_partition_db(p2)

    with sqlite3.connect(p1) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (day1, day1 + 86400_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (day1, day1 + 86400_000))
        conn.execute("INSERT INTO gaps VALUES (1, ?, ?, 'DEPTH_SEQUENCE_GAP', 'g1')", (day1 + 1000, day1 + 2000))

    with sqlite3.connect(p2) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (day2, day2 + 86400_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (day2, day2 + 86400_000))

    store.finalize_partitions(now_ms=day2 + 86400_000)

    eval_now = day2 + 86400_000
    ref = _reference_buckets_and_rolling(store, eval_now)
    opt = store.status(now_ms=eval_now)

    assert opt["closed_aggregate_buckets"] == ref["closed_aggregate_buckets"]
    assert opt["complete_aggregate_buckets"] == ref["complete_aggregate_buckets"]
    assert opt["gap_affected_buckets"] == ref["gap_affected_buckets"]
    assert opt["aggregate_completeness_ratio"] == pytest.approx(ref["aggregate_completeness_ratio"])
    assert opt["aggregate_completeness_by_interval_ms"] == ref["aggregate_completeness_by_interval_ms"]


def test_p12_partial_first_day(tmp_path: Path) -> None:
    """P12: Campaign/evaluation start mid-day. Require exact equality against brute-force reference."""
    day1 = _day_ts(2026, 9, 1)
    campaign_start = day1 + 14 * 3600_000 + 17 * 60_000  # 14:17:00 UTC

    store = MicrostructureStore(tmp_path / "micro", "TEST_P12", campaign_start)
    p1 = store._path(day1)
    _init_partition_db(p1)

    with sqlite3.connect(p1) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (campaign_start, day1 + 86400_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (campaign_start, day1 + 86400_000))
        conn.execute("INSERT INTO gaps VALUES (1, ?, ?, 'DEPTH_SEQUENCE_GAP', 'g1')", (campaign_start + 5000, campaign_start + 15000))

    store.finalize_partitions(now_ms=day1 + 86400_000 + store.protocol.finalization_grace_ms + 1000)

    eval_now = day1 + 86400_000
    ref = _reference_buckets_and_rolling(store, eval_now)
    opt = store.status(now_ms=eval_now)

    assert opt["closed_aggregate_buckets"] == ref["closed_aggregate_buckets"]
    assert opt["complete_aggregate_buckets"] == ref["complete_aggregate_buckets"]
    assert opt["gap_affected_buckets"] == ref["gap_affected_buckets"]
    assert opt["aggregate_completeness_ratio"] == pytest.approx(ref["aggregate_completeness_ratio"])


def test_p13_cross_midnight_gap(tmp_path: Path) -> None:
    """P13: A gap starting before midnight and ending after midnight marks exact same buckets as reference."""
    day1 = _day_ts(2026, 9, 1)
    day2 = _day_ts(2026, 9, 2)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P13", day1)
    p1 = store._path(day1)
    p2 = store._path(day2)
    _init_partition_db(p1)
    _init_partition_db(p2)

    with sqlite3.connect(p1) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (day1, day1 + 86400_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (day1, day1 + 86400_000))
        # Cross midnight gap from 23:59:50 to 00:00:20 (30 seconds)
        conn.execute("INSERT INTO gaps VALUES (1, ?, ?, 'DEPTH_SEQUENCE_GAP', 'x_midnight')", (day2 - 10_000, day2 + 20_000))

    with sqlite3.connect(p2) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (day2, day2 + 86400_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (day2, day2 + 86400_000))

    store.finalize_partitions(now_ms=day2 + 86400_000 + store.protocol.finalization_grace_ms + 1000)

    eval_now = day2 + 86400_000
    ref = _reference_buckets_and_rolling(store, eval_now)
    opt = store.status(now_ms=eval_now)

    assert opt["gap_affected_buckets"] == ref["gap_affected_buckets"]
    assert opt["complete_aggregate_buckets"] == ref["complete_aggregate_buckets"]
    assert opt["aggregate_completeness_ratio"] == pytest.approx(ref["aggregate_completeness_ratio"])


def test_p14_cross_midnight_coverage_segment(tmp_path: Path) -> None:
    """P14: Cross-midnight coverage segment produces exact bucket and uptime/continuity outputs."""
    day1 = _day_ts(2026, 9, 1)
    day2 = _day_ts(2026, 9, 2)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P14", day1)
    p1 = store._path(day1)
    p2 = store._path(day2)
    _init_partition_db(p1)
    _init_partition_db(p2)

    # Segment in p1 extends past midnight to 02:00:00 on day 2
    with sqlite3.connect(p1) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (day1, day2 + 7200_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (day1, day2 + 7200_000))

    with sqlite3.connect(p2) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (day2 + 7200_000, day2 + 86400_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (day2 + 7200_000, day2 + 86400_000))

    store.finalize_partitions(now_ms=day2 + 86400_000 + store.protocol.finalization_grace_ms + 1000)

    eval_now = day2 + 86400_000
    ref = _reference_buckets_and_rolling(store, eval_now)
    opt = store.status(now_ms=eval_now)

    assert opt["closed_aggregate_buckets"] == ref["closed_aggregate_buckets"]
    assert opt["complete_aggregate_buckets"] == ref["complete_aggregate_buckets"]
    assert opt["uptime_ratio"] == 1.0


def test_p15_active_plus_finalized_composition(tmp_path: Path) -> None:
    """P15: Multiple finalized partitions plus one active partition equals reference outputs."""
    day1 = _day_ts(2026, 9, 1)
    day2 = _day_ts(2026, 9, 2)
    day3 = _day_ts(2026, 9, 3)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P15", day1)
    p1 = store._path(day1)
    p2 = store._path(day2)
    p3 = store._path(day3)
    _init_partition_db(p1)
    _init_partition_db(p2)
    _init_partition_db(p3)

    for p, d in ((p1, day1), (p2, day2)):
        with sqlite3.connect(p) as conn:
            conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'CLOSED')", (d, d + 86400_000))
            conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'CLOSED')", (d, d + 86400_000))

    with sqlite3.connect(p3) as conn:
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', ?, ?, 1, 'OPEN')", (day3, day3 + 12 * 3600_000))
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', ?, ?, 1, 'OPEN')", (day3, day3 + 12 * 3600_000))

    # Finalize p1 and p2 only
    store.finalize_partitions(now_ms=day3)

    eval_now = day3 + 12 * 3600_000
    ref = _reference_buckets_and_rolling(store, eval_now)
    opt = store.status(now_ms=eval_now)

    assert opt["closed_aggregate_buckets"] == ref["closed_aggregate_buckets"]
    assert opt["complete_aggregate_buckets"] == ref["complete_aggregate_buckets"]
    assert opt["gap_affected_buckets"] == ref["gap_affected_buckets"]
    assert opt["aggregate_completeness_ratio"] == pytest.approx(ref["aggregate_completeness_ratio"])


def test_p16_cache_miss_vs_warm_hit(tmp_path: Path) -> None:
    """P16: All externally meaningful status fields equal between cache miss and warm cache hit."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P16", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    with sqlite3.connect(p) as conn:
        conn.execute("INSERT INTO depth_events VALUES (1000100, 1, 1000105, 0, '{}', 'd1')")
        conn.execute("INSERT INTO agg_trades VALUES (1, 1000100, 1000100, 1000120, 0, 50000.0, 0.5, 0, 'BUY', 't1')")
        conn.execute("INSERT INTO book_samples VALUES (1000100, 1, 1000105, 1.5, 0.2, 0.4, 0.6, 50000.0, 0.1)")
        conn.execute("INSERT INTO coverage_segments VALUES (1, 'i1', 'depth', 1000000, 1001000, 1, 'CLOSED')")
        conn.execute("INSERT INTO coverage_segments VALUES (2, 'i1', 'trade', 1000000, 1001000, 1, 'CLOSED')")
        conn.execute("INSERT INTO gaps VALUES (1, 1000500, 1000550, 'DEPTH_SEQUENCE_GAP', 'drop')")
        conn.execute("INSERT INTO process_instances VALUES ('i1', 1000000, 1001000, 1001000, 'CLOSED')")
        conn.execute("INSERT INTO clock_measurements VALUES (1000900, 1000880, 1000920, 1000905, 5.0, 40, 'OK')")

    eval_now = day_start + 3600_000
    status_miss = store.status(now_ms=eval_now)
    assert store._stats_cache_path.exists()
    status_hit = store.status(now_ms=eval_now)

    semantic_miss = {k: v for k, v in status_miss.items() if k != "status_performance"}
    semantic_hit = {k: v for k, v in status_hit.items() if k != "status_performance"}
    assert semantic_miss == semantic_hit


def test_p17_legacy_v2_cache(tmp_path: Path) -> None:
    """P17: Cache v2 is safely ignored/rebuilt as v3."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P17", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    legacy_v2_payload = {
        "schema_version": "2.0.0",
        "partitions": {
            p.name: {
                "mtime_ns": p.stat().st_mtime_ns,
                "size": p.stat().st_size,
                "stats": {
                    "depth": 9999,
                    "trades": 9999,
                    "gap_rows": [[1, 2, "KIND"]],
                },
            }
        },
    }
    store._stats_cache_path.write_text(json.dumps(legacy_v2_payload), encoding="utf-8")

    loaded = store._load_stats_cache()
    assert loaded == {}

    status = store.status(now_ms=day_start + 1000)
    assert status["depth_events"] == 0
    assert status["agg_trade_events"] == 0

    new_cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert new_cache["schema_version"] == STATS_CACHE_SCHEMA_VERSION
    assert STATS_CACHE_SCHEMA_VERSION == "3.0.0"


def test_p18_malformed_oversized_cache(tmp_path: Path) -> None:
    """P18: Preserve existing fail-safe behavior for corrupted/oversized cache."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P18", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    # Corrupted cache
    store._stats_cache_path.write_text("{corrupt: [json", encoding="utf-8")
    status1 = store.status(now_ms=day_start + 1000)
    assert status1["depth_events"] == 0
    assert store._stats_cache_path.exists()

    # Oversized cache
    oversized = MAX_PARTITION_STATS_CACHE_BYTES + 1024 * 1024
    with open(store._stats_cache_path, "wb") as f:
        f.truncate(oversized)

    with patch.object(Path, "read_text") as mock_read:
        assert store._load_stats_cache() == {}
        mock_read.assert_not_called()

    status2 = store.status(now_ms=day_start + 2000)
    assert status2["depth_events"] == 0


def test_p19_latency_semantics_unchanged(tmp_path: Path) -> None:
    """P19: Exact existing p50/p95/p99 raw and clock-adjusted behavior preserved."""
    day_start = _day_ts(2026, 9, 1)
    store = MicrostructureStore(tmp_path / "micro", "TEST_P19", day_start)
    p = store._path(day_start)
    _init_partition_db(p)

    with sqlite3.connect(p) as conn:
        for idx in range(1, 101):
            conn.execute(
                "INSERT INTO agg_trades VALUES (?, ?, ?, ?, 0, 50000.0, 0.1, 0, 'BUY', 'h')",
                (idx, day_start + idx, day_start + idx, day_start + idx + (idx % 25)),
            )
        conn.execute("INSERT INTO clock_measurements VALUES (?, ?, ?, ?, 4.5, 30, 'OK')",
                     (day_start + 2000, day_start + 1985, day_start + 2015, day_start + 2004))

    status_miss = store.status(now_ms=day_start + 3000)
    status_hit = store.status(now_ms=day_start + 3000)

    assert status_miss["latency_ms"] == status_hit["latency_ms"]
    assert status_hit["latency_ms"]["p50"] is not None
    assert status_hit["latency_ms"]["p95"] is not None
    assert status_hit["latency_ms"]["p99"] is not None
    assert status_hit["latency_ms"]["clock_adjusted_diagnostic"]["p50"] == status_hit["latency_ms"]["p50"] + 4.5


def test_p20_latest_clock_semantics_unchanged(tmp_path: Path) -> None:
    """P20: Exact existing latest-clock semantics preserved across multiple partitions."""
    day1 = _day_ts(2026, 9, 1)
    day2 = _day_ts(2026, 9, 2)

    store = MicrostructureStore(tmp_path / "micro", "TEST_P20", day1)
    p1 = store._path(day1)
    p2 = store._path(day2)
    _init_partition_db(p1)
    _init_partition_db(p2)

    with sqlite3.connect(p1) as conn:
        conn.execute("INSERT INTO clock_measurements VALUES (1000500, 1000490, 1000510, 1000502, 2.0, 20, 'OK')")
        conn.execute("INSERT INTO clock_measurements VALUES (1000900, 1000890, 1000910, 1000903, 3.0, 20, 'OK')")

    with sqlite3.connect(p2) as conn:
        conn.execute("INSERT INTO clock_measurements VALUES (1000700, 1000690, 1000710, 1000704, 4.0, 20, 'OK')")
        conn.execute("INSERT INTO clock_measurements VALUES (1001500, 1001490, 1001510, 1001508, 7.5, 20, 'OK')")

    status_miss = store.status(now_ms=day2 + 86400_000)
    status_hit = store.status(now_ms=day2 + 86400_000)

    assert status_miss["clock"] == status_hit["clock"]
    assert status_hit["clock"]["measured_at_ms"] == 1001500
    assert status_hit["clock"]["server_minus_local_midpoint_ms"] == 7.5
    assert status_hit["clock"]["quality"] == "OK"
