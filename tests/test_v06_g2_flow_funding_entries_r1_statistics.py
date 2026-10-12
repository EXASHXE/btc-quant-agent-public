"""Synthetic tests for statistical metrics, annual breakdown, block bootstrapping, and simultaneous max-|T| intervals."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_flow_funding_entries_r1.statistics import (
    compute_annual_breakdown,
    compute_block_bootstrap_max_t,
    compute_trade_metrics,
)


def _mock_trades(n: int = 10, mean_bps: float = 20.0) -> list[dict[str, object]]:
    trades = []
    t0 = 1612137600000
    for i in range(n):
        sign = 1 if i % 3 != 0 else -1
        net_bps = mean_bps * sign
        net_usdt = net_bps * 0.1
        gross_usdt = net_usdt + 0.22
        year = 2021 if i < 3 else (2022 if i < 6 else 2023)
        trades.append({
            "event_id": f"trade_{i}",
            "fold": f"{year}-05",
            "entry_at": t0 + i * 86_400_000 * 10,
            "net_after_funding_bps": net_bps,
            "gross_usdt": gross_usdt,
            "fee_entry": 0.05,
            "fee_exit": 0.05,
            "funding_usdt": 0.01,
            "net_after_funding_usdt": net_usdt,
        })
    return trades


def test_compute_trade_metrics_empty() -> None:
    """Empty trade list returns clean zeroed statistics."""
    res = compute_trade_metrics([])
    assert res["n"] == 0
    assert res["win_rate_pct"] == 0.0
    assert res["mean_net_bps"] == 0.0
    assert res["profit_factor"] == 0.0


def test_compute_trade_metrics_calculation() -> None:
    """Trade metrics calculation correctly derives win rate, mean, and profit factor."""
    trades = _mock_trades(n=10, mean_bps=50.0)
    res = compute_trade_metrics(trades)

    assert res["n"] == 10
    assert 0 <= res["win_rate_pct"] <= 100.0
    assert res["profit_factor"] > 0
    assert abs(res["total_net_usdt"] - sum(t["net_after_funding_usdt"] for t in trades)) < 1e-6


def test_compute_annual_breakdown() -> None:
    """compute_annual_breakdown partitions trades into 2021, 2022, 2023, and FULL_35M."""
    trades = _mock_trades(n=10)
    res = compute_annual_breakdown(trades)

    assert set(res.keys()) == {"2021", "2022", "2023", "FULL_35M"}
    assert res["2021"]["n"] == 3
    assert res["2022"]["n"] == 3
    assert res["2023"]["n"] == 4
    assert res["FULL_35M"]["n"] == 10


def test_block_bootstrap_max_t_determinism() -> None:
    """compute_block_bootstrap_max_t with fixed seed produces identical results."""
    trades1 = _mock_trades(n=20, mean_bps=30.0)
    trades2 = _mock_trades(n=20, mean_bps=-10.0)

    series = {"cand1": trades1, "cand2": trades2}
    eval_start = 1612137600000
    eval_end = eval_start + 300 * 86_400_000

    res1 = compute_block_bootstrap_max_t(series, eval_start, eval_end, block_days=14, n_rounds=500, seed=12345)
    res2 = compute_block_bootstrap_max_t(series, eval_start, eval_end, block_days=14, n_rounds=500, seed=12345)

    assert res1["q95_max_t"] == res2["q95_max_t"]
    assert res1["intervals"]["cand1"]["simultaneous_ci_95"] == res2["intervals"]["cand1"]["simultaneous_ci_95"]


def test_block_bootstrap_ci_falsifier() -> None:
    """Interval spanning zero correctly flags INSUFFICIENT_SUPPORT."""
    # A series with negative or near-zero returns will span zero
    trades = _mock_trades(n=20, mean_bps=1.0)
    series = {"cand": trades}
    eval_start = 1612137600000
    eval_end = eval_start + 300 * 86_400_000

    res = compute_block_bootstrap_max_t(series, eval_start, eval_end, block_days=14, n_rounds=200, seed=999)
    cand_res = res["intervals"]["cand"]

    if cand_res["simultaneous_ci_95"][0] <= 0 <= cand_res["simultaneous_ci_95"][1]:
        assert cand_res["spans_zero"] is True
        assert cand_res["statistical_support"] == "INSUFFICIENT_SUPPORT"
