"""Frozen research contract. No fitting or threshold search."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from scripts.research.strategy_eval import HORIZONS, PLAN
from scripts.research.strategy_eval.costs import SCENARIOS

from . import LABELS, TASK

X_NAMES = ["log_return_1h", "log_return_4h", "log_return_24h", "rv_1h", "rv_24h",
           "log1p_quote_volume_1h", "log_relative_base_volume_1h",
           "close_in_range_1h", "close_in_range_24h", "log1p_base_volume_24h"]


def epoch(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_REQUIRED")
    return int(dt.timestamp())


H40 = (epoch("2025-02-01T00:00:00Z"), epoch("2026-02-01T00:00:00Z"))
H39 = epoch("2026-09-01T00:00:00Z")


def excluded(left: int, right: int) -> bool:
    """Conservative known exclusions; does not assert older dates authorized."""
    return max(left, H40[0]) < min(right, H40[1]) or right > H39


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prior_map(root: Path) -> dict:
    ledger = root / "docs/project/V0.6_B_LINE_STRATEGY_VALIDATION_REGISTER.md"
    families = [
        ("flow_spread_H32", "INCONCLUSIVE", "H32 INCONCLUSIVE_MECHANISM"),
        ("flow_spread_H33_H34", "FAIL", "H33/H34 FALSIFIED"),
        ("tactical_trend_breakout", "ECONOMIC_BLOCKED", "No net economic/support PASS"),
        ("flow_regime_Goal_B", "FAIL", "NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED"),
        ("Goal_A_economics", "INCONCLUSIVE", "Original economics materially inconsistent"),
        ("funding_mark_R3", "SOURCE_BLOCKED", "R3 source/causality blocked"),
        ("funding_mark_R31", "INCONCLUSIVE", "R3.1 COMPLETE_DEVELOPMENT_ONLY"),
        ("exit_landmark_horizon", "INCONCLUSIVE", "DIAGNOSTIC_INSUFFICIENT_SUPPORT"),
        ("F3_basis_increment", "UNTESTED", "basis increment untested/PIT unknown"),
        ("R3_stress_costs", "ECONOMIC_BLOCKED", "27/27 stress cells failed"),
        ("PA_B_T6", "FAIL", "EMPIRICALLY INFEASIBLE"),
        ("R11_D2_E2", "SOURCE_BLOCKED", "NOT_ACCEPTED pending independent source/PIT review"),
    ]
    content = ledger.read_text()
    rows = []
    for name, status, evidence in families:
        if evidence not in content:
            raise ValueError("LEDGER_EVIDENCE_CHANGED:" + name)
        rows.append({"family": name, "status": status, "evidence": evidence,
                     "ledger": str(ledger.relative_to(root)), "ledger_sha256": sha(ledger)})
    return {"families": rows, "rule": "No sign/window/threshold revival of failed families"}


def registration() -> dict:
    common = {
        "instrument": "binance/BTCUSDT/USD_M_PERPETUAL", "direction": "SHORT_ONLY",
        "origin": "UTC HH:01; cutoff HH:00; interval_end strictly < cutoff",
        "entry": "HH:02 first minute open after origin; proxy, no fill claim",
        "exits": {str(h): "entry + fixed hours; no stop/target/re-entry optimization"
                  for h in HORIZONS}, "primary_horizon_h": 8,
        "costs": [asdict(c) for c in SCENARIOS],
        "funding": "actual native events: entry < settlement <= exit; signed mark/entry notional",
        "capital": "1/H fixed sleeves; no leverage/reinvestment",
        "denominator": "ALL scheduled origins incl warmup, missing Z, no signal, missing outcomes",
        "comparison": "X and X+Z use identical eligible X AND Z origins; missing Z masks BOTH arms",
        "missingness": "No imputation/forward fill/backfill; missing outcome is unresolved, not zero",
        "opportunities": "rough target 1/48h, measured without outcomes; thresholds never tuned",
        "baseline_features": X_NAMES, "inner_windows": "7d frozen P1; no candidate parameter search",
        "outer_folds": "42/56/70d dev +14d validation;24h purge+1h embargo",
        "eligible_development_dates_not_authorization": {
            "long": ["2021-01-01T00:00:00Z", "2025-01-01T00:00:00Z"],
            "short": ["2026-04-01T00:00:00Z", "2026-09-01T00:00:00Z"]},
        "private_dates": "UNRESOLVED; Owner v2 private attestations mandatory before labels",
        "known_exclusions": [["2025-02-01", "2026-02-01"], ["2026-09-01", "unbounded"]],
        "rejection": ["Any clock/source identity leak => invalid",
                      "Less than 30 paired acted origins or 12 weekly blocks => INCONCLUSIVE",
                      "Primary 8h net utility at 16bp <=0 => ECONOMIC_BLOCKED",
                      "Primary 8h paired incremental utility <=0 => FAIL",
                      "Primary 8h net or increment at 32bp <=0 => ECONOMIC_BLOCKED",
                      "Nonpositive primary increment in >=2 of 3 chronological folds => FAIL",
                      "Any unresolved acted cost/funding => INCONCLUSIVE; no PASS",
                      """Joint bootstrap 7d blocks, 8 candidate/horizon slots, Bonferroni 0.05/8;
