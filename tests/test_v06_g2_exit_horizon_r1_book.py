"""Synthetic, prospective witnesses for the local two-lead exit ledger."""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.strategy_research.g2_exit_horizon_r1.book import (
    PartialIneligible,
    _breakeven_stop,
    position,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    MINUTE,
    _proposed,
    episode,
)

ENTRY = 2 * MINUTE


def fixture(side: int = 1, n: int = 1500):
    bars = np.empty((n, 5), dtype=float)
    bars[:, 0] = np.arange(n) * MINUTE
    bars[:, 1:] = 100.0
    mark = bars.copy()
    event = {"event_time": 0, "decision_at": MINUTE, "entry_at": ENTRY,
             "decision_close": 100.0, "atr_hour": 20.0,
             "side": side, "stop": 90.0 if side > 0 else 110.0,
             "event_id": "synthetic"}
    cand = {"id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H", "horizon_hours": 12,
            "target_R": 2.0}
    return bars, mark, event, cand


def prices(bars, event, cand, side=1):
    p = _proposed(bars, event, cand, BASE)
    t1 = round(p["effective_entry"] + side * p["initial_risk"], 1)
    return p, t1, p["target"]


def run(bars, mark, event, cand, scheme="E1", *, quantity=0.2, funding=None, fill_mode="primary"):
    return position(bars, mark, funding or [], event, cand, BASE, scheme, quantity,
                    fill_mode=fill_mode)


def test_e0_legacy_trade_identity():
    bars, mark, event, cand = fixture()
    original = episode(bars, event, cand, BASE, quantity=0.2)
    result = run(bars, mark, event, cand, "E0")
    for key in ("exit_at", "exit_ack_at", "exit_reason", "raw_exit", "effective_exit",
                "gross_usdt", "net_usdt", "net_bps", "fee_entry", "fee_exit"):
        assert result[key] == pytest.approx(original[key]) if isinstance(original[key], float) else result[key] == original[key]


@pytest.mark.parametrize("scheme,hours", [("E0", 12), ("H1", 18), ("H2", 24)])
def test_horizon_only_moves_deadline(scheme, hours):
    bars, mark, event, cand = fixture()
    result = run(bars, mark, event, cand, scheme)
    assert result["exit_reason"] == "TIME_CAP"
    assert result["exit_at"] == ENTRY + hours * 3600_000
    assert result["raw_entry"] == 100


def test_partial_split_and_single_entry_fee():
    bars, mark, event, cand = fixture()
    p, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    result = run(bars, mark, event, cand)
    assert len(result["tiers"]) == 2
    assert [tier["quantity"] for tier in result["tiers"]] == pytest.approx([0.1, 0.1])
    assert len([j for j in result["journal"] if j["kind"] == "ENTRY_FEE"]) == 1
    assert result["fee_entry"] == pytest.approx(p["effective_entry"] * 0.2 * 6 / 10000)


@pytest.mark.parametrize("quantity", [0.001, 0.01, 0.2015])
def test_partial_ineligible_size(quantity):
    bars, mark, event, cand = fixture()
    with pytest.raises(PartialIneligible):
        run(bars, mark, event, cand, quantity=quantity)


@pytest.mark.parametrize("quantity", [0.018000000000000002, 0.027])
def test_inherited_float_lot_ulps_preserve_original_quantity(quantity):
    bars, mark, event, cand = fixture()
    bars[:, 1:] = 1000.0
    mark[:, 1:] = 1000.0
    event.update({"decision_close": 1000.0, "stop": 900.0, "atr_hour": 200.0})
    result = run(bars, mark, event, cand, quantity=quantity,
                 funding=[{"settlement_at": 8 * 3600_000, "rate": "0.001"}])
    assert sum(tier["quantity"] for tier in result["tiers"]) == pytest.approx(quantity)
    assert float(result["funding_settlements"][0]["quantity"]) == pytest.approx(quantity)


def test_stop_gap_before_time_cap():
    bars, mark, event, cand = fixture()
    deadline_idx = 2 + 12 * 60
    bars[deadline_idx, 1:5] = 89.0
    result = run(bars, mark, event, cand)
    assert result["exit_reason"] == "STOP_GAP"
    assert result["raw_exit"] == 89.0


def test_time_cap_before_favorable_target_gap():
    bars, mark, event, cand = fixture()
    _, _, t2 = prices(bars, event, cand)
    bars[2 + 12 * 60, 1:5] = t2 + 10
    result = run(bars, mark, event, cand)
    assert result["exit_reason"] == "TIME_CAP"
    assert result["raw_exit"] == t2


