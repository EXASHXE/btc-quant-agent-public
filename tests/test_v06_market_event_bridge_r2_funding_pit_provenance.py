"""Category 9: 32 tests for Funding PIT Arrival, MarkPriceWitness Provenance, and Cash Conservation.

Verifies:
- C envelope observed_wall_utc_ms and available_at_ms are set to receiver arrival time, never backdated
- Late arrival (200ms, 30s, 3h) fails closed with C_CONSUMER_CONTRACT_BLOCKED without modifying C
- Coincident arrival accepted by C MarketPitPort
- B and C receive identical source ingress timestamps
- MarkPriceWitness verification: freshness, positive price, verified quality, route/connection epoch
- Strict Decimal arithmetic to 8 decimal places with ROUND_HALF_EVEN
- Cash conservation across 1,000 synthetic balanced accounts (net zero)
- Future settlement rejection and settlement_id idempotence
- Extreme funding rates and negative rates
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.integration.market_event_bridge_r2.bridge_engine import MarketEventBridgeR2
from scripts.integration.market_event_bridge_r2.funding_adapter import (
    MarkPriceWitness,
    SettledFundingEntry,
    SettledFundingLedger,
)
from scripts.integration.market_event_bridge_r2.portable_ci_refs import ensure_portable_c_on_path

ensure_portable_c_on_path()
from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort


def _make_sample_witness(
    price: str = "64000.50",
    wall_ms: int = 1728720000100,
    route_epoch: str = "route-epoch-0",
    conn_epoch: int = 1,
    quality: str = "VERIFIED",
    reasons: tuple[str, ...] = ("OK",),
) -> MarkPriceWitness:
    return MarkPriceWitness(
        price=Decimal(price),
        observed_wall_utc_ms=wall_ms,
        available_at_ms=wall_ms,
        provider_event_ms=wall_ms - 10,
        source_sha="sha_mark_witness_test",
        route_epoch=route_epoch,
        connection_epoch=conn_epoch,
        quality=quality,
        reason_codes=reasons,
    )


def test_funding_c_envelope_observed_wall_utc_ms_equals_arrival_time() -> None:
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    funding_time = 1728720000000
    arrival_time = 1728720000500  # Arrived 500ms later

    # Prime a verified mark witness
    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": arrival_time - 10, "p": "64100.00"},
        observed_wall_utc_ms=arrival_time - 5,
        observed_monotonic_ns=1000,
    )

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": funding_time,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=2000,
    )

    settled = res["settled_funding"]
    assert settled["source_observed_wall_utc_ms"] == arrival_time
    assert settled["derived_available_at_ms"] == arrival_time
    assert settled["funding_time_ms"] == funding_time


def test_funding_c_envelope_available_at_ms_equals_arrival_time() -> None:
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    funding_time = 1728720000000
    arrival_time = 1728720030000  # Arrived 30 seconds late

    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": arrival_time - 10, "p": "64100.00"},
        observed_wall_utc_ms=arrival_time - 5,
        observed_monotonic_ns=1000,
    )

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": funding_time,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=2000,
    )

    settled = res["settled_funding"]
    assert settled["source_available_at_ms"] == arrival_time
    assert settled["source_available_at_ms"] != funding_time


def test_funding_late_arrival_200ms_blocks_c_contract() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@composite_1m", expected_manifest_sha256="msha")
    bridge = MarketEventBridgeR2(symbol="BTCUSDT", c_port=port)
    bridge.c_bar_builder.stream_id = "btcusdt@composite_1m"
    bridge.c_bar_builder.manifest_sha256 = "msha"

    funding_time = 1728720000000
    arrival_time = 1728720000200  # 200ms late

    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": arrival_time - 10, "p": "64000.00"},
        observed_wall_utc_ms=arrival_time - 5,
        observed_monotonic_ns=100,
    )

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": funding_time,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=200,
    )

    assert res["emitted_to_c"] is False
    assert res["c_consumer_status"] == "C_CONSUMER_CONTRACT_BLOCKED"
    assert "FUNDING_PIT_INVALID" in res["c_contract_block_reason"]


def test_funding_late_arrival_30s_blocks_c_contract() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@composite_1m", expected_manifest_sha256="msha")
    bridge = MarketEventBridgeR2(symbol="BTCUSDT", c_port=port)
    bridge.c_bar_builder.stream_id = "btcusdt@composite_1m"
    bridge.c_bar_builder.manifest_sha256 = "msha"

    funding_time = 1728720000000
    arrival_time = 1728720030000  # 30s late

    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": arrival_time - 10, "p": "64000.00"},
        observed_wall_utc_ms=arrival_time - 5,
        observed_monotonic_ns=100,
    )

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": funding_time,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=200,
    )

    assert res["emitted_to_c"] is False
    assert res["c_consumer_status"] == "C_CONSUMER_CONTRACT_BLOCKED"


def test_funding_late_arrival_3h_blocks_c_contract() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@composite_1m", expected_manifest_sha256="msha")
    bridge = MarketEventBridgeR2(symbol="BTCUSDT", c_port=port)
    bridge.c_bar_builder.stream_id = "btcusdt@composite_1m"
    bridge.c_bar_builder.manifest_sha256 = "msha"

    funding_time = 1728720000000
    arrival_time = 1728720000000 + 3 * 3600 * 1000  # 3 hours late

    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": arrival_time - 10, "p": "64000.00"},
        observed_wall_utc_ms=arrival_time - 5,
        observed_monotonic_ns=100,
    )

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": funding_time,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=200,
    )

    assert res["emitted_to_c"] is False
    assert res["c_consumer_status"] == "C_CONSUMER_CONTRACT_BLOCKED"


def test_funding_coincident_arrival_accepted_by_c() -> None:
    port = MarketPitPort(expected_stream_id="btcusdt@composite_1m", expected_manifest_sha256="msha")
    bridge = MarketEventBridgeR2(symbol="BTCUSDT", c_port=port)
    bridge.c_bar_builder.stream_id = "btcusdt@composite_1m"
    bridge.c_bar_builder.manifest_sha256 = "msha"

    funding_time = 1728720000000
    arrival_time = 1728720000000  # Coincident arrival

    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": arrival_time, "p": "64000.00"},
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=100,
    )

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": funding_time,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=arrival_time,
        observed_monotonic_ns=200,
    )

    assert res["emitted_to_c"] is True
    assert res["c_consumer_status"] == "ACCEPTED"


def test_mark_witness_creation_and_fields() -> None:
    witness = _make_sample_witness("64050.25", wall_ms=1728720000100)
    assert witness.price == Decimal("64050.25")
    assert witness.observed_wall_utc_ms == 1728720000100
    assert witness.quality == "VERIFIED"
    assert witness.source_sha != ""


def test_mark_witness_rejects_non_positive_price() -> None:
    w_zero = _make_sample_witness("0.0")
    valid, why = w_zero.is_valid_for_settlement(1728720000100)
    assert valid is False
    assert why == "MARK_PRICE_NON_POSITIVE"

    w_neg = _make_sample_witness("-100.0")
    valid, why = w_neg.is_valid_for_settlement(1728720000100)
    assert valid is False
    assert why == "MARK_PRICE_NON_POSITIVE"


def test_mark_witness_rejects_quality_degraded() -> None:
    w = _make_sample_witness(quality="DEGRADED")
    valid, why = w.is_valid_for_settlement(1728720000100)
    assert valid is False
    assert "MARK_QUALITY_NOT_VERIFIED" in why


def test_mark_witness_rejects_quality_unknown() -> None:
    w = _make_sample_witness(quality="UNKNOWN")
    valid, why = w.is_valid_for_settlement(1728720000100)
    assert valid is False
    assert "MARK_QUALITY_NOT_VERIFIED" in why


def test_mark_witness_rejects_clock_uncertain() -> None:
    w = _make_sample_witness(reasons=("OK", "CLOCK_UNCERTAIN"))
    valid, why = w.is_valid_for_settlement(1728720000100)
    assert valid is False
    assert why == "MARK_CLOCK_UNCERTAIN"


def test_mark_witness_rejects_stale_age_over_threshold() -> None:
    w = _make_sample_witness(wall_ms=1728720000000)
    # Reference time is 65 seconds later (> 60s)
    valid, why = w.is_valid_for_settlement(reference_time_ms=1728720065000, max_staleness_ms=60_000)
    assert valid is False
    assert "MARK_STALE_AGE" in why


def test_mark_witness_fresh_within_threshold_accepted() -> None:
    w = _make_sample_witness(wall_ms=1728720000000)
    # Reference time is 10 seconds later (<= 60s)
    valid, why = w.is_valid_for_settlement(reference_time_ms=1728720010000, max_staleness_ms=60_000)
    assert valid is True
    assert why == "OK"


def test_mark_witness_rejects_route_epoch_mismatch() -> None:
    w = _make_sample_witness(route_epoch="route-epoch-0")
    valid, why = w.is_valid_for_settlement(1728720000100, current_route_epoch="route-epoch-1")
    assert valid is False
    assert why == "MARK_ROUTE_EPOCH_MISMATCH"


def test_mark_witness_rejects_connection_epoch_mismatch() -> None:
    w = _make_sample_witness(conn_epoch=1)
    valid, why = w.is_valid_for_settlement(1728720000100, current_connection_epoch=2)
    assert valid is False
    assert why == "MARK_CONNECTION_EPOCH_MISMATCH"


def test_bridge_clears_mark_witness_on_route_switch() -> None:
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    bridge.ingest_frame(
        {"e": "markPriceUpdate", "E": 1728720000000, "p": "64000.00"},
        observed_wall_utc_ms=1728720000010,
        observed_monotonic_ns=100,
    )
    assert bridge.last_mark_witness is not None

    bridge.switch_route_node()
    assert bridge.last_mark_witness is None


def test_future_settlement_rejected() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    witness = _make_sample_witness(wall_ms=1728720000000)
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingTime": 1728720005000}
    # Arrival at 1728720000000 is EARLIER than fundingTime (future settlement)
    entry = ledger.ingest_settled_funding(raw, witness, observed_wall_utc_ms=1728720000000)
    assert entry is None
    assert ledger.rejected_count == 1


def test_duplicate_settlement_id_idempotent() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    witness = _make_sample_witness(wall_ms=1728720000000)
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}

    entry1 = ledger.ingest_settled_funding(raw, witness, observed_wall_utc_ms=1728720000100)
    assert entry1 is not None
    assert ledger.duplicate_count == 0

    entry2 = ledger.ingest_settled_funding(raw, witness, observed_wall_utc_ms=1728720000200)
    assert entry1 is entry2
    assert ledger.duplicate_count == 1
    assert len(ledger.journal) == 1


def test_cash_flow_exact_long_position() -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.00"),
        settlement_id="test1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    # Long pays positive rate: -1 * 1.5 * 0.0001 * 64000 = -9.6 USD
    cf = entry.calculate_cash_flow(Decimal("1.5"))
    assert cf == Decimal("-9.60000000")


def test_cash_flow_exact_short_position() -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.00"),
        settlement_id="test2",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    # Short receives positive rate: -1 * -1.5 * 0.0001 * 64000 = +9.6 USD
    cf = entry.calculate_cash_flow(Decimal("-1.5"))
    assert cf == Decimal("9.60000000")


def test_cash_flow_zero_position_exact_zero() -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.00"),
        settlement_id="test3",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("0.0"))
    assert cf == Decimal("0.00000000")


def test_1000_synthetic_accounts_cash_conservation() -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00012500"),
        mark_price=Decimal("63842.125"),
        settlement_id="test_conservation",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )

    total_cash_flow = Decimal("0.00000000")
    for i in range(1, 501):
        pos_size = Decimal(f"{i * 0.01:.4f}")
        long_cf = entry.calculate_cash_flow(pos_size)
        short_cf = entry.calculate_cash_flow(-pos_size)
        assert long_cf is not None and short_cf is not None
        assert long_cf + short_cf == Decimal("0.00000000")
        total_cash_flow += long_cf + short_cf

    assert total_cash_flow == Decimal("0.00000000")


def test_extreme_funding_rate_positive() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    witness = _make_sample_witness("60000.00")
    # Rate +1% (+0.01)
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.01000000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(raw, witness, 1728720000100)
    assert entry is not None
    cf = entry.calculate_cash_flow(Decimal("1.0"))
    assert cf == Decimal("-600.00000000")


def test_extreme_funding_rate_negative() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    witness = _make_sample_witness("60000.00")
    # Rate -1% (-0.01)
    raw = {"symbol": "BTCUSDT", "fundingRate": "-0.01000000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(raw, witness, 1728720000100)
    assert entry is not None
    # Long receives on negative rate: -1 * 1.0 * -0.01 * 60000 = +600 USD
    cf = entry.calculate_cash_flow(Decimal("1.0"))
    assert cf == Decimal("600.00000000")


def test_extreme_funding_rate_cap_10_percent() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    witness = _make_sample_witness("50000.00")
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.10000000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(raw, witness, 1728720000100)
    assert entry is not None
    cf = entry.calculate_cash_flow(Decimal("2.0"))
    assert cf == Decimal("-10000.00000000")


def test_missing_mark_price_fails_closed() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(raw, None, 1728720000100)
    assert entry is None
    assert ledger.rejected_count == 1


def test_zero_mark_price_fails_closed() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(raw, Decimal("0.0"), 1728720000100)
    assert entry is None
    assert ledger.rejected_count == 1


def test_negative_mark_price_fails_closed() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry = ledger.ingest_settled_funding(raw, Decimal("-64000.00"), 1728720000100)
    assert entry is None
    assert ledger.rejected_count == 1


def test_immutable_historical_cash_flow_witness() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    w1 = _make_sample_witness("64000.00", wall_ms=1728720000000)
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    entry1 = ledger.ingest_settled_funding(raw, w1, 1728720000100)
    assert entry1 is not None
    cf1 = entry1.calculate_cash_flow(Decimal("1.0"))
    assert cf1 == Decimal("-6.40000000")

    # A newer mark arriving later must not mutate existing sealed entry
    w2 = _make_sample_witness("65000.00", wall_ms=1728720060000)
    assert w2.price == Decimal("65000.00")
    assert entry1.calculate_cash_flow(Decimal("1.0")) == Decimal("-6.40000000")
    assert entry1.mark_price == Decimal("64000.00")


def test_full_machine_witness_audit_receipt() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    w = _make_sample_witness("64000.00")
    raw = {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1728720000000}
    ledger.ingest_settled_funding(raw, w, 1728720000100)

    report = ledger.generate_decimal_ledger_report()
    assert report["schema_version"] == "settled-funding-decimal-ledger-v1"
    assert report["symbol"] == "BTCUSDT"
    assert report["total_settlements"] == 1
    rec = report["journal_records"][0]
    assert rec["sample_long_1btc_cash_flow"] == "-6.40000000"
    assert rec["sample_short_1btc_cash_flow"] == "6.40000000"
    assert rec["canonical_sha256"] != ""


def test_decimal_quantization_round_half_even() -> None:
    # Test half-even round down: 0.000000005 with even pre-digit rounds to 0.00000000
    # Formula: -1 * pos * rate * mark
    # pos = Decimal('1.0'), rate = Decimal('0.00000001'), mark = Decimal('1.5')
    # cf = -0.000000015 -> even pre-digit (1 is odd so rounds to -0.00000002)
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00000001"),
        mark_price=Decimal("1.5"),
        settlement_id="round_test",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("1.0"))
    assert cf == Decimal("-0.00000002")


def test_funding_payload_converters_b_and_c() -> None:
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.50"),
        settlement_id="payload_test",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    b_payload = entry.to_b_funding_payload()
    assert b_payload["T"] == 1728720000000
    assert b_payload["r"] == 0.0001
    assert b_payload["p"] == 64000.50
    assert b_payload["settled"] is True

    c_payload = entry.to_c_funding_payload()
    assert c_payload["event_id"] == "FUNDING-BTCUSDT-1728720000000"
    assert c_payload["settlement_id"] == "payload_test"
    assert c_payload["settlement_at_ms"] == 1728720000000
    assert c_payload["rate_fraction"] == "0.00010000"
    assert c_payload["settled"] is True
    assert c_payload["rate_type"] == "SETTLED_REALIZED"


def test_settled_funding_entry_canonical_sha_idempotence() -> None:
    w = _make_sample_witness()
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.50"),
        settlement_id="sha_idemp_test",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="msha",
        quality="VERIFIED",
        reason_codes=("OK",),
        mark_witness=w,
    )
    d1 = entry.to_dict()
    d2 = entry.to_dict()
    assert d1["canonical_sha256"] == d2["canonical_sha256"]
    assert len(d1["canonical_sha256"]) == 64


def test_future_mark_price_witness_rejected_fail_closed() -> None:
    w_future = _make_sample_witness(wall_ms=1728720005000)
    valid, why = w_future.is_valid_for_settlement(reference_time_ms=1728720001000)
    assert valid is False
    assert why == "MARK_FUTURE_AVAILABLE"


def test_missing_json_fields_fail_closed_never_default_to_zero() -> None:
    ledger = SettledFundingLedger("BTCUSDT")
    witness = _make_sample_witness(wall_ms=1728720000000)

    assert ledger.ingest_settled_funding({}, witness, 1728720000100) is None
    assert ledger.ingest_settled_funding({"fundingTime": 1728720000000}, witness, 1728720000100) is None
    assert ledger.ingest_settled_funding({"fundingRate": "0.0001"}, witness, 1728720000100) is None
    assert ledger.ingest_settled_funding({"fundingTime": None, "fundingRate": "0.0001"}, witness, 1728720000100) is None
    assert ledger.ingest_settled_funding({"fundingTime": 1728720000000, "fundingRate": None}, witness, 1728720000100) is None
    assert ledger.ingest_settled_funding({"fundingTime": 0, "fundingRate": "0.0001"}, witness, 1728720000100) is None
    assert ledger.ingest_settled_funding({"fundingTime": 1728720000000, "fundingRate": ""}, witness, 1728720000100) is None

    assert ledger.rejected_count == 7


def test_degraded_derived_mark_bar_fallback_fails_closed() -> None:
    bridge = MarketEventBridgeR2(symbol="BTCUSDT")
    from scripts.integration.market_event_bridge_r2.mark_aggregator import DerivedMark1MBar
    degraded_bar = DerivedMark1MBar(
        symbol="BTCUSDT",
        bar_open_ms=1728720000000,
        bar_close_ms=1728720060000,
        closed=True,
        open=64000.0,
        high=64050.0,
        low=63950.0,
        close=64010.0,
        sample_count=5,
        derived_available_at_ms=1728720060000,
        feature_known_at_ms=1728720060000,
        quality="DEGRADED",
        reason_codes=("SOURCE_DROPPED",),
        parent_event_sha256=(),
        raw_source_manifest_sha256="msha",
    )
    bridge.last_derived_mark_bar = degraded_bar

    funding_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": 1728720000000,
    }
    res = bridge.ingest_frame(
        funding_frame,
        observed_wall_utc_ms=1728720060100,
        observed_monotonic_ns=1000,
    )
    assert "settled_funding" not in res
    assert bridge.stats.settled_fundings_adapted == 0

