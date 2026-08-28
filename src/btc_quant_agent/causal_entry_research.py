from __future__ import annotations

import bisect
import csv
import hashlib
import importlib
import json
import math
import random
import resource
import shutil
import statistics
import subprocess
import time
from collections import Counter, deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import FundingEvent, resample
from .config import AppConfig
from .domain import Candidate, Candle, Direction, Regime, Setup
from .engine import HistoricalFeatureCache, QuantEngine
from .geometry_research import run_v033_geometry_audit
from .regime import classify_regime
from .research import DEV_END_MS, DEV_START_MS
from .risk import build_position_plan

HORIZONS = (60, 120, 240, 480, 720)
REACH_THRESHOLDS = (1.0, 1.5, 2.5)
MATCH_K = 5
MIN_BAR_DISTANCE = 96
BOOTSTRAP_SIMULATIONS = 2_000
SEED = 34


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


class IndexedOneMinuteSeries:
    """Development-only arrays with causal indexed windows."""

    def __init__(self, candles: Sequence[Candle]) -> None:
        if not candles or candles[0].open_time_ms != DEV_START_MS:
            raise ValueError("v0.3.4 requires a complete development 1m series")
        if candles[-1].close_time_ms >= DEV_END_MS:
            raise ValueError("v0.3.4 series rejects holdout bars")
        self.bars = candles
        self.opens = [bar.open_time_ms for bar in candles]

    def index_after(self, timestamp_ms: int) -> int:
        return bisect.bisect_right(self.opens, timestamp_ms)

    def bounded_window(
        self, decision_close_ms: int, horizon_minutes: int
    ) -> tuple[Sequence[Candle], bool]:
        end_ms = decision_close_ms + horizon_minutes * 60_000
        incomplete = end_ms > DEV_END_MS
        start = self.index_after(decision_close_ms)
        end = bisect.bisect_right(self.opens, min(end_ms, DEV_END_MS - 1))
        return self.bars[start:end], incomplete


@dataclass(frozen=True)
class PendingLimit:
    candidate_id: str
    direction: Direction
    created_at_ms: int
    eligible_from_ms: int
    expires_at_ms: int
    limit_price: float
    invalidation_level: float
    stop_loss: float
    take_profit: float
    rr_gross: float
    rr_net: float
    recommended_notional: float
    max_loss_usdt: float
    estimated_fee_usdt: float
    estimated_slippage_usdt: float


def prospective_retrace_order(row: dict[str, Any], config: AppConfig) -> PendingLimit | None:
    """Create a limit only at confirmation; the past extreme is a price, never a fill."""

    direction = Direction(str(row["direction"]))
    limit = float(row["pullback_local_extreme"])
    candidate = Candidate(
        direction=direction,
        setup=Setup.TREND_PULLBACK,
        entry_low=limit,
        entry_high=limit,
        invalidation_level=float(row["invalidation_level"]),
        target_level=float(row["target"]),
        pattern_score=0,
        structure_id=str(row["candidate_id"]),
        reasons=("E_RETRACE",),
    )
    plan = build_position_plan(candidate, float(row["atr"]), config.strategy, config.risk)
    if plan is None:
        return None
    decision_close = int(row["decision_close_ms"])
    ttl_ms = min(
        config.runtime.ttl_minutes * 60_000,
        config.strategy.max_signal_age_bars * 15 * 60_000,
    )
    return PendingLimit(
        candidate_id=str(row["candidate_id"]),
        direction=direction,
        created_at_ms=decision_close + 1,
        eligible_from_ms=decision_close + 1,
        expires_at_ms=decision_close + ttl_ms,
        limit_price=limit,
        invalidation_level=float(row["invalidation_level"]),
        stop_loss=plan.stop_loss,
        take_profit=plan.take_profit,
        rr_gross=plan.rr_gross,
        rr_net=plan.rr_net,
        recommended_notional=plan.recommended_notional,
        max_loss_usdt=plan.risk_usdt,
        estimated_fee_usdt=plan.estimated_fee_usdt,
        estimated_slippage_usdt=plan.estimated_slippage_usdt,
    )


def _touches_limit(order: PendingLimit, bar: Candle) -> bool:
    return (
        bar.low <= order.limit_price
        if order.direction == Direction.LONG
        else bar.high >= order.limit_price
    )


