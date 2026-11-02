"""Historical frozen v0.3 suite: LEGACY_DIAGNOSTIC_ONLY, not current qualification.

Retained for historical readers/runners; new clients use formal_research.
P5/P6 promotion requires canonical replay/provenance, not these R summaries.
"""

from __future__ import annotations

import csv
import importlib
import json
import shutil
import subprocess
from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import (
    BacktestEngine,
    FundingEvent,
    TradeOutcome,
    bootstrap,
    metrics,
    monte_carlo,
    resample,
)
from .config import AppConfig
from .data.derivatives import HistoricalDerivativeStore
from .domain import Candle
from .engine import EngineMode, HistoricalFeatureCache, QuantEngine
from .structure import confirmed_levels

DEV_START_MS = int(datetime(2021, 1, 1, tzinfo=UTC).timestamp() * 1000)
DEV_END_MS = int(datetime(2026, 2, 1, tzinfo=UTC).timestamp() * 1000)


def mark_legacy_diagnostic(payload: dict[str, Any]) -> dict[str, Any]:
    """Label historical research output so it cannot masquerade as P5/P6 authority."""
    return {
        **payload,
        "classification": "LEGACY_DIAGNOSTIC_ONLY",
        "promotion_eligibility": "NOT_TESTABLE_FOR_NEW_PROMOTION",
        "can_promote": False,
    }


def _add_months(timestamp_ms: int, months: int) -> int:
    value = datetime.fromtimestamp(timestamp_ms / 1000, UTC)
    month_index = value.year * 12 + value.month - 1 + months
    shifted = datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=UTC)
    return int(shifted.timestamp() * 1000)


def _segment(outcomes: Sequence[TradeOutcome], attribute: str) -> dict[str, dict[str, Any]]:
    keys = sorted({str(getattr(item, attribute)) for item in outcomes if getattr(item, attribute)})
    return {
        key: metrics([item for item in outcomes if str(getattr(item, attribute)) == key])
        for key in keys
    }


def research_summary(outcomes: Sequence[TradeOutcome]) -> dict[str, Any]:
    by_year: dict[str, list[TradeOutcome]] = {}
    for item in outcomes:
        timestamp = item.exited_at_ms or item.entered_at_ms
        if timestamp is not None:
            year = str(datetime.fromtimestamp(timestamp / 1000, tz=UTC).year)
            by_year.setdefault(year, []).append(item)
    return mark_legacy_diagnostic({
        "overall": metrics(outcomes),
        "by_year": {year: metrics(items) for year, items in sorted(by_year.items())},
        "by_direction": _segment(outcomes, "direction"),
        "by_setup": _segment(outcomes, "setup"),
        "by_regime": _segment(outcomes, "regime"),
    })


def walk_forward_report(
    outcomes: Sequence[TradeOutcome],
    start_ms: int,
    end_ms: int,
    *,
    train_months: int = 12,
    validation_months: int = 3,
    test_months: int = 3,
) -> list[dict[str, Any]]:
    folds: list[dict[str, Any]] = []
    cursor = start_ms
    while _add_months(cursor, train_months + validation_months + test_months) <= end_ms:
        train_end = _add_months(cursor, train_months)
        test_start = _add_months(train_end, validation_months)
        test_end = _add_months(test_start, test_months)
        test_outcomes = [
            item
            for item in outcomes
            if item.exited_at_ms is not None and test_start <= item.exited_at_ms < test_end
        ]
        folds.append(
            {
                "train": [cursor, train_end],
                "validation": [train_end, test_start],
                "test": [test_start, test_end],
                "test_metrics": metrics(test_outcomes),
            }
        )
        cursor = _add_months(cursor, test_months)
    return folds


def sample_classification(outcomes: Sequence[TradeOutcome]) -> str:
    filled = sum(item.entered_at_ms is not None for item in outcomes)
    if filled < 50:
        return "INSUFFICIENT_SAMPLE_FOR_OPTIMIZATION"
    if filled < 150:
        return "LOW_SAMPLE"
    return "ELIGIBLE_FOR_PARAMETER_RESEARCH"


