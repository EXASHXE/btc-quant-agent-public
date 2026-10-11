"""Causal signal generators for Goal A R2 candidate families.

Ensures strict event availability:
- t_event: end of completed aggregate bar.
- t_decision: t_event + 60_000 ms (1m decision delay).
- t_entry: t_decision + 60_000 ms (1m execution delay, enters on open of 1m bar).
At least two 1m causal delays before entry.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .features import (
    aggregate_bars,
    calc_atr,
    calc_bollinger_bands,
    calc_choppiness_index,
    calc_ema,
    calc_rolling_extremes,
    calc_rolling_volume_zscore,
)

MINUTE = 60_000
HOUR = 3600_000


def generate_candidate_signals(
    last_1m: np.ndarray,
    candidate: dict[str, Any],
    fold: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate causal signal events for candidate in last_1m data.
    
    If fold is provided, filters to events where entry_at falls within
    [fold['embargo_start_ms'], fold['embargo_end_ms']].
    """
    family = candidate["family"]
    cand_id = candidate["id"]
    horizon_hours = int(candidate["horizon_hours"])
    target_r = float(candidate.get("target_R", 2.0))

    if family == "MACRO_PULLBACK_RECLAIM":
        raw_events = _signals_c01_macro_pullback_reclaim(last_1m)
    elif family == "FAILED_BREAKOUT_EXHAUSTION":
        raw_events = _signals_c02_failed_breakout_exhaustion(last_1m)
    elif family == "VOLATILITY_SHOCK_EXHAUSTION":
        raw_events = _signals_c03_volatility_shock_exhaustion(last_1m)
    elif family == "INTRADAY_RANGE_REVERSION":
        raw_events = _signals_c04_intraday_range_reversion(last_1m)
    else:
        raise ValueError(f"Unknown candidate family: {family}")

    # Build validated event records
    events = []
    # Build 1m lookup index for fast search
    t_1m = last_1m[:, 0].astype(np.int64)

    for rev in raw_events:
        t_event = int(rev["event_time"])
        t_decision = t_event + MINUTE
        t_entry = t_decision + MINUTE

        if fold is not None and (t_entry < fold["embargo_start_ms"] or t_entry > fold["embargo_end_ms"]):
            continue

        # Look up 1m index of decision close and entry open
        idx_decision = int(np.searchsorted(t_1m, t_decision, side="left"))
        idx_entry = int(np.searchsorted(t_1m, t_entry, side="left"))

        if idx_decision >= len(last_1m) or t_1m[idx_decision] != t_decision:
            continue
        if idx_entry >= len(last_1m) or t_1m[idx_entry] != t_entry:
            continue

        decision_close = float(last_1m[idx_decision, 4])
        raw_open = float(last_1m[idx_entry, 1])
        side = int(rev["side"])
        stop = float(rev["stop"])
        atr_hour = float(rev["atr_hour"])

        # Validate stop is on correct side of entry open
        if side * (raw_open - stop) <= 0:
            continue
        initial_risk = side * (raw_open - stop)
        if initial_risk <= 0:
            continue

        # Gap veto check
        if abs(raw_open - decision_close) > 0.25 * atr_hour + 1e-9:
            continue

        event_id = f"{cand_id}_{t_entry}_{side}"
        events.append({
            "event_id": event_id,
            "candidate_id": cand_id,
            "family": family,
            "event_time": t_event,
            "decision_at": t_decision,
            "decision_close": decision_close,
            "entry_at": t_entry,
            "side": side,
            "stop": stop,
            "atr_hour": atr_hour,
            "target_R": target_r,
            "horizon_hours": horizon_hours,
            "raw_entry": raw_open,
        })

    return events


