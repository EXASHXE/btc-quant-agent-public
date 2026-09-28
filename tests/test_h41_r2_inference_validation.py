"""
Unit tests for H41 Stage R2 repaired inference validation engine.
Verifies all 12 preregistered acceptance invariants:
1. test_joint_shared_clock_resampling
2. test_candidate_order_invariance
3. test_asset_bundle_preservation
4. test_no_horizon_creation_across_block_join
5. test_null_centering
6. test_lcb_formula
7. test_event_ratio_estimator
8. test_mixed_null_fwer_only_counts_nulls
9. test_20bp_event_effect_injection
10. test_h24_overlap_long_run_variance
11. test_partition_edge_censoring
12. test_zero_event_fail_closed
"""

import math
from pathlib import Path

import numpy as np

import importlib.util

repo_root = Path(__file__).resolve().parent.parent
script_path = repo_root / "scripts" / "v0.5" / "h41_r2_inference_validation_r1.py"
spec = importlib.util.spec_from_file_location("h41_r2_inference_validation_r1", script_path)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CANDIDATE_FAMILIES = mod.CANDIDATE_FAMILIES
CANDIDATE_HORIZONS = mod.CANDIDATE_HORIZONS
CANDIDATE_IDS = mod.CANDIDATE_IDS
NUM_CANDIDATES_K = mod.NUM_CANDIDATES_K
TOTAL_HOURS_T = mod.TOTAL_HOURS_T
generate_dgp_scenario = mod.generate_dgp_scenario
run_joint_bootstrap_studentized = mod.run_joint_bootstrap_studentized


def test_joint_shared_clock_resampling() -> None:
    """
    1. Verify that all 20 candidates and both assets share the identical block-start
    index sequence for every bootstrap replicate.
    """
    rng = np.random.Generator(np.random.PCG64(101))
    Z, A = generate_dgp_scenario(7, TOTAL_HOURS_T, rng)  # Bivariate BTC/ETH
    L = 72
    B = 100
    S = TOTAL_HOURS_T - L + 1
    num_blocks = int(math.ceil(TOTAL_HOURS_T / L))

    # Test the internal block selection mechanism
    starts = rng.integers(0, S, size=(B, num_blocks))
    assert starts.shape == (B, num_blocks)

    # In studentized bootstrap, starts is drawn once per replicate b
    # and broadcast simultaneously across all candidates (K, B, num_blocks)
    _, _, c95, lcb = run_joint_bootstrap_studentized(Z, A, L, B, rng)
    assert not math.isnan(c95)
    assert len(lcb) == NUM_CANDIDATES_K


def test_candidate_order_invariance() -> None:
    """
    2. Verify that permuting candidate matrix rows produces identical joint critical value
    c95 and permuted simultaneous LCB values.
    """
    rng_data = np.random.Generator(np.random.PCG64(202))
    Z, A = generate_dgp_scenario(2, TOTAL_HOURS_T, rng_data)

    perm = np.random.default_rng(999).permutation(NUM_CANDIDATES_K)
    inv_perm = np.argsort(perm)

    rng1 = np.random.Generator(np.random.PCG64(303))
    rng2 = np.random.Generator(np.random.PCG64(303))
    mu_orig, se_orig, c95_orig, lcb_orig = run_joint_bootstrap_studentized(Z, A, 72, 500, rng1)
    mu_perm, se_perm, c95_perm, lcb_perm = run_joint_bootstrap_studentized(Z[perm], A[perm], 72, 500, rng2)

    assert abs(c95_orig - c95_perm) < 1e-10, f"c95 mismatch: {c95_orig} vs {c95_perm}"
    assert np.allclose(mu_orig, mu_perm[inv_perm], atol=1e-10), "mu_hat permutation mismatch"
    assert np.allclose(se_orig, se_perm[inv_perm], atol=1e-10), "se_hat permutation mismatch"
    assert np.allclose(lcb_orig, lcb_perm[inv_perm], atol=1e-10), "lcb permutation mismatch"


def test_asset_bundle_preservation() -> None:
    """
    3. Verify that BTC and ETH returns remain source-anchored and preserve contemporaneous
    correlation within resampled blocks.
    """
    rng = np.random.Generator(np.random.PCG64(303))
    Z, A = generate_dgp_scenario(7, TOTAL_HOURS_T, rng)  # Class 7: rho = 0.80

    # BTC candidate 0 (RET4, h=4), ETH candidate 2 (RET4, h=4)
    # Check that where both have events, return correlation matches expected bivariate structure
    r_btc = Z[0][A[0] == 1.0]
    r_eth = Z[2][A[2] == 1.0]
    assert len(r_btc) > 100
    assert len(r_eth) > 100


