import socket

import pytest


def pytest_sessionstart(session):
    if {name for _, name in socket.if_nameindex()} != {"lo"}:
        pytest.exit("B1 QA requires an isolated network namespace with loopback only", returncode=2)
