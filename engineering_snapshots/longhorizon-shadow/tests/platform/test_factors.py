from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from btc_quant_agent.platform.core import Status
from btc_quant_agent.platform.data import frame, histories
from btc_quant_agent.platform.factors import FeaturePipeline, REGISTRY, normalize, validate_params


@pytest.mark.parametrize("id", list(REGISTRY))
def test_all_factors_are_prefix_invariant_and_nonfinite_safe(pipeline, id):
    prefix = FeaturePipeline(
        {s: df.iloc[:85].copy() for s, df in pipeline.frames.items()}, pipeline.benchmark
    )
    for symbol in pipeline.frames:
        full = pipeline.series(symbol, id)
        prior = prefix.series(symbol, id)
        np.testing.assert_allclose(full.iloc[:85], prior, equal_nan=True, rtol=1e-10, atol=1e-10)
        assert not np.isinf(full.to_numpy()).any()


def test_known_deterministic_formulas():
    c = np.arange(1, 41, dtype=float)
    df = pd.DataFrame(
        {
            "close": c,
            "high": c + 1,
            "low": c - 0.5,
            "volume": c * 2,
            "quote_volume": c * c * 2,
            "ts": np.arange(40) + 100,
            "available_ts": np.arange(40) + 101,
        }
    )
    p = FeaturePipeline({"X": df}, "X")
    assert p.series("X", "SMA", {"period": 3}).iloc[-1] == 39
    assert p.series("X", "WMA", {"period": 3}).iloc[-1] == pytest.approx((38 + 78 + 120) / 6)
    assert p.series("X", "RSI").iloc[-1] == 100
    assert p.series("X", "ROC", {"period": 3}).iloc[-1] == pytest.approx(40 / 37 - 1)
    assert p.series("X", "DONCHIAN_HIGH", {"period": 3}).iloc[-1] == 40
    assert p.series("X", "AROON_UP").iloc[-1] == 100
    assert p.series("X", "AROON_DOWN").iloc[-1] == 0
    assert p.series("X", "VWAP", {"period": 2}).iloc[-1] == pytest.approx((39 * 39 + 40 * 40) / (39 + 40))
    assert p.series("X", "RSRS").iloc[-1] == pytest.approx(1)
    assert p.series("X", "RSI").iloc[:14].isna().all()


def test_analytic_ramp_directional_volatility_volume_and_derivative_factors():
    n, p = 60, 14
    c = np.arange(1, n + 1, dtype=float)
    df = pd.DataFrame(
        {
            "close": c,
            "high": c + 1,
            "low": c - 0.5,
            "open": c - 0.2,
            "volume": np.full(n, 2.0),
            "quote_volume": 2 * c,
            "ts": np.arange(n) + 100,
            "available_ts": np.arange(n) + 101,
            "open_interest": 1000 + 10 * np.arange(n),
            "funding_rate": np.full(n, 0.0001),
            "basis": np.full(n, 0.002),
            "premium": np.full(n, 0.001),
            "spot_close": 2 * c,
            "taker_buy": np.full(n, 3.0),
            "taker_sell": np.full(n, 1.0),
            "aggressive_delta": np.full(n, 2.0),
            "bid": c - 0.01,
            "ask": c + 0.01,
            "bid_depth": np.full(n, 3.0),
            "ask_depth": np.full(n, 1.0),
        }
    )
    pipeline = FeaturePipeline({"X": df}, "X")
    atr = 2 - 0.5 * (1 - 1 / p) ** (n - 1)
    expected = {
        "SMA": n - (p - 1) / 2,
        "WMA": n - (p - 1) / 3,
        "EMA": n - (p - 1) / 2 * (1 - (1 - 2 / (p + 1)) ** (n - 1)),
        "RSI": 100,
        "ADX": 100,
        "ATR": atr,
        "DI_PLUS": 100 * (1 - (1 - 1 / p) ** (n - 1)) / atr,
        "DI_MINUS": 0,
        "BB_MID": n - (p - 1) / 2,
        "BB_UPPER": n - (p - 1) / 2 + 2 * np.sqrt((p * p - 1) / 12),
        "BB_LOWER": n - (p - 1) / 2 - 2 * np.sqrt((p * p - 1) / 12),
        "BB_WIDTH": 4 * np.sqrt((p * p - 1) / 12) / (n - (p - 1) / 2),
        "STOCHASTIC": 100 * (p - 0.5) / (p + 0.5),
        "KDJ_K": 100 * (p - 0.5) / (p + 0.5),
        "KDJ_D": 100 * (p - 0.5) / (p + 0.5),
        "KDJ_J": 100 * (p - 0.5) / (p + 0.5),
        "CCI": 6.5 / (0.015 * 3.5),
        "AROON_UP": 100,
        "AROON_DOWN": 0,
        "ROC": n / (n - p) - 1,
        "MOMENTUM": p,
        "DONCHIAN_HIGH": n,
        "DONCHIAN_LOW": n - p - 0.5,
        "BREAKOUT_HIGH": n,
        "BREAKOUT_LOW": n - p - 0.5,
        "DRAWDOWN": 0,
        "RSRS": 1,
        "VOLUME_SMA": 2,
        "OBV": 2 * (n - 1),
        "VWAP": n - (p - 1) / 2,
        "RELATIVE_VOLUME": 1,
        "RELATIVE_STRENGTH": 0,
        "TREND_PERSISTENCE": 1,
        "BREAKOUT_DISTANCE": 0,
        "BETA": 1,
        "CORRELATION": 1,
        "MOMENTUM_RANK": 1,
        "MARKET_RISK": 1,
        "OI_LEVEL": 1590,
        "OI_CHANGE": 1590 / 1450 - 1,
        "FUNDING": 0.0001,
        "FUNDING_MEAN": 0.0001,
        "BASIS": 0.002,
        "PREMIUM": 0.001,
        "SPOT_PERP_RETURN": 0,
        "TAKER_IMBALANCE": 0.5,
        "CVD": 120,
        "LIQUIDATION_SHOCK": 0,
        "QUOTE_SPREAD": 10000 * 0.02 / 60,
        "ORDERBOOK_IMBALANCE": 0.5,
        "DEPTH_CHANGE": 0,
        "REVERSAL_SEVERITY": 0,
    }
    for id, want in expected.items():
        assert pipeline.series("X", id).iloc[-1] == pytest.approx(want, rel=1e-8, abs=1e-8), id
    last_returns = np.diff(c[-p - 1 :]) / c[-p - 1 : -1]
    ema14 = n - (p - 1) / 2 * (1 - (1 - 2 / (p + 1)) ** (n - 1))
    ema28 = n - (2 * p - 1) / 2 * (1 - (1 - 2 / (2 * p + 1)) ** (n - 1))
    extra = {
        "HIST_VOL": np.std(np.diff(np.log(c[-p - 1 :])), ddof=1),
        "REALIZED_RANGE": np.sqrt(np.mean(np.log((c[-p:] + 1) / (c[-p:] - 0.5)) ** 2) / (4 * np.log(2))),
        "MA_DISTANCE": n / ema14 - 1,
        "TREND_STRENGTH": (ema14 - ema28) / atr,
        "VOL_ADJUSTED_RETURN": (n / (n - p) - 1) / (np.std(last_returns, ddof=1) * np.sqrt(p)),
        "RANGE_COMPRESSION": (1 / (n - 6.5)) / np.mean(1 / (c[-p:] - 6.5)),
        "LIQUIDITY_SCORE": (n / (n - p) - 1) * np.log1p(2 * (n - 6.5)) / (1 + 10000 * 0.02 / n),
        "POSITIONING_EXTREME": (p - 1) / 2 / np.std(np.arange(p), ddof=1),
    }
    for id, want in extra.items():
        assert pipeline.series("X", id).iloc[-1] == pytest.approx(want, rel=1e-8, abs=1e-8), id
    fast = n - 5.5 * (1 - (1 - 2 / 13) ** (n - 1))
    slow = n - 12.5 * (1 - (1 - 2 / 27) ** (n - 1))
    assert pipeline.series("X", "MACD").iloc[-1] == pytest.approx(fast - slow)
    assert pipeline.series("X", "MACD_HIST").iloc[-1] == pytest.approx(
        pipeline.series("X", "MACD").iloc[-1] - pipeline.series("X", "MACD_SIGNAL").iloc[-1]
    )
    assert pipeline.series("X", "STOCHRSI").isna().all()
    assert pipeline.series("X", "VOLUME_ANOMALY").isna().all()
    assert pipeline.series("X", "PIVOT_LOW").isna().all()
    assert pipeline.series("X", "PIVOT_HIGH").isna().all()


