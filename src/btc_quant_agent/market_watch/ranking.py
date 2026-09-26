from __future__ import annotations

import statistics

from ..domain import Regime
from .config import MarketWatchConfig
from .domain import (
    BenchmarkContext,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    MarketSnapshot,
    RelativePerformance,
    TimeframeSnapshot,
)


def compute_relative_performances(
    snapshots: dict[str, MarketSnapshot],
    config: MarketWatchConfig,
) -> dict[str, RelativePerformance]:
    """Compute relative strength across the universe relative to BTC, ETH, and universe median."""
    if not snapshots:
        return {}

    returns_1h = {s: snap.tf_1h.roc for s, snap in snapshots.items()}
    median_1h = statistics.median(returns_1h.values()) if returns_1h else 0.0

    btc_snap = snapshots.get("BTCUSDT")
    eth_snap = snapshots.get("ETHUSDT")

    btc_1h = btc_snap.tf_1h.roc if btc_snap is not None else median_1h
    eth_1h = eth_snap.tf_1h.roc if eth_snap is not None else median_1h

    performances: dict[str, RelativePerformance] = {}
    for symbol, snap in snapshots.items():
        p15m = snap.tf_15m.roc
        p1h = snap.tf_1h.roc
        p4h = snap.tf_4h.roc

        rel_btc = p1h - btc_1h
        rel_eth = p1h - eth_1h
        rel_med = p1h - median_1h

        # Raw score centered at 50, scaled by excess return
        raw_score = 50.0 + (rel_med * 500.0)
        score = max(0.0, min(100.0, raw_score))

        performances[symbol] = RelativePerformance(
            symbol=symbol,
            perf_15m=round(p15m, 4),
            perf_1h=round(p1h, 4),
            perf_4h=round(p4h, 4),
            rel_to_btc_1h=round(rel_btc, 4),
            rel_to_eth_1h=round(rel_eth, 4),
            rel_to_median_1h=round(rel_med, 4),
            score=round(score, 2),
        )

    # Assign ranks based on score
    sorted_symbols = sorted(performances.keys(), key=lambda s: performances[s].score, reverse=True)
    ranked: dict[str, RelativePerformance] = {}
    for rank_idx, s in enumerate(sorted_symbols, 1):
        item = performances[s]
        ranked[s] = RelativePerformance(
            symbol=item.symbol,
            perf_15m=item.perf_15m,
            perf_1h=item.perf_1h,
            perf_4h=item.perf_4h,
            rel_to_btc_1h=item.rel_to_btc_1h,
            rel_to_eth_1h=item.rel_to_eth_1h,
            rel_to_median_1h=item.rel_to_median_1h,
            score=item.score,
            rank=rank_idx,
        )

    return ranked


def check_fatal_vetoes(
    *,
    decision: DirectionalDecision,
    exhaustion: ExhaustionMetrics,
    net_rr: float,
    tf_4h: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    benchmark_context: BenchmarkContext,
    config: MarketWatchConfig,
) -> tuple[bool, tuple[str, ...]]:
    """Enforce fatal vetoes that MUST occur BEFORE ranking.

    A high numerical score may NEVER override a fatal veto.
    """
    vetoes: list[str] = []

    if decision != DirectionalDecision.WAIT:
        # Fatal Veto 1: Extreme overextension in the trade direction
        if exhaustion.state == ExhaustionState.EXTREME and (
            (decision == DirectionalDecision.LONG and exhaustion.distance_from_ema20_atr > 0)
            or (decision == DirectionalDecision.SHORT and exhaustion.distance_from_ema20_atr < 0)
        ):
            vetoes.append("FATAL_VETO_EXTREME_OVEREXTENSION")

        # Fatal Veto 2: Net RR below absolute floor
        if net_rr < config.min_net_rr:
            vetoes.append("FATAL_VETO_INSUFFICIENT_NET_RR")

        # Fatal Veto 3: Direct HTF Conflict
        if decision == DirectionalDecision.LONG and tf_4h.regime == Regime.TREND_DOWN or decision == DirectionalDecision.SHORT and tf_4h.regime == Regime.TREND_UP:
            vetoes.append("FATAL_VETO_CONFIRMED_HTF_CONFLICT")

    # Fatal Veto 4: Excessive spread
    if derivatives.spread_bps is not None and derivatives.spread_bps > config.thresholds.max_spread_bps * 1.5:
        vetoes.append("FATAL_VETO_EXCESSIVE_SPREAD")

    return (len(vetoes) > 0), tuple(vetoes)


