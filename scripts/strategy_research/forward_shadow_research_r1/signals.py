"""Mechanistic signal generators, multi-resolution aggregators, and causal feature pipelines.

Under B-line Controller Authority:
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

from .contract import AggTradeData, BarData, BookIntegrityV1, Quality
from .registry import PreRegisteredHypothesis, SignalFamily


class SignalDirection(int, Enum):
    FLAT = 0
    LONG = 1
    SHORT = -1


class SignalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    NO_SIGNAL = "NO_SIGNAL"
    NO_SIGNAL_INCOMPLETE_BOOK = "NO_SIGNAL_INCOMPLETE_BOOK"
    NO_SIGNAL_PREMIUM_NOT_RESTORING = "NO_SIGNAL_PREMIUM_NOT_RESTORING"
    NO_SIGNAL_ABNORMAL_VOLATILITY = "NO_SIGNAL_ABNORMAL_VOLATILITY"
    NO_SIGNAL_INCOMPATIBLE_IMBALANCE = "NO_SIGNAL_INCOMPATIBLE_IMBALANCE"
    NO_SIGNAL_DIRECTIONAL_FILTER_MISMATCH = "NO_SIGNAL_DIRECTIONAL_FILTER_MISMATCH"
    UNFILLABLE_OR_UNKNOWN = "UNFILLABLE_OR_UNKNOWN"
    FILL_UNCERTAIN = "FILL_UNCERTAIN"
    ATR_WARMUP_INSUFFICIENT = "ATR_WARMUP_INSUFFICIENT"
    ATR_GAP_INVALIDATED = "ATR_GAP_INVALIDATED"
    CLOCK_UNCERTAIN = "CLOCK_UNCERTAIN"


@dataclass(frozen=True)
class AggregatedBar:
    bar_open_ms: int
    bar_close_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_complete: bool
    bar_count: int


@dataclass(frozen=True)
class ATRResult:
    valid: bool
    atr_value: float
    stop_distance_1r: float
    target_distance_2r: float
    warmup_hours_observed: int
    reason: str = ""


@dataclass(frozen=True)
class SignalProposal:
    family: SignalFamily
    cell_id: str
    decision_at_ms: int
    feature_known_at_ms: int
    direction: SignalDirection
    status: SignalStatus
    proposed_entry_price: float | None
    best_bid: float | None
    best_ask: float | None
    mark_price: float | None
    atr_result: ATRResult | None
    stop_price: float | None
    target_price: float | None
    metrics: dict[str, float] = field(default_factory=dict)
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


def aggregate_1m_bars(bars_1m: Sequence[BarData], expected_count: int) -> AggregatedBar | None:
    """Aggregate consecutive 1m bars into a higher timeframe bar (e.g. 5m, 15m, 30m, 60m).

    Fails closed (returns None) if any bar is missing, unclosed, or discontinuous.
    """
    if len(bars_1m) != expected_count:
        return None

    # Verify continuity
    for i in range(len(bars_1m)):
        if not bars_1m[i].closed:
            return None
        if i > 0 and bars_1m[i].bar_open_ms != bars_1m[i - 1].bar_close_ms + 1:
            return None

    first = bars_1m[0]
    last = bars_1m[-1]
    high = max(b.high for b in bars_1m)
    low = min(b.low for b in bars_1m)
    vol = sum(b.volume for b in bars_1m)

    return AggregatedBar(
        bar_open_ms=first.bar_open_ms,
        bar_close_ms=last.bar_close_ms,
        open=first.open,
        high=high,
        low=low,
        close=last.close,
        volume=vol,
        is_complete=True,
        bar_count=len(bars_1m),
    )


def compute_atr_1h(
    hourly_bars: Sequence[AggregatedBar],
    period: int = 14,
    min_warmup_hours: int = 200,
) -> ATRResult:
    """Compute strictly causal 1h ATR(14) with >=200h warmup and gap invalidation.

    Wilder's smoothing over True Range:
    TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
    ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period
    """
    if len(hourly_bars) < min_warmup_hours:
        return ATRResult(
            valid=False,
            atr_value=0.0,
            stop_distance_1r=0.0,
            target_distance_2r=0.0,
            warmup_hours_observed=len(hourly_bars),
            reason=f"WARMUP_INSUFFICIENT_{len(hourly_bars)}_OF_{min_warmup_hours}",
        )

    # Check continuity across all bars
    for i in range(1, len(hourly_bars)):
        prev_bar = hourly_bars[i - 1]
        curr_bar = hourly_bars[i]
        # 1 hour = 3,600,000 ms. Normal gap is 1ms between close and open
        if curr_bar.bar_open_ms != prev_bar.bar_close_ms + 1:
            return ATRResult(
                valid=False,
                atr_value=0.0,
                stop_distance_1r=0.0,
                target_distance_2r=0.0,
                warmup_hours_observed=len(hourly_bars),
                reason=f"ATR_GAP_DETECTED_AT_INDEX_{i}",
            )

    # Compute True Range series
    tr_series: list[float] = []
    for i in range(len(hourly_bars)):
        curr = hourly_bars[i]
        if i == 0:
            tr = curr.high - curr.low
        else:
            prev = hourly_bars[i - 1]
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev.close),
                abs(curr.low - prev.close),
            )
        tr_series.append(tr)

    # Initial SMA over first `period` bars
    initial_atr = sum(tr_series[:period]) / float(period)
    atr = initial_atr

    # Wilder's smoothing for subsequent bars
    for i in range(period, len(tr_series)):
        atr = (atr * (period - 1) + tr_series[i]) / float(period)

    return ATRResult(
        valid=True,
        atr_value=atr,
        stop_distance_1r=1.0 * atr,
        target_distance_2r=2.0 * atr,
        warmup_hours_observed=len(hourly_bars),
        reason="VERIFIED",
    )


class SignalEngine:
    """Evaluates the 2 prespecified mechanistic signal families."""

    def __init__(self, hypothesis: PreRegisteredHypothesis):
        self.hypothesis = hypothesis

    def evaluate(
        self,
        decision_at_ms: int,
        feature_known_at_ms: int,
        last_bars_1m: Sequence[BarData],
        mark_bars_1m: Sequence[BarData],
        recent_agg_trades: Sequence[AggTradeData],
        latest_book: BookIntegrityV1 | None,
        hourly_bars_for_atr: Sequence[AggregatedBar],
    ) -> SignalProposal:
        """Evaluate signal proposal under causal as-of invariants."""
        # Multi-stream causal timing gate
        if decision_at_ms < feature_known_at_ms:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.CLOCK_UNCERTAIN,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid if latest_book else None,
                best_ask=latest_book.best_ask if latest_book else None,
                mark_price=mark_bars_1m[-1].close if mark_bars_1m else None,
                atr_result=None,
                stop_price=None,
                target_price=None,
                reason_codes=("DECISION_BEFORE_FEATURE_KNOWN",),
            )

        # Compute ATR(14)
        atr_res = compute_atr_1h(
            hourly_bars_for_atr,
            period=self.hypothesis.atr_period,
            min_warmup_hours=self.hypothesis.atr_min_warmup_hours,
        )
        if not atr_res.valid:
            status = (
                SignalStatus.ATR_GAP_INVALIDATED
                if "GAP" in atr_res.reason
                else SignalStatus.ATR_WARMUP_INSUFFICIENT
            )
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=status,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid if latest_book else None,
                best_ask=latest_book.best_ask if latest_book else None,
                mark_price=mark_bars_1m[-1].close if mark_bars_1m else None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=(atr_res.reason,),
            )

        # Dispatch to specific mechanistic family
        if self.hypothesis.family == SignalFamily.P1_BASIS_REVERSION_V2_SHADOW:
            return self._evaluate_p1_basis_reversion(
                decision_at_ms,
                feature_known_at_ms,
                last_bars_1m,
                mark_bars_1m,
                latest_book,
                atr_res,
            )
        elif self.hypothesis.family == SignalFamily.P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW:
            return self._evaluate_p2_orderflow_resilience(
                decision_at_ms,
                feature_known_at_ms,
                last_bars_1m,
                recent_agg_trades,
                latest_book,
                atr_res,
            )
        else:
            raise ValueError(f"Unknown family: {self.hypothesis.family}")

    def _evaluate_p1_basis_reversion(
        self,
        decision_at_ms: int,
        feature_known_at_ms: int,
        last_bars_1m: Sequence[BarData],
        mark_bars_1m: Sequence[BarData],
        latest_book: BookIntegrityV1 | None,
        atr_res: ATRResult,
    ) -> SignalProposal:
        """Evaluate P1_BASIS_REVERSION_V2_SHADOW.

        1. Observe 15m time-aligned completed Last and Mark closes.
        2. Dislocation candidate:
           abs(last_close - mark_close) / mark_close > max(5bp, 2 * spread)
        3. 5m past normalized premium shrink toward zero:
           |P(t)| < |P(t - 5m)|
           Long when Last below Mark and restoring.
           Short when Last above Mark and restoring.
        4. 30m abnormal vol cap check.
        5. Never execute at Mark; entry at best_ask (long) or best_bid (short).
        """
        # Check required bars count (at least 30 1m bars for 30m vol cap and 15m decision)
        if len(last_bars_1m) < 30 or len(mark_bars_1m) < 30:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid if latest_book else None,
                best_ask=latest_book.best_ask if latest_book else None,
                mark_price=mark_bars_1m[-1].close if mark_bars_1m else None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("INSUFFICIENT_1M_BARS_FOR_30M_CAP",),
            )

        # Check time alignment of 15m decision window (last 15 bars)
        for i in range(-15, 0):
            lb = last_bars_1m[i]
            mb = mark_bars_1m[i]
            if lb.bar_open_ms != mb.bar_open_ms or lb.bar_close_ms != mb.bar_close_ms:
                return SignalProposal(
                    family=self.hypothesis.family,
                    cell_id=self.hypothesis.cell_id,
                    decision_at_ms=decision_at_ms,
                    feature_known_at_ms=feature_known_at_ms,
                    direction=SignalDirection.FLAT,
                    status=SignalStatus.NO_SIGNAL,
                    proposed_entry_price=None,
                    best_bid=latest_book.best_bid if latest_book else None,
                    best_ask=latest_book.best_ask if latest_book else None,
                    mark_price=mark_bars_1m[-1].close if mark_bars_1m else None,
                    atr_result=atr_res,
                    stop_price=None,
                    target_price=None,
                    reason_codes=("LAST_MARK_1M_TIME_MISALIGNMENT",),
                )

        # Check book validity for spread calculation and quote execution
        if (
            latest_book is None
            or latest_book.best_bid is None
            or latest_book.best_ask is None
            or latest_book.quality != Quality.VERIFIED
            or latest_book.best_bid >= latest_book.best_ask
        ):
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.UNFILLABLE_OR_UNKNOWN,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid if latest_book else None,
                best_ask=latest_book.best_ask if latest_book else None,
                mark_price=mark_bars_1m[-1].close if mark_bars_1m else None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("INVALID_OR_MISSING_BOOK",),
            )

        mark_close = mark_bars_1m[-1].close
        last_close = last_bars_1m[-1].close

        # Effective top bid/ask spread
        top_spread = (latest_book.best_ask - latest_book.best_bid) / mark_close
        min_dislocation_ratio = max(
            self.hypothesis.min_dislocation_bps / 10000.0,  # 5bp = 0.0005
            self.hypothesis.spread_multiplier * top_spread, # 2x spread
        )

        current_dislocation = abs(last_close - mark_close) / mark_close

        metrics = {
            "last_close": last_close,
            "mark_close": mark_close,
            "current_dislocation_bps": current_dislocation * 10000.0,
            "threshold_dislocation_bps": min_dislocation_ratio * 10000.0,
            "top_spread_bps": top_spread * 10000.0,
        }

        # Step 1: Dislocation gate
        if current_dislocation <= min_dislocation_ratio:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=mark_close,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=("DISLOCATION_BELOW_THRESHOLD",),
            )

        # Step 2: 5m past premium shrink toward zero
        # 5m prior is index -6 in the 1m sequence
        last_close_5m = last_bars_1m[-6].close
        mark_close_5m = mark_bars_1m[-6].close
        premium_t = (last_close - mark_close) / mark_close
        premium_5m = (last_close_5m - mark_close_5m) / mark_close_5m

        metrics["premium_t_bps"] = premium_t * 10000.0
        metrics["premium_5m_bps"] = premium_5m * 10000.0

        # Must shrink toward zero: abs(premium_t) < abs(premium_5m)
        is_shrinking = abs(premium_t) < abs(premium_5m)

        if not is_shrinking:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_PREMIUM_NOT_RESTORING,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=mark_close,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=("PREMIUM_NOT_SHRINKING_TOWARD_ZERO",),
            )

        # Determine restoring direction
        # Long when Last below Mark (premium_t < 0) and restoring (moving up: premium_t > premium_5m)
        # Short when Last above Mark (premium_t > 0) and restoring (moving down: premium_t < premium_5m)
        if premium_t < 0 and premium_t > premium_5m:
            direction = SignalDirection.LONG
        elif premium_t > 0 and premium_t < premium_5m:
            direction = SignalDirection.SHORT
        else:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_PREMIUM_NOT_RESTORING,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=mark_close,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=("DIRECTIONAL_RESTORATION_MISMATCH",),
            )

        # Step 3: 30m abnormal vol cap
        high_30m = max(b.high for b in last_bars_1m[-30:])
        low_30m = min(b.low for b in last_bars_1m[-30:])
        vol_range_bps = ((high_30m - low_30m) / mark_close) * 10000.0
        metrics["vol_range_30m_bps"] = vol_range_bps

        if vol_range_bps > self.hypothesis.abnormal_vol_cap_bps:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_ABNORMAL_VOLATILITY,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=mark_close,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=(f"ABNORMAL_VOL_CAP_EXCEEDED_{vol_range_bps:.1f}BPS",),
            )

        # Step 4: Shadow entry execution price (never Mark)
        # LONG enters at best_ask; SHORT enters at best_bid
        entry_price = latest_book.best_ask if direction == SignalDirection.LONG else latest_book.best_bid

        # Stops and Targets based on 1h ATR(14)
        if direction == SignalDirection.LONG:
            stop_price = entry_price - (self.hypothesis.stop_r_multiple * atr_res.atr_value)
            target_price = entry_price + (self.hypothesis.target_r_multiple * atr_res.atr_value)
        else:
            stop_price = entry_price + (self.hypothesis.stop_r_multiple * atr_res.atr_value)
            target_price = entry_price - (self.hypothesis.target_r_multiple * atr_res.atr_value)

        return SignalProposal(
            family=self.hypothesis.family,
            cell_id=self.hypothesis.cell_id,
            decision_at_ms=decision_at_ms,
            feature_known_at_ms=feature_known_at_ms,
            direction=direction,
            status=SignalStatus.PROPOSED,
            proposed_entry_price=entry_price,
            best_bid=latest_book.best_bid,
            best_ask=latest_book.best_ask,
            mark_price=mark_close,
            atr_result=atr_res,
            stop_price=stop_price,
            target_price=target_price,
            metrics=metrics,
            reason_codes=("P1_BASIS_REVERSION_PROPOSAL_VERIFIED",),
        )

    def _evaluate_p2_orderflow_resilience(
        self,
        decision_at_ms: int,
        feature_known_at_ms: int,
        last_bars_1m: Sequence[BarData],
        recent_agg_trades: Sequence[AggTradeData],
        latest_book: BookIntegrityV1 | None,
        atr_res: ATRResult,
    ) -> SignalProposal:
        """Evaluate P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW.

        1. Aggressor signed traded quote notional imbalance > +0.20 / < -0.20 over last 15m.
        2. Top 10 book imbalance (bid - ask)/(bid + ask) > +0.10 / < -0.10.
        3. If no verified continuous L2, emit NO_SIGNAL_INCOMPLETE_BOOK.
        4. Direction: jointly positive (LONG) or jointly negative (SHORT).
        5. 30m prior close directional agreement filter:
           close >= close_30m_ago (LONG), close <= close_30m_ago (SHORT).
        """
        # Check bars count (need at least 30 1m bars for 30m directional filter)
        if len(last_bars_1m) < 30:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid if latest_book else None,
                best_ask=latest_book.best_ask if latest_book else None,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("INSUFFICIENT_BARS_FOR_30M_FILTER",),
            )

        # Strict L2 book verification: must exist, be verified, continuous, and have top 10 depth
        if (
            latest_book is None
            or latest_book.quality != Quality.VERIFIED
            or not latest_book.continuous
            or len(latest_book.bids) < self.hypothesis.book_top_levels
            or len(latest_book.asks) < self.hypothesis.book_top_levels
        ):
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_INCOMPLETE_BOOK,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid if latest_book else None,
                best_ask=latest_book.best_ask if latest_book else None,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("NO_VERIFIED_L2_CONTINUOUS_BOOK",),
            )

        # Check crossed spread or depth staleness
        if latest_book.best_bid is None or latest_book.best_ask is None or latest_book.best_bid >= latest_book.best_ask:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.UNFILLABLE_OR_UNKNOWN,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("CROSSED_OR_EMPTY_SPREAD",),
            )

        if latest_book.stale_age_ms > self.hypothesis.stale_depth_max_ms:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.FILL_UNCERTAIN,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("DEPTH_STALE_OVER_1000MS",),
            )

        # Step 1: Compute 15m aggressor traded notional imbalance
        cutoff_15m_ms = decision_at_ms - (15 * 60 * 1000)
        trades_15m = [t for t in recent_agg_trades if t.trade_time_ms >= cutoff_15m_ms]

        buy_notional = 0.0
        sell_notional = 0.0
        for t in trades_15m:
            notional = t.price * t.quantity
            # is_buyer_maker == True => buyer was maker => seller was taker (sell aggressor)
            # is_buyer_maker == False => buyer was taker (buy aggressor)
            if t.is_buyer_maker:
                sell_notional += notional
            else:
                buy_notional += notional

        total_trade_notional = buy_notional + sell_notional
        if total_trade_notional <= 0:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("ZERO_AGG_TRADES_IN_15M",),
            )

        agg_imbalance = (buy_notional - sell_notional) / total_trade_notional

        # Step 2: Compute top 10 order book imbalance
        book_imbalance = latest_book.top_n_imbalance(self.hypothesis.book_top_levels)
        if book_imbalance is None:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_INCOMPLETE_BOOK,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                reason_codes=("CANNOT_COMPUTE_BOOK_IMBALANCE",),
            )

        metrics = {
            "agg_imbalance": agg_imbalance,
            "book_imbalance": book_imbalance,
            "buy_trade_notional": buy_notional,
            "sell_trade_notional": sell_notional,
        }

        # Step 3: Direction determination from jointly positive/negative signals
        agg_thresh = self.hypothesis.agg_trade_imbalance_threshold
        book_thresh = self.hypothesis.book_imbalance_threshold

        if agg_imbalance > agg_thresh and book_imbalance > book_thresh:
            direction = SignalDirection.LONG
        elif agg_imbalance < -agg_thresh and book_imbalance < -book_thresh:
            direction = SignalDirection.SHORT
        else:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_INCOMPATIBLE_IMBALANCE,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=("IMBALANCE_CONDITIONS_NOT_MET_OR_INCOMPATIBLE",),
            )

        # Step 4: 30m prior close directional agreement filter
        close_now = last_bars_1m[-1].close
        close_30m_ago = last_bars_1m[-30].close
        metrics["close_now"] = close_now
        metrics["close_30m_ago"] = close_30m_ago

        if direction == SignalDirection.LONG and close_now < close_30m_ago:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_DIRECTIONAL_FILTER_MISMATCH,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=("LONG_FILTER_MISMATCH_CLOSE_BELOW_30M_AGO",),
            )
        elif direction == SignalDirection.SHORT and close_now > close_30m_ago:
            return SignalProposal(
                family=self.hypothesis.family,
                cell_id=self.hypothesis.cell_id,
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                direction=SignalDirection.FLAT,
                status=SignalStatus.NO_SIGNAL_DIRECTIONAL_FILTER_MISMATCH,
                proposed_entry_price=None,
                best_bid=latest_book.best_bid,
                best_ask=latest_book.best_ask,
                mark_price=None,
                atr_result=atr_res,
                stop_price=None,
                target_price=None,
                metrics=metrics,
                reason_codes=("SHORT_FILTER_MISMATCH_CLOSE_ABOVE_30M_AGO",),
            )

        # Step 5: Shadow entry price (actionable executable quote)
        entry_price = latest_book.best_ask if direction == SignalDirection.LONG else latest_book.best_bid

        # Stops and Targets based on 1h ATR(14)
        if direction == SignalDirection.LONG:
            stop_price = entry_price - (self.hypothesis.stop_r_multiple * atr_res.atr_value)
            target_price = entry_price + (self.hypothesis.target_r_multiple * atr_res.atr_value)
        else:
            stop_price = entry_price + (self.hypothesis.stop_r_multiple * atr_res.atr_value)
            target_price = entry_price - (self.hypothesis.target_r_multiple * atr_res.atr_value)

        return SignalProposal(
            family=self.hypothesis.family,
            cell_id=self.hypothesis.cell_id,
            decision_at_ms=decision_at_ms,
            feature_known_at_ms=feature_known_at_ms,
            direction=direction,
            status=SignalStatus.PROPOSED,
            proposed_entry_price=entry_price,
            best_bid=latest_book.best_bid,
            best_ask=latest_book.best_ask,
            mark_price=None,
            atr_result=atr_res,
            stop_price=stop_price,
            target_price=target_price,
            metrics=metrics,
            reason_codes=("P2_ORDERFLOW_RESILIENCE_PROPOSAL_VERIFIED",),
        )
