"""Deterministic invented-only method tests; independent scientist review is pending.

Report contract: two fixed seeds, 512 trials per null/power cell, alpha .05;
FWER and simultaneous coverage with multiplicity-adjusted Wilson uncertainty.
Candidate requires ex-ante finite population variance bounds and independent
units; grouping, estimand, family and costs must be preregistered before adoption.
No test reads historical outcomes or protected inputs. Source-only fidelity
verification invokes the pinned old statistic on fabricated timestamps/values.
No F1-F3 significance or authorization change follows from these tests.
"""

import builtins
import itertools
import math
import socket
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.strategy_research import g2_sparse_inference_synthetic_calibration_r1 as s


@pytest.fixture(scope="module")
def null_results():
    return [row for seed in s.SEEDS for row in s.null_calibration(seed)]


@pytest.mark.parametrize("seed", s.SEEDS)
@pytest.mark.parametrize("case", ("zero", "single_event", "constant", "unequal", "one_unit"))
def test_vectorized_legacy_matches_exact_source_on_invented_inputs(seed, case):
    old = s.verified_method_source()
    x = np.zeros((32, s.ARMS))
    if case == "single_event":
        x[0, 0] = 10
    elif case == "constant":
        x[:] = 2
    elif case == "unequal":
        x = np.random.default_rng(seed).normal(size=x.shape)
        x *= np.resize([1, 2, 5, 9], 32)[:, None]
    elif case == "one_unit":
        x = np.full((1, s.ARMS), 2.)
    day_ms = 86_400_000
    fabricated = {str(a): [{"entry_at": i * 7 * day_ms, "net_after_funding_bps": float(v)}
                          for i, v in enumerate(x[:, a]) if v != 0]
                  for a in range(s.ARMS)}
    reference = old.compute_block_bootstrap_max_t(
        fabricated, 0, len(x) * 7 * day_ms, block_days=7, n_rounds=s.BOOTSTRAPS, seed=seed
    )
    lo, hi, details = s.legacy_intervals(x, np.random.default_rng(seed))
    assert details["q95_max_t"] == pytest.approx(reference["q95_max_t"], rel=1e-12)
    for a in range(s.ARMS):
        assert [lo[a], hi[a]] == pytest.approx(
            reference["intervals"][str(a)]["simultaneous_ci_95"], rel=1e-12, abs=1e-12
        )


def test_zero_variance_max_t_failure_is_demonstrated():
    r = s.failure_exhibit()
    assert r["empty_week_fraction"] > .9
    assert r["exact_probability_event_omitted"] == pytest.approx(.362055289256, rel=1e-10)
    assert r["omission_clipped_t"] == 312500
    assert r["q95_max_t"] == 312500
    assert r["legacy_arm0_ci_bps"][1] > 97000
    assert r["max_nonstudentized_error_bps"] < 5
    assert .3 < r["zero_variance_nonzero_error_resample_fraction"] < .4
    assert r["candidate_arm0_ci_bps"][1] < 2


def test_population_variance_bound_not_observed_zero_variance():
    x = np.zeros((32, s.ARMS))
    lo, hi = s.candidate_intervals(x, np.ones_like(x), independent_units=True)
    assert np.all(lo < 0) and np.all(hi > 0)
    zlo, zhi = s.candidate_intervals(x, np.zeros_like(x), independent_units=True)
    assert np.array_equal(zlo, x.mean(axis=0))
    assert np.array_equal(zlo, zhi)
    x[:] = 2
    lo, hi = s.candidate_intervals(x, np.zeros_like(x), independent_units=True)
    assert np.all(lo == 2) and np.all(hi == 2)


@pytest.mark.parametrize("bad", ("nan", "inf", "negative", "empty", "shape", "dependence"))
def test_candidate_fails_closed_without_its_contract(bad):
    x, v, independent = np.zeros((32, s.ARMS)), np.ones((32, s.ARMS)), True
    if bad in ("nan", "inf", "negative"):
        v[0, 0] = {"nan": np.nan, "inf": np.inf, "negative": -1}[bad]
    elif bad == "empty":
        x, v = x[:0], v[:0]
    elif bad == "shape":
        v = v[:, :1]
    else:
        independent = False
    with pytest.raises(ValueError):
        s.candidate_intervals(x, v, independent_units=independent)


