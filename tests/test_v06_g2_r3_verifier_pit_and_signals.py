"""Hermetic tests for G2 R3 PIT bar aggregation, clock availability, signals, and stress geometry."""

from __future__ import annotations

from decimal import Decimal

from scripts.strategy_research.r3_verification.oracle_specs import (
    CANDIDATE_REGISTRY_IDS,
    FOUR_HOURS_MS,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
)
from scripts.strategy_research.r3_verification.pit_bar_and_signal_oracle import (
    Bar1m,
    HigherTimeframeBar,
    aggregate_completed_bars,
    compute_atr20,
    compute_ema_series,
    compute_er12,
    evaluate_closed_retest_candidate,
    evaluate_stress_cost_geometry,
    evaluate_structural_continuation_candidate,
)


def _make_1m_bars(
    *,
    symbol: str = "BTCUSDT",
    start_ms: int = 1_767_225_600_000,
    count: int = 120,
    base_price: Decimal = Decimal(50000),
) -> list[Bar1m]:
    bars: list[Bar1m] = []
    for i in range(count):
        p = base_price + Decimal(i)
        bars.append(
            Bar1m(
                symbol=symbol,
                open_ms=start_ms + i * ONE_MINUTE_MS,
                open=p,
                high=p + Decimal(20),
                low=p - Decimal(20),
                close=p + Decimal(5),
                volume=Decimal(10),
            )
        )
    return bars


def test_completed_1m_vs_unfinished_1h_and_4h_bars() -> None:
    """Unfinished 1h/4h bars or bars within the 60s availability lag must never enter lookbacks."""
    start_ms = 1_767_225_600_000  # 2026-01-01T00:00:00Z
    bars_1m = _make_1m_bars(start_ms=start_ms, count=300)  # 5 hours of 1m bars

    # At exactly 01:00:00Z (start_ms + 3600000), the 59th minute [00:59, 01:00) is NOT yet available
    # because its archival availability is 01:01:00Z (start_ms + 3660000).
    at_hour_boundary = aggregate_completed_bars(
        bars_1m,
        timeframe_ms=ONE_HOUR_MS,
        decision_at_ms=start_ms + ONE_HOUR_MS,
    )
    assert len(at_hour_boundary.completed_bars) == 0
    assert start_ms in at_hour_boundary.dropped_unfinished_buckets

    # At 01:01:00Z (start_ms + 3660000), the first 1h bar [00:00, 01:00) is complete & available,
    # while later hours remain unfinished and dropped.
    at_decision_clock = aggregate_completed_bars(
        bars_1m,
        timeframe_ms=ONE_HOUR_MS,
        decision_at_ms=start_ms + ONE_HOUR_MS + ONE_MINUTE_MS,
    )
    assert len(at_decision_clock.completed_bars) == 1
    assert at_decision_clock.completed_bars[0].open_ms == start_ms
    assert at_decision_clock.completed_bars[0].available_at_ms == (
        start_ms + ONE_HOUR_MS + ONE_MINUTE_MS
    )
    assert len(at_decision_clock.dropped_unfinished_buckets) == 4
    assert len(at_decision_clock.invalid_incomplete_buckets) == 0

    # At 04:00:30Z, the 4h bar [00:00, 04:00) is still inside its 60s lag -> 0 completed 4h bars.
    agg_4h_early = aggregate_completed_bars(
        bars_1m,
        timeframe_ms=FOUR_HOURS_MS,
        decision_at_ms=start_ms + FOUR_HOURS_MS + 30_000,
    )
    assert len(agg_4h_early.completed_bars) == 0

    # At 04:01:00Z, the 4h bar [00:00, 04:00) is complete & available, while [04:00, 08:00) is unfinished.
    agg_4h_ready = aggregate_completed_bars(
        bars_1m,
        timeframe_ms=FOUR_HOURS_MS,
        decision_at_ms=start_ms + FOUR_HOURS_MS + ONE_MINUTE_MS,
    )
    assert len(agg_4h_ready.completed_bars) == 1
    assert agg_4h_ready.completed_bars[0].constituent_count == 240
    assert agg_4h_ready.dropped_unfinished_buckets == (start_ms + FOUR_HOURS_MS,)


