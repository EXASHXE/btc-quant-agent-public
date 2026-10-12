"""One bounded 27-cell development campaign. No validation/retuning mode."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import engine, metrics, portfolio, signals, sources


def dump(value):
    return json.loads(engine.canonical(value))


def run():
    began = time.perf_counter()
    started = datetime.now(UTC).isoformat()
    roster = sources.verify_freeze()
    manifest_path = sources.EVIDENCE / "PUBLIC_DEVELOPMENT_SOURCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["gate"] != "PASS_PUBLIC_TRADE_PRICE_ONLY" or len(manifest["records"]) != 24:
        raise ValueError("DATA_SOURCE_UNAVAILABLE_REQUIRED_FULL_COVERAGE")
    allowed = {(p["year"], p["month"]) for p in roster["authorized_archives"]}
    if {(r["year"], r["month"]) for r in manifest["records"]} != allowed:
        raise ValueError("SOURCE_SET_NOT_FROZEN")
    source_sha = sources.digest(manifest_path.read_bytes())
    folds = [
        {
            **f,
            "start_ms": int(datetime.fromisoformat(f["score_start"]).timestamp() * 1000),
            "end_ms": int(datetime.fromisoformat(f["score_end"]).timestamp() * 1000),
        }
        for f in roster["folds"]
    ]
    r2 = json.loads(
        (
            sources.ROOT / "evidence/v0.6/b_line/g2_btc_flow_regime_r2/FROZEN_R2_ROSTER.json"
        ).read_text()
    )
    books = []
    trades = []
    paired_records = []
    fates = []
    entry_counts = []
    entry_hashes = []
    out = sources.SCRATCH / "research-run"
    out.mkdir(exist_ok=True)
    for fold in folds:
        arrays = []
        for month in (fold["warmup_month"], fold["month"]):
            name = sources.authorize(fold["year"], month)
            record = next(
                r for r in manifest["records"] if (r["year"], r["month"]) == (fold["year"], month)
            )
            cache = sources.SCRATCH / f"validated-{fold['year']}-{month:02d}.npy"
            if sources.digest(cache.read_bytes()) != record["validated_npy_sha256"]:
                raise ValueError("VALIDATED_CACHE_HASH_MISMATCH")
            if sources.digest((sources.SCRATCH / name).read_bytes()) != record["zip_sha256"]:
                raise ValueError("RAW_ZIP_HASH_MISMATCH")
            arrays.append(np.load(cache, allow_pickle=False))
        data = np.concatenate(arrays)
        engine.validate_prices(data)
        all_events = signals.generate(data, r2)
        hourly = signals.hourly_features(data)
        eligible = {
            group: [
                ev
                for ev in events
                if fold["start_ms"] <= ev["entry_at"]
                and ev["entry_at"] + 24 * engine.HOUR + engine.MINUTE <= fold["end_ms"]
            ]
            for group, events in all_events.items()
        }
        for group, events in all_events.items():
            raw = engine.canonical(events)
            entry_hashes.append(
                {
                    "fold": fold["id"],
                    "entry": group,
                    "raw_events_sha256": hashlib.sha256(raw).hexdigest(),
                    "raw_signal_count": len(events),
                    "common_eligible_count": len(eligible[group]),
                }
            )
        entry_counts.append(
            {
                "fold": fold["id"],
                "generated": {g: len(v) for g, v in all_events.items()},
                "common_eligible": {g: len(v) for g, v in eligible.items()},
            }
        )
        episode_cache = {}
        for candidate in roster["candidates"]:
            for cost_name, cost in roster["costs"].items():
                book = portfolio.month(
                    data, all_events[candidate["entry"]], candidate, fold, cost, hourly
                )
                for trade in book["trades"]:
                    trade.update(cost_case=cost_name, entry_group=candidate["entry"])
                    trade["funding_sensitivity"] = portfolio.funding_sensitivity(data, trade)
                trades.extend(book["trades"])
                report = metrics.describe(book["trades"])
                report.update(
                    fold=fold["id"],
                    year=fold["year"],
                    candidate=candidate["id"],
                    cost_case=cost_name,
                    monthly_initial_USDT=1000,
                    month_return_pct=book["month_return_pct"],
                    ending_equity=book["ending_equity"],
                    dense_MTM_DD_pct=book["dense_MTM_DD_pct"],
                    closed_DD_pct=book["closed_DD_pct"],
                    waits=book["waits"],
                    generated_signals=len(all_events[candidate["entry"]]),
                    common_eligible_signals=len(eligible[candidate["entry"]]),
                    simulated_fill_failure_count=sum(
                        n
                        for reason, n in book["waits"].items()
                        if reason
                        not in (
                            "COMMON_24H_PLUS_ACK_FOLD_CUTOFF",
                            "POSITION_ACK_OR_COOLDOWN",
                            "RISK_DISABLED",
                        )
                    ),
                    sides={
                        label: metrics.describe([t for t in book["trades"] if t["side"] == side])
                        for label, side in [("LONG", 1), ("SHORT", -1)]
                    },
                )
                books.append(report)
                fates.extend(
                    [
                        {
                            **x,
                            "fold": fold["id"],
                            "candidate": candidate["id"],
                            "cost_case": cost_name,
                        }
                        for x in book["event_fates"]
                    ]
                )
                np.savez_compressed(
                    out / f"account-{fold['id']}-{candidate['id']}-{cost_name}.npz",
                    equity=book["curve"],
                    exposure=book["exposure"],
                    start_ms=fold["start_ms"],
                    step_ms=60000,
                )
                for ev in eligible[candidate["entry"]]:
                    key = (
                        candidate["entry"],
                        candidate["exit"],
                        candidate["cap_hours"],
                        cost_name,
                        ev["event_id"],
                    )
                    try:
                        qty = portfolio.size(data, ev, candidate, cost, 1000.0)
                        episode_cache[key] = engine.episode(
                            data,
                            ev,
                            candidate["exit"],
                            candidate["cap_hours"],
                            engine.Cost.from_dict(cost),
                            qty,
                            hourly,
                            validated=True,
                        )
                    except ValueError as exc:
                        episode_cache[key] = {"rejected": str(exc)}
        for candidate in [c for c in roster["candidates"] if c["exit"] != "X0"]:
            for cost_name in roster["costs"]:
                for ev in eligible[candidate["entry"]]:
                    baseline = episode_cache[
                        candidate["entry"], "X0", candidate["cap_hours"], cost_name, ev["event_id"]
                    ]
                    alternate = episode_cache[
                        candidate["entry"],
                        candidate["exit"],
                        candidate["cap_hours"],
                        cost_name,
                        ev["event_id"],
                    ]
                    if "rejected" in baseline or "rejected" in alternate:
                        paired_records.append(
                            {
                                "candidate": candidate["id"],
                                "cost_case": cost_name,
                                "fold": fold["id"],
                                "year": fold["year"],
                                "entry_at": ev["entry_at"],
                                "event_id": ev["event_id"],
                                "status": "PAIR_REFUSED",
                                "X0_reason": baseline.get("rejected"),
                                "candidate_reason": alternate.get("rejected"),
                            }
                        )
                    else:
                        assert baseline["initial_quantity"] == alternate["initial_quantity"]
                        paired_records.append(
                            {
                                "candidate": candidate["id"],
                                "cost_case": cost_name,
                                "fold": fold["id"],
                                "year": fold["year"],
                                "entry_at": ev["entry_at"],
                                "event_id": ev["event_id"],
                                "status": "MATCHED_FIXED_Q_UNFUNDED",
                                "net_bps": float(alternate["net_bps"] - baseline["net_bps"]),
                                "X0_net_bps": float(baseline["net_bps"]),
                                "candidate_net_bps": float(alternate["net_bps"]),
                                "X0_ledger_sha256": baseline["ledger_sha256"],
                                "candidate_ledger_sha256": alternate["ledger_sha256"],
                            }
                        )
        print(
            json.dumps(
                {
                    "completed_fold": fold["id"],
                    "eligible_entries": entry_counts[-1]["common_eligible"],
                    "portfolio_trades": sum(
                        b["completed_trades"] for b in books if b["fold"] == fold["id"]
                    ),
                }
            ),
            flush=True,
        )
    summaries = []
    pairs = []
    for candidate in roster["candidates"]:
        for cost_name in roster["costs"]:
            selected = [
                t
                for t in trades
                if t["candidate"] == candidate["id"] and t["cost_case"] == cost_name
            ]
            monthly = [
                b
                for b in books
                if b["candidate"] == candidate["id"] and b["cost_case"] == cost_name
            ]
            stat = metrics.describe(selected)
            year_rows = []
            for year in (2021, 2022, 2023):
                ys = metrics.describe([t for t in selected if t["year"] == year])
                months = [b for b in monthly if b["year"] == year]
                ys.update(
                    year=year,
                    mean_independent_month_account_return_pct=float(
                        np.mean([b["month_return_pct"] for b in months])
                    ),
                    active_months=sum(b["completed_trades"] > 0 for b in months),
                )
                year_rows.append(ys)
            represented = [y for y in year_rows if y["completed_trades"]]
            stat.update(
                candidate=candidate["id"],
                entry=candidate["entry"],
                exit=candidate["exit"],
                cap_hours=candidate["cap_hours"],
                cost_case=cost_name,
                years=year_rows,
                months=monthly,
                active_months=sum(b["completed_trades"] > 0 for b in monthly),
                equal_year_mean_net_bps=float(np.mean([y["mean_net_bps"] for y in represented]))
                if represented
                else None,
                max_closed_dense_MTM_DD_pct=max(
                    max(b["dense_MTM_DD_pct"], b["closed_DD_pct"]) for b in monthly
                ),
                sides={
                    label: metrics.describe([t for t in selected if t["side"] == side])
                    for label, side in [("LONG", 1), ("SHORT", -1)]
                },
                weekly_uncertainty=metrics.block_uncertainty(selected, folds),
                monthly_uncertainty=metrics.block_uncertainty(selected, folds, monthly=True),
            )
            pair = None
            if candidate["exit"] != "X0":
                matching = [
                    r
                    for r in paired_records
                    if r["candidate"] == candidate["id"]
                    and r["cost_case"] == cost_name
                    and r["status"] == "MATCHED_FIXED_Q_UNFUNDED"
                ]
                refused = [
                    r
                    for r in paired_records
                    if r["candidate"] == candidate["id"]
                    and r["cost_case"] == cost_name
                    and r["status"] == "PAIR_REFUSED"
                ]
                base_id = f"{candidate['entry']}_X0_H{candidate['cap_hours']:02d}"
                base_set = {
                    (t["fold"], t["event_id"])
                    for t in trades
                    if t["candidate"] == base_id and t["cost_case"] == cost_name
                }
                alt_set = {(t["fold"], t["event_id"]) for t in selected}
                n = len(matching)

                def tail(key, _matching=matching, _n=n):
                    return (
                        float(
                            np.mean(
                                sorted(r[key] for r in _matching)[: max(1, int(np.ceil(0.05 * _n)))]
                            )
                        )
                        if _n
                        else None
                    )

                pair = {
                    "candidate": candidate["id"],
                    "cost_case": cost_name,
                    "matched_entries": n,
                    "pair_refused": len(refused),
                    "mean_delta_bps": float(np.mean([r["net_bps"] for r in matching]))
                    if n
                    else None,
                    "tail5_candidate_bps": tail("candidate_net_bps"),
                    "tail5_X0_bps": tail("X0_net_bps"),
                    "weekly_uncertainty": metrics.block_uncertainty(matching, folds),
                    "monthly_uncertainty": metrics.block_uncertainty(matching, folds, monthly=True),
                    "actual_account_entry_intersection": len(base_set & alt_set),
                    "actual_account_only_X0": len(base_set - alt_set),
                    "actual_account_only_alternate": len(alt_set - base_set),
                    "accounts_have_different_sizing_cooldown_and_risk_fates": True,
                    "paired_episodes_are_unfunded_not_ROI": True,
                }
                pairs.append(pair)
            stat["gate_failures"] = (
                metrics.gate(stat, pair, candidate)
                if cost_name == "STRESS"
                else ["SELECTION_USES_STRESS_ONLY"]
            )
            stat["disposition"] = (
                "DEVELOPMENT_HYPOTHESIS_READY_FOR_FUTURE_VALIDATION"
                if not stat["gate_failures"]
                else "DEVELOPMENT_NO_GO"
            )
            if selected:
                stat["funding_sensitivity_mean_net_bps"] = {
                    f"{cadence}_{rate}bp": float(
                        np.mean(
                            [
                                float(t["net_bps"])
                                - float(
                                    t["funding_sensitivity"][cadence]["adverse_usdt"][str(rate)]
                                )
                                / float(t["entry_notional"])
                                * 10000
                                for t in selected
                            ]
                        )
                    )
                    for cadence, rates in [
                        ("UTC8H_PLUS_MINUS_15S", [4, 8]),
                        ("UNKNOWN_HOURLY", [8]),
                    ]
                    for rate in rates
                }
            else:
                stat["funding_sensitivity_mean_net_bps"] = {}
            summaries.append(stat)
    eligible = [s for s in summaries if s["cost_case"] == "STRESS" and not s["gate_failures"]]
    eligible.sort(
        key=lambda s: (
            -next(
                p["mean_delta_bps"]
                for p in pairs
                if p["candidate"] == s["candidate"] and p["cost_case"] == "STRESS"
            ),
            -s["mean_net_bps"],
            s["candidate"],
        )
    )
    top = [s["candidate"] for s in eligible[:3]]
    chosen = []
    seen = set()
    stress = sorted(
        [t for t in trades if t["cost_case"] == "STRESS"], key=lambda t: float(t["net_bps"])
    )
    for t in stress[:2] + list(reversed(stress[-2:])) + stress:
        identity = (t["fold"], t["event_id"])
        if identity not in seen:
            chosen.append(t)
            seen.add(identity)
        if len(chosen) == 5:
            break
    source_files = {
        str(p.relative_to(sources.ROOT)): sources.digest(p.read_bytes())
        for p in sorted(Path(__file__).parent.glob("*.py"))
    }
    result = {
        "schema": "R3_BOUNDED_27_CELL_DEVELOPMENT_V1",
        "task_id": roster["task_id"],
        "actual_agent_mode": "UNKNOWN",
        "base_sha": sources.BASE,
        "freeze_sha": sources.FREEZE,
        "freeze_push_receipt": manifest["freeze_push_receipt"],
        "source_manifest_sha256": source_sha,
        "code_sha256_at_execution": source_files,
        "started_utc": started,
        "finished_utc": datetime.now(UTC).isoformat(),
        "runtime_seconds": time.perf_counter() - began,
        "economic_hypotheses_executed": 27,
        "cost_scenarios_per_hypothesis": 2,
        "retunes": 0,
        "rows": summaries,
        "entry_counts": entry_counts,
        "frozen_entry_hashes": entry_hashes,
        "top3_eligible": top,
        "terminal": "R3_DEV_HYPOTHESIS_ELIGIBLE_FOR_FUTURE_INDEPENDENT_VALIDATION"
        if top
        else "R3_DEV_NO_GO",
        "pnl_label": "NET_EX_FUNDING_PROXY",
        "real_funding_mark_OI_depth": "UNKNOWN",
        "restricted_2024_25_reads": 0,
        "account_identity": "INDEPENDENT_1000_USDT_MONTH_BOOKS_NO_CONTINUOUS_YEAR_ROI",
        "sample_trades": chosen,
        "rights": roster["source_rights"],
        "trading_and_alpha_authority": "NONE",
    }
    for name, value in [
        ("DEVELOPMENT_RESULTS_BASE_STRESS.json", result),
        (
            "PAIRED_EXIT_DELTA_VS_X0.json",
            {
                "freeze_sha": sources.FREEZE,
                "source_manifest_sha256": source_sha,
                "rows": pairs,
                "matched_records_sha256": hashlib.sha256(
                    engine.canonical(paired_records)
                ).hexdigest(),
                "per_entry_records": "SCRATCH_ONLY",
                "paired_episodes_are_unfunded_not_ROI": True,
            },
        ),
        (
            "MULTIPLICITY_SUPPORT_NEGATIVE_REPORT.json",
            {
                "freeze_sha": sources.FREEZE,
                "source_manifest_sha256": source_sha,
                "family_count": 27,
                "resamples": 10000,
                "seed": 27182026,
                "method": "Bonferroni 27; UTC week primary/month sensitivity; empty eligible blocks included",
                "top3_eligible": top,
                "terminal": result["terminal"],
                "all_STRESS_dispositions": [
                    {
                        "candidate": s["candidate"],
                        "n": s["completed_trades"],
                        "gate_failures": s["gate_failures"],
                        "net_adjusted_p": s["weekly_uncertainty"]["Bonferroni27_p"],
                    }
                    for s in summaries
                    if s["cost_case"] == "STRESS"
                ],
            },
        ),
    ]:
        sources.write(name, dump(value))
    for name, records in [
        ("portfolio-trades.jsonl", trades),
        ("entry-fates.jsonl", fates),
        ("paired-episodes.jsonl", paired_records),
    ]:
        with (out / name).open("wb") as stream:
            for row in records:
                stream.write(engine.canonical(row) + b"\n")
    print(
        json.dumps(
            {
                "terminal": result["terminal"],
                "top3": top,
                "runtime_seconds": result["runtime_seconds"],
                "portfolio_completed_trades": len(trades),
            }
        ),
        flush=True,
    )
    return result


if __name__ == "__main__":
    run()
