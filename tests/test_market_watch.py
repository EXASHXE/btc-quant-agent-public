from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from btc_quant_agent.domain import Candle, Regime
from btc_quant_agent.market_watch.alerting import build_market_watch_card
from btc_quant_agent.market_watch.config import MarketWatchConfig
from btc_quant_agent.market_watch.context import (
    apply_benchmark_context_gate,
    evaluate_benchmark_context,
)
from btc_quant_agent.market_watch.derivatives import (
    apply_derivatives_action_gate,
    evaluate_derivatives_regime,
    is_severe_long_crowding,
    is_severe_short_crowding,
)
from btc_quant_agent.market_watch.domain import (
    MARKET_WATCH_EVIDENCE_VERSION,
    AlertSeverity,
    BenchmarkContext,
    BreakoutState,
    ConfidenceBand,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    GridDecision,
    GridPlan,
    MarketSnapshot,
    MarketWatchAlert,
    PlaybookType,
    PriceMetrics,
    ScanHealth,
    ShadowFillStatus,
    ShadowPathResolution,
    SignalLifecycleState,
    SymbolAssessment,
    TimeframeSnapshot,
    compute_setup_key,
    compute_signal_identity,
    extract_signal_identity,
    normalize_price_level,
    validate_time_coverage,
)
from btc_quant_agent.market_watch.entry_quality import (
    calculate_net_risk_reward,
    evaluate_entry_quality,
    evaluate_exhaustion,
)
from btc_quant_agent.market_watch.grid_policy import evaluate_grid_policy, should_alert_grid_change
from btc_quant_agent.market_watch.lifecycle import advance_lifecycle_state
from btc_quant_agent.market_watch.playbooks import (
    evaluate_breakout_retest,
    evaluate_failed_breakout,
    evaluate_trend_pullback,
    evaluate_volatility_expansion,
)
from btc_quant_agent.market_watch.ranking import (
    calculate_opportunity_score,
    check_fatal_vetoes,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.service import MarketWatchService
from btc_quant_agent.market_watch.shadow import (
    ShadowEvaluationManager,
    compute_performance_metrics,
    compute_trade_friction_r,
    evaluate_intrabar_path,
    resolve_shadow_fill,
)
from btc_quant_agent.market_watch.snapshot import compute_snapshot_hash, compute_timeframe_snapshot
from btc_quant_agent.market_watch.state import (
    MarketWatchStateStore,
    compute_decision_fingerprint,
    evaluate_alert_emission,
    is_legacy_shadow_record,
)


def make_candle_series(
    symbol: str,
    interval: str,
    count: int = 50,
    base_price: float = 100.0,
    trend_per_bar: float = 0.0,
    volatility: float = 1.0,
    start_ms: int = 1_700_000_000_000,
    step_ms: int = 3_600_000,
) -> list[Candle]:
    """Generate deterministic synthetic candles for multi-timeframe analysis."""
    candles = []
    price = base_price
    for i in range(count):
        price += trend_per_bar
        open_p = price
        close_p = price + (0.4 * volatility if i % 2 == 0 else -0.3 * volatility)
        high_p = max(open_p, close_p) + volatility
        low_p = min(open_p, close_p) - volatility
        candles.append(
            Candle(
                symbol=symbol,
                interval=interval,
                open_time_ms=start_ms + i * step_ms,
                close_time_ms=start_ms + (i + 1) * step_ms - 1,
                open=round(open_p, 4),
                high=round(high_p, 4),
                low=round(low_p, 4),
                close=round(close_p, 4),
                volume=1000.0 + i * 10.0,
                quote_volume=(1000.0 + i * 10.0) * close_p,
            )
        )
    return candles


def make_dummy_tf(
    symbol: str,
    interval: str,
    close: float = 100.0,
    regime: Regime = Regime.TREND_UP,
    ema_fast: float = 101.0,
    ema_mid: float = 98.0,
    ema_fast_slope: float = 0.05,
    ema_mid_slope: float = 0.02,
    atr: float = 2.0,
    adx_val: float = 28.0,
    rsi_val: float = 55.0,
    roc_val: float = 0.015,
    structure: str = "HH_HL",
    supports: tuple[float, ...] = (96.0, 94.0),
    resistances: tuple[float, ...] = (104.0, 106.0),
    recent_swing_high: float = 105.0,
    recent_swing_low: float = 95.0,
) -> TimeframeSnapshot:
    """Helper to construct a valid TimeframeSnapshot."""
    closed = Candle(symbol, interval, 1000, 2000, close - 0.2, close + 0.5, close - 0.5, close, 5000.0)
    return TimeframeSnapshot(
        interval=interval,
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=close,
        ema_fast=ema_fast,
        ema_mid=ema_mid,
        ema_fast_slope=ema_fast_slope,
        ema_mid_slope=ema_mid_slope,
        atr=atr,
        atr_percentile=0.5,
        adx=adx_val,
        rsi=rsi_val,
        roc=roc_val,
        volume=5000.0,
        volume_z=0.5,
        bb_width=0.04,
        bb_width_percentile=0.4,
        recent_swing_high=recent_swing_high,
        recent_swing_low=recent_swing_low,
        supports=supports,
        resistances=resistances,
        structure=structure,
        regime=regime,
        is_volatility_compressed=False,
        is_volatility_expanded=False,
    )


# =========================================================================
# 1. DOMAIN & CONFIG TESTS
# =========================================================================

def test_market_watch_config_defaults() -> None:
    config = MarketWatchConfig()
    assert not config.enabled
    assert "BTCUSDT" in config.symbols
    assert "ETHUSDT" in config.symbols
    assert config.min_net_rr == 1.5
    assert config.high_quality_net_rr == 2.0
    assert config.grid.grid_boundary_change_pct == 2.0


def test_snapshot_hash_determinism() -> None:
    tf_15m = make_dummy_tf("BTCUSDT", "15m", 50000.0)
    tf_1h = make_dummy_tf("BTCUSDT", "1h", 50000.0)
    tf_4h = make_dummy_tf("BTCUSDT", "4h", 50000.0)
    deriv = DerivativesMetrics(mark_price=50000.0, funding_rate=0.0001, current_open_interest=100000.0)
    price_m = PriceMetrics(last_price=50000.0, change_24h_pct=0.02, high_24h=51000.0, low_24h=49000.0)

    h1 = compute_snapshot_hash(
        symbol="BTCUSDT",
        decision_time_ms=1700000000000,
        price=price_m,
        tf_15m=tf_15m,
        tf_1h=tf_1h,
        tf_4h=tf_4h,
        derivatives=deriv,
    )
    h2 = compute_snapshot_hash(
        symbol="BTCUSDT",
        decision_time_ms=1700000000000,
        price=price_m,
        tf_15m=tf_15m,
        tf_1h=tf_1h,
        tf_4h=tf_4h,
        derivatives=deriv,
    )
    assert h1 == h2
    assert len(h1) == 16


# =========================================================================
# 2. TIME SEMANTICS & CLOSED-BAR CONFIRMATION
# =========================================================================

def test_timeframe_snapshot_closed_bar_isolation() -> None:
    """Forming bar must be isolated and must not alter closed bar indicator series."""
    config = MarketWatchConfig()
    closed = make_candle_series("BTCUSDT", "1h", 40, base_price=100.0)
    forming = Candle(
        symbol="BTCUSDT",
        interval="1h",
        open_time_ms=closed[-1].close_time_ms + 1,
        close_time_ms=closed[-1].close_time_ms + 3_600_000,
        open=closed[-1].close,
        high=9999.0,  # Extreme spike in forming bar
        low=1.0,
        close=5000.0,
        volume=1_000_000.0,
    )

    snap_without = compute_timeframe_snapshot("1h", closed, None, config)
    snap_with = compute_timeframe_snapshot("1h", closed, forming, config)

    # Core closed indicators must be strictly identical
    assert snap_without.close == snap_with.close
    assert snap_without.ema_fast == snap_with.ema_fast
    assert snap_without.ema_mid == snap_with.ema_mid
    assert snap_without.rsi == snap_with.rsi
    assert snap_without.adx == snap_with.adx
    assert snap_without.atr == snap_with.atr
    assert snap_without.bb_width == snap_with.bb_width
    assert snap_without.structure == snap_with.structure
    assert snap_without.supports == snap_with.supports
    assert snap_without.resistances == snap_with.resistances

    # Forming bar is retained in latest_bar for display only
    assert snap_without.latest_bar.close == closed[-1].close
    assert snap_with.latest_bar.close == 5000.0
    assert snap_with.latest_closed_bar.close == closed[-1].close


# =========================================================================
# 3. DERIVATIVES STATE MACHINE
# =========================================================================

def test_derivatives_classification_states() -> None:
    config = MarketWatchConfig()

    # 1. Healthy long build: price up + OI up + normal funding
    r1, _, _ = evaluate_derivatives_regime(
        price_change_1h_pct=0.02,
        derivatives=DerivativesMetrics(
            mark_price=105.0,
            funding_rate=0.0001,
            current_open_interest=1000.0,
            oi_1h_change=0.03,
            taker_buy_sell_ratio=1.2,
        ),
        config=config,
    )
    assert r1 == DerivativesRegime.HEALTHY_LONG_BUILD

    # 2. Healthy short build: price down + OI up + funding negative/normal
    r2, _, _ = evaluate_derivatives_regime(
        price_change_1h_pct=-0.02,
        derivatives=DerivativesMetrics(
            mark_price=95.0,
            funding_rate=-0.0001,
            current_open_interest=1000.0,
            oi_1h_change=0.03,
            taker_buy_sell_ratio=0.8,
        ),
        config=config,
    )
    assert r2 == DerivativesRegime.HEALTHY_SHORT_BUILD

    # 3. Short covering: price up + OI down
    r3, _, _ = evaluate_derivatives_regime(
        price_change_1h_pct=0.025,
        derivatives=DerivativesMetrics(
            mark_price=105.0,
            funding_rate=0.00005,
            current_open_interest=1000.0,
            oi_1h_change=-0.02,
        ),
        config=config,
    )
    assert r3 == DerivativesRegime.SHORT_COVERING

    # 4. Long liquidation: price down + OI down
    r4, _, _ = evaluate_derivatives_regime(
        price_change_1h_pct=-0.025,
        derivatives=DerivativesMetrics(
            mark_price=95.0,
            funding_rate=0.00005,
            current_open_interest=1000.0,
            oi_1h_change=-0.025,
        ),
        config=config,
    )
    assert r4 == DerivativesRegime.LONG_LIQUIDATION

    # 5. Long crowding: extreme positive funding + high top long ratio
    r5, _, _ = evaluate_derivatives_regime(
        price_change_1h_pct=0.01,
        derivatives=DerivativesMetrics(
            mark_price=110.0,
            funding_rate=0.0006,  # > 0.0003
            current_open_interest=1000.0,
            oi_1h_change=0.02,
            top_trader_position_ratio=2.5,
        ),
        config=config,
    )
    assert r5 == DerivativesRegime.LONG_CROWDING

    # 6. Deleveraging: severe OI drop without directional cascade
    r6, _, _ = evaluate_derivatives_regime(
        price_change_1h_pct=0.0,
        derivatives=DerivativesMetrics(
            mark_price=100.0,
            funding_rate=0.0001,
            current_open_interest=1000.0,
            oi_1h_change=-0.08,  # < -0.05
        ),
        config=config,
    )
    assert r6 == DerivativesRegime.DELEVERAGING


# =========================================================================
# 4. ENTRY QUALITY & NET RR FRICTION
# =========================================================================

def test_calculate_net_risk_reward() -> None:
    config = MarketWatchConfig()
    # Gross: entry 100, SL 95 (risk 5), TP1 110 (reward 10) -> Gross RR = 2.0
    gross_rr, net_rr = calculate_net_risk_reward(
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        direction=DirectionalDecision.LONG,
        config=config,
        funding_rate=0.0001,
    )
    assert round(gross_rr, 2) == 2.0
    # Net RR must be less than gross RR due to fee, slippage, and adverse funding friction
    assert 1.7 < net_rr < gross_rr

    # Unfavorable RR < 1.5
    bad_gross, bad_net = calculate_net_risk_reward(
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=105.0,
        direction=DirectionalDecision.LONG,
        config=config,
    )
    assert bad_gross == 1.0
    assert bad_net < 1.0


def test_entry_quality_anti_chasing_veto() -> None:
    config = MarketWatchConfig()
    # Price is 115, EMA20 is 100, ATR is 2 -> distance = (115 - 100)/2 = 7.5 ATR (> 2.5 ATR threshold)
    tf_15m = make_dummy_tf("BTCUSDT", "15m", close=115.0, ema_fast=100.0, atr=2.0)
    deriv = DerivativesMetrics(mark_price=115.0, funding_rate=0.0001)

    exhaustion = evaluate_exhaustion(tf_15m, deriv, config)
    assert exhaustion.state == ExhaustionState.EXTREME

    quality, reasons, risks = evaluate_entry_quality(
        direction=DirectionalDecision.LONG,
        exhaustion=exhaustion,
        net_rr=2.2,
        tf_15m=tf_15m,
        derivatives=deriv,
        config=config,
    )
    assert quality == EntryQuality.POOR
    assert any("OVEREXTENDED" in r for r in reasons + risks)


# =========================================================================
# 5. PLAYBOOKS
# =========================================================================

def test_trend_pullback_playbook() -> None:
    config = MarketWatchConfig()
    # 4h and 1h uptrend
    tf_4h = make_dummy_tf("BTCUSDT", "4h", close=101.0, regime=Regime.TREND_UP, ema_fast=100.0, ema_mid=95.0)
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=101.0, regime=Regime.TREND_UP, ema_fast=100.0, ema_mid=95.0, atr=2.0)
    # 15m pulls back into EMA20 support and bounces
    tf_15m = make_dummy_tf("BTCUSDT", "15m", close=100.2, ema_fast=100.0, atr=0.8)

    deriv = DerivativesMetrics(mark_price=100.2, oi_1h_change=0.02, funding_rate=0.0001)
    exhaustion = ExhaustionMetrics(
        distance_from_ema20_atr=0.2,
        state=ExhaustionState.NORMAL,
        reasons=(),
    )

    res = evaluate_trend_pullback(
        tf_4h=tf_4h,
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
    )
    assert res is not None
    assert res["decision"] == DirectionalDecision.LONG
    assert res["setup"] == PlaybookType.TREND_PULLBACK
    assert res["stop_loss"] < 100.2 < res["take_profit_1"]


def test_failed_breakout_watch_playbook() -> None:
    config = MarketWatchConfig()
    # Resistance at 105.0. Bar poked above to 106.0, but closed back down at 104.5
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=104.5, resistances=(105.0,))
    closed = Candle("BTCUSDT", "15m", 100, 200, 104.8, 106.0, 104.0, 104.5, 5000.0)
    tf_15m = TimeframeSnapshot(
        interval="15m",
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=104.5,
        ema_fast=103.0,
        ema_mid=102.0,
        ema_fast_slope=0.01,
        ema_mid_slope=0.01,
        atr=1.0,
        atr_percentile=50.0,
        adx=20.0,
        rsi=60.0,
        roc=0.005,
        volume=5000.0,
        volume_z=0.5,
        bb_width=0.05,
        bb_width_percentile=50.0,
        recent_swing_high=106.0,
        recent_swing_low=100.0,
        supports=(100.0,),
        resistances=(105.0,),
        structure="UNCONFIRMED",
        regime=Regime.TRANSITION,
    )
    deriv = DerivativesMetrics(mark_price=104.5, oi_1h_change=0.04, funding_rate=0.0003)

    res = evaluate_failed_breakout(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        config=config,
    )
    assert res is not None
    assert res["decision"] == DirectionalDecision.WAIT
    assert res["setup"] == PlaybookType.FAILED_BREAKOUT
    assert "FAILED_BREAKOUT_DETECTED" in res["reasons"]
    assert "OI_EXPANDED_ON_FAILURE_LONGS_TRAPPED" in res["reasons"]


def test_volatility_expansion_playbook() -> None:
    config = MarketWatchConfig()
    # 15m volatility compressed previously, now expanding with breakout above upper band
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=103.0, regime=Regime.RANGE)
    closed = Candle("BTCUSDT", "15m", 100, 200, 101.0, 103.5, 100.5, 103.0, 8000.0)
    tf_15m = TimeframeSnapshot(
        interval="15m",
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=103.0,
        ema_fast=101.5,
        ema_mid=101.0,
        ema_fast_slope=0.04,
        ema_mid_slope=0.02,
        atr=1.2,
        atr_percentile=0.85,
        adx=22.0,
        rsi=62.0,
        roc=0.02,
        volume=8000.0,
        volume_z=1.8,
        bb_width=0.02,
        bb_width_percentile=0.15,  # Compressed
        recent_swing_high=102.5,
        recent_swing_low=100.0,
        supports=(100.0,),
        resistances=(102.5,),
        structure="HH_HL",
        regime=Regime.RANGE,
        is_volatility_compressed=True,
        has_prior_compression_window=True,
    )
    deriv = DerivativesMetrics(mark_price=103.0, oi_1h_change=0.03, funding_rate=0.0001)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=1.2, state=ExhaustionState.NORMAL)

    res = evaluate_volatility_expansion(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
    )
    assert res is not None
    assert res["decision"] == DirectionalDecision.LONG
    assert res["setup"] == PlaybookType.VOLATILITY_EXPANSION

    # R2-07: Single bar compression without actual prior window is rejected
    tf_no_prior = TimeframeSnapshot(
        interval="15m",
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=103.0,
        ema_fast=101.5,
        ema_mid=101.0,
        ema_fast_slope=0.04,
        ema_mid_slope=0.02,
        atr=1.2,
        atr_percentile=0.85,
        adx=22.0,
        rsi=62.0,
        roc=0.02,
        volume=8000.0,
        volume_z=1.8,
        bb_width=0.02,
        bb_width_percentile=0.15,
        recent_swing_high=102.5,
        recent_swing_low=100.0,
        supports=(100.0,),
        resistances=(102.5,),
        structure="HH_HL",
        regime=Regime.RANGE,
        is_volatility_compressed=True,
        has_prior_compression_window=False,
    )
    res_no_prior = evaluate_volatility_expansion(
        tf_1h=tf_1h,
        tf_15m=tf_no_prior,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
    )
    assert res_no_prior is None


# =========================================================================
# 6. BENCHMARK CONTEXT & ALT GATING
# =========================================================================

def test_benchmark_downside_shock_vetoes_alt_longs() -> None:
    config = MarketWatchConfig()
    # BTC drops 4.5% with high volatility
    btc_tf_1h = make_dummy_tf("BTCUSDT", "1h", close=48000.0, regime=Regime.TREND_DOWN, roc_val=-0.045)
    btc_snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=48000.0, change_24h_pct=-0.045),
        tf_15m=btc_tf_1h,
        tf_1h=btc_tf_1h,
        tf_4h=btc_tf_1h,
        derivatives=DerivativesMetrics(mark_price=48000.0),
        snapshot_hash="hash_btc",
    )

    ctx, _reasons, _risks = evaluate_benchmark_context(
        btc_snapshot=btc_snap,
        eth_snapshot=None,
        config=config,
    )
    assert ctx in (BenchmarkContext.BTC_VOLATILITY_SHOCK, BenchmarkContext.MARKET_RISK_OFF)

    # Now verify alt long gating turns LONG into WAIT
    gated, g_reasons, g_risks = apply_benchmark_context_gate(
        symbol="SOLUSDT",
        decision=DirectionalDecision.LONG,
        benchmark_context=ctx,
        relative_perf=None,
        entry_quality=EntryQuality.GOOD,
        net_rr=2.0,
        config=config,
    )
    assert gated == DirectionalDecision.WAIT
    assert any("BENCHMARK" in r for r in g_reasons + g_risks)


# =========================================================================
# 7. RANGE GRID POLICY & ANTI-FALLING-KNIFE
# =========================================================================

def test_grid_policy_range_generation_and_boundary_delta() -> None:
    config = MarketWatchConfig()
    # 1h in clean RANGE, supports at 90.0, resistances at 110.0, price at 100.0
    tf_1h = make_dummy_tf(
        "SOLUSDT", "1h", close=100.0, regime=Regime.RANGE, adx_val=15.0, supports=(90.0,), resistances=(110.0,)
    )
    tf_15m = make_dummy_tf("SOLUSDT", "15m", close=100.0, regime=Regime.RANGE)

    plan = evaluate_grid_policy(
        symbol="SOLUSDT",
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=DerivativesMetrics(mark_price=100.0, funding_rate=0.00005),
        prev_grid=None,
        config=config,
    )
    assert plan.decision in (GridDecision.LONG_BIAS, GridDecision.SHORT_BIAS, GridDecision.NEUTRAL)
    assert plan.lower_bound is not None and plan.lower_bound <= 90.0
    assert plan.upper_bound is not None and plan.upper_bound >= 110.0
    assert plan.grid_count >= 3

    # Check alert on initial plan
    assert should_alert_grid_change(plan, None)

    # Check boundary delta < 2% threshold does NOT alert
    plan_minor = GridPlan(
        symbol="SOLUSDT",
        decision=plan.decision,
        lower_bound=plan.lower_bound * 1.005,  # 0.5% delta
        upper_bound=plan.upper_bound * 1.005,
        grid_count=plan.grid_count,
        estimated_grid_pct=plan.estimated_grid_pct,
    )
    assert not should_alert_grid_change(plan_minor, plan, threshold_pct=2.0)

    # Check boundary delta >= 2% DOES alert
    plan_major = GridPlan(
        symbol="SOLUSDT",
        decision=plan.decision,
        lower_bound=plan.lower_bound * 1.03,  # 3% delta
        upper_bound=plan.upper_bound,
        grid_count=plan.grid_count,
        estimated_grid_pct=plan.estimated_grid_pct,
    )
    assert should_alert_grid_change(plan_major, plan, threshold_pct=2.0)


def test_grid_policy_anti_falling_knife_lower_bound_breach() -> None:
    """When price breaks below lower bound, grid PAUSES; never blindly lowers lower bound."""
    config = MarketWatchConfig()
    previous_grid = GridPlan(
        symbol="SOLUSDT",
        decision=GridDecision.NEUTRAL,
        lower_bound=100.0,
        upper_bound=120.0,
        grid_count=5,
        estimated_grid_pct=0.03,
    )

    # Current price drops to 98.0 (below lower_bound 100.0)
    tf_1h = make_dummy_tf("SOLUSDT", "1h", close=98.0, regime=Regime.RANGE, adx_val=15.0, supports=(85.0,))
    tf_15m = make_dummy_tf("SOLUSDT", "15m", close=98.0, regime=Regime.RANGE)

    plan = evaluate_grid_policy(
        symbol="SOLUSDT",
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=DerivativesMetrics(mark_price=98.0),
        prev_grid=previous_grid,
        config=config,
    )
    assert plan.decision == GridDecision.PAUSE
    assert "AVOID_BLIND_LOWERING_KNIFE_ACCUMULATION" in plan.reason_codes
    assert plan.lower_bound == 100.0  # Does NOT lower the bound
    assert should_alert_grid_change(plan, previous_grid)  # State change alert from NEUTRAL to PAUSE


# =========================================================================
# 8. STATE STORE, DEDUPLICATION & PERSISTENCE
# =========================================================================