def test_missing_1m_bar_invalidates_completed_bucket() -> None:
    """Missing even a single 1m bar inside a past 1h bucket must invalidate that bucket."""
    start_ms = 1_767_225_600_000
    bars_1m = _make_1m_bars(start_ms=start_ms, count=120)
    # Remove minute 17 from first hour
    del bars_1m[17]

    audit = aggregate_completed_bars(
        bars_1m,
        timeframe_ms=ONE_HOUR_MS,
        decision_at_ms=start_ms + 2 * ONE_HOUR_MS + ONE_MINUTE_MS,
    )
    assert len(audit.completed_bars) == 1
    assert audit.completed_bars[0].open_ms == start_ms + ONE_HOUR_MS
    assert audit.invalid_incomplete_buckets == (start_ms,)
    assert any("INCOMPLETE_BUCKET" in e for e in audit.validation_errors)


def test_premature_availability_and_invalid_grade_rejected() -> None:
    """1m bars claiming availability < end + 60s or non-archival source grade are rejected."""
    start_ms = 1_767_225_600_000
    bad_bar = Bar1m(
        symbol="BTCUSDT",
        open_ms=start_ms,
        open=Decimal(50000),
        high=Decimal(50100),
        low=Decimal(49900),
        close=Decimal(50050),
        volume=Decimal(10),
        available_at_ms=start_ms + ONE_MINUTE_MS + 10_000,  # Only +10s instead of +60s
        source_grade="LIVE_PIT_CLAIM",
    )
    errs = bad_bar.validate()
    assert any("PREMATURE_BAR_AVAILABILITY" in e for e in errs)
    assert any("INVALID_SOURCE_GRADE" in e for e in errs)


def test_indicators_atr20_ema_and_er12_invariants() -> None:
    """Verify ATR20, 60-bar warmup EMA20/EMA50, and ER12 zero-denominator rejection."""
    start_ms = 1_767_225_600_000
    flat_closes = [Decimal(100) for _ in range(60)]
    assert compute_er12(flat_closes) is None  # Zero denominator ineligible
    assert compute_ema_series(flat_closes[:59], 20, min_completed_bars=60) is None

    ema20 = compute_ema_series(flat_closes, 20, min_completed_bars=60)
    assert ema20 is not None
    assert ema20[-1] == Decimal(100)

    trending_closes = [Decimal(100 + i * 2) for i in range(60)]
    er12_trend = compute_er12(trending_closes)
    assert er12_trend == Decimal(1)

    htf_bars = [
        HigherTimeframeBar(
            symbol="BTCUSDT",
            timeframe_ms=ONE_HOUR_MS,
            open_ms=start_ms + i * ONE_HOUR_MS,
            end_ms_exclusive=start_ms + (i + 1) * ONE_HOUR_MS,
            available_at_ms=start_ms + (i + 1) * ONE_HOUR_MS + ONE_MINUTE_MS,
            open=Decimal(1000),
            high=Decimal(1015),
            low=Decimal(995),
            close=Decimal(1005),
            volume=Decimal(100),
            constituent_count=60,
        )
        for i in range(21)
    ]
    atr = compute_atr20(htf_bars)
    assert atr == Decimal(20)


