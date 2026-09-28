from __future__ import annotations

from ..domain import Regime
from .config import MarketWatchConfig
from .domain import (
    BenchmarkContext,
    DirectionalDecision,
    EntryQuality,
    MarketSnapshot,
    RelativePerformance,
)


def evaluate_benchmark_context(
    btc_snapshot: MarketSnapshot | None,
    eth_snapshot: MarketSnapshot | None,
    config: MarketWatchConfig,
) -> tuple[BenchmarkContext, tuple[str, ...], tuple[str, ...]]:
    """Derive global benchmark context from BTC and ETH multi-timeframe states."""
    reasons: list[str] = []
    risks: list[str] = []

    if btc_snapshot is None:
        return BenchmarkContext.BENCHMARK_NEUTRAL, ("BTC_SNAPSHOT_UNAVAILABLE",), ()

    btc_1h = btc_snapshot.tf_1h
    btc_4h = btc_snapshot.tf_4h
    tc = config.thresholds

    # Explicit 1h elapsed return (authoritative B0 semantics, strictly no ROC fallback)
    btc_return_1h = btc_snapshot.return_1h
    if btc_return_1h is None:
        reasons.append("BTC_RETURN_1H_UNAVAILABLE")

    # Check for BTC Volatility Shock using true return_1h only
    btc_vol_shock = (
        btc_return_1h is not None
        and btc_1h.atr_percentile >= tc.high_vol_atr_percentile
        and btc_return_1h < -0.015
    )
    if btc_vol_shock:
        reasons.append("BTC_DOWNSIDE_VOLATILITY_SHOCK")
        risks.append("BTC_FLASH_DROP_RISK")
        return BenchmarkContext.BTC_VOLATILITY_SHOCK, tuple(reasons), tuple(risks)

    # Check for ETH Volatility Shock using true return_1h only
    if eth_snapshot is not None:
        eth_1h = eth_snapshot.tf_1h
        eth_return_1h = eth_snapshot.return_1h
        if eth_return_1h is None:
            reasons.append("ETH_RETURN_1H_UNAVAILABLE")
        elif (
            eth_1h.atr_percentile >= tc.high_vol_atr_percentile
            and eth_return_1h < -0.02
        ):
            reasons.append("ETH_DOWNSIDE_VOLATILITY_SHOCK")
            risks.append("ETH_FLASH_DROP_RISK")
            return BenchmarkContext.ETH_VOLATILITY_SHOCK, tuple(reasons), tuple(risks)

    # Risk-off if BTC is firmly in downtrend or lost major support
    if btc_1h.regime == Regime.TREND_DOWN or btc_4h.regime == Regime.TREND_DOWN:
        reasons.append("BTC_TREND_DOWN_DOMINANT")
        risks.append("MARKET_HEADWINDS_FOR_LONGS")
        return BenchmarkContext.MARKET_RISK_OFF, tuple(reasons), tuple(risks)

    # Risk-on if BTC is firmly in uptrend
    if btc_1h.regime == Regime.TREND_UP and btc_4h.regime == Regime.TREND_UP:
        reasons.append("BTC_TREND_UP_ALIGNED")
        return BenchmarkContext.MARKET_RISK_ON, tuple(reasons), tuple(risks)

    reasons.append("BENCHMARK_BALANCED_OR_RANGE")
    return BenchmarkContext.BENCHMARK_NEUTRAL, tuple(reasons), tuple(risks)


def apply_benchmark_context_gate(
    *,
    symbol: str,
    decision: DirectionalDecision,
    benchmark_context: BenchmarkContext,
    relative_perf: RelativePerformance | None,
    entry_quality: EntryQuality,
    net_rr: float,
    config: MarketWatchConfig,
) -> tuple[DirectionalDecision, tuple[str, ...], tuple[str, ...]]:
    """Gate or penalize altcoin directional setups against BTC benchmark context.

    If BTC is in RISK_OFF or VOLATILITY_SHOCK:
    Alt LONG candidates are vetoed (switched to WAIT) UNLESS they display
    exceptional relative strength, GOOD+ entry quality, and high net RR.
    """
    if symbol in config.benchmark_symbols or decision != DirectionalDecision.LONG:
        return decision, (), ()

    reasons: list[str] = []
    risks: list[str] = []

    is_shock = benchmark_context in (
        BenchmarkContext.MARKET_RISK_OFF,
        BenchmarkContext.BTC_VOLATILITY_SHOCK,
        BenchmarkContext.ETH_VOLATILITY_SHOCK,
    )

    if is_shock:
        # Check exceptional relative strength exemption:
        # 1. 1h relative to BTC >= 2.5%
        # 2. Entry quality is GOOD or EXCELLENT
        # 3. Net RR >= high_quality_net_rr
        is_exceptional = (
            relative_perf is not None
            and relative_perf.rel_to_btc_1h is not None
            and relative_perf.rel_to_btc_1h >= 0.025
            and entry_quality in (EntryQuality.EXCELLENT, EntryQuality.GOOD)
            and net_rr >= config.high_quality_net_rr
        )

        if is_exceptional:
            reasons.append("EXCEPTIONAL_RELATIVE_STRENGTH_AGAINST_BTC_SHOCK")
            risks.append("BENCHMARK_RISK_OFF_CAUTION")
            return decision, tuple(reasons), tuple(risks)

        # Otherwise: VETO the Long and switch to WAIT
        reasons.append("BTC_BENCHMARK_RISK_OFF_VETO")
        reasons.append("WAIT_FOR_BENCHMARK_STABILIZATION")
        risks.append("BTC_CORRELATION_DRAG_RISK")
        return DirectionalDecision.WAIT, tuple(reasons), tuple(risks)

    return decision, (), ()
