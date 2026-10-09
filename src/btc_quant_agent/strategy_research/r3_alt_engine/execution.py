"""Pure B04 execution logic, stop-loss first, gap handling, target capping, and expiration."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    DECIMAL_CTX,
    quantize12dp,
    round_to_tick,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1m,
    Direction,
    ExitReason,
    OwnerLedger,
    SymbolFilters,
)


def evaluate_open_bar_exit(
    owner: OwnerLedger,
    bar: Bar1m,
    filters: SymbolFilters,
) -> tuple[bool, ExitReason | None, Decimal, int]:
    """
    Evaluate exit conditions at the exact open of the minute bar:
    1. Gap beyond stop loss -> Worse fill at bar.open
    2. Exact hold duration expiration (4h or 12h) -> Expiry at bar.open
    Returns (has_exit, reason, raw_price, economic_time_ms).
    """
    if owner.quantity <= Decimal(0) or owner.direction is None:
        return False, None, Decimal(0), bar.timestamp_ms

    direction = owner.direction
    stop_loss = owner.initial_stop
    target = owner.target
    expiry_time_ms = owner.entry_time_ms + owner.max_hold_ms

    # 1. Check open gap beyond stop loss (T21)
    if direction == Direction.LONG:
        if bar.open <= stop_loss:
            # Filled at worse open price
            return True, ExitReason.STOP_LOSS, bar.open, bar.timestamp_ms
    else:  # SHORT
        if bar.open >= stop_loss:
            # Filled at worse open price
            return True, ExitReason.STOP_LOSS, bar.open, bar.timestamp_ms

    # 2. Check hold expiration at exact open F + hold_ms (T23)
    if bar.timestamp_ms >= expiry_time_ms:
        # Expiry open. If open also breaches stop, stop wins (checked above).
        # Otherwise exit on expiry at open price.
        raw_exit = bar.open
        # Apply favorable cap (T22): if open is beyond target, cap at target
        if direction == Direction.LONG:
            raw_exit = min(raw_exit, target)
        else:
            raw_exit = max(raw_exit, target)
        return True, ExitReason.EXPIRY, raw_exit, bar.timestamp_ms

    return False, None, Decimal(0), bar.timestamp_ms


def evaluate_intrabar_exit(
    owner: OwnerLedger,
    bar: Bar1m,
    filters: SymbolFilters,
) -> tuple[bool, ExitReason | None, Decimal, int]:
    """
    Evaluate intrabar barrier exit conditions during [O, O+60000):
    1. SL-First rule: If both SL and TP breached within the same bar, STOP_LOSS wins (T20).
    2. Stop loss breach -> raw exit at stop_loss.
    3. Take profit breach -> raw exit at target.
    Intrabar economic timestamp is bar.timestamp_ms + 59999ms.
    Returns (has_exit, reason, raw_price, economic_time_ms).
    """
    if owner.quantity <= Decimal(0) or owner.direction is None:
        return False, None, Decimal(0), bar.timestamp_ms

    direction = owner.direction
    stop_loss = owner.initial_stop
    target = owner.target
    barrier_ts = bar.timestamp_ms + 59_999

    if direction == Direction.LONG:
        sl_breached = bar.low <= stop_loss
        tp_breached = bar.high >= target

        if sl_breached and tp_breached:
            # SL-first rule (T20): Stop-loss takes priority
            return True, ExitReason.STOP_LOSS, stop_loss, barrier_ts
        elif sl_breached:
            return True, ExitReason.STOP_LOSS, stop_loss, barrier_ts
        elif tp_breached:
            return True, ExitReason.TAKE_PROFIT, target, barrier_ts

    else:  # SHORT
        sl_breached = bar.high >= stop_loss
        tp_breached = bar.low <= target

        if sl_breached and tp_breached:
            # SL-first rule (T20)
            return True, ExitReason.STOP_LOSS, stop_loss, barrier_ts
        elif sl_breached:
            return True, ExitReason.STOP_LOSS, stop_loss, barrier_ts
        elif tp_breached:
            return True, ExitReason.TAKE_PROFIT, target, barrier_ts

    return False, None, Decimal(0), barrier_ts


def compute_effective_exit_price(
    raw_price: Decimal,
    direction: Direction,
    target: Decimal,
    exit_reason: ExitReason,
    filters: SymbolFilters,
    friction_rate: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Apply favorable exit price capping (T22) and adverse friction (spread + slippage).
    Favorable capping:
    - LONG: raw_price capped at target (min(raw_price, target)) across ALL favorable exits.
    - SHORT: raw_price capped at target (max(raw_price, target)) across ALL favorable exits.
    Friction embedding:
    - Closing LONG (selling): floor_to_tick(capped_raw * (1 - friction_rate))
    - Closing SHORT (buying): ceil_to_tick(capped_raw * (1 + friction_rate))
    Returns (effective_price, capped_raw_price).
    """
    capped_raw = raw_price
    if direction == Direction.LONG:
        if raw_price > target:
            capped_raw = target
        adverse_price = DECIMAL_CTX.multiply(capped_raw, DECIMAL_CTX.subtract(Decimal(1), friction_rate))
        effective = round_to_tick(adverse_price, filters.tick_size, mode="floor")
    else:  # SHORT
        if raw_price < target:
            capped_raw = target
        adverse_price = DECIMAL_CTX.multiply(capped_raw, DECIMAL_CTX.add(Decimal(1), friction_rate))
        effective = round_to_tick(adverse_price, filters.tick_size, mode="ceil")

    return quantize12dp(effective), quantize12dp(capped_raw)


def compute_effective_entry_price(
    raw_price: Decimal,
    direction: Direction,
    filters: SymbolFilters,
    friction_rate: Decimal,
) -> Decimal:
    """
    Model entry fill price embedding adverse half-spread and slippage.
    - Opening LONG (buying): ceil_to_tick(raw_price * (1 + friction_rate))
    - Opening SHORT (selling): floor_to_tick(raw_price * (1 - friction_rate))
    """
    if direction == Direction.LONG:
        adverse_price = DECIMAL_CTX.multiply(raw_price, DECIMAL_CTX.add(Decimal(1), friction_rate))
        effective = round_to_tick(adverse_price, filters.tick_size, mode="ceil")
    else:
        adverse_price = DECIMAL_CTX.multiply(raw_price, DECIMAL_CTX.subtract(Decimal(1), friction_rate))
        effective = round_to_tick(adverse_price, filters.tick_size, mode="floor")
    return quantize12dp(effective)
