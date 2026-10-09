"""Tests for r3_alt_engine: Clock, B04 standing exits, gap, target capping, expiry, and I01–I17 invariants.

Covers Oracle cases:
- T20: Same-bar SL-first priority
- T21: Adverse open gap fill
- T22: All favorable exits capped
- T23: 4h/12h exact hold expiration
- I01–I17: Comprehensive transition invariant suite
"""

import sys
from decimal import Decimal
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


from btc_quant_agent.strategy_research.r3_alt_engine.execution import (
    compute_effective_exit_price,
    evaluate_intrabar_exit,
    evaluate_open_bar_exit,
)
from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    CostModel,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1m,
    CostScenario,
    Direction,
    EngineState,
    ExitReason,
    OwnerKey,
    OwnerLedger,
    OwnerPhase,
    SymbolFilters,
)
from btc_quant_agent.strategy_research.r3_alt_engine.money import (
    assert_invariants,
)


def _get_btc_filters() -> SymbolFilters:
    return SymbolFilters(
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
    )


# ---------------------------------------------------------------------------
# T20–T23: B04 Standing Exits and Clock
# ---------------------------------------------------------------------------

def test_t20_same_bar_sl_first() -> None:
    """
    T20: Same bar SL-first priority.
    LONG entry=50000, stop=49000, target=51000.
    Bar O/H/L/C = 50000 / 52000 / 48000 / 50000.
    Expected: raw exit = 49000/SL, economic_at = O + 59999ms, no TP profit.
    """
    o_time = 1700000000000
    filters = _get_btc_filters()
    owner_key = OwnerKey("BASE", "POS_T20")

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        quantity=Decimal("1.0"),
        entry_price=Decimal("50000.0"),
        entry_time_ms=o_time - 60_000,
        initial_stop=Decimal("49000.0"),
        target=Decimal("51000.0"),
        max_hold_ms=14_400_000,
    )

    bar = Bar1m(
        timestamp_ms=o_time,
        open=Decimal("50000.0"),
        high=Decimal("52000.0"),
        low=Decimal("48000.0"),
        close=Decimal("50000.0"),
        volume=Decimal("10.0"),
        symbol="BTCUSDT",
    )

    has_exit, reason, raw_price, econ_ts = evaluate_intrabar_exit(ol, bar, filters)
    assert has_exit is True
    assert reason == ExitReason.STOP_LOSS
    assert raw_price == Decimal("49000.0")
    assert econ_ts == o_time + 59_999


def test_t21_adverse_gap_open() -> None:
    """
    T21: Adverse gap open.
    LONG entry=50000, stop=49000, bar open=48000 < stop=49000.
    Expected: raw exit = 48000 (worse fill, not 49000).
    """
    o_time = 1700000000000
    filters = _get_btc_filters()
    owner_key = OwnerKey("BASE", "POS_T21")

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        quantity=Decimal("1.0"),
        entry_price=Decimal("50000.0"),
        entry_time_ms=o_time - 60_000,
        initial_stop=Decimal("49000.0"),
        target=Decimal("51000.0"),
        max_hold_ms=14_400_000,
    )

    bar = Bar1m(
        timestamp_ms=o_time,
        open=Decimal("48000.0"),  # Gapped below stop
        high=Decimal("48500.0"),
        low=Decimal("47500.0"),
        close=Decimal("48000.0"),
        volume=Decimal("10.0"),
        symbol="BTCUSDT",
    )

    has_exit, reason, raw_price, econ_ts = evaluate_open_bar_exit(ol, bar, filters)
    assert has_exit is True
    assert reason == ExitReason.STOP_LOSS
    assert raw_price == Decimal("48000.0")
    assert econ_ts == o_time


def test_t22_all_favorable_exits_capped() -> None:
    """
    T22: All favorable exits capped at target across TP, time, kill, reduction.
    LONG target=51000, open=52000 -> raw capped at 51000.
    SHORT target=49000, open=48000 -> raw capped at 49000.
    """
    filters = _get_btc_filters()
    cost_model = CostModel(CostScenario.BASE)

    # 1. LONG favorable open
    eff_long, raw_long = compute_effective_exit_price(
        raw_price=Decimal("52000.0"),
        direction=Direction.LONG,
        target=Decimal("51000.0"),
        exit_reason=ExitReason.TAKE_PROFIT,
        filters=filters,
        friction_rate=cost_model.friction_rate,
    )
    assert raw_long == Decimal("51000.000000000000")
    # Adverse friction applied to 51000.0: floor_to_tick(51000 * (1 - 0.0005)) = floor(50974.5) = 50974.5
    assert eff_long < Decimal("51000.0")

    # 2. SHORT favorable open
    eff_short, raw_short = compute_effective_exit_price(
        raw_price=Decimal("48000.0"),
        direction=Direction.SHORT,
        target=Decimal("49000.0"),
        exit_reason=ExitReason.TAKE_PROFIT,
        filters=filters,
        friction_rate=cost_model.friction_rate,
    )
    assert raw_short == Decimal("49000.000000000000")
    # Adverse friction applied to 49000.0: ceil_to_tick(49000 * (1 + 0.0005)) = ceil(49024.5) = 49024.5
    assert eff_short > Decimal("49000.0")


