"""Categories 1 & 2 Assurance: Approval authority and temporal/price causality."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from scripts.g1_offline_preview_r1.__main__ import OfflineLLMAnalysisPort
from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.strategy_research.g1_offline_assurance_r1.oracle import (
    build_state_at_phase,
    make_analysis,
    make_bar,
    make_event,
    make_proposal,
    make_token,
    record_negative_transition,
)


@pytest.mark.parametrize(
    "phase", ["READY", "BAR_LOADED", "PROPOSED", "ANALYZED"]
)
@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("PLACE", {}),
        ("FILL_ENTRY", {"fill_id": "unapproved-fill"}),
    ],
)
def test_no_intent_or_fill_before_valid_human_approval(
    phase: str, kind: str, payload: dict[str, Any]
) -> None:
    s, _, _, _ = build_state_at_phase(phase)
    rec = record_negative_transition(
        f"unapproved_{kind}_in_{phase}",
        "approval_authority",
        s,
        make_event(kind, 60003, payload),
        "PHASE_INVALID",
    )
    assert rec["after"]["order_id"] is None
    assert rec["after"]["journal_len"] == 0
    assert rec["after"]["cash"] == "1000"


def test_absent_human_token_fixture_never_approves_or_places() -> None:
    b0 = make_bar(0)
    prop = make_proposal(digest(b0))
    analysis = make_analysis(prop)
    s = initial_state([])
    s = transition(s, make_event("BAR", 59999, b0))
    s = transition(s, make_event("PROPOSE", 60000, prop))
    s = transition(s, make_event("ANALYZE", 60001, analysis))
    rec = record_negative_transition(
        "human_token_absent",
        "approval_authority",
        s,
        make_event("APPROVE", 60002, {"token_id": "tok-1"}),
        "APPROVAL_UNTRUSTED_OR_REPLAYED",
    )
    assert rec["after"]["phase"] == "ANALYZED"
    assert rec["after"]["order_id"] is None
    assert rec["after"]["journal_len"] == 0


@pytest.mark.parametrize(
    ("case_id", "token_override", "approve_at", "expected_code"),
    [
        ("malicious_unknown_token_id", {}, 60002, "APPROVAL_UNTRUSTED_OR_REPLAYED"),
        ("other_order_signal_id", {"signal_id": "other-signal"}, 60002, "APPROVAL_DRIFT"),
        ("tampered_proposal_hash", {"proposal_hash": "00" * 32}, 60002, "APPROVAL_DRIFT"),
        ("wrong_token_quantity", {"quantity": "0.03"}, 60002, "APPROVAL_DRIFT"),
        ("token_issued_before_analysis", {"issued_at": 60000}, 60002, "APPROVAL_STALE_OR_REORDERED"),
        ("future_token_issued_after_approve", {"issued_at": 60005}, 60002, "APPROVAL_STALE_OR_REORDERED"),
        ("stale_expired_token", {"expires_at": 60003}, 60003, "APPROVAL_STALE_OR_REORDERED"),
        ("approval_crossing_proposal_expiry", {"expires_at": 200000}, 180000, "APPROVAL_STALE_OR_REORDERED"),
    ],
)
def test_approval_token_authority_and_clock_violations(
    case_id: str,
    token_override: dict[str, Any],
    approve_at: int,
    expected_code: str,
) -> None:
    b0 = make_bar(0)
    prop = make_proposal(digest(b0))
    tok = make_token(prop, **token_override)
    s = initial_state([tok])
    s = transition(s, make_event("BAR", 59999, b0))
    s = transition(s, make_event("PROPOSE", 60000, prop))
    s = transition(s, make_event("ANALYZE", 60001, make_analysis(prop)))
    requested_token_id = "forged-token" if case_id == "malicious_unknown_token_id" else tok["token_id"]
    rec = record_negative_transition(
        case_id,
        "approval_authority",
        s,
        make_event("APPROVE", approve_at, {"token_id": requested_token_id}),
        expected_code,
    )
    assert rec["after"]["order_id"] is None
    assert rec["after"]["journal_len"] == 0


@pytest.mark.parametrize(
    ("bad_token_field", "override"),
    [
        ("approved_false", {"approved": False}),
        ("untrusted_issuer", {"issuer": "LLM_AUTO_APPROVER"}),
        ("wrong_proposal_version", {"proposal_version": 2}),
        ("bool_proposal_version", {"proposal_version": True}),
        ("zero_quantity", {"quantity": "0"}),
        ("inverted_issue_expiry", {"issued_at": 70000, "expires_at": 70000}),
    ],
)
def test_initial_state_rejects_malformed_trusted_approval_fixtures(
    bad_token_field: str, override: dict[str, Any]
) -> None:
    b0 = make_bar(0)
    prop = make_proposal(digest(b0))
    tok = make_token(prop, **override)
    with pytest.raises(SafetyViolation, match="APPROVAL_FIXTURE_INVALID"):
        initial_state([tok])


def test_double_approval_and_token_replay_across_lifecycle_rejected() -> None:
    s, _, _, tok = build_state_at_phase("APPROVED")
    record_negative_transition(
        "double_approval_in_approved_phase",
        "approval_authority",
        s,
        make_event("APPROVE", 60003, {"token_id": tok["token_id"]}, "APPROVE-DUP"),
        "PHASE_INVALID",
    )
    # Force state back to ANALYZED with already-used token in used_tokens to prove token replay guard
    s_replay = {**s, "phase": "ANALYZED"}
    record_negative_transition(
        "replayed_token_id_rejected",
        "approval_authority",
        s_replay,
        make_event("APPROVE", 60003, {"token_id": tok["token_id"]}, "APPROVE-REPLAY"),
        "APPROVAL_UNTRUSTED_OR_REPLAYED",
    )


@pytest.mark.parametrize(
    ("mutation_name", "analysis_override", "analyze_at", "expected_code"),
    [
        ("wrong_signal_id", {"signal_id": "hallucinated-sig"}, 60001, "ANALYSIS_STALE_OR_HALLUCINATED"),
        ("wrong_proposal_hash", {"proposal_hash": "ff" * 32}, 60001, "ANALYSIS_STALE_OR_HALLUCINATED"),
        ("wrong_source_hash", {"source_hash": "aa" * 32}, 60001, "ANALYSIS_STALE_OR_HALLUCINATED"),
        ("elevated_risk_authority", {"risk": "EXECUTE_NOW"}, 60001, "ANALYSIS_AUTHORITY_OR_CLOCK"),
        ("as_of_before_decision", {"as_of": 59999}, 60001, "ANALYSIS_AUTHORITY_OR_CLOCK"),
        ("as_of_in_future", {"as_of": 60002}, 60001, "ANALYSIS_AUTHORITY_OR_CLOCK"),
        ("analysis_at_proposal_expiry", {}, 180000, "ANALYSIS_EXPIRED"),
        ("empty_summary", {"summary": ""}, 60001, "ANALYSIS_SUMMARY_INVALID"),
    ],
)
def test_mutated_synthetic_mock_analysis_rejected(
    mutation_name: str,
    analysis_override: dict[str, Any],
    analyze_at: int,
    expected_code: str,
) -> None:
    s, _, prop, _ = build_state_at_phase("PROPOSED")
    bad_analysis = make_analysis(prop, **analysis_override)
    rec = record_negative_transition(
        f"analysis_{mutation_name}",
        "approval_authority",
        s,
        make_event("ANALYZE", analyze_at, bad_analysis),
        expected_code,
    )
    assert rec["after"]["phase"] == "PROPOSED"
    assert rec["after"]["journal_len"] == 0
    if mutation_name in ("elevated_risk_authority", "empty_summary"):
        with pytest.raises(SafetyViolation, match="LLM_SCHEMA"):
            OfflineLLMAnalysisPort().analyze(bad_analysis)


@pytest.mark.parametrize(
    ("case_name", "prop_override", "expected_code"),
    [
        ("wrong_side_enum", {"side": "BUY"}, "SIDE_INVALID"),
        ("long_stop_above_last", {"side": "LONG", "stop": "100", "tp1": "105", "tp2": "110"}, "LEVEL_ORDER_INVALID"),
        ("long_tp1_below_last", {"side": "LONG", "stop": "95", "tp1": "100", "tp2": "110"}, "LEVEL_ORDER_INVALID"),
        ("long_tp2_below_tp1", {"side": "LONG", "stop": "95", "tp1": "105", "tp2": "105"}, "LEVEL_ORDER_INVALID"),
        ("short_stop_below_last", {"side": "SHORT", "stop": "100", "tp1": "95", "tp2": "90"}, "LEVEL_ORDER_INVALID"),
        ("short_tp1_above_last", {"side": "SHORT", "stop": "105", "tp1": "100", "tp2": "90"}, "LEVEL_ORDER_INVALID"),
        ("short_tp2_above_tp1", {"side": "SHORT", "stop": "105", "tp1": "95", "tp2": "95"}, "LEVEL_ORDER_INVALID"),
        ("no_action_with_positive_qty", {"side": "NO_ACTION", "quantity": "0.01"}, "QUANTITY_INVALID"),
    ],
)
def test_proposal_side_and_level_ordering_invariants(
    case_name: str, prop_override: dict[str, Any], expected_code: str
) -> None:
    s, _b0, prop, _ = build_state_at_phase("BAR_LOADED")
    bad_prop = {**prop, **prop_override}
    record_negative_transition(
        f"proposal_{case_name}",
        "approval_authority",
        s,
        make_event("PROPOSE", 60000, bad_prop),
        expected_code,
    )


@pytest.mark.parametrize(
    ("case_name", "bar_override", "event_at", "expected_code"),
    [
        ("unaligned_open_time", {"open_time": 60001, "close_time": 120000, "available_at": 120000}, 120000, "BAR_PIT_INVALID"),
        ("incomplete_minute_close", {"open_time": 60000, "close_time": 119998, "available_at": 119998}, 119999, "BAR_PIT_INVALID"),
        ("available_before_close", {"open_time": 60000, "close_time": 119999, "available_at": 119998}, 119999, "BAR_PIT_INVALID"),
        ("future_available_at", {"open_time": 60000, "close_time": 119999, "available_at": 120005}, 119999, "BAR_PIT_INVALID"),
        ("non_dense_bar_gap", {"open_time": 120000, "close_time": 179999, "available_at": 179999}, 179999, "BAR_NOT_DENSE_OR_MUTATED"),
        ("same_minute_duplicate_bar", {"open_time": 0, "close_time": 59999, "available_at": 59999}, 59999, "BAR_NOT_DENSE_OR_MUTATED"),
    ],
)
def test_incomplete_future_and_non_dense_bars_rejected(
    case_name: str, bar_override: dict[str, Any], event_at: int, expected_code: str
) -> None:
    s, _, _, _ = build_state_at_phase("BAR_LOADED")
    bad_bar = {**make_bar(60000), **bar_override}
    record_negative_transition(
        f"bar_{case_name}",
        "causality",
        s,
        make_event("BAR", event_at, bad_bar, f"BAR-{case_name}"),
        expected_code,
    )


def test_stale_bar_rejected_across_action_events() -> None:
    s_approved, _, _, _ = build_state_at_phase("APPROVED")
    # Bar 0 closed at 59999; at 120000 (59999 + 60001) without a new BAR, bar is stale
    record_negative_transition(
        "place_on_stale_bar",
        "causality",
        s_approved,
        make_event("PLACE", 120000),
        "BAR_STALE",
    )


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_mark_vs_last_strict_separation_in_triggers_fills_and_funding(side: str) -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side=side, quantity="0.02")
    # Extreme mark_close excursion that would breach stop/TP1 if Mark were confused with Last
    # Keep mark_close within 1x mark_equity guard while crossing stop (95/105) and tp1 (105/95)
    mark_crossing_stop = "90" if side == "LONG" else "110"
    b_mark_stop = make_bar(
        120000,
        last_open="100",
        last_high="101",
        last_low="99",
        last_close="100",
        mark_close=mark_crossing_stop,
    )
    s = transition(s, make_event("BAR", 179999, b_mark_stop, "BAR-MARK-STOP"))
    assert s["required_exit"] is None
    record_negative_transition(
        f"mark_only_stop_rejected_{side}",
        "causality",
        s,
        make_event("STOP", 179999, {"fill_id": "false-stop"}),
        "STOP_NOT_BREACHED",
    )
    # Funding at 180000 must use mark_close (90 or 110), NOT last_close (100)
    s = transition(
        s,
        make_event(
            "FUNDING",
            180000,
            {"settlement_id": "fund-mark", "settlement_at": 180000, "rate_fraction": "0.001"},
        ),
    )
    expected_funding = (
        Decimal(-1) * Decimal("0.02") * Decimal(mark_crossing_stop) * Decimal("0.001")
        if side == "LONG"
        else Decimal(1) * Decimal("0.02") * Decimal(mark_crossing_stop) * Decimal("0.001")
    )
    assert Decimal(s["journal"][-1]["cash_delta"]) == expected_funding


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_same_minute_stop_and_tp1_or_tp2_precedence(side: str) -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side=side, quantity="0.02")
    # Bar breaches BOTH stop (95/105) and TP1+tick (105.1/94.9) in the same minute
    both_bar = make_bar(
        120000,
        last_open="100",
        last_high="112",
        last_low="88",
        last_close="100",
        mark_close="100",
    )
    s_collision = transition(s, make_event("BAR", 179999, both_bar, "BAR-COLLISION"))
    assert s_collision["required_exit"] is not None
    assert s_collision["required_exit"]["kind"] == "STOP"
    record_negative_transition(
        f"tp1_blocked_by_required_stop_{side}",
        "causality",
        s_collision,
        make_event("TP1", 179999, {"fill_id": "tp1-blocked"}),
        "REQUIRED_EXIT_UNHANDLED",
    )
    # Even if required_exit is cleared synthetically, TP1 internal check enforces STOP_PRECEDES_TP1
    s_forced = {**s_collision, "required_exit": None}
    record_negative_transition(
        f"tp1_internal_stop_precedence_{side}",
        "causality",
        s_forced,
        make_event("TP1", 179999, {"fill_id": "tp1-forced"}),
        "STOP_PRECEDES_TP1",
    )


@pytest.mark.parametrize("horizon_hours", [12, 18, 24])
def test_horizon_time_cap_early_exact_and_missed_bar_causality(horizon_hours: int) -> None:
    b0 = make_bar(0)
    prop = make_proposal(digest(b0), horizon_hours=horizon_hours)
    tok = make_token(prop)
    s = initial_state([tok])
    s = transition(s, make_event("BAR", 59999, b0))
    s = transition(s, make_event("PROPOSE", 60000, prop))
    s = transition(s, make_event("ANALYZE", 60001, make_analysis(prop)))
    s = transition(s, make_event("APPROVE", 60002, {"token_id": tok["token_id"]}))
    s = transition(s, make_event("PLACE", 60003))
    s = transition(s, make_event("FILL_ENTRY", 60004, {"fill_id": "entry-h"}))
    s = transition(s, make_event("BAR", 119999, make_bar(60000)))
    s = transition(
        s,
        make_event(
            "ACK",
            120004,
            {"ack_id": "ack-entry-h", "order_id": s["order_id"], "fill_id": "entry-h"},
        ),
    )
    deadline = 60004 + horizon_hours * 3600000
    # Advance bars up to the minute immediately preceding deadline
    while s["last_bar"]["close_time"] + 60000 < deadline:
        nxt_open = s["last_bar"]["open_time"] + 60000
        s = transition(s, make_event("BAR", nxt_open + 59999, make_bar(nxt_open)))
    assert s["required_exit"] is None
    record_negative_transition(
        f"time_cap_early_{horizon_hours}h",
        "causality",
        s,
        make_event("TIME_CAP", s["last_at"], {"fill_id": "early-cap"}),
        "TIME_CAP_EARLY",
    )
    # First completed bar with close_time >= deadline triggers mandatory TIME_CAP
    cap_open = s["last_bar"]["open_time"] + 60000
    s_cap = transition(s, make_event("BAR", cap_open + 59999, make_bar(cap_open)))
    assert s_cap["required_exit"] is not None
    assert s_cap["required_exit"]["kind"] == "TIME_CAP"
    s_done = transition(s_cap, make_event("TIME_CAP", s_cap["last_at"], {"fill_id": "exact-cap"}))
    assert s_done["phase"] == "EXIT_WAIT_ACK"


@pytest.mark.parametrize("entry_ack_first", [True, False])
def test_stop_before_entry_ack_all_ack_arrival_orders_conserve(
    entry_ack_first: bool,
) -> None:
    s, _, _, _ = build_state_at_phase("WAIT_ENTRY_ACK", side="LONG", quantity="0.02")
    # Bar 1 breaches stop (95) before entry-1 has been ACKed!
    b1_stop = make_bar(60000, last_open="95", last_high="96", last_low="94", last_close="95")
    s = transition(s, make_event("BAR", 119999, b1_stop, "BAR-STOP-BEFORE-ENTRY-ACK"))
    assert s["required_exit"]["kind"] == "STOP"
    s = transition(s, make_event("STOP", 119999, {"fill_id": "stop-early"}, "STOP-EARLY"))
    assert s["phase"] == "EXIT_WAIT_ACK"
    assert s["entry_acknowledged"] is False
    assert Decimal(s["remaining_qty"]) == Decimal(0)
    assert "stop-early" in s["pending_cash"]

    # Advance to Bar 2 (close_time = 179999 >= 119999 + 60000) so both ACKs are causally eligible
    s = transition(
        s,
        make_event(
            "BAR",
            179999,
            make_bar(120000, last_open="95", last_high="96", last_low="94", last_close="95"),
        ),
    )
    order_id = s["order_id"]
    ack_pairs = (
        [("ack-e", "entry-1"), ("ack-s", "stop-early")]
        if entry_ack_first
        else [("ack-s", "stop-early"), ("ack-e", "entry-1")]
    )
    for idx, (ack_id, fill_id) in enumerate(ack_pairs):
        s = transition(
            s,
            make_event(
                "ACK",
                180000 + idx,
                {"ack_id": ack_id, "order_id": order_id, "fill_id": fill_id},
            ),
        )
        if idx == 0:
            assert s["phase"] == "EXIT_WAIT_ACK"
    assert s["phase"] == "CLOSED"
    assert s["entry_acknowledged"] is True
    assert not s["pending_cash"]
    assert Decimal(s["reserved_notional"]) == Decimal(0)


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_stop_update_causality_and_no_retroactive_same_bar_stop(side: str) -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side=side, quantity="0.04")
    fav = "106" if side == "LONG" else "94"
    b_tp1 = make_bar(
        120000,
        last_open=fav,
        last_high=str(int(fav) + 1),
        last_low=str(int(fav) - 1),
        last_close=fav,
        mark_close=fav,
    )
    s = transition(s, make_event("BAR", 179999, b_tp1))
    s = transition(s, make_event("TP1", 179999, {"fill_id": "tp1-fill"}))
    # Cannot update stop while in WAIT_TP1_ACK
    record_negative_transition(
        f"update_stop_before_tp1_ack_{side}",
        "causality",
        s,
        make_event("UPDATE_STOP", 180000),
        "PHASE_INVALID",
    )
    b_ack = make_bar(
        180000,
        last_open="100",
        last_high="101",
        last_low="99",
        last_close="100",
        mark_close="100",
    )
    s = transition(s, make_event("BAR", 239999, b_ack))
    s = transition(
        s,
        make_event(
            "ACK",
            239999,
            {"ack_id": "ack-tp1", "order_id": s["order_id"], "fill_id": "tp1-fill"},
        ),
    )
    # Cannot update stop at the exact same timestamp as tp1_ack_at
    record_negative_transition(
        f"update_stop_same_clock_as_ack_{side}",
        "causality",
        s,
        make_event("UPDATE_STOP", 239999),
        "STOP_UPDATE_BEFORE_ACK_OR_SAME_BAR",
    )
    # Cannot update stop at close_time + 2 (240001)
    record_negative_transition(
        f"update_stop_past_boundary_{side}",
        "causality",
        s,
        make_event("UPDATE_STOP", 240001),
        "STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY",
    )
    # Valid update at close_time + 1 (240000)
    s = transition(s, make_event("UPDATE_STOP", 240000))
    # Retroactive stop on the same source bar is rejected (C3 invariant)
    record_negative_transition(
        f"retroactive_stop_same_bar_{side}",
        "causality",
        s,
        make_event("STOP", 240000, {"fill_id": "retro-stop"}),
        "STOP_UPDATE_NOT_YET_EFFECTIVE",
    )
    # Next completed bar at 100 triggers the newly tightened BE stop
    b_next = make_bar(
        240000,
        last_open="100",
        last_high="101",
        last_low="99",
        last_close="100",
        mark_close="100",
    )
    s = transition(s, make_event("BAR", 299999, b_next))
    assert s["required_exit"]["kind"] == "STOP"
    s = transition(s, make_event("STOP", 299999, {"fill_id": "valid-be-stop"}))
    assert Decimal(s["remaining_qty"]) == Decimal(0)


def test_late_outbox_receipt_never_suppresses_due_stop_or_advances_clock() -> None:
    s, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.02")
    outbox_key = s["outbox"][0]["key"]
    b_stop = make_bar(120000, last_open="95", last_high="96", last_low="94", last_close="95")
    s = transition(s, make_event("BAR", 179999, b_stop))
    assert s["required_exit"]["kind"] == "STOP"
    # Outbox receipt cannot be processed while STOP is pending
    record_negative_transition(
        "outbox_receipt_blocked_by_due_stop",
        "causality",
        s,
        make_event("OUTBOX_RECEIPT", 99999999, {"message_id": outbox_key}),
        "REQUIRED_EXIT_UNHANDLED",
    )
    s = transition(s, make_event("STOP", 179999, {"fill_id": "stop-due"}))
    # Late outbox receipt after STOP does not advance last_at
    s = transition(s, make_event("OUTBOX_RECEIPT", 99999999, {"message_id": outbox_key}))
    assert s["last_at"] == 179999
    assert s["last_clock"] == 179999
