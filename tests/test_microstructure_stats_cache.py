"""Tests for MicrostructureStore partition statistics cache-v3.

Covers requirements C01 through C12 for partition stats cache bloat repair:
- C01: one key per partition
- C02: no revision-key leak
- C03: multiple files bounded
- C04: deleted partition pruned
- C05: changed file overwrites same entry
- C06: legacy cache discarded
- C07: oversized cache not parsed
- C08: malformed cache harmless
- C09: cache miss vs cache hit semantic equivalence
- C10: latency percentiles unchanged
- C11: latest clock unchanged
- C12: bounded repeated growth
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from btc_quant_agent.microstructure import (
    MAX_PARTITION_STATS_CACHE_BYTES,
    STATS_CACHE_SCHEMA_VERSION,
    MicrostructureStore,
)


def _init_partition_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE depth_events (event_time_ms INTEGER, final_update_id INTEGER, receive_time_ms INTEGER, receive_monotonic_ns INTEGER, payload_json TEXT, payload_hash TEXT, PRIMARY KEY(event_time_ms, final_update_id))")
        conn.execute("CREATE TABLE agg_trades (aggregate_trade_id INTEGER PRIMARY KEY, event_time_ms INTEGER, transaction_time_ms INTEGER, receive_time_ms INTEGER, receive_monotonic_ns INTEGER, price REAL, quantity REAL, buyer_is_maker INTEGER, aggressive_side TEXT, payload_hash TEXT)")
        conn.execute("CREATE TABLE book_samples (event_time_ms INTEGER, final_update_id INTEGER, receive_time_ms INTEGER, spread_bps REAL, top1_imbalance REAL, top5_imbalance REAL, top20_imbalance REAL, microprice REAL, ofi REAL, PRIMARY KEY(event_time_ms, final_update_id))")
        conn.execute("CREATE TABLE aggregates (interval_ms INTEGER, bucket_start_ms INTEGER, trade_count INTEGER DEFAULT 0, buy_quantity REAL DEFAULT 0, sell_quantity REAL DEFAULT 0, buy_notional REAL DEFAULT 0, sell_notional REAL DEFAULT 0, book_sample_count INTEGER DEFAULT 0, spread_bps_sum REAL DEFAULT 0, top1_imbalance_sum REAL DEFAULT 0, top5_imbalance_sum REAL DEFAULT 0, top20_imbalance_sum REAL DEFAULT 0, ofi_sum REAL DEFAULT 0, gap_count INTEGER DEFAULT 0, PRIMARY KEY(interval_ms, bucket_start_ms))")
        conn.execute("CREATE TABLE audit_counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)")
        conn.execute("CREATE TABLE coverage_segments (id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id TEXT, stream TEXT, start_ms INTEGER, end_ms INTEGER, sequence_valid INTEGER, status TEXT)")
        conn.execute("CREATE TABLE gaps (id INTEGER PRIMARY KEY, start_ms INTEGER, end_ms INTEGER, kind TEXT, detail TEXT)")
        conn.execute("CREATE TABLE process_instances (instance_id TEXT PRIMARY KEY, start_ms INTEGER, last_heartbeat_ms INTEGER, end_ms INTEGER, status TEXT)")
        conn.execute("CREATE TABLE clock_measurements (measured_at_ms INTEGER PRIMARY KEY, request_send_ms INTEGER, response_receive_ms INTEGER, server_time_ms INTEGER, offset_ms REAL, rtt_ms INTEGER, quality TEXT)")


def test_c01_one_key_per_partition(tmp_path: Path) -> None:
    """C01: Repeatedly mutate same SQLite partition, cache entry count remains 1."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p_path = store._path(1_000_000)
    _init_partition_db(p_path)

    for i in range(1, 6):
        with sqlite3.connect(p_path) as conn:
            conn.execute(
                "INSERT INTO agg_trades (aggregate_trade_id, event_time_ms, transaction_time_ms, receive_time_ms, receive_monotonic_ns, price, quantity, buyer_is_maker, aggressive_side, payload_hash) VALUES (?, ?, ?, ?, ?, 100.0, 1.0, 0, 'BUY', 'h')",
                (i, 1_000_000 + i * 100, 1_000_000 + i * 100, 1_000_000 + i * 100 + 5, 0),
            )
        status = store.status(now_ms=1_000_000 + i * 1000)
        assert status["agg_trade_events"] == i
        cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
        assert len(cache["partitions"]) == 1
        assert p_path.name in cache["partitions"]