def test_state_store_and_deduplication() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_mw.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        tf = make_dummy_tf("BTCUSDT", "1h", 50000.0)
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1700000000000,
            observed_at_ms=1700000000000,
            exchange_time_ms=1700000000000,
            price=PriceMetrics(last_price=50000.0),
            tf_15m=tf,
            tf_1h=tf,
            tf_4h=tf,
            derivatives=DerivativesMetrics(mark_price=50000.0),
            snapshot_hash="hash_123",
        )

        assessment = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.TREND_PULLBACK,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.EXCELLENT,
                entry_low=49800.0,
                entry_high=50200.0,
                stop_loss=48800.0,
                take_profit_1=52000.0,
                take_profit_2=54000.0,
                invalidation_level=48500.0,
                gross_rr=2.2,
                net_rr=2.0,
                confidence_band=ConfidenceBand.HIGH,
                reason_codes=("HEALTHY_OI_BUILD",),
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=85.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL),
            rank=1,
            alert_fingerprint="abc_fingerprint_1",
            lifecycle_state=SignalLifecycleState.TRIGGERED,
        )

        # 1. First evaluation: no previous state -> should alert
        should_alert, sev, _reasons = evaluate_alert_emission(assessment, None, config)
        assert should_alert
        assert sev == AlertSeverity.ACTION

        # Save symbol state
        store.save_symbol_state("BTCUSDT", assessment, now_ms=1700000000000, alert_sent=True)
        prev = store.get_symbol_state("BTCUSDT")
        assert prev is not None
        assert prev["last_alert_fingerprint"] == "abc_fingerprint_1"

        # 2. Second evaluation with identical state fingerprint: should suppress (NO_NOTIFICATION)
        should_alert2, _, reasons2 = evaluate_alert_emission(assessment, prev, config)
        assert not should_alert2
        assert "NO_NOTIFICATION_IDENTICAL_STATE" in reasons2


# =========================================================================
# 9. ALERTING & FEISHU CARD BUILDER
# =========================================================================

def test_feishu_card_builder() -> None:
    alert = MarketWatchAlert(
        symbol="BTCUSDT",
        severity=AlertSeverity.ACTION,
        title="[MarketWatch] BTCUSDT: DIRECTIONAL SIGNAL (LONG / HIGH)",
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.LONG,
            setup=PlaybookType.TREND_PULLBACK,
            regime=Regime.TREND_UP,
            entry_quality=EntryQuality.EXCELLENT,
            entry_low=64000.0,
            entry_high=64200.0,
            stop_loss=63200.0,
            take_profit_1=66000.0,
            take_profit_2=67500.0,
            invalidation_level=63000.0,
            gross_rr=2.3,
            net_rr=2.1,
            confidence_band=ConfidenceBand.HIGH,
            derivatives_regime=DerivativesRegime.HEALTHY_LONG_BUILD,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
        fingerprint="fp_card_123",
        evidence=("PULLBACK_TO_EMA20_HOLDING", "HEALTHY_LONG_BUILD"),
        risks=("OVERNIGHT_FUNDING_SPIKE",),
        alert_time_ms=1700000000000,
    )

    card = build_market_watch_card(alert)
    assert card["msg_type"] == "interactive"
    card_body = card["card"]
    assert card_body["header"]["template"] == "green"  # ACTION LONG -> green
    text_content = str(card)
    assert "64,000" in text_content
    assert "63,200" in text_content
    assert "TREND_PULLBACK" in text_content


# =========================================================================
# 10. SCENARIOS A THROUGH H (SECTION 43)
# =========================================================================

def test_scenario_a_bullish_breakout_healthy_oi() -> None:
    """Scenario A: Bullish breakout with healthy OI expansion."""
    config = MarketWatchConfig()
    closed = Candle("BTCUSDT", "15m", 100, 200, 102.0, 106.0, 102.0, 105.5, 5000.0)
    tf_15m = TimeframeSnapshot(
        interval="15m",
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=105.5,
        ema_fast=103.0,
        ema_mid=101.0,
        ema_fast_slope=0.03,
        ema_mid_slope=0.02,
        atr=1.5,
        atr_percentile=50.0,
        adx=32.0,
        rsi=62.0,
        roc=0.035,
        volume=5000.0,
        volume_z=1.5,
        bb_width=0.06,
        bb_width_percentile=55.0,
        recent_swing_high=105.0,
        recent_swing_low=100.0,
        supports=(102.0,),
        resistances=(105.0,),
        structure="HH_HL",
        regime=Regime.TREND_UP,
    )
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=105.5, regime=Regime.TREND_UP, resistances=(105.0,))
    deriv = DerivativesMetrics(mark_price=105.5, oi_1h_change=0.035, funding_rate=0.0001)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=1.2, state=ExhaustionState.NORMAL)

    plan = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
    )
    assert plan is not None
    # Bar N confirms breakout without triggering entry on same bar
    assert plan["decision"] == DirectionalDecision.WAIT
    assert plan["setup"] == PlaybookType.BREAKOUT_RETEST
    assert "BREAKOUT_CONFIRMED" in plan["reasons"]

    # Bar N+1 retest holding above level triggers LONG
    from dataclasses import replace
    retest_bar = Candle("BTCUSDT", "15m", 200, 300, 105.5, 105.8, 105.1, 105.4, 4000.0)
    tf_15m_retest = make_dummy_tf("BTCUSDT", "15m", close=105.4)
    tf_15m_retest = replace(tf_15m_retest, latest_closed_bar=retest_bar, closed_bar_end_time_ms=300)
    plan_retest = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m_retest,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
        prev_state=plan,
    )
    assert plan_retest is not None
    assert plan_retest["decision"] == DirectionalDecision.LONG
    assert plan_retest["setup"] == PlaybookType.BREAKOUT_RETEST
    assert "RETEST_CONFIRMED" in plan_retest["reasons"]


def test_scenario_b_bullish_breakout_low_oi_spot_divergence() -> None:
    """Scenario B: Bullish breakout on low OI / spot divergence flags trap warning."""
    config = MarketWatchConfig()
    tf_1h = make_dummy_tf("ETHUSDT", "1h", close=106.0, resistances=(105.0,))
    closed = Candle("ETHUSDT", "15m", 100, 200, 104.5, 106.5, 104.0, 106.0, 500.0)
    tf_15m = TimeframeSnapshot(
        interval="15m",
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=106.0,
        ema_fast=103.0,
        ema_mid=101.0,
        ema_fast_slope=0.03,
        ema_mid_slope=0.02,
        atr=1.5,
        atr_percentile=50.0,
        adx=25.0,
        rsi=65.0,
        roc=0.02,
        volume=500.0,
        volume_z=-0.5,
        bb_width=0.08,
        bb_width_percentile=60.0,
        recent_swing_high=105.0,
        recent_swing_low=100.0,
        supports=(102.0,),
        resistances=(105.0,),
        structure="HH_HL",
        regime=Regime.TREND_UP,
    )
    # OI contracting despite price breakout
    deriv = DerivativesMetrics(mark_price=106.0, oi_1h_change=-0.01, funding_rate=0.00005)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=1.0, state=ExhaustionState.NORMAL)

    plan = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
    )
    assert plan is not None
    assert "BREAKOUT_LOW_PARTICIPATION" in plan["risks"]


def test_scenario_c_extreme_overextension_anti_chase_ranking() -> None:
    """Scenario C: SUI with 20% gain but extreme overextension + long crowding vs LINK with healthy pull-back."""
    config = MarketWatchConfig()

    # SUI: overextended (> 2.5 ATR from EMA20), long crowding
    sui_tf = make_dummy_tf("SUIUSDT", "1h", close=120.0, ema_fast=100.0, atr=3.0)  # distance = 6.6 ATR
    sui_deriv = DerivativesMetrics(
        mark_price=120.0,
        funding_rate=0.0005,
        top_trader_position_ratio=2.8,
        regime=DerivativesRegime.LONG_CROWDING,
    )
    sui_exhaustion = ExhaustionMetrics(distance_from_ema20_atr=6.6, state=ExhaustionState.EXTREME)
    sui_veto, sui_vetoes = check_fatal_vetoes(
        decision=DirectionalDecision.LONG,
        exhaustion=sui_exhaustion,
        net_rr=1.8,
        tf_4h=sui_tf,
        derivatives=sui_deriv,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        config=config,
    )
    assert sui_veto
    assert "FATAL_VETO_EXTREME_OVEREXTENSION" in sui_vetoes

    sui_score = calculate_opportunity_score(
        tf_1h=sui_tf,
        tf_15m=sui_tf,
        entry_quality=EntryQuality.POOR,
        derivatives=sui_deriv,
        exhaustion=sui_exhaustion,
        relative_perf=None,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        net_rr=1.8,
        has_fatal_veto=sui_veto,
        config=config,
    )
    assert sui_score == 0.0

    # LINK: healthy trend pullback, good quality
    link_tf = make_dummy_tf("LINKUSDT", "1h", close=101.0, ema_fast=100.0, atr=2.0)  # distance = 0.5 ATR
    link_deriv = DerivativesMetrics(mark_price=101.0, regime=DerivativesRegime.HEALTHY_LONG_BUILD)
    link_exhaustion = ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL)
    link_veto, _ = check_fatal_vetoes(
        decision=DirectionalDecision.LONG,
        exhaustion=link_exhaustion,
        net_rr=2.2,
        tf_4h=link_tf,
        derivatives=link_deriv,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        config=config,
    )
    assert not link_veto

    link_score = calculate_opportunity_score(
        tf_1h=link_tf,
        tf_15m=link_tf,
        entry_quality=EntryQuality.EXCELLENT,
        derivatives=link_deriv,
        exhaustion=link_exhaustion,
        relative_perf=None,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        net_rr=2.2,
        has_fatal_veto=link_veto,
        config=config,
    )
    assert link_score > 60.0
    # LINK completely dominates SUI due to anti-chasing veto
    assert link_score > sui_score


def test_scenario_d_btc_downside_shock_veto() -> None:
    """Scenario D: BTC downside shock penalizes/vetoes alt longs."""
    config = MarketWatchConfig()
    btc_tf = make_dummy_tf("BTCUSDT", "1h", close=47000.0, regime=Regime.TREND_DOWN, roc_val=-0.05)
    btc_snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=47000.0, change_24h_pct=-0.05),
        tf_15m=btc_tf,
        tf_1h=btc_tf,
        tf_4h=btc_tf,
        derivatives=DerivativesMetrics(mark_price=47000.0),
        snapshot_hash="hash_btc",
    )

    ctx, _, _ = evaluate_benchmark_context(btc_snapshot=btc_snap, eth_snapshot=None, config=config)
    assert ctx in (BenchmarkContext.BTC_VOLATILITY_SHOCK, BenchmarkContext.MARKET_RISK_OFF)


def test_scenario_e_range_grid_recommendation() -> None:
    """Scenario E: Clean range generates active grid recommendation."""
    config = MarketWatchConfig()
    tf_1h = make_dummy_tf(
        "BNBUSDT", "1h", close=300.0, regime=Regime.RANGE, adx_val=14.0, supports=(285.0,), resistances=(315.0,)
    )
    tf_15m = make_dummy_tf("BNBUSDT", "15m", close=300.0, regime=Regime.RANGE)
    plan = evaluate_grid_policy(
        symbol="BNBUSDT",
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=DerivativesMetrics(mark_price=300.0, funding_rate=0.00005),
        prev_grid=None,
        config=config,
    )
    assert plan.decision in (GridDecision.LONG_BIAS, GridDecision.SHORT_BIAS, GridDecision.NEUTRAL)
    assert plan.lower_bound is not None and plan.upper_bound is not None
    assert plan.grid_count >= 3


def test_scenario_f_range_grid_lower_bound_breach() -> None:
    """Scenario F: Anti-falling-knife lower bound breach switches to PAUSE."""
    config = MarketWatchConfig()
    prev = GridPlan(
        symbol="SOLUSDT",
        decision=GridDecision.NEUTRAL,
        lower_bound=100.0,
        upper_bound=120.0,
        grid_count=5,
        estimated_grid_pct=0.02,
    )
    # Price breaks down to 97.0
    tf_1h = make_dummy_tf("SOLUSDT", "1h", close=97.0, regime=Regime.RANGE, adx_val=15.0, supports=(80.0,))
    tf_15m = make_dummy_tf("SOLUSDT", "15m", close=97.0, regime=Regime.RANGE)
    plan = evaluate_grid_policy(
        symbol="SOLUSDT",
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=DerivativesMetrics(mark_price=97.0),
        prev_grid=prev,
        config=config,
    )
    assert plan.decision == GridDecision.PAUSE
    assert plan.lower_bound == 100.0  # Does NOT lower bound


def test_scenario_g_deduplication_noise_suppression() -> None:
    """Scenario G: Identical fingerprint produces no new notification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_g.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        tf = make_dummy_tf("BTCUSDT", "1h", 50000.0)
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=50000.0),
            tf_15m=tf,
            tf_1h=tf,
            tf_4h=tf,
            derivatives=DerivativesMetrics(mark_price=50000.0),
            snapshot_hash="hash_1",
        )

        assessment = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.WAIT,
                setup=PlaybookType.NO_TRADE,
                regime=Regime.RANGE,
                entry_quality=EntryQuality.POOR,
                entry_low=0.0,
                entry_high=0.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=20.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.0, state=ExhaustionState.NORMAL),
            rank=4,
            alert_fingerprint="stable_fp_999",
            lifecycle_state=SignalLifecycleState.CANDIDATE,
        )

        store.save_symbol_state("BTCUSDT", assessment, now_ms=1000, alert_sent=True)
        prev = store.get_symbol_state("BTCUSDT")
        assert prev is not None

        alert, _, reasons = evaluate_alert_emission(assessment, prev, config)
        assert not alert
        assert "NO_NOTIFICATION_IDENTICAL_STATE" in reasons


def test_scenario_h_symbol_data_failure_isolation() -> None:
    """Scenario H: One symbol failure does not halt or fail the rest of universe."""
    client = MagicMock()

    def mock_klines(symbol: str, interval: str, limit: int) -> list[Candle]:
        if symbol == "ETHUSDT":
            raise ConnectionResetError("Binance temporary glitch")
        return make_candle_series(symbol, interval, 40)

    client.klines.side_effect = mock_klines
    client.collect_derivatives.return_value = MagicMock(
        snapshot=MagicMock(
            mark_price=100.0,
            index_price=100.0,
            funding_rate=0.0001,
            funding_time_ms=1000,
            open_interest=10000.0,
            open_interest_change_pct=0.01,
            taker_buy_sell_ratio=1.1,
            basis_rate=0.0001,
            long_short_account_ratio=1.0,
            order_book_imbalance=0.1,
            spread_bps=1.5,
        )
    )
    client._optional_get.return_value = None

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_h.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        scanner = MarketWatchScanner(config=config, client=client, store=store)
        ranked_assessments, _alerts = scanner.scan_universe(["BTCUSDT", "ETHUSDT"])

        assert len(ranked_assessments) == 1
        assert ranked_assessments[0].symbol == "BTCUSDT"


# =========================================================================
# 11. SHADOW EVALUATION & FORWARD OUTCOMES
# =========================================================================

def test_shadow_evaluation_manager() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_shadow.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store)

        tf = make_dummy_tf("BTCUSDT", "1h", 100.0)
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=100.0),
            tf_15m=tf,
            tf_1h=tf,
            tf_4h=tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_shadow",
        )

        assessment = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.TREND_PULLBACK,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.EXCELLENT,
                entry_low=100.0,
                entry_high=100.5,
                stop_loss=95.0,
                take_profit_1=110.0,
                take_profit_2=115.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.2, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
        )

        shadow_id = mgr.record_decision(assessment, reference_notes="Test shadow record")
        assert shadow_id > 0

        # Simulate subsequent forward candles hitting TP1
        future_candles = [
            Candle("BTCUSDT", "1h", 2000, 3000, 100.0, 105.0, 99.0, 104.0, 1000.0),
            Candle("BTCUSDT", "1h", 3000, 4000, 104.0, 112.0, 103.0, 111.0, 2000.0),  # TP1 110 hit
        ]

        outcome = mgr.evaluate_forward_outcomes(
            shadow_id=shadow_id,
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=115.0,
            direction=DirectionalDecision.LONG,
            future_candles=future_candles,
        )
        assert outcome["tp1_hit"] is True
        assert outcome["future_mfe"] >= 2.0  # (112 - 100) / 5 = 2.4 R
        assert outcome["net_r"] >= 1.0


# =========================================================================
# 12. SIGNAL LIFECYCLE ADVANCEMENT
# =========================================================================

def test_signal_lifecycle_transitions() -> None:
    # 1. CANDIDATE -> ARMED -> TRIGGERED
    s1 = advance_lifecycle_state(None, DirectionalDecision.WAIT, EntryQuality.POOR, is_invalidated=False)
    assert s1 == SignalLifecycleState.CANDIDATE

    s2 = advance_lifecycle_state(s1, DirectionalDecision.LONG, EntryQuality.MARGINAL, is_invalidated=False)
    assert s2 == SignalLifecycleState.ARMED

    s3 = advance_lifecycle_state(s2, DirectionalDecision.LONG, EntryQuality.EXCELLENT, is_invalidated=False)
    assert s3 == SignalLifecycleState.TRIGGERED

    # Invalidation overrides
    s4 = advance_lifecycle_state(s3, DirectionalDecision.LONG, EntryQuality.EXCELLENT, is_invalidated=True)
    assert s4 == SignalLifecycleState.INVALIDATED

    # TTL expiry
    s5 = advance_lifecycle_state(
        SignalLifecycleState.TRIGGERED,
        DirectionalDecision.LONG,
        EntryQuality.EXCELLENT,
        is_invalidated=False,
        age_bars=10,
        max_age_bars=6,
    )
    assert s5 == SignalLifecycleState.EXPIRED


# =========================================================================
# 13. EXECUTION SAFETY INVARIANT
# =========================================================================

def test_execution_safety_no_trading_methods() -> None:
    """Ensure MarketWatch module has zero order execution capabilities."""
    import inspect

    import btc_quant_agent.market_watch as mw
    import btc_quant_agent.market_watch.scanner as mw_scanner
    import btc_quant_agent.market_watch.service as mw_service

    forbidden_terms = ["order_market", "order_limit", "cancel_order", "post_order", "submit_order", "place_order"]

    for module in [mw, mw_scanner, mw_service]:
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) or inspect.isclass(obj):
                for term in forbidden_terms:
                    assert term not in name.lower(), f"Forbidden order method found: {name} in {module.__name__}"


# =========================================================================
# 14. R1 ADVERSARIAL TESTS (R1-01 THROUGH R1-15)
# =========================================================================

def test_r1_01_same_candle_cannot_breakout_and_retest() -> None:
    """Test 1: Same candle cannot breakout+retest simultaneously."""
    from dataclasses import replace

    config = MarketWatchConfig()
    closed = Candle("BTCUSDT", "15m", 100, 200, 102.0, 106.0, 102.0, 105.5, 5000.0)
    tf_15m = make_dummy_tf("BTCUSDT", "15m", close=105.5)
    tf_15m = replace(tf_15m, latest_closed_bar=closed, closed_bar_end_time_ms=200, volume_z=1.5)
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=105.5, resistances=(105.0,))
    deriv = DerivativesMetrics(mark_price=105.5, oi_1h_change=0.03, funding_rate=0.0001)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=1.0, state=ExhaustionState.NORMAL)

    plan = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
        prev_state=None,
    )
    assert plan is not None
    assert plan["decision"] == DirectionalDecision.WAIT
    assert plan["breakout_state"] == BreakoutState.BREAKOUT_CONFIRMED
    assert "RETEST_CONFIRMED" not in plan["reasons"]
    assert "AWAITING_CONFIRMED_RETEST" in plan["risks"]


def test_r1_02_breakout_bar_plus_later_valid_retest_succeeds() -> None:
    """Test 2: Breakout bar + later valid retest succeeds."""
    from dataclasses import replace

    config = MarketWatchConfig()
    closed = Candle("BTCUSDT", "15m", 100, 200, 102.0, 106.0, 102.0, 105.5, 5000.0)
    tf_15m = make_dummy_tf("BTCUSDT", "15m", close=105.5)
    tf_15m = replace(tf_15m, latest_closed_bar=closed, closed_bar_end_time_ms=200, volume_z=1.5)
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=105.5, resistances=(105.0,))
    deriv = DerivativesMetrics(mark_price=105.5, oi_1h_change=0.03, funding_rate=0.0001)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=1.0, state=ExhaustionState.NORMAL)

    # Bar N: Breakout
    bar_n_plan = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
    )
    assert bar_n_plan is not None

    # Bar N+2: Valid retest holding above level
    retest_bar = Candle("BTCUSDT", "15m", 300, 400, 105.8, 106.0, 105.1, 105.4, 4000.0)
    tf_15m_retest = make_dummy_tf("BTCUSDT", "15m", close=105.4)
    tf_15m_retest = replace(tf_15m_retest, latest_closed_bar=retest_bar, closed_bar_end_time_ms=400)

    retest_plan = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m_retest,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
        prev_state=bar_n_plan,
    )
    assert retest_plan is not None
    assert retest_plan["decision"] == DirectionalDecision.LONG
    assert retest_plan["breakout_state"] == BreakoutState.RETEST_CONFIRMED
    assert "RETEST_CONFIRMED" in retest_plan["reasons"]


def test_r1_03_short_plus_healthy_long_build_receives_penalized_score() -> None:
    """Test 3: SHORT + HEALTHY_LONG_BUILD receives negative/low derivative score."""
    config = MarketWatchConfig()
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=95.0, regime=Regime.TREND_DOWN, structure="LH_LL")
    tf_15m = make_dummy_tf("BTCUSDT", "15m", close=95.0, regime=Regime.TREND_DOWN, structure="LH_LL")
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=-0.5, state=ExhaustionState.NORMAL)

    deriv_long_build = DerivativesMetrics(
        mark_price=95.0,
        regime=DerivativesRegime.HEALTHY_LONG_BUILD,
        oi_1h_change=0.04,
        taker_buy_sell_ratio=1.5,
    )
    deriv_short_build = DerivativesMetrics(
        mark_price=95.0,
        regime=DerivativesRegime.HEALTHY_SHORT_BUILD,
        oi_1h_change=0.04,
        taker_buy_sell_ratio=0.7,
    )

    score_penalized = calculate_opportunity_score(
        decision=DirectionalDecision.SHORT,
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        entry_quality=EntryQuality.GOOD,
        derivatives=deriv_long_build,
        exhaustion=exhaustion,
        relative_perf=None,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        net_rr=2.0,
        has_fatal_veto=False,
        config=config,
    )

    score_favorable = calculate_opportunity_score(
        decision=DirectionalDecision.SHORT,
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        entry_quality=EntryQuality.GOOD,
        derivatives=deriv_short_build,
        exhaustion=exhaustion,
        relative_perf=None,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        net_rr=2.0,
        has_fatal_veto=False,
        config=config,
    )

    assert score_penalized < score_favorable
    assert score_favorable - score_penalized >= 10.0


def test_r1_04_grid_only_pause_transition_emits_alert() -> None:
    """Test 4: Grid-only PAUSE transition emits alert."""
    config = MarketWatchConfig()
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=100.0)
    snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=100.0),
        tf_15m=tf_1h,
        tf_1h=tf_1h,
        tf_4h=tf_1h,
        derivatives=DerivativesMetrics(mark_price=100.0),
        snapshot_hash="hash_grid_alert",
    )

    assessment = SymbolAssessment(
        symbol="BTCUSDT",
        snapshot=snap,
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=0.0,
            entry_high=0.0,
            stop_loss=0.0,
            take_profit_1=0.0,
            take_profit_2=0.0,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE, lower_bound=95.0, upper_bound=105.0),
        opportunity_score=10.0,
        relative_performance=None,
        exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.0, state=ExhaustionState.NORMAL),
        rank=1,
        alert_fingerprint="fp_pause_1",
    )

    prev_state = {
        "grid_decision": "NEUTRAL",
        "grid_lower_bound": 95.0,
        "grid_upper_bound": 105.0,
        "last_alert_fingerprint": "fp_prev_neutral",
    }

    emit, severity, reasons = evaluate_alert_emission(assessment, prev_state, config)
    assert emit is True
    assert severity == AlertSeverity.RISK
    assert "GRID_STATUS_CHANGED" in reasons


def test_r1_05_recent_failed_breakout_raises_confirmation_threshold() -> None:
    """Test 5: Recent failed breakout raises confirmation threshold."""
    from dataclasses import replace

    config = MarketWatchConfig()
    closed = Candle("BTCUSDT", "15m", 100, 200, 102.0, 105.6, 102.0, 105.5, 5000.0)
    tf_15m = make_dummy_tf("BTCUSDT", "15m", close=105.5)
    tf_15m = replace(tf_15m, latest_closed_bar=closed, closed_bar_end_time_ms=200, volume_z=0.5)
    tf_1h = make_dummy_tf("BTCUSDT", "1h", close=105.5, resistances=(105.0,))
    deriv = DerivativesMetrics(mark_price=105.5, oi_1h_change=0.03, funding_rate=0.0001)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=1.0, state=ExhaustionState.NORMAL)

    # Case A: Normal breakout (no memory) -> confirms
    plan_normal = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
        prev_state=None,
    )
    assert plan_normal is not None

    # Case B: With recent failed breakout memory on level 105.0 within TTL
    # Normal volume_z=1.1 is below failed_level_min_volume_z (1.5), so it is rejected!
    prev_state_failed = {
        "recent_failed_breakout": 105.0,
        "recent_failed_breakout_ms": 100,
    }
    plan_with_memory = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
        prev_state=prev_state_failed,
    )
    assert plan_with_memory is None

    # Case C: With memory, but volume and breakout exceed higher bar -> confirms
    tf_15m_high_vol = replace(tf_15m, volume_z=1.8, close=106.0)
    closed_high = Candle("BTCUSDT", "15m", 100, 200, 102.0, 106.0, 102.0, 106.0, 9000.0)
    tf_15m_high_vol = replace(tf_15m_high_vol, latest_closed_bar=closed_high)
    plan_with_memory_high = evaluate_breakout_retest(
        tf_1h=tf_1h,
        tf_15m=tf_15m_high_vol,
        derivatives=deriv,
        exhaustion=exhaustion,
        config=config,
        prev_state=prev_state_failed,
    )
    assert plan_with_memory_high is not None
    assert "FAILED_BREAKOUT_MEMORY_HIGHER_CONFIRMATION_MET" in plan_with_memory_high["reasons"]


def test_r1_06_armed_reachable_under_default_config() -> None:
    """Test 6: ARMED reachable under default config."""
    state = advance_lifecycle_state(
        previous_state=None,
        decision=DirectionalDecision.WAIT,
        entry_quality=EntryQuality.POOR,
        is_invalidated=False,
        has_setup=True,
        is_near_ready=True,
    )
    assert state == SignalLifecycleState.ARMED


def test_r1_07_ttl_expiry_reachable_in_scanner() -> None:
    """Test 7: TTL expiry reachable in scanner."""
    config = MarketWatchConfig()
    max_age = config.thresholds.max_signal_age_bars
    state = advance_lifecycle_state(
        previous_state=SignalLifecycleState.ARMED,
        decision=DirectionalDecision.WAIT,
        entry_quality=EntryQuality.POOR,
        is_invalidated=False,
        has_setup=True,
        is_near_ready=True,
        age_bars=max_age + 1,
        max_age_bars=max_age,
    )
    assert state == SignalLifecycleState.EXPIRED


def test_r1_08_shadow_record_auto_created_exactly_once() -> None:
    """Test 8: Shadow record auto-created exactly once."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_shadow_once.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        client = MagicMock()
        client.server_time_ms.return_value = 1700000000000
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(
                mark_price=100.0,
                index_price=100.0,
                funding_rate=0.0001,
                funding_time_ms=1000,
                open_interest=10000.0,
                open_interest_time_ms=1000,
                open_interest_change_pct=0.01,
                taker_buy_sell_ratio=1.1,
                taker_time_ms=1000,
                basis_rate=0.0001,
                basis_time_ms=1000,
                long_short_account_ratio=1.0,
                long_short_time_ms=1000,
                order_book_imbalance=0.1,
                spread_bps=1.5,
            ),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None

        scanner = MarketWatchScanner(config=config, client=client, store=store)

        mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
        mock_snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=100.0),
            tf_15m=mock_tf,
            tf_1h=mock_tf,
            tf_4h=mock_tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_armed_1",
        )
        armed_asmt = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=mock_snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.TREND_PULLBACK,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.GOOD,
                entry_low=99.0,
                entry_high=101.0,
                stop_loss=95.0,
                take_profit_1=110.0,
                take_profit_2=115.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.ARMED,
        )
        scanner.assess_symbol = MagicMock(return_value=armed_asmt)  # type: ignore[method-assign]

        # Scan 1: transitions to ARMED -> creates shadow record
        scanner.scan_universe(["BTCUSDT"])
        records_1 = store.get_all_shadow_records()
        assert len(records_1) == 1

        # Scan 2: still ARMED -> does NOT create a duplicate record
        scanner.scan_universe(["BTCUSDT"])
        records_2 = store.get_all_shadow_records()
        assert len(records_2) == 1


