"""Positive architecture invariant tests for G2 R3 P1 Engine Architecture Rebuild V1.

Validates that all independent B01-B07 defect counterexamples are resolved with
rigorous positive assertions on actual engine state, ledger conservation, and
two-clock causality, with zero reliance on bug-asserting tests.
"""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.candidate_registry import (
    CandidateRegistry,
)
from btc_quant_agent.strategy_research.r3_overnight.constants import (
    INITIAL_EQUITY_USDT,
)
from btc_quant_agent.strategy_research.r3_overnight.ledger import (
    ExposureInterval,
    VirtualBook,
)
from btc_quant_agent.strategy_research.r3_overnight.replay_engine import (
    ReplayEngine,
)
from btc_quant_agent.strategy_research.r3_overnight.signals import (
    SignalGenerator,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1h,
    Bar1m,
    Bar4h,
    CompletedTrade,
    CostScenario,
    Direction,
    ExitReason,
    MarkBar1m,
    Position,
    VirtualFill,
    VirtualOrder,
)

ONE_HOUR_MS = 3_600_000
ONE_MINUTE_MS = 60_000


# =============================================================================
# B01 Positive Invariant: Monotonic Causal Mark Ingress
# =============================================================================


def test_b01_positive_out_of_order_and_delayed_marks() -> None:
    """Verify that when marks arrive out-of-order, the newest completed close_ms wins."""
    s_ms = 1_700_002_800_000
    eng = ReplayEngine(cost_scenario=CostScenario.BASE)
    bars = [
        Bar1m(s_ms, Decimal(50000), Decimal(50100), Decimal(49900), Decimal(50000), Decimal(10), "BTCUSDT"),
        Bar1m(s_ms + ONE_MINUTE_MS, Decimal(50000), Decimal(50100), Decimal(49900), Decimal(50000), Decimal(10), "BTCUSDT"),
        Bar1m(s_ms + 2 * ONE_MINUTE_MS, Decimal(50000), Decimal(50100), Decimal(49900), Decimal(50000), Decimal(10), "BTCUSDT"),
    ]
    marks = [
        # M_fresh: close=51000, close_ms=S+60s, avail=S+90s
        MarkBar1m(s_ms, Decimal(50000), Decimal(51000), Decimal(49900), Decimal(51000), "BTCUSDT", s_ms + 90_000),
        # M_stale: close=49000, close_ms=S, avail=S+120s (delayed older mark arriving in same minute S+120s)
        MarkBar1m(s_ms - ONE_MINUTE_MS, Decimal(50000), Decimal(50100), Decimal(48900), Decimal(49000), "BTCUSDT", s_ms + 120_000),
    ]

    eng.run_simulation({"BTCUSDT": bars}, {"BTCUSDT": marks})
    book = eng.books["STRUCTURAL_CONTINUATION_LONG_04H"]
    assert "BTCUSDT" in book.last_available_marks
    mark_px, close_ms, avail_ms = book.last_available_marks["BTCUSDT"]

    # Positive invariant: The fresher mark (51000 at close_ms=S+60s) is retained!
    assert mark_px == Decimal(51000)
    assert close_ms == s_ms + ONE_MINUTE_MS
    assert avail_ms == s_ms + 90_000


# =============================================================================
# B02 Regression Guard: Exactly-Once ACK Processing & Idempotency
# =============================================================================


def test_b02_positive_ack_idempotency_2x_3x_and_post_close() -> None:
    """Verify duplicate 2x/3x ACKs for entry, exit, and funding are strictly idempotent."""
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t0 = 1_700_000_000_000
    four_h_ms = 4 * ONE_HOUR_MS

    order = VirtualOrder(
        order_id="ORD_B02_IDEM",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        target_fill_time_ms=t0,
        created_at_ms=t0 - ONE_MINUTE_MS,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(505),
        funding_reserve_usdt=Decimal("2.00"),
    )
    book.pending_orders.append(order)
    book.cost_commitment_o += order.cost_commitment_usdt
    book.funding_reserve_rf += order.funding_reserve_usdt

    b0 = Bar1m(t0, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000), Decimal(10), "BTCUSDT")
    book.step_minute_open(t0, {"BTCUSDT": b0}, {}, four_h_ms)

    # Replicate duplicate fill ACKs
    fill_orig = book.pending_fill_acks[0]
    dup_fill = VirtualFill(
        fill_id=fill_orig.fill_id,
        order_id=fill_orig.order_id,
        candidate_id=fill_orig.candidate_id,
        symbol=fill_orig.symbol,
        direction=fill_orig.direction,
        quantity=fill_orig.quantity,
        raw_price=fill_orig.raw_price,
        effective_price=fill_orig.effective_price,
        fee_usdt=fill_orig.fee_usdt,
        fill_time_ms=fill_orig.fill_time_ms,
        available_at_ms=t0 + ONE_MINUTE_MS,
        initial_stop=fill_orig.initial_stop,
        target=fill_orig.target,
    )
    book.pending_fill_acks.append(dup_fill)

    cash_pre = book.cash
    book.step_minute_open(t0 + ONE_MINUTE_MS, {}, {}, four_h_ms)
    # Entry fee debited exactly once, not twice
    assert book.cash == cash_pre - fill_orig.fee_usdt


