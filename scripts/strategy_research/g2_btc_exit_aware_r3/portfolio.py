"""Independent monthly simulated books and unfunded paired-episode quantities."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.replay import _size

from .engine import HOUR, MINUTE, Cost, dec, dense_equity, episode, lots, make_entry


@dataclass
class ResearchAccount:
    initial_equity: float = 1000.0
    cash: float = 1000.0
    disabled: bool = False
    busy_until: int = -1


def size(data, event, candidate, cost, equity=1000.0):
    i = int(np.searchsorted(data[:, 0], event["entry_at"]))
    e = make_entry(data, event, candidate["cap_hours"], Cost.from_dict(cost), Decimal(1))
    proposal = {
        "raw_entry": float(e.raw_price),
        "atr_hour": float(e.atr_hour),
        "last_available_close": float(data[i - 2, 4]),
        "hold_hours": candidate["cap_hours"],
    }
    c = {"id": candidate["id"], "allocation_fraction": 0.5, "family": "R3_DEVELOPMENT"}
    q = _size(equity, proposal, c, cost)
    return lots(dec(q) + Decimal("0.000000000001"))


def month(data, events, candidate, fold, cost, hourly):
    first = int(np.searchsorted(data[:, 0], fold["start_ms"]))
    last = int(np.searchsorted(data[:, 0], fold["end_ms"]))
    clock = data[first:last, 0].astype(np.int64)
    curve = np.full(len(clock), 1000.0)
    exposure = np.zeros(len(clock))
    account = ResearchAccount()
    trades = []
    fates = []
    waits = Counter()
    ids = set()
    highwater = 1000.0
    cursor = 0

    def refuse(ev, why):
        waits[why] += 1
        fates.append({"event_id": ev["event_id"], "entry_at": ev["entry_at"], "result": why})

    for event in sorted(events, key=lambda e: (e["entry_at"], e["event_id"])):
        t = event["entry_at"]
        if event["event_id"] in ids:
            refuse(event, "DUPLICATE_ENTRY")
            continue
        ids.add(event["event_id"])
        if t < fold["start_ms"] or t + 24 * HOUR + MINUTE > fold["end_ms"]:
            refuse(event, "COMMON_24H_PLUS_ACK_FOLD_CUTOFF")
            continue
        if t < account.busy_until:
            refuse(event, "POSITION_ACK_OR_COOLDOWN")
            continue
        if account.disabled:
            refuse(event, "RISK_DISABLED")
            continue
        n = int(np.searchsorted(clock, t))
        curve[cursor:n] = account.cash
        known = curve[max(0, n - 2)]
        try:
            quantity = size(data, event, candidate, cost, min(account.cash, float(known)))
            if quantity <= 0:
                raise ValueError("SIZE_OR_MIN_NOTIONAL")
            trade = episode(
                data,
                event,
                candidate["exit"],
                candidate["cap_hours"],
                Cost.from_dict(cost),
                quantity,
                hourly,
                validated=True,
            )
        except ValueError as exc:
            refuse(event, str(exc))
            continue
        eq, exp = dense_equity(data, trade, account.cash)
        peaks = np.maximum.accumulate(np.r_[highwater, eq])[1:]
        breaches = np.flatnonzero((peaks - eq >= 100 - 1e-8) | (exp > np.maximum(eq, 0) + 1e-8))
        if len(breaches):
            force = t + (int(breaches[0]) + 3) * MINUTE
            if force <= trade["exit_at"] // MINUTE * MINUTE:
                trade = episode(
                    data,
                    event,
                    candidate["exit"],
                    candidate["cap_hours"],
                    Cost.from_dict(cost),
                    quantity,
                    hourly,
                    force_at=force,
                    validated=True,
                )
                eq, exp = dense_equity(data, trade, account.cash)
                peaks = np.maximum.accumulate(np.r_[highwater, eq])[1:]
            if np.any(peaks[: len(eq)] - eq >= 100 - 1e-8):
                account.disabled = True
        end = n + len(eq)
        curve[n:end] = eq
        exposure[n:end] = exp
        account.cash += float(trade["net_usdt"])
        highwater = max(highwater, float(np.max(eq)), account.cash)
        if highwater - account.cash >= 100 - 1e-8:
            account.disabled = True
        account.busy_until = trade["exit_ack_at"] + HOUR
        cursor = end
        trade.update(fold=fold["id"], year=fold["year"], candidate=candidate["id"])
        trades.append(trade)
        fates.append({"event_id": event["event_id"], "entry_at": t, "result": "FILLED_SIMULATED"})
    curve[cursor:] = account.cash
    close_curve = np.r_[1000.0, 1000.0 + np.cumsum([float(t["net_usdt"]) for t in trades])]
    dd = lambda values: float(
        np.max(100 * (np.maximum.accumulate(values) - values) / np.maximum.accumulate(values))
    )
    return {
        "trades": trades,
        "event_fates": fates,
        "waits": dict(waits),
        "curve": curve,
        "exposure": exposure,
        "ending_equity": account.cash,
        "month_return_pct": (account.cash / 1000 - 1) * 100,
        "dense_MTM_DD_pct": dd(curve),
        "closed_DD_pct": dd(close_curve),
        "disabled": account.disabled,
        "sum_nominal_books_not_single_account_ROI": True,
    }


def funding_sensitivity(data, trade):
    entry, exit = trade["entry_at"], trade["exit_at"]
    q0 = trade["initial_quantity"]
    result = {}
    for label, interval, rates in [
        ("UTC8H_PLUS_MINUS_15S", 8 * HOUR, [4, 8]),
        ("UNKNOWN_HOURLY", HOUR, [8]),
    ]:
        charges = {str(r): Decimal(0) for r in rates}
        count = 0
        at = ((entry - 15000 + interval - 1) // interval) * interval
        while at <= exit + 15000:
            q = q0 - sum(
                (leg["quantity"] for leg in trade["legs"] if leg["fill_at"] < at - 15000),
                Decimal(0),
            )
            if q > 0:
                count += 1
                left = int(np.searchsorted(data[:, 0], at - 15000, "right")) - 1
                right = int(np.searchsorted(data[:, 0], at + 15000, "right"))
                price = dec(np.max(data[max(0, left) : max(left + 1, right), 2]))
                for r in rates:
                    charges[str(r)] += q * price * dec(r) / 10000
            at += interval
        result[label] = {
            "possible_windows": count,
            "adverse_usdt": {k: str(v) for k, v in charges.items()},
            "basis": "assumed cadence, remaining qty, Last high; not verified funding/Mark",
        }
    return result
