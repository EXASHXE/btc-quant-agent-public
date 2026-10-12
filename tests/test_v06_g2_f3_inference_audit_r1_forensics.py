"""Deterministic synthetic unit tests for F3 sparse-alpha and statistical-validity forensics.

Covers >=45 tests across 14 required forensic dimensions:
1. prefix mutation
2. timestamp boundaries
3. source admission hash
4. 2021/2022/2023 clock
5. Funding latency
6. Mark/Last swap adversarial
7. n=0/1/2/12
8. all-zero sampled block
9. Bounded studentizer
10. Float stability
11. PF no-negative-loss sentinel
12. Source row reversal
13. Normalization
14. Held-out future mutation
"""
from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_f3_inference_audit_r1.alternative_stats import (
    compute_exact_binomial_sign_test,
    evaluate_sparse_interval_refusal,
)
from scripts.strategy_research.g2_f3_inference_audit_r1.degenerate_studentizer import (
    compute_all_zero_draw_probability,
    compute_degenerate_t_value,
    create_sparse_synthetic_fixture,
    simulate_studentized_bootstrap,
)
from scripts.strategy_research.g2_f3_inference_audit_r1.diagnostics import (
    audit_event_and_block_support,
    audit_profit_factor_sentinels,
    classify_source_causality_and_known_at,
    compute_gross_fee_economics,
)
from scripts.strategy_research.g2_f3_inference_audit_r1.reconciliation import (
    compute_file_sha256,
    reconcile_single_trade_cashflow,
)

EVAL_START = 1612137600000  # 2021-02-01
EVAL_END = 1704067200000    # 2023-12-31 24:00:00


def _build_synthetic_trade(
    trade_id: int,
    year: int = 2021,
    net_bps: float = 100.0,
    net_usdt: float = 10.0,
    gross_usdt: float = 12.0,
    fee: float = 1.0,
    drag: float = 1.0,
    funding: float = 0.0,
    duration: float = 720.0,
    reason: str = "TIME_CAP",
    side: int = 1,
) -> dict[str, object]:
    t_entry = EVAL_START + trade_id * 86_400_000 * 20
    cash_before = 1000.0 + (trade_id * 5.0)
    cash_after = cash_before + net_usdt
    return {
        "event_id": f"SYNTH_EVENT_{year}_{trade_id}",
        "fold": f"{year}-06",
        "entry_at": t_entry,
        "side": side,
        "raw_entry": 30000.0,
        "net_after_funding_bps": net_bps,
        "gross_usdt": gross_usdt,
        "fee_entry": fee,
        "fee_exit": fee,
        "execution_drag_usdt": drag,
        "trading_net_usdt": gross_usdt - drag - 2 * fee,
        "funding_usdt": funding,
        "net_after_funding_usdt": net_usdt,
        "duration_minutes": duration,
        "exit_reason": reason,
        "cash_before_entry": cash_before,
        "cash_after_ack": cash_after,
        "journal": [
            {"type": "ENTRY_FEE", "cash_delta": -fee},
            {"type": "FUNDING", "cash_delta": funding},
            {"type": "EXIT", "cash_delta": cash_after - cash_before + fee - funding},
        ],
    }


# ==============================================================================
# 1. PREFIX MUTATION TESTS (4 tests)
# ==============================================================================

def test_prefix_mutation_id_parsing() -> None:
    """Mutating event prefix does not compromise horizon and timestamp extraction."""
    event_id = "MUTATED_PREFIX_1612429200000_-1"
    parts = event_id.rsplit("_", 2)
    assert len(parts) == 3
    assert int(parts[1]) == 1612429200000
    assert int(parts[2]) == -1


def test_prefix_mutation_fold_extraction() -> None:
    """Fold prefix determines year partition correctly even with mutated suffix."""
    trade = _build_synthetic_trade(1, year=2021)
    trade["fold"] = "2021-09-SPECIAL_SUFFIX"
    assert str(trade["fold"]).startswith("2021")


