"""Stage 2: Mutation Sensitivity Battery.

Validates that deliberate mutant inputs are strictly caught and rejected or fail-closed
across financial, causal, cryptographic, and order-book invariants:
- Mutant 1: Time traveler / inverted arrival latency (observed_wall_utc_ms < fundingTime).
- Mutant 2: Non-finite funding rates (NaN, Infinity, malformed strings).
- Mutant 3: Conflicting revised funding rate on identical settlement timestamp.
- Mutant 4: Mark price witness timestamp skew (> tolerance from settlement timestamp).
- Mutant 5: Mark price witness route epoch drift (stale route epoch witness).
- Mutant 6: Cryptographic payload hash tampering / payload mismatch.
- Mutant 7: Order book inverted ladder mutant (bid >= ask in snapshot).
- Mutant 8: Order book sequence gap / dropped packet (U > prev_u + 1 in delta).
- Mutant 9: Order book negative quantity mutant in snapshot.
- Mutant 10: Late funding receipt blocked by C consumer contract (FUNDING_PIT_INVALID).
- Mutant 11: Connection epoch format / type invalidation rejected by C consumer.
- Mutant 12: Late arrival without settlement mark witness prevents false realized PnL emission.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.integration.market_event_bridge_r2.bridge_engine import MarketEventBridgeR2
from scripts.integration.market_event_bridge_r2.funding_adapter import (
    MarkPriceWitness,
    SettledFundingLedger,
)
from scripts.integration.market_event_bridge_r2.portable_ci_refs import (
    ensure_portable_c_on_path,
)
from scripts.market_data.forward_public_feed_r1.contracts import (
    build_market_event_envelope,
    compute_sha256,
)
from scripts.market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine

ensure_portable_c_on_path()
from scripts.g1g3_offline_ports_r1.market_pit_port import (  # type: ignore
    MarketPitPort,
    SafetyViolation,
)


# Mutant 1: Time traveler / inverted arrival latency (observed_wall_utc_ms < fundingTime)
def test_mutant_01_time_traveler_negative_arrival_latency() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000
    witness = MarkPriceWitness(
        price=Decimal("65000.00"),
        observed_wall_utc_ms=t_settlement,
        available_at_ms=t_settlement,
        provider_event_ms=t_settlement,
        source_sha="witness_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    # Mutant: observed receipt is 1 hour before the funding event even took place
    mutant_record = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": t_settlement,
    }
    entry = ledger.ingest_settled_funding(
        raw_record=mutant_record,
        contemporaneous_mark_price=witness,
        observed_wall_utc_ms=t_settlement - 3_600_000,
    )
    assert entry is None
    assert ledger.rejected_count == 1


# Mutant 2: Non-finite funding rates (NaN, Infinity, malformed strings)
@pytest.mark.parametrize("bad_rate", ["NaN", "Infinity", "-Infinity", "nan", "inf", "invalid_number", "1.50000000"])
def test_mutant_02_nonfinite_funding_rate_rejected(bad_rate: str) -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    mutant_record = {
        "symbol": "BTCUSDT",
        "fundingRate": bad_rate,
        "fundingTime": 1728720000000,
    }
    entry = ledger.ingest_settled_funding(
        raw_record=mutant_record,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=1728720000200,
    )
    assert entry is None
    assert ledger.rejected_count == 1


# Mutant 3: Conflicting revised funding rate on identical settlement timestamp
def test_mutant_03_conflicting_revised_funding_rate_fails_closed() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000
    rec_original = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": t_settlement,
    }
    e1 = ledger.ingest_settled_funding(rec_original, contemporaneous_mark_price="64000.00", observed_wall_utc_ms=t_settlement + 100)
    assert e1 is not None

    # Identical rate format difference (deduped successfully)
    rec_dedup = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.0001",
        "fundingTime": t_settlement,
    }
    e2 = ledger.ingest_settled_funding(rec_dedup, contemporaneous_mark_price="64000.00", observed_wall_utc_ms=t_settlement + 200)
    assert e2 is not None
    assert e2 is e1  # Same entry returned
    assert ledger.duplicate_count == 1

    # Mutant: conflicting revised rate on same symbol and funding time
    rec_conflict = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00020000",
        "fundingTime": t_settlement,
    }
    e3 = ledger.ingest_settled_funding(rec_conflict, contemporaneous_mark_price="64000.00", observed_wall_utc_ms=t_settlement + 300)
    assert e3 is None
    assert ledger.rejected_count == 1
    assert len(ledger.journal) == 1
    assert ledger.journal[e1.settlement_id].funding_rate == Decimal("0.00010000")


# Mutant 4: Mark price witness timestamp skew (> tolerance from settlement timestamp)
def test_mutant_04_mark_witness_timestamp_skew_rejected() -> None:
    t_settlement = 1728720000000
    # Mark tick from 10 minutes prior
    skewed_witness = MarkPriceWitness(
        price=Decimal("65000.00"),
        observed_wall_utc_ms=t_settlement - 600_000,
        available_at_ms=t_settlement - 600_000,
        provider_event_ms=t_settlement - 600_000,
        source_sha="skewed_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    is_valid, reason = skewed_witness.is_valid_for_settlement(
        reference_time_ms=t_settlement + 100,
        settlement_time_ms=t_settlement,
    )
    assert is_valid is False
    assert "MARK_NOT_CONTEMPORANEOUS_WITH_SETTLEMENT" in reason

    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price=skewed_witness,
        observed_wall_utc_ms=t_settlement + 100,
    )
    assert entry is not None
    assert entry.cash_realization_status == "COST_INCOMPLETE"
    assert entry.mark_price is None


# Mutant 5: Mark price witness route epoch drift
def test_mutant_05_mark_witness_route_epoch_drift() -> None:
    t_settlement = 1728720000000
    witness_old_route = MarkPriceWitness(
        price=Decimal("65000.00"),
        observed_wall_utc_ms=t_settlement,
        available_at_ms=t_settlement,
        provider_event_ms=t_settlement,
        source_sha="route1_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    # Current active route is epoch 2
    is_valid, reason = witness_old_route.is_valid_for_settlement(
        reference_time_ms=t_settlement,
        settlement_time_ms=t_settlement,
        current_route_epoch="route-epoch-failover-2",
    )
    assert is_valid is False
    assert "ROUTE_EPOCH_MISMATCH" in reason


# Mutant 6: Cryptographic payload hash tampering / payload mismatch
def test_mutant_06_payload_hash_tampering_detected() -> None:
    original_payload = {"p": "65000.00", "q": "1.5"}
    env = build_market_event_envelope(
        symbol="BTCUSDT",
        channel="agg_trade",
        payload=original_payload,
        observed_wall_utc_ms=1728720000000,
        observed_monotonic_ns=1000,
        available_at_ms=1728720000000,
    )
    assert compute_sha256(env["payload"]) == env["payload_sha256"]

    # Tampered mutant payload
    tampered_payload = {"p": "65000.00", "q": "999.0"}
    assert compute_sha256(tampered_payload) != env["payload_sha256"]


# Mutant 7: Order book inverted ladder mutant (bid >= ask in snapshot)
def test_mutant_07_orderbook_inverted_spread_detected() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    # Inverted snapshot: bid 64010 >= ask 64005
    snap = {
        "lastUpdateId": 100,
        "bids": [["64010.00", "1.000"]],
        "asks": [["64005.00", "1.000"]],
    }
    receipt = engine.apply_snapshot(snap, 1728720000000)
    assert receipt.quality == "INVALID"
    assert "SNAPSHOT_CROSSED_BOOK" in receipt.reason_codes
    assert engine.is_bootstrapped is False


# Mutant 8: Order book sequence gap / dropped packet (U > prev_u + 1 in delta)
def test_mutant_08_orderbook_sequence_gap_detected() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 100,
        "bids": [["64000.00", "1.000"]],
        "asks": [["64005.00", "1.000"]],
    }
    engine.apply_snapshot(snap, 1728720000000)
    assert engine.is_bootstrapped is True

    # Mutant delta with dropped packets: U=105 instead of <= 101
    gapped_delta = {
        "e": "depthUpdate",
        "E": 1728720000100,
        "s": "BTCUSDT",
        "U": 105,
        "u": 106,
        "pu": 104,
        "b": [["64001.00", "1.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(gapped_delta, 1728720000100)
    assert receipt.quality == "INVALID"
    assert any("GAP_SNAPSHOT_TO_STREAM" in r for r in receipt.reason_codes)
    assert engine.needs_rebootstrap is True


# Mutant 9: Order book negative quantity mutant in snapshot
def test_mutant_09_orderbook_negative_quantity_rejected() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    mutant_snap = {
        "lastUpdateId": 100,
        "bids": [["64000.00", "-1.000"]],
        "asks": [["64005.00", "1.000"]],
    }
    receipt = engine.apply_snapshot(mutant_snap, 1728720000000)
    assert receipt.quality == "INVALID"
    assert any("INVALID_SNAPSHOT_PARSE_ERROR" in r for r in receipt.reason_codes)
    assert engine.is_bootstrapped is False


# Mutant 10: Late funding receipt blocked by C consumer contract (FUNDING_PIT_INVALID)
def test_mutant_10_c_consumer_late_funding_rejected_by_pit_contract() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@composite_1m", expected_manifest_sha256="msha")
    bridge = MarketEventBridgeR2(symbol="BTCUSDT", c_port=port)
    bridge.c_bar_builder.stream_id = "btcusdt@composite_1m"
    bridge.c_bar_builder.manifest_sha256 = "msha"

    t_settlement = 1728720000000
    t_late_arrival = t_settlement + 5_000  # 5s late

    # Ingest mark tick contemporaneous with arrival
    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": t_late_arrival, "p": "64000.00"},
        observed_wall_utc_ms=t_late_arrival,
        observed_monotonic_ns=100,
    )

    # Late funding arrival
    res = bridge.ingest_frame(
        {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement},
        observed_wall_utc_ms=t_late_arrival,
        observed_monotonic_ns=200,
    )
    assert res["emitted_to_c"] is False
    assert res["c_consumer_status"] == "C_CONSUMER_CONTRACT_BLOCKED"
    assert "FUNDING_PIT_INVALID" in res["c_contract_block_reason"]


# Mutant 11: Connection epoch format / type invalidation
def test_mutant_11_connection_epoch_type_invalidation() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@composite_1m", expected_manifest_sha256="msha")
    # C requires connection_epoch to be an int
    c_fund_env_bad = build_market_event_envelope(
        symbol="BTCUSDT",
        channel="funding_settled",
        payload={"fundingRate": "0.0001", "fundingTime": 1728720000000},
        observed_wall_utc_ms=1728720000000,
        observed_monotonic_ns=1000,
        available_at_ms=1728720000000,
        source_stream_id="btcusdt@composite_1m",
        connection_epoch="invalid_string_epoch",
        raw_source_manifest_sha256="msha",
    )
    with pytest.raises(SafetyViolation, match="CONNECTION_EPOCH_INVALID"):
        port.ingest_envelope(c_fund_env_bad)


# Mutant 12: Late arrival without settlement mark prevents false realized PnL emission
def test_mutant_12_late_arrival_prevents_phantom_pnl() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000
    t_arrival_3h = t_settlement + 3 * 3600_000

    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement}
    # Bare scalar mark from arrival time (T+3h), NOT from settlement time
    entry = ledger.ingest_settled_funding(rec, contemporaneous_mark_price="67000.00", observed_wall_utc_ms=t_arrival_3h)
    assert entry is not None
    assert entry.cash_realization_status == "COST_INCOMPLETE"
    assert entry.mark_price is None

    # Verify that serialized record preserves mark_price as None and prevents realized cash flow calculation
    entry_dict = entry.to_dict()
    assert entry_dict["mark_price"] is None
    assert entry_dict["cash_realization_status"] == "COST_INCOMPLETE"
    assert entry.to_b_funding_payload()["p"] == 0.0
    assert entry.calculate_cash_flow(Decimal("1.5")) is None
