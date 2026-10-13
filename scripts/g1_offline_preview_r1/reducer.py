"""Pure, fail-closed event reducer. It has no network or order adapter."""

from __future__ import annotations

import copy
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, getcontext, localcontext
from typing import Any

from .model import SafetyViolation, decimal, digest, exact, funding_receipt_fingerprint, timestamp

LOT = Decimal("0.001")
TICK = Decimal("0.1")
FEE = Decimal("0.0006")
ADVERSE_FILL = Decimal("0.0005")
COOLDOWN_MS = 6 * 60 * 60 * 1000
MIN_NOTIONAL = Decimal(1)


def _d(value: Decimal) -> str:
    return format(value, "f")


def _text(value: Any, code: str, limit: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise SafetyViolation(code)
    lowered = value.lower()
    if any(word in lowered for word in ("secret", "password", "api_key", "bearer", "token=")):
        raise SafetyViolation("SECRET_IN_EVENT")
    return value


def _phase(state: dict[str, Any], *allowed: str) -> None:
    if state["phase"] not in allowed:
        raise SafetyViolation("PHASE_INVALID")


def _bar(state: dict[str, Any], at: int) -> dict[str, Any]:
    bar = state["last_bar"]
    if bar is None or bar["available_at"] > at or bar["close_time"] > at:
        raise SafetyViolation("BAR_NOT_CAUSALLY_AVAILABLE")
    if at - bar["close_time"] > 60000:
        raise SafetyViolation("BAR_STALE")
    return bar


def _journal(
    state: dict[str, Any],
    key: str,
    kind: str,
    at: int,
    cash_delta: Decimal,
    quantity: Decimal = Decimal(0),
) -> None:
    if any(row["key"] == key for row in state["journal"]):
        raise SafetyViolation("JOURNAL_DUPLICATE")
    state["journal"].append(
        {
            "key": key,
            "kind": kind,
            "at": at,
            "cash_delta": _d(cash_delta),
            "quantity": _d(quantity),
            "source_hash": state["last_bar_hash"],
        }
    )
    state["cash"] = _d(decimal(state["cash"]) + cash_delta)


def _fill_price(last: Decimal, side: str, *, entry: bool) -> Decimal:
    adverse_up = (side == "LONG") == entry
    raw = last * (Decimal(1) + (ADVERSE_FILL if adverse_up else -ADVERSE_FILL))
    return raw.quantize(TICK, rounding=ROUND_CEILING if adverse_up else ROUND_FLOOR)


def _record_funding_fill(state, event, quantity, action):
    if state.get("funding_contract") == "SYNTHETIC_CAUSAL_R4":
        state["fill_history"].append(
            {
                "fill_id": event["payload"]["fill_id"],
                "executed_at": event["at"],
                "action": action,
                "side": state["proposal"]["side"],
                "quantity": _d(quantity),
            }
        )


def _settlement_exposure(state, settlement_at):
    if state.get("funding_contract") != "SYNTHETIC_CAUSAL_R4":
        raise SafetyViolation("COST_INCOMPLETE")
    fills = state["fill_history"]
    if [f["fill_id"] for f in fills] != state["used_fill_ids"]:
        raise SafetyViolation("COST_INCOMPLETE")
    current = exposure = Decimal(0)
    for fill in fills:
        exact(fill, {"fill_id", "executed_at", "action", "side", "quantity"}, "COST_INCOMPLETE")
        executed_at = timestamp(fill["executed_at"])
        if abs(executed_at - settlement_at) <= 15000:
            raise SafetyViolation("AMBIGUOUS_SETTLEMENT_BOUNDARY")
        if fill["side"] not in ("LONG", "SHORT") or fill["action"] not in ("ENTRY", "EXIT"):
            raise SafetyViolation("COST_INCOMPLETE")
        change = decimal(fill["quantity"], positive=True)
        change *= (1 if fill["side"] == "LONG" else -1) * (1 if fill["action"] == "ENTRY" else -1)
        current += change
        if executed_at < settlement_at:
            exposure += change
    expected = decimal(state["remaining_qty"])
    if expected:
        expected *= _position_side(state)
    if current != expected:
        raise SafetyViolation("COST_INCOMPLETE")
    return exposure


def _available(state: dict[str, Any]) -> Decimal:
    return decimal(state["cash"]) - decimal(state["reserved_notional"])


def _position_side(state: dict[str, Any]) -> int:
    return 1 if state["proposal"]["side"] == "LONG" else -1


def _required_exit(state: dict[str, Any]) -> dict[str, Any] | None:
    """Completed Last bars cannot be discarded after a conservative exit trigger."""
    if decimal(state["remaining_qty"]) == 0 or state["entry_at"] is None:
        return None
    bar = state["last_bar"]
    long = _position_side(state) == 1
    stop = decimal(state["stop"])
    kind = None
    if decimal(bar["last_low"]) <= stop if long else decimal(bar["last_high"]) >= stop:
        kind = "STOP"
    elif bar["close_time"] >= state["entry_at"] + state["proposal"]["horizon_hours"] * 3600000:
        kind = "TIME_CAP"
    elif state["phase"] == "OPEN" and not state["tp1_filled"]:
        target = decimal(state["proposal"]["tp1"])
        if (
            (decimal(bar["last_open"]) >= target or decimal(bar["last_high"]) >= target + TICK)
            if long
            else (decimal(bar["last_open"]) <= target or decimal(bar["last_low"]) <= target - TICK)
        ):
            kind = "TP1"
    elif state["tp1_filled"] and bar["open_time"] > state["tp1_bar_open"]:
        target = decimal(state["proposal"]["tp2"])
        if (
            (decimal(bar["last_open"]) >= target or decimal(bar["last_high"]) >= target + TICK)
            if long
            else (decimal(bar["last_open"]) <= target or decimal(bar["last_low"]) <= target - TICK)
        ):
            kind = "TP2"
    return (
        None
        if kind is None
        else {"kind": kind, "source_hash": state["last_bar_hash"], "at": bar["close_time"]}
    )


def _exit(
    state: dict[str, Any], event: dict[str, Any], kind: str, price: Decimal, quantity: Decimal
) -> None:
    payload = event["payload"]
    keys = {"fill_id"}
    if (
        kind == "TP1"
        and state.get("funding_contract") == "SYNTHETIC_CAUSAL_R4"
        and "executed_quantity" in payload
    ):
        keys.add("executed_quantity")
    exact(payload, keys)
    fill_id = _text(payload["fill_id"], "FILL_ID_INVALID")
    if fill_id in state["used_fill_ids"]:
        raise SafetyViolation("FILL_DUPLICATE")
    state["used_fill_ids"].append(fill_id)
    at = event["at"]
    entry = decimal(state["entry_price"], positive=True)
    gross = Decimal(_position_side(state)) * quantity * (price - entry)
    fee = quantity * price * FEE
    cash = gross - fee
    if quantity <= 0 or quantity > decimal(state["remaining_qty"]):
        raise SafetyViolation("INVENTORY_INVALID")
    state["remaining_qty"] = _d(decimal(state["remaining_qty"]) - quantity)
    _record_funding_fill(state, event, quantity, "EXIT")
    state["pending_cash"][fill_id] = _d(cash)
    state["pending_release"][fill_id] = _d(quantity * entry)
    state["pending_kind"][fill_id] = kind
    state["pending_at"][fill_id] = at
    state["phase"] = "WAIT_TP1_ACK" if kind == "TP1" else "EXIT_WAIT_ACK"
    if kind == "TP1":
        state["tp1_filled"] = True
        state["tp1_bar_open"] = _bar(state, at)["open_time"]
    state["trace"].append(
        {
            "event": event["id"],
            "kind": kind,
            "at": at,
            "fill_id": fill_id,
            "quantity": _d(quantity),
            "fill_price": _d(price),
            "gross": _d(gross),
            "exit_fee": _d(fee),
            "pending_cash": _d(cash),
        }
    )


def mark_equity(state: dict[str, Any]) -> str:
    """Diagnostic Mark equity with a residual exit fee, excluding exit impact."""
    cash = decimal(state["cash"])
    pending = sum((decimal(v) for v in state["pending_cash"].values()), Decimal(0))
    qty = decimal(state["remaining_qty"])
    if qty == 0 or state["last_bar"] is None or state["entry_price"] is None:
        return _d(cash + pending)
    mark = decimal(state["last_bar"]["mark_close"], positive=True)
    entry = decimal(state["entry_price"], positive=True)
    unrealized = Decimal(_position_side(state)) * qty * (mark - entry)
    return _d(cash + pending + unrealized - qty * mark * FEE)


def _check_portfolio(state: dict[str, Any]) -> None:
    cash = decimal(state["cash"])
    reserve = decimal(state["reserved_notional"])
    quantity = decimal(state["remaining_qty"])
    if cash < 0 or reserve < 0 or quantity < 0 or _available(state) < 0:
        raise SafetyViolation("CASH_OR_INVENTORY_NEGATIVE")
    if reserve > cash * Decimal("0.95") + Decimal("0.01"):
        raise SafetyViolation("ONE_X_OR_FIVE_PERCENT_RESERVE")
    if (
        quantity
        and state["entry_price"] is not None
        and quantity * decimal(state["entry_price"]) > reserve + Decimal("0.01")
    ):
        raise SafetyViolation("POSITION_UNRESERVED")
    state["available_cash"] = _d(_available(state))
    state["mark_equity"] = mark_equity(state)
    marked = decimal(state["mark_equity"])
    if marked <= 0:
        raise SafetyViolation("MARK_EQUITY_NONPOSITIVE")
    if (
        quantity
        and state["last_bar"] is not None
        and quantity * decimal(state["last_bar"]["mark_close"]) > marked
    ):
        raise SafetyViolation("MARK_EXPOSURE_ABOVE_ONE_X")
    state["position"] = (
        None
        if state["entry_price"] is None or state["phase"] == "CLOSED"
        else {
            "side": state["proposal"]["side"],
            "initial_quantity": state["entry_qty"],
            "remaining_quantity": state["remaining_qty"],
            "entry_price": state["entry_price"],
            "stop": state["stop"],
            "entry_at": state["entry_at"],
        }
    )


def transition(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Apply one trusted fixture event, returning a fresh JSON-compatible state."""
    if (
        isinstance(state, dict)
        and state.get("funding_contract") == "SYNTHETIC_CAUSAL_R4"
        and getcontext().prec != 128
    ):
        with localcontext() as context:
            context.prec = 128
            return transition(state, event)
    exact(event, {"id", "kind", "at", "payload"}, "EVENT_SCHEMA")
    event_id = _text(event["id"], "EVENT_ID_INVALID")
    kind = _text(event["kind"], "EVENT_KIND_INVALID")
    at = timestamp(event["at"])
    if not isinstance(event["payload"], dict):
        raise SafetyViolation("EVENT_SCHEMA")
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or state.get("safety_status") != "DRY_RUN_NO_NETWORK_NO_ORDERING"
    ):
        raise SafetyViolation("STATE_SCHEMA")
    if at < state["last_at"]:
        raise SafetyViolation("EVENT_REORDERED")
    if event_id in state["used_event_ids"]:
        raise SafetyViolation("EVENT_DUPLICATE")
    required = state["required_exit"]
    if required is not None and kind != required["kind"]:
        raise SafetyViolation("REQUIRED_EXIT_UNHANDLED")
    s = copy.deepcopy(state)
    p = event["payload"]

    if kind == "BAR":
        exact(
            p,
            {
                "source",
                "open_time",
                "close_time",
                "available_at",
                "last_open",
                "last_high",
                "last_low",
                "last_close",
                "mark_close",
            },
        )
        if p["source"] != "SYNTHETIC_V1":
            raise SafetyViolation("SOURCE_UNAUTHORIZED")
        opened = timestamp(p["open_time"])
        closed = timestamp(p["close_time"])
        available = timestamp(p["available_at"])
        if opened % 60000 or closed != opened + 59999 or not closed <= available <= at:
            raise SafetyViolation("BAR_PIT_INVALID")
        if s["last_bar"] is not None and opened != s["last_bar"]["open_time"] + 60000:
            raise SafetyViolation("BAR_NOT_DENSE_OR_MUTATED")
        o, h, low, c, mark = [
            decimal(p[k], positive=True)
            for k in ("last_open", "last_high", "last_low", "last_close", "mark_close")
        ]
        if low > min(o, c) or h < max(o, c) or low > h:
            raise SafetyViolation("BAR_OHLC_INVALID")
        s["last_bar"] = copy.deepcopy(p)
        s["last_bar_hash"] = digest(p)
        s["market"] = {
            "hash": s["last_bar_hash"],
            "close_time": closed,
            "available_at": available,
            "source": p["source"],
        }
        s["required_exit"] = _required_exit(s)

    elif kind == "PROPOSE":
        _phase(s, "READY", "CLOSED", "NO_ACTION")
        if at < s["cooldown_until"]:
            raise SafetyViolation("COOLDOWN_ACTIVE")
        exact(
            p,
            {
                "schema_version",
                "signal_id",
                "source_hash",
                "source_close_at",
                "decision_at",
                "side",
                "quantity",
                "stop",
                "tp1",
                "tp2",
                "horizon_hours",
                "expires_at",
                "version",
                "exit_identity",
            },
        )
        if (
            type(p["schema_version"]) is not int
            or p["schema_version"] != 1
            or type(p["version"]) is not int
            or p["version"] != 1
        ):
            raise SafetyViolation("PROPOSAL_VERSION")
        if p["exit_identity"] != "OFFLINE_TP1_BE_TIME_CAP_V1":
            raise SafetyViolation("EXIT_IDENTITY_INVALID")
        _text(p["signal_id"], "SIGNAL_ID_INVALID")
        if p["signal_id"] in s["used_signal_ids"]:
            raise SafetyViolation("SIGNAL_ID_REPLAY")
        bar = _bar(s, at)
        if (
            p["source_hash"] != s["last_bar_hash"]
            or timestamp(p["source_close_at"]) != bar["close_time"]
        ):
            raise SafetyViolation("PROPOSAL_SOURCE_DRIFT")
        decision = timestamp(p["decision_at"])
        expiry = timestamp(p["expires_at"])
        if decision < bar["available_at"] or decision > at or expiry <= at:
            raise SafetyViolation("PROPOSAL_PIT_OR_EXPIRY")
        if p["side"] not in ("LONG", "SHORT", "NO_ACTION"):
            raise SafetyViolation("SIDE_INVALID")
        qty = decimal(p["quantity"], positive=(p["side"] != "NO_ACTION"))
        if qty > Decimal("0.05") or qty % LOT or (p["side"] == "NO_ACTION" and qty != 0):
            raise SafetyViolation("QUANTITY_INVALID")
        stop, tp1, tp2 = [decimal(p[k], positive=True) for k in ("stop", "tp1", "tp2")]
        last = decimal(bar["last_close"], positive=True)
        if p["side"] == "LONG" and not stop < last < tp1 < tp2:
            raise SafetyViolation("LEVEL_ORDER_INVALID")
        if p["side"] == "SHORT" and not tp2 < tp1 < last < stop:
            raise SafetyViolation("LEVEL_ORDER_INVALID")
        if type(p["horizon_hours"]) is not int or p["horizon_hours"] not in (12, 18, 24):
            raise SafetyViolation("HORIZON_INVALID")
        s.update(
            {
                "proposal": copy.deepcopy(p),
                "proposal_hash": digest(p),
                "analysis_at": None,
                "analysis": None,
                "approval": None,
                "order_id": None,
                "entry_fill_id": None,
                "entry_at": None,
                "entry_price": None,
                "entry_qty": "0",
                "remaining_qty": "0",
                "stop": p["stop"],
                "tp1_filled": False,
                "tp1_ack_at": None,
                "tp1_bar_open": None,
                "entry_acknowledged": False,
            }
        )
        s["used_signal_ids"].append(p["signal_id"])
        s.pop("stop_update_source_hash", None)
        s["phase"] = "NO_ACTION" if p["side"] == "NO_ACTION" else "PROPOSED"

    elif kind == "ANALYZE":
        _phase(s, "PROPOSED")
        exact(
            p,
            {
                "schema_version",
                "signal_id",
                "proposal_hash",
                "source_hash",
                "as_of",
                "summary",
                "risk",
            },
        )
        if (
            type(p["schema_version"]) is not int
            or p["schema_version"] != 1
            or p["signal_id"] != s["proposal"]["signal_id"]
            or p["proposal_hash"] != s["proposal_hash"]
            or p["source_hash"] != s["proposal"]["source_hash"]
        ):
            raise SafetyViolation("ANALYSIS_STALE_OR_HALLUCINATED")
        if at >= s["proposal"]["expires_at"]:
            raise SafetyViolation("ANALYSIS_EXPIRED")
        if (
            p["risk"] != "DESCRIPTIVE_ONLY"
            or timestamp(p["as_of"]) > at
            or p["as_of"] < s["proposal"]["decision_at"]
        ):
            raise SafetyViolation("ANALYSIS_AUTHORITY_OR_CLOCK")
        _text(p["summary"], "ANALYSIS_SUMMARY_INVALID", 256)
        s["analysis_at"] = at
        s["analysis"] = copy.deepcopy(p)
        s["phase"] = "ANALYZED"

    elif kind == "APPROVE":
        _phase(s, "ANALYZED")
        exact(p, {"token_id"})
        token_id = _text(p["token_id"], "APPROVAL_TOKEN_INVALID")
        token = s["trusted_approvals"].get(token_id)
        if token is None or token_id in s["used_tokens"]:
            raise SafetyViolation("APPROVAL_UNTRUSTED_OR_REPLAYED")
        prop = s["proposal"]
        if (
            token["signal_id"] != prop["signal_id"]
            or token["proposal_hash"] != s["proposal_hash"]
            or token["quantity"] != prop["quantity"]
            or token["proposal_version"] != prop["version"]
        ):
            raise SafetyViolation("APPROVAL_DRIFT")
        if (
            token["issued_at"] < s["analysis_at"]
            or at < token["issued_at"]
            or at >= token["expires_at"]
            or at >= prop["expires_at"]
        ):
            raise SafetyViolation("APPROVAL_STALE_OR_REORDERED")
        s["used_tokens"].append(token_id)
        s["approval"] = {"token_hash": digest(token), "at": at, "signal_id": prop["signal_id"]}
        s["phase"] = "APPROVED"

    elif kind == "PLACE":
        _phase(s, "APPROVED")
        exact(p, set())
        bar = _bar(s, at)
        if at >= s["proposal"]["expires_at"]:
            raise SafetyViolation("APPROVAL_EXPIRED")
        qty = decimal(s["proposal"]["quantity"], positive=True)
        notional = qty * decimal(bar["last_close"], positive=True) * (Decimal(1) + ADVERSE_FILL)
        if notional < MIN_NOTIONAL or notional > decimal(s["cash"]) * Decimal("0.95"):
            raise SafetyViolation("ONE_X_OR_MIN_NOTIONAL")
        s["order_id"] = digest([s["proposal_hash"], "SIMULATED_ENTRY"])
        s["phase"] = "PLACED"

    elif kind == "FILL_ENTRY":
        _phase(s, "PLACED")
        exact(p, {"fill_id"})
        fill_id = _text(p["fill_id"], "FILL_ID_INVALID")
        if fill_id in s["used_fill_ids"]:
            raise SafetyViolation("FILL_DUPLICATE")
        bar = _bar(s, at)
        qty = decimal(s["proposal"]["quantity"], positive=True)
        price = _fill_price(
            decimal(bar["last_close"], positive=True), s["proposal"]["side"], entry=True
        )
        notional = qty * price
        fee = notional * FEE
        if notional < MIN_NOTIONAL or notional + fee > decimal(s["cash"]) * Decimal("0.95"):
            raise SafetyViolation("ONE_X_OR_FIVE_PERCENT_RESERVE")
        s["used_fill_ids"].append(fill_id)
        s["entry_fill_id"] = fill_id
        s["entry_at"] = at
        s["entry_price"] = _d(price)
        s["entry_qty"] = _d(qty)
        s["remaining_qty"] = _d(qty)
        _record_funding_fill(s, event, qty, "ENTRY")
        s["reserved_notional"] = _d(notional)
        _journal(s, "entry-fee:" + fill_id, "ENTRY_FEE", at, -fee, qty)
        s["phase"] = "WAIT_ENTRY_ACK"
        s["trace"].append(
            {
                "event": event_id,
                "kind": kind,
                "at": at,
                "fill_id": fill_id,
                "quantity": _d(qty),
                "fill_price": _d(price),
            }
        )

    elif kind == "ACK":
        _phase(s, "WAIT_ENTRY_ACK", "WAIT_TP1_ACK", "EXIT_WAIT_ACK")
        exact(p, {"ack_id", "order_id", "fill_id"})
        ack_id = _text(p["ack_id"], "ACK_ID_INVALID")
        fill_id = _text(p["fill_id"], "FILL_ID_INVALID")
        if ack_id in s["used_ack_ids"] or p["order_id"] != s["order_id"]:
            raise SafetyViolation("ACK_DUPLICATE_OR_UNKNOWN_ORDER")
        if fill_id == s["entry_fill_id"]:
            if s["entry_acknowledged"] or at < s["entry_at"] + 60000:
                raise SafetyViolation("ACK_BEFORE_FILL_OR_WRONG_ID")
            s["entry_acknowledged"] = True
        else:
            if fill_id not in s["pending_cash"] or at < s["pending_at"][fill_id] + 60000:
                raise SafetyViolation("ACK_BEFORE_FILL_OR_WRONG_ID")
            reason = s["pending_kind"][fill_id]
            _journal(
                s,
                "exit-net:" + fill_id,
                reason + "_NET",
                at,
                decimal(s["pending_cash"].pop(fill_id)),
            )
            s["reserved_notional"] = _d(
                decimal(s["reserved_notional"]) - decimal(s["pending_release"].pop(fill_id))
            )
            del s["pending_kind"][fill_id]
            del s["pending_at"][fill_id]
            if reason == "TP1":
                s["tp1_ack_at"] = at
        if decimal(s["remaining_qty"]) == 0:
            if s["pending_cash"] or not s["entry_acknowledged"]:
                s["phase"] = "EXIT_WAIT_ACK"
            else:
                s["phase"] = "CLOSED"
                s["cooldown_until"] = at + COOLDOWN_MS
        elif not s["entry_acknowledged"]:
            s["phase"] = "WAIT_ENTRY_ACK"
        elif s["pending_cash"]:
            s["phase"] = "WAIT_TP1_ACK"
        else:
            s["phase"] = "OPEN_RESIDUAL" if s["tp1_filled"] else "OPEN"
        s["used_ack_ids"].append(ack_id)

    elif kind == "FUNDING_RECEIPT":
        fingerprint = funding_receipt_fingerprint(event)
        settlement = p["settlement_id"]
        economic_at = p["settlement_at"]
        if settlement in s["used_settlements"] or economic_at in s["used_settlement_clocks"]:
            raise SafetyViolation("FUNDING_SETTLEMENT_CONFLICT")
        # This precision/rounding contract applies only to the new event kind;
        # legacy ledger calculations and old WAL/state identities stay intact.
        with localcontext() as context:
            context.prec = 128
            exposure = _settlement_exposure(s, economic_at)
            cash = (
                -exposure * decimal(p["mark_price"], positive=True) * decimal(p["rate_fraction"])
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
            _journal(s, "funding:" + settlement, kind, at, cash, abs(exposure))
            s["journal"][-1].update(
                settlement_at=economic_at,
                receipt_at=at,
                signed_exposure=_d(exposure),
                funding_fingerprint=fingerprint,
                source_hash=fingerprint,
                fill_history_hash=digest(s["fill_history"]),
                witnesses=copy.deepcopy(p),
            )
        s["used_settlements"].append(settlement)
        s["used_settlement_clocks"].append(economic_at)

    elif kind == "FUNDING":
        if s.get("funding_contract") == "SYNTHETIC_CAUSAL_R4":
            raise SafetyViolation("LEGACY_FUNDING_REQUIRES_LEGACY_GENESIS")
        _phase(s, "WAIT_ENTRY_ACK", "OPEN", "OPEN_RESIDUAL", "WAIT_TP1_ACK")
        exact(p, {"settlement_id", "settlement_at", "rate_fraction"})
        settlement = _text(p["settlement_id"], "SETTLEMENT_ID_INVALID")
        if (
            settlement in s["used_settlements"]
            or at in s["used_settlement_clocks"]
            or timestamp(p["settlement_at"]) != at
        ):
            raise SafetyViolation("FUNDING_DUPLICATE_OR_FUTURE")
        if s["phase"] == "WAIT_TP1_ACK" and at <= max(s["pending_at"].values(), default=-1):
            raise SafetyViolation("FUNDING_SETTLEMENT_COLLISION")
        if s["phase"] == "WAIT_ENTRY_ACK" and at <= s["entry_at"]:
            raise SafetyViolation("FUNDING_SETTLEMENT_COLLISION")
        bar = _bar(s, at)
        rate = decimal(p["rate_fraction"])
        if abs(rate) > Decimal("0.1"):
            raise SafetyViolation("FUNDING_RATE_BOUNDS")
        mark = decimal(bar["mark_close"], positive=True)
        qty = decimal(s["remaining_qty"], positive=True)
        cash = -Decimal(_position_side(s)) * qty * mark * rate
        _journal(s, "funding:" + settlement, "FUNDING", at, cash, qty)
        s["used_settlements"].append(settlement)
        s["used_settlement_clocks"].append(at)

    elif kind == "TP1":
        _phase(s, "OPEN")
        if s["tp1_filled"]:
            raise SafetyViolation("TP1_DUPLICATE")
        bar = _bar(s, at)
        qty = decimal(s["entry_qty"], positive=True)
        tier = ((qty * Decimal("0.5")) / LOT).to_integral_value(rounding=ROUND_FLOOR) * LOT
        if s.get("funding_contract") == "SYNTHETIC_CAUSAL_R4" and "executed_quantity" in p:
            executed = decimal(p["executed_quantity"], positive=True)
            if executed > tier or executed % LOT:
                raise SafetyViolation("PARTIAL_LOT_OR_MIN_NOTIONAL")
            tier = executed
        if (
            tier <= 0
            or qty - tier <= 0
            or tier * decimal(bar["last_close"]) < MIN_NOTIONAL
            or (qty - tier) * decimal(bar["last_close"]) < MIN_NOTIONAL
        ):
            raise SafetyViolation("PARTIAL_LOT_OR_MIN_NOTIONAL")
        target = decimal(s["proposal"]["tp1"], positive=True)
        long = _position_side(s) == 1
        traded = (
            decimal(bar["last_open"]) >= target if long else decimal(bar["last_open"]) <= target
        )
        through = (
            decimal(bar["last_high"]) >= target + TICK
            if long
            else decimal(bar["last_low"]) <= target - TICK
        )
        stop = decimal(s["stop"], positive=True)
        stop_hit = decimal(bar["last_low"]) <= stop if long else decimal(bar["last_high"]) >= stop
        if stop_hit:
            raise SafetyViolation("STOP_PRECEDES_TP1")
        if not (traded or through):
            raise SafetyViolation("TP1_TOUCH_NO_FILL")
        fill = _fill_price(target, s["proposal"]["side"], entry=False)
        _exit(s, event, "TP1", fill, tier)

    elif kind == "UPDATE_STOP":
        _phase(s, "OPEN_RESIDUAL")
        exact(p, set())
        bar = _bar(s, at)
        if at > bar["close_time"] + 1:
            raise SafetyViolation("STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY")
        if (
            s["tp1_ack_at"] is None
            or at <= s["tp1_ack_at"]
            or bar["open_time"] <= s["tp1_bar_open"]
        ):
            raise SafetyViolation("STOP_UPDATE_BEFORE_ACK_OR_SAME_BAR")
        entry = decimal(s["entry_price"], positive=True)
        # Solve price P&L after expected 5bp exit impact and both 6bp fees.
        if _position_side(s) == 1:
            raw = entry * (Decimal(1) + FEE) / ((Decimal(1) - ADVERSE_FILL) * (Decimal(1) - FEE))
            be = raw.quantize(TICK, rounding=ROUND_CEILING)
            while _fill_price(be, "LONG", entry=False) * (Decimal(1) - FEE) < entry * (
                Decimal(1) + FEE
            ):
                be += TICK
            s["stop"] = _d(max(decimal(s["stop"]), be))
        else:
            raw = entry * (Decimal(1) - FEE) / ((Decimal(1) + ADVERSE_FILL) * (Decimal(1) + FEE))
            be = raw.quantize(TICK, rounding=ROUND_FLOOR)
            while _fill_price(be, "SHORT", entry=False) * (Decimal(1) + FEE) > entry * (
                Decimal(1) - FEE
            ):
                be -= TICK
            s["stop"] = _d(min(decimal(s["stop"]), be))
        s["stop_update_source_hash"] = s["last_bar_hash"]

    elif kind in ("STOP", "TIME_CAP", "TP2"):
        _phase(s, "OPEN", "OPEN_RESIDUAL", "WAIT_TP1_ACK", "WAIT_ENTRY_ACK")
        bar = _bar(s, at)
        qty = decimal(s["remaining_qty"], positive=True)
        side = s["proposal"]["side"]
        if kind == "STOP":
            if s.get("stop_update_source_hash") == s["last_bar_hash"]:
                raise SafetyViolation("STOP_UPDATE_NOT_YET_EFFECTIVE")
            stop = decimal(s["stop"], positive=True)
            breached = (
                decimal(bar["last_low"]) <= stop
                if side == "LONG"
                else decimal(bar["last_high"]) >= stop
            )
            if not breached:
                raise SafetyViolation("STOP_NOT_BREACHED")
            gap = decimal(bar["last_open"], positive=True)
            price = min(stop, gap) if side == "LONG" else max(stop, gap)
        elif kind == "TIME_CAP":
            deadline = s["entry_at"] + s["proposal"]["horizon_hours"] * 3600000
            if bar["close_time"] < deadline:
                raise SafetyViolation("TIME_CAP_EARLY")
            if bar["close_time"] - deadline >= 60000:
                raise SafetyViolation("TIME_CAP_MISSED_FIRST_COMPLETED_BAR")
            stop = decimal(s["stop"], positive=True)
            stop_hit = (
                decimal(bar["last_low"]) <= stop
                if side == "LONG"
                else decimal(bar["last_high"]) >= stop
            )
            if stop_hit:
                raise SafetyViolation("STOP_PRECEDES_TIME_CAP")
            price = decimal(bar["last_close"], positive=True)
        else:
            if not s["tp1_filled"]:
                raise SafetyViolation("TP2_BEFORE_TP1")
            target = decimal(s["proposal"]["tp2"], positive=True)
            stop = decimal(s["stop"], positive=True)
            stop_hit = (
                decimal(bar["last_low"]) <= stop
                if side == "LONG"
                else decimal(bar["last_high"]) >= stop
            )
            if stop_hit:
                raise SafetyViolation("STOP_PRECEDES_TP2")
            gap = (
                decimal(bar["last_open"]) >= target
                if side == "LONG"
                else decimal(bar["last_open"]) <= target
            )
            through = (
                decimal(bar["last_high"]) >= target + TICK
                if side == "LONG"
                else decimal(bar["last_low"]) <= target - TICK
            )
            if not (gap or through):
                raise SafetyViolation("TP2_TOUCH_NO_FILL")
            if bar["open_time"] <= s["tp1_bar_open"]:
                raise SafetyViolation("TP2_SAME_BAR")
            price = target
        _exit(s, event, kind, _fill_price(price, side, entry=False), qty)

    elif kind == "OUTBOX_RECEIPT":
        exact(p, {"message_id"})
        _text(p["message_id"], "OUTBOX_ID_INVALID")
        # A local delivery receipt is operational only; it cannot change the ledger.
        if not any(row["key"] == p["message_id"] for row in s["outbox"]):
            raise SafetyViolation("OUTBOX_UNKNOWN")
        if p["message_id"] in s["delivered_outbox_ids"]:
            raise SafetyViolation("OUTBOX_RECEIPT_DUPLICATE")
        s["delivered_outbox_ids"].append(p["message_id"])

    else:
        raise SafetyViolation("EVENT_KIND_UNKNOWN")

    if required is not None and kind == required["kind"]:
        s["required_exit"] = None
    if kind != "OUTBOX_RECEIPT":
        s["last_at"] = at
        s["last_clock"] = at
    s["used_event_ids"].append(event_id)
    s["trace"].append(
        {"event": event_id, "kind": kind, "at": at, "trace_id": digest([event_id, kind])[:24]}
    )
    _check_portfolio(s)
    if kind not in ("BAR", "OUTBOX_RECEIPT"):
        s["outbox"].append(
            {
                "key": digest([event_id, "offline_outbox"]),
                "kind": ("NO_ACTION" if s["phase"] == "NO_ACTION" else "APPROVAL_NEEDED")
                if kind == "PROPOSE"
                else "EXECUTION_STATE",
                "event_kind": kind,
                "phase": s["phase"],
                "at": at,
                "trace_id": digest([event_id, kind])[:24],
                "source_hash": s["last_bar_hash"],
                "signal_id": s["proposal"]["signal_id"] if s["proposal"] else None,
                "cash": s["cash"],
                "available_cash": s["available_cash"],
                "remaining_qty": s["remaining_qty"],
                "safety_status": s["safety_status"],
            }
        )
    return s
