"""Causal batch factors, shared feature cache, explicit coverage and missingness."""

from __future__ import annotations

import numpy as np
import pandas as pd

from btc_quant_agent import indicators
from btc_quant_agent.structure import confirmed_pivots

from .core import Candle, FactorDefinition, FactorResult, Status, fingerprint

REGISTRY: dict[str, FactorDefinition] = {}
COMPUTATIONS: dict = {}


def register(
    id: str,
    formula: str,
    fields: str = "close",
    params: tuple[str, ...] = ("period",),
    *,
    derivative: bool = False,
    status: str = "WORKING_BASELINE",
    compute=None,
) -> None:
    if id in REGISTRY:
        raise ValueError(f"duplicate factor {id}")
    immediate = {
        "OI_LEVEL",
        "FUNDING",
        "BASIS",
        "PREMIUM",
        "TAKER_IMBALANCE",
        "QUOTE_SPREAD",
        "ORDERBOOK_IMBALANCE",
        "CVD",
        "OBV",
    }
    fixed_structure = {"PIVOT_LOW", "PIVOT_HIGH", "SUPPORT_DISTANCE", "RESISTANCE_DISTANCE"}
    if id in immediate | fixed_structure | {"LIQUIDATION_SHOCK"}:
        params = ()
    warmup = (
        "one observation; cumulative factors require an unbroken admitted prefix"
        if id in immediate
        else "five bars for first possible 2-left/2-right pivot; remains MISSING until a strict pivot exists"
        if id in fixed_structure
        else "two observations"
        if id == "LIQUIDATION_SHOCK"
        else "slow observations"
        if id == "MACD"
        else "slow + signal - 1 observations"
        if id in ("MACD_SIGNAL", "MACD_HIST")
        else "2 * period + 1 observations"
        if id == "ADX"
        else "2 * period observations"
        if id in ("STOCHRSI", "TREND_STRENGTH")
        else "2 * period - 1 observations"
        if id == "RANGE_COMPRESSION"
        else "period + 1 observations"
        if id
        in (
            "RSI",
            "ROC",
            "MOMENTUM",
            "DONCHIAN_HIGH",
            "DONCHIAN_LOW",
            "BREAKOUT_HIGH",
            "BREAKOUT_LOW",
            "HIST_VOL",
            "RELATIVE_VOLUME",
            "VOLUME_ANOMALY",
            "RELATIVE_STRENGTH",
            "VOL_ADJUSTED_RETURN",
            "TREND_PERSISTENCE",
            "BREAKOUT_DISTANCE",
            "LIQUIDITY_SCORE",
            "BETA",
            "CORRELATION",
            "MOMENTUM_RANK",
            "MARKET_RISK",
            "REVERSAL_SEVERITY",
            "OI_CHANGE",
            "SPOT_PERP_RETURN",
            "DEPTH_CHANGE",
            "DI_PLUS",
            "DI_MINUS",
        )
        else "period observations; zero denominator remains undefined"
    )
    defaults = tuple((name, {"fast": 12, "slow": 26, "signal": 9}.get(name, 14)) for name in params)
    REGISTRY[id] = FactorDefinition(
        id,
        "1.0.0",
        formula,
        tuple(fields.split()),
        params,
        parameter_defaults=defaults,
        supported_markets=("PERPETUAL",) if derivative else ("SPOT", "PERPETUAL", "EQUITY", "ETF"),
        implementation_status=status,
        warmup_rule=warmup,
    )
    if compute is not None:
        COMPUTATIONS[id] = compute