def test_12h_funding_stress_geometry_ineligible_without_dropping_candidates() -> None:
    """12h candidates under unknown hourly cadence require 280bp >= 250bp max stop -> ineligible, never deleted."""
    assert len(CANDIDATE_REGISTRY_IDS) == 8

    for cid in CANDIDATE_REGISTRY_IDS:
        is_12h = cid.endswith("_12H")
        res = evaluate_stress_cost_geometry(
            candidate_id=cid,
            max_holding_hours=12 if is_12h else 4,
            actual_stop_bps=Decimal(160),
        )
        assert res.registry_preserved is True
        if is_12h:
            # 12 * 8 + 44 = 140bp -> 2 * 140 = 280bp > 250bp max stop
            assert res.stress_cost_bps_cs == Decimal(140)
            assert res.required_min_stop_bps == Decimal(280)
            assert res.eligible is False
            assert res.status == "STRESS_COST_GEOMETRY_INELIGIBLE"
            assert res.claim_class == "NEGATIVE_UNDERPOWERED_DIAGNOSTIC"
        else:
            # 4 * 8 + 44 = 76bp -> 2 * 76 = 152bp <= 160bp <= 250bp
            assert res.stress_cost_bps_cs == Decimal(76)
            assert res.required_min_stop_bps == Decimal(152)
            assert res.eligible is True
            assert res.status == "ELIGIBLE"


def test_structural_continuation_signal_next_minute_entry_and_gates() -> None:
    """Verify STRUCTURAL_CONTINUATION 4h/1h signal, t+120s entry, gap veto, cooldown, and newer 4h bar gate."""
    start_ms = 1_767_225_600_000
    # Build 60 completed 4h bars in steady uptrend where close > EMA20 > EMA50 and |close - EMA20| <= ATR20_4h
    bars_4h: list[HigherTimeframeBar] = []
    for i in range(60):
        c = Decimal(40000) + Decimal(i * 150)
        bars_4h.append(
            HigherTimeframeBar(
                symbol="BTCUSDT",
                timeframe_ms=FOUR_HOURS_MS,
                open_ms=start_ms + i * FOUR_HOURS_MS,
                end_ms_exclusive=start_ms + (i + 1) * FOUR_HOURS_MS,
                available_at_ms=start_ms + (i + 1) * FOUR_HOURS_MS + ONE_MINUTE_MS,
                open=c - Decimal(100),
                high=c + Decimal(1500),
                low=c - Decimal(1500),
                close=c,
                volume=Decimal(500),
                constituent_count=240,
            )
        )

    last_4h_end = bars_4h[-1].end_ms_exclusive
    # Build 21 completed 1h bars ending at last_4h_end with ATR20_1h = 550 (~112bp of 48850)
    # So 1.5 * ATR20 = 825 (~168bp, within [152bp, 250bp] for 4h stress geometry!)
    bars_1h: list[HigherTimeframeBar] = []
    h_start = last_4h_end - 21 * ONE_HOUR_MS
    for j in range(20):
        bars_1h.append(
            HigherTimeframeBar(
                symbol="BTCUSDT",
                timeframe_ms=ONE_HOUR_MS,
                open_ms=h_start + j * ONE_HOUR_MS,
                end_ms_exclusive=h_start + (j + 1) * ONE_HOUR_MS,
                available_at_ms=h_start + (j + 1) * ONE_HOUR_MS + ONE_MINUTE_MS,
                open=Decimal(48500),
                high=Decimal(48800),
                low=Decimal(48250),
                close=Decimal(48500),
                volume=Decimal(100),
                constituent_count=60,
            )
        )
    # 21st 1h bar breaks prior 3 highs (48800), body >= 0.5*550=275, range <= 2*550=1100
    bars_1h.append(
        HigherTimeframeBar(
            symbol="BTCUSDT",
            timeframe_ms=ONE_HOUR_MS,
            open_ms=last_4h_end - ONE_HOUR_MS,
            end_ms_exclusive=last_4h_end,
            available_at_ms=last_4h_end + ONE_MINUTE_MS,
            open=Decimal(48450),
            high=Decimal(48900),
            low=Decimal(48350),
            close=Decimal(48850),
            volume=Decimal(150),
            constituent_count=60,
        )
    )

    decision_at_ms = last_4h_end + ONE_MINUTE_MS
    earliest_entry_ms = last_4h_end + 2 * ONE_MINUTE_MS

    valid_entry_bar = Bar1m(
        symbol="BTCUSDT",
        open_ms=earliest_entry_ms,
        open=Decimal(48860),
        high=Decimal(48950),
        low=Decimal(48800),
        close=Decimal(48900),
        volume=Decimal(12),
    )

    res_ok = evaluate_structural_continuation_candidate(
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=1,
        max_holding_hours=4,
        decision_at_ms=decision_at_ms,
        completed_1h_bars=bars_1h,
        completed_4h_bars=bars_4h,
        entry_minute_bar=valid_entry_bar,
        tick_size=Decimal("0.1"),
    )
    assert res_ok.action == "ENTER"
    assert res_ok.earliest_entry_open_ms == earliest_entry_ms

    # Lookahead entry bar at decision_at_ms (t+60s instead of t+120s) must be vetoed
    lookahead_bar = Bar1m(
        symbol="BTCUSDT",
        open_ms=decision_at_ms,
        open=Decimal(48860),
        high=Decimal(48950),
        low=Decimal(48800),
        close=Decimal(48900),
        volume=Decimal(12),
    )
    res_lookahead = evaluate_structural_continuation_candidate(
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=1,
        max_holding_hours=4,
        decision_at_ms=decision_at_ms,
        completed_1h_bars=bars_1h,
        completed_4h_bars=bars_4h,
        entry_minute_bar=lookahead_bar,
        tick_size=Decimal("0.1"),
    )
    assert res_lookahead.action == "WAIT"
    assert res_lookahead.reason == "LOOKAHEAD_ENTRY_BEFORE_EARLIEST_MINUTE_OPEN"

    # Favorable gap > 0.25 * ATR20 (0.25 * 550 = 137.5) must ALSO veto entry
    favorable_gap_bar = Bar1m(
        symbol="BTCUSDT",
        open_ms=earliest_entry_ms,
        open=Decimal(48650),  # -200 gap from 48850
        high=Decimal(48950),
        low=Decimal(48600),
        close=Decimal(48900),
        volume=Decimal(12),
    )
    res_gap = evaluate_structural_continuation_candidate(
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=1,
        max_holding_hours=4,
        decision_at_ms=decision_at_ms,
        completed_1h_bars=bars_1h,
        completed_4h_bars=bars_4h,
        entry_minute_bar=favorable_gap_bar,
        tick_size=Decimal("0.1"),
    )
    assert res_gap.action == "WAIT"
    assert res_gap.reason == "ENTRY_OPEN_GAP_EXCEEDS_0_25_ATR"

    # Same completed 4h bar as previous entry must wait
    res_same_4h = evaluate_structural_continuation_candidate(
        candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
        symbol="BTCUSDT",
        direction=1,
        max_holding_hours=4,
        decision_at_ms=decision_at_ms,
        completed_1h_bars=bars_1h,
        completed_4h_bars=bars_4h,
        entry_minute_bar=valid_entry_bar,
        tick_size=Decimal("0.1"),
        last_entry_4h_bar_open_ms=bars_4h[-1].open_ms,
    )
    assert res_same_4h.action == "WAIT"
    assert res_same_4h.reason == "REQUIRES_NEWER_COMPLETED_4H_BAR"


