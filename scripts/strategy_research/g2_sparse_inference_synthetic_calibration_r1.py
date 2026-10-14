"""Invented-data-only sparse inference calibration; no historical result use.

PRE-REGISTRATION (fixed before simulation): seeds 20261014/20261015, 512 trials
per cell, 199 shared-index bootstrap resamples (2000 for the failure exhibit),
six arms, two-sided family alpha .05, and the finite DGP/grid below. All values
are invented basis points of additive total per calendar week, NOT per trade.
Equal-week means retain empty weeks. Unequal event counts do not change weights.

CANDIDATE: nonstudentized max absolute mean error, bounded by Chebyshev and a
union bound. For independent units i, arm a, predeclared Var(X_ia) <= v_ia:
Var(mean_a) <= sum_i(v_ia)/n**2 = V_a; P(max_a |mean_a-mu_a| > h)
<= sum_a V_a/h**2 <= alpha, with h=sqrt(sum_a V_a/alpha). Thus all
mean_a +/- h intervals cover simultaneously with probability at least 1-alpha.
Arms may be dependent; units must be independent. Means can vary across units:
the estimand is the average of their population means. This is deliberately
conservative, finite-variance inference, not a sample-variance estimate or SE
floor repair. Bounds cannot be estimated from these outcomes. All-zero observed
data alone never justify a zero bound. A zero POPULATION variance bound does.
Unbounded/infinite-variance tails and unknown cluster dependence are unsupported.

Clustered weeks must be collapsed into predeclared independent superclusters;
here each cluster has four weeks and their average is one unit. Do not claim
independence from a small observed autocorrelation or discard empty weeks.
Future adoption requires a separately governed, outcome-blind variance envelope,
cluster definition, family, estimand, alpha and power plan, and ChatGPT-3 science
Challenger review. This script cannot infer those from F1-F3. Historical intervals
remain SIMULTANEOUS_INFERENCE_UNCALIBRATED; no Alpha/Mark/basis claim is licensed.

Calibration gate: every candidate null cell must have its multiplicity-adjusted
Monte Carlo FWER upper bound <= .05 and simultaneous coverage lower bound >= .95.
Wilson intervals quantify simulation uncertainty; the analytic bound supplies
the actual guarantee under the stated assumptions. No post-run threshold tuning.
Positive effects are only explicitly planted synthetic effects. The CLI has no
data path, input file, seed sweep, or protected-input option; it emits JSON stdout.
Exactly two new repository files are authorized. Evidence may be captured outside
the repository. G2_ALPHA_NO_GO / TESTNET_NOT_AUTHORIZED / LIVE_NOT_AUTHORIZED /
REAL_FUNDS_WRITE_NONE always apply. Independent review is pending, never attested.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
import subprocess
import sys
from pathlib import Path
from statistics import NormalDist
from types import ModuleType

import numpy as np

AUTHORITY_SHA = "ceb851765b84e8e83b78caa6ceecbc665e57c02f"
PROMPT_PATH = "prompts/v0.6/b_line/V06_RESET_R1_SPARSE_INFERENCE_SYNTHETIC.md"
PROMPT_BLOB = "dc0c73f07fbfeba3ebc54160a1bac647607a5a6d"
BASE_SHA = "13e3a710b137efeec2e21e3002f748834ec0cc22"
OLD_SHA = "f25954b45577cebb7624fae86cd91df9071a87ab"
OLD_PATH = "scripts/strategy_research/g2_flow_funding_entries_r1/statistics.py"
OLD_BLOB = "f86ee6c20c8bc08f0e42dcb4d586b4d908290018"
ROOT_DOC_PARENT = "5d0e639f76d58f7adb3809801421e2b053955d91"
ROOT = Path(__file__).resolve().parents[2]
CODE_PATH = "scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py"
TEST_PATH = "tests/test_v06_g2_sparse_inference_synthetic_calibration_r1.py"
SEEDS = (20261014, 20261015)
TRIALS = 512
BOOTSTRAPS = 199
ARMS = 6
ALPHA = 0.05
MC_FAMILY_ERROR = 0.01
SCENARIOS = (
    "all_zero", "sparse_97pct_empty", "constant_shift_null", "unequal_event_counts",
    "clustered_four_weeks", "degenerate_arm", "heavy_tail_t3",
    "sign_flipped_skew", "multi_arm_gaussian", "rare_asymmetric_null",
)
FUTURE_GRID = tuple(itertools.product((26, 52, 104, 208), (0.05, 0.25, 1.0), (1, 5, 15)))
PLANTED_EVENT_EFFECT_BPS = 5.0
EVENT_NOISE_SD_BPS = 2.0
TARGET_POWER = 0.8
# Coverage and FWER for two methods, plus future power, for both seeds.
MC_CELLS = len(SEEDS) * (len(SCENARIOS) * 2 * 2 + len(FUTURE_GRID) * 2)
MC_Z = NormalDist().inv_cdf(1 - MC_FAMILY_ERROR / (2 * MC_CELLS))


def git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True
    ).stdout


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def verified_method_source() -> ModuleType:
    """Read ONLY the pinned old method source, never its runner or results."""
    for sha, path, expected in (
        (AUTHORITY_SHA, PROMPT_PATH, PROMPT_BLOB), (OLD_SHA, OLD_PATH, OLD_BLOB),
    ):
        data = git_bytes("show", f"{sha}:{path}")
        if git_blob(data) != expected:
            raise RuntimeError(f"Immutable source blob mismatch: {path}")
        if path == OLD_PATH:
            source = data
    module = ModuleType("immutable_synthetic_method_reference")
    # Source is a pinned, SHA-verified method blob; no supplied code or data paths.
    exec(compile(source, f"{OLD_SHA}:{OLD_PATH}", "exec"), module.__dict__)  # noqa: S102
    return module


def candidate_intervals(
    units_bps: np.ndarray, variance_upper_bps2: np.ndarray, *, independent_units: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Population bounds are EX ANTE, never fit to units; same-unit arms may correlate."""
    x = np.asarray(units_bps, dtype=float)
    v = np.asarray(variance_upper_bps2, dtype=float)
    if (
        not independent_units or x.ndim != 2 or not all(x.shape) or v.shape != x.shape
        or not np.isfinite(x).all() or not np.isfinite(v).all() or (v < 0).any()
    ):
        raise ValueError("Require finite data, ex-ante finite variance bounds and independent units")
    h = math.sqrt(float(v.sum()) / (x.shape[0] ** 2 * ALPHA))
    if not math.isfinite(h):
        raise ValueError("Variance envelope overflow")
    center = x.mean(axis=0)
    return center - h, center + h


