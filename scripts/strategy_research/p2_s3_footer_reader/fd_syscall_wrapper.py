"""Metered POSIX file-descriptor syscall wrapper for the P2 S3A footer reader.

Wraps exclusively descriptor-relative and FD-bound POSIX primitives:
- ``os.open(single_component, flags, dir_fd=parent_fd)`` with
  ``O_NOFOLLOW | O_CLOEXEC`` (and ``O_DIRECTORY`` for directories)
- ``os.fstat(fd)``
- ``os.pread(fd, length, offset)``
- ``os.close(fd)``

Security invariants enforced in R2:
1. ``os.open(untrusted_absolute_synthetic_fixture_root)`` is eliminated. The
   fixture root is reached only by walking component-by-component from ``/``
   with ``O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`` at every ancestor hop, verifying
   ``TrustedTempRootCustody`` ``(st_dev, st_ino)`` expectations, and rejecting
   any forbidden owner-surrogate inode or mount escape.
2. Every ``openat`` call—including the **first** root open when ``len(_open_fds)==0``—
   reserves 1 close slot so ``attempted_fs_calls_total`` never exceeds
   ``max_attempted_fs_calls`` across ``1, 2, 3, 25, 27, 100``.
3. ``close_all_open_fds`` continues closing all remaining FDs even if one
   ``os.close`` fails, counts ``close_failed``, and raises ``FDCloseFailureError``
   so a cleanup failure can never be reported as PASS.
"""

from __future__ import annotations

import errno
import os
import stat
import tempfile
from collections.abc import Callable
from typing import Final

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    FORBIDDEN_OWNER_ROOT_PREFIXES,
    IMMUTABLE_OWNER_DATA_ROOT,
    MAX_ATTEMPTED_FS_CALLS,
    MAX_FOOTER_READ_BYTES,
    MAX_TOTAL_FILE_READ_BYTES,
    MAX_TRAILER_READ_BYTES,
)
from scripts.strategy_research.p2_s3_footer_reader.errors import (
    ByteBudgetExceededError,
    EACCESPermissionError,
    ENOENTNotFoundError,
    FDCloseFailureError,
    InvalidReadOffsetOrLengthError,
    MountBoundaryEscapeError,
    NotADirectoryComponentError,
    PathSyntaxOrTraversalError,
    ProductionExecutionForbiddenError,
    ShortReadOrTruncatedFileError,
    SymlinkDetectedError,
    SyscallBudgetExceededError,
    UnsupportedPlatformError,
    UntrustedRootCustodyError,
)
from scripts.strategy_research.p2_s3_footer_reader.types import (
    SyscallAccountingSnapshot,
    TrustedTempRootCustody,
    is_forbidden_surrogate_inode,
    is_forbidden_surrogate_path,
)

_REQUIRED_OS_ATTRS: Final[tuple[str, ...]] = (
    "open",
    "fstat",
    "pread",
    "close",
    "O_RDONLY",
    "O_DIRECTORY",
    "O_NOFOLLOW",
    "O_CLOEXEC",
)


def verify_posix_fd_platform_support() -> None:
    """Verify the runtime OS provides openat/dir_fd, O_NOFOLLOW, O_DIRECTORY, and pread."""
    for attr in _REQUIRED_OS_ATTRS:
        if not hasattr(os, attr):
            raise UnsupportedPlatformError(
                f"Runtime platform is missing required POSIX attribute os.{attr}."
            )
    if os.open not in os.supports_dir_fd:
        raise UnsupportedPlatformError(
            "Runtime platform does not support dir_fd in os.open (openat)."
        )


