"""Portable launcher for the existing CLI's bounded synthetic RC commands."""
import socket
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def denied(*args, **kwargs):
    raise RuntimeError("PROGRAM_A_OFFLINE_NETWORK_FORBIDDEN")


socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.getaddrinfo = denied

from btc_quant_agent.platform.cli import main  # noqa: E402

arguments = sys.argv[1:]
raise SystemExit(main(arguments if arguments[:1] == ["source"] else ["offline-rc", *arguments]))
