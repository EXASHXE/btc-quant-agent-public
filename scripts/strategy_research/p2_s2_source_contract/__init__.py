"""Quant v0.6 P2 S2 B-line: Bounded Source Authority Contract and Synthetic Capability Gate.

This package provides a pure policy kernel and synthetic capability contract model
for evaluating data source admission safety. It operates EXCLUSIVELY on injected
fake syscall hooks and synthetic test fixtures. It contains NO production entrypoints
capable of accessing real market data or the owner's WSL root.
"""

from scripts.strategy_research.p2_s2_source_contract.constants import (
    CODE_START_SHA,
    CONTROLLER_ADMISSION_DESIGN_SHA,
    CONTROLLER_DISPATCH_SHA,
    CONTROLLER_TERMINATION_SHA,
    IMMUTABLE_OWNER_WSL_DATA_ROOT,
    ORIGINAL_STAT_RECEIPT_SHA,
    SIX_NONPROTECTED_CANDIDATE_PATHS,
    TASK_ID,
    TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA,
)
from scripts.strategy_research.p2_s2_source_contract.errors import (
    AccessDeniedError,
    BudgetExceededError,
    CapabilityLevelEscalationError,
    CapabilityTokenError,
    ClockProvenanceError,
    ContractSecurityError,
    EACCESAccessDeniedError,
    ENOENTNotFoundError,
    MountBoundaryViolationError,
    NotADirectoryError,
    PathTraversalError,
    ProductionRootOverrideDeniedError,
    ProtectedPartitionDeniedError,
    SymlinkEncounteredError,
    TypeMismatchError,
    ZeroBytePolicyViolationError,
)
from scripts.strategy_research.p2_s2_source_contract.policy_kernel import (
    SyntheticSourceContractKernel,
)
from scripts.strategy_research.p2_s2_source_contract.source_map import (
    build_source_scope_and_authority_matrix,
)
from scripts.strategy_research.p2_s2_source_contract.syscall_interface import (
    AbstractSyscallInterface,
    InMemoryFakeFilesystem,
    InstrumentedSyscallHook,
)
from scripts.strategy_research.p2_s2_source_contract.types import (
    AccessLevel,
    AuditReceipt,
    CapabilityToken,
    EvidenceCertainty,
    InstrumentRole,
    PolicyDecision,
    SyscallAccounting,
)

__all__ = [
    "CODE_START_SHA",
    "CONTROLLER_ADMISSION_DESIGN_SHA",
    "CONTROLLER_DISPATCH_SHA",
    "CONTROLLER_TERMINATION_SHA",
    "IMMUTABLE_OWNER_WSL_DATA_ROOT",
    "ORIGINAL_STAT_RECEIPT_SHA",
    "SIX_NONPROTECTED_CANDIDATE_PATHS",
    "TASK_ID",
    "TERMINATED_LOCATOR_COUNTEREXAMPLE_SHA",
    "AbstractSyscallInterface",
    "AccessDeniedError",
    "AccessLevel",
    "AuditReceipt",
    "BudgetExceededError",
    "CapabilityLevelEscalationError",
    "CapabilityToken",
    "CapabilityTokenError",
    "ClockProvenanceError",
    "ContractSecurityError",
    "EACCESAccessDeniedError",
    "ENOENTNotFoundError",
    "EvidenceCertainty",
    "InMemoryFakeFilesystem",
    "InstrumentRole",
    "InstrumentedSyscallHook",
    "MountBoundaryViolationError",
    "NotADirectoryError",
    "PathTraversalError",
    "PolicyDecision",
    "ProductionRootOverrideDeniedError",
    "ProtectedPartitionDeniedError",
    "SymlinkEncounteredError",
    "SyntheticSourceContractKernel",
    "SyscallAccounting",
    "TypeMismatchError",
    "ZeroBytePolicyViolationError",
    "build_source_scope_and_authority_matrix",
]
