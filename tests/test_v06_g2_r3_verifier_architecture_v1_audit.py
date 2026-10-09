"""Role B Final Independent Semantic and Adversarial Pytest Suite for Role A P1 Architecture V1.

Task ID: V06_G2_R3_P1_ARCH_V1_B_FINAL_INDEPENDENT_SEMANTIC_AUDIT_R1
Controller Dispatch SHA: 5f9b7f75215b394ad86d49b468e7acd9a89c23a2
Pinned Prompt SHA: f2ff646bb317c7a7cb4de8bf6515e1d3cbe9e5f0
Target A Commit SHA: b5d34aacd36dc27454944a22436db555c3f6eeb8
Role B Start SHA: 068a4005f68b5ee4a970063cb1f3bc524a08784a
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.strategy_research.r3_verification.architecture_v1.a_arch_v1_auditor import (
    A_PARENT_R2_REAUDIT_VERDICT_SHA,
    A_R2_PATCH_SHA,
    A_TARGET_SHA,
    B_START_SHA,
    CONTROLLER_DISPATCH_SHA,
    EXPECTED_A_MODIFIED_FILES,
    PINNED_PROMPT_SHA,
    TASK_ID,
    TERMINAL_VERDICT,
    run_full_architecture_v1_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_JSON_PATH = (
    REPO_ROOT
    / "evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/"
    / "B01_B07_FINAL_INDEPENDENT_BEHAVIOR_MATRIX.json"
)
RECEIPT_JSON_PATH = (
    REPO_ROOT
    / "evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/"
    / "B_FINAL_SYNTHETIC_EXECUTION_RECEIPT.json"
)
VERDICT_MD_PATH = (
    REPO_ROOT
    / "docs/strategy_research/g2_r3/prep_b/architecture_v1/"
    / "B_FINAL_INDEPENDENT_ARCHITECTURE_VERDICT.md"
)


@pytest.fixture(scope="module")
def arch_v1_audit_bundle() -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the isolated Role B positive + adversarial audit once per module."""
    return run_full_architecture_v1_audit(repo_root=REPO_ROOT)


