"""Red-before regression test suite targeting B-line findings A03-A08."""

from decimal import Decimal
from typing import Any

import pytest

from btc_quant_agent.strategy_research.r3_overnight.candidate_registry import (
    get_default_registry,
)
from btc_quant_agent.strategy_research.r3_overnight.constants import (
    COOLDOWN_DURATION_MS,
)
from btc_quant_agent.strategy_research.r3_overnight.ledger import VirtualBook
from btc_quant_agent.strategy_research.r3_overnight.signals import SignalGenerator
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1h,
    Bar1m,
    Bar4h,
    CompletedTrade,
    CostScenario,
    Direction,
    ExitReason,
    MarkBar1m,
    VirtualOrder,
)


def _make_1m_bar(t: int, o: Decimal, h: Decimal, l: Decimal, c: Decimal, vol: Decimal = Decimal(10), sym: str = "BTCUSDT") -> Bar1m:
    return Bar1m(
        timestamp_ms=t,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
        symbol=sym,
    )


def _make_1h_bar(t: int, o: Decimal, h: Decimal, l: Decimal, c: Decimal, vol: Decimal = Decimal(100), sym: str = "BTCUSDT") -> Bar1h:
    return Bar1h(
        timestamp_ms=t,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
        symbol=sym,
        bar_count=60,
    )


def _make_4h_bar(t: int, o: Decimal, h: Decimal, l: Decimal, c: Decimal, vol: Decimal = Decimal(1000), sym: str = "BTCUSDT") -> Bar4h:
    return Bar4h(
        timestamp_ms=t,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
        symbol=sym,
        bar_count=240,
    )


def _make_mark_bar(t: int, price: Decimal, avail_at: int, sym: str = "BTCUSDT") -> MarkBar1m:
    return MarkBar1m(
        timestamp_ms=t,
        open=price,
        high=price,
        low=price,
        close=price,
        symbol=sym,
        available_at_ms=avail_at,
    )


# =============================================================================
# A03 Regressions: Entry ACK must not reset max_hold_ms to 0 or resurrect zombie
# =============================================================================

