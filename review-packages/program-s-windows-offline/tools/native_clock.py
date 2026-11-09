# ruff: noqa: E402
# Source/bootstrap path is established before optional installed Quant imports.
"""Finite120s actual Windows counters; no socket, server, settings or UTC qualification."""

from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from win_capture.win_clock import DualWindowsClockMonitor

m = DualWindowsClockMonitor()
rows = []
while True:
    s = m.sample()
    rows.append(s)
    if s["qpc_after_ms"] - m.anchor["qpc_before_ms"] >= 120000:
        break
    time.sleep(0.1)
result = {
    "schema": "S_ACTUAL_WINDOWS_120S_OFFLINE_V1",
    "samples": len(rows),
    "elapsed_qpc_ms": rows[-1]["qpc_after_ms"] - m.anchor["qpc_before_ms"],
    "wall_jumps": m.wall_jumps_observed,
    "W32Time": m.w32tm_snapshot,
    "first": rows[0],
    "last": rows[-1],
    "strict_UTC": False,
    "exchange_requests": 0,
    "clock_scope": "finite control coherence only; not Source qualification",
}
(ROOT / "audit/S_WINDOWS_CLOCK_120S.json").write_text(json.dumps(result, indent=2) + "\n")
(ROOT / "audit/S_WINDOWS_CLOCK_120S.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
print(json.dumps(result))
