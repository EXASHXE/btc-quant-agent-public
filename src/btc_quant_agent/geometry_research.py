from __future__ import annotations

import bisect
import hashlib
import importlib
import json
import math
import resource
import shutil
import statistics
import subprocess
import time
from collections import Counter, deque
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import FundingEvent, resample
from .config import AppConfig
from .domain import Candle, Direction, Setup, TimeframeFeatures
from .engine import HistoricalFeatureCache, QuantEngine
from .funnel import SetupFunnelTrace, trace_setup_funnels
from .indicators import ema
from .mechanism import decompose_rr
from .regime import classify_regime
from .research import DEV_END_MS, DEV_START_MS
from .structure import confirmed_pivots

HORIZON_MINUTES = (60, 120, 240, 480, 720)
REACH_THRESHOLDS_ATR = (0.5, 1.0, 1.5, 2.5)
TP_PATTERN_EXPECTED = 404
TP_POST_FACTOR_EXPECTED = 139
BR_POST_FACTOR_EXPECTED = 185
BR_RISK_PASS_EXPECTED = 14
TREND_DECISIONS_EXPECTED = 29_580
REACH_HORIZON_MINUTES = 720
ZONE_SCAN_BARS = 40


def assert_v033_development_only(rows: Sequence[dict[str, Any]]) -> None:
    if any(
        int(row["timestamp_ms"]) < DEV_START_MS
        or int(row["timestamp_ms"]) >= DEV_END_MS
        for row in rows
    ):
        raise ValueError("v0.3.3 holdout firewall rejected artifact row")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "mean": None, "median": None, "p25": None, "p75": None, "p90": None}
    return {
        "count": len(ordered),
        "mean": statistics.mean(ordered),
        "median": statistics.median(ordered),
        "p25": ordered[max(0, math.ceil(0.25 * len(ordered)) - 1)],
        "p75": ordered[max(0, math.ceil(0.75 * len(ordered)) - 1)],
        "p90": ordered[max(0, math.ceil(0.90 * len(ordered)) - 1)],
    }


def _values(rows: Sequence[dict[str, Any]], field: str) -> list[float]:
    return [float(row[field]) for row in rows if row.get(field) is not None]


def _split_distributions(
    rows: Sequence[dict[str, Any]],
    fields: Sequence[str],
    split_field: str,
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[split_field]), []).append(row)
    return {
        key: {
            field: _distribution(_values(items, field))
            for field in fields
        }
        for key, items in sorted(groups.items())
    }


def _summary_block(
    rows: Sequence[dict[str, Any]],
    fields: Sequence[str],
    *,
    splits: Sequence[str] = ("direction", "year"),
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "overall": {
            field: _distribution(_values(rows, field)) for field in fields
        },
    }
    for split in splits:
        output[f"by_{split}"] = _split_distributions(rows, fields, split)
    return output


def _net_rr(reward_pct: float, risk_pct: float, cost_rate: float) -> float | None:
    if risk_pct + cost_rate <= 0:
        return None
    return (reward_pct - cost_rate) / (risk_pct + cost_rate)


def _frozen_cost_rate(frozen: AppConfig) -> float:
    risk = frozen.risk
    return (
        2 * risk.taker_fee_rate
        + 2 * risk.slippage_bps_per_side / 10_000
        + risk.funding_stress_rate * risk.max_expected_funding_events
    )


def _scan_back_streak(
    condition: Callable[[int], bool], last: int, limit: int
) -> int | None:
    first = max(0, last - limit + 1)
    index = last
    while index >= first and condition(index):
        index -= 1
    streak_start = index + 1
    return streak_start if streak_start <= last else None


class _OneMinuteSeries:
    """Bounded 1m arrays for excursion windows; never contains holdout rows."""

    def __init__(self, candles_1m: Sequence[Candle]) -> None:
        if any(
            bar.open_time_ms < DEV_START_MS or bar.open_time_ms >= DEV_END_MS
            for bar in candles_1m
        ):
            raise ValueError("v0.3.3 excursion series rejects holdout rows")
        self.opens = [bar.open_time_ms for bar in candles_1m]
        self.highs = [bar.high for bar in candles_1m]
        self.lows = [bar.low for bar in candles_1m]

    def window(
        self, decision_close_ms: int, horizon_minutes: int
    ) -> tuple[list[float], list[float], int, bool]:
        end_ms = decision_close_ms + horizon_minutes * 60_000
        incomplete = end_ms > DEV_END_MS
        start = bisect.bisect_right(self.opens, decision_close_ms)
        end = bisect.bisect_right(self.opens, min(end_ms, DEV_END_MS - 1))
        return self.highs[start:end], self.lows[start:end], start, incomplete


def _mfe_mae(
    highs: Sequence[float],
    lows: Sequence[float],
    direction: Direction,
    entry: float,
) -> tuple[float, float, float | None, float | None]:
    if not highs:
        return 0.0, 0.0, None, None
    if direction == Direction.LONG:
        mfe = max(0.0, max(highs) - entry)
        mae = max(0.0, entry - min(lows))
        mfe_idx = (
            next((i for i, value in enumerate(highs) if value - entry >= mfe), None)
            if mfe > 0.0
            else None
        )
        mae_idx = (
            next((i for i, value in enumerate(lows) if entry - value >= mae), None)
            if mae > 0.0
            else None
        )
    else:
        mfe = max(0.0, entry - min(lows))
        mae = max(0.0, max(highs) - entry)
        mfe_idx = (
            next((i for i, value in enumerate(lows) if entry - value >= mfe), None)
            if mfe > 0.0
            else None
        )
        mae_idx = (
            next((i for i, value in enumerate(highs) if value - entry >= mae), None)
            if mae > 0.0
            else None
        )
    return mfe, mae, mfe_idx, mae_idx


def _excursion_row(
    row: dict[str, Any],
    series: _OneMinuteSeries,
    horizon: int,
    frozen_stop: float,
) -> dict[str, Any]:
    decision_close_ms = int(row["decision_close_ms"])
    entry = float(row["close"])
    direction = Direction(row["direction"])
    atr = float(row["atr"])
    highs, lows, start, incomplete = series.window(decision_close_ms, horizon)
    mfe, mae, mfe_idx, mae_idx = _mfe_mae(highs, lows, direction, entry)
    stop_distance = abs(entry - frozen_stop)
    return {
        "candidate_id": row["candidate_id"],
        "scope": row["scope"],
        "in_scope_a": row.get("in_scope_a", False),
        "in_scope_b": row.get("in_scope_b", False),
        "setup": row["setup"],
        "direction": row["direction"],
        "timestamp_ms": row["timestamp_ms"],
        "year": row["year"],
        "horizon_minutes": horizon,
        "window_start_index": start,
        "incomplete": incomplete,
        "mfe_atr": mfe / atr if atr > 0 else None,
        "mae_atr": mae / atr if atr > 0 else None,
        "mfe_pct": 100.0 * mfe / entry if entry > 0 else None,
        "mae_pct": 100.0 * mae / entry if entry > 0 else None,
        "mfe_stop_r": mfe / stop_distance if stop_distance > 0 else None,
        "mae_stop_r": mae / stop_distance if stop_distance > 0 else None,
        "mfe_mae_ratio": mfe / mae if mae > 0 else None,
        "time_to_mfe_minutes": None if mfe_idx is None else mfe_idx + 1,
        "time_to_mae_minutes": None if mae_idx is None else mae_idx + 1,
    }


