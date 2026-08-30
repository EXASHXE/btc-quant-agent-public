from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.funding_crowding_research import audit_funding_data
from btc_quant_agent.funding_stability_research import (
    SEED,
    run_v038_funding_stability,
    write_v038_artifacts,
)
from btc_quant_agent.research_protocol import DEV_END_MS, DEV_START_MS, validate_research_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/BTCUSDT")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--protocol", default="configs/research/v0.3.8_funding_stability_protocol.json"
    )
    parser.add_argument("--config")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    root = Path(args.root)
    manifest_path = root / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_research_manifest(manifest)
    funding_path = root / "funding_events.csv"
    _, funding_events = audit_funding_data(funding_path, manifest)
    candles = read_parquet_candles(root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    config = load_config(args.config or "configs/frozen/v0.2.2.toml")
    config = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    result = run_v038_funding_stability(candles, funding_events, config, seed=args.seed)
    output = write_v038_artifacts(
        args.output, result, config, args.protocol, manifest_path, funding_path
    )
    print(
        json.dumps(
            {
                "status": result["overall_status"],
                "output": str(output),
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
