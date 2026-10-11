"""Prospective experimental protocol and formal method design for future D1/D2 policies.

DESIGN ONLY: Explicitly non-executed in Goal B. No new backtests or selectable trials.
Requires fresh Controller authority before any prospective or historical evaluation.
"""
from __future__ import annotations

from typing import Any

PROSPECTIVE_D1_SPECIFICATION = {
    "policy_id": "D1_CONDITIONAL_12TO24H_MOMENTUM_GATE",
    "status": "DESIGN_ONLY_NON_EXECUTED",
    "rationale": (
        "Empirical Goal B findings demonstrate that 12->18h continuation is nearly a 50/50 "
        "coin-flip (53.6% favorable, 46.4% adverse), while 18->24h suffers from momentum exhaustion "
        "and increased stopouts. A conditional gate at t=12h could prospectively test whether "
        "unfavorable trades can be cut at 12h while high-momentum trades extend to 24h."
    ),
    "decision_epoch": "Strictly at t = entry_at + 12*HOUR, using completed 1m/1h bars as-of t=12h",
    "gate_features": [
        "completed_12h_unrealized_return_R (must be > +0.5R)",
        "completed_1h_flow_ratio_asof_12h (must be aligned with position side)",
        "completed_1h_close_relative_to_entry (no adverse trend breach)",
    ],
    "action": "If all gate criteria satisfied, extend exit deadline to 24h; else execute market exit at 12h + 1m ACK",
    "fill_assumptions": "Conservative taker exit at 12h + 1m under frozen STRESS44 friction",
    "sample_size_feasibility": {
        "historical_support": "56 total baseline TIME_CAP events across 35 months (~1.6 events/month)",
        "statistical_power": (
            "Extremely low power (N < 30 per candidate). Splitting 56 events into conditional branches "
            "results in < 15 events per branch, severely vulnerable to p-hacking and tail overfitting."
        ),
    },
    "falsification_conditions": [
        "D1 fails if its net bps does not exceed the unconditional E0 (12h) baseline by at least 25 bps.",
        "D1 fails if its net bps does not exceed unconditional H1 (18h) after accounting for conditional selection penalty.",
        "D1 fails if 2023 performance remains net negative.",
    ],
    "prerequisites": "Explicit Controller authority and formal registration before any historical run.",
}

PROSPECTIVE_D2_SPECIFICATION = {
    "policy_id": "D2_ATR_TRAILING_TRACKING",
    "status": "DESIGN_ONLY_NON_EXECUTED",
    "rationale": (
        "Empirical Goal B findings demonstrate that trades hitting TARGET between 12h and 18h "
        "account for >75% of H1 gains, while trades extending to 24h frequently reverse and hit STOP. "
        "An ATR trailing stop activated after t=12h could prospectively test profit protection."
    ),
    "activation_epoch": "Strictly at t = entry_at + 12*HOUR, only if position is still open",
    "trailing_distance": "1.5 * completed 1h ATR(14) as-of t=12h",
    "ratchet_frequency": "Evaluated at each completed 1m bar; stop ratchet only moves favorably, never backwards",
    "execution_budget": "Taker stop execution with 1-tick adverse slippage and 1-bar ACK delay",
    "sample_size_feasibility": {
        "statistical_power": (
            "Severely underpowered in existing 2021-2023 development sample (56 eligible events). "
            "Simulating multiple trailing multipliers (1.0, 1.5, 2.0 ATR) would constitute multiple-testing hunting."
        ),
    },
    "falsification_conditions": [
        "D2 fails if premature whipsaw stopouts reduce total net bps below E0.",
        "D2 fails if maximum drawdown is not reduced by at least 15% relative to H2.",
    ],
    "prerequisites": "Explicit Controller authority and formal registration before any historical run.",
}


def get_prospective_protocol_summary() -> dict[str, Any]:
    """Return structured specification of prospective D1 and D2 designs."""
    return {
        "status": "PROSPECTIVE_PROTOCOL_FROZEN_NON_EXECUTED",
        "new_selectable_policies_executed_now": 0,
        "D1_conditional_extension": PROSPECTIVE_D1_SPECIFICATION,
        "D2_atr_trailing": PROSPECTIVE_D2_SPECIFICATION,
        "controller_gate_required": True,
    }
