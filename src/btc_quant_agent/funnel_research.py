from __future__ import annotations

import hashlib
import importlib
import json
import resource
import shutil
import subprocess
import time
from collections import Counter, defaultdict, deque
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import BacktestEngine, FundingEvent, TradeOutcome, metrics, resample
from .config import AppConfig
from .domain import Candle, Regime
from .engine import HistoricalFeatureCache, QuantEngine
from .funnel import SetupFunnelTrace, explain_regime_classification, trace_setup_funnels
from .regime import classify_regime
from .research import DEV_END_MS, DEV_START_MS, ablation_configs, research_summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _period(timestamp_ms: int) -> tuple[int, str]:
    value = datetime.fromtimestamp(timestamp_ms / 1000, UTC)
    return value.year, f"{value.year}-Q{(value.month - 1) // 3 + 1}"


def _factor_bin(score: float) -> str:
    if score < 50:
        return "0-50"
    if score < 60:
        return "50-60"
    if score < 70:
        return "60-70"
    if score < 80:
        return "70-80"
    if score < 90:
        return "80-90"
    if score < 100:
        return "90-99.99"
    return "100"


def _safe_metrics(outcomes: Sequence[TradeOutcome]) -> dict[str, Any]:
    return metrics(outcomes)


def assert_development_only_rows(rows: Sequence[dict[str, Any]]) -> None:
    if any(
        int(row["timestamp_ms"]) < DEV_START_MS
        or int(row["timestamp_ms"]) >= DEV_END_MS
        for row in rows
    ):
        raise ValueError("holdout firewall rejected an artifact row")


def _counterfactual_counts(trace: SetupFunnelTrace) -> dict[str, bool]:
    predicates = {item.stage: item.predicate_passed for item in trace.stages}
    prefix = "TP" if trace.setup == "TREND_PULLBACK" else "BR"
    ignored = {
        "D1": set(),
        "D2": {f"{prefix}_{11 if prefix == 'TP' else 12:02d}_RSI_GATE" if prefix == "TP" else "BR_12_RSI"},
        "D3": {"TP_07_VOLUME_PASS" if prefix == "TP" else "BR_08_VOLUME_PASS"},
        "D4": {"TP_10_4H_MACRO_ALIGNED" if prefix == "TP" else "BR_11_4H_MACRO"},
        "D5": {"TP_12_FACTOR_SCORE" if prefix == "TP" else "BR_13_FACTOR_SCORE"},
        "D6": {"TP_13_POSITIVE_GROUPS" if prefix == "TP" else "BR_14_POSITIVE_GROUPS"},
        "D7": {"TP_08_TARGET_EXISTS"} if prefix == "TP" else {"BR_09_TARGET_EXISTS_OR_ATR_PROJECTION"},
        "D8": {"TP_14_RR_RISK_PLAN" if prefix == "TP" else "BR_15_RISK_PLAN"},
    }
    final_stage = "TP_15_CONFIRMED" if prefix == "TP" else "BR_16_CONFIRMED"
    output: dict[str, bool] = {}
    for diagnostic, removed in ignored.items():
        relevant = {
            name: passed for name, passed in predicates.items() if name != final_stage and name not in removed
        }
        output[diagnostic] = bool(relevant) and all(relevant.values())
    return output


