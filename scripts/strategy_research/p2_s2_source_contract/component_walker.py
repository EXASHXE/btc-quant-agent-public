"""Descriptor-based component path walker.

Models safe POSIX dirfd component-by-component traversal (O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
to defend against symlinks, TOCTOU races, parent traversal, and mount boundary escapes.
"""

import os

from scripts.strategy_research.p2_s2_source_contract.constants import MAX_COMPONENT_DEPTH
from scripts.strategy_research.p2_s2_source_contract.errors import (
    MountBoundaryViolationError,
    NotADirectoryError,
    PathTraversalError,
    SymlinkEncounteredError,
)
from scripts.strategy_research.p2_s2_source_contract.syscall_interface import (
    AbstractSyscallInterface,
    FileStatResult,
)


class ComponentSafeDescriptorWalker:
    """Safe descriptor-style path resolver and validator."""

    def __init__(self, syscall_hook: AbstractSyscallInterface) -> None:
        self.hook = syscall_hook

    def _split_and_validate_relative_path(self, rel_path: str) -> list[str]:
        # Reject null bytes, backslashes, and leading slashes
        if "\0" in rel_path:
            raise PathTraversalError("Null byte detected in path string.")
        if "\\" in rel_path:
            raise PathTraversalError("Backslash path separator not permitted; use canonical forward slash.")
        if rel_path.startswith("/"):
            raise PathTraversalError("Absolute path not permitted as relative target.")

        raw_parts = rel_path.split("/")
        parts: list[str] = []
        for part in raw_parts:
            if not part or part == ".":
                continue
            if part == "..":
                raise PathTraversalError(f"Parent directory traversal '..' forbidden in path: {rel_path}")
            parts.append(part)

        if not parts:
            raise PathTraversalError("Empty or degenerate relative path.")
        if len(parts) > MAX_COMPONENT_DEPTH:
            raise PathTraversalError(f"Path depth {len(parts)} exceeds maximum permitted depth {MAX_COMPONENT_DEPTH}")

        return parts

    def walk_and_verify(
        self,
        root_dir: str,
        rel_path: str,
        verify_open_toctou: bool = False,
    ) -> tuple[FileStatResult, str]:
        """Walk path component-by-component from root_dir down to rel_path.

        Returns (leaf_stat, canonical_path).
        Raises SymlinkEncounteredError, NotADirectoryError, MountBoundaryViolationError,
        EACCESAccessDeniedError, ENOENTNotFoundError, or PathTraversalError.
        """
        parts = self._split_and_validate_relative_path(rel_path)

        # 1. Stat root directory
        norm_root = "/" + "/".join([p for p in root_dir.replace("\\", "/").split("/") if p])
        root_stat = self.hook.lstat(norm_root)
        if root_stat.is_symlink():
            raise SymlinkEncounteredError(f"Root path itself is a symlink: {root_dir}")
        if not root_stat.is_dir():
            raise NotADirectoryError(f"Root path is not a directory: {root_dir}")

        root_dev = root_stat.st_dev
        current_path = norm_root

        # 2. Walk intermediate components
        for part in parts[:-1]:
            current_path = f"{current_path}/{part}"
            comp_stat = self.hook.lstat(current_path)

            if comp_stat.is_symlink():
                raise SymlinkEncounteredError(f"Symlink detected at intermediate component: {current_path}")
            if not comp_stat.is_dir():
                raise NotADirectoryError(f"Ancestor component is not a directory: {current_path}")
            if comp_stat.st_dev != root_dev:
                raise MountBoundaryViolationError(
                    f"Mount/device boundary crossed at {current_path} (dev={comp_stat.st_dev} != root_dev={root_dev})"
                )

        # 3. Stat final leaf component
        leaf_name = parts[-1]
        leaf_path = f"{current_path}/{leaf_name}"
        leaf_stat = self.hook.lstat(leaf_path)

        if leaf_stat.is_symlink():
            raise SymlinkEncounteredError(f"Symlink detected at leaf target: {leaf_path}")
        if leaf_stat.st_dev != root_dev:
            raise MountBoundaryViolationError(
                f"Mount/device boundary crossed at leaf {leaf_path} (dev={leaf_stat.st_dev} != root_dev={root_dev})"
            )

        # 4. Optional TOCTOU verification via simulated descriptor open
        if verify_open_toctou and leaf_stat.is_file():
            fd = self.hook.open(leaf_path, os.O_RDONLY)
            try:
                fd_stat = self.hook.fstat(fd)
                if fd_stat.st_ino != leaf_stat.st_ino or fd_stat.st_dev != leaf_stat.st_dev:
                    raise SymlinkEncounteredError(
                        f"TOCTOU race detected: file descriptor inode/dev mismatch for {leaf_path}"
                    )
                if fd_stat.is_symlink():
                    raise SymlinkEncounteredError(
                        f"TOCTOU race detected: target was replaced with symlink upon open: {leaf_path}"
                    )
            finally:
                self.hook.close(fd)

        return leaf_stat, leaf_path
