"""Feature-only UTC HH:01 as-of example; never reads return labels."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def _time_us(value: datetime) -> int:
    return int(value.timestamp() * 10**6)


def _load(partitions: list[dict[str, Any]], *, asset: str, exchange: str,
          product: str, table: str) -> dict[int, dict[str, Any]]:
    selected = [x for x in partitions if x["asset"] == asset and x["exchange"] == exchange
                and x["product"] == product and x["table"] == table]
    result = {}
    for item in selected:
        for row in pq.ParquetFile(item["partition_path"]).iter_batches(batch_size=512, use_threads=False):
            for value in row.to_pylist():
                t = _time_us(value["interval_start_utc"])
                if t in result:
                    raise ValueError("DUPLICATE_SAMPLE_TIMESTAMP")
                result[t] = value
    return result


def asof_example(partitions: list[dict[str, Any]], *, start_utc: str = "2026-04-02T01:01:00+00:00",
                 hours: int = 12) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not 1 <= hours <= 48:
        raise ValueError("ASOF_ORIGIN_BUDGET_INVALID")
    start = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
    if start.tzinfo is None or start.minute != 1 or start.second:
        raise ValueError("ASOF_ORIGIN_NOT_HH01_UTC")
    data = {}
    for asset in ("BTC", "ETH"):
        for exchange, product in (("binance", "USD_M_PERPETUAL"), ("binance", "SPOT"),
                                  ("okx", "OKX_SWAP"), ("okx", "SPOT")):
            data[asset, exchange, product] = _load(partitions, asset=asset, exchange=exchange,
                                                    product=product, table="bars")
        data[asset, "oi"] = _load(partitions, asset=asset, exchange="binance",
                                   product="USD_M_PERPETUAL", table="position_state")
        data[asset, "funding"] = _load(partitions, asset=asset, exchange="binance",
                                        product="USD_M_PERPETUAL", table="funding_settlements")
    result = []
    one_minute = 60 * 10**6
    for i in range(hours):
        origin = start + timedelta(hours=i)
        cutoff_us = _time_us(origin - timedelta(minutes=1))
        last_open = cutoff_us - 2 * one_minute
        for asset in ("BTC", "ETH"):
            perp = data[asset, "binance", "USD_M_PERPETUAL"]
            spot = data[asset, "binance", "SPOT"]
            okx = data[asset, "okx", "OKX_SWAP"]
            oi = data[asset, "oi"]
            funding = data[asset, "funding"]
            x_times = range(cutoff_us - 86460 * 10**6, cutoff_us - one_minute, one_minute)
            x_complete = all(t in perp and t in spot and
                             _time_us(perp[t]["interval_end_utc"]) < cutoff_us and
                             _time_us(spot[t]["interval_end_utc"]) < cutoff_us for t in x_times)
            candidates = [t for t in oi if cutoff_us - 600 * 10**6 <= t <= cutoff_us - 300 * 10**6]
            z_t = max(candidates, default=None)
            z_ready = z_t is not None and z_t - 4 * 3600 * 10**6 in oi
            same_minute = last_open in perp and last_open in okx and \
                _time_us(perp[last_open]["interval_end_utc"]) < cutoff_us and \
                _time_us(okx[last_open]["interval_end_utc"]) < cutoff_us
            settled = [t for t in funding if t <= cutoff_us]
            latest_funding = max(settled, default=None)
            blockers = []
            if not x_complete:
                blockers.append("BINANCE_X_24H_INCOMPLETE")
            if not z_ready:
                blockers.append("BINANCE_OI_4H_EXACT_PREDECESSOR_UNAVAILABLE")
            if not same_minute:
                blockers.append("CROSS_VENUE_PRIOR_CLOSED_MINUTE_UNAVAILABLE")
            if asset == "ETH":
                blockers.append("ETH_CONTROL_ONLY_NOT_CANDIDATE_A")
            ready = not blockers
            result.append({"origin_utc": origin.isoformat(), "cutoff_utc": (origin - timedelta(minutes=1)).isoformat(),
                "asset": asset, "action": "FEATURE_READY_NOT_TRADE" if ready else "NO_ACTION",
                "feature_ready": ready, "blockers": blockers, "x_24h_complete": x_complete,
                "x_last_closed_bar_start_utc": datetime.fromtimestamp(last_open / 10**6, UTC).isoformat(),
                "z_native_sample_utc": datetime.fromtimestamp(z_t / 10**6, UTC).isoformat() if z_t else None,
                "z_exact_4h_predecessor": z_ready, "receiver_first_known_at": None,
                "receiver_pit": "PIT_UNKNOWN", "source_not_admitted": True,
                "binance_perp_prior_close": perp[last_open]["close"] if same_minute else None,
                "okx_swap_prior_close": okx[last_open]["close"] if same_minute else None,
                "binance_minus_okx_usdt_per_base": (perp[last_open]["close"] - okx[last_open]["close"])
                    if same_minute else None,
                "latest_prior_funding_settlement_utc": datetime.fromtimestamp(latest_funding / 10**6, UTC).isoformat()
                    if latest_funding else None,
                "latest_prior_funding_rate": funding[latest_funding]["funding_rate"] if latest_funding else None,
                "future_funding_or_return_labels_read": 0})
    summary = {"scheduled_origin_asset_rows": len(result),
               "feature_ready_rows": sum(r["feature_ready"] for r in result),
               "no_action_rows": sum(r["action"] == "NO_ACTION" for r in result),
               "blocker_counts": dict(sorted(Counter(x for r in result for x in r["blockers"]).items())),
               "real_outcome_labels_read": 0, "funding_feature_rule": "ACTUAL_SETTLEMENT_T <= C_ONLY",
               "bar_feature_rule": "INTERVAL_END_STRICTLY_BEFORE_C",
               "event_clock_is_not_receiver_clock": True}
    return result, summary
