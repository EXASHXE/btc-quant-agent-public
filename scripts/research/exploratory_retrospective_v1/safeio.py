"""Descriptor-relative POSIX access; fail closed on unsupported platforms.

Independent of existing cross_venue authorization and path policy.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from . import GateError, require

PROTECTED = frozenset({
    "git", "aws", "agents", "codex", "ssh", "credential", "credentials", "secret",
    "secrets", "env", "netrc", "password", "passwd", "token", "tokens", "api", "key",
    "keys", "private",
    "protected", "archive", "archives", "historical", "history", "histories",
    "forward", "final", "oos", "holdout", "h39", "h40", "h41", "outcome", "outcomes",
    "label", "labels", "panel", "panels", "returns", "production", "prod", "accounts",
    "finalholdout", "aline",
})


def safe_path(value: str) -> Path:
    require(isinstance(value, str) and bool(value), "PATH_REQUIRED")
    # Check raw spelling before Path normalizes it. No Windows/UNC aliases on POSIX.
    require("\\" not in value and "\x00" not in value, "UNSAFE_PATH")
    require(all(p not in {"..", ".", ""} for p in value.split("/")[1:]), "TRAVERSAL")
    path = Path(value)
    require(path.is_absolute() and not value.startswith("//"), "ABSOLUTE_PATH_REQUIRED")
    for part in path.parts[1:]:
        tokens = set(re.split(r"[^a-z0-9]+", part.casefold()))
        require(not tokens.intersection(PROTECTED)
                and not {"a", "line"}.issubset(tokens), "PROTECTED_PATH")
    return path


@contextmanager
def directory_fd(path: Path) -> Iterator[int]:
    safe_path(str(path))
    require(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "PLATFORM_UNSUPPORTED")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as exc:
                raise GateError("UNSAFE_DIRECTORY") from exc
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def fingerprint(path: Path, expected_size: int, expected_hash: str,
                accepted_signature: list[int]) -> tuple[int, ...]:
    """Reject unsafe type/link metadata before reading, then hash one descriptor."""
    safe_path(str(path))
    with directory_fd(path.parent) as parent:
        try:
            before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "UNSAFE_FILE")
            require(before.st_size == expected_size, "SIZE_MISMATCH")
            require(signature(before) == tuple(accepted_signature), "SOURCE_MUTATED_AFTER_ACCEPTANCE")
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                require(signature(before) == signature(os.fstat(stream.fileno())), "SOURCE_MUTATED")
                payload = stream.read(expected_size + 1)
                require(hashlib.sha256(payload).hexdigest() == expected_hash, "FILE_HASH_MISMATCH")
                after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                require(signature(before) == signature(os.fstat(stream.fileno())) == signature(after)
                        and after.st_nlink == 1, "SOURCE_MUTATED")
                return signature(after)
        except OSError as exc:
            raise GateError("UNSAFE_FILE") from exc


def absent_output(path: Path) -> None:
    safe_path(str(path))
    with directory_fd(path.parent) as parent:
        try:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise GateError("OUTPUT_EXISTS")


def publish_new(path: Path, payload: bytes) -> None:
    """Exclusive creation under checked ancestors; never overwrite or follow links."""
    safe_path(str(path))
    with directory_fd(path.parent) as parent:
        try:
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
        except OSError as exc:
            raise GateError("OUTPUT_EXISTS_OR_UNSAFE") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
