"""Small, serializable contracts for the synthetic offline preview."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any


class SafetyViolation(ValueError):
    """A rejected event; the reducer leaves its input state untouched."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SafetyViolation("NON_CANONICAL_INPUT") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def redact_text(value: str) -> str:
    """Scrub accidental synthetic credential-like text before diagnostic output."""
    if not isinstance(value, str):
        raise SafetyViolation("TEXT_INVALID")
    value = re.sub(r"(?i)\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*\S+", "[REDACTED]", value)
    value = re.sub(r"(?i)\bbearer\s+\S+", "[REDACTED]", value)
    return value


def decimal(value: Any, *, positive: bool = False, zero_ok: bool = True) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise SafetyViolation("DECIMAL_STRING_REQUIRED")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value) is None:
        raise SafetyViolation("DECIMAL_BOUNDS")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise SafetyViolation("DECIMAL_INVALID") from exc
    if not number.is_finite() or (positive and number <= 0) or (not zero_ok and number == 0):
        raise SafetyViolation("DECIMAL_BOUNDS")
    if abs(number) > Decimal(1000000000):
        raise SafetyViolation("DECIMAL_BOUNDS")
    return number


def exact(value: Any, keys: set[str], code: str = "SCHEMA_FIELDS") -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise SafetyViolation(code)


def timestamp(value: Any) -> int:
    if type(value) is not int or value < 0 or value > 4102444800000:
        raise SafetyViolation("TIMESTAMP_INVALID")
    return value


def initial_state(trusted_approvals: list[dict[str, Any]]) -> dict[str, Any]:
    """The fixture's explicit human tokens are trusted input, never model output."""
    if not isinstance(trusted_approvals, list):
        raise SafetyViolation("APPROVAL_FIXTURE_INVALID")
    token_keys = {
        "token_id",
        "signal_id",
        "proposal_hash",
        "proposal_version",
        "quantity",
        "issued_at",
        "expires_at",
        "approved",
        "issuer",
    }
    tokens: dict[str, dict[str, Any]] = {}
    for raw in trusted_approvals:
        exact(raw, token_keys, "APPROVAL_FIXTURE_INVALID")
        if not isinstance(raw["token_id"], str) or not raw["token_id"] or raw["token_id"] in tokens:
            raise SafetyViolation("APPROVAL_FIXTURE_INVALID")
        if raw["approved"] is not True or raw["issuer"] != "TRUSTED_HUMAN_FIXTURE":
            raise SafetyViolation("APPROVAL_FIXTURE_INVALID")
        if type(raw["proposal_version"]) is not int or raw["proposal_version"] != 1:
            raise SafetyViolation("APPROVAL_FIXTURE_INVALID")
        decimal(raw["quantity"], positive=True)
        if timestamp(raw["issued_at"]) >= timestamp(raw["expires_at"]):
            raise SafetyViolation("APPROVAL_FIXTURE_INVALID")
        if not isinstance(raw["signal_id"], str) or not isinstance(raw["proposal_hash"], str):
            raise SafetyViolation("APPROVAL_FIXTURE_INVALID")
        tokens[raw["token_id"]] = dict(raw)
    return {
        "schema_version": 1,
        "safety_status": "DRY_RUN_NO_NETWORK_NO_ORDERING",
        "phase": "READY",
        "last_at": -1,
        "last_bar": None,
        "last_bar_hash": None,
        "market": None,
        "last_clock": -1,
        "proposal": None,
        "proposal_hash": None,
        "analysis": None,
        "analysis_at": None,
        "approval": None,
        "trusted_approvals": tokens,
        "used_tokens": [],
        "used_settlements": [],
        "used_settlement_clocks": [],
        "used_fill_ids": [],
        "required_exit": None,
        "used_signal_ids": [],
        "entry_acknowledged": False,
        "used_ack_ids": [],
        "delivered_outbox_ids": [],
        "used_event_ids": [],
        "order_id": None,
        "entry_fill_id": None,
        "entry_at": None,
        "entry_price": None,
        "entry_qty": "0",
        "remaining_qty": "0",
        "stop": None,
        "tp1_filled": False,
        "tp1_ack_at": None,
        "tp1_bar_open": None,
        "cooldown_until": 0,
        "cash": "1000",
        "reserved_notional": "0",
        "pending_cash": {},
        "pending_release": {},
        "pending_kind": {},
        "pending_at": {},
        "position": None,
        "available_cash": "1000",
        "mark_equity": "1000",
        "journal": [],
        "outbox": [],
        "trace": [],
        "counters": {
            "false_approvals_accepted": 0,
            "actual_private_or_network_calls": 0,
            "duplicate_cash_charges": 0,
            "oversize_exposure": 0,
            "phantom_spendable_ack": 0,
        },
    }