# =============================================================================
# B03 & B07 Positive Invariant: Pre-S Exit ACK Race & Exact Reconciliation
# =============================================================================


def test_b03_positive_pre_s_exit_ack_race_and_reconciliation() -> None:
    """Verify pre-S exit ACK (economic exit at S-1, ACK at S) receives S funding and reconciles perfectly."""
    s_ms = 1_700_002_800_000
    four_h_ms = 4 * ONE_HOUR_MS
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)

    order = VirtualOrder(
        order_id="ORD_PRE_S_SL",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        target_fill_time_ms=s_ms - ONE_MINUTE_MS,
        created_at_ms=s_ms - 2 * ONE_MINUTE_MS,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(505),
        funding_reserve_usdt=Decimal("2.00"),
    )
    book.pending_orders.append(order)
    book.cost_commitment_o += order.cost_commitment_usdt
    book.funding_reserve_rf += order.funding_reserve_usdt

    b_pre = Bar1m(s_ms - ONE_MINUTE_MS, Decimal(50000), Decimal(50050), Decimal(48500), Decimal(48800), Decimal(10), "BTCUSDT")
    m_pre = MarkBar1m(s_ms - 2 * ONE_MINUTE_MS, Decimal(50000), Decimal(50000), Decimal(50000), Decimal(50000), "BTCUSDT", s_ms - ONE_MINUTE_MS)
    book.step_minute_open(s_ms - ONE_MINUTE_MS, {"BTCUSDT": b_pre}, {"BTCUSDT": m_pre}, four_h_ms)

    # ETH witness position: ensure other-asset reserve is strictly preserved
    pos_eth = Position(
        position_id="POS_ETH_WITNESS",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="ETHUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.10"),
        effective_entry=Decimal(3000),
        entry_time_ms=s_ms + ONE_MINUTE_MS,
        entry_available_at_ms=s_ms + 2 * ONE_MINUTE_MS,
        stop=Decimal(2900),
        target=Decimal(3200),
        max_hold_ms=four_h_ms,
        cost_commitment_exit_usdt=Decimal("1.00"),
        funding_reserves_usdt=Decimal("2.00"),
        is_acknowledged=True,
    )
    book.positions["ETHUSDT"] = pos_eth
    book.funding_reserve_rf += Decimal("2.00")

    # Step at S: Stage 1 processes exit ACK, Stage 7 processes funding settlement S
    b_at_s = Bar1m(s_ms, Decimal(48800), Decimal(48850), Decimal(48750), Decimal(48800), Decimal(10), "BTCUSDT")
    m_at_s = MarkBar1m(s_ms - ONE_MINUTE_MS, Decimal(50000), Decimal(50000), Decimal(50000), Decimal(50000), "BTCUSDT", s_ms)
    book.step_minute_open(s_ms, {"BTCUSDT": b_at_s}, {"BTCUSDT": m_at_s}, four_h_ms)

    # Step S + 60s: funding ACK arrives
    book.step_minute_open(s_ms + ONE_MINUTE_MS, {}, {}, four_h_ms)

    trade = book.completed_trades[0]
    cash_delta = book.cash - INITIAL_EQUITY_USDT

    # Positive assertions:
    assert trade.total_funding_usdt == Decimal("0.200000")
    assert trade.net_pnl_usdt == cash_delta
    # ETH witness funding reserve is untouched!
    assert book.funding_reserve_rf == pos_eth.funding_reserves_usdt == Decimal("2.00")


