"""Gemini Goal C R2 — Independent Margin, Synthetic Liquidation, and Forensic Audit Truth Repair.

Strictly read-only with respect to R2, R3, R3.1, Exit R1, and Goal C R1 code and artifacts.
Produces an auditable contradiction resolution across:
1. Goal C R1 3-commit freeze provenance and CI docs-only skip truth;
2. All 20 Exit R1 1x account exposure cells (reconstructing E0 per-minute open q and Mark notional/equity);
3. All 32 Goal C R1 synthetic margin scenarios (recomputing Decimal rows and exact filtered denominators)
   plus a new 56-scenario deterministic synthetic margin/liquidation/gap/ACK fixture matrix;
4. Real 2021-2023 1R stop distance distributions (max 3.6120% W1, 3.5591% W2) vs synthetic 7.5% stop
   scenarios and closed-form Decimal 10x/15x liquidation inequalities;
5. Independent re-audit of 24 stratified real R1 ledger episodes and all 890 order-ledger trades;
6. Design-only future TESTNET readiness prerequisites.
"""
from __future__ import annotations

from pathlib import Path

TASK_ID = "V06_G2_GOAL_C_RISK_ASSURANCE_R2"
OWN_PREFIX = "g2_goal_c_risk_assurance_r2"
BRANCH_NAME = "feature/v06-bline-gemini-goal-c-risk-assurance-r2"
REPOSITORY = "EXASHXE/btc-quant-agent-public"

CONTROLLER_DISPATCH_SHA = "1172d3a91324c1a7379bc9e5c24ef601076547c2"
AUTHORITY_URL = (
    "https://github.com/EXASHXE/btc-quant-agent-public/blob/"
    "1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/"
    "V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md"
)

EXACT_START_SHA = "f381dd73a8c583e2a28dcab2e354b019b1d946fa"
C_R1_FROZEN_SHA = "8db2e3ff36011c6a65458f8cf4c2ba5e90d5fee2"
C_R1_MID_REPAIR_SHA = "4c0bac051767f788e6de173f6563a7b47af2ac69"
C_R1_FINAL_SHA = "f381dd73a8c583e2a28dcab2e354b019b1d946fa"

ORIGINAL_EXIT_R1_FROZEN_SHA = "de2c1fb222970a93ca797868b91b8544261ebaad"
ORIGINAL_EXIT_R1_FINAL_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
ORIGINAL_EXIT_R1_PARENT_SHA = "990c02b5479b3b14996f90fdbf677cb672ada81e"
ORIGINAL_R2_START_SHA = "d2477c1aaff601e0740a6899e60d85224c75a4dc"

TERMINAL_RECONCILED = "C_R2_MARGIN_RISK_EVIDENCE_RECONCILED_SYNTHETIC_ONLY"
TERMINAL_FAIL_CLOSED = "C_R2_MATERIAL_MARGIN_OR_EXPOSURE_DEFECT_FAIL_CLOSED"
TERMINAL_INCONCLUSIVE = "C_R2_INCONCLUSIVE_SOURCE_OR_FREEZE_REPAIR"

ROOT = Path(__file__).resolve().parents[3]
OWN_SCRIPTS_DIR = ROOT / "scripts/strategy_research/g2_goal_c_risk_assurance_r2"
OWN_DOCS_DIR = ROOT / "docs/strategy_research/g2_goal_c_risk_assurance_r2"
OWN_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_goal_c_risk_assurance_r2"
OWN_SCRATCH_DIR = Path("/tmp/btc-gemini-goal-c-risk-assurance-r2")

C_R1_SCRIPTS_DIR = ROOT / "scripts/strategy_research/g2_goal_execution_assurance_r1"
C_R1_DOCS_DIR = ROOT / "docs/strategy_research/g2_goal_execution_assurance_r1"
C_R1_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_goal_execution_assurance_r1"

EXIT_R1_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_exit_horizon_r1"
R31_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31"
R3_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_funding_mark_r3"
R2_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1"

R3_CACHE_DIR = Path("/tmp/btc-two-lead-funding-mark-r3")
R31_CACHE_DIR = Path("/tmp/btc-two-lead-mark-gap-r31")
EXIT_R1_CACHE_DIR = Path("/tmp/btc-exit-horizon-r1")

CANDIDATE_IDS = (
    "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
    "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
)
COST_NAMES = ("BASE", "STRESS")
SCHEMES = ("E0", "H1", "H2", "E1", "E2")
