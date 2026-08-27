from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.causal_entry_research import (
    run_v034_causal_entry_validation,
    write_v034_artifacts,
)
from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.data.funding import read_funding_events_csv
from btc_quant_agent.research_protocol import DEV_END_MS, DEV_START_MS, validate_research_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/BTCUSDT")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    parser.add_argument(
        "--protocol", default="configs/research/v0.3.4_causal_entry_protocol.json"
    )
    parser.add_argument("--seed", type=int, default=34)
    args = parser.parse_args()
    root = Path(args.root)
    manifest_path = root / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_research_manifest(manifest)
    candles = read_parquet_candles(root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    funding = [
        event
        for event in read_funding_events_csv(root / "funding_events.csv")
        if DEV_START_MS <= event.timestamp_ms < DEV_END_MS
    ]
    config = load_config(args.config)
    config = replace(
        config,
        strategy=replace(
            config.strategy,
            enable_derivatives_group=False,
            enable_order_book_factor=False,
        ),
    )
    started = time.perf_counter()
    result = run_v034_causal_entry_validation(candles, config, funding, seed=args.seed)
    output = write_v034_artifacts(
        args.output,
        result,
        config,
        args.protocol,
        manifest_path,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "status": result["overall_status"],
                "output": str(output),
                "funnel": result["e_retrace_funnel"],
                "hypothesis_verdicts": result["hypothesis_verdicts"],
                "candidate_recommendation": result["candidate_recommendation"],
                "performance": result["performance"],
                "wall_seconds": time.perf_counter() - started,
                "holdout_accessed": result["scope"]["holdout_accessed"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
