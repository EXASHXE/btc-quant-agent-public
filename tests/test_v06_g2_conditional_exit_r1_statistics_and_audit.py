"""Tests for G2 Conditional Exit R1 statistics, 8-contrast/4-contrast bootstrap, >=20 Decimal witnesses, and report equality."""
from __future__ import annotations

import copy
from typing import Any

import numpy as np
import pytest

from scripts.strategy_research.g2_conditional_exit_r1.audit import (
    audit_single_trade_decimal,
    dec_effective_tick,
    run_previous_exit_r1_decimal_witnesses,
)
from scripts.strategy_research.g2_conditional_exit_r1.conditional_book import (
    execute_conditional_position,
)
from scripts.strategy_research.g2_conditional_exit_r1.contract import (
    ALL_SCHEMES,
    CANDIDATE_IDS,
    CONDITIONAL_SCHEMES,
    CONTRASTS,
    CONTROLLER_DISPATCH_SHA,
    EXACT_START_SHA,
    READ_ONLY_MARGIN_R2,
    READ_ONLY_ORIGINAL_EXIT_R1,
    TASK_ID,
)
from scripts.strategy_research.g2_conditional_exit_r1.report import (
    compose_empirical_report_markdown,
    verify_report_matches_machine_ledger,
)
from scripts.strategy_research.g2_conditional_exit_r1.sources import (
    verify_exit_r1_and_b_r2_provenance,
)
from scripts.strategy_research.g2_conditional_exit_r1.statistics import (
    CALENDAR_START_MS,
    analyze_conditional_branch_and_tail,
    build_contrast_registry,
    effective_utc_weeks,
    max_t_bootstrap,
    same_day_clustering_stats,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    MINUTE,
    STRESS,
)

T0_2021 = 1_612_137_600_000  # 2021-02-01 00:00:00 UTC
COST_MAP = {"STRESS": STRESS, "BASE": BASE}
DEFAULT_CAND = {
    "id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
    "horizon_hours": 12,
    "target_R": 2.0,
    "cooldown_hours": 6,
}


