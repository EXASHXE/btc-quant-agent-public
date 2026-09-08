"""P0/P1 correctness gates. Synthetic only; P2-P7 remain deferred."""

from copy import deepcopy
from dataclasses import replace
import math
from unittest.mock import patch

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.benchmarks import BenchmarkEngine
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.economic.policy import TradePolicy
from btc_quant_agent.economic.simulator import EconomicSimulationEngine
from btc_quant_agent.economic.trade_event import TradeAction as A, TradeEvent


def trade(p, action=A.OPEN_LONG, price=100, quantity=1, fee=0, t=1000, asset="BTCUSDT"):
    return p.apply_trade(t, action, asset, price, quantity, fee)


def snapshot(p):
    return deepcopy((p.cash, p.positions, p.trade_history))


def assert_conservation(p, marks):
    realized = math.fsum(e.realized_pnl_usdt for e in p.trade_history)
    fees = math.fsum(e.fee_usdt for e in p.trade_history)
    funding = math.fsum(e.funding_usdt for e in p.trade_history)
    unrealized = math.fsum(
        pos.quantity * (marks[a] - pos.average_entry_price) for a, pos in p.positions.items()
    )
    assert p.cash == pytest.approx(p.initial_cash + realized - fees + funding)
    assert p.total_equity(marks) == pytest.approx(p.cash + unrealized)
    assert math.fsum(e.net_cashflow_usdt for e in p.trade_history) == pytest.approx(
        p.cash - p.initial_cash
    )


@pytest.mark.parametrize("initial", [0.01, 1, 1000, 100000, 1e8])
@pytest.mark.parametrize("nonempty", [False, True])
def test_b1_no_trade_capital_identity(initial, nonempty):
    bars = [Candle("BTCUSDT", "1m", 1000, 60999, 100, 100, 100, 100, 1)] if nonempty else []
    result = EconomicSimulationEngine(TradePolicy("p", "p"), initial_cash=initial).simulate(bars)
    assert result.initial_cash == result.final_equity == initial
    assert result.net_pnl_usdt == result.net_return_pct == result.max_drawdown_usdt == 0
    p = Portfolio(initial_cash=initial)
    assert p.cash == initial and p.total_equity({}) == initial


