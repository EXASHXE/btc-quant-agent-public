from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..config import DataConfig
from ..domain import Candle, DerivativesSnapshot

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}


class BinanceDataError(RuntimeError):
    pass


@dataclass
class BinancePublicClient:
    config: DataConfig

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode(params or {})
        url = f"{self.config.rest_base_url.rstrip('/')}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": "btc-quant-agent/0.2.1"})
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.request_timeout_seconds
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BinanceDataError(f"Binance public data request failed: {exc}") from exc

    def server_time_ms(self) -> int:
        payload = self._get("/fapi/v1/time")
        return int(payload["serverTime"])

    def klines(self, symbol: str, interval: str, limit: int = 500) -> list[Candle]:
        now_ms = self.server_time_ms()
        rows = self._get(
            "/fapi/v1/klines", {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        )
        return self._parse_klines(rows, symbol, interval, now_ms)

    def _parse_klines(
        self, rows: list[list[Any]], symbol: str, interval: str, latest_close_ms: int
    ) -> list[Candle]:
        candles: list[Candle] = []
        for row in rows:
            close_time = int(row[6])
            if close_time >= latest_close_ms:
                continue
            candles.append(
                Candle(
                    symbol=symbol.upper(),
                    interval=interval,
                    open_time_ms=int(row[0]),
                    close_time_ms=close_time,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    quote_volume=float(row[7]),
                    trades=int(row[8]),
                    taker_buy_base_volume=float(row[9]),
                    closed=True,
                )
            )
        return candles

    def historical_klines(
        self, symbol: str, interval: str, start_time_ms: int, end_time_ms: int
    ) -> list[Candle]:
        if interval not in INTERVAL_MS:
            raise ValueError(f"unsupported interval: {interval}")
        if end_time_ms <= start_time_ms:
            raise ValueError("end_time_ms must be after start_time_ms")
        cursor = start_time_ms
        rows: list[list[Any]] = []
        while cursor <= end_time_ms:
            page = self._get(
                "/fapi/v1/klines",
                {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": cursor,
                    "endTime": end_time_ms,
                    "limit": 1500,
                },
            )
            if not page:
                break
            rows.extend(page)
            next_cursor = int(page[-1][0]) + INTERVAL_MS[interval]
            if next_cursor <= cursor:
                raise BinanceDataError("historical pagination did not advance")
            cursor = next_cursor
            if len(page) < 1500:
                break
            time.sleep(0.05)
        unique = {int(row[0]): row for row in rows}
        ordered = [unique[key] for key in sorted(unique)]
        return self._parse_klines(ordered, symbol, interval, end_time_ms + 1)

    def derivatives(self, symbol: str, *, include_order_book: bool = False) -> DerivativesSnapshot:
        symbol = symbol.upper()
        observed_at = int(time.time() * 1000)
        premium = self._get("/fapi/v1/premiumIndex", {"symbol": symbol})
        oi = self._optional_get("/fapi/v1/openInterest", {"symbol": symbol}) or {}
        oi_history = self._optional_get(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": "1h", "limit": 2},
        ) or []
        taker = self._optional_get(
            "/futures/data/takerlongshortRatio", {"symbol": symbol, "period": "15m", "limit": 1}
        ) or []
        long_short = self._optional_get(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": "1h", "limit": 1},
        ) or []
        basis = self._optional_get(
            "/futures/data/basis",
            {"pair": symbol, "contractType": "PERPETUAL", "period": "5m", "limit": 1},
        ) or []
        depth = (
            self._optional_get("/fapi/v1/depth", {"symbol": symbol, "limit": 20}) or {}
            if include_order_book
            else {}
        )
        latest_taker = taker[-1] if taker else {}
        latest_long_short = long_short[-1] if long_short else {}
        latest_basis = basis[-1] if basis else {}
        oi_change = None
        if len(oi_history) >= 2:
            prior_oi = float(oi_history[-2].get("sumOpenInterest", 0.0))
            current_oi = float(oi_history[-1].get("sumOpenInterest", 0.0))
            oi_change = current_oi / prior_oi - 1.0 if prior_oi else None
        bids = depth.get("bids", [])
        asks = depth.get("asks", [])
        best_bid = float(bids[0][0]) if bids else None
        best_ask = float(asks[0][0]) if asks else None
        bid_notional = sum(float(price) * float(quantity) for price, quantity in bids[:5])
        ask_notional = sum(float(price) * float(quantity) for price, quantity in asks[:5])
        depth_total = bid_notional + ask_notional
        imbalance = (bid_notional - ask_notional) / depth_total if depth_total else None
        spread_bps = None
        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2.0
            spread_bps = (best_ask - best_bid) / mid * 10_000 if mid else None
        mark_price = float(premium["markPrice"])
        index_price = float(premium["indexPrice"])
        return DerivativesSnapshot(
            observed_at_ms=observed_at,
            mark_price=mark_price,
            index_price=index_price,
            premium_bps=(mark_price / index_price - 1.0) * 10_000 if index_price else None,
            funding_rate=float(premium["lastFundingRate"]),
            funding_time_ms=int(premium.get("time", observed_at)),
            open_interest=float(oi["openInterest"]) if "openInterest" in oi else None,
            open_interest_time_ms=int(oi.get("time", observed_at)) if oi else None,
            open_interest_change_pct=oi_change,
            taker_buy_sell_ratio=(
                float(latest_taker["buySellRatio"]) if "buySellRatio" in latest_taker else None
            ),
            taker_time_ms=int(latest_taker.get("timestamp", observed_at)),
            basis_rate=float(latest_basis["basisRate"]) if "basisRate" in latest_basis else None,
            basis_time_ms=int(latest_basis.get("timestamp", observed_at)) if latest_basis else None,
            long_short_account_ratio=(
                float(latest_long_short["longShortRatio"])
                if "longShortRatio" in latest_long_short
                else None
            ),
            long_short_time_ms=(
                int(latest_long_short.get("timestamp", observed_at)) if latest_long_short else None
            ),
            order_book_imbalance=imbalance,
            spread_bps=spread_bps,
            order_book_time_ms=int(depth.get("E", observed_at)) if depth else None,
        )

    def _optional_get(self, path: str, params: dict[str, Any]) -> Any | None:
        try:
            return self._get(path, params)
        except BinanceDataError:
            return None

    def mark_price(self, symbol: str) -> float:
        payload = self._get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
        return float(payload["markPrice"])

    def symbol_filters(self, symbol: str) -> dict[str, float]:
        payload = self._get("/fapi/v1/exchangeInfo")
        for item in payload.get("symbols", []):
            if item.get("symbol") != symbol.upper():
                continue
            filters = {entry["filterType"]: entry for entry in item.get("filters", [])}
            lot = filters.get("LOT_SIZE", {})
            price = filters.get("PRICE_FILTER", {})
            minimum = filters.get("MIN_NOTIONAL", {})
            return {
                "step_size": float(lot.get("stepSize", 0.0)),
                "min_quantity": float(lot.get("minQty", 0.0)),
                "tick_size": float(price.get("tickSize", 0.0)),
                "min_notional": float(minimum.get("notional", 0.0)),
            }
        raise BinanceDataError(f"symbol filters not found: {symbol}")

    def connectivity(self) -> bool:
        self._get("/fapi/v1/ping")
        return True
