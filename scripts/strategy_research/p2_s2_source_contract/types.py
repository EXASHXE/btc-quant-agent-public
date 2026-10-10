"""Data types, enums, and dataclasses for P2 S2 source contract."""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AccessLevel(int, Enum):
    """Hierarchical reader capability levels (default-deny, positive-only)."""
    L0_LOCATOR = 0    # Fixed locator known (0 read bytes, path identity verified)
    L1_METADATA = 1   # Metadata only (lstat: exists, size, mode, mtime; 0 read bytes)
    L2_SCHEMA = 2     # Structural schema/footer permission (0 row bytes, footer only)
    L3_QUALITY_QA = 3 # Timestamp monotonicity and quality audit (bounded byte sample)
    L4_MARKET_BODY = 4 # Real market price/mark/funding row values (requires prereg)

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, AccessLevel):
            return self.value >= other.value
        return NotImplemented

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, AccessLevel):
            return self.value > other.value
        return NotImplemented

    def __le__(self, other: Any) -> bool:
        if isinstance(other, AccessLevel):
            return self.value <= other.value
        return NotImplemented

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, AccessLevel):
            return self.value < other.value
        return NotImplemented


class PolicyDecision(str, Enum):
    """Deterministic policy decisions rendered by the contract kernel."""
    PERMITTED = "PERMITTED"
    DENIED_PROTECTED_PATH = "DENIED_PROTECTED_PATH"
    DENIED_ALLOWLIST_VIOLATION = "DENIED_ALLOWLIST_VIOLATION"
    DENIED_UNAUTHORIZED_LEVEL = "DENIED_UNAUTHORIZED_LEVEL"
    DENIED_CAPABILITY_INVALID = "DENIED_CAPABILITY_INVALID"
    DENIED_CAPABILITY_EXPIRED = "DENIED_CAPABILITY_EXPIRED"
    DENIED_ZERO_BYTE_POLICY = "DENIED_ZERO_BYTE_POLICY"
    DENIED_SYSCALL_BUDGET_EXCEEDED = "DENIED_SYSCALL_BUDGET_EXCEEDED"
    DENIED_SYMLINK_TRAVERSAL = "DENIED_SYMLINK_TRAVERSAL"
    DENIED_PARENT_TRAVERSAL = "DENIED_PARENT_TRAVERSAL"
    DENIED_NON_DIRECTORY_ANCESTOR = "DENIED_NON_DIRECTORY_ANCESTOR"
    DENIED_PERMISSION_ERROR = "DENIED_PERMISSION_ERROR"
    DENIED_NOT_FOUND = "DENIED_NOT_FOUND"
    DENIED_ROOT_OVERRIDE = "DENIED_ROOT_OVERRIDE"
    DENIED_TYPE_MISMATCH = "DENIED_TYPE_MISMATCH"
    DENIED_UNKNOWN_CLOCK_PROVENANCE = "DENIED_UNKNOWN_CLOCK_PROVENANCE"
    DENIED_MOUNT_BOUNDARY_VIOLATION = "DENIED_MOUNT_BOUNDARY_VIOLATION"


class EvidenceCertainty(str, Enum):
    """Certainty tiers for source assets."""
    OWNER_DECLARED = "OWNER_DECLARED"
    PHYSICAL_METADATA_EXECUTOR_OBSERVED = "PHYSICAL_METADATA_EXECUTOR_OBSERVED"
    UNVERIFIED_RIGHTS = "UNVERIFIED_RIGHTS"
    UNKNOWN_FILE_CONTINUITY = "UNKNOWN_FILE_CONTINUITY"
    PROTECTED_DO_NOT_TOUCH = "PROTECTED_DO_NOT_TOUCH"


class InstrumentRole(str, Enum):
    """Specific role and semantic scope of data objects."""
    BTC_PERP_1M_KLINE = "BTC_PERP_1M_KLINE"
    BTC_PERP_RAW_KLINE_CONTAINER = "BTC_PERP_RAW_KLINE_CONTAINER"
    BTC_PERP_RAW_MARK_CONTAINER = "BTC_PERP_RAW_MARK_CONTAINER"
    BTC_PERP_FUNDING_EVENTS_CSV = "BTC_PERP_FUNDING_EVENTS_CSV"
    BTC_PERP_RAW_FUNDING_CONTAINER = "BTC_PERP_RAW_FUNDING_CONTAINER"
    BTC_SPOT_MANIFEST_AND_DATA = "BTC_SPOT_MANIFEST_AND_DATA"
    ETH_HOURLY_AUXILIARY = "ETH_HOURLY_AUXILIARY"
    LEGACY_DERIVATIVE_HOURLY = "LEGACY_DERIVATIVE_HOURLY"
    UNPROVEN_ETH_SOL_PERP_1M = "UNPROVEN_ETH_SOL_PERP_1M"
    PROTECTED_HOLDOUT = "PROTECTED_HOLDOUT"


