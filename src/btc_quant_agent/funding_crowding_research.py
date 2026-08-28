from __future__ import annotations

import bisect
import collections
import csv
import hashlib
import importlib
import inspect
import itertools
import json
import platform
import random
import resource
import shutil
import statistics
import subprocess
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import FundingEvent, resample
from .breakout_edge_research import _spearman
from .causal_entry_research import IndexedOneMinuteSeries
from .config import AppConfig
from .data.collector import collect_derivative_snapshot
from .data.derivatives import DERIVATIVE_FIELDS, HistoricalDerivativeStore
from .directional_architecture_research import movement_label
from .domain import Candle
from .engine import HistoricalFeatureCache, QuantEngine
from .geometry_research import run_v033_geometry_audit
from .research import DEV_END_MS, DEV_START_MS

SEED = 37
SIMULATIONS = 2000
WINDOW = 270
PRIMARY_HORIZONS = (240, 480)
H19_HORIZONS = (240, 480, 1440)
LATE_START_MS = 1_704_067_200_000
STALE_MS = (8 * 60 + 5) * 60_000
DAY_MS = 86_400_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def causal_funding_percentile(history: Sequence[float], current: float) -> float:
    if len(history) != WINDOW:
        raise ValueError("funding percentile requires exactly 270 prior settlements")
    below = sum(value < current for value in history)
    equal = sum(value == current for value in history)
    return (below + 0.5 * equal) / WINDOW


def funding_direction(percentile: float) -> str:
    if percentile <= 0.25:
        return "LONG"
    if percentile >= 0.75:
        return "SHORT"
    return "NO_BIAS"