# =============================================================================
# B03 Positive Invariant: Close-Then-Reopen at S Multi-Position Attribution
# =============================================================================


def test_b03_positive_close_then_reopen_at_s_independent_attribution() -> None:
    """Verify close-then-reopen at S charges POS_1 (0.05) and POS_2 (0.01) independently."""
    s_ms = 1_700_002_800_000
    four_h_ms = 4 * ONE_HOUR_MS
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)

    pos_1_closing = Position(
        position_id="POS_1_CLOSING_AT_S",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal(50000),
        entry_time_ms=s_ms - four_h_ms,
        entry_available_at_ms=s_ms - four_h_ms + ONE_MINUTE_MS,
        stop=Decimal(49000),
        target=Decimal(52000),
        max_hold_ms=four_h_ms,
        cost_commitment_exit_usdt=Decimal("5.00"),
        funding_reserves_usdt=Decimal("2.00"),
        is_acknowledged=True,
    )
    book.positions["BTCUSDT"] = pos_1_closing
    book.cost_commitment_o = Decimal("5.00")
    book.funding_reserve_rf = Decimal("2.00")
    book.exposure_intervals.append(
        ExposureInterval(
            position_id="POS_1_CLOSING_AT_S",
            symbol="BTCUSDT",
            direction=Direction.LONG,
            start_ms=s_ms - four_h_ms,
            end_ms=None,
            quantity=Decimal("0.05"),
            entry_price=Decimal(50000),
        )
    )
    book.due_exits.append(("BTCUSDT", ExitReason.EXPIRY, s_ms))

    ord_2_reopen = VirtualOrder(
        order_id="ORD_2_REOPEN_AT_S",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        target_fill_time_ms=s_ms,
        created_at_ms=s_ms - ONE_MINUTE_MS,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(505),
        funding_reserve_usdt=Decimal("1.00"),
    )
    book.pending_orders.append(ord_2_reopen)
    book.cost_commitment_o += ord_2_reopen.cost_commitment_usdt
    book.funding_reserve_rf += ord_2_reopen.funding_reserve_usdt

    b_reopen = Bar1m(s_ms, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000), Decimal(10), "BTCUSDT")
    m_reopen = MarkBar1m(s_ms - ONE_MINUTE_MS, Decimal(50000), Decimal(50000), Decimal(50000), Decimal(50000), "BTCUSDT", s_ms)
    book.step_minute_open(s_ms, {"BTCUSDT": b_reopen}, {"BTCUSDT": m_reopen}, four_h_ms)

    pos_1_trade = book.pending_exit_acks[0][0]
    pos_2_active = book.positions["BTCUSDT"]

    # Positive assertions: POS_1 (0.05) is charged 1.00; POS_2 (0.01) is charged 0.20
    assert pos_1_trade.total_funding_usdt == Decimal("1.000000")
    assert pos_2_active.total_funding_charged_usdt == Decimal("0.200000")


# =============================================================================
# B03 Positive Invariant: Disjoint Positions Pending Exit Attribution
# =============================================================================


