from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.data.funding import read_funding_events_csv
from btc_quant_agent.research import run_full_suite, write_research_artifacts
from btc_quant_agent.research_protocol import (
    DEV_END_MS,
    DEV_START_MS,
    validate_research_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/BTCUSDT")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    root = Path(args.root)
    manifest_path = root / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_research_manifest(manifest)
    candles = read_parquet_candles(
        root,
        start_ms=DEV_START_MS,
        end_ms=DEV_END_MS,
    )
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
    suite = run_full_suite(candles, config, None, funding, seed=args.seed)
    write_research_artifacts(
        args.output,
        suite,
        config,
        data_manifest_path=manifest_path,
        seed=args.seed,
    )
    report = json.loads((Path(args.output) / "research_report.json").read_text())
    print(
        json.dumps(
            {
                "output": args.output,
                "classification": report["protocol"]["sample_classification"],
                "baseline": report["baseline"]["overall"],
                "holdout_accessed": report["protocol"]["holdout_accessed"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
