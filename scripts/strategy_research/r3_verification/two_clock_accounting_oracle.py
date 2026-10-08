"""Independent Two-Clock Accounting, Fill, Cost, Funding Ownership & Risk Supervisor Oracle."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from scripts.strategy_research.r3_verification.oracle_specs import (
    ADMISSIBLE_EQUITY_FRACTION,
    ALLOWLISTED_SYMBOLS,
    ARCHIVAL_AVAILABILITY_LAG_MS,
    BPS_DENOMINATOR,
    COOLDOWN_DURATION_MS,
    DRAWDOWN_KILL_THRESHOLD_USDT,
    FUNDING_OWNERSHIP_HALF_WINDOW_MS,
    INITIAL_EQUITY_USDT,
    MAX_ENTRY_GAP_ATR_FRACTION,
    MAX_MARK_EVENT_AGE_MS,
    MAX_RISK_BPS,
    MIN_RISK_BPS,
    ONE_MINUTE_MS,
    PER_ASSET_ALLOCATION_CEILING_USDT,
    SCENARIO_RESERVE_MULTIPLIER,
    STRESS_COST_SCENARIO,
    TARGET_RISK_MULTIPLE,
    VIRTUAL_ACK_DELAY_MS,
    BookSymbolState,
    CostScenario,
    FillAckSubPriority,
    MessageTypePriority,
    ceil_to_tick,
    decimal_context,
    floor_to_step,
    round_execution_price,
    round_ledger_usdt,
    round_stop_toward_entry,
    round_target_toward_entry,
)


@dataclass(frozen=True)
class SymbolFilterSpec:
    """Admitted or declared-proxy symbol filter parameters (never using integer precision as tick/step)."""

    symbol: str
    tick_size: Decimal
    lot_size: Decimal
    min_notional_usdt: Decimal = Decimal("5.0")
    product_multiplier: Decimal = Decimal(1)
    is_proxy: bool = True

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.symbol not in ALLOWLISTED_SYMBOLS:
            errors.append(f"UNALLOWLISTED_SYMBOL:{self.symbol}")
        with decimal_context():
            if self.tick_size <= Decimal(0):
                errors.append("NON_POSITIVE_TICK_SIZE")
            if self.lot_size <= Decimal(0):
                errors.append("NON_POSITIVE_LOT_SIZE")
            if self.min_notional_usdt <= Decimal(0):
                errors.append("NON_POSITIVE_MIN_NOTIONAL")
            if self.product_multiplier != Decimal(1):
                errors.append(f"UNSUPPORTED_PRODUCT_MULTIPLIER:{self.product_multiplier}")
        return errors


@dataclass(frozen=True)
class MarketBarMessage:
    """1-minute trade or mark bar input for a specific minute open_ms."""

    source_id: str
    symbol: str
    open_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal(1)
    is_mark: bool = False
    available_at_ms: int | None = None
    corrupted: bool = False

    @property
    def end_ms_exclusive(self) -> int:
        return self.open_ms + ONE_MINUTE_MS

    @property
    def event_at_ms(self) -> int:
        return self.end_ms_exclusive

    @property
    def effective_available_at_ms(self) -> int:
        if self.available_at_ms is not None:
            return self.available_at_ms
        return self.end_ms_exclusive + ARCHIVAL_AVAILABILITY_LAG_MS


@dataclass(frozen=True)
class SettlementWindow:
    """Funding settlement specification with inclusive [S - 15000, S + 15000] ownership window."""

    settlement_id: str
    symbol: str
    settlement_ms: int
    settlement_mark_price: Decimal
    actual_rate: Decimal
    admitted_rate_available_at_ms: int | None = None
    is_measured_schedule: bool = False

    @property
    def window_start_ms(self) -> int:
        return self.settlement_ms - FUNDING_OWNERSHIP_HALF_WINDOW_MS

    @property
    def window_end_ms(self) -> int:
        return self.settlement_ms + FUNDING_OWNERSHIP_HALF_WINDOW_MS

    @property
    def end_of_last_intersecting_minute_ms(self) -> int:
        last_min_open = (self.window_end_ms // ONE_MINUTE_MS) * ONE_MINUTE_MS
        return last_min_open + ONE_MINUTE_MS

    @property
    def ack_available_at_ms(self) -> int:
        base_avail = max(
            self.settlement_ms + VIRTUAL_ACK_DELAY_MS,
            self.end_of_last_intersecting_minute_ms + VIRTUAL_ACK_DELAY_MS,
        )
        if self.admitted_rate_available_at_ms is not None:
            return max(base_avail, self.admitted_rate_available_at_ms)
        return base_avail


@dataclass(frozen=True)
class OracleMessage:
    """Deterministically ordered message consumed by the Decision Ledger in Stage 1."""

    available_at_ms: int
    event_at_ms: int
    type_priority: MessageTypePriority
    sub_priority: int
    parent_order_id: str
    symbol: str
    source_id: str
    payload: dict[str, object]

    @property
    def sort_key(self) -> tuple[int, int, int, int, str, str, str]:
        return (
            self.available_at_ms,
            self.event_at_ms,
            int(self.type_priority),
            self.sub_priority,
            self.parent_order_id,
            self.symbol,
            self.source_id,
        )


@dataclass
class ReserveRecord:
    """Release-once commitment or funding reserve record."""

    reserve_id: str
    symbol: str
    kind: str  # "ENTRY_NOTIONAL_AND_FEE", "EXIT_COST", "FUNDING"
    amount_usdt: Decimal
    quantity: Decimal
    created_at_ms: int
    released: bool = False

    def release_once(self) -> Decimal:
        if self.released:
            raise RuntimeError(f"DOUBLE_RESERVE_RELEASE_ERROR:{self.reserve_id}")
        self.released = True
        return self.amount_usdt


@dataclass
class OrderRequest:
    """Scheduled entry, exit, or reduction order due no earlier than created_at_ms + 60000."""

    order_id: str
    symbol: str
    kind: str  # "ENTRY", "KILL_EXIT", "PRO_RATA_REDUCTION", "STALE_MARK_EXIT", "ORDINARY_EXIT"
    direction: int
    quantity: Decimal
    created_at_ms: int
    due_at_ms: int
    decision_close: Decimal = Decimal(0)
    atr20: Decimal = Decimal(0)
    raw_stop: Decimal = Decimal(0)
    max_hold_ms: int = 0
    entry_reserve_id: str | None = None
    exit_reserve_id: str | None = None
    funding_reserve_id: str | None = None
    retest_event_id: str | None = None
    reason: str = ""


@dataclass
class PositionRecord:
    """Economic or acknowledged position state for a single symbol."""

    position_id: str
    symbol: str
    direction: int
    quantity: Decimal
    raw_entry_price: Decimal
    effective_entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    initial_stop_risk_dollars_per_unit: Decimal
    entry_at_ms: int
    max_hold_ms: int
    exit_reserve_id: str | None = None
    funding_reserve_id: str | None = None
    accumulated_entry_fee_usdt: Decimal = Decimal(0)
    accumulated_exit_fee_usdt: Decimal = Decimal(0)
    accumulated_funding_usdt: Decimal = Decimal(0)


@dataclass(frozen=True)
class TradeOutcomeSummary:
    """Reconciled trade or reduction outcome with separate gross, friction, fee, funding, bps, and R."""

    trade_id: str
    position_id: str
    symbol: str
    direction: int
    quantity: Decimal
    entry_at_ms: int
    exit_at_ms: int
    exit_reason: str
    raw_entry_price: Decimal
    effective_entry_price: Decimal
    raw_exit_price: Decimal
    effective_exit_price: Decimal
    entry_notional_usdt: Decimal
    gross_quote_pnl_usdt: Decimal
    execution_drag_usdt: Decimal
    effective_quote_pnl_usdt: Decimal
    entry_fee_usdt: Decimal
    exit_fee_usdt: Decimal
    funding_cashflow_usdt: Decimal
    net_pnl_usdt: Decimal
    gross_bps: Decimal
    net_bps: Decimal
    initial_risk_dollars_usdt: Decimal
    net_r: Decimal | None
    account_equity_return_delta: Decimal


@dataclass
class ExposureInterval:
    """Economic exposure interval [start_ms, end_ms] for bounded funding ownership checks."""

    position_id: str
    symbol: str
    direction: int
    start_ms: int
    end_ms: int | None
    pre_quantity: Decimal
    post_quantity: Decimal
    entry_price: Decimal


@dataclass
class IndependentBookOracle:
    """Isolated 1,000-USDT virtual book implementing the R1.1 two-clock 8-stage contract."""

    book_id: str
    cost_scenario: CostScenario = STRESS_COST_SCENARIO
    filters: dict[str, SymbolFilterSpec] = field(default_factory=dict)

    # Decision ledger (E_d) state
    acknowledged_cash_usdt: Decimal = INITIAL_EQUITY_USDT
    acknowledged_positions: dict[str, PositionRecord] = field(default_factory=dict)
    last_available_marks: dict[str, tuple[Decimal, int, int]] = field(
        default_factory=dict
    )  # symbol -> (close, event_at_ms, available_at_ms)
    decision_high_water_usdt: Decimal = INITIAL_EQUITY_USDT
    kill_latched: bool = False
    decision_insolvency_latched: bool = False
    source_blocked: bool = False
    source_blocked_reason: str | None = None

    # Economic ledger (E_e) state
    economic_cash_usdt: Decimal = INITIAL_EQUITY_USDT
    economic_positions: dict[str, PositionRecord] = field(default_factory=dict)
    economic_marks: dict[str, Decimal] = field(default_factory=dict)
    economic_high_water_usdt: Decimal = INITIAL_EQUITY_USDT
    economic_max_drawdown_usdt: Decimal = Decimal(0)
    economically_insolvent: bool = False
    true_economic_leverage_breach: bool = False

    # State machine, message bus, reserves, orders, cooldowns, and audit logs
    symbol_states: dict[str, BookSymbolState] = field(
        default_factory=lambda: {s: BookSymbolState.FLAT for s in ALLOWLISTED_SYMBOLS}
    )
    cooldown_until_ms: dict[str, int] = field(default_factory=dict)
    consumed_retest_events: set[str] = field(default_factory=set)
    seen_message_ids: set[str] = field(default_factory=set)
    pending_messages: list[OracleMessage] = field(default_factory=list)
    reserves: dict[str, ReserveRecord] = field(default_factory=dict)
    due_orders: list[OrderRequest] = field(default_factory=list)
    exposure_intervals: list[ExposureInterval] = field(default_factory=list)
    charged_settlement_ids: set[str] = field(default_factory=set)
    completed_trades: list[TradeOutcomeSummary] = field(default_factory=list)
    wait_and_veto_log: list[dict[str, object]] = field(default_factory=list)
    reserve_shortfalls: list[dict[str, object]] = field(default_factory=list)
    stage_audit_log: list[dict[str, object]] = field(default_factory=list)
    _seq: int = 0

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{self.book_id}_{prefix}_{self._seq:06d}"

    def enqueue_message(self, msg: OracleMessage) -> None:
        """Enqueue a source or virtual acknowledgment message; reject duplicate source_ids."""
        if msg.source_id in self.seen_message_ids:
            self.source_blocked = True
            self.source_blocked_reason = f"DUPLICATE_MESSAGE_ID:{msg.source_id}"
            raise ValueError(self.source_blocked_reason)
        self.seen_message_ids.add(msg.source_id)
        self.pending_messages.append(msg)

    def compute_decision_equity(self) -> Decimal:
        """Compute E_d = acknowledged_cash + unrealized_MTM(acknowledged_positions, last_available_mark)."""
        with decimal_context():
            unrealized = Decimal(0)
            for sym, pos in self.acknowledged_positions.items():
                mark_info = self.last_available_marks.get(sym)
                mark_price = mark_info[0] if mark_info is not None else pos.effective_entry_price
                unrealized += (
                    pos.quantity
                    * Decimal(pos.direction)
                    * (mark_price - pos.effective_entry_price)
                )
            return round_ledger_usdt(self.acknowledged_cash_usdt + unrealized)

    def compute_economic_equity(self) -> Decimal:
        """Compute E_e = economic_cash + unrealized_MTM(economic_positions, current_minute_mark)."""
        with decimal_context():
            unrealized = Decimal(0)
            for sym, pos in self.economic_positions.items():
                mark_price = self.economic_marks.get(sym, pos.effective_entry_price)
                unrealized += (
                    pos.quantity
                    * Decimal(pos.direction)
                    * (mark_price - pos.effective_entry_price)
                )
            return round_ledger_usdt(self.economic_cash_usdt + unrealized)

    def compute_acknowledged_gross_notional(self) -> Decimal:
        """Compute G = sum(abs(q_ack) * last_available_mark)."""
        with decimal_context():
            gross = Decimal(0)
            for sym, pos in self.acknowledged_positions.items():
                mark_info = self.last_available_marks.get(sym)
                mark_price = mark_info[0] if mark_info is not None else pos.effective_entry_price
                gross += abs(pos.quantity) * mark_price
            return round_ledger_usdt(gross)

    def compute_economic_gross_notional(self) -> Decimal:
        """Compute ex-post economic gross notional at current minute mark."""
        with decimal_context():
            gross = Decimal(0)
            for sym, pos in self.economic_positions.items():
                mark_price = self.economic_marks.get(sym, pos.effective_entry_price)
                gross += abs(pos.quantity) * mark_price
            return round_ledger_usdt(gross)

    def compute_outstanding_reserves(self) -> tuple[Decimal, Decimal]:
        """Return (C_o, R_f): pending order/cost commitments C_o and adverse funding reserves R_f."""
        with decimal_context():
            c_o = Decimal(0)
            r_f = Decimal(0)
            for res in self.reserves.values():
                if res.released:
                    continue
                if res.kind in ("ENTRY_NOTIONAL_AND_FEE", "EXIT_COST"):
                    c_o += res.amount_usdt
                elif res.kind == "FUNDING":
                    r_f += res.amount_usdt
            return round_ledger_usdt(c_o), round_ledger_usdt(r_f)

    def compute_admissible_capital_a(self) -> Decimal:
        """Compute A = max(0, 0.95 * E_d - R_f - C_o)."""
        with decimal_context():
            e_d = self.compute_decision_equity()
            c_o, r_f = self.compute_outstanding_reserves()
            raw_a = ADMISSIBLE_EQUITY_FRACTION * e_d - r_f - c_o
            return round_ledger_usdt(max(Decimal(0), raw_a))

    def size_and_reserve_entry(
        self,
        *,
        symbol: str,
        direction: int,
        decision_at_ms: int,
        decision_close: Decimal,
        atr20: Decimal,
        raw_stop: Decimal,
        max_hold_ms: int,
        settlement_events_in_hold: int,
        snapshot_a: Decimal | None = None,
        residual_a_minus_g: Decimal | None = None,
        retest_event_id: str | None = None,
    ) -> OrderRequest | None:
        """Size an entry using R1.1 closed reserve equations and create release-once reserves."""
        if self.kill_latched or self.decision_insolvency_latched or self.source_blocked:
            self.wait_and_veto_log.append(
                {"symbol": symbol, "at_ms": decision_at_ms, "reason": "BOOK_DISABLED_OR_BLOCKED"}
            )
            return None

        sym_state = self.symbol_states.get(symbol, BookSymbolState.FLAT)
        if sym_state == BookSymbolState.COOLDOWN:
            cd_end = self.cooldown_until_ms.get(symbol, 0)
            if decision_at_ms >= cd_end:
                self.symbol_states[symbol] = BookSymbolState.FLAT
                sym_state = BookSymbolState.FLAT
        if sym_state != BookSymbolState.FLAT:
            self.wait_and_veto_log.append(
                {
                    "symbol": symbol,
                    "at_ms": decision_at_ms,
                    "reason": f"SYMBOL_NOT_FLAT:{sym_state.name}",
                }
            )
            return None

        flt = self.filters.get(symbol)
        if flt is None or flt.validate():
            self.wait_and_veto_log.append(
                {"symbol": symbol, "at_ms": decision_at_ms, "reason": "SOURCE_OR_FILTER_UNVERIFIED"}
            )
            return None

        mark_info = self.last_available_marks.get(symbol)
        if mark_info is None:
            self.wait_and_veto_log.append(
                {"symbol": symbol, "at_ms": decision_at_ms, "reason": "MISSING_AVAILABLE_MARK"}
            )
            return None
        latest_mark, mark_event_ms, _ = mark_info
        if decision_at_ms - mark_event_ms > MAX_MARK_EVENT_AGE_MS:
            self.wait_and_veto_log.append(
                {"symbol": symbol, "at_ms": decision_at_ms, "reason": "STALE_MARK_VETO"}
            )
            return None

        with decimal_context():
            if (
                decision_close <= Decimal(0)
                or atr20 <= Decimal(0)
                or latest_mark <= Decimal(0)
                or settlement_events_in_hold < 0
            ):
                self.wait_and_veto_log.append(
                    {"symbol": symbol, "at_ms": decision_at_ms, "reason": "COST_OR_PRICE_UNVERIFIED"}
                )
                return None

            a_cap = self.compute_admissible_capital_a() if snapshot_a is None else snapshot_a
            g_ack = self.compute_acknowledged_gross_notional()
            rem_cap = (a_cap - g_ack) if residual_a_minus_g is None else residual_a_minus_g
            budget_b = max(
                Decimal(0),
                min(PER_ASSET_ALLOCATION_CEILING_USDT, a_cap / Decimal(3), rem_cap),
            )
            if budget_b <= Decimal(0):
                self.wait_and_veto_log.append(
                    {"symbol": symbol, "at_ms": decision_at_ms, "reason": "ZERO_RESIDUAL_BUDGET_WAIT"}
                )
                return None

            # X = ceil_to_tick((P + 0.25*ATR) * (1 + (spread_bp + slip_bp)/10000))
            friction_rate = self.cost_scenario.execution_friction_bps_per_leg / BPS_DENOMINATOR
            fee_rate = self.cost_scenario.taker_fee_bps_per_leg / BPS_DENOMINATOR
            one_way_rate = self.cost_scenario.total_one_way_bps / BPS_DENOMINATOR
            adverse_fund_rate = (
                self.cost_scenario.funding_proxy_bps_per_event / BPS_DENOMINATOR
            )

            x_bound = ceil_to_tick(
                (decision_close + MAX_ENTRY_GAP_ATR_FRACTION * atr20)
                * (Decimal(1) + friction_rate),
                flt.tick_size,
            )
            c_entry = x_bound * fee_rate
            c_exit = SCENARIO_RESERVE_MULTIPLIER * x_bound * one_way_rate + flt.tick_size
            f_unit = (
                SCENARIO_RESERVE_MULTIPLIER
                * latest_mark
                * adverse_fund_rate
                * Decimal(settlement_events_in_hold)
            )
            unit_denom = x_bound + c_entry + c_exit + f_unit
            if unit_denom <= Decimal(0):
                self.wait_and_veto_log.append(
                    {"symbol": symbol, "at_ms": decision_at_ms, "reason": "INVALID_SIZING_DENOMINATOR"}
                )
                return None

            qty = floor_to_step(budget_b / unit_denom, flt.lot_size)
            provisional_notional = qty * x_bound
            if qty <= Decimal(0) or provisional_notional < flt.min_notional_usdt:
                self.wait_and_veto_log.append(
                    {"symbol": symbol, "at_ms": decision_at_ms, "reason": "MIN_LOT_OR_NOTIONAL_VETO"}
                )
                return None

            if provisional_notional > rem_cap:
                self.wait_and_veto_log.append(
                    {"symbol": symbol, "at_ms": decision_at_ms, "reason": "EXCEEDS_RESIDUAL_CAPITAL"}
                )
                return None

            entry_res_id = self._next_id("RES_ENTRY")
            exit_res_id = self._next_id("RES_EXIT")
            fund_res_id = self._next_id("RES_FUND")

            self.reserves[entry_res_id] = ReserveRecord(
                reserve_id=entry_res_id,
                symbol=symbol,
                kind="ENTRY_NOTIONAL_AND_FEE",
                amount_usdt=round_ledger_usdt(qty * (x_bound + c_entry)),
                quantity=qty,
                created_at_ms=decision_at_ms,
            )
            self.reserves[exit_res_id] = ReserveRecord(
                reserve_id=exit_res_id,
                symbol=symbol,
                kind="EXIT_COST",
                amount_usdt=round_ledger_usdt(qty * c_exit),
                quantity=qty,
                created_at_ms=decision_at_ms,
            )
            self.reserves[fund_res_id] = ReserveRecord(
                reserve_id=fund_res_id,
                symbol=symbol,
                kind="FUNDING",
                amount_usdt=round_ledger_usdt(qty * f_unit),
                quantity=qty,
                created_at_ms=decision_at_ms,
            )

            self.symbol_states[symbol] = BookSymbolState.ENTRY_PENDING
            if retest_event_id is not None:
                self.consumed_retest_events.add(retest_event_id)

            order = OrderRequest(
                order_id=self._next_id("ORD_ENTRY"),
                symbol=symbol,
                kind="ENTRY",
                direction=direction,
                quantity=qty,
                created_at_ms=decision_at_ms,
                due_at_ms=decision_at_ms + ONE_MINUTE_MS,
                decision_close=decision_close,
                atr20=atr20,
                raw_stop=raw_stop,
                max_hold_ms=max_hold_ms,
                entry_reserve_id=entry_res_id,
                exit_reserve_id=exit_res_id,
                funding_reserve_id=fund_res_id,
                retest_event_id=retest_event_id,
                reason="SCHEDULED_SIGNAL_ENTRY",
            )
            self.due_orders.append(order)
            return order

    def step_minute_open(
        self,
        open_ms: int,
        *,
        trade_bars_at_open: dict[str, MarketBarMessage] | None = None,
        mark_bars_at_open: dict[str, MarketBarMessage] | None = None,
        scheduled_entry_specs: Sequence[dict[str, object]] | None = None,
        settlements_to_check: Sequence[SettlementWindow] | None = None,
    ) -> dict[str, object]:
        """Execute all 8 deterministic R1.1 stages at minute open `open_ms`."""
        trade_bars = trade_bars_at_open or {}
        mark_bars = mark_bars_at_open or {}
        entry_specs = scheduled_entry_specs or ()
        settlements = settlements_to_check or ()

        # Stage 1: Consume available messages with available_at_ms <= open_ms
        stage1_consumed = self._stage1_consume_available_messages(open_ms)

        # Stage 2: Account risk (mark staleness, E_d update, high-water, >=100 USDT kill latch)
        stage2_risk = self._stage2_account_risk(open_ms)

        # Stage 3: Scheduling (cancel entries on kill/staleness, 1x reductions, new entries for O+60000)
        stage3_sched = self._stage3_scheduling(open_ms, entry_specs)

        # Stage 4: Previously due exits (kill -> pro-rata reduction -> ordinary gap-SL/gap-TP/expiry)
        exited_symbols_at_open, stage4_exits = self._stage4_execute_due_exits(open_ms, trade_bars)

        # Stage 5: Previously due entries (canonical BTCUSDT, ETHUSDT, SOLUSDT order)
        stage5_entries = self._stage5_execute_due_entries(
            open_ms, trade_bars, exited_symbols_at_open
        )

        # Stage 6: Intraminute protection (SL before TP if both touch; adverse stop gap; capped TP)
        stage6_intrabar = self._stage6_intraminute_protection(
            open_ms, trade_bars, exited_symbols_at_open
        )

        # Stage 7: Funding ownership (bounded [S-15000, S+15000] window, charge once, max(pre,post))
        stage7_funding = self._stage7_funding_ownership(open_ms, settlements)

        # Stage 8: Ex-post economic report and emission of delayed mark bars at T+60000
        stage8_report = self._stage8_ex_post_report(open_ms, trade_bars, mark_bars)

        summary = {
            "open_ms": open_ms,
            "stage1_consumed_count": len(stage1_consumed),
            "stage2_risk": stage2_risk,
            "stage3_scheduled": stage3_sched,
            "stage4_exits": stage4_exits,
            "stage5_entries": stage5_entries,
            "stage6_intrabar_exits": stage6_intrabar,
            "stage7_funding": stage7_funding,
            "stage8_report": stage8_report,
        }
        self.stage_audit_log.append(summary)
        return summary

    def _stage1_consume_available_messages(self, open_ms: int) -> list[OracleMessage]:
        ready = [m for m in self.pending_messages if m.available_at_ms <= open_ms]
        self.pending_messages = [
            m for m in self.pending_messages if m.available_at_ms > open_ms
        ]
        ready.sort(key=lambda m: m.sort_key)

        for msg in ready:
            if msg.type_priority == MessageTypePriority.FILL_ACK:
                self._apply_fill_ack(msg, open_ms)
            elif msg.type_priority == MessageTypePriority.FUNDING_ACK:
                self._apply_funding_ack(msg)
            elif msg.type_priority == MessageTypePriority.MARK_BAR:
                if bool(msg.payload.get("corrupted", False)):
                    self.source_blocked = True
                    self.source_blocked_reason = f"CORRUPTED_MARK_BAR:{msg.symbol}:{msg.event_at_ms}"
                else:
                    close_px = msg.payload["close"]
                    assert isinstance(close_px, Decimal)
                    if close_px <= Decimal(0):
                        self.source_blocked = True
                        self.source_blocked_reason = (
                            f"NON_POSITIVE_MARK_BAR:{msg.symbol}:{msg.event_at_ms}"
                        )
                    else:
                        self.last_available_marks[msg.symbol] = (
                            close_px,
                            msg.event_at_ms,
                            msg.available_at_ms,
                        )
        return ready

    def _apply_fill_ack(self, msg: OracleMessage, open_ms: int) -> None:
        p = msg.payload
        fill_kind = str(p["fill_kind"])
        symbol = msg.symbol
        cash_delta = p["cash_delta_usdt"]
        assert isinstance(cash_delta, Decimal)

        with decimal_context():
            self.acknowledged_cash_usdt = round_ledger_usdt(
                self.acknowledged_cash_usdt + cash_delta
            )

        if fill_kind == "ENTRY":
            entry_res_id = p.get("entry_reserve_id")
            if isinstance(entry_res_id, str) and entry_res_id in self.reserves:
                res = self.reserves[entry_res_id]
                if not res.released:
                    res.release_once()

            pos = PositionRecord(
                position_id=str(p["position_id"]),
                symbol=symbol,
                direction=int(p["direction"]),  # type: ignore[arg-type]
                quantity=p["quantity"],  # type: ignore[arg-type]
                raw_entry_price=p["raw_entry_price"],  # type: ignore[arg-type]
                effective_entry_price=p["effective_entry_price"],  # type: ignore[arg-type]
                stop_price=p["stop_price"],  # type: ignore[arg-type]
                target_price=p["target_price"],  # type: ignore[arg-type]
                initial_stop_risk_dollars_per_unit=p[
                    "initial_stop_risk_dollars_per_unit"
                ],  # type: ignore[arg-type]
                entry_at_ms=int(p["entry_at_ms"]),  # type: ignore[arg-type]
                max_hold_ms=int(p["max_hold_ms"]),  # type: ignore[arg-type]
                exit_reserve_id=p.get("exit_reserve_id"),  # type: ignore[arg-type]
                funding_reserve_id=p.get("funding_reserve_id"),  # type: ignore[arg-type]
            )
            self.acknowledged_positions[symbol] = pos
            if not self.kill_latched:
                if self.symbol_states.get(symbol) == BookSymbolState.ENTRY_PENDING:
                    self.symbol_states[symbol] = BookSymbolState.OPEN
            else:
                # Insolvent/killed book queues liquidation of newly acknowledged pending quantity
                self.symbol_states[symbol] = BookSymbolState.EXIT_PENDING
                self.due_orders.append(
                    OrderRequest(
                        order_id=self._next_id("ORD_KILL_LATE"),
                        symbol=symbol,
                        kind="KILL_EXIT",
                        direction=-pos.direction,
                        quantity=pos.quantity,
                        created_at_ms=open_ms,
                        due_at_ms=open_ms + ONE_MINUTE_MS,
                        reason="KILL_LIQUIDATE_NEWLY_ACKED_POSITION",
                    )
                )

        elif fill_kind in ("FULL_EXIT", "REDUCTION"):
            exited_qty = p["exited_quantity"]
            assert isinstance(exited_qty, Decimal)
            ack_pos = self.acknowledged_positions.get(symbol)
            if ack_pos is not None:
                with decimal_context():
                    prev_qty = ack_pos.quantity
                    rem_qty = max(Decimal(0), prev_qty - exited_qty)
                    # Proportionate exit/funding reserve reduction or full release
                    for res_id in (ack_pos.exit_reserve_id, ack_pos.funding_reserve_id):
                        if isinstance(res_id, str) and res_id in self.reserves:
                            res = self.reserves[res_id]
                            if not res.released:
                                if rem_qty == Decimal(0):
                                    res.release_once()
                                elif prev_qty > Decimal(0):
                                    res.amount_usdt = round_ledger_usdt(
                                        res.amount_usdt * (rem_qty / prev_qty)
                                    )
                                    res.quantity = rem_qty
                    if rem_qty == Decimal(0):
                        del self.acknowledged_positions[symbol]
                        exit_event_ms = int(p["exit_event_ms"])  # type: ignore[arg-type]
                        ceil_min = (
                            (exit_event_ms + ONE_MINUTE_MS - 1) // ONE_MINUTE_MS
                        ) * ONE_MINUTE_MS
                        self.cooldown_until_ms[symbol] = ceil_min + COOLDOWN_DURATION_MS
                        if not self.kill_latched:
                            self.symbol_states[symbol] = BookSymbolState.COOLDOWN
                        else:
                            self.symbol_states[symbol] = BookSymbolState.DISABLED
                    else:
                        ack_pos.quantity = rem_qty
                        if not self.kill_latched:
                            self.symbol_states[symbol] = BookSymbolState.OPEN

    def _apply_funding_ack(self, msg: OracleMessage) -> None:
        p = msg.payload
        funding_debit = p["funding_debit_usdt"]
        assert isinstance(funding_debit, Decimal)
        with decimal_context():
            self.acknowledged_cash_usdt = round_ledger_usdt(
                self.acknowledged_cash_usdt - funding_debit
            )

    def _stage2_account_risk(self, open_ms: int) -> dict[str, object]:
        stale_symbols: list[str] = []
        for sym in ALLOWLISTED_SYMBOLS:
            mark_info = self.last_available_marks.get(sym)
            if mark_info is not None:
                _, mark_event_ms, _ = mark_info
                if open_ms - mark_event_ms > MAX_MARK_EVENT_AGE_MS:
                    stale_symbols.append(sym)
            elif sym in self.acknowledged_positions:
                stale_symbols.append(sym)

        # Queue delayed exit at O + 60000 for known positions with stale/missing marks
        for sym in stale_symbols:
            if sym in self.acknowledged_positions:
                pos = self.acknowledged_positions[sym]
                already_queued = any(
                    o.symbol == sym and o.kind in ("KILL_EXIT", "STALE_MARK_EXIT")
                    for o in self.due_orders
                )
                if not already_queued:
                    self.symbol_states[sym] = BookSymbolState.EXIT_PENDING
                    self.due_orders.append(
                        OrderRequest(
                            order_id=self._next_id("ORD_STALE"),
                            symbol=sym,
                            kind="STALE_MARK_EXIT",
                            direction=-pos.direction,
                            quantity=pos.quantity,
                            created_at_ms=open_ms,
                            due_at_ms=open_ms + ONE_MINUTE_MS,
                            reason="STALE_OR_MISSING_MARK_DELAYED_EXIT",
                        )
                    )

        with decimal_context():
            e_d = self.compute_decision_equity()
            self.decision_high_water_usdt = max(self.decision_high_water_usdt, e_d)
            dd_usdt = round_ledger_usdt(self.decision_high_water_usdt - e_d)

            newly_killed = False
            if not self.kill_latched and (
                e_d <= Decimal(0) or dd_usdt >= DRAWDOWN_KILL_THRESHOLD_USDT
            ):
                self.kill_latched = True
                newly_killed = True
                if e_d <= Decimal(0):
                    self.decision_insolvency_latched = True
                for sym in ALLOWLISTED_SYMBOLS:
                    self.symbol_states[sym] = BookSymbolState.DISABLED
                # Queue liquidation of all known acknowledged positions at O + 60000
                for sym in sorted(self.acknowledged_positions):
                    pos = self.acknowledged_positions[sym]
                    self.due_orders = [
                        o
                        for o in self.due_orders
                        if not (o.symbol == sym and o.kind != "KILL_EXIT")
                    ]
                    if not any(
                        o.symbol == sym and o.kind == "KILL_EXIT" for o in self.due_orders
                    ):
                        self.due_orders.append(
                            OrderRequest(
                                order_id=self._next_id("ORD_KILL"),
                                symbol=sym,
                                kind="KILL_EXIT",
                                direction=-pos.direction,
                                quantity=pos.quantity,
                                created_at_ms=open_ms,
                                due_at_ms=open_ms + ONE_MINUTE_MS,
                                reason="DECISION_DRAWDOWN_OR_INSOLVENCY_KILL",
                            )
                        )

        return {
            "decision_equity_usdt": e_d,
            "decision_high_water_usdt": self.decision_high_water_usdt,
            "decision_drawdown_usdt": dd_usdt,
            "kill_latched": self.kill_latched,
            "newly_killed": newly_killed,
            "stale_symbols": stale_symbols,
        }

    def _stage3_scheduling(
        self, open_ms: int, entry_specs: Sequence[dict[str, object]]
    ) -> dict[str, object]:
        cancelled_entries: list[str] = []
        queued_reductions: list[str] = []
        scheduled_entries: list[str] = []

        # Cancel pending entry orders on kill or mark staleness
        for order in list(self.due_orders):
            if order.kind != "ENTRY":
                continue
            mark_info = self.last_available_marks.get(order.symbol)
            is_stale = (
                mark_info is None
                or (open_ms - mark_info[1]) > MAX_MARK_EVENT_AGE_MS
            )
            if self.kill_latched or self.source_blocked or is_stale:
                self._cancel_pending_entry_order(order)
                cancelled_entries.append(order.order_id)

        if not self.kill_latched and not self.source_blocked:
            with decimal_context():
                a_cap = self.compute_admissible_capital_a()
                g_ack = self.compute_acknowledged_gross_notional()
                pending_entry_notional = sum(
                    (
                        self.reserves[o.entry_reserve_id].amount_usdt
                        for o in self.due_orders
                        if o.kind == "ENTRY"
                        and o.entry_reserve_id in self.reserves
                        and not self.reserves[o.entry_reserve_id].released
                    ),
                    Decimal(0),
                )
                if g_ack + pending_entry_notional > a_cap:
                    # Cancel pending entries first
                    for order in list(self.due_orders):
                        if order.kind == "ENTRY":
                            self._cancel_pending_entry_order(order)
                            cancelled_entries.append(order.order_id)
                    a_cap = self.compute_admissible_capital_a()
                    g_ack = self.compute_acknowledged_gross_notional()

                if g_ack > a_cap and g_ack > Decimal(0):
                    # Proportional known-position reduction to target notional = A, rounded down by lot
                    scale = a_cap / g_ack
                    for sym in sorted(self.acknowledged_positions):
                        pos = self.acknowledged_positions[sym]
                        flt = self.filters.get(sym)
                        lot = flt.lot_size if flt is not None else Decimal("0.001")
                        target_qty = floor_to_step(pos.quantity * scale, lot)
                        reduce_qty = max(Decimal(0), pos.quantity - target_qty)
                        if reduce_qty > Decimal(0) and not any(
                            o.symbol == sym
                            and o.kind in ("KILL_EXIT", "PRO_RATA_REDUCTION")
                            for o in self.due_orders
                        ):
                            red_order = OrderRequest(
                                order_id=self._next_id("ORD_REDUCE"),
                                symbol=sym,
                                kind="PRO_RATA_REDUCTION",
                                direction=-pos.direction,
                                quantity=reduce_qty,
                                created_at_ms=open_ms,
                                due_at_ms=open_ms + ONE_MINUTE_MS,
                                reason="SUPERVISOR_1X_CAPITAL_REDUCTION",
                            )
                            self.due_orders.append(red_order)
                            queued_reductions.append(red_order.order_id)

                # Schedule eligible new entries from the same pre-entry snapshot in canonical symbol order
                if entry_specs:
                    snapshot_a = self.compute_admissible_capital_a()
                    residual = snapshot_a - self.compute_acknowledged_gross_notional()
                    by_sym = {str(s["symbol"]): s for s in entry_specs}
                    for sym in ALLOWLISTED_SYMBOLS:
                        spec = by_sym.get(sym)
                        if spec is None:
                            continue
                        ord_req = self.size_and_reserve_entry(
                            symbol=sym,
                            direction=int(spec["direction"]),  # type: ignore[arg-type]
                            decision_at_ms=open_ms,
                            decision_close=spec["decision_close"],  # type: ignore[arg-type]
                            atr20=spec["atr20"],  # type: ignore[arg-type]
                            raw_stop=spec["raw_stop"],  # type: ignore[arg-type]
                            max_hold_ms=int(spec["max_hold_ms"]),  # type: ignore[arg-type]
                            settlement_events_in_hold=int(
                                spec.get("settlement_events_in_hold", 4)  # type: ignore[arg-type]
                            ),
                            snapshot_a=snapshot_a,
                            residual_a_minus_g=residual,
                            retest_event_id=spec.get("retest_event_id"),  # type: ignore[arg-type]
                        )
                        if ord_req is not None and ord_req.entry_reserve_id is not None:
                            scheduled_entries.append(ord_req.order_id)
                            residual = max(
                                Decimal(0),
                                residual - self.reserves[ord_req.entry_reserve_id].amount_usdt,
                            )

        return {
            "cancelled_entries": cancelled_entries,
            "queued_reductions": queued_reductions,
            "scheduled_entries": scheduled_entries,
        }

    def _cancel_pending_entry_order(self, order: OrderRequest) -> None:
        if order in self.due_orders:
            self.due_orders.remove(order)
        for res_id in (
            order.entry_reserve_id,
            order.exit_reserve_id,
            order.funding_reserve_id,
        ):
            if isinstance(res_id, str) and res_id in self.reserves:
                res = self.reserves[res_id]
                if not res.released:
                    res.release_once()
        if not self.kill_latched and self.symbol_states.get(order.symbol) == BookSymbolState.ENTRY_PENDING:
            self.symbol_states[order.symbol] = BookSymbolState.FLAT

    def _stage4_execute_due_exits(
        self, open_ms: int, trade_bars: dict[str, MarketBarMessage]
    ) -> tuple[set[str], list[TradeOutcomeSummary]]:
        exited_symbols: set[str] = set()
        outcomes: list[TradeOutcomeSummary] = []

        # Collect ordinary open exits (gap-SL, gap-TP, expiry) for economic positions
        for sym in ALLOWLISTED_SYMBOLS:
            pos = self.economic_positions.get(sym)
            if pos is None:
                continue
            bar = trade_bars.get(sym)
            if bar is None:
                self.source_blocked = True
                self.source_blocked_reason = f"MISSING_ACTIVE_TRADE_BAR_AT_OPEN:{sym}:{open_ms}"
                continue

            # Check gap-SL, gap-TP, expiry at open_ms
            has_kill = any(
                o.symbol == sym
                and o.kind in ("KILL_EXIT", "STALE_MARK_EXIT")
                and o.due_at_ms <= open_ms
                and o.created_at_ms <= open_ms - ONE_MINUTE_MS
                for o in self.due_orders
            )
            if has_kill:
                continue

            with decimal_context():
                gap_sl = (pos.direction == 1 and bar.open <= pos.stop_price) or (
                    pos.direction == -1 and bar.open >= pos.stop_price
                )
                gap_tp = (pos.direction == 1 and bar.open >= pos.target_price) or (
                    pos.direction == -1 and bar.open <= pos.target_price
                )
                expired = open_ms >= pos.entry_at_ms + pos.max_hold_ms

                if gap_sl or gap_tp or expired:
                    reason = "GAP_SL" if gap_sl else ("GAP_TP" if gap_tp else "EXPIRY")
                    self.due_orders.append(
                        OrderRequest(
                            order_id=self._next_id("ORD_OPEN_EXIT"),
                            symbol=sym,
                            kind="ORDINARY_EXIT",
                            direction=-pos.direction,
                            quantity=pos.quantity,
                            created_at_ms=pos.entry_at_ms,
                            due_at_ms=open_ms,
                            reason=reason,
                        )
                    )

        # Priority order: KILL_EXIT/STALE_MARK_EXIT -> PRO_RATA_REDUCTION -> ORDINARY_EXIT (GAP_SL, GAP_TP, EXPIRY)
        priority_map = {
            "KILL_EXIT": 0,
            "STALE_MARK_EXIT": 1,
            "PRO_RATA_REDUCTION": 2,
            "ORDINARY_EXIT": 3,
        }
        due_exit_orders = [
            o
            for o in self.due_orders
            if o.kind in priority_map
            and o.due_at_ms <= open_ms
            and o.created_at_ms <= open_ms - ONE_MINUTE_MS
        ]
        due_exit_orders.sort(
            key=lambda o: (priority_map[o.kind], ALLOWLISTED_SYMBOLS.index(o.symbol), o.order_id)
        )

        for order in due_exit_orders:
            sym = order.symbol
            if sym in exited_symbols:
                # One exit per quantity at a single open; kill dominates reason
                if order in self.due_orders:
                    self.due_orders.remove(order)
                continue

            pos = self.economic_positions.get(sym)
            if pos is None:
                if order in self.due_orders:
                    self.due_orders.remove(order)
                continue

            bar = trade_bars.get(sym)
            if bar is None or bar.corrupted or bar.open <= Decimal(0) or bar.volume <= Decimal(0):
                self.source_blocked = True
                self.source_blocked_reason = f"UNAVAILABLE_LIQUIDATION_OPEN:{sym}:{open_ms}"
                self.symbol_states[sym] = BookSymbolState.EXIT_PENDING
                continue

            if order in self.due_orders:
                self.due_orders.remove(order)

            # Cancel conflicting pending entries on the same symbol
            for pending_entry in [
                o for o in list(self.due_orders) if o.symbol == sym and o.kind == "ENTRY"
            ]:
                self._cancel_pending_entry_order(pending_entry)

            with decimal_context():
                exit_qty = min(pos.quantity, order.quantity)
                # Every risk/time market exit at an open beyond a favorable standing target
                # caps its raw price at that target (LONG min(open,target), SHORT max(open,target))
                if pos.direction == 1:
                    capped_raw_exit = min(bar.open, pos.target_price)
                else:
                    capped_raw_exit = max(bar.open, pos.target_price)

                outcome = self._execute_economic_exit(
                    pos=pos,
                    exit_qty=exit_qty,
                    raw_exit_price=capped_raw_exit,
                    exit_event_ms=open_ms,
                    ack_origin_ms=open_ms,
                    exit_reason=order.reason or order.kind,
                    parent_order_id=order.order_id,
                )
                outcomes.append(outcome)
                exited_symbols.add(sym)

        return exited_symbols, outcomes

    def _stage5_execute_due_entries(
        self,
        open_ms: int,
        trade_bars: dict[str, MarketBarMessage],
        exited_symbols_at_open: set[str],
    ) -> list[str]:
        executed_position_ids: list[str] = []
        due_entries = [
            o
            for o in self.due_orders
            if o.kind == "ENTRY"
            and o.due_at_ms <= open_ms
            and o.created_at_ms <= open_ms - ONE_MINUTE_MS
        ]
        due_entries.sort(key=lambda o: (ALLOWLISTED_SYMBOLS.index(o.symbol), o.order_id))

        for order in due_entries:
            sym = order.symbol
            if (
                self.kill_latched
                or self.source_blocked
                or sym in exited_symbols_at_open
                or sym in self.economic_positions
            ):
                self._cancel_pending_entry_order(order)
                self.wait_and_veto_log.append(
                    {"symbol": sym, "at_ms": open_ms, "reason": "ENTRY_CANCELLED_AT_OPEN"}
                )
                continue

            bar = trade_bars.get(sym)
            if bar is None or bar.corrupted:
                self.source_blocked = True
                self.source_blocked_reason = f"MISSING_ENTRY_TRADE_BAR:{sym}:{open_ms}"
                self._cancel_pending_entry_order(order)
                continue

            if bar.open <= Decimal(0) or bar.volume <= Decimal(0):
                self._cancel_pending_entry_order(order)
                self.wait_and_veto_log.append(
                    {"symbol": sym, "at_ms": open_ms, "reason": "ZERO_VOLUME_OR_INVALID_OPEN_VETO"}
                )
                continue

            flt = self.filters[sym]
            with decimal_context():
                abs_gap = abs(bar.open - order.decision_close)
                if abs_gap > MAX_ENTRY_GAP_ATR_FRACTION * order.atr20:
                    self._cancel_pending_entry_order(order)
                    self.wait_and_veto_log.append(
                        {"symbol": sym, "at_ms": open_ms, "reason": "ENTRY_GAP_EXCEEDS_0_25_ATR"}
                    )
                    continue

                eff_entry = round_execution_price(
                    bar.open,
                    is_buy=(order.direction == 1),
                    cost_scenario=self.cost_scenario,
                    tick_size=flt.tick_size,
                )
                rounded_stop = round_stop_toward_entry(
                    order.raw_stop, direction=order.direction, tick_size=flt.tick_size
                )
                risk_per_unit = Decimal(order.direction) * (eff_entry - rounded_stop)
                if risk_per_unit <= Decimal(0):
                    self._cancel_pending_entry_order(order)
                    self.wait_and_veto_log.append(
                        {"symbol": sym, "at_ms": open_ms, "reason": "NON_POSITIVE_STOP_RISK_VETO"}
                    )
                    continue

                risk_bps = (risk_per_unit / eff_entry) * BPS_DENOMINATOR
                if risk_bps < MIN_RISK_BPS or risk_bps > MAX_RISK_BPS:
                    self._cancel_pending_entry_order(order)
                    self.wait_and_veto_log.append(
                        {"symbol": sym, "at_ms": open_ms, "reason": "ENTRY_RISK_BPS_OUT_OF_RANGE"}
                    )
                    continue

                raw_target = (
                    eff_entry
                    + Decimal(order.direction) * TARGET_RISK_MULTIPLE * risk_per_unit
                )
                rounded_target = round_target_toward_entry(
                    raw_target, direction=order.direction, tick_size=flt.tick_size
                )
                entry_notional = order.quantity * eff_entry
                if entry_notional < flt.min_notional_usdt:
                    self._cancel_pending_entry_order(order)
                    self.wait_and_veto_log.append(
                        {"symbol": sym, "at_ms": open_ms, "reason": "MIN_NOTIONAL_VETO_AT_EXECUTION"}
                    )
                    continue

                fee_rate = self.cost_scenario.taker_fee_bps_per_leg / BPS_DENOMINATOR
                entry_fee = round_ledger_usdt(entry_notional * fee_rate)

                # Record if actual entry cost exceeded reserved entry amount (never retroactive veto)
                if order.entry_reserve_id and order.entry_reserve_id in self.reserves:
                    res_amt = self.reserves[order.entry_reserve_id].amount_usdt
                    if entry_notional + entry_fee > res_amt:
                        self.reserve_shortfalls.append(
                            {
                                "symbol": sym,
                                "at_ms": open_ms,
                                "kind": "ENTRY",
                                "reserved_usdt": res_amt,
                                "actual_usdt": round_ledger_usdt(entry_notional + entry_fee),
                            }
                        )

                self.due_orders.remove(order)
                pos_id = self._next_id("POS")
                pos = PositionRecord(
                    position_id=pos_id,
                    symbol=sym,
                    direction=order.direction,
                    quantity=order.quantity,
                    raw_entry_price=bar.open,
                    effective_entry_price=eff_entry,
                    stop_price=rounded_stop,
                    target_price=rounded_target,
                    initial_stop_risk_dollars_per_unit=risk_per_unit,
                    entry_at_ms=open_ms,
                    max_hold_ms=order.max_hold_ms,
                    exit_reserve_id=order.exit_reserve_id,
                    funding_reserve_id=order.funding_reserve_id,
                    accumulated_entry_fee_usdt=entry_fee,
                )
                self.economic_positions[sym] = pos
                self.economic_cash_usdt = round_ledger_usdt(
                    self.economic_cash_usdt - entry_fee
                )
                self.exposure_intervals.append(
                    ExposureInterval(
                        position_id=pos_id,
                        symbol=sym,
                        direction=order.direction,
                        start_ms=open_ms,
                        end_ms=None,
                        pre_quantity=order.quantity,
                        post_quantity=order.quantity,
                        entry_price=eff_entry,
                    )
                )

                # Emit virtual FILL_ACK available at open_ms + 60000
                self.enqueue_message(
                    OracleMessage(
                        available_at_ms=open_ms + VIRTUAL_ACK_DELAY_MS,
                        event_at_ms=open_ms,
                        type_priority=MessageTypePriority.FILL_ACK,
                        sub_priority=int(FillAckSubPriority.ENTRY),
                        parent_order_id=order.order_id,
                        symbol=sym,
                        source_id=self._next_id("MSG_FILL_ACK_ENTRY"),
                        payload={
                            "fill_kind": "ENTRY",
                            "position_id": pos_id,
                            "direction": order.direction,
                            "quantity": order.quantity,
                            "raw_entry_price": bar.open,
                            "effective_entry_price": eff_entry,
                            "stop_price": rounded_stop,
                            "target_price": rounded_target,
                            "initial_stop_risk_dollars_per_unit": risk_per_unit,
                            "entry_at_ms": open_ms,
                            "max_hold_ms": order.max_hold_ms,
                            "entry_reserve_id": order.entry_reserve_id,
                            "exit_reserve_id": order.exit_reserve_id,
                            "funding_reserve_id": order.funding_reserve_id,
                            "cash_delta_usdt": -entry_fee,
                        },
                    )
                )
                executed_position_ids.append(pos_id)

        return executed_position_ids

    def _stage6_intraminute_protection(
        self,
        open_ms: int,
        trade_bars: dict[str, MarketBarMessage],
        exited_symbols_at_open: set[str],
    ) -> list[TradeOutcomeSummary]:
        outcomes: list[TradeOutcomeSummary] = []
        for sym in ALLOWLISTED_SYMBOLS:
            if sym in exited_symbols_at_open:
                continue
            pos = self.economic_positions.get(sym)
            if pos is None:
                continue
            bar = trade_bars.get(sym)
            if bar is None or bar.corrupted:
                self.source_blocked = True
                self.source_blocked_reason = f"MISSING_INTRAMINUTE_TRADE_BAR:{sym}:{open_ms}"
                continue

            with decimal_context():
                if pos.direction == 1:
                    sl_touched = bar.low <= pos.stop_price
                    tp_touched = bar.high >= pos.target_price
                    adverse_open_gap = bar.open < pos.stop_price
                else:
                    sl_touched = bar.high >= pos.stop_price
                    tp_touched = bar.low <= pos.target_price
                    adverse_open_gap = bar.open > pos.stop_price

                if not sl_touched and not tp_touched:
                    continue

                # Stop-first same-minute rule (SL_FIRST if both touch)
                if sl_touched:
                    raw_exit = bar.open if adverse_open_gap else pos.stop_price
                    reason = (
                        "INTRABAR_SL_FIRST_COLLISION"
                        if tp_touched
                        else ("GAP_SL" if adverse_open_gap else "INTRABAR_SL")
                    )
                else:
                    # Favorable target gap credits only fixed target (no overcredit)
                    raw_exit = pos.target_price
                    reason = "INTRABAR_TP"

                intrabar_event_ms = open_ms + ONE_MINUTE_MS - 1
                outcome = self._execute_economic_exit(
                    pos=pos,
                    exit_qty=pos.quantity,
                    raw_exit_price=raw_exit,
                    exit_event_ms=intrabar_event_ms,
                    ack_origin_ms=intrabar_event_ms,
                    exit_reason=reason,
                    parent_order_id=pos.position_id,
                )
                outcomes.append(outcome)

        return outcomes

    def _execute_economic_exit(
        self,
        *,
        pos: PositionRecord,
        exit_qty: Decimal,
        raw_exit_price: Decimal,
        exit_event_ms: int,
        ack_origin_ms: int,
        exit_reason: str,
        parent_order_id: str,
    ) -> TradeOutcomeSummary:
        sym = pos.symbol
        flt = self.filters[sym]
        with decimal_context():
            is_buy = pos.direction == -1
            eff_exit = round_execution_price(
                raw_exit_price,
                is_buy=is_buy,
                cost_scenario=self.cost_scenario,
                tick_size=flt.tick_size,
            )
            fee_rate = self.cost_scenario.taker_fee_bps_per_leg / BPS_DENOMINATOR
            exit_notional = exit_qty * eff_exit
            exit_fee = round_ledger_usdt(exit_notional * fee_rate)

            fraction = exit_qty / pos.quantity
            alloc_entry_fee = round_ledger_usdt(pos.accumulated_entry_fee_usdt * fraction)
            alloc_funding = round_ledger_usdt(pos.accumulated_funding_usdt * fraction)

            entry_notional = round_ledger_usdt(exit_qty * pos.effective_entry_price)
            gross_quote_pnl = round_ledger_usdt(
                exit_qty
                * Decimal(pos.direction)
                * (raw_exit_price - pos.raw_entry_price)
            )
            eff_quote_pnl = round_ledger_usdt(
                exit_qty
                * Decimal(pos.direction)
                * (eff_exit - pos.effective_entry_price)
            )
            execution_drag = round_ledger_usdt(gross_quote_pnl - eff_quote_pnl)
            total_fees = round_ledger_usdt(alloc_entry_fee + exit_fee)
            net_pnl = round_ledger_usdt(eff_quote_pnl - total_fees - alloc_funding)

            # Cash delta at exit = effective_quote_pnl - exit_fee (entry fee & funding already posted)
            cash_delta_at_exit = round_ledger_usdt(eff_quote_pnl - exit_fee)
            self.economic_cash_usdt = round_ledger_usdt(
                self.economic_cash_usdt + cash_delta_at_exit
            )

            gross_bps = round_ledger_usdt(
                (gross_quote_pnl / entry_notional) * BPS_DENOMINATOR
            )
            net_bps = round_ledger_usdt((net_pnl / entry_notional) * BPS_DENOMINATOR)
            init_risk_dollars = round_ledger_usdt(
                exit_qty * pos.initial_stop_risk_dollars_per_unit
            )
            net_r = (
                round_ledger_usdt(net_pnl / init_risk_dollars)
                if init_risk_dollars > Decimal(0)
                else None
            )
            eq_ret = round_ledger_usdt(net_pnl / INITIAL_EQUITY_USDT)

            rem_qty = max(Decimal(0), pos.quantity - exit_qty)
            # Update exposure interval for funding ownership checks
            for interval in reversed(self.exposure_intervals):
                if interval.position_id == pos.position_id and interval.end_ms is None:
                    interval.end_ms = exit_event_ms
                    interval.post_quantity = rem_qty
                    break

            if rem_qty == Decimal(0):
                del self.economic_positions[sym]
                fill_kind = "FULL_EXIT"
            else:
                pos.quantity = rem_qty
                pos.accumulated_entry_fee_usdt = round_ledger_usdt(
                    pos.accumulated_entry_fee_usdt - alloc_entry_fee
                )
                pos.accumulated_funding_usdt = round_ledger_usdt(
                    pos.accumulated_funding_usdt - alloc_funding
                )
                self.exposure_intervals.append(
                    ExposureInterval(
                        position_id=pos.position_id,
                        symbol=sym,
                        direction=pos.direction,
                        start_ms=exit_event_ms,
                        end_ms=None,
                        pre_quantity=rem_qty,
                        post_quantity=rem_qty,
                        entry_price=pos.effective_entry_price,
                    )
                )
                fill_kind = "REDUCTION"

            self.enqueue_message(
                OracleMessage(
                    available_at_ms=ack_origin_ms + VIRTUAL_ACK_DELAY_MS,
                    event_at_ms=exit_event_ms,
                    type_priority=MessageTypePriority.FILL_ACK,
                    sub_priority=int(FillAckSubPriority.EXIT_OR_REDUCTION),
                    parent_order_id=parent_order_id,
                    symbol=sym,
                    source_id=self._next_id("MSG_FILL_ACK_EXIT"),
                    payload={
                        "fill_kind": fill_kind,
                        "position_id": pos.position_id,
                        "exited_quantity": exit_qty,
                        "exit_event_ms": exit_event_ms,
                        "cash_delta_usdt": cash_delta_at_exit,
                    },
                )
            )

            summary = TradeOutcomeSummary(
                trade_id=self._next_id("TRD"),
                position_id=pos.position_id,
                symbol=sym,
                direction=pos.direction,
                quantity=exit_qty,
                entry_at_ms=pos.entry_at_ms,
                exit_at_ms=exit_event_ms,
                exit_reason=exit_reason,
                raw_entry_price=pos.raw_entry_price,
                effective_entry_price=pos.effective_entry_price,
                raw_exit_price=raw_exit_price,
                effective_exit_price=eff_exit,
                entry_notional_usdt=entry_notional,
                gross_quote_pnl_usdt=gross_quote_pnl,
                execution_drag_usdt=execution_drag,
                effective_quote_pnl_usdt=eff_quote_pnl,
                entry_fee_usdt=alloc_entry_fee,
                exit_fee_usdt=exit_fee,
                funding_cashflow_usdt=alloc_funding,
                net_pnl_usdt=net_pnl,
                gross_bps=gross_bps,
                net_bps=net_bps,
                initial_risk_dollars_usdt=init_risk_dollars,
                net_r=net_r,
                account_equity_return_delta=eq_ret,
            )
            self.completed_trades.append(summary)
            return summary

    def _stage7_funding_ownership(
        self, open_ms: int, settlements: Sequence[SettlementWindow]
    ) -> list[dict[str, object]]:
        """Evaluate bounded funding ownership [S - 15000, S + 15000] once all intersecting minutes complete."""
        minute_end_ms = open_ms + ONE_MINUTE_MS
        charges: list[dict[str, object]] = []

        for settlement in settlements:
            if settlement.settlement_id in self.charged_settlement_ids:
                continue
            if minute_end_ms < settlement.end_of_last_intersecting_minute_ms:
                continue

            # Find all exposure intervals for this symbol that intersect [S - 15000, S + 15000]
            # Never sum pre + post quantities; take max(pre_quantity, post_quantity) across intersecting intervals
            with decimal_context():
                chargeable_qty = Decimal(0)
                matched_pos_id: str | None = None
                matched_dir: int = 1
                matched_entry_px: Decimal = Decimal(0)

                for interval in self.exposure_intervals:
                    if interval.symbol != settlement.symbol:
                        continue
                    i_end = (
                        interval.end_ms
                        if interval.end_ms is not None
                        else minute_end_ms + ONE_MINUTE_MS
                    )
                    if (
                        interval.start_ms <= settlement.window_end_ms
                        and i_end >= settlement.window_start_ms
                    ):
                        candidate_qty = max(interval.pre_quantity, interval.post_quantity)
                        if candidate_qty > chargeable_qty:
                            chargeable_qty = candidate_qty
                            matched_pos_id = interval.position_id
                            matched_dir = interval.direction
                            matched_entry_px = interval.entry_price

                self.charged_settlement_ids.add(settlement.settlement_id)
                if chargeable_qty <= Decimal(0):
                    continue

                # Determine funding debit:
                # In selection/adverse scenario (allow_positive_funding_credit=False), zero benefit is allowed.
                proxy_rate = (
                    self.cost_scenario.funding_proxy_bps_per_event / BPS_DENOMINATOR
                )
                if not self.cost_scenario.allow_positive_funding_credit:
                    if settlement.is_measured_schedule:
                        adverse_actual = max(
                            Decimal(0), Decimal(matched_dir) * settlement.actual_rate
                        )
                        eff_rate = max(Decimal(2) * adverse_actual, proxy_rate)
                        notional_px = settlement.settlement_mark_price
                    else:
                        eff_rate = proxy_rate
                        notional_px = max(matched_entry_px, settlement.settlement_mark_price)
                    debit_usdt = round_ledger_usdt(chargeable_qty * notional_px * eff_rate)
                else:
                    # Measured reconstruction with signed rate: LONG pays positive, SHORT receives positive
                    debit_usdt = round_ledger_usdt(
                        Decimal(matched_dir)
                        * chargeable_qty
                        * settlement.settlement_mark_price
                        * settlement.actual_rate
                    )

                self.economic_cash_usdt = round_ledger_usdt(
                    self.economic_cash_usdt - debit_usdt
                )
                pos = self.economic_positions.get(settlement.symbol)
                if pos is not None and pos.position_id == matched_pos_id:
                    pos.accumulated_funding_usdt = round_ledger_usdt(
                        pos.accumulated_funding_usdt + debit_usdt
                    )

                self.enqueue_message(
                    OracleMessage(
                        available_at_ms=settlement.ack_available_at_ms,
                        event_at_ms=settlement.settlement_ms,
                        type_priority=MessageTypePriority.FUNDING_ACK,
                        sub_priority=0,
                        parent_order_id=settlement.settlement_id,
                        symbol=settlement.symbol,
                        source_id=f"MSG_FUND_ACK_{settlement.settlement_id}",
                        payload={
                            "settlement_id": settlement.settlement_id,
                            "quantity_charged": chargeable_qty,
                            "funding_debit_usdt": debit_usdt,
                        },
                    )
                )
                charges.append(
                    {
                        "settlement_id": settlement.settlement_id,
                        "symbol": settlement.symbol,
                        "quantity_charged": chargeable_qty,
                        "funding_debit_usdt": debit_usdt,
                        "ack_available_at_ms": settlement.ack_available_at_ms,
                    }
                )

        return charges

    def _stage8_ex_post_report(
        self,
        open_ms: int,
        trade_bars: dict[str, MarketBarMessage],
        mark_bars: dict[str, MarketBarMessage],
    ) -> dict[str, object]:
        for sym, mbar in mark_bars.items():
            if mbar.corrupted or mbar.close <= Decimal(0):
                self.source_blocked = True
                self.source_blocked_reason = f"INVALID_MARK_BAR_AT_CLOSE:{sym}:{open_ms}"
            else:
                self.economic_marks[sym] = mbar.close
            self.enqueue_message(
                OracleMessage(
                    available_at_ms=mbar.effective_available_at_ms,
                    event_at_ms=mbar.event_at_ms,
                    type_priority=MessageTypePriority.MARK_BAR,
                    sub_priority=0,
                    parent_order_id=mbar.source_id,
                    symbol=sym,
                    source_id=mbar.source_id,
                    payload={
                        "close": mbar.close,
                        "corrupted": mbar.corrupted,
                    },
                )
            )

        for sym, tbar in trade_bars.items():
            self.enqueue_message(
                OracleMessage(
                    available_at_ms=tbar.effective_available_at_ms,
                    event_at_ms=tbar.event_at_ms,
                    type_priority=MessageTypePriority.TRADE_BAR,
                    sub_priority=0,
                    parent_order_id=tbar.source_id,
                    symbol=sym,
                    source_id=tbar.source_id,
                    payload={"close": tbar.close},
                )
            )

        with decimal_context():
            e_e = self.compute_economic_equity()
            g_e = self.compute_economic_gross_notional()
            self.economic_high_water_usdt = max(self.economic_high_water_usdt, e_e)
            dd_e = round_ledger_usdt(self.economic_high_water_usdt - e_e)
            self.economic_max_drawdown_usdt = max(self.economic_max_drawdown_usdt, dd_e)
            if e_e <= Decimal(0):
                self.economically_insolvent = True
            if g_e > max(Decimal(0), e_e) and g_e > Decimal(0):
                self.true_economic_leverage_breach = True

        return {
            "economic_equity_usdt": e_e,
            "economic_gross_notional_usdt": g_e,
            "economic_drawdown_usdt": dd_e,
            "economically_insolvent": self.economically_insolvent,
            "true_economic_leverage_breach": self.true_economic_leverage_breach,
        }


@dataclass(frozen=True)
class MatchedEpisodeResult:
    """Unfunded paired counterfactual episode evaluation (never added into portfolio ROI)."""

    episode_id: str
    symbol: str
    entry_at_ms: int
    candidate_direction: int
    candidate_net_bps: Decimal
    matched_long_net_bps: Decimal
    matched_short_net_bps: Decimal
    balanced_50_50_net_bps: Decimal
    incremental_vs_balanced_bps: Decimal
    incremental_vs_same_direction_bps: Decimal
    overlaps_prior_episode: bool
    is_funded_portfolio_position: bool = False


class MatchedEpisodeOracle:
    """Evaluates unfunded overlapping LONG, SHORT, and balanced 50/50 matched counterfactual episodes."""

    @staticmethod
    def evaluate_paired_episode(
        *,
        episode_id: str,
        symbol: str,
        entry_at_ms: int,
        candidate_direction: int,
        candidate_net_bps: Decimal,
        matched_long_net_bps: Decimal,
        matched_short_net_bps: Decimal,
        overlaps_prior_episode: bool = False,
    ) -> MatchedEpisodeResult:
        with decimal_context():
            balanced_bps = round_ledger_usdt(
                (matched_long_net_bps + matched_short_net_bps) / Decimal(2)
            )
            inc_balanced = round_ledger_usdt(candidate_net_bps - balanced_bps)
            same_dir_bps = (
                matched_long_net_bps
                if candidate_direction == 1
                else matched_short_net_bps
            )
            inc_same_dir = round_ledger_usdt(candidate_net_bps - same_dir_bps)
            return MatchedEpisodeResult(
                episode_id=episode_id,
                symbol=symbol,
                entry_at_ms=entry_at_ms,
                candidate_direction=candidate_direction,
                candidate_net_bps=round_ledger_usdt(candidate_net_bps),
                matched_long_net_bps=round_ledger_usdt(matched_long_net_bps),
                matched_short_net_bps=round_ledger_usdt(matched_short_net_bps),
                balanced_50_50_net_bps=balanced_bps,
                incremental_vs_balanced_bps=inc_balanced,
                incremental_vs_same_direction_bps=inc_same_dir,
                overlaps_prior_episode=overlaps_prior_episode,
                is_funded_portfolio_position=False,
            )
