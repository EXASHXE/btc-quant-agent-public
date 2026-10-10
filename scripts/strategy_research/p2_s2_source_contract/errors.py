"""Specific error hierarchy for P2 S2 contract enforcement.

Every error corresponds to an unambiguous security or policy violation,
ensuring failure modes are distinct and cannot be confused or silently masked.
"""


class ContractSecurityError(Exception):
    """Base class for all security contract errors."""


class PathTraversalError(ContractSecurityError):
    """Raised when path contains '..', absolute aliases, or escapes target root."""


class SymlinkEncounteredError(ContractSecurityError):
    """Raised when any component in the path resolution is a symbolic link."""


class ProtectedPartitionDeniedError(ContractSecurityError):
    """Raised when attempting to access any protected partition (2026, forward, h39)."""


class BudgetExceededError(ContractSecurityError):
    """Raised when system call count or I/O budget ceiling is exceeded."""


class CapabilityTokenError(ContractSecurityError):
    """Base class for capability token validation errors."""


class CapabilityTokenInvalidError(CapabilityTokenError):
    """Raised when token signature is corrupt, missing, or improperly scoped."""


class CapabilityTokenExpiredError(CapabilityTokenError):
    """Raised when token expiry timestamp is prior to current evaluation time."""


class CapabilityLevelEscalationError(CapabilityTokenError):
    """Raised when requested access level exceeds token's granted max_level."""


class ZeroBytePolicyViolationError(ContractSecurityError):
    """Raised when an operation attempts to read market data bytes under max_bytes=0."""


class ProductionRootOverrideDeniedError(ContractSecurityError):
    """Raised when attempting to override immutable owner data root outside test harness."""


class MountBoundaryViolationError(ContractSecurityError):
    """Raised when traversing across filesystem/device boundaries (st_dev change)."""


class AccessDeniedError(ContractSecurityError):
    """Base class for permission-related errors."""


class EACCESAccessDeniedError(AccessDeniedError):
    """Raised when filesystem permission is denied (errno 13 EACCES).

    STRICTLY DISTINCT from ENOENTNotFoundError.
    """


class ENOENTNotFoundError(ContractSecurityError):
    """Raised when a path component does not exist (errno 2 ENOENT).

    STRICTLY DISTINCT from EACCESAccessDeniedError.
    """


class NotADirectoryError(ContractSecurityError):
    """Raised when an intermediate path component is not a directory (errno 20 ENOTDIR)."""


class TypeMismatchError(ContractSecurityError):
    """Raised when attempting to access a source using an incompatible instrument role."""


class ClockProvenanceError(ContractSecurityError):
    """Raised when true continuous 1m Mark PIT or funding settlement clock proof is unverified."""
