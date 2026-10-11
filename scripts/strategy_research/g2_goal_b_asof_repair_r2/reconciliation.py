"""Audit reconciliation and discrepancy matrix for Goal B R1 vs R2."""

from __future__ import annotations

from typing import Any

from .contract import FORMAL_REVOCATIONS


def build_reconciliation_matrix() -> dict[str, Any]:
    """Build structured discrepancy and claim-revocation comparison matrix."""
    return {
        "title": "Goal B R1 Claim Revocation and Machine-to-Human Reconciliation Matrix",
        "revocations": FORMAL_REVOCATIONS,
        "discrepancies": {
            "w2_annual_trade_counts": {
                "metric": "W2_C05 annual trade counts (2021, 2022, 2023)",
                "exit_r1_machine_truth": {"2021": 10, "2022": 21, "2023": 24, "total": 55},
                "r1_human_report_table_4": {"2021": 14, "2022": 17, "2023": 24, "total": 55},
                "delta": {"2021": -4, "2022": +4, "2023": 0, "total": 0},
                "status": "RECONCILED_MACHINE_TRUTH_PRESERVED",
                "root_cause": (
                    "Human copy-paste transposition in R1 report markdown table. "
                    "Underlying machine ledger always contained 10 (2021) and 21 (2022)."
                ),
            },
            "account_skipped_signals": {
                "metric": "Opportunity cost simulation blocked / skipped signal counts",
                "exit_r1_machine_truth": {
                    "W1": {"E0": 42, "H1": 42, "H2": 42, "intra_trade_cooldown": 30},
                    "W2": {"E0": 46, "H1": 46, "H2": 46, "intra_trade_cooldown": 38},
                },
                "r1_human_report_table_3": {
                    "W1": {"E0": 0, "H1": 42, "H2": 42},
                    "W2": {"E0": 0, "H1": 46, "H2": 46},
                },
                "status": "RECONCILED_MACHINE_TRUTH_RESTORED",
                "root_cause": (
                    "Human table set E0 to 0 because E0 was the reference baseline, "
                    "masking that E0 also blocked burst signals arriving within its 12h hold. "
                    "Critically, ZERO additional signals were missed in (12h, 24h) extended windows."
                ),
            },
            "cost_model_parameters": {
                "metric": "BASE22 and STRESS44 round-trip friction vectors",
                "commit_1_intermediate": {
                    "BASE": {"fee": 12.0, "spread": 4.0, "slippage": 8.0, "total": 24.0},
                    "STRESS": {"fee": 24.0, "spread": 8.0, "slippage": 16.0, "total": 48.0},
                },
                "commit_2_frozen_truth": {
                    "BASE": {"fee": 12.0, "spread": 4.0, "slippage": 6.0, "total": 22.0},
                    "STRESS": {"fee": 24.0, "spread": 8.0, "slippage": 12.0, "total": 44.0},
                },
                "status": "FROZEN_CONFORMANT_WITH_EXIT_R1",
                "root_cause": (
                    "Temporary slippage discrepancy in R1 Commit 1 was corrected in Commit 2. "
                    "All R2 analyses strictly use frozen BASE22 and STRESS44."
                ),
            },
            "asof_feature_leakage": {
                "metric": "As-of feature definitions and implementation",
                "r1_defect_lines": {
                    "trend": "run.py lines 136-142: path24h.before12h.Last_MFE_R vs Last_MAE_R (future [0,12h) leak)",
                    "volatility": "run.py lines 145-146: risk_bps > 300 (trade risk substitute, not 90d ATR)",
                    "funding": "run.py lines 149-154: e0['funding_settlements'][0] (in-trade post-entry settlement leak)",
                },
                "r2_repaired_implementation": {
                    "trend": "asof_features.py: strictly prior 240 1m LAST bars ending <= signal decision clock",
                    "volatility": "asof_features.py: expanding strictly prior-only 90d (2160h) completed 1h Wilder ATR14 / Close median",
                    "funding": "asof_features.py: latest official settlement strictly before signal decision clock",
                },
                "status": "DEFECTS_REVOKED__STRICT_ASOF_RECONSTRUCTED",
            },
        },
    }