def _signals_c01_macro_pullback_reclaim(last_1m: np.ndarray) -> list[dict[str, Any]]:
    """Hypothesis 1: 1h trend + 15m pullback + 5m reclaim."""
    agg_1h = aggregate_bars(last_1m, 60)
    agg_15m = aggregate_bars(last_1m, 15)
    agg_5m = aggregate_bars(last_1m, 5)

    if not agg_1h or not agg_15m or not agg_5m:
        return []

    c_1h = agg_1h["close"]
    ema20_1h = calc_ema(c_1h, 20)
    ema50_1h = calc_ema(c_1h, 50)
    atr_1h = calc_atr(agg_1h["high"], agg_1h["low"], c_1h, 14)
    end_1h = agg_1h["end_ms"]

    c_15m = agg_15m["close"]
    l_15m = agg_15m["low"]
    h_15m = agg_15m["high"]
    ema20_15m = calc_ema(c_15m, 20)
    end_15m = agg_15m["end_ms"]

    c_5m = agg_5m["close"]
    v_5m = agg_5m["volume"]
    flow_5m = agg_5m["signed_flow_ratio"]
    ema20_5m = calc_ema(c_5m, 20)
    end_5m = agg_5m["end_ms"]

    events = []
    # Warmup requirement: at least 60 1h bars
    if len(c_1h) < 60:
        return []

    for i5 in range(20, len(c_5m)):
        t_5m_end = end_5m[i5]
        event_time = t_5m_end + 1  # exact completed close time

        # Find latest completed 1h bar strictly before event_time
        idx_1h = int(np.searchsorted(end_1h, event_time, side="left")) - 1
        if idx_1h < 50 or np.isnan(atr_1h[idx_1h]):
            continue

        # Find latest completed 15m bar strictly before event_time
        idx_15m = int(np.searchsorted(end_15m, event_time, side="left")) - 1
        if idx_15m < 10:
            continue

        cur_atr_1h = float(atr_1h[idx_1h])
        if cur_atr_1h <= 0:
            continue

        # 1. Macro 1h Trend Alignment
        trend_long = (ema20_1h[idx_1h] > ema50_1h[idx_1h]) and (c_1h[idx_1h] > ema20_1h[idx_1h])
        trend_short = (ema20_1h[idx_1h] < ema50_1h[idx_1h]) and (c_1h[idx_1h] < ema20_1h[idx_1h])

        if not trend_long and not trend_short:
            continue

        # 2. 15m Value Retracement over last 4 completed 15m bars
        win_15m_l = l_15m[idx_15m - 3 : idx_15m + 1]
        win_15m_h = h_15m[idx_15m - 3 : idx_15m + 1]
        win_15m_ema = ema20_15m[idx_15m - 3 : idx_15m + 1]

        pullback_long = np.any(win_15m_l < win_15m_ema)
        pullback_short = np.any(win_15m_h > win_15m_ema)

        # 3. 5m Confirmation Reclaim
        vol_mean_5m = np.mean(v_5m[i5 - 3 : i5])
        vol_confirmed = v_5m[i5] > vol_mean_5m

        reclaim_long = (c_5m[i5] > ema20_5m[i5]) and (flow_5m[i5] > 0.05) and vol_confirmed
        reclaim_short = (c_5m[i5] < ema20_5m[i5]) and (flow_5m[i5] < -0.05) and vol_confirmed

        if trend_long and pullback_long and reclaim_long:
            stop_price = float(np.min(win_15m_l)) - 0.2 * cur_atr_1h
            events.append({
                "event_time": event_time,
                "side": 1,
                "stop": stop_price,
                "atr_hour": cur_atr_1h,
            })
        elif trend_short and pullback_short and reclaim_short:
            stop_price = float(np.max(win_15m_h)) + 0.2 * cur_atr_1h
            events.append({
                "event_time": event_time,
                "side": -1,
                "stop": stop_price,
                "atr_hour": cur_atr_1h,
            })

    return events


