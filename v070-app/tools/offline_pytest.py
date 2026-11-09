"""Run inherited synthetic tests with external network connections disabled."""

import socket
import ipaddress
import sys

import pytest


original_connect = socket.socket.connect


def blocked(sock, address):
    if sock.family == socket.AF_UNIX or ipaddress.ip_address(address[0]).is_loopback:
        return original_connect(sock, address)
    raise AssertionError("OFFLINE_ENGINEERING_EXTERNAL_NETWORK_BLOCKED")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked

raise SystemExit(pytest.main(sys.argv[1:]))
