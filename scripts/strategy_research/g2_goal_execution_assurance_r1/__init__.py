"""Independent BTC Exit-Book / Funding / Mark / Risk Execution Assurance (Gemini Goal C).

Read-only adversarial audit sidecar for R2, R3, R3.1, and Exit R1.
Does not define any new selectable trading strategy, threshold, or live/testnet interface.
"""
from __future__ import annotations

from pathlib import Path

TASK_ID = "V06_G2_GEMINI_GOAL_C_EXECUTION_ASSURANCE_R1"
PREFIX = "g2_goal_execution_assurance_r1"
CONTROLLER_DISPATCH_SHA = "c02743fddccdf517582c371a47e82d8dcbb05923"
EXACT_START_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
FROZEN_R1_SHA = "de2c1fb222970a93ca797868b91b8544261ebaad"
FINAL_R1_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
R31_DELIVERY_SHA = "990c02b5479b3b14996f90fdbf677cb672ada81e"
R31_FREEZE_SHA = "c36df02efab4c977b6dc823d0d92ff24de6f3a3e"
R2_DELIVERY_SHA = "d2477c12d39c627c443da9e59ff8381d485aa951"

ROOT = Path(__file__).resolve().parents[3]
SCRATCH = Path("/tmp/btc-gemini-execution-assurance-r1")
R3_CACHE = Path("/tmp/btc-two-lead-funding-mark-r3")
R31_CACHE = Path("/tmp/btc-two-lead-mark-gap-r31")
R1_CACHE = Path("/tmp/btc-exit-horizon-r1")

EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_goal_execution_assurance_r1"
DOCS_DIR = ROOT / "docs/strategy_research/g2_goal_execution_assurance_r1"
R1_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_exit_horizon_r1"
R31_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31"
R3_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_btc_two_lead_funding_mark_r3"
R2_EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1"

TERMINAL_COMPLETE = "EXECUTION_INDEPENDENT_DIAGNOSTIC_COMPLETE"
TERMINAL_DEFECT = "EXECUTION_MATERIAL_DEFECT_FOUND_STOP"
TERMINAL_INCONCLUSIVE = "EXECUTION_INCONCLUSIVE"