for id, formula, fields in [
    ("SMA", "mean(close, period)", "close"),
    ("EMA", "recursive EMA alpha=2/(period+1), first-observation seed; masked warmup", "close"),
    ("WMA", "linear weights 1..period, normalized", "close"),
    ("RSI", "100-100/(1+Wilder(gain)/Wilder(loss)); flat=50", "close"),
    ("STOCHRSI", "100*(RSI-min(RSI))/(max(RSI)-min(RSI)); flat undefined", "close"),
    ("ADX", "Wilder(100*abs(DI+-DI-)/(DI++DI-)); first-value Wilder seed", "high low close"),
    ("DI_PLUS", "100*Wilder(positive directional movement)/ATR", "high low close"),
    ("DI_MINUS", "100*Wilder(negative directional movement)/ATR", "high low close"),
    ("ATR", "Wilder(max(high-low,abs(high-prev_close),abs(low-prev_close)))", "high low close"),
    ("BB_MID", "SMA(close, period)", "close"),
    ("BB_UPPER", "SMA+2*population_std(close, period)", "close"),
    ("BB_LOWER", "SMA-2*population_std(close, period)", "close"),
    ("BB_WIDTH", "(upper-lower)/mid", "close"),
    ("STOCHASTIC", "100*(close-rolling_low)/(rolling_high-rolling_low)", "high low close"),
    ("KDJ_K", "recursive K=(2/3)*prior_K+(1/3)*RSV; first RSV seed", "high low close"),
    ("KDJ_D", "recursive D=(2/3)*prior_D+(1/3)*K; first K seed", "high low close"),
    ("KDJ_J", "3*K-2*D", "high low close"),
    ("CCI", "(typical_price-mean)/(0.015*mean_absolute_deviation)", "high low close"),
    ("AROON_UP", "100*index_of_latest_max(high)/(period-1)", "high"),
    ("AROON_DOWN", "100*index_of_latest_min(low)/(period-1)", "low"),
    ("ROC", "close/close.shift(period)-1", "close"),
    ("MOMENTUM", "close-close.shift(period)", "close"),
    ("DONCHIAN_HIGH", "max(high.shift(1), period); current bar excluded", "high"),
    ("DONCHIAN_LOW", "min(low.shift(1), period); current bar excluded", "low"),
    ("BREAKOUT_HIGH", "max(high.shift(1), period)", "high"),
    ("BREAKOUT_LOW", "min(low.shift(1), period)", "low"),
    ("HIST_VOL", "sample std(log returns); per-bar units, no assumed annualization", "close"),
    ("REALIZED_RANGE", "sqrt(mean(log(high/low)^2)/(4*log(2)))", "high low"),
    ("DRAWDOWN", "close/rolling_max(close)-1", "close"),
    ("MA_DISTANCE", "close/EMA(close, period)-1", "close"),
    ("PIVOT_LOW", "most recent strict pivot low, visible only after 2 right bars", "high low close"),
    ("PIVOT_HIGH", "most recent strict pivot high, visible only after 2 right bars", "high low close"),
    ("SUPPORT_DISTANCE", "close/confirmed_pivot_low-1; absent structure is missing", "high low close"),
    ("RESISTANCE_DISTANCE", "confirmed_pivot_high/close-1", "high low close"),
    ("RSRS", "rolling OLS slope of high on low; undefined on zero low variance", "high low"),
    ("VOLUME_SMA", "mean(base volume, period)", "volume"),
    ("OBV", "cumulative sign(close.diff)*base volume", "close volume"),
    (
        "VWAP",
        "rolling sum(actual quote_volume)/sum(base volume); rolling, not session VWAP",
        "quote_volume volume",
    ),
    ("RELATIVE_VOLUME", "volume/mean(volume.shift(1), period)", "volume"),
    ("VOLUME_ANOMALY", "(volume-prior_mean)/prior_std; flat baseline undefined", "volume"),
    ("RELATIVE_STRENGTH", "instrument ROC minus time-aligned benchmark ROC", "close benchmark"),
    ("VOL_ADJUSTED_RETURN", "ROC/(std(one-bar returns)*sqrt(period))", "close"),
    (
        "MOMENTUM_RANK",
        "cross-sectional percentile of ROC at identical decision timestamps",
        "close cross_section",
    ),
    ("TREND_PERSISTENCE", "abs(mean(sign(close.diff), period))", "close"),
    ("TREND_STRENGTH", "(EMA(period)-EMA(2*period))/ATR", "high low close"),
    ("RANGE_COMPRESSION", "BB_width/mean(BB_width, period)", "close"),
    ("BREAKOUT_DISTANCE", "close/prior_Donchian_high-1", "high close"),
    ("LIQUIDITY_SCORE", "ROC*log1p(mean(quote volume))/(1+spread_bps)", "close quote_volume bid ask"),
    ("BETA", "rolling covariance(returns,benchmark returns)/benchmark variance", "close benchmark"),
    ("CORRELATION", "rolling Pearson correlation with benchmark", "close benchmark"),
    ("REVERSAL_SEVERITY", "abs(drawdown)/per-bar historical volatility", "close"),
    ("MARKET_RISK", "mean(sign(universe ROC)) at matched timestamps", "close cross_section"),
    ("QUOTE_SPREAD", "10000*(ask-bid)/mid", "bid ask"),
]:
    register(id, formula, fields)
