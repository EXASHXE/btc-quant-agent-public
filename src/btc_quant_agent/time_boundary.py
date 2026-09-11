from __future__ import annotations

import math


class ClockBoundaryError(ValueError):
    """Raised when timestamps cannot share a causal comparison boundary."""


def validate_clock_skew(
    *, exchange_time_ms: int, receipt_time_ms: int, max_abs_skew_ms: int
) -> None:
    for name, value in (
        ("exchange_time_ms", exchange_time_ms),
        ("receipt_time_ms", receipt_time_ms),
        ("max_abs_skew_ms", max_abs_skew_ms),
    ):
        if type(value) is not int or value < 0:
            raise ClockBoundaryError(f"{name} must be a nonnegative integer")
    skew = receipt_time_ms - exchange_time_ms
    if abs(skew) > max_abs_skew_ms:
        raise ClockBoundaryError(
            f"local/exchange clock skew {skew}ms exceeds {max_abs_skew_ms}ms"
        )


def validate_availability(
    *, available_at_ms: int, decision_time_ms: int, max_age_ms: int
) -> None:
    for name, value in (
        ("available_at_ms", available_at_ms),
        ("decision_time_ms", decision_time_ms),
        ("max_age_ms", max_age_ms),
    ):
        if type(value) is not int or value < 0:
            raise ClockBoundaryError(f"{name} must be a nonnegative integer")
    if available_at_ms > decision_time_ms:
        raise ClockBoundaryError("observation is not yet available at decision time")
    if decision_time_ms - available_at_ms > max_age_ms:
        raise ClockBoundaryError("observation is stale at decision time")


def monotonic_elapsed_ms(start: float, end: float) -> float:
    """Return elapsed duration only for readings from one monotonic clock."""
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        raise ClockBoundaryError("monotonic clock readings are invalid or moved backwards")
    return (end - start) * 1_000.0