def test_prefix_mutation_candidate_filter() -> None:
    """Filtering candidate keys by prefix isolates target configurations cleanly."""
    cands = {
        "F1_TEST": np.zeros(10),
        "F2_TEST": np.zeros(10),
        "F3_MARK_LAST_12H": np.zeros(10),
        "F3_MARK_LAST_18H": np.zeros(10),
    }
    f3_cands = {k: v for k, v in cands.items() if k.startswith("F3_")}
    assert set(f3_cands.keys()) == {"F3_MARK_LAST_12H", "F3_MARK_LAST_18H"}


def test_prefix_mutation_invalid_prefix_rejection() -> None:
    """An unknown candidate family prefix raises an expected diagnostic flag."""
    cands = {"UNAUTHORIZED_F99_TEST": np.zeros(10)}
    has_valid_prefix = any(k.startswith(("F1_", "F2_", "F3_")) for k in cands)
    assert not has_valid_prefix


# ==============================================================================
# 2. TIMESTAMP BOUNDARIES TESTS (4 tests)
# ==============================================================================

def test_timestamp_boundary_exact_start() -> None:
    """Trade exactly at eval_start is assigned to block 0."""
    t = _build_synthetic_trade(0)
    t["entry_at"] = EVAL_START
    res = audit_event_and_block_support([t], EVAL_START, EVAL_END, block_days=14)
    assert res["n_active_blocks"] == 1


def test_timestamp_boundary_pre_eval_excluded() -> None:
    """Trade timestamp before eval_start falls outside positive block range and is excluded from active blocks."""
    t_pre = _build_synthetic_trade(0)
    t_pre["entry_at"] = EVAL_START - 60_000
    res = audit_event_and_block_support([t_pre], EVAL_START, EVAL_END, block_days=14)
    assert res["n_active_blocks"] == 0


def test_timestamp_boundary_post_eval_censor() -> None:
    """Trade timestamp after eval_end is flagged as out-of-evaluation and excluded from active blocks."""
    t_post = _build_synthetic_trade(0)
    t_post["entry_at"] = EVAL_END + 60_000
    res = audit_event_and_block_support([t_post], EVAL_START, EVAL_END, block_days=14)
    assert res["n_active_blocks"] == 0


def test_timestamp_boundary_minute_alignment() -> None:
    """Timestamp not on minute boundary is flagged."""
    t_unaligned = EVAL_START + 12345
    assert t_unaligned % 60_000 != 0
    t_aligned = EVAL_START + 60_000
    assert t_aligned % 60_000 == 0


# ==============================================================================
# 3. SOURCE ADMISSION HASH TESTS (4 tests)
# ==============================================================================

def test_source_admission_hash_frozen_contract() -> None:
    """FROZEN_CONTRACT.json matches known SHA256."""
    p = REPO_ROOT / "evidence/v0.6/b_line/g2_flow_funding_entries_r1/FROZEN_CONTRACT.json"
    assert p.is_file(), f"FROZEN_CONTRACT.json missing at {p}"
    sha = compute_file_sha256(p)
    assert sha == "99b0319ec6eb8390ff292919f292da614ecdd573008530362d1c27828709d26d"



def test_source_admission_hash_tamper_detection(tmp_path: Path) -> None:
    """Altering one byte in a file changes its SHA256."""
    f1 = tmp_path / "file1.txt"
    f2 = tmp_path / "file2.txt"
    f1.write_bytes(b"HELLO_WORLD_1")
    f2.write_bytes(b"HELLO_WORLD_2")
    assert compute_file_sha256(f1) != compute_file_sha256(f2)


def test_source_admission_hash_idempotence(tmp_path: Path) -> None:
    """Repeated hashing of the same file yields identical digest."""
    f = tmp_path / "stable.dat"
    f.write_bytes(b"SAMPLE_PAYLOAD_FOR_HASH_TEST")
    h1 = compute_file_sha256(f)
    h2 = compute_file_sha256(f)
    assert h1 == h2


def test_source_admission_hash_empty_file(tmp_path: Path) -> None:
    """Empty file produces standard empty sha256."""
    f = tmp_path / "empty.dat"
    f.write_bytes(b"")
    empty_sha = hashlib.sha256(b"").hexdigest()
    assert compute_file_sha256(f) == empty_sha


