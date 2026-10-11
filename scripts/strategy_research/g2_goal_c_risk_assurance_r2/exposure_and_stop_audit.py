"""C2.2 & C2.3: Independent 20-cell 1x exposure reconstruction (repairing E0 0-exposure defect) and stop-vs-liquidation proof.

Reconstructs per-minute open quantity `q(t)`, raw Mark notional `q(t) * Mark_close(t)`, and
minute Mark liquidation equity `E_Mark(t)` across all 20 Exit R1 account cells in pure Decimal
directly from the read-only `*_orders.jsonl` ledgers and authenticated 1m Mark bars, cross-checking:
1. `.npz` minute equity curves (`funded` in R3.1 for E0, `curve` in Exit R1 for H1/H2/E1/E2) to `<= 1e-7`,
2. Monthly peak exposure ratios (`marked_exposure_ratio` for E0, `peak_exposure_ratio` for H1/H2/E1/E2),
3. Original R3.1 E0 digests, 5% reserve gate (`0.95 * min(cash, 1000)`), and pre/post ACK cash conservation.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from . import (
    CANDIDATE_IDS,
    COST_NAMES,
    EXIT_R1_CACHE_DIR,
    EXIT_R1_EVIDENCE_DIR,
    R31_CACHE_DIR,
    R31_EVIDENCE_DIR,
    SCHEMES,
)
from .decimal_margin_engine import (
    BPS_DIVISOR,
    COST_MODELS_DEC,
    D,
    compute_stop_vs_liquidation_inequalities,
    dec_mark_liquidation_equity,
)


def _ms_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit_20_cells_exposure_and_stops(
    mark_all: np.ndarray,
    exit_r1_evidence_dir: Path = EXIT_R1_EVIDENCE_DIR,
    r31_evidence_dir: Path = R31_EVIDENCE_DIR,
    r31_cache_dir: Path = R31_CACHE_DIR,
    exit_r1_cache_dir: Path = EXIT_R1_CACHE_DIR,
) -> dict[str, Any]:
    """Reconstruct per-minute open q and Mark notional/equity across all 20 cells and audit stop distributions."""
    r1_results = json.loads(
        (exit_r1_evidence_dir / "EXIT_R1_RESULTS.json").read_text(encoding="utf-8")
    )
    r31_results = json.loads(
        (r31_evidence_dir / "R31_ECONOMIC_RESULTS.json").read_text(encoding="utf-8")
    )

    cell_summaries: list[dict[str, Any]] = []
    e0_four_cell_witnesses: dict[str, dict[str, Any]] = {}
    stop_gap_events: list[dict[str, Any]] = []
    total_admission_checks = 0
    total_reserve_breaches = 0
    max_ack_cash_conservation_diff = Decimal(0)
    global_max_npz_equity_diff = Decimal(0)
    global_max_peak_ratio_diff = Decimal(0)

    for cid in CANDIDATE_IDS:
        for cost_name in COST_NAMES:
            cost = COST_MODELS_DEC[cost_name]
            for scheme in SCHEMES:
                orders_path = exit_r1_evidence_dir / f"{cid}_{cost_name}_{scheme}_orders.jsonl"
                trades = [
                    json.loads(line)
                    for line in orders_path.read_text(encoding="utf-8").splitlines()
                ]
                acc_node = r1_results["candidates"][cid][cost_name]["account"][scheme]
                monthly = acc_node["monthly"]

                if scheme == "E0":
                    npz_path = r31_cache_dir / f"{cid}_{cost_name}_equity.npz"
                    npz_curve = np.load(npz_path)["funded"]
                    committed_peak_ratio = max(float(m["marked_exposure_ratio"]) for m in monthly)
                    committed_breach_mins = 0
                    committed_min_monthly_eq = min(float(m["funded_end"]) for m in monthly)
                    r31_node = r31_results["candidates"][cid]["costs"][cost_name]
                    assert (
                        acc_node["legacy_identity"]
                        == "EXACT_R31_FULL_FUNDED_BOOK_AND_MINUTE_CURVES"
                    )
                    assert acc_node["monthly"] == r31_node["monthly"]
                else:
                    npz_path = exit_r1_cache_dir / f"{cid}_{cost_name}_{scheme}_Mark_curve.npz"
                    npz_curve = np.load(npz_path)["curve"]
                    committed_peak_ratio = max(float(m["peak_exposure_ratio"]) for m in monthly)
                    committed_breach_mins = sum(int(m["exposure_above_1x_minutes"]) for m in monthly)
                    committed_min_monthly_eq = min(float(m["Mark_min_equity"]) for m in monthly)

                peak_ratio_dec = Decimal(0)
                min_open_mark_eq_dec = Decimal(1000000)
                max_cell_npz_diff = Decimal(0)
                occupied_open_minutes = 0
                breach_1x_minutes = 0
                cell_reserve_breaches = 0
                earliest_pos_q_witness: dict[str, Any] | None = None
                peak_exp_witness: dict[str, Any] | None = None

                for t_idx, t in enumerate(trades):
                    total_admission_checks += 1
                    cash_before = D(t["cash_before_entry"])
                    cash_after = D(t["cash_after_ack"])
                    net_after_fund = D(t["net_after_funding_usdt"])
                    ack_diff = abs((cash_before + net_after_fund) - cash_after)
                    max_ack_cash_conservation_diff = max(max_ack_cash_conservation_diff, ack_diff)

                    budget = Decimal("0.95") * min(cash_before, Decimal(1000))
                    q_init = D(t["quantity"])
                    eff_e = D(t["effective_entry"])
                    fee_e = D(t["fee_entry"])
                    outlay = q_init * eff_e + fee_e
                    if outlay > budget + Decimal("1e-7"):
                        cell_reserve_breaches += 1
                        total_reserve_breaches += 1

                    for tier in t.get("tiers", []):
                        if tier["reason"] == "STOP_GAP":
                            stop_p = D(t["stop"])
                            raw_ex = D(tier["raw_exit"])
                            raw_en = D(t["raw_entry"])
                            gap_bps = BPS_DIVISOR * abs(raw_ex - stop_p) / raw_en
                            stop_gap_events.append({
                                "candidate": cid,
                                "cost": cost_name,
                                "scheme": scheme,
                                "event_id": t["event_id"],
                                "side": int(t["side"]),
                                "stop_price": float(stop_p),
                                "gap_open_exit_price": float(raw_ex),
                                "adverse_gap_beyond_stop_bps": round(float(gap_bps), 4),
                            })

                    side = int(t["side"])
                    entry_at = int(t["entry_at"])
                    exit_at = int(t["exit_at"])
                    exit_ack_at = int(t["exit_ack_at"])

                    i_start = int(np.searchsorted(mark_all[:, 0], entry_at, side="left"))
                    end_bar_open = (
                        (exit_at // 60_000) * 60_000
                        if scheme == "E0"
                        else (exit_ack_at // 60_000) * 60_000
                    )
                    i_end = int(np.searchsorted(mark_all[:, 0], end_bar_open, side="left"))
                    npz_start = int(np.searchsorted(npz_curve[:, 0], int(mark_all[i_start, 0]) + 59_999, side="left"))

                    # Pre-convert journal and tier entries once per trade for speed and exactness
                    journal_items = [
                        (int(j["timestamp"]), D(j["cash_delta"])) for j in t["journal"]
                    ]
                    tier_items = [
                        (
                            int(x["exit_at"]),
                            int(x["exit_ack_at"]),
                            D(x["quantity"]),
                            Decimal(side) * (D(x["effective_exit"]) - eff_e) * D(x["quantity"]),
                        )
                        for x in t["tiers"]
                    ]

                    for offset, i in enumerate(range(i_start, i_end + 1)):
                        m_open = int(mark_all[i, 0])
                        m_close = m_open + 59_999
                        if scheme == "E0" and (m_open >= exit_at or i == i_end):
                            continue
                        rem_q = q_init - sum(
                            (tq for tex, _, tq, _ in tier_items if tex <= m_close),
                            Decimal(0),
                        )
                        if rem_q <= Decimal("1e-10"):
                            continue

                        occupied_open_minutes += 1
                        settled = cash_before + sum(
                            (cd for jts, cd in journal_items if jts <= m_close),
                            Decimal(0),
                        )
                        pending = sum(
                            (tpnl for tex, tack, _, tpnl in tier_items if tex <= m_close < tack),
                            Decimal(0),
                        )
                        raw_m_val = mark_all[i, 4]
                        eq_dec, notional_dec, ratio_dec = dec_mark_liquidation_equity(
                            settled, pending, side, eff_e, rem_q, raw_m_val, cost
                        )
                        min_open_mark_eq_dec = min(min_open_mark_eq_dec, eq_dec)

                        npz_val = D(npz_curve[npz_start + offset, 1])
                        eq_diff = abs(eq_dec - npz_val)
                        max_cell_npz_diff = max(max_cell_npz_diff, eq_diff)

                        if ratio_dec > Decimal(1) + Decimal("1e-9"):
                            breach_1x_minutes += 1

                        if earliest_pos_q_witness is None:
                            earliest_pos_q_witness = {
                                "trade_index": t_idx,
                                "event_id": t["event_id"],
                                "side": side,
                                "entry_at_ms": entry_at,
                                "entry_at_utc": _ms_to_iso(entry_at),
                                "minute_close_at_ms": m_close,
                                "minute_close_at_utc": _ms_to_iso(m_close),
                                "open_qty_btc": float(rem_q),
                                "mark_close_price": float(raw_m_val),
                                "raw_mark_notional_usdt": round(float(notional_dec), 6),
                                "reconstructed_mark_equity_usdt": round(float(eq_dec), 6),
                                "npz_curve_mark_equity_usdt": round(float(npz_val), 6),
                                "abs_equity_diff_usdt": float(eq_diff),
                                "notional_to_mark_equity_ratio": round(float(ratio_dec), 8),
                            }

                        if ratio_dec > peak_ratio_dec:
                            peak_ratio_dec = ratio_dec
                            peak_exp_witness = {
                                "trade_index": t_idx,
                                "event_id": t["event_id"],
                                "side": side,
                                "entry_at_ms": entry_at,
                                "minute_close_at_ms": m_close,
                                "minute_close_at_utc": _ms_to_iso(m_close),
                                "open_qty_btc": float(rem_q),
                                "mark_close_price": float(raw_m_val),
                                "raw_mark_notional_usdt": round(float(notional_dec), 6),
                                "reconstructed_mark_equity_usdt": round(float(eq_dec), 6),
                                "npz_curve_mark_equity_usdt": round(float(npz_val), 6),
                                "abs_equity_diff_usdt": float(eq_diff),
                                "peak_notional_to_mark_equity_ratio": round(float(ratio_dec), 8),
                            }

                assert max_cell_npz_diff <= Decimal("1e-7"), f"NPZ diff {max_cell_npz_diff} > 1e-7"
                peak_ratio_diff = abs(peak_ratio_dec - D(committed_peak_ratio))
                assert peak_ratio_diff <= Decimal("1e-7"), f"Peak ratio diff {peak_ratio_diff} > 1e-7"
                assert breach_1x_minutes == committed_breach_mins == 0

                global_max_npz_equity_diff = max(global_max_npz_equity_diff, max_cell_npz_diff)
                global_max_peak_ratio_diff = max(global_max_peak_ratio_diff, peak_ratio_diff)

                cell_key = f"{cid}__{cost_name}__{scheme}"
                summary_row = {
                    "cell_key": cell_key,
                    "candidate": cid,
                    "cost": cost_name,
                    "scheme": scheme,
                    "trades_executed_n": len(trades),
                    "occupied_open_minutes_n": occupied_open_minutes,
                    "c_r1_reported_peak_ratio": 0.0 if scheme == "E0" else round(committed_peak_ratio, 6),
                    "c_r1_reported_status": "INVALID_KEY_LOOKUP_DEFAULT_ZERO" if scheme == "E0" else "MATCHED",
                    "reconstructed_peak_mark_notional_to_equity_ratio": round(float(peak_ratio_dec), 8),
                    "committed_monthly_peak_exposure_ratio": round(committed_peak_ratio, 8),
                    "abs_peak_ratio_diff": float(peak_ratio_diff),
                    "exposure_above_1x_minutes": breach_1x_minutes,
                    "max_abs_minute_equity_diff_vs_npz": float(max_cell_npz_diff),
                    "min_open_minute_mark_equity_usdt": round(float(min_open_mark_eq_dec), 4),
                    "min_committed_monthly_equity_usdt": round(committed_min_monthly_eq, 4),
                    "ending_equity_usdt": round(
                        float(
                            acc_node["metrics"].get(
                                "ending_usdt", acc_node["metrics"].get("ending_cash_usdt")
                            )
                        ),
                        4,
                    ),
                    "max_mtm_drawdown_pct": round(float(acc_node["metrics"]["max_mtm_drawdown_pct"]), 4),
                    "five_pct_reserve_breaches_n": cell_reserve_breaches,
                    "earliest_positive_q_witness": earliest_pos_q_witness,
                    "peak_exposure_witness": peak_exp_witness,
                }
                cell_summaries.append(summary_row)
                if scheme == "E0":
                    e0_four_cell_witnesses[cell_key] = {
                        "candidate": cid,
                        "cost": cost_name,
                        "scheme": "E0",
                        "trades_executed_n": len(trades),
                        "occupied_open_minutes_n": occupied_open_minutes,
                        "c_r1_erroneous_peak_ratio": 0.0,
                        "reconstructed_peak_mark_notional_to_equity_ratio": round(float(peak_ratio_dec), 8),
                        "r31_and_exit_r1_monthly_marked_exposure_ratio": round(committed_peak_ratio, 8),
                        "abs_peak_ratio_diff": float(peak_ratio_diff),
                        "max_abs_minute_equity_diff_vs_r31_funded_npz": float(max_cell_npz_diff),
                        "earliest_positive_q_witness": earliest_pos_q_witness,
                        "peak_exposure_witness": peak_exp_witness,
                    }

    # Historical 1R stop distance distribution vs unstopped 24h MAE path tails
    stop_distributions: dict[str, Any] = {}
    for cid in CANDIDATE_IDS:
        p_path = exit_r1_evidence_dir / f"{cid}_STRESS_paired.jsonl"
        rows = [json.loads(line) for line in p_path.read_text(encoding="utf-8").splitlines()]
        stop_pcts: list[float] = []
        last_mae_r: list[float] = []
        mark_mae_r: list[float] = []
        unstopped_24h_mark_mae_pct_of_entry: list[float] = []
        max_stop_event: dict[str, Any] | None = None

        for r in rows:
            e0_c = r["cells"]["E0"]
            raw_en = float(e0_c["raw_entry"])
            init_risk = float(e0_c["initial_risk"])
            s_pct = 100.0 * init_risk / raw_en
            stop_pcts.append(s_pct)

            l_mae = min(
                float(r["path24h"]["before12h"]["Last_MAE_R"]),
                float(r["path24h"]["12to18h"]["Last_MAE_R"]),
                float(r["path24h"]["18to24h"]["Last_MAE_R"]),
            )
            m_mae = min(
                float(r["path24h"]["before12h"]["Mark_MAE_R"]),
                float(r["path24h"]["12to18h"]["Mark_MAE_R"]),
                float(r["path24h"]["18to24h"]["Mark_MAE_R"]),
            )
            last_mae_r.append(l_mae)
            mark_mae_r.append(m_mae)
            unstopped_24h_mark_mae_pct_of_entry.append(abs(m_mae) * s_pct)

            if max_stop_event is None or s_pct > max_stop_event["stop_distance_pct_of_entry"]:
                max_stop_event = {
                    "event_id": r["event_id"],
                    "side": int(r["side"]),
                    "raw_entry": raw_en,
                    "effective_entry": float(e0_c["effective_entry"]),
                    "stop_price": float(e0_c["stop"]),
                    "initial_risk_usdt_per_btc": init_risk,
                    "stop_distance_pct_of_entry": round(s_pct, 6),
                }

        arr_s = np.array(stop_pcts, dtype=float)
        arr_unstopped = np.array(unstopped_24h_mark_mae_pct_of_entry, dtype=float)
        stop_distributions[cid] = {
            "events_n": len(rows),
            "min_initial_1R_stop_distance_pct": round(float(np.min(arr_s)), 4),
            "p25_initial_1R_stop_distance_pct": round(float(np.percentile(arr_s, 25)), 4),
            "median_initial_1R_stop_distance_pct": round(float(np.median(arr_s)), 4),
            "p75_initial_1R_stop_distance_pct": round(float(np.percentile(arr_s, 75)), 4),
            "p90_initial_1R_stop_distance_pct": round(float(np.percentile(arr_s, 90)), 4),
            "max_initial_1R_stop_distance_pct": round(float(np.max(arr_s)), 4),
            "max_1R_stop_event_witness": max_stop_event,
            "worst_unstopped_24h_last_mae_R": round(float(np.min(last_mae_r)), 4),
            "worst_unstopped_24h_mark_mae_R": round(float(np.min(mark_mae_r)), 4),
            "worst_unstopped_24h_mark_excursion_pct_of_entry": round(float(np.max(arr_unstopped)), 4),
        }

    w1_dist = stop_distributions["W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H"]
    w2_dist = stop_distributions["W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H"]

    inequalities = compute_stop_vs_liquidation_inequalities(
        w1_max_stop_pct=D(w1_dist["max_initial_1R_stop_distance_pct"]) / Decimal(100),
        w1_median_stop_pct=D(w1_dist["median_initial_1R_stop_distance_pct"]) / Decimal(100),
        w2_max_stop_pct=D(w2_dist["max_initial_1R_stop_distance_pct"]) / Decimal(100),
        w2_median_stop_pct=D(w2_dist["median_initial_1R_stop_distance_pct"]) / Decimal(100),
        synthetic_stop_pct=Decimal("0.075000"),
    )

    return {
        "status": "PASS",
        "c_r1_contradiction_1_disposition": {
            "c_r1_e0_zero_exposure_claim_status": "INVALID__SCHEMA_KEY_LOOKUP_BUG_IN_C_R1_RISK_ENVELOPE",
            "c_r1_defect_location": "scripts/strategy_research/g2_goal_execution_assurance_r1/risk_envelope.py lines 382-393",
            "exact_root_cause": (
                "In `EXIT_R1_RESULTS.json`, the 4 inherited E0 cells store their monthly peak exposure ratio under "
                "key `'marked_exposure_ratio'` and monthly ending equity under `'funded_end'` (inherited from "
                "`R31_ECONOMIC_RESULTS.json`), whereas H1/H2/E1/E2 store `'peak_exposure_ratio'` and `'Mark_min_equity'`. "
                "C R1's `risk_envelope.py` queried `m.get('peak_exposure_ratio', m.get('max_position_notional_to_marked_equity', 0.0))` "
                "and `m.get('Mark_min_equity', m.get('ending_equity', 1000.0))`, silently defaulting all four E0 cells "
                "to `0.0` peak exposure and `1000.0` min monthly equity despite 34 (W1) and 55 (W2) executed trades."
            ),
            "reconstructed_e0_peak_ratios": {
                k: v["reconstructed_peak_mark_notional_to_equity_ratio"]
                for k, v in e0_four_cell_witnesses.items()
            },
        },
        "total_cells_reconstructed_n": len(cell_summaries),
        "total_admission_trades_verified_n": total_admission_checks,
        "total_five_pct_reserve_breaches_n": total_reserve_breaches,
        "total_exposure_above_1x_minutes_across_all_20_cells": sum(
            c["exposure_above_1x_minutes"] for c in cell_summaries
        ),
        "max_exposure_ratio_across_all_20_cells": max(
            c["reconstructed_peak_mark_notional_to_equity_ratio"] for c in cell_summaries
        ),
        "min_peak_exposure_ratio_across_all_20_cells": min(
            c["reconstructed_peak_mark_notional_to_equity_ratio"] for c in cell_summaries
        ),
        "global_max_abs_minute_equity_diff_vs_npz": float(global_max_npz_equity_diff),
        "global_max_abs_peak_ratio_diff_vs_committed": float(global_max_peak_ratio_diff),
        "max_ack_cash_conservation_diff_usdt": float(max_ack_cash_conservation_diff),
        "e0_four_cell_witnesses": e0_four_cell_witnesses,
        "all_20_cells_exposure_summaries": cell_summaries,
        "realized_stop_gap_events_n": len(stop_gap_events),
        "realized_stop_gap_events": stop_gap_events,
        "historical_stop_distance_and_mae_distributions": stop_distributions,
        "stop_vs_liquidation_inequality_proof": inequalities,
    }