def stress_costs(
    outcomes: Sequence[TradeOutcome], multiplier: float
) -> list[TradeOutcome]:
    """Reprice frozen trades so a cost stress cannot alter strategy decisions."""
    if multiplier <= 0:
        raise ValueError("cost multiplier must be positive")
    stressed: list[TradeOutcome] = []
    for item in outcomes:
        if item.r_multiple is None or item.gross_pnl_usdt is None:
            stressed.append(item)
            continue
        fees = item.fees_usdt * multiplier
        slippage = item.slippage_usdt * multiplier
        funding = item.funding_pnl_usdt * multiplier
        net = item.gross_pnl_usdt - fees - slippage + funding
        net_r = net / item.risk_usdt if item.risk_usdt else item.r_multiple
        stressed.append(
            replace(
                item,
                fees_usdt=fees,
                slippage_usdt=slippage,
                funding_pnl_usdt=funding,
                net_pnl_usdt=net,
                r_multiple=net_r,
            )
        )
    return stressed


def replay_decisions(
    candles_1m: Sequence[Candle],
    engine: QuantEngine,
    derivatives: HistoricalDerivativeStore | None = None,
) -> list[dict[str, Any]]:
    completed = {interval: resample(candles_1m, interval) for interval in ("15m", "1h", "4h")}
    limits = {
        "15m": engine.config.data.history_limit_15m,
        "1h": engine.config.data.history_limit_1h,
        "4h": engine.config.data.history_limit_4h,
    }
    history: dict[str, deque[Candle]] = {
        interval: deque(maxlen=limits[interval]) for interval in completed
    }
    cursors = {interval: 0 for interval in completed}
    output: list[dict[str, Any]] = []
    for decision_bar in completed["15m"]:
        for interval in ("15m", "1h", "4h"):
            bars = completed[interval]
            while (
                cursors[interval] < len(bars)
                and bars[cursors[interval]].close_time_ms <= decision_bar.close_time_ms
            ):
                history[interval].append(bars[cursors[interval]])
                cursors[interval] += 1
        now_ms = decision_bar.close_time_ms + 1
        result = engine.scan(
            list(history["4h"]),
            list(history["1h"]),
            list(history["15m"]),
            derivatives=(
                derivatives.snapshot_at(
                    now_ms,
                    engine.config.data,
                    include_order_book=engine.config.strategy.enable_order_book_factor,
                )
                if derivatives
                else None
            ),
            now_ms=now_ms,
        )
        support, resistance = confirmed_levels(
            list(history["15m"])[-engine.config.strategy.level_lookback_bars :],
            engine.config.strategy.pivot_left,
            engine.config.strategy.pivot_right,
        )
        output.append(
            {
                "timestamp_ms": now_ms,
                "price": decision_bar.close,
                "macro_4h": result.diagnostics.get("macro_4h"),
                "regime_1h": result.diagnostics.get("regime"),
                "structure_15m": result.diagnostics.get("structure_15m"),
                "ema_15m": result.diagnostics.get("ema_15m"),
                "support": support[-3:],
                "resistance": resistance[-3:],
                "factor_groups": result.diagnostics.get("factor_scores", {}),
                "factor_score": result.diagnostics.get("factor_score"),
                "setup": result.signal.setup.value if result.signal else None,
                "decision": result.action,
                "reject_reason": None if result.signal else result.reason,
                "reason_code": result.reason_code,
            }
        )
    return output


