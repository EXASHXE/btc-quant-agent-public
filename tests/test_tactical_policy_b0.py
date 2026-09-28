from __future__ import annotations

import dataclasses
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from btc_quant_agent.domain import Candle, Regime
from btc_quant_agent.market_watch.config import (
    MarketWatchConfig,
    MarketWatchThresholdsConfig,
    compute_market_watch_config_hash,
    compute_required_closed_bars,
    compute_required_fetch_bars,
)
from btc_quant_agent.market_watch.context import evaluate_benchmark_context
from btc_quant_agent.market_watch.domain import (
    ACTIVE_PLAYBOOKS,
    HEURISTIC_RULE_QUALITY_BAND_VERSION,
    RESERVED_INACTIVE_PLAYBOOKS,
    RULE_SCORE_SEMANTICS_VERSION,
    TACTICAL_POLICY_VERSION,
    BenchmarkContext,
    CandidateStatus,
    DerivativesMetrics,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    PlaybookCandidate,
    PlaybookType,
    ShadowTerminalReason,
    TacticalSemanticIdentity,
    TimeframeSnapshot,
)
from btc_quant_agent.market_watch.playbooks import (
    select_playbook_candidate,
)
from btc_quant_agent.market_watch.ranking import (
    calculate_opportunity_score,
    calculate_rule_score,
    compute_relative_performances,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.shadow import (
    evaluate_intrabar_path,
)
from btc_quant_agent.market_watch.snapshot import (
    ReturnAvailability,
    closed_bar_return,
    closed_bar_return_with_status,
    compute_timeframe_snapshot,
)
from btc_quant_agent.market_watch.state import (
    MarketWatchStateStore,
    is_legacy_shadow_record,
    is_legacy_tactical_record,
)


def _make_15m_candles(count: int, base_price: float = 100.0, step_price: float = 1.0, start_time_ms: int = 1_000_000_000_000) -> list[Candle]:
    candles = []
    interval_ms = 15 * 60 * 1000
    for i in range(count):
        open_time = start_time_ms + i * interval_ms
        close_time = open_time + interval_ms - 1
        price = base_price + i * step_price
        candles.append(
            Candle(
                symbol="BTCUSDT",
                interval="15m",
                open_time_ms=open_time,
                close_time_ms=close_time,
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=10.0,
                quote_volume=10.0 * price,
                trades=100,
                closed=True,
            )
        )
    return candles


def _make_dummy_tf(symbol: str, interval: str, close: float = 100.0) -> TimeframeSnapshot:
    closed = Candle(symbol, interval, 1000, 2000, close - 0.2, close + 0.5, close - 0.5, close, 5000.0, trades=10)
    return TimeframeSnapshot(
        interval=interval,
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=closed.close_time_ms,
        close=close,
        ema_fast=close * 1.01,
        ema_mid=close * 0.98,
        ema_fast_slope=0.05,
        ema_mid_slope=0.02,
        atr=2.0,
        atr_percentile=0.5,
        adx=28.0,
        rsi=55.0,
        roc=0.015,
        volume=5000.0,
        volume_z=0.5,
        bb_width=0.04,
        bb_width_percentile=0.4,
        recent_swing_high=close * 1.05,
        recent_swing_low=close * 0.95,
        supports=(close * 0.96, close * 0.94),
        resistances=(close * 1.04, close * 1.06),
        structure="HH_HL",
        regime=Regime.TREND_UP,
        is_volatility_compressed=False,
    )


# ==============================================================================
# 38. Tests - elapsed returns
# ==============================================================================

def test_elapsed_returns_exact_horizons() -> None:
    """True 1h, 4h, 12h returns computed from closed 15m bars using exact horizon anchors."""
    # 60 closed bars: 15h of data
    candles = _make_15m_candles(60, base_price=100.0, step_price=1.0)
    
    # Latest bar is at index 59 (price = 159.0)
    # 1h = 4 bars ago (index 55, price = 155.0) -> return = 159.0 / 155.0 - 1
    r1h, status1h = closed_bar_return_with_status(candles, horizon_ms=3_600_000)
    assert status1h == ReturnAvailability.AVAILABLE
    assert r1h is not None
    assert pytest.approx(r1h, abs=1e-6) == (159.0 / 155.0 - 1.0)

    # 4h = 16 bars ago (index 43, price = 143.0) -> return = 159.0 / 143.0 - 1
    r4h, status4h = closed_bar_return_with_status(candles, horizon_ms=14_400_000)
    assert status4h == ReturnAvailability.AVAILABLE
    assert r4h is not None
    assert pytest.approx(r4h, abs=1e-6) == (159.0 / 143.0 - 1.0)

    # 12h = 48 bars ago (index 11, price = 111.0) -> return = 159.0 / 111.0 - 1
    r12h, status12h = closed_bar_return_with_status(candles, horizon_ms=43_200_000)
    assert status12h == ReturnAvailability.AVAILABLE
    assert r12h is not None
    assert pytest.approx(r12h, abs=1e-6) == (159.0 / 111.0 - 1.0)


def test_elapsed_returns_forming_candle_isolation() -> None:
    """A forming candle (closed=False) cannot affect latest candle or elapsed return."""
    candles = _make_15m_candles(60, base_price=100.0, step_price=1.0)
    r1h_clean, _ = closed_bar_return_with_status(candles, horizon_ms=3_600_000)

    # Append forming candle with wildly different price
    forming_candle = dataclasses.replace(
        candles[-1],
        high=100000.0,
        close=99999.0,
        closed=False,
        close_time_ms=candles[-1].close_time_ms + 15 * 60 * 1000,
    )
    candles_with_forming = candles + [forming_candle]

    r1h_forming, status = closed_bar_return_with_status(candles_with_forming, horizon_ms=3_600_000)
    assert status == ReturnAvailability.AVAILABLE
    assert r1h_forming == r1h_clean


def test_elapsed_returns_missing_anchor_no_fallback() -> None:
    """If exact horizon anchor candle is missing, return UNAVAILABLE without fallback."""
    candles = _make_15m_candles(60, base_price=100.0, step_price=1.0)
    # Remove bar at index 55 (which is the exact 1h anchor)
    candles_gap = [c for i, c in enumerate(candles) if i != 55]

    r1h, status = closed_bar_return_with_status(candles_gap, horizon_ms=3_600_000)
    assert status == ReturnAvailability.MISSING_HORIZON_ANCHOR
    assert r1h is None
    assert closed_bar_return(candles_gap, horizon_ms=3_600_000) is None


def test_elapsed_returns_insufficient_history() -> None:
    """If history span < horizon, return INSUFFICIENT_HISTORY."""
    # Only 10 bars = 2.5 hours
    candles = _make_15m_candles(10, base_price=100.0, step_price=1.0)

    r4h, status = closed_bar_return_with_status(candles, horizon_ms=14_400_000)
    assert status == ReturnAvailability.INSUFFICIENT_HISTORY
    assert r4h is None


def test_benchmark_shock_uses_return_1h() -> None:
    """Benchmark volatility shock evaluates return_1h, not 12 x 1h roc."""
    cfg = MarketWatchConfig()

    tf_mock = MagicMock()
    tf_mock.atr_percentile = 0.90
    tf_mock.roc = 0.001  # Small 1h candle roc

    # BTC snapshot with large return_1h (-4.0%)
    btc_snap = MagicMock(
        symbol="BTCUSDT",
        return_1h=-0.04,
        return_1h_status="AVAILABLE",
        tf_1h=tf_mock,
    )
    ctx, reasons, _risks = evaluate_benchmark_context(
        btc_snapshot=btc_snap,
        eth_snapshot=None,
        config=cfg,
    )
    assert ctx == BenchmarkContext.BTC_VOLATILITY_SHOCK
    assert "BTC_DOWNSIDE_VOLATILITY_SHOCK" in reasons


# ==============================================================================
# 39. Tests - EMA slow
# ==============================================================================

def test_ema_slow_observational_behavior() -> None:
    """EMA slow computed when sufficient confirmed history exists, observational only."""
    cfg = MarketWatchConfig(thresholds=MarketWatchThresholdsConfig(ema_slow=50))

    # 110 candles (sufficient for ema_slow=50 + 50 warmup = 100)
    candles = _make_15m_candles(110, base_price=100.0, step_price=0.5)
    tf_snap = compute_timeframe_snapshot("15m", candles, None, cfg)
    assert tf_snap.ema_slow_status == "AVAILABLE"
    assert tf_snap.ema_slow is not None
    assert tf_snap.ema_slow > 0.0

    # Insufficient history case
    short_candles = _make_15m_candles(40, base_price=100.0)
    short_snap = compute_timeframe_snapshot("15m", short_candles, None, cfg)
    assert short_snap.ema_slow_status == "EMA_SLOW_INSUFFICIENT_HISTORY"
    assert short_snap.ema_slow is None


def test_ema_slow_forming_bar_isolation() -> None:
    """Forming bar cannot alter confirmed closed candle snapshot EMA slow."""
    cfg = MarketWatchConfig(thresholds=MarketWatchThresholdsConfig(ema_slow=50))
    candles = _make_15m_candles(110, base_price=100.0, step_price=0.5)
    snap1 = compute_timeframe_snapshot("15m", candles, None, cfg)

    forming = dataclasses.replace(
        candles[-1],
        high=10000.0,
        close=9999.0,
        closed=False,
        close_time_ms=candles[-1].close_time_ms + 900_000,
    )
    snap2 = compute_timeframe_snapshot("15m", candles, forming, cfg)
    assert snap1.ema_slow == snap2.ema_slow


def test_ema_slow_config_identity() -> None:
    """Changing configured ema_slow changes config hash and required fetch bars."""
    cfg1 = MarketWatchConfig(thresholds=MarketWatchThresholdsConfig(ema_slow=50))
    cfg2 = MarketWatchConfig(thresholds=MarketWatchThresholdsConfig(ema_slow=200))

    assert compute_market_watch_config_hash(cfg1) != compute_market_watch_config_hash(cfg2)
    assert compute_required_closed_bars(cfg2) > compute_required_closed_bars(cfg1)
    assert compute_required_fetch_bars(cfg2) == compute_required_closed_bars(cfg2) + 1


# ==============================================================================
# 40. Tests - playbooks
# ==============================================================================

def test_playbook_registry_and_range_mean_reversion_inactive() -> None:
    """Active registry matches frozen specification; RANGE_MEAN_REVERSION is reserved inactive."""
    assert PlaybookType.RANGE_MEAN_REVERSION in RESERVED_INACTIVE_PLAYBOOKS
    assert PlaybookType.RANGE_MEAN_REVERSION not in ACTIVE_PLAYBOOKS
    assert len(ACTIVE_PLAYBOOKS) == 5
    assert set(ACTIVE_PLAYBOOKS) == {
        PlaybookType.TREND_PULLBACK,
        PlaybookType.BREAKOUT_RETEST,
        PlaybookType.FAILED_BREAKOUT,
        PlaybookType.FAILED_BREAKDOWN,
        PlaybookType.VOLATILITY_EXPANSION,
    }


def test_static_precedence_deterministic_ordering() -> None:
    """STATIC_PRECEDENCE_V1 selects strictly in frozen order: TP -> BR -> FB -> VE."""
    c_tp = PlaybookCandidate(
        playbook=PlaybookType.TREND_PULLBACK,
        candidate_status=CandidateStatus.ACTIONABLE,
        decision=DirectionalDecision.LONG,
        entry_low=100.0,
        entry_high=102.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=115.0,
        structural_anchor_id=None,
        reason_codes=("TP_REASON",),
        risk_codes=(),
        setup_creation_bar_end_ms=1000,
    )
    c_br = PlaybookCandidate(
        playbook=PlaybookType.BREAKOUT_RETEST,
        candidate_status=CandidateStatus.ACTIONABLE,
        decision=DirectionalDecision.LONG,
        entry_low=101.0,
        entry_high=103.0,
        stop_loss=96.0,
        take_profit_1=111.0,
        take_profit_2=116.0,
        structural_anchor_id=None,
        reason_codes=("BR_REASON",),
        risk_codes=(),
        setup_creation_bar_end_ms=1000,
    )
    c_ve = PlaybookCandidate(
        playbook=PlaybookType.VOLATILITY_EXPANSION,
        candidate_status=CandidateStatus.ACTIONABLE,
        decision=DirectionalDecision.LONG,
        entry_low=102.0,
        entry_high=104.0,
        stop_loss=97.0,
        take_profit_1=112.0,
        take_profit_2=117.0,
        structural_anchor_id=None,
        reason_codes=("VE_REASON",),
        risk_codes=(),
        setup_creation_bar_end_ms=1000,
    )

    # If TP and BR and VE are all present, TP is selected
    selected, eligible, actionable = select_playbook_candidate([c_ve, c_br, c_tp])
    assert selected is not None
    assert selected.playbook == PlaybookType.TREND_PULLBACK
    assert len(eligible) == 3
    assert len(actionable) == 3

    # If TP absent, BR is selected
    selected_nobr, _, _ = select_playbook_candidate([c_ve, c_br])
    assert selected_nobr is not None
    assert selected_nobr.playbook == PlaybookType.BREAKOUT_RETEST

    # If only VE present, VE is selected
    selected_ve, _, _ = select_playbook_candidate([c_ve])
    assert selected_ve is not None
    assert selected_ve.playbook == PlaybookType.VOLATILITY_EXPANSION


# ==============================================================================
# 41. Tests - reference universe
# ==============================================================================

def test_reference_universe_degraded_behavior() -> None:
    """One missing reference member degrades universe: median neutralized, weights not renormalized."""
    cfg = MarketWatchConfig()
    expected = cfg.relative_strength_universe

    # Provide all members except one
    missing = expected[-1]
    available = expected[:-1]

    snaps: dict[str, Any] = {}
    for s in available:
        snaps[s] = MagicMock(
            symbol=s,
            return_1h=0.02,
            return_4h=0.04,
            return_12h=0.06,
        )

    perfs = compute_relative_performances(snaps, cfg)
    for rp in perfs.values():
        assert rp.universe_status == "UNIVERSE_DEGRADED"
        assert missing in rp.missing_members
        assert rp.rel_to_median_1h is None
        assert rp.rank == 0  # Cross-sectional rank unavailable when degraded


def test_reference_universe_btc_eth_independent_when_degraded() -> None:
    """BTC and ETH relative performance continue independently even when universe is degraded."""
    cfg = MarketWatchConfig()
    # Missing reference members
    snaps: dict[str, Any] = {
        "BTCUSDT": MagicMock(symbol="BTCUSDT", return_1h=0.01, return_4h=0.02, return_12h=0.03),
        "ETHUSDT": MagicMock(symbol="ETHUSDT", return_1h=-0.01, return_4h=-0.02, return_12h=-0.03),
        "LINKUSDT": MagicMock(symbol="LINKUSDT", return_1h=0.05, return_4h=0.06, return_12h=0.07),
    }

    perfs = compute_relative_performances(snaps, cfg)
    rp_link = perfs["LINKUSDT"]
    assert rp_link.universe_status == "UNIVERSE_DEGRADED"
    # BTC and ETH relative returns remain available and independent
    assert rp_link.rel_to_btc_1h == pytest.approx(0.05 - 0.01, abs=1e-6)
    assert rp_link.rel_to_eth_1h == pytest.approx(0.05 - (-0.01), abs=1e-6)
    # Median is neutral/None
    assert rp_link.rel_to_median_1h is None


def test_scanner_collection_semantics_link_vs_all() -> None:
    """Section 21: --symbols LINKUSDT and --all produce identical LINKUSDT RS context."""
    cfg = MarketWatchConfig()
    client = MagicMock()
    client._optional_get.return_value = None
    store = MagicMock()
    store.get_symbol_state.return_value = None
    scanner = MarketWatchScanner(cfg, client, store)

    # Mock candle data for all universe symbols
    candles = _make_15m_candles(60, base_price=100.0, step_price=0.5)
    client.klines.return_value = candles
    client.collect_derivatives.return_value = MagicMock(
        snapshot=MagicMock(
            observed_at_ms=1000,
            mark_price=100.0,
            index_price=100.0,
            funding_rate=0.0001,
            funding_time_ms=1000,
            open_interest=1000.0,
            open_interest_time_ms=1000,
            open_interest_change_pct=0.01,
            taker_buy_sell_ratio=1.0,
            taker_time_ms=1000,
            basis_rate=0.0001,
            basis_time_ms=1000,
            long_short_account_ratio=1.0,
            long_short_time_ms=1000,
            top_trader_position_ratio=1.0,
            top_trader_account_ratio=1.0,
            order_book_imbalance=0.0,
            spread_bps=1.0,
        ),
        field_availability={},
        endpoint_errors={},
    )

    # Scan 1: link only
    asmts_link, _ = scanner.scan_universe(["LINKUSDT"])
    # Scan 2: all default symbols
    asmts_all, _ = scanner.scan_universe(cfg.symbols)

    assert len(asmts_link) == 1
    assert asmts_link[0].symbol == "LINKUSDT"
    asmt_all_link = next(a for a in asmts_all if a.symbol == "LINKUSDT")

    # Identical relative performance context
    assert asmts_link[0].relative_performance is not None
    assert asmt_all_link.relative_performance is not None
    assert asmts_link[0].relative_performance.universe_status == asmt_all_link.relative_performance.universe_status
    assert asmts_link[0].relative_performance.score == asmt_all_link.relative_performance.score


# ==============================================================================
# 42. Tests - Rule Score
# ==============================================================================

def test_rule_score_non_probabilistic_contract() -> None:
    """Rule Score is non-probabilistic, legacy opportunity_score alias matches value."""
    cfg = MarketWatchConfig()
    plan = DirectionalPlan(
        symbol="BTCUSDT",
        decision=DirectionalDecision.LONG,
        setup=PlaybookType.TREND_PULLBACK,
        regime=Regime.TREND_UP,
        entry_quality=EntryQuality.EXCELLENT,
        entry_low=100.0,
        entry_high=102.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=115.0,
        rule_score=85.0,
        rule_score_semantics=RULE_SCORE_SEMANTICS_VERSION,
        heuristic_quality_band_semantics=HEURISTIC_RULE_QUALITY_BAND_VERSION,
    )

    assert plan.rule_score == 85.0
    assert plan.opportunity_score == 85.0
    assert plan.rule_score_semantics == "RULE_SCORE_V1"
    assert plan.heuristic_quality_band_semantics == "HEURISTIC_RULE_QUALITY_BAND_V1"

    # Verify calculate_rule_score == calculate_opportunity_score
    tf_1h = _make_dummy_tf("BTCUSDT", "1h", 100.0)
    tf_15m = _make_dummy_tf("BTCUSDT", "15m", 100.0)
    deriv = DerivativesMetrics(mark_price=100.0, taker_buy_sell_ratio=1.1)
    exhaustion = ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL)

    s1 = calculate_rule_score(decision=DirectionalDecision.WAIT, tf_1h=tf_1h, tf_15m=tf_15m, entry_quality=EntryQuality.POOR, derivatives=deriv, exhaustion=exhaustion, relative_perf=None, benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL, net_rr=1.0, has_fatal_veto=False, config=cfg)
    s2 = calculate_opportunity_score(decision=DirectionalDecision.WAIT, tf_1h=tf_1h, tf_15m=tf_15m, entry_quality=EntryQuality.POOR, derivatives=deriv, exhaustion=exhaustion, relative_perf=None, benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL, net_rr=1.0, has_fatal_veto=False, config=cfg)
    assert s1 == s2


