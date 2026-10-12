"""Descriptive metrics, 12h branch decomposition, right-tail concentration, and simultaneous max-|T| block bootstrap."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    CALENDAR_END_MS,
    CALENDAR_START_MS,
    calculate_candidate_metrics,
)

from .contract import CONTRASTS

MIN_BRANCH_SUPPORT = 10
MIN_CALENDAR_BLOCKS = 8


def safe_mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def safe_median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def effective_utc_weeks(timestamps_ms: list[int]) -> int:
    if not timestamps_ms:
        return 0
    return len({datetime.fromtimestamp(ts / 1000, UTC).isocalendar()[:2] for ts in timestamps_ms})


def same_day_clustering_stats(timestamps_ms: list[int]) -> dict[str, Any]:
    if not timestamps_ms:
        return {
            "total_events": 0,
            "unique_utc_days": 0,
            "same_day_clustered_events": 0,
            "multi_event_days": 0,
            "max_events_in_single_utc_day": 0,
        }
    days = [datetime.fromtimestamp(ts / 1000, UTC).strftime("%Y-%m-%d") for ts in timestamps_ms]
    counts = Counter(days)
    multi_days = {d: c for d, c in counts.items() if c > 1}
    return {
        "total_events": len(timestamps_ms),
        "unique_utc_days": len(counts),
        "same_day_clustered_events": sum(c for c in multi_days.values()),
        "multi_event_days": len(multi_days),
        "max_events_in_single_utc_day": max(counts.values()),
    }


def descriptive_metrics(
    trades: list[dict[str, Any]],
    cost_name: str,
    curve: np.ndarray | None = None,
    monthly: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute comprehensive descriptive metrics for paired or full-account trade sets."""
    values = [
        {
            **t,
            "net_usdt": float(t["net_after_funding_usdt"]),
            "net_bps": float(t["net_after_funding_bps"]),
        }
        for t in trades
    ]
    result = calculate_candidate_metrics(
        values,
        cost_name,
        minute_equity_curve=[1000.0, *curve[:, 1].tolist()] if curve is not None else None,
    )
    risks = [
        t["net_usdt"]
        / (
            float(t["quantity"])
            * float(t.get("initial_risk", int(t["side"]) * (float(t["effective_entry"]) - float(t["stop"]))))
        )
        for t in values
    ]
    net_bps_list = [t["net_bps"] for t in values]
    gross_bps_list = [float(t["gross_bps"]) for t in values]
    drag_usdt_list = [float(t.get("execution_drag_usdt", 0.0)) for t in trades]
    drag_bps_list = [
        10_000.0 * float(t.get("execution_drag_usdt", 0.0)) / float(t["entry_notional"])
        for t in trades
    ]
    entry_ts = [int(t["entry_at"]) for t in trades]

    result.update({
        "mean_net_bps": safe_mean(net_bps_list),
        "median_net_bps": safe_median(net_bps_list),
        "mean_gross_bps": safe_mean(gross_bps_list),
        "median_gross_bps": safe_median(gross_bps_list),
        "mean_net_R": safe_mean(risks),
        "median_net_R": safe_median(risks),
        "execution_drag_usdt": sum(drag_usdt_list),
        "mean_execution_drag_bps": safe_mean(drag_bps_list),
        "fee_entry_usdt": sum(float(t["fee_entry"]) for t in trades),
        "fee_exit_usdt": sum(float(t["fee_exit"]) for t in trades),
        "total_fees_usdt": sum(float(t["fee_entry"]) + float(t["fee_exit"]) for t in trades),
        "funding_signed_usdt": sum(float(t["funding_cash_usdt"]) for t in trades),
        "funding_events": sum(len(t["funding_settlements"]) for t in trades),
        "funding_debits_usdt": sum(
            -float(x["signed_cash_usdt"])
            for t in trades
            for x in t["funding_settlements"]
            if float(x["signed_cash_usdt"]) < 0
        ),
        "funding_credits_usdt": sum(
            float(x["signed_cash_usdt"])
            for t in trades
            for x in t["funding_settlements"]
            if float(x["signed_cash_usdt"]) > 0
        ),
        "mean_weighted_exit_age_minutes": safe_mean(
            [float(t.get("weighted_exit_age_minutes", t["duration_minutes"])) for t in trades]
        ),
        "effective_utc_weeks": effective_utc_weeks(entry_ts),
        "same_day_clustering": same_day_clustering_stats(entry_ts),
        "matched_balanced_mean_bps": safe_mean(
            [float(t["control_net_bps"]) for t in trades if t.get("control_net_bps") is not None]
        ),
        "matched_balanced_qualified_n": sum(t.get("control_net_bps") is not None for t in trades),
    })

    counts = result["exit_reasons"]
    n = len(trades)
    result["exit_reason_shares"] = {k: v / n for k, v in counts.items()} if n else {}
    result["side"] = {}
    for side_val, label in ((1, "LONG"), (-1, "SHORT")):
        st = [t for t in values if int(t["side"]) == side_val]
        result["side"][label] = {
            "n": len(st),
            "mean_net_bps": safe_mean([t["net_bps"] for t in st]),
            "median_net_bps": safe_median([t["net_bps"] for t in st]),
            "net_cash_usdt": sum(t["net_usdt"] for t in st),
        }

    for y_str, row in result["yearly_breakdown"].items():
        y_int = int(y_str)
        st = [t for t in values if datetime.fromtimestamp(int(t["entry_at"]) / 1000, UTC).year == y_int]
        row.update({
            "gross_mean_bps": safe_mean([float(t["gross_bps"]) for t in st]),
            "median_net_bps": safe_median([t["net_bps"] for t in st]),
            "funding_usdt": sum(float(t["funding_cash_usdt"]) for t in st),
            "fee_usdt": sum(float(t["fee_entry"]) + float(t["fee_exit"]) for t in st),
            "execution_drag_usdt": sum(float(t.get("execution_drag_usdt", 0.0)) for t in st),
        })
        if monthly is not None:
            months = [m for m in monthly if int(m["year"]) == y_int]
            if months:
                row["cash_return_pct"] = 100.0 * (
                    float(months[-1]["ending_cash"]) / float(months[0]["starting_cash"]) - 1.0
                )

    if curve is not None:
        result.update({
            "ending_cash_usdt": float(curve[-1, 1]),
            "cash_return_pct": 100.0 * (float(curve[-1, 1]) / 1000.0 - 1.0),
            "min_mark_equity_usdt": float(np.min(curve[:, 1])),
        })
    return result


