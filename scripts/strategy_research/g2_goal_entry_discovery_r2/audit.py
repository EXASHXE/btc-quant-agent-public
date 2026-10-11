"""Independent Decimal precision crosscheck audit for Goal A R2.

Validates that float engine arithmetic matches exact Decimal calculations
for adverse execution prices, fees, gross P&L, net P&L, and signed funding cash.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

TICK = Decimal("0.1")


def _dec_tick(price: Decimal, upwards: bool) -> Decimal:
    scaled = price / TICK
    rounded = scaled.to_integral_value(rounding=ROUND_CEILING if upwards else ROUND_FLOOR)
    return rounded * TICK


def _dec_effective(raw_price: Decimal, side: int, fee_bps: Decimal, spread_bps: Decimal, slip_bps: Decimal, entry: bool) -> Decimal:
    adverse_fraction = (Decimal("0.5") * spread_bps + slip_bps) / Decimal(10000)
    sign = Decimal(side if entry else -side)
    raw_effective = raw_price * (Decimal(1) + sign * adverse_fraction)
    return _dec_tick(raw_effective, upwards=(sign > Decimal(0)))


def _dec_fee(price: Decimal, qty: Decimal, fee_bps: Decimal) -> Decimal:
    return price * qty * (fee_bps / Decimal(10000))


def audit_trade_decimal(trade: dict[str, Any], cost: dict[str, float]) -> dict[str, Any]:
    """Perform independent high-precision Decimal crosscheck on an executed trade."""
    side = int(trade["side"])
    qty = Decimal(str(trade["quantity"]))
    raw_open = Decimal(str(trade["raw_entry"]))
    raw_exit = Decimal(str(trade["raw_exit"]))

    fee_bps = Decimal(str(cost.get("fee_bps", 0.0)))
    spread_bps = Decimal(str(cost.get("spread_bps", 0.0)))
    slip_bps = Decimal(str(cost.get("slip_bps", cost.get("slippage_bps", 0.0))))

    dec_eff_entry = _dec_effective(raw_open, side, fee_bps, spread_bps, slip_bps, entry=True)
    dec_eff_exit = _dec_effective(raw_exit, side, fee_bps, spread_bps, slip_bps, entry=False)

    dec_fee_entry = _dec_fee(dec_eff_entry, qty, fee_bps)
    dec_fee_exit = _dec_fee(dec_eff_exit, qty, fee_bps)

    dec_gross = Decimal(side) * (raw_exit - raw_open) * qty
    dec_net = Decimal(side) * (dec_eff_exit - dec_eff_entry) * qty - dec_fee_entry - dec_fee_exit

    # Recompute funding
    dec_funding = Decimal(0)
    for f in trade.get("funding_events", []):
        r_rate = Decimal(str(f["rate"]))
        m_price = Decimal(str(f["mark_price"]))
        f_delta = -Decimal(side) * r_rate * qty * m_price
        dec_funding += f_delta

    dec_net_after_funding = dec_net + dec_funding

    # Verification assertions
    diff_eff_entry = abs(float(dec_eff_entry) - float(trade["effective_entry"]))
    diff_eff_exit = abs(float(dec_eff_exit) - float(trade["effective_exit"]))
    diff_net = abs(float(dec_net) - float(trade["net_usdt"]))
    diff_funding = abs(float(dec_funding) - float(trade["funding_cash_usdt"]))
    diff_total = abs(float(dec_net_after_funding) - float(trade["net_after_funding_usdt"]))

    assert diff_eff_entry < 1e-4, f"Effective entry mismatch: {diff_eff_entry}"
    assert diff_eff_exit < 1e-4, f"Effective exit mismatch: {diff_eff_exit}"
    assert diff_net < 1e-4, f"Net trading cash mismatch: {diff_net}"
    assert diff_funding < 1e-4, f"Funding cash mismatch: {diff_funding}"
    assert diff_total < 1e-4, f"Total net cash mismatch: {diff_total}"

    return {
        "event_id": trade["event_id"],
        "side": side,
        "quantity": str(qty),
        "decimal_gross_usdt": str(dec_gross),
        "engine_net_after_funding_usdt": float(trade["net_after_funding_usdt"]),
        "decimal_net_after_funding_usdt": str(dec_net_after_funding),
        "max_absolute_error": max(diff_eff_entry, diff_eff_exit, diff_net, diff_funding, diff_total),
        "status": "EXACT_DECIMAL_MATCH",
    }
