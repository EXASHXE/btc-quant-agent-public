from __future__ import annotations

from .domain import (
    DirectionalDecision,
    EntryQuality,
    SignalLifecycleState,
)


def advance_lifecycle_state(
    previous_state: SignalLifecycleState | None,
    decision: DirectionalDecision,
    entry_quality: EntryQuality,
    is_invalidated: bool,
    has_setup: bool = False,
    is_near_ready: bool = False,
    age_bars: int = 0,
    max_age_bars: int = 8,
) -> SignalLifecycleState:
    """Deterministic transition for signal lifecycle.

    States:
    - NO SETUP -> CANDIDATE
    - CANDIDATE with near-ready setup -> ARMED
    - ARMED with all closed-bar + GOOD entry requirements -> TRIGGERED
    - TRIGGERED/ARMED with invalidation -> INVALIDATED
    - age beyond TTL -> EXPIRED
    """
    if is_invalidated:
        return SignalLifecycleState.INVALIDATED

    if age_bars >= max_age_bars and previous_state in (SignalLifecycleState.ARMED, SignalLifecycleState.TRIGGERED):
        return SignalLifecycleState.EXPIRED

    # Actionable signal with GOOD+ entry quality
    if decision in (DirectionalDecision.LONG, DirectionalDecision.SHORT):
        if entry_quality in (EntryQuality.EXCELLENT, EntryQuality.GOOD):
            return SignalLifecycleState.TRIGGERED
        # Marginal quality keeps it armed
        return SignalLifecycleState.ARMED

    # Setup candidate near-ready or awaiting confirmation (e.g. breakout confirmed waiting retest)
    if is_near_ready or (has_setup and entry_quality == EntryQuality.MARGINAL) or (previous_state == SignalLifecycleState.ARMED and has_setup):
        return SignalLifecycleState.ARMED

    # If decision returned to WAIT after being TRIGGERED, mark EXPIRED
    if previous_state == SignalLifecycleState.TRIGGERED:
        return SignalLifecycleState.EXPIRED

    return SignalLifecycleState.CANDIDATE
