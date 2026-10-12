"""Adversarial synthetic witnesses for the pure preview reducer."""

from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition


def ev(kind: str, at: int, payload: dict | None = None, label: str | None = None) -> dict:
    return {"id": label or f"{kind}-{at}", "kind": kind, "at": at, "payload": payload or {}}


def bar(open_time: int = 0, *, last: str = "100", high: str = "101",
        low: str = "99", mark: str = "100") -> dict:
    return {"source": "SYNTHETIC_V1", "open_time": open_time,
            "close_time": open_time + 59999, "available_at": open_time + 59999,
            "last_open": last, "last_high": high, "last_low": low,
            "last_close": last, "mark_close": mark}


def proposal(source_hash: str, *, side: str = "LONG", qty: str = "0.02") -> dict:
    return {"schema_version": 1, "signal_id": "s1", "source_hash": source_hash,
            "source_close_at": 59999, "decision_at": 60000, "side": side,
            "quantity": qty, "stop": "95" if side == "LONG" else "105",
            "tp1": "105" if side == "LONG" else "95",
            "tp2": "110" if side == "LONG" else "90", "horizon_hours": 12,
            "expires_at": 180000, "version": 1,
            "exit_identity": "OFFLINE_TP1_BE_TIME_CAP_V1"}


def fresh(*, side: str = "LONG", qty: str = "0.02") -> tuple[dict, dict, dict]:
    b = bar()
    p = proposal(digest(b), side=side, qty=qty)
    token = {"token_id": "human1", "signal_id": "s1", "proposal_hash": digest(p),
             "proposal_version": 1, "quantity": qty, "issued_at": 60002,
             "expires_at": 160000, "approved": True, "issuer": "TRUSTED_HUMAN_FIXTURE"}
    return initial_state([token]), b, p


def analyzed(*, side: str = "LONG", qty: str = "0.02") -> dict:
    s, b, p = fresh(side=side, qty=qty)
    s = transition(s, ev("BAR", 59999, b))
    s = transition(s, ev("PROPOSE", 60000, p))
    analysis = {"schema_version": 1, "signal_id": "s1", "proposal_hash": digest(p),
                "source_hash": digest(b), "as_of": 60000, "summary": "Synthetic risk note",
                "risk": "DESCRIPTIVE_ONLY"}
    return transition(s, ev("ANALYZE", 60001, analysis))


def open_position(*, side: str = "LONG", qty: str = "0.02") -> dict:
    s = analyzed(side=side, qty=qty)
    s = transition(s, ev("APPROVE", 60002, {"token_id": "human1"}))
    s = transition(s, ev("PLACE", 60003))
    s = transition(s, ev("FILL_ENTRY", 60004, {"fill_id": "entry1"}))
    s = transition(s, ev("BAR", 119999, bar(60000)))
    return transition(s, ev("ACK", 120004,
                            {"ack_id": "ackentry", "order_id": s["order_id"],
                             "fill_id": "entry1"}))


def next_bar(s: dict, *, last: str = "100", high: str = "101", low: str = "99",
             mark: str = "100") -> dict:
    opened = s["last_bar"]["open_time"] + 60000
    return transition(s, ev("BAR", opened + 59999,
                            bar(opened, last=last, high=high, low=low, mark=mark)))


def rejected(s: dict, e: dict, code: str) -> None:
    original = copy.deepcopy(s)
    with pytest.raises(SafetyViolation) as captured:
        transition(s, e)
    assert captured.value.code == code
    assert s == original


@pytest.mark.parametrize(("mutation", "code"), [
    ({"source": "EXCHANGE_REAL"}, "SOURCE_UNAUTHORIZED"),
    ({"close_time": 60000}, "BAR_PIT_INVALID"),
    ({"available_at": 60001}, "BAR_PIT_INVALID"),
    ({"last_open": "0"}, "DECIMAL_BOUNDS"),
    ({"last_high": "98"}, "BAR_OHLC_INVALID"),
    ({"last_low": "102"}, "BAR_OHLC_INVALID"),
    ({"mark_close": "NaN"}, "DECIMAL_BOUNDS"),
    ({"mark_close": "1e-9999"}, "DECIMAL_BOUNDS"),
    ({"extra": "x"}, "SCHEMA_FIELDS"),
])
def test_bad_bar_fails_closed(mutation: dict, code: str) -> None:
    s, b, _ = fresh()
    rejected(s, ev("BAR", 59999, b | mutation), code)


