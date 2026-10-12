"""Alternative statistical designs and sparse-support refusal for independent forensic audit.

Covers:
- Nonparametric interval refusal on sparse support (n < 30 or active blocks < 10)
- Exact binomial sign test and Clopper-Pearson confidence interval
- Adverse-event sensitivity analysis (1-2 event shift)
- Exploratory fixed-SE centered block bootstrap (descriptive only, cannot grant PASS)
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def evaluate_sparse_interval_refusal(
    n_trades: int,
    n_active_blocks: int,
    min_trades: int = 30,
    min_active_blocks: int = 10,
) -> dict[str, Any]:
    """Pre-registered rule: refuse to produce inferential confidence intervals when support is sparse."""
    refuse_trades = n_trades < min_trades
    refuse_blocks = n_active_blocks < min_active_blocks
    should_refuse = refuse_trades or refuse_blocks

    reasons: list[str] = []
    if refuse_trades:
        reasons.append(f"Trades count {n_trades} < minimum required {min_trades}")
    if refuse_blocks:
        reasons.append(f"Active blocks count {n_active_blocks} < minimum required {min_active_blocks}")

    return {
        "should_refuse_interval": should_refuse,
        "refusal_status": "SPARSE_SUPPORT_REFUSAL" if should_refuse else "SUPPORT_SUFFICIENT",
        "reasons": reasons,
        "n_trades": n_trades,
        "n_active_blocks": n_active_blocks,
        "min_trades_threshold": min_trades,
        "min_active_blocks_threshold": min_active_blocks,
    }


def compute_exact_binomial_sign_test(
    n: int,
    k_wins: int,
    p0: float = 0.5,
) -> dict[str, Any]:
    """Exact two-sided binomial sign test under null hypothesis of no directional edge (p = 0.5)."""
    if n <= 0:
        return {
            "n": 0,
            "k_wins": 0,
            "k_losses": 0,
            "win_rate_pct": 0.0,
            "p_value_two_sided": 1.0,
            "clopper_pearson_95_ci": [0.0, 1.0],
            "score_95_ci": [0.0, 1.0],
            "statistically_significant_at_05": False,
        }

    # Binomial probabilities
    probs = [math.comb(n, j) * (p0**j) * ((1.0 - p0) ** (n - j)) for j in range(n + 1)]
    obs_prob = probs[k_wins]
    # Two-sided p-value: sum probabilities <= obs_prob
    p_value = min(1.0, sum(p for p in probs if p <= obs_prob + 1e-12))

    # Clopper-Pearson exact 95% confidence interval for binomial proportion (alpha = 0.05)
    alpha = 0.05
    if k_wins == 0:
        cp_lower = 0.0
    else:
        # Solve P(X >= k | p) = alpha / 2 via bisection
        low, high = 0.0, 1.0
        for _ in range(50):
            mid = (low + high) / 2.0
            p_tail = sum(math.comb(n, j) * (mid**j) * ((1.0 - mid) ** (n - j)) for j in range(k_wins, n + 1))
            if p_tail > alpha / 2.0:
                high = mid
            else:
                low = mid
        cp_lower = (low + high) / 2.0

    if k_wins == n:
        cp_upper = 1.0
    else:
        # Solve P(X <= k | p) = alpha / 2 via bisection
        low, high = 0.0, 1.0
        for _ in range(50):
            mid = (low + high) / 2.0
            p_tail = sum(math.comb(n, j) * (mid**j) * ((1.0 - mid) ** (n - j)) for j in range(k_wins + 1))
            if p_tail < alpha / 2.0:
                high = mid
            else:
                low = mid
        cp_upper = (low + high) / 2.0

    # Standard Wilson score interval (symmetric, properly bounded in [0, 1])
    z = 1.959963984540054
    z2 = z * z
    denom = n + z2
    center = (k_wins + z2 / 2.0) / denom
    half = (z * math.sqrt(k_wins * (1.0 - k_wins / n) + z2 / 4.0)) / denom
    score_lower = max(0.0, center - half)
    score_upper = min(1.0, center + half)

    win_rate = (k_wins / n) * 100.0

    return {
        "n": n,
        "k_wins": k_wins,
        "k_losses": n - k_wins,
        "win_rate_pct": win_rate,
        "p_value_two_sided": float(p_value),
        "clopper_pearson_95_ci": [float(cp_lower), float(cp_upper)],
        "score_95_ci": [float(score_lower), float(score_upper)],
        "statistically_significant_at_05": p_value < 0.05,
    }


def compute_adverse_event_sensitivity(
    trades: list[dict[str, Any]],
    adverse_loss_bps: float = 44.0,
) -> dict[str, Any]:
    """Test sensitivity of net USDT and mean bps if top 1 or top 2 winning trades turn into adverse losses."""
    if not trades:
        return {"n": 0}

    net_usdt = [float(t["net_after_funding_usdt"]) for t in trades]
    net_bps = [float(t["net_after_funding_bps"]) for t in trades]
    base_sum_usdt = sum(net_usdt)
    base_mean_bps = float(np.mean(net_bps))

    # Find winning trades sorted by profit descending
    win_indices = [i for i, u in enumerate(net_usdt) if u > 0]
    win_indices.sort(key=lambda idx: net_usdt[idx], reverse=True)

    sensitivity_cases: list[dict[str, Any]] = []

    for shift_k in (1, 2):
        if len(win_indices) < shift_k:
            continue
        shifted_usdt = list(net_usdt)
        shifted_bps = list(net_bps)

        for i in range(shift_k):
            idx = win_indices[i]
            # Convert winning trade to an adverse loss
            shifted_bps[idx] = -abs(adverse_loss_bps)
            # 1000 USDT notional approx for USDT impact
            shifted_usdt[idx] = -abs(adverse_loss_bps) / 10_000.0 * 1000.0

        new_sum_usdt = sum(shifted_usdt)
        new_mean_bps = float(np.mean(shifted_bps))

        pos = sum(u for u in shifted_usdt if u > 0)
        neg = abs(sum(u for u in shifted_usdt if u < 0))
        new_pf = pos / neg if neg > 0 else (999.0 if pos > 0 else 0.0)

        sensitivity_cases.append({
            "shifted_wins_count": shift_k,
            "new_total_net_usdt": new_sum_usdt,
            "new_mean_net_bps": new_mean_bps,
            "new_profit_factor": new_pf,
            "remains_profitable": new_sum_usdt > 0,
        })

    return {
        "base_total_net_usdt": base_sum_usdt,
        "base_mean_net_bps": base_mean_bps,
        "sensitivity_cases": sensitivity_cases,
    }


def compute_fixed_se_block_bootstrap(
    series: np.ndarray,
    n_rounds: int = 2000,
    seed: int = 20261012,
) -> dict[str, Any]:
    """Exploratory block bootstrap using baseline sample SE to prevent degenerate zero denominator.

    Descriptive only: cannot grant scientific PASS to sparse sample.
    """
    n_blocks = len(series)
    m = float(np.mean(series))
    s = float(np.std(series, ddof=1)) if n_blocks > 1 else 0.0
    se_sample = s / math.sqrt(n_blocks) if s > 0 else 1e-6

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_rounds, dtype=np.float64)
    t_fixed = np.empty(n_rounds, dtype=np.float64)

    for b in range(n_rounds):
        indices = rng.integers(0, n_blocks, size=n_blocks)
        boot_sample = series[indices]
        b_mean = float(np.mean(boot_sample))
        boot_means[b] = b_mean
        t_fixed[b] = abs((b_mean - m) / se_sample)

    q95_t = float(np.percentile(t_fixed, 95.0))
    p_lower = float(np.percentile(boot_means, 2.5))
    p_upper = float(np.percentile(boot_means, 97.5))

    fixed_ci_lower = m - q95_t * se_sample
    fixed_ci_upper = m + q95_t * se_sample

    return {
        "n_blocks": n_blocks,
        "mean_bps": m,
        "se_sample_bps": se_sample,
        "fixed_se_q95_t": q95_t,
        "fixed_se_ci_95": [float(fixed_ci_lower), float(fixed_ci_upper)],
        "percentile_ci_95": [float(p_lower), float(p_upper)],
        "fixed_ci_spans_zero": bool(fixed_ci_lower <= 0 <= fixed_ci_upper),
        "percentile_ci_spans_zero": bool(p_lower <= 0 <= p_upper),
        "caveat": "EXPLORATORY_DESCRIPTIVE_ONLY_CANNOT_GRANT_PROMOTION",
    }