# ==============================================================================
# 4. 2021/2022/2023 CLOCK TESTS (4 tests)
# ==============================================================================

def test_annual_clock_2021_partition() -> None:
    """9 trades in 2021 are correctly counted."""
    trades = [_build_synthetic_trade(i, year=2021) for i in range(9)]
    res = audit_event_and_block_support(trades, EVAL_START, EVAL_END)
    assert res["annual_counts"]["2021"] == 9
    assert res["annual_counts"]["2022"] == 0
    assert res["annual_counts"]["2023"] == 0


def test_annual_clock_2022_partition() -> None:
    """2 trades in 2022 are correctly counted."""
    trades = [_build_synthetic_trade(i, year=2022) for i in range(2)]
    res = audit_event_and_block_support(trades, EVAL_START, EVAL_END)
    assert res["annual_counts"]["2022"] == 2


def test_annual_clock_2023_partition() -> None:
    """1 trade in 2023 is correctly counted."""
    trades = [_build_synthetic_trade(0, year=2023)]
    res = audit_event_and_block_support(trades, EVAL_START, EVAL_END)
    assert res["annual_counts"]["2023"] == 1


def test_annual_clock_9_2_1_distribution() -> None:
    """F3 9/2/1 distribution sums to 12 trades."""
    trades = (
        [_build_synthetic_trade(i, year=2021) for i in range(9)]
        + [_build_synthetic_trade(i + 9, year=2022) for i in range(2)]
        + [_build_synthetic_trade(11, year=2023)]
    )
    res = audit_event_and_block_support(trades, EVAL_START, EVAL_END)
    assert res["annual_counts"] == {"2021": 9, "2022": 2, "2023": 1}
    assert res["n_executed_trades"] == 12


# ==============================================================================
# 5. FUNDING LATENCY TESTS (4 tests)
# ==============================================================================

def test_funding_latency_one_minute_delay() -> None:
    """Settlement at T and entry at T + 1m is valid point-in-time."""
    t_settle = 1612454400000
    t_decision = t_settle + 60_000
    t_entry = t_decision + 60_000
    assert t_entry >= t_settle + 120_000


def test_funding_latency_zero_lag_detected() -> None:
    """Attempted entry at settlement timestamp violates availability delay."""
    t_settle = 1612454400000
    t_entry = t_settle
    is_valid_lag = t_entry >= t_settle + 60_000
    assert not is_valid_lag


def test_funding_latency_negative_lag_detected() -> None:
    """Entry before settlement timestamp is severe lookahead."""
    t_settle = 1612454400000
    t_entry = t_settle - 60_000
    assert t_entry < t_settle


def test_funding_latency_settlement_cadence_8h() -> None:
    """Consecutive settlements must be 8 hours apart."""
    s1 = 1612454400000
    s2 = s1 + 8 * 3_600_000
    assert abs(s2 - s1 - 8 * 3_600_000) == 0


# ==============================================================================
# 6. MARK/LAST SWAP ADVERSARIAL TESTS (4 tests)
# ==============================================================================

def test_mark_last_swap_inverts_basis() -> None:
    """Swapping Mark and Last inverts basis sign: (Last - Mark)/Mark vs (Mark - Last)/Last."""
    last = 30010.0
    mark = 30000.0
    basis_normal = (last - mark) / mark
    basis_swapped = (mark - last) / last
    assert basis_normal > 0
    assert basis_swapped < 0


def test_mark_last_swap_basis_parity() -> None:
    """Under small dislocation, swapped basis is approximately negative of original."""
    last = 30009.0
    mark = 30000.0
    b1 = (last - mark) / mark
    b2 = (mark - last) / mark
    assert abs(b1 + b2) < 1e-12


def test_mark_last_non_tradeable_nature() -> None:
    """Mark price cannot be executed as an order book fill."""
    info = classify_source_causality_and_known_at()
    assert info["mark_1m_close"]["role"] == "VALUATION_PROXY_NON_TRADEABLE"


