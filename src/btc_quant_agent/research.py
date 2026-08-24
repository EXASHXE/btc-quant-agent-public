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
from .engine import QuantEngine


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
    return {
        "overall": metrics(outcomes),
        "by_year": {year: metrics(items) for year, items in sorted(by_year.items())},
        "by_direction": _segment(outcomes, "direction"),
        "by_setup": _segment(outcomes, "setup"),
        "by_regime": _segment(outcomes, "regime"),
    }


def walk_forward_report(
    outcomes: Sequence[TradeOutcome],
    start_ms: int,
    end_ms: int,
    *,
    train_months: int = 12,
    validation_months: int = 3,
    test_months: int = 3,
) -> list[dict[str, Any]]:
    month_ms = 30 * 86_400_000
    train = train_months * month_ms
    validation = validation_months * month_ms
    test = test_months * month_ms
    folds: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor + train + validation + test <= end_ms:
        test_start = cursor + train + validation
        test_end = test_start + test
        test_outcomes = [
            item
            for item in outcomes
            if item.exited_at_ms is not None and test_start <= item.exited_at_ms < test_end
        ]
        folds.append(
            {
                "train": [cursor, cursor + train],
                "validation": [cursor + train, test_start],
                "test": [test_start, test_end],
                "test_metrics": metrics(test_outcomes),
            }
        )
        cursor += test
    return folds


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
        output.append(
            {
                "timestamp_ms": now_ms,
                "price": decision_bar.close,
                "macro_4h": result.diagnostics.get("macro_4h"),
                "regime_1h": result.diagnostics.get("regime"),
                "structure_15m": result.diagnostics.get("structure_15m"),
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
            enable_volatility_liquidity_group=False,
            enable_order_book_factor=False,
        ),
        "B_plus_momentum": replace(
            base,
            enable_participation_group=False,
            enable_derivatives_group=False,
            enable_volatility_liquidity_group=False,
            enable_order_book_factor=False,
        ),
        "C_plus_participation": replace(
            base,
            enable_derivatives_group=False,
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

    def run(candidate: AppConfig, events: Sequence[FundingEvent] = funding_events) -> list[TradeOutcome]:
        return BacktestEngine(QuantEngine(candidate), derivatives, events).run(candles)

    baseline = run(baseline_config)
    ablation: dict[str, Any] = {}
    for name, candidate in ablation_configs(baseline_config, derivatives is not None).items():
        ablation[name] = (
            {"status": "SKIPPED_NO_POINT_IN_TIME_DATA"}
            if candidate is None
            else research_summary(run(candidate))
        )
    stability = {
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
    cost_stress: dict[str, Any] = {}
    for multiplier in (1.0, 1.5, 2.0):
        stressed = replace(
            baseline_config,
            risk=replace(
                baseline_config.risk,
                taker_fee_rate=baseline_config.risk.taker_fee_rate * multiplier,
                slippage_bps_per_side=baseline_config.risk.slippage_bps_per_side * multiplier,
                funding_stress_rate=baseline_config.risk.funding_stress_rate * multiplier,
            ),
        )
        stressed_events = [replace(event, funding_rate=event.funding_rate * multiplier) for event in funding_events]
        cost_stress[f"{multiplier:.1f}x"] = research_summary(run(stressed, stressed_events))
    start_ms, end_ms = candles[0].open_time_ms, candles[-1].close_time_ms
    holdout_start = end_ms - 6 * 30 * 86_400_000
    holdout = [item for item in baseline if item.exited_at_ms and item.exited_at_ms >= holdout_start]
    return {
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
        "walk_forward": walk_forward_report(baseline, start_ms, holdout_start),
        "final_holdout_6m": research_summary(holdout),
        "parameter_stability": stability,
        "cost_stress": cost_stress,
        "monte_carlo": monte_carlo(baseline, seed=seed),
        "bootstrap": bootstrap(baseline, seed=seed),
        "block_bootstrap": bootstrap(baseline, seed=seed, block_size=max(1, round(len(baseline) ** 0.5))),
        "outcomes": baseline,
    }


def write_research_artifacts(
    output_dir: str | Path,
    suite: dict[str, Any],
    config: AppConfig,
    *,
    data_manifest_path: str | Path,
    seed: int,
) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    outcomes = suite.pop("outcomes")
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
    report = {"provenance": provenance, **suite}
    (target / "research_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    overall = report["baseline"]["overall"]
    (target / "research_report.md").write_text(
        "# Research Report\n\n"
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
    with (target / "config.toml").open("w", encoding="utf-8") as handle:
        for section, values in asdict(config).items():
            handle.write(f"[{section}]\n")
            for key, value in values.items():
                handle.write(f"{key} = {json.dumps(value)}\n")
            handle.write("\n")
    shutil.copyfile(data_manifest_path, target / "data_manifest.json")
