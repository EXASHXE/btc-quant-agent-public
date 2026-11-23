"""Test-only process entry; never copied into the release wheel."""

import fcntl
import json
import os
import sys
import termios
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from quant_s2rb.runtime import Paths, rehearse_loopback
from quant_s2v2.ledger import Ledger
from quant_s2v2.protocol import Denied


def install_wire_guard():
    def guard(event, args):
        if event in {
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyaddr",
            "socket.getnameinfo",
        }:
            raise Denied("QA_SYSTEM_RESOLVER_FORBIDDEN")
        if event in {"socket.connect", "socket.bind"}:
            address = args[1]
            if type(address) is tuple and address[0] != "127.0.0.1":
                raise Denied("QA_NON_LOOPBACK_FORBIDDEN")

    sys.addaudithook(guard)


def crash_before_debit(*args):
    os._exit(72)


def crash_after_debit(self, *args):
    original_reserve(self, *args)
    os._exit(73)


def crash_before_failure_log(*args):
    os._exit(74)


original_reserve = Ledger.reserve


def bad_fsync(fd):
    raise OSError("injected fsync failure")


class FixtureClock:
    def __init__(self, epoch):
        self.epoch = epoch

    def now(self):
        return (
            self.epoch["wall_ms"] + (time.monotonic_ns() - self.epoch["monotonic_ns"]) // 1_000_000
        )


if __name__ == "__main__":
    install_wire_guard()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    configuration, grant, wheel, clock, fault = sys.argv[1:]
    epoch = json.loads(Path(clock).read_text())
    with ExitStack() as stack:
        stack.enter_context(patch("quant_s2rb.runtime.Clock", new=lambda: FixtureClock(epoch)))
        faults = {
            "before_debit": ("quant_s2v2.ledger.Ledger.reserve", crash_before_debit),
            "after_debit": ("quant_s2v2.ledger.Ledger.reserve", crash_after_debit),
            "ambiguity": ("quant_s2rb.runtime._stop", crash_before_failure_log),
            "fsync": ("quant_s2v2.ledger.os.fsync", bad_fsync),
        }
        if fault != "none":
            stack.enter_context(patch(faults[fault][0], new=faults[fault][1]))
        try:
            result = rehearse_loopback(Paths(Path(configuration), Path(grant), Path(wheel)))
        except Denied as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(3)
    print(json.dumps(result, sort_keys=True))
