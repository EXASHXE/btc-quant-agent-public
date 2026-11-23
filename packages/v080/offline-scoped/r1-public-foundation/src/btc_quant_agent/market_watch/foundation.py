"""Deterministic advisory source vetoes; no quote acquisition or order authority."""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from math import isfinite
from typing import Any, TypeGuard

from .config import MarketWatchConfig, compute_required_closed_bars
from .domain import (
    ExecutableQuote,
    InputClock,
    MarketSnapshot,
    PriceSource,
    QuoteVerification,
    ScanHealth,
)

QUOTE_MAX_AGE_MS = 5_000
REFERENCE_MAX_SKEW_MS = 60_000
DERIVATIVE_MAX_AGE_MS = 3_600_000


def metadata_map(value: object) -> dict[str, Any]:
    return value if type(value) is dict else {}


def timestamp(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and type(value) is int and value > 0


def clock_reason(clock: InputClock, cutoff: int, max_age: int) -> str | None:
    if type(clock) is not InputClock or not timestamp(cutoff):
        return "TIMING_UNKNOWN"
    source, received, available = (clock.source_event_at_ms, clock.receiver_known_at_ms, clock.available_at_ms)
    if not timestamp(source) or not timestamp(received) or not timestamp(available):
        return "TIMING_UNKNOWN"
    if not source <= received <= available <= cutoff:
        return "CLOCK_ORDER_INVALID"
    if cutoff - source > max_age or cutoff - received > max_age:
        return "STALE"
    return None


def reference_reasons(candidate: MarketSnapshot, reference: MarketSnapshot | None,
                      symbol: str) -> tuple[str, ...]:
    if type(candidate) is not MarketSnapshot or type(reference) is not MarketSnapshot:
        return (f"REFERENCE_{symbol}_TIMING_UNKNOWN",)
    if reference.symbol != symbol:
        return (f"REFERENCE_{symbol}_SYMBOL_MISMATCH",)
    reason = clock_reason(reference.clock, candidate.decision_time_ms, 14_400_000)
    reasons = [f"REFERENCE_{symbol}_{reason}"] if reason else []
    available = getattr(reference.clock, "available_at_ms", None)
    own = getattr(candidate.clock, "available_at_ms", None)
    if timestamp(available) and timestamp(own) and abs(available - own) > REFERENCE_MAX_SKEW_MS:
        reasons.append(f"REFERENCE_{symbol}_SKEW")
    for name in ("15m", "1h", "4h"):
        a = metadata_map(candidate.closed_bar_watermarks).get(name)
        b = metadata_map(reference.closed_bar_watermarks).get(name)
        if not timestamp(a) or not timestamp(b) or a != b:
            reasons.append(f"REFERENCE_{symbol}_{name}_BAR_MISMATCH")
    return tuple(sorted(set(reasons)))


def number(value: object) -> TypeGuard[int | float]:
    if type(value) not in (int, float) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def positive(value: object) -> TypeGuard[int | float]:
    return number(value) and value > 0


def actionable_reasons(snapshot: MarketSnapshot, config: MarketWatchConfig | None = None,
                       *, cutoff_ms: int | None = None,
                       derivatives_required: bool = True) -> tuple[str, ...]:
    """ACTION veto only; informational WATCH and risk escalation are independent."""
    if type(snapshot) is not MarketSnapshot:
        return ("SOURCE_METADATA_UNKNOWN",)
    cutoff = snapshot.decision_time_ms if cutoff_ms is None else cutoff_ms
    reasons = [r for r in snapshot.reference_timing_reasons if type(r) is str] if type(snapshot.reference_timing_reasons) in (tuple, list) else ["SOURCE_METADATA_UNKNOWN"]
    reason = clock_reason(snapshot.clock, cutoff, 14_400_000)
    if reason:
        reasons.append(f"SNAPSHOT_{reason}")
    if not timestamp(cutoff) or not timestamp(snapshot.decision_time_ms):
        reasons.append("DECISION_TIMING_UNKNOWN")
    elif cutoff < snapshot.decision_time_ms:
        reasons.append("DECISION_AFTER_CUTOFF")
    if snapshot.health != ScanHealth.OK:
        reasons.append("SOURCE_HEALTH_DEGRADED")
    required = compute_required_closed_bars(config or MarketWatchConfig())
    for name, duration in (("15m", 900_000), ("1h", 3_600_000), ("4h", 14_400_000)):
        count = metadata_map(snapshot.candle_counts).get(name)
        if type(count) is not int or count < required:
            reasons.append(f"BARS_{name}_INSUFFICIENT")
        reason = clock_reason(metadata_map(snapshot.candle_clocks).get(name, InputClock()), cutoff, duration * 2)
        if reason:
            reasons.append(f"BARS_{name}_{reason}")
    quote = getattr(snapshot.price, "executable_quote", None)
    if type(quote) is not ExecutableQuote:
        reasons.append("EXECUTABLE_QUOTE_UNKNOWN")
    else:
        if (quote.source != PriceSource.EXECUTABLE_BID_ASK
                or quote.verification != QuoteVerification.VERIFIED
                or type(quote.authority) is not str or not quote.authority.strip()
                or quote.symbol != snapshot.symbol):
            reasons.append("EXECUTABLE_QUOTE_UNVERIFIED")
        if not positive(quote.bid) or not positive(quote.ask) or quote.bid > quote.ask:
            reasons.append("EXECUTABLE_QUOTE_INVALID")
        reason = clock_reason(quote.clock, cutoff, QUOTE_MAX_AGE_MS)
        if reason:
            reasons.append(f"EXECUTABLE_QUOTE_{reason}")
    if not all(positive(metadata_map(snapshot.symbol_filters).get(k)) for k in ("tick_size", "step_size")):
        reasons.append("SYMBOL_FILTERS_UNKNOWN")
    for symbol in ("BTCUSDT", "ETHUSDT"):
        if symbol == snapshot.symbol:
            continue
        reason = clock_reason(metadata_map(snapshot.reference_clocks).get(symbol, InputClock()),
                              snapshot.decision_time_ms, 14_400_000)
        if reason:
            reasons.append(f"REFERENCE_{symbol}_{reason}")
    if derivatives_required:
        if snapshot.derivatives.endpoint_errors:
            reasons.append("DERIVATIVES_FAILED")
        for field in ("funding_rate", "current_open_interest", "oi_1h_change"):
            value = getattr(snapshot.derivatives, field)
            if not number(value):
                reasons.append(f"DERIVATIVES_{field}_UNKNOWN")
            reason = clock_reason(metadata_map(snapshot.derivative_clocks).get(field, InputClock()),
                                  cutoff, DERIVATIVE_MAX_AGE_MS)
            if reason:
                reasons.append(f"DERIVATIVES_{field}_{reason}")
    return tuple(sorted(set(reasons)))


def increment(value: float, step: float, *, upward: bool = False) -> float:
    """Quantize to actual increments; reject invalid/zero executable levels."""
    if type(value) not in (int, float, Decimal) or type(step) not in (int, float, Decimal):
        raise ValueError("INVALID_INCREMENT_INPUT")
    try:
        amount, quantum = Decimal(str(value)), Decimal(str(step))
        if not amount.is_finite() or not quantum.is_finite() or amount <= 0 or quantum <= 0:
            raise ValueError("INVALID_INCREMENT_INPUT")
        rounded = (amount / quantum).to_integral_value(
            rounding=ROUND_CEILING if upward else ROUND_FLOOR) * quantum
        if rounded <= 0:
            raise ValueError("INCREMENT_ROUNDS_TO_ZERO")
        return float(rounded)
    except InvalidOperation as exc:
        raise ValueError("INVALID_INCREMENT_INPUT") from exc


def normalize_quantity(quantity: float, symbol_filters: dict[str, float]) -> float:
    """Round quantity down, without claiming sizing or account authority."""
    if not positive(metadata_map(symbol_filters).get("step_size")):
        raise ValueError("SYMBOL_FILTERS_UNKNOWN")
    return increment(quantity, symbol_filters["step_size"])