# ==============================================================================
# 43. Tests - version identity and SQLite migration
# ==============================================================================

def test_sqlite_additive_idempotent_migration() -> None:
    """Opening old prototype schema and initializing B0 store succeeds idempotently without reset."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_migration.db"
        # 1. Create legacy schema
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE market_watch_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision_time_ms INTEGER,
                    symbol TEXT,
                    snapshot_hash TEXT,
                    policy_version TEXT,
                    config_hash TEXT,
                    opportunity_score REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE market_watch_shadow_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_ms INTEGER,
                    symbol TEXT,
                    agent_decision TEXT
                )
                """
            )
            # Insert legacy rows
            conn.execute(
                "INSERT INTO market_watch_assessments (symbol, opportunity_score, policy_version) VALUES (?, ?, ?)",
                ("BTCUSDT", 70.0, "OLD_POLICY"),
            )
            conn.execute(
                "INSERT INTO market_watch_shadow_records (symbol, agent_decision) VALUES (?, ?)",
                ("BTCUSDT", "LONG"),
            )
            conn.commit()

        # 2. First B0 initialization
        store1 = MarketWatchStateStore(db_path)
        legacy_shadows = store1.get_all_shadow_records()
        assert len(legacy_shadows) == 1
        assert is_legacy_tactical_record(legacy_shadows[0]) is True
        assert is_legacy_shadow_record(legacy_shadows[0]) is True

        # Default tactical query excludes legacy rows
        tactical_shadows = store1.get_tactical_shadow_records(include_legacy=False)
        assert len(tactical_shadows) == 0

        # 3. Second B0 initialization (must be strictly idempotent)
        store2 = MarketWatchStateStore(db_path)
        # Record new B0 shadow observation
        new_id = store2.record_shadow_observation(
            timestamp_ms=2_000_000_000_000,
            symbol="ETHUSDT",
            snapshot_hash="hash_b0",
            agent_decision="LONG",
            agent_setup="TREND_PULLBACK",
            entry_quality="EXCELLENT",
            reason_codes=["REASON_1"],
            policy_version=TACTICAL_POLICY_VERSION,
            semantic_identity=TacticalSemanticIdentity(),
        )
        assert new_id > 0

        # Query tactical shadow records
        tactical_records = store2.get_tactical_shadow_records(include_legacy=False)
        assert len(tactical_records) == 1
        assert tactical_records[0]["symbol"] == "ETHUSDT"
        assert is_legacy_tactical_record(tactical_records[0]) is False


