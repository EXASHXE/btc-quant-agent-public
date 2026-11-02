"""Explicit fabricated Session03 V2 replay fixture; external network is blocked."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket

from btc_quant_agent.platform.canary import session03 as s
from canary_public.test_session03 import prepared
from canary_public.test_session02 import Backend


def blocked(*args, **kwargs):
    raise AssertionError("OFFLINE_DEMONSTRATION_NATIVE_NETWORK_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    setattr(socket.socket, "connect", blocked)
    setattr(socket.socket, "connect_ex", blocked)
    socket.getaddrinfo = blocked
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    clock, scope = prepared(root)
    clock.advance(7 * 3600000)
    result = s.run_session03(scope, enabled=True, clock=clock, backend=Backend(clock), output=root / "session")
    assert result["exposure"] == "SYNTHETIC" and result["native_market_requests"] == 0
    assert result["flex_window_contract"]["version"] == s.VERSION
    print(json.dumps({"status": "FABRICATED_OFFLINE_REPLAY_ONLY", "receipt": str(root / "session/report.json"),
                      "replay": result["replay"]["status"], "native_market_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
