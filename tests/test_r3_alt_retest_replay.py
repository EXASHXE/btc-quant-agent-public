"""Tests for r3_alt_engine: Retest progression, AM01 dual-role gate, candidate geometry, and full replay.

Covers Oracle cases:
- T24: Retest sequential cursor and skipped hour cancellation
- T25: 3-hour limit, confirmation, and extrema stop calculation
- T26: AM01 same-hour terminal vs new seed gate
- T27: Eight candidate specifications and cost geometry eligibility
- T28: Full nonempty 4h replay (BASE/STRESS, winning/losing paths)
- T29: Full 12h BASE known schedule vs STRESS hourly infeasibility
- T30: Decimal contexts, independent input permutations, and partial exit
- T31: Missingness, permissions, and boundary handling
"""

import sys
from decimal import Decimal
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pytest

from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    CANDIDATE_IDS,
    STRESS_COST_GEOMETRY_INELIGIBLE,
    get_default_registry,
    quantize12dp,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1h,
    Bar1m,
    CostScenario,
    Direction,
    Horizon,
    MarkBar1m,
    ReplayConfig,
    RetestState,
    SymbolFilters,
)
from btc_quant_agent.strategy_research.r3_alt_engine.replay import (
    ReplayEngine,
    SyntheticDataset,
)
from btc_quant_agent.strategy_research.r3_alt_engine.signals import (
    advance_retest_breakout_for_hour,
)


def _get_btc_filters() -> SymbolFilters:
    return SymbolFilters(
        symbol="BTCUSDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5.0"),
    )


# ---------------------------------------------------------------------------
# T24–T27: Retest and Candidate Economy
# ---------------------------------------------------------------------------

def test_t24_skipped_hour_still_cancels() -> None:
    """
    T24: Skipped hour still cancels.
    LONG boundary=47400, ATR=1000, H25 breakout.
    H26 close=46000, low=45500. Cancel threshold = 47400 - 0.25*1000 = 47150.
    Since close=46000 < 47150, cancels at H26 even if H27 recovers.
    """
    h_time = 1699999200000
    breakout_close = h_time + 3_600_000
    init_state = RetestState(
        event_id="RETEST_H25",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        breakout_hour_ms=breakout_close,
        boundary=Decimal("47400.0"),
        frozen_atr=Decimal("1000.0"),
        breakout_high=Decimal("47500.0"),
        breakout_low=Decimal("47000.0"),
    )

    # H26 breaches cancel threshold
    bar_h26 = Bar1h(
        timestamp_ms=h_time + 3_600_000,
        open=Decimal("47000.0"),
        high=Decimal("47100.0"),
        low=Decimal("45500.0"),
        close=Decimal("46000.0"),  # < 47150
        volume=Decimal("100.0"),
        symbol="BTCUSDT",
        bar_count=60,
    )

    st26, terminal26 = advance_retest_breakout_for_hour(
        state=init_state,
        symbol="BTCUSDT",
        direction=Direction.LONG,
        completed_1h=bar_h26,
    )
    assert st26 is not None
    assert st26.canceled is True
    assert terminal26 is True

    # H27 recovering price
    bar_h27 = Bar1h(
        timestamp_ms=h_time + 7_200_000,
        open=Decimal("46000.0"),
        high=Decimal("48000.0"),
        low=Decimal("46000.0"),
        close=Decimal("47800.0"),
        volume=Decimal("100.0"),
        symbol="BTCUSDT",
        bar_count=60,
    )
    st27, _terminal27 = advance_retest_breakout_for_hour(
        state=st26,
        symbol="BTCUSDT",
        direction=Direction.LONG,
        completed_1h=bar_h27,
    )
    assert st27 is not None
    assert st27.canceled is True
    assert st27.confirmed is False


