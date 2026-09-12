"""Same-directory durable publication; store generations remain the caller's authority."""

from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

_owners = threading.local()
_UNSET = object()


class PublicationConflict(RuntimeError):
    pass


class PublicationUncertain(OSError):
    """Replace completed, but directory durability was not confirmed. Never retry blindly."""


def file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


@contextmanager
def publication_lock(path: Path) -> Iterator[None]:
    # pathlib.resolve probes the final target with Path.stat on Python <3.13.
    # Normalize aliases without adding a target read before the write boundary.
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    held = getattr(_owners, "held", None)
    if held is None:
        held = _owners.held = set()
    if path in held:
        yield
        return
    descriptor = os.open(path.with_name(f".{path.name}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        held.add(path)
        try:
            yield
        finally:
            held.remove(path)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_bytes(
    path: str | Path, encoded: bytes, *, expected_sha256: str | None | object = _UNSET,
    before_replace: Callable[[Path], None] | None = None,
) -> Path:
    target = Path(os.path.realpath(path))
    with publication_lock(target):
        if expected_sha256 is not _UNSET and file_digest(target) != expected_sha256:
            raise PublicationConflict("stale publication content; target preserved")
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        temporary = Path(name)
        replaced = False
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if before_replace is not None:
                before_replace(temporary)
            os.replace(temporary, target)
            replaced = True
            fsync_directory(target.parent)
        except BaseException as exc:
            try:
                temporary.unlink(missing_ok=True)
            finally:
                if replaced:
                    raise PublicationUncertain("target replaced; parent durability unconfirmed") from exc
            raise
    return Path(path)
