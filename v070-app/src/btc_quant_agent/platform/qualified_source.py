"""Versioned source qualification boundary for the Program B shadow product.

Native ingestion stays closed until the controller supplies an independently
verified, source-specific authority service. A payload or caller-supplied flag
cannot open this boundary.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from .core import fingerprint
from .rc_source import SYMBOLS
from .swing import Contract, INTERVALS

QUALIFICATION_SCHEMA = "V070_B_QUALIFICATION_DIMENSIONS_V1"
NATIVE_STATE = "NATIVE_BLOCKED_AUTHORITY"
BINANCE_VENUE = "BINANCE_USDM_FUTURES"
BINANCE_MARKET_ENDPOINT = "wss://fstream.binance.com/market/stream"
BINANCE_INTERVALS = {"1h": "1H", "4h": "4H", "1d": "1D"}


class QualificationDimensions(Contract):
    schema_version: Literal["V070_B_QUALIFICATION_DIMENSIONS_V1"] = QUALIFICATION_SCHEMA
    implemented: bool
    integrated: bool
    offline_tested: bool
    native_qualified: bool = False
    shadow_qualified: bool = False
    economically_validated: bool = False

class NativeQuarantineRecord(Contract):
    """Unqualified receipt envelope derived from raw bytes; never an authority token."""
    source_id: Literal["BINANCE_USDM_PUBLIC_WS_KLINE_V1"] = "BINANCE_USDM_PUBLIC_WS_KLINE_V1"
    venue: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    interval: Literal["1H", "4H", "1D"]
    open_time_ms: int = Field(gt=0)
    end_time_ms: int = Field(gt=0)
    close_time_ms: int = Field(gt=0)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    explicitly_final: bool
    source_event_ms: int = Field(gt=0)
    received_ms: int = Field(gt=0)
    available_ms: int = Field(gt=0)
    durable_ms: int = Field(gt=0)
    revision: int = Field(ge=0)
    provenance_id: str = Field(min_length=1)
    raw_payload_b64: str = Field(min_length=1)
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_status: Literal["NATIVE_UNQUALIFIED"] = "NATIVE_UNQUALIFIED"
    clock_status: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    clock_uncertainty_ms: int | None = Field(default=None, ge=0)
    clock_probe_age_ms: int | None = Field(default=None, ge=0)

    @property
    def identity(self) -> str:
        return fingerprint([self.source_id, self.venue, self.symbol, self.interval,
                            self.open_time_ms, self.revision])

    @model_validator(mode="after")
    def candle_integrity(self):
        width = INTERVALS[self.interval]
        normalized = self.model_dump(exclude={"raw_payload_b64", "raw_sha256", "normalized_sha256"})
        normalized_bytes = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()
        try:
            raw_bytes = base64.b64decode(self.raw_payload_b64, validate=True)
        except ValueError as exc:
            raise ValueError("NATIVE_RAW_PAYLOAD_ENCODING_INVALID") from exc
        if (hashlib.sha256(raw_bytes).hexdigest() != self.raw_sha256
                or hashlib.sha256(normalized_bytes).hexdigest() != self.normalized_sha256):
            raise ValueError("NATIVE_RAW_OR_NORMALIZED_HASH_MISMATCH")
        if (self.symbol not in SYMBOLS or self.end_time_ms - self.open_time_ms != width
                or self.open_time_ms % width or self.close_time_ms != self.end_time_ms - 1
                or not self.explicitly_final or not self.low <= min(self.open, self.close)
                or not self.high >= max(self.open, self.close) or self.low > self.high
                or not self.end_time_ms <= self.source_event_ms <= self.received_ms
                <= self.available_ms <= self.durable_ms):
            raise ValueError("NATIVE_CANDLE_INTEGRITY_OR_CLOCK_INVALID")
        return self


def _strict_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("NATIVE_DUPLICATE_JSON_KEY")
        output[key] = value
    return output


def _int(value, code):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(code)
    return value


def _number(value, code):
    if not isinstance(value, str):
        raise ValueError(code)
    try:
        result = float(Decimal(value))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(code) from exc
    if not math.isfinite(result):
        raise ValueError(code)
    return result


def decode_binance_kline(raw: bytes, *, venue: str, endpoint: str,
                         received_ms: int, available_ms: int, durable_ms: int,
                         observed_now_ms: int, revision: int = 0,
                         clock_status: str = "UNQUALIFIED",
                         clock_uncertainty_ms: int | None = None,
                         clock_probe_age_ms: int | None = None,
                         expected_symbol: str | None = None,
                         expected_interval: str | None = None) -> NativeQuarantineRecord:
    """Decode raw/combined Binance USD-M kline bytes; never qualifies or admits them."""
    if venue != BINANCE_VENUE or endpoint != BINANCE_MARKET_ENDPOINT:
        raise ValueError("NATIVE_VENUE_OR_ENDPOINT_MISMATCH")
    if clock_status != "UNQUALIFIED":
        raise ValueError("CALLER_CLOCK_STATUS_CANNOT_QUALIFY_SOURCE")
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("NATIVE_RAW_BYTES_REQUIRED")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_strict_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NATIVE_NONFINITE_JSON")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("NATIVE_WIRE_JSON_INVALID") from exc
    stream = None
    if isinstance(value, dict) and set(value) == {"stream", "data"}:
        stream, event = value["stream"], value["data"]
    else:
        event = value
    if not isinstance(event, dict) or event.get("e") != "kline" or not isinstance(event.get("k"), dict):
        raise ValueError("NATIVE_KLINE_EVENT_PROVENANCE_UNKNOWN")
    k = event["k"]
    if not isinstance(k.get("x"), bool) or k["x"] is not True:
        raise ValueError("NATIVE_KLINE_NOT_EXPLICITLY_FINAL")
    symbol = event.get("s")
    interval = k.get("i")
    if (symbol not in SYMBOLS or k.get("s") != symbol
            or interval not in BINANCE_INTERVALS):
        raise ValueError("NATIVE_SYMBOL_OR_INTERVAL_MISMATCH")
    if expected_symbol is None or expected_interval is None:
        raise ValueError("NATIVE_SIGNED_SCOPE_BINDING_MISSING")
    if symbol != expected_symbol or interval != expected_interval:
        raise ValueError("NATIVE_SIGNED_SCOPE_MISMATCH")
    if stream is not None and stream != f"{symbol.lower()}@kline_{interval}":
        raise ValueError("NATIVE_STREAM_SYMBOL_INTERVAL_MISMATCH")
    open_ms = _int(k.get("t"), "NATIVE_OPEN_TIME_INVALID")
    close_inclusive_ms = _int(k.get("T"), "NATIVE_CLOSE_TIME_INVALID")
    end_ms = close_inclusive_ms + 1
    event_ms = _int(event.get("E"), "NATIVE_EVENT_TIME_INVALID")
    times = (received_ms, available_ms, durable_ms, observed_now_ms)
    if any(isinstance(t, bool) or not isinstance(t, int) or t <= 0 for t in times):
        raise ValueError("NATIVE_RECEIPT_CLOCK_INVALID")
    if not end_ms <= event_ms <= received_ms <= available_ms <= durable_ms <= observed_now_ms:
        raise ValueError("NATIVE_EVENT_OR_AVAILABILITY_CLOCK_INVALID")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("NATIVE_REVISION_INVALID")
    if revision != 0:
        raise ValueError("NATIVE_REVISION_PROVENANCE_UNKNOWN")
    interval_name = BINANCE_INTERVALS[interval]
    width = INTERVALS[interval_name]
    if end_ms - open_ms != width or open_ms % width or close_inclusive_ms != end_ms - 1:
        raise ValueError("NATIVE_BAR_ALIGNMENT_INVALID")
    candle = {"symbol": symbol, "interval": interval_name,
              "open_time_ms": open_ms, "close_time_ms": close_inclusive_ms,
              "open": _number(k.get("o"), "NATIVE_OHLCV_INVALID"),
              "high": _number(k.get("h"), "NATIVE_OHLCV_INVALID"),
              "low": _number(k.get("l"), "NATIVE_OHLCV_INVALID"),
              "close": _number(k.get("c"), "NATIVE_OHLCV_INVALID"),
              "volume": _number(k.get("v"), "NATIVE_OHLCV_INVALID")}
    normalized = {"source_id": "BINANCE_USDM_PUBLIC_WS_KLINE_V1",
                  "venue": venue, "instrument": symbol, "endpoint": endpoint,
                  "symbol": symbol, "interval": interval_name,
                  "open_time_ms": open_ms, "end_time_ms": end_ms,
                  "close_time_ms": close_inclusive_ms, "open": candle["open"],
                  "high": candle["high"], "low": candle["low"], "close": candle["close"],
                  "volume": candle["volume"], "explicitly_final": True,
                  "source_event_ms": event_ms, "received_ms": received_ms,
                  "available_ms": available_ms, "durable_ms": durable_ms,
                  "revision": revision, "provenance_id": f"{event_ms}:{open_ms}:{revision}",
                  "source_status": "NATIVE_UNQUALIFIED", "clock_status": "UNQUALIFIED",
                  "clock_uncertainty_ms": clock_uncertainty_ms,
                  "clock_probe_age_ms": clock_probe_age_ms}
    normalized_raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                                allow_nan=False).encode()
    return NativeQuarantineRecord(**normalized, raw_payload_b64=base64.b64encode(raw).decode("ascii"),
                                  raw_sha256=hashlib.sha256(raw).hexdigest(),
                                  normalized_sha256=hashlib.sha256(normalized_raw).hexdigest())


@dataclass(frozen=True)
class NativeAdmissionBlocked(RuntimeError):
    code: str = NATIVE_STATE

    def __str__(self) -> str:
        return self.code


def admit_native(_candidate: NativeQuarantineRecord) -> None:
    """Fail closed: no source-specific verified grant/control service exists."""
    raise NativeAdmissionBlocked()


def source_status(*, exposure: str) -> str:
    if exposure == "SYNTHETIC":
        return "SYNTHETIC"
    if exposure in {"NATIVE", "NATIVE_UNQUALIFIED"}:
        return NATIVE_STATE
    raise ValueError("UNKNOWN_EXPOSURE")