def _stage_report(
    counts: Counter[tuple[str, str, str]],
    yearly: Counter[tuple[str, str, str, int]],
    setup: str,
) -> dict[str, Any]:
    expected = {
        "TREND_PULLBACK": (
            "TP_01_REGIME_ELIGIBLE", "TP_02_SWING_LEVEL_EXISTS",
            "TP_03_EMA25_ZONE_TOUCHED", "TP_04_STRUCTURE_INTACT",
            "TP_05_EMA7_RECLAIM", "TP_06_PREVIOUS_EXTREME_BREAK",
            "TP_07_VOLUME_PASS", "TP_08_TARGET_EXISTS",
            "TP_09_PATTERN_CANDIDATE", "TP_10_4H_MACRO_ALIGNED",
            "TP_11_RSI_GATE", "TP_12_FACTOR_SCORE", "TP_13_POSITIVE_GROUPS",
            "TP_14_RR_RISK_PLAN", "TP_15_CONFIRMED",
        ),
        "BREAKOUT_RETEST": (
            "BR_01_REGIME_ELIGIBLE", "BR_02_CONFIRMED_PIVOT_EXISTS",
            "BR_03_BREAKOUT_CLOSE_PASS", "BR_04_BREAKOUT_DISTANCE_PASS",
            "BR_05_RETEST_TOUCH_PASS", "BR_06_RETEST_CLOSE_HOLDS_LEVEL",
            "BR_07_CONTINUATION_CANDLE", "BR_08_VOLUME_PASS",
            "BR_09_TARGET_EXISTS_OR_ATR_PROJECTION", "BR_10_PATTERN_CANDIDATE",
            "BR_11_4H_MACRO", "BR_12_RSI", "BR_13_FACTOR_SCORE",
            "BR_14_POSITIVE_GROUPS", "BR_15_RISK_PLAN", "BR_16_CONFIRMED",
        ),
    }
    directions: dict[str, Any] = {}
    for direction in ("LONG", "SHORT"):
        ordered = expected[setup]
        initial = counts[(setup, direction, ordered[0])] if ordered else 0
        previous = initial
        rows = []
        for stage in ordered:
            passed = counts[(setup, direction, stage)]
            rows.append(
                {
                    "stage": stage,
                    "count": passed,
                    "survival_pct": 100.0 * passed / initial if initial else 0.0,
                    "dropoff_from_prior_pct": 100.0 * (previous - passed) / previous if previous else 0.0,
                    "by_year": {
                        str(year): yearly[(setup, direction, stage, year)]
                        for year in range(2021, 2027)
                    },
                }
            )
            previous = passed
        directions[direction] = rows
    return directions


def _candidate_row(trace: SetupFunnelTrace, features: Any) -> dict[str, Any]:
    assert trace.candidate is not None
    factor = trace.factor
    return {
        "timestamp_ms": trace.timestamp_ms,
        "year": trace.year,
        "direction": trace.direction,
        "setup": trace.setup,
        "regime": trace.regime,
        "macro_aligned": next(
            item.predicate_passed for item in trace.stages if "MACRO" in item.stage
        ),
        "ema_fast": features.ema_fast,
        "ema_mid": features.ema_mid,
        "ema_slow": features.ema_slow,
        "adx": features.adx,
        "atr_percentile": features.atr_percentile,
        "rsi": features.rsi,
        "roc": features.roc,
        "volume_z": features.volume_z,
        "cvd_slope": features.cvd_slope,
        "pattern_stage": next(item.stage for item in trace.stages if "PATTERN_CANDIDATE" in item.stage),
        "pattern_pass": True,
        "target_source": trace.target_source,
        "factor_raw_score": factor.raw_score if factor else None,
        "factor_available_max": factor.available_max if factor else None,
        "factor_score": factor.score if factor else None,
        "positive_groups": factor.positive_groups if factor else None,
        "factor_scores": json.dumps(factor.group_scores, sort_keys=True) if factor else None,
        "factor_blocked_reason": factor.blocked_reason if factor else None,
        "rr_gross": trace.rr_gross,
        "rr_net": trace.rr_net,
        "risk_plan_pass": trace.risk_plan_pass,
        "final_decision": trace.final_decision,
        "final_reason": trace.final_reason,
    }


