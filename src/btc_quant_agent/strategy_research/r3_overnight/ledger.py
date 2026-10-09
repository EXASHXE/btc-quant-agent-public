"""Virtual book ledger implementing deterministic 8-stage execution and accounting."""

from decimal import Decimal
from typing import Any

from btc_quant_agent.strategy_research.r3_overnight.constants import (
    ALLOCATION_CEILING_PER_ASSET_USDT,
    COOLDOWN_DURATION_MS,
    DRAWDOWN_KILL_THRESHOLD_USDT,
    FUNDING_OWNERSHIP_HALF_WINDOW_MS,
    INITIAL_EQUITY_USDT,
    MARK_STALENESS_LIMIT_MS,
    MAX_GAP_ATR_FRACTION,
    MAX_RISK_BPS,
    MIN_RISK_BPS,
    RESERVE_BUFFER_MULTIPLIER,
)
from btc_quant_agent.strategy_research.r3_overnight.cost_model import (
    CostModel,
    floor_to_lot,
    round_to_tick,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1m,
    CompletedTrade,
    CostScenario,
    Direction,
    ExitReason,
    FundingEventRecord,
    MarkBar1m,
    Position,
    SignalEvent,
    SymbolFilters,
    VirtualFill,
    VirtualOrder,
)


class VirtualBook:
    """
    Isolated 1,000-USDT virtual book for an individual candidate strategy.
    Implements deterministic point-in-time state ordering and conservative risk latches.
    """

    def __init__(
        self,
        candidate_id: str,
        cost_scenario: CostScenario = CostScenario.BASE,
        symbol_filters: dict[str, SymbolFilters] | None = None,
    ) -> None:
        self.candidate_id = candidate_id
        self.cost_model = CostModel(cost_scenario)
        self.filters = symbol_filters or {
            "BTCUSDT": SymbolFilters(symbol="BTCUSDT", tick_size=Decimal("0.10"), step_size=Decimal("0.001")),
            "ETHUSDT": SymbolFilters(symbol="ETHUSDT", tick_size=Decimal("0.01"), step_size=Decimal("0.01")),
            "SOLUSDT": SymbolFilters(symbol="SOLUSDT", tick_size=Decimal("0.01"), step_size=Decimal("0.1")),
        }

        # Collateral and equity tracking
        self.cash: Decimal = INITIAL_EQUITY_USDT
        self.high_water_equity: Decimal = INITIAL_EQUITY_USDT
        self.decision_equity: Decimal = INITIAL_EQUITY_USDT
        self.economic_equity: Decimal = INITIAL_EQUITY_USDT
        self.killed: bool = False
        self.kill_reason: str | None = None
        self.kill_latched_at_ms: int | None = None
        self.insolvent: bool = False

        # Active positions and orders
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.pending_orders: list[VirtualOrder] = []
        self.due_exits: list[tuple[str, ExitReason, int]] = []  # (symbol, reason, due_at_ms)
        self.completed_trades: list[CompletedTrade] = []
        self.funding_charges: list[FundingEventRecord] = []

        # Commitments and reserves
        self.cost_commitment_o: Decimal = Decimal(0)  # Pending entry notionals + entry/exit reserves
        self.funding_reserve_rf: Decimal = Decimal(0)  # Pending/open funding reserves

        # Acknowledgments and message delays
        self.pending_fill_acks: list[VirtualFill] = []
        self.pending_exit_acks: list[tuple[Any, ...]] = []  # (trade, available_at_ms, exit_reserve, rem_funding)
        self.pending_funding_acks: list[FundingEventRecord] = []

        # Latest available mark prices: symbol -> (mark_price, close_time_ms, available_at_ms)
        self.last_available_marks: dict[str, tuple[Decimal, int, int]] = {}

        # Cooldown per symbol: symbol -> timestamp_ms
        self.cooldown_until_ms: dict[str, int] = {}

        # Economic position history and deduplication tracking
        self.closed_position_ids: set[str] = set()
        self.last_economic_exit_time_ms: dict[str, int] = {}
        self.last_entry_4h_time_ms: dict[str, int] = {}

        # Charged settlement window IDs to prevent double charge: (symbol, settlement_time_ms)
        self.charged_settlements: set[tuple[str, int]] = set()

        # Equity curve time series for diagnostics
        self.equity_history: list[tuple[int, Decimal]] = []

    def get_symbol_filter(self, symbol: str) -> SymbolFilters:
        return self.filters.get(
            symbol,
            SymbolFilters(symbol=symbol, tick_size=Decimal("0.01"), step_size=Decimal("0.001")),
        )

    # -------------------------------------------------------------------------
    # Sizing & Capital Allocation
    # -------------------------------------------------------------------------

    def compute_available_capital(self) -> Decimal:
        """
        Capital A = max(0, 0.95 * E_d - R_f - C_o)
        Preserves mandatory 5% equity reserve buffer.
        """
        admissible = Decimal("0.95") * self.decision_equity - self.funding_reserve_rf - self.cost_commitment_o
        return max(Decimal(0), admissible)

    def compute_asset_budget(self, symbol: str, available_capital: Decimal) -> Decimal:
        """
        Asset budget B = max(0, min(333.333333333333, A / 3, A - G))
        """
        gross_notional = sum(
            abs(pos.quantity) * self.last_available_marks.get(s, (pos.effective_entry, 0, 0))[0]
            for s, pos in self.positions.items()
        )
        remaining_capacity = available_capital - gross_notional
        b = min(ALLOCATION_CEILING_PER_ASSET_USDT, available_capital / Decimal(3), remaining_capacity)
        return max(Decimal(0), b)

    def calculate_order_sizing(
        self,
        signal: SignalEvent,
        max_hold_ms: int,
    ) -> VirtualOrder | None:
        """
        Compute order sizing, price bounds, and required reserves according to PIT contract.
        """
        if self.killed or self.insolvent:
            return None
        if signal.symbol in self.positions:
            return None
        # Check cooldown against decision availability timestamp (A07)
        if signal.available_at_ms < self.cooldown_until_ms.get(signal.symbol, 0):
            return None

        # Check mark freshness (age <= 120s from completed mark close time) (A06)
        mark_info = self.last_available_marks.get(signal.symbol)
        if mark_info is None:
            return None
        mark_price, mark_close_ms, _ = mark_info
        if (signal.decision_time_ms - mark_close_ms) > MARK_STALENESS_LIMIT_MS:
            return None

        capital_a = self.compute_available_capital()
        budget_b = self.compute_asset_budget(signal.symbol, capital_a)
        if budget_b <= Decimal(0):
            return None

        sym_filter = self.get_symbol_filter(signal.symbol)
        p = signal.decision_close
        atr = signal.hourly_atr20

        # Adverse entry-notional bound X
        x_raw = (p + MAX_GAP_ATR_FRACTION * atr) * (Decimal(1) + self.cost_model.friction_rate)
        x = round_to_tick(x_raw, sym_filter.tick_size, mode="ceil")

        # Exit reserve per unit
        c_exit = (
            RESERVE_BUFFER_MULTIPLIER * x * (self.cost_model.fee_rate + self.cost_model.friction_rate)
            + sym_filter.tick_size
        )

        # Entry fee reserve per unit
        c_entry = x * self.cost_model.fee_rate

        # Funding reserve per unit
        # Estimate intersecting hourly funding events during planned holding window
        planned_entry_ms = signal.earliest_entry_ms
        holding_hours = max_hold_ms // 3_600_000
        n_events = Decimal(max(1, holding_hours))
        f_unit = RESERVE_BUFFER_MULTIPLIER * mark_price * self.cost_model.funding_rate * n_events

        denominator = x + c_entry + c_exit + f_unit
        if denominator <= Decimal(0):
            return None

        raw_qty = budget_b / denominator
        qty = floor_to_lot(raw_qty, sym_filter.step_size)

        if qty <= Decimal(0):
            return None

        entry_notional = qty * x
        if entry_notional < sym_filter.min_notional:
            return None

        # Sizing risk distance checks
        preliminary_stop = self.cost_model.round_stop_level(signal.proposed_stop, signal.direction, sym_filter)
        risk_dist = abs(x - preliminary_stop)
        risk_bps = risk_dist / x
        if risk_bps < MIN_RISK_BPS or risk_bps > MAX_RISK_BPS:
            return None

        # Target calculation (2R)
        raw_target = x + (Decimal(signal.direction.sign) * Decimal("2.0") * risk_dist)
        target = self.cost_model.round_target_level(raw_target, signal.direction, sym_filter)

        cost_commitment = qty * (x + c_entry + c_exit)
        funding_reserve = qty * f_unit

        order_id = f"ORD_{signal.candidate_id}_{signal.symbol}_{planned_entry_ms}"
        return VirtualOrder(
            order_id=order_id,
            candidate_id=signal.candidate_id,
            symbol=signal.symbol,
            direction=signal.direction,
            quantity=qty,
            target_fill_time_ms=planned_entry_ms,
            created_at_ms=signal.available_at_ms,
            expected_entry_bound=x,
            initial_stop=preliminary_stop,
            target=target,
            cost_commitment_usdt=cost_commitment,
            funding_reserve_usdt=funding_reserve,
            decision_close=signal.decision_close,
            hourly_atr20=signal.hourly_atr20,
            retest_event_id=signal.event_id,
        )

    # -------------------------------------------------------------------------
    # Deterministic 8-Stage Execution Loop for Minute Open O
    # -------------------------------------------------------------------------

    def step_minute_open(
        self,
        open_time_ms: int,
        bars_1m: dict[str, Bar1m],
        marks_1m: dict[str, MarkBar1m],
        candidate_max_hold_ms: int,
        hourly_signal: SignalEvent | None = None,
    ) -> None:
        """Execute one complete minute open progression through the 8 stages."""

        # Stage 1: Available Messages (A03, A06)
        self._stage_1_available_messages(open_time_ms, marks_1m)

        # Stage 2: Account Risk & Mark Freshness
        self._stage_2_account_risk(open_time_ms)

        # Stage 3: Scheduling
        self._stage_3_scheduling(open_time_ms, hourly_signal, candidate_max_hold_ms)

        # Stage 4: Previously Due Exits
        self._stage_4_due_exits(open_time_ms, bars_1m)

        # Stage 5: Previously Due Entries
        self._stage_5_due_entries(open_time_ms, bars_1m, candidate_max_hold_ms)

        # Stage 6: Intraminute Protection (1m OHLCV checks)
        self._stage_6_intraminute_protection(open_time_ms, bars_1m, candidate_max_hold_ms)

        # Stage 7: Funding Ownership
        self._stage_7_funding_ownership(open_time_ms)

        # Stage 8: Ex-Post Report
        self._stage_8_ex_post_report(open_time_ms, marks_1m)

    def _stage_1_available_messages(
        self,
        open_time_ms: int,
        marks_1m: dict[str, MarkBar1m] | None = None,
    ) -> None:
        """Consume all messages with available_at_ms <= open_time_ms."""
        # Process available marks in Stage 1 (A06)
        if marks_1m:
            for sym, mbar in marks_1m.items():
                if mbar.available_at_ms <= open_time_ms and mbar.close_ms <= open_time_ms:
                    self.last_available_marks[sym] = (mbar.close, mbar.close_ms, mbar.available_at_ms)

        # Process available entry fills (A03)
        remaining_fills: list[VirtualFill] = []
        for fill in self.pending_fill_acks:
            if fill.available_at_ms <= open_time_ms:
                # Fill acknowledged: debit actual entry fee exactly once
                self.cash -= fill.fee_usdt
                # If position is active in self.positions, mark acknowledged
                pos = self.positions.get(fill.symbol)
                if pos is not None and pos.position_id == fill.fill_id:
                    pos.is_acknowledged = True
                # If position was already closed (e.g. SL/TP in Stage 6 of same minute),
                # it is tracked in self.closed_position_ids and must NEVER be resurrected as a zombie!
            else:
                remaining_fills.append(fill)
        self.pending_fill_acks = remaining_fills

        # Process available exit acks (A07, A08)
        remaining_exits: list[tuple[Any, ...]] = []
        for item in self.pending_exit_acks:
            if len(item) == 4:
                trade, ack_time, exit_reserve, rem_funding = item
            else:
                trade, ack_time = item[0], item[1]
                exit_reserve, rem_funding = Decimal(0), Decimal(0)

            if ack_time <= open_time_ms:
                # Realize cash delta:
                gross_pnl = trade.quantity * Decimal(trade.direction.sign) * (trade.effective_exit - trade.effective_entry)
                self.cash += gross_pnl - trade.exit_fee_usdt
                self.completed_trades.append(trade)
                # Release exit commitment and remaining funding reserve
                self.cost_commitment_o -= exit_reserve
                self.funding_reserve_rf -= rem_funding
                # Cooldown starts from ceil_to_minute(economic_exit_at) + COOLDOWN_DURATION_MS (A07)
                ceil_exit_ms = ((trade.exit_time_ms + 59_999) // 60_000) * 60_000
                self.cooldown_until_ms[trade.symbol] = ceil_exit_ms + COOLDOWN_DURATION_MS
            else:
                remaining_exits.append(item)
        self.pending_exit_acks = remaining_exits

        # Process available funding charges
        remaining_funding: list[FundingEventRecord] = []
        for f_rec in self.pending_funding_acks:
            if f_rec.available_at_ms <= open_time_ms:
                self.cash -= f_rec.cashflow_debit_usdt
                self.funding_charges.append(f_rec)
            else:
                remaining_funding.append(f_rec)
        self.pending_funding_acks = remaining_funding

    def _stage_2_account_risk(
        self,
        open_time_ms: int,
        marks_1m: dict[str, MarkBar1m] | None = None,
    ) -> None:
        """Value acknowledged positions, verify mark freshness, and check drawdown kill."""
        # Note: Mark updates processed in Stage 1 per specification (A06).

        # Check mark freshness for active symbols (A06: uses mark close timestamp)
        for sym in list(self.positions.keys()):
            mark_info = self.last_available_marks.get(sym)
            if (
                mark_info is None or (open_time_ms - mark_info[1]) > MARK_STALENESS_LIMIT_MS
            ) and not any(e[0] == sym and e[1] == ExitReason.MARK_STALENESS for e in self.due_exits):
                self.due_exits.append((sym, ExitReason.MARK_STALENESS, open_time_ms + 60_000))

        # Value acknowledged positions
        unrealized_pnl = Decimal(0)
        for sym, pos in self.positions.items():
            mark_price = self.last_available_marks.get(sym, (pos.effective_entry, 0, 0))[0]
            unrealized_pnl += pos.quantity * Decimal(pos.direction.sign) * (mark_price - pos.effective_entry)

        self.decision_equity = self.cash + unrealized_pnl

        # Update high-water mark
        self.high_water_equity = max(self.high_water_equity, self.decision_equity)

        # Peak-to-trough decision drawdown latch
        drawdown = self.high_water_equity - self.decision_equity
        if not self.killed:
            if self.decision_equity <= Decimal(0):
                self.killed = True
                self.insolvent = True
                self.kill_reason = "INSOLVENCY_ZERO_OR_NEGATIVE_EQUITY"
                self.kill_latched_at_ms = open_time_ms
                self._trigger_kill_liquidation(open_time_ms)
            elif drawdown >= DRAWDOWN_KILL_THRESHOLD_USDT:
                self.killed = True
                self.kill_reason = f"DRAWDOWN_LIMIT_EXCEEDED_{drawdown:.2f}_USDT"
                self.kill_latched_at_ms = open_time_ms
                self._trigger_kill_liquidation(open_time_ms)

    def _trigger_kill_liquidation(self, open_time_ms: int) -> None:
        """On kill latch, cancel pending commitments and queue immediate liquidation."""
        self.pending_orders.clear()
        self.cost_commitment_o = Decimal(0)
        self.funding_reserve_rf = Decimal(0)
        for sym in self.positions:
            if not any(e[0] == sym and e[1] == ExitReason.DRAWDOWN_KILL for e in self.due_exits):
                self.due_exits.append((sym, ExitReason.DRAWDOWN_KILL, open_time_ms + 60_000))

    def _stage_3_scheduling(
        self,
        open_time_ms: int,
        hourly_signal: SignalEvent | None,
        candidate_max_hold_ms: int,
    ) -> None:
        """Schedule future entries or reductions."""
        if self.killed or self.insolvent:
            self.pending_orders.clear()
            return

        if hourly_signal is not None and hourly_signal.available_at_ms <= open_time_ms:
            # Sizing and scheduling
            order = self.calculate_order_sizing(hourly_signal, candidate_max_hold_ms)
            if order is not None:
                self.pending_orders.append(order)
                self.cost_commitment_o += order.cost_commitment_usdt
                self.funding_reserve_rf += order.funding_reserve_usdt

    def _stage_4_due_exits(
        self,
        open_time_ms: int,
        bars_1m: dict[str, Bar1m],
    ) -> None:
        """Process exits that became due at or before open_time_ms."""
        ready_exits = [e for e in self.due_exits if e[2] <= open_time_ms]
        if not ready_exits:
            return

        # Canonical execution of due exits
        processed_exits: list[tuple[str, ExitReason, int]] = []
        for exit_item in ready_exits:
            sym, reason, _ = exit_item
            pos = self.positions.get(sym)
            bar = bars_1m.get(sym)
            if pos is None or bar is None:
                continue

            sym_filter = self.get_symbol_filter(sym)
            raw_open = bar.open
            is_buy_exit = (pos.direction == Direction.SHORT)

            # Cap favorable gap TP at target price
            if reason == ExitReason.TAKE_PROFIT:
                if pos.direction == Direction.LONG:
                    raw_exit = min(raw_open, pos.target)
                else:
                    raw_exit = max(raw_open, pos.target)
            elif reason == ExitReason.STOP_LOSS:
                # Adverse gap stop uses worse open
                if pos.direction == Direction.LONG:
                    raw_exit = min(raw_open, pos.stop)
                else:
                    raw_exit = max(raw_open, pos.stop)
            else:
                raw_exit = raw_open

            effective_exit = self.cost_model.model_execution_price(raw_exit, is_buy_exit, sym_filter)
            exit_notional = pos.quantity * effective_exit
            exit_fee = self.cost_model.compute_taker_fee(exit_notional)

            # Remove position from active book immediately (A03, A07)
            del self.positions[sym]
            self.closed_position_ids.add(pos.position_id)
            self.last_economic_exit_time_ms[sym] = open_time_ms
            ceil_exit_ms = ((open_time_ms + 59_999) // 60_000) * 60_000
            self.cooldown_until_ms[sym] = ceil_exit_ms + COOLDOWN_DURATION_MS
            processed_exits.append(exit_item)

            # Build completed trade
            entry_notional = pos.quantity * pos.effective_entry
            gross_pnl = pos.quantity * Decimal(pos.direction.sign) * (effective_exit - pos.effective_entry)
            total_fees = self.cost_model.compute_taker_fee(entry_notional) + exit_fee
            net_pnl = gross_pnl - total_fees - pos.total_funding_charged_usdt

            initial_risk_dollars = pos.quantity * abs(pos.effective_entry - pos.stop)
            net_bps = (net_pnl / entry_notional) * Decimal(10000) if entry_notional > Decimal(0) else Decimal(0)
            net_r = (net_pnl / initial_risk_dollars) if initial_risk_dollars > Decimal(0) else None

            holding_min = (open_time_ms - pos.entry_time_ms) // 60_000

            trade = CompletedTrade(
                trade_id=f"TRD_{pos.position_id}_{open_time_ms}",
                candidate_id=pos.candidate_id,
                symbol=sym,
                direction=pos.direction,
                quantity=pos.quantity,
                effective_entry=pos.effective_entry,
                raw_entry=pos.effective_entry,
                effective_exit=effective_exit,
                raw_exit=raw_exit,
                entry_time_ms=pos.entry_time_ms,
                exit_time_ms=open_time_ms,
                holding_minutes=holding_min,
                exit_reason=reason,
                entry_fee_usdt=self.cost_model.compute_taker_fee(entry_notional),
                exit_fee_usdt=exit_fee,
                total_fees_usdt=total_fees,
                total_funding_usdt=pos.total_funding_charged_usdt,
                gross_pnl_usdt=gross_pnl,
                net_pnl_usdt=net_pnl,
                entry_notional_usdt=entry_notional,
                initial_risk_dollars=initial_risk_dollars,
                net_bps=net_bps,
                net_r=net_r,
                retest_event_id=pos.retest_event_id,
            )

            # Exit acknowledgment available at open_time_ms + 60s, carrying exit and funding reserves (A08)
            self.pending_exit_acks.append((trade, open_time_ms + 60_000, pos.cost_commitment_exit_usdt, pos.funding_reserves_usdt))

        # Clear processed exits
        self.due_exits = [e for e in self.due_exits if e not in processed_exits]

    def _stage_5_due_entries(
        self,
        open_time_ms: int,
        bars_1m: dict[str, Bar1m],
        candidate_max_hold_ms: int,
    ) -> None:
        """Process entries due at open_time_ms in canonical BTCUSDT, ETHUSDT, SOLUSDT order."""
        if self.killed or self.insolvent:
            self.pending_orders.clear()
            return

        canonical_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        orders_by_sym = {o.symbol: o for o in self.pending_orders if o.target_fill_time_ms == open_time_ms}

        for sym in canonical_symbols:
            order = orders_by_sym.get(sym)
            if order is None:
                continue

            self.pending_orders.remove(order)

            bar = bars_1m.get(sym)
            if bar is None or bar.volume <= Decimal(0):
                # No fill / missing bar -> veto, release all commitments
                self.cost_commitment_o -= order.cost_commitment_usdt
                self.funding_reserve_rf -= order.funding_reserve_usdt
                continue

            # Gap check: absolute gap from decision close > 0.25 ATR20 is vetoed
            if order.hourly_atr20 > Decimal(0):
                gap_dist = abs(bar.open - order.decision_close)
                if gap_dist > MAX_GAP_ATR_FRACTION * order.hourly_atr20:
                    # Gap veto: entry rejected, release commitments
                    self.cost_commitment_o -= order.cost_commitment_usdt
                    self.funding_reserve_rf -= order.funding_reserve_usdt
                    continue

            sym_filter = self.get_symbol_filter(sym)
            is_buy = (order.direction == Direction.LONG)
            effective_entry = self.cost_model.model_execution_price(bar.open, is_buy, sym_filter)

            # Round standing stop adversely toward entry
            stop = self.cost_model.round_stop_level(order.initial_stop, order.direction, sym_filter)
            risk_dist = abs(effective_entry - stop)
            risk_bps = risk_dist / effective_entry
            if risk_bps < MIN_RISK_BPS or risk_bps > MAX_RISK_BPS:
                # Risk filter violation at actual fill -> veto, release commitments
                self.cost_commitment_o -= order.cost_commitment_usdt
                self.funding_reserve_rf -= order.funding_reserve_usdt
                continue

            # Target (2R)
            raw_target = effective_entry + (Decimal(order.direction.sign) * Decimal("2.0") * risk_dist)
            target = self.cost_model.round_target_level(raw_target, order.direction, sym_filter)

            entry_notional = order.quantity * effective_entry
            entry_fee = self.cost_model.compute_taker_fee(entry_notional)

            # Exit reserve including tick_size * quantity buffer (A08)
            c_exit = (
                RESERVE_BUFFER_MULTIPLIER
                * effective_entry
                * (self.cost_model.fee_rate + self.cost_model.friction_rate)
                * order.quantity
                + sym_filter.tick_size * order.quantity
            )

            # Standing position is locked immediately with candidate max_hold_ms (A03)
            pos = Position(
                position_id=f"POS_{order.order_id}",
                candidate_id=order.candidate_id,
                symbol=sym,
                direction=order.direction,
                quantity=order.quantity,
                effective_entry=effective_entry,
                entry_time_ms=open_time_ms,
                entry_available_at_ms=open_time_ms + 60_000,
                stop=stop,
                target=target,
                max_hold_ms=candidate_max_hold_ms,
                cost_commitment_exit_usdt=c_exit,
                retest_event_id=order.retest_event_id,
                funding_reserves_usdt=order.funding_reserve_usdt,
                total_funding_charged_usdt=Decimal(0),
                is_acknowledged=False,
            )
            self.positions[sym] = pos

            # Release pending entry notional and fee, but retain exit commitment in cost_commitment_o (A08)
            pending_entry_released = order.cost_commitment_usdt - c_exit
            self.cost_commitment_o -= pending_entry_released
            # funding_reserve_rf remains reserved for open position pos.funding_reserves_usdt

            # Record entry 4h bucket for structural continuation dedup (A07)
            self.last_entry_4h_time_ms[sym] = (open_time_ms // 14_400_000) * 14_400_000

            # Create fill acknowledgment message available at open_time_ms + 60s
            fill = VirtualFill(
                fill_id=pos.position_id,
                order_id=order.order_id,
                candidate_id=order.candidate_id,
                symbol=sym,
                direction=order.direction,
                quantity=order.quantity,
                raw_price=bar.open,
                effective_price=effective_entry,
                fee_usdt=entry_fee,
                fill_time_ms=open_time_ms,
                available_at_ms=open_time_ms + 60_000,
                initial_stop=stop,
                target=target,
                retest_event_id=order.retest_event_id,
            )
            self.pending_fill_acks.append(fill)

    def _stage_6_intraminute_protection(
        self,
        open_time_ms: int,
        bars_1m: dict[str, Bar1m],
        candidate_max_hold_ms: int,
    ) -> None:
        """
        Evaluate 1m OHLCV for intrabar SL/TP touches.
        CRITICAL: If both stop and target are touched, SL resolves first!
        Adverse stop gap uses worse open.
        """
        for sym, pos in list(self.positions.items()):
            bar = bars_1m.get(sym)
            if bar is None:
                continue

            sl_hit = False
            tp_hit = False

            if pos.direction == Direction.LONG:
                if bar.low <= pos.stop:
                    sl_hit = True
                if bar.high >= pos.target:
                    tp_hit = True
            else:  # SHORT
                if bar.high >= pos.stop:
                    sl_hit = True
                if bar.low <= pos.target:
                    tp_hit = True

            # Check timeout / expiry
            expiry_hit = (open_time_ms + 60_000 >= pos.entry_time_ms + pos.max_hold_ms)

            # SL dominates TP collision
            if sl_hit:
                # Intraminute stop loss triggered
                sym_filter = self.get_symbol_filter(sym)
                is_buy_exit = (pos.direction == Direction.SHORT)

                # Worse open for adverse stop gap
                if pos.direction == Direction.LONG:
                    raw_exit = min(bar.open, pos.stop)
                else:
                    raw_exit = max(bar.open, pos.stop)

                effective_exit = self.cost_model.model_execution_price(raw_exit, is_buy_exit, sym_filter)
                self._record_closed_position(pos, effective_exit, raw_exit, ExitReason.STOP_LOSS, open_time_ms + 60_000, economic_exit_ms=open_time_ms)
                del self.positions[sym]

            elif tp_hit:
                # Take profit triggered (fixed target price, no overcredit)
                sym_filter = self.get_symbol_filter(sym)
                is_buy_exit = (pos.direction == Direction.SHORT)
                raw_exit = pos.target
                effective_exit = self.cost_model.model_execution_price(raw_exit, is_buy_exit, sym_filter)
                self._record_closed_position(pos, effective_exit, raw_exit, ExitReason.TAKE_PROFIT, open_time_ms + 60_000, economic_exit_ms=open_time_ms)
                del self.positions[sym]

            elif expiry_hit:
                # Schedule expiry exit for the following open
                if not any(e[0] == sym and e[1] == ExitReason.EXPIRY for e in self.due_exits):
                    self.due_exits.append((sym, ExitReason.EXPIRY, open_time_ms + 60_000))

    def _record_closed_position(
        self,
        pos: Position,
        effective_exit: Decimal,
        raw_exit: Decimal,
        reason: ExitReason,
        ack_available_at_ms: int,
        economic_exit_ms: int | None = None,
    ) -> None:
        """Helper to create CompletedTrade and queue its acknowledgment."""
        econ_exit = economic_exit_ms if economic_exit_ms is not None else (ack_available_at_ms - 60_000)
        self.closed_position_ids.add(pos.position_id)
        self.last_economic_exit_time_ms[pos.symbol] = econ_exit
        ceil_exit_ms = ((econ_exit + 59_999) // 60_000) * 60_000
        self.cooldown_until_ms[pos.symbol] = ceil_exit_ms + COOLDOWN_DURATION_MS

        entry_notional = pos.quantity * pos.effective_entry
        exit_fee = self.cost_model.compute_taker_fee(pos.quantity * effective_exit)
        gross_pnl = pos.quantity * Decimal(pos.direction.sign) * (effective_exit - pos.effective_entry)
        entry_fee = self.cost_model.compute_taker_fee(entry_notional)
        total_fees = entry_fee + exit_fee
        net_pnl = gross_pnl - total_fees - pos.total_funding_charged_usdt

        initial_risk_dollars = pos.quantity * abs(pos.effective_entry - pos.stop)
        net_bps = (net_pnl / entry_notional) * Decimal(10000) if entry_notional > Decimal(0) else Decimal(0)
        net_r = (net_pnl / initial_risk_dollars) if initial_risk_dollars > Decimal(0) else None
        holding_min = (econ_exit - pos.entry_time_ms) // 60_000

        trade = CompletedTrade(
            trade_id=f"TRD_{pos.position_id}_{econ_exit}",
            candidate_id=pos.candidate_id,
            symbol=pos.symbol,
            direction=pos.direction,
            quantity=pos.quantity,
            effective_entry=pos.effective_entry,
            raw_entry=pos.effective_entry,
            effective_exit=effective_exit,
            raw_exit=raw_exit,
            entry_time_ms=pos.entry_time_ms,
            exit_time_ms=econ_exit,
            holding_minutes=holding_min,
            exit_reason=reason,
            entry_fee_usdt=entry_fee,
            exit_fee_usdt=exit_fee,
            total_fees_usdt=total_fees,
            total_funding_usdt=pos.total_funding_charged_usdt,
            gross_pnl_usdt=gross_pnl,
            net_pnl_usdt=net_pnl,
            entry_notional_usdt=entry_notional,
            initial_risk_dollars=initial_risk_dollars,
            net_bps=net_bps,
            net_r=net_r,
            retest_event_id=pos.retest_event_id,
        )
        self.pending_exit_acks.append((trade, ack_available_at_ms, pos.cost_commitment_exit_usdt, pos.funding_reserves_usdt))

    def _stage_7_funding_ownership(self, open_time_ms: int) -> None:
        """
        Funding settlements occur on whole UTC hours S.
        Ownership window is [S - 15000ms, S + 15000ms].
        Charge each settlement ID once per position.
        """
        # Determine if this minute intersects a whole UTC hour
        # S is the nearest hour
        minute_start = open_time_ms
        minute_end = open_time_ms + 60_000

        # Hourly boundary in this minute:
        hour_s = (minute_start // 3_600_000) * 3_600_000
        if minute_start <= hour_s < minute_end or minute_start <= hour_s + 3_600_000 < minute_end:
            target_s = hour_s if (minute_start <= hour_s < minute_end) else (hour_s + 3_600_000)
            window_start = target_s - FUNDING_OWNERSHIP_HALF_WINDOW_MS
            window_end = target_s + FUNDING_OWNERSHIP_HALF_WINDOW_MS

            # Check overlap with [minute_start, minute_end]
            if max(minute_start, window_start) <= min(minute_end, window_end):
                for sym, pos in self.positions.items():
                    key = (sym, target_s)
                    if key in self.charged_settlements:
                        continue
                    self.charged_settlements.add(key)

                    # Charge funding
                    mark_price = self.last_available_marks.get(sym, (pos.effective_entry, 0, 0))[0]
                    debit = self.cost_model.compute_funding_charge(pos.quantity, mark_price)
                    pos.total_funding_charged_usdt += debit
                    pos.funding_reserves_usdt = max(Decimal(0), pos.funding_reserves_usdt - debit)

                    f_rec = FundingEventRecord(
                        event_id=f"FUND_{sym}_{target_s}",
                        symbol=sym,
                        settlement_time_ms=target_s,
                        rate=self.cost_model.funding_rate,
                        settlement_mark=mark_price,
                        position_quantity=pos.quantity,
                        cashflow_debit_usdt=debit,
                        charged_at_ms=open_time_ms,
                        available_at_ms=target_s + 60_000,
                    )
                    self.pending_funding_acks.append(f_rec)

    def _stage_8_ex_post_report(
        self,
        open_time_ms: int,
        marks_1m: dict[str, MarkBar1m],
    ) -> None:
        """Record minute-close mark-to-market equity."""
        unrealized = Decimal(0)
        for sym, pos in self.positions.items():
            m_bar = marks_1m.get(sym)
            mark_price = m_bar.close if m_bar is not None else pos.effective_entry
            unrealized += pos.quantity * Decimal(pos.direction.sign) * (mark_price - pos.effective_entry)

        self.economic_equity = self.cash + unrealized
        self.equity_history.append((open_time_ms + 60_000, self.economic_equity))
