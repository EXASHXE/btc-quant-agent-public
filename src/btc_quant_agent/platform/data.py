"""Explicitly synthetic source. No network, files, credentials or historical loaders."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Protocol

import numpy as np
import pandas as pd

from .config import PlatformConfig
from .core import (
    Candle,
    DataProvenance,
    DerivativeSnapshot,
    ExecutableQuote,
    InstrumentSpec,
    MarketEvent,
    TradeObservation,
    fingerprint,
    quantize,
)

START = 1_767_225_600_000  # 2026-01-01, generated timestamps, not a market dataset.


class DataProvider(Protocol):
    def events(self, config: PlatformConfig) -> list[MarketEvent]: ...


class SyntheticProvider:
    def events(self, config: PlatformConfig) -> list[MarketEvent]:
        rng = np.random.default_rng(config.seed)
        events = []
        for j, symbol in enumerate(config.universe):
            scenario = config.scenario
            if scenario == "mixed":
                scenario = ("trend", "range", "shock")[j % 3]
            spec = InstrumentSpec(
                symbol,
                market=config.market,
                max_leverage=5 if config.market == "PERPETUAL" else 1,
                session="24x7" if config.market in ("SPOT", "PERPETUAL") else "SYNTHETIC_US",
            )
            price = 100.0 + j * 30
            oi = 10000.0
            previous_close = price
            for i in range(config.bars):
                if scenario == "trend":
                    change = 0.10 + 0.20 * np.sin(i / 4) + rng.normal(0, 0.06)
                else:
                    change = -0.12 * (price - (100 + j * 30)) + rng.normal(0, 0.24)
                shock = scenario == "shock" and i in (75, 150)
                if shock:
                    change -= 8
                    oi *= 0.75
                elif scenario == "shock" and (75 < i < 84 or 150 < i < 159):
                    change += 0.7
                price = max(2, price + change)
                opening = previous_close
                high = max(opening, price) + 0.10 + abs(rng.normal(0, 0.08))
                low = min(opening, price) - 0.10 - abs(rng.normal(0, 0.08))
                volume = 2000 * (4 if shock else 1 + 0.2 * abs(np.sin(i / 3)))
                start = START + i * config.interval_seconds * 1000
                close = start + config.interval_seconds * 1000 - 1
                received = close + 100
                available = received + 10
                provenance = DataProvenance(
                    "synthetic", f"s{config.seed}:{symbol}:{i}", close, received, available
                )
                bid = quantize(price * (1 - config.execution.spread_bps / 20000), spec.tick_size)
                ask = quantize(price * (1 + config.execution.spread_bps / 20000), spec.tick_size, up=True)
                quote = ExecutableQuote(symbol, bid, ask, provenance, Decimal("1000"), Decimal("1000"))
                candle = Candle(
                    symbol,
                    f"{config.interval_seconds}s",
                    start,
                    close,
                    opening,
                    high,
                    low,
                    price,
                    volume,
                    volume * price,
                    volume * 0.52,
                    100,
                    True,
                    available,
                )
                oi *= 1 + rng.normal(0, 0.0004)
                derivatives = None
                if config.market == "PERPETUAL":
                    derivatives = DerivativeSnapshot(
                        provenance,
                        oi,
                        "BASE",
                        0.0001,
                        i % 60 == 0,
                        0.0002,
                        0.0001,
                        volume * 0.52,
                        volume * 0.48,
                        price * 0.9998,
                        price,
                    )
                trades = (
                    TradeObservation(
                        symbol,
                        quantize(price, spec.tick_size),
                        Decimal(str(volume * 0.52)),
                        "BUY",
                        provenance,
                    ),
                    TradeObservation(
                        symbol,
                        quantize(price, spec.tick_size),
                        Decimal(str(volume * 0.48)),
                        "SELL",
                        provenance,
                    ),
                )
                events.append(MarketEvent(spec, candle, provenance, available, quote, derivatives, trades))
                previous_close = price
        return sorted(events, key=lambda e: (e.decision_ts, e.spec.symbol))


def dataset_hash(events: list[MarketEvent]) -> str:
    return fingerprint(events)


def frame(events: list[MarketEvent], cutoff: int) -> pd.DataFrame:
    rows = []
    latest_ts = max((e.candle.close_time_ms for e in events if e.candle.closed and
                     e.candle.close_time_ms <= cutoff), default=-1)
    for e in events:
        c = e.candle
        if (
            not c.closed
            or c.close_time_ms > cutoff
            or c.available_at_ms is None
            or c.available_at_ms > cutoff
            or e.provenance.provider != e.spec.provider
            or e.provenance.reason(cutoff, 10**15)
        ):
            continue
        row = {
            "ts": c.close_time_ms,
            "available_ts": max(e.provenance.available_ts, c.available_at_ms),
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "quote_volume": c.quote_volume,
        }
        d = e.derivatives
        if d is not None:
            def field_admitted(name: str) -> bool:
                p = d.field_clock(name)
                reference = e.decision_ts if c.close_time_ms == latest_ts else c.close_time_ms + 1
                # Freshness is relative to this observation's row. Availability remains the
                # actual receipt time: fetching a historical value never backdates its availability.
                return bool(p is not None and p.provider == e.spec.provider and
                            not d.field_reason(name, min(e.decision_ts, cutoff), 10**15) and
                            0 <= reference - p.exchange_event_ts <= 120000)

            oi_clock = d.field_clock("open_interest")
            if (
                d.oi_unit == "BASE"
                and oi_clock is not None
                and oi_clock.provider == e.spec.provider
                and field_admitted("open_interest")
            ):
                row["open_interest"] = d.open_interest
                row["open_interest__available_ts"] = d.field_clock("open_interest").available_ts
            for name in ("funding_rate", "basis", "premium", "taker_buy", "taker_sell", "spot_close"):
                p = d.field_clock(name)
                if field_admitted(name):
                    row[name] = getattr(d, name)
                    row[name + "__available_ts"] = p.available_ts
        q = e.quote
        if q and not q.reason(e.spec, e.decision_ts):
            row.update(bid=float(q.bid), ask=float(q.ask))
            row.update(bid__available_ts=q.provenance.available_ts, ask__available_ts=q.provenance.available_ts)
        valid_trades = [
            t
            for t in e.trades
            if t.symbol == e.spec.symbol and t.provenance.provider == e.spec.provider
            and not t.provenance.reason(e.decision_ts, 60000)
            and t.aggressive_side in ("BUY", "SELL")
            and t.quantity > 0 and t.price > 0
        ]
        if valid_trades and len(valid_trades) == len(e.trades):
            row["aggressive_delta"] = sum(
                float(t.quantity) * (1 if t.aggressive_side == "BUY" else -1)
                for t in valid_trades
                if t.aggressive_side in ("BUY", "SELL")
            )
            row["aggressive_delta__available_ts"] = max(t.provenance.available_ts for t in valid_trades)
        rows.append(row)
    return pd.DataFrame(rows)


def histories(events: list[MarketEvent]) -> dict[str, list[MarketEvent]]:
    result: dict[str, list[MarketEvent]] = {}
    for event in events:
        result.setdefault(event.spec.symbol, []).append(event)
    return result


class PayloadAdapter:
    """Normalize caller-supplied authorized payloads; transport is intentionally absent."""

    def __init__(self, provider: str):
        if provider not in ("binance", "okx", "equity"):
            raise ValueError("UNSUPPORTED_PROVIDER")
        self.provider = provider

    def quote(
        self,
        spec: InstrumentSpec,
        payload: dict,
        *,
        received_ts: int,
        available_ts: int,
        source_id: str,
        admitted: bool = False,
    ) -> ExecutableQuote:
        keys = {
            "binance": ("bidPrice", "askPrice", "time"),
            "okx": ("bidPx", "askPx", "ts"),
            "equity": ("bid", "ask", "event_ts"),
        }
        bid, ask, ts = keys[self.provider]
        provenance = DataProvenance(
            self.provider,
            source_id,
            int(payload[ts]),
            received_ts,
            available_ts,
            "CALLER_SUPPLIED_UNVERIFIED",
            admitted,
        )
        return ExecutableQuote(
            spec.symbol, Decimal(str(payload[bid])), Decimal(str(payload[ask])), provenance
        )


def with_missing_quote(event: MarketEvent) -> MarketEvent:
    return replace(event, quote=None)