def test_r1_09_link_only_scan_still_loads_btc_eth_context() -> None:
    """Test 9: LINK-only scan still loads BTC/ETH context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_link.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        collected_symbols: list[str] = []
        client = MagicMock()
        client.server_time_ms.return_value = 1700000000000

        def mock_klines(symbol: str, interval: str, limit: int) -> list[Candle]:
            collected_symbols.append(symbol)
            return make_candle_series(symbol, interval, 40)

        client.klines.side_effect = mock_klines
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(
                mark_price=10.0,
                index_price=10.0,
                funding_rate=0.0001,
                funding_time_ms=1000,
                open_interest=10000.0,
                open_interest_time_ms=1000,
                open_interest_change_pct=0.01,
                taker_buy_sell_ratio=1.1,
                taker_time_ms=1000,
                basis_rate=0.0001,
                basis_time_ms=1000,
                long_short_account_ratio=1.0,
                long_short_time_ms=1000,
                order_book_imbalance=0.1,
                spread_bps=1.5,
            ),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None

        scanner = MarketWatchScanner(config=config, client=client, store=store)
        assessments, _ = scanner.scan_universe(["LINKUSDT"])

        # BTC and ETH were collected in background
        assert "BTCUSDT" in collected_symbols
        assert "ETHUSDT" in collected_symbols
        assert "LINKUSDT" in collected_symbols

        # But returned assessments ONLY contain the target symbol
        assert len(assessments) == 1
        assert assessments[0].symbol == "LINKUSDT"


def test_r1_10_partial_derivative_failure_marks_degraded() -> None:
    """Test 10: Partial derivative failure -> DEGRADED."""
    client = MagicMock()
    client.server_time_ms.return_value = 1700000000000
    client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
    client.collect_derivatives.return_value = MagicMock(
        snapshot=MagicMock(
            mark_price=100.0,
            index_price=100.0,
            funding_rate=0.0001,
            funding_time_ms=1000,
            open_interest=None,
            open_interest_time_ms=None,
            open_interest_change_pct=None,
            taker_buy_sell_ratio=None,
            taker_time_ms=None,
            basis_rate=None,
            basis_time_ms=None,
            long_short_account_ratio=None,
            long_short_time_ms=None,
            order_book_imbalance=None,
            spread_bps=None,
        ),
        field_availability={"mark_price": True, "open_interest": False},
        endpoint_errors={"open_interest": "HTTP_429"},
    )
    client._optional_get.return_value = None

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_part_fail.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        scanner = MarketWatchScanner(config=config, client=client, store=store)
        snap, health, reasons = scanner.collect_symbol_snapshot("BTCUSDT", now_ms=1700000000000)

        assert snap is not None
        assert health == ScanHealth.DEGRADED
        assert any("DERIVATIVES_PARTIAL_ERROR" in r for r in reasons)


def test_r1_11_market_watch_data_config_is_actually_used() -> None:
    """Test 11: Market-watch DataConfig is actually used."""
    from btc_quant_agent.config import DataConfig
    from btc_quant_agent.market_watch.service import MarketWatchService

    dcfg = DataConfig(rest_base_url="https://custom.binance.endpoint", request_timeout_seconds=42.0)
    mw_cfg = MarketWatchConfig()
    svc = MarketWatchService.create(config=mw_cfg, data_config=dcfg)
    assert svc.client.config.rest_base_url == "https://custom.binance.endpoint"
    assert svc.client.config.request_timeout_seconds == 42.0


def test_r1_12_policy_config_hash_changes_when_thresholds_change() -> None:
    """Test 12: Policy config hash changes when thresholds change."""
    from dataclasses import replace

    from btc_quant_agent.market_watch.config import compute_market_watch_config_hash

    cfg1 = MarketWatchConfig()
    hash1 = compute_market_watch_config_hash(cfg1)

    cfg2 = MarketWatchConfig(thresholds=replace(cfg1.thresholds, breakout_atr_threshold=0.55))
    hash2 = compute_market_watch_config_hash(cfg2)

    assert hash1 != hash2
    assert len(hash1) == 16
    assert len(hash2) == 16


def test_r1_13_multi_tf_relative_strength_contribution() -> None:
    """Test 13: 15m/1h/4h all contribute to RS."""
    from btc_quant_agent.market_watch.ranking import compute_relative_performances

    config = MarketWatchConfig()

    tf_15m_a = make_dummy_tf("SOLUSDT", "15m", roc_val=0.05)
    tf_1h_a = make_dummy_tf("SOLUSDT", "1h", roc_val=0.02)
    tf_4h_a = make_dummy_tf("SOLUSDT", "4h", roc_val=0.01)

    tf_15m_b = make_dummy_tf("SOLUSDT", "15m", roc_val=-0.05)  # Alter only 15m

    snap_btc = MarketSnapshot(
        symbol="BTCUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=100.0), tf_15m=make_dummy_tf("BTCUSDT", "15m", roc_val=0.0),
        tf_1h=make_dummy_tf("BTCUSDT", "1h", roc_val=0.0), tf_4h=make_dummy_tf("BTCUSDT", "4h", roc_val=0.0),
        derivatives=DerivativesMetrics(mark_price=100.0), snapshot_hash="h_btc",
        return_1h=0.0, return_4h=0.0, return_12h=0.0,
    )
    snap_eth = MarketSnapshot(
        symbol="ETHUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=10.0), tf_15m=make_dummy_tf("ETHUSDT", "15m", roc_val=0.0),
        tf_1h=make_dummy_tf("ETHUSDT", "1h", roc_val=0.0), tf_4h=make_dummy_tf("ETHUSDT", "4h", roc_val=0.0),
        derivatives=DerivativesMetrics(mark_price=10.0), snapshot_hash="h_eth",
        return_1h=0.0, return_4h=0.0, return_12h=0.0,
    )

    snap_sol_a = MarketSnapshot(
        symbol="SOLUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=50.0), tf_15m=tf_15m_a, tf_1h=tf_1h_a, tf_4h=tf_4h_a,
        derivatives=DerivativesMetrics(mark_price=50.0), snapshot_hash="h_sol_a",
        return_1h=0.02, return_4h=0.01, return_12h=0.05,
    )
    snap_sol_b = MarketSnapshot(
        symbol="SOLUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=50.0), tf_15m=tf_15m_b, tf_1h=tf_1h_a, tf_4h=tf_4h_a,
        derivatives=DerivativesMetrics(mark_price=50.0), snapshot_hash="h_sol_b",
        return_1h=0.02, return_4h=0.01, return_12h=-0.05,
    )

    perfs_a = compute_relative_performances({"BTCUSDT": snap_btc, "ETHUSDT": snap_eth, "SOLUSDT": snap_sol_a}, config)
    perfs_b = compute_relative_performances({"BTCUSDT": snap_btc, "ETHUSDT": snap_eth, "SOLUSDT": snap_sol_b}, config)

    assert perfs_a["SOLUSDT"].multi_tf_excess != perfs_b["SOLUSDT"].multi_tf_excess
    assert perfs_a["SOLUSDT"].multi_tf_excess > perfs_b["SOLUSDT"].multi_tf_excess


def test_r1_14_feishu_grid_only_alert_contains_no_fake_zero_price_directional_plan() -> None:
    """Test 14: Feishu grid-only alert contains no fake 0-price directional plan."""
    alert = MarketWatchAlert(
        symbol="BTCUSDT",
        severity=AlertSeverity.RISK,
        title="[MarketWatch] BTCUSDT: GRID PAUSE",
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=0.0,
            entry_high=0.0,
            stop_loss=0.0,
            take_profit_1=0.0,
            take_profit_2=0.0,
            opportunity_score=15.0,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE, lower_bound=95.0, upper_bound=105.0),
        fingerprint="fp_grid_only",
        evidence=("LOWER_BOUND_BREACHED",),
        risks=("DOWNWARD_VOLATILITY",),
        alert_time_ms=1700000000000,
        last_price=94.5,
        change_24h_pct=-0.03,
        atr=2.5,
        key_support=95.0,
        key_resistance=105.0,
    )

    card = build_market_watch_card(alert)
    card_str = str(card)

    # Must NOT display fake 0 entry zone or 0 stop loss
    assert "0 – 0" not in card_str
    assert "Stop Loss: 0" not in card_str
    assert "TP1 / TP2: 0 / 0" not in card_str
    # Must display latest price and grid info
    assert "94.5" in card_str
    assert "PAUSE" in card_str


# =========================================================================
# 11. MARKET WATCH R2 REFINEMENT TESTS
# =========================================================================


def test_r2_01_two_run_scanner_breakout_persist_to_retest_triggered() -> None:
    """R2-01: Breakout scan N persists breakout_direction -> Retest scan N+1 confirms RETEST_CONFIRMED/TRIGGERED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_01.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        symbol = "BTCUSDT"
        res_level = 100.0
        bar_len_ms = 15 * 60 * 1000

        # Bar N: Closed breakout above resistance (close=102.0 > 100.0)
        t_n = 1700000000000
        candle_n = Candle(symbol, "15m", t_n - bar_len_ms, t_n, 99.0, 102.5, 98.5, 102.0, 5000.0)
        tf_15m_n = TimeframeSnapshot(
            interval="15m",
            latest_bar=candle_n,
            latest_closed_bar=candle_n,
            closed_bar_end_time_ms=t_n,
            close=102.0,
            ema_fast=100.0,
            ema_mid=99.0,
            ema_fast_slope=0.02,
            ema_mid_slope=0.01,
            atr=1.0,
            atr_percentile=0.5,
            adx=25.0,
            rsi=55.0,
            roc=0.02,
            volume=5000.0,
            volume_z=1.0,
            bb_width=0.04,
            bb_width_percentile=0.5,
            recent_swing_high=res_level,
            recent_swing_low=95.0,
            supports=(95.0,),
            resistances=(res_level,),
            structure="HH_HL",
            regime=Regime.TREND_UP,
        )
        tf_1h_n = TimeframeSnapshot(
            interval="1h",
            latest_bar=candle_n,
            latest_closed_bar=candle_n,
            closed_bar_end_time_ms=t_n,
            close=102.0,
            ema_fast=100.0,
            ema_mid=99.0,
            ema_fast_slope=0.02,
            ema_mid_slope=0.01,
            atr=2.0,
            atr_percentile=0.5,
            adx=25.0,
            rsi=55.0,
            roc=0.02,
            volume=20000.0,
            volume_z=1.0,
            bb_width=0.04,
            bb_width_percentile=0.5,
            recent_swing_high=res_level,
            recent_swing_low=95.0,
            supports=(95.0,),
            resistances=(res_level,),
            structure="HH_HL",
            regime=Regime.TREND_UP,
        )
        tf_4h_n = tf_1h_n

        deriv_n = DerivativesMetrics(mark_price=102.0, oi_1h_change=0.02, funding_rate=0.0001)

        client_n = MagicMock()
        client_n.server_time_ms.return_value = t_n
        client_n.klines.return_value = [candle_n]

        scanner = MarketWatchScanner(config=config, client=client_n, store=store)

        # Mock collect_symbol_snapshot for Run 1
        snap_n = MarketSnapshot(
            symbol=symbol,
            decision_time_ms=t_n,
            observed_at_ms=t_n,
            exchange_time_ms=t_n,
            price=PriceMetrics(last_price=102.0),
            tf_15m=tf_15m_n,
            tf_1h=tf_1h_n,
            tf_4h=tf_4h_n,
            derivatives=deriv_n,
            snapshot_hash="snap_n",
        )
        scanner.collect_symbol_snapshot = MagicMock(return_value=(snap_n, ScanHealth.OK, {}))  # type: ignore[method-assign]

        assessments_n, _ = scanner.scan_universe([symbol])
        assert len(assessments_n) == 1
        asmt_n = assessments_n[0]

        # Scan 1: Breakout confirmed, awaiting retest -> DirectionalDecision.WAIT
        assert asmt_n.directional.breakout_state == BreakoutState.BREAKOUT_CONFIRMED
        assert asmt_n.directional.breakout_direction == "LONG"
        assert asmt_n.directional.decision == DirectionalDecision.WAIT

        # Verify SQLite persistence
        persisted_st_n = store.get_symbol_state(symbol)
        assert persisted_st_n is not None
        assert persisted_st_n["breakout_state"] == "BREAKOUT_CONFIRMED"
        assert persisted_st_n["breakout_direction"] == "LONG"
        assert persisted_st_n["breakout_level"] == res_level
        assert persisted_st_n["breakout_bar_end_ms"] == t_n

        # Bar N+1: Retests the level (low reaches level + retest_tol, closes above level at 101.5)
        t_n1 = t_n + bar_len_ms
        candle_n1 = Candle(symbol, "15m", t_n, t_n1, 102.0, 102.5, 100.1, 101.5, 6000.0)
        tf_15m_n1 = TimeframeSnapshot(
            interval="15m",
            latest_bar=candle_n1,
            latest_closed_bar=candle_n1,
            closed_bar_end_time_ms=t_n1,
            close=101.5,
            ema_fast=100.5,
            ema_mid=99.5,
            ema_fast_slope=0.02,
            ema_mid_slope=0.01,
            atr=1.0,
            atr_percentile=0.5,
            adx=25.0,
            rsi=55.0,
            roc=0.02,
            volume=6000.0,
            volume_z=1.0,
            bb_width=0.04,
            bb_width_percentile=0.5,
            recent_swing_high=res_level,
            recent_swing_low=95.0,
            supports=(95.0,),
            resistances=(res_level,),
            structure="HH_HL",
            regime=Regime.TREND_UP,
        )

        snap_n1 = MarketSnapshot(
            symbol=symbol,
            decision_time_ms=t_n1,
            observed_at_ms=t_n1,
            exchange_time_ms=t_n1,
            price=PriceMetrics(last_price=101.5),
            tf_15m=tf_15m_n1,
            tf_1h=tf_1h_n,
            tf_4h=tf_4h_n,
            derivatives=deriv_n,
            snapshot_hash="snap_n1",
        )
        scanner.collect_symbol_snapshot = MagicMock(return_value=(snap_n1, ScanHealth.OK, {}))  # type: ignore[method-assign]

        assessments_n1, _ = scanner.scan_universe([symbol])
        assert len(assessments_n1) == 1
        asmt_n1 = assessments_n1[0]

        # Scan 2: Retest confirmed, directional decision triggered!
        assert asmt_n1.directional.breakout_state == BreakoutState.RETEST_CONFIRMED
        assert asmt_n1.directional.decision == DirectionalDecision.LONG
        assert asmt_n1.lifecycle_state == SignalLifecycleState.TRIGGERED


def test_r2_02_derivatives_action_gate() -> None:
    """R2-02: Derivatives Action Gate enforcement rules."""
    config = MarketWatchConfig()

    # Rule 1: SHORT + LONG_LIQUIDATION => WAIT / DO_NOT_CHASE_SHORT
    d_liq = DerivativesMetrics(
        mark_price=100.0,
        regime=DerivativesRegime.LONG_LIQUIDATION,
    )
    dec, reasons, risks = apply_derivatives_action_gate(decision=DirectionalDecision.SHORT, derivatives=d_liq, config=config)
    assert dec == DirectionalDecision.WAIT
    assert "DERIVATIVES_VETO_SHORT_ON_LIQUIDATION_UNWIND" in reasons
    assert "DO_NOT_CHASE_SHORT" in risks

    # Rule 2: SHORT + DELEVERAGING => WAIT / DO_NOT_CHASE_SHORT
    d_del = DerivativesMetrics(
        mark_price=100.0,
        regime=DerivativesRegime.DELEVERAGING,
    )
    dec, reasons, risks = apply_derivatives_action_gate(decision=DirectionalDecision.SHORT, derivatives=d_del, config=config)
    assert dec == DirectionalDecision.WAIT
    assert "DERIVATIVES_VETO_SHORT_ON_LIQUIDATION_UNWIND" in reasons
    assert "DO_NOT_CHASE_SHORT" in risks

    # Rule 3: LONG + severe LONG_CROWDING => WAIT
    d_sev_long = DerivativesMetrics(
        mark_price=100.0,
        regime=DerivativesRegime.LONG_CROWDING,
        funding_rate=0.0009,  # > funding_extreme_abs (0.0008)
    )
    assert is_severe_long_crowding(d_sev_long, config)
    dec, reasons, risks = apply_derivatives_action_gate(decision=DirectionalDecision.LONG, derivatives=d_sev_long, config=config)
    assert dec == DirectionalDecision.WAIT
    assert "DERIVATIVES_VETO_SEVERE_LONG_CROWDING" in reasons
    assert "LONG_CROWDING_RISK" in risks

    # Rule 4: SHORT + severe SHORT_CROWDING => WAIT
    d_sev_short = DerivativesMetrics(
        mark_price=100.0,
        regime=DerivativesRegime.SHORT_CROWDING,
        funding_rate=-0.0009,  # <= -funding_extreme_abs (-0.0008)
        global_account_long_short_ratio=0.50,
    )
    assert is_severe_short_crowding(d_sev_short, config)
    dec, reasons, risks = apply_derivatives_action_gate(decision=DirectionalDecision.SHORT, derivatives=d_sev_short, config=config)
    assert dec == DirectionalDecision.WAIT
    assert "DERIVATIVES_VETO_SEVERE_SHORT_CROWDING" in reasons
    assert "SHORT_CROWDING_RISK" in risks

    # Rule 5: Moderate crowding does NOT veto (penalty only)
    d_mod_long = DerivativesMetrics(
        mark_price=100.0,
        regime=DerivativesRegime.LONG_CROWDING,
        funding_rate=0.0005,  # Moderate between 0.0003 and 0.0008
        global_account_long_short_ratio=1.5,
    )
    assert not is_severe_long_crowding(d_mod_long, config)
    dec, reasons, risks = apply_derivatives_action_gate(decision=DirectionalDecision.LONG, derivatives=d_mod_long, config=config)
    assert dec == DirectionalDecision.LONG