def _signals_c02_failed_breakout_exhaustion(last_1m: np.ndarray) -> list[dict[str, Any]]:
    """Hypothesis 2: 24h boundary penetration + 2-bar reclaim + volume absorption."""
    agg_1h = aggregate_bars(last_1m, 60)
    agg_15m = aggregate_bars(last_1m, 15)
    if not agg_1h or not agg_15m:
        return []

    c_1h = agg_1h["close"]
    atr_1h = calc_atr(agg_1h["high"], agg_1h["low"], c_1h, 14)
    atr_24h = calc_atr(agg_1h["high"], agg_1h["low"], c_1h, 24)
    end_1h = agg_1h["end_ms"]

    c_15m = agg_15m["close"]
    h_15m = agg_15m["high"]
    l_15m = agg_15m["low"]
    v_15m = agg_15m["volume"]
    end_15m = agg_15m["end_ms"]

    # 96 15m bars = 24 hours
    lookback = 96
    if len(c_15m) < lookback + 10:
        return []

    roll_h, roll_l = calc_rolling_extremes(h_15m, l_15m, lookback)

    events = []
    for i in range(lookback + 2, len(c_15m)):
        t_end = end_15m[i]
        event_time = t_end + 1

        idx_1h = int(np.searchsorted(end_1h, event_time, side="left")) - 1
        if idx_1h < 25 or np.isnan(atr_1h[idx_1h]) or np.isnan(atr_24h[idx_1h]):
            continue

        cur_atr_1h = float(atr_1h[idx_1h])
        cur_atr_24h = float(atr_24h[idx_1h])
        if cur_atr_1h <= 0 or cur_atr_24h <= 0:
            continue

        h24 = roll_h[i - 1]
        l24 = roll_l[i - 1]
        if np.isnan(h24) or np.isnan(l24) or (h24 - l24) < 1.5 * cur_atr_24h:
            continue

        # Volume absorption condition: 15m volume > 1.25x rolling 24h mean 15m volume
        v_mean_24h = np.mean(v_15m[i - lookback : i])
        if v_15m[i] < 1.25 * v_mean_24h:
            continue

        # Check upside false breakout: previous bar pierced h24 + 0.1*ATR, current bar closes back below h24
        pierced_up = (h_15m[i - 1] > h24 + 0.1 * cur_atr_1h) and (c_15m[i - 1] > h24)
        reclaimed_down = (c_15m[i] < h24)

        # Check downside false breakdown: previous bar pierced l24 - 0.1*ATR, current bar closes back above l24
        pierced_down = (l_15m[i - 1] < l24 - 0.1 * cur_atr_1h) and (c_15m[i - 1] < l24)
        reclaimed_up = (c_15m[i] > l24)

        if pierced_up and reclaimed_down:
            stop_price = max(h_15m[i - 1], h_15m[i]) + 0.25 * cur_atr_1h
            events.append({
                "event_time": event_time,
                "side": -1,
                "stop": stop_price,
                "atr_hour": cur_atr_1h,
            })
        elif pierced_down and reclaimed_up:
            stop_price = min(l_15m[i - 1], l_15m[i]) - 0.25 * cur_atr_1h
            events.append({
                "event_time": event_time,
                "side": 1,
                "stop": stop_price,
                "atr_hour": cur_atr_1h,
            })

    return events


def _signals_c03_volatility_shock_exhaustion(last_1m: np.ndarray) -> list[dict[str, Any]]:
    """Hypothesis 3: Volatility shock displacement + volume z-score > 3.0 + stabilization."""
    agg_1h = aggregate_bars(last_1m, 60)
    agg_15m = aggregate_bars(last_1m, 15)
    if not agg_1h or not agg_15m:
        return []

    c_1h = agg_1h["close"]
    atr_1h = calc_atr(agg_1h["high"], agg_1h["low"], c_1h, 14)
    end_1h = agg_1h["end_ms"]

    o_15m = agg_15m["open"]
    c_15m = agg_15m["close"]
    h_15m = agg_15m["high"]
    l_15m = agg_15m["low"]
    v_15m = agg_15m["volume"]
    end_15m = agg_15m["end_ms"]

    z_vol_15m = calc_rolling_volume_zscore(v_15m, 96)

    events = []
    if len(c_15m) < 100:
        return []

    for i in range(97, len(c_15m)):
        t_end = end_15m[i]
        event_time = t_end + 1

        idx_1h = int(np.searchsorted(end_1h, event_time, side="left")) - 1
        if idx_1h < 15 or np.isnan(atr_1h[idx_1h]):
            continue

        cur_atr_1h = float(atr_1h[idx_1h])
        if cur_atr_1h <= 0:
            continue

        # i-1 is the shock candidate bar; i is the stabilization bar
        shock_body = c_15m[i - 1] - o_15m[i - 1]
        abs_shock_body = abs(shock_body)
        shock_vol_z = z_vol_15m[i - 1]

        # Shock criteria: |body| > 2.0 * 1h ATR and vol z-score > 3.0
        if abs_shock_body < 2.0 * cur_atr_1h or np.isnan(shock_vol_z) or shock_vol_z < 3.0:
            continue

        # Downward liquidation shock exhaustion -> Long signal
        if shock_body < 0:
            # Stabilization: low does not breach shock low, range is smaller, reclaims >= 30% of shock body
            held_extreme = l_15m[i] >= l_15m[i - 1]
            smaller_range = (h_15m[i] - l_15m[i]) < (h_15m[i - 1] - l_15m[i - 1])
            reclaimed_body = c_15m[i] >= c_15m[i - 1] + 0.3 * abs_shock_body

            if held_extreme and smaller_range and reclaimed_body:
                stop_price = l_15m[i - 1] - 0.25 * cur_atr_1h
                events.append({
                    "event_time": event_time,
                    "side": 1,
                    "stop": stop_price,
                    "atr_hour": cur_atr_1h,
                })

        # Upward liquidation shock exhaustion -> Short signal
        elif shock_body > 0:
            # Stabilization: high does not breach shock high, range is smaller, reclaims >= 30% of shock body
            held_extreme = h_15m[i] <= h_15m[i - 1]
            smaller_range = (h_15m[i] - l_15m[i]) < (h_15m[i - 1] - l_15m[i - 1])
            reclaimed_body = c_15m[i] <= c_15m[i - 1] - 0.3 * abs_shock_body

            if held_extreme and smaller_range and reclaimed_body:
                stop_price = h_15m[i - 1] + 0.25 * cur_atr_1h
                events.append({
                    "event_time": event_time,
                    "side": -1,
                    "stop": stop_price,
                    "atr_hour": cur_atr_1h,
                })

    return events