def test_c02_no_revision_key_leak(tmp_path: Path) -> None:
    """C02: Assert no persisted key contains the old filename:mtime:size pattern."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p_path = store._path(1_000_000)
    _init_partition_db(p_path)

    for i in range(1, 4):
        with sqlite3.connect(p_path) as conn:
            conn.execute(
                "INSERT INTO agg_trades (aggregate_trade_id, event_time_ms, transaction_time_ms, receive_time_ms, receive_monotonic_ns, price, quantity, buyer_is_maker, aggressive_side, payload_hash) VALUES (?, ?, ?, ?, ?, 100.0, 1.0, 0, 'BUY', 'h')",
                (i, 1_000_000 + i * 10, 1_000_000 + i * 10, 1_000_000 + i * 10 + 2, 0),
            )
        store.status(now_ms=1_000_000 + i * 1000)

    cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    for key in cache["partitions"]:
        assert ":" not in key
        assert key.endswith(".sqlite3")
        assert key == p_path.name


def test_c03_multiple_files_bounded(tmp_path: Path) -> None:
    """C03: With N partition SQLite files, cache entries <= N (exactly N after scans)."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    timestamps = [1_000_000, 1_000_000 + 86_400_000, 1_000_000 + 2 * 86_400_000]
    paths = [store._path(ts) for ts in timestamps]
    for p in paths:
        _init_partition_db(p)

    store.status(now_ms=timestamps[-1] + 1000)
    cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert len(cache["partitions"]) == 3
    assert set(cache["partitions"].keys()) == {p.name for p in paths}


def test_c04_deleted_partition_pruned(tmp_path: Path) -> None:
    """C04: Create two partitions, remove one disposable TEST partition, assert deleted filename removed."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p1 = store._path(1_000_000)
    p2 = store._path(1_000_000 + 86_400_000)
    _init_partition_db(p1)
    _init_partition_db(p2)

    store.status(now_ms=1_000_000 + 86_400_000 + 1000)
    cache1 = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert p1.name in cache1["partitions"]
    assert p2.name in cache1["partitions"]

    # Delete disposable test partition p2
    p2.unlink()
    store.status(now_ms=1_000_000 + 86_400_000 + 2000)
    cache2 = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert p1.name in cache2["partitions"]
    assert p2.name not in cache2["partitions"]
    assert len(cache2["partitions"]) == 1


def test_c05_changed_file_overwrites_same_entry(tmp_path: Path) -> None:
    """C05: Change mtime/size and verify signature and stats are replaced under same filename."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)
    store.status(now_ms=1_001_000)

    cache1 = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    entry1 = cache1["partitions"][p.name]
    assert entry1["stats"]["trades"] == 0

    # Insert enough rows to allocate new SQLite pages and ensure mtime/size change
    with sqlite3.connect(p) as conn:
        for idx in range(1, 1000):
            conn.execute(
                "INSERT INTO agg_trades (aggregate_trade_id, event_time_ms, transaction_time_ms, receive_time_ms, receive_monotonic_ns, price, quantity, buyer_is_maker, aggressive_side, payload_hash) VALUES (?, 1000000, 1000000, 1000005, 0, 100.0, 1.0, 0, 'BUY', 'h')",
                (idx,)
            )

    store.status(now_ms=1_002_000)
    cache2 = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert len(cache2["partitions"]) == 1
    entry2 = cache2["partitions"][p.name]
    assert entry2["stats"]["trades"] == 999
    assert (entry2["mtime_ns"], entry2["size"]) != (entry1["mtime_ns"], entry1["size"])
    assert entry2["size"] > entry1["size"]