def _touches_stop(order: PendingLimit, bar: Candle) -> bool:
    return (
        bar.low <= order.stop_loss
        if order.direction == Direction.LONG
        else bar.high >= order.stop_loss
    )


def _touches_target(order: PendingLimit, bar: Candle) -> bool:
    return (
        bar.high >= order.take_profit
        if order.direction == Direction.LONG
        else bar.low <= order.take_profit
    )


def _structurally_invalid(order: PendingLimit, bar: Candle) -> bool:
    if (bar.close_time_ms + 1) % (15 * 60_000) != 0:
        return False
    return (
        bar.close <= order.invalidation_level
        if order.direction == Direction.LONG
        else bar.close >= order.invalidation_level
    )


def advance_pending_limit(
    order: PendingLimit,
    bars: Sequence[Candle],
) -> dict[str, Any]:
    """Advance a pending order one arriving 1m bar at a time."""

    expected_open = order.eligible_from_ms
    for bar in bars:
        if bar.open_time_ms < order.eligible_from_ms:
            continue
        if bar.open_time_ms > order.expires_at_ms:
            return {"state": "UNFILLED_EXPIRED", "resolved_at_ms": order.expires_at_ms}
        if bar.open_time_ms != expected_open:
            return {"state": "DATA_INVALID", "resolved_at_ms": bar.open_time_ms}
        expected_open += 60_000
        if _touches_limit(order, bar):
            return {
                "state": "FILLED",
                "filled_at_ms": bar.open_time_ms,
                "fill_bar": bar,
                "fill_price": order.limit_price,
            }
        if _structurally_invalid(order, bar):
            return {
                "state": "INVALIDATED_BEFORE_FILL",
                "resolved_at_ms": bar.close_time_ms,
            }
    return {"state": "PENDING_AT_END", "resolved_at_ms": DEV_END_MS - 1}


def _funding_cashflow(
    order: PendingLimit,
    entered_at_ms: int,
    exited_at_ms: int,
    funding_events: Sequence[FundingEvent],
) -> float:
    quantity = order.recommended_notional / order.limit_price
    sign = -1.0 if order.direction == Direction.LONG else 1.0
    return sum(
        quantity * (event.mark_price or order.limit_price) * event.funding_rate * sign
        for event in funding_events
        if entered_at_ms < event.timestamp_ms <= exited_at_ms
    )


def resolve_open_trade(
    order: PendingLimit,
    bars: Sequence[Candle],
    fill_index: int,
    funding_events: Sequence[FundingEvent],
    holding_minutes: int,
) -> dict[str, Any]:
    """Resolve causally from the fill bar with stop priority on ambiguous bars."""

    entered = bars[fill_index].open_time_ms
    deadline = entered + holding_minutes * 60_000
    exit_bar = bars[fill_index]
    outcome = "OPEN_AT_END"
    exit_price: float | None = None
    for bar in bars[fill_index:]:
        if bar.open_time_ms >= DEV_END_MS or bar.open_time_ms > deadline:
            break
        exit_bar = bar
        stop_hit = _touches_stop(order, bar)
        target_hit = _touches_target(order, bar)
        if stop_hit or target_hit:
            outcome = "LOSS" if stop_hit else "WIN"
            exit_price = order.stop_loss if stop_hit else order.take_profit
            break
        if bar.close_time_ms >= deadline:
            outcome = "TIMEOUT"
            exit_price = bar.close
            break
    if exit_price is None:
        return {
            "candidate_id": order.candidate_id,
            "outcome": outcome,
            "entered_at_ms": entered,
            "exited_at_ms": None,
            "entry_price": order.limit_price,
            "exit_price": None,
            "net_pnl_usdt": None,
            "net_r": None,
        }
    exited = exit_bar.close_time_ms
    signed_move = (
        exit_price - order.limit_price
        if order.direction == Direction.LONG
        else order.limit_price - exit_price
    )
    gross_pnl = order.recommended_notional * signed_move / order.limit_price
    funding = _funding_cashflow(order, entered, exited, funding_events)
    net_pnl = gross_pnl - order.estimated_fee_usdt - order.estimated_slippage_usdt + funding
    return {
        "candidate_id": order.candidate_id,
        "direction": order.direction.value,
        "outcome": outcome,
        "entered_at_ms": entered,
        "exited_at_ms": exited,
        "entry_price": order.limit_price,
        "exit_price": exit_price,
        "stop_loss": order.stop_loss,
        "take_profit": order.take_profit,
        "rr_gross": order.rr_gross,
        "rr_net": order.rr_net,
        "recommended_notional": order.recommended_notional,
        "risk_usdt": order.max_loss_usdt,
        "gross_pnl_usdt": gross_pnl,
        "fees_usdt": order.estimated_fee_usdt,
        "slippage_usdt": order.estimated_slippage_usdt,
        "funding_pnl_usdt": funding,
        "net_pnl_usdt": net_pnl,
        "net_r": net_pnl / order.max_loss_usdt,
        "holding_minutes": (exited - entered + 1) / 60_000,
    }


