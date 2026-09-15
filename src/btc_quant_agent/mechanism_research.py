from __future__ import annotations

import bisect
import hashlib
import importlib
import json
import math
import resource
import shutil
import statistics
import subprocess
import time
from collections import Counter, deque
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import BacktestEngine, FundingEvent, TradeOutcome, metrics, resample
from .config import AppConfig
from .domain import Candidate, Candle, Direction, Setup, TimeframeFeatures
from .engine import EngineMode, HistoricalFeatureCache, QuantEngine
from .funnel import trace_setup_funnels
from .mechanism import (
    EXPERIMENT_ARMS,
    decompose_rr,
    deduplicate_factor_score,
    e1_fixed_tp_target,
    funding_crossing_count,
)
from .multifactor import FactorAssessment
from .regime import classify_regime
from .research import DEV_END_MS, DEV_START_MS, mark_legacy_diagnostic, research_summary
from .risk import build_position_plan
from .structure import confirmed_pivots


def assert_v032_development_only(rows: Sequence[dict[str, Any]]) -> None:
    if any(
        int(row["timestamp_ms"]) < DEV_START_MS
        or int(row["timestamp_ms"]) >= DEV_END_MS
        for row in rows
    ):
        raise ValueError("v0.3.2 holdout firewall rejected artifact row")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _factor_transform(
    mode: str, config: AppConfig
) -> Callable[[FactorAssessment, Candidate, TimeframeFeatures], FactorAssessment]:
    def transform(
        control: FactorAssessment,
        candidate: Candidate,
        features: TimeframeFeatures,
    ) -> FactorAssessment:
        if mode not in {"E2", "E3"}:
            raise ValueError("unknown factor experiment")
        return deduplicate_factor_score(
            control, candidate, features, config.strategy, mode  # type: ignore[arg-type]
        )

    return transform


def _run_arm(
    name: str,
    candles: Sequence[Candle],
    config: AppConfig,
    cache: HistoricalFeatureCache,
    funding: Sequence[FundingEvent],
) -> tuple[list[TradeOutcome], list[dict[str, Any]], float]:
    candidate_transform = e1_fixed_tp_target if name == "E1" else None
    factor_transform = _factor_transform(name, config) if name in {"E2", "E3"} else None
    engine = QuantEngine(
        config,
        cache,
        research_candidate_transform=candidate_transform,
        research_factor_transform=factor_transform,
        mode=EngineMode.LEGACY_RESEARCH_V022,
    )
    backtest = BacktestEngine(engine, None, funding, capture_decisions=name != "CONTROL")
    started = time.perf_counter()
    outcomes = backtest.run(candles)
    return outcomes, backtest.decision_log, time.perf_counter() - started


def _score_summary(rows: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(row[key]) for row in rows]
    bins: Counter[str] = Counter()
    for value in values:
        label = (
            "0-50" if value < 50 else "50-60" if value < 60 else
            "60-70" if value < 70 else "70-80" if value < 80 else
            "80-90" if value < 90 else "90-99.99" if value < 100 else "100"
        )
        bins[label] += 1
    return {
        "count": len(values),
        "bins": {name: bins[name] for name in ("0-50", "50-60", "60-70", "70-80", "80-90", "90-99.99", "100")},
        "score_100_share": sum(value == 100 for value in values) / len(values) if values else None,
        "unique_score_count": len(set(values)),
        "variance": statistics.pvariance(values) if values else None,
    }


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left)
        * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator else None


