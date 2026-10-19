"""Prospective research contract for V065-BLINE-R2-SAMPLE-EXPANSION.

Preserves the frozen BLINE-R1 registration and hypotheses without retrospective rewrites.
Extends candidate evaluation scope prospectively to newly admitted partitions (2026 Q2/Q3),
keeps venue populations strictly separated, and provides event episode clustering.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from scripts.research.strategy_eval import HORIZONS, PLAN
from scripts.research.strategy_eval.costs import SCENARIOS

from .contracts import H39, X_NAMES, epoch, excluded

TASK_R2 = "V065-BLINE-R2-SAMPLE-EXPANSION"
SCHEMA_R2 = "bline-r2.preregistration.v1"
LABELS_R2 = [
    "P3_ACCESS_SCOPE_HOLD",
    "PIT_UNKNOWN",
    "SOURCE_NOT_ADMITTED",
    "NO_ALPHA_ESTABLISHED",
    "G2_ALPHA_NO_GO",
    "G4_TESTNET_NO_GO",
    "LIVE_NO_GO",
    "REAL_FUNDS_WRITE_NONE",
]


def registration_r2() -> dict[str, Any]:
    """Prospective research registration for BLINE-R2 sample expansion.

    Reuses frozen candidate thresholds exactly (zero threshold tuning).
    Registers prospective extended window for 2026 and cross-venue population isolation.
    """
    common = {
        "instrument": "binance/BTCUSDT/USD_M_PERPETUAL",
        "direction": "SHORT_ONLY",
        "origin": "UTC HH:01; cutoff HH:00; interval_end strictly < cutoff",
        "entry": "HH:02 first minute open after origin; proxy, no fill claim",
        "exits": {
            str(h): "entry + fixed hours; no stop/target/re-entry optimization"
            for h in HORIZONS
        },
        "primary_horizon_h": 8,
        "costs": [asdict(c) for c in SCENARIOS],
        "funding": "actual native events: entry < settlement <= exit; signed mark/entry notional",
        "capital": "1/H fixed sleeves; no leverage/reinvestment",
        "denominator": "ALL scheduled origins incl warmup, missing Z, no signal, missing outcomes",
        "comparison": "X and X+Z use identical eligible X AND Z origins; missing Z masks BOTH arms",
        "missingness": "No imputation/forward fill/backfill; missing outcome is unresolved, not zero",
        "opportunities": "rough target 1/48h, measured without outcomes; thresholds never tuned",
        "baseline_features": X_NAMES,
        "inner_windows": "7d frozen P1; no candidate parameter search",
        "outer_folds": "42/56/70d dev +14d validation;24h purge+1h embargo",
        "eligible_development_dates_not_authorization": {
            "long": ["2021-01-01T00:00:00Z", "2025-01-01T00:00:00Z"],
            "short_r1": ["2026-04-01T00:00:00Z", "2026-09-01T00:00:00Z"],
            "short_r2_extended": ["2026-04-01T00:00:00Z", "2026-10-01T00:00:00Z"],
        },
        "private_dates": "UNRESOLVED; Owner v2 private attestations mandatory before labels",
        "known_exclusions": [["2025-02-01", "2026-02-01"]],
        "rejection": [
            "Any clock/source identity leak => invalid",
            "Less than 30 paired acted origins or 12 weekly blocks => INCONCLUSIVE",
            "Primary 8h net utility at 16bp <=0 => ECONOMIC_BLOCKED",
            "Primary 8h paired incremental utility <=0 => FAIL",
            "Primary 8h net or increment at 32bp <=0 => ECONOMIC_BLOCKED",
            "Nonpositive primary increment in >=2 of 3 chronological folds => FAIL",
            "Any unresolved acted cost/funding => INCONCLUSIVE; no PASS",
            (
                "Joint bootstrap 7d blocks, 8 candidate/horizon slots, Bonferroni 0.05/8; "
                "positive lower bound required; no OOS claim"
            ),
        ],
        "populations": {
            "binance": {
                "role": "PRIMARY_EVALUATION_POPULATION",
                "instrument": "BTCUSDT",
                "market": "futures_um",
                "status": "SOURCES_ADMITTED_2021_2026",
            },
            "okx": {
                "role": "CROSS_VENUE_CONTROL_POPULATION",
                "instrument": "BTC-USDT-SWAP",
                "market": "swap",
                "status": "SOURCES_ADMITTED_Q2_Q3_NO_HISTORICAL_OI",
            },
            "bybit": {
                "role": "EXTERNAL_COMPARISON_POPULATION",
                "instrument": "BTCUSDT",
                "market": "linear_perpetual",
                "status": "SOURCES_UNAVAILABLE_NOT_ADMITTED",
            },
        },
    }

    candidates = [
        {
            "id": "FUNDING_PREMIUM_RELEASE",
            "mechanism": (
                "After a rally, aligned positive past funding, cash basis and mark-index premium "
                "start compressing: crowded leveraged longs may unwind."
            ),
            "X_baseline": "SHORT iff log_return_4h >= 0.01",
            "incremental_Z": "previous 4h premium and basis; last1h changes; settled funding",
            "X_plus_Z": (
                "X baseline AND prior4h mark-index >=0.0005 AND prior4h cash basis >=0.0003 "
                "AND premium_change<=-0.0002 AND basis_change<=-0.0002 AND last_settled_funding>=0.0001"
            ),
            "difference_from_prior": (
                "Joint cross-market compression state after rally, not funding-level carry, "
                "threshold rescue of R3.1, flow spread or exit extension; incremental state untested."
            ),
            "native_source_scope": "Binance BTC 2021-2024; optional 2026 extension where basis/mark available",
            "frozen_r1_reproduction": True,
        },
        {
            "id": "OI_DELEVERAGING_CONTINUATION",
            "mechanism": (
                "Falling price with falling base OI and long-heavy top positions may signal "
                "forced long deleveraging with continued sell pressure."
            ),
            "X_baseline": "SHORT iff log_return_4h <= -0.01",
            "incremental_Z": "log(base_OI(t)/base_OI(t-4h)), log(top_position_LS(t))",
            "X_plus_Z": "X baseline AND log_OI_4h<=-0.02 AND log_top_position_LS>=log(1.5)",
            "difference_from_prior": (
                "OI contraction continuation; differs from frozen P1 increasing-OI overhang "
                "and price-only trends. No 2021 synthetic OI reconstruction."
            ),
            "native_source_scope": (
                "Binance BTC 2026-04-01 through 2026-09-30 (Q2+Q3), 5m OI + exact 4h predecessor"
            ),
            "frozen_r1_reproduction": True,
        },
    ]

    return {
        "task": TASK_R2,
        "schema": SCHEMA_R2,
        "labels": LABELS_R2,
        "state": "PREREGISTERED_PROSPECTIVE_SAMPLE_EXPANSION",
        "parameter_search_budget": 0,
        "p1_plan": PLAN,
        "common": common,
        "candidates": candidates,
        "r1_baseline_reference": {
            "task": "V065-BLINE-R1",
            "schema": "bline-r1.preregistration.v1",
            "state": "FROZEN_PRESERVED_IMMUTABLE",
        },
    }


def signals_r2(
    row: dict[str, Any],
    candidate: str,
    *,
    allow_extended_2026: bool = True,
) -> tuple[int, int, bool]:
    """Deterministic candidate signals with prospective R2 extension support.

    Returns:
        (x_baseline_action, xz_action, paired_eligible)
        - x_baseline_action: -1 (SHORT) or 0 (NO_ACTION)
        - xz_action: -1 (SHORT) or 0 (NO_ACTION)
        - paired_eligible: True if both X and Z are observed and valid for paired comparison
    """
    if row.get("venue", "binance") != "binance" or row.get("asset", "BTC") != "BTC":
        return 0, 0, False

    t = row.get("t", 0)
    if row.get("data_kind") == "HISTORICAL_FEATURE_ONLY":
        if candidate == "FUNDING_PREMIUM_RELEASE":
            left = epoch("2021-01-01T00:00:00Z")
            # If extended, allows 2026 where derivatives are populated; otherwise 2021-2025
            right = epoch("2026-10-01T00:00:00Z") if allow_extended_2026 else epoch("2025-01-01T00:00:00Z")
            # Check excluded H40
            if excluded(t, t + 3600):
                return 0, 0, False
            if not left <= t < right:
                return 0, 0, False
        elif candidate == "OI_DELEVERAGING_CONTINUATION":
            left = epoch("2026-04-01T00:00:00Z")
            # In R1, right = H39 (2026-09-01). In R2 extended, right = 2026-10-01 (includes Sept 2026).
            right = epoch("2026-10-01T00:00:00Z") if allow_extended_2026 else H39
            if not left <= t < right:
                return 0, 0, False
        else:
            raise ValueError(f"CANDIDATE_NOT_REGISTERED: {candidate}")

    x = row.get("x")
    if not row.get("x_complete") or x is None:
        return 0, 0, False

    if candidate == "FUNDING_PREMIUM_RELEASE":
        z = row.get("derivatives")
        if z is None:
            return 0, 0, False
        baseline = -int(x[1] >= 0.01)
        trigger = (
            z["premium_prior4h"] >= 0.0005
            and z["basis_prior4h"] >= 0.0003
            and z["premium_change"] <= -0.0002
            and z["basis_change"] <= -0.0002
            and z["funding_rate"] >= 0.0001
        )
        return baseline, baseline * int(trigger), True

    elif candidate == "OI_DELEVERAGING_CONTINUATION":
        if row.get("z_status") != "OBSERVED" or row.get("z") is None:
            return 0, 0, False
        baseline = -int(x[1] <= -0.01)
        # z[0] is log(base_OI(t)/base_OI(t-4h)), z[1] is log(top_position_LS(t))
        trigger = row["z"][0] <= -0.02 and row["z"][1] >= math.log(1.5)
        return baseline, baseline * int(trigger), True

    return 0, 0, False
