"""Stage 1: Financial and Causal PIT Invariants Synthetic Negative Test Battery.

Covers:
- Settled Funding (funding_time T) with REST receipt at T+0.2s, T+30s vs T+3h.
- Mark observed at receipt does NOT prove Mark at settlement => COST_INCOMPLETE.
- Rates 0.0001 and 0.00010000 duplicate settlement => exactly once deduped.
- Same symbol + settlement with conflicting revised rate => detectable conflict.
- Nonfinite Decimal rate/price, negative qty, no source SHA, route switch.
- Consumer C late-funding contract rejection proof (C_CONSUMER_REQUIRES_NEW_AUTHORITY).
- Order book continuity with pu gap and route reconnect lineage reset.
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
    SettledFundingEntry,
    SettledFundingLedger,
)
from scripts.integration.market_event_bridge_r2.portable_ci_refs import (
    ensure_portable_c_on_path,
)
from scripts.market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine

ensure_portable_c_on_path()
from scripts.g1g3_offline_ports_r1.market_pit_port import (  # type: ignore
    MarketPitPort,
    SafetyViolation,
)


# 1. Settled Funding receipt chronology (T+0.2s, T+30s vs T+3h)
def test_contemporaneous_receipt_vs_late_receipt_at_3h() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000

    # Case 1: T + 200ms (contemporaneous)
    rec1 = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement}
    e1 = ledger.ingest_settled_funding(
        raw_record=rec1,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=t_settlement + 200,
    )
    assert e1 is not None
    assert e1.cash_realization_status == "COST_PROVISIONAL_SCALAR"
    assert e1.mark_price == Decimal("64000.00")
    assert e1.calculate_cash_flow(Decimal("1.0")) == Decimal("-6.40000000")

    # Case 2: T + 3h (late receipt) on different settlement
    t_settlement_2 = 1728748800000
    rec2 = {"symbol": "BTCUSDT", "fundingRate": "0.00015000", "fundingTime": t_settlement_2}
    e2 = ledger.ingest_settled_funding(
        raw_record=rec2,
        contemporaneous_mark_price="65000.00",
        observed_wall_utc_ms=t_settlement_2 + 3 * 3600 * 1000,
    )
    assert e2 is not None
    # Late arrival without historical mark witness must NOT masquerade receipt price as settlement price
    assert e2.cash_realization_status == "COST_INCOMPLETE"
    assert e2.mark_price is None
    assert e2.calculate_cash_flow(Decimal("1.0")) is None


# 2. Mark observed at receipt does NOT prove Mark at settlement
def test_mark_at_receipt_cannot_masquerade_as_settlement_price() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000
    t_receipt = t_settlement + 3 * 3600 * 1000  # 3 hours late

    # Witness observed at receipt time (T+3h), NOT at settlement time
    witness_at_receipt = MarkPriceWitness(
        price=Decimal("67000.00"),
        observed_wall_utc_ms=t_receipt,
        available_at_ms=t_receipt,
        provider_event_ms=t_receipt,
        source_sha="fresh_mark_witness_at_receipt",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )

    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price=witness_at_receipt,
        observed_wall_utc_ms=t_receipt,
    )
    assert entry is not None
    assert entry.cash_realization_status == "COST_INCOMPLETE"
    assert entry.mark_price is None
    assert entry.calculate_cash_flow(Decimal("2.0")) is None


# 3. Duplicate rates numeric equivalence (0.0001 vs 0.00010000)
def test_equivalent_rates_deduplicated_exactly_once() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000

    r1 = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement}
    e1 = ledger.ingest_settled_funding(
        raw_record=r1,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=t_settlement + 100,
    )
    assert e1 is not None

    r2 = {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingTime": t_settlement}
    e2 = ledger.ingest_settled_funding(
        raw_record=r2,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=t_settlement + 200,
    )
    assert e2 is e1
    assert ledger.duplicate_count == 1
    assert len(ledger.journal) == 1


# 4. Conflicting revised rate for same symbol + settlement is detectable conflict
def test_conflicting_revised_rate_detectable_conflict_fails_closed() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    t_settlement = 1728720000000

    r1 = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": t_settlement}
    e1 = ledger.ingest_settled_funding(
        raw_record=r1,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=t_settlement + 100,
    )
    assert e1 is not None

    r2 = {"symbol": "BTCUSDT", "fundingRate": "0.00020000", "fundingTime": t_settlement}
    e2 = ledger.ingest_settled_funding(
        raw_record=r2,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=t_settlement + 200,
    )
    assert e2 is None
    assert ledger.rejected_count == 1
    assert len(ledger.journal) == 1
    assert ledger.journal[e1.settlement_id].funding_rate == Decimal("0.00010000")


# 5. Nonfinite Decimal rate rejected
@pytest.mark.parametrize("bad_rate", ["NaN", "Infinity", "-Infinity", "1.50000000", "-2.00000000"])
def test_nonfinite_or_out_of_bounds_decimal_rate_rejected(bad_rate: str) -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": bad_rate, "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=1728720001000,
    )
    assert entry is None
    assert ledger.rejected_count == 1


# 6. Nonfinite Mark price rejected
@pytest.mark.parametrize("bad_mark", ["NaN", "Infinity", "-Infinity", "0.0", "-100.00"])
def test_nonfinite_mark_price_rejected(bad_mark: str) -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price=bad_mark,
        observed_wall_utc_ms=1728720001000,
    )
    assert entry is None
    assert ledger.rejected_count == 1


# 7. Nonfinite position size in calculate_cash_flow returns None
@pytest.mark.parametrize("bad_pos", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_nonfinite_position_size_returns_none(bad_pos: Decimal) -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.00"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="sha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    assert entry.calculate_cash_flow(bad_pos) is None


# 8. Untrusted bare scalar cannot claim quality VERIFIED
def test_untrusted_bare_scalar_cannot_be_verified() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price=64000.0,
        observed_wall_utc_ms=1728720001000,
    )
    assert entry is not None
    assert entry.quality == "UNVERIFIED_SCALAR"
    assert entry.mark_witness is not None
    assert entry.mark_witness.quality == "UNVERIFIED_SCALAR"
    assert entry.mark_witness.source_sha == "unverified_bare_scalar"


# 9. MarkPriceWitness route epoch mismatch fails
def test_mark_witness_route_epoch_mismatch_fails() -> None:
    witness = MarkPriceWitness(
        price=Decimal("64000.00"),
        observed_wall_utc_ms=1728720000000,
        available_at_ms=1728720000000,
        provider_event_ms=1728720000000,
        source_sha="s_sha",
        route_epoch="route-epoch-stale",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    valid, why = witness.is_valid_for_settlement(
        reference_time_ms=1728720001000,
        current_route_epoch="route-epoch-active",
    )
    assert valid is False
    assert why == "MARK_ROUTE_EPOCH_MISMATCH"


# 10. MarkPriceWitness connection epoch mismatch fails
def test_mark_witness_connection_epoch_mismatch_fails() -> None:
    witness = MarkPriceWitness(
        price=Decimal("64000.00"),
        observed_wall_utc_ms=1728720000000,
        available_at_ms=1728720000000,
        provider_event_ms=1728720000000,
        source_sha="s_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    valid, why = witness.is_valid_for_settlement(
        reference_time_ms=1728720001000,
        current_connection_epoch=2,
    )
    assert valid is False
    assert why == "MARK_CONNECTION_EPOCH_MISMATCH"


# 11. MarkPriceWitness CLOCK_UNCERTAIN fails
def test_mark_witness_clock_uncertain_fails() -> None:
    witness = MarkPriceWitness(
        price=Decimal("64000.00"),
        observed_wall_utc_ms=1728720000000,
        available_at_ms=1728720000000,
        provider_event_ms=1728720000000,
        source_sha="s_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("CLOCK_UNCERTAIN",),
    )
    valid, why = witness.is_valid_for_settlement(reference_time_ms=1728720001000)
    assert valid is False
    assert why == "MARK_CLOCK_UNCERTAIN"


# 12. MarkPriceWitness future known fails
def test_mark_witness_future_known_fails() -> None:
    witness = MarkPriceWitness(
        price=Decimal("64000.00"),
        observed_wall_utc_ms=1728720005000,
        available_at_ms=1728720005000,
        provider_event_ms=1728720005000,
        source_sha="s_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    valid, why = witness.is_valid_for_settlement(reference_time_ms=1728720001000)
    assert valid is False
    assert why == "MARK_FUTURE_AVAILABLE"


# 13. MarkPriceWitness stale from settlement time fails
def test_mark_witness_stale_from_settlement_fails() -> None:
    witness = MarkPriceWitness(
        price=Decimal("64000.00"),
        observed_wall_utc_ms=1728719000000,  # 1000 seconds prior
        available_at_ms=1728719000000,
        provider_event_ms=1728719000000,
        source_sha="s_sha",
        route_epoch="route-epoch-0",
        connection_epoch=1,
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    valid, why = witness.is_valid_for_settlement(
        reference_time_ms=1728720001000,
        settlement_time_ms=1728720000000,
        max_staleness_ms=60_000,
    )
    assert valid is False
    assert "MARK_NOT_CONTEMPORANEOUS_WITH_SETTLEMENT" in why


# 14. Future settlement timestamp relative to observed wall utc fails
def test_future_settlement_timestamp_rejected() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720050000}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=1728720000000,  # wall before settlement
    )
    assert entry is None
    assert ledger.rejected_count == 1


# 15. Non-positive funding time rejected
@pytest.mark.parametrize("bad_ft", [0, -1000, -1])
def test_non_positive_funding_time_rejected(bad_ft: int) -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": bad_ft}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=1728720000000,
    )
    assert entry is None
    assert ledger.rejected_count == 1


# 16. Blank or whitespace funding rate rejected
@pytest.mark.parametrize("blank_fr", ["", "   ", "\t"])
def test_blank_or_whitespace_funding_rate_rejected(blank_fr: str) -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": blank_fr, "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(
        raw_record=rec,
        contemporaneous_mark_price="64000.00",
        observed_wall_utc_ms=1728720001000,
    )
    assert entry is None
    assert ledger.rejected_count == 1


# 17. Ledger state idempotency on rejections
def test_ledger_side_effects_idempotency_on_rejection() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec_valid = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    e_valid = ledger.ingest_settled_funding(rec_valid, 64000.0, 1728720001000)
    assert e_valid is not None
    assert len(ledger.journal) == 1

    # Inject 5 invalid requests
    for i in range(5):
        ledger.ingest_settled_funding({"symbol": "BTCUSDT", "fundingRate": "NaN", "fundingTime": 1728720000000 + i}, 64000.0, 1728720001000)

    assert len(ledger.journal) == 1
    assert ledger.rejected_count == 5


# 18. Consumer C late-funding contract rejects legitimate later receiver time
def test_consumer_c_late_funding_contract_rejects_later_receiver_time() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m_sha")
    t_settlement = 1728720000000
    t_receipt = t_settlement + 3600_000  # 1 hour late arrival via REST

    c_payload = {
        "event_id": f"FUNDING-BTCUSDT-{t_settlement}",
        "settlement_id": f"BTCUSDT:{t_settlement}:0.0001",
        "settlement_at_ms": t_settlement,
        "rate_fraction": "0.00010000",
        "settled": True,
        "rate_type": "SETTLED_REALIZED",
    }
    import hashlib
    import json

    c_payload_sha = hashlib.sha256(
        json.dumps(c_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    env = {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "funding_settled",
        "provider_event_ms": t_settlement,
        "provider_transaction_ms": t_settlement,
        "observed_wall_utc_ms": t_receipt,
        "observed_monotonic_ns": 100,
        "available_at_ms": t_receipt,  # Strict PIT receiver time
        "source_stream_id": "btcusdt@kline_1m",
        "connection_epoch": 1,
        "source_sequence": None,
        "payload_sha256": c_payload_sha,
        "payload": c_payload,
        "quality": "VERIFIED",
        "reason_codes": ["OK"],
        "raw_source_manifest_sha256": "m_sha",
    }
    with pytest.raises(SafetyViolation) as exc_info:
        port.ingest_envelope(env)
    assert "FUNDING_PIT_INVALID" in str(exc_info.value)


# 19. Order book continuity pu sequence gap drops continuity
def test_order_book_continuity_pu_gap_drops_continuity() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["64000.00", "1.0"]],
        "asks": [["64010.00", "1.0"]],
    }
    rec_snap = engine.apply_snapshot(snap, observed_wall_ms=1000)
    assert rec_snap.continuous is True
    assert engine.continuous is True

    # Delta with pu gap (pu=1005 != 1000)
    gap_delta = {
        "e": "depthUpdate",
        "E": 1100,
        "s": "BTCUSDT",
        "U": 1006,
        "u": 1010,
        "pu": 1005,
        "b": [["64000.50", "2.0"]],
        "a": [],
    }
    rec_delta = engine.apply_delta(gap_delta, observed_wall_ms=1100)
    assert rec_delta.continuous is False
    assert rec_delta.quality == "INVALID"
    assert engine.continuous is False
    assert engine.needs_rebootstrap is True


# 20. Order book route reconnect resets book and mark lineage
def test_order_book_route_reconnect_resets_book_and_mark_lineage() -> None:
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 2000,
        "bids": [[f"{64000 - i}", "1.0"] for i in range(12)],
        "asks": [[f"{64010 + i}", "1.0"] for i in range(12)],
        "symbol": "BTCUSDT",
    }
    bridge.ingest_frame(snap, observed_wall_utc_ms=1000, observed_monotonic_ns=100)
    assert bridge.last_top10_snapshot is not None
    assert bridge.last_top10_snapshot.quality == "VERIFIED"

    # Route failover
    bridge.switch_route_node("route-epoch-failover-1")
    assert bridge.route_epoch == "route-epoch-failover-1"
    assert bridge.connection_epoch == 2

    # Ingesting diff before fresh snapshot is rejected as degraded
    delta = {
        "e": "depthUpdate",
        "E": 2000,
        "s": "BTCUSDT",
        "U": 2001,
        "u": 2005,
        "pu": 2000,
        "b": [["64001.00", "2.0"]],
        "a": [],
    }
    bridge.ingest_frame(delta, observed_wall_utc_ms=2000, observed_monotonic_ns=200)
    assert bridge.last_top10_snapshot.quality != "VERIFIED"


# 21. Rate boundary overflow rejected
def test_rate_boundary_overflow_rejected() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "1.00000001", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(rec, 64000.0, 1728720001000)
    assert entry is None
    assert ledger.rejected_count == 1


# 22. Repeated identical record deduplicated cleanly multifold
def test_duplicate_identical_record_repeated_multifold() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    for i in range(5):
        ledger.ingest_settled_funding(rec, 64000.0, 1728720001000 + i * 100)
    assert len(ledger.journal) == 1
    assert ledger.duplicate_count == 4


# 23. Zero position size exact conservation invariant
def test_cash_flow_zero_position_exact_conservation() -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("99999999.99"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="sha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    assert entry.calculate_cash_flow(Decimal(0)) == Decimal("0.00000000")


# 24. Strict provenance rejects provisional bare scalar
def test_strict_provenance_rejects_provisional_scalar() -> None:
    ledger = SettledFundingLedger(symbol="BTCUSDT")
    rec = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(rec, 64000.0, 1728720001000)
    assert entry is not None
    assert entry.calculate_cash_flow(Decimal("1.0"), strict_provenance=False) == Decimal("-6.40000000")
    assert entry.calculate_cash_flow(Decimal("1.0"), strict_provenance=True) is None
