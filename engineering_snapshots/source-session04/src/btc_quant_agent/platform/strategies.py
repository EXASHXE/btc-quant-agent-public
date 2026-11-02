"""Independent registered mechanisms using the same typed candidate compiler."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np

from .config import PlatformConfig, StrategyConfig
from .core import EvidenceTier
from .core import Lifecycle, MarketEvent, StrategyCandidate, StrategyDefinition, dec, fingerprint, quantize
from .factors import FeaturePipeline
from .regime import classify

REGISTRY: dict[str, StrategyDefinition] = {}
EVALUATORS: dict = {}


def register(definition: StrategyDefinition, evaluator=None) -> None:
    if definition.id in REGISTRY:
        raise ValueError("DUPLICATE_STRATEGY")
    REGISTRY[definition.id] = definition
    if evaluator is not None:
        EVALUATORS[definition.id] = evaluator


for id, description, features, mechanism in [
    ("single_ma", "Price versus single EMA", ("EMA",), "price follows its smoothed trend"),
    ("double_ma", "Fast and slow moving-average trend", ("EMA",), "fast EMA above/below slow EMA"),
    ("multi_ma", "Three EMA trend alignment", ("EMA",), "fast, middle and slow EMA ordered"),
    (
        "macd_adx",
        "MACD histogram and ADX confirmation",
        ("MACD_HIST", "ADX"),
        "directional impulse with trend strength",
    ),
    ("aroon", "Aroon trend continuation", ("AROON_UP", "AROON_DOWN"), "recent extremes establish direction"),
    (
        "trend_breakout",
        "Donchian/Turtle channel breakout",
        ("DONCHIAN_HIGH", "DONCHIAN_LOW"),
        "close exceeds prior channel",
    ),
    (
        "spot_led_breakout",
        "Observed spot leads perpetual breakout",
        ("DONCHIAN_HIGH", "SPOT_PERP_RETURN"),
        "spot relative strength confirms breakout",
    ),
    (
        "breakout_retest",
        "Prior breakout followed by level retest",
        ("DONCHIAN_HIGH",),
        "observed prior resistance becomes retest reference",
    ),
    (
        "trend_pullback",
        "EMA trend pullback",
        ("EMA", "ADX"),
        "pullback recovers fast EMA in established slow trend",
    ),
    (
        "compression_breakout",
        "Volatility compression to expansion",
        ("RANGE_COMPRESSION", "BB_WIDTH", "DONCHIAN_HIGH"),
        "compressed range expands beyond channel",
    ),
    (
        "bollinger_reversion",
        "Bollinger band mean reversion",
        ("BB_LOWER", "BB_UPPER", "BB_MID"),
        "extreme deviation returns toward observed mean",
    ),
    ("rsi_reversion", "RSI oversold/overbought reversion", ("RSI",), "directional exhaustion"),
    (
        "rsi_divergence",
        "Confirmed swing/RSI divergence",
        ("RSI", "PIVOT_LOW", "PIVOT_HIGH"),
        "compare oscillator at two causally confirmed swings",
    ),
    ("stochrsi_reversal", "StochRSI extreme reversal", ("STOCHRSI",), "oscillator leaves extreme band"),
    ("cci_reversal", "CCI extreme crossing", ("CCI",), "cross back inside plus/minus 100"),
    (
        "rsrs_timing",
        "RSRS slope versus own trailing distribution",
        ("RSRS",),
        "positive standardized rolling high/low slope",
    ),
    (
        "sweep_reclaim",
        "Prior range sweep and close reclaim",
        ("DONCHIAN_LOW", "DONCHIAN_HIGH"),
        "failed break of observed channel",
    ),
    (
        "turning_point",
        "Causally confirmed local turning point",
        ("PIVOT_LOW", "PIVOT_HIGH"),
        "new pivot confirmation with price moving away",
    ),
    (
        "shock_reversal",
        "Price shock and OI contraction recovery",
        ("LIQUIDATION_SHOCK", "QUOTE_SPREAD"),
        "deleveraging proxy followed by price and liquidity recovery",
    ),
    (
        "liquidation_reversion",
        "Deleveraging reversion proxy",
        ("LIQUIDATION_SHOCK", "RELATIVE_VOLUME"),
        "shock plus volume anomaly followed by recovery; no measured liquidations",
    ),
    (
        "multi_factor_momentum",
        "Configured factor ensemble on an EMA trend",
        ("EMA", "ADX", "RELATIVE_STRENGTH", "RELATIVE_VOLUME"),
        "trend candidates ranked by explicit factor weights",
    ),
]:
    register(
        StrategyDefinition(
            id,
            "1.0.0",
            description,
            features,
            mechanism,
            supported_markets=("PERPETUAL",)
            if id in ("shock_reversal", "liquidation_reversion", "spot_led_breakout")
            else ("SPOT", "PERPETUAL", "EQUITY", "ETF"),
        )
    )

for id, text in [
    ("pair_trading", "rolling hedge ratio and spread z-score"),
    ("cointegration_spread", "training-only cointegration test and frozen hedge ratio"),
    ("funding_carry", "separate spot long and perpetual short, funding settlement and leg costs"),
    ("grid", "range-only inventory-aware grid with quote crossing fills"),
    ("volatility_target", "inverse realized-volatility allocation with gross cap"),
    ("rebalance", "periodic target-weight rebalance and turnover accounting"),
    ("relative_strength_rotation", "cross-sectional momentum selection and target weights"),
]:
    register(
        StrategyDefinition(
            id,
            "0.1.0",
            text,
            (),
            text,
            status="RESEARCH_ONLY",
            supported_markets=("PERPETUAL",)
            if id == "funding_carry"
            else ("SPOT", "PERPETUAL", "EQUITY", "ETF"),
            limitations="Research-only portfolio simulator; excluded from single-leg advisory/backtest engine.",
        )
    )


PARAMETERS = {
    "single_ma": ("fast",),
    "double_ma": ("fast", "slow"),
    "multi_ma": ("fast", "slow"),
    "macd_adx": ("threshold",),
    "aroon": (),
    "trend_breakout": ("period",),
    "spot_led_breakout": ("period",),
    "breakout_retest": ("period",),
    "trend_pullback": ("fast", "slow"),
    "compression_breakout": ("period",),
    "bollinger_reversion": ("period",),
    "rsi_reversion": ("threshold",),
    "rsi_divergence": (),
    "stochrsi_reversal": ("threshold",),
    "cci_reversal": ("threshold",),
    "rsrs_timing": ("threshold",),
    "sweep_reclaim": ("period",),
    "turning_point": (),
    "shock_reversal": ("threshold", "lookback"),
    "liquidation_reversion": ("threshold", "lookback"),
    "multi_factor_momentum": ("fast", "slow", "threshold"),
}
for id, definition in list(REGISTRY.items()):
    REGISTRY[id] = replace(definition, parameters=PARAMETERS.get(id, ()))
for id in ("trend_breakout", "bollinger_reversion", "shock_reversal"):
    REGISTRY[id] = replace(REGISTRY[id], evidence_tier=EvidenceTier.SYNTHETIC_VALIDATED)


def direction(
    pipeline: FeaturePipeline, event: MarketEvent, index: int, strategy: StrategyConfig
) -> str | None:
    if strategy.id in EVALUATORS:
        return EVALUATORS[strategy.id](pipeline, event, index, strategy)
    df, symbol = pipeline.frames[event.spec.symbol], event.spec.symbol
    p = strategy.params
    period, fast, slow = int(p.get("period", 20)), int(p.get("fast", 10)), int(p.get("slow", 30))
    if index < max(40, slow + 2):
        return None
    c, prior = float(df.close.iloc[index]), float(df.close.iloc[index - 1])

    def f(id, offset=0, params=None):
        return pipeline.result(symbol, id, index - offset, event.decision_ts, params).value

    ef, es = f("EMA", params={"period": fast}), f("EMA", params={"period": slow})
    high, low = f("DONCHIAN_HIGH", params={"period": period}), f("DONCHIAN_LOW", params={"period": period})
    id = strategy.id
    if id == "single_ma":
        return "LONG" if ef is not None and c > ef else "SHORT" if ef is not None and c < ef else None
    if id in ("double_ma", "multi_ma", "multi_factor_momentum"):
        middle = f("EMA", params={"period": (fast + slow) // 2})
        if ef is None or es is None or middle is None:
            return None
        if id == "multi_ma":
            return "LONG" if ef > middle > es else "SHORT" if ef < middle < es else None
        if id == "multi_factor_momentum" and (f("ADX") is None or f("ADX") < p.get("threshold", 20)):
            return None
        return "LONG" if ef > es else "SHORT" if ef < es else None
    if id == "macd_adx":
        hist, adx = f("MACD_HIST"), f("ADX")
        if hist is None or adx is None or adx < p.get("threshold", 22):
            return None
        return "LONG" if hist > 0 else "SHORT" if hist < 0 else None
    if id == "aroon":
        up, down = f("AROON_UP"), f("AROON_DOWN")
        if up is None or down is None:
            return None
        return "LONG" if up > 80 and down < 40 else "SHORT" if down > 80 and up < 40 else None
    if id in ("trend_breakout", "spot_led_breakout", "compression_breakout"):
        if high is None or low is None:
            return None
        if id == "spot_led_breakout":
            relative = f("SPOT_PERP_RETURN")
            if relative is None:
                return None
            return (
                "LONG"
                if c > high and relative < -0.0005
                else "SHORT"
                if c < low and relative > 0.0005
                else None
            )
        if id == "compression_breakout":
            compression = f("RANGE_COMPRESSION", 1)
            if compression is None or compression >= 1:
                return None
        return "LONG" if c > high else "SHORT" if c < low else None
    if id == "breakout_retest":
        old_high, old_low = (
            f("DONCHIAN_HIGH", 1, {"period": period}),
            f("DONCHIAN_LOW", 1, {"period": period}),
        )
        if old_high and prior > old_high and df.low.iloc[index] <= old_high < c:
            return "LONG"
        if old_low and prior < old_low and df.high.iloc[index] >= old_low > c:
            return "SHORT"
        return None
    if id == "trend_pullback":
        if ef is None or es is None:
            return None
        if ef > es and df.low.iloc[index] <= ef < c and c > prior:
            return "LONG"
        if ef < es and df.high.iloc[index] >= ef > c and c < prior:
            return "SHORT"
        return None
    if id == "bollinger_reversion":
        lower, upper = f("BB_LOWER", params={"period": period}), f("BB_UPPER", params={"period": period})
        if lower is None or upper is None:
            return None
        return "LONG" if c < lower else "SHORT" if c > upper else None
    if id == "rsi_reversion":
        rsi = f("RSI")
        threshold = p.get("threshold", 30)
        return (
            "LONG"
            if rsi is not None and rsi < threshold
            else "SHORT"
            if rsi is not None and rsi > 100 - threshold
            else None
        )
    if id in ("stochrsi_reversal", "cci_reversal"):
        name, lower, upper = ("STOCHRSI", 20, 80) if id == "stochrsi_reversal" else ("CCI", -100, 100)
        threshold = p.get("threshold", 20 if id == "stochrsi_reversal" else 100)
        lower, upper = (threshold, 100 - threshold) if id == "stochrsi_reversal" else (-threshold, threshold)
        now, before = f(name), f(name, 1)
        if now is None or before is None:
            return None
        return "LONG" if before < lower <= now else "SHORT" if before > upper >= now else None
    if id == "rsi_divergence":
        # Pivot at j is confirmed at j+2. Oscillator is sampled at that actual pivot, not at confirmation.
        for name, sign in (("PIVOT_LOW", "LONG"), ("PIVOT_HIGH", "SHORT")):
            seq = pipeline.series(symbol, name).iloc[: index + 1]
            changed = seq.notna() & seq.ne(seq.shift())
            points = list(np.flatnonzero(changed.to_numpy()))
            if len(points) < 2 or points[-1] != index:
                continue
            a, b = points[-2], points[-1]
            ra = pipeline.result(symbol, "RSI", a - 2, event.decision_ts).value
            rb = pipeline.result(symbol, "RSI", b - 2, event.decision_ts).value
            if ra is None or rb is None:
                continue
            if sign == "LONG" and seq.iloc[b] < seq.iloc[a] and rb > ra:
                return sign
            if sign == "SHORT" and seq.iloc[b] > seq.iloc[a] and rb < ra:
                return sign
        return None
    if id == "rsrs_timing":
        seq = pipeline.series(symbol, "RSRS").iloc[max(0, index - 60) : index + 1].dropna()
        if len(seq) < 30 or seq.std() == 0:
            return None
        z = (seq.iloc[-1] - seq.iloc[:-1].mean()) / seq.iloc[:-1].std()
        threshold = p.get("threshold", 1)
        return "LONG" if z > threshold else "SHORT" if z < -threshold else None
    if id == "sweep_reclaim":
        if low and df.low.iloc[index] < low < c:
            return "LONG"
        if high and df.high.iloc[index] > high > c:
            return "SHORT"
        return None
    if id == "turning_point":
        for name, sign in (("PIVOT_LOW", "LONG"), ("PIVOT_HIGH", "SHORT")):
            now, before = f(name), f(name, 1)
            if now is not None and now != before and ((c > prior) if sign == "LONG" else (c < prior)):
                return sign
        return None
    if id in ("shock_reversal", "liquidation_reversion"):
        shocks = [f("LIQUIDATION_SHOCK", j) for j in range(1, int(p.get("lookback", 6)) + 1)]
        spread = f("QUOTE_SPREAD")
        if (
            any(x is not None and x > p.get("threshold", 0.002) for x in shocks)
            and c > prior
            and spread is not None
            and spread < 10
        ):
            return "LONG"
        return None
    if REGISTRY[id].status == "RESEARCH_ONLY":
        return None
    raise ValueError(f"strategy has no evaluator: {id}")


def evaluate(
    pipeline: FeaturePipeline,
    event: MarketEvent,
    index: int,
    strategy: StrategyConfig,
    config: PlatformConfig,
) -> StrategyCandidate | None:
    definition = REGISTRY[strategy.id]
    if definition.status == "RESEARCH_ONLY":
        return None
    regime = classify(pipeline, event.spec.symbol, index, event.decision_ts)
    if strategy.regimes and regime.state not in strategy.regimes:
        return None
    side = direction(pipeline, event, index, strategy)
    if side is None or (side == "SHORT" and event.spec.market != "PERPETUAL"):
        return None
    df = pipeline.frames[event.spec.symbol]
    sample = df.iloc[max(0, index - config.exits.stop_lookback + 1) : index + 1]
    price = dec(event.candle.close)
    tick = event.spec.tick_size
    observed = dec(sample.low.min()) if side == "LONG" else dec(sample.high.max())
    stop = quantize(
        observed - tick * config.exits.stop_buffer_ticks
        if side == "LONG"
        else observed + tick * config.exits.stop_buffer_ticks,
        tick,
        up=side == "SHORT",
    )
    width = dec(config.entry.region_bps / 10000)
    entry_low = quantize(price * (1 - width), tick)
    entry_high = quantize(price * (1 + width), tick, up=True)
    target = None
    mean_policy = strategy.id in ("bollinger_reversion", "rsi_reversion", "stochrsi_reversal", "cci_reversal")
    if config.exits.policy == "mean" or (mean_policy and config.exits.policy == "strategy"):
        mean = pipeline.result(
            event.spec.symbol,
            "BB_MID",
            index,
            event.decision_ts,
            {"period": int(strategy.params.get("period", 20))},
        ).value
        if mean is None:
            return None
        target = quantize(mean, tick, up=side == "SHORT")
        if (side == "LONG" and target <= entry_high) or (side == "SHORT" and target >= entry_low):
            return None
    features = {}
    for id in definition.required_features:
        params = (
            {"period": int(strategy.params.get("period", 20))}
            if id.startswith(("BB_", "DONCHIAN_"))
            else None
        )
        if id == "EMA":
            for label, period in (
                ("fast", strategy.params.get("fast", 10)),
                ("slow", strategy.params.get("slow", 30)),
            ):
                features[f"EMA_{label}_{period}"] = pipeline.result(
                    event.spec.symbol, id, index, event.decision_ts, {"period": int(period)}
                ).value
        else:
            features[id] = pipeline.result(event.spec.symbol, id, index, event.decision_ts, params).value
    if any(v is None for v in features.values()):
        return None
    evidence = {
        "features": features,
        "strategy_parameters": strategy.params,
        "close": event.candle.close,
        "source": event.provenance.source_id,
        "stop_reference": "observed trailing low" if side == "LONG" else "observed trailing high",
        "stop_window_start": int(sample.ts.iloc[0]),
        "regime": regime.state,
        "score_semantics": "opportunity rank, not calibrated probability",
    }
    identity = fingerprint([config.hash, event.spec.symbol, strategy.id, event.decision_ts, evidence])
    return StrategyCandidate(
        identity,
        event.spec.symbol,
        side,
        strategy.id,
        definition.version,
        event.decision_ts,
        Lifecycle.DISCOVERED,
        0,
        json.dumps(evidence, sort_keys=True),
        (
            f"{config.entry.confirmation_bars} subsequent completed bars move in setup direction",
            "fresh executable quote within entry region and expiry; all hard risk gates pass",
        ),
        entry_low,
        entry_high,
        entry_high if side == "LONG" else entry_low,
        event.decision_ts + config.entry.expiry_minutes * 60000,
        stop,
        stop,
        target,
        "OBSERVED_MEAN" if target else "OPEN_ENDED_TRAIL",
        regime.state,
        event.provenance,
        evidence_tier=definition.evidence_tier,
    )


def resolve(candidates: list[StrategyCandidate], config: PlatformConfig) -> list[StrategyCandidate]:
    priorities = {s.id: s.priority for s in config.strategies}
    groups = {s.id: s.group for s in config.strategies}
    by_symbol = {}
    for c in candidates:
        by_symbol.setdefault(c.symbol, []).append(c)
    selected = []
    for symbol, items in sorted(by_symbol.items()):
        items = list({c.id: c for c in items}.values())
        if config.entry.aggregation == "vote":
            votes = sum(1 if c.direction == "LONG" else -1 for c in items)
            if votes == 0:
                continue
            direction = "LONG" if votes > 0 else "SHORT"
            items = [c for c in items if c.direction == direction]
        chosen = sorted(
            items, key=lambda c: (-priorities[c.strategy_id], -c.opportunity_score, c.strategy_id, c.id)
        )[0]
        compatible = [
            c
            for c in items
            if c.direction == chosen.direction and groups[c.strategy_id] != groups[chosen.strategy_id]
        ]
        if compatible:
            evidence = json.loads(chosen.evidence_json)
            evidence["compatible_strategy_groups"] = [
                {"group": groups[c.strategy_id], "strategy": c.strategy_id, "candidate_id": c.id}
                for c in sorted(compatible, key=lambda x: x.strategy_id)
            ]
            chosen = replace(chosen, evidence_json=json.dumps(evidence, sort_keys=True))
        selected.append(replace(chosen, state=Lifecycle.WATCH))
    return selected