def legacy_intervals(
    weeks_bps: np.ndarray, rng: np.random.Generator, rounds: int = BOOTSTRAPS,
) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """Vectorized exact pinned clipped-SE formula, verified against immutable function.

    Shared indices across arms; the old baseline uses 1e-6 only when std==0,
    whereas resampled SE is max(SE,1e-6). Alpha is the old hardcoded .05.
    """
    n = len(weeks_bps)
    mean = weeks_bps.mean(axis=0)
    sd = weeks_bps.std(axis=0, ddof=1) if n > 1 else np.zeros(weeks_bps.shape[1])
    se = np.where(sd > 0, sd / math.sqrt(n), 1e-6)
    indices = rng.integers(0, n, size=(rounds, n))
    samples = weeks_bps[indices]
    boot_mean = samples.mean(axis=1)
    boot_se = (
        samples.std(axis=1, ddof=1) / math.sqrt(n)
        if n > 1 else np.full_like(boot_mean, 1e-6)
    )
    clipped_se = np.maximum(boot_se, 1e-6)
    max_t = (np.abs(boot_mean - mean) / clipped_se).max(axis=1)
    q = float(np.percentile(max_t, 95))
    return mean - q * se, mean + q * se, {
        "q95_max_t": q,
        "zero_variance_resample_fraction": float(np.mean((boot_se == 0).any(axis=1))),
        "zero_variance_nonzero_error_resample_fraction": float(np.mean(
            ((boot_se == 0) & (np.abs(boot_mean - mean) > 0)).any(axis=1)
        )),
        "max_nonstudentized_error_bps": float(np.abs(boot_mean - mean).max()),
    }