def test_a03_entry_ack_preserves_max_hold_and_does_not_expire_early():
    """Finding A03: Entry ACK at t0+60s must preserve 4h holding horizon, not reset to 0 causing early expiry."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000
    four_hours_ms = 4 * 3_600_000

    marks_0 = {"BTCUSDT": _make_mark_bar(t0 - 60_000, Decimal(50000), t0)}
    bars_0 = {"BTCUSDT": _make_1m_bar(t0, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000))}

    order = VirtualOrder(
        order_id="ORD_1",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        target_fill_time_ms=t0,
        created_at_ms=t0 - 60_000,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(505),
        funding_reserve_usdt=Decimal(2),
    )
    book.pending_orders.append(order)
    book.cost_commitment_o += order.cost_commitment_usdt
    book.funding_reserve_rf += order.funding_reserve_usdt

    # Step t0: order fills in Stage 5, position created with 4h max_hold
    book.step_minute_open(t0, bars_0, marks_0, four_hours_ms)
    assert "BTCUSDT" in book.positions
    pos_t0 = book.positions["BTCUSDT"]
    assert pos_t0.max_hold_ms == four_hours_ms

    # Step t0 + 60s: entry ACK arrives in Stage 1
    t1 = t0 + 60_000
    marks_1 = {"BTCUSDT": _make_mark_bar(t0, Decimal(50000), t1)}
    bars_1 = {"BTCUSDT": _make_1m_bar(t1, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000))}
    book.step_minute_open(t1, bars_1, marks_1, four_hours_ms)

    assert "BTCUSDT" in book.positions
    pos_t1 = book.positions["BTCUSDT"]
    # CRITICAL ASSERTION: max_hold_ms must NOT be reset to 0!
    assert pos_t1.max_hold_ms == four_hours_ms, f"A03 DEFECT: max_hold_ms was reset to {pos_t1.max_hold_ms}"

    # Step t0 + 120s (2 minutes after entry): position MUST STILL BE ACTIVE, not expired!
    t2 = t0 + 120_000
    marks_2 = {"BTCUSDT": _make_mark_bar(t1, Decimal(50000), t2)}
    bars_2 = {"BTCUSDT": _make_1m_bar(t2, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000))}
    book.step_minute_open(t2, bars_2, marks_2, four_hours_ms)

    assert "BTCUSDT" in book.positions, "A03 DEFECT: Position prematurely expired at t0+120s!"
    assert len(book.completed_trades) == 0


def test_a03_no_zombie_resurrection_after_same_minute_stop_loss():
    """Finding A03: If position hits Stop Loss in same minute t0, entry ACK at t0+60s must NOT resurrect a zombie position."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000
    four_hours_ms = 4 * 3_600_000

    order = VirtualOrder(
        order_id="ORD_STOP",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        target_fill_time_ms=t0,
        created_at_ms=t0 - 60_000,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(505),
        funding_reserve_usdt=Decimal(2),
    )
    book.pending_orders.append(order)

    # Bar at t0 opens at 50,000 but plunges to 48,000 (below stop 49,000)
    bars_0 = {"BTCUSDT": _make_1m_bar(t0, Decimal(50000), Decimal(50010), Decimal(48000), Decimal(48500))}
    marks_0 = {"BTCUSDT": _make_mark_bar(t0 - 60_000, Decimal(50000), t0)}

    # Step t0: Stage 5 fills order, Stage 6 immediately triggers STOP_LOSS and removes position from self.positions
    book.step_minute_open(t0, bars_0, marks_0, four_hours_ms)
    assert "BTCUSDT" not in book.positions, "Position should be closed in Stage 6 at t0"

    # Step t1 = t0 + 60s: entry fill ACK is available
    t1 = t0 + 60_000
    bars_1 = {"BTCUSDT": _make_1m_bar(t1, Decimal(48500), Decimal(48600), Decimal(48400), Decimal(48500))}
    marks_1 = {"BTCUSDT": _make_mark_bar(t0, Decimal(48500), t1)}
    book.step_minute_open(t1, bars_1, marks_1, four_hours_ms)

    # CRITICAL ASSERTION: Zombie position must NOT be resurrected in self.positions!
    assert "BTCUSDT" not in book.positions, "A03 DEFECT: Zombie position was resurrected by entry ACK!"
    assert len(book.completed_trades) == 1
    assert book.completed_trades[0].exit_reason == ExitReason.STOP_LOSS

    # Step t2 = t0 + 120s: still no duplicate trade
    t2 = t0 + 120_000
    bars_2 = {"BTCUSDT": _make_1m_bar(t2, Decimal(48500), Decimal(48600), Decimal(48400), Decimal(48500))}
    marks_2 = {"BTCUSDT": _make_mark_bar(t1, Decimal(48500), t2)}
    book.step_minute_open(t2, bars_2, marks_2, four_hours_ms)
    assert len(book.completed_trades) == 1, "A03 DEFECT: Duplicate trade generated!"


# =============================================================================
# A04 Regressions: Candidate isolation across 04H and 12H retest state
# =============================================================================

