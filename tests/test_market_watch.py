from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

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
    SignalLifecycleState,
    SymbolAssessment,
    TimeframeSnapshot,
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
from btc_quant_agent.market_watch.shadow import ShadowEvaluationManager
from btc_quant_agent.market_watch.snapshot import compute_snapshot_hash, compute_timeframe_snapshot
from btc_quant_agent.market_watch.state import MarketWatchStateStore, evaluate_alert_emission


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
    )
    snap_eth = MarketSnapshot(
        symbol="ETHUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=10.0), tf_15m=make_dummy_tf("ETHUSDT", "15m", roc_val=0.0),
        tf_1h=make_dummy_tf("ETHUSDT", "1h", roc_val=0.0), tf_4h=make_dummy_tf("ETHUSDT", "4h", roc_val=0.0),
        derivatives=DerivativesMetrics(mark_price=10.0), snapshot_hash="h_eth",
    )

    snap_sol_a = MarketSnapshot(
        symbol="SOLUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=50.0), tf_15m=tf_15m_a, tf_1h=tf_1h_a, tf_4h=tf_4h_a,
        derivatives=DerivativesMetrics(mark_price=50.0), snapshot_hash="h_sol_a",
    )
    snap_sol_b = MarketSnapshot(
        symbol="SOLUSDT", decision_time_ms=1000, observed_at_ms=1000, exchange_time_ms=1000,
        price=PriceMetrics(last_price=50.0), tf_15m=tf_15m_b, tf_1h=tf_1h_a, tf_4h=tf_4h_a,
        derivatives=DerivativesMetrics(mark_price=50.0), snapshot_hash="h_sol_b",
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
    emit, _sev, reasons = evaluate_alert_emission(asmt, prev_state, config)
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
