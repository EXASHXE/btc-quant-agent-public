"""Positive invariant test suite for Gemini A R2 centralized engineering repairs (B01-B07).

Validates correct after-state behaviors:
- B01: Causal mark stream ingestion by effective availability; rejection of future, stale, and out-of-order marks.
- B02: Idempotent ACK delivery for entry fills, exit acks, and funding settlements (no double fees/cash debits/zombies).
- B03: Settlement interval ownership [S-15s, S+15s] for preceding, succeeding, and same-minute SL positions.
- B04: Intraminute exit timestamp at minute-end (open+60s-1), holding_minutes >= 1, consistent cooldown anchoring.
- B05: Available vs economic equity valuation; drawdown kill cancels orders while retaining live position commitments.
- B06: Retest progression advancing bars_since_breakout and extrema across intermediate invalid hours without state skip.
- B07: Exact aggregate funding reserve conservation (zero residual leak after position close).
- E2E: Real synthetic ReplayEngine simulation with causal marks, signal triggering, fill, 4h holding, and reconciliation.
"""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.candidate_registry import (
    get_default_registry,
)
from btc_quant_agent.strategy_research.r3_overnight.constants import (
    COOLDOWN_DURATION_MS,
)
from btc_quant_agent.strategy_research.r3_overnight.ledger import (
    VirtualBook,
)
from btc_quant_agent.strategy_research.r3_overnight.replay_engine import (
    ReplayEngine,
)
from btc_quant_agent.strategy_research.r3_overnight.signals import (
    SignalGenerator,
)
from btc_quant_agent.strategy_research.r3_overnight.synthetic_fixtures import (
    make_1m_bar,
    make_mark_bar,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1h,
    Bar1m,
    Bar4h,
    CompletedTrade,
    CostScenario,
    Direction,
    ExitReason,
    FundingEventRecord,
    MarkBar1m,
    Position,
    VirtualFill,
    VirtualOrder,
)


def _make_1h(t: int, o: Decimal, h: Decimal, l: Decimal, c: Decimal, vol: Decimal = Decimal(100), sym: str = "BTCUSDT") -> Bar1h:
    return Bar1h(timestamp_ms=t, open=o, high=h, low=l, close=c, volume=vol, symbol=sym, bar_count=60)


def _make_4h(t: int, o: Decimal, h: Decimal, l: Decimal, c: Decimal, vol: Decimal = Decimal(1000), sym: str = "BTCUSDT") -> Bar4h:
    return Bar4h(timestamp_ms=t, open=o, high=h, low=l, close=c, volume=vol, symbol=sym, bar_count=240)


# =============================================================================
# B01 Positive Invariants: Causal Mark Price Stream
# =============================================================================

