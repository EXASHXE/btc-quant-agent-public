"""Causal regime hysteresis, mechanism-group selection and frozen setup geometry."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core import dec, fingerprint, primitive, quantize
from ..strategies import REGISTRY
from .sources import MINUTE, STRUCTURE, SourceHistory
from .store import SelectorStore

VERSION = "l23-selector-v1.0-engineering-hypothesis"
GROUPS = {
    "EMA": "trend",
    "SMA": "trend",
    "MACD_HIST": "trend",
    "ADX": "trend",
    "RELATIVE_STRENGTH": "relative_strength",
    "VOLUME_ANOMALY": "participation",
    "RELATIVE_VOLUME": "participation",
    "ATR": "volatility_context",
    "RSI": "oscillator",
}
PLAYS = ("trend_pullback", "breakout_retest", "bollinger_reversion")


class Policy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    version: str = VERSION
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    benchmark: str = "BTCUSDT"
    enabled: tuple[str, ...] = PLAYS
    structural_interval_ms: int = STRUCTURE
    monitor_interval_ms: int = MINUTE
    quote_max_age_ms: int = Field(5000, gt=0, le=10000)
    funding_max_age_ms: int = Field(300_000, gt=0)
    response_minutes: tuple[int, ...] = (1, 3, 5)
    latency_stress_minutes: tuple[int, ...] = (10, 15)
    independent_confirmations: int = Field(2, ge=2)
    min_rank_members: int = Field(10, ge=10)
    fee_bps: float = Field(4, ge=0)
    slippage_bps: float = Field(2, ge=0)
    max_spread_bps: float = Field(25, gt=0)
    per_trade_risk: float = Field(0.0025, gt=0, le=0.01)
    total_risk: float = Field(0.0075, gt=0, le=0.05)
    cluster_risk: float = Field(0.005, gt=0, le=0.05)
    gross: float = Field(1, gt=0)
    symbol: float = Field(0.2, gt=0)
    net_beta: float = Field(0.5, gt=0)
    leverage: float = Field(1, ge=1, le=5)
    funding_review_hours: int = Field(24, ge=1)
    # Duplicate trend indicators are alternative representations, never independent votes.
    factor_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "EMA": 1.0,
            "ADX": 1.0,
            "MACD_HIST": 1.0,
            "RELATIVE_STRENGTH": 1.0,
            "VOLUME_ANOMALY": 1.0,
        }
    )
    mechanism_weights: dict[str, float] = Field(
        default_factory=lambda: {"trend": 1.0, "relative_strength": 1.0, "participation": 1.0}
    )

    @model_validator(mode="after")
    def validate_contract(self):
        if (
            self.version != VERSION
            or self.structural_interval_ms != STRUCTURE
            or self.monitor_interval_ms != MINUTE
        ):
            raise ValueError("UNSUPPORTED_SELECTOR_VERSION_OR_INTERVAL")
        if len(set(self.symbols)) != len(self.symbols) or self.benchmark not in self.symbols:
            raise ValueError("UNIVERSE_IDENTITY_INVALID")
        if not set(self.enabled) <= set(PLAYS) or not self.enabled:
            raise ValueError("ONLY_THREE_BOUNDED_V1_PLAYBOOKS_ARE_ACTIONABLE")
        if any(f not in GROUPS or w < 0 or not isfinite(w) for f, w in self.factor_weights.items()):
            raise ValueError("INVALID_FACTOR_ROLE_OR_WEIGHT")
        if any(
            g not in set(GROUPS.values()) or w < 0 or not isfinite(w)
            for g, w in self.mechanism_weights.items()
        ):
            raise ValueError("INVALID_MECHANISM_WEIGHT")
        if self.cluster_risk > self.total_risk or self.per_trade_risk > self.total_risk:
            raise ValueError("RISK_BUDGET_INCONSISTENT")
        return self

    @property
    def hash(self) -> str:
        return fingerprint(self)


def load_policy(path: str | Path) -> Policy:
    return Policy.model_validate(yaml.safe_load(Path(path).read_text()))


def group_confirmations(votes: dict[str, bool], policy: Policy) -> dict:
    groups: dict[str, list[str]] = {}
    for factor, passed in sorted(votes.items()):
        group = GROUPS.get(factor)
        if group and group != "volatility_context" and passed and policy.factor_weights.get(factor, 0) > 0:
            groups.setdefault(group, []).append(factor)
    return {
        "groups": groups,
        "independent_votes": len(groups),
        "score": sum(policy.mechanism_weights.get(g, 0) for g in groups),
        "semantics": "One contribution per mechanism; context and hard gates do not vote",
    }


def metrics(history: SourceHistory, symbol: str) -> dict:
    df, pipeline = history.frames[symbol], history.pipeline
    if len(df) < 65:
        return {"usable": False, "reason": "STRUCTURAL_WARMUP"}
    i, ts = len(df) - 1, history.universe.cutoff + 1000
    if int(df.ts.iloc[-1]) != history.universe.cutoff or any(np.diff(df.ts.tail(65)) != STRUCTURE):
        return {"usable": False, "reason": "SOURCE_OUTAGE_OR_INTERVAL_CHANGE"}

    def f(name, params=None):
        return pipeline.result(symbol, name, i, ts, params).value

    atr, adx, ema20, ema40 = f("ATR"), f("ADX"), f("EMA", {"period": 20}), f("EMA", {"period": 40})
    if any(v is None for v in (atr, adx, ema20, ema40)) or atr <= 0:
        return {"usable": False, "reason": "STRUCTURAL_FACTORS_UNAVAILABLE"}
    close = df.close
    path = float(close.diff().abs().tail(20).sum())
    if not path:
        return {"usable": False, "reason": "ZERO_PATH_UNKNOWN"}
    slope = float(
        pipeline.series(symbol, "EMA", {"period": 40}).iloc[-1]
        - pipeline.series(symbol, "EMA", {"period": 40}).iloc[-4]
    )
    sigma = float(close.pct_change().iloc[-61:-1].std(ddof=1))
    # This proxy is deliberately not labeled a calibrated volatility percentile or liquidation observation.
    true_range = pd.concat(
        [df.high - df.low, (df.high - close.shift()).abs(), (df.low - close.shift()).abs()], axis=1
    ).max(axis=1)
    prior_range = float(true_range.iloc[-61:-1].median())
    z = float(close.pct_change().iloc[-1]) / max(sigma, float(df.close.iloc[-1]) ** -1 * 0.01)
    oi = f("OI_CHANGE", {"period": 1})
    rvol = f("RELATIVE_VOLUME")
    return {
        "usable": True,
        "atr": atr,
        "adx": adx,
        "ema20": ema20,
        "ema40": ema40,
        "T": (ema20 - ema40) / atr,
        "slope": slope,
        "ER": abs(float(close.iloc[-1] - close.iloc[-21])) / path,
        "range_intact": float(df.low.iloc[-21:-1].min())
        <= float(close.iloc[-1])
        <= float(df.high.iloc[-21:-1].max()),
        "high_volatility_proxy": float(true_range.iloc[-1]) > 3 * prior_range,
        "z_return": z,
        "oi_change": oi,
        "rvol": rvol,
        "volatility_semantics": "prior 60-bar sigma/range engineering proxy; not daily percentile",
        "lineage_hash": fingerprint(history.lineage(symbol, "close")),
    }


def advance_regime(old: dict, m: dict, cutoff: int, *, source_healthy: bool = True) -> dict:
    if cutoff < old.get("cutoff", -1):
        raise ValueError("REGIME_DECISION_PRECEDES_CHECKPOINT")
    if cutoff == old.get("cutoff", -1):
        return old
    state, pending = old.get("state", "UNKNOWN"), old.get("pending", "UNKNOWN")
    if not source_healthy or not m.get("usable"):
        return {
            "state": "UNKNOWN",
            "pending": "UNKNOWN",
            "count": 0,
            "failures": 0,
            "cutoff": cutoff,
            "reason": m.get("reason", "SOURCE_HEALTH_OVERRIDE"),
            "metrics": m,
        }
    shock = (
        abs(m["z_return"]) >= 3
        and m.get("oi_change") is not None
        and m["oi_change"] <= -0.02
        and (m.get("rvol") is not None and m["rvol"] >= 2)
    )
    if shock or m["high_volatility_proxy"] or abs(m["z_return"]) >= 3:
        state = "DELEVERAGING_SHOCK" if shock else "HIGH_VOLATILITY"
        return {
            "state": state,
            "pending": "UNKNOWN",
            "count": 0,
            "failures": 0,
            "cutoff": cutoff,
            "reason": "IMMEDIATE_RESTRICTION_PROXY",
            "metrics": m,
        }
    trend_up = m["adx"] >= 25 and m["T"] >= 0.5 and m["slope"] > 0 and m["ER"] >= 0.35
    trend_down = m["adx"] >= 25 and m["T"] <= -0.5 and m["slope"] < 0 and m["ER"] >= 0.35
    range_ok = m["adx"] <= 18 and abs(m["T"]) <= 0.25 and m["ER"] <= 0.25 and m["range_intact"]
    proposed = "TREND_UP" if trend_up else "TREND_DOWN" if trend_down else "RANGE" if range_ok else "UNKNOWN"
    side = 1 if state == "TREND_UP" else -1
    retained = (
        state in {"TREND_UP", "TREND_DOWN"}
        and m["adx"] >= 20
        and side * m["T"] >= 0.25
        and side * m["slope"] > 0
    ) or (state == "RANGE" and m["adx"] < 22 and abs(m["T"]) < 0.4 and m["ER"] < 0.35 and m["range_intact"])
    count = old.get("count", 0) + 1 if pending == proposed else 1
    failures = 0 if retained else old.get("failures", 0) + 1
    if proposed != "UNKNOWN" and count >= 2:
        state, failures = proposed, 0
    elif not retained and failures >= 2:
        state = "UNKNOWN"
    return {
        "state": state,
        "pending": proposed,
        "count": count,
        "failures": failures,
        "cutoff": cutoff,
        "reason": "CAUSAL_TWO_BAR_HYSTERESIS",
        "metrics": m,
    }


@dataclass(frozen=True)
class Setup:
    anchors: dict
    ranking: dict
    vetoes: tuple[str, ...] = ()


def portfolio_beta(history: SourceHistory, symbol: str) -> float | None:
    asset, ref = history.frames[symbol], history.frames[history.universe.benchmark]
    joined = asset[["ts", "close"]].merge(ref[["ts", "close"]], on="ts", suffixes=("", "_btc"))
    if len(joined) < 201 or not history.synchronized():
        return None
    returns = joined[["close", "close_btc"]].tail(289).pct_change().dropna()
    if len(returns) < 200 or returns.close_btc.var() <= 1e-15:
        return None
    return float(returns.close.cov(returns.close_btc) / returns.close_btc.var())


def ranks(history: SourceHistory, side: str, policy: Policy) -> dict[str, dict]:
    if not history.synchronized() or len(history.universe.members) < policy.min_rank_members:
        return {
            s: {
                "opportunity": None,
                "side_strength": None,
                "reason": "SYNCHRONIZED_RANK_COVERAGE_UNAVAILABLE",
            }
            for s in history.universe.members
        }
    raw = {}
    sign = 1 if side == "LONG" else -1
    for symbol, df in history.frames.items():
        i = len(df) - 1
        atr = history.pipeline.result(symbol, "ATR", i, history.universe.cutoff + 1000).value
        rvol = history.pipeline.result(symbol, "RELATIVE_VOLUME", i, history.universe.cutoff + 1000).value
        beta = portfolio_beta(history, symbol)
        if len(df) < 201 or atr is None or rvol is None or beta is None:
            return {
                s: {"opportunity": None, "side_strength": None, "reason": "RANK_WARMUP"}
                for s in history.universe.members
            }
        ret = df.close.pct_change(12).iloc[-1]
        benchmark = history.frames[history.universe.benchmark].close.pct_change(12).iloc[-1]
        vol = df.close.pct_change(12).iloc[-61:-1].std()
        friction = (
            df.close.iloc[-1] * (2 * policy.fee_bps + 2 * policy.slippage_bps + policy.max_spread_bps) / 10000
        )
        raw[symbol] = {
            "participation": float(np.log1p(rvol)),
            "geometry": min(atr / friction, 10),
            "side_strength": sign
            * float(ret if symbol == history.universe.benchmark else ret - beta * benchmark)
            / max(float(vol), 1e-9),
        }
    df = pd.DataFrame(raw).T.rank(method="average", pct=True)
    return {
        s: {
            "opportunity": float(0.5 * df.loc[s, "participation"] + 0.5 * df.loc[s, "geometry"]),
            "side_strength": float(df.loc[s, "side_strength"]),
            "universe_hash": history.universe.hash,
            "denominator": len(raw),
            "semantics": "Side-aware ranks; not probability",
        }
        for s in raw
    }


def make_setup(
    history: SourceHistory, symbol: str, strategy: str, regime: str, policy: Policy, ranking: dict
) -> Setup | None:
    df, pipeline = history.frames[symbol], history.pipeline
    if len(df) < 65:
        return None
    m = metrics(history, symbol)
    if not m["usable"]:
        return None
    i, atr = len(df) - 1, m["atr"]
    row, prior = df.iloc[-1], df.iloc[-21:-1]
    direction = "LONG" if regime == "TREND_UP" else "SHORT" if regime == "TREND_DOWN" else None
    target = None
    now = history.universe.cutoff + 1000
    spec = next(b.spec for b in history.bars if b.spec.symbol == symbol)
    if strategy == "trend_pullback":
        if direction is None or not (
            row.low <= m["ema20"] + 0.25 * atr and row.high >= m["ema20"] - 0.25 * atr
        ):
            return None
        anchor, ttl, mechanism = m["ema20"], 15, "TREND_PULLBACK"
    elif strategy == "breakout_retest":
        if direction is None:
            return None
        anchor = float(prior.high.max() if direction == "LONG" else prior.low.min())
        if (1 if direction == "LONG" else -1) * (row.close - anchor) < 0.05 * atr:
            return None
        ttl, mechanism = 20, "TREND_RETEST"
    elif strategy == "bollinger_reversion":
        if regime != "RANGE":
            return None
        lower = pipeline.result(symbol, "BB_LOWER", i, now, {"period": 20}).value
        upper = pipeline.result(symbol, "BB_UPPER", i, now, {"period": 20}).value
        target = pipeline.result(symbol, "BB_MID", i, now, {"period": 20}).value
        if any(v is None for v in (lower, upper, target)):
            return None
        direction = "LONG" if row.low < lower else "SHORT" if row.high > upper else None
        if direction is None:
            return None
        anchor, ttl, mechanism = lower if direction == "LONG" else upper, 10, "BOUNDED_RANGE"
    else:
        return None
    side = 1 if direction == "LONG" else -1
    stop_ref = float(df.low.tail(12).min() if side == 1 else df.high.tail(12).max())
    stop = quantize(stop_ref - side * max(2 * float(spec.tick_size), 0.15 * atr), spec.tick_size, up=side < 0)
    zone_width = 0.15 * atr if strategy == "breakout_retest" else 0.25 * atr
    low, high = (
        quantize(anchor - zone_width, spec.tick_size),
        quantize(anchor + zone_width, spec.tick_size, up=True),
    )
    p0 = quantize(anchor, spec.tick_size, up=side < 0)
    price_risk = side * float(p0 - stop)
    if price_risk <= 0 or (target is not None and side * (target - float(p0)) <= 0):
        return None
    chase = p0 + dec(side * min(0.35 * atr, 0.25 * price_risk))
    setup_bar = int(row.ts)
    reference_row = prior.high.idxmax() if direction == "SHORT" else prior.low.idxmin()
    if strategy == "breakout_retest":
        reference_row = prior.high.idxmax() if direction == "LONG" else prior.low.idxmin()
    structural_id = fingerprint(
        [spec.provider, spec.market, symbol, direction, mechanism, int(df.loc[reference_row, "ts"])]
    )
    identity = fingerprint([symbol, direction, mechanism, structural_id])
    votes = group_confirmations(
        {
            "EMA": direction is not None,
            "ADX": m["adx"] >= 20,
            "MACD_HIST": direction is not None,
            "VOLUME_ANOMALY": (m["rvol"] or 0) >= 1,
        },
        policy,
    )
    anchors = {
        "id": identity,
        "symbol": symbol,
        "side": direction,
        "strategy": strategy,
        "strategy_version": REGISTRY[strategy].version,
        "evidence_tier": str(REGISTRY[strategy].evidence_tier),
        "mechanism": mechanism,
        "setup_bar_id": fingerprint([spec.provider, symbol, STRUCTURE, setup_bar]),
        "setup_ts": setup_bar,
        "anchor": str(p0),
        "atr": atr,
        "structural_setup_id": structural_id,
        "zone_low": str(low),
        "zone_high": str(high),
        "chase_cap": str(quantize(chase, spec.tick_size, up=side < 0)),
        "original_stop": str(stop),
        "stop_reference": stop_ref,
        "stop": str(stop),
        "target": str(quantize(target, spec.tick_size, up=side < 0)) if target is not None else None,
        "expiry": setup_bar + ttl * MINUTE,
        "policy_hash": policy.hash,
        "universe_hash": history.universe.hash,
        "beta": portfolio_beta(history, symbol),
        "cluster": "CONSERVATIVE_CRYPTO_COMMON_CLUSTER",
        "regime": regime,
        "confirmations": votes,
        "source_lineage_hash": m["lineage_hash"],
        "contract": primitive(spec),
        "instrument_hash": fingerprint(spec),
        "entry_mode": "resting_limit" if strategy == "breakout_retest" else "market",
        "funding_semantics": "Adverse 24h risk horizon, not a holding deadline",
    }
    from ..canary.clock_domain import NativeProvenance, current_decision, native_bounds

    source = history.traces.get((symbol, setup_bar, "close"))
    context = current_decision()
    if source and isinstance(source.provenance, NativeProvenance) and context:
        anchors.update(
            known_at_ts=context[0]["wall_ms"],
            known_clock_sample=context[0],
            clock_epoch_id=context[0]["epoch_id"],
            expiry_mono_ms=native_bounds(source.provenance, anchors["expiry"])[0],
            setup_provenance=primitive(source.provenance),
            owner_scope_hash=context[1],
        )
    vetoes = () if ranking.get("opportunity") is not None else ("RANK_COVERAGE_WATCH_ONLY",)
    return Setup(anchors, ranking, vetoes)


def resolve_setups(setups: list[Setup]) -> tuple[list[Setup], list[dict]]:
    """Veto first, one episode per mechanism, then reject unresolved opposing evidence."""
    eligible, rejected = {}, []
    for setup in setups:
        a = setup.anchors
        if setup.vetoes:
            rejected.append({"id": a["id"], "reasons": list(setup.vetoes), "state": "WATCH"})
            continue
        eligible[a["id"]] = setup
    selected: list[Setup] = []
    for symbol in sorted({s.anchors["symbol"] for s in eligible.values()}):
        items = [s for s in eligible.values() if s.anchors["symbol"] == symbol]
        if len({s.anchors["side"] for s in items}) > 1:
            rejected.extend(
                {"id": s.anchors["id"], "state": "WATCH", "reasons": ["UNRESOLVED_OPPOSING_SETUPS"]}
                for s in items
            )
            continue
        # Multiple representations of a mechanism cannot create extra votes/opportunities.
        groups: dict[str, Setup] = {}
        for s in sorted(items, key=lambda s: (-(s.ranking.get("opportunity") or 0), s.anchors["id"])):
            groups.setdefault(s.anchors["mechanism"], s)
        selected.extend(groups.values())
    return selected, rejected


def scan(history: SourceHistory, store: SelectorStore, policy: Policy) -> dict:
    states, candidates, watch = {}, [], []
    all_ranks = {side: ranks(history, side, policy) for side in ("LONG", "SHORT")}
    for symbol in history.universe.members:
        old = store.regime(symbol)
        m = metrics(history, symbol)
        state = advance_regime(old, m, history.universe.cutoff)
        from ..canary.clock_domain import current_decision

        context = current_decision()
        if context and state["cutoff"] != old.get("cutoff"):
            state.update(clock_sample=context[0], clock_scope_hash=context[1])
        states[symbol] = store.save_regime(symbol, state)
        regime = state["state"]
        if regime in {"UNKNOWN", "HIGH_VOLATILITY", "DELEVERAGING_SHOCK"}:
            watch.append(
                {
                    "symbol": symbol,
                    "state": "WATCH",
                    "regime": regime,
                    "veto": "SOURCE_QUALIFIED_CESSATION_NOT_ESTABLISHED"
                    if regime == "DELEVERAGING_SHOCK"
                    else "REGIME_RESTRICTS_NEW_ENTRY",
                }
            )
        for strategy in policy.enabled:
            ranking = all_ranks["SHORT" if regime == "TREND_DOWN" else "LONG"][symbol]
            setup = make_setup(history, symbol, strategy, regime, policy, ranking)
            if setup:
                setup = Setup({**setup.anchors, "regime_evidence": states[symbol]}, ranking, setup.vetoes)
                try:
                    frozen = store.episode(setup.anchors["id"])
                except KeyError:
                    pass
                else:
                    setup = Setup(frozen["anchors"], ranking, setup.vetoes)
                candidates.append(setup)
    selected, rejected = resolve_setups(candidates)
    for s in selected:
        store.create_episode(s.anchors, s.anchors.get("known_at_ts", history.universe.cutoff + 1000))
    return {
        "version": VERSION,
        "source": "PUBLIC_READONLY_CANARY" if history.exposure == "PUBLIC_CANARY" else "OFFLINE_SYNTHETIC",
        "regimes": states,
        "candidates": [{"anchors": s.anchors, "ranking": s.ranking, "vetoes": s.vetoes} for s in candidates],
        "selected": [s.anchors["id"] for s in selected],
        "rejected": rejected,
        "watch": watch,
        "universe": history.universe,
        "policy_hash": policy.hash,
    }
