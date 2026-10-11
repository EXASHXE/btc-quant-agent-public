"""Synthetic causality and cash invariants; no historical source access."""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.economics import (
    funded_fold,
    funding_overlay,
    mark_account_curve,
    mark_close_asof,
    validate_mark,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import BASE, simulate_fold

MINUTE = 60_000


def marks(n: int = 70, price: float = 100.0) -> np.ndarray:
    return np.array([[i * MINUTE, price, price, price, price] for i in range(n)], dtype=float)


def trade(*, side: int = 1, entry: int = MINUTE, exit_at: int = 10 * MINUTE) -> dict:
    return {
        "side": side, "entry_at": entry, "exit_at": exit_at,
        "quantity": 2, "entry_notional": 200,
        "net_usdt": 3, "effective_entry": 100,
        "fee_entry": 0.12,
    }


def event(t: int, rate: str, **extra) -> dict:
    return {"settlement_at": t, "rate": rate, **extra}


def test_mark_latest_completed_minute_never_future() -> None:
    m = marks(3)
    m[0, 4], m[1, 4] = 101, 999
    assert mark_close_asof(m, MINUTE) == (Decimal("101.0"), MINUTE - 1)
    assert mark_close_asof(m, 2 * MINUTE - 1) == (Decimal("999.0"), 2 * MINUTE - 1)
    with pytest.raises(ValueError, match="No completed"):
        mark_close_asof(m, MINUTE - 2)


@pytest.mark.parametrize("mutation", [
    lambda m: m.__setitem__((1, 0), 0),
    lambda m: m.__setitem__((1, 2), 90),
    lambda m: m.__setitem__((1, 3), 110),
    lambda m: m.__setitem__((1, 4), -1),
    lambda m: m.__setitem__((1, 1), float("nan")),
])
def test_bad_mark_identity_or_ohlc_fails(mutation) -> None:
    m = marks(3)
    mutation(m)
    with pytest.raises(ValueError):
        validate_mark(m)


@pytest.mark.parametrize("side,rate,expected", [
    (1, "0.0001", "-0.02000"),
    (-1, "0.0001", "0.02000"),
    (1, "-0.0001", "0.02000"),
    (-1, "-0.0001", "-0.02000"),
])
def test_signed_funding_cash_four_quadrants(side, rate, expected) -> None:
    result = funding_overlay(trade(side=side), marks(), [event(8 * MINUTE, rate)])
    assert Decimal(result["funding_cash_usdt"]) == Decimal(expected)
    assert result["settlements"][0]["mark_basis"] == "LATEST_COMPLETED_1M_MARK_CLOSE_APPROXIMATION"
    assert result["settlements"][0]["mark_close_at"] == 8 * MINUTE - 1


def test_entry_inclusive_exit_exclusive_and_sixty_second_sensitivity() -> None:
    t = trade(entry=2 * MINUTE, exit_at=8 * MINUTE)
    events = [event(2 * MINUTE, "0.0001"), event(8 * MINUTE, "0.0002")]
    assert funding_overlay(t, marks(), events)["settlement_count"] == 1
    assert funding_overlay(t, marks(), events, shift_entry_ms=MINUTE)["settlement_count"] == 0
    assert funding_overlay(t, marks(), events, shift_exit_ms=MINUTE)["settlement_count"] == 2


def test_future_rate_or_mark_correction_cannot_change_past_cash() -> None:
    t = trade(exit_at=9 * MINUTE)
    m = marks()
    baseline = funding_overlay(t, m, [event(8 * MINUTE, "0.0001")])
    m[9, 4] = 99999
    later = funding_overlay(t, m, [event(8 * MINUTE, "0.0001"), event(10 * MINUTE, "0.099")])
    assert baseline["funding_cash_usdt"] == later["funding_cash_usdt"]


@pytest.mark.parametrize("events", [
    [event(2 * MINUTE, "0.001"), event(2 * MINUTE, "0.001")],
    [event(3 * MINUTE, "0.001"), event(2 * MINUTE, "0.001")],
    [event(2 * MINUTE, "0.01%")],
    [event(2 * MINUTE, "NaN")],
])
def test_duplicate_out_of_order_or_wrong_units_fail(events) -> None:
    with pytest.raises(ValueError):
        funding_overlay(trade(), marks(), events)


def test_source_settlement_mark_needs_provenance() -> None:
    e = event(8 * MINUTE, "0.0001", mark_price="102")
    with pytest.raises(ValueError, match="Unproven"):
        funding_overlay(trade(), marks(), [e])
    e["mark_price_source_proven"] = True
    result = funding_overlay(trade(), marks(), [e])
    assert Decimal(result["funding_cash_usdt"]) == Decimal("-0.0204")
    assert result["settlements"][0]["mark_basis"] == "PROVIDER_SETTLEMENT_MARK"


def test_no_observed_crossing_means_zero_only_on_complete_supplied_stream() -> None:
    result = funding_overlay(trade(exit_at=4 * MINUTE), marks(), [event(8 * MINUTE, "0.001")])
    assert result["settlement_count"] == 0
    assert Decimal(result["funding_cash_usdt"]) == 0


def test_mark_curve_funding_receipt_and_terminal_cash_reconcile() -> None:
    t = trade(entry=MINUTE, exit_at=10 * MINUTE)
    overlay = funding_overlay(t, marks(), [event(8 * MINUTE, "0.001")])
    t["funding_settlements"] = overlay["settlements"]
    t["funding_cash_usdt"] = overlay["funding_cash_usdt"]
    out = mark_account_curve([t], marks(), MINUTE, 12 * MINUTE, 1000., BASE)
    assert out["ending_equity"] == pytest.approx(1002.8)
    curve = out["minute_equity_curve"]
    assert curve[6, 1] > curve[7, 1]  # funding paid at minute 8 boundary
    assert curve[9, 1] == pytest.approx(1002.8)


def test_mark_curve_disagrees_with_false_funding_ledger() -> None:
    t = trade()
    t["funding_settlements"] = []
    t["funding_cash_usdt"] = "1"
    with pytest.raises(ValueError, match="disagree"):
        mark_account_curve([t], marks(), MINUTE, 12 * MINUTE, 1000., BASE)


def test_mark_curve_price_changes_risk_without_changing_fills() -> None:
    t = trade()
    t["funding_settlements"] = []
    t["funding_cash_usdt"] = "0"
    flat = mark_account_curve([t], marks(), MINUTE, 12 * MINUTE, 1000., BASE)
    m = marks()
    m[5, 1:] = [50, 50, 50, 50]
    stressed = mark_account_curve([t], m, MINUTE, 12 * MINUTE, 1000., BASE)
    assert stressed["ending_equity"] == flat["ending_equity"]
    assert stressed["max_mtm_drawdown_pct"] > flat["max_mtm_drawdown_pct"]


def test_funded_book_same_r2_episode_and_observed_funding_changes_cash() -> None:
    last = np.array([[i * MINUTE, 100, 100, 100, 100, 1, 0.5] for i in range(70)], dtype=float)
    mark = marks()
    signal = {"event_time": 0, "decision_at": MINUTE, "entry_at": 2 * MINUTE,
              "side": 1, "stop": 90, "decision_close": 100, "atr_hour": 40, "event_id": "S"}
    candidate = {"id": "FIXED_SYNTHETIC", "horizon_hours": 1, "cooldown_hours": 4, "target_R": 2}
    fold = {"start_ms": 2 * MINUTE, "end_ms": 65 * MINUTE, "year": 2021, "month": 2}
    baseline = simulate_fold(last, [signal], candidate, fold, BASE)
    funded = funded_fold(last, mark, [event(8 * MINUTE, "0.001")], [signal], candidate, fold, BASE)
    assert len(baseline["trades"]) == len(funded["trades"]) == 1
    a, b = baseline["trades"][0], funded["trades"][0]
    assert (a["entry_at"], a["exit_at"], a["quantity"], a["fee_entry"], a["fee_exit"]) == (
        b["entry_at"], b["exit_at"], b["quantity"], b["fee_entry"], b["fee_exit"])
    assert funded["ending_equity"] == pytest.approx(
        baseline["ending_equity"] + float(b["funding_cash_usdt"]))
    assert funded["minute_equity_curve"][-1, 1] == pytest.approx(funded["ending_equity"])


def test_due_funding_can_reduce_later_size_without_changing_signals() -> None:
    last = np.array([[i * MINUTE, 100, 100, 100, 100, 1, 0.5] for i in range(380)], dtype=float)
    mark = marks(380)
    signals = [
        {"event_time": 0, "decision_at": MINUTE, "entry_at": 2 * MINUTE,
         "side": 1, "stop": 90, "decision_close": 100, "atr_hour": 40, "event_id": "A"},
        {"event_time": 308 * MINUTE, "decision_at": 309 * MINUTE, "entry_at": 310 * MINUTE,
         "side": 1, "stop": 90, "decision_close": 100, "atr_hour": 40, "event_id": "B"},
    ]
    candidate = {"id": "FIXED_SYNTHETIC", "horizon_hours": 1, "cooldown_hours": 4, "target_R": 2}
    fold = {"start_ms": 2 * MINUTE, "end_ms": 373 * MINUTE}
    baseline = funded_fold(last, mark, [], signals, candidate, fold, BASE)
    adverse = funded_fold(last, mark, [event(8 * MINUTE, "0.05")], signals, candidate, fold, BASE)
    assert len(baseline["trades"]) == len(adverse["trades"]) == 2
    assert baseline["trades"][0]["quantity"] == adverse["trades"][0]["quantity"]
    assert adverse["trades"][1]["quantity"] < baseline["trades"][1]["quantity"]
    assert [t["event_id"] for t in adverse["trades"]] == ["A", "B"]
