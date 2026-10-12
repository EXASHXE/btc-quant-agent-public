"""Deterministic synthetic test suite for G2 Conditional Exit R1 book & 12h causal decisions."""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.strategy_research.g2_conditional_exit_r1.conditional_book import (
    PartialIneligibleError,
    ack_clock,
    effective_price_decimal,
    evaluate_x1_at_12h,
    evaluate_x2_at_12h,
    execute_conditional_position,
    extract_completed_1h_last_candles,
)
from scripts.strategy_research.g2_exit_horizon_r1.book import position as original_exit_r1_position
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    HOUR,
    MINUTE,
    STRESS,
    _proposed,
)

# Default synthetic start: 2022-05-10 00:00:00 UTC (1652140800000), entry at +46m (mid-hour 00:46:00)
BASE_START_MS = 1_652_140_800_000
DEFAULT_ENTRY_OFFSET_MIN = 46


def make_fixture(
    side: int = 1,
    total_minutes: int = 1600,
    entry_offset_min: int = DEFAULT_ENTRY_OFFSET_MIN,
    base_price: float = 1000.0,
    start_ms: int = BASE_START_MS,
) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    """Create contiguous 1m Last and Mark arrays with a valid candidate & event."""
    last = np.empty((total_minutes, 7), dtype=float)
    opens = start_ms + np.arange(total_minutes, dtype=np.int64) * MINUTE
    last[:, 0] = opens
    last[:, 1:5] = base_price
    last[:, 5] = 10.0
    last[:, 6] = opens + MINUTE - 1
    mark = last[:, :5].copy()

    entry_at = start_ms + entry_offset_min * MINUTE
    event = {
        "event_time": entry_at - 2 * MINUTE,
        "decision_at": entry_at - MINUTE,
        "entry_at": entry_at,
        "decision_close": base_price,
        "atr_hour": 100.0,
        "side": side,
        "stop": (base_price - 100.0) if side > 0 else (base_price + 100.0),
        "event_id": f"syn_{entry_at}_{side}",
    }
    cand = {
        "id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "horizon_hours": 12,
        "target_R": 2.0,
        "cooldown_hours": 6,
    }
    return last, mark, event, cand


# -------------------------------------------------------------------------
# 1. X1_NET_POSITIVE_AT_12H: Positive, Negative, Zero, and Cost Friction
# -------------------------------------------------------------------------


@pytest.mark.parametrize("side", [1, -1])
def test_x1_positive_net_at_12h_extends_to_18h(side: int) -> None:
    last, mark, event, cand = make_fixture(side=side)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    # Set completed 1m Mark close at idx_12h - 1 well in profit (+20 USD for long, -20 USD for short)
    mark[idx_12h - 1, 1:5] = 1020.0 if side > 0 else 980.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["reached_12h_time_cap_boundary"] is True
    assert res["decision_12h"]["extend_to_18h"] is True
    assert res["decision_12h"]["estimated_liquidation_net_usdt"] > 0.0
    assert res["exit_at"] == event["entry_at"] + 18 * HOUR
    assert res["exit_reason"] == "TIME_CAP"


@pytest.mark.parametrize("side", [1, -1])
def test_x1_negative_net_at_12h_exits_at_12h_identical_to_e0(side: int) -> None:
    last, mark, event, cand = make_fixture(side=side)
    # Flat Mark at 1000.0 -> negative net after entry/exit fees & slippage
    res_x1 = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    res_e0 = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, "E0", 0.2)
    assert res_x1["decision_12h"]["reached_12h_time_cap_boundary"] is True
    assert res_x1["decision_12h"]["extend_to_18h"] is False
    assert res_x1["decision_12h"]["estimated_liquidation_net_usdt"] < 0.0
    assert res_x1["exit_at"] == event["entry_at"] + 12 * HOUR
    assert res_x1["net_after_funding_usdt"] == res_e0["net_after_funding_usdt"]


