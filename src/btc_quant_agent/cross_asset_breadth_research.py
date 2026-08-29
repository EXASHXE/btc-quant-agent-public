from __future__ import annotations

import bisect
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

from .backtest import resample
from .causal_entry_research import IndexedOneMinuteSeries
from .config import AppConfig
from .domain import Candle
from .engine import HistoricalFeatureCache, QuantEngine
from .funding_crowding_research import (
    PRIMARY_HORIZONS,
    _cluster_bootstrap_median,
    _movement_analysis,
    _percentile,
    _permutation_analysis,
    opportunity_union,
)
from .funding_stability_research import _interaction_analysis, interaction_verdict
from .geometry_research import run_v033_geometry_audit
from .regime import classify_regime
from .research import DEV_END_MS

BASKET = ("ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LTCUSDT")
SEED = 39
SIMULATIONS = 2000
LATE_START_MS = 1_704_067_200_000
HORIZONS = (240, 480, 1440)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_hourly_basket(root: str | Path) -> dict[str, list[dict[str, Any]]]:
    pq = importlib.import_module("pyarrow.parquet")
    return {
        symbol: pq.read_table(Path(root) / f"{symbol}.parquet").to_pylist() for symbol in BASKET
    }


def xab_direction(returns: Sequence[float]) -> str:
    if len(returns) != 5:
        raise ValueError("XAB4H requires all five frozen basket members")
    positive = sum(value > 0 for value in returns)
    negative = sum(value < 0 for value in returns)
    if positive >= 4:
        return "LONG"
    if negative >= 4:
        return "SHORT"
    return "NO_BIAS"


def btc_momentum_direction(value: float) -> str:
    return "LONG" if value > 0 else "SHORT" if value < 0 else "NO_BIAS"


def build_hourly_features(
    basket: dict[str, list[dict[str, Any]]], btc_hourly: Sequence[Candle], config: AppConfig
) -> list[dict[str, Any]]:
    maps = {
        symbol: {int(row["open_time_ms"]): row for row in rows} for symbol, rows in basket.items()
    }
    engine = QuantEngine(config, HistoricalFeatureCache())
    output: list[dict[str, Any]] = []
    for index, btc in enumerate(btc_hourly):
        if index < 4:
            continue
        opens = [btc.open_time_ms - offset * 3_600_000 for offset in range(5)]
        available = all(open_time in maps[symbol] for symbol in BASKET for open_time in opens)
        timestamp = btc.close_time_ms + 1
        base: dict[str, Any] = {
            "timestamp_ms": timestamp,
            "decision_close_ms": btc.close_time_ms,
            "feature_time_ms": btc.close_time_ms,
            "bar_index": index,
            "close": btc.close,
            "year": datetime.fromtimestamp(timestamp / 1000, UTC).year,
            "split": "LATE" if timestamp >= LATE_START_MS else "EARLY",
            "week_cluster": datetime.fromtimestamp(timestamp / 1000, UTC).strftime("%G-W%V"),
            "day_cluster": datetime.fromtimestamp(timestamp / 1000, UTC).strftime("%Y-%m-%d"),
        }
        snapshot = engine.diagnostic_features(
            "1h", list(btc_hourly[max(0, index - config.data.history_limit_1h + 1) : index + 1])
        )
        btc_return = btc.close / btc_hourly[index - 4].close - 1
        base.update(
            {
                "atr": snapshot.atr,
                "atr_percentile": snapshot.atr_percentile,
                "atr_decile": min(9, int(snapshot.atr_percentile * 10)),
                "market_state": classify_regime(snapshot, config.strategy).value,
                "btc_trailing_4h_return": btc_return,
                "btc_mom_direction": btc_momentum_direction(btc_return),
                "btc_mom_bucket": "POSITIVE"
                if btc_return > 0
                else "NEGATIVE"
                if btc_return < 0
                else "ZERO",
                "btc_feature_close_ms": snapshot.bar_close_time_ms,
            }
        )
        if not available:
            output.append(
                {
                    **base,
                    "feature_status": "DATA_UNAVAILABLE",
                    "direction": "NO_BIAS",
                    "funding_direction": "NO_BIAS",
                }
            )
            continue
        returns = {
            symbol: float(maps[symbol][btc.open_time_ms]["close"])
            / float(maps[symbol][btc.open_time_ms - 4 * 3_600_000]["close"])
            - 1
            for symbol in BASKET
        }
        direction = xab_direction(tuple(returns.values()))
        output.append(
            {
                **base,
                "feature_status": "EXTREME" if direction != "NO_BIAS" else "NO_BIAS",
                "direction": direction,
                "funding_direction": direction,
                "positive_count": sum(value > 0 for value in returns.values()),
                "negative_count": sum(value < 0 for value in returns.values()),
                **{f"{symbol}_r4h": value for symbol, value in returns.items()},
            }
        )
    return output