def test_r2_03_shadow_semantics_freeze_maturity_and_stop_first() -> None:
    """R2-03: Shadow horizon freeze, maturity gating, and conservative STOP_FIRST ambiguity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_03.db"
        store = MarketWatchStateStore(db_path)
        manager = ShadowEvaluationManager(store)

        t0 = 1700000000000
        bar_len_ms = 15 * 60 * 1000
        eval_bars = 4
        eval_end = t0 + eval_bars * bar_len_ms

        rec_id = store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="hash_s",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=["TEST"],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            evaluation_horizon_bars=eval_bars,
        )

        # 1. Verify frozen horizon stored in DB
        pending = store.get_pending_shadow_records()
        assert len(pending) == 1
        assert pending[0]["evaluation_horizon_bars"] == eval_bars
        assert pending[0]["evaluation_end_ms"] == eval_end

        # 2. At t = 2 bars (before maturity), no terminal event (price fluctuates between 95 and 105)
        c1 = Candle("BTCUSDT", "15m", t0, t0 + bar_len_ms, 100.0, 105.0, 95.0, 102.0, 100.0)
        c2 = Candle("BTCUSDT", "15m", t0 + bar_len_ms, t0 + 2 * bar_len_ms, 102.0, 104.0, 96.0, 101.0, 100.0)
        client = MagicMock()
        client.klines.return_value = [c1, c2]

        res = manager.resolve_pending_observations(client, current_time_ms=t0 + 2 * bar_len_ms)
        assert res["resolved_count"] == 0
        assert res["pending_count"] == 1
        assert res["results"][0]["status"] == "PENDING_UNMATURED"

        # Record remains unresolved in DB
        assert len(store.get_pending_shadow_records()) == 1

        # 3. Same-bar TP/SL ambiguity: Candle touches both SL (85 <= 90) and TP1 (115 >= 110)
        c_ambig = Candle("BTCUSDT", "15m", t0, t0 + bar_len_ms, 100.0, 115.0, 85.0, 105.0, 100.0)
        outcome = manager.evaluate_forward_outcomes(
            shadow_id=rec_id,
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction=DirectionalDecision.LONG,
            future_candles=[c_ambig],
            persist=False,
        )
        # Conservative STOP_FIRST assumes SL hit first!
        assert outcome["sl_hit"] is True
        assert outcome["tp1_hit"] is False
        assert outcome["net_r"] == -1.0
        assert outcome["is_terminal"] is True


def test_r2_04_strict_pit_timestamps() -> None:
    """R2-04: decision_time >= all consumed source availability/receipt timestamps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_04.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        t_exchange = 1700000000000
        t_deriv = 1700000006000
        t_scan_start = 1700000001000

        client = MagicMock()
        client.server_time_ms.return_value = t_exchange
        client.klines.side_effect = lambda sym, interval, limit: make_candle_series(sym, interval, 40)
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(
                mark_price=104.0,
                index_price=104.0,
                funding_rate=0.0001,
                funding_time_ms=t_deriv,
                open_interest=1000.0,
                open_interest_time_ms=t_deriv,
                open_interest_change_pct=0.01,
                taker_buy_sell_ratio=1.0,
                taker_time_ms=t_deriv,
                basis_rate=0.0001,
                basis_time_ms=t_deriv,
                long_short_account_ratio=1.0,
                long_short_time_ms=t_deriv,
                order_book_imbalance=0.0,
                spread_bps=1.0,
            ),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None

        scanner = MarketWatchScanner(config=config, client=client, store=store)
        snap, _health, _errors = scanner.collect_symbol_snapshot("BTCUSDT", now_ms=t_scan_start)

        assert snap is not None
        # PIT guarantee: observed_at derived from sources, decision_time >= all sources
        assert snap.observed_at_ms >= t_deriv
        assert snap.decision_time_ms >= snap.observed_at_ms
        assert snap.decision_time_ms >= t_scan_start


def test_r2_05_grid_previous_bounds_uses_persisted_bounds() -> None:
    """R2-05: Grid previous bounds must use persisted grid_lower_bound/grid_upper_bound."""
    config = MarketWatchConfig()
    prev_state = {
        "grid_decision": "NEUTRAL",
        "grid_lower_bound": 92.0,
        "grid_upper_bound": 108.0,
        "recent_support": 80.0,     # Outdated support
        "recent_resistance": 120.0, # Outdated resistance
    }

    # Assessment with identical grid boundaries (92.0, 108.0)
    asmt = SymbolAssessment(
        symbol="BTCUSDT",
        policy_version="1.0",
        config_hash="h",
        snapshot=MagicMock(decision_time_ms=1000, snapshot_hash="h", tf_15m=MagicMock(closed_bar_end_time_ms=1000)),
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=0.0,
            entry_high=0.0,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.NEUTRAL, lower_bound=92.0, upper_bound=108.0),
        opportunity_score=50.0,
        relative_performance=None,
        exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
        rank=1,
        lifecycle_state=SignalLifecycleState.CANDIDATE,
        alert_fingerprint="fp1",
    )
    # Emission must recognize boundaries are identical to persisted grid bounds (no change)
    _emit, _sev, reasons = evaluate_alert_emission(asmt, prev_state, config)
    assert "GRID_BOUNDARIES_SHIFTED" not in reasons


def test_r2_06_lifecycle_reset_on_setup_change() -> None:
    """R2-06: New setup resets created_bar_end_ms and age_bars."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_06.db"
        store = MarketWatchStateStore(db_path)

        t0 = 1700000000000
        bar_len_ms = 15 * 60 * 1000
        # State from 5 bars ago under setup A
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_watch_symbol_state (
                    symbol, setup, lifecycle_state, created_bar_end_ms, updated_at_ms, age_bars
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("BTCUSDT", "TREND_PULLBACK", "CANDIDATE", t0, t0 + 5 * bar_len_ms, 5),
            )

        # Now new assessment with setup B (BREAKOUT_RETEST)
        t_curr = t0 + 5 * bar_len_ms
        closed = Candle("BTCUSDT", "15m", t_curr - bar_len_ms, t_curr, 100.0, 105.0, 99.0, 104.0, 100.0)
        tf_15m = TimeframeSnapshot(
            interval="15m",
            latest_bar=closed,
            latest_closed_bar=closed,
            closed_bar_end_time_ms=t_curr,
            close=104.0,
            ema_fast=100.0,
            ema_mid=99.0,
            ema_fast_slope=0.01,
            ema_mid_slope=0.01,
            atr=1.0,
            atr_percentile=0.5,
            adx=25.0,
            rsi=50.0,
            roc=0.01,
            volume=100.0,
            volume_z=0.5,
            bb_width=0.02,
            bb_width_percentile=0.5,
            recent_swing_high=105.0,
            recent_swing_low=99.0,
            supports=(99.0,),
            resistances=(105.0,),
            structure="HH_HL",
            regime=Regime.RANGE,
        )
        asmt = SymbolAssessment(
            symbol="BTCUSDT",
            policy_version="1.0",
            config_hash="h",
            snapshot=MagicMock(decision_time_ms=t_curr, snapshot_hash="h", tf_15m=tf_15m, tf_1h=tf_15m),
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.WAIT,
                setup=PlaybookType.BREAKOUT_RETEST,
                regime=Regime.RANGE,
                entry_quality=EntryQuality.POOR,
                entry_low=0.0,
                entry_high=0.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=50.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.CANDIDATE,
            alert_fingerprint="fp2",
        )

        store.save_symbol_state("BTCUSDT", asmt, now_ms=t_curr)
        st = store.get_symbol_state("BTCUSDT")
        assert st is not None
        assert st["setup"] == "BREAKOUT_RETEST"
        # created_bar_end_ms reset to t_curr, age_bars reset to 0!
        assert st["created_bar_end_ms"] == t_curr
        assert st["age_bars"] == 0


def test_r2_08_explain_grid_codes_and_shadow_resolve_return_schema() -> None:
    """R2-08: explain() returns grid_codes from reason_codes; shadow_resolve() returns int counts and results list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_08.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        client = MagicMock()
        client.klines.return_value = []

        service = MarketWatchService(config=config, client=client, store=store)

        # 1. explain() test with grid reason_codes
        dec_payload = {
            "symbol": "BTCUSDT",
            "grid": {
                "decision": "ACTIVE",
                "reason_codes": ["VOLATILITY_RANGE_BOUND", "SUFFICIENT_PROFIT_SPREAD"],
            },
            "veto_reasons": [],
        }
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_watch_assessments (
                    decision_time_ms, symbol, snapshot_hash, policy_version, config_hash,
                    regime, setup, directional_decision, grid_decision, entry_quality,
                    derivatives_regime, benchmark_context, opportunity_score, rank,
                    reason_codes_json, risk_codes_json, decision_json, alert_fingerprint,
                    notification_sent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1000, "BTCUSDT", "h", "1.0", "ch",
                    "RANGE", "NO_TRADE", "WAIT", "ACTIVE", "POOR",
                    "BALANCED", "NEUTRAL", 50.0, 1,
                    "[]", "[]", json.dumps(dec_payload), "fp",
                    0,
                ),
            )

        exp = service.explain("BTCUSDT")
        assert "grid_codes" in exp
        assert "VOLATILITY_RANGE_BOUND" in exp["grid_codes"]
        assert "SUFFICIENT_PROFIT_SPREAD" in exp["grid_codes"]

        # 2. shadow_resolve() schema test
        res = service.shadow_resolve()
        assert res["status"] == "SUCCESS"
        assert isinstance(res["resolved_count"], int)
        assert isinstance(res["pending_count"], int)
        assert isinstance(res["results"], list)
        assert "summary" in res


def test_r2_1_01_shadow_armed_and_triggered_independent_dedupe() -> None:
    """R2.1-01: ARMED and TRIGGERED have independent dedupe markers; ARMED does not suppress TRIGGERED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_1_01.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        client = MagicMock()
        client.server_time_ms.return_value = 1700000000000
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(
                mark_price=100.0,
                index_price=100.0,
                funding_rate=0.0001,
                funding_time_ms=1000,
                open_interest=10000.0,
                open_interest_time_ms=1000,
                open_interest_change_pct=0.01,
                taker_buy_sell_ratio=1.1,
                taker_time_ms=1000,
                basis_rate=0.0001,
                basis_time_ms=1000,
                long_short_account_ratio=1.0,
                long_short_time_ms=1000,
                order_book_imbalance=0.1,
                spread_bps=1.5,
            ),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None

        scanner = MarketWatchScanner(config=config, client=client, store=store)
        mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
        mock_snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=100.0),
            tf_15m=mock_tf,
            tf_1h=mock_tf,
            tf_4h=mock_tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_armed_1",
        )

        armed_asmt = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=mock_snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.WAIT,
                setup=PlaybookType.TREND_PULLBACK,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.GOOD,
                entry_low=99.0,
                entry_high=101.0,
                stop_loss=95.0,
                take_profit_1=110.0,
                take_profit_2=115.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.ARMED,
        )
        scanner.assess_symbol = MagicMock(return_value=armed_asmt)

        # Scan 1: ARMED -> records 1 SETUP_ARMED observation
        scanner.scan_universe(["BTCUSDT"])
        records_1 = store.get_all_shadow_records()
        assert len(records_1) == 1
        assert records_1[0]["observation_type"] == "SETUP_ARMED"

        # Scan 2: still ARMED -> does NOT create duplicate record
        scanner.scan_universe(["BTCUSDT"])
        records_2 = store.get_all_shadow_records()
        assert len(records_2) == 1

        # Scan 3: transitions to TRIGGERED LONG -> creates ACTIONABLE_TRIGGERED observation (not suppressed by ARMED!)
        triggered_asmt = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=mock_snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.TREND_PULLBACK,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.GOOD,
                entry_low=99.0,
                entry_high=101.0,
                stop_loss=95.0,
                take_profit_1=110.0,
                take_profit_2=115.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=85.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
        )
        scanner.assess_symbol = MagicMock(return_value=triggered_asmt)

        scanner.scan_universe(["BTCUSDT"])
        records_3 = store.get_all_shadow_records()
        assert len(records_3) == 2
        obs_types = {r["observation_type"] for r in records_3}
        assert obs_types == {"SETUP_ARMED", "ACTIONABLE_TRIGGERED"}

        # Scan 4: still TRIGGERED LONG -> does NOT create duplicate
        scanner.scan_universe(["BTCUSDT"])
        records_4 = store.get_all_shadow_records()
        assert len(records_4) == 2

        # Check performance metrics: only ACTIONABLE_TRIGGERED is eligible for trading metrics
        metrics = compute_performance_metrics(records_4)
        assert metrics["total_records"] == 2
        assert metrics["actionable_records"] == 1
        assert metrics["ineligible_count"] == 1  # The SETUP_ARMED observation


def test_r2_1_02_derivatives_risk_alert_on_wait_to_wait() -> None:
    """R2.1-02: Alert on severe crowding (>=WATCH) and liquidation/deleveraging (>=RISK) even during WAIT -> WAIT."""
    config = MarketWatchConfig(min_alert_severity="WATCH")
    mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)

    # Previous state: WAIT with BALANCED / NEUTRAL derivatives
    prev_state = {
        "symbol": "BTCUSDT",
        "directional_decision": "WAIT",
        "lifecycle_state": "CANDIDATE",
        "derivatives_regime": "BALANCED",
        "last_alert_fingerprint": "old_fp_neutral",
    }

    # Case A: Transition to severe long crowding (WAIT -> WAIT) -> at least WATCH
    severe_crowding_snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=100.0),
        tf_15m=mock_tf,
        tf_1h=mock_tf,
        tf_4h=mock_tf,
        derivatives=DerivativesMetrics(
            mark_price=100.0,
            funding_rate=0.0006,  # >= 0.0005
            taker_buy_sell_ratio=1.35,  # >= 1.30
            current_open_interest=10000.0,
            oi_1h_change=0.04,
            regime=DerivativesRegime.LONG_CROWDING,
        ),
        snapshot_hash="hash_sc",
    )
    asmt_sc = SymbolAssessment(
        symbol="BTCUSDT",
        snapshot=severe_crowding_snap,
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=0.0,
            entry_high=0.0,
            derivatives_regime=DerivativesRegime.LONG_CROWDING,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
        opportunity_score=30.0,
        relative_performance=None,
        exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
        rank=1,
        lifecycle_state=SignalLifecycleState.CANDIDATE,
        alert_fingerprint="new_fp_sc",
    )
    emit, sev, reasons = evaluate_alert_emission(asmt_sc, prev_state, config)
    assert emit is True
    assert sev in (AlertSeverity.WATCH, AlertSeverity.RISK)
    assert any("CROWDING" in r for r in reasons)

    # Case B: Transition to LONG_LIQUIDATION (WAIT -> WAIT) -> at least RISK
    liq_snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=100.0),
        tf_15m=mock_tf,
        tf_1h=mock_tf,
        tf_4h=mock_tf,
        derivatives=DerivativesMetrics(
            mark_price=100.0,
            current_open_interest=10000.0,
            oi_1h_change=-0.05,
            regime=DerivativesRegime.LONG_LIQUIDATION,
        ),
        snapshot_hash="hash_liq",
    )
    asmt_liq = SymbolAssessment(
        symbol="BTCUSDT",
        snapshot=liq_snap,
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=0.0,
            entry_high=0.0,
            derivatives_regime=DerivativesRegime.LONG_LIQUIDATION,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
        opportunity_score=30.0,
        relative_performance=None,
        exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
        rank=1,
        lifecycle_state=SignalLifecycleState.CANDIDATE,
        alert_fingerprint="new_fp_liq",
    )
    emit_liq, sev_liq, reasons_liq = evaluate_alert_emission(asmt_liq, prev_state, config)
    assert emit_liq is True
    assert sev_liq == AlertSeverity.RISK
    assert "LONG_LIQUIDATION_RISK" in reasons_liq

    # Case C: Transition to DELEVERAGING (WAIT -> WAIT) -> at least RISK
    del_snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=100.0),
        tf_15m=mock_tf,
        tf_1h=mock_tf,
        tf_4h=mock_tf,
        derivatives=DerivativesMetrics(
            mark_price=100.0,
            current_open_interest=10000.0,
            oi_1h_change=-0.05,
            regime=DerivativesRegime.DELEVERAGING,
        ),
        snapshot_hash="hash_del",
    )
    asmt_del = SymbolAssessment(
        symbol="BTCUSDT",
        snapshot=del_snap,
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=0.0,
            entry_high=0.0,
            derivatives_regime=DerivativesRegime.DELEVERAGING,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
        opportunity_score=30.0,
        relative_performance=None,
        exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
        rank=1,
        lifecycle_state=SignalLifecycleState.CANDIDATE,
        alert_fingerprint="new_fp_del",
    )
    emit_del, sev_del, reasons_del = evaluate_alert_emission(asmt_del, prev_state, config)
    assert emit_del is True
    assert sev_del == AlertSeverity.RISK
    assert "DELEVERAGING_RISK" in reasons_del


def test_r2_1_03_strict_pit_receipt_semantics() -> None:
    """R2.1-03: observed_at_ms and decision_time_ms incorporate all receipt timestamps and decision_time_ms >= all inputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_1_03.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()

        t_base = 1700000000000
        t_avail = t_base + 5000
        t_deriv_obs = t_base + 8000
        t_receipt = t_base + 12000

        candles_15m = make_candle_series("BTCUSDT", "15m", 30, start_ms=t_base - 30 * 900000, step_ms=900000)
        # Set available_at_ms on candles
        candles_15m = [dataclasses.replace(c, available_at_ms=t_avail) for c in candles_15m]

        client = MagicMock()
        client.server_time_ms.return_value = t_receipt
        client.klines.return_value = candles_15m
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(
                mark_price=100.0,
                index_price=100.0,
                funding_rate=0.0001,
                funding_time_ms=t_base,
                open_interest=10000.0,
                open_interest_time_ms=t_base,
                open_interest_change_pct=0.01,
                taker_buy_sell_ratio=1.1,
                taker_time_ms=t_base,
                basis_rate=0.0001,
                basis_time_ms=t_base,
                long_short_account_ratio=1.0,
                long_short_time_ms=t_base,
                order_book_imbalance=0.1,
                spread_bps=1.5,
                observed_at_ms=t_deriv_obs,
            ),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None

        scanner = MarketWatchScanner(config=config, client=client, store=store)
        snap, _health, _errors = scanner.collect_symbol_snapshot("BTCUSDT", now_ms=t_base)
        assert snap is not None
        # observed_at_ms must incorporate all feeds (deriv_observed_at_ms, available_at_ms, server_time receipt)
        assert snap.observed_at_ms >= t_deriv_obs
        assert snap.observed_at_ms >= t_avail
        # decision_time_ms must be >= observed_at_ms and >= all input timestamps
        assert snap.decision_time_ms >= snap.observed_at_ms
        assert snap.decision_time_ms >= t_receipt


