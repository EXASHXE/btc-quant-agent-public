from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.directional_architecture_research import (
    run_v036_directional_architecture,
    write_v036_artifacts,
)
from btc_quant_agent.research_protocol import (
    DEV_END_MS,
    DEV_START_MS,
    validate_research_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/BTCUSDT")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--protocol",
        default="configs/research/v0.3.6_directional_architecture_protocol.json",
    )
    parser.add_argument("--config")
    parser.add_argument("--seed", type=int, default=36)
    args = parser.parse_args()
    root = Path(args.root)
    manifest_path = root / "data_manifest.json"
    validate_research_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    candles = read_parquet_candles(root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    config = load_config(args.config)
    config = replace(
        config,
        strategy=replace(
            config.strategy,
            enable_derivatives_group=False,
            enable_order_book_factor=False,
        ),
    )
    result = run_v036_directional_architecture(candles, config, seed=args.seed)
    output = write_v036_artifacts(
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
                "episodes": result["episode_summary"],
                "verdicts": result["hypothesis_verdicts"],
                "proposed_direction_architecture": result["proposed_direction_architecture"],
                "opportunity_layer_setups": result["opportunity_layer_setups"],
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
