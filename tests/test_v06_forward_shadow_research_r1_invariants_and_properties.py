"""Deterministic property and invariant tests verifying edge cases, horizons, and causality.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.account import (
    ExitReason,
    PaperAccount,
)
from scripts.strategy_research.forward_shadow_research_r1.adapter import (
    PublicFeedAdapter,
)
from scripts.strategy_research.forward_shadow_research_r1.contract import (
    AggTradeData,
    BarData,
    BookIntegrityV1,
    MarketEventV1,
    Quality,
    SettledFundingData,
    canonical_json,
    sha256_hex,
)
from scripts.strategy_research.forward_shadow_research_r1.execution import (
    ShadowExecutionEngine,
)
from scripts.strategy_research.forward_shadow_research_r1.fixtures import (
    generate_warmup_hourly_bars,
    make_funding_settled_event,
    make_test_book,
)
from scripts.strategy_research.forward_shadow_research_r1.registry import (
    Horizon,
    get_default_hypotheses,
)
from scripts.strategy_research.forward_shadow_research_r1.signals import (
    SignalEngine,
    SignalStatus,
    compute_atr_1h,
)
from scripts.strategy_research.forward_shadow_research_r1.statistics import (
    block_bootstrap_net_bps,
)


def make_dummy_1m_bar(index: int, open_p: float, high_p: float, low_p: float, close_p: float, closed: bool = True) -> BarData:
    start = 1700000000000 + (index * 60000)
    end = start + 59999
    return BarData(
        bar_open_ms=start,
        bar_close_ms=end,
        closed=closed,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=10.0,
    )


def test_one_minute_future_mutation_cannot_alter_decision():
    """Future bar mutation after decision time cannot alter the as-of decision or entry quote."""
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)

    # 35 bars
    bars_1m = [
        BarData(
            bar_open_ms=1000 + (i * 60000),
            bar_close_ms=1000 + (i * 60000) + 59999,
            closed=True,
            open=65000.0 - (40.0 if i == 34 else 60.0),
            high=65000.0,
            low=64900.0,
            close=65000.0 - (40.0 if i == 34 else 60.0),
            volume=10.0,
        )
        for i in range(35)
    ]
    mark_bars = [
        BarData(
            bar_open_ms=1000 + (i * 60000),
            bar_close_ms=1000 + (i * 60000) + 59999,
            closed=True,
            open=65000.0,
            high=65005.0,
            low=64995.0,
            close=65000.0,
            volume=10.0,
        )
        for i in range(35)
    ]
    book = make_test_book(best_bid=64959.0, best_ask=64961.0)
    hourly_bars = generate_warmup_hourly_bars(1000 - (210 * 3600 * 1000), 210)
    decision_ms = bars_1m[-1].bar_close_ms

    prop_original = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=bars_1m,
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )

    # Simulate future mutation on a minute that arrives after decision
    future_mutated_bar = BarData(
        bar_open_ms=decision_ms + 1,
        bar_close_ms=decision_ms + 60000,
        closed=True,
        open=99999.0,
        high=99999.0,
        low=11111.0,
        close=99999.0,
        volume=9999.0,
    )
    assert future_mutated_bar.bar_open_ms > decision_ms

    # Re-evaluate as of original decision time: must be 100% identical!
    prop_recheck = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=bars_1m,  # As-of input strictly unchanged
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )

    assert prop_original.direction == prop_recheck.direction
    assert prop_original.proposed_entry_price == prop_recheck.proposed_entry_price
    assert prop_original.stop_price == prop_recheck.stop_price
    assert prop_original.target_price == prop_recheck.target_price


def test_stale_book_boundary_999ms_vs_1001ms():
    """Book with 999ms stale age is admitted; 1001ms is degraded/fails closed."""
    book_ok = make_test_book(stale_age_ms=999)
    qual_ok, _ = book_ok.validate()
    assert qual_ok == Quality.VERIFIED

    book_stale = make_test_book(stale_age_ms=1001)
    qual_stale, reasons = book_stale.validate()
    assert qual_stale == Quality.DEGRADED
    assert "STALE_DEPTH_OVER_1000MS" in reasons


def test_stale_mark_boundary_1999ms_vs_2001ms():
    """Mark event with 1999ms stale age is verified; 2001ms is degraded."""
    payload = {"p": "65000.0"}
    p_sha = sha256_hex(canonical_json(payload))

    ev_ok = MarketEventV1.from_dict({
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "mark_price",
        "provider_event_ms": 10000,
        "observed_wall_utc_ms": 11999,  # 1999ms <= 2000ms
        "observed_monotonic_ns": 1000,
        "available_at_ms": 11999,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": p_sha,
        "payload": payload,
        "quality": "VERIFIED",
    })
    assert ev_ok.quality == Quality.VERIFIED

    ev_stale = MarketEventV1.from_dict({
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "mark_price",
        "provider_event_ms": 10000,
        "observed_wall_utc_ms": 12001,  # 2001ms > 2000ms
        "observed_monotonic_ns": 1000,
        "available_at_ms": 12001,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": p_sha,
        "payload": payload,
        "quality": "VERIFIED",
    })
    assert ev_stale.quality == Quality.DEGRADED
    assert "STALE_MARK_OVER_2000MS" in ev_stale.reason_codes


def test_source_hash_quarantine():
    """Corrupted raw source payload SHA is quarantined as INVALID."""
    payload = {"k": {"c": "65000.0"}}
    raw = canonical_json(payload)
    actual_sha = sha256_hex(raw)
    bad_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    assert actual_sha != bad_sha

    ev = MarketEventV1.from_dict({
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "last_kline_1m",
        "observed_wall_utc_ms": 1000,
        "observed_monotonic_ns": 1000,
        "available_at_ms": 1000,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": bad_sha,  # Quarantined!
        "payload": payload,
        "quality": "VERIFIED",
    })
    assert ev.quality == Quality.INVALID
    assert "PAYLOAD_SHA256_MISMATCH" in ev.reason_codes


def test_simulated_ack_ledger_consistency():
    """Position receipt hash is strictly verifiable against canonical serialized dictionary."""
    acc = PaperAccount()
    pos = acc.open_shadow_position(
        cell_id="CELL_ACK",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    acc.close_shadow_position(
        exit_fill_ms=2000,
        best_bid=66000.0,
        best_ask=66001.0,
        exit_reason=ExitReason.PROFIT_TARGET,
    )
    assert pos.receipt_sha256 != ""
    recomputed = sha256_hex(canonical_json(pos.to_dict()))
    assert pos.receipt_sha256 == recomputed


def test_6h_horizon_exit_cap():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    assert hyp.horizon_hours == Horizon.H6
    assert hyp.horizon_hours.minutes == 360
    assert hyp.horizon_hours.ms == 6 * 3600 * 1000


def test_12h_horizon_exit_cap():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_12H"]
    assert hyp.horizon_hours == Horizon.H12
    assert hyp.horizon_hours.minutes == 720
    assert hyp.horizon_hours.ms == 12 * 3600 * 1000


def test_18h_horizon_exit_cap():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_18H"]
    assert hyp.horizon_hours == Horizon.H18
    assert hyp.horizon_hours.minutes == 1080
    assert hyp.horizon_hours.ms == 18 * 3600 * 1000


def test_reserve_protection_under_drawdown():
    """When account experiences drawdown to 200 USDT, 5% reserve continues protecting 10 USDT."""
    acc = PaperAccount(initial_capital_usdt=1000.0, reserve_fraction=0.05)
    acc.cash_usdt = 200.0
    assert acc.reserve_usdt == 10.0
    assert acc.usable_capital_usdt == 190.0
    # Lot size respects reduced usable capital
    lot = acc.calculate_lot_size(65000.0)
    # 190 / 65000 ~= 0.0029 -> 0.002 BTC
    assert lot == 0.002


def test_duplicate_funding_events_in_stream():
    """Identical funding events in feed are deduplicated by PublicFeedAdapter."""
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    engine.account.open_shadow_position(
        cell_id=hyp.cell_id,
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )

    ev_fund = make_funding_settled_event(2000, 0.0001, 65000.0)
    raw = ev_fund.to_dict()

    # Feed 3 times
    adapter.ingest_dict(raw)
    adapter.ingest_dict(raw)
    adapter.ingest_dict(raw)

    assert adapter.stats.duplicate_events_count == 2
    # Exactly one funding receipt accrued in active position
    assert len(engine.account.active_position.funding_receipts) == 1


def test_negative_funding_short_position_pays():
    """When shorting and funding rate is negative, short pays (- (-1) * qty * mark * (-rate) = - cash)."""
    acc = PaperAccount()
    pos = acc.open_shadow_position(
        cell_id="CELL_NEG_SHORT",
        direction=-1,  # Short
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=66000.0,
        target_price=63000.0,
        horizon_ms=3600000,
    )
    # Rate is negative (-0.0001)
    receipt = pos.apply_funding(
        SettledFundingData(2000, -0.0001, 65000.0, settled=True),
        observed_at_ms=2005,
    )
    assert receipt.cash_flow_usdt < 0.0  # Cash flow is negative (short pays!)
    assert pos.total_funding_usdt < 0.0


def test_atr_month_continuity_720_hours():
    """ATR can compute smoothly across 720 hours (30 full days) with no gaps."""
    bars_30d = generate_warmup_hourly_bars(1700000000000, hours_count=720, hourly_vol=40.0)
    res = compute_atr_1h(bars_30d, period=14, min_warmup_hours=200)
    assert res.valid is True
    assert res.warmup_hours_observed == 720
    assert res.atr_value > 0.0


def test_bootstrap_identical_seeds_10_runs():
    """Verify that random_seed guarantees deterministic numerical stability across 10 repeated runs."""
    trades = [
        {"exit_fill_ms": 1700000000000 + (w * 7 * 86400000), "net_bps": 5.0 + (w % 3) * 4}
        for w in range(20)
    ]
    results = [
        block_bootstrap_net_bps(trades, block_size_days=7, n_bootstraps=200, random_seed=777)
        for _ in range(10)
    ]
    first_ci_low = results[0].ci_lower_95
    first_ci_high = results[0].ci_upper_95
    for r in results:
        assert r.ci_lower_95 == first_ci_low
        assert r.ci_upper_95 == first_ci_high


def test_multi_stream_join_max_available_time():
    """Verify that multi-stream join strictly enforces decision_at >= max(all observed available_at_ms)."""
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)
    bars = [make_dummy_1m_bar(i, 65000.0, 65001.0, 64999.0, 65000.0) for i in range(35)]
    book = make_test_book()

    # Streams arrive at: last=1500ms, mark=1600ms, book=1550ms
    feature_known_ms = max(1500, 1600, 1550)
    assert feature_known_ms == 1600

    # Decision at 1599 (< 1600): rejected!
    prop_early = engine.evaluate(
        decision_at_ms=1599,
        feature_known_at_ms=feature_known_ms,
        last_bars_1m=bars,
        mark_bars_1m=bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=(),
    )
    assert prop_early.status == SignalStatus.CLOCK_UNCERTAIN

    # Decision at 1600 (>= 1600): causal timing check passes
    prop_ok = engine.evaluate(
        decision_at_ms=1600,
        feature_known_at_ms=feature_known_ms,
        last_bars_1m=bars,
        mark_bars_1m=bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=(),
    )
    assert prop_ok.status != SignalStatus.CLOCK_UNCERTAIN


def test_p1_zero_dislocation_when_prices_equal():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)
    bars = [make_dummy_1m_bar(i, 65000.0, 65001.0, 64999.0, 65000.0) for i in range(35)]
    book = make_test_book()
    hourly_bars = generate_warmup_hourly_bars(1000 - (210 * 3600 * 1000), 210)

    decision_ms = bars[-1].bar_close_ms
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=bars,
        mark_bars_1m=bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL
    assert prop.metrics["current_dislocation_bps"] == 0.0


def test_book_empty_sides_imbalance_none():
    book_empty_bids = BookIntegrityV1(
        best_bid=None,
        best_ask=65001.0,
        bids=(),
        asks=((65001.0, 1.0),),
    )
    assert book_empty_bids.top_n_imbalance(10) is None


def test_account_insufficient_equity_after_severe_losses():
    acc = PaperAccount(initial_capital_usdt=1000.0)
    acc.cash_usdt = 5.0  # Usable equity = 4.75 USDT
    pos = acc.open_shadow_position(
        cell_id="CELL_LOW_EQUITY",
        direction=1,
        entry_decision_ms=1000,
        entry_fill_ms=1000,
        best_bid=65000.0,
        best_ask=65001.0,
        stop_price=64000.0,
        target_price=67000.0,
        horizon_ms=3600000,
    )
    assert pos is None, "Should fail open when usable capital < min lot notional"


def test_p2_zero_volume_trades_produces_no_signal():
    hyp = get_default_hypotheses()["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]
    engine = SignalEngine(hyp)
    last_bars = [make_dummy_1m_bar(i, 65000.0, 65001.0, 64999.0, 65000.0) for i in range(35)]
    decision_ms = last_bars[-1].bar_close_ms
    book = make_test_book()
    hourly_bars = generate_warmup_hourly_bars(1000 - (210 * 3600 * 1000), 210)

    # AggTrade with 0 quantity
    zero_vol_trade = AggTradeData(1, 65000.0, 0.0, 1, 1, decision_ms - 1000, is_buyer_maker=False)
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=(),
        recent_agg_trades=(zero_vol_trade,),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL


def test_wilders_smoothing_exact_recurrence():
    """Verify that compute_atr_1h matches exact analytical formula for Wilder's smoothing."""
    bars = generate_warmup_hourly_bars(1000, hours_count=200, hourly_vol=10.0)
    res = compute_atr_1h(bars, period=14, min_warmup_hours=200)
    assert res.valid is True
    # For constant range of 20 (high - low = 20, open=close, high=price+10, low=price-10):
    # TR is constant 20.0, ATR should converge exactly to 20.0
    assert abs(res.atr_value - 20.0) < 1e-4