def _build_synthetic_witness_arrays(
    *,
    entry_idx: int = 180,
    n_minutes: int = 1600,
    base_price: float = 40_000.0,
    drift_pre_12h: float = 0.0,
    drift_last_4h: float = 0.0,
    drift_post_12h: float = 0.0,
    mark_offset_12h: float = 0.0,
    early_stop: bool = False,
    early_tp: bool = False,
    post_12h_tp: bool = False,
    post_12h_stop: bool = False,
    side: int = 1,
    funding_rate: float = 0.0001,
    eid: str = "ev_01",
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    opens = T0_2021 + np.arange(n_minutes, dtype=np.int64) * MINUTE
    last = np.empty((n_minutes, 7), dtype=float)
    last[:, 0] = opens
    last[:, 1] = base_price
    last[:, 2] = base_price + 8.0
    last[:, 3] = base_price - 8.0
    last[:, 4] = base_price
    last[:, 5] = 10.0
    last[:, 6] = opens + MINUTE - 1
    mark = last[:, :5].copy()

    idx_8h = entry_idx + 8 * 60
    idx_12h = entry_idx + 12 * 60

    for i in range(entry_idx, min(idx_8h, n_minutes)):
        frac = (i - entry_idx) / max(1, 8 * 60)
        p = base_price + side * drift_pre_12h * frac
        last[i, 1] = p
        last[i, 4] = p
        last[i, 2] = p + 8.0
        last[i, 3] = p - 8.0
        mark[i, 1:5] = p

    p_at_8h = base_price + side * drift_pre_12h
    for i in range(idx_8h, min(idx_12h, n_minutes)):
        frac = (i - idx_8h + 1) / (4 * 60)
        p = p_at_8h + side * drift_last_4h * frac
        last[i, 1] = p
        last[i, 4] = p
        last[i, 2] = p + 8.0
        last[i, 3] = p - 8.0
        mark[i, 1:5] = p

    p_at_12h = p_at_8h + side * drift_last_4h
    mark[idx_12h - 1, 4] = p_at_12h + side * mark_offset_12h
    mark[idx_12h - 1, 2] = max(mark[idx_12h - 1, 2], mark[idx_12h - 1, 4])
    mark[idx_12h - 1, 3] = min(mark[idx_12h - 1, 3], mark[idx_12h - 1, 4])

    for i in range(idx_12h, n_minutes):
        frac = (i - idx_12h + 1) / (6 * 60)
        p = p_at_12h + side * drift_post_12h * frac
        last[i, 1] = p
        last[i, 4] = p
        last[i, 2] = p + 8.0
        last[i, 3] = p - 8.0
        mark[i, 1:5] = p

    if early_stop:
        bar = entry_idx + 120
        if side == 1:
            last[bar, 3] = base_price - 500.0
        else:
            last[bar, 2] = base_price + 500.0
    elif early_tp:
        bar = entry_idx + 180
        if side == 1:
            last[bar, 2] = base_price + 900.0
        else:
            last[bar, 3] = base_price - 900.0

    if post_12h_tp:
        bar = idx_12h + 90
        if side == 1:
            last[bar, 2] = base_price + 900.0
        else:
            last[bar, 3] = base_price - 900.0
    elif post_12h_stop:
        bar = idx_12h + 90
        if side == 1:
            last[bar, 3] = base_price - 500.0
        else:
            last[bar, 2] = base_price + 500.0

    # Official 8h UTC funding timestamps: 08:00 UTC (idx 480, <12h) and 16:00 UTC (idx 960, between 12h and 18h)
    funding_events = [
        {"settlement_at": int(opens[480]), "rate": f"{funding_rate:.8f}"},
        {"settlement_at": int(opens[960]), "rate": f"{funding_rate:.8f}"},
    ]

    entry_at = int(opens[entry_idx])
    event = {
        "event_time": entry_at - 2 * MINUTE,
        "decision_at": entry_at - MINUTE,
        "entry_at": entry_at,
        "decision_close": base_price,
        "atr_hour": 200.0,
        "side": side,
        "stop": (base_price - 200.0) if side > 0 else (base_price + 200.0),
        "event_id": eid,
    }
    return last, mark, funding_events, event


# ---------------------------------------------------------------------------
# 1. >= 20 Synthetic Pure-Decimal Trade Witnesses & Tamper Rejection Tests
# ---------------------------------------------------------------------------

SYNTHETIC_WITNESS_CASES = [
    # (idx, scheme, cost, side, drift_pre, drift_4h, drift_post, mark_off, early_stop, early_tp, post_tp, post_stop, f_rate)
    (0, "X1_NET_POSITIVE_AT_12H", "STRESS", 1, 180.0, 60.0, 120.0, 0.0, False, False, False, False, 0.0001),
    (1, "X1_NET_POSITIVE_AT_12H", "BASE", 1, 180.0, 60.0, -90.0, 0.0, False, False, False, False, -0.0001),
    (2, "X1_NET_POSITIVE_AT_12H", "STRESS", -1, 200.0, 50.0, 100.0, 0.0, False, False, True, False, -0.0001),
    (3, "X1_NET_POSITIVE_AT_12H", "BASE", -1, 200.0, 50.0, -100.0, 0.0, False, False, False, True, 0.0001),
    (4, "X1_NET_POSITIVE_AT_12H", "STRESS", 1, -120.0, -30.0, 200.0, 0.0, False, False, False, False, 0.0001),
    (5, "X1_NET_POSITIVE_AT_12H", "BASE", -1, -100.0, -40.0, -150.0, 0.0, False, False, False, False, 0.0002),
    (6, "X1_NET_POSITIVE_AT_12H", "STRESS", 1, 20.0, 10.0, 50.0, 0.0, False, False, False, False, 0.0005),
    (7, "X1_NET_POSITIVE_AT_12H", "BASE", 1, 20.0, 10.0, 50.0, 150.0, False, False, False, False, 0.0001),
    (8, "X1_NET_POSITIVE_AT_12H", "STRESS", 1, 0.0, 0.0, 0.0, 0.0, True, False, False, False, 0.0001),
    (9, "X1_NET_POSITIVE_AT_12H", "BASE", -1, 0.0, 0.0, 0.0, 0.0, False, True, False, False, -0.0001),
    (10, "X2_COMPLETED_4H_TREND_AT_12H", "STRESS", 1, -150.0, 90.0, 140.0, 0.0, False, False, False, False, 0.0001),
    (11, "X2_COMPLETED_4H_TREND_AT_12H", "BASE", 1, -150.0, 90.0, 140.0, 0.0, False, False, True, False, -0.0001),
    (12, "X2_COMPLETED_4H_TREND_AT_12H", "STRESS", -1, -120.0, 80.0, 110.0, 0.0, False, False, False, False, 0.0001),
    (13, "X2_COMPLETED_4H_TREND_AT_12H", "BASE", -1, -120.0, 80.0, -80.0, 0.0, False, False, False, True, -0.0002),
    (14, "X2_COMPLETED_4H_TREND_AT_12H", "STRESS", 1, 250.0, -70.0, 100.0, 0.0, False, False, False, False, 0.0001),
    (15, "X2_COMPLETED_4H_TREND_AT_12H", "BASE", -1, 250.0, -70.0, 100.0, 0.0, False, False, False, False, 0.0001),
    (16, "X2_COMPLETED_4H_TREND_AT_12H", "STRESS", 1, 100.0, 0.0, 80.0, 0.0, False, False, False, False, 0.0),
    (17, "X2_COMPLETED_4H_TREND_AT_12H", "BASE", -1, 100.0, 0.0, 80.0, 0.0, False, False, False, False, 0.0),
    (18, "X2_COMPLETED_4H_TREND_AT_12H", "STRESS", 1, 0.0, 0.0, 0.0, 0.0, True, False, False, False, 0.0001),
    (19, "X2_COMPLETED_4H_TREND_AT_12H", "BASE", -1, 0.0, 0.0, 0.0, 0.0, False, True, False, False, 0.0001),
    (20, "E0", "STRESS", 1, 140.0, 40.0, 90.0, 0.0, False, False, False, False, 0.0001),
    (21, "H1", "BASE", -1, 140.0, 40.0, 90.0, 0.0, False, False, False, False, -0.0001),
]


@pytest.mark.parametrize("case", SYNTHETIC_WITNESS_CASES)
def test_synthetic_decimal_witness_audit_exact(case: tuple[Any, ...]) -> None:
    (
        idx,
        scheme,
        cost_name,
        side,
        drift_pre,
        drift_4h,
        drift_post,
        mark_off,
        early_stop,
        early_tp,
        post_tp,
        post_stop,
        f_rate,
    ) = case
    last, mark, funding_events, ev = _build_synthetic_witness_arrays(
        side=side,
        drift_pre_12h=drift_pre,
        drift_last_4h=drift_4h,
        drift_post_12h=drift_post,
        mark_offset_12h=mark_off,
        early_stop=early_stop,
        early_tp=early_tp,
        post_12h_tp=post_tp,
        post_12h_stop=post_stop,
        funding_rate=f_rate,
        eid=f"syn_witness_{idx:02d}",
    )
    trade = execute_conditional_position(
        last,
        mark,
        funding_events,
        ev,
        DEFAULT_CAND,
        COST_MAP[cost_name],
        scheme,
        0.25,
    )
    receipt = audit_single_trade_decimal(trade, cost_name)
    assert receipt["status"] == "PASS"
    assert receipt["event_id"] == f"syn_witness_{idx:02d}"


def test_decimal_audit_detects_tampering() -> None:
    last, mark, funding_events, ev = _build_synthetic_witness_arrays(
        side=1, drift_pre_12h=180.0, drift_last_4h=60.0, drift_post_12h=120.0, eid="tamper_ev"
    )
    trade_x1 = execute_conditional_position(
        last, mark, funding_events, ev, DEFAULT_CAND, STRESS, "X1_NET_POSITIVE_AT_12H", 0.25
    )

    # 1. Tamper effective_entry
    bad1 = copy.deepcopy(trade_x1)
    bad1["effective_entry"] += 0.2
    with pytest.raises(ValueError, match="Independent entry tick mismatch"):
        audit_single_trade_decimal(bad1, "STRESS")

    # 2. Tamper funding_cash_usdt
    bad2 = copy.deepcopy(trade_x1)
    bad2["funding_cash_usdt"] = str(float(bad2["funding_cash_usdt"]) + 0.05)
    with pytest.raises(ValueError, match="Independent funding cash drift"):
        audit_single_trade_decimal(bad2, "STRESS")

    # 3. Tamper journal cash_delta
    bad3 = copy.deepcopy(trade_x1)
    bad3["journal"][0]["cash_delta"] += 0.01
    with pytest.raises(ValueError, match="Independent cash journal sum drift"):
        audit_single_trade_decimal(bad3, "STRESS")

    # 4. Tamper X1 decision_12h extend_to_18h
    bad4 = copy.deepcopy(trade_x1)
    bad4["decision_12h"]["extend_to_18h"] = not bad4["decision_12h"]["extend_to_18h"]
    with pytest.raises(ValueError, match="X1 independent extension decision mismatch"):
        audit_single_trade_decimal(bad4, "STRESS")

    # 5. Tamper X2 signed_price_diff_str
    trade_x2 = execute_conditional_position(
        last, mark, funding_events, ev, DEFAULT_CAND, STRESS, "X2_COMPLETED_4H_TREND_AT_12H", 0.25
    )
    bad5 = copy.deepcopy(trade_x2)
    bad5["decision_12h"]["extend_to_18h"] = not bad5["decision_12h"]["extend_to_18h"]
    with pytest.raises(ValueError, match="X2 independent extension decision mismatch"):
        audit_single_trade_decimal(bad5, "STRESS")


def test_dec_effective_tick_rounding_directions() -> None:
    cost = {"fee_bps": "12", "spread_bps": "8", "slip_bps": "6"}
    # LONG entry rounds UP (ceiling), LONG exit rounds DOWN (floor)
    long_in = dec_effective_tick("40000.0", 1, cost, entry=True)
    long_out = dec_effective_tick("40000.0", 1, cost, entry=False)
    assert long_in > dec_effective_tick("40000.0", 1, {"spread_bps": "0", "slip_bps": "0"}, entry=True)
    assert long_out < dec_effective_tick("40000.0", 1, {"spread_bps": "0", "slip_bps": "0"}, entry=False)
    # SHORT entry rounds DOWN (floor), SHORT exit rounds UP (ceiling)
    short_in = dec_effective_tick("40000.0", -1, cost, entry=True)
    short_out = dec_effective_tick("40000.0", -1, cost, entry=False)
    assert short_in == long_out
    assert short_out == long_in


# ---------------------------------------------------------------------------
# 2. Previous Exit R1 Real Ledgers & Provenance Verification
# ---------------------------------------------------------------------------

def test_previous_exit_r1_decimal_witnesses_and_provenance() -> None:
    prov = verify_exit_r1_and_b_r2_provenance()
    assert prov["exit_r1_ledgers_verified"] == 12
    assert prov["b_r2_revocations_verified"] is True
    assert prov["w1_original_events"] == 34
    assert prov["w2_original_events"] == 55
    assert prov["stress_e0_time_cap_counts"]["W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H"] == 20
    assert prov["stress_e0_time_cap_counts"]["W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H"] == 36

    prev_audit = run_previous_exit_r1_decimal_witnesses()
    assert prev_audit["status"] == "PASS"
    assert prev_audit["witness_count"] >= 20
    assert prev_audit["candidates_covered"] == list(CANDIDATE_IDS)
    assert prev_audit["costs_covered"] == ["BASE", "STRESS"]
    assert prev_audit["schemes_covered"] == ["E0", "H1"]


# ---------------------------------------------------------------------------
# 3. 12h Conditional Decision Branch Decomposition & Right-Tail Concentration
# ---------------------------------------------------------------------------

def test_analyze_conditional_branch_and_tail_decomposition() -> None:
    # Build 6 synthetic paired events covering:
    # - 1 early stop (<12h)
    # - 1 early TP (<12h)
    # - 1 reached 12h, extended, post-12h TP (true positive extension)
    # - 1 reached 12h, extended, post-12h STOP (false extension)
    # - 1 reached 12h, exited at 12h, where H1 > E0 (missed favorable extension)
    # - 1 reached 12h, exited at 12h, where H1 < E0 (correctly avoided extension)
    scenarios = [
        {"early_stop": True},
        {"early_tp": True},
        {"drift_pre_12h": 200.0, "drift_last_4h": 60.0, "post_12h_tp": True},
        {"drift_pre_12h": 200.0, "drift_last_4h": 60.0, "post_12h_stop": True},
        {"drift_pre_12h": -120.0, "drift_last_4h": -40.0, "drift_post_12h": 250.0},
        {"drift_pre_12h": -120.0, "drift_last_4h": -40.0, "drift_post_12h": -200.0},
    ]
    paired_rows = []
    for idx, sc in enumerate(scenarios):
        last, mark, funding_events, ev = _build_synthetic_witness_arrays(eid=f"br_{idx}", **sc)
        cells = {}
        for sch in ALL_SCHEMES:
            t = execute_conditional_position(last, mark, funding_events, ev, DEFAULT_CAND, STRESS, sch, 0.25)
            cells[sch] = t
        paired_rows.append({
            "candidate": DEFAULT_CAND["id"],
            "cost": "STRESS",
            "event_id": ev["event_id"],
            "entry_at": ev["entry_at"],
            "side": ev["side"],
            "cells": cells,
        })

    br_x1 = analyze_conditional_branch_and_tail(paired_rows, "X1_NET_POSITIVE_AT_12H")
    assert br_x1["total_events_n"] == 6
    assert br_x1["early_stop_before_12h_n"] == 1
    assert br_x1["early_target_before_12h_n"] == 1
    assert br_x1["reached_12h_boundary_n"] == 4
    assert br_x1["extended_to_18h_n"] == 2
    assert br_x1["exited_at_12h_n"] == 2
    assert br_x1["post_12h_target_hits_n"] == 1
    assert br_x1["post_12h_stop_hits_n"] == 1
    assert br_x1["true_positive_extensions_n"] == 1
    assert br_x1["false_extensions_n"] == 1
    assert br_x1["missed_favorable_extensions_n"] == 1
    assert br_x1["correctly_avoided_extensions_n"] == 1
    # Only 1 positive delta vs E0 => top-1 share is 1.0
    assert br_x1["right_tail_concentration"]["positive_delta_events_n"] == 1
    assert abs(br_x1["right_tail_concentration"]["top_1_trade_share_of_positive_gain"] - 1.0) < 1e-12
    # Extended N = 2 < 10 => underpowered branch & thin evidence flag must be True
    assert br_x1["underpowered_branch_split"] is True
    assert br_x1["thin_evidence_flag"] is True
    assert br_x1["evidence_support_label"] == "THIN_EVIDENCE_UNDERPOWERED_BRANCH"


# ---------------------------------------------------------------------------
# 4. Simultaneous Calendar Block Bootstrap (8-Contrast & 4-Contrast Families)
# ---------------------------------------------------------------------------

def _make_bootstrap_registry(k: int, n_blocks: int = 30) -> list[tuple[str, list[dict[str, Any]]]]:
    rng = np.random.default_rng(123)
    registry: list[tuple[str, list[dict[str, Any]]]] = []
    for j in range(k):
        rows = []
        for b in range(n_blocks):
            at = CALENDAR_START_MS + b * 14 * 86_400_000 + 3_600_000
            val = float(rng.normal(loc=2.0, scale=25.0))
            rows.append({"entry_at": at, "delta_bps": val})
        registry.append((f"C_{j}", rows))
    return registry


@pytest.mark.parametrize("k", [4, 8])
@pytest.mark.parametrize("block_days", [7, 14])
def test_max_t_bootstrap_8_and_4_contrasts_deterministic(k: int, block_days: int) -> None:
    reg = _make_bootstrap_registry(k)
    res1 = max_t_bootstrap(reg, block_days, draws=1000, seed=42)
    res2 = max_t_bootstrap(reg, block_days, draws=1000, seed=42)
    assert res1["status"] == "MEASURED_CONDITIONAL_ON_EXPOSED_SELECTED_LEADS"
    assert res1["family_size"] == k
    assert res1["block_days"] == block_days
    assert res1["critical_95_maxT"] == res2["critical_95_maxT"]
    assert len(res1["contrasts"]) == k
    for c in res1["contrasts"]:
        assert c["simultaneous_LCB_bps"] < c["mean_delta_bps"] < c["simultaneous_UCB_bps"]
        assert c["nonempty_calendar_blocks"] > 0
        assert c["zero_trade_blocks"] > 0


def test_max_t_bootstrap_edge_cases() -> None:
    reg = _make_bootstrap_registry(4)
    # Invalid block_days
    with pytest.raises(ValueError, match="Expected 4 or 8 contrasts"):
        max_t_bootstrap(reg, 10, draws=100)

    # Empty contrast returns INSUFFICIENT_SUPPORT
    reg_empty = list(reg)
    reg_empty[1] = ("EMPTY", [])
    res_empty = max_t_bootstrap(reg_empty, 7, draws=200, seed=42)
    assert res_empty["status"] == "INSUFFICIENT_SUPPORT"
    assert "EMPTY" in res_empty["empty_contrasts"]

    # Out-of-window timestamp raises ValueError
    reg_bad_ts = list(reg)
    reg_bad_ts[0] = ("BAD_TS", [{"entry_at": CALENDAR_START_MS - 1000, "delta_bps": 1.0}])
    with pytest.raises(ValueError, match="Invalid paired clock"):
        max_t_bootstrap(reg_bad_ts, 7, draws=100)


def test_same_day_clustering_and_effective_weeks() -> None:
    assert effective_utc_weeks([]) == 0
    assert same_day_clustering_stats([])["total_events"] == 0
    ts = [
        T0_2021 + 3_600_000,
        T0_2021 + 7_200_000,  # same UTC day as first
        T0_2021 + 10 * 86_400_000,  # different UTC day and week
    ]
    assert effective_utc_weeks(ts) == 2
    cl = same_day_clustering_stats(ts)
    assert cl["total_events"] == 3
    assert cl["unique_utc_days"] == 2
    assert cl["same_day_clustered_events"] == 2
    assert cl["multi_event_days"] == 1
    assert cl["max_events_in_single_utc_day"] == 2


# ---------------------------------------------------------------------------
# 5. Report Composition and Machine-to-Report Equality Verifier
# ---------------------------------------------------------------------------

def _make_mock_results_payload() -> dict[str, Any]:
    last, mark, funding_events, ev = _build_synthetic_witness_arrays(
        drift_pre_12h=180.0, drift_last_4h=60.0, drift_post_12h=100.0, eid="mock_ev_1"
    )
    paired_all: dict[tuple[str, str], list[dict[str, Any]]] = {}
    candidates_payload: dict[str, Any] = {}

    for cid in CANDIDATE_IDS:
        cand_cfg = {**DEFAULT_CAND, "id": cid}
        candidates_payload[cid] = {}
        for cost_name in ("STRESS", "BASE"):
            cells = {}
            for sch in ALL_SCHEMES:
                t = execute_conditional_position(
                    last, mark, funding_events, ev, cand_cfg, COST_MAP[cost_name], sch, 0.25
                )
                cells[sch] = t
            paired_rows = [{
                "candidate": cid,
                "cost": cost_name,
                "event_id": ev["event_id"],
                "entry_at": ev["entry_at"],
                "side": ev["side"],
                "cells": cells,
            }]
            paired_all[cid, cost_name] = paired_rows

            acc_block = {}
            for sch in ALL_SCHEMES:
                acc_block[sch] = {
                    "accepted_event_set_identical_to_E0": True,
                    "occupied_minutes": 720,
                    "opportunity_cost_conflicts": 0,
                    "metrics": {
                        "trade_count": 1,
                        "mean_net_bps": 45.0,
                        "median_net_bps": 45.0,
                        "mean_net_R": 0.45,
                        "median_net_R": 0.45,
                        "net_profit_factor": 1.5,
                        "cash_return_pct": 1.25,
                        "max_mtm_drawdown_pct": 2.1,
                        "funding_signed_usdt": -0.5,
                        "total_fees_usdt": 3.2,
                        "execution_drag_usdt": 1.8,
                        "yearly_breakdown": {
                            y: {
                                "n_trades": 1 if y == "2021" else 0,
                                "mean_net_bps": 45.0 if y == "2021" else None,
                                "median_net_bps": 45.0 if y == "2021" else None,
                                "gross_mean_bps": 60.0 if y == "2021" else None,
                                "cash_return_pct": 1.25 if y == "2021" else -0.5,
                                "funding_usdt": -0.5 if y == "2021" else 0.0,
                                "fee_usdt": 3.2 if y == "2021" else 0.0,
                            }
                            for y in ("2021", "2022", "2023")
                        },
                    },
                }
            branch_block = {
                sch: analyze_conditional_branch_and_tail(paired_rows, sch)
                for sch in CONDITIONAL_SCHEMES
            }
            candidates_payload[cid][cost_name] = {
                "account": acc_block,
                "conditional_branch_analysis": branch_block,
            }

    paired_decomp = {}
    inference_block = {}
    reg8_mock = _make_bootstrap_registry(8)
    for cost_name in ("STRESS", "BASE"):
        _, decomp = build_contrast_registry(paired_all, CANDIDATE_IDS, cost_name)
        paired_decomp[cost_name] = decomp
        b7 = max_t_bootstrap(reg8_mock, 7, draws=200, seed=42)
        b14 = max_t_bootstrap(reg8_mock, 14, draws=200, seed=42)
        names = [f"{c}:{a}-{b}" for c in CANDIDATE_IDS for a, b in CONTRASTS]
        for idx_c, n_str in enumerate(names):
            b7["contrasts"][idx_c]["contrast"] = n_str
            b14["contrasts"][idx_c]["contrast"] = n_str
        inference_block[cost_name] = {
            "joint_8_contrasts": {"7": b7, "14": b14},
            "per_candidate_4_contrasts": {
                cid: {
                    "7": max_t_bootstrap(_make_bootstrap_registry(4), 7, draws=200, seed=42),
                    "14": max_t_bootstrap(_make_bootstrap_registry(4), 14, draws=200, seed=42),
                }
                for cid in CANDIDATE_IDS
            },
        }

    return {
        "TASK_ID": TASK_ID,
        "CONTROLLER_DISPATCH_SHA": CONTROLLER_DISPATCH_SHA,
        "EXACT_START_SHA": EXACT_START_SHA,
        "READ_ONLY_ORIGINAL_EXIT_R1": READ_ONLY_ORIGINAL_EXIT_R1,
        "READ_ONLY_MARGIN_R2": READ_ONLY_MARGIN_R2,
        "frozen_code_sha": "a" * 40,
        "source_manifest_sha256": "b" * 64,
        "terminal": "X1_X2_INSUFFICIENT_SUPPORT",
        "grade": "B_LINE_CONDITIONAL_EXIT_R1_NEGATIVE_RETAIN_BASELINES_NO_PROMOTION",
        "provenance_and_revocations": {
            "exit_r1_ledgers_verified": 12,
            "b_r2_revocations_verified": True,
        },
        "baseline_e0_h1_identity": {"status": "PASS_EXACT_REPRODUCTION"},
        "candidates": candidates_payload,
        "paired_contrast_decomposition": paired_decomp,
        "inference": inference_block,
        "cross_candidate_same_day_overlap": {
            "w1_unique_utc_days": 1,
            "w2_unique_utc_days": 1,
            "shared_utc_days_count": 1,
        },
        "independent_Decimal_audit": {
            "status": "PASS",
            "audited_new_trade_episodes_n": 24,
            "audited_previous_exit_r1_witnesses_n": 40,
            "total_decimal_witnesses_n": 64,
            "official_funding_events_verified": 3285,
        },
        "terminal_gate_summary": {
            "simultaneous_ci_includes_zero_or_negative": True,
            "thin_evidence_or_underpowered_branch": True,
            "w2_2023_negative_or_nonpositive": True,
        },
    }


def test_compose_and_verify_report_matches_machine_ledger() -> None:
    payload = _make_mock_results_payload()
    md = compose_empirical_report_markdown(payload)
    assert verify_report_matches_machine_ledger(md, payload) is True

    # Tamper with a number in the markdown report and verify rejection
    bad_md = md.replace(
        "| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `E0` | 1 |",
        "| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `E0` | 99 |",
    )
    with pytest.raises(ValueError, match="Report Table 2 row mismatch"):
        verify_report_matches_machine_ledger(bad_md, payload)