def test_x1_exact_zero_net_estimate_exits_at_12h() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    proposal = _proposed(last[:, :5], event, cand, BASE)
    # Under BASE (fee=6bps, spread=4bps, slip=3bps) on 1000.0:
    # eff_entry = 1000.5, fee_entry = 1000.5 * 0.2 * 0.0006 = 0.12006
    # Choose mark close at 1002.0 -> 1002.0 * (1 - 0.0005) = 1001.499 -> hyp_eff_exit = 1001.4
    # fee_exit = 1001.4 * 0.2 * 0.0006 = 0.120168
    # price_pnl = (1001.4 - 1000.5) * 0.2 = 0.18000
    # fees = 0.240228 -> net before funding = -0.060228
    # Add positive funding credit of +0.060228 (rate = -0.00030114 at mark 1000.0 on qty 0.2)
    mark[idx_12h - 1, 1:5] = 1002.0
    funding = [{"settlement_at": BASE_START_MS + 8 * HOUR, "rate": "-0.00030114"}]
    x1_info = evaluate_x1_at_12h(
        proposal, mark, funding, BASE, 0.2, event["entry_at"] + 12 * HOUR
    )
    assert x1_info["estimated_liquidation_net_usdt"] == 0.0
    assert x1_info["extend_to_18h"] is False


def test_x1_cost_friction_flips_gross_positive_to_net_negative() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    # Small gross gain (+2.0 USD on 1000.0 = +20 bps), which is < STRESS44 roundtrip (44 bps)
    mark[idx_12h - 1, 1:5] = 1002.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["gross_mark_pnl_usdt"] > 0.0
    assert res["decision_12h"]["estimated_liquidation_net_usdt"] < 0.0
    assert res["decision_12h"]["extend_to_18h"] is False
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR


