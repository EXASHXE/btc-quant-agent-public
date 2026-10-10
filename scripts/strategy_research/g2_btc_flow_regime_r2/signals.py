"""Six frozen R2 BTC price and taker-flow signals; no execution or outcome access.

Input rows are contiguous UTC one-minute [time, open, high, low, close,
base_volume, taker_buy_base_volume]. All event clocks are exclusive bar ends.
"""

from __future__ import annotations

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.signals import (
    MINUTE_MS,
    _atr,
    _ema,
    _er,
    _event,
    _last_complete,
    aggregate,
)

FAMILIES = {
    "FLOW_CONFIRMED_TREND": 8,
    "EXHAUSTION_FADE": 4,
    "LOW_ER_RANGE_REENTRY": 4,
    "VOL_COMPRESSION_RELEASE": 12,
    "FLOW_ABSORPTION_REVERSAL": 8,
    "SUSTAINED_FLOW": 24,
}


def rsi14(close: np.ndarray) -> np.ndarray:
    """Wilder RSI, first defined after exactly fourteen closed differences."""
    values = np.asarray(close, dtype=np.float64)
    out = np.full(len(values), np.nan)
    if len(values) <= 14:
        return out
    changes = np.diff(values)
    gain = float(np.maximum(changes[:14], 0).mean())
    loss = float(np.maximum(-changes[:14], 0).mean())
    for k in range(14, len(values)):
        if k > 14:
            gain = (13 * gain + max(float(changes[k - 1]), 0)) / 14
            loss = (13 * loss + max(float(-changes[k - 1]), 0)) / 14
        if gain == 0 and loss == 0:
            out[k] = 50
        elif loss == 0:
            out[k] = 100
        elif gain == 0:
            out[k] = 0
        else:
            out[k] = 100 - 100 / (1 + gain / loss)
    return out


def flow_aggregate(data: np.ndarray, minutes: int) -> dict[str, np.ndarray]:
    """Complete UTC OHLCV bars plus volume-weighted signed taker imbalance."""
    rows = np.asarray(data, dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] != 7 or len(rows) == 0:
        raise ValueError("Expected nonempty Nx7 one-minute rows")
    bars = aggregate(rows[:, :6], minutes)
    buy = rows[:, 6]
    if (not np.all(np.isfinite(buy)) or np.any(buy < 0)
            or np.any(buy > rows[:, 5]) or np.any((rows[:, 5] == 0) & (buy != 0))):
        raise ValueError("Taker buy base volume must lie within base volume")
    ends = bars["end_ms"].astype(np.int64)
    if len(ends) == 0:
        bars["taker_buy_volume"] = np.empty(0)
        bars["imbalance"] = np.empty(0)
        return bars
    first = int(np.searchsorted(rows[:, 0], ends[0] - minutes * MINUTE_MS))
    summed = buy[first : first + len(ends) * minutes].reshape(-1, minutes).sum(axis=1)
    volume = bars["volume"]
    imbalance = np.full(len(ends), np.nan)
    np.divide(2 * summed, volume, out=imbalance, where=volume > 0)
    imbalance[volume > 0] -= 1
    bars["taker_buy_volume"] = summed
    bars["imbalance"] = imbalance
    return bars


def _tail(side: int, opened: float, high: float, low: float, close: float) -> float:
    span = high - low
    if span <= 0:
        return np.nan
    return ((min(opened, close) - low) if side == 1
            else (high - max(opened, close))) / span


def _clv(high: float, low: float, close: float) -> float:
    return (2 * close - high - low) / (high - low) if high > low else np.nan


def _trend(side: int, j: int, four: dict[str, np.ndarray],
           ema20: np.ndarray, ema50: np.ndarray, er4: np.ndarray,
           minimum_er: float) -> bool:
    return bool(
        j >= 59 and np.isfinite(ema20[j]) and np.isfinite(ema50[j])
        and side * (four["close"][j] - ema20[j]) > 0
        and side * (ema20[j] - ema50[j]) > 0
        and side * (ema20[j] - ema20[j - 3]) > 0
        and er4[j] >= minimum_er
    )