def _reachability_row(
    row: dict[str, Any],
    series: _OneMinuteSeries,
    threshold_label: str,
    level_atr: float | None,
    favorable: float,
    *,
    frozen_stop: float,
    invalidation: float,
    local_extreme: float | None,
) -> dict[str, Any]:
    decision_close_ms = int(row["decision_close_ms"])
    direction = Direction(row["direction"])
    highs, lows, _start, incomplete = series.window(decision_close_ms, REACH_HORIZON_MINUTES)
    long = direction == Direction.LONG
    stop_idx: int | None = None
    invalidation_idx: int | None = None
    local_idx: int | None = None
    reach_idx: int | None = None
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        if stop_idx is None and ((low <= frozen_stop) if long else (high >= frozen_stop)):
            stop_idx = index
        if invalidation_idx is None and (
            (low <= invalidation) if long else (high >= invalidation)
        ):
            invalidation_idx = index
        if (
            local_idx is None
            and local_extreme is not None
            and ((low <= local_extreme) if long else (high >= local_extreme))
        ):
            local_idx = index
        if reach_idx is None and ((high >= favorable) if long else (low <= favorable)):
            reach_idx = index
    reached = reach_idx is not None
    reached_before_stop = False
    if reach_idx is not None:
        reached_before_stop = stop_idx is None or reach_idx < stop_idx
    return {
        "candidate_id": row["candidate_id"],
        "scope": row["scope"],
        "in_scope_a": row.get("in_scope_a", False),
        "in_scope_b": row.get("in_scope_b", False),
        "setup": row["setup"],
        "direction": row["direction"],
        "timestamp_ms": row["timestamp_ms"],
        "year": row["year"],
        "threshold_label": threshold_label,
        "level_atr": level_atr,
        "incomplete": incomplete,
        "reached": reached,
        "reached_before_stop": reached_before_stop,
        "reached_minutes": reach_idx + 1 if reach_idx is not None else None,
        "stop_first_touch_minutes": stop_idx + 1 if stop_idx is not None else None,
        "invalidation_first_touch_minutes": (
            invalidation_idx + 1 if invalidation_idx is not None else None
        ),
        "local_extreme_first_touch_minutes": (
            local_idx + 1 if local_idx is not None else None
        ),
    }


def _barrier_row(
    row: dict[str, Any],
    first_barrier: float | None,
    series: _OneMinuteSeries,
) -> dict[str, Any]:
    decision_close_ms = int(row["decision_close_ms"])
    atr = float(row["atr"])
    direction = Direction(row["direction"])
    highs, lows, _start, incomplete = series.window(decision_close_ms, REACH_HORIZON_MINUTES)
    long = direction == Direction.LONG
    reached_minutes: int | None = None
    if first_barrier is not None:
        for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
            if (high >= first_barrier) if long else (low <= first_barrier):
                reached_minutes = index + 1
                break
    continuation: float | None = None
    if reached_minutes is not None and first_barrier is not None and atr > 0:
        after = highs[reached_minutes:] if long else lows[reached_minutes:]
        if after:
            if long:
                continuation = (max(after) - first_barrier) / atr
            else:
                continuation = (first_barrier - min(after)) / atr
    return {
        "candidate_id": row["candidate_id"],
        "scope": row["scope"],
        "in_scope_a": row.get("in_scope_a", False),
        "in_scope_b": row.get("in_scope_b", False),
        "setup": row["setup"],
        "direction": row["direction"],
        "timestamp_ms": row["timestamp_ms"],
        "year": row["year"],
        "first_confirmed_barrier_distance_atr": row["first_barrier_distance_atr"],
        "confirmed_barriers_before_2_5_atr_target": row[
            "confirmed_barriers_before_2_5_atr_target"
        ],
        "first_confirmed_barrier_reached_in_12h": reached_minutes is not None,
        "first_confirmed_barrier_reach_minutes": reached_minutes,
        "max_continuation_excursion_after_barrier_atr": continuation,
        "incomplete": incomplete,
    }