def test_x1_base_vs_stress_friction_difference() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    # +3.5 USD on 1000.0 (+35 bps): positive under BASE22, negative under STRESS44
    mark[idx_12h - 1, 1:5] = 1003.5
    res_base = execute_conditional_position(
        last[:, :5], mark, [], event, cand, BASE, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    res_stress = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res_base["decision_12h"]["extend_to_18h"] is True
    assert res_stress["decision_12h"]["extend_to_18h"] is False


# -------------------------------------------------------------------------
# 2. Funding Accrual Before vs After 12h & Sign Handling
# -------------------------------------------------------------------------


def test_x1_accrued_funding_before_12h_enables_extension() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1002.0  # Slightly negative without funding under BASE
    # Negative funding rate pays LONG before 12h
    funding = [{"settlement_at": event["entry_at"] + 4 * HOUR, "rate": "-0.005"}]
    res = execute_conditional_position(
        last[:, :5], mark, funding, event, cand, BASE, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["accrued_funding_usdt"] > 0.0
    assert res["decision_12h"]["extend_to_18h"] is True
    assert res["exit_at"] == event["entry_at"] + 18 * HOUR


def test_x1_adverse_funding_before_12h_blocks_extension() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1005.0  # Positive before funding under BASE
    # Large positive funding rate charges LONG before 12h
    funding = [{"settlement_at": event["entry_at"] + 4 * HOUR, "rate": "0.01"}]
    res = execute_conditional_position(
        last[:, :5], mark, funding, event, cand, BASE, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["accrued_funding_usdt"] < 0.0
    assert res["decision_12h"]["extend_to_18h"] is False
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR


def test_x1_ignores_funding_at_or_after_12h_decision() -> None:
    last, mark, event, cand = make_fixture(side=1)
    deadline_12h = event["entry_at"] + 12 * HOUR
    # Huge favorable funding at exact deadline_12h and at +14h must NOT be used at 12h decision
    funding = [
        {"settlement_at": deadline_12h, "rate": "-0.05"},
        {"settlement_at": event["entry_at"] + 14 * HOUR, "rate": "-0.05"},
    ]
    res = execute_conditional_position(
        last[:, :5], mark, funding, event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["accrued_funding_count"] == 0
    assert res["decision_12h"]["accrued_funding_usdt"] == 0.0
    assert res["decision_12h"]["extend_to_18h"] is False
    assert res["settlement_count"] == 0


def test_extended_trade_accrues_funding_in_12h_to_18h_window() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1020.0
    funding = [
        {"settlement_at": event["entry_at"] + 4 * HOUR, "rate": "0.001"},
        {"settlement_at": event["entry_at"] + 14 * HOUR, "rate": "0.002"},
    ]
    res = execute_conditional_position(
        last[:, :5], mark, funding, event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["accrued_funding_count"] == 1
    assert res["settlement_count"] == 2
    assert float(res["funding_cash_usdt"]) == pytest.approx(-0.2 * 1000.0 * 0.003)


def test_funding_publication_lag_sensitivity_at_12h() -> None:
    last, mark, event, cand = make_fixture(side=1)
    deadline_12h = event["entry_at"] + 12 * HOUR
    proposal = _proposed(last[:, :5], event, cand, BASE)
    # Settlement 10 seconds before deadline_12h
    funding = [{"settlement_at": deadline_12h - 10_000, "rate": "-0.01"}]
    no_lag = evaluate_x1_at_12h(proposal, mark, funding, BASE, 0.2, deadline_12h, funding_lag_ms=0)
    with_lag = evaluate_x1_at_12h(
        proposal, mark, funding, BASE, 0.2, deadline_12h, funding_lag_ms=60_000
    )
    assert no_lag["accrued_funding_count"] == 1
    assert with_lag["accrued_funding_count"] == 0
    assert with_lag["lag_excluded_settlement_count"] == 1


# -------------------------------------------------------------------------
# 3. Mark vs Last Divergence at 12h (Mark selection proxy, Last execution)
# -------------------------------------------------------------------------


def test_mark_positive_last_low_at_12h_extends_and_fills_on_last_at_18h() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    idx_18h = DEFAULT_ENTRY_OFFSET_MIN + 18 * 60
    # Mark at 12h is high (1025.0), Last at 12h is low (995.0), Last at 18h is 1010.0, Mark at 18h is 1050.0
    mark[idx_12h - 1, 1:5] = 1025.0
    last[idx_12h, 1:5] = 995.0
    last[idx_18h, 1:5] = 1010.0
    mark[idx_18h - 1, 1:5] = 1050.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["extend_to_18h"] is True
    # Actual exit fill at 18h uses Last (1010.0), never Mark (1050.0)!
    assert res["raw_exit"] == 1010.0


def test_mark_negative_last_positive_at_12h_exits_at_12h_on_last() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    # Mark at 12h is depressed (998.0), Last at 12h open is favorable (1015.0)
    mark[idx_12h - 1, 1:5] = 998.0
    last[idx_12h, 1:5] = 1015.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["extend_to_18h"] is False
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR
    # Exits at 12h using Last open (1015.0), not Mark (998.0)!
    assert res["raw_exit"] == 1015.0


def test_x1_never_uses_uncompleted_12h_mark_bar() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    # The bar opening AT 12h (idx_12h, closing at 12h + 59.999s) has a huge spike to 1200.0,
    # while the last completed bar (idx_12h - 1) is 1000.0.
    mark[idx_12h, 1:5] = 1200.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["mark_close_price"] == 1000.0
    assert res["decision_12h"]["extend_to_18h"] is False


# -------------------------------------------------------------------------
# 4. X2_COMPLETED_4H_TREND_AT_12H & Mid-Hour 1h Candle Close Semantics
# -------------------------------------------------------------------------


@pytest.mark.parametrize("entry_offset_min", [1, 16, 31, 46])
def test_x2_mid_hour_excludes_unclosed_current_hour_bar(entry_offset_min: int) -> None:
    last, _mark, event, _cand = make_fixture(side=1, entry_offset_min=entry_offset_min)
    decision_12h_at = event["entry_at"] + 12 * HOUR
    # Hour 12 (the unclosed hour [12:00, 12:59:59.999] containing 12:01/12:16/12:31/12:46) spikes to 1150.0,
    # while completed hours 8, 9, 10, 11 stay flat at 1000.0.
    unclosed_hour_start_idx = 12 * 60
    last[unclosed_hour_start_idx : unclosed_hour_start_idx + 60, 1:5] = 1150.0
    x2_info = evaluate_x2_at_12h(last[:, :5], 1, decision_12h_at)
    assert x2_info["last_1h_open_at"] == BASE_START_MS + 11 * HOUR
    assert x2_info["last_1h_close_at"] == BASE_START_MS + 12 * HOUR - 1
    assert x2_info["last_1h_close_at"] < decision_12h_at
    assert x2_info["signed_price_diff"] == 0.0
    assert x2_info["extend_to_18h"] is False


@pytest.mark.parametrize("side", [1, -1])
def test_x2_positive_4h_completed_trend_extends_to_18h(side: int) -> None:
    last, mark, event, cand = make_fixture(side=side)
    # Completed hours before 12:46 are hours 8, 9, 10, 11.
    # Set hour 8 close (minute 9*60 - 1) to 1000.0 and hour 11 close (minute 12*60 - 1) to 1010 (long) or 990 (short)
    last[12 * 60 - 1, 4] = 1010.0 if side > 0 else 990.0
    last[12 * 60 - 1, 2] = max(last[12 * 60 - 1, 2], last[12 * 60 - 1, 4])
    last[12 * 60 - 1, 3] = min(last[12 * 60 - 1, 3], last[12 * 60 - 1, 4])
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X2_COMPLETED_4H_TREND_AT_12H", 0.2
    )
    assert res["decision_12h"]["extend_to_18h"] is True
    assert res["decision_12h"]["signed_price_diff"] == 10.0
    assert res["exit_at"] == event["entry_at"] + 18 * HOUR


@pytest.mark.parametrize("side", [1, -1])
def test_x2_negative_4h_completed_trend_exits_at_12h(side: int) -> None:
    last, mark, event, cand = make_fixture(side=side)
    last[12 * 60 - 1, 4] = 990.0 if side > 0 else 1010.0
    last[12 * 60 - 1, 2] = max(last[12 * 60 - 1, 2], last[12 * 60 - 1, 4])
    last[12 * 60 - 1, 3] = min(last[12 * 60 - 1, 3], last[12 * 60 - 1, 4])
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X2_COMPLETED_4H_TREND_AT_12H", 0.2
    )
    assert res["decision_12h"]["extend_to_18h"] is False
    assert res["decision_12h"]["signed_price_diff"] == -10.0
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR


def test_x2_exact_zero_return_exits_at_12h() -> None:
    last, mark, event, cand = make_fixture(side=1)
    # Intermediate hours 9 and 10 move, but hour 8 close == hour 11 close == 1000.0
    last[10 * 60 - 1, 4] = 1005.0
    last[10 * 60 - 1, 2] = 1005.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X2_COMPLETED_4H_TREND_AT_12H", 0.2
    )
    assert res["decision_12h"]["signed_price_diff"] == 0.0
    assert res["decision_12h"]["extend_to_18h"] is False
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR


def test_1159_bar_not_closed_before_115959999_is_excluded() -> None:
    last, _, _, _ = make_fixture(side=1)
    # At 11:59:00.000 (open of the 11:59 bar), the 11:00-11:59 hour is NOT yet closed
    clock_1159_open = BASE_START_MS + 11 * HOUR + 59 * MINUTE
    hours_at_1159 = extract_completed_1h_last_candles(last[:, :5], clock_1159_open)
    assert hours_at_1159[-1]["open_time"] == BASE_START_MS + 10 * HOUR
    # At 11:59:59.999 (exact close of the 11:59 bar), the 11:00-11:59 hour IS closed
    hours_at_1159_close = extract_completed_1h_last_candles(last[:, :5], clock_1159_open + MINUTE - 1)
    assert hours_at_1159_close[-1]["open_time"] == BASE_START_MS + 11 * HOUR


# -------------------------------------------------------------------------
# 5. Pre-12h Early Exits, Boundary STOP Precedence, and 12h->18h Collisions
# -------------------------------------------------------------------------


@pytest.mark.parametrize("scheme", ["X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H"])
def test_early_tp_before_12h_byte_identical_to_e0(scheme: str) -> None:
    last, mark, event, cand = make_fixture(side=1)
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    # Hit target at 5 hours after entry
    hit_idx = DEFAULT_ENTRY_OFFSET_MIN + 5 * 60
    last[hit_idx, 2] = proposal["target"] + 1.0
    res_cond = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, scheme, 0.2)
    res_e0 = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, "E0", 0.2)
    assert res_cond["exit_reason"] == "TARGET"
    assert res_cond["decision_12h"]["reached_12h_time_cap_boundary"] is False
    assert res_cond["exit_at"] == res_e0["exit_at"]
    assert res_cond["net_after_funding_usdt"] == res_e0["net_after_funding_usdt"]


