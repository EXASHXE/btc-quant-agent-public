"""Deterministic fake exchange fixture generator for Binance USDⓈ-M BTCUSDT public streams.

Provides hermetic, reproducible streams of exchange frames without network or credentials.
Supports controlled anomalies for edge-case and robustness verification:
- Continuous depth updates conforming to U/u/pu bridge rules
- Intentional sequence gaps (pu mismatch)
- Stale snapshot races
- Crossed books
- Final vs developing klines
- Mark price stream with estimated funding vs settled funding records
- Ingress clock jumps
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class DeterministicExchangeFixture:
    """Hermetic synthetic Binance USDⓈ-M exchange frame generator."""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        base_price: Decimal = Decimal("65000.00"),
        start_time_ms: int = 1728720000000,
        epoch: str = "epoch-fixture-001",
    ) -> None:
        self.symbol = symbol
        self.base_price = base_price
        self.current_time_ms = start_time_ms
        self.epoch = epoch
        self._trade_seq = 100000
        self._depth_update_id = 500000000
        self._last_depth_u = self._depth_update_id

    def generate_kline_frame(
        self,
        interval: str = "1m",
        closed: bool = False,
        price_offset: Decimal = Decimal("0.00"),
    ) -> dict[str, Any]:
        """Generate a public kline stream frame."""
        t_open = (self.current_time_ms // 60_000) * 60_000
        t_close = t_open + 59_999
        c_price = self.base_price + price_offset
        o_price = self.base_price
        h_price = max(o_price, c_price) + Decimal("15.50")
        l_price = min(o_price, c_price) - Decimal("12.25")
        vol = Decimal("142.85")
        taker_vol = Decimal("71.42")

        return {
            "e": "kline",
            "E": self.current_time_ms,
            "s": self.symbol,
            "k": {
                "t": t_open,
                "T": t_close,
                "s": self.symbol,
                "i": interval,
                "f": self._trade_seq,
                "L": self._trade_seq + 50,
                "o": str(o_price),
                "c": str(c_price),
                "h": str(h_price),
                "l": str(l_price),
                "v": str(vol),
                "n": 51,
                "x": closed,
                "q": str(vol * c_price),
                "V": str(taker_vol),
                "Q": str(taker_vol * c_price),
                "B": "0",
            },
        }

    def generate_mark_price_frame(
        self,
        estimated_funding_rate: str = "0.00010000",
        next_funding_time_ms: int | None = None,
    ) -> dict[str, Any]:
        """Generate a public mark price stream frame."""
        if next_funding_time_ms is None:
            # next 8-hour boundary
            next_funding_time_ms = ((self.current_time_ms // 28_800_000) + 1) * 28_800_000
        mark_price = str(self.base_price)
        index_price = str(self.base_price - Decimal("1.25"))

        return {
            "e": "markPriceUpdate",
            "E": self.current_time_ms,
            "s": self.symbol,
            "p": mark_price,
            "i": index_price,
            "P": mark_price,
            "r": estimated_funding_rate,
            "T": next_funding_time_ms,
        }

    def generate_agg_trade_frame(
        self,
        price_offset: Decimal = Decimal("0.00"),
        quantity: Decimal = Decimal("0.150"),
        buyer_is_maker: bool = False,
    ) -> dict[str, Any]:
        """Generate a public aggregate trade frame."""
        self._trade_seq += 1
        p = self.base_price + price_offset
        return {
            "e": "aggTrade",
            "E": self.current_time_ms,
            "s": self.symbol,
            "a": self._trade_seq,
            "p": str(p),
            "q": str(quantity),
            "f": self._trade_seq * 2,
            "l": self._trade_seq * 2 + 1,
            "T": self.current_time_ms - 2,
            "m": buyer_is_maker,
        }

    def generate_depth_snapshot_frame(
        self,
        levels: int = 20,
        spread: Decimal = Decimal("1.00"),
        tick_size: Decimal = Decimal("0.50"),
        last_update_id: int | None = None,
    ) -> dict[str, Any]:
        """Generate a public REST depth snapshot frame."""
        if last_update_id is None:
            last_update_id = self._depth_update_id
        self._last_depth_u = last_update_id

        best_bid = self.base_price - (spread / Decimal(2))
        best_ask = self.base_price + (spread / Decimal(2))

        bids: list[list[str]] = []
        asks: list[list[str]] = []

        for i in range(levels):
            bid_p = best_bid - (tick_size * Decimal(i))
            ask_p = best_ask + (tick_size * Decimal(i))
            bid_q = Decimal("1.500") + (Decimal("0.1") * Decimal(i))
            ask_q = Decimal("1.200") + (Decimal("0.1") * Decimal(i))
            bids.append([str(bid_p), str(bid_q)])
            asks.append([str(ask_p), str(ask_q)])

        return {
            "lastUpdateId": last_update_id,
            "E": self.current_time_ms,
            "T": self.current_time_ms - 1,
            "bids": bids,
            "asks": asks,
        }

    def generate_depth_delta_frame(
        self,
        span: int = 5,
        force_gap: bool = False,
        force_pu: int | None = None,
        bids_update: list[tuple[str, str]] | None = None,
        asks_update: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Generate a public differential depth stream frame."""
        prev_u = self._last_depth_u
        if force_gap:
            pu = prev_u + 999  # deliberate gap
        elif force_pu is not None:
            pu = force_pu
        else:
            pu = prev_u

        first_u = prev_u + 1
        final_u = first_u + span
        self._last_depth_u = final_u

        b_payload = (
            [[p, q] for p, q in bids_update]
            if bids_update is not None
            else [[str(self.base_price - Decimal("0.50")), "2.500"]]
        )
        a_payload = (
            [[p, q] for p, q in asks_update]
            if asks_update is not None
            else [[str(self.base_price + Decimal("0.50")), "2.800"]]
        )

        return {
            "e": "depthUpdate",
            "E": self.current_time_ms,
            "T": self.current_time_ms - 1,
            "s": self.symbol,
            "U": first_u,
            "u": final_u,
            "pu": pu,
            "b": b_payload,
            "a": a_payload,
        }

    def generate_settled_funding_frame(
        self,
        funding_rate: str = "0.00010000",
        funding_time_ms: int | None = None,
        mark_price: str | None = None,
    ) -> dict[str, Any]:
        """Generate an official settled funding REST item."""
        if funding_time_ms is None:
            funding_time_ms = (self.current_time_ms // 28_800_000) * 28_800_000
        if mark_price is None:
            mark_price = str(self.base_price)

        return {
            "symbol": self.symbol,
            "fundingRate": funding_rate,
            "fundingTime": funding_time_ms,
            "markPrice": mark_price,
        }
