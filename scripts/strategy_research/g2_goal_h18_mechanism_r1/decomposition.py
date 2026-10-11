"""Exact price, funding, fee, and execution decomposition equations."""
from __future__ import annotations

from typing import Any


def decompose_trade(trade: dict[str, Any]) -> dict[str, Any]:
    """Decompose a single trade into price, funding, fee, and drag components."""
    q = float(trade["quantity"])
    side = int(trade["side"])
    raw_entry = float(trade["raw_entry"])
    raw_exit = float(trade["raw_exit"])
    eff_entry = float(trade["effective_entry"])
    eff_exit = float(trade["effective_exit"])
    notional = float(trade["entry_notional"])

    gross_price_pnl = side * (raw_exit - raw_entry) * q
    effective_price_pnl = side * (eff_exit - eff_entry) * q
    execution_drag = gross_price_pnl - effective_price_pnl

    funding_cash = float(trade["funding_cash_usdt"])
    fee_entry = float(trade["fee_entry"])
    fee_exit = float(trade["fee_exit"])
    total_fees = fee_entry + fee_exit

    net_after_funding_usdt = float(trade["net_after_funding_usdt"])
    net_after_funding_bps = float(trade["net_after_funding_bps"])

    # Cash identity check: effective price PnL + funding - total fees == net USDT
    reconstructed_net_usdt = effective_price_pnl + funding_cash - total_fees
    diff = abs(reconstructed_net_usdt - net_after_funding_usdt)
    assert diff < 1e-6, f"Cash identity violation: {diff} USDT discrepancy"

    return {
        "event_id": trade.get("event_id"),
        "candidate": trade.get("candidate"),
        "scheme": trade.get("scheme"),
        "side": side,
        "quantity": q,
        "entry_notional": notional,
        "raw_entry": raw_entry,
        "raw_exit": raw_exit,
        "effective_entry": eff_entry,
        "effective_exit": eff_exit,
        "gross_price_pnl_usdt": gross_price_pnl,
        "effective_price_pnl_usdt": effective_price_pnl,
        "execution_drag_usdt": execution_drag,
        "funding_cash_usdt": funding_cash,
        "fee_entry_usdt": fee_entry,
        "fee_exit_usdt": fee_exit,
        "total_fees_usdt": total_fees,
        "net_after_funding_usdt": net_after_funding_usdt,
        "net_after_funding_bps": net_after_funding_bps,
        "gross_bps": float(trade.get("gross_bps", (gross_price_pnl / notional) * 10000)),
        "exit_reason": trade.get("exit_reason"),
        "duration_minutes": float(trade.get("duration_minutes", 0)),
    }


