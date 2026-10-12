"""Deterministic unit tests for shadow order execution, protective stops, time caps, and cooldowns.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.account import (
    ExitReason,
    PaperAccount,
    PositionStatus,
)
from scripts.strategy_research.forward_shadow_research_r1.contract import (
    BarData,
)
from scripts.strategy_research.forward_shadow_research_r1.execution import (
    ShadowExecutionEngine,
)
from scripts.strategy_research.forward_shadow_research_r1.fixtures import (
    make_test_book,
)
from scripts.strategy_research.forward_shadow_research_r1.registry import (
    get_default_hypotheses,
)


def test_paper_account_opens_long_position():
    account = PaperAccount(
        initial_capital_usdt=1000.0,
        reserve_fraction=0.05,
        lot_step_btc=0.001,
        cooldown_hours=6,
        taker_fee_bps=5.0,
        adverse_slippage_bps=0.5,
    )
    pos = account.open_shadow_position(
        cell_id="CELL_TEST_6H",
        direction=1,
        entry_decision_ms=10000,
        entry_fill_ms=10000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos is not None
    assert pos.direction == 1
    # Long enters at best_ask + slippage
    assert pos.entry_base_quote == 65001.0
    expected_slip = 65001.0 * (0.5 / 10000.0)
    assert abs(pos.entry_price - (65001.0 + expected_slip)) < 1e-4
    # Usable capital = 950 USDT. 950 / 65001.0325 ~= 0.01461 -> 0.014 BTC
    assert pos.qty_btc == 0.014
    assert pos.status == PositionStatus.OPEN
    assert account.active_position is pos


def test_paper_account_opens_short_position():
    account = PaperAccount(initial_capital_usdt=1000.0)
    pos = account.open_shadow_position(
        cell_id="CELL_TEST_12H",
        direction=-1,
        entry_decision_ms=10000,
        entry_fill_ms=10000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=66000.0,
        target_price=63000.0,
        horizon_ms=12 * 3600 * 1000,
    )
    assert pos is not None
    assert pos.direction == -1
    # Short enters at best_bid - slippage
    assert pos.entry_base_quote == 65000.0
    assert pos.entry_price < 65000.0
    assert pos.qty_btc == 0.014


def test_single_active_position_invariant():
    account = PaperAccount(initial_capital_usdt=1000.0)
    pos1 = account.open_shadow_position(
        cell_id="CELL_1",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos1 is not None

    # Attempt to open second position while pos1 is open
    pos2 = account.open_shadow_position(
        cell_id="CELL_2",
        direction=1,
        entry_decision_ms=2000,
        entry_fill_ms=2000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos2 is None, "Must enforce single active position invariant"


def test_cooldown_blocks_immediate_reentry():
    account = PaperAccount(cooldown_hours=6)
    account.open_shadow_position(
        cell_id="CELL_1",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    exit_time = 1000 + 3600000  # 1 hour later
    account.close_shadow_position(
        exit_fill_ms=exit_time,
        best_bid=66000.0,
        best_ask=66001.0,
        exit_reason=ExitReason.PROFIT_TARGET,
    )

    # 3 hours after exit (within 6h cooldown): must be blocked!
    t_attempt_3h = exit_time + (3 * 3600 * 1000)
    pos_blocked = account.open_shadow_position(
        cell_id="CELL_1",
        direction=1,
        entry_decision_ms=t_attempt_3h,
        entry_fill_ms=t_attempt_3h,
        best_bid=66000.0,
        best_ask=66001.0,
        stop_price=65000.0,
        target_price=68000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos_blocked is None

    # 6 hours + 1 minute after exit: allowed!
    t_attempt_6h = exit_time + (6 * 3600 * 1000) + 60000
    pos_allowed = account.open_shadow_position(
        cell_id="CELL_1",
        direction=1,
        entry_decision_ms=t_attempt_6h,
        entry_fill_ms=t_attempt_6h,
        best_bid=66000.0,
        best_ask=66001.0,
        stop_price=65000.0,
        target_price=68000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos_allowed is not None


def test_protective_stop_before_target_precedence():
    """When both Stop Loss and Profit Target are breached in the same bar, STOP takes precedence."""
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)

    start_ms = 1700000000000
    # Open long position manually in engine's account
    pos = engine.account.open_shadow_position(
        cell_id=hyp.cell_id,
        direction=1,
        entry_decision_ms=start_ms,
        entry_fill_ms=start_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos is not None

    # Extreme volatility bar: Low drops to 63900 (breaching stop) AND High reaches 67100 (breaching target)
    bar = BarData(
        bar_open_ms=start_ms + 60000,
        bar_close_ms=start_ms + 119999,
        closed=True,
        open=65000.0,
        high=67100.0,  # Target breached!
        low=63900.0,   # Stop breached!
        close=65000.0,
        volume=100.0,
    )
    mark_bar = BarData(
        bar_open_ms=bar.bar_open_ms,
        bar_close_ms=bar.bar_close_ms,
        closed=True,
        open=65000.0,
        high=67100.0,
        low=63900.0,
        close=65000.0,
        volume=100.0,
    )

    engine._evaluate_active_position_exits(bar, mark_bar)

    assert engine.account.active_position is None
    closed = engine.account.closed_positions[-1]
    assert closed.exit_reason == ExitReason.STOP_LOSS, "Protective stop must precede target!"


def test_time_cap_exit_trigger():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)

    start_ms = 1700000000000
    pos = engine.account.open_shadow_position(
        cell_id=hyp.cell_id,
        direction=1,
        entry_decision_ms=start_ms,
        entry_fill_ms=start_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,  # 6h = 21,600,000 ms
    )
    assert pos is not None

    # Bar right at the 6h boundary
    bar_end = start_ms + (6 * 3600 * 1000)
    bar = BarData(
        bar_open_ms=bar_end - 59999,
        bar_close_ms=bar_end,
        closed=True,
        open=65500.0,
        high=65600.0,
        low=65400.0,
        close=65550.0,
        volume=10.0,
    )
    mark_bar = bar

    engine._evaluate_active_position_exits(bar, mark_bar)

    assert engine.account.active_position is None
    closed = engine.account.closed_positions[-1]
    assert closed.exit_reason == ExitReason.TIME_CAP_HORIZON


def test_right_censoring_at_stream_end():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_12H"]
    engine = ShadowExecutionEngine(hyp)

    start_ms = 1700000000000
    pos = engine.account.open_shadow_position(
        cell_id=hyp.cell_id,
        direction=1,
        entry_decision_ms=start_ms,
        entry_fill_ms=start_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=12 * 3600 * 1000,
    )
    assert pos is not None

    # Stream ends only 2 hours in
    stream_end = start_ms + (2 * 3600 * 1000)
    summary = engine.finalize_evaluation(stream_end_ms=stream_end)

    assert summary.positions_right_censored_count == 1
    assert summary.positions_closed_count == 0
    assert pos.status == PositionStatus.RIGHT_CENSORED
    assert pos.exit_reason == ExitReason.STREAM_END_RIGHT_CENSORED


def test_unrealized_mae_tracking():
    account = PaperAccount()
    pos = account.open_shadow_position(
        cell_id="CELL_MAE",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65000.0 + (65000.0 * 0.00005),
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    assert pos is not None
    # Price drops to 64500 (adverse excursion)
    pos.update_mae(64500.0)
    assert pos.max_adverse_excursion_bps < -70.0  # Around -76 bps

    # Price rises back to 66000
    pos.update_mae(66000.0)
    # MAE must retain the maximum drawdown seen
    assert pos.max_adverse_excursion_bps < -70.0


def test_deterministic_receipt_sha256():
    account = PaperAccount()
    pos = account.open_shadow_position(
        cell_id="CELL_SHA",
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
    account.close_shadow_position(
        exit_fill_ms=2000,
        best_bid=65500.0,
        best_ask=65501.0,
        exit_reason=ExitReason.PROFIT_TARGET,
    )
    assert len(pos.receipt_sha256) == 64
    assert pos.receipt_sha256 != ""


def test_stop_loss_quote_bounded_under_bouncing_market_bid():
    """Ensure that a long stop loss cannot exit at an unearned higher price if the book bounces above stop."""
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)

    start_ms = 1700000000000
    pos = engine.account.open_shadow_position(
        cell_id=hyp.cell_id,
        direction=1,
        entry_decision_ms=start_ms,
        entry_fill_ms=start_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos is not None

    # The minute bar dipped to 63900 (triggering stop loss)
    bar = BarData(
        bar_open_ms=start_ms + 60000,
        bar_close_ms=start_ms + 119999,
        closed=True,
        open=65000.0,
        high=65100.0,
        low=63900.0,  # Stop loss breached!
        close=65000.0,
        volume=10.0,
    )
    mark_bar = bar

    # But the current book has already bounced to 66000!
    bounced_book = make_test_book(best_bid=66000.0, best_ask=66001.0)
    engine.on_book_update(bounced_book)

    engine._evaluate_active_position_exits(bar, mark_bar)

    assert engine.account.active_position is None
    closed = engine.account.closed_positions[-1]
    assert closed.exit_reason == ExitReason.STOP_LOSS
    # Exit price must be bounded by stop_price (64000.0), NOT 66000.0!
    assert closed.exit_price <= 64000.0
    assert closed.gross_pnl_usdt < 0.0  # Must be a loss, never a fake profit!


def test_stop_loss_quote_bounded_for_short_under_favorable_ask():
    """Ensure that a short stop loss cannot exit at an unearned lower price if the book drops below stop."""
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)

    start_ms = 1700000000000
    pos = engine.account.open_shadow_position(
        cell_id=hyp.cell_id,
        direction=-1,  # Short
        entry_decision_ms=start_ms,
        entry_fill_ms=start_ms,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=66000.0,
        target_price=63000.0,
        horizon_ms=6 * 3600 * 1000,
    )
    assert pos is not None

    # The minute bar spiked to 66100 (triggering short stop loss)
    bar = BarData(
        bar_open_ms=start_ms + 60000,
        bar_close_ms=start_ms + 119999,
        closed=True,
        open=65000.0,
        high=66100.0,  # Short stop breached!
        low=64900.0,
        close=65000.0,
        volume=10.0,
    )
    mark_bar = bar

    # But the current book dropped back to 64000!
    bounced_book = make_test_book(best_bid=63999.0, best_ask=64000.0)
    engine.on_book_update(bounced_book)

    engine._evaluate_active_position_exits(bar, mark_bar)

    assert engine.account.active_position is None
    closed = engine.account.closed_positions[-1]
    assert closed.exit_reason == ExitReason.STOP_LOSS
    # Exit price must be bounded by stop_price (66000.0), NOT 64000.0!
    assert closed.exit_price >= 66000.0
    assert closed.gross_pnl_usdt < 0.0  # Must be a loss, never a fake profit!

