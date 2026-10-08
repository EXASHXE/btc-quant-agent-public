"""Signal evaluation engine for Structural Continuation and Closed Retest families."""

from dataclasses import dataclass
from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.constants import (
    DECISION_AVAILABILITY_LAG_MS,
    FILL_DELAY_FROM_DECISION_MS,
    MAX_RISK_BPS,
    MIN_RISK_BPS,
)
from btc_quant_agent.strategy_research.r3_overnight.indicators import (
    compute_atr20_1h,
    compute_atr20_4h,
    compute_ema_series,
    compute_er12_4h,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1h,
    Bar4h,
    CandidateDefinition,
    CandidateFamily,
    Direction,
    SignalEvent,
)


@dataclass
class RetestBreakoutState:
    """State of an ongoing breakout awaiting retest confirmation."""
    event_id: str
    symbol: str
    direction: Direction
    breakout_hour_ms: int
    boundary: Decimal
    frozen_atr: Decimal
    breakout_high: Decimal
    breakout_low: Decimal
    bars_since_breakout: int = 0
    intermediate_highs: list[Decimal] = None
    intermediate_lows: list[Decimal] = None
    confirmed: bool = False
    canceled: bool = False

    def __post_init__(self):
        if self.intermediate_highs is None:
            self.intermediate_highs = [self.breakout_high]
        if self.intermediate_lows is None:
            self.intermediate_lows = [self.breakout_low]