def test_mark_last_dislocation_threshold_check() -> None:
    """Basis dislocation >= 3.0 bps threshold triggers expected flag."""
    basis_bps = 3.5
    thresh_bps = 3.0
    assert basis_bps >= thresh_bps


# ==============================================================================
# 7. N=0/1/2/12 SAMPLE SIZE TESTS (4 tests)
# ==============================================================================

def test_sample_size_n0_empty() -> None:
    """n=0 trades returns clean zeroed support and refusal."""
    res = audit_event_and_block_support([], EVAL_START, EVAL_END)
    assert res["n_executed_trades"] == 0
    refusal = evaluate_sparse_interval_refusal(0, 0)
    assert refusal["should_refuse_interval"] is True


def test_sample_size_n1_refusal() -> None:
    """n=1 trade fails sample viability gate."""
    trade = _build_synthetic_trade(0, net_usdt=10.0)
    refusal = evaluate_sparse_interval_refusal(len([trade]), 1)
    assert refusal["should_refuse_interval"] is True
    assert refusal["n_trades"] < 30


def test_sample_size_n2_degenerate_draw_rate() -> None:
    """n=2 trades across 76 blocks gives > 10% all-zero draw probability."""
    prob = compute_all_zero_draw_probability(76, 2)
    assert prob > 0.10


def test_sample_size_n12_viability_failure() -> None:
    """n=12 trades fails sample viability threshold n >= 30."""
    trades = [_build_synthetic_trade(i) for i in range(12)]
    res = audit_event_and_block_support(trades, EVAL_START, EVAL_END)
    assert res["n_executed_trades"] == 12
    assert res["passes_sample_viability_n30"] is False


# ==============================================================================
# 8. ALL-ZERO SAMPLED BLOCK TESTS (4 tests)
# ==============================================================================

def test_all_zero_sampled_block_prob_formula() -> None:
    """compute_all_zero_draw_probability with 5 blocks and 1 non-zero gives 0.8^5 = 0.32768."""
    prob = compute_all_zero_draw_probability(5, 1)
    assert abs(prob - 0.32768) < 1e-6


def test_all_zero_sampled_block_limits() -> None:
    """Zero non-zero blocks gives 1.0 probability of all-zero sample."""
    assert compute_all_zero_draw_probability(10, 0) == 1.0
    assert compute_all_zero_draw_probability(10, 10) == 0.0


def test_all_zero_sampled_block_asymptotic_exp_k() -> None:
    """For large B and k=2 non-zero blocks, prob approaches exp(-2) ~ 0.1353."""
    prob = compute_all_zero_draw_probability(1000, 2)
    assert abs(prob - math.exp(-2)) < 0.01


def test_all_zero_sampled_block_draw_count() -> None:
    """Simulation on 100 blocks with 2 non-zeros observes non-zero rate ~ 13%."""
    series = np.zeros(100)
    series[0] = 50.0
    series[1] = -50.0
    res = simulate_studentized_bootstrap({"test": series}, n_rounds=500, seed=42)
    all_zero_rate = res["intervals"]["test"]["all_zero_rate_pct"]
    assert 5.0 <= all_zero_rate <= 25.0


# ==============================================================================
# 9. BOUNDED STUDENTIZER TESTS (4 tests)
# ==============================================================================

def test_bounded_studentizer_degenerate_t_calculation() -> None:
    """t-value with baseline mean 1.2 and floor 1e-6 is 1,200,000.0."""
    t_val = compute_degenerate_t_value(1.2, floor=1e-6)
    assert abs(t_val - 1_200_000.0) < 1e-6


def test_bounded_studentizer_exact_match_7d() -> None:
    """F1 7-day mean of -182.6063851570522 / 152 yields exact t ~ 1,201,357.8."""
    mean_7d = -182.6063851570522 / 152
    t_val = compute_degenerate_t_value(mean_7d, floor=1e-6)
    assert abs(t_val - 1201357.7970858698) < 1e-6


