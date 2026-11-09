"""Actual causal daily+4H S1 compiler, deliberately synthetic-only in RC V1."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Literal, cast

import pandas as pd

from .. import indicators
from ..structure import confirmed_pivots, structure_label
from .config import StrategyConfig
from .core import fingerprint
from .factors import FeaturePipeline
from .rc_models import PRODUCT, STRATEGY_VERSION, RCDecision, RCPlan, frozen_contract
from .rc_source import asof
from .strategies import direction
from .swing import INTERVALS, SwingPolicy, closed_bar_errors


def features(bars):
    candles = [b.candle for b in bars]
    close = [c.close for c in candles]
    high, low = [c.high for c in candles], [c.low for c in candles]
    fast, slow = indicators.ema(close, 10), indicators.ema(close, 30)
    state = (
        "TREND_UP"
        if fast[-1] > slow[-1] and slow[-1] > slow[-4]
        else "TREND_DOWN"
        if fast[-1] < slow[-1] and slow[-1] < slow[-4]
        else "RANGE"
    )
    return {
        "regime": state,
        "ema10": fast[-1],
        "ema30": slow[-1],
        "ema30_slope3": slow[-1] - slow[-4],
        "atr14": indicators.atr(high, low, close, 14)[-1],
        "adx14": indicators.adx(high, low, close, 14)[-1],
        "last_completed_end_ms": bars[-1].end_ms,
    }


def decide_s1(*, symbol, trigger_ms, decision_ms, receipts=(), source_blocked=False, holding_hours=24):
    return compile_s1(
        symbol=symbol,
        trigger_ms=trigger_ms,
        decision_ms=decision_ms,
        receipts=receipts,
        source_blocked=source_blocked,
        holding_hours=holding_hours,
    )


def compile_s1(
    *,
    symbol,
    trigger_ms,
    decision_ms,
    receipts=(),
    source_blocked=False,
    holding_hours=24,
    asof_reader=asof,
    decision_factory=RCDecision,
    product_id=PRODUCT,
    cost_label="SYNTHETIC_ADVERSE_FEE_SPREAD_SLIPPAGE_FUNDING_CARRY_PROJECTION_NOT_EXECUTABLE_R",
    source_reason="SYNTHETIC_MARKET_SIDE_ONLY_ACCOUNT_VETO",
    bar_policy=None,
):
    """Existing strategy calculation with explicit source and result-schema boundaries."""
    spec = frozen_contract()
    if type(holding_hours) is not int or not 4 <= holding_hours <= 120:
        raise ValueError("S1_HOLDING_HORIZON_REQUIRES_4_TO_120_HOURS")
    policy = SwingPolicy() if bar_policy is None else bar_policy
    rows, errors = asof_reader(receipts, symbol, trigger_ms, decision_ms)
    bars = [r.bar for r in rows]
    prefix_hash = fingerprint([r.model_dump(mode="json") for r in rows])
    base = dict(
        symbol=symbol,
        trigger_close_ms=trigger_ms,
        decision_ms=decision_ms,
        scheduled_review_ms=policy.next_review(decision_ms),
        prefix_sha256=prefix_hash,
        receipt_ids=tuple(r.identity for r in rows),
    )
    diagnostics = {"optional_1H": "ABSENT_NO_URGENCY", "holding_hours": holding_hours}

    def result(state, reasons, **extra):
        return decision_factory(
            **base, market_state=state, reasons=tuple(reasons), diagnostics=diagnostics, **extra
        )

    if source_blocked:
        return result("SOURCE_BLOCKED", ["SOURCE_STOP_NO_NEW_ELIGIBILITY"])
    errors += closed_bar_errors(
        bars, symbol=symbol, decision_ms=decision_ms, trigger_close_ms=trigger_ms, policy=policy
    )
    if errors:
        return result("DATA_UNAVAILABLE", tuple(dict.fromkeys(errors)))
    groups = {i: [b for b in bars if b.candle.interval == i] for i in INTERVALS}
    daily, four = features(groups["1D"]), features(groups["4H"])
    diagnostics.update({"1D": daily, "4H": four})
    if daily["regime"] != four["regime"] or daily["regime"] not in ("TREND_UP", "TREND_DOWN"):
        return result("NO_SETUP", ["DAILY_4H_TREND_NOT_ALIGNED"])
    candles = [b.candle for b in groups["4H"]]
    frame = pd.DataFrame(
        [
            {
                "ts": c.close_time_ms,
                "available_ts": c.available_at_ms,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )
    pipeline = FeaturePipeline({symbol: frame}, symbol)
    side = direction(
        pipeline,
        cast(
            Any,
            SimpleNamespace(candle=candles[-1], decision_ts=decision_ms, spec=SimpleNamespace(symbol=symbol)),
        ),
        len(candles) - 1,
        StrategyConfig(id="trend_pullback"),
    )
    expected = "LONG" if daily["regime"] == "TREND_UP" else "SHORT"
    if side != expected:
        return result("NO_SETUP", ["S1_EMA_PULLBACK_RECOVERY_ABSENT"])
    side = cast(Literal["LONG", "SHORT"], side)
    pivots = confirmed_pivots(candles, left=2, right=2)
    protective = [p for p in pivots if p.kind == ("LOW" if side == "LONG" else "HIGH")]
    diagnostics["structure"] = structure_label(pivots)
    sign = 1 if side == "LONG" else -1
    if len(protective) < 2 or sign * (protective[-1].price - protective[-2].price) <= 0:
        return result("NO_SETUP", ["LAG_CONFIRMED_PROTECTIVE_STRUCTURE_ABSENT"])
    atr, close, fast = four["atr14"], candles[-1].close, four["ema10"]
    lo, hi = min(fast, close) - 0.05 * atr, max(fast, close) + 0.05 * atr
    entry = hi if sign == 1 else lo
    costs = spec["strategy"]["costs_bps"]
    execution_buffer = entry * (costs["spread_round_trip"] + costs["slippage_each_side"]) / 10000
    pivot = protective[-1]
    stop = pivot.price - sign * (0.15 * atr + execution_buffer)
    if (
        stop <= 0
        or sign * (entry - stop) <= 0
        or (candles[-1].low <= stop if sign == 1 else candles[-1].high >= stop)
    ):
        return result("NO_SETUP", ["STRUCTURAL_INVALIDATION_ALREADY_CROSSED"])
    target_pivots = [
        p for p in pivots if p.kind == ("HIGH" if sign == 1 else "LOW") and sign * (p.price - entry) > 0
    ]
    targets = tuple(sorted({p.price for p in target_pivots}, reverse=sign == -1))
    if not targets:
        return result("NO_SETUP", ["NO_PREOBSERVABLE_FIXED_TARGET_ZONE"])
    max_price = max(entry, *targets)
    cost = (
        2 * max_price * (costs["fee_each_side"] + costs["slippage_each_side"]) / 10000
        + entry
        * (costs["spread_round_trip"] + costs["funding_and_carry_per_day"] * holding_hours / 24)
        / 10000
    )
    planned_r = (abs(targets[0] - entry) - cost) / (abs(entry - stop) + cost)
    diagnostics.update(
        {
            "planned_gross_r": abs(targets[0] - entry) / abs(entry - stop),
            "planned_after_cost_r": planned_r,
            "structural_pivot_index": pivot.pivot_index,
            "pivot_confirmation_index": pivot.confirmed_index,
            "structural_confirmation_available_ms": groups["4H"][pivot.confirmed_index].available_ms,
            "fixed_target_confirmation_ends": [groups["4H"][p.confirmed_index].end_ms for p in target_pivots],
        }
    )
    if planned_r < 2:
        return result("NO_SETUP", ["NEAREST_STRUCTURAL_TARGET_AFTER_COST_BELOW_2R"])
    hourly = groups["1H"]
    confirmed = False
    if hourly:
        confirmed = sign * (hourly[-1].candle.close - hourly[-2].candle.close) > 0
        diagnostics["optional_1H"] = "CONFIRMS_NO_URGENCY" if confirmed else "NOT_CONFIRMING_NO_URGENCY"
    opportunity = RCPlan(
        symbol=symbol,
        direction=side,
        regime=daily["regime"],
        setup_close_ms=trigger_ms,
        available_ms=max(b.available_ms for b in bars),
        structural_observed_ms=max(groups["4H"][p.confirmed_index].end_ms for p in [pivot, *target_pivots]),
        entry_region=(lo, hi),
        structural_invalidation=pivot.price,
        atr_buffer=0.15 * atr,
        execution_buffer=execution_buffer,
        target_zones=targets,
        planned_after_cost_r=planned_r,
        planned_cost_per_unit=cost,
        holding_hours=holding_hours,
        cost_assumption=cost_label,
        review_deadline_ms=trigger_ms + 24 * INTERVALS["1H"],
        expires_ms=trigger_ms + 24 * INTERVALS["1H"],
        account_status="UNKNOWN",
    )
    identity = fingerprint([product_id, STRATEGY_VERSION, symbol, trigger_ms, prefix_hash])
    return result(
        "ARMED" if confirmed else "WATCH",
        [
            "DAILY_4H_COMPLETED_TREND_ALIGNED",
            "S1_EMA_PULLBACK_RECOVERED",
            "LAG_CONFIRMED_PROTECTIVE_PIVOT",
            "FIXED_PREOBSERVABLE_TARGET_AFTER_COST_GEOMETRY",
            source_reason,
        ],
        opportunity=opportunity,
        episode_id=identity,
        eligible_planned_r=tuple(r for r in (2, 3, 4) if r <= planned_r),
    )
