"""Hermetic tests for G2 R3 Two-Clock Accounting, Fill, Cost, Funding Ownership & Risk Supervisor."""

from __future__ import annotations

import decimal
from decimal import Decimal

import pytest

from scripts.strategy_research.r3_verification.oracle_specs import (
    BASE_COST_SCENARIO,
    INITIAL_EQUITY_USDT,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
    STRESS_COST_SCENARIO,
    FillAckSubPriority,
    MessageTypePriority,
    round_execution_price,
    round_ledger_usdt,
)
from scripts.strategy_research.r3_verification.two_clock_accounting_oracle import (
    IndependentBookOracle,
    MarketBarMessage,
    MatchedEpisodeOracle,
    OracleMessage,
    SettlementWindow,
    SymbolFilterSpec,
)


def _default_filters() -> dict[str, SymbolFilterSpec]:
    return {
        "BTCUSDT": SymbolFilterSpec(
            symbol="BTCUSDT",
            tick_size=Decimal("0.1"),
            lot_size=Decimal("0.001"),
            min_notional_usdt=Decimal("5.0"),
        ),
        "ETHUSDT": SymbolFilterSpec(
            symbol="ETHUSDT",
            tick_size=Decimal("0.01"),
            lot_size=Decimal("0.01"),
            min_notional_usdt=Decimal("5.0"),
        ),
        "SOLUSDT": SymbolFilterSpec(
            symbol="SOLUSDT",
            tick_size=Decimal("0.01"),
            lot_size=Decimal("0.1"),
            min_notional_usdt=Decimal("5.0"),
        ),
    }


def test_22bp_base_and_44bp_stress_cost_reconciliation_no_double_debit() -> None:
    """Verify 22bp/44bp round-trip cost, tick rounding, and that embedded friction is never debited twice."""
    assert BASE_COST_SCENARIO.round_trip_one_time_bps == Decimal(22)
    assert STRESS_COST_SCENARIO.round_trip_one_time_bps == Decimal(44)

    t0 = 1_767_225_600_000
    book = IndependentBookOracle(
        book_id="BOOK_BASE",
        cost_scenario=BASE_COST_SCENARIO,
        filters=_default_filters(),
    )
    book.last_available_marks["BTCUSDT"] = (Decimal("50000.0"), t0, t0 + ONE_MINUTE_MS)

    order = book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=t0 + ONE_MINUTE_MS,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("400.0"),
        raw_stop=Decimal("49400.0"),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=1,
    )
    assert order is not None

    # Execute entry at t0 + 120000, and hit ordinary target at 51250 in the next minute
    open_entry = t0 + 2 * ONE_MINUTE_MS
    book.step_minute_open(
        open_entry,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49950.0"),
                close=Decimal("50050.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49950.0"),
                close=Decimal("50050.0"),
                is_mark=True,
            )
        },
    )
    assert "BTCUSDT" in book.economic_positions
    pos = book.economic_positions["BTCUSDT"]

    # Next minute hits target
    open_exit = open_entry + ONE_MINUTE_MS
    book.step_minute_open(
        open_exit,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_2",
                symbol="BTCUSDT",
                open_ms=open_exit,
                open=Decimal("50100.0"),
                high=pos.target_price + Decimal("100.0"),
                low=Decimal("50050.0"),
                close=pos.target_price + Decimal("50.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_2",
                symbol="BTCUSDT",
                open_ms=open_exit,
                open=Decimal("50100.0"),
                high=pos.target_price + Decimal("100.0"),
                low=Decimal("50050.0"),
                close=pos.target_price,
                is_mark=True,
            )
        },
    )
    assert len(book.completed_trades) == 1
    tr = book.completed_trades[0]
    assert tr.exit_reason == "INTRABAR_TP"
    # Verify PnL bridge: net_pnl == effective_quote_pnl - entry_fee - exit_fee - funding
    assert tr.net_pnl_usdt == round_ledger_usdt(
        tr.effective_quote_pnl_usdt
        - tr.entry_fee_usdt
        - tr.exit_fee_usdt
        - tr.funding_cashflow_usdt
    )
    # Verify economic cash equals initial 1000 + net_pnl (no double debit of spread/slippage)
    assert book.economic_cash_usdt == round_ledger_usdt(
        INITIAL_EQUITY_USDT + tr.net_pnl_usdt
    )


