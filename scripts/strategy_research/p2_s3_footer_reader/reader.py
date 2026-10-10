"""Independent POSIX dir_fd single-file Parquet footer reader for P2 S3A.

Enforces:
1. Zero production/owner-root execution: any reference to
   ``/root/workspace/project/Quant-agent/data`` or CLI/env overrides is rejected
   before any OS syscall.
2. Trusted temporary fixture root custody (R2 F01): ancestor components from ``/``
   are walked with ``O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`` and verified against
   harness-attested ``TrustedTempRootCustody`` ``(st_dev, st_ino)`` expectations
   and forbidden owner-surrogate inode sets; unattested roots fail closed with
   ``S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN``.
3. Honest synthetic token semantics (R2 F02): ``SyntheticTestGrant`` uses a
   public SHA-256 checksum labeled ``TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION``
   and cannot authorize unattested or production roots.
4. Exact single pilot relative path allowlist:
   ``research/BTCUSDT/1m/year=2021/month=03/data.parquet``.
5. Component-by-component ``os.open(..., dir_fd=parent_fd)`` walk with
   ``O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`` for intermediate directories and
   ``O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK`` for the leaf file.
6. Per-hop ``fstat`` verification of directory/regular-file mode, constant
   ``st_dev`` (no mount escape), and ``st_nlink == 1`` on the leaf file.
7. Bounded two-step ``os.pread`` of the 8-byte trailer and ``<= 65,536``-byte
   Thrift footer (``<= 65,544`` bytes total), followed by post-read ``fstat`` and
   parent-directory reopen ``(st_dev, st_ino, st_size, st_mtime_ns)`` TOCTOU
   identity verification.
8. Deterministic ``finally:`` closure of all opened directory and file FDs, with
   any ``os.close`` failure raising ``FDCloseFailureError``.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping, Sequence

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    FORBIDDEN_CLI_OVERRIDE_FLAGS,
    FORBIDDEN_ENV_OVERRIDE_VARS,
    HEADER_STATUS_NOT_VERIFIED,
    PARQUET_TRAILER_SIZE_BYTES,
    PROTECTED_PATH_TOKENS,
    S3_SINGLE_PILOT_COMPONENTS,
    S3_SINGLE_PILOT_REL_PATH,
    SYNTHETIC_GRANT_TOKEN_SEMANTICS,
)
from scripts.strategy_research.p2_s3_footer_reader.errors import (
    CliOrEnvRootOverrideForbiddenError,
    GrantAuthorizationError,
    GrantExpiredError,
    GrantScopeEscalationError,
    HardlinkOrAliasError,
    MountBoundaryEscapeError,
    NonRegularFileError,
    NotADirectoryComponentError,
    PathSyntaxOrTraversalError,
    ProductionExecutionForbiddenError,
    ProtectedPathDeniedError,
    RowGroupDataReadForbiddenError,
    S3FooterReaderError,
    ShortReadOrTruncatedFileError,
    TOCTOUOrFDIdentityError,
    UnapprovedTargetFileError,
    UntrustedRootCustodyError,
)
from scripts.strategy_research.p2_s3_footer_reader.fd_syscall_wrapper import (
    MeteredPosixSyscallWrapper,
    assert_not_owner_data_root,
    validate_and_split_temp_root_path,
)
from scripts.strategy_research.p2_s3_footer_reader.footer_parser import (
    parse_in_memory_parquet_footer,
    validate_parquet_trailer_and_extent,
)
from scripts.strategy_research.p2_s3_footer_reader.types import (
    FooterReadExecutionReceipt,
    SyntheticTestGrant,
    TrustedTempRootCustody,
    get_registered_trusted_custody,
    is_forbidden_surrogate_inode,
)


def validate_no_cli_or_env_overrides(
    cli_args: Sequence[str] | None = None,
    env_vars: Mapping[str, str] | None = None,
) -> None:
    """Reject any CLI flag or environment variable attempting to override root/mode."""
    if cli_args:
        for arg in cli_args:
            token = arg.strip()
            for flag in FORBIDDEN_CLI_OVERRIDE_FLAGS:
                if token == flag or token.startswith(flag + "="):
                    raise CliOrEnvRootOverrideForbiddenError(
                        f"Forbidden CLI override flag {token!r} rejected."
                    )

    merged_env: dict[str, str] = {}
    for k in FORBIDDEN_ENV_OVERRIDE_VARS:
        if k in os.environ:
            merged_env[k] = os.environ[k]
    if env_vars:
        for k, v in env_vars.items():
            merged_env[k] = v

    for env_key in FORBIDDEN_ENV_OVERRIDE_VARS:
        val = merged_env.get(env_key, "").strip()
        if val:
            raise CliOrEnvRootOverrideForbiddenError(
                f"Forbidden environment override variable {env_key!r}={val!r} rejected."
            )


def validate_synthetic_grant(
    grant: SyntheticTestGrant | None,
    *,
    synthetic_fixture_root: str,
    current_epoch_s: int,
) -> TrustedTempRootCustody | None:
    """Validate synthetic test grant structure, expiry, scope, and custody reference."""
    if grant is None or not isinstance(grant, SyntheticTestGrant):
        raise GrantAuthorizationError(
            "Missing or invalid SyntheticTestGrant; default policy is fail-closed DENY."
        )
    if grant.allow_real_owner_root:
        raise GrantScopeEscalationError(
            "Grant attempts to authorize real owner data root (forbidden in S3A)."
        )
    if grant.allow_row_group_reads:
        raise RowGroupDataReadForbiddenError(
            "Grant attempts to authorize row-group or page data reads (forbidden in S3)."
        )
    if grant.is_external_authority_grant:
        raise GrantScopeEscalationError(
            "SyntheticTestGrant falsely claims external authority (forbidden in S3A)."
        )
    if grant.token_semantics != SYNTHETIC_GRANT_TOKEN_SEMANTICS:
        raise GrantAuthorizationError(
            f"Invalid grant token_semantics={grant.token_semantics!r}; must be "
            f"{SYNTHETIC_GRANT_TOKEN_SEMANTICS!r}."
        )
    if grant.stage_scope != "S3A_SYNTHETIC_FOOTER_ONLY":
        raise GrantScopeEscalationError(
            f"Unsupported grant stage_scope={grant.stage_scope!r}; "
            "only 'S3A_SYNTHETIC_FOOTER_ONLY' is permitted."
        )
    if not grant.grant_id or not grant.signature_hex:
        raise GrantAuthorizationError(
            "Grant is missing grant_id or structural integrity checksum."
        )
    expected_checksum = grant.compute_expected_checksum()
    if grant.signature_hex != expected_checksum:
        raise GrantAuthorizationError(
            "Grant structural integrity checksum mismatch (tampered grant)."
        )
    if grant.expires_at_epoch_s <= grant.issued_at_epoch_s:
        raise GrantExpiredError(
            "Grant has invalid expiry window (expires_at <= issued_at)."
        )
    if current_epoch_s < grant.issued_at_epoch_s:
        raise GrantAuthorizationError(
            f"Grant not yet valid (current={current_epoch_s} < issued={grant.issued_at_epoch_s})."
        )
    if current_epoch_s >= grant.expires_at_epoch_s:
        raise GrantExpiredError(
            f"Grant has expired (current={current_epoch_s} >= expires={grant.expires_at_epoch_s})."
        )

    assert_not_owner_data_root(grant.synthetic_fixture_root)
    if grant.synthetic_fixture_root != synthetic_fixture_root:
        raise GrantAuthorizationError(
            f"Grant fixture root {grant.synthetic_fixture_root!r} does not match "
            f"requested synthetic_fixture_root {synthetic_fixture_root!r}."
        )
    if grant.allowed_rel_path != S3_SINGLE_PILOT_REL_PATH:
        raise UnapprovedTargetFileError(
            f"Grant allowed_rel_path {grant.allowed_rel_path!r} is not the single "
            f"S3 pilot path {S3_SINGLE_PILOT_REL_PATH!r}."
        )
    return get_registered_trusted_custody(grant.trusted_custody_id)


def validate_and_split_single_pilot_rel_path(rel_path: str) -> tuple[str, ...]:
    """Validate relative path syntax, protected domains, and single-file identity."""
    if not isinstance(rel_path, str) or not rel_path:
        raise PathSyntaxOrTraversalError("Relative path must be a non-empty string.")
    if "\x00" in rel_path:
        raise PathSyntaxOrTraversalError("NUL byte forbidden in relative path.")
    if "\\" in rel_path:
        raise PathSyntaxOrTraversalError(
            f"Backslash separator forbidden in relative path: {rel_path!r}."
        )
    if rel_path.startswith(("/", "~")):
        raise PathSyntaxOrTraversalError(
            f"Absolute or home-relative path forbidden: {rel_path!r}."
        )
    if rel_path.endswith("/"):
        raise PathSyntaxOrTraversalError(
            f"Trailing slash forbidden on file target path: {rel_path!r}."
        )

    raw_parts = rel_path.split("/")
    for part in raw_parts:
        if part in ("", ".", ".."):
            raise PathSyntaxOrTraversalError(
                f"Empty, '.' or '..' traversal segment forbidden in {rel_path!r}."
            )

    rel_lower = rel_path.lower()
    for token in PROTECTED_PATH_TOKENS:
        if token.lower() in rel_lower:
            raise ProtectedPathDeniedError(
                f"Target path {rel_path!r} touches protected/withheld domain {token!r}."
            )

    if rel_path != S3_SINGLE_PILOT_REL_PATH:
        raise UnapprovedTargetFileError(
            f"Target path {rel_path!r} is not admitted; S3 allows ONLY "
            f"{S3_SINGLE_PILOT_REL_PATH!r}."
        )

    parts_tuple = tuple(raw_parts)
    if parts_tuple != S3_SINGLE_PILOT_COMPONENTS:
        raise UnapprovedTargetFileError(
            f"Component sequence {parts_tuple!r} does not match "
            f"{S3_SINGLE_PILOT_COMPONENTS!r}."
        )
    return parts_tuple


def _fd_identity_tuple(st: os.stat_result) -> tuple[int, int, int, int]:
    """Return (st_dev, st_ino, st_size, st_mtime_ns) identity tuple from fstat."""
    return (int(st.st_dev), int(st.st_ino), int(st.st_size), int(st.st_mtime_ns))


class SingleFileParquetFooterReader:
    """Bounded POSIX dir_fd single-file Parquet footer reader for P2 S3A."""

    def __init__(
        self,
        *,
        synthetic_fixture_root: str,
        grant: SyntheticTestGrant | None,
        synthetic_test_mode: bool = True,
        production_mode: bool = False,
        current_epoch_s: int = 1_800_000_000,
        cli_args: Sequence[str] | None = None,
        env_vars: Mapping[str, str] | None = None,
        simulated_dev_overrides: dict[str, int] | None = None,
        simulated_open_errno_by_label: dict[str, int] | None = None,
        simulated_close_errno_by_label: dict[str, int] | None = None,
        short_read_truncate_bytes: int | None = None,
        post_trailer_pread_hook: Callable[[], None] | None = None,
        request_extra_row_page_read: bool = False,
    ) -> None:
        self._synthetic_fixture_root: str = synthetic_fixture_root
        self._grant: SyntheticTestGrant | None = grant
        self._synthetic_test_mode: bool = synthetic_test_mode
        self._production_mode: bool = production_mode
        self._current_epoch_s: int = current_epoch_s
        self._cli_args: Sequence[str] | None = cli_args
        self._env_vars: Mapping[str, str] | None = env_vars
        self._simulated_dev_overrides: dict[str, int] | None = simulated_dev_overrides
        self._simulated_open_errno_by_label: dict[str, int] | None = (
            simulated_open_errno_by_label
        )
        self._simulated_close_errno_by_label: dict[str, int] | None = (
            simulated_close_errno_by_label
        )
        self._short_read_truncate_bytes: int | None = short_read_truncate_bytes
        self._post_trailer_pread_hook: Callable[[], None] | None = (
            post_trailer_pread_hook
        )
        self._request_extra_row_page_read: bool = request_extra_row_page_read

    def read_single_parquet_footer(
        self,
        rel_path: str = S3_SINGLE_PILOT_REL_PATH,
    ) -> FooterReadExecutionReceipt:
        """Execute the guarded single-file footer read or raise S3FooterReaderError.

        On any ``S3FooterReaderError``, the structured ``FooterReadExecutionReceipt``
        (with complete syscall and FD closure accounting) is attached to
        ``exc.receipt`` before re-raising.
        """
        max_calls = (
            self._grant.max_attempted_fs_calls
            if isinstance(self._grant, SyntheticTestGrant)
            else 100
        )
        max_trailer = (
            self._grant.max_trailer_read_bytes
            if isinstance(self._grant, SyntheticTestGrant)
            else 8
        )
        max_footer = (
            self._grant.max_footer_read_bytes
            if isinstance(self._grant, SyntheticTestGrant)
            else 65_536
        )
        max_total = (
            self._grant.max_total_read_bytes
            if isinstance(self._grant, SyntheticTestGrant)
            else 65_544
        )

        wrapper: MeteredPosixSyscallWrapper | None = None
        observed_file_size: int | None = None

        try:
            wrapper = MeteredPosixSyscallWrapper(
                max_attempted_fs_calls=max_calls,
                max_trailer_read_bytes=max_trailer,
                max_footer_read_bytes=max_footer,
                max_total_read_bytes=max_total,
                simulated_dev_overrides=self._simulated_dev_overrides,
                simulated_open_errno_by_label=self._simulated_open_errno_by_label,
                simulated_close_errno_by_label=self._simulated_close_errno_by_label,
                short_read_truncate_bytes=self._short_read_truncate_bytes,
                post_trailer_pread_hook=self._post_trailer_pread_hook,
            )

            # 1. Reject CLI / environment overrides before any syscall.
            validate_no_cli_or_env_overrides(self._cli_args, self._env_vars)

            # 2. Reject production mode or missing synthetic_test_mode before any syscall.
            if self._production_mode or not self._synthetic_test_mode:
                raise ProductionExecutionForbiddenError(
                    "Production mode or disabled synthetic_test_mode is forbidden in S3A."
                )

            # 3. Validate fixture root path syntax, owner-root block, and temp prefix.
            validate_and_split_temp_root_path(self._synthetic_fixture_root)

            # 4. Reject any request to read row-group / data pages.
            if self._request_extra_row_page_read:
                raise RowGroupDataReadForbiddenError(
                    "Reading Parquet data pages or row values is forbidden in S3."
                )

            # 5. Validate relative target path before any syscall.
            components = validate_and_split_single_pilot_rel_path(rel_path)

            # 6. Validate synthetic test grant structure, expiry, scope, and custody.
            trusted_custody = validate_synthetic_grant(
                self._grant,
                synthetic_fixture_root=self._synthetic_fixture_root,
                current_epoch_s=self._current_epoch_s,
            )

            # 7. Open anchored root directory FD via component-by-component ancestor walk
            #    and verify harness root custody (R2 F01).
            root_fd = wrapper.open_anchored_root_dir(
                self._synthetic_fixture_root,
                trusted_custody=trusted_custody,
                require_trusted_custody=True,
            )
            root_st = wrapper.fstat_fd(root_fd)
            if not stat.S_ISDIR(root_st.st_mode):
                raise NotADirectoryComponentError(
                    "Anchored root FD is not a directory after fstat."
                )
            root_dev = int(root_st.st_dev)
            root_ino = int(root_st.st_ino)
            if is_forbidden_surrogate_inode(root_dev, root_ino):
                raise UntrustedRootCustodyError(
                    "Anchored root FD resolves to a forbidden owner-surrogate inode."
                )
            if trusted_custody is not None:
                if root_dev != trusted_custody.expected_parent_dev:
                    raise MountBoundaryEscapeError(
                        f"Root st_dev={root_dev} differs from attested parent "
                        f"st_dev={trusted_custody.expected_parent_dev}."
                    )
                if (
                    trusted_custody.expected_root_ino is not None
                    and (
                        root_dev != trusted_custody.expected_root_dev
                        or root_ino != trusted_custody.expected_root_ino
                    )
                ):
                    raise UntrustedRootCustodyError(
                        "Root directory (st_dev, st_ino) changed after harness "
                        "custody attestation."
                    )

            # 8. Walk intermediate directories component-by-component via openat(dir_fd).
            parent_fd = root_fd
            for comp in components[:-1]:
                next_dir_fd = wrapper.openat_directory_component(parent_fd, comp)
                dir_st = wrapper.fstat_fd(next_dir_fd)
                if not stat.S_ISDIR(dir_st.st_mode):
                    raise NotADirectoryComponentError(
                        f"Intermediate component {comp!r} is not a directory."
                    )
                if int(dir_st.st_dev) != root_dev:
                    raise MountBoundaryEscapeError(
                        f"Cross-device mount boundary escape detected at directory "
                        f"{comp!r}: st_dev={dir_st.st_dev} != root_dev={root_dev}."
                    )
                if is_forbidden_surrogate_inode(dir_st.st_dev, dir_st.st_ino):
                    raise UntrustedRootCustodyError(
                        f"Directory component {comp!r} aliases a forbidden "
                        "owner-surrogate inode."
                    )
                parent_fd = next_dir_fd

            # 9. Open final leaf file relative to month=03 directory FD with O_NOFOLLOW.
            leaf_name = components[-1]
            leaf_fd = wrapper.openat_regular_leaf(parent_fd, leaf_name)
            leaf_st_pre = wrapper.fstat_fd(leaf_fd)

            if not stat.S_ISREG(leaf_st_pre.st_mode):
                raise NonRegularFileError(
                    f"Target leaf {leaf_name!r} is not a regular file "
                    f"(st_mode={oct(leaf_st_pre.st_mode)})."
                )
            if int(leaf_st_pre.st_dev) != root_dev:
                raise MountBoundaryEscapeError(
                    f"Cross-device mount boundary escape detected at leaf "
                    f"{leaf_name!r}: st_dev={leaf_st_pre.st_dev} != root_dev={root_dev}."
                )
            if is_forbidden_surrogate_inode(leaf_st_pre.st_dev, leaf_st_pre.st_ino):
                raise UntrustedRootCustodyError(
                    f"Target leaf {leaf_name!r} aliases a forbidden "
                    "owner-surrogate inode."
                )
            if int(leaf_st_pre.st_nlink) > 1:
                raise HardlinkOrAliasError(
                    f"Target leaf {leaf_name!r} has st_nlink={leaf_st_pre.st_nlink} > 1 "
                    "(hardlink aliasing forbidden)."
                )

            observed_file_size = int(leaf_st_pre.st_size)
            if observed_file_size < 13:
                raise ShortReadOrTruncatedFileError(
                    f"Target leaf {leaf_name!r} size={observed_file_size} bytes is "
                    "smaller than minimum valid Parquet size (13 bytes)."
                )

            pre_identity = _fd_identity_tuple(leaf_st_pre)

            # 10. Read 8-byte Parquet trailer via os.pread(leaf_fd, 8, file_size - 8).
            trailer_offset = observed_file_size - PARQUET_TRAILER_SIZE_BYTES
            trailer_bytes = wrapper.pread_bytes(
                leaf_fd,
                PARQUET_TRAILER_SIZE_BYTES,
                trailer_offset,
                is_trailer=True,
            )

            # 11. Validate trailer magic ("PAR1"), footer_len (1..65536), and file extent.
            footer_len = validate_parquet_trailer_and_extent(
                trailer_bytes,
                file_size_bytes=observed_file_size,
                max_footer_bytes=max_footer,
            )

            # 12. Read Thrift FileMetaData footer via os.pread(leaf_fd, footer_len, offset).
            footer_offset = (
                observed_file_size - PARQUET_TRAILER_SIZE_BYTES - footer_len
            )
            footer_bytes = wrapper.pread_bytes(
                leaf_fd,
                footer_len,
                footer_offset,
                is_trailer=False,
            )

            # 13. Post-read TOCTOU verification on both open leaf FD and parent dir entry.
            leaf_st_post = wrapper.fstat_fd(leaf_fd)
            post_identity = _fd_identity_tuple(leaf_st_post)
            if post_identity != pre_identity:
                raise TOCTOUOrFDIdentityError(
                    f"Leaf FD identity changed during read: pre={pre_identity} vs "
                    f"post={post_identity}."
                )

            reopen_fd = wrapper.openat_regular_leaf(parent_fd, leaf_name)
            reopen_st = wrapper.fstat_fd(reopen_fd)
            wrapper.close_fd(reopen_fd)
            if not stat.S_ISREG(reopen_st.st_mode):
                raise TOCTOUOrFDIdentityError(
                    "Directory entry replaced with non-regular file during read."
                )
            reopen_identity = _fd_identity_tuple(reopen_st)
            if reopen_identity != pre_identity:
                raise TOCTOUOrFDIdentityError(
                    f"Directory entry {leaf_name!r} replaced during read (TOCTOU): "
                    f"initial={pre_identity} vs reopen={reopen_identity}."
                )

            # 14. Parse in-memory footer buffer ONLY and strip statistics/KV metadata.
            sanitized_meta = parse_in_memory_parquet_footer(
                footer_bytes,
                trailer_bytes,
                file_size_bytes=observed_file_size,
                max_footer_bytes=max_footer,
            )

            # 15. Close all remaining open FDs and fail closed if any close failed (R2 F03).
            wrapper.close_all_open_fds(raise_on_failure=True)

        except S3FooterReaderError as exc:
            if wrapper is not None:
                wrapper.close_all_open_fds(raise_on_failure=False)
                snap = wrapper.snapshot()
            else:
                fallback = MeteredPosixSyscallWrapper()
                snap = fallback.snapshot()
            err_receipt = FooterReadExecutionReceipt(
                allowed=False,
                decision_code=exc.decision_code,
                error_type=type(exc).__name__,
                error_message=exc.message,
                rel_path=str(rel_path),
                file_size_bytes=observed_file_size,
                header_verification_status=HEADER_STATUS_NOT_VERIFIED,
                syscall_accounting=snap,
                schema_metadata=None,
                grant_token_semantics=SYNTHETIC_GRANT_TOKEN_SEMANTICS,
            )
            exc.receipt = err_receipt  # type: ignore[attr-defined]
            raise
        finally:
            if wrapper is not None:
                wrapper.close_all_open_fds(raise_on_failure=False)

        final_snap = wrapper.snapshot()
        return FooterReadExecutionReceipt(
            allowed=True,
            decision_code="ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED",
            error_type=None,
            error_message=None,
            rel_path=rel_path,
            file_size_bytes=observed_file_size,
            header_verification_status=HEADER_STATUS_NOT_VERIFIED,
            syscall_accounting=final_snap,
            schema_metadata=sanitized_meta,
            grant_token_semantics=SYNTHETIC_GRANT_TOKEN_SEMANTICS,
        )

    def evaluate_to_receipt(
        self,
        rel_path: str = S3_SINGLE_PILOT_REL_PATH,
    ) -> FooterReadExecutionReceipt:
        """Run the reader and always return a FooterReadExecutionReceipt without raising."""
        try:
            return self.read_single_parquet_footer(rel_path=rel_path)
        except S3FooterReaderError as exc:
            receipt = getattr(exc, "receipt", None)
            if isinstance(receipt, FooterReadExecutionReceipt):
                return receipt
            raise


__all__ = [
    "SingleFileParquetFooterReader",
    "validate_and_split_single_pilot_rel_path",
    "validate_no_cli_or_env_overrides",
    "validate_synthetic_grant",
]