def _tp_geometry_row(
    trace: SetupFunnelTrace,
    history_15m: list[Candle],
    features_15m: TimeframeFeatures,
    frozen: AppConfig,
    now_ms: int,
    year: int,
) -> dict[str, Any]:
    candidate = trace.candidate
    assert candidate is not None
    strategy = frozen.strategy
    long = candidate.direction == Direction.LONG
    atr = features_15m.atr
    close = features_15m.close
    closes = [bar.close for bar in history_15m]
    lows = [bar.low for bar in history_15m]
    highs = [bar.high for bar in history_15m]
    ema_fast_series = ema(closes, strategy.ema_fast)
    ema_mid_series = ema(closes, strategy.ema_mid)
    ema_fast = ema_fast_series[-1]
    ema_mid = ema_mid_series[-1]
    last_index = len(history_15m) - 1
    latest = history_15m[-1]
    prior = history_15m[-2]
    tolerance = strategy.pullback_atr_tolerance * atr
    pivots = confirmed_pivots(history_15m, strategy.pivot_left, strategy.pivot_right)
    kind = "LOW" if long else "HIGH"
    swing_pivots = [pivot for pivot in pivots if pivot.kind == kind]
    invalidation = candidate.invalidation_level
    invalidation_pivot = _match_pivot(swing_pivots, kind, invalidation)
    recent = history_15m[-5:]
    if long:
        pullback_extreme = min(bar.low for bar in recent)
    else:
        pullback_extreme = max(bar.high for bar in recent)
    extreme_offset = next(
        4 - index
        for index, bar in enumerate(recent)
        if (bar.low if long else bar.high) == pullback_extreme
    )
    touch_index = _zone_touch_index(
        last_index, lows, highs, ema_mid_series, tolerance, long
    )
    reclaim_index = _scan_back_streak(
        (
            (lambda index: closes[index] > ema_fast_series[index])
            if long
            else (lambda index: closes[index] < ema_fast_series[index])
        ),
        last_index,
        ZONE_SCAN_BARS,
    )
    decomposition = decompose_rr(candidate, atr, strategy, frozen.risk)
    entry_midpoint = decomposition.entry_reference
    frozen_stop = decomposition.actual_stop
    pullback_extreme_bar = recent[4 - extreme_offset]
    local_extreme_stop = (
        pullback_extreme - strategy.stop_atr_buffer * atr
        if long
        else pullback_extreme + strategy.stop_atr_buffer * atr
    )
    diagnostic_risk = (
        entry_midpoint - local_extreme_stop
        if long
        else local_extreme_stop - entry_midpoint
    )
    diagnostic_stop_distance_atr = diagnostic_risk / atr if atr > 0 else None
    reward = decomposition.reward_distance_usdt
    diagnostic_gross_rr = reward / diagnostic_risk if diagnostic_risk > 0 else None
    cost_rate = _frozen_cost_rate(frozen)
    diagnostic_net_rr = (
        _net_rr(reward / entry_midpoint, diagnostic_risk / entry_midpoint, cost_rate)
        if diagnostic_risk > 0 and entry_midpoint > 0
        else None
    )
    pivot_160 = confirmed_pivots(
        history_15m[-strategy.level_lookback_bars :],
        strategy.pivot_left,
        strategy.pivot_right,
    )
    target = candidate.target_level
    target_pivot = _match_pivot(pivot_160, "HIGH" if long else "LOW", target)
    between_target = sorted(
        pivot.price
        for pivot in pivot_160
        if pivot.kind == ("HIGH" if long else "LOW")
        and (close < pivot.price < target if long else target < pivot.price < close)
    )
    projected_25 = close + 2.5 * atr if long else close - 2.5 * atr
    intermediate_barriers_25 = sorted(
        pivot.price
        for pivot in pivot_160
        if pivot.kind == ("HIGH" if long else "LOW")
        and (
            close < pivot.price < projected_25
            if long
            else projected_25 < pivot.price < close
        )
    )
    first_barrier = intermediate_barriers_25[0] if intermediate_barriers_25 else None
    break_overshoot = (
        (latest.close - prior.high) / atr if long else (prior.low - latest.close) / atr
    ) if atr > 0 else None
    decision_close_ms = latest.close_time_ms
    invalidation_distance = close - invalidation if long else invalidation - close
    local_extreme_distance = (
        close - pullback_extreme if long else pullback_extreme - close
    )
    ema25_touch_depth = (
        ema_mid - pullback_extreme if long else pullback_extreme - ema_mid
    )
    touch_move = (
        (close - closes[touch_index]) / atr
        if touch_index is not None and atr > 0
        else None
    )
    reclaim_move = (
        (close - closes[reclaim_index]) / atr
        if reclaim_index is not None and atr > 0
        else None
    )
    swing_extreme_gap = (
        pullback_extreme - invalidation if long else invalidation - pullback_extreme
    )
    return {
        "candidate_id": f"{now_ms}:TP:{candidate.direction.value}",
        "scope": (
            "TP_POST_FACTOR"
            if trace.factor is not None and trace.factor.blocked_reason is None
            else "TP_PATTERN"
        ),
        "in_scope_a": True,
        "in_scope_b": (
            trace.factor is not None and trace.factor.blocked_reason is None
        ),
        "setup": "TREND_PULLBACK",
        "direction": candidate.direction.value,
        "timestamp_ms": now_ms,
        "year": year,
        "decision_close_ms": decision_close_ms,
        "close": close,
        "atr": atr,
        "entry_low": candidate.entry_low,
        "entry_high": candidate.entry_high,
        "entry_reference": entry_midpoint,
        "ema7": ema_fast,
        "ema25": ema_mid,
        "invalidation_level": invalidation,
        "invalidation_pivot_open_time_ms": (
            invalidation_pivot.open_time_ms if invalidation_pivot is not None else None
        ),
        "invalidation_pivot_age_bars": (
            last_index - invalidation_pivot.pivot_index
            if invalidation_pivot is not None
            else None
        ),
        "invalidation_pivot_age_minutes": (
            (decision_close_ms - invalidation_pivot.open_time_ms) / 60_000.0
            if invalidation_pivot is not None
            else None
        ),
        "invalidation_distance_atr": invalidation_distance / atr if atr > 0 else None,
        "pullback_local_extreme": pullback_extreme,
        "pullback_local_extreme_bar_offset": extreme_offset,
        "pullback_local_extreme_bar_close_time_ms": pullback_extreme_bar.close_time_ms,
        "local_extreme_distance_atr": local_extreme_distance / atr if atr > 0 else None,
        "confirmed_swing_vs_local_extreme_gap_atr": swing_extreme_gap / atr if atr > 0 else None,
        "frozen_stop": frozen_stop,
        "frozen_stop_distance_atr": decomposition.stop_distance_atr,
        "ema25_touch_depth_atr": ema25_touch_depth / atr if atr > 0 else None,
        "pullback_extreme_to_confirmed_swing_atr": swing_extreme_gap / atr if atr > 0 else None,
        "pullback_extreme_to_final_close_atr": (
            local_extreme_distance / atr if atr > 0 else None
        ),
        "ema25_to_final_close_atr": (
            (close - ema_mid) / atr if long and atr > 0 else (ema_mid - close) / atr if atr > 0 else None
        ),
        "ema7_to_final_close_atr": (
            (close - ema_fast) / atr if long and atr > 0 else (ema_fast - close) / atr if atr > 0 else None
        ),
        "first_ema25_zone_touch_bar_offset": (
            last_index - touch_index if touch_index is not None else None
        ),
        "first_ema25_zone_touch_timestamp_ms": (
            history_15m[touch_index].close_time_ms if touch_index is not None else None
        ),
        "first_ema7_reclaim_bar_offset": (
            last_index - reclaim_index if reclaim_index is not None else None
        ),
        "first_ema7_reclaim_timestamp_ms": (
            history_15m[reclaim_index].close_time_ms
            if reclaim_index is not None
            else None
        ),
        "previous_extreme_break_timestamp_ms": decision_close_ms,
        "final_candidate_timestamp_ms": decision_close_ms,
        "touch_to_candidate_bars": (
            last_index - touch_index if touch_index is not None else None
        ),
        "touch_to_candidate_minutes": (
            15 * (last_index - touch_index) if touch_index is not None else None
        ),
        "touch_to_candidate_price_move_atr": touch_move,
        "ema7_reclaim_to_candidate_price_move_atr": reclaim_move,
        "previous_extreme_break_overshoot_atr": break_overshoot,
        "target": target,
        "target_distance_atr": decomposition.reward_distance_atr,
        "target_pivot_open_time_ms": (
            target_pivot.open_time_ms if target_pivot is not None else None
        ),
        "target_pivot_age_minutes": (
            (decision_close_ms - target_pivot.open_time_ms) / 60_000.0
            if target_pivot is not None
            else None
        ),
        "intermediate_confirmed_pivots_to_target": len(between_target),
        "required_target_price": decomposition.required_target_price,
        "required_reward_atr": decomposition.required_reward_atr,
        "required_minus_actual_target_gap_atr": decomposition.actual_target_gap_atr,
        "reward_distance_atr_over_stop_distance_atr": (
            decomposition.reward_distance_atr / decomposition.stop_distance_atr
            if decomposition.stop_distance_atr > 0
            else None
        ),
        "gross_rr": decomposition.rr_gross,
        "local_extreme_stop": local_extreme_stop,
        "local_extreme_stop_distance_atr": diagnostic_stop_distance_atr,
        "local_extreme_stop_gross_rr": diagnostic_gross_rr,
        "local_extreme_stop_net_rr": diagnostic_net_rr,
        "local_extreme_stop_net_rr_pass": (
            diagnostic_net_rr is not None and diagnostic_net_rr >= strategy.rr_min
        ),
        "first_barrier_distance_atr": (
            (first_barrier - close) / atr
            if first_barrier is not None and long and atr > 0
            else (close - first_barrier) / atr
            if first_barrier is not None and atr > 0
            else None
        ),
        "confirmed_barriers_before_2_5_atr_target": len(intermediate_barriers_25),
    }