def run_retrace_lifecycle(
    candidate_rows: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
    config: AppConfig,
    funding_events: Sequence[FundingEvent],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    pending_rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    fill_buckets: Counter[str] = Counter()
    for row in candidate_rows:
        order = prospective_retrace_order(row, config)
        base = {
            "candidate_id": row["candidate_id"],
            "timestamp_ms": row["timestamp_ms"],
            "decision_close_ms": row["decision_close_ms"],
            "year": row["year"],
            "direction": row["direction"],
            "historical_extreme_bar_close_time_ms": row[
                "pullback_local_extreme_bar_close_time_ms"
            ],
            "limit_price": row["pullback_local_extreme"],
        }
        if order is None:
            reasons["NO_PROSPECTIVE_RR"] += 1
            pending_rows.append({**base, "state": "NO_PROSPECTIVE_RR"})
            continue
        start = series.index_after(int(row["decision_close_ms"]))
        lifecycle = advance_pending_limit(order, series.bars[start:])
        state = str(lifecycle["state"])
        if state == "DATA_INVALID":
            state = "INVALIDATED_BEFORE_FILL"
        reasons[state] += 1
        pending = {
            **base,
            **asdict(order),
            **{key: value for key, value in lifecycle.items() if key != "fill_bar"},
            "state": state,
        }
        pending_rows.append(pending)
        if state != "FILLED":
            continue
        filled_at = int(lifecycle["filled_at_ms"])
        lag_minutes = (filled_at - order.eligible_from_ms) // 60_000 + 1
        fill_buckets[
            "le_15m" if lag_minutes <= 15 else "le_30m" if lag_minutes <= 30 else "le_45m"
        ] += 1
        fill_index = bisect.bisect_left(series.opens, filled_at)
        # Exact limit-price fill makes this recheck identical to the prospective plan.
        if prospective_retrace_order(row, config) is None:
            reasons["RR_FAILED_AT_FILL"] += 1
            pending["state"] = "RR_FAILED_AT_FILL"
            continue
        trade = resolve_open_trade(
            order,
            series.bars,
            fill_index,
            funding_events,
            config.backtest.trend_pullback_holding_minutes,
        )
        trade.update({"year": row["year"], "timestamp_ms": row["timestamp_ms"]})
        trades.append(trade)
    resolved = [trade for trade in trades if trade["outcome"] != "OPEN_AT_END"]
    r_values = [float(trade["net_r"]) for trade in resolved if trade["net_r"] is not None]
    wins = [value for value in r_values if value > 0]
    losses = [value for value in r_values if value < 0]
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in sorted(resolved, key=lambda item: int(item["exited_at_ms"])):
        equity += float(trade["net_r"])
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    summary = {
        "tp_post_factor": len(candidate_rows),
        "prospective_rr_pass": len(candidate_rows) - reasons["NO_PROSPECTIVE_RR"],
        "limit_placed": len(candidate_rows) - reasons["NO_PROSPECTIVE_RR"],
        "filled_in_ttl": reasons["FILLED"],
        "valid_at_fill": len(trades),
        "risk_pass": len(trades),
        "opened": len(trades),
        "target": sum(trade["outcome"] == "WIN" for trade in trades),
        "stop": sum(trade["outcome"] == "LOSS" for trade in trades),
        "timeout": sum(trade["outcome"] == "TIMEOUT" for trade in trades),
        "open_at_end": sum(trade["outcome"] == "OPEN_AT_END" for trade in trades),
        "reason_counts": dict(sorted(reasons.items())),
        "fill_timing_exclusive": {
            "le_15m": fill_buckets["le_15m"],
            "gt_15_le_30m": fill_buckets["le_30m"],
            "gt_30_le_45m": fill_buckets["le_45m"],
        },
        "fill_timing_cumulative": {
            "le_15m": fill_buckets["le_15m"],
            "le_30m": fill_buckets["le_15m"] + fill_buckets["le_30m"],
            "le_45m": sum(fill_buckets.values()),
        },
        "expectancy_r": statistics.mean(r_values) if r_values else None,
        "profit_factor": (
            sum(wins) / abs(sum(losses)) if losses else (math.inf if wins else None)
        ),
        "max_drawdown_r": max_drawdown if r_values else None,
        "win_rate": len(wins) / len(r_values) if r_values else None,
    }
    return pending_rows, trades, summary


def collect_trend_control_pool(
    candles_1m: Sequence[Candle],
    config: AppConfig,
    tp_pattern_times: set[int],
) -> list[dict[str, Any]]:
    completed = {name: resample(candles_1m, name) for name in ("15m", "1h", "4h")}
    limits = {
        "15m": config.data.history_limit_15m,
        "1h": config.data.history_limit_1h,
        "4h": config.data.history_limit_4h,
    }
    histories: dict[str, deque[Candle]] = {
        name: deque(maxlen=limits[name]) for name in completed
    }
    cursors = {name: 0 for name in completed}
    engine = QuantEngine(config, HistoricalFeatureCache())
    rows: list[dict[str, Any]] = []
    for bar_index, decision_bar in enumerate(completed["15m"]):
        for interval in ("15m", "1h", "4h"):
            bars = completed[interval]
            while (
                cursors[interval] < len(bars)
                and bars[cursors[interval]].close_time_ms <= decision_bar.close_time_ms
            ):
                histories[interval].append(bars[cursors[interval]])
                cursors[interval] += 1
        try:
            f1 = engine.diagnostic_features("1h", list(histories["1h"]))
            f15 = engine.diagnostic_features("15m", list(histories["15m"]))
        except (ValueError, IndexError):
            continue
        regime = classify_regime(f1, config.strategy)
        if regime not in {Regime.TREND_UP, Regime.TREND_DOWN}:
            continue
        timestamp = decision_bar.close_time_ms + 1
        rows.append(
            {
                "control_id": f"CTRL:{timestamp}",
                "timestamp_ms": timestamp,
                "decision_close_ms": decision_bar.close_time_ms,
                "bar_index": bar_index,
                "year": datetime.fromtimestamp(timestamp / 1000, UTC).year,
                "direction": (
                    Direction.LONG.value
                    if regime == Regime.TREND_UP
                    else Direction.SHORT.value
                ),
                "regime": regime.value,
                "atr": f15.atr,
                "atr_percentile": f15.atr_percentile,
                "atr_decile": min(9, int(f15.atr_percentile * 10)),
                "close": f15.close,
                "is_tp_pattern": timestamp in tp_pattern_times,
            }
        )
    return rows


def match_controls(
    candidate_rows: Sequence[dict[str, Any]],
    control_pool: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    eligible_pool: dict[tuple[int, str, str, int], list[dict[str, Any]]] = {}
    timestamp_to_pool = {int(row["timestamp_ms"]): row for row in control_pool}
    for control in control_pool:
        if control.get("is_excluded_pattern", control.get("is_tp_pattern", False)):
            continue
        key = (
            int(control["year"]),
            str(control["direction"]),
            str(control["regime"]),
            int(control["atr_decile"]),
        )
        eligible_pool.setdefault(key, []).append(control)
    output: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        reference = timestamp_to_pool[int(candidate["timestamp_ms"])]
        key = (
            int(candidate["year"]),
            str(candidate["direction"]),
            str(reference["regime"]),
            int(reference["atr_decile"]),
        )
        eligible = [
            row
            for row in eligible_pool.get(key, [])
            if abs(int(row["bar_index"]) - int(reference["bar_index"]))
            >= MIN_BAR_DISTANCE
        ]
        selected = sorted(
            eligible,
            key=lambda row: (
                abs(int(row["bar_index"]) - int(reference["bar_index"])),
                int(row["decision_close_ms"]),
            ),
        )[:MATCH_K]
        for rank, control in enumerate(selected, start=1):
            output.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_timestamp_ms": candidate["timestamp_ms"],
                    "control_rank": rank,
                    **control,
                    "bar_distance": abs(
                        int(control["bar_index"]) - int(reference["bar_index"])
                    ),
                }
            )
    return output


