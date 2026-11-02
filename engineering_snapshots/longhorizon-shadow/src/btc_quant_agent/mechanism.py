from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from .backtest import FundingEvent
from .config import RiskConfig, StrategyConfig
from .domain import Candidate, Direction, Setup, TimeframeFeatures
from .multifactor import FactorAssessment
from .risk import build_position_plan

EXPERIMENT_ARMS = ("CONTROL", "E0", "E1", "E2", "E3")
E1_ATR_MULTIPLIER = 2.5


@dataclass(frozen=True)
class RRDecomposition:
    entry_reference: float
    invalidation_level: float
    atr: float
    stop_atr_buffer: float
    stop_before_buffer: float
    actual_stop: float
    stop_distance_usdt: float
    stop_distance_pct: float
    stop_distance_atr: float
    target: float
    reward_distance_usdt: float
    reward_distance_pct: float
    reward_distance_atr: float
    rr_gross: float | None
    fee_rate_total: float
    slippage_rate_total: float
    funding_stress_total: float
    rr_after_fee: float | None
    rr_after_fee_slippage: float | None
    rr_net: float | None
    desired_risk_usdt: float
    raw_notional_before_cap: float | None
    capped_notional: float | None
    min_notional_pass: bool
    valid_geometry: bool
    gross_rr_pass: bool
    after_fee_pass: bool
    after_fee_slippage_pass: bool
    after_funding_pass: bool
    frozen_risk_plan_pass: bool
    reject_reason: str
    required_target_price: float | None
    required_reward_atr: float | None
    actual_target_gap_atr: float | None
    raw_invalidation_rr_net: float | None
    buffer_crossed_threshold: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _net_rr(reward_pct: float, risk_pct: float, cost_rate: float) -> float:
    return (reward_pct - cost_rate) / (risk_pct + cost_rate)


def decompose_rr(
    candidate: Candidate,
    atr: float,
    strategy: StrategyConfig,
    risk: RiskConfig,
) -> RRDecomposition:
    entry = (candidate.entry_low + candidate.entry_high) / 2.0
    buffer = strategy.stop_atr_buffer * atr
    stop = (
        candidate.invalidation_level - buffer
        if candidate.direction == Direction.LONG
        else candidate.invalidation_level + buffer
    )
    raw_risk = (
        entry - candidate.invalidation_level
        if candidate.direction == Direction.LONG
        else candidate.invalidation_level - entry
    )
    stop_distance = entry - stop if candidate.direction == Direction.LONG else stop - entry
    reward = (
        candidate.target_level - entry
        if candidate.direction == Direction.LONG
        else entry - candidate.target_level
    )
    valid = entry > 0 and stop_distance > 0 and reward > 0
    risk_pct = stop_distance / entry if valid else 0.0
    raw_risk_pct = raw_risk / entry if entry > 0 and raw_risk > 0 else None
    reward_pct = reward / entry if valid else 0.0
    fee = 2 * risk.taker_fee_rate
    slippage = 2 * risk.slippage_bps_per_side / 10_000
    funding = risk.funding_stress_rate * risk.max_expected_funding_events
    gross_rr = reward / stop_distance if valid else None
    after_fee = _net_rr(reward_pct, risk_pct, fee) if valid else None
    after_slippage = _net_rr(reward_pct, risk_pct, fee + slippage) if valid else None
    net = _net_rr(reward_pct, risk_pct, fee + slippage + funding) if valid else None
    raw_rr_net = (
        _net_rr(reward_pct, raw_risk_pct, fee + slippage + funding)
        if valid and raw_risk_pct is not None
        else None
    )
    gross_pass = bool(gross_rr is not None and gross_rr >= strategy.rr_min)
    fee_pass = bool(after_fee is not None and after_fee >= strategy.rr_min)
    slippage_pass = bool(
        after_slippage is not None and after_slippage >= strategy.rr_min
    )
    funding_pass = bool(net is not None and net >= strategy.rr_min)
    total_loss_pct = risk_pct + fee + slippage + funding if valid else 0.0
    desired_risk = risk.account_equity_usdt * risk.risk_per_trade
    raw_notional = desired_risk / total_loss_pct if total_loss_pct > 0 else None
    capped = min(raw_notional, risk.max_notional_usdt) if raw_notional is not None else None
    min_notional = bool(capped is not None and capped >= risk.min_notional_usdt)
    frozen_plan = build_position_plan(candidate, atr, strategy, risk)
    if not valid:
        reason = "INVALID_GEOMETRY"
    elif not gross_pass:
        reason = "GROSS_RR_BELOW_THRESHOLD"
    elif not fee_pass:
        reason = "FEE_DRAG_CROSSED_THRESHOLD"
    elif not slippage_pass:
        reason = "SLIPPAGE_DRAG_CROSSED_THRESHOLD"
    elif not funding_pass:
        reason = "FUNDING_STRESS_CROSSED_THRESHOLD"
    elif not min_notional:
        reason = "MIN_NOTIONAL_REJECT"
    else:
        reason = "PASS"
    required_reward_pct = (
        strategy.rr_min * (risk_pct + fee + slippage + funding)
        + fee
        + slippage
        + funding
        if valid
        else None
    )
    required_reward = entry * required_reward_pct if required_reward_pct is not None else None
    required_target = (
        entry + required_reward
        if required_reward is not None and candidate.direction == Direction.LONG
        else entry - required_reward
        if required_reward is not None
        else None
    )
    required_atr = required_reward / atr if required_reward is not None and atr > 0 else None
    gap_atr = (
        (required_reward - reward) / atr
        if required_reward is not None and atr > 0
        else None
    )
    return RRDecomposition(
        entry,
        candidate.invalidation_level,
        atr,
        strategy.stop_atr_buffer,
        candidate.invalidation_level,
        stop,
        stop_distance,
        risk_pct,
        stop_distance / atr if atr > 0 else 0.0,
        candidate.target_level,
        reward,
        reward_pct,
        reward / atr if atr > 0 else 0.0,
        gross_rr,
        fee,
        slippage,
        funding,
        after_fee,
        after_slippage,
        net,
        desired_risk,
        raw_notional,
        capped,
        min_notional,
        valid,
        gross_pass,
        fee_pass,
        slippage_pass,
        funding_pass,
        frozen_plan is not None,
        reason,
        required_target,
        required_atr,
        gap_atr,
        raw_rr_net,
        bool(
            raw_rr_net is not None
            and raw_rr_net >= strategy.rr_min
            and (net is None or net < strategy.rr_min)
        ),
    )


