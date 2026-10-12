"""Read-only authenticated R3/R31 public caches and original Exit R1 / B R2 provenance gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.sources import source_plan
from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.gaps import (
    ALLOWED_DAYS,
    compose_gap_month,
    parse_daily,
)
from scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.monthly import load_all

from .contract import (
    B_R2_EVIDENCE_DIR,
    CANDIDATE_IDS,
    EXIT_R1_EVIDENCE_DIR,
    EXPECTED_EXIT_R1_LEDGER_SHA256,
    EXPECTED_ORIGINAL_EVENTS,
    EXPECTED_ORIGINAL_STRESS_TIME_CAPS,
    EXPECTED_R31_MANIFEST_SHA256,
    GAP_R31_CACHE,
    OLD_R3_CACHE,
    R31_EVIDENCE_DIR,
    sha256_file,
)


def guarded(path: Path, base: Path) -> Path:
    if path.parent != base or base.is_symlink() or path.is_symlink():
        raise ValueError("NO_SOURCE: Unauthorized or symlinked public cache path")
    if base.parent == GAP_R31_CACHE and GAP_R31_CACHE.is_symlink():
        raise ValueError("NO_SOURCE: Symlinked R31 parent")
    return path


def verify_exit_r1_and_b_r2_provenance() -> dict[str, Any]:
    """Verify original Exit R1 immutable E0/H1 ledgers and B R2 formal revocations."""
    if not __debug__:
        raise ValueError("Optimized Python forbidden before provenance verification")

    ledger_checks: dict[str, dict[str, Any]] = {}
    for filename, expected_sha in EXPECTED_EXIT_R1_LEDGER_SHA256.items():
        p = EXIT_R1_EVIDENCE_DIR / filename
        if not p.is_file() or p.is_symlink():
            raise ValueError(f"NO_SOURCE: Missing or symlinked Exit R1 ledger {filename}")
        actual_sha = sha256_file(p)
        if actual_sha != expected_sha:
            raise ValueError(f"NO_SOURCE: Exit R1 ledger SHA mismatch for {filename}")
        lines = [line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        cid = next(c for c in CANDIDATE_IDS if filename.startswith(c))
        if len(lines) != EXPECTED_ORIGINAL_EVENTS[cid]:
            raise ValueError(f"NO_SOURCE: Unexpected row count in {filename}: {len(lines)}")
        ledger_checks[filename] = {
            "sha256": actual_sha,
            "rows": len(lines),
            "status": "EXACT_MATCH",
        }

    # Verify W1=20 and W2=36 original E0 STRESS TIME_CAP counts
    stress_time_cap_counts: dict[str, int] = {}
    for cid in CANDIDATE_IDS:
        paired_path = EXIT_R1_EVIDENCE_DIR / f"{cid}_STRESS_paired.jsonl"
        rows = [json.loads(line) for line in paired_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        tc_count = sum(1 for r in rows if r["cells"]["E0"]["exit_reason"] == "TIME_CAP")
        if tc_count != EXPECTED_ORIGINAL_STRESS_TIME_CAPS[cid]:
            raise ValueError(
                f"Exit R1 STRESS E0 TIME_CAP count mismatch for {cid}: {tc_count} != {EXPECTED_ORIGINAL_STRESS_TIME_CAPS[cid]}"
            )
        stress_time_cap_counts[cid] = tc_count

    # Verify B R2 formal revocations of post-entry MFE/MAE and funding bins
    b_r2_contract_path = B_R2_EVIDENCE_DIR / "B_R2_FROZEN_CONTRACT.json"
    if not b_r2_contract_path.is_file():
        raise ValueError("NO_SOURCE: Missing B_R2_FROZEN_CONTRACT.json")
    b_r2_contract = json.loads(b_r2_contract_path.read_text(encoding="utf-8"))
    revocations = b_r2_contract.get("formal_revocations", {})
    for required_key in ("R1_TREND_LEAKAGE", "R1_VOLATILITY_SUBSTITUTION", "R1_FUNDING_LEAKAGE"):
        if required_key not in revocations or "REVOKED" not in str(revocations[required_key]):
            raise ValueError(f"Missing required B R2 formal revocation: {required_key}")

    return {
        "exit_r1_ledgers_verified": len(ledger_checks),
        "exit_r1_ledger_receipts": ledger_checks,
        "w1_original_events": EXPECTED_ORIGINAL_EVENTS["W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H"],
        "w2_original_events": EXPECTED_ORIGINAL_EVENTS["W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H"],
        "stress_e0_time_cap_counts": stress_time_cap_counts,
        "b_r2_revocations_verified": True,
        "b_r2_revoked_keys": sorted(revocations.keys()),
        "holding_time_12h_decision_not_entry_predictor": True,
    }


def load_immutable_exit_r1_ledgers() -> dict[tuple[str, str], dict[str, list[dict[str, Any]]]]:
    """Load read-only original Exit R1 paired, E0_orders, and H1_orders ledgers."""
    out: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            paired_p = EXIT_R1_EVIDENCE_DIR / f"{cid}_{cost_name}_paired.jsonl"
            e0_p = EXIT_R1_EVIDENCE_DIR / f"{cid}_{cost_name}_E0_orders.jsonl"
            h1_p = EXIT_R1_EVIDENCE_DIR / f"{cid}_{cost_name}_H1_orders.jsonl"
            out[cid, cost_name] = {
                "paired": [json.loads(line) for line in paired_p.read_text(encoding="utf-8").splitlines() if line.strip()],
                "E0_orders": [json.loads(line) for line in e0_p.read_text(encoding="utf-8").splitlines() if line.strip()],
                "H1_orders": [json.loads(line) for line in h1_p.read_text(encoding="utf-8").splitlines() if line.strip()],
            }
    return out


def load_sources(
    *,
    old_cache: Path = OLD_R3_CACHE,
    gap_cache: Path = GAP_R31_CACHE,
) -> tuple[dict[str, Any], dict[tuple[int, int], list[dict[str, Any]]], dict[str, Any]]:
    """Load read-only 2021-2023 Last, Mark gap-composite, and Funding from R3/R31 caches."""
    if not __debug__:
        raise ValueError("Optimized Python forbidden before any source inspection")

    for y in (2021, 2022, 2023):
        for m in range(1, 13):
            for kind in ("last", "mark", "funding"):
                p = source_plan(y, m, kind)
                for suffix in ("", ".CHECKSUM"):
                    q = guarded(old_cache / (kind + "-" + p["zip_name"] + suffix), old_cache)
                    if not q.is_file():
                        raise ValueError("NO_SOURCE: Required signed R3 cache unavailable; no substitute download")

    for d in ALLOWED_DAYS:
        folder = gap_cache / d
        name = f"BTCUSDT-1m-{d}.zip"
        for suffix in ("", ".CHECKSUM"):
            q = guarded(folder / (name + suffix), folder)
            if not q.is_file():
                raise ValueError("NO_SOURCE: Required signed R31 daily gap cache unavailable")

    arrays, rates, receipt = load_all()
    reference = json.loads((R31_EVIDENCE_DIR / "R31_COMPOSITE_SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    if reference.get("source_manifest_sha256") != EXPECTED_R31_MANIFEST_SHA256:
        raise ValueError("NO_SOURCE: R31 composite manifest SHA256 mismatch")

    days = {}
    for d in ALLOWED_DAYS:
        ref = next(x for x in reference["gap_source_receipts"] if x["day"] == d)
        folder = gap_cache / d
        name = f"BTCUSDT-1m-{d}.zip"
        raw = guarded(folder / name, folder).read_bytes()
        check = guarded(folder / (name + ".CHECKSUM"), folder).read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref["daily_parse"]["zip_sha256"]:
            raise ValueError(f"NO_SOURCE: Daily ZIP SHA mismatch for {d}")
        if hashlib.sha256(check).hexdigest() != ref["daily_parse"]["checksum_sha256"]:
            raise ValueError(f"NO_SOURCE: Daily CHECKSUM SHA mismatch for {d}")
        days[d], proof = parse_daily(raw, check, d)
        if len(days[d]) != 1440 or proof["csv_sha256"] != ref["daily_parse"]["csv_sha256"]:
            raise ValueError(f"NO_SOURCE: Daily CSV parse mismatch for {d}")

    proofs = []
    for (y, m), a in arrays["mark"].items():
        extra = [days[d] for d in ALLOWED_DAYS if d.startswith(f"{y}-{m:02d}-")]
        arrays["mark"][y, m], p = compose_gap_month(a, extra, y, m)
        original = next(x for x in reference["composites"] if (x["year"], x["month"]) == (y, m))
        if not p["dense"] or p["composite_sha256"] != original["composite_sha256"]:
            raise ValueError(f"NO_SOURCE: Composite Mark SHA mismatch for {y}-{m:02d}")
        proofs.append({"year": y, "month": m, **p})

    last_total = sum(len(v) for v in arrays["last"].values())
    mark_total = sum(len(v) for v in arrays["mark"].values())
    funding_total = sum(len(v) for v in rates.values())
    if last_total != 1_576_800 or mark_total != 1_576_800 or funding_total != 3_285:
        raise ValueError(
            f"NO_SOURCE: Unexpected row counts last={last_total}, mark={mark_total}, funding={funding_total}"
        )

    receipt.update({
        "R31_source_manifest_sha256": reference["source_manifest_sha256"],
        "source_manifest_sha256": reference["source_manifest_sha256"],
        "composites": proofs,
        "daily_receipts": reference["gap_source_receipts"],
        "last_total_minutes": last_total,
        "mark_total_minutes": mark_total,
        "funding_total_events": funding_total,
        "network_calls": 0,
        "old_scratch_writes": 0,
        "allowed_cache_roots": [str(old_cache), str(gap_cache)],
        "known_at": "UNKNOWN; retrospective archive timestamps, evaluated strictly as-of 12h holding clock",
        "settlement_Mark": "latest completed 1m Mark close approximation",
    })
    return arrays, rates, receipt
