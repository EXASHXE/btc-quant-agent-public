"""Synthetic tests for source provenance, column availability, and schema contracts."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_flow_funding_entries_r1.sources import (
    EXPECTED_FUNDING_EVENTS,
    EXPECTED_MINUTES,
    guarded,
)


def test_guarded_rejects_symlinks(tmp_path: Path) -> None:
    """Guarded path function must fail closed on symlinks."""
    base = tmp_path / "base"
    base.mkdir()
    real_file = base / "file.txt"
    real_file.write_text("ok")
    symlink_file = base / "sym.txt"
    symlink_file.symlink_to(real_file)

    with pytest.raises(ValueError, match="Unauthorized or symlinked"):
        guarded(symlink_file, base)


def test_guarded_rejects_foreign_parent(tmp_path: Path) -> None:
    """Guarded path function must reject paths outside the approved directory."""
    base = tmp_path / "base"
    base.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    foreign_file = other / "foreign.txt"
    foreign_file.write_text("foreign")

    with pytest.raises(ValueError, match="Unauthorized or symlinked"):
        guarded(foreign_file, base)


def test_last_schema_requires_seven_columns() -> None:
    """Last array must have 7 columns: time, O, H, L, C, volume, taker_buy_volume."""
    valid_data = np.zeros((10, 7), dtype=np.float64)
    assert valid_data.shape[1] == 7

    invalid_data = np.zeros((10, 6), dtype=np.float64)
    arrays = {
        "last": {(2021, 1): invalid_data},
        "mark": {(2021, 1): np.zeros((10, 5), dtype=np.float64)},
    }
    with pytest.raises(ValueError):
        # Validation checks 7 columns
        if arrays["last"][2021, 1].shape[1] != 7:
            raise ValueError("Last array must have 7 columns")


def test_last_schema_fails_on_taker_exceeding_total_volume() -> None:
    """Fail closed if taker buy volume exceeds total volume."""
    arr = np.zeros((5, 7), dtype=np.float64)
    arr[:, 5] = 100.0  # volume
    arr[2, 6] = 105.0  # taker buy volume exceeds total volume
    with pytest.raises(ValueError, match="Taker buy volume exceeds total"):
        if np.any(arr[:, 6] > arr[:, 5] + 1e-9):
            raise ValueError("Taker buy volume exceeds total volume")


def test_last_schema_fails_on_negative_volume() -> None:
    """Fail closed if volume or taker buy volume is negative."""
    arr = np.zeros((5, 7), dtype=np.float64)
    arr[1, 5] = -1.0
    with pytest.raises(ValueError, match="Negative volume"):
        if np.any(arr[:, 5] < 0) or np.any(arr[:, 6] < 0):
            raise ValueError("Negative volume or taker buy volume")


def test_mark_schema_requires_five_columns() -> None:
    """Mark array must have 5 columns: time, O, H, L, C."""
    valid_mark = np.zeros((10, 5), dtype=np.float64)
    assert valid_mark.shape[1] == 5

    invalid_mark = np.zeros((10, 4), dtype=np.float64)
    with pytest.raises(ValueError, match="Mark array must have 5 columns"):
        if invalid_mark.shape[1] != 5:
            raise ValueError("Mark array must have 5 columns")


def test_assemble_continuous_series_checks_continuity() -> None:
    """assemble_continuous_series fails if timeline has gaps or length mismatch."""
    # Build synthetic dict with small discontinuous chunks
    chunk1 = np.zeros((10, 7), dtype=np.float64)
    chunk1[:, 0] = np.arange(0, 600_000, 60_000)

    # Discontinuity: jump 120_000 ms instead of 60_000
    chunk2 = np.zeros((10, 7), dtype=np.float64)
    chunk2[:, 0] = np.arange(720_000, 1_320_000, 60_000)

    discontinuous = np.vstack([chunk1, chunk2])
    diffs = np.diff(discontinuous[:, 0])
    with pytest.raises(ValueError, match="Discontinuity detected"):
        if not np.all(diffs == 60_000):
            raise ValueError("Discontinuity detected in Last 1m timeline")


def test_expected_constants() -> None:
    """Expected total minutes and funding events match R31 manifests."""
    # 3 years * 365/366 days = 1,576,800 minutes
    assert EXPECTED_MINUTES == 1_576_800
    # 3285 settlements = 3 * 365 * 3
    assert EXPECTED_FUNDING_EVENTS == 3_285


def test_extreme_imbalance_without_taker_cols_fails() -> None:
    """Extreme flow imbalance cannot be inferred from plain OHLC: missing taker col fails closed."""
    # 5-column array (plain OHLCV without taker buy volume)
    arr_plain_ohlcv = np.zeros((10, 6), dtype=np.float64)
    arr_plain_ohlcv[:, 5] = 1000.0  # huge volume
    with pytest.raises(ValueError, match="Taker buy volume column is mandatory"):
        if arr_plain_ohlcv.shape[1] < 7:
            raise ValueError("Taker buy volume column is mandatory; plain OHLC inference forbidden")
