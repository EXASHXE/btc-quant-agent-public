"""Signal evaluation engine for Structural Continuation and Closed Retest families."""

from collections.abc import Sequence
from decimal import Decimal

from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    DECISION_AVAILABILITY_LAG_MS,
    FILL_DELAY_FROM_DECISION_MS,
    MAX_RISK_BPS,
    MIN_RISK_BPS,
    compute_atr20_1h,
    compute_atr20_4h,
    compute_ema_series,
    compute_er12_4h,
    quantize12dp,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1h,
    Bar4h,
    CandidateDefinition,
    CandidateFamily,
    Direction,
    RetestState,
    SignalEvent,
)


def advance_retest_breakout_for_hour(
    state: RetestState | None,
    symbol: str,
    direction: Direction,
    completed_1h: Bar1h,
) -> tuple[RetestState | None, bool]:
    """
    Advance retest breakout progression for a newly completed 1h bar.
    Returns (new_retest_state, had_terminal_transition_this_hour).
    Under AM01: If canceled, confirmed, or expired on this bar,
    had_terminal_transition_this_hour is True, preventing new breakout seeding.
    """
    if state is None or state.confirmed or state.canceled or state.expired:
        return state, False

    if completed_1h.close_ms <= state.breakout_hour_ms:
        return state, False
    if completed_1h.close_ms <= state.last_advanced_hour_ms:
        return state, False

    elapsed_hours = (completed_1h.close_ms - state.breakout_hour_ms) // 3_600_000
    new_intermediate_highs = state.intermediate_highs + (completed_1h.high,)
    new_intermediate_lows = state.intermediate_lows + (completed_1h.low,)

    is_canceled = False
    is_confirmed = False
    is_expired = False

    # Check cancellation: close beyond boundary by 0.25 frozen ATR in wrong direction (T24)
    if direction == Direction.LONG:
        cancel_threshold = state.boundary - Decimal("0.25") * state.frozen_atr
        if completed_1h.close < cancel_threshold:
            is_canceled = True
    else:
        cancel_threshold = state.boundary + Decimal("0.25") * state.frozen_atr
        if completed_1h.close > cancel_threshold:
            is_canceled = True

    # 3-hour confirmation window limit (T25)
    if elapsed_hours > 3:
        is_expired = True

    if is_canceled or is_expired:
        updated = RetestState(
            event_id=state.event_id,
            symbol=symbol,
            direction=direction,
            breakout_hour_ms=state.breakout_hour_ms,
            boundary=state.boundary,
            frozen_atr=state.frozen_atr,
            breakout_high=state.breakout_high,
            breakout_low=state.breakout_low,
            bars_since_breakout=elapsed_hours,
            intermediate_highs=new_intermediate_highs,
            intermediate_lows=new_intermediate_lows,
            confirmed=False,
            canceled=is_canceled,
            expired=is_expired,
            last_advanced_hour_ms=completed_1h.close_ms,
            consumed_by=state.consumed_by,
        )
        return updated, True  # Terminal transition occurred

    # Check confirmation within 3 hours
    if direction == Direction.LONG:
        band_lower = state.boundary - Decimal("0.25") * state.frozen_atr
        band_upper = state.boundary + Decimal("0.25") * state.frozen_atr
        touches_zone = (band_lower <= completed_1h.low <= band_upper)
        close_above = completed_1h.close >= state.boundary + Decimal("0.10") * state.frozen_atr
        bullish_bar = completed_1h.close > completed_1h.open

        if touches_zone and close_above and bullish_bar:
            is_confirmed = True
    else:
        band_lower = state.boundary - Decimal("0.25") * state.frozen_atr
        band_upper = state.boundary + Decimal("0.25") * state.frozen_atr
        touches_zone = (band_lower <= completed_1h.high <= band_upper)
        close_below = completed_1h.close <= state.boundary - Decimal("0.10") * state.frozen_atr
        bearish_bar = completed_1h.close < completed_1h.open

        if touches_zone and close_below and bearish_bar:
            is_confirmed = True

    updated = RetestState(
        event_id=state.event_id,
        symbol=symbol,
        direction=direction,
        breakout_hour_ms=state.breakout_hour_ms,
        boundary=state.boundary,
        frozen_atr=state.frozen_atr,
        breakout_high=state.breakout_high,
        breakout_low=state.breakout_low,
        bars_since_breakout=elapsed_hours,
        intermediate_highs=new_intermediate_highs,
        intermediate_lows=new_intermediate_lows,
        confirmed=is_confirmed,
        canceled=False,
        expired=False,
        last_advanced_hour_ms=completed_1h.close_ms,
        consumed_by=state.consumed_by,
    )

    return updated, is_confirmed


