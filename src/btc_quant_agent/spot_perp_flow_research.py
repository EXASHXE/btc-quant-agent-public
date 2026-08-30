from __future__ import annotations

import bisect
import collections
import hashlib
import importlib
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

from .backtest import resample
from .config import AppConfig
from .domain import Candle
from .engine import EngineMode, HistoricalFeatureCache, QuantEngine
from .funding_crowding_research import (
    _cluster_bootstrap_median,
    _percentile,
    _permutation_analysis,
    opportunity_union,
)
from .geometry_research import run_v033_geometry_audit
from .research import DEV_END_MS, DEV_START_MS

FEATURE_ID = "SPOT_PERP_TAKER_FLOW_SPREAD_1H"
SEED = 42
SIMULATIONS = 2000
HORIZONS = (120, 240, 480, 1440)
PRIMARY_HORIZONS = (240, 480)
DECISION_MS = 15 * 60_000
WINDOW_MS = 60 * 60_000
DAY_MS = 24 * 60 * 60_000
LATE_START_MS = 1_704_067_200_000


def flow_direction(spread: float) -> str:
    return "LONG" if spread > 0 else "SHORT" if spread < 0 else "NO_BIAS"


def taker_imbalance(volume: float, taker_buy_base_volume: float) -> float:
    if volume <= 0:
        raise ValueError("flow imbalance requires positive volume")
    if taker_buy_base_volume < 0 or taker_buy_base_volume > volume + 1e-9:
        raise ValueError("taker-buy base volume is outside total-volume bounds")
    return 2 * taker_buy_base_volume / volume - 1


def btc_momentum_direction(value: float) -> str:
    return "LONG" if value > 0 else "SHORT" if value < 0 else "NO_BIAS"


def build_hourly_market_context(
    candles: Sequence[Candle], config: AppConfig
) -> list[dict[str, Any]]:
    hourly = resample(candles, "1h")
    engine = QuantEngine(config, HistoricalFeatureCache(), mode=EngineMode.LEGACY_RESEARCH_V022)
    output: list[dict[str, Any]] = []
    for index, bar in enumerate(hourly):
        if index == 0:
            continue
        history = list(hourly[max(0, index - config.data.history_limit_1h + 1) : index + 1])
        try:
            snapshot = engine.diagnostic_features("1h", history)
        except (IndexError, ValueError):
            continue
        trailing_return = bar.close / hourly[index - 1].close - 1
        output.append(
            {
                "available_at_ms": bar.close_time_ms + 1,
                "atr": snapshot.atr,
                "atr_percentile": snapshot.atr_percentile,
                "atr_decile": min(9, int(snapshot.atr_percentile * 10)),
                "btc_trailing_1h_return": trailing_return,
                "btc_mom_direction": btc_momentum_direction(trailing_return),
                "btc_mom_bucket": (
                    "POSITIVE"
                    if trailing_return > 0
                    else "NEGATIVE"
                    if trailing_return < 0
                    else "ZERO"
                ),
                "btc_feature_close_ms": snapshot.bar_close_time_ms,
            }
        )
    return output


def _flow_row(row: Any) -> tuple[int, float, float]:
    if isinstance(row, Candle):
        return row.open_time_ms, row.volume, row.taker_buy_base_volume
    return (
        int(row["open_time_ms"]),
        float(row["volume"]),
        float(row["taker_buy_base_volume"]),
    )


