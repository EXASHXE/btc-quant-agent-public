"""Descriptive statistics, multi-year block bootstrap, and promotion gate checks."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.metrics import (
    DAY,
    MONDAY_ORIGIN,
    describe,
    drawdown,
    possible_settlements,
)


def describe_extended(trades: list[dict[str, Any]]) -> dict[str, Any]:
    base = describe(trades)
    long_n = sum(1 for t in trades if t["side"] > 0)
    short_n = sum(1 for t in trades if t["side"] < 0)
    base["long_trades"] = long_n
    base["short_trades"] = short_n
    base["mean_hold_minutes"] = (
        float(np.mean([t["duration_minutes"] for t in trades])) if trades else None
    )
    base["median_hold_minutes"] = (
        float(np.median([t["duration_minutes"] for t in trades])) if trades else None
    )
    base["mean_incremental_vs_balanced_bps"] = (
        float(np.mean([t["incremental_vs_balanced_bps"] for t in trades]))
        if trades and "incremental_vs_balanced_bps" in trades[0]
        else None
    )
    base["median_incremental_vs_balanced_bps"] = (
        float(np.median([t["incremental_vs_balanced_bps"] for t in trades]))
        if trades and "incremental_vs_balanced_bps" in trades[0]
        else None
    )
    return base


def summarize_by_year(
    trades: list[dict[str, Any]], monthly_folds: list[dict[str, Any]]
) -> dict[str, Any]:
    years = sorted({int(f["year"]) for f in monthly_folds})
    annual: dict[str, dict[str, Any]] = {}
    for y in years:
        y_trades = [t for t in trades if int(t.get("year", 0)) == y]
        annual[str(y)] = describe_extended(y_trades)

    populated_years = [y for y in years if annual[str(y)]["trades"] > 0]
    distinct_months = len({(int(t["year"]), int(t["month"])) for t in trades})

    if len(populated_years) >= 1:
        pop_means = [float(annual[str(y)]["mean_net_bps"]) for y in populated_years]
        pop_inc = [
            float(annual[str(y)]["mean_incremental_vs_balanced_bps"])
            for y in populated_years
            if annual[str(y)]["mean_incremental_vs_balanced_bps"] is not None
        ]
        equal_pop_year_mean = float(np.mean(pop_means))
        equal_pop_year_inc = float(np.mean(pop_inc)) if pop_inc else None
        worst_pop_year_mean = float(np.min(pop_means))
    else:
        equal_pop_year_mean = None
        equal_pop_year_inc = None
        worst_pop_year_mean = None

    if len(populated_years) == len(years) and len(years) > 0:
        equal_all_3y_mean = equal_pop_year_mean
        equal_all_3y_inc = equal_pop_year_inc
        worst_all_3y_mean = worst_pop_year_mean
    else:
        equal_all_3y_mean = None
        equal_all_3y_inc = None
        worst_all_3y_mean = None

    return {
        "annual": annual,
        "populated_years": populated_years,
        "distinct_years_count": len(populated_years),
        "distinct_months_count": distinct_months,
        "equal_populated_year_mean_net_bps": equal_pop_year_mean,
        "equal_populated_year_incremental_bps": equal_pop_year_inc,
        "worst_populated_year_mean_net_bps": worst_pop_year_mean,
        "equal_3year_mean_net_bps": equal_all_3y_mean,
        "equal_3year_incremental_bps": equal_all_3y_inc,
        "worst_3year_mean_net_bps": worst_all_3y_mean,
    }


def block_bootstrap_2021_2023(
    trades: list[dict[str, Any]],
    monthly_folds: list[dict[str, Any]],
    *,
    seed: int = 20261011,
    resamples: int = 10_000,
    block_days: int = 7,
    combined_comparisons: int = 48,
) -> dict[str, Any]:
    """Calendar block bootstrap across populated years (2021-2023) with 48-trial adjustment.

    Includes all calendar blocks (including zero-trade blocks) within the scored months
    of each populated year. Requires >=2 populated years; otherwise returns INSUFFICIENT_SUPPORT.
    """
    years = sorted({int(f["year"]) for f in monthly_folds})
    populated_years = [
        y for y in years if any(int(t.get("year", 0)) == y for t in trades)
    ]
    if len(populated_years) < 2:
        return {
            "status": "INSUFFICIENT_YEAR_SUPPORT_LT_2",
            "block_days": block_days,
            "populated_years": populated_years,
            "equal_year_net_bps": None,
            "equal_year_incremental_bps": None,
            "net_ci95": None,
            "incremental_ci95": None,
            "unadjusted_net_LCB95_bps": None,
            "adjusted_48_net_LCB_bps": None,
            "adjusted_48_incremental_LCB_bps": None,
            "adjusted_96_net_LCB_bps": None,
            "adjusted_96_incremental_LCB_bps": None,
        }

    rng = np.random.default_rng(seed)
    bootstrap = np.zeros((resamples, 2), dtype=np.float64)
    undefined = np.zeros(resamples, dtype=bool)
    year_means: list[np.ndarray] = []
    frames: list[dict[str, Any]] = []
    width = block_days * DAY

    for y in populated_years:
        y_folds = [f for f in monthly_folds if int(f["year"]) == y]
        y_start = min(int(f["start_ms"]) for f in y_folds)
        y_end = max(int(f["end_ms"]) for f in y_folds)
        origin = MONDAY_ORIGIN if block_days == 7 else y_start
        first_blk = (y_start - origin) // width
        last_blk = (y_end - 1 - origin) // width
        n_blocks = int(last_blk - first_blk + 1)
        counts = np.zeros(n_blocks, dtype=np.float64)
        sums = np.zeros((n_blocks, 2), dtype=np.float64)
        y_trades = [t for t in trades if int(t.get("year", 0)) == y]
        for t in y_trades:
            k = int((int(t["entry_at"]) - origin) // width - first_blk)
            if 0 <= k < n_blocks:
                counts[k] += 1.0
                sums[k, 0] += float(t["net_bps"])
                sums[k, 1] += float(t["incremental_vs_balanced_bps"])
        frames.append(
            {
                "year": y,
                "calendar_blocks": n_blocks,
                "nonempty_blocks": int(np.sum(counts > 0)),
                "trades": len(y_trades),
            }
        )
        year_means.append(sums.sum(axis=0) / counts.sum())
        idx = rng.integers(0, n_blocks, size=(resamples, n_blocks))
        sampled_n = counts[idx].sum(axis=1)
        undefined |= sampled_n == 0
        bootstrap += (
            np.divide(
                sums[idx].sum(axis=1),
                sampled_n[:, None],
                out=np.zeros((resamples, 2), dtype=np.float64),
                where=sampled_n[:, None] > 0,
            )
            / len(populated_years)
        )

    bootstrap[undefined] = -np.inf

    def quantile(column: np.ndarray, q: float) -> float | None:
        pos = max(0, min(resamples - 1, math.floor(q * resamples)))
        val = float(np.sort(column)[pos])
        return val if math.isfinite(val) else None

    q_unadj = 0.05
    q_48 = 0.05 / float(combined_comparisons)
    q_96 = 0.05 / float(combined_comparisons * 2)
    mean_vec = np.mean(year_means, axis=0)

    return {
        "status": "FINITE_FIXED_BLOCK_BOOTSTRAP",
        "seed": seed,
        "resamples": resamples,
        "block_days": block_days,
        "populated_years": populated_years,
        "calendar_frames": frames,
        "undefined_sample_fraction": float(undefined.mean()),
        "equal_year_net_bps": float(mean_vec[0]),
        "equal_year_incremental_bps": float(mean_vec[1]),
        "net_ci95": [quantile(bootstrap[:, 0], 0.025), quantile(bootstrap[:, 0], 0.975)],
        "incremental_ci95": [quantile(bootstrap[:, 1], 0.025), quantile(bootstrap[:, 1], 0.975)],
        "unadjusted_net_LCB95_bps": quantile(bootstrap[:, 0], q_unadj),
        "unadjusted_incremental_LCB95_bps": quantile(bootstrap[:, 1], q_unadj),
        "adjusted_48_net_LCB_bps": quantile(bootstrap[:, 0], q_48),
        "adjusted_48_incremental_LCB_bps": quantile(bootstrap[:, 1], q_48),
        "adjusted_96_net_LCB_bps": quantile(bootstrap[:, 0], q_96),
        "adjusted_96_incremental_LCB_bps": quantile(bootstrap[:, 1], q_96),
        "familywise_comparisons": combined_comparisons,
        "one_sided_q_48": q_48,
        "one_sided_q_96": q_96,
    }


def evaluate_promotion_gate(summary: dict[str, Any]) -> tuple[list[str], str]:
    """Evaluate all development promotion gates on a STRESS candidate summary."""
    failures: list[str] = []
    n_trades = int(summary.get("trades", 0))
    y_info = summary["annual_summary"]
    n_years = int(y_info["distinct_years_count"])
    n_months = int(y_info["distinct_months_count"])
    eq_mean = y_info["equal_populated_year_mean_net_bps"]
    eq_inc = y_info["equal_populated_year_incremental_bps"]
    worst_yr = y_info["worst_populated_year_mean_net_bps"]
    pf = summary.get("profit_factor")
    mtm_dd = float(summary.get("continuous_1x_dense_MTM_drawdown_pct", 0.0))
    close_dd = float(summary.get("continuous_1x_trade_close_drawdown_pct", 0.0))

    if n_trades < 100:
        failures.append("INSUFFICIENT_TOTAL_TRADES_LT_100")
    if n_years < 2:
        failures.append("INSUFFICIENT_DISTINCT_YEARS_LT_2")
    if n_months < 6:
        failures.append("INSUFFICIENT_DISTINCT_MONTHS_LT_6")
    if eq_mean is None or eq_mean <= 0.0:
        failures.append("NONPOSITIVE_EQUAL_YEAR_STRESS_MEAN")
    if eq_inc is None or eq_inc <= 0.0:
        failures.append("NONPOSITIVE_EQUAL_YEAR_INCREMENTAL_VS_CONTROL")
    if pf is None or pf < 1.15:
        failures.append("STRESS_PROFIT_FACTOR_LT_1_15")
    if worst_yr is None or worst_yr < -10.0:
        failures.append("WORST_YEAR_MEAN_BELOW_MINUS_10BPS")
    if mtm_dd > 12.0 or close_dd > 12.0:
        failures.append("ACCOUNT_1X_DRAWDOWN_GT_12PCT")

    w7 = summary["weekly_bootstrap"]
    w14 = summary["two_week_bootstrap"]
    for label, ci in (("WEEK_7D", w7), ("BLOCK_14D", w14)):
        if ci.get("adjusted_48_net_LCB_bps") is None or ci["adjusted_48_net_LCB_bps"] <= 0.0:
            failures.append(f"{label}_ADJUSTED_48_NET_LCB_NONPOSITIVE")
        if (
            ci.get("adjusted_48_incremental_LCB_bps") is None
            or ci["adjusted_48_incremental_LCB_bps"] <= 0.0
        ):
            failures.append(f"{label}_ADJUSTED_48_INCREMENTAL_LCB_NONPOSITIVE")

    if not failures:
        status = "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"
    elif n_trades == 0:
        status = "UNSUPPORTED_ZERO_TRADES"
    elif (
        eq_mean is not None
        and eq_mean > 0.0
        and eq_inc is not None
        and eq_inc > 0.0
        and n_trades >= 30
    ):
        status = "WEAK_DEV_LEAD_NOT_READY_FOR_HOLDOUT"
    else:
        status = "FALSIFIED_DEV_CANDIDATE"
    return failures, status


__all__ = [
    "DAY",
    "MONDAY_ORIGIN",
    "block_bootstrap_2021_2023",
    "describe",
    "describe_extended",
    "drawdown",
    "evaluate_promotion_gate",
    "possible_settlements",
    "summarize_by_year",
]
