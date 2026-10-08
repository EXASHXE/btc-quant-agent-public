"""Independent PIT Bar Aggregation, Clock Availability, Signal & Stress-Geometry Oracle."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from scripts.strategy_research.r3_verification.oracle_specs import (
    ALLOWLISTED_SYMBOLS,
    ARCHIVAL_AVAILABILITY_LAG_MS,
    BPS_DENOMINATOR,
    CANDIDATE_REGISTRY_IDS,
    COOLDOWN_DURATION_MS,
    EARLIEST_ENTRY_LAG_FROM_BAR_END_MS,
    FOUR_HOURS_MS,
    MAX_ENTRY_GAP_ATR_FRACTION,
    MAX_RISK_BPS,
    MIN_RISK_BPS,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
    REQUIRED_SOURCE_DATA_GRADE,
    STRESS_COST_SCENARIO,
    TARGET_RISK_MULTIPLE,
    CostScenario,
    decimal_context,
    round_execution_price,
    round_stop_toward_entry,
    round_target_toward_entry,
)


@dataclass(frozen=True)
class Bar1m:
    """Canonical 1-minute bar with explicit event and archival reconstructed availability clocks."""

    symbol: str
    open_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    available_at_ms: int | None = None
    source_grade: str = REQUIRED_SOURCE_DATA_GRADE

    @property
    def end_ms_exclusive(self) -> int:
        return self.open_ms + ONE_MINUTE_MS

    @property
    def close_ms_inclusive(self) -> int:
        return self.end_ms_exclusive - 1

    @property
    def effective_available_at_ms(self) -> int:
        if self.available_at_ms is not None:
            return self.available_at_ms
        return self.end_ms_exclusive + ARCHIVAL_AVAILABILITY_LAG_MS

    def validate(self) -> list[str]:
        """Return list of integrity errors for this 1m bar (empty if valid)."""
        errors: list[str] = []
        if self.symbol not in ALLOWLISTED_SYMBOLS:
            errors.append(f"UNALLOWLISTED_SYMBOL:{self.symbol}")
        if self.open_ms % ONE_MINUTE_MS != 0:
            errors.append(f"UNALIGNED_1M_OPEN:{self.open_ms}")
        if self.source_grade != REQUIRED_SOURCE_DATA_GRADE:
            errors.append(f"INVALID_SOURCE_GRADE:{self.source_grade}")
        if self.effective_available_at_ms < self.end_ms_exclusive + ARCHIVAL_AVAILABILITY_LAG_MS:
            errors.append(
                f"PREMATURE_BAR_AVAILABILITY:{self.effective_available_at_ms}"
                f"<{self.end_ms_exclusive + ARCHIVAL_AVAILABILITY_LAG_MS}"
            )
        with decimal_context():
            if min(self.open, self.high, self.low, self.close) <= Decimal(0):
                errors.append("NON_POSITIVE_OHLC_PRICE")
            if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
                errors.append("INVALID_OHLC_ENVELOPE")
            if self.low > self.high:
                errors.append("LOW_GREATER_THAN_HIGH")
            if self.volume < Decimal(0):
                errors.append("NEGATIVE_VOLUME")
        return errors


@dataclass(frozen=True)
class HigherTimeframeBar:
    """Epoch-aligned completed 1h or 4h bar aggregated strictly from completed 1m bars."""

    symbol: str
    timeframe_ms: int
    open_ms: int
    end_ms_exclusive: int
    available_at_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    constituent_count: int


@dataclass(frozen=True)
class AggregationAudit:
    """Result of PIT-safe bar aggregation at a specific decision_at_ms clock."""

    completed_bars: tuple[HigherTimeframeBar, ...]
    dropped_unfinished_buckets: tuple[int, ...]
    invalid_incomplete_buckets: tuple[int, ...]
    validation_errors: tuple[str, ...]


def aggregate_completed_bars(
    bars_1m: Sequence[Bar1m],
    *,
    timeframe_ms: int,
    decision_at_ms: int,
) -> AggregationAudit:
    """Aggregate epoch-aligned 1h or 4h bars visible at `decision_at_ms`.

    Rules enforced:
    1. Only 1m bars with `effective_available_at_ms <= decision_at_ms` are visible.
    2. A bucket `[B, B + timeframe_ms)` is unfinished if `B + timeframe_ms + 60_000 > decision_at_ms`
       and is dropped as an unfinished bar (never included in indicator lookbacks).
    3. A past bucket whose `B + timeframe_ms + 60_000 <= decision_at_ms` must have all
       `timeframe_ms // 60_000` constituent 1m bars present and valid; otherwise it is recorded
       in `invalid_incomplete_buckets` and `validation_errors`.
    """
    if timeframe_ms not in (ONE_HOUR_MS, FOUR_HOURS_MS):
        raise ValueError(f"Unsupported timeframe_ms={timeframe_ms}; expected 1h or 4h")
    expected_count = timeframe_ms // ONE_MINUTE_MS

    errors: list[str] = []
    seen_opens: set[int] = set()
    visible_by_bucket: dict[int, list[Bar1m]] = {}
    all_buckets_seen: set[int] = set()

    for bar in bars_1m:
        bar_errors = bar.validate()
        if bar_errors:
            errors.extend(bar_errors)
            continue
        if bar.open_ms in seen_opens:
            errors.append(f"DUPLICATE_1M_BAR:{bar.symbol}:{bar.open_ms}")
            continue
        seen_opens.add(bar.open_ms)

        bucket_open = (bar.open_ms // timeframe_ms) * timeframe_ms
        all_buckets_seen.add(bucket_open)

        if bar.effective_available_at_ms <= decision_at_ms:
            visible_by_bucket.setdefault(bucket_open, []).append(bar)

    completed: list[HigherTimeframeBar] = []
    dropped_unfinished: list[int] = []
    invalid_incomplete: list[int] = []

    for bucket_open in sorted(all_buckets_seen):
        bucket_end = bucket_open + timeframe_ms
        bucket_min_available = bucket_end + ARCHIVAL_AVAILABILITY_LAG_MS
        if decision_at_ms < bucket_min_available:
            dropped_unfinished.append(bucket_open)
            continue

        constituents = sorted(
            visible_by_bucket.get(bucket_open, []), key=lambda b: b.open_ms
        )
        if len(constituents) != expected_count:
            invalid_incomplete.append(bucket_open)
            errors.append(
                f"INCOMPLETE_BUCKET:{bucket_open}:got={len(constituents)}:expected={expected_count}"
            )
            continue

        # Verify contiguous 1m grid inside bucket
        expected_opens = [bucket_open + i * ONE_MINUTE_MS for i in range(expected_count)]
        actual_opens = [b.open_ms for b in constituents]
        if actual_opens != expected_opens:
            invalid_incomplete.append(bucket_open)
            errors.append(f"NON_CONTIGUOUS_BUCKET:{bucket_open}")
            continue

        with decimal_context():
            htf_open = constituents[0].open
            htf_close = constituents[-1].close
            htf_high = max(b.high for b in constituents)
            htf_low = min(b.low for b in constituents)
            htf_vol = sum((b.volume for b in constituents), Decimal(0))
            htf_avail = max(b.effective_available_at_ms for b in constituents)

        completed.append(
            HigherTimeframeBar(
                symbol=constituents[0].symbol,
                timeframe_ms=timeframe_ms,
                open_ms=bucket_open,
                end_ms_exclusive=bucket_end,
                available_at_ms=htf_avail,
                open=htf_open,
                high=htf_high,
                low=htf_low,
                close=htf_close,
                volume=htf_vol,
                constituent_count=expected_count,
            )
        )

    return AggregationAudit(
        completed_bars=tuple(completed),
        dropped_unfinished_buckets=tuple(dropped_unfinished),
        invalid_incomplete_buckets=tuple(invalid_incomplete),
        validation_errors=tuple(errors),
    )


def compute_atr20(bars: Sequence[HigherTimeframeBar]) -> Decimal | None:
    """Compute arithmetic mean of 20 completed true ranges using prior bar closes."""
    if len(bars) < 21:
        return None
    with decimal_context():
        recent = bars[-21:]
        trs: list[Decimal] = []
        for idx in range(1, 21):
            curr = recent[idx]
            prev_close = recent[idx - 1].close
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev_close),
                abs(curr.low - prev_close),
            )
            trs.append(tr)
        return sum(trs, Decimal(0)) / Decimal(20)


def compute_ema_series(
    closes: Sequence[Decimal],
    period: int,
    *,
    min_completed_bars: int = 60,
) -> tuple[Decimal, ...] | None:
    """Compute EMA series seeded by SMA of first `period` bars, requiring `min_completed_bars`."""
    if period <= 0 or len(closes) < max(period, min_completed_bars):
        return None
    with decimal_context():
        alpha = Decimal(2) / Decimal(period + 1)
        one_minus_alpha = Decimal(1) - alpha
        seed_sma = sum(closes[:period], Decimal(0)) / Decimal(period)
        ema_values: list[Decimal] = [seed_sma]
        current_ema = seed_sma
        for price in closes[period:]:
            current_ema = alpha * price + one_minus_alpha * current_ema
            ema_values.append(current_ema)
        return tuple(ema_values)


def compute_er12(closes: Sequence[Decimal]) -> Decimal | None:
    """Compute 12-bar Efficiency Ratio; returns None if fewer than 13 bars or zero denominator."""
    if len(closes) < 13:
        return None
    with decimal_context():
        window = closes[-13:]
        net_disp = abs(window[-1] - window[0])
        sum_step = sum(
            (abs(window[i] - window[i - 1]) for i in range(1, 13)),
            Decimal(0),
        )
        if sum_step == Decimal(0):
            return None
        return net_disp / sum_step


@dataclass(frozen=True)
class StressGeometryResult:
    """Result of pre-entry stress cost geometry check."""

    candidate_id: str
    eligible: bool
    status: str
    claim_class: str
    required_min_stop_bps: Decimal
    required_min_target_bps: Decimal
    actual_stop_bps: Decimal
    actual_target_bps: Decimal
    stress_cost_bps_cs: Decimal
    settlement_events_in_hold: int
    registry_preserved: bool


def evaluate_stress_cost_geometry(
    *,
    candidate_id: str,
    max_holding_hours: int,
    actual_stop_bps: Decimal,
    settlement_events_in_hold: int | None = None,
    tick_rounding_bound_bps: Decimal = Decimal(0),
    cost_scenario: CostScenario = STRESS_COST_SCENARIO,
) -> StressGeometryResult:
    """Verify stress cost geometry (`stop >= 2*C_s`, `target >= 3*C_s`, `30 <= stop <= 250` bps).

    When funding schedule is unverified, each hour in `max_holding_hours` is a potential
    settlement event (`settlement_events_in_hold = max_holding_hours`). For 12h candidates,
    `C_s = 44 + 12 * 8 = 140` bps, requiring `stop >= 280` bps > `250` bps max stop.
    This must return `STRESS_COST_GEOMETRY_INELIGIBLE` and `NEGATIVE_UNDERPOWERED_DIAGNOSTIC`
    while keeping `candidate_id` in `CANDIDATE_REGISTRY_IDS`.
    """
    if candidate_id not in CANDIDATE_REGISTRY_IDS:
        raise ValueError(f"Unknown candidate_id={candidate_id}")

    events = max_holding_hours if settlement_events_in_hold is None else settlement_events_in_hold
    with decimal_context():
        cs_bps = (
            cost_scenario.round_trip_one_time_bps
            + cost_scenario.funding_proxy_bps_per_event * Decimal(events)
            + tick_rounding_bound_bps
        )
        req_stop_bps = Decimal(2) * cs_bps
        req_target_bps = Decimal(3) * cs_bps
        actual_target_bps = TARGET_RISK_MULTIPLE * actual_stop_bps

        if req_stop_bps > MAX_RISK_BPS:
            return StressGeometryResult(
                candidate_id=candidate_id,
                eligible=False,
                status="STRESS_COST_GEOMETRY_INELIGIBLE",
                claim_class="NEGATIVE_UNDERPOWERED_DIAGNOSTIC",
                required_min_stop_bps=req_stop_bps,
                required_min_target_bps=req_target_bps,
                actual_stop_bps=actual_stop_bps,
                actual_target_bps=actual_target_bps,
                stress_cost_bps_cs=cs_bps,
                settlement_events_in_hold=events,
                registry_preserved=True,
            )

        if actual_stop_bps < MIN_RISK_BPS or actual_stop_bps > MAX_RISK_BPS:
            return StressGeometryResult(
                candidate_id=candidate_id,
                eligible=False,
                status="WAIT_RISK_BOUNDS_30_250_BPS",
                claim_class="NEGATIVE_UNDERPOWERED_DIAGNOSTIC",
                required_min_stop_bps=req_stop_bps,
                required_min_target_bps=req_target_bps,
                actual_stop_bps=actual_stop_bps,
                actual_target_bps=actual_target_bps,
                stress_cost_bps_cs=cs_bps,
                settlement_events_in_hold=events,
                registry_preserved=True,
            )

        if actual_stop_bps < req_stop_bps or actual_target_bps < req_target_bps:
            return StressGeometryResult(
                candidate_id=candidate_id,
                eligible=False,
                status="WAIT_STRESS_GEOMETRY_HURDLE",
                claim_class="NEGATIVE_UNDERPOWERED_DIAGNOSTIC",
                required_min_stop_bps=req_stop_bps,
                required_min_target_bps=req_target_bps,
                actual_stop_bps=actual_stop_bps,
                actual_target_bps=actual_target_bps,
                stress_cost_bps_cs=cs_bps,
                settlement_events_in_hold=events,
                registry_preserved=True,
            )

        return StressGeometryResult(
            candidate_id=candidate_id,
            eligible=True,
            status="ELIGIBLE",
            claim_class="DIAGNOSTIC_CANDIDATE_EVALUABLE",
            required_min_stop_bps=req_stop_bps,
            required_min_target_bps=req_target_bps,
            actual_stop_bps=actual_stop_bps,
            actual_target_bps=actual_target_bps,
            stress_cost_bps_cs=cs_bps,
            settlement_events_in_hold=events,
            registry_preserved=True,
        )


@dataclass(frozen=True)
class SignalDecisionResult:
    """Outcome of hourly signal + next-minute entry gate verification."""

    candidate_id: str
    symbol: str
    direction: int
    decision_at_ms: int
    earliest_entry_open_ms: int
    action: str  # "ENTER" or "WAIT"
    reason: str
    decision_close: Decimal | None = None
    hourly_atr20: Decimal | None = None
    effective_entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    initial_risk_bps: Decimal | None = None
    retest_event_id: str | None = None


def evaluate_structural_continuation_candidate(
    *,
    candidate_id: str,
    symbol: str,
    direction: int,
    max_holding_hours: int,
    decision_at_ms: int,
    completed_1h_bars: Sequence[HigherTimeframeBar],
    completed_4h_bars: Sequence[HigherTimeframeBar],
    entry_minute_bar: Bar1m | None,
    tick_size: Decimal,
    cost_scenario: CostScenario = STRESS_COST_SCENARIO,
    last_exit_ms: int | None = None,
    last_entry_4h_bar_open_ms: int | None = None,
    settlement_events_in_hold: int | None = None,
) -> SignalDecisionResult:
    """Independently verify `STRUCTURAL_CONTINUATION` signal and entry admissibility."""
    if not completed_1h_bars:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=decision_at_ms + ONE_MINUTE_MS,
            action="WAIT",
            reason="INSUFFICIENT_1H_BARS",
        )

    last_1h = completed_1h_bars[-1]
    expected_decision_ms = last_1h.end_ms_exclusive + ARCHIVAL_AVAILABILITY_LAG_MS
    earliest_entry_ms = last_1h.end_ms_exclusive + EARLIEST_ENTRY_LAG_FROM_BAR_END_MS
    if decision_at_ms != expected_decision_ms:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="INVALID_DECISION_CLOCK_ALIGNMENT",
        )

    # Cooldown check: expires at ceil_to_minute(economic_exit_at) + 4h
    if last_exit_ms is not None:
        ceil_exit_min = ((last_exit_ms + ONE_MINUTE_MS - 1) // ONE_MINUTE_MS) * ONE_MINUTE_MS
        if decision_at_ms < ceil_exit_min + COOLDOWN_DURATION_MS:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="COOLDOWN_ACTIVE",
            )

    if len(completed_4h_bars) < 60 or len(completed_1h_bars) < 21:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="WARMUP_INCOMPLETE",
        )

    last_4h = completed_4h_bars[-1]
    if last_entry_4h_bar_open_ms is not None and last_4h.open_ms <= last_entry_4h_bar_open_ms:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="REQUIRES_NEWER_COMPLETED_4H_BAR",
        )

    with decimal_context():
        closes_4h = [b.close for b in completed_4h_bars]
        ema20_series = compute_ema_series(closes_4h, 20, min_completed_bars=60)
        ema50_series = compute_ema_series(closes_4h, 50, min_completed_bars=60)
        er12 = compute_er12(closes_4h)
        atr20_4h = compute_atr20(completed_4h_bars)
        atr20_1h = compute_atr20(completed_1h_bars)

        if (
            ema20_series is None
            or ema50_series is None
            or er12 is None
            or atr20_4h is None
            or atr20_1h is None
        ):
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="INDICATOR_INELIGIBLE",
            )

        ema20_now = ema20_series[-1]
        ema20_prev3 = ema20_series[-4]
        ema50_now = ema50_series[-1]
        c4h = last_4h.close

        if direction == 1:
            structure_ok = c4h > ema20_now > ema50_now and ema20_now > ema20_prev3
        else:
            structure_ok = c4h < ema20_now < ema50_now and ema20_now < ema20_prev3

        if not structure_ok or er12 < Decimal("0.35"):
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="4H_STRUCTURE_OR_ER12_REJECTED",
            )

        if abs(c4h - ema20_now) > atr20_4h:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="4H_EMA20_EXTENSION_EXCEEDED",
            )

        prior_3_1h = completed_1h_bars[-4:-1]
        if direction == 1:
            breakout_ok = last_1h.close > max(b.high for b in prior_3_1h)
        else:
            breakout_ok = last_1h.close < min(b.low for b in prior_3_1h)

        signed_body = Decimal(direction) * (last_1h.close - last_1h.open)
        bar_range = last_1h.high - last_1h.low
        if (
            not breakout_ok
            or signed_body < Decimal("0.5") * atr20_1h
            or bar_range > Decimal("2.0") * atr20_1h
        ):
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="1H_BREAKOUT_OR_BODY_RANGE_REJECTED",
            )

        decision_risk_bps = (atr20_1h / last_1h.close) * BPS_DENOMINATOR
        if decision_risk_bps < MIN_RISK_BPS or decision_risk_bps > MAX_RISK_BPS:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="DECISION_ATR_BPS_OUT_OF_RANGE",
                decision_close=last_1h.close,
                hourly_atr20=atr20_1h,
            )

        raw_stop = last_1h.close - Decimal(direction) * Decimal("1.5") * atr20_1h
        return _finalize_next_minute_entry_check(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            max_holding_hours=max_holding_hours,
            decision_at_ms=decision_at_ms,
            earliest_entry_ms=earliest_entry_ms,
            decision_close=last_1h.close,
            atr20_1h=atr20_1h,
            raw_stop=raw_stop,
            entry_minute_bar=entry_minute_bar,
            tick_size=tick_size,
            cost_scenario=cost_scenario,
            settlement_events_in_hold=settlement_events_in_hold,
            retest_event_id=None,
        )


@dataclass(frozen=True)
class ClosedRetestEvent:
    """Frozen breakout state for CLOSED_RETEST family."""

    symbol: str
    direction: int
    breakout_hour_open_ms: int
    frozen_boundary: Decimal
    frozen_atr20: Decimal

    @property
    def event_id(self) -> str:
        side = "LONG" if self.direction == 1 else "SHORT"
        return f"{self.symbol}/{side}/{self.breakout_hour_open_ms}"


def evaluate_closed_retest_candidate(
    *,
    candidate_id: str,
    symbol: str,
    direction: int,
    max_holding_hours: int,
    decision_at_ms: int,
    completed_1h_bars: Sequence[HigherTimeframeBar],
    completed_4h_bars: Sequence[HigherTimeframeBar],
    entry_minute_bar: Bar1m | None,
    tick_size: Decimal,
    consumed_retest_event_ids: frozenset[str] = frozenset(),
    cost_scenario: CostScenario = STRESS_COST_SCENARIO,
    last_exit_ms: int | None = None,
    settlement_events_in_hold: int | None = None,
) -> SignalDecisionResult:
    """Independently verify `CLOSED_RETEST` signal, event uniqueness, and entry admissibility."""
    if not completed_1h_bars:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=decision_at_ms + ONE_MINUTE_MS,
            action="WAIT",
            reason="INSUFFICIENT_1H_BARS",
        )

    last_1h = completed_1h_bars[-1]
    expected_decision_ms = last_1h.end_ms_exclusive + ARCHIVAL_AVAILABILITY_LAG_MS
    earliest_entry_ms = last_1h.end_ms_exclusive + EARLIEST_ENTRY_LAG_FROM_BAR_END_MS
    if decision_at_ms != expected_decision_ms:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="INVALID_DECISION_CLOCK_ALIGNMENT",
        )

    if last_exit_ms is not None:
        ceil_exit_min = ((last_exit_ms + ONE_MINUTE_MS - 1) // ONE_MINUTE_MS) * ONE_MINUTE_MS
        if decision_at_ms < ceil_exit_min + COOLDOWN_DURATION_MS:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="COOLDOWN_ACTIVE",
            )

    if len(completed_4h_bars) < 60 or len(completed_1h_bars) < 28:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="WARMUP_INCOMPLETE",
        )

    with decimal_context():
        closes_4h = [b.close for b in completed_4h_bars]
        ema20_series = compute_ema_series(closes_4h, 20, min_completed_bars=60)
        ema50_series = compute_ema_series(closes_4h, 50, min_completed_bars=60)
        atr20_1h_now = compute_atr20(completed_1h_bars)
        if ema20_series is None or ema50_series is None or atr20_1h_now is None:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="INDICATOR_INELIGIBLE",
            )

        c4h = completed_4h_bars[-1].close
        ema20_now = ema20_series[-1]
        ema50_now = ema50_series[-1]
        if direction == 1 and not (c4h > ema20_now > ema50_now):
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="4H_EMA_ORDERING_REJECTED",
            )
        if direction == -1 and not (c4h < ema20_now < ema50_now):
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="4H_EMA_ORDERING_REJECTED",
            )

        # Check candidate breakout bars k in {1, 2, 3} hours before confirmation bar (last_1h)
        n_bars = len(completed_1h_bars)
        matched_event: ClosedRetestEvent | None = None
        matched_stop: Decimal | None = None

        for offset in (3, 2, 1):
            b_idx = n_bars - 1 - offset
            if b_idx < 24:
                continue
            breakout_bar = completed_1h_bars[b_idx]
            prior_24 = completed_1h_bars[b_idx - 24 : b_idx]
            atr_at_breakout = compute_atr20(completed_1h_bars[: b_idx + 1])
            if atr_at_breakout is None:
                continue

            if direction == 1:
                boundary = max(b.high for b in prior_24)
                broke = breakout_bar.close >= boundary + Decimal("0.25") * atr_at_breakout
            else:
                boundary = min(b.low for b in prior_24)
                broke = breakout_bar.close <= boundary - Decimal("0.25") * atr_at_breakout

            signed_body = Decimal(direction) * (breakout_bar.close - breakout_bar.open)
            if not broke or signed_body < Decimal("0.5") * atr_at_breakout:
                continue

            event = ClosedRetestEvent(
                symbol=symbol,
                direction=direction,
                breakout_hour_open_ms=breakout_bar.open_ms,
                frozen_boundary=boundary,
                frozen_atr20=atr_at_breakout,
            )

            # Check intermediate bars between breakout_bar and last_1h for cancellation or earlier confirmation
            intervening = completed_1h_bars[b_idx + 1 : n_bars - 1]
            cancelled_or_already_confirmed = False
            for ibar in intervening:
                if _is_retest_cancelled(ibar, event) or _is_retest_confirmed(ibar, event):
                    cancelled_or_already_confirmed = True
                    break
            if cancelled_or_already_confirmed:
                continue

            if _is_retest_confirmed(last_1h, event):
                if event.event_id in consumed_retest_event_ids:
                    return SignalDecisionResult(
                        candidate_id=candidate_id,
                        symbol=symbol,
                        direction=direction,
                        decision_at_ms=decision_at_ms,
                        earliest_entry_open_ms=earliest_entry_ms,
                        action="WAIT",
                        reason="RETEST_EVENT_ALREADY_CONSUMED",
                        retest_event_id=event.event_id,
                    )
                span_bars = completed_1h_bars[b_idx:n_bars]
                if direction == 1:
                    matched_stop = (
                        min(b.low for b in span_bars) - Decimal("0.25") * event.frozen_atr20
                    )
                else:
                    matched_stop = (
                        max(b.high for b in span_bars) + Decimal("0.25") * event.frozen_atr20
                    )
                matched_event = event
                break

        if matched_event is None or matched_stop is None:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="NO_CONFIRMED_RETEST",
            )

        decision_risk_bps = (atr20_1h_now / last_1h.close) * BPS_DENOMINATOR
        if decision_risk_bps < MIN_RISK_BPS or decision_risk_bps > MAX_RISK_BPS:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="DECISION_ATR_BPS_OUT_OF_RANGE",
                decision_close=last_1h.close,
                hourly_atr20=atr20_1h_now,
                retest_event_id=matched_event.event_id,
            )

        return _finalize_next_minute_entry_check(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            max_holding_hours=max_holding_hours,
            decision_at_ms=decision_at_ms,
            earliest_entry_ms=earliest_entry_ms,
            decision_close=last_1h.close,
            atr20_1h=atr20_1h_now,
            raw_stop=matched_stop,
            entry_minute_bar=entry_minute_bar,
            tick_size=tick_size,
            cost_scenario=cost_scenario,
            settlement_events_in_hold=settlement_events_in_hold,
            retest_event_id=matched_event.event_id,
        )


def _is_retest_cancelled(bar: HigherTimeframeBar, event: ClosedRetestEvent) -> bool:
    with decimal_context():
        if event.direction == 1:
            return bar.close < event.frozen_boundary - Decimal("0.25") * event.frozen_atr20
        return bar.close > event.frozen_boundary + Decimal("0.25") * event.frozen_atr20


def _is_retest_confirmed(bar: HigherTimeframeBar, event: ClosedRetestEvent) -> bool:
    with decimal_context():
        band_low = event.frozen_boundary - Decimal("0.25") * event.frozen_atr20
        band_high = event.frozen_boundary + Decimal("0.25") * event.frozen_atr20
        if event.direction == 1:
            touched = band_low <= bar.low <= band_high
            recovered = bar.close >= event.frozen_boundary + Decimal("0.10") * event.frozen_atr20
            bullish = bar.close > bar.open
            return touched and recovered and bullish
        touched = band_low <= bar.high <= band_high
        recovered = bar.close <= event.frozen_boundary - Decimal("0.10") * event.frozen_atr20
        bearish = bar.close < bar.open
        return touched and recovered and bearish


def _finalize_next_minute_entry_check(
    *,
    candidate_id: str,
    symbol: str,
    direction: int,
    max_holding_hours: int,
    decision_at_ms: int,
    earliest_entry_ms: int,
    decision_close: Decimal,
    atr20_1h: Decimal,
    raw_stop: Decimal,
    entry_minute_bar: Bar1m | None,
    tick_size: Decimal,
    cost_scenario: CostScenario,
    settlement_events_in_hold: int | None,
    retest_event_id: str | None,
) -> SignalDecisionResult:
    """Verify next-minute open availability, absolute gap <= 0.25 ATR20, stop rounding, and stress geometry."""
    if entry_minute_bar is None:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="MISSING_NEXT_MINUTE_ENTRY_BAR",
            decision_close=decision_close,
            hourly_atr20=atr20_1h,
            retest_event_id=retest_event_id,
        )

    if entry_minute_bar.open_ms < earliest_entry_ms:
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="LOOKAHEAD_ENTRY_BEFORE_EARLIEST_MINUTE_OPEN",
            decision_close=decision_close,
            hourly_atr20=atr20_1h,
            retest_event_id=retest_event_id,
        )

    if entry_minute_bar.volume <= Decimal(0):
        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="WAIT",
            reason="ZERO_VOLUME_ENTRY_BAR_NO_FILL",
            decision_close=decision_close,
            hourly_atr20=atr20_1h,
            retest_event_id=retest_event_id,
        )

    with decimal_context():
        # Both adverse and favorable gaps > 0.25 ATR20 veto entry
        abs_gap = abs(entry_minute_bar.open - decision_close)
        if abs_gap > MAX_ENTRY_GAP_ATR_FRACTION * atr20_1h:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="ENTRY_OPEN_GAP_EXCEEDS_0_25_ATR",
                decision_close=decision_close,
                hourly_atr20=atr20_1h,
                retest_event_id=retest_event_id,
            )

        eff_entry = round_execution_price(
            entry_minute_bar.open,
            is_buy=(direction == 1),
            cost_scenario=cost_scenario,
            tick_size=tick_size,
        )
        rounded_stop = round_stop_toward_entry(raw_stop, direction=direction, tick_size=tick_size)
        signed_risk_dist = Decimal(direction) * (eff_entry - rounded_stop)
        if signed_risk_dist <= Decimal(0):
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason="NON_POSITIVE_ROUNDED_STOP_RISK",
                decision_close=decision_close,
                hourly_atr20=atr20_1h,
                effective_entry_price=eff_entry,
                stop_price=rounded_stop,
                retest_event_id=retest_event_id,
            )

        raw_target = eff_entry + Decimal(direction) * TARGET_RISK_MULTIPLE * signed_risk_dist
        rounded_target = round_target_toward_entry(
            raw_target, direction=direction, tick_size=tick_size
        )

        risk_bps = (signed_risk_dist / eff_entry) * BPS_DENOMINATOR
        geom = evaluate_stress_cost_geometry(
            candidate_id=candidate_id,
            max_holding_hours=max_holding_hours,
            actual_stop_bps=risk_bps,
            settlement_events_in_hold=settlement_events_in_hold,
            cost_scenario=cost_scenario,
        )
        if not geom.eligible:
            return SignalDecisionResult(
                candidate_id=candidate_id,
                symbol=symbol,
                direction=direction,
                decision_at_ms=decision_at_ms,
                earliest_entry_open_ms=earliest_entry_ms,
                action="WAIT",
                reason=geom.status,
                decision_close=decision_close,
                hourly_atr20=atr20_1h,
                effective_entry_price=eff_entry,
                stop_price=rounded_stop,
                target_price=rounded_target,
                initial_risk_bps=risk_bps,
                retest_event_id=retest_event_id,
            )

        return SignalDecisionResult(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            decision_at_ms=decision_at_ms,
            earliest_entry_open_ms=earliest_entry_ms,
            action="ENTER",
            reason="ADMISSIBLE_SIGNAL_AND_ENTRY",
            decision_close=decision_close,
            hourly_atr20=atr20_1h,
            effective_entry_price=eff_entry,
            stop_price=rounded_stop,
            target_price=rounded_target,
            initial_risk_bps=risk_bps,
            retest_event_id=retest_event_id,
        )