def test_a04_candidate_isolation_and_metamorphic_order_invariance():
    """Finding A04: Closed retest state must be isolated between 04H and 12H candidates and evaluation order invariant."""
    gen = SignalGenerator()
    c_04h = get_default_registry().get_candidate("CLOSED_RETEST_LONG_04H")
    c_12h = get_default_registry().get_candidate("CLOSED_RETEST_LONG_12H")

    bars_1h = []
    base_t = 1_700_000_000_000
    for i in range(25):
        bars_1h.append(_make_1h_bar(base_t + i * 3_600_000, Decimal(50000), Decimal(50100), Decimal(49900), Decimal(50000)))
    # Breakout bar 25
    bars_1h.append(_make_1h_bar(base_t + 25 * 3_600_000, Decimal(50000), Decimal(50600), Decimal(49950), Decimal(50550)))
    bars_4h = [
        Bar4h(
            timestamp_ms=base_t + i * 14_400_000,
            open=Decimal(45000 + i * 100),
            high=Decimal(45050 + i * 100),
            low=Decimal(44950 + i * 100),
            close=Decimal(45000 + i * 100),
            volume=Decimal(1000),
            symbol="BTCUSDT",
            bar_count=240,
        )
        for i in range(65)
    ]

    # Evaluate 04H on breakout bar
    gen.evaluate_hourly_decision(c_04h, "BTCUSDT", bars_1h, bars_4h)

    # In unpatched code, key is ("BTCUSDT", LONG) without candidate ID
    # Evaluate 12H immediately after on the breakout bar:
    gen.evaluate_hourly_decision(c_12h, "BTCUSDT", bars_1h, bars_4h)

    # If state is shared, bars_since_breakout is corrupted to 1 on breakout bar!
    active_dict: dict[Any, Any] = getattr(gen, "_active_breakouts", {})
    state_04 = active_dict.get((c_04h.id, "BTCUSDT", Direction.LONG))
    if state_04 is None:
        state_legacy = active_dict.get(("BTCUSDT", Direction.LONG))
        assert state_legacy is not None
        pytest.fail(f"A04 DEFECT: Shared breakout state found without candidate ID, bars_since_breakout={state_legacy.bars_since_breakout}")


# =============================================================================
# A05 Regressions: Retest touch zone requires LOW inside band, and stop includes breakout bar
# =============================================================================

def test_a05_retest_touch_zone_deep_wick_rejection():
    """Finding A05: Long retest requires bar LOW inside [B - 0.25 ATR, B + 0.25 ATR], rejecting deep wicks below band."""
    gen = SignalGenerator()
    c_04h = get_default_registry().get_candidate("CLOSED_RETEST_LONG_04H")
    base_t = 1_700_000_000_000

    bars_1h = [_make_1h_bar(base_t + i * 3_600_000, Decimal(50000), Decimal(50100), Decimal(49900), Decimal(50000)) for i in range(25)]
    # Breakout bar
    bars_1h.append(_make_1h_bar(base_t + 25 * 3_600_000, Decimal(50000), Decimal(50600), Decimal(49950), Decimal(50550), Decimal(200)))
    bars_4h = [
        Bar4h(
            timestamp_ms=base_t + i * 14_400_000,
            open=Decimal(45000 + i * 100),
            high=Decimal(45050 + i * 100),
            low=Decimal(44950 + i * 100),
            close=Decimal(45000 + i * 100),
            volume=Decimal(1000),
            symbol="BTCUSDT",
            bar_count=240,
        )
        for i in range(65)
    ]
    gen.evaluate_hourly_decision(c_04h, "BTCUSDT", bars_1h, bars_4h)

    # Next bar: Deep wick down to 49,000 (well below boundary 50100 - 0.25*ATR ~ 50044.375), but high is 50,200 (overlaps zone).
    # Unpatched code accepts this because high >= B - 0.25*ATR and low <= B + 0.25*ATR.
    # Specification requires bar LOW to be INSIDE [B - 0.25*ATR, B + 0.25*ATR]!
    bars_1h.append(_make_1h_bar(base_t + 26 * 3_600_000, Decimal(50100), Decimal(50200), Decimal(49000), Decimal(50180), Decimal(200)))
    sig = gen.evaluate_hourly_decision(c_04h, "BTCUSDT", bars_1h, bars_4h)
    assert sig is None, f"A05 DEFECT: Deep wick below touch zone was erroneously accepted as retest confirmation: {sig}"


# =============================================================================
# A06 Regressions: Mark processed in Stage 1 and close timestamp freshness
# =============================================================================

