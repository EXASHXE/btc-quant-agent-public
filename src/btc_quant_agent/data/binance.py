from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
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
MAX_SOURCE_CLOCK_EXTENSION_MS = 5_000


class BinanceDataError(RuntimeError):
    def __init__(self, message: str, error_class: str = "UNKNOWN", retryable: bool = False):
        super().__init__(message)
        self.error_class = error_class
        self.retryable = retryable


def classify_public_error(exc: BaseException) -> tuple[str, bool]:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return "HTTP_429", True
        if 500 <= exc.code <= 599:
            return "HTTP_5XX", True
        return "HTTP_4XX_NON_RETRYABLE", False
    if isinstance(reason, socket.gaierror):
        return "DNS_ERROR", True
    if isinstance(reason, ssl.SSLError):
        text = str(reason).lower()
        return (
            "TLS_HANDSHAKE_TIMEOUT"
            if "timed out" in text or "handshake" in text
            else "CONNECTION_RESET",
            True,
        )
    if isinstance(reason, (TimeoutError, socket.timeout)):
        text = str(reason).lower()
        return (
            "TLS_HANDSHAKE_TIMEOUT" if "handshake" in text else "CONNECT_TIMEOUT",
            True,
        )
    if isinstance(reason, (ConnectionResetError, BrokenPipeError)):
        return "CONNECTION_RESET", True
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ValueError)):
        return "SCHEMA_ERROR", False
    return "UNKNOWN", False


