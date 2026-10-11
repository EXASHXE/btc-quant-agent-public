"""Block bootstrap uncertainty, max-|T| simultaneous intervals, and sample support."""
from __future__ import annotations

from typing import Any

import numpy as np

CALENDAR_START_MS = 1609459200000  # 2021-01-01 00:00:00 UTC
CALENDAR_END_MS = 1704067200000    # 2024-01-01 00:00:00 UTC


def mean(values: list[float] | np.ndarray) -> float | None:
    """Compute mean or return None if empty."""
    return float(np.mean(values)) if len(values) > 0 else None


def block_bootstrap_contrasts(
    registry: list[tuple[str, list[dict[str, Any]]]],
    block_days: int = 14,
    draws: int = 10000,
    seed: int = 42,
) -> dict[str, Any]:
    """Shared UTC block bootstrap across fixed contrasts with zero-trade blocks retained.

    registry: list of (contrast_name, list_of_paired_rows)
    block_days: 7 or 14
    draws: default 10000
    seed: default 42
    """
    if block_days not in (7, 14):
        raise ValueError(f"Block days must be 7 or 14, got {block_days}")
    if not registry:
        raise ValueError("Empty contrast registry")

    duration = block_days * 86400000
    blocks = (CALENDAR_END_MS - CALENDAR_START_MS + duration - 1) // duration
    n_contrasts = len(registry)

    sums = np.zeros((blocks, n_contrasts), dtype=float)
    counts = np.zeros((blocks, n_contrasts), dtype=int)

    for j, (_, rows) in enumerate(registry):
        for row in rows:
            at = int(row["entry_at"])
            val = float(row["delta_bps"])
            if not (CALENDAR_START_MS <= at < CALENDAR_END_MS) or not np.isfinite(val):
                raise ValueError(f"Invalid timestamp or value: at={at}, val={val}")
            idx = (at - CALENDAR_START_MS) // duration
            sums[idx, j] += val
            counts[idx, j] += 1

    total_events = counts.sum(axis=0)
    if np.any(total_events == 0):
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "block_days": block_days,
            "empty_contrasts": [registry[j][0] for j in np.where(total_events == 0)[0]],
        }

    centers = sums.sum(axis=0) / total_events
    rng = np.random.default_rng(seed)
    sample_indices = rng.integers(0, blocks, size=(draws, blocks))

    sampled_counts = counts[sample_indices].sum(axis=1)  # (draws, n_contrasts)
    sampled_sums = sums[sample_indices].sum(axis=1)      # (draws, n_contrasts)

    valid_draws_mask = np.all(sampled_counts > 0, axis=1)
    if np.sum(valid_draws_mask) < draws * 0.95:
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "block_days": block_days,
            "valid_draws": int(np.sum(valid_draws_mask)),
        }

    estimates = sampled_sums[valid_draws_mask] / sampled_counts[valid_draws_mask]
    se = estimates.std(axis=0, ddof=1)

    if np.any(se <= 1e-12):
        return {
            "status": "INSUFFICIENT_SUPPORT",
            "block_days": block_days,
            "degenerate_contrasts": [registry[j][0] for j in np.where(se <= 1e-12)[0]],
        }

    null_t = (estimates - centers) / se
    max_abs_t = np.max(np.abs(null_t), axis=1)
    critical_95 = float(np.quantile(max_abs_t, 0.95))

    contrasts_out = []
    for j, (name, _) in enumerate(registry):
        lcb = float(centers[j] - critical_95 * se[j])
        ucb = float(centers[j] + critical_95 * se[j])
        active_blocks = int(np.count_nonzero(counts[:, j]))
        empty_blocks = int(np.count_nonzero(counts[:, j] == 0))
        includes_zero = bool(lcb <= 0.0 <= ucb)

        contrasts_out.append({
            "contrast": name,
            "qualified_n": int(total_events[j]),
            "point_estimate_bps": float(centers[j]),
            "bootstrap_se_bps": float(se[j]),
            "simultaneous_95_lcb_bps": lcb,
            "simultaneous_95_ucb_bps": ucb,
            "includes_zero": includes_zero,
            "active_calendar_blocks": active_blocks,
            "total_calendar_blocks": int(blocks),
            "zero_trade_blocks": empty_blocks,
        })

    return {
        "status": "MEASURED_CONDITIONAL_ON_EXPOSED_SELECTED_LEADS",
        "block_days": block_days,
        "draws": draws,
        "valid_draws": int(np.sum(valid_draws_mask)),
        "seed": seed,
        "critical_95_max_t": critical_95,
        "contrasts": contrasts_out,
        "selection_disclosure": "Prior 48 trials exposed; results are observational diagnostic only",
    }
