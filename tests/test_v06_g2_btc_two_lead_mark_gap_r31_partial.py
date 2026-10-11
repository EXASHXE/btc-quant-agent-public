"""Synthetic-only funding coverage invariants for the R3.1 partial route."""
from decimal import Decimal

import numpy as np
import pytest

from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.partial import (
    _mark_map,
    _summarize,
    attribute_trade,
)


def trade(*, side=1, entry=0, exit_at=120_000):
    return {"event_id": "FIXED_EVENT", "side": side, "quantity": "0.1",
            "entry_notional": "10", "net_usdt": "0.2", "entry_at": entry, "exit_at": exit_at}


def funding(at=60_000, rate="0.001", **extra):
    return {"settlement_at": at, "rate": rate, **extra}


def test_long_positive_rate_is_a_debit():
    row = attribute_trade(trade(), [funding()], {0: Decimal(100)})
    assert row["total_signed_cash_usdt"] == "-0.0100"
    assert row["net_after_funding_bps"] == "190.0000"


def test_short_positive_rate_is_a_credit():
    row = attribute_trade(trade(side=-1), [funding()], {0: Decimal(100)})
    assert row["total_signed_cash_usdt"] == "0.0100"


def test_negative_rate_reverses_payment_direction():
    long = attribute_trade(trade(), [funding(rate="-0.001")], {0: Decimal(100)})
    short = attribute_trade(trade(side=-1), [funding(rate="-0.001")], {0: Decimal(100)})
    assert Decimal(long["total_signed_cash_usdt"]) > 0
    assert Decimal(short["total_signed_cash_usdt"]) < 0


def test_missing_exact_preceding_minute_never_searches_earlier_mark():
    row = attribute_trade(trade(exit_at=180_000), [funding(at=120_000)], {0: Decimal(100)})
    assert row["settlements"][0]["required_mark_minute"] == 60_000
    assert row["settlements"][0]["signed_cash_usdt"] is None
    assert row["funding_status"] == "UNKNOWN_REQUIRED_MARK"


def test_funding_at_exit_is_excluded_and_at_entry_is_included():
    row = attribute_trade(trade(entry=60_000, exit_at=120_000),
                          [funding(at=60_000), funding(at=120_000)], {0: Decimal(100)})
    assert row["settlement_count"] == 1
    assert row["settlements"][0]["settlement_at"] == 60_000


def test_proven_settlement_mark_can_cover_missing_minute():
    row = attribute_trade(trade(), [funding(mark_price="123", mark_price_source_proven=True)], {})
    assert row["settlements"][0]["mark_basis"] == "PROVEN_PROVIDER_SETTLEMENT_MARK"
    assert row["funding_status"] == "COMPLETE"
    assert row["total_signed_cash_usdt"] == "-0.0123"


def test_unproven_settlement_mark_fails_closed():
    with pytest.raises(ValueError, match="unproven"):
        attribute_trade(trade(), [funding(mark_price="123")], {})


def test_partial_coverage_suppresses_full_period_mean():
    rows = [attribute_trade(trade(), [funding()], {0: Decimal(100)}),
            attribute_trade({**trade(exit_at=180_000), "event_id": "MISSING"}, [funding(at=120_000)], {})]
    summary = _summarize(rows)
    assert summary["known_settlement_pairs"] == 1
    assert summary["event_coverage_pct"] == 50
    assert summary["full_period_after_funding_mean_net_bps"] is None
    assert summary["fully_covered_subset_mean_net_bps"] is not None
    assert summary["unknown_trade_ids"] == ["MISSING"]


def test_zero_event_trade_is_covered_without_any_mark():
    row = attribute_trade(trade(), [], {})
    assert row["funding_status"] == "COMPLETE"
    assert row["total_signed_cash_usdt"] == "0"
    assert _summarize([row])["event_coverage_pct"] == 100


def test_zero_rate_proves_zero_cash_even_when_mark_missing():
    row = attribute_trade(trade(), [funding(rate="0")], {})
    assert row["funding_status"] == "COMPLETE"
    assert row["settlements"][0]["mark_basis"] == "ZERO_RATE_MARK_NOT_REQUIRED"


def test_duplicate_or_unsorted_funding_events_fail():
    with pytest.raises(ValueError, match="duplicate or unordered"):
        attribute_trade(trade(), [funding(), funding()], {})


def test_sparse_mark_map_rejects_duplicate_and_bad_ohlc():
    minute = 1_609_459_200_000  # 2021-01-01 00:00 UTC
    valid = np.array([[minute, 100, 101, 99, 100]], dtype=float)
    with pytest.raises(ValueError, match="duplicate"):
        _mark_map({(2021, 1): np.vstack([valid, valid])})
    with pytest.raises(ValueError, match="OHLC"):
        _mark_map({(2021, 1): np.array([[minute, 100, 99, 98, 100]], dtype=float)})


def test_known_plus_unknown_cash_does_not_become_partial_total():
    row = attribute_trade(trade(exit_at=240_000),
                          [funding(60_000), funding(180_000)], {0: Decimal(100)})
    assert row["known_signed_cash_usdt"] == "-0.0100"
    assert row["total_signed_cash_usdt"] is None
    assert row["net_after_funding_bps"] is None
    assert row["unresolved_cash_bound"] == "UNBOUNDED_FROM_ADMITTED_SOURCE"