def run_funnel_diagnostic(
    candles_1m: Sequence[Candle],
    config: AppConfig,
    funding_events: Sequence[FundingEvent],
) -> dict[str, Any]:
    if not candles_1m or candles_1m[0].open_time_ms != DEV_START_MS:
        raise ValueError("funnel requires the complete development period")
    if candles_1m[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("holdout candles are forbidden")
    frozen = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    started = time.perf_counter()
    cache = HistoricalFeatureCache()
    variants = {"D1_baseline": frozen}
    variants.update(
        {
            name: candidate
            for name, candidate in ablation_configs(frozen, False).items()
            if name in {"A_trend_structure", "B_plus_momentum", "C_plus_participation"}
            and candidate is not None
        }
    )
    outcomes: dict[str, list[TradeOutcome]] = {}
    runtimes: dict[str, float] = {}
    for name, candidate in variants.items():
        variant_started = time.perf_counter()
        outcomes[name] = BacktestEngine(QuantEngine(candidate, cache), None, funding_events).run(
            candles_1m
        )
        runtimes[name] = time.perf_counter() - variant_started

    completed = {interval: resample(candles_1m, interval) for interval in ("15m", "1h", "4h")}
    limits = {
        "15m": frozen.data.history_limit_15m,
        "1h": frozen.data.history_limit_1h,
        "4h": frozen.data.history_limit_4h,
    }
    histories: dict[str, deque[Candle]] = {
        key: deque(maxlen=limits[key]) for key in completed
    }
    cursors = {key: 0 for key in completed}
    engine = QuantEngine(frozen, cache)
    regime_counts: Counter[str] = Counter()
    regime_year: Counter[tuple[str, int]] = Counter()
    regime_quarter: Counter[tuple[str, str]] = Counter()
    transition_reasons: Counter[str] = Counter()
    transition_year: Counter[tuple[str, int]] = Counter()
    stage_counts: Counter[tuple[str, str, str]] = Counter()
    stage_year: Counter[tuple[str, str, str, int]] = Counter()
    gate_counts: Counter[tuple[str, str, int, str]] = Counter()
    target_missing: Counter[tuple[int, str]] = Counter()
    level_availability: Counter[tuple[int, str, str]] = Counter()
    data_ready = 0
    invalid: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    near_buckets: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    decision_count = 0
    trace_started = time.perf_counter()
    for decision_bar in completed["15m"]:
        decision_count += 1
        for interval in ("15m", "1h", "4h"):
            bars = completed[interval]
            while cursors[interval] < len(bars) and bars[cursors[interval]].close_time_ms <= decision_bar.close_time_ms:
                histories[interval].append(bars[cursors[interval]])
                cursors[interval] += 1
        now_ms = decision_bar.close_time_ms + 1
        result = engine.scan(
            list(histories["4h"]), list(histories["1h"]), list(histories["15m"]), None, now_ms
        )
        if result.reason_code in {"FEATURE_ERROR", "INVALID_CANDLES", "STALE_DECISION_DATA"}:
            invalid[result.reason_code] += 1
            continue
        data_ready += 1
        features_4h = engine.diagnostic_features("4h", list(histories["4h"]))
        features_1h = engine.diagnostic_features("1h", list(histories["1h"]))
        features_15m = engine.diagnostic_features("15m", list(histories["15m"]))
        regime = classify_regime(features_1h, frozen.strategy)
        year, quarter = _period(now_ms)
        regime_counts[str(regime)] += 1
        regime_year[(str(regime), year)] += 1
        regime_quarter[(str(regime), quarter)] += 1
        explanation = explain_regime_classification(features_1h, frozen.strategy)
        if regime == Regime.TRANSITION:
            reasons = explanation.contributing_reasons or (explanation.primary_reason,)
            for reason in reasons:
                transition_reasons[reason] += 1
                transition_year[(reason, year)] += 1
            if len(reasons) > 1:
                transition_reasons["MULTIPLE_CONDITIONS"] += 1
                transition_year[("MULTIPLE_CONDITIONS", year)] += 1
        traces = trace_setup_funnels(
            list(histories["15m"]), features_4h, features_1h, features_15m,
            regime, frozen, result,
        )
        for trace in traces:
            for observation in trace.stages:
                if observation.passed:
                    stage_counts[(trace.setup, trace.direction, observation.stage)] += 1
                    stage_year[(trace.setup, trace.direction, observation.stage, year)] += 1
            for diagnostic, passes in _counterfactual_counts(trace).items():
                if passes:
                    gate_counts[(diagnostic, trace.setup, year, trace.direction)] += 1
            if trace.setup == "TREND_PULLBACK":
                swing_stage = trace.stages[1]
                level_availability[(year, trace.direction, "available")] += int(
                    swing_stage.predicate_passed
                )
                level_availability[(year, trace.direction, "evaluated")] += 1
                if all(item.passed for item in trace.stages[:7]) and not trace.stages[7].predicate_passed:
                    target_missing[(year, trace.direction)] += 1
            if trace.candidate is not None:
                candidates.append(_candidate_row(trace, features_15m))
            pattern_index = 8 if trace.setup == "TREND_PULLBACK" else 9
            pattern_predicates = trace.stages[: pattern_index + 1]
            distance = sum(not item.predicate_passed for item in pattern_predicates)
            row = {
                "timestamp_ms": trace.timestamp_ms,
                "year": year,
                "direction": trace.direction,
                "setup": trace.setup,
                "regime": trace.regime,
                "near_miss_score": distance,
                "failed_predicates": json.dumps(
                    [item.stage for item in pattern_predicates if not item.predicate_passed]
                ),
                "final_reason": trace.final_reason,
            }
            bucket = near_buckets[(year, trace.direction, trace.setup)]
            bucket.append(row)
            bucket.sort(key=lambda item: (int(item["near_miss_score"]), int(item["timestamp_ms"])))
            del bucket[10:]
    funnel_runtime = time.perf_counter() - trace_started

    total_ready = sum(regime_counts.values())
    regime_report = {
        regime.value: {
            "count": regime_counts[regime.value],
            "percentage": 100.0 * regime_counts[regime.value] / total_ready if total_ready else 0.0,
            "by_year": {str(year): regime_year[(regime.value, year)] for year in range(2021, 2027)},
            "by_quarter": {
                quarter: count for (name, quarter), count in sorted(regime_quarter.items()) if name == regime.value
            },
        }
        for regime in Regime
    }
    factor_categories: dict[str, Counter[str]] = {
        "all_pattern_candidates": Counter(), "factor_rejected": Counter(),
        "risk_rejected": Counter(), "confirmed": Counter(),
    }
    for row in candidates:
        score_value = row["factor_score"]
        score = float(score_value) if isinstance(score_value, (int, float)) else 0.0
        factor_categories["all_pattern_candidates"][_factor_bin(score)] += 1
        if row["factor_blocked_reason"]:
            factor_categories["factor_rejected"][_factor_bin(score)] += 1
        elif not row["risk_plan_pass"]:
            factor_categories["risk_rejected"][_factor_bin(score)] += 1
        elif row["final_decision"] in {"LONG", "SHORT"}:
            factor_categories["confirmed"][_factor_bin(score)] += 1
    bin_order = ["0-50", "50-60", "60-70", "70-80", "80-90", "90-99.99", "100"]
    factor_report = {
        name: {bucket: counts[bucket] for bucket in bin_order}
        for name, counts in factor_categories.items()
    }
    gate_report: dict[str, Any] = {}
    baseline_signals = sum(
        count for (diagnostic, _setup, _year, _direction), count in gate_counts.items() if diagnostic == "D1"
    )
    for diagnostic in [f"D{number}" for number in range(1, 9)]:
        distributions = {
            "by_setup": {
                setup: sum(count for (name, candidate_setup, _year, _direction), count in gate_counts.items() if name == diagnostic and candidate_setup == setup)
                for setup in ("TREND_PULLBACK", "BREAKOUT_RETEST")
            },
            "by_year": {
                str(year): sum(count for (name, _setup, candidate_year, _direction), count in gate_counts.items() if name == diagnostic and candidate_year == year)
                for year in range(2021, 2027)
            },
        }
        signals = sum(distributions["by_setup"].values())
        gate_report[diagnostic] = {
            "signals": signals,
            "filled_trades": outcomes["D1_baseline"] and _safe_metrics(outcomes["D1_baseline"])["filled_trades"] if diagnostic == "D1" else None,
            "expectancy_r": _safe_metrics(outcomes["D1_baseline"])["expectancy_r"] if diagnostic == "D1" else None,
            "profit_factor": _safe_metrics(outcomes["D1_baseline"])["profit_factor"] if diagnostic == "D1" else None,
            "max_drawdown_r": _safe_metrics(outcomes["D1_baseline"])["max_drawdown_r"] if diagnostic == "D1" else None,
            "trade_count_delta": signals - baseline_signals,
            **distributions,
            "outcome_status": "REPLAYED" if diagnostic == "D1" else "COUNT_ONLY_NO_COMPLIANT_TRADE_OBJECT",
        }

    abc = {name: research_summary(items) for name, items in outcomes.items()}
    removal: dict[str, Any] = {}
    for left, right, label in (
        ("A_trend_structure", "B_plus_momentum", "A_to_B_momentum"),
        ("B_plus_momentum", "C_plus_participation", "B_to_C_participation"),
    ):
        right_ids = {item.signal_id for item in outcomes[right]}
        removed = [item for item in outcomes[left] if item.signal_id not in right_ids]
        resolved = [item.r_multiple for item in removed if item.r_multiple is not None]
        removal[label] = {
            "removed_trade_ids": [item.as_dict() for item in removed],
            "removed_winners": sum(value > 0 for value in resolved),
            "removed_losers": sum(value < 0 for value in resolved),
            "removed_avg_r": sum(resolved) / len(resolved) if resolved else None,
        }
    target = {
        "trend_target_missing": sum(target_missing.values()),
        "trend_target_missing_by_year_direction": {
            f"{year}_{direction}": target_missing[(year, direction)]
            for year in range(2021, 2027) for direction in ("LONG", "SHORT")
        },
        "breakout_confirmed_target": sum(row["target_source"] == "CONFIRMED_LEVEL" for row in candidates if row["setup"] == "BREAKOUT_RETEST"),
        "breakout_atr_projected_target": sum(row["target_source"] == "ATR_PROJECTION" for row in candidates if row["setup"] == "BREAKOUT_RETEST"),
        "support_resistance_availability_by_year": {
            f"{year}_{direction}": {
                "available": level_availability[(year, direction, "available")],
                "evaluated": level_availability[(year, direction, "evaluated")],
            }
            for year in range(2021, 2027) for direction in ("LONG", "SHORT")
        },
    }
    return {
        "protocol": {"scope": "DEVELOPMENT_ONLY", "holdout_accessed": False, "start_ms": DEV_START_MS, "end_ms_exclusive": DEV_END_MS},
        "data_readiness": {"decision_count": decision_count, "ready": data_ready, "invalid": dict(invalid)},
        "regime": regime_report,
        "transition_attribution": {
            "overall": dict(transition_reasons),
            "by_year": {reason: {str(year): transition_year[(reason, year)] for year in range(2021, 2027)} for reason in sorted(transition_reasons)},
        },
        "trend_pullback": _stage_report(stage_counts, stage_year, "TREND_PULLBACK"),
        "breakout_retest": _stage_report(stage_counts, stage_year, "BREAKOUT_RETEST"),
        "factor_score_distribution": factor_report,
        "single_gate_ablation": gate_report,
        "abc": abc,
        "removal_attribution": removal,
        "target_level": target,
        "candidate_rows": candidates,
        "near_miss_rows": [row for rows in near_buckets.values() for row in rows],
        "outcomes": outcomes,
        "performance": {
            "baseline_runtime_seconds": runtimes["D1_baseline"],
            "abc_runtime_seconds": runtimes,
            "funnel_runtime_seconds": funnel_runtime,
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "candidate_rows": len(candidates),
        },
    }


def write_funnel_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    *,
    seed: int = 31,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable funnel run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    provenance = {
        "git_commit_sha": subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
        "strategy_version": config.runtime.strategy_version,
        "feature_version": config.runtime.feature_version,
        "validation_status": config.runtime.validation_status,
        "config_hash": config.config_hash,
        "data_checksum": json.loads(manifest.read_text(encoding="utf-8"))["checksum_sha256"],
        "protocol_checksum": _sha256(protocol),
        "random_seed": seed,
    }
    candidates = result.pop("candidate_rows")
    near_misses = result.pop("near_miss_rows")
    outcomes = result.pop("outcomes")
    assert_development_only_rows([*candidates, *near_misses])
    payload = {"provenance": provenance, **result}
    files = {
        "funnel_summary.json": payload,
        "funnel_by_year.json": {"regime": result["regime"], "transition": result["transition_attribution"]},
        "trend_pullback_funnel.json": result["trend_pullback"],
        "breakout_retest_funnel.json": result["breakout_retest"],
        "factor_score_distribution.json": result["factor_score_distribution"],
        "single_gate_ablation.json": result["single_gate_ablation"],
        "abc_removal_attribution.json": result["removal_attribution"],
        "loss_attribution.json": {
            name: [item.as_dict() for item in items] for name, items in outcomes.items()
        },
    }
    for filename, value in files.items():
        (target / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")

    pq.write_table(pa.Table.from_pylist(candidates), target / "candidate_events.parquet")
    pq.write_table(pa.Table.from_pylist(near_misses), target / "near_miss.parquet")
    shutil.copyfile(protocol, target / "protocol.json")
    shutil.copyfile(manifest, target / "data_manifest.json")
    return target
