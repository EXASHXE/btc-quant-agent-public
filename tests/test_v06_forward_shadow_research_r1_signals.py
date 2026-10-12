"""Deterministic unit tests for mechanistic signals, ATR calculations, and 6 observation cells.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.contract import (
    AggTradeData,
    BarData,
    BookIntegrityV1,
)
from scripts.strategy_research.forward_shadow_research_r1.fixtures import (
    generate_warmup_hourly_bars,
    make_test_book,
)
from scripts.strategy_research.forward_shadow_research_r1.registry import (
    SELECTABLE_OBSERVATION_CELLS,
    get_default_hypotheses,
)
from scripts.strategy_research.forward_shadow_research_r1.signals import (
    AggregatedBar,
    SignalDirection,
    SignalEngine,
    SignalStatus,
    aggregate_1m_bars,
    compute_atr_1h,
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


def test_aggregate_1m_bars_success():
    bars = [make_dummy_1m_bar(i, 65000.0, 65010.0, 64990.0, 65005.0) for i in range(5)]
    agg = aggregate_1m_bars(bars, 5)
    assert agg is not None
    assert agg.bar_count == 5
    assert agg.open == 65000.0
    assert agg.high == 65010.0
    assert agg.low == 64990.0
    assert agg.close == 65005.0
    assert agg.volume == 50.0


def test_aggregate_1m_bars_fails_on_unclosed_bar():
    bars = [make_dummy_1m_bar(i, 65000.0, 65010.0, 64990.0, 65005.0) for i in range(5)]
    bars[2] = make_dummy_1m_bar(2, 65000.0, 65010.0, 64990.0, 65005.0, closed=False)
    agg = aggregate_1m_bars(bars, 5)
    assert agg is None


def test_aggregate_1m_bars_fails_on_gap():
    bars = [make_dummy_1m_bar(i, 65000.0, 65010.0, 64990.0, 65005.0) for i in range(5)]
    # Introduce a 1-minute gap at index 3
    bad_bar = BarData(
        bar_open_ms=bars[2].bar_close_ms + 60001,  # Gap!
        bar_close_ms=bars[2].bar_close_ms + 120000,
        closed=True,
        open=65000.0,
        high=65010.0,
        low=64990.0,
        close=65005.0,
        volume=10.0,
    )
    bars[3] = bad_bar
    agg = aggregate_1m_bars(bars, 5)
    assert agg is None


def test_atr_1h_insufficient_warmup():
    bars = generate_warmup_hourly_bars(1700000000000, hours_count=199)
    res = compute_atr_1h(bars, period=14, min_warmup_hours=200)
    assert res.valid is False
    assert "WARMUP_INSUFFICIENT" in res.reason


def test_atr_1h_gap_invalidated():
    bars = generate_warmup_hourly_bars(1700000000000, hours_count=205)
    # Inject gap between bar 100 and 101
    b100 = bars[100]
    bad_b101 = AggregatedBar(
        bar_open_ms=b100.bar_close_ms + 5000,  # Gap!
        bar_close_ms=b100.bar_close_ms + 3605000,
        open=65000.0,
        high=65050.0,
        low=64950.0,
        close=65000.0,
        volume=100.0,
        is_complete=True,
        bar_count=60,
    )
    corrupted_bars = list(bars)
    corrupted_bars[101] = bad_b101
    res = compute_atr_1h(corrupted_bars, period=14, min_warmup_hours=200)
    assert res.valid is False
    assert "ATR_GAP_DETECTED" in res.reason


def test_atr_1h_valid_warmup():
    bars = generate_warmup_hourly_bars(1700000000000, hours_count=205, hourly_vol=50.0)
    res = compute_atr_1h(bars, period=14, min_warmup_hours=200)
    assert res.valid is True
    assert res.atr_value > 0.0
    assert abs(res.stop_distance_1r - res.atr_value) < 1e-6
    assert abs(res.target_distance_2r - (2.0 * res.atr_value)) < 1e-6


def test_p1_basis_reversion_long_signal():
    hypotheses = get_default_hypotheses()
    hyp = hypotheses["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)

    # 35 1m bars
    # Mark is steady at 65000.0
    # Last is at 65000 - 40.0 (-61.5 bps) at decision, restoring from -65000 - 60.0 (-92 bps) at 5m prior
    mark_bars = [make_dummy_1m_bar(i, 65000.0, 65005.0, 64995.0, 65000.0) for i in range(35)]
    last_bars = []
    for i in range(35):
        if i < 29:
            p = 65000.0 - 65.0
        elif i < 34:
            p = 65000.0 - 55.0
        else:
            p = 65000.0 - 35.0  # At index 34 (decision): Last is restoring upward!
        last_bars.append(make_dummy_1m_bar(i, p, p + 2.0, p - 2.0, p))

    book = make_test_book(best_bid=64964.5, best_ask=64965.5)
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    decision_ms = last_bars[-1].bar_close_ms
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )

    assert prop.status == SignalStatus.PROPOSED
    assert prop.direction == SignalDirection.LONG
    # Long enters at best_ask, never at Mark!
    assert prop.proposed_entry_price == book.best_ask
    assert prop.stop_price < prop.proposed_entry_price
    assert prop.target_price > prop.proposed_entry_price


def test_p1_basis_reversion_short_signal():
    hypotheses = get_default_hypotheses()
    hyp = hypotheses["P1_BASIS_REVERSION_V2_SHADOW_12H"]
    engine = SignalEngine(hyp)

    # Mark is steady at 65000.0
    # Last is at 65000 + 40.0 (+61.5 bps) at decision, restoring downward from +60.0 at 5m prior
    mark_bars = [make_dummy_1m_bar(i, 65000.0, 65005.0, 64995.0, 65000.0) for i in range(35)]
    last_bars = []
    for i in range(35):
        if i < 29:
            p = 65000.0 + 65.0
        elif i < 34:
            p = 65000.0 + 55.0
        else:
            p = 65000.0 + 35.0  # Restoring downward towards Mark
        last_bars.append(make_dummy_1m_bar(i, p, p + 2.0, p - 2.0, p))

    book = make_test_book(best_bid=65034.5, best_ask=65035.5)
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    decision_ms = last_bars[-1].bar_close_ms
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )

    assert prop.status == SignalStatus.PROPOSED
    assert prop.direction == SignalDirection.SHORT
    # Short enters at best_bid, never Mark!
    assert prop.proposed_entry_price == book.best_bid
    assert prop.stop_price > prop.proposed_entry_price
    assert prop.target_price < prop.proposed_entry_price


def test_p1_fails_dislocation_below_threshold():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)

    # Dislocation only 1.0 USDT (~0.15 bp < 5bp)
    mark_bars = [make_dummy_1m_bar(i, 65000.0, 65005.0, 64995.0, 65000.0) for i in range(35)]
    last_bars = [make_dummy_1m_bar(i, 65001.0, 65005.0, 64995.0, 65001.0) for i in range(35)]
    book = make_test_book(best_bid=65000.5, best_ask=65001.5)
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    decision_ms = last_bars[-1].bar_close_ms
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL
    assert "DISLOCATION_BELOW_THRESHOLD" in prop.reason_codes


def test_p1_fails_when_premium_widening():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)

    mark_bars = [make_dummy_1m_bar(i, 65000.0, 65005.0, 64995.0, 65000.0) for i in range(35)]
    last_bars = []
    # Premium widening away from zero: 5m ago was -20, now is -40!
    for i in range(35):
        p = 65000.0 - (20.0 if i < 34 else 45.0)
        last_bars.append(make_dummy_1m_bar(i, p, p + 1.0, p - 1.0, p))

    book = make_test_book(best_bid=64954.5, best_ask=64955.5)
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    decision_ms = last_bars[-1].bar_close_ms
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL_PREMIUM_NOT_RESTORING


def test_p1_fails_on_abnormal_30m_volatility():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)

    # 30m range > 300 bps (e.g. 65000 * 0.03 = 1950 points)
    mark_bars = [make_dummy_1m_bar(i, 65000.0, 65005.0, 64995.0, 65000.0) for i in range(35)]
    last_bars = []
    for i in range(35):
        if i == 10:
            # Extreme spike causing abnormal 30m range
            last_bars.append(make_dummy_1m_bar(i, 65000.0, 68000.0, 64000.0, 65000.0))
        elif i < 34:
            last_bars.append(make_dummy_1m_bar(i, 64940.0, 64945.0, 64935.0, 64940.0))
        else:
            last_bars.append(make_dummy_1m_bar(i, 64960.0, 64965.0, 64955.0, 64960.0))

    book = make_test_book(best_bid=64959.5, best_ask=64960.5)
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    decision_ms = last_bars[-1].bar_close_ms
    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=mark_bars,
        recent_agg_trades=(),
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL_ABNORMAL_VOLATILITY


def test_p2_orderflow_resilience_long_signal():
    hyp = get_default_hypotheses()["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]
    engine = SignalEngine(hyp)

    last_bars = [make_dummy_1m_bar(i, 65000.0 + (i * 0.1), 65002.0, 64998.0, 65000.0 + (i * 0.1)) for i in range(35)]
    decision_ms = last_bars[-1].bar_close_ms

    # Generate aggTrades with heavy buyer aggression (is_buyer_maker = False)
    trades = []
    for i in range(20):
        trades.append(
            AggTradeData(
                aggregate_trade_id=i + 1,
                price=65000.0,
                quantity=1.0,
                first_trade_id=i * 10,
                last_trade_id=i * 10 + 1,
                trade_time_ms=decision_ms - (10 * 60 * 1000) + (i * 1000),
                is_buyer_maker=False,  # Buy aggressor!
            )
        )

    # Skewed book with bid imbalance > +0.10
    book = make_test_book(
        best_bid=65003.0,
        best_ask=65004.0,
        bids_skew=2.0,
        asks_skew=0.8,
    )
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=(),
        recent_agg_trades=trades,
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.PROPOSED
    assert prop.direction == SignalDirection.LONG
    assert prop.proposed_entry_price == book.best_ask


def test_p2_orderflow_maker_flag_reversed_changes_direction():
    hyp = get_default_hypotheses()["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]
    engine = SignalEngine(hyp)

    # Close now <= close 30m ago for short filter
    last_bars = [make_dummy_1m_bar(i, 65005.0 - (i * 0.1), 65006.0, 64998.0, 65005.0 - (i * 0.1)) for i in range(35)]
    decision_ms = last_bars[-1].bar_close_ms

    # Flipped maker flag: is_buyer_maker = True => seller aggressor
    trades = []
    for i in range(20):
        trades.append(
            AggTradeData(
                aggregate_trade_id=i + 1,
                price=65000.0,
                quantity=1.0,
                first_trade_id=i * 10,
                last_trade_id=i * 10 + 1,
                trade_time_ms=decision_ms - (10 * 60 * 1000) + (i * 1000),
                is_buyer_maker=True,  # Seller aggressor!
            )
        )

    # Skewed book with ask imbalance (< -0.10)
    book = make_test_book(
        best_bid=65001.0,
        best_ask=65002.0,
        bids_skew=0.7,
        asks_skew=2.2,
    )
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=(),
        recent_agg_trades=trades,
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.PROPOSED
    assert prop.direction == SignalDirection.SHORT
    assert prop.proposed_entry_price == book.best_bid


def test_p2_incomplete_book_fails():
    hyp = get_default_hypotheses()["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]
    engine = SignalEngine(hyp)

    last_bars = [make_dummy_1m_bar(i, 65000.0, 65002.0, 64998.0, 65000.0) for i in range(35)]
    decision_ms = last_bars[-1].bar_close_ms

    # Book with discontinuous L2
    bad_book = BookIntegrityV1(
        best_bid=65000.0,
        best_ask=65001.0,
        continuous=False,  # Discontinuous!
        bids=((65000.0, 1.0),) * 10,
        asks=((65001.0, 1.0),) * 10,
    )
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=(),
        recent_agg_trades=(),
        latest_book=bad_book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL_INCOMPLETE_BOOK


def test_p2_30m_directional_filter_mismatch_fails():
    hyp = get_default_hypotheses()["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]
    engine = SignalEngine(hyp)

    # For LONG, price is falling over 30m: close_now < close_30m_ago
    last_bars = [make_dummy_1m_bar(i, 65050.0 - i, 65052.0 - i, 65048.0 - i, 65050.0 - i) for i in range(35)]
    decision_ms = last_bars[-1].bar_close_ms

    trades = [
        AggTradeData(1, 65000.0, 5.0, 1, 2, decision_ms - 5000, is_buyer_maker=False)
    ]
    book = make_test_book(best_bid=65010.0, best_ask=65011.0, bids_skew=2.0, asks_skew=0.8)
    hourly_bars = generate_warmup_hourly_bars(1700000000000 - (210 * 3600 * 1000), 210)

    prop = engine.evaluate(
        decision_at_ms=decision_ms,
        feature_known_at_ms=decision_ms,
        last_bars_1m=last_bars,
        mark_bars_1m=(),
        recent_agg_trades=trades,
        latest_book=book,
        hourly_bars_for_atr=hourly_bars,
    )
    assert prop.status == SignalStatus.NO_SIGNAL_DIRECTIONAL_FILTER_MISMATCH


def test_causal_asof_timing_decision_before_known_fails():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = SignalEngine(hyp)
    bars = [make_dummy_1m_bar(i, 65000.0, 65001.0, 64999.0, 65000.0) for i in range(35)]

    # decision_at_ms strictly < feature_known_at_ms!
    prop = engine.evaluate(
        decision_at_ms=1000,
        feature_known_at_ms=2000,
        last_bars_1m=bars,
        mark_bars_1m=bars,
        recent_agg_trades=(),
        latest_book=make_test_book(),
        hourly_bars_for_atr=(),
    )
    assert prop.status == SignalStatus.CLOCK_UNCERTAIN
    assert "DECISION_BEFORE_FEATURE_KNOWN" in prop.reason_codes


def test_exactly_six_selectable_observation_cells():
    cells = SELECTABLE_OBSERVATION_CELLS
    assert len(cells) == 6
    assert set(cells) == {
        "P1_BASIS_REVERSION_V2_SHADOW_6H",
        "P1_BASIS_REVERSION_V2_SHADOW_12H",
        "P1_BASIS_REVERSION_V2_SHADOW_18H",
        "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H",
        "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_12H",
        "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_18H",
    }
