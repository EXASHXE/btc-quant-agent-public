from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from btc_quant_agent.data.binance_spot_archive import build_spot_market_flow_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build checksum-verified Binance Spot flow data")
    parser.add_argument("--root", default="data/research/BTCUSDT_SPOT")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    manifest = build_spot_market_flow_dataset(
        args.root,
        datetime(2021, 1, 1, tzinfo=UTC),
        datetime(2026, 2, 1, tzinfo=UTC),
        symbol=args.symbol,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