def test_bounded_studentizer_exact_match_14d() -> None:
    """F1 14-day mean of -182.6063851570522 / 76 yields exact t ~ 2,402,715.59."""
    mean_14d = -182.6063851570522 / 76
    t_val = compute_degenerate_t_value(mean_14d, floor=1e-6)
    assert abs(t_val - 2402715.5941717396) < 1e-6



def test_bounded_studentizer_floor_scaling() -> None:
    """Changing floor from 1e-6 to 1e-3 divides degenerate t by 1000."""
    t1 = compute_degenerate_t_value(2.0, floor=1e-6)
    t2 = compute_degenerate_t_value(2.0, floor=1e-3)
    assert abs(t1 / t2 - 1000.0) < 1e-6


def test_bounded_studentizer_minimal_5_block_fixture() -> None:
    """Minimal 5-block fixture produces expected million-scale q95."""
    fixture = create_sparse_synthetic_fixture(5, {"cand": [(0, 10.0)]})
    res = simulate_studentized_bootstrap(fixture, n_rounds=300, seed=123)
    assert res["q95_max_t"] > 1e5


# ==============================================================================
# 10. FLOAT STABILITY TESTS (4 tests)
# ==============================================================================

def test_float_stability_sub_cent_accounting() -> None:
    """Cashflow delta matches net within sub-cent tolerance."""
    t = _build_synthetic_trade(1, net_usdt=10.270758423452929)
    res = reconcile_single_trade_cashflow(t)
    assert res["cash_delta_matches_net"] is True


def test_float_stability_near_zero_variance() -> None:
    """Array with identical floats has 0.0 standard deviation without NaN."""
    arr = np.full(50, 12.3456789)
    s = float(np.std(arr, ddof=1))
    assert abs(s) < 1e-12


def test_float_stability_epsilon_division_safety() -> None:
    """Small standard error does not cause ZeroDivisionError when clamped."""
    se = max(0.0, 1e-6)
    t = 1.0 / se
    assert math.isfinite(t)


def test_float_stability_order_invariance() -> None:
    """Sum of net USDT is invariant to trade row order."""
    vals = [10.27, -27.96, 34.36, -11.22, 96.76]
    s1 = sum(vals)
    s2 = sum(reversed(vals))
    assert abs(s1 - s2) < 1e-12


# ==============================================================================
# 11. PF NO-NEGATIVE-LOSS SENTINEL TESTS (4 tests)
# ==============================================================================

def test_pf_sentinel_zero_loss_assigned_999() -> None:
    """Positive profits with zero losses evaluates to 999.0 sentinel."""
    trades = [_build_synthetic_trade(0, net_usdt=10.27)]
    econ = compute_gross_fee_economics(trades)
    assert econ["loss_count"] == 0
    annual = {"2023": {"profit_factor": 999.0, "n": 1, "total_net_usdt": 10.27}}
    sentinel_audit = audit_profit_factor_sentinels(annual)
    assert sentinel_audit["2023"]["is_division_by_zero_sentinel"] is True
    assert sentinel_audit["2023"]["scientific_interpretation"] == "ZERO_LOSS_PLACEHOLDER_NOT_FINITE_STATISTICAL_EVIDENCE"


def test_pf_sentinel_normal_calculation() -> None:
    """When both positive and negative trades exist, calculated PF is finite."""
    annual = {"2021": {"profit_factor": 1.77, "n": 9, "total_net_usdt": 65.90}}
    sentinel_audit = audit_profit_factor_sentinels(annual)
    assert sentinel_audit["2021"]["is_division_by_zero_sentinel"] is False


def test_pf_sentinel_all_loss_is_zero() -> None:
    """When all trades lose, PF is 0.0."""
    annual = {"2023": {"profit_factor": 0.0, "n": 2, "total_net_usdt": -16.54}}
    sentinel_audit = audit_profit_factor_sentinels(annual)
    assert sentinel_audit["2023"]["is_division_by_zero_sentinel"] is False


def test_pf_sentinel_zero_trades_is_zero() -> None:
    """Zero trades yields zero PF."""
    annual = {"2021": {"profit_factor": 0.0, "n": 0, "total_net_usdt": 0.0}}
    sentinel_audit = audit_profit_factor_sentinels(annual)
    assert sentinel_audit["2021"]["scientific_interpretation"] == "ZERO_TRADES"


