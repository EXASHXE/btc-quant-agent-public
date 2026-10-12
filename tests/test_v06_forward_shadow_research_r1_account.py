"""Deterministic unit tests for paper account accounting, reserve guards, and funding accruals.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.account import (
    CostCompleteness,
    ExitReason,
    PaperAccount,
)
from scripts.strategy_research.forward_shadow_research_r1.contract import (
    SettledFundingData,
)


def test_initial_account_state():
    acc = PaperAccount(initial_capital_usdt=1000.0, reserve_fraction=0.05)
    assert acc.cash_usdt == 1000.0
    assert acc.reserve_usdt == 50.0
    assert acc.usable_capital_usdt == 950.0
    assert acc.active_position is None
    assert acc.last_exit_ms == -1


def test_reserve_updates_with_capital():
    acc = PaperAccount(initial_capital_usdt=1000.0, reserve_fraction=0.05)
    acc.cash_usdt = 2000.0
    assert acc.reserve_usdt == 100.0
    assert acc.usable_capital_usdt == 1900.0

    acc.cash_usdt = 500.0
    assert acc.reserve_usdt == 25.0
    assert acc.usable_capital_usdt == 475.0


def test_lot_size_step_alignment():
    acc = PaperAccount(initial_capital_usdt=1000.0, reserve_fraction=0.05, lot_step_btc=0.001)
    # Price = 65000.0. Usable = 950.0. 950 / 65000 = 0.014615...
    # Stepped: floor(14.615) * 0.001 = 0.014 BTC
    lot = acc.calculate_lot_size(65000.0)
    assert lot == 0.014


def test_lot_size_insufficient_capital():
    acc = PaperAccount(initial_capital_usdt=10.0, reserve_fraction=0.05, lot_step_btc=0.001)
    # Usable = 9.5 USDT. 9.5 / 65000 = 0.000146 < 0.001 min step
    lot = acc.calculate_lot_size(65000.0)
    assert lot == 0.0


def test_realized_funding_accrual_long():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    pos = acc.open_shadow_position(
        cell_id="CELL_FUND",
        direction=1,  # Long
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    assert pos is not None
    # Positive funding rate: Long pays (- qty * mark * rate)
    f_data = SettledFundingData(
        funding_time_ms=2000,
        funding_rate=0.0001,  # 1 bp
        mark_price=65000.0,
        settled=True,
    )
    receipt = pos.apply_funding(f_data, observed_at_ms=2005)
    assert receipt is not None
    expected_flow = - 1.0 * pos.qty_btc * 65000.0 * 0.0001
    assert abs(receipt.cash_flow_usdt - expected_flow) < 1e-6
    assert abs(pos.total_funding_usdt - expected_flow) < 1e-6


def test_realized_funding_accrual_short():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    pos = acc.open_shadow_position(
        cell_id="CELL_FUND_SHORT",
        direction=-1,  # Short
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=66000.0,
        target_price=63000.0,
        horizon_ms=3600000,
    )
    assert pos is not None
    # Positive funding rate: Short receives (+ qty * mark * rate)
    f_data = SettledFundingData(
        funding_time_ms=2000,
        funding_rate=0.0001,
        mark_price=65000.0,
        settled=True,
    )
    receipt = pos.apply_funding(f_data, observed_at_ms=2005)
    assert receipt is not None
    expected_flow = 1.0 * pos.qty_btc * 65000.0 * 0.0001
    assert abs(receipt.cash_flow_usdt - expected_flow) < 1e-6
    assert pos.total_funding_usdt > 0.0


def test_negative_funding_rate_long():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    pos = acc.open_shadow_position(
        cell_id="CELL_FUND_NEG",
        direction=1,  # Long
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    assert pos is not None
    # Negative funding rate: Long receives
    f_data = SettledFundingData(
        funding_time_ms=2000,
        funding_rate=-0.0002,  # -2 bps
        mark_price=65000.0,
        settled=True,
    )
    receipt = pos.apply_funding(f_data, observed_at_ms=2005)
    assert receipt is not None
    assert receipt.cash_flow_usdt > 0.0
    assert pos.total_funding_usdt > 0.0


def test_estimated_funding_rejected_from_cash():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    pos = acc.open_shadow_position(
        cell_id="CELL_EST",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    assert pos is not None
    # Estimated funding (settled = False)
    f_est = SettledFundingData(
        funding_time_ms=2000,
        funding_rate=0.0005,
        mark_price=65000.0,
        settled=False,
    )
    receipt = pos.apply_funding(f_est, observed_at_ms=2005)
    assert receipt is None
    assert pos.total_funding_usdt == 0.0
    assert len(pos.funding_receipts) == 0


def test_cost_completeness_passes_when_receipt_present():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    # Entry at 07:00 UTC (25,200,000 ms)
    # Exit at 09:00 UTC (32,400,000 ms) -> spans 08:00 UTC (28,800,000 ms)
    entry_ms = 25200000
    exit_ms = 32400000
    pos = acc.open_shadow_position(
        cell_id="CELL_CC_PASS",
        direction=1,
        entry_decision_ms=entry_ms,
        entry_fill_ms=entry_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=12 * 3600 * 1000,
    )
    assert pos is not None
    # Apply official settled funding at 28,800,000 ms
    pos.apply_funding(
        SettledFundingData(28800000, 0.0001, 65000.0, settled=True),
        observed_at_ms=28800005,
    )
    acc.close_shadow_position(exit_ms, 65500.0, 65501.0, ExitReason.TIME_CAP_HORIZON)
    assert pos.cost_completeness == CostCompleteness.COST_COMPLETE


def test_cost_completeness_fails_when_receipt_missing():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    # Entry at 07:00 UTC, Exit at 09:00 UTC -> spans 08:00 UTC settlement
    entry_ms = 25200000
    exit_ms = 32400000
    pos = acc.open_shadow_position(
        cell_id="CELL_CC_FAIL",
        direction=1,
        entry_decision_ms=entry_ms,
        entry_fill_ms=entry_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=12 * 3600 * 1000,
    )
    assert pos is not None
    # DO NOT apply funding receipt!
    acc.close_shadow_position(exit_ms, 65500.0, 65501.0, ExitReason.TIME_CAP_HORIZON)
    assert pos.cost_completeness == CostCompleteness.PARTIAL_ECONOMICS_UNKNOWN


def test_cash_balance_and_net_bps_after_exit():
    acc = PaperAccount(
        initial_capital_usdt=1000.0,
        taker_fee_bps=5.0,
        adverse_slippage_bps=0.5,
    )
    pos = acc.open_shadow_position(
        cell_id="CELL_PNL",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    assert pos is not None
    initial_cash = acc.cash_usdt

    acc.close_shadow_position(
        exit_fill_ms=2000,
        best_bid=65500.0,
        best_ask=65501.0,
        exit_reason=ExitReason.PROFIT_TARGET,
    )

    # Cash should be updated by net_pnl_usdt
    assert abs(acc.cash_usdt - (initial_cash + pos.net_pnl_usdt)) < 1e-6
    # Net bps should be calculated
    expected_bps = (pos.net_pnl_usdt / pos.entry_notional_usdt) * 10000.0
    assert abs(pos.net_bps - expected_bps) < 1e-6
