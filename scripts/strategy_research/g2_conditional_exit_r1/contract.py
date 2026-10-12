"""Frozen contract, provenance constants, and predeclared primary gates for G2 Conditional Exit R1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

TASK_ID = "V06_G2_GEMINI_B_CONDITIONAL_EXIT_R1"
CONTROLLER_DISPATCH_SHA = "99df4ed8e820984d69d7b895be8808b892ed7f5f"
CONTROLLER_AUTHORITY = (
    "https://github.com/EXASHXE/btc-quant-agent-public/blob/"
    "99df4ed8e820984d69d7b895be8808b892ed7f5f/reviews/v0.6/b_line/"
    "V06_G2_NEXT_WAVE_CODEX_GEMINI_PARALLEL_R1_CONTROLLER_AUTHORITY.md"
)
REPOSITORY = "EXASHXE/btc-quant-agent-public"
BRANCH = "feature/v06-bline-gemini-g2-conditional-exit-r1"
EXACT_START_SHA = "d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2"
WORKTREE = "/root/workspace/project/quant-v0.6/gemini-g2-conditional-exit-r1"
OWN_NAMESPACE = "g2_conditional_exit_r1"
READ_ONLY_ORIGINAL_EXIT_R1 = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
READ_ONLY_MARGIN_R2 = "c9846adacc1f2df85931ecf4649e02a3a61cf466"

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path("/tmp/btc-g2_conditional_exit_r1")
OLD_R3_CACHE = Path("/tmp/btc-two-lead-funding-mark-r3")
GAP_R31_CACHE = Path("/tmp/btc-two-lead-mark-gap-r31")

EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_conditional_exit_r1"
DOCS_DIR = ROOT / "docs/strategy_research/g2_conditional_exit_r1"
EXIT_R1_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_exit_horizon_r1"
B_R2_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_goal_b_asof_repair_r2"
R31_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31"

CANDIDATE_IDS = (
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
)

BASELINE_SCHEMES = ("E0", "H1")
CONDITIONAL_SCHEMES = (
    "X1_NET_POSITIVE_AT_12H",
    "X2_COMPLETED_4H_TREND_AT_12H",
)
ALL_SCHEMES = (*BASELINE_SCHEMES, *CONDITIONAL_SCHEMES)

CONTRASTS = (
    ("X1_NET_POSITIVE_AT_12H", "E0"),
    ("X1_NET_POSITIVE_AT_12H", "H1"),
    ("X2_COMPLETED_4H_TREND_AT_12H", "E0"),
    ("X2_COMPLETED_4H_TREND_AT_12H", "H1"),
)

EXPECTED_ORIGINAL_EVENTS = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H": 34,
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H": 55,
}

EXPECTED_ORIGINAL_STRESS_TIME_CAPS = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H": 20,
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H": 36,
}

EXPECTED_ORIGINAL_H1_MINUS_E0_STRESS_BPS = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H": 37.345251625080365,
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H": 22.434225789691734,
}

EXPECTED_EXIT_R1_LEDGER_SHA256 = {
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_STRESS_paired.jsonl": (
        "f8d10f8a8e7d16046c2d207bf12250d63f3cc1c1ec0b3d26a692c4317f8d2d8a"
    ),
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_STRESS_E0_orders.jsonl": (
        "1c083656fb4bb66c206c4d879fbf09d9ce1cf240c58c73f67b91c07c5c15f943"
    ),
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_STRESS_H1_orders.jsonl": (
        "a7a1d8b01edad6f39bc156193a5040cf1949ee45c25be5e242892ab86e937444"
    ),
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_BASE_paired.jsonl": (
        "acda3f0996931b551750e41eebc5a124127e1dac84821197264f76a3e63b00a5"
    ),
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_BASE_E0_orders.jsonl": (
        "7d383d0256f4afea8a9956ddfe5f45afd129e167a45327f579f72ef84a4ef496"
    ),
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_BASE_H1_orders.jsonl": (
        "38437985dbb11ecfcd69e00fd305b09834725c3dcbffe23247be126f10729c6e"
    ),
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_STRESS_paired.jsonl": (
        "c27a8dabafd4b8e9949aa94fe76f524104481395294e812ca630a73c28db7847"
    ),
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_STRESS_E0_orders.jsonl": (
        "be22694a2737cf80af50d62741091b47778b71139deb3da861799432a44df445"
    ),
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_STRESS_H1_orders.jsonl": (
        "1f034d1195955d64a5373d3456e7772809198216ceddf2e91bbd352807e6b02f"
    ),
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_BASE_paired.jsonl": (
        "4e417da29f07c85884199647c284031ca4c84801b48b0170bfd8f9f5e06be4b2"
    ),
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_BASE_E0_orders.jsonl": (
        "9fb80199d02ba5e3460c1c3ac35cb38b70a77d200cb189e2500db011f10a735f"
    ),
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_BASE_H1_orders.jsonl": (
        "28824ecf3df3c725030d38f8a495348baf74e468daf1cb443537b71ec312535d"
    ),
}

EXPECTED_R31_MANIFEST_SHA256 = "1f06a24b892a24430f3d2f9e5f2c46e926ed24a437785614c400a1fa536b677c"

TERMINAL_CANDIDATE_SIGNAL = "X1_X2_DEVELOPMENT_ONLY_CANDIDATE_SIGNAL"
TERMINAL_INSUFFICIENT_SUPPORT = "X1_X2_INSUFFICIENT_SUPPORT"
TERMINAL_METHOD_OR_SOURCE_BLOCKED = "X1_X2_METHOD_OR_SOURCE_BLOCKED"
VALID_TERMINALS = (
    TERMINAL_CANDIDATE_SIGNAL,
    TERMINAL_INSUFFICIENT_SUPPORT,
    TERMINAL_METHOD_OR_SOURCE_BLOCKED,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