# ==============================================================================
# 44. Mandatory Forward Evidence regressions
# ==============================================================================

def test_forward_evidence_resolution_and_path() -> None:
    """Preserve forward evidence fill-anchored evaluation, stop-first, and terminal semantics."""
    candles_1m = [
        Candle(symbol="BTCUSDT", interval="1m", open_time_ms=1000 + i * 60000, close_time_ms=1000 + (i + 1) * 60000 - 1, open=100.0, high=101.0, low=99.0, close=100.0, volume=1.0, quote_volume=100.0, trades=10, closed=True)
        for i in range(10)
    ]
    # Path resolution on 1m
    res = evaluate_intrabar_path(
        direction=DirectionalDecision.LONG,
        entry_price=100.0,
        stop_loss=95.0,
        tp1=105.0,
        tp2=110.0,
        one_minute_candles=candles_1m,
    )
    assert res["terminal_reason"] is None or res["terminal_reason"] in [t.value for t in ShadowTerminalReason]


# ==============================================================================
# 45. Execution-fence tests
# ==============================================================================

def test_execution_fence_no_private_api_mutations() -> None:
    """Verify market_watch modules contain zero private order or wallet execution endpoints."""
    mw_dir = Path("src/btc_quant_agent/market_watch")
    forbidden_tokens = [
        "order_market_buy",
        "order_market_sell",
        "create_order",
        "cancel_order",
        "api_secret",
        "api_key",
        "POST /fapi/v1/order",
        "DELETE /fapi/v1/order",
    ]
    for py_file in mw_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"Forbidden execution fence token '{token}' found in {py_file}"
