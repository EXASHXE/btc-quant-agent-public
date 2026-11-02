"""One-shot operator launcher; no scheduler and no market access without explicit flag/window."""

from __future__ import annotations

import argparse
import json
import sys

from btc_quant_agent.platform.canary.control import CanaryStore
from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.canary.public_journal import PublicJournal
from btc_quant_agent.platform.canary.public_policy import (
    OUTPUT,
    PublicStop,
    SystemClock,
    load_scope,
    preflight,
    DEFAULT_GRANT,
)
from btc_quant_agent.platform.canary.public_runtime import run_public


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("preflight", "run", "replay", "purge-expired"))
    p.add_argument("--grant", default=str(DEFAULT_GRANT))
    p.add_argument(
        "--enable-public-network",
        action="store_true",
        help="Explicit operator activation; exact UTC window is still mandatory",
    )
    a = p.parse_args(argv)
    try:
        scope = load_scope(a.grant)
        if a.command == "preflight":
            result = preflight(scope)
        elif a.command == "run":
            result = run_public(scope, enabled=a.enable_public_network)
        else:
            run = OUTPUT / "run"
            if not (run / "started.json").is_file():
                raise PublicStop("NO_NATIVE_RUN_TO_REPLAY")
            mode = json.loads((run / "started.json").read_text())["exposure"]
            journal = PublicJournal(run, CanaryStore(run / "state.sqlite"), SystemClock(), exposure=mode)
            if a.command == "replay":
                result = journal.audit_replay(normalize)
            else:
                result = journal.expire(SystemClock().wall())
        print(json.dumps(result, indent=2, default=str, allow_nan=False))
        return 2 if result.get("status") == "BLOCKED" else 0
    except (PublicStop, ValueError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": str(exc),
                    "native_market_calls_this_failed_launch": 0
                    if "WINDOW" in str(exc) or "DEFAULT_DISABLED" in str(exc)
                    else None,
                    "source_qualified": False,
                    "shadow_advisory_qualified": False,
                    "economically_validated": False,
                }
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
