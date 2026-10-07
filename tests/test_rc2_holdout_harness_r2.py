"""Validation harness R2 qualification test suite.

Covers:
- Event-time normalization unit tests
- Known FIL regression (FILUSDT-metrics-2026-09-06.zip)
- Permutation invariance across row orderings
- Cache identity authority and mismatch detection
- Script identity mismatch and mutation detection
- No-new-protected-symbol firewall
- Replay determinism and context smoke
"""

from __future__ import annotations

import csv
import hashlib
import io
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.rc2.validation.source_normalizer import (
    CacheAuthorityError,
    CacheIdentity,
    ProtectedSymbolFirewallViolation,
    RunnerIdentityMismatchError,
    assert_all_symbols_allowed,
    assert_symbol_allowed,
    capture_execution_identity,
    compute_cache_identity,
    normalize_metrics_rows,
    parse_event_timestamp,
    save_authorized_cache,
    validate_and_load_cache,
    verify_execution_identity,
    verify_fil_20260906_regression,
    verify_permutation_invariance,
)

ROOT = Path(__file__).resolve().parents[1]
CACHED_FIL_ZIP = (
    Path("/tmp/rc2_r1_1_source_cache")
    / hashlib.sha256(
        b"https://data.binance.vision/data/futures/um/daily/metrics/FILUSDT/FILUSDT-metrics-2026-09-06.zip"
    ).hexdigest()
)


def test_protected_symbol_firewall() -> None:
    # Allowed symbols must not raise
    assert_symbol_allowed("FILUSDT")
    assert_symbol_allowed("btcusdt")
    assert_symbol_allowed("ADA")
    assert_symbol_allowed("ETH")
    assert_symbol_allowed("OPUSDT")

    allowed_set = ["FILUSDT", "ETCUSDT", "BTCUSDT", "ETHUSDT"]
    assert_all_symbols_allowed(allowed_set)

    # Protected or unknown symbols must fail closed immediately
    with pytest.raises(ProtectedSymbolFirewallViolation):
        assert_symbol_allowed("UNAUTHORIZED_COIN")

    with pytest.raises(ProtectedSymbolFirewallViolation):
        assert_symbol_allowed("PROTECTED_SECRET_USDT")

    with pytest.raises(ProtectedSymbolFirewallViolation):
        assert_all_symbols_allowed(["BTCUSDT", "FORBIDDEN_ASSET"])


def test_parse_event_timestamp() -> None:
    ts_str = "2026-09-06 17:55:00"
    ts = parse_event_timestamp(ts_str)
    dt = datetime.fromtimestamp(ts / 1000, UTC)
    assert dt.strftime("%Y-%m-%d %H:%M:%S") == ts_str
    assert parse_event_timestamp(ts) == ts


def test_event_time_normalization_unit() -> None:
    header = [
        "create_time",
        "symbol",
        "sum_open_interest",
        "sum_open_interest_value",
        "count_toptrader_long_short_ratio",
        "sum_toptrader_long_short_ratio",
        "count_long_short_ratio",
        "sum_taker_long_short_vol_ratio",
    ]

    # Construct out-of-order rows for 17h and 18h UTC buckets
    raw_rows = [
        ["2026-09-06 17:30:00", "TEST", "100.0", "1.0", "1.1", "1.2", "1.3", "0.95"],
        ["2026-09-06 17:55:00", "TEST", "150.0", "1.0", "1.1", "1.2", "1.3", "0.98"],
        ["2026-09-06 17:15:00", "TEST", "90.0", "1.0", "1.1", "1.2", "1.3", "0.91"],
        ["2026-09-06 17:35:00", "TEST", "110.0", "1.0", "1.1", "1.2", "1.3", "0.96"],
        # Duplicate timestamp: should be deterministically deduplicated
        ["2026-09-06 17:35:00", "TEST", "110.0", "1.0", "1.1", "1.2", "1.3", "0.96"],
        ["2026-09-06 18:05:00", "TEST", "200.0", "1.0", "1.1", "1.2", "1.3", "1.05"],
        ["2026-09-06 18:25:00", "TEST", "220.0", "1.0", "1.1", "1.2", "1.3", "1.10"],
    ]

    tf_start = parse_event_timestamp("2026-09-06 17:00:00")
    data_end = parse_event_timestamp("2026-09-06 19:00:00")

    result = normalize_metrics_rows(raw_rows, header, tf_start, data_end)

    # Hourly buckets: 17h and 18h
    oi_hist = result["oi_hist"]
    assert len(oi_hist) == 2

    # In 17h bucket: 17:55 must be chosen (sumOpenInterest == 150.0), NOT 17:35
    assert oi_hist[0]["timestamp"] == parse_event_timestamp("2026-09-06 17:55:00")
    assert oi_hist[0]["sumOpenInterest"] == 150.0

    # In 18h bucket: 18:25 must be chosen
    assert oi_hist[1]["timestamp"] == parse_event_timestamp("2026-09-06 18:25:00")
    assert oi_hist[1]["sumOpenInterest"] == 220.0

    # Taker 15m buckets
    taker_hist = result["taker_hist"]
    # 17:15, 17:30, 17:35, 17:55, 18:05, 18:25
    assert len(taker_hist) >= 4


