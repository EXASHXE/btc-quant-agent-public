"""Analysis 1: Baseline time-cap censored vs early-exit path and mechanism analysis."""
from __future__ import annotations

from typing import Any

import numpy as np


def analyze_time_cap_strata(paired_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze baseline TIME_CAP vs early STOP/TARGET baseline strata."""
    time_caps = [e for e in paired_events if e.get("baseline_time_cap")]
    early_exits = [e for e in paired_events if not e.get("baseline_time_cap")]

    # 1. Early exit integrity check: H1 and H2 must be identical to E0
    early_exit_diffs = []
    for e in early_exits:
        e0 = e["cells"]["E0"]
        h1 = e["cells"]["H1"]
        h2 = e["cells"]["H2"]
        if (
            e0["exit_at"] != h1["exit_at"]
            or e0["exit_at"] != h2["exit_at"]
            or abs(float(e0["net_after_funding_bps"]) - float(h1["net_after_funding_bps"])) > 1e-6
            or abs(float(e0["net_after_funding_bps"]) - float(h2["net_after_funding_bps"])) > 1e-6
        ):
            early_exit_diffs.append(e["event_id"])

    assert len(early_exit_diffs) == 0, f"Early exit mutation detected in {len(early_exit_diffs)} events"

    # 2. Trace 12->18h (E0 -> H1) for TIME_CAP cohort
    h1_deltas_net = []
    h1_deltas_gross = []
    h1_deltas_funding = []
    h1_deltas_fee = []
    h1_fates = {"TIME_CAP": 0, "TARGET": 0, "STOP": 0}

    # By-fate delta tracking
    h1_fate_deltas: dict[str, list[float]] = {"TIME_CAP": [], "TARGET": [], "STOP": []}

    for e in time_caps:
        e0 = e["cells"]["E0"]
        h1 = e["cells"]["H1"]
        fate = h1["exit_reason"]
        h1_fates[fate] = h1_fates.get(fate, 0) + 1

        d_net = float(h1["net_after_funding_bps"]) - float(e0["net_after_funding_bps"])
        d_gross = float(h1["gross_bps"]) - float(e0["gross_bps"])
        d_fund = float(h1["funding_cash_usdt"]) - float(e0["funding_cash_usdt"])
        d_fee = float(h1["fee_exit"]) - float(e0["fee_exit"])

        h1_deltas_net.append(d_net)
        h1_deltas_gross.append(d_gross)
        h1_deltas_funding.append(d_fund)
        h1_deltas_fee.append(d_fee)
        h1_fate_deltas.setdefault(fate, []).append(d_net)

    n_tc = len(time_caps)
    h1_fav_count = sum(d > 0 for d in h1_deltas_net)
    h1_adv_count = sum(d < 0 for d in h1_deltas_net)
    h1_flat_count = sum(d == 0 for d in h1_deltas_net)

    # 3. Trace 18->24h (H1 -> H2) for TIME_CAP cohort
    h2_deltas_net = []
    h2_fates = {"TIME_CAP": 0, "TARGET": 0, "STOP": 0}
    transitions: list[dict[str, Any]] = []
    extra_stops_18_24 = 0
    extra_targets_18_24 = 0

    for e in time_caps:
        h1 = e["cells"]["H1"]
        h2 = e["cells"]["H2"]
        fate1 = h1["exit_reason"]
        fate2 = h2["exit_reason"]
        h2_fates[fate2] = h2_fates.get(fate2, 0) + 1

        d_net = float(h2["net_after_funding_bps"]) - float(h1["net_after_funding_bps"])
        h2_deltas_net.append(d_net)

        if fate2 == "STOP" and fate1 != "STOP":
            extra_stops_18_24 += 1
        if fate2 == "TARGET" and fate1 != "TARGET":
            extra_targets_18_24 += 1

        transitions.append({
            "event_id": e["event_id"],
            "h1_fate": fate1,
            "h2_fate": fate2,
            "delta_h2_h1_bps": d_net,
        })

    h2_fav_count = sum(d > 0 for d in h2_deltas_net)
    h2_adv_count = sum(d < 0 for d in h2_deltas_net)

    # 4. Outlier & Concentration analysis for 12->18h
    sorted_h1_deltas = sorted(h1_deltas_net, reverse=True)
    total_h1_sum = sum(h1_deltas_net)
    top1_share = (sorted_h1_deltas[0] / total_h1_sum) if total_h1_sum > 0 else 0.0
    top3_share = (sum(sorted_h1_deltas[:3]) / total_h1_sum) if total_h1_sum > 0 else 0.0
    mean_without_top1 = (sum(sorted_h1_deltas[1:]) / (n_tc - 1)) if n_tc > 1 else 0.0

    # 5. Extract MFE / MAE summaries from path24h
    path_stats: dict[str, Any] = {}
    for window in ("before12h", "12to18h", "18to24h"):
        last_mfe = [e["path24h"][window]["Last_MFE_R"] for e in time_caps if window in e.get("path24h", {})]
        last_mae = [e["path24h"][window]["Last_MAE_R"] for e in time_caps if window in e.get("path24h", {})]
        mark_mfe = [e["path24h"][window]["Mark_MFE_R"] for e in time_caps if window in e.get("path24h", {})]
        mark_mae = [e["path24h"][window]["Mark_MAE_R"] for e in time_caps if window in e.get("path24h", {})]
        path_stats[window] = {
            "mean_Last_MFE_R": float(np.mean(last_mfe)) if last_mfe else 0.0,
            "mean_Last_MAE_R": float(np.mean(last_mae)) if last_mae else 0.0,
            "mean_Mark_MFE_R": float(np.mean(mark_mfe)) if mark_mfe else 0.0,
            "mean_Mark_MAE_R": float(np.mean(mark_mae)) if mark_mae else 0.0,
        }

    return {
        "total_events": len(paired_events),
        "early_exit_count": len(early_exits),
        "time_cap_count": n_tc,
        "early_exit_mutation_count": len(early_exit_diffs),
        "h1_12to18h": {
            "mean_delta_net_bps": float(np.mean(h1_deltas_net)) if h1_deltas_net else 0.0,
            "median_delta_net_bps": float(np.median(h1_deltas_net)) if h1_deltas_net else 0.0,
            "sum_delta_net_bps": float(total_h1_sum),
            "mean_delta_gross_bps": float(np.mean(h1_deltas_gross)) if h1_deltas_gross else 0.0,
            "total_delta_funding_usdt": float(sum(h1_deltas_funding)),
            "total_delta_exit_fee_usdt": float(sum(h1_deltas_fee)),
            "favorable_continuation_count": h1_fav_count,
            "adverse_reversal_count": h1_adv_count,
            "flat_count": h1_flat_count,
            "favorable_fraction": (h1_fav_count / n_tc) if n_tc else 0.0,
            "adverse_fraction": (h1_adv_count / n_tc) if n_tc else 0.0,
            "fates": h1_fates,
            "fate_breakdown": {
                f: {
                    "count": len(vals),
                    "mean_delta_net_bps": float(np.mean(vals)) if vals else 0.0,
                    "sum_delta_net_bps": float(sum(vals)),
                    "share_of_total_delta_pct": (sum(vals) / total_h1_sum * 100) if abs(total_h1_sum) > 1e-6 else 0.0,
                }
                for f, vals in h1_fate_deltas.items()
            },
            "concentration": {
                "top1_delta_bps": sorted_h1_deltas[0] if sorted_h1_deltas else 0.0,
                "top1_share_pct": float(top1_share * 100),
                "top3_share_pct": float(top3_share * 100),
                "mean_without_top1_bps": float(mean_without_top1),
            },
        },
        "h2_18to24h": {
            "mean_delta_net_bps": float(np.mean(h2_deltas_net)) if h2_deltas_net else 0.0,
            "median_delta_net_bps": float(np.median(h2_deltas_net)) if h2_deltas_net else 0.0,
            "sum_delta_net_bps": float(sum(h2_deltas_net)),
            "favorable_count": h2_fav_count,
            "adverse_count": h2_adv_count,
            "fates": h2_fates,
            "extra_stops_in_18to24h": extra_stops_18_24,
            "extra_targets_in_18to24h": extra_targets_18_24,
            "transitions": transitions,
        },
        "path_features": path_stats,
    }