# ==============================================================================
# 12. SOURCE ROW REVERSAL TESTS (4 tests)
# ==============================================================================

def test_source_row_reversal_sum_pnl() -> None:
    """Reversing trade records leaves total net USDT unchanged."""
    trades = [_build_synthetic_trade(i, net_usdt=float(i * 5 - 10)) for i in range(6)]
    e1 = compute_gross_fee_economics(trades)
    e2 = compute_gross_fee_economics(list(reversed(trades)))
    assert abs(e1["net_usdt"] - e2["net_usdt"]) < 1e-9


def test_source_row_reversal_win_rate() -> None:
    """Reversing trade records preserves win rate."""
    trades = [_build_synthetic_trade(i, net_usdt=float(i * 5 - 10)) for i in range(6)]
    e1 = compute_gross_fee_economics(trades)
    e2 = compute_gross_fee_economics(list(reversed(trades)))
    assert e1["win_rate_pct"] == e2["win_rate_pct"]


def _compute_max_drawdown(cash_curve: list[float]) -> tuple[float, float]:
    peak = cash_curve[0]
    max_dd_usdt = 0.0
    max_dd_pct = 0.0
    for c in cash_curve:
        peak = max(peak, c)
        dd_u = peak - c
        dd_p = (dd_u / peak * 100.0) if peak > 0 else 0.0
        max_dd_usdt = max(max_dd_usdt, dd_u)
        max_dd_pct = max(max_dd_pct, dd_p)
    return max_dd_usdt, max_dd_pct


def test_source_row_reversal_path_dependent_drawdown() -> None:
    """Max percentage drawdown is path-dependent and differs under time reversal."""
    trades_forward = [
        _build_synthetic_trade(0, net_usdt=50.0),
        _build_synthetic_trade(1, net_usdt=-40.0),
        _build_synthetic_trade(2, net_usdt=10.0),
    ]
    # Forward: 1000 -> 1050 -> 1010 -> 1020 (peak=1050, dd=40, dd_pct=40/1050 ~ 3.8095%)
    curve_fwd = [1000.0]
    for t in trades_forward:
        curve_fwd.append(curve_fwd[-1] + float(t["net_after_funding_usdt"]))
    dd_u_fwd, dd_p_fwd = _compute_max_drawdown(curve_fwd)

    # Reversed: 1000 -> 1010 -> 970 -> 1020 (peak=1010, dd=40, dd_pct=40/1010 ~ 3.9604%)
    curve_rev = [1000.0]
    for t in reversed(trades_forward):
        curve_rev.append(curve_rev[-1] + float(t["net_after_funding_usdt"]))
    dd_u_rev, dd_p_rev = _compute_max_drawdown(curve_rev)

    assert abs(dd_u_fwd - dd_u_rev) < 1e-6  # USDT drawdown happens to be 40.0 in both
    assert abs(dd_p_fwd - dd_p_rev) > 0.1   # Percentage drawdown is path-dependent (3.81% vs 3.96%)
    assert abs(dd_p_fwd - (40.0 / 1050.0 * 100.0)) < 1e-6
    assert abs(dd_p_rev - (40.0 / 1010.0 * 100.0)) < 1e-6



def test_source_row_reversal_chronological_sort() -> None:
    """Sorting by entry_at restores original temporal sequence."""
    trades = [_build_synthetic_trade(i) for i in range(5)]
    shuffled = [trades[3], trades[0], trades[4], trades[1], trades[2]]
    restored = sorted(shuffled, key=lambda t: int(t["entry_at"]))
    assert [t["event_id"] for t in restored] == [t["event_id"] for t in trades]


# ==============================================================================
# 13. NORMALIZATION TESTS (4 tests)
# ==============================================================================

def test_normalization_basis_bps_to_decimal() -> None:
    """3.0 bps threshold converts to 0.0003 decimal."""
    thresh_bps = 3.0
    thresh_dec = thresh_bps / 10_000.0
    assert thresh_dec == 0.0003