def build_flow_decisions(
    spot_rows: Sequence[dict[str, Any]],
    perp_rows: Sequence[Candle],
    hourly_context: Sequence[dict[str, Any]],
    *,
    start_ms: int = DEV_START_MS,
    end_ms: int = DEV_END_MS,
) -> list[dict[str, Any]]:
    """Build the sole frozen arm using the exact 60 complete minutes before T."""
    spot_by_time = {int(row["open_time_ms"]): row for row in spot_rows}
    perp_by_time = {row.open_time_ms: row for row in perp_rows}
    context_times = [int(row["available_at_ms"]) for row in hourly_context]
    first_decision = start_ms + DECISION_MS
    output: list[dict[str, Any]] = []
    for timestamp in range(first_decision, end_ms, DECISION_MS):
        context_index = bisect.bisect_right(context_times, timestamp) - 1
        context = hourly_context[context_index] if context_index >= 0 else None
        opens = range(timestamp - WINDOW_MS, timestamp, 60_000)
        aligned: list[tuple[dict[str, Any], Candle]] = []
        for open_time in opens:
            spot = spot_by_time.get(open_time)
            perp = perp_by_time.get(open_time)
            if spot is None or perp is None:
                aligned = []
                break
            aligned.append((spot, perp))
        base: dict[str, Any] = {
            "feature_id": FEATURE_ID,
            "timestamp_ms": timestamp,
            "decision_close_ms": timestamp - 1,
            "year": datetime.fromtimestamp(timestamp / 1_000, UTC).year,
            "split": "LATE" if timestamp >= LATE_START_MS else "EARLY",
            "day_cluster": datetime.fromtimestamp(timestamp / 1_000, UTC).strftime("%Y-%m-%d"),
            "week_cluster": datetime.fromtimestamp(timestamp / 1_000, UTC).strftime("%G-W%V"),
        }
        if not aligned or context is None:
            output.append(
                {
                    **base,
                    "feature_status": "DATA_UNAVAILABLE",
                    "direction": "NO_BIAS",
                    "funding_direction": "NO_BIAS",
                }
            )
            continue
        spot_volume = sum(float(spot["volume"]) for spot, _ in aligned)
        spot_buy = sum(float(spot["taker_buy_base_volume"]) for spot, _ in aligned)
        perp_volume = sum(perp.volume for _, perp in aligned)
        perp_buy = sum(perp.taker_buy_base_volume for _, perp in aligned)
        if spot_volume <= 0 or perp_volume <= 0:
            output.append(
                {
                    **base,
                    **context,
                    "feature_status": "DATA_UNAVAILABLE",
                    "direction": "NO_BIAS",
                    "funding_direction": "NO_BIAS",
                }
            )
            continue
        spot_imbalance = taker_imbalance(spot_volume, spot_buy)
        perp_imbalance = taker_imbalance(perp_volume, perp_buy)
        spread = spot_imbalance - perp_imbalance
        direction = flow_direction(spread)
        output.append(
            {
                **base,
                **context,
                "feature_status": "AVAILABLE" if direction != "NO_BIAS" else "NO_BIAS",
                "direction": direction,
                "funding_direction": direction,
                "spot_volume_1h": spot_volume,
                "spot_taker_buy_1h": spot_buy,
                "spot_imbalance": spot_imbalance,
                "spot_direction": flow_direction(spot_imbalance),
                "perp_volume_1h": perp_volume,
                "perp_taker_buy_1h": perp_buy,
                "perp_imbalance": perp_imbalance,
                "perp_direction": flow_direction(perp_imbalance),
                "flow_spread": spread,
            }
        )
    return output


