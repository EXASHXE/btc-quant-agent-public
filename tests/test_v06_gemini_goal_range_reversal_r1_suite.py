"""Scoped unit test suite (>=12 tests) for Gemini Goal-B range/reversal/vol discovery."""
from __future__ import annotations

import copy
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_empirical_fast_r1 import (
    replay as r1_replay,
    signals as r1_signals,
)
from scripts.strategy_research.g2_btc_empirical_fast_r1.sources import FIELDS, ms
from scripts.strategy_research.g2_gemini_goal_range_reversal_r1 import (
    audit,
    metrics,
    replay,
    signals,
    sources,
)

MINUTE = replay.MINUTE
BASE = replay.BASE
STRESS = replay.STRESS


def make_bars(count: int = 600, price: float = 1000.0) -> np.ndarray:
    a = np.empty((count, 7), dtype=np.float64)
    a[:, 0] = np.arange(count) * MINUTE
    a[:, 1:5] = price
    a[:, 5] = 10.0
    a[:, 6] = 5.0
    return a


def make_event(
    entry_minute: int = 3,
    side: int = 1,
    stop: float | None = None,
    target_r: float = 2.0,
) -> dict:
    return {
        "event_time": (entry_minute - 2) * MINUTE,
        "decision_at": (entry_minute - 1) * MINUTE,
        "entry_at": entry_minute * MINUTE,
        "decision_close": 1000.0,
        "atr_hour": 100.0,
        "stop": (980.0 if side > 0 else 1020.0) if stop is None else stop,
        "target_r": target_r,
        "side": side,
        "event_id": f"ev_{entry_minute}_{side}",
        "trend_bar_end": 0,
        "regime_vol_bps": 80.0,
    }


CAND = {
    "id": "W1_C01_FAILED_ACCEPTANCE_REENTRY_04H",
    "candidate_id": "W1_C01_FAILED_ACCEPTANCE_REENTRY_04H",
    "family": "FAILED_ACCEPTANCE_REENTRY",
    "horizon_hours": 4,
    "cooldown_hours": 1,
    "target_r": 2.0,
}
FOLD = {"id": "2021-02", "year": 2021, "month": 2, "start_ms": 3 * MINUTE, "end_ms": 550 * MINUTE}


def test_01_no_lookahead_decision_and_next_open_fill() -> None:
    d = make_bars()
    ev = make_event()
    t = replay.episode(d, ev, CAND, BASE)
    assert t["entry_at"] == 3 * MINUTE
    bad_entry = dict(ev, entry_at=ev["decision_at"])
    with pytest.raises(ValueError, match="delay"):
        replay.episode(d, bad_entry, CAND, BASE)
    bad_dec = dict(ev, decision_at=ev["event_time"])
    with pytest.raises(ValueError, match="availability"):
        replay.episode(d, bad_dec, CAND, BASE)


def test_02_future_bar_mutation_does_not_alter_earlier_signals() -> None:
    rng = np.random.default_rng(42)
    n_min = 65 * 240  # >60 4h bars
    d1 = np.empty((n_min, 7), dtype=np.float64)
    d1[:, 0] = np.arange(n_min) * MINUTE
    closes = 20000.0 + np.cumsum(rng.normal(0, 15, size=n_min))
    opens = np.r_[20000.0, closes[:-1]]
    highs = np.maximum(opens, closes) + rng.uniform(1, 20, size=n_min)
    lows = np.minimum(opens, closes) - rng.uniform(1, 20, size=n_min)
    vols = rng.uniform(10, 100, size=n_min)
    tb_vols = vols * rng.uniform(0.2, 0.8, size=n_min)
    d1[:, 1], d1[:, 2], d1[:, 3], d1[:, 4], d1[:, 5], d1[:, 6] = (
        opens,
        highs,
        lows,
        closes,
        vols,
        tb_vols,
    )
    reg = {
        "candidates": [
            {
                "candidate_id": "W1_C01_FAILED_ACCEPTANCE_REENTRY_04H",
                "family": "FAILED_ACCEPTANCE_REENTRY",
                "side": "BOTH",
                "horizon_hours": 4,
            },
            {
                "candidate_id": "W1_C03_VOL_COMPRESSION_TO_REVERT_08H",
                "family": "VOL_COMPRESSION_TO_REVERT",
                "side": "BOTH",
                "horizon_hours": 8,
            },
        ]
    }
    cutoff_idx = 62 * 240
    cutoff_ms = int(d1[cutoff_idx, 0])
    d2 = d1.copy()
    # Mutate all bars strictly after cutoff_idx
    d2[cutoff_idx + 1 :, 1:5] *= 1.25
    d2[cutoff_idx + 1 :, 6] = d2[cutoff_idx + 1 :, 5] * 0.95

    s1 = signals.generate_wave_signals(d1, reg)
    s2 = signals.generate_wave_signals(d2, reg)
    for cid in s1:
        ev1 = [e for e in s1[cid] if e["event_time"] <= cutoff_ms]
        ev2 = [e for e in s2[cid] if e["event_time"] <= cutoff_ms]
        assert ev1 == ev2


