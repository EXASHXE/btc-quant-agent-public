import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from btc_quant_agent.backtest import FundingEvent
from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candidate, Direction, Setup, TimeframeFeatures
from btc_quant_agent.mechanism import (
    E1_ATR_MULTIPLIER,
    EXPERIMENT_ARMS,
    decompose_rr,
    deduplicate_factor_score,
    e1_fixed_tp_target,
    funding_crossing_count,
)
from btc_quant_agent.mechanism_research import (
    DEV_END_MS,
    DEV_START_MS,
    assert_v032_development_only,
    run_v032_experiments,
)
from btc_quant_agent.multifactor import assess_factors
from btc_quant_agent.risk import build_position_plan


def _candidate(
    *, setup: Setup = Setup.TREND_PULLBACK, target: float = 112.0
) -> Candidate:
    return Candidate(
        Direction.LONG, setup, 99.0, 101.0, 95.0, target, 80, "fixture",
        ("fixture",),
    )


def _features(**changes: object) -> TimeframeFeatures:
    value = TimeframeFeatures(
        close=100.0, ema_fast=99.0, ema_mid=98.0, ema_slow=95.0,
        ema_mid_slope=1.0, ema_slow_slope=0.5, atr=2.0,
        atr_percentile=0.5, adx=25.0, volume_z=1.0, rsi=55.0, roc=0.01,
        bb_width_percentile=0.5, cvd_slope=1.0, cvd_available=True,
        last_swing_high=110.0, previous_swing_high=105.0,
        last_swing_low=95.0, previous_swing_low=90.0, structure="HH_HL",
        bar_open_time_ms=0, bar_close_time_ms=1,
    )
    return replace(value, **changes)