def test_arch_v1_isolated_runtime_binding_and_git_lineage(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify isolated /tmp extraction of b5d34aac, SHA lineage, and Role A scope hygiene."""
    matrix, receipt = arch_v1_audit_bundle

    assert matrix["task_id"] == TASK_ID
    assert matrix["controller_dispatch_sha"] == CONTROLLER_DISPATCH_SHA
    assert matrix["pinned_prompt_sha"] == PINNED_PROMPT_SHA
    assert matrix["a_target_sha"] == A_TARGET_SHA
    assert matrix["b_start_sha"] == B_START_SHA
    assert matrix["terminal_verdict"] == TERMINAL_VERDICT

    runtime_binding = receipt["isolated_runtime_binding"]
    extract_root = runtime_binding["extracted_archive_root"]
    assert runtime_binding["verified_isolated_from_role_b_src"] is True
    for mod_label, mod_path in runtime_binding["module_file_paths"].items():
        assert mod_path.startswith(extract_root), (
            f"Module {mod_label} was not loaded from isolated archive: {mod_path}"
        )
        assert str(REPO_ROOT / "src") not in mod_path

    lineage = receipt["git_lineage_and_scope_audit"]
    assert lineage["lineage_verified"] is True
    assert lineage["resolved_a_target_sha"] == A_TARGET_SHA
    assert lineage["a_parent_sha_398e6bab"] == A_PARENT_R2_REAUDIT_VERDICT_SHA
    assert lineage["a_great_grandparent_sha_2c60b065"] == A_R2_PATCH_SHA
    assert lineage["a_modified_files_since_2c60b065"] == EXPECTED_A_MODIFIED_FILES
    assert lineage["forbidden_or_protected_files_touched_by_a"] == []


def test_b01_positive_and_adversarial_mark_causality_and_stage8_mtm(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B01 positive out-of-order stale mark rejection and adversarial B01-D1/D2 defects."""
    matrix, _ = arch_v1_audit_bundle
    b01 = matrix["items"]["B01"]

    assert b01["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b01["positive_verification"]["mark_price_after_stale_arrival"] == "51000"

    assert b01["arch_v1_b5d34aac_adversarial_case_status"] == "BLOCKED"
    assert b01["arch_v1_b5d34aac_final_status"] == "BLOCKED"

    d1 = b01["adversarial_verification"]["b01_d1_same_close_conflict_and_late_overwrite"]
    assert d1["virtual_book_order_ab_mark"] == "52000"
    assert d1["virtual_book_order_ba_mark"] == "50000"
    assert d1["replay_engine_order_ab_mark"] == "50000"
    assert d1["replay_engine_order_ba_mark"] == "52000"
    assert d1["late_same_close_overwritten_mark_at_s_plus_60s"] == "48000"

    d2 = b01["adversarial_verification"]["b01_d2_stage8_future_mark_leak_and_mtm_reset"]
    assert d2["stage1_pit_safe_mark_ingested"] is False
    assert d2["stage8_economic_equity_from_unclosed_future_bar"] == "1100.000000000000"
    assert d2["stage8_economic_equity_when_current_marks_empty"] == "1000.000000000000"


def test_b02_positive_and_adversarial_ack_idempotency_and_cooldown_integrity(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B02 positive duplicate ACK idempotency and adversarial B02-D1/D2/D3 defects."""
    matrix, _ = arch_v1_audit_bundle
    b02 = matrix["items"]["B02"]

    assert b02["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b02["arch_v1_b5d34aac_adversarial_case_status"] == "BLOCKED"
    assert b02["arch_v1_b5d34aac_final_status"] == "BLOCKED"

    d1 = b02["adversarial_verification"]["b02_d1_contradictory_reused_ack_id_silently_ignored"]
    assert d1["exception_raised_on_contradictory_payload"] is False

    d2 = b02["adversarial_verification"]["b02_d2_late_exit_ack_rewinds_cooldown_until_ms"]
    assert d2["cooldown_rewound_by_ms"] == 7_140_000  # 119 minutes rewound backwards

    d3 = b02["adversarial_verification"]["b02_d3_fill_id_vs_position_id_premature_auto_ack"]
    assert d3["position_acknowledged_at_s"] is True
    assert d3["cost_commitment_o_at_s"] == "0.00"


def test_b03_positive_and_adversarial_funding_window_and_reserve_retention(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B03 positive pre-S exit attribution and adversarial B03-D1/D2/D3 defects."""
    matrix, _ = arch_v1_audit_bundle
    b03 = matrix["items"]["B03"]

    assert b03["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b03["positive_verification"]["pre_s_exit_at_s_minus_1_funding_cost_usdt"] == "0.200000"

    assert b03["arch_v1_b5d34aac_adversarial_case_status"] == "BLOCKED"
    assert b03["arch_v1_b5d34aac_final_status"] == "BLOCKED"

    d1 = b03["adversarial_verification"]["b03_d1_premature_reserve_release_before_funding_ack"]
    assert d1["funding_reserve_rf_at_s_plus_60k"] == "0.00"
    assert d1["cash_at_s_plus_60k"] == "1000.000000000000"
    assert d1["available_capital_at_s_plus_60k"] == "945.00000000000000"

    d2 = b03["adversarial_verification"]["b03_d2_pre_s_exit_ack_before_s_releases_reserve_early"]
    assert d2["funding_reserve_rf_before_s"] == "0.00"
    assert d2["unsettled_exit_trades_count"] == 0

    d3 = b03["adversarial_verification"]["b03_d3_substring_collision_pos1_in_pos10"]
    assert d3["trade_pos10_charged_usdt"] == "0.200000"
    assert d3["trade_pos1_charged_usdt"] == "0"


def test_b04_positive_and_adversarial_exit_semantics(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B04 SL-first collision, gap open pricing, minute-end timestamp, and cooldown."""
    matrix, _ = arch_v1_audit_bundle
    b04 = matrix["items"]["B04"]

    assert b04["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b04["arch_v1_b5d34aac_adversarial_case_status"] == "PASS"
    assert b04["arch_v1_b5d34aac_final_status"] == "PASS"
    assert b04["positive_verification"]["sl_tp_collision_reason"] == "STOP_LOSS"
    assert b04["positive_verification"]["sl_tp_collision_holding_minutes_floor"] == 1
    assert b04["positive_verification"]["adverse_gap_sl_raw_exit_price"] == "48000"
    assert b04["positive_verification"]["favorable_gap_tp_raw_exit_price"] == "51000"


def test_b05_positive_and_adversarial_unacknowledged_exposure_and_pending_exit_loss(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B05 open unacked loss kill and adversarial B05-D1/D2 pending exit loss blindspot."""
    matrix, _ = arch_v1_audit_bundle
    b05 = matrix["items"]["B05"]

    assert b05["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b05["arch_v1_b5d34aac_adversarial_case_status"] == "BLOCKED"
    assert b05["arch_v1_b5d34aac_final_status"] == "BLOCKED"

    d1 = b05["adversarial_verification"][
        "b05_d1_pending_exit_ack_loss_invisible_to_stage2_kill_and_capital"
    ]
    assert d1["killed_at_s_plus_60k"] is False
    assert float(d1["pending_exit_gross_pnl_usdt"]) <= -150.0
    assert float(d1["available_capital_at_s_plus_60k"]) > 930.0

    d2 = b05["adversarial_verification"][
        "b05_d2_compute_available_capital_ignores_unacked_unrealized_loss"
    ]
    assert d2["decision_equity_usdt"] == "999.799900000000"
    assert float(d2["reported_available_capital_usdt"]) > 440.0


def test_b06_positive_and_adversarial_signal_progression_and_skipped_bar_scan(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B06 cooldown progression and adversarial B06-D1/D2 skipped-bar and fallthrough bugs."""
    matrix, _ = arch_v1_audit_bundle
    b06 = matrix["items"]["B06"]

    assert b06["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b06["arch_v1_b5d34aac_adversarial_case_status"] == "BLOCKED"
    assert b06["arch_v1_b5d34aac_final_status"] == "BLOCKED"

    d1 = b06["adversarial_verification"][
        "b06_d1_skipped_intermediate_hour_drops_cancellation_and_low"
    ]
    assert d1["signal_emitted_at_bar_27_despite_bar_26_crash"] is not None

    d2 = b06["adversarial_verification"]["b06_d2_same_bar_cancel_and_rebreakout_fallthrough"]
    assert d2["same_bar_rebreakout_registered_on_hour_3"] is True


def test_b07_positive_and_adversarial_per_position_reserve_cap_and_shortfall(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify B07 witness reserve isolation at S and adversarial B07-D1/D2 shortfall/conservation gaps."""
    matrix, _ = arch_v1_audit_bundle
    b07 = matrix["items"]["B07"]

    assert b07["arch_v1_b5d34aac_positive_case_status"] == "PASS"
    assert b07["positive_verification"]["eth_witness_reserve_at_s_usdt"] == "2.00"
    assert b07["positive_verification"]["btc_owner_reserve_at_s_usdt"] == "0.00"

    assert b07["arch_v1_b5d34aac_adversarial_case_status"] == "BLOCKED"
    assert b07["arch_v1_b5d34aac_final_status"] == "BLOCKED"

    d1 = b07["adversarial_verification"][
        "b07_d1_unreserved_shortfall_and_released_reserve_before_funding_ack"
    ]
    assert d1["available_capital_before_funding_ack_usdt"] == "941.00000000000000"

    d2 = b07["adversarial_verification"][
        "b07_d2_stage2_stage3_conservation_equation_mismatch_at_s"
    ]
    assert d2["book_funding_reserve_rf_during_stage2_at_s"] == "0.50"
    assert d2["sum_open_pos_plus_pending_exit_acks_during_stage2_at_s"] == "0"
    assert d2["hidden_in_unsettled_exit_trades_usdt"] == "0.50"


def test_synthetic_e2e_240h_warmup_and_serialized_artifacts_sync(
    arch_v1_audit_bundle: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Verify 240h warmup E2E reconciliation and on-disk JSON/Markdown deliverables."""
    matrix, receipt = arch_v1_audit_bundle
    e2e = receipt["synthetic_e2e_audit"]

    assert e2e["warmup_hours_verified"] == 240
    assert e2e["happy_path_reconciled_with_role_a_receipt"] is True
    assert e2e["candidate_order_permutation_check"]["permutation_invariant"] is True
    assert (
        e2e["profiles"]["CLOSED_RETEST_LONG_12H_STRESS"][
            "retained_as_geometry_ineligible_witness"
        ]
        is True
    )

    assert MATRIX_JSON_PATH.is_file(), f"Missing matrix JSON: {MATRIX_JSON_PATH}"
    assert RECEIPT_JSON_PATH.is_file(), f"Missing receipt JSON: {RECEIPT_JSON_PATH}"
    assert VERDICT_MD_PATH.is_file(), f"Missing verdict Markdown: {VERDICT_MD_PATH}"

    disk_matrix = json.loads(MATRIX_JSON_PATH.read_text(encoding="utf-8"))
    disk_receipt = json.loads(RECEIPT_JSON_PATH.read_text(encoding="utf-8"))

    assert disk_matrix == matrix
    assert disk_receipt["task_id"] == receipt["task_id"]
    assert disk_receipt["a_target_sha"] == receipt["a_target_sha"]
    assert disk_receipt["terminal_verdict"] == TERMINAL_VERDICT
    assert disk_receipt["synthetic_e2e_audit"] == receipt["synthetic_e2e_audit"]
    assert (
        disk_receipt["cross_stage_compound_conservation_audit"]
        == receipt["cross_stage_compound_conservation_audit"]
    )

    verdict_md = VERDICT_MD_PATH.read_text(encoding="utf-8")
    assert TERMINAL_VERDICT in verdict_md
    assert A_TARGET_SHA in verdict_md
    assert CONTROLLER_DISPATCH_SHA in verdict_md
    assert PINNED_PROMPT_SHA in verdict_md
