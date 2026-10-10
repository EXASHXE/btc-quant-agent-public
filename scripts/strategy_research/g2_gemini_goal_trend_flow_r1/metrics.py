"""Statistical metrics, block bootstrap, and strict promotion gate evaluation."""
from __future__ import annotations

from collections import defaultdict
import numpy as np


def compute_drawdown(equity_curve: list[float]) -> float:
    """Compute maximum drawdown percentage from an equity curve."""
    if not equity_curve or len(equity_curve) < 2:
        return 0.0
    arr = np.array(equity_curve, dtype=np.float64)
    peaks = np.maximum.accumulate(arr)
    dd = (peaks - arr) / np.maximum(peaks, 1e-6)
    return float(np.max(dd) * 100.0)


def calculate_candidate_metrics(trades: list[dict], cost_name: str) -> dict:
    """Calculate descriptive performance metrics for a candidate."""
    n = len(trades)
    if n == 0:
        return {
            "cost_model": cost_name,
            "trade_count": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "mean_gross_bps": 0.0,
            "median_gross_bps": 0.0,
            "mean_net_bps": 0.0,
            "median_net_bps": 0.0,
            "equal_year_net_bps": 0.0,
            "worst_year_net_bps": 0.0,
            "years_covered": 0,
            "months_covered": 0,
            "max_mtm_drawdown_pct": 0.0,
            "mean_duration_minutes": 0.0,
            "exit_reasons": {},
            "yearly_breakdown": {},
        }

    gross_bps = np.array([t["gross_bps"] for t in trades], dtype=np.float64)
    net_bps = np.array([t["net_bps"] for t in trades], dtype=np.float64)
    net_usdts = np.array([t["net_usdt"] for t in trades], dtype=np.float64)
    gross_usdts = np.array([t["gross_usdt"] for t in trades], dtype=np.float64)

    wins = net_usdts > 0
    win_rate = float(np.mean(wins) * 100.0)

    gross_wins = np.sum(gross_usdts[gross_usdts > 0])
    gross_losses = abs(np.sum(gross_usdts[gross_usdts < 0]))
    pf = float(gross_wins / max(gross_losses, 1e-6))

    # Equity curve
    curve = [1000.0]
    eq = 1000.0
    for u in net_usdts:
        eq += u
        curve.append(eq)
    max_dd = compute_drawdown(curve)

    # Breakdown by calendar year and month
    by_year = defaultdict(list)
    by_month = set()
    exit_reasons = defaultdict(int)
    durations = []

    for t in trades:
        entry_at = t["entry_at"]
        dt = np.datetime64(int(entry_at), "ms").astype("datetime64[s]").item()
        y = dt.year
        m = dt.month
        by_year[y].append(t["net_bps"])
        by_month.add((y, m))
        exit_reasons[t["exit_reason"]] += 1
        durations.append(t["duration_minutes"])

    yearly_breakdown = {}
    yearly_means = []
    for y in sorted(by_year.keys()):
        bps_list = by_year[y]
        m_net = float(np.mean(bps_list))
        yearly_means.append(m_net)
        yearly_breakdown[y] = {
            "n_trades": len(bps_list),
            "mean_net_bps": m_net,
        }

    equal_year_net = float(np.mean(yearly_means)) if yearly_means else 0.0
    worst_year_net = float(np.min(yearly_means)) if yearly_means else 0.0

    return {
        "cost_model": cost_name,
        "trade_count": n,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "mean_gross_bps": float(np.mean(gross_bps)),
        "median_gross_bps": float(np.median(gross_bps)),
        "mean_net_bps": float(np.mean(net_bps)),
        "median_net_bps": float(np.median(net_bps)),
        "equal_year_net_bps": equal_year_net,
        "worst_year_net_bps": worst_year_net,
        "years_covered": len(by_year),
        "months_covered": len(by_month),
        "max_mtm_drawdown_pct": max_dd,
        "mean_duration_minutes": float(np.mean(durations)) if durations else 0.0,
        "exit_reasons": dict(exit_reasons),
        "yearly_breakdown": yearly_breakdown,
    }