def _sequential_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    stages = (
        "valid_geometry", "gross_rr_pass", "after_fee_pass",
        "after_fee_slippage_pass", "after_funding_pass", "min_notional_pass",
        "frozen_risk_plan_pass",
    )
    output: dict[str, Any] = {}
    for setup in ("TREND_PULLBACK", "BREAKOUT_RETEST"):
        for direction in ("LONG", "SHORT"):
            selected = [row for row in rows if row["setup"] == setup and row["direction"] == direction]
            output[f"{setup}_{direction}"] = {
                "post_factor_candidates": len(selected),
                **{stage: sum(bool(row[stage]) for row in selected) for stage in stages},
                "by_year": {
                    str(year): {
                        "post_factor_candidates": sum(int(row["year"]) == year for row in selected),
                        **{
                            stage: sum(int(row["year"]) == year and bool(row[stage]) for row in selected)
                            for stage in stages
                        },
                    }
                    for year in range(2021, 2027)
                },
            }
    return output


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "count": len(ordered),
        "mean": statistics.mean(ordered),
        "median": statistics.median(ordered),
        "p10": ordered[max(0, math.ceil(0.10 * len(ordered)) - 1)],
        "p90": ordered[max(0, math.ceil(0.90 * len(ordered)) - 1)],
    }


def _excursions(
    outcomes: Sequence[TradeOutcome],
    decision_rows: Sequence[dict[str, Any]],
    e1_candidates: Sequence[dict[str, Any]],
    candles: Sequence[Candle],
) -> list[dict[str, Any]]:
    decision_time = {
        str(row["signal_id"]): int(row["timestamp_ms"])
        for row in decision_rows if row.get("signal_id")
    }
    atr_by_key = {
        (int(row["timestamp_ms"]), str(row["direction"])): float(row["atr"])
        for row in e1_candidates
    }
    opens = [bar.open_time_ms for bar in candles]
    output: list[dict[str, Any]] = []
    for item in outcomes:
        if item.setup != "TREND_PULLBACK" or item.entered_at_ms is None or item.exited_at_ms is None:
            continue
        timestamp = decision_time.get(item.signal_id)
        if timestamp is None or item.direction is None or item.entry_price is None:
            continue
        atr = atr_by_key.get((timestamp, item.direction))
        if not atr:
            continue
        start = bisect.bisect_left(opens, item.entered_at_ms)
        end = bisect.bisect_right(opens, item.exited_at_ms)
        bars = candles[start:end]
        if not bars:
            continue
        if item.direction == "LONG":
            mfe = (max(bar.high for bar in bars) - item.entry_price) / atr
            mae = (item.entry_price - min(bar.low for bar in bars)) / atr
        else:
            mfe = (item.entry_price - min(bar.low for bar in bars)) / atr
            mae = (max(bar.high for bar in bars) - item.entry_price) / atr
        output.append({"signal_id": item.signal_id, "timestamp_ms": timestamp, "mfe_atr": mfe, "mae_atr": mae})
    return output


