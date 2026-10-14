"""Statistical metrics, annual breakdown, block bootstrapping, and simultaneous max-|T| intervals.

Computes:
- Fixed-event equal notional returns (1,000 USDT notional per trade)
- Account-level PnL, cash curve, and max MTM drawdown
- Annual performance: 2021 (Feb-Dec), 2022, 2023, and full 35-month development
- Profit factor (PF), win rate, gross return, fee drag, and signed funding attribution
- 7-day and 14-day calendar block bootstrapping with simultaneous max-|T| intervals across all 6 comparisons
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

BOOTSTRAP_ROUNDS = 2000
BOOTSTRAP_SEED = 20261012


def compute_trade_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate summary statistics for a collection of executed trades."""
    n = len(trades)
    if n == 0:
        return {
            "n": 0,
            "win_rate_pct": 0.0,
            "mean_net_bps": 0.0,
            "sum_net_bps": 0.0,
            "std_net_bps": 0.0,
            "t_stat": 0.0,
            "profit_factor": 0.0,
            "total_gross_usdt": 0.0,
            "total_fee_usdt": 0.0,
            "total_funding_usdt": 0.0,
            "total_net_usdt": 0.0,
        }

    net_bps = np.array([float(t["net_after_funding_bps"]) for t in trades], dtype=np.float64)
    gross_usdt = np.array([float(t["gross_usdt"]) for t in trades], dtype=np.float64)
    fee_usdt = np.array([float(t["fee_entry"]) + float(t["fee_exit"]) for t in trades], dtype=np.float64)
    funding_usdt = np.array([float(t["funding_usdt"]) for t in trades], dtype=np.float64)
    net_usdt = np.array([float(t["net_after_funding_usdt"]) for t in trades], dtype=np.float64)

    wins = np.sum(net_bps > 0)
    win_rate = (wins / n) * 100.0

    mean_net = float(np.mean(net_bps))
    sum_net = float(np.sum(net_bps))
    std_net = float(np.std(net_bps, ddof=1)) if n > 1 else 0.0
    se = std_net / math.sqrt(n) if n > 1 and std_net > 0 else 0.0
    t_stat = mean_net / se if se > 0 else 0.0

    pos_usdt = np.sum(net_usdt[net_usdt > 0])
    neg_usdt = np.abs(np.sum(net_usdt[net_usdt < 0]))
    pf = float(pos_usdt / neg_usdt) if neg_usdt > 0 else (999.0 if pos_usdt > 0 else 0.0)

    return {
        "n": n,
        "win_rate_pct": win_rate,
        "mean_net_bps": mean_net,
        "sum_net_bps": sum_net,
        "std_net_bps": std_net,
        "t_stat": t_stat,
        "profit_factor": pf,
        "total_gross_usdt": float(np.sum(gross_usdt)),
        "total_fee_usdt": float(np.sum(fee_usdt)),
        "total_funding_usdt": float(np.sum(funding_usdt)),
        "total_net_usdt": float(np.sum(net_usdt)),
    }


def compute_annual_breakdown(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Breakdown trade metrics by year and full period."""
    years = [2021, 2022, 2023]
    result: dict[str, Any] = {}

    for y in years:
        y_trades = [t for t in trades if t.get("fold", "").startswith(str(y))]
        result[str(y)] = compute_trade_metrics(y_trades)

    result["FULL_35M"] = compute_trade_metrics(trades)
    return result


def compute_block_bootstrap_max_t(
    candidate_trade_series: dict[str, list[dict[str, Any]]],
    eval_start_ms: int,
    eval_end_ms: int,
    block_days: int = 14,
    n_rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Calibrate simultaneous max-|T| intervals across all candidate series via calendar block resampling."""
    block_ms = block_days * 86_400_000
    n_blocks = math.ceil((eval_end_ms - eval_start_ms) / block_ms)

    # Map trades for each candidate into time blocks
    cand_names = sorted(candidate_trade_series.keys())
    cand_block_returns: dict[str, np.ndarray] = {}

    for name in cand_names:
        trades = candidate_trade_series[name]
        block_sums = np.zeros(n_blocks, dtype=np.float64)
        block_counts = np.zeros(n_blocks, dtype=np.int64)

        for t in trades:
            b_idx = int((t["entry_at"] - eval_start_ms) // block_ms)
            if 0 <= b_idx < n_blocks:
                block_sums[b_idx] += float(t["net_after_funding_bps"])
                block_counts[b_idx] += 1

        cand_block_returns[name] = block_sums

    # Compute baseline block sample means and standard errors
    baseline_stats = {}
    for name in cand_names:
        series = cand_block_returns[name]
        m = float(np.mean(series))
        s = float(np.std(series, ddof=1)) if len(series) > 1 else 0.0
        se = s / math.sqrt(n_blocks) if s > 0 else 1e-6
        baseline_stats[name] = {"mean": m, "std": s, "se": se}

    # Deterministic block bootstrapping
    rng = np.random.default_rng(seed)
    max_t_values = np.empty(n_rounds, dtype=np.float64)

    for b in range(n_rounds):
        indices = rng.integers(0, n_blocks, size=n_blocks)
        max_abs_t = 0.0

        for name in cand_names:
            boot_sample = cand_block_returns[name][indices]
            b_mean = np.mean(boot_sample)
            b_se = np.std(boot_sample, ddof=1) / math.sqrt(n_blocks) if len(boot_sample) > 1 else 1e-6
            b_se = max(b_se, 1e-6)

            t_val = abs((b_mean - baseline_stats[name]["mean"]) / b_se)
            max_abs_t = max(max_abs_t, t_val)

        max_t_values[b] = max_abs_t

    q95 = float(np.percentile(max_t_values, 95.0))
    q99 = float(np.percentile(max_t_values, 99.0))

    # Form simultaneous intervals
    intervals = {}
    for name in cand_names:
        m = baseline_stats[name]["mean"]
        se = baseline_stats[name]["se"]
        ci_lower = m - q95 * se
        ci_upper = m + q95 * se
        spans_zero = bool(ci_lower <= 0 <= ci_upper)
        intervals[name] = {
            "mean_block_net_bps": m,
            "block_se": se,
            "q95_critical_value": q95,
            "simultaneous_ci_95": [float(ci_lower), float(ci_upper)],
            "spans_zero": spans_zero,
            "statistical_support": "SUPPORTED" if not spans_zero and m > 0 else "INSUFFICIENT_SUPPORT",
        }

    return {
        "block_days": block_days,
        "n_blocks": n_blocks,
        "n_rounds": n_rounds,
        "q95_max_t": q95,
        "q99_max_t": q99,
        "intervals": intervals,
    }