def _match_pivot(pivots: Sequence[Any], kind: str, price: float) -> Any | None:
    exact = next(
        (pivot for pivot in reversed(pivots) if pivot.kind == kind and pivot.price == price),
        None,
    )
    if exact is not None:
        return exact
    return next(
        (
            pivot
            for pivot in reversed(pivots)
            if pivot.kind == kind and math.isclose(pivot.price, price, rel_tol=1e-12)
        ),
        None,
    )


def _zone_touch_index(
    last_index: int,
    lows: Sequence[float],
    highs: Sequence[float],
    ema_mid_series: Sequence[float],
    tolerance: float,
    long: bool,
) -> int | None:
    for index in range(last_index, max(-1, last_index - ZONE_SCAN_BARS), -1):
        if long:
            if lows[index] <= ema_mid_series[index] + tolerance:
                return index
        elif highs[index] >= ema_mid_series[index] - tolerance:
            return index
    return None


def _br_geometry_row(
    trace: SetupFunnelTrace,
    history_15m: list[Candle],
    features_15m: TimeframeFeatures,
    frozen: AppConfig,
    now_ms: int,
    year: int,
) -> dict[str, Any]:
    candidate = trace.candidate
    assert candidate is not None
    strategy = frozen.strategy
    atr = features_15m.atr
    decomposition = decompose_rr(candidate, atr, strategy, frozen.risk)
    long = candidate.direction == Direction.LONG
    latest = history_15m[-1]
    decision_close_ms = latest.close_time_ms
    pivot_160 = confirmed_pivots(
        history_15m[-strategy.level_lookback_bars : -3],
        strategy.pivot_left,
        strategy.pivot_right,
    )
    level = (
        min(candidate.entry_low, candidate.entry_high)
        if long
        else max(candidate.entry_low, candidate.entry_high)
    )
    level_pivot = _match_pivot(pivot_160, "HIGH" if long else "LOW", level)
    return {
        "candidate_id": f"{now_ms}:BR:{candidate.direction.value}",
        "scope": (
            "BR_RISK_PASS" if decomposition.reject_reason == "PASS" else "BR_POST_FACTOR"
        ),
        "in_scope_a": False,
        "in_scope_b": False,
        "setup": "BREAKOUT_RETEST",
        "direction": candidate.direction.value,
        "timestamp_ms": now_ms,
        "year": year,
        "decision_close_ms": decision_close_ms,
        "close": features_15m.close,
        "atr": atr,
        "entry_low": candidate.entry_low,
        "entry_high": candidate.entry_high,
        "entry_reference": decomposition.entry_reference,
        "ema7": None,
        "ema25": None,
        "breakout_level": level,
        "breakout_level_pivot_open_time_ms": (
            level_pivot.open_time_ms if level_pivot is not None else None
        ),
        "breakout_level_pivot_age_minutes": (
            (decision_close_ms - level_pivot.open_time_ms) / 60_000.0
            if level_pivot is not None
            else None
        ),
        "invalidation_level": decomposition.invalidation_level,
        "frozen_stop": decomposition.actual_stop,
        "frozen_stop_distance_atr": decomposition.stop_distance_atr,
        "invalidation_distance_atr": (
            (decomposition.entry_reference - decomposition.invalidation_level) / atr
            if long and atr > 0
            else (decomposition.invalidation_level - decomposition.entry_reference) / atr
            if atr > 0
            else None
        ),
        "target": decomposition.target,
        "target_distance_atr": decomposition.reward_distance_atr,
        "gross_rr": decomposition.rr_gross,
        "net_rr": decomposition.rr_net,
        "reject_reason": decomposition.reject_reason,
        "entry_lag_bars": 1,
        "required_reward_atr": decomposition.required_reward_atr,
        "reward_distance_atr_over_stop_distance_atr": (
            decomposition.reward_distance_atr / decomposition.stop_distance_atr
            if decomposition.stop_distance_atr > 0
            else None
        ),
    }


def _br_qualification_row(
    trace: SetupFunnelTrace,
    history_15m: list[Candle],
    features_15m: TimeframeFeatures,
    frozen: AppConfig,
    now_ms: int,
    year: int,
    bar_index: int,
) -> dict[str, Any]:
    candidate = trace.candidate
    factor = trace.factor
    assert candidate is not None and factor is not None
    decomposition = decompose_rr(candidate, features_15m.atr, frozen.strategy, frozen.risk)
    stages = {item.stage: item for item in trace.stages}
    momentum_aligned = (
        features_15m.roc > 0
        if candidate.direction == Direction.LONG
        else features_15m.roc < 0
    )
    participation_score = factor.group_scores.get("participation_flow")
    return {
        "candidate_id": f"{now_ms}:BR:{candidate.direction.value}",
        "timestamp_ms": now_ms,
        "decision_close_ms": history_15m[-1].close_time_ms,
        "bar_index": bar_index,
        "year": year,
        "direction": candidate.direction.value,
        "setup": candidate.setup.value,
        "regime": trace.regime,
        "close": features_15m.close,
        "atr": features_15m.atr,
        "atr_percentile": features_15m.atr_percentile,
        "atr_decile": min(9, int(features_15m.atr_percentile * 10)),
        "entry_low": candidate.entry_low,
        "entry_high": candidate.entry_high,
        "invalidation_level": candidate.invalidation_level,
        "target": candidate.target_level,
        "target_source": trace.target_source,
        "macro_pass": stages["BR_12_4H_MACRO"].predicate_passed,
        "rsi_pass": stages["BR_13_RSI"].predicate_passed,
        "momentum_roc_aligned": momentum_aligned,
        "participation_available": participation_score is not None,
        "participation_pass": (
            participation_score is not None and participation_score >= 50.0
        ),
        "participation_score": participation_score,
        "factor_score": factor.score,
        "positive_groups": factor.positive_groups,
        "factor_score_pass": stages["BR_14_FACTOR_SCORE"].predicate_passed,
        "positive_groups_pass": stages["BR_15_POSITIVE_GROUPS"].predicate_passed,
        "post_macro_rsi": (
            stages["BR_12_4H_MACRO"].predicate_passed
            and stages["BR_13_RSI"].predicate_passed
        ),
        "post_factor": factor.blocked_reason is None,
        "factor_blocked_reason": factor.blocked_reason,
        "factor_group_scores": factor.group_scores,
        **decomposition.as_dict(),
    }


def _year_of(now_ms: int) -> int:
    return datetime.fromtimestamp(now_ms / 1000, UTC).year


