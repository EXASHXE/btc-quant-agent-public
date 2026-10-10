"""Adversarial mutation and security edge-case tests for P2 owner exact WSL root verifier."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Generator
from unittest import mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.strategy_research.p2_owner_root_metadata.cli import run_cli
from scripts.strategy_research.p2_owner_root_metadata.config import (
    APPROVED_MONTH_PARTITIONS,
    FilePresenceStatus,
    TerminalVerdict,
)
from scripts.strategy_research.p2_owner_root_metadata.probe import (
    OwnerRootProbe,
    ProbeBudgetExceededError,
    ProbeSecurityError,
)


@pytest.fixture
def mock_tree() -> Generator[str, None, None]:
    """Create a temporary synthetic data root representing owner data layout."""
    d = tempfile.mkdtemp(prefix="test_p2_adv_")
    try:
        for part in APPROVED_MONTH_PARTITIONS:
            month_dir = os.path.join(d, part["rel_dir"])
            os.makedirs(month_dir, exist_ok=True)
            with open(os.path.join(month_dir, "data.parquet"), "wb") as f:
                f.write(b"MOCK_PARQUET")

        perp_root = os.path.join(d, "research/BTCUSDT")
        os.makedirs(perp_root, exist_ok=True)
        with open(os.path.join(perp_root, "data_manifest.json"), "w") as f:
            f.write('{"mock": true}')
        with open(os.path.join(perp_root, "funding_events.csv"), "w") as f:
            f.write("mock_csv")

        for sub in ["mark_price", "funding", "klines"]:
            os.makedirs(os.path.join(perp_root, "raw", sub), exist_ok=True)

        spot_root = os.path.join(d, "research/BTCUSDT_SPOT")
        os.makedirs(os.path.join(spot_root, "1m"), exist_ok=True)
        with open(os.path.join(spot_root, "data_manifest.json"), "w") as f:
            f.write('{"spot": true}')

        cross_root = os.path.join(d, "research/cross_asset_1h")
        os.makedirs(cross_root, exist_ok=True)
        with open(os.path.join(cross_root, "ETHUSDT.parquet"), "wb") as f:
            f.write(b"MOCK_ETH")
        with open(os.path.join(cross_root, "basket_manifest.json"), "w") as f:
            f.write('{"basket": true}')

        v0319_root = os.path.join(d, "research/v0.3.19_official_derivatives")
        os.makedirs(v0319_root, exist_ok=True)
        with open(os.path.join(v0319_root, "hourly_inputs.parquet"), "wb") as f:
            f.write(b"MOCK_V0319")
        with open(os.path.join(v0319_root, "raw_data_manifest.json"), "w") as f:
            f.write('{"v0319": true}')

        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_adv_01_symlink_ancestor_stops_pipeline(mock_tree: str) -> None:
    """Symlink in custom ancestor chain terminates with P2_PROTECTION_OR_IDENTITY_STOP."""
    real_sub = os.path.join(mock_tree, "real_sub")
    link_sub = os.path.join(mock_tree, "link_sub")
    os.makedirs(real_sub, exist_ok=True)
    os.symlink(real_sub, link_sub)

    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    chain = [mock_tree, link_sub]
    ok = probe.verify_ancestors(custom_chain=chain)
    assert ok is False
    assert probe.counters.symlinks_encountered == 1


def test_adv_02_intermediate_symlink_at_1m_detected(mock_tree: str) -> None:
    """Intermediate symlink at research/BTCUSDT/1m is detected and rejected."""
    one_m_dir = os.path.join(mock_tree, "research/BTCUSDT/1m")
    shutil.rmtree(one_m_dir)
    outside_dir = os.path.join(mock_tree, "outside_1m")
    os.makedirs(outside_dir, exist_ok=True)
    os.symlink(outside_dir, one_m_dir)

    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    probe.scan_selected_months()

    assert probe.counters.symlinks_encountered >= 1
    assert any(m.status == FilePresenceStatus.SYMLINK_REJECTED.value for m in probe.month_observations)


def test_adv_03_intermediate_symlink_at_year_detected(mock_tree: str) -> None:
    """Intermediate symlink at year=2021 is detected and rejected."""
    year_dir = os.path.join(mock_tree, "research/BTCUSDT/1m/year=2021")
    shutil.rmtree(year_dir)
    outside_year = os.path.join(mock_tree, "outside_2021")
    os.makedirs(outside_year, exist_ok=True)
    os.symlink(outside_year, year_dir)

    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    probe.scan_selected_months()

    assert probe.counters.symlinks_encountered >= 1
    assert probe.month_observations[0].status == FilePresenceStatus.SYMLINK_REJECTED.value


def test_adv_04_intermediate_symlink_at_month_detected(mock_tree: str) -> None:
    """Intermediate symlink at month=03 is detected and rejected."""
    month_dir = os.path.join(mock_tree, "research/BTCUSDT/1m/year=2021/month=03")
    shutil.rmtree(month_dir)
    outside_month = os.path.join(mock_tree, "outside_month_03")
    os.makedirs(outside_month, exist_ok=True)
    os.symlink(outside_month, month_dir)

    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    probe.scan_selected_months()

    assert probe.counters.symlinks_encountered >= 1
    assert probe.month_observations[0].status == FilePresenceStatus.SYMLINK_REJECTED.value


def test_adv_05_symlink_leaf_parquet_stops_pipeline(mock_tree: str) -> None:
    """Symlink parquet file terminates with P2_PROTECTION_OR_IDENTITY_STOP."""
    p_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[0]["rel_dir"])
    p_file = os.path.join(p_dir, "data.parquet")
    os.remove(p_file)
    dummy_target = os.path.join(mock_tree, "dummy.parquet")
    with open(dummy_target, "wb") as f:
        f.write(b"DUMMY")
    os.symlink(dummy_target, p_file)

    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(probe, "verify_ancestors", lambda: True)
        verdict = probe.execute()
        assert verdict == TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
        assert probe.counters.symlinks_encountered >= 1


def test_adv_06_malicious_alternate_name_traversal_propagates(mock_tree: str) -> None:
    """Malicious alternate parquet name with traversal is detected and raises ProbeSecurityError."""
    month_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[0]["rel_dir"])
    os.remove(os.path.join(month_dir, "data.parquet"))
    # Create an entry whose name has traversal or symlink
    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    # Mock entry with malicious name
    fake_entry = mock.MagicMock()
    fake_entry.name = "../escape.parquet"
    fake_entry.path = os.path.join(month_dir, fake_entry.name)

    with (
        mock.patch("os.scandir") as mock_scandir,
        pytest.raises(ProbeSecurityError, match="Malicious parquet filename"),
    ):
        mock_scandir.return_value.__enter__.return_value = [fake_entry]
        probe.scan_selected_months()


def test_adv_07_malicious_alternate_name_protected_pattern_propagates(mock_tree: str) -> None:
    """Protected pattern in alternate parquet name raises ProbeSecurityError without swallowing."""
    month_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[0]["rel_dir"])
    os.remove(os.path.join(month_dir, "data.parquet"))
    with open(os.path.join(month_dir, "forward_2026_test.parquet"), "wb") as f:
        f.write(b"TRAP")

    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    with pytest.raises(ProbeSecurityError, match="Malicious parquet filename"):
        probe.scan_selected_months()


def test_adv_08_permission_error_is_never_absent(mock_tree: str) -> None:
    """PermissionError marks status as PERMISSION_DENIED and is never marked as ENOENT/missing."""
    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    with mock.patch("os.lstat", side_effect=PermissionError("Mock Permission Denied")):
        probe.scan_additional_targets()

    for obs in probe.target_observations:
        assert obs.status == FilePresenceStatus.PERMISSION_DENIED.value
        assert "Permission denied" in obs.notes


def test_adv_09_cap_limit_raising_within_alternate_probe(mock_tree: str) -> None:
    """Budget limit reached during alternate parquet probe propagates ProbeBudgetExceededError."""
    month_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[0]["rel_dir"])
    os.remove(os.path.join(month_dir, "data.parquet"))
    with open(os.path.join(month_dir, "alt_kline.parquet"), "wb") as f:
        f.write(b"ALT")

    # Set tight lstat cap
    probe = OwnerRootProbe(data_root=mock_tree, max_lstat=2, allow_custom_root=True)
    with pytest.raises(ProbeBudgetExceededError):
        probe.scan_selected_months()


def test_adv_10_fake_root_escaping_rejected(mock_tree: str) -> None:
    """Relative path escaping root raises ProbeSecurityError."""
    probe = OwnerRootProbe(data_root=mock_tree, allow_custom_root=True)
    with pytest.raises(ProbeSecurityError, match="traversal"):
        probe._verify_path_components_non_symlink("../../etc/passwd")


def test_adv_11_production_mode_rejects_unauthorized_root() -> None:
    """Production mode without allow_custom_root strictly rejects any non-whitelisted root."""
    with pytest.raises(ProbeSecurityError, match="Unauthorized data root"):
        OwnerRootProbe(data_root="/tmp/fake_root", allow_custom_root=False)


def test_adv_12_non_symlink_preflight_on_data_root(mock_tree: str) -> None:
    """Data root itself being a symlink terminates with P2_PROTECTION_OR_IDENTITY_STOP."""
    link_root = os.path.join(mock_tree, "symlink_root")
    os.symlink(mock_tree, link_root)

    probe = OwnerRootProbe(data_root=link_root, allow_custom_root=True)
    verdict = probe.execute()
    assert verdict == TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP
    assert "symbolic link" in (probe.stop_reason or "")


def test_adv_13_cli_execution_end_to_end(mock_tree: str) -> None:
    """CLI execution with --allow-custom-root generates all required JSON and MD artifacts."""
    out_evidence = os.path.join(mock_tree, "evidence")
    out_docs = os.path.join(mock_tree, "docs")

    test_args = [
        "cli.py",
        "--data-root",
        mock_tree,
        "--allow-custom-root",
        "--out-dir-evidence",
        out_evidence,
        "--out-dir-docs",
        out_docs,
    ]

    with pytest.MonkeyPatch.context() as m:
        m.setattr(OwnerRootProbe, "verify_ancestors", lambda self: True)
        m.setattr(sys, "argv", test_args)
        ret = run_cli()
        assert ret == 0

    receipt_file = os.path.join(out_evidence, "P2_OWNER_ROOT_EXACT_SCAN_RECEIPT.json")
    matrix_file = os.path.join(out_evidence, "P2_SELECTED_SOURCE_TYPE_AND_PERMISSIONS_MATRIX.json")
    report_file = os.path.join(out_docs, "P2_OWNER_ROOT_EXACT_METADATA_REPORT.md")

    assert os.path.exists(receipt_file)
    assert os.path.exists(matrix_file)
    assert os.path.exists(report_file)

    with open(receipt_file, "r", encoding="utf-8") as f:
        receipt_data = json.load(f)
    assert (
        receipt_data["terminal_verdict"]
        == TerminalVerdict.P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY.value
    )

    with open(matrix_file, "r", encoding="utf-8") as f:
        matrix_data = json.load(f)
    assert "source_classes" in matrix_data

    with open(report_file, "r", encoding="utf-8") as f:
        report_content = f.read()
    assert "Gemini P2 — Exact Owner-Supplied WSL Data Root" in report_content
    assert "P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY" in report_content