@pytest.mark.parametrize("scheme", ["X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H"])
def test_early_stop_before_12h_byte_identical_to_e0(scheme: str) -> None:
    last, mark, event, cand = make_fixture(side=1)
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    hit_idx = DEFAULT_ENTRY_OFFSET_MIN + 3 * 60
    last[hit_idx, 3] = proposal["stop"] - 1.0
    res_cond = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, scheme, 0.2)
    res_e0 = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, "E0", 0.2)
    assert res_cond["exit_reason"] == "STOP"
    assert res_cond["decision_12h"]["reached_12h_time_cap_boundary"] is False
    assert res_cond["exit_at"] == res_e0["exit_at"]
    assert res_cond["net_after_funding_usdt"] == res_e0["net_after_funding_usdt"]


@pytest.mark.parametrize("scheme", ["X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H"])
def test_stop_in_final_minute_before_12h_prevents_conditional_selection(scheme: str) -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    # Make both X1 and X2 look favorable, but hit STOP in the final minute bar (idx_12h - 1) before 12h
    mark[idx_12h - 1, 1:5] = 1050.0
    last[12 * 60 - 1, 4] = 1020.0
    last[12 * 60 - 1, 2] = 1020.0
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    last[idx_12h - 1, 3] = proposal["stop"] - 0.5
    res = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, scheme, 0.2)
    assert res["exit_reason"] == "STOP"
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR - 1
    assert res["decision_12h"]["reached_12h_time_cap_boundary"] is False


