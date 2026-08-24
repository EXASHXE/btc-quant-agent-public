from __future__ import annotations

from .config import RiskConfig, StrategyConfig
from .domain import Candidate, Direction, PositionPlan


def build_position_plan(
    candidate: Candidate,
    atr: float,
    strategy: StrategyConfig,
    risk: RiskConfig,
    funding_rate: float | None = None,
) -> PositionPlan | None:
    entry = (candidate.entry_low + candidate.entry_high) / 2.0
    buffer = strategy.stop_atr_buffer * atr
    if candidate.direction == Direction.LONG:
        stop = candidate.invalidation_level - buffer
        target = candidate.target_level
        gross_risk = entry - stop
        gross_reward = target - entry
    else:
        stop = candidate.invalidation_level + buffer
        target = candidate.target_level
        gross_risk = stop - entry
        gross_reward = entry - target
    if entry <= 0 or gross_risk <= 0 or gross_reward <= 0:
        return None

    round_trip_fee_rate = 2 * risk.taker_fee_rate
    round_trip_slippage_rate = 2 * risk.slippage_bps_per_side / 10_000
    effective_funding = risk.funding_rate_estimate if funding_rate is None else funding_rate
    observed_adverse_funding = (
        max(effective_funding, 0.0)
        if candidate.direction == Direction.LONG
        else max(-effective_funding, 0.0)
    )
    adverse_funding = max(observed_adverse_funding, risk.funding_stress_rate) * (
        risk.max_expected_funding_events
    )
    stop_distance_pct = gross_risk / entry
    total_loss_pct = (
        stop_distance_pct + round_trip_fee_rate + round_trip_slippage_rate + adverse_funding
    )
    total_reward_cost_pct = round_trip_fee_rate + round_trip_slippage_rate + adverse_funding
    rr_gross = gross_reward / gross_risk
    rr_net = (gross_reward / entry - total_reward_cost_pct) / total_loss_pct
    if rr_net < strategy.rr_min:
        return None

    desired_risk = risk.account_equity_usdt * risk.risk_per_trade
    notional = min(desired_risk / total_loss_pct, risk.max_notional_usdt)
    if notional < risk.min_notional_usdt:
        return None
    estimated_fee = notional * round_trip_fee_rate
    estimated_slippage = notional * round_trip_slippage_rate
    estimated_funding = notional * adverse_funding
    estimated_loss = notional * total_loss_pct
    return PositionPlan(
        entry_reference=entry,
        stop_loss=stop,
        take_profit=target,
        rr_gross=rr_gross,
        rr_net=rr_net,
        risk_usdt=estimated_loss,
        recommended_notional=notional,
        required_margin=notional / risk.display_leverage,
        estimated_fee_usdt=estimated_fee,
        estimated_slippage_usdt=estimated_slippage,
        estimated_funding_usdt=estimated_funding,
    )