@pytest.mark.parametrize(("mutation", "code"), [
    ({"source_hash": "bad"}, "PROPOSAL_SOURCE_DRIFT"),
    ({"source_close_at": 60000}, "PROPOSAL_SOURCE_DRIFT"),
    ({"decision_at": 59998}, "PROPOSAL_PIT_OR_EXPIRY"),
    ({"decision_at": 60001}, "PROPOSAL_PIT_OR_EXPIRY"),
    ({"quantity": "0.051"}, "QUANTITY_INVALID"),
    ({"quantity": "0.0205"}, "QUANTITY_INVALID"),
    ({"stop": "101"}, "LEVEL_ORDER_INVALID"),
    ({"tp1": "99"}, "LEVEL_ORDER_INVALID"),
    ({"horizon_hours": 36}, "HORIZON_INVALID"),
    ({"version": 2}, "PROPOSAL_VERSION"),
    ({"exit_identity": "REAL_ORDER"}, "EXIT_IDENTITY_INVALID"),
    ({"expires_at": 60000}, "PROPOSAL_PIT_OR_EXPIRY"),
    ({"evil": "x"}, "SCHEMA_FIELDS"),
])
def test_bad_proposal_fails_closed(mutation: dict, code: str) -> None:
    s, b, p = fresh()
    s = transition(s, ev("BAR", 59999, b))
    rejected(s, ev("PROPOSE", 60000, p | mutation), code)


@pytest.mark.parametrize(("mutation", "code"), [
    ({"proposal_hash": "bad"}, "ANALYSIS_STALE_OR_HALLUCINATED"),
    ({"signal_id": "hallucinated"}, "ANALYSIS_STALE_OR_HALLUCINATED"),
    ({"as_of": 60002}, "ANALYSIS_AUTHORITY_OR_CLOCK"),
    ({"risk": "APPROVE"}, "ANALYSIS_AUTHORITY_OR_CLOCK"),
    ({"summary": "api_key=private"}, "SECRET_IN_EVENT"),
    ({"place_order": True}, "SCHEMA_FIELDS"),
])
def test_model_has_no_authority(mutation: dict, code: str) -> None:
    s, b, p = fresh()
    s = transition(s, ev("BAR", 59999, b))
    s = transition(s, ev("PROPOSE", 60000, p))
    a = {"schema_version": 1, "signal_id": "s1", "proposal_hash": digest(p),
         "source_hash": digest(b), "as_of": 60000, "summary": "synthetic",
         "risk": "DESCRIPTIVE_ONLY"}
    rejected(s, ev("ANALYZE", 60001, a | mutation), code)


def test_manual_gate_and_entry_ack() -> None:
    s = analyzed()
    rejected(s, ev("PLACE", 60002), "PHASE_INVALID")
    rejected(s, ev("APPROVE", 60002, {"token_id": "invented"}), "APPROVAL_UNTRUSTED_OR_REPLAYED")
    s = transition(s, ev("APPROVE", 60002, {"token_id": "human1"}))
    rejected(s, ev("APPROVE", 60002, {"token_id": "human1"}, "again"), "PHASE_INVALID")
    s = transition(s, ev("PLACE", 60003))
    assert s["order_id"] == digest([s["proposal_hash"], "SIMULATED_ENTRY"])
    s = transition(s, ev("FILL_ENTRY", 60004, {"fill_id": "entry1"}))
    assert s["phase"] == "WAIT_ENTRY_ACK"
    assert Decimal(s["available_cash"]) < Decimal(1000)
    rejected(s, ev("FUNDING", 60004, {"settlement_id": "f1", "settlement_at": 60004,
                                       "rate_fraction": "0.001"}), "FUNDING_SETTLEMENT_COLLISION")
    s = transition(s, ev("FUNDING", 60005, {"settlement_id": "f1", "settlement_at": 60005,
                                           "rate_fraction": "0.001"}))
    assert Decimal(s["journal"][-1]["cash_delta"]) == Decimal("-0.002")
    assert s["phase"] == "WAIT_ENTRY_ACK"
    rejected(s, ev("ACK", 60005, {"ack_id": "a1", "order_id": s["order_id"],
                                   "fill_id": "entry1"}), "ACK_BEFORE_FILL_OR_WRONG_ID")
    s = transition(s, ev("ACK", 120004, {"ack_id": "a1", "order_id": s["order_id"],
                                    "fill_id": "entry1"}))
    assert s["phase"] == "OPEN"
    assert s["position"]["remaining_quantity"] == "0.02"
    assert s["counters"]["actual_private_or_network_calls"] == 0