def _reach_rate(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in rows if not item["incomplete"]]
    reached = sum(bool(item["reached"]) for item in eligible)
    reached_before_stop = sum(bool(item["reached_before_stop"]) for item in eligible)
    stop_first = sum(
        bool(item["reached"]) and not bool(item["reached_before_stop"])
        for item in eligible
    )
    return {
        "eligible_candidates": len(eligible),
        "incomplete_excluded": sum(bool(item["incomplete"]) for item in rows),
        "reached": reached,
        "reached_before_stop": reached_before_stop,
        "stop_first": stop_first,
        "reached_rate": reached / len(eligible) if eligible else None,
        "reached_before_stop_rate": (
            reached_before_stop / len(eligible) if eligible else None
        ),
        "stop_first_rate": stop_first / len(eligible) if eligible else None,
    }


def run_v033_geometry_audit(
    candles_1m: Sequence[Candle],
    config: AppConfig,
    funding_events: Sequence[FundingEvent],
    *,
    capture_trend_controls: bool = False,
    capture_breakout_qualification: bool = False,
) -> dict[str, Any]:
    del funding_events
    if not candles_1m or candles_1m[0].open_time_ms != DEV_START_MS:
        raise ValueError("v0.3.3 requires the complete development period")
    if candles_1m[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("v0.3.3 geometry audit rejects holdout rows")
    started = time.perf_counter()
    completed = {
        interval: resample(candles_1m, interval) for interval in ("15m", "1h", "4h")
    }
    series = _OneMinuteSeries(candles_1m)
    del candles_1m
    frozen = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    limits = {
        "15m": frozen.data.history_limit_15m,
        "1h": frozen.data.history_limit_1h,
        "4h": frozen.data.history_limit_4h,
    }
    histories: dict[str, deque[Candle]] = {
        name: deque(maxlen=limits[name]) for name in completed
    }
    cursors = {name: 0 for name in completed}
    engine = QuantEngine(frozen, HistoricalFeatureCache())
    tp_rows: list[dict[str, Any]] = []
    br_rows: list[dict[str, Any]] = []
    trend_control_rows: list[dict[str, Any]] = []
    breakout_qualification_rows: list[dict[str, Any]] = []
    denominator: Counter[str] = Counter()
    loop_started = time.perf_counter()
    for bar_index, decision_bar in enumerate(completed["15m"]):
        for interval in ("15m", "1h", "4h"):
            bars = completed[interval]
            while (
                cursors[interval] < len(bars)
                and bars[cursors[interval]].close_time_ms <= decision_bar.close_time_ms
            ):
                histories[interval].append(bars[cursors[interval]])
                cursors[interval] += 1
        now_ms = decision_bar.close_time_ms + 1
        scan_outcome = engine.scan(
            list(histories["4h"]),
            list(histories["1h"]),
            list(histories["15m"]),
            None,
            now_ms,
        )
        if scan_outcome.reason_code in {
            "FEATURE_ERROR",
            "INVALID_CANDLES",
            "STALE_DECISION_DATA",
        }:
            continue
        f4 = engine.diagnostic_features("4h", list(histories["4h"]))
        f1 = engine.diagnostic_features("1h", list(histories["1h"]))
        f15 = engine.diagnostic_features("15m", list(histories["15m"]))
        regime = classify_regime(f1, frozen.strategy)
        denominator[str(regime)] += 1
        if regime.value not in {"TREND_UP", "TREND_DOWN"}:
            continue
        denominator["TREND_DECISION"] += 1
        year = _year_of(now_ms)
        if capture_trend_controls:
            trend_control_rows.append(
                {
                    "control_id": f"CTRL:{now_ms}",
                    "timestamp_ms": now_ms,
                    "decision_close_ms": decision_bar.close_time_ms,
                    "bar_index": bar_index,
                    "year": year,
                    "direction": (
                        Direction.LONG.value
                        if regime.value == "TREND_UP"
                        else Direction.SHORT.value
                    ),
                    "regime": regime.value,
                    "atr": f15.atr,
                    "atr_percentile": f15.atr_percentile,
                    "atr_decile": min(9, int(f15.atr_percentile * 10)),
                    "close": f15.close,
                    "is_tp_pattern": False,
                }
            )
        history_15m = list(histories["15m"])
        traces = trace_setup_funnels(
            history_15m, f4, f1, f15, regime, frozen, scan_outcome
        )
        for trace in traces:
            candidate = trace.candidate
            factor = trace.factor
            if candidate is None:
                continue
            if candidate.setup == Setup.TREND_PULLBACK:
                tp_rows.append(
                    _tp_geometry_row(trace, history_15m, f15, frozen, now_ms, year)
                )
            else:
                if capture_breakout_qualification and factor is not None:
                    breakout_qualification_rows.append(
                        _br_qualification_row(
                            trace, history_15m, f15, frozen, now_ms, year, bar_index
                        )
                    )
                if factor is not None and factor.blocked_reason is None:
                    br_rows.append(
                        _br_geometry_row(trace, history_15m, f15, frozen, now_ms, year)
                    )
    loop_runtime = time.perf_counter() - loop_started

    tp_pattern = list(tp_rows)
    tp_post = [row for row in tp_rows if row["scope"] == "TP_POST_FACTOR"]
    br_post = list(br_rows)
    br_risk = [row for row in br_rows if row["scope"] == "BR_RISK_PASS"]
    counts = {
        "trend_decisions": denominator["TREND_DECISION"],
        "tp_pattern": len(tp_pattern),
        "tp_post_factor": len(tp_post),
        "br_post_factor": len(br_post),
        "br_risk_pass": len(br_risk),
    }
    expected = {
        "trend_decisions": TREND_DECISIONS_EXPECTED,
        "tp_pattern": TP_PATTERN_EXPECTED,
        "tp_post_factor": TP_POST_FACTOR_EXPECTED,
        "br_post_factor": BR_POST_FACTOR_EXPECTED,
        "br_risk_pass": BR_RISK_PASS_EXPECTED,
    }
    if counts != expected:
        raise RuntimeError(
            "GEOMETRY_AUDIT_BLOCKED: frozen scope reproduction mismatch "
            f"expected={expected} actual={counts}"
        )

    excursion_rows: list[dict[str, Any]] = []
    reachability_rows: list[dict[str, Any]] = []
    barrier_rows: list[dict[str, Any]] = []
    for row in [*tp_rows, *br_rows]:
        frozen_stop = float(row["frozen_stop"])
        for horizon in HORIZON_MINUTES:
            excursion_rows.append(_excursion_row(row, series, horizon, frozen_stop))
        thresholds: list[tuple[str, float | None, float | None]] = [
            (f"atr_{value}", value, None) for value in REACH_THRESHOLDS_ATR
        ]
        thresholds.append(
            (
                "frozen_structural_target",
                float(row["target_distance_atr"]),
                float(row["target"]),
            )
        )
        required_atr = row.get("required_reward_atr")
        thresholds.append(
            (
                "required_target_for_net_rr",
                float(required_atr) if required_atr is not None else None,
                (
                    float(row["required_target_price"])
                    if row.get("required_target_price") is not None
                    else None
                ),
            )
        )
        for label, level_atr, absolute in thresholds:
            if level_atr is None:
                continue
            if absolute is not None:
                level = absolute
            else:
                atr = float(row["atr"])
                level = (
                    float(row["close"]) + level_atr * atr
                    if row["direction"] == "LONG"
                    else float(row["close"]) - level_atr * atr
                )
            reachability_rows.append(
                _reachability_row(
                    row,
                    series,
                    label,
                    level_atr,
                    level,
                    frozen_stop=frozen_stop,
                    invalidation=float(row["invalidation_level"]),
                    local_extreme=row.get("pullback_local_extreme"),
                )
            )
        if row["setup"] == "TREND_PULLBACK":
            barrier_distance = row.get("first_barrier_distance_atr")
            first_barrier = None
            if barrier_distance is not None:
                atr = float(row["atr"])
                if row["direction"] == "LONG":
                    first_barrier = float(row["close"]) + float(barrier_distance) * atr
                else:
                    first_barrier = float(row["close"]) - float(barrier_distance) * atr
            barrier_rows.append(_barrier_row(row, first_barrier, series))

    threshold_labels = [f"atr_{value}" for value in REACH_THRESHOLDS_ATR] + [
        "frozen_structural_target",
        "required_target_for_net_rr",
    ]
    reachability_summary: dict[str, Any] = {
        "scope_a_tp_pattern": {},
        "scope_b_tp_post_factor": {},
        "br_reference_risk_pass": {},
    }
    for label in threshold_labels:
        reachability_summary["scope_a_tp_pattern"][label] = _reach_rate(
            [
                item
                for item in reachability_rows
                if item["in_scope_a"]
                and item["setup"] == "TREND_PULLBACK"
                and item["threshold_label"] == label
            ]
        )
        reachability_summary["scope_b_tp_post_factor"][label] = _reach_rate(
            [
                item
                for item in reachability_rows
                if item["in_scope_b"]
                and item["setup"] == "TREND_PULLBACK"
                and item["threshold_label"] == label
            ]
        )
        reachability_summary["br_reference_risk_pass"][label] = _reach_rate(
            [
                item
                for item in reachability_rows
                if item["scope"] == "BR_RISK_PASS"
                and item["setup"] == "BREAKOUT_RETEST"
                and item["threshold_label"] == label
            ]
        )

    mfe_mae_summary: dict[str, Any] = {}
    predicates: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] = (
        ("TP_PATTERN", lambda item: bool(item["in_scope_a"])),
        ("TP_POST_FACTOR", lambda item: bool(item["in_scope_b"])),
        ("BR_POST_FACTOR", lambda item: item["scope"] == "BR_POST_FACTOR"),
        ("BR_RISK_PASS", lambda item: item["scope"] == "BR_RISK_PASS"),
    )
    for horizon in HORIZON_MINUTES:
        block: dict[str, Any] = {}
        for scope, predicate in predicates:
            scope_rows = [
                item
                for item in excursion_rows
                if item["horizon_minutes"] == horizon
                and predicate(item)
                and not item["incomplete"]
            ]
            block[scope] = {
                field: _distribution(_values(scope_rows, field))
                for field in (
                    "mfe_atr", "mae_atr", "mfe_pct", "mae_pct",
                    "mfe_stop_r", "mae_stop_r", "mfe_mae_ratio",
                    "time_to_mfe_minutes", "time_to_mae_minutes",
                )
            }
        mfe_mae_summary[f"{horizon}m"] = block

    tp_core_fields = (
        "invalidation_pivot_age_bars", "invalidation_pivot_age_minutes",
        "invalidation_distance_atr", "local_extreme_distance_atr",
        "confirmed_swing_vs_local_extreme_gap_atr", "frozen_stop_distance_atr",
        "target_distance_atr",
    )
    lag_fields = (
        "touch_to_candidate_bars", "touch_to_candidate_minutes",
        "touch_to_candidate_price_move_atr",
        "ema7_reclaim_to_candidate_price_move_atr",
        "previous_extreme_break_overshoot_atr",
    )
    pullback_fields = (
        "ema25_touch_depth_atr", "pullback_extreme_to_confirmed_swing_atr",
        "pullback_extreme_to_final_close_atr", "ema25_to_final_close_atr",
        "ema7_to_final_close_atr", "pullback_local_extreme_bar_offset",
        "first_ema25_zone_touch_bar_offset", "first_ema7_reclaim_bar_offset",
    )
    target_fields = (
        "target_distance_atr", "target_pivot_age_minutes",
        "intermediate_confirmed_pivots_to_target", "required_reward_atr",
        "required_minus_actual_target_gap_atr",
        "reward_distance_atr_over_stop_distance_atr",
    )
    br_core_fields = (
        "frozen_stop_distance_atr", "invalidation_distance_atr", "target_distance_atr",
        "gross_rr", "breakout_level_pivot_age_minutes", "required_reward_atr",
    )

    entry_reference_diagnostic: dict[str, Any] = {}
    cost_rate = _frozen_cost_rate(frozen)
    reference_getters: tuple[
        tuple[str, Callable[[dict[str, Any]], float]], ...
    ] = (
        ("frozen_midpoint_entry", lambda row: float(row["entry_reference"])),
        ("final_confirmation_close", lambda row: float(row["close"])),
        ("ema7_at_candidate", lambda row: float(row["ema7"])),
    )
    for reference, getter in reference_getters:
        ref_rows: list[dict[str, Any]] = []
        for row in tp_post:
            ref = getter(row)
            stop_distance = abs(ref - float(row["frozen_stop"]))
            target_distance = abs(float(row["target"]) - ref)
            atr = float(row["atr"])
            net = (
                _net_rr(target_distance / ref, stop_distance / ref, cost_rate)
                if ref > 0 and stop_distance > 0
                else None
            )
            ref_rows.append(
                {
                    "reference": reference,
                    "stop_distance_atr": stop_distance / atr if atr > 0 else None,
                    "target_distance_atr": target_distance / atr if atr > 0 else None,
                    "gross_rr": (
                        target_distance / stop_distance if stop_distance > 0 else None
                    ),
                    "net_rr": net,
                    "net_rr_pass": net is not None and net >= frozen.strategy.rr_min,
                }
            )
        entry_reference_diagnostic[reference] = {
            "distributions": {
                field: _distribution(_values(ref_rows, field))
                for field in ("stop_distance_atr", "target_distance_atr", "gross_rr", "net_rr")
            },
            "net_rr_pass_count": sum(bool(row["net_rr_pass"]) for row in ref_rows),
            "net_rr_pass_rate": (
                sum(bool(row["net_rr_pass"]) for row in ref_rows) / len(ref_rows)
                if ref_rows
                else None
            ),
        }
    supplementary_rows: list[dict[str, Any]] = []
    for row in tp_post:
        extreme = row.get("pullback_local_extreme")
        if extreme is None:
            continue
        ref = float(extreme)
        stop_distance = abs(ref - float(row["frozen_stop"]))
        target_distance = abs(float(row["target"]) - ref)
        atr = float(row["atr"])
        net = (
            _net_rr(target_distance / ref, stop_distance / ref, cost_rate)
            if ref > 0 and stop_distance > 0
            else None
        )
        supplementary_rows.append(
            {
                "reference": "pullback_extreme_entry_supplementary",
                "stop_distance_atr": stop_distance / atr if atr > 0 else None,
                "target_distance_atr": target_distance / atr if atr > 0 else None,
                "gross_rr": target_distance / stop_distance if stop_distance > 0 else None,
                "net_rr": net,
                "net_rr_pass": net is not None and net >= frozen.strategy.rr_min,
            }
        )
    entry_reference_diagnostic["pullback_extreme_entry_supplementary"] = {
        "distributions": {
            field: _distribution(_values(supplementary_rows, field))
            for field in ("stop_distance_atr", "target_distance_atr", "gross_rr", "net_rr")
        },
        "net_rr_pass_count": sum(bool(row["net_rr_pass"]) for row in supplementary_rows),
        "net_rr_pass_rate": (
            sum(bool(row["net_rr_pass"]) for row in supplementary_rows)
            / len(supplementary_rows)
            if supplementary_rows
            else None
        ),
    }

    local_extreme_summary = {
        "scope_b_tp_post_factor": {
            "distributions": {
                field: _distribution(_values(tp_post, field))
                for field in (
                    "local_extreme_stop_distance_atr",
                    "local_extreme_stop_gross_rr",
                    "local_extreme_stop_net_rr",
                )
            },
            "net_rr_pass_count": sum(
                bool(row["local_extreme_stop_net_rr_pass"]) for row in tp_post
            ),
            "net_rr_pass_rate": (
                sum(bool(row["local_extreme_stop_net_rr_pass"]) for row in tp_post)
                / len(tp_post)
                if tp_post
                else None
            ),
        },
        "scope_a_tp_pattern": {
            "distributions": {
                field: _distribution(_values(tp_pattern, field))
                for field in (
                    "local_extreme_stop_distance_atr",
                    "local_extreme_stop_gross_rr",
                    "local_extreme_stop_net_rr",
                )
            },
            "net_rr_pass_count": sum(
                bool(row["local_extreme_stop_net_rr_pass"]) for row in tp_pattern
            ),
            "net_rr_pass_rate": (
                sum(bool(row["local_extreme_stop_net_rr_pass"]) for row in tp_pattern)
                / len(tp_pattern)
                if tp_pattern
                else None
            ),
        },
    }

    tp_vs_br_comparison: dict[str, Any] = {}
    for scope, rows, fields, predicate in (
        ("TP_POST_FACTOR", tp_post, tp_core_fields, lambda item: item["in_scope_b"]),
        (
            "BR_POST_FACTOR",
            br_post,
            br_core_fields,
            lambda item: item["scope"] == "BR_POST_FACTOR",
        ),
        (
            "BR_RISK_PASS",
            br_risk,
            br_core_fields,
            lambda item: item["scope"] == "BR_RISK_PASS",
        ),
    ):
        setup = rows[0]["setup"] if rows else None
        target_reach_rows = (
            [
                item
                for item in reachability_rows
                if predicate(item)
                and item["setup"] == setup
                and item["threshold_label"] == "frozen_structural_target"
            ]
            if setup is not None
            else []
        )
        tp_vs_br_comparison[scope] = {
            "candidate_count": len(rows),
            "geometry": _summary_block(rows, fields, splits=("direction",)),
            "target_reached_before_stop_12h": _reach_rate(target_reach_rows),
        }

    barrier_summary = {
        "scope_a_tp_pattern": {
            "candidate_count": len(tp_pattern),
            "barrier_incidence": (
                sum(row["first_barrier_distance_atr"] is not None for row in tp_pattern)
                / len(tp_pattern)
                if tp_pattern
                else None
            ),
            "first_barrier_distance_atr": _distribution(
                _values(tp_pattern, "first_barrier_distance_atr")
            ),
            "barrier_count_before_2_5_atr": _distribution(
                _values(tp_pattern, "confirmed_barriers_before_2_5_atr_target")
            ),
            "first_barrier_reached_in_12h": sum(
                bool(row["first_confirmed_barrier_reached_in_12h"])
                for row in barrier_rows
                if row["in_scope_a"]
            ),
            "max_continuation_after_barrier_atr": _distribution(
                _values(
                    [row for row in barrier_rows if row["in_scope_a"]],
                    "max_continuation_excursion_after_barrier_atr",
                )
            ),
        },
    }

    result: dict[str, Any] = {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "start_ms": DEV_START_MS,
            "end_ms_exclusive": DEV_END_MS,
        },
        "denominator_correctness": {
            "trend_up": denominator["TREND_UP"],
            "trend_down": denominator["TREND_DOWN"],
            "trend_decisions": denominator["TREND_DECISION"],
        },
        "scope_counts": counts,
        "invalidation_age_summary": {
            "scope_a_tp_pattern": _summary_block(tp_pattern, tp_core_fields),
            "scope_b_tp_post_factor": _summary_block(tp_post, tp_core_fields),
        },
        "pullback_geometry_summary": {
            "scope_a_tp_pattern": _summary_block(tp_pattern, pullback_fields),
            "scope_b_tp_post_factor": _summary_block(tp_post, pullback_fields),
        },
        "entry_lag_summary": {
            "scope_a_tp_pattern": _summary_block(tp_pattern, lag_fields),
            "scope_b_tp_post_factor": _summary_block(tp_post, lag_fields),
        },
        "target_geometry_summary": {
            "scope_a_tp_pattern": _summary_block(tp_pattern, target_fields),
            "scope_b_tp_post_factor": _summary_block(tp_post, target_fields),
        },
        "local_extreme_stop_diagnostic": local_extreme_summary,
        "entry_reference_diagnostic": entry_reference_diagnostic,
        "excursion_summary": mfe_mae_summary,
        "reachability_summary": reachability_summary,
        "barrier_summary": barrier_summary,
        "tp_vs_br_comparison": tp_vs_br_comparison,
        "year_direction_stability": {
            "tp_post_factor_invalidation_age_minutes": _summary_block(
                tp_post, ("invalidation_pivot_age_minutes",), splits=("direction", "year")
            ),
            "tp_post_factor_frozen_stop_distance_atr": _summary_block(
                tp_post, ("frozen_stop_distance_atr",), splits=("direction", "year")
            ),
            "tp_post_factor_target_distance_atr": _summary_block(
                tp_post, ("target_distance_atr",), splits=("direction", "year")
            ),
            "tp_post_factor_required_reward_atr": _summary_block(
                tp_post, ("required_reward_atr",), splits=("direction", "year")
            ),
        },
        "hypothesis_verdicts": {},
        "overall_status": "GEOMETRY_AUDIT_COMPLETE",
        "tp_geometry_rows": tp_rows,
        "br_geometry_reference_rows": br_rows,
        "excursion_rows": excursion_rows,
        "reachability_rows": reachability_rows,
        "barrier_rows": barrier_rows,
        "trend_control_rows": trend_control_rows,
        "breakout_qualification_rows": breakout_qualification_rows,
        "performance": {
            "decision_loop_seconds": loop_runtime,
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        },
    }
    result["hypothesis_verdicts"] = _hypothesis_verdicts(result, tp_post)
    return result


