"""Unit behavioral tests for P2 bounded metadata root locator."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from collections.abc import Generator
from unittest import mock

import pytest

# Ensure repository root is on sys.path without creating foreign __init__.py files
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.strategy_research.p2_metadata_locator.config import (
    SELECTED_SAFE_MONTHS,
    CoverageStatus,
    RootCertainty,
    SourceRole,
    is_path_protected_holdout,
)
from scripts.strategy_research.p2_metadata_locator.matrix import generate_coverage_matrix
from scripts.strategy_research.p2_metadata_locator.scanner import MetadataScanner


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    d = tempfile.mkdtemp(prefix="test_p2_locator_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_01_depth_exhaustion_stops_safely(temp_dir: str) -> None:
    """Test 1: Recursion stops strictly at MAX_DEPTH without exploring deeper."""
    # Create directory tree of depth 7
    curr = temp_dir
    for i in range(1, 8):
        curr = os.path.join(curr, f"level_{i}")
        os.makedirs(curr, exist_ok=True)
        with open(os.path.join(curr, f"file_{i}.txt"), "w") as f:
            f.write("test")

    scanner = MetadataScanner(candidate_roots=[temp_dir], max_depth=3)
    ev = scanner.evaluate_candidate(temp_dir)
    # scanner depth should not exceed 3
    assert scanner.counters.depth_reached <= 3
    # Subdirectories found should only go up to depth 3
    for s in ev.subdirectories_found:
        rel = os.path.relpath(s, temp_dir)
        parts = rel.split(os.sep)
        assert len(parts) <= 3, f"Depth exceeded 3: {rel}"


def test_02_entry_cap_exhaustion_stops_safely(temp_dir: str) -> None:
    """Test 2: Scanner terminates cleanly when MAX_DIR_ENTRIES is reached."""
    # Create 30 fake files
    for i in range(30):
        with open(os.path.join(temp_dir, f"dummy_{i:02d}.dat"), "w") as f:
            f.write("data")

    scanner = MetadataScanner(candidate_roots=[temp_dir], max_dir_entries=10)
    receipt = scanner.run()
    assert receipt.budget_exhausted is True
    assert scanner.counters.dir_entries_scanned == 10
    assert "DIR_ENTRIES_CAP_REACHED" in (receipt.stop_reason or "")


def test_03_lstat_cap_exhaustion_stops_safely(temp_dir: str) -> None:
    """Test 3: Scanner terminates cleanly when MAX_LSTAT is reached."""
    for i in range(20):
        with open(os.path.join(temp_dir, f"file_{i:02d}.parquet"), "w") as f:
            f.write("mock")

    scanner = MetadataScanner(candidate_roots=[temp_dir], max_lstat=5)
    receipt = scanner.run()
    assert receipt.budget_exhausted is True
    assert scanner.counters.lstat_calls == 5
    assert "LSTAT_CAP_REACHED" in (receipt.stop_reason or "")


def test_04_symlink_encountered_and_zero_followed(temp_dir: str) -> None:
    """Test 4: Symlinks are encountered and counted, but NEVER followed (MAX_SYMLINK_FOLLOW=0)."""
    target_dir = os.path.join(temp_dir, "real_target")
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "target_file.txt"), "w") as f:
        f.write("content")

    link_path = os.path.join(temp_dir, "symlink_dir")
    try:
        os.symlink(target_dir, link_path)
    except OSError:
        pytest.skip("Symlink creation not supported on this filesystem")

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    receipt = scanner.run()
    assert receipt.terminal_verdict is not None
    assert scanner.counters.symlinks_encountered >= 1
    assert scanner.counters.symlinks_followed == 0


def test_05_symlink_to_restricted_path_rejected(temp_dir: str) -> None:
    """Test 5: Symlink pointing to restricted or external paths is rejected without traversal."""
    link_path = os.path.join(temp_dir, "link_to_etc")
    try:
        os.symlink("/etc", link_path)
    except OSError:
        pytest.skip("Symlink creation not supported")

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    ev = scanner.evaluate_candidate(temp_dir)
    assert scanner.counters.symlinks_encountered >= 1
    assert scanner.counters.symlinks_followed == 0
    # None of /etc contents should be in subdirectories
    assert not any("/etc" in s for s in ev.subdirectories_found)


def test_06_hidden_folder_excluded_without_entering(temp_dir: str) -> None:
    """Test 6: Hidden dot-directories (.git, .cache, etc.) are excluded without entering."""
    hidden = os.path.join(temp_dir, ".git")
    os.makedirs(hidden, exist_ok=True)
    with open(os.path.join(hidden, "HEAD"), "w") as f:
        f.write("ref: refs/heads/main")

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    ev = scanner.evaluate_candidate(temp_dir)
    assert scanner.counters.hidden_paths_skipped >= 1
    # Hidden folder should not be descended into
    assert not any(".git" in s for s in ev.subdirectories_found)


def test_07_protected_feb_apr_2026_excluded(temp_dir: str) -> None:
    """Test 7: Protected holdout [2026-02-01, 2026-08-01) is detected and excluded without entering."""
    # Create protected 2026-02 holdout folder
    protected_sub = os.path.join(temp_dir, "1m", "year=2026", "month=02")
    os.makedirs(protected_sub, exist_ok=True)
    with open(os.path.join(protected_sub, "data.parquet"), "w") as f:
        f.write("protected_bytes")

    assert is_path_protected_holdout(protected_sub) is True

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    ev = scanner.evaluate_candidate(temp_dir)
    assert scanner.counters.protected_paths_excluded >= 1
    assert scanner.counters.protected_body_or_partition_accesses == 0
    # The protected subfolder must not appear in traversed subdirs
    assert not any("month=02" in s for s in ev.subdirectories_found)


def test_08_repo_worktree_and_foreign_repo_excluded(temp_dir: str) -> None:
    """Test 8: Foreign worktrees and parallel task folders are strictly excluded."""
    foreign_dir = os.path.join(temp_dir, "postp1-sol61-opportunity-science-r1")
    os.makedirs(foreign_dir, exist_ok=True)
    with open(os.path.join(foreign_dir, "sol_file.txt"), "w") as f:
        f.write("sol")

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    ev = scanner.evaluate_candidate(temp_dir)
    # Foreign worktree should not be descended into
    assert not any("postp1-sol61-opportunity-science-r1" in s for s in ev.subdirectories_found)


def test_09_mount_escape_and_forbidden_roots_rejected() -> None:
    """Test 9: Explicit forbidden roots (/, /proc, /sys, /etc) are immediately rejected."""
    for fb in ["/", "/proc", "/sys", "/dev", "/etc"]:
        scanner = MetadataScanner(candidate_roots=[fb])
        ev = scanner.evaluate_candidate(fb)
        assert ev.ownership_authorized is False
        assert ev.certainty == RootCertainty.ROOT_UNKNOWN
        assert "FORBIDDEN" in (ev.rejection_reason or "")


def test_10_enoent_vs_eacces_handled_gracefully(temp_dir: str) -> None:
    """Test 10: Non-existent paths (ENOENT) and permission denials (EACCES) handled gracefully."""
    # Non-existent path
    non_existent = os.path.join(temp_dir, "does_not_exist_abc123")
    scanner = MetadataScanner(candidate_roots=[non_existent])
    ev = scanner.evaluate_candidate(non_existent)
    assert ev.exists is False
    assert ev.certainty == RootCertainty.ROOT_UNKNOWN

    # Simulated permission error
    with mock.patch("os.listdir", side_effect=PermissionError("Permission denied")):
        scanner2 = MetadataScanner(candidate_roots=[temp_dir])
        ev2 = scanner2.evaluate_candidate(temp_dir)
        assert scanner2.counters.permission_denied_entries >= 1
        assert ev2.certainty == RootCertainty.ROOT_UNKNOWN


def test_11_1m_kline_vs_true_1m_mark_distinction(temp_dir: str) -> None:
    """Test 11: 1m Kline and true 1m Mark price are treated as strictly distinct roles."""
    # Build fake safe partitions for BTC
    for month in SELECTED_SAFE_MONTHS:
        y, m = month.split("-")
        p = os.path.join(temp_dir, "1m", f"year={y}", f"month={m}")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "data.parquet"), "w") as f:
            f.write("kline_bytes")

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    receipt = scanner.run()
    assert receipt.confirmed_root == temp_dir

    matrix = generate_coverage_matrix(receipt)
    # Check BTC rows for Kline vs Mark
    kline_cells = [c for c in matrix.grid if c.symbol == "BTCUSDT" and c.role == SourceRole.KLINE_1M]
    mark_cells = [c for c in matrix.grid if c.symbol == "BTCUSDT" and c.role == SourceRole.TRUE_MARK_1M]

    assert all(c.status == CoverageStatus.PRESENT_METADATA_ONLY for c in kline_cells)
    # True 1m Mark price must NOT be marked PRESENT just because 1m Kline exists
    assert all(c.status == CoverageStatus.UNKNOWN_UNPROBED for c in mark_cells)


def test_12_eight_original_asset_period_boundaries(temp_dir: str) -> None:
    """Test 12: Asset/period boundaries for BTC, ETH, and SOL are distinct and not conflated."""
    scanner = MetadataScanner(candidate_roots=[temp_dir])
    receipt = scanner.run()
    matrix = generate_coverage_matrix(receipt)

    btc_cells = [c for c in matrix.grid if c.symbol == "BTCUSDT"]
    eth_cells = [c for c in matrix.grid if c.symbol == "ETHUSDT"]
    sol_cells = [c for c in matrix.grid if c.symbol == "SOLUSDT"]

    assert len(btc_cells) == len(SELECTED_SAFE_MONTHS) * 5
    assert len(eth_cells) == len(SELECTED_SAFE_MONTHS) * 5
    assert len(sol_cells) == len(SELECTED_SAFE_MONTHS) * 5

    # ETH and SOL must report UNKNOWN_UNPROBED
    assert all(c.status == CoverageStatus.UNKNOWN_UNPROBED for c in eth_cells)
    assert all(c.status == CoverageStatus.UNKNOWN_UNPROBED for c in sol_cells)


def test_13_zero_content_reads_strictly_enforced(temp_dir: str) -> None:
    """Test 13: File bodies are never opened or read (MAX_REAL_DATA_BODY_BYTES=0)."""
    # Create fake safe partitions
    for month in SELECTED_SAFE_MONTHS:
        y, m = month.split("-")
        p = os.path.join(temp_dir, "1m", f"year={y}", f"month={m}")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "data.parquet"), "w") as f:
            f.write("unopened_market_data_bytes_1234567890")

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    receipt = scanner.run()

    assert receipt.counters.real_data_body_bytes_read == 0
    assert receipt.counters.protected_body_or_partition_accesses == 0
    assert receipt.counters.remote_market_calls == 0


def test_14_deterministic_traversal_order(temp_dir: str) -> None:
    """Test 14: Traversal order across directory entries is strictly deterministic (sorted)."""
    names = ["zeta", "alpha", "omega", "beta", "gamma"]
    for n in names:
        os.makedirs(os.path.join(temp_dir, n), exist_ok=True)

    scanner = MetadataScanner(candidate_roots=[temp_dir])
    ev = scanner.evaluate_candidate(temp_dir)
    basenames = [os.path.basename(s) for s in ev.subdirectories_found]
    assert basenames == sorted(names)


def test_15_selected_partition_lstat_cap(temp_dir: str) -> None:
    """Test 15: Selected partition lstat calls respect max_selected_partition_lstat."""
    scanner = MetadataScanner(candidate_roots=[temp_dir], max_selected_partition_lstat=2)
    ev = scanner.evaluate_candidate(temp_dir)
    assert scanner.counters.selected_partition_lstat_calls <= 2
    probes = ev.safe_partitions_checked
    capped_count = sum(1 for p in probes.values() if p.reason == "BUDGET_CAP_REACHED")
    assert capped_count == len(SELECTED_SAFE_MONTHS) - 2


def test_16_root_candidate_certainty_levels(temp_dir: str) -> None:
    """Test 16: Certainty levels: CONFIRMED vs CANDIDATE_UNVERIFIED vs UNKNOWN."""
    # 1. Empty folder -> UNKNOWN
    s1 = MetadataScanner(candidate_roots=[temp_dir])
    ev1 = s1.evaluate_candidate(temp_dir)
    assert ev1.certainty == RootCertainty.ROOT_UNKNOWN

    # 2. Folder with some market indicators -> CANDIDATE_UNVERIFIED
    os.makedirs(os.path.join(temp_dir, "1m"), exist_ok=True)
    s2 = MetadataScanner(candidate_roots=[temp_dir])
    ev2 = s2.evaluate_candidate(temp_dir)
    assert ev2.certainty == RootCertainty.ROOT_CANDIDATE_UNVERIFIED

    # 3. Folder with all 6 safe partitions -> CONFIRMED
    for month in SELECTED_SAFE_MONTHS:
        y, m = month.split("-")
        p = os.path.join(temp_dir, "1m", f"year={y}", f"month={m}")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "data.parquet"), "w") as f:
            f.write("mock")

    s3 = MetadataScanner(candidate_roots=[temp_dir])
    ev3 = s3.evaluate_candidate(temp_dir)
    assert ev3.certainty == RootCertainty.ROOT_CONFIRMED_FOR_SELECTED_METADATA


def test_17_wall_clock_timeout_safety_cutoff(temp_dir: str) -> None:
    """Test 17: Wall clock safety cutoff triggers if execution exceeds allowed time."""
    # Create several files
    for i in range(10):
        with open(os.path.join(temp_dir, f"file_{i}.txt"), "w") as f:
            f.write("test")

    # Set an impossibly small timeout
    scanner = MetadataScanner(candidate_roots=[temp_dir], max_wall_clock_seconds=0.000001)
    # Inject a tiny sleep before check
    scanner.start_time = time.time() - 10.0
    receipt = scanner.run()
    assert receipt.budget_exhausted is True
    assert "WALL_CLOCK_TIMEOUT" in (receipt.stop_reason or "")