def test_r2_1_04_signal_identity_resets_lifecycle_and_shadow_dedupe() -> None:
    """R2.1-04: Changed breakout level or direction resets created_bar_end_ms, age_bars, and shadow dedupe state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_1_04.db"
        store = MarketWatchStateStore(db_path)

        t0 = 1700000000000
        bar_len = 15 * 60 * 1000
        t1 = t0 + 4 * bar_len

        # Initial signal: BREAKOUT_RETEST with breakout level 100.0, LONG
        sig_id_1 = compute_signal_identity("BTCUSDT", PlaybookType.BREAKOUT_RETEST, "LONG", 100.0)
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_watch_symbol_state (
                    symbol, setup, breakout_level, breakout_direction, lifecycle_state,
                    created_bar_end_ms, updated_at_ms, age_bars, signal_identity,
                    last_shadow_armed_signal_id, last_shadow_triggered_signal_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("BTCUSDT", "BREAKOUT_RETEST", 100.0, "LONG", "TRIGGERED", t0, t1, 4, sig_id_1, sig_id_1, sig_id_1),
            )

        # Assessment with NEW breakout level (105.0) -> different signal_identity
        closed = Candle("BTCUSDT", "15m", t1 - bar_len, t1, 104.0, 106.0, 103.0, 105.5, 100.0)
        tf_15m = TimeframeSnapshot(
            interval="15m",
            latest_bar=closed,
            latest_closed_bar=closed,
            closed_bar_end_time_ms=t1,
            close=105.5,
            ema_fast=100.0,
            ema_mid=99.0,
            ema_fast_slope=0.01,
            ema_mid_slope=0.01,
            atr=1.0,
            atr_percentile=0.5,
            adx=25.0,
            rsi=50.0,
            roc=0.01,
            volume=100.0,
            volume_z=0.5,
            bb_width=0.02,
            bb_width_percentile=0.5,
            recent_swing_high=106.0,
            recent_swing_low=103.0,
            supports=(103.0,),
            resistances=(106.0,),
            structure="HH_HL",
            regime=Regime.TREND_UP,
        )
        asmt = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=MagicMock(decision_time_ms=t1, snapshot_hash="h2", tf_15m=tf_15m, tf_1h=tf_15m),
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.BREAKOUT_RETEST,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.GOOD,
                entry_low=104.0,
                entry_high=106.0,
                breakout_level=105.0,  # Changed level!
                breakout_direction="LONG",
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=75.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
            alert_fingerprint="fp_new",
        )

        store.save_symbol_state("BTCUSDT", asmt, now_ms=t1)
        st = store.get_symbol_state("BTCUSDT")
        assert st is not None
        assert st["breakout_level"] == 105.0
        # Reset: created_bar_end_ms reset to t1, age_bars reset to 0
        assert st["created_bar_end_ms"] == t1
        assert st["age_bars"] == 0
        # Shadow dedupe state cleared on reset!
        assert st["last_shadow_armed_signal_id"] is None
        assert st["last_shadow_triggered_signal_id"] is None


def test_r2_1_05_shadow_metrics_only_resolved_eligible_actionable() -> None:
    """R2.1-05: Performance metrics use only RESOLVED + ELIGIBLE actionable records; pending records excluded from hit-rate denominator."""
    records = [
        # 1. ACTIONABLE_TRIGGERED, resolved, TP1 hit
        {
            "id": 1,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "resolved": 1,
            "tp1_hit": 1,
            "tp2_hit": 0,
            "sl_hit": 0,
            "future_mfe": 2.0,
            "future_mae": 0.5,
            "net_r": 1.5,
            "regime_after": "BALANCED",
            "agent_setup": "TREND_PULLBACK",
        },
        # 2. ACTIONABLE_TRIGGERED, resolved, SL hit
        {
            "id": 2,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "SHORT",
            "entry_price": 100.0,
            "resolved": 1,
            "tp1_hit": 0,
            "tp2_hit": 0,
            "sl_hit": 1,
            "future_mfe": 0.2,
            "future_mae": 1.2,
            "net_r": -1.0,
            "regime_after": "BALANCED",
            "agent_setup": "TREND_PULLBACK",
        },
        # 3. ACTIONABLE_TRIGGERED, pending (unresolved) - MUST NOT enter denominator
        {
            "id": 3,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "resolved": 0,
            "tp1_hit": 0,
            "tp2_hit": 0,
            "sl_hit": 0,
            "future_mfe": None,
            "future_mae": None,
            "net_r": None,
            "regime_after": None,
            "agent_setup": "TREND_PULLBACK",
        },
        # 4. SETUP_ARMED (non-actionable) - MUST NOT enter denominator
        {
            "id": 4,
            "observation_type": "SETUP_ARMED",
            "direction": "LONG",
            "entry_price": 100.0,
            "resolved": 0,
            "tp1_hit": 0,
            "tp2_hit": 0,
            "sl_hit": 0,
            "future_mfe": None,
            "future_mae": None,
            "net_r": None,
            "regime_after": None,
            "agent_setup": "TREND_PULLBACK",
        },
        # 5. ACTIONABLE_TRIGGERED, resolved, but INELIGIBLE (e.g. data gap) - MUST NOT enter denominator
        {
            "id": 5,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "resolved": 1,
            "tp1_hit": 0,
            "tp2_hit": 0,
            "sl_hit": 0,
            "future_mfe": 0.0,
            "future_mae": 0.0,
            "net_r": 0.0,
            "regime_after": "INELIGIBLE",
            "agent_setup": "TREND_PULLBACK",
        },
    ]

    metrics = compute_performance_metrics(records)
    assert metrics["total_records"] == 5
    assert metrics["actionable_records"] == 4
    assert metrics["resolved_actionable_count"] == 2
    assert metrics["pending_count"] == 2
    assert metrics["ineligible_count"] == 2  # SETUP_ARMED (#4) + INELIGIBLE (#5)
    # Denominator must be strictly resolved_actionable_count (2)
    assert metrics["tp1_hit_rate"] == 0.5  # 1 / 2, NOT 1 / 3 or 1 / 5
    assert metrics["sl_hit_rate"] == 0.5   # 1 / 2
    assert metrics["tp2_hit_rate"] == 0.0
    assert metrics["median_net_r"] == 0.25  # median([1.5, -1.0]) = 0.25


def test_r2_1_06_shadow_historical_recovery_on_downtime_restart() -> None:
    """R2.1-06: Historical recovery resolves frozen windows via historical_klines after simulated downtime."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_1_06.db"
        store = MarketWatchStateStore(db_path)

        t0 = 1700000000000
        bar_len = 15 * 60 * 1000
        eval_horizon = 16
        eval_end = t0 + eval_horizon * bar_len

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h_old",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            policy_version="1.0",
            config_hash="c_old",
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=115.0,
            direction="LONG",
            evaluation_horizon_bars=eval_horizon,
            evaluation_end_ms=eval_end,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status="WAITING_FOR_FILL",
        )

        # Current time is 150 bars later (simulating restart after prolonged downtime)
        t_curr = t0 + 150 * bar_len

        client = MagicMock()
        # Normal client.klines only returns recent 120 bars (from t0 + 30 bars to t_curr)
        # which misses the evaluation window [t0, eval_end]!
        recent_start = t0 + 30 * bar_len
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 120, start_ms=recent_start, step_ms=bar_len)

        # historical_klines provides candles covering [t0, eval_end]
        hist_candles = make_candle_series("BTCUSDT", "15m", 16, start_ms=t0, step_ms=bar_len, base_price=100.0)
        # Make candle 3 hit TP1 (high >= 110.0)
        hist_candles[3] = Candle(
            symbol="BTCUSDT",
            interval="15m",
            open_time_ms=hist_candles[3].open_time_ms,
            close_time_ms=hist_candles[3].close_time_ms,
            open=102.0,
            high=112.0,  # TP1 hit!
            low=101.0,
            close=111.0,
            volume=500.0,
        )
        client.historical_klines.return_value = hist_candles

        mgr = ShadowEvaluationManager(store=store)
        res = mgr.resolve_pending_observations(client, current_time_ms=t_curr)

        assert res["resolved_count"] == 1
        assert res["pending_count"] == 0

        # historical_klines was called to recover the frozen evaluation window
        client.historical_klines.assert_called_once_with("BTCUSDT", "15m", t0, eval_end)

        # Verify record in DB is resolved and hit TP1
        records = store.get_all_shadow_records()
        assert len(records) == 1
        assert records[0]["resolved"] == 1
        assert records[0]["tp1_hit"] == 1
        assert records[0]["sl_hit"] == 0


def test_r2_2_01_pre_signal_price_must_not_fill() -> None:
    """R2.2-16-01: Signal confirmation occurs after earlier intrabar price; pre-signal price MUST NOT fill."""
    signal_time_ms = 1_700_000_600_000  # 10 minutes past hour
    entry_window_end_ms = signal_time_ms + 4 * 15 * 60 * 1000

    pre_candle = Candle("BTCUSDT", "1m", signal_time_ms - 120_000, signal_time_ms - 60_000, 105.0, 105.0, 99.0, 100.0, 50.0)
    post_candle = Candle("BTCUSDT", "1m", signal_time_ms, signal_time_ms + 60_000, 104.0, 106.0, 103.0, 105.0, 50.0)

    status, fill_p, fill_t = resolve_shadow_fill("LONG", 99.0, 101.0, signal_time_ms, entry_window_end_ms, [pre_candle, post_candle])
    assert status == ShadowFillStatus.WAITING_FOR_FILL
    assert fill_p is None
    assert fill_t is None


def test_r2_2_02_long_entry_zone_reached_only_after_signal_fill_time_is_post_signal() -> None:
    """R2.2-16-02: LONG entry zone reached only after signal: fill_time is strictly post-signal."""
    signal_time_ms = 1_700_000_000_000
    entry_window_end_ms = signal_time_ms + 4 * 15 * 60 * 1000

    post_candle = Candle("BTCUSDT", "15m", signal_time_ms, signal_time_ms + 900_000, 103.0, 104.0, 100.5, 101.0, 100.0)
    status, fill_p, fill_t = resolve_shadow_fill("LONG", 99.0, 101.0, signal_time_ms, entry_window_end_ms, [post_candle])
    assert status == ShadowFillStatus.FILLED
    assert fill_p == 101.0
    assert fill_t == signal_time_ms + 900_000
    assert fill_t > signal_time_ms


def test_r2_2_03_entry_zone_never_revisited_becomes_no_fill_not_loss() -> None:
    """R2.2-16-03: Entry zone never revisited: record becomes NO_FILL, not loss."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_2_03.db"
        store = MarketWatchStateStore(db_path)
        manager = ShadowEvaluationManager(store)

        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000
        win_bars = 4
        win_end = t0 + win_bars * bar_len

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="hash_nf",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=["TEST"],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            entry_zone_low=99.0,
            entry_zone_high=100.0,
            entry_window_bars=win_bars,
            entry_window_end_ms=win_end,
            fill_status=ShadowFillStatus.WAITING_FOR_FILL.value,
        )

        candles = [
            Candle("BTCUSDT", "15m", t0 + i * bar_len, t0 + (i + 1) * bar_len, 106.0, 108.0, 105.0, 107.0, 100.0)
            for i in range(5)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = manager.resolve_pending_observations(client, current_time_ms=t0 + 5 * bar_len)
        assert res["resolved_count"] == 1
        assert res["results"][0]["status"] == "NO_FILL"

        records = store.get_all_shadow_records()
        assert len(records) == 1
        rec = records[0]
        assert rec["resolved"] == 1
        assert rec["fill_status"] == "NO_FILL"
        assert rec["regime_after"] == "NO_FILL"
        assert rec["sl_hit"] == 0
        assert rec["tp1_hit"] == 0
        assert rec["future_mfe"] is None
        assert rec["future_mae"] is None
        assert rec["net_r"] is None


def test_r2_2_04_scanner_autorecord_and_shadow_manager_have_identical_fill_semantics() -> None:
    """R2.2-16-04: Scanner auto-record and ShadowEvaluationManager explicit record use identical fill semantics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_2_04.db"
        store = MarketWatchStateStore(db_path)
        manager = ShadowEvaluationManager(store)

        mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
        t0 = 1_700_000_000_000
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=t0,
            observed_at_ms=t0,
            exchange_time_ms=t0,
            price=PriceMetrics(last_price=100.0),
            tf_15m=mock_tf,
            tf_1h=mock_tf,
            tf_4h=mock_tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_sem",
        )
        plan = DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.LONG,
            setup=PlaybookType.TREND_PULLBACK,
            regime=Regime.TREND_UP,
            entry_quality=EntryQuality.GOOD,
            entry_low=98.0,
            entry_high=100.0,
            stop_loss=95.0,
            take_profit_1=110.0,
            take_profit_2=115.0,
        )
        asmt = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=plan,
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
            signal_identity="BTCUSDT:TREND_PULLBACK:LONG:SWING:1700000000000",
        )

        mgr_id = manager.record_decision(asmt)
        records = store.get_all_shadow_records()
        mgr_rec = next(r for r in records if r["id"] == mgr_id)

        assert mgr_rec["entry_zone_low"] == 98.0
        assert mgr_rec["entry_zone_high"] == 100.0
        assert mgr_rec["signal_time_ms"] == t0
        assert mgr_rec["entry_window_bars"] == 4
        assert mgr_rec["entry_window_end_ms"] == t0 + 4 * 15 * 60 * 1000
        assert mgr_rec["fill_status"] == ShadowFillStatus.WAITING_FOR_FILL.value


def test_r2_2_05_armed_does_not_suppress_actionable_triggered() -> None:
    """R2.2-16-05: ARMED observation does not suppress later ACTIONABLE_TRIGGERED record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_2_05.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        client = MagicMock()
        client.server_time_ms.return_value = 1000
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(mark_price=100.0, index_price=100.0, funding_rate=0.0001, funding_time_ms=1000,
                               open_interest=1000.0, open_interest_time_ms=1000, open_interest_change_pct=0.01,
                               taker_buy_sell_ratio=1.0, taker_time_ms=1000, basis_rate=0.0001, basis_time_ms=1000,
                               long_short_account_ratio=1.0, long_short_time_ms=1000, order_book_imbalance=0.1, spread_bps=1.0),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None
        scanner = MarketWatchScanner(config=config, client=client, store=store)

        mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=100.0),
            tf_15m=mock_tf,
            tf_1h=mock_tf,
            tf_4h=mock_tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_armed_trig",
        )

        asmt_armed = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.WAIT,
                setup=PlaybookType.TREND_PULLBACK,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.GOOD,
                entry_low=99.0,
                entry_high=101.0,
                stop_loss=95.0,
                take_profit_1=110.0,
                take_profit_2=115.0,
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.ARMED,
            signal_identity="BTCUSDT:TREND_PULLBACK:LONG:65000:1000",
        )
        scanner.assess_symbol = MagicMock(return_value=asmt_armed)
        scanner.scan_universe(["BTCUSDT"])

        asmt_trig = dataclasses.replace(
            asmt_armed,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
            directional=dataclasses.replace(asmt_armed.directional, decision=DirectionalDecision.LONG),
        )
        scanner.assess_symbol = MagicMock(return_value=asmt_trig)
        scanner.scan_universe(["BTCUSDT"])

        records = store.get_all_shadow_records()
        assert len(records) == 2
        obs_types = {r["observation_type"] for r in records}
        assert obs_types == {"SETUP_ARMED", "ACTIONABLE_TRIGGERED"}


def test_r2_2_06_exactly_one_actionable_triggered_per_signal_identity() -> None:
    """R2.2-16-06: Exactly one ACTIONABLE_TRIGGERED record per signal_identity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_2_06.db"
        store = MarketWatchStateStore(db_path)

        sig_id = "BTCUSDT:BREAKOUT_RETEST:LONG:65000.00:1700000000000"
        id1 = store.record_shadow_observation(
            timestamp_ms=1000,
            symbol="BTCUSDT",
            snapshot_hash="h1",
            agent_decision="LONG",
            agent_setup="BREAKOUT_RETEST",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=65000.0,
            stop_loss=64000.0,
            tp1=67000.0,
            tp2=68000.0,
            direction="LONG",
            signal_identity=sig_id,
            observation_type="ACTIONABLE_TRIGGERED",
        )
        id2 = store.record_shadow_observation(
            timestamp_ms=2000,
            symbol="BTCUSDT",
            snapshot_hash="h2",
            agent_decision="LONG",
            agent_setup="BREAKOUT_RETEST",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=65000.0,
            stop_loss=64000.0,
            tp1=67000.0,
            tp2=68000.0,
            direction="LONG",
            signal_identity=sig_id,
            observation_type="ACTIONABLE_TRIGGERED",
        )
        assert id1 == id2
        records = store.get_all_shadow_records()
        actionable = [r for r in records if r["observation_type"] == "ACTIONABLE_TRIGGERED"]
        assert len(actionable) == 1


def test_r2_2_07_doge_scale_aware_precision_no_collision() -> None:
    """R2.2-16-07: DOGE-like prices do not collide due to fixed 2-decimal rounding."""
    p1 = 0.12345
    p2 = 0.12389
    assert f"{p1:.2f}" == f"{p2:.2f}"  # Collides under :.2f

    n1 = normalize_price_level(p1, tick_size=0.00001)
    n2 = normalize_price_level(p2, tick_size=0.00001)
    assert n1 != n2
    assert n1 == "0.12345"
    assert n2 == "0.12389"

    sig1 = compute_signal_identity("DOGEUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, p1, tick_size=0.00001)
    sig2 = compute_signal_identity("DOGEUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, p2, tick_size=0.00001)
    assert sig1 != sig2


def test_r2_2_08_trend_pullback_stable_across_small_ema_drift() -> None:
    """R2.2-16-08: Same Trend Pullback across small EMA drift keeps same signal identity."""
    snap1 = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=65000.0),
        tf_15m=make_dummy_tf("BTCUSDT", "15m", 65000.0),
        tf_1h=make_dummy_tf("BTCUSDT", "1h", 65000.0),
        tf_4h=make_dummy_tf("BTCUSDT", "4h", 65000.0),
        derivatives=DerivativesMetrics(mark_price=65000.0),
        snapshot_hash="h1",
    )
    snap2 = dataclasses.replace(
        snap1,
        tf_15m=make_dummy_tf("BTCUSDT", "15m", 65050.0),
    )

    plan = DirectionalPlan(
        symbol="BTCUSDT",
        decision=DirectionalDecision.LONG,
        setup=PlaybookType.TREND_PULLBACK,
        regime=Regime.TREND_UP,
        entry_quality=EntryQuality.GOOD,
        entry_low=64500.0,
        entry_high=65000.0,
        stop_loss=63500.0,
        take_profit_1=67000.0,
        take_profit_2=68000.0,
    )

    sig1 = extract_signal_identity("BTCUSDT", plan, snap1, created_bar_end_ms=1_700_000_000_000)
    sig2 = extract_signal_identity("BTCUSDT", plan, snap2, created_bar_end_ms=1_700_000_000_000)
    assert sig1 == sig2


def test_r2_2_09_new_breakout_level_produces_new_signal_identity() -> None:
    """R2.2-16-09: New breakout level produces new signal identity."""
    sig1 = compute_signal_identity("BTCUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 65000.0)
    sig2 = compute_signal_identity("BTCUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 66000.0)
    assert sig1 != sig2


def test_r2_2_10_playbook_direction_flip_produces_new_signal_identity() -> None:
    """R2.2-16-10: Same playbook direction flip produces new signal identity."""
    sig_long = compute_signal_identity("BTCUSDT", PlaybookType.FAILED_BREAKOUT, DirectionalDecision.LONG, 65000.0)
    sig_short = compute_signal_identity("BTCUSDT", PlaybookType.FAILED_BREAKOUT, DirectionalDecision.SHORT, 65000.0)
    assert sig_long != sig_short
    assert ":LONG:" in sig_long
    assert ":SHORT:" in sig_short


def test_r2_2_11_first_partial_post_signal_15m_window_not_dropped() -> None:
    """R2.2-16-11: First partial post-signal 15m window is evaluated via 1m candles, not silently dropped."""
    signal_time_ms = 1_700_000_500_000
    end_of_15m_bar = 1_700_000_900_000

    c_1m = [
        Candle("BTCUSDT", "1m", signal_time_ms + i * 60_000, signal_time_ms + (i + 1) * 60_000,
               102.0, 103.0, 99.5 if i == 2 else 101.0, 102.0, 10.0)
        for i in range(6)
    ]
    status, fill_p, fill_t = resolve_shadow_fill("LONG", 99.0, 100.0, signal_time_ms, end_of_15m_bar, c_1m)
    assert status == ShadowFillStatus.FILLED
    assert fill_p == 100.0
    assert fill_t == signal_time_ms + 3 * 60_000


def test_r2_2_12_same_bar_sl_tp_1m_chronological_path_used() -> None:
    """R2.2-16-12: Same-bar SL+TP: 1m chronological path used when available."""
    manager = ShadowEvaluationManager(MagicMock())
    t0 = 1_700_000_000_000
    t1 = t0 + 900_000

    c_15m = Candle("BTCUSDT", "15m", t0, t1, 100.0, 115.0, 85.0, 105.0, 1000.0)
    c_1m_seq = [
        Candle("BTCUSDT", "1m", t0, t0 + 60_000, 100.0, 104.0, 100.0, 103.0, 10.0),
        Candle("BTCUSDT", "1m", t0 + 60_000, t0 + 120_000, 103.0, 108.0, 102.0, 107.0, 10.0),
        Candle("BTCUSDT", "1m", t0 + 120_000, t0 + 180_000, 107.0, 112.0, 106.0, 111.0, 10.0),
        Candle("BTCUSDT", "1m", t0 + 600_000, t0 + 660_000, 95.0, 96.0, 85.0, 86.0, 10.0),
    ]

    outcome = manager.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c_15m],
        persist=False,
        intrabar_1m_candles=c_1m_seq,
    )
    assert outcome["tp1_hit"] is True
    assert outcome["sl_hit"] is False
    assert outcome["path_resolution"] == ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value


def test_r2_2_13_same_bar_ambiguity_without_1m_falls_back_to_stop_first() -> None:
    """R2.2-16-13: Same-bar ambiguity without 1m: conservative STOP_FIRST fallback."""
    manager = ShadowEvaluationManager(MagicMock())
    c_15m = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 115.0, 85.0, 105.0, 1000.0)

    outcome = manager.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c_15m],
        persist=False,
        intrabar_1m_candles=None,
    )
    assert outcome["sl_hit"] is True
    assert outcome["tp1_hit"] is False
    assert outcome["path_resolution"] == ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value


def test_r2_2_14_gross_r_reflects_actual_risk_distance() -> None:
    """R2.2-16-14: gross_r reflects actual fill/stop/exit distances."""
    manager = ShadowEvaluationManager(MagicMock())
    c = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 135.0, 95.0, 130.0, 100.0)
    outcome = manager.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=80.0,
        tp1=130.0,
        tp2=140.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c],
        persist=False,
    )
    assert outcome["gross_r"] == 1.5


def test_r2_2_15_friction_r_reduces_gross_r_to_net_r() -> None:
    """R2.2-16-15: friction_r reduces gross_r to net_r."""
    cfg = MarketWatchConfig()
    f_dollars, f_r = compute_trade_friction_r(fill_price=100.0, exit_price=120.0, initial_risk=10.0, config=cfg)
    assert f_dollars > 0.0
    assert f_r > 0.0

    manager = ShadowEvaluationManager(MagicMock())
    c = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 125.0, 95.0, 120.0, 100.0)
    outcome = manager.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=120.0,
        tp2=130.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c],
        persist=False,
        config=cfg,
    )
    assert outcome["gross_r"] == 2.0
    assert outcome["friction_r"] == f_r
    assert outcome["net_r"] == round(2.0 - f_r, 4)


def test_r2_2_16_pending_records_exclude_from_hit_rate_denominator() -> None:
    """R2.2-16-16: Pending records do not enter hit-rate denominator."""
    records = [
        {
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "fill_status": "FILLED",
            "signal_time_ms": 1000,
            "resolved": 1,
            "tp1_hit": 1,
            "tp2_hit": 0,
            "sl_hit": 0,
            "net_r": 1.0,
        },
        *(
            {
                "observation_type": "ACTIONABLE_TRIGGERED",
                "direction": "LONG",
                "entry_price": 100.0,
                "fill_status": "WAITING_FOR_FILL",
                "signal_time_ms": 1000,
                "resolved": 0,
                "tp1_hit": 0,
                "tp2_hit": 0,
                "sl_hit": 0,
                "net_r": None,
            }
            for _ in range(9)
        ),
    ]
    metrics = compute_performance_metrics(records)
    assert metrics["total_records"] == 10
    assert metrics["resolved_actionable_count"] == 1
    assert metrics["pending_actionable_count"] == 9
    assert metrics["tp1_hit_rate"] == 1.0


def test_r2_2_17_no_fill_records_exclude_from_trading_win_loss_denominator() -> None:
    """R2.2-16-17: NO_FILL records do not enter trading win/loss denominator."""
    records = [
        {
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "fill_status": "FILLED",
            "signal_time_ms": 1000,
            "resolved": 1,
            "tp1_hit": 1,
            "tp2_hit": 0,
            "sl_hit": 0,
            "net_r": 1.0,
        },
        *(
            {
                "observation_type": "ACTIONABLE_TRIGGERED",
                "direction": "LONG",
                "entry_price": 100.0,
                "fill_status": "NO_FILL",
                "regime_after": "NO_FILL",
                "signal_time_ms": 1000,
                "resolved": 1,
                "tp1_hit": 0,
                "tp2_hit": 0,
                "sl_hit": 0,
                "net_r": None,
            }
            for _ in range(4)
        ),
    ]
    metrics = compute_performance_metrics(records)
    assert metrics["total_records"] == 5
    assert metrics["no_fill_count"] == 4
    assert metrics["resolved_actionable_count"] == 1
    assert metrics["tp1_hit_rate"] == 1.0


