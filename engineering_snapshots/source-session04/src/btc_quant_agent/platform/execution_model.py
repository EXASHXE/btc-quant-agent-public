"""Synthetic fills only. Candle touches never establish entry-limit fills."""

from __future__ import annotations

from btc_quant_agent.economic.fee_model import FeeModel

from .config import PlatformConfig
from .core import EntryPlan, MarketEvent, SimulatedFill, dec, fingerprint, quantize


def fee(notional: float, config: PlatformConfig) -> float:
    bps = config.execution.fee_bps
    if bps < 0:
        return -abs(notional) * abs(bps) / 10000  # Explicit configured rebate scenario.
    return FeeModel(taker_fee_rate=bps / 10000).calculate_fee(notional)


def entry_fill(plan: EntryPlan, event: MarketEvent, config: PlatformConfig) -> SimulatedFill | None:
    if plan.action != "ENTRY_ELIGIBLE" or plan.risk is None or event.quote is None:
        return None
    q = event.quote
    if q.reason(event.spec, event.decision_ts, config.execution.quote_max_age_ms):
        return None
    long = plan.candidate.direction == "LONG"
    if config.execution.entry_mode == "limit":
        # A resting buy limit at lower region / sell at upper region needs a later executable cross.
        limit = plan.candidate.entry_low if long else plan.candidate.entry_high
        if q.ask >= limit if long else q.bid <= limit:
            return None
        price = limit  # Conservative no price improvement, synthetic crossing assumption only.
    else:
        price = plan.entry_price
    if price is None:
        return None
    available = q.ask_quantity if long else q.bid_quantity
    if available is None:
        return None  # Capacity cannot be fabricated from an OHLC touch.
    amount = min(
        plan.risk.quantity * dec(config.execution.fill_fraction),
        available,
        dec(event.candle.volume * config.execution.volume_participation),
    )
    try:
        quantity = quantize(amount, event.spec.quantity_step)
    except ValueError:
        return None
    notional = float(quantity * price * event.spec.multiplier)
    if notional < float(event.spec.min_notional):
        return None
    slip = max(
        0,
        float((price - (q.ask if long else q.bid)) * (1 if long else -1) * quantity * event.spec.multiplier),
    )
    return SimulatedFill(
        fingerprint([plan.candidate.id, event.decision_ts, price, quantity]),
        plan.candidate.id,
        event.spec.symbol,
        plan.candidate.direction,
        price,
        quantity,
        event.decision_ts,
        fee(notional, config),
        slip,
    )


def exit_price(
    event: MarketEvent, direction: str, config: PlatformConfig, reference: float | None = None
) -> tuple[float, float, float, float] | None:
    """Return modeled execution, reference mid, spread/unit and slippage/unit."""
    side = 1 if direction == "LONG" else -1
    if reference is None:
        if event.quote is None or event.quote.reason(event.spec, event.decision_ts):
            return None
        q = event.quote
        reference = float((q.bid + q.ask) / 2)
        executable = float(q.bid if side == 1 else q.ask)
        spread = abs(executable - reference)
    else:
        spread = reference * config.execution.spread_bps / 20000
        executable = reference - side * spread
    raw = executable * (1 - side * config.execution.slippage_bps / 10000)
    actual = float(quantize(raw, event.spec.tick_size, up=side == -1))
    slippage = max(0, side * (executable - actual))
    return actual, reference, spread, slippage
