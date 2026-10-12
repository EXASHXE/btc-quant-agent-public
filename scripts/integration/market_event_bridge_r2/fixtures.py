"""Deterministic Fixture Generator: Multi-scenario high-velocity exchange simulator.

Produces reproducible 10-30 minute streams of Binance USDⓈ-M market events
(1s Mark ticks, trades, 100ms diff depth, L2 snapshots, 1m klines, and settled funding).
Used for deterministic testing, queue backpressure, latency profiling, and replay.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass
class ScenarioMetrics:
    scenario_name: str
    total_frames: int
    duration_minutes: int
    seed: int
    depth_deltas_count: int
    agg_trades_count: int
    mark_ticks_count: int
    klines_count: int
    funding_records_count: int


class BridgeFixtureGenerator:
    """Generates deterministic synthetic USDⓈ-M market frames across multiple scenarios."""

    def __init__(self, seed: int = 20261012, symbol: str = "BTCUSDT") -> None:
        self.seed = seed
        self.symbol = symbol
        self._rng = random.Random(seed)

    def generate_scenario(
        self,
        scenario_name: str = "happy_path_10m",
        base_time_ms: int = 1728720000000,  # 2024-10-12 08:00:00 UTC
    ) -> tuple[list[dict[str, Any]], ScenarioMetrics]:
        """Generate complete ordered sequence of exchange frames for named scenario."""
        self._rng = random.Random(self.seed)

        if scenario_name == "happy_path_10m":
            duration_minutes = 10
            drop_prob = 0.0
        elif scenario_name == "jitter_and_drops_15m":
            duration_minutes = 15
            drop_prob = 0.05
        elif scenario_name == "high_frequency_stress_30m":
            duration_minutes = 30
            drop_prob = 0.01
        else:
            duration_minutes = 10
            drop_prob = 0.0

        frames: list[dict[str, Any]] = []
        base_price = 64000.0

        depth_count = 0
        agg_count = 0
        mark_count = 0
        kline_count = 0
        funding_count = 0

        # Initial depth snapshot
        snap_id = 1_000_000
        snap_frame = {
            "lastUpdateId": snap_id,
            "bids": [[f"{base_price - 0.5 * i:.2f}", f"{1.0 + 0.1 * i:.3f}"] for i in range(1, 25)],
            "asks": [[f"{base_price + 0.5 * i:.2f}", f"{1.0 + 0.1 * i:.3f}"] for i in range(1, 25)],
            "symbol": self.symbol,
            "E": base_time_ms,
            "T": base_time_ms,
        }
        frames.append(snap_frame)

        prev_u = snap_id

        for minute_idx in range(duration_minutes):
            minute_open_ms = base_time_ms + minute_idx * 60_000
            minute_close_ms = minute_open_ms + 59_999

            minute_open_p = base_price
            minute_high_p = base_price
            minute_low_p = base_price
            minute_vol = 0.0

            # 60 seconds per minute
            for sec in range(60):
                sec_ms = minute_open_ms + sec * 1000

                # 1. Mark price tick every second (unless dropped in jitter scenario)
                if self._rng.random() >= drop_prob:
                    mark_drift = self._rng.uniform(-2.0, 2.0)
                    mark_p = round(base_price + mark_drift, 2)
                    mark_frame = {
                        "e": "markPriceUpdate",
                        "E": sec_ms,
                        "s": self.symbol,
                        "p": f"{mark_p:.2f}",
                        "i": f"{mark_p + 0.5:.2f}",
                        "r": "0.00010000",
                        "T": sec_ms,
                    }
                    frames.append(mark_frame)
                    mark_count += 1

                    # Contemporaneous settled funding record at start of session (minute 0)
                    if funding_count == 0:
                        funding_frame = {
                            "symbol": self.symbol,
                            "fundingRate": "0.00010000",
                            "fundingTime": base_time_ms,
                        }
                        frames.append(funding_frame)
                        funding_count += 1

                # 2. Agg trade
                trade_p = round(base_price + self._rng.uniform(-1.5, 1.5), 2)
                trade_qty = round(self._rng.uniform(0.01, 2.5), 4)
                minute_high_p = max(minute_high_p, trade_p)
                minute_low_p = min(minute_low_p, trade_p)
                minute_vol += trade_qty
                base_price = trade_p

                trade_frame = {
                    "e": "aggTrade",
                    "E": sec_ms + 200,
                    "s": self.symbol,
                    "a": 5000000 + minute_idx * 60 + sec,
                    "p": f"{trade_p:.2f}",
                    "q": f"{trade_qty:.4f}",
                    "f": 10000000 + (minute_idx * 60 + sec) * 2,
                    "l": 10000000 + (minute_idx * 60 + sec) * 2 + 1,
                    "T": sec_ms + 200,
                    "m": self._rng.choice([True, False]),
                }
                frames.append(trade_frame)
                agg_count += 1

                # 3. Depth delta update
                u_id = prev_u + 1
                U_id = prev_u + 1
                pu_id = prev_u
                prev_u = u_id

                delta_frame = {
                    "e": "depthUpdate",
                    "E": sec_ms + 500,
                    "T": sec_ms + 500,
                    "s": self.symbol,
                    "U": U_id,
                    "u": u_id,
                    "pu": pu_id,
                    "b": [
                        [f"{base_price - 0.5:.2f}", f"{self._rng.uniform(0.5, 5.0):.3f}"],
                        [f"{base_price - 1.0:.2f}", f"{self._rng.uniform(0.5, 5.0):.3f}"],
                    ],
                    "a": [
                        [f"{base_price + 0.5:.2f}", f"{self._rng.uniform(0.5, 5.0):.3f}"],
                        [f"{base_price + 1.0:.2f}", f"{self._rng.uniform(0.5, 5.0):.3f}"],
                    ],
                }
                frames.append(delta_frame)
                depth_count += 1

            # End of minute kline frame
            minute_close_p = base_price
            kline_frame = {
                "e": "kline",
                "E": minute_close_ms,
                "s": self.symbol,
                "k": {
                    "t": minute_open_ms,
                    "T": minute_close_ms,
                    "s": self.symbol,
                    "i": "1m",
                    "f": 10000000 + minute_idx * 120,
                    "L": 10000000 + (minute_idx + 1) * 120,
                    "o": f"{minute_open_p:.2f}",
                    "c": f"{minute_close_p:.2f}",
                    "h": f"{minute_high_p:.2f}",
                    "l": f"{minute_low_p:.2f}",
                    "v": f"{minute_vol:.4f}",
                    "n": 60,
                    "x": True,
                    "q": f"{minute_vol * minute_close_p:.2f}",
                    "V": f"{minute_vol * 0.5:.4f}",
                    "Q": f"{minute_vol * minute_close_p * 0.5:.2f}",
                    "B": "0",
                },
            }
            frames.append(kline_frame)
            kline_count += 1

        metrics = ScenarioMetrics(
            scenario_name=scenario_name,
            total_frames=len(frames),
            duration_minutes=duration_minutes,
            seed=self.seed,
            depth_deltas_count=depth_count,
            agg_trades_count=agg_count,
            mark_ticks_count=mark_count,
            klines_count=kline_count,
            funding_records_count=funding_count,
        )

        return frames, metrics
