from __future__ import annotations

import statistics
from typing import Any

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
from .evidence import RuleScoreBreakdown


def compute_relative_performances(
    snapshots: dict[str, MarketSnapshot],
    config: MarketWatchConfig,
) -> dict[str, RelativePerformance]:
    """Compute true multi-timeframe relative strength (1h, 4h, 12h) relative to BTC, ETH, and cross-sectional median.

    Frozen B0 semantics:
    - Target horizons: 1h, 4h, 12h.
    - Expected reference universe from config.relative_strength_universe.
    - If ANY expected member is missing or incomplete:
        universe_status = UNIVERSE_DEGRADED
        cross-sectional median component = UNAVAILABLE / NEUTRAL (contribution = 0)
        remaining weights NOT renormalized
        relative cross-sectional rank UNAVAILABLE (rank = 0)
    - BTC and ETH benchmark components continue independently if their own source data is available.
    - If BTC or ETH is missing, that component is neutral (contribution = 0). Never substitute median.
    """
    if not snapshots:
        return {}

    rc = config.ranking
    expected_members = tuple(config.relative_strength_universe)
    available_members = tuple(s for s in expected_members if s in snapshots)
    missing_members = tuple(s for s in expected_members if s not in snapshots)

    is_degraded = len(missing_members) > 0
    universe_status = "UNIVERSE_DEGRADED" if is_degraded else "UNIVERSE_COMPLETE"

    def get_returns(snap: Any) -> tuple[float | None, float | None, float | None]:
        # Authoritative B0 returns: return_1h, return_4h, return_12h (strictly no ROC fallback)
        r1h = float(snap.return_1h) if isinstance(getattr(snap, "return_1h", None), (int, float)) else None
        r4h = float(snap.return_4h) if isinstance(getattr(snap, "return_4h", None), (int, float)) else None
        r12h = float(snap.return_12h) if isinstance(getattr(snap, "return_12h", None), (int, float)) else None
        return r1h, r4h, r12h

    # Extract returns for all snapshots
    snap_returns: dict[str, tuple[float | None, float | None, float | None]] = {
        s: get_returns(snap) for s, snap in snapshots.items()
    }

    expected_members = tuple(config.relative_strength_universe)
    missing_members = tuple(s for s in expected_members if s not in snapshots)
    incomplete_return_members = tuple(
        s for s in expected_members
        if s in snapshots and (
            snap_returns[s][0] is None or snap_returns[s][1] is None or snap_returns[s][2] is None
        )
    )

    is_degraded = (len(missing_members) > 0) or (len(incomplete_return_members) > 0)
    universe_status = "UNIVERSE_DEGRADED" if is_degraded else "UNIVERSE_COMPLETE"
    available_members = tuple(s for s in expected_members if s in snapshots and s not in incomplete_return_members)

    # BTC / ETH benchmark returns (independent, never substituted by median)
    btc_r = snap_returns.get("BTCUSDT")
    eth_r = snap_returns.get("ETHUSDT")

    btc_1h = btc_r[0] if btc_r is not None else None
    btc_4h = btc_r[1] if btc_r is not None else None
    btc_12h = btc_r[2] if btc_r is not None else None

    eth_1h = eth_r[0] if eth_r is not None else None
    eth_4h = eth_r[1] if eth_r is not None else None
    eth_12h = eth_r[2] if eth_r is not None else None

    # Cross-sectional medians over expected reference universe ONLY if UNIVERSE_COMPLETE
    if not is_degraded:
        all_1h: list[float] = [r for s in expected_members if (r := snap_returns[s][0]) is not None]
        all_4h: list[float] = [r for s in expected_members if (r := snap_returns[s][1]) is not None]
        all_12h: list[float] = [r for s in expected_members if (r := snap_returns[s][2]) is not None]

        median_1h = statistics.median(all_1h) if len(all_1h) == len(expected_members) else None
        median_4h = statistics.median(all_4h) if len(all_4h) == len(expected_members) else None
        median_12h = statistics.median(all_12h) if len(all_12h) == len(expected_members) else None
        if median_1h is None or median_4h is None or median_12h is None:
            is_degraded = True
            universe_status = "UNIVERSE_DEGRADED"
    else:
        median_1h = None
        median_4h = None
        median_12h = None

    performances: dict[str, RelativePerformance] = {}
    for symbol, (p1h, p4h, p12h) in snap_returns.items():
        # 1h excess
        c_btc_1h = rc.rs_weight_btc * (p1h - btc_1h) if (p1h is not None and btc_1h is not None) else 0.0
        c_eth_1h = rc.rs_weight_eth * (p1h - eth_1h) if (p1h is not None and eth_1h is not None) else 0.0
        c_med_1h = rc.rs_weight_median * (p1h - median_1h) if (p1h is not None and median_1h is not None) else 0.0
        ex_1h = c_btc_1h + c_eth_1h + c_med_1h

        # 4h excess
        c_btc_4h = rc.rs_weight_btc * (p4h - btc_4h) if (p4h is not None and btc_4h is not None) else 0.0
        c_eth_4h = rc.rs_weight_eth * (p4h - eth_4h) if (p4h is not None and eth_4h is not None) else 0.0
        c_med_4h = rc.rs_weight_median * (p4h - median_4h) if (p4h is not None and median_4h is not None) else 0.0
        ex_4h = c_btc_4h + c_eth_4h + c_med_4h

        # 12h excess
        c_btc_12h = rc.rs_weight_btc * (p12h - btc_12h) if (p12h is not None and btc_12h is not None) else 0.0
        c_eth_12h = rc.rs_weight_eth * (p12h - eth_12h) if (p12h is not None and eth_12h is not None) else 0.0
        c_med_12h = rc.rs_weight_median * (p12h - median_12h) if (p12h is not None and median_12h is not None) else 0.0
        ex_12h = c_btc_12h + c_eth_12h + c_med_12h

        multi_tf_excess = (
            rc.rs_weight_1h * ex_1h
            + rc.rs_weight_4h * ex_4h
            + rc.rs_weight_12h * ex_12h
        )

        raw_score = 50.0 + (multi_tf_excess * 500.0)
        score = max(0.0, min(100.0, raw_score))

        performances[symbol] = RelativePerformance(
            symbol=symbol,
            perf_1h=round(p1h, 4) if p1h is not None else None,
            perf_4h=round(p4h, 4) if p4h is not None else None,
            perf_12h=round(p12h, 4) if p12h is not None else None,
            rel_to_btc_1h=round(p1h - btc_1h, 4) if (p1h is not None and btc_1h is not None) else None,
            rel_to_eth_1h=round(p1h - eth_1h, 4) if (p1h is not None and eth_1h is not None) else None,
            rel_to_median_1h=round(p1h - median_1h, 4) if (p1h is not None and median_1h is not None) else None,
            score=round(score, 2),
            multi_tf_excess=round(multi_tf_excess, 4),
            rank=0,  # default unranked / unavailable
            perf_15m=None,
            universe_status=universe_status,
            missing_members=missing_members,
            incomplete_return_members=incomplete_return_members,
            expected_members=expected_members,
            available_members=available_members,
        )

    # Assign ranks based on score ONLY if UNIVERSE_COMPLETE
    if not is_degraded:
        sorted_symbols = sorted(performances.keys(), key=lambda s: performances[s].score, reverse=True)
        ranked: dict[str, RelativePerformance] = {}
        for rank_idx, s in enumerate(sorted_symbols, 1):
            item = performances[s]
            ranked[s] = RelativePerformance(
                symbol=item.symbol,
                perf_1h=item.perf_1h,
                perf_4h=item.perf_4h,
                perf_12h=item.perf_12h,
                rel_to_btc_1h=item.rel_to_btc_1h,
                rel_to_eth_1h=item.rel_to_eth_1h,
                rel_to_median_1h=item.rel_to_median_1h,
                score=item.score,
                multi_tf_excess=item.multi_tf_excess,
                rank=rank_idx,
                perf_15m=None,
                universe_status=item.universe_status,
                missing_members=item.missing_members,
                incomplete_return_members=item.incomplete_return_members,
                expected_members=item.expected_members,
                available_members=item.available_members,
            )
        return ranked

    return performances


