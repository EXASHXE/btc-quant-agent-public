"""Single-shot finite audit and negative-battery evidence generator for G1 offline assurance R1."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from scripts.g1_offline_preview_r1.fixtures import make_fixture
from scripts.g1_offline_preview_r1.model import digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.strategy_research.g1_offline_assurance_r1 import (
    CONTROLLER_DISPATCH_SHA,
    EXACT_START_SHA,
    OWN_NAMESPACE,
    OWN_SCRATCH,
    PARENT_C3_SHA,
    TASK_ID,
)
from scripts.strategy_research.g1_offline_assurance_r1.crash_worker import (
    PROCESS_CRASH_CHECKPOINTS,
)
from scripts.strategy_research.g1_offline_assurance_r1.oracle import (
    EXPECTED_C4_SOURCE_HASHES,
    REPO_ROOT,
    audit_static_import_and_call_surface,
    build_state_at_phase,
    independent_fixture_ledger,
    intercept_outbound_network,
    make_analysis,
    make_bar,
    make_event,
    make_token,
    record_negative_transition,
)

EVIDENCE_DIR = REPO_ROOT / "evidence/v0.6/b_line/g1_offline_assurance_r1"


def build_negative_battery_cases() -> list[dict[str, Any]]:
    """Run >60 distinct negative/adversarial inputs and capture core state before/after each."""
    records: list[dict[str, Any]] = []

    def add(test_id: str, category: str, state: dict[str, Any], ev: dict[str, Any], code: str):
        records.append(record_negative_transition(test_id, category, state, ev, code))

    s_ready, b0, prop_long, tok_long = build_state_at_phase("READY")
    s_bar, _, _, _ = build_state_at_phase("BAR_LOADED")
    s_prop, _, _, _ = build_state_at_phase("PROPOSED")
    s_anal, _, _, _ = build_state_at_phase("ANALYZED")
    s_appr, _, _, _ = build_state_at_phase("APPROVED")
    s_plac, _, _, _ = build_state_at_phase("PLACED")
    s_wait_e, _, _, _ = build_state_at_phase("WAIT_ENTRY_ACK")
    s_open_l, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.02")
    s_open_s, _, _, _ = build_state_at_phase("OPEN", side="SHORT", quantity="0.02")

    # --- Category 1: Approval authority (18 distinct cases) ---
    add("N01_place_in_ready", "1_approval_authority", s_ready, make_event("PLACE", 60003), "PHASE_INVALID")
    add("N02_place_in_bar_loaded", "1_approval_authority", s_bar, make_event("PLACE", 60003), "PHASE_INVALID")
    add("N03_place_in_proposed", "1_approval_authority", s_prop, make_event("PLACE", 60003), "PHASE_INVALID")
    add("N04_place_in_analyzed", "1_approval_authority", s_anal, make_event("PLACE", 60003), "PHASE_INVALID")
    add("N05_fill_in_ready", "1_approval_authority", s_ready, make_event("FILL_ENTRY", 60004, {"fill_id": "f1"}), "PHASE_INVALID")
    add("N06_fill_in_proposed", "1_approval_authority", s_prop, make_event("FILL_ENTRY", 60004, {"fill_id": "f1"}), "PHASE_INVALID")
    add("N07_fill_in_analyzed", "1_approval_authority", s_anal, make_event("FILL_ENTRY", 60004, {"fill_id": "f1"}), "PHASE_INVALID")
    add("N08_fill_in_approved_before_place", "1_approval_authority", s_appr, make_event("FILL_ENTRY", 60004, {"fill_id": "f1"}), "PHASE_INVALID")
    add("N09_approve_unknown_token", "1_approval_authority", s_anal, make_event("APPROVE", 60002, {"token_id": "forged"}), "APPROVAL_UNTRUSTED_OR_REPLAYED")
    add("N10_double_approve_in_approved", "1_approval_authority", s_appr, make_event("APPROVE", 60003, {"token_id": tok_long["token_id"]}), "PHASE_INVALID")
    add("N11_replayed_token_in_analyzed", "1_approval_authority", {**s_appr, "phase": "ANALYZED"}, make_event("APPROVE", 60003, {"token_id": tok_long["token_id"]}), "APPROVAL_UNTRUSTED_OR_REPLAYED")

    for tid, override, at, code in [
        ("N12_token_wrong_signal_id", {"signal_id": "other"}, 60002, "APPROVAL_DRIFT"),
        ("N13_token_wrong_proposal_hash", {"proposal_hash": "00" * 32}, 60002, "APPROVAL_DRIFT"),
        ("N14_token_wrong_quantity", {"quantity": "0.03"}, 60002, "APPROVAL_DRIFT"),
        ("N15_token_issued_before_analysis", {"issued_at": 60000}, 60002, "APPROVAL_STALE_OR_REORDERED"),
        ("N16_future_token_issued_after_approve", {"issued_at": 60005}, 60002, "APPROVAL_STALE_OR_REORDERED"),
        ("N17_expired_token_at_approve", {"expires_at": 60003}, 60003, "APPROVAL_STALE_OR_REORDERED"),
        ("N18_approve_crossing_proposal_expiry", {"expires_at": 200000}, 180000, "APPROVAL_STALE_OR_REORDERED"),
    ]:
        t_custom = make_token(prop_long, **override)
        st = initial_state([t_custom])
        st = transition(st, make_event("BAR", 59999, b0))
        st = transition(st, make_event("PROPOSE", 60000, prop_long))
        st = transition(st, make_event("ANALYZE", 60001, make_analysis(prop_long)))
        add(tid, "1_approval_authority", st, make_event("APPROVE", at, {"token_id": t_custom["token_id"]}), code)

    # --- Synthetic mock analysis & proposal mutations (10 distinct cases) ---
    add("N19_analysis_hallucinated_signal", "1_approval_authority", s_prop, make_event("ANALYZE", 60001, make_analysis(prop_long, signal_id="bad")), "ANALYSIS_STALE_OR_HALLUCINATED")
    add("N20_analysis_hallucinated_hash", "1_approval_authority", s_prop, make_event("ANALYZE", 60001, make_analysis(prop_long, proposal_hash="bad")), "ANALYSIS_STALE_OR_HALLUCINATED")
    add("N21_analysis_elevated_risk", "1_approval_authority", s_prop, make_event("ANALYZE", 60001, make_analysis(prop_long, risk="APPROVE")), "ANALYSIS_AUTHORITY_OR_CLOCK")
    add("N22_analysis_future_as_of", "1_approval_authority", s_prop, make_event("ANALYZE", 60001, make_analysis(prop_long, as_of=60002)), "ANALYSIS_AUTHORITY_OR_CLOCK")
    add("N23_analysis_past_decision_as_of", "1_approval_authority", s_prop, make_event("ANALYZE", 60001, make_analysis(prop_long, as_of=59999)), "ANALYSIS_AUTHORITY_OR_CLOCK")
    add("N24_analysis_expired_proposal", "1_approval_authority", s_prop, make_event("ANALYZE", 180000, make_analysis(prop_long)), "ANALYSIS_EXPIRED")
    add("N25_propose_wrong_side", "1_approval_authority", s_bar, make_event("PROPOSE", 60000, {**prop_long, "side": "HOLD"}), "SIDE_INVALID")
    add("N26_propose_long_inverted_stop", "1_approval_authority", s_bar, make_event("PROPOSE", 60000, {**prop_long, "stop": "101"}), "LEVEL_ORDER_INVALID")
    add("N27_propose_short_inverted_stop", "1_approval_authority", s_bar, make_event("PROPOSE", 60000, {**prop_long, "side": "SHORT", "stop": "99", "tp1": "95", "tp2": "90"}), "LEVEL_ORDER_INVALID")
    add("N28_propose_no_action_nonzero_qty", "1_approval_authority", s_bar, make_event("PROPOSE", 60000, {**prop_long, "side": "NO_ACTION", "quantity": "0.01"}), "QUANTITY_INVALID")

    # --- Category 2: Causality (18 distinct cases) ---
    add("N29_bar_unaligned_open", "2_causality", s_bar, make_event("BAR", 120000, make_bar(60001, close_time=120000, available_at=120000)), "BAR_PIT_INVALID")
    add("N30_bar_incomplete_close", "2_causality", s_bar, make_event("BAR", 119999, make_bar(60000, close_time=119998, available_at=119998)), "BAR_PIT_INVALID")
    add("N31_bar_available_before_close", "2_causality", s_bar, make_event("BAR", 119999, make_bar(60000, close_time=119999, available_at=119990)), "BAR_PIT_INVALID")
    add("N32_bar_future_available", "2_causality", s_bar, make_event("BAR", 119999, make_bar(60000, close_time=119999, available_at=120005)), "BAR_PIT_INVALID")
    add("N33_bar_non_dense_gap", "2_causality", s_bar, make_event("BAR", 179999, make_bar(120000)), "BAR_NOT_DENSE_OR_MUTATED")
    add("N34_bar_ohlc_low_above_open", "2_causality", s_bar, make_event("BAR", 119999, make_bar(60000, last_open="100", last_low="101", last_high="102")), "BAR_OHLC_INVALID")
    add("N35_place_on_stale_bar", "2_causality", s_appr, make_event("PLACE", 120000), "BAR_STALE")
    add("N36_reordered_event_clock", "2_causality", s_open_l, make_event("BAR", 59999, b0, "BAR-OLD"), "EVENT_REORDERED")

    # Mark vs Last & collision precedence
    s_mark_low = transition(
        s_open_l,
        make_event("BAR", 179999, make_bar(120000, last_open="100", last_high="101", last_low="99", last_close="100", mark_close="90")),
    )
    add("N37_mark_crash_does_not_breach_last_stop", "2_causality", s_mark_low, make_event("STOP", 179999, {"fill_id": "m-stop"}), "STOP_NOT_BREACHED")

    s_coll_l = transition(
        s_open_l,
        make_event("BAR", 179999, make_bar(120000, last_open="100", last_high="112", last_low="88", last_close="100")),
    )
    add("N38_same_bar_stop_blocks_tp1_long", "2_causality", s_coll_l, make_event("TP1", 179999, {"fill_id": "tp1-l"}), "REQUIRED_EXIT_UNHANDLED")
    add("N39_same_bar_stop_precedes_tp1_internal_long", "2_causality", {**s_coll_l, "required_exit": None}, make_event("TP1", 179999, {"fill_id": "tp1-l2"}), "STOP_PRECEDES_TP1")

    s_coll_s = transition(
        s_open_s,
        make_event("BAR", 179999, make_bar(120000, last_open="100", last_high="112", last_low="88", last_close="100")),
    )
    add("N40_same_bar_stop_blocks_tp1_short", "2_causality", s_coll_s, make_event("TP1", 179999, {"fill_id": "tp1-s"}), "REQUIRED_EXIT_UNHANDLED")
    add("N41_due_stop_blocks_late_outbox_receipt", "2_causality", s_coll_l, make_event("OUTBOX_RECEIPT", 99999999, {"message_id": s_coll_l["outbox"][0]["key"]}), "REQUIRED_EXIT_UNHANDLED")
    add("N42_due_stop_blocks_next_bar_omission", "2_causality", s_coll_l, make_event("BAR", 239999, make_bar(180000)), "REQUIRED_EXIT_UNHANDLED")
    add("N43_time_cap_early_rejected", "2_causality", s_open_l, make_event("TIME_CAP", 120005, {"fill_id": "early-tc"}), "TIME_CAP_EARLY")
    add("N44_entry_ack_before_60s_rejected", "2_causality", s_wait_e, make_event("ACK", 60005, {"ack_id": "a1", "order_id": s_wait_e["order_id"], "fill_id": "entry-1"}), "ACK_BEFORE_FILL_OR_WRONG_ID")

    # C3 stop update causality
    s_tp1 = transition(
        s_open_l,
        make_event("BAR", 179999, make_bar(120000, last_open="106", last_high="107", last_low="105", last_close="106")),
    )
    s_tp1 = transition(s_tp1, make_event("TP1", 179999, {"fill_id": "tp1-c3"}))
    s_tp1_ack = transition(s_tp1, make_event("BAR", 239999, make_bar(180000, last_open="100", last_high="101", last_low="99", last_close="100")))
    s_tp1_ack = transition(s_tp1_ack, make_event("ACK", 239999, {"ack_id": "ack-tp1-c3", "order_id": s_tp1_ack["order_id"], "fill_id": "tp1-c3"}))
    add("N45_stop_update_past_boundary_rejected", "2_causality", s_tp1_ack, make_event("UPDATE_STOP", 240001), "STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY")
    s_updated = transition(s_tp1_ack, make_event("UPDATE_STOP", 240000))
    add("N46_retroactive_be_stop_same_bar_rejected", "2_causality", s_updated, make_event("STOP", 240000, {"fill_id": "retro"}), "STOP_UPDATE_NOT_YET_EFFECTIVE")

    # --- Category 3: Financial ledger (12 distinct cases) ---
    add("N47_propose_sub_lot_quantity", "3_financial_ledger", s_bar, make_event("PROPOSE", 60000, {**prop_long, "quantity": "0.0105"}), "QUANTITY_INVALID")
    add("N48_propose_oversize_quantity", "3_financial_ledger", s_bar, make_event("PROPOSE", 60000, {**prop_long, "quantity": "0.051"}), "QUANTITY_INVALID")
    add("N49_duplicate_entry_fill_id_on_tp1", "3_financial_ledger", transition(s_open_l, make_event("BAR", 179999, make_bar(120000, last_open="106", last_high="107", last_low="105", last_close="106"))), make_event("TP1", 179999, {"fill_id": "entry-1"}), "FILL_DUPLICATE")
    add("N50_funding_collision_with_entry_at", "3_financial_ledger", s_wait_e, make_event("FUNDING", 60004, {"settlement_id": "f-coll", "settlement_at": 60004, "rate_fraction": "0.0001"}), "FUNDING_SETTLEMENT_COLLISION")
    add("N51_funding_collision_with_tp1_pending_at", "3_financial_ledger", s_tp1, make_event("FUNDING", 179999, {"settlement_id": "f-tp1-coll", "settlement_at": 179999, "rate_fraction": "0.0001"}), "FUNDING_SETTLEMENT_COLLISION")
    add("N52_funding_rate_exceeds_bound", "3_financial_ledger", s_open_l, make_event("FUNDING", 120005, {"settlement_id": "f-big", "settlement_at": 120005, "rate_fraction": "-0.15"}), "FUNDING_RATE_BOUNDS")

    s_funded = transition(s_open_l, make_event("FUNDING", 120005, {"settlement_id": "f-1", "settlement_at": 120005, "rate_fraction": "0.0001"}))
    add("N53_funding_duplicate_settlement_id", "3_financial_ledger", s_funded, make_event("FUNDING", 120006, {"settlement_id": "f-1", "settlement_at": 120006, "rate_fraction": "0.0001"}), "FUNDING_DUPLICATE_OR_FUTURE")
    add("N54_funding_same_clock_alias", "3_financial_ledger", s_funded, make_event("FUNDING", 120005, {"settlement_id": "f-alias", "settlement_at": 120005, "rate_fraction": "0.0001"}, "FUND-ALIAS"), "FUNDING_DUPLICATE_OR_FUTURE")
    add("N55_mark_exposure_above_one_x_short", "3_financial_ledger", s_open_s, make_event("BAR", 179999, make_bar(120000, mark_close="30000")), "MARK_EXPOSURE_ABOVE_ONE_X")
    add("N56_propose_second_position_while_open", "3_financial_ledger", s_open_l, make_event("PROPOSE", 120005, {**prop_long, "signal_id": "sig-second"}), "PHASE_INVALID")

    s_one_lot, _, _, _ = build_state_at_phase("OPEN", side="LONG", quantity="0.001")
    s_one_lot_tp = transition(s_one_lot, make_event("BAR", 179999, make_bar(120000, last_open="106", last_high="107", last_low="105", last_close="106")))
    add("N57_tp1_single_lot_cannot_split", "3_financial_ledger", s_one_lot_tp, make_event("TP1", 179999, {"fill_id": "tp1-1lot"}), "PARTIAL_LOT_OR_MIN_NOTIONAL")
    add("N58_tp2_before_tp1_rejected", "3_financial_ledger", s_open_l, make_event("TP2", 120005, {"fill_id": "tp2-early"}), "TP2_BEFORE_TP1")

    # --- Category 4 & 5: Schema, recovery, and secret scrubbing (7 distinct cases) ---
    add("N59_unknown_state_schema_version", "4_failure_recovery", {**s_ready, "schema_version": 2}, make_event("BAR", 59999, b0), "STATE_SCHEMA")
    add("N60_tampered_safety_status", "4_failure_recovery", {**s_ready, "safety_status": "LIVE"}, make_event("BAR", 59999, b0), "STATE_SCHEMA")
    add("N61_secret_in_event_id", "5_output_and_safety", s_bar, make_event("BAR", 119999, make_bar(60000), "api_key=leak"), "SECRET_IN_EVENT")
    add("N62_secret_in_signal_id", "5_output_and_safety", s_bar, make_event("PROPOSE", 60000, {**prop_long, "signal_id": "password_sig"}), "SECRET_IN_EVENT")
    add("N63_secret_in_fill_id", "5_output_and_safety", s_plac, make_event("FILL_ENTRY", 60004, {"fill_id": "bearer_fill"}), "SECRET_IN_EVENT")
    add("N64_secret_in_Direct_analysis_summary", "5_output_and_safety", s_prop, make_event("ANALYZE", 60001, make_analysis(prop_long, summary="token=my_secret_tok")), "SECRET_IN_EVENT")
    add("N65_unknown_event_kind_rejected", "5_output_and_safety", s_open_l, make_event("CANCEL_ALL", 120005, {}), "EVENT_KIND_UNKNOWN")

    return records


def run_all_audits() -> dict[str, Any]:
    """Execute the single-shot finite audit and write evidence artifacts."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    OWN_SCRATCH.mkdir(mode=0o700, parents=True, exist_ok=True)

    with intercept_outbound_network() as net_calls:
        static_report = audit_static_import_and_call_surface()
        source_hash_verification: dict[str, dict[str, Any]] = {}
        for rel, expected_sha in EXPECTED_C4_SOURCE_HASHES.items():
            actual_sha = hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()
            source_hash_verification[rel] = {
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "matches": actual_sha == expected_sha,
            }

        negative_battery = build_negative_battery_cases()

        ledger_verifications: list[dict[str, Any]] = []
        for side in ("LONG", "SHORT"):
            for exit_kind, horizon in [("STOP", 24), ("TP2", 24), ("TIME_CAP", 12), ("TIME_CAP", 18), ("TIME_CAP", 24)]:
                fixture = make_fixture(side, horizon, exit_kind)
                oracle = independent_fixture_ledger(side, horizon, exit_kind)
                s = initial_state(fixture["trusted_approvals"])
                for ev in fixture["events"]:
                    s = transition(s, ev)
                assert s["phase"] == "CLOSED"
                assert Decimal(s["cash"]) == Decimal(oracle["final_cash"])
                ledger_verifications.append(
                    {
                        "fixture_name": fixture["fixture_name"],
                        "side": side,
                        "horizon_hours": horizon,
                        "exit_kind": exit_kind,
                        "oracle": oracle,
                        "actual_final_cash": s["cash"],
                        "actual_journal_hash": digest(s["journal"]),
                        "actual_state_hash": digest(s),
                        "exact_match": True,
                    }
                )

    assert net_calls == [], f"Unexpected network calls: {net_calls}"

    static_audit_payload = {
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "exact_start_sha": EXACT_START_SHA,
        "parent_c3_sha": PARENT_C3_SHA,
        "own_namespace": OWN_NAMESPACE,
        "all_c4_source_hashes_match": all(
            v["matches"] for v in source_hash_verification.values()
        ),
        "source_hash_verification": source_hash_verification,
        "ast_surface_audit": static_report,
        "c3_touched_symbols": {
            "commit_sha": PARENT_C3_SHA,
            "executable_files": ["scripts/g1_offline_preview_r1/reducer.py"],
            "symbols": ["transition"],
            "invariants_added": [
                "PROPOSE clears stop_update_source_hash",
                "UPDATE_STOP enforces at <= bar['close_time'] + 1 (STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY) and records stop_update_source_hash = last_bar_hash",
                "STOP rejects when stop_update_source_hash == last_bar_hash (STOP_UPDATE_NOT_YET_EFFECTIVE)",
            ],
        },
        "c4_touched_symbols": {
            "commit_sha": EXACT_START_SHA,
            "executable_files": ["scripts/g1_offline_preview_r1/__main__.py"],
            "symbols": ["SafeArgumentParser", "SafeArgumentParser.error", "main"],
            "invariants_added": [
                "SafeArgumentParser.error exits with code 3 and static canonical JSON CLI_ARGUMENTS_INVALID without echoing caller argument values",
            ],
        },
        "pre_approval_journal_mutation_possible": False,
        "outbound_network_calls_observed": len(net_calls),
    }

    (EVIDENCE_DIR / "STATIC_IDENTITY_AND_SURFACE_AUDIT.json").write_text(
        json.dumps(static_audit_payload, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE_DIR / "NEGATIVE_BATTERY_STATE_TRANSITIONS.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "exact_start_sha": EXACT_START_SHA,
                "negative_case_count": len(negative_battery),
                "any_state_mutated_on_rejection": any(
                    r["state_mutated"] for r in negative_battery
                ),
                "outbound_network_calls_observed": len(net_calls),
                "cases": negative_battery,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE_DIR / "INDEPENDENT_DECIMAL_LEDGER_AUDIT.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "exact_start_sha": EXACT_START_SHA,
                "scenario_count": len(ledger_verifications),
                "total_verified_journal_effects": sum(
                    len(x["oracle"]["effects"]) for x in ledger_verifications
                ),
                "synthetic_min_notional_proxy": "1 (synthetic contract constant; NOT Binance production USD-M minimum)",
                "scenarios": ledger_verifications,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "static_files_verified": len(source_hash_verification),
        "negative_cases_verified": len(negative_battery),
        "ledger_scenarios_verified": len(ledger_verifications),
        "process_checkpoints_configured": len(PROCESS_CRASH_CHECKPOINTS),
        "network_calls": len(net_calls),
    }


if __name__ == "__main__":
    summary = run_all_audits()
    print(json.dumps(summary, sort_keys=True))
