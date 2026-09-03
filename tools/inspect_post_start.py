import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

start_ms = 1788417000000  # 2026-09-03T06:30:00Z
now_ms = int(time.time() * 1000)

print(f"Current UTC: {datetime.fromtimestamp(now_ms/1000, UTC).isoformat()} ({now_ms})")
print(f"Start UTC:   {datetime.fromtimestamp(start_ms/1000, UTC).isoformat()} ({start_ms})")
print(f"Elapsed since start: {(now_ms - start_ms)/1000:.1f}s ({(now_ms - start_ms)/900000:.2f} 15m slots)")

# Expected decision slots since 06:30 UTC
slots = []
s = start_ms
while s <= now_ms:
    slots.append(s)
    s += 900_000
print(f"Expected slots ({len(slots)}): {[datetime.fromtimestamp(x/1000, UTC).strftime('%H:%M') for x in slots]}")

# Derivatives
c1 = sqlite3.connect("data/forward/BTCUSDT/derivatives.sqlite3")
runs = c1.execute(
    "SELECT run_id, scheduled_slot_ms, status, evidence_epoch_id, started_at_ms, error_summary FROM collection_runs WHERE scheduled_slot_ms >= ? ORDER BY scheduled_slot_ms",
    (start_ms,)
).fetchall()
print("\n--- Derivatives (DERIVATIVES_PIT_EPOCH_V0320_001) ---")
print(f"Recorded runs: {len(runs)}")
for r in runs:
    dt_str = datetime.fromtimestamp(r[1]/1000, UTC).strftime('%H:%M:%S') if r[1] else "None"
    print(f"  slot={r[1]} ({dt_str}) status={r[2]} epoch={r[3]} err={r[5]}")

# Opportunity
c2 = sqlite3.connect("data/forward/BTCUSDT/opportunity_shadow.sqlite3")
obs = c2.execute(
    "SELECT observation_id, scheduled_slot_ms, status, campaign_id, observed_at_ms FROM scan_observations WHERE scheduled_slot_ms >= ? ORDER BY scheduled_slot_ms",
    (start_ms,)
).fetchall()
print("\n--- Opportunity (H37 / OPPORTUNITY_FORWARD_V0320_20260903T063000Z) ---")
print(f"Recorded scans: {len(obs)}")
for o in obs:
    dt_str = datetime.fromtimestamp(o[1]/1000, UTC).strftime('%H:%M:%S') if o[1] else "None"
    print(f"  slot={o[1]} ({dt_str}) status={o[2]} campaign={o[3]}")

# Microstructure
print("\n--- Microstructure ---")
for p in sorted(Path("data/forward/BTCUSDT/microstructure").glob("microstructure-*.sqlite3")):
    c_m = sqlite3.connect(p)
    try:
        depth_cnt = c_m.execute("SELECT count(*) FROM depth_events").fetchone()[0]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        depth_cnt = "N/A"
    try:
        trade_cnt = c_m.execute("SELECT count(*) FROM agg_trades").fetchone()[0]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        trade_cnt = "N/A"
    try:
        hb = c_m.execute("SELECT MAX(last_heartbeat_ms) FROM process_instances").fetchone()[0]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        hb = "N/A"
    print(f"  {p.name}: trades={trade_cnt}, depth={depth_cnt}, last_hb={hb}")