def _h6_distance_exceeds_local_extreme_across_years(
    tp_post: list[dict[str, Any]], minimum_per_year: int = 5
) -> bool | None:
    years: dict[str, list[tuple[float, float]]] = {}
    for row in tp_post:
        invalidation = row.get("invalidation_distance_atr")
        extreme = row.get("local_extreme_distance_atr")
        if invalidation is None or extreme is None:
            continue
        years.setdefault(str(row["year"]), []).append((float(invalidation), float(extreme)))
    checked = 0
    for pairs in years.values():
        if len(pairs) < minimum_per_year:
            continue
        checked += 1
        median_invalidation = statistics.median(pair[0] for pair in pairs)
        median_extreme = statistics.median(pair[1] for pair in pairs)
        if median_invalidation - median_extreme < 0.5:
            return False
    return True if checked >= 2 else None


def _hypothesis_verdicts(
    result: dict[str, Any], tp_post: list[dict[str, Any]]
) -> dict[str, Any]:
    verdicts: dict[str, Any] = {}
    invalidation_age = _distribution(
        _values(tp_post, "invalidation_pivot_age_minutes")
    )["median"]
    invalidation_distance = _distribution(
        _values(tp_post, "invalidation_distance_atr")
    )["median"]
    local_extreme_distance = _distribution(
        _values(tp_post, "local_extreme_distance_atr")
    )["median"]
    target_distance = _distribution(_values(tp_post, "target_distance_atr"))["median"]
    required_reward = _distribution(_values(tp_post, "required_reward_atr"))["median"]
    touch_move = _distribution(
        _values(tp_post, "touch_to_candidate_price_move_atr")
    )["median"]
    extreme_move = _distribution(
        _values(tp_post, "pullback_extreme_to_final_close_atr")
    )["median"]
    local_pass_rate = result["local_extreme_stop_diagnostic"]["scope_b_tp_post_factor"][
        "net_rr_pass_rate"
    ] or 0.0
    best_ref_pass = max(
        item["net_rr_pass_rate"] or 0.0
        for item in result["entry_reference_diagnostic"].values()
    )
    extreme_ref_pass = (
        result["entry_reference_diagnostic"][
            "pullback_extreme_entry_supplementary"
        ]["net_rr_pass_rate"]
        or 0.0
    )
    two_half_atr = result["reachability_summary"]["scope_b_tp_post_factor"]["atr_2.5"]

    def numeric(value: object) -> float:
        return float(value) if isinstance(value, (int, float)) else 0.0

    distance_exceeds = _h6_distance_exceeds_local_extreme_across_years(tp_post)
    if distance_exceeds is True:
        verdicts["H6"] = "SUPPORTED"
    elif distance_exceeds is False:
        verdicts["H6"] = "FALSIFIED"
    elif local_pass_rate > 0.10:
        verdicts["H6"] = "INCONCLUSIVE_MECHANISM"
    else:
        verdicts["H6"] = "INCONCLUSIVE_LOW_SAMPLE"

    if (
        numeric(extreme_move) >= 0.4 * numeric(target_distance)
        and numeric(target_distance) > 0
    ) or numeric(extreme_ref_pass) > 0.10:
        verdicts["H7"] = "SUPPORTED"
    elif best_ref_pass <= 0.05 and numeric(extreme_move) < 0.2 * max(
        numeric(target_distance), 1e-9
    ):
        verdicts["H7"] = "FALSIFIED"
    else:
        verdicts["H7"] = "INCONCLUSIVE_MECHANISM"

    reach_before_stop_2_5 = two_half_atr["reached_before_stop_rate"] or 0.0
    if numeric(target_distance) < 1.5 and numeric(required_reward) > 5.0:
        verdicts["H8"] = "SUPPORTED"
    elif reach_before_stop_2_5 > 0.5:
        verdicts["H8"] = "FALSIFIED"
    else:
        verdicts["H8"] = "INCONCLUSIVE_MECHANISM"
    verdicts["evidence"] = {
        "tp_post_factor_count": len(tp_post),
        "invalidation_pivot_age_minutes_median": invalidation_age,
        "invalidation_distance_atr_median": invalidation_distance,
        "local_extreme_distance_atr_median": local_extreme_distance,
        "target_distance_atr_median": target_distance,
        "required_reward_atr_median": required_reward,
        "touch_to_candidate_price_move_atr_median": touch_move,
        "pullback_extreme_to_final_close_atr_median": extreme_move,
        "local_extreme_stop_pass_rate": local_pass_rate,
        "best_entry_reference_pass_rate": best_ref_pass,
        "pullback_extreme_entry_pass_rate": extreme_ref_pass,
        "atr_2_5_reached_before_stop_rate": reach_before_stop_2_5,
        "h6_distance_exceeds_local_extreme_across_years": distance_exceeds,
    }
    return verdicts