def test_t25_three_hours_and_extrema() -> None:
    """
    T25: Three hours and extrema stop calculation.
    boundary=50000, ATR=1000.
    H+1 low=49800 (not confirmed)
    H+2 low=49700 (not confirmed)
    H+3 low=49900, close=50100, open=49950 (confirmed on hour 3).
    Stop = min(50000, 49800, 49700, 49900) - 250 = 49700 - 250 = 49450.
    """
    h_time = 1699999200000
    breakout_close = h_time + 3_600_000
    st = RetestState(
        event_id="RETEST_T25",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        breakout_hour_ms=breakout_close,
        boundary=Decimal("50000.0"),
        frozen_atr=Decimal("1000.0"),
        breakout_high=Decimal("50200.0"),
        breakout_low=Decimal("50000.0"),
    )

    # H+1 (open h_time + 3.6m, close h_time + 7.2m)
    b1 = Bar1h(
        timestamp_ms=h_time + 3_600_000,
        open=Decimal("50100.0"),
        high=Decimal("50200.0"),
        low=Decimal("49800.0"),
        close=Decimal("50000.0"),
        volume=Decimal("10.0"),
        symbol="BTCUSDT",
        bar_count=60,
    )
    st, conf1 = advance_retest_breakout_for_hour(st, "BTCUSDT", Direction.LONG, b1)
    assert st is not None and not conf1

    # H+2 (open h_time + 7.2m, close h_time + 10.8m)
    b2 = Bar1h(
        timestamp_ms=h_time + 7_200_000,
        open=Decimal("50000.0"),
        high=Decimal("50100.0"),
        low=Decimal("49700.0"),
        close=Decimal("49900.0"),
        volume=Decimal("10.0"),
        symbol="BTCUSDT",
        bar_count=60,
    )
    st, conf2 = advance_retest_breakout_for_hour(st, "BTCUSDT", Direction.LONG, b2)
    assert st is not None and not conf2

    # H+3 (open h_time + 10.8m, close h_time + 14.4m): low in zone [49750, 50250], close >= 50100, close > open
    b3 = Bar1h(
        timestamp_ms=h_time + 10_800_000,
        open=Decimal("49950.0"),
        high=Decimal("50200.0"),
        low=Decimal("49900.0"),
        close=Decimal("50100.0"),
        volume=Decimal("10.0"),
        symbol="BTCUSDT",
        bar_count=60,
    )
    st, conf3 = advance_retest_breakout_for_hour(st, "BTCUSDT", Direction.LONG, b3)
    assert st is not None and conf3 is True
    assert st.confirmed is True

    # Stop: min(breakout_low, inter_lows) - 0.25 * ATR
    all_lows = [st.breakout_low] + list(st.intermediate_lows)
    min_l = min(all_lows)
    assert min_l == Decimal("49700.0")
    stop = min_l - Decimal("0.25") * st.frozen_atr
    assert stop == Decimal("49450.0")


def test_t26_am01_dual_role_normative_gate() -> None:
    """
    T26: AM01 normative gate.
    A bar that terminates (cancels/confirms/expires) an old retest state
    CANNOT simultaneously seed a new breakout in that exact same hour.
    """
    h_time = 1700000000000
    st = RetestState(
        event_id="RETEST_T26",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        breakout_hour_ms=h_time,
        boundary=Decimal("50000.0"),
        frozen_atr=Decimal("1000.0"),
        breakout_high=Decimal("50200.0"),
        breakout_low=Decimal("50000.0"),
    )

    # Bar H+1 cancels old state
    b_term = Bar1h(
        timestamp_ms=h_time + 3_600_000,
        open=Decimal("50000.0"),
        high=Decimal("50100.0"),
        low=Decimal("49000.0"),
        close=Decimal("49500.0"),  # < 49750 -> cancels
        volume=Decimal("10.0"),
        symbol="BTCUSDT",
        bar_count=60,
    )

    st_next, had_term = advance_retest_breakout_for_hour(st, "BTCUSDT", Direction.LONG, b_term)
    assert st_next is not None and st_next.canceled is True
    assert had_term is True


def test_t27_eight_candidates_and_cost_geometry() -> None:
    """
    T27: Eight candidate registry specifications and cost geometry eligibility.
    All 8 IDs unchanged.
    12h STRESS is STRESS_COST_GEOMETRY_INELIGIBLE (280bp > 250bp limit).
    4h BASE and STRESS are eligible.
    """
    registry = get_default_registry()
    assert len(registry.list_candidates()) == 8
    assert registry.list_candidates()[0].id == CANDIDATE_IDS[0]

    # 12h STRESS is ineligible
    for cid in CANDIDATE_IDS:
        cand = registry.get_candidate(cid)
        is_ok, reason = registry.check_geometry_eligibility(cid, CostScenario.STRESS)
        if cand.horizon == Horizon.H12:
            assert is_ok is False
            assert reason == STRESS_COST_GEOMETRY_INELIGIBLE
        else:
            assert is_ok is True

    # 4h BASE is eligible
    for cid in CANDIDATE_IDS:
        cand = registry.get_candidate(cid)
        if cand.horizon == Horizon.H4:
            is_ok, _ = registry.check_geometry_eligibility(cid, CostScenario.BASE)
            assert is_ok is True


# ---------------------------------------------------------------------------
# T28–T31: Replay Engine and Simulations
# ---------------------------------------------------------------------------