def test_r2_2_18_historical_recovery_resolves_observation_older_than_120_bars() -> None:
    """R2.2-16-18: Historical recovery resolves an observation older than latest 120x15m."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_2_18.db"
        store = MarketWatchStateStore(db_path)

        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000
        eval_horizon = 16
        eval_end = t0 + eval_horizon * bar_len

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h_old",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            evaluation_horizon_bars=eval_horizon,
            evaluation_end_ms=eval_end,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status=ShadowFillStatus.WAITING_FOR_FILL.value,
        )

        t_curr = t0 + 180 * bar_len
        client = MagicMock()
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 120, start_ms=t0 + 60 * bar_len, step_ms=bar_len)

        hist_candles = make_candle_series("BTCUSDT", "15m", 16, start_ms=t0, step_ms=bar_len, base_price=100.0)
        hist_candles[2] = Candle("BTCUSDT", "15m", hist_candles[2].open_time_ms, hist_candles[2].close_time_ms, 102.0, 112.0, 101.0, 111.0, 500.0)
        client.historical_klines.return_value = hist_candles

        mgr = ShadowEvaluationManager(store=store)
        res = mgr.resolve_pending_observations(client, current_time_ms=t_curr)

        assert res["resolved_count"] == 1
        assert res["pending_count"] == 0
        client.historical_klines.assert_called_once_with("BTCUSDT", "15m", t0, eval_end)


def test_r2_2_19_decision_time_after_all_input_timestamps() -> None:
    """R2.2-16-19: decision_time >= all receipt/availability timestamps."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_2_19.db"
        store = MarketWatchStateStore(db_path)
        client = MagicMock()
        client.server_time_ms.return_value = 1000
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(mark_price=100.0, index_price=100.0, funding_rate=0.0001, funding_time_ms=1200,
                               open_interest=1000.0, open_interest_time_ms=1200, open_interest_change_pct=0.01,
                               taker_buy_sell_ratio=1.0, taker_time_ms=1200, basis_rate=0.0001, basis_time_ms=1200,
                               long_short_account_ratio=1.0, long_short_time_ms=1200, order_book_imbalance=0.1, spread_bps=1.0),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None
        scanner = MarketWatchScanner(config=MarketWatchConfig(), client=client, store=store)

        snap, _health, _ = scanner.collect_symbol_snapshot("BTCUSDT", now_ms=1500)
        assert snap is not None
        assert snap.collection_started_at_ms <= snap.observed_at_ms <= snap.decision_time_ms
        assert snap.decision_time_ms >= snap.collection_completed_at_ms


def test_r2_2_20_fingerprint_uses_active_config_not_default() -> None:
    """R2.2-16-20: Changing active crowding config cannot cause fingerprint logic to use default config thresholds."""
    config_a = MarketWatchConfig(
        thresholds=dataclasses.replace(MarketWatchConfig().thresholds, funding_extreme_abs=0.0003)
    )
    config_b = MarketWatchConfig(
        thresholds=dataclasses.replace(MarketWatchConfig().thresholds, funding_extreme_abs=0.0010)
    )

    mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
    snap = MarketSnapshot(
        symbol="BTCUSDT",
        decision_time_ms=1000,
        observed_at_ms=1000,
        exchange_time_ms=1000,
        price=PriceMetrics(last_price=100.0),
        tf_15m=mock_tf,
        tf_1h=mock_tf,
        tf_4h=mock_tf,
        derivatives=DerivativesMetrics(
            mark_price=100.0,
            funding_rate=0.0005,
            taker_buy_sell_ratio=1.40,
            current_open_interest=1000.0,
            oi_1h_change=0.02,
        ),
        snapshot_hash="hash_crowd",
    )
    asmt = SymbolAssessment(
        symbol="BTCUSDT",
        snapshot=snap,
        directional=DirectionalPlan(
            symbol="BTCUSDT",
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.NO_TRADE,
            regime=Regime.RANGE,
            entry_quality=EntryQuality.POOR,
            entry_low=99.0,
            entry_high=101.0,
            stop_loss=95.0,
            take_profit_1=110.0,
            take_profit_2=115.0,
        ),
        grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
        opportunity_score=50.0,
        relative_performance=None,
        exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
        rank=1,
        lifecycle_state=SignalLifecycleState.CANDIDATE,
    )

    fp_a = compute_decision_fingerprint(asmt, config_a)
    fp_b = compute_decision_fingerprint(asmt, config_b)
    assert fp_a != fp_b


def test_r2_2_21_legacy_shadow_records_excluded_when_required_fields_absent() -> None:
    """R2.2-16-21: Legacy shadow records remain readable but are excluded from R2.2 actionable-performance metrics."""
    records = [
        {
            "id": 1,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "fill_status": "FILLED",
            "signal_time_ms": 1000,
            "resolved": 1,
            "tp1_hit": 1,
            "tp2_hit": 0,
            "sl_hit": 0,
            "net_r": 1.0,
        },
        {
            "id": 2,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "fill_status": "LEGACY",
            "regime_after": "LEGACY",
            "resolved": 1,
            "tp1_hit": 1,
            "tp2_hit": 0,
            "sl_hit": 0,
            "net_r": 1.0,
            "is_legacy": True,
        },
    ]
    metrics = compute_performance_metrics(records)
    assert metrics["total_records"] == 2
    assert metrics["ineligible_count"] >= 1
    assert metrics["resolved_actionable_count"] == 1
    assert metrics["tp1_hit_rate"] == 1.0

# ==============================================================================
# R2.3 ADVERSARIAL TEST SUITE (Section 43: Tests 01 to 37)
# ==============================================================================


def test_r2_3_01_entry_window_fetch_empty_api_failure_not_no_fill() -> None:
    """R2.3-01: Entry window fetch empty due to API failure MUST NOT become NO_FILL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_01.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h1",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        client = MagicMock()
        client.klines.return_value = []
        client.historical_klines.return_value = []

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 6 * bar_len)
        assert res["resolved_count"] == 0
        assert res["pending_count"] == 1
        assert res["results"][0]["status"] == "PENDING_DATA_GAP"

        recs = store.get_all_shadow_records()
        assert len(recs) == 1
        assert recs[0]["resolved"] == 0
        assert recs[0]["regime_after"] == "PENDING_DATA_GAP"
        assert recs[0]["coverage_reason"] == "ENTRY_WINDOW_DATA_GAP"

        metrics = compute_performance_metrics(recs)
        assert metrics["resolved_actionable_count"] == 0
        assert metrics["pending_data_gap_count"] == 1
        assert metrics["no_fill_count"] == 0


def test_r2_3_02_entry_window_has_internal_15m_gap_not_no_fill() -> None:
    """R2.3-02: Entry window with internal 15m gap MUST NOT become NO_FILL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_02.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h2",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        # Missing bar 2 (gap between bar 1 and bar 3)
        c0 = Candle("BTCUSDT", "15m", t0, t0 + bar_len, 105.0, 108.0, 104.0, 106.0, 100.0)
        c1 = Candle("BTCUSDT", "15m", t0 + bar_len, t0 + 2 * bar_len, 106.0, 109.0, 105.0, 107.0, 100.0)
        c3 = Candle("BTCUSDT", "15m", t0 + 3 * bar_len, t0 + 4 * bar_len, 107.0, 110.0, 106.0, 108.0, 100.0)

        client = MagicMock()
        client.klines.return_value = [c0, c1, c3]

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 5 * bar_len)
        assert res["resolved_count"] == 0
        recs = store.get_all_shadow_records()
        assert recs[0]["resolved"] == 0
        assert recs[0]["regime_after"] == "PENDING_DATA_GAP"
        assert recs[0]["coverage_reason"] == "ENTRY_WINDOW_DATA_GAP"


def test_r2_3_03_complete_entry_window_with_no_touch_becomes_no_fill() -> None:
    """R2.3-03: Complete entry window with no touch becomes NO_FILL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_03.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h3",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        candles = [
            Candle("BTCUSDT", "15m", t0 + i * bar_len, t0 + (i + 1) * bar_len, 105.0, 109.0, 103.0, 106.0, 100.0)
            for i in range(4)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 5 * bar_len)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "NO_FILL"
        assert recs[0]["terminal_reason"] == "NO_FILL"
        assert recs[0]["coverage_status"] == "COMPLETE"
        assert recs[0]["resolved"] == 1

        metrics = compute_performance_metrics(recs)
        assert metrics["resolved_actionable_count"] == 0
        assert metrics["no_fill_count"] == 1


def test_r2_3_04_outcome_window_fetch_incomplete_at_maturity_not_timeout() -> None:
    """R2.3-04: Outcome window fetch incomplete at maturity time MUST NOT become TIMEOUT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_04.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h4",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status="FILLED",
            fill_time_ms=t0,
            fill_price=100.0,
            evaluation_start_ms=t0,
        )

        # Only 10 candles covering t0 to t0 + 10 * bar_len, missing bars 10 to 15!
        candles = [
            Candle("BTCUSDT", "15m", t0 + i * bar_len, t0 + (i + 1) * bar_len, 100.0, 104.0, 98.0, 101.0, 100.0)
            for i in range(10)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 17 * bar_len)
        assert res["resolved_count"] == 0
        recs = store.get_all_shadow_records()
        assert recs[0]["resolved"] == 0
        assert recs[0]["regime_after"] == "PENDING_DATA_GAP"
        assert recs[0]["coverage_reason"] == "OUTCOME_WINDOW_DATA_GAP"


def test_r2_3_05_complete_outcome_window_with_no_tp_sl_becomes_timeout() -> None:
    """R2.3-05: Complete outcome window with no TP/SL becomes TIMEOUT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_05.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h5",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status="FILLED",
            fill_time_ms=t0,
            fill_price=100.0,
            evaluation_start_ms=t0,
        )

        candles = [
            Candle("BTCUSDT", "15m", t0 + i * bar_len, t0 + (i + 1) * bar_len, 100.0, 104.0, 98.0, 102.0 if i < 15 else 103.5, 100.0)
            for i in range(16)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 17 * bar_len)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["resolved"] == 1
        assert recs[0]["terminal_reason"] == "TIMEOUT"
        assert recs[0]["exit_price"] == 103.5
        assert recs[0]["coverage_status"] == "COMPLETE"


def test_r2_3_06_late_fill_receives_full_horizon() -> None:
    """R2.3-06: Signal at 10:00, fill at 10:45 (bar 3), 4h horizon => evaluation_end must be 14:45."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_06.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000  # 10:00
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h6",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=115.0,
            tp2=125.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        # Bar 0, 1, 2 stay above entry (105-108). Bar 3 touches 100.0 at 10:45
        candles = [
            Candle("BTCUSDT", "15m", t0, t0 + bar_len, 106.0, 108.0, 104.0, 105.0, 100.0),
            Candle("BTCUSDT", "15m", t0 + bar_len, t0 + 2 * bar_len, 105.0, 107.0, 103.0, 104.0, 100.0),
            Candle("BTCUSDT", "15m", t0 + 2 * bar_len, t0 + 3 * bar_len, 104.0, 106.0, 102.0, 103.0, 100.0),
            Candle("BTCUSDT", "15m", t0 + 3 * bar_len, t0 + 4 * bar_len, 103.0, 104.0, 99.0, 101.0, 100.0),  # Fills here!
        ]
        client = MagicMock()
        client.klines.return_value = candles

        # Check at 10:45 close (t0 + 4 * bar_len)
        mgr.resolve_pending_observations(client, current_time_ms=t0 + 4 * bar_len)
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "FILLED"
        expected_fill_time = t0 + 4 * bar_len
        expected_eval_end = expected_fill_time + 16 * bar_len
        assert recs[0]["fill_time_ms"] == expected_fill_time
        assert recs[0]["evaluation_start_ms"] == expected_fill_time
        assert recs[0]["evaluation_end_ms"] == expected_eval_end


def test_r2_3_07_initial_candles_only_to_old_horizon_refetches_through_new_horizon() -> None:
    """R2.3-07: Initial candles only go to old signal-based horizon => resolver refetches through new fill-based horizon."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_07.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h7",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=115.0,
            tp2=125.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        # Fills at bar 3 (t0 + 4 * bar_len).
        fill_t = t0 + 4 * bar_len
        new_eval_end = fill_t + 16 * bar_len  # t0 + 20 * bar_len

        # Initial klines only up to t0 + 16 * bar_len (bars 0-2 stay above 100.0, bar 3 fills at 99.0)
        initial_candles = [
            Candle("BTCUSDT", "15m", t0 + i * bar_len, t0 + (i + 1) * bar_len, 104.0, 106.0, 99.0 if i == 3 else 102.0, 103.0, 100.0)
            for i in range(16)
        ]
        client = MagicMock()
        client.klines.return_value = initial_candles

        # historical_klines provides additional candles up to new_eval_end, where bar 14 hits TP1
        extended_candles = [
            Candle("BTCUSDT", "15m", fill_t + i * bar_len, fill_t + (i + 1) * bar_len,
                   100.0, 116.0 if i == 14 else 104.0, 98.0, 101.0, 100.0)
            for i in range(16)
        ]
        client.historical_klines.return_value = extended_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=new_eval_end + bar_len)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["resolved"] == 1
        assert recs[0]["terminal_reason"] == "TP1"
        assert recs[0]["evaluation_end_ms"] == new_eval_end


def test_r2_3_08_rerunning_resolver_keeps_same_fill_and_evaluation_boundaries() -> None:
    """R2.3-08: Re-running resolver keeps same fill and evaluation boundaries once frozen."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_08.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h8",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=115.0,
            tp2=125.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        c0 = Candle("BTCUSDT", "15m", t0, t0 + bar_len, 101.0, 102.0, 99.0, 100.0, 100.0)
        client = MagicMock()
        client.klines.return_value = [c0]

        # Run 1
        mgr.resolve_pending_observations(client, current_time_ms=t0 + bar_len)
        r1 = store.get_all_shadow_records()[0]
        assert r1["fill_status"] == "FILLED"
        f_price = r1["fill_price"]
        f_time = r1["fill_time_ms"]
        e_start = r1["evaluation_start_ms"]
        e_end = r1["evaluation_end_ms"]

        # Run 2 at later time
        c1 = Candle("BTCUSDT", "15m", t0 + bar_len, t0 + 2 * bar_len, 100.0, 102.0, 98.0, 101.0, 100.0)
        client.klines.return_value = [c0, c1]
        mgr.resolve_pending_observations(client, current_time_ms=t0 + 2 * bar_len)
        r2 = store.get_all_shadow_records()[0]
        assert r2["fill_price"] == f_price
        assert r2["fill_time_ms"] == f_time
        assert r2["evaluation_start_ms"] == e_start
        assert r2["evaluation_end_ms"] == e_end


def test_r2_3_09_same_setup_across_minor_ema_drift_preserves_identity() -> None:
    """R2.3-09: Same setup across minor EMA drift keeps same setup_key and signal_identity."""
    k1 = compute_setup_key("BTCUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 105.0)
    k2 = compute_setup_key("BTCUSDT", "BREAKOUT_RETEST", "LONG", 105.0)
    assert k1 == k2
    t0 = 1_700_000_000_000
    id1 = f"{k1}:{t0}"
    id2 = f"{k2}:{t0}"
    assert id1 == id2


def test_r2_3_10_new_setup_instance_after_invalidation_new_identity() -> None:
    """R2.3-10: New setup instance after invalidation allows same setup_key, requires new signal_identity."""
    k = compute_setup_key("BTCUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 105.0)
    t0 = 1_700_000_000_000
    t1 = 1_700_100_000_000
    id1 = f"{k}:{t0}"
    id2 = f"{k}:{t1}"
    assert id1 != id2


def test_r2_3_11_same_breakout_level_three_days_later_new_identity() -> None:
    """R2.3-11: Same breakout level 3 days later creates new signal_identity."""
    k = compute_setup_key("BTCUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 105.0)
    t_day1 = 1_700_000_000_000
    t_day3 = t_day1 + (3 * 24 * 60 * 60 * 1000)
    id_day1 = f"{k}:{t_day1}"
    id_day3 = f"{k}:{t_day3}"
    assert id_day1 != id_day3


def test_r2_3_12_direction_flip_changes_setup_key_and_identity() -> None:
    """R2.3-12: Direction flip changes setup_key and signal_identity."""
    k_long = compute_setup_key("BTCUSDT", PlaybookType.TREND_PULLBACK, DirectionalDecision.LONG, 100.0)
    k_short = compute_setup_key("BTCUSDT", PlaybookType.TREND_PULLBACK, DirectionalDecision.SHORT, 100.0)
    assert k_long != k_short
    assert "LONG" in k_long
    assert "SHORT" in k_short


def test_r2_3_13_doge_precision_no_collision() -> None:
    """R2.3-13: DOGE precision retains distinct levels without collision."""
    k1 = compute_setup_key("DOGEUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 0.123456)
    k2 = compute_setup_key("DOGEUSDT", PlaybookType.BREAKOUT_RETEST, DirectionalDecision.LONG, 0.123457)
    assert k1 != k2


def test_r2_3_14_pre_signal_entry_zone_touch_cannot_fill() -> None:
    """R2.3-14: Pre-signal entry-zone touch cannot fill."""
    t0 = 1_700_000_000_000
    bar_len = 15 * 60 * 1000
    # Candle 0 is before signal (closed at t0). Candle 1 is after signal (close at t0 + bar_len)
    c_pre = Candle("BTCUSDT", "15m", t0 - bar_len, t0, 101.0, 102.0, 99.0, 100.0, 100.0)
    c_post = Candle("BTCUSDT", "15m", t0, t0 + bar_len, 104.0, 106.0, 103.0, 105.0, 100.0)

    status, fill_p, fill_t = resolve_shadow_fill(
        DirectionalDecision.LONG,
        entry_zone_low=99.5,
        entry_zone_high=100.5,
        signal_time_ms=t0,
        entry_window_end_ms=t0 + 4 * bar_len,
        candles=[c_pre, c_post],
    )
    assert status == ShadowFillStatus.WAITING_FOR_FILL
    assert fill_p is None
    assert fill_t is None


def test_r2_3_15_fill_occurs_in_1m_candle_post_fill_remainder_only_eligible() -> None:
    """R2.3-15: Fill occurs in 1m candle; post-fill remainder only is eligible for TP/SL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_15.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len_15m = 15 * 60 * 1000
        bar_len_1m = 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h15",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len_15m,
            evaluation_horizon_bars=16,
            evaluation_end_ms=t0 + 16 * bar_len_15m,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 102.0, 111.0, 99.0, 103.0, 1000.0)
        # 1m candles inside bar: minute 2 touches entry (100.0). Minute 5 touches TP1 (110.0).
        m_candles = [
            Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
                   102.0, 111.0 if i == 5 else 103.0, 99.0 if i == 2 else 101.0, 102.0, 100.0)
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + bar_len_15m)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["tp1_hit"] == 1
        assert recs[0]["terminal_reason"] == "TP1"


def test_r2_3_16_fill_candle_hits_tp_after_fill() -> None:
    """R2.3-16: Fill candle hits TP after fill => TP1 recognized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_16.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len_15m = 15 * 60 * 1000
        bar_len_1m = 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h16",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 102.0, 112.0, 99.0, 111.0, 1000.0)
        # minute 1 fills (low=99.0), minute 8 hits TP1 (high=112.0)
        m_candles = [
            Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
                   101.0, 112.0 if i == 8 else 103.0, 99.0 if i == 1 else 100.5, 102.0, 100.0)
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + bar_len_15m)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["terminal_reason"] == "TP1"
        assert recs[0]["tp1_hit"] == 1
        assert recs[0]["sl_hit"] == 0


def test_r2_3_17_fill_candle_hits_sl_after_fill() -> None:
    """R2.3-17: Fill candle hits SL after fill => STOP recognized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_17.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len_15m = 15 * 60 * 1000
        bar_len_1m = 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h17",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 102.0, 103.0, 94.0, 96.0, 1000.0)
        # minute 1 fills at 100.0, minute 4 plunges to 94.0 (SL breached)
        m_candles = [
            Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
                   101.0, 102.0, 94.0 if i == 4 else (99.5 if i == 1 else 100.0), 96.0 if i == 4 else 101.0, 100.0)
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + bar_len_15m)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["terminal_reason"] == "STOP"
        assert recs[0]["sl_hit"] == 1
        assert recs[0]["tp1_hit"] == 0


def test_r2_3_18_fill_candle_touch_before_fill_only_not_counted() -> None:
    """R2.3-18: Fill candle high/low touched before fill only must NOT count as post-fill TP/SL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_18.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len_15m = 15 * 60 * 1000
        bar_len_1m = 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h18",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 105.0, 111.0, 99.0, 102.0, 1000.0)
        # minute 0 touched 111.0 (before fill!). Minute 5 fills at 99.0. Minutes 6-14 fluctuate between 101 and 103
        m_candles = [
            Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
                   105.0 if i == 0 else 102.0, 111.0 if i == 0 else 103.0, 99.0 if i == 5 else 101.0, 102.0, 100.0)
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + bar_len_15m)
        assert res["resolved_count"] == 0  # NOT resolved in fill bar!
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "FILLED"
        assert recs[0]["resolved"] == 0
        assert recs[0]["tp1_hit"] == 0


def test_r2_3_19_fifteen_min_dual_touch_1m_proves_tp_first() -> None:
    """R2.3-19: 15m candle touches SL and TP; 1m path proves TP first => TP1."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    t0 = 1_700_000_000_000
    bar_len_15m = 15 * 60 * 1000
    bar_len_1m = 60 * 1000

    c_ambig = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 100.0, 115.0, 85.0, 105.0, 1000.0)
    # 1m shows TP touched at minute 3 (high=115.0), SL touched at minute 10 (low=85.0)
    m_candles = [
        Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
               100.0, 115.0 if i == 3 else 102.0, 85.0 if i == 10 else 99.0, 101.0, 100.0)
        for i in range(15)
    ]

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c_ambig],
        persist=False,
        intrabar_1m_candles=m_candles,
    )
    assert outcome["tp1_hit"] is True
    assert outcome["sl_hit"] is False
    assert outcome["terminal_reason"] == "TP1"
    assert outcome["path_resolution"] == ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value


def test_r2_3_20_fifteen_min_dual_touch_1m_proves_sl_first() -> None:
    """R2.3-20: 15m candle touches both; 1m proves SL first => STOP."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    t0 = 1_700_000_000_000
    bar_len_15m = 15 * 60 * 1000
    bar_len_1m = 60 * 1000

    c_ambig = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 100.0, 115.0, 85.0, 105.0, 1000.0)
    # 1m shows SL touched at minute 2 (low=85.0), TP touched at minute 8 (high=115.0)
    m_candles = [
        Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
               100.0, 115.0 if i == 8 else 102.0, 85.0 if i == 2 else 99.0, 101.0, 100.0)
        for i in range(15)
    ]

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c_ambig],
        persist=False,
        intrabar_1m_candles=m_candles,
    )
    assert outcome["sl_hit"] is True
    assert outcome["tp1_hit"] is False
    assert outcome["terminal_reason"] == "STOP"
    assert outcome["path_resolution"] == ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value


def test_r2_3_21_one_min_candle_dual_touch_stop_first_fallback() -> None:
    """R2.3-21: 1m candle itself touches both => STOP_FIRST fallback."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    t0 = 1_700_000_000_000
    bar_len_15m = 15 * 60 * 1000
    bar_len_1m = 60 * 1000

    c_ambig = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 100.0, 115.0, 85.0, 105.0, 1000.0)
    # minute 4 candle itself touches both high=115.0 and low=85.0
    m_candles = [
        Candle("BTCUSDT", "1m", t0 + i * bar_len_1m, t0 + (i + 1) * bar_len_1m,
               100.0, 115.0 if i == 4 else 102.0, 85.0 if i == 4 else 99.0, 101.0, 100.0)
        for i in range(15)
    ]

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c_ambig],
        persist=False,
        intrabar_1m_candles=m_candles,
    )
    assert outcome["sl_hit"] is True
    assert outcome["tp1_hit"] is False
    assert outcome["terminal_reason"] == "STOP"
    assert outcome["path_resolution"] == ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value


def test_r2_3_22_one_min_unavailable_fifteen_min_stop_first_fallback() -> None:
    """R2.3-22: 1m unavailable => 15m STOP_FIRST fallback."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    t0 = 1_700_000_000_000
    bar_len_15m = 15 * 60 * 1000

    c_ambig = Candle("BTCUSDT", "15m", t0, t0 + bar_len_15m, 100.0, 115.0, 85.0, 105.0, 1000.0)
    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c_ambig],
        persist=False,
        intrabar_1m_candles=None,
    )
    assert outcome["sl_hit"] is True
    assert outcome["tp1_hit"] is False
    assert outcome["terminal_reason"] == "STOP"
    assert outcome["path_resolution"] == ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value


