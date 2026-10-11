"""Signed observed funding and mark-risk accounting for the two frozen R2 leads.

The settlement rate is a past cash flow, never a signal input. Trade fills and
stops remain those of the R2 last-trade replay. A minute Mark close is visible
only at the end of that minute; a boundary settlement uses the preceding close.
"""
from __future__ import annotations

import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    _effective,
    _fee,
    _index,
    _proposed,
    _slippage,
    episode,
)


def _event_clock(event: dict[str, Any]) -> int:
    return int(event.get("settlement_at", event.get("funding_time_ms")))


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not result.is_finite():
        raise ValueError(f"Nonfinite {label}")
    return result


def _validate_events(events: list[dict[str, Any]]) -> None:
    previous = -1
    for event in events:
        clock = _event_clock(event)
        if clock <= previous or clock < 0:
            raise ValueError("Funding events must be strictly increasing and unique")
        _decimal(event["rate"], "funding rate")
        previous = clock


def validate_mark(mark: np.ndarray, *, start_ms: int | None = None, end_ms: int | None = None) -> None:
    """Require dense chronological 1m source, with unambiguous positive OHLC."""
    if mark.ndim != 2 or mark.shape[1] != 5 or len(mark) == 0:
        raise ValueError("Mark must be nonempty Nx5 minute/OHLC")
    if not np.all(np.isfinite(mark)) or np.any(mark[:, 1:] <= 0):
        raise ValueError("Invalid Mark OHLC")
    clocks = mark[:, 0]
    if np.any(clocks != np.floor(clocks)) or np.any(clocks % MINUTE) or np.any(np.diff(clocks) != MINUTE):
        raise ValueError("Mark UTC minutes missing, duplicated or unsorted")
    if np.any(mark[:, 2] < np.maximum.reduce((mark[:, 1], mark[:, 3], mark[:, 4]))) or np.any(
        mark[:, 3] > np.minimum(mark[:, 1], mark[:, 4])
    ):
        raise ValueError("Invalid Mark high/low relation")
    if start_ms is not None and int(clocks[0]) > start_ms:
        raise ValueError("Mark starts after required interval")
    if end_ms is not None and int(clocks[-1]) + MINUTE < end_ms:
        raise ValueError("Mark ends before required interval")


def mark_close_asof(mark: np.ndarray, timestamp_ms: int) -> tuple[Decimal, int]:
    """Latest completed mark minute at timestamp, without future lookahead."""
    starts = mark[:, 0]
    idx = int(np.searchsorted(starts, timestamp_ms - (MINUTE - 1), side="right")) - 1
    if idx < 0:
        raise ValueError("No completed Mark minute at settlement")
    close_at = int(starts[idx]) + MINUTE - 1
    if close_at > timestamp_ms:
        raise AssertionError("Future Mark close")
    return _decimal(mark[idx, 4], "Mark close"), close_at


def funding_overlay(
    trade: dict[str, Any],
    mark: np.ndarray,
    events: list[dict[str, Any]],
    *,
    shift_entry_ms: int = 0,
    shift_exit_ms: int = 0,
) -> dict[str, Any]:
    """Attribute observed settlements in [entry, exit); shifts are sensitivity only.

    ``mark_price`` is accepted solely when the caller's source receipt proves
    it is the official settlement mark. Otherwise latest completed 1m close
    is an explicit approximation of settlement notional.
    """
    _validate_events(events)
    side = int(trade["side"])
    if side not in (-1, 1):
        raise ValueError("Invalid signed side")
    qty = _decimal(trade["quantity"], "quantity")
    if qty <= 0:
        raise ValueError("Quantity must be positive")
    entry = int(trade["entry_at"]) + shift_entry_ms
    exit_at = int(trade["exit_at"]) + shift_exit_ms
    if exit_at <= entry:
        raise ValueError("Shifted trade interval is empty")
    rows: list[dict[str, Any]] = []
    total = Decimal(0)
    for event in events:
        clock = _event_clock(event)
        if clock < entry or clock >= exit_at:
            continue
        rate = _decimal(event["rate"], "funding rate")
        source_mark = event.get("mark_price")
        if source_mark is not None:
            price = _decimal(source_mark, "settlement Mark")
            if not event.get("mark_price_source_proven", False):
                raise ValueError("Unproven settlement Mark price")
            mark_basis = "PROVIDER_SETTLEMENT_MARK"
            mark_close_at = None
        else:
            price, mark_close_at = mark_close_asof(mark, clock)
            mark_basis = "LATEST_COMPLETED_1M_MARK_CLOSE_APPROXIMATION"
        if price <= 0:
            raise ValueError("Nonpositive settlement Mark")
        cash = -Decimal(side) * qty * price * rate
        total += cash
        rows.append({
            "settlement_at": clock,
            "source_rate_fraction": str(rate),
            "side": side,
            "quantity": str(qty),
            "settlement_mark": str(price),
            "mark_basis": mark_basis,
            "mark_close_at": mark_close_at,
            "signed_cash_usdt": str(cash),
        })
    notional = _decimal(trade["entry_notional"], "entry notional")
    if notional <= 0:
        raise ValueError("Nonpositive entry notional")
    net = _decimal(trade["net_usdt"], "pre-funding net") + total
    return {
        "settlements": rows,
        "settlement_count": len(rows),
        "funding_cash_usdt": str(total),
        "net_after_funding_usdt": str(net),
        "net_after_funding_bps": str(Decimal(10_000) * net / notional),
        "timing_shift_entry_ms": shift_entry_ms,
        "timing_shift_exit_ms": shift_exit_ms,
    }


