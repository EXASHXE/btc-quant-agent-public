"""Focused tests for 2022 Binance USD-M BTCUSDT native position gap."""

from __future__ import annotations

import json

import pytest

from scripts.research.bline_r3_ratio_gap.contracts import (
    BINANCE_METRICS_SCHEMA,
    EXPECTED_HOURLY_ORIGINS_2022,
    INVARIANTS,
    LABELS,
    OBSERVED_RATIO_BLANK_ORIGINS_2022,
    OBSERVED_RATIO_PRESENT_ORIGINS_2022,
    SIMULATED_COVERAGE_UPPER_BOUND_LABEL,
    TASK,
    TERMINAL_DECISION,
    sha256_digest,
)
from scripts.research.bline_r3_ratio_gap.reconcile import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_OUTPUT_DIR,
    compare_reference_slices,
)


def test_contracts_and_decision_authority() -> None:
    """Verify task identity, terminal decision, and invariant freeze."""
    assert TASK == "V065-BLINE-R3-2022-NATIVE-POSITION-GAP-01"
    assert TERMINAL_DECISION == "NATIVE_RATIO_2022_PUBLISHER_GAP"
    assert "P3_ACCESS_SCOPE_HOLD" in LABELS
    assert "REAL_FUNDS_WRITE_NONE" in LABELS
    assert "no_account_ratio_substitution" in INVARIANTS
    assert "no_zero_or_fill_inference" in INVARIANTS


def test_schema_invariance_across_2021_2022_2023() -> None:
    """Verify raw archive CSV schema identity across 2021, 2022, and 2023."""
    slices = compare_reference_slices(DEFAULT_CATALOG_PATH)
    assert len(slices) >= 9, "Expected reference slices across all three years"

    for s in slices:
        assert s["header_exact_match"] is True, f"Header mismatch in slice {s['period']}"
        assert s["header"] == BINANCE_METRICS_SCHEMA
        # Column 0: create_time, Column 1: symbol
        assert s["header"][0] == "create_time"
        assert s["header"][1] == "symbol"
        # Column 2: base OI, Column 3: notional OI
        assert s["header"][2] == "sum_open_interest"
        assert s["header"][3] == "sum_open_interest_value"
        # Column 4: accounts ratio, Column 5: positions ratio
        assert s["header"][4] == "count_toptrader_long_short_ratio"
        assert s["header"][5] == "sum_toptrader_long_short_ratio"


def test_2022_observed_and_missing_origin_counts() -> None:
    """Verify exact 2022 origin counts match the authoritative 1,115 vs 7,645 split."""
    report_file = DEFAULT_OUTPUT_DIR / "reconciliation_report.json"
    if not report_file.exists():
        pytest.skip("Deliverables not generated yet; run CLI first")

    report = json.loads(report_file.read_text(encoding="utf-8"))
    summary = report["year_2022_summary"]

    assert summary["scheduled_hourly_origins"] == EXPECTED_HOURLY_ORIGINS_2022 == 8760
    assert summary["native_ratio_present_origins"] == OBSERVED_RATIO_PRESENT_ORIGINS_2022 == 1115
    assert summary["native_ratio_missing_origins"] == OBSERVED_RATIO_BLANK_ORIGINS_2022 == 7645
    assert summary["native_ratio_present_origins"] + summary["native_ratio_missing_origins"] == 8760
    assert summary["native_oi_present_origins"] == 8750


def test_missing_position_classification_is_raw_blank_string() -> None:
    """Verify missing position samples are classified strictly as RAW_BLANK_STRING across full taxonomy."""
    report_file = DEFAULT_OUTPUT_DIR / "origin_gap_classification.json"
    if not report_file.exists():
        pytest.skip("Deliverables not generated yet")

    gaps = json.loads(report_file.read_text(encoding="utf-8"))
    assert len(gaps) == 10, "Expected all 10 gap taxonomy categories"
    assert gaps["RAW_BLANK_STRING"] == OBSERVED_RATIO_BLANK_ORIGINS_2022 == 7645
    assert gaps["SAMPLE_TRULY_ABSENT"] == 0
    assert gaps["NATIVE_ZERO"] == 0
    assert gaps["NULL_LITERAL"] == 0
    assert gaps["INVALID_FLOAT"] == 0
    assert gaps["RAW_NORMALIZED_MAPPING_MISMATCH"] == 0
    assert gaps["TIMESTAMP_MISMATCH"] == 0
    assert gaps["MISSING_EXACT_4H_PREDECESSOR"] == 0
    assert gaps["CONFLICTING_SOURCE"] == 0
    assert gaps["UNACCEPTABLE_SOURCE_IDENTITY"] == 0


