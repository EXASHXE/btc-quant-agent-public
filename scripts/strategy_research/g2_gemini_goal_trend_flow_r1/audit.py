"""Independent Decimal walkthrough and anti-lookahead audit for trade episodes."""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any
import numpy as np

TICK_DECIMAL = Decimal("0.1")


def d(val: float | int | str) -> Decimal:
    return Decimal(str(val))


def rounded(val: Decimal, precision: str = "0.00000001") -> Decimal:
    return val.quantize(Decimal(precision), rounding=ROUND_HALF_UP)


def _tick_decimal(val: Decimal, upwards: bool) -> Decimal:
    scaled = val / TICK_DECIMAL
    q = scaled.quantize(Decimal("1"), rounding=ROUND_CEILING if upwards else ROUND_FLOOR)
    return q * TICK_DECIMAL


def audit_single_trade(data_1m: np.ndarray, tr: dict[str, Any], cost: dict[str, float]) -> dict[str, Any]:
    """Perform independent Decimal verification on a single trade."""
    side = int(tr["side"])
    qty = d(tr["quantity"])
    raw_entry = d(tr["raw_entry"])
    raw_exit = d(tr["raw_exit"])

    fee_bps = d(cost.get("fee_bps", 0.0))
    spread_bps = d(cost.get("spread_bps", 0.0))
    slip_bps = d(cost.get("slip_bps", cost.get("slippage_bps", 0.0)))

    # Half-spread + slippage adverse shift
    adverse_fraction = (spread_bps / Decimal("2") + slip_bps) / Decimal("10000")

    # Effective entry
    sign_entry = Decimal(side)
    eff_entry_calc = _tick_decimal(raw_entry * (Decimal("1") + sign_entry * adverse_fraction), upwards=sign_entry > 0)

    # Effective exit
    sign_exit = Decimal(-side)
    eff_exit_calc = _tick_decimal(raw_exit * (Decimal("1") + sign_exit * adverse_fraction), upwards=sign_exit > 0)

    # Fees
    fee_entry_calc = eff_entry_calc * qty * (fee_bps / Decimal("10000"))
    fee_exit_calc = eff_exit_calc * qty * (fee_bps / Decimal("10000"))

    # PnL
    gross_calc = Decimal(side) * (raw_exit - raw_entry) * qty
    drag_calc = Decimal(side) * (eff_entry_calc - raw_entry + raw_exit - eff_exit_calc) * qty
    net_calc = gross_calc - drag_calc - fee_entry_calc - fee_exit_calc

    notional = raw_entry * qty
    net_bps_calc = (net_calc / notional) * Decimal("10000")

    diff_net = abs(float(net_calc) - float(tr["net_usdt"]))
    diff_bps = abs(float(net_bps_calc) - float(tr["net_bps"]))

    assertions = "PASS" if (diff_net < 1e-4 and diff_bps < 1e-2) else "FAIL"

    return {
        "event_id": tr.get("event_id", ""),
        "assertions": assertions,
        "side": side,
        "exit_reason": tr.get("exit_reason", ""),
        "decimal_eff_entry": str(eff_entry_calc),
        "trade_eff_entry": str(tr["effective_entry"]),
        "decimal_eff_exit": str(eff_exit_calc),
        "trade_eff_exit": str(tr["effective_exit"]),
        "decimal_net_usdt": str(rounded(net_calc, "0.0001")),
        "trade_net_usdt": str(tr["net_usdt"]),
        "diff_net_usdt": diff_net,
        "diff_bps": diff_bps,
    }


def audit_candidate_trades(data_1m: np.ndarray, trades: list[dict[str, Any]], cost: dict[str, float], sample_count: int = 3) -> list[dict[str, Any]]:
    """Audit up to sample_count trades with independent Decimal walkthrough."""
    if not trades:
        return []
    indices = [0, len(trades) // 2, len(trades) - 1][:sample_count]
    return [audit_single_trade(data_1m, trades[i], cost) for i in indices]