def test_c06_legacy_cache_discarded(tmp_path: Path) -> None:
    """C06: Provide old unversioned cache structure and verify it is ignored and rebuilt."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)

    legacy_payload = {
        f"{p.name}:12345:67890": {
            "depth": 999,
            "trades": 999,
        }
    }
    store._stats_cache_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    loaded = store._load_stats_cache()
    assert loaded == {}

    status = store.status(now_ms=1_001_000)
    assert status["depth_events"] == 0
    assert status["agg_trade_events"] == 0

    new_cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert new_cache.get("schema_version") == STATS_CACHE_SCHEMA_VERSION
    assert p.name in new_cache["partitions"]


def test_c07_oversized_cache_not_parsed(tmp_path: Path) -> None:
    """C07: Oversized test cache above defensive threshold treated as miss without full JSON parse."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)

    # Use truncate to create a sparse file of size MAX + 1 MB
    oversized_bytes = MAX_PARTITION_STATS_CACHE_BYTES + 1024 * 1024
    with open(store._stats_cache_path, "wb") as f:
        f.truncate(oversized_bytes)

    with patch.object(Path, "read_text") as mock_read:
        loaded = store._load_stats_cache()
        assert loaded == {}
        mock_read.assert_not_called()

    status = store.status(now_ms=1_001_000)
    assert status["depth_events"] == 0
    # Defensive guard also unlinked the oversized file or replaced it with valid cache
    cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert cache["schema_version"] == STATS_CACHE_SCHEMA_VERSION


def test_c08_malformed_cache_harmless(tmp_path: Path) -> None:
    """C08: Invalid JSON does not corrupt status; it rebuilds safely from SQLite."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)
    with sqlite3.connect(p) as conn:
        conn.execute(
            "INSERT INTO agg_trades (aggregate_trade_id, event_time_ms, transaction_time_ms, receive_time_ms, receive_monotonic_ns, price, quantity, buyer_is_maker, aggressive_side, payload_hash) VALUES (1, 1000000, 1000000, 1000010, 0, 100.0, 1.0, 0, 'BUY', 'h')"
        )

    store._stats_cache_path.write_text("{\"corrupted\": [truncated json...", encoding="utf-8")

    status = store.status(now_ms=1_001_000)
    assert status["agg_trade_events"] == 1
    new_cache = json.loads(store._stats_cache_path.read_text(encoding="utf-8"))
    assert new_cache["schema_version"] == STATS_CACHE_SCHEMA_VERSION
    assert new_cache["partitions"][p.name]["stats"]["trades"] == 1


def test_c09_cache_miss_vs_cache_hit_semantic_equivalence(tmp_path: Path) -> None:
    """C09: status_without_cache == status_with_cache for all externally meaningful fields."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)

    with sqlite3.connect(p) as conn:
        conn.execute("INSERT INTO depth_events VALUES (1000100, 1, 1000105, 0, '{}', 'd1')")
        conn.execute("INSERT INTO agg_trades VALUES (1, 1000100, 1000100, 1000120, 0, 50000.0, 0.5, 0, 'BUY', 't1')")
        conn.execute("INSERT INTO book_samples VALUES (1000100, 1, 1000105, 1.5, 0.2, 0.4, 0.6, 50000.0, 0.1)")
        conn.execute("INSERT INTO coverage_segments (instance_id, stream, start_ms, end_ms, sequence_valid, status) VALUES ('inst1', 'depth', 1000000, 1001000, 1, 'CLOSED')")
        conn.execute("INSERT INTO coverage_segments (instance_id, stream, start_ms, end_ms, sequence_valid, status) VALUES ('inst1', 'trade', 1000000, 1001000, 1, 'CLOSED')")
        conn.execute("INSERT INTO gaps (id, start_ms, end_ms, kind, detail) VALUES (1, 1000500, 1000550, 'DEPTH_SEQUENCE_GAP', 'drop')")
        conn.execute("INSERT INTO process_instances VALUES ('inst1', 1000000, 1001000, 1001000, 'CLOSED')")
        conn.execute("INSERT INTO clock_measurements VALUES (1000900, 1000880, 1000920, 1000905, 5.0, 40, 'OK')")

    eval_now = 1_002_000
    status_miss = store.status(now_ms=eval_now)
    assert store._stats_cache_path.exists()
    status_hit = store.status(now_ms=eval_now)

    assert status_miss == status_hit


