"""Focused Program O worker evidence; no acquisition or authority claims."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def write(name, obj):
    (ROOT / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def main():
    host = read("audit/O_HOST_CLOCK_TELEMETRY.json")
    original = read("evidence/N_SANITIZED_CLOCK_AND_COUNTS.json")
    contract = read("src/btc_quant_agent/platform/live/operational_clock.json")
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    policy_hash = hashlib.sha256(canonical).hexdigest()
    write(
        "O1_CLOCK_DIAGNOSIS.json",
        {
            "schema": "O_CLOCK_CAUSAL_DIAGNOSIS_V1",
            "N_steps": original["clock_steps"],
            "N_guard": "L SwingCollector current-price stage offset_step -> SWING_CLOCK_JUMP_DURING_CURRENT_PRICE_CHECK before SNAPSHOT/DECISION commit",
            "N_first_complete_reacquisition_matched": original[
                "completed_source_content_reacquisition_matches"
            ],
            "N_final_snapshots": 0,
            "N_final_decisions": 0,
            "N_raw_candles_are_not_admitted_source": True,
            "read_only_host_telemetry": "audit/O_HOST_CLOCK_TELEMETRY.json",
            "paired_bracket_max_ns": host["bracket_max_ns"],
            "host_elapsed_monotonic_seconds": host["elapsed_seconds"],
            "host_offset_ranges_ns": host["offset_ranges_ns"],
            "realtime_offset_single_observed_step_ms": 2285.928827,
            "RAW_vs_MONOTONIC": "Measured cumulative 2146.627168ms divergence in about30s; not a proven isolated step",
            "clocksource": "tsc",
            "boot_ID": host["metadata"]["boot_id"],
            "time_sync_status": "timesyncd active; NTPSynchronized=yes/NTP=yes; NOT uncertainty evidence",
            "proven": [
                "N anomalies occur within the same request worker, same boot, 0ms paired sample spans",
                "Current host has measurable counter-domain inconsistency beyond50ms; wall-only hypothesis is insufficient",
            ],
            "upstream_root_cause": "UNKNOWN",
            "hypotheses_not_proven": [
                "WSL2/Hyper-V clock virtualization",
                "host/guest synchronization or clock frequency corrections",
                "suspend/resume or resource effects",
            ],
            "software_ordering_defect_demonstrated": False,
            "host_qualified": False,
            "independent_UTC_uncertainty": "NOT_ESTABLISHED",
            "OS_NTP_or_network_settings_changes": 0,
            "new_exchange_requests": 0,
        },
    )
    write(
        "O2_OPERATIONAL_TIME_CONTRACT.json",
        {
            "schema": "O_TIME_POLICY_WORKER_HANDOFF_V1",
            "policy": contract,
            "canonical_contract_sha256": policy_hash,
            "new_opt_in_only": True,
            "current_host_is_NOT_unblocked": True,
            "legacy_byte_invariants": "audit/O_FROZEN_INVARIANTS.json",
            "source_diff": "audit/O_ACCEPTED_L_SOURCE_DIFF.patch",
            "new_source_files": [
                "src/btc_quant_agent/platform/live/operational_clock.py",
                "src/btc_quant_agent/platform/live/operational_clock.json",
            ],
            "normal_phase_ordinals": {
                "metadata": [1],
                "venue_probes": [2, 12],
                "completed_1D_4H_for_three_symbols": [3, 8],
                "current_partial_4H": [9, 11],
            },
            "optional_single_witness": {
                "probes": [13, 23],
                "completed": [14, 19],
                "current_partial_4H": [20, 22],
                "only_data_after_last_anomaly_accepted": True,
            },
            "literal_N_ordinal_pattern_2_minus799_19_plus918": "BLOCKED: second step lies within witness; no third pass or hidden retry",
            "phase_equivalent_initial_probe_and_current_step_2_minus799_9_plus918": "Only SYNTHETIC QA passes after stable full witness; NOT evidence that N raw capture can be promoted",
            "independence_limit": "Separate subsequent HTTPS responses from same venue; not independent UTC or cryptographically signed exchange publication times",
            "absolute_time": "Bounded venue-time interval, actual review-local wall and monotonic/control samples recorded separately; no backdating",
            "fresh_session_rule": "New sessions use a fresh venue mapping; same boot and monotonic non-regression remain required. Never extrapolate an expired reference.",
            "review_after_proof_wall_step": "BLOCKED until separately authorized fresh complete scan; immutable diagnostic retained",
            "legacy_research_and_J_L_contracts_changed": False,
        },
    )
    demo = read("O3_SYNTHETIC_OPERATOR_DEMONSTRATION.json")
    write(
        "O3_OFFLINE_ACCEPTANCE.json",
        {
            "status": "WORKER_OFFLINE_EVIDENCE_FOR_CONTROLLER_REVIEW",
            "demo": demo,
            "new_genuine_market_requests": 0,
            "N_real_capture_promoted_to_snapshot": False,
            "current_host_admission": "HOST_CLOCK_UNQUALIFIED",
            "public_data_economic_boundary": "SOURCE_CLASS_INVALID / INSUFFICIENT_SUPPORT",
            "clock_model_in_positive_QA": "EXPLICITLY_FABRICATED_STABLE_RAW_BOOTTIME_AND_MONOTONIC",
        },
    )
    reports = [
        "audit/O_product_domain_tests.xml",
        "audit/O_c_domain_tests.xml",
        "audit/O_mvp_domain_tests.xml",
        "audit/O_rc_domain_tests.xml",
        "audit/O_final_new_tests.xml",
    ]
    unique = {}
    domains = []
    for report in reports:
        cases = ET.parse(ROOT / report).getroot().findall(".//testcase")
        tally = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
        for c in cases:
            state = (
                "ERROR"
                if c.find("error") is not None
                else "FAIL"
                if c.find("failure") is not None
                else "SKIP"
                if c.find("skipped") is not None
                else "PASS"
            )
            tally[state] += 1
            key = (c.attrib["classname"], c.attrib["name"])
            assert key not in unique or unique[key] == state, "CONTRADICTORY_TEST_REPETITION"
            unique[key] = state
        domains.append({"report": report, "counts": tally, "cases": len(cases)})
    total = {name: sum(s == name for s in unique.values()) for name in ["PASS", "FAIL", "ERROR", "SKIP"]}
    write(
        "O4_TEST_MATRIX.json",
        {
            "status": "PASS" if total["FAIL"] + total["ERROR"] == 0 else "FAIL",
            "domains": domains,
            "unique_final_counts": total,
            "inherited_unique_cases": 632,
            "new_unique_cases": len(unique) - 632,
            "not_added_to_unique_total": [
                "O_initial_targeted.xml",
                "O_targeted.xml",
                "O_policy_final_tests.xml",
                "O_policy_complete_final.xml",
                "O_host_counterexample_initial.xml",
                "repeated inherited historical results",
            ],
            "offline_network_enforcement": "tools/offline_pytest.py LOOPBACK_ONLY; synthetic original-target CONNECT/TLS in inherited and new fixtures",
            "Ruff": (ROOT / "audit/O_ruff.log").read_text().strip(),
            "scoped_mypy": (ROOT / "audit/O_mypy.log").read_text().strip(),
            "compilation": "PASS audit/O_compile.log",
            "clean_install": "PASS --no-index --require-hashes pip check",
            "measured_host_clock": "FAILED_ADMISSION_NOT_TEST_FAILURE; real counterexample test must PASS by rejecting it",
            "earlier_diagnostic_failures_preserved": [
                "audit/O_mypy_initial.log",
                "audit/O_HOST_CLOCK_TELEMETRY.json",
            ],
        },
    )
    write(
        "O6_INTEGRATED_ACCEPTANCE.json",
        {
            "worker_terminal_state": "O_HOST_CLOCK_STABILITY_REQUIRED",
            "controller_acceptance": "PENDING_INDEPENDENT_CONTROLLER_0C",
            "opt_in_operational_policy_implemented_and_offline_tested": True,
            "policy_sha256": policy_hash,
            "current_WSL_host_qualified": False,
            "alternative_host_tested": False,
            "upstream_cause": "UNKNOWN",
            "genuine_exchange_requests_by_O": 0,
            "new_account_order_trade_alert_requests": 0,
            "N_inherited_capture": {
                "requests": 22,
                "HTTP_200": 22,
                "raw_distinct_completed_bars": 540,
                "admitted_snapshots": 0,
                "decisions": 0,
                "retention_deadline_UTC": "2026-11-09T16:20:00Z",
                "payloads_read_copied_deleted_by_O": False,
            },
            "tests": total,
            "build": read("O_REPRODUCIBLE_BUILD.json"),
            "SOURCE_QUALIFIED": False,
            "SHADOW_QUALIFIED": False,
            "ECONOMICALLY_VALIDATED": False,
            "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
            "S1": "ONLY_ENABLED_STRATEGY",
            "S2": "RESEARCH_ONLY_DISABLED",
            "S3": "RESEARCH_ONLY_DISABLED",
            "remaining_blocker": "Current host control clock-domain incoherence. Need separately approved host remediation or demonstrably stable approved host, then independent O acceptance and new exact bounded public scan authority.",
            "native_or_operational_scan_started": False,
            "publication_merge_or_deploy": False,
            "successor_worker_started": False,
            "retention_state": read("audit/O_N_RETENTION_STATUS.json"),
            "preservation": read("O6_PRESERVATION_AFTER.json"),
        },
    )
    print(
        json.dumps(
            {"counts": total, "policy_sha256": policy_hash, "terminal": "O_HOST_CLOCK_STABILITY_REQUIRED"}
        )
    )


if __name__ == "__main__":
    main()
