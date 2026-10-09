"""Tests for cost model, tick/lot rounding, virtual book ledger, and risk controls."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.constants import (
    ALLOCATION_CEILING_PER_ASSET_USDT,
    INITIAL_EQUITY_USDT,
)
from btc_quant_agent.strategy_research.r3_overnight.cost_model import (
    CostModel,
    floor_to_lot,
)
from btc_quant_agent.strategy_research.r3_overnight.ledger import VirtualBook
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1m,
    CostScenario,
    Direction,
    ExitReason,
    MarkBar1m,
    SymbolFilters,
)


def test_cost_model_rates_and_friction():
    base_model = CostModel(CostScenario.BASE)
    assert base_model.friction_bps == Decimal(5)  # 2bp half spread + 3bp slip
    assert base_model.fee_bps == Decimal(6)  # 6bp taker fee
    # Round trip: 2 * (5 + 6) = 22 bps

    stress_model = CostModel(CostScenario.STRESS)
    assert stress_model.friction_bps == Decimal(10)  # 4bp half spread + 6bp slip
    assert stress_model.fee_bps == Decimal(12)  # 12bp taker fee
    # Round trip: 2 * (10 + 12) = 44 bps


def test_tick_and_lot_rounding():
    filters = SymbolFilters(symbol="BTCUSDT", tick_size=Decimal("0.10"), step_size=Decimal("0.001"))

    # Buy order embeds adverse friction upward, rounded UP to tick
    base_model = CostModel(CostScenario.BASE)
    raw_p = Decimal("50000.00")
    # friction rate = 5 / 10000 = 0.0005
    # raw_p * 1.0005 = 50025.00 -> rounded to tick 0.10 is 50025.00
    exec_p = base_model.model_execution_price(raw_p, is_buy=True, filters=filters)
    assert exec_p == Decimal("50025.00")

    # Sell order embeds adverse friction downward, rounded DOWN to tick
    exec_p_sell = base_model.model_execution_price(raw_p, is_buy=False, filters=filters)
    # raw_p * 0.9995 = 49975.00
    assert exec_p_sell == Decimal("49975.00")

    # Floor to lot: 0.1239 BTC -> 0.123 BTC
    assert floor_to_lot(Decimal("0.1239"), filters.step_size) == Decimal("0.123")


def test_virtual_book_initial_capital_and_reserves():
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    assert book.cash == INITIAL_EQUITY_USDT == Decimal("1000.000000000000")
    assert book.high_water_equity == INITIAL_EQUITY_USDT
    assert book.decision_equity == INITIAL_EQUITY_USDT

    # Available capital A = 0.95 * 1000 = 950 USDT (preserving 5% reserve)
    avail_a = book.compute_available_capital()
    assert avail_a == Decimal("950.000000000000")

    # Budget B = min(333.333333333333, 950/3, 950 - 0) = 316.6666666666666...
    budget_b = book.compute_asset_budget("BTCUSDT", avail_a)
    assert budget_b <= ALLOCATION_CEILING_PER_ASSET_USDT
    assert budget_b == avail_a / Decimal(3)


def test_drawdown_kill_latch():
    book = VirtualBook(candidate_id="STRUCTURAL_CONTINUATION_LONG_04H", cost_scenario=CostScenario.BASE)
    t = 1_700_000_000_000

    # Inject mark that values book at 890 USDT (loss of 110 USDT > 100 USDT limit)
    # Give book a fake position of 0.05 BTC bought at 50,000 USDT (2,500 notional)
    from btc_quant_agent.strategy_research.r3_overnight.types import Position
    book.positions["BTCUSDT"] = Position(
        position_id="POS_1",
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        quantity=Decimal("0.05"),
        effective_entry=Decimal("50000.00"),
        entry_time_ms=t,
        entry_available_at_ms=t + 60_000,
        stop=Decimal("49000.00"),
        target=Decimal("52000.00"),
        max_hold_ms=240 * 60_000,
        cost_commitment_exit_usdt=Decimal("5.0"),
    )

    # Mark price drops to 47,500 -> unrealized loss = 0.05 * 2500 = 125 USDT.
    # Equity = 1000 - 125 = 875 USDT -> Drawdown = 125 USDT > 100 USDT threshold!
    marks = {
        "BTCUSDT": MarkBar1m(
            timestamp_ms=t,
            open=Decimal(47500),
            high=Decimal(47500),
            low=Decimal(47500),
            close=Decimal(47500),
            symbol="BTCUSDT",
            available_at_ms=t + 60_000,
        )
    }
    bars = {
        "BTCUSDT": Bar1m(
            timestamp_ms=t + 60_000,
            open=Decimal(47500),
            high=Decimal(47500),
            low=Decimal(47500),
            close=Decimal(47500),
            volume=Decimal(10),
            symbol="BTCUSDT",
        )
    }

    book.step_minute_open(
        open_time_ms=t + 60_000,
        bars_1m=bars,
        marks_1m=marks,
        candidate_max_hold_ms=240 * 60_000,
    )

    assert book.killed is True
    assert "DRAWDOWN_LIMIT_EXCEEDED" in str(book.kill_reason)
    # Liquidation queued for next open
    assert any(e[0] == "BTCUSDT" and e[1] == ExitReason.DRAWDOWN_KILL for e in book.due_exits)
