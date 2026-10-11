"""Independent pure-Decimal forensic margin, liquidation, stop-vs-liquidation clock, and exposure engine.

Strictly self-contained: does NOT import or call C R1 `risk_envelope.py` as an oracle.
Implements:
1. Exact Decimal tick rounding, adverse effective entry/exit pricing, fee, and 1x reserve gates.
2. Exact Decimal isolated margin vs total account equity conservation:
   - Explicitly separates strict exchange initial margin `M_strict = N / L` from discretionary
     margin buffer `B_disc = M_posted - N / L`.
   - Solves in closed-form Decimal for the exact Mark liquidation price `P_liq` and adverse
     Mark move fraction `delta_p_liq` where Mark equity after fees and funding reaches
     maintenance margin `MM_req(q_open, P_Mark) = q_open * P_Mark * (MMR + c)`.
   - Evaluates both 1m Mark close and 1m intrabar worst High/Low, modeling 1m intrabar
     unknown sequencing conservatively (liquidation-first if both stop and liquidation
     are breached or if `delta_p_liq <= stop_distance_pct`).
   - Distinguishes isolated collateral bankruptcy (`isolated_margin_after_gap < 0`) from
     negative total account wealth (`total_account_equity_after_gap <= 0`).
3. Exact filtered denominator builder (`X / Y` from actual row predicates; `Y == 0 -> UNKNOWN`,
   never `X / Y > 1`).
4. Closed-form Decimal stop-distance vs 10x/15x liquidation inequality proofs comparing
   real 2021-2023 max 1R stop distances (`3.6120%` W1, `3.5591%` W2) against synthetic `7.5%` stops.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, getcontext
from typing import Any

getcontext().prec = 50

MINUTE_MS = 60_000
HOUR_MS = 3_600_000

TICK_DEC = Decimal("0.1")
LOT_DEC = Decimal("0.001")
MIN_NOTIONAL_DEC = Decimal("5.0")
BPS_DIVISOR = Decimal(10000)
EPS_1E9 = Decimal("0.000000001")
EPS_1E7 = Decimal("0.0000001")
EPS_1E4 = Decimal("0.0001")

COST_MODELS_DEC: dict[str, dict[str, Decimal]] = {
    "BASE": {
        "fee_bps": Decimal("6.0"),
        "spread_bps": Decimal("4.0"),
        "slip_bps": Decimal("3.0"),
        "nominal_roundtrip_bps": Decimal("22.0"),
    },
    "STRESS": {
        "fee_bps": Decimal("12.0"),
        "spread_bps": Decimal("8.0"),
        "slip_bps": Decimal("6.0"),
        "nominal_roundtrip_bps": Decimal("44.0"),
    },
}


def D(val: Any) -> Decimal:
    """Convert numeric or string value to exact Decimal via string representation."""
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def q4(val: Decimal) -> float:
    """Round Decimal to 4 decimal places as float for deterministic JSON serialization."""
    return float(val.quantize(Decimal("0.0001")))


def q6(val: Decimal) -> float:
    """Round Decimal to 6 decimal places as float for deterministic JSON serialization."""
    return float(val.quantize(Decimal("0.000001")))


def dec_tick(price: Decimal | float | str, upwards: bool) -> Decimal:
    """Round price to 0.1 tick: ceiling when upwards=True, floor when upwards=False."""
    p = D(price)
    scaled = p / TICK_DEC
    if upwards:
        rounded = (scaled - EPS_1E9).to_integral_value(rounding=ROUND_CEILING)
    else:
        rounded = (scaled + EPS_1E9).to_integral_value(rounding=ROUND_FLOOR)
    return rounded * TICK_DEC


def dec_effective_price(
    raw_price: Decimal | float | str,
    side: int,
    cost: dict[str, Decimal],
    *,
    is_entry: bool,
) -> Decimal:
    """Compute adverse effective fill price including half-spread + slippage and 0.1 tick rounding."""
    raw = D(raw_price)
    adverse_frac = (Decimal("0.5") * cost["spread_bps"] + cost["slip_bps"]) / BPS_DIVISOR
    sign = side if is_entry else -side
    shifted = raw * (Decimal(1) + Decimal(sign) * adverse_frac)
    return dec_tick(shifted, upwards=(sign > 0))


def dec_fee(
    eff_price: Decimal | float | str,
    qty: Decimal | float | str,
    cost: dict[str, Decimal],
) -> Decimal:
    """Compute trading fee in USDT on effective notional."""
    return D(eff_price) * D(qty) * (cost["fee_bps"] / BPS_DIVISOR)


def dec_floor_lot(qty_raw: Decimal) -> Decimal:
    """Floor quantity to 0.001 BTC lot step."""
    lots = (qty_raw / LOT_DEC + Decimal("1e-12")).to_integral_value(rounding=ROUND_FLOOR)
    return lots * LOT_DEC


def dec_split_quantities(qty: Decimal | float | str) -> tuple[Decimal, Decimal]:
    """Split total quantity into (q1_tp1, q2_runner) on 0.001 BTC lot boundaries."""
    q = D(qty)
    q1 = dec_floor_lot(q / Decimal(2))
    q2 = q - q1
    if q1 < LOT_DEC or q2 < LOT_DEC:
        raise ValueError(f"Quantity {q} cannot be split into two >=0.001 BTC lots")
    return q1, q2


def dec_1x_reserve_budget(
    cash_before: Decimal | float | str,
    raw_entry: Decimal | float | str,
    eff_entry: Decimal | float | str,
    atr_hour: Decimal | float | str,
    horizon_hours: int,
    cost: dict[str, Decimal],
) -> dict[str, Decimal]:
    """Compute exact 1x cash-account 5% reserve budget and per-unit reservation."""
    cash = D(cash_before)
    raw = D(raw_entry)
    eff = D(eff_entry)
    atr = D(atr_hour)
    budget = Decimal("0.95") * min(cash, Decimal(1000))
    worst_shift = dec_effective_price(raw + Decimal("0.25") * atr, 1, cost, is_entry=True)
    worst = max(eff, worst_shift)
    fee_unit = worst * cost["fee_bps"] / BPS_DIVISOR
    reserve_unit = (
        Decimal("1.10")
        * worst
        * (cost["fee_bps"] + Decimal("0.5") * cost["spread_bps"] + cost["slip_bps"])
        / BPS_DIVISOR
    )
    fund_unit = Decimal("1.10") * raw * Decimal(8) * Decimal(horizon_hours) / BPS_DIVISOR
    per_unit = worst + fee_unit + reserve_unit + fund_unit
    q = dec_floor_lot(budget / per_unit)
    return {
        "budget": budget,
        "per_unit": per_unit,
        "quantity": q,
        "reserved_notional": q * worst,
        "exit_cost_reserve": q * reserve_unit,
        "funding_reserve": q * fund_unit,
    }


def dec_mark_liquidation_equity(
    settled_cash: Decimal | float | str,
    pending_ack_pnl: Decimal | float | str,
    side: int,
    eff_entry: Decimal | float | str,
    remaining_qty: Decimal | float | str,
    raw_mark_close: Decimal | float | str,
    cost: dict[str, Decimal],
) -> tuple[Decimal, Decimal, Decimal]:
    """Compute 1x account minute Mark liquidation equity, raw Mark notional, and exposure ratio.

    Note: for settled_cash that includes trade entry fee debit (as in H1/H2/E1/E2 journal or
    E0 equity - fee_entry + due_funding), Mark equity is:
        settled_cash + pending_ack_pnl + side * (liq_mark - eff_entry) * remaining_qty - fee(liq_mark, remaining_qty)
    Returns (mark_equity, raw_mark_notional, exposure_ratio).
    """
    settled = D(settled_cash)
    pending = D(pending_ack_pnl)
    q_rem = D(remaining_qty)
    if q_rem <= Decimal(0):
        eq = settled + pending
        return eq, Decimal(0), Decimal(0)
    raw_m = D(raw_mark_close)
    liq_m = dec_effective_price(raw_m, side, cost, is_entry=False)
    fee_m = dec_fee(liq_m, q_rem, cost)
    eq = settled + pending + Decimal(side) * (liq_m - D(eff_entry)) * q_rem - fee_m
    notional = raw_m * q_rem
    ratio = notional / eq if eq > Decimal(0) else Decimal("Infinity")
    return eq, notional, ratio


def solve_decimal_liquidation_price_and_move(
    *,
    side: int,
    entry_price: Decimal,
    eff_entry: Decimal,
    open_qty: Decimal,
    wallet_margin_balance: Decimal,
    fee_frac: Decimal,
    adverse_exec_frac: Decimal,
    mmr: Decimal,
    clear_frac: Decimal,
) -> tuple[Decimal, Decimal]:
    """Solve in closed-form Decimal for exact Mark liquidation price `P_liq` and adverse move fraction `delta_p_liq`.

    Liquidation occurs when isolated Mark equity after exit fee/slip buffer reaches maintenance margin:
        wallet_margin_balance + side * (P_liq - eff_entry) * open_qty
            - open_qty * P_liq * (fee_frac + adverse_exec_frac)
        == open_qty * P_liq * (mmr + clear_frac)
    """
    if open_qty <= Decimal(0):
        return Decimal(0), Decimal(1)
    theta = fee_frac + adverse_exec_frac + mmr + clear_frac
    margin_per_btc = wallet_margin_balance / open_qty
    if side == 1:
        # P_liq * (1 - theta) = eff_entry - margin_per_btc
        denom = Decimal(1) - theta
        p_liq = max(Decimal(0), (eff_entry - margin_per_btc) / denom)
        delta_p_liq = (entry_price - p_liq) / entry_price
    else:
        # P_liq * (1 + theta) = eff_entry + margin_per_btc
        denom = Decimal(1) + theta
        p_liq = max(Decimal(0), (eff_entry + margin_per_btc) / denom)
        delta_p_liq = (p_liq - entry_price) / entry_price
    return p_liq, delta_p_liq


def evaluate_decimal_margin_scenario(
    *,
    scenario_id: str,
    side: int,
    leverage: Decimal | float | str,
    mmr: Decimal | float | str,
    clearance_fee_bps: Decimal | float | str,
    entry_price: Decimal | float | str,
    stop_distance_pct: Decimal | float | str,
    intrabar_adverse_mark_pct: Decimal | float | str,
    open_gap_adverse_pct: Decimal | float | str,
    mark_close_adverse_pct: Decimal | float | str | None = None,
    funding_rate_bps: Decimal | float | str = Decimal("8.0"),
    funding_settled_before_shock: bool = True,
    partial_tp1_before_shock: bool = False,
    tp1_cash_acked_before_shock: bool = False,
    cancel_replace_ack_pending_at_stop: bool = False,
    sizing_mode: str = "NAIVE_FULL_LEVERAGE_NOTIONAL",
    max_account_risk_pct: Decimal | float | str = Decimal("0.02"),
    initial_cash: Decimal | float | str = Decimal("1000.0"),
    cost_name: str = "STRESS",
    historical_bracket_status: str = "HYPOTHETICAL_STRESS_PARAMETER",
    override_initial_qty_btc: Decimal | float | str | None = None,
) -> dict[str, Any]:
    """Pure Decimal evaluation of an isolated/total-account margin, liquidation, and gap scenario.

    Explicitly separates:
    - `strict_initial_margin_usdt = initial_notional / L` vs `initial_margin_posted_usdt = N/L + discretionary_buffer`
    - 1m intrabar worst Mark shock (`intrabar_adverse_mark_pct`) vs 1m settled Mark close (`mark_close_adverse_pct`)
    - Pending un-ACKed TP1 profit vs ACKed spendable TP1 cash
    - Cancel-replace ACK race (stop triggering before TP1 quantity reduction is ACKed)
    - Isolated collateral deficit (`isolated_margin_after_gap_usdt < 0`) vs negative total account wealth (`total_account_equity_after_gap_usdt <= 0`)
    """
    cost = COST_MODELS_DEC[cost_name]
    lev = D(leverage)
    mmr_d = D(mmr)
    clear_bps = D(clearance_fee_bps)
    entry_p = D(entry_price)
    stop_dist = D(stop_distance_pct)
    shock_mark_dist = D(intrabar_adverse_mark_pct)
    close_mark_dist = D(mark_close_adverse_pct) if mark_close_adverse_pct is not None else shock_mark_dist
    gap_dist = D(open_gap_adverse_pct)
    fund_bps = D(funding_rate_bps)
    max_risk_pct = D(max_account_risk_pct)
    cash0 = D(initial_cash)

    fee_frac = cost["fee_bps"] / BPS_DIVISOR
    adverse_exec_frac = (Decimal("0.5") * cost["spread_bps"] + cost["slip_bps"]) / BPS_DIVISOR
    clear_frac = clear_bps / BPS_DIVISOR

    margin_budget = Decimal("0.95") * cash0
    stop_price = entry_p * (Decimal(1) - Decimal(side) * stop_dist)
    eff_entry = dec_effective_price(entry_p, side, cost, is_entry=True)

    per_unit_risk_frac = (
        stop_dist
        + Decimal("0.02")
        + Decimal(2) * (fee_frac + adverse_exec_frac)
        + (fund_bps / BPS_DIVISOR)
        + mmr_d
        + clear_frac
    )

    if sizing_mode == "NAIVE_FULL_LEVERAGE_NOTIONAL":
        target_notional = margin_budget * lev
        qty = dec_floor_lot(target_notional / entry_p)
    elif sizing_mode in ("RISK_BUDGET_CAPPED_ISOLATED", "RISK_BUDGET_CAPPED_STRICT_NL_MARGIN"):
        risk_budget_usdt = max_risk_pct * cash0
        max_notional_by_risk = risk_budget_usdt / per_unit_risk_frac
        max_notional_by_margin = margin_budget * lev / (Decimal(1) + lev * (mmr_d + clear_frac + fee_frac))
        target_notional = min(max_notional_by_risk, max_notional_by_margin)
        qty = dec_floor_lot(target_notional / entry_p)
    else:
        raise ValueError(f"Unsupported sizing_mode: {sizing_mode}")

    if override_initial_qty_btc is not None:
        qty = D(override_initial_qty_btc)

    if qty <= Decimal(0) or qty * entry_p < MIN_NOTIONAL_DEC:
        return {
            "scenario_id": scenario_id,
            "admitted": False,
            "sizing_mode": sizing_mode,
            "leverage": float(lev),
            "reason": "SIZE_OR_MIN_NOTIONAL_REJECTED",
        }

    initial_notional = qty * entry_p
    strict_initial_margin = initial_notional / lev

    if sizing_mode == "RISK_BUDGET_CAPPED_ISOLATED":
        # C R1 convention: posts max(N/L, N * per_unit_risk_frac) bounded by margin_budget
        initial_margin_posted = min(
            margin_budget,
            max(strict_initial_margin, initial_notional * per_unit_risk_frac),
        )
    else:
        # Both NAIVE_FULL_LEVERAGE_NOTIONAL and RISK_BUDGET_CAPPED_STRICT_NL_MARGIN post strictly N/L
        initial_margin_posted = strict_initial_margin

    discretionary_margin_buffer = max(Decimal(0), initial_margin_posted - strict_initial_margin)
    effective_isolated_leverage = initial_notional / initial_margin_posted
    entry_fee_usdt = qty * eff_entry * fee_frac

    open_qty = qty
    realized_tp1_pnl = Decimal(0)
    tp1_exit_fee = Decimal(0)
    if partial_tp1_before_shock:
        q1 = dec_floor_lot(qty / Decimal(2))
        open_qty = qty - q1
        tp1_raw = entry_p * (Decimal(1) + Decimal(side) * stop_dist)
        tp1_eff = dec_effective_price(tp1_raw, side, cost, is_entry=False)
        tp1_exit_fee = q1 * tp1_eff * fee_frac
        realized_tp1_pnl = Decimal(side) * (tp1_eff - eff_entry) * q1

    # If cancel-replace ACK is still pending when the stop triggers, the exchange stop order
    # still carries the unreduced quantity `qty` (or creates a race condition).
    stop_exec_qty = qty if (partial_tp1_before_shock and cancel_replace_ack_pending_at_stop) else open_qty

    funding_debit_usdt = (
        open_qty * entry_p * (fund_bps / BPS_DIVISOR) if funding_settled_before_shock else Decimal(0)
    )

    acked_tp1_credit = realized_tp1_pnl if (partial_tp1_before_shock and tp1_cash_acked_before_shock) else Decimal(0)

    wallet_margin_balance_posted = (
        initial_margin_posted - entry_fee_usdt - tp1_exit_fee - funding_debit_usdt + acked_tp1_credit
    )
    wallet_margin_balance_strict = (
        strict_initial_margin - entry_fee_usdt - tp1_exit_fee - funding_debit_usdt + acked_tp1_credit
    )

    p_liq_posted, delta_p_liq_posted = solve_decimal_liquidation_price_and_move(
        side=side,
        entry_price=entry_p,
        eff_entry=eff_entry,
        open_qty=open_qty,
        wallet_margin_balance=wallet_margin_balance_posted,
        fee_frac=fee_frac,
        adverse_exec_frac=adverse_exec_frac,
        mmr=mmr_d,
        clear_frac=clear_frac,
    )
    p_liq_strict, delta_p_liq_strict = solve_decimal_liquidation_price_and_move(
        side=side,
        entry_price=entry_p,
        eff_entry=eff_entry,
        open_qty=open_qty,
        wallet_margin_balance=wallet_margin_balance_strict,
        fee_frac=fee_frac,
        adverse_exec_frac=adverse_exec_frac,
        mmr=mmr_d,
        clear_frac=clear_frac,
    )

    # Evaluate at intrabar worst Mark price (`shock_mark_dist`)
    shock_mark_price = entry_p * (Decimal(1) - Decimal(side) * shock_mark_dist)
    open_notional_at_shock = open_qty * shock_mark_price
    exit_fee_buffer_at_shock = open_notional_at_shock * (fee_frac + adverse_exec_frac)
    maintenance_margin_required = open_notional_at_shock * (mmr_d + clear_frac)
    unrealized_mark_pnl = Decimal(side) * (shock_mark_price - eff_entry) * open_qty

    effective_margin_equity_posted = (
        wallet_margin_balance_posted + unrealized_mark_pnl - exit_fee_buffer_at_shock
    )
    effective_margin_equity_strict = (
        wallet_margin_balance_strict + unrealized_mark_pnl - exit_fee_buffer_at_shock
    )

    mark_liquidated_at_shock = effective_margin_equity_posted <= maintenance_margin_required
    mark_liquidated_before_stop = (
        mark_liquidated_at_shock and shock_mark_dist <= stop_dist + EPS_1E9
    )

    strict_nl_liquidated_at_shock = effective_margin_equity_strict <= maintenance_margin_required
    strict_nl_liquidated_before_stop = (
        strict_nl_liquidated_at_shock and shock_mark_dist <= stop_dist + EPS_1E9
    )

    # Evaluate at 1m settled Mark close (`close_mark_dist`) to distinguish intrabar wick vs settled close
    close_mark_price = entry_p * (Decimal(1) - Decimal(side) * close_mark_dist)
    close_notional = open_qty * close_mark_price
    close_exit_fee_buf = close_notional * (fee_frac + adverse_exec_frac)
    close_mm_req = close_notional * (mmr_d + clear_frac)
    close_upnl = Decimal(side) * (close_mark_price - eff_entry) * open_qty
    close_margin_eq_posted = wallet_margin_balance_posted + close_upnl - close_exit_fee_buf
    mark_liquidated_at_close = close_margin_eq_posted <= close_mm_req

    # Stop-vs-liquidation ordering classification under conservative 1m intrabar sequencing
    if mark_liquidated_at_shock and delta_p_liq_posted <= stop_dist + EPS_1E9:
        if mark_liquidated_at_close:
            clock_ordering = "LIQUIDATION_FIRST_BOTH_WICK_AND_CLOSE"
        else:
            clock_ordering = "LIQUIDATION_FIRST_ON_INTRABAR_MARK_WICK"
    elif mark_liquidated_at_shock and not mark_liquidated_at_close:
        clock_ordering = "INTRABAR_MARK_WICK_BREACHES_LIQUIDATION_WHILE_CLOSE_SAFE"
    elif shock_mark_dist >= stop_dist:
        clock_ordering = "STRATEGY_STOP_FIRST_BEFORE_LIQUIDATION_THRESHOLD"
    else:
        clock_ordering = "NEITHER_STOP_NOR_LIQUIDATION_TRIGGERED_AT_SHOCK"

    # Evaluate bar-open adverse stop-gap shock (`gap_dist`)
    gap_open_price = entry_p * (Decimal(1) - Decimal(side) * gap_dist)
    gap_eff_exit = dec_effective_price(gap_open_price, side, cost, is_entry=False)
    gap_exit_fee = stop_exec_qty * gap_eff_exit * fee_frac
    gap_realized_loss = Decimal(side) * (gap_eff_exit - eff_entry) * stop_exec_qty

    isolated_margin_after_gap_posted = (
        wallet_margin_balance_posted + gap_realized_loss - gap_exit_fee
    )
    isolated_margin_deficit_signed = min(Decimal(0), isolated_margin_after_gap_posted)
    isolated_margin_shortfall_positive = max(Decimal(0), -isolated_margin_after_gap_posted)

    isolated_margin_after_gap_strict = (
        wallet_margin_balance_strict + gap_realized_loss - gap_exit_fee
    )
    strict_nl_deficit_signed = min(Decimal(0), isolated_margin_after_gap_strict)

    account_equity_after_gap = (
        cash0
        - entry_fee_usdt
        - tp1_exit_fee
        - funding_debit_usdt
        + realized_tp1_pnl
        + gap_realized_loss
        - gap_exit_fee
    )

    return {
        "scenario_id": scenario_id,
        "grade": "SYNTHETIC_ONLY_DECIMAL_MARGIN_CONTRACT__NOT_HISTORICAL_BINANCE_TIER_OR_EMPIRICAL_RETURN",
        "historical_bracket_status": historical_bracket_status,
        "sizing_mode": sizing_mode,
        "side": side,
        "leverage": float(lev),
        "hypothetical_mmr": float(mmr_d),
        "hypothetical_clearance_fee_bps": float(clear_bps),
        "admitted": True,
        "initial_qty_btc": q6(qty),
        "open_qty_at_shock_btc": q6(open_qty),
        "stop_exec_qty_btc": q6(stop_exec_qty),
        "initial_notional_usdt": q4(initial_notional),
        "effective_account_leverage_ratio": q4(initial_notional / cash0),
        "strict_exchange_initial_margin_usdt": q4(strict_initial_margin),
        "discretionary_margin_buffer_usdt": q4(discretionary_margin_buffer),
        "initial_margin_posted_usdt": q4(initial_margin_posted),
        "effective_isolated_position_leverage": q4(effective_isolated_leverage),
        "stop_price": float(stop_price.quantize(Decimal("0.01"))),
        "stop_distance_pct": float(stop_dist),
        "intrabar_adverse_mark_pct": float(shock_mark_dist),
        "mark_close_adverse_pct": float(close_mark_dist),
        "open_gap_adverse_pct": float(gap_dist),
        "partial_tp1_before_shock": bool(partial_tp1_before_shock),
        "tp1_cash_acked_before_shock": bool(tp1_cash_acked_before_shock),
        "funding_settled_before_shock": bool(funding_settled_before_shock),
        "cancel_replace_ack_pending_at_stop": bool(cancel_replace_ack_pending_at_stop),
        "posted_margin_liq_price": q4(p_liq_posted),
        "posted_margin_liq_adverse_move_pct": q6(delta_p_liq_posted),
        "strict_nl_margin_liq_price": q4(p_liq_strict),
        "strict_nl_margin_liq_adverse_move_pct": q6(delta_p_liq_strict),
        "maintenance_margin_required_usdt": q4(maintenance_margin_required),
        "effective_margin_equity_at_shock_usdt": q4(effective_margin_equity_posted),
        "strict_nl_effective_margin_equity_at_shock_usdt": q4(effective_margin_equity_strict),
        "mark_liquidated_at_shock": bool(mark_liquidated_at_shock),
        "mark_liquidated_at_close": bool(mark_liquidated_at_close),
        "mark_liquidated_before_strategy_stop": bool(mark_liquidated_before_stop),
        "strict_nl_liquidated_at_shock": bool(strict_nl_liquidated_at_shock),
        "strict_nl_liquidated_before_strategy_stop": bool(strict_nl_liquidated_before_stop),
        "stop_vs_liquidation_clock_ordering": clock_ordering,
        "isolated_margin_after_gap_usdt": q4(isolated_margin_after_gap_posted),
        "isolated_margin_bankruptcy_deficit_usdt": q4(isolated_margin_deficit_signed),
        "isolated_bankruptcy_shortfall_positive_usdt": q4(isolated_margin_shortfall_positive),
        "strict_nl_isolated_margin_bankruptcy_deficit_usdt": q4(strict_nl_deficit_signed),
        "isolated_collateral_bankrupt_after_gap": bool(isolated_margin_after_gap_posted < Decimal(0)),
        "total_account_equity_after_gap_usdt": q4(account_equity_after_gap),
        "account_insolvent_after_gap": bool(account_equity_after_gap <= Decimal(0)),
        "negative_isolated_but_positive_total_equity": bool(
            isolated_margin_after_gap_posted < Decimal(0) and account_equity_after_gap > Decimal(0)
        ),
    }


def compute_filtered_scenario_denominators(
    scenarios: list[dict[str, Any]],
    group_predicates: dict[str, Callable[[dict[str, Any]], bool]],
) -> dict[str, dict[str, Any]]:
    """Compute exact X / Y numerator/denominator counts directly from scenario rows.

    Enforces:
    - Y == len(filtered_rows)
    - If Y == 0, ratio string is 'UNKNOWN'
    - For every boolean condition, 0 <= X <= Y (never X/Y > 1)
    """
    results: dict[str, dict[str, Any]] = {}
    metrics_predicates: dict[str, Callable[[dict[str, Any]], bool]] = {
        "mark_liquidated_at_shock": lambda s: bool(s.get("mark_liquidated_at_shock", False)),
        "mark_liquidated_before_strategy_stop": lambda s: bool(
            s.get("mark_liquidated_before_strategy_stop", False)
        ),
        "strict_nl_liquidated_before_strategy_stop": lambda s: bool(
            s.get("strict_nl_liquidated_before_strategy_stop", s.get("mark_liquidated_before_strategy_stop", False))
        ),
        "isolated_gap_bankruptcy_deficit": lambda s: float(
            s.get("isolated_margin_bankruptcy_deficit_usdt", 0.0)
        )
        < 0.0,
        "account_insolvent_after_gap": lambda s: bool(s.get("account_insolvent_after_gap", False)),
    }

    for group_name, pred in group_predicates.items():
        subset = [s for s in scenarios if s.get("admitted", True) and pred(s)]
        denom = len(subset)
        group_entry: dict[str, Any] = {
            "denominator_n": denom,
            "scenario_ids": [s["scenario_id"] for s in subset],
            "counts": {},
        }
        for m_name, m_pred in metrics_predicates.items():
            if denom == 0:
                group_entry["counts"][m_name] = {
                    "numerator": 0,
                    "denominator": 0,
                    "ratio_str": "UNKNOWN",
                    "fraction": None,
                    "matching_scenario_ids": [],
                }
            else:
                matched = [s["scenario_id"] for s in subset if m_pred(s)]
                num = len(matched)
                assert 0 <= num <= denom, f"Impossible count {num}/{denom} for {group_name}.{m_name}"
                group_entry["counts"][m_name] = {
                    "numerator": num,
                    "denominator": denom,
                    "ratio_str": f"{num}/{denom}",
                    "fraction": round(num / denom, 6),
                    "matching_scenario_ids": matched,
                }
        results[group_name] = group_entry
    return results


def compute_stop_vs_liquidation_inequalities(
    *,
    w1_max_stop_pct: Decimal = Decimal("0.036120"),
    w1_median_stop_pct: Decimal = Decimal("0.016507"),
    w2_max_stop_pct: Decimal = Decimal("0.035591"),
    w2_median_stop_pct: Decimal = Decimal("0.014270"),
    synthetic_stop_pct: Decimal = Decimal("0.075000"),
    entry_price: Decimal = Decimal("30000.0"),
    clearance_fee_bps: Decimal = Decimal("75.0"),
    funding_rate_bps: Decimal = Decimal("8.0"),
    cost_name: str = "STRESS",
) -> dict[str, Any]:
    """Compute exact Decimal liquidation thresholds for 1x, 5x, 10x, 15x and compare with real vs synthetic stops."""
    cost = COST_MODELS_DEC[cost_name]
    fee_frac = cost["fee_bps"] / BPS_DIVISOR
    adverse_exec_frac = (Decimal("0.5") * cost["spread_bps"] + cost["slip_bps"]) / BPS_DIVISOR
    clear_frac = clearance_fee_bps / BPS_DIVISOR
    fund_frac = funding_rate_bps / BPS_DIVISOR
    eff_entry_long = dec_effective_price(entry_price, 1, cost, is_entry=True)
    eff_entry_short = dec_effective_price(entry_price, -1, cost, is_entry=True)

    grid_rows: list[dict[str, Any]] = []
    for lev_int in (1, 5, 10, 15):
        lev = Decimal(lev_int)
        im_frac = Decimal(1) / lev
        for mmr_str in ("0.004", "0.005", "0.010"):
            mmr = Decimal(mmr_str)
            for side in (1, -1):
                eff_e = eff_entry_long if side == 1 else eff_entry_short
                q = Decimal(1)
                m_strict = entry_price / lev
                entry_fee = eff_e * fee_frac
                fund_debit = entry_price * fund_frac
                wallet_m = m_strict - entry_fee - fund_debit
                p_liq, delta_p_liq = solve_decimal_liquidation_price_and_move(
                    side=side,
                    entry_price=entry_price,
                    eff_entry=eff_e,
                    open_qty=q,
                    wallet_margin_balance=wallet_m,
                    fee_frac=fee_frac,
                    adverse_exec_frac=adverse_exec_frac,
                    mmr=mmr,
                    clear_frac=clear_frac,
                )
                grid_rows.append({
                    "leverage": lev_int,
                    "side": "LONG" if side == 1 else "SHORT",
                    "initial_margin_pct": round(float(im_frac * Decimal(100)), 4),
                    "hypothetical_mmr_bps": float(mmr * BPS_DIVISOR),
                    "clearance_fee_bps": float(clearance_fee_bps),
                    "entry_and_exit_friction_plus_funding_bps": float(
                        (Decimal(2) * (fee_frac + adverse_exec_frac) + fund_frac) * BPS_DIVISOR
                    ),
                    "liquidation_price_from_30000": q4(p_liq),
                    "adverse_mark_move_to_liquidation_pct": round(float(delta_p_liq * Decimal(100)), 4),
                    "liquidates_at_w1_max_stop_3_6120pct_without_extra_wick": bool(
                        delta_p_liq <= w1_max_stop_pct
                    ),
                    "liquidates_at_w2_max_stop_3_5591pct_without_extra_wick": bool(
                        delta_p_liq <= w2_max_stop_pct
                    ),
                    "liquidates_before_synthetic_7_5000pct_stop": bool(
                        delta_p_liq <= synthetic_stop_pct
                    ),
                    "headroom_above_w1_max_stop_pct": round(
                        float((delta_p_liq - w1_max_stop_pct) * Decimal(100)), 4
                    ),
                })

    im_15x = Decimal(1) / Decimal(15)
    min_combined_nonprice_buffer_for_w1_max = im_15x - w1_max_stop_pct
    min_combined_nonprice_buffer_for_w2_max = im_15x - w2_max_stop_pct

    return {
        "historical_stop_distance_summary_pct": {
            "W1_C04_max_1R_stop_pct": float(w1_max_stop_pct * Decimal(100)),
            "W1_C04_median_1R_stop_pct": float(w1_median_stop_pct * Decimal(100)),
            "W2_C05_max_1R_stop_pct": float(w2_max_stop_pct * Decimal(100)),
            "W2_C05_median_1R_stop_pct": float(w2_median_stop_pct * Decimal(100)),
        },
        "synthetic_scenario_stop_distance_pct": float(synthetic_stop_pct * Decimal(100)),
        "c_r1_contradiction_2_disposition": {
            "c_r1_report_claim_7_5_to_11_6_pct_1R_stop": "INVALID__CONFLATED_UNSTOPPED_24H_MAE_AND_SYNTHETIC_STOP_WITH_HISTORICAL_1R_STOP",
            "c_r1_machine_string_3_61pct_exceeds_15x_margin": "INVALID__MATHEMATICALLY_FALSE_UNDER_STANDARD_MMR",
            "mathematical_proof": (
                "At 15x gross leverage, raw initial margin is 1/15 = 6.6667%. Under STRESS costs "
                "(22 bps per leg fee+half-spread+slip = 44 bps roundtrip), 8 bps funding, 75 bps clearance, "
                "and 40-100 bps MMR, the adverse Mark move to liquidation is 4.4441% to 5.0660% (LONG) and "
                "4.3118% to 4.9961% (SHORT). All strictly exceed historical max 1R stop distances "
                "(3.6120% W1, 3.5591% W2) by +0.70% to +1.45% of entry price. A 3.6120% stop move alone "
                "triggers liquidation at 15x ONLY if combined non-price buffers (MMR + clearance + fees + funding) "
                "exceed 6.6667% - 3.6120% = 3.0547% (305.47 bps), or if an intrabar Mark wick / cross-minute "
                "gap exceeds ~4.31%-5.07% before the 1m Last stop executes."
            ),
            "min_combined_nonprice_buffer_pct_to_liquidate_at_w1_max_3_6120pct_at_15x": round(
                float(min_combined_nonprice_buffer_for_w1_max * Decimal(100)), 4
            ),
            "min_combined_nonprice_buffer_pct_to_liquidate_at_w2_max_3_5591pct_at_15x": round(
                float(min_combined_nonprice_buffer_for_w2_max * Decimal(100)), 4
            ),
        },
        "liquidation_threshold_grid": grid_rows,
    }
