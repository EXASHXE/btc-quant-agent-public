"""Versioned fabricated B1 feeds for offline strategy and action-time examples."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_personal_public_b1.fixture import FixtureClock, FixtureTransport
from quant_personal_public_b1.policy import (
    DEPTH,
    INTERVALS,
    KLINES,
    MARK,
    OI_HISTORY,
    QUOTE,
    TICKER,
)
from quant_personal_public_b1.runtime import Runtime
from quant_personal_public_b1.session import RunIdentity

from .model import HOUR, MINUTE, D, check

FIXTURE_VERSION = "B2_SYNTHETIC_MARKET_EXAMPLES_V1"
SIGNAL_END = 1_735_689_600_000
INITIAL = 2 * MINUTE
AFTER_TRIGGER = 32 * MINUTE
PULLBACK = "TREND_PULLBACK"
EARLY = "EARLY_CONTINUATION"


def exact(value: Decimal) -> str:
    return format(value, "f")


class FabricatedMarket:
    def __init__(self, path: Path, family: str, direction: str, *, setup: str = "trend",
                 base_end: int = SIGNAL_END, history: int | None = None) -> None:
        check(family in (PULLBACK, EARLY) and direction in ("LONG", "SHORT"), "INVALID_FIXTURE")
        self.path, self.family, self.direction = path, family, direction
        self.sign = 1 if direction == "LONG" else -1
        self.setup, self.base_end = setup, base_end
        self.variant = "inside"
        self.stop_override: Decimal | None = None
        self.tp_override: Decimal | None = None
        self.mark_override: Decimal | None = None
        self.reference_size = "1.00"
        self.funding_rate = "0.0001"
        self.clock = FixtureClock(base_end + INITIAL)
        self.transport = FixtureTransport(self.clock, mutate=self.respond)
        self.epoch = "B2-SYNTHETIC-" + family + "-" + direction
        self.boot = "B2-FIXTURE-BOOT-A"
        self.history = history

    @property
    def trigger_entry(self) -> Decimal:
        return D("100.74") if self.family == PULLBACK else D("102.11")

    def actual(self, v: Decimal) -> Decimal:
        return v if self.sign > 0 else 200 - v

    def scan(self, offset_ms: int, variant: str = "inside") -> dict[str, Any]:
        target = self.base_end + offset_ms
        check(target >= self.clock.venue_ms, "FIXTURE_TIME_REGRESSION")
        self.clock.advance(target - self.clock.venue_ms)
        self.variant = variant
        args: dict[str, Any] = {"identity": RunIdentity(self.boot, self.epoch)}
        if self.history is not None:
            from dataclasses import replace

            from quant_personal_public_b1.policy import Policy
            from quant_personal_public_b1.runtime import Config

            args["config"] = Config(policy=replace(Policy(), history_bars=self.history))
        return Runtime.fixtures(self.path, self.clock, self.transport, **args).scan(("BTCUSDT",))

    def row(self, frame: str, opened: int) -> list[Any]:
        width = INTERVALS[frame]
        i = (opened + width - self.base_end) // width
        close = D("101.00") + D(i) * D("0.26")
        op, h, lo = close - D("0.32"), close + D("0.27"), close - D("0.55")
        if frame == "1h":
            overrides = ({
                -4: ("100.95", "101.30", "100.50", "100.95"),
                -3: ("100.95", "101.16", "98.95", "99.25"),
                -2: ("99.25", "99.70", "99.02", "99.28"),
                -1: ("99.28", "99.66", "99.14", "99.47"),
                0: ("99.47", "100.58", "99.35", "100.39"),
            } if self.family == PULLBACK else {
                -4: ("100.89", "101.58" if self.setup == "overlap" else "101.12", "100.65", "100.98"),
                -3: ("100.98", "101.20", "100.72", "100.93"),
                -2: ("100.93", "101.18", "100.80", "101.04"),
                -1: ("101.04", "101.24", "100.84", "101.10"),
                0: ("101.09", "101.90", "101.00", "101.74"),
            })
            if i in overrides:
                op, h, lo, close = (D(v) for v in overrides[i])
            elif i > 0:
                close = self.trigger_entry
                op, h, lo = close, close + D("0.17"), close - D("0.17")
        elif frame == "4h":
            if i == -12:
                h = (D("101.28") if self.family == PULLBACK else D("102.60")) if self.setup == "tight" else D("107.30")
            if self.setup in ("chop", "contradict"):
                factor = (D("0.025") if self.setup == "chop" else D("-0.20")) * i
                close = D(100) + factor if self.setup == "contradict" else D(100) + factor * (1 if i % 2 else -1)
                op, h, lo = close - D("0.10"), close + D("0.32"), close - D("0.32")
        elif frame == "1d":
            close = D("97") + D(i % 7) * D("0.45")
            op, h, lo = close - D("0.21"), close + D("0.38"), close - D("0.43")
            if i == -9:
                h = D("110.25")
        elif frame == "15m":
            center = self.trigger_entry if i >= 1 else self.trigger_entry - D("0.62")
            if i in (1, 2):
                near = D("100.75") if self.family == PULLBACK else D("102.10")
                op, h, lo, close = near - D("0.50"), near + D("0.05"), near - D("0.60"), near
                if i == 2 and self.variant in ("wick", "revision_before"):
                    close = op + D("0.05")
                if i == 2 and self.variant == "revision_after":
                    close -= D("0.01")
            else:
                op, h, lo, close = center - D("0.07"), center + D("0.10"), center - D("0.15"), center
        else:  # 5m microstructure and no-chase context
            center = self.trigger_entry - (D("0.32") if i <= 5 else D("0.00"))
            op, h, lo, close = center - D("0.06"), center + D("0.12"), center - D("0.16"), center
        a, z = sorted((self.actual(lo), self.actual(h)))
        return [opened, exact(self.actual(op)), exact(z), exact(a), exact(self.actual(close)), "12.34",
                opened + width - 1, "100.123", 7, "5.0", "55.0", "0"]

    def respond(self, route: str, params: dict[str, Any], body: Any) -> Any:
        if route == KLINES:
            frame = params["interval"]
            result = [self.row(frame, row[0]) for row in body]
            if self.variant == "gap" and frame == "15m":
                result.pop()
            return result
        fav = self.trigger_entry
        if self.clock.venue_ms < self.base_end + AFTER_TRIGGER:
            fav -= D("0.21")
        if self.variant == "chase":
            fav += D("2")
        elif self.variant == "invalid":
            fav = self.stop_override if self.stop_override is not None else D("97")
        elif self.variant == "target_hit":
            fav = self.tp_override if self.tp_override is not None else D("108")
        half = D("0.01")
        if self.variant == "spread":
            # Keep the actionable entry side stable and widen only the exit side.
            half = D("0.80")
            fav -= half - D("0.01")
        centre = self.actual(fav)
        bid, ask = centre - half, centre + half
        mark = self.actual(self.mark_override) if self.mark_override is not None else centre
        if route == QUOTE:
            body.update(askPrice=exact(ask), bidPrice=exact(bid))
            if self.variant == "stale":
                body["time"] -= 25_000
        elif route == DEPTH:
            body["bids"] = [[exact(bid - D("0.01") * i), self.reference_size] for i in range(params["limit"])]
            body["asks"] = [[exact(ask + D("0.01") * i), self.reference_size] for i in range(params["limit"])]
        elif route == MARK:
            body.update(markPrice=exact(mark), indexPrice=exact(mark), lastFundingRate=self.funding_rate)
            if self.variant == "funding":
                body["nextFundingTime"] = self.clock.venue_ms + HOUR
        elif route == TICKER:
            body.update(openPrice=exact(centre), highPrice=exact(centre + 6), lowPrice=exact(centre - 6),
                        lastPrice=exact(centre), weightedAvgPrice=exact(centre))
        elif route == OI_HISTORY and self.variant == "oi_gap":
            body.pop(1)
        return body
