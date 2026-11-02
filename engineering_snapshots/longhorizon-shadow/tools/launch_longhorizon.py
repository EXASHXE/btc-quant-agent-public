"""One operator, one finite foreground session. Ships no native authorization."""

from __future__ import annotations

import argparse
import json

from btc_quant_agent.platform.canary.longhorizon import load_grant, requirements
from btc_quant_agent.platform.canary.public_policy import PublicStop, SystemClock
from btc_quant_agent.platform.canary.public_runtime import run_public


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("requirements", "preflight", "run"))
    parser.add_argument("--owner-grant")
    parser.add_argument("--clock-qualification-receipt")
    parser.add_argument("--enable-public-network", action="store_true")
    args = parser.parse_args(argv)
    entered = False
    try:
        if args.command == "requirements":
            result = requirements()
        else:
            if not args.owner_grant:
                raise PublicStop("LONGHORIZON_NEW_OWNER_GRANT_ABSENT")
            if args.command == "run" and not args.enable_public_network:
                raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
            scope = load_grant(args.owner_grant, args.clock_qualification_receipt)
            clock = SystemClock()
            result = scope.preflight(clock, native=True)
            if args.command == "run" and not result["reasons"]:
                entered = True
                result = run_public(scope, enabled=True, clock=clock)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 2 if result.get("status") in ("BLOCKED", "OFFLINE_READY_PENDING_EXACT_OWNER_GRANT") else 0
    except (PublicStop, ValueError, OSError) as exc:
        print(json.dumps({"status": "NO_GO_NATIVE_SOURCE", "reason": str(exc),
                          "native_market_requests_this_failed_launch": None if entered else 0,
                          "request_count_status": "RECONCILE_RECEIPTS" if entered else "NO_RUN_ENTERED",
                          "source_qualified": False, "shadow_advisory_qualified": False,
                          "economically_validated": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