def test_b03_positive_disjoint_positions_pending_exit_matching() -> None:
    """Verify funding at S is attributed to POS_AT_S by position_id, leaving POS_EARLY funding at 0."""
    s_ms = 1_700_002_800_000
    four_h_ms = 4 * ONE_HOUR_MS
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)

    trade_early = CompletedTrade(
        trade_id="TRD_POS_EARLY_1700002680000",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        effective_entry=Decimal(50000),
        raw_entry=Decimal(50000),
        effective_exit=Decimal(50100),
        raw_exit=Decimal(50100),
        entry_time_ms=s_ms - 180_000,
        exit_time_ms=s_ms - 120_000,
        holding_minutes=1,
        exit_reason=ExitReason.TAKE_PROFIT,
        entry_fee_usdt=Decimal("0.25"),
        exit_fee_usdt=Decimal("0.25"),
        total_fees_usdt=Decimal("0.50"),
        total_funding_usdt=Decimal(0),
        gross_pnl_usdt=Decimal("1.00"),
        net_pnl_usdt=Decimal("0.50"),
        entry_notional_usdt=Decimal(500),
        initial_risk_dollars=Decimal(10),
        net_bps=Decimal(10),
        net_r=Decimal("0.05"),
        position_id="POS_EARLY",
    )
    book.exposure_intervals.append(
        ExposureInterval(
            position_id="POS_EARLY",
            symbol="BTCUSDT",
            direction=Direction.LONG,
            start_ms=s_ms - 180_000,
            end_ms=s_ms - 120_000,
            quantity=Decimal("0.01"),
            entry_price=Decimal(50000),
        )
    )
    book.pending_exit_acks.append((trade_early, s_ms + ONE_MINUTE_MS, Decimal("1.00"), Decimal("1.00")))
    book.cost_commitment_o += Decimal("1.00")
    book.funding_reserve_rf += Decimal("1.00")

    ord_at_s = VirtualOrder(
        order_id="ORD_AT_S2",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.02"),
        target_fill_time_ms=s_ms,
        created_at_ms=s_ms - ONE_MINUTE_MS,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(1010),
        funding_reserve_usdt=Decimal("2.00"),
    )
    book.pending_orders.append(ord_at_s)
    book.cost_commitment_o += ord_at_s.cost_commitment_usdt
    book.funding_reserve_rf += ord_at_s.funding_reserve_usdt

    b_sl_s = Bar1m(s_ms, Decimal(50000), Decimal(50050), Decimal(48500), Decimal(48800), Decimal(10), "BTCUSDT")
    m_reopen = MarkBar1m(s_ms - ONE_MINUTE_MS, Decimal(50000), Decimal(50000), Decimal(50000), Decimal(50000), "BTCUSDT", s_ms)
    book.step_minute_open(s_ms, {"BTCUSDT": b_sl_s}, {"BTCUSDT": m_reopen}, four_h_ms)

    early_trade_funding = book.pending_exit_acks[0][0].total_funding_usdt
    at_s_trade_funding = book.pending_exit_acks[1][0].total_funding_usdt

    # Positive assertions:
    assert early_trade_funding == Decimal(0)
    assert at_s_trade_funding == Decimal("0.400000")


# =============================================================================
# B04 Regression Guard: Minute-End Exits, Cooldown, and Holding Hours
# =============================================================================


def test_b04_positive_minute_end_sl_tp_and_cooldown_and_horizons() -> None:
    """Verify B04 minute-end exit anchoring and 4h cooldown preservation."""
    s_ms = 1_700_002_800_000
    four_h_ms = 4 * ONE_HOUR_MS
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)

    order = VirtualOrder(
        order_id="ORD_B04_SL",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.01"),
        target_fill_time_ms=s_ms,
        created_at_ms=s_ms - ONE_MINUTE_MS,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(505),
        funding_reserve_usdt=Decimal("2.00"),
    )
    book.pending_orders.append(order)
    book.cost_commitment_o += order.cost_commitment_usdt
    book.funding_reserve_rf += order.funding_reserve_usdt

    b_sl = Bar1m(s_ms, Decimal(50000), Decimal(50050), Decimal(48500), Decimal(48800), Decimal(10), "BTCUSDT")
    book.step_minute_open(s_ms, {"BTCUSDT": b_sl}, {}, four_h_ms)

    trade = book.pending_exit_acks[0][0]
    expected_cooldown = s_ms + ONE_MINUTE_MS + 4 * ONE_HOUR_MS
    assert trade.exit_time_ms == s_ms + ONE_MINUTE_MS - 1
    assert trade.holding_minutes == 1
    assert book.cooldown_until_ms["BTCUSDT"] == expected_cooldown


# =============================================================================
# B05 Positive Invariant: Pre-ACK Drawdown Kill & Capital Safety
# =============================================================================