def test_03_fee_applied_once_per_leg_and_stress_more_adverse() -> None:
    d = make_bars()
    d[4, 1:4] = [1100.0, 1100.0, 1100.0]
    base_t = replay.episode(d, make_event(), CAND, BASE, quantity=2.0)
    stress_t = replay.episode(d, make_event(), CAND, STRESS, quantity=2.0)
    assert base_t["fee_usdt"] == pytest.approx(
        2.0 * (base_t["effective_entry"] + base_t["effective_exit"]) * 6.0 / 10_000.0
    )
    assert base_t["net_usdt"] == pytest.approx(
        base_t["gross_usdt"] - base_t["fee_usdt"] - base_t["execution_drag_usdt"]
    )
    assert stress_t["net_usdt"] < base_t["net_usdt"]


def test_04_same_bar_stop_wins_collision_over_target() -> None:
    d = make_bars()
    d[3, 2] = 1100.0
    d[3, 3] = 900.0
    t = replay.episode(d, make_event(), CAND, BASE)
    assert t["exit_reason"] == "STOP"
    assert t["raw_exit"] == 980.0
    assert t["exit_at"] == 4 * MINUTE - 1


def test_05_adverse_open_gap_uses_worse_open_and_favorable_gap_capped() -> None:
    d = make_bars()
    d[4, 1:4] = [965.0, 965.0, 965.0]
    down = replay.episode(d, make_event(), CAND, BASE)
    assert down["exit_reason"] == "STOP_GAP" and down["raw_exit"] == 965.0
    assert down["net_r"] < -1.0  # Loss can exceed 1R on adverse gap

    d2 = make_bars()
    d2[4, 1:4] = [1100.0, 1100.0, 1100.0]
    up = replay.episode(d2, make_event(), CAND, BASE)
    assert up["exit_reason"] == "TARGET_GAP_CAPPED"
    assert up["raw_exit"] == up["target"] < 1100.0


def test_06_expiry_open_adverse_gap_precedes_time_cap() -> None:
    d = make_bars()
    expiry = 3 + 240
    d[expiry, 1:4] = [970.0, 970.0, 970.0]
    t = replay.episode(d, make_event(), CAND, BASE)
    assert t["exit_at"] == expiry * MINUTE
    assert t["exit_reason"] == "STOP_GAP"
    assert t["raw_exit"] == 970.0


def test_07_monthly_window_24h_edge_isolation_and_no_cross_month_hold() -> None:
    manifest = {
        "records": [
            {"year": 2021, "month": 1, "status": "VERIFIED_COMPLETE_PUBLIC_MONTH"},
            {"year": 2021, "month": 2, "status": "VERIFIED_COMPLETE_PUBLIC_MONTH"},
        ]
    }
    folds = sources.build_monthly_scoring_folds(manifest)
    assert len(folds) == 1
    f = folds[0]
    assert f["id"] == "2021-02"
    assert f["start_ms"] == f["month_start_ms"] + 24 * 3_600_000
    assert f["end_ms"] == f["month_end_ms"] - 24 * 3_600_000

    d = make_bars()
    tail_ev = make_event(350)  # 350 + 240 = 590 > 550
    res = replay.simulate_fold(d, [tail_ev], CAND, FOLD, BASE)
    assert not res["trades"]
    assert res["waits"]["PURGED_FOLD_EDGE"] == 1