def write_v033_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    *,
    seed: int = 33,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable geometry run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    tp_rows = result.pop("tp_geometry_rows")
    br_rows = result.pop("br_geometry_reference_rows")
    excursion_rows = result.pop("excursion_rows")
    reachability_rows = result.pop("reachability_rows")
    barrier_rows = result.pop("barrier_rows")
    result.pop("trend_control_rows", None)
    result.pop("breakout_qualification_rows", None)
    for rows in (tp_rows, br_rows, excursion_rows, reachability_rows, barrier_rows):
        assert_v033_development_only(rows)
    provenance = {
        "git_commit_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "strategy_version": config.runtime.strategy_version,
        "feature_version": config.runtime.feature_version,
        "config_hash": config.config_hash,
        "dataset_checksum": json.loads(manifest.read_text(encoding="utf-8"))[
            "checksum_sha256"
        ],
        "protocol_checksum": _sha256(protocol),
        "random_seed": seed,
        "validation_status": config.runtime.validation_status,
    }
    payload = {"provenance": provenance, **result}
    outputs = {
        "invalidation_age_summary.json": result["invalidation_age_summary"],
        "entry_lag_summary.json": result["entry_lag_summary"],
        "target_geometry_summary.json": result["target_geometry_summary"],
        "local_extreme_stop_diagnostic.json": result["local_extreme_stop_diagnostic"],
        "entry_reference_diagnostic.json": result["entry_reference_diagnostic"],
        "reachability_summary.json": result["reachability_summary"],
        "barrier_summary.json": result["barrier_summary"],
        "tp_vs_br_comparison.json": result["tp_vs_br_comparison"],
        "experiment_summary.json": payload,
    }
    for name, value in outputs.items():
        (target / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    pq.write_table(pa.Table.from_pylist(tp_rows), target / "tp_geometry.parquet")
    pq.write_table(pa.Table.from_pylist(br_rows), target / "br_geometry_reference.parquet")
    pq.write_table(
        pa.Table.from_pylist(excursion_rows), target / "excursion_1h_2h_4h_8h_12h.parquet"
    )
    pq.write_table(pa.Table.from_pylist(reachability_rows), target / "reachability.parquet")
    pq.write_table(pa.Table.from_pylist(barrier_rows), target / "barrier_audit.parquet")
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "data_manifest.json")
    return target
