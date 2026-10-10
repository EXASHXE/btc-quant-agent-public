"""Adversarial mutation and security edge-case tests for P2 owner exact WSL root verifier."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Generator

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.strategy_research.p2_owner_root_metadata.cli import run_cli
from scripts.strategy_research.p2_owner_root_metadata.config import (
    APPROVED_MONTH_PARTITIONS,
    TerminalVerdict,
)
from scripts.strategy_research.p2_owner_root_metadata.probe import OwnerRootProbe


@pytest.fixture
def mock_tree() -> Generator[str, None, None]:
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

    probe = OwnerRootProbe(data_root=mock_tree)
    chain = [mock_tree, link_sub]
    ok = probe.verify_ancestors(custom_chain=chain)
    assert ok is False
    assert probe.counters.symlinks_encountered == 1


def test_adv_02_symlink_parquet_stops_pipeline(mock_tree: str) -> None:
    """Symlink parquet file terminates with P2_PROTECTION_OR_IDENTITY_STOP."""
    # Replace data.parquet with symlink
    p_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[0]["rel_dir"])
    p_file = os.path.join(p_dir, "data.parquet")
    os.remove(p_file)
    dummy_target = os.path.join(mock_tree, "dummy.parquet")
    with open(dummy_target, "wb") as f:
        f.write(b"DUMMY")
    os.symlink(dummy_target, p_file)

    probe = OwnerRootProbe(data_root=mock_tree)
    # Mock ancestor check to pass
    with pytest.MonkeyPatch.context() as m:
        m.setattr(probe, "verify_ancestors", lambda: True)
        verdict = probe.execute()
        assert verdict == TerminalVerdict.P2_PROTECTION_OR_IDENTITY_STOP


def test_adv_03_missing_root_returns_not_present() -> None:
    """Non-existent root returns P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH."""
    non_existent = "/non/existent/path/for/quant/test"
    probe = OwnerRootProbe(data_root=non_existent)
    verdict = probe.execute()
    assert verdict == TerminalVerdict.P2_OWNER_ROOT_NOT_PRESENT_AT_EXACT_PATH


def test_adv_04_incomplete_files_returns_incomplete(mock_tree: str) -> None:
    """If one month is missing, verdict is P2_OWNER_ROOT_PRESENT_BUT_SELECTED_FILES_INCOMPLETE."""
    # Remove the last month directory
    last_dir = os.path.join(mock_tree, APPROVED_MONTH_PARTITIONS[-1]["rel_dir"])
    shutil.rmtree(last_dir)

    probe = OwnerRootProbe(data_root=mock_tree)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(probe, "verify_ancestors", lambda: True)
        verdict = probe.execute()
        assert verdict == TerminalVerdict.P2_OWNER_ROOT_PRESENT_BUT_SELECTED_FILES_INCOMPLETE
        assert "2025-04" in (probe.stop_reason or "")


def test_adv_05_cli_execution_end_to_end(mock_tree: str) -> None:
    """CLI execution generates all required JSON and MD artifacts with valid JSON syntax."""
    out_evidence = os.path.join(mock_tree, "evidence")
    out_docs = os.path.join(mock_tree, "docs")

    test_args = [
        "cli.py",
        "--data-root",
        mock_tree,
        "--out-dir-evidence",
        out_evidence,
        "--out-dir-docs",
        out_docs,
    ]

    with pytest.MonkeyPatch.context() as m:
        # Patch verify_ancestors to pass on temp mock directory
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
    assert receipt_data["terminal_verdict"] == TerminalVerdict.P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY.value

    with open(matrix_file, "r", encoding="utf-8") as f:
        matrix_data = json.load(f)
    assert "source_classes" in matrix_data

    with open(report_file, "r", encoding="utf-8") as f:
        report_content = f.read()
    assert "Gemini P2 — Exact Owner-Supplied WSL Data Root" in report_content
    assert "P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY" in report_content
