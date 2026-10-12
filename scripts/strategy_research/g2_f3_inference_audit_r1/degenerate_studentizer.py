"""Exact numerical failure mechanism of simultaneous max-|T| studentized bootstrap under sparse calendar blocks.

Forensic analysis of the frozen studentizer in scripts/strategy_research/g2_flow_funding_entries_r1/statistics.py.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

BOOTSTRAP_ROUNDS = 2000
BOOTSTRAP_SEED = 20261012


def compute_all_zero_draw_probability(n_blocks: int, n_nonzero_blocks: int) -> float:
    """Exact probability that a bootstrap resample of size n_blocks with replacement contains zero non-zero blocks.

    P(all zero) = ((n_blocks - n_nonzero_blocks) / n_blocks) ** n_blocks.
    As n_blocks -> infty with fixed n_nonzero_blocks = k, this approaches exp(-k).
    """
    if n_blocks <= 0:
        raise ValueError("n_blocks must be positive")
    if n_nonzero_blocks < 0 or n_nonzero_blocks > n_blocks:
        raise ValueError("n_nonzero_blocks must be in [0, n_blocks]")
    prob_single_zero = (n_blocks - n_nonzero_blocks) / n_blocks
    return float(prob_single_zero**n_blocks)


def compute_degenerate_t_value(
    baseline_mean: float,
    floor: float = 1e-6,
) -> float:
    """Compute the t-value resulting from an all-zero bootstrap sample where standard error hits the floor.

    When all resampled blocks are zero:
    b_mean = 0.0
    b_std = 0.0
    b_se = max(0.0 / sqrt(n_blocks), floor) = floor
    t = |0.0 - baseline_mean| / floor = |baseline_mean| / floor
    """
    if floor <= 0:
        raise ValueError("floor must be positive")
    return float(abs(baseline_mean) / floor)


def simulate_studentized_bootstrap(
    cand_block_returns: dict[str, np.ndarray],
    n_rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = BOOTSTRAP_SEED,
    floor: float = 1e-6,
) -> dict[str, Any]:
    """Execute the exact original studentized bootstrap algorithm to record max-|T| and component diagnostics.

    Replicates scripts/strategy_research/g2_flow_funding_entries_r1/statistics.py lines 115-163.
    """
    cand_names = sorted(cand_block_returns.keys())
    first_series = next(iter(cand_block_returns.values()))
    n_blocks = len(first_series)

    # Compute baseline statistics
    baseline_stats: dict[str, dict[str, float]] = {}
    for name in cand_names:
        series = cand_block_returns[name]
        if len(series) != n_blocks:
            raise ValueError(f"Series length mismatch for {name}: {len(series)} vs {n_blocks}")
        m = float(np.mean(series))
        s = float(np.std(series, ddof=1)) if len(series) > 1 else 0.0
        se = s / math.sqrt(n_blocks) if s > 0 else floor
        baseline_stats[name] = {"mean": m, "std": s, "se": se}

    rng = np.random.default_rng(seed)
    max_t_values = np.empty(n_rounds, dtype=np.float64)
    per_candidate_t_values: dict[str, np.ndarray] = {name: np.empty(n_rounds, dtype=np.float64) for name in cand_names}
    all_zero_draw_counts: dict[str, int] = {name: 0 for name in cand_names}

    for b in range(n_rounds):
        indices = rng.integers(0, n_blocks, size=n_blocks)
        max_abs_t = 0.0

        for name in cand_names:
            boot_sample = cand_block_returns[name][indices]
            b_mean = float(np.mean(boot_sample))
            b_std = float(np.std(boot_sample, ddof=1)) if len(boot_sample) > 1 else 0.0
            raw_b_se = b_std / math.sqrt(n_blocks) if len(boot_sample) > 1 else floor
            b_se = max(raw_b_se, floor)

            if np.all(boot_sample == 0.0):
                all_zero_draw_counts[name] += 1

            t_val = abs((b_mean - baseline_stats[name]["mean"]) / b_se)
            per_candidate_t_values[name][b] = t_val
            max_abs_t = max(max_abs_t, t_val)

        max_t_values[b] = max_abs_t

    q95 = float(np.percentile(max_t_values, 95.0))
    q99 = float(np.percentile(max_t_values, 99.0))

    intervals: dict[str, dict[str, Any]] = {}
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
            "ci_width_bps": float(ci_upper - ci_lower),
            "spans_zero": spans_zero,
            "all_zero_draws": all_zero_draw_counts[name],
            "all_zero_rate_pct": (all_zero_draw_counts[name] / n_rounds) * 100.0,
            "standalone_q95": float(np.percentile(per_candidate_t_values[name], 95.0)),
        }

    return {
        "n_blocks": n_blocks,
        "n_rounds": n_rounds,
        "q95_max_t": q95,
        "q99_max_t": q99,
        "intervals": intervals,
        "baseline_stats": baseline_stats,
    }


def create_sparse_synthetic_fixture(
    n_blocks: int,
    sparse_specs: dict[str, list[tuple[int, float]]],
) -> dict[str, np.ndarray]:
    """Create a minimal synthetic fixture of calendar blocks with sparse non-zero events.

    Args:
        n_blocks: total number of calendar blocks (e.g. 5, 10, 20, 76, 152).
        sparse_specs: mapping candidate_name -> list of (block_index, return_bps).
    """
    fixture: dict[str, np.ndarray] = {}
    for name, events in sparse_specs.items():
        arr = np.zeros(n_blocks, dtype=np.float64)
        for idx, val in events:
            if not 0 <= idx < n_blocks:
                raise IndexError(f"Block index {idx} out of range [0, {n_blocks})")
            arr[idx] += val
        fixture[name] = arr
    return fixture


def audit_sparse_inference_mechanism(
    cand_block_returns: dict[str, np.ndarray],
    n_rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = BOOTSTRAP_SEED,
    floor: float = 1e-6,
) -> dict[str, Any]:
    """Produce complete mathematical forensic analysis explaining why simultaneous max-|T| explodes."""
    first_series = next(iter(cand_block_returns.values()))
    n_blocks = len(first_series)

    sim_res = simulate_studentized_bootstrap(cand_block_returns, n_rounds=n_rounds, seed=seed, floor=floor)

    per_cand_analysis: dict[str, Any] = {}
    contaminating_candidates: list[str] = []

    for name, series in cand_block_returns.items():
        nonzero_mask = series != 0.0
        n_nonzero = int(np.sum(nonzero_mask))
        p_all_zero_theory = compute_all_zero_draw_probability(n_blocks, n_nonzero)
        m = float(np.mean(series))
        degen_t_theory = compute_degenerate_t_value(m, floor=floor)

        sim_cand = sim_res["intervals"][name]
        is_contaminator = sim_cand["all_zero_rate_pct"] >= 5.0 and degen_t_theory >= 1e4

        if is_contaminator:
            contaminating_candidates.append(name)

        per_cand_analysis[name] = {
            "n_nonzero_blocks": n_nonzero,
            "zero_fraction": float((n_blocks - n_nonzero) / n_blocks),
            "baseline_mean_bps": m,
            "theoretical_all_zero_prob": p_all_zero_theory,
            "empirical_all_zero_rate_pct": sim_cand["all_zero_rate_pct"],
            "theoretical_degenerate_t": degen_t_theory,
            "empirical_standalone_q95": sim_cand["standalone_q95"],
            "causes_degenerate_critical_value": is_contaminator,
        }

    return {
        "n_blocks": n_blocks,
        "n_rounds": n_rounds,
        "floor": floor,
        "simultaneous_q95_max_t": sim_res["q95_max_t"],
        "contaminating_candidates": contaminating_candidates,
        "candidates": per_cand_analysis,
        "simulation_intervals": sim_res["intervals"],
        "root_cause_summary": (
            "The simultaneous max-|T| studentizer explodes because sparse candidates (with few non-zero blocks) "
            "frequently yield all-zero resamples where sample variance vanishes. The denominator b_se is clamped "
            f"to floor={floor}, producing t = |mean| / floor on the order of 10^6. Whenever the all-zero draw "
            "probability exceeds 5% (which occurs for any candidate with k <= 2 non-zero blocks), the simultaneous "
            "q95 is mathematically forced to this million-scale artifact, blowing up confidence intervals for all "
            "evaluated candidates regardless of their individual sample properties."
        ),
    }
