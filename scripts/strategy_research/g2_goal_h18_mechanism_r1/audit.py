"""Independent Decimal and standard library audit of real event decompositions."""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

D_ONE_TICK = Decimal("0.1")
D_TEN_THOUSAND = Decimal(10000)


def D(v: Any) -> Decimal:
    """Convert value to exact Decimal via string representation."""
    return Decimal(str(v))


def decimal_effective_price(
    raw_price: Decimal,
    side: int,
    spread_bps: Decimal,
    slip_bps: Decimal,
    is_entry: bool,
) -> Decimal:
    """Compute tick-rounded effective price independently in Decimal arithmetic."""
    direction = side if is_entry else -side
    adverse = (spread_bps / Decimal(2) + slip_bps) / D_TEN_THOUSAND
    val = raw_price * (Decimal(1) + Decimal(direction) * adverse)
    units = val / D_ONE_TICK
    rounding = ROUND_CEILING if direction > 0 else ROUND_FLOOR
    return units.to_integral_value(rounding=rounding) * D_ONE_TICK


def audit_event_decimal(
    trade: dict[str, Any],
    cost_model: dict[str, Any],
) -> dict[str, Any]:
    """Audit a single trade using independent Decimal calculations."""
    q = D(trade["quantity"])
    side = int(trade["side"])
    raw_entry = D(trade["raw_entry"])
    raw_exit = D(trade["raw_exit"])
    notional = D(trade["entry_notional"])

    fee_bps = D(cost_model["fee_bps"])
    spread_bps = D(cost_model["spread_bps"])
    slip_bps = D(cost_model.get("slip_bps", cost_model.get("slippage_bps", 0)))

    # Reconstruct effective entry and exit
    calc_eff_entry = decimal_effective_price(raw_entry, side, spread_bps, slip_bps, is_entry=True)
    calc_eff_exit = decimal_effective_price(raw_exit, side, spread_bps, slip_bps, is_entry=False)

    record_eff_entry = D(trade["effective_entry"])
    record_eff_exit = D(trade["effective_exit"])

    diff_entry = abs(calc_eff_entry - record_eff_entry)
    diff_exit = abs(calc_eff_exit - record_eff_exit)
    assert diff_entry < Decimal("1e-6"), f"Entry tick mismatch: {diff_entry}"
    assert diff_exit < Decimal("1e-6"), f"Exit tick mismatch: {diff_exit}"

    # Fees
    calc_fee_entry = calc_eff_entry * q * (fee_bps / D_TEN_THOUSAND)
    calc_fee_exit = calc_eff_exit * q * (fee_bps / D_TEN_THOUSAND)

    # Effective price PnL
    calc_price_pnl = Decimal(side) * (calc_eff_exit - calc_eff_entry) * q

    # Funding settlements
    calc_funding_cash = Decimal(0)
    for s in trade.get("funding_settlements", []):
        s_side = int(s["side"])
        s_q = D(s["quantity"])
        s_mark = D(s["settlement_mark"])
        s_rate = D(s["source_rate_fraction"])
        # In USDT-M perps, funding cash = - side * Q * mark * rate
        # Long pays when rate > 0: - (+1) * Q * mark * rate
        s_cash = - Decimal(s_side) * s_q * s_mark * s_rate
        calc_funding_cash += s_cash

    calc_net_usdt = calc_price_pnl + calc_funding_cash - calc_fee_entry - calc_fee_exit
    calc_net_bps = (calc_net_usdt / notional) * D_TEN_THOUSAND

    record_net_usdt = D(trade["net_after_funding_usdt"])
    record_net_bps = D(trade["net_after_funding_bps"])

    diff_net_usdt = abs(calc_net_usdt - record_net_usdt)
    diff_net_bps = abs(calc_net_bps - record_net_bps)

    assert diff_net_usdt < Decimal("1e-4"), f"Net USDT mismatch: {diff_net_usdt}"
    assert diff_net_bps < Decimal("1e-3"), f"Net bps mismatch: {diff_net_bps}"

    return {
        "event_id": trade["event_id"],
        "scheme": trade["scheme"],
        "side": side,
        "quantity": str(q),
        "calc_effective_entry": str(calc_eff_entry),
        "calc_effective_exit": str(calc_eff_exit),
        "calc_price_pnl_usdt": str(calc_price_pnl),
        "calc_funding_cash_usdt": str(calc_funding_cash),
        "calc_fee_entry_usdt": str(calc_fee_entry),
        "calc_fee_exit_usdt": str(calc_fee_exit),
        "calc_net_usdt": str(calc_net_usdt),
        "calc_net_bps": str(calc_net_bps),
        "audit_passed": True,
    }


def audit_contrast_decimal(
    trade_new: dict[str, Any],
    trade_old: dict[str, Any],
    cost_model: dict[str, Any],
) -> dict[str, Any]:
    """Audit contrast decomposition in exact Decimal arithmetic."""
    a_new = audit_event_decimal(trade_new, cost_model)
    a_old = audit_event_decimal(trade_old, cost_model)

    d_net_usdt = D(a_new["calc_net_usdt"]) - D(a_old["calc_net_usdt"])
    d_price_usdt = D(a_new["calc_price_pnl_usdt"]) - D(a_old["calc_price_pnl_usdt"])
    d_funding_usdt = D(a_new["calc_funding_cash_usdt"]) - D(a_old["calc_funding_cash_usdt"])
    d_exit_fee_usdt = D(a_new["calc_fee_exit_usdt"]) - D(a_old["calc_fee_exit_usdt"])

    # Identity: Delta Net = Delta Price + Delta Funding - Delta Exit Fee
    reconstructed_delta = d_price_usdt + d_funding_usdt - d_exit_fee_usdt
    diff = abs(reconstructed_delta - d_net_usdt)
    assert diff < Decimal("1e-6"), f"Decimal contrast identity discrepancy: {diff}"

    notional = D(trade_new["entry_notional"])
    d_net_bps = (d_net_usdt / notional) * D_TEN_THOUSAND

    return {
        "event_id": trade_new["event_id"],
        "contrast": f"{trade_new['scheme']}-{trade_old['scheme']}",
        "delta_net_usdt": str(d_net_usdt),
        "delta_net_bps": str(d_net_bps),
        "delta_price_usdt": str(d_price_usdt),
        "delta_funding_usdt": str(d_funding_usdt),
        "delta_exit_fee_usdt": str(d_exit_fee_usdt),
        "identity_reproduced_exact": True,
    }
