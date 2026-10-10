"""Unit behavioral and falsification tests for P2 owner exact WSL root metadata verification."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Generator
from unittest import mock

import pytest

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.strategy_research.p2_owner_root_metadata.config import (
    APPROVED_MONTH_PARTITIONS,
    FilePresenceStatus,
    TerminalVerdict,
    is_path_protected,
    is_path_traversal,
)
from scripts.strategy_research.p2_owner_root_metadata.matrix import (
    build_candidate_month_matrix,
    build_source_type_and_permissions_matrix,
)
from scripts.strategy_research.p2_owner_root_metadata.probe import (
    OwnerRootProbe,
    ProbeBudgetExceededError,
    ProbeSecurityError,
)


@pytest.fixture
def mock_tree() -> Generator[str, None, None]:
    """Create a temporary synthetic data root representing owner data layout."""
    d = tempfile.mkdtemp(prefix="test_p2_owner_root_")
    try:
        # Build 6 approved month directories with data.parquet
        for part in APPROVED_MONTH_PARTITIONS:
            month_dir = os.path.join(d, part["rel_dir"])
            os.makedirs(month_dir, exist_ok=True)
            with open(os.path.join(month_dir, "data.parquet"), "wb") as f:
                f.write(b"MOCK_PARQUET_HEADER_BYTES_ONLY")

        # Build additional targets
        perp_root = os.path.join(d, "research/BTCUSDT")
        os.makedirs(perp_root, exist_ok=True)
        with open(os.path.join(perp_root, "data_manifest.json"), "w") as f:
            f.write('{"mock": true}')
        with open(os.path.join(perp_root, "funding_events.csv"), "w") as f:
            f.write("timestamp,funding_rate\n1600000000,0.0001\n")

        for sub in ["mark_price", "funding", "klines"]:
            os.makedirs(os.path.join(perp_root, "raw", sub), exist_ok=True)

        spot_root = os.path.join(d, "research/BTCUSDT_SPOT")
        os.makedirs(os.path.join(spot_root, "1m"), exist_ok=True)
        with open(os.path.join(spot_root, "data_manifest.json"), "w") as f:
            f.write('{"spot": true}')

        cross_root = os.path.join(d, "research/cross_asset_1h")
        os.makedirs(cross_root, exist_ok=True)
        with open(os.path.join(cross_root, "ETHUSDT.parquet"), "wb") as f:
            f.write(b"MOCK_ETH_PARQUET")
        with open(os.path.join(cross_root, "basket_manifest.json"), "w") as f:
            f.write('{"basket": true}')

        v0319_root = os.path.join(d, "research/v0.3.19_official_derivatives")
        os.makedirs(v0319_root, exist_ok=True)
        with open(os.path.join(v0319_root, "hourly_inputs.parquet"), "wb") as f:
            f.write(b"MOCK_V0319_PARQUET")
        with open(os.path.join(v0319_root, "raw_data_manifest.json"), "w") as f:
            f.write('{"v0319": true}')

        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_01_exact_allowed_six_dirs(mock_tree: str) -> None:
    """Test 1: Only the precisely allowlisted 6 months are inspected."""
    probe = OwnerRootProbe(data_root=mock_tree)
    probe.scan_selected_months()

    assert len(probe.month_observations) == 6
    labels = [m.label for m in probe.month_observations]
    expected_labels = ["2021-03", "2021-04", "2023-03", "2023-04", "2025-03", "2025-04"]
    assert labels == expected_labels
    for m in probe.month_observations:
        assert m.status == FilePresenceStatus.PRESENT_METADATA_ONLY.value
        assert m.file_name == "data.parquet"
        assert m.file_is_regular is True


def test_02_deny_2026(mock_tree: str) -> None:
    """Test 2: Probing year=2026 or 2026- months raises ProbeSecurityError."""
    assert is_path_protected("/data/research/BTCUSDT/1m/year=2026/month=01") is True
    assert is_path_protected("2026-03") is True

    probe = OwnerRootProbe(data_root=mock_tree)
    with pytest.raises(ProbeSecurityError, match="Protected holdout/excluded"):
        probe._safe_lstat(os.path.join(mock_tree, "research/BTCUSDT/1m/year=2026/month=03"))

    assert probe.counters.protected_body_or_partition_accesses == 1


def test_03_deny_forward_and_h39(mock_tree: str) -> None:
    """Test 3: Denies forward and h39/h39_validation directories."""
    assert is_path_protected("data/forward/BTCUSDT") is True
    assert is_path_protected("data/research/h39_validation") is True
    assert is_path_protected("/root/workspace/Quant-agent-sanitized") is True

    probe = OwnerRootProbe(data_root=mock_tree)
    with pytest.raises(ProbeSecurityError):
        probe._safe_lstat(os.path.join(mock_tree, "forward/BTCUSDT"))

    with pytest.raises(ProbeSecurityError):
        probe._safe_lstat(os.path.join(mock_tree, "research/h39_validation"))


def test_04_deny_traversal(mock_tree: str) -> None:
    """Test 4: Denies directory traversal attempts using .."""
    assert is_path_traversal("research/BTCUSDT/../../etc/passwd") is True
    assert is_path_traversal("research/BTCUSDT/1m/data.parquet") is False

    probe = OwnerRootProbe(data_root=mock_tree)
    with pytest.raises(ProbeSecurityError, match="traversal"):
        probe._safe_lstat(os.path.join(mock_tree, "research/../research/BTCUSDT"))


def test_05_deny_symlink_in_root_or_leaf(mock_tree: str) -> None:
    """Test 5: Symlinks in ancestors or leaf files are detected and rejected."""
    # Replace a month directory with a symlink to another directory
    target_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[0]["rel_dir"])
    shutil.rmtree(target_dir)
    real_target = os.path.join(mock_tree, "temp_real_dir")
    os.makedirs(real_target, exist_ok=True)
    os.symlink(real_target, target_dir)

    probe = OwnerRootProbe(data_root=mock_tree)
    probe.scan_selected_months()

    first_obs = probe.month_observations[0]
    assert first_obs.dir_is_symlink is True
    assert first_obs.status == FilePresenceStatus.SYMLINK_REJECTED.value
    assert probe.counters.symlinks_encountered >= 1


def test_06_capped_dir_entries_and_total_calls(mock_tree: str) -> None:
    """Test 6: Capped dir entries and total lstat calls raise budget exceeded if breached."""
    # Set probe with max_lstat=3
    probe = OwnerRootProbe(data_root=mock_tree, max_lstat=3)
    with pytest.raises(ProbeBudgetExceededError, match="MAX_LSTAT cap"):
        for _ in range(5):
            probe._safe_lstat(mock_tree)


def test_07_missing_vs_denied_treatment(mock_tree: str) -> None:
    """Test 7: Distinguishes ENOENT missing target from PROTECTED_EXCLUDED without false claims."""
    probe = OwnerRootProbe(data_root=mock_tree)

    # Missing target
    missing_path = os.path.join(mock_tree, "research/BTCUSDT/1m/year=2021/month=99")
    with pytest.raises(FileNotFoundError):
        probe._safe_lstat(missing_path)

    # Protected target
    protected_path = os.path.join(mock_tree, "research/BTCUSDT/1m/year=2026/month=01")
    with pytest.raises(ProbeSecurityError):
        probe._safe_lstat(protected_path)


def test_08_no_body_opens(mock_tree: str) -> None:
    """Test 8: Strict zero-open policy; no file descriptors opened for reading market data."""
    probe = OwnerRootProbe(data_root=mock_tree)
    with mock.patch("builtins.open", wraps=open) as mock_open:
        probe.scan_selected_months()
        probe.scan_additional_targets()
        # Ensure open was never called on any file under mock_tree
        for call_args in mock_open.call_args_list:
            called_path = str(call_args[0][0])
            assert not called_path.startswith(mock_tree), f"Forbidden open() on {called_path}"

    assert probe.counters.real_data_body_bytes_read == 0
    assert probe.counters.parquet_opens == 0
    assert probe.counters.csv_opens == 0


def test_09_spot_perp_distinction(mock_tree: str) -> None:
    """Test 9: Explicit separation and tagging of spot vs perpetual datasets."""
    probe = OwnerRootProbe(data_root=mock_tree)
    probe.scan_additional_targets()

    spot_targets = [t for t in probe.target_observations if t.is_spot]
    perp_targets = [t for t in probe.target_observations if not t.is_spot]

    assert len(spot_targets) >= 2
    for st in spot_targets:
        assert "SPOT" in st.rel_path

    for pt in perp_targets:
        assert "SPOT" not in pt.rel_path


def test_10_mark_funding_parent_cannot_be_deemed_true_minute_pit(mock_tree: str) -> None:
    """Test 10: Parent directory presence does not prove continuous true 1m PIT."""
    probe = OwnerRootProbe(data_root=mock_tree)
    probe.scan_additional_targets()

    raw_mark = next(t for t in probe.target_observations if t.target_id == "btc_perp_raw_mark_price_parent")
    raw_funding = next(t for t in probe.target_observations if t.target_id == "btc_perp_raw_funding_parent")

    assert raw_mark.proves_minute_pit is False
    assert raw_funding.proves_minute_pit is False
    assert "NOT prove" in raw_mark.notes


def test_11_expected_name_mismatch_handling(mock_tree: str) -> None:
    """Test 11: If data.parquet is absent, scandir finds alternative parquet basename without opening."""
    # In month 2021-03, rename data.parquet to btc_202103_kline.parquet
    month_dir = os.path.join(mock_tree, "research/BTCUSDT/1m/year=2021/month=03")
    old_p = os.path.join(month_dir, "data.parquet")
    new_p = os.path.join(month_dir, "btc_202103_kline.parquet")
    os.rename(old_p, new_p)

    probe = OwnerRootProbe(data_root=mock_tree)
    probe.scan_selected_months()

    first_obs = probe.month_observations[0]
    assert first_obs.status == FilePresenceStatus.PRESENT_METADATA_ONLY.value
    assert first_obs.file_name == "btc_202103_kline.parquet"
    assert "Alternate parquet name" in first_obs.notes
    assert probe.counters.dir_list_calls == 1


def test_12_matrix_generation_and_falsification_structure(mock_tree: str) -> None:
    """Test 12: Matrix generation correctly categorizes rows and unexecuted readiness checks."""
    probe = OwnerRootProbe(data_root=mock_tree)
    probe.scan_selected_months()
    probe.scan_additional_targets()

    month_matrix = build_candidate_month_matrix(probe.month_observations)
    assert month_matrix["total_approved_months"] == 6
    assert month_matrix["all_selected_files_present_metadata_only"] is True

    source_matrix = build_source_type_and_permissions_matrix(month_matrix, probe.target_observations)
    assert len(source_matrix["source_classes"]) >= 6
    assert len(source_matrix["next_bounded_readiness_checks"]) == 5

    # Check the required BTC-only formula in Check E
    check_e = next(c for c in source_matrix["next_bounded_readiness_checks"] if c["check_id"].startswith("CHECK_E"))
    assert "100% single asset exposure >60% ceiling" in check_e["description"]
    assert "NOT '1/3 assets 33% below >=60% positive support'" in check_e["description"]
