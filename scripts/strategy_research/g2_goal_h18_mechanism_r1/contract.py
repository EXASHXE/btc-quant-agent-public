"""Frozen method contract and cryptographic identity digests for Gemini Goal B."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

TASK_ID = "V06_G2_POST_EXIT_R1_GOAL_B_H18_MECHANISM_R1"
CONTROLLER_DISPATCH_SHA = "c02743fddccdf517582c371a47e82d8dcbb05923"
START_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
EXIT_R1_FROZEN_SHA = "de2c1fb222970a93ca797868b91b8544261ebaad"
ROOT = Path(__file__).resolve().parents[3]
OWN_PREFIX = "g2_goal_h18_mechanism_r1"
OWN_BRANCH = "feature/v06-bline-gemini-goal-h18-mechanism-r1"
OWN_WORKTREE = "/root/workspace/project/quant-v0.6/gemini-h18-mechanism-r1"
OWN_SCRATCH = Path("/tmp/btc-gemini-h18-goal-r1")

CANDIDATES = (
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
)
SCHEMES = ("E0", "H1", "H2")
COST_MODELS = ("STRESS", "BASE")
MIN_EVENTS_PER_STRATUM = 10
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 42

EXPECTED_E0_EVENTS = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H": 34,
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H": 55,
}

EXPECTED_E0_TIME_CAPS = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H": 20,
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H": 36,
}

EXPECTED_CONTRASTS = (
    ("H1", "E0"),
    ("H2", "E0"),
    ("H2", "H1"),
)

PREDECLARED_STATE_LABELS = {
    "year": ("2021", "2022", "2023"),
    "side": ("LONG", "SHORT"),
    "trend_alignment": ("TREND_ALIGNED", "COUNTERTREND", "NEUTRAL"),
    "volatility_regime": ("HIGH_VOL", "LOW_VOL", "INCOMPLETE_LOOKBACK"),
    "funding_regime": ("POSITIVE", "NEGATIVE", "ZERO", "UNKNOWN"),
}

ANALYSIS_OBJECTIVES = {
    "analysis_1_timecap_vs_early_exit": (
        "Frozen E0-accepted time-cap censored vs early STOP/TARGET baseline strata, "
        "tracing 12-18h and 18-24h incremental favorable/adverse path, funding cash, "
        "fee changes, exit reason fates, MFE/MAE, risk-scaled returns, and actual timestamps."
    ),
    "analysis_2_whole_account_opportunity_cost": (
        "Whole-account opportunity cost: independent E0/H1/H2 signal stream replays, "
        "logging signals declined due to prior position extension, exit ACK/cooldown, "
        "5% cash reserve, 1x notional, cumulative cash, and minute Mark MTM. "
        "Distinguish matched same-event vs different account event set estimands."
    ),
    "analysis_3_time_execution_decomposition": (
        "Post-12h incremental signed price PnL vs extra settled Funding vs fees/spread/slip, "
        "additional Mark drawdown/occupancy, 2021/2022/2023 attribution, and one-bar later "
        "exit ACK / worse slip fixed sensitivities under BASE and STRESS."
    ),
}

FALSIFICATION_GATES = {
    "gate_1_h18_continuation_coin_flip": (
        "If >=45% of 12-18h time-cap continuation outcomes are adverse/reversals, "
        "the positive H1-E0 mean is an asymmetric right-tail outlier effect rather than "
        "a reliable continuation alpha."
    ),
    "gate_2_h24_momentum_exhaustion": (
        "If 18-24h yields net negative mean continuation and increased stopouts, "
        "H2 underperformance relative to H1 is falsified as structural trend decay."
    ),
    "gate_3_2023_instability": (
        "If W2 remains negative in 2023 under STRESS despite H1 extension, "
        "18h holding cannot be claimed to rescue structural regime failure."
    ),
    "gate_4_regime_targeting_feasibility": (
        "If as-of regime strata have N < 10 events, regime targeting is marked "
        "UNDERPOWERED and cannot support any selectable conditional exit policy."
    ),
    "gate_5_opportunity_blocking": (
        "If extending horizon from 12h to 18h or 24h does not block new entries from "
        "the candidate stream (due to signal sparsity), account-level trade set equals "
        "the paired trade set, but capital occupancy increases."
    ),
}


def hash_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_frozen_contract_data() -> dict[str, Any]:
    """Assemble complete frozen contract metadata."""
    manifest_p = ROOT / "evidence/v0.6/b_line/g2_exit_horizon_r1/COMMITTED_LEDGER_MANIFEST.json"
    manifest_sha = hash_file(manifest_p) if manifest_p.is_file() else None

    # Track code files in own prefix
    code_files: dict[str, str] = {}
    script_dir = ROOT / "scripts/strategy_research/g2_goal_h18_mechanism_r1"
    if script_dir.is_dir():
        for p in sorted(script_dir.glob("*.py")):
            rel = str(p.relative_to(ROOT))
            code_files[rel] = hash_file(p)

    test_dir = ROOT / "tests"
    for p in sorted(test_dir.glob("test_v06_g2_goal_h18_mechanism_r1_*.py")):
        rel = str(p.relative_to(ROOT))
        code_files[rel] = hash_file(p)

    return {
        "TASK_ID": TASK_ID,
        "CONTROLLER_DISPATCH_SHA": CONTROLLER_DISPATCH_SHA,
        "START_SHA": START_SHA,
        "EXIT_R1_FROZEN_SHA": EXIT_R1_FROZEN_SHA,
        "OWN_PREFIX": OWN_PREFIX,
        "OWN_BRANCH": OWN_BRANCH,
        "OWN_WORKTREE": OWN_WORKTREE,
        "candidates": list(CANDIDATES),
        "schemes": list(SCHEMES),
        "cost_models": list(COST_MODELS),
        "min_events_per_stratum": MIN_EVENTS_PER_STRATUM,
        "bootstrap": {
            "draws": BOOTSTRAP_DRAWS,
            "seed": BOOTSTRAP_SEED,
            "block_days": [7, 14],
            "zero_trade_blocks_retained": True,
        },
        "predeclared_state_labels": PREDECLARED_STATE_LABELS,
        "expected_e0_events": EXPECTED_E0_EVENTS,
        "expected_e0_time_caps": EXPECTED_E0_TIME_CAPS,
        "expected_contrasts": [f"{n}-{o}" for n, o in EXPECTED_CONTRASTS],
        "analysis_objectives": ANALYSIS_OBJECTIVES,
        "falsification_gates": FALSIFICATION_GATES,
        "inherited_exit_r1_manifest_sha256": manifest_sha,
        "frozen_code_files": code_files,
        "grade": "OBSERVATIONAL_MECHANISTIC_DIAGNOSTIC_DEV_ONLY",
        "new_configurable_exit_policies_authorized": 0,
    }


def verify_contract_integrity(contract: dict[str, Any]) -> bool:
    """Verify that contract satisfies all frozen requirements."""
    assert contract["TASK_ID"] == TASK_ID
    assert contract["CONTROLLER_DISPATCH_SHA"] == CONTROLLER_DISPATCH_SHA
    assert contract["START_SHA"] == START_SHA
    assert contract["EXIT_R1_FROZEN_SHA"] == EXIT_R1_FROZEN_SHA
    assert set(contract["candidates"]) == set(CANDIDATES)
    assert set(contract["schemes"]) == set(SCHEMES)
    assert set(contract["cost_models"]) == set(COST_MODELS)
    assert contract["min_events_per_stratum"] == MIN_EVENTS_PER_STRATUM
    assert contract["bootstrap"]["draws"] == BOOTSTRAP_DRAWS
    assert contract["bootstrap"]["seed"] == BOOTSTRAP_SEED
    assert contract["new_configurable_exit_policies_authorized"] == 0
    return True