def test_08_continuous_1x_account_no_artificial_dd_truncation_and_exact_mtm() -> None:
    d = make_bars(900)
    # First trade loses >12% on gap, second trade at minute 400 still executes when enable_drawdown_kill=False
    d[4, 1:4] = [850.0, 850.0, 850.0]
    d[401, 1:4] = [1050.0, 1050.0, 1050.0]
    ev1 = make_event(3, side=1, stop=980.0)
    ev2 = make_event(400, side=1, stop=980.0)
    fold = {"id": "2021-02", "year": 2021, "month": 2, "start_ms": 3 * MINUTE, "end_ms": 850 * MINUTE}

    res_no_kill = replay.simulate_fold(d, [ev1, ev2], CAND, fold, BASE, enable_drawdown_kill=False)
    assert len(res_no_kill["trades"]) == 2
    assert not res_no_kill["disabled"]
    dd = metrics.drawdown(np.r_[1000.0, res_no_kill["curve"]])
    assert dd > 12.0  # True drawdown (>12%) is observed without artificial 10% truncation!

    # Also verify exact match with R1 minute-by-minute simulate on normal trade
    d_norm = make_bars(600)
    d_norm[4, 1:4] = [1060.0, 1060.0, 1060.0]
    r_fast = replay.simulate_fold(d_norm, [make_event()], CAND, FOLD, BASE)
    r_ref = r1_replay.simulate(d_norm[:, :6], [make_event()], CAND, FOLD, BASE)
    np.testing.assert_allclose(r_fast["curve"], r_ref["curve"])
    assert r_fast["ending_equity"] == pytest.approx(r_ref["ending_equity"])


def test_09_deterministic_repeatability_and_wait_ledger() -> None:
    d = make_bars()
    d[4, 1:4] = [1060.0, 1060.0, 1060.0]
    evs = [make_event(3), make_event(5), make_event(520)]
    r1 = replay.simulate_fold(d, evs, CAND, FOLD, BASE)
    r2 = replay.simulate_fold(d, copy.deepcopy(evs), CAND, FOLD, BASE)
    np.testing.assert_array_equal(r1["curve"], r2["curve"])
    assert r1["trades"] == r2["trades"]
    assert r1["event_log"] == r2["event_log"]
    assert [e["result"] for e in r1["event_log"]] == [
        "FILLED",
        "POSITION_ACK_OR_COOLDOWN",
        "PURGED_FOLD_EDGE",
    ]


