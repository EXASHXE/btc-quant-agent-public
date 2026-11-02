"""Run quant with external network calls denied (including DNS)."""

import socket

from btc_quant_agent.platform.cli import main


def blocked(*args, **kwargs):
    raise RuntimeError("OFFLINE_ENGINEERING_NETWORK_BLOCKED")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.getaddrinfo = blocked
main()