def ablation_configs(config: AppConfig, has_derivatives: bool) -> dict[str, AppConfig | None]:
    base = config.strategy
    variants = {
        "A_trend_structure": replace(
            base,
            enable_momentum_group=False,
            enable_participation_group=False,
            enable_derivatives_group=False,
            enable_volatility_liquidity_group=True,
            enable_volatility_liquidity_score=False,
            enable_order_book_factor=False,
        ),
        "B_plus_momentum": replace(
            base,
            enable_participation_group=False,
            enable_derivatives_group=False,
            enable_volatility_liquidity_group=True,
            enable_volatility_liquidity_score=False,
            enable_order_book_factor=False,
        ),
        "C_plus_participation": replace(
            base,
            enable_derivatives_group=False,
            enable_volatility_liquidity_group=True,
            enable_volatility_liquidity_score=False,
            enable_order_book_factor=False,
        ),
    }
    output: dict[str, AppConfig | None] = {
        name: replace(config, strategy=strategy) for name, strategy in variants.items()
    }
    output["D_plus_derivatives"] = replace(
        config, strategy=replace(base, enable_order_book_factor=False)
    ) if has_derivatives else None
    output["E_plus_order_book"] = replace(
        config, strategy=replace(base, enable_order_book_factor=True)
    ) if has_derivatives else None
    return output


def run_full_suite(
    candles: Sequence[Candle],
    config: AppConfig,
    derivatives: HistoricalDerivativeStore | None,
    funding_events: Sequence[FundingEvent],
    *,
    seed: int,
) -> dict[str, Any]:
    if not candles:
        raise ValueError("development research requires non-empty 1m candles")
    if candles[0].open_time_ms != DEV_START_MS or candles[-1].close_time_ms >= DEV_END_MS:
        raise ValueError(
            "development research is restricted to [2021-01-01, 2026-02-01) UTC"
        )
    baseline_config = (
        config
        if derivatives is not None
        else replace(
            config,
            strategy=replace(
                config.strategy,
                enable_derivatives_group=False,
                enable_order_book_factor=False,
            ),
        )
    )
    feature_cache = HistoricalFeatureCache()

    baseline_decisions: list[dict[str, Any]] = []

    def run(
        candidate: AppConfig,
        events: Sequence[FundingEvent] = funding_events,
        *,
        capture_decisions: bool = False,
    ) -> list[TradeOutcome]:
        backtest = BacktestEngine(
            QuantEngine(candidate, feature_cache, mode=EngineMode.LEGACY_RESEARCH_V022),
            derivatives,
            events,
            capture_decisions=capture_decisions,
        )
        outcomes = backtest.run(candles)
        if capture_decisions:
            baseline_decisions.extend(backtest.decision_log)
        return outcomes

    baseline = run(baseline_config, capture_decisions=True)
    classification = sample_classification(baseline)
    ablation: dict[str, Any] = {}
    for name, candidate in ablation_configs(baseline_config, derivatives is not None).items():
        ablation[name] = (
            {"status": "SKIPPED_NO_POINT_IN_TIME_DATA"}
            if candidate is None
            else research_summary(run(candidate))
        )
    stability = (
        {
            str(score): research_summary(
                run(
                    replace(
                        baseline_config,
                        strategy=replace(
                            baseline_config.strategy, factor_score_min=float(score)
                        ),
                    )
                )
            )
            for score in (65, 68, 70, 72, 75, 78, 80)
        }
        if classification == "ELIGIBLE_FOR_PARAMETER_RESEARCH"
        else {"status": f"SKIPPED_{classification}"}
    )
    cost_stress = {
        f"{multiplier:.1f}x": research_summary(stress_costs(baseline, multiplier))
        for multiplier in (1.0, 1.5, 2.0)
    }
    start_ms, end_ms = candles[0].open_time_ms, candles[-1].close_time_ms + 1
    return mark_legacy_diagnostic({
        "protocol": {
            "scope": "DEVELOPMENT_ONLY",
            "development_start_ms": DEV_START_MS,
            "development_end_ms_exclusive": DEV_END_MS,
            "sample_classification": classification,
            "holdout_accessed": False,
        },
        "baseline": research_summary(baseline),
        "baseline_feature_policy": {
            "derivatives_enabled": baseline_config.strategy.enable_derivatives_group,
            "order_book_enabled": baseline_config.strategy.enable_order_book_factor,
            "reason": (
                "point-in-time derivatives supplied"
                if derivatives is not None
                else "derivatives disabled because point-in-time history was not supplied"
            ),
        },
        "ablation": ablation,
        "walk_forward": walk_forward_report(baseline, start_ms, end_ms),
        "parameter_stability": stability,
        "cost_stress": cost_stress,
        "monte_carlo": monte_carlo(baseline, seed=seed),
        "bootstrap": bootstrap(baseline, seed=seed),
        "block_bootstrap": bootstrap(baseline, seed=seed, block_size=max(1, round(len(baseline) ** 0.5))),
        "decisions": baseline_decisions,
        "outcomes": baseline,
    })