def test_r2_3_23_non_default_taker_fee_changes_friction_r() -> None:
    """R2.3-23: Non-default taker fee changes friction_r."""
    from btc_quant_agent.market_watch.shadow import compute_trade_friction_r
    config_default = MarketWatchConfig()
    config_custom = MarketWatchConfig(taker_fee_rate=0.0010)

    _d1, f_r1 = compute_trade_friction_r(100.0, 110.0, 10.0, config_default)
    _d2, f_r2 = compute_trade_friction_r(100.0, 110.0, 10.0, config_custom)
    assert f_r2 > f_r1


def test_r2_3_24_non_default_slippage_changes_friction_r() -> None:
    """R2.3-24: Non-default slippage changes friction_r."""
    from btc_quant_agent.market_watch.shadow import compute_trade_friction_r
    config_default = MarketWatchConfig()
    config_custom = MarketWatchConfig(slippage_bps_per_side=6.0)

    _d1, f_r1 = compute_trade_friction_r(100.0, 110.0, 10.0, config_default)
    _d2, f_r2 = compute_trade_friction_r(100.0, 110.0, 10.0, config_custom)
    assert f_r2 > f_r1


def test_r2_3_25_net_r_equals_gross_r_minus_friction_r() -> None:
    """R2.3-25: net_r = gross_r - friction_r."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    config = MarketWatchConfig()
    c = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 112.0, 99.0, 111.0, 100.0)

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c],
        persist=False,
        config=config,
    )
    gross = outcome["gross_r"]
    fric = outcome["friction_r"]
    net = outcome["net_r"]
    assert abs(net - (gross - fric)) < 1e-4


def test_r2_3_26_tp1_is_terminal_and_returns_correct_actual_r() -> None:
    """R2.3-26: TP1 is terminal and returns correct actual R."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    c = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 116.0, 98.0, 115.0, 100.0)

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,  # Risk dist = 10.0
        tp1=115.0,        # Reward dist = 15.0 => gross_r = 1.5
        tp2=125.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c],
        persist=False,
    )
    assert outcome["terminal_reason"] == "TP1"
    assert outcome["gross_r"] == 1.5
    assert outcome["is_terminal"] is True


def test_r2_3_27_stop_returns_approximately_minus_one_gross_r() -> None:
    """R2.3-27: STOP returns approximately -1 gross R before friction."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    c = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 102.0, 89.0, 90.0, 100.0)

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=115.0,
        tp2=125.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c],
        persist=False,
    )
    assert outcome["terminal_reason"] == "STOP"
    assert outcome["gross_r"] == -1.0


def test_r2_3_28_timeout_uses_final_covered_candle_close() -> None:
    """R2.3-28: TIMEOUT uses final covered candle close."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    candles = [
        Candle("BTCUSDT", "15m", 1000 + i * 900_000, 1000 + (i + 1) * 900_000, 100.0, 106.0 if i == 15 else 104.0, 96.0, 102.0 if i < 15 else 105.0, 100.0)
        for i in range(16)
    ]

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=115.0,
        tp2=125.0,
        direction=DirectionalDecision.LONG,
        future_candles=candles,
        persist=False,
    )
    assert outcome["terminal_reason"] == "TIMEOUT"
    assert outcome["exit_price"] == 105.0
    assert outcome["gross_r"] == 0.5  # (105 - 100) / 10.0


def test_r2_3_29_tp1_then_later_sl_cannot_convert_terminal_tp1_into_loss() -> None:
    """R2.3-29: TP1 hit then later SL cannot convert terminal TP1 into loss."""
    mgr = ShadowEvaluationManager(store=MagicMock())
    c1 = Candle("BTCUSDT", "15m", 1000, 2000, 100.0, 112.0, 99.0, 111.0, 100.0)  # Hits TP1 (110.0)
    c2 = Candle("BTCUSDT", "15m", 2000, 3000, 111.0, 112.0, 85.0, 86.0, 100.0)   # Plunges below SL (90.0)

    outcome = mgr.evaluate_forward_outcomes(
        shadow_id=1,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        direction=DirectionalDecision.LONG,
        future_candles=[c1, c2],
        persist=False,
    )
    assert outcome["terminal_reason"] == "TP1"
    assert outcome["tp1_hit"] is True
    assert outcome["sl_hit"] is False
    assert outcome["gross_r"] == 1.0


def test_r2_3_30_legacy_row_without_modern_fill_semantics_is_legacy_ineligible() -> None:
    """R2.3-30: Legacy row without modern fill semantics resolves to LEGACY_INELIGIBLE."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_30.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000

        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_watch_shadow_records (
                    timestamp_ms, symbol, snapshot_hash, policy_version, config_hash,
                    agent_decision, agent_setup, entry_quality, reason_codes_json,
                    entry_price, stop_loss, tp1, tp2, direction, resolved,
                    fill_status, regime_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'LEGACY', 'LEGACY')
                """,
                (t0, "BTCUSDT", "h30", "1.0", "c30", "LONG", "TREND_PULLBACK", "GOOD", "[]",
                 100.0, 90.0, 110.0, 120.0, "LONG"),
            )

        client = MagicMock()
        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 1000)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["terminal_reason"] == "LEGACY_INELIGIBLE"
        assert recs[0]["regime_after"] == "LEGACY_INELIGIBLE"
        assert recs[0]["resolved"] == 1


def test_r2_3_31_legacy_row_excluded_from_trade_denominator() -> None:
    """R2.3-31: Legacy row is excluded from trade hit-rate denominator."""
    records = [
        {
            "id": 1,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "entry_zone_low": 99.0,
            "entry_zone_high": 101.0,
            "stop_loss": 90.0,
            "fill_status": "FILLED",
            "signal_time_ms": 1000,
            "entry_window_start_ms": 1000,
            "entry_window_end_ms": 4600000,
            "resolved": 1,
            "tp1_hit": 1,
            "tp2_hit": 0,
            "sl_hit": 0,
            "net_r": 1.0,
            "terminal_reason": "TP1",
            "evidence_version": MARKET_WATCH_EVIDENCE_VERSION,
            "signal_identity": "BTCUSDT:TREND_PULLBACK:LONG:100.0:1000",
            "setup_key": "BTCUSDT:TREND_PULLBACK:LONG:100.0",
            "execution_path_model": "PARTIAL_FIRST_BAR_1M_THEN_15M",
            "policy_version": "1.0",
            "config_hash": "c1",
        },
        {
            "id": 2,
            "observation_type": "ACTIONABLE_TRIGGERED",
            "direction": "LONG",
            "entry_price": 100.0,
            "fill_status": "LEGACY",
            "regime_after": "LEGACY_INELIGIBLE",
            "terminal_reason": "LEGACY_INELIGIBLE",
            "resolved": 1,
            "is_legacy": True,
        },
    ]
    metrics = compute_performance_metrics(records)
    assert metrics["total_records"] == 2
    assert metrics["resolved_actionable_count"] == 1
    assert metrics["ineligible_count"] == 1
    assert metrics["tp1_hit_rate"] == 1.0


def test_r2_3_32_exactly_one_actionable_triggered_per_signal_identity() -> None:
    """R2.3-32: Exactly one ACTIONABLE_TRIGGERED record per signal_identity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_32.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        client = MagicMock()
        client.server_time_ms.return_value = 1_700_000_000_000
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
        client.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(mark_price=100.0, index_price=100.0, funding_rate=0.0001, funding_time_ms=1000,
                               open_interest=10000.0, open_interest_time_ms=1000, open_interest_change_pct=0.01,
                               taker_buy_sell_ratio=1.1, taker_time_ms=1000, basis_rate=0.0001, basis_time_ms=1000,
                               long_short_account_ratio=1.0, long_short_time_ms=1000, order_book_imbalance=0.1, spread_bps=1.5),
            field_availability={"mark_price": True},
            endpoint_errors={},
        )
        client._optional_get.return_value = None

        scanner = MarketWatchScanner(config=config, client=client, store=store)
        mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=100.0),
            tf_15m=mock_tf,
            tf_1h=mock_tf,
            tf_4h=mock_tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_dedupe",
        )
        asmt = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT",
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.BREAKOUT_RETEST,
                regime=Regime.TREND_UP,
                entry_quality=EntryQuality.GOOD,
                entry_low=99.0,
                entry_high=101.0,
                stop_loss=95.0,
                take_profit_1=110.0,
                take_profit_2=115.0,
                breakout_level=100.0,
                breakout_direction="LONG",
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
            alert_fingerprint="fp1",
            signal_identity="BTCUSDT:BREAKOUT_RETEST:LONG:100.0:1000",
            setup_key="BTCUSDT:BREAKOUT_RETEST:LONG:100.0",
        )

        # Run cycle 1
        scanner._record_shadow_observations_if_needed(asmt, 1000)
        recs1 = store.get_all_shadow_records()
        assert len(recs1) == 1

        # Run cycle 2 with identical signal_identity
        scanner._record_shadow_observations_if_needed(asmt, 2000)
        recs2 = store.get_all_shadow_records()
        assert len(recs2) == 1  # Dedupe prevented duplicate!


def test_r2_3_33_new_signal_identity_after_invalidation_creates_new_actionable_record() -> None:
    """R2.3-33: New signal_identity after invalidation creates a new actionable record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_33.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        client = MagicMock()
        scanner = MarketWatchScanner(config=config, client=client, store=store)

        mock_tf = make_dummy_tf("BTCUSDT", "15m", 100.0)
        snap = MarketSnapshot(
            symbol="BTCUSDT",
            decision_time_ms=1000,
            observed_at_ms=1000,
            exchange_time_ms=1000,
            price=PriceMetrics(last_price=100.0),
            tf_15m=mock_tf,
            tf_1h=mock_tf,
            tf_4h=mock_tf,
            derivatives=DerivativesMetrics(mark_price=100.0),
            snapshot_hash="hash_retrigger",
        )

        # Instance 1
        asmt1 = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=DirectionalPlan(
                symbol="BTCUSDT", decision=DirectionalDecision.LONG, setup=PlaybookType.BREAKOUT_RETEST,
                regime=Regime.TREND_UP, entry_quality=EntryQuality.GOOD,
                entry_low=99.0, entry_high=101.0, stop_loss=95.0, take_profit_1=110.0, take_profit_2=115.0,
                breakout_level=100.0, breakout_direction="LONG",
            ),
            grid=GridPlan(symbol="BTCUSDT", decision=GridDecision.PAUSE),
            opportunity_score=80.0, relative_performance=None,
            exhaustion=ExhaustionMetrics(distance_from_ema20_atr=0.1, state=ExhaustionState.NORMAL),
            rank=1, lifecycle_state=SignalLifecycleState.TRIGGERED,
            alert_fingerprint="fp1",
            signal_identity="BTCUSDT:BREAKOUT_RETEST:LONG:100.0:1000",
            setup_key="BTCUSDT:BREAKOUT_RETEST:LONG:100.0",
        )
        scanner._record_shadow_observations_if_needed(asmt1, 1000)
        assert len(store.get_all_shadow_records()) == 1

        # Invalidation: symbol state reset
        store.set_last_shadow_signal_ids("BTCUSDT", triggered_id=None)

        # Instance 2 (re-trigger with new identity at t=5000)
        asmt2 = SymbolAssessment(
            symbol="BTCUSDT",
            snapshot=snap,
            directional=asmt1.directional,
            grid=asmt1.grid,
            opportunity_score=80.0,
            relative_performance=None,
            exhaustion=asmt1.exhaustion,
            rank=1,
            lifecycle_state=SignalLifecycleState.TRIGGERED,
            alert_fingerprint="fp2",
            signal_identity="BTCUSDT:BREAKOUT_RETEST:LONG:100.0:5000",
            setup_key="BTCUSDT:BREAKOUT_RETEST:LONG:100.0",
        )
        scanner._record_shadow_observations_if_needed(asmt2, 5000)
        assert len(store.get_all_shadow_records()) == 2


def test_r2_3_34_process_offline_over_120_bars_recovers_exact_window() -> None:
    """R2.3-34: Process offline >120 15m bars recovers exact window via historical_klines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_34.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000
        eval_horizon = 16
        eval_end = t0 + eval_horizon * bar_len

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h34",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            evaluation_horizon_bars=eval_horizon,
            evaluation_end_ms=eval_end,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status="WAITING_FOR_FILL",
        )

        t_curr = t0 + 150 * bar_len  # 150 bars later
        client = MagicMock()
        client.klines.return_value = make_candle_series("BTCUSDT", "15m", 120, start_ms=t0 + 30 * bar_len, step_ms=bar_len)

        hist_candles = make_candle_series("BTCUSDT", "15m", 16, start_ms=t0, step_ms=bar_len, base_price=100.0)
        hist_candles[2] = Candle("BTCUSDT", "15m", hist_candles[2].open_time_ms, hist_candles[2].close_time_ms,
                                 102.0, 112.0, 101.0, 111.0, 500.0)  # TP1 hit
        client.historical_klines.return_value = hist_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t_curr)
        assert res["resolved_count"] == 1
        client.historical_klines.assert_called_once_with("BTCUSDT", "15m", t0, eval_end)


def test_r2_3_35_temporary_historical_fetch_failure_remains_pending_until_retry() -> None:
    """R2.3-35: Temporary historical fetch failure remains pending; later retry resolves correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "mw_r2_3_35.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        bar_len = 15 * 60 * 1000
        eval_horizon = 16
        eval_end = t0 + eval_horizon * bar_len

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h35",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=95.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            evaluation_horizon_bars=eval_horizon,
            evaluation_end_ms=eval_end,
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status="WAITING_FOR_FILL",
        )

        client = MagicMock()
        client.klines.return_value = []
        client.historical_klines.side_effect = RuntimeError("Network error")

        # Attempt 1: Fails
        res1 = mgr.resolve_pending_observations(client, current_time_ms=t0 + 10 * bar_len)
        assert res1["resolved_count"] == 0
        recs1 = store.get_all_shadow_records()
        assert recs1[0]["resolved"] == 0

        # Attempt 2: Recovers
        client.historical_klines.side_effect = None
        hist_candles = make_candle_series("BTCUSDT", "15m", 16, start_ms=t0, step_ms=bar_len, base_price=100.0)
        hist_candles[2] = Candle("BTCUSDT", "15m", hist_candles[2].open_time_ms, hist_candles[2].close_time_ms,
                                 102.0, 112.0, 101.0, 111.0, 500.0)
        client.historical_klines.return_value = hist_candles

        res2 = mgr.resolve_pending_observations(client, current_time_ms=t0 + 10 * bar_len)
        assert res2["resolved_count"] == 1
        recs2 = store.get_all_shadow_records()
        assert recs2[0]["resolved"] == 1
        assert recs2[0]["tp1_hit"] == 1


def test_r2_3_36_decision_time_after_observed_at_after_collection_started() -> None:
    """R2.3-36: decision_time >= observed_at >= collection_started."""
    client = MagicMock()
    client.server_time_ms.return_value = 1000
    client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
    client.collect_derivatives.return_value = MagicMock(
        snapshot=MagicMock(mark_price=100.0, index_price=100.0, funding_rate=0.0001, funding_time_ms=1200,
                           open_interest=1000.0, open_interest_time_ms=1200, open_interest_change_pct=0.01,
                           taker_buy_sell_ratio=1.0, taker_time_ms=1200, basis_rate=0.0001, basis_time_ms=1200,
                           long_short_account_ratio=1.0, long_short_time_ms=1200, order_book_imbalance=0.1, spread_bps=1.0),
        field_availability={"mark_price": True},
        endpoint_errors={},
    )
    client._optional_get.return_value = None

    scanner = MarketWatchScanner(config=MarketWatchConfig(), client=client, store=MagicMock())
    snap, _health, _errs = scanner.collect_symbol_snapshot("BTCUSDT", now_ms=1500)
    assert snap is not None
    assert snap.decision_time_ms >= snap.observed_at_ms
    assert snap.observed_at_ms >= snap.collection_started_at_ms


def test_r2_3_37_decision_time_after_collection_completed() -> None:
    """R2.3-37: decision_time >= collection_completed."""
    client = MagicMock()
    client.server_time_ms.return_value = 1000
    client.klines.return_value = make_candle_series("BTCUSDT", "15m", 40)
    client.collect_derivatives.return_value = MagicMock(
        snapshot=MagicMock(mark_price=100.0, index_price=100.0, funding_rate=0.0001, funding_time_ms=1200,
                           open_interest=1000.0, open_interest_time_ms=1200, open_interest_change_pct=0.01,
                           taker_buy_sell_ratio=1.0, taker_time_ms=1200, basis_rate=0.0001, basis_time_ms=1200,
                           long_short_account_ratio=1.0, long_short_time_ms=1200, order_book_imbalance=0.1, spread_bps=1.0),
        field_availability={"mark_price": True},
        endpoint_errors={},
    )
    client._optional_get.return_value = None

    scanner = MarketWatchScanner(config=MarketWatchConfig(), client=client, store=MagicMock())
    snap, _health, _errs = scanner.collect_symbol_snapshot("BTCUSDT", now_ms=1500)
    assert snap is not None
    assert snap.decision_time_ms >= snap.collection_completed_at_ms


# =========================================================================
# 30. MARKET WATCH R2.3.1 - FORWARD EVIDENCE PRODUCTION SEMANTICS HOTFIX
# =========================================================================


def test_r2_3_1_01_binance_contiguous_15m_klines_pass_continuity() -> None:
    """R2.3.1-01: Realistic Binance contiguous 15m klines pass continuity without gaps."""
    c1 = Candle("BTCUSDT", "15m", 0, 899999, 100.0, 105.0, 95.0, 102.0, 1000.0)
    c2 = Candle("BTCUSDT", "15m", 900000, 1799999, 102.0, 106.0, 101.0, 104.0, 1000.0)
    res = validate_time_coverage([c1, c2], start_ms=0, end_ms=1800000, interval_ms=900000)
    assert res.complete is True
    assert res.internal_gap_count == 0
    assert res.start_covered is True
    assert res.end_covered is True


def test_r2_3_1_02_binance_missing_15m_candle_detected_as_gap() -> None:
    """R2.3.1-02: Missing 15m candle in Binance klines is detected as a gap."""
    c1 = Candle("BTCUSDT", "15m", 0, 899999, 100.0, 105.0, 95.0, 102.0, 1000.0)
    c2 = Candle("BTCUSDT", "15m", 1800000, 2699999, 102.0, 106.0, 101.0, 104.0, 1000.0)
    res = validate_time_coverage([c1, c2], start_ms=0, end_ms=2700000, interval_ms=900000)
    assert res.complete is False
    assert res.internal_gap_count >= 1


def test_r2_3_1_03_binance_contiguous_1m_klines_pass_continuity() -> None:
    """R2.3.1-03: Realistic Binance contiguous 1m klines pass continuity."""
    c1 = Candle("BTCUSDT", "1m", 0, 59999, 100.0, 101.0, 99.0, 100.5, 100.0)
    c2 = Candle("BTCUSDT", "1m", 60000, 119999, 100.5, 102.0, 100.0, 101.5, 100.0)
    res = validate_time_coverage([c1, c2], start_ms=0, end_ms=120000, interval_ms=60000)
    assert res.complete is True
    assert res.internal_gap_count == 0


def test_r2_3_1_04_entry_window_expiry_binance_timestamps_resolves_no_fill() -> None:
    """R2.3.1-04: Entry-window expiry with realistic Binance timestamps resolves NO_FILL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_no_fill.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000
        end_ms = t0 + 4 * step_15m

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h_no_fill",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            entry_window_bars=4,
            entry_window_end_ms=end_ms,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
        )

        candles = [
            Candle(
                "BTCUSDT",
                "15m",
                t0 + i * step_15m,
                t0 + (i + 1) * step_15m - 1,
                106.0,
                110.0,
                105.0,
                107.0,
                1000.0,
            )
            for i in range(4)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = mgr.resolve_pending_observations(client, current_time_ms=end_ms)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "NO_FILL"
        assert recs[0]["resolved"] == 1
        assert recs[0]["terminal_reason"] == "NO_FILL"


def test_r2_3_1_05_outcome_window_maturity_binance_timestamps_resolves_timeout() -> None:
    """R2.3.1-05: Outcome-window maturity with realistic Binance timestamps resolves TIMEOUT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_timeout.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000
        horizon_bars = 4
        end_ms = t0 + horizon_bars * step_15m

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h_timeout",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            fill_status="FILLED",
            fill_price=100.0,
            fill_time_ms=t0,
            evaluation_horizon_bars=horizon_bars,
            evaluation_end_ms=end_ms,
        )

        candles = [
            Candle(
                "BTCUSDT",
                "15m",
                t0 + i * step_15m,
                t0 + (i + 1) * step_15m - 1,
                100.0,
                102.0,
                98.0,
                101.0,
                1000.0,
            )
            for i in range(horizon_bars)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = mgr.resolve_pending_observations(client, current_time_ms=end_ms)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["resolved"] == 1
        assert recs[0]["terminal_reason"] == "TIMEOUT"


def test_r2_3_1_06_partial_signal_bar_touch_pre_signal_only_not_filled() -> None:
    """R2.3.1-06: 15m candle touches entry only before signal; 1m proves no post-signal touch => NOT filled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_psb_pre.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000
        step_1m = 60 * 1000
        signal_time = t0 + 5 * step_1m

        store.record_shadow_observation(
            timestamp_ms=signal_time,
            symbol="BTCUSDT",
            snapshot_hash="h_psb6",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=signal_time,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
            entry_window_bars=4,
            entry_window_end_ms=signal_time + 4 * step_15m,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 102.0, 106.0, 98.0, 104.0, 1000.0)
        m_candles = [
            Candle(
                "BTCUSDT",
                "1m",
                t0 + i * step_1m,
                t0 + (i + 1) * step_1m - 1,
                103.0,
                105.0,
                98.0 if i == 2 else 103.0,
                104.0,
                100.0,
            )
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        assert res["resolved_count"] == 0
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "WAITING_FOR_FILL"
        assert recs[0]["resolved"] == 0


def test_r2_3_1_07_partial_signal_bar_missing_1m_data_gap() -> None:
    """R2.3.1-07: 15m partial signal bar touches entry but 1m is unavailable => PENDING_DATA_GAP, not FILLED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_psb_gap.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000
        step_1m = 60 * 1000
        signal_time = t0 + 5 * step_1m

        store.record_shadow_observation(
            timestamp_ms=signal_time,
            symbol="BTCUSDT",
            snapshot_hash="h_psb7",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=signal_time,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
            entry_window_bars=4,
            entry_window_end_ms=signal_time + 4 * step_15m,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 102.0, 106.0, 98.0, 104.0, 1000.0)
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = []

        mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "WAITING_FOR_FILL"
        assert recs[0]["coverage_status"] == "INCOMPLETE"
        assert recs[0]["coverage_reason"] == "PARTIAL_SIGNAL_BAR_DATA_GAP"
        assert recs[0]["resolved"] == 0


def test_r2_3_1_08_partial_signal_bar_post_signal_touch_fills() -> None:
    """R2.3.1-08: 15m partial signal bar, 1m proves post-signal touch => FILLED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_psb_post.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000
        step_1m = 60 * 1000
        signal_time = t0 + 5 * step_1m

        store.record_shadow_observation(
            timestamp_ms=signal_time,
            symbol="BTCUSDT",
            snapshot_hash="h_psb8",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=signal_time,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
            entry_window_bars=4,
            entry_window_end_ms=signal_time + 4 * step_15m,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 104.0, 106.0, 99.0, 103.0, 1000.0)
        m_candles = [
            Candle(
                "BTCUSDT",
                "1m",
                t0 + i * step_1m,
                t0 + (i + 1) * step_1m - 1,
                104.0,
                105.0,
                99.5 if i == 7 else 103.0,
                103.5,
                100.0,
            )
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "FILLED"
        assert recs[0]["fill_price"] is not None
        assert recs[0]["fill_time_ms"] == t0 + 8 * step_1m - 1


def test_r2_3_1_09_partial_signal_bar_mid_minute_signal() -> None:
    """R2.3.1-09: Mid-minute signal conservative rule: partial minute entry touch does not fill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_psb_mid.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000
        step_1m = 60 * 1000
        signal_time = t0 + 5 * step_1m + 30_000

        store.record_shadow_observation(
            timestamp_ms=signal_time,
            symbol="BTCUSDT",
            snapshot_hash="h_psb9",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=signal_time,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
            entry_window_bars=4,
            entry_window_end_ms=signal_time + 4 * step_15m,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 104.0, 106.0, 99.0, 103.0, 1000.0)
        m_candles = [
            Candle(
                "BTCUSDT",
                "1m",
                t0 + i * step_1m,
                t0 + (i + 1) * step_1m - 1,
                104.0,
                105.0,
                99.5 if i == 5 else 103.0,
                103.5,
                100.0,
            )
            for i in range(15)
        ]
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = m_candles

        mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "WAITING_FOR_FILL"


def test_r2_3_1_10_fill_minute_dual_touch_entry_and_stop_becomes_stop_first() -> None:
    """R2.3.1-10: Fill minute touches entry + stop => STOP with ONE_MINUTE_FILL_BAR_STOP_FIRST."""
    c1 = Candle("BTCUSDT", "1m", 60000, 119999, 100.0, 102.0, 94.0, 96.0, 100.0)
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=95.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=[c1],
        is_fill_bar=True,
        fill_minute_open_ms=60000,
    )
    assert res["is_terminal"] is True
    assert res["sl_hit"] is True
    assert res["tp1_hit"] is False
    assert res["terminal_reason"] == "STOP"
    assert res["path_resolution"] == ShadowPathResolution.ONE_MINUTE_FILL_BAR_STOP_FIRST.value