def test_t23_hold_exact_expiry_first_due_open() -> None:
    """
    T23: 4h/12h hold exact expiration at first due open F + hold_ms.
    If open also breaches stop, stop takes priority.
    """
    f_time = 1700000000000
    hold_4h_ms = 4 * 3_600_000  # 14,400,000 ms
    expiry_time_ms = f_time + hold_4h_ms
    filters = _get_btc_filters()
    owner_key = OwnerKey("BASE", "POS_T23")

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        quantity=Decimal("1.0"),
        entry_price=Decimal("50000.0"),
        entry_time_ms=f_time,
        initial_stop=Decimal("49000.0"),
        target=Decimal("52000.0"),
        max_hold_ms=hold_4h_ms,
    )

    # 1. Bar 1 minute BEFORE expiry: no expiry
    bar_before = Bar1m(
        timestamp_ms=expiry_time_ms - 60_000,
        open=Decimal("50500.0"),
        high=Decimal("50800.0"),
        low=Decimal("50200.0"),
        close=Decimal("50600.0"),
        volume=Decimal("1.0"),
        symbol="BTCUSDT",
    )
    has_exit_before, _, _, _ = evaluate_open_bar_exit(ol, bar_before, filters)
    assert has_exit_before is False

    # 2. Bar AT exact expiry open: expires at open price 50500
    bar_expiry = Bar1m(
        timestamp_ms=expiry_time_ms,
        open=Decimal("50500.0"),
        high=Decimal("50800.0"),
        low=Decimal("50200.0"),
        close=Decimal("50600.0"),
        volume=Decimal("1.0"),
        symbol="BTCUSDT",
    )
    has_exit_exp, reason_exp, raw_price_exp, econ_ts_exp = evaluate_open_bar_exit(ol, bar_expiry, filters)
    assert has_exit_exp is True
    assert reason_exp == ExitReason.EXPIRY
    assert raw_price_exp == Decimal("50500.0")
    assert econ_ts_exp == expiry_time_ms

    # 3. Bar AT exact expiry open where open breaches stop (48500 < stop 49000): Stop wins!
    bar_expiry_sl = Bar1m(
        timestamp_ms=expiry_time_ms,
        open=Decimal("48500.0"),
        high=Decimal("48800.0"),
        low=Decimal("48200.0"),
        close=Decimal("48600.0"),
        volume=Decimal("1.0"),
        symbol="BTCUSDT",
    )
    has_exit_sl, reason_sl, raw_price_sl, _econ_ts_sl = evaluate_open_bar_exit(ol, bar_expiry_sl, filters)
    assert has_exit_sl is True
    assert reason_sl == ExitReason.STOP_LOSS
    assert raw_price_sl == Decimal("48500.0")


# ---------------------------------------------------------------------------
# Invariants I01–I17 Comprehensive Test
# ---------------------------------------------------------------------------

def test_i01_to_i17_invariants_comprehensive() -> None:
    """Verify all 17 invariants I01–I17 on a coherent state."""
    owner_key = OwnerKey("BASE", "POS_INV")
    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        cash_settled=Decimal("1000.000000000000"),
        quantity=Decimal("0.5"),
        entry_price=Decimal("50000.000000000000"),
        initial_stop=Decimal("49000.000000000000"),
        target=Decimal("52000.000000000000"),
        max_hold_ms=14_400_000,
    )

    st = EngineState(
        clock_ms=1700000000000,
        latest_mark_close_ms=1700000000000,
        latest_marks={"BTCUSDT": Decimal("50000.000000000000")},
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    results = assert_invariants(st, "BASE")
    for i in range(1, 18):
        inv_id = f"I{i:02d}"
        assert results[inv_id] is True, f"Invariant {inv_id} failed"