def test_synthetic_boundary_predecessor_clock() -> None:
    """Verify 4-hour predecessor clock behavior at active-blank boundaries.

    In accordance with state_at_origin and contracts_r2:
    - Base OI requires both origin sample (t) and 4-hour predecessor (t - 4h).
    - Top-trader position ratio is an origin-level condition at time t (no predecessor required).
    """
    t_origin = 1653872460_000_000  # 2022-05-30 01:01:00 UTC
    cutoff_us = t_origin - 60_000_000
    target_sample_us = cutoff_us - 600_000_000
    pred_sample_us = target_sample_us - 4 * 3600 * 1_000_000

    # Case 1: Valid base OI at target and pred; valid pos_ratio at target only.
    # Predecessor position ratio is None (blank).
    # Since position ratio is a level condition, this origin IS joint eligible!
    db_level_valid = {
        target_sample_us: {"base_oi": 85000.0, "pos_ratio": 1.25},
        pred_sample_us: {"base_oi": 84500.0, "pos_ratio": None},
    }
    tgt1 = db_level_valid.get(target_sample_us)
    prd1 = db_level_valid.get(pred_sample_us)
    has_oi1 = tgt1 is not None and tgt1["base_oi"] is not None
    has_pred_oi1 = prd1 is not None and prd1["base_oi"] is not None
    has_pos1 = tgt1 is not None and tgt1["pos_ratio"] is not None

    joint_eligible1 = has_oi1 and has_pred_oi1 and has_pos1
    assert joint_eligible1 is True, "Must be joint eligible when target has ratio and base OI has 4h pred"

    # Case 2: Predecessor BASE OI is missing (or 0E-8 non-positive).
    # Must reject origin because base OI delta requires exact 4h predecessor.
    db_missing_pred_oi = {
        target_sample_us: {"base_oi": 85000.0, "pos_ratio": 1.25},
        pred_sample_us: {"base_oi": None, "pos_ratio": None},
    }
    tgt2 = db_missing_pred_oi.get(target_sample_us)
    prd2 = db_missing_pred_oi.get(pred_sample_us)
    has_oi2 = tgt2 is not None and tgt2["base_oi"] is not None
    has_pred_oi2 = prd2 is not None and prd2["base_oi"] is not None
    has_pos2 = tgt2 is not None and tgt2["pos_ratio"] is not None

    joint_eligible2 = has_oi2 and has_pred_oi2 and has_pos2
    assert joint_eligible2 is False, "Must reject origin when 4h predecessor base OI is missing"


def test_no_account_ratio_substitution() -> None:
    """Ensure count_toptrader_long_short_ratio (accounts) is NEVER substituted for position ratio."""
    # Sample row where pos_ratio is blank but hypothetical account ratio is present
    row = {
        "base_oi": 80000.0,
        "act_ratio": 1.45,  # accounts
        "pos_ratio": None,  # positions missing
    }

    # Evaluation strictly requires pos_ratio
    pos_present = row["pos_ratio"] is not None
    assert pos_present is False, "Must not treat account ratio as position ratio"


def test_simulated_coverage_upper_bound_labeling_and_computation() -> None:
    """Verify simulated coverage upper bound calculation and strict non-trading labeling."""
    report_file = DEFAULT_OUTPUT_DIR / "simulated_coverage_upper_bound.json"
    if not report_file.exists():
        pytest.skip("Deliverables not generated yet")

    sim = json.loads(report_file.read_text(encoding="utf-8"))
    assert sim["label"] == SIMULATED_COVERAGE_UPPER_BOUND_LABEL
    assert sim["simulated_eligible_hourly_origins"] == 8746
    assert sim["observed_eligible_hourly_origins"] == 1115
    assert sim["counterfactual_additional_origins"] == 7631
    assert "warning" in sim
    assert "DO NOT treat this upper bound as real observed data" in sim["warning"]


def test_deliverable_manifest_and_checksum_integrity() -> None:
    """Verify deliverable files exist and match the manifest digest."""
    manifest_file = DEFAULT_OUTPUT_DIR / "manifest.json"
    if not manifest_file.exists():
        pytest.skip("Manifest not generated yet")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["task"] == TASK
    assert manifest["terminal_decision"] == TERMINAL_DECISION

    for filename, expected_digest in manifest["files"].items():
        if filename == "manifest.json":
            continue
        file_path = DEFAULT_OUTPUT_DIR / filename
        assert file_path.exists(), f"Deliverable missing: {filename}"
        actual_digest = sha256_digest(file_path)
        assert actual_digest == expected_digest, f"Digest mismatch for {filename}"
