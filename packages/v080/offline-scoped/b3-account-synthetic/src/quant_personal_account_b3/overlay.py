"""Account-aware overlay, protection assessment, position relation, and human actionability."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .accounting import AccountingReport, compute_accounting_report
from .b2_reader import B2CardRecord
from .client import (
    ROUTE_ACCOUNT,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
    ROUTE_POSITION_RISK,
)
from .matching import EpisodeMatchResult, match_episode_to_account
from .models import (
    DECIMAL_CONTEXT,
    SCHEMA_OVERLAY,
    ZERO,
    D,
    decimal_str,
    digest,
    synthetic_provenance_block,
)
from .normalize import (
    NormalizedAlgoOrder,
    NormalizedOrder,
    NormalizedPosition,
    PrivateAccountSnapshot,
)
from .storage import ManualAssociation

ACTIVE_ORDINARY_STATUSES = frozenset({"NEW", "PARTIALLY_FILLED"})
ACTIVE_ALGO_STATUSES = frozenset({"NEW", "WORKING", "PENDING"})

SL_ORDER_TYPES = frozenset({"STOP_MARKET", "STOP"})
TP_ORDER_TYPES = frozenset({"TAKE_PROFIT_MARKET", "TAKE_PROFIT"})
TRAILING_ORDER_TYPES = frozenset({"TRAILING_STOP_MARKET"})

OWNER_HISTORICAL_CONTEXT_NOT_POLICY = {
    "stated_per_trade_loss_preference": "2.5% (OWNER_STATED historical context only; NOT approved executable B3 policy)",
    "stated_usual_leverage": "10-15x isolated (OWNER_STATED historical context only; NOT approved executable B3 policy)",
    "approved_numerical_account_policy": False,
}


@dataclass(frozen=True)
class ProtectiveOrderView:
    source: str  # ORDINARY_OPEN_ORDERS | ALGO_OPEN_ORDERS
    order_id: int
    client_id: str
    role: str  # STOP_LOSS | TAKE_PROFIT | TRAILING_STOP
    order_type: str
    side: str
    position_side: str
    status: str
    trigger_price: Decimal | None
    price: Decimal | None
    working_type: str | None
    close_position: bool
    reduce_only: bool
    covered_qty: Decimal
    raw_qty: Decimal
    valid_direction_and_trigger: bool
    conflict_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "order_id": self.order_id,
            "client_id": self.client_id,
            "role": self.role,
            "order_type": self.order_type,
            "side": self.side,
            "position_side": self.position_side,
            "status": self.status,
            "trigger_price": decimal_str(self.trigger_price),
            "price": decimal_str(self.price),
            "working_type": self.working_type,
            "close_position": self.close_position,
            "reduce_only": self.reduce_only,
            "covered_qty": decimal_str(self.covered_qty),
            "raw_qty": decimal_str(self.raw_qty),
            "valid_direction_and_trigger": self.valid_direction_and_trigger,
            "conflict_reason": self.conflict_reason,
        }


def _classify_order_role(order_type: str) -> str | None:
    if order_type in SL_ORDER_TYPES:
        return "STOP_LOSS"
    if order_type in TP_ORDER_TYPES:
        return "TAKE_PROFIT"
    if order_type in TRAILING_ORDER_TYPES:
        return "TRAILING_STOP"
    return None


def _closing_side(direction: str) -> str:
    return "SELL" if direction == "LONG" else "BUY"


def _evaluate_position_relation(
    card: B2CardRecord,
    snapshot: PrivateAccountSnapshot | None,
) -> tuple[str, list[NormalizedPosition], list[str]]:
    """Determine position_relation without ever fabricating a zero position for omitted rows."""
    if snapshot is None:
        return "UNKNOWN", [], ["ACCOUNT_SNAPSHOT_UNAVAILABLE"]

    pos_cov = snapshot.endpoint_coverage.get(ROUTE_POSITION_RISK)
    if pos_cov is None or pos_cov.status != "OK":
        code = pos_cov.status if pos_cov else "MISSING"
        return "UNKNOWN", [], [f"POSITION_RISK_ENDPOINT_{code}"]

    symbol_rows = [p for p in snapshot.positions if p.symbol == card.symbol]
    active_legs = [p for p in symbol_rows if p.is_open]
    explicit_zero_rows = [p for p in symbol_rows if not p.is_open]

    if any(p.effective_direction == "CONFLICTING" for p in active_legs):
        return "UNKNOWN", active_legs, ["CONFLICTING_POSITION_AMT_AND_POSITION_SIDE"]

    if len(active_legs) > 1:
        return "MULTIPLE", active_legs, ["MULTIPLE_ACTIVE_POSITION_LEGS"]

    if len(active_legs) == 1:
        leg = active_legs[0]
        if card.episode_payload is None:
            return "UNKNOWN", active_legs, ["ACTIVE_POSITION_PRESENT_BUT_NO_DIRECTIONAL_B2_EPISODE"]
        ep_dir = str(card.episode_payload["direction"])
        if leg.effective_direction == ep_dir:
            return "SAME_DIRECTION", active_legs, ["ACTIVE_POSITION_MATCHES_SETUP_DIRECTION"]
        return "OPPOSITE_DIRECTION", active_legs, ["ACTIVE_POSITION_OPPOSES_SETUP_DIRECTION"]

    # Zero active rows for card.symbol in positionRisk.
    if explicit_zero_rows:
        return "NO_POSITION", [], ["EXPLICIT_ZERO_POSITION_ROW_OBSERVED"]

    # Symbol was OMITTED from positionRisk. NEVER fabricate zero without corroborating account evidence!
    acc_cov = snapshot.endpoint_coverage.get(ROUTE_ACCOUNT)
    account = snapshot.account
    if acc_cov is not None and acc_cov.status == "OK" and account is not None:
        if card.symbol in account.embedded_positions_zero_symbols:
            return "NO_POSITION", [], ["CORROBORATED_BY_ACCOUNT_EXPLICIT_ZERO_POSITION"]
        if (
            pos_cov.symbol == card.symbol
            and account.total_position_initial_margin is not None
            and account.total_position_initial_margin == ZERO
            and account.total_unrealized_profit == ZERO
            and len(account.embedded_position_symbols) == 0
        ):
            return "NO_POSITION", [], ["CORROBORATED_ZERO_ACCOUNT_POSITION_MARGIN_AND_EMPTY_SYMBOL_QUERY"]

    return "UNKNOWN", [], ["POSITION_ROW_OMITTED_NOT_PROOF_OF_ZERO_POSITION"]


def _assess_leg_protection(
    leg: NormalizedPosition,
    open_orders: tuple[NormalizedOrder, ...],
    open_algo_orders: tuple[NormalizedAlgoOrder, ...],
) -> dict[str, Any]:
    """Assess active SL/TP/trailing protection for one open position leg using BOTH ordinary and Algo open orders."""
    close_side = _closing_side(leg.effective_direction)
    ref_price = leg.mark_price if (leg.mark_price is not None and leg.mark_price > ZERO) else leg.entry_price
    protective_views: list[ProtectiveOrderView] = []
    conflicts: list[str] = []

    def check_trigger_side(role: str, trigger: Decimal | None) -> tuple[bool, str | None]:
        if role == "TRAILING_STOP":
            return True, None
        if trigger is None or trigger <= ZERO:
            return False, "MISSING_TRIGGER_PRICE"
        if ref_price <= ZERO:
            return True, None
        if role == "STOP_LOSS":
            if leg.effective_direction == "LONG" and trigger >= ref_price:
                return False, "LONG_SL_TRIGGER_AT_OR_ABOVE_REFERENCE_PRICE"
            if leg.effective_direction == "SHORT" and trigger <= ref_price:
                return False, "SHORT_SL_TRIGGER_AT_OR_BELOW_REFERENCE_PRICE"
        elif role == "TAKE_PROFIT":
            if leg.effective_direction == "LONG" and trigger <= ref_price:
                return False, "LONG_TP_TRIGGER_AT_OR_BELOW_REFERENCE_PRICE"
            if leg.effective_direction == "SHORT" and trigger >= ref_price:
                return False, "SHORT_TP_TRIGGER_AT_OR_ABOVE_REFERENCE_PRICE"
        return True, None

    # 1. Active ordinary open orders (strictly excluding historical/canceled/expired/filled).
    for o in open_orders:
        if o.symbol != leg.symbol:
            continue
        if o.source_endpoint != ROUTE_OPEN_ORDERS or o.status not in ACTIVE_ORDINARY_STATUSES:
            continue
        role = _classify_order_role(o.order_type)
        if role is None:
            continue
        # Must match position side semantics (or detect Hedge/One-way mismatch conflict).
        if o.position_side != leg.position_side:
            if leg.position_mode == "HEDGE" and o.position_side == "BOTH":
                conflicts.append(f"ORDINARY_ORDER_{o.order_id}_BOTH_ON_HEDGE_LEG")
            continue
        if o.side != close_side:
            if o.reduce_only or o.close_position:
                conflicts.append(f"ORDINARY_ORDER_{o.order_id}_WRONG_CLOSING_SIDE")
            continue
        is_closing_semantic = o.close_position or o.reduce_only or leg.position_mode == "HEDGE"
        if not is_closing_semantic:
            conflicts.append(f"ORDINARY_ORDER_{o.order_id}_NOT_REDUCE_ONLY_OR_CLOSE_POSITION")
            continue

        trigger_p = o.stop_price if role != "TRAILING_STOP" else o.activate_price
        trig_ok, trig_err = check_trigger_side(role, trigger_p)
        raw_qty = leg.abs_qty if o.close_position else o.remaining_qty
        if not trig_ok and trig_err:
            conflicts.append(f"ORDINARY_ORDER_{o.order_id}_{trig_err}")
        protective_views.append(
            ProtectiveOrderView(
                source="ORDINARY_OPEN_ORDERS",
                order_id=o.order_id,
                client_id=o.client_order_id,
                role=role,
                order_type=o.order_type,
                side=o.side,
                position_side=o.position_side,
                status=o.status,
                trigger_price=trigger_p,
                price=o.price if o.price > ZERO else None,
                working_type=o.working_type,
                close_position=o.close_position,
                reduce_only=o.reduce_only,
                covered_qty=raw_qty if trig_ok else ZERO,
                raw_qty=raw_qty,
                valid_direction_and_trigger=trig_ok,
                conflict_reason=trig_err,
            )
        )

    # 2. Active Algo conditional open orders (strictly excluding historical/canceled/expired/triggered).
    for a in open_algo_orders:
        if a.symbol != leg.symbol:
            continue
        if a.source_endpoint != ROUTE_OPEN_ALGO_ORDERS or a.algo_status not in ACTIVE_ALGO_STATUSES:
            continue
        role = _classify_order_role(a.order_type)
        if role is None:
            continue
        if a.position_side != leg.position_side:
            if leg.position_mode == "HEDGE" and a.position_side == "BOTH":
                conflicts.append(f"ALGO_ORDER_{a.algo_id}_BOTH_ON_HEDGE_LEG")
            continue
        if a.side != close_side:
            if a.reduce_only or a.close_position:
                conflicts.append(f"ALGO_ORDER_{a.algo_id}_WRONG_CLOSING_SIDE")
            continue
        is_closing_semantic = a.close_position or a.reduce_only or leg.position_mode == "HEDGE"
        if not is_closing_semantic:
            conflicts.append(f"ALGO_ORDER_{a.algo_id}_NOT_REDUCE_ONLY_OR_CLOSE_POSITION")
            continue

        trigger_p = a.trigger_price if role != "TRAILING_STOP" else (a.activate_price or a.trigger_price)
        trig_ok, trig_err = check_trigger_side(role, trigger_p)
        raw_qty = leg.abs_qty if a.close_position else a.quantity
        if not trig_ok and trig_err:
            conflicts.append(f"ALGO_ORDER_{a.algo_id}_{trig_err}")
        protective_views.append(
            ProtectiveOrderView(
                source="ALGO_OPEN_ORDERS",
                order_id=a.algo_id,
                client_id=a.client_algo_id,
                role=role,
                order_type=a.order_type,
                side=a.side,
                position_side=a.position_side,
                status=a.algo_status,
                trigger_price=trigger_p,
                price=a.price if (a.price is not None and a.price > ZERO) else None,
                working_type=a.working_type,
                close_position=a.close_position,
                reduce_only=a.reduce_only,
                covered_qty=raw_qty if trig_ok else ZERO,
                raw_qty=raw_qty,
                valid_direction_and_trigger=trig_ok,
                conflict_reason=trig_err,
            )
        )

    valid_sl = [v for v in protective_views if v.role == "STOP_LOSS" and v.valid_direction_and_trigger]
    valid_trailing = [v for v in protective_views if v.role == "TRAILING_STOP" and v.valid_direction_and_trigger]
    valid_tp = [v for v in protective_views if v.role == "TAKE_PROFIT" and v.valid_direction_and_trigger]

    # Conflict detection: duplicate closePosition SLs at differing trigger prices, or SL over-coverage > leg_qty.
    close_pos_sls = [v for v in valid_sl if v.close_position]
    if len(close_pos_sls) > 1:
        distinct_triggers = {v.trigger_price for v in close_pos_sls}
        if len(distinct_triggers) > 1:
            conflicts.append("CONFLICTING_MULTIPLE_CLOSE_POSITION_STOP_LOSSES")
        else:
            conflicts.append("DUPLICATE_CLOSE_POSITION_STOP_LOSSES")

    non_close_sl_qty = sum((v.covered_qty for v in valid_sl if not v.close_position), ZERO)
    if close_pos_sls and non_close_sl_qty > ZERO:
        conflicts.append("CONFLICTING_CLOSE_POSITION_AND_QTY_STOP_LOSSES")
    if non_close_sl_qty > leg.abs_qty:
        conflicts.append("STOP_LOSS_QUANTITY_EXCEEDS_POSITION_QUANTITY")

    sl_qty_total = leg.abs_qty if close_pos_sls else min(leg.abs_qty, non_close_sl_qty)
    trailing_close = any(v.close_position for v in valid_trailing)
    trailing_qty_total = leg.abs_qty if trailing_close else min(
        leg.abs_qty, sum((v.covered_qty for v in valid_trailing if not v.close_position), ZERO)
    )
    downside_covered = min(leg.abs_qty, sl_qty_total + trailing_qty_total)
    uncovered_qty = max(ZERO, leg.abs_qty - downside_covered)

    tp_close = any(v.close_position for v in valid_tp)
    tp_qty_total = leg.abs_qty if tp_close else min(
        leg.abs_qty, sum((v.covered_qty for v in valid_tp if not v.close_position), ZERO)
    )

    if conflicts:
        leg_status = "CONFLICTING"
    elif downside_covered >= leg.abs_qty and leg.abs_qty > ZERO:
        leg_status = "PROTECTED"
    elif downside_covered > ZERO:
        leg_status = "PARTIAL"
    else:
        leg_status = "UNPROTECTED"

    # Compute liquidation distance if both mark and liquidation prices are positive.
    liq_dist_price: Decimal | None = None
    liq_dist_pct: Decimal | None = None
    with localcontext(DECIMAL_CONTEXT):
        if (
            leg.liquidation_price is not None
            and leg.liquidation_price > ZERO
            and leg.mark_price is not None
            and leg.mark_price > ZERO
        ):
            liq_dist_price = abs(leg.mark_price - leg.liquidation_price)
            liq_dist_pct = (liq_dist_price / leg.mark_price) * D("100")

    return {
        "symbol": leg.symbol,
        "direction": leg.effective_direction,
        "position_side": leg.position_side,
        "position_mode": leg.position_mode,
        "quantity": decimal_str(leg.abs_qty),
        "signed_quantity": decimal_str(leg.position_amt),
        "notional": decimal_str(leg.notional),
        "entry_price": decimal_str(leg.entry_price),
        "break_even_price": decimal_str(leg.break_even_price),
        "mark_price": decimal_str(leg.mark_price),
        "unrealized_pnl": decimal_str(leg.unrealized_profit),
        "leverage": decimal_str(leg.leverage),
        "margin_type": leg.margin_type,
        "isolated_margin": decimal_str(leg.isolated_margin),
        "liquidation_price": decimal_str(leg.liquidation_price),
        "liquidation_distance_price": decimal_str(liq_dist_price),
        "liquidation_distance_pct": decimal_str(liq_dist_pct),
        "liquidation_clearance": "UNKNOWN",
        "protection_status": leg_status,
        "sl_covered_qty": decimal_str(sl_qty_total),
        "trailing_covered_qty": decimal_str(trailing_qty_total),
        "downside_covered_qty": decimal_str(downside_covered),
        "uncovered_qty": decimal_str(uncovered_qty),
        "tp_covered_qty": decimal_str(tp_qty_total),
        "active_protective_orders": [v.to_dict() for v in protective_views],
        "conflicts": conflicts,
    }


def _assess_protection(
    card: B2CardRecord,
    snapshot: PrivateAccountSnapshot | None,
    position_relation: str,
    active_legs: list[NormalizedPosition],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Evaluate protection_status across ordinary + Algo open orders; incomplete/stale endpoints => UNKNOWN."""
    if snapshot is None:
        return "UNKNOWN", [], ["ACCOUNT_SNAPSHOT_UNAVAILABLE"]

    required = (ROUTE_POSITION_RISK, ROUTE_OPEN_ORDERS, ROUTE_OPEN_ALGO_ORDERS)
    missing_or_bad: list[str] = []
    for ep in required:
        cov = snapshot.endpoint_coverage.get(ep)
        if cov is None or cov.status != "OK":
            st = cov.status if cov else "MISSING"
            missing_or_bad.append(f"{ep}:{st}")

    if missing_or_bad:
        # Incomplete or stale endpoint coverage (including missing openAlgoOrders!) MUST stay UNKNOWN.
        return "UNKNOWN", [], ["PROTECTION_ENDPOINT_COVERAGE_INCOMPLETE_OR_STALE", *missing_or_bad]

    if position_relation == "UNKNOWN":
        return "UNKNOWN", [], ["POSITION_RELATION_UNKNOWN"]

    if position_relation == "NO_POSITION":
        # Check for orphan active protective orders when there is no open position.
        orphan_orders = [
            o.order_id
            for o in snapshot.open_orders
            if o.symbol == card.symbol
            and o.status in ACTIVE_ORDINARY_STATUSES
            and (o.reduce_only or o.close_position)
        ]
        orphan_algos = [
            a.algo_id
            for a in snapshot.open_algo_orders
            if a.symbol == card.symbol
            and a.algo_status in ACTIVE_ALGO_STATUSES
            and (a.reduce_only or a.close_position)
        ]
        if orphan_orders or orphan_algos:
            return "CONFLICTING", [], ["ORPHAN_PROTECTIVE_ORDERS_WITHOUT_OPEN_POSITION"]
        return "UNKNOWN", [], ["NO_OPEN_POSITION_TO_PROTECT"]

    leg_reports = [
        _assess_leg_protection(leg, snapshot.open_orders, snapshot.open_algo_orders) for leg in active_legs
    ]
    statuses = [r["protection_status"] for r in leg_reports]
    reasons: list[str] = []
    for r in leg_reports:
        reasons.extend(r["conflicts"])

    if any(st == "CONFLICTING" for st in statuses):
        return "CONFLICTING", leg_reports, list(dict.fromkeys(reasons or ["PROTECTIVE_ORDER_CONFLICT"]))
    if all(st == "PROTECTED" for st in statuses):
        return "PROTECTED", leg_reports, ["ALL_ACTIVE_LEGS_FULLY_COVERED_BY_ACTIVE_SL_OR_TRAILING"]
    if any(st in ("PROTECTED", "PARTIAL") for st in statuses):
        return "PARTIAL", leg_reports, ["PARTIAL_DOWNSIDE_PROTECTION_UNCOVERED_QUANTITY_PRESENT"]
    return "UNPROTECTED", leg_reports, ["NO_ACTIVE_STOP_LOSS_OR_TRAILING_PROTECTION"]


