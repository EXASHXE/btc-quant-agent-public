"""Reason-code vocabulary and access guards for H40.

Provides a stable 16-entry pre-outcome reason code vocabulary and access guards
enforcing confirmation holdout privacy, H39 protected surface isolation,
and default-deny execution policies.
"""

from __future__ import annotations

from enum import Enum


class H40ReasonCode(str, Enum):
    """Stable reason-code vocabulary for H40 pre-outcome failures and abstentions."""

    # Section 11 mandatory reason codes
    SOURCE_MISSING = "SOURCE_MISSING"
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    SOURCE_GAP = "SOURCE_GAP"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    PIT_UNAVAILABLE = "PIT_UNAVAILABLE"
    PRODUCT_MISMATCH = "PRODUCT_MISMATCH"
    INTERVAL_MISMATCH = "INTERVAL_MISMATCH"
    OUTSIDE_PREREGISTERED_SPLIT = "OUTSIDE_PREREGISTERED_SPLIT"
    PROTECTED_SURFACE_DENIED = "PROTECTED_SURFACE_DENIED"
    CONFIRMATION_NOT_READY = "CONFIRMATION_NOT_READY"
    UNAUTHORIZED_FAMILY = "UNAUTHORIZED_FAMILY"
    SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"
    CONFIG_IDENTITY_CONFLICT = "CONFIG_IDENTITY_CONFLICT"
    NOT_TESTABLE = "NOT_TESTABLE"
    EXECUTION_DISABLED = "EXECUTION_DISABLED"

    # Contextual boundary and eligibility reason codes
    FAMILY_PAIR_RESTRICTED = "FAMILY_PAIR_RESTRICTED"
    CONFIRMATION_HOLD_LOCKED = "CONFIRMATION_HOLD_LOCKED"
    HORIZON_TRUNCATED = "HORIZON_TRUNCATED"
    PURGE_BOUNDARY = "PURGE_BOUNDARY"
    THRESHOLD_UNMET = "THRESHOLD_UNMET"
    LOOKBACK_RESERVED = "LOOKBACK_RESERVED"


class H40GuardError(RuntimeError):
    """Raised when an H40 access guard or preregistration invariant is violated."""

    def __init__(self, reason_code: H40ReasonCode, message: str) -> None:
        super().__init__(f"[{reason_code.value}] {message}")
        self.reason_code = reason_code
        self.message = message


class H40ConfirmationGuard:
    """Guards confirmation holdout outcomes against premature discovery/evaluation access.

    Allows inspecting confirmation metadata (e.g., timestamps, partition bounds,
    row counts, partition hash) but strictly denies access to future price series,
    returns, labels, or candidate evaluation before lifecycle state reaches
    `H40_CONFIRMATION_READY`.
    """

    def __init__(self, is_confirmation_ready: bool = False) -> None:
        self._is_confirmation_ready = is_confirmation_ready

    @property
    def is_ready(self) -> bool:
        return self._is_confirmation_ready

    def assert_metadata_accessible(self) -> None:
        """Partition metadata, bounds, and timestamp indices are always accessible."""
        return

    def assert_outcomes_accessible(self) -> None:
        """Denies access to confirmation future returns, prices, or evaluation metrics."""
        if not self._is_confirmation_ready:
            raise H40GuardError(
                H40ReasonCode.CONFIRMATION_NOT_READY,
                "Confirmation partition outcomes, returns, and evaluation are sealed "
                "until explicit H40_CONFIRMATION_READY authority is granted.",
            )


class H40ProtectedSurfaceGuard:
    """Guards H39 protected outcome surfaces and final holdout data against access."""

    # Forbidden substrings / path markers
    FORBIDDEN_LOCATORS: tuple[str, ...] = (
        "h39_validation",
        "h39_protected",
        "final_holdout",
        "v0323_h39",
        "v0.3.23_holdout",
    )

    @classmethod
    def assert_surface_allowed(cls, locator: str) -> None:
        """Checks if a locator or path touches protected surfaces and fails closed."""
        lower = locator.lower().replace("\\", "/")
        for pattern in cls.FORBIDDEN_LOCATORS:
            if pattern in lower:
                raise H40GuardError(
                    H40ReasonCode.PROTECTED_SURFACE_DENIED,
                    f"Access to protected surface matching '{pattern}' is permanently denied: {locator}",
                )


class H40ExecutionGuard:
    """Enforces default-deny execution across all H40 components."""

    @classmethod
    def assert_execution_disabled(cls) -> None:
        """Always fails closed if execution or order dispatch is attempted."""
        raise H40GuardError(
            H40ReasonCode.EXECUTION_DISABLED,
            "Execution is permanently disabled in H40 research scaffold. Default action is NO_TRADE.",
        )
