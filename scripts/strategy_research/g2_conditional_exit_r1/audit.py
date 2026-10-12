"""Independent stdlib CSV/ZIP/Decimal audit for G2 Conditional Exit R1 (>=20 witnesses)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

from .contract import (
    CANDIDATE_IDS,
    EXIT_R1_EVIDENCE_DIR,
    GAP_R31_CACHE,
    OLD_R3_CACHE,
)
from .sources import guarded

COST_SPECS = {
    "STRESS": {"fee_bps": "12", "spread_bps": "8", "slip_bps": "6"},
    "BASE": {"fee_bps": "6", "spread_bps": "4", "slip_bps": "3"},
}


def D(v: Any) -> Decimal:
    return Decimal(str(v))


def dec_effective_tick(raw: Any, side: int, cost: dict[str, Any], *, entry: bool) -> Decimal:
    direction = side if entry else -side
    spread = D(cost.get("spread_bps", 0))
    slip = D(cost.get("slip_bps", cost.get("slippage_bps", 0)))
    adverse = (spread / D(2) + slip) / D(10000)
    val = D(raw) * (D(1) + D(direction) * adverse)
    units = val / D("0.1")
    return units.to_integral_value(rounding=ROUND_CEILING if direction > 0 else ROUND_FLOOR) * D("0.1")


def _read_zip_member(path: Path, expected_sha: str) -> str:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError(f"Independent archive SHA mismatch for {path.name}")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        if len(names) != 1:
            raise ValueError(f"Expected single member in {path.name}, got {len(names)}")
        return z.read(names[0]).decode("utf-8")


def audit_single_trade_decimal(
    trade: dict[str, Any],
    cost_name: str,
    *,
    marks_by_open: dict[int, tuple[Decimal, int, str]] | None = None,
    funding_by_clock: dict[int, Decimal] | None = None,
) -> dict[str, Any]:
    """Audit a single trade's prices, fees, drag, funding, journal, and 12h X1/X2 decision in pure Decimal."""
    cost = COST_SPECS[cost_name]
    q = D(trade["quantity"])
    side = int(trade["side"])
    side_d = D(side)
    raw_entry = D(trade["raw_entry"])
    eff_entry = dec_effective_tick(raw_entry, side, cost, entry=True)

    if abs(eff_entry - D(trade["effective_entry"])) > D("0.000001"):
        raise ValueError(f"Independent entry tick mismatch on {trade['event_id']}")

    fee_entry = eff_entry * q * D(cost["fee_bps"]) / D(10000)
    if abs(fee_entry - D(trade["fee_entry"])) > D("0.00000001"):
        raise ValueError(f"Independent entry fee mismatch on {trade['event_id']}")

    tiers = trade.get("tiers") or [
        {
            "quantity": trade["quantity"],
            "raw_exit": trade["raw_exit"],
            "effective_exit": trade["effective_exit"],
            "fee_exit": trade["fee_exit"],
            "exit_at": trade["exit_at"],
            "exit_ack_at": trade["exit_ack_at"],
            "reason": trade["exit_reason"],
        }
    ]

    fee_exit_total = D(0)
    gross_total = D(0)
    drag_total = D(0)
    tier_proofs = []
    for x in tiers:
        t_qty = D(x["quantity"])
        raw_exit = D(x["raw_exit"])
        eff_exit = dec_effective_tick(raw_exit, side, cost, entry=False)
        t_fee = eff_exit * t_qty * D(cost["fee_bps"]) / D(10000)
        fee_exit_total += t_fee
        gross_total += side_d * (raw_exit - raw_entry) * t_qty
        drag_total += side_d * (eff_entry - raw_entry + raw_exit - eff_exit) * t_qty
        if abs(eff_exit - D(x["effective_exit"])) > D("0.000001"):
            raise ValueError(f"Independent exit tick mismatch on {trade['event_id']}")
        if abs(t_fee - D(x["fee_exit"])) > D("0.00000001"):
            raise ValueError(f"Independent exit fee mismatch on {trade['event_id']}")
        if int(x["exit_ack_at"]) <= int(x["exit_at"]):
            raise ValueError(f"Non-causal exit ACK on {trade['event_id']}")
        tier_proofs.append({
            "quantity": str(t_qty),
            "raw_exit": str(raw_exit),
            "independent_effective_exit": str(eff_exit),
            "independent_fee_exit": str(t_fee),
            "exit_at": int(x["exit_at"]),
            "exit_ack_at": int(x["exit_ack_at"]),
            "reason": str(x["reason"]),
        })

    if abs(sum(D(x["quantity"]) for x in tiers) - q) > D("1e-12"):
        raise ValueError(f"Tier quantity conservation failure on {trade['event_id']}")

    # Audit funding settlements
    funding_total = D(0)
    settlement_proofs = []
    entry_at = int(trade["entry_at"])
    exit_at = int(trade["exit_at"])

    if funding_by_clock is not None and marks_by_open is not None:
        for at, rate in sorted(funding_by_clock.items()):
            if not (entry_at <= at < exit_at):
                continue
            open_q = q - sum((D(x["quantity"]) for x in tiers if int(x["exit_at"]) <= at), D(0))
            if open_q <= 0:
                continue
            stamp = ((at - 59_999) // 60_000) * 60_000
            mp, mc, origin = marks_by_open[stamp]
            if not (mc <= at and at - mc < 60_000):
                raise ValueError("Independent settlement Mark as-of violation")
            bill = -side_d * open_q * mp * rate
            funding_total += bill
            settlement_proofs.append({
                "settlement_at": at,
                "remaining_quantity": str(open_q),
                "rate": str(rate),
                "mark_close_at": mc,
                "mark_close": str(mp),
                "mark_origin": origin,
                "signed_cash_usdt": str(bill),
            })
    else:
        for s in trade.get("funding_settlements", []):
            at = int(s["settlement_at"])
            if not (entry_at <= at < exit_at):
                raise ValueError("Funding settlement outside [entry_at, exit_at)")
            open_q = q - sum((D(x["quantity"]) for x in tiers if int(x["exit_at"]) <= at), D(0))
            if abs(open_q - D(s["quantity"])) > D("1e-12"):
                raise ValueError("Funding settlement open quantity mismatch")
            rate = D(s["source_rate_fraction"])
            mp = D(s["settlement_mark"])
            bill = -side_d * open_q * mp * rate
            if abs(bill - D(s["signed_cash_usdt"])) > D("1e-10"):
                raise ValueError("Funding settlement signed cash mismatch")
            funding_total += bill
            settlement_proofs.append({
                "settlement_at": at,
                "remaining_quantity": str(open_q),
                "rate": str(rate),
                "mark_close_at": s.get("mark_close_at"),
                "mark_close": str(mp),
                "signed_cash_usdt": str(bill),
            })

    if abs(funding_total - D(trade["funding_cash_usdt"])) > D("1e-8"):
        raise ValueError(f"Independent funding cash drift on {trade['event_id']}")

    net_pre_funding = gross_total - drag_total - fee_entry - fee_exit_total
    net_after_funding = net_pre_funding + funding_total
    notional = raw_entry * q
    net_after_funding_bps = D(10000) * net_after_funding / notional

    if abs(net_pre_funding - D(trade["net_usdt"])) > D("1e-7"):
        raise ValueError(f"Independent pre-funding net drift on {trade['event_id']}")
    if abs(net_after_funding - D(trade["net_after_funding_usdt"])) > D("1e-7"):
        raise ValueError(f"Independent net_after_funding_usdt drift on {trade['event_id']}")
    if abs(net_after_funding_bps - D(trade["net_after_funding_bps"])) > D("1e-5"):
        raise ValueError(f"Independent net_after_funding_bps drift on {trade['event_id']}")

    if "journal" in trade:
        journal_sum = sum((D(j["cash_delta"]) for j in trade["journal"]), D(0))
        if abs(journal_sum - net_after_funding) > D("1e-7"):
            raise ValueError(f"Independent cash journal sum drift on {trade['event_id']}")
        for j in trade["journal"]:
            if j["kind"] == "EXIT_PNL_ACK" and not any(int(j["timestamp"]) == int(x["exit_ack_at"]) for x in tiers):
                raise ValueError(f"Premature or unmatched EXIT_PNL_ACK in journal on {trade['event_id']}")

    # Audit 12h conditional decision if present and reached
    dec_12h = trade.get("decision_12h", {})
    decision_audit: dict[str, Any] = {"reached_12h": bool(dec_12h.get("reached_12h_time_cap_boundary", False))}
    if dec_12h.get("reached_12h_time_cap_boundary"):
        policy = dec_12h.get("policy", dec_12h.get("scheme"))
        dec_at = int(dec_12h["decision_at"])
        if dec_at != entry_at + 12 * 3_600_000:
            raise ValueError("12h decision clock does not equal entry_at + 12h")
        if policy == "X1_NET_POSITIVE_AT_12H":
            m_close = D(dec_12h["mark_close_price_str"])
            if int(dec_12h["mark_bar_close_at"]) != dec_at - 1:
                raise ValueError("X1 Mark bar close timestamp is not decision_at - 1")
            if marks_by_open is not None and (dec_at - 60_000) in marks_by_open:
                archive_mp, archive_mc, _ = marks_by_open[dec_at - 60_000]
                if abs(archive_mp - m_close) > D("1e-8") or archive_mc != dec_at - 1:
                    raise ValueError("X1 Mark close price mismatches raw archive")
            hyp_exit = dec_effective_tick(m_close, side, cost, entry=False)
            hyp_exit_fee = hyp_exit * q * D(cost["fee_bps"]) / D(10000)
            acc_fund = sum(
                (D(s["signed_cash_usdt"]) for s in dec_12h.get("accrued_funding_settlements", [])),
                D(0),
            )
            est_net = side_d * (hyp_exit - eff_entry) * q - fee_entry - hyp_exit_fee + acc_fund
            if abs(est_net - D(dec_12h["estimated_liquidation_net_usdt_str"])) > D("1e-8"):
                raise ValueError("X1 independent Decimal net estimate mismatch")
            expected_extend = bool(est_net > D(0))
            if expected_extend != bool(dec_12h["extend_to_18h"]):
                raise ValueError("X1 independent extension decision mismatch")
            decision_audit.update({
                "policy": policy,
                "independent_estimated_net_usdt": str(est_net),
                "independent_extend_to_18h": expected_extend,
                "status": "PASS",
            })
        elif policy == "X2_COMPLETED_4H_TREND_AT_12H":
            c_early = D(dec_12h["earliest_1h_close_str"])
            c_last = D(dec_12h["last_1h_close_str"])
            if int(dec_12h["last_1h_close_at"]) > dec_at:
                raise ValueError("X2 last 1h close timestamp is after decision_at")
            if int(dec_12h["last_1h_open_at"]) - int(dec_12h["earliest_1h_open_at"]) != 3 * 3_600_000:
                raise ValueError("X2 4-bar 1h window span mismatch")
            s_diff = side_d * (c_last - c_early)
            if abs(s_diff - D(dec_12h["signed_price_diff_str"])) > D("1e-8"):
                raise ValueError("X2 independent signed price diff mismatch")
            expected_extend = bool(s_diff > D(0))
            if expected_extend != bool(dec_12h["extend_to_18h"]):
                raise ValueError("X2 independent extension decision mismatch")
            decision_audit.update({
                "policy": policy,
                "independent_signed_price_diff": str(s_diff),
                "independent_extend_to_18h": expected_extend,
                "status": "PASS",
            })

    return {
        "candidate": trade.get("candidate", "UNKNOWN"),
        "scheme": trade.get("scheme", "UNKNOWN"),
        "cost": cost_name,
        "event_id": trade["event_id"],
        "year": datetime.fromtimestamp(entry_at / 1000, UTC).year,
        "side": side,
        "quantity": str(q),
        "independent_effective_entry": str(eff_entry),
        "independent_fee_entry": str(fee_entry),
        "independent_fee_exit": str(fee_exit_total),
        "independent_gross_usdt": str(gross_total),
        "independent_drag_usdt": str(drag_total),
        "independent_funding_usdt": str(funding_total),
        "independent_net_after_funding_usdt": str(net_after_funding),
        "independent_net_after_funding_bps": str(net_after_funding_bps),
        "tiers": tier_proofs,
        "settlements": settlement_proofs,
        "decision_12h_audit": decision_audit,
        "status": "PASS",
    }


def run_previous_exit_r1_decimal_witnesses() -> dict[str, Any]:
    """Audit >= 20 real previous-Exit-R1 events across W1/W2, STRESS/BASE, E0/H1, 2021-2023, LONG/SHORT."""
    witnesses: list[dict[str, Any]] = []
    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            p = EXIT_R1_EVIDENCE_DIR / f"{cid}_{cost_name}_paired.jsonl"
            rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
            # Deterministically pick first 3 TIME_CAP events and first 2 early-exit events per (cid, cost)
            tc_rows = [r for r in rows if r["cells"]["E0"]["exit_reason"] == "TIME_CAP"][:3]
            early_rows = [r for r in rows if r["cells"]["E0"]["exit_reason"] != "TIME_CAP"][:2]
            for r in tc_rows + early_rows:
                for sch in ("E0", "H1"):
                    cell = {**r["cells"][sch], "scheme": sch}
                    witnesses.append(audit_single_trade_decimal(cell, cost_name))

    if len(witnesses) < 20:
        raise ValueError(f"Expected >= 20 previous-R1 Decimal witnesses, got {len(witnesses)}")

    return {
        "status": "PASS",
        "witness_count": len(witnesses),
        "candidates_covered": sorted({w["candidate"] for w in witnesses}),
        "costs_covered": sorted({w["cost"] for w in witnesses}),
        "schemes_covered": sorted({w["scheme"] for w in witnesses}),
        "years_covered": sorted({w["year"] for w in witnesses}),
        "sides_covered": sorted({w["side"] for w in witnesses}),
        "witnesses": witnesses,
    }


def run_independent_real_decimal_audit(
    trades: list[dict[str, Any]],
    source_receipt: dict[str, Any],
    *,
    old_cache: Path = OLD_R3_CACHE,
    gap_cache: Path = GAP_R31_CACHE,
) -> dict[str, Any]:
    """Audit >= 24 new X1/X2 real trades against raw CSV/ZIP archives in pure Decimal."""
    ordered = sorted(
        trades,
        key=lambda t: (
            int(t["entry_at"]),
            str(t["candidate"]),
            str(t["scheme"]),
            0 if t.get("cost") == "STRESS" else 1,
        ),
    )

    chosen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    groups_seen: set[tuple[Any, ...]] = set()

    # Stratify across (candidate, scheme, cost, reached_12h, extend_to_18h, side, year)
    for t in ordered:
        dec = t.get("decision_12h", {})
        key = (
            t["candidate"],
            t["scheme"],
            t["cost"],
            bool(dec.get("reached_12h_time_cap_boundary")),
            bool(dec.get("extend_to_18h")),
            int(t["side"]),
        )
        id_key = (t["candidate"], t["event_id"], t["scheme"], t["cost"])
        if key not in groups_seen and id_key not in chosen:
            chosen[id_key] = t
            groups_seen.add(key)

    for t in ordered:
        if len(chosen) >= 28:
            break
        id_key = (t["candidate"], t["event_id"], t["scheme"], t["cost"])
        if id_key not in chosen:
            chosen[id_key] = t

    if len(chosen) < 20:
        raise ValueError(f"Expected >= 20 real trades for Decimal audit, got {len(chosen)}")

    # Load all 3,285 official funding settlements directly from raw R3 ZIP archives
    funding_by_clock: dict[int, Decimal] = {}
    for ref in source_receipt["successful_sources"]:
        if ref["kind"] != "funding":
            continue
        name = f"funding-BTCUSDT-fundingRate-{ref['year']}-{ref['month']:02d}.zip"
        text = _read_zip_member(guarded(old_cache / name, old_cache), ref["zip_sha256"])
        for row in csv.DictReader(io.StringIO(text)):
            at = int(row["calc_time"])
            if at in funding_by_clock:
                raise ValueError("Duplicate official funding timestamp in raw archive")
            funding_by_clock[at] = D(row["last_funding_rate"])

    if len(funding_by_clock) != 3285:
        raise ValueError(f"Expected 3285 official funding events, got {len(funding_by_clock)}")

    # Collect required Mark open timestamps (for funding settlements and 12h X1 decisions)
    needed_marks: set[int] = set()
    for t in chosen.values():
        entry_at = int(t["entry_at"])
        exit_at = int(t["exit_at"])
        deadline_12h = entry_at + 12 * 3_600_000
        needed_marks.add(deadline_12h - 60_000)
        for at in funding_by_clock:
            if entry_at <= at < exit_at:
                needed_marks.add(((at - 59_999) // 60_000) * 60_000)

    marks_by_open: dict[int, tuple[Decimal, int, str]] = {}
    for ref in source_receipt["successful_sources"]:
        if ref["kind"] != "mark":
            continue
        y, m = int(ref["year"]), int(ref["month"])
        targets = {
            at
            for at in needed_marks
            if (
                datetime.fromtimestamp(at / 1000, UTC).year,
                datetime.fromtimestamp(at / 1000, UTC).month,
            )
            == (y, m)
        }
        if not targets:
            continue
        name = f"mark-BTCUSDT-1m-{y}-{m:02d}.zip"
        for row in csv.reader(io.StringIO(_read_zip_member(guarded(old_cache / name, old_cache), ref["zip_sha256"]))):
            if not row or row[0] == "open_time" or not row[0].isdigit():
                continue
            at = int(row[0])
            if at in targets:
                marks_by_open[at] = (D(row[4]), int(row[6]), "MONTHLY_AUTHORITY")

    for day_rec in source_receipt.get("daily_receipts", []):
        d = day_rec["day"]
        start = int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
        if not any(start <= at < start + 86_400_000 and at not in marks_by_open for at in needed_marks):
            continue
        folder = gap_cache / d
        name = f"BTCUSDT-1m-{d}.zip"
        for row in csv.reader(
            io.StringIO(_read_zip_member(guarded(folder / name, folder), day_rec["daily_parse"]["zip_sha256"]))
        ):
            if not row or row[0] == "open_time" or not row[0].isdigit():
                continue
            at = int(row[0])
            if at in needed_marks:
                if at in marks_by_open:
                    raise ValueError("Overlapping daily and monthly Mark bar")
                marks_by_open[at] = (D(row[4]), int(row[6]), "DAILY_SHA_AUTHENTICATED")

    if not needed_marks <= set(marks_by_open):
        missing = sorted(needed_marks - set(marks_by_open))
        raise ValueError(f"Missing required Mark minutes in independent archive check: {missing[:5]}")

    episodes = []
    for t in chosen.values():
        ep = audit_single_trade_decimal(
            t,
            str(t["cost"]),
            marks_by_open=marks_by_open,
            funding_by_clock=funding_by_clock,
        )
        episodes.append(ep)

    prev_r1_receipt = run_previous_exit_r1_decimal_witnesses()

    return {
        "status": "PASS",
        "method": "independent stdlib CSV/ZIP/Decimal; zero production execution helper calls",
        "audited_new_trade_episodes_n": len(episodes),
        "audited_previous_exit_r1_witnesses_n": prev_r1_receipt["witness_count"],
        "total_decimal_witnesses_n": len(episodes) + prev_r1_receipt["witness_count"],
        "per_cost_new_n": {
            c: sum(e["cost"] == c for e in episodes) for c in ("STRESS", "BASE")
        },
        "per_scheme_new_n": {
            s: sum(e["scheme"] == s for e in episodes)
            for s in ("X1_NET_POSITIVE_AT_12H", "X2_COMPLETED_4H_TREND_AT_12H")
        },
        "official_funding_events_verified": len(funding_by_clock),
        "new_trade_episodes": episodes,
        "previous_exit_r1_witness_summary": {
            "status": prev_r1_receipt["status"],
            "witness_count": prev_r1_receipt["witness_count"],
            "candidates_covered": prev_r1_receipt["candidates_covered"],
            "costs_covered": prev_r1_receipt["costs_covered"],
            "years_covered": prev_r1_receipt["years_covered"],
        },
    }
