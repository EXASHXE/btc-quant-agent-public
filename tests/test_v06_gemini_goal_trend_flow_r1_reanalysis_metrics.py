"""Synthetic witnesses for the fixed 24-candidate economic reanalysis."""

from datetime import UTC, datetime

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    block_bootstrap,
    calculate_candidate_metrics,
    evaluate_promotion_gate,
)


def _ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=UTC).timestamp() * 1000)


def _trade(at: int, net: float, gross: float, control: float = 0.0) -> dict:
    return {
        "entry_at": at,
        "gross_bps": gross,
        "net_bps": net,
        "gross_usdt": gross / 100,
        "net_usdt": net / 100,
        "control_net_bps": control,
        "exit_reason": "TIME",
        "duration_minutes": 240,
    }


def test_net_profit_factor_and_distinct_trade_close_vs_minute_mtm():
    trades = [_trade(_ms(2021, 2, 2), 20, 60), _trade(_ms(2021, 3, 2), -10, 20)]
    without_marks = calculate_candidate_metrics(trades, "STRESS")
    assert without_marks["net_profit_factor"] == 2
    assert without_marks["gross_profit_factor"] is None  # No gross loss.
    assert without_marks["max_mtm_drawdown_pct"] is None
    assert without_marks["max_trade_close_drawdown_pct"] > 0
    with_marks = calculate_candidate_metrics(
        trades, "STRESS", minute_equity_curve=[1000, 1010, 890, 1000]
    )
    assert with_marks["max_mtm_drawdown_pct"] == 100 * 120 / 1010
    assert with_marks["max_trade_close_drawdown_pct"] != with_marks["max_mtm_drawdown_pct"]


def test_paired_control_requires_every_trade():
    trades = [_trade(_ms(2021, 2, 2), 20, 30, 5), _trade(_ms(2021, 3, 2), 10, 20, 15)]
    assert calculate_candidate_metrics(trades, "STRESS")["mean_paired_increment_bps"] == 5
    trades[1].pop("control_net_bps")
    assert calculate_candidate_metrics(trades, "STRESS")["mean_paired_increment_bps"] is None


def test_calendar_bootstrap_retains_empty_weeks_and_adjusts_48_trials():
    trades = [_trade(_ms(2021, 2, 2), 4, 5), _trade(_ms(2023, 12, 2), 6, 7)]
    result = block_bootstrap(trades, n_iter=1000)
    assert result["block_count"] > result["nonempty_block_count"] + 100
    assert result["familywise_alpha"] == 0.05 / 48
    assert result["familywise_lcb_48"] is None  # Sparse draws have zero sampled trades.
    assert result["zero_trade_resamples"] > 0


def test_calendar_bootstrap_repeatable_and_same_utc_origin():
    a = [_trade(_ms(2021, 2, 2), 10, 20), _trade(_ms(2021, 2, 10), -5, 5)]
    b = [_trade(_ms(2021, 2, 2), 10, 20), _trade(_ms(2021, 2, 24), -5, 5)]
    first = block_bootstrap(a, n_iter=1000, seed=42)
    assert first == block_bootstrap(a, n_iter=1000, seed=42)
    assert first["block_count"] == block_bootstrap(b, n_iter=1000, seed=42)["block_count"]


def test_gate_fails_closed_without_true_mtm_control_or_both_adjusted_bounds():
    metrics = {
        "trade_count": 100,
        "years_covered": 2,
        "months_covered": 6,
        "mean_net_bps": 4,
        "equal_year_net_bps": 4,
        "net_profit_factor": 1.2,
        "worst_year_net_bps": 1,
        "max_mtm_drawdown_pct": None,
        "mean_paired_increment_bps": None,
    }
    good = {
        "familywise_lcb_48": 1,
        "nonempty_block_count": 100,
        "zero_trade_resamples": 0,
        "family_size": 48,
        "familywise_alpha": 0.05 / 48,
    }
    assert not evaluate_promotion_gate(metrics, good, good)["all_passed"]
    metrics["max_mtm_drawdown_pct"] = 5
    metrics["mean_paired_increment_bps"] = 1
    assert evaluate_promotion_gate(metrics, good, good)["all_passed"]
    assert not evaluate_promotion_gate(metrics, good, {**good, "familywise_lcb_48": None})["all_passed"]
