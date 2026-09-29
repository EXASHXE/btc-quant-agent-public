"""Independent exact accepted Stage R2 function at blob ec8f975a.

The function body is retained verbatim to detect production semantic drift.
"""
# ruff: noqa: I001, UP006, UP035, RUF046
from __future__ import annotations

import math
from typing import Tuple

import numpy as np

def run_joint_bootstrap_studentized(
    Z: np.ndarray,
    A: np.ndarray,
    L: int,
    B: int,
    rng: np.random.Generator
) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """
    Executes shared-clock, source-bundle standardized single-step joint maximum bootstrap
    with Studentized bootstrap-t and Künsch (1989) ratio-estimator block sums.

    Z: (K, T) - event return array (Z = A * Y)
    A: (K, T) - event eligibility mask
    L: block length in hours
    B: number of bootstrap replicates
    Returns: (mu_hat, se_hat, c95, lcb)
    """
    K, T = Z.shape
    num_blocks = int(math.ceil(T / L))
    S = T - L + 1

    # 1. Sample ratio estimator
    denom = A.sum(axis=1)
    testable = denom >= 60.0
    valid = np.where(testable)[0]
    mu_hat = np.zeros(K, dtype=np.float64)
    se_hat = np.full(K, np.nan, dtype=np.float64)
    lcb = np.full(K, -np.inf, dtype=np.float64)

    if len(valid) == 0:
        return mu_hat, se_hat, float("nan"), lcb

    mu_hat[valid] = Z[valid].sum(axis=1) / denom[valid]

    # Precompute overlapping block sums for valid candidates: shape (len(valid), S)
    Z_cs = np.pad(np.cumsum(Z[valid], axis=1), ((0, 0), (1, 0)))
    A_cs = np.pad(np.cumsum(A[valid], axis=1), ((0, 0), (1, 0)))
    Z_blocks = Z_cs[:, L:] - Z_cs[:, :-L]
    A_blocks = A_cs[:, L:] - A_cs[:, :-L]

    # Original sample standard error using Künsch (1989) moving block sums
    e_blocks = Z_blocks - mu_hat[valid, None] * A_blocks
    e_bar = np.mean(e_blocks, axis=1, keepdims=True)
    var_sum = (T / (L * S)) * np.sum((e_blocks - e_bar)**2, axis=1)
    se_hat[valid] = np.sqrt(np.maximum(var_sum, 1e-12)) / denom[valid]

    # 2. Shared block resampling: (B, num_blocks) block start indices
    starts = rng.integers(0, S, size=(B, num_blocks))

    # Precompute quadratic block terms for fast replicate SE evaluation
    Z2_blocks = Z_blocks**2
    A2_blocks = A_blocks**2
    ZA_blocks = Z_blocks * A_blocks

    # Gather block sums for each replicate: shape (len(valid), B)
    # Use chunked computation with np.take (chunks of 2500) to keep memory inside CPU L3 cache and maximize speed
    chunk_B = 2500
    if B <= chunk_B:
        Z_b = np.sum(np.take(Z_blocks, starts, axis=1), axis=2)
        A_b = np.sum(np.take(A_blocks, starts, axis=1), axis=2)
        Z2_b = np.sum(np.take(Z2_blocks, starts, axis=1), axis=2)
        A2_b = np.sum(np.take(A2_blocks, starts, axis=1), axis=2)
        ZA_b = np.sum(np.take(ZA_blocks, starts, axis=1), axis=2)
    else:
        Z_b_list, A_b_list, Z2_b_list, A2_b_list, ZA_b_list = [], [], [], [], []
        for b_start in range(0, B, chunk_B):
            sub_starts = starts[b_start:b_start + chunk_B]
            Z_b_list.append(np.sum(np.take(Z_blocks, sub_starts, axis=1), axis=2))
            A_b_list.append(np.sum(np.take(A_blocks, sub_starts, axis=1), axis=2))
            Z2_b_list.append(np.sum(np.take(Z2_blocks, sub_starts, axis=1), axis=2))
            A2_b_list.append(np.sum(np.take(A2_blocks, sub_starts, axis=1), axis=2))
            ZA_b_list.append(np.sum(np.take(ZA_blocks, sub_starts, axis=1), axis=2))
        Z_b = np.concatenate(Z_b_list, axis=1)
        A_b = np.concatenate(A_b_list, axis=1)
        Z2_b = np.concatenate(Z2_b_list, axis=1)
        A2_b = np.concatenate(A2_b_list, axis=1)
        ZA_b = np.concatenate(ZA_b_list, axis=1)

    denom_b = np.maximum(A_b, 1e-12)
    mu_b = Z_b / denom_b

    # Handle zero-event draws fail-closed
    zero_draws = (A_b == 0.0)
    if np.any(zero_draws):
        mu_b[zero_draws] = mu_hat[valid, None].repeat(B, axis=1)[zero_draws]

    # Replicate standard error across the k independent bootstrap blocks
    sum_e2 = np.maximum(Z2_b - 2.0 * mu_b * ZA_b + (mu_b**2) * A2_b, 0.0)
    s2 = sum_e2 / max(num_blocks - 1, 1)
    var_b = (num_blocks / (denom_b**2)) * s2
    se_b = np.sqrt(np.maximum(var_b, 1e-12))

    # 3. Finite-sample non-circular null centering rule
    center = np.sum(Z_blocks, axis=1) / np.maximum(np.sum(A_blocks, axis=1), 1e-12)

    # 4. Studentized test statistic in bootstrap: T* = (mu* - center) / SE*
    T_b = (mu_b - center[:, None]) / se_b

    # 5. Joint maximum statistic across testable coordinates
    max_T = np.max(T_b, axis=0)
    c95 = float(np.percentile(max_T, 95.0))

    # 6. Simultaneous Lower Confidence Bound (LCB)
    lcb[valid] = mu_hat[valid] - c95 * se_hat[valid]

    return mu_hat, se_hat, c95, lcb
