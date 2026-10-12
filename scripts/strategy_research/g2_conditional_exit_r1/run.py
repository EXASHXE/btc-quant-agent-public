"""One-shot execution pipeline for Gemini Goal B — Causal Conditional 12h->18h Exit Study R1."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import run as prior_r3
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import (
    canonical,
    eligible_events,
    verify_identity,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import BASE, STRESS
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.signals import generate_wave_signals
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.sources import get_monthly_folds

from .account import PROSPECTIVE_HORIZON_HOURS, path_eligible, replay_fold
from .audit import run_independent_real_decimal_audit
from .conditional_book import PartialIneligibleError, execute_conditional_position
from .contract import (
    ALL_SCHEMES,
    BRANCH,
    CANDIDATE_IDS,
    CONDITIONAL_SCHEMES,
    CONTROLLER_AUTHORITY,
    CONTROLLER_DISPATCH_SHA,
    EVIDENCE_DIR,
    EXACT_START_SHA,
    EXPECTED_ORIGINAL_EVENTS,
    EXPECTED_ORIGINAL_H1_MINUS_E0_STRESS_BPS,
    EXPECTED_ORIGINAL_STRESS_TIME_CAPS,
    OWN_NAMESPACE,
    READ_ONLY_MARGIN_R2,
    READ_ONLY_ORIGINAL_EXIT_R1,
    ROOT,
    SCRATCH,
    TASK_ID,
    TERMINAL_CANDIDATE_SIGNAL,
    TERMINAL_INSUFFICIENT_SUPPORT,
    TERMINAL_METHOD_OR_SOURCE_BLOCKED,
    dump_json,
    sha256_bytes,
    sha256_file,
)
from .sources import (
    load_immutable_exit_r1_ledgers,
    load_sources,
    verify_exit_r1_and_b_r2_provenance,
)
from .statistics import (
    analyze_conditional_branch_and_tail,
    build_contrast_registry,
    descriptive_metrics,
    max_t_bootstrap,
    safe_mean,
)


def write_jsonl_ledger(name: str, rows: list[dict[str, Any]], *, directory: Path = SCRATCH) -> dict[str, Any]:
    path = directory / name
    raw = b"".join(canonical(r) for r in rows)
    path.write_bytes(raw)
    return {
        "path": str(path),
        "sha256": sha256_bytes(raw),
        "rows": len(rows),
    }


def freeze_check(code_sha: str) -> list[dict[str, Any]]:
    """Verify Commit 1 code/test/contract immutability and remote push verification before any outcome."""
    if not __debug__:
        raise ValueError("INVALID_METHOD: Optimized Python forbidden; assertion gates must remain active")

    parent = subprocess.check_output(
        ["git", "rev-parse", f"{code_sha}^"], cwd=ROOT, text=True
    ).strip()
    if parent != EXACT_START_SHA:
        raise ValueError(
            f"INVALID_METHOD: Freeze commit parent {parent} != EXACT_START_SHA {EXACT_START_SHA}"
        )

    tracked_paths = (
        subprocess.check_output(
            [
                "git",
                "ls-tree",
                "-r",
                "--name-only",
                code_sha,
                "--",
                f"scripts/strategy_research/{OWN_NAMESPACE}",
                f"tests/test_v06_{OWN_NAMESPACE}_book.py",
                f"tests/test_v06_{OWN_NAMESPACE}_account.py",
                f"tests/test_v06_{OWN_NAMESPACE}_statistics_and_audit.py",
                f"docs/strategy_research/{OWN_NAMESPACE}/G2_CONDITIONAL_EXIT_R1_FROZEN_METHOD_SPEC.md",
            ],
            cwd=ROOT,
            text=True,
        )
        .strip()
        .splitlines()
    )
    if len(tracked_paths) < 13:
        raise ValueError("INVALID_METHOD: Missing frozen implementation/test/spec files in code_sha")

    for rel_p in tracked_paths:
        disk_bytes = (ROOT / rel_p).read_bytes()
        git_bytes = subprocess.check_output(["git", "show", f"{code_sha}:{rel_p}"], cwd=ROOT)
        if disk_bytes != git_bytes:
            raise ValueError(f"INVALID_METHOD: Post-freeze implementation mutation detected in {rel_p}")

    contract_path = EVIDENCE_DIR / "G2_CONDITIONAL_EXIT_R1_FROZEN_CONTRACT.json"
    rel_contract = str(contract_path.relative_to(ROOT)).replace("\\", "/")
    if contract_path.read_bytes() != subprocess.check_output(
        ["git", "show", f"{code_sha}:{rel_contract}"], cwd=ROOT
    ):
        raise ValueError("INVALID_METHOD: Frozen contract mutated after Commit 1")

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for rel_p, expected_h in contract["frozen_implementation_sha256"].items():
        if sha256_file(ROOT / rel_p) != expected_h:
            raise ValueError(f"INVALID_METHOD: Frozen file SHA256 mismatch on {rel_p}")
    for rel_p, expected_h in contract["inherited_sha256"].items():
        if sha256_file(ROOT / rel_p) != expected_h:
            raise ValueError(f"INVALID_METHOD: Inherited read-only file SHA256 mismatch on {rel_p}")

    # Verify remote push receipt exists and matches code_sha
    remote_ver_path = SCRATCH / "FIRST_FREEZE_REMOTE_VERIFICATION.json"
    if not remote_ver_path.is_file():
        remote_ver_path = EVIDENCE_DIR / "FIRST_FREEZE_REMOTE_VERIFICATION.json"
    if not remote_ver_path.is_file():
        raise ValueError("INVALID_METHOD: Missing FIRST_FREEZE_REMOTE_VERIFICATION.json before historical run")
    remote_ver = json.loads(remote_ver_path.read_text(encoding="utf-8"))
    if (
        remote_ver.get("commit1_SHA") != code_sha
        or remote_ver.get("ls_remote_SHA") != code_sha
        or remote_ver.get("parent_SHA") != EXACT_START_SHA
        or not remote_ver.get("REMOTE_PUSH_VERIFIED")
    ):
        raise ValueError("INVALID_METHOD: Remote push verification does not match code_sha")

    configs, _ = verify_identity()
    selected = [c for c in configs if c["id"] in CANDIDATE_IDS]
    if len(selected) != 2 or {c["id"] for c in selected} != set(CANDIDATE_IDS):
        raise ValueError("INVALID_METHOD: Candidate configuration identity failure")
    return selected


def matched_control(
    last: np.ndarray,
    mark: np.ndarray,
    rates: list[dict[str, Any]],
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    scheme: str,
    q: float,
) -> dict[str, Any]:
    """Compute same-event opposite-side paired reference control."""
    try:
        controls = [
            execute_conditional_position(
                last, mark, rates, event, candidate, cost, scheme, q, side_override=s
            )
            for s in (-1, 1)
        ]
    except PartialIneligibleError:
        return {"qualified": False, "reason": "INELIGIBLE_PARTIAL_CONTROL"}
    return {
        "qualified": True,
        "balanced_net_bps": safe_mean([float(t["net_after_funding_bps"]) for t in controls]),
        "LONG_net_bps": float(controls[1]["net_after_funding_bps"]),
        "SHORT_net_bps": float(controls[0]["net_after_funding_bps"]),
        "grade": "NONTRADABLE_SAME_EVENT_PAIRED_REFERENCE_NOT_POOLED_CASH",
    }


def verify_baseline_e0_h1_identity(
    configs: list[dict[str, Any]],
    cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]],
    signals: dict[str, dict[tuple[int, int], list[dict[str, Any]]]],
    events_map: dict[str, dict[tuple[int, int], dict[str, dict[str, Any]]]],
    immutable_ledgers: dict[tuple[str, str], dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    """Verify our standalone conditional_book and account exactly reproduce Exit R1 E0 and H1."""
    receipts = []
    for c in configs:
        cid = c["id"]
        for cost_name, cost in (("STRESS", STRESS), ("BASE", BASE)):
            ref_bundle = immutable_ledgers[cid, cost_name]
            ref_paired = ref_bundle["paired"]
            if len(ref_paired) != EXPECTED_ORIGINAL_EVENTS[cid]:
                raise ValueError(f"Expected {EXPECTED_ORIGINAL_EVENTS[cid]} paired rows for {cid}")

            # 1. Verify paired E0 and H1 trade-by-trade identity
            deltas_h1_e0 = []
            for p_row in ref_paired:
                ev_id = p_row["event_id"]
                dt = datetime.fromtimestamp(int(p_row["entry_at"]) / 1000, UTC)
                key = (dt.year, dt.month)
                last, mark, fund, _ = cache[key]
                ev = events_map[cid][key][ev_id]
                for sch in ("E0", "H1"):
                    ref_cell = p_row["cells"][sch]
                    actual = execute_conditional_position(
                        last, mark, fund, ev, c, cost, sch, float(ref_cell["quantity"])
                    )
                    for exact_field in (
                        "entry_at",
                        "exit_at",
                        "exit_ack_at",
                        "exit_reason",
                        "quantity",
                        "raw_entry",
                        "effective_entry",
                        "raw_exit",
                        "effective_exit",
                        "settlement_count",
                    ):
                        if actual[exact_field] != ref_cell[exact_field]:
                            raise ValueError(
                                f"Baseline {sch} paired field {exact_field} mismatch on {ev_id}: "
                                f"{actual[exact_field]} != {ref_cell[exact_field]}"
                            )
                    for float_field in (
                        "fee_entry",
                        "fee_exit",
                        "gross_usdt",
                        "execution_drag_usdt",
                        "net_usdt",
                        "funding_cash_usdt",
                        "net_after_funding_usdt",
                        "net_after_funding_bps",
                    ):
                        if abs(float(actual[float_field]) - float(ref_cell[float_field])) > 1e-7:
                            raise ValueError(
                                f"Baseline {sch} paired float {float_field} mismatch on {ev_id}"
                            )
                deltas_h1_e0.append(
                    float(p_row["cells"]["H1"]["net_after_funding_bps"])
                    - float(p_row["cells"]["E0"]["net_after_funding_bps"])
                )

            if cost_name == "STRESS":
                mean_delta = float(np.mean(deltas_h1_e0))
                if abs(mean_delta - EXPECTED_ORIGINAL_H1_MINUS_E0_STRESS_BPS[cid]) > 1e-9:
                    raise ValueError(f"Baseline H1-E0 STRESS mean delta mismatch for {cid}: {mean_delta}")

            # 2. Verify full 35-fold account replay for E0 and H1 reproduces E0_orders and H1_orders
            for sch in ("E0", "H1"):
                ref_orders = ref_bundle[f"{sch}_orders"]
                cash = 1000.0
                replayed_trades = []
                for key, (last, mark, fund, fold) in cache.items():
                    book = replay_fold(last, mark, fund, signals[cid][key], c, fold, cost, sch, cash)
                    cash = book["ending_equity"]
                    replayed_trades.extend(book["trades"])
                if len(replayed_trades) != len(ref_orders):
                    raise ValueError(f"Full account {sch} trade count mismatch for {cid}/{cost_name}")
                for act_t, ref_t in zip(replayed_trades, ref_orders, strict=True):
                    if act_t["event_id"] != ref_t["event_id"] or act_t["exit_at"] != ref_t["exit_at"]:
                        raise ValueError(f"Full account {sch} trade identity mismatch on {act_t['event_id']}")
                    if abs(float(act_t["net_after_funding_usdt"]) - float(ref_t["net_after_funding_usdt"])) > 1e-7:
                        raise ValueError(f"Full account {sch} net cash mismatch on {act_t['event_id']}")
                    if abs(float(act_t["cash_after_ack"]) - float(ref_t["cash_after_ack"])) > 1e-6:
                        raise ValueError(f"Full account {sch} ending cash mismatch on {act_t['event_id']}")

            receipts.append({
                "candidate": cid,
                "cost": cost_name,
                "paired_events_verified": len(ref_paired),
                "E0_account_orders_verified": len(ref_bundle["E0_orders"]),
                "H1_account_orders_verified": len(ref_bundle["H1_orders"]),
                "H1_minus_E0_mean_net_bps": float(np.mean(deltas_h1_e0)),
                "status": "EXACT_MATCH",
            })

    return {
        "status": "ALL_EIGHT_BASELINE_CELLS_EXACT_MATCH",
        "cells_verified": len(receipts),
        "receipts": receipts,
    }


def evaluate_paired_cell(
    base_e0_orders: list[dict[str, Any]],
    events_for_cand: dict[tuple[int, int], dict[str, dict[str, Any]]],
    cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]],
    candidate: dict[str, Any],
    cost_name: str,
    cost: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Evaluate E0, H1, X1, and X2 on the exact original accepted E0 events and quantities."""
    rows: list[dict[str, Any]] = []
    censored_18h: list[str] = []
    censored_24h: list[str] = []
    accepted = len(base_e0_orders)
    caps = sum(1 for t in base_e0_orders if t["exit_reason"] == "TIME_CAP")
    missing_caps = 0

    for old in base_e0_orders:
        entry_at = int(old["entry_at"])
        dt = datetime.fromtimestamp(entry_at / 1000, UTC)
        key = (dt.year, dt.month)
        last, mark, rates, fold = cache[key]

        if not path_eligible(entry_at, int(fold["end_ms"]), hours=18):
            censored_18h.append(old["event_id"])
            missing_caps += int(old["exit_reason"] == "TIME_CAP")
            continue
        if not path_eligible(entry_at, int(fold["end_ms"]), hours=24):
            censored_24h.append(old["event_id"])

        ev = events_for_cand[key][old["event_id"]]
        record: dict[str, Any] = {
            "candidate": candidate["id"],
            "cost": cost_name,
            "event_id": old["event_id"],
            "entry_at": entry_at,
            "side": int(old["side"]),
            "quantity": float(old["quantity"]),
            "baseline_time_cap": old["exit_reason"] == "TIME_CAP",
            "cells": {},
        }
        for scheme in ALL_SCHEMES:
            t = execute_conditional_position(
                last, mark, rates, ev, candidate, cost, scheme, float(old["quantity"])
            )
            if scheme == "E0" and (
                t["exit_at"] != old["exit_at"]
                or abs(float(t["net_after_funding_usdt"]) - float(old["net_after_funding_usdt"])) > 1e-7
            ):
                raise ValueError(f"Paired E0 mismatch on {old['event_id']}")
            ctrl = matched_control(last, mark, rates, ev, candidate, cost, scheme, float(old["quantity"]))
            t["control_net_bps"] = ctrl.get("balanced_net_bps")
            t["matched_control"] = ctrl
            record["cells"][scheme] = t
        rows.append(record)

    support = {
        "E0_accepted_n": accepted,
        "paired18h_qualified_n": len(rows),
        "censored_18h_event_ids": censored_18h,
        "censored_24h_event_ids": censored_24h,
        "E0_TIME_CAP_n": caps,
        "censored_E0_TIME_CAP_n": missing_caps,
        "censored_TIME_CAP_fraction": (missing_caps / caps) if caps else 0.0,
        "meets_predeclared_time_cap_minimum": (
            caps >= EXPECTED_ORIGINAL_STRESS_TIME_CAPS[candidate["id"]]
            if cost_name == "STRESS"
            else caps >= 19
        ),
    }
    return rows, support


