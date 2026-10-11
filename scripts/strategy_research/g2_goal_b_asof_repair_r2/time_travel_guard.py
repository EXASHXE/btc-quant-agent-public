"""Time-travel mutation guard and leakage verification for Goal B R2.

Proves that any post-decision data mutation (bars, prices, funding rates)
leaves as-of-entry feature extractors 100% byte-for-byte unchanged.
"""

from __future__ import annotations

import copy
from typing import Any

import numpy as np

from .asof_features import (
    COL_CLOSE,
    COL_CLOSE_TIME,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    extract_pre_entry_atr_regime,
    extract_pre_entry_funding_state,
    extract_pre_entry_trend_aligned,
)


def mutate_future_1m_bars(
    bars_1m: np.ndarray,
    signal_decision_at_ms: int,
    multiplier: float = 10.0,
    noise: float = 1000.0,
) -> np.ndarray:
    """Mutate every 1m bar that closes after signal_decision_at_ms."""
    mutated = bars_1m.copy()
    mask = mutated[:, COL_CLOSE_TIME] > signal_decision_at_ms
    if np.any(mask):
        mutated[mask, COL_OPEN] = mutated[mask, COL_OPEN] * multiplier + noise
        mutated[mask, COL_HIGH] = mutated[mask, COL_HIGH] * multiplier + 2.0 * noise
        mutated[mask, COL_LOW] = np.maximum(1.0, mutated[mask, COL_LOW] * multiplier - noise)
        mutated[mask, COL_CLOSE] = mutated[mask, COL_CLOSE] * multiplier + noise
    return mutated


def mutate_future_hourly_bars(
    hourly_bars: np.ndarray,
    signal_decision_at_ms: int,
    multiplier: float = 10.0,
) -> np.ndarray:
    """Mutate every 1h bar that closes after signal_decision_at_ms."""
    mutated = hourly_bars.copy()
    mask = mutated[:, 5] > signal_decision_at_ms
    if np.any(mask):
        mutated[mask, 1:5] *= multiplier
    return mutated


def mutate_future_funding_settlements(
    settlements: list[dict[str, Any]],
    signal_decision_at_ms: int,
    extreme_rate: float = 0.50,
) -> list[dict[str, Any]]:
    """Mutate settlements or inject extreme settlements after signal_decision_at_ms."""
    mutated = [copy.deepcopy(s) for s in settlements]
    for s in mutated:
        if int(s["calc_time"]) >= signal_decision_at_ms:
            s["last_funding_rate"] = extreme_rate
    # Also inject a rogue future settlement
    mutated.append(
        {
            "calc_time": signal_decision_at_ms + 1000,
            "funding_interval_hours": 8,
            "last_funding_rate": -extreme_rate,
        }
    )
    return mutated


def verify_time_travel_invariance(
    bars_1m: np.ndarray,
    hourly_bars: np.ndarray,
    funding_settlements: list[dict[str, Any]],
    signal_decision_at_ms: int,
    side: int,
    entry_at_ms: int | None = None,
) -> dict[str, Any]:
    """Execute time-travel mutation and verify strict byte-level output invariance."""
    # 1. Baseline extraction
    trend_base = extract_pre_entry_trend_aligned(
        bars_1m, signal_decision_at_ms, side, entry_at_ms=entry_at_ms
    )
    atr_base = extract_pre_entry_atr_regime(
        hourly_bars, signal_decision_at_ms, entry_at_ms=entry_at_ms
    )
    fund_base = extract_pre_entry_funding_state(
        funding_settlements, signal_decision_at_ms, entry_at_ms=entry_at_ms
    )

    # 2. Mutate future
    bars_1m_mut = mutate_future_1m_bars(bars_1m, signal_decision_at_ms)
    hourly_mut = mutate_future_hourly_bars(hourly_bars, signal_decision_at_ms)
    fund_mut = mutate_future_funding_settlements(funding_settlements, signal_decision_at_ms)

    # 3. Post-mutation extraction
    trend_mut = extract_pre_entry_trend_aligned(
        bars_1m_mut, signal_decision_at_ms, side, entry_at_ms=entry_at_ms
    )
    atr_mut = extract_pre_entry_atr_regime(
        hourly_mut, signal_decision_at_ms, entry_at_ms=entry_at_ms
    )
    fund_mut_res = extract_pre_entry_funding_state(
        fund_mut, signal_decision_at_ms, entry_at_ms=entry_at_ms
    )

    # 4. Strict assertions
    assert trend_base["trend_regime"] == trend_mut["trend_regime"], (
        f"Trend regime mismatch: {trend_base['trend_regime']} != {trend_mut['trend_regime']}"
    )
    assert trend_base["alignment_val"] == trend_mut["alignment_val"], (
        f"Trend alignment value mismatch: {trend_base['alignment_val']} != {trend_mut['alignment_val']}"
    )

    assert atr_base["volatility_regime"] == atr_mut["volatility_regime"], (
        f"ATR regime mismatch: {atr_base['volatility_regime']} != {atr_mut['volatility_regime']}"
    )
    assert atr_base["current_norm_atr"] == atr_mut["current_norm_atr"], (
        f"Current norm ATR mismatch: {atr_base['current_norm_atr']} != {atr_mut['current_norm_atr']}"
    )
    assert atr_base["median_norm_atr"] == atr_mut["median_norm_atr"], (
        f"Median norm ATR mismatch: {atr_base['median_norm_atr']} != {atr_mut['median_norm_atr']}"
    )

    assert fund_base["funding_regime"] == fund_mut_res["funding_regime"], (
        f"Funding regime mismatch: {fund_base['funding_regime']} != {fund_mut_res['funding_regime']}"
    )
    assert fund_base["rate"] == fund_mut_res["rate"], (
        f"Funding rate mismatch: {fund_base['rate']} != {fund_mut_res['rate']}"
    )

    return {
        "status": "PASS_TIME_TRAVEL_INVARIANT",
        "signal_decision_at_ms": signal_decision_at_ms,
        "trend_regime": trend_base["trend_regime"],
        "volatility_regime": atr_base["volatility_regime"],
        "funding_regime": fund_base["funding_regime"],
    }