def build_flow_episodes(
    decisions: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    onsets: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    previous_time: int | None = None
    active_direction: str | None = None
    episode_id: str | None = None
    episode_index = -1
    for row in decisions:
        timestamp = int(row["timestamp_ms"])
        direction = str(row["direction"])
        available = row["feature_status"] == "AVAILABLE" and direction != "NO_BIAS"
        consecutive = previous_time is not None and timestamp - previous_time == DECISION_MS
        if not available:
            active_direction, episode_id, episode_index = None, None, -1
            previous_time = timestamp
            continue
        if not consecutive or direction != active_direction:
            active_direction = direction
            episode_id = f"FLOW:{timestamp}:{direction}"
            episode_index = 0
            onsets.append({**row, "event_id": episode_id, "episode_id": episode_id, "episode_index": 0})
        else:
            episode_index += 1
        members.append({**row, "episode_id": episode_id, "episode_index": episode_index})
        previous_time = timestamp
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in members:
        grouped[str(row["episode_id"])].append(row)
    for row in onsets:
        length = len(grouped[str(row["episode_id"])])
        row["episode_length_decisions"] = length
        row["episode_duration_minutes"] = length * 15
    return onsets, members


class StrictNextOpenSeries:
    def __init__(self, candles: Sequence[Candle], *, end_ms: int = DEV_END_MS) -> None:
        self.candles = tuple(candles)
        self.opens = tuple(row.open_time_ms for row in candles)
        self.end_ms = end_ms

    def label(
        self, decision_close_ms: int, horizon_minutes: int, atr: float, direction: str
    ) -> dict[str, Any]:
        start = bisect.bisect_right(self.opens, decision_close_ms)
        expected_end = self.opens[start] + horizon_minutes * 60_000 if start < len(self.opens) else 0
        end = bisect.bisect_left(self.opens, expected_end)
        incomplete = (
            start >= len(self.opens)
            or end - start != horizon_minutes
            or expected_end > self.end_ms
            or self.candles[end - 1].close_time_ms >= self.end_ms
            or (
                end > start
                and self.opens[end - 1] - self.opens[start]
                != (horizon_minutes - 1) * 60_000
            )
        )
        if incomplete or atr <= 0 or direction == "NO_BIAS":
            return {"horizon_minutes": horizon_minutes, "incomplete": True}
        bars = self.candles[start:end]
        reference = bars[0].open
        raw = (bars[-1].close - reference) / atr
        high, low = max(row.high for row in bars), min(row.low for row in bars)
        if direction == "LONG":
            signed = raw
            mfe = max(0.0, high - reference) / atr
            mae = max(0.0, reference - low) / atr
        else:
            signed = -raw
            mfe = max(0.0, reference - low) / atr
            mae = max(0.0, high - reference) / atr
        return {
            "horizon_minutes": horizon_minutes,
            "incomplete": False,
            "reference_open_time_ms": bars[0].open_time_ms,
            "reference_price": reference,
            "raw_return_atr": raw,
            "signed_return_atr": signed,
            "mfe_atr": mfe,
            "mae_atr": mae,
            "reach_1_0": mfe >= 1.0,
            "reach_1_5": mfe >= 1.5,
            "reach_2_5": mfe >= 2.5,
        }


def build_flow_labels(
    episodes: Sequence[dict[str, Any]], series: StrictNextOpenSeries
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row["event_id"],
            "timestamp_ms": row["timestamp_ms"],
            "year": row["year"],
            "split": row["split"],
            "week_cluster": row["week_cluster"],
            "day_cluster": row["day_cluster"],
            "direction": row["direction"],
            "funding_direction": row["direction"],
            **series.label(
                int(row["decision_close_ms"]), horizon, float(row["atr"]), str(row["direction"])
            ),
        }
        for row in episodes
        for horizon in HORIZONS
    ]


def _median(rows: Sequence[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if not row.get("incomplete")]
    return statistics.median(values) if values else None


def summarize_h32(
    episodes: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "episode_count": len(episodes),
        "long_count": sum(row["direction"] == "LONG" for row in episodes),
        "short_count": sum(row["direction"] == "SHORT" for row in episodes),
        "week_clusters": len({row["week_cluster"] for row in episodes}),
        "horizons": {},
    }
    for horizon in HORIZONS:
        rows = [row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]]
        output["horizons"][f"{horizon}m"] = {
            "count": len(rows),
            "signed_median": _median(rows, "signed_return_atr"),
            "mfe_median": _median(rows, "mfe_atr"),
            "mae_median": _median(rows, "mae_atr"),
            "reach_1_0": statistics.mean(float(row["reach_1_0"]) for row in rows) if rows else None,
            "reach_1_5": statistics.mean(float(row["reach_1_5"]) for row in rows) if rows else None,
            "reach_2_5": statistics.mean(float(row["reach_2_5"]) for row in rows) if rows else None,
            "by_split": {
                split: _median([row for row in rows if row["split"] == split], "signed_return_atr")
                for split in ("EARLY", "LATE")
            },
            "by_direction": {
                side: {
                    "count": sum(row["direction"] == side for row in rows),
                    "signed_median": _median(
                        [row for row in rows if row["direction"] == side], "signed_return_atr"
                    ),
                }
                for side in ("LONG", "SHORT")
            },
        }
    output["leave_one_year_out"] = {
        str(year): {
            f"{horizon}m": _median(
                [
                    row
                    for row in labels
                    if row["year"] != year and row["horizon_minutes"] == horizon
                ],
                "signed_return_atr",
            )
            for horizon in PRIMARY_HORIZONS
        }
        for year in sorted({int(row["year"]) for row in episodes})
    }
    return output