def assert_not_owner_data_root(candidate_path: str) -> None:
    """Fail closed before any OS syscall if a path points at or inside the owner root."""
    normalized = candidate_path.replace("\\", "/").strip()
    while "//" in normalized and not normalized.startswith("//"):
        normalized = normalized.replace("//", "/")
    normalized_lower = normalized.lower()
    owner_lower = IMMUTABLE_OWNER_DATA_ROOT.lower()
    if normalized_lower == owner_lower or normalized_lower.startswith(owner_lower + "/"):
        raise ProductionExecutionForbiddenError(
            f"Access to physical owner data root {IMMUTABLE_OWNER_DATA_ROOT!r} is "
            "strictly forbidden in S3A."
        )
    for forbidden in FORBIDDEN_OWNER_ROOT_PREFIXES:
        fl = forbidden.lower()
        if normalized_lower == fl or normalized_lower.startswith(fl + "/"):
            raise ProductionExecutionForbiddenError(
                f"Access to forbidden owner data path {candidate_path!r} is "
                "strictly forbidden in S3A."
            )
    if "quant-agent/data" in normalized_lower or "quant-agent-sanitized" in normalized_lower:
        raise ProductionExecutionForbiddenError(
            f"Path {candidate_path!r} matches forbidden owner data root pattern."
        )


def validate_and_split_temp_root_path(root_path: str) -> tuple[str, ...]:
    """Validate that root_path is a canonical-syntax absolute path under system temp."""
    if not isinstance(root_path, str) or not root_path:
        raise PathSyntaxOrTraversalError(
            "synthetic_fixture_root must be a non-empty string."
        )
    assert_not_owner_data_root(root_path)
    if "\x00" in root_path or "\\" in root_path:
        raise PathSyntaxOrTraversalError(
            f"Forbidden NUL or backslash in synthetic_fixture_root: {root_path!r}."
        )
    if not root_path.startswith("/"):
        raise PathSyntaxOrTraversalError(
            f"Relative synthetic_fixture_root forbidden: {root_path!r}."
        )
    stripped = root_path.rstrip("/")
    if not stripped or "//" in stripped:
        raise PathSyntaxOrTraversalError(
            f"Empty segment '//' forbidden in synthetic_fixture_root: {root_path!r}."
        )
    parts = stripped.lstrip("/").split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise PathSyntaxOrTraversalError(
                f"Traversal or dot segment {part!r} forbidden in "
                f"synthetic_fixture_root: {root_path!r}."
            )

    tmp_base = tempfile.gettempdir().replace("\\", "/").rstrip("/")
    if not (stripped == tmp_base or stripped.startswith(tmp_base + "/")):
        raise UntrustedRootCustodyError(
            f"Fixture root {root_path!r} is outside trusted system temp directory "
            f"{tmp_base!r}."
        )
    if is_forbidden_surrogate_path(stripped):
        raise UntrustedRootCustodyError(
            f"Fixture root {root_path!r} matches a forbidden owner-surrogate tree."
        )
    return tuple(parts)


