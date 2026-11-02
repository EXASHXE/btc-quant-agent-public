"""Run inherited synthetic tests with external network connections disabled."""

import socket
import sys

import pytest


def blocked(*args, **kwargs):
    raise AssertionError("OFFLINE_ENGINEERING_EXTERNAL_NETWORK_BLOCKED")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked
raise SystemExit(pytest.main(sys.argv[1:]))