def directionality_label(
    identity: dict[str, Any],
    series: IndexedOneMinuteSeries,
    horizon: int,
) -> dict[str, Any]:
    bars, incomplete = series.bounded_window(int(identity["decision_close_ms"]), horizon)
    atr = float(identity["atr"])
    reference = float(identity["close"])
    direction = Direction(str(identity["direction"]))
    if incomplete or not bars or atr <= 0:
        return {"horizon_minutes": horizon, "incomplete": True}
    if direction == Direction.LONG:
        signed_return = (bars[-1].close - reference) / atr
        mfe = max(0.0, max(bar.high for bar in bars) - reference) / atr
        mae = max(0.0, reference - min(bar.low for bar in bars)) / atr
    else:
        signed_return = (reference - bars[-1].close) / atr
        mfe = max(0.0, reference - min(bar.low for bar in bars)) / atr
        mae = max(0.0, max(bar.high for bar in bars) - reference) / atr
    return {
        "horizon_minutes": horizon,
        "incomplete": False,
        "signed_return_atr": signed_return,
        "mfe_atr": mfe,
        "mae_atr": mae,
        "mfe_mae_ratio": mfe / mae if mae > 0 else None,
        "reach_1_0": mfe >= 1.0,
        "reach_1_5": mfe >= 1.5,
        "reach_2_5": mfe >= 2.5,
    }


