"""Provider-neutral observations. Payloads never confer source authorization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..core import Candle, DataProvenance, ExecutableQuote, InstrumentSpec, dec, fingerprint


@dataclass(frozen=True)
class Receipt:
    provider: str
    channel: str
    instrument_id: str
    received_ts: int | None
    available_ts: int | None
    payload_json: str
    exposure: str = "CALLER_SUPPLIED_UNVERIFIED"
    error: str | None = None

    @classmethod
    def make(
        cls,
        provider: str,
        channel: str,
        instrument_id: str,
        received_ts: int | None,
        available_ts: int | None,
        payload: Any,
        *,
        exposure: str = "CALLER_SUPPLIED_UNVERIFIED",
        error: str | None = None,
    ) -> Receipt:
        return cls(
            provider,
            channel,
            instrument_id,
            received_ts,
            available_ts,
            json.dumps(payload, sort_keys=True, allow_nan=False),
            exposure,
            error,
        )

    @property
    def id(self) -> str:
        return fingerprint(self)

    @property
    def payload(self) -> Any:
        return json.loads(self.payload_json)

    def provenance(self, event_ts: Any) -> DataProvenance:
        if isinstance(event_ts, str) and event_ts.isdigit():
            event_ts = int(event_ts)
        if type(event_ts) is not int or event_ts <= 0:
            raise ValueError("EXCHANGE_EVENT_TIME_UNKNOWN")
        if type(self.received_ts) is not int or type(self.available_ts) is not int:
            raise ValueError("RECEIVER_OR_AVAILABILITY_TIME_UNKNOWN")
        p = DataProvenance(
            self.provider,
            self.id,
            event_ts,
            self.received_ts,
            self.available_ts,
            self.exposure,
            self.exposure == "SYNTHETIC",
        )
        # A parser can normalize unadmitted data, but cannot manufacture missing clocks.
        if not 0 < event_ts <= self.received_ts <= self.available_ts:
            raise ValueError("SOURCE_CLOCK_ORDER_INVALID")
        return p


@dataclass(frozen=True)
class InstrumentRecord:
    spec: InstrumentSpec
    venue_symbol: str
    active: bool
    received_ts: int
    available_ts: int
    receipt_id: str
    exposure: str
    # Static metadata has no invented exchange-event timestamp.


@dataclass(frozen=True)
class CandleRecord:
    candle: Candle
    provenance: DataProvenance


@dataclass(frozen=True)
class FieldObservation:
    name: str
    value: float
    unit: str
    provenance: DataProvenance

    def __post_init__(self) -> None:
        dec(self.value)


@dataclass(frozen=True)
class ProviderBatch:
    provider: str
    decision_ts: int
    receipts: tuple[Receipt, ...]
    fixture_id: str | None = None

    @property
    def id(self) -> str:
        return fingerprint(self)


@dataclass(frozen=True)
class NormalizedSymbol:
    symbol: str
    instrument: InstrumentRecord | None
    candles: tuple[CandleRecord, ...]
    quote: ExecutableQuote | None
    observations: tuple[FieldObservation, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedSnapshot:
    id: str
    provider: str
    decision_ts: int
    exposure: str
    fixture_id: str | None
    symbols: tuple[NormalizedSymbol, ...]
    receipt_ids: tuple[str, ...]


class MarketDataProvider(Protocol):
    def snapshot(self, bar: int, *, response_delay_minutes: int = 0) -> ProviderBatch: ...


class ActivationDenied(RuntimeError):
    pass


class PublicSource:
    """The integration seam has no network transport or environment-variable bypass."""

    def __init__(self, provider: str):
        self.provider = provider

    def snapshot(self, bar: int, *, response_delay_minutes: int = 0) -> ProviderBatch:
        raise ActivationDenied("REAL_SOURCE_ACTIVATION_REQUIRES_SEPARATE_ACCESS_AUTHORIZATION")