@pytest.mark.parametrize("scheme", ["X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H"])
def test_stop_gap_on_12h_boundary_open_takes_precedence_over_conditional_cap(scheme: str) -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1050.0
    last[12 * 60 - 1, 4] = 1020.0
    last[12 * 60 - 1, 2] = 1020.0
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    # Bar opening at exact 12h boundary gaps below stop
    last[idx_12h, 1:5] = proposal["stop"] - 5.0
    res = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, scheme, 0.2)
    assert res["exit_reason"] == "STOP_GAP"
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR
    assert res["raw_exit"] == proposal["stop"] - 5.0
    assert res["decision_12h"]["reached_12h_time_cap_boundary"] is False


def test_stop_and_target_collision_at_12h_boundary_minute_when_extended() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1030.0
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    # When extended at idx_12h, if idx_12h has both low <= stop and high >= target, intrabar STOP wins
    last[idx_12h, 2] = proposal["target"] + 5.0
    last[idx_12h, 3] = proposal["stop"] - 1.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["decision_12h"]["extend_to_18h"] is True
    assert res["exit_reason"] == "STOP"
    assert res["exit_at"] == event["entry_at"] + 12 * HOUR + MINUTE - 1


def test_stop_and_target_collision_during_12h_to_18h_extension() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1030.0
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    idx_15h = DEFAULT_ENTRY_OFFSET_MIN + 15 * 60
    last[idx_15h, 2] = proposal["target"] + 2.0
    last[idx_15h, 3] = proposal["stop"] - 2.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["exit_reason"] == "STOP"
    assert res["raw_exit"] == proposal["stop"]
    assert res["exit_at"] == event["entry_at"] + 15 * HOUR + MINUTE - 1