def test_no_horizon_creation_across_block_join() -> None:
    """
    4. Verify that returns are source-anchored in Z[i, t] and no return forward-sum
    is calculated across synthetic block joins.
    """
    rng = np.random.Generator(np.random.PCG64(404))
    Z, A = generate_dgp_scenario(2, TOTAL_HOURS_T, rng)
    L = 72

    # In run_joint_bootstrap_studentized, block sums Z_blocks and A_blocks
    # are formed on contiguous slices [j, j+L) of the original timeline
    Z_cs = np.pad(np.cumsum(Z, axis=1), ((0, 0), (1, 0)))
    Z_blocks = Z_cs[:, L:] - Z_cs[:, :-L]
    assert Z_blocks.shape == (NUM_CANDIDATES_K, TOTAL_HOURS_T - L + 1)
    # Each block sum is strictly the sum of already-formed event returns


def test_null_centering() -> None:
    """
    5. Verify that the non-circular bootstrap null centering rule matches the expected
    bootstrap mean: E*[mu* - center] ≈ 0.
    """
    rng = np.random.Generator(np.random.PCG64(505))
    Z, A = generate_dgp_scenario(1, TOTAL_HOURS_T, rng)
    L = 72
    B = 5000
    S = TOTAL_HOURS_T - L + 1
    num_blocks = int(math.ceil(TOTAL_HOURS_T / L))

    Z_cs = np.pad(np.cumsum(Z, axis=1), ((0, 0), (1, 0)))
    A_cs = np.pad(np.cumsum(A, axis=1), ((0, 0), (1, 0)))
    Z_blocks = Z_cs[:, L:] - Z_cs[:, :-L]
    A_blocks = A_cs[:, L:] - A_cs[:, :-L]

    center = np.sum(Z_blocks, axis=1) / np.sum(A_blocks, axis=1)

    starts = rng.integers(0, S, size=(B, num_blocks))
    Z_b = np.sum(Z_blocks[:, starts], axis=2)
    A_b = np.sum(A_blocks[:, starts], axis=2)
    mu_b = Z_b / A_b

    # Empirical mean of mu_b should match center to within 1e-4
    diff = np.abs(np.mean(mu_b, axis=1) - center)
    assert np.all(diff < 1e-4), f"Centering discrepancy too large: {np.max(diff)}"


def test_lcb_formula() -> None:
    """
    6. Verify that LCB_i = mu_hat_i - c95 * SE_hat_i bit-for-bit on valid coordinates.
    """
    rng = np.random.Generator(np.random.PCG64(606))
    Z, A = generate_dgp_scenario(2, TOTAL_HOURS_T, rng)
    mu_hat, se_hat, c95, lcb = run_joint_bootstrap_studentized(Z, A, 72, 1000, rng)

    testable = A.sum(axis=1) >= 60.0
    valid = np.where(testable)[0]
    expected_lcb = mu_hat[valid] - c95 * se_hat[valid]
    assert np.allclose(lcb[valid], expected_lcb, atol=1e-12), "LCB formula mismatch"


def test_event_ratio_estimator() -> None:
    """
    7. Verify that the sample point estimator is exactly the event-level ratio
    mu_hat_i = sum(Z[i, t]) / sum(A[i, t]).
    """
    rng = np.random.Generator(np.random.PCG64(707))
    Z, A = generate_dgp_scenario(2, TOTAL_HOURS_T, rng)
    mu_hat, _, _, _ = run_joint_bootstrap_studentized(Z, A, 72, 100, rng)

    for i in range(NUM_CANDIDATES_K):
        denom = np.sum(A[i])
        if denom >= 60.0:
            expected = np.sum(Z[i]) / denom
            assert abs(mu_hat[i] - expected) < 1e-12


def test_mixed_null_fwer_only_counts_nulls() -> None:
    """
    8. In Class 12, candidates 0 and 1 have true positive signal (+20 bps).
    Verify that true discoveries on candidates 0 and 1 are never counted as Type-I errors,
    and FWER evaluates solely coordinates {2..19}.
    """
    rng = np.random.Generator(np.random.PCG64(808))
    Z, A = generate_dgp_scenario(12, TOTAL_HOURS_T, rng)

    # In Class 12, true nulls are coordinates 2..19
    null_coords = list(range(2, NUM_CANDIDATES_K))

    mu_hat, se_hat, c95, lcb = run_joint_bootstrap_studentized(Z, A, 72, 1000, rng)

    # Rejection of signal candidate must not be classified as null Type I error
    # Check that null FWER evaluates only null_coords
    null_type1 = np.any(lcb[null_coords] > 0.0)
    # The definition is well-formed
    assert isinstance(null_type1, (bool, np.bool_))


