"""Causal, research-only Decimal partial-exit simulator. No source I/O or orders."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal

import numpy as np

MINUTE = 60_000
HOUR = 60 * MINUTE
TICK = Decimal("0.1")
LOT = Decimal("0.001")
CASH = Decimal("0.00000001")


def dec(value) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("NONFINITE_FINANCIAL_INPUT")
    return result


def money(value: Decimal) -> Decimal:
    return value.quantize(CASH, rounding=ROUND_HALF_EVEN)


def tick(value: Decimal, up: bool) -> Decimal:
    return (value / TICK).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * TICK


def lots(value: Decimal) -> Decimal:
    return (value / LOT).to_integral_value(rounding=ROUND_FLOOR) * LOT


def canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=lambda x: str(x) if isinstance(x, Decimal) else asdict(x),
    ).encode()


@dataclass(frozen=True)
class Cost:
    fee_bps: Decimal
    spread_bps: Decimal
    slip_bps: Decimal

    @classmethod
    def from_dict(cls, row):
        try:
            result = cls(
                dec(row["fee_bps"]),
                dec(row["spread_bps"]),
                dec(row["slippage_bps"] if "slippage_bps" in row else row["slip_bps"]),
            )
        except KeyError as exc:
            raise ValueError("COST_UNAVAILABLE") from exc
        if any(x < 0 for x in (result.fee_bps, result.spread_bps, result.slip_bps)):
            raise ValueError("NEGATIVE_COST")
        return result

    def effective(self, raw: Decimal, side: int, entry: bool) -> Decimal:
        direction = side if entry else -side
        adjusted = raw * (1 + direction * (self.spread_bps + self.slip_bps) / 10000)
        if raw <= 0 or adjusted <= 0:
            raise ValueError("NONPOSITIVE_EXECUTION_PRICE")
        return tick(adjusted, direction > 0)

    def fee(self, effective: Decimal, quantity: Decimal) -> Decimal:
        return money(effective * quantity * self.fee_bps / 10000)


@dataclass(frozen=True)
class Entry:
    event_id: str
    side: int
    event_closed_at: int
    signal_available_at: int
    decision_at: int
    order_possible_at: int
    fill_at: int
    raw_price: Decimal
    effective_price: Decimal
    initial_quantity: Decimal
    initial_stop: Decimal
    initial_R: Decimal
    atr_hour: Decimal
    cap_at: int
    fee: Decimal


@dataclass(frozen=True)
class ExitLeg:
    fill_id: str
    trigger_at: int
    effective_at: int
    fill_at: int
    ack_at: int
    reason: str
    quantity: Decimal
    remaining: Decimal
    raw_price: Decimal
    effective_price: Decimal
    fee: Decimal
    spread_drag: Decimal
    slippage_drag: Decimal
    tick_drag: Decimal
    signed_gross: Decimal
    signed_effective_pnl: Decimal


@dataclass
class PositionState:
    entry: Entry
    remaining: Decimal
    active_stop: Decimal
    pending_stop: Decimal | None = None
    pending_at: int | None = None
    tp1_ack_at: int | None = None
    stop_updates: list = field(default_factory=list)
    legs: list[ExitLeg] = field(default_factory=list)
    seen_fills: set[str] = field(default_factory=set)

    def record(self, leg: ExitLeg) -> None:
        if leg.fill_id in self.seen_fills:
            raise ValueError("DUPLICATE_FILL")
        if leg.quantity <= 0 or leg.quantity > self.remaining or leg.quantity != lots(leg.quantity):
            raise ValueError("EXIT_QUANTITY_INVALID")
        if leg.remaining != self.remaining - leg.quantity:
            raise ValueError("RESIDUAL_CONSERVATION_FAILED")
        self.seen_fills.add(leg.fill_id)
        self.remaining = leg.remaining
        self.legs.append(leg)

    def queue_stop(self, price: Decimal, observed_at: int) -> None:
        candidates = [self.active_stop, price]
        if self.pending_stop is not None:
            candidates.append(self.pending_stop)
        value = max(candidates) if self.entry.side == 1 else min(candidates)
        if self.entry.side * (value - self.active_stop) > 0:
            if self.pending_at is None:
                self.pending_at = observed_at + MINUTE
            self.pending_stop = value


def make_entry(data, event, hours: int, cost: Cost, quantity: Decimal) -> Entry:
    end, decision, filled = (int(event[k]) for k in ("event_time", "decision_at", "entry_at"))
    if (
        any(t % MINUTE for t in (end, decision, filled))
        or decision != end + MINUTE
        or filled != decision + MINUTE
    ):
        raise ValueError("ENTRY_KNOWN_AT_VIOLATION")
    if hours not in (8, 18, 24):
        raise ValueError("UNFROZEN_CAP")
    side = int(event["side"])
    if side not in (-1, 1):
        raise ValueError("SIDE_INVALID")
    q = dec(quantity)
    if q <= 0 or q != lots(q):
        raise ValueError("ENTRY_QUANTITY_INVALID")
    i = int(np.searchsorted(data[:, 0], filled))
    if i < 2 or i >= len(data) or int(data[i, 0]) != filled:
        raise ValueError("ENTRY_MINUTE_UNAVAILABLE")
    raw, atr, close = dec(data[i, 1]), dec(event["atr_hour"]), dec(event["decision_close"])
    source_stop = dec(event["stop"])
    if atr <= 0 or raw <= 0 or side * (raw - source_stop) <= 0:
        raise ValueError("INITIAL_STOP_INVALID")
    risk_bps = 10000 * abs(raw - source_stop) / raw
    if not Decimal(30) <= risk_bps <= Decimal(300):
        raise ValueError("INITIAL_RISK_OUTSIDE_30_300BP")
    if abs(raw - close) > Decimal(".25") * atr:
        raise ValueError("ENTRY_GAP_VETO")
    if raw * q < 5:
        raise ValueError("ENTRY_MIN_NOTIONAL")
    stop = tick(source_stop, side < 0)
    effective = cost.effective(raw, side, True)
    risk = side * (effective - stop)
    if risk <= 0:
        raise ValueError("INITIAL_EFFECTIVE_RISK_INVALID")
    return Entry(
        str(event["event_id"]),
        side,
        end,
        end + MINUTE,
        decision,
        filled,
        filled,
        raw,
        effective,
        q,
        stop,
        risk,
        atr,
        filled + hours * HOUR,
        cost.fee(effective, q),
    )


def break_even(entry: Entry, cost: Cost) -> Decimal:
    fee = cost.fee_bps / 10000
    drag = (cost.spread_bps + cost.slip_bps) / 10000
    if entry.side == 1:
        raw = tick(entry.effective_price * (1 + fee) / ((1 - fee) * (1 - drag)), True)
    else:
        raw = tick(entry.effective_price * (1 - fee) / ((1 + fee) * (1 + drag)), False)
    # Tick and fee quantization can move the analytic boundary.
    for _ in range(10):
        eff = cost.effective(raw, entry.side, False)
        per_unit = entry.side * (eff - entry.effective_price)
        if per_unit - eff * fee - entry.effective_price * fee >= 0:
            return raw
        raw += entry.side * TICK
    raise ValueError("BREAK_EVEN_ROUNDING_NOT_CONVERGED")


def target_plan(entry: Entry, policy: str):
    if policy == "X0":
        levels, amounts = ["2"], [entry.initial_quantity]
    elif policy == "X1":
        levels = ["1", "1.8", "3"]
        first, second = (
            lots(entry.initial_quantity * Decimal(".4")),
            lots(entry.initial_quantity * Decimal(".3")),
        )
        amounts = [first, second, entry.initial_quantity - first - second]
    elif policy == "X2":
        levels = ["1.5", "3"]
        first = lots(entry.initial_quantity * Decimal(".5"))
        amounts = [first, entry.initial_quantity - first]
    else:
        raise ValueError("UNFROZEN_EXIT")
    if any(q <= 0 or q * entry.raw_price < 5 for q in amounts):
        raise ValueError("PARTIAL_LOT_INELIGIBLE")
    targets = [
        tick(entry.effective_price + entry.side * dec(r) * entry.initial_R, entry.side < 0)
        for r in levels
    ]
    if any(x <= 0 for x in targets):
        raise ValueError("TARGET_NONPOSITIVE")
    return targets, amounts


def validate_prices(data) -> None:
    if data.ndim != 2 or data.shape[1] < 6 or len(data) < 3 or not np.all(np.isfinite(data[:, :6])):
        raise ValueError("PRICE_ARRAY_INVALID")
    if np.any(data[:, 0] % MINUTE) or np.any(np.diff(data[:, 0]) != MINUTE):
        raise ValueError("MINUTE_GAP_OR_DUPLICATE")
    if (
        np.any(data[:, 3] <= 0)
        or np.any(data[:, 2] < np.maximum(data[:, 1], data[:, 4]))
        or np.any(data[:, 3] > np.minimum(data[:, 1], data[:, 4]))
        or np.any(data[:, 5] < 0)
    ):
        raise ValueError("OHLC_INVALID")


def episode(
    data,
    event,
    policy: str,
    hours: int,
    cost: Cost,
    quantity,
    hourly=None,
    force_at=None,
    *,
    validated=False,
) -> dict:
    if not validated:
        validate_prices(data)
    entry = make_entry(data, event, hours, cost, dec(quantity))
    targets, amounts = target_plan(entry, policy)
    hourly = [] if hourly is None else hourly
    if any(h["available_at"] < h["end_ms"] + MINUTE or h["end_ms"] % HOUR for h in hourly):
        raise ValueError("HOURLY_ATR_AVAILABLE_BEFORE_CLOSE_DELAY")
    if any(
        hourly[k]["available_at"] <= hourly[k - 1]["available_at"] for k in range(1, len(hourly))
    ):
        raise ValueError("HOURLY_ATR_ORDER_INVALID")
    state = PositionState(entry, entry.initial_quantity, entry.initial_stop)
    start = int(np.searchsorted(data[:, 0], entry.fill_at))
    hidx, used_hour, next_target = -1, -2, 0
    collisions = 0
    activated_be = False
    initial_active_at = entry.fill_at

    def fill(raw, qty, at, reason, trigger_at, active_at):
        raw = dec(raw)
        eff = cost.effective(raw, entry.side, False)
        spread = money(raw * qty * cost.spread_bps / 10000)
        slip = money(raw * qty * cost.slip_bps / 10000)
        friction = money(entry.side * (raw - eff) * qty)
        leg = ExitLeg(
            f"{entry.event_id}:{len(state.legs)}",
            trigger_at,
            active_at,
            at,
            ((at + MINUTE - 1) // MINUTE) * MINUTE + MINUTE,
            reason,
            qty,
            state.remaining - qty,
            raw,
            eff,
            cost.fee(eff, qty),
            spread,
            slip,
            friction - spread - slip,
            money(entry.side * (raw - entry.raw_price) * qty),
            money(entry.side * (eff - entry.effective_price) * qty),
        )
        state.record(leg)
        if reason == "TP1":
            state.tp1_ack_at = leg.ack_at

    for i in range(start, len(data)):
        t = int(data[i, 0])
        if t > entry.cap_at:
            break
        if state.pending_at is not None and t >= state.pending_at:
            old = state.active_stop
            state.active_stop = state.pending_stop
            initial_active_at = t
            state.stop_updates.append(
                {"active_at": t, "old": str(old), "new": str(state.active_stop)}
            )
            state.pending_stop, state.pending_at = None, None
        while hidx + 1 < len(hourly) and hourly[hidx + 1]["available_at"] <= t:
            hidx += 1
        if state.tp1_ack_at is not None and t >= state.tp1_ack_at:
            if policy == "X1" and not activated_be:
                state.queue_stop(break_even(entry, cost), t)
                activated_be = True
            if policy == "X2" and hidx >= 0 and used_hour != hidx:
                h = hourly[hidx]
                if math.isfinite(float(h["atr"])) and float(h["atr"]) > 0:
                    price = tick(
                        dec(h["close"]) - entry.side * Decimal("1.5") * dec(h["atr"]),
                        entry.side < 0,
                    )
                    if price > 0:
                        state.queue_stop(price, t)
                used_hour = hidx
        op, high, low = map(float, data[i, 1:4])
        stop = float(state.active_stop)
        stop_touch = low <= stop if entry.side == 1 else high >= stop
        target_touch = (
            high >= float(targets[next_target])
            if entry.side == 1
            else low <= float(targets[next_target])
        )
        if stop_touch and target_touch:
            collisions += 1
        if entry.side * (op - stop) <= 0:
            fill(op, state.remaining, t, "STOP_GAP", t, initial_active_at)
        elif force_at is not None and t >= force_at:
            raw = min(dec(op), targets[-1]) if entry.side == 1 else max(dec(op), targets[-1])
            fill(raw, state.remaining, t, "RISK_CLOSE", force_at, force_at)
        elif t >= entry.cap_at:
            raw = min(dec(op), targets[-1]) if entry.side == 1 else max(dec(op), targets[-1])
            fill(raw, state.remaining, t, "TIME_CAP", entry.cap_at, entry.cap_at)
        elif stop_touch:
            fill(
                state.active_stop,
                state.remaining,
                t + MINUTE - 1,
                "STOP",
                t + MINUTE - 1,
                initial_active_at,
            )
        else:
            while next_target < len(targets) and (
                high >= float(targets[next_target])
                if entry.side == 1
                else low <= float(targets[next_target])
            ):
                raw = targets[next_target]
                gap = entry.side * (dec(op) - raw) >= 0
                at = t if gap else t + MINUTE - 1
                fill(raw, amounts[next_target], at, f"TP{next_target + 1}", at, entry.fill_at)
                next_target += 1
        if state.remaining == 0:
            break
    if state.remaining != 0:
        raise ValueError("INCOMPLETE_FILLS_MISSING_CAP_MINUTE")
    if sum((leg.quantity for leg in state.legs), Decimal(0)) != entry.initial_quantity:
        raise ValueError("EXIT_QUANTITY_CONSERVATION_FAILED")
    gross = sum((x.signed_gross for x in state.legs), Decimal(0))
    fee = entry.fee + sum((x.fee for x in state.legs), Decimal(0))
    net = sum((x.signed_effective_pnl for x in state.legs), Decimal(0)) - fee
    entry_drag = money(
        entry.side * (entry.effective_price - entry.raw_price) * entry.initial_quantity
    )
    exit_drag = sum((x.spread_drag + x.slippage_drag + x.tick_drag for x in state.legs), Decimal(0))
    if abs(gross - entry_drag - exit_drag - fee - net) > CASH * len(state.legs):
        raise ValueError("CASH_CONSERVATION_FAILED")
    notional = entry.raw_price * entry.initial_quantity
    result = {
        "entry": asdict(entry),
        "legs": [asdict(x) for x in state.legs],
        "cost": asdict(cost),
        "event_id": entry.event_id,
        "side": entry.side,
        "entry_at": entry.fill_at,
        "exit_at": state.legs[-1].fill_at,
        "exit_ack_at": state.legs[-1].ack_at,
        "exit_reason": state.legs[-1].reason,
        "policy": policy,
        "cap_hours": hours,
        "initial_quantity": entry.initial_quantity,
        "entry_notional": notional,
        "gross_usdt": gross,
        "fee_usdt": fee,
        "execution_drag_usdt": entry_drag + exit_drag,
        "net_usdt": net,
        "gross_bps": gross / notional * 10000,
        "net_bps": net / notional * 10000,
        "net_R": net / (entry.initial_R * entry.initial_quantity),
        "hold_minutes": (state.legs[-1].fill_at - entry.fill_at) / MINUTE,
        "collision_minutes": collisions,
        "minute_path_status": "MINUTE_PATH_UNKNOWN" if collisions else "OHLC_SIMULATED_PATH",
        "stop_updates": state.stop_updates,
        "pnl_grade": "NET_EX_FUNDING_PROXY",
        "real_funding": "UNKNOWN",
        "fill_grade": "HYPOTHETICAL_TAKER_NO_L2_CAPACITY_PROOF",
    }
    result["ledger_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def dense_equity(data, trade, initial_cash: float) -> tuple[np.ndarray, np.ndarray]:
    """Ex-post dense Last liquidation-cost proxy; never a true Mark curve."""
    entry = trade["entry"]
    side = entry["side"]
    start = int(np.searchsorted(data[:, 0], trade["entry_at"]))
    last = int(np.searchsorted(data[:, 0], (trade["exit_at"] // MINUTE) * MINUTE))
    closes = data[start : last + 1, 4]
    q = float(entry["initial_quantity"])
    eff = float(entry["effective_price"])
    result = np.empty(len(closes))
    exposure = np.empty(len(closes))
    cash = initial_cash - float(entry["fee"])
    j = 0
    for k, close in enumerate(closes):
        t = int(data[start + k, 0])
        while j < len(trade["legs"]) and trade["legs"][j]["fill_at"] // MINUTE * MINUTE <= t:
            leg = trade["legs"][j]
            q -= float(leg["quantity"])
            cash += float(leg["signed_effective_pnl"] - leg["fee"])
            j += 1
        exposure[k] = max(0, q) * close
        c = trade["cost"]
        adverse = (float(c["spread_bps"]) + float(c["slip_bps"])) / 10000
        adjusted = close * (1 - side * adverse)
        liquidation = (
            math.floor(adjusted / 0.1 + 1e-9) if side == 1 else math.ceil(adjusted / 0.1 - 1e-9)
        ) * 0.1
        result[k] = (
            cash
            + side * (liquidation - eff) * max(0, q)
            - liquidation * max(0, q) * float(c["fee_bps"]) / 10000
        )
    return result, exposure