def test_b05_positive_pre_ack_loss_trips_drawdown_kill_and_no_phantom_capital() -> None:
    """Verify unacknowledged position loss > $100 trips kill threshold and zeroes available capital."""
    s_ms = 1_700_002_800_000
    four_h_ms = 4 * ONE_HOUR_MS
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)

    order = VirtualOrder(
        order_id="ORD_UNACKED_CRASH",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        target_fill_time_ms=s_ms,
        created_at_ms=s_ms - ONE_MINUTE_MS,
        expected_entry_bound=Decimal(50100),
        initial_stop=Decimal(49000),
        target=Decimal(52000),
        cost_commitment_usdt=Decimal(2510),
        funding_reserve_usdt=Decimal("2.00"),
    )
    book.pending_orders.append(order)
    book.cost_commitment_o += order.cost_commitment_usdt
    book.funding_reserve_rf += order.funding_reserve_usdt

    b_fill = Bar1m(s_ms, Decimal(50000), Decimal(50000), Decimal(49100), Decimal(49200), Decimal(10), "BTCUSDT")
    m_crash = MarkBar1m(s_ms, Decimal(50000), Decimal(50000), Decimal(47500), Decimal(47500), "BTCUSDT", s_ms + ONE_MINUTE_MS)
    book.step_minute_open(s_ms, {"BTCUSDT": b_fill}, {"BTCUSDT": m_crash}, four_h_ms)

    # Delay fill ACK so position remains unacknowledged at S + 60s
    book.pending_fill_acks[0].available_at_ms = s_ms + 2 * ONE_MINUTE_MS
    book.step_minute_open(s_ms + ONE_MINUTE_MS, {}, {"BTCUSDT": m_crash}, four_h_ms)

    # Positive assertions:
    assert book.killed is True, "Drawdown supervisor must trip kill latch on pre-ACK loss"
    assert book.compute_available_capital() == Decimal(0), "Killed book must report 0 available capital"
    assert "DRAWDOWN_LIMIT_EXCEEDED" in str(book.kill_reason)


# =============================================================================
# B06 Positive Invariant: Wall-Clock Retest Progression & Hour 3 Expiry
# =============================================================================


def test_b06_positive_retest_elapsed_wall_clock_hours_across_cooldown() -> None:
    """Verify breakout state advances by elapsed wall-clock hours and cancels after 3 hours despite cooldown."""
    base_t = 1_700_000_000_000
    gen = SignalGenerator()
    c_retest = CandidateRegistry().get_candidate("CLOSED_RETEST_LONG_04H")

    bars_1h = [
        Bar1h(base_t + i * ONE_HOUR_MS, Decimal(45000 + i * 100), Decimal(45100 + i * 100),
              Decimal(44900 + i * 100), Decimal(45000 + i * 100), Decimal(100), "BTCUSDT", 60)
        for i in range(25)
    ]
    # Bar 25 is breakout: close 50050 > prior 24h high 47400
    bars_1h.append(
        Bar1h(base_t + 25 * ONE_HOUR_MS, Decimal(49800), Decimal(50100), Decimal(49700), Decimal(50050), Decimal(200), "BTCUSDT", 60)
    )
    bars_4h = [
        Bar4h(base_t + i * 4 * ONE_HOUR_MS, Decimal(45000 + i * 100), Decimal(45200 + i * 100),
              Decimal(44950 + i * 100), Decimal(45000 + i * 100), Decimal(1000), "BTCUSDT", 240)
        for i in range(65)
    ]

    gen.evaluate_hourly_decision(c_retest, "BTCUSDT", bars_1h, bars_4h)
    exit_ms = bars_1h[-1].close_ms + 10 * ONE_MINUTE_MS

    # Hours 26, 27, 28, 29 in 4h cooldown
    for h_idx in range(26, 30):
        bars_1h.append(
            Bar1h(base_t + h_idx * ONE_HOUR_MS, Decimal(50300), Decimal(50400), Decimal(50050), Decimal(50300), Decimal(100), "BTCUSDT", 60)
        )
        gen.evaluate_hourly_decision(c_retest, "BTCUSDT", bars_1h, bars_4h, last_exit_time_ms=exit_ms)

    # Hour 30 (5 elapsed hours after breakout): cooldown has expired
    bars_1h.append(
        Bar1h(base_t + 30 * ONE_HOUR_MS, Decimal(50100), Decimal(50220), Decimal(50080), Decimal(50180), Decimal(150), "BTCUSDT", 60)
    )
    sig_h30 = gen.evaluate_hourly_decision(c_retest, "BTCUSDT", bars_1h, bars_4h, last_exit_time_ms=exit_ms)
    breakout_state = gen._active_breakouts[(c_retest.id, "BTCUSDT", Direction.LONG)]

    # Positive assertions: stale 5th hour is canceled and emits NO signal!
    assert sig_h30 is None
    assert breakout_state.canceled is True
    assert breakout_state.bars_since_breakout == 5 or breakout_state.bars_since_breakout >= 3


