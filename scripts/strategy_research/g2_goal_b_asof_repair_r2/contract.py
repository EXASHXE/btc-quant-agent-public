"""Frozen contract, digests, definitions, and revocation attestations for Goal B R2."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

TASK_ID = "g2_goal_b_asof_repair_r2"
CONTROLLER_AUTHORITY = (
    "https://github.com/EXASHXE/btc-quant-agent-public/blob/"
    "1172d3a91324c1a7379bc9e5c24ef601076547c2/"
    "reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md"
)
CONTROLLER_DISPATCH_SHA = "1172d3a91324c1a7379bc9e5c24ef601076547c2"
PARENT_COMMIT_SHA = "397a62c1a0fbd6ad14a569a5be0058b1f684f08e"
SHARED_BASE_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
R1_FROZEN_SHA = "ebb33b7f96e5ab0c753beab14363632a0a221416"

ROOT = Path(__file__).resolve().parents[3]
PUBLIC_CACHE_DIR = Path("/tmp/btc-two-lead-funding-mark-r3")
EXIT_R1_DIR = ROOT / "evidence/v0.6/b_line/g2_exit_horizon_r1"
EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_goal_b_asof_repair_r2"
DOCS_DIR = ROOT / "docs/strategy_research/g2_goal_b_asof_repair_r2"

CANDIDATES = [
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
]

HORIZONS = ["E0", "H1", "H2"]

COST_MODELS: dict[str, dict[str, float]] = {
    "BASE": {
        "fee_bps": 12.0,
        "spread_bps": 4.0,
        "slippage_bps": 6.0,
        "total_bps": 22.0,
    },
    "STRESS": {
        "fee_bps": 24.0,
        "spread_bps": 8.0,
        "slippage_bps": 12.0,
        "total_bps": 44.0,
    },
}

# Immutable Exit R1 Paired Ledger Digests
EXPECTED_LEDGER_DIGESTS: dict[str, dict[str, Any]] = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_BASE_paired.jsonl": {
        "sha256": "acda3f0996931b551750e41eebc5a124127e1dac84821197264f76a3e63b00a5",
        "expected_events": 34,
        "candidate": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "cost": "BASE",
    },
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_STRESS_paired.jsonl": {
        "sha256": "f8d10f8a8e7d16046c2d207bf12250d63f3cc1c1ec0b3d26a692c4317f8d2d8a",
        "expected_events": 34,
        "candidate": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "cost": "STRESS",
    },
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_BASE_paired.jsonl": {
        "sha256": "4e417da29f07c85884199647c284031ca4c84801b48b0170bfd8f9f5e06be4b2",
        "expected_events": 55,
        "candidate": "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
        "cost": "BASE",
    },
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_STRESS_paired.jsonl": {
        "sha256": "c27a8dabafd4b8e9949aa94fe76f524104481395294e812ca630a73c28db7847",
        "expected_events": 55,
        "candidate": "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
        "cost": "STRESS",
    },
}

# Strict Timing Constants
SIGNAL_DECISION_LAG_MS = 60_000  # Exactly 1m before entry execution
TREND_BARS_COUNT = 240           # 240 consecutive 1m bars = strictly pre-entry 4h window
ATR_PERIOD = 14                  # Wilder ATR period on 1-hour bars
ATR_LOOKBACK_HOURS = 2160        # 90 days * 24 hours = 2,160 completed hourly bars
MIN_EVENTS_PER_STRATUM = 10      # Power gate minimum count per cell

# Formal Revocation Statements
FORMAL_REVOCATIONS: dict[str, str] = {
    "R1_TREND_LEAKAGE": (
        "REVOKED: Goal B R1 run.py (lines 136-142) assigned trend alignment using "
        "path24h.before12h.Last_MFE_R vs Last_MAE_R, which leaks the post-entry [0, 12h) "
        "in-trade price path. All R1 claims asserting predictive trend regimes are WITHDRAWN."
    ),
    "R1_VOLATILITY_SUBSTITUTION": (
        "REVOKED: Goal B R1 run.py (lines 145-146) binned volatility via risk_bps > 300 "
        "instead of the predeclared expanding prior-only 90d completed 1h ATR14 percentile. "
        "All R1 claims asserting high/low volatility regime performance are WITHDRAWN."
    ),
    "R1_FUNDING_LEAKAGE": (
        "REVOKED: Goal B R1 run.py (lines 149-154) extracted funding state from "
        "e0['funding_settlements'][0], which is the first settlement settling AFTER trade entry. "
        "All R1 claims asserting positive/negative funding regime advantages are WITHDRAWN."
    ),
    "R1_W2_YEAR_MISSTATEMENT": (
        "RECONCILED: Goal B R1 human report Table 4 misstated W2 annual trade counts as "
        "2021: 14, 2022: 17, 2023: 24. Verified primary Exit R1 machine records are "
        "2021: 10, 2022: 21, 2023: 24 (total 55). The machine truth is strictly preserved."
    ),
    "R1_SKIPPED_SIGNALS_MISSTATEMENT": (
        "RECONCILED: Goal B R1 human report Table 3 stated 0 skipped signals for E0, masking "
        "that E0 single-position account simulation also blocked candidate signals arriving "
        "during its 12h hold and cooldown."
    ),
    "R1_SLIPPAGE_VECTOR_DIFF": (
        "RECONCILED: In R1 Commit 1 slippage was temporarily set to 16/8 bp before being corrected "
        "in Commit 2 to 12/6 bp to match frozen STRESS44 (24 fee + 8 spread + 12 slip = 44 bp) and "
        "BASE22 (12 fee + 4 spread + 6 slip = 22 bp). STRESS44 / BASE22 are strictly frozen."
    ),
    "NO_STRATEGY_SEARCH": (
        "ATTESTED: Post-hoc causal repair is an observational diagnostic addendum only. "
        "Zero new entry rules, exit policies, parameter sweeps, or conditional switching "
        "variants are tested or promoted."
    ),
}


def sha256_of_file(path: Path) -> str:
    """Compute hex sha256 of file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_frozen_contract_data() -> dict[str, Any]:
    """Return immutable contract dictionary."""
    return {
        "task_id": TASK_ID,
        "controller_authority": CONTROLLER_AUTHORITY,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "parent_commit_sha": PARENT_COMMIT_SHA,
        "shared_base_sha": SHARED_BASE_SHA,
        "r1_frozen_sha": R1_FROZEN_SHA,
        "candidates": CANDIDATES,
        "horizons": HORIZONS,
        "cost_models": COST_MODELS,
        "expected_ledger_digests": EXPECTED_LEDGER_DIGESTS,
        "timing_constants": {
            "signal_decision_lag_ms": SIGNAL_DECISION_LAG_MS,
            "trend_bars_count": TREND_BARS_COUNT,
            "atr_period": ATR_PERIOD,
            "atr_lookback_hours": ATR_LOOKBACK_HOURS,
            "min_events_per_stratum": MIN_EVENTS_PER_STRATUM,
        },
        "formal_revocations": FORMAL_REVOCATIONS,
    }


def verify_contract_integrity(contract: dict[str, Any] | None = None) -> None:
    """Verify that ledger files exist and match exact SHA256 digests."""
    c = contract or get_frozen_contract_data()
    for fname, meta in c["expected_ledger_digests"].items():
        p = EXIT_R1_DIR / fname
        if not p.is_file():
            raise FileNotFoundError(f"Missing immutable Exit R1 ledger: {p}")
        actual_hash = sha256_of_file(p)
        if actual_hash != meta["sha256"]:
            raise ValueError(
                f"Hash mismatch for {fname}: expected {meta['sha256']}, got {actual_hash}"
            )
