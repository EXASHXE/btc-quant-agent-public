from __future__ import annotations

import collections
import hashlib
import importlib
import json
import random
import resource
import shutil
import statistics
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .causal_entry_research import IndexedOneMinuteSeries, _percentile, match_controls
from .config import AppConfig
from .domain import Candle, Direction
from .geometry_research import run_v033_geometry_audit
from .research import DEV_END_MS, DEV_START_MS

SEED = 36
SIMULATIONS = 2000
HORIZONS = (60, 120, 240, 480, 720)
PRIMARY_HORIZONS = (240, 480)
LATE_START_MS = 1_704_067_200_000
MIN_SEPARATION_MS = 24 * 60 * 60 * 1000
METRICS = (
    "signed_return_atr",
    "mfe_atr",
    "mae_atr",
    "reach_1_0",
    "reach_1_5",
    "reach_2_5",
)
MOVEMENT_METRICS = (
    "future_range_atr",
    "max_excursion_atr",
    "mfe_plus_mae_atr",
    "absolute_close_return_atr",
    "movement_1_5",
    "movement_2_5",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _split(timestamp_ms: int) -> str:
    return "LATE" if timestamp_ms >= LATE_START_MS else "EARLY"


def _episode_label(
    episode: dict[str, Any],
    series: IndexedOneMinuteSeries,
    horizon: int,
    direction: str | None = None,
) -> dict[str, Any]:
    bars, incomplete = series.bounded_window(int(episode["decision_close_ms"]), horizon)
    atr = float(episode["atr"])
    reference = float(episode["close"])
    chosen = Direction(direction or str(episode["direction"]))
    if incomplete or not bars or atr <= 0:
        return {"horizon_minutes": horizon, "incomplete": True}
    high = max(bar.high for bar in bars)
    low = min(bar.low for bar in bars)
    if chosen == Direction.LONG:
        signed = (bars[-1].close - reference) / atr
        mfe = max(0.0, high - reference) / atr
        mae = max(0.0, reference - low) / atr
    else:
        signed = (reference - bars[-1].close) / atr
        mfe = max(0.0, reference - low) / atr
        mae = max(0.0, high - reference) / atr
    return {
        "horizon_minutes": horizon,
        "incomplete": False,
        "signed_return_atr": signed,
        "mfe_atr": mfe,
        "mae_atr": mae,
        "reach_1_0": mfe >= 1.0,
        "reach_1_5": mfe >= 1.5,
        "reach_2_5": mfe >= 2.5,
    }


def build_episode_labels(
    episodes: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> list[dict[str, Any]]:
    return [
        {
            "episode_id": episode["episode_id"],
            "timestamp_ms": episode["timestamp_ms"],
            "year": episode["year"],
            "direction": episode["direction"],
            "split": _split(int(episode["timestamp_ms"])),
            **_episode_label(episode, series, horizon),
        }
        for episode in episodes
        for horizon in HORIZONS
    ]


def permute_directions_preserving_strata(
    episodes: Sequence[dict[str, Any]], seed: int = SEED
) -> dict[str, str]:
    groups: dict[tuple[int, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for episode in episodes:
        groups[(int(episode["year"]), int(episode["atr_decile"]))].append(episode)
    rng = random.Random(seed)
    output: dict[str, str] = {}
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda row: str(row["episode_id"]))
        directions = [str(row["direction"]) for row in rows]
        rng.shuffle(directions)
        output.update(
            (str(row["episode_id"]), direction)
            for row, direction in zip(rows, directions, strict=True)
        )
    return output


def _match_episode_pairs(
    episodes: Sequence[dict[str, Any]],
    left_predicate: Callable[[dict[str, Any]], bool],
    right_predicate: Callable[[dict[str, Any]], bool],
    *,
    opposite_direction: bool = False,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    right = [row for row in episodes if right_predicate(row)]
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for left in episodes:
        if not left_predicate(left):
            continue
        eligible = [
            row
            for row in right
            if int(row["year"]) == int(left["year"])
            and int(row["atr_decile"]) == int(left["atr_decile"])
            and (
                str(row["direction"]) != str(left["direction"])
                if opposite_direction
                else str(row["direction"]) == str(left["direction"])
            )
            and abs(int(row["timestamp_ms"]) - int(left["timestamp_ms"])) >= MIN_SEPARATION_MS
        ]
        if eligible:
            control = min(
                eligible,
                key=lambda row: (
                    abs(int(row["timestamp_ms"]) - int(left["timestamp_ms"])),
                    int(row["timestamp_ms"]),
                ),
            )
            pairs.append((left, control))
    return pairs


def _boolean_field(field: str, expected: bool) -> Callable[[dict[str, Any]], bool]:
    def predicate(row: dict[str, Any]) -> bool:
        return bool(row[field]) is expected

    return predicate


def _pair_rows(
    pairs: Sequence[tuple[dict[str, Any], dict[str, Any]]],
    label_by_id: dict[tuple[str, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for left, right in pairs:
        for horizon in PRIMARY_HORIZONS:
            left_label = label_by_id[(str(left["episode_id"]), horizon)]
            right_label = label_by_id[(str(right["episode_id"]), horizon)]
            if left_label["incomplete"] or right_label["incomplete"]:
                continue
            output.append(
                {
                    "pair_id": f"{left['episode_id']}->{right['episode_id']}",
                    "year": int(left["year"]),
                    "direction": str(left["direction"]),
                    "split": _split(int(left["timestamp_ms"])),
                    "horizon_minutes": horizon,
                    **{f"left_{metric}": left_label[metric] for metric in METRICS},
                    **{f"right_{metric}": right_label[metric] for metric in METRICS},
                }
            )
    return output


def _paired_same_episode_rows(
    episodes: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
    permuted: dict[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for episode in episodes:
        for horizon in PRIMARY_HORIZONS:
            real = _episode_label(episode, series, horizon)
            null = _episode_label(episode, series, horizon, permuted[str(episode["episode_id"])])
            if real["incomplete"] or null["incomplete"]:
                continue
            output.append(
                {
                    "pair_id": str(episode["episode_id"]),
                    "year": int(episode["year"]),
                    "direction": str(episode["direction"]),
                    "split": _split(int(episode["timestamp_ms"])),
                    "horizon_minutes": horizon,
                    **{f"left_{metric}": real[metric] for metric in METRICS},
                    **{f"right_{metric}": null[metric] for metric in METRICS},
                }
            )
    return output


def _delta(rows: Sequence[dict[str, Any]], metric: str) -> float | None:
    left = [float(row[f"left_{metric}"]) for row in rows]
    right = [float(row[f"right_{metric}"]) for row in rows]
    if not left or not right:
        return None
    if metric.startswith(("reach_", "movement_")):
        return statistics.mean(left) - statistics.mean(right)
    return statistics.median(left) - statistics.median(right)


def _pair_summary(
    rows: Sequence[dict[str, Any]], metrics: Sequence[str] = METRICS
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for horizon in PRIMARY_HORIZONS:
        block = [row for row in rows if int(row["horizon_minutes"]) == horizon]
        output[f"{horizon}m"] = {
            "pair_count": len(block),
            "metrics": {
                metric: {
                    "left_median_or_rate": (
                        statistics.mean(float(row[f"left_{metric}"]) for row in block)
                        if metric.startswith(("reach_", "movement_")) and block
                        else _median([float(row[f"left_{metric}"]) for row in block])
                    ),
                    "right_median_or_rate": (
                        statistics.mean(float(row[f"right_{metric}"]) for row in block)
                        if metric.startswith(("reach_", "movement_")) and block
                        else _median([float(row[f"right_{metric}"]) for row in block])
                    ),
                    "delta": _delta(block, metric),
                }
                for metric in metrics
            },
        }
    return output


def _pair_bootstrap(
    rows: Sequence[dict[str, Any]],
    metrics: Sequence[str] = METRICS,
    *,
    seed: int = SEED,
    simulations: int = SIMULATIONS,
) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        clusters[str(row["pair_id"])].append(row)
    ids = sorted(clusters)
    output: dict[str, Any] = {"seed": seed, "simulations": simulations, "cluster": "pair_id"}
    np = importlib.import_module("numpy")
    for horizon in PRIMARY_HORIZONS:
        output[f"{horizon}m"] = {}
        horizon_rows = {
            identity: next(
                (row for row in clusters[identity] if int(row["horizon_minutes"]) == horizon),
                None,
            )
            for identity in ids
        }
        usable_rows = [row for row in horizon_rows.values() if row is not None]
        rng = np.random.default_rng(seed + horizon)
        sample_batches = []
        for start in range(0, simulations, 100):
            size = min(100, simulations - start)
            sample_batches.append(rng.integers(0, len(usable_rows), size=(size, len(usable_rows))))
        for metric in metrics:
            left = np.asarray(
                [float(row[f"left_{metric}"]) for row in usable_rows],
                dtype=float,
            )
            right = np.asarray(
                [float(row[f"right_{metric}"]) for row in usable_rows],
                dtype=float,
            )
            values: list[float] = []
            for indices in sample_batches:
                if metric.startswith(("reach_", "movement_")):
                    batch = left[indices].mean(axis=1) - right[indices].mean(axis=1)
                else:
                    batch = np.median(left[indices], axis=1) - np.median(right[indices], axis=1)
                values.extend(float(value) for value in batch)
            output[f"{horizon}m"][metric] = {
                "p05": _percentile(values, 0.05),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
            }
    return output


def _permutation_distribution(
    episodes: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
    *,
    seed: int = SEED,
    simulations: int = SIMULATIONS,
) -> dict[str, Any]:
    groups: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for index, episode in enumerate(episodes):
        groups[(int(episode["year"]), int(episode["atr_decile"]))].append(index)
    directions = [1 if row["direction"] == "LONG" else -1 for row in episodes]
    rng = random.Random(seed)
    output: dict[str, Any] = {"seed": seed, "simulations": simulations}
    for horizon in PRIMARY_HORIZONS:
        eligible = [
            index
            for index, episode in enumerate(episodes)
            if not _episode_label(episode, series, horizon)["incomplete"]
        ]
        long_returns = {
            index: float(
                _episode_label(episodes[index], series, horizon, "LONG")["signed_return_atr"]
            )
            for index in eligible
        }
        real = [long_returns[index] * directions[index] for index in eligible]
        values: list[float] = []
        for _ in range(simulations):
            permuted = list(directions)
            for indices in groups.values():
                assigned = [permuted[index] for index in indices]
                rng.shuffle(assigned)
                for index, value in zip(indices, assigned, strict=True):
                    permuted[index] = value
            null = [long_returns[index] * permuted[index] for index in eligible]
            values.append(statistics.median(real) - statistics.median(null))
        output[f"{horizon}m"] = {
            "p05": _percentile(values, 0.05),
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
        }
    return output


def _stability(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    early_late = {
        split: {
            f"{horizon}m": _delta(
                [
                    row
                    for row in rows
                    if row["split"] == split and row["horizon_minutes"] == horizon
                ],
                "signed_return_atr",
            )
            for horizon in PRIMARY_HORIZONS
        }
        for split in ("EARLY", "LATE")
    }
    years = sorted({int(row["year"]) for row in rows})
    loyo = {
        str(year): {
            f"{horizon}m": _delta(
                [
                    row
                    for row in rows
                    if int(row["year"]) != year and row["horizon_minutes"] == horizon
                ],
                "signed_return_atr",
            )
            for horizon in PRIMARY_HORIZONS
        }
        for year in years
    }
    return {"early_late": early_late, "leave_one_year_out": loyo}


def _comparison(rows: Sequence[dict[str, Any]], metrics: Sequence[str] = METRICS) -> dict[str, Any]:
    return {
        "summary": _pair_summary(rows, metrics),
        "bootstrap": _pair_bootstrap(rows, metrics),
        "stability": _stability(rows) if "signed_return_atr" in metrics else {},
    }


def _increment_verdict(comparison: dict[str, Any]) -> str:
    summary = comparison["summary"]
    if int(summary["240m"]["pair_count"]) < 30:
        return "INCONCLUSIVE_LOW_SAMPLE"
    d4 = float(summary["240m"]["metrics"]["signed_return_atr"]["delta"])
    d8 = float(summary["480m"]["metrics"]["signed_return_atr"]["delta"])
    boot = comparison["bootstrap"]
    if (d4 <= 0 and d8 <= 0) or (
        float(boot["240m"]["signed_return_atr"]["p95"]) <= 0
        and float(boot["480m"]["signed_return_atr"]["p95"]) <= 0
    ):
        return "FALSIFIED"
    stable = comparison["stability"]
    early_late = [value for block in stable["early_late"].values() for value in block.values()]
    loyo_positive = sum(
        value is not None and float(value) > 0
        for block in stable["leave_one_year_out"].values()
        for value in block.values()
    )
    if (
        d4 > 0
        and d8 > 0
        and float(boot["240m"]["signed_return_atr"]["p05"]) >= -0.05
        and float(boot["480m"]["signed_return_atr"]["p05"]) >= -0.05
        and all(value is not None and float(value) >= 0 for value in early_late)
        and loyo_positive >= 4
    ):
        return "SUPPORTED"
    return "INCONCLUSIVE_MECHANISM"


def _real_stats(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for horizon in PRIMARY_HORIZONS:
        block = [
            row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]
        ]
        output[f"{horizon}m"] = {
            "count": len(block),
            "signed_return_atr_median": _median([float(row["signed_return_atr"]) for row in block]),
            "by_direction": {
                direction: {
                    "count": sum(row["direction"] == direction for row in block),
                    "signed_return_atr_median": _median(
                        [
                            float(row["signed_return_atr"])
                            for row in block
                            if row["direction"] == direction
                        ]
                    ),
                }
                for direction in ("LONG", "SHORT")
            },
        }
    return output


def _h14_verdict(permutation: dict[str, Any], matched: dict[str, Any], real: dict[str, Any]) -> str:
    if (
        int(permutation["summary"]["240m"]["pair_count"]) < 100
        or min(
            int(real["240m"]["by_direction"][direction]["count"]) for direction in ("LONG", "SHORT")
        )
        < 30
        or int(matched["summary"]["240m"]["pair_count"]) < 50
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    deltas = [
        float(comparison["summary"][f"{horizon}m"]["metrics"]["signed_return_atr"]["delta"])
        for comparison in (permutation, matched)
        for horizon in PRIMARY_HORIZONS
    ]
    perm_deltas = deltas[:2]
    perm_boot = permutation["bootstrap"]
    real_medians = [
        float(real[f"{horizon}m"]["signed_return_atr_median"]) for horizon in PRIMARY_HORIZONS
    ]
    if (
        all(value <= 0 for value in perm_deltas)
        or all(
            float(perm_boot[f"{horizon}m"]["signed_return_atr"]["p95"]) <= 0
            for horizon in PRIMARY_HORIZONS
        )
        or all(value <= 0 for value in real_medians)
    ):
        return "FALSIFIED"
    ci_ok = all(
        float(comparison["bootstrap"][f"{horizon}m"]["signed_return_atr"]["p05"]) >= -0.05
        for comparison in (permutation, matched)
        for horizon in PRIMARY_HORIZONS
    )
    sides_ok = all(
        float(real[f"{horizon}m"]["by_direction"][direction]["signed_return_atr_median"]) > 0
        for horizon in PRIMARY_HORIZONS
        for direction in ("LONG", "SHORT")
    )
    loyo_ok = all(
        value is not None and float(value) > 0
        for block in permutation["stability"]["leave_one_year_out"].values()
        for value in block.values()
    )
    early_late_ok = all(
        value is not None and float(value) > 0
        for block in permutation["stability"]["early_late"].values()
        for value in block.values()
    )
    return (
        "SUPPORTED"
        if all(value > 0 for value in deltas) and ci_ok and sides_ok and loyo_ok and early_late_ok
        else "INCONCLUSIVE_MECHANISM"
    )


def _stage_summary(
    episodes: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    ids = {str(row["episode_id"]) for row in episodes}
    output: dict[str, Any] = {"episode_count": len(ids), "horizons": {}}
    for horizon in PRIMARY_HORIZONS:
        block = [
            row
            for row in labels
            if str(row["episode_id"]) in ids
            and row["horizon_minutes"] == horizon
            and not row["incomplete"]
        ]
        output["horizons"][f"{horizon}m"] = {
            "count": len(block),
            **{
                metric: (
                    statistics.mean(float(row[metric]) for row in block)
                    if metric.startswith("reach_") and block
                    else _median([float(row[metric]) for row in block])
                )
                for metric in METRICS
            },
            "by_direction_signed_return": {
                direction: _median(
                    [
                        float(row["signed_return_atr"])
                        for row in block
                        if row["direction"] == direction
                    ]
                )
                for direction in ("LONG", "SHORT")
            },
        }
    return output


def _subset_delta(
    labels: Sequence[dict[str, Any]], base_ids: set[str], selected_ids: set[str], horizon: int
) -> float | None:
    base = [
        float(row["signed_return_atr"])
        for row in labels
        if str(row["episode_id"]) in base_ids
        and row["horizon_minutes"] == horizon
        and not row["incomplete"]
    ]
    selected = [
        float(row["signed_return_atr"])
        for row in labels
        if str(row["episode_id"]) in selected_ids
        and row["horizon_minutes"] == horizon
        and not row["incomplete"]
    ]
    return statistics.median(selected) - statistics.median(base) if base and selected else None


def _ladder(
    episodes: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]], h14: str
) -> dict[str, Any]:
    predicates: dict[str, Callable[[dict[str, Any]], bool]] = {
        "D0": lambda row: True,
        "D1": lambda row: bool(row["macro_4h_aligned"]),
        "D2": lambda row: bool(row["macro_4h_aligned"] and row["structure_15m_aligned"]),
        "D3": lambda row: bool(
            row["macro_4h_aligned"]
            and row["structure_15m_aligned"]
            and row["momentum_both_aligned"]
        ),
    }
    selected = {
        name: [row for row in episodes if predicate(row)] for name, predicate in predicates.items()
    }
    stages = {name: _stage_summary(rows, labels) for name, rows in selected.items()}
    adjacent: dict[str, Any] = {}
    for left, right in (("D0", "D1"), ("D1", "D2"), ("D2", "D3")):
        base_ids = {str(row["episode_id"]) for row in selected[left]}
        selected_ids = {str(row["episode_id"]) for row in selected[right]}
        deltas = {
            f"{horizon}m": _subset_delta(labels, base_ids, selected_ids, horizon)
            for horizon in PRIMARY_HORIZONS
        }
        rng = random.Random(SEED)
        boot: dict[str, Any] = {}
        base_list = sorted(base_ids)
        for horizon in PRIMARY_HORIZONS:
            values: list[float] = []
            by_id = {
                str(row["episode_id"]): float(row["signed_return_atr"])
                for row in labels
                if row["horizon_minutes"] == horizon and not row["incomplete"]
            }
            usable = [identity for identity in base_list if identity in by_id]
            for _ in range(SIMULATIONS):
                sample = [rng.choice(usable) for _ in usable] if usable else []
                all_values = [by_id[identity] for identity in sample]
                selected_values = [
                    by_id[identity] for identity in sample if identity in selected_ids
                ]
                if all_values and selected_values:
                    values.append(
                        statistics.median(selected_values) - statistics.median(all_values)
                    )
            boot[f"{horizon}m"] = {
                "p05": _percentile(values, 0.05),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
            }
        split_deltas = {
            split: {
                f"{horizon}m": _subset_delta(
                    [row for row in labels if row["split"] == split],
                    base_ids,
                    selected_ids,
                    horizon,
                )
                for horizon in PRIMARY_HORIZONS
            }
            for split in ("EARLY", "LATE")
        }
        adjacent[f"{right}-{left}"] = {
            "deltas": deltas,
            "bootstrap": boot,
            "early_late": split_deltas,
        }
    proposed = "NONE"
    if h14 == "SUPPORTED":
        proposed = "D0"
        for left, right in (("D0", "D1"), ("D1", "D2"), ("D2", "D3")):
            block = adjacent[f"{right}-{left}"]
            layer = stages[right]
            passes = (
                int(layer["horizons"]["240m"]["count"]) >= 30
                and all(float(block["deltas"][f"{h}m"] or -999) >= 0 for h in PRIMARY_HORIZONS)
                and all(
                    float(block["bootstrap"][f"{h}m"]["p05"] or -999) >= -0.10
                    for h in PRIMARY_HORIZONS
                )
                and all(
                    value is not None and float(value) >= 0
                    for split in block["early_late"].values()
                    for value in split.values()
                )
                and all(
                    float(
                        layer["horizons"][f"{h}m"]["by_direction_signed_return"][direction] or -999
                    )
                    >= 0
                    for h in PRIMARY_HORIZONS
                    for direction in ("LONG", "SHORT")
                )
            )
            if not passes:
                break
            proposed = right
    return {"stages": stages, "adjacent": adjacent, "proposed_direction_architecture": proposed}


def movement_label(
    identity: dict[str, Any], series: IndexedOneMinuteSeries, horizon: int
) -> dict[str, Any]:
    bars, incomplete = series.bounded_window(int(identity["decision_close_ms"]), horizon)
    atr = float(identity["atr"])
    reference = float(identity["close"])
    if incomplete or not bars or atr <= 0:
        return {"horizon_minutes": horizon, "incomplete": True}
    high = max(bar.high for bar in bars)
    low = min(bar.low for bar in bars)
    upper = max(0.0, high - reference) / atr
    lower = max(0.0, reference - low) / atr
    maximum = max(abs(high - reference), abs(low - reference)) / atr
    return {
        "horizon_minutes": horizon,
        "incomplete": False,
        "future_range_atr": (high - low) / atr,
        "max_excursion_atr": maximum,
        "mfe_plus_mae_atr": upper + lower,
        "absolute_close_return_atr": abs(bars[-1].close - reference) / atr,
        "movement_1_5": maximum >= 1.5,
        "movement_2_5": maximum >= 2.5,
    }


def _opportunity_rows(
    candidates: Sequence[dict[str, Any]],
    matches: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        for horizon in PRIMARY_HORIZONS:
            label = movement_label(candidate, series, horizon)
            if not label["incomplete"]:
                output.append(
                    {
                        "pair_id": str(candidate["candidate_id"]),
                        "candidate_id": candidate["candidate_id"],
                        "kind": "CANDIDATE",
                        "year": candidate["year"],
                        "split": _split(int(candidate["timestamp_ms"])),
                        **label,
                    }
                )
    for match in matches:
        for horizon in PRIMARY_HORIZONS:
            label = movement_label(match, series, horizon)
            if not label["incomplete"]:
                output.append(
                    {
                        "pair_id": str(match["candidate_id"]),
                        "candidate_id": match["candidate_id"],
                        "kind": "CONTROL",
                        "year": match["year"],
                        "split": _split(int(match["candidate_timestamp_ms"])),
                        **label,
                    }
                )
    return output


def _movement_delta(rows: Sequence[dict[str, Any]], metric: str) -> float | None:
    candidates = [float(row[metric]) for row in rows if row["kind"] == "CANDIDATE"]
    controls = [float(row[metric]) for row in rows if row["kind"] == "CONTROL"]
    if not candidates or not controls:
        return None
    if metric.startswith("movement_"):
        return statistics.mean(candidates) - statistics.mean(controls)
    return statistics.median(candidates) - statistics.median(controls)


def _opportunity_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for horizon in PRIMARY_HORIZONS:
        block = [row for row in rows if row["horizon_minutes"] == horizon]
        output[f"{horizon}m"] = {
            "candidate_count": len(
                {row["candidate_id"] for row in block if row["kind"] == "CANDIDATE"}
            ),
            "control_count": sum(row["kind"] == "CONTROL" for row in block),
            "metrics": {
                metric: {
                    "candidate_median_or_rate": (
                        statistics.mean(
                            float(row[metric]) for row in block if row["kind"] == "CANDIDATE"
                        )
                        if metric.startswith("movement_")
                        else _median(
                            [float(row[metric]) for row in block if row["kind"] == "CANDIDATE"]
                        )
                    ),
                    "control_median_or_rate": (
                        statistics.mean(
                            float(row[metric]) for row in block if row["kind"] == "CONTROL"
                        )
                        if metric.startswith("movement_")
                        else _median(
                            [float(row[metric]) for row in block if row["kind"] == "CONTROL"]
                        )
                    ),
                    "delta": _movement_delta(block, metric),
                }
                for metric in MOVEMENT_METRICS
            },
        }
    return output


def _opportunity_bootstrap(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    pair_rows: list[dict[str, Any]] = []
    clusters: dict[tuple[str, int], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        clusters[(str(row["candidate_id"]), int(row["horizon_minutes"]))].append(row)
    for (identity, horizon), block in clusters.items():
        candidate = next((row for row in block if row["kind"] == "CANDIDATE"), None)
        controls = [row for row in block if row["kind"] == "CONTROL"]
        if candidate is None or not controls:
            continue
        pair_rows.append(
            {
                "pair_id": identity,
                "horizon_minutes": horizon,
                **{f"left_{metric}": candidate[metric] for metric in MOVEMENT_METRICS},
                **{
                    f"right_{metric}": (
                        statistics.mean(float(row[metric]) for row in controls)
                        if metric.startswith("movement_")
                        else statistics.median(float(row[metric]) for row in controls)
                    )
                    for metric in MOVEMENT_METRICS
                },
            }
        )
    return _pair_bootstrap(pair_rows, MOVEMENT_METRICS)


def _opportunity_verdict(
    summary: dict[str, Any], bootstrap: dict[str, Any], rows: Sequence[dict[str, Any]]
) -> str:
    if int(summary["240m"]["candidate_count"]) < 30:
        return "INCONCLUSIVE_LOW_SAMPLE"
    required = ("future_range_atr", "max_excursion_atr", "movement_1_5")
    deltas = {
        horizon: [float(summary[f"{horizon}m"]["metrics"][metric]["delta"]) for metric in required]
        for horizon in PRIMARY_HORIZONS
    }
    if all(value <= 0 for values in deltas.values() for value in values) or all(
        float(bootstrap[f"{horizon}m"]["future_range_atr"]["p95"]) <= 0
        for horizon in PRIMARY_HORIZONS
    ):
        return "FALSIFIED"
    split_range = {
        split: {
            horizon: _movement_delta(
                [
                    row
                    for row in rows
                    if row["split"] == split and row["horizon_minutes"] == horizon
                ],
                "future_range_atr",
            )
            for horizon in PRIMARY_HORIZONS
        }
        for split in ("EARLY", "LATE")
    }
    if (
        all(value > 0 for values in deltas.values() for value in values)
        and all(
            float(bootstrap[f"{horizon}m"]["future_range_atr"]["p05"]) >= -0.05
            for horizon in PRIMARY_HORIZONS
        )
        and all(
            value is not None and float(value) > 0
            for values in split_range.values()
            for value in values.values()
        )
    ):
        return "SUPPORTED"
    return "INCONCLUSIVE_MECHANISM"


def _opportunity_analysis(
    candidates: Sequence[dict[str, Any]],
    control_pool: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
) -> tuple[dict[str, Any], dict[str, Any]]:
    pattern_times = {int(row["timestamp_ms"]) for row in candidates}
    pool = [
        {**row, "is_excluded_pattern": int(row["timestamp_ms"]) in pattern_times}
        for row in control_pool
    ]
    matches = match_controls(candidates, pool)
    rows = _opportunity_rows(candidates, matches, series)
    summary = _opportunity_summary(rows)
    bootstrap = _opportunity_bootstrap(rows)
    split_range = {
        split: {
            f"{horizon}m_future_range_delta": _movement_delta(
                [
                    row
                    for row in rows
                    if row["split"] == split and row["horizon_minutes"] == horizon
                ],
                "future_range_atr",
            )
            for horizon in PRIMARY_HORIZONS
        }
        for split in ("EARLY", "LATE")
    }
    return (
        {
            "summary": summary,
            "early_late": split_range,
            "verdict": _opportunity_verdict(summary, bootstrap, rows),
            "matched_rows": len(matches),
            "unique_controls": len({row["control_id"] for row in matches}),
        },
        bootstrap,
    )


def _development_only(rows: Sequence[dict[str, Any]]) -> None:
    for row in rows:
        for key, value in row.items():
            if value is None:
                continue
            if key.endswith(("timestamp_ms", "close_ms")) and not (
                DEV_START_MS <= int(value) < DEV_END_MS
            ):
                raise ValueError("v0.3.6 holdout firewall rejected row")


def run_v036_directional_architecture(
    candles: Sequence[Candle], config: AppConfig, *, seed: int = SEED
) -> dict[str, Any]:
    started = time.perf_counter()
    frozen = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    if (
        frozen.execution.mode != "disabled"
        or frozen.execution.auto_execute
        or frozen.execution.allow_live
    ):
        raise ValueError("v0.3.6 requires disabled execution")
    replay = run_v033_geometry_audit(
        candles,
        frozen,
        (),
        capture_trend_controls=True,
        capture_breakout_qualification=True,
        capture_directional_episodes=True,
    )
    episodes = list(replay["directional_episode_rows"])
    _development_only(episodes)
    series = IndexedOneMinuteSeries(candles)
    labels = build_episode_labels(episodes, series)
    label_by_id = {(str(row["episode_id"]), int(row["horizon_minutes"])): row for row in labels}
    permuted = permute_directions_preserving_strata(episodes, seed)
    permutation_rows = _paired_same_episode_rows(episodes, series, permuted)
    permutation = _comparison(permutation_rows)
    permutation["permutation_distribution"] = _permutation_distribution(episodes, series, seed=seed)
    opposite_pairs = _match_episode_pairs(
        episodes, lambda row: True, lambda row: True, opposite_direction=True
    )
    matched = _comparison(_pair_rows(opposite_pairs, label_by_id))
    real = _real_stats(labels)
    h14 = _h14_verdict(permutation, matched, real)

    comparisons: dict[str, Any] = {}
    for name, field in (
        ("macro", "macro_4h_aligned"),
        ("structure", "structure_15m_aligned"),
        ("rsi", "rsi_15m_aligned"),
        ("roc", "roc_15m_aligned"),
        ("both", "momentum_both_aligned"),
    ):
        pairs = _match_episode_pairs(
            episodes,
            _boolean_field(field, True),
            _boolean_field(field, False),
        )
        comparison = _comparison(_pair_rows(pairs, label_by_id))
        comparison["verdict"] = _increment_verdict(comparison)
        comparisons[name] = comparison

    h17_components = {name: comparisons[name]["verdict"] for name in ("rsi", "roc", "both")}
    if h17_components["both"] == "SUPPORTED":
        h17 = "SUPPORTED"
    elif all(value == "FALSIFIED" for value in h17_components.values()):
        h17 = "FALSIFIED"
    elif (
        h17_components["both"] == "INCONCLUSIVE_LOW_SAMPLE"
        and "SUPPORTED" not in h17_components.values()
    ):
        h17 = "INCONCLUSIVE_LOW_SAMPLE"
    else:
        h17 = "INCONCLUSIVE_MECHANISM"
    ladder = _ladder(episodes, labels, h14)

    control_pool = list(replay["trend_control_rows"])
    br_events = list(replay["breakout_qualification_rows"])
    tp_events = list(replay["tp_geometry_rows"])
    br_opportunity, br_bootstrap = _opportunity_analysis(br_events, control_pool, series)
    tp_opportunity, tp_bootstrap = _opportunity_analysis(tp_events, control_pool, series)
    setup_verdicts = (br_opportunity["verdict"], tp_opportunity["verdict"])
    if "SUPPORTED" in setup_verdicts:
        h18 = "SUPPORTED"
    elif all(value == "FALSIFIED" for value in setup_verdicts):
        h18 = "FALSIFIED"
    elif all(value == "INCONCLUSIVE_LOW_SAMPLE" for value in setup_verdicts):
        h18 = "INCONCLUSIVE_LOW_SAMPLE"
    else:
        h18 = "INCONCLUSIVE_MECHANISM"

    by_year_direction: dict[str, Any] = {}
    for year in sorted({int(row["year"]) for row in episodes}):
        for direction in ("LONG", "SHORT"):
            ids = {
                str(row["episode_id"])
                for row in episodes
                if int(row["year"]) == year and row["direction"] == direction
            }
            by_year_direction[f"{year}_{direction}"] = {
                "episodes": len(ids),
                **{
                    f"{horizon}m_signed_return_atr_median": _median(
                        [
                            float(row["signed_return_atr"])
                            for row in labels
                            if str(row["episode_id"]) in ids
                            and row["horizon_minutes"] == horizon
                            and not row["incomplete"]
                        ]
                    )
                    for horizon in PRIMARY_HORIZONS
                },
            }
    episode_summary = {
        "episode_count": len(episodes),
        "long_episodes": sum(row["direction"] == "LONG" for row in episodes),
        "short_episodes": sum(row["direction"] == "SHORT" for row in episodes),
        "median_duration_hours": _median([float(row["duration_hours"]) for row in episodes]),
        "by_year": dict(sorted(collections.Counter(int(row["year"]) for row in episodes).items())),
        "real_direction": real,
    }
    late_real_positive = all(
        _median(
            [
                float(row["signed_return_atr"])
                for row in labels
                if row["split"] == "LATE"
                and row["horizon_minutes"] == horizon
                and not row["incomplete"]
            ]
        )
        is not None
        and float(
            _median(
                [
                    float(row["signed_return_atr"])
                    for row in labels
                    if row["split"] == "LATE"
                    and row["horizon_minutes"] == horizon
                    and not row["incomplete"]
                ]
            )
            or 0
        )
        > 0
        for horizon in PRIMARY_HORIZONS
    )
    proposed = ladder["proposed_direction_architecture"]
    if h14 == "SUPPORTED" and proposed != "NONE" and late_real_positive and h18 == "SUPPORTED":
        recommendation = "RECOMMEND_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE"
    elif h14 == "SUPPORTED" and proposed != "NONE" and late_real_positive and h18 == "FALSIFIED":
        recommendation = "RECOMMEND_DIRECTION_ONLY_PROTOTYPE"
    elif h14 == "FALSIFIED" or proposed == "NONE":
        recommendation = "RECOMMEND_NEW_FEATURE_FAMILY_RESEARCH"
    else:
        recommendation = "INCONCLUSIVE_CONTINUE_ARCHITECTURE_DIAGNOSTIC"
    return {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "start_ms": DEV_START_MS,
            "end_ms_exclusive": DEV_END_MS,
            "validation_status": frozen.runtime.validation_status,
            "execution_mode": frozen.execution.mode,
            "candidate_freeze": False,
        },
        "episode_summary": episode_summary,
        "h14_regime_directionality": {"real": real, "verdict": h14},
        "h14_null_permutation": permutation,
        "h14_matched_opposite": matched,
        "h15_macro_increment": comparisons["macro"],
        "h16_structure_increment": comparisons["structure"],
        "h17_momentum_increment": {
            "rsi": comparisons["rsi"],
            "roc": comparisons["roc"],
            "both": comparisons["both"],
            "component_verdicts": h17_components,
            "verdict": h17,
        },
        "direction_ladder": ladder,
        "early_late_confirmation": {
            "h14_real_minus_permutation": permutation["stability"]["early_late"],
            "late_real_direction_positive_4h_8h": late_real_positive,
        },
        "br_opportunity_layer": br_opportunity,
        "tp_opportunity_layer": tp_opportunity,
        "opportunity_bootstrap": {"BR_PATTERN": br_bootstrap, "TP_PATTERN": tp_bootstrap},
        "by_year_direction": by_year_direction,
        "hypothesis_verdicts": {
            "H14": h14,
            "H15": comparisons["macro"]["verdict"],
            "H16": comparisons["structure"]["verdict"],
            "H17": h17,
            "H18": h18,
        },
        "proposed_direction_architecture": proposed,
        "opportunity_layer_setups": [
            setup
            for setup, block in (("BR_PATTERN", br_opportunity), ("TP_PATTERN", tp_opportunity))
            if block["verdict"] == "SUPPORTED"
        ],
        "recommendation": recommendation,
        "overall_status": "DIRECTIONAL_ARCHITECTURE_RESET_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "replay": replay["performance"],
        },
        "regime_episodes": episodes,
    }


def write_v036_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    *,
    seed: int = SEED,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable v0.3.6 run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "data_manifest.json")
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    pq.write_table(
        pa.Table.from_pylist(result["regime_episodes"]), target / "regime_episodes.parquet"
    )
    names = (
        "episode_summary",
        "h14_regime_directionality",
        "h14_null_permutation",
        "h14_matched_opposite",
        "h15_macro_increment",
        "h16_structure_increment",
        "h17_momentum_increment",
        "direction_ladder",
        "early_late_confirmation",
        "br_opportunity_layer",
        "tp_opportunity_layer",
        "opportunity_bootstrap",
        "by_year_direction",
    )
    for name in names:
        (target / f"{name}.json").write_text(
            json.dumps(result[name], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        git_sha = "UNKNOWN"
    summary = {
        key: value
        for key, value in result.items()
        if key not in {"regime_episodes"}
        and key
        not in {
            "h14_null_permutation",
            "h14_matched_opposite",
            "h15_macro_increment",
            "h16_structure_increment",
            "h17_momentum_increment",
            "direction_ladder",
            "br_opportunity_layer",
            "tp_opportunity_layer",
            "opportunity_bootstrap",
            "by_year_direction",
        }
    }
    summary["provenance"] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "config": asdict(config),
        "config_hash": config.config_hash,
        "protocol_sha256": _sha256(protocol),
        "data_manifest_sha256": _sha256(manifest),
        "seed": seed,
        "bootstrap_simulations": SIMULATIONS,
    }
    (target / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
