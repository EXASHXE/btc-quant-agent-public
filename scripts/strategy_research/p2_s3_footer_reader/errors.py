"""Typed exception hierarchy for the P2 S3A single-file Parquet footer reader.

Every exception carries a deterministic ``decision_code`` used in structured
execution receipts and security oracle verification.
"""

from __future__ import annotations


class S3FooterReaderError(Exception):
    """Base exception for all fail-closed violations in the S3A footer reader."""

    default_decision_code: str = "DENIED_UNSPECIFIED_SECURITY_ERROR"

    def __init__(self, message: str, *, decision_code: str | None = None) -> None:
        super().__init__(message)
        self.message: str = message
        self.decision_code: str = decision_code or self.default_decision_code


class ProductionExecutionForbiddenError(S3FooterReaderError):
    """Raised when attempting to target the real owner data root or run in production."""

    default_decision_code = "DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN"


class CliOrEnvRootOverrideForbiddenError(S3FooterReaderError):
    """Raised when CLI arguments or environment variables attempt to override root/mode."""

    default_decision_code = "DENIED_CLI_OR_ENV_ROOT_OVERRIDE"


class GrantAuthorizationError(S3FooterReaderError):
    """Raised when the synthetic test grant is missing, unsigned, or invalid."""

    default_decision_code = "DENIED_INVALID_OR_MISSING_GRANT"


class GrantExpiredError(GrantAuthorizationError):
    """Raised when the synthetic test grant timestamp has expired."""

    default_decision_code = "DENIED_EXPIRED_GRANT"


class GrantScopeEscalationError(GrantAuthorizationError):
    """Raised when a grant attempts to escalate beyond single-file footer QA."""

    default_decision_code = "DENIED_GRANT_SCOPE_ESCALATION"


class PathSyntaxOrTraversalError(S3FooterReaderError):
    """Raised on absolute paths, '..', '.', empty segments, backslashes, or NUL bytes."""

    default_decision_code = "DENIED_PATH_SYNTAX_OR_TRAVERSAL"


class ProtectedPathDeniedError(S3FooterReaderError):
    """Raised when a path references 2026 protected windows, forward, H39, or heldout."""

    default_decision_code = "DENIED_PROTECTED_PATH_DOMAIN"


class UnapprovedTargetFileError(S3FooterReaderError):
    """Raised when the relative path is not the single S3 pilot file (2021-03)."""

    default_decision_code = "DENIED_UNAPPROVED_TARGET_FILE"


class SymlinkDetectedError(S3FooterReaderError):
    """Raised when the root, any intermediate directory, or the leaf file is a symlink."""

    default_decision_code = "DENIED_SYMLINK_DETECTED"


class NotADirectoryComponentError(S3FooterReaderError):
    """Raised when the root or an intermediate path component is not a directory."""

    default_decision_code = "DENIED_NOT_A_DIRECTORY_COMPONENT"


class NonRegularFileError(S3FooterReaderError):
    """Raised when the opened leaf file descriptor is a directory, FIFO, socket, or device."""

    default_decision_code = "DENIED_NON_REGULAR_FILE"


class MountBoundaryEscapeError(S3FooterReaderError):
    """Raised when st_dev changes across components relative to the anchored root FD."""

    default_decision_code = "DENIED_MOUNT_BOUNDARY_ESCAPE"


class HardlinkOrAliasError(S3FooterReaderError):
    """Raised when leaf st_nlink > 1 or inode aliasing is detected."""

    default_decision_code = "DENIED_HARDLINK_OR_INODE_ALIAS"


class TOCTOUOrFDIdentityError(S3FooterReaderError):
    """Raised when (st_dev, st_ino, st_size, st_mtime_ns) changes across open/pread/re-check."""

    default_decision_code = "DENIED_TOCTOU_OR_FD_IDENTITY_MISMATCH"


class EACCESPermissionError(S3FooterReaderError):
    """Raised when POSIX openat/fstat/pread fails with EACCES or EPERM (distinct from ENOENT)."""

    default_decision_code = "DENIED_EACCES_PERMISSION"


class ENOENTNotFoundError(S3FooterReaderError):
    """Raised when POSIX openat fails with ENOENT (distinct from EACCES)."""

    default_decision_code = "DENIED_ENOENT_NOT_FOUND"