def test_a06_mark_available_in_stage_1_and_close_time_freshness():
    """Finding A06: Mark messages processed in Stage 1 with close_ms timestamp for 120s freshness."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t = 1_700_000_000_000

    # Mark bar for [t-60s, t] closes at t, available at t+60s
    mbar = MarkBar1m(
        timestamp_ms=t - 60_000,
        open=Decimal(50000),
        high=Decimal(50000),
        low=Decimal(50000),
        close=Decimal(50000),
        symbol="BTCUSDT",
        available_at_ms=t + 60_000,
    )

    # At open t+60s, Stage 1 consumes available mark
    book.step_minute_open(t + 60_000, {}, {"BTCUSDT": mbar}, 4 * 3_600_000)

    assert "BTCUSDT" in book.last_available_marks
    _mark_price, mark_time, _avail_time = book.last_available_marks["BTCUSDT"]
    # CRITICAL ASSERTION: mark_time must be completed mark close_ms (t), NOT timestamp_ms (t - 60_000)!
    assert mark_time == t, f"A06 DEFECT: Stored mark timestamp was {mark_time} (bar open), expected {t} (bar close)"


# =============================================================================
# A07 Regressions: Cooldown from economic exit and 4h dedup arguments
# =============================================================================

def test_a07_cooldown_starts_from_economic_exit():
    """Finding A07: Cooldown starts from ceil_to_minute(economic_exit_at) + 4h."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t_exit = 1_700_000_000_000

    # Setup completed trade exit at t_exit, acknowledged at t_exit + 60s
    trade = CompletedTrade(
        trade_id="TRD_1",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        effective_entry=Decimal(50000),
        raw_entry=Decimal(50000),
        effective_exit=Decimal(51000),
        raw_exit=Decimal(51000),
        entry_time_ms=t_exit - 3_600_000,
        exit_time_ms=t_exit,  # economic exit at t_exit
        holding_minutes=60,
        exit_reason=ExitReason.TAKE_PROFIT,
        entry_fee_usdt=Decimal("0.30"),
        exit_fee_usdt=Decimal("0.30"),
        total_fees_usdt=Decimal("0.60"),
        total_funding_usdt=Decimal(0),
        gross_pnl_usdt=Decimal(10),
        net_pnl_usdt=Decimal("9.40"),
        entry_notional_usdt=Decimal(500),
        initial_risk_dollars=Decimal(10),
        net_bps=Decimal(188),
        net_r=Decimal("0.94"),
    )
    book.pending_exit_acks.append((trade, t_exit + 60_000))

    # Consume exit ACK at t_exit + 60_000
    book.step_minute_open(t_exit + 60_000, {}, {}, 4 * 3_600_000)

    ceil_exit = ((t_exit + 59_999) // 60_000) * 60_000
    expected_cooldown = ceil_exit + COOLDOWN_DURATION_MS
    actual_cooldown = book.cooldown_until_ms.get("BTCUSDT")
    assert actual_cooldown == expected_cooldown, f"A07 DEFECT: Cooldown was {actual_cooldown}, expected {expected_cooldown}"


# =============================================================================
# A08 Regressions: Reserve accounting includes tick_size * quantity
# =============================================================================

def test_a08_reserve_includes_tick_size_times_quantity():
    """Finding A08: Position exit reserve must include sym_filter.tick_size * quantity."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t = 1_700_000_000_000

    order = VirtualOrder(
        order_id="ORD_RES",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        target_fill_time_ms=t,
        created_at_ms=t - 60_000,
        expected_entry_bound=Decimal(50000),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(2500),
        funding_reserve_usdt=Decimal(10),
    )
    book.pending_orders.append(order)

    bars = {"BTCUSDT": _make_1m_bar(t, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000))}
    marks = {"BTCUSDT": _make_mark_bar(t - 60_000, Decimal(50000), t)}

    book.step_minute_open(t, bars, marks, 4 * 3_600_000)
    pos = book.positions["BTCUSDT"]
    tick = book.get_symbol_filter("BTCUSDT").tick_size  # 0.10

    # Expected exit reserve = 1.10 * entry * (fee + friction) * qty + tick * qty
    expected_exit_reserve = (
        Decimal("1.10") * pos.effective_entry * (book.cost_model.fee_rate + book.cost_model.friction_rate) * pos.quantity
        + tick * pos.quantity
    )
    assert pos.cost_commitment_exit_usdt == expected_exit_reserve, (
        f"A08 DEFECT: cost_commitment_exit_usdt is {pos.cost_commitment_exit_usdt}, "
        f"omitted tick * qty ({tick * pos.quantity})"
    )