def decompose_contrast(trade_new: dict[str, Any], trade_old: dict[str, Any]) -> dict[str, Any]:
    """Decompose the delta between two matched horizons for the exact same event.

    Delta Net USDT = Delta Effective Price PnL + Delta Funding Cash - Delta Exit Fee
    Entry fees, entry notional, and initial quantity are mathematically identical.
    """
    d_new = decompose_trade(trade_new)
    d_old = decompose_trade(trade_old)

    assert d_new["event_id"] == d_old["event_id"], "Contrasting mismatched events"
    notional = d_new["entry_notional"]

    delta_net_usdt = d_new["net_after_funding_usdt"] - d_old["net_after_funding_usdt"]
    delta_net_bps = d_new["net_after_funding_bps"] - d_old["net_after_funding_bps"]
    delta_gross_bps = d_new["gross_bps"] - d_old["gross_bps"]

    delta_effective_price_usdt = d_new["effective_price_pnl_usdt"] - d_old["effective_price_pnl_usdt"]
    delta_gross_price_usdt = d_new["gross_price_pnl_usdt"] - d_old["gross_price_pnl_usdt"]
    delta_funding_usdt = d_new["funding_cash_usdt"] - d_old["funding_cash_usdt"]
    delta_exit_fee_usdt = d_new["fee_exit_usdt"] - d_old["fee_exit_usdt"]
    delta_drag_usdt = d_new["execution_drag_usdt"] - d_old["execution_drag_usdt"]

    # Verify additive decomposition
    reconstructed_delta_net = delta_effective_price_usdt + delta_funding_usdt - delta_exit_fee_usdt
    diff = abs(reconstructed_delta_net - delta_net_usdt)
    assert diff < 1e-6, f"Contrast decomposition discrepancy: {diff} USDT"

    return {
        "event_id": d_new["event_id"],
        "scheme_new": d_new["scheme"],
        "scheme_old": d_old["scheme"],
        "side": d_new["side"],
        "entry_notional": notional,
        "delta_net_usdt": delta_net_usdt,
        "delta_net_bps": delta_net_bps,
        "delta_gross_bps": delta_gross_bps,
        "delta_effective_price_usdt": delta_effective_price_usdt,
        "delta_gross_price_usdt": delta_gross_price_usdt,
        "delta_funding_usdt": delta_funding_usdt,
        "delta_exit_fee_usdt": delta_exit_fee_usdt,
        "delta_drag_usdt": delta_drag_usdt,
        "delta_price_bps": (delta_effective_price_usdt / notional) * 10000,
        "delta_funding_bps": (delta_funding_usdt / notional) * 10000,
        "delta_fee_bps": (-delta_exit_fee_usdt / notional) * 10000,
        "exit_reason_new": d_new["exit_reason"],
        "exit_reason_old": d_old["exit_reason"],
        "duration_minutes_new": d_new["duration_minutes"],
        "duration_minutes_old": d_old["duration_minutes"],
    }


def aggregate_decomposition(contrasts: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-event decompositions into cohort totals and means."""
    if not contrasts:
        return {
            "count": 0,
            "mean_delta_net_bps": 0.0,
            "mean_delta_gross_bps": 0.0,
            "mean_delta_price_bps": 0.0,
            "mean_delta_funding_bps": 0.0,
            "mean_delta_fee_bps": 0.0,
            "total_delta_net_usdt": 0.0,
            "total_delta_price_usdt": 0.0,
            "total_delta_funding_usdt": 0.0,
            "total_delta_exit_fee_usdt": 0.0,
        }

    n = len(contrasts)
    mean_net_bps = sum(c["delta_net_bps"] for c in contrasts) / n
    mean_gross_bps = sum(c["delta_gross_bps"] for c in contrasts) / n
    mean_price_bps = sum(c["delta_price_bps"] for c in contrasts) / n
    mean_funding_bps = sum(c["delta_funding_bps"] for c in contrasts) / n
    mean_fee_bps = sum(c["delta_fee_bps"] for c in contrasts) / n

    total_net_usdt = sum(c["delta_net_usdt"] for c in contrasts)
    total_price_usdt = sum(c["delta_effective_price_usdt"] for c in contrasts)
    total_funding_usdt = sum(c["delta_funding_usdt"] for c in contrasts)
    total_exit_fee_usdt = sum(c["delta_exit_fee_usdt"] for c in contrasts)

    return {
        "count": n,
        "mean_delta_net_bps": mean_net_bps,
        "mean_delta_gross_bps": mean_gross_bps,
        "mean_delta_price_bps": mean_price_bps,
        "mean_delta_funding_bps": mean_funding_bps,
        "mean_delta_fee_bps": mean_fee_bps,
        "total_delta_net_usdt": total_net_usdt,
        "total_delta_price_usdt": total_price_usdt,
        "total_delta_funding_usdt": total_funding_usdt,
        "total_delta_exit_fee_usdt": total_exit_fee_usdt,
        "price_share_pct": (total_price_usdt / total_net_usdt * 100) if abs(total_net_usdt) > 1e-6 else 0.0,
        "funding_share_pct": (total_funding_usdt / total_net_usdt * 100) if abs(total_net_usdt) > 1e-6 else 0.0,
        "fee_share_pct": (-total_exit_fee_usdt / total_net_usdt * 100) if abs(total_net_usdt) > 1e-6 else 0.0,
    }
