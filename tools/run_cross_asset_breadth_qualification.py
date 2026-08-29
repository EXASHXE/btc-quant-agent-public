from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.config import load_config
from btc_quant_agent.cross_asset_breadth_research import (
    read_hourly_basket,
    run_v039,
    write_v039_artifacts,
)
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.research_protocol import DEV_END_MS, DEV_START_MS, validate_research_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btc-root", default="data/research/BTCUSDT")
    parser.add_argument("--basket-root", default="data/research/cross_asset_1h")
    parser.add_argument(
        "--protocol", default="configs/research/v0.3.9_cross_asset_breadth_protocol.json"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    btc_root, basket_root = Path(args.btc_root), Path(args.basket_root)
    manifest = json.loads((btc_root / "data_manifest.json").read_text())
    validate_research_manifest(manifest)
    basket_manifest = json.loads((basket_root / "basket_manifest.json").read_text())
    if basket_manifest["end_ms_exclusive"] != DEV_END_MS:
        raise ValueError("cross-asset Holdout firewall")
    candles = read_parquet_candles(btc_root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    config = load_config(args.config)
    config = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    result = run_v039(candles, read_hourly_basket(basket_root), config)
    output = write_v039_artifacts(
        args.output,
        result,
        config,
        args.protocol,
        btc_root / "data_manifest.json",
        basket_root / "basket_manifest.json",
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
