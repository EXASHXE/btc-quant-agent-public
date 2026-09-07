"""Corrected, scale-invariant inference for the H39 formal evaluator.

This module deliberately contains no data loading.  The formal estimand is the
coefficient of the part of a candidate feature that is outside the linear span
of the frozen baseline controls, for the continuous future return target.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

H39_CORRECTED_EVALUATOR_VERSION = "H39_CONDITIONAL_OLS_HAC_V1"
H39_OBSERVATION_CADENCE_MS = 15 * 60_000
H39_PRIMARY_HORIZON_MS = 60 * 60_000
H39_PRIMARY_HAC_LAG = math.ceil(H39_PRIMARY_HORIZON_MS / H39_OBSERVATION_CADENCE_MS) - 1
H39_COLLINEAR_RESIDUAL_FRACTION_TOL = 1e-6
H39_MAX_FULL_DESIGN_CONDITION = 1e8


@dataclass(frozen=True)
class ConditionalIncrementalResult:
    status: str
    reason: str | None
    method: str
    sample_size: int
    effect_estimate: float
    standard_error_hac: float
    t_statistic_hac: float
    p_value_one_sided: float
    ci_lower_95: float
    ci_upper_95: float
    expected_sign: int
    sign_correct: bool
    ci_excludes_zero_in_correct_direction: bool
    candidate_residual_fraction: float
    full_design_condition_number: float
    baseline_rank: int
    full_rank: int
    hac_max_lag: int
    observation_cadence_ms: int
    timestamp_pair_counts: tuple[int, ...]
    iid_standard_error: float
    iid_t_statistic: float

    @property
    def testable(self) -> bool:
        return self.status == "TESTABLE"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _not_testable(
    *,
    reason: str,
    n: int,
    expected_sign: int,
    residual_fraction: float = 0.0,
    condition_number: float = math.inf,
    baseline_rank: int = 0,
    full_rank: int = 0,
    max_lag: int = H39_PRIMARY_HAC_LAG,
    cadence_ms: int = H39_OBSERVATION_CADENCE_MS,
) -> ConditionalIncrementalResult:
    return ConditionalIncrementalResult(
        status="NOT_TESTABLE",
        reason=reason,
        method=H39_CORRECTED_EVALUATOR_VERSION,
        sample_size=n,
        effect_estimate=0.0,
        standard_error_hac=math.inf,
        t_statistic_hac=0.0,
        p_value_one_sided=1.0,
        ci_lower_95=-math.inf,
        ci_upper_95=math.inf,
        expected_sign=expected_sign,
        sign_correct=False,
        ci_excludes_zero_in_correct_direction=False,
        candidate_residual_fraction=residual_fraction,
        full_design_condition_number=condition_number,
        baseline_rank=baseline_rank,
        full_rank=full_rank,
        hac_max_lag=max_lag,
        observation_cadence_ms=cadence_ms,
        timestamp_pair_counts=tuple(0 for _ in range(max_lag + 1)),
        iid_standard_error=math.inf,
        iid_t_statistic=0.0,
    )


def _one_sided_normal_p(t_stat: float, expected_sign: int) -> float:
    directed = float(expected_sign) * t_stat
    return float(0.5 * math.erfc(directed / math.sqrt(2.0)))


def conditional_incremental_ols_hac(
    *,
    future_returns: Sequence[float],
    baseline_controls: Sequence[Sequence[float]],
    candidate: Sequence[float],
    timestamps_ms: Sequence[int],
    expected_sign: int = 1,
    cadence_ms: int = H39_OBSERVATION_CADENCE_MS,
    horizon_ms: int = H39_PRIMARY_HORIZON_MS,
    collinear_tolerance: float = H39_COLLINEAR_RESIDUAL_FRACTION_TOL,
    max_condition_number: float = H39_MAX_FULL_DESIGN_CONDITION,
) -> ConditionalIncrementalResult:
    """Test candidate information conditional on baseline controls using FWL OLS.

    Baseline columns and the candidate are standardized before an unpenalized
    SVD projection.  The candidate residual is standardized again, so positive
    rescaling of either nuisance variables or the candidate cannot change the
    statistic or its effect interpretation.  Exact and near baseline-span
    candidates fail closed as ``NOT_TESTABLE``.

    HAC pairs are selected by physical timestamp difference rather than filtered
    row adjacency.  Irregular grids are accepted only when all timestamps remain
    on the declared cadence grid; missing slots simply remove unavailable pairs.
    """
    y = np.asarray(future_returns, dtype=np.float64)
    base = np.asarray(baseline_controls, dtype=np.float64)
    x = np.asarray(candidate, dtype=np.float64)
    ts = np.asarray(timestamps_ms, dtype=np.int64)
    n = int(y.size)
    max_lag = math.ceil(horizon_ms / cadence_ms) - 1

    if expected_sign not in {-1, 1}:
        raise ValueError("expected_sign must be -1 or 1")
    if n < 8 or x.shape != (n,) or ts.shape != (n,) or base.ndim != 2 or base.shape[0] != n:
        return _not_testable(
            reason="INVALID_OR_INSUFFICIENT_SHAPES",
            n=n,
            expected_sign=expected_sign,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    if not np.all(np.isfinite(y)) or not np.all(np.isfinite(base)) or not np.all(np.isfinite(x)):
        return _not_testable(
            reason="NON_FINITE_INPUT",
            n=n,
            expected_sign=expected_sign,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    if np.any(np.diff(ts) <= 0):
        return _not_testable(
            reason="TIMESTAMPS_NOT_STRICTLY_INCREASING",
            n=n,
            expected_sign=expected_sign,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    if np.any((ts - ts[0]) % cadence_ms != 0):
        return _not_testable(
            reason="TIMESTAMPS_OFF_CADENCE_GRID",
            n=n,
            expected_sign=expected_sign,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )

    # Drop constant nuisance columns; they add no information beyond the intercept.
    base_sd = np.std(base, axis=0, ddof=0)
    keep = base_sd > np.finfo(np.float64).eps * 100.0
    base_z = (
        (base[:, keep] - np.mean(base[:, keep], axis=0)) / base_sd[keep]
        if np.any(keep)
        else np.empty((n, 0))
    )
    x_sd = float(np.std(x, ddof=0))
    if not math.isfinite(x_sd) or x_sd <= np.finfo(np.float64).eps * 100.0:
        return _not_testable(
            reason="CONSTANT_CANDIDATE",
            n=n,
            expected_sign=expected_sign,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    x_z = (x - float(np.mean(x))) / x_sd

    x0 = np.column_stack((np.ones(n, dtype=np.float64), base_z))
    baseline_rank = int(np.linalg.matrix_rank(x0))
    if baseline_rank != x0.shape[1]:
        return _not_testable(
            reason="RANK_DEFICIENT_BASELINE",
            n=n,
            expected_sign=expected_sign,
            baseline_rank=baseline_rank,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )

    gamma = np.linalg.lstsq(x0, x_z, rcond=None)[0]
    x_resid = x_z - x0 @ gamma
    residual_fraction = float(np.linalg.norm(x_resid) / np.linalg.norm(x_z))
    full = np.column_stack((x0, x_z))
    full_rank = int(np.linalg.matrix_rank(full))
    condition_number = float(np.linalg.cond(full))
    if full_rank != full.shape[1] or residual_fraction <= collinear_tolerance:
        return _not_testable(
            reason="CANDIDATE_IN_BASELINE_SPAN",
            n=n,
            expected_sign=expected_sign,
            residual_fraction=residual_fraction,
            condition_number=condition_number,
            baseline_rank=baseline_rank,
            full_rank=full_rank,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    if not math.isfinite(condition_number) or condition_number > max_condition_number:
        return _not_testable(
            reason="NEAR_COLLINEAR_CANDIDATE",
            n=n,
            expected_sign=expected_sign,
            residual_fraction=residual_fraction,
            condition_number=condition_number,
            baseline_rank=baseline_rank,
            full_rank=full_rank,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )

    # Standardized incremental residual gives a scale-stable effect (return per
    # one standard deviation of baseline-orthogonal candidate information).
    xr_sd = float(np.std(x_resid, ddof=0))
    if xr_sd <= np.finfo(np.float64).eps * 100.0:
        return _not_testable(
            reason="ZERO_VARIANCE_CANDIDATE_RESIDUAL",
            n=n,
            expected_sign=expected_sign,
            residual_fraction=residual_fraction,
            condition_number=condition_number,
            baseline_rank=baseline_rank,
            full_rank=full_rank,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    xr = x_resid / xr_sd
    y_resid = y - x0 @ np.linalg.lstsq(x0, y, rcond=None)[0]
    xx = float(xr @ xr)
    beta = float((xr @ y_resid) / xx)
    residuals = y_resid - beta * xr
    scores = xr * residuals

    timestamp_index = {int(value): idx for idx, value in enumerate(ts)}
    long_run_sum = float(scores @ scores)
    pair_counts = [n]
    for lag in range(1, max_lag + 1):
        delta = lag * cadence_ms
        cross_sum = 0.0
        pairs = 0
        for idx, stamp in enumerate(ts):
            prior = timestamp_index.get(int(stamp) - delta)
            if prior is not None:
                cross_sum += float(scores[idx] * scores[prior])
                pairs += 1
        weight = 1.0 - lag / (max_lag + 1.0)
        long_run_sum += 2.0 * weight * cross_sum
        pair_counts.append(pairs)

    if not math.isfinite(long_run_sum) or long_run_sum <= np.finfo(np.float64).eps:
        return _not_testable(
            reason="NON_POSITIVE_HAC_VARIANCE",
            n=n,
            expected_sign=expected_sign,
            residual_fraction=residual_fraction,
            condition_number=condition_number,
            baseline_rank=baseline_rank,
            full_rank=full_rank,
            max_lag=max_lag,
            cadence_ms=cadence_ms,
        )
    var_hac = long_run_sum / (xx * xx)
    se_hac = math.sqrt(var_hac)
    t_hac = beta / se_hac
    p_value = _one_sided_normal_p(t_hac, expected_sign)
    ci_lower = beta - 1.96 * se_hac
    ci_upper = beta + 1.96 * se_hac

    df = max(1, n - x0.shape[1] - 1)
    iid_var = float(residuals @ residuals) / df / xx
    iid_se = math.sqrt(max(iid_var, 0.0))
    iid_t = beta / iid_se if iid_se > 0 else 0.0
    sign_correct = beta * expected_sign > 0.0
    ci_excludes = ci_lower > 0.0 if expected_sign == 1 else ci_upper < 0.0
    return ConditionalIncrementalResult(
        status="TESTABLE",
        reason=None,
        method=H39_CORRECTED_EVALUATOR_VERSION,
        sample_size=n,
        effect_estimate=beta,
        standard_error_hac=se_hac,
        t_statistic_hac=t_hac,
        p_value_one_sided=p_value,
        ci_lower_95=ci_lower,
        ci_upper_95=ci_upper,
        expected_sign=expected_sign,
        sign_correct=sign_correct,
        ci_excludes_zero_in_correct_direction=ci_excludes,
        candidate_residual_fraction=residual_fraction,
        full_design_condition_number=condition_number,
        baseline_rank=baseline_rank,
        full_rank=full_rank,
        hac_max_lag=max_lag,
        observation_cadence_ms=cadence_ms,
        timestamp_pair_counts=tuple(pair_counts),
        iid_standard_error=iid_se,
        iid_t_statistic=iid_t,
    )