def check_fatal_vetoes(
    *,
    decision: DirectionalDecision,
    exhaustion: ExhaustionMetrics,
    net_rr: float,
    tf_4h: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    benchmark_context: BenchmarkContext,
    config: MarketWatchConfig,
    trend_evidence: Any | None = None,
    enforce_promoted_evidence: bool = False,
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

        # Fatal Veto 5: Promoted Trend & Structure Evidence (TACTICAL_POLICY_R2_B1)
        if config.thresholds.enable_promoted_trend_filter and (enforce_promoted_evidence or trend_evidence is not None):
            if trend_evidence is None:
                vetoes.append("VETO_PROMOTED_TREND_EVIDENCE_MISSING")
            else:
                trans = getattr(trend_evidence, "structure_transition", None)
                if trans in config.thresholds.disallowed_structure_transitions:
                    vetoes.append("VETO_UNCONFIRMED_STRUCTURE_TRANSITION")
                pers = getattr(trend_evidence, "trend_persistence", None)
                if pers is None or pers < config.thresholds.min_trend_persistence:
                    vetoes.append("VETO_INSUFFICIENT_TREND_PERSISTENCE")

    # Fatal Veto 4: Excessive spread
    if derivatives.spread_bps is not None and derivatives.spread_bps > config.thresholds.max_spread_bps * 1.5:
        vetoes.append("FATAL_VETO_EXCESSIVE_SPREAD")

    return (len(vetoes) > 0), tuple(vetoes)


def calculate_rule_score_breakdown(
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
) -> RuleScoreBreakdown:
    """Calculate transparent multi-factor Rule Score (RULE_SCORE_V1) breakdown for operational ranking.

    CRITICAL SEMANTIC BOUNDARY:
    - RULE_SCORE_V1 != P(win)
    - RULE_SCORE_V1 != calibrated confidence
    - RULE_SCORE_V1 != expected return
    - RULE_SCORE_V1 != probability of fill
    - RULE_SCORE_V1 != validated alpha
    It is a deterministic rule quality heuristic.

    Fully direction-aware:
    - LONG: HH_HL positive, LH_LL negative, HEALTHY_LONG_BUILD positive, HEALTHY_SHORT_BUILD negative, taker buy/sell > 1 positive.
    - SHORT: LH_LL positive, HH_HL negative, HEALTHY_SHORT_BUILD positive, HEALTHY_LONG_BUILD negative, taker buy/sell < 1 positive.
    - WAIT: discounted/capped so it cannot receive an actionable opportunity ranking comparable to LONG/SHORT.
    """
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
    crowding_penalty = 0.0
    if (is_long and derivatives.regime == DerivativesRegime.LONG_CROWDING) or (
        is_short and derivatives.regime == DerivativesRegime.SHORT_CROWDING
    ):
        crowding_penalty = rc.penalty_crowding

    overextension_penalty = 0.0
    if exhaustion.state == ExhaustionState.EXTREME:
        if (is_long and exhaustion.distance_from_ema20_atr > 0) or (
            is_short and exhaustion.distance_from_ema20_atr < 0
        ):
            overextension_penalty = rc.penalty_overextension * 1.5
        elif is_wait:
            overextension_penalty = rc.penalty_overextension
    elif exhaustion.state == ExhaustionState.ELEVATED:
        overextension_penalty = rc.penalty_overextension * 0.7

    benchmark_penalty = 0.0
    if is_long and benchmark_context in (
        BenchmarkContext.MARKET_RISK_OFF,
        BenchmarkContext.BTC_VOLATILITY_SHOCK,
    ):
        benchmark_penalty = rc.penalty_benchmark_risk

    low_liquidity_penalty = 0.0
    if derivatives.spread_bps is not None and derivatives.spread_bps > config.thresholds.max_spread_bps:
        low_liquidity_penalty = rc.penalty_low_liquidity

    total_penalty = crowding_penalty + overextension_penalty + benchmark_penalty + low_liquidity_penalty
    pre_wait_adjustment_score = max(0.0, min(100.0, weighted_base - total_penalty))

    wait_adjustment_applied = bool(is_wait)
    score = pre_wait_adjustment_score
    if wait_adjustment_applied:
        score = min(25.0, score * 0.4)

    final_rule_score = 0.0 if has_fatal_veto else round(score, 2)

    return RuleScoreBreakdown(
        effective_direction=eff_decision.value,
        adx_score=round(adx_score, 4),
        ema_slope_score=round(ema_slope_score, 4),
        trend_quality=round(trend_quality, 4),
        structure_quality=round(structure_quality, 4),
        entry_quality_score=round(entry_score, 4),
        derivatives_confirmation_score=round(deriv_score, 4),
        volume_z_score=round(vol_z_score, 4),
        taker_score=round(taker_score, 4),
        participation_quality=round(participation_quality, 4),
        relative_strength_score=round(rs_score, 4),
        net_rr_score=round(net_rr_score, 4),
        weighted_base=round(weighted_base, 4),
        crowding_penalty=round(crowding_penalty, 4),
        overextension_penalty=round(overextension_penalty, 4),
        benchmark_penalty=round(benchmark_penalty, 4),
        low_liquidity_penalty=round(low_liquidity_penalty, 4),
        total_penalty=round(total_penalty, 4),
        pre_wait_adjustment_score=round(pre_wait_adjustment_score, 4),
        wait_adjustment_applied=wait_adjustment_applied,
        final_rule_score=final_rule_score,
    )


def calculate_rule_score(
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
    """Calculate transparent multi-factor Rule Score (RULE_SCORE_V1) for operational ranking.

    CRITICAL SEMANTIC BOUNDARY:
    - RULE_SCORE_V1 != P(win)
    - RULE_SCORE_V1 != calibrated confidence
    - RULE_SCORE_V1 != expected return
    - RULE_SCORE_V1 != probability of fill
    - RULE_SCORE_V1 != validated alpha
    It is a deterministic rule quality heuristic.

    Fully direction-aware:
    - LONG: HH_HL positive, LH_LL negative, HEALTHY_LONG_BUILD positive, HEALTHY_SHORT_BUILD negative, taker buy/sell > 1 positive.
    - SHORT: LH_LL positive, HH_HL negative, HEALTHY_SHORT_BUILD positive, HEALTHY_LONG_BUILD negative, taker buy/sell < 1 positive.
    - WAIT: discounted/capped so it cannot receive an actionable opportunity ranking comparable to LONG/SHORT.
    """
    return calculate_rule_score_breakdown(
        decision=decision,
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        entry_quality=entry_quality,
        derivatives=derivatives,
        exhaustion=exhaustion,
        relative_perf=relative_perf,
        benchmark_context=benchmark_context,
        net_rr=net_rr,
        has_fatal_veto=has_fatal_veto,
        config=config,
    ).final_rule_score


# Deprecated backward compatibility alias
calculate_opportunity_score = calculate_rule_score