positive lower bound required; no OOS claim""".replace("\n", " ")],
    }
    return {"task": TASK, "schema": "bline-r1.preregistration.v1", "labels": LABELS,
            "state": "PREREGISTERED_UNTESTED_REAL_OUTCOMES", "parameter_search_budget": 0,
            "p1_plan": PLAN, "common": common, "candidates": [
        {"id": "FUNDING_PREMIUM_RELEASE", "mechanism": """After a rally, aligned positive past funding,
cash basis and mark-index premium start compressing: crowded leveraged longs may unwind.""".replace("\n", " "),
         "X_baseline": "SHORT iff log_return_4h >= 0.01",
         "incremental_Z": "previous 4h premium and basis; last1h changes; settled funding",
         "X_plus_Z": """X baseline AND prior4h mark-index >=0.0005 AND prior4h cash basis >=0.0003
AND premium_change<=-0.0002 AND basis_change<=-0.0002 AND last_settled_funding>=0.0001""".replace("\n", " "),
         "difference_from_prior": """Joint cross-market compression state after rally, not funding-level carry,
threshold rescue of R3.1, flow spread or exit extension; incremental state untested.""".replace("\n", " "),
         "native_source_scope": "Binance BTC 2021-2024; no C2 requirement"},
        {"id": "OI_DELEVERAGING_CONTINUATION", "mechanism": """Falling price with falling base OI and
long-heavy top positions may signal forced long deleveraging with continued sell pressure.""".replace("\n", " "),
         "X_baseline": "SHORT iff log_return_4h <= -0.01",
         "incremental_Z": "log(base_OI(t)/base_OI(t-4h)), log(top_position_LS(t))",
         "X_plus_Z": "X baseline AND log_OI_4h<=-0.02 AND log_top_position_LS>=log(1.5)",
         "difference_from_prior": """OI contraction continuation; differs from frozen P1 increasing-OI
overhang and price-only trends. No 2021 synthetic OI reconstruction.""".replace("\n", " "),
         "native_source_scope": "Binance BTC 2026-04-01 through 2026-08-31, 5m OI + exact4h predecessor"}]}


def signals(row: dict, candidate: str) -> tuple[int, int, bool]:
    """Paired deterministic policies; unready observations remain in denominator."""
    if row.get("venue", "binance") != "binance" or row.get("asset", "BTC") != "BTC":
        return 0, 0, False
    if row.get("data_kind") == "HISTORICAL_FEATURE_ONLY":
        left, right = ((epoch("2021-01-01T00:00:00Z"), epoch("2025-01-01T00:00:00Z"))
                       if candidate == "FUNDING_PREMIUM_RELEASE" else
                       (epoch("2026-04-01T00:00:00Z"), H39))
        if not left <= row["t"] < right:
            return 0, 0, False
    x = row.get("x")
    if not row.get("x_complete") or x is None:
        return 0, 0, False
    if candidate == "FUNDING_PREMIUM_RELEASE":
        z = row.get("derivatives")
        if z is None:
            return 0, 0, False
        baseline = -int(x[1] >= 0.01)
        trigger = (z["premium_prior4h"] >= .0005 and z["basis_prior4h"] >= .0003
                   and z["premium_change"] <= -.0002 and z["basis_change"] <= -.0002
                   and z["funding_rate"] >= .0001)
    elif candidate == "OI_DELEVERAGING_CONTINUATION":
        if row.get("z_status") != "OBSERVED" or row.get("z") is None:
            return 0, 0, False
        import math
        baseline = -int(x[1] <= -.01)
        trigger = row["z"][0] <= -.02 and row["z"][1] >= math.log(1.5)
    else:
        raise ValueError("CANDIDATE_NOT_REGISTERED")
    return baseline, baseline * int(trigger), True
