"""Deterministic unit tests for PublicFeedAdapter and fixture generators.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.adapter import (
    PublicFeedAdapter,
)
from scripts.strategy_research.forward_shadow_research_r1.contract import (
    Channel,
    Quality,
)
from scripts.strategy_research.forward_shadow_research_r1.execution import (
    ShadowExecutionEngine,
)
from scripts.strategy_research.forward_shadow_research_r1.fixtures import (
    generate_warmup_hourly_bars,
    make_agg_trade_event,
    make_funding_settled_event,
    make_kline_event,
    make_test_book,
)
from scripts.strategy_research.forward_shadow_research_r1.registry import (
    get_default_hypotheses,
)


def test_adapter_empty_line():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)
    res = adapter.ingest_line("   \n")
    assert res is None
    assert adapter.stats.total_events_received == 0


def test_adapter_valid_kline_ingestion():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    ev = make_kline_event(
        channel=Channel.LAST_KLINE_1M,
        bar_open_ms=1000,
        bar_close_ms=60999,
        open_price=65000.0,
        high_price=65010.0,
        low_price=64990.0,
        close_price=65005.0,
    )
    raw = json.dumps(ev.to_dict())
    ingested = adapter.ingest_line(raw)

    assert ingested is not None
    assert adapter.stats.total_events_received == 1
    assert adapter.stats.verified_events_count == 1
    assert adapter.stats.channel_counts["last_kline_1m"] == 1
    assert adapter.pending_last_1m is not None


def test_adapter_deduplication():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    ev = make_agg_trade_event(
        trade_id=12345,
        trade_time_ms=1000,
        price=65000.0,
        quantity=1.0,
        is_buyer_maker=False,
    )
    raw = json.dumps(ev.to_dict())

    # Ingest first time: accepted
    r1 = adapter.ingest_line(raw)
    assert r1 is not None

    # Ingest second time: duplicate dropped
    r2 = adapter.ingest_line(raw)
    assert r2 is None
    assert adapter.stats.total_events_received == 2
    assert adapter.stats.duplicate_events_count == 1


def test_adapter_clock_jump_detection():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    ev1 = make_kline_event(
        channel=Channel.LAST_KLINE_1M,
        bar_open_ms=1000,
        bar_close_ms=60999,
        open_price=65000.0,
        high_price=65010.0,
        low_price=64990.0,
        close_price=65005.0,
        observed_wall_utc_ms=5000,
        observed_monotonic_ns=100,
    )
    adapter.ingest_dict(ev1.to_dict())

    # Second event has greater monotonic order but wall time jumps backwards
    ev2 = make_kline_event(
        channel=Channel.LAST_KLINE_1M,
        bar_open_ms=61000,
        bar_close_ms=120999,
        open_price=65005.0,
        high_price=65015.0,
        low_price=64995.0,
        close_price=65010.0,
        observed_wall_utc_ms=4500,  # Wall jumped backwards!
        observed_monotonic_ns=200,   # Monotonic jumped forward!
    )
    ingested2 = adapter.ingest_dict(ev2.to_dict())

    assert ingested2 is not None
    assert ingested2.quality == Quality.INVALID
    assert "RECEIVER_CLOCK_JUMP_BACKWARD" in ingested2.reason_codes
    assert adapter.stats.clock_uncertain_events_count == 1


def test_adapter_pairs_aligned_last_and_mark_bars():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    t_open = 1700000000000
    t_close = t_open + 59999

    ev_last = make_kline_event(Channel.LAST_KLINE_1M, t_open, t_close, 65000, 65005, 64995, 65000)
    ev_mark = make_kline_event(Channel.MARK_PRICE, t_open, t_close, 65000, 65002, 64998, 65000)

    adapter.ingest_dict(ev_last.to_dict())
    assert adapter.pending_last_1m is not None
    assert len(engine.last_bars_1m) == 0

    adapter.ingest_dict(ev_mark.to_dict())
    # After mark arrives, pair is flushed to engine!
    assert adapter.pending_last_1m is None
    assert adapter.pending_mark_1m is None
    assert len(engine.last_bars_1m) == 1
    assert len(engine.mark_bars_1m) == 1


def test_adapter_routes_agg_trade():
    hyp = get_default_hypotheses()["P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    ev = make_agg_trade_event(1001, 1700000000000, 65000.0, 2.5, is_buyer_maker=False)
    adapter.ingest_dict(ev.to_dict())

    assert len(engine.agg_trades_buffer) == 1
    assert engine.agg_trades_buffer[0].aggregate_trade_id == 1001


def test_adapter_routes_funding_settled():
    hyp = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
    engine = ShadowExecutionEngine(hyp)
    adapter = PublicFeedAdapter(engine)

    # Open position
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
    assert engine.account.active_position is not None

    ev_fund = make_funding_settled_event(2000, 0.0001, 65000.0)
    adapter.ingest_dict(ev_fund.to_dict())

    assert len(engine.account.active_position.funding_receipts) == 1


def test_fixture_generators():
    book = make_test_book(best_bid=65000.0, best_ask=65002.0, depth_levels=10)
    assert book.best_bid == 65000.0
    assert book.best_ask == 65002.0
    assert len(book.bids) == 10
    assert len(book.asks) == 10

    warmup = generate_warmup_hourly_bars(1700000000000, hours_count=210)
    assert len(warmup) == 210
    # Check continuous
    for i in range(1, len(warmup)):
        assert warmup[i].bar_open_ms == warmup[i - 1].bar_close_ms + 1
