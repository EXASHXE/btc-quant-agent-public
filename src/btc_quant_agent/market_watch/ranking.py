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
    """Compute true multi-timeframe relative strength (15m, 1h, 4h) relative to BTC, ETH, and median."""
    if not snapshots:
        return {}

    rc = config.ranking

    returns_15m = {s: snap.tf_15m.roc for s, snap in snapshots.items()}
    returns_1h = {s: snap.tf_1h.roc for s, snap in snapshots.items()}
    returns_4h = {s: snap.tf_4h.roc for s, snap in snapshots.items()}

    median_15m = statistics.median(returns_15m.values()) if returns_15m else 0.0
    median_1h = statistics.median(returns_1h.values()) if returns_1h else 0.0
    median_4h = statistics.median(returns_4h.values()) if returns_4h else 0.0

    btc_snap = snapshots.get("BTCUSDT")
    eth_snap = snapshots.get("ETHUSDT")

    btc_15m = btc_snap.tf_15m.roc if btc_snap is not None else median_15m
    btc_1h = btc_snap.tf_1h.roc if btc_snap is not None else median_1h
    btc_4h = btc_snap.tf_4h.roc if btc_snap is not None else median_4h

    eth_15m = eth_snap.tf_15m.roc if eth_snap is not None else median_15m
    eth_1h = eth_snap.tf_1h.roc if eth_snap is not None else median_1h
    eth_4h = eth_snap.tf_4h.roc if eth_snap is not None else median_4h

    performances: dict[str, RelativePerformance] = {}
    for symbol, snap in snapshots.items():
        p15m = snap.tf_15m.roc
        p1h = snap.tf_1h.roc
        p4h = snap.tf_4h.roc

        # 15m excess
        ex_15m = (
            rc.rs_weight_btc * (p15m - btc_15m)
            + rc.rs_weight_eth * (p15m - eth_15m)
            + rc.rs_weight_median * (p15m - median_15m)
        )
        # 1h excess
        ex_1h = (
            rc.rs_weight_btc * (p1h - btc_1h)
            + rc.rs_weight_eth * (p1h - eth_1h)
            + rc.rs_weight_median * (p1h - median_1h)
        )
        # 4h excess
        ex_4h = (
            rc.rs_weight_btc * (p4h - btc_4h)
            + rc.rs_weight_eth * (p4h - eth_4h)
            + rc.rs_weight_median * (p4h - median_4h)
        )

        multi_tf_excess = (
            rc.rs_weight_15m * ex_15m
            + rc.rs_weight_1h * ex_1h
            + rc.rs_weight_4h * ex_4h
        )

        raw_score = 50.0 + (multi_tf_excess * 500.0)
        score = max(0.0, min(100.0, raw_score))

        performances[symbol] = RelativePerformance(
            symbol=symbol,
            perf_15m=round(p15m, 4),
            perf_1h=round(p1h, 4),
            perf_4h=round(p4h, 4),
            rel_to_btc_1h=round(p1h - btc_1h, 4),
            rel_to_eth_1h=round(p1h - eth_1h, 4),
            rel_to_median_1h=round(p1h - median_1h, 4),
            score=round(score, 2),
            multi_tf_excess=round(multi_tf_excess, 4),
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
            multi_tf_excess=item.multi_tf_excess,
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
    decision: DirectionalDecision | None = None,
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
    """Calculate transparent multi-factor opportunity score for operational ranking.

    Fully direction-aware:
    - LONG: HH_HL positive, LH_LL negative, HEALTHY_LONG_BUILD positive, HEALTHY_SHORT_BUILD negative, taker buy/sell > 1 positive.
    - SHORT: LH_LL positive, HH_HL negative, HEALTHY_SHORT_BUILD positive, HEALTHY_LONG_BUILD negative, taker buy/sell < 1 positive.
    - WAIT: discounted/capped so it cannot receive an actionable opportunity ranking comparable to LONG/SHORT.
    """
    if has_fatal_veto:
        return 0.0

    if decision is None:
        if str(tf_1h.regime) == "TREND_UP" or tf_1h.structure == "HH_HL":
            eff_decision = DirectionalDecision.LONG
        elif str(tf_1h.regime) == "TREND_DOWN" or tf_1h.structure == "LH_LL":
            eff_decision = DirectionalDecision.SHORT
        else:
            eff_decision = DirectionalDecision.WAIT
    else:
        eff_decision = decision

    rc = config.ranking
    is_long = eff_decision == DirectionalDecision.LONG
    is_short = eff_decision == DirectionalDecision.SHORT
    is_wait = eff_decision == DirectionalDecision.WAIT

    # 1. Trend Quality (0-100)
    adx_score = min(100.0, tf_1h.adx * 2.5)
    if is_long:
        ema_slope_score = 100.0 if (tf_1h.ema_fast_slope > 0 and tf_1h.ema_mid_slope >= 0) else (20.0 if (tf_1h.ema_fast_slope < 0 and tf_1h.ema_mid_slope <= 0) else 45.0)
    elif is_short:
        ema_slope_score = 100.0 if (tf_1h.ema_fast_slope < 0 and tf_1h.ema_mid_slope <= 0) else (20.0 if (tf_1h.ema_fast_slope > 0 and tf_1h.ema_mid_slope >= 0) else 45.0)
    else:
        ema_slope_score = 40.0
    trend_quality = 0.6 * adx_score + 0.4 * ema_slope_score

    # 2. Structure Quality (0-100)
    if is_long:
        if tf_1h.structure == "HH_HL":
            structure_quality = 95.0
        elif tf_1h.structure == "LH_LL":
            structure_quality = 15.0
        elif tf_1h.structure == "UNCONFIRMED":
            structure_quality = 40.0
        else:
            structure_quality = 55.0
    elif is_short:
        if tf_1h.structure == "LH_LL":
            structure_quality = 95.0
        elif tf_1h.structure == "HH_HL":
            structure_quality = 15.0
        elif tf_1h.structure == "UNCONFIRMED":
            structure_quality = 40.0
        else:
            structure_quality = 55.0
    else:
        structure_quality = 35.0

    # 3. Entry Quality (0-100)
    eq_map = {
        EntryQuality.EXCELLENT: 95.0,
        EntryQuality.GOOD: 75.0,
        EntryQuality.MARGINAL: 40.0,
        EntryQuality.POOR: 15.0,
    }
    entry_score = eq_map.get(entry_quality, 20.0)
    if is_wait:
        entry_score = min(entry_score, 25.0)

    # 4. Derivatives Confirmation (0-100)
    if is_long:
        deriv_map = {
            DerivativesRegime.HEALTHY_LONG_BUILD: 95.0,
            DerivativesRegime.SHORT_COVERING: 65.0,
            DerivativesRegime.NEUTRAL: 50.0,
            DerivativesRegime.LEVERAGE_BUILD_NO_DIRECTION: 45.0,
            DerivativesRegime.UNKNOWN: 40.0,
            DerivativesRegime.LONG_LIQUIDATION: 20.0,
            DerivativesRegime.HEALTHY_SHORT_BUILD: 10.0,
            DerivativesRegime.LONG_CROWDING: 15.0,
            DerivativesRegime.SHORT_CROWDING: 55.0,
            DerivativesRegime.DELEVERAGING: 15.0,
        }
    elif is_short:
        deriv_map = {
            DerivativesRegime.HEALTHY_SHORT_BUILD: 95.0,
            DerivativesRegime.LONG_LIQUIDATION: 65.0,
            DerivativesRegime.NEUTRAL: 50.0,
            DerivativesRegime.LEVERAGE_BUILD_NO_DIRECTION: 45.0,
            DerivativesRegime.UNKNOWN: 40.0,
            DerivativesRegime.SHORT_COVERING: 20.0,
            DerivativesRegime.HEALTHY_LONG_BUILD: 10.0,
            DerivativesRegime.SHORT_CROWDING: 15.0,
            DerivativesRegime.LONG_CROWDING: 55.0,
            DerivativesRegime.DELEVERAGING: 15.0,
        }
    else:
        deriv_map = {
            DerivativesRegime.NEUTRAL: 50.0,
            DerivativesRegime.HEALTHY_LONG_BUILD: 40.0,
            DerivativesRegime.HEALTHY_SHORT_BUILD: 40.0,
            DerivativesRegime.SHORT_COVERING: 35.0,
            DerivativesRegime.LONG_LIQUIDATION: 25.0,
            DerivativesRegime.LONG_CROWDING: 20.0,
            DerivativesRegime.SHORT_CROWDING: 20.0,
            DerivativesRegime.DELEVERAGING: 15.0,
            DerivativesRegime.LEVERAGE_BUILD_NO_DIRECTION: 35.0,
            DerivativesRegime.UNKNOWN: 30.0,
        }
    deriv_score = deriv_map.get(derivatives.regime, 40.0)

    # 5. Participation Quality (0-100)
    vol_z_score = max(0.0, min(100.0, (tf_15m.volume_z + 1.0) * 40.0))
    taker_ratio = derivatives.taker_buy_sell_ratio
    if taker_ratio is not None:
        if is_long:
            taker_score = max(0.0, min(100.0, taker_ratio * 50.0))
        elif is_short:
            taker_score = max(0.0, min(100.0, (2.0 - taker_ratio) * 50.0))
        else:
            taker_score = 50.0
    else:
        taker_score = 50.0
    participation_quality = 0.5 * vol_z_score + 0.5 * taker_score

    # 6. Relative Strength (0-100)
    if relative_perf is not None:
        if is_long:
            rs_score = relative_perf.score
        elif is_short:
            rs_score = 100.0 - relative_perf.score
        else:
            rs_score = 40.0
    else:
        rs_score = 50.0

    # 7. Net RR Quality (0-100)
    if is_wait or net_rr <= 0:
        net_rr_score = 0.0
    else:
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
    if is_long and derivatives.regime == DerivativesRegime.LONG_CROWDING or is_short and derivatives.regime == DerivativesRegime.SHORT_CROWDING:
        total_penalty += rc.penalty_crowding

    if exhaustion.state == ExhaustionState.EXTREME:
        if is_long and exhaustion.distance_from_ema20_atr > 0 or is_short and exhaustion.distance_from_ema20_atr < 0:
            total_penalty += rc.penalty_overextension * 1.5
        elif is_wait:
            total_penalty += rc.penalty_overextension
    elif exhaustion.state == ExhaustionState.ELEVATED:
        total_penalty += rc.penalty_overextension * 0.7

    if is_long and benchmark_context in (
        BenchmarkContext.MARKET_RISK_OFF,
        BenchmarkContext.BTC_VOLATILITY_SHOCK,
    ):
        total_penalty += rc.penalty_benchmark_risk

    if derivatives.spread_bps is not None and derivatives.spread_bps > config.thresholds.max_spread_bps:
        total_penalty += rc.penalty_low_liquidity

    score = max(0.0, min(100.0, weighted_base - total_penalty))

    if is_wait:
        score = min(25.0, score * 0.4)

    return round(score, 2)
