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
import stat
import tempfile
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
    _prune_stale_surrogates()
    key = (int(dev), int(ino))
    return any(key in inodes for inodes in _FORBIDDEN_SURROGATE_TREES.values())


def is_forbidden_surrogate_path(candidate_path: str) -> bool:
    """Return True if candidate_path lexically matches or is inside a forbidden surrogate."""
    _prune_stale_surrogates()
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


def _walk_and_attest_temp_root(temp_root_path: str) -> TrustedTempRootCustody | None:
    """Walk from '/' with O_DIRECTORY|O_NOFOLLOW to attest a temp fixture root."""
    if not isinstance(temp_root_path, str) or not temp_root_path.startswith("/"):
        return None
    if "\\" in temp_root_path or "\x00" in temp_root_path:
        return None
    stripped = temp_root_path.rstrip("/")
    if not stripped:
        return None
    parts = stripped.lstrip("/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None

    tmp_base = tempfile.gettempdir().replace("\\", "/").rstrip("/")
    if not (stripped == tmp_base or stripped.startswith(tmp_base + "/")):
        return None
    if is_forbidden_surrogate_path(stripped):
        return None

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    cur_fd: int | None = None
    try:
        cur_fd = os.open("/", flags)
        for comp in parts[:-1]:
            next_fd = os.open(comp, flags, dir_fd=cur_fd)
            os.close(cur_fd)
            cur_fd = next_fd
            st = os.fstat(cur_fd)
            if not stat.S_ISDIR(st.st_mode):
                return None
            if is_forbidden_surrogate_inode(st.st_dev, st.st_ino):
                return None

        parent_st = os.fstat(cur_fd)
        parent_dev = int(parent_st.st_dev)
        parent_ino = int(parent_st.st_ino)

        root_dev: int | None = None
        root_ino: int | None = None
        try:
            leaf_fd = os.open(parts[-1], flags, dir_fd=cur_fd)
        except OSError:
            # Final root directory may be a symlink or missing in negative tests;
            # parent custody is still recorded so the metered reader can test the leaf root.
            pass
        else:
            try:
                leaf_st = os.fstat(leaf_fd)
                if stat.S_ISDIR(leaf_st.st_mode) and int(leaf_st.st_dev) == parent_dev:
                    if is_forbidden_surrogate_inode(leaf_st.st_dev, leaf_st.st_ino):
                        return None
                    root_dev = int(leaf_st.st_dev)
                    root_ino = int(leaf_st.st_ino)
            finally:
                os.close(leaf_fd)
    except OSError:
        return None
    finally:
        if cur_fd is not None:
            try:
                os.close(cur_fd)
            except OSError:
                pass

    custody_id = f"S3A-CUSTODY-{secrets.token_hex(12)}"
    custody = TrustedTempRootCustody(
        custody_id=custody_id,
        canonical_temp_root=stripped,
        expected_parent_dev=parent_dev,
        expected_parent_ino=parent_ino,
        expected_root_dev=root_dev,
        expected_root_ino=root_ino,
        attested_uid=os.geteuid() if hasattr(os, "geteuid") else 0,
    )
    _TRUSTED_CUSTODY_REGISTRY[custody_id] = custody
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
        custody = _walk_and_attest_temp_root(synthetic_fixture_root)
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

    max_attempted_fs_calls: int
    attempted_fs_calls_total: int
    openat_attempted: int
    openat_succeeded: int
    openat_failed: int
    fstat_attempted: int
    fstat_succeeded: int
    fstat_failed: int
    pread_attempted: int
    pread_succeeded: int
    pread_failed: int
    close_attempted: int
    close_succeeded: int
    close_failed: int
    open_fds_remaining: int
    requested_read_bytes_total: int
    actual_read_bytes_total: int
    trailer_bytes_read: int
    footer_bytes_read: int
    short_read_events: int
    owner_root_touched: bool = False

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
