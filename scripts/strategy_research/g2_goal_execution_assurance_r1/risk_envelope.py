"""Target 5: Capital, 1x exposure validation, and synthetic-only 10x/15x margin/liquidation harness.

Strictly separates verified 1x cash-cap/5%-reserve behavior from hypothetical leveraged margin mechanics.
Never multiplies 1x historical trade P&L by 10x/15x or claims empirical leveraged returns.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from .decimal_journal import (
    COST_MODELS_DEC,
    D,
    dec_effective_price,
)


def run_synthetic_leverage_scenario(
    *,
    scenario_id: str,
    side: int,
    leverage: float,
    mmr: float,
    clearance_fee_bps: float,
    entry_price: float,
    stop_distance_pct: float,
    intrabar_adverse_mark_pct: float,
    open_gap_adverse_pct: float,
    funding_rate_bps: float = 8.0,
    partial_tp1_before_shock: bool = False,
    sizing_mode: str = "NAIVE_FULL_LEVERAGE_NOTIONAL",
    max_account_risk_pct: float = 0.02,
    initial_cash: float = 1000.0,
    cost_name: str = "STRESS",
) -> dict[str, Any]:
    """Execute one purely synthetic parametric margin and Mark-liquidation stress scenario.

    Illustrates variation margin, maintenance margin trigger on Mark price, exit fee and funding
    buffers, partial TP1 deleveraging, and stop-gap bankruptcy deficits.
    """
    cost = COST_MODELS_DEC[cost_name]
    fee_bps = float(cost["fee_bps"])
    spread_bps = float(cost["spread_bps"])
    slip_bps = float(cost["slip_bps"])
    adverse_exec_frac = (0.5 * spread_bps + slip_bps) / 10_000.0
    fee_frac = fee_bps / 10_000.0
    clear_frac = clearance_fee_bps / 10_000.0

    margin_budget = 0.95 * initial_cash
    stop_price = entry_price * (1.0 - side * stop_distance_pct)
    eff_entry = float(dec_effective_price(entry_price, side, cost, is_entry=True))

    if sizing_mode == "NAIVE_FULL_LEVERAGE_NOTIONAL":
        # Illustrates why scaling notional to L * margin_budget is unsafe when stop_distance_pct is large
        target_notional = margin_budget * leverage
        qty = math.floor((target_notional / entry_price) / 0.001) * 0.001
    elif sizing_mode == "RISK_BUDGET_CAPPED_ISOLATED":
        # Caps notional so planned stop + 2% gap buffer + roundtrip fees + funding <= max_account_risk_pct * initial_cash
        per_unit_risk_frac = (
            stop_distance_pct
            + 0.02
            + 2.0 * (fee_frac + adverse_exec_frac)
            + (funding_rate_bps / 10_000.0)
            + mmr
            + clear_frac
        )
        risk_budget_usdt = max_account_risk_pct * initial_cash
        max_notional_by_risk = risk_budget_usdt / per_unit_risk_frac
        max_notional_by_margin = margin_budget * leverage / (1.0 + leverage * (mmr + clear_frac + fee_frac))
        target_notional = min(max_notional_by_risk, max_notional_by_margin)
        qty = math.floor((target_notional / entry_price) / 0.001) * 0.001
    else:
        raise ValueError(f"Unknown sizing_mode: {sizing_mode}")

    if qty <= 0 or qty * entry_price < 5.0:
        return {
            "scenario_id": scenario_id,
            "grade": "SYNTHETIC_ONLY_PARAMETRIC_SCENARIO_CONTRACT",
            "sizing_mode": sizing_mode,
            "leverage": leverage,
            "admitted": False,
            "reason": "SIZE_OR_MIN_NOTIONAL_REJECTED",
        }

    initial_notional = qty * entry_price
    if sizing_mode == "RISK_BUDGET_CAPPED_ISOLATED":
        # Allocate isolated margin equal to max(1/L margin, full per-unit risk+MMR+gap buffer) bounded by margin_budget
        initial_margin_posted = min(
            margin_budget,
            max(initial_notional / leverage, initial_notional * per_unit_risk_frac),
        )
    else:
        initial_margin_posted = initial_notional / leverage
    entry_fee_usdt = qty * eff_entry * fee_frac

    # If partial TP1 occurs before the adverse shock, half the inventory closes at +1R
    open_qty = qty
    realized_tp1_pnl_pending = 0.0
    tp1_exit_fee = 0.0
    if partial_tp1_before_shock:
        q1 = math.floor((qty / 2.0) / 0.001) * 0.001
        open_qty = round(qty - q1, 6)
        tp1_raw = entry_price * (1.0 + side * stop_distance_pct)
        tp1_eff = float(dec_effective_price(tp1_raw, side, cost, is_entry=False))
        tp1_exit_fee = q1 * tp1_eff * fee_frac
        realized_tp1_pnl_pending = side * (tp1_eff - eff_entry) * q1

    # Funding settlement debit on remaining open inventory
    funding_debit_usdt = open_qty * entry_price * (funding_rate_bps / 10_000.0)

    # Wallet cash available to support margin before TP1 ACK release
    # Note: pending TP1 ACK receivable is NOT spendable wallet cash until ACK
    wallet_margin_balance = initial_margin_posted - entry_fee_usdt - tp1_exit_fee - funding_debit_usdt

    # Evaluate Mark-triggered liquidation threshold for remaining open_qty
    # Liquidation triggers when: wallet_margin_balance + side * (mark_liq - eff_entry) * open_qty - exit_fee_buffer <= open_qty * mark_liq * (mmr + clear_frac)
    # Solve for the exact adverse Mark price move fraction where Maintenance Margin is breached
    shock_mark_price = entry_price * (1.0 - side * intrabar_adverse_mark_pct)
    open_notional_at_shock = open_qty * shock_mark_price
    exit_fee_buffer_at_shock = open_notional_at_shock * (fee_frac + adverse_exec_frac)
    maintenance_margin_required = open_notional_at_shock * (mmr + clear_frac)
    unrealized_mark_pnl = side * (shock_mark_price - eff_entry) * open_qty
    effective_margin_equity_at_shock = wallet_margin_balance + unrealized_mark_pnl - exit_fee_buffer_at_shock

    mark_liquidated_before_stop = (
        effective_margin_equity_at_shock <= maintenance_margin_required
        and intrabar_adverse_mark_pct <= stop_distance_pct + 1e-9
    )
    mark_liquidated_at_shock = effective_margin_equity_at_shock <= maintenance_margin_required

    # Evaluate bar-open adverse stop-gap shock (e.g., cross-minute gap beyond stop)
    gap_open_price = entry_price * (1.0 - side * open_gap_adverse_pct)
    gap_eff_exit = float(dec_effective_price(gap_open_price, side, cost, is_entry=False))
    gap_exit_fee = open_qty * gap_eff_exit * fee_frac
    gap_realized_loss = side * (gap_eff_exit - eff_entry) * open_qty
    isolated_margin_after_gap = wallet_margin_balance + gap_realized_loss - gap_exit_fee
    margin_deficit_usdt = min(0.0, isolated_margin_after_gap)
    account_equity_after_gap = (
        initial_cash
        - entry_fee_usdt
        - tp1_exit_fee
        - funding_debit_usdt
        + realized_tp1_pnl_pending
        + gap_realized_loss
        - gap_exit_fee
    )

    return {
        "scenario_id": scenario_id,
        "grade": "SYNTHETIC_ONLY_PARAMETRIC_SCENARIO_CONTRACT__NOT_HISTORICAL_BINANCE_TIER_OR_EMPIRICAL_RETURN",
        "sizing_mode": sizing_mode,
        "side": side,
        "leverage": leverage,
        "hypothetical_mmr": mmr,
        "hypothetical_clearance_fee_bps": clearance_fee_bps,
        "admitted": True,
        "initial_qty_btc": round(qty, 6),
        "open_qty_at_shock_btc": round(open_qty, 6),
        "initial_notional_usdt": round(initial_notional, 4),
        "effective_account_leverage_ratio": round(initial_notional / initial_cash, 4),
        "initial_margin_posted_usdt": round(initial_margin_posted, 4),
        "stop_price": round(stop_price, 2),
        "stop_distance_pct": stop_distance_pct,
        "intrabar_adverse_mark_pct": intrabar_adverse_mark_pct,
        "open_gap_adverse_pct": open_gap_adverse_pct,
        "partial_tp1_before_shock": partial_tp1_before_shock,
        "maintenance_margin_required_usdt": round(maintenance_margin_required, 4),
        "effective_margin_equity_at_shock_usdt": round(effective_margin_equity_at_shock, 4),
        "mark_liquidated_at_shock": bool(mark_liquidated_at_shock),
        "mark_liquidated_before_strategy_stop": bool(mark_liquidated_before_stop),
        "isolated_margin_after_gap_usdt": round(isolated_margin_after_gap, 4),
        "isolated_margin_bankruptcy_deficit_usdt": round(margin_deficit_usdt, 4),
        "total_account_equity_after_gap_usdt": round(account_equity_after_gap, 4),
        "account_insolvent_after_gap": bool(account_equity_after_gap <= 0.0),
    }


def build_synthetic_leverage_stress_matrix() -> dict[str, Any]:
    """Generate the frozen synthetic-only 1x / 5x / 10x / 15x stress envelope matrix."""
    scenarios: list[dict[str, Any]] = []
    # 1. Compare 1x, 5x, 10x, 15x under a realistic 2*ATR stop distance (7.5%) and -6.5% intrabar Mark move + -9% stop gap
    for lev in (1.0, 5.0, 10.0, 15.0):
        for mmr in (0.004, 0.005, 0.010):
            for mode in ("NAIVE_FULL_LEVERAGE_NOTIONAL", "RISK_BUDGET_CAPPED_ISOLATED"):
                scen_id = f"SYN_LEV_{int(lev)}X_MMR_{int(mmr*10000)}BP_{mode[:5]}"
                scenarios.append(
                    run_synthetic_leverage_scenario(
                        scenario_id=scen_id,
                        side=1,
                        leverage=lev,
                        mmr=mmr,
                        clearance_fee_bps=75.0,
                        entry_price=30_000.0,
                        stop_distance_pct=0.075,
                        intrabar_adverse_mark_pct=0.068,
                        open_gap_adverse_pct=0.095,
                        partial_tp1_before_shock=False,
                        sizing_mode=mode,
                    )
                )

    # 2. Partial TP1 deleveraging comparison at 10x and 15x (pre-TP1 vs post-TP1 shock)
    for lev in (10.0, 15.0):
        for partial_done in (False, True):
            for side in (1, -1):
                scen_id = f"SYN_PARTIAL_TP1_{int(lev)}X_SIDE_{side}_TP1_{int(partial_done)}"
                scenarios.append(
                    run_synthetic_leverage_scenario(
                        scenario_id=scen_id,
                        side=side,
                        leverage=lev,
                        mmr=0.005,
                        clearance_fee_bps=75.0,
                        entry_price=30_000.0,
                        stop_distance_pct=0.08,
                        intrabar_adverse_mark_pct=0.072,
                        open_gap_adverse_pct=0.10,
                        partial_tp1_before_shock=partial_done,
                        sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
                    )
                )

    naive_10x_15x = [
        s
        for s in scenarios
        if s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL" and s["leverage"] in (10.0, 15.0) and not s["partial_tp1_before_shock"]
    ]
    risk_capped_10x_15x = [
        s
        for s in scenarios
        if s["sizing_mode"] == "RISK_BUDGET_CAPPED_ISOLATED" and s["leverage"] in (10.0, 15.0)
    ]

    return {
        "grade": "SYNTHETIC_ONLY_PARAMETRIC_SCENARIO_CONTRACT__NO_EMPIRICAL_LEVERAGED_PNL",
        "historical_exchange_maintenance_tiers": "UNKNOWN",
        "historical_liquidation_engine_mark_parameters": "UNKNOWN",
        "naive_1x_pnl_multiplication_prohibited": True,
        "scenario_count": len(scenarios),
        "summary_findings": {
            "naive_10x_15x_liquidated_before_strategy_stop_count": sum(
                1 for s in naive_10x_15x if s["mark_liquidated_before_strategy_stop"]
            ),
            "naive_10x_15x_gap_bankruptcy_deficit_count": sum(
                1 for s in naive_10x_15x if s["isolated_margin_bankruptcy_deficit_usdt"] < 0
            ),
            "risk_capped_10x_15x_liquidated_count": sum(
                1 for s in risk_capped_10x_15x if s["mark_liquidated_at_shock"]
            ),
            "risk_capped_10x_15x_account_insolvent_count": sum(
                1 for s in risk_capped_10x_15x if s["account_insolvent_after_gap"]
            ),
        },
        "scenarios": scenarios,
        "minimal_input_contract_for_future_leverage_research_or_testnet": {
            "authorization_status": "NOT_AUTHORIZED_BY_THIS_AUDIT",
            "required_exchange_asof_specifications": [
                {
                    "id": "REQ_01_MAINTENANCE_MARGIN_BRACKETS",
                    "description": "Official historical as-of dated Binance USD-M BTCUSDT notional bracket schedule (notional floor/cap, MMR, maintenance amount, max leverage per bracket, effective timestamps).",
                    "current_status": "UNKNOWN",
                },
                {
                    "id": "REQ_02_EXCHANGE_LIQUIDATION_AND_MARK_FORMULA",
                    "description": "Exact sub-minute Mark price composition (spot index basket, funding basis moving average, price clamp bounds), bankruptcy price formula, insurance fund liquidation clearance fee rate, and ADL queue rules.",
                    "current_status": "UNKNOWN",
                },
                {
                    "id": "REQ_03_FEE_AND_FUNDING_SETTLEMENT_AUTHORITY",
                    "description": "As-of dated maker/taker fee schedule, exact exchange settlement Mark price at 00:00/08:00/16:00 UTC (currently approximated by latest completed 1m Mark close), and funding credit/debit wallet posting latency.",
                    "current_status": "UNKNOWN",
                },
                {
                    "id": "REQ_04_L2_QUEUE_AND_SUBMINUTE_ORDER_BOOK",
                    "description": "L2 order-book depth or tick-by-tick trade stream to resolve intra-minute STOP vs TP1/TP2 ordering and limit queue fill probability on touch vs trade-through.",
                    "current_status": "UNKNOWN",
                },
                {
                    "id": "REQ_05_EXECUTOR_STATE_MACHINE_AND_TESTNET_BOUNDARY_HARNESS",
                    "description": "Idempotent clientOrderId state machine, partial-fill stop quantity amendment / cancel-replace race-condition tests, WebSocket user-stream vs REST reconciliation, and hard margin-utilization kill-switch before any separate TESTNET gate.",
                    "current_status": "NOT_AUTHORIZED_IN_G2",
                },
            ],
        },
    }


def audit_real_r1_capital_and_exposure(
    r1_evidence_dir: Path,
    r31_cache_dir: Path,
    r1_cache_dir: Path,
) -> dict[str, Any]:
    """Validate 1x cash cap, 5% reserve, Mark notional/equity ratio, and adverse tails on committed R1 data."""
    r1_results = json.loads((r1_evidence_dir / "EXIT_R1_RESULTS.json").read_text())
    ledger_manifest = json.loads((r1_evidence_dir / "COMMITTED_LEDGER_MANIFEST.json").read_text())

    admission_checks = 0
    admission_breaches: list[dict[str, Any]] = []
    stop_gap_events: list[dict[str, Any]] = []
    worst_single_trade_loss_bps = 0.0
    worst_single_trade_loss_event: dict[str, Any] | None = None

    for item in ledger_manifest:
        cpath = Path(item["committed_path"])
        if not cpath.name.endswith("_orders.jsonl"):
            continue
        parts = cpath.stem.split("_")
        scheme = parts[-2]
        cost_name = parts[-3]
        cand_id = "_".join(parts[:-3])
        full_path = r1_evidence_dir.parents[3] / cpath
        for line in full_path.read_text(encoding="utf-8").splitlines():
            t = json.loads(line)
            admission_checks += 1
            cash_before = D(t["cash_before_entry"])
            budget = Decimal("0.95") * min(cash_before, Decimal(1000))
            q = D(t["quantity"])
            eff_entry = D(t["effective_entry"])
            fee_entry = D(t["fee_entry"])
            outlay = q * eff_entry + fee_entry
            if outlay > budget + Decimal("1e-7"):
                admission_breaches.append({
                    "candidate": cand_id,
                    "cost": cost_name,
                    "scheme": scheme,
                    "event_id": t["event_id"],
                    "outlay": str(outlay),
                    "budget": str(budget),
                })
            # Check reserve dictionary if present (H1, H2, E1, E2)
            if "reserve" in t:
                res = t["reserve"]
                if abs(D(res["budget"]) - budget) > Decimal("1e-7"):
                    admission_breaches.append({
                        "candidate": cand_id,
                        "cost": cost_name,
                        "scheme": scheme,
                        "event_id": t["event_id"],
                        "reason": "Reserve budget mismatch",
                    })

            net_bps = float(t["net_after_funding_bps"])
            if net_bps < worst_single_trade_loss_bps:
                worst_single_trade_loss_bps = net_bps
                worst_single_trade_loss_event = {
                    "candidate": cand_id,
                    "cost": cost_name,
                    "scheme": scheme,
                    "event_id": t["event_id"],
                    "net_after_funding_bps": net_bps,
                    "exit_reason": t["exit_reason"],
                }

            for tier in t.get("tiers", []):
                if tier["reason"] == "STOP_GAP":
                    side = int(t["side"])
                    stop_p = float(t["stop"])
                    raw_exit_p = float(tier["raw_exit"])
                    gap_beyond_stop_bps = 10_000.0 * abs(raw_exit_p - stop_p) / float(t["raw_entry"])
                    stop_gap_events.append({
                        "candidate": cand_id,
                        "cost": cost_name,
                        "scheme": scheme,
                        "event_id": t["event_id"],
                        "side": side,
                        "stop_price": stop_p,
                        "gap_open_exit_price": raw_exit_p,
                        "adverse_gap_beyond_stop_bps": round(gap_beyond_stop_bps, 4),
                    })

    # Inspect exposure ratios and Mark drawdowns across all 20 cells
    cell_exposure_summaries: list[dict[str, Any]] = []
    for cid, c_dict in r1_results["candidates"].items():
        for cost_name, cost_dict in c_dict.items():
            for scheme, acc in cost_dict["account"].items():
                monthly = acc["monthly"]
                max_exp = max(
                    float(m.get("peak_exposure_ratio", m.get("max_position_notional_to_marked_equity", 0.0)))
                    for m in monthly
                )
                breach_mins = sum(
                    int(m.get("exposure_above_1x_minutes", m.get("marked_exposure_breach_minutes", 0)))
                    for m in monthly
                )
                min_eq = min(
                    float(m.get("Mark_min_equity", m.get("ending_equity", 1000.0)))
                    for m in monthly
                )
                max_dd = float(acc["metrics"]["max_mtm_drawdown_pct"])
                cell_exposure_summaries.append({
                    "candidate": cid,
                    "cost": cost_name,
                    "scheme": scheme,
                    "peak_mark_notional_to_equity_ratio": round(max_exp, 6),
                    "exposure_above_1x_minutes": breach_mins,
                    "max_mtm_drawdown_pct": round(max_dd, 4),
                    "min_monthly_mark_equity_usdt": round(min_eq, 4),
                })

    # Inspect realized adverse excursion (MAE) tails from paired ledgers
    mae_tails: dict[str, Any] = {}
    for cid in (
        "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
    ):
        p_path = r1_evidence_dir / f"{cid}_STRESS_paired.jsonl"
        rows = [json.loads(line) for line in p_path.read_text(encoding="utf-8").splitlines()]
        last_mae_24h = [
            min(
                float(r["path24h"]["before12h"]["Last_MAE_R"]),
                float(r["path24h"]["12to18h"]["Last_MAE_R"]),
                float(r["path24h"]["18to24h"]["Last_MAE_R"]),
            )
            for r in rows
        ]
        mark_mae_24h = [
            min(
                float(r["path24h"]["before12h"]["Mark_MAE_R"]),
                float(r["path24h"]["12to18h"]["Mark_MAE_R"]),
                float(r["path24h"]["18to24h"]["Mark_MAE_R"]),
            )
            for r in rows
        ]
        stop_dist_pcts = [
            100.0 * float(r["cells"]["E0"]["initial_risk"]) / float(r["cells"]["E0"]["raw_entry"])
            for r in rows
        ]
        mae_tails[cid] = {
            "events_n": len(rows),
            "worst_24h_last_mae_R": round(min(last_mae_24h), 4),
            "worst_24h_mark_mae_R": round(min(mark_mae_24h), 4),
            "max_initial_stop_distance_pct_of_entry": round(max(stop_dist_pcts), 4),
            "median_initial_stop_distance_pct_of_entry": round(float(np.median(stop_dist_pcts)), 4),
            "why_1x_solvency_does_not_imply_10x_15x": (
                f"Max planned 1R stop distance is {max(stop_dist_pcts):.2f}% of BTC entry price; "
                "at 15x gross leverage (6.67% initial margin), a single 1R stop move exceeds initial margin "
                "minus maintenance margin and triggers forced Mark liquidation before the strategy stop."
            ),
        }

    return {
        "status": "PASS" if not admission_breaches else "DEFECT_FOUND",
        "admission_trades_verified_n": admission_checks,
        "admission_1x_reserve_breaches_n": len(admission_breaches),
        "admission_breaches": admission_breaches,
        "total_exposure_above_1x_minutes_across_all_20_cells": sum(
            c["exposure_above_1x_minutes"] for c in cell_exposure_summaries
        ),
        "max_exposure_ratio_across_all_20_cells": max(
            c["peak_mark_notional_to_equity_ratio"] for c in cell_exposure_summaries
        ),
        "cell_exposure_summaries": cell_exposure_summaries,
        "realized_stop_gap_events_n": len(stop_gap_events),
        "realized_stop_gap_events": stop_gap_events,
        "worst_single_trade_loss": worst_single_trade_loss_event,
        "adverse_mae_and_stop_distance_tails": mae_tails,
        "synthetic_leverage_stress_envelope": build_synthetic_leverage_stress_matrix(),
    }
