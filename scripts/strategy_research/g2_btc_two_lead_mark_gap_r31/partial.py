"""Funding-only attribution when authenticated minute Mark coverage is incomplete.

This module replays the two frozen R2 last-price books.  It never substitutes
last price for a missing Mark or turns a partially covered book into a return.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.run import IDS, OLD_EP
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_controls import (
    matched_control,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import (
    canonical,
    eligible_events,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    STRESS,
    simulate_fold,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.signals import generate_wave_signals
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.sources import get_monthly_folds

MINUTE = 60_000


def _decimal(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid funding arithmetic input") from exc
    if not number.is_finite():
        raise ValueError("nonfinite funding arithmetic input")
    return number


def _mark_map(arrays: dict) -> dict[int, Decimal]:
    """Preserve exact sparse clocks; duplicate or invalid source rows fail closed."""
    found: dict[int, Decimal] = {}
    for key in sorted(arrays):
        if not (isinstance(key, tuple) and len(key) == 2 and 2021 <= key[0] <= 2023 and 1 <= key[1] <= 12):
            raise ValueError("out-of-scope partial Mark month")
        month = arrays[key]
        if month.ndim != 2 or month.shape[1] != 5:
            raise ValueError("partial Mark must be Nx5")
        previous = -1
        for row in month:
            minute = int(row[0])
            if row[0] != minute or minute % MINUTE or minute <= previous or minute in found:
                raise ValueError("duplicate, unordered or non-minute Mark clock")
            observed = datetime.fromtimestamp(minute / 1000, UTC)
            if (observed.year, observed.month) != key:
                raise ValueError("partial Mark minute outside source month")
            o, h, low, close = (_decimal(x) for x in row[1:])
            if low <= 0 or h < max(o, low, close) or low > min(o, close):
                raise ValueError("invalid partial Mark OHLC")
            found[minute] = close
            previous = minute
    return found


def attribute_trade(trade: dict, events: list[dict], marks: dict[int, Decimal]) -> dict:
    """Attribute [entry, exit) settlements using the exact preceding closed minute.

    The nearest *available* minute is deliberately never substituted when the
    required minute is absent.  A proven official settlement Mark is accepted.
    """
    side = int(trade["side"])
    if side not in (-1, 1):
        raise ValueError("invalid signed side")
    quantity = _decimal(trade["quantity"])
    notional = _decimal(trade["entry_notional"])
    if quantity <= 0 or notional <= 0:
        raise ValueError("invalid quantity or notional")
    entry, exit_at = int(trade["entry_at"]), int(trade["exit_at"])
    if entry >= exit_at:
        raise ValueError("empty trade interval")
    rows = []
    known_cash = Decimal(0)
    previous_event = -1
    for event in events:
        at = int(event["settlement_at"])
        if at <= previous_event:
            raise ValueError("duplicate or unordered funding event")
        previous_event = at
        if not entry <= at < exit_at:
            continue
        rate = _decimal(event["rate"])
        required_minute = ((at - (MINUTE - 1)) // MINUTE) * MINUTE
        if required_minute < 0:
            raise ValueError("funding precedes any completed UTC minute")
        price = None
        basis = "UNKNOWN_REQUIRED_MARK"
        if event.get("mark_price") is not None:
            if event.get("mark_price_source_proven") is not True:
                raise ValueError("unproven funding settlement Mark")
            price = _decimal(event["mark_price"])
            basis = "PROVEN_PROVIDER_SETTLEMENT_MARK"
        elif required_minute in marks:
            price = marks[required_minute]
            basis = "AUTHENTICATED_EXACT_PRECEDING_1M_MARK_CLOSE_APPROXIMATION"
        elif rate == 0:
            # Zero signed rate proves zero cash, even without a notional Mark.
            basis = "ZERO_RATE_MARK_NOT_REQUIRED"
        if price is not None and price <= 0:
            raise ValueError("nonpositive settlement Mark")
        cash = -Decimal(side) * quantity * price * rate if price is not None else (Decimal(0) if rate == 0 else None)
        if cash is not None:
            known_cash += cash
        sign = "ZERO" if rate == 0 else ("DEBIT" if -side * rate < 0 else "CREDIT")
        rows.append({"settlement_at": at, "required_mark_minute": required_minute,
                     "required_mark_close_at": required_minute + MINUTE - 1,
                     "rate_fraction": str(rate), "rate_bps": str(rate * 10_000),
                     "mark_basis": basis, "mark_price": str(price) if price is not None else None,
                     "signed_cash_usdt": str(cash) if cash is not None else None,
                     "cash_sign_if_unknown": sign if cash is None else None})
    unknown = [row for row in rows if row["signed_cash_usdt"] is None]
    complete = not unknown
    net_before = _decimal(trade["net_usdt"])
    return {"event_id": trade["event_id"], "side": side, "entry_at": entry, "exit_at": exit_at,
            "year": datetime.fromtimestamp(entry / 1000, UTC).year,
            "quantity": str(quantity), "entry_notional": str(notional),
            "settlement_count": len(rows), "known_settlement_count": len(rows) - len(unknown),
            "unknown_settlement_count": len(unknown), "funding_status": "COMPLETE" if complete else "UNKNOWN_REQUIRED_MARK",
            "settlements": rows, "known_signed_cash_usdt": str(known_cash),
            "total_signed_cash_usdt": str(known_cash) if complete else None,
            "net_after_funding_bps": str(Decimal(10_000) * (net_before + known_cash) / notional) if complete else None,
            "unresolved_cash_bound": "UNBOUNDED_FROM_ADMITTED_SOURCE" if unknown else None}


def _summarize(trades: list[dict]) -> dict:
    total_events = sum(t["settlement_count"] for t in trades)
    known_events = sum(t["known_settlement_count"] for t in trades)
    covered = [t for t in trades if t["funding_status"] == "COMPLETE"]
    return {"trade_count": len(trades), "fully_covered_trade_count": len(covered),
            "trade_coverage_pct": 100 * len(covered) / len(trades) if trades else None,
            "settlement_pairs": total_events, "known_settlement_pairs": known_events,
            "event_coverage_pct": 100 * known_events / total_events if total_events else 100.0,
            "unknown_trade_ids": [t["event_id"] for t in trades if t["funding_status"] != "COMPLETE"],
            "unknown_event_pairs": [{"event_id": t["event_id"], "settlement_at": s["settlement_at"]}
                                    for t in trades for s in t["settlements"] if s["signed_cash_usdt"] is None],
            "known_signed_cash_usdt": str(sum((_decimal(t["known_signed_cash_usdt"]) for t in trades), Decimal(0))),
            "fully_covered_subset_mean_net_bps": str(sum((_decimal(t["net_after_funding_bps"]) for t in covered), Decimal(0)) / len(covered)) if covered else None,
            "full_period_after_funding_mean_net_bps": str(sum((_decimal(t["net_after_funding_bps"]) for t in covered), Decimal(0)) / len(trades)) if len(covered) == len(trades) and trades else None,
            "Mark_MTM_STATUS": "INCOMPLETE"}


def partial_study(candidates: list[dict], arrays: dict, funding: dict, output_dir: Path, source_receipt: dict) -> dict:
    """Measured funding coverage on frozen R2 trades, even when Mark is sparse.

    ``arrays['last']`` is dense Nx7 by month; ``arrays['mark']`` is sparse Nx5.
    The caller has already authenticated each input archive and pinned scope.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("partial output directory is a symlink")
    old = json.loads((OLD_EP / "REANALYSIS_R2_RESULTS.json").read_text())
    old_sources = json.loads((OLD_EP / "REANALYSIS_R2_SOURCE_RECEIPT.json").read_text())
    expected_sources = {(m["year"], m["month"]): m for m in old_sources["months"]}
    expected_months = {(year, month) for year in range(2021, 2024) for month in range(1, 13)}
    if set(arrays["last"]) != expected_months or set(funding) != expected_months:
        raise ValueError("complete 2021-2023 last and funding months required")
    source_last = set()
    for row in source_receipt["successful_sources"]:
        if row["kind"] == "last":
            key = row["year"], row["month"]
            if key in source_last or key not in expected_months or row["csv_sha256"] != expected_sources[key]["csv_sha256"]:
                raise ValueError("R2 last-price source identity changed")
            source_last.add(key)
    if source_last != expected_months:
        raise ValueError("R2 last-price source receipts incomplete")
    if {c["id"] for c in candidates} != set(IDS) or len(candidates) != 2:
        raise ValueError("partial study requires exactly two frozen candidates")
    marks = _mark_map(arrays["mark"])
    folds = get_monthly_folds()
    result = {"terminal": "R31_MARK_GAPS_REMAIN_FUNDING_PARTIAL_ONLY",
              "scientific_grade": "OBSERVED_FUNDING_PARTIAL_DEV_ONLY",
              "Mark_MTM_STATUS": "INCOMPLETE", "automatic_promotions": [],
              "source_manifest_sha256": source_receipt.get("source_manifest_sha256"),
              "candidates": {}}
    for candidate in candidates:
        cid = candidate["id"]
        signals_by_month = {}
        for fold in folds:
            key = (fold["year"], fold["month"])
            prev = (fold["prev_year"], fold["prev_month"])
            last = np.vstack([arrays["last"][prev], arrays["last"][key]])
            signals = generate_wave_signals(last, cid, fold["embargo_start_ms"], fold["embargo_end_ms"])
            signals_by_month[key] = eligible_events(signals, candidate, fold)[0]
        result["candidates"][cid] = {}
        for cost_name, cost in (("BASE", BASE), ("STRESS", STRESS)):
            cash = 1000.0
            baseline_bytes = bytearray()
            baseline_trades = []
            curves = []
            attributed = []
            for fold in folds:
                key = (fold["year"], fold["month"])
                prev = (fold["prev_year"], fold["prev_month"])
                last = np.vstack([arrays["last"][prev], arrays["last"][key]])
                rates = [*funding[prev], *funding[key]]
                signals = signals_by_month[key]
                lookup = {s["event_id"]: s for s in signals}
                booked = simulate_fold(last, signals, candidate, fold, cost, initial_equity=cash)
                cash = booked["ending_equity"]
                curves.append(booked["minute_equity_curve"])
                for trade in booked["trades"]:
                    control = matched_control(last, lookup[trade["event_id"]], candidate, cost, trade)
                    trade["control_net_bps"] = control["balanced_net_bps"]
                    trade["paired_increment_bps"] = control["paired_increment_bps"]
                    trade["pause_net_bps"] = 0.0
                    baseline_bytes.extend(canonical({"trade": trade, "event": lookup[trade["event_id"]], "control": control}))
                    baseline_trades.append(trade)
                    attributed.append(attribute_trade(trade, rates, marks))
            expected = old["candidates"][cid]["scenarios"][cost_name]
            baseline_sha = hashlib.sha256(baseline_bytes).hexdigest()
            if baseline_sha != expected["trade_ledger"]["sha256"]:
                raise ValueError("R2 full trade/event/control ledger identity mismatch")
            if len(baseline_trades) != expected["metrics"]["trade_count"]:
                raise ValueError("R2 baseline trade count mismatch")
            if hashlib.sha256(np.vstack(curves).tobytes()).hexdigest() != expected["minute_equity_ledger"]["uncompressed_curve_sha256"]:
                raise ValueError("R2 minute cash identity mismatch")
            path = output_dir / f"{cid}_{cost_name}_partial_funding.jsonl"
            path.write_bytes(b"".join(canonical(row) for row in attributed))
            groups: dict[str, list[dict]] = defaultdict(list)
            for row in attributed:
                groups[str(row["year"])].append(row)
                groups["LONG" if row["side"] == 1 else "SHORT"].append(row)
            result["candidates"][cid][cost_name] = {
                "R2_baseline_ledger_sha256_matched": baseline_sha,
                "baseline": expected["metrics"], "coverage": _summarize(attributed),
                "by_year": {year: _summarize(groups[year]) for year in ("2021", "2022", "2023")},
                "by_side": {side: _summarize(groups[side]) for side in ("LONG", "SHORT")},
                "attribution_ledger": {"path_outside_git": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(attributed)},
            }
    return result
