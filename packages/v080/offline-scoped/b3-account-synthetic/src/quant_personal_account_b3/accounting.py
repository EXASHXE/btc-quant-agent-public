"""Canonical Decimal accounting, multi-asset separation, fill-vs-income cross-check, and realized net R."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any

from .b2_reader import B2CardRecord
from .client import ROUTE_INCOME, ROUTE_USER_TRADES
from .matching import EpisodeMatchResult
from .models import (
    DECIMAL_CONTEXT,
    SCHEMA_RECONCILIATION,
    ZERO,
    D,
    decimal_str,
    synthetic_provenance_block,
)
from .normalize import (
    EndpointCoverage,
    NormalizedFill,
    NormalizedIncome,
    PrivateAccountSnapshot,
)


def _add_asset(bucket: dict[str, Decimal], asset: str, amount: Decimal) -> None:
    bucket[asset] = bucket.get(asset, ZERO) + amount


def _serialize_asset_map(bucket: dict[str, Decimal]) -> dict[str, str]:
    return {asset: format(val, "f") for asset, val in sorted(bucket.items())}


def _dedup_fills(fills: Sequence[NormalizedFill]) -> tuple[list[NormalizedFill], list[dict[str, Any]]]:
    by_key: dict[tuple[str, int], NormalizedFill] = {}
    conflicts: list[dict[str, Any]] = []
    for fill in fills:
        key = (fill.symbol, fill.trade_id)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = fill
        elif prev != fill:
            conflicts.append(
                {
                    "type": "CONFLICTING_DUPLICATE_FILL",
                    "symbol": fill.symbol,
                    "trade_id": fill.trade_id,
                }
            )
    ordered = sorted(by_key.values(), key=lambda f: (f.trade_time_ms, f.symbol, f.trade_id))
    return ordered, conflicts


def _dedup_income(rows: Sequence[NormalizedIncome]) -> tuple[list[NormalizedIncome], list[dict[str, Any]]]:
    by_key: dict[tuple[str, str, str, int], NormalizedIncome] = {}
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        key = row.dedup_key()
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = row
        elif prev != row:
            conflicts.append(
                {
                    "type": "CONFLICTING_DUPLICATE_INCOME",
                    "tran_id": row.tran_id,
                    "income_type": row.income_type,
                    "asset": row.asset,
                }
            )
    ordered = sorted(by_key.values(), key=lambda r: (r.time_ms, r.tran_id, r.income_type, r.asset))
    return ordered, conflicts


def _quote_asset_for_symbol(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return "USDT"
    if symbol.endswith("USDC"):
        return "USDC"
    return "UNKNOWN_QUOTE_ASSET"


@dataclass(frozen=True)
class AccountingReport:
    """Canonical Decimal accounting report with separate cross-check evidence and multi-asset isolation."""

    coverage_status: str  # COMPLETE | PARTIAL | UNAVAILABLE
    missing_windows: tuple[dict[str, Any], ...]
    canonical_policy: dict[str, str]
    canonical_realized_pnl_by_asset: dict[str, Decimal]
    canonical_commission_paid_by_asset: dict[str, Decimal]
    canonical_funding_fee_by_asset: dict[str, Decimal]
    other_income_by_type_and_asset: dict[str, dict[str, Decimal]]
    canonical_net_cashflow_by_asset: dict[str, Decimal]
    single_currency_net_available: bool
    cross_check_realized_pnl: dict[str, Any]
    cross_check_commission: dict[str, Any]
    reconciliation_status: str  # RECONCILED | DISCREPANCY | PARTIAL_COVERAGE | UNAVAILABLE
    discrepancies: tuple[dict[str, Any], ...]
    per_trade_view: tuple[dict[str, Any], ...]
    per_order_view: tuple[dict[str, Any], ...]
    per_period_view: tuple[dict[str, Any], ...]
    per_episode_view: dict[str, Any] | None
    actual_vs_b2_projected: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_RECONCILIATION,
            "coverage_status": self.coverage_status,
            "missing_windows": list(self.missing_windows),
            "canonical_policy": self.canonical_policy,
            "canonical_totals": {
                "realized_pnl_by_asset": _serialize_asset_map(self.canonical_realized_pnl_by_asset),
                "commission_paid_by_asset": _serialize_asset_map(self.canonical_commission_paid_by_asset),
                "funding_fee_by_asset": _serialize_asset_map(self.canonical_funding_fee_by_asset),
                "other_income_by_type_and_asset": {
                    itype: _serialize_asset_map(amap)
                    for itype, amap in sorted(self.other_income_by_type_and_asset.items())
                },
                "net_trading_cashflow_by_asset": _serialize_asset_map(self.canonical_net_cashflow_by_asset),
                "single_currency_net_available": self.single_currency_net_available,
                "cross_asset_fx_conversion": "NOT_PERFORMED_STRICT_ASSET_SEPARATION",
            },
            "reconciliation_cross_check": {
                "status": self.reconciliation_status,
                "realized_pnl": self.cross_check_realized_pnl,
                "commission": self.cross_check_commission,
                "discrepancies": list(self.discrepancies),
            },
            "ledger_views": {
                "per_trade": list(self.per_trade_view),
                "per_order": list(self.per_order_view),
                "per_period": list(self.per_period_view),
                "per_episode": self.per_episode_view,
            },
            "actual_vs_b2_projected": self.actual_vs_b2_projected,
            **synthetic_provenance_block(),
        }


CANONICAL_ACCOUNTING_POLICY = {
    "executed_qty_fill_price_realized_pnl_commission": "CANONICAL_FROM_USER_TRADES",
    "funding_cashflow": "CANONICAL_FROM_INCOME_FUNDING_FEE",
    "income_commission_and_realized_pnl": "RECONCILIATION_CROSS_CHECK_ONLY_NEVER_DOUBLE_COUNTED",
    "other_income_types": "SEPARATE_LEDGER_CATEGORIES",
    "asset_conversion": "NEVER_SUM_DIFFERENT_ASSETS_WITHOUT_VERIFIED_CONVERSION",
    "numeric_precision": "EXACT_DECIMAL_NO_BINARY_FLOAT",
}


def compute_accounting_report(
    snapshot: PrivateAccountSnapshot | None,
    *,
    card: B2CardRecord | None = None,
    match_result: EpisodeMatchResult | None = None,
    symbol_filter: str | None = None,
) -> AccountingReport:
    """Build canonical Decimal accounting totals, cross-checks, ledger views, and realized net R."""
    if snapshot is None:
        return AccountingReport(
            coverage_status="UNAVAILABLE",
            missing_windows=(),
            canonical_policy=dict(CANONICAL_ACCOUNTING_POLICY),
            canonical_realized_pnl_by_asset={},
            canonical_commission_paid_by_asset={},
            canonical_funding_fee_by_asset={},
            other_income_by_type_and_asset={},
            canonical_net_cashflow_by_asset={},
            single_currency_net_available=False,
            cross_check_realized_pnl={"status": "UNAVAILABLE"},
            cross_check_commission={"status": "UNAVAILABLE"},
            reconciliation_status="UNAVAILABLE",
            discrepancies=(),
            per_trade_view=(),
            per_order_view=(),
            per_period_view=(),
            per_episode_view=None,
            actual_vs_b2_projected=_build_actual_vs_projected_unavailable(card),
        )

    trades_cov: EndpointCoverage | None = snapshot.endpoint_coverage.get(ROUTE_USER_TRADES)
    income_cov: EndpointCoverage | None = snapshot.endpoint_coverage.get(ROUTE_INCOME)

    missing_windows: list[dict[str, Any]] = []
    for ep_name, cov in ((ROUTE_USER_TRADES, trades_cov), (ROUTE_INCOME, income_cov)):
        if cov is None or cov.status in ("MISSING", "ERROR", "PERMISSION_DENIED", "RATE_LIMITED", "NOT_FETCHED"):
            missing_windows.append(
                {
                    "endpoint": ep_name,
                    "reason": cov.status if cov else "MISSING",
                    "error_code": cov.error_code if cov else "ENDPOINT_NOT_PRESENT",
                }
            )
        else:
            for gap in cov.gap_windows:
                missing_windows.append({"endpoint": ep_name, **gap})
            if cov.status in ("PARTIAL", "STALE") and not cov.gap_windows:
                missing_windows.append({"endpoint": ep_name, "reason": cov.status, "error_code": cov.error_code})

    trades_ok = trades_cov is not None and trades_cov.status == "OK" and trades_cov.page_coverage_complete
    income_ok = income_cov is not None and income_cov.status == "OK" and income_cov.page_coverage_complete

    if not trades_ok and not income_ok and not snapshot.fills and not snapshot.income_rows:
        coverage_status = "UNAVAILABLE"
    elif trades_ok and income_ok and not missing_windows:
        coverage_status = "COMPLETE"
    else:
        coverage_status = "PARTIAL"

    raw_fills = [f for f in snapshot.fills if symbol_filter is None or f.symbol == symbol_filter]
    raw_income = [
        r for r in snapshot.income_rows if symbol_filter is None or r.symbol == "" or r.symbol == symbol_filter
    ]

    fills, fill_conflicts = _dedup_fills(raw_fills)
    income_rows, inc_conflicts = _dedup_income(raw_income)

    # Canonical aggregations (strictly separated by asset).
    realized_pnl_by_asset: dict[str, Decimal] = {}
    commission_paid_by_asset: dict[str, Decimal] = {}
    funding_by_asset: dict[str, Decimal] = {}
    other_income: dict[str, dict[str, Decimal]] = {}

    # Cross-check evidence from income rows (NEVER added to canonical realized PnL or commission totals!).
    income_realized_pnl_by_asset: dict[str, Decimal] = {}
    income_commission_by_asset: dict[str, Decimal] = {}
    income_rpnl_tran_ids: list[str] = []
    income_comm_tran_ids: list[str] = []

    with localcontext(DECIMAL_CONTEXT):
        for fill in fills:
            quote_asset = _quote_asset_for_symbol(fill.symbol)
            _add_asset(realized_pnl_by_asset, quote_asset, fill.realized_pnl)
            _add_asset(commission_paid_by_asset, fill.commission_asset, fill.commission)

        for inc in income_rows:
            if inc.income_type == "FUNDING_FEE":
                _add_asset(funding_by_asset, inc.asset, inc.income)
            elif inc.income_type == "REALIZED_PNL":
                _add_asset(income_realized_pnl_by_asset, inc.asset, inc.income)
                income_rpnl_tran_ids.append(inc.tran_id)
            elif inc.income_type == "COMMISSION":
                _add_asset(income_commission_by_asset, inc.asset, inc.income)
                income_comm_tran_ids.append(inc.tran_id)
            else:
                bucket = other_income.setdefault(inc.income_type, {})
                _add_asset(bucket, inc.asset, inc.income)

        # Canonical net trading cashflow per asset: realized_pnl - commission_paid + funding_fee (same asset only!).
        all_trading_assets = sorted(
            set(realized_pnl_by_asset) | set(commission_paid_by_asset) | set(funding_by_asset)
        )
        net_by_asset: dict[str, Decimal] = {}
        for asset in all_trading_assets:
            net_by_asset[asset] = (
                realized_pnl_by_asset.get(asset, ZERO)
                - commission_paid_by_asset.get(asset, ZERO)
                + funding_by_asset.get(asset, ZERO)
            )
        single_currency_net = len(all_trading_assets) <= 1

        # Cross-check reconciliation: userTrades vs income[REALIZED_PNL] and income[COMMISSION].
        discrepancies: list[dict[str, Any]] = [*fill_conflicts, *inc_conflicts]

        rpnl_assets = sorted(set(realized_pnl_by_asset) | set(income_realized_pnl_by_asset))
        rpnl_deltas: dict[str, str] = {}
        rpnl_has_mismatch = False
        for asset in rpnl_assets:
            canon_val = realized_pnl_by_asset.get(asset, ZERO)
            inc_val = income_realized_pnl_by_asset.get(asset, ZERO)
            delta = inc_val - canon_val
            rpnl_deltas[asset] = format(delta, "f")
            if delta != ZERO:
                rpnl_has_mismatch = True
                discrepancies.append(
                    {
                        "type": "REALIZED_PNL_RECONCILIATION_DISCREPANCY",
                        "asset": asset,
                        "canonical_user_trades": format(canon_val, "f"),
                        "income_cross_check": format(inc_val, "f"),
                        "delta": format(delta, "f"),
                        "trade_ids": [f.trade_id for f in fills if _quote_asset_for_symbol(f.symbol) == asset],
                        "tran_ids": income_rpnl_tran_ids,
                    }
                )

        comm_assets = sorted(set(commission_paid_by_asset) | set(income_commission_by_asset))
        comm_deltas: dict[str, str] = {}
        comm_has_mismatch = False
        for asset in comm_assets:
            # userTrades.commission is positive fee paid; income[COMMISSION].income is negative cashflow.
            expected_cashflow = -commission_paid_by_asset.get(asset, ZERO)
            inc_cashflow = income_commission_by_asset.get(asset, ZERO)
            delta = inc_cashflow - expected_cashflow
            comm_deltas[asset] = format(delta, "f")
            if delta != ZERO:
                comm_has_mismatch = True
                discrepancies.append(
                    {
                        "type": "COMMISSION_RECONCILIATION_DISCREPANCY",
                        "asset": asset,
                        "canonical_user_trades_cashflow": format(expected_cashflow, "f"),
                        "income_cross_check_cashflow": format(inc_cashflow, "f"),
                        "delta": format(delta, "f"),
                        "trade_ids": [f.trade_id for f in fills if f.commission_asset == asset],
                        "tran_ids": income_comm_tran_ids,
                    }
                )

        if discrepancies:
            recon_status = "DISCREPANCY"
        elif coverage_status == "COMPLETE":
            recon_status = "RECONCILED"
        elif coverage_status == "PARTIAL":
            recon_status = "PARTIAL_COVERAGE"
        else:
            recon_status = "UNAVAILABLE"

        cross_rpnl = {
            "status": "DISCREPANCY" if rpnl_has_mismatch else ("PARTIAL_COVERAGE" if coverage_status != "COMPLETE" else "RECONCILED"),
            "canonical_user_trades_by_asset": _serialize_asset_map(realized_pnl_by_asset),
            "income_evidence_by_asset": _serialize_asset_map(income_realized_pnl_by_asset),
            "delta_by_asset": rpnl_deltas,
        }
        cross_comm = {
            "status": "DISCREPANCY" if comm_has_mismatch else ("PARTIAL_COVERAGE" if coverage_status != "COMPLETE" else "RECONCILED"),
            "canonical_user_trades_paid_by_asset": _serialize_asset_map(commission_paid_by_asset),
            "income_evidence_cashflow_by_asset": _serialize_asset_map(income_commission_by_asset),
            "delta_cashflow_by_asset": comm_deltas,
        }

        per_trade = tuple(_build_per_trade_view(fills))
        per_order = tuple(_build_per_order_view(fills))
        per_period = tuple(_build_per_period_view(fills, income_rows, coverage_status))
        per_episode, actual_vs_projected = _build_episode_ledger_and_net_r(
            card=card,
            match_result=match_result,
            fills=fills,
            income_rows=income_rows,
            trades_ok=trades_ok,
            income_ok=income_ok,
        )

    return AccountingReport(
        coverage_status=coverage_status,
        missing_windows=tuple(missing_windows),
        canonical_policy=dict(CANONICAL_ACCOUNTING_POLICY),
        canonical_realized_pnl_by_asset=realized_pnl_by_asset,
        canonical_commission_paid_by_asset=commission_paid_by_asset,
        canonical_funding_fee_by_asset=funding_by_asset,
        other_income_by_type_and_asset=other_income,
        canonical_net_cashflow_by_asset=net_by_asset,
        single_currency_net_available=single_currency_net,
        cross_check_realized_pnl=cross_rpnl,
        cross_check_commission=cross_comm,
        reconciliation_status=recon_status,
        discrepancies=tuple(discrepancies),
        per_trade_view=per_trade,
        per_order_view=per_order,
        per_period_view=per_period,
        per_episode_view=per_episode,
        actual_vs_b2_projected=actual_vs_projected,
    )


def _build_per_trade_view(fills: list[NormalizedFill]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": f.symbol,
            "trade_id": f.trade_id,
            "order_id": f.order_id,
            "side": f.side,
            "position_side": f.position_side,
            "price": decimal_str(f.price),
            "qty": decimal_str(f.qty),
            "quote_qty": decimal_str(f.quote_qty),
            "realized_pnl": decimal_str(f.realized_pnl),
            "realized_pnl_asset": _quote_asset_for_symbol(f.symbol),
            "commission": decimal_str(f.commission),
            "commission_asset": f.commission_asset,
            "trade_time_ms": f.trade_time_ms,
        }
        for f in fills
    ]


def _build_per_order_view(fills: list[NormalizedFill]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[NormalizedFill]] = {}
    for fill in fills:
        grouped.setdefault((fill.symbol, fill.order_id), []).append(fill)

    rows: list[dict[str, Any]] = []
    for (symbol, order_id), group in sorted(grouped.items(), key=lambda kv: (kv[1][0].trade_time_ms, kv[0][1])):
        total_qty = sum((f.qty for f in group), ZERO)
        total_quote = sum((f.price * f.qty for f in group), ZERO)
        vwap = (total_quote / total_qty) if total_qty > ZERO else ZERO
        rpnl = sum((f.realized_pnl for f in group), ZERO)
        comm_by_asset: dict[str, Decimal] = {}
        for f in group:
            _add_asset(comm_by_asset, f.commission_asset, f.commission)
        rows.append(
            {
                "symbol": symbol,
                "order_id": order_id,
                "side": group[0].side,
                "position_side": group[0].position_side,
                "fill_count": len(group),
                "is_partial_fill_aggregate": len(group) > 1,
                "trade_ids": [f.trade_id for f in group],
                "executed_qty": format(total_qty, "f"),
                "vwap_fill_price": format(vwap, "f"),
                "quote_qty": format(total_quote, "f"),
                "realized_pnl": format(rpnl, "f"),
                "realized_pnl_asset": _quote_asset_for_symbol(symbol),
                "commission_by_asset": _serialize_asset_map(comm_by_asset),
                "first_trade_time_ms": min(f.trade_time_ms for f in group),
                "last_trade_time_ms": max(f.trade_time_ms for f in group),
            }
        )
    return rows


def _utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _build_per_period_view(
    fills: list[NormalizedFill],
    income_rows: list[NormalizedIncome],
    coverage_status: str,
) -> list[dict[str, Any]]:
    days: dict[str, dict[str, Any]] = {}

    def ensure_day(day: str) -> dict[str, Any]:
        if day not in days:
            days[day] = {
                "period_utc_day": day,
                "coverage_status": coverage_status,
                "fill_count": 0,
                "realized_pnl_by_asset": {},
                "commission_paid_by_asset": {},
                "funding_fee_by_asset": {},
                "other_income_by_type_and_asset": {},
            }
        return days[day]

    for f in fills:
        rec = ensure_day(_utc_day(f.trade_time_ms))
        rec["fill_count"] += 1
        _add_asset(rec["realized_pnl_by_asset"], _quote_asset_for_symbol(f.symbol), f.realized_pnl)
        _add_asset(rec["commission_paid_by_asset"], f.commission_asset, f.commission)

    for inc in income_rows:
        rec = ensure_day(_utc_day(inc.time_ms))
        if inc.income_type == "FUNDING_FEE":
            _add_asset(rec["funding_fee_by_asset"], inc.asset, inc.income)
        elif inc.income_type not in ("COMMISSION", "REALIZED_PNL"):
            bucket = rec["other_income_by_type_and_asset"].setdefault(inc.income_type, {})
            _add_asset(bucket, inc.asset, inc.income)

    output: list[dict[str, Any]] = []
    for day in sorted(days):
        rec = days[day]
        output.append(
            {
                "period_utc_day": day,
                "coverage_status": rec["coverage_status"],
                "fill_count": rec["fill_count"],
                "realized_pnl_by_asset": _serialize_asset_map(rec["realized_pnl_by_asset"]),
                "commission_paid_by_asset": _serialize_asset_map(rec["commission_paid_by_asset"]),
                "funding_fee_by_asset": _serialize_asset_map(rec["funding_fee_by_asset"]),
                "other_income_by_type_and_asset": {
                    k: _serialize_asset_map(v) for k, v in sorted(rec["other_income_by_type_and_asset"].items())
                },
            }
        )
    return output


def _extract_b2_projected(card: B2CardRecord | None) -> dict[str, Any]:
    if card is None or card.plan is None:
        return {"available": False, "reason": "NO_B2_MARKET_PLAN"}
    plan = card.plan
    if plan.get("schema") != "B2_MARKET_PLAN_V1":
        return {"available": False, "schema": plan.get("schema"), "reason": "B2_PLAN_IS_PREVIEW_ONLY"}
    return {
        "available": True,
        "schema": plan["schema"],
        "price_currency": plan.get("price_currency", "USDT"),
        "entry_fill": plan.get("entry_fill"),
        "hard_stop": plan.get("hard_stop"),
        "expected_stop_stress_fill": plan.get("expected_stop_stress_fill"),
        "unit_stop_loss_usdt": plan.get("unit_stop_loss_usdt"),
        "fee_rate_each_side": plan.get("fee_rate_each_side"),
        "slippage_bps_each_side": plan.get("slippage_bps_each_side"),
        "spread_usdt": plan.get("spread_usdt"),
        "funding_stress_cost_usdt_per_base": (plan.get("funding") or {}).get("stress_cost_usdt_per_base"),
        "planned_targets": [
            {"label": t["label"], "price": t["price"], "net_r": t.get("net_r"), "status": t["status"]}
            for t in plan.get("targets", [])
        ],
        "planned_conditional_paths": plan.get("conditional_paths", []),
    }


def _build_actual_vs_projected_unavailable(card: B2CardRecord | None) -> dict[str, Any]:
    return {
        "b2_projected_assumptions": _extract_b2_projected(card),
        "actual_accounting_summary": None,
        "planned_vs_realized_net_r": {
            "realized_net_r_status": "ACTUAL_R_UNAVAILABLE",
            "realized_net_r": None,
            "reasons": ["ACCOUNT_CONTEXT_UNAVAILABLE"],
            "risk_denominator_usdt": None,
            "risk_denominator_provenance": None,
        },
    }


def _build_episode_ledger_and_net_r(
    *,
    card: B2CardRecord | None,
    match_result: EpisodeMatchResult | None,
    fills: list[NormalizedFill],
    income_rows: list[NormalizedIncome],
    trades_ok: bool,
    income_ok: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if card is None:
        return None, None

    projected = _extract_b2_projected(card)
    if match_result is None or card.episode_id is None:
        return None, {
            "b2_projected_assumptions": projected,
            "actual_accounting_summary": None,
            "planned_vs_realized_net_r": {
                "realized_net_r_status": "ACTUAL_R_UNAVAILABLE",
                "realized_net_r": None,
                "reasons": ["NO_B2_EPISODE_OR_MATCH"],
                "risk_denominator_usdt": None,
                "risk_denominator_provenance": None,
            },
        }

    matched_tids = set(match_result.matched_trade_ids)
    matched_fills = [f for f in fills if f.trade_id in matched_tids]
    entry_fills = [f for f in matched_fills if f.trade_id in set(match_result.entry_fill_ids)]
    exit_fills = [f for f in matched_fills if f.trade_id in set(match_result.exit_fill_ids)]

    matched_tran_ids = set(match_result.matched_income_tran_ids)
    matched_funding = [r for r in income_rows if r.tran_id in matched_tran_ids and r.income_type == "FUNDING_FEE"]

    entry_qty = sum((f.qty for f in entry_fills), ZERO)
    entry_quote = sum((f.price * f.qty for f in entry_fills), ZERO)
    entry_vwap = (entry_quote / entry_qty) if entry_qty > ZERO else None

    exit_qty = sum((f.qty for f in exit_fills), ZERO)
    exit_quote = sum((f.price * f.qty for f in exit_fills), ZERO)
    exit_vwap = (exit_quote / exit_qty) if exit_qty > ZERO else None

    ep_rpnl: dict[str, Decimal] = {}
    ep_comm: dict[str, Decimal] = {}
    ep_funding: dict[str, Decimal] = {}
    for f in matched_fills:
        _add_asset(ep_rpnl, _quote_asset_for_symbol(f.symbol), f.realized_pnl)
        _add_asset(ep_comm, f.commission_asset, f.commission)
    for inc in matched_funding:
        _add_asset(ep_funding, inc.asset, inc.income)

    ep_assets = sorted(set(ep_rpnl) | set(ep_comm) | set(ep_funding))
    ep_net: dict[str, Decimal] = {
        a: ep_rpnl.get(a, ZERO) - ep_comm.get(a, ZERO) + ep_funding.get(a, ZERO) for a in ep_assets
    }

    # Evaluate realized net R strictly against B2's explicit unit_stop_loss_usdt risk basis.
    r_reasons: list[str] = []
    realized_r_status = "ACTUAL_R_UNAVAILABLE"
    realized_r: Decimal | None = None
    denom_usdt: Decimal | None = None
    denom_provenance: str | None = None

    price_ccy = str(projected.get("price_currency", "USDT")) if projected.get("available") else "USDT"

    if not projected.get("available"):
        r_reasons.append("MISSING_B2_STOP_RISK_BASIS")
    if match_result.signal_trade_match != "MATCHED":
        r_reasons.append(f"SIGNAL_MATCH_NOT_CONFIRMED_{match_result.signal_trade_match}")
    if match_result.shared_position_episode_ids:
        r_reasons.append("SHARED_POSITION_MULTI_EPISODE_ALLOCATION_UNPROVEN")
    if not trades_ok:
        r_reasons.append("USER_TRADES_COVERAGE_INCOMPLETE")
    if not income_ok:
        r_reasons.append("FUNDING_INCOME_COVERAGE_INCOMPLETE")
    if entry_qty <= ZERO:
        r_reasons.append("NO_MATCHED_ENTRY_FILLS")
    if exit_qty <= ZERO:
        r_reasons.append("NO_MATCHED_EXIT_FILLS")
    elif entry_qty > ZERO and exit_qty < entry_qty:
        r_reasons.append("PARTIAL_EXIT_POSITION_STILL_OPEN")
    elif entry_qty > ZERO and exit_qty > entry_qty:
        r_reasons.append("EXIT_QTY_EXCEEDS_MATCHED_ENTRY_QTY")

    non_quote_fee_assets = [a for a in ep_comm if a != price_ccy and ep_comm[a] != ZERO]
    non_quote_funding_assets = [a for a in ep_funding if a != price_ccy and ep_funding[a] != ZERO]
    if non_quote_fee_assets or non_quote_funding_assets:
        r_reasons.append("NON_QUOTE_FEE_OR_FUNDING_ASSET_UNVALUED")

    if not r_reasons:
        unit_stop = D(str(projected["unit_stop_loss_usdt"]))
        if unit_stop <= ZERO:
            r_reasons.append("INVALID_B2_UNIT_STOP_LOSS")
        else:
            denom_usdt = unit_stop * entry_qty
            denom_provenance = f"B2_MARKET_PLAN_V1.unit_stop_loss_usdt ({unit_stop}) * actual_matched_entry_qty ({entry_qty})"
            actual_net_quote = ep_net.get(price_ccy, ZERO)
            realized_r = actual_net_quote / denom_usdt
            realized_r_status = "AVAILABLE"
    elif (
        projected.get("available")
        and match_result.signal_trade_match == "MATCHED"
        and entry_qty > ZERO
        and exit_qty > ZERO
        and not non_quote_fee_assets
        and not non_quote_funding_assets
        and set(r_reasons).issubset({"FUNDING_INCOME_COVERAGE_INCOMPLETE", "PARTIAL_EXIT_POSITION_STILL_OPEN"})
    ):
        realized_r_status = "PARTIAL"
    else:
        realized_r_status = "ACTUAL_R_UNAVAILABLE"

    episode_ledger = {
        "b2_episode_id": card.episode_id,
        "b2_card_id": card.card_id,
        "symbol": card.symbol,
        "match_status": match_result.signal_trade_match,
        "coverage_status": "COMPLETE" if (trades_ok and income_ok) else "PARTIAL",
        "entry_fill_count": len(entry_fills),
        "exit_fill_count": len(exit_fills),
        "entry_qty": format(entry_qty, "f"),
        "entry_vwap": decimal_str(entry_vwap),
        "exit_qty": format(exit_qty, "f"),
        "exit_vwap": decimal_str(exit_vwap),
        "realized_pnl_by_asset": _serialize_asset_map(ep_rpnl),
        "commission_paid_by_asset": _serialize_asset_map(ep_comm),
        "funding_fee_by_asset": _serialize_asset_map(ep_funding),
        "net_cashflow_by_asset": _serialize_asset_map(ep_net),
        "single_currency_net_available": len(ep_assets) <= 1,
    }

    actual_vs_projected = {
        "b2_projected_assumptions": projected,
        "actual_accounting_summary": episode_ledger,
        "planned_vs_realized_net_r": {
            "realized_net_r_status": realized_r_status,
            "realized_net_r": decimal_str(realized_r),
            "reasons": r_reasons if r_reasons else ["ALL_REQUIRED_EVIDENCE_AND_B2_RISK_BASIS_PRESENT"],
            "risk_denominator_usdt": decimal_str(denom_usdt),
            "risk_denominator_provenance": denom_provenance,
            "planned_tp1_net_r": (
                projected["planned_targets"][0].get("net_r")
                if projected.get("available") and projected.get("planned_targets")
                else None
            ),
        },
    }
    return episode_ledger, actual_vs_projected