def test_10_source_validator_detects_timestamp_units_and_rejects_2024_2026() -> None:
    expected = ms("2021-01-01T00:00:00Z")
    assert sources.detect_timestamp_unit(expected, expected)[1] == "MILLISECONDS_DETECTED"
    assert (
        sources.detect_timestamp_unit(expected * 1000, expected)[1]
        == "MICROSECONDS_DETECTED_CONVERTED_TO_MS"
    )
    assert (
        sources.detect_timestamp_unit(expected // 1000, expected)[1]
        == "SECONDS_DETECTED_CONVERTED_TO_MS"
    )
    with pytest.raises(ValueError, match="Forbidden year"):
        sources.parse_month_with_taker(b"", 2024, 1)
    with pytest.raises(ValueError, match="Forbidden year"):
        sources.fetch_with_timing(
            "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip",
            Path("/tmp/never.zip"),
        )


def test_11_fast_indicators_match_r1_reference_exactly() -> None:
    rng = np.random.default_rng(7)
    n_min = 4800
    d = np.empty((n_min, 7), dtype=np.float64)
    d[:, 0] = np.arange(n_min) * MINUTE
    c = 30000.0 + np.cumsum(rng.normal(0, 10, size=n_min))
    o = np.r_[30000.0, c[:-1]]
    h = np.maximum(o, c) + rng.uniform(1, 15, size=n_min)
    l = np.minimum(o, c) - rng.uniform(1, 15, size=n_min)
    v = rng.uniform(5, 50, size=n_min)
    d[:, 1], d[:, 2], d[:, 3], d[:, 4], d[:, 5], d[:, 6] = o, h, l, c, v, 0.6 * v

    agg_fast = signals.aggregate_with_taker(d, 15)
    agg_ref = r1_signals.aggregate(d[:, :6], 15)
    for k in ("end_ms", "open", "high", "low", "close", "volume"):
        np.testing.assert_allclose(agg_fast[k], agg_ref[k])

    np.testing.assert_allclose(
        signals._atr_fast(agg_fast, 20), r1_signals._atr(agg_ref, 20), equal_nan=True
    )
    np.testing.assert_allclose(
        signals._er_fast(agg_fast["close"], 12),
        r1_signals._er(agg_ref["close"], 12),
        equal_nan=True,
    )


def test_12_block_bootstrap_48_trial_multiplicity_and_promotion_gate() -> None:
    folds = [
        {
            "id": f"{y}-{m:02d}",
            "year": y,
            "month": m,
            "start_ms": ms(f"{y}-{m:02d}-02T00:00:00Z"),
            "end_ms": ms(f"{y}-{m:02d}-27T00:00:00Z"),
        }
        for y in (2021, 2022, 2023)
        for m in range(2, 10)
    ]
    trades = []
    for idx, f in enumerate(folds):
        for k in range(6):
            win = k > 0
            trades.append(
                {
                    "year": f["year"],
                    "month": f["month"],
                    "entry_at": f["start_ms"] + (k * 3 + 1) * 86_400_000,
                    "side": 1 if (idx + k) % 2 == 0 else -1,
                    "duration_minutes": 180.0,
                    "gross_bps": 95.0 if win else -20.0,
                    "net_bps": 50.0 if win else -40.0,
                    "net_usdt": 5.0 if win else -2.0,
                    "fee_usdt": 1.2,
                    "execution_drag_usdt": 1.0,
                    "net_r": 0.6 if win else -0.4,
                    "mae_bps": -20.0,
                    "mfe_bps": 110.0,
                    "exit_reason": "TARGET" if win else "STOP",
                    "raw_entry": 20000.0,
                    "stop": 19800.0,
                    "effective_entry": 20020.0,
                    "effective_exit": 20150.0 if win else 19950.0,
                    "quantity": 0.04,
                    "incremental_vs_balanced_bps": 45.0 if win else -10.0,
                }
            )
    summary = metrics.describe_extended(trades)
    summary["annual_summary"] = metrics.summarize_by_year(trades, folds)
    summary["continuous_1x_dense_MTM_drawdown_pct"] = 3.5
    summary["continuous_1x_trade_close_drawdown_pct"] = 2.0
    summary["weekly_bootstrap"] = metrics.block_bootstrap_2021_2023(
        trades, folds, block_days=7, combined_comparisons=48
    )
    summary["two_week_bootstrap"] = metrics.block_bootstrap_2021_2023(
        trades, folds, block_days=14, combined_comparisons=48
    )
    failures, status = metrics.evaluate_promotion_gate(summary)
    assert failures == []
    assert status == "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"


def test_13_independent_decimal_audit_matches_episode() -> None:
    d = make_bars()
    d[4, 1:4] = [1060.0, 1060.0, 1060.0]
    ev = make_event(3, side=1, stop=980.0, target_r=1.75)
    t = replay.episode(d, ev, CAND, STRESS, quantity=0.5)
    t["cost_case"] = "STRESS"
    t["partial_reductions"] = []
    res = audit.audit_single_trade(d[:, :6], t, STRESS)
    assert res["assertions"] == "PASS"


def test_14_quarter_hour_atr_gap_veto_and_dynamic_target_r() -> None:
    d = make_bars()
    late = make_event()
    late["decision_close"] = 970.0  # gap = 30 > 0.25 * 100
    r = replay.simulate_fold(d, [late], CAND, FOLD, BASE)
    assert not r["trades"]
    assert any("gap veto" in k for k in r["waits"])

    low_r = make_event(target_r=1.2)
    with pytest.raises(ValueError, match="1.5R"):
        replay.episode(d, low_r, CAND, BASE)