def generate(data: np.ndarray, roster: dict,
             diagnostics: dict | None = None) -> dict[str, list[dict]]:
    """Emit frozen signals; optionally count causal filter coverage, not causes.

    ``feature_conditions_not_met`` is exactly evaluated quarter/side slots
    minus emissions for that family. It does not attribute a failed Boolean
    expression to a specific feature or pretend that an event was observed.
    """
    rows = np.asarray(data, dtype=np.float64)
    q = flow_aggregate(rows, 15)
    h = flow_aggregate(rows, 60)
    f = flow_aggregate(rows, 240)
    candidates = roster["candidates"]
    if len(candidates) != 6 or {c["family"] for c in candidates} != set(FAMILIES):
        raise ValueError("Exactly six frozen R2 families required")
    by_family = {c["family"]: c for c in candidates}
    if (len({c["id"] for c in candidates}) != 6
            or any(c["horizon_hours"] != FAMILIES[c["family"]]
                   or c["side"] != "BOTH" for c in candidates)):
        raise ValueError("Frozen R2 family identity, side, or horizon mismatch")
    out: dict[str, list[dict]] = {c["id"]: [] for c in candidates}
    if diagnostics is not None:
        diagnostics.clear()
        diagnostics.update({
            "completed_15m_quarters": len(q["end_ms"]),
            "before_60_completed_4h": 0,
            "before_20_completed_1h": 0,
            "global_atr_vol_bad": 0,
            "eligible_quarter_side_observations": 0,
            "first_after_hour_eligible_quarter_side_observations": 0,
            "candidates": {c["id"]: {
                "fully_evaluated_eligible_quarter_side_observations": 0,
                "first_after_hour_eligible_quarter_side_observations": 0,
                "emitted": 0,
                "feature_conditions_not_met": 0,
            } for c in candidates},
        })
    ema20, ema50 = _ema(f["close"], 20), _ema(f["close"], 50)
    atr4, atr1, atr15 = _atr(f), _atr(h), _atr(q)
    er4 = _er(f["close"])
    rsi1, rsi15 = rsi14(h["close"]), rsi14(q["close"])
    h_prior_vol20 = np.full(len(h["end_ms"]), np.nan)
    q_prior_vol20 = np.full(len(q["end_ms"]), np.nan)
    if len(h_prior_vol20) > 20:
        h_prior_vol20[20:] = np.convolve(h["volume"], np.ones(20) / 20,
                                            mode="valid")[:-1]
    if len(q_prior_vol20) > 20:
        q_prior_vol20[20:] = np.convolve(q["volume"], np.ones(20) / 20,
                                            mode="valid")[:-1]
    # True range of the latest *completed* hourly bar, distinct from ATR20.
    h_prior_close = np.r_[h["close"][:1], h["close"][:-1]]
    h_tr = np.maximum.reduce((h["high"] - h["low"],
                              np.abs(h["high"] - h_prior_close),
                              np.abs(h["low"] - h_prior_close)))

    for k, event_end in enumerate(q["end_ms"]):
        hour_idx = _last_complete(h["end_ms"], event_end)
        four_idx = _last_complete(f["end_ms"], event_end)
        if four_idx < 59:
            if diagnostics is not None:
                diagnostics["before_60_completed_4h"] += 1
            continue
        if hour_idx < 20:
            if diagnostics is not None:
                diagnostics["before_20_completed_1h"] += 1
            continue
        close = float(q["close"][k])
        ah = float(atr1[hour_idx])
        if not (np.isfinite(ah) and ah > 0 and close > 0
                and 15 <= 10_000 * ah / close <= 250):
            if diagnostics is not None:
                diagnostics["global_atr_vol_bad"] += 1
            continue
        opened, high, low = (float(q[name][k]) for name in ("open", "high", "low"))
        aq = float(atr15[k])
        q_i = float(q["imbalance"][k])
        first_after_hour = event_end == h["end_ms"][hour_idx] + 15 * MINUTE_MS
        if diagnostics is not None:
            diagnostics["eligible_quarter_side_observations"] += 2
            if first_after_hour:
                diagnostics["first_after_hour_eligible_quarter_side_observations"] += 2
            for counts in diagnostics["candidates"].values():
                counts["fully_evaluated_eligible_quarter_side_observations"] += 2
                if first_after_hour:
                    counts["first_after_hour_eligible_quarter_side_observations"] += 2
        for side in (1, -1):
            def emit(family: str, stop: float, *, _side: int = side,
                     _end: float = event_end, _close: float = close,
                     _ah: float = ah, _j: int = four_idx) -> None:
                candidate = by_family[family]
                identity = f"{family}:{_side}:{int(_end)}"
                out[candidate["id"]].append(_event(
                    candidate["id"], family, candidate["horizon_hours"], _side,
                    _end, _close, _ah, stop, f["end_ms"][_j], identity,
                ))
                if diagnostics is not None:
                    diagnostics["candidates"][candidate["id"]]["emitted"] += 1

            signed_body = side * (close - opened)
            # Directional flow-accepted trend continuation.
            if (k >= 20 and np.isfinite(aq) and aq > 0
                    and _trend(side, four_idx, f, ema20, ema50, er4, .30)
                    and side * (close - (max(q["high"][k - 8:k]) if side == 1
                                         else min(q["low"][k - 8:k]))) > 0
                    and signed_body >= .30 * aq
                    and side * _clv(high, low, close) >= .40
                    and side * q_i >= .15
                    and side * h["imbalance"][hour_idx] >= .08
                    and q["volume"][k] >= 1.20 * q_prior_vol20[k]):
                emit("FLOW_CONFIRMED_TREND", close - side * 1.5 * ah)

            # Exhaustion requires a completed 1h stretch and fresh 15m rejection.
            if (k >= 4 and np.isfinite(aq) and aq > 0
                    and np.isfinite(atr4[four_idx])
                    and side * (h["close"][hour_idx] - ema20[four_idx])
                    <= -1.5 * atr4[four_idx]
                    and ((rsi1[hour_idx] <= 30) if side == 1
                         else (rsi1[hour_idx] >= 70))
                    and side * q["imbalance"][k - 1] <= -.20
                    and side * q_i >= -.05
                    and side * (q_i - q["imbalance"][k - 1]) >= .20
                    and side * ((low if side == 1 else high)
                                - (min(q["low"][k - 4:k]) if side == 1
                                   else max(q["high"][k - 4:k]))) < 0
                    and side * (close - q["close"][k - 1]) > .10 * aq
                    and signed_body > 0 and _tail(side, opened, high, low, close) >= .40):
                emit("EXHAUSTION_FADE", (low if side == 1 else high) - side * .25 * ah)

            # Channel must be frozen before the current quarter and close inside it.
            if k >= 16 and np.isfinite(aq) and aq > 0 and er4[four_idx] <= .20:
                edge_low = float(min(q["low"][k - 16:k]))
                edge_high = float(max(q["high"][k - 16:k]))
                edge = edge_low if side == 1 else edge_high
                extreme = low if side == 1 else high
                if (np.isfinite(atr4[four_idx])
                        and abs(f["close"][four_idx] - ema20[four_idx])
                        <= atr4[four_idx]
                        and side * (extreme - edge) < -.15 * aq
                        and side * (close - edge) > .10 * aq
                        and edge_low < close < edge_high
                        and signed_body > 0
                        and ((rsi15[k] <= 45) if side == 1 else (rsi15[k] >= 55))):
                    emit("LOW_ER_RANGE_REENTRY", extreme - side * .25 * ah)

            # Hourly compression precedes h; only the first closed 15m bar
            # following h may confirm the hourly release.
            if (first_after_hour and hour_idx >= 20 and np.isfinite(q_i)
                    and np.isfinite(atr1[hour_idx]) and np.isfinite(h_prior_vol20[hour_idx])
                    and signed_body > 0 and side * q_i >= .10):
                pre_atr = atr1[hour_idx - 6:hour_idx]
                pre_range = h["high"][hour_idx - 6:hour_idx] - h["low"][hour_idx - 6:hour_idx]
                edge = (max(h["high"][hour_idx - 6:hour_idx]) if side == 1
                        else min(h["low"][hour_idx - 6:hour_idx]))
                if (np.all(np.isfinite(pre_atr)) and pre_atr.mean() > 0
                        and pre_range.mean() / pre_atr.mean() <= .70
                        and side * (h["close"][hour_idx] - edge) > 0
                        and side * (h["close"][hour_idx] - h["open"][hour_idx])
                        >= .50 * ah
                        and h_tr[hour_idx] >= 1.30 * ah
                        and h["volume"][hour_idx] >= 1.50 * h_prior_vol20[hour_idx]
                        and side * (close - edge) >= .10 * ah):
                    emit("VOL_COMPRESSION_RELEASE", close - side * 1.75 * ah)

            # A pre-rejection eight-quarter range excludes all last three bars.
            if (k >= 10 and np.isfinite(aq) and aq > 0 and er4[four_idx] <= .35
                    and side * q["imbalance"][k - 2] <= -.15
                    and side * q["imbalance"][k - 1] <= -.15
                    and side * q_i >= .05 and signed_body >= .30 * aq):
                pre_low = float(min(q["low"][k - 10:k - 2]))
                pre_high = float(max(q["high"][k - 10:k - 2]))
                edge = pre_low if side == 1 else pre_high
                rejects = range(k - 2, k + 1)
                tails = sum(_tail(side, q["open"][v], q["high"][v],
                                  q["low"][v], q["close"][v]) >= .35 for v in rejects)
                if (tails >= 2 and all(
                        -.25 * ah <= side * ((q["low"][v] if side == 1
                                              else q["high"][v]) - edge) <= .50 * ah
                        for v in rejects)
                        and side * (close - q["close"][k - 2]) >= 0
                        and side * (close - (max(q["high"][k - 2:k]) if side == 1
                                             else min(q["low"][k - 2:k]))) > 0
                        and pre_low < close < pre_high):
                    stop = ((min(q["low"][k - 2:k + 1]) - .25 * ah) if side == 1
                            else (max(q["high"][k - 2:k + 1]) + .25 * ah))
                    emit("FLOW_ABSORPTION_REVERSAL", stop)

            # Two complete hourly pressure advances and one new-hour quarter.
            if (first_after_hour and hour_idx >= 2 and np.isfinite(aq) and aq > 0
                    and _trend(side, four_idx, f, ema20, ema50, er4, .35)
                    and side * h["imbalance"][hour_idx - 1] >= .08
                    and side * h["imbalance"][hour_idx] >= .08
                    and all(side * (h["close"][v] - h["close"][v - 1])
                            > .20 * atr1[v - 1] for v in (hour_idx - 1, hour_idx))
                    and side * q_i >= .10
                    and side * (close - h["close"][hour_idx]) >= .15 * ah
                    and signed_body >= .25 * aq
                    and abs(close - h["close"][hour_idx]) <= .75 * ah):
                emit("SUSTAINED_FLOW", close - side * 2 * ah)
    if diagnostics is not None:
        for counts in diagnostics["candidates"].values():
            counts["feature_conditions_not_met"] = (
                counts["fully_evaluated_eligible_quarter_side_observations"]
                - counts["emitted"]
            )
    return out