def test_intraminute_stop_before_both_targets():
    bars, mark, event, cand = fixture()
    p, _, t2 = prices(bars, event, cand)
    bars[3, 2] = t2 + 0.2
    bars[3, 3] = p["stop"] - 0.1
    result = run(bars, mark, event, cand)
    assert result["exit_reason"] == "STOP"
    assert len(result["tiers"]) == 1


def test_exact_tp_touch_does_not_fill():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1
    result = run(bars, mark, event, cand)
    assert result["touch_no_fill_count"] == 1
    assert all(tier["reason"] != "TP1" for tier in result["tiers"])


def test_one_tick_trade_through_fills_tp1():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    result = run(bars, mark, event, cand)
    assert result["tiers"][0]["reason"] == "TP1"
    assert result["tiers"][0]["raw_exit"] == t1


def test_favorable_open_through_both_capped():
    bars, mark, event, cand = fixture()
    _, _, t2 = prices(bars, event, cand)
    bars[3, 1:5] = t2 + 5
    result = run(bars, mark, event, cand)
    assert [x["reason"] for x in result["tiers"]] == ["TP1_GAP_CAPPED", "TP2_GAP_CAPPED"]
    assert len({x["exit_at"] for x in result["tiers"]}) == 1


def test_intrabar_tp1_tp2_cannot_both_fill():
    bars, mark, event, cand = fixture()
    _, _, t2 = prices(bars, event, cand)
    bars[3, 2] = t2 + 0.1
    result = run(bars, mark, event, cand)
    assert result["tiers"][0]["reason"] == "TP1"
    assert result["tiers"][1]["reason"] == "TIME_CAP"


def test_e2_breakeven_only_after_tp1_ack():
    bars, mark, event, cand = fixture()
    p, t1, _ = prices(bars, event, cand)
    be = _breakeven_stop(p, BASE)
    bars[3, 2] = t1 + 0.1
    bars[4, 1:5] = [be + 0.2, be + 0.2, be - 0.1, be + 0.2]
    bars[5, 1:5] = [be + 0.2, be + 0.2, be - 0.1, be + 0.2]
    result = run(bars, mark, event, cand, "E2")
    assert result["tiers"][0]["reason"] == "TP1"
    # TP1 at minute 3 close: ACK at minute 5, so minute 4 cannot amend.
    assert result["tiers"][1]["exit_at"] == 5 * MINUTE + MINUTE - 1
    assert result["tiers"][1]["raw_exit"] == be
    assert be >= p["stop"]


def test_short_breakeven_stop_never_widens():
    bars, _, event, cand = fixture(side=-1)
    p = _proposed(bars, event, cand, BASE)
    assert _breakeven_stop(p, BASE) <= p["stop"]


def test_signed_funding_on_partial_remaining_quantity():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    events = [{"settlement_at": 8 * 3600_000, "rate": "0.001"}]
    result = run(bars, mark, event, cand, funding=events)
    assert result["funding_settlements"][0]["quantity"] == "0.1"
    assert float(result["funding_cash_usdt"]) == pytest.approx(-0.01)
    assert result["funding_settlements"][0]["mark_close_at"] == 8 * 3600_000 - 1


@pytest.mark.parametrize("side,rate,positive_cash", [(1, "0.001", False), (-1, "0.001", True),
                                                      (1, "-0.001", True), (-1, "-0.001", False)])
def test_funding_sign(side, rate, positive_cash):
    bars, mark, event, cand = fixture(side=side)
    event_row = {"settlement_at": 8 * 3600_000, "rate": rate}
    result = run(bars, mark, event, cand, "E0", funding=[event_row])
    assert (float(result["funding_cash_usdt"]) > 0) is positive_cash
    assert result["funding_settlements"][0]["quantity"] == "0.2"


def test_funding_before_partial_uses_whole_quantity():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[9 * 60, 2] = t1 + 0.1
    result = run(bars, mark, event, cand,
                 funding=[{"settlement_at": 8 * 3600_000, "rate": "0.001"}])
    assert result["funding_settlements"][0]["quantity"] == "0.2"


def test_funding_after_flat_excluded():
    bars, mark, event, cand = fixture()
    p, _, _ = prices(bars, event, cand)
    bars[3, 3] = p["stop"] - 0.1
    result = run(bars, mark, event, cand, funding=[{"settlement_at": 8 * 3600_000, "rate": "0.01"}])
    assert result["funding_settlements"] == []
    assert result["funding_cash_usdt"] == "0"