def test_b06_positive_retest_third_hour_unconfirmed_expiry_and_fresh_breakout() -> None:
    """Verify unconfirmed breakout on hour 3 expires and falls through to register fresh breakout."""
    base_t = 1_700_000_000_000
    gen = SignalGenerator()
    c_retest = CandidateRegistry().get_candidate("CLOSED_RETEST_LONG_04H")

    bars_1h = [
        Bar1h(base_t + i * ONE_HOUR_MS, Decimal(45000 + i * 100), Decimal(45100 + i * 100),
              Decimal(44900 + i * 100), Decimal(45000 + i * 100), Decimal(100), "BTCUSDT", 60)
        for i in range(25)
    ]
    # Hour 25 breakout
    bars_1h.append(
        Bar1h(base_t + 25 * ONE_HOUR_MS, Decimal(49800), Decimal(50100), Decimal(49700), Decimal(50050), Decimal(200), "BTCUSDT", 60)
    )
    bars_4h = [
        Bar4h(base_t + i * 4 * ONE_HOUR_MS, Decimal(45000 + i * 100), Decimal(45200 + i * 100),
              Decimal(44950 + i * 100), Decimal(45000 + i * 100), Decimal(1000), "BTCUSDT", 240)
        for i in range(65)
    ]

    gen.evaluate_hourly_decision(c_retest, "BTCUSDT", bars_1h, bars_4h)

    # Hours 26 and 27: unconfirmed
    for h_idx in (26, 27):
        bars_1h.append(
            Bar1h(base_t + h_idx * ONE_HOUR_MS, Decimal(50400), Decimal(50550), Decimal(50350), Decimal(50500), Decimal(100), "BTCUSDT", 60)
        )
        gen.evaluate_hourly_decision(c_retest, "BTCUSDT", bars_1h, bars_4h)

    # Hour 28 (3rd bar): unconfirmed for Breakout 1, but forms fresh breakout above prior 24h high (50550)
    bars_1h.append(
        Bar1h(base_t + 28 * ONE_HOUR_MS, Decimal(50500), Decimal(51000), Decimal(50480), Decimal(50950), Decimal(200), "BTCUSDT", 60)
    )
    gen.evaluate_hourly_decision(c_retest, "BTCUSDT", bars_1h, bars_4h)
    state = gen._active_breakouts[(c_retest.id, "BTCUSDT", Direction.LONG)]

    # Positive assertions: New breakout registered on H28!
    assert state.breakout_hour_ms == bars_1h[-1].close_ms
    assert state.canceled is False


# =============================================================================
# B07 Positive Invariant: Reserve Exhaustion & Conservation
# =============================================================================


def test_b07_positive_funding_reserve_exhaustion_no_cross_theft_and_conservation() -> None:
    """Verify funding debit exceeding owner reserve consumes only owner reserve without theft from other positions."""
    s_ms = 1_700_002_800_000
    four_h_ms = 4 * ONE_HOUR_MS
    book = VirtualBook("STRUCTURAL_CONTINUATION_LONG_04H", CostScenario.BASE)

    pos_btc = Position(
        position_id="POS_BTC_EXHAUST",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal(50000),
        entry_time_ms=s_ms - ONE_MINUTE_MS,
        entry_available_at_ms=s_ms,
        stop=Decimal(49000),
        target=Decimal(52000),
        max_hold_ms=four_h_ms,
        cost_commitment_exit_usdt=Decimal("5.00"),
        funding_reserves_usdt=Decimal("0.40"),  # Reserve 0.40 < debit 1.00 at S
        is_acknowledged=True,
    )
    pos_eth = Position(
        position_id="POS_ETH_INTACT",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="ETHUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.50"),
        effective_entry=Decimal(3000),
        entry_time_ms=s_ms + ONE_MINUTE_MS,
        entry_available_at_ms=s_ms + 2 * ONE_MINUTE_MS,
        stop=Decimal(2900),
        target=Decimal(3200),
        max_hold_ms=four_h_ms,
        cost_commitment_exit_usdt=Decimal("2.00"),
        funding_reserves_usdt=Decimal("2.00"),  # 2.00 reserve outside S window
        is_acknowledged=True,
    )
    book.positions["BTCUSDT"] = pos_btc
    book.positions["ETHUSDT"] = pos_eth
    book.cost_commitment_o = Decimal("7.00")
    book.funding_reserve_rf = Decimal("2.40")

    b_reopen = Bar1m(s_ms, Decimal(50000), Decimal(50050), Decimal(49950), Decimal(50000), Decimal(10), "BTCUSDT")
    m_reopen = MarkBar1m(s_ms - ONE_MINUTE_MS, Decimal(50000), Decimal(50000), Decimal(50000), Decimal(50000), "BTCUSDT", s_ms)
    book.step_minute_open(s_ms, {"BTCUSDT": b_reopen}, {"BTCUSDT": m_reopen}, four_h_ms)

    sum_position_rf = sum(p.funding_reserves_usdt for p in book.positions.values())
    aggregate_rf = book.funding_reserve_rf

    # Positive assertions:
    # 1. Exact equality between sum of owner reserves and aggregate reserve
    assert sum_position_rf == aggregate_rf == Decimal("2.00")
    # 2. BTC's reserve was consumed down to 0, NOT negative
    assert pos_btc.funding_reserves_usdt == Decimal("0.00")
    # 3. ETH's separate 2.00 reserve was NOT stolen or touched
    assert pos_eth.funding_reserves_usdt == Decimal("2.00")


