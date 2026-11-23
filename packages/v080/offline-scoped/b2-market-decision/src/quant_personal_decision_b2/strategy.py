"""Causal feature kernels and direction-symmetric setup and trigger rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .model import (
    EPISODE,
    FEATURES,
    MINUTE,
    STRATEGY,
    VENUE,
    Bar,
    D,
    Market,
    Policy,
    check,
    digest,
)

PIVOT_LAG = 2
CONFIRM_WIDTH = 15 * MINUTE
FAMILY_ORDER = ("TREND_PULLBACK", "EARLY_CONTINUATION")


@dataclass(frozen=True)
class Pivot:
    price: Decimal
    candle_end_ms: int
    confirmed_ms: int
    receipt_id: int
    confirmation_receipt_id: int


def ema(values: list[Decimal], period: int) -> list[Decimal]:
    check(len(values) >= period > 0, "FEATURE_WARMUP")
    result = [sum(values[:period], D(0)) / period]
    alpha = D(2) / (period + 1)
    for value in values[period:]:
        result.append(result[-1] + alpha * (value - result[-1]))
    return result


def atr14(bars: tuple[Bar, ...]) -> Decimal:
    check(len(bars) >= 15, "FEATURE_WARMUP")
    ranges = [max(bar.high - bar.low, abs(bar.high - prev.close), abs(bar.low - prev.close))
              for prev, bar in zip(bars, bars[1:], strict=False)]
    value = sum(ranges[:14], D(0)) / 14
    for tr in ranges[14:]:
        value = (13 * value + tr) / 14
    return value


def pivots(bars: tuple[Bar, ...], *, highs: bool) -> list[Pivot]:
    levels = [bar.high if highs else -bar.low for bar in bars]
    results = []
    for i in range(PIVOT_LAG, len(bars) - PIVOT_LAG):
        neighbors = levels[i - PIVOT_LAG:i] + levels[i + 1:i + PIVOT_LAG + 1]
        if all(levels[i] > other for other in neighbors):
            bar, confirmer = bars[i], bars[i + PIVOT_LAG]
            results.append(Pivot(levels[i] if highs else -levels[i], bar.end_ms, confirmer.end_ms,
                                 bar.source["receipt_id"], confirmer.source["receipt_id"]))
    return results


def regime(bars: tuple[Bar, ...]) -> dict[str, Any]:
    closes = [bar.close for bar in bars]
    fast, slow = ema(closes, 10), ema(closes, 20)
    tr = atr14(bars)
    displacement = closes[-1] - closes[-7]
    upper, lower = pivots(bars, highs=True), pivots(bars, highs=False)
    higher = len(upper) >= 2 and len(lower) >= 2 and upper[-1].price > upper[-2].price and lower[-1].price > lower[-2].price
    lower_swing = len(upper) >= 2 and len(lower) >= 2 and upper[-1].price < upper[-2].price and lower[-1].price < lower[-2].price
    direction = 0
    for sign in (1, -1):
        opposing = lower_swing if sign > 0 else higher
        if (not opposing and sign * (fast[-1] - slow[-1]) > tr * D("0.12")
                and sign * (slow[-1] - slow[-4]) > 0 and sign * displacement > tr * D("0.60")):
            direction = sign
    if direction:
        status = "UP" if direction > 0 else "DOWN"
    else:
        status = "RANGE" if abs(displacement) <= max(tr * D("0.60"), D("0.00000001")) else "TRANSITION"
    return {"state": status, "direction": direction, "ema10": fast[-1], "ema20": slow[-1],
            "ema20_slope_three": slow[-1] - slow[-4], "atr14": tr, "six_bar_displacement": displacement,
            "structure": "HIGHER_SWINGS" if higher else "LOWER_SWINGS" if lower_swing else "MIXED_OR_INSUFFICIENT",
            "last_pivot_high": vars(upper[-1]) if upper else None,
            "last_pivot_low": vars(lower[-1]) if lower else None, "latest_end_ms": bars[-1].end_ms}


def axis(bar: Bar, sign: int) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return sign * bar.open, (bar.high if sign > 0 else -bar.low), (bar.low if sign > 0 else -bar.high), sign * bar.close


def obstacles(frames: dict[str, tuple[Bar, ...]], sign: int, beyond: Decimal) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for frame in ("4h", "1d"):
        eligible = [p for p in pivots(frames[frame], highs=sign > 0) if sign * p.price > beyond]
        result[frame] = vars(min(eligible, key=lambda p: (sign * p.price, -p.confirmed_ms))) if eligible else None
    candidates = [(sign * row["price"], frame) for frame, row in result.items() if row is not None]
    first_frame = min(candidates)[1] if candidates else None
    return {"4h": result["4h"], "1d": result["1d"],
            "first": {"frame": first_frame, **result[first_frame]} if first_frame else None}


def setup_candidates(market: Market, tick: Decimal, policy: Policy) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    h1 = market.bars["1h"]
    k = h1[-1]
    prefixes = {frame: tuple(bar for bar in market.bars[frame] if bar.end_ms <= k.end_ms)
                for frame in ("1d", "4h")}
    check(len(prefixes["4h"]) >= 30 and len(prefixes["1d"]) >= 12, "FEATURE_WARMUP")
    four = regime(prefixes["4h"])
    day = prefixes["1d"]
    daily = [b.close for b in day]
    day_highs, day_lows = pivots(day, highs=True), pivots(day, highs=False)
    d_ema = ema(daily, 10)
    diagnostics: dict[str, Any] = {"features": FEATURES, "pivot_right_bars": PIVOT_LAG, "regime_4h": four,
                   "background_1d": {"close": daily[-1], "ema10": d_ema[-1],
                                     "tone": "ABOVE_EMA" if daily[-1] > d_ema[-1] else "AT_OR_BELOW_EMA",
                                     "pivot_high": vars(day_highs[-1]) if day_highs else None,
                                     "pivot_low": vars(day_lows[-1]) if day_lows else None,
                                     "latest_end_ms": day[-1].end_ms}}
    sign = four["direction"]
    tr = atr14(h1)
    baseline = ema([bar.close for bar in h1], 30)[-1]
    vols = sorted(bar.volume for bar in h1[-11:-1])
    typical_volume = (vols[4] + vols[5]) / 2
    body_ratio = abs(k.close - k.open) / (k.high - k.low) if k.high > k.low else D(0)
    diagnostics["signal_1h"] = {"bar_end_ms": k.end_ms, "atr14": tr, "ema30": baseline,
                                "volume_ratio": k.volume / typical_volume if typical_volume else None,
                                "body_ratio": body_ratio}
    if not sign or tr <= 0 or sign * (k.close - baseline) <= 0:
        diagnostics["screen"] = "REGIME_NOT_DIRECTIONAL" if not sign else "ONE_HOUR_TREND_NOT_ALIGNED"
        return [], diagnostics
    recent = h1[-4:-1]
    shelf = [axis(bar, sign) for bar in recent]
    impulse = max(axis(bar, sign)[1] for bar in h1[-12:-4])
    ceiling = max(item[1] for item in shelf)
    anchor = min(recent, key=lambda bar: axis(bar, sign)[2])
    base = axis(anchor, sign)[2]
    opened, favorable_high, adverse_low, close = axis(k, sign)
    depth = (impulse - base) / tr
    shelf_width = (ceiling - base) / tr
    healthy_k = close > opened and close > shelf[-1][3] and body_ratio >= D("0.45") and adverse_low >= base
    families = []
    if healthy_k and D("0.85") <= depth <= D("3.50") and shelf[-1][2] > base:
        families.append("TREND_PULLBACK")
    if (healthy_k and D("-0.35") <= depth <= D("1.35") and shelf_width <= D("1.10")
            and close > ceiling + tick and (typical_volume <= 0 or k.volume >= typical_volume * D("0.85"))):
        families.append("EARLY_CONTINUATION")
    diagnostics["signal_1h"].update(retracement_atr=depth, shelf_width_atr=shelf_width,
                                   matching_families=families, impulse_level=sign * impulse)
    diagnostics["screen"] = "SETUP_FOUND" if families else "NO_FAMILY_MATCH"
    now = market.evaluated_ms
    earliest = ((max(now, k.end_ms) + CONFIRM_WIDTH - 1) // CONFIRM_WIDTH) * CONFIRM_WIDTH
    deadline = min(now + policy.trigger_minutes * MINUTE, k.end_ms + policy.expiry_minutes * MINUTE)
    if earliest + CONFIRM_WIDTH > deadline:
        diagnostics["screen"] = "SIGNAL_K_TOO_OLD_FOR_INDEPENDENT_TRIGGER"
        return [], diagnostics
    buffer = max(tick, tr * D("0.08"))
    invalid = base - tr * D("0.12")
    stop = invalid - tr * D("0.12")
    side = "LONG" if sign > 0 else "SHORT"
    group = digest([VENUE, market.symbol, STRATEGY, side, k.open_ms])
    results = []
    for family in families:
        relevant_shelf = shelf[-2:] if family == "TREND_PULLBACK" else shelf
        line = max(favorable_high, *(row[1] for row in relevant_shelf))
        prior = obstacles(prefixes, sign, line)
        results.append({
            "schema": EPISODE, "episode_id": digest([group, family, anchor.open_ms]), "group_id": group,
            "venue": VENUE, "symbol": market.symbol, "strategy": STRATEGY, "features": FEATURES,
            "direction": side, "sign": sign, "family": family, "rank": FAMILY_ORDER.index(family) + 1,
            "overlap_families": families, "signal_k": k.row(), "anchor": anchor.row(), "atr14": tr,
            "confirmation_line": sign * line, "confirmation_buffer": buffer, "entry_tick": tick,
            "structural_invalidation": sign * invalid, "hard_stop_unrounded": sign * stop,
            "entry_band_unrounded": sorted((sign * (line - tr * D("0.20")), sign * (line + tr * D("0.70")))),
            "frozen_at_ms": now, "earliest_trigger_open_ms": earliest, "trigger_deadline_ms": deadline,
            "expires_at_ms": k.end_ms + policy.expiry_minutes * MINUTE,
            "obstacles": prior, "feature_diagnostics": diagnostics,
            "freeze_source_publication_sha256": market.source["source_publication_sha256"],
        })
    return results, diagnostics


def trigger(episode: dict[str, Any], market: Market) -> tuple[dict[str, Any] | None, str]:
    sign = episode["sign"]
    hurdle = sign * D(episode["confirmation_line"]) + D(episode["confirmation_buffer"])
    result = "INDEPENDENT_15M_PENDING"
    for bar in market.bars["15m"]:
        if bar.open_ms < episode["earliest_trigger_open_ms"] or bar.end_ms > episode["trigger_deadline_ms"]:
            continue
        opened, hi, lo, close = axis(bar, sign)
        if hi < hurdle:
            continue
        if close < hurdle:
            result = "WICK_ONLY_BREAKOUT"
            continue
        if bar.source["revision"] != 1:
            result = "REVISED_TRIGGER_WITHHELD"
            continue
        if close <= opened or hi <= lo or (close - opened) / (hi - lo) < D("0.45") or (hi - close) / (hi - lo) > D("0.35"):
            result = "TRIGGER_BODY_NOT_CONFIRMED"
            continue
        return bar.row(), "INDEPENDENT_15M_CONFIRMED"
    return None, result