def e1_fixed_tp_target(
    candidate: Candidate, features: TimeframeFeatures
) -> Candidate:
    if candidate.setup != Setup.TREND_PULLBACK:
        return candidate
    offset = E1_ATR_MULTIPLIER * features.atr
    target = (
        features.close + offset
        if candidate.direction == Direction.LONG
        else features.close - offset
    )
    return replace(candidate, target_level=target)


def deduplicate_factor_score(
    control: FactorAssessment,
    candidate: Candidate,
    features: TimeframeFeatures,
    config: StrategyConfig,
    mode: Literal["E2", "E3"],
) -> FactorAssessment:
    del candidate
    if control.available_max <= 0:
        return control
    scores = dict(control.group_scores)
    raw = control.raw_score
    available = control.available_max
    if mode == "E2":
        if "trend_structure" not in scores:
            return control
        scores.pop("trend_structure")
        raw -= 30.0
        available -= 30.0
    else:
        if "participation_flow" not in scores or not features.cvd_available:
            return control
        # Direction is encoded by the control participation score: 100 means aligned.
        aligned = scores["participation_flow"] == 100.0
        raw -= 6.0
        available -= 6.0
        scores["participation_flow"] = 100.0 if aligned else 0.0
    normalized = 100.0 * raw / available if available > 0 else 0.0
    positive = sum(score >= 50.0 for score in scores.values())
    required = min(config.min_positive_factor_groups, len(scores))
    if normalized < config.factor_score_min:
        blocked = f"factor score {normalized:.1f} below {config.factor_score_min:.1f}"
    elif positive < required:
        blocked = f"positive factor groups {positive} below {required}"
    else:
        blocked = None
    return replace(
        control,
        score=round(normalized, 2),
        positive_groups=positive,
        group_scores=scores,
        blocked_reason=blocked,
        raw_score=raw,
        available_max=available,
    )


def funding_crossing_count(
    signal_timestamp_ms: int,
    setup: Setup,
    funding_events: list[FundingEvent],
    trend_holding_minutes: int,
    breakout_holding_minutes: int,
) -> int:
    holding = (
        trend_holding_minutes
        if setup == Setup.TREND_PULLBACK
        else breakout_holding_minutes
    )
    end_ms = signal_timestamp_ms + holding * 60_000
    return sum(
        signal_timestamp_ms < event.timestamp_ms <= end_ms
        for event in funding_events
    )
