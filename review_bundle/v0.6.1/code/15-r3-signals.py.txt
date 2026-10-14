"""Frozen A identity and two new causal entry mechanisms; no outcomes or costs."""

from __future__ import annotations

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.signals import (
    _atr,
    _ema,
    _er,
    _event,
    _last_complete,
)
from scripts.strategy_research.g2_btc_flow_regime_r2.signals import flow_aggregate
from scripts.strategy_research.g2_btc_flow_regime_r2.signals import generate as r2_generate


def features(data):
    q, h, f = (flow_aggregate(data, n) for n in (15, 60, 240))
    aq, ah, af = (_atr(b) for b in (q, h, f))
    return (
        q,
        h,
        f,
        aq,
        ah,
        af,
        _ema(f["close"], 20),
        _ema(f["close"], 50),
        _er(f["close"]),
        _ema(h["close"], 20),
    )


def hourly_features(data):
    h = flow_aggregate(data, 60)
    atr = _atr(h)
    return [
        {
            "end_ms": int(end),
            "available_at": int(end) + 60000,
            "close": float(h["close"][i]),
            "atr": float(atr[i]),
        }
        for i, end in enumerate(h["end_ms"])
    ]


def scan_new(q, h, f, aq, ah, af, e20, e50, er, eh):
    """Feature-array entry scanner, also usable with explicit synthetic features."""
    out = {"B": [], "C": []}
    pending = {1: None, -1: None}
    vol = np.full(len(q["end_ms"]), np.nan)
    if len(vol) > 20:
        vol[20:] = np.convolve(q["volume"], np.ones(20) / 20, "valid")[:-1]
    for k, end in enumerate(q["end_ms"]):
        hi = _last_complete(h["end_ms"], end)
        fi = _last_complete(f["end_ms"], end)
        for side in (1, -1):
            if pending[side] and k > pending[side]["b"] + 4:
                pending[side] = None
        if k < 20 or hi < 20 or fi < 59:
            continue
        close, opened, high, low = (float(q[x][k]) for x in ("close", "open", "high", "low"))
        atr_h, atr_q, imb = ah[hi], aq[k], q["imbalance"][k]
        if not (
            np.isfinite(atr_h)
            and atr_h > 0
            and 15 <= 10000 * atr_h / close <= 250
            and np.isfinite(atr_q)
            and atr_q > 0
            and np.isfinite(imb)
        ):
            continue
        for s in (1, -1):

            def emit(group, stop, _side=s, _end=end, _close=close, _atr=atr_h, _fi=fi):
                out[group].append(
                    _event(
                        group,
                        "BREAKOUT_RETEST_REACCEPTANCE"
                        if group == "B"
                        else "FAILED_BREAKOUT_NEXT_BAR_REENTRY",
                        8,
                        _side,
                        _end,
                        _close,
                        _atr,
                        stop,
                        f["end_ms"][_fi],
                        f"{group}:{_side}:{int(_end)}",
                    )
                )

            trend = (
                s * (f["close"][fi] - e20[fi]) > 0
                and s * (e20[fi] - e50[fi]) > 0
                and s * (e20[fi] - e20[fi - 3]) > 0
                and er[fi] >= 0.25
                and s * (h["close"][hi] - eh[hi]) > 0
                and s * (eh[hi] - eh[hi - 3]) > 0
                and s * h["imbalance"][hi] >= 0.05
            )
            p = pending[s]
            if p and s * (close - p["edge"]) < -0.25 * p["atr"]:
                pending[s] = None
                p = None
            if p:
                distance = s * ((low if s == 1 else high) - p["edge"])
                if (
                    p["retest"] is None
                    and p["b"] < k <= p["b"] + 3
                    and -0.25 * p["atr"] <= distance <= 0.20 * p["atr"]
                    and s * (close - p["edge"]) >= 0
                ):
                    p["retest"] = k
                elif p["retest"] is not None and k > p["retest"]:
                    previous = q["high"][k - 1] if s == 1 else q["low"][k - 1]
                    if (
                        trend
                        and s * (close - p["edge"]) > 0.10 * p["atr"]
                        and s * (close - previous) > 0
                        and s * (close - opened) >= 0.20 * atr_q
                        and s * imb >= 0.10
                        and q["volume"][k] >= vol[k]
                    ):
                        extreme = (
                            min(q["low"][p["retest"] : k + 1])
                            if s == 1
                            else max(q["high"][p["retest"] : k + 1])
                        )
                        emit("B", extreme - s * 0.25 * atr_h)
                        pending[s] = None
            elif trend:
                edge = max(q["high"][k - 8 : k]) if s == 1 else min(q["low"][k - 8 : k])
                if (
                    s * (close - edge) > 0.10 * atr_q
                    and s * (close - opened) >= 0.20 * atr_q
                    and s * imb >= 0.10
                    and q["volume"][k] >= 1.10 * vol[k]
                ):
                    pending[s] = {"b": k, "edge": float(edge), "atr": float(atr_q), "retest": None}
            b = k - 1
            if b < 20 or not np.isfinite(aq[b]) or aq[b] <= 0 or not np.isfinite(q["imbalance"][b]):
                continue
            lower, upper = min(q["low"][b - 16 : b]), max(q["high"][b - 16 : b])
            edge = lower if s == 1 else upper
            extreme = q["low"][b] if s == 1 else q["high"][b]
            breakout = (
                s * (extreme - edge) < -0.15 * aq[b]
                and s * (q["close"][b] - edge) <= 0
                and s * (q["close"][b] - q["open"][b]) <= 0
                and s * q["imbalance"][b] <= -0.15
                and q["volume"][b] >= 1.20 * vol[b]
            )
            if (
                breakout
                and lower < close < upper
                and s * (close - edge) > 0.10 * aq[b]
                and s * (close - opened) >= 0.20 * atr_q
                and s * imb >= 0.10
                and s * (imb - q["imbalance"][b]) >= 0.25
                and er[fi] <= 0.25
                and np.isfinite(af[fi])
                and abs(f["close"][fi] - e20[fi]) <= 1.25 * af[fi]
            ):
                extreme = min(q["low"][b : k + 1]) if s == 1 else max(q["high"][b : k + 1])
                emit("C", extreme - s * 0.25 * atr_h)
    return out


def generate(data, r2_roster):
    # Exact old function/roster: A's original dicts are returned without mutation.
    old = r2_generate(data, r2_roster)
    result = scan_new(*features(data))
    result["A"] = old["FLOW_CONFIRMED_TREND_08H"]
    return result