def _signals_c04_intraday_range_reversion(last_1m: np.ndarray) -> list[dict[str, Any]]:
    """Hypothesis 4: Intraday range reversion in range-classified state."""
    agg_1h = aggregate_bars(last_1m, 60)
    agg_15m = aggregate_bars(last_1m, 15)
    if not agg_1h or not agg_15m:
        return []

    c_1h = agg_1h["close"]
    h_1h = agg_1h["high"]
    l_1h = agg_1h["low"]
    atr_1h = calc_atr(h_1h, l_1h, c_1h, 14)
    atr_24h = calc_atr(h_1h, l_1h, c_1h, 24)
    atr_7d = calc_atr(h_1h, l_1h, c_1h, 168)  # 168 hours = 7 days
    chop_1h = calc_choppiness_index(h_1h, l_1h, c_1h, 24)
    bb_up_1h, _bb_mid_1h, bb_lo_1h = calc_bollinger_bands(c_1h, 20, 2.0)
    end_1h = agg_1h["end_ms"]

    o_15m = agg_15m["open"]
    c_15m = agg_15m["close"]
    h_15m = agg_15m["high"]
    l_15m = agg_15m["low"]
    end_15m = agg_15m["end_ms"]

    events = []
    if len(c_1h) < 170:
        return []

    for i in range(20, len(c_15m)):
        t_end = end_15m[i]
        event_time = t_end + 1

        idx_1h = int(np.searchsorted(end_1h, event_time, side="left")) - 1
        if idx_1h < 168 or np.isnan(atr_1h[idx_1h]) or np.isnan(chop_1h[idx_1h]):
            continue

        cur_atr_1h = float(atr_1h[idx_1h])
        cur_chop = float(chop_1h[idx_1h])
        ratio_vol = float(atr_24h[idx_1h] / atr_7d[idx_1h]) if (atr_7d[idx_1h] > 0) else 2.0

        # Ranging regime: Choppiness > 55 and volatility contained (<= 1.1)
        if cur_chop < 55.0 or ratio_vol > 1.1:
            continue

        up_band = float(bb_up_1h[idx_1h])
        lo_band = float(bb_lo_1h[idx_1h])
        bar_range = h_15m[i] - l_15m[i]
        if bar_range <= 1e-8:
            continue

        # Short at upper band: touched upper band, closed inside, upper wick >= 40% of bar range
        touched_up = max(h_15m[i - 1], h_15m[i]) >= up_band
        closed_inside_up = c_15m[i] < up_band
        upper_wick = h_15m[i] - max(o_15m[i], c_15m[i])
        rejection_up = (upper_wick / bar_range) >= 0.40

        # Long at lower band: touched lower band, closed inside, lower wick >= 40% of bar range
        touched_lo = min(l_15m[i - 1], l_15m[i]) <= lo_band
        closed_inside_lo = c_15m[i] > lo_band
        lower_wick = min(o_15m[i], c_15m[i]) - l_15m[i]
        rejection_lo = (lower_wick / bar_range) >= 0.40

        if touched_up and closed_inside_up and rejection_up:
            stop_price = up_band + 0.5 * cur_atr_1h
            events.append({
                "event_time": event_time,
                "side": -1,
                "stop": stop_price,
                "atr_hour": cur_atr_1h,
            })
        elif touched_lo and closed_inside_lo and rejection_lo:
            stop_price = lo_band - 0.5 * cur_atr_1h
            events.append({
                "event_time": event_time,
                "side": 1,
                "stop": stop_price,
                "atr_hour": cur_atr_1h,
            })

    return events