def analyze_conditional_branch_and_tail(
    paired_rows: list[dict[str, Any]],
    scheme: str,
) -> dict[str, Any]:
    """Decompose 12h conditional decisions, post-12h outcomes, false extensions, and right-tail concentration."""
    total_n = len(paired_rows)
    early_stop_n = 0
    early_target_n = 0
    reached_12h_n = 0
    extended_n = 0
    exited_at_12h_n = 0

    post_12h_target_n = 0
    post_12h_stop_n = 0
    post_12h_time_cap_18h_n = 0

    true_positive_extensions_n = 0  # Extended at 12h AND net(18h) > net(12h)
    false_extensions_n = 0  # Extended at 12h AND net(18h) < net(12h)
    neutral_extensions_n = 0  # Extended at 12h AND net(18h) == net(12h)
    missed_favorable_extensions_n = 0  # Exited at 12h BUT H1 net(18h) > E0 net(12h)
    correctly_avoided_extensions_n = 0  # Exited at 12h AND H1 net(18h) <= E0 net(12h)

    extension_deltas_vs_e0: list[float] = []
    all_deltas_vs_e0: list[float] = []
    all_deltas_vs_h1: list[float] = []
    mark_vs_last_12h_bps: list[float] = []
    decisions_table: list[dict[str, Any]] = []

    for row in paired_rows:
        e0 = row["cells"]["E0"]
        h1 = row["cells"]["H1"]
        cell = row["cells"][scheme]
        dec = cell["decision_12h"]

        e0_bps = float(e0["net_after_funding_bps"])
        h1_bps = float(h1["net_after_funding_bps"])
        cell_bps = float(cell["net_after_funding_bps"])
        delta_vs_e0 = cell_bps - e0_bps
        delta_vs_h1 = cell_bps - h1_bps
        h1_minus_e0 = h1_bps - e0_bps

        all_deltas_vs_e0.append(delta_vs_e0)
        all_deltas_vs_h1.append(delta_vs_h1)

        if not dec["reached_12h_time_cap_boundary"]:
            if e0["exit_reason"] in ("STOP", "STOP_GAP"):
                early_stop_n += 1
            elif e0["exit_reason"] in ("TARGET", "TARGET_GAP_CAPPED"):
                early_target_n += 1
        else:
            reached_12h_n += 1
            if "estimated_liquidation_net_bps" in dec:
                mark_vs_last_12h_bps.append(float(dec["estimated_liquidation_net_bps"]) - e0_bps)
            if dec["extend_to_18h"]:
                extended_n += 1
                extension_deltas_vs_e0.append(delta_vs_e0)
                if cell["exit_reason"] in ("TARGET", "TARGET_GAP_CAPPED"):
                    post_12h_target_n += 1
                elif cell["exit_reason"] in ("STOP", "STOP_GAP"):
                    post_12h_stop_n += 1
                else:
                    post_12h_time_cap_18h_n += 1

                if delta_vs_e0 > 1e-9:
                    true_positive_extensions_n += 1
                elif delta_vs_e0 < -1e-9:
                    false_extensions_n += 1
                else:
                    neutral_extensions_n += 1
            else:
                exited_at_12h_n += 1
                if h1_minus_e0 > 1e-9:
                    missed_favorable_extensions_n += 1
                else:
                    correctly_avoided_extensions_n += 1

        decisions_table.append({
            "event_id": row["event_id"],
            "entry_at": int(row["entry_at"]),
            "year": datetime.fromtimestamp(int(row["entry_at"]) / 1000, UTC).year,
            "side": int(row["side"]),
            "reached_12h": bool(dec["reached_12h_time_cap_boundary"]),
            "extend_to_18h": bool(dec["extend_to_18h"]),
            "outcome_at_12h": dec["outcome_at_12h"],
            "decision_12h_details": dec,
            "e0_exit_reason": e0["exit_reason"],
            "h1_exit_reason": h1["exit_reason"],
            "scheme_exit_reason": cell["exit_reason"],
            "e0_net_bps": e0_bps,
            "h1_net_bps": h1_bps,
            "scheme_net_bps": cell_bps,
            "delta_vs_e0_bps": delta_vs_e0,
            "delta_vs_h1_bps": delta_vs_h1,
        })

    # Right-tail concentration analysis on positive deltas vs E0
    positive_deltas = sorted([d for d in all_deltas_vs_e0 if d > 1e-9], reverse=True)
    total_positive_gain_bps = sum(positive_deltas)
    top1_share = (positive_deltas[0] / total_positive_gain_bps) if total_positive_gain_bps > 0 else 0.0
    top2_share = (sum(positive_deltas[:2]) / total_positive_gain_bps) if total_positive_gain_bps > 0 else 0.0
    top3_share = (sum(positive_deltas[:3]) / total_positive_gain_bps) if total_positive_gain_bps > 0 else 0.0

    # Thin evidence / underpowered check
    underpowered_branch = extended_n < MIN_BRANCH_SUPPORT or exited_at_12h_n < MIN_BRANCH_SUPPORT
    thin_extension_outcomes = (
        post_12h_target_n <= 2
        or true_positive_extensions_n <= 2
        or underpowered_branch
    )

    return {
        "scheme": scheme,
        "total_events_n": total_n,
        "early_stop_before_12h_n": early_stop_n,
        "early_target_before_12h_n": early_target_n,
        "reached_12h_boundary_n": reached_12h_n,
        "extended_to_18h_n": extended_n,
        "exited_at_12h_n": exited_at_12h_n,
        "post_12h_target_hits_n": post_12h_target_n,
        "post_12h_stop_hits_n": post_12h_stop_n,
        "post_12h_time_cap_18h_n": post_12h_time_cap_18h_n,
        "true_positive_extensions_n": true_positive_extensions_n,
        "false_extensions_n": false_extensions_n,
        "neutral_extensions_n": neutral_extensions_n,
        "missed_favorable_extensions_n": missed_favorable_extensions_n,
        "correctly_avoided_extensions_n": correctly_avoided_extensions_n,
        "mean_delta_vs_e0_all_events_bps": safe_mean(all_deltas_vs_e0),
        "mean_delta_vs_h1_all_events_bps": safe_mean(all_deltas_vs_h1),
        "mean_delta_vs_e0_on_extended_bps": safe_mean(extension_deltas_vs_e0),
        "mark_vs_last_at_12h_mean_optimism_bps": safe_mean(mark_vs_last_12h_bps),
        "mark_vs_last_at_12h_median_optimism_bps": safe_median(mark_vs_last_12h_bps),
        "right_tail_concentration": {
            "positive_delta_events_n": len(positive_deltas),
            "total_positive_gain_bps": total_positive_gain_bps,
            "top_1_trade_share_of_positive_gain": top1_share,
            "top_2_trades_share_of_positive_gain": top2_share,
            "top_3_trades_share_of_positive_gain": top3_share,
        },
        "underpowered_branch_split": underpowered_branch,
        "thin_evidence_flag": thin_extension_outcomes,
        "evidence_support_label": "THIN_EVIDENCE_UNDERPOWERED_BRANCH" if thin_extension_outcomes else "ADEQUATE_CELL_COUNT",
        "decisions_at_12h": decisions_table,
    }