def build_breadth_episodes(
    features: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    onsets: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    active: str | None = None
    identity: str | None = None
    member_index = -1
    for row in features:
        direction = str(row["direction"])
        if row["feature_status"] == "DATA_UNAVAILABLE" or direction == "NO_BIAS":
            active, identity, member_index = None, None, -1
            continue
        if direction != active:
            active, identity, member_index = direction, f"XAB:{row['timestamp_ms']}:{direction}", 0
            onsets.append({**row, "event_id": identity, "episode_id": identity, "episode_index": 0})
        else:
            member_index += 1
        members.append({**row, "episode_id": identity, "episode_index": member_index})
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in members:
        grouped[str(row["episode_id"])].append(row)
    for row in onsets:
        row["episode_length_hours"] = len(grouped[str(row["episode_id"])])
    return onsets, members


def _direction_label(
    identity: dict[str, Any],
    series: IndexedOneMinuteSeries,
    horizon: int,
    direction: str | None = None,
) -> dict[str, Any]:
    bars, incomplete = series.bounded_window(int(identity["decision_close_ms"]), horizon)
    atr, reference = float(identity["atr"]), float(identity["close"])
    if incomplete or not bars or atr <= 0:
        return {"horizon_minutes": horizon, "incomplete": True}
    chosen = direction or str(identity["direction"])
    raw = (bars[-1].close - reference) / atr
    high, low = max(bar.high for bar in bars), min(bar.low for bar in bars)
    if chosen == "LONG":
        signed, mfe, mae = raw, max(0.0, high - reference) / atr, max(0.0, reference - low) / atr
    else:
        signed, mfe, mae = -raw, max(0.0, reference - low) / atr, max(0.0, high - reference) / atr
    return {
        "horizon_minutes": horizon,
        "incomplete": False,
        "raw_return_atr": raw,
        "signed_return_atr": signed,
        "mfe_atr": mfe,
        "mae_atr": mae,
        "reach_1_0": mfe >= 1,
        "reach_1_5": mfe >= 1.5,
        "reach_2_5": mfe >= 2.5,
    }


def build_labels(
    events: Sequence[dict[str, Any]], series: IndexedOneMinuteSeries
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row["event_id"],
            "timestamp_ms": row["timestamp_ms"],
            "year": row["year"],
            "split": row["split"],
            "week_cluster": row["week_cluster"],
            "direction": row["direction"],
            "funding_direction": row["direction"],
            "btc_mom_direction": row["btc_mom_direction"],
            **_direction_label(row, series, horizon),
        }
        for row in events
        for horizon in HORIZONS
    ]


def _summary(events: Sequence[dict[str, Any]], labels: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "episode_count": len(events),
        "long": sum(row["direction"] == "LONG" for row in events),
        "short": sum(row["direction"] == "SHORT" for row in events),
        "week_clusters": len({row["week_cluster"] for row in events}),
        "horizons": {},
    }
    for horizon in HORIZONS:
        rows = [
            row for row in labels if row["horizon_minutes"] == horizon and not row["incomplete"]
        ]
        output["horizons"][f"{horizon}m"] = {
            "count": len(rows),
            "signed_median": statistics.median(float(row["signed_return_atr"]) for row in rows),
            "mfe_median": statistics.median(float(row["mfe_atr"]) for row in rows),
            "mae_median": statistics.median(float(row["mae_atr"]) for row in rows),
            "reach_1_0": statistics.mean(float(row["reach_1_0"]) for row in rows),
            "reach_1_5": statistics.mean(float(row["reach_1_5"]) for row in rows),
            "reach_2_5": statistics.mean(float(row["reach_2_5"]) for row in rows),
            "by_split": {
                split: statistics.median(
                    float(row["signed_return_atr"]) for row in rows if row["split"] == split
                )
                for split in ("EARLY", "LATE")
            },
            "by_direction": {
                side: {
                    "count": sum(row["direction"] == side for row in rows),
                    "signed_median": statistics.median(
                        float(row["signed_return_atr"]) for row in rows if row["direction"] == side
                    ),
                }
                for side in ("LONG", "SHORT")
            },
        }
    return output