def h32_verdict(
    summary: dict[str, Any], bootstrap: dict[str, Any], permutation: dict[str, Any]
) -> str:
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 1_000
        or min(int(h8["by_direction"][side]["count"]) for side in ("LONG", "SHORT")) < 300
        or int(summary["week_clusters"]) < 100
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    medians = [float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS]
    deltas = [
        float(permutation["horizons"][f"{h}m"]["deterministic_point_delta"])
        for h in PRIMARY_HORIZONS
    ]
    if all(value <= 0 for value in medians) or all(value <= 0 for value in deltas):
        return "FALSIFIED"
    stable_loo = all(
        not all(float(block[f"{h}m"]) < -0.05 for h in PRIMARY_HORIZONS)
        for block in summary["leave_one_year_out"].values()
    )
    supported = (
        all(value > 0 for value in medians + deltas)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(
            float(summary["horizons"][f"{h}m"]["by_split"][split]) >= -0.05
            for h in PRIMARY_HORIZONS
            for split in ("EARLY", "LATE")
        )
        and all(
            float(summary["horizons"][f"{h}m"]["by_direction"][side]["signed_median"])
            >= -0.05
            for h in PRIMARY_HORIZONS
            for side in ("LONG", "SHORT")
        )
        and stable_loo
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def incremental_vs_momentum(
    episodes: Sequence[dict[str, Any]],
    labels: Sequence[dict[str, Any]],
    *,
    simulations: int = SIMULATIONS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    label_map = {
        (str(row["event_id"]), int(row["horizon_minutes"])): row
        for row in labels
        if not row["incomplete"]
    }
    eligible = [row for row in episodes if row["btc_mom_direction"] != "NO_BIAS"]
    output: dict[str, Any] = {
        "event_count": len(eligible),
        "agreement_rate": statistics.mean(
            row["direction"] == row["btc_mom_direction"] for row in eligible
        )
        if eligible
        else None,
        "opposed_event_count": sum(
            row["direction"] != row["btc_mom_direction"] for row in eligible
        ),
        "horizons": {},
    }
    bootstrap: dict[str, Any] = {"seed": SEED, "simulations": simulations}
    permutation: dict[str, Any] = {"seed": SEED, "simulations": simulations, "horizons": {}}
    strata: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in eligible:
        strata[(row["year"], row["atr_decile"], row["btc_mom_bucket"])].append(row)
    for horizon in PRIMARY_HORIZONS:
        pairs: list[dict[str, Any]] = []
        for event in eligible:
            label = label_map.get((str(event["event_id"]), horizon))
            if label is None:
                continue
            raw = float(label["raw_return_atr"])
            flow = raw if event["direction"] == "LONG" else -raw
            btc = raw if event["btc_mom_direction"] == "LONG" else -raw
            pairs.append(
                {
                    "delta": flow - btc,
                    "flow": flow,
                    "btc": btc,
                    "aligned": event["direction"] == event["btc_mom_direction"],
                    "week_cluster": event["week_cluster"],
                    "incomplete": False,
                }
            )
        block = {
            "count": len(pairs),
            "flow_median": _median(pairs, "flow"),
            "btc_momentum_median": _median(pairs, "btc"),
            "paired_median_delta": _median(pairs, "delta"),
            "aligned_flow_median": _median(
                [row for row in pairs if row["aligned"]], "flow"
            ),
            "opposed_flow_median": _median(
                [row for row in pairs if not row["aligned"]], "flow"
            ),
        }
        output["horizons"][f"{horizon}m"] = block
        bootstrap[f"{horizon}m"] = _cluster_bootstrap_median(
            pairs,
            "delta",
            "week_cluster",
            seed=SEED,
            simulations=simulations,
        )
        paired_median = block["paired_median_delta"]
        if paired_median is None:
            raise ValueError("H33 requires complete paired primary-horizon labels")
        real_delta = float(paired_median)
        rng = random.Random(SEED + horizon)

        def permuted_delta(
            permuted: dict[str, str], selected_horizon: int = horizon
        ) -> float:
            values: list[float] = []
            for event in eligible:
                label = label_map.get((str(event["event_id"]), selected_horizon))
                if label is None:
                    continue
                raw = float(label["raw_return_atr"])
                flow = raw if permuted[str(event["event_id"])] == "LONG" else -raw
                btc = raw if event["btc_mom_direction"] == "LONG" else -raw
                values.append(flow - btc)
            return statistics.median(values)

        null_values: list[float] = []
        point_delta: float | None = None
        for simulation in range(simulations + 1):
            assigned: dict[str, str] = {}
            for group in strata.values():
                directions = [str(row["direction"]) for row in group]
                rng.shuffle(directions)
                assigned.update(
                    (str(row["event_id"]), direction)
                    for row, direction in zip(group, directions, strict=True)
                )
            null = permuted_delta(assigned)
            if simulation == 0:
                point_delta = real_delta - null
            else:
                null_values.append(real_delta - null)
        permutation["horizons"][f"{horizon}m"] = {
            "real_paired_median_delta": real_delta,
            "deterministic_point_delta": point_delta,
            "distribution_p05": _percentile(null_values, 0.05),
            "distribution_p50": _percentile(null_values, 0.5),
            "distribution_p95": _percentile(null_values, 0.95),
        }
    deltas = [float(output["horizons"][f"{h}m"]["paired_median_delta"]) for h in PRIMARY_HORIZONS]
    output["stratified_permutation_delta"] = {
        f"{h}m": permutation["horizons"][f"{h}m"]["deterministic_point_delta"]
        for h in PRIMARY_HORIZONS
    }
    perm_deltas = [float(output["stratified_permutation_delta"][f"{h}m"]) for h in PRIMARY_HORIZONS]
    output["verdict"] = (
        "FALSIFIED"
        if all(value <= 0 for value in deltas)
        else "SUPPORTED"
        if all(value > 0 for value in deltas)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(value > 0 for value in perm_deltas)
        else "INCONCLUSIVE_MECHANISM"
    )
    output["permutation"] = permutation
    return output, bootstrap


def diagnostic_single_market(
    episodes: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    label_map = {
        (str(row["event_id"]), int(row["horizon_minutes"])): row
        for row in labels
        if not row["incomplete"]
    }
    return {
        name: {
            f"{horizon}m": _median(
                [
                    {
                        "value": (
                            float(label_map[(str(row["event_id"]), horizon)]["raw_return_atr"])
                            if row[field] == "LONG"
                            else -float(
                                label_map[(str(row["event_id"]), horizon)]["raw_return_atr"]
                            )
                        ),
                        "incomplete": False,
                    }
                    for row in episodes
                    if row[field] != "NO_BIAS"
                    and (str(row["event_id"]), horizon) in label_map
                ],
                "value",
            )
            for horizon in PRIMARY_HORIZONS
        }
        for name, field in (("spot_only", "spot_direction"), ("perp_only", "perp_direction"))
    }


def attach_flow_to_opportunities(
    opportunities: Sequence[dict[str, Any]], decisions: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    times = [int(row["timestamp_ms"]) for row in decisions]
    output: list[dict[str, Any]] = []
    for row in opportunities:
        timestamp = int(row["timestamp_ms"])
        index = bisect.bisect_right(times, timestamp) - 1
        flow = decisions[index] if index >= 0 else None
        available = flow is not None and flow["feature_status"] == "AVAILABLE"
        direction = str(flow["direction"]) if flow is not None and available else "NO_BIAS"
        output.append(
            {
                **row,
                "event_id": row["opportunity_id"],
                "direction": direction,
                "funding_direction": direction,
                "flow_status": "AVAILABLE" if available else "UNAVAILABLE_OR_NO_BIAS",
                "flow_timestamp_ms": flow["timestamp_ms"] if flow else None,
                "flow_age_ms": timestamp - int(flow["timestamp_ms"]) if flow else None,
                "year": int(flow["year"]) if flow else datetime.fromtimestamp(timestamp / 1_000, UTC).year,
                "atr": flow.get("atr") if flow else None,
                "atr_decile": flow.get("atr_decile") if flow else None,
                "btc_mom_bucket": flow.get("btc_mom_bucket") if flow else "UNAVAILABLE",
                "split": "LATE" if timestamp >= LATE_START_MS else "EARLY",
                "day_cluster": datetime.fromtimestamp(timestamp / 1_000, UTC).strftime("%Y-%m-%d"),
            }
        )
    return output


def summarize_h34(
    candidates: Sequence[dict[str, Any]],
    matches: Sequence[dict[str, Any]],
    series: StrictNextOpenSeries,
    *,
    simulations: int = SIMULATIONS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_labels: dict[tuple[str, int], dict[str, Any]] = {}
    for row in candidates:
        for horizon in PRIMARY_HORIZONS:
            label = series.label(
                int(row["decision_close_ms"]), horizon, float(row["atr"]), str(row["direction"])
            )
            candidate_labels[(str(row["opportunity_id"]), horizon)] = {
                **label,
                "direction": row["direction"],
                "split": row["split"],
                "day_cluster": row["day_cluster"],
            }
    control_by_candidate: dict[tuple[str, int], list[float]] = collections.defaultdict(list)
    for row in matches:
        for horizon in PRIMARY_HORIZONS:
            label = series.label(
                int(row["decision_close_ms"]), horizon, float(row["atr"]), str(row["direction"])
            )
            if not label["incomplete"]:
                control_by_candidate[(str(row["candidate_id"]), horizon)].append(
                    float(label["signed_return_atr"])
                )
    summary: dict[str, Any] = {
        "candidate_count": len(candidates),
        "day_clusters": len({row["day_cluster"] for row in candidates}),
        "horizons": {},
    }
    bootstrap: dict[str, Any] = {"seed": SEED, "simulations": simulations}
    candidate_by_id = {str(row["opportunity_id"]): row for row in candidates}
    for horizon in PRIMARY_HORIZONS:
        labels = [
            {"event_id": identity, **label}
            for (identity, selected), label in candidate_labels.items()
            if selected == horizon and not label["incomplete"]
        ]
        delta_rows: list[dict[str, Any]] = []
        for row in labels:
            identity = str(row["event_id"])
            controls = control_by_candidate.get((identity, horizon), [])
            if controls:
                delta_rows.append(
                    {
                        "delta": float(row["signed_return_atr"]) - statistics.median(controls),
                        "day_cluster": candidate_by_id[identity]["day_cluster"],
                        "incomplete": False,
                    }
                )
        pooled_bootstrap = _cluster_bootstrap_median(
            labels,
            "signed_return_atr",
            "day_cluster",
            seed=SEED,
            simulations=simulations,
        )
        matched_bootstrap = (
            _cluster_bootstrap_median(
                delta_rows,
                "delta",
                "day_cluster",
                seed=SEED,
                simulations=simulations,
            )
            if delta_rows
            else None
        )
        summary["horizons"][f"{horizon}m"] = {
            "count": len(labels),
            "signed_median": _median(labels, "signed_return_atr"),
            "candidate_minus_control_delta": _median(delta_rows, "delta"),
            "matched_candidate_count": len(delta_rows),
            "by_split": {
                split: _median(
                    [row for row in labels if row["split"] == split], "signed_return_atr"
                )
                for split in ("EARLY", "LATE")
            },
            "by_direction": {
                side: {
                    "count": sum(row["direction"] == side for row in labels),
                    "signed_median": _median(
                        [row for row in labels if row["direction"] == side],
                        "signed_return_atr",
                    ),
                }
                for side in ("LONG", "SHORT")
            },
        }
        bootstrap[f"{horizon}m"] = {
            "signed": pooled_bootstrap,
            "matched_delta": matched_bootstrap,
        }
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 150
        or min(int(h8["by_direction"][side]["count"]) for side in ("LONG", "SHORT")) < 30
        or int(summary["day_clusters"]) < 60
    ):
        verdict = "INCONCLUSIVE_LOW_SAMPLE"
    else:
        medians = [
            float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS
        ]
        deltas = [
            float(summary["horizons"][f"{h}m"]["candidate_minus_control_delta"])
            for h in PRIMARY_HORIZONS
        ]
        if all(value <= 0 for value in medians) or all(value <= 0 for value in deltas):
            verdict = "FALSIFIED"
        else:
            supported = (
                all(value > 0 for value in medians + deltas)
                and all(
                    float(bootstrap[f"{h}m"]["signed"]["p05"]) >= -0.05
                    and bootstrap[f"{h}m"]["matched_delta"] is not None
                    and float(bootstrap[f"{h}m"]["matched_delta"]["p05"]) >= -0.05
                    for h in PRIMARY_HORIZONS
                )
                and all(
                    float(summary["horizons"][f"{h}m"]["by_split"][split]) >= -0.05
                    for h in PRIMARY_HORIZONS
                    for split in ("EARLY", "LATE")
                )
                and all(
                    float(
                        summary["horizons"][f"{h}m"]["by_direction"][side]["signed_median"]
                    )
                    >= -0.05
                    for h in PRIMARY_HORIZONS
                    for side in ("LONG", "SHORT")
                )
            )
            verdict = "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"
    summary["verdict"] = verdict
    return summary, bootstrap


def match_opportunity_controls(
    candidates: Sequence[dict[str, Any]],
    decisions: Sequence[dict[str, Any]],
    opportunity_times: set[int],
) -> list[dict[str, Any]]:
    pool = [
        row
        for row in decisions
        if row["feature_status"] == "AVAILABLE"
        and int(row["timestamp_ms"]) not in opportunity_times
    ]
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        eligible = [
            row
            for row in pool
            if row["year"] == candidate["year"]
            and row["direction"] == candidate["direction"]
            and row["atr_decile"] == candidate["atr_decile"]
            and row["btc_mom_bucket"] == candidate["btc_mom_bucket"]
            and abs(int(row["timestamp_ms"]) - int(candidate["timestamp_ms"])) >= DAY_MS
        ]
        for rank, control in enumerate(
            sorted(
                eligible,
                key=lambda row: (
                    abs(int(row["timestamp_ms"]) - int(candidate["timestamp_ms"])),
                    int(row["timestamp_ms"]),
                ),
            )[:5],
            1,
        ):
            output.append(
                {
                    **control,
                    "control_id": f"FLOWCTRL:{control['timestamp_ms']}",
                    "candidate_id": candidate["opportunity_id"],
                    "control_rank": rank,
                }
            )
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run_v0312(
    candles: Sequence[Candle], spot_rows: Sequence[dict[str, Any]], config: AppConfig
) -> dict[str, Any]:
    started = time.perf_counter()
    frozen = replace(
        config,
        strategy=replace(
            config.strategy, enable_derivatives_group=False, enable_order_book_factor=False
        ),
    )
    if frozen.execution.mode != "disabled" or frozen.execution.auto_execute or frozen.execution.allow_live:
        raise ValueError("v0.3.12 requires disabled execution")
    if not candles or candles[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("v0.3.12 Holdout firewall")
    contexts = build_hourly_market_context(candles, frozen)
    decisions = build_flow_decisions(spot_rows, candles, contexts)
    onsets, members = build_flow_episodes(decisions)
    labels = build_flow_labels(onsets, StrictNextOpenSeries(candles))
    h32 = summarize_h32(onsets, labels)
    bootstrap = {
        "seed": SEED,
        "simulations": SIMULATIONS,
        **{
            f"{h}m": _cluster_bootstrap_median(
                [row for row in labels if row["horizon_minutes"] == h],
                "signed_return_atr",
                "week_cluster",
                seed=SEED,
                simulations=SIMULATIONS,
            )
            for h in PRIMARY_HORIZONS
        },
    }
    permutation = _permutation_analysis(
        onsets,
        labels,
        stratum_fields=("year", "atr_decile", "btc_mom_bucket"),
        seed=SEED,
        simulations=SIMULATIONS,
    )
    h32["verdict"] = h32_verdict(h32, bootstrap, permutation)
    h33, h33_bootstrap = incremental_vs_momentum(onsets, labels)
    h33["single_market_diagnostics"] = diagnostic_single_market(onsets, labels)

    replay = run_v033_geometry_audit(
        candles, frozen, (), capture_trend_controls=True, capture_breakout_qualification=True
    )
    union = opportunity_union(
        list(replay["breakout_qualification_rows"]), list(replay["tp_geometry_rows"])
    )
    attached = attach_flow_to_opportunities(union, decisions)
    candidates = [row for row in attached if row["direction"] != "NO_BIAS"]
    matches = match_opportunity_controls(
        candidates, decisions, {int(row["timestamp_ms"]) for row in union}
    )
    h34, h34_bootstrap = summarize_h34(candidates, matches, StrictNextOpenSeries(candles))
    reuse = collections.Counter(str(row["control_id"]) for row in matches)
    h34.update(
        {
            "union_count": len(union),
            "flow_available_count": len(candidates),
            "flow_coverage_pct": 100 * len(candidates) / len(union) if union else None,
            "control_reuse_distribution": dict(
                sorted(collections.Counter(reuse.values()).items())
            ),
        }
    )
    lengths = [float(row["episode_length_decisions"]) for row in onsets]
    recommendation = (
        "STOP_SPOT_PERP_FLOW_FAMILY"
        if h32["verdict"] == "FALSIFIED"
        else "STOP_AS_NON_INCREMENTAL"
        if h32["verdict"] == "SUPPORTED" and h33["verdict"] == "FALSIFIED"
        else "RECOMMEND_DIRECTION_PLUS_OPPORTUNITY_INTEGRATION_RESEARCH"
        if h32["verdict"] == "SUPPORTED" and h33["verdict"] == "SUPPORTED"
        else "INCONCLUSIVE_FLOW_FAMILY"
    )
    return {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "candidate_freeze": False,
            "execution_mode": frozen.execution.mode,
            "runtime_maximum_stage": "OPPORTUNITY_ONLY",
        },
        "flow_decisions": decisions,
        "flow_episode_onsets": onsets,
        "flow_episode_members": members,
        "flow_labels": labels,
        "flow_episode_summary": {
            "raw_decisions": len(decisions),
            "available_decisions": sum(row["feature_status"] == "AVAILABLE" for row in decisions),
            "episode_count": len(onsets),
            "long_count": sum(row["direction"] == "LONG" for row in onsets),
            "short_count": sum(row["direction"] == "SHORT" for row in onsets),
            "length_decisions": {
                "p25": _percentile(lengths, 0.25),
                "median": _percentile(lengths, 0.5),
                "p75": _percentile(lengths, 0.75),
                "max": max(lengths) if lengths else None,
            },
        },
        "h32_summary": h32,
        "h32_bootstrap": bootstrap,
        "h32_permutation": permutation,
        "h33_incremental": h33,
        "h33_bootstrap": h33_bootstrap,
        "opportunity_flow_events": attached,
        "opportunity_control_matches": matches,
        "h34_summary": h34,
        "h34_bootstrap": h34_bootstrap,
        "movement_smoke": {
            "passed": True,
            "frozen_geometry_counts": replay["scope_counts"],
            "excursion_summary": replay["excursion_summary"],
            "reachability_summary": replay["reachability_summary"],
            "hypothesis_verdicts": replay["hypothesis_verdicts"],
            "performance": replay["performance"],
        },
        "by_year_side": {
            str(year): {
                side: sum(row["year"] == year and row["direction"] == side for row in onsets)
                for side in ("LONG", "SHORT")
            }
            for year in sorted({int(row["year"]) for row in onsets})
        },
        "hypothesis_verdicts": {
            "H32": h32["verdict"],
            "H33": h33["verdict"],
            "H34": h34["verdict"],
        },
        "recommendation": recommendation,
        "overall_status": "SPOT_PERP_FLOW_QUALIFICATION_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        },
    }


def write_v0312_artifacts(
    output: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol: str | Path,
    btc_manifest: str | Path,
    spot_manifest: str | Path,
) -> Path:
    target = Path(output)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("immutable v0.3.12 run exists")
    target.mkdir(parents=True, exist_ok=True)
    protocol_path, btc_path, spot_path = Path(protocol), Path(btc_manifest), Path(spot_manifest)
    shutil.copyfile(protocol_path, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol_path) + "\n", encoding="utf-8")
    shutil.copyfile(spot_path, target / "spot_data_manifest.json")
    spot = json.loads(spot_path.read_text(encoding="utf-8"))
    audit_keys = (
        "row_count",
        "expected_bars",
        "missing_count",
        "duplicate_count",
        "out_of_order_count",
        "invalid_volume_count",
        "zero_volume_count",
        "known_gaps",
        "timestamp_normalization",
    )
    (target / "spot_data_audit.json").write_text(
        json.dumps({key: spot[key] for key in audit_keys}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pa, pq = importlib.import_module("pyarrow"), importlib.import_module("pyarrow.parquet")
    for key, filename in (
        ("flow_decisions", "flow_decisions.parquet"),
        ("flow_episode_onsets", "flow_episode_onsets.parquet"),
        ("flow_labels", "flow_labels.parquet"),
        ("opportunity_flow_events", "opportunity_flow_events.parquet"),
        ("opportunity_control_matches", "opportunity_control_matches.parquet"),
    ):
        pq.write_table(pa.Table.from_pylist(result[key]), target / filename, compression="zstd")
    for key in (
        "h32_summary",
        "h32_bootstrap",
        "h32_permutation",
        "h33_incremental",
        "h33_bootstrap",
        "h34_summary",
        "h34_bootstrap",
        "by_year_side",
    ):
        (target / f"{key}.json").write_text(
            json.dumps(result[key], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    summary = {
        key: value
        for key, value in result.items()
        if key
        not in {
            "flow_decisions",
            "flow_episode_onsets",
            "flow_episode_members",
            "flow_labels",
            "opportunity_flow_events",
            "opportunity_control_matches",
            "h32_summary",
            "h32_bootstrap",
            "h32_permutation",
            "h33_incremental",
            "h33_bootstrap",
            "h34_summary",
            "h34_bootstrap",
            "by_year_side",
        }
    }
    summary["provenance"] = {
        "git_sha": sha,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "protocol_sha256": _sha256(protocol_path),
        "btc_dataset_sha256": json.loads(btc_path.read_text())["checksum_sha256"],
        "spot_dataset_sha256": spot["checksum_sha256"],
        "config_hash": config.config_hash,
        "seed": SEED,
        "simulations": SIMULATIONS,
        "python_version": platform.python_version(),
    }
    (target / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