def test_stop_first_same_minute_and_gap_tp_cap() -> None:
    """Verify SL_FIRST when a 1m bar touches both SL and TP, and TP cap on forced/time gap exits."""
    t0 = 1_767_225_600_000
    book = IndependentBookOracle(
        book_id="BOOK_SL_TP",
        cost_scenario=STRESS_COST_SCENARIO,
        filters=_default_filters(),
    )
    book.last_available_marks["BTCUSDT"] = (Decimal("50000.0"), t0, t0 + ONE_MINUTE_MS)
    book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=t0 + ONE_MINUTE_MS,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("500.0"),
        raw_stop=Decimal("49200.0"),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=4,
    )

    open_entry = t0 + 2 * ONE_MINUTE_MS
    # Same-bar touches both SL (49200) and TP (~51672) -> SL must resolve first!
    book.step_minute_open(
        open_entry,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_BOTH",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("53000.0"),
                low=Decimal("49000.0"),
                close=Decimal("52000.0"),
                volume=Decimal(20),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_BOTH",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("53000.0"),
                low=Decimal("49000.0"),
                close=Decimal("52000.0"),
                is_mark=True,
            )
        },
    )
    assert len(book.completed_trades) == 1
    assert book.completed_trades[0].exit_reason == "INTRABAR_SL_FIRST_COLLISION"
    assert book.completed_trades[0].raw_exit_price == Decimal(49200)

    # Now test forced/time exit target cap on a fresh book:
    # When expiry open gaps favorably beyond target, raw exit price is capped at target!
    book2 = IndependentBookOracle(
        book_id="BOOK_TP_CAP",
        cost_scenario=STRESS_COST_SCENARIO,
        filters=_default_filters(),
    )
    book2.last_available_marks["BTCUSDT"] = (Decimal("50000.0"), t0, t0 + ONE_MINUTE_MS)
    book2.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=t0 + ONE_MINUTE_MS,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("500.0"),
        raw_stop=Decimal("49200.0"),
        max_hold_ms=ONE_MINUTE_MS,  # Expires at next minute open
        settlement_events_in_hold=1,
    )
    book2.step_minute_open(
        open_entry,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB2_1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50050.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB2_1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50050.0"),
                is_mark=True,
            )
        },
    )
    target_px = book2.economic_positions["BTCUSDT"].target_price

    # At open_entry + 60000, trade open gaps to 55000 (> target_px) -> must cap at target_px
    book2.step_minute_open(
        open_entry + ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB2_2",
                symbol="BTCUSDT",
                open_ms=open_entry + ONE_MINUTE_MS,
                open=Decimal("55000.0"),
                high=Decimal("55100.0"),
                low=Decimal("54900.0"),
                close=Decimal("55000.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB2_2",
                symbol="BTCUSDT",
                open_ms=open_entry + ONE_MINUTE_MS,
                open=Decimal("55000.0"),
                high=Decimal("55100.0"),
                low=Decimal("54900.0"),
                close=Decimal("55000.0"),
                is_mark=True,
            )
        },
    )
    assert len(book2.completed_trades) == 1
    assert book2.completed_trades[0].raw_exit_price == target_px