def test_target_hit_during_12h_to_18h_extension_matches_h1() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1030.0
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    idx_16h = DEFAULT_ENTRY_OFFSET_MIN + 16 * 60
    last[idx_16h, 2] = proposal["target"] + 1.0
    res_x1 = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    res_h1 = execute_conditional_position(last[:, :5], mark, [], event, cand, STRESS, "H1", 0.2)
    assert res_x1["exit_reason"] == "TARGET"
    assert res_x1["exit_at"] == res_h1["exit_at"]
    assert res_x1["net_after_funding_usdt"] == res_h1["net_after_funding_usdt"]


def test_18h_time_cap_caps_favorable_open_at_target() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    idx_18h = DEFAULT_ENTRY_OFFSET_MIN + 18 * 60
    mark[idx_12h - 1, 1:5] = 1030.0
    proposal = _proposed(last[:, :5], event, cand, STRESS)
    last[idx_18h, 1:5] = proposal["target"] + 50.0
    res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
    )
    assert res["exit_reason"] == "TIME_CAP"
    assert res["exit_at"] == event["entry_at"] + 18 * HOUR
    assert res["raw_exit"] == proposal["target"]


# -------------------------------------------------------------------------
# 6. ACK Semantics, Funding De-dup, and Partial Tiers Conservation
# -------------------------------------------------------------------------


def test_ack_clock_open_vs_intrabar_fills() -> None:
    open_ts = 1_650_000_000_000
    bar_end_ts = open_ts + MINUTE - 1
    assert ack_clock(open_ts) == open_ts + MINUTE
    assert ack_clock(bar_end_ts) == open_ts + 2 * MINUTE


def test_duplicate_or_unsorted_funding_events_rejected() -> None:
    last, mark, event, cand = make_fixture(side=1)
    dup = [{"settlement_at": event["entry_at"] + HOUR, "rate": "0.001"}] * 2
    with pytest.raises(ValueError, match="Funding events must be strictly increasing"):
        execute_conditional_position(
            last[:, :5], mark, dup, event, cand, STRESS, "X1_NET_POSITIVE_AT_12H", 0.2
        )


def test_partial_tiers_conserve_quantity_cash_and_funding() -> None:
    last, mark, event, cand = make_fixture(side=1)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    mark[idx_12h - 1, 1:5] = 1030.0
    proposal = _proposed(last[:, :5], event, cand, BASE)
    tp1 = proposal["effective_entry"] + proposal["initial_risk"]
    # Hit TP1 at +2h, then reach 12h with remaining half and extend to 18h
    last[DEFAULT_ENTRY_OFFSET_MIN + 2 * 60, 2] = tp1 + 1.0
    funding = [{"settlement_at": event["entry_at"] + 6 * HOUR, "rate": "0.001"}]
    res = execute_conditional_position(
        last[:, :5],
        mark,
        funding,
        event,
        cand,
        BASE,
        "X1_NET_POSITIVE_AT_12H",
        0.2,
        partial_tp1_fraction=0.5,
    )
    assert len(res["tiers"]) == 2
    assert [t["quantity"] for t in res["tiers"]] == pytest.approx([0.1, 0.1])
    assert res["funding_settlements"][0]["quantity"] == "0.1"
    assert math.isclose(
        sum(j["cash_delta"] for j in res["journal"]),
        float(res["net_after_funding_usdt"]),
        abs_tol=1e-9,
    )


def test_partial_tier_below_min_notional_rejected() -> None:
    last, mark, event, cand = make_fixture(side=1)
    with pytest.raises(PartialIneligibleError):
        execute_conditional_position(
            last[:, :5],
            mark,
            [],
            event,
            cand,
            BASE,
            "X1_NET_POSITIVE_AT_12H",
            0.002,
            partial_tp1_fraction=0.5,
        )


