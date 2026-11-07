"""Replaceable deterministic regime baseline; no fitted state model required."""

from .core import RegimeResult
from .factors import FeaturePipeline


def classify(pipeline: FeaturePipeline, symbol: str, index: int, decision_ts: int) -> RegimeResult:
    def value(id, params=None):
        return pipeline.result(symbol, id, index, decision_ts, params).value

    adx, trend, vol = value("ADX"), value("TREND_STRENGTH"), value("HIST_VOL")
    shocks = [
        pipeline.result(symbol, "LIQUIDATION_SHOCK", j, decision_ts).value
        for j in range(max(0, index - 8), index + 1)
    ]
    if any(v is not None and v > 0.002 for v in shocks):
        state = "DELEVERAGING_SHOCK"
    elif vol is not None and vol > 0.015:
        state = "HIGH_VOLATILITY"
    elif trend is None or adx is None:
        state = "UNKNOWN"
    elif adx > 22 and trend > 0.25:
        state = "TREND_UP"
    elif adx > 22 and trend < -0.25:
        state = "TREND_DOWN"
    else:
        state = "RANGE"
    return RegimeResult(
        state,
        tuple((k, v) for k, v in (("adx", adx), ("trend", trend), ("vol", vol)) if v is not None),
        decision_ts,
    )
