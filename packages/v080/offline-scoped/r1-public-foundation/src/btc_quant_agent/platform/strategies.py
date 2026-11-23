"""S1 contract and inherited EMA pullback kernel; integrated production signals await LT-B."""

from __future__ import annotations

from types import MappingProxyType

from .config import PlatformConfig, StrategyConfig
from .core import MarketEvent, StrategyCandidate, StrategyDefinition
from .factors import FeaturePipeline
from .swing import require_active_strategy

REGISTRY = MappingProxyType({
    "trend_pullback": StrategyDefinition(
        "trend_pullback", "1.0.0", "EMA trend pullback; swing integration pending",
        ("EMA", "ADX"), "pullback recovers fast EMA in established slow trend",
        parameters=("fast", "slow"), status="CONTRACT_ACTIVE_LT_B_PENDING",
        limitations="No source qualification, positive trade, fill or economic claim in LT-A.",
    )
})


def register(definition: StrategyDefinition, evaluator=None) -> None:
    require_active_strategy(definition.id)
    raise ValueError("SWING_REGISTRY_FROZEN_NO_DYNAMIC_ACTIVATION")


def direction(pipeline: FeaturePipeline, event: MarketEvent, index: int,
              strategy: StrategyConfig) -> str | None:
    """Inherited S1 kernel only; not a public recommendation or trade compiler."""
    require_active_strategy(strategy.id)
    if (not event.candle.closed or event.candle.interval not in ("4H", "1D")
            or event.candle.available_at_ms is None
            or event.candle.available_at_ms > event.decision_ts
            or event.candle.close_time_ms >= event.decision_ts):
        return None
    df, symbol = pipeline.frames[event.spec.symbol], event.spec.symbol
    fast, slow = int(strategy.params.get("fast", 10)), int(strategy.params.get("slow", 30))
    if index < max(40, slow + 2):
        return None
    c, prior = float(df.close.iloc[index]), float(df.close.iloc[index - 1])
    ef = pipeline.result(symbol, "EMA", index, event.decision_ts, {"period": fast}).value
    es = pipeline.result(symbol, "EMA", index, event.decision_ts, {"period": slow}).value
    if ef is None or es is None:
        return None
    if ef > es and df.low.iloc[index] <= ef < c and c > prior:
        return "LONG"
    if ef < es and df.high.iloc[index] >= ef > c and c < prior:
        return "SHORT"
    return None


def evaluate(pipeline: FeaturePipeline, event: MarketEvent, index: int,
             strategy: StrategyConfig, config: PlatformConfig) -> StrategyCandidate | None:
    """Do not run the old quote/stop/target compiler on a relabeled long timeframe."""
    require_active_strategy(strategy.id)
    for selected in config.strategies:
        require_active_strategy(selected.id)
    # LT-B must join qualified 1D+4H inputs and preobservable structural zones first.
    return None
