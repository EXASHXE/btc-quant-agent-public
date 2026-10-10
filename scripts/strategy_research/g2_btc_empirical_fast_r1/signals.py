"""Frozen, closed-bar BTC price signal rules for the public-data experiment.

All timestamps are UTC milliseconds. An event's bar closes at ``event_time``;
the decision is one full minute later and the earliest fill another minute later.
This module observes no fills, costs, returns, or source files.
"""

from __future__ import annotations

import numpy as np

MINUTE_MS = 60_000
HOUR_MS = 60 * MINUTE_MS
FOUR_HOUR_MS = 4 * HOUR_MS


def aggregate(data: np.ndarray, minutes: int) -> dict[str, np.ndarray]:
    """Aggregate complete aligned UTC windows; fail on a missing or duplicate minute."""
    if minutes not in (15, 60, 240):
        raise ValueError("Only frozen 15m, 1h, and 4h windows are supported")
    bars = np.asarray(data, dtype=np.float64)
    if bars.ndim != 2 or bars.shape[1] != 6 or len(bars) == 0:
        raise ValueError("Expected nonempty [open_ms,open,high,low,close,volume] rows")
    times = bars[:, 0]
    if (
        not np.all(np.isfinite(bars))
        or np.any(times != np.floor(times))
        or np.any(times % MINUTE_MS != 0)
        or (len(times) > 1 and np.any(np.diff(times) != MINUTE_MS))
    ):
        raise ValueError("Minute rows must be finite, unique, aligned, and contiguous")
    if np.any(bars[:, 2] < np.maximum(bars[:, 1], bars[:, 4])) or np.any(
        bars[:, 3] > np.minimum(bars[:, 1], bars[:, 4])
    ) or np.any(bars[:, 2] < bars[:, 3]) or np.any(bars[:, 5] < 0):
        raise ValueError("Malformed OHLCV")
    window_ms = minutes * MINUTE_MS
    first_window_start = ((int(times[0]) + window_ms - 1) // window_ms) * window_ms
    first = int(np.searchsorted(times, first_window_start))
    last = len(bars) - ((len(bars) - first) % minutes)
    if last <= first:
        return {name: np.empty(0, dtype=np.float64) for name in (
            "end_ms", "open", "high", "low", "close", "volume"
        )}
    chunks = bars[first:last].reshape(-1, minutes, 6)
    result = {
        "end_ms": chunks[:, -1, 0] + MINUTE_MS,
        "open": chunks[:, 0, 1],
        "high": np.max(chunks[:, :, 2], axis=1),
        "low": np.min(chunks[:, :, 3], axis=1),
        "close": chunks[:, -1, 4],
        "volume": np.sum(chunks[:, :, 5], axis=1),
    }
    if np.any(result["end_ms"] % window_ms):
        raise AssertionError("UTC aggregate did not close on its expected boundary")
    return result


def _sma(values: np.ndarray, window: int) -> np.ndarray:
    output = np.full(len(values), np.nan)
    for index in range(window - 1, len(values)):
        part = values[index - window + 1 : index + 1]
        if np.all(np.isfinite(part)):
            output[index] = np.mean(part)
    return output


def _ema(values: np.ndarray, window: int) -> np.ndarray:
    output = np.full(len(values), np.nan)
    if len(values) < window:
        return output
    seed = values[:window]
    if not np.all(np.isfinite(seed)):
        return output
    output[window - 1] = float(np.mean(seed))
    alpha = 2.0 / (window + 1)
    for index in range(window, len(values)):
        output[index] = alpha * values[index] + (1 - alpha) * output[index - 1]
    return output


def _atr(bars: dict[str, np.ndarray], window: int = 20) -> np.ndarray:
    close = bars["close"]
    prior = np.empty(len(close))
    prior[0] = close[0]  # Frozen first TR is H-L, with no earlier close.
    prior[1:] = close[:-1]
    tr = np.maximum.reduce((
        bars["high"] - bars["low"],
        np.abs(bars["high"] - prior),
        np.abs(bars["low"] - prior),
    ))
    return _sma(tr, window)


def _er(close: np.ndarray, window: int = 12) -> np.ndarray:
    output = np.full(len(close), np.nan)
    for index in range(window, len(close)):
        denominator = np.abs(np.diff(close[index - window : index + 1])).sum()
        if denominator > 0:
            output[index] = abs(close[index] - close[index - window]) / denominator
    return output


def _last_complete(ends: np.ndarray, decision_end: float) -> int:
    return int(np.searchsorted(ends, decision_end, side="right") - 1)


def _trend(side: int, index: int, bars: dict[str, np.ndarray], ema20: np.ndarray,
           ema50: np.ndarray, er12: np.ndarray, *, structural: bool) -> bool:
    if index < 59 or not np.isfinite(ema20[index]) or not np.isfinite(ema50[index]):
        return False
    close = bars["close"][index]
    if not (side * (close - ema20[index]) > 0 and side * (ema20[index] - ema50[index]) > 0):
        return False
    return not structural or (side * (ema20[index] - ema20[index - 3]) > 0
                              and er12[index] >= .35)


def _event(candidate_id: str, family: str, horizon: int, side: int,
           event_end: float, close: float, atr_hour: float, stop: float,
           trend_end: float, event_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "family": family,
        "horizon_hours": horizon,
        "side": side,
        "event_time": int(event_end),
        "decision_at": int(event_end + MINUTE_MS),
        "entry_at": int(event_end + 2 * MINUTE_MS),
        "decision_close": float(close),
        "atr_hour": float(atr_hour),
        "stop": float(stop),
        "trend_bar_end": int(trend_end),
        "regime_vol_bps": float(10_000 * atr_hour / close),
        "event_id": event_id,
    }


def _eligible_atr(close: float, atr: float, *, challenger: bool) -> bool:
    if not (np.isfinite(close) and np.isfinite(atr) and close > 0 and atr > 0):
        return False
    bps = 10_000 * atr / close
    return (15 if challenger else 30) <= bps <= 250


def generate(data: np.ndarray, registry: dict) -> dict[str, list[dict]]:
    """Generate frozen family signals; no outcome, fill, or cost state is read.

    ``registry['candidates']`` is a list of mappings with ``id``, ``family``,
    ``side`` (LONG, SHORT, or BOTH), and ``horizon_hours``. The eight originals
    share underlying events across horizons by design.
    """
    quarter = aggregate(data, 15)
    hour = aggregate(data, 60)
    four = aggregate(data, 240)
    candidate_rows = registry["candidates"]
    if len(candidate_rows) > 12:
        raise ValueError("Frozen experiment permits at most 12 candidates")
    candidates = {row["id"]: row for row in candidate_rows}
    if len(candidates) != len(candidate_rows):
        raise ValueError("Candidate IDs must be unique")
    by_family_side: dict[tuple[str, int], list[dict]] = {}
    for row in candidate_rows:
        if row["family"] not in {
            "STRUCTURAL_CONTINUATION", "CLOSED_RETEST", "TREND_PULLBACK",
            "RANGE_EXPANSION", "FAILED_BREAKOUT", "IMPULSE_COMPRESSION",
        } or row["side"] not in {"LONG", "SHORT", "BOTH"}:
            raise ValueError("Unfrozen family or side")
        allowed_horizons = ((4, 12) if row["family"] in {
            "STRUCTURAL_CONTINUATION", "CLOSED_RETEST"} else (8, 24))
        if row["horizon_hours"] not in allowed_horizons:
            raise ValueError("Unfrozen candidate horizon")
        sides = (1, -1) if row["side"] == "BOTH" else ((1,) if row["side"] == "LONG" else (-1,))
        for side in sides:
            by_family_side.setdefault((row["family"], side), []).append(row)
    output: dict[str, list[dict]] = {name: [] for name in candidates}
    ema4_20, ema4_50 = _ema(four["close"], 20), _ema(four["close"], 50)
    atr4, atr1, atr15 = _atr(four), _atr(hour), _atr(quarter)
    er4, er1 = _er(four["close"]), _er(hour["close"])
    ema15_20 = _ema(quarter["close"], 20)
    vol15_mean = _sma(quarter["volume"], 20)

    def emit(family: str, side: int, end: float, close: float, ah: float,
             stop: float, trend_end: float, identity: str) -> None:
        if not _eligible_atr(close, ah, challenger=family not in (
            "STRUCTURAL_CONTINUATION", "CLOSED_RETEST"
        )):
            return
        for row in by_family_side.get((family, side), []):
            output[row["id"]].append(_event(row["id"], family,
                row["horizon_hours"], side, end, close, ah, stop,
                trend_end, identity))

    # An open 4h bar is never observable. Pending retests retain breakout ATR
    # and boundary, and cannot be refreshed from intervening future bars.
    pending: dict[int, dict | None] = {1: None, -1: None}
    for k in range(len(hour["end_ms"])):
        end = hour["end_ms"][k]
        j = _last_complete(four["end_ms"], end)
        if j < 59:
            continue
        close, opened = hour["close"][k], hour["open"][k]
        for side in (1, -1):
            # Confirmation is checked before a new breakout. A wrong-direction
            # close cancels before a same-hour wick can be used to confirm.
            state = pending[side]
            if state is not None:
                age = k - state["index"]
                if age > 3 or side * (close - state["boundary"]) < -.25 * state["atr"]:
                    pending[side] = None
                elif age >= 1:
                    boundary, frozen = state["boundary"], state["atr"]
                    wick = hour["low"][k] if side == 1 else hour["high"][k]
                    touched = abs(wick - boundary) <= .25 * frozen
                    confirmed = (touched and side * (close - boundary) >= .10 * frozen
                                 and side * (close - opened) > 0
                                 and _trend(side, j, four, ema4_20, ema4_50, er4,
                                            structural=False))
                    if confirmed:
                        extreme = (np.min(hour["low"][state["index"] : k + 1])
                                   if side == 1 else np.max(hour["high"][state["index"] : k + 1]))
                        stop = extreme - side * .25 * frozen
                        emit("CLOSED_RETEST", side, end, close, atr1[k], stop,
                             four["end_ms"][j], f"RETEST:{side}:{int(state['end'])}")
                        pending[side] = None
            if k >= 3 and _trend(side, j, four, ema4_20, ema4_50, er4,
                                  structural=True) and np.isfinite(atr4[j]):
                boundary3 = (np.max(hour["high"][k - 3 : k]) if side == 1
                             else np.min(hour["low"][k - 3 : k]))
                if (side * (close - boundary3) > 0
                    and side * (close - opened) >= .5 * atr1[k]
                    and hour["high"][k] - hour["low"][k] <= 2 * atr1[k]
                    and abs(close - ema4_20[j]) <= atr4[j]):
                    emit("STRUCTURAL_CONTINUATION", side, end, close, atr1[k],
                         close - side * 1.5 * atr1[k], four["end_ms"][j],
                         f"STRUCTURAL:{side}:{int(end)}")
            if (pending[side] is None and k >= 24
                    and np.isfinite(atr1[k]) and atr1[k] > 0 and _trend(
                    side, j, four, ema4_20, ema4_50, er4, structural=False)):
                boundary24 = (np.max(hour["high"][k - 24 : k]) if side == 1
                              else np.min(hour["low"][k - 24 : k]))
                if (side * (close - boundary24) >= .25 * atr1[k]
                    and side * (close - opened) >= .5 * atr1[k]):
                    pending[side] = {"index": k, "end": end,
                                     "boundary": boundary24, "atr": atr1[k]}

    for k in range(len(quarter["end_ms"])):
        end = quarter["end_ms"][k]
        h = _last_complete(hour["end_ms"], end)
        j = _last_complete(four["end_ms"], end)
        if j < 59 or h < 20 or not _eligible_atr(
                quarter["close"][k], atr1[h], challenger=True):
            continue
        close, opened = quarter["close"][k], quarter["open"][k]
        high, low = quarter["high"][k], quarter["low"][k]
        for side in (1, -1):
            # Pullback into the completed 15m EMA in an established 4h trend.
            if (k >= 1 and _trend(side, j, four, ema4_20, ema4_50, er4,
                                  structural=False) and er4[j] >= .25
                and np.isfinite(ema15_20[k - 1])
                and side * (quarter["close"][k - 1] - ema15_20[k - 1]) <= 0
                and side * ((low if side == 1 else high) - ema15_20[k]) <= 0
                and side * (close - ema15_20[k]) > 0
                and side * (close - opened) > 0):
                emit("TREND_PULLBACK", side, end, close, atr1[h],
                     close - side * 1.5 * atr1[h], four["end_ms"][j],
                     f"PULLBACK:{side}:{int(end)}")
            if k < 20 or not np.isfinite(atr15[k]) or atr15[k] <= 0:
                continue
            boundary = (np.max(quarter["high"][k - 16 : k]) if side == 1
                        else np.min(quarter["low"][k - 16 : k]))
            if (side * (close - boundary) > 0
                and side * (close - opened) >= .5 * atr15[k]
                and quarter["volume"][k] >= 1.25 * vol15_mean[k - 1]
                and er1[h] >= .25):
                emit("RANGE_EXPANSION", side, end, close, atr1[h],
                     close - side * 1.5 * atr1[h], four["end_ms"][j],
                     f"EXPANSION:{side}:{int(end)}")
            # Failed breakout trades the reversal, so test the opposite wick.
            fail_boundary = (np.min(quarter["low"][k - 16 : k]) if side == 1
                             else np.max(quarter["high"][k - 16 : k]))
            wick = low if side == 1 else high
            if (side * (wick - fail_boundary) < -.25 * atr15[k]
                and side * (close - fail_boundary) > .10 * atr15[k]
                and side * (close - opened) > 0):
                stop = (low - .25 * atr15[k] if side == 1
                        else high + .25 * atr15[k])
                emit("FAILED_BREAKOUT", side, end, close, atr1[h], stop,
                     four["end_ms"][j], f"FAILED:{side}:{int(end)}")
            if k < 3 or not _trend(side, j, four, ema4_20, ema4_50, er4,
                                    structural=False):
                continue
            impulse = k - 3
            frozen = atr15[impulse - 1] if impulse >= 1 else np.nan
            if not np.isfinite(frozen) or frozen <= 0:
                continue
            impulse_hi, impulse_lo = quarter["high"][impulse], quarter["low"][impulse]
            if (side * (quarter["close"][impulse] - quarter["open"][impulse])
                    < 1.5 * frozen or impulse_hi - impulse_lo > 3 * frozen):
                continue
            if any((quarter["high"][q] - quarter["low"][q] > .75 * frozen
                    or quarter["high"][q] > impulse_hi
                    or quarter["low"][q] < impulse_lo)
                   for q in (impulse + 1, impulse + 2)):
                continue
            compression_edge = (max(quarter["high"][impulse + 1 : k]) if side == 1
                                else min(quarter["low"][impulse + 1 : k]))
            if (side * (close - compression_edge) >= .1 * frozen
                and side * (close - opened) >= .5 * frozen):
                emit("IMPULSE_COMPRESSION", side, end, close, atr1[h],
                     close - side * 2 * atr1[h], four["end_ms"][j],
                     f"COMPRESSION:{side}:{int(end)}")
    return output
