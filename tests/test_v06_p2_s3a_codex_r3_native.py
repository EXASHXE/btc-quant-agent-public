"""R3 independent native OS regression cases on invented /tmp Parquet fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.strategy_research.p2_s3_footer_reader.constants import (
    VERIFIED_C6823DBC_FILE_SIZES_BYTES,
)
from scripts.strategy_research.p2_s3_footer_reader.errors import ByteBudgetExceededError
from scripts.strategy_research.p2_s3_footer_reader.fd_syscall_wrapper import (
    MeteredPosixSyscallWrapper,
)
from scripts.strategy_research.p2_s3_footer_reader.r3_oracle import (
    BoundaryObserver,
    assert_case_contract,
    load_frozen_fixture,
    run_case,
    run_constructor_denial,
    run_cross_fork_prepared_grant,
    run_prepared_platform_denial,
    run_second_use_or_retune,
)

_CASES = load_frozen_fixture()["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_one_native_synthetic_scenario(case: dict[str, object]) -> None:
    result = run_case(case)
    assert_case_contract(result)
    events = result["native_core_events"]
    assert not any("Quant-agent/data" in str(event.get("path")) for event in events)
    assert not any("2026-02" in str(event.get("path")) for event in events)
    if case["kind"] == "normal" and case["cap"] == 100 and case["depth"] <= 5:
        assert result["native_core_total"] > 0
        assert result["observation"]["receipt"]["allowed"] is True
    if case["depth"] == 36:
        assert result["native_core_total"] <= 100
        assert result["observation"]["receipt"]["allowed"] is False
    if case["kind"] in {"missing_ancestor", "permission_eacces", "nondirectory_ancestor"}:
        expected_errno = {"missing_ancestor": 2, "permission_eacces": 13,
                          "nondirectory_ancestor": 20}[str(case["kind"])]
        failed = [event for event in events if event["family"] == "open"
                  and event["errno"] == expected_errno]
        assert failed
        assert len({(event["path"], event["arg2"]) for event in failed}) == len(failed)


def test_frozen_fixture_digest_and_case_independence() -> None:
    fixture = load_frozen_fixture()
    ids = [case["id"] for case in fixture["cases"]]
    assert len(ids) >= 20
    assert len(ids) == len(set(ids))
    assert len(bytes.fromhex(fixture["parquet_hex"])) == 1009
    assert fixture["parquet_sha256"] == hashlib.sha256(
        bytes.fromhex(fixture["parquet_hex"])
    ).hexdigest()


def test_65545th_requested_byte_denied_before_native_pread(tmp_path: Path) -> None:
    path = tmp_path / "invented_bytes_only"
    path.write_bytes(b"X" * 65_545)
    fd = os.open(path, os.O_RDONLY)
    wrapper = MeteredPosixSyscallWrapper(max_attempted_fs_calls=100)
    try:
        with BoundaryObserver() as observer:
            assert len(wrapper.pread_bytes(fd, 8, 0, is_trailer=True)) == 8
            assert len(wrapper.pread_bytes(fd, 65_536, 8, is_trailer=False)) == 65_536
            with pytest.raises(ByteBudgetExceededError):
                wrapper.pread_bytes(fd, 1, 65_544, is_trailer=False)
        reads = [event for event in observer.events if event["family"] == "pread"]
        assert len(reads) == 2
        assert sum(event["requested"] for event in reads) == 65_544
    finally:
        os.close(fd)


@pytest.mark.parametrize("kind,family", [
    ("native_unknown_open_ebadf", "open"),
    ("native_pread_ebadf", "pread"),
])
def test_native_ebadf_faults_are_structured(kind: str, family: str) -> None:
    # The parquet bytes remain the frozen fixture; only an OS argument is substituted.
    result = run_case({"id": kind, "kind": kind, "depth": 1, "cap": 100})
    assert_case_contract(result)
    events = result["native_core_events"]
    faults = [event for event in events if event["family"] == family and event["errno"] == 9]
    assert len(faults) == 1
    assert result["observation"]["receipt"]["allowed"] is False


@pytest.mark.parametrize("kind", ["reuse", "retune_cap", "retune_cap101", "retune_bytes"])
def test_one_shot_grant_cannot_be_reused_or_retuned(kind: str) -> None:
    result = run_second_use_or_retune(kind)
    assert result["child_exit_code"] == 0
    assert result["native_core_total"] == 0
    assert result["native_noncore_fs_events"] == []
    assert result["observation"]["python_boundary_events"] == []
    assert result["observation"]["physically_held_fds_after_reader"] == []
    receipt = result["observation"]["receipt"]
    assert receipt["allowed"] is False
    assert receipt["syscall_accounting"]["max_attempted_fs_calls"] == 100
    assert receipt["syscall_accounting"]["reader_attempted_fs_calls"] == 0
    if kind == "reuse":
        assert result["observation"]["first_receipt"]["allowed"] is True
        assert receipt["syscall_accounting"]["preparation_attempted_fs_calls"] == 0
    else:
        assert receipt["syscall_accounting"]["preparation_attempted_fs_calls"] > 0


def test_parent_prepared_grant_cannot_be_consumed_across_fork() -> None:
    result = run_cross_fork_prepared_grant()
    child = result["child"]
    assert child["child_exit_code"] == 0
    assert child["native_core_total"] == 0
    assert child["native_noncore_fs_events"] == []
    observation = child["observation"]
    assert observation["python_boundary_events"] == []
    assert observation["physically_held_fds_after_reader"] == []
    receipt = observation["receipt"]
    assert receipt["allowed"] is False
    assert receipt["syscall_accounting"]["attempted_fs_calls_total"] == 0
    assert receipt["syscall_accounting"]["open_fds_remaining"] == 0
    assert result["parent_receipt"]["allowed"] is True


def test_r2_matched_shallow_geometry_accounts_for_preparation() -> None:
    result = run_case({"id": "matched_r2_shallow", "kind": "normal", "depth": 0, "cap": 100})
    assert_case_contract(result)
    accounting = result["observation"]["receipt"]["syscall_accounting"]
    assert result["native_core_total"] == 50
    assert accounting["attempted_fs_calls_total"] == 50
    assert accounting["preparation_attempted_fs_calls"] == 13
    assert accounting["reader_attempted_fs_calls"] == 37
    assert result["observation"]["receipt"]["allowed"] is True


@pytest.mark.parametrize("kind", ["missing_pread", "invalid_101_call_budget"])
def test_constructor_denial_has_structured_zero_fs_receipt(kind: str) -> None:
    result = run_constructor_denial(kind)
    assert result["child_exit_code"] == 0
    assert result["native_core_total"] == 0
    assert result["native_noncore_fs_events"] == []
    observation = result["observation"]
    assert "uncaught" not in observation
    assert observation["python_boundary_events"] == []
    assert observation["physically_held_fds_after_reader"] == []
    receipt = observation["receipt"]
    assert receipt["allowed"] is False
    accounting = receipt["syscall_accounting"]
    assert accounting["attempted_fs_calls_total"] == 0
    assert accounting["open_fds_remaining"] == 0
    assert accounting["close_complete"] is True


def test_prepared_grant_platform_failure_reports_preparation_native_calls() -> None:
    result = run_prepared_platform_denial()
    assert result["child_exit_code"] == 0
    observation = result["observation"]
    assert "uncaught" not in observation
    assert observation["physically_held_fds_after_reader"] == []
    receipt = observation["receipt"]
    accounting = receipt["syscall_accounting"]
    assert receipt["allowed"] is False
    assert result["native_core_total"] == 16
    assert result["native_core_total"] == accounting["attempted_fs_calls_total"]
    assert sum(event["family"] in {"open", "fstat", "pread", "close"}
               for event in observation["python_boundary_events"]) == 16
    assert accounting["preparation_attempted_fs_calls"] == 16
    assert accounting["reader_attempted_fs_calls"] == 0
    assert accounting["close_complete"] is True


def test_original_git_pinned_13_regular_file_sizes_unchanged() -> None:
    """Git object metadata only; never stat or read the original owner tree."""
    repo = Path(__file__).resolve().parents[1]
    receipt_path = "evidence/v0.6/b_line/p2_owner_root_metadata_r1/P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json"
    raw = subprocess.check_output(
        ["git", "show", f"c6823dbc46249cac43aa10400aacbbe9f4542410:{receipt_path}"],
        cwd=repo,
    )
    original = json.loads(raw)
    regular = {
        row["file_rel_path"]: row["file_size_bytes"]
        for row in original["candidate_month_observations"]
        if row.get("file_is_regular") is True
    }
    regular.update({
        row["rel_path"]: row["size_bytes"]
        for row in original["additional_target_observations"]
        if row.get("is_regular") is True
    })
    assert len(regular) == 13
    assert regular["research/BTCUSDT/data_manifest.json"] == 45234
    assert regular["research/BTCUSDT/funding_events.csv"] == 219066
    assert regular == VERIFIED_C6823DBC_FILE_SIZES_BYTES
