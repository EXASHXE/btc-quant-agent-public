"""Clock progression, event scheduling, causal availability, and tie-breaking."""

from collections.abc import Sequence

from btc_quant_agent.strategy_research.r3_alt_engine.journal import (
    InvalidMinuteClockError,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Event,
    EventKind,
)

# Deterministic typed tie priority
# Lower number is processed first when available_at_ms is identical
EVENT_TIE_PRIORITY: dict[EventKind, int] = {
    EventKind.OBSERVED_MARK: 1,
    EventKind.OBSERVED_MINUTE_BAR: 2,
    EventKind.EXIT_ACK: 3,
    EventKind.FILL_ACK: 4,
    EventKind.FUNDING_ACK: 5,
    EventKind.ECONOMIC_EXIT: 6,
    EventKind.RISK_KILL: 7,
    EventKind.FUNDING_OBLIGATION: 8,
    EventKind.ECONOMIC_FILL: 9,
    EventKind.ORDER_RESERVED: 10,
    EventKind.SIGNAL_AT_DECISION: 11,
    EventKind.END_OF_MINUTE_REPORT: 12,
}


def sort_events_for_processing(events: Sequence[Event]) -> list[Event]:
    """
    Sort eligible events by:
    1. available_at_ms (causal knowledge availability)
    2. Event kind tie-breaker priority
    3. Stable event_id string (deterministic input order invariance)
    """
    return sorted(
        events,
        key=lambda e: (
            e.available_at_ms,
            EVENT_TIE_PRIORITY.get(e.kind, 99),
            e.event_id,
        ),
    )


class ClockManager:
    """Manages advancing time and determining eligible event batches."""

    @staticmethod
    def validate_aligned_open(aligned_open_ms: int) -> None:
        """Reject non-aligned minute open (e.g. S - 5000ms). Raises InvalidMinuteClockError."""
        if aligned_open_ms % 60_000 != 0:
            raise InvalidMinuteClockError(
                f"Clock advance timestamp {aligned_open_ms} is not aligned to 60000ms minute open. "
                f"INVALID_MINUTE_CLOCK."
            )

    @staticmethod
    def filter_eligible_events(
        events: Sequence[Event],
        as_of_ms: int,
    ) -> list[Event]:
        """
        Filter events whose available_at_ms is <= as_of_ms.
        Future information is never consumed.
        """
        eligible = [e for e in events if e.available_at_ms <= as_of_ms]
        return sort_events_for_processing(eligible)
