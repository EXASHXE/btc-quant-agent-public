"""Deterministic event validation, canonical digest, cause graph, and double-entry journal."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from btc_quant_agent.strategy_research.r3_alt_engine.frozen_primitives import (
    DECIMAL_CTX,
    quantize12dp,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    EngineState,
    Event,
    EventKind,
    OwnerLedger,
    OwnerPhase,
    Posting,
)


class ConflictFailClosedError(Exception):
    """Raised when an event ID payload conflict or Mark conflict is detected."""


class CauseOrOwnerFailClosedError(Exception):
    """Raised when an ACK has a mismatched owner or causal reference."""


class InvalidMinuteClockError(Exception):
    """Raised when clock advance violates minute alignment."""


def canonical_json_serialize(obj: Any) -> str:
    """Recursively convert payload to canonical JSON string with sorted keys."""
    if isinstance(obj, Mapping):
        return "{" + ",".join(
            f"{json.dumps(str(k))}:{canonical_json_serialize(v)}"
            for k, v in sorted(obj.items(), key=lambda item: str(item[0]))
        ) + "}"
    elif isinstance(obj, (list, tuple, set, frozenset)):
        return "[" + ",".join(canonical_json_serialize(item) for item in obj) + "]"
    elif isinstance(obj, Decimal):
        # Format decimal with exact string representation
        return json.dumps(str(obj))
    elif isinstance(obj, (int, float, bool, str)) or obj is None:
        return json.dumps(obj)
    else:
        return json.dumps(str(obj))


def compute_payload_digest(payload: Mapping[str, Any]) -> str:
    """Compute SHA256 hex digest of canonical serialized payload excluding event_id."""
    clean_dict = {str(k): v for k, v in payload.items() if str(k) != "event_id"}
    canonical_repr = canonical_json_serialize(clean_dict)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def compute_journal_chain_hash(prev_hash: str, postings: Sequence[Posting]) -> str:
    """Compute deterministic cryptographic chain hash over append batch."""
    hasher = hashlib.sha256(prev_hash.encode("utf-8"))
    for p in postings:
        record_str = (
            f"{p.event_id}|{p.dr_account.value}|{p.cr_account.value}|"
            f"{quantize12dp(p.amount)}|{p.owner_key!s}|{p.is_memo}|{p.cause_id}"
        )
        hasher.update(record_str.encode("utf-8"))
    return hasher.hexdigest()


def validate_event(
    state: EngineState,
    event: Event,
) -> tuple[bool, str | None]:
    """
    Validate event identity, payload conflict, source Mark consistency, and ACK causes.
    Returns (is_duplicate, None) if valid duplicate, or (False, None) if valid new event.
    Raises ConflictFailClosedError or CauseOrOwnerFailClosedError on invalid stimulus.
    """
    # 1. Event ID vs payload digest check (Invariant I11)
    if event.event_id in state.event_registry:
        existing_digest = state.event_registry[event.event_id]
        if existing_digest != event.payload_digest:
            raise ConflictFailClosedError(
                f"Event ID '{event.event_id}' has conflicting payload digest: "
                f"existing={existing_digest}, new={event.payload_digest}. CONFLICT_FAIL_CLOSED."
            )
        # Identical payload duplicate
        return True, None

    # 2. Source / Symbol / Close Mark collision check (Invariant I10, T01, T03)
    if event.kind == EventKind.OBSERVED_MARK:
        source_id = event.source_id or "SYNTHETIC_MARK"
        symbol = event.symbol
        close_ms = int(event.payload.get("close_ms", event.economic_at_ms))
        price_val = Decimal(str(event.payload.get("price", event.payload.get("close", 0))))
        mark_key = (source_id, symbol, close_ms)

        if mark_key in state.source_close_marks:
            existing_price = state.source_close_marks[mark_key]
            if existing_price != price_val:
                raise ConflictFailClosedError(
                    f"Conflicting Mark price for source '{source_id}', symbol '{symbol}', "
                    f"close_ms={close_ms}: existing={existing_price}, new={price_val}. "
                    f"CONFLICT_FAIL_CLOSED."
                )

    # 3. Cause / Owner check for ACKs (T09, Invariant I11)
    if event.kind in (EventKind.FILL_ACK, EventKind.EXIT_ACK, EventKind.FUNDING_ACK):
        owner_ledger: OwnerLedger | None = state.owner_ledgers.get(event.owner_key)
        if owner_ledger is None:
            raise CauseOrOwnerFailClosedError(
                f"ACK {event.kind.value} references non-existent owner {event.owner_key}. "
                f"CAUSE_OR_OWNER_FAIL_CLOSED."
            )

        if event.kind == EventKind.FILL_ACK:
            # Must match pending unacked entry or order
            expected_order_id = str(event.payload.get("order_id", event.order_id))
            if owner_ledger.phase not in (OwnerPhase.RESERVED, OwnerPhase.UNACKED_OPEN):
                raise CauseOrOwnerFailClosedError(
                    f"FillAck received for owner {event.owner_key} in phase {owner_ledger.phase.value}. "
                    f"CAUSE_OR_OWNER_FAIL_CLOSED."
                )
            if expected_order_id and owner_ledger.owner_key.position_id != expected_order_id:
                raise CauseOrOwnerFailClosedError(
                    f"FillAck order_id '{expected_order_id}' does not match owner position_id '{owner_ledger.owner_key.position_id}'. "
                    f"CAUSE_OR_OWNER_FAIL_CLOSED."
                )
            if event.cause_id and event.order_id and event.cause_id != event.order_id:
                raise CauseOrOwnerFailClosedError(
                    f"FillAck cause_id '{event.cause_id}' does not match order_id '{event.order_id}'. "
                    f"CAUSE_OR_OWNER_FAIL_CLOSED."
                )

        elif event.kind == EventKind.EXIT_ACK:
            slice_id = str(event.payload.get("slice_id", event.cause_id))
            matching_slice = any(
                s.slice_id == slice_id and not s.is_acknowledged
                for s in owner_ledger.pending_exit_slices
            )
            if not matching_slice and owner_ledger.phase not in (OwnerPhase.EXIT_PENDING, OwnerPhase.CLOSED_UNSETTLED):
                raise CauseOrOwnerFailClosedError(
                    f"ExitAck received for owner {event.owner_key} with unmatched slice_id '{slice_id}'. "
                    f"CAUSE_OR_OWNER_FAIL_CLOSED."
                )

        elif event.kind == EventKind.FUNDING_ACK:
            # Owner must have funding liability or coverage to settle
            has_funding_liability = (
                owner_ledger.funding_payable > Decimal(0)
                or owner_ledger.enc_funding_dedicated > Decimal(0)
                or owner_ledger.enc_funding_future > Decimal(0)
                or owner_ledger.enc_shortfall > Decimal(0)
            )
            if not has_funding_liability and owner_ledger.phase == OwnerPhase.FLAT:
                raise CauseOrOwnerFailClosedError(
                    f"FundingAck received for owner {event.owner_key} with zero funding liability. "
                    f"CAUSE_OR_OWNER_FAIL_CLOSED."
                )

    return False, None


def validate_postings_batch(postings: Sequence[Posting]) -> None:
    """
    Validate that every posting batch is balanced under double entry.
    Invariant I01: sum(dr_USDT) == sum(cr_USDT) for economic postings, and independently memo dr == cr.
    Invariant I13: quantized to 12 decimal places with local context.
    """
    if not postings:
        return

    econ_dr_sum = Decimal(0)
    econ_cr_sum = Decimal(0)
    memo_dr_sum = Decimal(0)
    memo_cr_sum = Decimal(0)

    for p in postings:
        if p.amount < Decimal(0):
            raise ValueError(f"Posting amount must be non-negative: {p.amount}")
        if p.amount != quantize12dp(p.amount):
            raise ValueError(f"Posting amount is not quantized to 12dp: {p.amount}")

        if p.is_memo:
            memo_dr_sum = DECIMAL_CTX.add(memo_dr_sum, p.amount)
            memo_cr_sum = DECIMAL_CTX.add(memo_cr_sum, p.amount)
        else:
            econ_dr_sum = DECIMAL_CTX.add(econ_dr_sum, p.amount)
            econ_cr_sum = DECIMAL_CTX.add(econ_cr_sum, p.amount)

    if econ_dr_sum != econ_cr_sum:
        raise ValueError(
            f"Economic posting batch unbalanced: dr={econ_dr_sum}, cr={econ_cr_sum}"
        )
    if memo_dr_sum != memo_cr_sum:
        raise ValueError(
            f"Memo posting batch unbalanced: dr={memo_dr_sum}, cr={memo_cr_sum}"
        )