def evaluate_hourly_signal(
    candidate: CandidateDefinition,
    symbol: str,
    bars_1h: Sequence[Bar1h],
    bars_4h: Sequence[Bar4h],
    retest_state: RetestState | None,
    consumed_retest_events: frozenset[str],
    last_exit_time_ms: int | None = None,
    last_entry_4h_time_ms: int | None = None,
) -> tuple[SignalEvent | None, RetestState | None]:
    """
    Evaluate candidate strategy predicates at exclusive close of latest completed 1h bar.
    Adheres to AM01:
    - Retest cursor progression
    - First valid confirmation consumed once per variant
    - No new breakout seeding in the same hour as terminal transition (AM01, T26)
    """
    if len(bars_1h) < 25:
        return None, retest_state
    if len(bars_4h) < 60:
        return None, retest_state

    current_1h = bars_1h[-1]
    decision_time_ms = current_1h.close_ms
    available_at_ms = decision_time_ms + DECISION_AVAILABILITY_LAG_MS
    earliest_entry_ms = decision_time_ms + DECISION_AVAILABILITY_LAG_MS + FILL_DELAY_FROM_DECISION_MS

    # Advance active breakout state progression for completed hour
    curr_retest = retest_state
    had_terminal_this_hour = False
    if candidate.family == CandidateFamily.CLOSED_RETEST:
        curr_retest, had_terminal_this_hour = advance_retest_breakout_for_hour(
            state=curr_retest,
            symbol=symbol,
            direction=candidate.direction,
            completed_1h=current_1h,
        )

    # 4h Cooldown check
    if last_exit_time_ms is not None:
        cooldown_end_ms = ((last_exit_time_ms + 59_999) // 60_000) * 60_000 + 4 * 3_600_000
        if decision_time_ms < cooldown_end_ms:
            return None, curr_retest

    # 1h ATR20 check
    atr20_1h = compute_atr20_1h(list(bars_1h))
    if atr20_1h is None or atr20_1h <= Decimal(0):
        return None, curr_retest

    decision_close = current_1h.close
    vol_bps = atr20_1h / decision_close
    if vol_bps < MIN_RISK_BPS or vol_bps > MAX_RISK_BPS:
        return None, curr_retest

    # 4h Indicator preparation
    closes_4h = [b.close for b in bars_4h]
    ema20_series = compute_ema_series(closes_4h, 20)
    ema50_series = compute_ema_series(closes_4h, 50)
    ema20_now = ema20_series[-1]
    ema50_now = ema50_series[-1]
    if ema20_now is None or ema50_now is None:
        return None, curr_retest

    last_4h = bars_4h[-1]

    if candidate.family == CandidateFamily.STRUCTURAL_CONTINUATION:
        # Requires newer completed 4h bar than preceding entry
        if last_entry_4h_time_ms is not None and last_4h.timestamp_ms <= last_entry_4h_time_ms:
            return None, curr_retest

        if len(ema20_series) < 4 or ema20_series[-4] is None:
            return None, curr_retest
        ema20_3_bars_ago = ema20_series[-4]
        if ema20_3_bars_ago is None:
            return None, curr_retest

        # 4h ATR20
        atr20_4h = compute_atr20_4h(list(bars_4h))
        if atr20_4h is None or atr20_4h <= Decimal(0):
            return None, curr_retest

        # Distance from 4h EMA20 <= 1.0 * 4h ATR20
        if abs(last_4h.close - ema20_now) > atr20_4h:
            return None, curr_retest

        # ER12 on 4h >= 0.35
        er12 = compute_er12_4h(list(bars_4h))
        if er12 is None or er12 < Decimal("0.35"):
            return None, curr_retest

        # 1h confirmation: range <= 2 * ATR20
        h_range = current_1h.high - current_1h.low
        if h_range > Decimal("2.0") * atr20_1h:
            return None, curr_retest

        prior_3_1h = bars_1h[-4:-1]
        event_id = f"SC_{symbol}_{candidate.direction.name}_{decision_time_ms}"

        if candidate.direction == Direction.LONG:
            if not (last_4h.close > ema20_now > ema50_now):
                return None, curr_retest
            if not (ema20_now > ema20_3_bars_ago):
                return None, curr_retest
            max_prior_high = max(b.high for b in prior_3_1h)
            if not (current_1h.close > max_prior_high):
                return None, curr_retest
            body = current_1h.close - current_1h.open
            if body < Decimal("0.5") * atr20_1h:
                return None, curr_retest

            proposed_stop = decision_close - Decimal("1.5") * atr20_1h

        else:  # SHORT
            if not (last_4h.close < ema20_now < ema50_now):
                return None, curr_retest
            if not (ema20_now < ema20_3_bars_ago):
                return None, curr_retest
            min_prior_low = min(b.low for b in prior_3_1h)
            if not (current_1h.close < min_prior_low):
                return None, curr_retest
            body = current_1h.open - current_1h.close
            if body < Decimal("0.5") * atr20_1h:
                return None, curr_retest

            proposed_stop = decision_close + Decimal("1.5") * atr20_1h

        signal = SignalEvent(
            candidate_id=candidate.id,
            symbol=symbol,
            direction=candidate.direction,
            decision_time_ms=decision_time_ms,
            available_at_ms=available_at_ms,
            decision_close=quantize12dp(decision_close),
            hourly_atr20=quantize12dp(atr20_1h),
            proposed_stop=quantize12dp(proposed_stop),
            earliest_entry_ms=earliest_entry_ms,
            event_id=event_id,
        )
        return signal, curr_retest

    elif candidate.family == CandidateFamily.CLOSED_RETEST:
        # 4h EMA ordering check
        if candidate.direction == Direction.LONG:
            if not (last_4h.close > ema20_now > ema50_now):
                return None, curr_retest
        else:
            if not (last_4h.close < ema20_now < ema50_now):
                return None, curr_retest

        # Check existing confirmed breakout awaiting entry
        if curr_retest is not None and curr_retest.confirmed and not curr_retest.canceled and not curr_retest.expired and curr_retest.event_id not in consumed_retest_events:
            # Stop calculation using extrema from breakout through confirmation (T25)
                if candidate.direction == Direction.LONG:
                    all_lows = [curr_retest.breakout_low] + list(curr_retest.intermediate_lows)
                    min_low = min(all_lows)
                    stop = min_low - Decimal("0.25") * curr_retest.frozen_atr
                else:
                    all_highs = [curr_retest.breakout_high] + list(curr_retest.intermediate_highs)
                    max_high = max(all_highs)
                    stop = max_high + Decimal("0.25") * curr_retest.frozen_atr

                signal = SignalEvent(
                    candidate_id=candidate.id,
                    symbol=symbol,
                    direction=candidate.direction,
                    decision_time_ms=decision_time_ms,
                    available_at_ms=available_at_ms,
                    decision_close=quantize12dp(decision_close),
                    hourly_atr20=quantize12dp(atr20_1h),
                    proposed_stop=quantize12dp(stop),
                    earliest_entry_ms=earliest_entry_ms,
                    event_id=curr_retest.event_id,
                )
                return signal, curr_retest

        # If breakout is still active (not confirmed and not canceled), wait
        if curr_retest is not None and not curr_retest.confirmed and not curr_retest.canceled and not curr_retest.expired:
            return None, curr_retest

        # AM01 Freeze rule (T26):
        # If terminal transition (cancel/confirm/expire) occurred ON THIS EXACT BAR,
        # cannot seed a new breakout this hour!
        if had_terminal_this_hour:
            return None, curr_retest

        # Check new breakout against prior 24 completed hourly bars
        prior_24_1h = bars_1h[-25:-1]
        new_event_id = f"RETEST_{symbol}_{candidate.direction.name}_{decision_time_ms}"
        if new_event_id in consumed_retest_events:
            return None, curr_retest

        if candidate.direction == Direction.LONG:
            prior_24_high = max(b.high for b in prior_24_1h)
            break_dist = current_1h.close - prior_24_high
            body = current_1h.close - current_1h.open
            if break_dist >= Decimal("0.25") * atr20_1h and body >= Decimal("0.5") * atr20_1h:
                new_retest = RetestState(
                    event_id=new_event_id,
                    symbol=symbol,
                    direction=Direction.LONG,
                    breakout_hour_ms=decision_time_ms,
                    boundary=prior_24_high,
                    frozen_atr=atr20_1h,
                    breakout_high=current_1h.high,
                    breakout_low=current_1h.low,
                    bars_since_breakout=0,
                    intermediate_highs=(current_1h.high,),
                    intermediate_lows=(current_1h.low,),
                    confirmed=False,
                    canceled=False,
                    expired=False,
                    last_advanced_hour_ms=decision_time_ms,
                )
                return None, new_retest
        else:  # SHORT
            prior_24_low = min(b.low for b in prior_24_1h)
            break_dist = prior_24_low - current_1h.close
            body = current_1h.open - current_1h.close
            if break_dist >= Decimal("0.25") * atr20_1h and body >= Decimal("0.5") * atr20_1h:
                new_retest = RetestState(
                    event_id=new_event_id,
                    symbol=symbol,
                    direction=Direction.SHORT,
                    breakout_hour_ms=decision_time_ms,
                    boundary=prior_24_low,
                    frozen_atr=atr20_1h,
                    breakout_high=current_1h.high,
                    breakout_low=current_1h.low,
                    bars_since_breakout=0,
                    intermediate_highs=(current_1h.high,),
                    intermediate_lows=(current_1h.low,),
                    confirmed=False,
                    canceled=False,
                    expired=False,
                    last_advanced_hour_ms=decision_time_ms,
                )
                return None, new_retest

    return None, curr_retest