def run_v032_experiments(
    candles_1m: Sequence[Candle],
    config: AppConfig,
    funding_events: Sequence[FundingEvent],
) -> dict[str, Any]:
    if not candles_1m or candles_1m[0].open_time_ms != DEV_START_MS:
        raise ValueError("v0.3.2 requires the complete development period")
    if candles_1m[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("v0.3.2 experiments reject holdout rows")
    if EXPERIMENT_ARMS != ("CONTROL", "E0", "E1", "E2", "E3"):
        raise ValueError("combined experiment arms are forbidden")
    frozen = replace(
        config,
        strategy=replace(config.strategy, enable_derivatives_group=False, enable_order_book_factor=False),
    )
    started = time.perf_counter()
    cache = HistoricalFeatureCache()
    arm_outcomes: dict[str, list[TradeOutcome]] = {}
    arm_decisions: dict[str, list[dict[str, Any]]] = {}
    runtimes: dict[str, float] = {}
    for name in ("CONTROL", "E1", "E2", "E3"):
        arm_outcomes[name], arm_decisions[name], runtimes[name] = _run_arm(
            name, candles_1m, frozen, cache, funding_events
        )

    completed = {interval: resample(candles_1m, interval) for interval in ("15m", "1h", "4h")}
    limits = {"15m": frozen.data.history_limit_15m, "1h": frozen.data.history_limit_1h, "4h": frozen.data.history_limit_4h}
    histories: dict[str, deque[Candle]] = {name: deque(maxlen=limits[name]) for name in completed}
    cursors = {name: 0 for name in completed}
    engine = QuantEngine(frozen, cache, mode=EngineMode.LEGACY_RESEARCH_V022)
    rr_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    e1_rows: list[dict[str, Any]] = []
    denominator: Counter[str] = Counter()
    momentum: Counter[str] = Counter()
    diagnostic_started = time.perf_counter()
    for decision_bar in completed["15m"]:
        for interval in ("15m", "1h", "4h"):
            bars = completed[interval]
            while cursors[interval] < len(bars) and bars[cursors[interval]].close_time_ms <= decision_bar.close_time_ms:
                histories[interval].append(bars[cursors[interval]])
                cursors[interval] += 1
        now_ms = decision_bar.close_time_ms + 1
        result = engine.scan(list(histories["4h"]), list(histories["1h"]), list(histories["15m"]), None, now_ms)
        if result.reason_code in {"FEATURE_ERROR", "INVALID_CANDLES", "STALE_DECISION_DATA"}:
            continue
        f4 = engine.diagnostic_features("4h", list(histories["4h"]))
        f1 = engine.diagnostic_features("1h", list(histories["1h"]))
        f15 = engine.diagnostic_features("15m", list(histories["15m"]))
        regime = classify_regime(f1, frozen.strategy)
        denominator[str(regime)] += 1
        traces = trace_setup_funnels(
            list(histories["15m"]), f4, f1, f15, regime, frozen, result
        )
        for trace in traces:
            if trace.stages[0].passed:
                denominator[f"{trace.setup}_REGIME_ELIGIBLE"] += 1
            candidate = trace.candidate
            factor = trace.factor
            if candidate is None or factor is None:
                continue
            rsi_ok = (
                frozen.strategy.rsi_long_min <= f15.rsi <= frozen.strategy.rsi_long_max
                if candidate.direction == Direction.LONG
                else frozen.strategy.rsi_short_min <= f15.rsi <= frozen.strategy.rsi_short_max
            )
            roc_ok = (
                f15.roc > 0 if candidate.direction == Direction.LONG else f15.roc < 0
            )
            momentum[
                "NEITHER" if rsi_ok and roc_ok else "RSI_ONLY_REJECT" if not rsi_ok and roc_ok
                else "ROC_ONLY_REJECT" if rsi_ok and not roc_ok else "BOTH"
            ] += 1
            e2 = deduplicate_factor_score(factor, candidate, f15, frozen.strategy, "E2")
            e3 = deduplicate_factor_score(factor, candidate, f15, frozen.strategy, "E3")
            frozen_plan = build_position_plan(
                candidate, f15.atr, frozen.strategy, frozen.risk
            )
            year = datetime.fromtimestamp(now_ms / 1000, UTC).year
            base_row = {
                "timestamp_ms": now_ms, "year": year,
                "direction": candidate.direction.value, "setup": candidate.setup.value,
                "regime": str(regime), "atr": f15.atr, "close": f15.close,
                "control_score": factor.score, "control_positive_groups": factor.positive_groups,
                "control_blocked": factor.blocked_reason,
                "e2_score": e2.score, "e2_positive_groups": e2.positive_groups,
                "e2_blocked": e2.blocked_reason,
                "e2_risk_plan_pass": e2.blocked_reason is None and frozen_plan is not None,
                "e3_score": e3.score, "e3_positive_groups": e3.positive_groups,
                "e3_blocked": e3.blocked_reason,
                "e3_risk_plan_pass": e3.blocked_reason is None and frozen_plan is not None,
            }
            candidate_rows.append(base_row)
            if candidate.setup == Setup.TREND_PULLBACK:
                experimental = e1_fixed_tp_target(candidate, f15)
                e1_rr = decompose_rr(experimental, f15.atr, frozen.strategy, frozen.risk)
                pivots = confirmed_pivots(
                    list(histories["15m"])[-frozen.strategy.level_lookback_bars :],
                    frozen.strategy.pivot_left, frozen.strategy.pivot_right,
                )
                between = [
                    pivot.price for pivot in pivots
                    if pivot.kind == ("HIGH" if candidate.direction == Direction.LONG else "LOW")
                    and (
                        f15.close < pivot.price < experimental.target_level
                        if candidate.direction == Direction.LONG
                        else experimental.target_level < pivot.price < f15.close
                    )
                ]
                distance = (
                    min(abs(level - f15.close) for level in between) / f15.atr
                    if between and f15.atr > 0 else None
                )
                e1_rows.append({
                    **base_row,
                    "post_factor_pass": factor.blocked_reason is None,
                    "nearest_confirmed_level": candidate.target_level,
                    "experimental_target": experimental.target_level,
                    "intermediate_level_exists": bool(between),
                    "intermediate_barrier_count": len(between),
                    "distance_to_intermediate_barrier_atr": distance,
                    "risk_plan_pass": factor.blocked_reason is None and e1_rr.frozen_risk_plan_pass,
                    "rr_gross": e1_rr.rr_gross,
                    "rr_net": e1_rr.rr_net,
                })
            if factor.blocked_reason is not None:
                continue
            decomposition = decompose_rr(candidate, f15.atr, frozen.strategy, frozen.risk)
            crossings = funding_crossing_count(
                now_ms, candidate.setup, list(funding_events),
                frozen.backtest.trend_pullback_holding_minutes,
                frozen.backtest.breakout_retest_holding_minutes,
            )
            rr_rows.append({**base_row, **decomposition.as_dict(), "funding_crossing_count": crossings})
    runtimes["E0_DIAGNOSTIC"] = time.perf_counter() - diagnostic_started
    expected_trends = denominator["TREND_UP"] + denominator["TREND_DOWN"]
    if denominator["TREND_PULLBACK_REGIME_ELIGIBLE"] != expected_trends or denominator["BREAKOUT_RETEST_REGIME_ELIGIBLE"] != expected_trends:
        raise RuntimeError("corrected funnel regime denominator mismatch")

    reasons = Counter(str(row["reject_reason"]) for row in rr_rows)
    sequential = _sequential_summary(rr_rows)
    required = {
        group: {
            "required_reward_atr": _distribution([float(row["required_reward_atr"]) for row in rows if row["required_reward_atr"] is not None]),
            "actual_target_gap_atr": _distribution([float(row["actual_target_gap_atr"]) for row in rows if row["actual_target_gap_atr"] is not None]),
        }
        for group, rows in {
            f"{setup}_{direction}_{year}": [row for row in rr_rows if row["setup"] == setup and row["direction"] == direction and int(row["year"]) == year and row["reject_reason"] != "PASS"]
            for setup in ("TREND_PULLBACK", "BREAKOUT_RETEST")
            for direction in ("LONG", "SHORT") for year in range(2021, 2027)
        }.items()
    }
    funding_summary = {
        "crossing_counts": dict(Counter(int(row["funding_crossing_count"]) for row in rr_rows)),
        "frozen_reserve_rate": frozen.risk.funding_stress_rate * frozen.risk.max_expected_funding_events,
        "incremental_rejects": reasons["FUNDING_STRESS_CROSSED_THRESHOLD"],
        "baseline_actual_funding_pnl_usdt": sum(item.funding_pnl_usdt for item in arm_outcomes["CONTROL"]),
    }
    stop_summary = {
        "post_factor_candidates": len(rr_rows),
        "buffer_crossed_threshold": sum(bool(row["buffer_crossed_threshold"]) for row in rr_rows),
        "by_setup": {
            setup: sum(bool(row["buffer_crossed_threshold"]) and row["setup"] == setup for row in rr_rows)
            for setup in ("TREND_PULLBACK", "BREAKOUT_RETEST")
        },
    }
    e1_outcomes = [item for item in arm_outcomes["E1"] if item.setup == "TREND_PULLBACK"]
    excursions = _excursions(e1_outcomes, arm_decisions["E1"], e1_rows, candles_1m)
    e1_metrics = metrics(e1_outcomes)
    e1_result = {
        "eligible_frozen_tp_candidates": len(e1_rows),
        "eligible_post_factor_candidates": sum(bool(row["post_factor_pass"]) for row in e1_rows),
        "risk_plan_survival": sum(bool(row["risk_plan_pass"]) for row in e1_rows),
        "outcomes": e1_metrics,
        "target_reach_rate": e1_metrics["outcome_counts"].get("WIN", 0) / e1_metrics["filled_trades"] if e1_metrics["filled_trades"] else None,
        "stop_rate": e1_metrics["outcome_counts"].get("LOSS", 0) / e1_metrics["filled_trades"] if e1_metrics["filled_trades"] else None,
        "timeout_rate": e1_metrics["outcome_counts"].get("TIMEOUT", 0) / e1_metrics["filled_trades"] if e1_metrics["filled_trades"] else None,
        "year_coverage": sorted({datetime.fromtimestamp((item.entered_at_ms or 0) / 1000, UTC).year for item in e1_outcomes if item.entered_at_ms}),
        "mfe_atr": _distribution([float(row["mfe_atr"]) for row in excursions]),
        "mae_atr": _distribution([float(row["mae_atr"]) for row in excursions]),
        "sample_classification": "LOW_SAMPLE" if e1_metrics["filled_trades"] < 20 else "ADEQUATE_SAMPLE",
    }
    barrier = {
        "eligible_candidates": len(e1_rows),
        "intermediate_barrier_count": sum(bool(row["intermediate_level_exists"]) for row in e1_rows),
        "incidence": sum(bool(row["intermediate_level_exists"]) for row in e1_rows) / len(e1_rows) if e1_rows else None,
        "barrier_distance_atr": _distribution([float(row["distance_to_intermediate_barrier_atr"]) for row in e1_rows if row["distance_to_intermediate_barrier_atr"] is not None]),
        "excursions": excursions,
    }
    factor_results: dict[str, Any] = {}
    for arm, key in (("E2", "e2_score"), ("E3", "e3_score")):
        arm_rows = [row for row in candidate_rows if row["control_blocked"] not in {"4H macro trend is not aligned", "15m RSI is overextended"}]
        passed = [row for row in arm_rows if row[f"{arm.lower()}_blocked"] is None]
        control_values = [float(row["control_score"]) for row in arm_rows]
        arm_values = [float(row[key]) for row in arm_rows]
        factor_results[arm] = {
            "candidate_count": len(arm_rows),
            "distribution": _score_summary(arm_rows, key),
            "control_distribution_same_scope": _score_summary(arm_rows, "control_score"),
            "factor_pass": len(passed),
            "risk_gate_count": sum(bool(row[f"{arm.lower()}_risk_plan_pass"]) for row in arm_rows),
            "raw_confirmed_decisions": sum(
                row.get("direction") in {"LONG", "SHORT"}
                for row in arm_decisions.get(arm, [])
            ),
            "rank_score_pearson": _pearson(control_values, arm_values),
            "outcomes": research_summary(arm_outcomes[arm]),
        }
    return mark_legacy_diagnostic({
        "scope": {"development_only": True, "holdout_accessed": False, "start_ms": DEV_START_MS, "end_ms_exclusive": DEV_END_MS},
        "denominator_correctness": {
            "trend_up": denominator["TREND_UP"], "trend_down": denominator["TREND_DOWN"],
            "trend_total": expected_trends,
            "tp_regime_eligible": denominator["TREND_PULLBACK_REGIME_ELIGIBLE"],
            "br_regime_eligible": denominator["BREAKOUT_RETEST_REGIME_ELIGIBLE"],
        },
        "control_summary": research_summary(arm_outcomes["CONTROL"]),
        "rr_component_summary": {
            "post_factor_candidates": len(rr_rows), "reject_reasons": dict(reasons),
            "sequential_pass_table": sequential,
        },
        "required_target_distance": required,
        "funding_stress_diagnostic": funding_summary,
        "stop_buffer_diagnostic": stop_summary,
        "e1_tp_target_results": e1_result,
        "e1_barrier_diagnostic": barrier,
        "e2_score_dedup_results": factor_results["E2"],
        "e3_participation_dedup_results": factor_results["E3"],
        "momentum_diagnostic": dict(momentum),
        "mechanism_comparison": {
            "arms": {
                name: research_summary(arm_outcomes[name])
                for name in ("CONTROL", "E1", "E2", "E3")
            },
            "hypothesis_verdicts": {
                "H1": "FALSIFIED",
                "H2": "SUPPORTED",
                "H3": "FALSIFIED",
                "H5": "INCONCLUSIVE_MECHANISM",
            },
            "candidate_recommendation": "NO_CANDIDATE",
        },
        "rr_rows": rr_rows,
        "e1_rows": e1_rows,
        "e1_trade_rows": [
            {"timestamp_ms": item.entered_at_ms, **item.as_dict()}
            for item in e1_outcomes
            if item.entered_at_ms is not None
        ],
        "performance": {
            "arm_runtime_seconds": runtimes,
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        },
    })


def write_v032_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    *,
    seed: int = 32,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable mechanism run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    rr_rows = result.pop("rr_rows")
    e1_rows = result.pop("e1_rows")
    e1_trades = result.pop("e1_trade_rows")
    assert_v032_development_only(rr_rows)
    assert_v032_development_only(e1_rows)
    assert_v032_development_only(e1_trades)
    provenance = {
        "git_commit_sha": subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
        "strategy_version": config.runtime.strategy_version,
        "feature_version": config.runtime.feature_version,
        "config_hash": config.config_hash,
        "dataset_checksum": json.loads(manifest.read_text(encoding="utf-8"))["checksum_sha256"],
        "protocol_checksum": _sha256(protocol),
        "random_seed": seed,
        "validation_status": config.runtime.validation_status,
    }
    payload = mark_legacy_diagnostic({"provenance": provenance, **result})
    outputs = {
        "control_summary.json": result["control_summary"],
        "rr_component_summary.json": result["rr_component_summary"],
        "required_target_distance.json": result["required_target_distance"],
        "funding_stress_diagnostic.json": result["funding_stress_diagnostic"],
        "stop_buffer_diagnostic.json": result["stop_buffer_diagnostic"],
        "e1_tp_target_results.json": result["e1_tp_target_results"],
        "e1_barrier_diagnostic.json": result["e1_barrier_diagnostic"],
        "e2_score_dedup_results.json": result["e2_score_dedup_results"],
        "e2_score_distribution.json": result["e2_score_dedup_results"]["distribution"],
        "e3_participation_dedup_results.json": result["e3_participation_dedup_results"],
        "mechanism_comparison.json": result["mechanism_comparison"],
        "experiment_summary.json": payload,
    }
    for name, value in outputs.items():
        (target / name).write_text(
            json.dumps(
                mark_legacy_diagnostic(dict(value)),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    pq.write_table(pa.Table.from_pylist(rr_rows), target / "rr_component_decomposition.parquet")
    pq.write_table(pa.Table.from_pylist(e1_trades), target / "e1_tp_trades.parquet")
    pq.write_table(pa.Table.from_pylist(e1_rows), target / "e1_candidate_diagnostic.parquet")
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "data_manifest.json")
    return target
