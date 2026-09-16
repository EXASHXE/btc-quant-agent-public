"""Lifecycle state definitions and state-machine transitions for H40."""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

from .guards import H40GuardError, H40ReasonCode


class H40LifecycleState(str, Enum):
    """Lifecycle states for the H40 research and evaluation pipeline."""

    H40_PREREGISTERED = "H40_PREREGISTERED"
    H40_P1_SCAFFOLDED = "H40_P1_SCAFFOLDED"
    H40_DISCOVERY = "H40_DISCOVERY"
    H40_CANDIDATE_LOCKED = "H40_CANDIDATE_LOCKED"
    H40_WALK_FORWARD_VALIDATED = "H40_WALK_FORWARD_VALIDATED"
    H40_CONFIRMATION_READY = "H40_CONFIRMATION_READY"
    H40_CONFIRMATION_EVALUATED_ONCE = "H40_CONFIRMATION_EVALUATED_ONCE"
    H40_NO_GO = "H40_NO_GO"
    NOT_TESTABLE = "NOT_TESTABLE"


class H40LifecycleStateMachine:
    """Tracks and governs lifecycle state transitions for H40.

    Ensures that phase progression respects strict ordering and that Phase 1
    enters and remains in `H40_P1_SCAFFOLDED` without leaking into Discovery
    or Confirmation states.
    """

    # Authorized forward transitions
    VALID_TRANSITIONS: ClassVar[dict[H40LifecycleState, frozenset[H40LifecycleState]]] = {
        H40LifecycleState.H40_PREREGISTERED: frozenset({
            H40LifecycleState.H40_P1_SCAFFOLDED,
            H40LifecycleState.NOT_TESTABLE,
        }),
        H40LifecycleState.H40_P1_SCAFFOLDED: frozenset({
            H40LifecycleState.H40_DISCOVERY,
            H40LifecycleState.H40_NO_GO,
            H40LifecycleState.NOT_TESTABLE,
        }),
        H40LifecycleState.H40_DISCOVERY: frozenset({
            H40LifecycleState.H40_CANDIDATE_LOCKED,
            H40LifecycleState.H40_NO_GO,
            H40LifecycleState.NOT_TESTABLE,
        }),
        H40LifecycleState.H40_CANDIDATE_LOCKED: frozenset({
            H40LifecycleState.H40_WALK_FORWARD_VALIDATED,
            H40LifecycleState.H40_NO_GO,
        }),
        H40LifecycleState.H40_WALK_FORWARD_VALIDATED: frozenset({
            H40LifecycleState.H40_CONFIRMATION_READY,
            H40LifecycleState.H40_NO_GO,
        }),
        H40LifecycleState.H40_CONFIRMATION_READY: frozenset({
            H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE,
            H40LifecycleState.H40_NO_GO,
        }),
        H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE: frozenset(),
        H40LifecycleState.H40_NO_GO: frozenset(),
        H40LifecycleState.NOT_TESTABLE: frozenset(),
    }

    def __init__(self, initial_state: H40LifecycleState = H40LifecycleState.H40_P1_SCAFFOLDED) -> None:
        self._current_state = initial_state

    @property
    def current_state(self) -> H40LifecycleState:
        return self._current_state

    def transition_to(self, new_state: H40LifecycleState) -> None:
        """Transitions to new state if authorized, otherwise raises H40GuardError."""
        allowed = self.VALID_TRANSITIONS.get(self._current_state, frozenset())
        if new_state not in allowed:
            raise H40GuardError(
                H40ReasonCode.CONFIRMATION_NOT_READY
                if new_state == H40LifecycleState.H40_CONFIRMATION_READY
                else H40ReasonCode.NOT_TESTABLE,
                f"Illegal lifecycle transition from {self._current_state.value} to {new_state.value}.",
            )
        self._current_state = new_state
