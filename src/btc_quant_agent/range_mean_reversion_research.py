from __future__ import annotations

import bisect
import collections
import hashlib
import importlib
import json
import math
import platform
import random
import resource
import shutil
import statistics
import subprocess
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .backtest import resample
from .config import AppConfig
from .domain import Candle
from .features import build_features, minimum_history
from .regime import classify_regime
from .research import DEV_END_MS, DEV_START_MS

FEATURE_IDENTITY = "RANGE_BOLL20_2Z_15M"
SEED = 40
SIMULATIONS = 2_000
HORIZONS = (120, 240, 480)
PRIMARY_HORIZONS = (240, 480)
LATE_START_MS = 1_704_067_200_000
MATCH_K = 5
MIN_SEPARATION_MS = 24 * 60 * 60_000
PREREGISTRATION_COMMIT_SHA = "dc9fb05b42d894b15478d4756559de59cf1ce6e2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def boll20(closes: Sequence[float]) -> tuple[float, float, float] | None:
    """Frozen 20-close arithmetic center and population sigma."""
    if len(closes) < 20:
        return None
    sample = [float(value) for value in closes[-20:]]
    center = statistics.mean(sample)
    sigma = math.sqrt(sum((value - center) ** 2 for value in sample) / 20)
    if sigma <= 0:
        return None
    return center, sigma, (sample[-1] - center) / sigma


def fade_side(z: float) -> str:
    if z <= -2.0:
        return "LONG_FADE"
    if z >= 2.0:
        return "SHORT_FADE"
    return "NO_BIAS"


def _cluster(timestamp_ms: int) -> tuple[int, str, str, str]:
    stamp = datetime.fromtimestamp(timestamp_ms / 1000, UTC)
    return (
        stamp.year,
        "LATE" if timestamp_ms >= LATE_START_MS else "EARLY",
        stamp.strftime("%G-W%V"),
        stamp.strftime("%Y-%m-%d"),
    )


def _hourly_states(hourly: Sequence[Candle], config: AppConfig) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    required = minimum_history(config.strategy)
    for index in range(required - 1, len(hourly)):
        history = hourly[max(0, index - config.data.history_limit_1h + 1) : index + 1]
        feature = build_features(history, config.strategy)
        output.append(
            {
                "feature_1h_close_ms": feature.bar_close_time_ms,
                "market_state": classify_regime(feature, config.strategy).value,
                "atr": feature.atr,
                "atr_percentile": feature.atr_percentile,
                "atr_decile": min(9, int(feature.atr_percentile * 10)),
            }
        )
    return output


