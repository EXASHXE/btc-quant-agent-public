"""One-shot fabricated-source demo. All DNS and socket connections are forbidden."""

import argparse
import json
from pathlib import Path
import socket
import sys


def main():
    def forbidden(*a, **kw):
        raise AssertionError("FABRICATED_DEMO_HAS_NO_NETWORK_PERMISSION")

    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.getaddrinfo = forbidden
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    from canary_public.fixtures import Backend, Clock, structural_replay
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.canary.public_policy import END, OUTPUT, PublicStop, load_scope
    from btc_quant_agent.platform.canary.public_runtime import run_public, save_reports

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("finite", "structural"))
    args = parser.parse_args()
    path = OUTPUT / "engineering" / ("demo_" + args.profile)
    if path.exists():
        raise PublicStop("IMMUTABLE_DEMO_OUTPUT_ALREADY_EXISTS")
    scope = load_scope()
    if args.profile == "finite":
        clock = Clock(END - 6000)
        result = run_public(scope, enabled=True, clock=clock, backend=Backend(scope, clock), output=path)
    else:
        model, journal, _ = structural_replay(scope, path)
        result = {
            "status": "SYNTHETIC_DEMO_ONLY",
            "exposure": "SYNTHETIC",
            "native_market_requests": 0,
            "model": model.report(),
            "replay": journal.audit_replay(normalize),
            "source_qualified": False,
            "shadow_advisory_qualified": False,
            "economically_validated": False,
            "external_sends": 0,
            "actual_user_actions_or_fills": 0,
        }
        save_reports(path, result)
    print(
        json.dumps(
            {
                "output": str(path),
                "exposure": result["exposure"],
                "replay": result["replay"],
                "native_market_requests": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
