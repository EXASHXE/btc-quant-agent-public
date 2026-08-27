from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from btc_quant_agent.causal_entry_research import (
    MIN_BAR_DISTANCE,
    IndexedOneMinuteSeries,
    PendingLimit,
    _development_only,
    advance_pending_limit,
    bootstrap_directionality,
    directionality_label,
    match_controls,
    prospective_retrace_order,
    resolve_open_trade,
)
from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candle, Direction
from btc_quant_agent.research import DEV_END_MS, DEV_START_MS

PROTOCOL_PATH = Path("configs/research/v0.3.4_causal_entry_protocol.json")


def test_v034_protocol_preregistration_rules() -> None:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert protocol["protocol_id"] == "btc-quant-agent-v0.3.4-causal-entry-directionality-v1"
    assert protocol["scope"]["holdout_forbidden"] is True
    assert protocol["control"]["rr_min"] == 1.8
    assert protocol["control"]["ttl_minutes"] == 45
    assert protocol["control"]["max_signal_age_bars"] == 3
    assert protocol["control"]["trend_pullback_holding_minutes"] == 720
    assert protocol["control"]["validation_status"] == "EXPERIMENTAL"
    arm = protocol["e_retrace_arm"]
    assert arm["causal_fill_rule"]["retroactive_fill"] is False
    assert arm["causal_fill_rule"]["gap_through_never_improves_price"] is True
    assert arm["same_1m_ambiguity"]["favorable_ordering"] is False
    assert arm["frozen_execution"]["entry_execution_only"] is True
    assert arm["frozen_execution"]["local_stop"] is False
    assert arm["frozen_execution"]["target_change"] is False
    assert arm["frozen_execution"]["rr_reduction"] is False
    assert arm["position_policy"]["max_open_positions_constraint_applied"] is False
    assert arm["funnel_reason_codes"] == [
        "NO_PROSPECTIVE_RR",
        "UNFILLED_EXPIRED",
        "INVALIDATED_BEFORE_FILL",
        "RR_FAILED_AT_FILL",
        "FILLED",
    ]
    controls = protocol["matched_controls"]
    assert controls["k_per_candidate"] == 5
    assert controls["matching"]["min_bar_distance"] == 96
    assert controls["matching"]["not_tp_pattern_candidate"] is True
    assert controls["matching"]["same_year"] is True
    assert controls["matching"]["same_1h_regime"] is True
    assert controls["matching"]["deterministic"] is True
    directionality = protocol["directionality"]
    assert directionality["horizons_minutes"] == [60, 120, 240, 480, 720]
    assert directionality["reach_thresholds_atr"] == [1.0, 1.5, 2.5]
    assert directionality["statistics"]["bootstrap_simulations"] == 2000
    hypotheses = protocol["hypotheses"]
    assert hypotheses["allowed_verdicts"] == [
        "SUPPORTED",
        "FALSIFIED",
        "INCONCLUSIVE_LOW_SAMPLE",
        "INCONCLUSIVE_MECHANISM",
    ]
    assert "support_rule" in hypotheses["H9_directional_edge"]
    assert "verdict_rules" in hypotheses["H10_causal_retrace_entry"]
    for prohibition, value in protocol["prohibitions"].items():
        assert value is False, prohibition
    assert protocol["candidate_gate"]["candidate_freeze"] is False
    assert protocol["candidate_gate"]["holdout_consumption"] is False
    assert protocol["candidate_gate"]["allowed_recommendations"] == [
        "NO_CANDIDATE",
        "RECOMMEND_FOR_V0.3.5_CANDIDATE_RESEARCH",
    ]
    assert protocol["overall_allowed_status"] == [
        "CAUSAL_ENTRY_VALIDATION_COMPLETE",
        "CAUSAL_ENTRY_VALIDATION_BLOCKED",
    ]
    assert protocol["random_seed"] == 34


def _bar(open_ms: int, *, low: float = 99.0, high: float = 101.0, close: float = 100.0) -> Candle:
    return Candle("BTCUSDT", "1m", open_ms, open_ms + 59_999, close, high, low, close, 1.0)


def _candidate(decision_close_ms: int = DEV_START_MS + 899_999) -> dict[str, object]:
    return {
        "candidate_id": "candidate-1",
        "direction": "LONG",
        "timestamp_ms": decision_close_ms + 1,
        "decision_close_ms": decision_close_ms,
        "year": 2021,
        "pullback_local_extreme": 100.0,
        "pullback_local_extreme_bar_close_time_ms": decision_close_ms - 900_000,
        "invalidation_level": 98.0,
        "target": 106.0,
        "atr": 2.0,
    }