def _build_human_actionability(
    *,
    card: B2CardRecord,
    account_context_status: str,
    position_relation: str,
    protection_status: str,
    signal_trade_match: str,
    accounting: AccountingReport,
    leg_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce explicit manual next checks and safety warnings; never imply unverified checks."""
    warnings: list[str] = [
        "SYNTHETIC_PRIVATE_QA_ONLY / FIXTURE_ONLY / NOT_A_REAL_ACCOUNT: offline synthetic fixture overlay only; no real account connected.",
        "ADVISORY_ONLY: market-side EXECUTABLE is never an order instruction; Layer 3 trading is disabled.",
    ]
    checks: list[str] = []

    if account_context_status == "UNAVAILABLE":
        warnings.append("ACCOUNT_UNAVAILABLE: existing exposure, conflicting positions, and TP/SL orders were NOT checked.")
        checks.append("Manually inspect Binance positions, ordinary open orders, and conditional Algo TP/SL orders before acting.")
    elif account_context_status == "STALE":
        warnings.append("ACCOUNT_STALE: private snapshot exceeds freshness window; exposure and protection are NOT verified current.")
        checks.append("Refresh private snapshot or manually check current live positions and TP/SL orders.")
    elif account_context_status == "PARTIAL":
        warnings.append("ACCOUNT_PARTIAL: one or more private endpoints are missing or partial (e.g. openAlgoOrders or history gaps).")
        checks.append("Manually verify missing endpoint state (especially conditional Algo TP/SL orders) before acting.")

    if position_relation == "OPPOSITE_DIRECTION":
        warnings.append("OPPOSITE_DIRECTION_POSITION: existing synthetic position opposes the B2 market setup.")
        checks.append("Verify whether to ignore setup, tighten existing stop, or manually close opposing leg before any new decision.")
    elif position_relation == "MULTIPLE":
        warnings.append("MULTIPLE_POSITION_LEGS: both Hedge legs or multiple active exposures exist on this symbol.")
        checks.append("Manually review both LONG and SHORT Hedge legs, net exposure, and independent leg stops.")
    elif position_relation == "SAME_DIRECTION":
        checks.append("Existing same-direction position detected; verify additive risk manually (safe_position_size is UNKNOWN).")
    elif position_relation == "UNKNOWN":
        checks.append("Position state is UNKNOWN; manually verify open positions on the venue.")

    if protection_status == "UNPROTECTED":
        warnings.append("UNPROTECTED_POSITION: active position leg has zero verified active Stop-Loss or Trailing Stop coverage.")
        checks.append("Urgently check manual Stop-Loss placement on the exchange (B3 cannot place orders).")
    elif protection_status == "PARTIAL":
        uncovered = ", ".join(f"{r['position_side']} uncovered={r['uncovered_qty']}" for r in leg_reports)
        warnings.append(f"PARTIAL_PROTECTION: uncovered position quantity remains ({uncovered}).")
        checks.append("Manually check uncovered quantity and verify active ordinary + Algo stop orders.")
    elif protection_status == "CONFLICTING":
        warnings.append("CONFLICTING_PROTECTION: contradictory or over-allocated protective orders detected.")
        checks.append("Manually reconcile conflicting Stop-Loss / Take-Profit orders on the exchange.")
    elif protection_status == "UNKNOWN" and position_relation not in ("NO_POSITION",):
        warnings.append("PROTECTION_UNKNOWN: protective coverage could not be verified from complete fresh endpoints.")

    if signal_trade_match == "AMBIGUOUS":
        warnings.append("AMBIGUOUS_SIGNAL_MATCH: multiple candidate orders/episodes or contradictory evidence detected; not forced to MATCHED.")
        checks.append("Review order/trade IDs manually or record an auditable OWNER_ENTERED association if appropriate.")
    elif signal_trade_match == "PROBABLE_MATCH":
        checks.append("Machine match is PROBABLE_MATCH (no direct clientOrderId); confirm order linkage manually.")

    if accounting.reconciliation_status == "DISCREPANCY":
        warnings.append("ACCOUNTING_DISCREPANCY: userTrades totals and income cross-check evidence do not reconcile cleanly.")
        checks.append("Inspect reconciliation discrepancies by tradeId and tranId before relying on PnL/fee summaries.")
    elif accounting.coverage_status == "PARTIAL":
        warnings.append("ACCOUNTING_PARTIAL: historical fills or income endpoints have gaps or retention limits.")

    checks.append(f"B2 market guidance ({card.market_status}): {card.card_payload.get('next_human_action', '')}")

    return {
        "summary": checks[0],
        "manual_next_checks": checks,
        "warnings": warnings,
        "exposure_and_tpsl_verified": (
            account_context_status == "SYNTHETIC_CONNECTED"
            and position_relation != "UNKNOWN"
            and protection_status in ("PROTECTED", "PARTIAL", "UNPROTECTED", "CONFLICTING")
        ),
        "order_instruction_issued": False,
    }


def build_account_overlay(
    *,
    card: B2CardRecord,
    snapshot: PrivateAccountSnapshot | None,
    peer_cards: tuple[B2CardRecord, ...] = (),
    manual_associations: tuple[ManualAssociation, ...] = (),
    recorded_wall_ms: int | None = None,
) -> dict[str, Any]:
    """Build an immutable B3 account-aware overlay linked to a verified read-only B2 card & episode."""
    account_context_status = snapshot.overall_status if snapshot is not None else "UNAVAILABLE"
    position_relation, active_legs, pos_reasons = _evaluate_position_relation(card, snapshot)
    protection_status, leg_reports, prot_reasons = _assess_protection(
        card, snapshot, position_relation, active_legs
    )
    match_result: EpisodeMatchResult = match_episode_to_account(
        card,
        snapshot,
        peer_cards=peer_cards,
        manual_associations=manual_associations,
    )
    accounting: AccountingReport = compute_accounting_report(
        snapshot,
        card=card,
        match_result=match_result,
        symbol_filter=card.symbol,
    )
    human_actionability = _build_human_actionability(
        card=card,
        account_context_status=account_context_status,
        position_relation=position_relation,
        protection_status=protection_status,
        signal_trade_match=match_result.signal_trade_match,
        accounting=accounting,
        leg_reports=leg_reports,
    )

    acc_cov = snapshot.endpoint_coverage.get(ROUTE_ACCOUNT) if snapshot else None
    if snapshot is not None and snapshot.account is not None and acc_cov is not None and acc_cov.status == "OK":
        portfolio_context: dict[str, Any] = {
            "available": True,
            "wallet_balance": decimal_str(snapshot.account.wallet_balance),
            "available_balance": decimal_str(snapshot.account.available_balance),
            "margin_balance": decimal_str(snapshot.account.margin_balance),
            "total_unrealized_profit": decimal_str(snapshot.account.total_unrealized_profit),
            "total_initial_margin": decimal_str(snapshot.account.total_initial_margin),
            "total_maint_margin": decimal_str(snapshot.account.total_maint_margin),
            "multi_assets_margin": snapshot.account.multi_assets_margin,
            "portfolio_exposure_limits": "UNKNOWN",
            "safe_position_size": "UNKNOWN",
            "liquidation_clearance": "UNKNOWN",
            "owner_historical_context_not_policy": OWNER_HISTORICAL_CONTEXT_NOT_POLICY,
        }
    else:
        portfolio_context = {
            "available": False,
            "wallet_balance": "UNKNOWN",
            "available_balance": "UNKNOWN",
            "margin_balance": "UNKNOWN",
            "total_unrealized_profit": "UNKNOWN",
            "total_initial_margin": "UNKNOWN",
            "total_maint_margin": "UNKNOWN",
            "multi_assets_margin": "UNKNOWN",
            "portfolio_exposure_limits": "UNKNOWN",
            "safe_position_size": "UNKNOWN",
            "liquidation_clearance": "UNKNOWN",
            "owner_historical_context_not_policy": OWNER_HISTORICAL_CONTEXT_NOT_POLICY,
        }

    # Overlay identity is deterministic from immutable B2 card digest + snapshot_id + manual links.
    overlay_id = digest(
        [
            SCHEMA_OVERLAY,
            card.card_id,
            card.payload_sha256,
            snapshot.snapshot_id if snapshot else "UNAVAILABLE",
            [m.association_id for m in manual_associations if m.b2_episode_id == card.episode_id],
        ]
    )
    wall_ms = (time.time_ns() // 1_000_000) if recorded_wall_ms is None else recorded_wall_ms

    return {
        "schema": SCHEMA_OVERLAY,
        "overlay_id": overlay_id,
        "journal_recorded_wall_ms": wall_ms,
        # Exact immutable B2 linkage (never modified or rewritten).
        "b2_card_id": card.card_id,
        "b2_episode_id": card.episode_id,
        "b2_card_sha256": card.payload_sha256,
        "b2_evaluated_ms": card.as_of_ms,
        "b2_market_evidence": card.evidence,
        "b2_original_account_fields": {
            "account_context_status": card.card_payload.get("account_context_status"),
            "account_overlay": card.card_payload.get("account_overlay"),
            "portfolio_exposure_limits": card.card_payload.get("portfolio_exposure_limits"),
        },
        "symbol": card.symbol,
        "snapshot_id": snapshot.snapshot_id if snapshot else None,
        "snapshot_mode": snapshot.snapshot_mode if snapshot else "UNAVAILABLE",
        "snapshot_as_of_venue_ms": snapshot.as_of_venue_ms if snapshot else None,
        # Six required independent dimensions:
        "market_setup_status": card.market_status,
        "account_context_status": account_context_status,
        "position_relation": position_relation,
        "protection_status": protection_status,
        "signal_trade_match": match_result.signal_trade_match,
        "human_actionability": human_actionability,
        # Explicit policy boundaries:
        "portfolio_exposure_limits": "UNKNOWN",
        "safe_position_size": "UNKNOWN",
        "liquidation_clearance": "UNKNOWN",
        # Detailed contexts:
        "position_relation_reasons": pos_reasons,
        "protection_reasons": prot_reasons,
        "position_context": leg_reports,
        "portfolio_context": portfolio_context,
        "endpoint_coverage": (
            {k: v.to_dict() for k, v in sorted(snapshot.endpoint_coverage.items())} if snapshot else {}
        ),
        "signal_match_detail": match_result.to_dict(),
        "accounting_reconciliation": accounting.to_dict(),
        **synthetic_provenance_block(),
    }
