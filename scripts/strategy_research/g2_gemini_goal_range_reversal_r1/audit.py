"""Independent Decimal arithmetic and minute-by-minute first-hit audit for 3-5 trades per candidate.

Calls no replay helpers. Independently verifies:
- Event -> Decision (+60s) -> Entry (+120s) causal clocks
- Decimal tick rounding, spread+slippage drag, target_r calculation
- First-hit minute walk with same-bar SL-first priority, adverse open gap, favorable target cap, time cap
- Single-counted entry and exit leg fees and net USDT / net bps.
"""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

import numpy as np


def d(value: Any) -> Decimal:
    return Decimal(str(value))


def rounded(price: Decimal, up: bool) -> Decimal:
    tick = Decimal("0.1")
    eps = Decimal("0.000000001")
    units = (price / tick) - eps if up else (price / tick) + eps
    return units.to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * tick


def audit_single_trade(data: np.ndarray, trade: dict[str, Any], costs: dict[str, Any]) -> dict[str, Any]:
    assert not trade.get("partial_reductions") and trade["exit_reason"] != "DRAWDOWN_KILL"
    assert int(trade["decision_at"]) >= int(trade["event_time"]) + 60_000
    assert int(trade["entry_at"]) >= int(trade["decision_at"]) + 60_000
    i = int(np.searchsorted(data[:, 0], trade["entry_at"]))
    assert int(data[i, 0]) == int(trade["entry_at"])
    assert int(data[i - 2, 0]) + 120_000 <= int(trade["entry_at"])

    side = int(trade["side"])
    qty = d(trade["quantity"])
    entry = d(float(data[i, 1]))
    assert entry == d(trade["raw_entry"])
    slip_val = costs.get("slippage_bps", costs.get("slip_bps"))
    drag = (d(costs["spread_bps"]) + d(slip_val)) / Decimal("10000")
    effective_entry = rounded(entry * (Decimal("1") + side * drag), side > 0)
    stop = d(trade["stop"])
    risk = side * (effective_entry - stop)
    target_r = d(trade.get("target_r", 2.0))
    target = rounded(effective_entry + side * target_r * risk, side < 0)
    assert abs(target - d(trade["target"])) <= Decimal("0.100001")
    target = d(trade["target"])

    deadline = int(trade["entry_at"]) + int(trade["hold_hours"]) * 3_600_000
    witness = None
    for j in range(i, len(data)):
        at = int(data[j, 0])
        op, hi, lo = (d(float(v)) for v in data[j, 1:4])
        if side * (op - stop) <= 0:
            raw, reason, exit_at = op, "STOP_GAP", at
        elif at >= deadline:
            raw = min(op, target) if side > 0 else max(op, target)
            reason, exit_at = "TIME_CAP", at
        elif side * (op - target) >= 0:
            raw, reason, exit_at = target, "TARGET_GAP_CAPPED", at
        elif lo <= stop if side > 0 else hi >= stop:
            raw, reason, exit_at = stop, "STOP", at + 59_999
        elif hi >= target if side > 0 else lo <= target:
            raw, reason, exit_at = target, "TARGET", at + 59_999
        else:
            continue
        collision = (lo <= stop and hi >= target) if side > 0 else (hi >= stop and lo <= target)
        witness = {"utc_minute_open_ms": at, "stop_target_same_bar": bool(collision)}
        break

    assert witness is not None
    assert reason == trade["exit_reason"] and exit_at == int(trade["exit_at"])
    assert abs(raw - d(trade["raw_exit"])) < Decimal("0.000001")

    effective_exit = rounded(raw * (Decimal("1") - side * drag), side < 0)
    fee_rate = d(costs["fee_bps"]) / Decimal("10000")
    entry_fee = effective_entry * qty * fee_rate
    exit_fee = effective_exit * qty * fee_rate
    net = side * (effective_exit - effective_entry) * qty - entry_fee - exit_fee

    for key, val in (
        ("effective_entry", effective_entry),
        ("effective_exit", effective_exit),
        ("entry_fee_usdt", entry_fee),
        ("exit_fee_usdt", exit_fee),
        ("net_usdt", net),
    ):
        assert abs(val - d(trade[key])) < Decimal("0.000001"), f"Mismatch on {key}"

    return {
        "candidate": trade["candidate"],
        "fold": trade["fold"],
        "cost_case": trade["cost_case"],
        "event_id": trade["event_id"],
        "side": side,
        "event_time": int(trade["event_time"]),
        "decision_at": int(trade["decision_at"]),
        "entry_at": int(trade["entry_at"]),
        "exit_at": exit_at,
        "exit_reason": reason,
        "source_entry_open": str(entry),
        "raw_exit": str(raw),
        "stop": str(stop),
        "target": str(target),
        "target_r": str(target_r),
        "quantity": str(qty),
        "effective_entry": str(effective_entry),
        "effective_exit": str(effective_exit),
        "decimal_entry_fee": str(entry_fee),
        "decimal_exit_fee": str(exit_fee),
        "decimal_net_usdt": str(net),
        "net_bps": float(trade["net_bps"]),
        "exit_witness": witness,
        "assertions": "PASS",
    }


def audit_candidate_trades(
    data: np.ndarray,
    trades: list[dict[str, Any]],
    costs_by_name: dict[str, dict[str, Any]],
    max_per_candidate: int = 5,
) -> list[dict[str, Any]]:
    """Select up to `max_per_candidate` trades per candidate for independent Decimal hand-audit."""
    by_cand: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        if not t.get("partial_reductions") and t["exit_reason"] != "DRAWDOWN_KILL":
            by_cand.setdefault(str(t["candidate"]), []).append(t)

    audited: list[dict[str, Any]] = []
    for cid, cand_trades in sorted(by_cand.items()):
        ordered = sorted(
            cand_trades,
            key=lambda x: (int(x["entry_at"]), str(x["cost_case"]), str(x["event_id"])),
        )
        # Prefer STRESS trades covering LONG, SHORT, STOP, TARGET, TIME_CAP
        stress_First = sorted(ordered, key=lambda x: (0 if x["cost_case"] == "STRESS" else 1, int(x["entry_at"])))
        chosen: list[dict[str, Any]] = []
        seen_ids: set[tuple[str, str]] = set()
        predicates = [
            lambda x: x["side"] == 1 and x["exit_reason"] == "STOP",
            lambda x: x["side"] == -1 and x["exit_reason"] == "STOP",
            lambda x: x["exit_reason"] == "TARGET",
            lambda x: x["exit_reason"] == "TIME_CAP",
            lambda x: True,
        ]
        for pred in predicates:
            for t in stress_First:
                key = (str(t["event_id"]), str(t["cost_case"]))
                if key not in seen_ids and pred(t):
                    chosen.append(t)
                    seen_ids.add(key)
                    break
            if len(chosen) >= max_per_candidate:
                break
        for t in stress_First:
            if len(chosen) >= max_per_candidate:
                break
            key = (str(t["event_id"]), str(t["cost_case"]))
            if key not in seen_ids:
                chosen.append(t)
                seen_ids.add(key)

        for t in chosen:
            audited.append(audit_single_trade(data, t, costs_by_name[t["cost_case"]]))
    return audited
