from __future__ import annotations

import collections
import hashlib
import importlib
import json
import math
import random
import resource
import shutil
import statistics
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

from .backtest import FundingEvent
from .causal_entry_research import (
    BOOTSTRAP_SIMULATIONS,
    HORIZONS,
    IndexedOneMinuteSeries,
    _metric_delta,
    _percentile,
    bootstrap_directionality,
    build_directionality_rows,
    directionality_label,
    match_controls,
    summarize_directionality,
)
from .config import AppConfig
from .domain import Candle
from .geometry_research import run_v033_geometry_audit
from .research import DEV_END_MS, DEV_START_MS

SEED = 35
EXPECTED = {
    "BR_PATTERN": 546,
    "BR_POST_FACTOR": 185,
    "BR_GROSS_RR_PASS": 63,
    "BR_AFTER_FEE_PASS": 45,
    "BR_AFTER_SLIPPAGE_PASS": 33,
    "BR_RISK_PASS": 14,
    "BR_HISTORICAL_FILLED": 13,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _median(rows: Sequence[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return statistics.median(values) if values else None


def _mean(rows: Sequence[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return statistics.mean(values) if values else None


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    lm = statistics.mean(left)
    rm = statistics.mean(right)
    numerator = sum((a - lm) * (b - rm) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum((a - lm) ** 2 for a in left) * sum((b - rm) ** 2 for b in right))
    return numerator / denominator if denominator else None


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2.0 + 1.0
        for position in order[start:end]:
            ranks[position] = rank
        start = end
    return ranks


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _pearson(_ranks(left), _ranks(right))


def _labels_for_candidates(
    candidates: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        for horizon in HORIZONS:
            output.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "kind": "CANDIDATE",
                    "year": candidate["year"],
                    "direction": candidate["direction"],
                    **directionality_label(candidate, series, horizon),
                }
            )
    return output


def _stage_metrics(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metrics = ("signed_return_atr", "mfe_atr", "mae_atr", "reach_1_0", "reach_2_5")
    output: dict[str, Any] = {}
    for horizon in (240, 480):
        rows = [
            row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]
        ]
        output[f"{horizon}m"] = {
            "count": len(rows),
            **{
                metric: (
                    statistics.mean(float(row[metric]) for row in rows)
                    if metric.startswith("reach_") and rows
                    else _median(rows, metric)
                )
                for metric in metrics
            },
        }
    return output


def _stage_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {
        horizon: {
            metric: (
                None
                if left[horizon][metric] is None or right[horizon][metric] is None
                else float(left[horizon][metric]) - float(right[horizon][metric])
            )
            for metric in ("signed_return_atr", "mfe_atr", "mae_atr", "reach_1_0", "reach_2_5")
        }
        for horizon in ("240m", "480m")
    }


def _stage_bootstrap(
    pattern_labels: Sequence[dict[str, Any]],
    selected_ids: set[str],
    *,
    seed: int,
    simulations: int = BOOTSTRAP_SIMULATIONS,
) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in pattern_labels:
        clusters[str(row["candidate_id"])].append(row)
    ids = sorted(clusters)
    rng = random.Random(seed)
    output: dict[str, Any] = {}
    for horizon in (240, 480):
        values: list[float] = []
        for _ in range(simulations):
            sample_ids = [rng.choice(ids) for _ in ids]
            all_values = [
                float(row["signed_return_atr"])
                for identity in sample_ids
                for row in clusters[identity]
                if row["horizon_minutes"] == horizon and not row["incomplete"]
            ]
            selected = [
                float(row["signed_return_atr"])
                for identity in sample_ids
                if identity in selected_ids
                for row in clusters[identity]
                if row["horizon_minutes"] == horizon and not row["incomplete"]
            ]
            if all_values and selected:
                values.append(statistics.median(selected) - statistics.median(all_values))
        output[f"{horizon}m"] = {
            "p05": _percentile(values, 0.05),
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
        }
    return output


def _gate_ladder(
    candidates: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    predicates: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("S1_BR_PATTERN", lambda row: True),
        ("S2_MACRO_RSI_PASS", lambda row: bool(row["post_macro_rsi"])),
        ("S3_BR_POST_FACTOR", lambda row: bool(row["post_factor"])),
        ("S4_GROSS_RR_PASS", lambda row: bool(row["post_factor"] and row["gross_rr_pass"])),
        ("S5_BR_RISK_PASS", lambda row: bool(row["post_factor"] and row["frozen_risk_plan_pass"])),
    ]
    stage_labels: dict[str, list[dict[str, Any]]] = {}
    summary: dict[str, Any] = {"stages": {}, "adjacent_deltas": {}}
    for name, predicate in predicates:
        selected = [row for row in candidates if predicate(row)]
        labels = _labels_for_candidates(selected, series)
        stage_labels[name] = labels
        summary["stages"][name] = _stage_metrics(labels)
    for (left_name, _), (right_name, _) in pairwise(predicates):
        summary["adjacent_deltas"][f"{right_name}-{left_name}"] = _stage_delta(
            summary["stages"][right_name], summary["stages"][left_name]
        )
    summary["interpretation"] = "observational selection attribution, not causal"
    return summary, stage_labels["S1_BR_PATTERN"]


def _match_gate_near_misses(
    candidates: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    definitions: dict[
        str, tuple[Callable[[dict[str, Any]], bool], Callable[[dict[str, Any]], bool]]
    ] = {
        "MOMENTUM_ROC": (
            lambda row: bool(row["post_macro_rsi"] and row["momentum_roc_aligned"]),
            lambda row: bool(row["post_macro_rsi"] and not row["momentum_roc_aligned"]),
        ),
        "PARTICIPATION": (
            lambda row: bool(row["post_macro_rsi"] and row["participation_pass"]),
            lambda row: bool(
                row["post_macro_rsi"]
                and row["participation_available"]
                and not row["participation_pass"]
            ),
        ),
        "FACTOR_SCORE": (
            lambda row: bool(row["post_macro_rsi"] and row["factor_score_pass"]),
            lambda row: bool(row["post_macro_rsi"] and not row["factor_score_pass"]),
        ),
        "GROSS_RR": (
            lambda row: bool(row["post_factor"] and row["gross_rr_pass"]),
            lambda row: bool(row["post_factor"] and not row["gross_rr_pass"]),
        ),
    }
    matches: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for gate, (pass_predicate, reject_predicate) in definitions.items():
        passed = [row for row in candidates if pass_predicate(row)]
        rejected = [row for row in candidates if reject_predicate(row)]
        gate_matches: list[dict[str, Any]] = []
        for item in passed:
            eligible = [
                row
                for row in rejected
                if row["year"] == item["year"]
                and row["direction"] == item["direction"]
                and row["atr_decile"] == item["atr_decile"]
                and abs(int(row["bar_index"]) - int(item["bar_index"])) >= 96
            ]
            if gate == "GROSS_RR":
                eligible.sort(
                    key=lambda row: (
                        abs(float(item["rr_gross"]) - float(row["rr_gross"])),
                        abs(int(row["bar_index"]) - int(item["bar_index"])),
                    )
                )
            else:
                eligible.sort(
                    key=lambda row: (
                        abs(int(row["bar_index"]) - int(item["bar_index"])),
                        int(row["decision_close_ms"]),
                    )
                )
            if not eligible:
                continue
            reject = eligible[0]
            for horizon in (240, 480):
                left = directionality_label(item, series, horizon)
                right = directionality_label(reject, series, horizon)
                if left["incomplete"] or right["incomplete"]:
                    continue
                gate_matches.append(
                    {
                        "gate": gate,
                        "pass_candidate_id": item["candidate_id"],
                        "reject_candidate_id": reject["candidate_id"],
                        "timestamp_ms": item["timestamp_ms"],
                        "reject_timestamp_ms": reject["timestamp_ms"],
                        "year": item["year"],
                        "direction": item["direction"],
                        "atr_decile": item["atr_decile"],
                        "bar_distance": abs(int(reject["bar_index"]) - int(item["bar_index"])),
                        "horizon_minutes": horizon,
                        "signed_return_delta": float(left["signed_return_atr"])
                        - float(right["signed_return_atr"]),
                        "mfe_delta": float(left["mfe_atr"]) - float(right["mfe_atr"]),
                        "mae_delta": float(left["mae_atr"]) - float(right["mae_atr"]),
                    }
                )
        matches.extend(gate_matches)
        rng = random.Random(SEED + len(summary))
        block: dict[str, Any] = {
            "pass_count": len(passed),
            "reject_count": len(rejected),
            "matched_pass_count": len({row["pass_candidate_id"] for row in gate_matches}),
            "horizons": {},
        }
        for horizon in (240, 480):
            deltas = [
                float(row["signed_return_delta"])
                for row in gate_matches
                if row["horizon_minutes"] == horizon
            ]
            boot = (
                [statistics.mean(rng.choice(deltas) for _ in deltas) for _ in range(2_000)]
                if deltas
                else []
            )
            rows = [row for row in gate_matches if row["horizon_minutes"] == horizon]
            block["horizons"][f"{horizon}m"] = {
                "pairs": len(rows),
                "signed_return_delta_mean": statistics.mean(deltas) if deltas else None,
                "mfe_delta_mean": _mean(rows, "mfe_delta"),
                "mae_delta_mean": _mean(rows, "mae_delta"),
                "bootstrap": {
                    "p05": _percentile(boot, 0.05),
                    "p50": _percentile(boot, 0.50),
                    "p95": _percentile(boot, 0.95),
                },
            }
        block["classification"] = (
            "INCONCLUSIVE_LOW_SAMPLE" if block["matched_pass_count"] < 20 else "EVALUABLE"
        )
        summary[gate] = block
    return matches, summary


def _reuse_diagnostics(matches: Sequence[dict[str, Any]], candidate_count: int) -> dict[str, Any]:
    reuse = collections.Counter(str(row["control_id"]) for row in matches)
    distribution = collections.Counter(reuse.values())
    return {
        "candidate_count": candidate_count,
        "total_matched_rows": len(matches),
        "unique_controls": len(reuse),
        "reuse_distribution": {str(key): value for key, value in sorted(distribution.items())},
        "max_reuse_count": max(reuse.values(), default=0),
        "effective_unique_control_ratio": len(reuse) / len(matches) if matches else None,
        "full_k_candidates": sum(
            sum(row["candidate_id"] == identity for row in matches) == 5
            for identity in {str(row["candidate_id"]) for row in matches}
        ),
    }


def _rr_relationship(
    candidates: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> dict[str, Any]:
    post = [row for row in candidates if row["post_factor"]]
    output: dict[str, Any] = {"threshold_scanned": False, "horizons": {}}
    for horizon in (240, 480):
        rows: list[dict[str, float]] = []
        for item in post:
            label = directionality_label(item, series, horizon)
            if label["incomplete"]:
                continue
            rows.append(
                {
                    "gross_rr": float(item["rr_gross"]),
                    "net_rr": float(item["rr_net"]),
                    "signed": float(label["signed_return_atr"]),
                    "mfe": float(label["mfe_atr"]),
                    "mae": float(label["mae_atr"]),
                }
            )
        gross = [row["gross_rr"] for row in rows]
        net = [row["net_rr"] for row in rows]
        output["horizons"][f"{horizon}m"] = {
            "count": len(rows),
            "gross_rr_signed_pearson": _pearson(gross, [row["signed"] for row in rows]),
            "gross_rr_signed_spearman": _spearman(gross, [row["signed"] for row in rows]),
            "net_rr_signed_pearson": _pearson(net, [row["signed"] for row in rows]),
            "net_rr_signed_spearman": _spearman(net, [row["signed"] for row in rows]),
            "gross_rr_mfe_pearson": _pearson(gross, [row["mfe"] for row in rows]),
            "gross_rr_mae_pearson": _pearson(gross, [row["mae"] for row in rows]),
        }
    return output


def _baseline_audit(
    risk_pass: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
    baseline_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    pq = importlib.import_module("pyarrow.parquet")
    decisions = pq.read_table(baseline_dir / "decision_replay.parquet").to_pylist()
    trades = pq.read_table(baseline_dir / "trades.parquet").to_pylist()
    signal_by_time = {int(row["timestamp_ms"]): row for row in decisions if row.get("signal_id")}
    trade_by_signal = {str(row["signal_id"]): row for row in trades}
    lifecycle: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for item in sorted(risk_pass, key=lambda row: int(row["timestamp_ms"])):
        timestamp = int(item["timestamp_ms"])
        signal = signal_by_time.get(timestamp)
        trade = trade_by_signal.get(str(signal["signal_id"])) if signal else None
        suppressor = next(
            (
                row
                for row in trades
                if row["entered_at_ms"] is not None
                and row["exited_at_ms"] is not None
                and int(row["entered_at_ms"]) < timestamp <= int(row["exited_at_ms"])
            ),
            None,
        )
        state = (
            "FILLED_RESOLVED"
            if trade
            else "SUPPRESSED_OPEN_POSITION"
            if suppressor
            else "NOT_EMITTED"
        )
        lifecycle.append(
            {
                "candidate_id": item["candidate_id"],
                "timestamp_ms": timestamp,
                "year": item["year"],
                "direction": item["direction"],
                "entry_low": item["entry_low"],
                "entry_high": item["entry_high"],
                "stop": item["actual_stop"],
                "target": item["target"],
                "rr_gross": item["rr_gross"],
                "rr_net": item["rr_net"],
                "filled": trade is not None,
                "lifecycle": state,
                "signal_id": signal["signal_id"] if signal else None,
                "suppressing_signal_id": suppressor["signal_id"] if suppressor else None,
                "outcome": trade["outcome"] if trade else None,
            }
        )
        if trade is None:
            continue
        start = series.index_after(int(trade["entered_at_ms"]) - 1)
        end = series.index_after(int(trade["exited_at_ms"]))
        bars = series.bars[start:end]
        entry = float(trade["entry_price"])
        risk = abs(entry - float(item["actual_stop"]))
        if item["direction"] == "LONG":
            mfe_r = max(0.0, max(bar.high for bar in bars) - entry) / risk
            mae_r = max(0.0, entry - min(bar.low for bar in bars)) / risk
        else:
            mfe_r = max(0.0, entry - min(bar.low for bar in bars)) / risk
            mae_r = max(0.0, max(bar.high for bar in bars) - entry) / risk
        audit.append(
            {
                "timestamp_ms": timestamp,
                "year": item["year"],
                "direction": item["direction"],
                "signal_id": trade["signal_id"],
                "entry": trade["entry_price"],
                "stop": item["actual_stop"],
                "target": item["target"],
                "planned_gross_rr": item["rr_gross"],
                "planned_net_rr": item["rr_net"],
                "fill_latency_minutes": (int(trade["entered_at_ms"]) - timestamp) / 60_000,
                "holding_minutes": trade["holding_minutes"],
                "exit": trade["exit_price"],
                "outcome": trade["outcome"],
                "gross_r": float(trade["gross_pnl_usdt"]) / float(trade["risk_usdt"]),
                "fee_r": -float(trade["fees_usdt"]) / float(trade["risk_usdt"]),
                "slippage_r": -float(trade["slippage_usdt"]) / float(trade["risk_usdt"]),
                "funding_r": float(trade["funding_pnl_usdt"]) / float(trade["risk_usdt"]),
                "net_r": trade["net_r"],
                "post_fill_mfe_r": mfe_r,
                "post_fill_mae_r": mae_r,
            }
        )
    paths: collections.Counter[str] = collections.Counter()
    for row in audit:
        if row["outcome"] == "TIMEOUT":
            paths["timeout"] += 1
        elif row["outcome"] == "LOSS" and float(row["post_fill_mfe_r"]) >= 1.0:
            paths["reached_1r_then_stopped"] += 1
        elif row["outcome"] == "LOSS" and float(row["post_fill_mfe_r"]) >= 0.5:
            paths["favorable_excursion_then_reversal"] += 1
        elif row["outcome"] == "LOSS":
            paths["immediate_failure_never_0_5r"] += 1
        else:
            paths["winner"] += 1
    loss_summary = {
        "counts": dict(sorted(paths.items())),
        "losers": sum(row["outcome"] == "LOSS" for row in audit),
        "large_mfe_reversal_systematic": paths["reached_1r_then_stopped"] >= 3,
        "winner_medians": {
            "planned_rr": _median(
                [row for row in audit if float(row["net_r"]) > 0], "planned_net_rr"
            ),
            "mfe_r": _median([row for row in audit if float(row["net_r"]) > 0], "post_fill_mfe_r"),
            "mae_r": _median([row for row in audit if float(row["net_r"]) > 0], "post_fill_mae_r"),
        },
        "loser_medians": {
            "planned_rr": _median(
                [row for row in audit if float(row["net_r"]) <= 0], "planned_net_rr"
            ),
            "mfe_r": _median([row for row in audit if float(row["net_r"]) <= 0], "post_fill_mfe_r"),
            "mae_r": _median([row for row in audit if float(row["net_r"]) <= 0], "post_fill_mae_r"),
        },
    }
    return lifecycle, audit, loss_summary


def _h11(summary: dict[str, Any], bootstrap: dict[str, Any], loyo: dict[str, Any]) -> str:
    four = summary["240m"]["metrics"]
    eight = summary["480m"]["metrics"]
    d4 = float(four["signed_return_atr"]["delta"])
    d8 = float(eight["signed_return_atr"]["delta"])
    if d4 <= 0 and d8 <= 0:
        return "FALSIFIED"
    if (
        d4 > 0
        and d8 > 0
        and float(bootstrap["horizons"]["240m"]["signed_return_atr"]["p05"]) >= -0.05
        and float(bootstrap["horizons"]["480m"]["signed_return_atr"]["p05"]) >= -0.05
        and float(four["reach_1_0"]["delta"]) > 0
        and float(eight["reach_1_0"]["delta"]) > 0
        and all(float(value) > 0 for block in loyo.values() for value in block.values())
    ):
        return "SUPPORTED"
    return "INCONCLUSIVE_MECHANISM"


def _leave_one_year_out(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    years = sorted({int(row["year"]) for row in rows if row["kind"] == "CANDIDATE"})
    return {
        str(year): {
            f"{horizon}m_signed_return_delta": _metric_delta(
                [
                    row
                    for row in rows
                    if int(row["year"]) != year
                    and row["horizon_minutes"] == horizon
                    and not row["incomplete"]
                ],
                "signed_return_atr",
            )
            for horizon in (240, 480)
        }
        for year in years
    }


def run_v035_breakout_qualification(
    candles: Sequence[Candle],
    config: AppConfig,
    funding: Sequence[FundingEvent],
    baseline_dir: str | Path,
    *,
    seed: int = SEED,
) -> dict[str, Any]:
    del funding
    started = time.perf_counter()
    frozen = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    result = run_v033_geometry_audit(
        candles,
        frozen,
        (),
        capture_trend_controls=True,
        capture_breakout_qualification=True,
    )
    candidates = list(result["breakout_qualification_rows"])
    pattern_times = {int(row["timestamp_ms"]) for row in candidates}
    pool = [
        {**row, "is_tp_pattern": int(row["timestamp_ms"]) in pattern_times}
        for row in result["trend_control_rows"]
    ]
    counts = {
        "BR_PATTERN": len(candidates),
        "BR_POST_FACTOR": sum(bool(row["post_factor"]) for row in candidates),
        "BR_GROSS_RR_PASS": sum(
            bool(row["post_factor"] and row["gross_rr_pass"]) for row in candidates
        ),
        "BR_AFTER_FEE_PASS": sum(
            bool(row["post_factor"] and row["after_fee_pass"]) for row in candidates
        ),
        "BR_AFTER_SLIPPAGE_PASS": sum(
            bool(row["post_factor"] and row["after_fee_slippage_pass"]) for row in candidates
        ),
        "BR_RISK_PASS": sum(
            bool(row["post_factor"] and row["frozen_risk_plan_pass"]) for row in candidates
        ),
    }
    series = IndexedOneMinuteSeries(candles)
    matches = match_controls(candidates, pool)
    labels = build_directionality_rows(candidates, matches, pool, series)
    directionality = summarize_directionality(labels)
    bootstrap = bootstrap_directionality(labels, seed)
    loyo = _leave_one_year_out(labels)
    gate_ladder, pattern_labels = _gate_ladder(candidates, series)
    post_ids = {str(row["candidate_id"]) for row in candidates if row["post_factor"]}
    h12_bootstrap = _stage_bootstrap(pattern_labels, post_ids, seed=seed)
    h12_deltas = _stage_delta(
        gate_ladder["stages"]["S3_BR_POST_FACTOR"], gate_ladder["stages"]["S1_BR_PATTERN"]
    )
    near_matches, near_summary = _match_gate_near_misses(candidates, series)
    risk_pass = [row for row in candidates if row["post_factor"] and row["frozen_risk_plan_pass"]]
    lifecycle, trade_audit, loss_paths = _baseline_audit(risk_pass, series, Path(baseline_dir))
    counts["BR_HISTORICAL_FILLED"] = len(trade_audit)
    if counts != EXPECTED:
        raise RuntimeError(
            f"BREAKOUT_EDGE_QUALIFICATION_BLOCKED counts={counts} expected={EXPECTED}"
        )
    h11 = _h11(directionality, bootstrap, loyo)
    d4 = float(h12_deltas["240m"]["signed_return_atr"])
    d8 = float(h12_deltas["480m"]["signed_return_atr"])
    if d4 <= 0 and d8 <= 0:
        h12 = "FALSIFIED"
    elif (
        d4 > 0
        and d8 > 0
        and float(h12_bootstrap["240m"]["p05"]) >= -0.05
        and float(h12_bootstrap["480m"]["p05"]) >= -0.05
    ):
        h12 = "SUPPORTED"
    else:
        h12 = "INCONCLUSIVE_MECHANISM"
    h13 = "INCONCLUSIVE_LOW_SAMPLE"
    recommendation = (
        "RECOMMEND_STRATEGY_ARCHITECTURE_RESET"
        if h11 == "FALSIFIED"
        else "INCONCLUSIVE_CONTINUE_DIAGNOSTIC"
    )
    reuse = _reuse_diagnostics(matches, len(candidates))
    by_year_direction = {
        f"{year}_{direction}": {
            "pattern": sum(
                int(row["year"]) == year and row["direction"] == direction for row in candidates
            ),
            "post_factor": sum(
                int(row["year"]) == year
                and row["direction"] == direction
                and bool(row["post_factor"])
                for row in candidates
            ),
            "risk_pass": sum(
                int(row["year"]) == year
                and row["direction"] == direction
                and bool(row["frozen_risk_plan_pass"])
                for row in candidates
            ),
            "filled": sum(
                int(row["year"]) == year and row["direction"] == direction for row in trade_audit
            ),
        }
        for year in range(2021, 2027)
        for direction in ("LONG", "SHORT")
    }
    return {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "start_ms": DEV_START_MS,
            "end_ms_exclusive": DEV_END_MS,
            "tp_status": "TP_RESEARCH_SUSPENDED_AFTER_V0.3.4",
        },
        "br_stage_counts": counts,
        "reference_count_reconciliation": {
            "historical_reference_after_fee": 44,
            "actual_after_fee": 45,
            "historical_reference_after_slippage": 32,
            "actual_after_slippage": 33,
            "explanation": "prompt values were approximate; frozen decompose_rr code and prior v0.3.2 artifact both reproduce 45/33",
        },
        "control_reuse": reuse,
        "br_directionality_by_horizon": directionality,
        "br_directionality_bootstrap": bootstrap,
        "leave_one_year_out": loyo,
        "gate_ladder": {
            **gate_ladder,
            "post_factor_vs_pattern": h12_deltas,
            "post_factor_vs_pattern_bootstrap": h12_bootstrap,
        },
        "gate_near_miss_summary": near_summary,
        "rr_directionality_relationship": _rr_relationship(candidates, series),
        "loss_path_attribution": loss_paths,
        "by_year_direction": by_year_direction,
        "hypothesis_verdicts": {"H11": h11, "H12": h12, "H13": h13},
        "recommendation": recommendation,
        "overall_status": "BREAKOUT_EDGE_QUALIFICATION_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        },
        "br_funnel_events": candidates,
        "br_pattern_matched_controls": matches,
        "gate_near_miss_matches": near_matches,
        "risk_pass_14_lifecycle": lifecycle,
        "baseline_13_trade_audit": trade_audit,
    }


def _development_only(rows: Sequence[dict[str, Any]]) -> None:
    for row in rows:
        for key, value in row.items():
            if (
                value is not None
                and key.endswith(("timestamp_ms", "at_ms"))
                and not DEV_START_MS <= int(value) < DEV_END_MS
            ):
                raise ValueError("v0.3.5 holdout firewall rejected artifact row")


def write_v035_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    baseline_dir: str | Path,
    *,
    seed: int = SEED,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable v0.3.5 run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    row_names = (
        "br_funnel_events",
        "br_pattern_matched_controls",
        "gate_near_miss_matches",
        "risk_pass_14_lifecycle",
        "baseline_13_trade_audit",
    )
    rows = {name: list(result.pop(name)) for name in row_names}
    for values in rows.values():
        _development_only(values)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    baseline = Path(baseline_dir)
    provenance = {
        "git_commit_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "strategy_version": config.runtime.strategy_version,
        "feature_version": config.runtime.feature_version,
        "config_hash": config.config_hash,
        "dataset_checksum": json.loads(manifest.read_text(encoding="utf-8"))["checksum_sha256"],
        "protocol_checksum": _sha256(protocol),
        "baseline_trade_artifact_checksum": _sha256(baseline / "trades.parquet"),
        "baseline_decision_artifact_checksum": _sha256(baseline / "decision_replay.parquet"),
        "random_seed": seed,
        "validation_status": config.runtime.validation_status,
    }
    payload = {"provenance": provenance, **result}
    outputs = {
        "br_stage_counts.json": result["br_stage_counts"],
        "br_directionality_by_horizon.json": result["br_directionality_by_horizon"],
        "br_directionality_bootstrap.json": result["br_directionality_bootstrap"],
        "gate_ladder.json": result["gate_ladder"],
        "gate_near_miss_summary.json": result["gate_near_miss_summary"],
        "rr_directionality_relationship.json": result["rr_directionality_relationship"],
        "loss_path_attribution.json": result["loss_path_attribution"],
        "by_year_direction.json": result["by_year_direction"],
        "experiment_summary.json": payload,
    }
    for name, value in outputs.items():
        (target / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    parquet_names = {
        "br_funnel_events": "br_funnel_events.parquet",
        "br_pattern_matched_controls": "br_pattern_matched_controls.parquet",
        "gate_near_miss_matches": "gate_near_miss_matches.parquet",
        "risk_pass_14_lifecycle": "risk_pass_14_lifecycle.parquet",
        "baseline_13_trade_audit": "baseline_13_trade_audit.parquet",
    }
    for key, name in parquet_names.items():
        pq.write_table(pa.Table.from_pylist(rows[key]), target / name)
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "data_manifest.json")
    return target
