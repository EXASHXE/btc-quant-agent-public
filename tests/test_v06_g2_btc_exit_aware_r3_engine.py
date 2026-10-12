"""Synthetic-only accounting, chronology and frozen-mechanism regressions."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.strategy_research.g2_btc_exit_aware_r3 import engine as e
from scripts.strategy_research.g2_btc_exit_aware_r3 import portfolio as p
from scripts.strategy_research.g2_btc_exit_aware_r3 import signals as s
from scripts.strategy_research.g2_btc_exit_aware_r3 import sources

BASE = e.Cost.from_dict({"fee_bps": 6, "spread_bps": 2, "slip_bps": 3})
ZERO = e.Cost.from_dict({"fee_bps": 0, "spread_bps": 0, "slip_bps": 0})


def rows(n=1500, price=10000):
    a = np.tile([0, price, price + 5, price - 5, price, 10.0], (n, 1))
    a[:, 0] = np.arange(n) * e.MINUTE
    return a


def event(side=1):
    return {
        "event_id": "SYNTHETIC_ONLY:entry",
        "event_time": 0,
        "decision_at": 60000,
        "entry_at": 120000,
        "side": side,
        "stop": 9970 if side == 1 else 10030,
        "decision_close": 10000,
        "atr_hour": 50,
    }


def witness(which):
    data = rows()
    ev = event(-1 if which == 5 else 1)
    q = Decimal(".128" if which == 4 else ".127")
    candles = {
        1: [[10000, 10010, 9960, 9990]],
        2: [
            [10000, 10050, 9995, 10010],
            [10010, 10080, 10005, 10020],
            [10020, 10120, 10015, 10030],
        ],
        3: [
            [10000, 10050, 9995, 10010],
            [10010, 10020, 10005, 10010],
            [10010, 10035, 10005, 10030],
            [10030, 10035, 9990, 10030],
        ],
        4: [[10000, 10060, 9995, 10010], [10010, 10120, 10005, 10020]],
        5: [[10000, 10010, 9950, 9990], [9990, 10000, 9920, 9980], [9980, 9990, 9890, 9970]],
    }
    for k, candle in enumerate(candles[which], 3):
        data[k, 1:5] = candle
    policy = "X0" if which == 1 else "X2" if which == 4 else "X1"
    hourly = [{"end_ms": 0, "available_at": 60000, "close": 10000, "atr": 10}] if which == 4 else []
    expected = {
        1: Decimal("-6.60171400"),
        2: Decimal("6.06198322"),
        3: Decimal("0.90048198"),
        4: Decimal("7.88477568"),
        5: Decimal("6.08532440"),
    }[which]
    result = e.episode(data, ev, policy, 8, BASE, q, hourly)
    source = {
        "label": "SYNTHETIC_ONLY",
        "event": ev,
        "candles": candles[which],
        "quantity": str(q),
        "policy": policy,
        "hourly": hourly,
    }
    return result, expected, source


@pytest.mark.parametrize(
    "case",
    [1, 2, 3, 4, 5],
    ids=[
        "long_stop",
        "long_three_targets",
        "protected_stop",
        "half_then_cap",
        "short_three_targets",
    ],
)
def test_independent_hand_decimal(case):
    result, expected, source = witness(case)
    assert result["net_usdt"] == expected
    independent_entry_fee = (
        result["entry"]["effective_price"] * result["initial_quantity"] * Decimal("0.0006")
    ).quantize(e.CASH)
    independently_summed = -independent_entry_fee
    for leg in result["legs"]:
        adjusted = leg["raw_price"] * (1 - result["side"] * Decimal("0.0005"))
        effective = (adjusted / Decimal(".1")).to_integral_value(
            rounding="ROUND_FLOOR" if result["side"] == 1 else "ROUND_CEILING"
        ) * Decimal(".1")
        fee = (effective * leg["quantity"] * Decimal(".0006")).quantize(e.CASH)
        independently_summed += (
            result["side"] * (effective - result["entry"]["effective_price"]) * leg["quantity"]
        ).quantize(e.CASH) - fee
        assert effective == leg["effective_price"] and fee == leg["fee"]
    assert independently_summed == expected
    assert sum(x["quantity"] for x in result["legs"]) == result["initial_quantity"]
    assert source["label"] == "SYNTHETIC_ONLY"


def test_X0_full_target():
    a = rows()
    a[3, 2] = 10080
    r = e.episode(a, event(), "X0", 8, BASE, ".127")
    assert len(r["legs"]) == 1 and r["legs"][0]["raw_price"] == 10075 and r["exit_reason"] == "TP1"


def test_X1_actual_lot_residual():
    r, _, _ = witness(2)
    assert [x["quantity"] for x in r["legs"]] == [Decimal(".050"), Decimal(".038"), Decimal(".039")]


def test_X2_half_actual_quantity():
    r, _, _ = witness(4)
    assert [x["quantity"] for x in r["legs"]] == [Decimal(".064"), Decimal(".064")]


def test_break_even_includes_remaining_costs():
    entry = e.make_entry(rows(), event(), 8, BASE, Decimal(".127"))
    raw = e.break_even(entry, BASE)
    eff = BASE.effective(raw, 1, False)
    assert raw > entry.raw_price
    assert (eff - entry.effective_price) * Decimal(".077") - BASE.fee(
        eff, Decimal(".077")
    ) - BASE.fee(entry.effective_price, Decimal(".077")) >= 0


def test_TP1_ACK_then_next_minute_stop():
    r, _, _ = witness(3)
    assert r["legs"][0]["fill_at"] == 239999
    assert r["legs"][0]["ack_at"] == 300000
    assert r["stop_updates"][0]["active_at"] == 360000
    assert r["legs"][-1]["effective_at"] == 360000


def test_no_pre_TP1_break_even_stop():
    a = rows()
    a[3, 1:5] = [10000, 10020, 9980, 10010]
    a[4, 1:5] = [10010, 10050, 9960, 9970]
    r = e.episode(a, event(), "X1", 8, BASE, ".127")
    assert r["exit_reason"] == "STOP" and len(r["legs"]) == 1 and not r["stop_updates"]


def test_hourly_ATR_premature_rejected():
    with pytest.raises(ValueError, match="AVAILABLE_BEFORE"):
        e.episode(
            rows(),
            event(),
            "X2",
            8,
            BASE,
            ".128",
            [{"end_ms": 3600000, "available_at": 3600000, "close": 10000, "atr": 10}],
        )


def test_hourly_ATR_unclosed_grid_rejected():
    with pytest.raises(ValueError, match="AVAILABLE_BEFORE"):
        e.episode(
            rows(),
            event(),
            "X2",
            8,
            BASE,
            ".128",
            [{"end_ms": 3599999, "available_at": 3660000, "close": 10000, "atr": 10}],
        )


def test_missing_ATR_retains_original_stop():
    a = rows()
    a[3, 2] = 10060
    a[6, 3] = 9960
    r = e.episode(a, event(), "X2", 8, BASE, ".128")
    assert r["legs"][-1]["raw_price"] == 9970 and not r["stop_updates"]


@pytest.mark.parametrize("side", [1, -1])
def test_pending_stops_never_loosen(side):
    entry = e.make_entry(rows(), event(side), 8, BASE, Decimal(".127"))
    state = e.PositionState(entry, entry.initial_quantity, entry.initial_stop)
    state.queue_stop(Decimal(9990 if side == 1 else 10010), 180000)
    state.queue_stop(Decimal(9980 if side == 1 else 10020), 180000)
    assert state.pending_stop == Decimal(9990 if side == 1 else 10010)
    assert state.pending_at == 240000


def test_adverse_gap_worse_than_stop():
    a = rows()
    a[3, 1:5] = [9950, 9980, 9940, 9960]
    r = e.episode(a, event(), "X0", 8, BASE, ".127")
    assert r["exit_reason"] == "STOP_GAP" and r["legs"][0]["raw_price"] == 9950


def test_favorable_gap_is_capped():
    a = rows()
    a[3, 1:5] = [10200, 10210, 10190, 10200]
    r = e.episode(a, event(), "X0", 8, BASE, ".127")
    assert r["legs"][0]["raw_price"] == 10075 and r["exit_at"] == 180000


def test_stop_first_same_bar_collision():
    a = rows()
    a[3, 2:4] = [10200, 9950]
    r = e.episode(a, event(), "X1", 8, BASE, ".127")
    assert len(r["legs"]) == 1 and r["exit_reason"] == "STOP"
    assert r["minute_path_status"] == "MINUTE_PATH_UNKNOWN" and r["collision_minutes"] == 1


@pytest.mark.parametrize("cap", [18, 24])
def test_explicit_maximum_cap(cap):
    r = e.episode(rows(1500), event(), "X0", cap, BASE, ".127")
    assert r["exit_reason"] == "TIME_CAP" and r["exit_at"] == 120000 + cap * e.HOUR


def test_unfrozen_horizon_rejects():
    with pytest.raises(ValueError, match="UNFROZEN_CAP"):
        e.episode(rows(), event(), "X0", 12, BASE, ".127")


def test_partial_lot_dust_rejects_before_fee():
    with pytest.raises(ValueError, match="PARTIAL_LOT_INELIGIBLE"):
        e.episode(rows(), event(), "X1", 8, BASE, ".001")


def test_duplicate_fill_rejects_mutation():
    r, _, _ = witness(2)
    entry = e.make_entry(rows(), event(), 8, BASE, Decimal(".127"))
    state = e.PositionState(entry, entry.initial_quantity, entry.initial_stop)
    leg = e.ExitLeg(**r["legs"][0])
    state.record(leg)
    with pytest.raises(ValueError, match="DUPLICATE_FILL"):
        state.record(leg)
    assert state.remaining == Decimal(".077")


def test_overfill_rejects():
    r, _, _ = witness(2)
    entry = e.make_entry(rows(), event(), 8, BASE, Decimal(".127"))
    state = e.PositionState(entry, entry.initial_quantity, entry.initial_stop)
    leg = {**r["legs"][0], "quantity": Decimal(".128")}
    with pytest.raises(ValueError, match="QUANTITY"):
        state.record(e.ExitLeg(**leg))


@pytest.mark.parametrize("qty", ["0", "-.01", ".1275"])
def test_invalid_entry_quantities(qty):
    with pytest.raises(ValueError, match="QUANTITY"):
        e.make_entry(rows(), event(), 8, BASE, e.dec(qty))


def test_invalid_position_direction():
    ev = event()
    ev["side"] = 0
    with pytest.raises(ValueError, match="SIDE"):
        e.make_entry(rows(), ev, 8, BASE, Decimal(".127"))


@pytest.mark.parametrize(
    "mutation",
    [{"decision_at": 0}, {"decision_at": 120000, "entry_at": 180000}, {"entry_at": 180000}],
)
def test_exact_frozen_clock_tuple(mutation):
    with pytest.raises(ValueError, match="KNOWN_AT"):
        e.make_entry(rows(), {**event(), **mutation}, 8, BASE, Decimal(".127"))


@pytest.mark.parametrize("bad", ["gap", "duplicate"])
def test_minute_continuity_fail_closed(bad):
    a = rows()
    a[10, 0] += 60000 if bad == "gap" else -60000
    with pytest.raises(ValueError, match="GAP_OR_DUPLICATE"):
        e.episode(a, event(), "X0", 8, BASE, ".127")


def feature_fixture(group="B", short=False):
    n = 26
    q = {"end_ms": 240 * e.HOUR + np.arange(n) * 15 * e.MINUTE}
    for name, value in [
        ("open", 99.9),
        ("high", 100.1),
        ("low", 99.8),
        ("close", 100),
        ("volume", 100),
        ("imbalance", 0),
    ]:
        q[name] = np.full(n, float(value))
    if group == "B":
        for k, vals in [
            (20, [100.1, 100.6, 100.0, 100.5, 120, 0.2]),
            (21, [100.4, 100.5, 100.1, 100.2, 100, 0]),
            (22, [100.3, 100.9, 100.2, 100.8, 110, 0.2]),
        ]:
            for key, val in zip(["open", "high", "low", "close", "volume", "imbalance"], vals):
                q[key][k] = val
    else:
        for k, vals in [
            (20, [99.9, 100.0, 99.7, 99.75, 130, -0.25]),
            (21, [99.8, 100.0, 99.8, 99.95, 100, 0.2]),
        ]:
            for key, val in zip(["open", "high", "low", "close", "volume", "imbalance"], vals):
                q[key][k] = val
    h = {
        "end_ms": np.arange(1, 247) * e.HOUR,
        "close": np.full(246, 110.0),
        "imbalance": np.full(246, 0.1),
    }
    f = {
        "end_ms": np.arange(1, 61) * 4 * e.HOUR,
        "close": np.full(60, 110.0 if group == "B" else 100.0),
    }
    aq = np.full(n, 0.5)
    ah = np.full(246, 1.0)
    af = np.full(60, 1.0)
    e20 = 99 + np.arange(60) * 0.01 if group == "B" else np.full(60, 100.0)
    e50 = np.full(60, 90.0)
    er = np.full(60, 0.3 if group == "B" else 0.2)
    eh = 99 + np.arange(246) * 0.01
    if short:
        for bar in [q, h, f]:
            for key in ["open", "close"]:
                if key in bar:
                    bar[key] = 200 - bar[key]
            if "high" in bar:
                bar["high"], bar["low"] = 200 - bar["low"], 200 - bar["high"]
            if "imbalance" in bar:
                bar["imbalance"] = -bar["imbalance"]
        e20, e50, eh = 200 - e20, 200 - e50, 200 - eh
    return q, h, f, aq, ah, af, e20, e50, er, eh


@pytest.mark.parametrize("group,short", [("B", False), ("B", True), ("C", False), ("C", True)])
def test_new_closed_bar_mechanisms(group, short):
    values = feature_fixture(group, short)
    result = s.scan_new(*values)[group]
    assert len(result) == 1 and result[0]["side"] == (-1 if short else 1)
    assert result[0]["decision_at"] == result[0]["event_time"] + 60000


def test_B_distinct_retest_then_confirmation():
    values = feature_fixture("B")
    q = values[0]
    q["close"][21] = 100.8
    q["high"][21] = 100.9
    q["imbalance"][21] = 0.2
    result = s.scan_new(*values)["B"]
    assert not result  # Retest bar itself cannot simultaneously confirm.


def test_B_setup_expires_after_four_bars():
    values = feature_fixture("B")
    q = values[0]
    q["close"][22] = 100.2
    q["open"][22] = 100.2
    q["close"][25] = 100.8
    q["high"][25] = 101.0
    q["imbalance"][25] = 0.3
    q["volume"][25] = 120
    assert not s.scan_new(*values)["B"]


def test_C_confirmation_exact_next_bar():
    values = feature_fixture("C")
    q = values[0]
    q["imbalance"][21] = -0.2
    q["close"][21] = 99.75
    q["low"][21] = 99.7
    q["open"][21] = 99.8
    assert not s.scan_new(*values)["C"]


def test_missing_flow_cannot_signal():
    values = feature_fixture("C")
    values[0]["imbalance"][21] = np.nan
    assert not s.scan_new(*values)["C"]


def test_future_mutation_preserves_earlier_nonempty_signal():
    values = feature_fixture("B")
    before = s.scan_new(*values)["B"]
    assert before
    for key in ["open", "close", "high", "low"]:
        values[0][key][23:] += 50
    after = s.scan_new(*values)["B"]
    assert before == [x for x in after if x["event_time"] <= before[0]["event_time"]]


def test_future_mutation_preserves_earlier_exit_legs():
    r, _, _ = witness(2)
    a = rows()
    a[3, 1:5] = [10000, 10050, 9995, 10010]
    a[4, 1:5] = [10010, 10080, 10005, 10020]
    a[100:, 1:5] += 500
    changed = e.episode(a, event(), "X1", 8, BASE, ".127")
    assert r["legs"][:2] == changed["legs"][:2]


def test_month_common_cutoff_and_no_cross_fold():
    a = rows(1600)
    fold = {"id": "SYNTHETIC2021-02", "year": 2021, "start_ms": 0, "end_ms": 24 * e.HOUR}
    result = p.month(
        a,
        [event()],
        {"id": "A_X0_H08", "exit": "X0", "cap_hours": 8},
        fold,
        {"fee_bps": 6, "spread_bps": 2, "slip_bps": 3},
        [],
    )
    assert not result["trades"] and result["waits"]["COMMON_24H_PLUS_ACK_FOLD_CUTOFF"] == 1


def test_monthly_accounts_reset_without_cumulative_ROI():
    a = rows(3000)
    fold = {"id": "SYNTHETIC2021-02", "year": 2021, "start_ms": 0, "end_ms": 48 * e.HOUR}
    args = (
        a,
        [],
        {"id": "A_X0_H08", "exit": "X0", "cap_hours": 8},
        fold,
        {"fee_bps": 6, "spread_bps": 2, "slip_bps": 3},
        [],
    )
    one = p.month(*args)
    two = p.month(*args)
    assert one["ending_equity"] == two["ending_equity"] == 1000
    assert one["month_return_pct"] == 0 and one["sum_nominal_books_not_single_account_ROI"]


def test_missing_cost_never_default_zero():
    with pytest.raises(ValueError, match="COST_UNAVAILABLE"):
        e.Cost.from_dict({"spread_bps": 2, "slip_bps": 3})


def test_negative_fee_rejected():
    with pytest.raises(ValueError, match="NEGATIVE_COST"):
        e.Cost.from_dict({"fee_bps": -1, "spread_bps": 2, "slip_bps": 3})


def test_fee_double_charges_actual_legs_once():
    a = rows()
    a[3, 2] = 10200
    ev = event()
    c1 = e.Cost.from_dict({"fee_bps": 6, "spread_bps": 0, "slip_bps": 0})
    c2 = e.Cost.from_dict({"fee_bps": 12, "spread_bps": 0, "slip_bps": 0})
    r1 = e.episode(a, ev, "X1", 8, c1, ".127")
    r2 = e.episode(a, ev, "X1", 8, c2, ".127")
    assert r2["fee_usdt"] == 2 * r1["fee_usdt"]
    assert r1["entry"]["fee"] == Decimal(".76200000")


def test_nonfinite_price_rejects():
    a = rows()
    a[3, 2] = np.inf
    with pytest.raises(ValueError, match="PRICE_ARRAY_INVALID"):
        e.episode(a, event(), "X0", 8, BASE, ".127")


def test_missing_cap_data_reports_incomplete():
    with pytest.raises(ValueError, match="INCOMPLETE_FILLS"):
        e.episode(rows(50), event(), "X0", 8, BASE, ".127")


def test_reserved_period_rejected_before_any_stat(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("metadata touched")

    monkeypatch.setattr(Path, "stat", forbidden)
    with pytest.raises(ValueError, match="RESERVED"):
        sources.authorize(2024, 2)


def test_engine_needs_no_network_or_account_reads(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden I/O")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    r, expected, _ = witness(2)
    assert r["net_usdt"] == expected


def test_unknown_funding_cannot_be_realized_net():
    r, _, _ = witness(2)
    assert r["real_funding"] == "UNKNOWN" and r["pnl_grade"] == "NET_EX_FUNDING_PROXY"


def test_funding_sensitivity_uses_remaining_quantity():
    r, _, _ = witness(2)
    r["entry_at"] = 8 * e.HOUR - 2 * e.MINUTE
    r["exit_at"] = 8 * e.HOUR + e.MINUTE
    r["legs"][0]["fill_at"] = 8 * e.HOUR - 60000
    r["legs"][1]["fill_at"] = 8 * e.HOUR + 100
    r["legs"][2]["fill_at"] = 8 * e.HOUR + 60000
    f = p.funding_sensitivity(rows(1500), r)["UTC8H_PLUS_MINUS_15S"]
    assert f["possible_windows"] == 1
    assert Decimal(f["adverse_usdt"]["8"]) == Decimal(".077") * Decimal(10005) * Decimal(".0008")


def test_zero_cost_long_short_symmetry():
    long = rows()
    long[3, 2] = 10070
    short = long.copy()
    short[:, 1] = 20000 - long[:, 1]
    short[:, 4] = 20000 - long[:, 4]
    short[:, 2] = 20000 - long[:, 3]
    short[:, 3] = 20000 - long[:, 2]
    a = e.episode(long, event(), "X0", 8, ZERO, ".127")
    b = e.episode(short, event(-1), "X0", 8, ZERO, ".127")
    assert a["net_usdt"] == b["net_usdt"] == Decimal("7.62000000")


def test_short_stop_leaves_no_residual_risk():
    a = rows()
    a[3, 2] = 10050
    r = e.episode(a, event(-1), "X1", 8, BASE, ".127")
    assert r["legs"][-1]["remaining"] == 0 and sum(x["quantity"] for x in r["legs"]) == Decimal(
        ".127"
    )


def test_A_returns_exact_R2_event_dictionary(monkeypatch):
    original = [
        {"event_id": "FLOW_CONFIRMED_TREND:1:900000", "stop": 9970, "event_time": 900000, "side": 1}
    ]
    monkeypatch.setattr(
        s, "r2_generate", lambda data, roster: {"FLOW_CONFIRMED_TREND_08H": original}
    )
    monkeypatch.setattr(s, "features", lambda data: feature_fixture("B"))
    r = s.generate(rows(), {})
    assert r["A"] is original and r["A"][0] == original[0]


def test_year_week_blocks_do_not_treat_minutes_as_trades():
    from datetime import UTC, datetime

    from scripts.strategy_research.g2_btc_exit_aware_r3.metrics import block_uncertainty

    folds = []
    trades = []
    for year in (2021, 2022, 2023):
        start = int(datetime(year, 2, 2, tzinfo=UTC).timestamp() * 1000)
        end = start + 26 * 24 * e.HOUR
        folds.append({"year": year, "start_ms": start, "end_ms": end})
        trades.append({"year": year, "entry_at": start, "net_bps": 10})
    result = block_uncertainty(trades, folds)
    assert result["represented_years"] == [2021, 2022, 2023] and result["observed"] == 10
    assert result["undefined_resamples"] > 0 and result["zero_trade_blocks_included"]


def test_empty_support_is_undefined_not_zero_profit():
    from scripts.strategy_research.g2_btc_exit_aware_r3.metrics import describe

    r = describe([])
    assert r["completed_trades"] == 0 and r["mean_net_bps"] is None and r["profit_factor"] is None


def test_source_checksum_mismatch_is_rejected():
    from scripts.strategy_research.g2_btc_empirical_fast_r1.sources import validate_zip_checksum

    with pytest.raises(ValueError):
        validate_zip_checksum(
            b"SYNTHETIC_ONLY", "0" * 64 + "  BTCUSDT-1m-2021-01.zip", "BTCUSDT-1m-2021-01.zip"
        )