def test_signed_funding_and_replay_rejected() -> None:
    s = open_position()
    s = next_bar(s, mark="110")
    at = s["last_at"]
    s = transition(s, ev("FUNDING", at, {"settlement_id": "f1", "settlement_at": at,
                                         "rate_fraction": "0.001"}))
    assert Decimal(s["journal"][-1]["cash_delta"]) == Decimal("-0.00220")
    rejected(s, ev("FUNDING", at, {"settlement_id": "f1", "settlement_at": at,
                                  "rate_fraction": "0.001"}, "dup"), "FUNDING_DUPLICATE_OR_FUTURE")
    s = transition(s, ev("FUNDING", at, {"settlement_id": "f2", "settlement_at": at,
                                         "rate_fraction": "-0.001"}, "rev"))
    assert Decimal(s["journal"][-1]["cash_delta"]) == Decimal("0.00220")


def test_short_funding_sign_and_mark_not_last() -> None:
    s = open_position(side="SHORT")
    s = next_bar(s, mark="110")
    at = s["last_at"]
    s = transition(s, ev("FUNDING", at, {"settlement_id": "f1", "settlement_at": at,
                                         "rate_fraction": "0.001"}))
    assert Decimal(s["journal"][-1]["cash_delta"]) == Decimal("0.00220")


def test_partial_cash_waits_for_ack_and_uses_residual_for_funding() -> None:
    s = open_position()
    s = next_bar(s, last="105", high="105.2", low="104.8", mark="105")
    before = s["cash"]
    s = transition(s, ev("TP1", s["last_at"], {"fill_id": "tier1"}))
    assert s["cash"] == before
    assert Decimal(s["remaining_qty"]) == Decimal("0.01")
    assert s["phase"] == "WAIT_TP1_ACK"
    rejected(s, ev("FUNDING", s["last_at"], {"settlement_id": "f1",
                     "settlement_at": s["last_at"], "rate_fraction": "0.001"}), "FUNDING_SETTLEMENT_COLLISION")
    s = next_bar(s, last="105", high="106", low="104", mark="110")
    ack_at = s["last_at"]
    s = transition(s, ev("FUNDING", ack_at, {"settlement_id": "f1", "settlement_at": ack_at,
                                             "rate_fraction": "0.001"}))
    assert Decimal(s["journal"][-1]["cash_delta"]) == Decimal("-0.00110")
    s = transition(s, ev("ACK", ack_at, {"ack_id": "a2", "order_id": s["order_id"],
                                      "fill_id": "tier1"}))
    assert s["phase"] == "OPEN_RESIDUAL"


def test_tp_touch_does_not_fill_and_stop_precedes_tp() -> None:
    s = open_position()
    b = bar(120000, last="105", high="105", low="104")
    b["last_open"] = "104.9"
    s = transition(s, ev("BAR", 179999, b))
    rejected(s, ev("TP1", s["last_at"], {"fill_id": "tier1"}), "TP1_TOUCH_NO_FILL")
    s = next_bar(s, last="100", high="106", low="94")
    rejected(s, ev("TP1", s["last_at"], {"fill_id": "tier1"}), "STOP_PRECEDES_TP1")


def test_stop_update_needs_later_bar_and_never_loosens() -> None:
    s = open_position()
    s = next_bar(s, last="105", high="105.2", low="104.8")
    s = transition(s, ev("TP1", s["last_at"], {"fill_id": "tier1"}))
    s = next_bar(s, last="105", high="106", low="104")
    at = s["last_at"]
    s = transition(s, ev("ACK", at, {"ack_id": "a2", "order_id": s["order_id"],
                                   "fill_id": "tier1"}))
    rejected(s, ev("UPDATE_STOP", at), "STOP_UPDATE_BEFORE_ACK_OR_SAME_BAR")
    s = next_bar(s, last="105", high="106", low="104")
    s = transition(s, ev("UPDATE_STOP", s["last_at"]))
    assert Decimal(s["stop"]) > Decimal(100)


def test_final_stop_ack_and_cooldown() -> None:
    s = open_position()
    s = next_bar(s, last="95", high="96", low="94")
    s = transition(s, ev("STOP", s["last_at"], {"fill_id": "stop1"}))
    assert s["phase"] == "EXIT_WAIT_ACK"
    assert Decimal(s["remaining_qty"]) == 0
    rejected(s, ev("ACK", s["last_at"], {"ack_id": "a2", "order_id": s["order_id"],
                                            "fill_id": "stop1"}), "ACK_BEFORE_FILL_OR_WRONG_ID")
    at = s["last_at"] + 60000
    s = transition(s, ev("ACK", at, {"ack_id": "a2", "order_id": s["order_id"],
                                   "fill_id": "stop1"}))
    assert s["phase"] == "CLOSED"
    assert Decimal(s["reserved_notional"]) == 0
    assert not s["pending_cash"]
    assert s["position"] is None
    assert s["cooldown_until"] == at + 6 * 3600000
    json.dumps(s)


