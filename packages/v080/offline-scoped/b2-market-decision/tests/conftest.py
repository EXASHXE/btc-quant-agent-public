import socket

import pytest


def pytest_sessionstart(session):
    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        pytest.exit("B2 tests require a loopback-only network namespace", returncode=2)