def build_funding_features(events: Sequence[FundingEvent]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    rates = [float(event.funding_rate) for event in events]
    trailing: collections.deque[float] = collections.deque(maxlen=WINDOW)
    for index, event in enumerate(events):
        if len(trailing) < WINDOW:
            percentile = None
            status = "WARMUP_INCOMPLETE"
            direction = "NO_BIAS"
        else:
            percentile = causal_funding_percentile(tuple(trailing), rates[index])
            direction = funding_direction(percentile)
            status = "EXTREME" if direction != "NO_BIAS" else "MIDDLE"
        output.append(
            {
                "event_id": f"F:{event.timestamp_ms}",
                "funding_index": index,
                "timestamp_ms": event.timestamp_ms,
                "funding_rate": event.funding_rate,
                "mark_price": event.mark_price,
                "funding_percentile": percentile,
                "funding_direction": direction,
                "feature_status": status,
                "history_count": len(trailing),
            }
        )
        trailing.append(rates[index])
    return output


def audit_funding_data(
    path: str | Path, manifest: dict[str, Any]
) -> tuple[dict[str, Any], list[FundingEvent]]:
    source = str(manifest.get("source", ""))
    source_root = str(manifest.get("source_root", ""))
    if "Binance Public Data" not in source or "data.binance.vision" not in source_root:
        raise RuntimeError("FUNDING_FEATURE_QUALIFICATION_BLOCKED: unverified funding source")
    target = Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    timestamps = [int(row["timestamp_ms"]) for row in raw_rows]
    if timestamps != sorted(timestamps):
        raise RuntimeError("FUNDING_FEATURE_QUALIFICATION_BLOCKED: unsorted funding timestamps")
    duplicates = len(timestamps) - len(set(timestamps))
    if duplicates:
        raise RuntimeError("FUNDING_FEATURE_QUALIFICATION_BLOCKED: duplicate funding timestamps")
    checksum = _sha256(target)
    expected = str(manifest["funding"]["checksum_sha256"])
    if checksum != expected:
        raise RuntimeError("FUNDING_FEATURE_QUALIFICATION_BLOCKED: funding checksum mismatch")
    development_rows = [row for row in raw_rows if int(row["timestamp_ms"]) < DEV_END_MS]
    rates = [float(row["funding_rate"]) for row in development_rows]
    dev_times = [int(row["timestamp_ms"]) for row in development_rows]
    intervals = [right - left for left, right in itertools.pairwise(dev_times)]
    irregular = [value for value in intervals if abs(value - 8 * 60 * 60_000) > 5 * 60_000]
    missing_mark = sum(not row.get("mark_price") for row in development_rows)
    events = [
        FundingEvent(
            timestamp_ms=int(row["timestamp_ms"]),
            funding_rate=float(row["funding_rate"]),
            mark_price=float(row["mark_price"]) if row.get("mark_price") else None,
        )
        for row in development_rows
        if DEV_START_MS <= int(row["timestamp_ms"]) < DEV_END_MS
    ]
    return (
        {
            "source": source,
            "source_root": source_root,
            "point_in_time_verified": True,
            "sha256": checksum,
            "total_rows_manifest": int(manifest["funding"]["row_count"]),
            "development_rows": len(events),
            "post_development_rows_metadata_count": len(raw_rows) - len(development_rows),
            "sorted_timestamps": True,
            "duplicates": duplicates,
            "irregular_intervals_over_5m_from_8h": len(irregular),
            "irregular_interval_ms_distribution": dict(
                sorted(collections.Counter(intervals).items())
            ),
            "missing_mark_prices": missing_mark,
            "funding_rate_min": min(rates),
            "funding_rate_max": max(rates),
            "funding_rate_median": statistics.median(rates),
            "first_development_timestamp_ms": min(event.timestamp_ms for event in events),
            "last_development_timestamp_ms": max(event.timestamp_ms for event in events),
            "holdout_effect_sizes_read": False,
        },
        events,
    )


class StrictAfterPriceSeries:
    def __init__(self, candles: Sequence[Candle]) -> None:
        self.candles = tuple(candles)
        self.opens = tuple(bar.open_time_ms for bar in candles)

    def label(
        self,
        timestamp_ms: int,
        horizon_minutes: int,
        atr: float,
        direction: str,
    ) -> dict[str, Any]:
        start = bisect.bisect_right(self.opens, timestamp_ms)
        end_open = self.opens[start] + horizon_minutes * 60_000 if start < len(self.opens) else 0
        end = bisect.bisect_left(self.opens, end_open)
        incomplete = (
            start >= len(self.opens) or end - start != horizon_minutes or end_open > DEV_END_MS
        )
        if incomplete or atr <= 0:
            return {"horizon_minutes": horizon_minutes, "incomplete": True}
        bars = self.candles[start:end]
        reference = bars[0].open
        raw_return = (bars[-1].close - reference) / atr
        high = max(bar.high for bar in bars)
        low = min(bar.low for bar in bars)
        if direction == "LONG":
            signed = raw_return
            mfe = max(0.0, high - reference) / atr
            mae = max(0.0, reference - low) / atr
        else:
            signed = -raw_return
            mfe = max(0.0, reference - low) / atr
            mae = max(0.0, high - reference) / atr
        return {
            "horizon_minutes": horizon_minutes,
            "incomplete": False,
            "reference_open_time_ms": bars[0].open_time_ms,
            "reference_price": reference,
            "signed_return_atr": signed,
            "raw_return_atr": raw_return,
            "mfe_atr": mfe,
            "mae_atr": mae,
            "reach_1_0": mfe >= 1.0,
            "reach_1_5": mfe >= 1.5,
            "reach_2_5": mfe >= 2.5,
        }


def _decorate_funding_features(
    feature_rows: list[dict[str, Any]], candles: Sequence[Candle], config: AppConfig
) -> None:
    hourly = resample(candles, "1h")
    closes = [bar.close_time_ms for bar in hourly]
    engine = QuantEngine(config, HistoricalFeatureCache())
    for row in feature_rows:
        if row["feature_status"] == "WARMUP_INCOMPLETE":
            continue
        index = bisect.bisect_right(closes, int(row["timestamp_ms"])) - 1
        history = hourly[max(0, index - config.data.history_limit_1h + 1) : index + 1]
        features = engine.diagnostic_features("1h", history)
        row.update(
            {
                "atr": features.atr,
                "atr_percentile": features.atr_percentile,
                "atr_decile": min(9, int(features.atr_percentile * 10)),
                "atr_feature_close_ms": features.bar_close_time_ms,
                "year": datetime.fromtimestamp(int(row["timestamp_ms"]) / 1000, UTC).year,
                "week_cluster": datetime.fromtimestamp(
                    int(row["timestamp_ms"]) / 1000, UTC
                ).strftime("%G-W%V"),
                "split": "LATE" if int(row["timestamp_ms"]) >= LATE_START_MS else "EARLY",
            }
        )


def _funding_label_rows(
    features: Sequence[dict[str, Any]], series: StrictAfterPriceSeries
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in features:
        if row["funding_direction"] == "NO_BIAS":
            continue
        for horizon in H19_HORIZONS:
            label = series.label(
                int(row["timestamp_ms"]),
                horizon,
                float(row["atr"]),
                str(row["funding_direction"]),
            )
            output.append(
                {
                    "event_id": f"F:{row['timestamp_ms']}",
                    "timestamp_ms": row["timestamp_ms"],
                    "year": row["year"],
                    "week_cluster": row["week_cluster"],
                    "split": row["split"],
                    "funding_direction": row["funding_direction"],
                    "funding_percentile": row["funding_percentile"],
                    **label,
                }
            )
    return output


def _median(rows: Sequence[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if not row.get("incomplete")]
    return statistics.median(values) if values else None


def _cluster_bootstrap_median(
    rows: Sequence[dict[str, Any]],
    field: str,
    cluster_field: str,
    *,
    seed: int = SEED,
    simulations: int = SIMULATIONS,
) -> dict[str, Any]:
    clusters: dict[str, list[float]] = collections.defaultdict(list)
    for row in rows:
        if not row.get("incomplete"):
            clusters[str(row[cluster_field])].append(float(row[field]))
    ids = sorted(clusters)
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(simulations):
        sample_ids = [rng.choice(ids) for _ in ids]
        sample = [value for identity in sample_ids for value in clusters[identity]]
        values.append(statistics.median(sample))
    return {
        "cluster_field": cluster_field,
        "cluster_count": len(ids),
        "event_count": sum(len(values) for values in clusters.values()),
        "p05": _percentile(values, 0.05),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
    }


def _permutation_analysis(
    identities: Sequence[dict[str, Any]],
    label_rows: Sequence[dict[str, Any]],
    *,
    stratum_fields: Sequence[str],
) -> dict[str, Any]:
    by_event_horizon = {
        (str(row["event_id"]), int(row["horizon_minutes"])): row
        for row in label_rows
        if not row["incomplete"]
    }
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in identities:
        groups[tuple(row[field] for field in stratum_fields)].append(row)
    rng = random.Random(SEED)
    output: dict[str, Any] = {"seed": SEED, "simulations": SIMULATIONS, "horizons": {}}
    for horizon in PRIMARY_HORIZONS:
        eligible = [
            row for row in identities if (str(row["event_id"]), horizon) in by_event_horizon
        ]
        real = [
            float(by_event_horizon[(str(row["event_id"]), horizon)]["signed_return_atr"])
            for row in eligible
        ]
        point_directions: dict[str, str] = {}
        point_rng = random.Random(SEED + horizon)
        for group in groups.values():
            directions = [str(row["funding_direction"]) for row in group]
            point_rng.shuffle(directions)
            point_directions.update(
                (str(row["event_id"]), direction)
                for row, direction in zip(group, directions, strict=True)
            )

        def score(row: dict[str, Any], direction: str, selected_horizon: int = horizon) -> float:
            raw = float(
                by_event_horizon[(str(row["event_id"]), selected_horizon)]["raw_return_atr"]
            )
            return raw if direction == "LONG" else -raw

        point_null = [score(row, point_directions[str(row["event_id"])]) for row in eligible]
        deltas: list[float] = []
        for _ in range(SIMULATIONS):
            permuted: dict[str, str] = {}
            for group in groups.values():
                directions = [str(row["funding_direction"]) for row in group]
                rng.shuffle(directions)
                permuted.update(
                    (str(row["event_id"]), direction)
                    for row, direction in zip(group, directions, strict=True)
                )
            null = [score(row, permuted[str(row["event_id"])]) for row in eligible]
            deltas.append(statistics.median(real) - statistics.median(null))
        output["horizons"][f"{horizon}m"] = {
            "real_signed_median": statistics.median(real),
            "deterministic_point_delta": statistics.median(real) - statistics.median(point_null),
            "distribution_p05": _percentile(deltas, 0.05),
            "distribution_p50": _percentile(deltas, 0.50),
            "distribution_p95": _percentile(deltas, 0.95),
        }
    return output


def _h19_summary(
    feature_rows: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    extremes = [row for row in feature_rows if row["funding_direction"] != "NO_BIAS"]
    summary: dict[str, Any] = {"horizons": {}}
    bootstrap: dict[str, Any] = {"seed": SEED, "simulations": SIMULATIONS}
    tail_spread: dict[str, Any] = {"horizons": {}}
    early_late: dict[str, Any] = {}
    for horizon in H19_HORIZONS:
        rows = [
            row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]
        ]
        summary["horizons"][f"{horizon}m"] = {
            "count": len(rows),
            "signed_median": _median(rows, "signed_return_atr"),
            "raw_median": _median(rows, "raw_return_atr"),
            "by_direction": {
                direction: {
                    "count": sum(row["funding_direction"] == direction for row in rows),
                    "signed_median": _median(
                        [row for row in rows if row["funding_direction"] == direction],
                        "signed_return_atr",
                    ),
                }
                for direction in ("LONG", "SHORT")
            },
        }
        bootstrap[f"{horizon}m"] = _cluster_bootstrap_median(
            rows, "signed_return_atr", "week_cluster"
        )
        bottom = [row for row in rows if row["funding_direction"] == "LONG"]
        top = [row for row in rows if row["funding_direction"] == "SHORT"]
        spread = float(_median(bottom, "raw_return_atr") or 0) - float(
            _median(top, "raw_return_atr") or 0
        )
        spread_rows = [
            {
                **row,
                "spread_value": float(row["raw_return_atr"])
                * (1 if row["funding_direction"] == "LONG" else -1),
            }
            for row in rows
        ]
        spread_boot = _cluster_bootstrap_tail_spread(spread_rows)
        percentiles = [float(row["funding_percentile"]) for row in rows]
        raw_returns = [float(row["raw_return_atr"]) for row in rows]
        tail_spread["horizons"][f"{horizon}m"] = {
            "bottom_raw_median": _median(bottom, "raw_return_atr"),
            "top_raw_median": _median(top, "raw_return_atr"),
            "bottom_minus_top": spread,
            "week_cluster_bootstrap": spread_boot,
            "spearman_percentile_raw_return": _spearman(percentiles, raw_returns),
        }
    for split in ("EARLY", "LATE"):
        early_late[split] = {}
        for horizon in PRIMARY_HORIZONS:
            rows = [
                row
                for row in labels
                if row["split"] == split
                and row["horizon_minutes"] == horizon
                and not row["incomplete"]
            ]
            bottom = [row for row in rows if row["funding_direction"] == "LONG"]
            top = [row for row in rows if row["funding_direction"] == "SHORT"]
            early_late[split][f"{horizon}m"] = {
                "signed_median": _median(rows, "signed_return_atr"),
                "bottom_minus_top_raw_spread": float(_median(bottom, "raw_return_atr") or 0)
                - float(_median(top, "raw_return_atr") or 0),
                "long_signed_median": _median(bottom, "signed_return_atr"),
                "short_signed_median": _median(top, "signed_return_atr"),
            }
    summary["eligible_extreme_events"] = len(extremes)
    summary["week_clusters"] = len({str(row["week_cluster"]) for row in extremes})
    summary["avg_events_per_week"] = len(extremes) / max(1, int(summary["week_clusters"]))
    return summary, bootstrap, tail_spread, early_late


def _cluster_bootstrap_tail_spread(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    clusters: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        clusters[str(row["week_cluster"])].append(row)
    ids = sorted(clusters)
    rng = random.Random(SEED)
    values: list[float] = []
    for _ in range(SIMULATIONS):
        sample_ids = [rng.choice(ids) for _ in ids]
        sample = [row for identity in sample_ids for row in clusters[identity]]
        bottom = [
            float(row["raw_return_atr"]) for row in sample if row["funding_direction"] == "LONG"
        ]
        top = [
            float(row["raw_return_atr"]) for row in sample if row["funding_direction"] == "SHORT"
        ]
        if bottom and top:
            values.append(statistics.median(bottom) - statistics.median(top))
    return {
        "cluster_count": len(ids),
        "p05": _percentile(values, 0.05),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
    }


def asof_funding(timestamp_ms: int, features: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    timestamps = [int(row["timestamp_ms"]) for row in features]
    index = bisect.bisect_right(timestamps, timestamp_ms) - 1
    return features[index] if index >= 0 else None


def opportunity_union(
    br_rows: Sequence[dict[str, Any]], tp_rows: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for tag, rows in (("BR", br_rows), ("TP", tp_rows)):
        for row in rows:
            timestamp = int(row["timestamp_ms"])
            if timestamp not in grouped:
                grouped[timestamp] = {
                    **row,
                    "opportunity_id": f"O:{timestamp}",
                    "setup_tags": [tag],
                }
            elif tag not in grouped[timestamp]["setup_tags"]:
                grouped[timestamp]["setup_tags"].append(tag)
    for row in grouped.values():
        row["setup_tag"] = "+".join(sorted(row.pop("setup_tags")))
        row.pop("direction", None)
    return [grouped[key] for key in sorted(grouped)]


def attach_funding_to_opportunities(
    opportunities: Sequence[dict[str, Any]],
    features: Sequence[dict[str, Any]],
    controls_by_timestamp: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in opportunities:
        timestamp = int(row["timestamp_ms"])
        funding = asof_funding(timestamp, features)
        reference = controls_by_timestamp.get(timestamp, row)
        enriched = {
            **row,
            "event_id": row["opportunity_id"],
            "year": int(reference.get("year", datetime.fromtimestamp(timestamp / 1000, UTC).year)),
            "atr_decile": int(reference.get("atr_decile", row.get("atr_decile", 0))),
            "bar_index": int(reference.get("bar_index", row.get("bar_index", 0))),
            "split": "LATE" if timestamp >= LATE_START_MS else "EARLY",
            "day_cluster": datetime.fromtimestamp(timestamp / 1000, UTC).strftime("%Y-%m-%d"),
        }
        if funding is None or funding["feature_status"] == "WARMUP_INCOMPLETE":
            enriched.update(
                funding_status="UNAVAILABLE", funding_direction="NO_BIAS", funding_age_ms=None
            )
        else:
            age = timestamp - int(funding["timestamp_ms"])
            status = "STALE_FUNDING" if age > STALE_MS else str(funding["feature_status"])
            enriched.update(
                funding_status=status,
                funding_timestamp_ms=funding["timestamp_ms"],
                funding_age_ms=age,
                funding_percentile=funding["funding_percentile"],
                funding_direction=(
                    funding["funding_direction"] if status != "STALE_FUNDING" else "NO_BIAS"
                ),
            )
        output.append(enriched)
    return output


def _directional_opportunity_label(
    identity: dict[str, Any], series: IndexedOneMinuteSeries, horizon: int
) -> dict[str, Any]:
    bars, incomplete = series.bounded_window(int(identity["decision_close_ms"]), horizon)
    atr = float(identity["atr"])
    if incomplete or not bars or atr <= 0:
        return {"horizon_minutes": horizon, "incomplete": True}
    raw = (bars[-1].close - float(identity["close"])) / atr
    signed = raw if identity["funding_direction"] == "LONG" else -raw
    return {
        "horizon_minutes": horizon,
        "incomplete": False,
        "raw_return_atr": raw,
        "signed_return_atr": signed,
    }


def _opportunity_labels(
    rows: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row["opportunity_id"],
            "timestamp_ms": row["timestamp_ms"],
            "year": row["year"],
            "atr_decile": row["atr_decile"],
            "setup_tag": row["setup_tag"],
            "split": row["split"],
            "day_cluster": row["day_cluster"],
            "funding_direction": row["funding_direction"],
            **_directional_opportunity_label(row, series, horizon),
        }
        for row in rows
        if row["funding_direction"] != "NO_BIAS"
        for horizon in PRIMARY_HORIZONS
    ]


def _direction_summary(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {"horizons": {}}
    for horizon in PRIMARY_HORIZONS:
        rows = [
            row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]
        ]
        output["horizons"][f"{horizon}m"] = {
            "count": len(rows),
            "signed_median": _median(rows, "signed_return_atr"),
            "by_direction": {
                direction: {
                    "count": sum(row["funding_direction"] == direction for row in rows),
                    "signed_median": _median(
                        [row for row in rows if row["funding_direction"] == direction],
                        "signed_return_atr",
                    ),
                }
                for direction in ("LONG", "SHORT")
            },
            "by_setup": {
                tag: {
                    "count": sum(row["setup_tag"] == tag for row in rows),
                    "signed_median": _median(
                        [row for row in rows if row["setup_tag"] == tag],
                        "signed_return_atr",
                    ),
                }
                for tag in ("BR", "TP", "BR+TP")
            },
        }
    output["day_clusters"] = len(
        {str(row["day_cluster"]) for row in labels if not row["incomplete"]}
    )
    return output


def _split_direction_summary(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        split: _direction_summary([row for row in labels if row["split"] == split])
        for split in ("EARLY", "LATE")
    }


def _matched_tail_pairs(
    features: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    bottoms = [row for row in features if row["funding_direction"] == "LONG"]
    tops = [row for row in features if row["funding_direction"] == "SHORT"]
    label_map = {
        (str(row["event_id"]), int(row["horizon_minutes"])): row
        for row in labels
        if not row["incomplete"]
    }
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for bottom in bottoms:
        eligible = [
            top
            for top in tops
            if top["year"] == bottom["year"]
            and top["atr_decile"] == bottom["atr_decile"]
            and abs(int(top["timestamp_ms"]) - int(bottom["timestamp_ms"])) >= DAY_MS
        ]
        if eligible:
            pairs.append(
                (
                    bottom,
                    min(
                        eligible,
                        key=lambda row: (
                            abs(int(row["timestamp_ms"]) - int(bottom["timestamp_ms"])),
                            int(row["timestamp_ms"]),
                        ),
                    ),
                )
            )
    output: dict[str, Any] = {"pair_count": len(pairs), "horizons": {}}
    for horizon in PRIMARY_HORIZONS:
        deltas = []
        for bottom, top in pairs:
            left = label_map.get((f"F:{bottom['timestamp_ms']}", horizon))
            right = label_map.get((f"F:{top['timestamp_ms']}", horizon))
            if left and right:
                deltas.append(float(left["raw_return_atr"]) - float(right["raw_return_atr"]))
        output["horizons"][f"{horizon}m"] = {
            "complete_pairs": len(deltas),
            "median_paired_delta": statistics.median(deltas) if deltas else None,
        }
    return output


def h19_verdict(
    summary: dict[str, Any],
    bootstrap: dict[str, Any],
    permutation: dict[str, Any],
    tail: dict[str, Any],
    early_late: dict[str, Any],
) -> str:
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 300
        or min(int(h8["by_direction"][side]["count"]) for side in ("LONG", "SHORT")) < 100
        or int(summary["week_clusters"]) < 80
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    medians = [float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS]
    spreads = [float(tail["horizons"][f"{h}m"]["bottom_minus_top"]) for h in PRIMARY_HORIZONS]
    perm = [
        float(permutation["horizons"][f"{h}m"]["deterministic_point_delta"])
        for h in PRIMARY_HORIZONS
    ]
    if (
        all(value <= 0 for value in medians)
        or all(value <= 0 for value in spreads)
        or all(value <= 0 for value in perm)
    ):
        return "FALSIFIED"
    supported = (
        all(value > 0 for value in medians + spreads + perm)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(
            float(tail["horizons"][f"{h}m"]["week_cluster_bootstrap"]["p05"]) >= -0.05
            for h in PRIMARY_HORIZONS
        )
        and all(
            float(tail["horizons"][f"{h}m"]["spearman_percentile_raw_return"]) < 0
            for h in PRIMARY_HORIZONS
        )
        and all(
            float(early_late[split][f"{h}m"]["signed_median"]) > 0
            for split in ("EARLY", "LATE")
            for h in PRIMARY_HORIZONS
        )
        and all(
            float(summary["horizons"][f"{h}m"]["by_direction"][side]["signed_median"]) >= -0.05
            for h in PRIMARY_HORIZONS
            for side in ("LONG", "SHORT")
        )
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def h20_verdict(
    summary: dict[str, Any],
    bootstrap: dict[str, Any],
    permutation: dict[str, Any],
    early_late: dict[str, Any],
) -> str:
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 100
        or min(int(h8["by_direction"][s]["count"]) for s in ("LONG", "SHORT")) < 30
        or int(summary["day_clusters"]) < 60
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    medians = [float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS]
    perm = [
        float(permutation["horizons"][f"{h}m"]["deterministic_point_delta"])
        for h in PRIMARY_HORIZONS
    ]
    if all(value <= 0 for value in medians) or all(value <= 0 for value in perm):
        return "FALSIFIED"
    supported = (
        all(value > 0 for value in medians + perm)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(
            float(early_late[split]["horizons"][f"{h}m"]["signed_median"]) > 0
            for split in ("EARLY", "LATE")
            for h in PRIMARY_HORIZONS
        )
        and all(
            float(summary["horizons"][f"{h}m"]["by_direction"][side]["signed_median"]) >= -0.05
            for h in PRIMARY_HORIZONS
            for side in ("LONG", "SHORT")
        )
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def _match_movement_controls(
    opportunities: Sequence[dict[str, Any]],
    controls: Sequence[dict[str, Any]],
    features: Sequence[dict[str, Any]],
    excluded_times: set[int],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for control in controls:
        timestamp = int(control["timestamp_ms"])
        if timestamp in excluded_times:
            continue
        funding = asof_funding(timestamp, features)
        if (
            funding is None
            or funding["funding_direction"] == "NO_BIAS"
            or timestamp - int(funding["timestamp_ms"]) > STALE_MS
        ):
            continue
        annotated.append({**control, "funding_direction": funding["funding_direction"]})
    output: list[dict[str, Any]] = []
    for candidate in opportunities:
        eligible = [
            row
            for row in annotated
            if int(row["year"]) == int(candidate["year"])
            and int(row["atr_decile"]) == int(candidate["atr_decile"])
            and row["funding_direction"] == candidate["funding_direction"]
            and abs(int(row["bar_index"]) - int(candidate["bar_index"])) >= 96
        ]
        for rank, control in enumerate(
            sorted(
                eligible,
                key=lambda row: (
                    abs(int(row["bar_index"]) - int(candidate["bar_index"])),
                    int(row["timestamp_ms"]),
                ),
            )[:5],
            1,
        ):
            output.append(
                {**control, "candidate_id": candidate["opportunity_id"], "control_rank": rank}
            )
    return output


def _movement_analysis(
    opportunities: Sequence[dict[str, Any]],
    controls: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metrics = (
        "future_range_atr",
        "max_excursion_atr",
        "absolute_close_return_atr",
        "movement_1_5",
        "movement_2_5",
    )
    pair_values: dict[tuple[str, int], dict[str, Any]] = {}
    candidate_map = {str(row["opportunity_id"]): row for row in opportunities}
    for identity, candidate in candidate_map.items():
        for horizon in PRIMARY_HORIZONS:
            label = movement_label(candidate, series, horizon)
            if not label["incomplete"]:
                pair_values[(identity, horizon)] = {"candidate": label, "controls": []}
    for control in controls:
        for horizon in PRIMARY_HORIZONS:
            label = movement_label(control, series, horizon)
            key = (str(control["candidate_id"]), horizon)
            if key in pair_values and not label["incomplete"]:
                pair_values[key]["controls"].append(label)
    paired: list[dict[str, Any]] = []
    for (identity, horizon), block in pair_values.items():
        if not block["controls"]:
            continue
        candidate = block["candidate"]
        source = candidate_map[identity]
        paired.append(
            {
                "candidate_id": identity,
                "horizon_minutes": horizon,
                "day_cluster": source["day_cluster"],
                "split": source["split"],
                **{f"candidate_{metric}": candidate[metric] for metric in metrics},
                **{
                    f"control_{metric}": (
                        statistics.mean(float(row[metric]) for row in block["controls"])
                        if metric.startswith("movement_")
                        else statistics.median(float(row[metric]) for row in block["controls"])
                    )
                    for metric in metrics
                },
            }
        )
    summary: dict[str, Any] = {"horizons": {}, "early_late": {}}
    for horizon in PRIMARY_HORIZONS:
        rows = [row for row in paired if row["horizon_minutes"] == horizon]
        summary["horizons"][f"{horizon}m"] = {
            "count": len(rows),
            "metrics": {
                metric: {
                    "candidate_median_or_rate": statistics.mean(
                        float(row[f"candidate_{metric}"]) for row in rows
                    )
                    if metric.startswith("movement_") and rows
                    else (_percentile([float(row[f"candidate_{metric}"]) for row in rows], 0.5)),
                    "control_median_or_rate": statistics.mean(
                        float(row[f"control_{metric}"]) for row in rows
                    )
                    if metric.startswith("movement_") and rows
                    else (_percentile([float(row[f"control_{metric}"]) for row in rows], 0.5)),
                    "delta": (
                        (
                            statistics.mean(float(row[f"candidate_{metric}"]) for row in rows)
                            - statistics.mean(float(row[f"control_{metric}"]) for row in rows)
                        )
                        if metric.startswith("movement_") and rows
                        else (
                            (
                                statistics.median(float(row[f"candidate_{metric}"]) for row in rows)
                                - statistics.median(float(row[f"control_{metric}"]) for row in rows)
                            )
                            if rows
                            else None
                        )
                    ),
                }
                for metric in metrics
            },
        }
    for split in ("EARLY", "LATE"):
        summary["early_late"][split] = {
            f"{h}m_future_range_delta": (
                statistics.median(
                    float(row["candidate_future_range_atr"])
                    for row in paired
                    if row["split"] == split and row["horizon_minutes"] == h
                )
                - statistics.median(
                    float(row["control_future_range_atr"])
                    for row in paired
                    if row["split"] == split and row["horizon_minutes"] == h
                )
            )
            if any(row["split"] == split and row["horizon_minutes"] == h for row in paired)
            else None
            for h in PRIMARY_HORIZONS
        }
    summary["day_clusters"] = len(
        {row["day_cluster"] for row in paired if row["horizon_minutes"] == 480}
    )
    bootstrap: dict[str, Any] = {"seed": SEED, "simulations": SIMULATIONS}
    for horizon in PRIMARY_HORIZONS:
        rows = [row for row in paired if row["horizon_minutes"] == horizon]
        clusters: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in rows:
            clusters[str(row["day_cluster"])].append(row)
        ids = sorted(clusters)
        rng = random.Random(SEED + horizon)
        values = []
        for _ in range(SIMULATIONS):
            sample = (
                [row for _id in [rng.choice(ids) for _ in ids] for row in clusters[_id]]
                if ids
                else []
            )
            if sample:
                values.append(
                    statistics.median(float(row["candidate_future_range_atr"]) for row in sample)
                    - statistics.median(float(row["control_future_range_atr"]) for row in sample)
                )
        bootstrap[f"{horizon}m"] = {
            "cluster_count": len(ids),
            "p05": _percentile(values, 0.05),
            "p50": _percentile(values, 0.5),
            "p95": _percentile(values, 0.95),
        }
    return summary, bootstrap


def h21_verdict(summary: dict[str, Any], bootstrap: dict[str, Any]) -> str:
    if int(summary["horizons"]["480m"]["count"]) < 30 or int(summary["day_clusters"]) < 20:
        return "INCONCLUSIVE_LOW_SAMPLE"
    ranges = [
        float(summary["horizons"][f"{h}m"]["metrics"]["future_range_atr"]["delta"])
        for h in PRIMARY_HORIZONS
    ]
    maxima = [
        float(summary["horizons"][f"{h}m"]["metrics"]["max_excursion_atr"]["delta"])
        for h in PRIMARY_HORIZONS
    ]
    if (all(value <= 0 for value in ranges) and all(value <= 0 for value in maxima)) or all(
        float(bootstrap[f"{h}m"]["p95"]) <= 0 for h in PRIMARY_HORIZONS
    ):
        return "FALSIFIED"
    supported = (
        all(value > 0 for value in ranges + maxima)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(
            float(summary["early_late"][split][f"{h}m_future_range_delta"]) > 0
            for split in ("EARLY", "LATE")
            for h in PRIMARY_HORIZONS
        )
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def forward_derivatives_audit(root: str | Path, config: AppConfig) -> dict[str, Any]:
    base = Path(root)
    candidates = sorted(
        path
        for path in base.rglob("*.csv")
        if "derivative" in path.name.lower() and path.name != "funding_events.csv"
    )
    independent_times = {
        "funding_time_ms",
        "open_interest_time_ms",
        "taker_time_ms",
        "basis_time_ms",
        "long_short_time_ms",
        "order_book_time_ms",
    }.issubset(DERIVATIVE_FIELDS)
    status: dict[str, Any] = {
        "read_only_audit": True,
        "collector_callable": callable(collect_derivative_snapshot),
        "collector_signature": str(inspect.signature(collect_derivative_snapshot)),
        "independent_field_timestamps": independent_times,
        "order_book_default_disabled": not config.strategy.enable_order_book_factor,
        "historical_hypothesis_input": False,
        "actual_accumulated_data_present": bool(candidates),
        "csv_files": [],
    }
    for path in candidates:
        snapshots = HistoricalDerivativeStore.from_csv(path).as_snapshots()
        timestamps = [row.observed_at_ms for row in snapshots]
        status["csv_files"].append(
            {
                "path": str(path),
                "sha256": _sha256(path),
                "samples": len(snapshots),
                "start_ms": min(timestamps) if timestamps else None,
                "end_ms": max(timestamps) if timestamps else None,
                "gaps_over_30m": sum(
                    right - left > 30 * 60_000 for left, right in itertools.pairwise(timestamps)
                ),
            }
        )
    return status


def _by_year_direction(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for year in sorted({int(row["year"]) for row in labels}):
        for side in ("LONG", "SHORT"):
            block = [
                row
                for row in labels
                if int(row["year"]) == year and row["funding_direction"] == side
            ]
            output[f"{year}_{side}"] = {
                f"{h}m_count": sum(
                    row["horizon_minutes"] == h and not row["incomplete"] for row in block
                )
                for h in PRIMARY_HORIZONS
            } | {
                f"{h}m_signed_median": _median(
                    [row for row in block if row["horizon_minutes"] == h],
                    "signed_return_atr",
                )
                for h in PRIMARY_HORIZONS
            }
    return output


def run_v037_funding_qualification(
    candles: Sequence[Candle],
    funding_events: Sequence[FundingEvent],
    config: AppConfig,
    funding_audit: dict[str, Any],
    *,
    data_root: str | Path = "data",
    seed: int = SEED,
) -> dict[str, Any]:
    if seed != SEED:
        raise ValueError("v0.3.7 preregistered seed is 37")
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
        raise ValueError("v0.3.7 requires disabled execution")
    if not candles or candles[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("v0.3.7 holdout firewall rejected price data")
    if any(event.timestamp_ms >= DEV_END_MS for event in funding_events):
        raise ValueError("v0.3.7 holdout firewall rejected funding data")
    replay = run_v033_geometry_audit(
        candles,
        frozen,
        (),
        capture_trend_controls=True,
        capture_breakout_qualification=True,
    )
    features = build_funding_features(funding_events)
    _decorate_funding_features(features, candles, frozen)
    valid_features = [row for row in features if row["feature_status"] != "WARMUP_INCOMPLETE"]
    funding_labels = _funding_label_rows(valid_features, StrictAfterPriceSeries(candles))
    h19_summary, h19_bootstrap, h19_tail, h19_early_late = _h19_summary(
        valid_features, funding_labels
    )
    extreme_features = [row for row in valid_features if row["funding_direction"] != "NO_BIAS"]
    h19_permutation = _permutation_analysis(
        extreme_features, funding_labels, stratum_fields=("year", "atr_decile")
    )
    h19_tail["matched_tail_pairs"] = _matched_tail_pairs(extreme_features, funding_labels)
    h19 = h19_verdict(h19_summary, h19_bootstrap, h19_permutation, h19_tail, h19_early_late)
    controls = list(replay["trend_control_rows"])
    br = list(replay["breakout_qualification_rows"])
    tp = list(replay["tp_geometry_rows"])
    union = opportunity_union(br, tp)
    controls_by_timestamp = {int(row["timestamp_ms"]): row for row in controls}
    opportunities = attach_funding_to_opportunities(union, features, controls_by_timestamp)
    biased = [row for row in opportunities if row["funding_direction"] != "NO_BIAS"]
    indexed = IndexedOneMinuteSeries(candles)
    opportunity_labels = _opportunity_labels(biased, indexed)
    h20_summary = _direction_summary(opportunity_labels)
    h20_bootstrap = {
        "seed": SEED,
        "simulations": SIMULATIONS,
        **{
            f"{h}m": _cluster_bootstrap_median(
                [row for row in opportunity_labels if row["horizon_minutes"] == h],
                "signed_return_atr",
                "day_cluster",
            )
            for h in PRIMARY_HORIZONS
        },
    }
    h20_permutation = _permutation_analysis(
        biased,
        opportunity_labels,
        stratum_fields=("year", "atr_decile", "setup_tag"),
    )
    h20_early_late = _split_direction_summary(opportunity_labels)
    h20 = h20_verdict(h20_summary, h20_bootstrap, h20_permutation, h20_early_late)
    movement_controls = _match_movement_controls(
        biased, controls, features, {int(row["timestamp_ms"]) for row in union}
    )
    h21_summary, h21_bootstrap = _movement_analysis(biased, movement_controls, indexed)
    h21 = h21_verdict(h21_summary, h21_bootstrap)
    if h19 == h20 == h21 == "SUPPORTED":
        recommendation = "RECOMMEND_FUNDING_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE"
    elif h19 == "SUPPORTED" and h20.startswith("INCONCLUSIVE") and h21.startswith("INCONCLUSIVE"):
        recommendation = "RECOMMEND_FUNDING_DIRECTION_FOLLOWUP"
    elif h19 == "FALSIFIED":
        recommendation = "RECOMMEND_NEXT_NEW_FEATURE_FAMILY_CROSS_ASSET"
    else:
        recommendation = "INCONCLUSIVE_CONTINUE_FUNDING_DIAGNOSTIC"
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
        "funding_data_audit": funding_audit,
        "funding_feature_events": features,
        "funding_label_rows": funding_labels,
        "h19_funding_directionality": {**h19_summary, "verdict": h19},
        "h19_week_cluster_bootstrap": h19_bootstrap,
        "h19_permutation": h19_permutation,
        "h19_tail_spread": h19_tail,
        "h19_early_late": h19_early_late,
        "opportunity_funding_events": opportunities,
        "h20_opportunity_directionality": {
            **h20_summary,
            "union_raw_count": len(br) + len(tp),
            "union_deduplicated_count": len(union),
            "extreme_biased_count": len(biased),
            "extreme_coverage_pct": 100 * len(biased) / len(union) if union else 0,
            "permutation": h20_permutation,
            "verdict": h20,
        },
        "h20_day_cluster_bootstrap": h20_bootstrap,
        "h20_early_late": h20_early_late,
        "h21_movement_retention": {
            **h21_summary,
            "matched_control_rows": len(movement_controls),
            "verdict": h21,
        },
        "h21_bootstrap": h21_bootstrap,
        "by_year_direction": _by_year_direction(funding_labels),
        "forward_derivatives_collection_status": forward_derivatives_audit(data_root, frozen),
        "hypothesis_verdicts": {"H19": h19, "H20": h20, "H21": h21},
        "recommendation": recommendation,
        "overall_status": "FUNDING_FEATURE_QUALIFICATION_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "replay": replay["performance"],
        },
    }


def write_v037_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    funding_path: str | Path,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable v0.3.7 run already exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol = Path(protocol_path)
    manifest = Path(manifest_path)
    funding = Path(funding_path)
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "price_data_manifest.json")
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    pq.write_table(
        pa.Table.from_pylist(result["funding_feature_events"]),
        target / "funding_feature_events.parquet",
    )
    pq.write_table(
        pa.Table.from_pylist(result["opportunity_funding_events"]),
        target / "opportunity_funding_events.parquet",
    )
    names = (
        "funding_data_audit",
        "h19_funding_directionality",
        "h19_week_cluster_bootstrap",
        "h19_permutation",
        "h19_tail_spread",
        "h19_early_late",
        "h20_opportunity_directionality",
        "h20_day_cluster_bootstrap",
        "h20_early_late",
        "h21_movement_retention",
        "h21_bootstrap",
        "by_year_direction",
        "forward_derivatives_collection_status",
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
        if key
        not in set(names)
        | {"funding_feature_events", "funding_label_rows", "opportunity_funding_events"}
    }
    summary["provenance"] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "price_data_manifest_sha256": _sha256(manifest),
        "funding_csv_sha256": _sha256(funding),
        "protocol_sha256": _sha256(protocol),
        "config_hash": config.config_hash,
        "seed": SEED,
        "bootstrap_simulations": SIMULATIONS,
        "python_version": platform.python_version(),
    }
    (target / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
