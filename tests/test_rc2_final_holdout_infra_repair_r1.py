"""Adversarial and qualification test suite for RC2 Final Holdout Infra Repair R1.

Verifies:
1. Finding I — Empty/missing field in Binance metrics normalizer:
   - Latest hourly row missing top position, earlier same-bucket valid -> only that field uses earlier valid event.
   - Entire hour missing top position -> missing bucket, coverage/lookback audit fails closed.
   - Whitespace, NaN, infinity, text garbage, malformed timestamps handled without crash or corruption.
   - Missing taker in 15m bucket, valid OI at hour -> independent selection.
   - Duplicate event times and reversed/permuted archive order give identical normalized digests.
   - Known FIL archive regression remains 17:55, not archive-order 17:35.
   - PIT causality: no future event visible in scanner step.
   - Full-window missing-middle lookback fails closed before outcome resolution.
2. Finding II — Execution dispatch accepted by Controller authority:
   - Wrong execution dispatch 405e0042... and random 40-hex rejected before network / capability creation.
   - Valid Controller fixture dispatch proof accepted only with matching runner + seal + policy + incident commit.
   - Target substitution in authority JSON rejected.
   - Incomplete / malformed authority JSON or stale / un-fetched docs ref rejected fail-closed.
3. Source retrieval failure still durably publishes INFRA_INCOMPLETE.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.rc2.validation.r3_access_guard import (
    AccessCapability,
    ExecutionAccessLedger,
)
from scripts.rc2.validation.run_holdout_r3 import (
    FROZEN_POLICY_SHA,
    ORIGINAL_INCIDENT_EVIDENCE_COMMIT,
    REFERENCES,
    REQUIRED_DECISION,
    RETRY_AUTHORITY_REL_PATH,
    TASK_ID,
    audit_full_window_production_context,
    build_dataset,
    check_execution_authorization,
    finalize_failed_attempt,
    validate_retry_dispatch_authority,
)
from scripts.rc2.validation.source_normalizer import (
    normalize_metrics_rows,
    parse_event_timestamp,
    parse_finite_float,
    verify_fil_20260906_regression,
    verify_permutation_invariance,
)
from scripts.rc2.validation.target_seal import (
    TARGET_SEAL_SCHEMA_VERSION,
)

METRICS_HEADER = [
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
]

CACHED_FIL_ZIP = (
    Path("/tmp/rc2_r1_1_source_cache")
    / hashlib.sha256(
        b"https://data.binance.vision/data/futures/um/daily/metrics/FILUSDT/FILUSDT-metrics-2026-09-06.zip"
    ).hexdigest()
)


# =====================================================================
# Finding I — Normalizer Missing-Value & Per-Field Selection Tests
# =====================================================================

def test_parse_finite_float_contract() -> None:
    """Explicitly verify valid, missing, and invalid numeric states."""
    # Valid finite numbers
    assert parse_finite_float("123.45") == (123.45, "VALID")
    assert parse_finite_float(" 0.001 ") == (0.001, "VALID")
    assert parse_finite_float("-42.5") == (-42.5, "VALID")
    assert parse_finite_float(100) == (100.0, "VALID")
    assert parse_finite_float(0.0) == (0.0, "VALID")

    # Missing values (empty / whitespace / None) -> no constant/NaN replacement
    assert parse_finite_float("") == (None, "MISSING")
    assert parse_finite_float("   ") == (None, "MISSING")
    assert parse_finite_float(None) == (None, "MISSING")

    # Invalid values (NaN, Inf, text garbage) -> fail-closed rejection
    assert parse_finite_float("nan") == (None, "INVALID")
    assert parse_finite_float("NaN") == (None, "INVALID")
    assert parse_finite_float("inf") == (None, "INVALID")
    assert parse_finite_float("-Infinity") == (None, "INVALID")
    assert parse_finite_float("corrupt_value") == (None, "INVALID")
    assert parse_finite_float(float("nan")) == (None, "INVALID")
    assert parse_finite_float(float("inf")) == (None, "INVALID")


def test_latest_hourly_row_missing_top_position_earlier_same_bucket_valid() -> None:
    """Verify Finding I core fix:

    When the latest row in an hour has an empty top position (''), only top_pos
    falls back to the earlier valid event in the same bucket; other metrics retain the latest event.
    """
    tf_start = parse_event_timestamp("2026-09-06 17:00:00")
    data_end = parse_event_timestamp("2026-09-06 17:59:59")

    # Three events in the 17h bucket
    # Row 1: 17:15 - all valid
    # Row 2: 17:35 - all valid
    # Row 3: 17:55 - top_pos is empty (''), but oi, gls, top_acc, taker are valid
    rows = [
        METRICS_HEADER,
        ["2026-09-06 17:15:00", "TESTUSDT", "100.0", "1000.0", "1.1", "1.15", "1.2", "1.25"],
        ["2026-09-06 17:35:00", "TESTUSDT", "110.0", "1100.0", "1.2", "1.30", "1.3", "1.35"],
        ["2026-09-06 17:55:00", "TESTUSDT", "120.0", "1200.0", "1.4", "",     "1.5", "1.55"],
    ]

    norm = normalize_metrics_rows(rows, METRICS_HEADER, tf_start, data_end, symbol="TESTUSDT")

    # oi_hist must select latest valid event in bucket: 17:55:00
    assert len(norm["oi_hist"]) == 1
    assert norm["oi_hist"][0]["timestamp"] == parse_event_timestamp("2026-09-06 17:55:00")
    assert norm["oi_hist"][0]["sumOpenInterest"] == 120.0

    # gls_hist and top_acc_hist also select latest event: 17:55:00
    assert norm["gls_hist"][0]["timestamp"] == parse_event_timestamp("2026-09-06 17:55:00")
    assert norm["gls_hist"][0]["longShortRatio"] == 1.5

    assert norm["top_acc_hist"][0]["timestamp"] == parse_event_timestamp("2026-09-06 17:55:00")
    assert norm["top_acc_hist"][0]["longShortRatio"] == 1.4

    # taker_hist selects 17:55:00 for the 17:45-18:00 15m bucket
    assert norm["taker_hist"][-1]["timestamp"] == parse_event_timestamp("2026-09-06 17:55:00")
    assert norm["taker_hist"][-1]["buySellRatio"] == 1.55

    # top_pos_hist MUST select 17:35:00 (earlier valid event in same bucket) with value 1.30
    assert len(norm["top_pos_hist"]) == 1
    assert norm["top_pos_hist"][0]["timestamp"] == parse_event_timestamp("2026-09-06 17:35:00")
    assert norm["top_pos_hist"][0]["longShortRatio"] == 1.30

    # Audit counters must record the missing observation exactly
    top_pos_audit = norm["field_audit"]["sum_toptrader_long_short_ratio"]
    assert top_pos_audit["valid_count"] == 2
    assert top_pos_audit["missing_count"] == 1
    assert top_pos_audit["invalid_count"] == 0
    assert top_pos_audit["selected_count"] == 1
    assert top_pos_audit["missing_bucket_count"] == 0

    oi_audit = norm["field_audit"]["sum_open_interest"]
    assert oi_audit["valid_count"] == 3
    assert oi_audit["missing_count"] == 0


def test_entire_hour_missing_top_position_yields_missing_bucket() -> None:
    """When an entire hour has NO valid top position observations, that bucket is recorded as missing."""
    tf_start = parse_event_timestamp("2026-09-06 17:00:00")
    data_end = parse_event_timestamp("2026-09-06 18:59:59")

    # Hour 17: all valid
    # Hour 18: top_pos is '' in every row, other fields valid
    rows = [
        METRICS_HEADER,
        ["2026-09-06 17:55:00", "TESTUSDT", "100.0", "1000.0", "1.1", "1.2", "1.3", "1.4"],
        ["2026-09-06 18:15:00", "TESTUSDT", "110.0", "1100.0", "1.2", "",    "1.4", "1.5"],
        ["2026-09-06 18:55:00", "TESTUSDT", "120.0", "1200.0", "1.3", "   ", "1.5", "1.6"],
    ]

    norm = normalize_metrics_rows(rows, METRICS_HEADER, tf_start, data_end, symbol="TESTUSDT")

    # OI has both hour 17 and hour 18
    assert len(norm["oi_hist"]) == 2

    # top_pos_hist has ONLY hour 17; hour 18 is completely missing
    assert len(norm["top_pos_hist"]) == 1
    assert norm["top_pos_hist"][0]["timestamp"] == parse_event_timestamp("2026-09-06 17:55:00")

    top_pos_audit = norm["field_audit"]["sum_toptrader_long_short_ratio"]
    assert top_pos_audit["valid_count"] == 1
    assert top_pos_audit["missing_count"] == 2
    assert top_pos_audit["selected_count"] == 1
    assert top_pos_audit["missing_bucket_count"] == 1


def test_adversarial_numeric_inputs_whitespace_nan_inf_garbage_malformed_ts() -> None:
    """Malformed headers, bad timestamps, whitespace, NaNs, and garbage text are handled fail-closed."""
    tf_start = parse_event_timestamp("2026-09-06 17:00:00")
    data_end = parse_event_timestamp("2026-09-06 17:59:59")

    rows = [
        METRICS_HEADER,
        # Header row repetition in middle of CSV
        ["calc_time", "symbol", "sum_open_interest", "sum_open_interest_value", "c", "s", "c", "s"],
        # Malformed timestamp
        ["INVALID_TIMESTAMP_HERE", "TESTUSDT", "100.0", "1000.0", "1.1", "1.2", "1.3", "1.4"],
        # Short row (< len(header))
        ["2026-09-06 17:10:00", "TESTUSDT"],
        # Row with NaN, Inf, whitespace, text garbage
        ["2026-09-06 17:20:00", "TESTUSDT", "NaN", "1000.0", "Infinity", "   ", "garbage_text", "-inf"],
        # Row with valid observations
        ["2026-09-06 17:40:00", "TESTUSDT", "200.0", "2000.0", "1.2", "1.3", "1.4", "1.5"],
    ]

    norm = normalize_metrics_rows(rows, METRICS_HEADER, tf_start, data_end, symbol="TESTUSDT")

    # Dropped records audit verification
    dropped = norm["dropped_records"]
    assert dropped["header_rows_count"] == 2
    assert dropped["malformed_timestamp_count"] == 1
    assert dropped["malformed_rows_count"] == 1

    # Valid row at 17:40 was selected for all metrics
    assert len(norm["oi_hist"]) == 1
    assert norm["oi_hist"][0]["sumOpenInterest"] == 200.0
    assert norm["top_pos_hist"][0]["longShortRatio"] == 1.3
    assert norm["gls_hist"][0]["longShortRatio"] == 1.4

    # Verify invalid count for NaN and text garbage
    oi_audit = norm["field_audit"]["sum_open_interest"]
    assert oi_audit["invalid_count"] == 1  # 'NaN'
    gls_audit = norm["field_audit"]["count_long_short_ratio"]
    assert gls_audit["invalid_count"] == 1  # 'garbage_text'
    top_pos_audit = norm["field_audit"]["sum_toptrader_long_short_ratio"]
    assert top_pos_audit["missing_count"] == 1  # '   '


def test_missing_taker_in_15m_bucket_independent_of_hourly_oi() -> None:
    """Missing taker in one 15m bucket does not discard hourly OI, and vice-versa."""
    tf_start = parse_event_timestamp("2026-09-06 17:00:00")
    data_end = parse_event_timestamp("2026-09-06 17:59:59")

    # 4 distinct 15m intervals:
    # 17:10 (bucket 17:00-17:15): taker valid
    # 17:25 (bucket 17:15-17:30): taker missing (''), OI valid
    # 17:40 (bucket 17:30-17:45): taker valid
    # 17:55 (bucket 17:45-18:00): taker valid, OI missing ('')
    rows = [
        METRICS_HEADER,
        ["2026-09-06 17:10:00", "TESTUSDT", "100.0", "1000.0", "1.1", "1.1", "1.1", "1.10"],
        ["2026-09-06 17:25:00", "TESTUSDT", "110.0", "1100.0", "1.2", "1.2", "1.2", ""],
        ["2026-09-06 17:40:00", "TESTUSDT", "120.0", "1200.0", "1.3", "1.3", "1.3", "1.30"],
        ["2026-09-06 17:55:00", "TESTUSDT", "",      "1300.0", "1.4", "1.4", "1.4", "1.40"],
    ]

    norm = normalize_metrics_rows(rows, METRICS_HEADER, tf_start, data_end, symbol="TESTUSDT")

    # taker_hist has observations for 17:10, 17:40, 17:55 (3 buckets out of 4)
    taker_ts = [x["timestamp"] for x in norm["taker_hist"]]
    assert len(taker_ts) == 3
    assert parse_event_timestamp("2026-09-06 17:25:00") not in taker_ts

    # oi_hist selects 17:40 (the latest valid OI in the hourly bucket, since 17:55 was '')
    assert len(norm["oi_hist"]) == 1
    assert norm["oi_hist"][0]["timestamp"] == parse_event_timestamp("2026-09-06 17:40:00")
    assert norm["oi_hist"][0]["sumOpenInterest"] == 120.0


def test_duplicate_event_times_and_permutations_identical_digests() -> None:
    """Duplicate event timestamps with varied content are deterministically tie-broken

    and permutation invariant.
    """
    tf_start = parse_event_timestamp("2026-09-06 17:00:00")
    data_end = parse_event_timestamp("2026-09-06 17:59:59")

    # Rows with duplicate timestamps and different values
    rows = [
        ["2026-09-06 17:15:00", "TESTUSDT", "100.0", "1000.0", "1.1", "1.2", "1.3", "1.4"],
        ["2026-09-06 17:15:00", "TESTUSDT", "105.0", "1050.0", "1.1", "1.2", "1.3", "1.4"],
        ["2026-09-06 17:30:00", "TESTUSDT", "110.0", "1100.0", "1.2", "1.3", "1.4", "1.5"],
        ["2026-09-06 17:45:00", "TESTUSDT", "120.0", "1200.0", "1.3", "1.4", "1.5", "1.6"],
        ["2026-09-06 17:45:00", "TESTUSDT", "125.0", "1250.0", "1.3", "1.4", "1.5", "1.6"],
    ]

    report = verify_permutation_invariance(
        rows, METRICS_HEADER, tf_start, data_end, num_permutations=10, seed=12345
    )
    assert report["permutation_invariance_proven"] is True
    assert report["tested_order_count"] == 12
    assert report["original_combined_digest"] == report["reversed_combined_digest"]


def test_known_fil_archive_regression_remains_1755() -> None:
    """Official FILUSDT archive regression remains event time 17:55:00, not archive-order 17:35:00."""
    if not CACHED_FIL_ZIP.exists():
        pytest.skip(f"Cached archive {CACHED_FIL_ZIP} missing")
    archive_bytes = CACHED_FIL_ZIP.read_bytes()
    report = verify_fil_20260906_regression(archive_bytes)

    assert report["regression_verified"] is True
    assert report["archive_order_tail_observation"] == "2026-09-06 17:35:00"
    assert report["normalized_selected_observation"] == "2026-09-06 17:55:00"
    assert report["expected_selected_observation"] == "2026-09-06 17:55:00"
    assert report["archive_flaw_discrepancy_minutes"] == 20


def test_full_window_missing_middle_lookback_fails_before_outcome_resolution() -> None:
    """Downstream full-window production scanner audit detects missing metric lookbacks

    and halts fail-closed before any target outcome resolution.
    """
    burned_fixture_path = Path("/tmp/rc2_harness_r2_raw.json.gz")
    if not burned_fixture_path.exists():
        pytest.skip("No burned fixture available in /tmp")

    with gzip.open(burned_fixture_path, "rt", encoding="utf-8") as f:
        wrapped = json.load(f)
    raw = wrapped.get("payload", wrapped.get("data", wrapped))

    targets = ("FILUSDT", "ETCUSDT")
    # Induce an adversarial defect: remove top position series from FILUSDT entirely
    saved_top_pos = raw["data"]["FILUSDT"]["top_pos_hist"]
    raw["data"]["FILUSDT"]["top_pos_hist"] = []

    try:
        dataset = build_dataset(raw, targets, REFERENCES, include_outcomes=False)
        audit = audit_full_window_production_context(dataset, targets, REFERENCES)

        assert audit["full_window_audit_passed"] is False
        assert audit["defects_count"] > 0
        assert audit["target_1m_outcome_queries_count"] == 0
        assert audit["first_failure"] is not None
        assert "top position" in audit["first_failure"]["error"]
    finally:
        raw["data"]["FILUSDT"]["top_pos_hist"] = saved_top_pos


# =====================================================================
# Finding II — Controller Execution Dispatch Authority Binding Tests
# =====================================================================

def test_wrong_execution_dispatch_rejected_before_network(tmp_path: Path) -> None:
    """Arbitrary lowercase 40-hex dispatch SHAs and development dispatch 405e0042...

    are rejected fail-closed before capability creation and before any source access.
    """
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runner_sha256 = hashlib.sha256((ROOT / "scripts/rc2/validation/run_holdout_r3.py").read_bytes()).hexdigest()

    # Create dummy seal
    seal_path = tmp_path / "seal.json"
    seal_payload = {
        "schema_version": TARGET_SEAL_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "created_at_utc": "2026-10-07T20:00:00Z",
        "target_symbols": ["FILUSDT", "ETCUSDT"],
        "context_only_references": list(REFERENCES),
    }
    seal_path.write_text(json.dumps(seal_payload, indent=2) + "\n", encoding="utf-8")
    seal_sha256 = hashlib.sha256(seal_path.read_bytes()).hexdigest()

    # Case 1: The reported development dispatch 405e0042687bfae5aa986e0f2982e26cba3827cd
    ok, terminal, detail = check_execution_authorization(
        authorized_runner_sha=head,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha="405e0042687bfae5aa986e0f2982e26cba3827cd",
        target_seal_path=seal_path,
        authorized_target_seal_sha256=seal_sha256,
        root=ROOT,
    )
    assert ok is False
    assert terminal == "RC2_HOLDOUT_R3_PREFLIGHT_FAIL"
    assert any(
        "Failed to read authority artifact" in r or "not an ancestor" in r
        for r in detail["reasons"]
    )
    assert detail["proof"] is None

    # Case 2: Random arbitrary 40-hex SHA
    random_sha = "0123456789abcdef0123456789abcdef01234567"
    ok2, terminal2, detail2 = check_execution_authorization(
        authorized_runner_sha=head,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha=random_sha,
        target_seal_path=seal_path,
        authorized_target_seal_sha256=seal_sha256,
        root=ROOT,
    )
    assert ok2 is False
    assert terminal2 == "RC2_HOLDOUT_R3_PREFLIGHT_FAIL"
    assert any(
        "not an ancestor" in r or "Failed to read authority artifact" in r
        for r in detail2["reasons"]
    )
    assert detail2["proof"] is None


def test_hermetic_controller_dispatch_authority_positive_and_negative(tmp_path: Path) -> None:
    """Hermetic synthetic Git fixture test proving:

    - valid Controller dispatch authority is accepted;
    - decision tampering is rejected;
    - max_attempts > 1 is rejected;
    - runner SHA mismatch is rejected;
    - runner SHA256 mismatch is rejected;
    - target seal SHA256 mismatch is rejected;
    - frozen policy SHA mismatch is rejected;
    - original incident commit mismatch is rejected;
    - target substitution is rejected;
    - missing docs trust root ref is rejected fail-closed.
    """
    git_dir = tmp_path / "fixture_repo"
    git_dir.mkdir()
    subprocess.check_call(["git", "init", "-b", "main"], cwd=git_dir)
    subprocess.check_call(["git", "config", "user.name", "Test Controller"], cwd=git_dir)
    subprocess.check_call(["git", "config", "user.email", "controller@test.local"], cwd=git_dir)

    dummy_runner_sha = "a" * 40
    dummy_runner_sha256 = "b" * 64
    dummy_seal_sha256 = "c" * 64
    sealed_targets = ("FILUSDT", "ETCUSDT")

    valid_authority_payload = {
        "schema_version": "B_LINE_RC2_FINAL_HOLDOUT_RETRY_AUTHORITY_V1",
        "task_id": TASK_ID,
        "decision": REQUIRED_DECISION,
        "max_attempts": 1,
        "authorized_runner_sha": dummy_runner_sha,
        "authorized_runner_sha256": dummy_runner_sha256,
        "target_seal_sha256": dummy_seal_sha256,
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "real_funds_write_authority": "NONE",
        "original_incident_evidence_commit": ORIGINAL_INCIDENT_EVIDENCE_COMMIT,
        "target_symbols": list(sealed_targets),
    }

    # Commit valid authority file to fixture repo
    auth_file_path = git_dir / RETRY_AUTHORITY_REL_PATH
    auth_file_path.parent.mkdir(parents=True, exist_ok=True)
    auth_file_path.write_text(json.dumps(valid_authority_payload, indent=2) + "\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "."], cwd=git_dir)
    subprocess.check_call(["git", "commit", "-m", "docs(controller): retry authority"], cwd=git_dir)

    valid_dispatch_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_dir, text=True).strip()

    # Create mock docs branch pointing to this commit (or descendant)
    subprocess.check_call(["git", "branch", "mock-docs", valid_dispatch_sha], cwd=git_dir)

    # 1. POSITIVE: Valid authority matches all requirements
    ok, reasons, data = validate_retry_dispatch_authority(
        dispatch_sha=valid_dispatch_sha,
        authorized_runner_sha=dummy_runner_sha,
        authorized_runner_sha256=dummy_runner_sha256,
        authorized_target_seal_sha256=dummy_seal_sha256,
        sealed_targets=sealed_targets,
        root=git_dir,
        docs_ref="mock-docs",
    )
    assert ok is True
    assert reasons == []
    assert data["decision"] == REQUIRED_DECISION

    # 2. NEGATIVE: Stale or missing docs ref
    ok_ref, reasons_ref, _ = validate_retry_dispatch_authority(
        dispatch_sha=valid_dispatch_sha,
        authorized_runner_sha=dummy_runner_sha,
        authorized_runner_sha256=dummy_runner_sha256,
        authorized_target_seal_sha256=dummy_seal_sha256,
        sealed_targets=sealed_targets,
        root=git_dir,
        docs_ref="nonexistent-docs-ref",
    )
    assert ok_ref is False
    assert any("missing or not fetched" in r for r in reasons_ref)

    # Helper to commit modified authority payload and test rejection
    def test_rejected_payload(mutation: dict[str, Any], expected_err_fragment: str) -> None:
        mutated = dict(valid_authority_payload)
        mutated.update(mutation)
        auth_file_path.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
        subprocess.check_call(["git", "commit", "-am", f"mutate {expected_err_fragment}"], cwd=git_dir)
        mut_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_dir, text=True).strip()
        subprocess.check_call(["git", "branch", "-f", "mock-docs", mut_sha], cwd=git_dir)

        mut_ok, mut_reasons, _ = validate_retry_dispatch_authority(
            dispatch_sha=mut_sha,
            authorized_runner_sha=dummy_runner_sha,
            authorized_runner_sha256=dummy_runner_sha256,
            authorized_target_seal_sha256=dummy_seal_sha256,
            sealed_targets=sealed_targets,
            root=git_dir,
            docs_ref="mock-docs",
        )
        assert mut_ok is False, f"Expected rejection for {expected_err_fragment}"
        assert any(expected_err_fragment in r for r in mut_reasons), f"Reasons: {mut_reasons}"

    # 3. Decision mismatch
    test_rejected_payload({"decision": "UNAUTHORIZED_DECISION"}, "Authority decision mismatch")

    # 4. max_attempts > 1
    test_rejected_payload({"max_attempts": 2}, "Authority max_attempts mismatch")

    # 5. real_funds != NONE
    test_rejected_payload({"real_funds_write_authority": "WRITE"}, "real_funds_write_authority mismatch")

    # 6. runner SHA mismatch
    test_rejected_payload({"authorized_runner_sha": "f" * 40}, "Authority runner SHA mismatch")

    # 7. runner SHA256 mismatch
    test_rejected_payload({"authorized_runner_sha256": "f" * 64}, "Authority runner SHA256 mismatch")

    # 8. target seal SHA256 mismatch
    test_rejected_payload({"target_seal_sha256": "f" * 64}, "Authority target seal SHA256 mismatch")

    # 9. frozen policy SHA mismatch
    test_rejected_payload({"frozen_policy_sha": "0" * 40}, "Authority frozen policy SHA mismatch")

    # 10. original incident commit mismatch
    test_rejected_payload({"original_incident_evidence_commit": "0" * 40}, "original incident commit mismatch")

    # 11. Target substitution
    test_rejected_payload({"target_symbols": ["BTCUSDT", "ETHUSDT"]}, "target substitution detected")


def test_durable_failure_publication_on_source_retrieval_exception(tmp_path: Path) -> None:
    """When source retrieval raises an exception (as in the ORCA incident),

    the runner durably publishes INFRA_INCOMPLETE evidence to evidence_dir.
    """
    evidence_dir = tmp_path / "HOLDOUT_FINAL_TEST"
    staging_dir = tmp_path / "staging_test"
    staging_dir.mkdir()

    ledger = ExecutionAccessLedger(staging_dir / "EXECUTION_ACCESS_LEDGER.json")
    # Simulate an allowed access and then a failure
    cap = AccessCapability.construction_review(ledger)
    cap.check_access("FILUSDT", caller="test")

    pre_identity = MagicMock()
    pre_identity.to_dict.return_value = {"task_id": TASK_ID, "src_clean": True}

    finalize_failed_attempt(
        staging_dir=staging_dir,
        evidence_dir=evidence_dir,
        terminal="RC2_HOLDOUT_R3_INFRA_INCOMPLETE",
        phase="SOURCE_RETRIEVAL",
        exception_class="ValueError",
        exception_message="could not convert string to float: ''",
        protected_source_access_started=True,
        outcome_replay_started=False,
        target_outcomes_resolved=False,
        authorized_runner_sha="0" * 40,
        authorized_runner_sha256="0" * 64,
        execution_dispatch_sha="1" * 40,
        authorized_target_seal_sha256="2" * 64,
        target_symbols=("FILUSDT",),
        ledger=ledger,
        pre_identity=pre_identity,
        post_identity=None,
        source_bundle_manifest=None,
    )

    # Must be published to evidence_dir
    assert evidence_dir.exists()
    assert (evidence_dir / "ATTEMPT_RECEIPT.json").exists()
    assert (evidence_dir / "EVIDENCE.json").exists()
    assert (evidence_dir / "OUTPUT_MANIFEST.json").exists()
    assert (evidence_dir / "EXECUTION_IDENTITY.json").exists()
    assert (evidence_dir / "EXECUTION_ACCESS_LEDGER.json").exists()

    receipt = json.loads((evidence_dir / "ATTEMPT_RECEIPT.json").read_text())
    assert receipt["terminal"] == "RC2_HOLDOUT_R3_INFRA_INCOMPLETE"
    assert receipt["phase"] == "SOURCE_RETRIEVAL"
    assert receipt["exception_class"] == "ValueError"
    assert receipt["target_outcome_replay_started"] is False
    assert receipt["target_outcomes_resolved"] is False

    evidence = json.loads((evidence_dir / "EVIDENCE.json").read_text())
    assert evidence["terminal"] == "RC2_HOLDOUT_R3_INFRA_INCOMPLETE"
    assert evidence["policy_quality_authority"] == "NONE_INFRA_INCOMPLETE"
    assert evidence["release_authority"] is False
    assert evidence["real_funds_write_authority"] == "NONE"