register("MACD", "EMA(fast)-EMA(slow)", params=("fast", "slow", "signal"))
register("MACD_SIGNAL", "EMA(MACD, signal)", params=("fast", "slow", "signal"))
register("MACD_HIST", "MACD-MACD_SIGNAL", params=("fast", "slow", "signal"))
for id, formula, fields in [
    ("OI_LEVEL", "reported open interest in base units; other units rejected", "open_interest"),
    ("OI_CHANGE", "OI/OI.shift(period)-1, consistent base units", "open_interest"),
    ("FUNDING", "reported current rate; not a realized settlement", "funding_rate"),
    ("FUNDING_MEAN", "rolling mean of observed rate snapshots; not cumulative realized cash", "funding_rate"),
    ("BASIS", "reported futures/spot basis", "basis"),
    ("PREMIUM", "reported mark/index premium", "premium"),
    ("SPOT_PERP_RETURN", "ROC(perpetual)-ROC(observed spot)", "close spot_close"),
    ("TAKER_IMBALANCE", "(reported buy-reported sell)/(buy+sell)", "taker_buy taker_sell"),
    ("CVD", "cumulative signed actual aggressive trade base quantity", "aggressive_delta"),
    ("POSITIONING_EXTREME", "(OI-rolling_mean)/rolling_std", "open_interest"),
    (
        "LIQUIDATION_SHOCK",
        "max(-one_bar_return,0)*max(-one_bar_OI_change,0); proxy only",
        "close open_interest",
    ),
    ("ORDERBOOK_IMBALANCE", "(trusted bid_depth-ask_depth)/(bid_depth+ask_depth)", "bid_depth ask_depth"),
    ("DEPTH_CHANGE", "total trusted depth/total_depth.shift(period)-1", "bid_depth ask_depth"),
]:
    register(id, formula, fields, derivative=True)


def validate_params(id: str, params: dict) -> None:
    definition = REGISTRY[id]
    unknown = set(params) - set(definition.parameter_schema)
    if unknown:
        raise ValueError(f"{id}: unsupported factor parameters {sorted(unknown)}")
    for name, value in params.items():
        minimum = 1 if id == "OI_CHANGE" and name == "period" else 2
        if type(value) is not int or not minimum <= value <= 10000:
            raise ValueError(f"{id}.{name}: expected integer in [{minimum}, 10000]")
    if id.startswith("MACD") and params.get("fast", 12) >= params.get("slow", 26):
        raise ValueError("MACD fast must be less than slow")


def normalize(values: pd.Series, method: str) -> pd.Series:
    valid = values.replace([np.inf, -np.inf], np.nan)
    if method == "rank":
        return valid.rank(pct=True, method="average")
    if method == "zscore":
        std = valid.std(ddof=0)
        return (valid - valid.mean()) / std if std > 0 else valid * 0
    if method != "raw":
        raise ValueError(f"unsupported normalization {method}")
    return valid


