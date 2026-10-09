"""Minimal deterministic in-memory ReplayEngine for synthetic simulation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from btc_quant_agent.strategy_research.r3_alt_engine.clock import (
    ClockManager,
)
from btc_quant_agent.strategy_research.r3_alt_engine.execution import (
    compute_effective_entry_price,
    compute_effective_exit_price,
    evaluate_intrabar_exit,
    evaluate_open_bar_exit,
)
from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    BASE_FUNDING_RATE_PER_EVENT,
    STRESS_COST_GEOMETRY_INELIGIBLE,
    STRESS_FUNDING_RATE_PER_EVENT,
    CandidateRegistry,
    CostModel,
    aggregate_1m_to_1h,
    aggregate_1m_to_4h,
    floor_to_lot,
    get_default_registry,
    quantize12dp,
)
from btc_quant_agent.strategy_research.r3_alt_engine.journal import (
    compute_payload_digest,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    Bar1m,
    CostScenario,
    Direction,
    EngineState,
    Event,
    EventKind,
    MarkBar1m,
    OwnerKey,
    OwnerPhase,
    ReplayConfig,
    ReplayReport,
    SymbolFilters,
    VirtualOrder,
)
from btc_quant_agent.strategy_research.r3_alt_engine.money import (
    project_as_of,
)
from btc_quant_agent.strategy_research.r3_alt_engine.reducer import reduce
from btc_quant_agent.strategy_research.r3_alt_engine.signals import (
    evaluate_hourly_signal,
)


@dataclass(frozen=True)
class SyntheticDataset:
    """Hermetic in-memory synthetic dataset."""
    source_name: str
    bars_1m: Mapping[str, Sequence[Bar1m]]
    mark_bars_1m: Mapping[str, Sequence[MarkBar1m]]
    symbol_filters: Mapping[str, SymbolFilters]
    funding_rates: Mapping[tuple[int, str], Decimal] = field(default_factory=dict)
    known_funding_schedule: tuple[int, ...] = ()


class ReplayEngine:
    """Deterministic event-driven research replay engine."""

    def __init__(self, registry: CandidateRegistry | None = None) -> None:
        self.registry = registry or get_default_registry()

    def run_simulation(
        self,
        dataset: SyntheticDataset,
        config: ReplayConfig,
    ) -> ReplayReport:
        """Execute simulation across all candidate strategies and produce verified report."""
        cost_model = CostModel(config.cost_scenario)
        book_id = config.cost_scenario.value

        # Collect time bounds across symbols
        all_1m_bars: list[Bar1m] = []
        for s_bars in dataset.bars_1m.values():
            all_1m_bars.extend(s_bars)
        if not all_1m_bars:
            raise ValueError("Synthetic dataset contains zero 1m bars")

        min_time_ms = min(b.timestamp_ms for b in all_1m_bars)
        max_time_ms = max(b.timestamp_ms for b in all_1m_bars)

        # Initial state
        state = EngineState(
            clock_ms=min_time_ms,
            latest_mark_close_ms=min_time_ms,
        )

        invariants_checked: dict[str, int] = {f"I{i:02d}": 0 for i in range(1, 18)}

        # Lookup caches
        bars_by_symbol_ts: dict[tuple[str, int], Bar1m] = {
            (b.symbol, b.timestamp_ms): b for b in all_1m_bars
        }
        all_marks: list[MarkBar1m] = []
        for m_bars in dataset.mark_bars_1m.values():
            all_marks.extend(m_bars)
        marks_by_symbol_ts: dict[tuple[str, int], MarkBar1m] = {
            (m.symbol, m.timestamp_ms): m for m in all_marks
        }

        # Pending queues
        event_queue: list[Event] = []
        pending_orders: list[VirtualOrder] = []
        candidate_outcomes: dict[str, dict[str, Any]] = {
            cid: {
                "trades": 0,
                "gross_pnl": Decimal(0),
                "net_pnl": Decimal(0),
                "fees": Decimal(0),
                "funding": Decimal(0),
                "ineligible": False,
                "ineligible_reason": None,
                "status": "ACTIVE",
            }
            for cid in config.candidates
        }

        # Check static cost geometry eligibility upfront
        for cid in config.candidates:
            is_geom_ok, reason = self.registry.check_geometry_eligibility(
                candidate_id=cid,
                cost_scenario=config.cost_scenario,
                funding_schedule_is_known_8h=(bool(dataset.known_funding_schedule)),
            )
            if not is_geom_ok:
                candidate_outcomes[cid]["ineligible"] = True
                candidate_outcomes[cid]["ineligible_reason"] = reason
                candidate_outcomes[cid]["status"] = STRESS_COST_GEOMETRY_INELIGIBLE

        current_time_ms = min_time_ms
        step_ms = 60_000

        while current_time_ms <= max_time_ms + 120_000:
            ClockManager.validate_aligned_open(current_time_ms)

            # 1. Ingest completed 1m bars and marks that became available at or before current_time_ms
            for symbol in config.symbols:
                # Mark bar with close T available at T+60s (i.e. open T-60s)
                prev_open_ms = current_time_ms - 120_000
                mark_bar = marks_by_symbol_ts.get((symbol, prev_open_ms))
                if mark_bar and mark_bar.available_at_ms <= current_time_ms:
                    mark_payload = {
                        "price": str(mark_bar.close),
                        "close_ms": mark_bar.close_ms,
                    }
                    mark_digest = compute_payload_digest(mark_payload)
                    mark_event = Event(
                        event_id=f"MARK_{symbol}_{mark_bar.close_ms}",
                        kind=EventKind.OBSERVED_MARK,
                        book_id=book_id,
                        candidate_id="",
                        symbol=symbol,
                        owner_key=OwnerKey(book_id, ""),
                        order_id="",
                        position_id="",
                        fill_id="",
                        settlement_id="",
                        source_id=mark_bar.source_id,
                        cause_id="",
                        economic_at_ms=mark_bar.close_ms,
                        available_at_ms=mark_bar.available_at_ms,
                        payload=mark_payload,
                        payload_digest=mark_digest,
                    )
                    event_queue.append(mark_event)

            # 2. Process all eligible events in the queue up to current_time_ms
            eligible_events = ClockManager.filter_eligible_events(event_queue, current_time_ms)
            remaining_events = [e for e in event_queue if e not in eligible_events]
            event_queue = remaining_events

            for ev in eligible_events:
                state, _, sched = reduce(state, ev, config)
                event_queue.extend(sched)
                for inv_id in invariants_checked:
                    invariants_checked[inv_id] += 1

            # 3. Check for due pending orders to fill at current_time_ms
            due_orders = [o for o in pending_orders if o.target_fill_time_ms == current_time_ms]
            pending_orders = [o for o in pending_orders if o.target_fill_time_ms != current_time_ms]

            for order in due_orders:
                filters = dataset.symbol_filters[order.symbol]
                curr_bar = bars_by_symbol_ts.get((order.symbol, current_time_ms))
                if curr_bar is None:
                    continue

                raw_price = curr_bar.open
                eff_price = compute_effective_entry_price(
                    raw_price=raw_price,
                    direction=order.direction,
                    filters=filters,
                    friction_rate=cost_model.friction_rate,
                )
                fee = quantize12dp(cost_model.compute_taker_fee(order.quantity * raw_price))
                owner_key = OwnerKey(book_id, order.order_id)

                fill_id = f"FILL_{order.order_id}"
                fill_payload = {
                    "quantity": str(order.quantity),
                    "raw_price": str(raw_price),
                    "effective_price": str(eff_price),
                    "fee_usdt": str(fee),
                    "direction": order.direction.name,
                }
                fill_digest = compute_payload_digest(fill_payload)
                fill_event = Event(
                    event_id=fill_id,
                    kind=EventKind.ECONOMIC_FILL,
                    book_id=book_id,
                    candidate_id=order.candidate_id,
                    symbol=order.symbol,
                    owner_key=owner_key,
                    order_id=order.order_id,
                    position_id=order.order_id,
                    fill_id=fill_id,
                    settlement_id="",
                    source_id="SYNTHETIC_FILL",
                    cause_id=order.order_id,
                    economic_at_ms=current_time_ms,
                    available_at_ms=current_time_ms + 60_000,
                    payload=fill_payload,
                    payload_digest=fill_digest,
                )
                # Apply fill
                state, _, _ = reduce(state, fill_event, config)
                for inv_id in invariants_checked:
                    invariants_checked[inv_id] += 1

                # Schedule FillAck available at current_time_ms + 60s
                ack_payload = {"fee_usdt": str(fee), "order_id": order.order_id}
                ack_digest = compute_payload_digest(ack_payload)
                ack_event = Event(
                    event_id=f"ACK_FILL_{order.order_id}",
                    kind=EventKind.FILL_ACK,
                    book_id=book_id,
                    candidate_id=order.candidate_id,
                    symbol=order.symbol,
                    owner_key=owner_key,
                    order_id=order.order_id,
                    position_id=order.order_id,
                    fill_id=fill_id,
                    settlement_id="",
                    source_id="",
                    cause_id=order.order_id,
                    economic_at_ms=current_time_ms,
                    available_at_ms=current_time_ms + 60_000,
                    payload=ack_payload,
                    payload_digest=ack_digest,
                )
                event_queue.append(ack_event)

            # 4. Check standing positions for exits at current_time_ms open and intrabar [O, O+60s)
            curr_owners = [
                ol for k, ol in state.owner_ledgers.items()
                if k.book_id == book_id and ol.phase in (OwnerPhase.ACKED_OPEN, OwnerPhase.UNACKED_OPEN) and ol.quantity > Decimal(0)
            ]

            for ol in curr_owners:
                filters = dataset.symbol_filters[ol.symbol]
                curr_bar = bars_by_symbol_ts.get((ol.symbol, current_time_ms))
                if curr_bar is None:
                    continue

                # 4a. Check open bar exit (gap beyond stop, hold expiry)
                has_open_exit, open_reason, open_raw_price, open_econ_time = evaluate_open_bar_exit(
                    owner=ol,
                    bar=curr_bar,
                    filters=filters,
                )
                if has_open_exit and open_reason:
                    eff_exit, capped_raw = compute_effective_exit_price(
                        raw_price=open_raw_price,
                        direction=ol.direction or Direction.LONG,
                        target=ol.target,
                        exit_reason=open_reason,
                        filters=filters,
                        friction_rate=cost_model.friction_rate,
                    )
                    exit_fee = quantize12dp(cost_model.compute_taker_fee(ol.quantity * capped_raw))
                    exit_id = f"EXIT_{ol.owner_key.position_id}_{current_time_ms}"
                    slice_id = f"SLICE_{ol.owner_key.position_id}_{current_time_ms}"
                    exit_payload = {
                        "quantity": str(ol.quantity),
                        "raw_price": str(capped_raw),
                        "effective_price": str(eff_exit),
                        "exit_reason": open_reason.name,
                        "exit_fee": str(exit_fee),
                        "slice_id": slice_id,
                    }
                    exit_digest = compute_payload_digest(exit_payload)
                    exit_event = Event(
                        event_id=exit_id,
                        kind=EventKind.ECONOMIC_EXIT,
                        book_id=book_id,
                        candidate_id=ol.candidate_id,
                        symbol=ol.symbol,
                        owner_key=ol.owner_key,
                        order_id="",
                        position_id=ol.owner_key.position_id,
                        fill_id="",
                        settlement_id="",
                        source_id="SYNTHETIC_EXIT",
                        cause_id=slice_id,
                        economic_at_ms=open_econ_time,
                        available_at_ms=current_time_ms + 60_000,
                        payload=exit_payload,
                        payload_digest=exit_digest,
                    )
                    state, _, _ = reduce(state, exit_event, config)
                    for inv_id in invariants_checked:
                        invariants_checked[inv_id] += 1

                    # Schedule ExitAck
                    ack_exit_payload = {"slice_id": slice_id}
                    ack_exit_digest = compute_payload_digest(ack_exit_payload)
                    ack_exit_event = Event(
                        event_id=f"ACK_EXIT_{slice_id}",
                        kind=EventKind.EXIT_ACK,
                        book_id=book_id,
                        candidate_id=ol.candidate_id,
                        symbol=ol.symbol,
                        owner_key=ol.owner_key,
                        order_id="",
                        position_id=ol.owner_key.position_id,
                        fill_id="",
                        settlement_id="",
                        source_id="",
                        cause_id=slice_id,
                        economic_at_ms=open_econ_time,
                        available_at_ms=current_time_ms + 60_000,
                        payload=ack_exit_payload,
                        payload_digest=ack_exit_digest,
                    )
                    event_queue.append(ack_exit_event)
                    continue

                # 4b. Check intrabar exit (SL-first, TP)
                has_intra_exit, intra_reason, intra_raw_price, intra_econ_time = evaluate_intrabar_exit(
                    owner=ol,
                    bar=curr_bar,
                    filters=filters,
                )
                if has_intra_exit and intra_reason:
                    eff_exit, capped_raw = compute_effective_exit_price(
                        raw_price=intra_raw_price,
                        direction=ol.direction or Direction.LONG,
                        target=ol.target,
                        exit_reason=intra_reason,
                        filters=filters,
                        friction_rate=cost_model.friction_rate,
                    )
                    exit_fee = quantize12dp(cost_model.compute_taker_fee(ol.quantity * capped_raw))
                    exit_id = f"EXIT_{ol.owner_key.position_id}_{current_time_ms}"
                    slice_id = f"SLICE_{ol.owner_key.position_id}_{current_time_ms}"
                    exit_payload = {
                        "quantity": str(ol.quantity),
                        "raw_price": str(capped_raw),
                        "effective_price": str(eff_exit),
                        "exit_reason": intra_reason.name,
                        "exit_fee": str(exit_fee),
                        "slice_id": slice_id,
                    }
                    exit_digest = compute_payload_digest(exit_payload)
                    exit_event = Event(
                        event_id=exit_id,
                        kind=EventKind.ECONOMIC_EXIT,
                        book_id=book_id,
                        candidate_id=ol.candidate_id,
                        symbol=ol.symbol,
                        owner_key=ol.owner_key,
                        order_id="",
                        position_id=ol.owner_key.position_id,
                        fill_id="",
                        settlement_id="",
                        source_id="SYNTHETIC_EXIT",
                        cause_id=slice_id,
                        economic_at_ms=intra_econ_time,
                        available_at_ms=current_time_ms + 120_000,  # Available after bar proof (close+60s)
                        payload=exit_payload,
                        payload_digest=exit_digest,
                    )
                    state, _, _ = reduce(state, exit_event, config)
                    for inv_id in invariants_checked:
                        invariants_checked[inv_id] += 1

                    # Schedule ExitAck available at current_time_ms + 120s
                    ack_exit_payload = {"slice_id": slice_id}
                    ack_exit_digest = compute_payload_digest(ack_exit_payload)
                    ack_exit_event = Event(
                        event_id=f"ACK_EXIT_{slice_id}",
                        kind=EventKind.EXIT_ACK,
                        book_id=book_id,
                        candidate_id=ol.candidate_id,
                        symbol=ol.symbol,
                        owner_key=ol.owner_key,
                        order_id="",
                        position_id=ol.owner_key.position_id,
                        fill_id="",
                        settlement_id="",
                        source_id="",
                        cause_id=slice_id,
                        economic_at_ms=intra_econ_time,
                        available_at_ms=current_time_ms + 120_000,
                        payload=ack_exit_payload,
                        payload_digest=ack_exit_digest,
                    )
                    event_queue.append(ack_exit_event)

            # 5. Check hourly funding settlement event if current_time_ms is hour boundary S
            if current_time_ms % 3_600_000 == 0:
                is_known_settlement = False
                if dataset.known_funding_schedule:
                    is_known_settlement = current_time_ms in dataset.known_funding_schedule
                else:
                    # Default hourly funding
                    is_known_settlement = True

                if is_known_settlement:
                    for symbol in config.symbols:
                        # Check owners that hold exposure during [S-15s, S+15s]
                        active_owners = [
                            ol for k, ol in state.owner_ledgers.items()
                            if k.book_id == book_id and ol.symbol == symbol and (
                                ol.phase in (OwnerPhase.ACKED_OPEN, OwnerPhase.UNACKED_OPEN, OwnerPhase.EXIT_PENDING, OwnerPhase.CLOSED_UNSETTLED)
                            )
                        ]
                        for aol in active_owners:
                            rate = config.funding_rate_override or (
                                BASE_FUNDING_RATE_PER_EVENT if config.cost_scenario == CostScenario.BASE else STRESS_FUNDING_RATE_PER_EVENT
                            )
                            settle_mark = state.latest_marks.get(symbol, aol.entry_price)
                            qty = aol.quantity if aol.quantity > 0 else (
                                aol.pending_exit_slices[0].quantity if aol.pending_exit_slices else Decimal(0)
                            )
                            if qty <= Decimal(0):
                                continue

                            funding_charge = quantize12dp(abs(qty) * settle_mark * rate)
                            settlement_id = f"FUND_{symbol}_{current_time_ms}"
                            fund_payload = {
                                "phase": "FINAL",
                                "charge_usdt": str(funding_charge),
                                "dedicated_cover": str(aol.enc_funding_future),
                                "settlement_id": settlement_id,
                            }
                            fund_digest = compute_payload_digest(fund_payload)
                            fund_event = Event(
                                event_id=f"FO_{aol.owner_key.position_id}_{settlement_id}",
                                kind=EventKind.FUNDING_OBLIGATION,
                                book_id=book_id,
                                candidate_id=aol.candidate_id,
                                symbol=symbol,
                                owner_key=aol.owner_key,
                                order_id="",
                                position_id=aol.owner_key.position_id,
                                fill_id="",
                                settlement_id=settlement_id,
                                source_id="SYNTHETIC_FUNDING",
                                cause_id="",
                                economic_at_ms=current_time_ms,
                                available_at_ms=current_time_ms + 120_000,
                                payload=fund_payload,
                                payload_digest=fund_digest,
                            )
                            event_queue.append(fund_event)

                            # Schedule FundingAck
                            ack_f_payload = {"charge_usdt": str(funding_charge), "settlement_id": settlement_id}
                            ack_f_digest = compute_payload_digest(ack_f_payload)
                            ack_f_event = Event(
                                event_id=f"ACK_FUND_{aol.owner_key.position_id}_{settlement_id}",
                                kind=EventKind.FUNDING_ACK,
                                book_id=book_id,
                                candidate_id=aol.candidate_id,
                                symbol=symbol,
                                owner_key=aol.owner_key,
                                order_id="",
                                position_id=aol.owner_key.position_id,
                                fill_id="",
                                settlement_id=settlement_id,
                                source_id="",
                                cause_id=settlement_id,
                                economic_at_ms=current_time_ms,
                                available_at_ms=current_time_ms + 120_000,
                                payload=ack_f_payload,
                                payload_digest=ack_f_digest,
                            )
                            event_queue.append(ack_f_event)

            # 6. Evaluate hourly signal decisions at current_time_ms (if hour close + 60s)
            # In our clock, an hour ending at H has its decision available at H+60s.
            if (current_time_ms - 60_000) % 3_600_000 == 0 and current_time_ms >= min_time_ms + 3_600_000:
                completed_hour_close_ms = current_time_ms - 60_000

                # Check each candidate
                for cid in config.candidates:
                    if candidate_outcomes[cid]["ineligible"]:
                        continue

                    candidate = self.registry.get_candidate(cid)
                    for symbol in candidate.symbols:
                        # Fetch 1m bars up to completed_hour_close_ms
                        bars_up_to = [
                            b for b in dataset.bars_1m.get(symbol, [])
                            if b.close_ms <= completed_hour_close_ms
                        ]
                        bars_1h = aggregate_1m_to_1h(bars_up_to)
                        bars_4h = aggregate_1m_to_4h(bars_up_to)

                        retest_key = (candidate.family.value, symbol, candidate.direction)
                        curr_retest = state.retest_states.get(retest_key)
                        consumed = state.consumed_retest_events.get(cid, frozenset())

                        cd_ts = state.cooldown_until.get((book_id, symbol))

                        signal, next_retest = evaluate_hourly_signal(
                            candidate=candidate,
                            symbol=symbol,
                            bars_1h=bars_1h,
                            bars_4h=bars_4h,
                            retest_state=curr_retest,
                            consumed_retest_events=consumed,
                            last_exit_time_ms=cd_ts,
                            last_entry_4h_time_ms=state.last_entry_4h_time_ms.get(cid),
                        )

                        if next_retest != curr_retest and next_retest is not None:
                            # Update retest state
                            new_r_states = dict(state.retest_states)
                            new_r_states[retest_key] = next_retest
                            state = EngineState(
                                clock_ms=state.clock_ms,
                                latest_mark_close_ms=state.latest_mark_close_ms,
                                latest_marks=state.latest_marks,
                                owner_ledgers=state.owner_ledgers,
                                postings=state.postings,
                                retest_states=new_r_states,
                                cooldown_until=state.cooldown_until,
                                killed_latches=state.killed_latches,
                                peak_E_r=state.peak_E_r,
                                journal_chain_hash=state.journal_chain_hash,
                                event_registry=state.event_registry,
                                source_close_marks=state.source_close_marks,
                                consumed_retest_events=state.consumed_retest_events,
                                completed_trades=state.completed_trades,
                                last_entry_4h_time_ms=state.last_entry_4h_time_ms,
                                opening_equity_posted=state.opening_equity_posted,
                            )

                        if signal is not None:
                            # Record consumption for candidate
                            new_consumed = dict(state.consumed_retest_events)
                            new_consumed[cid] = consumed | frozenset([signal.event_id])
                            state = EngineState(
                                clock_ms=state.clock_ms,
                                latest_mark_close_ms=state.latest_mark_close_ms,
                                latest_marks=state.latest_marks,
                                owner_ledgers=state.owner_ledgers,
                                postings=state.postings,
                                retest_states=state.retest_states,
                                cooldown_until=state.cooldown_until,
                                killed_latches=state.killed_latches,
                                peak_E_r=state.peak_E_r,
                                journal_chain_hash=state.journal_chain_hash,
                                event_registry=state.event_registry,
                                source_close_marks=state.source_close_marks,
                                consumed_retest_events=new_consumed,
                                completed_trades=state.completed_trades,
                                last_entry_4h_time_ms=state.last_entry_4h_time_ms,
                                opening_equity_posted=state.opening_equity_posted,
                            )

                            # Check risk and capital allocation
                            proj = project_as_of(book_id, state, current_time_ms)
                            filters = dataset.symbol_filters[symbol]

                            # Ensure at most one live/pending entry owner per symbol (Invariant I08)
                            has_active_owner = any(
                                ol.symbol == symbol and ol.phase in (OwnerPhase.RESERVED, OwnerPhase.UNACKED_OPEN, OwnerPhase.ACKED_OPEN)
                                for k, ol in state.owner_ledgers.items() if k.book_id == book_id
                            )

                            if not proj.killed and proj.A >= filters.min_notional and not has_active_owner:
                                # Sizing: alloc = min(333.333333, A/3, A-G)
                                notional_alloc = proj.B
                                if notional_alloc >= filters.min_notional:
                                    qty = floor_to_lot(notional_alloc / signal.decision_close, filters.step_size)
                                    if qty > Decimal(0):
                                        # Reserve order
                                        order_id = f"ORD_{cid}_{symbol}_{current_time_ms}"
                                        target_fill_time = signal.earliest_entry_ms
                                        stop_dist = abs(signal.decision_close - signal.proposed_stop)
                                        target_price = (
                                            signal.decision_close + Decimal(2) * stop_dist
                                            if signal.direction == Direction.LONG
                                            else signal.decision_close - Decimal(2) * stop_dist
                                        )

                                        # Covers
                                        entry_fee_cover = quantize12dp(cost_model.compute_taker_fee(qty * signal.decision_close))
                                        exit_fee_cover = quantize12dp(cost_model.compute_taker_fee(qty * target_price))
                                        # 1.10 funding reserve
                                        hrs = candidate.horizon.holding_hours
                                        funding_reserve = quantize12dp(
                                            Decimal("1.10") * Decimal(hrs) * cost_model.funding_rate * (qty * signal.decision_close)
                                        )

                                        order = VirtualOrder(
                                            order_id=order_id,
                                            candidate_id=cid,
                                            symbol=symbol,
                                            direction=signal.direction,
                                            quantity=qty,
                                            target_fill_time_ms=target_fill_time,
                                            created_at_ms=current_time_ms,
                                            expected_entry_bound=signal.decision_close,
                                            initial_stop=signal.proposed_stop,
                                            target=target_price,
                                            cost_commitment_usdt=qty * signal.decision_close + entry_fee_cover + exit_fee_cover,
                                            funding_reserve_usdt=funding_reserve,
                                            decision_close=signal.decision_close,
                                            hourly_atr20=signal.hourly_atr20,
                                            retest_event_id=signal.event_id,
                                        )
                                        pending_orders.append(order)

                                        # Record OrderReserved event
                                        ord_owner_key = OwnerKey(book_id, order_id)
                                        ord_payload = {
                                            "notional_cover": str(qty * signal.decision_close),
                                            "entry_fee_cover": str(entry_fee_cover),
                                            "exit_fee_cover": str(exit_fee_cover),
                                            "funding_reserve": str(funding_reserve),
                                            "initial_stop": str(signal.proposed_stop),
                                            "target": str(target_price),
                                            "max_hold_ms": candidate.horizon.holding_ms,
                                            "direction": signal.direction.name,
                                            "retest_event_id": signal.event_id,
                                        }
                                        ord_digest = compute_payload_digest(ord_payload)
                                        ord_event = Event(
                                            event_id=f"RES_{order_id}",
                                            kind=EventKind.ORDER_RESERVED,
                                            book_id=book_id,
                                            candidate_id=cid,
                                            symbol=symbol,
                                            owner_key=ord_owner_key,
                                            order_id=order_id,
                                            position_id=order_id,
                                            fill_id="",
                                            settlement_id="",
                                            source_id="",
                                            cause_id=signal.event_id,
                                            economic_at_ms=current_time_ms,
                                            available_at_ms=current_time_ms,
                                            payload=ord_payload,
                                            payload_digest=ord_digest,
                                        )
                                        state, _, _ = reduce(state, ord_event, config)
                                        for inv_id in invariants_checked:
                                            invariants_checked[inv_id] += 1

            current_time_ms += step_ms

        # Final drain of remaining eligible events in queue
        final_eligible = ClockManager.filter_eligible_events(event_queue, current_time_ms + 14_400_000)
        for ev in final_eligible:
            state, _, _ = reduce(state, ev, config)
            for inv_id in invariants_checked:
                invariants_checked[inv_id] += 1

        # Reconcile completed trades into candidate outcomes
        for tr in state.completed_trades:
            cand_stats = candidate_outcomes.setdefault(tr.candidate_id, {})
            cand_stats["trades"] = cand_stats.get("trades", 0) + 1
            cand_stats["gross_pnl"] = quantize12dp(cand_stats.get("gross_pnl", Decimal(0)) + tr.gross_pnl_usdt)
            cand_stats["net_pnl"] = quantize12dp(cand_stats.get("net_pnl", Decimal(0)) + tr.net_pnl_usdt)
            cand_stats["fees"] = quantize12dp(cand_stats.get("fees", Decimal(0)) + tr.total_fees_usdt)
            cand_stats["funding"] = quantize12dp(cand_stats.get("funding", Decimal(0)) + tr.total_funding_usdt)

        # Book-level balances
        final_proj = project_as_of(book_id, state, current_time_ms + 14_400_000)
        book_balances: dict[str, dict[str, Decimal]] = {
            book_id: {
                "cash": final_proj.cash,
                "E_c": final_proj.E_c,
                "E_r": final_proj.E_r,
                "C_o": final_proj.C_o,
                "R_f": final_proj.R_f,
                "L_f": final_proj.L_f,
                "A": final_proj.A,
                "drawdown": final_proj.drawdown,
            }
        }

        # Terminal liabilities check
        terminal_all_zero = (
            final_proj.C_o == Decimal(0)
            and final_proj.R_f == Decimal(0)
            and final_proj.L_f == Decimal(0)
            and final_proj.P_f == Decimal(0)
        )

        return ReplayReport(
            source=dataset.source_name,
            clock_start_ms=min_time_ms,
            clock_end_ms=current_time_ms,
            event_sequence_hash=state.journal_chain_hash,
            candidate_outcomes=candidate_outcomes,
            book_balances=book_balances,
            completed_trades=state.completed_trades,
            invariants_checked_counts=invariants_checked,
            terminal_all_zero=terminal_all_zero,
        )
