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
    age_bars: int = 0,
    max_age_bars: int = 6,
) -> SignalLifecycleState:
    """Deterministic transition for signal lifecycle.

    States:
    - CANDIDATE: setup shape exists but entry not yet ready
    - ARMED: conditions nearly satisfied / waiting confirmation
    - TRIGGERED: all closed-bar requirements satisfied with GOOD+ entry
    - INVALIDATED: structure or risk gate failed
    - EXPIRED: TTL exceeded
    """
    if is_invalidated:
        return SignalLifecycleState.INVALIDATED

    if age_bars >= max_age_bars and previous_state in (SignalLifecycleState.ARMED, SignalLifecycleState.TRIGGERED):
        return SignalLifecycleState.EXPIRED

    if decision in (DirectionalDecision.LONG, DirectionalDecision.SHORT):
        if entry_quality in (EntryQuality.EXCELLENT, EntryQuality.GOOD):
            return SignalLifecycleState.TRIGGERED
        if entry_quality == EntryQuality.MARGINAL:
            return SignalLifecycleState.ARMED
        return SignalLifecycleState.CANDIDATE

    # If decision is WAIT
    if previous_state == SignalLifecycleState.TRIGGERED:
        return SignalLifecycleState.EXPIRED

    return SignalLifecycleState.CANDIDATE