@pytest.mark.parametrize("initial", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_new_capital_rejected(initial):
    with pytest.raises(ValueError):
        Portfolio(initial_cash=initial)
    with pytest.raises(ValueError):
        EconomicSimulationEngine(TradePolicy("p", "p"), initial_cash=initial)


@pytest.mark.parametrize("side,end,pnl", [(1, 110, 10), (1, 90, -10), (-1, 90, 10), (-1, 110, -10)])
def test_four_direction_hand_calculated_paths(side, end, pnl):
    p = Portfolio(initial_cash=1000)
    opening, closing = (A.OPEN_LONG, A.CLOSE_LONG) if side == 1 else (A.OPEN_SHORT, A.CLOSE_SHORT)
    first = trade(p, opening, fee=0.05)
    assert p.cash == 999.95
    assert first.net_cashflow_usdt == -0.05
    assert p.get_position_quantity() == side
    assert p.positions["BTCUSDT"].average_entry_price == 100
    assert p.positions["BTCUSDT"].unrealized_pnl(end) == pnl
    assert p.total_equity({"BTCUSDT": 100}) == 999.95  # no notional equity jump
    assert_conservation(p, {"BTCUSDT": end})
    fee = end * 0.0005
    last = trade(p, closing, price=end, fee=fee, t=2000)
    assert last.realized_pnl_usdt == pnl
    assert last.quantity == 1 and last.position_after == 0
    assert not p.positions
    assert p.cash == pytest.approx(1000 + pnl - 0.05 - fee)
    assert_conservation(p, {})


@pytest.mark.parametrize("side", [1, -1])
def test_increase_partial_reduce_and_funding_cashflows(side):
    p = Portfolio(initial_cash=1000)
    opening, closing = (A.OPEN_LONG, A.CLOSE_LONG) if side == 1 else (A.OPEN_SHORT, A.CLOSE_SHORT)
    trade(p, opening, price=100, fee=0.05)
    trade(p, opening, price=120, quantity=1, fee=0.06, t=2000)
    assert p.get_position_quantity() == side * 2
    assert p.positions["BTCUSDT"].average_entry_price == 110
    assert p.positions["BTCUSDT"].entry_timestamp_ms == 1000
    assert_conservation(p, {"BTCUSDT": 115})
    f = p.apply_funding(2500, "BTCUSDT", -side * 2.2, 110)
    assert f.net_cashflow_usdt == -side * 2.2
    ev = trade(p, closing, price=130, quantity=0.5, fee=0.0325, t=3000)
    assert ev.quantity == 0.5 and ev.realized_pnl_usdt == side * 10
    assert p.get_position_quantity() == side * 1.5
    assert p.positions["BTCUSDT"].average_entry_price == 110
    assert_conservation(p, {"BTCUSDT": 90})
    p.apply_funding(3500, "BTCUSDT", side * 1.65, 110)
    trade(p, closing, price=90, quantity=1.5, fee=0.0675, t=4000)
    assert not p.positions
    assert_conservation(p, {})
    restored = Portfolio.from_events(1000, p.trade_history)
    assert snapshot(restored) == snapshot(p)


def test_explicit_reversal_sequential_positions_and_same_timestamp_order():
    p = Portfolio(initial_cash=1000)
    for t, action, price in [
        (1000, A.OPEN_LONG, 100),
        (2000, A.CLOSE_LONG, 110),
        (2000, A.OPEN_SHORT, 110),
        (3000, A.CLOSE_SHORT, 100),
        (4000, A.OPEN_LONG, 100),
        (5000, A.CLOSE_LONG, 90),
    ]:
        trade(p, action, price, t=t)
        assert_conservation(p, {"BTCUSDT": price})
    assert p.cash == 1010 and not p.positions


@pytest.mark.parametrize(
    "opening,bad",
    [
        (A.OPEN_LONG, A.OPEN_SHORT),
        (A.OPEN_SHORT, A.OPEN_LONG),
        (A.OPEN_LONG, A.CLOSE_SHORT),
        (A.OPEN_SHORT, A.CLOSE_LONG),
    ],
)
def test_b4_wrong_direction_rejected_without_state_change(opening, bad):
    p = Portfolio(initial_cash=1000)
    trade(p, opening)
    before = snapshot(p)
    with pytest.raises(ValueError):
        trade(p, bad, price=110, fee=0.1, t=2000)
    assert snapshot(p) == before


@pytest.mark.parametrize("closing", [A.CLOSE_LONG, A.CLOSE_SHORT])
def test_missing_or_excess_close_rejected(closing):
    p = Portfolio(initial_cash=1000)
    for quantity in (1, 2):
        before = snapshot(p)
        with pytest.raises(ValueError):
            trade(p, closing, quantity=quantity, t=2000)
        assert snapshot(p) == before
        if quantity == 1:
            trade(p, A.OPEN_LONG if closing == A.CLOSE_LONG else A.OPEN_SHORT)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"t": 0},
        {"t": -1},
        {"t": 1000.5},
        {"t": True},
        {"t": float("nan")},
        {"price": 0},
        {"price": -1},
        {"price": float("nan")},
        {"price": float("inf")},
        {"quantity": 0},
        {"quantity": -1},
        {"quantity": float("nan")},
        {"quantity": float("inf")},
        {"fee": -1},
        {"fee": float("nan")},
        {"fee": float("inf")},
        {"asset": " "},
        {"action": "UNSUPPORTED"},
        {"action": A.FUNDING_SETTLEMENT},
    ],
)
def test_b4_invalid_trade_is_atomic(kwargs):
    p = Portfolio(initial_cash=1000)
    before = snapshot(p)
    with pytest.raises(ValueError):
        trade(p, **kwargs)
    assert snapshot(p) == before


def test_backwards_trade_and_funding_rejected_atomically():
    p = Portfolio(initial_cash=1000)
    trade(p, t=2000)
    before = snapshot(p)
    with pytest.raises(ValueError, match="Backwards"):
        trade(p, A.CLOSE_LONG, t=1999)
    with pytest.raises(ValueError, match="Backwards"):
        p.apply_funding(1999, "BTCUSDT", -1, 100)
    assert snapshot(p) == before