def run_one_shot(code_sha: str) -> dict[str, Any]:
    """Execute the single outcome-blind frozen development pass for G2 Conditional Exit R1."""
    configs = freeze_check(code_sha)
    if SCRATCH.is_symlink():
        raise ValueError("Task scratch directory cannot be a symlink")
    SCRATCH.mkdir(exist_ok=True, mode=0o700)

    marker = SCRATCH / "ONE_SHOT_STARTED"
    if marker.exists():
        raise ValueError("INVALID_METHOD: One-shot pass already started; second run prohibited")
    marker.write_text(code_sha + "\n", encoding="utf-8")

    # P0 provenance and source gates
    provenance_receipt = verify_exit_r1_and_b_r2_provenance()
    dump_json(SCRATCH / "PROVENANCE_AND_REVOCATION_RECEIPT.json", provenance_receipt)

    arrays, rates, source_receipt = load_sources()
    dump_json(SCRATCH / "SOURCE_IDENTITY.json", source_receipt)

    # Verify original R3/R31 E0 study gate in memory redirected to SCRATCH
    orig_scratch = prior_r3.SCRATCH
    prior_r3.SCRATCH = SCRATCH
    try:
        _ = prior_r3.study(configs, arrays, rates, code_sha, source_receipt)
    finally:
        prior_r3.SCRATCH = orig_scratch

    folds = get_monthly_folds()
    if len(folds) != 35 or (folds[0]["year"], folds[0]["month"]) != (2021, 2) or (folds[-1]["year"], folds[-1]["month"]) != (2023, 12):
        raise ValueError("Expected exact 35 monthly folds from 2021-02 to 2023-12")

    cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]] = {}
    signals: dict[str, dict[tuple[int, int], list[dict[str, Any]]]] = {}
    events_map: dict[str, dict[tuple[int, int], dict[str, dict[str, Any]]]] = {}

    for f in folds:
        key = (int(f["year"]), int(f["month"]))
        prev = (int(f["prev_year"]), int(f["prev_month"]))
        cache[key] = (
            np.vstack([arrays["last"][prev], arrays["last"][key]]),
            np.vstack([arrays["mark"][prev], arrays["mark"][key]]),
            [*rates[prev], *rates[key]],
            f,
        )

    for c in configs:
        cid = c["id"]
        signals[cid] = {}
        events_map[cid] = {}
        for key, (last, _mark, _fund, f) in cache.items():
            full = generate_wave_signals(last, cid, int(f["embargo_start_ms"]), int(f["embargo_end_ms"]))
            elig = eligible_events(full, c, f)[0]
            signals[cid][key] = elig
            events_map[cid][key] = {e["event_id"]: e for e in elig}

    immutable_ledgers = load_immutable_exit_r1_ledgers()
    baseline_identity = verify_baseline_e0_h1_identity(
        configs, cache, signals, events_map, immutable_ledgers
    )
    dump_json(SCRATCH / "BASELINE_E0_H1_IDENTITY_RECEIPT.json", baseline_identity)

    result: dict[str, Any] = {
        "TASK_ID": TASK_ID,
        "CONTROLLER_DISPATCH_SHA": CONTROLLER_DISPATCH_SHA,
        "CONTROLLER_AUTHORITY": CONTROLLER_AUTHORITY,
        "BRANCH": BRANCH,
        "EXACT_START_SHA": EXACT_START_SHA,
        "READ_ONLY_ORIGINAL_EXIT_R1": READ_ONLY_ORIGINAL_EXIT_R1,
        "READ_ONLY_MARGIN_R2": READ_ONLY_MARGIN_R2,
        "frozen_code_sha": code_sha,
        "source_manifest_sha256": source_receipt["source_manifest_sha256"],
        "grade": "DEVELOPMENT_ONLY_PRECOMMITTED_12H_CONDITIONAL_EXIT_STUDY",
        "selectable_new_configurations": 4,
        "baseline_reference_configurations": 2,
        "total_candidate_scheme_cells_per_cost": 8,
        "cumulative_exposed_trial_count": 68,
        "provenance_and_revocations": provenance_receipt,
        "baseline_e0_h1_identity": baseline_identity,
        "candidates": {},
        "paired_contrast_decomposition": {},
        "inference": {},
        "automatic_promotions": [],
    }

    paired_all: dict[tuple[str, str], list[dict[str, Any]]] = {}
    auditable_new_trades: list[dict[str, Any]] = []

    for c in configs:
        cid = c["id"]
        result["candidates"][cid] = {}
        for cost_name, cost in (("STRESS", STRESS), ("BASE", BASE)):
            base_e0_orders = immutable_ledgers[cid, cost_name]["E0_orders"]
            pairs, support = evaluate_paired_cell(
                base_e0_orders, events_map[cid], cache, c, cost_name, cost
            )
            paired_all[cid, cost_name] = pairs

            paired_metrics = {}
            branch_analysis = {}
            account_results = {}

            for scheme in ALL_SCHEMES:
                scheme_paired_trades = [row["cells"][scheme] for row in pairs if scheme in row["cells"]]
                paired_metrics[scheme] = descriptive_metrics(scheme_paired_trades, cost_name)
                if scheme in CONDITIONAL_SCHEMES:
                    branch_analysis[scheme] = analyze_conditional_branch_and_tail(pairs, scheme)

                # Full 35-fold single-position 1x account simulation
                cash = 1000.0
                acc_trades: list[dict[str, Any]] = []
                curves: list[np.ndarray] = []
                monthly: list[dict[str, Any]] = []
                skipped_fates: list[dict[str, Any]] = []
                for key, (last, mark, fund, fold) in cache.items():
                    before = cash
                    book = replay_fold(last, mark, fund, signals[cid][key], c, fold, cost, scheme, cash)
                    for trade in book["trades"]:
                        ctrl = matched_control(
                            last, mark, fund, events_map[cid][key][trade["event_id"]], c, cost, scheme, float(trade["quantity"])
                        )
                        trade["control_net_bps"] = ctrl.get("balanced_net_bps")
                        trade["matched_control"] = ctrl
                    cash = book["ending_equity"]
                    acc_trades.extend(book["trades"])
                    curves.append(book["curve"])
                    skipped_fates.extend(book["skipped_event_ids"])
                    monthly.append({
                        "year": key[0],
                        "month": key[1],
                        "starting_cash": before,
                        "ending_cash": cash,
                        "N": len(book["trades"]),
                        "event_fates": book["fates"],
                        "Mark_DD_pct": book["max_mtm_drawdown_pct"],
                        "Mark_min_equity": book["min_mark_equity"],
                        "occupancy_fraction": book["occupancy_fraction"],
                        "occupied_minutes": book["occupied_minutes"],
                        "peak_exposure_ratio": book["max_exposure_ratio"],
                        "exposure_above_1x_minutes": book["exposure_above_1x_minutes"],
                    })

                full_curve = np.vstack(curves)
                curve_path = SCRATCH / f"{cid}_{cost_name}_{scheme}_Mark_curve.npz"
                np.savez_compressed(curve_path, curve=full_curve)
                curve_sha = sha256_file(curve_path)

                e0_accepted_ids = [t["event_id"] for t in base_e0_orders]
                scheme_accepted_ids = [t["event_id"] for t in acc_trades]

                account_results[scheme] = {
                    "metrics": descriptive_metrics(acc_trades, cost_name, full_curve, monthly),
                    "monthly": monthly,
                    "journal": write_jsonl_ledger(f"{cid}_{cost_name}_{scheme}_orders.jsonl", acc_trades),
                    "skipped_signal_fates": skipped_fates,
                    "accepted_event_ids": scheme_accepted_ids,
                    "accepted_event_set_identical_to_E0": scheme_accepted_ids == e0_accepted_ids,
                    "prospective_censor_horizon_hours": PROSPECTIVE_HORIZON_HOURS[scheme],
                    "curve": {
                        "path": str(curve_path),
                        "sha256": curve_sha,
                        "uncompressed_curve_sha256": hashlib.sha256(full_curve.tobytes()).hexdigest(),
                    },
                    "peak_exposure_ratio": max(float(m["peak_exposure_ratio"]) for m in monthly),
                    "exposure_above_1x_minutes": sum(int(m["exposure_above_1x_minutes"]) for m in monthly),
                    "occupied_minutes": sum(int(m["occupied_minutes"]) for m in monthly),
                    "opportunity_cost_conflicts": sum(
                        1 for x in skipped_fates if x["reason"] == "POSITION_ACK_OR_COOLDOWN"
                    ),
                    "prospective_fold_censors": sum(
                        1 for x in skipped_fates if x["reason"] == "PROSPECTIVE_FOLD_CENSOR"
                    ),
                }

                if scheme in CONDITIONAL_SCHEMES:
                    auditable_new_trades.extend(
                        {"cost": cost_name, "curve_path": str(curve_path), "curve_sha256": curve_sha, **t}
                        for t in acc_trades
                    )

            result["candidates"][cid][cost_name] = {
                "support": support,
                "paired": paired_metrics,
                "conditional_branch_analysis": branch_analysis,
                "account": account_results,
                "paired_ledger": write_jsonl_ledger(f"{cid}_{cost_name}_paired.jsonl", pairs),
            }

    # Cross-candidate same-day clustering diagnostic
    w1_days = {
        datetime.fromtimestamp(int(p["entry_at"]) / 1000, UTC).strftime("%Y-%m-%d")
        for p in paired_all["W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H", "STRESS"]
    }
    w2_days = {
        datetime.fromtimestamp(int(p["entry_at"]) / 1000, UTC).strftime("%Y-%m-%d")
        for p in paired_all["W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H", "STRESS"]
    }
    result["cross_candidate_same_day_overlap"] = {
        "w1_unique_utc_days": len(w1_days),
        "w2_unique_utc_days": len(w2_days),
        "shared_utc_days_count": len(w1_days & w2_days),
        "shared_utc_days": sorted(w1_days & w2_days),
    }

    # Bootstrap inference (8-contrast joint family + 4-contrast per-candidate families)
    for cost_name in ("STRESS", "BASE"):
        reg_8, decomp_8 = build_contrast_registry(paired_all, CANDIDATE_IDS, cost_name)
        result["paired_contrast_decomposition"][cost_name] = decomp_8
        result["inference"][cost_name] = {
            "joint_8_contrasts": {
                "7": max_t_bootstrap(reg_8, 7),
                "14": max_t_bootstrap(reg_8, 14),
            },
            "per_candidate_4_contrasts": {},
        }
        for cid in CANDIDATE_IDS:
            reg_4, _ = build_contrast_registry(paired_all, (cid,), cost_name)
            result["inference"][cost_name]["per_candidate_4_contrasts"][cid] = {
                "7": max_t_bootstrap(reg_4, 7),
                "14": max_t_bootstrap(reg_4, 14),
            }

    # Independent Decimal Audit (>=20 new + >=20 previous-R1 witnesses)
    decimal_audit = run_independent_real_decimal_audit(auditable_new_trades, source_receipt)
    result["independent_Decimal_audit"] = decimal_audit
    dump_json(SCRATCH / "DECIMAL_AUDIT_RECEIPT.json", decimal_audit)

    # Evaluate predeclared terminal gates
    w2_2023_negative_any = False
    thin_evidence_any = False
    for cid in CANDIDATE_IDS:
        stress_rec = result["candidates"][cid]["STRESS"]
        for sch in CONDITIONAL_SCHEMES:
            br = stress_rec["conditional_branch_analysis"][sch]
            if br["thin_evidence_flag"] or br["underpowered_branch_split"]:
                thin_evidence_any = True
            y2023_bps = stress_rec["account"][sch]["metrics"]["yearly_breakdown"]["2023"]["mean_net_bps"]
            if (y2023_bps is None or float(y2023_bps) <= 0.0) and cid == "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H":
                w2_2023_negative_any = True

    ci_spans_zero_any = False
    for block_d in ("7", "14"):
        inf = result["inference"]["STRESS"]["joint_8_contrasts"][block_d]
        if inf["status"] != "MEASURED_CONDITIONAL_ON_EXPOSED_SELECTED_LEADS":
            ci_spans_zero_any = True
            continue
        for c_row in inf["contrasts"]:
            if (
                c_row["qualified_n"] < 20
                or c_row["nonempty_calendar_blocks"] < 8
                or c_row["simultaneous_LCB_bps"] <= 0.0
            ):
                ci_spans_zero_any = True

    if decimal_audit["status"] != "PASS":
        result["terminal"] = TERMINAL_METHOD_OR_SOURCE_BLOCKED
    elif ci_spans_zero_any or thin_evidence_any or w2_2023_negative_any:
        result["terminal"] = TERMINAL_INSUFFICIENT_SUPPORT
    else:
        result["terminal"] = TERMINAL_CANDIDATE_SIGNAL

    result["terminal_gate_summary"] = {
        "decimal_audit_pass": decimal_audit["status"] == "PASS",
        "simultaneous_ci_includes_zero_or_negative": ci_spans_zero_any,
        "thin_evidence_or_underpowered_branch": thin_evidence_any,
        "w2_2023_negative_or_nonpositive": w2_2023_negative_any,
        "terminal": result["terminal"],
    }

    dump_json(SCRATCH / "G2_CONDITIONAL_EXIT_R1_RESULTS.json", result)
    print("TERMINAL", result["terminal"], flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code-sha", required=True, help="Exact Commit 1 frozen git SHA")
    args = parser.parse_args()
    try:
        run_one_shot(args.code_sha)
    except Exception as exc:
        if SCRATCH.is_symlink():
            raise
        SCRATCH.mkdir(exist_ok=True, mode=0o700)
        dump_json(
            SCRATCH / "G2_CONDITIONAL_EXIT_R1_FAILURE.json",
            {
                "TASK_ID": TASK_ID,
                "terminal": TERMINAL_METHOD_OR_SOURCE_BLOCKED,
                "exception": type(exc).__name__,
                "reason": str(exc),
                "frozen_code_sha": args.code_sha,
                "optimistic_summary_suppressed": True,
                "rerun_prohibited": True,
            },
        )
        raise


if __name__ == "__main__":
    main()