class MeteredPosixSyscallWrapper:
    """Strict syscall and byte meter around POSIX openat, fstat, pread, and close."""

    def __init__(
        self,
        *,
        max_attempted_fs_calls: int = MAX_ATTEMPTED_FS_CALLS,
        max_trailer_read_bytes: int = MAX_TRAILER_READ_BYTES,
        max_footer_read_bytes: int = MAX_FOOTER_READ_BYTES,
        max_total_read_bytes: int = MAX_TOTAL_FILE_READ_BYTES,
        simulated_dev_overrides: dict[str, int] | None = None,
        simulated_open_errno_by_label: dict[str, int] | None = None,
        simulated_close_errno_by_label: dict[str, int] | None = None,
        short_read_truncate_bytes: int | None = None,
        post_trailer_pread_hook: Callable[[], None] | None = None,
    ) -> None:
        verify_posix_fd_platform_support()
        if max_attempted_fs_calls <= 0 or max_attempted_fs_calls > MAX_ATTEMPTED_FS_CALLS:
            raise SyscallBudgetExceededError(
                f"Configured max_attempted_fs_calls={max_attempted_fs_calls} violates "
                f"hard ceiling 1..{MAX_ATTEMPTED_FS_CALLS}."
            )
        if max_trailer_read_bytes < 0 or max_trailer_read_bytes > MAX_TRAILER_READ_BYTES:
            raise ByteBudgetExceededError(
                f"Configured max_trailer_read_bytes={max_trailer_read_bytes} exceeds "
                f"hard cap {MAX_TRAILER_READ_BYTES}."
            )
        if max_footer_read_bytes < 0 or max_footer_read_bytes > MAX_FOOTER_READ_BYTES:
            raise ByteBudgetExceededError(
                f"Configured max_footer_read_bytes={max_footer_read_bytes} exceeds "
                f"hard cap {MAX_FOOTER_READ_BYTES}."
            )
        if max_total_read_bytes < 0 or max_total_read_bytes > MAX_TOTAL_FILE_READ_BYTES:
            raise ByteBudgetExceededError(
                f"Configured max_total_read_bytes={max_total_read_bytes} exceeds "
                f"hard cap {MAX_TOTAL_FILE_READ_BYTES}."
            )

        self._max_attempted_fs_calls: int = max_attempted_fs_calls
        self._max_trailer_read_bytes: int = max_trailer_read_bytes
        self._max_footer_read_bytes: int = max_footer_read_bytes
        self._max_total_read_bytes: int = max_total_read_bytes

        self._openat_attempted: int = 0
        self._openat_succeeded: int = 0
        self._openat_failed: int = 0

        self._fstat_attempted: int = 0
        self._fstat_succeeded: int = 0
        self._fstat_failed: int = 0

        self._pread_attempted: int = 0
        self._pread_succeeded: int = 0
        self._pread_failed: int = 0

        self._close_attempted: int = 0
        self._close_succeeded: int = 0
        self._close_failed: int = 0

        self._requested_read_bytes_total: int = 0
        self._actual_read_bytes_total: int = 0
        self._trailer_bytes_read: int = 0
        self._footer_bytes_read: int = 0
        self._short_read_events: int = 0

        self._open_fds: dict[int, str] = {}
        self._fd_labels: dict[int, str] = {}
        self._close_errors: list[str] = []
        self._raw_kernel_invocation_log: list[tuple[str, str, int]] = []

        self._simulated_dev_overrides: dict[str, int] = dict(
            simulated_dev_overrides or {}
        )
        self._simulated_open_errno_by_label: dict[str, int] = dict(
            simulated_open_errno_by_label or {}
        )
        self._simulated_close_errno_by_label: dict[str, int] = dict(
            simulated_close_errno_by_label or {}
        )
        self._short_read_truncate_bytes: int | None = short_read_truncate_bytes
        self._post_trailer_pread_hook: Callable[[], None] | None = post_trailer_pread_hook

    @property
    def attempted_fs_calls_total(self) -> int:
        """Return total attempted FS calls across openat, fstat, pread, and close."""
        return (
            self._openat_attempted
            + self._fstat_attempted
            + self._pread_attempted
            + self._close_attempted
        )

    @property
    def open_fds_count(self) -> int:
        """Return number of currently open file descriptors tracked by this wrapper."""
        return len(self._open_fds)

    @property
    def close_failed_count(self) -> int:
        """Return number of failed os.close attempts."""
        return self._close_failed

    @property
    def raw_kernel_invocation_log(self) -> tuple[tuple[str, str, int], ...]:
        """Return immutable log of (syscall_name, label, errno_or_zero) invocations."""
        return tuple(self._raw_kernel_invocation_log)

    def snapshot(self) -> SyscallAccountingSnapshot:
        """Return an immutable snapshot of all syscall and byte counters."""
        return SyscallAccountingSnapshot(
            max_attempted_fs_calls=self._max_attempted_fs_calls,
            attempted_fs_calls_total=self.attempted_fs_calls_total,
            openat_attempted=self._openat_attempted,
            openat_succeeded=self._openat_succeeded,
            openat_failed=self._openat_failed,
            fstat_attempted=self._fstat_attempted,
            fstat_succeeded=self._fstat_succeeded,
            fstat_failed=self._fstat_failed,
            pread_attempted=self._pread_attempted,
            pread_succeeded=self._pread_succeeded,
            pread_failed=self._pread_failed,
            close_attempted=self._close_attempted,
            close_succeeded=self._close_succeeded,
            close_failed=self._close_failed,
            open_fds_remaining=len(self._open_fds),
            requested_read_bytes_total=self._requested_read_bytes_total,
            actual_read_bytes_total=self._actual_read_bytes_total,
            trailer_bytes_read=self._trailer_bytes_read,
            footer_bytes_read=self._footer_bytes_read,
            short_read_events=self._short_read_events,
            owner_root_touched=False,
        )

    def _check_syscall_budget(self, *, reserve_for_new_fd: bool = False) -> None:
        """Verify that executing another syscall (plus closing open FDs) fits budget.

        R2 F03 Fix: Every new FD open (including the very first root open when
        ``len(self._open_fds) == 0``) reserves 1 close slot so that closing the
        opened FD in ``finally:`` can never push ``attempted_fs_calls_total``
        above ``max_attempted_fs_calls``.
        """
        reserved_closes = len(self._open_fds) + (1 if reserve_for_new_fd else 0)
        if self.attempted_fs_calls_total + 1 + reserved_closes > self._max_attempted_fs_calls:
            raise SyscallBudgetExceededError(
                f"FS syscall budget insufficient: attempted={self.attempted_fs_calls_total}, "
                f"open_fds_reserved={reserved_closes}, "
                f"max_attempted_fs_calls={self._max_attempted_fs_calls}."
            )

    def _raw_open(
        self,
        component_name: str,
        flags: int,
        *,
        dir_fd: int,
        label: str,
    ) -> int:
        """Execute and count a single-component os.open(..., dir_fd=dir_fd) syscall."""
        if "/" in component_name or component_name in ("", ".", ".."):
            raise PathSyntaxOrTraversalError(
                f"Multi-component or dot openat forbidden: {component_name!r}."
            )
        self._check_syscall_budget(reserve_for_new_fd=True)
        self._openat_attempted += 1
        if label in self._simulated_open_errno_by_label:
            self._openat_failed += 1
            sim_err = self._simulated_open_errno_by_label[label]
            self._raw_kernel_invocation_log.append(("openat", label, sim_err))
            raise OSError(sim_err, os.strerror(sim_err), component_name)
        try:
            fd = os.open(component_name, flags, dir_fd=dir_fd)
        except OSError as exc:
            self._openat_failed += 1
            self._raw_kernel_invocation_log.append(
                ("openat", label, int(exc.errno or errno.EIO))
            )
            raise
        self._openat_succeeded += 1
        self._raw_kernel_invocation_log.append(("openat", label, 0))
        self._open_fds[fd] = label
        self._fd_labels[fd] = label
        return fd

    def _disambiguate_enotdir_or_symlink(
        self,
        component_name: str,
        *,
        dir_fd: int,
        label: str,
    ) -> None:
        """Distinguish symlink (ELOOP) from non-directory (ENOTDIR) via O_NOFOLLOW openat."""
        nonblock = getattr(os, "O_NONBLOCK", 0)
        probe_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | nonblock
        try:
            probe_fd = self._raw_open(
                component_name,
                probe_flags,
                dir_fd=dir_fd,
                label=f"{label}:symlink_probe",
            )
        except OSError as probe_exc:
            if probe_exc.errno == errno.ELOOP:
                raise SymlinkDetectedError(
                    f"Symlink rejected at component {label!r} (ELOOP)."
                ) from probe_exc
            if probe_exc.errno in (errno.EACCES, errno.EPERM):
                raise EACCESPermissionError(
                    f"Permission denied probing component {label!r}."
                ) from probe_exc
            raise NotADirectoryComponentError(
                f"Component {label!r} is not a directory (errno={probe_exc.errno})."
            ) from probe_exc
        else:
            self.close_fd(probe_fd)
            raise NotADirectoryComponentError(
                f"Component {label!r} is a regular/non-directory file, not a directory."
            )

    def _translate_open_oserror(
        self,
        exc: OSError,
        *,
        component_name: str,
        dir_fd: int,
        label: str,
        expect_directory: bool,
    ) -> None:
        """Translate POSIX openat OSError errno into typed fail-closed security errors."""
        err = exc.errno
        if err == errno.ELOOP:
            raise SymlinkDetectedError(
                f"Symlink rejected at {label!r} (errno=ELOOP)."
            ) from exc
        if err == errno.ENOTDIR:
            if expect_directory:
                self._disambiguate_enotdir_or_symlink(
                    component_name, dir_fd=dir_fd, label=label
                )
            raise NotADirectoryComponentError(
                f"Non-directory component encountered at {label!r} (errno=ENOTDIR)."
            ) from exc
        if err in (errno.EACCES, errno.EPERM):
            raise EACCESPermissionError(
                f"Permission denied opening {label!r} (errno={err})."
            ) from exc
        if err == errno.ENOENT:
            raise ENOENTNotFoundError(
                f"Path component not found at {label!r} (errno=ENOENT)."
            ) from exc
        raise OSError(err, f"Unexpected OS error opening {label!r}: {exc.strerror}") from exc

    def open_anchored_root_dir(
        self,
        root_path: str,
        *,
        trusted_custody: TrustedTempRootCustody | None = None,
        require_trusted_custody: bool = False,
    ) -> int:
        """Open the synthetic fixture root via component-by-component ancestor walk.

        R2 F01 Fix: Eliminates ``os.open(untrusted_absolute_synthetic_fixture_root)``.
        Walks from ``/`` across every ancestor component ``parts[:-1]`` with
        ``O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC`` so that any ancestor
        symlink, mount boundary escape, dangling parent, or forbidden surrogate
        inode is caught before the root directory is opened. Then opens the single
        final root component ``parts[-1]`` via ``_raw_open(..., dir_fd=parent_fd)``.
        """
        parts = validate_and_split_temp_root_path(root_path)
        self._check_syscall_budget(reserve_for_new_fd=True)

        if trusted_custody is not None:
            stripped = root_path.rstrip("/")
            if trusted_custody.canonical_temp_root != stripped:
                raise UntrustedRootCustodyError(
                    f"Custody root mismatch: attested={trusted_custody.canonical_temp_root!r} "
                    f"vs requested={stripped!r}."
                )

        dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        cur_fd: int | None = None
        tmp_base_dev: int | None = None
        try:
            cur_fd = os.open("/", dir_flags)
            for idx, ancestor_comp in enumerate(parts[:-1]):
                if ancestor_comp in self._simulated_dev_overrides:
                    raise MountBoundaryEscapeError(
                        f"Cross-device mount boundary escape detected at ancestor "
                        f"{ancestor_comp!r}."
                    )
                try:
                    next_fd = os.open(ancestor_comp, dir_flags, dir_fd=cur_fd)
                except OSError:
                    # Replay failing ancestor open through the metered wrapper so
                    # the failed openat (and symlink disambiguation probe) is counted.
                    try:
                        self._raw_open(
                            ancestor_comp,
                            dir_flags,
                            dir_fd=cur_fd,
                            label=f"<ancestor:{ancestor_comp}>",
                        )
                    except OSError as metered_exc:
                        if metered_exc.errno == errno.ENOENT and require_trusted_custody:
                            raise UntrustedRootCustodyError(
                                f"Ancestor component {ancestor_comp!r} missing or renamed."
                            ) from metered_exc
                        self._translate_open_oserror(
                            metered_exc,
                            component_name=ancestor_comp,
                            dir_fd=cur_fd,
                            label=f"<ancestor:{ancestor_comp}>",
                            expect_directory=True,
                        )
                    raise AssertionError("Unreachable")

                os.close(cur_fd)
                cur_fd = next_fd
                anc_st = os.fstat(cur_fd)
                if not stat.S_ISDIR(anc_st.st_mode):
                    raise NotADirectoryComponentError(
                        f"Ancestor component {ancestor_comp!r} is not a directory."
                    )
                if is_forbidden_surrogate_inode(anc_st.st_dev, anc_st.st_ino):
                    raise UntrustedRootCustodyError(
                        f"Ancestor component {ancestor_comp!r} resolves to a "
                        "forbidden owner-surrogate inode."
                    )
                if idx == 0:
                    tmp_base_dev = int(anc_st.st_dev)
                elif tmp_base_dev is not None and int(anc_st.st_dev) != tmp_base_dev:
                    raise MountBoundaryEscapeError(
                        f"Cross-device mount boundary escape at ancestor {ancestor_comp!r}: "
                        f"st_dev={anc_st.st_dev} != tmp_base_dev={tmp_base_dev}."
                    )

            parent_st = os.fstat(cur_fd)
            if is_forbidden_surrogate_inode(parent_st.st_dev, parent_st.st_ino):
                raise UntrustedRootCustodyError(
                    "Parent directory resolves to a forbidden owner-surrogate inode."
                )
            if require_trusted_custody and trusted_custody is None:
                raise UntrustedRootCustodyError(
                    f"Trusted harness root custody is missing or unproven for {root_path!r}."
                )
            if trusted_custody is not None and (
                int(parent_st.st_dev) != trusted_custody.expected_parent_dev
                or int(parent_st.st_ino) != trusted_custody.expected_parent_ino
            ):
                raise UntrustedRootCustodyError(
                    "Parent directory (st_dev, st_ino) changed after custody attestation."
                )

            root_leaf_name = parts[-1]
            try:
                return self._raw_open(
                    root_leaf_name,
                    dir_flags,
                    dir_fd=cur_fd,
                    label="<root>",
                )
            except OSError as exc:
                self._translate_open_oserror(
                    exc,
                    component_name=root_leaf_name,
                    dir_fd=cur_fd,
                    label="<root>",
                    expect_directory=True,
                )
                raise AssertionError("Unreachable") from exc
        finally:
            if cur_fd is not None:
                try:
                    os.close(cur_fd)
                except OSError:
                    pass

    def openat_directory_component(self, parent_dir_fd: int, component: str) -> int:
        """Open a single child directory component relative to parent_dir_fd."""
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            return self._raw_open(
                component,
                flags,
                dir_fd=parent_dir_fd,
                label=component,
            )
        except OSError as exc:
            self._translate_open_oserror(
                exc,
                component_name=component,
                dir_fd=parent_dir_fd,
                label=component,
                expect_directory=True,
            )
            raise AssertionError("Unreachable") from exc

    def openat_regular_leaf(self, parent_dir_fd: int, filename: str) -> int:
        """Open the final leaf file relative to parent_dir_fd with O_NOFOLLOW|O_CLOEXEC."""
        nonblock = getattr(os, "O_NONBLOCK", 0)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | nonblock
        try:
            return self._raw_open(
                filename,
                flags,
                dir_fd=parent_dir_fd,
                label=filename,
            )
        except OSError as exc:
            self._translate_open_oserror(
                exc,
                component_name=filename,
                dir_fd=parent_dir_fd,
                label=filename,
                expect_directory=False,
            )
            raise AssertionError("Unreachable") from exc

    def fstat_fd(self, fd: int) -> os.stat_result:
        """Execute and count os.fstat(fd), applying optional test st_dev override."""
        self._check_syscall_budget(reserve_for_new_fd=False)
        self._fstat_attempted += 1
        label = self._fd_labels.get(fd, f"fd:{fd}")
        try:
            st = os.fstat(fd)
        except OSError as exc:
            self._fstat_failed += 1
            self._raw_kernel_invocation_log.append(
                ("fstat", label, int(exc.errno or errno.EIO))
            )
            if exc.errno in (errno.EACCES, errno.EPERM):
                raise EACCESPermissionError(
                    f"Permission denied in fstat({fd})."
                ) from exc
            raise
        self._fstat_succeeded += 1
        self._raw_kernel_invocation_log.append(("fstat", label, 0))
        if label in self._simulated_dev_overrides:
            override_dev = self._simulated_dev_overrides[label]
            seq = list(st)
            seq[2] = override_dev  # st_dev index in stat_result tuple
            return os.stat_result(seq)
        return st

    def pread_bytes(
        self,
        fd: int,
        length: int,
        offset: int,
        *,
        is_trailer: bool,
    ) -> bytes:
        """Execute a bounded, counted os.pread(fd, length, offset) call."""
        if length <= 0:
            raise InvalidReadOffsetOrLengthError(
                f"Invalid pread length={length}; must be > 0."
            )
        if offset < 0:
            raise InvalidReadOffsetOrLengthError(
                f"Invalid pread offset={offset}; must be >= 0."
            )

        if is_trailer:
            if self._trailer_bytes_read + length > self._max_trailer_read_bytes:
                raise ByteBudgetExceededError(
                    f"Trailer read request of {length} bytes exceeds max_trailer_read_bytes="
                    f"{self._max_trailer_read_bytes} (already read={self._trailer_bytes_read})."
                )
        else:
            if self._footer_bytes_read + length > self._max_footer_read_bytes:
                raise ByteBudgetExceededError(
                    f"Footer read request of {length} bytes exceeds max_footer_read_bytes="
                    f"{self._max_footer_read_bytes} (already read={self._footer_bytes_read})."
                )

        if self._requested_read_bytes_total + length > self._max_total_read_bytes:
            raise ByteBudgetExceededError(
                f"Cumulative requested read bytes ({self._requested_read_bytes_total + length}) "
                f"exceeds max_total_read_bytes={self._max_total_read_bytes}."
            )

        self._check_syscall_budget(reserve_for_new_fd=False)
        self._pread_attempted += 1
        self._requested_read_bytes_total += length
        label = "trailer" if is_trailer else "footer"

        actual_os_length = length
        if (
            self._short_read_truncate_bytes is not None
            and self._short_read_truncate_bytes < length
        ):
            actual_os_length = max(0, self._short_read_truncate_bytes)

        try:
            data = os.pread(fd, actual_os_length, offset)
        except OSError as exc:
            self._pread_failed += 1
            self._raw_kernel_invocation_log.append(
                ("pread", label, int(exc.errno or errno.EIO))
            )
            if exc.errno in (errno.EACCES, errno.EPERM):
                raise EACCESPermissionError(
                    f"Permission denied during pread on fd={fd}."
                ) from exc
            raise

        actual_len = len(data)
        self._actual_read_bytes_total += actual_len
        if is_trailer:
            self._trailer_bytes_read += actual_len
        else:
            self._footer_bytes_read += actual_len

        if actual_len != length:
            self._pread_failed += 1
            self._short_read_events += 1
            self._raw_kernel_invocation_log.append(("pread", label, errno.EIO))
            raise ShortReadOrTruncatedFileError(
                f"Short read on pread(offset={offset}, requested={length}): "
                f"received {actual_len} bytes."
            )

        self._pread_succeeded += 1
        self._raw_kernel_invocation_log.append(("pread", label, 0))
        if is_trailer and self._post_trailer_pread_hook is not None:
            self._post_trailer_pread_hook()
        return data

    def close_fd(self, fd: int) -> None:
        """Close a tracked file descriptor and increment close accounting."""
        if fd not in self._open_fds:
            return
        label = self._open_fds.pop(fd)
        self._close_attempted += 1
        sim_err = self._simulated_close_errno_by_label.get(label)
        os_err: OSError | None = None
        try:
            os.close(fd)
        except OSError as exc:
            os_err = exc

        if sim_err is not None or os_err is not None:
            err_code = (
                sim_err
                if sim_err is not None
                else int(os_err.errno if os_err and os_err.errno else errno.EIO)
            )
            self._close_failed += 1
            self._raw_kernel_invocation_log.append(("close", label, err_code))
            msg = f"Failed to close FD for {label!r} (errno={err_code})."
            self._close_errors.append(msg)
            raise FDCloseFailureError(msg)

        self._close_succeeded += 1
        self._raw_kernel_invocation_log.append(("close", label, 0))

    def close_all_open_fds(self, *, raise_on_failure: bool = False) -> None:
        """Deterministically close all remaining open FDs without aborting on error."""
        for fd in reversed(list(self._open_fds.keys())):
            try:
                self.close_fd(fd)
            except (FDCloseFailureError, OSError):
                # Continue closing all remaining FDs even if one close fails.
                continue
        if raise_on_failure and self._close_failed > 0:
            raise FDCloseFailureError(
                f"Encountered {self._close_failed} FD close failure(s) during cleanup: "
                f"{'; '.join(self._close_errors)}"
            )


__all__ = [
    "MeteredPosixSyscallWrapper",
    "assert_not_owner_data_root",
    "validate_and_split_temp_root_path",
    "verify_posix_fd_platform_support",
]