def _strategy_config() -> AppConfig:
    base = AppConfig()
    return replace(
        base,
        strategy=replace(
            base.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )


def test_rr_decomposition_reconstructs_frozen_plan() -> None:
    config = _strategy_config()
    candidate = _candidate()
    diagnostic = decompose_rr(candidate, 2.0, config.strategy, config.risk)
    plan = build_position_plan(candidate, 2.0, config.strategy, config.risk)
    assert plan is not None
    assert diagnostic.frozen_risk_plan_pass
    assert diagnostic.actual_stop == plan.stop_loss
    assert diagnostic.rr_gross == pytest.approx(plan.rr_gross)
    assert diagnostic.rr_net == pytest.approx(plan.rr_net)
    assert diagnostic.capped_notional == pytest.approx(plan.recommended_notional)


def test_rr_component_order_is_deterministic() -> None:
    config = _strategy_config()
    item = decompose_rr(_candidate(), 2.0, config.strategy, config.risk)
    assert item.rr_gross is not None
    assert item.rr_after_fee is not None
    assert item.rr_after_fee_slippage is not None
    assert item.rr_net is not None
    assert item.rr_gross > item.rr_after_fee > item.rr_after_fee_slippage > item.rr_net


def test_required_target_price_hits_exact_rr_threshold() -> None:
    config = _strategy_config()
    first = decompose_rr(_candidate(target=104.0), 2.0, config.strategy, config.risk)
    assert first.required_target_price is not None
    candidate = replace(_candidate(), target_level=first.required_target_price)
    exact = decompose_rr(candidate, 2.0, config.strategy, config.risk)
    assert exact.rr_net == pytest.approx(config.strategy.rr_min)


def test_funding_crossing_count_is_time_correct() -> None:
    events = [FundingEvent(timestamp, 0.0) for timestamp in (8_000, 16_000, 24_000)]
    assert funding_crossing_count(7_000, Setup.TREND_PULLBACK, events, 0, 0) == 0
    assert funding_crossing_count(7_000, Setup.TREND_PULLBACK, events, 1, 1) == 3


def test_stop_buffer_diagnostic_does_not_change_control() -> None:
    config = _strategy_config()
    candidate = _candidate()
    before = asdict(candidate)
    decompose_rr(candidate, 2.0, config.strategy, config.risk)
    assert asdict(candidate) == before


def test_e1_changes_tp_target_only() -> None:
    candidate = _candidate()
    changed = e1_fixed_tp_target(candidate, _features())
    assert changed.target_level != candidate.target_level
    assert asdict(changed) | {"target_level": candidate.target_level} == asdict(candidate)


def test_e1_does_not_rescue_target_missing_candidates() -> None:
    # The transform accepts a Candidate, so setup events rejected before Candidate creation
    # have no object that can enter E1.
    assert e1_fixed_tp_target(_candidate(), _features()).setup == Setup.TREND_PULLBACK


def test_e1_multiplier_is_fixed_2_5_atr() -> None:
    changed = e1_fixed_tp_target(_candidate(), _features(atr=4.0, close=100.0))
    assert E1_ATR_MULTIPLIER == 2.5
    assert changed.target_level == 110.0


def test_e1_does_not_change_entry_stop_or_factor_logic() -> None:
    config = _strategy_config()
    candidate = _candidate()
    features = _features()
    changed = e1_fixed_tp_target(candidate, features)
    assert changed.entry_low == candidate.entry_low
    assert changed.entry_high == candidate.entry_high
    assert changed.invalidation_level == candidate.invalidation_level
    assert assess_factors(changed, features, features, features, None, config.strategy) == assess_factors(
        candidate, features, features, features, None, config.strategy
    )


def test_e2_keeps_all_hard_gates() -> None:
    config = _strategy_config()
    features = _features(rsi=90.0)
    control = assess_factors(_candidate(), features, features, features, None, config.strategy)
    changed = deduplicate_factor_score(control, _candidate(), features, config.strategy, "E2")
    assert changed == control
    assert changed.blocked_reason == "15m RSI is overextended"


def test_e2_removes_only_trend_structure_score() -> None:
    config = _strategy_config()
    features = _features()
    control = assess_factors(_candidate(), features, features, features, None, config.strategy)
    changed = deduplicate_factor_score(control, _candidate(), features, config.strategy, "E2")
    assert changed.raw_score == control.raw_score - 30.0
    assert changed.available_max == control.available_max - 30.0
    assert "trend_structure" not in changed.group_scores
    assert set(changed.group_scores) == set(control.group_scores) - {"trend_structure"}


def test_e2_threshold_is_pre_registered() -> None:
    assert _strategy_config().strategy.factor_score_min == 72.0


def test_e3_keeps_setup_volume_gate() -> None:
    config = _strategy_config()
    assert config.strategy.volume_z_min == -0.25
    assert _features().volume_z >= config.strategy.volume_z_min


def test_e3_removes_only_volume_base_credit() -> None:
    config = _strategy_config()
    features = _features()
    control = assess_factors(_candidate(), features, features, features, None, config.strategy)
    changed = deduplicate_factor_score(control, _candidate(), features, config.strategy, "E3")
    assert changed.raw_score == control.raw_score - 6.0
    assert changed.available_max == control.available_max - 6.0
    assert set(changed.group_scores) == set(control.group_scores)


def test_e3_uses_fixed_cvd_scoring() -> None:
    config = _strategy_config()
    aligned = _features(cvd_slope=1.0)
    opposed = _features(cvd_slope=-1.0)
    for features, expected in ((aligned, 100.0), (opposed, 0.0)):
        control = assess_factors(_candidate(), features, features, features, None, config.strategy)
        changed = deduplicate_factor_score(control, _candidate(), features, config.strategy, "E3")
        assert changed.group_scores["participation_flow"] == expected


def test_no_combined_experiment_arms() -> None:
    assert EXPERIMENT_ARMS == ("CONTROL", "E0", "E1", "E2", "E3")
    assert all("+" not in arm for arm in EXPERIMENT_ARMS)


def test_v032_experiments_reject_holdout_rows() -> None:
    with pytest.raises(ValueError, match="complete development period"):
        run_v032_experiments([], AppConfig(), [])


def test_holdout_gate_remains_unconsumed() -> None:
    assert_v032_development_only([{"timestamp_ms": DEV_START_MS}])
    with pytest.raises(ValueError, match="holdout firewall"):
        assert_v032_development_only([{"timestamp_ms": DEV_END_MS}])


def test_all_v032_artifacts_are_development_only() -> None:
    assert_v032_development_only(
        [{"timestamp_ms": DEV_START_MS}, {"timestamp_ms": DEV_END_MS - 1}]
    )


def test_holdout_remains_sealed() -> None:
    protocol = json.loads(
        Path("configs/research/v0.3.2_mechanism_protocol.json").read_text(
            encoding="utf-8"
        )
    )
    assert protocol["scope"]["holdout_forbidden"] is True
    assert protocol["prohibitions"]["holdout_consumption"] is False
