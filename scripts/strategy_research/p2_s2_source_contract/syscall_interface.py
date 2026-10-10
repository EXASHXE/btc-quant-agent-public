"""Deterministic fake syscall interface and accounting hook.

Provides an instrumented boundary between policy logic and OS operations.
Every single low-level operation is recorded in SyscallAccounting at the boundary;
no caching of unique paths is performed.
"""

import os
import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from scripts.strategy_research.p2_s2_source_contract.errors import (
    BudgetExceededError,
    EACCESAccessDeniedError,
    ENOENTNotFoundError,
    NotADirectoryError,
    ZeroBytePolicyViolationError,
)
from scripts.strategy_research.p2_s2_source_contract.types import SyscallAccounting


@dataclass
class FileStatResult:
    """Represents stat/lstat results."""
    st_mode: int
    st_size: int
    st_mtime: float = 1787667332.0
    st_dev: int = 1
    st_ino: int = 1000

    def is_symlink(self) -> bool:
        return stat.S_ISLNK(self.st_mode)

    def is_dir(self) -> bool:
        return stat.S_ISDIR(self.st_mode)

    def is_file(self) -> bool:
        return stat.S_ISREG(self.st_mode)


class AbstractSyscallInterface(ABC):
    """Abstract interface for low-level filesystem system calls."""

    @abstractmethod
    def lstat(self, path: str) -> FileStatResult:
        """Perform lstat (does not follow symlinks)."""

    @abstractmethod
    def open(self, path: str, flags: int, mode: int = 0) -> int:
        """Open file descriptor."""

    @abstractmethod
    def fstat(self, fd: int) -> FileStatResult:
        """Perform fstat on open file descriptor."""

    @abstractmethod
    def read(self, fd: int, n_bytes: int) -> bytes:
        """Read up to n_bytes from file descriptor."""

    @abstractmethod
    def close(self, fd: int) -> None:
        """Close file descriptor."""

    @abstractmethod
    def scandir(self, path: str) -> list[str]:
        """List directory entries."""


class InstrumentedSyscallHook(AbstractSyscallInterface):
    """Decorator hook that rigorously counts system calls and byte reads at the boundary."""

    def __init__(
        self,
        backend: AbstractSyscallInterface,
        max_syscalls: int = 50,
        max_bytes: int = 0,
    ) -> None:
        self.backend = backend
        self.max_syscalls = max_syscalls
        self.max_bytes = max_bytes
        self.accounting = SyscallAccounting()

    def _check_syscall_budget(self) -> None:
        if self.accounting.total_calls >= self.max_syscalls:
            raise BudgetExceededError(
                f"Syscall budget ceiling exceeded: total_calls={self.accounting.total_calls} >= max_syscalls={self.max_syscalls}"
            )

    def lstat(self, path: str) -> FileStatResult:
        self._check_syscall_budget()
        self.accounting.record_lstat()
        try:
            return self.backend.lstat(path)
        except PermissionError as exc:
            raise EACCESAccessDeniedError(f"Permission denied (EACCES) for lstat on: {path}") from exc
        except FileNotFoundError as exc:
            raise ENOENTNotFoundError(f"Path not found (ENOENT) for lstat on: {path}") from exc
        except NotADirectoryError as exc:
            raise NotADirectoryError(f"Not a directory (ENOTDIR) for lstat on: {path}") from exc

    def open(self, path: str, flags: int, mode: int = 0) -> int:
        self._check_syscall_budget()
        self.accounting.record_open()
        try:
            return self.backend.open(path, flags, mode)
        except PermissionError as exc:
            raise EACCESAccessDeniedError(f"Permission denied (EACCES) for open on: {path}") from exc
        except FileNotFoundError as exc:
            raise ENOENTNotFoundError(f"Path not found (ENOENT) for open on: {path}") from exc
        except NotADirectoryError as exc:
            raise NotADirectoryError(f"Not a directory (ENOTDIR) for open on: {path}") from exc

    def fstat(self, fd: int) -> FileStatResult:
        self._check_syscall_budget()
        self.accounting.record_fstat()
        try:
            return self.backend.fstat(fd)
        except OSError as exc:
            raise EACCESAccessDeniedError(f"fstat failed on fd={fd}: {exc}") from exc

    def read(self, fd: int, n_bytes: int) -> bytes:
        self._check_syscall_budget()
        if self.max_bytes == 0 and n_bytes > 0:
            self.accounting.record_read(0)
            raise ZeroBytePolicyViolationError(
                f"Zero-byte read policy strictly enforced (max_bytes=0). Requested read of {n_bytes} bytes denied."
            )
        if self.accounting.bytes_read + n_bytes > self.max_bytes:
            self.accounting.record_read(0)
            raise BudgetExceededError(
                f"Byte budget exceeded: attempted {self.accounting.bytes_read + n_bytes} > max_bytes={self.max_bytes}"
            )
        data = self.backend.read(fd, n_bytes)
        self.accounting.record_read(len(data))
        return data

    def close(self, fd: int) -> None:
        self._check_syscall_budget()
        self.accounting.record_close()
        self.backend.close(fd)

    def scandir(self, path: str) -> list[str]:
        self._check_syscall_budget()
        self.accounting.record_scandir()
        try:
            return self.backend.scandir(path)
        except PermissionError as exc:
            raise EACCESAccessDeniedError(f"Permission denied (EACCES) for scandir on: {path}") from exc
        except FileNotFoundError as exc:
            raise ENOENTNotFoundError(f"Path not found (ENOENT) for scandir on: {path}") from exc
        except NotADirectoryError as exc:
            raise NotADirectoryError(f"Not a directory (ENOTDIR) for scandir on: {path}") from exc