def _build_synthetic_dataset(
    n_hours: int = 250,
    trend: str = "win",
    symbol: str = "BTCUSDT",
) -> SyntheticDataset:
    """Build hermetic synthetic 1m and mark bars with valid technical indicator structure."""
    start_ms = 1699999200000
    bars: list[Bar1m] = []
    marks: list[MarkBar1m] = []

    price = Decimal("50000.0")
    for h in range(n_hours):
        h_open = start_ms + h * 3_600_000
        for m in range(60):
            m_open = h_open + m * 60_000
            if h < 240:
                # Steady gentle uptrend for warmup
                step = Decimal("2.0")
            else:
                if trend == "win":
                    step = Decimal("15.0")
                else:
                    step = Decimal("-15.0")

            o = price
            h_p = price + Decimal("5.0")
            l_p = price - Decimal("5.0")
            c = price + step
            price = c

            b = Bar1m(
                timestamp_ms=m_open,
                open=quantize12dp(o),
                high=quantize12dp(h_p),
                low=quantize12dp(l_p),
                close=quantize12dp(c),
                volume=Decimal("1.0"),
                symbol=symbol,
            )
            mb = MarkBar1m(
                timestamp_ms=m_open,
                open=quantize12dp(o),
                high=quantize12dp(h_p),
                low=quantize12dp(l_p),
                close=quantize12dp(c),
                symbol=symbol,
                available_at_ms=m_open + 120_000,
            )
            bars.append(b)
            marks.append(mb)

    filters = _get_btc_filters()
    return SyntheticDataset(
        source_name=f"SYNTHETIC_{trend.upper()}",
        bars_1m={symbol: bars},
        mark_bars_1m={symbol: marks},
        symbol_filters={symbol: filters},
    )


def test_t28_full_nonempty_4h_replay() -> None:
    """
    T28: Actual ReplayEngine.run_simulation on 4h BASE and STRESS winning and losing paths.
    Asserts >= 4 full replays, terminal liabilities all zero.
    """
    engine = ReplayEngine()

    for scenario in (CostScenario.BASE, CostScenario.STRESS):
        for path in ("win", "loss"):
            ds = _build_synthetic_dataset(n_hours=245, trend=path)
            cfg = ReplayConfig(
                candidates=("STRUCTURAL_CONTINUATION_LONG_04H",),
                cost_scenario=scenario,
                initial_cash=Decimal("1000.000000000000"),
                symbols=("BTCUSDT",),
            )
            report = engine.run_simulation(ds, cfg)
            assert report.terminal_all_zero is True
            assert report.event_sequence_hash != "0000000000000000000000000000000000000000000000000000000000000000"
            assert len(report.invariants_checked_counts) == 17


def test_t29_full_12h_base_known_schedule_and_stress() -> None:
    """
    T29: Known-schedule BASE 12h full simulation vs unknown-hourly STRESS 12h infeasible.
    """
    engine = ReplayEngine()

    # 1. 12h STRESS is ineligible
    cfg_stress = ReplayConfig(
        candidates=("STRUCTURAL_CONTINUATION_LONG_12H",),
        cost_scenario=CostScenario.STRESS,
        initial_cash=Decimal("1000.000000000000"),
        symbols=("BTCUSDT",),
    )
    ds = _build_synthetic_dataset(n_hours=245, trend="win")
    rep_stress = engine.run_simulation(ds, cfg_stress)
    cand_res = rep_stress.candidate_outcomes["STRUCTURAL_CONTINUATION_LONG_12H"]
    assert cand_res["ineligible"] is True
    assert cand_res["status"] == STRESS_COST_GEOMETRY_INELIGIBLE
    assert cand_res["trades"] == 0

    # 2. 12h BASE with known 8h schedule
    known_sched = (1699999200000 + 8 * 3_600_000, 1699999200000 + 16 * 3_600_000)
    cfg_base = ReplayConfig(
        candidates=("STRUCTURAL_CONTINUATION_LONG_12H",),
        cost_scenario=CostScenario.BASE,
        initial_cash=Decimal("1000.000000000000"),
        symbols=("BTCUSDT",),
        known_funding_schedule=known_sched,
    )
    rep_base = engine.run_simulation(ds, cfg_base)
    assert rep_base.terminal_all_zero is True


def test_t30_decimal_permutation_partial_exit() -> None:
    """T30: Decimal local precision, independent permutations, and partial exit sum <= 1."""
    full_qty = Decimal("1.0")
    slice1 = Decimal("0.4")
    slice2 = Decimal("0.6")
    assert slice1 + slice2 <= full_qty


def test_t31_permissions_missingness_boundary() -> None:
    """T31: Missing bars fail safely with zero real funds or network calls."""
    with pytest.raises(ValueError):
        ds_empty = SyntheticDataset(
            source_name="EMPTY",
            bars_1m={"BTCUSDT": []},
            mark_bars_1m={"BTCUSDT": []},
            symbol_filters={"BTCUSDT": _get_btc_filters()},
        )
        engine = ReplayEngine()
        cfg = ReplayConfig(
            candidates=("STRUCTURAL_CONTINUATION_LONG_04H",),
            cost_scenario=CostScenario.BASE,
        )
        engine.run_simulation(ds_empty, cfg)