def max_t_bootstrap(
    registry: list[tuple[str, list[dict[str, Any]]]],
    block_days: int,
    *,
    draws: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    """Shared UTC calendar block bootstrap with simultaneous centered two-sided max-|T|.

    Supports both the full 8-contrast joint family (2 candidates x 4 contrasts:
    X1-E0, X1-H1, X2-E0, X2-H1) and per-candidate 4-contrast families.
    """
    k = len(registry)
    if k not in (4, 8) or block_days not in (7, 14):
        raise ValueError(f"Expected 4 or 8 contrasts and block_days in (7, 14), got k={k}, block_days={block_days}")

    duration = block_days * 86_400_000
    blocks = (CALENDAR_END_MS - CALENDAR_START_MS + duration - 1) // duration
    sums = np.zeros((blocks, k), dtype=float)
    counts = np.zeros((blocks, k), dtype=int)

    for j, (_, rows) in enumerate(registry):
        for row in rows:
            at = int(row["entry_at"])
            value = float(row["delta_bps"])
            if not (CALENDAR_START_MS <= at < CALENDAR_END_MS) or not np.isfinite(value):
                raise ValueError("Invalid paired clock or non-finite delta_bps in bootstrap")
            i = (at - CALENDAR_START_MS) // duration
            sums[i, j] += value
            counts[i, j] += 1

    n = counts.sum(axis=0)
    if np.any(n == 0):
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "family_size": k,
            "block_days": block_days,
            "empty_contrasts": [registry[j][0] for j in np.where(n == 0)[0]],
        }

    center = sums.sum(axis=0) / n
    sample = np.random.default_rng(seed).integers(0, blocks, size=(draws, blocks))
    ns = counts[sample].sum(axis=1)
    ss = sums[sample].sum(axis=1)
    valid = np.all(ns > 0, axis=1)
    if int(valid.sum()) < int(draws * 0.99):
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "family_size": k,
            "block_days": block_days,
            "valid_draws": int(valid.sum()),
        }

    estimate = ss[valid] / ns[valid]
    se = estimate.std(axis=0, ddof=1)
    # Handle zero-variance contrast gracefully (e.g. if a conditional scheme happens to equal E0 or H1 everywhere)
    active_cols = se > 1e-12
    if not np.any(active_cols):
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "family_size": k,
            "block_days": block_days,
            "degenerate_contrasts": [registry[j][0] for j in range(k)],
        }

    null_t = np.zeros_like(estimate)
    null_t[:, active_cols] = (estimate[:, active_cols] - center[active_cols]) / se[active_cols]
    critical = float(np.quantile(np.max(np.abs(null_t), axis=1), 0.95))

    out = []
    for j, (name, _) in enumerate(registry):
        lcb = float(center[j] - critical * se[j])
        ucb = float(center[j] + critical * se[j])
        spans_zero = bool(lcb <= 0.0 <= ucb)
        out.append({
            "contrast": name,
            "qualified_n": int(n[j]),
            "mean_delta_bps": float(center[j]),
            "bootstrap_SE_bps": float(se[j]),
            "simultaneous_LCB_bps": lcb,
            "simultaneous_UCB_bps": ucb,
            "spans_zero": spans_zero,
            "nonempty_calendar_blocks": int(np.count_nonzero(counts[:, j])),
            "total_calendar_blocks": int(blocks),
            "zero_trade_blocks": int(np.count_nonzero(counts[:, j] == 0)),
        })

    return {
        "status": "MEASURED_CONDITIONAL_ON_EXPOSED_SELECTED_LEADS",
        "method": "centered two-sided max-|T|; fixed bootstrap SD studentizer",
        "family_size": k,
        "block_days": block_days,
        "draws": draws,
        "valid_joint_draws": int(valid.sum()),
        "seed": seed,
        "critical_95_maxT": critical,
        "contrasts": out,
        "all_intervals_span_zero": all(c["spans_zero"] for c in out),
        "cumulative_trial_disclosure": (
            "48 entry + 8 Goal A + 8 Exit R1 + 4 conditional exit = 68 exposed development configurations; "
            "no independent Alpha claim from 2021-2023 development data"
        ),
    }