@dataclass
class SyntheticFsNode:
    """Node in the synthetic filesystem."""
    is_dir: bool = False
    is_symlink: bool = False
    symlink_target: str | None = None
    size: int = 0
    content: bytes = b""
    mode: int = 0o100644
    dev: int = 1
    ino: int = 1000
    permission_denied: bool = False


class InMemoryFakeFilesystem(AbstractSyscallInterface):
    """In-memory synthetic filesystem fixture for contract verification."""

    def __init__(self, root_dev: int = 1) -> None:
        self.nodes: dict[str, SyntheticFsNode] = {}
        self.open_fds: dict[int, str] = {}
        self.next_fd: int = 10
        self.next_ino: int = 2000
        self.root_dev = root_dev
        self.toctou_triggers: dict[str, Any] = {}

    def _norm(self, path: str) -> str:
        # Standardize path representation without traversing symlinks
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        return "/" + "/".join(parts)

    def add_directory(self, path: str, mode: int = 0o40755, dev: int | None = None) -> None:
        norm = self._norm(path)
        self.next_ino += 1
        self.nodes[norm] = SyntheticFsNode(
            is_dir=True,
            is_symlink=False,
            mode=mode,
            size=4096,
            dev=dev if dev is not None else self.root_dev,
            ino=self.next_ino,
        )

    def add_file(
        self,
        path: str,
        size: int = 0,
        content: bytes = b"",
        mode: int = 0o100644,
        dev: int | None = None,
    ) -> None:
        norm = self._norm(path)
        self.next_ino += 1
        effective_size = size if size > 0 else len(content)
        self.nodes[norm] = SyntheticFsNode(
            is_dir=False,
            is_symlink=False,
            size=effective_size,
            content=content,
            mode=mode,
            dev=dev if dev is not None else self.root_dev,
            ino=self.next_ino,
        )

    def add_symlink(self, path: str, target: str, dev: int | None = None) -> None:
        norm = self._norm(path)
        self.next_ino += 1
        mode = stat.S_IFLNK | 0o777
        self.nodes[norm] = SyntheticFsNode(
            is_dir=False,
            is_symlink=True,
            symlink_target=target,
            mode=mode,
            dev=dev if dev is not None else self.root_dev,
            ino=self.next_ino,
        )

    def set_permission_denied(self, path: str, denied: bool = True) -> None:
        norm = self._norm(path)
        if norm in self.nodes:
            self.nodes[norm].permission_denied = denied

    def register_toctou_mutation(self, path: str, new_node: SyntheticFsNode) -> None:
        """Register a node mutation that triggers immediately after an lstat call."""
        norm = self._norm(path)
        self.toctou_triggers[norm] = new_node

    def lstat(self, path: str) -> FileStatResult:
        norm = self._norm(path)
        if norm not in self.nodes:
            raise FileNotFoundError(f"File not found: {path}")
        node = self.nodes[norm]
        if node.permission_denied:
            raise PermissionError(f"Permission denied: {path}")

        res = FileStatResult(
            st_mode=node.mode,
            st_size=node.size,
            st_dev=node.dev,
            st_ino=node.ino,
        )
        # Check TOCTOU trigger
        if norm in self.toctou_triggers:
            self.nodes[norm] = self.toctou_triggers.pop(norm)
        return res

    def open(self, path: str, flags: int, mode: int = 0) -> int:
        norm = self._norm(path)
        if norm not in self.nodes:
            raise FileNotFoundError(f"File not found: {path}")
        node = self.nodes[norm]
        if node.permission_denied:
            raise PermissionError(f"Permission denied: {path}")
        if node.is_symlink:
            # If O_NOFOLLOW is modeled or symlink encountered
            raise PermissionError(f"Cannot open symlink directly with O_NOFOLLOW: {path}")
        if node.is_dir and not (flags & os.O_DIRECTORY):
            raise IsADirectoryError(f"Path is a directory: {path}")
        if not node.is_dir and (flags & os.O_DIRECTORY):
            raise NotADirectoryError(f"Path is not a directory: {path}")

        fd = self.next_fd
        self.next_fd += 1
        self.open_fds[fd] = norm
        return fd

    def fstat(self, fd: int) -> FileStatResult:
        if fd not in self.open_fds:
            raise OSError(f"Bad file descriptor: {fd}")
        norm = self.open_fds[fd]
        node = self.nodes[norm]
        return FileStatResult(
            st_mode=node.mode,
            st_size=node.size,
            st_dev=node.dev,
            st_ino=node.ino,
        )

    def read(self, fd: int, n_bytes: int) -> bytes:
        if fd not in self.open_fds:
            raise OSError(f"Bad file descriptor: {fd}")
        norm = self.open_fds[fd]
        node = self.nodes[norm]
        if node.content:
            return node.content[:n_bytes]
        return b"\x00" * min(node.size, n_bytes)

    def close(self, fd: int) -> None:
        if fd in self.open_fds:
            del self.open_fds[fd]

    def scandir(self, path: str) -> list[str]:
        norm = self._norm(path)
        if norm not in self.nodes:
            raise FileNotFoundError(f"Path not found: {path}")
        node = self.nodes[norm]
        if node.permission_denied:
            raise PermissionError(f"Permission denied: {path}")
        if not node.is_dir:
            raise NotADirectoryError(f"Not a directory: {path}")

        results: set[str] = set()
        prefix = norm.rstrip("/") + "/"
        for p in self.nodes:
            if p.startswith(prefix) and p != norm:
                rel = p[len(prefix):]
                top_child = rel.split("/")[0]
                results.add(top_child)
        return sorted(results)
