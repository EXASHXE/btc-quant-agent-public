"""Local static snapshot renderer; reuses the original document and table renderer."""

from __future__ import annotations

import html
import json
import time

from .reporting import document, table
from .swing import INTERVALS, decide
from .swing_view import view


def page(snapshot=None, *, now_ms=None):
    now_ms = now_ms if now_ms is not None else time.time_ns() // 1_000_000
    if snapshot is not None and snapshot.get("schema_version") == "PROGRAM_A_LOCAL_DASHBOARD_V1":
        from .rc_dashboard import render

        return render(snapshot, now_ms=now_ms)
    if snapshot is None:
        snapshot = decide(symbol="BTCUSDT", decision_ms=now_ms,
                          trigger_close_ms=now_ms // INTERVALS["4H"] * INTERVALS["4H"]
                          ).model_dump(mode="json")
    value = view(snapshot, now_ms=now_ms)
    rows = [{"State": value["state"], "Actionability": value["actionability"],
             "Scope": value["scope"]}]
    body = ("<p>Review once or twice daily. Decisions use completed 4H and 1D candles; "
            "1H confirmation is optional. Holding horizon: 4 hours to 5 days; S1: 8 hours to 5 days.</p>"
            + table(rows) + "<p>Planned payoff is not an observed fill or PnL. "
            "Unattended leveraged positions carry risk. No orders or notifications.</p><pre>"
            + html.escape(json.dumps(value, indent=2, default=str, allow_nan=False)) + "</pre>")
    return document("Swing advisory — local snapshot", body,
                    label="OFFLINE CONTRACT / HISTORICAL VIEW · NO SOURCE OR ECONOMIC QUALIFICATION")
