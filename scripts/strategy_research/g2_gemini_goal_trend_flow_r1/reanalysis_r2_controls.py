"""Nontradable, event-matched controls and explicit funding stress scenarios.

These diagnostics never select an entry or change an accepted strategy trade.
The funding rates are hypothetical; no historical funding observation is read.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .replay import HOUR, _effective, _fee, episode


def _pair_mtm_diagnostic(
    data: np.ndarray, legs: dict[int, dict[str, Any]], cost: dict[str, float]
) -> dict[str, float | int]:
    """Mark one matched pair against a diagnostic 1000 USDT reference.

    This is deliberately local to a single accepted event. Different pairs
    may overlap and must never be concatenated as a funded control portfolio.
    """
    first = int(legs[1]["entry_index"])
    last = max(int(leg["exit_index"]) for leg in legs.values())
    peak = 1000.0
    trough = 1000.0
    max_dd = 0.0
    for idx in range(first, last + 1):
        minute = int(data[idx, 0])
        pair_pnl = 0.0
        for leg in legs.values():
            if idx >= leg["exit_index"] or minute >= leg["exit_at"]:
                pair_pnl += float(leg["net_usdt"])
            else:
                liquidation = _effective(float(data[idx, 4]), int(leg["side"]), cost, False)
                q = float(leg["quantity"])
                pair_pnl += (
                    int(leg["side"]) * (liquidation - float(leg["effective_entry"])) * q
                    - float(leg["fee_entry"]) - _fee(liquidation, q, cost)
                )
        equity = 1000.0 + pair_pnl
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("Insolvent matched-pair diagnostic mark")
        peak = max(peak, equity)
        trough = min(trough, equity)
        max_dd = max(max_dd, 100 * (peak - equity) / peak)
    return {
        "pair_mtm_minutes": last - first + 1,
        "pair_min_mtm_equity_on_1000_usdt": trough,
        "pair_max_mtm_drawdown_pct_on_1000_usdt": max_dd,
        "pair_entry_cash_proxy_usdt": sum(
            float(leg["effective_entry"]) * float(leg["quantity"]) + float(leg["fee_entry"])
            for leg in legs.values()
        ),
    }


def matched_control(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    actual_trade: dict[str, Any],
) -> dict[str, Any]:
    """Replay both signs at the accepted trade's time and half its quantity.

    The two legs have the same *total* raw entry notional as the actual trade.
    Each uses the original raw risk distance reflected about the entry open,
    with the same target-R, horizon, exit priority, and execution costs. The
    pair is a nontradable counterfactual, not a second cash account or signal.
    """
    if int(event["entry_at"]) != int(actual_trade["entry_at"]):
        raise ValueError("Control must share accepted entry clock")
    if int(event["side"]) != int(actual_trade["side"]):
        raise ValueError("Control must share accepted strategy direction")
    total_quantity = float(actual_trade["quantity"])
    if not math.isfinite(total_quantity) or total_quantity <= 0:
        raise ValueError("Invalid accepted quantity")
    if not math.isclose(
        float(actual_trade["entry_notional"]),
        float(actual_trade["raw_entry"]) * total_quantity,
        rel_tol=0,
        abs_tol=1e-7,
    ):
        raise ValueError("Accepted trade notional is inconsistent")
    legs = {
        sign: episode(data, event, candidate, cost, side_override=sign, quantity=total_quantity / 2)
        for sign in (1, -1)
    }
    if any(leg["entry_at"] != actual_trade["entry_at"] for leg in legs.values()):
        raise ValueError("Control entry clock drifted")
    if any(leg["raw_entry"] != actual_trade["raw_entry"] for leg in legs.values()):
        raise ValueError("Control entry price drifted")
    own = legs[int(actual_trade["side"])]
    if not math.isclose(
        own["net_bps"], float(actual_trade["net_bps"]), rel_tol=0, abs_tol=1e-7
    ):
        raise ValueError("Accepted trade differs from event-matched own-side replay")
    raw_risk = abs(float(actual_trade["raw_entry"]) - float(event["stop"]))
    if any(not math.isclose(
        abs(float(actual_trade["raw_entry"]) - float(leg["stop"])),
        raw_risk,
        rel_tol=0,
        abs_tol=0.1000001,
    ) for leg in legs.values()):
        raise ValueError("Control raw risk distance drifted")
    control_usdt = sum(float(leg["net_usdt"]) for leg in legs.values())
    control_bps = 10_000 * control_usdt / float(actual_trade["entry_notional"])
    return {
        "event_id": actual_trade["event_id"],
        "entry_at": actual_trade["entry_at"],
        "pause_net_usdt": 0.0,
        "pause_net_bps": 0.0,
        "balanced_net_usdt": control_usdt,
        "balanced_net_bps": control_bps,
        "paired_increment_bps": float(actual_trade["net_bps"]) - control_bps,
        "total_quantity": total_quantity,
        "long": legs[1],
        "short": legs[-1],
        "nontradable": True,
        **_pair_mtm_diagnostic(data, legs, cost),
    }


def funding_sensitivity(
    trade: dict[str, Any],
    rate_bps: float,
    *,
    cadence_hours: int = 8,
    offset_seconds: int = 0,
    adverse_only: bool = False,
) -> dict[str, float | int | str]:
    """Apply invented signed settlement rates to an already fixed trade.

    8h denotes the hypothesized UTC 00/08/16 schedule. Hourly denotes a
    conservative unknown-cadence stress. Settlements at entry are counted and
    at exit are excluded; ±15s offsets expose boundary uncertainty. A positive
    signed rate debits a long and credits a short. ``adverse_only`` charges
    either side and must never be described as observed funding.
    """
    if cadence_hours not in (1, 8) or offset_seconds not in (-15, 0, 15):
        raise ValueError("Only frozen hourly/eight-hour and ±15s clocks are supported")
    if not math.isfinite(rate_bps):
        raise ValueError("Funding scenario rate must be finite")
    entry = int(trade["entry_at"])
    exit_at = int(trade["exit_at"])
    side = int(trade["side"])
    notional = float(trade["entry_notional"])
    if entry < 0 or exit_at < entry or side not in (-1, 1) or notional <= 0:
        raise ValueError("Invalid trade funding interval or notional")
    period = cadence_hours * HOUR
    offset = offset_seconds * 1000
    first = ((entry - offset + period - 1) // period) * period + offset
    count = max(0, (exit_at - first + period - 1) // period)
    signed_cash = -notional * count * (
        abs(rate_bps) if adverse_only else side * rate_bps
    ) / 10_000
    funding_bps = 10_000 * signed_cash / notional
    return {
        "scenario": "ADVERSE_ONLY_UNKNOWN_CADENCE" if adverse_only else "SIGNED_RATE_HYPOTHESIS",
        "cadence_hours": cadence_hours,
        "offset_seconds": offset_seconds,
        "rate_bps_per_settlement": rate_bps,
        "settlement_count": count,
        "funding_cash_usdt": signed_cash,
        "funding_bps": funding_bps,
        "net_after_funding_bps": float(trade["net_bps"]) + funding_bps,
    }