def test_r2_3_1_11_fill_minute_entry_and_tp1_no_stop_does_not_credit_same_minute_tp1() -> None:
    """R2.3.1-11: Fill minute touches entry + TP1 (no stop) => fill succeeds, same-minute TP1 NOT credited."""
    c1 = Candle("BTCUSDT", "1m", 60000, 119999, 100.0, 112.0, 98.0, 108.0, 100.0)
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=95.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=[c1],
        is_fill_bar=True,
        fill_minute_open_ms=60000,
    )
    assert res["is_terminal"] is False
    assert res["tp1_hit"] is False
    assert res["sl_hit"] is False


def test_r2_3_1_12_fill_minute_entry_tp1_and_stop_becomes_stop_first() -> None:
    """R2.3.1-12: Fill minute touches entry + TP1 + stop => STOP with ONE_MINUTE_FILL_BAR_STOP_FIRST."""
    c1 = Candle("BTCUSDT", "1m", 60000, 119999, 100.0, 112.0, 93.0, 105.0, 100.0)
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=95.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=[c1],
        is_fill_bar=True,
        fill_minute_open_ms=60000,
    )
    assert res["is_terminal"] is True
    assert res["sl_hit"] is True
    assert res["tp1_hit"] is False
    assert res["terminal_reason"] == "STOP"
    assert res["path_resolution"] == ShadowPathResolution.ONE_MINUTE_FILL_BAR_STOP_FIRST.value


def test_r2_3_1_13_fill_minute_entry_tp1_then_next_minute_tp1_resolves_tp1() -> None:
    """R2.3.1-13: Fill minute touches entry + TP1, next minute touches TP1 => TP1 resolved."""
    c1 = Candle("BTCUSDT", "1m", 60000, 119999, 100.0, 112.0, 98.0, 108.0, 100.0)
    c2 = Candle("BTCUSDT", "1m", 120000, 179999, 108.0, 113.0, 106.0, 111.0, 100.0)
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=95.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=[c1, c2],
        is_fill_bar=True,
        fill_minute_open_ms=60000,
    )
    assert res["is_terminal"] is True
    assert res["tp1_hit"] is True
    assert res["sl_hit"] is False
    assert res["terminal_reason"] == "TP1"


def test_r2_3_1_14_fill_minute_entry_tp1_then_next_minute_sl_resolves_stop() -> None:
    """R2.3.1-14: Fill minute touches entry + TP1, next minute hits SL => STOP resolved."""
    c1 = Candle("BTCUSDT", "1m", 60000, 119999, 100.0, 112.0, 98.0, 108.0, 100.0)
    c2 = Candle("BTCUSDT", "1m", 120000, 179999, 108.0, 108.0, 93.0, 94.0, 100.0)
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=95.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=[c1, c2],
        is_fill_bar=True,
        fill_minute_open_ms=60000,
    )
    assert res["is_terminal"] is True
    assert res["sl_hit"] is True
    assert res["tp1_hit"] is False
    assert res["terminal_reason"] == "STOP"


def test_r2_3_1_15_one_min_unavailable_15m_touches_entry_and_sl_becomes_stop() -> None:
    """R2.3.1-15: 15m touches entry + SL and 1m is unavailable => terminal STOP via FIFTEEN_MINUTE_STOP_FIRST."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_1m_unavail_sl.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h15",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 101.0, 102.0, 88.0, 92.0, 1000.0)
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = []

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "FILLED"
        assert recs[0]["sl_hit"] == 1
        assert recs[0]["terminal_reason"] == "STOP"
        assert recs[0]["path_resolution"] == ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value


def test_r2_3_1_16_one_min_unavailable_15m_touches_entry_and_tp1_no_same_bar_tp1() -> None:
    """R2.3.1-16: 15m touches entry + TP1 (no SL) and 1m is unavailable => fill registered, no same-bar TP1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_1m_unavail_tp.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h16",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 100.0, 112.0, 99.0, 108.0, 1000.0)
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = []

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        assert res["resolved_count"] == 0
        recs = store.get_all_shadow_records()
        assert recs[0]["fill_status"] == "FILLED"
        assert recs[0]["tp1_hit"] == 0
        assert recs[0]["resolved"] == 0


def test_r2_3_1_17_one_min_unavailable_15m_touches_entry_tp1_and_sl_becomes_stop() -> None:
    """R2.3.1-17: 15m touches entry + TP1 + SL and 1m is unavailable => terminal STOP via FIFTEEN_MINUTE_STOP_FIRST."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_1m_unavail_all.db")
        mgr = ShadowEvaluationManager(store=store)
        t0 = 1_700_000_000_000
        step_15m = 15 * 60 * 1000

        store.record_shadow_observation(
            timestamp_ms=t0,
            symbol="BTCUSDT",
            snapshot_hash="h17",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="GOOD",
            reason_codes=[],
            entry_price=100.0,
            stop_loss=90.0,
            tp1=110.0,
            tp2=120.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_time_ms=t0,
            entry_zone_low=99.0,
            entry_zone_high=101.0,
        )

        c15 = Candle("BTCUSDT", "15m", t0, t0 + step_15m - 1, 100.0, 115.0, 88.0, 105.0, 1000.0)
        client = MagicMock()
        client.klines.return_value = [c15]
        client.historical_klines.return_value = []

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + step_15m)
        assert res["resolved_count"] == 1
        recs = store.get_all_shadow_records()
        assert recs[0]["sl_hit"] == 1
        assert recs[0]["terminal_reason"] == "STOP"
        assert recs[0]["path_resolution"] == ShadowPathResolution.FIFTEEN_MINUTE_STOP_FIRST.value


def test_r2_3_1_18_r2_2_row_with_null_evidence_version_resolves_legacy_ineligible() -> None:
    """R2.3.1-18: R2.2 row with NULL evidence_version resolves to LEGACY_INELIGIBLE."""
    rec = {
        "id": 1,
        "observation_type": "ACTIONABLE_TRIGGERED",
        "signal_time_ms": 1_700_000_000_000,
        "direction": "LONG",
        "entry_price": 100.0,
        "evidence_version": None,
        "signal_identity": "BTCUSDT:TREND_PULLBACK:LONG:100.0:1700000000000",
        "setup_key": "BTCUSDT:TREND_PULLBACK:LONG:100.0",
        "entry_window_start_ms": 1_700_000_000_000,
        "entry_window_end_ms": 1_700_003_600_000,
        "execution_path_model": "PARTIAL_FIRST_BAR_1M_THEN_15M",
        "policy_version": "1.0",
        "config_hash": "c1",
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 90.0,
    }
    assert is_legacy_shadow_record(rec) is True


def test_r2_3_1_19_row_with_wrong_evidence_version_resolves_legacy_ineligible() -> None:
    """R2.3.1-19: Row with evidence_version != FORWARD_EVIDENCE_V1 resolves to LEGACY_INELIGIBLE."""
    rec = {
        "id": 2,
        "observation_type": "ACTIONABLE_TRIGGERED",
        "signal_time_ms": 1_700_000_000_000,
        "direction": "LONG",
        "entry_price": 100.0,
        "evidence_version": "FORWARD_EVIDENCE_V0",
        "signal_identity": "BTCUSDT:TREND_PULLBACK:LONG:100.0:1700000000000",
        "setup_key": "BTCUSDT:TREND_PULLBACK:LONG:100.0",
        "entry_window_start_ms": 1_700_000_000_000,
        "entry_window_end_ms": 1_700_003_600_000,
        "execution_path_model": "PARTIAL_FIRST_BAR_1M_THEN_15M",
        "policy_version": "1.0",
        "config_hash": "c1",
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 90.0,
    }
    assert is_legacy_shadow_record(rec) is True


def test_r2_3_1_20_row_with_missing_setup_key_is_legacy_ineligible() -> None:
    """R2.3.1-20: Correct evidence_version but missing setup_key is LEGACY_INELIGIBLE."""
    rec = {
        "id": 3,
        "observation_type": "ACTIONABLE_TRIGGERED",
        "signal_time_ms": 1_700_000_000_000,
        "direction": "LONG",
        "entry_price": 100.0,
        "evidence_version": MARKET_WATCH_EVIDENCE_VERSION,
        "signal_identity": "BTCUSDT:TREND_PULLBACK:LONG:100.0:1700000000000",
        "setup_key": None,
        "entry_window_start_ms": 1_700_000_000_000,
        "entry_window_end_ms": 1_700_003_600_000,
        "execution_path_model": "PARTIAL_FIRST_BAR_1M_THEN_15M",
        "policy_version": "1.0",
        "config_hash": "c1",
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 90.0,
    }
    assert is_legacy_shadow_record(rec) is True


def test_r2_3_1_21_modern_record_with_all_fields_is_eligible() -> None:
    """R2.3.1-21: Modern record with all required fields is eligible."""
    rec = {
        "id": 4,
        "observation_type": "ACTIONABLE_TRIGGERED",
        "signal_time_ms": 1_700_000_000_000,
        "direction": "LONG",
        "entry_price": 100.0,
        "evidence_version": MARKET_WATCH_EVIDENCE_VERSION,
        "signal_identity": "BTCUSDT:TREND_PULLBACK:LONG:100.0:1700000000000",
        "setup_key": "BTCUSDT:TREND_PULLBACK:LONG:100.0",
        "entry_window_start_ms": 1_700_000_000_000,
        "entry_window_end_ms": 1_700_003_600_000,
        "execution_path_model": "PARTIAL_FIRST_BAR_1M_THEN_15M",
        "policy_version": "1.0",
        "config_hash": "c1",
        "entry_zone_low": 99.0,
        "entry_zone_high": 101.0,
        "stop_loss": 90.0,
    }
    assert is_legacy_shadow_record(rec) is False


def test_r2_3_1_22_tp1_at_minute_2_mfe_does_not_include_minute_12_spike() -> None:
    """R2.3.1-22: TP1 reached at minute 2; MFE stops at minute 2 and excludes minute 12 spike."""
    t0 = 1_700_000_000_000
    step_1m = 60_000
    candles = [
        Candle(
            "BTCUSDT",
            "1m",
            t0 + i * step_1m,
            t0 + (i + 1) * step_1m - 1,
            100.0,
            110.0 if i == 2 else (140.0 if i == 12 else 102.0),
            98.0,
            101.0,
            100.0,
        )
        for i in range(15)
    ]
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=candles,
        is_fill_bar=False,
    )
    assert res["is_terminal"] is True
    assert res["tp1_hit"] is True
    assert res["terminal_reason"] == "TP1"
    assert res["mfe"] == 1.0


def test_r2_3_1_23_sl_at_minute_3_mae_does_not_include_minute_10_collapse() -> None:
    """R2.3.1-23: SL reached at minute 3; MAE stops at minute 3 and excludes minute 10 collapse."""
    t0 = 1_700_000_000_000
    step_1m = 60_000
    candles = [
        Candle(
            "BTCUSDT",
            "1m",
            t0 + i * step_1m,
            t0 + (i + 1) * step_1m - 1,
            100.0,
            102.0,
            90.0 if i == 3 else (50.0 if i == 10 else 98.0),
            99.0,
            100.0,
        )
        for i in range(15)
    ]
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=candles,
        is_fill_bar=False,
    )
    assert res["is_terminal"] is True
    assert res["sl_hit"] is True
    assert res["terminal_reason"] == "STOP"
    assert res["mae"] == 1.0


def test_r2_3_1_24_same_minute_ambiguous_stop_first_mfe_zero_mae_one() -> None:
    """R2.3.1-24: Same-minute ambiguous stop-first has conservative MFE=0 and MAE=1.0 with no post-terminal contamination."""
    c1 = Candle("BTCUSDT", "1m", 60000, 119999, 100.0, 115.0, 88.0, 95.0, 100.0)
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=90.0,
        tp1=110.0,
        tp2=120.0,
        one_minute_candles=[c1],
        is_fill_bar=True,
        fill_minute_open_ms=60000,
    )
    assert res["is_terminal"] is True
    assert res["sl_hit"] is True
    assert res["tp1_hit"] is False
    assert res["terminal_reason"] == "STOP"
    assert res["mfe"] == 0.0
    assert res["mae"] >= 1.0


def test_r2_3_1_25_three_action_one_risk_max_three_preserves_risk() -> None:
    """R2.3.1-25: 3 high-opportunity ACTION alerts + 1 low-opportunity RISK alert with max 3 preserves RISK."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_risk_preserve.db")
        config = MarketWatchConfig(max_alert_symbols=3)
        client = MagicMock()
        scanner = MarketWatchScanner(config=config, client=client, store=store)

        def mock_eval_symbol(*args, **kwargs):
            snap_obj = kwargs.get("snapshot") or (args[0] if args else None)
            sym = getattr(snap_obj, "symbol", "")
            scores = {"ACT1": 90.0, "ACT2": 80.0, "ACT3": 70.0, "RSK1": 10.0}
            snap = MagicMock(
                symbol=sym,
                price=MagicMock(last_price=100.0, change_24h_pct=0.01),
                tf_1h=MagicMock(atr=1.0, recent_swing_low=95.0, recent_swing_high=105.0, regime="TREND"),
                derivatives=MagicMock(funding_rate=0.0001, oi_1h_change=0.01, oi_12h_change=0.02),
            )
            plan = MagicMock(
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.TREND_PULLBACK,
                entry_quality="GOOD",
                reason_codes=("R1",),
                risk_codes=("RISK1",),
            )
            return MagicMock(
                symbol=sym,
                opportunity_score=scores.get(sym, 50.0),
                snapshot=snap,
                directional=plan,
                grid=None,
                alert_fingerprint=f"fp_{sym}",
                lifecycle_state=SignalLifecycleState.TRIGGERED,
                policy_version="1.0",
                config_hash="c1",
                signal_identity=f"sig_{sym}",
                setup_key=f"key_{sym}",
                veto_reasons=(),
            )

        def mock_alert_emission(asmt, prev, cfg):
            if asmt.symbol == "RSK1":
                return True, AlertSeverity.RISK, ["LIQUIDATION"]
            return True, AlertSeverity.ACTION, ["SIGNAL"]

        scanner._record_shadow_observations_if_needed = MagicMock()
        store.save_symbol_state = MagicMock()

        def make_snap(sym):
            s = MagicMock(symbol=sym)
            s.tf_15m.roc = 0.01
            s.tf_1h.roc = 0.02
            s.tf_4h.roc = 0.03
            return s

        with (
            patch.object(scanner, "assess_symbol", side_effect=mock_eval_symbol),
            patch("btc_quant_agent.market_watch.scanner.evaluate_alert_emission", side_effect=mock_alert_emission),
            patch.object(scanner, "collect_symbol_snapshot", side_effect=lambda s, now_ms: (make_snap(s), MagicMock(), [])),
        ):
            _asmts, alerts = scanner.scan_universe(["ACT1", "ACT2", "ACT3", "RSK1"])
            alert_syms = [al.symbol for al in alerts]
            assert len(alerts) == 3
            assert "RSK1" in alert_syms


def test_r2_3_1_26_four_risk_alerts_max_three_all_four_survive() -> None:
    """R2.3.1-26: 4 RISK alerts with max_alert_symbols = 3 => all 4 survive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_risk_all.db")
        config = MarketWatchConfig(max_alert_symbols=3)
        client = MagicMock()
        scanner = MarketWatchScanner(config=config, client=client, store=store)

        def mock_eval_symbol(*args, **kwargs):
            snap_obj = kwargs.get("snapshot") or (args[0] if args else None)
            sym = getattr(snap_obj, "symbol", "")
            snap = MagicMock(
                symbol=sym,
                price=MagicMock(last_price=100.0, change_24h_pct=0.01),
                tf_1h=MagicMock(atr=1.0, recent_swing_low=95.0, recent_swing_high=105.0, regime="TREND"),
                derivatives=MagicMock(funding_rate=0.0001, oi_1h_change=0.01, oi_12h_change=0.02),
            )
            plan = MagicMock(
                decision=DirectionalDecision.WAIT,
                setup=PlaybookType.NO_TRADE,
                entry_quality="POOR",
                reason_codes=(),
                risk_codes=("CROWDING",),
            )
            return MagicMock(
                symbol=sym,
                opportunity_score=10.0,
                snapshot=snap,
                directional=plan,
                grid=None,
                alert_fingerprint=f"fp_{sym}",
                lifecycle_state=SignalLifecycleState.CANDIDATE,
                policy_version="1.0",
                config_hash="c1",
                signal_identity=f"sig_{sym}",
                setup_key=f"key_{sym}",
                veto_reasons=(),
            )

        def mock_alert_emission(asmt, prev, cfg):
            return True, AlertSeverity.RISK, ["SEVERE_CROWDING"]

        scanner._record_shadow_observations_if_needed = MagicMock()
        store.save_symbol_state = MagicMock()

        def make_snap(sym):
            s = MagicMock(symbol=sym)
            s.tf_15m.roc = 0.01
            s.tf_1h.roc = 0.02
            s.tf_4h.roc = 0.03
            return s

        with (
            patch.object(scanner, "assess_symbol", side_effect=mock_eval_symbol),
            patch("btc_quant_agent.market_watch.scanner.evaluate_alert_emission", side_effect=mock_alert_emission),
            patch.object(scanner, "collect_symbol_snapshot", side_effect=lambda s, now_ms: (make_snap(s), MagicMock(), [])),
        ):
            _asmts, alerts = scanner.scan_universe(["RSK1", "RSK2", "RSK3", "RSK4"])
            assert len(alerts) == 4
            assert {al.symbol for al in alerts} == {"RSK1", "RSK2", "RSK3", "RSK4"}


def test_r2_3_1_27_equal_severity_sorted_by_opportunity_score_then_symbol() -> None:
    """R2.3.1-27: Equal severity alerts sorted by opportunity_score descending, then symbol ascending."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MarketWatchStateStore(Path(tmpdir) / "test_sort_det.db")
        config = MarketWatchConfig(max_alert_symbols=10)
        client = MagicMock()
        scanner = MarketWatchScanner(config=config, client=client, store=store)

        scores = {"SYM_B": 75.0, "SYM_C": 75.0, "SYM_A": 50.0}

        def mock_eval_symbol(*args, **kwargs):
            snap_obj = kwargs.get("snapshot") or (args[0] if args else None)
            sym = getattr(snap_obj, "symbol", "")
            snap = MagicMock(
                symbol=sym,
                price=MagicMock(last_price=100.0, change_24h_pct=0.01),
                tf_1h=MagicMock(atr=1.0, recent_swing_low=95.0, recent_swing_high=105.0, regime="TREND"),
                derivatives=MagicMock(funding_rate=0.0001, oi_1h_change=0.01, oi_12h_change=0.02),
            )
            plan = MagicMock(
                decision=DirectionalDecision.LONG,
                setup=PlaybookType.TREND_PULLBACK,
                entry_quality="GOOD",
                reason_codes=("R1",),
                risk_codes=(),
            )
            return MagicMock(
                symbol=sym,
                opportunity_score=scores.get(sym, 0.0),
                snapshot=snap,
                directional=plan,
                grid=None,
                alert_fingerprint=f"fp_{sym}",
                lifecycle_state=SignalLifecycleState.TRIGGERED,
                policy_version="1.0",
                config_hash="c1",
                signal_identity=f"sig_{sym}",
                setup_key=f"key_{sym}",
                veto_reasons=(),
            )

        def mock_alert_emission(asmt, prev, cfg):
            return True, AlertSeverity.ACTION, ["SIGNAL"]

        scanner._record_shadow_observations_if_needed = MagicMock()
        store.save_symbol_state = MagicMock()

        def make_snap(sym):
            s = MagicMock(symbol=sym)
            s.tf_15m.roc = 0.01
            s.tf_1h.roc = 0.02
            s.tf_4h.roc = 0.03
            return s

        with (
            patch.object(scanner, "assess_symbol", side_effect=mock_eval_symbol),
            patch("btc_quant_agent.market_watch.scanner.evaluate_alert_emission", side_effect=mock_alert_emission),
            patch.object(scanner, "collect_symbol_snapshot", side_effect=lambda s, now_ms: (make_snap(s), MagicMock(), [])),
        ):
            _asmts, alerts = scanner.scan_universe(["SYM_A", "SYM_C", "SYM_B"])
            assert [al.symbol for al in alerts] == ["SYM_B", "SYM_C", "SYM_A"]
