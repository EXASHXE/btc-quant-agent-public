from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.data.binance_spot_archive import read_spot_flow_rows
from btc_quant_agent.research_protocol import DEV_END_MS, DEV_START_MS, validate_research_manifest
from btc_quant_agent.spot_perp_flow_research import run_v0312, write_v0312_artifacts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btc-root", default="data/research/BTCUSDT")
    parser.add_argument("--spot-root", default="data/research/BTCUSDT_SPOT")
    parser.add_argument(
        "--protocol", default="configs/research/v0.3.12_spot_perp_flow_protocol.json"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    btc_root, spot_root = Path(args.btc_root), Path(args.spot_root)
    btc_manifest = json.loads((btc_root / "data_manifest.json").read_text())
    validate_research_manifest(btc_manifest)
    spot_manifest = json.loads((spot_root / "data_manifest.json").read_text())
    if spot_manifest["start_ms"] != DEV_START_MS or spot_manifest["end_ms_exclusive"] != DEV_END_MS:
        raise ValueError("Spot dataset violates v0.3.12 Development firewall")
    candles = read_parquet_candles(btc_root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    spot = read_spot_flow_rows(spot_root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    config = load_config(args.config or "configs/frozen/v0.2.2.toml")
    config = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    result = run_v0312(candles, spot, config)
    output = write_v0312_artifacts(
        args.output,
        result,
        config,
        args.protocol,
        btc_root / "data_manifest.json",
        spot_root / "data_manifest.json",
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
