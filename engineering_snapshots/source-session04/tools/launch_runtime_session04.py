"""Manual foreground Session04 only. Default-disabled; no signer or scheduler."""

import argparse
import json

from btc_quant_agent.platform.canary import session04 as s
from btc_quant_agent.platform.canary.public_policy import PublicStop, SystemClock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("requirements", "preflight", "run", "reconcile"))
    parser.add_argument("--owner-grant")
    parser.add_argument("--enable-public-network", action="store_true")
    args = parser.parse_args(argv)
    entered = False
    try:
        if args.command == "requirements":
            result = s.requirements()
        elif args.command == "reconcile":
            result = s.previous.reconcile(s.SESSION_OUTPUT)
        else:
            if not args.owner_grant:
                raise PublicStop("SESSION04_OWNER_GRANT_ABSENT")
            if args.command == "run" and not args.enable_public_network:
                raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
            clock = SystemClock()
            scope = s.load_session04(args.owner_grant, clock.wall())
            result = scope.preflight(clock, native=True)
            if args.command == "run":
                if result["reasons"]:
                    raise PublicStop("|".join(result["reasons"]))
                entered = True
                result = s.run_session04(scope, enabled=True, clock=clock)
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 2 if result.get("status") == "BLOCKED" else 0
    except (PublicStop, ValueError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "native_market_requests": None if entered else 0,
                          "source_qualified": False, "shadow_advisory_qualified": False,
                          "long_authorized": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
