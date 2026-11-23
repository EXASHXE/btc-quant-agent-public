"""Process and workspace fences for synthetic-only H3."""

import fcntl
import os
import socket
import stat
from contextlib import contextmanager

from quant_hermes_feishu_h1.contract import ContractError


class Blocked(RuntimeError):
    """A bounded H3 operation was refused."""


def isolated():
    """Require a separate Linux network namespace with only loopback."""
    if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net") or {
        name for _, name in socket.if_nameindex()
    } != {"lo"}:
        raise Blocked("NETWORK_ISOLATION_REQUIRED")


def private_directory(path):
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
        or path.absolute() != path.resolve()
    ):
        raise Blocked("UNSAFE_WORKSPACE")


@contextmanager
def exclusive(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise Blocked("UNSAFE_LOCK")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked("COMPETING_WRITER") from None
        yield
    finally:
        os.close(fd)


class OfflinePermit:
    """A bounded QA permit. There is no loader for live grants."""

    def __init__(self, home, *, starts_ms, expires_ms, clock):
        self.home = home
        self.starts_ms, self.expires_ms, self.clock = starts_ms, expires_ms, clock

    def check(self):
        isolated()
        if (
            os.path.lexists(self.home / "REVOKED")
            or not self.starts_ms <= self.clock() < self.expires_ms
        ):
            raise ContractError("UNAUTHORIZED", "Offline permit expired or revoked")


def restrict_python_network():
    """Add a process-wide guard against accidental DNS or IP socket construction."""
    import sys

    def deny(event, args):
        if event in {
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyaddr",
            "socket.getnameinfo",
        } or (event == "socket.__new__" and args[1] != socket.AF_UNIX):
            raise Blocked("OFFLINE_IP_SOCKET_OR_DNS_DENIED")

    sys.addaudithook(deny)