@pytest.mark.parametrize("kind", ["trade", "funding"])
def test_event_construction_failure_is_atomic(kind):
    p = Portfolio(initial_cash=1000)
    trade(p)
    before = snapshot(p)
    with patch(
        "btc_quant_agent.economic.portfolio.TradeEvent", side_effect=ValueError("event rejected")
    ):
        with pytest.raises(ValueError, match="event rejected"):
            if kind == "trade":
                trade(p, A.CLOSE_LONG, price=110, fee=0.5, t=2000)
            else:
                p.apply_funding(2000, "BTCUSDT", -1, 100)
    assert snapshot(p) == before


@pytest.mark.parametrize(
    "t,cashflow,mark",
    [(0, -1, 100), (1000, float("nan"), 100), (1000, -1, 0), (1000, -1, float("inf"))],
)
def test_invalid_funding_is_atomic(t, cashflow, mark):
    p = Portfolio(initial_cash=1000)
    trade(p)
    before = snapshot(p)
    with pytest.raises(ValueError):
        p.apply_funding(t, "BTCUSDT", cashflow, mark)
    assert snapshot(p) == before


def test_zero_position_funding_and_cash_debt_not_reset():
    p = Portfolio(initial_cash=1)
    with pytest.raises(ValueError):
        p.apply_funding(1000, "BTCUSDT", -1, 100)
    p.apply_funding(1000, "BTCUSDT", 0, 100)
    trade(p, fee=1)
    assert p.cash == 0
    restored = Portfolio.from_events(1, p.trade_history)
    assert restored.cash == 0 and restored.get_position_quantity() == 1
    trade(p, A.CLOSE_LONG, price=99, fee=0.1, t=2000)
    assert p.cash == pytest.approx(-1.1)
    assert Portfolio.from_events(1, p.trade_history).cash == p.cash
    # Direct snapshot injection is deliberately unsupported.
    with pytest.raises(TypeError):
        Portfolio(initial_cash=1000, cash=0)


def test_replay_rejects_tampered_cash_and_invalid_serialized_timestamp():
    p = Portfolio(initial_cash=1000)
    ev = trade(p)
    with pytest.raises(ValueError, match="disagrees"):
        Portfolio.from_events(1000, [replace(ev, cash_after=1001)])
    with pytest.raises(ValueError):
        TradeEvent.from_dict({**ev.to_dict(), "timestamp_ms": 1000.5})
    assert snapshot(Portfolio.from_events(1000, [TradeEvent.from_dict(ev.to_dict())])) == snapshot(
        p
    )


def test_numeric_overflow_does_not_commit():
    p = Portfolio(initial_cash=1000)
    trade(p, quantity=1e308)
    before = snapshot(p)
    with pytest.raises(ValueError):
        trade(p, A.CLOSE_LONG, price=200, quantity=1e308, t=2000)
    assert snapshot(p) == before


def test_mark_to_market_requires_valid_price():
    p = Portfolio(initial_cash=1000)
    trade(p)
    for marks in ({}, {"BTCUSDT": 0}, {"BTCUSDT": float("nan")}):
        with pytest.raises(ValueError):
            p.total_equity(marks)


@pytest.mark.parametrize("pnl", [-1e6, 0, 1, 1e6])
def test_p0_unverified_summary_never_qualifies(pnl):
    policy = TradePolicy("p", "p")
    base = EconomicSimulationEngine(policy).simulate([])
    forged = replace(base, net_pnl_usdt=pnl, final_equity=100000 + pnl, net_return_pct=pnl / 100000)
    bars = [Candle("BTCUSDT", "1m", 1000, 60999, 100, 100, 100, 100, 1)]
    result = BenchmarkEngine(FeeModel(0, 0, SlippageMode.ZERO)).evaluate_economic_qualification(
        forged, bars, policy
    )
    assert result["economic_qualification_passed"] is False
    assert result["qualification_evaluated"] is False
    assert result["diagnostic_only"] is True and result["verdict"] == "NOT_TESTABLE"
    assert result["comparisons"]["beats_cash"] == (pnl > 0)