class SyscallBudgetExceededError(S3FooterReaderError):
    """Raised when attempted FS syscalls would exceed max_attempted_fs_calls."""

    default_decision_code = "DENIED_SYSCALL_BUDGET_EXCEEDED"


class ByteBudgetExceededError(S3FooterReaderError):
    """Raised when requested or cumulative read bytes exceed the trailer/footer/total cap."""

    default_decision_code = "DENIED_BYTE_BUDGET_EXCEEDED"


class ShortReadOrTruncatedFileError(S3FooterReaderError):
    """Raised when file size is below minimum Parquet size or pread returns a short read."""

    default_decision_code = "DENIED_SHORT_READ_OR_TRUNCATED_FILE"


class InvalidReadOffsetOrLengthError(S3FooterReaderError):
    """Raised when pread offset < 0 or length <= 0."""

    default_decision_code = "DENIED_INVALID_READ_OFFSET_OR_LENGTH"


class InvalidParquetFormatError(S3FooterReaderError):
    """Base exception for Parquet trailer/footer structural validation errors."""

    default_decision_code = "DENIED_INVALID_PARQUET_FORMAT"


class InvalidParquetMagicError(InvalidParquetFormatError):
    """Raised when the 4-byte trailer magic is not b'PAR1'."""

    default_decision_code = "DENIED_INVALID_PARQUET_TRAILER_MAGIC"


class InvalidParquetFooterLengthError(InvalidParquetFormatError):
    """Raised when the 4-byte little-endian footer length is <= 0 or > 65,536."""

    default_decision_code = "DENIED_INVALID_PARQUET_FOOTER_LENGTH"


class InvalidParquetFooterExtentError(InvalidParquetFormatError):
    """Raised when footer_len + 8 > file_size - 4 (overlapping 4-byte file header)."""

    default_decision_code = "DENIED_PARQUET_FOOTER_EXCEEDS_FILE_EXTENT"


class CorruptedParquetFooterError(InvalidParquetFormatError):
    """Raised when Thrift/Parquet footer bytes cannot be decoded by the metadata parser."""

    default_decision_code = "DENIED_CORRUPTED_PARQUET_THRIFT_FOOTER"


class ParserInputViolationError(S3FooterReaderError):
    """Raised when parse_parquet_footer_bytes is passed a path, FD, or file-like object."""

    default_decision_code = "DENIED_PARSER_DIRECT_PATH_OR_FD_FORBIDDEN"


class RowGroupDataReadForbiddenError(S3FooterReaderError):
    """Raised when any attempt is made to read data pages, row values, or full files."""

    default_decision_code = "DENIED_ROW_GROUP_DATA_READ_FORBIDDEN"


class UnsupportedPlatformError(S3FooterReaderError):
    """Raised when required POSIX openat/O_NOFOLLOW/O_DIRECTORY/pread primitives are absent."""

    default_decision_code = "DENIED_UNSUPPORTED_PLATFORM_OR_FLAGS"


__all__ = [
    "ByteBudgetExceededError",
    "CliOrEnvRootOverrideForbiddenError",
    "CorruptedParquetFooterError",
    "EACCESPermissionError",
    "ENOENTNotFoundError",
    "GrantAuthorizationError",
    "GrantExpiredError",
    "GrantScopeEscalationError",
    "HardlinkOrAliasError",
    "InvalidParquetFooterExtentError",
    "InvalidParquetFooterLengthError",
    "InvalidParquetFormatError",
    "InvalidParquetMagicError",
    "InvalidReadOffsetOrLengthError",
    "MountBoundaryEscapeError",
    "NonRegularFileError",
    "NotADirectoryComponentError",
    "ParserInputViolationError",
    "PathSyntaxOrTraversalError",
    "ProductionExecutionForbiddenError",
    "ProtectedPathDeniedError",
    "RowGroupDataReadForbiddenError",
    "S3FooterReaderError",
    "ShortReadOrTruncatedFileError",
    "SymlinkDetectedError",
    "SyscallBudgetExceededError",
    "TOCTOUOrFDIdentityError",
    "UnapprovedTargetFileError",
    "UnsupportedPlatformError",
]
