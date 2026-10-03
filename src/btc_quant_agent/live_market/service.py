"""Lightweight Live V1 market stream service."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

from .models import MarketObservationV1


class MarketStreamService:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        ws_base_url: str = "wss://fstream.binance.com",
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.ws_base_url = ws_base_url.rstrip("/")
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

        self._mark_price: float = 0.0
        self._best_bid: float = 0.0
        self._best_ask: float = 0.0
        self._kline_close: float = 0.0
        self._kline_open_time: int = 0
        self._kline_close_time: int = 0
        self._source_timestamp_ms: int = 0
        self._receipt_timestamp_ms: int = 0
        self._component_times: dict[str, tuple[int, int]] = {}
        self._connected: bool = False
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_simulated(
        self,
        mark_price: float,
        best_bid: float,
        best_ask: float,
        kline_close: float,
        now_ms: int | None = None,
        kline_open_time_ms: int | None = None,
        kline_close_time_ms: int | None = None,
    ) -> None:
        now = self.clock_ms() if now_ms is None else now_ms
        self._mark_price = mark_price
        self._best_bid = best_bid
        self._best_ask = best_ask
        self._kline_close = kline_close
        self._kline_open_time = kline_open_time_ms or (now - 60_000)
        self._kline_close_time = kline_close_time_ms or now
        self._source_timestamp_ms = now
        self._receipt_timestamp_ms = now
        self._component_times = {name: (now, now) for name in ("mark", "book", "kline")}
        self._connected = True

    def latest_observation(self, now_ms: int | None = None) -> MarketObservationV1 | None:
        if (
            self._mark_price <= 0
            or self._best_bid <= 0
            or self._best_ask <= 0
            or self._kline_close <= 0
        ):
            return None
        mid = (self._best_bid + self._best_ask) / 2.0
        spread_bps = ((self._best_ask - self._best_bid) / mid) * 10_000 if mid > 0 else 0.0
        return MarketObservationV1.build(
            symbol=self.symbol,
            mark_price=self._mark_price,
            best_bid=self._best_bid,
            best_ask=self._best_ask,
            kline_1m_close=self._kline_close,
            kline_1m_open_time_ms=self._kline_open_time,
            kline_1m_close_time_ms=self._kline_close_time,
            source_timestamp_ms=self._source_timestamp_ms,
            receipt_timestamp_ms=self._receipt_timestamp_ms,
            mark_source_timestamp_ms=self._component_times.get("mark", (None, None))[0],
            mark_receipt_timestamp_ms=self._component_times.get("mark", (None, None))[1],
            book_source_timestamp_ms=self._component_times.get("book", (None, None))[0],
            book_receipt_timestamp_ms=self._component_times.get("book", (None, None))[1],
            kline_source_timestamp_ms=self._component_times.get("kline", (None, None))[0],
            kline_receipt_timestamp_ms=self._component_times.get("kline", (None, None))[1],
            stream_connected=self._connected,
            spread_bps=max(0.0, spread_bps),
        )

    def handle_message(self, raw_message: str | bytes, receipt_ms: int) -> None:
        data = json.loads(raw_message)
        payload = data.get("data", data)
        event_type = payload.get("e")
        component = {"markPriceUpdate": "mark", "bookTicker": "book", "kline": "kline"}.get(event_type)
        if component is None or "E" not in payload:
            return
        required = {"mark": ("p",), "book": ("b", "a"), "kline": ("c", "t", "T")}
        values = payload.get("k", {}) if component == "kline" else payload
        if not isinstance(values, dict) or any(key not in values for key in required[component]):
            return
        if component == "mark":
            mark_price = float(values["p"])
        elif component == "book":
            best_bid = float(values["b"])
            best_ask = float(values["a"])
        else:
            kline_close = float(values["c"])
            kline_open_time = int(values["t"])
            kline_close_time = int(values["T"])
        source_ms = int(payload["E"])
        if source_ms > receipt_ms or source_ms < self._component_times.get(component, (0, 0))[0]:
            return
        self._component_times[component] = (source_ms, receipt_ms)
        self._source_timestamp_ms = source_ms
        self._receipt_timestamp_ms = receipt_ms

        if event_type == "markPriceUpdate":
            self._mark_price = mark_price
        elif event_type == "bookTicker":
            self._best_bid = best_bid
            self._best_ask = best_ask
        elif event_type == "kline":
            self._kline_close = kline_close
            self._kline_open_time = kline_open_time
            self._kline_close_time = kline_close_time

    async def run_stream(self) -> None:
        import websockets

        sym = self.symbol.lower()
        url = f"{self.ws_base_url}/stream?streams={sym}@markPrice@1s/{sym}@kline_1m/{sym}@bookTicker"
        backoff = 1.0

        while not self._stop_event.is_set():
            try:
                async for socket in websockets.connect(url, open_timeout=15):
                    self._connected = True
                    backoff = 1.0
                    async for message in socket:
                        if self._stop_event.is_set():
                            break
                        now = self.clock_ms()
                        self.handle_message(message, now)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001 - retry with backoff
                self._connected = False
                await asyncio.sleep(min(10.0, backoff))
                backoff = min(10.0, backoff * 1.5)
            finally:
                self._connected = False

    def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run_stream())

    def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
