"""Stop-distance sizing and portfolio limits are hard gates, independent of ranks."""

from __future__ import annotations

from dataclasses import dataclass

from .config import PlatformConfig
from .core import InstrumentSpec, RiskPlan, StrategyCandidate, quantize


@dataclass(frozen=True)
class Exposure:
    symbol: str
    direction: str
    notional: float
    beta: float | None = None


def size(
    candidate: StrategyCandidate,
    spec: InstrumentSpec,
    entry: float,
    config: PlatformConfig,
    exposures: list[Exposure],
    correlations: dict[tuple[str, str], float] | None = None,
    funding_rate: float | None = None,
    beta: float | None = None,
) -> tuple[RiskPlan | None, tuple[str, ...]]:
    r, e = config.risk, config.execution
    veto = []
    side = 1 if candidate.direction == "LONG" else -1
    stop = float(candidate.stop)
    worst_entry = (
        max(entry, float(candidate.entry_high)) if side == 1 else min(entry, float(candidate.entry_low))
    )
    distance = side * (worst_entry - stop)
    if distance <= 0:
        return None, ("INVALID_STRUCTURAL_STOP",)
    if r.leverage > spec.max_leverage:
        veto.append("CONTRACT_LEVERAGE_LIMIT")
    liquidation = (
        entry * (1 - side * (1 / r.leverage - spec.maintenance_margin_rate))
        if spec.market == "PERPETUAL"
        else None
    )
    if liquidation is not None and side * (stop - liquidation) / entry < r.liquidation_buffer:
        veto.append("LIQUIDATION_BUFFER")
    projected = None
    if spec.market == "PERPETUAL":
        if funding_rate is None:
            if e.funding == "required":
                veto.append("FUNDING_UNKNOWN")
        else:
            # Conservative projection: ceil(horizon / 8h), future rates held constant, not guaranteed.
            import math

            interval = spec.funding_interval_hours
            if interval is None or interval <= 0:
                veto.append("FUNDING_INTERVAL_UNKNOWN")
            settlements = max(
                1,
                math.ceil(config.exits.max_holding_bars * config.interval_seconds / ((interval or 8) * 3600)),
            )
            projected = max(0, side * funding_rate) * settlements
            if projected > r.max_funding_drag:
                veto.append("FUNDING_DRAG")
    friction = worst_entry * (
        2 * (max(e.fee_bps, 0) + e.slippage_bps) / 10000 + e.spread_bps / 10000 + (projected or 0)
    )
    budget = r.equity * r.per_trade
    unit_loss = (distance + friction) * float(spec.multiplier)
    try:
        quantity = quantize(
            min(budget / unit_loss, r.equity * r.max_symbol / (worst_entry * float(spec.multiplier))),
            spec.quantity_step,
        )
    except ValueError:
        return None, ("SIZE_BELOW_STEP",)
    notional = float(quantity) * entry * float(spec.multiplier)
    gross = sum(x.notional for x in exposures)
    own = sum(x.notional for x in exposures if x.symbol == spec.symbol)
    if len(exposures) >= r.max_positions:
        veto.append("POSITION_LIMIT")
    if gross + notional > r.equity * r.max_gross:
        veto.append("GROSS_EXPOSURE_LIMIT")
    if own + notional > r.equity * r.max_symbol:
        veto.append("SYMBOL_EXPOSURE_LIMIT")
    if notional < float(spec.min_notional):
        veto.append("MIN_NOTIONAL")
    if gross / r.leverage + notional / r.leverage > r.equity:
        veto.append("CAPITAL_OCCUPANCY")
    same = [x for x in exposures if x.direction == candidate.direction]
    if same:
        if correlations is None or any((spec.symbol, x.symbol) not in correlations for x in same):
            veto.append("PORTFOLIO_CORRELATION_UNKNOWN")
        elif (
            sum(abs(correlations[(spec.symbol, x.symbol)]) >= r.correlation_threshold for x in same)
            >= r.max_correlated
        ):
            veto.append("CORRELATION_CONCENTRATION")
    if beta is not None and all(x.beta is not None for x in exposures):
        existing = sum(x.notional * x.beta * (1 if x.direction == "LONG" else -1) for x in exposures)
        if abs(existing + side * notional * beta) > r.equity * r.max_beta_exposure:
            veto.append("BETA_CONCENTRATION")
    elif exposures:
        veto.append("PORTFOLIO_BETA_UNKNOWN")
    plan = RiskPlan(
        quantity,
        budget,
        float(quantity) * unit_loss,
        notional,
        r.leverage,
        liquidation,
        friction,
        projected,
        (
            "Modeled stop loss can be exceeded by gaps.",
            "Liquidation proxy omits exchange tiers and cross margin.",
            "Funding projection holds current rate constant; settlement cash is accounted separately.",
        ),
    )
    return (None, tuple(sorted(set(veto)))) if veto else (plan, ())
