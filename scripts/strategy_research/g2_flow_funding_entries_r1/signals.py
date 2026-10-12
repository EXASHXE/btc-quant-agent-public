"""Candidate signal identities and continuous causal feature engines for G2 Flow-Funding R1.

Pre-registered 3 hypothesis families x 2 fixed horizons (12h, 18h) = 6 configurations:
1. F1_AGGRESSOR_FLOW_ABSORPTION (12h, 18h): Aggressor taker-flow imbalance vs price progress exhaustion.
2. F2_REALIZED_FUNDING_REVERSAL (12h, 18h): Consecutive settled funding sign reversal with price trend.
3. F3_MARK_LAST_DISLOCATION_REPAIR (12h, 18h): Mark-Last sustained basis dislocation crossed with flow repair.

Feature calculation is strictly continuous across all 36 months (2021-01 through 2023-12)
with January 2021 as warmup, eliminating any monthly or annual ATR reset artifacts.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

import numpy as np

MINUTE = 60_000
HOUR = 3_600_000

CANDIDATE_CONFIGS: list[dict[str, Any]] = [
    {
        "id": "F1_AGGRESSOR_FLOW_ABSORPTION_12H",
        "family": "F1_FLOW_PRICE_DIVERGENCE",
        "horizon_hours": 12,
        "stop_mult": 1.5,
        "target_r": 2.0,
        "cooldown_hours": 4,
        "economic_rationale": "Microstructure absorption: aggressive taker flow dominates 1h window but price progress fails or reverses, forecasting mean reversion in direction of passive liquidity.",
        "clock_type": "hourly_closed_bar",
        "parameters": {"flow_imbalance_threshold": 0.20, "price_progress_sign_divergence": True},
    },
    {
        "id": "F1_AGGRESSOR_FLOW_ABSORPTION_18H",
        "family": "F1_FLOW_PRICE_DIVERGENCE",
        "horizon_hours": 18,
        "stop_mult": 1.5,
        "target_r": 2.0,
        "cooldown_hours": 4,
        "economic_rationale": "Microstructure absorption with 18h extended horizon: passive absorption resolution over multi-session duration.",
        "clock_type": "hourly_closed_bar",
        "parameters": {"flow_imbalance_threshold": 0.20, "price_progress_sign_divergence": True},
    },
    {
        "id": "F2_REALIZED_FUNDING_REVERSAL_12H",
        "family": "F2_REALIZED_FUNDING_CROWDING",
        "horizon_hours": 12,
        "stop_mult": 1.5,
        "target_r": 2.0,
        "cooldown_hours": 4,
        "economic_rationale": "Perps leverage crowding flip: consecutive settled funding rates reverse sign (+ to - or - to +), combined with retrospective price confirmation, signaling speculative crowding washout.",
        "clock_type": "settled_funding_with_1m_lag",
        "parameters": {"min_settlement_lag_minutes": 1, "require_price_confirmation": True},
    },
    {
        "id": "F2_REALIZED_FUNDING_REVERSAL_18H",
        "family": "F2_REALIZED_FUNDING_CROWDING",
        "horizon_hours": 18,
        "stop_mult": 1.5,
        "target_r": 2.0,
        "cooldown_hours": 4,
        "economic_rationale": "Perps leverage crowding flip with 18h extended horizon to capture medium-term repositioning.",
        "clock_type": "settled_funding_with_1m_lag",
        "parameters": {"min_settlement_lag_minutes": 1, "require_price_confirmation": True},
    },
    {
        "id": "F3_MARK_LAST_DISLOCATION_REPAIR_12H",
        "family": "F3_MARK_LAST_DISLOCATION",
        "horizon_hours": 12,
        "stop_mult": 1.5,
        "target_r": 2.0,
        "cooldown_hours": 4,
        "economic_rationale": "Fair value basis repair: Last trade price deviates from Mark price over sustained 1h window, and volume flow moves in reversion direction, capturing basis convergence.",
        "clock_type": "hourly_closed_bar",
        "parameters": {"basis_threshold_bps": 3.0, "flow_confirmation": True},
    },
    {
        "id": "F3_MARK_LAST_DISLOCATION_REPAIR_18H",
        "family": "F3_MARK_LAST_DISLOCATION",
        "horizon_hours": 18,
        "stop_mult": 1.5,
        "target_r": 2.0,
        "cooldown_hours": 4,
        "economic_rationale": "Fair value basis repair with 18h horizon for sustained dislocation normalization.",
        "clock_type": "hourly_closed_bar",
        "parameters": {"basis_threshold_bps": 3.0, "flow_confirmation": True},
    },
]


def config_identity_sha(config: dict[str, Any]) -> str:
    serialized = json.dumps(config, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_continuous_1h_bars(
    last_1m: np.ndarray,
    mark_1m: np.ndarray,
) -> dict[str, np.ndarray]:
    """Aggregate continuous 1m bars into continuous 1h bars with causal ATR and basis.

    No state is reset across month or year boundaries.
    """
    n_1m = len(last_1m)
    assert n_1m % 60 == 0, "Last 1m array length must be multiple of 60"
    n_1h = n_1m // 60

    last_reshaped = last_1m.reshape((n_1h, 60, 7))
    mark_reshaped = mark_1m.reshape((n_1h, 60, 5))

    open_times = last_reshaped[:, 0, 0].astype(np.int64)
    opens = last_reshaped[:, 0, 1]
    highs = np.max(last_reshaped[:, :, 2], axis=1)
    lows = np.min(last_reshaped[:, :, 3], axis=1)
    closes = last_reshaped[:, -1, 4]
    volumes = np.sum(last_reshaped[:, :, 5], axis=1)
    tbvs = np.sum(last_reshaped[:, :, 6], axis=1)
    end_ms = open_times + HOUR - 1

    # Taker-buy signed flow ratio in [-1.0, 1.0]
    safe_v = np.maximum(volumes, 1e-6)
    signed_flow = (2.0 * tbvs - safe_v) / safe_v
    signed_flow = np.clip(signed_flow, -1.0, 1.0)

    # 1h Mark and Last mean prices for basis calculation
    last_mean = np.mean(last_reshaped[:, :, 4], axis=1)
    mark_mean = np.mean(mark_reshaped[:, :, 4], axis=1)
    basis = (last_mean - mark_mean) / mark_mean

    # Continuous Wilder's ATR(14)
    # TR_0 = H_0 - L_0; TR_t = max(H_t - L_t, abs(H_t - C_{t-1}), abs(L_t - C_{t-1}))
    tr = np.empty(n_1h, dtype=np.float64)
    tr[0] = highs[0] - lows[0]
    for t in range(1, n_1h):
        c_prev = closes[t - 1]
        tr[t] = max(highs[t] - lows[t], abs(highs[t] - c_prev), abs(lows[t] - c_prev))

    atr = np.full(n_1h, np.nan, dtype=np.float64)
    period = 14
    if n_1h >= period:
        # Initial SMA for first period
        atr[period - 1] = np.mean(tr[:period])
        # Wilder's smoothing: ATR_t = (13 * ATR_{t-1} + TR_t) / 14
        for t in range(period, n_1h):
            atr[t] = (atr[t - 1] * (period - 1) + tr[t]) / period

    return {
        "open_time": open_times,
        "end_ms": end_ms,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "taker_buy_volume": tbvs,
        "signed_flow": signed_flow,
        "basis": basis,
        "atr": atr,
    }


def generate_candidate_signals(
    candidate: dict[str, Any],
    bars_1h: dict[str, np.ndarray],
    funding_events: list[dict[str, Any]],
    last_1m: np.ndarray,
    eval_start_ms: int,
) -> list[dict[str, Any]]:
    """Generate deterministic point-in-time signals for a given candidate configuration."""
    cand_id = candidate["id"]
    family = candidate["family"]
    horizon_hours = int(candidate["horizon_hours"])
    stop_mult = float(candidate["stop_mult"])
    target_r = float(candidate["target_r"])

    signals: list[dict[str, Any]] = []

    if family == "F1_FLOW_PRICE_DIVERGENCE":
        n_1h = len(bars_1h["open_time"])
        flow_thresh = float(candidate["parameters"]["flow_imbalance_threshold"])

        for h in range(14, n_1h):
            t_open = int(bars_1h["open_time"][h])
            t_decision = t_open + HOUR  # bar is closed exactly at t_open + HOUR
            t_event = t_decision - MINUTE  # timestamp of the last 1m bar in the 1h candle
            t_entry = t_decision + MINUTE  # entry at the open of the next minute

            # Check evaluation window
            if t_entry < eval_start_ms:
                continue

            atr_val = float(bars_1h["atr"][h])
            if np.isnan(atr_val) or atr_val <= 0:
                continue

            s_flow = float(bars_1h["signed_flow"][h])
            c_h = float(bars_1h["close"][h])
            o_h = float(bars_1h["open"][h])
            delta_p = c_h - o_h

            side = 0
            # LONG: aggressive sellers dominate (s_flow <= -threshold) but price didn't fall (delta_p >= 0)
            if s_flow <= -flow_thresh and delta_p >= 0.0:
                side = 1
            # SHORT: aggressive buyers dominate (s_flow >= threshold) but price didn't rise (delta_p <= 0)
            elif s_flow >= flow_thresh and delta_p <= 0.0:
                side = -1

            if side != 0:
                decision_close = c_h
                stop_dist = stop_mult * atr_val
                stop_price = decision_close - side * stop_dist

                signals.append({
                    "event_id": f"{cand_id}_{t_decision}_{side}",
                    "candidate_id": cand_id,
                    "side": side,
                    "event_time": t_event,
                    "decision_at": t_decision,
                    "entry_at": t_entry,
                    "decision_close": decision_close,
                    "atr_hour": atr_val,
                    "stop": stop_price,
                    "target_r": target_r,
                    "horizon_hours": horizon_hours,
                    "feature_values": {
                        "signed_flow": s_flow,
                        "delta_price": delta_p,
                        "atr_1h": atr_val,
                    },
                })

    elif family == "F2_REALIZED_FUNDING_CROWDING":
        # Index funding events chronologically
        funding_sorted = sorted(funding_events, key=lambda x: int(x["settlement_at"]))
        rates_by_time = {int(x["settlement_at"]): Decimal(str(x["rate"])) for x in funding_sorted}
        settlement_times = sorted(rates_by_time.keys())

        # Precompute 1m open times lookup
        last_times = last_1m[:, 0].astype(np.int64)

        for i in range(1, len(settlement_times)):
            t_settle = settlement_times[i]
            t_prev_settle = settlement_times[i - 1]

            # Enforce 8h interval between consecutive settlements
            if abs(t_settle - t_prev_settle - 8 * HOUR) > MINUTE:
                continue

            # Conservative >= 1m publication lag
            t_decision = t_settle + MINUTE  # 00:01:00 UTC
            t_event = t_settle - MINUTE    # bar just before settlement
            t_entry = t_decision + MINUTE   # 00:02:00 UTC

            if t_entry < eval_start_ms:
                continue

            r_curr = rates_by_time[t_settle]
            r_prev = rates_by_time[t_prev_settle]

            # Find 1m bar at t_settle - MINUTE (the last bar of settling window) and t_prev_settle
            idx_end = np.searchsorted(last_times, t_settle - MINUTE)
            idx_start = np.searchsorted(last_times, t_prev_settle)

            if idx_end >= len(last_times) or idx_start >= len(last_times):
                continue
            if last_times[idx_end] != t_settle - MINUTE or last_times[idx_start] != t_prev_settle:
                continue

            p_end = float(last_1m[idx_end, 4])     # close of 8h window
            p_start = float(last_1m[idx_start, 1])  # open of 8h window
            delta_p_8h = p_end - p_start

            # Find decision close at t_settle (bar starting at t_settle, closing at t_decision - 1ms)
            idx_dec = np.searchsorted(last_times, t_settle)
            if idx_dec >= len(last_times) or last_times[idx_dec] != t_settle:
                continue
            decision_close = float(last_1m[idx_dec, 4])

            # Get ATR from latest closed 1h bar before decision
            idx_1h = np.searchsorted(bars_1h["open_time"] + HOUR, t_decision) - 1
            if idx_1h < 0 or np.isnan(bars_1h["atr"][idx_1h]):
                continue
            atr_val = float(bars_1h["atr"][idx_1h])

            side = 0
            # LONG: funding flipped from positive to negative, price declined -> short crowding capitulation
            if r_prev > 0 and r_curr < 0 and delta_p_8h < 0:
                side = 1
            # SHORT: funding flipped from negative to positive, price rose -> long crowding purge
            elif r_prev < 0 and r_curr > 0 and delta_p_8h > 0:
                side = -1

            if side != 0:
                stop_dist = stop_mult * atr_val
                stop_price = decision_close - side * stop_dist

                signals.append({
                    "event_id": f"{cand_id}_{t_decision}_{side}",
                    "candidate_id": cand_id,
                    "side": side,
                    "event_time": t_event,
                    "decision_at": t_decision,
                    "entry_at": t_entry,
                    "decision_close": decision_close,
                    "atr_hour": atr_val,
                    "stop": stop_price,
                    "target_r": target_r,
                    "horizon_hours": horizon_hours,
                    "feature_values": {
                        "r_prev": float(r_prev),
                        "r_curr": float(r_curr),
                        "delta_p_8h": delta_p_8h,
                        "atr_1h": atr_val,
                    },
                })

    elif family == "F3_MARK_LAST_DISLOCATION":
        n_1h = len(bars_1h["open_time"])
        basis_thresh = float(candidate["parameters"]["basis_threshold_bps"]) / 10_000.0

        for h in range(14, n_1h):
            t_open = int(bars_1h["open_time"][h])
            t_decision = t_open + HOUR
            t_event = t_decision - MINUTE
            t_entry = t_decision + MINUTE

            if t_entry < eval_start_ms:
                continue

            atr_val = float(bars_1h["atr"][h])
            if np.isnan(atr_val) or atr_val <= 0:
                continue

            b_val = float(bars_1h["basis"][h])
            s_flow = float(bars_1h["signed_flow"][h])
            c_h = float(bars_1h["close"][h])

            side = 0
            # LONG: Last traded at a discount to Mark (b_val <= -basis_thresh) and flow is buying (s_flow > 0)
            if b_val <= -basis_thresh and s_flow > 0.0:
                side = 1
            # SHORT: Last traded at a premium to Mark (b_val >= basis_thresh) and flow is selling (s_flow < 0)
            elif b_val >= basis_thresh and s_flow < 0.0:
                side = -1

            if side != 0:
                decision_close = c_h
                stop_dist = stop_mult * atr_val
                stop_price = decision_close - side * stop_dist

                signals.append({
                    "event_id": f"{cand_id}_{t_decision}_{side}",
                    "candidate_id": cand_id,
                    "side": side,
                    "event_time": t_event,
                    "decision_at": t_decision,
                    "entry_at": t_entry,
                    "decision_close": decision_close,
                    "atr_hour": atr_val,
                    "stop": stop_price,
                    "target_r": target_r,
                    "horizon_hours": horizon_hours,
                    "feature_values": {
                        "basis": b_val,
                        "signed_flow": s_flow,
                        "atr_1h": atr_val,
                    },
                })

    # Validate strictly increasing chronological ordering and PIT rules
    for sig in signals:
        assert sig["decision_at"] >= sig["event_time"] + MINUTE
        assert sig["entry_at"] >= sig["decision_at"] + MINUTE
        assert sig["event_time"] % MINUTE == 0
        assert sig["decision_at"] % MINUTE == 0
        assert sig["entry_at"] % MINUTE == 0
        assert sig["side"] in (-1, 1)

    return signals
