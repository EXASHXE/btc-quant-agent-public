"""Pinned append-before-attempt witness, separate from mutable service state."""

import fcntl
import hashlib
import json
import os
import re
import stat
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class Denied(RuntimeError):
    """Fail-closed local capability refusal."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class FilePin:
    path: Path
    device: int
    inode: int
    uid: int

    @classmethod
    def capture_fixture(cls, path):
        info = path.lstat()
        return cls(path, info.st_dev, info.st_ino, info.st_uid)

    def matches(self, info):
        return (
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and (info.st_dev, info.st_ino, info.st_uid) == (self.device, self.inode, self.uid)
        )

    def verify_private(self):
        try:
            info = self.path.lstat()
            parent = self.path.parent.stat()
            if (
                self.path.resolve(strict=True) != self.path
                or not self.matches(info)
                or info.st_mode & 0o077
                or parent.st_uid != self.uid
                or parent.st_mode & 0o077
            ):
                raise Denied("STATE_IDENTITY_MISMATCH")
        except OSError as exc:
            raise Denied("STATE_UNAVAILABLE") from exc


@dataclass(frozen=True)
class Witness:
    pin: FilePin
    header_sha256: str
    fixture_only: bool = False

    def require_separation(self, paths):
        parent = self.pin.path.parent
        for path in paths:
            if (
                path == self.pin.path
                or path.parent == parent
                or parent.is_relative_to(path.parent)
                or path.parent.is_relative_to(parent)
            ):
                raise Denied("INDEPENDENT_WITNESS_PATH_REQUIRED")

    def _check_ownership_and_append(self, fd, info):
        if info.st_mode & 0o007:
            raise Denied("WITNESS_MODE_UNSAFE")
        if self.fixture_only:
            if info.st_uid != os.geteuid():
                raise Denied("FIXTURE_WITNESS_UID")
            return
        parent = self.pin.path.parent.stat()
        if info.st_uid != 0 or parent.st_uid != 0 or parent.st_mode & 0o022 or os.geteuid() == 0:
            raise Denied("INDEPENDENT_WITNESS_PRINCIPAL_REQUIRED")
        # Linux FS_IOC_GETFLAGS, sized for the native ABI's long.
        size = struct.calcsize("@l")
        request = (2 << 30) | (size << 16) | (ord("f") << 8) | 1
        flags = struct.unpack_from("@i", fcntl.ioctl(fd, request, bytes(size)))[0]
        if not flags & 0x20:
            raise Denied("WITNESS_NOT_KERNEL_APPEND_ONLY")

    @contextmanager
    def _open(self, *, write=False):
        fd = None
        try:
            if self.pin.path.resolve(strict=True) != self.pin.path:
                raise Denied("WITNESS_PATH_MISMATCH")
            flags = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            flags |= (os.O_RDWR | os.O_APPEND) if write else os.O_RDONLY
            fd = os.open(self.pin.path, flags)
            info = os.fstat(fd)
            if not self.pin.matches(info):
                raise Denied("WITNESS_IDENTITY_MISMATCH")
            self._check_ownership_and_append(fd, info)
            fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            if not self.pin.matches(self.pin.path.lstat()):
                raise Denied("WITNESS_IDENTITY_MISMATCH")
            with open(fd, "rb", closefd=False) as stream:
                body = stream.read(8193)
            header, sep, rest = body.partition(b"\n")
            if (
                not sep
                or len(body) > 8192
                or not header.startswith(b"H4_WITNESS_V1 ")
                or hashlib.sha256(header + b"\n").hexdigest() != self.header_sha256
                or (rest and not rest.endswith(b"\n"))
            ):
                raise Denied("WITNESS_CONTENT_INVALID")
            records = {}
            for line in rest.splitlines():
                row = json.loads(line)
                if (
                    type(row) is not list
                    or len(row) != 2
                    or type(row[0]) is not str
                    or row[0] in records
                    or type(row[1]) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", row[1])
                    or canonical(row) != line
                ):
                    raise Denied("WITNESS_RECORD_INVALID")
                records[row[0]] = row[1]
            yield fd, records
        except (OSError, ValueError) as exc:
            raise Denied("WITNESS_UNAVAILABLE_OR_BUSY") from exc
        finally:
            if fd is not None:
                os.close(fd)

    def check(self, slot, key=None):
        with self._open() as (_, records):
            if "revoked" in records:
                raise Denied("CAPABILITY_REVOKED")
            if key is None and slot in records:
                raise Denied("CAPABILITY_SPENT")
            if key is not None and records.get(slot) != key:
                raise Denied("CONSUMPTION_WITNESS_MISSING")

    def spend(self, slot, key, *, idempotent=False):
        if not re.fullmatch(r"[a-z0-9_]{1,32}", slot) or not re.fullmatch(r"[0-9a-f]{64}", key):
            raise Denied("WITNESS_BINDING_INVALID")
        with self._open(write=True) as (fd, records):
            if slot in records:
                if idempotent and records[slot] == key:
                    return
                raise Denied("CAPABILITY_SPENT")
            if slot != "revoked" and "revoked" in records:
                raise Denied("CAPABILITY_REVOKED")
            row = canonical([slot, key]) + b"\n"
            if os.write(fd, row) != len(row):
                raise Denied("WITNESS_WRITE_INCOMPLETE")
            os.fsync(fd)