def wilson(count: int, total: int) -> dict[str, object]:
    p = count / total
    z2 = MC_Z ** 2
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    radius = MC_Z * math.sqrt(p * (1 - p) / total + z2 / (4 * total ** 2)) / (
        1 + z2 / total
    )
    return {"count": count, "trials": total, "rate": p,
            "mc_interval": [max(0.0, center - radius), min(1.0, center + radius)]}


def invented_null(
    name: str, rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return raw weeks, independent-unit means, their known variance envelopes.

    Every arm has true mean ZERO. Constant-shift null has only ONE independent
    unit: all 32 weeks equal a common +/-2 bps shock. Clustered shocks are repeated
    for four weeks plus iid .1 bps noise. Rare-asymmetric null is 100*(Bernoulli
    .001-.001), mean 0 and variance 9.99 bps^2. t3 has known variance 3 bps^2;
    no clipping/truncation of heavy tails occurs. Event counts are fixed 1/2/5/9;
    weekly total is their sum of independent N(0,1) invented event contributions.
    """
    n = 32
    shape = (n, ARMS)
    if name == "all_zero":
        x, v = np.zeros(shape), 0.0
    elif name == "sparse_97pct_empty":
        x = rng.binomial(1, 0.025, shape) * rng.choice((-10., 10.), shape)
        v = 2.5
    elif name == "constant_shift_null":
        unit = rng.choice((-2., 2.), (1, ARMS))
        return np.repeat(unit, n, axis=0), unit, np.full_like(unit, 4.)
    elif name == "unequal_event_counts":
        counts = np.resize(np.array([1, 2, 5, 9]), n)[:, None]
        x = rng.normal(size=shape) * np.sqrt(counts)
        return x, x, np.broadcast_to(counts, shape).astype(float)
    elif name == "clustered_four_weeks":
        shock = rng.normal(size=shape)
        weeks = np.repeat(shock, 4, axis=0) + rng.normal(0, .1, (4 * n, ARMS))
        units = weeks.reshape(n, 4, ARMS).mean(axis=1)
        return weeks, units, np.full(shape, 1 + .01 / 4)
    elif name == "degenerate_arm":
        x = rng.normal(size=shape)
        x[:, 0] = 0
        v = np.ones(shape)
        v[:, 0] = 0
    elif name == "heavy_tail_t3":
        x, v = rng.standard_t(3, shape), 3.0
    elif name == "sign_flipped_skew":
        x = (rng.exponential(size=shape) - 1) * rng.choice((-1., 1.), (n, 1))
        v = 1.0
    elif name == "multi_arm_gaussian":
        x, v = rng.normal(size=shape), 1.0
    elif name == "rare_asymmetric_null":
        x, v = 100 * (rng.binomial(1, .001, shape) - .001), 9.99
    else:
        raise ValueError(f"Unregistered DGP: {name}")
    return x, x, np.broadcast_to(v, shape).copy()


def null_calibration(seed: int) -> list[dict[str, object]]:
    result = []
    for index, name in enumerate(SCENARIOS):
        dgp_rng = np.random.default_rng(np.random.SeedSequence([seed, 0, index]))
        boot_rng = np.random.default_rng(np.random.SeedSequence([seed, 1, index]))
        misses = {"legacy": 0, "candidate": 0}
        for _ in range(TRIALS):
            weeks, units, v = invented_null(name, dgp_rng)
            old_lo, old_hi, _ = legacy_intervals(weeks, boot_rng)
            lo, hi = candidate_intervals(units, v, independent_units=True)
            misses["legacy"] += int(((old_lo > 0) | (old_hi < 0)).any())
            misses["candidate"] += int(((lo > 0) | (hi < 0)).any())
        for method, failures in misses.items():
            result.append({"seed": seed, "dgp": name, "method": method,
                           "true_means_bps": [0.] * ARMS,
                           "type_i_fwer": wilson(failures, TRIALS),
                           "simultaneous_ci_coverage": wilson(TRIALS - failures, TRIALS)})
    return result


def future_feasibility(seed: int) -> list[dict[str, object]]:
    """Outcome-blind grid; effect 5 bps/event, expected weekly effect p*5 bps.

    Events are independent Bernoulli(p) per effective week; event noise SD=2 bps,
    cost noise SD in {1,5,15} bps, both centered Gaussians, independent of events.
    Only arm 0 receives the planted net effect; no historical costs or returns.
    Variance envelope p*(4+c^2)+p*(1-p)*25 covers all arms under this alternative
    AND the zero-effect null. Future power is arm-0 positive exclusion, not any
    rejection. A support row reports expected occupied independent weeks and
    P(any event). Guaranteed power lower bound uses Chebyshev on the miss event.
    Feasible means that lower bound >= .8, not an empirical threshold selection.
    """
    rows = []
    for index, (n, p, cost_sd) in enumerate(FUTURE_GRID):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 2, index]))
        boot_rng = np.random.default_rng(np.random.SeedSequence([seed, 3, index]))
        mu = p * PLANTED_EVENT_EFFECT_BPS
        v = p * (EVENT_NOISE_SD_BPS ** 2 + cost_sd ** 2) + p * (1 - p) * 25
        h = math.sqrt(ARMS * v / (n * ALPHA))
        power_bound = max(0., 1 - v / (n * (mu - h) ** 2)) if mu > h else 0.
        minimum_n = math.ceil(
            (math.sqrt(ARMS * v / ALPHA) + math.sqrt(v / (1 - TARGET_POWER))) ** 2
            / mu ** 2
        )
        planted_rejects = old_rejects = 0
        for _ in range(TRIALS):
            active = rng.binomial(1, p, (n, ARMS))
            x = active * rng.normal(0, math.sqrt(4 + cost_sd ** 2), (n, ARMS))
            x[:, 0] += active[:, 0] * PLANTED_EVENT_EFFECT_BPS
            lo, _hi = candidate_intervals(x, np.full_like(x, v), independent_units=True)
            planted_rejects += int(lo[0] > 0)
            # The old comparison is restricted to the same finite planted grid;
            # resampling has a separate stream and cannot perturb the DGP stream.
            old_lo, _, _details = legacy_intervals(x, boot_rng)
            old_rejects += int(old_lo[0] > 0)
        rows.append({"seed": seed, "effective_independent_weeks": n,
                     "event_probability_per_week": p, "cost_noise_sd_bps_per_event": cost_sd,
                     "expected_occupied_weeks": n * p, "probability_any_event": 1 - (1 - p) ** n,
                     "planted_net_effect_bps_per_event": PLANTED_EVENT_EFFECT_BPS,
                     "true_mean_bps_per_week_arm0": mu, "variance_envelope_bps2": v,
                     "candidate_half_width_bps": h,
                     "candidate_power": wilson(planted_rejects, TRIALS),
                     "legacy_power": wilson(old_rejects, TRIALS),
                     "guaranteed_power_lower_bound": power_bound,
                     "minimum_independent_weeks_for_80pct_guaranteed_power": minimum_n,
                     "feasible_at_predeclared_target": power_bound >= TARGET_POWER})
    return rows


def failure_exhibit() -> dict[str, object]:
    """Fixed realization of iid 10*Bernoulli(1/32); old 2000 resamples.

    This hand-constructed exhibit is not a coverage experiment. The candidate
    uses this INVENTED DGP's population variance, not a sample-based estimate.
    """
    x = np.zeros((32, ARMS))
    x[0, 0] = 10
    lo, hi, details = legacy_intervals(x, np.random.default_rng(SEEDS[0]), 2000)
    v = np.zeros_like(x)
    v[:, 0] = 100 * (1 / 32) * (31 / 32)
    candidate_lo, candidate_hi = candidate_intervals(x, v, independent_units=True)
    return {"invented": True, "weeks": 32, "single_event_bps": 10.,
            "empty_week_fraction": 31 / 32, "mean_bps": 10 / 32,
            "exact_probability_event_omitted": (31 / 32) ** 32,
            "omission_centered_mean_error_bps": 10 / 32,
            "omission_clipped_t": (10 / 32) / 1e-6,
            "legacy_arm0_ci_bps": [float(lo[0]), float(hi[0])],
            "candidate_exhibit_dgp": "iid weekly 10*Bernoulli(1/32), arm0 only",
            "candidate_true_mean_bps": 10 / 32,
            "candidate_arm0_ci_bps": [float(candidate_lo[0]), float(candidate_hi[0])], **details}


def provenance() -> dict[str, object]:
    verified_method_source()
    git_bytes("merge-base", "--is-ancestor", BASE_SHA, "HEAD")
    files = {path: (ROOT / path).read_bytes() for path in (CODE_PATH, TEST_PATH)}
    return {"authority_commit": AUTHORITY_SHA, "prompt_git_blob": PROMPT_BLOB,
            "root_doc_parent": ROOT_DOC_PARENT, "code_base_commit": BASE_SHA,
            "old_method_commit": OLD_SHA, "old_method_git_blob": OLD_BLOB,
            "execution_commit": git_bytes("rev-parse", "HEAD").decode().strip(),
            "execution_tree": git_bytes("rev-parse", "HEAD^{tree}").decode().strip(),
            "source_git_blobs": {p: git_blob(b) for p, b in files.items()},
            "source_sha256": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()},
            "worktree_dirty": bool(git_bytes("status", "--porcelain")),
            "python": platform.python_version(), "numpy": np.__version__,
            "input_reads": [f"git:{AUTHORITY_SHA}:{PROMPT_PATH}",
                            f"git:{OLD_SHA}:{OLD_PATH}", CODE_PATH, TEST_PATH],
            "historical_outcome_inputs": [], "protected_inputs": [],
            "historical_returns_recalculated": False}


def calibrated(rows: list[dict[str, object]]) -> bool:
    candidate = [row for row in rows if row["method"] == "candidate"]
    # Require the exact predeclared cell set, not vacuous pass or omitted failures.
    if len(candidate) != len(SEEDS) * len(SCENARIOS) or {
        (r["seed"], r["dgp"]) for r in candidate
    } != set(itertools.product(SEEDS, SCENARIOS)):
        return False
    return all(r["type_i_fwer"]["mc_interval"][1] <= ALPHA and
               r["simultaneous_ci_coverage"]["mc_interval"][0] >= 1 - ALPHA
               for r in candidate)


def report() -> dict[str, object]:
    receipt = provenance()
    null_rows = [row for seed in SEEDS for row in null_calibration(seed)]
    power_rows = [row for seed in SEEDS for row in future_feasibility(seed)]
    return {"declaration": "ALL SIMULATED VALUES INVENTED; SYNTHETIC ONLY",
            "status": "METHOD_CANDIDATE_CALIBRATED_ON_SYNTHETIC_ONLY"
            if calibrated(null_rows) else "METHOD_BLOCKED",
            "historical_inference": "SIMULTANEOUS_INFERENCE_UNCALIBRATED",
            "authorization": ["G2_ALPHA_NO_GO", "TESTNET_NOT_AUTHORIZED",
                              "LIVE_NOT_AUTHORIZED", "REAL_FUNDS_WRITE_NONE"],
            "independent_review": "PENDING_CHATGPT_3_SCIENCE_CHALLENGER_BEFORE_ADOPTION",
            "candidate": "Nonstudentized max-mean Chebyshev union-bound simultaneous CI",
            "required_scope": "Known ex-ante finite variance bounds and independent units",
            "statistic_units": "bps of additive weekly totals, not bps per event",
            "future_adoption_preregistration": ["Outcome-blind finite variance envelopes",
                "Independent supercluster boundaries and target weighting",
                "Complete arm family and nominal alpha", "Fixed event/cost support and power plan",
                "Separate authority for any historical use", "Independent science Challenger review"],
            "unsupported_scope": ["Unknown variance bound", "Infinite variance",
                                  "Unknown between-cluster dependence"],
            "pre_registration": {"seeds": SEEDS, "trials_per_cell": TRIALS,
                                 "bootstrap_rounds": BOOTSTRAPS, "arms": ARMS, "alpha": ALPHA,
                                 "mc_family_error": MC_FAMILY_ERROR, "mc_cells": MC_CELLS,
                                 "mc_interval": "Multiplicity-adjusted two-sided Wilson",
                                 "mc_z": MC_Z, "target_power": TARGET_POWER},
            "provenance": receipt, "old_zero_variance_failure": failure_exhibit(),
            "null_calibration": null_rows, "future_support_power": power_rows}


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("No data inputs or tunable simulation arguments are authorized")
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))
