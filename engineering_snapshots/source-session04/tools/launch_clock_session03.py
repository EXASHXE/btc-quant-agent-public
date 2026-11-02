"""Operator-only, signed flexible Session03. No scheduling, waiting or grant creation."""

from __future__ import annotations

import argparse
import json

from btc_quant_agent.platform.canary.public_policy import PublicStop, SystemClock
from btc_quant_agent.platform.canary import session03 as s


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("requirements", "preflight", "run", "reconcile"))
    parser.add_argument("--owner-grant", help="Separately Owner-signed exact Session03 authorization")
    parser.add_argument(
        "--enable-public-network", action="store_true", help="Explicit foreground operator opt-in"
    )
    args = parser.parse_args(argv)
    entered = False
    try:
        if args.command == "requirements":
            result = s.requirements()
        elif args.command == "reconcile":
            result = s.reconcile()
        else:
            if not args.owner_grant:
                raise PublicStop("SESSION03_OWNER_GRANT_ABSENT")
            if args.command == "run" and not args.enable_public_network:
                raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
            clock = SystemClock()
            scope = s.load_session03(args.owner_grant, clock.wall())
            result = scope.preflight(clock, native=True)
            if args.command == "run":
                if result["reasons"]:
                    raise PublicStop("|".join(result["reasons"]))
                entered = True
                result = s.run_session03(scope, enabled=True, clock=clock)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 2 if result.get("status") in ("BLOCKED", "PREPARED_BUT_NOT_AUTHORIZED") else 0
    except (PublicStop, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "PREPARED_BUT_NOT_AUTHORIZED",
                    "reason": str(exc),
                    "native_market_requests_this_failed_launch": None if entered else 0,
                    "source_qualified": False,
                    "shadow_advisory_qualified": False,
                    "economically_validated": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
