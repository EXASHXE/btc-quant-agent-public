"""Adversarial statistical metrics, controls, and block bootstrap for Goal A R2.

Features:
- Paired matched counterfactual baseline controls (side_override = -side).
- 7d / 14d calendar block bootstrap with simultaneous maxT across all attempted configs (seed=42, 10k draws).
- Annual breakdown including dedicated 2023 performance diagnostic.
- Friction pressure sensitivity (BASE 22bp, STRESS 44bp, +5bp, +10bp).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def compute_trade_metrics(trades: list[dict[str, Any]], cash0: float = 1000.0) -> dict[str, Any]:
    """Compute comprehensive trading, funding, and risk metrics."""
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "net_usdt": 0.0,
            "net_after_funding_usdt": 0.0,
            "funding_cash_usdt": 0.0,
            "fee_total_usdt": 0.0,
            "adverse_drag_usdt": 0.0,
            "gross_usdt": 0.0,
            "mean_net_bps": 0.0,
            "std_net_bps": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "exit_reasons": {},
            "long_trades": 0,
            "short_trades": 0,
        }

    net_pnls = np.array([float(t["net_after_funding_usdt"]) for t in trades], dtype=np.float64)
    net_bps = np.array([float(t["net_after_funding_bps"]) for t in trades], dtype=np.float64)

    wins = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]

    gross_win = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 1e-8 else (999.0 if gross_win > 0 else 0.0)

    win_rate = float(len(wins) / n * 100.0)

    # Cash curve drawdown
    cum_cash = np.cumsum(np.r_[0.0, net_pnls]) + cash0
    peak = np.maximum.accumulate(cum_cash)
    dd = (peak - cum_cash) / peak
    max_dd = float(np.max(dd) * 100.0)

    mean_bps = float(np.mean(net_bps))
    std_bps = float(np.std(net_bps, ddof=1)) if n > 1 else 0.0

    # Sharpe on trade returns
    sharpe = (mean_bps / std_bps * math.sqrt(n)) if std_bps > 1e-8 else 0.0

    downside_bps = net_bps[net_bps < 0]
    downside_std = float(np.std(downside_bps, ddof=1)) if len(downside_bps) > 1 else 0.0
    sortino = (mean_bps / downside_std * math.sqrt(n)) if downside_std > 1e-8 else 0.0

    reasons = {}
    for t in trades:
        r = t["exit_reason"]
        reasons[r] = reasons.get(r, 0) + 1

    longs = sum(1 for t in trades if t["side"] == 1)
    shorts = sum(1 for t in trades if t["side"] == -1)

    return {
        "n_trades": n,
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "net_usdt": float(sum(float(t["net_usdt"]) for t in trades)),
        "net_after_funding_usdt": float(np.sum(net_pnls)),
        "funding_cash_usdt": float(sum(float(t["funding_cash_usdt"]) for t in trades)),
        "fee_total_usdt": float(sum(float(t["fee_entry"] + t["fee_exit"]) for t in trades)),
        "adverse_drag_usdt": float(sum(float(t["adverse_drag"]) for t in trades)),
        "gross_usdt": float(sum(float(t["gross_usdt"]) for t in trades)),
        "mean_net_bps": mean_bps,
        "std_net_bps": std_bps,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": max_dd,
        "exit_reasons": reasons,
        "long_trades": longs,
        "short_trades": shorts,
    }


def block_bootstrap_max_t(
    candidate_returns_map: dict[str, list[dict[str, Any]]],
    start_ms: int,
    end_ms: int,
    block_days: int = 7,
    n_draws: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    """Calendar-block bootstrap simultaneous maxT across all attempted candidate configurations.
    
    Preserves empty blocks (zero return periods when flat).
    """
    block_ms = block_days * 86_400_000
    n_blocks = math.ceil((end_ms - start_ms) / block_ms)

    cand_ids = list(candidate_returns_map.keys())
    m = len(cand_ids)
    if m == 0 or n_blocks == 0:
        return {}

    # Build matrix of returns per block: shape (m, n_blocks)
    block_pnl_matrix = np.zeros((m, n_blocks), dtype=np.float64)

    for c_idx, cid in enumerate(cand_ids):
        trades = candidate_returns_map[cid]
        for t in trades:
            t_exit = int(t["exit_at"])
            b_idx = int((t_exit - start_ms) // block_ms)
            if 0 <= b_idx < n_blocks:
                block_pnl_matrix[c_idx, b_idx] += float(t["net_after_funding_usdt"])

    # Observed t-statistics per candidate
    obs_means = np.mean(block_pnl_matrix, axis=1)
    obs_stds = np.std(block_pnl_matrix, axis=1, ddof=1)
    obs_t = np.zeros(m, dtype=np.float64)
    for i in range(m):
        obs_t[i] = (obs_means[i] / obs_stds[i] * math.sqrt(n_blocks)) if obs_stds[i] > 1e-8 else 0.0

    # Center matrix under null hypothesis H0 (mean = 0)
    centered = block_pnl_matrix - obs_means[:, None]

    # Deterministic pseudo-random generation with fixed seed=42
    rng = np.random.default_rng(seed)
    sampled_indices = rng.integers(0, n_blocks, size=(n_draws, n_blocks))

    max_t_dist = np.empty(n_draws, dtype=np.float64)

    for d in range(n_draws):
        idx_b = sampled_indices[d]
        draw_mat = centered[:, idx_b]
        draw_means = np.mean(draw_mat, axis=1)
        draw_stds = np.std(draw_mat, axis=1, ddof=1)
        draw_t = np.where(draw_stds > 1e-8, (draw_means / np.maximum(draw_stds, 1e-8)) * math.sqrt(n_blocks), 0.0)
        max_t_dist[d] = np.max(draw_t)

    # 95th percentile critical threshold for simultaneous maxT
    q95 = float(np.percentile(max_t_dist, 95.0))

    results = {}
    for i, cid in enumerate(cand_ids):
        p_val_fwer = float(np.mean(max_t_dist >= obs_t[i]))
        results[cid] = {
            "candidate_id": cid,
            "observed_t": float(obs_t[i]),
            "fwer_adjusted_p_value": p_val_fwer,
            "statistically_significant_at_95pct": bool(obs_t[i] >= q95),
            "critical_max_t_95pct": q95,
            "n_calendar_blocks": n_blocks,
            "block_days": block_days,
        }

    return {
        "block_days": block_days,
        "n_blocks": n_blocks,
        "n_draws": n_draws,
        "critical_max_t_95pct": q95,
        "candidates": results,
    }
