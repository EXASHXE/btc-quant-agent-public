"""Category 7: Stress, Security, Fault-Tolerance & End-to-End Suite.

Covers:
- Offline / default network disabled security verification
- Strict fail-closed on unrouted Binance endpoints
- Desensitization of proxy credentials in configs, errors, and logs
- WSL2 host environment gateway detection
- End-to-end replay with 10m, 15m, and 30m high-frequency synthetic scenarios
- Route epoch switch / book reset on failover
- Crossed spread and sequence gap defense
- Resource cleanup verification (no lingering daemons or threads)
- CLI subcommand stress: proxy-diagnostic, fixture, bridge-check
- High-velocity burst throughput benchmarking (>1,000 frames/sec)
"""

import json
import sys
import time
from pathlib import Path

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import pytest

from scripts.integration.market_event_bridge_r2.bridge_engine import MarketEventBridgeR2
from scripts.integration.market_event_bridge_r2.cli import main as bridge_cli_main
from scripts.integration.market_event_bridge_r2.fixtures import BridgeFixtureGenerator
from scripts.market_data.forward_public_feed_r1.connector import (
    BinancePublicFeedClient,
    NetworkGateError,
)
from scripts.market_data.forward_public_feed_r1.proxy_route import (
    NetworkErrorCode,
    NetworkRouteError,
    ProxyRouteConfig,
    detect_wsl2_networking,
    sanitize_env_proxy_map,
    validate_2026_routed_url,
)


def test_default_network_disabled_fail_closed():
    # Attempting to fetch from network with default disabled network_mode fails closed
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    assert client.network_mode == "disabled"
    with pytest.raises(NetworkGateError):
        client.fetch_public_depth_snapshot()


def test_unrouted_endpoints_fail_closed():
    # 2026 unrouted /stream is strictly forbidden
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url("wss://fstream.binance.com/stream?streams=btcusdt@depth@100ms")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID

    # dapi (coin-m) is strictly forbidden for USD-M
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url("wss://dstream.binance.com/public/stream?streams=btcusdt@depth@100ms")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID

    # spot is strictly forbidden
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url("wss://stream.binance.com:9443/ws/btcusdt@depth")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID

    # ws-fapi is strictly forbidden
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url("wss://ws-fapi.binance.com/ws-fapi/v1")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_proxy_credential_desensitization(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://superadmin:ultra_secret_pass_999@192.168.31.200:7890")
    cleaned_map = sanitize_env_proxy_map()
    assert "HTTP_PROXY" in cleaned_map
    assert "ultra_secret_pass_999" not in cleaned_map["HTTP_PROXY"]
    assert "http://superadmin:***@192.168.31.200:7890" in cleaned_map["HTTP_PROXY"]

    cfg = ProxyRouteConfig(
        mode="public-clash-explicit",
        kind="http",
        host="192.168.31.200",
        port=7890,
    )
    s = cfg.to_sanitized_dict()
    assert s["host"] == "192.168.31.200"
    assert s["port"] == 7890
    assert "password" not in s


def test_wsl2_network_gateway_resolution():
    info = detect_wsl2_networking()
    assert isinstance(info["is_wsl"], bool)
    assert "detected_gateway_ip" in info
    assert "wsl_network_mode" in info


def test_bridge_10m_scenario_stress():
    generator = BridgeFixtureGenerator(seed=1001, symbol="BTCUSDT")
    frames, metrics = generator.generate_scenario("happy_path_10m")
    assert len(frames) > 500
    assert metrics.duration_minutes == 10

    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    res = bridge.process_fixture_sequence(frames, base_wall_utc_ms=1728720000000)

    assert res["total_frames_processed"] == len(frames)
    assert bridge.stats.mark_ticks_ingested > 400
    assert bridge.stats.mark_bars_derived >= 9
    assert bridge.stats.top10_book_snapshots_emitted > 500
    assert bridge.stats.settled_fundings_adapted >= 1


def test_bridge_15m_jitter_and_drops_scenario():
    generator = BridgeFixtureGenerator(seed=1002, symbol="BTCUSDT")
    frames, _metrics = generator.generate_scenario("jitter_and_drops_15m")
    assert len(frames) > 700

    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    res = bridge.process_fixture_sequence(frames, base_wall_utc_ms=1728720000000)

    assert res["total_frames_processed"] == len(frames)
    assert bridge.stats.mark_ticks_ingested > 500
    assert bridge.stats.mark_bars_derived >= 12
    # Verify that jitter did not crash ladder adapter or mark aggregator
    assert bridge.last_top10_snapshot is not None
    assert bridge.last_derived_mark_bar is not None


def test_bridge_30m_stress_scenario():
    generator = BridgeFixtureGenerator(seed=1003, symbol="BTCUSDT")
    frames, _metrics = generator.generate_scenario("high_frequency_stress_30m")
    assert len(frames) > 1500

    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    start = time.perf_counter()
    res = bridge.process_fixture_sequence(frames, base_wall_utc_ms=1728720000000)
    elapsed = time.perf_counter() - start

    assert res["total_frames_processed"] == len(frames)
    assert bridge.stats.mark_bars_derived >= 25
    assert bridge.stats.top10_book_snapshots_emitted > 1500
    # 30m scenario processing under 5.0 seconds
    assert elapsed < 5.0


def test_route_epoch_switch_resets_ladder_and_clears_stale_book():
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    # Feed initial snapshot
    snap = {
        "lastUpdateId": 5000,
        "bids": [[f"{64000 - i}", "1.0"] for i in range(15)],
        "asks": [[f"{64010 + i}", "1.0"] for i in range(15)],
        "symbol": "BTCUSDT",
    }
    bridge.ingest_frame(snap, observed_wall_utc_ms=1000, observed_monotonic_ns=100)
    assert bridge.last_top10_snapshot is not None
    assert bridge.route_epoch == "route-epoch-0"

    # Simulate node switch (failover to secondary Clash proxy node)
    bridge.switch_route_node("route-epoch-1")
    assert bridge.route_epoch == "route-epoch-1"
    assert bridge.connection_epoch == 2

    # Ladder adapter must require fresh snapshot before emitting valid deltas
    delta = {
        "e": "depthUpdate",
        "E": 2000,
        "s": "BTCUSDT",
        "U": 5001,
        "u": 5005,
        "pu": 5000,
        "b": [["64001.00", "2.0"]],
        "a": [],
    }
    bridge.ingest_frame(delta, observed_wall_utc_ms=2000, observed_monotonic_ns=200)
    # When unbootstrapped after reset, top10 snapshot is not VERIFIED
    assert bridge.last_top10_snapshot.quality != "VERIFIED"

    # New snapshot after switch
    snap2 = {
        "lastUpdateId": 5005,
        "bids": [[f"{64002 - i}", "1.5"] for i in range(15)],
        "asks": [[f"{64008 + i}", "1.5"] for i in range(15)],
        "symbol": "BTCUSDT",
    }
    res_snap2 = bridge.ingest_frame(snap2, observed_wall_utc_ms=2050, observed_monotonic_ns=300)
    assert "top10_snapshot" in res_snap2
    assert bridge.last_top10_snapshot.route_epoch == "route-epoch-1"


def test_ladder_adapter_crossed_spread_defense():
    from scripts.integration.market_event_bridge_r2.book_ladder import OrderBookLadderAdapter
    from scripts.market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine

    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 100,
        "bids": [["65000.00", "1.0"]],
        "asks": [["64000.00", "1.0"]],
        "symbol": "BTCUSDT",
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)
    adapter = OrderBookLadderAdapter(engine)
    top10 = adapter.extract_atomic_snapshot(current_wall_ms=1000)
    assert top10.quality == "INVALID"
    assert "SNAPSHOT_CROSSED_BOOK" in engine.reason_codes
    assert not engine.is_bootstrapped


