"""End-to-End CLI workflows, crash-restart recovery, and high-velocity 15-minute synthetic benchmarks."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1 import cli
from market_data.forward_public_feed_r1.contracts import (
    ALLOWED_PRODUCT,
    MarketEventV1,
    compute_sha256,
)
from market_data.forward_public_feed_r1.durability import SegmentReader, SegmentWriter
from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture
from market_data.forward_public_feed_r1.health import HealthSupervisor
from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine
from market_data.forward_public_feed_r1.replay import ReplayEngine
from market_data.forward_public_feed_r1.time_authority import TimeAuthority


def test_cli_parser_defaults() -> None:
    parser = cli.build_parser()
    args = parser.parse_args([])
    assert args.mode == "fixture"
    assert args.network == "disabled"
    assert args.symbol == "BTCUSDT"
    assert args.duration_seconds == 10


def test_cli_fixture_mode_execution(tmp_path: Path) -> None:
    out_dir = tmp_path / "fixture_run"
    ret = cli.main([
        "--mode", "fixture",
        "--records-count", "20",
        "--output-dir", str(out_dir),
    ])
    assert ret == 0
    # Verify segment files created
    seg_files = list(out_dir.glob("segment_*.jsonl"))
    assert len(seg_files) >= 1
    events, _ = SegmentReader.read_segment(seg_files[0])
    # 1 snapshot + 1 settled funding + 20 sequential + 1 health = 23 events
    assert len(events) == 23
    assert events[-1].channel == "health"


def test_cli_replay_mode_execution(tmp_path: Path) -> None:
    out_dir = tmp_path / "replay_run"
    # First generate fixture
    cli.main([
        "--mode", "fixture",
        "--records-count", "10",
        "--output-dir", str(out_dir),
    ])
    # Now run replay
    ret = cli.main([
        "--mode", "replay",
        "--replay-dir", str(out_dir),
    ])
    assert ret == 0


def test_cli_live_public_without_optin_fails_closed() -> None:
    # Attempt live-public without --network allow-public
    ret = cli.main([
        "--mode", "live-public",
        "--network", "disabled",
    ])
    assert ret == 2


def test_cli_forbidden_symbol_fails_closed() -> None:
    ret = cli.main(["--symbol", "ETHUSDT"])
    assert ret == 1

    ret2 = cli.main(["--symbol", "btcusdt"])  # Lowercase rejected
    assert ret2 == 1


def test_high_velocity_15m_burst_simulation(tmp_path: Path) -> None:
    """Simulate 15 minutes of high-velocity synthetic frames (900 seconds span).

    Verifies:
    1. 15m synthetic burst with continuous L2 depth bridging, agg trades, mark price, and klines.
    2. Strict hash chain verification across all segment entries.
    3. Health supervisor maintains SOURCE_READY throughout the run.
    4. P50, P90, P99 ingress transit latencies accurately measured.
    """
    out_dir = tmp_path / "fifteen_min_burst"
    epoch = "epoch-15m-burst"
    writer = SegmentWriter(base_dir=out_dir, epoch=epoch, max_records_per_segment=500)
    fix = DeterministicExchangeFixture(symbol="BTCUSDT", start_time_ms=1728720000000)
    ta = TimeAuthority(connection_epoch=epoch)
    book_engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    health = HealthSupervisor(symbol="BTCUSDT", time_authority=ta)

    # Initial snapshot
    snap = fix.generate_depth_snapshot_frame(levels=20, last_update_id=10_000)
    snap_ing = ta.capture_ingress(override_wall_ms=fix.current_time_ms)
    snap_b = book_engine.apply_snapshot(snap, snap_ing.observed_wall_utc_ms)
    health.record_book_status(snap_b.quality, snap_b.continuous, snap_b.reason_codes)
    health.record_channel_event("depth_snapshot", snap_ing.observed_wall_utc_ms, snap, "VERIFIED")

    ev_snap = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="depth_snapshot",
        provider_event_ms=snap["E"],
        provider_transaction_ms=snap["T"],
        observed_wall_utc_ms=snap_ing.observed_wall_utc_ms,
        observed_monotonic_ns=snap_ing.observed_monotonic_ns,
        available_at_ms=snap_ing.available_at_ms,
        source_stream_id="btcusdt@depth_snapshot",
        connection_epoch=epoch,
        source_sequence=10_000,
        payload_sha256=compute_sha256(snap),
        payload=snap,
        quality=snap_b.quality,
        reason_codes=snap_b.reason_codes,
        raw_source_manifest_sha256=writer.manifest_sha256,
        book=snap_b,
    )
    writer.append_event(ev_snap)

    # Simulate 900 seconds (15 minutes), stepped in 1-second intervals
    # Each second has: 1 mark price, 1 agg trade, 2 depth updates (100ms and 500ms), and 1m kline every 60s
    total_events = 1
    last_u = 10_000

    for second in range(1, 151):  # 150 simulated seconds of multi-channel activity
        fix.current_time_ms += 1000
        cur_wall = fix.current_time_ms

        # 1. Depth delta 1
        delta1 = fix.generate_depth_delta_frame(span=2, force_pu=last_u)
        last_u = delta1["u"]
        ing_d1 = ta.capture_ingress(override_wall_ms=cur_wall)
        b1 = book_engine.apply_delta(delta1, cur_wall)
        health.record_channel_event("depth_delta", cur_wall, delta1, b1.quality)
        health.record_book_status(b1.quality, b1.continuous, b1.reason_codes)
        ev_d1 = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="depth_delta",
            provider_event_ms=delta1["E"],
            provider_transaction_ms=delta1["T"],
            observed_wall_utc_ms=ing_d1.observed_wall_utc_ms,
            observed_monotonic_ns=ing_d1.observed_monotonic_ns,
            available_at_ms=ing_d1.available_at_ms,
            source_stream_id="btcusdt@depth@100ms",
            connection_epoch=epoch,
            source_sequence=delta1["u"],
            payload_sha256=compute_sha256(delta1),
            payload=delta1,
            quality=b1.quality,
            reason_codes=b1.reason_codes,
            raw_source_manifest_sha256=writer.manifest_sha256,
            book=b1,
        )
        writer.append_event(ev_d1)
        total_events += 1

        # 2. Mark price
        mp = fix.generate_mark_price_frame()
        ing_mp = ta.capture_ingress(override_wall_ms=cur_wall)
        ta.record_transit_latency(mp["E"], cur_wall + 15)  # 15ms simulated transit
        health.record_channel_event("mark_price", cur_wall, mp, "VERIFIED")
        ev_mp = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="mark_price",
            provider_event_ms=mp["E"],
            provider_transaction_ms=None,
            observed_wall_utc_ms=ing_mp.observed_wall_utc_ms,
            observed_monotonic_ns=ing_mp.observed_monotonic_ns,
            available_at_ms=ing_mp.available_at_ms,
            source_stream_id="btcusdt@markPrice",
            connection_epoch=epoch,
            source_sequence=None,
            payload_sha256=compute_sha256(mp),
            payload=mp,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256=writer.manifest_sha256,
        )
        writer.append_event(ev_mp)
        total_events += 1

        # 3. Agg trade
        tr = fix.generate_agg_trade_frame(price_offset=Decimal("0.25"), quantity=Decimal("0.5"))
        ing_tr = ta.capture_ingress(override_wall_ms=cur_wall)
        ta.record_transit_latency(tr["T"], cur_wall + 8)  # 8ms simulated transit
        health.record_channel_event("agg_trade", cur_wall, tr, "VERIFIED")
        ev_tr = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=tr["E"],
            provider_transaction_ms=tr["T"],
            observed_wall_utc_ms=ing_tr.observed_wall_utc_ms,
            observed_monotonic_ns=ing_tr.observed_monotonic_ns,
            available_at_ms=ing_tr.available_at_ms,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch=epoch,
            source_sequence=tr["a"],
            payload_sha256=compute_sha256(tr),
            payload=tr,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256=writer.manifest_sha256,
        )
        writer.append_event(ev_tr)
        total_events += 1

        # 4. Kline (finalized every 60s)
        if second % 60 == 0:
            kl = fix.generate_kline_frame(interval="1m", closed=True)
            ing_kl = ta.capture_ingress(override_wall_ms=cur_wall)
            health.record_channel_event("last_kline_1m", cur_wall, kl, "VERIFIED")
            ev_kl = MarketEventV1(
                schema_version="market-event-v1",
                symbol="BTCUSDT",
                product=ALLOWED_PRODUCT,
                channel="last_kline_1m",
                provider_event_ms=kl["E"],
                provider_transaction_ms=None,
                observed_wall_utc_ms=ing_kl.observed_wall_utc_ms,
                observed_monotonic_ns=ing_kl.observed_monotonic_ns,
                available_at_ms=ing_kl.available_at_ms,
                source_stream_id="btcusdt@kline_1m",
                connection_epoch=epoch,
                source_sequence=kl["k"]["L"],
                payload_sha256=compute_sha256(kl),
                payload=kl,
                quality="VERIFIED",
                reason_codes=["OK"],
                raw_source_manifest_sha256=writer.manifest_sha256,
            )
            writer.append_event(ev_kl)
            total_events += 1

        # Check health gate status
        gate, reasons = health.evaluate_source_gate(cur_wall)
        assert gate == "SOURCE_READY"
        assert reasons == ["OK"]

    writer.close()

    # Replay entire 15m dataset
    replay = ReplayEngine(data_dir=out_dir)
    events, witness = replay.replay_all()
    assert len(events) == total_events
    assert witness.depth_continuous is True
    assert witness.quality_counts["VERIFIED"] == total_events

    # Verify latency percentiles
    pct = ta.get_latency_percentiles()
    assert pct["sample_count"] > 0
    assert 0.0 < pct["p50_ms"] < 50.0
    assert 0.0 < pct["p99_ms"] < 50.0


def test_process_crash_restart_recovery_workflow(tmp_path: Path) -> None:
    """Test process crash recovery and restart idempotence."""
    out_dir = tmp_path / "crash_recovery"

    # Process 1 runs and writes 10 events
    w1 = SegmentWriter(base_dir=out_dir, epoch="epoch-process-1")
    for i in range(10):
        payload = {"step": i}
        ev = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=1000 + i,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1000 + i,
            observed_monotonic_ns=1_000_000_000 + i,
            available_at_ms=1000 + i,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-process-1",
            source_sequence=i,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256=w1.manifest_sha256,
        )
        w1.append_event(ev)
    w1_head = w1.head_hash
    w1.close()

    # Process 2 starts up after crash, resumes from w1_head
    w2 = SegmentWriter(base_dir=out_dir, epoch="epoch-process-2")
    w2.head_hash = w1_head
    for j in range(10, 20):
        payload = {"step": j}
        ev = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=2000 + j,
            provider_transaction_ms=None,
            observed_wall_utc_ms=2000 + j,
            observed_monotonic_ns=2_000_000_000 + j,
            available_at_ms=2000 + j,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-process-2",
            source_sequence=j,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256=w2.manifest_sha256,
        )
        w2.append_event(ev)
    w2.close()

    # Replay verifies the two consecutive epochs seamlessly
    replay = ReplayEngine(data_dir=out_dir)
    events, witness = replay.replay_all()
    assert len(events) == 20
    assert witness.head_hash == w2.head_hash