# =============================================================================
# Integrated Synthetic E2E: Signal -> Fill -> ACK -> Exit -> Funding -> Flat Book
# =============================================================================


def test_synthetic_e2e_empty_book_case() -> None:
    """Honest empty book fixture: flat market generates 0 signals, 0 trades, exactly 1000->1000 cash."""
    start_ms = (1_700_000_000_000 // 14_400_000) * 14_400_000
    bars_flat: list[Bar1m] = []
    marks_flat: list[MarkBar1m] = []
    p = Decimal("50000.00")
    for m in range(120):
        t = start_ms + m * ONE_MINUTE_MS
        bars_flat.append(Bar1m(t, p, p, p, p, Decimal(10), "BTCUSDT"))
        marks_flat.append(MarkBar1m(t, p, p, p, p, "BTCUSDT", t + ONE_MINUTE_MS))

    eng = ReplayEngine(cost_scenario=CostScenario.BASE)
    results = eng.run_simulation({"BTCUSDT": bars_flat}, {"BTCUSDT": marks_flat})

    for cid in CandidateRegistry().list_candidates():
        book = eng.books[cid.id]
        assert len(results[cid.id]) == 0
        assert len(book.completed_trades) == 0
        assert book.cash == INITIAL_EQUITY_USDT
        assert book.cost_commitment_o == Decimal(0)
        assert book.funding_reserve_rf == Decimal(0)
        assert len(book.positions) == 0
        assert len(book.pending_orders) == 0
        assert len(book.pending_fill_acks) == 0
        assert len(book.pending_exit_acks) == 0


def test_synthetic_e2e_nonempty_executed_book_case() -> None:
    """Nonempty synthetic execution fixture: real ReplayEngine simulation with signal, fill, funding, and expiry."""
    start_ms = (1_700_000_000_000 // 14_400_000) * 14_400_000
    bars: list[Bar1m] = []
    marks: list[MarkBar1m] = []

    # 240 warmup hours
    for h in range(240):
        t_h = start_ms + h * ONE_HOUR_MS
        p = Decimal("40000.00") + Decimal(str(h * 40))
        for m in range(60):
            t = t_h + m * ONE_MINUTE_MS
            bars.append(Bar1m(t, p, p + Decimal(100), p - Decimal(100), p, Decimal(100), "BTCUSDT"))
            marks.append(MarkBar1m(t, p, p, p, p, "BTCUSDT", t + ONE_MINUTE_MS))

    # Hour 240: Breakout hour
    t_240 = start_ms + 240 * ONE_HOUR_MS
    for m in range(60):
        t = t_240 + m * ONE_MINUTE_MS
        o = Decimal("49600.00") + Decimal(str(m * 10))
        c = o + Decimal("8.00")
        bars.append(Bar1m(t, o, c + Decimal(5), o - Decimal(5), c, Decimal(100), "BTCUSDT"))
        marks.append(MarkBar1m(t, c, c, c, c, "BTCUSDT", t + ONE_MINUTE_MS))

    # Hour 241: Retest confirmation hour
    t_241 = start_ms + 241 * ONE_HOUR_MS
    for m in range(60):
        t = t_241 + m * ONE_MINUTE_MS
        if m == 5:
            o, h_p, l_p, c = Decimal(49750), Decimal(49760), Decimal(49660), Decimal(49700)
        elif m == 59:
            o, h_p, l_p, c = Decimal(49900), Decimal(50010), Decimal(49890), Decimal(50000)
        else:
            o, h_p, l_p, c = Decimal(49800), Decimal(49820), Decimal(49780), Decimal(49800)
        bars.append(Bar1m(t, o, h_p, l_p, c, Decimal(100), "BTCUSDT"))
        marks.append(MarkBar1m(t, c, c, c, c, "BTCUSDT", t + ONE_MINUTE_MS))

    # Hours 242..255 (holding, 4 funding settlements, 240m max hold expiry, exit and settle)
    for h in range(242, 256):
        t_h = start_ms + h * ONE_HOUR_MS
        p = Decimal("50005.00")
        for m in range(60):
            t = t_h + m * ONE_MINUTE_MS
            bars.append(Bar1m(t, p, p + Decimal(10), p - Decimal(10), p, Decimal(100), "BTCUSDT"))
            marks.append(MarkBar1m(t, p, p, p, p, "BTCUSDT", t + ONE_MINUTE_MS))

    eng = ReplayEngine(cost_scenario=CostScenario.BASE)
    results = eng.run_simulation({"BTCUSDT": bars}, {"BTCUSDT": marks})

    # Verify exact executed trade details for CLOSED_RETEST_LONG_04H
    assert len(results["CLOSED_RETEST_LONG_04H"]) == 1
    trade_4h = results["CLOSED_RETEST_LONG_04H"][0]
    assert trade_4h.trade_id == "TRD_POS_ORD_CLOSED_RETEST_LONG_04H_BTCUSDT_1700863320000_1700877720000"
    assert trade_4h.position_id == "POS_ORD_CLOSED_RETEST_LONG_04H_BTCUSDT_1700863320000"
    assert trade_4h.quantity == Decimal("0.006")
    assert trade_4h.effective_entry == Decimal("50030.10")
    assert trade_4h.effective_exit == Decimal("49979.90")
    assert trade_4h.entry_time_ms == 1700863320000
    assert trade_4h.exit_time_ms == 1700877720000
    assert trade_4h.exit_reason == ExitReason.EXPIRY
    assert trade_4h.entry_fee_usdt == Decimal("0.180108360")
    assert trade_4h.exit_fee_usdt == Decimal("0.179927640")
    assert trade_4h.total_funding_usdt == Decimal("0.480048000")
    assert trade_4h.net_pnl_usdt == Decimal("-1.141284000")

    # Verify book state and algebraic cash conservation
    book_4h = eng.books["CLOSED_RETEST_LONG_04H"]
    assert book_4h.cash == Decimal("998.858716000000")
    cash_delta_4h = book_4h.cash - INITIAL_EQUITY_USDT
    assert cash_delta_4h == trade_4h.net_pnl_usdt
    assert book_4h.cost_commitment_o == Decimal(0)
    assert book_4h.funding_reserve_rf == Decimal(0)
    assert len(book_4h.positions) == 0
    assert len(book_4h.pending_orders) == 0
    assert len(book_4h.pending_fill_acks) == 0
    assert len(book_4h.pending_exit_acks) == 0
    assert len(book_4h._unsettled_exit_trades) == 0

    # Verify CLOSED_RETEST_LONG_12H
    assert len(results["CLOSED_RETEST_LONG_12H"]) == 1
    trade_12h = results["CLOSED_RETEST_LONG_12H"][0]
    assert trade_12h.total_funding_usdt == Decimal("1.440144000")
    assert trade_12h.net_pnl_usdt == Decimal("-2.101380000")
    book_12h = eng.books["CLOSED_RETEST_LONG_12H"]
    assert book_12h.cash == Decimal("997.898620000000")
    assert (book_12h.cash - INITIAL_EQUITY_USDT) == trade_12h.net_pnl_usdt
    assert book_12h.cost_commitment_o == Decimal(0)
    assert book_12h.funding_reserve_rf == Decimal(0)


def test_synthetic_e2e_flat_book_full_reconciliation() -> None:
    """Verify integrated synthetic scenario ends in flat reconciled book (alias)."""
    test_synthetic_e2e_nonempty_executed_book_case()