def test_unavailable_depth_and_derivatives_are_missing_not_zero(events, config):
    group = histories(events)[config.universe[0]]
    stripped = [replace(e, derivatives=None, trades=()) for e in group]
    df = frame(stripped, stripped[-1].decision_ts)
    p = FeaturePipeline({config.universe[0]: df}, config.universe[0])
    for id in ("OI_LEVEL", "FUNDING", "CVD", "ORDERBOOK_IMBALANCE", "DEPTH_CHANGE"):
        result = p.result(config.universe[0], id, len(df) - 1, stripped[-1].decision_ts)
        assert result.status == Status.MISSING and result.value is None


def test_derivatives_available_after_decision_are_not_smuggled(events, config):
    e = events[210]
    late = replace(
        e.derivatives, provenance=replace(e.derivatives.provenance, available_ts=e.decision_ts + 100000)
    )
    df = frame([replace(e, derivatives=late)], e.decision_ts + 200000)
    assert "open_interest" not in df


def test_late_cross_symbol_input_blocks_result(pipeline):
    frames = {s: df.copy() for s, df in pipeline.frames.items()}
    symbol = list(frames)[1]
    now = int(frames[symbol].available_ts.iloc[80])
    frames[pipeline.benchmark].loc[80, "available_ts"] = now + 1
    p = FeaturePipeline(frames, pipeline.benchmark)
    assert p.result(symbol, "RELATIVE_STRENGTH", 80, now).status == Status.INADMISSIBLE
    assert p.result(symbol, "MOMENTUM_RANK", 80, now).status == Status.INADMISSIBLE
    frames[pipeline.benchmark].loc[80, "available_ts"] = now
    frames[pipeline.benchmark].loc[70, "available_ts"] = now + 1
    assert (
        FeaturePipeline(frames, pipeline.benchmark).result(symbol, "BETA", 80, now).status
        == Status.INADMISSIBLE
    )


def test_cache_and_normalization(pipeline):
    before = pipeline.computations
    a = pipeline.series(pipeline.benchmark, "EMA", {"period": 19})
    b = pipeline.series(pipeline.benchmark, "EMA", {"period": 19})
    assert a is b and pipeline.computations == before + 1
    ranks = normalize(pd.Series([3, 1, np.nan, 2]), "rank")
    assert ranks.iloc[0] == 1 and ranks.iloc[1] == pytest.approx(1 / 3) and pd.isna(ranks.iloc[2])
    with pytest.raises(ValueError):
        validate_params("RSI", {"period": 0})
    with pytest.raises(ValueError):
        validate_params("RSI", {"typo": 2})
