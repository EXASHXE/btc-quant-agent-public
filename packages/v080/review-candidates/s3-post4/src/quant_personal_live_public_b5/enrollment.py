"""File-identity-pinned enrollment/canary registry fence for a single approved release."""

from __future__ import annotations

import fcntl
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import encode, sha

from .contract import bounded_int, sha_text

ANCHOR_PREFIX = b"H2A_ENROLLMENT_V1 "
MAX_BYTES = 2048


@dataclass(frozen=True)
class Enrollment:
    path: Path
    device: int
    inode: int
    anchor_sha256: str

    def validate(self):
        require(isinstance(self.path, Path) and self.path.is_absolute()
                and bounded_int(self.device, 0, 2**64-1) and bounded_int(self.inode, 1, 2**64-1)
                and sha_text(self.anchor_sha256), "ENROLLMENT_PIN_INVALID")


def _key(info):
    return (info.st_dev, info.st_ino)


@contextmanager
def _open(pin, uid, *, writing=False):
    pin.validate()
    try:
        require(uid == os.geteuid() and pin.path.resolve() == pin.path, "ENROLLMENT_PRINCIPAL_MISMATCH")
        directory = pin.path.parent.stat()
        require(directory.st_uid == uid and stat.S_ISDIR(directory.st_mode)
                and not directory.st_mode & 0o077, "ENROLLMENT_DIRECTORY_NOT_PRIVATE")
        flags = (os.O_RDWR if writing else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        with os.fdopen(os.open(pin.path, flags), "r+b" if writing else "rb", buffering=0) as marker:
            info = os.fstat(marker.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == uid and not info.st_mode & 0o077
                    and info.st_nlink == 1 and _key(info) == (pin.device,pin.inode), "ENROLLMENT_IDENTITY_MISMATCH")
            fcntl.flock(marker, (fcntl.LOCK_EX if writing else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            body = marker.read(MAX_BYTES+1)
            anchor, sep, state = body.partition(b"\n")
            require(len(body) <= MAX_BYTES and sep and anchor.startswith(ANCHOR_PREFIX)
                    and sha(anchor+b"\n") == pin.anchor_sha256, "ENROLLMENT_ANCHOR_MISMATCH")
            yield marker, state
    except FileNotFoundError as exc:
        raise SourceBlocked("ENROLLMENT_OR_REGISTRY_MISSING") from exc
    except BlockingIOError as exc:
        raise SourceBlocked("ENROLLMENT_BUSY") from exc


def _append(marker, payload):
    marker.seek(0, os.SEEK_END)
    require(marker.write(payload) == len(payload), "ENROLLMENT_WRITE_INCOMPLETE")
    os.fsync(marker.fileno())


def _binding(approval):
    return encode({"run_id": approval.run_id, "release": approval.release,
                   "scope": approval.scope.sha256, "authorization": approval.signed_sha256}).encode("ascii")


def _started(approval):
    return b"START "+_binding(approval)+b"\n"


def _registered(ledger):
    info=ledger.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
            and not info.st_mode & 0o077, "ENROLLMENT_LEDGER_UNQUALIFIED")
    return b"REGISTERED "+encode(list(_key(info))).encode("ascii")+b"\n"


def require_enrolled(pin, uid, approval, ledger):
    with _open(pin, uid) as (_, state):
        expected=_started(approval)+_registered(ledger)
        require(state == expected, "REGISTRY_ENROLLMENT_MISMATCH")


def enroll_once(pin, uid, approval, ledger, create_records):
    """Ordinary registry loss or a crashed enrollment stays closed."""
    with _open(pin, uid, writing=True) as (marker, state):
        require(state == b"" and not ledger.exists(), "ENROLLMENT_ALREADY_SPENT")
        _append(marker, _started(approval))
        result=create_records()
        # Persist the directory entry before declaring enrollment complete.
        with os.fdopen(os.open(ledger, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC), "rb") as db:
            os.fsync(db.fileno())
        directory=os.open(ledger.parent,os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        _append(marker, _registered(ledger))
        return result
