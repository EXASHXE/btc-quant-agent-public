"""Finite, grant-bound Session 02 launcher. This preparation ships NO authorization."""

from __future__ import annotations

import argparse
import json

from btc_quant_agent.platform.canary.public_policy import PublicStop, SystemClock
from btc_quant_agent.platform.canary.public_runtime import run_public
from btc_quant_agent.platform.canary.session02 import load_session02, requirements


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("requirements", "preflight", "run"))
    parser.add_argument("--owner-grant", help="Future exact Owner-signed grant; no grant is shipped")
    parser.add_argument(
        "--enable-public-network",
        action="store_true",
        help="Explicit one-shot operator opt-in; signature/time/technical gates still mandatory",
    )
    args = parser.parse_args(argv)
    entered_run = False
    try:
        if args.command == "requirements":
            result = requirements()
        else:
            if not args.owner_grant:
                raise PublicStop("SESSION02_OWNER_GRANT_ABSENT")
            if args.command == "run" and not args.enable_public_network:
                raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
            clock = SystemClock()
            scope = load_session02(args.owner_grant, clock.wall())
            result = scope.preflight(clock, native=True)
            if args.command == "run":
                if result["reasons"]:
                    raise PublicStop("|".join(result["reasons"]))
                entered_run = True
                result = run_public(scope, enabled=True, clock=clock)
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 2 if result.get("status") in ("BLOCKED", "PREPARED_BUT_NOT_AUTHORIZED") else 0
    except (PublicStop, ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "PREPARED_BUT_NOT_AUTHORIZED",
                    "reason": str(exc),
                    "native_market_requests_this_failed_launch": None if entered_run else 0,
                    "request_count_status": "RECONCILE_RUN_RECEIPTS" if entered_run else "NO_NATIVE_RUN_ENTERED",
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
