"""Generated provider-shaped fixtures, never downloaded or relabeled market payloads."""

from __future__ import annotations


from ..core import dec, quantize
from ..data import START, SyntheticProvider, histories
from .adapters import venue_symbol
from .config import BridgeConfig
from .contracts import ProviderBatch, Receipt

SCENARIOS = (
    "normal",
    "missing_quote",
    "stale_quote",
    "derivative_failure",
    "missing_oi",
    "clock_error",
    "high_spread",
    "illiquid",
    "missing_spot",
    "missing_liquidity",
)


class OfflineFixtureProvider:
    def __init__(self, config: BridgeConfig, scenario: str = "normal"):
        if scenario not in SCENARIOS:
            raise ValueError("UNKNOWN_OFFLINE_FIXTURE")
        self.config = config
        self.scenario = scenario
        self.data = histories(SyntheticProvider().events(config.platform))
        self.spot = histories(
            SyntheticProvider().events(
                config.platform.model_copy(update={"market": "SPOT", "seed": config.platform.seed + 73})
            )
        )

    def snapshot(self, bar: int, *, response_delay_minutes: int = 0) -> ProviderBatch:
        c = self.config
        p = c.provider
        market = c.platform.market
        if not 0 <= bar < c.platform.bars:
            raise ValueError("FIXTURE_BAR_OUT_OF_RANGE")
        now = self.data[c.platform.benchmark][bar].decision_ts + response_delay_minutes * 60000
        receipts = []

        def emit(channel, identifier, payload, received, available=None, error=None):
            if p == "okx" and channel not in ("candles", "spot_candles"):
                payload = {"code": "0", "data": [payload]}
            receipts.append(
                Receipt.make(
                    p,
                    channel,
                    identifier,
                    received,
                    received + 10 if available is None else available,
                    payload,
                    exposure="SYNTHETIC",
                    error=error,
                )
            )

        for symbol, group in self.data.items():
            identifier = venue_symbol(symbol, market, p)
            base = symbol[:-4]
            if p == "binance":
                metadata = {
                    "symbol": identifier,
                    "baseAsset": base,
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                    "fundingIntervalHours": 8,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                }
            else:
                metadata = {
                    "instId": identifier,
                    "instType": "SWAP" if market == "PERPETUAL" else "SPOT",
                    "ctType": "linear",
                    "settleCcy": "USDT",
                    "ctVal": "0.01",
                    "ctValCcy": base,
                    "baseCcy": base,
                    "quoteCcy": "USDT",
                    "state": "live",
                    "tickSz": "0.01",
                    "lotSz": "1" if market == "PERPETUAL" else "0.001",
                    "minimumNotional": "5",
                    "fundingIntervalHours": 8,
                }
            emit("instrument", identifier, metadata, START - 2000)
            for i in range(bar + 1):
                e = group[i]
                candle = e.candle
                t = candle.close_time_ms

                def candle_row(event, spot=False):
                    b = event.candle
                    o, h, low, close = [
                        str(quantize(value, ".01", up=idx == 1))
                        for idx, value in enumerate((b.open, b.high, b.low, b.close))
                    ]
                    volume = dec(str(round(b.volume, 6)))
                    quote_volume = volume * dec(close)
                    if p == "binance":
                        return [
                            b.open_time_ms,
                            o,
                            h,
                            low,
                            close,
                            str(volume),
                            b.close_time_ms,
                            str(quote_volume),
                            100,
                            "0",
                        ]
                    contracts = volume / dec(".01") if market == "PERPETUAL" and not spot else volume
                    return [
                        str(b.open_time_ms),
                        o,
                        h,
                        low,
                        close,
                        str(contracts),
                        str(volume),
                        str(quote_volume),
                        "1",
                    ]

                emit("candles", identifier, [candle_row(e)], e.provenance.received_ts)
                if self.scenario != "missing_spot":
                    emit(
                        "spot_candles",
                        venue_symbol(symbol, "SPOT", p),
                        [candle_row(self.spot[symbol][i], True)],
                        self.spot[symbol][i].provenance.received_ts,
                    )
                if market == "PERPETUAL":
                    mark = str(quantize(candle.close, ".01"))
                    funding = (
                        {
                            "symbol": identifier,
                            "lastFundingRate": "0.0001",
                            "markPrice": mark,
                            "indexPrice": mark,
                            "time": t,
                        }
                        if p == "binance"
                        else {
                            "instId": identifier,
                            "fundingRate": "0.0001",
                            "markPrice": mark,
                            "indexPrice": mark,
                            "ts": str(t),
                        }
                    )
                    assert e.derivatives is not None and e.derivatives.open_interest is not None
                    oi = e.derivatives.open_interest
                    interest = (
                        {"symbol": identifier, "openInterest": str(oi), "time": t}
                        if p == "binance"
                        else {"instId": identifier, "oi": str(oi / 0.01), "ts": str(t)}
                    )
                    error = "FABRICATED_DERIVATIVE_TIMEOUT" if self.scenario == "derivative_failure" else None
                    emit("funding", identifier, funding, e.provenance.received_ts, error=error)
                    emit(
                        "open_interest",
                        identifier,
                        interest,
                        e.provenance.received_ts,
                        error=error
                        or ("FABRICATED_OI_UNAVAILABLE" if self.scenario == "missing_oi" else None),
                    )
            e = group[bar]
            price = dec(str(e.candle.close))
            spread = dec(".01") if self.scenario == "high_spread" else dec(".0001")
            bid = str(quantize(price * (1 - spread), ".01"))
            ask = str(quantize(price * (1 + spread), ".01", up=True))
            ts = now - 110
            if self.scenario == "stale_quote":
                ts -= 120000
            if self.scenario == "clock_error":
                ts = now + 1000
            quote = (
                {
                    "symbol": identifier,
                    "bidPrice": bid,
                    "askPrice": ask,
                    "bidQty": "1000000",
                    "askQty": "1000000",
                    "time": ts,
                }
                if p == "binance"
                else {
                    "instId": identifier,
                    "bidPx": bid,
                    "askPx": ask,
                    "bidSz": "1000000",
                    "askSz": "1000000",
                    "ts": str(ts),
                }
            )
            if self.scenario != "missing_quote":
                emit("quote", identifier, quote, now - 10)
            daily_volume = (
                "1000" if self.scenario == "illiquid" and symbol == c.platform.universe[-1] else "250000000"
            )
            liquidity = (
                {"symbol": identifier, "quoteVolume": daily_volume, "closeTime": now - 110}
                if p == "binance"
                else {"instId": identifier, "volCcyQuote24h": daily_volume, "ts": str(now - 110)}
            )
            if self.scenario != "missing_liquidity":
                emit("liquidity", identifier, liquidity, now - 10)
        return ProviderBatch(p, now, tuple(receipts), f"GENERATED:{c.platform.seed}:{self.scenario}")