def build_contrast_registry(
    paired_all: dict[tuple[str, str], list[dict[str, Any]]],
    candidate_ids: tuple[str, ...],
    cost_name: str,
) -> tuple[list[tuple[str, list[dict[str, Any]]]], list[dict[str, Any]]]:
    """Build 8-contrast registry and detailed decomposition table for a cost tier."""
    registry: list[tuple[str, list[dict[str, Any]]]] = []
    decomposition: list[dict[str, Any]] = []

    for cid in candidate_ids:
        pairs = paired_all[cid, cost_name]
        for new_scheme, ref_scheme in CONTRASTS:
            rows = []
            valid = []
            for p in pairs:
                if new_scheme not in p["cells"] or ref_scheme not in p["cells"]:
                    continue
                a = p["cells"][new_scheme]
                b = p["cells"][ref_scheme]
                rows.append({
                    "entry_at": int(p["entry_at"]),
                    "delta_bps": float(a["net_after_funding_bps"]) - float(b["net_after_funding_bps"]),
                })
                valid.append(p)
            name = f"{cid}:{new_scheme}-{ref_scheme}"
            registry.append((name, rows))
            deltas = [x["delta_bps"] for x in rows]
            decomposition.append({
                "contrast": name,
                "candidate": cid,
                "new_scheme": new_scheme,
                "reference_scheme": ref_scheme,
                "qualified_n": len(valid),
                "differing_events_n": sum(abs(d) > 1e-9 for d in deltas),
                "mean_delta_net_bps": safe_mean(deltas),
                "median_delta_net_bps": safe_median(deltas),
                "mean_delta_gross_bps": safe_mean(
                    [float(p["cells"][new_scheme]["gross_bps"]) - float(p["cells"][ref_scheme]["gross_bps"]) for p in valid]
                ),
                "mean_delta_funding_usdt": safe_mean(
                    [
                        float(p["cells"][new_scheme]["funding_cash_usdt"])
                        - float(p["cells"][ref_scheme]["funding_cash_usdt"])
                        for p in valid
                    ]
                ),
                "mean_delta_fees_usdt": safe_mean(
                    [
                        float(p["cells"][new_scheme]["fee_entry"])
                        + float(p["cells"][new_scheme]["fee_exit"])
                        - float(p["cells"][ref_scheme]["fee_entry"])
                        - float(p["cells"][ref_scheme]["fee_exit"])
                        for p in valid
                    ]
                ),
                "mean_delta_weighted_exit_minutes": safe_mean(
                    [
                        float(p["cells"][new_scheme]["weighted_exit_age_minutes"])
                        - float(p["cells"][ref_scheme]["weighted_exit_age_minutes"])
                        for p in valid
                    ]
                ),
                "year": {
                    str(y): safe_mean([
                        float(p["cells"][new_scheme]["net_after_funding_bps"])
                        - float(p["cells"][ref_scheme]["net_after_funding_bps"])
                        for p in valid
                        if datetime.fromtimestamp(int(p["entry_at"]) / 1000, UTC).year == y
                    ])
                    for y in (2021, 2022, 2023)
                },
                "side": {
                    str(sign): safe_mean([
                        float(p["cells"][new_scheme]["net_after_funding_bps"])
                        - float(p["cells"][ref_scheme]["net_after_funding_bps"])
                        for p in valid
                        if int(p["side"]) == sign
                    ])
                    for sign in (-1, 1)
                },
            })
    return registry, decomposition
