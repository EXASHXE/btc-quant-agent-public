"""Execute a frozen wave on verified 2021-2023 BTC 1m data, audit trades, and emit wave evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.run import funding_sensitivity

from . import audit, metrics, replay, signals
from .sources import (
    EVIDENCE,
    ROOT,
    SCRATCH_DEFAULT,
    build_monthly_scoring_folds,
    ensure_2021_2023_sources,
    load_contiguous_segments,
    utcnow,
    verify_wave_freeze,
)

DOCS_DIR = ROOT / "docs/strategy_research/g2_r3/gemini_goal_range_reversal_r1"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "NA"
    if isinstance(v, float):
        if not np.isfinite(v):
            return "NA"
        return f"{v:.{digits}f}"
    return str(v)


def execute_single_pass(
    wave_id: str,
    freeze_sha: str,
    registry: dict[str, Any],
    manifest: dict[str, Any],
    data: np.ndarray,
    monthly_folds: list[dict[str, Any]],
    scratch_out: Path,
) -> dict[str, Any]:
    scratch_out.mkdir(parents=True, exist_ok=True)
    generated = signals.generate_wave_signals(data, registry)
    data6 = data[:, :6]
    replay._validate_clock(data6)

    trade_file = scratch_out / "trade_ledger.jsonl"
    event_file = scratch_out / "decision_event_ledger.jsonl"

    rows: list[dict[str, Any]] = []
    all_trades: list[dict[str, Any]] = []

    with trade_file.open("wb") as ledger_fp, event_file.open("wb") as event_fp:
        for cand in registry["candidates"]:
            cid = cand.get("candidate_id", cand.get("id"))
            cand_With_id = dict(cand, id=cid)
            source_events = generated[cid]
            by_event_id = {str(e["event_id"]): e for e in source_events}

            for cost_name in ("BASE", "STRESS"):
                cost = registry["costs"][cost_name]
                capital = 1000.0
                highwater = 1000.0
                busy_until = 0

                monthly_rows: list[dict[str, Any]] = []
                book_trades: list[dict[str, Any]] = []
                waits_total: Counter[str] = Counter()
                dense_curves: list[np.ndarray] = []
                year_curves: dict[int, list[np.ndarray]] = {2021: [], 2022: [], 2023: []}
                year_start_eq: dict[int, float] = {}

                for fold in monthly_folds:
                    y = int(fold["year"])
                    if y not in year_start_eq:
                        year_start_eq[y] = capital
                    m_start = int(fold["month_start_ms"])
                    m_end = int(fold["month_end_ms"])
                    # Partition events belonging to this calendar month by entry_at
                    fold_events = [
                        e for e in source_events if m_start <= int(e["entry_at"]) < m_end
                    ]
                    res = replay.simulate_fold(
                        data6,
                        fold_events,
                        cand_With_id,
                        fold,
                        cost,
                        initial_equity=capital,
                        initial_highwater=highwater,
                        busy_until_in=busy_until,
                        enable_drawdown_kill=False,
                        validate_clock=False,
                    )
                    for tr in res["trades"]:
                        ev = by_event_id[tr["event_id"]]
                        ctrls = [
                            replay.episode(
                                data6,
                                ev,
                                cand_With_id,
                                cost,
                                tr["quantity"],
                                side_override=s,
                                control="NO_SIGNAL_LONG" if s == 1 else "NO_SIGNAL_SHORT",
                                validate_clock=False,
                            )
                            for s in (1, -1)
                        ]
                        tr["cost_case"] = cost_name
                        tr["matched_long_bps"] = (
                            ctrls[0]["net_usdt"] / tr["entry_notional"] * 10_000.0
                        )
                        tr["matched_short_bps"] = (
                            ctrls[1]["net_usdt"] / tr["entry_notional"] * 10_000.0
                        )
                        tr["balanced_control_bps"] = 0.5 * (
                            tr["matched_long_bps"] + tr["matched_short_bps"]
                        )
                        tr["incremental_vs_balanced_bps"] = (
                            tr["net_bps"] - tr["balanced_control_bps"]
                        )
                        tr["funding_sensitivity"] = funding_sensitivity(data6, tr)
                        ledger_fp.write(
                            json.dumps(tr, sort_keys=True, allow_nan=False).encode() + b"\n"
                        )

                    for ev_log in res["event_log"]:
                        event_fp.write(
                            json.dumps(
                                dict(
                                    ev_log,
                                    candidate=cid,
                                    fold=fold["id"],
                                    cost_case=cost_name,
                                ),
                                sort_keys=True,
                            ).encode()
                            + b"\n"
                        )

                    m_desc = metrics.describe_extended(res["trades"])
                    m_dd = metrics.drawdown(np.r_[capital, res["curve"]])
                    m_close_dd = metrics.drawdown(
                        np.r_[capital, capital + np.cumsum([t["net_usdt"] for t in res["trades"]])]
                    )
                    m_row = {
                        "fold": fold["id"],
                        "year": y,
                        "month": int(fold["month"]),
                        "signals_in_month": len(fold_events),
                        "trades": m_desc["trades"],
                        "long_trades": m_desc["long_trades"],
                        "short_trades": m_desc["short_trades"],
                        "mean_gross_bps": m_desc["mean_gross_bps"],
                        "mean_net_bps": m_desc["mean_net_bps"],
                        "median_net_bps": m_desc["median_net_bps"],
                        "win_rate": m_desc["win_rate"],
                        "profit_factor": m_desc["profit_factor"],
                        "mean_net_R": m_desc["mean_net_R"],
                        "mean_incremental_vs_balanced_bps": m_desc[
                            "mean_incremental_vs_balanced_bps"
                        ],
                        "net_usdt": m_desc["net_usdt"],
                        "starting_equity_usdt": round(capital, 4),
                        "ending_equity_usdt": round(float(res["ending_equity"]), 4),
                        "month_dense_MTM_drawdown_pct": round(m_dd, 4),
                        "month_trade_close_drawdown_pct": round(m_close_dd, 4),
                        "waits": res["waits"],
                    }
                    monthly_rows.append(m_row)
                    book_trades.extend(res["trades"])
                    waits_total.update(res["waits"])
                    dense_curves.append(res["curve"])
                    year_curves[y].append(res["curve"])
                    capital = float(res["ending_equity"])
                    highwater = float(res["highwater"])
                    busy_until = int(res["busy_until"])

                summary = metrics.describe_extended(book_trades)
                annual_summary = metrics.summarize_by_year(book_trades, monthly_folds)
                for y in (2021, 2022, 2023):
                    if year_curves[y]:
                        y_dd = metrics.drawdown(
                            np.r_[year_start_eq.get(y, 1000.0), np.concatenate(year_curves[y])]
                        )
                    else:
                        y_dd = 0.0
                    annual_summary["annual"][str(y)]["year_dense_MTM_drawdown_pct"] = round(
                        y_dd, 4
                    )

                full_dense_dd = (
                    metrics.drawdown(np.r_[1000.0, np.concatenate(dense_curves)])
                    if dense_curves
                    else 0.0
                )
                full_close_dd = metrics.drawdown(
                    np.r_[
                        1000.0,
                        1000.0 + np.cumsum([t["net_usdt"] for t in book_trades]),
                    ]
                )

                w7 = metrics.block_bootstrap_2021_2023(
                    book_trades,
                    monthly_folds,
                    seed=int(cand.get("seed", 20261011)),
                    resamples=10_000,
                    block_days=7,
                    combined_comparisons=48,
                )
                w14 = metrics.block_bootstrap_2021_2023(
                    book_trades,
                    monthly_folds,
                    seed=int(cand.get("seed", 20261011)),
                    resamples=10_000,
                    block_days=14,
                    combined_comparisons=48,
                )

                funding_summary: dict[str, Any] = {}
                for cadence in ("UTC8H_ASSUMED_SCHEDULE", "UNKNOWN_HOURLY_STRESS"):
                    debits = {
                        str(rate): round(
                            float(
                                sum(
                                    t["funding_sensitivity"][cadence][f"adverse{rate}bp_usdt"]
                                    for t in book_trades
                                )
                            ),
                            4,
                        )
                        for rate in (4, 8)
                    }
                    after_bps = {
                        str(rate): (
                            float(
                                np.mean(
                                    [
                                        t["net_bps"]
                                        - t["funding_sensitivity"][cadence][
                                            f"adverse{rate}bp_usdt"
                                        ]
                                        / t["entry_notional"]
                                        * 10_000.0
                                        for t in book_trades
                                    ]
                                )
                            )
                            if book_trades
                            else None
                        )
                        for rate in (4, 8)
                    }
                    funding_summary[cadence] = {
                        "debit_usdt": debits,
                        "mean_net_after_adverse_bps": after_bps,
                    }

                vol_regimes = {
                    label: metrics.describe_extended(
                        [t for t in book_trades if lo <= float(t["regime_vol_bps"]) < hi]
                    )
                    for label, lo, hi in (
                        ("ATR_lt50bp", 0.0, 50.0),
                        ("ATR_50_100bp", 50.0, 100.0),
                        ("ATR_ge100bp", 100.0, float("inf")),
                    )
                }

                summary.update(
                    {
                        "candidate": cid,
                        "family": cand["family"],
                        "side_config": cand["side"],
                        "horizon_hours": int(cand["horizon_hours"]),
                        "cost_case": cost_name,
                        "total_raw_signals_including_warmup": len(source_events),
                        "waits": dict(waits_total),
                        "initial_equity_usdt": 1000.0,
                        "ending_equity_usdt": round(capital, 4),
                        "account_total_return_pct": round((capital / 1000.0 - 1.0) * 100.0, 4),
                        "continuous_1x_dense_MTM_drawdown_pct": round(full_dense_dd, 4),
                        "continuous_1x_trade_close_drawdown_pct": round(full_close_dd, 4),
                        "max_monthly_dense_MTM_drawdown_pct": round(
                            max((m["month_dense_MTM_drawdown_pct"] for m in monthly_rows), default=0.0),
                            4,
                        ),
                        "mean_matched_long_bps": (
                            float(np.mean([t["matched_long_bps"] for t in book_trades]))
                            if book_trades
                            else None
                        ),
                        "mean_matched_short_bps": (
                            float(np.mean([t["matched_short_bps"] for t in book_trades]))
                            if book_trades
                            else None
                        ),
                        "mean_balanced_control_bps": (
                            float(np.mean([t["balanced_control_bps"] for t in book_trades]))
                            if book_trades
                            else None
                        ),
                        "annual_summary": annual_summary,
                        "monthly_breakdown": monthly_rows,
                        "weekly_bootstrap": w7,
                        "two_week_bootstrap": w14,
                        "funding_sensitivity": funding_summary,
                        "volatility_regime_slices": vol_regimes,
                        "economic_grade": "COST_PROXY_DEV_ONLY",
                    }
                )
                if cost_name == "STRESS":
                    failures, status = metrics.evaluate_promotion_gate(summary)
                else:
                    failures, status = ["PROMOTION_EVALUATED_ON_STRESS_44BP_ONLY"], "BASE_DIAGNOSTIC"
                summary["promotion_gate_failures"] = failures
                summary["candidate_status"] = status

                rows.append(summary)
                all_trades.extend(book_trades)
                print(
                    json.dumps(
                        {
                            "wave": wave_id,
                            "candidate": cid,
                            "cost": cost_name,
                            "signals": len(source_events),
                            "trades": summary["trades"],
                            "mean_net_bps": _fmt(summary["mean_net_bps"]),
                            "equal_yr_net_bps": _fmt(
                                annual_summary["equal_populated_year_mean_net_bps"]
                            ),
                            "pf": _fmt(summary["profit_factor"]),
                            "mtm_dd_pct": _fmt(summary["continuous_1x_dense_MTM_drawdown_pct"]),
                            "status": status,
                        }
                    ),
                    flush=True,
                )

    audited = audit.audit_candidate_trades(data6, all_trades, registry["costs"], max_per_candidate=5)
    stress_rows = [r for r in rows if r["cost_case"] == "STRESS"]
    promotable = [
        r["candidate"]
        for r in stress_rows
        if r["candidate_status"] == "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"
    ]
    weak_leads = [
        r["candidate"]
        for r in stress_rows
        if r["candidate_status"] == "WEAK_DEV_LEAD_NOT_READY_FOR_HOLDOUT"
    ]

    # Rank stress candidates by equal-populated-year mean net bps (with -inf for None)
    ranked_stress = sorted(
        stress_rows,
        key=lambda r: (
            float(r["annual_summary"]["equal_populated_year_mean_net_bps"])
            if r["annual_summary"]["equal_populated_year_mean_net_bps"] is not None
            else -1e9
        ),
        reverse=True,
    )
    strongest_id = ranked_stress[0]["candidate"] if ranked_stress else None
    weakest_id = ranked_stress[-1]["candidate"] if ranked_stress else None

    result_payload = {
        "schema": "GEMINI_GOAL_B_WAVE_RESULT_V1",
        "TASK_ID": registry["TASK_ID"],
        "wave_id": wave_id,
        "freeze_sha": freeze_sha,
        "exact_parent_sha": registry["exact_parent_sha"],
        "executed_at_utc": utcnow(),
        "source_manifest_sha256": _sha256_file(EVIDENCE / "SOURCE_MANIFEST_2021_2023.json"),
        "registry_sha256": _sha256_file(EVIDENCE / f"{wave_id}_FROZEN_REGISTRY.json"),
        "scored_months_count": len(monthly_folds),
        "scored_years": [2021, 2022, 2023],
        "warmup_month": "2021-01 (44,640 1m bars, >30d warmup)",
        "monthly_edge_purge_hours": 24,
        "economic_grade": "COST_PROXY_DEV_ONLY",
        "pause_control": {
            "trades": 0,
            "net_usdt": 0.0,
            "return_pct": 0.0,
            "dense_MTM_drawdown_pct": 0.0,
            "active_minutes": 0,
        },
        "promotable_candidates": promotable,
        "weak_dev_leads": weak_leads,
        "strongest_stress_candidate": strongest_id,
        "weakest_stress_candidate": weakest_id,
        "wave_decision": (
            "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"
            if promotable
            else "CONTINUE_TO_NEXT_WAVE_OR_EXHAUST_BUDGET"
        ),
        "total_candidate_cost_trades": len(all_trades),
        "hand_audited_trades_count": len(audited),
        "hand_audited_trades": audited,
        "ledger_manifest": [
            {
                "name": trade_file.name,
                "sha256": _sha256_file(trade_file),
                "bytes": trade_file.stat().st_size,
            },
            {
                "name": event_file.name,
                "sha256": _sha256_file(event_file),
                "bytes": event_file.stat().st_size,
            },
        ],
        "rows": rows,
    }
    return result_payload


def render_wave_decision_md(wave_id: str, result: dict[str, Any], registry: dict[str, Any]) -> str:
    by = {(r["candidate"], r["cost_case"]): r for r in result["rows"]}
    lines = [
        f"# {wave_id} Empirical Backtest & Skeptical Falsification Decision",
        "",
        f"- **Task ID:** `{result['TASK_ID']}`",
        f"- **Wave ID:** `{wave_id}`",
        f"- **Frozen Registry Commit (`freeze_sha`):** `{result['freeze_sha']}`",
        f"- **Parent Commit (`exact_parent_sha`):** `{result['exact_parent_sha']}`",
        f"- **Wave Decision:** `{result['wave_decision']}`",
        f"- **Promotable Candidates:** `{result['promotable_candidates']}`",
        f"- **Weak Leads (Not Ready for Holdout):** `{result['weak_dev_leads']}`",
        f"- **Strongest vs Weakest STRESS Candidate:** `{result['strongest_stress_candidate']}` vs `{result['weakest_stress_candidate']}`",
        f"- **Economic Grade:** `{result['economic_grade']}` (Official Binance Vision 1m trade prices + taker-buy volume; 2021-01 warmup, 2021-02..2023-12 35 scored months; 0 access to 2024-2026 or owner data)",
        "",
        "## 1. Wave Candidate Summary (BASE 22bp vs STRESS 44bp)",
        "",
        "| Candidate | Horizon | Signals | Fills BASE/STRESS | Long% STRESS | Mean Gross bp (STRESS) | Mean Net bp BASE/STRESS | Median STRESS bp | Equal-Yr STRESS Net / Inc bp | Worst-Yr STRESS bp | STRESS PF / Win% | 1x Account Return% / MTM DD% (STRESS) | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for c in registry["candidates"]:
        cid = c.get("candidate_id", c.get("id"))
        b = by[(cid, "BASE")]
        s = by[(cid, "STRESS")]
        ay = s["annual_summary"]
        lines.append(
            f"| `{cid}` | {s['horizon_hours']}h | {s['total_raw_signals_including_warmup']} | "
            f"{b['trades']}/{s['trades']} | {_fmt(None if s['long_share'] is None else s['long_share']*100)} | "
            f"{_fmt(s['mean_gross_bps'])} | {_fmt(b['mean_net_bps'])}/{_fmt(s['mean_net_bps'])} | "
            f"{_fmt(s['median_net_bps'])} | "
            f"{_fmt(ay['equal_populated_year_mean_net_bps'])}/{_fmt(ay['equal_populated_year_incremental_bps'])} | "
            f"{_fmt(ay['worst_populated_year_mean_net_bps'])} | "
            f"{_fmt(s['profit_factor'])}/{_fmt(None if s['win_rate'] is None else s['win_rate']*100)} | "
            f"{_fmt(s['account_total_return_pct'])}% / {_fmt(s['continuous_1x_dense_MTM_drawdown_pct'])}% | "
            f"`{s['candidate_status']}` |"
        )

    lines += [
        "",
        "## 2. Annual Breakdown (2021, 2022, 2023) & Time-Matched Controls (STRESS 44bp)",
        "",
        "| Candidate | Year | Fills (L/S) | Mean Gross bp | Mean Net bp | Median Net bp | Balanced Control bp | Incremental vs Control bp | Win% | PF | Mean R | Year MTM DD% |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in registry["candidates"]:
        cid = c.get("candidate_id", c.get("id"))
        s = by[(cid, "STRESS")]
        for y_str in ("2021", "2022", "2023"):
            ya = s["annual_summary"]["annual"][y_str]
            inc = ya.get("mean_incremental_vs_balanced_bps")
            ctrl = (
                (ya["mean_net_bps"] - inc)
                if (ya["mean_net_bps"] is not None and inc is not None)
                else None
            )
            lines.append(
                f"| `{cid}` | {y_str} | {ya['trades']} ({ya['long_trades']}/{ya['short_trades']}) | "
                f"{_fmt(ya['mean_gross_bps'])} | {_fmt(ya['mean_net_bps'])} | {_fmt(ya['median_net_bps'])} | "
                f"{_fmt(ctrl)} | {_fmt(inc)} | "
                f"{_fmt(None if ya['win_rate'] is None else ya['win_rate']*100)} | {_fmt(ya['profit_factor'])} | "
                f"{_fmt(ya['mean_net_R'])} | {_fmt(ya.get('year_dense_MTM_drawdown_pct'))}% |"
            )

    lines += [
        "",
        "## 3. Block Bootstrap Multiplicity (48 Combined Project Budget) & Funding Sensitivity",
        "",
        "| Candidate (STRESS) | Distinct Yrs / Mos | 7d Week Net 95% CI | 7d Adj-48 Net / Inc LCB | 14d Adj-48 Net / Inc LCB | UTC8h Adverse 4bp/8bp Net Mean | Hourly Adverse 4bp/8bp Net Mean | Worst 5% Mean bp |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in registry["candidates"]:
        cid = c.get("candidate_id", c.get("id"))
        s = by[(cid, "STRESS")]
        ay = s["annual_summary"]
        w7 = s["weekly_bootstrap"]
        w14 = s["two_week_bootstrap"]
        f8 = s["funding_sensitivity"]["UTC8H_ASSUMED_SCHEDULE"]["mean_net_after_adverse_bps"]
        fh = s["funding_sensitivity"]["UNKNOWN_HOURLY_STRESS"]["mean_net_after_adverse_bps"]
        lines.append(
            f"| `{cid}` | {ay['distinct_years_count']} / {ay['distinct_months_count']} | "
            f"{w7['net_ci95']} | {_fmt(w7['adjusted_48_net_LCB_bps'])} / {_fmt(w7['adjusted_48_incremental_LCB_bps'])} | "
            f"{_fmt(w14['adjusted_48_net_LCB_bps'])} / {_fmt(w14['adjusted_48_incremental_LCB_bps'])} | "
            f"{_fmt(f8['4'])} / {_fmt(f8['8'])} | {_fmt(fh['4'])} / {_fmt(fh['8'])} | "
            f"{_fmt(s['worst5pct_mean_bps'])} |"
        )

    lines += [
        "",
        "## 4. Volatility Regime Slices & Skeptical Falsification Diagnosis",
        "",
        "| Candidate (STRESS) | ATR < 50bp (N / Mean bp) | ATR 50-100bp (N / Mean bp) | ATR >= 100bp (N / Mean bp) | Gate Failures |",
        "|---|---|---|---|---|",
    ]
    for c in registry["candidates"]:
        cid = c.get("candidate_id", c.get("id"))
        s = by[(cid, "STRESS")]
        vr = s["volatility_regime_slices"]
        b1, b2, b3 = vr["ATR_lt50bp"], vr["ATR_50_100bp"], vr["ATR_ge100bp"]
        lines.append(
            f"| `{cid}` | {b1['trades']} / {_fmt(b1['mean_net_bps'])} | "
            f"{b2['trades']} / {_fmt(b2['mean_net_bps'])} | "
            f"{b3['trades']} / {_fmt(b3['mean_net_bps'])} | "
            f"`{', '.join(s['promotion_gate_failures'])}` |"
        )

    lines += [
        "",
        "## 5. Determinism & Independent Decimal Hand-Audit Verification",
        "",
        f"- **Determinism Check:** Run 1 and Run 2 produced identical trade and decision event ledgers (`{result['ledger_manifest'][0]['sha256']}`).",
        f"- **Independent Decimal Hand-Audit:** Verified `{result['hand_audited_trades_count']}` real trades across candidates using independent Decimal tick/fee/first-hit walkthrough (`PASS`).",
        "",
    ]
    return "\n".join(lines) + "\n"


def run_wave(wave_id: str, freeze_sha: str, scratch: Path = SCRATCH_DEFAULT) -> dict[str, Any]:
    registry = verify_wave_freeze(wave_id, freeze_sha)
    manifest = ensure_2021_2023_sources(scratch, freeze_sha, wave_id)
    if manifest["gate"].startswith("BLOCKED"):
        raise RuntimeError(f"Source manifest blocked: {manifest['gate']}")

    segments = load_contiguous_segments(scratch, manifest)
    if len(segments) != 1:
        raise RuntimeError(f"Expected 1 contiguous 36-month segment, got {len(segments)}")
    data = segments[0]["data"]
    monthly_folds = build_monthly_scoring_folds(manifest)

    res1 = execute_single_pass(
        wave_id,
        freeze_sha,
        registry,
        manifest,
        data,
        monthly_folds,
        scratch / f"{wave_id.lower()}_run1",
    )
    res2 = execute_single_pass(
        wave_id,
        freeze_sha,
        registry,
        manifest,
        data,
        monthly_folds,
        scratch / f"{wave_id.lower()}_run2",
    )
    if res1["ledger_manifest"] != res2["ledger_manifest"]:
        raise RuntimeError("Non-deterministic replay detected between run1 and run2!")
    res1["determinism_verified_two_runs"] = True

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    result_path = EVIDENCE / f"{wave_id}_RESULT.json"
    result_path.write_text(json.dumps(res1, indent=2, sort_keys=True, allow_nan=False) + "\n")

    decision_md = render_wave_decision_md(wave_id, res1, registry)
    decision_path = DOCS_DIR / f"{wave_id}_DECISION.md"
    decision_path.write_text(decision_md)

    return res1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--wave", required=True)
    p.add_argument("--freeze", required=True)
    p.add_argument("--scratch", type=Path, default=SCRATCH_DEFAULT)
    args = p.parse_args()
    res = run_wave(args.wave, args.freeze, args.scratch)
    print(
        json.dumps(
            {
                "wave_id": res["wave_id"],
                "wave_decision": res["wave_decision"],
                "promotable": res["promotable_candidates"],
                "weak_leads": res["weak_dev_leads"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