def _order(decision_close_ms: int = DEV_START_MS + 899_999) -> PendingLimit:
    created = decision_close_ms + 1
    return PendingLimit(
        candidate_id="candidate-1",
        direction=Direction.LONG,
        created_at_ms=created,
        eligible_from_ms=created,
        expires_at_ms=decision_close_ms + 45 * 60_000,
        limit_price=100.0,
        invalidation_level=98.0,
        stop_loss=97.5,
        take_profit=105.0,
        rr_gross=2.0,
        rr_net=1.8,
        recommended_notional=50.0,
        max_loss_usdt=1.0,
        estimated_fee_usdt=0.05,
        estimated_slippage_usdt=0.02,
    )


def test_retrace_order_created_only_after_candidate() -> None:
    row = _candidate()
    order = prospective_retrace_order(row, AppConfig())
    assert order is not None
    assert order.created_at_ms == int(row["decision_close_ms"]) + 1
    assert order.created_at_ms > int(row["pullback_local_extreme_bar_close_time_ms"])


def test_retrace_cannot_fill_on_past_pullback_bar() -> None:
    order = _order()
    past = _bar(order.created_at_ms - 60_000, low=95.0)
    future = _bar(order.created_at_ms, low=100.5, high=101.0, close=100.8)
    result = advance_pending_limit(order, [past, future])
    assert result["state"] != "FILLED"


def test_retrace_fill_starts_next_1m_bar() -> None:
    order = _order()
    first_future = _bar(order.eligible_from_ms, low=99.0)
    result = advance_pending_limit(order, [first_future])
    assert result["state"] == "FILLED"
    assert result["filled_at_ms"] == order.eligible_from_ms
    assert result["fill_price"] == order.limit_price


def test_retrace_uses_frozen_ttl() -> None:
    config = AppConfig()
    order = prospective_retrace_order(_candidate(), config)
    assert order is not None
    assert order.expires_at_ms - int(_candidate()["decision_close_ms"]) == 45 * 60_000
    shorter = replace(config, runtime=replace(config.runtime, ttl_minutes=30))
    shorter_order = prospective_retrace_order(_candidate(), shorter)
    assert shorter_order is not None
    assert shorter_order.expires_at_ms - int(_candidate()["decision_close_ms"]) == 30 * 60_000


def test_retrace_expires_unfilled() -> None:
    order = _order()
    bars = [
        _bar(order.eligible_from_ms + minute * 60_000, low=100.5, high=101.0, close=100.8)
        for minute in range(46)
    ]
    assert advance_pending_limit(order, bars)["state"] == "UNFILLED_EXPIRED"


def test_retrace_invalidation_cancels_pending() -> None:
    order = replace(_order(), invalidation_level=100.2)
    bars = [
        _bar(order.eligible_from_ms + minute * 60_000, low=100.5, high=101.0, close=100.8)
        for minute in range(14)
    ]
    bars.append(_bar(order.eligible_from_ms + 14 * 60_000, low=100.1, high=101.0, close=100.1))
    assert advance_pending_limit(order, bars)["state"] == "INVALIDATED_BEFORE_FILL"


def test_retrace_same_bar_ambiguity_is_conservative() -> None:
    order = _order()
    ambiguous = _bar(order.eligible_from_ms, low=97.0, high=106.0, close=102.0)
    trade = resolve_open_trade(order, [ambiguous], 0, (), 720)
    assert trade["outcome"] == "LOSS"
    assert trade["exit_price"] == order.stop_loss


def test_e_retrace_changes_entry_execution_only() -> None:
    row = _candidate()
    order = prospective_retrace_order(row, AppConfig())
    assert order is not None
    assert order.limit_price == row["pullback_local_extreme"]
    assert order.limit_price != row.get("close")


def test_e_retrace_keeps_frozen_stop_target_rr_costs() -> None:
    config = AppConfig()
    row = _candidate()
    order = prospective_retrace_order(row, config)
    assert order is not None
    assert order.stop_loss == pytest.approx(98.0 - 0.25 * 2.0)
    assert order.take_profit == 106.0
    assert order.rr_net >= 1.8
    assert order.estimated_fee_usdt == pytest.approx(
        order.recommended_notional * 2 * config.risk.taker_fee_rate
    )


