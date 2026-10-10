"""Data structures, root custody records, and sanitized metadata schemas for P2 S3A.

All output structures enforce strict sanitization:
- Column min/max/null_count/distinct_count statistics are never included.
- Custom key_value_metadata payloads are suppressed.
- Every output marks ``header_verification_status = "FILE_HEADER_NOT_VERIFIED"``.
- ``SyntheticTestGrant`` is explicitly labeled ``TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION``
  (unkeyed public SHA-256 structural checksum, NOT HMAC and NOT owner/Controller authority).
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    HEADER_STATUS_NOT_VERIFIED,
    MAX_ATTEMPTED_FS_CALLS,
    MAX_FOOTER_READ_BYTES,
    MAX_TOTAL_FILE_READ_BYTES,
    MAX_TRAILER_READ_BYTES,
    S3_SINGLE_PILOT_REL_PATH,
    SYNTHETIC_GRANT_TOKEN_SEMANTICS,
)

_SYNTHETIC_GRANT_CHECKSUM_DOMAIN: str = (
    "TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION_V2"
)


@dataclass(frozen=True)
class TrustedTempRootCustody:
    """Harness-attested custody record for an isolated temporary fixture directory.

    Proves that the fixture root's ancestor chain from ``/`` was walked
    component-by-component with ``O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`` at
    attestation time and records the exact expected ``(st_dev, st_ino)`` of the
    parent directory and (when already materialized) the fixture root itself.
    """

    custody_id: str
    canonical_temp_root: str
    expected_parent_dev: int
    expected_parent_ino: int
    expected_root_dev: int | None
    expected_root_ino: int | None
    attested_uid: int


# Process-local registry of harness-attested temp root custody records and
# designated forbidden owner-surrogate temp trees used in adversarial tests.
_TRUSTED_CUSTODY_REGISTRY: dict[str, TrustedTempRootCustody] = {}
# One preparation -> one reader. The exact meter is handed off, never reset.
_TRUSTED_PREPARATIONS: dict[str, tuple[int, Any, Any]] = {}
_FORBIDDEN_SURROGATE_TREES: dict[str, set[tuple[int, int]]] = {}


def _prune_stale_surrogates() -> None:
    """Remove any registered surrogate temp tree that has already been deleted."""
    stale = [p for p in _FORBIDDEN_SURROGATE_TREES if not os.path.exists(p)]
    for p in stale:
        _FORBIDDEN_SURROGATE_TREES.pop(p, None)


def register_forbidden_owner_surrogate_tree(surrogate_root: str | Path) -> None:
    """Register a temporary directory tree as a forbidden owner-root surrogate.

    Used in adversarial regression tests to model a prohibited owner data root
    entirely inside ``tmp_path`` without ever touching or referencing the real
    ``/root/workspace/project/Quant-agent/data`` directory.
    """
    from scripts.strategy_research.p2_s3_footer_reader.fd_syscall_wrapper import (
        validate_and_split_temp_root_path,
    )

    validate_and_split_temp_root_path(str(surrogate_root))
    _prune_stale_surrogates()
    norm = str(surrogate_root).replace("\\", "/").rstrip("/")
    inodes: set[tuple[int, int]] = set()
    root_path = Path(surrogate_root)
    if root_path.exists():
        st = os.stat(root_path, follow_symlinks=False)
        inodes.add((int(st.st_dev), int(st.st_ino)))
        for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
            dp = Path(dirpath)
            dst = os.stat(dp, follow_symlinks=False)
            inodes.add((int(dst.st_dev), int(dst.st_ino)))
            for dname in dirnames:
                cst = os.stat(dp / dname, follow_symlinks=False)
                inodes.add((int(cst.st_dev), int(cst.st_ino)))
            for fname in filenames:
                fst = os.stat(dp / fname, follow_symlinks=False)
                inodes.add((int(fst.st_dev), int(fst.st_ino)))
    _FORBIDDEN_SURROGATE_TREES[norm] = inodes


def is_forbidden_surrogate_inode(dev: int, ino: int) -> bool:
    """Return True if (dev, ino) belongs to a live registered forbidden surrogate tree."""
    key = (int(dev), int(ino))
    return any(key in inodes for inodes in _FORBIDDEN_SURROGATE_TREES.values())


def is_forbidden_surrogate_path(candidate_path: str) -> bool:
    """Return True if candidate_path lexically matches or is inside a forbidden surrogate."""
    norm = candidate_path.replace("\\", "/").rstrip("/")
    for surr in _FORBIDDEN_SURROGATE_TREES:
        if norm == surr or norm.startswith(surr + "/"):
            return True
    return False


def get_registered_trusted_custody(custody_id: str) -> TrustedTempRootCustody | None:
    """Look up a harness-registered TrustedTempRootCustody by custody_id."""
    if not custody_id:
        return None
    return _TRUSTED_CUSTODY_REGISTRY.get(custody_id)


def consume_prepared_meter(custody_id: str) -> tuple[Any, Any] | None:
    """Consume process-local TEST_ONLY preparation once; no filesystem lookup."""
    prepared = _TRUSTED_PREPARATIONS.pop(custody_id, None)
    if prepared is None or prepared[0] != os.getpid():
        return None  # Forked copies cannot replay or reattribute parent preparation.
    return prepared[1], prepared[2]


def _walk_and_attest_temp_root(
    temp_root_path: str, *, max_calls: int, max_trailer: int,
    max_footer: int, max_total: int,
) -> TrustedTempRootCustody:
    """Account preparation and its cleanup with the very same invocation meter."""
    from scripts.strategy_research.p2_s3_footer_reader.errors import (
        FDCloseFailureError,
        S3FooterReaderError,
    )
    from scripts.strategy_research.p2_s3_footer_reader.fd_syscall_wrapper import (
        MeteredPosixSyscallWrapper,
    )

    meter = MeteredPosixSyscallWrapper(
        max_attempted_fs_calls=max_calls, max_trailer_read_bytes=max_trailer,
        max_footer_read_bytes=max_footer, max_total_read_bytes=max_total,
    )
    failure: S3FooterReaderError | None = None
    root_st = None
    try:
        fd = meter.open_anchored_root_dir(temp_root_path)
        root_st = meter.fstat_fd(fd)
    except (S3FooterReaderError, OSError) as exc:
        failure = exc if isinstance(exc, S3FooterReaderError) else S3FooterReaderError(
            f"Preparation OS failure: errno={exc.errno}", decision_code="DENIED_OS_ERROR"
        )
    finally:
        meter.close_all_open_fds(raise_on_failure=False)
    if meter.open_fds_count or meter.close_failed_count:
        failure = FDCloseFailureError("Preparation has unconfirmed FD closure.")
    meter.finish_preparation()
    parent_st = meter.last_root_parent_stat
    custody = TrustedTempRootCustody(
        custody_id=f"S3A-CUSTODY-{secrets.token_hex(12)}",
        canonical_temp_root=temp_root_path.rstrip("/"),
        expected_parent_dev=int(parent_st.st_dev) if parent_st else 0,
        expected_parent_ino=int(parent_st.st_ino) if parent_st else 0,
        expected_root_dev=int(root_st.st_dev) if root_st else None,
        expected_root_ino=int(root_st.st_ino) if root_st else None,
        attested_uid=os.geteuid() if hasattr(os, "geteuid") else 0,
    )
    _TRUSTED_CUSTODY_REGISTRY[custody.custody_id] = custody
    _TRUSTED_PREPARATIONS[custody.custody_id] = (os.getpid(), meter, failure)
    return custody


@dataclass(frozen=True)
class SyntheticTestGrant:
    """Explicit test-only capability descriptor for the S3A synthetic footer reader.

    IMPORTANT SECURITY HONESTY NOTICE (R2 F02):
    ``signature_hex`` / ``compute_expected_checksum()`` is an unkeyed public SHA-256
    structural integrity checksum labeled ``TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION``.
    It is NOT an HMAC, NOT cryptographic authentication, and NOT an owner or
    Controller authorization grant. A self-minted ``SyntheticTestGrant`` can NEVER
    authorize access to the physical owner data root, unattested directories, or
    production execution.
    """

    grant_id: str
    stage_scope: str
    allowed_rel_path: str
    synthetic_fixture_root: str
    issued_at_epoch_s: int
    expires_at_epoch_s: int
    max_attempted_fs_calls: int = MAX_ATTEMPTED_FS_CALLS
    max_trailer_read_bytes: int = MAX_TRAILER_READ_BYTES
    max_footer_read_bytes: int = MAX_FOOTER_READ_BYTES
    max_total_read_bytes: int = MAX_TOTAL_FILE_READ_BYTES
    allow_row_group_reads: bool = False
    allow_real_owner_root: bool = False
    signature_hex: str = ""
    token_semantics: str = SYNTHETIC_GRANT_TOKEN_SEMANTICS
    is_external_authority_grant: bool = False
    trusted_custody_id: str = ""

    def compute_expected_checksum(self) -> str:
        """Compute unkeyed public SHA-256 structural integrity checksum (test-only)."""
        payload = (
            f"{_SYNTHETIC_GRANT_CHECKSUM_DOMAIN}|"
            f"semantics={self.token_semantics}|"
            f"grant_id={self.grant_id}|"
            f"stage_scope={self.stage_scope}|"
            f"allowed_rel_path={self.allowed_rel_path}|"
            f"synthetic_fixture_root={self.synthetic_fixture_root}|"
            f"issued_at={self.issued_at_epoch_s}|"
            f"expires_at={self.expires_at_epoch_s}|"
            f"max_calls={self.max_attempted_fs_calls}|"
            f"max_trailer={self.max_trailer_read_bytes}|"
            f"max_footer={self.max_footer_read_bytes}|"
            f"max_total={self.max_total_read_bytes}|"
            f"allow_rows={int(self.allow_row_group_reads)}|"
            f"allow_owner={int(self.allow_real_owner_root)}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compute_expected_signature(self) -> str:
        """Alias for compute_expected_checksum (public SHA-256 checksum, NOT HMAC)."""
        return self.compute_expected_checksum()


def create_valid_synthetic_grant(
    synthetic_fixture_root: str,
    *,
    grant_id: str = "S3A-SYNTH-GRANT-001",
    allowed_rel_path: str = S3_SINGLE_PILOT_REL_PATH,
    issued_at_epoch_s: int = 1_700_000_000,
    expires_at_epoch_s: int = 1_900_000_000,
    max_attempted_fs_calls: int = MAX_ATTEMPTED_FS_CALLS,
    max_trailer_read_bytes: int = MAX_TRAILER_READ_BYTES,
    max_footer_read_bytes: int = MAX_FOOTER_READ_BYTES,
    max_total_read_bytes: int = MAX_TOTAL_FILE_READ_BYTES,
    attest_root_custody: bool = True,
) -> SyntheticTestGrant:
    """Create a test-only structural grant and optionally attest temp root custody."""
    custody_id = ""
    if attest_root_custody:
        custody = _walk_and_attest_temp_root(
            synthetic_fixture_root, max_calls=max_attempted_fs_calls,
            max_trailer=max_trailer_read_bytes, max_footer=max_footer_read_bytes,
            max_total=max_total_read_bytes,
        )
        if custody is not None:
            custody_id = custody.custody_id

    unsigned = SyntheticTestGrant(
        grant_id=grant_id,
        stage_scope="S3A_SYNTHETIC_FOOTER_ONLY",
        allowed_rel_path=allowed_rel_path,
        synthetic_fixture_root=synthetic_fixture_root,
        issued_at_epoch_s=issued_at_epoch_s,
        expires_at_epoch_s=expires_at_epoch_s,
        max_attempted_fs_calls=max_attempted_fs_calls,
        max_trailer_read_bytes=max_trailer_read_bytes,
        max_footer_read_bytes=max_footer_read_bytes,
        max_total_read_bytes=max_total_read_bytes,
        allow_row_group_reads=False,
        allow_real_owner_root=False,
        signature_hex="",
        token_semantics=SYNTHETIC_GRANT_TOKEN_SEMANTICS,
        is_external_authority_grant=False,
        trusted_custody_id=custody_id,
    )
    checksum = unsigned.compute_expected_checksum()
    return SyntheticTestGrant(
        grant_id=unsigned.grant_id,
        stage_scope=unsigned.stage_scope,
        allowed_rel_path=unsigned.allowed_rel_path,
        synthetic_fixture_root=unsigned.synthetic_fixture_root,
        issued_at_epoch_s=unsigned.issued_at_epoch_s,
        expires_at_epoch_s=unsigned.expires_at_epoch_s,
        max_attempted_fs_calls=unsigned.max_attempted_fs_calls,
        max_trailer_read_bytes=unsigned.max_trailer_read_bytes,
        max_footer_read_bytes=unsigned.max_footer_read_bytes,
        max_total_read_bytes=unsigned.max_total_read_bytes,
        allow_row_group_reads=unsigned.allow_row_group_reads,
        allow_real_owner_root=unsigned.allow_real_owner_root,
        signature_hex=checksum,
        token_semantics=SYNTHETIC_GRANT_TOKEN_SEMANTICS,
        is_external_authority_grant=False,
        trusted_custody_id=custody_id,
    )


@dataclass(frozen=True)
class ColumnSchemaSummary:
    """Sanitized per-column Parquet schema descriptor without value statistics."""

    column_index: int
    name: str
    path_in_schema: str
    physical_type: str
    logical_type: str
    converted_type: str
    max_definition_level: int
    max_repetition_level: int
    compression_codecs: tuple[str, ...]
    encodings: tuple[str, ...]
    had_embedded_statistics: bool
    statistics_suppressed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_index": self.column_index,
            "name": self.name,
            "path_in_schema": self.path_in_schema,
            "physical_type": self.physical_type,
            "logical_type": self.logical_type,
            "converted_type": self.converted_type,
            "max_definition_level": self.max_definition_level,
            "max_repetition_level": self.max_repetition_level,
            "compression_codecs": list(self.compression_codecs),
            "encodings": list(self.encodings),
            "had_embedded_statistics": self.had_embedded_statistics,
            "statistics_suppressed": self.statistics_suppressed,
        }


@dataclass(frozen=True)
class SanitizedParquetFooterMetadata:
    """Sanitized Parquet footer summary with statistics and KV metadata stripped."""

    format_version: str
    created_by: str | None
    num_columns: int
    num_row_groups: int
    declared_num_rows: int
    footer_length_bytes: int
    trailer_length_bytes: int
    header_verification_status: str
    embedded_statistics_detected: bool
    embedded_statistics_suppressed: bool
    key_value_metadata_detected: bool
    key_value_metadata_suppressed: bool
    row_data_pages_read: int
    columns: tuple[ColumnSchemaSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "created_by": self.created_by,
            "num_columns": self.num_columns,
            "num_row_groups": self.num_row_groups,
            "declared_num_rows": self.declared_num_rows,
            "footer_length_bytes": self.footer_length_bytes,
            "trailer_length_bytes": self.trailer_length_bytes,
            "header_verification_status": self.header_verification_status,
            "embedded_statistics_detected": self.embedded_statistics_detected,
            "embedded_statistics_suppressed": self.embedded_statistics_suppressed,
            "key_value_metadata_detected": self.key_value_metadata_detected,
            "key_value_metadata_suppressed": self.key_value_metadata_suppressed,
            "row_data_pages_read": self.row_data_pages_read,
            "columns": [col.to_dict() for col in self.columns],
        }


@dataclass(frozen=True)
class SyscallAccountingSnapshot:
    """Immutable snapshot of POSIX FS syscall and byte counters."""

    max_attempted_fs_calls: int = MAX_ATTEMPTED_FS_CALLS
    attempted_fs_calls_total: int = 0
    openat_attempted: int = 0
    openat_succeeded: int = 0
    openat_failed: int = 0
    fstat_attempted: int = 0
    fstat_succeeded: int = 0
    fstat_failed: int = 0
    pread_attempted: int = 0
    pread_succeeded: int = 0
    pread_failed: int = 0
    close_attempted: int = 0
    close_succeeded: int = 0
    close_failed: int = 0
    open_fds_remaining: int = 0
    requested_read_bytes_total: int = 0
    actual_read_bytes_total: int = 0
    trailer_bytes_read: int = 0
    footer_bytes_read: int = 0
    short_read_events: int = 0
    owner_root_touched: bool = False
    preparation_attempted_fs_calls: int = 0
    reader_attempted_fs_calls: int = 0
    preparation_family_counts: tuple[tuple[str, int], ...] = ()
    unconfirmed_fds: tuple[tuple[int, str], ...] = ()
    close_complete: bool = True
    simulated_pre_close_failures: int = 0
    simulated_pre_open_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempted_fs_calls": self.max_attempted_fs_calls,
            "attempted_fs_calls_total": self.attempted_fs_calls_total,
            "openat_attempted": self.openat_attempted,
            "openat_succeeded": self.openat_succeeded,
            "openat_failed": self.openat_failed,
            "fstat_attempted": self.fstat_attempted,
            "fstat_succeeded": self.fstat_succeeded,
            "fstat_failed": self.fstat_failed,
            "pread_attempted": self.pread_attempted,
            "pread_succeeded": self.pread_succeeded,
            "pread_failed": self.pread_failed,
            "close_attempted": self.close_attempted,
            "close_succeeded": self.close_succeeded,
            "close_failed": self.close_failed,
            "open_fds_remaining": self.open_fds_remaining,
            "requested_read_bytes_total": self.requested_read_bytes_total,
            "actual_read_bytes_total": self.actual_read_bytes_total,
            "trailer_bytes_read": self.trailer_bytes_read,
            "footer_bytes_read": self.footer_bytes_read,
            "short_read_events": self.short_read_events,
            "owner_root_touched": self.owner_root_touched,
            "accounting_scope": "SINGLE_USE_PREPARATION_PLUS_READER_AND_CLEANUP",
            "preparation_attempted_fs_calls": self.preparation_attempted_fs_calls,
            "reader_attempted_fs_calls": self.reader_attempted_fs_calls,
            "preparation_family_counts": dict(self.preparation_family_counts),
            "unconfirmed_fds": [{"fd": fd, "label": label, "status": "CLOSE_UNCONFIRMED"}
                                for fd, label in self.unconfirmed_fds],
            "close_complete": self.close_complete,
            "simulated_pre_close_failures": self.simulated_pre_close_failures,
            "simulated_pre_open_failures": self.simulated_pre_open_failures,
        }


@dataclass(frozen=True)
class FooterReadExecutionReceipt:
    """Structured execution receipt emitted by SingleFileParquetFooterReader."""

    allowed: bool
    decision_code: str
    error_type: str | None
    error_message: str | None
    rel_path: str
    file_size_bytes: int | None
    header_verification_status: str
    syscall_accounting: SyscallAccountingSnapshot
    schema_metadata: SanitizedParquetFooterMetadata | None
    grant_token_semantics: str = SYNTHETIC_GRANT_TOKEN_SEMANTICS

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision_code": self.decision_code,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "rel_path": self.rel_path,
            "file_size_bytes": self.file_size_bytes,
            "header_verification_status": (
                self.header_verification_status or HEADER_STATUS_NOT_VERIFIED
            ),
            "grant_token_semantics": self.grant_token_semantics,
            "syscall_accounting": self.syscall_accounting.to_dict(),
            "schema_metadata": (
                self.schema_metadata.to_dict()
                if self.schema_metadata is not None
                else None
            ),
        }


__all__ = [
    "ColumnSchemaSummary",
    "FooterReadExecutionReceipt",
    "SanitizedParquetFooterMetadata",
    "SyntheticTestGrant",
    "SyscallAccountingSnapshot",
    "TrustedTempRootCustody",
    "create_valid_synthetic_grant",
    "get_registered_trusted_custody",
    "is_forbidden_surrogate_inode",
    "is_forbidden_surrogate_path",
    "register_forbidden_owner_surrogate_tree",
]