def build_features_15m(
    candles_15m: Sequence[Candle], hourly_states: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build the one frozen feature using only fully closed as-of data."""
    state_closes = [int(row["feature_1h_close_ms"]) for row in hourly_states]
    output: list[dict[str, Any]] = []
    closes: collections.deque[float] = collections.deque(maxlen=20)
    previous_open: int | None = None
    for bar in candles_15m:
        if bar.close_time_ms + 1 >= DEV_END_MS:
            break
        contiguous = previous_open is None or bar.open_time_ms - previous_open == 900_000
        if not contiguous:
            closes.clear()
        closes.append(bar.close)
        previous_open = bar.open_time_ms
        calculated = boll20(tuple(closes))
        state_index = bisect.bisect_right(state_closes, bar.close_time_ms) - 1
        state = hourly_states[state_index] if state_index >= 0 else None
        timestamp_ms = bar.close_time_ms + 1
        year, split, week, day = _cluster(timestamp_ms)
        base: dict[str, Any] = {
            "feature_identity": FEATURE_IDENTITY,
            "timestamp_ms": timestamp_ms,
            "decision_close_ms": bar.close_time_ms,
            "decision_open_ms": bar.open_time_ms,
            "decision_close": bar.close,
            "year": year,
            "split": split,
            "week_cluster": week,
            "day_cluster": day,
            "data_contiguous": contiguous,
        }
        if calculated is None or state is None:
            output.append({**base, "feature_status": "UNAVAILABLE", "side": "NO_BIAS"})
            continue
        center, sigma, z = calculated
        side = fade_side(z)
        output.append(
            {
                **base,
                **state,
                "center": center,
                "sigma": sigma,
                "z": z,
                "abs_z": abs(z),
                "side": side,
                "feature_status": "EXTREME" if side != "NO_BIAS" else "NO_BIAS",
            }
        )
    return output


def build_range_features(candles: Sequence[Candle], config: AppConfig) -> list[dict[str, Any]]:
    if not candles or candles[0].open_time_ms != DEV_START_MS:
        raise ValueError("v0.3.10 requires the complete Development series")
    if candles[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("v0.3.10 rejects Final Holdout bars")
    return build_features_15m(resample(candles, "15m"), _hourly_states(resample(candles, "1h"), config))


def build_episodes(
    features: Sequence[dict[str, Any]], *, regime: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Create regime-conditioned episodes; unavailable/no-bias/gaps always break them."""
    onsets: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    active_side: str | None = None
    episode_id: str | None = None
    member_index = -1
    previous_open: int | None = None
    for row in features:
        desired = row.get("market_state") == regime if regime == "RANGE" else row.get("market_state") != "RANGE"
        available = row.get("feature_status") != "UNAVAILABLE"
        contiguous = previous_open is None or int(row["decision_open_ms"]) - previous_open == 900_000
        side = str(row.get("side", "NO_BIAS"))
        qualifies = desired and available and contiguous and side != "NO_BIAS"
        if not qualifies:
            active_side, episode_id, member_index = None, None, -1
        else:
            if side != active_side:
                active_side = side
                episode_id = f"{regime}:{row['timestamp_ms']}:{side}"
                member_index = 0
                onsets.append(
                    {**row, "event_id": episode_id, "episode_id": episode_id, "episode_index": 0}
                )
            else:
                member_index += 1
            members.append(
                {
                    **row,
                    "event_id": f"{episode_id}:M{member_index}",
                    "episode_id": episode_id,
                    "episode_index": member_index,
                }
            )
        previous_open = int(row["decision_open_ms"])
    lengths = collections.Counter(str(row["episode_id"]) for row in members)
    for row in onsets:
        row["episode_length_bars"] = lengths[str(row["episode_id"])]
    return onsets, members


class DevelopmentMinuteSeries:
    def __init__(self, candles: Sequence[Candle]) -> None:
        if not candles or candles[0].open_time_ms != DEV_START_MS:
            raise ValueError("complete Development 1m series required")
        if candles[-1].close_time_ms >= DEV_END_MS:
            raise ValueError("Final Holdout bar rejected")
        self.bars = candles
        self.opens = [bar.open_time_ms for bar in candles]

    def window(self, decision_close_ms: int, horizon_minutes: int) -> tuple[Sequence[Candle], bool]:
        end_exclusive = decision_close_ms + 1 + horizon_minutes * 60_000
        if end_exclusive > DEV_END_MS:
            return (), True
        start = bisect.bisect_right(self.opens, decision_close_ms)
        end = bisect.bisect_left(self.opens, end_exclusive)
        bars = self.bars[start:end]
        incomplete = (
            len(bars) != horizon_minutes
            or not bars
            or bars[0].open_time_ms <= decision_close_ms
            or bars[-1].close_time_ms >= DEV_END_MS
            or any(
                bars[index].open_time_ms - bars[index - 1].open_time_ms != 60_000
                for index in range(1, len(bars))
            )
        )
        return bars, incomplete


def label_event(event: dict[str, Any], series: DevelopmentMinuteSeries, horizon: int) -> dict[str, Any]:
    bars, incomplete = series.window(int(event["decision_close_ms"]), horizon)
    base = {
        "event_id": event["event_id"],
        "timestamp_ms": event["timestamp_ms"],
        "decision_close_ms": event["decision_close_ms"],
        "year": event["year"],
        "split": event["split"],
        "week_cluster": event["week_cluster"],
        "day_cluster": event["day_cluster"],
        "side": event["side"],
        "market_state": event["market_state"],
        "horizon_minutes": horizon,
        "incomplete": incomplete,
    }
    atr = float(event["atr"])
    if incomplete or not bars or atr <= 0:
        return base
    entry = bars[0].open
    center = float(event["center"])
    is_long = event["side"] == "LONG_FADE"
    adverse = entry - atr if is_long else entry + atr
    signed = (bars[-1].close - entry) / atr if is_long else (entry - bars[-1].close) / atr
    high, low = max(bar.high for bar in bars), min(bar.low for bar in bars)
    mfe = (high - entry) / atr if is_long else (entry - low) / atr
    mae = (entry - low) / atr if is_long else (high - entry) / atr
    ordering = "NEITHER"
    time_to_center: int | None = None
    target_crossed_at_entry = entry >= center if is_long else entry <= center
    if target_crossed_at_entry:
        ordering = "CENTER_FIRST"
        time_to_center = 0
    for index, bar in enumerate(bars):
        if ordering == "CENTER_FIRST":
            break
        center_hit = bar.low <= center <= bar.high
        adverse_hit = bar.low <= adverse if is_long else bar.high >= adverse
        if center_hit or adverse_hit:
            if center_hit and adverse_hit:
                ordering = "SAME_1M_BAR_AMBIGUOUS"
            elif center_hit:
                ordering = "CENTER_FIRST"
            else:
                ordering = "ADVERSE_FIRST"
            if center_hit:
                time_to_center = index + 1
            break
    center_hit_any = target_crossed_at_entry or any(bar.low <= center <= bar.high for bar in bars)
    if center_hit_any and time_to_center is None:
        time_to_center = next(index + 1 for index, bar in enumerate(bars) if bar.low <= center <= bar.high)
    prior_sign = 1 if entry > center else -1 if entry < center else 0
    crossings = 0
    for bar in bars:
        current_sign = 1 if bar.close > center else -1 if bar.close < center else 0
        if current_sign == 0:
            continue
        if prior_sign and current_sign != prior_sign:
            crossings += 1
        prior_sign = current_sign
    return {
        **base,
        "entry_reference_ms": bars[0].open_time_ms,
        "entry_reference": entry,
        "frozen_center": center,
        "frozen_sigma": event["sigma"],
        "frozen_1h_atr": atr,
        "adverse_boundary": adverse,
        "future_close_ms": bars[-1].close_time_ms,
        "future_close": bars[-1].close,
        "signed_return_atr": signed,
        "mfe_atr": max(0.0, mfe),
        "mae_atr": max(0.0, mae),
        "center_hit": center_hit_any,
        "time_to_center_minutes": time_to_center,
        "ordering": ordering,
        "center_first": ordering == "CENTER_FIRST",
        "center_crossings": crossings,
        "future_range_atr": (high - low) / atr,
        "both_center_half_atr": low <= center - 0.5 * atr and high >= center + 0.5 * atr,
    }


def build_labels(events: Sequence[dict[str, Any]], series: DevelopmentMinuteSeries) -> list[dict[str, Any]]:
    return [label_event(event, series, horizon) for event in events for horizon in HORIZONS]


def _deciles(rows: Sequence[dict[str, Any]], key: str) -> dict[str, int]:
    ordered = sorted(rows, key=lambda row: (float(row[key]), int(row["timestamp_ms"])))
    count = len(ordered)
    return {str(row["event_id"]): min(9, index * 10 // count) for index, row in enumerate(ordered)}


def assign_matching_deciles(events: Sequence[dict[str, Any]]) -> None:
    abs_z = _deciles(events, "abs_z")
    for row in events:
        row["abs_z_decile"] = abs_z[str(row["event_id"])]


def match_non_range_controls(
    candidates: Sequence[dict[str, Any]], controls: Sequence[dict[str, Any]], *, k: int = MATCH_K
) -> list[dict[str, Any]]:
    if k > MATCH_K:
        raise ValueError("v0.3.10 matching permits K <= 5")
    forbidden = {"signed_return_atr", "center_first", "center_hit", "mfe_atr", "mae_atr"}
    if any(forbidden.intersection(row) for row in (*candidates, *controls)):
        raise ValueError("outcome fields are forbidden in matching inputs")
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in controls:
        key = (row["year"], row["side"], row["atr_decile"], row["abs_z_decile"])
        groups[key].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: int(row["timestamp_ms"]))
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate["year"], candidate["side"], candidate["atr_decile"], candidate["abs_z_decile"])
        pool = groups.get(key, [])
        eligible = [
            row for row in pool
            if abs(int(row["timestamp_ms"]) - int(candidate["timestamp_ms"])) >= MIN_SEPARATION_MS
        ]
        eligible.sort(
            key=lambda row: (
                abs(int(row["timestamp_ms"]) - int(candidate["timestamp_ms"])),
                int(row["timestamp_ms"]),
            )
        )
        for rank, control in enumerate(eligible[:k], 1):
            output.append(
                {
                    "timestamp_ms": candidate["timestamp_ms"],
                    "candidate_id": candidate["event_id"],
                    "control_id": control["event_id"],
                    "rank": rank,
                    "distance_hours": abs(int(control["timestamp_ms"]) - int(candidate["timestamp_ms"])) / 3_600_000,
                    "year": candidate["year"],
                    "side": candidate["side"],
                    "atr_decile": candidate["atr_decile"],
                    "abs_z_decile": candidate["abs_z_decile"],
                }
            )
    return output


def _rates(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if not row["incomplete"]]
    returns = [float(row["signed_return_atr"]) for row in complete]
    hit_times = [float(row["time_to_center_minutes"]) for row in complete if row["time_to_center_minutes"] is not None]
    return {
        "count": len(complete),
        "signed_median_return_atr": statistics.median(returns) if returns else None,
        "center_hit_rate": statistics.mean(float(row["center_hit"]) for row in complete) if complete else None,
        "center_first_rate": statistics.mean(float(row["center_first"]) for row in complete) if complete else None,
        "ambiguous_count": sum(row["ordering"] == "SAME_1M_BAR_AMBIGUOUS" for row in complete),
        "time_to_center_minutes": {
            "count": len(hit_times),
            "p25": _percentile(hit_times, 0.25),
            "median": _percentile(hit_times, 0.5),
            "p75": _percentile(hit_times, 0.75),
            "p90": _percentile(hit_times, 0.9),
        },
        "mfe_median_atr": statistics.median(float(row["mfe_atr"]) for row in complete) if complete else None,
        "mae_median_atr": statistics.median(float(row["mae_atr"]) for row in complete) if complete else None,
    }


def summarize_h29(events: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    lengths = [float(row["episode_length_bars"]) for row in events]
    output: dict[str, Any] = {
        "episode_onsets": len(events),
        "long_fade": sum(row["side"] == "LONG_FADE" for row in events),
        "short_fade": sum(row["side"] == "SHORT_FADE" for row in events),
        "week_clusters": len({row["week_cluster"] for row in events}),
        "day_clusters": len({row["day_cluster"] for row in events}),
        "episode_length_bars": {
            "p25": _percentile(lengths, 0.25), "median": _percentile(lengths, 0.5),
            "p75": _percentile(lengths, 0.75), "max": max(lengths) if lengths else None,
        },
        "horizons": {},
    }
    for horizon in HORIZONS:
        rows = [row for row in labels if row["horizon_minutes"] == horizon]
        horizon_summary = _rates(rows)
        horizon_summary["by_split"] = {
            split: _rates([row for row in rows if row["split"] == split]) for split in ("EARLY", "LATE")
        }
        horizon_summary["by_side"] = {
            side: _rates([row for row in rows if row["side"] == side])
            for side in ("LONG_FADE", "SHORT_FADE")
        }
        horizon_summary["by_year"] = {
            str(year): _rates([row for row in rows if row["year"] == year]) for year in range(2021, 2027)
        }
        output["horizons"][f"{horizon}m"] = horizon_summary
    return output


def cluster_bootstrap(
    rows: Sequence[dict[str, Any]], value_key: str, cluster_key: str, *, seed: int = SEED,
    simulations: int = SIMULATIONS,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        groups[str(row[cluster_key])].append(row)
    names = sorted(groups)
    generator = random.Random(seed)
    values: list[float] = []
    for _ in range(simulations):
        sample = [item for _name in names for item in groups[generator.choice(names)]]
        values.append(statistics.median(float(row[value_key]) for row in sample))
    return {
        "seed": seed, "simulations": simulations, "clusters": len(names),
        "p05": _percentile(values, 0.05), "p50": _percentile(values, 0.5),
        "p95": _percentile(values, 0.95),
    }


def h29_bootstrap(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        f"{horizon}m": cluster_bootstrap(
            [row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]],
            "signed_return_atr", "week_cluster",
        )
        for horizon in PRIMARY_HORIZONS
    }


def matched_analysis(
    matches: Sequence[dict[str, Any]], candidate_labels: Sequence[dict[str, Any]],
    control_labels: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    c_labels = {(str(row["event_id"]), int(row["horizon_minutes"])): row for row in candidate_labels if not row["incomplete"]}
    n_labels = {(str(row["event_id"]), int(row["horizon_minutes"])): row for row in control_labels if not row["incomplete"]}
    pairs: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for match in matches:
        pairs[str(match["candidate_id"])].append(match)
    deltas: list[dict[str, Any]] = []
    for candidate_id, selected in pairs.items():
        for horizon in PRIMARY_HORIZONS:
            candidate = c_labels.get((candidate_id, horizon))
            controls = [n_labels[(str(row["control_id"]), horizon)] for row in selected if (str(row["control_id"]), horizon) in n_labels]
            if candidate is None or not controls:
                continue
            deltas.append(
                {
                    "candidate_id": candidate_id,
                    "timestamp_ms": candidate["timestamp_ms"],
                    "day_cluster": candidate["day_cluster"],
                    "horizon_minutes": horizon,
                    "control_count": len(controls),
                    "signed_return_delta": float(candidate["signed_return_atr"]) - statistics.mean(float(row["signed_return_atr"]) for row in controls),
                    "center_first_delta": float(candidate["center_first"]) - statistics.mean(float(row["center_first"]) for row in controls),
                    "center_hit_delta": float(candidate["center_hit"]) - statistics.mean(float(row["center_hit"]) for row in controls),
                }
            )
    summary: dict[str, Any] = {"horizons": {}}
    for horizon in PRIMARY_HORIZONS:
        rows = [row for row in deltas if row["horizon_minutes"] == horizon]
        summary["horizons"][f"{horizon}m"] = {
            "candidate_count": len(rows),
            "signed_return_median_delta": statistics.median(float(row["signed_return_delta"]) for row in rows) if rows else None,
            "center_first_mean_delta": statistics.mean(float(row["center_first_delta"]) for row in rows) if rows else None,
            "center_hit_mean_delta": statistics.mean(float(row["center_hit_delta"]) for row in rows) if rows else None,
        }
    return summary, deltas


def h30_bootstrap(deltas: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        f"{horizon}m": cluster_bootstrap(
            [row for row in deltas if row["horizon_minutes"] == horizon],
            "signed_return_delta", "day_cluster",
        )
        for horizon in PRIMARY_HORIZONS
    }


def h29_verdict(summary: dict[str, Any], bootstrap: dict[str, Any]) -> str:
    h4, h8 = summary["horizons"]["240m"], summary["horizons"]["480m"]
    gate = (
        h8["count"] >= 300 and summary["long_fade"] >= 100 and summary["short_fade"] >= 100
        and summary["week_clusters"] >= 80
    )
    if not gate:
        return "INCONCLUSIVE_MECHANISM"
    medians = [float(h4["signed_median_return_atr"]), float(h8["signed_median_return_atr"])]
    rates = [float(h4["center_first_rate"]), float(h8["center_first_rate"])]
    if all(value <= 0 for value in medians) or all(value <= 0.5 for value in rates):
        return "FALSIFIED"
    stability = all(
        float(summary["horizons"][key][group][name]["signed_median_return_atr"]) >= -0.05
        for key in ("240m", "480m") for group, names in (("by_split", ("EARLY", "LATE")), ("by_side", ("LONG_FADE", "SHORT_FADE")))
        for name in names
    )
    supported = (
        all(value > 0 for value in medians) and all(value > 0.5 for value in rates)
        and all(float(bootstrap[key]["p05"]) >= -0.05 for key in ("240m", "480m"))
        and stability
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def h30_verdict(summary: dict[str, Any], bootstrap: dict[str, Any]) -> str:
    rows = [summary["horizons"][key] for key in ("240m", "480m")]
    if any(row["candidate_count"] == 0 for row in rows):
        return "INCONCLUSIVE_MECHANISM"
    returns = [float(row["signed_return_median_delta"]) for row in rows]
    center = [float(row["center_first_mean_delta"]) for row in rows]
    if all(value <= 0 for value in returns) or all(value <= 0 for value in center):
        return "FALSIFIED"
    supported = (
        all(value > 0 for value in returns) and all(value > 0 for value in center)
        and all(float(bootstrap[key]["p05"]) >= -0.05 for key in ("240m", "480m"))
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    return {
        "count": len(values), "p25": _percentile(values, 0.25), "median": _percentile(values, 0.5),
        "p75": _percentile(values, 0.75), "p90": _percentile(values, 0.9),
        "max": max(values) if values else None,
    }


def h31_diagnostic(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in labels if row["horizon_minutes"] == 480 and not row["incomplete"]]
    def group(selected: Sequence[dict[str, Any]]) -> dict[str, Any]:
        return {
            "count": len(selected),
            "center_crossings": _distribution([float(row["center_crossings"]) for row in selected]),
            "future_range_atr": _distribution([float(row["future_range_atr"]) for row in selected]),
            "two_sided_oscillation_fraction": statistics.mean(float(row["both_center_half_atr"]) for row in selected) if selected else None,
            "center_first_fraction": statistics.mean(float(row["center_first"]) for row in selected) if selected else None,
            "time_to_center_minutes": _distribution([float(row["time_to_center_minutes"]) for row in selected if row["time_to_center_minutes"] is not None]),
        }
    return {
        "interpretation": "diagnostic motion only; no orders or PnL",
        "overall": group(rows),
        "by_split": {split: group([row for row in rows if row["split"] == split]) for split in ("EARLY", "LATE")},
        "by_side": {side: group([row for row in rows if row["side"] == side]) for side in ("LONG_FADE", "SHORT_FADE")},
    }


def _matching_diagnostics(
    candidates: Sequence[dict[str, Any]], controls: Sequence[dict[str, Any]], matches: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    reuse = collections.Counter(str(row["control_id"]) for row in matches)
    matched_ids = {str(row["candidate_id"]) for row in matches}
    return {
        "candidate_count": len(candidates), "control_pool_count": len(controls),
        "matched_candidate_count": len(matched_ids), "unmatched_candidate_count": len(candidates) - len(matched_ids),
        "match_pair_count": len(matches), "k_max": max((int(row["rank"]) for row in matches), default=0),
        "control_reuse_histogram": dict(sorted(collections.Counter(reuse.values()).items())),
        "unique_controls_used": len(reuse),
        "distance_hours": _distribution([float(row["distance_hours"]) for row in matches]),
        "balance_exact": all(
            row["year"] is not None and row["side"] is not None and row["atr_decile"] is not None and row["abs_z_decile"] is not None
            for row in matches
        ),
    }


def _same_day_sensitivity(deltas: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for horizon in PRIMARY_HORIZONS:
        rows = [row for row in deltas if row["horizon_minutes"] == horizon]
        days: dict[str, list[float]] = collections.defaultdict(list)
        for row in rows:
            days[str(row["day_cluster"])].append(float(row["signed_return_delta"]))
        daily = [statistics.median(values) for values in days.values()]
        output[f"{horizon}m"] = {
            "candidate_level_median_delta": statistics.median(
                float(row["signed_return_delta"]) for row in rows
            ) if rows else None,
            "equal_weight_day_median_delta": statistics.median(daily) if daily else None,
            "day_count": len(days),
            "multi_candidate_day_count": sum(len(values) > 1 for values in days.values()),
            "interpretation": "descriptive same-day clustering sensitivity only",
        }
    return output


def _member_comparison(
    members: Sequence[dict[str, Any]], onsets: Sequence[dict[str, Any]],
    member_labels: Sequence[dict[str, Any]], onset_labels: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "member_count": len(members), "onset_count": len(onsets),
        "member_to_onset_ratio": len(members) / len(onsets) if onsets else None,
        "inference_unit": "episode onset only",
        "horizons": {},
    }
    for horizon in PRIMARY_HORIZONS:
        member_rows = [row for row in member_labels if row["horizon_minutes"] == horizon]
        onset_rows = [row for row in onset_labels if row["horizon_minutes"] == horizon]
        output["horizons"][f"{horizon}m"] = {
            "onset": _rates(onset_rows),
            "all_members_serially_dependent": _rates(member_rows),
        }
    return output


def recommendation(h29: str, h30: str) -> str:
    if h29 == "SUPPORTED" and h30 == "SUPPORTED":
        return "RECOMMEND_BOUNDED_RANGE_PROTOTYPE_RESEARCH"
    if h29 == "SUPPORTED":
        return "MEAN_REVERSION_EXISTS_BUT_RANGE_NOT_INCREMENTAL"
    if h29 == "FALSIFIED" or (h29 == "FALSIFIED" and h30 == "FALSIFIED"):
        return "STOP_RANGE_FAMILY_MOVE_TO_NEW_DATA_FAMILY"
    return "INCONCLUSIVE_RANGE_MECHANISM"


def assert_development_only(result: dict[str, Any]) -> None:
    timestamp_keys = {
        "timestamp_ms", "decision_close_ms", "decision_open_ms", "feature_1h_close_ms",
        "entry_reference_ms", "future_close_ms",
    }
    def walk(value: Any, key: str | None = None) -> None:
        if key in timestamp_keys and value is not None and int(value) >= DEV_END_MS:
            raise ValueError(f"v0.3.10 Holdout firewall rejected {key}={value}")
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
    walk(result)


def run_v0310(candles: Sequence[Candle], config: AppConfig) -> dict[str, Any]:
    started = time.perf_counter()
    if config.runtime.validation_status != "EXPERIMENTAL" or config.execution.mode != "disabled" or config.execution.auto_execute or config.execution.allow_live:
        raise ValueError("v0.3.10 safety state is not frozen")
    features = build_range_features(candles, config)
    range_onsets, range_members = build_episodes(features, regime="RANGE")
    non_range_onsets, non_range_members = build_episodes(features, regime="NON_RANGE")
    all_onsets = [*range_onsets, *non_range_onsets]
    assign_matching_deciles(all_onsets)
    series = DevelopmentMinuteSeries(candles)
    range_labels = build_labels(range_onsets, series)
    range_member_labels = build_labels(range_members, series)
    control_labels = build_labels(non_range_onsets, series)
    matches = match_non_range_controls(range_onsets, non_range_onsets)
    h29 = summarize_h29(range_onsets, range_labels)
    h29_boot = h29_bootstrap(range_labels)
    h30, matched_deltas = matched_analysis(matches, range_labels, control_labels)
    h30_boot = h30_bootstrap(matched_deltas)
    v29, v30 = h29_verdict(h29, h29_boot), h30_verdict(h30, h30_boot)
    range_extremes = [row for row in features if row.get("market_state") == "RANGE" and row.get("side") != "NO_BIAS"]
    raw_extremes = [row for row in features if row.get("side") != "NO_BIAS"]
    result = {
        "scope": {"development_only": True, "holdout_accessed": False, "start_ms": DEV_START_MS, "end_ms_exclusive": DEV_END_MS},
        "safety": {"validation_status": config.runtime.validation_status, "execution_mode": config.execution.mode, "auto_execute": config.execution.auto_execute, "allow_live": config.execution.allow_live, "candidate_freeze": False},
        "feature_identity": FEATURE_IDENTITY,
        "counts": {"raw_extreme_15m_decisions": len(raw_extremes), "range_extreme_15m_decisions": len(range_extremes), "range_episode_onsets": len(range_onsets), "non_range_episode_onsets": len(non_range_onsets)},
        "h29_summary": h29, "h29_bootstrap": h29_boot,
        "h30_matched_analysis": {
            **h30,
            "diagnostics": _matching_diagnostics(range_onsets, non_range_onsets, matches),
            "same_day_clustering_sensitivity": _same_day_sensitivity(matched_deltas),
        },
        "h30_bootstrap": h30_boot,
        "h31_grid_feasibility_diagnostic": h31_diagnostic(range_labels),
        "serial_dependence": {
            "range": _member_comparison(
                range_members, range_onsets, range_member_labels, range_labels
            ),
            "non_range": {
                "member_count": len(non_range_members),
                "onset_count": len(non_range_onsets),
                "member_to_onset_ratio": len(non_range_members) / len(non_range_onsets)
                if non_range_onsets else None,
                "inference_unit": "episode onset only",
            },
        },
        "hypothesis_verdicts": {"H29": v29, "H30": v30, "H31": "DIAGNOSTIC_ONLY"},
        "recommendation": recommendation(v29, v30),
        "performance": {"runtime_seconds": time.perf_counter() - started, "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024},
        "range_extreme_events": range_extremes,
        "range_episode_onsets": range_onsets,
        "range_episode_members": range_members,
        "range_labels": range_labels,
        "non_range_control_matches": matches,
        "non_range_episode_onsets": non_range_onsets,
        "non_range_episode_members": non_range_members,
        "non_range_labels": control_labels,
        "matched_deltas": matched_deltas,
        "all_feature_rows": features,
    }
    assert_development_only(result)
    return result


def _git_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def _preregistration_sha(protocol: Path) -> str:
    if protocol.name != "v0.3.10_range_mean_reversion_protocol.json":
        raise ValueError("unexpected v0.3.10 protocol path")
    # CI uses a depth-one checkout, so git-log cannot reliably discover the
    # earlier preregistration commit. This identity was frozen before formal code.
    return PREREGISTRATION_COMMIT_SHA


def write_v0310_artifacts(
    output: str | Path, result: dict[str, Any], config: AppConfig, protocol_path: str | Path,
    manifest_path: str | Path,
) -> Path:
    target = Path(output)
    if target.exists():
        raise FileExistsError("formal artifact directory is immutable")
    target.mkdir(parents=True)
    protocol, manifest = Path(protocol_path), Path(manifest_path)
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    config_snapshot = json.dumps(asdict(config), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (target / "config_snapshot.json").write_text(config_snapshot, encoding="utf-8")
    (target / "config.sha256").write_text(hashlib.sha256(config_snapshot.encode()).hexdigest() + "\n", encoding="utf-8")
    provenance = {
        "git_sha": _git_sha(), "protocol_sha256": _sha256(protocol),
        "preregistration_commit_sha": _preregistration_sha(protocol),
        "dataset_manifest_file_sha256": _sha256(manifest),
        "dataset_checksum_sha256": json.loads(manifest.read_text(encoding="utf-8"))["checksum_sha256"],
        "config_hash": config.config_hash, "seed": SEED, "bootstrap_simulations": SIMULATIONS,
        "python_version": platform.python_version(), "runtime_seconds": result["performance"]["runtime_seconds"],
        "peak_rss_mib": result["performance"]["peak_rss_mib"], "holdout_accessed": False,
    }
    summary = {
        "scope": result["scope"], "safety": result["safety"], "feature_identity": FEATURE_IDENTITY,
        "counts": result["counts"], "hypothesis_verdicts": result["hypothesis_verdicts"],
        "recommendation": result["recommendation"], "performance": result["performance"], "provenance": provenance,
        "canonical": True,
    }
    json_files = {
        "experiment_summary.json": summary,
        "h29_summary.json": result["h29_summary"], "h29_bootstrap.json": result["h29_bootstrap"],
        "h30_matched_analysis.json": result["h30_matched_analysis"], "h30_bootstrap.json": result["h30_bootstrap"],
        "h31_grid_feasibility_diagnostic.json": result["h31_grid_feasibility_diagnostic"],
        "by_year_side.json": {key: value for key, value in result["h29_summary"]["horizons"].items()},
        "serial_dependence.json": result["serial_dependence"], "provenance.json": provenance,
    }
    for name, payload in json_files.items():
        (target / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pq = importlib.import_module("pyarrow.parquet")
    pa = importlib.import_module("pyarrow")
    parquet = {
        "range_extreme_events.parquet": result["range_extreme_events"],
        "range_episode_onsets.parquet": result["range_episode_onsets"],
        "range_episode_members.parquet": result["range_episode_members"],
        "range_labels.parquet": result["range_labels"],
        "non_range_control_matches.parquet": result["non_range_control_matches"],
    }
    for name, rows in parquet.items():
        pq.write_table(pa.Table.from_pylist(rows), target / name, compression="zstd")
    return target