def test_event_backtest_pending_limit_is_causal() -> None:
    order = _order()
    bars = [
        _bar(order.eligible_from_ms, low=100.5, high=101.0, close=100.8),
        _bar(order.eligible_from_ms + 60_000, low=99.0, high=101.0, close=100.0),
    ]
    first = advance_pending_limit(order, bars[:1])
    second = advance_pending_limit(order, bars)
    assert first["state"] == "PENDING_AT_END"
    assert second["state"] == "FILLED"
    assert second["filled_at_ms"] == bars[1].open_time_ms


def _control(timestamp: int, *, is_tp: bool = False, decile: int = 4) -> dict[str, object]:
    return {
        "control_id": f"control-{timestamp}",
        "timestamp_ms": timestamp,
        "decision_close_ms": timestamp - 1,
        "bar_index": (timestamp - DEV_START_MS) // 900_000,
        "year": 2021,
        "direction": "LONG",
        "regime": "TREND_UP",
        "atr": 2.0,
        "atr_percentile": 0.45,
        "atr_decile": decile,
        "close": 100.0,
        "is_tp_pattern": is_tp,
    }


def test_matched_controls_are_not_tp_candidates() -> None:
    candidate_time = DEV_START_MS + 200 * 900_000
    candidate = {**_candidate(candidate_time - 1), "timestamp_ms": candidate_time}
    pool = [_control(candidate_time, is_tp=True)] + [
        _control(candidate_time + distance * 900_000, is_tp=distance == 100)
        for distance in (96, 97, 98, 99, 100, 101)
    ]
    matches = match_controls([candidate], pool)
    assert len(matches) == 5
    assert all(not row["is_tp_pattern"] for row in matches)


def test_matched_controls_match_year_direction_regime_volatility() -> None:
    candidate_time = DEV_START_MS + 200 * 900_000
    candidate = {**_candidate(candidate_time - 1), "timestamp_ms": candidate_time}
    pool = [_control(candidate_time, is_tp=True)] + [
        _control(candidate_time + distance * 900_000) for distance in range(96, 102)
    ]
    matches = match_controls([candidate], pool)
    assert all(row["year"] == 2021 for row in matches)
    assert all(row["direction"] == "LONG" and row["regime"] == "TREND_UP" for row in matches)
    assert all(row["atr_decile"] == 4 and row["bar_distance"] >= MIN_BAR_DISTANCE for row in matches)


def test_directionality_horizons_never_cross_holdout() -> None:
    bars = [
        _bar(DEV_START_MS),
        _bar(DEV_END_MS - 120_000),
        _bar(DEV_END_MS - 60_000),
    ]
    series = IndexedOneMinuteSeries(bars)
    identity = {
        "decision_close_ms": DEV_END_MS - 120_001,
        "atr": 2.0,
        "close": 100.0,
        "direction": "LONG",
    }
    assert directionality_label(identity, series, 60)["incomplete"] is True
    exact_identity = {**identity, "decision_close_ms": DEV_END_MS - 60 * 60_000}
    assert directionality_label(exact_identity, series, 60)["incomplete"] is False


def test_bootstrap_is_deterministic() -> None:
    rows: list[dict[str, object]] = []
    for candidate_id, candidate_value in (("a", 1.0), ("b", -0.5)):
        rows.extend(
            [
                {
                    "candidate_id": candidate_id,
                    "kind": "CANDIDATE",
                    "horizon_minutes": horizon,
                    "incomplete": False,
                    "signed_return_atr": candidate_value,
                    "mfe_atr": 1.0,
                    "mae_atr": 0.5,
                    "reach_1_0": True,
                    "reach_1_5": False,
                    "reach_2_5": False,
                }
                for horizon in (60, 120, 240, 480, 720)
            ]
        )
        rows.extend(
            [
                {
                    "candidate_id": candidate_id,
                    "kind": "CONTROL",
                    "horizon_minutes": horizon,
                    "incomplete": False,
                    "signed_return_atr": 0.0,
                    "mfe_atr": 0.5,
                    "mae_atr": 0.5,
                    "reach_1_0": False,
                    "reach_1_5": False,
                    "reach_2_5": False,
                }
                for horizon in (60, 120, 240, 480, 720)
            ]
        )
    assert bootstrap_directionality(rows, seed=34, simulations=20) == bootstrap_directionality(
        rows, seed=34, simulations=20
    )


def test_all_v034_artifacts_development_only() -> None:
    _development_only([{"timestamp_ms": DEV_START_MS, "exited_at_ms": DEV_END_MS - 1}])
    with pytest.raises(ValueError, match="holdout firewall"):
        _development_only([{"timestamp_ms": DEV_END_MS}])