def block_bootstrap(
    trades: list[dict], block_days: int = 7, n_iter: int = 10000, seed: int = 42
) -> dict:
    """Weekly/14-day block bootstrap resampling of trade net bps."""
    if len(trades) < 5:
        return {
            "mean": 0.0,
            "median": 0.0,
            "ci_95_lower": 0.0,
            "ci_95_upper": 0.0,
            "lcb_95": 0.0,
            "block_count": 0,
        }

    # Group trades into time blocks
    block_ms = block_days * 86400 * 1000
    trades_sorted = sorted(trades, key=lambda t: t["entry_at"])
    t_min = trades_sorted[0]["entry_at"]

    blocks = defaultdict(list)
    for t in trades_sorted:
        b_idx = (t["entry_at"] - t_min) // block_ms
        blocks[b_idx].append(t["net_bps"])

    block_keys = list(blocks.keys())
    n_blocks = len(block_keys)
    if n_blocks < 2:
        return {
            "mean": float(np.mean([t["net_bps"] for t in trades])),
            "median": float(np.median([t["net_bps"] for t in trades])),
            "ci_95_lower": 0.0,
            "ci_95_upper": 0.0,
            "lcb_95": 0.0,
            "block_count": n_blocks,
        }

    rng = np.random.default_rng(seed)
    block_arrs = [np.array(blocks[k], dtype=np.float64) for k in block_keys]

    resampled_means = np.empty(n_iter, dtype=np.float64)
    for i in range(n_iter):
        chosen_indices = rng.integers(0, n_blocks, size=n_blocks)
        sampled_trades = np.concatenate([block_arrs[idx] for idx in chosen_indices])
        resampled_means[i] = np.mean(sampled_trades)

    ci_lower = float(np.percentile(resampled_means, 2.5))
    ci_upper = float(np.percentile(resampled_means, 97.5))
    lcb = float(np.percentile(resampled_means, 5.0))

    return {
        "mean": float(np.mean(resampled_means)),
        "median": float(np.median(resampled_means)),
        "ci_95_lower": ci_lower,
        "ci_95_upper": ci_upper,
        "lcb_95": lcb,
        "block_count": n_blocks,
    }


def evaluate_promotion_gate(stress_metrics: dict, bootstrap_res: dict) -> dict:
    """Evaluate 7 strict promotion criteria under STRESS cost model."""
    n = stress_metrics["trade_count"]
    years = stress_metrics["years_covered"]
    months = stress_metrics["months_covered"]
    equal_yr_net = stress_metrics["equal_year_net_bps"]
    pf = stress_metrics["profit_factor"]
    worst_yr_net = stress_metrics["worst_year_net_bps"]
    max_dd = stress_metrics["max_mtm_drawdown_pct"]
    lcb = bootstrap_res.get("lcb_95", -999.0)

    g1_n = n >= 100
    g2_breadth = (years >= 2) and (months >= 6)
    g3_equal_yr = equal_yr_net > 0.0
    g4_pf = pf >= 1.15
    g5_worst_yr = worst_yr_net >= -10.0
    g6_dd = max_dd <= 12.0
    g7_bootstrap = lcb > 0.0

    all_pass = g1_n and g2_breadth and g3_equal_yr and g4_pf and g5_worst_yr and g6_dd and g7_bootstrap

    return {
        "gates": {
            "G1_sample_size_ge_100": {"passed": g1_n, "value": n, "threshold": 100},
            "G2_temporal_breadth": {"passed": g2_breadth, "years": years, "months": months},
            "G3_equal_year_net_gt_0": {"passed": g3_equal_yr, "value": equal_yr_net, "threshold": 0.0},
            "G4_profit_factor_ge_115": {"passed": g4_pf, "value": pf, "threshold": 1.15},
            "G5_worst_year_net_ge_neg10": {"passed": g5_worst_yr, "value": worst_yr_net, "threshold": -10.0},
            "G6_max_drawdown_le_12pct": {"passed": g6_dd, "value": max_dd, "threshold": 12.0},
            "G7_bootstrap_lcb_gt_0": {"passed": g7_bootstrap, "value": lcb, "threshold": 0.0},
        },
        "all_passed": all_pass,
        "verdict": (
            "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"
            if all_pass
            else "FALSIFIED_DEV_CANDIDATE"
        ),
    }
