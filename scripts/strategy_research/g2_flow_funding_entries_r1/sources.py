"""Read-only authenticated R3/R31 public caches for G2 Flow-Funding Alpha discovery.

Guards ensure no network downloads, no unadmitted data sources, and strict
preservation of authenticated public archives across 2021-01 through 2023-12.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.sources import source_plan
from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.gaps import (
    ALLOWED_DAYS,
    compose_gap_month,
    parse_daily,
)
from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.monthly import load_all

ROOT = Path(__file__).resolve().parents[3]
OLD = Path("/tmp/btc-two-lead-funding-mark-r3")
GAP = Path("/tmp/btc-two-lead-mark-gap-r31")
SCRATCH = Path("/tmp/btc-g2_flow_funding_entries_r1")
EP = ROOT / "evidence/v0.6/b_line/g2_flow_funding_entries_r1"
R31_EP = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31"
MINUTE = 60_000
EXPECTED_MINUTES = 1_576_800
EXPECTED_FUNDING_EVENTS = 3_285


def guarded(path: Path, base: Path) -> Path:
    if path.parent != base or base.is_symlink() or path.is_symlink():
        raise ValueError("Unauthorized or symlinked public cache path")
    if base.parent == GAP and GAP.is_symlink():
        raise ValueError("Symlinked R31 parent")
    return path


def load() -> tuple[dict[str, dict[tuple[int, int], np.ndarray]], dict[tuple[int, int], list[dict[str, Any]]], dict[str, Any]]:
    """Load authenticated 36-month Last, Mark, and Funding data from immutable caches."""
    if not __debug__:
        raise ValueError("Optimized Python forbidden before any source inspection")

    # Preflight every approved exact filename
    for y in (2021, 2022, 2023):
        for m in range(1, 13):
            for kind in ("last", "mark", "funding"):
                p = source_plan(y, m, kind)
                for suffix in ("", ".CHECKSUM"):
                    q = guarded(OLD / (kind + "-" + p["zip_name"] + suffix), OLD)
                    if not q.is_file():
                        raise ValueError(f"Required signed R3 cache {q.name} unavailable; no new source retry")

    arrays, rates, receipt = load_all()
    reference = json.loads((R31_EP / "R31_COMPOSITE_SOURCE_MANIFEST.json").read_text())
    days = {}
    for d in ALLOWED_DAYS:
        ref = next(x for x in reference["gap_source_receipts"] if x["day"] == d)
        folder = GAP / d
        name = f"BTCUSDT-1m-{d}.zip"
        raw = guarded(folder / name, folder).read_bytes()
        check = guarded(folder / (name + ".CHECKSUM"), folder).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == ref["daily_parse"]["zip_sha256"]
        assert hashlib.sha256(check).hexdigest() == ref["daily_parse"]["checksum_sha256"]
        days[d], proof = parse_daily(raw, check, d)
        assert len(days[d]) == 1440 and proof["csv_sha256"] == ref["daily_parse"]["csv_sha256"]

    proofs = []
    for (y, m), a in arrays["mark"].items():
        extra = [days[d] for d in ALLOWED_DAYS if d.startswith(f"{y}-{m:02d}-")]
        arrays["mark"][y, m], p = compose_gap_month(a, extra, y, m)
        original = next(x for x in reference["composites"] if (x["year"], x["month"]) == (y, m))
        assert p["dense"] and p["composite_sha256"] == original["composite_sha256"]
        proofs.append({"year": y, "month": m, **p})

    total_mark = sum(len(v) for v in arrays["mark"].values())
    total_last = sum(len(v) for v in arrays["last"].values())
    assert total_mark == EXPECTED_MINUTES, f"Mark minutes mismatch: {total_mark} != {EXPECTED_MINUTES}"
    assert total_last == EXPECTED_MINUTES, f"Last minutes mismatch: {total_last} != {EXPECTED_MINUTES}"

    # Verify Last table schema: 7 columns (time, open, high, low, close, volume, taker_buy_volume)
    for (y, m), arr in arrays["last"].items():
        if arr.shape[1] != 7:
            raise ValueError(f"Last array for {y}-{m:02d} must have 7 columns (got {arr.shape[1]})")
        if np.any(arr[:, 5] < 0) or np.any(arr[:, 6] < 0):
            raise ValueError(f"Negative volume or taker buy volume in {y}-{m:02d}")
        if np.any(arr[:, 6] > arr[:, 5] + 1e-9):
            raise ValueError(f"Taker buy volume exceeds total volume in {y}-{m:02d}")

    # Verify Mark table schema: 5 columns (time, open, high, low, close)
    for (y, m), arr in arrays["mark"].items():
        if arr.shape[1] != 5:
            raise ValueError(f"Mark array for {y}-{m:02d} must have 5 columns (got {arr.shape[1]})")

    all_funding = [e for key in sorted(rates) for e in rates[key]]
    assert len(all_funding) == EXPECTED_FUNDING_EVENTS

    receipt.update({
        "R31_source_manifest_sha256": reference["source_manifest_sha256"],
        "source_manifest_sha256": reference["source_manifest_sha256"],
        "composites": proofs,
        "daily_receipts": reference["gap_source_receipts"],
        "network_calls": 0,
        "scratch_writes": 0,
        "allowed_cache_roots": [str(OLD), str(GAP)],
        "known_at": "UNKNOWN; retrospective sources not entry signals",
        "settlement_Mark": "latest completed 1m close approximation",
        "taker_buy_base_volume_authenticated": True,
    })
    return arrays, rates, receipt


def assemble_continuous_series(
    arrays: dict[str, dict[tuple[int, int], np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    """Concatenate 36 monthly arrays into strictly contiguous 1,576,800-minute timelines."""
    months = [(y, m) for y in (2021, 2022, 2023) for m in range(1, 13)]
    last_chunks = [arrays["last"][y, m] for y, m in months]
    mark_chunks = [arrays["mark"][y, m] for y, m in months]

    last_full = np.vstack(last_chunks)
    mark_full = np.vstack(mark_chunks)

    if len(last_full) != EXPECTED_MINUTES or len(mark_full) != EXPECTED_MINUTES:
        raise ValueError(f"Concatenated arrays length mismatch: {len(last_full)} vs {EXPECTED_MINUTES}")

    diff_last = np.diff(last_full[:, 0])
    diff_mark = np.diff(mark_full[:, 0])
    if not np.all(diff_last == MINUTE):
        raise ValueError("Discontinuity detected in Last 1m timeline")
    if not np.all(diff_mark == MINUTE):
        raise ValueError("Discontinuity detected in Mark 1m timeline")
    if not np.all(last_full[:, 0] == mark_full[:, 0]):
        raise ValueError("Timestamp mismatch between Last and Mark timelines")

    return last_full, mark_full
