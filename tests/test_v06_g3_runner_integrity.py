"""Unit tests for G3 Runner Evidence Integrity and Reporter Correctness.

Verifies fixes for:
- BLOCKER G3-F01: Machine-derived test scenario statuses (no hardcoded PASS)
- BLOCKER G3-F02: Fail-closed external smoke status (ENABLED_PASS unreachable without verified run)
- HIGH G3-F03: Genuine performance measurements (no calculated formulas, correct memory naming)
- HIGH G3-F04: Worktree preservation baseline comparison
- HIGH G3-F06: Consistency enforcement between test outcomes and terminal state
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts/ops_g3 is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_OPS_DIR = _REPO_ROOT / "scripts" / "ops_g3"
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

from run_operational_readiness import (
    SCENARIO_DEFINITIONS,
    TERMINAL_BLOCKED,
    TERMINAL_PASS,
    compare_worktree_snapshots,
    determine_terminal_state,
    evaluate_external_smoke,
    evaluate_scenarios,
    measure_performance_snapshot,
    parse_junit_xml,
)


def test_g3_f01_junit_xml_parsing_handles_pass_fail_skip_error(tmp_path: Path) -> None:
    """Prove that parse_junit_xml accurately identifies PASS, FAIL, ERROR, SKIPPED."""
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="1" failures="1" skipped="1" tests="4">
    <testcase classname="test_pkg" name="test_alpha" time="0.100" />
    <testcase classname="test_pkg" name="test_bravo" time="0.200">
      <failure message="assertion error">assert False</failure>
    </testcase>
    <testcase classname="test_pkg" name="test_charlie" time="0.050">
      <error message="runtime error">setup failed</error>
    </testcase>
    <testcase classname="test_pkg" name="test_delta" time="0.001">
      <skipped message="skip reason" />
    </testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    outcomes = parse_junit_xml(xml_file)
    assert outcomes["test_alpha"] == "PASS"
    assert outcomes["test_bravo"] == "FAIL"
    assert outcomes["test_charlie"] == "ERROR"
    assert outcomes["test_delta"] == "SKIPPED"


def test_g3_f01_scenario_evaluation_fails_when_test_fails() -> None:
    """Prove that a failing test marks scenario FAIL, never PASS (fixes G3-F01)."""
    # Simulate matrix 1 test failing
    test_outcomes = {
        "test_g3_matrix_1_parallel_initializers_elect_single_worker": "FAIL",
        "test_g3_matrix_2_cold_start_sigterm_and_fresh_restart_recovery": "PASS",
        "test_g3_matrix_3_unexpected_death_synthetic_fault_injection_reconciliation": "PASS",
        "test_g3_matrix_4_negative_callback_and_approval_matrix": "PASS",
        "test_g3_matrix_5_config_segregation_and_mainnet_credential_rejection": "PASS",
        "test_g3_matrix_6_startup_service_patterns_and_container_lint": "PASS",
        "test_g3_matrix_7_performance_and_resource_snapshot": "PASS",
    }
    scenarios, all_passed = evaluate_scenarios(test_outcomes, pytest_exit_code=1)

    assert all_passed is False
    sc1 = next(s for s in scenarios if s["scenario_id"] == "G3-SCN-01-PARALLEL-INITIALIZER-FCNTL")
    assert sc1["status"] == "FAIL"
    assert sc1["verified"] is False


def test_g3_f01_scenario_evaluation_marks_missing_test_not_run() -> None:
    """Prove that a missing test marks scenario NOT_RUN, never PASS."""
    # Omit matrix 3 test
    test_outcomes = {
        "test_g3_matrix_1_parallel_initializers_elect_single_worker": "PASS",
        "test_g3_matrix_2_cold_start_sigterm_and_fresh_restart_recovery": "PASS",
        "test_g3_matrix_4_negative_callback_and_approval_matrix": "PASS",
        "test_g3_matrix_5_config_segregation_and_mainnet_credential_rejection": "PASS",
        "test_g3_matrix_6_startup_service_patterns_and_container_lint": "PASS",
        "test_g3_matrix_7_performance_and_resource_snapshot": "PASS",
    }
    scenarios, all_passed = evaluate_scenarios(test_outcomes, pytest_exit_code=0)

    assert all_passed is False
    sc3 = next(s for s in scenarios if s["scenario_id"] == "G3-SCN-03-FAULT-INJECTION-CRASH-CHECKPOINTS")
    assert sc3["status"] == "NOT_RUN"
    assert sc3["verified"] is False


def test_g3_f01_scenario_evaluation_all_pass_only_on_complete_success() -> None:
    """Prove that all scenarios are marked PASS only when every required test passes with exit code 0."""
    test_outcomes = {
        "test_g3_matrix_1_parallel_initializers_elect_single_worker": "PASS",
        "test_g3_matrix_2_cold_start_sigterm_and_fresh_restart_recovery": "PASS",
        "test_g3_matrix_3_unexpected_death_synthetic_fault_injection_reconciliation": "PASS",
        "test_g3_matrix_4_negative_callback_and_approval_matrix": "PASS",
        "test_g3_matrix_5_config_segregation_and_mainnet_credential_rejection": "PASS",
        "test_g3_matrix_6_startup_service_patterns_and_container_lint": "PASS",
        "test_g3_matrix_7_performance_and_resource_snapshot": "PASS",
    }
    scenarios, all_passed = evaluate_scenarios(test_outcomes, pytest_exit_code=0)

    assert all_passed is True
    assert len(scenarios) == len(SCENARIO_DEFINITIONS)
    for sc in scenarios:
        assert sc["status"] == "PASS"
        assert sc["verified"] is True


def test_g3_f02_external_smoke_fail_closed_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove smoke evaluation returns NOT_RUN_NO_TEST_CREDENTIALS when flag is unset."""
    monkeypatch.delenv("BTC_QUANT_G3_EXTERNAL_SMOKE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)

    receipt = evaluate_external_smoke()
    assert receipt["status"] == "NOT_RUN_NO_TEST_CREDENTIALS"
    assert receipt["flag_enabled"] is False
    assert receipt["credentials_provided"] is False
    assert receipt["observed_provider_calls_count"] == 0
    assert receipt["signed_writes_count"] == 0


def test_g3_f02_external_smoke_fail_closed_flag_on_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove smoke evaluation returns NOT_RUN_OPERATOR_AUTHORIZATION_REQUIRED when flag is set without creds."""
    monkeypatch.setenv("BTC_QUANT_G3_EXTERNAL_SMOKE", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)

    receipt = evaluate_external_smoke()
    assert receipt["status"] == "NOT_RUN_OPERATOR_AUTHORIZATION_REQUIRED"
    assert receipt["flag_enabled"] is True
    assert receipt["credentials_provided"] is False
    assert receipt["observed_provider_calls_count"] == 0


def test_g3_f02_external_smoke_fail_closed_dummy_credentials_no_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove dummy credentials do NOT produce ENABLED_PASS and values are never leaked in receipt."""
    dummy_secret = "secret-dummy-token-xyz-12345"
    monkeypatch.setenv("BTC_QUANT_G3_EXTERNAL_SMOKE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", dummy_secret)
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test_dummy_app")

    receipt = evaluate_external_smoke()
    # ENABLED_PASS must be completely unreachable
    assert receipt["status"] == "EXTERNAL_SMOKE_NOT_IMPLEMENTED"
    assert receipt["status"] != "ENABLED_PASS"
    assert receipt["flag_enabled"] is True
    assert receipt["credentials_provided"] is True
    assert receipt["observed_provider_calls_count"] == 0

    # Ensure secret value is never written in any receipt field
    receipt_str = str(receipt)
    assert dummy_secret not in receipt_str
    assert "cli_test_dummy_app" not in receipt_str


def test_g3_f03_performance_measurement_genuine_and_rss_labeled(tmp_path: Path) -> None:
    """Prove that cold start, migration, and recovery are genuine timings and RSS is accurately labeled."""
    snapshot = measure_performance_snapshot(tmp_path)

    # Durations must be positive numbers
    assert snapshot["schema_migration_ms"] > 0
    assert snapshot["runtime_cold_start_ms"] > 0
    assert snapshot["cold_recovery_ms"] > 0

    # Cold start must be genuinely measured, timing methodology explicitly noted
    assert snapshot["timing_methodology"] == "Exact time.perf_counter() boundaries for each stage; no calculated multipliers."

    # Memory field must be process_peak_rss_mb, NOT steady_state_rss_mb
    assert "process_peak_rss_mb" in snapshot
    assert "steady_state_rss_mb" not in snapshot
    assert snapshot["process_peak_rss_mb"] > 0
    assert snapshot["memory_metric_kind"] == "RUSAGE_SELF_PEAK_RSS_LINUX_KIB_CONVERTED_MIB"


def test_g3_f04_worktree_preservation_comparison() -> None:
    """Prove baseline comparison detects changes and does not unconditionally claim preserved=true."""
    baseline = {
        "repo_a": {"path": "/path/a", "head_sha": "sha_1", "branch": "main", "dirty_file_count": 0, "exists": True},
        "repo_b": {"path": "/path/b", "head_sha": "sha_2", "branch": "feat", "dirty_file_count": 2, "exists": True},
    }

    # Case 1: Identical current snapshot
    current_identical = {
        "repo_a": {"path": "/path/a", "head_sha": "sha_1", "branch": "main", "dirty_file_count": 0, "exists": True},
        "repo_b": {"path": "/path/b", "head_sha": "sha_2", "branch": "feat", "dirty_file_count": 2, "exists": True},
    }
    comp_ok = compare_worktree_snapshots(baseline, current_identical)
    assert comp_ok["repo_a"]["preserved"] is True
    assert comp_ok["repo_b"]["preserved"] is True

    # Case 2: Changed HEAD in repo_a
    current_head_changed = {
        "repo_a": {"path": "/path/a", "head_sha": "sha_MODIFIED", "branch": "main", "dirty_file_count": 0, "exists": True},
        "repo_b": {"path": "/path/b", "head_sha": "sha_2", "branch": "feat", "dirty_file_count": 2, "exists": True},
    }
    comp_head_bad = compare_worktree_snapshots(baseline, current_head_changed)
    assert comp_head_bad["repo_a"]["preserved"] is False
    assert comp_head_bad["repo_b"]["preserved"] is True

    # Case 3: Changed dirty file count in repo_b
    current_dirty_changed = {
        "repo_a": {"path": "/path/a", "head_sha": "sha_1", "branch": "main", "dirty_file_count": 0, "exists": True},
        "repo_b": {"path": "/path/b", "head_sha": "sha_2", "branch": "feat", "dirty_file_count": 5, "exists": True},
    }
    comp_dirty_bad = compare_worktree_snapshots(baseline, current_dirty_changed)
    assert comp_dirty_bad["repo_a"]["preserved"] is True
    assert comp_dirty_bad["repo_b"]["preserved"] is False


def test_g3_f06_reporter_consistency_enforcement() -> None:
    """Prove consistency checker rejects contradictions between test results and terminal state."""
    passing_scenarios = [
        {"scenario_id": "S1", "status": "PASS", "verified": True},
        {"scenario_id": "S2", "status": "PASS", "verified": True},
    ]
    failing_scenarios = [
        {"scenario_id": "S1", "status": "PASS", "verified": True},
        {"scenario_id": "S2", "status": "FAIL", "verified": False},
    ]
    clean_worktrees = {"repo_a": {"preserved": True}}
    dirty_worktrees = {"repo_a": {"preserved": False}}

    # When all pass, returns TERMINAL_PASS
    term1 = determine_terminal_state(passing_scenarios, all_passed=True, pytest_exit_code=0, worktree_comparison=clean_worktrees)
    assert term1 == TERMINAL_PASS

    # When scenario fails, returns TERMINAL_BLOCKED
    term2 = determine_terminal_state(failing_scenarios, all_passed=False, pytest_exit_code=1, worktree_comparison=clean_worktrees)
    assert term2 == TERMINAL_BLOCKED

    # When worktree modified, returns TERMINAL_BLOCKED
    term3 = determine_terminal_state(passing_scenarios, all_passed=True, pytest_exit_code=0, worktree_comparison=dirty_worktrees)
    assert term3 == TERMINAL_BLOCKED
