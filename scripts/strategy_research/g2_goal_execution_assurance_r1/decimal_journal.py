"""Independent stdlib Decimal cash, quantity, funding, and Mark liquidation journal.

Contains ZERO imports from production replay, economics, book, account, or audit modules.
Provides two independent Decimal implementations (chronological event ledger and
double-entry stage balance-sheet checker) to cross-verify synthetic and historical episodes.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import UTC, datetime
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    Decimal,
    InvalidOperation,
    localcontext,
)
from pathlib import Path
from typing import Any

import numpy as np

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
TICK_DEC = Decimal("0.1")
LOT_DEC = Decimal("0.001")
MIN_NOTIONAL_DEC = Decimal("5.0")

COST_MODELS_DEC: dict[str, dict[str, Decimal]] = {
    "BASE": {
        "fee_bps": Decimal(6),
        "spread_bps": Decimal(4),
        "slip_bps": Decimal(3),
        "nominal_roundtrip_bps": Decimal(22),
    },
    "STRESS": {
        "fee_bps": Decimal(12),
        "spread_bps": Decimal(8),
        "slip_bps": Decimal(6),
        "nominal_roundtrip_bps": Decimal(44),
    },
}

SCHEME_HORIZONS: dict[str, int] = {"E0": 12, "H1": 18, "H2": 24, "E1": 12, "E2": 12}


def D(value: Any, label: str = "value") -> Decimal:
    """Convert any numeric or string input to an exact finite Decimal."""
    try:
        res = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid Decimal for {label}: {value!r}") from exc
    if not res.is_finite():
        raise ValueError(f"Non-finite Decimal for {label}: {value!r}")
    return res


def dec_tick(price: Decimal, upwards: bool) -> Decimal:
    """Round price to 0.1 tick with 1e-12 integer-tick tolerance matching exchange tick grid."""
    with localcontext() as ctx:
        ctx.prec = 50
        scaled = price / TICK_DEC
        eps = Decimal("1e-11")
        if upwards:
            integral = (scaled - eps).to_integral_value(rounding=ROUND_CEILING)
        else:
            integral = (scaled + eps).to_integral_value(rounding=ROUND_FLOOR)
        return integral * TICK_DEC


def dec_effective_price(raw_price: Any, side: int, cost: dict[str, Any], is_entry: bool) -> Decimal:
    """Compute adverse effective fill price in pure Decimal."""
    with localcontext() as ctx:
        ctx.prec = 50
        raw = D(raw_price, "raw_price")
        direction = Decimal(int(side) if is_entry else -int(side))
        spread_bps = D(cost.get("spread_bps", 0), "spread_bps")
        slip_bps = D(cost.get("slip_bps", cost.get("slippage_bps", 0)), "slip_bps")
        adverse_frac = (spread_bps / Decimal(2) + slip_bps) / Decimal(10_000)
        unrounded = raw * (Decimal(1) + direction * adverse_frac)
        return dec_tick(unrounded, upwards=direction > 0)


def dec_fee(price: Decimal, quantity: Decimal, cost: dict[str, Any]) -> Decimal:
    """Compute trading fee in pure Decimal."""
    with localcontext() as ctx:
        ctx.prec = 50
        fee_bps = D(cost.get("fee_bps", 0), "fee_bps")
        return price * quantity * fee_bps / Decimal(10_000)


def dec_ack_clock(fill_clock: int) -> int:
    """Compute causal order acknowledgment clock in UTC milliseconds."""
    return (int(fill_clock) // MINUTE_MS + 1) * MINUTE_MS + (
        MINUTE_MS if int(fill_clock) % MINUTE_MS else 0
    )


def dec_split_quantity(
    quantity: Any, eff_entry: Decimal, target1: Decimal, target2: Decimal
) -> tuple[Decimal, Decimal]:
    """Independently split initial quantity into (q1, q2) on the 0.001 BTC lot grid."""
    with localcontext() as ctx:
        ctx.prec = 50
        q = D(quantity, "quantity")
        nearest_lot_q = (q / LOT_DEC).to_integral_value(rounding=ROUND_HALF_EVEN) * LOT_DEC
        if q <= 0 or abs(q - nearest_lot_q) > Decimal("1e-12"):
            raise ValueError("Quantity is not a positive 0.001 lot multiple")
        q1 = (nearest_lot_q / Decimal(2) / LOT_DEC).to_integral_value(rounding=ROUND_FLOOR) * LOT_DEC
        q2 = q - q1
        if q1 <= 0 or q2 <= 0:
            raise ValueError("Zero partial tier quantity")
        min_leg_notional = min(
            q1 * target1, q2 * target2, q1 * eff_entry, q2 * eff_entry
        )
        if min_leg_notional < MIN_NOTIONAL_DEC:
            raise ValueError("Partial tier below 5.0 USDT minimum notional")
        return q1, q2


def dec_breakeven_stop(
    eff_entry: Decimal, orig_stop: Decimal, side: int, cost: dict[str, Any]
) -> Decimal:
    """Independently find smallest favorable raw tick with non-negative residual net after both fees."""
    with localcontext() as ctx:
        ctx.prec = 50
        s = int(side)
        raw = dec_tick(eff_entry, upwards=s > 0)
        unit = Decimal(1)
        for _ in range(100_000):
            eff_exit = dec_effective_price(raw, s, cost, is_entry=False)
            net_unit = (
                Decimal(s) * (eff_exit - eff_entry)
                - dec_fee(eff_entry, unit, cost)
                - dec_fee(eff_exit, unit, cost)
            )
            if net_unit >= Decimal("-1e-10"):
                return max(raw, orig_stop) if s > 0 else min(raw, orig_stop)
            raw = raw + Decimal(s) * TICK_DEC
        raise ValueError("Independent Decimal breakeven search did not converge")


def dec_size_admission(
    raw_entry: Any,
    atr_hour: Any,
    side: int,
    horizon_hours: int,
    cost: dict[str, Any],
    cash: Any,
) -> tuple[Decimal, dict[str, Decimal]]:
    """Independently compute R3/R1 1x budget and 5% reserve admission quantity in Decimal."""
    with localcontext() as ctx:
        ctx.prec = 50
        cash_d = D(cash, "cash")
        raw_d = D(raw_entry, "raw_entry")
        atr_d = D(atr_hour, "atr_hour")
        budget = Decimal("0.95") * min(cash_d, Decimal(1000))
        eff_entry = dec_effective_price(raw_d, side, cost, is_entry=True)
        worst_shock_raw = raw_d + Decimal("0.25") * atr_d
        worst_entry = max(eff_entry, dec_effective_price(worst_shock_raw, 1, cost, is_entry=True))
        fee_bps = D(cost["fee_bps"], "fee_bps")
        spread_bps = D(cost["spread_bps"], "spread_bps")
        slip_bps = D(cost.get("slip_bps", cost.get("slippage_bps", 0)), "slip_bps")
        fee_unit = worst_entry * fee_bps / Decimal(10_000)
        exit_reserve = (
            Decimal("1.10")
            * worst_entry
            * (fee_bps + Decimal("0.5") * spread_bps + slip_bps)
            / Decimal(10_000)
        )
        funding_reserve = (
            Decimal("1.10") * raw_d * Decimal(8) * Decimal(int(horizon_hours)) / Decimal(10_000)
        )
        per_unit = worst_entry + fee_unit + exit_reserve + funding_reserve
        lots = ((budget / per_unit / LOT_DEC) + Decimal("1e-10")).to_integral_value(
            rounding=ROUND_FLOOR
        )
        q = lots * LOT_DEC
        if q <= 0 or q * raw_d < MIN_NOTIONAL_DEC:
            raise ValueError("SIZE_OR_MIN_NOTIONAL")
        actual_entry_outlay = q * eff_entry + dec_fee(eff_entry, q, cost)
        if actual_entry_outlay > budget + Decimal("1e-8"):
            raise ValueError("Entry breaches 1x/reserve budget")
        return q, {
            "budget": budget,
            "per_unit": per_unit,
            "reserved_notional": q * worst_entry,
            "exit_cost_reserve": q * exit_reserve,
            "funding_reserve": q * funding_reserve,
            "actual_entry_outlay": actual_entry_outlay,
        }


def verify_and_audit_episode(
    trade: dict[str, Any],
    funding_lookup: dict[int, Decimal],
    mark_lookup: dict[int, tuple[Decimal, int, str]],
    *,
    last_bars_lookup: dict[int, tuple[Decimal, Decimal, Decimal, Decimal]] | None = None,
    curve_array: np.ndarray | None = None,
) -> dict[str, Any]:
    """Dual-Decimal independent verification of a single trade episode.

    Implementation A: Event-driven chronological Decimal recalculation from raw prices/rates.
    Implementation B: Double-entry stage balance-sheet and Mark liquidation equation checker.
    Returns a detailed receipt and list of any discovered witness discrepancies.
    """
    with localcontext() as ctx:
        ctx.prec = 50
        discrepancies: list[dict[str, Any]] = []
        cost_name = str(trade.get("cost", "STRESS"))
        cost = COST_MODELS_DEC[cost_name]
        side = int(trade["side"])
        side_d = Decimal(side)
        scheme = str(trade.get("scheme", "E0"))
        q = D(trade["quantity"], "quantity")
        raw_entry = D(trade["raw_entry"], "raw_entry")
        eff_entry = dec_effective_price(raw_entry, side, cost, is_entry=True)
        entry_at = int(trade["entry_at"])
        decision_at = int(trade["decision_at"])
        event_time = int(trade["event_time"])

        def record_defect(clock: int, kind: str, expected: Any, actual: Any, reason: str) -> None:
            discrepancies.append({
                "event_id": trade.get("event_id", "UNKNOWN"),
                "candidate": trade.get("candidate", "UNKNOWN"),
                "scheme": scheme,
                "cost": cost_name,
                "local_clock": int(clock),
                "defect_kind": kind,
                "expected": str(expected),
                "actual": str(actual),
                "reason": reason,
            })

        # 1. Causality of event -> decision -> entry clocks
        if (
            event_time % MINUTE_MS != 0
            or decision_at % MINUTE_MS != 0
            or entry_at % MINUTE_MS != 0
            or decision_at < event_time + MINUTE_MS
            or entry_at < decision_at + MINUTE_MS
        ):
            record_defect(
                entry_at,
                "CAUSALITY_CLOCK_ORDER",
                f"event({event_time}) + 60s <= decision({decision_at}) + 60s <= entry({entry_at})",
                f"{event_time},{decision_at},{entry_at}",
                "1m availability order violated at entry",
            )

        # 2. Entry effective tick & single entry fee check
        if abs(eff_entry - D(trade["effective_entry"])) > Decimal("1e-6"):
            record_defect(
                entry_at,
                "EFFECTIVE_ENTRY_TICK",
                eff_entry,
                trade["effective_entry"],
                "Effective entry tick rounding mismatch",
            )

        ind_fee_entry = dec_fee(eff_entry, q, cost)
        if abs(ind_fee_entry - D(trade["fee_entry"])) > Decimal("1e-8"):
            record_defect(
                entry_at,
                "ENTRY_FEE_ONCE",
                ind_fee_entry,
                trade["fee_entry"],
                "Entry fee mismatch",
            )

        # 3. Stop side & partial split check
        stop_d = D(trade["stop"], "stop")
        if side_d * (raw_entry - stop_d) <= 0 or side_d * (eff_entry - stop_d) <= 0:
            record_defect(
                entry_at,
                "OPPOSITE_SIDE_STOP",
                "side * (entry - stop) > 0",
                f"raw={raw_entry}, eff={eff_entry}, stop={stop_d}",
                "Stop is not on protective side of entry",
            )

        init_risk = side_d * (eff_entry - stop_d)
        target2 = D(trade["target"], "target")
        target1 = dec_tick(eff_entry + side_d * init_risk, upwards=side < 0)

        tiers = trade.get("tiers") or [
            {
                "quantity": trade["quantity"],
                "raw_exit": trade["raw_exit"],
                "effective_exit": trade["effective_exit"],
                "exit_at": trade["exit_at"],
                "exit_ack_at": trade["exit_ack_at"],
                "reason": trade["exit_reason"],
                "fee_exit": trade["fee_exit"],
                "fee_entry_alloc": trade["fee_entry"],
                "gross_usdt": trade["gross_usdt"],
                "execution_drag_usdt": (
                    D(trade["gross_usdt"])
                    - D(trade["net_usdt"])
                    - D(trade["fee_entry"])
                    - D(trade["fee_exit"])
                ),
                "net_usdt": trade["net_usdt"],
            }
        ]

        if scheme in {"E1", "E2"}:
            q1_exp, q2_exp = dec_split_quantity(q, eff_entry, target1, target2)
            if len(tiers) == 2 and (
                abs(D(tiers[0]["quantity"]) - q1_exp) > Decimal("1e-12")
                or abs(D(tiers[1]["quantity"]) - q2_exp) > Decimal("1e-12")
            ):
                record_defect(
                    entry_at,
                    "PARTIAL_LOT_SPLIT",
                    f"({q1_exp}, {q2_exp})",
                    f"({tiers[0]['quantity']}, {tiers[1]['quantity']})",
                    "Partial tier split mismatch",
                )

        # 4. Tier-by-tier price P&L, execution drag, exit fee, and ACK causality
        ind_gross = Decimal(0)
        ind_drag = Decimal(0)
        ind_fee_exit_sum = Decimal(0)
        ind_fee_entry_alloc_sum = Decimal(0)
        tier_proofs: list[dict[str, Any]] = []

        for idx, tier in enumerate(tiers):
            t_qty = D(tier["quantity"], f"tier[{idx}].quantity")
            t_raw_exit = D(tier["raw_exit"], f"tier[{idx}].raw_exit")
            t_eff_exit = dec_effective_price(t_raw_exit, side, cost, is_entry=False)
            t_fee_exit = dec_fee(t_eff_exit, t_qty, cost)
            t_fee_entry_alloc = dec_fee(eff_entry, t_qty, cost)
            t_gross = side_d * (t_raw_exit - raw_entry) * t_qty
            t_drag = side_d * (eff_entry - raw_entry + t_raw_exit - t_eff_exit) * t_qty
            t_net = t_gross - t_drag - t_fee_entry_alloc - t_fee_exit
            t_exit_at = int(tier["exit_at"])
            t_ack_at = int(tier["exit_ack_at"])
            expected_ack = dec_ack_clock(t_exit_at)

            if abs(t_eff_exit - D(tier["effective_exit"])) > Decimal("1e-6"):
                record_defect(
                    t_exit_at,
                    "TIER_EFFECTIVE_EXIT",
                    t_eff_exit,
                    tier["effective_exit"],
                    f"Tier {idx} effective exit mismatch",
                )
            if abs(t_fee_exit - D(tier["fee_exit"])) > Decimal("1e-8"):
                record_defect(
                    t_exit_at,
                    "TIER_EXIT_FEE",
                    t_fee_exit,
                    tier["fee_exit"],
                    f"Tier {idx} exit fee mismatch",
                )
            if t_ack_at != expected_ack or t_ack_at <= t_exit_at:
                record_defect(
                    t_exit_at,
                    "ACK_CAUSALITY",
                    expected_ack,
                    t_ack_at,
                    f"Tier {idx} ACK clock not causal",
                )

            ind_gross += t_gross
            ind_drag += t_drag
            ind_fee_exit_sum += t_fee_exit
            ind_fee_entry_alloc_sum += t_fee_entry_alloc
            tier_proofs.append({
                "tier_index": idx,
                "reason": str(tier["reason"]),
                "quantity": str(t_qty),
                "raw_exit": str(t_raw_exit),
                "independent_effective_exit": str(t_eff_exit),
                "independent_fee_exit": str(t_fee_exit),
                "independent_gross_usdt": str(t_gross),
                "independent_drag_usdt": str(t_drag),
                "independent_net_usdt": str(t_net),
                "exit_at": t_exit_at,
                "exit_ack_at": t_ack_at,
            })

        # Verify TP1 + TP2 intrabar collision rule (cannot both infer intraminute fills in same bar)
        if len(tiers) == 2:
            r0, r1 = str(tiers[0]["reason"]), str(tiers[1]["reason"])
            if r0 == "TP1" and r1 == "TP2" and int(tiers[0]["exit_at"]) == int(tiers[1]["exit_at"]):
                record_defect(
                    int(tiers[0]["exit_at"]),
                    "INTRABAR_TP1_TP2_COLLISION",
                    "exit_at(TP1) < exit_at(TP2)",
                    f"{tiers[0]['exit_at']} == {tiers[1]['exit_at']}",
                    "TP1 and TP2 inferred on same intraminute bar without opening gap",
                )

        if abs(sum((D(x["quantity"]) for x in tiers), Decimal(0)) - q) > Decimal("1e-12"):
            record_defect(
                int(trade["exit_at"]),
                "QUANTITY_CONSERVATION",
                q,
                sum((D(x["quantity"]) for x in tiers), Decimal(0)),
                "Sum of tier quantities does not equal initial quantity",
            )

        if abs(ind_fee_entry_alloc_sum - ind_fee_entry) > Decimal("1e-9"):
            record_defect(
                entry_at,
                "ENTRY_FEE_ALLOCATION_SUM",
                ind_fee_entry,
                ind_fee_entry_alloc_sum,
                "Allocated tier entry fees do not sum to single entry fee",
            )

        if abs(ind_fee_exit_sum - D(trade["fee_exit"])) > Decimal("1e-8"):
            record_defect(
                int(trade["exit_at"]),
                "SUM_OF_TIER_EXIT_FEES",
                ind_fee_exit_sum,
                trade["fee_exit"],
                "Sum of tier exit fees disagrees with trade fee_exit",
            )

        # Optional independent 1m Last bar path check if last_bars_lookup is provided
        last_bar_checks: list[dict[str, Any]] = []
        if last_bars_lookup is not None:
            if entry_at not in last_bars_lookup:
                record_defect(entry_at, "MISSING_ENTRY_LAST_BAR", "present", "missing", "Missing entry Last bar")
            else:
                op_e, _, _, _ = last_bars_lookup[entry_at]
                if abs(op_e - raw_entry) > Decimal("1e-8"):
                    record_defect(entry_at, "RAW_ENTRY_OPEN_MISMATCH", op_e, raw_entry, "Entry open price mismatch")
                last_bar_checks.append({"clock": entry_at, "check": "ENTRY_OPEN_MATCH", "raw_open": str(op_e)})

        # 5. Independent Funding calculation on remaining inventory at latest completed 1m Mark close
        final_exit_at = max(int(x["exit_at"]) for x in tiers)
        ind_funding_total = Decimal(0)
        ind_settlements: list[dict[str, Any]] = []

        for settle_at in sorted(k for k in funding_lookup if entry_at <= k < final_exit_at):
            rate = funding_lookup[settle_at]
            exited_by_settle = sum(
                (D(x["quantity"]) for x in tiers if int(x["exit_at"]) <= settle_at),
                Decimal(0),
            )
            open_qty = q - exited_by_settle
            if open_qty < 0:
                record_defect(
                    settle_at,
                    "NEGATIVE_RESIDUAL_INVENTORY",
                    ">=0",
                    open_qty,
                    "Negative remaining inventory at funding settlement",
                )
            if open_qty == 0:
                continue
            mark_open_stamp = ((settle_at - (MINUTE_MS - 1)) // MINUTE_MS) * MINUTE_MS
            if mark_open_stamp not in mark_lookup:
                record_defect(
                    settle_at,
                    "MISSING_COMPLETED_MARK_AT_SETTLEMENT",
                    mark_open_stamp,
                    "MISSING",
                    "Required completed 1m Mark bar missing at funding settlement",
                )
                continue
            mark_close_price, mark_close_time, mark_origin = mark_lookup[mark_open_stamp]
            if not (mark_close_time <= settle_at and settle_at - mark_close_time < MINUTE_MS):
                record_defect(
                    settle_at,
                    "MARK_ASOF_CAUSALITY",
                    f"{settle_at - MINUTE_MS} < close_time <= {settle_at}",
                    mark_close_time,
                    "Settlement Mark close timestamp violates 1m causality",
                )
            bill = -side_d * open_qty * mark_close_price * rate
            ind_funding_total += bill
            ind_settlements.append({
                "settlement_at": settle_at,
                "remaining_quantity": str(open_qty),
                "rate_fraction": str(rate),
                "asof_mark_open_at": mark_open_stamp,
                "asof_mark_close_at": mark_close_time,
                "asof_mark_close": str(mark_close_price),
                "mark_source": mark_origin,
                "signed_cash_usdt": str(bill),
            })

        committed_settlements = trade.get("funding_settlements", [])
        if len(ind_settlements) != len(committed_settlements):
            record_defect(
                final_exit_at,
                "FUNDING_SETTLEMENT_COUNT",
                len(ind_settlements),
                len(committed_settlements),
                "Funding settlement count mismatch",
            )
        else:
            for ind_s, com_s in zip(ind_settlements, committed_settlements, strict=True):
                if int(ind_s["settlement_at"]) != int(com_s["settlement_at"]):
                    record_defect(
                        int(ind_s["settlement_at"]),
                        "FUNDING_CLOCK_MISMATCH",
                        ind_s["settlement_at"],
                        com_s["settlement_at"],
                        "Funding settlement timestamp mismatch",
                    )
                if abs(D(ind_s["remaining_quantity"]) - D(com_s["quantity"])) > Decimal("1e-12"):
                    record_defect(
                        int(ind_s["settlement_at"]),
                        "RESIDUAL_FUNDING_QUANTITY",
                        ind_s["remaining_quantity"],
                        com_s["quantity"],
                        "Remaining quantity at funding settlement mismatch",
                    )
                if abs(D(ind_s["signed_cash_usdt"]) - D(com_s["signed_cash_usdt"])) > Decimal("1e-8"):
                    record_defect(
                        int(ind_s["settlement_at"]),
                        "FUNDING_BILL_CASH",
                        ind_s["signed_cash_usdt"],
                        com_s["signed_cash_usdt"],
                        "Signed funding bill mismatch",
                    )

        ind_net_before_funding = ind_gross - ind_drag - ind_fee_entry - ind_fee_exit_sum
        ind_net_after_funding = ind_net_before_funding + ind_funding_total
        notional = raw_entry * q
        ind_net_after_funding_bps = Decimal(10_000) * ind_net_after_funding / notional

        if abs(ind_net_before_funding - D(trade["net_usdt"])) > Decimal("1e-7"):
            record_defect(
                final_exit_at,
                "NET_BEFORE_FUNDING",
                ind_net_before_funding,
                trade["net_usdt"],
                "Net USDT before funding mismatch",
            )
        if abs(ind_funding_total - D(trade.get("funding_cash_usdt", 0))) > Decimal("1e-8"):
            record_defect(
                final_exit_at,
                "TOTAL_FUNDING_CASH",
                ind_funding_total,
                trade.get("funding_cash_usdt", 0),
                "Total signed funding cash mismatch",
            )
        if abs(ind_net_after_funding - D(trade.get("net_after_funding_usdt", trade["net_usdt"]))) > Decimal("1e-7"):
            record_defect(
                final_exit_at,
                "NET_AFTER_FUNDING",
                ind_net_after_funding,
                trade.get("net_after_funding_usdt"),
                "Net USDT after funding mismatch",
            )

        # 6. Implementation B: Double-entry stage balance-sheet and ACK spendability check
        journal = trade.get("journal", [])
        if journal:
            journal_sum = sum((D(j["cash_delta"]) for j in journal), Decimal(0))
            if abs(journal_sum - ind_net_after_funding) > Decimal("1e-7"):
                record_defect(
                    final_exit_at,
                    "JOURNAL_CASH_CONSERVATION",
                    ind_net_after_funding,
                    journal_sum,
                    "Cash journal deltas do not sum to net_after_funding_usdt",
                )
            for j in journal:
                if j["kind"] == "EXIT_PNL_ACK" and not any(
                    int(j["timestamp"]) == int(x["exit_ack_at"]) for x in tiers
                ):
                    record_defect(
                        int(j["timestamp"]),
                        "PREMATURE_CASH_ACK",
                        "timestamp in tier.exit_ack_at",
                        j["timestamp"],
                        "EXIT_PNL_ACK recorded before or outside causal tier ACK clock",
                    )

        cash_before = D(trade.get("cash_before_entry", "1000"))
        stage_clocks = sorted({
            entry_at - 1,
            entry_at,
            *(int(x["exit_at"]) for x in tiers),
            *(int(x["exit_ack_at"]) for x in tiers),
            *(int(x["settlement_at"]) for x in ind_settlements),
        })

        def balance_sheet_at(at_clock: int, mark_p: Decimal) -> dict[str, Decimal]:
            if at_clock < entry_at:
                return {
                    "available_cash": cash_before,
                    "pending_ack_receivable": Decimal(0),
                    "remaining_quantity": Decimal(0),
                    "unrealized_liability_or_pnl": Decimal(0),
                    "mark_liquidation_equity": cash_before,
                }
            avail_cash = cash_before - ind_fee_entry
            rem_q = q
            pending_rec = Decimal(0)
            for x in tiers:
                x_qty = D(x["quantity"])
                x_eff = dec_effective_price(x["raw_exit"], side, cost, is_entry=False)
                x_pnl = side_d * (x_eff - eff_entry) * x_qty
                x_fee = dec_fee(x_eff, x_qty, cost)
                if int(x["exit_at"]) <= at_clock:
                    rem_q -= x_qty
                    avail_cash -= x_fee
                    if int(x["exit_ack_at"]) <= at_clock:
                        avail_cash += x_pnl
                    else:
                        pending_rec += x_pnl
            avail_cash += sum(
                (D(b["signed_cash_usdt"]) for b in ind_settlements if int(b["settlement_at"]) <= at_clock),
                Decimal(0),
            )
            rem_q = max(Decimal(0), rem_q)
            if rem_q > 0:
                liq_p = dec_effective_price(mark_p, side, cost, is_entry=False)
                unrealized = side_d * (liq_p - eff_entry) * rem_q - dec_fee(liq_p, rem_q, cost)
            else:
                unrealized = Decimal(0)
            eq = avail_cash + pending_rec + unrealized
            return {
                "available_cash": avail_cash,
                "pending_ack_receivable": pending_rec,
                "remaining_quantity": rem_q,
                "unrealized_liability_or_pnl": unrealized,
                "mark_liquidation_equity": eq,
            }

        stage_checks: list[dict[str, Any]] = []
        for clk in stage_clocks:
            asof_stamp = ((max(clk, entry_at) - (MINUTE_MS - 1)) // MINUTE_MS) * MINUTE_MS
            mp = mark_lookup[asof_stamp][0] if asof_stamp in mark_lookup else raw_entry
            bs = balance_sheet_at(clk, mp)
            if journal and clk >= entry_at:
                j_cash = cash_before + sum(
                    (D(j["cash_delta"]) for j in journal if int(j["timestamp"]) <= clk),
                    Decimal(0),
                )
                if abs(bs["available_cash"] - j_cash) > Decimal("1e-7"):
                    record_defect(
                        clk,
                        "STAGE_CASH_VS_JOURNAL",
                        bs["available_cash"],
                        j_cash,
                        "Double-entry available cash diverges from journal cumulative sum",
                    )

            minute_close = (clk // MINUTE_MS) * MINUTE_MS + (MINUTE_MS - 1)
            close_open_stamp = minute_close - (MINUTE_MS - 1)
            curve_eq_str = None
            ind_close_eq_str = None
            if clk >= entry_at and close_open_stamp in mark_lookup:
                mpc = mark_lookup[close_open_stamp][0]
                bs_close = balance_sheet_at(minute_close, mpc)
                ind_close_eq_str = str(bs_close["mark_liquidation_equity"])
                if curve_array is not None:
                    ix = int(np.searchsorted(curve_array[:, 0], minute_close))
                    if ix < len(curve_array) and int(curve_array[ix, 0]) == minute_close:
                        c_val = D(curve_array[ix, 1], "curve_equity")
                        curve_eq_str = str(c_val)
                        if abs(bs_close["mark_liquidation_equity"] - c_val) > Decimal("1e-6"):
                            record_defect(
                                minute_close,
                                "MARK_CURVE_EQUITY_MISMATCH",
                                bs_close["mark_liquidation_equity"],
                                c_val,
                                "Independent minute-close Mark liquidation equity diverges from account curve",
                            )

            stage_checks.append({
                "stage_clock": clk,
                "available_cash": str(bs["available_cash"]),
                "pending_ack_receivable": str(bs["pending_ack_receivable"]),
                "remaining_quantity": str(bs["remaining_quantity"]),
                "unrealized_liability_or_pnl": str(bs["unrealized_liability_or_pnl"]),
                "mark_liquidation_equity": str(bs["mark_liquidation_equity"]),
                "minute_close_clock": minute_close,
                "independent_close_equity": ind_close_eq_str,
                "committed_curve_equity": curve_eq_str,
                "status": "PASS" if not discrepancies else "FAIL",
            })

        if "cash_after_ack" in trade:
            final_ack = max(int(x["exit_ack_at"]) for x in tiers)
            bs_final = balance_sheet_at(final_ack, raw_entry)
            if abs(bs_final["available_cash"] - D(trade["cash_after_ack"])) > Decimal("1e-7"):
                record_defect(
                    final_ack,
                    "CLOSING_ACK_CASH_MISMATCH",
                    bs_final["available_cash"],
                    trade["cash_after_ack"],
                    "Closing cash after ACK disagrees with independent journal",
                )

        return {
            "candidate": trade.get("candidate", "UNKNOWN"),
            "scheme": scheme,
            "cost": cost_name,
            "event_id": trade.get("event_id", "UNKNOWN"),
            "side": side,
            "year": datetime.fromtimestamp(entry_at / 1000, UTC).year,
            "entry_at": entry_at,
            "exit_at": final_exit_at,
            "exit_ack_at": max(int(x["exit_ack_at"]) for x in tiers),
            "exit_reason": str(trade.get("exit_reason", tiers[-1]["reason"])),
            "quantity": str(q),
            "independent_effective_entry": str(eff_entry),
            "independent_fee_entry": str(ind_fee_entry),
            "independent_fee_exit": str(ind_fee_exit_sum),
            "independent_gross_usdt": str(ind_gross),
            "independent_drag_usdt": str(ind_drag),
            "independent_net_before_funding_usdt": str(ind_net_before_funding),
            "independent_funding_cash_usdt": str(ind_funding_total),
            "independent_net_after_funding_usdt": str(ind_net_after_funding),
            "independent_net_after_funding_bps": str(ind_net_after_funding_bps),
            "tier_proofs": tier_proofs,
            "funding_settlements": ind_settlements,
            "stage_checks": stage_checks,
            "last_bar_checks": last_bar_checks,
            "discrepancies": discrepancies,
            "status": "PASS" if not discrepancies else "DEFECT",
        }


def read_zip_csv_member(zip_path: Path, expected_sha256: str) -> tuple[str, str]:
    """Read and authenticate a single-member ZIP archive using stdlib only."""
    if zip_path.is_symlink() or zip_path.parent.is_symlink():
        raise ValueError(f"Symlinked archive forbidden: {zip_path}")
    raw = zip_path.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha256:
        raise ValueError(
            f"Independent archive SHA mismatch for {zip_path.name}: expected {expected_sha256}, got {actual_sha}"
        )
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        if len(names) != 1:
            raise ValueError(f"Expected 1 member in {zip_path.name}, found {len(names)}")
        text = zf.read(names[0]).decode("utf-8-sig")
    return text, actual_sha


def audit_real_r1_episodes(
    r1_evidence_dir: Path,
    r3_cache_dir: Path,
    r31_cache_dir: Path,
    r1_cache_dir: Path,
) -> dict[str, Any]:
    """Forensically reconstruct and audit genuine R1 episodes from authenticated CSV/ZIP caches."""
    import json

    source_identity = json.loads((r1_evidence_dir / "SOURCE_IDENTITY.json").read_text())
    ledger_manifest = json.loads((r1_evidence_dir / "COMMITTED_LEDGER_MANIFEST.json").read_text())

    # 1. Authenticate and parse all 36 monthly funding archives (3,285 events)
    funding_lookup: dict[int, Decimal] = {}
    funding_archive_Hashes: dict[str, str] = {}
    for ref in source_identity["successful_sources"]:
        if ref["kind"] != "funding":
            continue
        zip_name = f"funding-BTCUSDT-fundingRate-{ref['year']}-{ref['month']:02d}.zip"
        text, sha = read_zip_csv_member(r3_cache_dir / zip_name, ref["zip_sha256"])
        funding_archive_Hashes[zip_name] = sha
        for row in csv.DictReader(io.StringIO(text)):
            at = int(row["calc_time"])
            if at in funding_lookup:
                raise ValueError(f"Duplicate funding timestamp in source: {at}")
            funding_lookup[at] = D(row["last_funding_rate"], "last_funding_rate")
    if len(funding_lookup) != 3285:
        raise ValueError(f"Expected 3285 funding events, got {len(funding_lookup)}")

    # 2. Load all 20 committed order ledgers (890 total trade episodes)
    all_order_trades: list[dict[str, Any]] = []
    for item in ledger_manifest:
        cpath = Path(item["committed_path"])
        if not cpath.name.endswith("_orders.jsonl"):
            continue
        full_path = r1_evidence_dir.parents[3] / cpath
        raw_bytes = full_path.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != item["sha256"]:
            raise ValueError(f"Committed order ledger SHA mismatch: {cpath}")
        parts = cpath.stem.split("_")
        # Format: <CANDIDATE>_<COST>_<SCHEME>_orders
        scheme = parts[-2]
        cost_name = parts[-3]
        cand_id = "_".join(parts[:-3])
        for line in raw_bytes.decode("utf-8").splitlines():
            t = json.loads(line)
            t["cost"] = cost_name
            t["scheme"] = scheme
            t["candidate"] = cand_id
            t["ledger_sha256"] = item["sha256"]
            all_order_trades.append(t)

    # 3. Verify original R1 24 partial+funding cohort and nearest TP1-to-settlement distance
    partial_funded = [
        t
        for t in sorted(
            all_order_trades,
            key=lambda x: (
                int(x["entry_at"]),
                str(x["candidate"]),
                str(x["scheme"]),
                0 if x["cost"] == "STRESS" else 1,
            ),
        )
        if x_S(t) and t["scheme"] in {"E1", "E2"}
    ]

    nearest_tp1: tuple[tuple[int, int, str, int, str, str], dict[str, Any]] | None = None
    post_tp1_residual_episodes_all = 0
    for t in partial_funded:
        for tier in t.get("tiers", []):
            if str(tier["reason"]).startswith("TP1"):
                tp1_at = int(tier["exit_at"])
                for f_at in funding_lookup:
                    dist = abs(f_at - tp1_at)
                    cand_tuple = (dist, f_at, str(t["event_id"]), tp1_at, str(t["scheme"]), str(t["cost"]))
                    if nearest_tp1 is None or cand_tuple < nearest_tp1[0]:
                        nearest_tp1 = (cand_tuple, t)
                if any(
                    int(b["settlement_at"]) >= tp1_at and D(b["quantity"]) < D(t["quantity"])
                    for b in t.get("funding_settlements", [])
                ):
                    post_tp1_residual_episodes_all += 1

    # Reconstruct the exact 24-episode cohort from Exit R1 audit.py plus H1/H2/E0 coverage
    r1_24_cohort: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    groups_seen: set[tuple[str, int, int, str]] = set()
    for t in partial_funded:
        yr = datetime.fromtimestamp(int(t["entry_at"]) / 1000, UTC).year
        grp = (str(t["candidate"]), int(t["side"]), yr, str(t["cost"]))
        if grp not in groups_seen:
            r1_24_cohort[(str(t["candidate"]), str(t["event_id"]), str(t["scheme"]), str(t["cost"]))] = t
            groups_seen.add(grp)
    for sign in (-1, 1):
        t_match = next(
            (
                t
                for t in partial_funded
                if any(sign * D(x["source_rate_fraction"]) > 0 for x in t["funding_settlements"])
            ),
            None,
        )
        if t_match is not None:
            r1_24_cohort[
                (
                    str(t_match["candidate"]),
                    str(t_match["event_id"]),
                    str(t_match["scheme"]),
                    str(t_match["cost"]),
                )
            ] = t_match
    if nearest_tp1 is not None:
        t_near = nearest_tp1[1]
        r1_24_cohort[
            (str(t_near["candidate"]), str(t_near["event_id"]), str(t_near["scheme"]), str(t_near["cost"]))
        ] = t_near

    r1_24_post_tp1_count = sum(
        any(
            int(b["settlement_at"])
            >= min(int(x["exit_at"]) for x in t["tiers"] if str(x["reason"]).startswith("TP1"))
            and D(b["quantity"]) < D(t["quantity"])
            for b in t["funding_settlements"]
        )
        for t in r1_24_cohort.values()
    )

    # Expand forensic cohort to >= 40 genuine episodes covering E1, E2, H1, H2, E0, 2021/2022/2023, STRESS/BASE, LONG/SHORT
    forensic_selected: dict[tuple[str, str, str, str], dict[str, Any]] = dict(r1_24_cohort)
    for scheme in ("H1", "H2", "E0", "E1", "E2"):
        for cost_name in ("STRESS", "BASE"):
            for cand_id in (
                "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
                "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
            ):
                for yr in (2021, 2022, 2023):
                    for side in (1, -1):
                        match = next(
                            (
                                t
                                for t in all_order_trades
                                if t["scheme"] == scheme
                                and t["cost"] == cost_name
                                and t["candidate"] == cand_id
                                and int(t["side"]) == side
                                and datetime.fromtimestamp(int(t["entry_at"]) / 1000, UTC).year == yr
                            ),
                            None,
                        )
                        if match is not None and len(forensic_selected) < 48:
                            key = (
                                str(match["candidate"]),
                                str(match["event_id"]),
                                str(match["scheme"]),
                                str(match["cost"]),
                            )
                            forensic_selected.setdefault(key, match)

    # 4. Collect all needed 1m Mark and Last timestamps across ALL 890 trades
    needed_mark_stamps: set[int] = set()
    needed_last_stamps: set[int] = set()
    for t in all_order_trades:
        entry_at = int(t["entry_at"])
        needed_last_stamps.add(entry_at)
        tiers = t.get("tiers") or [{"exit_at": t["exit_at"], "exit_ack_at": t["exit_ack_at"]}]
        stages = {
            entry_at,
            *(int(x["exit_at"]) for x in tiers),
            *(int(x["exit_ack_at"]) for x in tiers),
            *(f_at for f_at in funding_lookup if entry_at <= f_at < int(t["exit_at"])),
        }
        for clk in stages:
            needed_mark_stamps.add(((clk - (MINUTE_MS - 1)) // MINUTE_MS) * MINUTE_MS)
            needed_mark_stamps.add((clk // MINUTE_MS) * MINUTE_MS)

    mark_lookup: dict[int, tuple[Decimal, int, str]] = {}
    for ref in source_identity["successful_sources"]:
        if ref["kind"] != "mark":
            continue
        y, m = int(ref["year"]), int(ref["month"])
        targets = {
            at
            for at in needed_mark_stamps
            if (datetime.fromtimestamp(at / 1000, UTC).year, datetime.fromtimestamp(at / 1000, UTC).month)
            == (y, m)
        }
        if not targets:
            continue
        zip_name = f"mark-BTCUSDT-1m-{y}-{m:02d}.zip"
        text, _ = read_zip_csv_member(r3_cache_dir / zip_name, ref["zip_sha256"])
        for row in csv.reader(io.StringIO(text)):
            if not row or row[0] == "open_time":
                continue
            at = int(row[0])
            if at in targets:
                mark_lookup[at] = (D(row[4], "mark_close"), int(row[6]), "MONTHLY_AUTHORITY")

    for day_rec in source_identity.get("daily_receipts", []):
        d_str = day_rec["day"]
        d_start = int(datetime.strptime(d_str, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
        if not any(d_start <= at < d_start + 86_400_000 and at not in mark_lookup for at in needed_mark_stamps):
            continue
        zip_path = r31_cache_dir / d_str / f"BTCUSDT-1m-{d_str}.zip"
        text, _ = read_zip_csv_member(zip_path, day_rec["daily_parse"]["zip_sha256"])
        for row in csv.reader(io.StringIO(text)):
            if not row or row[0] == "open_time":
                continue
            at = int(row[0])
            if at in needed_mark_stamps:
                if at in mark_lookup:
                    raise ValueError(f"Overlapping daily Mark repair at {at}")
                mark_lookup[at] = (D(row[4], "mark_close"), int(row[6]), "DAILY_SHA_AUTHENTICATED")

    if not needed_mark_stamps <= set(mark_lookup):
        missing = sorted(needed_mark_stamps - set(mark_lookup))[:5]
        raise ValueError(f"Required Mark timestamps unavailable in authenticated caches: {missing}")

    last_bars_lookup: dict[int, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
    for ref in source_identity["successful_sources"]:
        if ref["kind"] != "last":
            continue
        y, m = int(ref["year"]), int(ref["month"])
        targets = {
            at
            for at in needed_last_stamps
            if (datetime.fromtimestamp(at / 1000, UTC).year, datetime.fromtimestamp(at / 1000, UTC).month)
            == (y, m)
        }
        if not targets:
            continue
        zip_name = f"last-BTCUSDT-1m-{y}-{m:02d}.zip"
        text, _ = read_zip_csv_member(r3_cache_dir / zip_name, ref["zip_sha256"])
        for row in csv.reader(io.StringIO(text)):
            if not row or not row[0].isdigit():
                continue
            at = int(row[0])
            if at in targets:
                last_bars_lookup[at] = (
                    D(row[1], "open"),
                    D(row[2], "high"),
                    D(row[3], "low"),
                    D(row[4], "close"),
                )

    # 5. Load available minute Mark curves (.npz) for cross-checking stage minute-close equity
    curves_by_cell: dict[tuple[str, str, str], np.ndarray] = {}
    for cand_id in (
        "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H",
    ):
        for cost_name in ("STRESS", "BASE"):
            e0_npz = r31_cache_dir / f"{cand_id}_{cost_name}_equity.npz"
            if e0_npz.is_file() and not e0_npz.is_symlink():
                with np.load(e0_npz) as arch:
                    curves_by_cell[(cand_id, cost_name, "E0")] = arch["funded"]
            for scheme in ("H1", "H2", "E1", "E2"):
                s_npz = r1_cache_dir / f"{cand_id}_{cost_name}_{scheme}_Mark_curve.npz"
                if s_npz.is_file() and not s_npz.is_symlink():
                    with np.load(s_npz) as arch:
                        curves_by_cell[(cand_id, cost_name, scheme)] = arch["curve"]

    # 6. Audit all 48 selected forensic episodes in full detail AND all 890 order ledger rows
    detailed_episodes: list[dict[str, Any]] = []
    all_defects: list[dict[str, Any]] = []

    for key, trade in forensic_selected.items():
        cand_id, _, scheme, cost_name = key
        curve_arr = curves_by_cell.get((cand_id, cost_name, scheme))
        rec = verify_and_audit_episode(
            trade,
            funding_lookup,
            mark_lookup,
            last_bars_lookup=last_bars_lookup,
            curve_array=curve_arr,
        )
        detailed_episodes.append(rec)
        all_defects.extend(rec["discrepancies"])

    ledger_wide_checked = 0
    for trade in all_order_trades:
        cand_id = str(trade["candidate"])
        cost_name = str(trade["cost"])
        scheme = str(trade["scheme"])
        curve_arr = curves_by_cell.get((cand_id, cost_name, scheme))
        rec = verify_and_audit_episode(
            trade,
            funding_lookup,
            mark_lookup,
            last_bars_lookup=last_bars_lookup,
            curve_array=curve_arr,
        )
        ledger_wide_checked += 1
        for d in rec["discrepancies"]:
            if d not in all_defects:
                all_defects.append(d)

    return {
        "status": "PASS" if not all_defects else "DEFECT_FOUND",
        "method": "Dual-Decimal independent stdlib CSV/ZIP/Decimal recalculation and stage balance-sheet check; zero production economics calls",
        "forensic_episodes_audited_n": len(detailed_episodes),
        "ledger_wide_episodes_audited_n": ledger_wide_checked,
        "forensic_per_cost_n": {
            c: sum(e["cost"] == c for e in detailed_episodes) for c in ("STRESS", "BASE")
        },
        "forensic_per_scheme_n": {
            s: sum(e["scheme"] == s for e in detailed_episodes) for s in ("E0", "H1", "H2", "E1", "E2")
        },
        "forensic_years_covered": sorted({e["year"] for e in detailed_episodes}),
        "forensic_sides_covered": sorted({e["side"] for e in detailed_episodes}),
        "r1_original_partial_funded_cohort_n": len(r1_24_cohort),
        "r1_original_post_tp1_residual_funding_n": r1_24_post_tp1_count,
        "all_order_ledgers_post_tp1_residual_funding_n": post_tp1_residual_episodes_all,
        "funding_events_verified_n": len(funding_lookup),
        "closest_actual_tp1_to_settlement": {
            "distance_ms": nearest_tp1[0][0],
            "settlement_at": nearest_tp1[0][1],
            "event_id": nearest_tp1[0][2],
            "tp1_exit_at": nearest_tp1[0][3],
            "scheme": nearest_tp1[0][4],
            "cost": nearest_tp1[0][5],
            "within_60sec_supported": nearest_tp1[0][0] <= 60_000,
        }
        if nearest_tp1
        else None,
        "defect_witnesses": all_defects,
        "episodes": detailed_episodes,
    }


def x_S(trade: dict[str, Any]) -> bool:
    """Return True if trade has both a TP1 tier fill and at least one funding settlement."""
    return bool(trade.get("funding_settlements")) and any(
        str(x.get("reason", "")).startswith("TP1") for x in trade.get("tiers", [])
    )

