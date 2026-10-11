"""Read-only authenticated Binance Vision 2021-2023 public caches for Goal A R2.

Strict negative constraints:
- Zero network calls.
- Zero writes to legacy task directories or outside task own scratch /tmp/btc-gemini-entry-goal-r2.
- Only official Binance Vision BTCUSDT USD-M 2021-2023 Last, Mark, and Funding.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from pathlib import Path

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
SCRATCH = Path("/tmp/btc-gemini-entry-goal-r2")
EP = ROOT / "evidence/v0.6/b_line/g2_goal_entry_discovery_r2"
R31_EP = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31"


def guarded(path: Path, base: Path) -> Path:
    """Ensure path is directly inside base and neither is a symlink."""
    if path.parent != base or base.is_symlink() or path.is_symlink():
        raise ValueError(f"Unauthorized or symlinked path: {path}")
    if base.parent == GAP and GAP.is_symlink():
        raise ValueError("Symlinked R31 parent directory")
    return path


def load() -> tuple[dict[str, dict[tuple[int, int], any]], dict[tuple[int, int], list[dict]], dict]:
    """Load authenticated 2021-2023 1m Last, 1m Mark R31 composites, and Funding."""
    if not __debug__:
        raise ValueError("Optimized Python forbidden before source inspection")

    SCRATCH.mkdir(parents=True, exist_ok=True)

    # Preflight R3 source caches
    for y in (2021, 2022, 2023):
        for m in range(1, 13):
            for kind in ("last", "mark", "funding"):
                p = source_plan(y, m, kind)
                for suffix in ("", ".CHECKSUM"):
                    q = guarded(OLD / (kind + "-" + p["zip_name"] + suffix), OLD)
                    if not q.is_file():
                        raise ValueError(f"Required signed R3 cache missing: {q}")

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

    assert sum(map(len, arrays["mark"].values())) == 1576800
    assert sum(map(len, arrays["last"].values())) == 1576800
    assert sum(map(len, rates.values())) == 3285

    receipt.update({
        "R31_source_manifest_sha256": reference["source_manifest_sha256"],
        "source_manifest_sha256": reference["source_manifest_sha256"],
        "composites": proofs,
        "daily_receipts": reference["gap_source_receipts"],
        "network_calls": 0,
        "scratch_directory": str(SCRATCH),
        "allowed_cache_roots": [str(OLD), str(GAP)],
        "known_at": "retrospective archives; completed 1m close timestamps",
        "settlement_Mark": "latest completed 1m close approximation",
    })
    return arrays, rates, receipt


def get_monthly_folds() -> list[dict]:
    """Return 35 monthly folds (2021-02 to 2023-12) with 24h edge embargoes.
    
    2021-01 is reserved strictly for continuous indicator warmup.
    """
    folds = []
    all_months = [(y, m) for y in (2021, 2022, 2023) for m in range(1, 13)]
    for idx in range(1, len(all_months)):
        scored_y, scored_m = all_months[idx]
        prev_y, prev_m = all_months[idx - 1]
        days_in_month = calendar.monthrange(scored_y, scored_m)[1]
        start_ms = int(calendar.timegm((scored_y, scored_m, 1, 0, 0, 0, 0, 0, 0)) * 1000)
        end_ms = start_ms + days_in_month * 1440 * 60_000

        embargo_start_ms = start_ms + 24 * 3600 * 1000
        embargo_end_ms = end_ms - 24 * 3600 * 1000

        folds.append({
            "year": scored_y,
            "month": scored_m,
            "prev_year": prev_y,
            "prev_month": prev_m,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "embargo_start_ms": embargo_start_ms,
            "embargo_end_ms": embargo_end_ms,
        })
    return folds
