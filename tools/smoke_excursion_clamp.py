from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from typing import Any

import pyarrow.parquet as pq


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--excursion-parquet",
        default=(
            "artifacts/research/v0.3.3_geometry_20260827T120000Z/"
            "excursion_1h_2h_4h_8h_12h.parquet"
        ),
    )
    args = parser.parse_args()
    table = pq.read_table(args.excursion_parquet).to_pylist()
    report: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    scopes = sorted({str(row["scope"]) for row in table})
    for scope in scopes:
        for horizon in (60, 120, 240, 480, 720):
            for field in ("mfe_atr", "mae_atr"):
                rows = [
                    row
                    for row in table
                    if row["scope"] == scope
                    and row["horizon_minutes"] == horizon
                    and row[field] is not None
                    and not row["incomplete"]
                ]
                values = [float(row[field]) for row in rows]
                if not values:
                    continue
                clamped = [max(0.0, value) for value in values]
                negative = sum(value < 0 for value in values)
                report[f"{scope}_{horizon}m"][field] = {
                    "count": len(values),
                    "negative_count": negative,
                    "negative_rate": negative / len(values),
                    "median_before": statistics.median(values),
                    "median_after_clamp": statistics.median(clamped),
                    "median_changed": statistics.median(values)
                    != statistics.median(clamped),
                }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
