"""Read-only shadow order execution simulator, time-cap manager, and protective stop ordering.

Under B-line Controller Authority:
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

import collections
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .account import ExitReason, PaperAccount, PositionStatus
from .contract import AggTradeData, BarData, BookIntegrityV1, SettledFundingData
from .registry import PreRegisteredHypothesis
from .signals import (
    AggregatedBar,
    SignalDirection,
    SignalEngine,
    SignalProposal,
    SignalStatus,
    aggregate_1m_bars,
)


@dataclass
class ShadowExecutionSummary:
    cell_id: str
    total_decision_evaluations: int
    signals_proposed_count: int
    positions_opened_count: int
    positions_closed_count: int
    positions_right_censored_count: int
    unfillable_proposals_count: int
    closed_positions: list[dict[str, Any]]
    account_initial_capital_usdt: float
    account_final_cash_usdt: float
    net_pnl_usdt: float
    mean_net_bps: float
    all_cost_complete: bool
    incomplete_economics_count: int


class ShadowExecutionEngine:
    """Manages full forward shadow simulation for a specific prespecified hypothesis cell."""

    def __init__(self, hypothesis: PreRegisteredHypothesis):
        self.hypothesis = hypothesis
        self.account = PaperAccount(
            initial_capital_usdt=hypothesis.account_capital_usdt,
            reserve_fraction=hypothesis.reserve_fraction,
            lot_step_btc=hypothesis.lot_step_btc,
            cooldown_hours=hypothesis.cooldown_hours,
            taker_fee_bps=hypothesis.taker_fee_bps,
            adverse_slippage_bps=hypothesis.adverse_slippage_bps,
        )
        self.signal_engine = SignalEngine(hypothesis)

        # Rolling data buffers
        self.last_bars_1m: list[BarData] = []
        self.mark_bars_1m: list[BarData] = []
        self.agg_trades_buffer: collections.deque[AggTradeData] = collections.deque()
        self.hourly_bars_buffer: list[AggregatedBar] = []
        self.hourly_accumulation_1m: list[BarData] = []

        self.latest_book: BookIntegrityV1 | None = None
        self.total_decision_evaluations: int = 0
        self.signals_proposed_count: int = 0
        self.unfillable_proposals_count: int = 0

    def set_warmup_hourly_bars(self, hourly_bars: Sequence[AggregatedBar]) -> None:
        """Seed pre-calculated hourly bars for ATR(14) 200h warmup prefix."""
        self.hourly_bars_buffer.extend(hourly_bars)

    def on_agg_trade(self, trade: AggTradeData) -> None:
        """Record trade in rolling 30m trade buffer."""
        self.agg_trades_buffer.append(trade)
        # Prune trades older than 30 minutes
        cutoff = trade.trade_time_ms - (30 * 60 * 1000)
        while self.agg_trades_buffer and self.agg_trades_buffer[0].trade_time_ms < cutoff:
            self.agg_trades_buffer.popleft()

    def on_book_update(self, book: BookIntegrityV1) -> None:
        """Update current top order book."""
        self.latest_book = book

    def on_funding_settled(self, funding_data: SettledFundingData, observed_at_ms: int) -> None:
        """Process official settled funding event."""
        if self.account.active_position is not None:
            self.account.active_position.apply_funding(funding_data, observed_at_ms)

    def on_minute_bars(
        self,
        last_bar_1m: BarData,
        mark_bar_1m: BarData,
        current_available_at_ms: int,
    ) -> SignalProposal | None:
        """Process strictly time-aligned 1m bar close for Last and Mark."""
        # Append to minute bars
        self.last_bars_1m.append(last_bar_1m)
        self.mark_bars_1m.append(mark_bar_1m)

        # Maintain 1h bar aggregator
        self.hourly_accumulation_1m.append(last_bar_1m)
        if len(self.hourly_accumulation_1m) == 60:
            h_bar = aggregate_1m_bars(self.hourly_accumulation_1m, 60)
            if h_bar is not None:
                self.hourly_bars_buffer.append(h_bar)
            self.hourly_accumulation_1m.clear()

        # Step 1: Manage active position exits on this new minute bar
        if self.account.active_position is not None:
            self._evaluate_active_position_exits(last_bar_1m, mark_bar_1m)

        # Step 2: Signal evaluation at 15m decision boundaries
        proposal: SignalProposal | None = None
        # Decision boundary: bar_close_ms is aligned with 15m (900,000 ms)
        is_15m_boundary = (last_bar_1m.bar_close_ms + 1) % (15 * 60 * 1000) == 0

        if is_15m_boundary and len(self.last_bars_1m) >= 30:
            self.total_decision_evaluations += 1
            feature_known_at_ms = max(current_available_at_ms, last_bar_1m.bar_close_ms + 1)
            decision_at_ms = feature_known_at_ms + 1

            # Evaluate signal
            proposal = self.signal_engine.evaluate(
                decision_at_ms=decision_at_ms,
                feature_known_at_ms=feature_known_at_ms,
                last_bars_1m=self.last_bars_1m,
                mark_bars_1m=self.mark_bars_1m,
                recent_agg_trades=tuple(self.agg_trades_buffer),
                latest_book=self.latest_book,
                hourly_bars_for_atr=self.hourly_bars_buffer,
            )

            if proposal.status == SignalStatus.PROPOSED and proposal.direction != SignalDirection.FLAT:
                self.signals_proposed_count += 1
                # If no position is open and not in cooldown, attempt shadow fill
                if self.account.active_position is None and not self.account.is_in_cooldown(decision_at_ms):
                    if (
                        self.latest_book is not None
                        and self.latest_book.best_bid is not None
                        and self.latest_book.best_ask is not None
                        and self.latest_book.best_bid < self.latest_book.best_ask
                        and proposal.stop_price is not None
                        and proposal.target_price is not None
                    ):
                        pos = self.account.open_shadow_position(
                            cell_id=self.hypothesis.cell_id,
                            direction=proposal.direction.value,
                            entry_decision_ms=decision_at_ms,
                            entry_fill_ms=decision_at_ms,
                            best_bid=self.latest_book.best_bid,
                            best_ask=self.latest_book.best_ask,
                            stop_price=proposal.stop_price,
                            target_price=proposal.target_price,
                            horizon_ms=self.hypothesis.horizon_hours.ms,
                        )
                        if pos is None:
                            self.unfillable_proposals_count += 1
                    else:
                        self.unfillable_proposals_count += 1

        return proposal

    def _evaluate_active_position_exits(self, last_bar: BarData, mark_bar: BarData) -> None:
        """Check protective stops, profit targets, and time cap with stop-before-target precedence."""
        pos = self.account.active_position
        if pos is None:
            return

        # Track unrealized MAE using mark close
        pos.update_mae(mark_bar.close)

        stop_hit = False
        target_hit = False

        if pos.direction == 1:
            # Long position
            if last_bar.low <= pos.stop_price:
                stop_hit = True
            if last_bar.high >= pos.target_price:
                target_hit = True
        else:
            # Short position
            if last_bar.high >= pos.stop_price:
                stop_hit = True
            if last_bar.low <= pos.target_price:
                target_hit = True

        # Time cap check
        time_cap_hit = last_bar.bar_close_ms >= pos.max_exit_ms

        # Precedence: Protective stop ALWAYS takes precedence over target if both hit
        exit_reason: ExitReason | None = None
        if stop_hit:
            exit_reason = ExitReason.STOP_LOSS
        elif target_hit:
            exit_reason = ExitReason.PROFIT_TARGET
        elif time_cap_hit:
            exit_reason = ExitReason.TIME_CAP_HORIZON

        if exit_reason is not None:
            # Execute conservative exit quote
            if (
                self.latest_book
                and self.latest_book.best_bid is not None
                and self.latest_book.best_ask is not None
            ):
                current_bid = self.latest_book.best_bid
                current_ask = self.latest_book.best_ask
            else:
                current_bid = last_bar.low
                current_ask = last_bar.high

            if current_bid >= current_ask:
                current_bid = last_bar.close * 0.9999
                current_ask = last_bar.close * 1.0001

            # Conservative quote for STOP LOSS: cannot exit at a better price than the stop price!
            if exit_reason == ExitReason.STOP_LOSS:
                if pos.direction == 1:
                    best_bid = min(pos.stop_price, current_bid)
                    best_ask = best_bid + 1.0
                else:
                    best_ask = max(pos.stop_price, current_ask)
                    best_bid = best_ask - 1.0
            elif exit_reason == ExitReason.PROFIT_TARGET:
                if pos.direction == 1:
                    best_bid = min(pos.target_price, current_bid) if current_bid >= pos.target_price else pos.target_price
                    best_ask = best_bid + 1.0
                else:
                    best_ask = max(pos.target_price, current_ask) if current_ask <= pos.target_price else pos.target_price
                    best_bid = best_ask - 1.0
            else:
                # Time cap / horizon
                best_bid = current_bid
                best_ask = current_ask

            self.account.close_shadow_position(
                exit_fill_ms=last_bar.bar_close_ms,
                best_bid=best_bid,
                best_ask=best_ask,
                exit_reason=exit_reason,
            )

    def finalize_evaluation(self, stream_end_ms: int) -> ShadowExecutionSummary:
        """Finalize simulation, right-censor open positions, and return complete summary."""
        right_censored_count = 0
        if self.account.active_position is not None:
            # Right censor open position
            self.account.active_position.status = PositionStatus.RIGHT_CENSORED
            self.account.active_position.exit_reason = ExitReason.STREAM_END_RIGHT_CENSORED
            right_censored_count += 1
            # Do NOT invent exit fill or PnL!

        closed_dicts = [p.to_dict() for p in self.account.closed_positions]
        net_bps_list = [p.net_bps for p in self.account.closed_positions]
        mean_bps = float(sum(net_bps_list) / len(net_bps_list)) if net_bps_list else 0.0

        all_cost_complete = all(
            p.cost_completeness.value == "COST_COMPLETE" for p in self.account.closed_positions
        )
        incomplete_count = sum(
            1 for p in self.account.closed_positions if p.cost_completeness.value != "COST_COMPLETE"
        )

        return ShadowExecutionSummary(
            cell_id=self.hypothesis.cell_id,
            total_decision_evaluations=self.total_decision_evaluations,
            signals_proposed_count=self.signals_proposed_count,
            positions_opened_count=len(self.account.closed_positions) + right_censored_count,
            positions_closed_count=len(self.account.closed_positions),
            positions_right_censored_count=right_censored_count,
            unfillable_proposals_count=self.unfillable_proposals_count,
            closed_positions=closed_dicts,
            account_initial_capital_usdt=self.account.initial_capital_usdt,
            account_final_cash_usdt=self.account.cash_usdt,
            net_pnl_usdt=self.account.cash_usdt - self.account.initial_capital_usdt,
            mean_net_bps=mean_bps,
            all_cost_complete=all_cost_complete,
            incomplete_economics_count=incomplete_count,
        )