def write_research_artifacts(
    output_dir: str | Path,
    suite: dict[str, Any],
    config: AppConfig,
    *,
    data_manifest_path: str | Path,
    seed: int,
) -> None:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable research run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    outcomes = suite.pop("outcomes")
    decisions = suite.pop("decisions")
    decision_counts: dict[str, int] = {}
    reject_counts: dict[str, int] = {}
    for decision in decisions:
        action = str(decision["decision"])
        reason = str(decision["reason_code"])
        decision_counts[action] = decision_counts.get(action, 0) + 1
        reject_counts[reason] = reject_counts.get(reason, 0) + 1
    suite["decision_audit"] = {
        "row_count": len(decisions),
        "decision_counts": dict(sorted(decision_counts.items())),
        "reason_code_counts": dict(
            sorted(reject_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
    }
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    ).stdout.strip()
    manifest = json.loads(Path(data_manifest_path).read_text(encoding="utf-8"))
    provenance = {
        "git_commit_sha": commit,
        "strategy_version": config.runtime.strategy_version,
        "feature_version": config.runtime.feature_version,
        "config_hash": config.config_hash,
        "dataset_checksums": [manifest.get("checksum_sha256")],
        "random_seed": seed,
        "validation_status": config.runtime.validation_status,
    }
    report = mark_legacy_diagnostic({"provenance": provenance, **suite})
    (target / "research_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    overall = report["baseline"]["overall"]
    (target / "research_report.md").write_text(
        "# Research Report\n\n"
        "Authority: `LEGACY_DIAGNOSTIC_ONLY` / `NOT_TESTABLE_FOR_NEW_PROMOTION`  \n"
        "Can promote: `false`\n\n"
        f"Strategy status: `{config.runtime.validation_status}`\n\n"
        f"Trades: {overall['trades']}  \nExpectancy R: {overall['expectancy_r']}  \n"
        f"Profit factor: {overall['profit_factor']}  \nMax drawdown R: {overall['max_drawdown_r']}\n",
        encoding="utf-8",
    )
    equity = 0.0
    with (target / "equity_curve.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("exited_at_ms", "equity_r"))
        for outcome in outcomes:
            if outcome.r_multiple is not None:
                equity += outcome.r_multiple
                writer.writerow((outcome.exited_at_ms, equity))
    try:
        pa = importlib.import_module("pyarrow")
        pq = importlib.import_module("pyarrow.parquet")
    except ImportError as exc:
        raise RuntimeError("install the research extra to write trades.parquet") from exc
    pq.write_table(pa.Table.from_pylist([item.as_dict() for item in outcomes]), target / "trades.parquet")
    pq.write_table(pa.Table.from_pylist(decisions), target / "decision_replay.parquet")
    samples: dict[str, list[dict[str, Any]]] = {}
    for action in sorted(decision_counts):
        samples[action] = [
            decision for decision in decisions if decision["decision"] == action
        ][:10]
    (target / "decision_samples.json").write_text(
        json.dumps(samples, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (target / "config.toml").open("w", encoding="utf-8") as handle:
        for section, values in asdict(config).items():
            handle.write(f"[{section}]\n")
            for key, value in values.items():
                handle.write(f"{key} = {json.dumps(value)}\n")
            handle.write("\n")
    shutil.copyfile(data_manifest_path, target / "data_manifest.json")