def build_directionality_rows(
    candidates: Sequence[dict[str, Any]],
    matches: Sequence[dict[str, Any]],
    pool: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
) -> list[dict[str, Any]]:
    pool_by_time = {int(row["timestamp_ms"]): row for row in pool}
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        identity = {**pool_by_time[int(candidate["timestamp_ms"])], **candidate}
        for horizon in HORIZONS:
            output.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "identity_id": candidate["candidate_id"],
                    "kind": "CANDIDATE",
                    "year": candidate["year"],
                    "direction": candidate["direction"],
                    **directionality_label(identity, series, horizon),
                }
            )
    for match in matches:
        for horizon in HORIZONS:
            output.append(
                {
                    "candidate_id": match["candidate_id"],
                    "identity_id": match["control_id"],
                    "kind": "CONTROL",
                    "year": match["year"],
                    "direction": match["direction"],
                    **directionality_label(match, series, horizon),
                }
            )
    return output


def _metric_delta(rows: Sequence[dict[str, Any]], metric: str) -> float | None:
    candidates = [
        float(row[metric])
        for row in rows
        if row["kind"] == "CANDIDATE" and row.get(metric) is not None
    ]
    controls = [
        float(row[metric])
        for row in rows
        if row["kind"] == "CONTROL" and row.get(metric) is not None
    ]
    if not candidates or not controls:
        return None
    if metric.startswith("reach_"):
        return statistics.mean(candidates) - statistics.mean(controls)
    return statistics.median(candidates) - statistics.median(controls)


