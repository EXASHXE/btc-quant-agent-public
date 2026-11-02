"""Pure public-payload decoders. No transport, accounts, credentials or orders."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from btc_quant_agent.data.binance import decode_public_klines

from ..core import Candle, DataProvenance, ExecutableQuote, InstrumentSpec, dec
from ..data import PayloadAdapter
from .contracts import (
    CandleRecord,
    FieldObservation,
    InstrumentRecord,
    NormalizedSnapshot,
    NormalizedSymbol,
    ProviderBatch,
    Receipt,
)


def venue_symbol(symbol: str, market: str, provider: str) -> str:
    if not symbol.endswith("USDT") or not symbol[:-4].isalnum():
        raise ValueError("UNSUPPORTED_USDT_SYMBOL")
    return (
        symbol
        if provider == "binance"
        else symbol[:-4] + "-USDT" + ("-SWAP" if market == "PERPETUAL" else "")
    )


def positive(value: Any) -> float:
    result = dec(value)
    if result <= 0:
        raise ValueError("NONPOSITIVE_MARKET_VALUE")
    return float(result)


class PublicPayloadAdapter:
    def __init__(self, provider: str, market: str, interval_seconds: int):
        if provider not in ("binance", "okx") or market not in ("SPOT", "PERPETUAL"):
            raise ValueError("UNSUPPORTED_PUBLIC_CONTRACT")
        self.provider = provider
        self.market = market
        self.interval_seconds = interval_seconds

    def _data(self, r: Receipt) -> Any:
        if r.provider != self.provider:
            raise ValueError("PROVIDER_MISMATCH")
        if r.error:
            raise ValueError("PROVIDER_ERROR:" + r.error)
        data = r.payload
        if self.provider == "okx" and isinstance(data, dict) and "code" in data:
            if str(data["code"]) != "0":
                raise ValueError("PROVIDER_ERROR_CODE")
            data = data["data"]
            if r.channel not in ("candles", "spot_candles"):
                if len(data) != 1:
                    raise ValueError("AMBIGUOUS_INSTRUMENT_RESPONSE")
                data = data[0]
        if isinstance(data, dict):
            identity = data.get("symbol", data.get("instId"))
            if identity is not None and identity != r.instrument_id:
                raise ValueError("RESPONSE_SYMBOL_MISMATCH")
        return data

    def instrument(self, r: Receipt, symbol: str) -> InstrumentRecord:
        d = self._data(r)
        if (
            type(r.received_ts) is not int
            or type(r.available_ts) is not int
            or not 0 < r.received_ts <= r.available_ts
        ):
            raise ValueError("METADATA_RECEIVE_CLOCK_INVALID")
        expected = venue_symbol(symbol, self.market, self.provider)
        if r.instrument_id != expected:
            raise ValueError("INSTRUMENT_MAPPING_MISMATCH")
        if self.provider == "binance":
            filters = {row["filterType"]: row for row in d["filters"]}
            tick = dec(filters["PRICE_FILTER"]["tickSize"])
            step = dec(filters["LOT_SIZE"]["stepSize"])
            minimum = filters.get("MIN_NOTIONAL", filters.get("NOTIONAL", {}))
            min_notional = dec(minimum.get("notional", minimum.get("minNotional")))
            if d["quoteAsset"] != "USDT" or d["baseAsset"] != symbol[:-4]:
                raise ValueError("UNSUPPORTED_CURRENCY")
            if self.market == "PERPETUAL" and (
                d["contractType"] != "PERPETUAL" or d["marginAsset"] != "USDT"
            ):
                raise ValueError("UNSUPPORTED_INVERSE_OR_DELIVERY_CONTRACT")
            multiplier = dec(1)
            active = d["status"] == "TRADING"
        else:
            kind = "SWAP" if self.market == "PERPETUAL" else "SPOT"
            if d["instType"] != kind:
                raise ValueError("INSTRUMENT_TYPE_MISMATCH")
            if self.market == "PERPETUAL":
                if d["ctType"] != "linear" or d["settleCcy"] != "USDT" or d["ctValCcy"] != symbol[:-4]:
                    raise ValueError("UNSUPPORTED_INVERSE_OR_QUANTO_CONTRACT")
                multiplier = dec(d["ctVal"])
            else:
                if d["baseCcy"] != symbol[:-4] or d["quoteCcy"] != "USDT":
                    raise ValueError("UNSUPPORTED_CURRENCY")
                multiplier = dec(1)
            tick = dec(d["tickSz"])
            step = dec(d["lotSz"])
            # Explicit fixture/policy metadata; absent native minimum notional is not inferred.
            min_notional = dec(d["minimumNotional"])
            active = d["state"] == "live"
        interval = d.get("fundingIntervalHours")
        if interval is not None and (type(interval) is not int or interval <= 0):
            raise ValueError("INVALID_FUNDING_INTERVAL")
        # Account leverage/tier entitlement is unknown: advisory assumes unlevered capacity only.
        spec = InstrumentSpec(
            symbol,
            self.market,
            self.provider,
            tick_size=tick,
            quantity_step=step,
            multiplier=multiplier,
            min_notional=min_notional,
            max_leverage=1,
            funding_interval_hours=interval if self.market == "PERPETUAL" else None,
        )
        return InstrumentRecord(spec, expected, active, r.received_ts, r.available_ts, r.id, r.exposure)

    def candles(
        self,
        r: Receipt,
        record: InstrumentRecord,
        *,
        spot: bool = False,
        completion_cutoff_ms: int | None = None,
        provenance_factory: Callable[[Any], DataProvenance] | None = None,
    ) -> tuple[CandleRecord, ...]:
        rows = self._data(r)
        expected = venue_symbol(record.spec.symbol, "SPOT" if spot else self.market, self.provider)
        if r.instrument_id != expected:
            raise ValueError("CANDLE_INSTRUMENT_MISMATCH")
        result = []
        for row in rows:
            if self.provider == "binance":
                # Reuse the repaired project's decoder and actual response receive time.
                if len(row) < 10:
                    raise ValueError("INCOMPLETE_KLINE_SCHEMA")
                p = provenance_factory(row[6]) if provenance_factory else r.provenance(row[6])
                candles = decode_public_klines(
                    [row],
                    record.spec.symbol,
                    f"{self.interval_seconds}s",
                    p.received_ts if completion_cutoff_ms is None else completion_cutoff_ms,
                    received_at_ms=p.received_ts,
                )
                if not candles:
                    raise ValueError("CANDLE_NOT_CLOSED")
                c = replace(candles[0], available_at_ms=p.available_ts)
            else:
                if len(row) < 9 or str(row[8]) != "1":
                    raise ValueError("CANDLE_NOT_CONFIRMED")
                start = int(row[0])
                close = start + self.interval_seconds * 1000 - 1
                p = r.provenance(close)
                base = dec(row[5]) if spot or self.market == "SPOT" else dec(row[5]) * record.spec.multiplier
                if not spot and self.market == "PERPETUAL" and abs(base - dec(row[6])) > dec("0.00000001"):
                    raise ValueError("CANDLE_VOLUME_UNIT_MISMATCH")
                c = Candle(
                    record.spec.symbol,
                    f"{self.interval_seconds}s",
                    start,
                    close,
                    open=float(dec(row[1])),
                    high=float(dec(row[2])),
                    low=float(dec(row[3])),
                    close=float(dec(row[4])),
                    volume=float(base),
                    quote_volume=float(dec(row[7])),
                    closed=True,
                    available_at_ms=p.available_ts,
                )
            if c.close_time_ms - c.open_time_ms + 1 != self.interval_seconds * 1000:
                raise ValueError("CANDLE_INTERVAL_MISMATCH")
            if min(c.open, c.high, c.low, c.close) <= 0:
                raise ValueError("NONPOSITIVE_CANDLE_PRICE")
            result.append(CandleRecord(c, p))
        return tuple(result)

    def quote(
        self,
        r: Receipt,
        record: InstrumentRecord,
        *,
        provenance_factory: Callable[[Any], DataProvenance] | None = None,
    ):
        d = self._data(r)
        if r.instrument_id != record.venue_symbol:
            raise ValueError("QUOTE_INSTRUMENT_MISMATCH")
        if self.provider == "binance":
            ts = d.get("T", d.get("time"))
            bid = d.get("bidPrice", d.get("b"))
            ask = d.get("askPrice", d.get("a"))
            bq = d.get("bidQty", d.get("B"))
            aq = d.get("askQty", d.get("A"))
        else:
            ts = d.get("ts")
            bid = d.get("bidPx")
            ask = d.get("askPx")
            bq = d.get("bidSz")
            aq = d.get("askSz")
        p = provenance_factory(ts) if provenance_factory else r.provenance(ts)
        canonical = (
            {"bidPrice": bid, "askPrice": ask, "time": ts}
            if self.provider == "binance"
            else {"bidPx": bid, "askPx": ask, "ts": ts}
        )
        q = PayloadAdapter(self.provider).quote(
            record.spec,
            canonical,
            received_ts=p.received_ts,
            available_ts=p.available_ts,
            source_id=p.source_id,
            admitted=p.admissible,
        )
        # A missing size remains missing. It is never inferred from bar volume.
        return replace(
            q,
            provenance=p,
            bid_quantity=dec(bq) if bq is not None else None,
            ask_quantity=dec(aq) if aq is not None else None,
        )

    def fields(self, r: Receipt, record: InstrumentRecord) -> tuple[FieldObservation, ...]:
        d = self._data(r)
        if r.instrument_id != record.venue_symbol:
            raise ValueError("FIELD_INSTRUMENT_MISMATCH")
        ts = d.get("time", d.get("ts", d.get("closeTime")))
        p = r.provenance(ts)
        values = {}
        if r.channel == "funding":
            key = "lastFundingRate" if self.provider == "binance" else "fundingRate"
            if d.get(key) is not None:
                values["funding_rate"] = (float(dec(d[key])), "RATE_PER_SETTLEMENT")
            if d.get("markPrice") is not None:
                values["mark_price"] = (positive(d["markPrice"]), "USDT_PER_BASE")
            if d.get("indexPrice") is not None and d.get("markPrice") is not None:
                values["premium"] = (positive(d["markPrice"]) / positive(d["indexPrice"]) - 1, "RATIO")
        elif r.channel == "open_interest":
            oi = float(dec(d["openInterest"] if self.provider == "binance" else d["oi"]))
            if oi < 0:
                raise ValueError("NEGATIVE_OPEN_INTEREST")
            values["open_interest"] = (
                oi if self.provider == "binance" else oi * float(record.spec.multiplier),
                "BASE",
            )
        elif r.channel == "liquidity":
            value = d["quoteVolume"] if self.provider == "binance" else d["volCcyQuote24h"]
            if dec(value) < 0:
                raise ValueError("NEGATIVE_QUOTE_VOLUME")
            values["quote_volume_24h"] = (float(dec(value)), "USDT")
        return tuple(FieldObservation(name, value, unit, p) for name, (value, unit) in values.items())

    def normalize(self, batch: ProviderBatch, symbols: list[str]) -> NormalizedSnapshot:
        if batch.provider != self.provider:
            raise ValueError("BATCH_PROVIDER_MISMATCH")
        normalized = []
        for symbol in symbols:
            expected = venue_symbol(symbol, self.market, self.provider)
            spot = venue_symbol(symbol, "SPOT", self.provider)
            receipts = [
                r
                for r in batch.receipts
                if r.instrument_id == expected or (r.channel == "spot_candles" and r.instrument_id == spot)
            ]
            metadata = [r for r in receipts if r.channel == "instrument"]
            record = None
            issues = []
            candles: list[CandleRecord] = []
            fields: list[FieldObservation] = []
            quotes: list[ExecutableQuote] = []
            if len(metadata) != 1:
                issues.append("INSTRUMENT_METADATA_MISSING_OR_DUPLICATE")
            else:
                try:
                    record = self.instrument(metadata[0], symbol)
                except (ValueError, KeyError, TypeError, IndexError) as exc:
                    issues.append("instrument:" + str(exc))
            if record:
                for r in receipts:
                    if r.channel == "instrument":
                        continue
                    try:
                        if r.channel == "candles":
                            candles.extend(self.candles(r, record))
                        elif r.channel == "spot_candles":
                            for c in self.candles(r, record, spot=True):
                                fields.append(
                                    FieldObservation(
                                        "spot_close", c.candle.close, "USDT_PER_BASE", c.provenance
                                    )
                                )
                        elif r.channel == "quote":
                            quotes.append(self.quote(r, record))
                        else:
                            fields.extend(self.fields(r, record))
                    except (ValueError, KeyError, TypeError, IndexError) as exc:
                        issues.append(r.channel + ":" + str(exc))
            unique: dict[int, CandleRecord] = {}
            for c in candles:
                key = c.candle.close_time_ms
                if key in unique and unique[key] != c:
                    raise ValueError("CONFLICTING_CANDLE_REVISION")
                unique[key] = c
            if len(quotes) > 1:
                raise ValueError("AMBIGUOUS_EXECUTABLE_QUOTE")
            normalized.append(
                NormalizedSymbol(
                    symbol,
                    record,
                    tuple(unique[k] for k in sorted(unique)),
                    quotes[0] if quotes else None,
                    tuple(
                        sorted(
                            fields,
                            key=lambda f: (f.name, f.provenance.exchange_event_ts, f.provenance.available_ts),
                        )
                    ),
                    tuple(sorted(set(issues))),
                )
            )
        exposure = (
            "SYNTHETIC"
            if batch.receipts and all(r.exposure == "SYNTHETIC" for r in batch.receipts)
            else "CALLER_SUPPLIED_UNVERIFIED"
        )
        return NormalizedSnapshot(
            batch.id,
            self.provider,
            batch.decision_ts,
            exposure,
            batch.fixture_id,
            tuple(normalized),
            tuple(r.id for r in batch.receipts),
        )
