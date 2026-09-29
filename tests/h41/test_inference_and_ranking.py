from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from btc_quant_agent.h41.authority import CANDIDATES
from btc_quant_agent.h41.inference import (
    infer_with_testability,
    run_frozen_joint_inference,
    run_joint_bootstrap_studentized,
)
from btc_quant_agent.h41.science import HOUR_MS, PARTITIONS, Event, EventBatch
from btc_quant_agent.h41.selection import CandidateInference, rank_positive_lcb
from btc_quant_agent.h41.testability import H41State, make_testability_receipt

from .r2_reference import run_joint_bootstrap_studentized as accepted_r2


def _synthetic_matrices() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(81)
    a = (rng.random((20, 2184)) < .2).astype(np.float64)
    a[0] = 0  # Explicit zero-event candidate.
    signal = rng.normal(.0002, .004, size=(20, 2184))
    signal[:, :140] += .003  # Overlapping-block center differs from sample mean.
    return a * signal, a


def test_exact_stage_r2_numerical_replay() -> None:
    z, a = _synthetic_matrices()
    seed = 301
    actual = run_joint_bootstrap_studentized(z, a, 120, 250,
                                              np.random.default_rng(seed))
    expected = accepted_r2(z, a, 120, 250, np.random.default_rng(seed))
    for left, right in zip(actual, expected, strict=True):
        np.testing.assert_array_equal(left, right)
    assert actual[3][0] == -np.inf
    z_blocks = np.cumsum(np.pad(z[1], (1, 0)))[120:] - np.cumsum(np.pad(z[1], (1, 0)))[:-120]
    a_blocks = np.cumsum(np.pad(a[1], (1, 0)))[120:] - np.cumsum(np.pad(a[1], (1, 0)))[:-120]
    center = np.sum(z_blocks) / np.sum(a_blocks)
    mu = np.sum(z[1]) / np.sum(a[1])
    assert center != mu


def test_frozen_runner_uses_120h_10000_draws() -> None:
    z, a = _synthetic_matrices()
    actual = run_frozen_joint_inference(z, a, np.random.default_rng(45))
    expected = accepted_r2(z, a, 120, 10_000, np.random.default_rng(45))
    for left, right in zip(actual, expected, strict=True):
        np.testing.assert_array_equal(left, right)


def test_permutation_invariance_and_zero_support() -> None:
    z, a = _synthetic_matrices()
    order = np.arange(20)[::-1]
    direct = run_joint_bootstrap_studentized(z, a, 120, 100, np.random.default_rng(11))
    permuted = run_joint_bootstrap_studentized(z[order], a[order], 120, 100,
                                                np.random.default_rng(11))
    for i in (0, 1, 3):
        np.testing.assert_array_equal(direct[i][order], permuted[i])
    assert direct[2] == permuted[2]


def test_occupied_day_floor_cannot_be_forged_into_inference() -> None:
    start = PARTITIONS['WF1_CALIBRATION'][0]
    times = sorted(start + (i % 29) * 24 * HOUR_MS + (i // 29) * HOUR_MS
                   for i in range(60))
    batches = tuple(EventBatch(c.candidate_id, 'WF1_CALIBRATION',
                               tuple(Event(t, 1, c.horizon_hours) for t in times) if i == 0 else ())
                    for i, c in enumerate(CANDIDATES))
    receipts = tuple(make_testability_receipt(batch) for batch in batches)
    assert receipts[0].state == H41State.BASIC_SUPPORT_UNAVAILABLE
    a = np.zeros((20, 2184))
    z = np.zeros((20, 2184))
    for t in times:
        index = (t - start) // HOUR_MS
        a[0, index] = 1
        z[0, index] = .01
    _, _, c95, lcb = infer_with_testability(z, a, receipts, batches,
                                             np.random.default_rng(2))
    assert np.isnan(c95)
    assert np.all(lcb == -np.inf)
    forged = (replace(receipts[0], occupied_calendar_days_D=30,
                      state=H41State.TESTABLE_EXPLORATORY),) + receipts[1:]
    with pytest.raises(ValueError, match='lineage'):
        infer_with_testability(z, a, forged, batches, np.random.default_rng(2))
    z[1, 0] = .01
    with pytest.raises(ValueError, match='original event mask'):
        infer_with_testability(z, a, receipts, batches, np.random.default_rng(2))


def test_lcb_ranking_beats_point_estimate_then_n_then_id() -> None:
    a, b, c = (row.candidate_id for row in CANDIDATES[:3])
    def full(rows: list[CandidateInference]) -> list[CandidateInference]:
        ids = {row.candidate_id for row in rows}
        return rows + [CandidateInference(row.candidate_id, -np.inf, 0, 0, 0)
                       for row in CANDIDATES if row.candidate_id not in ids]
    rows = [CandidateInference(a, .01, 100, .3, 30), CandidateInference(b, .02, 60, .1, 30)]
    assert [row.candidate_id for row in rank_positive_lcb(full(rows))] == [b, a]
    rows = [CandidateInference(a, .02, 100, .1, 30), CandidateInference(b, .02, 101, .1, 30)]
    assert rank_positive_lcb(full(rows))[0].candidate_id == b
    rows = [CandidateInference(b, .02, 100, .1, 30), CandidateInference(a, .02, 100, .1, 30)]
    assert rank_positive_lcb(full(rows))[0].candidate_id == min(a, b)
    rows.append(CandidateInference(c, float('nan'), 999, 2, 30))
    assert len(rank_positive_lcb(full(rows))) == 2
    with pytest.raises(ValueError):
        rank_positive_lcb([rows[0], rows[0]])
    with pytest.raises(ValueError, match="complete"):
        rank_positive_lcb(rows)
    unsupported = full([CandidateInference(a, .1, 59, .2, 30),
                        CandidateInference(b, .1, 60, .2, 29)])
    assert rank_positive_lcb(unsupported) == ()