def test_two_clock_separation_delayed_mark_and_delayed_kill_latch() -> None:
    """Delayed mark cannot veto earlier entry; economic insolvency precedes causal decision kill."""
    t0 = 1_767_225_600_000
    book = IndependentBookOracle(
        book_id="BOOK_CLOCK",
        cost_scenario=STRESS_COST_SCENARIO,
        filters=_default_filters(),
    )
    book.last_available_marks["BTCUSDT"] = (Decimal("50000.0"), t0, t0 + ONE_MINUTE_MS)

    book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=t0 + ONE_MINUTE_MS,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("500.0"),
        raw_stop=Decimal("49200.0"),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=1,
    )

    # At open_entry = t0 + 120000, position enters at 50000; mark crashes to 30000 at close of this minute!
    # Economic ledger E_e immediately observes the crash at Stage 8 of open_entry,
    # but Decision ledger E_d does NOT see that mark until available_at = open_entry + 120000!
    open_entry = t0 + 2 * ONE_MINUTE_MS
    step1 = book.step_minute_open(
        open_entry,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_CRASH_1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50050.0"),
                low=Decimal("49500.0"),
                close=Decimal("49600.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_CRASH_1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50000.0"),
                low=Decimal("30000.0"),
                close=Decimal("30000.0"),
                is_mark=True,
            )
        },
    )
    # Economic drawdown > 100 USDT immediately in Stage 8, but Decision kill_latched is still False!
    assert step1["stage8_report"]["economic_drawdown_usdt"] > Decimal(100)  # type: ignore[index]
    assert book.kill_latched is False

    # At open_entry + 60000, FILL_ACK is consumed, but MB_CRASH_1 is only available at open_entry + 120000
    step2 = book.step_minute_open(
        open_entry + ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_CRASH_2",
                symbol="BTCUSDT",
                open_ms=open_entry + ONE_MINUTE_MS,
                open=Decimal("49600.0"),
                high=Decimal("49700.0"),
                low=Decimal("49500.0"),
                close=Decimal("49600.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_CRASH_2",
                symbol="BTCUSDT",
                open_ms=open_entry + ONE_MINUTE_MS,
                open=Decimal("30000.0"),
                high=Decimal("30000.0"),
                low=Decimal("30000.0"),
                close=Decimal("30000.0"),
                is_mark=True,
            )
        },
    )
    assert book.kill_latched is False
    assert step2["stage2_risk"]["kill_latched"] is False  # type: ignore[index]

    # At open_entry + 120000, MB_CRASH_1 becomes available in Stage 1 -> Stage 2 latches kill
    # and queues liquidation for the NEXT open (open_entry + 180000), never same-open lookahead!
    step3 = book.step_minute_open(
        open_entry + 2 * ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_CRASH_3",
                symbol="BTCUSDT",
                open_ms=open_entry + 2 * ONE_MINUTE_MS,
                open=Decimal("49600.0"),
                high=Decimal("49700.0"),
                low=Decimal("49500.0"),
                close=Decimal("49600.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_CRASH_3",
                symbol="BTCUSDT",
                open_ms=open_entry + 2 * ONE_MINUTE_MS,
                open=Decimal("30000.0"),
                high=Decimal("30000.0"),
                low=Decimal("30000.0"),
                close=Decimal("30000.0"),
                is_mark=True,
            )
        },
    )
    assert book.kill_latched is True
    assert step3["stage4_exits"] == []  # Not liquidated at the same open!
    assert "BTCUSDT" in book.economic_positions

    # At open_entry + 180000, the due KILL_EXIT executes at Stage 4
    step4 = book.step_minute_open(
        open_entry + 3 * ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_CRASH_4",
                symbol="BTCUSDT",
                open_ms=open_entry + 3 * ONE_MINUTE_MS,
                open=Decimal("49550.0"),
                high=Decimal("49600.0"),
                low=Decimal("49500.0"),
                close=Decimal("49550.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_CRASH_4",
                symbol="BTCUSDT",
                open_ms=open_entry + 3 * ONE_MINUTE_MS,
                open=Decimal("30000.0"),
                high=Decimal("30000.0"),
                low=Decimal("30000.0"),
                close=Decimal("30000.0"),
                is_mark=True,
            )
        },
    )
    assert len(step4["stage4_exits"]) == 1  # type: ignore[arg-type]
    assert book.completed_trades[-1].exit_reason == "DECISION_DRAWDOWN_OR_INSOLVENCY_KILL"
    assert "BTCUSDT" not in book.economic_positions