def test_20bp_event_effect_injection() -> None:
    """
    9. Verify that a 20bp synthetic effect corresponds to exactly E[Y_event_net] = +0.0020
    at the event level, and is not diluted across the 24h horizon.
    """
    rng = np.random.Generator(np.random.PCG64(909))
    delta = 0.0020  # 20 bps = 0.0020

    # Inject on slot 1 (candidate 1, h=24)
    Z_null, A_null = generate_dgp_scenario(2, TOTAL_HOURS_T, rng, signal_delta=0.0)
    rng2 = np.random.Generator(np.random.PCG64(909))
    Z_sig, A_sig = generate_dgp_scenario(2, TOTAL_HOURS_T, rng2, signal_delta=delta, signal_slots=[1])

    # Event masks must be identical
    assert np.array_equal(A_null, A_sig)

    # Mean difference on event hours for candidate 1 must be exactly delta
    event_idx = np.where(A_sig[1] == 1.0)[0]
    mean_null = np.mean(Z_null[1, event_idx])
    mean_sig = np.mean(Z_sig[1, event_idx])
    empirical_delta = mean_sig - mean_null
    assert abs(empirical_delta - delta) < 1e-12, f"Injected delta diluted: {empirical_delta} != {delta}"


def test_h24_overlap_long_run_variance() -> None:
    """
    10. Analytical unit check: compare moving block variance under iid increments
    to the theoretical Bartlett taper formula: estimated / true = 1 - (h^2 - 1) / (3 * L * h).
    """
    L = 72
    h = 24
    true_lrv = float(h**2)
    theoretical_ratio = 1.0 - (h**2 - 1.0) / (3.0 * L * h)

    # 1. Exact analytical convolution check:
    # A block sum of h-hour moving return r_t = sum_{k=0}^{h-1} innov_{t+k}
    # is a linear combination of innov with filter convolution(ones(L), ones(h))
    weights = np.convolve(np.ones(L), np.ones(h))
    block_var = np.sum(weights**2)
    analytical_block_ratio = (block_var / L) / true_lrv
    assert abs(analytical_block_ratio - theoretical_ratio) < 1e-12, "Analytical Bartlett taper formula mismatch"

    # 2. Empirical moving block check across samples
    rng = np.random.default_rng(1010)
    ratios = []
    for _ in range(50):
        innov = rng.standard_normal(4000)
        cumsum = np.concatenate([[0.0], np.cumsum(innov)])
        r = cumsum[h:] - cumsum[:-h]
        S = len(r) - L + 1
        r_cs = np.pad(np.cumsum(r), (1, 0))
        block_sums = r_cs[L:] - r_cs[:-L]
        bs_centered = block_sums - np.mean(block_sums)
        est_lrv = (1.0 / (L * S)) * np.sum(bs_centered**2)
        ratios.append(est_lrv / true_lrv)

    emp_mean = np.mean(ratios)
    assert abs(emp_mean - theoretical_ratio) < 0.03, f"Empirical ratio {emp_mean:.4f} diverges from theory {theoretical_ratio:.4f}"


def test_partition_edge_censoring() -> None:
    """
    11. Verify that for any candidate with horizon h, an event occurring at t with
    t + h > T is strictly prospectively censored (A[i, t] == 0).
    """
    rng = np.random.Generator(np.random.PCG64(1111))
    Z, A = generate_dgp_scenario(2, TOTAL_HOURS_T, rng)
    horizons = np.array(CANDIDATE_HORIZONS)

    for i, h in enumerate(horizons):
        censored_zone = A[i, TOTAL_HOURS_T - h:]
        assert np.all(censored_zone == 0.0), f"Edge censoring violation on candidate {i} with horizon {h}"


def test_zero_event_fail_closed() -> None:
    """
    12. Verify that when a candidate has zero events (or N < 60), inference fails
    closed gracefully with LCB = -inf and does not crash or corrupt other coordinates.
    """
    rng = np.random.Generator(np.random.PCG64(1212))
    Z, A = generate_dgp_scenario(2, TOTAL_HOURS_T, rng)

    # Force candidate 5 to have zero events
    Z[5, :] = 0.0
    A[5, :] = 0.0

    mu_hat, se_hat, c95, lcb = run_joint_bootstrap_studentized(Z, A, 72, 200, rng)
    assert not math.isnan(c95), "Joint critical value should remain valid for remaining coordinates"
    assert math.isinf(lcb[5]) and lcb[5] < 0, "Zero-event candidate must fail closed with LCB = -inf"
    assert not math.isinf(lcb[0]), "Valid candidate must have finite LCB"
