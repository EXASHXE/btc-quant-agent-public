"""Deterministic unit tests for small-sample block bootstrap, degeneracy refusal, and power projections.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.statistics import (
    block_bootstrap_net_bps,
    compute_basic_metrics,
    project_statistical_power,
)


def test_basic_metrics_empty():
    res = compute_basic_metrics([])
    assert res["trade_count"] == 0
    assert res["mean_net_bps"] == 0.0
    assert res["profit_factor"] == 0.0
    assert res["status"] == "EMPTY_SAMPLE"


def test_basic_metrics_all_losses_no_zero_div():
    res = compute_basic_metrics([-10.0, -20.0, -5.0])
    assert res["trade_count"] == 3
    assert res["mean_net_bps"] < 0
    assert res["win_rate"] == 0.0
    assert res["profit_factor"] == 0.0  # gross_gains is 0


def test_basic_metrics_all_wins_no_zero_div():
    res = compute_basic_metrics([15.0, 25.0, 10.0])
    assert res["trade_count"] == 3
    assert res["win_rate"] == 1.0
    assert res["profit_factor"] == float("inf")  # gross_losses is 0


def test_basic_metrics_mixed_trades():
    res = compute_basic_metrics([20.0, -10.0, 30.0, -10.0])
    assert res["trade_count"] == 4
    assert res["win_rate"] == 0.5
    # Gains = 50, Losses = 20 -> PF = 2.5
    assert abs(res["profit_factor"] - 2.5) < 1e-6


def test_bootstrap_empty_trades_refusal():
    res = block_bootstrap_net_bps([])
    assert res.status == "EMPTY_SAMPLE"
    assert res.is_degenerate is True
    assert res.ci_lower_95 is None
    assert res.ci_upper_95 is None
    assert res.diagnostic == "EVIDENCE_IMMATURE"


def test_bootstrap_zero_variance_refusal():
    # Exactly identical trades
    trades = [
        {"exit_fill_ms": 1700000000000 + (i * 86400000), "net_bps": 10.0}
        for i in range(20)
    ]
    res = block_bootstrap_net_bps(trades, block_size_days=7)
    assert res.status == "DEGENERATE_ZERO_VARIANCE"
    assert res.is_degenerate is True
    assert res.ci_lower_95 is None
    assert res.ci_upper_95 is None
    assert res.diagnostic == "EVIDENCE_IMMATURE"


def test_bootstrap_insufficient_blocks_refusal():
    # Only 2 active weeks (< 5 active blocks)
    trades = [
        {"exit_fill_ms": 1700000000000 + (i * 3600000), "net_bps": float(i)}
        for i in range(12)
    ]
    res = block_bootstrap_net_bps(trades, block_size_days=7)
    assert res.status == "INSUFFICIENT_ACTIVE_BLOCKS"
    assert res.is_degenerate is True
    assert res.ci_lower_95 is None
    assert res.ci_upper_95 is None
    assert res.diagnostic == "EVIDENCE_IMMATURE"


def test_bootstrap_valid_reproducibility():
    # 20 distinct weeks of diverse trades
    week_ms = 7 * 24 * 3600 * 1000
    trades = []
    for w in range(20):
        t_base = 1700000000000 + (w * week_ms)
        trades.append({"exit_fill_ms": t_base + 1000, "net_bps": 10.0 + (w % 5) * 3})
        trades.append({"exit_fill_ms": t_base + 50000, "net_bps": -5.0 + (w % 3) * 2})

    res1 = block_bootstrap_net_bps(trades, block_size_days=7, n_bootstraps=500, random_seed=42)
    res2 = block_bootstrap_net_bps(trades, block_size_days=7, n_bootstraps=500, random_seed=42)

    assert res1.status == "BOOTSTRAP_SUCCESS"
    assert res1.is_degenerate is False
    assert res1.ci_lower_95 is not None
    assert res1.ci_upper_95 is not None
    # Deterministic seed reproducibility
    assert res1.ci_lower_95 == res2.ci_lower_95
    assert res1.ci_upper_95 == res2.ci_upper_95
    assert res1.standard_error == res2.standard_error
    assert res1.active_blocks >= 15
    assert res1.diagnostic == "SAMPLE_READINESS_MET"


def test_bootstrap_14d_block_size():
    week_ms = 7 * 24 * 3600 * 1000
    trades = []
    for w in range(24):
        t_base = 1700000000000 + (w * week_ms)
        trades.append({"exit_fill_ms": t_base + 1000, "net_bps": 12.0 + (w % 4)})
        trades.append({"exit_fill_ms": t_base + 2000, "net_bps": -8.0 + (w % 2)})

    res_14d = block_bootstrap_net_bps(trades, block_size_days=14, n_bootstraps=500, random_seed=99)
    assert res_14d.status == "BOOTSTRAP_SUCCESS"
    assert res_14d.is_degenerate is False
    assert res_14d.ci_lower_95 is not None


def test_power_projection_monotonicity():
    projections = project_statistical_power(
        assumed_std_bps=25.0,
        target_sample_sizes=(30, 60, 100),
        effect_sizes_bps=(5.0, 15.0),
        alpha=0.05,
        n_simulations=400,
        random_seed=123,
    )
    assert len(projections) == 6

    # For same effect size, power should increase with sample size
    p_n30_eff15 = next(p for p in projections if p.sample_size == 30 and p.effect_size_bps == 15.0)
    p_n100_eff15 = next(p for p in projections if p.sample_size == 100 and p.effect_size_bps == 15.0)
    assert p_n100_eff15.projected_power > p_n30_eff15.projected_power

    # For same sample size, power should increase with effect size
    p_n60_eff5 = next(p for p in projections if p.sample_size == 60 and p.effect_size_bps == 5.0)
    p_n60_eff15 = next(p for p in projections if p.sample_size == 60 and p.effect_size_bps == 15.0)
    assert p_n60_eff15.projected_power > p_n60_eff5.projected_power