def test_c10_latency_percentiles_unchanged(tmp_path: Path) -> None:
    """C10: Explicitly verify p50/p95/p99 raw and clock-adjusted diagnostics are identical across miss/hit."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)

    with sqlite3.connect(p) as conn:
        for idx in range(1, 101):
            conn.execute(
                "INSERT INTO agg_trades VALUES (?, ?, ?, ?, 0, 50000.0, 0.1, 0, 'BUY', 'h')",
                (idx, 1_000_000 + idx, 1_000_000 + idx, 1_000_000 + idx + (idx % 20),)
            )
        conn.execute("INSERT INTO clock_measurements VALUES (1000900, 1000880, 1000920, 1000905, 3.5, 40, 'OK')")

    status_miss = store.status(now_ms=1_002_000)
    status_hit = store.status(now_ms=1_002_000)

    assert status_miss["latency_ms"] == status_hit["latency_ms"]
    assert status_hit["latency_ms"]["p50"] is not None
    assert status_hit["latency_ms"]["p95"] is not None
    assert status_hit["latency_ms"]["p99"] is not None
    assert status_miss["latency_ms"]["clock_adjusted_diagnostic"] == status_hit["latency_ms"]["clock_adjusted_diagnostic"]


def test_c11_latest_clock_unchanged(tmp_path: Path) -> None:
    """C11: Multiple clock measurements across multiple partitions produce same globally latest clock."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p1 = store._path(1_000_000)
    p2 = store._path(1_000_000 + 86_400_000)
    _init_partition_db(p1)
    _init_partition_db(p2)

    with sqlite3.connect(p1) as conn:
        conn.execute("INSERT INTO clock_measurements VALUES (1000500, 1000490, 1000510, 1000502, 2.0, 20, 'OK')")
        conn.execute("INSERT INTO clock_measurements VALUES (1000900, 1000890, 1000910, 1000903, 3.0, 20, 'OK')")

    with sqlite3.connect(p2) as conn:
        conn.execute("INSERT INTO clock_measurements VALUES (1000700, 1000690, 1000710, 1000704, 4.0, 20, 'OK')")
        conn.execute("INSERT INTO clock_measurements VALUES (1001200, 1001190, 1001210, 1001208, 8.0, 20, 'OK')")

    status_miss = store.status(now_ms=1002000 + 86_400_000)
    status_hit = store.status(now_ms=1002000 + 86_400_000)

    assert status_miss["clock"] == status_hit["clock"]
    assert status_hit["clock"]["measured_at_ms"] == 1001200
    assert status_hit["clock"]["server_minus_local_midpoint_ms"] == 8.0
    assert status_hit["clock"]["quality"] == "OK"


def test_c12_bounded_repeated_growth(tmp_path: Path) -> None:
    """C12: Repeated status calls against one mutating partition do not grow linearly with revisions."""
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    p = store._path(1_000_000)
    _init_partition_db(p)

    # Initial revision
    with sqlite3.connect(p) as conn:
        conn.execute(
            "INSERT INTO agg_trades VALUES (1, 1000000, 1000000, 1000005, 0, 100.0, 1.0, 0, 'BUY', 'h')"
        )
    store.status(now_ms=1_001_000)
    initial_cache_size = store._stats_cache_path.stat().st_size

    # Mutate 40 times and call status
    for i in range(2, 42):
        with sqlite3.connect(p) as conn:
            conn.execute(
                "INSERT INTO agg_trades VALUES (?, ?, ?, ?, 0, 100.0, 1.0, 0, 'BUY', 'h')",
                (i, 1_000_000 + i, 1_000_000 + i, 1_000_000 + i + 5),
            )
        store.status(now_ms=1_001_000 + i * 100)

    final_cache_size = store._stats_cache_path.stat().st_size
    # Cache size after 40 revisions should NOT be ~40x initial size.
    # It must remain bounded (e.g. <= 2x initial size + tolerance).
    assert final_cache_size <= initial_cache_size * 2 + 512