def h26_verdict(
    summary: dict[str, Any], bootstrap: dict[str, Any], permutation: dict[str, Any]
) -> str:
    h8 = summary["horizons"]["480m"]
    if (
        int(h8["count"]) < 250
        or min(int(h8["by_direction"][s]["count"]) for s in ("LONG", "SHORT")) < 75
        or int(summary["week_clusters"]) < 80
    ):
        return "INCONCLUSIVE_LOW_SAMPLE"
    med = [float(summary["horizons"][f"{h}m"]["signed_median"]) for h in PRIMARY_HORIZONS]
    perm = [
        float(permutation["horizons"][f"{h}m"]["deterministic_point_delta"])
        for h in PRIMARY_HORIZONS
    ]
    if all(v <= 0 for v in med) or all(v <= 0 for v in perm):
        return "FALSIFIED"
    ok = (
        all(v > 0 for v in med + perm)
        and all(float(bootstrap[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(
            float(summary["horizons"][f"{h}m"]["by_split"][s]) > 0
            for h in PRIMARY_HORIZONS
            for s in ("EARLY", "LATE")
        )
        and all(
            float(summary["horizons"][f"{h}m"]["by_direction"][s]["signed_median"]) >= -0.05
            for h in PRIMARY_HORIZONS
            for s in ("LONG", "SHORT")
        )
    )
    return "SUPPORTED" if ok else "INCONCLUSIVE_MECHANISM"


def _h27(
    events: Sequence[dict[str, Any]],
    labels: Sequence[dict[str, Any]],
    permutation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    label_map = {
        (str(row["event_id"]), int(row["horizon_minutes"])): row
        for row in labels
        if not row["incomplete"]
    }
    eligible = [row for row in events if row["btc_mom_direction"] != "NO_BIAS"]
    output: dict[str, Any] = {
        "event_count": len(eligible),
        "agreement_rate": statistics.mean(
            row["direction"] == row["btc_mom_direction"] for row in eligible
        ),
        "horizons": {},
    }
    boot: dict[str, Any] = {"seed": SEED, "simulations": SIMULATIONS}
    for h in PRIMARY_HORIZONS:
        pairs = []
        for event in eligible:
            lab = label_map.get((str(event["event_id"]), h))
            if lab:
                raw = float(lab["raw_return_atr"])
                xab = raw if event["direction"] == "LONG" else -raw
                btc = raw if event["btc_mom_direction"] == "LONG" else -raw
                pairs.append(
                    {
                        "delta": xab - btc,
                        "xab": xab,
                        "btc": btc,
                        "week_cluster": event["week_cluster"],
                        "aligned": event["direction"] == event["btc_mom_direction"],
                        "incomplete": False,
                    }
                )
        output["horizons"][f"{h}m"] = {
            "count": len(pairs),
            "xab_median": statistics.median(row["xab"] for row in pairs),
            "btc_mom_median": statistics.median(row["btc"] for row in pairs),
            "paired_delta": statistics.median(row["delta"] for row in pairs),
            "aligned_xab_median": statistics.median(row["xab"] for row in pairs if row["aligned"]),
            "opposed_xab_median": statistics.median(
                row["xab"] for row in pairs if not row["aligned"]
            ),
        }
        boot[f"{h}m"] = _cluster_bootstrap_median(
            pairs, "delta", "week_cluster", seed=SEED, simulations=SIMULATIONS
        )
    deltas = [float(output["horizons"][f"{h}m"]["paired_delta"]) for h in PRIMARY_HORIZONS]
    output["stratified_permutation_delta"] = {
        f"{h}m": permutation["horizons"][f"{h}m"]["deterministic_point_delta"]
        for h in PRIMARY_HORIZONS
    }
    perm = [float(output["stratified_permutation_delta"][f"{h}m"]) for h in PRIMARY_HORIZONS]
    output["verdict"] = (
        "FALSIFIED"
        if all(v <= 0 for v in deltas)
        else "SUPPORTED"
        if all(v > 0 for v in deltas)
        and all(float(boot[f"{h}m"]["p05"]) >= -0.05 for h in PRIMARY_HORIZONS)
        and all(v > 0 for v in perm)
        else "INCONCLUSIVE_MECHANISM"
    )
    return output, boot


def _asof_feature(timestamp: int, features: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    times = [int(row["timestamp_ms"]) for row in features]
    index = bisect.bisect_right(times, timestamp) - 1
    return features[index] if index >= 0 else None


def _attach_opportunities(
    rows: Sequence[dict[str, Any]],
    features: Sequence[dict[str, Any]],
    controls: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        feature = _asof_feature(int(row["timestamp_ms"]), features)
        reference = controls[int(row["timestamp_ms"])]
        direction = (
            str(feature["direction"])
            if feature and feature["feature_status"] == "EXTREME"
            else "NO_BIAS"
        )
        output.append(
            {
                **row,
                "event_id": row["opportunity_id"],
                "funding_direction": direction,
                "direction": direction,
                "year": reference["year"],
                "atr_decile": reference["atr_decile"],
                "bar_index": reference["bar_index"],
                "btc_mom_bucket": feature["btc_mom_bucket"] if feature else "UNAVAILABLE",
                "split": "LATE" if int(row["timestamp_ms"]) >= LATE_START_MS else "EARLY",
                "day_cluster": datetime.fromtimestamp(
                    int(row["timestamp_ms"]) / 1000, UTC
                ).strftime("%Y-%m-%d"),
            }
        )
    return output


def _match_controls(
    candidates: Sequence[dict[str, Any]],
    pool: Sequence[dict[str, Any]],
    features: Sequence[dict[str, Any]],
    excluded: set[int],
) -> list[dict[str, Any]]:
    annotated = []
    for control in pool:
        if int(control["timestamp_ms"]) in excluded:
            continue
        feature = _asof_feature(int(control["timestamp_ms"]), features)
        if not feature or feature["feature_status"] != "EXTREME":
            continue
        annotated.append(
            {
                **control,
                "funding_direction": feature["direction"],
                "direction": feature["direction"],
                "btc_mom_bucket": feature["btc_mom_bucket"],
            }
        )
    output = []
    for candidate in candidates:
        eligible = [
            row
            for row in annotated
            if row["year"] == candidate["year"]
            and row["atr_decile"] == candidate["atr_decile"]
            and row["direction"] == candidate["direction"]
            and row["btc_mom_bucket"] == candidate["btc_mom_bucket"]
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


def composition_audit(features: Sequence[dict[str, Any]]) -> dict[str, Any]:
    extreme = [row for row in features if row["feature_status"] == "EXTREME"]
    signs = {
        symbol: [
            1 if float(row[f"{symbol}_r4h"]) > 0 else -1 if float(row[f"{symbol}_r4h"]) < 0 else 0
            for row in extreme
        ]
        for symbol in BASKET
    }
    final = [1 if row["direction"] == "LONG" else -1 for row in extreme]
    member = {
        symbol: statistics.mean(a == b for a, b in zip(values, final, strict=True))
        for symbol, values in signs.items()
    }
    leave = {}
    for removed in BASKET:
        directions = []
        for i in range(len(extreme)):
            values = [signs[s][i] for s in BASKET if s != removed]
            directions.append(
                1
                if sum(v > 0 for v in values) >= 4
                else -1
                if sum(v < 0 for v in values) >= 4
                else 0
            )
        leave[removed] = {
            "direction_agreement_rate": statistics.mean(
                value == final[i] for i, value in enumerate(directions)
            ),
            "extreme_event_count": sum(value != 0 for value in directions),
            "event_count_change": sum(value != 0 for value in directions) - len(extreme),
        }
    matrix = {
        left: {right: statistics.correlation(signs[left], signs[right]) for right in BASKET}
        for left in BASKET
    }
    sensitive = (
        max(member.values()) > 0.9
        or min(block["direction_agreement_rate"] for block in leave.values()) < 0.7
    )
    return {
        "diagnostic_only": True,
        "member_sign_agreement": member,
        "leave_one_out": leave,
        "pair_sign_correlation": matrix,
        "classification": "one-asset-sensitive representation"
        if sensitive
        else "highly redundant breadth representation"
        if statistics.mean(abs(matrix[a][b]) for a in BASKET for b in BASKET if a != b) > 0.75
        else "diversified breadth representation",
    }


def run_v039(
    candles: Sequence[Candle], basket: dict[str, list[dict[str, Any]]], config: AppConfig
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
        raise ValueError("v0.3.9 requires disabled execution")
    if candles[-1].close_time_ms >= DEV_END_MS:
        raise ValueError("holdout firewall")
    hourly = resample(candles, "1h")
    features = build_hourly_features(basket, hourly, frozen)
    onsets, members = build_breadth_episodes(features)
    series = IndexedOneMinuteSeries(candles)
    labels = build_labels(onsets, series)
    summary = _summary(onsets, labels)
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
            for h in HORIZONS
        },
    }
    permutation = _permutation_analysis(
        onsets,
        labels,
        stratum_fields=("year", "atr_decile", "btc_mom_bucket"),
        seed=SEED,
        simulations=SIMULATIONS,
    )
    h26 = h26_verdict(summary, bootstrap, permutation)
    h27, h27boot = _h27(onsets, labels, permutation)
    replay = run_v033_geometry_audit(
        candles, frozen, (), capture_trend_controls=True, capture_breakout_qualification=True
    )
    controls = list(replay["trend_control_rows"])
    cmap = {int(row["timestamp_ms"]): row for row in controls}
    union = opportunity_union(
        list(replay["breakout_qualification_rows"]), list(replay["tp_geometry_rows"])
    )
    attached = _attach_opportunities(union, features, cmap)
    candidates = [row for row in attached if row["direction"] != "NO_BIAS"]
    matches = _match_controls(
        candidates, controls, features, {int(row["timestamp_ms"]) for row in union}
    )
    h28, match_table = _interaction_analysis(
        candidates, matches, series, seed=SEED, simulations=SIMULATIONS
    )
    h28["verdict"] = interaction_verdict(h28)
    h28["union_count"] = len(union)
    h28["extreme_coverage_pct"] = 100 * len(candidates) / len(union)
    h28["by_setup"] = {
        tag: {
            f"{h}m_signed_median": statistics.median(
                float(_direction_label(row, series, h)["signed_return_atr"])
                for row in candidates
                if row["setup_tag"] == tag and not _direction_label(row, series, h)["incomplete"]
            )
            if any(row["setup_tag"] == tag for row in candidates)
            else None
            for h in PRIMARY_HORIZONS
        }
        for tag in ("BR", "TP", "BR+TP")
    }
    movement, movementboot = _movement_analysis(
        candidates, matches, series, seed=SEED, simulations=SIMULATIONS
    )
    if h26 == "SUPPORTED" and h27["verdict"] == "SUPPORTED" and h28["verdict"] != "FALSIFIED":
        rec = "RECOMMEND_CROSS_ASSET_DIRECTION_PLUS_OPPORTUNITY_PROTOTYPE"
    elif h26 == "SUPPORTED" and h27["verdict"] != "FALSIFIED":
        rec = "RECOMMEND_CROSS_ASSET_DIRECTION_FOLLOWUP"
    elif (
        h26.startswith("INCONCLUSIVE")
        and h28["verdict"] == "SUPPORTED"
        and h27["verdict"] != "FALSIFIED"
    ):
        rec = "RECOMMEND_OPPORTUNITY_CONDITIONED_CROSS_ASSET_FOLLOWUP"
    else:
        rec = "STOP_CROSS_ASSET_BREADTH_MOVE_TO_NEW_DATA_FAMILY"
    return {
        "scope": {
            "development_only": True,
            "holdout_accessed": False,
            "candidate_freeze": False,
            "execution_mode": frozen.execution.mode,
        },
        "breadth_hourly_features": features,
        "breadth_episode_onsets": onsets,
        "breadth_episode_members": members,
        "breadth_episode_summary": {
            **summary,
            "length_hours": {
                "p25": _percentile([float(row["episode_length_hours"]) for row in onsets], 0.25),
                "median": _percentile([float(row["episode_length_hours"]) for row in onsets], 0.5),
                "p75": _percentile([float(row["episode_length_hours"]) for row in onsets], 0.75),
                "max": max(row["episode_length_hours"] for row in onsets),
            },
            "extreme_hourly_decisions": len(members),
        },
        "h26_directionality": {**summary, "verdict": h26},
        "h26_bootstrap": bootstrap,
        "h26_permutation": permutation,
        "h27_btc_momentum_incremental": h27,
        "h27_bootstrap": h27boot,
        "opportunity_xab_events": attached,
        "opportunity_matched_controls": match_table,
        "h28_opportunity_directionality": h28,
        "h28_bootstrap": h28["bootstrap"],
        "movement_smoke": {**movement, "bootstrap": movementboot},
        "breadth_composition_audit": composition_audit(features),
        "by_year_direction": {
            str(y): {
                f"{h}m": statistics.median(
                    float(row["signed_return_atr"])
                    for row in labels
                    if row["year"] == y and row["horizon_minutes"] == h and not row["incomplete"]
                )
                for h in PRIMARY_HORIZONS
            }
            for y in sorted({row["year"] for row in labels})
        },
        "hypothesis_verdicts": {"H26": h26, "H27": h27["verdict"], "H28": h28["verdict"]},
        "recommendation": rec,
        "overall_status": "CROSS_ASSET_QUALIFICATION_COMPLETE",
        "performance": {
            "total_runtime_seconds": time.perf_counter() - started,
            "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "replay": replay["performance"],
        },
    }


def write_v039_artifacts(
    output: str | Path,
    result: dict[str, Any],
    config: AppConfig,
    protocol: str | Path,
    btc_manifest: str | Path,
    basket_manifest: str | Path,
) -> Path:
    target = Path(output)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError("immutable v0.3.9 run exists")
    target.mkdir(parents=True, exist_ok=True)
    protocol_path = Path(protocol)
    basket_path = Path(basket_manifest)
    btc_path = Path(btc_manifest)
    shutil.copyfile(protocol_path, target / "protocol.json")
    (target / "protocol.sha256").write_text(_sha256(protocol_path) + "\n")
    shutil.copyfile(basket_path, target / "basket_manifest.json")
    manifest = json.loads(basket_path.read_text())
    (target / "per_symbol_data_audit.json").write_text(
        json.dumps(manifest["symbols"], indent=2, sort_keys=True) + "\n"
    )
    pa, pq = importlib.import_module("pyarrow"), importlib.import_module("pyarrow.parquet")
    for key in (
        "breadth_hourly_features",
        "breadth_episode_onsets",
        "opportunity_xab_events",
        "opportunity_matched_controls",
    ):
        pq.write_table(pa.Table.from_pylist(result[key]), target / f"{key}.parquet")
    names = (
        "breadth_episode_summary",
        "h26_directionality",
        "h26_bootstrap",
        "h26_permutation",
        "h27_btc_momentum_incremental",
        "h27_bootstrap",
        "h28_opportunity_directionality",
        "h28_bootstrap",
        "breadth_composition_audit",
        "by_year_direction",
    )
    for name in names:
        (target / f"{name}.json").write_text(
            json.dumps(result[name], indent=2, sort_keys=True) + "\n"
        )
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "UNKNOWN"
    summary = {
        key: value
        for key, value in result.items()
        if key
        not in set(names)
        | {
            "breadth_hourly_features",
            "breadth_episode_onsets",
            "breadth_episode_members",
            "opportunity_xab_events",
            "opportunity_matched_controls",
        }
    }
    summary["provenance"] = {
        "git_sha": sha,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "config_hash": config.config_hash,
        "btc_manifest_sha256": _sha256(btc_path),
        "basket_manifest_sha256": _sha256(basket_path),
        "cross_asset_checksums": {
            s: block["parquet_sha256"] for s, block in manifest["symbols"].items()
        },
        "protocol_sha256": _sha256(protocol_path),
        "seed": SEED,
        "simulations": SIMULATIONS,
        "python_version": platform.python_version(),
    }
    (target / "experiment_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return target