# -------------------------------------------------------------------------
# 7. No Future Data After 12h & 50% Future Bar Mutation Invariance
# -------------------------------------------------------------------------


@pytest.mark.parametrize("scheme", ["X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H"])
def test_50_percent_future_bar_mutation_invariance_on_12h_decision(scheme: str) -> None:
    last, mark, event, cand = make_fixture(side=1, total_minutes=1600)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60  # index 766 out of 1600 (>52% of bars are >= idx_12h)
    mark[idx_12h - 1, 1:5] = 1025.0
    last[12 * 60 - 1, 4] = 1015.0
    last[12 * 60 - 1, 2] = 1015.0
    funding_base = [{"settlement_at": event["entry_at"] + 4 * HOUR, "rate": "0.0002"}]

    base_res = execute_conditional_position(
        last[:, :5], mark, funding_base, event, cand, STRESS, scheme, 0.2
    )

    # Mutate >50% of all bars (every bar from idx_12h through 1599 = 834/1600 bars = 52.1%)
    last_mut = last[:, :5].copy()
    mark_mut = mark.copy()
    last_mut[idx_12h:, 1:5] = 5000.0
    mark_mut[idx_12h:, 1:5] = 200.0
    funding_mut = [
        *funding_base,
        {"settlement_at": event["entry_at"] + 13 * HOUR, "rate": "0.50"},
    ]

    mut_res = execute_conditional_position(
        last_mut, mark_mut, funding_mut, event, cand, STRESS, scheme, 0.2
    )
    # The 12h decision object must be 100% identical despite massive post-12h mutation
    assert base_res["decision_12h"] == mut_res["decision_12h"]


@pytest.mark.parametrize("scheme", ["X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H"])
def test_when_exiting_at_12h_post_12h_bar_mutation_leaves_entire_trade_invariant(scheme: str) -> None:
    last, mark, event, cand = make_fixture(side=1, total_minutes=1600)
    idx_12h = DEFAULT_ENTRY_OFFSET_MIN + 12 * 60
    base_res = execute_conditional_position(
        last[:, :5], mark, [], event, cand, STRESS, scheme, 0.2
    )
    assert base_res["decision_12h"]["extend_to_18h"] is False

    # Mutate all bars strictly after idx_12h (833 bars > 50% of array)
    last_mut = last[:, :5].copy()
    mark_mut = mark.copy()
    last_mut[idx_12h + 1 :, 1:5] = 9999.0
    mark_mut[idx_12h :, 1:5] = 100.0
    mut_res = execute_conditional_position(
        last_mut, mark_mut, [], event, cand, STRESS, scheme, 0.2
    )
    assert base_res == mut_res


def test_standalone_e0_and_h1_match_original_exit_r1_book() -> None:
    last, mark, event, cand = make_fixture(side=-1)
    funding = [{"settlement_at": event["entry_at"] + 5 * HOUR, "rate": "-0.0005"}]
    for sch in ("E0", "H1"):
        ours = execute_conditional_position(last[:, :5], mark, funding, event, cand, STRESS, sch, 0.25)
        orig = original_exit_r1_position(last[:, :5], mark, funding, event, cand, STRESS, sch, 0.25)
        for k in (
            "entry_at",
            "exit_at",
            "exit_ack_at",
            "exit_reason",
            "raw_entry",
            "effective_entry",
            "raw_exit",
            "effective_exit",
            "net_after_funding_usdt",
            "net_after_funding_bps",
        ):
            assert ours[k] == orig[k]


def test_effective_price_decimal_matches_buy_and_sell_rounding() -> None:
    assert str(effective_price_decimal("1000.0", 1, STRESS, entry=True)) == "1001.0"
    assert str(effective_price_decimal("1000.0", 1, STRESS, entry=False)) == "999.0"
    assert str(effective_price_decimal("1000.0", -1, STRESS, entry=True)) == "999.0"
    assert str(effective_price_decimal("1000.0", -1, STRESS, entry=False)) == "1001.0"