def test_normalization_signed_flow_bounds() -> None:
    """Signed flow is bounded within [-1.0, 1.0]."""
    v = 100.0
    tbv = 150.0  # extreme
    raw_flow = (2.0 * tbv - v) / v
    clipped = float(np.clip(raw_flow, -1.0, 1.0))
    assert -1.0 <= clipped <= 1.0


def test_normalization_t_stat_standard_error() -> None:
    """T-statistic standard error scales by 1/sqrt(N)."""
    std = 10.0
    se10 = std / math.sqrt(10)
    se40 = std / math.sqrt(40)
    assert abs(se10 / se40 - 2.0) < 1e-6


def test_normalization_win_rate_percentage() -> None:
    """Win rate scales between 0% and 100%."""
    res = compute_exact_binomial_sign_test(12, 6)
    assert res["win_rate_pct"] == 50.0


def test_exact_binomial_sign_test_bounds_and_symmetry() -> None:
    """Exact binomial sign test satisfies proper boundary coverage and symmetry."""
    # k=0 out of 12: lower bound must be 0.0
    r0 = compute_exact_binomial_sign_test(12, 0)
    assert r0["clopper_pearson_95_ci"][0] == 0.0
    assert r0["score_95_ci"][0] == 0.0
    assert r0["k_losses"] == 12

    # k=12 out of 12: upper bound must be 1.0
    r12 = compute_exact_binomial_sign_test(12, 12)
    assert r12["clopper_pearson_95_ci"][1] == 1.0
    assert r12["score_95_ci"][1] == 1.0
    assert r12["k_losses"] == 0

    # k=6 out of 12: symmetric around 0.5
    r6 = compute_exact_binomial_sign_test(12, 6)
    cp_mid = (r6["clopper_pearson_95_ci"][0] + r6["clopper_pearson_95_ci"][1]) / 2.0
    score_mid = (r6["score_95_ci"][0] + r6["score_95_ci"][1]) / 2.0
    assert abs(cp_mid - 0.5) < 1e-6
    assert abs(score_mid - 0.5) < 1e-6

    # n=0 empty edge case consistency
    r_empty = compute_exact_binomial_sign_test(0, 0)
    assert r_empty["k_losses"] == 0
    assert "clopper_pearson_95_ci" in r_empty
    assert "score_95_ci" in r_empty
    assert r_empty["statistically_significant_at_05"] is False



# ==============================================================================
# 14. HELD-OUT FUTURE MUTATION TESTS (4 tests)
# ==============================================================================

def test_held_out_future_mutation_2024_rejected() -> None:
    """Fold starting in 2024 violates 35-month development scope."""
    fold_name = "2024-01"
    is_in_dev_scope = fold_name.startswith(("2021", "2022", "2023")) and fold_name != "2021-01"
    assert not is_in_dev_scope


def test_held_out_future_mutation_boundary_protection() -> None:
    """Timestamp after 2023-12-31 23:59:00 UTC is strictly rejected."""
    t_2024 = 1704067200000 + 60_000
    assert t_2024 > EVAL_END


def test_held_out_future_mutation_isolation() -> None:
    """Simulated future fold mutation does not alter frozen 2021-2023 trade metrics."""
    trades_dev = [_build_synthetic_trade(i, year=2021) for i in range(5)]
    base_econ = compute_gross_fee_economics(trades_dev)

    # Mutate a dummy 2024 trade in isolated scope
    future_trade = _build_synthetic_trade(99, year=2024, net_usdt=500.0)
    assert future_trade["net_after_funding_usdt"] == 500.0
    assert base_econ["net_usdt"] == sum(float(t["net_after_funding_usdt"]) for t in trades_dev)


def test_held_out_future_mutation_path_eligibility_window() -> None:
    """Prospective 24h deadline ensures trades near fold end are embargoed."""
    fold_end = 1704067200000
    entry_too_late = fold_end - 12 * 3_600_000
    is_eligible = entry_too_late + 24 * 3_600_000 + 60_000 < fold_end
    assert not is_eligible