def test_closed_retest_confirmation_cancellation_and_single_event_consumption() -> None:
    """Verify CLOSED_RETEST breakout freeze, confirmation within 3 bars, and single use per event ID."""
    start_ms = 1_767_225_600_000
    bars_4h = [
        HigherTimeframeBar(
            symbol="BTCUSDT",
            timeframe_ms=FOUR_HOURS_MS,
            open_ms=start_ms + i * FOUR_HOURS_MS,
            end_ms_exclusive=start_ms + (i + 1) * FOUR_HOURS_MS,
            available_at_ms=start_ms + (i + 1) * FOUR_HOURS_MS + ONE_MINUTE_MS,
            open=Decimal(40000) + Decimal(i * 150),
            high=Decimal(40500) + Decimal(i * 150),
            low=Decimal(39500) + Decimal(i * 150),
            close=Decimal(40100) + Decimal(i * 150),
            volume=Decimal(500),
            constituent_count=240,
        )
        for i in range(60)
    ]
    last_4h_end = bars_4h[-1].end_ms_exclusive
    h_start = last_4h_end - 28 * ONE_HOUR_MS

    # First 26 hourly bars have high=48000, low=47400, close=47700 -> ATR20 = 600
    bars_1h: list[HigherTimeframeBar] = []
    for j in range(26):
        bars_1h.append(
            HigherTimeframeBar(
                symbol="BTCUSDT",
                timeframe_ms=ONE_HOUR_MS,
                open_ms=h_start + j * ONE_HOUR_MS,
                end_ms_exclusive=h_start + (j + 1) * ONE_HOUR_MS,
                available_at_ms=h_start + (j + 1) * ONE_HOUR_MS + ONE_MINUTE_MS,
                open=Decimal(47700),
                high=Decimal(48000),
                low=Decimal(47400),
                close=Decimal(47700),
                volume=Decimal(100),
                constituent_count=60,
            )
        )

    # Bar 26 (index 26): Breakout above boundary=48000 by >=0.25*600=150 and body >=0.5*600=300
    breakout_open_ms = h_start + 26 * ONE_HOUR_MS
    bars_1h.append(
        HigherTimeframeBar(
            symbol="BTCUSDT",
            timeframe_ms=ONE_HOUR_MS,
            open_ms=breakout_open_ms,
            end_ms_exclusive=breakout_open_ms + ONE_HOUR_MS,
            available_at_ms=breakout_open_ms + ONE_HOUR_MS + ONE_MINUTE_MS,
            open=Decimal(47800),
            high=Decimal(48300),
            low=Decimal(47700),
            close=Decimal(48200),
            volume=Decimal(180),
            constituent_count=60,
        )
    )
    # Bar 27 (index 27): Confirmation bar -> low touches [48000-150, 48000+150] = [47850, 48150],
    # close >= 48000 + 0.10*600 = 48060, and close > open.
    confirm_open_ms = h_start + 27 * ONE_HOUR_MS
    bars_1h.append(
        HigherTimeframeBar(
            symbol="BTCUSDT",
            timeframe_ms=ONE_HOUR_MS,
            open_ms=confirm_open_ms,
            end_ms_exclusive=last_4h_end,
            available_at_ms=last_4h_end + ONE_MINUTE_MS,
            open=Decimal(48100),
            high=Decimal(48550),
            low=Decimal(47950),
            close=Decimal(48500),
            volume=Decimal(140),
            constituent_count=60,
        )
    )

    decision_at_ms = last_4h_end + ONE_MINUTE_MS
    earliest_entry_ms = last_4h_end + 2 * ONE_MINUTE_MS
    entry_bar = Bar1m(
        symbol="BTCUSDT",
        open_ms=earliest_entry_ms,
        open=Decimal(48500),
        high=Decimal(48600),
        low=Decimal(48450),
        close=Decimal(48520),
        volume=Decimal(15),
    )

    res = evaluate_closed_retest_candidate(
        candidate_id="CLOSED_RETEST_LONG_04H",
        symbol="BTCUSDT",
        direction=1,
        max_holding_hours=4,
        decision_at_ms=decision_at_ms,
        completed_1h_bars=bars_1h,
        completed_4h_bars=bars_4h,
        entry_minute_bar=entry_bar,
        tick_size=Decimal("0.1"),
    )
    assert res.action == "ENTER"
    expected_event_id = f"BTCUSDT/LONG/{breakout_open_ms}"
    assert res.retest_event_id == expected_event_id

    # Attempting to consume the same retest_event_id again must be rejected
    res_repeat = evaluate_closed_retest_candidate(
        candidate_id="CLOSED_RETEST_LONG_04H",
        symbol="BTCUSDT",
        direction=1,
        max_holding_hours=4,
        decision_at_ms=decision_at_ms,
        completed_1h_bars=bars_1h,
        completed_4h_bars=bars_4h,
        entry_minute_bar=entry_bar,
        tick_size=Decimal("0.1"),
        consumed_retest_event_ids=frozenset({expected_event_id}),
    )
    assert res_repeat.action == "WAIT"
    assert res_repeat.reason == "RETEST_EVENT_ALREADY_CONSUMED"
