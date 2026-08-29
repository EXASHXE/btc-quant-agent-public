from __future__ import annotations

import argparse
import json
from pathlib import Path

from btc_quant_agent.config import load_config
from btc_quant_agent.data.binance_archive import read_parquet_candles
from btc_quant_agent.range_mean_reversion_research import run_v0310, write_v0310_artifacts
from btc_quant_agent.research_protocol import DEV_END_MS, DEV_START_MS, validate_research_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/research/BTCUSDT")
    parser.add_argument("--protocol", default="configs/research/v0.3.10_range_mean_reversion_protocol.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    root = Path(args.data_root)
    manifest_path = root / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_research_manifest(manifest)
    candles = read_parquet_candles(root, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
    config = load_config(args.config)
    result = run_v0310(candles, config)
    output = write_v0310_artifacts(args.output, result, config, args.protocol, manifest_path)
    print(json.dumps({
        "output": str(output), "verdicts": result["hypothesis_verdicts"],
        "recommendation": result["recommendation"], "counts": result["counts"],
        "performance": result["performance"], "holdout_accessed": result["scope"]["holdout_accessed"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
