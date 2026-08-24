from __future__ import annotations

from typing import Any

from .domain import Signal


def explain_signal(signal: Signal) -> dict[str, Any]:
    return {
        "signal_id": signal.signal_id,
        "summary": (
            f"{signal.symbol} {signal.direction.value} / {signal.setup.value}，"
            f"净盈亏比 {signal.rr_net:.2f}。"
        ),
        "reasons": signal.reasons,
        "risks": signal.risks,
        "factor_scores": signal.factor_scores,
        "factor_evidence": signal.factor_evidence,
        "positive_factor_groups": signal.positive_factor_groups,
        "numbers_are_immutable": True,
        "statistical_probability": ("not calibrated" if signal.p_win is None else signal.p_win),
        "validation_status": signal.validation_status,
    }
