"""Independent Decimal first-hit and cash audit; never invokes replay helpers."""
from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

import numpy as np


def audit_episode(data: np.ndarray, event: dict, candidate: dict, cost: dict, trade: dict) -> dict:
    def d(value):
        return Decimal(str(value))

    def tick(value, up):
        return (value / Decimal("0.1")).to_integral_value(
            rounding=ROUND_CEILING if up else ROUND_FLOOR
        ) * Decimal("0.1")

    def execution(raw, sign):
        shift = (d(cost["spread_bps"]) / 2 + d(cost["slip_bps"])) / 10000
        return tick(raw * (1 + sign * shift), sign > 0)

    side = int(event["side"])
    entry_at = int(event["entry_at"])
    start = int(np.searchsorted(data[:, 0], entry_at))
    assert int(data[start, 0]) == entry_at
    assert event["decision_at"] == event["event_time"] + 60000
    assert entry_at == event["decision_at"] + 60000
    raw_entry = d(data[start, 1])
    eff_entry = execution(raw_entry, side)
    stop = tick(d(event["stop"]), side < 0)
    target = tick(eff_entry + side * d(candidate["target_R"]) * side * (eff_entry - stop), side < 0)
    deadline = entry_at + int(candidate["horizon_hours"]) * 3600000
    expected = None
    scanned = 0
    for row in data[start:]:
        at = int(row[0]); op, hi, lo = map(d, row[1:4])
        scanned += 1
        if side * (op - stop) <= 0:
            expected = ("STOP_GAP", op, at)
        elif at >= deadline:
            expected = ("TIME_CAP", min(op, target) if side > 0 else max(op, target), at)
        elif side * (op - target) >= 0:
            expected = ("TARGET_GAP_CAPPED", target, at)
        elif (lo <= stop if side > 0 else hi >= stop):
            expected = ("STOP", stop, at + 59999)
        elif (hi >= target if side > 0 else lo <= target):
            expected = ("TARGET", target, at + 59999)
        if expected is not None:
            break
    assert expected is not None, "Independent path incomplete"
    reason, raw_exit, exit_at = expected
    assert reason == trade["exit_reason"]
    assert exit_at == trade["exit_at"]
    assert abs(raw_exit - d(trade["raw_exit"])) < Decimal("0.000001")
    assert abs(stop - d(trade["stop"])) < Decimal("0.000001")
    assert abs(target - d(trade["target"])) < Decimal("0.000001")
    eff_exit = execution(raw_exit, -side)
    q = d(trade["quantity"])
    fee_entry = eff_entry * q * d(cost["fee_bps"]) / 10000
    fee_exit = eff_exit * q * d(cost["fee_bps"]) / 10000
    net = side * (eff_exit - eff_entry) * q - fee_entry - fee_exit
    bps = net / (raw_entry * q) * 10000
    assert abs(net - d(trade["net_usdt"])) < Decimal("0.000001")
    assert abs(bps - d(trade["net_bps"])) < Decimal("0.00001")
    assert abs(fee_entry - d(trade["fee_entry"])) < Decimal("0.000001")
    assert abs(fee_exit - d(trade["fee_exit"])) < Decimal("0.000001")
    assert trade["exit_ack_at"] > exit_at
    return {"event_id": trade["event_id"], "side": side, "reason": reason,
            "candidate": candidate["id"], "scanned_minutes": scanned,
            "entry_at": entry_at, "exit_at": exit_at, "exit_ack_at": trade["exit_ack_at"],
            "decimal_raw_entry": str(raw_entry), "decimal_stop": str(stop), "decimal_target": str(target),
            "decimal_raw_exit": str(raw_exit), "decimal_entry_fee": str(fee_entry),
            "decimal_exit_fee": str(fee_exit), "decimal_net_usdt": str(net),
            "decimal_net_bps": str(bps), "float_net_bps": trade["net_bps"], "assertions": "PASS"}
