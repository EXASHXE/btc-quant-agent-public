from __future__ import annotations

import argparse
import json
import resource
import time
from dataclasses import replace

from btc_quant_agent.backtest import BacktestEngine
from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.data.funding import read_funding_events_csv
from btc_quant_agent.engine import QuantEngine
from btc_quant_agent.research_protocol import DEV_START_MS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rows", type=int, choices=(100_000, 500_000, 1_000_000))
    parser.add_argument("--root", default="data/research/BTCUSDT")
    args = parser.parse_args()

    load_started = time.perf_counter()
    candles = read_parquet_candles(
        args.root,
        start_ms=DEV_START_MS,
        end_ms=DEV_START_MS + args.rows * 60_000,
    )
    funding = read_funding_events_csv(f"{args.root}/funding_events.csv")
    funding = [event for event in funding if event.timestamp_ms <= candles[-1].close_time_ms]
    loaded_seconds = time.perf_counter() - load_started
    config = load_config()
    config = replace(
        config,
        strategy=replace(
            config.strategy,
            enable_derivatives_group=False,
            enable_order_book_factor=False,
        ),
    )
    run_started = time.perf_counter()
    outcomes = BacktestEngine(QuantEngine(config), None, funding).run(candles)
    run_seconds = time.perf_counter() - run_started
    print(
        json.dumps(
            {
                "rows": len(candles),
                "loaded_seconds": round(loaded_seconds, 3),
                "backtest_seconds": round(run_seconds, 3),
                "rows_per_second": round(len(candles) / run_seconds),
                "max_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                "outcomes": len(outcomes),
                "filled_trades": sum(item.entered_at_ms is not None for item in outcomes),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