def test_funding_ownership_window_reduction_max_qty_and_no_positive_credit() -> None:
    """Verify [S-15000, S+15000] ownership, max(pre,post) on reduction, charge once, and 0 positive credit."""
    t0 = 1_767_225_600_000
    book = IndependentBookOracle(
        book_id="BOOK_FUND",
        cost_scenario=STRESS_COST_SCENARIO,
        filters=_default_filters(),
    )
    book.last_available_marks["BTCUSDT"] = (Decimal("50000.0"), t0, t0 + ONE_MINUTE_MS)
    book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=t0 + ONE_MINUTE_MS,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("500.0"),
        raw_stop=Decimal("49200.0"),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=2,
    )

    open_entry = t0 + 2 * ONE_MINUTE_MS
    book.step_minute_open(
        open_entry,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_F1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_F1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                is_mark=True,
            )
        },
    )
    initial_qty = book.economic_positions["BTCUSDT"].quantity

    # Settlement at open_entry + 60000 (00:03:00Z); window [00:02:45Z, 00:03:15Z]
    # Last intersecting minute is [00:03:00Z, 00:04:00Z), whose end is open_entry + 120000
    settlement_ms = open_entry + ONE_MINUTE_MS
    settlement = SettlementWindow(
        settlement_id="SETTLE_0003",
        symbol="BTCUSDT",
        settlement_ms=settlement_ms,
        settlement_mark_price=Decimal("50200.0"),
        actual_rate=Decimal("-0.0005"),  # Favorable negative rate for LONG -> still adverse debit in stress!
        is_measured_schedule=True,
    )

    # At open_entry + 60000 (minute [00:03, 00:04)), all intersecting minutes have completed at Stage 7
    step_fund = book.step_minute_open(
        settlement_ms,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_F2",
                symbol="BTCUSDT",
                open_ms=settlement_ms,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_F2",
                symbol="BTCUSDT",
                open_ms=settlement_ms,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                is_mark=True,
            )
        },
        settlements_to_check=[settlement],
    )
    charges = step_fund["stage7_funding"]
    assert isinstance(charges, list) and len(charges) == 1
    assert charges[0]["quantity_charged"] == initial_qty
    # Stress charges max(2 * adverse_actual, 8bp) = 8bp > 0 (never a negative debit / positive credit!)
    assert charges[0]["funding_debit_usdt"] > Decimal(0)

    # Passing the same settlement_id again on the next minute must NOT charge a second time
    step_repeat = book.step_minute_open(
        settlement_ms + ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_F3",
                symbol="BTCUSDT",
                open_ms=settlement_ms + ONE_MINUTE_MS,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                volume=Decimal(10),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_F3",
                symbol="BTCUSDT",
                open_ms=settlement_ms + ONE_MINUTE_MS,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                is_mark=True,
            )
        },
        settlements_to_check=[settlement],
    )
    assert step_repeat["stage7_funding"] == []


def test_5pct_buffer_1x_constraints_release_once_and_simultaneous_canonical_sizing() -> None:
    """Verify 5% admission buffer, simultaneous canonical sizing, and release-once reserve guard."""
    t0 = 1_767_225_600_000
    book = IndependentBookOracle(
        book_id="BOOK_CAP",
        cost_scenario=STRESS_COST_SCENARIO,
        filters=_default_filters(),
    )
    for sym, px in (
        ("BTCUSDT", Decimal("50000.0")),
        ("ETHUSDT", Decimal("2500.0")),
        ("SOLUSDT", Decimal("100.0")),
    ):
        book.last_available_marks[sym] = (px, t0, t0 + ONE_MINUTE_MS)

    # Initial admissible capital A = 0.95 * 1000 = 950 USDT (5% buffer = 50 USDT)
    assert book.compute_admissible_capital_a() == Decimal("950.000000000000")

    # Schedule simultaneous entries across all 3 symbols in Stage 3
    step_sched = book.step_minute_open(
        t0 + ONE_MINUTE_MS,
        scheduled_entry_specs=[
            {
                "symbol": "SOLUSDT",
                "direction": 1,
                "decision_close": Decimal("100.0"),
                "atr20": Decimal("1.0"),
                "raw_stop": Decimal("98.5"),
                "max_hold_ms": 4 * ONE_HOUR_MS,
                "settlement_events_in_hold": 4,
            },
            {
                "symbol": "BTCUSDT",
                "direction": 1,
                "decision_close": Decimal("50000.0"),
                "atr20": Decimal("500.0"),
                "raw_stop": Decimal("49250.0"),
                "max_hold_ms": 4 * ONE_HOUR_MS,
                "settlement_events_in_hold": 4,
            },
            {
                "symbol": "ETHUSDT",
                "direction": -1,
                "decision_close": Decimal("2500.0"),
                "atr20": Decimal("25.0"),
                "raw_stop": Decimal("2537.5"),
                "max_hold_ms": 4 * ONE_HOUR_MS,
                "settlement_events_in_hold": 4,
            },
        ],
    )
    # Canonical ordering commits BTCUSDT, ETHUSDT, SOLUSDT sequentially
    assert [o.symbol for o in book.due_orders] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert len(step_sched["stage3_scheduled"]["scheduled_entries"]) == 3  # type: ignore[index]

    # Total reserved commitments C_o + R_f must not exceed 950 USDT (1x constraint & 5% buffer)
    c_o, r_f = book.compute_outstanding_reserves()
    assert c_o + r_f <= Decimal("950.000000000000")

    # Verify release-once invariant raises RuntimeError if a reserve is released twice
    first_res = next(iter(book.reserves.values()))
    first_res.release_once()
    with pytest.raises(RuntimeError, match="DOUBLE_RESERVE_RELEASE_ERROR"):
        first_res.release_once()