def mark_account_curve(
    trades: list[dict[str, Any]],
    mark: np.ndarray,
    start_ms: int,
    end_ms: int,
    initial_equity: float,
    cost: dict[str, float],
) -> dict[str, Any]:
    """Minute close liquidation-value diagnostic for exact supplied fills.

    Trades must carry ``funding_settlements`` and ``funding_cash_usdt`` from
    funding_overlay. Closed cash is recognized in the exit minute; before that
    only settlements already due at that minute's close enter the mark.
    """
    if start_ms % MINUTE or end_ms % MINUTE or end_ms <= start_ms or initial_equity <= 0:
        raise ValueError("Invalid fold clock or starting cash")
    validate_mark(mark, start_ms=start_ms, end_ms=end_ms)
    start = _index(mark, start_ms)
    stop = _index(mark, end_ms - MINUTE)
    curve = np.full(stop - start + 1, initial_equity, dtype=float)
    equity = float(initial_equity)
    cursor = start
    max_exposure = 0.0
    breach_minutes = 0
    for trade in trades:
        entry_at, exit_at = int(trade["entry_at"]), int(trade["exit_at"])
        if entry_at < start_ms or exit_at >= end_ms or entry_at > exit_at:
            raise ValueError("Trade outside fold")
        i_entry = _index(mark, entry_at)
        i_exit = _index(mark, exit_at // MINUTE * MINUTE)
        if i_entry < cursor:
            raise ValueError("Overlapping trades")
        curve[cursor - start:i_entry - start] = equity
        qty = float(trade["quantity"])
        side = int(trade["side"])
        settlements = trade.get("funding_settlements", [])
        funding_total = float(trade.get("funding_cash_usdt", 0.0))
        if abs(sum(float(x["signed_cash_usdt"]) for x in settlements) - funding_total) > 1e-7:
            raise ValueError("Funding cash and settlement ledger disagree")
        exit_equity = equity + float(trade["net_usdt"]) + funding_total
        for i in range(i_entry, i_exit + 1):
            minute = int(mark[i, 0])
            close_at = minute + MINUTE - 1
            # R2 exits are open or minute-end. The exit minute records closed
            # cash, never a later mark as an executable fill.
            if minute >= exit_at or i == i_exit:
                value = exit_equity
            else:
                due = sum(float(x["signed_cash_usdt"]) for x in settlements if int(x["settlement_at"]) <= close_at)
                raw = float(mark[i, 4])
                liquidation = _effective(raw, side, cost, entry=False)
                value = (
                    equity + due + side * (liquidation - float(trade["effective_entry"])) * qty
                    - float(trade["fee_entry"]) - _fee(liquidation, qty, cost)
                )
                if value <= 0:
                    raise ValueError("Nonpositive Mark liquidation-value equity")
                exposure = raw * qty / value
                max_exposure = max(max_exposure, exposure)
                breach_minutes += exposure > 1 + 1e-9
            curve[i - start] = value
        if exit_equity <= 0:
            raise ValueError("Nonpositive funded cash")
        equity = exit_equity
        cursor = i_exit + 1
    curve[cursor - start:] = equity
    with_start = np.r_[initial_equity, curve]
    peaks = np.maximum.accumulate(with_start)
    return {
        "minute_equity_curve": np.column_stack((mark[start:stop + 1, 0] + MINUTE - 1, curve)),
        "ending_equity": equity,
        "max_mtm_drawdown_pct": float(np.max((peaks - with_start) / peaks) * 100),
        "max_position_notional_to_marked_equity": max_exposure,
        "marked_exposure_breach_minutes": int(breach_minutes),
    }


def funded_fold(
    last: np.ndarray,
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    signal_events: list[dict[str, Any]],
    candidate: dict[str, Any],
    fold: dict[str, Any],
    cost: dict[str, float],
    initial_equity: float = 1000.0,
) -> dict[str, Any]:
    """R2 episode, ACK/cooldown and sizing, with due funding in future cash.

    The frozen R2 signal events and trade-price path are inputs. No Mark value
    or future funding rate changes the signal, stop, target, or raw fill.
    """
    start, end = int(fold["start_ms"]), int(fold["end_ms"])
    if start % MINUTE or end % MINUTE or end <= start or initial_equity <= 0:
        raise ValueError("Invalid fold or starting equity")
    first, last_idx = _index(last, start), _index(last, end - MINUTE)
    if np.any(np.diff(last[first:last_idx + 1, 0]) != MINUTE):
        raise ValueError("Noncontiguous last-price fold")
    validate_mark(mark, start_ms=start, end_ms=end)
    _validate_events(funding_events)
    cash = float(initial_equity)
    next_allowed = start
    cooldown = int(candidate.get("cooldown_hours", 4)) * HOUR
    trades: list[dict[str, Any]] = []
    fates: Counter[str] = Counter()
    for signal in sorted(signal_events, key=lambda x: (int(x["entry_at"]), str(x.get("event_id", "")))):
        entry = int(signal["entry_at"])
        if not start <= entry < end:
            continue
        if entry < next_allowed:
            fates["POSITION_ACK_OR_COOLDOWN"] += 1
            continue
        try:
            proposal = _proposed(last, signal, candidate, cost)
        except ValueError as exc:
            fates["LOOKAHEAD_OR_CLOCK" if "Availability" in str(exc) else "ENTRY_OR_SOURCE_REJECTED"] += 1
            continue
        budget = 0.95 * min(cash, 1000.0)
        raw = proposal["raw_entry"]
        worst_entry = max(proposal["effective_entry"], _effective(raw + 0.25 * float(signal["atr_hour"]), 1, cost, True))
        fee_unit = worst_entry * float(cost["fee_bps"]) / 10_000
        exit_reserve = 1.10 * worst_entry * (
            float(cost["fee_bps"]) + 0.5 * float(cost["spread_bps"]) + _slippage(cost)
        ) / 10_000
        funding_reserve = 1.10 * raw * 8.0 * proposal["horizon_hours"] / 10_000
        per_unit = worst_entry + fee_unit + exit_reserve + funding_reserve
        quantity = math.floor(budget / per_unit / LOT + 1e-10) * LOT
        if quantity <= 0 or quantity * raw < MIN_NOTIONAL:
            fates["SIZE_OR_MIN_NOTIONAL"] += 1
            continue
        if quantity * proposal["effective_entry"] + _fee(proposal["effective_entry"], quantity, cost) > budget + 1e-8:
            raise ValueError("Entry would breach 1x/reserve budget")
        try:
            trade = episode(last, signal, candidate, cost, quantity=quantity)
        except ValueError:
            fates["INCOMPLETE_EPISODE"] += 1
            continue
        if trade["exit_ack_at"] >= end:
            fates["EXIT_ACK_OUTSIDE_FOLD"] += 1
            continue
        overlay = funding_overlay(trade, mark, funding_events)
        funded = float(overlay["funding_cash_usdt"])
        after = cash + float(trade["net_usdt"]) + funded
        if after <= 0:
            raise ValueError("Insolvent funded account after exit")
        trade["cash_before_entry"] = cash
        trade["funding_settlements"] = overlay["settlements"]
        trade["funding_cash_usdt"] = overlay["funding_cash_usdt"]
        trade["net_after_funding_usdt"] = overlay["net_after_funding_usdt"]
        trade["net_after_funding_bps"] = overlay["net_after_funding_bps"]
        cash = after
        trade["cash_after_ack"] = cash
        trades.append(trade)
        next_allowed = max(int(trade["exit_ack_at"]), int(trade["exit_at"]) + cooldown)
        fates["FILLED"] += 1
    account = mark_account_curve(trades, mark, start, end, initial_equity, cost)
    if abs(account["ending_equity"] - cash) > 1e-7:
        raise AssertionError("Funded cash/Mark account divergence")
    return {
        "candidate": candidate.get("id", "UNKNOWN"),
        "year": fold.get("year", 0),
        "month": fold.get("month", 0),
        "starting_equity": initial_equity,
        "ending_equity": cash,
        "trades": trades,
        "event_fates": dict(fates),
        **account,
    }