def test_known_fil_regression() -> None:
    assert CACHED_FIL_ZIP.exists(), f"Cached archive {CACHED_FIL_ZIP} missing"
    archive_bytes = CACHED_FIL_ZIP.read_bytes()
    report = verify_fil_20260906_regression(archive_bytes)

    assert report["regression_verified"] is True
    assert report["archive_order_tail_observation"] == "2026-09-06 17:35:00"
    assert report["normalized_selected_observation"] == "2026-09-06 17:55:00"
    assert report["expected_selected_observation"] == "2026-09-06 17:55:00"
    assert report["archive_flaw_discrepancy_minutes"] == 20


def test_permutation_invariance_on_fil_archive() -> None:
    assert CACHED_FIL_ZIP.exists(), f"Cached archive {CACHED_FIL_ZIP} missing"
    archive_bytes = CACHED_FIL_ZIP.read_bytes()

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        raw_csv = z.read(csv_name).decode("utf-8-sig")

    rows = list(csv.reader(io.StringIO(raw_csv)))
    header = rows[0]
    metric_rows = [r for r in rows[1:] if r and r[0].lower() != "create_time"]

    tf_start = int(datetime(2026, 9, 6, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    data_end = int(datetime(2026, 9, 6, 23, 59, 59, tzinfo=UTC).timestamp() * 1000)

    proof = verify_permutation_invariance(
        metric_rows, header, tf_start, data_end, num_permutations=5, seed=101
    )
    assert proof["permutation_invariance_proven"] is True
    assert proof["tested_order_count"] == 7
    assert proof["original_combined_digest"] == proof["reversed_combined_digest"]
    for p in proof["permutations"]:
        assert p["digests_match"] is True
        assert p["combined_digest"] == proof["original_combined_digest"]


def test_cache_identity_and_authority(tmp_path: Path) -> None:
    time_window = {"first_step_ms": 1000, "data_end_ms": 2000}
    symbol_roles = {"targets": ["FILUSDT"], "references": ["BTCUSDT"]}
    source_archives = [{"url": "https://example.com/archive.zip", "sha256": "abcdef"}]
    test_script = tmp_path / "script.py"
    test_script.write_text("print('test')")

    identity = compute_cache_identity(
        time_window=time_window,
        symbol_roles=symbol_roles,
        source_archives=source_archives,
        script_paths=[test_script],
    )

    cache_file = tmp_path / "cache.json.gz"
    raw_data = {"test_key": "test_value"}
    save_authorized_cache(cache_file, identity, raw_data)

    # 1. Same identity -> reusable
    loaded, audit = validate_and_load_cache(cache_file, identity)
    assert loaded == raw_data
    assert audit["reusable"] is True

    # 2. Schema version change -> reject
    altered_identity = CacheIdentity(
        schema_version=identity.schema_version,
        parser_schema_version="STALE_PARSER_V1",
        time_window=identity.time_window,
        symbol_roles=identity.symbol_roles,
        harness_code_hashes=identity.harness_code_hashes,
        source_archives_count=identity.source_archives_count,
        source_archives_digest=identity.source_archives_digest,
    )
    with pytest.raises(CacheAuthorityError):
        validate_and_load_cache(cache_file, altered_identity, on_mismatch="fail_closed")

    loaded_rebuild, audit_rebuild = validate_and_load_cache(
        cache_file, altered_identity, on_mismatch="rebuild"
    )
    assert loaded_rebuild is None
    assert audit_rebuild["reusable"] is False
    assert any("PARSER_SCHEMA_VERSION" in m for m in audit_rebuild["mismatch_reasons"])

    # 3. Source digest change -> reject
    altered_source_identity = CacheIdentity(
        schema_version=identity.schema_version,
        parser_schema_version=identity.parser_schema_version,
        time_window=identity.time_window,
        symbol_roles=identity.symbol_roles,
        harness_code_hashes=identity.harness_code_hashes,
        source_archives_count=identity.source_archives_count,
        source_archives_digest="mismatched_source_digest",
    )
    loaded_rebuild2, audit_rebuild2 = validate_and_load_cache(
        cache_file, altered_source_identity, on_mismatch="rebuild"
    )
    assert loaded_rebuild2 is None
    assert any("SOURCE_ARCHIVES_DIGEST" in m for m in audit_rebuild2["mismatch_reasons"])


def test_script_identity_and_mutation(tmp_path: Path) -> None:
    script = tmp_path / "test_runner.py"
    script.write_text("INITIAL_STATE = 1")

    # Use current repo root and current branch
    import subprocess
    current_branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()

    pre_id = capture_execution_identity(
        task_id="TEST_TASK",
        root=ROOT,
        expected_branch=current_branch,
        script_paths=[script],
    )

    # Without mutation, verify passes
    verified = verify_execution_identity(pre_id, root=ROOT, script_paths=[script])
    assert verified["exact_runner_identity_verified"] is True

    # Mutate script
    script.write_text("MUTATED_STATE = 2")
    with pytest.raises(RunnerIdentityMismatchError) as exc_info:
        verify_execution_identity(pre_id, root=ROOT, script_paths=[script])
    assert "SCRIPT_HASHES_MISMATCH" in str(exc_info.value)


def test_context_smoke_and_pit_invariance() -> None:
    import unittest.mock

    from btc_quant_agent.domain import Candle
    from btc_quant_agent.market_watch.config import MarketWatchConfig
    from btc_quant_agent.market_watch.replay import (
        HistoricalReplayClient,
        OOSPartitionSpec,
        ReplayDataset,
        SymbolReplaySeries,
        _InMemoryReplayStateStore,
    )
    from btc_quant_agent.market_watch.scanner import MarketWatchScanner

    first_step = 1_788_717_599_999
    targets = ("FILUSDT", "ETCUSDT")
    references = ("BTCUSDT", "ETHUSDT")
    all_syms = targets + references

    series_map: dict[str, SymbolReplaySeries] = {}
    for sym in all_syms:
        c_15m = [
            Candle(
                sym,
                "15m",
                first_step - (i + 1) * 900_000 + 1,
                first_step - i * 900_000,
                100.0,
                101.0,
                99.0,
                100.0,
                500.0,
            )
            for i in range(350, 0, -1)
        ]
        c_1h = [
            Candle(
                sym,
                "1h",
                first_step - (i + 1) * 3_600_000 + 1,
                first_step - i * 3_600_000,
                100.0,
                101.0,
                99.0,
                100.0,
                2000.0,
            )
            for i in range(350, 0, -1)
        ]
        c_4h = [
            Candle(
                sym,
                "4h",
                first_step - (i + 1) * 14_400_000 + 1,
                first_step - i * 14_400_000,
                100.0,
                101.0,
                99.0,
                100.0,
                8000.0,
            )
            for i in range(350, 0, -1)
        ]
        c_1m = [
            Candle(
                sym,
                "1m",
                first_step - (i + 1) * 60_000 + 1,
                first_step - i * 60_000,
                100.0,
                100.5,
                99.5,
                100.0,
                50.0,
            )
            for i in range(100, 0, -1)
        ]
        oi = [{"timestamp": first_step - i * 3_600_000, "sumOpenInterest": 1000.0} for i in range(20, -1, -1)]
        taker = [{"timestamp": first_step - i * 900_000, "buySellRatio": 1.05} for i in range(20, -1, -1)]
        gls = [{"timestamp": first_step - i * 3_600_000, "longShortRatio": 1.10} for i in range(20, -1, -1)]
        top_pos = [{"timestamp": first_step - i * 3_600_000, "longShortRatio": 1.15} for i in range(20, -1, -1)]
        top_acc = [{"timestamp": first_step - i * 3_600_000, "longShortRatio": 1.12} for i in range(20, -1, -1)]
        basis = [{"timestamp": first_step - i * 300_000, "basisRate": 0.0001} for i in range(20, -1, -1)]
        funding = [{"funding_time_ms": first_step - 3_600_000, "funding_rate": 0.0001, "mark_price": None}]

        series_map[sym] = SymbolReplaySeries(
            symbol=sym,
            klines_15m=tuple(c_15m),
            klines_1h=tuple(c_1h),
            klines_4h=tuple(c_4h),
            klines_1m=tuple(c_1m),
            funding_rates=tuple(funding),
            oi_hist=tuple(oi),
            taker_hist=tuple(taker),
            gls_hist=tuple(gls),
            top_pos_hist=tuple(top_pos),
            top_acc_hist=tuple(top_acc),
            basis_hist=tuple(basis),
        )

    p1 = (first_step + 1000, first_step + 2000)
    p2 = (first_step + 2000, first_step + 3000)
    p3 = (first_step + 3000, first_step + 4000)
    ds = ReplayDataset(
        symbols=targets,
        series_by_symbol=series_map,
        step_timestamps_ms=(first_step,),
        partitions=(
            OOSPartitionSpec("P1", first_step - 1000, first_step, *p1),
            OOSPartitionSpec("P2", first_step - 1000, first_step, *p2),
            OOSPartitionSpec("P3", first_step - 1000, first_step, *p3),
        ),
        data_end_ms=first_step + 100_000,
    )

    client = HistoricalReplayClient(ds, first_step, allow_synthetic_1m_for_tests=False)
    scanner = MarketWatchScanner(MarketWatchConfig(), client, _InMemoryReplayStateStore())

    with unittest.mock.patch(
        "btc_quant_agent.market_watch.scanner.time.time", return_value=first_step / 1000
    ):
        assessments, _ = scanner.scan_universe(symbols=targets, notify=False)

    assert len(assessments) == len(targets)
    assert client.pit_violations_count == 0
    assert client.authentic_1m_queries_count == 0
    assert all(r in ds.series_by_symbol for r in references)

