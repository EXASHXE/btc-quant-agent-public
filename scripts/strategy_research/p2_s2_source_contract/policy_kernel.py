"""Synthetic Source Contract Policy Kernel.

A pure policy kernel that enforces positive-only reader permissions and capability gates.
Accepts ONLY injected fake syscall hooks and fixture roots under test.
Contains NO production entrypoints or network/file APIs able to access user's WSL root or real market data.
"""

import os
import uuid
from datetime import UTC, datetime

from scripts.strategy_research.p2_s2_source_contract.component_walker import (
    ComponentSafeDescriptorWalker,
)
from scripts.strategy_research.p2_s2_source_contract.constants import (
    DEFAULT_MAX_BYTES,
    IMMUTABLE_OWNER_WSL_DATA_ROOT,
    METADATA_PARENT_DIRECTORIES,
    PROTECTED_PARTITION_PATTERNS,
    RECORDED_METADATA_FILE_SIZES,
    SIX_NONPROTECTED_CANDIDATE_PATHS,
    TASK_ID,
)
from scripts.strategy_research.p2_s2_source_contract.errors import (
    AccessDeniedError,
    BudgetExceededError,
    CapabilityLevelEscalationError,
    CapabilityTokenError,
    CapabilityTokenExpiredError,
    CapabilityTokenInvalidError,
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
from scripts.strategy_research.p2_s2_source_contract.syscall_interface import (
    AbstractSyscallInterface,
    InstrumentedSyscallHook,
)
from scripts.strategy_research.p2_s2_source_contract.types import (
    AccessLevel,
    AuditReceipt,
    CapabilityToken,
    InstrumentRole,
    PolicyDecision,
    SyscallAccounting,
)


class SyntheticSourceContractKernel:
    """Pure policy kernel for source admission and access control."""

    def __init__(
        self,
        fixture_root: str | None = None,
        syscall_hook: AbstractSyscallInterface | None = None,
        is_test_mode: bool = False,
        allow_custom_root_flag: bool = False,
    ) -> None:
        self.is_test_mode = is_test_mode
        self.allow_custom_root_flag = allow_custom_root_flag

        # Security check: Counterexample defense against CLI custom root override
        # If not in explicit test mode, custom roots are strictly forbidden
        if not is_test_mode:
            if fixture_root is not None and fixture_root != IMMUTABLE_OWNER_WSL_DATA_ROOT:
                raise ProductionRootOverrideDeniedError(
                    f"Production mode forbids custom root overrides ({fixture_root}). "
                    f"Owner WSL root is immutable: {IMMUTABLE_OWNER_WSL_DATA_ROOT}"
                )
            if allow_custom_root_flag:
                raise ProductionRootOverrideDeniedError(
                    "Production mode forbids 'allow_custom_root' flag."
                )
            self.root_dir = IMMUTABLE_OWNER_WSL_DATA_ROOT
            self.hook: AbstractSyscallInterface | None = None
        else:
            self.root_dir = fixture_root or "/synthetic/root"
            self.hook = syscall_hook

    def _canonicalize_relative_path(self, target_rel_path: str) -> str:
        """Sanitize and canonicalize relative path, checking for traversal aliases."""
        if "\0" in target_rel_path:
            raise PathTraversalError("Null byte in path.")
        if "\\" in target_rel_path:
            raise PathTraversalError("Backslashes not permitted in relative path.")
        if target_rel_path.startswith("/"):
            raise PathTraversalError("Leading slash not permitted in relative path.")

        parts = [p for p in target_rel_path.split("/") if p]
        canonical_parts: list[str] = []
        for p in parts:
            if p == ".":
                continue
            if p == "..":
                raise PathTraversalError(f"Traversal '..' rejected in path: {target_rel_path}")
            canonical_parts.append(p)

        canonical = "/".join(canonical_parts)
        if not canonical:
            raise PathTraversalError("Empty relative path.")

        # Commonpath sanity check
        simulated_full = os.path.join(self.root_dir, canonical).replace("\\", "/")
        norm_root = self.root_dir.replace("\\", "/").rstrip("/")
        if not simulated_full.startswith(norm_root + "/"):
            raise PathTraversalError(f"Path escapes root directory: {simulated_full}")

        return canonical

    def _check_protected_patterns(self, rel_path: str) -> None:
        """Reject access to protected partitions and credentials."""
        for pattern in PROTECTED_PARTITION_PATTERNS:
            if pattern in rel_path:
                raise ProtectedPartitionDeniedError(
                    f"Access denied to protected partition or sensitive file pattern: '{pattern}' in '{rel_path}'"
                )

    def evaluate_request(
        self,
        target_rel_path: str,
        token: CapabilityToken | None,
        requested_level: AccessLevel,
        role: InstrumentRole = InstrumentRole.BTC_PERP_1M_KLINE,
        requested_bytes: int = 0,
        current_time_utc: str | None = None,
        verify_clock_provenance: bool = False,
        clock_provenance_proven: bool = False,
    ) -> AuditReceipt:
        """Evaluate source access request against all positive capability gates."""
        receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
        timestamp_now = current_time_utc or datetime.now(UTC).isoformat()
        accounting = SyscallAccounting()

        try:
            # 1. Reject production physical execution if hook not provided
            if not self.is_test_mode:
                raise AccessDeniedError(
                    "Direct physical execution on owner data root is prohibited. "
                    "Kernel runs exclusively with synthetic hooks."
                )

            if self.hook is None:
                raise AccessDeniedError("Syscall hook is required in test mode.")

            # 2. Canonicalize path & detect traversal
            canonical_rel = self._canonicalize_relative_path(target_rel_path)

            # 3. Check hard protected partition denials
            self._check_protected_patterns(canonical_rel)

            # 4. Capability Token Checks
            if token is None:
                raise CapabilityTokenInvalidError("Capability token is required for all data operations.")

            if not token.is_valid_signature():
                raise CapabilityTokenInvalidError(
                    f"Capability token {token.token_id} has invalid cryptographic signature."
                )

            # Expiration check
            if current_time_utc and token.expires_at_utc < current_time_utc:
                raise CapabilityTokenExpiredError(
                    f"Capability token {token.token_id} expired at {token.expires_at_utc} (current: {current_time_utc})."
                )

            # Level non-escalation check
            if requested_level > token.max_level:
                raise CapabilityLevelEscalationError(
                    f"Requested level {requested_level.name} exceeds token grant {token.max_level.name}."
                )

            # Path allowlist in token
            if canonical_rel not in token.allowed_paths:
                raise CapabilityTokenInvalidError(
                    f"Path {canonical_rel} not authorized by capability token {token.token_id}."
                )

            # 5. Global Contract Positive Allowlist Check for L1+
            allowed_files = set(SIX_NONPROTECTED_CANDIDATE_PATHS) | set(RECORDED_METADATA_FILE_SIZES.keys())
            allowed_dirs = set(METADATA_PARENT_DIRECTORIES)

            if canonical_rel not in allowed_files and canonical_rel not in allowed_dirs:
                # E.g. Candidate month=05 in 2021 or random file
                raise CapabilityTokenInvalidError(
                    f"Path '{canonical_rel}' is not in the approved positive allowlist."
                )

            # 6. Instrument role & semantic type checks
            if role == InstrumentRole.BTC_SPOT_MANIFEST_AND_DATA:
                if "BTCUSDT_SPOT" not in canonical_rel:
                    raise TypeMismatchError(f"Spot role specified for non-spot path: {canonical_rel}")
            elif role == InstrumentRole.BTC_PERP_1M_KLINE:
                if canonical_rel not in SIX_NONPROTECTED_CANDIDATE_PATHS:
                    raise TypeMismatchError(f"BTC_PERP_1M_KLINE role requested for non-candidate file: {canonical_rel}")
            elif role == InstrumentRole.BTC_PERP_RAW_MARK_CONTAINER:
                if "raw/mark_price" not in canonical_rel:
                    raise TypeMismatchError(f"Raw mark role requested for non-mark path: {canonical_rel}")
                if verify_clock_provenance and not clock_provenance_proven:
                    raise ClockProvenanceError(
                        "Raw Mark price container existence does NOT prove continuous 1m PIT Mark. Proof missing."
                    )
            elif role == InstrumentRole.BTC_PERP_FUNDING_EVENTS_CSV:
                if "funding_events.csv" not in canonical_rel and "raw/funding" not in canonical_rel:
                    raise TypeMismatchError(f"Funding role requested for non-funding path: {canonical_rel}")
                if verify_clock_provenance and not clock_provenance_proven:
                    raise ClockProvenanceError(
                        "Funding events existence does NOT prove known-at/settlement timing. Proof missing."
                    )

            # 7. Zero-Byte Policy Enforcement
            if requested_bytes > DEFAULT_MAX_BYTES:
                raise ZeroBytePolicyViolationError(
                    f"Requested {requested_bytes} bytes exceeds zero-byte policy (max_bytes={DEFAULT_MAX_BYTES})."
                )

            # 8. Component-safe Descriptor Walk
            walker = ComponentSafeDescriptorWalker(self.hook)
            leaf_stat, _ = walker.walk_and_verify(
                root_dir=self.root_dir,
                rel_path=canonical_rel,
                verify_open_toctou=(requested_level >= AccessLevel.L2_SCHEMA),
            )

            # Copy accounting from hook if instrumented
            if isinstance(self.hook, InstrumentedSyscallHook):
                accounting = self.hook.accounting

            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=canonical_rel,
                requested_level=requested_level,
                decision=PolicyDecision.PERMITTED,
                reason="All positive capability contract checks and component walk passed successfully.",
                syscall_accounting=accounting,
                exception_class=None,
                is_synthetic_fixture=self.is_test_mode,
                metadata_size_bytes=leaf_stat.st_size,
            )

        except ProtectedPartitionDeniedError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_PROTECTED_PATH,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except CapabilityTokenExpiredError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_CAPABILITY_EXPIRED,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except CapabilityLevelEscalationError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_UNAUTHORIZED_LEVEL,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except (CapabilityTokenInvalidError, CapabilityTokenError) as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_CAPABILITY_INVALID,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except ZeroBytePolicyViolationError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_ZERO_BYTE_POLICY,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except SymlinkEncounteredError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_SYMLINK_TRAVERSAL,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except PathTraversalError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_PARENT_TRAVERSAL,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except NotADirectoryError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_NON_DIRECTORY_ANCESTOR,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except MountBoundaryViolationError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_MOUNT_BOUNDARY_VIOLATION,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except EACCESAccessDeniedError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_PERMISSION_ERROR,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except ENOENTNotFoundError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_NOT_FOUND,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except BudgetExceededError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_SYSCALL_BUDGET_EXCEEDED,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except TypeMismatchError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_TYPE_MISMATCH,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except ClockProvenanceError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_UNKNOWN_CLOCK_PROVENANCE,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except ProductionRootOverrideDeniedError as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_ROOT_OVERRIDE,
                reason=str(exc),
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
        except (ContractSecurityError, OSError) as exc:
            return AuditReceipt(
                receipt_id=receipt_id,
                task_id=TASK_ID,
                timestamp_utc=timestamp_now,
                requested_path=target_rel_path,
                canonical_relative_path=target_rel_path,
                requested_level=requested_level,
                decision=PolicyDecision.DENIED_PERMISSION_ERROR,
                reason=f"Security or OS error: {exc}",
                syscall_accounting=accounting,
                exception_class=exc.__class__.__name__,
                is_synthetic_fixture=self.is_test_mode,
            )
