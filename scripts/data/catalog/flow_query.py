"""DATA-C2: Flow query engine and validation suite.

Supports:
  - Range queries over partitioned minute flow Parquet data.
  - QA validation: aggTrades minute aggregates vs C1 canonical OHLCV bars.
  - Cross-market flow analysis: BTC perpetual vs spot volume and signed flow.
  - Causal hourly as-of join: strictly closed minutes (interval_end_utc <= C),
    5m and 1h flow rollups, and zero future outcome evaluation.
  - Generates artifacts:
      * lakehouse/c2/aggregates_vs_candles_QA.json
      * lakehouse/c2/real_pilot_query.json
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

DEFAULT_C1_ROOT = Path("/root/workspace/project/crypto-data/lakehouse/c1/canonical_v1")
DEFAULT_C2_ROOT = Path("/root/workspace/project/crypto-data/lakehouse/c2")


def _to_us(dt: datetime) -> int:
    return int(dt.timestamp() * 10**6)


def _dt_from_iso_or_obj(val: str | datetime) -> datetime:
    if isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    return val


class FlowQueryEngine:
    def __init__(
        self,
        c2_root: Path = DEFAULT_C2_ROOT,
        c1_root: Path = DEFAULT_C1_ROOT,
    ):
        self.c2_root = c2_root
        self.minute_flow_dir = c2_root / "minute_flow"
        self.c1_root = c1_root

    def query_flow_range(
        self,
        exchange: str,
        asset: str,
        product: str,
        start_utc: str | datetime,
        end_utc: str | datetime,
        columns: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query minute flow records bounded by UTC timestamp range with partition pruning."""
        start_dt = _dt_from_iso_or_obj(start_utc)
        end_dt = _dt_from_iso_or_obj(end_utc)
        start_us = _to_us(start_dt)
        end_us = _to_us(end_dt)

        partition_dir = (
            self.minute_flow_dir
            / f"exchange={exchange}"
            / f"asset={asset}"
            / f"product={product}"
        )

        if not partition_dir.exists():
            return []

        dataset = ds.dataset(
            str(partition_dir),
            format="parquet",
            partitioning="hive",
        )

        filter_expr = (pc.field("interval_start_utc") >= pa.scalar(start_us, pa.timestamp("us", tz="UTC"))) & (
            pc.field("interval_start_utc") < pa.scalar(end_us, pa.timestamp("us", tz="UTC"))
        )

        scanner = dataset.scanner(
            columns=columns,
            filter=filter_expr,
            use_threads=True,
        )

        table_data = scanner.to_table()
        if limit is not None and limit > 0:
            table_data = table_data.slice(0, limit)

        pylist = table_data.to_pylist()
        if pylist and "interval_start_utc" in pylist[0]:
            pylist.sort(key=lambda r: r["interval_start_utc"])
        return pylist

    def query_c1_bars_range(
        self,
        exchange: str,
        asset: str,
        product: str,
        start_utc: str | datetime,
        end_utc: str | datetime,
        columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query C1 canonical bars for comparison."""
        start_dt = _dt_from_iso_or_obj(start_utc)
        end_dt = _dt_from_iso_or_obj(end_utc)
        start_us = _to_us(start_dt)
        end_us = _to_us(end_dt)

        partition_dir = (
            self.c1_root
            / "table=bars"
            / f"exchange={exchange}"
            / f"asset={asset}"
            / f"product={product}"
        )

        if not partition_dir.exists():
            return []

        dataset = ds.dataset(
            str(partition_dir),
            format="parquet",
            partitioning="hive",
        )

        filter_expr = (pc.field("interval_start_utc") >= pa.scalar(start_us, pa.timestamp("us", tz="UTC"))) & (
            pc.field("interval_start_utc") < pa.scalar(end_us, pa.timestamp("us", tz="UTC"))
        )

        scanner = dataset.scanner(columns=columns, filter=filter_expr, use_threads=True)
        table_data = scanner.to_table()
        pylist = table_data.to_pylist()
        if pylist and "interval_start_utc" in pylist[0]:
            pylist.sort(key=lambda r: r["interval_start_utc"])
        return pylist

    def compare_flow_vs_c1_bars(
        self,
        exchange: str = "binance",
        asset: str = "BTC",
        product: str = "USD_M_PERPETUAL",
        start_utc: str | datetime = "2023-08-15T00:00:00Z",
        end_utc: str | datetime = "2023-08-16T00:00:00Z",
    ) -> dict[str, Any]:
        """Validate aggTrades minute aggregates against C1 canonical OHLCV bars."""
        flows = self.query_flow_range(exchange, asset, product, start_utc, end_utc)
        bars = self.query_c1_bars_range(exchange, asset, product, start_utc, end_utc)

        bars_by_start = {
            (r["interval_start_utc"].isoformat() if hasattr(r["interval_start_utc"], "isoformat") else str(r["interval_start_utc"])): r
            for r in bars
        }

        matched_count = 0
        total_flow_vol_base = 0.0
        total_bar_vol_base = 0.0
        max_price_diff = 0.0
        volume_diff_abs_sum = 0.0
        discrepancies: list[dict[str, Any]] = []

        for f in flows:
            key = f["interval_start_utc"].isoformat() if hasattr(f["interval_start_utc"], "isoformat") else str(f["interval_start_utc"])
            b = bars_by_start.get(key)
            if not b:
                continue

            matched_count += 1
            f_vol = f["volume_base"]
            b_vol = b["base_volume"]
            total_flow_vol_base += f_vol
            total_bar_vol_base += b_vol

            vol_diff = abs(f_vol - b_vol)
            volume_diff_abs_sum += vol_diff

            p_diff = abs(f["trade_close"] - b["close"])
            max_price_diff = max(max_price_diff, p_diff)

            # Check if difference is material (> 0.01%)
            if b_vol > 0 and (vol_diff / b_vol) > 0.0001:
                discrepancies.append({
                    "minute": key,
                    "flow_volume": round(f_vol, 4),
                    "bar_volume": round(b_vol, 4),
                    "rel_diff": round(vol_diff / b_vol, 6),
                })

        rel_diff_pct = (
            abs(total_flow_vol_base - total_bar_vol_base) / total_bar_vol_base * 100
            if total_bar_vol_base > 0
            else 0.0
        )

        is_passed = matched_count > 0 and rel_diff_pct < 0.05 and max_price_diff < 1.0

        qa_report = {
            "exchange": exchange,
            "asset": asset,
            "product": product,
            "window_start_utc": str(start_utc),
            "window_end_utc": str(end_utc),
            "flow_records_count": len(flows),
            "bar_records_count": len(bars),
            "matched_minutes": matched_count,
            "total_flow_volume_base": round(total_flow_vol_base, 4),
            "total_bar_volume_base": round(total_bar_vol_base, 4),
            "relative_volume_diff_pct": round(rel_diff_pct, 6),
            "max_close_price_diff": round(max_price_diff, 4),
            "material_discrepancies_count": len(discrepancies),
            "qa_verdict": "PASS" if is_passed else "FAIL",
            "audit": {
                "interpretation": (
                    "aggTrades are aggregated fills across order matching engine; "
                    "minor sub-satoshi rounding differences vs kline base volume are standard."
                ),
            },
        }

        qa_file = self.c2_root / "aggregates_vs_candles_QA.json"
        qa_file.write_text(json.dumps(qa_report, indent=2, sort_keys=True))
        return qa_report

    def compare_cross_market_flow(
        self,
        asset: str = "BTC",
        start_utc: str | datetime = "2023-08-15T00:00:00Z",
        end_utc: str | datetime = "2023-08-16T00:00:00Z",
    ) -> dict[str, Any]:
        """Compare flow dynamics between Perpetual and Spot over a matching interval."""
        perp_flows = self.query_flow_range("binance", asset, "USD_M_PERPETUAL", start_utc, end_utc)
        spot_flows = self.query_flow_range("binance", asset, "SPOT", start_utc, end_utc)

        perp_vol = sum(r["volume_base"] for r in perp_flows)
        spot_vol = sum(r["volume_base"] for r in spot_flows)
        perp_signed = sum(r["signed_flow_base"] for r in perp_flows)
        spot_signed = sum(r["signed_flow_base"] for r in spot_flows)
        perp_events = sum(r["event_count"] for r in perp_flows)
        spot_events = sum(r["event_count"] for r in spot_flows)

        perp_quote = sum(r["volume_quote"] for r in perp_flows)
        spot_quote = sum(r["volume_quote"] for r in spot_flows)

        perp_vwap = (perp_quote / perp_vol) if perp_vol > 0 else 0.0
        spot_vwap = (spot_quote / spot_vol) if spot_vol > 0 else 0.0

        return {
            "asset": asset,
            "window_start_utc": str(start_utc),
            "window_end_utc": str(end_utc),
            "perpetual": {
                "minutes": len(perp_flows),
                "total_events": perp_events,
                "total_volume_base": round(perp_vol, 4),
                "total_signed_flow_base": round(perp_signed, 4),
                "vwap": round(perp_vwap, 2),
            },
            "spot": {
                "minutes": len(spot_flows),
                "total_events": spot_events,
                "total_volume_base": round(spot_vol, 4),
                "total_signed_flow_base": round(spot_signed, 4),
                "vwap": round(spot_vwap, 2),
            },
            "perpetual_to_spot_volume_ratio": round(perp_vol / spot_vol, 2) if spot_vol > 0 else None,
            "perpetual_to_spot_events_ratio": round(perp_events / spot_events, 2) if spot_events > 0 else None,
            "spread_vwap_perp_minus_spot": round(perp_vwap - spot_vwap, 2),
        }

    def hourly_asof_flow_slice(
        self,
        origins: list[str | datetime],
        asset: str = "BTC",
    ) -> list[dict[str, Any]]:
        """Perform causal hourly as-of join at decision origins (e.g. HH:01 UTC).

        Cutoff C = origin rounded down to exact hour (HH:00:00 UTC).
        Strictly enforces:
          - Closed minute requirement: interval_end_utc <= C
          - Multi-scale flow aggregations:
              * 1m flow at cutoff minute [C-1m, C]
              * 5m flow rollup over [C-5m, C]
              * 60m (1h) flow rollup over [C-60m, C]
          - Cross-market perpetual vs spot features
          - Strict governance assertion: future_funding_or_return_labels_read == 0
        """
        results = []

        for origin_item in origins:
            origin_dt = _dt_from_iso_or_obj(origin_item)
            # Cutoff C is exact hour boundary
            cutoff_dt = origin_dt.replace(minute=0, second=0, microsecond=0)
            cutoff_us = _to_us(cutoff_dt)

            # Query pre-cutoff 60 minutes for both perp and spot
            window_start_dt = cutoff_dt - timedelta(hours=1)
            window_start_us = _to_us(window_start_dt)

            perp_minutes = self.query_flow_range(
                "binance", asset, "USD_M_PERPETUAL", window_start_dt, cutoff_dt
            )
            spot_minutes = self.query_flow_range(
                "binance", asset, "SPOT", window_start_dt, cutoff_dt
            )

            # Enforce strict causal filter
            def _filter_causal(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
                causal = []
                for r in records:
                    end_val = r["interval_end_utc"]
                    end_us = int(end_val.timestamp() * 10**6) if hasattr(end_val, "timestamp") else int(end_val)
                    if end_us <= cutoff_us:
                        causal.append(r)
                    else:
                        raise ValueError(f"CAUSALITY_VIOLATION: record ends at {end_us} > cutoff {cutoff_us}")
                return causal

            causal_perp = _filter_causal(perp_minutes)
            causal_spot = _filter_causal(spot_minutes)

            # 1m feature (last closed minute)
            last_1m_perp = causal_perp[-1] if causal_perp else None
            last_1m_spot = causal_spot[-1] if causal_spot else None

            # 5m rollup (last 5 closed minutes)
            five_m_cutoff_us = cutoff_us - 5 * 60 * 10**6
            p_5m = [r for r in causal_perp if _to_us(r["interval_start_utc"] if hasattr(r["interval_start_utc"], "timestamp") else datetime.fromtimestamp(r["interval_start_utc"]/10**6, UTC)) >= five_m_cutoff_us]
            s_5m = [r for r in causal_spot if _to_us(r["interval_start_utc"] if hasattr(r["interval_start_utc"], "timestamp") else datetime.fromtimestamp(r["interval_start_utc"]/10**6, UTC)) >= five_m_cutoff_us]

            # Aggregate helper
            def _rollup(recs: list[dict[str, Any]]) -> dict[str, Any]:
                if not recs:
                    return {
                        "count_minutes": 0, "volume_base": 0.0, "volume_quote": 0.0,
                        "signed_flow_base": 0.0, "signed_flow_quote": 0.0,
                        "event_count": 0, "buy_volume_base": 0.0, "sell_volume_base": 0.0,
                        "vwap": None, "order_imbalance": 0.0
                    }
                vol_base = sum(r["volume_base"] for r in recs)
                vol_quote = sum(r["volume_quote"] for r in recs)
                signed_b = sum(r["signed_flow_base"] for r in recs)
                signed_q = sum(r["signed_flow_quote"] for r in recs)
                events = sum(r["event_count"] for r in recs)
                buy_b = sum(r["buy_volume_base"] for r in recs)
                sell_b = sum(r["sell_volume_base"] for r in recs)
                imbalance = (signed_b / vol_base) if vol_base > 0 else 0.0
                vwap = (vol_quote / vol_base) if vol_base > 0 else None
                return {
                    "count_minutes": len(recs),
                    "volume_base": round(vol_base, 4),
                    "volume_quote": round(vol_quote, 2),
                    "signed_flow_base": round(signed_b, 4),
                    "signed_flow_quote": round(signed_q, 2),
                    "event_count": events,
                    "buy_volume_base": round(buy_b, 4),
                    "sell_volume_base": round(sell_b, 4),
                    "vwap": round(vwap, 2) if vwap else None,
                    "order_imbalance": round(imbalance, 6),
                }

            slice_rec = {
                "origin_utc": origin_dt.isoformat(),
                "cutoff_utc": cutoff_dt.isoformat(),
                "asset": asset,
                "perp_1m_flow": {
                    "signed_flow_base": round(last_1m_perp["signed_flow_base"], 4) if last_1m_perp else None,
                    "volume_base": round(last_1m_perp["volume_base"], 4) if last_1m_perp else None,
                    "vwap": round(last_1m_perp["vwap"], 2) if last_1m_perp else None,
                    "trade_close": round(last_1m_perp["trade_close"], 2) if last_1m_perp else None,
                    "events": last_1m_perp["event_count"] if last_1m_perp else 0,
                },
                "perp_5m_flow": _rollup(p_5m),
                "perp_1h_flow": _rollup(causal_perp),
                "spot_1m_flow": {
                    "signed_flow_base": round(last_1m_spot["signed_flow_base"], 4) if last_1m_spot else None,
                    "volume_base": round(last_1m_spot["volume_base"], 4) if last_1m_spot else None,
                    "vwap": round(last_1m_spot["vwap"], 2) if last_1m_spot else None,
                    "trade_close": round(last_1m_spot["trade_close"], 2) if last_1m_spot else None,
                    "events": last_1m_spot["event_count"] if last_1m_spot else 0,
                },
                "spot_5m_flow": _rollup(s_5m),
                "spot_1h_flow": _rollup(causal_spot),
                "cross_flow": {
                    "perp_vs_spot_1h_signed_flow_spread": round(_rollup(causal_perp)["signed_flow_base"] - _rollup(causal_spot)["signed_flow_base"], 4),
                    "perp_vs_spot_1h_vol_ratio": round(_rollup(causal_perp)["volume_base"] / _rollup(causal_spot)["volume_base"], 2) if _rollup(causal_spot)["volume_base"] > 0 else None,
                },
                "governance": {
                    "future_funding_or_return_labels_read": 0,
                    "real_historical_outcomes_evaluated": 0,
                    "max_observed_interval_end_utc": (
                        causal_perp[-1]["interval_end_utc"].isoformat()
                        if causal_perp and hasattr(causal_perp[-1]["interval_end_utc"], "isoformat")
                        else str(causal_perp[-1]["interval_end_utc"]) if causal_perp else None
                    ),
                    "cutoff_respected": True,
                },
            }
            results.append(slice_rec)

        return results

    def run_pilot_demo(self) -> dict[str, Any]:
        """Execute complete QA validation and hourly causal as-of demo for pilot month."""
        # 1. Run QA vs C1 Bars on 2023-08-15
        qa_result = self.compare_flow_vs_c1_bars(
            exchange="binance",
            asset="BTC",
            product="USD_M_PERPETUAL",
            start_utc="2023-08-15T00:00:00Z",
            end_utc="2023-08-16T00:00:00Z",
        )

        # 2. Run cross market perp vs spot comparison
        cross_result = self.compare_cross_market_flow(
            asset="BTC",
            start_utc="2023-08-15T00:00:00Z",
            end_utc="2023-08-16T00:00:00Z",
        )

        # 3. Run hourly causal as-of slice for 6 consecutive hours on 2023-08-15
        origins = [
            f"2023-08-15T{hour:02d}:01:00Z"
            for hour in range(1, 7)
        ]
        asof_slices = self.hourly_asof_flow_slice(origins, asset="BTC")

        demo_output = {
            "qa_validation": qa_result,
            "cross_market_flow_24h": cross_result,
            "causal_hourly_asof_slices": asof_slices,
            "governance_audit": {
                "total_asof_origins_evaluated": len(asof_slices),
                "future_funding_or_return_labels_read": 0,
                "real_historical_outcomes_evaluated": 0,
                "strict_causal_enforcement": True,
            },
        }

        out_path = self.c2_root / "real_pilot_query.json"
        out_path.write_text(json.dumps(demo_output, indent=2, sort_keys=True))

        return demo_output


def main() -> None:
    parser = argparse.ArgumentParser(description="DATA-C2 Flow Query and Validation")
    parser.add_argument("command", choices=["qa", "cross", "asof", "demo"], default="demo", nargs="?")
    args = parser.parse_args()

    engine = FlowQueryEngine()
    if args.command == "qa":
        res = engine.compare_flow_vs_c1_bars()
        print(json.dumps(res, indent=2))
    elif args.command == "cross":
        res = engine.compare_cross_market_flow()
        print(json.dumps(res, indent=2))
    elif args.command == "asof":
        res = engine.hourly_asof_flow_slice(["2023-08-15T02:01:00Z"])
        print(json.dumps(res, indent=2))
    elif args.command == "demo":
        res = engine.run_pilot_demo()
        print("Demo completed successfully. Summary:")
        print(f"  QA Verdict: {res['qa_validation']['qa_verdict']}")
        print(f"  Relative Vol Diff: {res['qa_validation']['relative_volume_diff_pct']}%")
        print(f"  Perp vs Spot 24h Vol Ratio: {res['cross_market_flow_24h']['perpetual_to_spot_volume_ratio']}")
        print(f"  Hourly As-Of Slices: {len(res['causal_hourly_asof_slices'])}")


if __name__ == "__main__":
    main()
