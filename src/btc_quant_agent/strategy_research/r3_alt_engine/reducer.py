"""Pure deterministic state reducer applying events and generating double-entry postings."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    DECIMAL_CTX,
    quantize12dp,
)
from btc_quant_agent.strategy_research.r3_alt_engine.journal import (
    compute_journal_chain_hash,
    validate_event,
    validate_postings_batch,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    AccountType,
    CompletedTrade,
    Direction,
    EngineState,
    Event,
    EventKind,
    ExitReason,
    MemoAccountType,
    OwnerLedger,
    OwnerPhase,
    PendingExitSlice,
    Posting,
    ReplayConfig,
)
from btc_quant_agent.strategy_research.r3_alt_engine.money import (
    assert_invariants,
)


def reduce(
    state: EngineState,
    event: Event,
    config: ReplayConfig,
) -> tuple[EngineState, list[Posting], list[Event]]:
    """
    Apply a single event to EngineState producing a new immutable EngineState,
    a list of double-entry postings, and scheduled successor events.
    Atomically fails unchanged on conflict.
    """
    # 1. Validate event and check idempotent duplicates (Invariant I11)
    is_duplicate, _ = validate_event(state, event)
    if is_duplicate:
        # Duplicate accepted once without mutating financial state (T06)
        return state, [], []

    postings: list[Posting] = []
    scheduled_events: list[Event] = []

    # Copy mutable state containers for evolve
    new_owner_ledgers = dict(state.owner_ledgers)
    new_latest_marks = dict(state.latest_marks)
    new_source_close_marks = dict(state.source_close_marks)
    new_cooldown_until = dict(state.cooldown_until)
    new_killed_latches = dict(state.killed_latches)
    new_peak_E_r = dict(state.peak_E_r)
    new_event_registry = dict(state.event_registry)
    new_retest_states = dict(state.retest_states)
    new_consumed_retest = dict(state.consumed_retest_events)
    new_completed_trades = list(state.completed_trades)
    new_opening_posted = dict(state.opening_equity_posted)
    new_clock_ms = max(state.clock_ms, event.available_at_ms)
    new_latest_mark_close = state.latest_mark_close_ms

    # Register event ID and canonical digest
    new_event_registry[event.event_id] = event.payload_digest

    # Handle event kinds
    if event.kind == EventKind.OBSERVED_MARK:
        source_id = event.source_id or "SYNTHETIC_MARK"
        symbol = event.symbol
        close_ms = int(event.payload.get("close_ms", event.economic_at_ms))
        price_val = Decimal(str(event.payload.get("price", event.payload.get("close", 0))))
        mark_key = (source_id, symbol, close_ms)

        # Monotonic mark close watermark check (T02, I10)
        new_source_close_marks[mark_key] = price_val
        if close_ms >= new_latest_mark_close:
            new_latest_mark_close = close_ms
            new_latest_marks[symbol] = price_val

    elif event.kind == EventKind.ORDER_RESERVED:
        owner_key = event.owner_key
        notional_cover = quantize12dp(Decimal(str(event.payload.get("notional_cover", 0))))
        entry_fee_cover = quantize12dp(Decimal(str(event.payload.get("entry_fee_cover", 0))))
        exit_fee_cover = quantize12dp(Decimal(str(event.payload.get("exit_fee_cover", 0))))
        funding_future_cover = quantize12dp(Decimal(str(event.payload.get("funding_reserve", 0))))

        reserved_ol = OwnerLedger(
            owner_key=owner_key,
            candidate_id=event.candidate_id,
            symbol=event.symbol,
            direction=Direction[event.payload.get("direction", "LONG")] if "direction" in event.payload else None,
            phase=OwnerPhase.RESERVED,
            enc_notional=notional_cover,
            enc_fee=entry_fee_cover,
            enc_exit_fee=exit_fee_cover,
            enc_funding_future=funding_future_cover,
            initial_stop=quantize12dp(Decimal(str(event.payload.get("initial_stop", 0)))),
            target=quantize12dp(Decimal(str(event.payload.get("target", 0)))),
            max_hold_ms=int(event.payload.get("max_hold_ms", 0)),
            retest_event_id=event.payload.get("retest_event_id"),
        )
        new_owner_ledgers[owner_key] = reserved_ol

        # Balanced memo encumbrances
        total_memo_cover = notional_cover + entry_fee_cover + exit_fee_cover + funding_future_cover
        if total_memo_cover > Decimal(0):
            postings.append(
                Posting(
                    dr_account=MemoAccountType.ENC_NOTIONAL,
                    cr_account=MemoAccountType.MEMO_CONTRA,
                    amount=total_memo_cover,
                    owner_key=owner_key,
                    event_id=event.event_id,
                    is_memo=True,
                    timestamp_ms=event.economic_at_ms,
                    cause_id=event.order_id,
                )
            )

    elif event.kind == EventKind.ECONOMIC_FILL:
        owner_key = event.owner_key
        fill_ol = new_owner_ledgers.get(owner_key)
        qty = Decimal(str(event.payload.get("quantity", 0)))
        raw_price = Decimal(str(event.payload.get("raw_price", 0)))
        effective_price = Decimal(str(event.payload.get("effective_price", 0)))
        fee_usdt = quantize12dp(Decimal(str(event.payload.get("fee_usdt", 0))))
        dir_val = Direction[event.payload.get("direction", "LONG")] if "direction" in event.payload else (fill_ol.direction if fill_ol else Direction.LONG)

        if fill_ol:
            # Atomic fee notice conversion (T34, AM02):
            # When entry fee becomes a visible payable, entry fee cover enc_fee is reduced
            # to avoid double deducting the fee from free capital A!
            new_enc_fee = max(Decimal(0), fill_ol.enc_fee - fee_usdt)
            updated_ol = OwnerLedger(
                owner_key=owner_key,
                candidate_id=fill_ol.candidate_id,
                symbol=fill_ol.symbol,
                direction=dir_val,
                phase=OwnerPhase.UNACKED_OPEN,
                cash_settled=fill_ol.cash_settled,
                trade_receivable=fill_ol.trade_receivable,
                trade_payable=fill_ol.trade_payable,
                fee_payable=fill_ol.fee_payable + fee_usdt,
                funding_payable=fill_ol.funding_payable,
                realized_gain=fill_ol.realized_gain,
                realized_loss=fill_ol.realized_loss,
                fee_expense=fill_ol.fee_expense + fee_usdt,
                funding_expense=fill_ol.funding_expense,
                enc_notional=fill_ol.enc_notional,
                enc_fee=new_enc_fee,
                enc_exit_fee=fill_ol.enc_exit_fee,
                enc_funding_future=fill_ol.enc_funding_future,
                enc_funding_dedicated=fill_ol.enc_funding_dedicated,
                enc_shortfall=fill_ol.enc_shortfall,
                quantity=qty,
                entry_price=effective_price,
                entry_time_ms=event.economic_at_ms,
                initial_stop=fill_ol.initial_stop,
                target=fill_ol.target,
                max_hold_ms=fill_ol.max_hold_ms,
                retest_event_id=fill_ol.retest_event_id,
            )
            new_owner_ledgers[owner_key] = updated_ol

        if fee_usdt > Decimal(0):
            # Fee accrual: Dr FEE_EXPENSE / Cr FEE_PAYABLE
            postings.append(
                Posting(
                    dr_account=AccountType.FEE_EXPENSE,
                    cr_account=AccountType.FEE_PAYABLE,
                    amount=fee_usdt,
                    owner_key=owner_key,
                    event_id=event.event_id,
                    is_memo=False,
                    timestamp_ms=event.economic_at_ms,
                    cause_id=event.fill_id,
                )
            )

    elif event.kind == EventKind.FILL_ACK:
        owner_key = event.owner_key
        ack_ol = new_owner_ledgers.get(owner_key)
        fee_to_settle = quantize12dp(Decimal(str(event.payload.get("fee_usdt", ack_ol.fee_payable if ack_ol else 0))))

        if ack_ol:
            remaining_fee_payable = max(Decimal(0), ack_ol.fee_payable - fee_to_settle)
            new_cash = ack_ol.cash_settled - fee_to_settle
            released_notional = ack_ol.enc_notional

            updated_ol = OwnerLedger(
                owner_key=owner_key,
                candidate_id=ack_ol.candidate_id,
                symbol=ack_ol.symbol,
                direction=ack_ol.direction,
                phase=OwnerPhase.ACKED_OPEN,
                cash_settled=new_cash,
                trade_receivable=ack_ol.trade_receivable,
                trade_payable=ack_ol.trade_payable,
                fee_payable=remaining_fee_payable,
                funding_payable=ack_ol.funding_payable,
                realized_gain=ack_ol.realized_gain,
                realized_loss=ack_ol.realized_loss,
                fee_expense=ack_ol.fee_expense,
                funding_expense=ack_ol.funding_expense,
                enc_notional=Decimal(0),
                enc_fee=Decimal(0),
                enc_exit_fee=ack_ol.enc_exit_fee,
                enc_funding_future=ack_ol.enc_funding_future,
                enc_funding_dedicated=ack_ol.enc_funding_dedicated,
                enc_shortfall=ack_ol.enc_shortfall,
                quantity=ack_ol.quantity,
                entry_price=ack_ol.entry_price,
                entry_time_ms=ack_ol.entry_time_ms,
                initial_stop=ack_ol.initial_stop,
                target=ack_ol.target,
                max_hold_ms=ack_ol.max_hold_ms,
                retest_event_id=ack_ol.retest_event_id,
            )
            new_owner_ledgers[owner_key] = updated_ol

            if fee_to_settle > Decimal(0):
                # Settle fee against cash: Dr FEE_PAYABLE / Cr CASH
                postings.append(
                    Posting(
                        dr_account=AccountType.FEE_PAYABLE,
                        cr_account=AccountType.CASH,
                        amount=fee_to_settle,
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=False,
                        timestamp_ms=event.available_at_ms,
                        cause_id=event.cause_id or event.fill_id,
                    )
                )

            if released_notional > Decimal(0):
                postings.append(
                    Posting(
                        dr_account=MemoAccountType.MEMO_CONTRA,
                        cr_account=MemoAccountType.ENC_NOTIONAL,
                        amount=released_notional,
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=True,
                        timestamp_ms=event.available_at_ms,
                        cause_id=event.fill_id,
                    )
                )

    elif event.kind == EventKind.ECONOMIC_EXIT:
        owner_key = event.owner_key
        exit_ol = new_owner_ledgers.get(owner_key)
        exit_qty = Decimal(str(event.payload.get("quantity", exit_ol.quantity if exit_ol else 0)))
        raw_price = Decimal(str(event.payload.get("raw_price", 0)))
        effective_price = Decimal(str(event.payload.get("effective_price", 0)))
        reason = ExitReason[event.payload.get("exit_reason", "STOP_LOSS")]
        exit_fee = quantize12dp(Decimal(str(event.payload.get("exit_fee", 0))))
        slice_id = str(event.payload.get("slice_id", f"SL_{event.event_id}"))

        if exit_ol:
            direction_sign = exit_ol.direction.sign if exit_ol.direction else 1
            gross_pnl = quantize12dp(
                DECIMAL_CTX.multiply(
                    exit_qty,
                    DECIMAL_CTX.multiply(
                        DECIMAL_CTX.subtract(effective_price, exit_ol.entry_price),
                        Decimal(direction_sign),
                    ),
                )
            )
            is_loss = gross_pnl < Decimal(0)

            new_slice = PendingExitSlice(
                slice_id=slice_id,
                quantity=exit_qty,
                raw_price=raw_price,
                effective_price=effective_price,
                gross_pnl=gross_pnl,
                exit_fee=exit_fee,
                exit_time_ms=event.economic_at_ms,
                available_at_ms=event.available_at_ms,
                exit_reason=reason,
                is_loss=is_loss,
                is_acknowledged=False,
            )

            rem_qty = max(Decimal(0), exit_ol.quantity - exit_qty)
            new_tp = exit_ol.trade_payable + (abs(gross_pnl) if is_loss else Decimal(0))
            new_tr = exit_ol.trade_receivable + (gross_pnl if not is_loss else Decimal(0))

            updated_ol = OwnerLedger(
                owner_key=owner_key,
                candidate_id=exit_ol.candidate_id,
                symbol=exit_ol.symbol,
                direction=exit_ol.direction,
                phase=OwnerPhase.EXIT_PENDING,
                cash_settled=exit_ol.cash_settled,
                trade_receivable=new_tr,
                trade_payable=new_tp,
                fee_payable=exit_ol.fee_payable + exit_fee,
                funding_payable=exit_ol.funding_payable,
                realized_gain=exit_ol.realized_gain + (gross_pnl if not is_loss else Decimal(0)),
                realized_loss=exit_ol.realized_loss + (abs(gross_pnl) if is_loss else Decimal(0)),
                fee_expense=exit_ol.fee_expense + exit_fee,
                funding_expense=exit_ol.funding_expense,
                enc_notional=exit_ol.enc_notional,
                enc_fee=exit_ol.enc_fee,
                enc_exit_fee=Decimal(0),
                enc_funding_future=exit_ol.enc_funding_future,
                enc_funding_dedicated=exit_ol.enc_funding_dedicated,
                enc_shortfall=exit_ol.enc_shortfall,
                quantity=rem_qty,
                entry_price=exit_ol.entry_price,
                entry_time_ms=exit_ol.entry_time_ms,
                initial_stop=exit_ol.initial_stop,
                target=exit_ol.target,
                max_hold_ms=exit_ol.max_hold_ms,
                pending_exit_slices=exit_ol.pending_exit_slices + (new_slice,),
                retest_event_id=exit_ol.retest_event_id,
            )
            new_owner_ledgers[owner_key] = updated_ol

            # Update cooldown: max(previous, ceil_valid_exit + 14400000) (T08, I09)
            exit_ceil_ms = ((event.economic_at_ms + 59_999) // 60_000) * 60_000
            new_cooldown_ts = exit_ceil_ms + 14_400_000
            cd_key = (event.book_id, exit_ol.symbol)
            prev_cd = new_cooldown_until.get(cd_key, 0)
            new_cooldown_until[cd_key] = max(prev_cd, new_cooldown_ts)

            if is_loss:
                postings.append(
                    Posting(
                        dr_account=AccountType.REALIZED_LOSS,
                        cr_account=AccountType.TRADE_PAYABLE,
                        amount=abs(gross_pnl),
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=False,
                        timestamp_ms=event.economic_at_ms,
                        cause_id=slice_id,
                    )
                )
            else:
                postings.append(
                    Posting(
                        dr_account=AccountType.TRADE_RECEIVABLE,
                        cr_account=AccountType.REALIZED_GAIN,
                        amount=gross_pnl,
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=False,
                        timestamp_ms=event.economic_at_ms,
                        cause_id=slice_id,
                    )
                )

            if exit_fee > Decimal(0):
                postings.append(
                    Posting(
                        dr_account=AccountType.FEE_EXPENSE,
                        cr_account=AccountType.FEE_PAYABLE,
                        amount=exit_fee,
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=False,
                        timestamp_ms=event.economic_at_ms,
                        cause_id=slice_id,
                    )
                )

    elif event.kind == EventKind.EXIT_ACK:
        owner_key = event.owner_key
        exit_ack_ol = new_owner_ledgers.get(owner_key)
        slice_id = str(event.payload.get("slice_id", event.cause_id))

        if exit_ack_ol:
            updated_slices: list[PendingExitSlice] = []
            settled_cash_delta = Decimal(0)
            trade_to_record: CompletedTrade | None = None

            for s in exit_ack_ol.pending_exit_slices:
                if (s.slice_id == slice_id or not slice_id) and not s.is_acknowledged:
                    ack_slice = PendingExitSlice(
                        slice_id=s.slice_id,
                        quantity=s.quantity,
                        raw_price=s.raw_price,
                        effective_price=s.effective_price,
                        gross_pnl=s.gross_pnl,
                        exit_fee=s.exit_fee,
                        exit_time_ms=s.exit_time_ms,
                        available_at_ms=s.available_at_ms,
                        exit_reason=s.exit_reason,
                        is_loss=s.is_loss,
                        is_acknowledged=True,
                    )
                    updated_slices.append(ack_slice)

                    if s.is_loss:
                        settled_cash_delta = DECIMAL_CTX.subtract(settled_cash_delta, abs(s.gross_pnl))
                        postings.append(
                            Posting(
                                dr_account=AccountType.TRADE_PAYABLE,
                                cr_account=AccountType.CASH,
                                amount=abs(s.gross_pnl),
                                owner_key=owner_key,
                                event_id=event.event_id,
                                is_memo=False,
                                timestamp_ms=event.available_at_ms,
                                cause_id=s.slice_id,
                            )
                        )
                    else:
                        settled_cash_delta = DECIMAL_CTX.add(settled_cash_delta, s.gross_pnl)
                        postings.append(
                            Posting(
                                dr_account=AccountType.CASH,
                                cr_account=AccountType.TRADE_RECEIVABLE,
                                amount=s.gross_pnl,
                                owner_key=owner_key,
                                event_id=event.event_id,
                                is_memo=False,
                                timestamp_ms=event.available_at_ms,
                                cause_id=s.slice_id,
                            )
                        )

                    if s.exit_fee > Decimal(0):
                        settled_cash_delta = DECIMAL_CTX.subtract(settled_cash_delta, s.exit_fee)
                        postings.append(
                            Posting(
                                dr_account=AccountType.FEE_PAYABLE,
                                cr_account=AccountType.CASH,
                                amount=s.exit_fee,
                                owner_key=owner_key,
                                event_id=event.event_id,
                                is_memo=False,
                                timestamp_ms=event.available_at_ms,
                                cause_id=s.slice_id,
                            )
                        )

                    hold_mins = (s.exit_time_ms - exit_ack_ol.entry_time_ms) // 60_000
                    trade_to_record = CompletedTrade(
                        trade_id=f"TR_{s.slice_id}",
                        candidate_id=exit_ack_ol.candidate_id,
                        symbol=exit_ack_ol.symbol,
                        direction=exit_ack_ol.direction or Direction.LONG,
                        quantity=s.quantity,
                        effective_entry=exit_ack_ol.entry_price,
                        raw_entry=exit_ack_ol.entry_price,
                        effective_exit=s.effective_price,
                        raw_exit=s.raw_price,
                        entry_time_ms=exit_ack_ol.entry_time_ms,
                        exit_time_ms=s.exit_time_ms,
                        holding_minutes=hold_mins,
                        exit_reason=s.exit_reason,
                        entry_fee_usdt=Decimal(0),
                        exit_fee_usdt=s.exit_fee,
                        total_fees_usdt=s.exit_fee,
                        total_funding_usdt=Decimal(0),
                        gross_pnl_usdt=s.gross_pnl,
                        net_pnl_usdt=s.gross_pnl - s.exit_fee,
                        entry_notional_usdt=s.quantity * exit_ack_ol.entry_price,
                        initial_risk_dollars=abs(exit_ack_ol.entry_price - exit_ack_ol.initial_stop) * s.quantity,
                        net_bps=((s.gross_pnl - s.exit_fee) / (s.quantity * exit_ack_ol.entry_price)) * Decimal(10000) if s.quantity * exit_ack_ol.entry_price > 0 else Decimal(0),
                        net_r=(s.gross_pnl - s.exit_fee) / (abs(exit_ack_ol.entry_price - exit_ack_ol.initial_stop) * s.quantity) if abs(exit_ack_ol.entry_price - exit_ack_ol.initial_stop) * s.quantity > 0 else None,
                        retest_event_id=exit_ack_ol.retest_event_id,
                        position_id=owner_key.position_id,
                    )
                else:
                    updated_slices.append(s)

            if trade_to_record:
                new_completed_trades.append(trade_to_record)

            all_acked = all(s.is_acknowledged for s in updated_slices)
            new_phase = OwnerPhase.CLOSED_UNSETTLED if (all_acked and exit_ack_ol.quantity == Decimal(0)) else exit_ack_ol.phase

            new_cash = exit_ack_ol.cash_settled + settled_cash_delta
            new_tp = max(Decimal(0), exit_ack_ol.trade_payable - (abs(trade_to_record.gross_pnl_usdt) if trade_to_record and trade_to_record.gross_pnl_usdt < 0 else Decimal(0)))
            new_tr = max(Decimal(0), exit_ack_ol.trade_receivable - (trade_to_record.gross_pnl_usdt if trade_to_record and trade_to_record.gross_pnl_usdt > 0 else Decimal(0)))
            new_fp = max(Decimal(0), exit_ack_ol.fee_payable - (trade_to_record.exit_fee_usdt if trade_to_record else Decimal(0)))

            updated_ol = OwnerLedger(
                owner_key=owner_key,
                candidate_id=exit_ack_ol.candidate_id,
                symbol=exit_ack_ol.symbol,
                direction=exit_ack_ol.direction,
                phase=new_phase,
                cash_settled=new_cash,
                trade_receivable=new_tr,
                trade_payable=new_tp,
                fee_payable=new_fp,
                funding_payable=exit_ack_ol.funding_payable,
                realized_gain=exit_ack_ol.realized_gain,
                realized_loss=exit_ack_ol.realized_loss,
                fee_expense=exit_ack_ol.fee_expense,
                funding_expense=exit_ack_ol.funding_expense,
                enc_notional=exit_ack_ol.enc_notional,
                enc_fee=exit_ack_ol.enc_fee,
                enc_exit_fee=exit_ack_ol.enc_exit_fee,
                enc_funding_future=exit_ack_ol.enc_funding_future,
                enc_funding_dedicated=exit_ack_ol.enc_funding_dedicated,
                enc_shortfall=exit_ack_ol.enc_shortfall,
                quantity=exit_ack_ol.quantity,
                entry_price=exit_ack_ol.entry_price,
                entry_time_ms=exit_ack_ol.entry_time_ms,
                initial_stop=exit_ack_ol.initial_stop,
                target=exit_ack_ol.target,
                max_hold_ms=exit_ack_ol.max_hold_ms,
                pending_exit_slices=tuple(updated_slices),
                retest_event_id=exit_ack_ol.retest_event_id,
            )
            new_owner_ledgers[owner_key] = updated_ol

    elif event.kind == EventKind.FUNDING_OBLIGATION:
        owner_key = event.owner_key
        fund_ol = new_owner_ledgers.get(owner_key)
        phase_str = event.payload.get("phase", "FINAL")
        charge_usdt = quantize12dp(Decimal(str(event.payload.get("charge_usdt", 0))))
        dedicated_cover = quantize12dp(Decimal(str(event.payload.get("dedicated_cover", 0))))

        if fund_ol:
            if phase_str == "CONDITIONAL":
                updated_ol = OwnerLedger(
                    owner_key=owner_key,
                    candidate_id=fund_ol.candidate_id,
                    symbol=fund_ol.symbol,
                    direction=fund_ol.direction,
                    phase=fund_ol.phase,
                    cash_settled=fund_ol.cash_settled,
                    trade_receivable=fund_ol.trade_receivable,
                    trade_payable=fund_ol.trade_payable,
                    fee_payable=fund_ol.fee_payable,
                    funding_payable=fund_ol.funding_payable,
                    realized_gain=fund_ol.realized_gain,
                    realized_loss=fund_ol.realized_loss,
                    fee_expense=fund_ol.fee_expense,
                    funding_expense=fund_ol.funding_expense,
                    enc_notional=fund_ol.enc_notional,
                    enc_fee=fund_ol.enc_fee,
                    enc_exit_fee=fund_ol.enc_exit_fee,
                    enc_funding_future=charge_usdt,
                    enc_funding_dedicated=fund_ol.enc_funding_dedicated,
                    enc_shortfall=fund_ol.enc_shortfall,
                    quantity=fund_ol.quantity,
                    entry_price=fund_ol.entry_price,
                    entry_time_ms=fund_ol.entry_time_ms,
                    initial_stop=fund_ol.initial_stop,
                    target=fund_ol.target,
                    max_hold_ms=fund_ol.max_hold_ms,
                    pending_exit_slices=fund_ol.pending_exit_slices,
                    retest_event_id=fund_ol.retest_event_id,
                )
                new_owner_ledgers[owner_key] = updated_ol
            else:
                shortfall = max(Decimal(0), charge_usdt - dedicated_cover)
                updated_ol = OwnerLedger(
                    owner_key=owner_key,
                    candidate_id=fund_ol.candidate_id,
                    symbol=fund_ol.symbol,
                    direction=fund_ol.direction,
                    phase=fund_ol.phase,
                    cash_settled=fund_ol.cash_settled,
                    trade_receivable=fund_ol.trade_receivable,
                    trade_payable=fund_ol.trade_payable,
                    fee_payable=fund_ol.fee_payable,
                    funding_payable=fund_ol.funding_payable + charge_usdt,
                    realized_gain=fund_ol.realized_gain,
                    realized_loss=fund_ol.realized_loss,
                    fee_expense=fund_ol.fee_expense,
                    funding_expense=fund_ol.funding_expense + charge_usdt,
                    enc_notional=fund_ol.enc_notional,
                    enc_fee=fund_ol.enc_fee,
                    enc_exit_fee=fund_ol.enc_exit_fee,
                    enc_funding_future=Decimal(0),
                    enc_funding_dedicated=dedicated_cover,
                    enc_shortfall=shortfall,
                    quantity=fund_ol.quantity,
                    entry_price=fund_ol.entry_price,
                    entry_time_ms=fund_ol.entry_time_ms,
                    initial_stop=fund_ol.initial_stop,
                    target=fund_ol.target,
                    max_hold_ms=fund_ol.max_hold_ms,
                    pending_exit_slices=fund_ol.pending_exit_slices,
                    retest_event_id=fund_ol.retest_event_id,
                )
                new_owner_ledgers[owner_key] = updated_ol

                postings.append(
                    Posting(
                        dr_account=AccountType.FUNDING_EXPENSE,
                        cr_account=AccountType.FUNDING_PAYABLE,
                        amount=charge_usdt,
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=False,
                        timestamp_ms=event.economic_at_ms,
                        cause_id=event.settlement_id,
                    )
                )

    elif event.kind == EventKind.FUNDING_ACK:
        owner_key = event.owner_key
        fund_ack_ol = new_owner_ledgers.get(owner_key)
        settle_amt = quantize12dp(Decimal(str(event.payload.get("charge_usdt", fund_ack_ol.funding_payable if fund_ack_ol else 0))))

        if fund_ack_ol:
            new_cash = fund_ack_ol.cash_settled - settle_amt
            remaining_payable = max(Decimal(0), fund_ack_ol.funding_payable - settle_amt)

            all_slices_acked = all(s.is_acknowledged for s in fund_ack_ol.pending_exit_slices)
            can_flatten = (
                fund_ack_ol.quantity == Decimal(0)
                and all_slices_acked
                and remaining_payable == Decimal(0)
                and fund_ack_ol.fee_payable == Decimal(0)
            )
            new_phase = OwnerPhase.FLAT if can_flatten else fund_ack_ol.phase

            updated_ol = OwnerLedger(
                owner_key=owner_key,
                candidate_id=fund_ack_ol.candidate_id,
                symbol=fund_ack_ol.symbol,
                direction=fund_ack_ol.direction,
                phase=new_phase,
                cash_settled=new_cash,
                trade_receivable=fund_ack_ol.trade_receivable,
                trade_payable=fund_ack_ol.trade_payable,
                fee_payable=fund_ack_ol.fee_payable,
                funding_payable=remaining_payable,
                realized_gain=fund_ack_ol.realized_gain,
                realized_loss=fund_ack_ol.realized_loss,
                fee_expense=fund_ack_ol.fee_expense,
                funding_expense=fund_ack_ol.funding_expense,
                enc_notional=fund_ack_ol.enc_notional,
                enc_fee=fund_ack_ol.enc_fee,
                enc_exit_fee=fund_ack_ol.enc_exit_fee,
                enc_funding_future=Decimal(0),
                enc_funding_dedicated=Decimal(0),
                enc_shortfall=Decimal(0),
                quantity=fund_ack_ol.quantity,
                entry_price=fund_ack_ol.entry_price,
                entry_time_ms=fund_ack_ol.entry_time_ms,
                initial_stop=fund_ack_ol.initial_stop,
                target=fund_ack_ol.target,
                max_hold_ms=fund_ack_ol.max_hold_ms,
                pending_exit_slices=fund_ack_ol.pending_exit_slices,
                is_tombstone=can_flatten,
                retest_event_id=fund_ack_ol.retest_event_id,
            )
            new_owner_ledgers[owner_key] = updated_ol

            if settle_amt > Decimal(0):
                postings.append(
                    Posting(
                        dr_account=AccountType.FUNDING_PAYABLE,
                        cr_account=AccountType.CASH,
                        amount=settle_amt,
                        owner_key=owner_key,
                        event_id=event.event_id,
                        is_memo=False,
                        timestamp_ms=event.available_at_ms,
                        cause_id=event.cause_id or event.settlement_id,
                    )
                )

    elif event.kind == EventKind.RISK_KILL:
        new_killed_latches[event.book_id] = True

    # Validate posting batch double-entry invariants
    validate_postings_batch(postings)

    # Compute new journal chain hash
    new_chain_hash = compute_journal_chain_hash(state.journal_chain_hash, postings)

    # Construct new immutable state
    new_state = EngineState(
        clock_ms=new_clock_ms,
        latest_mark_close_ms=new_latest_mark_close,
        latest_marks=new_latest_marks,
        owner_ledgers=new_owner_ledgers,
        postings=state.postings + tuple(postings),
        retest_states=new_retest_states,
        cooldown_until=new_cooldown_until,
        killed_latches=new_killed_latches,
        peak_E_r=new_peak_E_r,
        journal_chain_hash=new_chain_hash,
        event_registry=new_event_registry,
        source_close_marks=new_source_close_marks,
        consumed_retest_events=new_consumed_retest,
        completed_trades=tuple(new_completed_trades),
        last_entry_4h_time_ms=state.last_entry_4h_time_ms,
        opening_equity_posted=new_opening_posted,
    )

    # Assert money invariants
    assert_invariants(new_state, event.book_id)

    return new_state, postings, scheduled_events
