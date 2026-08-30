from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.breakout_edge_research import (
    run_v035_breakout_qualification,
    write_v035_artifacts,
)
from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.data.funding import read_funding_events_csv
from btc_quant_agent.research_protocol import (
    DEV_END_MS,
    DEV_START_MS,
    validate_research_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/BTCUSDT")
    parser.add_argument("--output", required=True)
    parser.add_argument("--protocol", default="configs/research/v0.3.5_breakout_edge_protocol.json")
    parser.add_argument(
        "--baseline", default="artifacts/research/run0-dev-frozen-v022-seed7-20260825"
    )
    parser.add_argument("--seed", type=int, default=35)
    args = parser.parse_args()
    root = Path(args.root)
    manifest_path = root / "data_manifest.json"
    validate_research_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    candles = read_parquet_candles(root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    funding = [
        event
        for event in read_funding_events_csv(root / "funding_events.csv")
        if DEV_START_MS <= event.timestamp_ms < DEV_END_MS
    ]
    config = load_config("configs/frozen/v0.2.2.toml")
    config = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    result = run_v035_breakout_qualification(
        candles, config, funding, args.baseline, seed=args.seed
    )
    output = write_v035_artifacts(
        args.output, result, config, args.protocol, manifest_path, args.baseline, seed=args.seed
    )
    print(
        json.dumps(
            {
                "status": result["overall_status"],
                "output": str(output),
                "counts": result["br_stage_counts"],
                "verdicts": result["hypothesis_verdicts"],
                "recommendation": result["recommendation"],
                "performance": result["performance"],
                "holdout_accessed": result["scope"]["holdout_accessed"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