def calculate_opportunity_score(
    *,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
    entry_quality: EntryQuality,
    derivatives: DerivativesMetrics,
    exhaustion: ExhaustionMetrics,
    relative_perf: RelativePerformance | None,
    benchmark_context: BenchmarkContext,
    net_rr: float,
    has_fatal_veto: bool,
    config: MarketWatchConfig,
) -> float:
    """Calculate transparent multi-factor opportunity score for operational ranking."""
    if has_fatal_veto:
        return 0.0

    rc = config.ranking

    # 1. Trend Quality (0-100)
    adx_score = min(100.0, tf_1h.adx * 2.5)
    ema_slope_score = 100.0 if (tf_1h.ema_fast_slope > 0 and tf_1h.ema_mid_slope > 0) or (
        tf_1h.ema_fast_slope < 0 and tf_1h.ema_mid_slope < 0
    ) else 40.0
    trend_quality = 0.6 * adx_score + 0.4 * ema_slope_score

    # 2. Structure Quality (0-100)
    if tf_1h.structure in ("HH_HL", "LH_LL"):
        structure_quality = 90.0
    elif tf_1h.structure == "UNCONFIRMED":
        structure_quality = 40.0
    else:
        structure_quality = 60.0

    # 3. Entry Quality (0-100)
    eq_map = {
        EntryQuality.EXCELLENT: 95.0,
        EntryQuality.GOOD: 75.0,
        EntryQuality.MARGINAL: 40.0,
        EntryQuality.POOR: 15.0,
    }
    entry_score = eq_map.get(entry_quality, 20.0)

    # 4. Derivatives Confirmation (0-100)
    deriv_map = {
        DerivativesRegime.HEALTHY_LONG_BUILD: 90.0,
        DerivativesRegime.HEALTHY_SHORT_BUILD: 90.0,
        DerivativesRegime.SHORT_COVERING: 50.0,
        DerivativesRegime.LONG_LIQUIDATION: 30.0,
        DerivativesRegime.LONG_CROWDING: 20.0,
        DerivativesRegime.SHORT_CROWDING: 20.0,
        DerivativesRegime.DELEVERAGING: 15.0,
        DerivativesRegime.LEVERAGE_BUILD_NO_DIRECTION: 45.0,
        DerivativesRegime.NEUTRAL: 50.0,
        DerivativesRegime.UNKNOWN: 40.0,
    }
    deriv_score = deriv_map.get(derivatives.regime, 40.0)

    # 5. Participation Quality (0-100)
    vol_z_score = max(0.0, min(100.0, (tf_15m.volume_z + 1.0) * 40.0))
    taker_score = 70.0
    if derivatives.taker_buy_sell_ratio is not None:
        taker_score = max(0.0, min(100.0, derivatives.taker_buy_sell_ratio * 50.0))
    participation_quality = 0.5 * vol_z_score + 0.5 * taker_score

    # 6. Relative Strength (0-100)
    rs_score = relative_perf.score if relative_perf is not None else 50.0

    # 7. Net RR Quality (0-100)
    net_rr_score = max(0.0, min(100.0, (net_rr / config.high_quality_net_rr) * 80.0))

    # Base weighted sum
    weighted_base = (
        rc.weight_trend_quality * trend_quality
        + rc.weight_structure_quality * structure_quality
        + rc.weight_entry_quality * entry_score
        + rc.weight_derivatives_confirmation * deriv_score
        + rc.weight_participation_quality * participation_quality
        + rc.weight_relative_strength * rs_score
        + rc.weight_net_rr * net_rr_score
    )

    # Penalties
    total_penalty = 0.0

    # Crowding penalty
    if derivatives.regime in (DerivativesRegime.LONG_CROWDING, DerivativesRegime.SHORT_CROWDING):
        total_penalty += rc.penalty_crowding

    # Overextension penalty
    if exhaustion.state == ExhaustionState.EXTREME:
        total_penalty += rc.penalty_overextension * 1.5
    elif exhaustion.state == ExhaustionState.ELEVATED:
        total_penalty += rc.penalty_overextension * 0.7

    # Benchmark risk penalty
    if benchmark_context in (BenchmarkContext.MARKET_RISK_OFF, BenchmarkContext.BTC_VOLATILITY_SHOCK):
        total_penalty += rc.penalty_benchmark_risk

    # Low liquidity / wide spread penalty
    if derivatives.spread_bps is not None and derivatives.spread_bps > config.thresholds.max_spread_bps:
        total_penalty += rc.penalty_low_liquidity

    final_score = max(0.0, min(100.0, weighted_base - total_penalty))
    return round(final_score, 2)
