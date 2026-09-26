from __future__ import annotations

from ..domain import Regime
from .config import MarketWatchConfig
from .domain import (
    DerivativesMetrics,
    DerivativesRegime,
    GridDecision,
    GridPlan,
    TimeframeSnapshot,
)


def evaluate_grid_policy(
    *,
    symbol: str,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    prev_grid: GridPlan | None = None,
    config: MarketWatchConfig,
) -> GridPlan:
    """Evaluate grid recommendations independent of directional policy.

    Safety invariants:
    - Never lower a long-grid lower bound merely because price fell below it.
    - If price leaves grid and regime deteriorates, switch to PAUSE.
    - Expected grid profit per step must exceed estimated friction + safety margin.
    """
    gc = config.grid
    reasons: list[str] = []

    # Check 1: Strong trend or high volatility disables grid
    if tf_1h.regime in (Regime.TREND_UP, Regime.TREND_DOWN, Regime.HIGH_VOLATILITY) or tf_1h.adx >= gc.max_trend_adx:
        reasons.append("HIGH_ADX_OR_TREND_DOMINANT")
        reasons.append("GRID_UNSUITABLE_IN_TREND")
        return GridPlan(
            symbol=symbol,
            decision=GridDecision.PAUSE,
            lower_bound=None,
            upper_bound=None,
            grid_count=0,
            estimated_grid_pct=None,
            reason_codes=tuple(reasons),
        )

    # Check 2: Severe derivatives imbalance disables grid
    if derivatives.regime in (
        DerivativesRegime.DELEVERAGING,
        DerivativesRegime.LONG_LIQUIDATION,
        DerivativesRegime.LONG_CROWDING,
        DerivativesRegime.SHORT_CROWDING,
    ):
        reasons.append("DERIVATIVES_IMBALANCE_ACTIVE")
        reasons.append("GRID_PAUSED_FOR_SAFETY")
        return GridPlan(
            symbol=symbol,
            decision=GridDecision.PAUSE,
            lower_bound=None,
            upper_bound=None,
            grid_count=0,
            estimated_grid_pct=None,
            reason_codes=tuple(reasons),
        )

    # Check 3: Anti-falling-knife lower bound check from previous grid
    close = tf_15m.close
    if prev_grid is not None and prev_grid.lower_bound is not None and close < prev_grid.lower_bound:
        reasons.append("LOWER_BOUND_BREACHED")
        reasons.append("AVOID_BLIND_LOWERING_KNIFE_ACCUMULATION")
        reasons.append("GRID_TRANSITIONED_TO_PAUSE")
        return GridPlan(
            symbol=symbol,
            decision=GridDecision.PAUSE,
            lower_bound=prev_grid.lower_bound,
            upper_bound=prev_grid.upper_bound,
            grid_count=0,
            estimated_grid_pct=None,
            reason_codes=tuple(reasons),
        )

    # Range Grid Calculation
    atr = max(tf_1h.atr, 1e-6)
    buffer = gc.atr_buffer_mult * 0.5 * atr

    sup = tf_1h.supports[-1] if tf_1h.supports else (close - 2.5 * atr)
    res = tf_1h.resistances[-1] if tf_1h.resistances else (close + 2.5 * atr)

    lower_bound = round(max(1e-4, sup - buffer), 4)
    upper_bound = round(res + buffer, 4)

    if upper_bound <= lower_bound:
        upper_bound = round(lower_bound + 3.0 * atr, 4)

    grid_count = gc.default_grid_count
    total_range_pct = (upper_bound - lower_bound) / lower_bound
    step_pct = (total_range_pct / grid_count) * 100.0

    # Ensure step pct exceeds minimum grid profit floor
    if step_pct < gc.min_grid_profit_pct:
        # Increase step size by reducing grid count
        grid_count = max(3, int(total_range_pct * 100.0 / gc.min_grid_profit_pct))
        step_pct = (total_range_pct / grid_count) * 100.0

    # Determine Grid Bias
    if tf_1h.close > tf_1h.ema_mid and tf_1h.ema_mid_slope >= 0:
        decision = GridDecision.LONG_BIAS
        reasons.append("PRICE_ABOVE_MID_EMA_LONG_BIAS")
    elif tf_1h.close < tf_1h.ema_mid and tf_1h.ema_mid_slope <= 0:
        decision = GridDecision.SHORT_BIAS
        reasons.append("PRICE_BELOW_MID_EMA_SHORT_BIAS")
    else:
        decision = GridDecision.NEUTRAL
        reasons.append("RANGE_BALANCED_NEUTRAL_GRID")

    reasons.append(f"GRID_SPAN_{step_pct:.2f}%_PER_STEP")

    return GridPlan(
        symbol=symbol,
        decision=decision,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        grid_count=grid_count,
        estimated_grid_pct=round(step_pct, 3),
        stop_loss=round(lower_bound - atr, 4),
        take_profit=round(upper_bound + atr, 4),
        reason_codes=tuple(reasons),
    )


def should_alert_grid_change(current: GridPlan, previous: GridPlan | None, threshold_pct: float = 2.0) -> bool:
    """Alert only if grid state changes or bounds change >= configured threshold (default 2%)."""
    if previous is None:
        return current.decision != GridDecision.PAUSE

    if current.decision != previous.decision:
        return True

    if current.decision == GridDecision.PAUSE and previous.decision == GridDecision.PAUSE:
        return False

    if current.lower_bound is not None and previous.lower_bound is not None:
        lower_delta_pct = abs(current.lower_bound - previous.lower_bound) / previous.lower_bound * 100.0
        if lower_delta_pct >= threshold_pct:
            return True

    if current.upper_bound is not None and previous.upper_bound is not None:
        upper_delta_pct = abs(current.upper_bound - previous.upper_bound) / previous.upper_bound * 100.0
        if upper_delta_pct >= threshold_pct:
            return True

    return False