class SignalGenerator:
    """Evaluates hourly bars at exclusive close + 60s lag for all 8 candidates."""

    def __init__(self) -> None:
        # Per symbol/direction active breakout states
        self._active_breakouts: dict[tuple[str, Direction], RetestBreakoutState] = {}
        # Completed/consumed retest event IDs to guarantee single-use
        self._consumed_retest_events: set[str] = set()

    def evaluate_hourly_decision(
        self,
        candidate: CandidateDefinition,
        symbol: str,
        bars_1h: list[Bar1h],
        bars_4h: list[Bar4h],
        last_exit_time_ms: int | None = None,
        last_entry_4h_time_ms: int | None = None,
    ) -> SignalEvent | None:
        """
        Evaluate candidate rule at exclusive end of latest completed 1h bar.
        Decision available at bar_close + 60s.
        Earliest entry at bar_close + 120s (following minute open).
        """
        if len(bars_1h) < 25:  # Need 24 preceding + current 1h bar
            return None
        if len(bars_4h) < 60:  # Need 60 completed 4h bars for EMA stabilization
            return None

        current_1h = bars_1h[-1]
        decision_time_ms = current_1h.close_ms
        available_at_ms = decision_time_ms + DECISION_AVAILABILITY_LAG_MS
        earliest_entry_ms = decision_time_ms + FILL_DELAY_FROM_DECISION_MS + DECISION_AVAILABILITY_LAG_MS

        # Check 4h cooldown
        if last_exit_time_ms is not None and decision_time_ms < last_exit_time_ms + 4 * 3_600_000:
            return None

        # Hourly ATR20 check
        atr20_1h = compute_atr20_1h(bars_1h)
        if atr20_1h is None or atr20_1h <= Decimal(0):
            return None

        decision_close = current_1h.close
        vol_bps = atr20_1h / decision_close
        if vol_bps < MIN_RISK_BPS or vol_bps > MAX_RISK_BPS:
            return None

        # 4h Indicator preparation
        closes_4h = [b.close for b in bars_4h]
        ema20_series = compute_ema_series(closes_4h, 20)
        ema50_series = compute_ema_series(closes_4h, 50)

        ema20_now = ema20_series[-1]
        ema50_now = ema50_series[-1]
        if ema20_now is None or ema50_now is None:
            return None

        last_4h = bars_4h[-1]
        current_4h_time_ms = last_4h.timestamp_ms

        if candidate.family == CandidateFamily.STRUCTURAL_CONTINUATION:
            # Requires newer completed 4h bar than preceding entry
            if last_entry_4h_time_ms is not None and current_4h_time_ms <= last_entry_4h_time_ms:
                return None

            return self._evaluate_structural_continuation(
                candidate=candidate,
                symbol=symbol,
                bars_1h=bars_1h,
                bars_4h=bars_4h,
                ema20_series=ema20_series,
                ema50_series=ema50_series,
                atr20_1h=atr20_1h,
                decision_time_ms=decision_time_ms,
                available_at_ms=available_at_ms,
                earliest_entry_ms=earliest_entry_ms,
            )

        elif candidate.family == CandidateFamily.CLOSED_RETEST:
            return self._evaluate_closed_retest(
                candidate=candidate,
                symbol=symbol,
                bars_1h=bars_1h,
                bars_4h=bars_4h,
                ema20_now=ema20_now,
                ema50_now=ema50_now,
                atr20_1h=atr20_1h,
                decision_time_ms=decision_time_ms,
                available_at_ms=available_at_ms,
                earliest_entry_ms=earliest_entry_ms,
            )

        return None

    def _evaluate_structural_continuation(
        self,
        candidate: CandidateDefinition,
        symbol: str,
        bars_1h: list[Bar1h],
        bars_4h: list[Bar4h],
        ema20_series: list[Decimal | None],
        ema50_series: list[Decimal | None],
        atr20_1h: Decimal,
        decision_time_ms: int,
        available_at_ms: int,
        earliest_entry_ms: int,
    ) -> SignalEvent | None:
        current_1h = bars_1h[-1]
        decision_close = current_1h.close
        last_4h = bars_4h[-1]
        ema20_now = ema20_series[-1]
        ema50_now = ema50_series[-1]

        # EMA20 3 bars earlier (need at least 4 valid 4h EMA points)
        if len(ema20_series) < 4 or ema20_series[-4] is None:
            return None
        ema20_3_bars_ago = ema20_series[-4]

        # 4h ATR20
        atr20_4h = compute_atr20_4h(bars_4h)
        if atr20_4h is None or atr20_4h <= Decimal(0):
            return None

        # Distance from 4h EMA20 <= 1.0 * 4h ATR20
        dist_from_ema20 = abs(last_4h.close - ema20_now)
        if dist_from_ema20 > atr20_4h:
            return None

        # ER12 on 4h >= 0.35
        er12 = compute_er12_4h(bars_4h)
        if er12 is None or er12 < Decimal("0.35"):
            return None

        # 1h confirmation: range <= 2 * ATR20
        h_range = current_1h.high - current_1h.low
        if h_range > Decimal("2.0") * atr20_1h:
            return None

        prior_3_1h = bars_1h[-4:-1]
        event_id = f"SC_{symbol}_{candidate.direction.name}_{decision_time_ms}"

        if candidate.direction == Direction.LONG:
            # 4h structure: close > EMA20 > EMA50
            if not (last_4h.close > ema20_now > ema50_now):
                return None
            # EMA20 rising
            if not (ema20_now > ema20_3_bars_ago):
                return None
            # 1h close breaks highs of prior 3 completed 1h bars
            max_prior_high = max(b.high for b in prior_3_1h)
            if not (current_1h.close > max_prior_high):
                return None
            # Signed body >= 0.5 ATR20
            body = current_1h.close - current_1h.open
            if body < Decimal("0.5") * atr20_1h:
                return None

            proposed_stop = decision_close - Decimal("1.5") * atr20_1h

        else:  # SHORT
            # 4h structure: close < EMA20 < EMA50
            if not (last_4h.close < ema20_now < ema50_now):
                return None
            # EMA20 falling
            if not (ema20_now < ema20_3_bars_ago):
                return None
            # 1h close breaks lows of prior 3 completed 1h bars
            min_prior_low = min(b.low for b in prior_3_1h)
            if not (current_1h.close < min_prior_low):
                return None
            # Signed body >= 0.5 ATR20
            body = current_1h.open - current_1h.close
            if body < Decimal("0.5") * atr20_1h:
                return None

            proposed_stop = decision_close + Decimal("1.5") * atr20_1h

        return SignalEvent(
            candidate_id=candidate.id,
            symbol=symbol,
            direction=candidate.direction,
            decision_time_ms=decision_time_ms,
            available_at_ms=available_at_ms,
            decision_close=decision_close,
            hourly_atr20=atr20_1h,
            proposed_stop=proposed_stop,
            earliest_entry_ms=earliest_entry_ms,
            event_id=event_id,
            metadata={"er12": str(er12), "dist_ema20": str(dist_from_ema20)},
        )

    def _evaluate_closed_retest(
        self,
        candidate: CandidateDefinition,
        symbol: str,
        bars_1h: list[Bar1h],
        bars_4h: list[Bar4h],
        ema20_now: Decimal,
        ema50_now: Decimal,
        atr20_1h: Decimal,
        decision_time_ms: int,
        available_at_ms: int,
        earliest_entry_ms: int,
    ) -> SignalEvent | None:
        current_1h = bars_1h[-1]
        decision_close = current_1h.close
        last_4h = bars_4h[-1]
        key = (symbol, candidate.direction)

        # 4h EMA direction ordering check
        if candidate.direction == Direction.LONG:
            if not (last_4h.close > ema20_now > ema50_now):
                return None
        else:
            if not (last_4h.close < ema20_now < ema50_now):
                return None

        # Check existing breakout state
        breakout = self._active_breakouts.get(key)
        if breakout is not None and not breakout.confirmed and not breakout.canceled:
            breakout.bars_since_breakout += 1
            breakout.intermediate_highs.append(current_1h.high)
            breakout.intermediate_lows.append(current_1h.low)

            # Check cancellation: close beyond boundary by 0.25 frozen ATR in wrong direction
            if candidate.direction == Direction.LONG:
                if current_1h.close < breakout.boundary - Decimal("0.25") * breakout.frozen_atr:
                    breakout.canceled = True
                    return None
            else:
                if current_1h.close > breakout.boundary + Decimal("0.25") * breakout.frozen_atr:
                    breakout.canceled = True
                    return None

            # Only next 3 closed hourly bars may confirm
            if breakout.bars_since_breakout > 3:
                breakout.canceled = True
                return None

            # Check confirmation
            if candidate.direction == Direction.LONG:
                # low touches [boundary - 0.25 ATR, boundary + 0.25 ATR]
                touches_zone = (
                    current_1h.low <= breakout.boundary + Decimal("0.25") * breakout.frozen_atr
                    and current_1h.high >= breakout.boundary - Decimal("0.25") * breakout.frozen_atr
                )
                close_above = current_1h.close >= breakout.boundary + Decimal("0.10") * breakout.frozen_atr
                bullish_bar = current_1h.close > current_1h.open

                if touches_zone and close_above and bullish_bar:
                    breakout.confirmed = True
                    self._consumed_retest_events.add(breakout.event_id)
                    # Stop LONG is minimum low from breakout through confirmation minus 0.25 frozen ATR
                    min_low = min(breakout.intermediate_lows)
                    stop = min_low - Decimal("0.25") * breakout.frozen_atr
                    return SignalEvent(
                        candidate_id=candidate.id,
                        symbol=symbol,
                        direction=Direction.LONG,
                        decision_time_ms=decision_time_ms,
                        available_at_ms=available_at_ms,
                        decision_close=decision_close,
                        hourly_atr20=atr20_1h,
                        proposed_stop=stop,
                        earliest_entry_ms=earliest_entry_ms,
                        event_id=breakout.event_id,
                        metadata={"breakout_boundary": str(breakout.boundary)},
                    )

            else:  # SHORT
                touches_zone = (
                    current_1h.high >= breakout.boundary - Decimal("0.25") * breakout.frozen_atr
                    and current_1h.low <= breakout.boundary + Decimal("0.25") * breakout.frozen_atr
                )
                close_below = current_1h.close <= breakout.boundary - Decimal("0.10") * breakout.frozen_atr
                bearish_bar = current_1h.close < current_1h.open

                if touches_zone and close_below and bearish_bar:
                    breakout.confirmed = True
                    self._consumed_retest_events.add(breakout.event_id)
                    # Stop SHORT is maximum high from breakout through confirmation plus 0.25 frozen ATR
                    max_high = max(breakout.intermediate_highs)
                    stop = max_high + Decimal("0.25") * breakout.frozen_atr
                    return SignalEvent(
                        candidate_id=candidate.id,
                        symbol=symbol,
                        direction=Direction.SHORT,
                        decision_time_ms=decision_time_ms,
                        available_at_ms=available_at_ms,
                        decision_close=decision_close,
                        hourly_atr20=atr20_1h,
                        proposed_stop=stop,
                        earliest_entry_ms=earliest_entry_ms,
                        event_id=breakout.event_id,
                        metadata={"breakout_boundary": str(breakout.boundary)},
                    )

            return None

        # Check for new breakout
        prior_24_1h = bars_1h[-25:-1]
        event_id = f"RETEST_{symbol}_{candidate.direction.name}_{decision_time_ms}"
        if event_id in self._consumed_retest_events:
            return None

        if candidate.direction == Direction.LONG:
            prior_24_high = max(b.high for b in prior_24_1h)
            break_dist = current_1h.close - prior_24_high
            body = current_1h.close - current_1h.open
            if break_dist >= Decimal("0.25") * atr20_1h and body >= Decimal("0.5") * atr20_1h:
                # Register breakout
                self._active_breakouts[key] = RetestBreakoutState(
                    event_id=event_id,
                    symbol=symbol,
                    direction=Direction.LONG,
                    breakout_hour_ms=decision_time_ms,
                    boundary=prior_24_high,
                    frozen_atr=atr20_1h,
                    breakout_high=current_1h.high,
                    breakout_low=current_1h.low,
                )
        else:  # SHORT
            prior_24_low = min(b.low for b in prior_24_1h)
            break_dist = prior_24_low - current_1h.close
            body = current_1h.open - current_1h.close
            if break_dist >= Decimal("0.25") * atr20_1h and body >= Decimal("0.5") * atr20_1h:
                # Register breakout
                self._active_breakouts[key] = RetestBreakoutState(
                    event_id=event_id,
                    symbol=symbol,
                    direction=Direction.SHORT,
                    breakout_hour_ms=decision_time_ms,
                    boundary=prior_24_low,
                    frozen_atr=atr20_1h,
                    breakout_high=current_1h.high,
                    breakout_low=current_1h.low,
                )

        return None
