"""Category 5: Settled Funding Decimal Ledger Unit Tests.

Covers:
- Settled vs estimated rate discrimination
- Exact signed cash flow formula for long and short positions
- Precise Decimal arithmetic and ROUND_HALF_EVEN quantization
- Rejection of future timestamps, missing Mark price (COST_INCOMPLETE), non-positive Mark price
- Journal deduplication and distinct settlement isolation
- Compatibility with B's parse_funding_payload and C's MarketPitPort funding validation
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.integration.market_event_bridge_r2.funding_adapter import (
    SettledFundingEntry,
    SettledFundingLedger,
)

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.integration.market_event_bridge_r2.portable_ci_refs import (
    ensure_portable_b_on_path,
    ensure_portable_c_on_path,
)

ensure_portable_b_on_path()
ensure_portable_c_on_path()


def test_settled_funding_entry_creation():
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.50"),
        settlement_id="BTCUSDT:1728720000000:0.00010000",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000100,
        feature_known_at_ms=1728720000100,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    assert entry.symbol == "BTCUSDT"
    assert entry.funding_time_ms == 1728720000000
    assert entry.funding_rate == Decimal("0.00010000")
    assert entry.mark_price == Decimal("64000.50")
    assert entry.settled is True
    assert entry.rate_type == "SETTLED_REALIZED"


def test_settled_funding_entry_immutable():
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal("64000.0"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    with pytest.raises(AttributeError):
        entry.symbol = "ETHUSDT"  # type: ignore


def test_cash_flow_long_position_positive_rate():
    # Long (+1.5 BTC) pays positive rate (+0.0001) at mark 60000 => cf = -1 * 1.5 * 0.0001 * 60000 = -9.0 USD
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal("60000.00"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("1.5"))
    assert cf == Decimal("-9.00000000")


def test_cash_flow_short_position_positive_rate():
    # Short (-1.5 BTC) receives positive rate (+0.0001) at mark 60000 => cf = -1 * (-1.5) * 0.0001 * 60000 = +9.0 USD
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal("60000.00"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("-1.5"))
    assert cf == Decimal("9.00000000")


def test_cash_flow_long_position_negative_rate():
    # Long (+2.0 BTC) receives negative rate (-0.0002) at mark 50000 => cf = -1 * 2 * (-0.0002) * 50000 = +20.0 USD
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("-0.0002"),
        mark_price=Decimal("50000.00"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("2.0"))
    assert cf == Decimal("20.00000000")


def test_cash_flow_short_position_negative_rate():
    # Short (-2.0 BTC) pays negative rate (-0.0002) at mark 50000 => cf = -1 * (-2) * (-0.0002) * 50000 = -20.0 USD
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("-0.0002"),
        mark_price=Decimal("50000.00"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("-2.0"))
    assert cf == Decimal("-20.00000000")


def test_cash_flow_zero_position():
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.0005"),
        mark_price=Decimal("70000.00"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("0.0"))
    assert cf == Decimal("0.00000000")


def test_cash_flow_decimal_precision_round_half_even():
    # 0.00001234 BTC * 0.00010000 * 64123.456789 = -0.000079128... -> rounded to 8 decimal places
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64123.456789"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("0.00001234"))
    assert cf.as_tuple().exponent == -8


def test_cash_flow_large_position_precise():
    # 500.12345678 BTC at 65432.10 * 0.000375
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.000375"),
        mark_price=Decimal("65432.10"),
        settlement_id="s1",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    cf = entry.calculate_cash_flow(Decimal("500.12345678"))
    assert isinstance(cf, Decimal)
    assert cf < Decimal(0)


def test_to_b_funding_payload_format():
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.0"),
        settlement_id="BTCUSDT:1728720000000:0.00010000",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    p = entry.to_b_funding_payload()
    assert p["T"] == 1728720000000
    assert p["r"] == 0.0001
    assert p["p"] == 64000.0
    assert p["settled"] is True
    assert p["estimated"] is False
    assert p["symbol"] == "BTCUSDT"


def test_to_c_funding_payload_format():
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.0"),
        settlement_id="BTCUSDT:1728720000000:0.00010000",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    p = entry.to_c_funding_payload()
    assert set(p.keys()) == {
        "event_id",
        "settlement_id",
        "settlement_at_ms",
        "rate_fraction",
        "settled",
        "rate_type",
    }
    assert p["settled"] is True
    assert p["rate_type"] == "SETTLED_REALIZED"
    assert p["settlement_at_ms"] == 1728720000000
    assert p["rate_fraction"] == "0.00010000"


def test_ledger_ingest_valid():
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00015000",
        "fundingTime": 1728720000000,
    }
    entry = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price="64500.00",
        observed_wall_utc_ms=1728720001000,
        raw_manifest_sha256="feedbeef",
    )
    assert entry is not None
    assert entry.funding_rate == Decimal("0.00015000")
    assert entry.mark_price == Decimal("64500.00")
    assert entry.funding_time_ms == 1728720000000
    assert len(ledger.journal) == 1
    assert ledger.rejected_count == 0


def test_ledger_rejects_future_timestamp():
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00015000",
        "fundingTime": 1728720005000,  # in the future
    }
    entry = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price=64000.0,
        observed_wall_utc_ms=1728720000000,  # wall is before funding
    )
    assert entry is None
    assert ledger.rejected_count == 1
    assert len(ledger.journal) == 0


def test_ledger_rejects_none_mark_price():
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00015000",
        "fundingTime": 1728720000000,
    }
    # COST_INCOMPLETE: missing mark price fails closed
    entry = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price=None,
        observed_wall_utc_ms=1728720001000,
    )
    assert entry is None
    assert ledger.rejected_count == 1


def test_ledger_rejects_zero_or_negative_mark_price():
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00015000",
        "fundingTime": 1728720000000,
    }
    entry_zero = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price=0.0,
        observed_wall_utc_ms=1728720001000,
    )
    assert entry_zero is None
    assert ledger.rejected_count == 1

    entry_neg = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price=-100.0,
        observed_wall_utc_ms=1728720001000,
    )
    assert entry_neg is None
    assert ledger.rejected_count == 2


def test_ledger_deduplication():
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": 1728720000000,
    }
    e1 = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price="64000.0",
        observed_wall_utc_ms=1728720001000,
    )
    e2 = ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price="64000.0",
        observed_wall_utc_ms=1728720002000,
    )
    assert e1 is e2
    assert ledger.duplicate_count == 1
    assert len(ledger.journal) == 1


def test_ledger_different_settlements():
    ledger = SettledFundingLedger("BTCUSDT")
    raw1 = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": 1728720000000,
    }
    raw2 = {
        "symbol": "BTCUSDT",
        "fundingRate": "-0.00005000",
        "fundingTime": 1728748800000,
    }
    e1 = ledger.ingest_settled_funding(
        raw_record=raw1,
        contemporaneous_mark_price=64000.0,
        observed_wall_utc_ms=1728748801000,
    )
    e2 = ledger.ingest_settled_funding(
        raw_record=raw2,
        contemporaneous_mark_price=64500.0,
        observed_wall_utc_ms=1728748801000,
    )
    assert e1 != e2
    assert len(ledger.journal) == 2
    assert ledger.duplicate_count == 0


def test_ledger_report_generation():
    ledger = SettledFundingLedger("BTCUSDT")
    raw = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": 1728720000000,
    }
    ledger.ingest_settled_funding(
        raw_record=raw,
        contemporaneous_mark_price="60000.0",
        observed_wall_utc_ms=1728720001000,
    )
    rep = ledger.generate_decimal_ledger_report()
    assert rep["schema_version"] == "settled-funding-decimal-ledger-v1"
    assert rep["total_settlements"] == 1
    assert rep["duplicate_count"] == 0
    assert rep["rejected_count"] == 0
    rec = rep["journal_records"][0]
    assert rec["sample_long_1btc_cash_flow"] == "-6.00000000"
    assert rec["sample_short_1btc_cash_flow"] == "6.00000000"


def test_interop_with_b_parse_funding_payload():
    from scripts.strategy_research.forward_shadow_research_r1.contract import (
        parse_funding_payload,
    )

    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.50"),
        settlement_id="BTCUSDT:1728720000000:0.00010000",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="deadbeef",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    b_payload = entry.to_b_funding_payload()
    b_funding_data = parse_funding_payload(b_payload)
    assert b_funding_data.settled is True
    assert b_funding_data.funding_rate == 0.0001
    assert b_funding_data.mark_price == 64000.50
    assert b_funding_data.funding_time_ms == 1728720000000


def test_interop_with_c_market_pit_port():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort

    port = MarketPitPort(
        expected_stream_id="btcusdt@kline_1m",
        expected_manifest_sha256="manifest_hash_test",
    )
    entry = SettledFundingEntry(
        symbol="BTCUSDT",
        funding_time_ms=1728720000000,
        funding_rate=Decimal("0.00010000"),
        mark_price=Decimal("64000.0"),
        settlement_id="BTCUSDT:1728720000000:0.00010000",
        settled=True,
        rate_type="SETTLED_REALIZED",
        derived_available_at_ms=1728720000000,
        feature_known_at_ms=1728720000000,
        producer_manifest_sha256="manifest_hash_test",
        quality="VERIFIED",
        reason_codes=("OK",),
    )
    c_payload = entry.to_c_funding_payload()
    import hashlib
    import json
    payload_sha = hashlib.sha256(json.dumps(c_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    env = {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "funding_settled",
        "provider_event_ms": 1728720000000,
        "provider_transaction_ms": 1728720000000,
        "observed_wall_utc_ms": 1728720000000,
        "observed_monotonic_ns": 100_000_000,
        "available_at_ms": 1728720000000,
        "source_stream_id": "btcusdt@kline_1m",
        "connection_epoch": 1,
        "source_sequence": None,
        "payload_sha256": payload_sha,
        "payload": c_payload,
        "quality": "VERIFIED",
        "reason_codes": ["OK"],
        "raw_source_manifest_sha256": "manifest_hash_test",
    }
    result = port.ingest_envelope(env)
    assert result["status"] == "ACCEPTED"
    assert result["g1_event"] is not None
    assert result["g1_event"]["kind"] == "FUNDING"
    assert result["g1_event"]["payload"]["rate_fraction"] == "0.00010000"