def test_b01_causal_mark_ingestion_and_future_stale_rejection():
    """B01 positive invariant: marks are admitted strictly when close_ms <= open_time_ms and available_at_ms <= open_time_ms.

    Old R1 defect: Marks ingested had timestamp at open O with available_at <= O, leaving last_available_marks empty.
    R2 behavior: Mark is admitted once closed and available; future marks rejected; stale marks (>120s) trigger liquidation.
    """
    book = VirtualBook(candidate_id="CLOSED_RETEST_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000 // 60_000 * 60_000

    # 1. Future mark: close_ms > open_time_ms -> must be rejected
    future_mark = MarkBar1m(
        timestamp_ms=t0,
        open=Decimal("50000.00"),
        high=Decimal("50000.00"),
        low=Decimal("50000.00"),
        close=Decimal("50000.00"),
        symbol="BTCUSDT",
        available_at_ms=t0,  # close_ms = t0 + 60_000 > t0
    )
    book.step_minute_open(t0, {}, {"BTCUSDT": future_mark}, 4 * 3_600_000)
    assert "BTCUSDT" not in book.last_available_marks, "Future mark must not be ingested"

    # 2. Causally valid mark: closed at t0, available at t0 -> admitted in Stage 1 at t0
    valid_mark = MarkBar1m(
        timestamp_ms=t0 - 60_000,
        open=Decimal("50000.00"),
        high=Decimal("50010.00"),
        low=Decimal("49990.00"),
        close=Decimal("50005.00"),
        symbol="BTCUSDT",
        available_at_ms=t0,
    )
    book.step_minute_open(t0, {}, {"BTCUSDT": valid_mark}, 4 * 3_600_000)
    assert "BTCUSDT" in book.last_available_marks
    price, close_ms, avail_ms = book.last_available_marks["BTCUSDT"]
    assert price == Decimal("50005.00")
    assert close_ms == t0
    assert avail_ms == t0

    # 3. Out-of-order stale mark delivery arriving later: older close_ms must not overwrite newer mark
    stale_ooo_mark = MarkBar1m(
        timestamp_ms=t0 - 120_000,
        open=Decimal("49900.00"),
        high=Decimal("49900.00"),
        low=Decimal("49900.00"),
        close=Decimal("49900.00"),
        symbol="BTCUSDT",
        available_at_ms=t0 + 60_000,
    )
    book.step_minute_open(t0 + 60_000, {}, {"BTCUSDT": stale_ooo_mark}, 4 * 3_600_000)
    price_after, close_after, _ = book.last_available_marks["BTCUSDT"]
    assert price_after == Decimal("50005.00"), "Out of order older mark must not overwrite newer mark"
    assert close_after == t0


def test_b01_mark_freshness_staleness_exit():
    """B01 positive invariant: If mark is older than 120s, active position triggers MARK_STALENESS exit."""
    book = VirtualBook(candidate_id="CLOSED_RETEST_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000 // 60_000 * 60_000
    pos = Position(
        position_id="POS_STALE_TEST",
        candidate_id="CLOSED_RETEST_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal("50000.00"),
        entry_time_ms=t0,
        entry_available_at_ms=t0 + 60_000,
        stop=Decimal("49000.00"),
        target=Decimal("52000.00"),
        max_hold_ms=4 * 3_600_000,
        cost_commitment_exit_usdt=Decimal("5.00"),
        is_acknowledged=True,
    )
    book.positions["BTCUSDT"] = pos
    # Last mark was at t0
    book.last_available_marks["BTCUSDT"] = (Decimal("50000.00"), t0, t0)

    # Step at t0 + 180s (>120s staleness):
    t_stale = t0 + 180_000
    bar_stale = make_1m_bar(t_stale, Decimal("50000.00"), Decimal("50010.00"), Decimal("49990.00"), Decimal("50000.00"))
    book.step_minute_open(t_stale, {"BTCUSDT": bar_stale}, {}, 4 * 3_600_000)

    assert any(e[0] == "BTCUSDT" and e[1] == ExitReason.MARK_STALENESS for e in book.due_exits), (
        "Mark older than 120s must trigger MARK_STALENESS due exit"
    )


# =============================================================================
# B02 Positive Invariants: ACK Idempotency
# =============================================================================

def test_b02_ack_idempotency_entry_exit_and_funding():
    """B02 positive invariant: Repeated delivery of ACKs produces exactly one economic effect.

    Old R1 defect: Duplicate entry ACK deducted cash twice, charged duplicate fees, or created phantom entries.
    R2 behavior: Track acknowledged event IDs; redundant delivery has exactly zero secondary impact.
    """
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    initial_cash = book.cash
    t0 = 1_700_000_000_000 // 60_000 * 60_000

    # 1. Fill ACK idempotency
    fill = VirtualFill(
        fill_id="FILL_IDEM_1",
        order_id="ORD_IDEM_1",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        raw_price=Decimal("50000.00"),
        effective_price=Decimal("50000.00"),
        fee_usdt=Decimal("0.75"),
        fill_time_ms=t0,
        available_at_ms=t0 + 60_000,
        initial_stop=Decimal("49000.00"),
        target=Decimal("52000.00"),
    )
    # Deliver fill ACK
    book.pending_fill_acks.append(fill)
    book.step_minute_open(t0 + 60_000, {}, {}, 4 * 3_600_000)
    cash_after_first = book.cash
    assert cash_after_first == initial_cash - Decimal("0.75")

    # Deliver exact same fill ACK a 2nd and 3rd time
    book.pending_fill_acks.append(fill)
    book.pending_fill_acks.append(fill)
    book.step_minute_open(t0 + 120_000, {}, {}, 4 * 3_600_000)
    book.step_minute_open(t0 + 180_000, {}, {}, 4 * 3_600_000)

    assert book.cash == cash_after_first, "Duplicate fill ACK must not deduct cash or charge fees again"

    # 2. Exit ACK idempotency
    trade = CompletedTrade(
        trade_id="TRD_IDEM_1",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal("50000.00"),
        raw_entry=Decimal("50000.00"),
        effective_exit=Decimal("51000.00"),
        raw_exit=Decimal("51000.00"),
        entry_time_ms=t0,
        exit_time_ms=t0 + 3_600_000,
        holding_minutes=60,
        exit_reason=ExitReason.TAKE_PROFIT,
        entry_fee_usdt=Decimal("0.75"),
        exit_fee_usdt=Decimal("0.75"),
        total_fees_usdt=Decimal("1.50"),
        total_funding_usdt=Decimal("0.00"),
        gross_pnl_usdt=Decimal("50.00"),
        net_pnl_usdt=Decimal("48.50"),
        entry_notional_usdt=Decimal("2500.00"),
        initial_risk_dollars=Decimal("50.00"),
        net_bps=Decimal("194.00"),
        net_r=Decimal("0.97"),
        retest_event_id=None,
    )
    book.cost_commitment_o = Decimal("5.00")
    book.funding_reserve_rf = Decimal("1.00")

    # Deliver exit ACK
    book.pending_exit_acks.append((trade, t0 + 3_660_000, Decimal("5.00"), Decimal("1.00")))
    book.step_minute_open(t0 + 3_660_000, {}, {}, 4 * 3_600_000)
    cash_after_exit = book.cash
    assert len(book.completed_trades) == 1
    assert book.cost_commitment_o == Decimal(0)
    assert book.funding_reserve_rf == Decimal(0)

    # Deliver duplicate exit ACK
    book.pending_exit_acks.append((trade, t0 + 3_720_000, Decimal("5.00"), Decimal("1.00")))
    book.step_minute_open(t0 + 3_720_000, {}, {}, 4 * 3_600_000)
    assert book.cash == cash_after_exit, "Duplicate exit ACK must not credit cash or pnl again"
    assert len(book.completed_trades) == 1, "Duplicate exit ACK must not create duplicate completed trade"

    # 3. Funding ACK idempotency
    charge = FundingEventRecord(
        event_id="FUND_IDEM_1",
        symbol="BTCUSDT",
        settlement_time_ms=t0 + 7_200_000,
        rate=Decimal("0.0004"),
        settlement_mark=Decimal("50000.00"),
        position_quantity=Decimal("0.05"),
        cashflow_debit_usdt=Decimal("1.00"),
        charged_at_ms=t0 + 7_200_000,
        available_at_ms=t0 + 7_260_000,
    )
    book.pending_funding_acks.append(charge)
    book.step_minute_open(t0 + 7_260_000, {}, {}, 4 * 3_600_000)
    cash_after_funding = book.cash
    assert cash_after_funding == cash_after_exit - Decimal("1.00")
    assert len(book.funding_charges) == 1

    # Deliver duplicate funding ACK
    book.pending_funding_acks.append(charge)
    book.step_minute_open(t0 + 7_320_000, {}, {}, 4 * 3_600_000)
    assert book.cash == cash_after_funding, "Duplicate funding ACK must not debit cash again"
    assert len(book.funding_charges) == 1


# =============================================================================
# B03 Positive Invariants: Hourly Settlement Ownership [S-15s, S+15s]
# =============================================================================

def test_b03_hourly_settlement_ownership_window():
    """B03 positive invariant: Positions held across [S-15s, S+15s] are charged; positions closed prior are not.

    Old R1 defect: Strict inequality missed boundary; same-minute SL at S was dropped without paying funding.
    R2 behavior: Explicit ExposureInterval tracks economic lifetime including intraminute exits at S.
    """
    s_boundary = 1_700_000_000_000 // 3_600_000 * 3_600_000  # Exact hour boundary S

    # Case A: Position opened at S - 60s, hits SL at minute S (economic exit S + 60s - 1)
    # Exposure interval [S - 60s, S + 60s - 1] overlaps [S - 15s, S + 15s] -> MUST pay funding!
    book_a = VirtualBook(candidate_id="CLOSED_RETEST_LONG_04H", cost_scenario=CostScenario.BASE)
    order_a = VirtualOrder(
        order_id="ORD_SL_AT_S",
        candidate_id="CLOSED_RETEST_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        target_fill_time_ms=s_boundary - 60_000,
        created_at_ms=s_boundary - 120_000,
        expected_entry_bound=Decimal("50000.00"),
        initial_stop=Decimal("49500.00"),
        target=Decimal("52000.00"),
        cost_commitment_usdt=Decimal("2500.00"),
        funding_reserve_usdt=Decimal("5.00"),
    )
    book_a.pending_orders.append(order_a)
    bar_pre = make_1m_bar(s_boundary - 60_000, Decimal("50000.00"), Decimal("50010.00"), Decimal("49990.00"), Decimal("50000.00"))
    mark_pre = make_mark_bar(s_boundary - 60_000, Decimal("50000.00"))
    book_a.step_minute_open(s_boundary - 60_000, {"BTCUSDT": bar_pre}, {"BTCUSDT": mark_pre}, 4 * 3_600_000)

    # Minute S: bar drops below stop 49500 -> Stage 6 triggers STOP_LOSS exit
    bar_s = make_1m_bar(s_boundary, Decimal("50000.00"), Decimal("50010.00"), Decimal("49000.00"), Decimal("49100.00"))
    mark_s = make_mark_bar(s_boundary, Decimal("49100.00"))
    book_a.step_minute_open(s_boundary, {"BTCUSDT": bar_s}, {"BTCUSDT": mark_s}, 4 * 3_600_000)

    # Funding settlement at S must be charged!
    charge_count_a = len(book_a.pending_funding_acks)
    assert charge_count_a == 1, "Position exiting via SL at minute S must be charged funding for hour S"

    # Case B: Position closed at S - 120s (economic exit S - 60_001 ms).
    # Since S - 60_001 < S - 15_000, interval does not overlap [S - 15s, S + 15s]!
    book_b = VirtualBook(candidate_id="CLOSED_RETEST_LONG_04H", cost_scenario=CostScenario.BASE)
    order_b = VirtualOrder(
        order_id="ORD_CLOSED_EARLY",
        candidate_id="CLOSED_RETEST_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        target_fill_time_ms=s_boundary - 180_000,
        created_at_ms=s_boundary - 240_000,
        expected_entry_bound=Decimal("50000.00"),
        initial_stop=Decimal("49500.00"),
        target=Decimal("52000.00"),
        cost_commitment_usdt=Decimal("2500.00"),
        funding_reserve_usdt=Decimal("5.00"),
    )
    book_b.pending_orders.append(order_b)
    bar_b1 = make_1m_bar(s_boundary - 180_000, Decimal("50000.00"), Decimal("50010.00"), Decimal("49990.00"), Decimal("50000.00"))
    mark_b1 = make_mark_bar(s_boundary - 180_000, Decimal("50000.00"))
    book_b.step_minute_open(s_boundary - 180_000, {"BTCUSDT": bar_b1}, {"BTCUSDT": mark_b1}, 4 * 3_600_000)

    # Hits TP at S - 120s (economic exit S - 60_001 ms)
    bar_b2 = make_1m_bar(s_boundary - 120_000, Decimal("50000.00"), Decimal("52100.00"), Decimal("49990.00"), Decimal("52050.00"))
    mark_b2 = make_mark_bar(s_boundary - 120_000, Decimal("52050.00"))
    book_b.step_minute_open(s_boundary - 120_000, {"BTCUSDT": bar_b2}, {"BTCUSDT": mark_b2}, 4 * 3_600_000)

    # Minute S - 60s
    bar_b3 = make_1m_bar(s_boundary - 60_000, Decimal("52050.00"), Decimal("52100.00"), Decimal("52000.00"), Decimal("52050.00"))
    mark_b3 = make_mark_bar(s_boundary - 60_000, Decimal("52050.00"))
    book_b.step_minute_open(s_boundary - 60_000, {"BTCUSDT": bar_b3}, {"BTCUSDT": mark_b3}, 4 * 3_600_000)

    # Step at S: position was already closed at S - 120s
    bar_b4 = make_1m_bar(s_boundary, Decimal("52050.00"), Decimal("52100.00"), Decimal("52000.00"), Decimal("52050.00"))
    mark_b4 = make_mark_bar(s_boundary, Decimal("52050.00"))
    book_b.step_minute_open(s_boundary, {"BTCUSDT": bar_b4}, {"BTCUSDT": mark_b4}, 4 * 3_600_000)

    assert len(book_b.pending_funding_acks) == 0, "Position closed before S-15s must NOT be charged funding at S"


# =============================================================================
# B04 Positive Invariants: Deterministic Exit Timestamps and Cooldown
# =============================================================================

def test_b04_intraminute_exit_timestamp_and_cooldown_anchoring():
    """B04 positive invariant: Intraminute SL/TP exits stamped at open_time_ms + 60_000 - 1, holding_minutes >= 1.

    Old R1 defect: Intraminute exit was stamped at bar open O (leaking future outcome into opening); holding_minutes was 0.
    R2 behavior: exit_time_ms = open_time_ms + 59_999, holding_minutes >= 1, cooldown anchored to ceil_to_minute + 4h.
    """
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000 // 60_000 * 60_000
    pos = Position(
        position_id="POS_B04_TEST",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal("50000.00"),
        entry_time_ms=t0,
        entry_available_at_ms=t0 + 60_000,
        stop=Decimal("49500.00"),
        target=Decimal("51000.00"),
        max_hold_ms=4 * 3_600_000,
        cost_commitment_exit_usdt=Decimal("5.00"),
        is_acknowledged=True,
    )
    book.positions["BTCUSDT"] = pos

    # Step at t0: hits stop loss intraminute in Stage 6
    bar = make_1m_bar(t0, Decimal("50000.00"), Decimal("50010.00"), Decimal("49000.00"), Decimal("49100.00"))
    mark = make_mark_bar(t0, Decimal("49100.00"))
    book.step_minute_open(t0, {"BTCUSDT": bar}, {"BTCUSDT": mark}, 4 * 3_600_000)

    # Consume exit ACK in next minute
    book.step_minute_open(t0 + 60_000, {}, {}, 4 * 3_600_000)

    assert len(book.completed_trades) == 1
    trade = book.completed_trades[0]
    expected_exit_time = t0 + 60_000 - 1
    assert trade.exit_time_ms == expected_exit_time, f"Exit time must be minute end: {trade.exit_time_ms} != {expected_exit_time}"
    assert trade.holding_minutes >= 1, f"Holding minutes must be >= 1 for completed bar: {trade.holding_minutes}"

    # Cooldown anchoring: ceil_to_minute(expected_exit_time) + 4h = t0 + 60_000 + 4 * 3_600_000
    expected_cooldown = t0 + 60_000 + COOLDOWN_DURATION_MS
    actual_cooldown = book.cooldown_until_ms.get("BTCUSDT")
    assert actual_cooldown == expected_cooldown, f"Cooldown {actual_cooldown} != expected {expected_cooldown}"


# =============================================================================
# B05 Positive Invariants: Decision Equity and Kill Reservation Integrity
# =============================================================================

def test_b05_unacked_position_excluded_from_decision_equity():
    """B05A positive invariant: Decision equity values only acknowledged positions."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    initial_cash = book.cash
    t0 = 1_700_000_000_000 // 60_000 * 60_000

    pos = Position(
        position_id="POS_UNACKED",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.10"),
        effective_entry=Decimal("50000.00"),
        entry_time_ms=t0,
        entry_available_at_ms=t0 + 60_000,
        stop=Decimal("49000.00"),
        target=Decimal("52000.00"),
        max_hold_ms=4 * 3_600_000,
        cost_commitment_exit_usdt=Decimal("5.00"),
        is_acknowledged=False,  # Unacknowledged!
    )
    book.positions["BTCUSDT"] = pos
    book.last_available_marks["BTCUSDT"] = (Decimal("55000.00"), t0, t0)  # +$500 unrealized gain

    # Step minute open at t0 (before ACK available at t0 + 60s)
    book.step_minute_open(t0, {}, {}, 4 * 3_600_000)

    # Decision equity must NOT count unacknowledged position's unrealized pnl
    assert book.decision_equity == initial_cash, f"Decision equity {book.decision_equity} must equal cash {initial_cash}"


def test_b05_drawdown_kill_preserves_obligations_and_prevents_negative_reserves():
    """B05B positive invariant: Drawdown kill cancels pending orders but retains open position commitments."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000 // 60_000 * 60_000

    # Add an active open position
    pos = Position(
        position_id="POS_ACTIVE",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal("50000.00"),
        entry_time_ms=t0,
        entry_available_at_ms=t0,
        stop=Decimal("49000.00"),
        target=Decimal("52000.00"),
        max_hold_ms=4 * 3_600_000,
        cost_commitment_exit_usdt=Decimal("5.00"),
        funding_reserves_usdt=Decimal("1.00"),
        is_acknowledged=True,
    )
    book.positions["BTCUSDT"] = pos
    book.cost_commitment_o = Decimal("5.00")
    book.funding_reserve_rf = Decimal("1.00")

    # Add a pending order
    order = VirtualOrder(
        order_id="ORD_PENDING",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="ETHUSDT",
        direction=Direction.LONG,
        quantity=Decimal("1.0"),
        target_fill_time_ms=t0 + 60_000,
        created_at_ms=t0,
        expected_entry_bound=Decimal("3000.00"),
        initial_stop=Decimal("2900.00"),
        target=Decimal("3200.00"),
        cost_commitment_usdt=Decimal("10.00"),
        funding_reserve_usdt=Decimal("2.00"),
    )
    book.pending_orders.append(order)
    book.cost_commitment_o += Decimal("10.00")
    book.funding_reserve_rf += Decimal("2.00")

    # Mark price crash triggering DRAWDOWN_KILL
    book.last_available_marks["BTCUSDT"] = (Decimal("40000.00"), t0, t0)  # -$500 unrealized loss > $50 threshold

    bar = make_1m_bar(t0, Decimal("50000.00"), Decimal("50010.00"), Decimal("49990.00"), Decimal("50000.00"))
    book.step_minute_open(t0, {"BTCUSDT": bar}, {}, 4 * 3_600_000)

    assert book.killed is True, "Book must be killed on drawdown threshold breach"
    assert len(book.pending_orders) == 0, "Pending orders must be canceled on kill"
    # Commitments must reflect active position's obligations, NOT negative or zeroed out
    assert book.cost_commitment_o == Decimal("5.00"), f"Cost commitment should be 5.00, got {book.cost_commitment_o}"
    assert book.funding_reserve_rf == Decimal("1.00"), f"Funding reserve should be 1.00, got {book.funding_reserve_rf}"

    # Step t0 + 60s: due kill liquidation executes in Stage 4
    bar_liq = make_1m_bar(t0 + 60_000, Decimal("40000.00"), Decimal("40010.00"), Decimal("39990.00"), Decimal("40000.00"))
    book.step_minute_open(t0 + 60_000, {"BTCUSDT": bar_liq}, {}, 4 * 3_600_000)

    # Step t0 + 120s: liquidation exit ACK arrives in Stage 1
    book.step_minute_open(t0 + 120_000, {}, {}, 4 * 3_600_000)

    assert book.cost_commitment_o == Decimal(0), "Commitment must cleanly reach 0 upon exit ACK"
    assert book.funding_reserve_rf == Decimal(0), "Funding reserve must cleanly reach 0 upon exit ACK"


# =============================================================================
# B06 Positive Invariants: Retest State Progression Across Invalid Intermediate Hours
# =============================================================================

def test_b06_retest_progression_across_invalid_intermediate_hour():
    """B06 positive invariant: bars_since_breakout and extrema advance for every completed post-breakout hour.

    Old R1 defect: Filter failure at intermediate hour returned None before advancing breakout state, causing time skip.
    R2 behavior: _advance_active_breakout advances bars_since_breakout and extrema before filter checks.
    """
    gen = SignalGenerator()
    c = get_default_registry().get_candidate("CLOSED_RETEST_LONG_04H")
    base_t = 1_700_000_000_000 // 14_400_000 * 14_400_000

    bars_1h: list[Bar1h] = []
    for i in range(25):
        p = Decimal(50000 + i * 10)
        bars_1h.append(_make_1h(base_t + i * 3_600_000, p, p + Decimal(100), p - Decimal(100), p))

    # Hour 25: Breakout bar
    boundary = max(b.high for b in bars_1h[-24:])
    bars_1h.append(_make_1h(base_t + 25 * 3_600_000, Decimal(50300), Decimal(50700), Decimal(50280), Decimal(50650)))

    # 65 4h bars for EMA stabilization
    bars_4h: list[Bar4h] = []
    for i in range(65):
        t_4h = base_t + i * 14_400_000
        p = Decimal(45000 + i * 100)
        bars_4h.append(_make_4h(t_4h, p, p + Decimal(50), p - Decimal(50), p))

    # Evaluate breakout hour
    sig0 = gen.evaluate_hourly_decision(c, "BTCUSDT", bars_1h, bars_4h)
    assert sig0 is None, "Breakout bar itself does not confirm retest"
    state = gen._active_breakouts.get((c.id, "BTCUSDT", Direction.LONG))
    assert state is not None, "Breakout must be registered"
    assert state.bars_since_breakout == 0

    # Hour 26: Intermediate invalid hour with deep wick below touch zone -> fails filter
    # But it MUST advance bars_since_breakout from 0 to 1 and record extrema!
    bars_1h.append(_make_1h(base_t + 26 * 3_600_000, Decimal(50600), Decimal(50650), Decimal(50200), Decimal(50620)))
    sig_h26 = gen.evaluate_hourly_decision(c, "BTCUSDT", bars_1h, bars_4h)
    assert sig_h26 is None, "Intermediate hour fails filter, must return None"

    state_after_h26 = gen._active_breakouts.get((c.id, "BTCUSDT", Direction.LONG))
    assert state_after_h26.bars_since_breakout == 1, (
        f"bars_since_breakout must advance to 1, got {state_after_h26.bars_since_breakout}"
    )
    assert Decimal(50200) in state_after_h26.intermediate_lows, "Intermediate low must be recorded"

    # Hour 27: Valid retest touch and confirmation!
    bars_1h.append(_make_1h(base_t + 27 * 3_600_000, Decimal(50400), Decimal(50600), boundary, Decimal(50550)))
    sig_h27 = gen.evaluate_hourly_decision(c, "BTCUSDT", bars_1h, bars_4h)
    assert sig_h27 is not None, "Retest must confirm on hour 2 after intermediate invalid hour"
    assert sig_h27.candidate_id == c.id


# =============================================================================
# B07 Positive Invariants: Funding Reserve Conservation
# =============================================================================

def test_b07_exact_funding_reserve_conservation():
    """B07 positive invariant: Aggregate funding_reserve_rf and position funding_reserves_usdt are debited in Stage 7 with zero leak.

    Old R1 defect: funding_reserve_rf was not debited upon Stage 7 funding charge, leaking residual reserve after position close.
    R2 behavior: Exact source/destination debit conservation; zero leaked reserve on close.
    """
    book = VirtualBook(candidate_id="CLOSED_RETEST_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000 // 3_600_000 * 3_600_000
    pos = Position(
        position_id="POS_FUNDING_CONSERVATION",
        candidate_id="CLOSED_RETEST_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal("50000.00"),
        entry_time_ms=t0 - 180_000,
        entry_available_at_ms=t0 - 120_000,
        stop=Decimal("49000.00"),
        target=Decimal("52000.00"),
        max_hold_ms=4 * 3_600_000,
        cost_commitment_exit_usdt=Decimal("5.00"),
        funding_reserves_usdt=Decimal("2.00"),
        is_acknowledged=True,
    )
    book.positions["BTCUSDT"] = pos
    book.cost_commitment_o = Decimal("5.00")
    book.funding_reserve_rf = Decimal("2.00")

    # Step at hour boundary t0: Stage 7 funding evaluation
    bar = make_1m_bar(t0, Decimal("50000.00"), Decimal("50010.00"), Decimal("49990.00"), Decimal("50000.00"))
    mark = make_mark_bar(t0, Decimal("50000.00"))
    book.step_minute_open(t0, {"BTCUSDT": bar}, {"BTCUSDT": mark}, 4 * 3_600_000)

    # Funding charged: 0.05 * 50,000 * 0.0004 = 1.00 USDT
    expected_charge = Decimal("1.00000000")
    assert pos.funding_reserves_usdt == Decimal("2.00") - expected_charge
    assert book.funding_reserve_rf == Decimal("2.00") - expected_charge

    # Step t0 + 60s: funding ACK arrives in Stage 1 and is consumed
    bar_2 = make_1m_bar(t0 + 60_000, Decimal("50000.00"), Decimal("50010.00"), Decimal("49990.00"), Decimal("50000.00"))
    mark_2 = make_mark_bar(t0 + 60_000, Decimal("50000.00"))
    book.step_minute_open(t0 + 60_000, {"BTCUSDT": bar_2}, {"BTCUSDT": mark_2}, 4 * 3_600_000)

    # Now close position at t0 + 120s
    bar_exit = make_1m_bar(t0 + 120_000, Decimal("50000.00"), Decimal("52100.00"), Decimal("49990.00"), Decimal("52050.00"))
    mark_exit = make_mark_bar(t0 + 120_000, Decimal("52050.00"))
    book.step_minute_open(t0 + 120_000, {"BTCUSDT": bar_exit}, {"BTCUSDT": mark_exit}, 4 * 3_600_000)

    # Acknowledge exit at t0 + 180s
    book.step_minute_open(t0 + 180_000, {}, {}, 4 * 3_600_000)

    # CRITICAL INVARIANT: Zero leaked funding reserve after position close!
    assert book.funding_reserve_rf == Decimal(0), (
        f"Leaked funding reserve must be exactly 0, got {book.funding_reserve_rf}"
    )
    assert book.cost_commitment_o == Decimal(0), (
        f"Leaked cost commitment must be exactly 0, got {book.cost_commitment_o}"
    )


# =============================================================================
# E2E Integration: Real Synthetic ReplayEngine Simulation
# =============================================================================

def test_replay_engine_e2e_synthetic_take_profit():
    """End-to-end ReplayEngine run with causal marks, signal generation, fill, holding, and TP exit."""
    start_ms = 1_700_000_000_000 // 14_400_000 * 14_400_000
    bars_1m: list[Bar1m] = []
    marks_1m: list[MarkBar1m] = []

    # 240 warmup hours (60 4h bars)
    for h in range(240):
        t_h = start_ms + h * 3_600_000
        p = Decimal("40000.00") + Decimal(str(h * 40))
        for m in range(60):
            t = t_h + m * 60_000
            bars_1m.append(make_1m_bar(t, p, p + Decimal("100.00"), p - Decimal("100.00"), p, Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, p, "BTCUSDT"))

    # Breakout hour 240
    t_240 = start_ms + 240 * 3_600_000
    for m in range(60):
        t = t_240 + m * 60_000
        o = Decimal("49600.00") + Decimal(str(m * 10))
        c = o + Decimal("8.00")
        h_p = c + Decimal("5.00")
        l_p = o - Decimal("5.00")
        bars_1m.append(make_1m_bar(t, o, h_p, l_p, c, Decimal("100.0"), "BTCUSDT"))
        marks_1m.append(make_mark_bar(t + 60_000, c, "BTCUSDT"))

    # Retest confirmation hour 241
    t_241 = start_ms + 241 * 3_600_000
    for m in range(60):
        t = t_241 + m * 60_000
        if m == 5:
            bars_1m.append(make_1m_bar(t, Decimal("49750.00"), Decimal("49760.00"), Decimal("49660.00"), Decimal("49700.00"), Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, Decimal("49700.00"), "BTCUSDT"))
        elif m == 59:
            bars_1m.append(make_1m_bar(t, Decimal("49900.00"), Decimal("50010.00"), Decimal("49890.00"), Decimal("50000.00"), Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, Decimal("50000.00"), "BTCUSDT"))
        else:
            bars_1m.append(make_1m_bar(t, Decimal("49800.00"), Decimal("49820.00"), Decimal("49780.00"), Decimal("49800.00"), Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, Decimal("49800.00"), "BTCUSDT"))

    # Hour 242:
    # Minutes 0..4: open at 50,005 (fills order without gap veto)
    # Minutes 5..59: price surges to 52,000 hitting TP!
    t_242 = start_ms + 242 * 3_600_000
    for m in range(60):
        t = t_242 + m * 60_000
        p = Decimal("50005.00") if m < 5 else Decimal("52000.00")
        bars_1m.append(make_1m_bar(t, p, p + Decimal("20.00"), p - Decimal("20.00"), p, Decimal("100.0"), "BTCUSDT"))
        marks_1m.append(make_mark_bar(t + 60_000, p, "BTCUSDT"))

    # Holding hours 243..246
    for h in range(243, 247):
        t_h = start_ms + h * 3_600_000
        p = Decimal("52000.00")
        for m in range(60):
            t = t_h + m * 60_000
            bars_1m.append(make_1m_bar(t, p, p + Decimal("20.00"), p - Decimal("20.00"), p, Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, p, "BTCUSDT"))

    engine = ReplayEngine(cost_scenario=CostScenario.BASE)
    results = engine.run_simulation({"BTCUSDT": bars_1m}, {"BTCUSDT": marks_1m})

    assert len(results["CLOSED_RETEST_LONG_04H"]) == 1
    trade = results["CLOSED_RETEST_LONG_04H"][0]
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert trade.net_pnl_usdt > Decimal(0)

    book = engine.books["CLOSED_RETEST_LONG_04H"]
    assert book.cost_commitment_o == Decimal(0)
    assert book.funding_reserve_rf == Decimal(0)
    assert book.decision_equity == book.cash


def test_replay_engine_e2e_synthetic_expiry_4h():
    """End-to-end ReplayEngine run with 4h holding and EXPIRY exit."""
    start_ms = 1_700_000_000_000 // 14_400_000 * 14_400_000
    bars_1m: list[Bar1m] = []
    marks_1m: list[MarkBar1m] = []

    # 240 warmup hours
    for h in range(240):
        t_h = start_ms + h * 3_600_000
        p = Decimal("40000.00") + Decimal(str(h * 40))
        for m in range(60):
            t = t_h + m * 60_000
            bars_1m.append(make_1m_bar(t, p, p + Decimal("100.00"), p - Decimal("100.00"), p, Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, p, "BTCUSDT"))

    # Breakout hour 240
    t_240 = start_ms + 240 * 3_600_000
    for m in range(60):
        t = t_240 + m * 60_000
        o = Decimal("49600.00") + Decimal(str(m * 10))
        c = o + Decimal("8.00")
        h_p = c + Decimal("5.00")
        l_p = o - Decimal("5.00")
        bars_1m.append(make_1m_bar(t, o, h_p, l_p, c, Decimal("100.0"), "BTCUSDT"))
        marks_1m.append(make_mark_bar(t + 60_000, c, "BTCUSDT"))

    # Retest confirmation hour 241
    t_241 = start_ms + 241 * 3_600_000
    for m in range(60):
        t = t_241 + m * 60_000
        if m == 5:
            bars_1m.append(make_1m_bar(t, Decimal("49750.00"), Decimal("49760.00"), Decimal("49660.00"), Decimal("49700.00"), Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, Decimal("49700.00"), "BTCUSDT"))
        elif m == 59:
            bars_1m.append(make_1m_bar(t, Decimal("49900.00"), Decimal("50010.00"), Decimal("49890.00"), Decimal("50000.00"), Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, Decimal("50000.00"), "BTCUSDT"))
        else:
            bars_1m.append(make_1m_bar(t, Decimal("49800.00"), Decimal("49820.00"), Decimal("49780.00"), Decimal("49800.00"), Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, Decimal("49800.00"), "BTCUSDT"))

    # Flat price at 50,005 for hours 242..248 (exceeding 240m max hold)
    for h in range(242, 248):
        t_h = start_ms + h * 3_600_000
        p = Decimal("50005.00")
        for m in range(60):
            t = t_h + m * 60_000
            bars_1m.append(make_1m_bar(t, p, p + Decimal("10.00"), p - Decimal("10.00"), p, Decimal("100.0"), "BTCUSDT"))
            marks_1m.append(make_mark_bar(t + 60_000, p, "BTCUSDT"))

    engine = ReplayEngine(cost_scenario=CostScenario.BASE)
    results = engine.run_simulation({"BTCUSDT": bars_1m}, {"BTCUSDT": marks_1m})

    trades_04h = results["CLOSED_RETEST_LONG_04H"]
    assert len(trades_04h) == 1
    trade = trades_04h[0]
    assert trade.exit_reason == ExitReason.EXPIRY
    assert trade.holding_minutes == 240

    book = engine.books["CLOSED_RETEST_LONG_04H"]
    assert book.cost_commitment_o == Decimal(0)
    assert book.funding_reserve_rf == Decimal(0)