@dataclass
class CapabilityToken:
    """Cryptographically verifiable or synthetic permission token."""
    token_id: str
    subject: str
    allowed_paths: list[str]
    max_level: AccessLevel
    max_bytes: int = 0
    max_syscalls: int = 50
    created_at_utc: str = "2026-10-10T12:00:00Z"
    expires_at_utc: str = "2026-10-11T12:00:00Z"
    signature_hash: str = ""
    is_test_fixture: bool = False

    def __post_init__(self) -> None:
        if not self.signature_hash:
            # Generate deterministic pseudo-signature for the capability token
            payload = f"{self.token_id}:{self.subject}:{self.max_level.value}:{self.max_bytes}:{self.expires_at_utc}"
            self.signature_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_valid_signature(self) -> bool:
        payload = f"{self.token_id}:{self.subject}:{self.max_level.value}:{self.max_bytes}:{self.expires_at_utc}"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.signature_hash == expected


@dataclass
class SyscallAccounting:
    """Rigorous accounting of actual system calls executed at the syscall boundary."""
    lstat_calls: int = 0
    open_calls: int = 0
    fstat_calls: int = 0
    read_calls: int = 0
    bytes_read: int = 0
    scandir_calls: int = 0
    close_calls: int = 0
    total_calls: int = 0

    def record_lstat(self) -> None:
        self.lstat_calls += 1
        self.total_calls += 1

    def record_open(self) -> None:
        self.open_calls += 1
        self.total_calls += 1

    def record_fstat(self) -> None:
        self.fstat_calls += 1
        self.total_calls += 1

    def record_read(self, n_bytes: int) -> None:
        self.read_calls += 1
        self.bytes_read += n_bytes
        self.total_calls += 1

    def record_scandir(self) -> None:
        self.scandir_calls += 1
        self.total_calls += 1

    def record_close(self) -> None:
        self.close_calls += 1
        self.total_calls += 1


@dataclass
class AuditReceipt:
    """Verifiable audit receipt produced for every evaluated contract request."""
    receipt_id: str
    task_id: str
    timestamp_utc: str
    requested_path: str
    canonical_relative_path: str
    requested_level: AccessLevel
    decision: PolicyDecision
    reason: str
    syscall_accounting: SyscallAccounting
    exception_class: str | None = None
    is_synthetic_fixture: bool = True
    metadata_size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "task_id": self.task_id,
            "timestamp_utc": self.timestamp_utc,
            "requested_path": self.requested_path,
            "canonical_relative_path": self.canonical_relative_path,
            "requested_level": self.requested_level.name,
            "decision": self.decision.value,
            "reason": self.reason,
            "syscall_accounting": {
                "lstat_calls": self.syscall_accounting.lstat_calls,
                "open_calls": self.syscall_accounting.open_calls,
                "fstat_calls": self.syscall_accounting.fstat_calls,
                "read_calls": self.syscall_accounting.read_calls,
                "bytes_read": self.syscall_accounting.bytes_read,
                "scandir_calls": self.syscall_accounting.scandir_calls,
                "close_calls": self.syscall_accounting.close_calls,
                "total_calls": self.syscall_accounting.total_calls,
            },
            "exception_class": self.exception_class,
            "is_synthetic_fixture": self.is_synthetic_fixture,
            "metadata_size_bytes": self.metadata_size_bytes,
        }


@dataclass
class SourceMapEntry:
    """Metadata and authority mapping for one data source item."""
    source_id: str
    relative_path: str
    role: InstrumentRole
    certainty: EvidenceCertainty
    receipt_sha: str
    size_bytes: int | None
    is_regular_file: bool
    is_directory: bool
    expected_fields: list[str] = field(default_factory=list)
    clock_definition: str = "UTC"
    rights_status: str = "UNVERIFIED"
    continuity_status: str = "UNKNOWN"
    notes: str = ""
