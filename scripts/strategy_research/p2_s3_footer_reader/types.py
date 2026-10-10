"""Data structures and sanitized metadata schemas for the P2 S3A footer reader.

All output structures enforce strict sanitization:
- Column min/max/null_count/distinct_count statistics are never included.
- Custom key_value_metadata payloads are suppressed.
- Every output marks ``header_verification_status = "FILE_HEADER_NOT_VERIFIED"``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    HEADER_STATUS_NOT_VERIFIED,
    MAX_ATTEMPTED_FS_CALLS,
    MAX_FOOTER_READ_BYTES,
    MAX_TOTAL_FILE_READ_BYTES,
    MAX_TRAILER_READ_BYTES,
    S3_SINGLE_PILOT_REL_PATH,
)

_SYNTHETIC_GRANT_HMAC_DOMAIN: str = "S3A_SYNTHETIC_TEST_HARNESS_GRANT_V1"


@dataclass(frozen=True)
class SyntheticTestGrant:
    """Explicit test-only capability grant for the S3A synthetic footer reader.

    A SyntheticTestGrant can NEVER authorize reading from the physical owner
    WSL data root (``/root/workspace/project/Quant-agent/data``) or reading
    row-group data pages.
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

    def compute_expected_signature(self) -> str:
        """Compute deterministic SHA-256 signature over canonical grant fields."""
        payload = (
            f"{_SYNTHETIC_GRANT_HMAC_DOMAIN}|"
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
) -> SyntheticTestGrant:
    """Create a properly signed test-only grant anchored to a temporary directory."""
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
    )
    sig = unsigned.compute_expected_signature()
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
        signature_hex=sig,
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
    "create_valid_synthetic_grant",
]