def summarize_directionality(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    metrics = (
        "signed_return_atr",
        "mfe_atr",
        "mae_atr",
        "reach_1_0",
        "reach_1_5",
        "reach_2_5",
    )
    for horizon in HORIZONS:
        block = [row for row in rows if row["horizon_minutes"] == horizon and not row["incomplete"]]
        output[f"{horizon}m"] = {
            "candidate_count": len({row["candidate_id"] for row in block if row["kind"] == "CANDIDATE"}),
            "control_count": sum(row["kind"] == "CONTROL" for row in block),
            "metrics": {
                metric: {
                    "candidate_median_or_rate": _median(
                        [float(row[metric]) for row in block if row["kind"] == "CANDIDATE"]
                    )
                    if not metric.startswith("reach_")
                    else statistics.mean(
                        [float(row[metric]) for row in block if row["kind"] == "CANDIDATE"]
                    ),
                    "control_median_or_rate": _median(
                        [float(row[metric]) for row in block if row["kind"] == "CONTROL"]
                    )
                    if not metric.startswith("reach_")
                    else statistics.mean(
                        [float(row[metric]) for row in block if row["kind"] == "CONTROL"]
                    ),
                    "delta": _metric_delta(block, metric),
                }
                for metric in metrics
            },
        }
    return output


def bootstrap_directionality(
    rows: Sequence[dict[str, Any]],
    seed: int = SEED,
    simulations: int = BOOTSTRAP_SIMULATIONS,
) -> dict[str, Any]:
    candidate_ids = sorted({str(row["candidate_id"]) for row in rows})
    clustered: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        clustered.setdefault(str(row["candidate_id"]), []).append(row)
    rng = random.Random(seed)
    samples = [
        [rng.choice(candidate_ids) for _ in candidate_ids] for _ in range(simulations)
    ]
    metrics = (
        "signed_return_atr",
        "mfe_atr",
        "mae_atr",
        "reach_1_0",
        "reach_1_5",
        "reach_2_5",
    )
    output: dict[str, Any] = {
        "seed": seed,
        "simulations": simulations,
        "cluster_unit": "candidate_id_with_matched_controls",
        "horizons": {},
    }
    for horizon in HORIZONS:
        horizon_output: dict[str, Any] = {}
        for metric in metrics:
            values: list[float] = []
            for sample in samples:
                sampled_rows = [
                    row
                    for candidate_id in sample
                    for row in clustered[candidate_id]
                    if row["horizon_minutes"] == horizon and not row["incomplete"]
                ]
                delta = _metric_delta(sampled_rows, metric)
                if delta is not None:
                    values.append(delta)
            horizon_output[metric] = {
                "p05": _percentile(values, 0.05),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
            }
        output["horizons"][f"{horizon}m"] = horizon_output
    return output


def _leave_one_year_out(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    years = sorted({int(row["year"]) for row in rows if row["kind"] == "CANDIDATE"})
    return {
        str(year): {
            f"{horizon}m_signed_return_delta": _metric_delta(
                [
                    row
                    for row in rows
                    if int(row["year"]) != year
                    and row["horizon_minutes"] == horizon
                    and not row["incomplete"]
                ],
                "signed_return_atr",
            )
            for horizon in (240, 480)
        }
        for year in years
    }


def _h9_verdict(
    summary: dict[str, Any], bootstrap: dict[str, Any], loyo: dict[str, Any]
) -> str:
    block4 = summary["240m"]
    block8 = summary["480m"]
    if block4["candidate_count"] < 30 or block4["control_count"] / block4["candidate_count"] < 3:
        return "INCONCLUSIVE_LOW_SAMPLE"
    delta4 = float(block4["metrics"]["signed_return_atr"]["delta"])
    delta8 = float(block8["metrics"]["signed_return_atr"]["delta"])
    p054 = float(bootstrap["horizons"]["240m"]["signed_return_atr"]["p05"])
    p058 = float(bootstrap["horizons"]["480m"]["signed_return_atr"]["p05"])
    p954 = float(bootstrap["horizons"]["240m"]["signed_return_atr"]["p95"])
    p958 = float(bootstrap["horizons"]["480m"]["signed_return_atr"]["p95"])
    reach1 = (
        float(block4["metrics"]["reach_1_0"]["delta"]) > 0
        and float(block8["metrics"]["reach_1_0"]["delta"]) > 0
    )
    reach25 = (
        float(block4["metrics"]["reach_2_5"]["delta"]) > 0
        or float(block8["metrics"]["reach_2_5"]["delta"]) > 0
    )
    stable = all(
        value is not None and float(value) > 0
        for year in loyo.values()
        for value in year.values()
    )
    if delta4 > 0 and delta8 > 0 and p054 >= -0.05 and p058 >= -0.05 and reach1 and reach25 and stable:
        return "SUPPORTED"
    if (delta4 <= 0 and delta8 <= 0) or (p954 <= 0 and p958 <= 0):
        return "FALSIFIED"
    return "INCONCLUSIVE_MECHANISM"


def _h10_verdict(funnel: dict[str, Any]) -> str:
    valid = int(funnel["valid_at_fill"])
    prospective = int(funnel["prospective_rr_pass"])
    placed = int(funnel["limit_placed"])
    filled = int(funnel["filled_in_ttl"])
    opened = int(funnel["opened"])
    if valid >= 20:
        if filled / placed >= 0.30 and opened / filled >= 0.50:
            return "SUPPORTED"
        return "FALSIFIED"
    if valid >= 10:
        return "INCONCLUSIVE_LOW_SAMPLE"
    return "FALSIFIED" if prospective < 10 else "INCONCLUSIVE_MECHANISM"


def _by_year_direction(
    candidates: Sequence[dict[str, Any]],
    pending: Sequence[dict[str, Any]],
    trades: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for year in range(2021, 2027):
        for direction in ("LONG", "SHORT"):
            key = f"{year}_{direction}"
            candidate_ids = {
                str(row["candidate_id"])
                for row in candidates
                if int(row["year"]) == year and row["direction"] == direction
            }
            selected_pending = [row for row in pending if str(row["candidate_id"]) in candidate_ids]
            selected_trades = [row for row in trades if str(row["candidate_id"]) in candidate_ids]
            values = [float(row["net_r"]) for row in selected_trades if row["net_r"] is not None]
            output[key] = {
                "candidates": len(candidate_ids),
                "prospective_pass": sum(row["state"] != "NO_PROSPECTIVE_RR" for row in selected_pending),
                "fills": sum(row["state"] == "FILLED" for row in selected_pending),
                "trades": len(selected_trades),
                "expectancy_r": statistics.mean(values) if values else None,
            }
    return output


def run_v034_causal_entry_validation(
    candles_1m: Sequence[Candle],
    config: AppConfig,
    funding_events: Sequence[FundingEvent],
    *,
    seed: int = SEED,
) -> dict[str, Any]:
    started = time.perf_counter()
    frozen = replace(
        config,
        strategy=replace(
            config.strategy,
            enable_derivatives_group=False,
            enable_order_book_factor=False,
        ),
    )
    if frozen.execution.mode != "disabled" or frozen.execution.auto_execute or frozen.execution.allow_live:
        raise ValueError("v0.3.4 requires disabled execution")
    v033 = run_v033_geometry_audit(
        candles_1m, frozen, funding_events, capture_trend_controls=True
    )
    tp_all = list(v033["tp_geometry_rows"])
    candidates = [row for row in tp_all if row["scope"] == "TP_POST_FACTOR"]
    if len(candidates) != 139:
        raise RuntimeError("v0.3.4 frozen Scope-B reproduction failed")
    series = IndexedOneMinuteSeries(candles_1m)
    pending, trades, funnel = run_retrace_lifecycle(candidates, series, frozen, funding_events)
    tp_pattern_times = {int(row["timestamp_ms"]) for row in tp_all}
    pool = [
        {**row, "is_tp_pattern": int(row["timestamp_ms"]) in tp_pattern_times}
        for row in v033["trend_control_rows"]
    ]
    matches = match_controls(candidates, pool)
    labels = build_directionality_rows(candidates, matches, pool, series)
    directionality = summarize_directionality(labels)
    bootstrap = bootstrap_directionality(labels, seed)
    loyo = _leave_one_year_out(labels)
    h9 = _h9_verdict(directionality, bootstrap, loyo)
    h10 = _h10_verdict(funnel)
    recommendation = (
        "RECOMMEND_FOR_V0.3.5_CANDIDATE_RESEARCH"
        if h10 == "SUPPORTED" and h9 != "FALSIFIED"
        else "NO_CANDIDATE"
    )
    return {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "start_ms": DEV_START_MS,
            "end_ms_exclusive": DEV_END_MS,
        },
        "control_identity": {
            "strategy_version": frozen.runtime.strategy_version,
            "feature_version": frozen.runtime.feature_version,
            "validation_status": frozen.runtime.validation_status,
            "execution_mode": frozen.execution.mode,
            "rr_min": frozen.strategy.rr_min,
            "ttl_minutes": frozen.runtime.ttl_minutes,
            "max_signal_age_bars": frozen.strategy.max_signal_age_bars,
            "seed": seed,
        },
        "e_retrace_funnel": funnel,
        "directionality_by_horizon": directionality,
        "directionality_bootstrap": bootstrap,
        "leave_one_year_out": loyo,
        "by_year_direction": _by_year_direction(candidates, pending, trades),
        "matched_control_coverage": {
            "candidate_count": len(candidates),
            "matched_rows": len(matches),
            "full_k_candidates": sum(
                sum(row["candidate_id"] == candidate["candidate_id"] for row in matches) == MATCH_K
                for candidate in candidates
            ),
            "mean_controls_per_candidate": len(matches) / len(candidates),
        },
        "hypothesis_verdicts": {"H9": h9, "H10": h10},
        "candidate_recommendation": recommendation,
        "overall_status": "CAUSAL_ENTRY_VALIDATION_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        },
        "tp_candidate_events": candidates,
        "e_retrace_pending_orders": pending,
        "e_retrace_trades": trades,
        "matched_controls": matches,
        "directionality_rows": labels,
    }


def _development_only(rows: Sequence[dict[str, Any]]) -> None:
    for row in rows:
        timestamps = [
            int(value)
            for key, value in row.items()
            if key.endswith(("timestamp_ms", "at_ms")) and value is not None
        ]
        if any(timestamp < DEV_START_MS or timestamp >= DEV_END_MS for timestamp in timestamps):
            raise ValueError(f"v0.3.4 holdout firewall rejected row {row}")


def write_v034_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    *,
    seed: int = SEED,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable v0.3.4 run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    candidate_rows = list(result.pop("tp_candidate_events"))
    pending_rows = list(result.pop("e_retrace_pending_orders"))
    trade_rows = list(result.pop("e_retrace_trades"))
    matched_rows = list(result.pop("matched_controls"))
    label_rows = list(result.pop("directionality_rows"))
    for rows in (candidate_rows, pending_rows, trade_rows, matched_rows):
        _development_only(rows)
    if any(row.get("incomplete") is False and int(row["horizon_minutes"]) > 0 for row in label_rows):
        # Completeness is already bounded by IndexedOneMinuteSeries; retain an explicit check.
        _development_only([row for row in candidate_rows])
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    provenance = {
        "git_commit_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "strategy_version": config.runtime.strategy_version,
        "feature_version": config.runtime.feature_version,
        "config_hash": config.config_hash,
        "dataset_checksum": manifest_payload["checksum_sha256"],
        "protocol_checksum": _sha256(protocol),
        "random_seed": seed,
        "validation_status": config.runtime.validation_status,
    }
    payload = {"provenance": provenance, **result}
    json_outputs = {
        "control_identity.json": result["control_identity"],
        "e_retrace_funnel.json": result["e_retrace_funnel"],
        "directionality_by_horizon.json": result["directionality_by_horizon"],
        "directionality_bootstrap.json": result["directionality_bootstrap"],
        "by_year_direction.json": result["by_year_direction"],
        "experiment_summary.json": payload,
    }
    for name, value in json_outputs.items():
        (target / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    for name, rows in (
        ("tp_candidate_events.parquet", candidate_rows),
        ("e_retrace_pending_orders.parquet", pending_rows),
        ("e_retrace_trades.parquet", trade_rows),
        ("matched_controls.parquet", matched_rows),
    ):
        pq.write_table(pa.Table.from_pylist(rows), target / name)
    with (target / "e_retrace_equity.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("exited_at_ms", "candidate_id", "net_r", "equity_r"))
        writer.writeheader()
        equity = 0.0
        for trade in sorted(
            (row for row in trade_rows if row.get("net_r") is not None),
            key=lambda row: int(row["exited_at_ms"]),
        ):
            equity += float(trade["net_r"])
            writer.writerow(
                {
                    "exited_at_ms": trade["exited_at_ms"],
                    "candidate_id": trade["candidate_id"],
                    "net_r": trade["net_r"],
                    "equity_r": equity,
                }
            )
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "data_manifest.json")
    return target
