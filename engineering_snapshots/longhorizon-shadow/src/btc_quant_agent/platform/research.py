"""Small reproducible synthetic experiments; never touches the historical PRIMARY registry."""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import build_pipeline, run
from .config import PlatformConfig
from .core import ExperimentResult, fingerprint, primitive
from .data import SyntheticProvider
from .factors import quality_table
from .ml import DatasetBuilder


def factor_research(config: PlatformConfig, source_identity: str):
    events = SyntheticProvider().events(config)
    pipeline, _ = build_pipeline(events, config)
    quality = quality_table(pipeline)
    selected = [f.id for f in config.factors] or ["ROC", "RSI", "MA_DISTANCE", "RELATIVE_VOLUME"]
    values = pd.concat(
        [pd.DataFrame({id: pipeline.series(s, id) for id in selected}) for s in pipeline.frames]
    )
    corr = values.corr(min_periods=20)
    redundancy = [
        {"first": a, "second": b, "correlation": float(corr.loc[a, b])}
        for i, a in enumerate(selected)
        for b in selected[i + 1 :]
        if np.isfinite(corr.loc[a, b]) and abs(corr.loc[a, b]) > 0.85
    ]
    baseline = run(config, events, source_identity)
    ablations = []
    for factor in config.factors:
        trial = config.model_copy(update={"factors": [f for f in config.factors if f.id != factor.id]})
        result = run(trial, events, source_identity)
        ablations.append(
            {"removed": factor.id, "config_hash": trial.hash, "metrics": result["run"]["metrics"]}
        )
    equal = config.model_copy(
        update={"factors": [f.model_copy(update={"weight": 1.0}) for f in config.factors]}
    )
    equal_result = run(equal, events, source_identity)
    return {
        "exposure": "SYNTHETIC",
        "config_hash": config.hash,
        "source_identity": source_identity,
        "quality": quality,
        "correlation": json.loads(corr.to_json()),
        "redundancy": redundancy,
        "baseline": baseline["run"],
        "equal_weight": equal_result["run"],
        "ablations": ablations,
        "configurations_evaluated": 2 + len(ablations),
        "warnings": ["In-sample exploratory engineering comparison; no best-configuration Alpha claim."],
    }


def walk_forward(config: PlatformConfig, folds: int = 3):
    data = DatasetBuilder().build(config)
    unique = np.unique(data.times)
    boundaries = np.linspace(len(unique) // 2, len(unique), folds + 1, dtype=int)
    result = []
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        start, end = unique[left], unique[min(right, len(unique) - 1)]
        train = np.flatnonzero(
            (data.times < start)
            & (data.label_ends < start - config.ml.embargo * config.interval_seconds * 1000)
        )
        val = np.flatnonzero((data.times >= start) & (data.times < end))
        result.append(
            {
                "train_samples": len(train),
                "validation_samples": len(val),
                "train_max_label_end": int(data.label_ends[train].max()),
                "validation_start": int(start),
                "validation_end": int(end),
                "scaler_fit_partition": "TRAIN_ONLY",
            }
        )
    return result


def search(
    config: PlatformConfig, grid: dict, source_identity: str, *, method: str = "grid", max_trials: int = 12
):
    if method not in ("grid", "random"):
        raise ValueError("search method must be grid or random")
    if not 1 <= max_trials <= 100:
        raise ValueError("max_trials must be in [1,100]")
    allowed = {
        "entry.min_score",
        "entry.region_bps",
        "exits.trailing_atr",
        "exits.stop_lookback",
        "risk.per_trade",
    }
    if not set(grid) <= allowed:
        raise ValueError("unsupported search parameters")
    keys = sorted(grid)
    if any(not isinstance(grid[k], list) or not grid[k] for k in keys):
        raise ValueError("grid values must be nonempty lists")
    choices = list(product(*(grid[k] for k in keys)))
    if method == "random":
        np.random.default_rng(config.seed).shuffle(choices)
    events = SyntheticProvider().events(config)
    results = []
    for choice in choices[:max_trials]:
        raw = config.model_dump(mode="json")
        for key, value in zip(keys, choice):
            section, field = key.split(".")
            raw[section][field] = value
        trial = PlatformConfig.model_validate(raw)
        result = run(trial, events, source_identity)
        results.append({"parameters": dict(zip(keys, choice)), "run": result["run"]})
    return {
        "method": method,
        "seed": config.seed,
        "configurations_evaluated": len(results),
        "results": results,
        "warnings": ["Synthetic exploratory search; no PRIMARY trial registration and no confirmed Alpha."],
    }


def register_experiment(result: dict, config: PlatformConfig, path, source_identity: str):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    id = fingerprint([config.hash, source_identity, result])
    events = SyntheticProvider().events(config)
    entry = ExperimentResult(
        id,
        config.hash,
        source_identity,
        (events[0].decision_ts, events[-1].decision_ts),
        "SYNTHETIC",
        {"configurations_evaluated": result.get("configurations_evaluated", 1)},
        ("Development-only; not the protected historical registry or a PRIMARY trial.",),
        (id + ".json",),
    )
    artifact = path / (id + ".json")
    encoded = json.dumps({"registry": primitive(entry), "result": result}, indent=2, allow_nan=False) + "\n"
    if artifact.exists() and artifact.read_text() != encoded:
        raise ValueError("EXPERIMENT_ARTIFACT_CONFLICT")
    artifact.write_text(encoded)
    return entry


def policy_attribution(config: PlatformConfig, source_identity: str):
    """Explicit policy comparisons, with unmatched entry/occupancy effects disclosed."""
    events = SyntheticProvider().events(config)
    baseline = run(config, events, source_identity)
    delayed = config.model_copy(
        update={"execution": config.execution.model_copy(update={"delay_minutes": 5})}
    )
    fixed = config.model_copy(
        update={
            "exits": config.exits.model_copy(
                update={"trailing_atr": 100000.0, "partial_at_r": 100000.0, "max_holding_bars": 10}
            )
        }
    )
    entry = run(delayed, events, source_identity)
    management = run(fixed, events, source_identity)
    return {
        "exposure": "SYNTHETIC",
        "baseline": baseline["run"],
        "entry_timing_comparison": {
            "manual_delay_minutes": 5,
            "run": entry["run"],
            "total_pnl_delta": entry["run"]["metrics"]["total_marked_modeled_net_pnl"]
            - baseline["run"]["metrics"]["total_marked_modeled_net_pnl"],
        },
        "exit_management_comparison": {
            "policy": "initial stop plus ten-bar time exit; no partial/trail",
            "run": management["run"],
            "total_pnl_delta": management["run"]["metrics"]["total_marked_modeled_net_pnl"]
            - baseline["run"]["metrics"]["total_marked_modeled_net_pnl"],
        },
        "configurations_evaluated": 3,
        "limitations": [
            "Policy comparisons include endogenous position occupancy and subsequent selection effects.",
            "These are descriptive entry-policy and exit-policy differences, not isolated causal value estimates.",
        ],
    }