def test_reordered_and_duplicate_event_fail_without_mutation() -> None:
    s = open_position()
    rejected(s, ev("BAR", 59999, bar(), "old"), "EVENT_REORDERED")
    rejected(s, ev("ACK", 120004, {"ack_id": "other", "order_id": s["order_id"],
                                      "fill_id": "entry1"}, "ACK-120004"), "EVENT_DUPLICATE")


def test_outbox_receipt_cannot_change_cash() -> None:
    s = analyzed()
    key = s["outbox"][0]["key"]
    cash = s["cash"]
    s = transition(s, ev("OUTBOX_RECEIPT", s["last_at"], {"message_id": key}))
    assert s["cash"] == cash
    assert not s["journal"]
    assert len(s["delivered_outbox_ids"]) == 1
    rejected(s, ev("OUTBOX_RECEIPT", s["last_at"], {"message_id": key}, "replayed"),
             "OUTBOX_RECEIPT_DUPLICATE")


def test_outbox_tracks_execution_without_bar_noise() -> None:
    s, b, p = fresh()
    s = transition(s, ev("BAR", 59999, b))
    assert s["outbox"] == []
    s = transition(s, ev("PROPOSE", 60000, p))
    assert [row["kind"] for row in s["outbox"]] == ["APPROVAL_NEEDED"]
    a = {"schema_version": 1, "signal_id": "s1", "proposal_hash": digest(p),
         "source_hash": digest(b), "as_of": 60000, "summary": "synthetic",
         "risk": "DESCRIPTIVE_ONLY"}
    s = transition(s, ev("ANALYZE", 60001, a))
    assert s["outbox"][-1]["event_kind"] == "ANALYZE"
    assert s["outbox"][-1]["phase"] == "ANALYZED"
    assert s["outbox"][-1]["trace_id"]
    s = transition(s, ev("BAR", 119999, bar(60000)))
    assert len(s["outbox"]) == 2


def test_analysis_bool_version_and_expiry_rejected() -> None:
    s, b, p = fresh()
    s = transition(s, ev("BAR", 59999, b))
    rejected(s, ev("PROPOSE", 60000, p | {"schema_version": True}), "PROPOSAL_VERSION")
    s = transition(s, ev("PROPOSE", 60000, p))
    a = {"schema_version": 1, "signal_id": "s1", "proposal_hash": digest(p),
         "source_hash": digest(b), "as_of": 60000, "summary": "synthetic",
         "risk": "DESCRIPTIVE_ONLY"}
    rejected(s, ev("ANALYZE", 60001, a | {"schema_version": True}),
             "ANALYSIS_STALE_OR_HALLUCINATED")
    rejected(s, ev("ANALYZE", 180000, a), "ANALYSIS_EXPIRED")


def test_time_cap_uses_first_completed_bar_last_close_and_stop_priority() -> None:
    s = open_position()
    deadline = s["entry_at"] + 12 * 3600000
    while s["last_bar"]["close_time"] + 60000 < deadline:
        s = next_bar(s)
    rejected(s, ev("TIME_CAP", s["last_at"], {"fill_id": "tooearly"}), "TIME_CAP_EARLY")
    opened = s["last_bar"]["open_time"] + 60000
    end_bar = bar(opened, last="101", high="102", low="99")
    end_bar["last_open"] = "100"
    stop_bar = end_bar | {"last_low": "94"}
    stopped = transition(s, ev("BAR", opened + 59999, stop_bar))
    rejected(stopped, ev("TIME_CAP", stopped["last_at"], {"fill_id": "cap1"}),
             "STOP_PRECEDES_TIME_CAP")
    s = transition(s, ev("BAR", opened + 59999, end_bar))
    s = transition(s, ev("TIME_CAP", s["last_at"], {"fill_id": "cap1"}))
    assert s["trace"][-2]["fill_price"] == "100.9"
    assert s["phase"] == "EXIT_WAIT_ACK"


def test_trusted_fixture_rejects_implicit_approval() -> None:
    with pytest.raises(SafetyViolation, match="APPROVAL_FIXTURE_INVALID"):
        initial_state([{"token_id": "auto", "approved": True}])
