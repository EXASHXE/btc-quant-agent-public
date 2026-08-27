from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from helpers import candles

from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candidate, Candle, Direction, Setup, TimeframeFeatures
from btc_quant_agent.funnel import SetupFunnelTrace
from btc_quant_agent.geometry_research import (
    BR_POST_FACTOR_EXPECTED,
    BR_RISK_PASS_EXPECTED,
    DEV_END_MS,
    DEV_START_MS,
    TP_PATTERN_EXPECTED,
    TP_POST_FACTOR_EXPECTED,
    TREND_DECISIONS_EXPECTED,
    _br_geometry_row,
    _frozen_cost_rate,
    _mfe_mae,
    _net_rr,
    _OneMinuteSeries,
    _tp_geometry_row,
    assert_v033_development_only,
    run_v033_geometry_audit,
)
from btc_quant_agent.mechanism import decompose_rr
from btc_quant_agent.multifactor import FactorAssessment


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


def _config() -> AppConfig:
    base = AppConfig()
    return replace(
        base,
        strategy=replace(
            base.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )


def _tp_candidate(target: float = 112.0) -> Candidate:
    return Candidate(
        Direction.LONG, Setup.TREND_PULLBACK, 99.0, 101.0, 95.0, target, 80,
        "fixture", ("fixture",),
    )


def _trace(
    candidate: Candidate | None,
    *,
    blocked: str | None = None,
    direction: Direction = Direction.LONG,
) -> SetupFunnelTrace:
    factor = (
        FactorAssessment(
            score=80.0, positive_groups=4,
            group_scores={"a": 100.0}, evidence=(), risks=(),
            blocked_reason=blocked, raw_score=80.0, available_max=100.0,
        )
        if candidate is not None
        else None
    )
    return SetupFunnelTrace(
        0, 2023, 1, str(direction), str(Setup.TREND_PULLBACK), "TREND_UP",
        (), candidate, "CONFIRMED_LEVEL", factor, None, None, False, "WAIT", None,
    )


def _history(start: int = 0) -> list[Candle]:
    return candles(300, "15m", 900_000, start=start, base=100.0)


def test_geometry_audit_does_not_change_strategy_decision() -> None:
    config = _config()
    candidate = _tp_candidate()
    before = asdict(candidate)
    row = _tp_geometry_row(
        _trace(candidate, blocked="factor score below threshold"),
        _history(),
        _features(close=100.0, atr=2.0, ema_fast=99.0, ema_mid=98.0),
        config,
        DEV_START_MS + 1,
        2023,
    )
    assert asdict(candidate) == before
    assert row["scope"] == "TP_PATTERN"
    assert row["entry_reference"] == pytest.approx((99.0 + 101.0) / 2)
    assert row["frozen_stop"] == pytest.approx(95.0 - 0.25 * 2.0)


def test_invalidation_pivot_age_is_causal() -> None:
    config = _config()
    history = candles(300, "15m", 900_000, start=0, base=100.0)
    candidate = _tp_candidate()
    invalidation = 99.6
    candidate = replace(candidate, invalidation_level=invalidation)
    decision_close_ms = history[-1].close_time_ms
    row = _tp_geometry_row(
        _trace(candidate, blocked="factor score below threshold"),
        history,
        _features(close=100.0, atr=2.0, last_swing_low=invalidation),
        config,
        decision_close_ms + 1,
        2023,
    )
    pivot_time = row["invalidation_pivot_open_time_ms"]
    assert pivot_time is not None
    assert int(pivot_time) <= decision_close_ms
    assert row["invalidation_pivot_age_bars"] >= 0
    assert row["invalidation_pivot_age_minutes"] >= 0.0


def test_local_extreme_stop_is_diagnostic_only() -> None:
    config = _config()
    candidate = _tp_candidate()
    row = _tp_geometry_row(
        _trace(candidate, blocked="factor score below threshold"),
        _history(),
        _features(close=100.0, atr=2.0),
        config,
        DEV_START_MS + 1,
        2023,
    )
    assert row["local_extreme_stop"] != row["frozen_stop"]
    assert row["local_extreme_stop_distance_atr"] is not None
    assert asdict(candidate) == asdict(_tp_candidate())


def test_entry_reference_diagnostic_is_static_only() -> None:
    config = _config()
    candidate = _tp_candidate()
    row = _tp_geometry_row(
        _trace(candidate, blocked="factor score below threshold"),
        _history(),
        _features(close=100.0, atr=2.0, ema_fast=99.0),
        config,
        DEV_START_MS + 1,
        2023,
    )
    refs = {
        "frozen_midpoint_entry": row["entry_reference"],
        "final_confirmation_close": row["close"],
        "ema7_at_candidate": row["ema7"],
    }
    for ref in refs.values():
        assert ref is not None
    cost = _frozen_cost_rate(config)
    for ref in refs.values():
        stop_distance = abs(ref - row["frozen_stop"])
        assert stop_distance > 0
        net = _net_rr(
            abs(row["target"] - ref) / ref, stop_distance / ref, cost
        )
        assert net is not None
    assert asdict(candidate) == asdict(_tp_candidate())


def test_excursion_starts_after_decision() -> None:
    opens = [DEV_START_MS + i * 60_000 for i in range(10)]
    highs = [100.0 + i for i in range(10)]
    lows = [99.0 - i for i in range(10)]
    series = _OneMinuteSeries(
        [
            Candle("BTCUSDT", "1m", o, o + 59_999, 100.0, h, l, 100.0, 1.0)
            for o, h, l in zip(opens, highs, lows, strict=True)
        ]
    )
    decision_close_ms = DEV_START_MS + 3 * 60_000 - 1
    highs_w, _lows_w, start, incomplete = series.window(decision_close_ms, 5)
    assert start == 3
    assert highs_w[0] == highs[3]
    assert not incomplete


def test_excursion_never_reads_holdout() -> None:
    bars = [
        Candle(
            "BTCUSDT", "1m", DEV_START_MS + i * 60_000,
            DEV_START_MS + (i + 1) * 60_000 - 1, 100.0, 100.0 + i, 99.0 - i, 100.0, 1.0,
        )
        for i in range(10)
    ]
    series = _OneMinuteSeries(bars)
    decision_close_ms = DEV_END_MS - 60_000 - 1
    _highs_w, _lows_w, _start, incomplete = series.window(decision_close_ms, 120)
    assert incomplete
    holdout_bar = Candle(
        "BTCUSDT", "1m", DEV_END_MS, DEV_END_MS + 59_999, 100.0, 101.0, 99.0, 100.0, 1.0
    )
    with pytest.raises(ValueError, match="holdout"):
        _OneMinuteSeries([*bars, holdout_bar])


def test_long_short_excursion_symmetry() -> None:
    highs = [100.0, 103.0, 102.0, 105.0, 104.0]
    lows = [100.0, 101.0, 99.0, 100.0, 98.0]
    entry = 100.0
    long_mfe, long_mae, long_mfe_idx, long_mae_idx = _mfe_mae(
        highs, lows, Direction.LONG, entry
    )
    short_mfe, short_mae, short_mfe_idx, short_mae_idx = _mfe_mae(
        highs, lows, Direction.SHORT, entry
    )
    assert long_mfe == pytest.approx(5.0)
    assert long_mae == pytest.approx(2.0)
    assert long_mfe == pytest.approx(short_mae)
    assert long_mae == pytest.approx(short_mfe)
    assert long_mfe_idx == pytest.approx(short_mae_idx)
    assert long_mae_idx == pytest.approx(short_mfe_idx)


def test_required_target_reconstruction_matches_v032() -> None:
    config = _config()
    candidate = _tp_candidate(target=104.0)
    decomposition = decompose_rr(candidate, 2.0, config.strategy, config.risk)
    required = decomposition.required_target_price
    assert required is not None
    exact = decompose_rr(
        replace(candidate, target_level=required), 2.0, config.strategy, config.risk
    )
    assert exact.rr_net == pytest.approx(config.strategy.rr_min)
    assert decomposition.required_reward_atr is not None
    cost = _frozen_cost_rate(config)
    net = _net_rr(
        decomposition.reward_distance_pct,
        decomposition.stop_distance_pct,
        cost,
    )
    assert net == pytest.approx(decomposition.rr_net)


def test_tp_br_geometry_scopes_are_exact() -> None:
    assert TP_PATTERN_EXPECTED == 404
    assert TP_POST_FACTOR_EXPECTED == 139
    assert BR_POST_FACTOR_EXPECTED == 185
    assert BR_RISK_PASS_EXPECTED == 14
    assert TREND_DECISIONS_EXPECTED == 29_580


def test_artifacts_are_development_only() -> None:
    assert_v033_development_only(
        [{"timestamp_ms": DEV_START_MS}, {"timestamp_ms": DEV_END_MS - 1}]
    )
    with pytest.raises(ValueError, match="holdout firewall"):
        assert_v033_development_only([{"timestamp_ms": DEV_END_MS}])


def test_geometry_audit_requires_complete_development_window() -> None:
    with pytest.raises(ValueError, match="complete development period"):
        run_v033_geometry_audit([], AppConfig(), [])


def test_geometry_audit_rejects_holdout_rows() -> None:
    bars = [
        Candle(
            "BTCUSDT", "1m", DEV_START_MS, DEV_START_MS + 59_999,
            100.0, 101.0, 99.0, 100.0, 1.0,
        ),
        Candle(
            "BTCUSDT", "1m", DEV_END_MS - 60_000, DEV_END_MS,
            100.0, 101.0, 99.0, 100.0, 1.0,
        ),
    ]
    with pytest.raises(ValueError, match="holdout"):
        run_v033_geometry_audit(bars, AppConfig(), [])


def test_protocol_forbids_strategy_arm_and_holdout() -> None:
    protocol = json.loads(
        Path("configs/research/v0.3.3_geometry_protocol.json").read_text(
            encoding="utf-8"
        )
    )
    assert protocol["scope"]["holdout_forbidden"] is True
    assert protocol["prohibitions"]["strategy_arm"] is False
    assert protocol["prohibitions"]["candidate_freeze"] is False
    assert protocol["prohibitions"]["holdout_consumption"] is False
    assert protocol["prohibitions"]["pnl_based_selection"] is False
    assert protocol["prohibitions"]["rr_min_reduction"] is False
    assert protocol["control"]["validation_status"] == "EXPERIMENTAL"
    assert protocol["overall_allowed_status"] == [
        "GEOMETRY_AUDIT_COMPLETE",
        "GEOMETRY_AUDIT_BLOCKED",
    ]


def test_holdout_certificate_remains_unconsumed() -> None:
    certificates = list(Path("var").rglob("*certificate*"))
    assert not any("holdout_consumed_at_ms" in cert.read_text() for cert in certificates if cert.is_file())


def test_br_reference_row_static_geometry() -> None:
    config = _config()
    br_candidate = Candidate(
        Direction.LONG, Setup.BREAKOUT_RETEST, 98.0, 100.0, 97.0, 106.0, 78,
        "fixture", ("fixture",),
    )
    row = _br_geometry_row(
        _trace(br_candidate), _history(), _features(close=100.0, atr=2.0),
        config, DEV_START_MS + 1, 2023,
    )
    assert row["scope"] == "BR_RISK_PASS" or row["scope"] == "BR_POST_FACTOR"
    assert row["entry_lag_bars"] == 1
    assert row["frozen_stop_distance_atr"] is not None
    assert asdict(br_candidate) == asdict(
        Candidate(
            Direction.LONG, Setup.BREAKOUT_RETEST, 98.0, 100.0, 97.0, 106.0, 78,
            "fixture", ("fixture",),
        )
    )