def test_unequal_counts_keep_equal_week_estimand_and_family_correction():
    x = np.array([[0., 0.], [10., 20.]])
    v = np.array([[1., 1.], [9., 9.]])
    lo, hi = s.candidate_intervals(x, v, independent_units=True)
    h = math.sqrt(20 / (4 * .05))
    assert (lo + hi) / 2 == pytest.approx([5., 10.])
    assert hi - x.mean(axis=0) == pytest.approx([h, h])
    single_lo, _ = s.candidate_intervals(x[:, :1], v[:, :1], independent_units=True)
    assert x[:, 0].mean() - lo[0] == pytest.approx(
        math.sqrt(2) * (x[:, 0].mean() - single_lo[0])
    )


def test_clustered_autocorrelation_uses_independent_superclusters():
    weeks, units, v = s.invented_null("clustered_four_weeks", np.random.default_rng(s.SEEDS[0]))
    assert weeks.shape == (128, 6) and units.shape == (32, 6)
    assert np.array_equal(units, weeks.reshape(32, 4, 6).mean(axis=1))
    assert np.corrcoef(weeks[::4, 0], weeks[1::4, 0])[0, 1] > .95
    assert np.all(v == 1.0025)


def test_predeclared_null_fwer_and_coverage_gate(null_results):
    assert s.calibrated(null_results)
    assert len(null_results) == len(s.SEEDS) * len(s.SCENARIOS) * 2
    for row in null_results:
        assert row["type_i_fwer"]["count"] + row["simultaneous_ci_coverage"]["count"] == s.TRIALS
        if row["method"] == "candidate":
            assert row["type_i_fwer"]["mc_interval"][1] <= s.ALPHA
            assert row["simultaneous_ci_coverage"]["mc_interval"][0] >= 1 - s.ALPHA
        elif row["dgp"] == "constant_shift_null":
            assert row["type_i_fwer"]["rate"] == 1
        elif row["dgp"] == "rare_asymmetric_null":
            assert row["type_i_fwer"]["mc_interval"][0] > s.ALPHA


def test_gate_cannot_pass_missing_cells_or_failed_calibration(null_results):
    assert not s.calibrated([])
    assert not s.calibrated([r for r in null_results if r["seed"] == s.SEEDS[0]])
    broken = [dict(row) for row in null_results]
    candidate = next(row for row in broken if row["method"] == "candidate")
    candidate["type_i_fwer"] = s.wilson(s.TRIALS, s.TRIALS)
    assert not s.calibrated(broken)


@pytest.mark.parametrize("seed", s.SEEDS)
def test_null_simulations_reproduce_exactly_for_both_seeds(seed, null_results):
    assert s.null_calibration(seed) == [row for row in null_results if row["seed"] == seed]


@pytest.mark.parametrize("seed", s.SEEDS)
def test_future_support_power_is_invented_and_reproducible(seed):
    rows = s.future_feasibility(seed)
    assert rows == s.future_feasibility(seed)
    assert len(rows) == len(s.FUTURE_GRID)
    assert any(row["feasible_at_predeclared_target"] for row in rows)
    assert any(not row["feasible_at_predeclared_target"] for row in rows)
    for row in rows:
        n, p = row["effective_independent_weeks"], row["event_probability_per_week"]
        assert row["expected_occupied_weeks"] == n * p
        assert row["true_mean_bps_per_week_arm0"] == p * 5
        assert row["feasible_at_predeclared_target"] == (row["guaranteed_power_lower_bound"] >= .8)
        assert row["feasible_at_predeclared_target"] == (
            n >= row["minimum_independent_weeks_for_80pct_guaranteed_power"]
        )


def test_simulations_do_not_access_files_processes_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Simulation crossed invented-data-only boundary")

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", forbidden)
        m.setattr(Path, "open", forbidden)
        m.setattr(s.subprocess, "run", forbidden)
        m.setattr(socket, "socket", forbidden)
        # All finite registered DGPs and statistic paths are guarded here;
        # source provenance/fidelity reads are deliberately outside simulation.
        for index, name in enumerate(s.SCENARIOS):
            weeks, units, v = s.invented_null(name, np.random.default_rng(index))
            s.candidate_intervals(units, v, independent_units=True)
            s.legacy_intervals(weeks, np.random.default_rng(index))


def test_preregistration_is_finite_and_outcome_blind():
    assert s.SEEDS == (20261014, 20261015)
    assert s.TRIALS == 512 and s.BOOTSTRAPS == 199 and s.ALPHA == .05
    assert s.FUTURE_GRID == tuple(itertools.product((26, 52, 104, 208), (.05, .25, 1.), (1, 5, 15)))
    assert s.PLANTED_EVENT_EFFECT_BPS == 5 and s.EVENT_NOISE_SD_BPS == 2
    assert s.MC_Z > 3
