"""Small-sample block bootstrap, block-occupancy diagnostics, and power projections.

Under B-line Controller Authority:
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BootstrapResult:
    status: str
    point_estimate_net_bps: float | None
    ci_lower_95: float | None
    ci_upper_95: float | None
    standard_error: float | None
    active_blocks: int
    total_blocks_spanned: int
    trade_count: int
    is_degenerate: bool
    diagnostic: str


@dataclass(frozen=True)
class PowerProjection:
    sample_size: int
    effect_size_bps: float
    projected_power: float
    rejection_rate_at_alpha_05: float


def compute_basic_metrics(trades_net_bps: Sequence[float]) -> dict[str, Any]:
    """Compute exact basic statistics with never-divide-by-zero guarantees."""
    n = len(trades_net_bps)
    if n == 0:
        return {
            "trade_count": 0,
            "mean_net_bps": 0.0,
            "std_net_bps": 0.0,
            "median_net_bps": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "status": "EMPTY_SAMPLE",
        }

    mean_val = float(np.mean(trades_net_bps))
    std_val = float(np.std(trades_net_bps, ddof=1)) if n > 1 else 0.0
    median_val = float(np.median(trades_net_bps))
    wins = [x for x in trades_net_bps if x > 0]
    losses = [abs(x) for x in trades_net_bps if x < 0]

    win_rate = float(len(wins) / n)
    gross_gains = sum(wins)
    gross_losses = sum(losses)
    profit_factor = (
        float(gross_gains / gross_losses)
        if gross_losses > 0
        else (float("inf") if gross_gains > 0 else 0.0)
    )

    return {
        "trade_count": n,
        "mean_net_bps": mean_val,
        "std_net_bps": std_val,
        "median_net_bps": median_val,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "status": "VALID",
    }


def block_bootstrap_net_bps(
    trades: Sequence[dict[str, Any]],
    block_size_days: int = 7,
    n_bootstraps: int = 2000,
    random_seed: int = 42,
) -> BootstrapResult:
    """Perform 7d or 14d block bootstrap over trade net bps.

    Refuses when zero active blocks or degenerate SE; does not clamp to 1e-6 and declare fake CI.
    """
    if not trades:
        return BootstrapResult(
            status="EMPTY_SAMPLE",
            point_estimate_net_bps=None,
            ci_lower_95=None,
            ci_upper_95=None,
            standard_error=None,
            active_blocks=0,
            total_blocks_spanned=0,
            trade_count=0,
            is_degenerate=True,
            diagnostic="EVIDENCE_IMMATURE",
        )

    # Extract timestamps and net bps
    timestamps_ms = [int(t.get("exit_fill_ms") or t.get("entry_fill_ms") or 0) for t in trades]
    net_bps = [float(t.get("net_bps", 0.0)) for t in trades]
    trade_count = len(trades)

    # Check zero variance / degenerate trade data
    if len(set(net_bps)) <= 1:
        return BootstrapResult(
            status="DEGENERATE_ZERO_VARIANCE",
            point_estimate_net_bps=net_bps[0] if net_bps else 0.0,
            ci_lower_95=None,
            ci_upper_95=None,
            standard_error=None,
            active_blocks=1 if net_bps else 0,
            total_blocks_spanned=1,
            trade_count=trade_count,
            is_degenerate=True,
            diagnostic="EVIDENCE_IMMATURE",
        )

    # Bin into calendar blocks of block_size_days (block_size_ms)
    block_size_ms = block_size_days * 24 * 3600 * 1000
    min_ts = min(timestamps_ms)
    max_ts = max(timestamps_ms)

    total_blocks_spanned = max(1, math.ceil((max_ts - min_ts + 1) / block_size_ms))

    # Group trades by block index
    block_map: dict[int, list[float]] = {}
    for ts, bps in zip(timestamps_ms, net_bps):
        blk_idx = (ts - min_ts) // block_size_ms
        block_map.setdefault(blk_idx, []).append(bps)

    active_blocks = len(block_map)

    # If fewer than 5 active blocks, small sample makes block bootstrap SE unviable
    if active_blocks < 5 or trade_count < 10:
        return BootstrapResult(
            status="INSUFFICIENT_ACTIVE_BLOCKS",
            point_estimate_net_bps=float(np.mean(net_bps)),
            ci_lower_95=None,
            ci_upper_95=None,
            standard_error=None,
            active_blocks=active_blocks,
            total_blocks_spanned=total_blocks_spanned,
            trade_count=trade_count,
            is_degenerate=True,
            diagnostic="EVIDENCE_IMMATURE",
        )

    # Run block bootstrap
    rng = np.random.RandomState(random_seed)
    block_keys = list(block_map.keys())
    resampled_means = []

    for _ in range(n_bootstraps):
        sampled_keys = rng.choice(block_keys, size=len(block_keys), replace=True)
        sampled_trades: list[float] = []
        for k in sampled_keys:
            sampled_trades.extend(block_map[k])
        if sampled_trades:
            resampled_means.append(np.mean(sampled_trades))

    if not resampled_means or np.std(resampled_means) <= 1e-12:
        return BootstrapResult(
            status="DEGENERATE_BOOTSTRAP_SE",
            point_estimate_net_bps=float(np.mean(net_bps)),
            ci_lower_95=None,
            ci_upper_95=None,
            standard_error=None,
            active_blocks=active_blocks,
            total_blocks_spanned=total_blocks_spanned,
            trade_count=trade_count,
            is_degenerate=True,
            diagnostic="EVIDENCE_IMMATURE",
        )

    ci_lower = float(np.percentile(resampled_means, 2.5))
    ci_upper = float(np.percentile(resampled_means, 97.5))
    se = float(np.std(resampled_means))

    # Predeclared minimum readiness diagnostic
    diagnostic = "SAMPLE_READINESS_MET" if (trade_count >= 30 and active_blocks >= 15) else "EVIDENCE_IMMATURE"

    return BootstrapResult(
        status="BOOTSTRAP_SUCCESS",
        point_estimate_net_bps=float(np.mean(net_bps)),
        ci_lower_95=ci_lower,
        ci_upper_95=ci_upper,
        standard_error=se,
        active_blocks=active_blocks,
        total_blocks_spanned=total_blocks_spanned,
        trade_count=trade_count,
        is_degenerate=False,
        diagnostic=diagnostic,
    )


def project_statistical_power(
    assumed_std_bps: float = 25.0,
    target_sample_sizes: Sequence[int] = (30, 60, 100),
    effect_sizes_bps: Sequence[float] = (5.0, 10.0, 15.0),
    alpha: float = 0.05,
    n_simulations: int = 1000,
    random_seed: int = 12345,
) -> list[PowerProjection]:
    """Compute pre-outcome synthetic power projections across sample sizes and effect sizes."""
    rng = np.random.RandomState(random_seed)
    projections = []

    for n in target_sample_sizes:
        critical_t = 1.96  # approx two-tailed 5%
        for eff in effect_sizes_bps:
            rejections = 0
            for _ in range(n_simulations):
                sample = rng.normal(loc=eff, scale=assumed_std_bps, size=n)
                sample_mean = np.mean(sample)
                sample_se = np.std(sample, ddof=1) / math.sqrt(n) if n > 1 else 1.0
                t_stat = sample_mean / sample_se if sample_se > 0 else 0.0
                if abs(t_stat) > critical_t:
                    rejections += 1
            power = rejections / float(n_simulations)
            projections.append(
                PowerProjection(
                    sample_size=n,
                    effect_size_bps=eff,
                    projected_power=power,
                    rejection_rate_at_alpha_05=power,
                )
            )

    return projections
