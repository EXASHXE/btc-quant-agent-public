from __future__ import annotations

import collections
import hashlib
import importlib
import json
import platform
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
from .causal_entry_research import IndexedOneMinuteSeries
from .config import AppConfig
from .domain import Candle
from .engine import HistoricalFeatureCache, QuantEngine
from .funding_crowding_research import (
    PRIMARY_HORIZONS,
    StrictAfterPriceSeries,
    _cluster_bootstrap_median,
    _decorate_funding_features,
    _funding_label_rows,
    _h19_summary,
    _match_movement_controls,
    _movement_analysis,
    _percentile,
    _permutation_analysis,
    attach_funding_to_opportunities,
    build_funding_features,
    opportunity_union,
)
from .geometry_research import run_v033_geometry_audit
from .regime import classify_regime
from .research import DEV_END_MS

SEED = 38
SIMULATIONS = 2000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_extreme_episodes(
    features: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    onsets: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    active_direction: str | None = None
    episode_id: str | None = None
    episode_index = -1
    for row in features:
        direction = str(row["funding_direction"])
        if direction == "NO_BIAS":
            active_direction = None
            episode_id = None
            episode_index = -1
            continue
        if direction != active_direction:
            active_direction = direction
            episode_id = f"FE:{row['timestamp_ms']}:{direction}"
            episode_index = 0
            onset = {**row, "episode_id": episode_id, "episode_index": 0}
            onsets.append(onset)
        else:
            episode_index += 1
        members.append({**row, "episode_id": episode_id, "episode_index": episode_index})
    by_episode: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in members:
        by_episode[str(row["episode_id"])].append(row)
    for onset in onsets:
        block = by_episode[str(onset["episode_id"])]
        onset["length_settlements"] = len(block)
        onset["duration_hours"] = (
            int(block[-1]["timestamp_ms"]) - int(block[0]["timestamp_ms"])
        ) / 3_600_000 + 8
    return onsets, members


def _episode_summary(onsets: Sequence[dict[str, Any]]) -> dict[str, Any]:
    lengths = [float(row["length_settlements"]) for row in onsets]
    durations = [float(row["duration_hours"]) for row in onsets]
    return {
        "episode_count": len(onsets),
        "long_count": sum(row["funding_direction"] == "LONG" for row in onsets),
        "short_count": sum(row["funding_direction"] == "SHORT" for row in onsets),
        "length_settlements": {
            "p25": _percentile(lengths, 0.25),
            "median": _percentile(lengths, 0.5),
            "p75": _percentile(lengths, 0.75),
            "max": max(lengths),
        },
        "median_duration_hours": statistics.median(durations),
        "by_year": dict(sorted(collections.Counter(int(row["year"]) for row in onsets).items())),
        "by_split": dict(sorted(collections.Counter(str(row["split"]) for row in onsets).items())),
    }


def h22_verdict(
    summary: dict[str, Any],
    bootstrap: dict[str, Any],
    permutation: dict[str, Any],
    early_late: dict[str, Any],
) -> str:
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 250
        or min(int(h8["by_direction"][side]["count"]) for side in ("LONG", "SHORT")) < 75
        or int(summary["week_clusters"]) < 80
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    medians = [float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS]
    deltas = [
        float(permutation["horizons"][f"{h}m"]["deterministic_point_delta"])
        for h in PRIMARY_HORIZONS
    ]
    if all(value <= 0 for value in medians) or all(value <= 0 for value in deltas):
        return "FALSIFIED"
    supported = (
        all(value > 0 for value in medians + deltas)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
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


def _persistence_attribution(
    members: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    label_map = {
        (int(row["timestamp_ms"]), int(row["horizon_minutes"])): row
        for row in labels
        if not row["incomplete"]
    }
    output: dict[str, Any] = {"diagnostic_only": True, "buckets": {}}
    for name in ("episode_index_0", "episode_index_1", "episode_index_gte_2"):
        selected = [
            row
            for row in members
            if (
                int(row["episode_index"]) == 0
                if name == "episode_index_0"
                else int(row["episode_index"]) == 1
                if name == "episode_index_1"
                else int(row["episode_index"]) >= 2
            )
        ]
        block: dict[str, Any] = {"settlement_count": len(selected), "horizons": {}}
        for horizon in PRIMARY_HORIZONS:
            rows = [
                label_map[(int(row["timestamp_ms"]), horizon)]
                for row in selected
                if (int(row["timestamp_ms"]), horizon) in label_map
            ]
            block["horizons"][f"{horizon}m"] = {
                "count": len(rows),
                "signed_median": statistics.median(float(row["signed_return_atr"]) for row in rows)
                if rows
                else None,
                "mfe_median": statistics.median(float(row["mfe_atr"]) for row in rows)
                if rows
                else None,
                "mae_median": statistics.median(float(row["mae_atr"]) for row in rows)
                if rows
                else None,
                "by_split": {
                    split: (
                        statistics.median(
                            float(row["signed_return_atr"]) for row in rows if row["split"] == split
                        )
                        if any(row["split"] == split for row in rows)
                        else None
                    )
                    for split in ("EARLY", "LATE")
                },
                "by_direction": {
                    side: (
                        statistics.median(
                            float(row["signed_return_atr"])
                            for row in rows
                            if row["funding_direction"] == side
                        )
                        if any(row["funding_direction"] == side for row in rows)
                        else None
                    )
                    for side in ("LONG", "SHORT")
                },
            }
        output["buckets"][name] = block
    return output


def _decorate_market_state(
    rows: Sequence[dict[str, Any]], candles: Sequence[Candle], config: AppConfig
) -> None:
    hourly = resample(candles, "1h")
    closes = [bar.close_time_ms for bar in hourly]
    engine = QuantEngine(config, HistoricalFeatureCache())
    import bisect

    for row in rows:
        index = bisect.bisect_right(closes, int(row["timestamp_ms"])) - 1
        history = hourly[max(0, index - config.data.history_limit_1h + 1) : index + 1]
        snapshot = engine.diagnostic_features("1h", history)
        row["market_state"] = classify_regime(snapshot, config.strategy).value
        row["market_state_feature_close_ms"] = snapshot.bar_close_time_ms


def _state_attribution(
    onsets: Sequence[dict[str, Any]],
    labels: Sequence[dict[str, Any]],
    features: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    label_map = {
        (int(row["timestamp_ms"]), int(row["horizon_minutes"])): row
        for row in labels
        if not row["incomplete"]
    }
    states: dict[str, Any] = {}
    for state in sorted({str(row["market_state"]) for row in onsets}):
        selected = [row for row in onsets if row["market_state"] == state]
        states[state] = {
            "count": len(selected),
            "long": sum(row["funding_direction"] == "LONG" for row in selected),
            "short": sum(row["funding_direction"] == "SHORT" for row in selected),
            "horizons": {},
        }
        for horizon in PRIMARY_HORIZONS:
            rows = [
                label_map[(int(row["timestamp_ms"]), horizon)]
                for row in selected
                if (int(row["timestamp_ms"]), horizon) in label_map
            ]
            states[state]["horizons"][f"{horizon}m"] = {
                "signed_median": statistics.median(float(row["signed_return_atr"]) for row in rows)
                if rows
                else None,
                "early": statistics.median(
                    float(row["signed_return_atr"]) for row in rows if row["split"] == "EARLY"
                )
                if any(row["split"] == "EARLY" for row in rows)
                else None,
                "late": statistics.median(
                    float(row["signed_return_atr"]) for row in rows if row["split"] == "LATE"
                )
                if any(row["split"] == "LATE" for row in rows)
                else None,
                "bootstrap": _cluster_bootstrap_median(
                    rows, "signed_return_atr", "week_cluster", seed=SEED, simulations=SIMULATIONS
                )
                if rows
                else None,
            }
    rates: dict[str, Any] = {}
    for split in ("EARLY", "LATE"):
        values = [float(row["funding_rate"]) for row in features if row["split"] == split]
        rates[split] = {
            "count": len(values),
            "p25": _percentile(values, 0.25),
            "median": _percentile(values, 0.5),
            "p75": _percentile(values, 0.75),
            "extreme_frequency": sum(
                row["funding_direction"] != "NO_BIAS" for row in features if row["split"] == split
            )
            / len(values),
        }
    rates["by_tail"] = {}
    for side in ("LONG", "SHORT", "NO_BIAS"):
        values = [
            float(row["funding_rate"]) for row in features if row["funding_direction"] == side
        ]
        rates["by_tail"][side] = {
            "count": len(values),
            "p25": _percentile(values, 0.25),
            "median": _percentile(values, 0.5),
            "p75": _percentile(values, 0.75),
        }
    side_stable = []
    for side in ("LONG", "SHORT"):
        if all(
            statistics.median(
                float(row["signed_return_atr"])
                for row in labels
                if row["funding_direction"] == side
                and row["split"] == split
                and row["horizon_minutes"] == h
                and not row["incomplete"]
            )
            > 0
            for split in ("EARLY", "LATE")
            for h in PRIMARY_HORIZONS
        ):
            side_stable.append(side)
    state_explanations = [
        state
        for state, block in states.items()
        if all(
            block["horizons"][f"{h}m"][split.lower()] is not None
            and float(block["horizons"][f"{h}m"][split.lower()]) > 0
            for split in ("EARLY", "LATE")
            for h in PRIMARY_HORIZONS
        )
    ]
    verdict = "SUPPORTED" if side_stable and state_explanations else "INCONCLUSIVE_MECHANISM"
    return {
        "states": states,
        "funding_rate_distribution": rates,
        "stable_positive_sides": side_stable,
        "stable_positive_states": state_explanations,
        "verdict": verdict,
    }


def _interaction_label(
    identity: dict[str, Any], series: IndexedOneMinuteSeries, horizon: int
) -> dict[str, Any]:
    bars, incomplete = series.bounded_window(int(identity["decision_close_ms"]), horizon)
    atr = float(identity["atr"])
    if incomplete or not bars or atr <= 0:
        return {"horizon_minutes": horizon, "incomplete": True}
    reference = float(identity["close"])
    high, low = max(bar.high for bar in bars), min(bar.low for bar in bars)
    raw = (bars[-1].close - reference) / atr
    if identity["funding_direction"] == "LONG":
        signed, mfe, mae = raw, max(0.0, high - reference) / atr, max(0.0, reference - low) / atr
    else:
        signed, mfe, mae = -raw, max(0.0, reference - low) / atr, max(0.0, high - reference) / atr
    return {
        "horizon_minutes": horizon,
        "incomplete": False,
        "signed_return_atr": signed,
        "mfe_atr": mfe,
        "mae_atr": mae,
        "reach_1_0": mfe >= 1.0,
    }


def _interaction_analysis(
    candidates: Sequence[dict[str, Any]],
    matches: Sequence[dict[str, Any]],
    series: IndexedOneMinuteSeries,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidate_labels = [
        {
            "event_id": row["opportunity_id"],
            "timestamp_ms": row["timestamp_ms"],
            "funding_direction": row["funding_direction"],
            "split": row["split"],
            "day_cluster": row["day_cluster"],
            **_interaction_label(row, series, horizon),
        }
        for row in candidates
        for horizon in PRIMARY_HORIZONS
    ]
    label_map = {
        (str(row["event_id"]), int(row["horizon_minutes"])): row
        for row in candidate_labels
        if not row["incomplete"]
    }
    pair_rows: list[dict[str, Any]] = []
    for match in matches:
        identity = str(match["candidate_id"])
        for horizon in PRIMARY_HORIZONS:
            candidate = label_map.get((identity, horizon))
            control = _interaction_label(match, series, horizon)
            if candidate is None or control["incomplete"]:
                continue
            pair_rows.append(
                {
                    "candidate_id": identity,
                    "candidate_timestamp_ms": next(
                        row["timestamp_ms"]
                        for row in candidates
                        if row["opportunity_id"] == identity
                    ),
                    "control_id": match["control_id"],
                    "control_timestamp_ms": match["timestamp_ms"],
                    "control_rank": match["control_rank"],
                    "horizon_minutes": horizon,
                    "candidate_signed": candidate["signed_return_atr"],
                    "control_signed": control["signed_return_atr"],
                    "candidate_mfe": candidate["mfe_atr"],
                    "control_mfe": control["mfe_atr"],
                    "candidate_mae": candidate["mae_atr"],
                    "control_mae": control["mae_atr"],
                    "candidate_reach_1_0": candidate["reach_1_0"],
                    "control_reach_1_0": control["reach_1_0"],
                }
            )
    summary: dict[str, Any] = {
        "candidate_count": len(candidates),
        "day_clusters": len({row["day_cluster"] for row in candidates}),
        "horizons": {},
    }
    bootstrap: dict[str, Any] = {}
    for horizon in PRIMARY_HORIZONS:
        labels = [
            row
            for row in candidate_labels
            if row["horizon_minutes"] == horizon and not row["incomplete"]
        ]
        pairs = [row for row in pair_rows if row["horizon_minutes"] == horizon]
        by_candidate: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for row in pairs:
            by_candidate[str(row["candidate_id"])].append(row)
        candidate_deltas = {
            identity: statistics.median(float(row["candidate_signed"]) for row in block)
            - statistics.median(float(row["control_signed"]) for row in block)
            for identity, block in by_candidate.items()
        }
        deltas = list(candidate_deltas.values())
        candidate_by_id = {str(row["opportunity_id"]): row for row in candidates}
        delta_rows = [
            {
                "delta": value,
                "day_cluster": candidate_by_id[identity]["day_cluster"],
                "incomplete": False,
            }
            for identity, value in candidate_deltas.items()
        ]
        summary["horizons"][f"{horizon}m"] = {
            "count": len(labels),
            "signed_median": statistics.median(float(row["signed_return_atr"]) for row in labels),
            "candidate_minus_control_delta": statistics.median(deltas) if deltas else None,
            "candidate_minus_control_bootstrap": _cluster_bootstrap_median(
                delta_rows, "delta", "day_cluster", seed=SEED, simulations=SIMULATIONS
            )
            if delta_rows
            else None,
            "candidate_metrics": {
                "mfe_median": statistics.median(float(row["mfe_atr"]) for row in labels),
                "mae_median": statistics.median(float(row["mae_atr"]) for row in labels),
                "reach_1_0_rate": statistics.mean(float(row["reach_1_0"]) for row in labels),
            },
            "matched_control_metrics": {
                metric: statistics.median(float(row[f"control_{metric}"]) for row in pairs)
                if metric != "reach_1_0"
                else statistics.mean(float(row[f"control_{metric}"]) for row in pairs)
                for metric in ("mfe", "mae", "reach_1_0")
            },
            "by_direction": {
                side: {
                    "count": sum(row["funding_direction"] == side for row in labels),
                    "signed_median": statistics.median(
                        float(row["signed_return_atr"])
                        for row in labels
                        if row["funding_direction"] == side
                    )
                    if any(row["funding_direction"] == side for row in labels)
                    else None,
                }
                for side in ("LONG", "SHORT")
            },
            "by_split": {
                split: statistics.median(
                    float(row["signed_return_atr"]) for row in labels if row["split"] == split
                )
                if any(row["split"] == split for row in labels)
                else None
                for split in ("EARLY", "LATE")
            },
        }
        bootstrap[f"{horizon}m"] = _cluster_bootstrap_median(
            labels, "signed_return_atr", "day_cluster", seed=SEED, simulations=SIMULATIONS
        )
    summary["bootstrap"] = bootstrap
    return summary, pair_rows


def interaction_verdict(summary: dict[str, Any]) -> str:
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 150
        or min(int(h8["by_direction"][side]["count"]) for side in ("LONG", "SHORT")) < 30
        or int(summary["day_clusters"]) < 60
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    medians = [float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS]
    deltas = [
        float(summary["horizons"][f"{h}m"]["candidate_minus_control_delta"])
        for h in PRIMARY_HORIZONS
    ]
    if all(value <= 0 for value in medians) or all(value <= 0 for value in deltas):
        return "FALSIFIED"
    supported = (
        all(value > 0 for value in medians + deltas)
        and all(float(summary["bootstrap"][f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(
            float(summary["horizons"][f"{h}m"]["by_split"][split]) > 0
            for h in PRIMARY_HORIZONS
            for split in ("EARLY", "LATE")
        )
        and all(
            float(summary["horizons"][f"{h}m"]["by_direction"][side]["signed_median"]) >= -0.05
            for h in PRIMARY_HORIZONS
            for side in ("LONG", "SHORT")
        )
    )
    return "SUPPORTED" if supported else "INCONCLUSIVE_MECHANISM"


def _year_stability(labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(year): {
            f"{horizon}m_signed_median": statistics.median(
                float(row["signed_return_atr"])
                for row in labels
                if int(row["year"]) == year
                and row["horizon_minutes"] == horizon
                and not row["incomplete"]
            )
            for horizon in PRIMARY_HORIZONS
        }
        for year in sorted({int(row["year"]) for row in labels})
    }


def run_v038_funding_stability(
    candles: Sequence[Candle],
    funding_events: Sequence[FundingEvent],
    config: AppConfig,
    *,
    seed: int = SEED,
) -> dict[str, Any]:
    if seed != SEED:
        raise ValueError("v0.3.8 preregistered seed is 38")
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
        raise ValueError("v0.3.8 requires disabled execution")
    if (
        not candles
        or candles[-1].close_time_ms >= DEV_END_MS
        or any(row.timestamp_ms >= DEV_END_MS for row in funding_events)
    ):
        raise ValueError("v0.3.8 holdout firewall")
    replay = run_v033_geometry_audit(
        candles, frozen, (), capture_trend_controls=True, capture_breakout_qualification=True
    )
    features = build_funding_features(funding_events)
    _decorate_funding_features(features, candles, frozen)
    valid = [row for row in features if row["feature_status"] != "WARMUP_INCOMPLETE"]
    onsets, members = build_extreme_episodes(valid)
    _decorate_market_state(onsets, candles, frozen)
    price_series = StrictAfterPriceSeries(candles)
    onset_labels = _funding_label_rows(onsets, price_series)
    member_labels = _funding_label_rows(members, price_series)
    h22_summary, h22_boot, _, h22_splits = _h19_summary(onsets, onset_labels)
    h22_perm = _permutation_analysis(onsets, onset_labels, stratum_fields=("year", "atr_decile"))
    h22 = h22_verdict(h22_summary, h22_boot, h22_perm, h22_splits)
    h23 = _state_attribution(onsets, onset_labels, valid)
    controls = list(replay["trend_control_rows"])
    control_map = {int(row["timestamp_ms"]): row for row in controls}
    indexed = IndexedOneMinuteSeries(candles)
    interactions: dict[str, Any] = {}
    matched_tables: dict[str, list[dict[str, Any]]] = {}
    opportunity_sets: dict[str, list[dict[str, Any]]] = {}
    for name, raw in (
        ("TP", list(replay["tp_geometry_rows"])),
        ("BR", list(replay["breakout_qualification_rows"])),
    ):
        union = opportunity_union(raw if name == "BR" else [], raw if name == "TP" else [])
        attached = attach_funding_to_opportunities(union, features, control_map)
        candidates = [row for row in attached if row["funding_direction"] != "NO_BIAS"]
        matches = _match_movement_controls(
            candidates, controls, features, {int(row["timestamp_ms"]) for row in union}
        )
        summary, table = _interaction_analysis(candidates, matches, indexed)
        summary["verdict"] = interaction_verdict(summary)
        interactions[name] = summary
        matched_tables[name] = table
        opportunity_sets[name] = candidates
    all_union = opportunity_union(
        list(replay["breakout_qualification_rows"]), list(replay["tp_geometry_rows"])
    )
    all_attached = attach_funding_to_opportunities(all_union, features, control_map)
    all_candidates = [row for row in all_attached if row["funding_direction"] != "NO_BIAS"]
    movement_matches = _match_movement_controls(
        all_candidates, controls, features, {int(row["timestamp_ms"]) for row in all_union}
    )
    movement, movement_boot = _movement_analysis(all_candidates, movement_matches, indexed)
    movement["bootstrap"] = movement_boot
    movement["same_positive_direction_as_v037"] = all(
        float(movement["horizons"][f"{h}m"]["metrics"]["future_range_atr"]["delta"]) > 0
        for h in PRIMARY_HORIZONS
    )
    h24, h25 = interactions["TP"]["verdict"], interactions["BR"]["verdict"]
    if h22 == "SUPPORTED" and (h24 == "SUPPORTED" or h25 == "SUPPORTED"):
        recommendation = "RECOMMEND_FUNDING_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE_RESEARCH"
    elif h22 == "SUPPORTED":
        recommendation = "RECOMMEND_FUNDING_EPISODE_DIRECTION_FOR_PROTOTYPE_RESEARCH"
    elif h24 == "SUPPORTED" and h25 != "SUPPORTED":
        recommendation = "RECOMMEND_FUNDING_TP_INTERACTION_FOR_PROTOTYPE_RESEARCH"
    elif h22 == "FALSIFIED" or all(value not in {"SUPPORTED"} for value in (h22, h24, h25)):
        recommendation = (
            "STOP_FUNDING_FAMILY_MOVE_TO_CROSS_ASSET"
            if any(value == "FALSIFIED" for value in (h22, h24, h25))
            else "INCONCLUSIVE_STOP_FUNDING_UNTIL_NEW_FORWARD_DATA"
        )
    else:
        recommendation = "INCONCLUSIVE_STOP_FUNDING_UNTIL_NEW_FORWARD_DATA"
    return {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "end_ms_exclusive": DEV_END_MS,
            "execution_mode": frozen.execution.mode,
            "candidate_freeze": False,
        },
        "funding_episode_onsets": onsets,
        "funding_episode_members": members,
        "episode_summary": _episode_summary(onsets),
        "h22_episode_directionality": {
            **h22_summary,
            "permutation": h22_perm,
            "early_late": h22_splits,
            "verdict": h22,
        },
        "h22_bootstrap": h22_boot,
        "persistence_attribution": _persistence_attribution(members, member_labels),
        "h23_time_state_attribution": h23,
        "h24_tp_funding_interaction": interactions["TP"],
        "h24_tp_matched_controls": matched_tables["TP"],
        "h25_br_funding_interaction": interactions["BR"],
        "h25_br_matched_controls": matched_tables["BR"],
        "early_late_year_stability": {
            "h22_early_late": h22_splits,
            "h22_by_year": _year_stability(onset_labels),
        },
        "movement_reproduction": movement,
        "hypothesis_verdicts": {"H22": h22, "H23": h23["verdict"], "H24": h24, "H25": h25},
        "recommendation": recommendation,
        "overall_status": "FUNDING_STABILITY_DIAGNOSTIC_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "replay": replay["performance"],
        },
    }


def write_v038_artifacts(
    output_dir: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol_path: str | Path,
    manifest_path: str | Path,
    funding_path: str | Path,
) -> Path:
    target = Path(output_dir)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"immutable v0.3.8 run exists: {target}")
    target.mkdir(parents=True, exist_ok=True)
    protocol, manifest, funding = Path(protocol_path), Path(manifest_path), Path(funding_path)
    shutil.copyfile(protocol, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol) + "\n", encoding="utf-8")
    shutil.copyfile(manifest, target / "data_manifest.json")
    pa, pq = importlib.import_module("pyarrow"), importlib.import_module("pyarrow.parquet")
    for key in (
        "funding_episode_onsets",
        "funding_episode_members",
        "h24_tp_matched_controls",
        "h25_br_matched_controls",
    ):
        pq.write_table(pa.Table.from_pylist(result[key]), target / f"{key}.parquet")
    names = (
        "episode_summary",
        "h22_episode_directionality",
        "h22_bootstrap",
        "persistence_attribution",
        "h23_time_state_attribution",
        "h24_tp_funding_interaction",
        "h25_br_funding_interaction",
        "early_late_year_stability",
        "movement_reproduction",
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
        | {
            "funding_episode_onsets",
            "funding_episode_members",
            "h24_tp_matched_controls",
            "h25_br_matched_controls",
        }
    }
    summary["provenance"] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "config_hash": config.config_hash,
        "price_manifest_sha256": _sha256(manifest),
        "funding_csv_sha256": _sha256(funding),
        "protocol_sha256": _sha256(protocol),
        "seed": SEED,
        "simulations": SIMULATIONS,
        "python_version": platform.python_version(),
    }
    (target / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target
