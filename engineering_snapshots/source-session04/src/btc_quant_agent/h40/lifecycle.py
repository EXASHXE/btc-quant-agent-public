"""Lifecycle state definitions and state-machine transitions for H40."""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

from .guards import H40GuardError, H40ReasonCode
from .lifecycle_authority import H40RuntimeSnapshotSeal, VerifiedLifecycleAuthorization


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
            H40LifecycleState.H40_NO_GO,
        }),
        H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE: frozenset(),
        H40LifecycleState.H40_NO_GO: frozenset(),
        H40LifecycleState.NOT_TESTABLE: frozenset(),
    }

    ALLOWED_INITIAL_STATES: ClassVar[frozenset[H40LifecycleState]] = frozenset({
        H40LifecycleState.H40_PREREGISTERED,
        H40LifecycleState.H40_P1_SCAFFOLDED,
    })

    def __init__(
        self,
        initial_state: H40LifecycleState = H40LifecycleState.H40_P1_SCAFFOLDED,
        *,
        _synthetic_test_mode: bool = False,
    ) -> None:
        if initial_state not in self.ALLOWED_INITIAL_STATES:
            if initial_state in {
                H40LifecycleState.H40_CONFIRMATION_READY,
                H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE,
            }:
                raise H40GuardError(
                    H40ReasonCode.CONFIRMATION_NOT_READY,
                    f"Cannot initialize lifecycle directly at confirmation state '{initial_state.value}'.",
                )
            raise H40GuardError(
                H40ReasonCode.NOT_TESTABLE,
                f"Cannot initialize lifecycle directly at post-scaffold state '{initial_state.value}'. "
                f"Must start at H40_PREREGISTERED or H40_P1_SCAFFOLDED.",
            )
        self._current_state = initial_state
        self._run_authority_id: str | None = None
        self._last_receipt_hash: str | None = None
        self._synthetic_test_mode = _synthetic_test_mode

    @classmethod
    def synthetic_for_tests(
        cls,
        initial_state: H40LifecycleState = H40LifecycleState.H40_P1_SCAFFOLDED,
    ) -> H40LifecycleStateMachine:
        """Create an explicitly non-authoritative machine for synthetic fixtures."""
        return cls(initial_state, _synthetic_test_mode=True)

    @property
    def current_state(self) -> H40LifecycleState:
        return self._current_state

    def transition_to(self, new_state: H40LifecycleState) -> None:
        """Fail closed: adjacency alone never supplies F01 evidence authority."""
        reason = (
            H40ReasonCode.CONFIRMATION_NOT_READY
            if new_state
            in {
                H40LifecycleState.H40_CONFIRMATION_READY,
                H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE,
            }
            else H40ReasonCode.NOT_TESTABLE
        )
        raise H40GuardError(
            reason,
            "Direct lifecycle adjacency is not authority; use a reverified "
            "VerifiedLifecycleAuthorization.",
        )

    def transition_with_verified_authority(
        self,
        authorization: VerifiedLifecycleAuthorization,
    ) -> None:
        """Apply one adjacency only after receipt, run, and lineage verification."""
        if not isinstance(authorization, VerifiedLifecycleAuthorization):
            raise TypeError("transition requires VerifiedLifecycleAuthorization")
        if authorization.synthetic_only and not self._synthetic_test_mode:
            raise H40GuardError(
                H40ReasonCode.NOT_TESTABLE,
                "Synthetic lifecycle authority cannot advance a production state machine.",
            )
        seal = authorization.context.get("seal")
        if seal is not None and not getattr(seal, "synthetic_only", False):
            if not isinstance(seal, H40RuntimeSnapshotSeal):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    "production authorization lacks runtime snapshot seal",
                )
            seal.verify_against_accepted_ledger()
        try:
            new_state = H40LifecycleState(authorization.target_state)
        except ValueError as exc:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "Transition authority names an unknown target state.",
            ) from exc
        if new_state == H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE:
            raise H40GuardError(
                H40ReasonCode.CONFIRMATION_NOT_READY,
                "H40-FSA-F02 remains OPEN_SEALED; confirmation evaluation is prohibited.",
            )
        allowed = self.VALID_TRANSITIONS.get(self._current_state, frozenset())
        if new_state not in allowed:
            raise H40GuardError(
                H40ReasonCode.CONFIRMATION_NOT_READY
                if new_state == H40LifecycleState.H40_CONFIRMATION_READY
                else H40ReasonCode.NOT_TESTABLE,
                f"Illegal lifecycle transition from {self._current_state.value} to {new_state.value}.",
            )
        authorization.assert_valid(
            source_state=self._current_state.value,
            target_state=new_state.value,
            expected_run_authority_id=self._run_authority_id,
            expected_upstream_receipt_hash=self._last_receipt_hash,
        )
        self._current_state = new_state
        self._run_authority_id = authorization.run_authority_id
        self._last_receipt_hash = authorization.receipt_hash