@dataclass(frozen=True)
class DerivativeCollection:
    collection_started_at_ms: int
    observed_at_ms: int
    snapshot: DerivativesSnapshot
    attempted_fields: tuple[str, ...]
    field_availability: dict[str, bool]
    endpoint_errors: dict[str, str]
    endpoint_telemetry: dict[str, Any] | None = None


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
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            error_class, retryable = classify_public_error(exc)
            raise BinanceDataError(
                f"Binance public data request failed [{error_class}]: {exc}",
                error_class,
                retryable,
            ) from exc

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
        return self.collect_derivatives(symbol, include_order_book=include_order_book).snapshot

    def collect_derivatives(
        self, symbol: str, *, include_order_book: bool = False
    ) -> DerivativeCollection:
        symbol = symbol.upper()
        started = int(time.time() * 1000)
        errors: dict[str, str] = {}
        telemetry: dict[str, Any] = {}

        def valid_payload(name: str, payload: Any) -> bool:
            if name == "funding_mark_index":
                return isinstance(payload, dict) and {
                    "markPrice",
                    "indexPrice",
                    "lastFundingRate",
                    "time",
                }.issubset(payload)
            if name == "open_interest":
                return isinstance(payload, dict) and {"openInterest", "time"}.issubset(payload)
            required = {
                "open_interest_history": "sumOpenInterest",
                "taker": "buySellRatio",
                "long_short": "longShortRatio",
                "basis": "basisRate",
            }
            if name in required:
                return (
                    isinstance(payload, list)
                    and bool(payload)
                    and isinstance(payload[-1], dict)
                    and required[name] in payload[-1]
                    and "timestamp" in payload[-1]
                )
            if name == "order_book":
                return isinstance(payload, dict) and "bids" in payload and "asks" in payload
            return True

        def attempt(name: str, path: str, params: dict[str, Any]) -> Any:
            attempts: list[dict[str, Any]] = []
            for number in range(1, 4):
                attempt_started = time.perf_counter()
                try:
                    payload = self._get(path, params)
                    if not valid_payload(name, payload):
                        latency = round((time.perf_counter() - attempt_started) * 1_000, 3)
                        attempts.append(
                            {
                                "attempt": number,
                                "status": "FAILED",
                                "latency_ms": latency,
                                "error_class": "SCHEMA_ERROR",
                            }
                        )
                        errors[name] = "SCHEMA_ERROR: required response fields absent"
                        telemetry[name] = {
                            "attempt_count": number,
                            "success": False,
                            "final_error_class": "SCHEMA_ERROR",
                            "attempts": attempts,
                        }
                        return None
                    attempts.append(
                        {
                            "attempt": number,
                            "status": "SUCCESS",
                            "latency_ms": round(
                                (time.perf_counter() - attempt_started) * 1_000, 3
                            ),
                            "error_class": None,
                        }
                    )
                    telemetry[name] = {
                        "attempt_count": number,
                        "success": True,
                        "final_error_class": None,
                        "attempts": attempts,
                    }
                    return payload
                except BinanceDataError as exc:
                    attempts.append(
                        {
                            "attempt": number,
                            "status": "FAILED",
                            "latency_ms": round(
                                (time.perf_counter() - attempt_started) * 1_000, 3
                            ),
                            "error_class": exc.error_class,
                        }
                    )
                    if not exc.retryable or number == 3:
                        errors[name] = str(exc)
                        telemetry[name] = {
                            "attempt_count": number,
                            "success": False,
                            "final_error_class": exc.error_class,
                            "attempts": attempts,
                        }
                        return None
                    time.sleep(0.1 * number)
            raise AssertionError("bounded retry loop exhausted unexpectedly")

        premium = attempt("funding_mark_index", "/fapi/v1/premiumIndex", {"symbol": symbol}) or {}
        oi = attempt("open_interest", "/fapi/v1/openInterest", {"symbol": symbol}) or {}
        oi_history = (
            attempt(
                "open_interest_history",
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": "1h", "limit": 2},
            )
            or []
        )
        taker = (
            attempt(
                "taker",
                "/futures/data/takerlongshortRatio",
                {"symbol": symbol, "period": "15m", "limit": 1},
            )
            or []
        )
        long_short = (
            attempt(
                "long_short",
                "/futures/data/globalLongShortAccountRatio",
                {"symbol": symbol, "period": "1h", "limit": 1},
            )
            or []
        )
        basis = (
            attempt(
                "basis",
                "/futures/data/basis",
                {"pair": symbol, "contractType": "PERPETUAL", "period": "5m", "limit": 1},
            )
            or []
        )
        depth = (
            attempt("order_book", "/fapi/v1/depth", {"symbol": symbol, "limit": 20}) or {}
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
        mark_price = float(premium["markPrice"]) if "markPrice" in premium else None
        index_price = float(premium["indexPrice"]) if "indexPrice" in premium else None
        local_observed_at = int(time.time() * 1000)
        snapshot = DerivativesSnapshot(
            observed_at_ms=local_observed_at,
            mark_price=mark_price,
            index_price=index_price,
            premium_bps=(mark_price / index_price - 1.0) * 10_000
            if mark_price is not None and index_price
            else None,
            funding_rate=float(premium["lastFundingRate"])
            if "lastFundingRate" in premium
            else None,
            funding_time_ms=int(premium["time"]) if "time" in premium else None,
            open_interest=float(oi["openInterest"]) if "openInterest" in oi else None,
            open_interest_time_ms=int(oi["time"]) if "time" in oi else None,
            open_interest_change_pct=oi_change,
            taker_buy_sell_ratio=(
                float(latest_taker["buySellRatio"]) if "buySellRatio" in latest_taker else None
            ),
            taker_time_ms=int(latest_taker["timestamp"]) if "timestamp" in latest_taker else None,
            basis_rate=float(latest_basis["basisRate"]) if "basisRate" in latest_basis else None,
            basis_time_ms=int(latest_basis["timestamp"]) if "timestamp" in latest_basis else None,
            long_short_account_ratio=(
                float(latest_long_short["longShortRatio"])
                if "longShortRatio" in latest_long_short
                else None
            ),
            long_short_time_ms=(
                int(latest_long_short["timestamp"]) if "timestamp" in latest_long_short else None
            ),
            order_book_imbalance=imbalance,
            spread_bps=spread_bps,
            order_book_time_ms=int(depth["E"]) if "E" in depth else None,
        )
        availability = {
            "mark_price": snapshot.mark_price is not None,
            "index_price": snapshot.index_price is not None,
            "premium_bps": snapshot.premium_bps is not None,
            "funding_rate": snapshot.funding_rate is not None,
            "open_interest": snapshot.open_interest is not None,
            "open_interest_change_pct": snapshot.open_interest_change_pct is not None,
            "taker_buy_sell_ratio": snapshot.taker_buy_sell_ratio is not None,
            "basis_rate": snapshot.basis_rate is not None,
            "long_short_account_ratio": snapshot.long_short_account_ratio is not None,
            "order_book_imbalance": snapshot.order_book_imbalance is not None,
            "spread_bps": snapshot.spread_bps is not None,
        }
        attempted = (
            "mark_price",
            "index_price",
            "premium_bps",
            "funding_rate",
            "open_interest",
            "open_interest_change_pct",
            "taker_buy_sell_ratio",
            "basis_rate",
            "long_short_account_ratio",
            *(("order_book_imbalance", "spread_bps") if include_order_book else ()),
        )
        source_times = {
            "funding_mark_index": snapshot.funding_time_ms,
            "open_interest": snapshot.open_interest_time_ms,
            "open_interest_history": (
                int(oi_history[-1]["timestamp"]) if oi_history else None
            ),
            "taker": snapshot.taker_time_ms,
            "long_short": snapshot.long_short_time_ms,
            "basis": snapshot.basis_time_ms,
            "order_book": snapshot.order_book_time_ms,
        }
        valid_source_times = [
            value for value in source_times.values() if value is not None
        ]
        observed_at = max([local_observed_at, *valid_source_times])
        if observed_at - local_observed_at > MAX_SOURCE_CLOCK_EXTENSION_MS:
            raise BinanceDataError(
                "source clock exceeds conservative observation bound",
                "SOURCE_CLOCK_SKEW",
                False,
            )
        snapshot = replace(snapshot, observed_at_ms=observed_at)
        telemetry["_observation_clock"] = {
            "success": True,
            "attempt_count": 0,
            "attempts": [],
            "final_error_class": None,
            "local_assembly_time_ms": local_observed_at,
            "effective_observed_at_ms": observed_at,
            "conservative_clock_extension_ms": observed_at - local_observed_at,
        }
        for name, source_timestamp in source_times.items():
            if name in telemetry:
                telemetry[name]["source_timestamp_ms"] = source_timestamp
        return DerivativeCollection(
            started,
            observed_at,
            snapshot,
            attempted,
            availability,
            errors,
            telemetry,
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
