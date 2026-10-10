"""Independent native regressions capture frozen implementation failures.

These passing audit tests prove the FAIL_HARD witnesses were reproduced; they
do not label the target secure. Linux ptrace must actually execute, never skip.
"""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/strategy_research/p2_s3a_independent_audit_r1"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("s3a_independent_harness", SCRIPTS / "harness.py")
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)
FIXTURES = json.loads((SCRIPTS / "fixtures.json").read_text())


@pytest.mark.parametrize("spec", FIXTURES["scenarios"], ids=lambda s: s["id"])
def test_live_native_counter_and_isolated_security_witness(spec):
    out = HARNESS.run_case(spec, FIXTURES)
    assert out["child_exit"] == 0
    assert out["assertion"] == "KERNEL_AND_INDEPENDENT_BOUNDARY_COUNTS_MATCH"
    obs = out["observation"]
    target = obs["target_receipt"]
    mode = spec["mode"]
    if mode == "normal":
        if spec["cap"] in (100, 27):
            assert target["allowed"]
            assert out["native_common_attempts"] == 36
            assert out["target_reported_attempts"] == 27
            assert out["native_common_minus_reported"] == 9
        elif spec["cap"] == 1:
            assert target["decision_code"] == "BUDGET_INSUFFICIENT_STOP"
            assert out["native_common_attempts"] == 0
        else:
            assert not target["allowed"]
            assert out["native_common_attempts"] > spec["cap"]
            assert out["target_reported_attempts"] <= spec["cap"]
    elif mode == "deep_cap100":
        assert target["allowed"]
        assert out["native_common_attempts"] == 144
        assert out["native_common_attempts"] > spec["cap"]
        assert out["target_reported_attempts"] == 27
    elif mode in ("missing_ancestor", "ancestor_symlink", "ancestor_nondirectory", "permission_eacces"):
        failures = [e for e in out["native_events"] if e["family"] == "open" and
                    e["path"] == "gate" and e["errno"]]
        expected_errno = {"missing_ancestor": errno.ENOENT, "permission_eacces": errno.EACCES,
                          "ancestor_symlink": errno.ENOTDIR,
                          "ancestor_nondirectory": errno.ENOTDIR}[mode]
        assert [e["errno"] for e in failures[:2]] == [expected_errno, expected_errno]
        assert not target["allowed"]
        assert out["native_common_minus_reported"] == 9
    elif mode in ("close_root_fault", "close_leaf_fault"):
        assert len(obs["actual_held_descriptors_after_target"]) == 1
        assert obs["snapshot_after_operation"]["open_fds_remaining"] == 0
        assert any(e["syscall"] == "close" and e["errno"] == errno.EBADF
                   for e in out["native_events"])
        assert any(e.get("audit_closed") for e in obs["excluded_auditor_cleanup"])
        if mode == "close_root_fault":
            assert target["unstructured_exception"] == "OSError"
        else:
            assert target["decision_code"] == "DENIED_FD_CLEANUP_CLOSE_FAILED"
    elif mode == "attestation_only":
        assert obs["scope"] == "GRANT_ATTESTATION_SETUP"
        assert target["custody_created"]
        assert out["native_common_attempts"] == 12
    elif mode == "self_minted_factory":
        assert target["allowed"]
        assert target["grant_token_semantics"] == "TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION"
    else:
        assert not target["allowed"]
    if mode not in ("close_root_fault", "close_leaf_fault"):
        assert not obs["actual_held_descriptors_after_target"]
    if mode in ("normal", "deep_cap100", "self_minted_factory") and target.get("allowed"):
        reads = [e for e in out["native_events"] if e["syscall"] == "pread64"]
        assert len(reads) == 2 and reads[0]["args"][2] == 8
        assert sum(e["returned"] for e in reads) <= 65544
        assert not any(e["syscall"] == "read" for e in out["native_events"])
        metadata = target["schema_metadata"]
        assert metadata["embedded_statistics_suppressed"]
        assert metadata["key_value_metadata_suppressed"]
        assert metadata["row_data_pages_read"] == 0
        for column in metadata["columns"]:
            assert column["statistics_suppressed"]
            assert not {"min", "max", "null_count", "distinct_count", "statistics"} & column.keys()
        assert "audit_marker" not in json.dumps(metadata)


def test_frozen_fixture_provenance_is_immutable_and_synthetic():
    content = (SCRIPTS / "fixtures.json").read_bytes()
    assert hashlib.sha256(content).hexdigest() == (SCRIPTS / "fixtures.sha256").read_text().strip()
    assert hashlib.sha256(bytes.fromhex(FIXTURES["parquet_hex"])).hexdigest() == FIXTURES["parquet_sha256"]
    assert len(FIXTURES["scenarios"]) >= 12


def test_github_original_receipt_not_borrowed_prose_is_source_authority():
    import subprocess

    commit = "c6823dbc46249cac43aa10400aacbbe9f4542410"
    path = "evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json"
    raw = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
    original = json.loads(raw)
    sizes = {x["file_rel_path"]: x["file_size_bytes"] for x in original["candidate_month_observations"]}
    sizes.update({x["rel_path"]: x["size_bytes"] for x in original["additional_target_observations"]
                  if x.get("is_regular")})
    assert "target_Checks" not in original
    assert len(sizes) == 13
    assert sizes["research/BTCUSDT/data_manifest.json"] == 45234
    assert sizes["research/BTCUSDT/funding_events.csv"] == 219066
    assert sizes == HARNESS.constants.VERIFIED_C6823DBC_FILE_SIZES_BYTES