class FeaturePipeline:
    """One vector per (symbol, factor, parameters). All vector operations are causal."""

    def __init__(self, frames: dict[str, pd.DataFrame], benchmark: str):
        self.frames = frames
        self.benchmark = benchmark
        self.cache: dict[tuple, pd.Series] = {}
        self.computations = 0

    def series(self, symbol: str, id: str, params: dict | None = None) -> pd.Series:
        id = id.upper()
        params = params or {}
        validate_params(id, params)
        key = (symbol, id, fingerprint(params))
        if key in self.cache:
            return self.cache[key]
        self.computations += 1
        df = self.frames[symbol]
        missing = set(REGISTRY[id].required_fields) - set(df) - {"benchmark", "cross_section"}
        if "benchmark" in REGISTRY[id].required_fields and self.benchmark not in self.frames:
            missing.add("benchmark")
        if missing:
            value = pd.Series(np.nan, index=df.index, dtype=float)
        else:
            value = self._compute(symbol, id, params).replace([np.inf, -np.inf], np.nan)
        value = value.astype(float)
        self.cache[key] = value
        return value

    def _compute(self, symbol: str, id: str, params: dict) -> pd.Series:
        if id in COMPUTATIONS:
            return COMPUTATIONS[id](self, symbol, params)
        df = self.frames[symbol]
        p = params.get("period", 14)
        c = df.get("close", pd.Series(np.nan, index=df.index))
        h, low, v = df.get("high"), df.get("low"), df.get("volume")
        ema = c.ewm(span=p, adjust=False, min_periods=p).mean()
        mean = c.rolling(p).mean()
        std = c.rolling(p).std(ddof=0)
        roc = c.pct_change(p, fill_method=None)
        if id == "SMA" or id == "BB_MID":
            return mean
        if id == "EMA":
            return ema
        if id == "WMA":
            weights = np.arange(1, p + 1)
            return c.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        if id == "RSI" or id == "STOCHRSI":
            d = c.diff()
            up = d.clip(lower=0).ewm(alpha=1 / p, adjust=False, min_periods=p).mean()
            down = (-d.clip(upper=0)).ewm(alpha=1 / p, adjust=False, min_periods=p).mean()
            rsi = 100 - 100 / (1 + up / down)
            rsi = rsi.mask((up == 0) & (down == 0), 50)
            if id == "RSI":
                return rsi
            return 100 * (rsi - rsi.rolling(p).min()) / (rsi.rolling(p).max() - rsi.rolling(p).min())
        if id.startswith("MACD"):
            fast, slow, signal = (params.get("fast", 12), params.get("slow", 26), params.get("signal", 9))
            macd = (
                c.ewm(span=fast, adjust=False, min_periods=slow).mean()
                - c.ewm(span=slow, adjust=False, min_periods=slow).mean()
            )
            sig = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
            return macd if id == "MACD" else sig if id == "MACD_SIGNAL" else macd - sig
        if id in ("ATR", "ADX", "DI_PLUS", "DI_MINUS"):
            # Reuse existing project's first-value-seeded Wilder conventions.
            tr = pd.Series(indicators.atr(h.tolist(), low.tolist(), c.tolist(), p), index=df.index)
            if id == "ATR":
                return tr.where(np.arange(len(c)) >= p - 1)
            up, down = h.diff(), -low.diff()
            plus = up.where((up > down) & (up > 0), 0).ewm(alpha=1 / p, adjust=False).mean()
            minus = down.where((down > up) & (down > 0), 0).ewm(alpha=1 / p, adjust=False).mean()
            if id == "DI_PLUS":
                return (100 * plus / tr).where(np.arange(len(c)) >= p)
            if id == "DI_MINUS":
                return (100 * minus / tr).where(np.arange(len(c)) >= p)
            dx = 100 * (plus - minus).abs() / (plus + minus)
            return dx.ewm(alpha=1 / p, adjust=False, min_periods=2 * p).mean()
        if id == "BB_UPPER":
            return mean + 2 * std
        if id == "BB_LOWER":
            return mean - 2 * std
        if id == "BB_WIDTH":
            return 4 * std / mean
        if id in ("STOCHASTIC", "KDJ_K", "KDJ_D", "KDJ_J"):
            rsv = 100 * (c - low.rolling(p).min()) / (h.rolling(p).max() - low.rolling(p).min())
            k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
            d = k.ewm(alpha=1 / 3, adjust=False).mean()
            return {"STOCHASTIC": rsv, "KDJ_K": k, "KDJ_D": d, "KDJ_J": 3 * k - 2 * d}[id]
        if id == "CCI":
            typical = (h + low + c) / 3
            deviation = typical.rolling(p).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
            return (typical - typical.rolling(p).mean()) / (0.015 * deviation)
        if id in ("AROON_UP", "AROON_DOWN"):
            seq = h if id == "AROON_UP" else low
            pick = np.argmax if id == "AROON_UP" else np.argmin
            return seq.rolling(p).apply(lambda x: 100 * (p - 1 - pick(x[::-1])) / (p - 1), raw=True)
        if id == "ROC":
            return roc
        if id == "MOMENTUM":
            return c.diff(p)
        if id in ("DONCHIAN_HIGH", "BREAKOUT_HIGH"):
            return h.shift(1).rolling(p).max()
        if id in ("DONCHIAN_LOW", "BREAKOUT_LOW"):
            return low.shift(1).rolling(p).min()
        if id == "HIST_VOL":
            return np.log(c / c.shift()).rolling(p).std()
        if id == "REALIZED_RANGE":
            return np.sqrt((np.log(h / low) ** 2).rolling(p).mean() / (4 * np.log(2)))
        if id == "DRAWDOWN":
            return c / c.rolling(p).max() - 1
        if id == "MA_DISTANCE":
            return c / ema - 1
        if id in ("PIVOT_LOW", "PIVOT_HIGH"):
            bars = [
                Candle(symbol, "configured", int(r.ts) - 1, int(r.ts), r.close, r.high, r.low, r.close, 1)
                for r in df.itertuples()
            ]
            output = pd.Series(np.nan, index=df.index)
            kind = "LOW" if id == "PIVOT_LOW" else "HIGH"
            for pivot in confirmed_pivots(bars):
                if pivot.kind == kind:
                    output.iloc[pivot.confirmed_index] = pivot.price
            return output.ffill()
        if id == "SUPPORT_DISTANCE":
            return c / self.series(symbol, "PIVOT_LOW") - 1
        if id == "RESISTANCE_DISTANCE":
            return self.series(symbol, "PIVOT_HIGH") / c - 1
        if id == "RSRS":
            return low.rolling(p).cov(h) / low.rolling(p).var()
        if id == "VOLUME_SMA":
            return v.rolling(p).mean()
        if id == "OBV":
            return (np.sign(c.diff()).fillna(0) * v).cumsum()
        if id == "VWAP":
            return df.quote_volume.rolling(p).sum() / v.rolling(p).sum()
        if id == "RELATIVE_VOLUME":
            return v / v.shift().rolling(p).mean()
        if id == "VOLUME_ANOMALY":
            return (v - v.shift().rolling(p).mean()) / v.shift().rolling(p).std()
        if id == "VOL_ADJUSTED_RETURN":
            return roc / (c.pct_change(fill_method=None).rolling(p).std() * np.sqrt(p))
        if id == "TREND_PERSISTENCE":
            return np.sign(c.diff()).rolling(p).mean().abs()
        if id == "TREND_STRENGTH":
            return (ema - c.ewm(span=2 * p, adjust=False, min_periods=2 * p).mean()) / self.series(
                symbol, "ATR", {"period": p}
            )
        if id == "RANGE_COMPRESSION":
            width = self.series(symbol, "BB_WIDTH", {"period": p})
            return width / width.rolling(p).mean()
        if id == "BREAKOUT_DISTANCE":
            return c / self.series(symbol, "DONCHIAN_HIGH", {"period": p}) - 1
        if id in ("RELATIVE_STRENGTH", "BETA", "CORRELATION"):
            benchmark = self.frames[self.benchmark].set_index("ts").close.reindex(df.ts).set_axis(df.index)
            if id == "RELATIVE_STRENGTH":
                return roc - benchmark.pct_change(p, fill_method=None)
            a, b = c.pct_change(fill_method=None), benchmark.pct_change(fill_method=None)
            return a.rolling(p).corr(b) if id == "CORRELATION" else a.rolling(p).cov(b) / b.rolling(p).var()
        if id in ("MOMENTUM_RANK", "MARKET_RISK"):
            table = pd.DataFrame(
                {s: self.series(s, "ROC", {"period": p}).set_axis(f.ts) for s, f in self.frames.items()}
            )
            out = (
                table.rank(axis=1, pct=True)[symbol] if id == "MOMENTUM_RANK" else np.sign(table).mean(axis=1)
            )
            return out.reindex(df.ts).set_axis(df.index)
        if id == "QUOTE_SPREAD":
            return 20000 * (df.ask - df.bid) / (df.ask + df.bid)
        if id == "LIQUIDITY_SCORE":
            return (
                roc * np.log1p(df.quote_volume.rolling(p).mean()) / (1 + self.series(symbol, "QUOTE_SPREAD"))
            )
        if id == "REVERSAL_SEVERITY":
            return self.series(symbol, "DRAWDOWN", {"period": p}).abs() / self.series(
                symbol, "HIST_VOL", {"period": p}
            )
        direct = {
            "OI_LEVEL": "open_interest",
            "FUNDING": "funding_rate",
            "BASIS": "basis",
            "PREMIUM": "premium",
        }
        if id in direct:
            return df[direct[id]]
        if id == "OI_CHANGE":
            return df.open_interest.pct_change(p, fill_method=None)
        if id == "FUNDING_MEAN":
            return df.funding_rate.rolling(p).mean()
        if id == "SPOT_PERP_RETURN":
            return roc - df.spot_close.pct_change(p, fill_method=None)
        if id == "TAKER_IMBALANCE":
            return (df.taker_buy - df.taker_sell) / (df.taker_buy + df.taker_sell)
        if id == "CVD":
            return df.aggressive_delta.cumsum(skipna=False)
        if id == "POSITIONING_EXTREME":
            return (df.open_interest - df.open_interest.rolling(p).mean()) / df.open_interest.rolling(p).std()
        if id == "LIQUIDATION_SHOCK":
            return (-c.pct_change(fill_method=None)).clip(lower=0) * (
                -df.open_interest.pct_change(fill_method=None)
            ).clip(lower=0)
        if id == "ORDERBOOK_IMBALANCE":
            return (df.bid_depth - df.ask_depth) / (df.bid_depth + df.ask_depth)
        if id == "DEPTH_CHANGE":
            return (df.bid_depth + df.ask_depth).pct_change(p, fill_method=None)
        raise ValueError(f"registered factor lacks computation: {id}")

    def result(
        self, symbol: str, id: str, index: int, decision_ts: int, params: dict | None = None
    ) -> FactorResult:
        id = id.upper()
        df = self.frames[symbol]
        if not 0 <= index < len(df):
            return FactorResult(id, None, Status.MISSING, None, "NO_OBSERVATION")
        available = int(df.available_ts.iloc[: index + 1].max())
        for dependency in REGISTRY[id].required_fields:
            column = dependency + "__available_ts"
            if column in df:
                known = df[column].iloc[: index + 1].dropna()
                if len(known):
                    available = max(available, int(known.max()))
        if available > decision_ts:
            return FactorResult(id, None, Status.INADMISSIBLE, available, "DEPENDENCY_AFTER_DECISION")
        if id in ("RELATIVE_STRENGTH", "BETA", "CORRELATION", "MOMENTUM_RANK", "MARKET_RISK"):
            symbols = (
                [self.benchmark] if id in ("RELATIVE_STRENGTH", "BETA", "CORRELATION") else list(self.frames)
            )
            ts = df.ts.iloc[index]
            for s in symbols:
                if s not in self.frames:
                    return FactorResult(id, None, Status.INADMISSIBLE, None, "REFERENCE_SOURCE_MISSING")
                matched = self.frames[s].loc[self.frames[s].ts == ts]
                known = self.frames[s].loc[self.frames[s].ts <= ts]
                if matched.empty or int(known.available_ts.max()) > decision_ts:
                    return FactorResult(
                        id, None, Status.INADMISSIBLE, None, "CROSS_SECTION_NOT_YET_AVAILABLE"
                    )
        missing = set(REGISTRY[id].required_fields) - set(df) - {"benchmark", "cross_section"}
        if missing:
            return FactorResult(id, None, Status.MISSING, None, "MISSING_FIELDS:" + ",".join(sorted(missing)))
        value = self.series(symbol, id, params).iloc[index]
        if not np.isfinite(value):
            status = Status.WARMUP if index < 2 * (params or {}).get("period", 14) else Status.MISSING
            return FactorResult(id, None, status, available, "UNDEFINED_OR_INSUFFICIENT_WINDOW")
        return FactorResult(id, float(value), Status.OK, available)


def quality_table(pipeline: FeaturePipeline) -> list[dict]:
    rows = []
    for id in REGISTRY:
        values = pd.concat([pipeline.series(s, id) for s in pipeline.frames])
        rows.append(
            {
                "factor": id,
                "coverage": float(values.notna().mean()),
                "finite_observations": int(values.notna().sum()),
                "total": len(values),
            }
        )
    return sorted(rows, key=lambda r: (-r["coverage"], r["factor"]))