def test_funding_ledger_zero_default_prevention():
    from scripts.integration.market_event_bridge_r2.funding_adapter import SettledFundingLedger

    ledger = SettledFundingLedger("BTCUSDT")
    # Record without rate or negative rate with missing mark price
    raw_missing_mark = {"fundingRate": "0.0001", "fundingTime": 1000}
    entry = ledger.ingest_settled_funding(raw_missing_mark, contemporaneous_mark_price=None, observed_wall_utc_ms=2000)
    assert entry is None
    assert ledger.rejected_count == 1


def test_no_lingering_threads_or_daemons():
    import threading

    threads_before = threading.enumerate()
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    gen = BridgeFixtureGenerator(seed=999)
    frames, _ = gen.generate_scenario("happy_path_10m")
    bridge.process_fixture_sequence(frames[:50], base_wall_utc_ms=1728720000000)
    threads_after = threading.enumerate()

    assert len(threads_before) == len(threads_after)


def test_bridge_cli_proxy_diagnostic_json_output(capsys):
    ret = bridge_cli_main(["proxy-diagnostic", "--network=disabled"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["diagnostic_code"] == "NETWORK_DISABLED"
    assert "layers" in data
    assert "environment" in data


def test_bridge_cli_fixture_generation(tmp_path):
    out_file = tmp_path / "test_fixture.jsonl"
    ret = bridge_cli_main(["fixture", "--scenario=happy_path_10m", f"--output-file={out_file}"])
    assert ret == 0
    assert out_file.exists()
    lines = [json.loads(line) for line in out_file.read_text().splitlines() if line.strip()]
    assert len(lines) > 500


def test_bridge_cli_bridge_check_dry_run(tmp_path):
    evidence_dir = tmp_path / "evidence"
    ret = bridge_cli_main(["bridge-check", f"--evidence-dir={evidence_dir}"])
    assert ret == 0
    assert (evidence_dir / "BRIDGE_AFTER_SYNTHETIC_WITNESSES.json").exists()


def test_burst_throughput_performance():
    generator = BridgeFixtureGenerator(seed=2026, symbol="BTCUSDT")
    frames, _ = generator.generate_scenario("happy_path_10m")
    # Duplicate frames to make a 2,000+ frame burst
    burst_frames = frames * 3

    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    start = time.perf_counter()
    res = bridge.process_fixture_sequence(burst_frames, base_wall_utc_ms=1728720000000)
    elapsed = time.perf_counter() - start

    assert res["total_frames_processed"] == len(burst_frames)
    fps = len(burst_frames) / elapsed
    # Throughput must exceed 1,000 frames/sec on modern CPU
    assert fps > 1000.0