def test_total_message_ordering_and_duplicate_id_rejection() -> None:
    """Verify (available_at, event_at, type_priority, sub_priority, parent_order_id, symbol, source_id)."""
    m_mark = OracleMessage(
        available_at_ms=1000,
        event_at_ms=900,
        type_priority=MessageTypePriority.MARK_BAR,
        sub_priority=0,
        parent_order_id="P1",
        symbol="BTCUSDT",
        source_id="ID_MARK",
        payload={},
    )
    m_trade = OracleMessage(
        available_at_ms=1000,
        event_at_ms=900,
        type_priority=MessageTypePriority.TRADE_BAR,
        sub_priority=0,
        parent_order_id="P1",
        symbol="BTCUSDT",
        source_id="ID_TRADE",
        payload={},
    )
    m_fund = OracleMessage(
        available_at_ms=1000,
        event_at_ms=900,
        type_priority=MessageTypePriority.FUNDING_ACK,
        sub_priority=0,
        parent_order_id="P1",
        symbol="BTCUSDT",
        source_id="ID_FUND",
        payload={},
    )
    m_fill_entry = OracleMessage(
        available_at_ms=1000,
        event_at_ms=900,
        type_priority=MessageTypePriority.FILL_ACK,
        sub_priority=int(FillAckSubPriority.ENTRY),
        parent_order_id="P2",
        symbol="BTCUSDT",
        source_id="ID_FILL_ENTRY",
        payload={},
    )
    m_fill_exit = OracleMessage(
        available_at_ms=1000,
        event_at_ms=900,
        type_priority=MessageTypePriority.FILL_ACK,
        sub_priority=int(FillAckSubPriority.EXIT_OR_REDUCTION),
        parent_order_id="P1",
        symbol="BTCUSDT",
        source_id="ID_FILL_EXIT",
        payload={},
    )

    shuffled = [m_mark, m_fill_entry, m_trade, m_fill_exit, m_fund]
    ordered = sorted(shuffled, key=lambda m: m.sort_key)
    assert [m.source_id for m in ordered] == [
        "ID_FILL_EXIT",
        "ID_FILL_ENTRY",
        "ID_FUND",
        "ID_TRADE",
        "ID_MARK",
    ]

    book = IndependentBookOracle(book_id="BOOK_DUP")
    book.enqueue_message(m_trade)
    with pytest.raises(ValueError, match="DUPLICATE_MESSAGE_ID"):
        book.enqueue_message(m_trade)
    assert book.source_blocked is True


def test_hermetic_decimal_precision_and_matched_counterfactual_episodes() -> None:
    """Verify global Decimal context mutation cannot alter oracle rounding, and matched episodes stay unfunded."""
    prev_prec = decimal.getcontext().prec
    prev_round = decimal.getcontext().rounding
    try:
        decimal.getcontext().prec = 3
        decimal.getcontext().rounding = decimal.ROUND_DOWN

        px = round_execution_price(
            Decimal("50000.123456"),
            is_buy=True,
            cost_scenario=STRESS_COST_SCENARIO,
            tick_size=Decimal("0.01"),
        )
        # 50000.123456 * 1.001 = 50050.123579456 -> ceil to 0.01 = 50050.13
        assert px == Decimal("50050.13")

        ep = MatchedEpisodeOracle.evaluate_paired_episode(
            episode_id="EP_01",
            symbol="BTCUSDT",
            entry_at_ms=1_767_225_600_000,
            candidate_direction=1,
            candidate_net_bps=Decimal("18.5"),
            matched_long_net_bps=Decimal("18.5"),
            matched_short_net_bps=Decimal("-62.5"),
            overlaps_prior_episode=True,
        )
        assert ep.balanced_50_50_net_bps == Decimal("-22.000000000000")
        assert ep.incremental_vs_balanced_bps == Decimal("40.500000000000")
        assert ep.incremental_vs_same_direction_bps == Decimal("0.000000000000")
        assert ep.is_funded_portfolio_position is False
    finally:
        decimal.getcontext().prec = prev_prec
        decimal.getcontext().rounding = prev_round
