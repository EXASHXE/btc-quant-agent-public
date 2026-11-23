"""Reproduce two bounded fixture scans using a fresh local SQLite cache."""

import argparse
import json
import sqlite3
from pathlib import Path

from .fixture import FixtureClock, FixtureTransport
from .policy import INTERVALS, KLINES
from .scan import Scanner
from .store import Cache


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True, help="new SQLite file for this two-scan fixture run")
    args = parser.parse_args()
    try:
        args.cache.touch(exist_ok=False)
    except FileExistsError:
        parser.error("--cache already exists. Use a fresh path for the deterministic demonstration.")
    clock = FixtureClock()
    transport = FixtureTransport(clock)
    first = Scanner(args.cache, transport, clock).scan()
    first_calls = list(transport.calls)
    clock.advance(INTERVALS["5m"])
    transport.calls.clear()
    second = Scanner(args.cache, transport, clock).scan()
    cache = Cache(args.cache)
    reloaded = [cache.load_snapshot(1) == first, cache.load_snapshot() == second]
    with cache.connect() as db:
        candle_count = db.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    summaries = {
        "first_scan": first["market_setup_status"], "refresh_scan": second["market_setup_status"],
        "snapshots_equal_after_reload": reloaded, "closed_candles_in_cache": candle_count,
        "first_requested_kline_rows": sum(int(params["limit"]) for route, params, _ in first_calls if route == KLINES),
        "refresh_requested_kline_rows": sum(int(params["limit"]) for route, params, _ in transport.calls if route == KLINES),
        "symbols": second["symbols"], "intervals": second["interval_order"],
        "data_origin": second["data_origin"], "account_context_status": second["account_context_status"],
        "human_actionability": second["human_actionability"],
    }
    print(json.dumps(summaries, indent=2))
    return int(not (first["data_ready"] and second["data_ready"] and all(reloaded)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except sqlite3.Error as exc:
        raise SystemExit(f"Local cache error: {exc}") from exc