def test_missing_completed_mark_at_settlement_fails():
    bars, mark, event, cand = fixture()
    mark = mark[mark[:, 0] != 8 * 3600_000 - MINUTE]
    with pytest.raises(ValueError, match="Mark"):
        run(bars, mark, event, cand, "E0",
            funding=[{"settlement_at": 8 * 3600_000, "rate": "0.001"}])


def test_duplicate_funding_clock_fails():
    bars, mark, event, cand = fixture()
    row = {"settlement_at": 8 * 3600_000, "rate": "0.001"}
    with pytest.raises(ValueError, match="Funding events"):
        run(bars, mark, event, cand, "E0", funding=[row, row])


def test_cash_journal_and_tiers_conserve():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    result = run(bars, mark, event, cand,
                 funding=[{"settlement_at": 8 * 3600_000, "rate": "0.001"}])
    assert sum(x["quantity"] for x in result["tiers"]) == pytest.approx(result["quantity"])
    assert sum(x["cash_delta"] for x in result["journal"]) == pytest.approx(
        result["net_usdt"] + float(result["funding_cash_usdt"]))
    assert [x["timestamp"] for x in result["journal"]] == sorted(x["timestamp"] for x in result["journal"])
    assert math.isclose(result["fee_exit"], sum(x["fee_exit"] for x in result["tiers"]))


def test_tp1_profit_not_available_until_ack():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    result = run(bars, mark, event, cand)
    tp1 = result["tiers"][0]
    j = [x for x in result["journal"] if x["kind"] == "EXIT_PNL_ACK"]
    assert j[0]["timestamp"] == tp1["exit_ack_at"]
    assert j[0]["timestamp"] > tp1["exit_at"]


def test_journal_inventory_at_later_ack_uses_actual_fill_state():
    bars, mark, event, cand = fixture()
    _, t1, t2 = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    bars[4, 1:5] = t2 + 0.2
    result = run(bars, mark, event, cand)
    first_ack = min((x for x in result["journal"] if x["kind"] == "EXIT_PNL_ACK"),
                    key=lambda x: x["timestamp"])
    assert first_ack["remaining_quantity"] == 0.0


def test_e0_strict_diagnostic_differs_from_legacy_touch():
    bars, mark, event, cand = fixture()
    _, _, t2 = prices(bars, event, cand)
    bars[3, 2] = t2
    legacy = run(bars, mark, event, cand, "E0")
    matched = run(bars, mark, event, cand, "E0", fill_mode="through")
    assert legacy["exit_reason"] == "TARGET"
    assert matched["exit_reason"] == "TIME_CAP"
    assert matched["touch_no_fill_count"] == 1


def test_one_bar_delay_diagnostic_waits_confirmation():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    bars[4, 1:5] = t1 + 0.2
    immediate = run(bars, mark, event, cand)
    delayed = run(bars, mark, event, cand, fill_mode="delay")
    assert immediate["tiers"][0]["exit_at"] == 4 * MINUTE - 1
    assert delayed["tiers"][0]["exit_at"] >= 4 * MINUTE


def test_unfilled_first_confirmation_waits_later_bar():
    bars, mark, event, cand = fixture()
    _, t1, _ = prices(bars, event, cand)
    bars[3, 2] = t1 + 0.1
    bars[4, 2] = t1 + 0.1
    result = run(bars, mark, event, cand, fill_mode="unfilled")
    assert result["tiers"][0]["exit_at"] == 5 * MINUTE - 1


@pytest.mark.parametrize("mode", ["delay", "unfilled"])
def test_opening_gap_sensitivity_does_not_bypass_pending_tp1(mode):
    bars, mark, event, cand = fixture()
    _, _, t2 = prices(bars, event, cand)
    bars[3, 1:5] = t2 + 1
    bars[4, 1:5] = t2 + 1
    result = run(bars, mark, event, cand, fill_mode=mode)
    assert result["tiers"][0]["exit_at"] >= 4 * MINUTE
    assert result["tiers"][0]["reason"].startswith("TP1")


def test_unknown_scheme_or_fill_mode_rejected():
    bars, mark, event, cand = fixture()
    with pytest.raises(ValueError, match="Unregistered"):
        run(bars, mark, event, cand, "D1")
    with pytest.raises(ValueError, match="Unregistered"):
        run(bars, mark, event, cand, fill_mode="magic")


def test_missing_last_minute_rejected():
    bars, mark, event, cand = fixture()
    bars = bars[bars[:, 0] != 5 * MINUTE]
    with pytest.raises(ValueError, match="Missing"):
        run(bars, mark, event, cand, "E1")
