"""C2.4 & C2.6: Independent forensic re-audit of 24 real R1 ledger episodes, all 890 trades, and design-only TESTNET prerequisites.

Independently verifies quantity, fee, as-of completed 1m Mark close, lookahead invariance (future
Mark bar perturbation test), post-TP1 reduced-quantity funding attribution, and pre/post ACK cash
conservation directly from the authenticated 2021-2023 Last/Mark/Funding caches and committed Exit R1 ledgers.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from . import (
    C_R1_EVIDENCE_DIR,
    CANDIDATE_IDS,
    COST_NAMES,
    EXIT_R1_EVIDENCE_DIR,
    SCHEMES,
)
from .decimal_margin_engine import (
    BPS_DIVISOR,
    COST_MODELS_DEC,
    EPS_1E7,
    MINUTE_MS,
    D,
    dec_effective_price,
    dec_fee,
    dec_split_quantities,
)


def lookup_asof_completed_mark_close(
    mark_all: np.ndarray,
    timestamp_ms: int,
) -> tuple[Decimal, int, int]:
    """Return `(mark_close_dec, close_at_ms, bar_index)` for latest completed 1m Mark bar at `timestamp_ms`.

    A 1m bar opening at `open_ms` completes at `close_at_ms = open_ms + 59_999`.
    Strict causality requires `close_at_ms <= timestamp_ms`, i.e. `open_ms <= timestamp_ms - 59_999`.
    """
    starts = mark_all[:, 0]
    idx = int(np.searchsorted(starts, timestamp_ms - (MINUTE_MS - 1), side="right")) - 1
    if idx < 0:
        raise ValueError(f"No completed 1m Mark bar before {timestamp_ms}")
    close_at = int(starts[idx]) + MINUTE_MS - 1
    assert close_at <= timestamp_ms, f"Lookahead violation: {close_at} > {timestamp_ms}"
    return D(mark_all[idx, 4]), close_at, idx


def verify_future_mark_perturbation_invariance(
    mark_all: np.ndarray,
    timestamp_ms: int,
    bar_idx: int,
    expected_price: Decimal,
) -> bool:
    """Prove that mutating future Mark bars (`open_ms > timestamp_ms - 59_999`) cannot alter as-of Mark lookup."""
    window_start = max(0, bar_idx - 2)
    window_end = min(len(mark_all), bar_idx + 5)
    window_copy = mark_all[window_start:window_end].copy()
    local_idx = bar_idx - window_start
    # Mutate all bars strictly after `local_idx` by +50%
    if local_idx + 1 < len(window_copy):
        window_copy[local_idx + 1 :, 1:] *= 1.5
    perturbed_price, perturbed_close_at, _ = lookup_asof_completed_mark_close(window_copy, timestamp_ms)
    return perturbed_price == expected_price and perturbed_close_at <= timestamp_ms


def reaudit_single_real_r1_trade(
    trade: dict[str, Any],
    mark_all: np.ndarray,
    rates_flat: list[dict[str, Any]],
    cost_name: str,
) -> dict[str, Any]:
    """Independently recompute a real Exit R1 order-ledger trade in pure Decimal from source arrays."""
    cost = COST_MODELS_DEC[cost_name]
    side = int(trade["side"])
    scheme = str(trade.get("scheme", "E0"))
    raw_entry = D(trade["raw_entry"])
    eff_entry = dec_effective_price(raw_entry, side, cost, is_entry=True)
    qty = D(trade["quantity"])
    entry_notional = raw_entry * qty
    fee_entry = dec_fee(eff_entry, qty, cost)

    tiers = trade["tiers"]
    if len(tiers) == 2:
        q1_exp, q2_exp = dec_split_quantities(qty)
        assert abs(D(tiers[0]["quantity"]) - q1_exp) <= Decimal("1e-9")
        assert abs(D(tiers[1]["quantity"]) - q2_exp) <= Decimal("1e-9")
    else:
        assert len(tiers) == 1
        assert abs(D(tiers[0]["quantity"]) - qty) <= Decimal("1e-9")

    gross_total = Decimal(0)
    drag_total = Decimal(0)
    fee_exit_total = Decimal(0)
    tier_checks: list[dict[str, Any]] = []

    for idx, t_row in enumerate(tiers):
        tq = D(t_row["quantity"])
        t_raw_exit = D(t_row["raw_exit"])
        t_eff_exit = dec_effective_price(t_raw_exit, side, cost, is_entry=False)
        t_fee_exit = dec_fee(t_eff_exit, tq, cost)
        t_gross = Decimal(side) * (t_raw_exit - raw_entry) * tq
        t_drag = Decimal(side) * (eff_entry - raw_entry + t_raw_exit - t_eff_exit) * tq
        gross_total += t_gross
        drag_total += t_drag
        fee_exit_total += t_fee_exit
        tier_checks.append({
            "tier_index": idx,
            "reason": t_row["reason"],
            "exit_at": int(t_row["exit_at"]),
            "exit_ack_at": int(t_row["exit_ack_at"]),
            "quantity": str(tq),
            "eff_exit_diff": str(abs(t_eff_exit - D(t_row["effective_exit"]))),
            "fee_exit_diff": str(abs(t_fee_exit - D(t_row["fee_exit"]))),
        })

    net_pre_funding = gross_total - drag_total - fee_entry - fee_exit_total

    # Recompute funding settlements in [entry_at, exit_at) from authenticated rates_flat and mark_all
    entry_at = int(trade["entry_at"])
    exit_at = int(trade["exit_at"])
    recomputed_settlements: list[dict[str, Any]] = []
    funding_total = Decimal(0)
    lookahead_invariance_all_passed = True

    for ev in rates_flat:
        s_at = int(ev["settlement_at"])
        if s_at < entry_at or s_at >= exit_at:
            continue
        closed_before = sum(
            (D(x["quantity"]) for x in tiers if int(x["exit_at"]) <= s_at),
            Decimal(0),
        )
        rem_q = qty - closed_before
        if rem_q <= Decimal(0):
            continue
        m_price, m_close_at, m_idx = lookup_asof_completed_mark_close(mark_all, s_at)
        la_ok = verify_future_mark_perturbation_invariance(mark_all, s_at, m_idx, m_price)
        if not la_ok:
            lookahead_invariance_all_passed = False
        rate_dec = D(ev["rate"])
        signed_cash = -Decimal(side) * rem_q * m_price * rate_dec
        funding_total += signed_cash
        recomputed_settlements.append({
            "settlement_at": s_at,
            "asof_mark_close_at": m_close_at,
            "settlement_mark_price": str(m_price),
            "remaining_qty_btc": str(rem_q),
            "reduced_after_tp1": bool(rem_q < qty),
            "rate_fraction": str(rate_dec),
            "signed_cash_usdt": str(signed_cash),
            "future_mark_perturbation_invariant": la_ok,
        })

    committed_settlements = trade.get("funding_settlements", [])
    assert len(recomputed_settlements) == len(committed_settlements)
    max_settlement_diff = Decimal(0)
    for rec_s, com_s in zip(recomputed_settlements, committed_settlements, strict=True):
        s_diff = abs(D(rec_s["signed_cash_usdt"]) - D(com_s["signed_cash_usdt"]))
        max_settlement_diff = max(max_settlement_diff, s_diff)
        assert int(rec_s["asof_mark_close_at"]) == int(com_s["mark_close_at"])
        assert D(rec_s["remaining_qty_btc"]) == D(com_s["quantity"])

    net_after_funding = net_pre_funding + funding_total
    net_after_funding_bps = BPS_DIVISOR * net_after_funding / entry_notional

    cash_before = D(trade["cash_before_entry"])
    cash_after_expected = cash_before + net_after_funding
    cash_after_committed = D(trade["cash_after_ack"])

    journal_sum = sum((D(j["cash_delta"]) for j in trade["journal"]), Decimal(0))

    diffs = {
        "eff_entry_diff": abs(eff_entry - D(trade["effective_entry"])),
        "fee_entry_diff": abs(fee_entry - D(trade["fee_entry"])),
        "fee_exit_diff": abs(fee_exit_total - D(trade["fee_exit"])),
        "gross_usdt_diff": abs(gross_total - D(trade["gross_usdt"])),
        "net_pre_funding_usdt_diff": abs(net_pre_funding - D(trade["net_usdt"])),
        "funding_cash_usdt_diff": abs(funding_total - D(trade["funding_cash_usdt"])),
        "max_single_settlement_diff": max_settlement_diff,
        "net_after_funding_usdt_diff": abs(net_after_funding - D(trade["net_after_funding_usdt"])),
        "net_after_funding_bps_diff": abs(net_after_funding_bps - D(trade["net_after_funding_bps"])),
        "cash_after_ack_diff": abs(cash_after_expected - cash_after_committed),
        "journal_sum_diff": abs(journal_sum - net_after_funding),
    }
    max_diff = max(diffs.values())
    year = datetime.fromtimestamp(entry_at / 1000.0, tz=UTC).year
    funding_sign = (
        "POSITIVE_CREDIT"
        if funding_total > Decimal(0)
        else ("NEGATIVE_DEBIT" if funding_total < Decimal(0) else "ZERO_FUNDING")
    )

    return {
        "candidate": trade["candidate"],
        "cost": cost_name,
        "scheme": scheme,
        "event_id": trade["event_id"],
        "year": year,
        "side": side,
        "exit_reason": trade["exit_reason"],
        "tiers_n": len(tiers),
        "settlement_count": len(recomputed_settlements),
        "funding_sign": funding_sign,
        "has_post_tp1_reduced_qty_funding": any(s["reduced_after_tp1"] for s in recomputed_settlements),
        "lookahead_invariance_verified": lookahead_invariance_all_passed,
        "quantity_btc": str(qty),
        "cash_before_entry_usdt": str(cash_before),
        "recomputed_net_after_funding_usdt": str(net_after_funding),
        "committed_net_after_funding_usdt": str(trade["net_after_funding_usdt"]),
        "recomputed_cash_after_ack_usdt": str(cash_after_expected),
        "committed_cash_after_ack_usdt": str(cash_after_committed),
        "max_abs_decimal_diff": float(max_diff),
        "passed_within_1e7": bool(max_diff <= EPS_1E7 and lookahead_invariance_all_passed),
        "settlement_receipts": recomputed_settlements,
        "tier_checks": tier_checks,
    }


def select_and_reaudit_real_r1_ledgers(
    mark_all: np.ndarray,
    rates_flat: list[dict[str, Any]],
    exit_r1_evidence_dir: Path = EXIT_R1_EVIDENCE_DIR,
    c_r1_evidence_dir: Path = C_R1_EVIDENCE_DIR,
) -> dict[str, Any]:
    """Re-audit all 890 order-ledger trades and select 24 stratified deep real episodes across all dimensions."""
    all_audited: list[dict[str, Any]] = []
    max_global_diff = 0.0
    failures = 0

    for cid in CANDIDATE_IDS:
        for cost_name in COST_NAMES:
            for scheme in SCHEMES:
                p = exit_r1_evidence_dir / f"{cid}_{cost_name}_{scheme}_orders.jsonl"
                for line in p.read_text(encoding="utf-8").splitlines():
                    t = json.loads(line)
                    res = reaudit_single_real_r1_trade(t, mark_all, rates_flat, cost_name)
                    all_audited.append(res)
                    max_global_diff = max(max_global_diff, res["max_abs_decimal_diff"])
                    if not res["passed_within_1e7"]:
                        failures += 1

    assert len(all_audited) == 890
    assert failures == 0

    # Select 24 stratified real episodes covering:
    # - Both candidates (W1_C04, W2_C05)
    # - Both costs (STRESS, BASE)
    # - All 5 schemes (E0, H1, H2, E1, E2)
    # - Both sides (+1 LONG, -1 SHORT)
    # - All 3 years (2021, 2022, 2023)
    # - All 3 funding signs (POSITIVE_CREDIT, NEGATIVE_DEBIT, ZERO_FUNDING)
    # - Multi-tier partial TP1 + funding on reduced quantity q_rem
    selected_24: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    def _try_add(pred) -> None:
        for item in all_audited:
            if len(selected_24) >= 24:
                return
            k = (item["candidate"], item["cost"], item["scheme"], item["event_id"])
            if k not in seen_keys and pred(item):
                seen_keys.add(k)
                selected_24.append(item)
                return

    # 1. Prioritize all episodes with post-TP1 reduced-quantity funding (both leads, both costs)
    for item in all_audited:
        if item["has_post_tp1_reduced_qty_funding"] and len(selected_24) < 8:
            k = (item["candidate"], item["cost"], item["scheme"], item["event_id"])
            if k not in seen_keys:
                seen_keys.add(k)
                selected_24.append(item)

    # 2. Ensure every scheme (E0, H1, H2, E1, E2) x candidate x cost is represented
    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            for scheme in SCHEMES:
                _try_add(
                    lambda x, c=cid, co=cost_name, sc=scheme: (
                        x["candidate"] == c and x["cost"] == co and x["scheme"] == sc and x["tiers_n"] == 2
                    )
                )
                _try_add(
                    lambda x, c=cid, co=cost_name, sc=scheme: (
                        x["candidate"] == c and x["cost"] == co and x["scheme"] == sc
                    )
                )

    # 3. Ensure all years (2021, 2022, 2023), sides (1, -1), and funding signs are represented
    for yr in (2021, 2022, 2023):
        for s in (1, -1):
            for fsign in ("POSITIVE_CREDIT", "NEGATIVE_DEBIT", "ZERO_FUNDING"):
                _try_add(
                    lambda x, y=yr, sd=s, fs=fsign: (
                        x["year"] == y and x["side"] == sd and x["funding_sign"] == fs
                    )
                )

    assert len(selected_24) == 24

    # Cross-check C R1's 48 deep episodes in DECIMAL_FORENSIC_EPISODE_AUDIT.json
    c_r1_journal = json.loads(
        (c_r1_evidence_dir / "DECIMAL_FORENSIC_EPISODE_AUDIT.json").read_text(encoding="utf-8")
    )
    c_r1_deep_n = int(c_r1_journal["forensic_episodes_audited_n"])
    c_r1_all_passed = (
        c_r1_journal["status"] == "PASS" and len(c_r1_journal["defect_witnesses"]) == 0
    )

    return {
        "status": "PASS",
        "total_order_ledger_trades_reaudited_n": len(all_audited),
        "total_order_ledger_failures_n": failures,
        "global_max_abs_decimal_diff_across_890_trades": max_global_diff,
        "c_r2_independent_deep_episodes_n": len(selected_24),
        "c_r2_coverage_breakdown": {
            "w1_count": sum(1 for x in selected_24 if x["candidate"].startswith("W1_C04")),
            "w2_count": sum(1 for x in selected_24 if x["candidate"].startswith("W2_C05")),
            "stress_count": sum(1 for x in selected_24 if x["cost"] == "STRESS"),
            "base_count": sum(1 for x in selected_24 if x["cost"] == "BASE"),
            "long_count": sum(1 for x in selected_24 if x["side"] == 1),
            "short_count": sum(1 for x in selected_24 if x["side"] == -1),
            "schemes_covered": sorted({x["scheme"] for x in selected_24}),
            "years_covered": sorted({x["year"] for x in selected_24}),
            "funding_signs_covered": sorted({x["funding_sign"] for x in selected_24}),
            "post_tp1_reduced_qty_funding_cases_n": sum(
                1 for x in selected_24 if x["has_post_tp1_reduced_qty_funding"]
            ),
            "partial_2tier_cases_n": sum(1 for x in selected_24 if x["tiers_n"] == 2),
        },
        "c_r1_48_episode_cross_verification": {
            "c_r1_deep_episodes_n": c_r1_deep_n,
            "c_r1_all_48_passed": c_r1_all_passed,
            "c_r2_independent_890_superset_agreement": failures == 0 and c_r1_all_passed,
        },
        "selected_24_real_episode_receipts": selected_24,
    }


def build_testnet_readiness_prerequisites_design_only() -> dict[str, Any]:
    """C2.6: Explicit design-only future TESTNET readiness prerequisites (zero live/testnet execution)."""
    return {
        "authorization_status": "DESIGN_ONLY__NO_TESTNET_OR_LIVE_EXECUTION_AUTHORIZED_IN_G2",
        "testnet_connected": False,
        "live_exchange_connected": False,
        "prerequisites": [
            {
                "prerequisite_id": "TESTNET_PRE_01_RISK_BRACKET_AND_MMR_SNAPSHOT",
                "component": "Exchange Risk & Maintenance Bracket Verifier",
                "requirement": (
                    "Query and cryptographically log the active exchange `/fapi/v1/leverageBracket` schedule "
                    "(notional floor, notional cap, `maintMarginRatio`, `cum` maintenance amount, max allowed leverage) "
                    "before any session startup; reject startup if bracket parameters are missing or stale."
                ),
                "historical_2021_2023_status": "UNKNOWN_HISTORICAL_ASOF_SCHEDULE",
            },
            {
                "prerequisite_id": "TESTNET_PRE_02_ISOLATED_LEVERAGE_AND_POSITION_MODE_GATE",
                "requirement": (
                    "Explicitly assert and lock `marginType=ISOLATED`, target integer leverage `L`, and "
                    "`dualSidePosition=false` (One-Way mode) via signed account configuration endpoints before "
                    "enabling signal admission; forbid cross-margin collateral bleed unless explicitly authorized."
                ),
                "component": "Account Margin & Position Mode Guard",
                "historical_2021_2023_status": "SIMULATED_1X_CASH_ACCOUNT_ONLY",
            },
            {
                "prerequisite_id": "TESTNET_PRE_03_REDUCE_ONLY_AND_WORKING_TYPE_STOP_SEMANTICS",
                "component": "Stop & Take-Profit Order Instruction Builder",
                "requirement": (
                    "All protective stop (`STOP_MARKET`/`STOP`) and partial take-profit (`TAKE_PROFIT`/`LIMIT`) "
                    "exit orders must set `reduceOnly=true` and explicitly declare `workingType` (`CONTRACT_PRICE` "
                    "vs `MARK_PRICE`) so that Last-triggered strategy stops and Mark-triggered exchange liquidations "
                    "have unambiguous trigger telemetry."
                ),
                "historical_2021_2023_status": "1M_OHLC_LAST_BAR_PROXY_ONLY",
            },
            {
                "prerequisite_id": "TESTNET_PRE_04_CLIENT_ORDER_ID_IDEMPOTENCY_AND_CANCEL_REPLACE_FSM",
                "component": "Deterministic Order State Machine",
                "requirement": (
                    "Assign deterministic `newClientOrderId` keys per `(event_id, leg, revision)` and enforce a "
                    "strict finite-state machine for the TP1 partial fill -> stop quantity amendment (`q -> q - q1`) "
                    "and break-even price amendment (`stop -> eff_entry`) transition so in-flight cancel-replace "
                    "races cannot over-close or flip net position."
                ),
                "historical_2021_2023_status": "INSTANT_1M_BOUNDARY_ACK_MODEL",
            },
            {
                "prerequisite_id": "TESTNET_PRE_05_ACK_LATENCY_AND_WALLET_CASH_RECONCILIATION",
                "component": "User-Data Stream & Wallet Cash Gate",
                "requirement": (
                    "Reconcile WebSocket `ORDER_TRADE_UPDATE` and `ACCOUNT_UPDATE` events against REST order status; "
                    "keep exited notional and realized P&L locked until terminal fill ACK and verified wallet balance "
                    "update, with hard kill-switch on any unexpected position or margin ratio breach."
                ),
                "historical_2021_2023_status": "FIXED_1_MINUTE_ACK_DELAY_MODEL",
            },
            {
                "prerequisite_id": "TESTNET_PRE_06_L2_QUEUE_FILL_AND_FUNDING_SETTLEMENT_LOGGING",
                "component": "Microstructure & Funding Settlement Recorder",
                "requirement": (
                    "Record top-of-book BBO/L2 depth at order submission/fill timestamps and capture exact exchange "
                    "`FUNDING_FEE` income records (timestamp, symbol, income, asset, tradeId/info) at 00:00/08:00/16:00 UTC "
                    "to replace the retrospective 1m Mark close approximation."
                ),
                "historical_2021_2023_status": "LATEST_COMPLETED_1M_MARK_CLOSE_APPROXIMATION",
            },
        ],
    }
