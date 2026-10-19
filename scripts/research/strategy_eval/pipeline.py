"""Manual P1-A offline research CLI. Synthetic PnL is computed, never a fill claim.

Run ``python3 -m scripts.research.strategy_eval.pipeline demo --output-dir /tmp/new``.
``inspect-historical`` never computes outcomes. ``evaluate-historical`` consumes
only a hash/window-bound, explicitly allowlisted normalized EXPOSED_DEV panel.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from zipfile import BadZipFile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

import numpy as np

from . import DAY, HORIZONS, LABELS, PLAN, SEED, TASK
from . import clocked_dataset as data
from .costs import (BASELINE, MAKER_SENSITIVITY, SCENARIOS, US, CostAssumptions, Outcome,
                    Settlement, economics, finite, policy_action)

OUTPUT_FILES = ("run_config.json", "source_inventory.json", "origins.jsonl", "trades.csv",
                "metrics.json", "test_receipt.json")
MIN_TRAIN = 30


@dataclass(frozen=True)
class RidgeModel:
    center: float
    mean: np.ndarray
    scale: np.ndarray
    beta: np.ndarray
    full: bool
    lam: float
    train_count: int
    train_times_sha256: str

    def report(self) -> dict[str, Any]:
        return {
            "lambda": self.lam, "train_count": self.train_count,
            "train_times_sha256": self.train_times_sha256,
            "score_center_training_only": self.center,
            "means_training_only": self.mean.tolist(), "scales_training_only": self.scale.tolist(),
            "beta_standardized": self.beta.tolist(),
            "score_coefficient": float(self.beta[-1] / self.scale[-1]) if self.full else None,
        }


def outcome(row: dict[str, Any], horizon: int) -> Outcome | None:
    return row.get("outcomes", {}).get(str(horizon))


def label_return(row: dict[str, Any], horizon: int) -> float | None:
    value = outcome(row, horizon)
    if (value is None or type(value.entry_t) is not int or type(value.exit_t) is not int
            or value.entry_t != row["t"] + 60
            or value.exit_t != row["t"] + 60 + horizon * 3600):
        return None
    return value.simple_return


def purge(rows: list[dict[str, Any]], start: int, boundary: int) -> list[dict[str, Any]]:
    """Identical X/XZ population; worst-horizon label end strictly before embargo."""
    return [r for r in rows if start <= r["t"] < boundary
            and r["t"] + 60 + 24 * 3600 < boundary - 3600
            and data.ready(r)[1] and all(finite(label_return(r, h)) for h in HORIZONS)]


def design(rows: list[dict[str, Any]], center: float, full: bool) -> np.ndarray:
    x = np.asarray([r["x"] for r in rows], dtype=float).reshape(len(rows), 10)
    if full:
        score = [(r["z"][1] - center) * max(r["z"][0], 0.0) for r in rows]
        x = np.column_stack((x, score))
    return x


def fit(train: list[dict[str, Any]], horizon: int, lam: float, full: bool) -> RidgeModel:
    data.require(horizon in HORIZONS and lam in PLAN["ridge_lambdas"], "MODEL_NOT_FROZEN")
    data.require(len(train) >= MIN_TRAIN and all(data.ready(r)[1] for r in train), "INSUFFICIENT_HISTORY")
    center = float(np.mean([r["z"][1] for r in train]))
    raw = design(train, center, full)
    mean, scale = raw.mean(axis=0), raw.std(axis=0)
    scale[scale == 0] = 1.0
    a = np.column_stack((np.ones(len(raw)), (raw - mean) / scale))
    y = np.asarray([label_return(r, horizon) for r in train], dtype=float)
    data.require(bool(np.isfinite(a).all() and np.isfinite(y).all()), "NONFINITE_TRAINING_DATA")
    penalty = np.eye(a.shape[1]) * lam
    penalty[0, 0] = 0
    matrix, rhs = a.T @ a + penalty, a.T @ y
    beta = np.linalg.solve(matrix, rhs)
    if full and beta[-1] > 0:
        # Exact single-coordinate inequality optimum, refitting the free controls.
        beta[:-1] = np.linalg.solve(matrix[:-1, :-1], rhs[:-1])
        beta[-1] = 0.0
    time_digest = hashlib.sha256(
        ",".join(str(r["t"]) for r in train).encode("ascii")).hexdigest()
    return RidgeModel(center, mean, scale, beta, full, lam, len(train), time_digest)


def predict(model: RidgeModel, rows: list[dict[str, Any]]) -> np.ndarray:
    if not rows:
        return np.asarray([], dtype=float)
    a = design(rows, model.center, model.full)
    return np.column_stack((np.ones(len(a)), (a - model.mean) / model.scale)) @ model.beta


def inner_splits(rows: list[dict[str, Any]], start: int,
                 dev_end: int) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    splits = []
    for k in (3, 2, 1):
        v0 = dev_end - k * 7 * DAY
        v1 = v0 + 7 * DAY
        train = purge(rows, start, v0)
        val = [r for r in rows if v0 <= r["t"] < v1
               and r["t"] + 60 + 24 * 3600 < dev_end and data.ready(r)[1]
               and all(finite(label_return(r, h)) for h in HORIZONS)]
        data.require(len(train) >= MIN_TRAIN and bool(val), "INSUFFICIENT_HISTORY")
        splits.append((train, val))
    return splits


def tune(rows: list[dict[str, Any]], start: int, dev_end: int,
         horizon: int, full: bool) -> tuple[float, list[dict[str, Any]]]:
    splits = inner_splits(rows, start, dev_end)
    scores = []
    for lam in PLAN["ridge_lambdas"]:
        errors = []
        for train, val in splits:
            p = predict(fit(train, horizon, lam, full), val)
            errors.extend((p - np.asarray([label_return(r, horizon) for r in val])) ** 2)
        scores.append({"lambda": lam, "inner_mse": float(np.mean(errors)), "rows": len(errors)})
    selected = min(scores, key=lambda s: (s["inner_mse"], s["lambda"]))["lambda"]
    return selected, scores


def claimed_clock(row: dict[str, Any]) -> dict[str, Any]:
    """Reuse R3 only for synthetic caller claims; native lag is checked separately."""
    from scripts.research.r11_d2 import prospective_causal_clock as clock

    ns = clock.NS
    t = row["t"]
    xok, zok = data.ready(row)
    calibration = clock.ClockCalibration("P1_SYNTHETIC_BOOT", 0, (t - 2) * ns, 0, 0)
    contract = clock.PredeclaredSourceSet(
        "P1_SYNTHETIC_FIXED_X_Z", t * ns,
        (clock.SourceRequirement("X", "DERIVED"), clock.SourceRequirement("Z", "DERIVED")))
    policies = {
        "X": clock.SourcePolicy("X", "DERIVED", "synthetic-X", "synthetic-epoch", 0, 2 * ns),
        # This is the committed stock projection, not an R3 live OI feed. R3's
        # live OI ten-second sample policy cannot admit a five-minute archive.
        # Keep that policy intact; the separate native-stock guard governs Z.
        "Z": clock.SourcePolicy("Z", "DERIVED", "synthetic-Z", "synthetic-epoch", 0, 10 * ns,
                                sample_max_age_ns=661 * ns),
    }
    records = []
    for name, permitted in (("X", xok), ("Z", zok)):
        if permitted:
            records.append(clock.SourceEvidence(
                name, calibration.boot_id, policies[name].connection_id, "synthetic-epoch",
                *(int(v * ns) for v in (0.4, 0.5, 0.6, 0.65, 0.7, 0.8)),
                role="COMPLETED_INTERVAL" if name == "X" else "POINT",
                economic_end_upper_utc_ns=row["x_end_us"] * 1000 if name == "X" else None,
                sample_lower_utc_ns=row["z_t"] * ns if name == "Z" else None,
                sample_upper_utc_ns=row["z_t"] * ns if name == "Z" else None))
    result = clock.evaluate_fixed_origin(
        calibration, records, policies, predeclared_sources=contract,
        fixed_origin_utc_ns=t * ns, fixed_decision_mono_ns=2 * ns + ns // 1000,
        feature_ready_mono_ns=ns, feature_admission_mono_ns=ns + ns // 5)
    return {**asdict(result), "evidence": "DEV_SYNTHETIC_CLAIMED_ONLY", "receiver_pit": "PIT_UNKNOWN",
            "R3_sources": "DERIVED_FEATURE_PROJECTIONS_NOT_LIVE_OI_ADMISSION",
            "native_stock_clock": "SEPARATE_C_MINUS_10M_TO_C_MINUS_5M_GUARD"}


def synthetic_dataset() -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Generate native minute prices first, then features and realized endpoint PnL."""
    start = 1704067200  # 2024-01-01 UTC; deliberately separate from historical July.
    rng = np.random.default_rng(SEED)
    n = 85 * 1440 + 1
    hours = np.arange(n, dtype=float) / 60
    drift = -0.004 * np.sin(hours / 11) + 0.002 * np.sin(hours / 79)
    increments = drift / 60 + rng.normal(0, 0.00010, n)
    prices = 42000 * np.exp(np.cumsum(increments))
    basis = 0.0004 * np.sin(hours / 17) + rng.normal(0, 0.000015, n)
    spot_prices = prices / np.exp(basis)
    volumes = 10 + 3 * np.sin(hours / 9) + rng.uniform(0, 2, n)
    imbalance = 0.5 + 0.2 * np.sin(hours / 11)
    stocks = {}
    for i in range(0, 84 * 1440, 5):
        hour = i / 60
        t = start + i * 60
        if i in (45 * 1440 + 235, 45 * 1440 + 230):
            continue
        oi = 100000 * math.exp(0.07 * math.sin(hour / 31))
        ratio = math.exp(0.8 * math.sin(hour / 11))
        if i == 46 * 1440 + 715:
            ratio = None
        stocks[t] = data.Stock(t, oi, ratio, native_timestamp=t * 1000,
                               native_unit="SYNTHETIC_MS")
    def bars(spot: bool) -> Iterable[data.Bar]:
        values = spot_prices if spot else prices
        for i in range(84 * 1440):
            if i == 44 * 1440 + 180:
                continue
            opening, closing = float(values[i]), float(values[i + 1])
            volume = float(volumes[i])
            quote = volume * closing
            t = (start + i * 60) * US
            yield data.Bar(t, t + 60 * US - 1000, opening,
                           max(opening, closing) * 1.0002, min(opening, closing) * 0.9998,
                           closing, volume, quote, quote * float(imbalance[i]),
                           market="spot" if spot else "futures_um")
    rows = data.feature_grid(bars(False), bars(True), stocks, start, start + 84 * DAY)
    calendar = tuple((start + i * 8 * 3600) * US for i in range(85 * 3 + 1))
    for row in rows:
        row["clock_verdict"] = claimed_clock(row)
        entry = row["t"] + 60
        i = (entry - start) // 60
        row["outcomes"] = {}
        for h in HORIZONS:
            exit_t = entry + h * 3600
            settlements = tuple(
                Settlement(t, 0.00008 * math.cos((t // US - start) / 3600 / 37),
                           float(prices[(t // US - start) // 60]) * 1.0001)
                for t in calendar if entry * US < t <= exit_t * US)
            row["outcomes"][str(h)] = Outcome(
                entry, exit_t, float(prices[i]), float(prices[i + h * 60]), settlements,
                tuple(s.t_us for s in settlements), (entry * US, exit_t * US))
    inventory = {
        "mode": "DEV_SYNTHETIC_ONLY", "labels": list(LABELS), "seed": SEED,
        "historical_rows_read": 0, "market_requests": 0, "ticks_l2_opened": 0,
        "minute_price_rows": n, "feature_origins": len(rows),
        "sources": [{"source": name, "native_unit": "SYNTHETIC_MINUTE_OPEN_UTC_SECONDS",
                     "sha256": hashlib.sha256(array.astype("<f8").tobytes()).hexdigest()}
                    for name, array in (("USDM_PRICE", prices), ("SPOT_PRICE", spot_prices),
                                        ("BASE_VOLUME", volumes))],
        "stock_projection": "SYNTHETIC_BASE_OI_AND_TOP_POSITION_RATIO_ONLY",
        "fixture_missingness": "ONE_MISSING_MINUTE_TWO_MISSING_STOCK_SAMPLES_ONE_INVALID_RATIO",
        "price_generation": "SEEDED_MINUTE_PROCESS_THEN_REALIZED_ENTRY_EXIT_AND_NATIVE_FUNDING",
    }
    return rows, start, inventory


def _decision(row: dict[str, Any], h: int, arm: str, assumptions: CostAssumptions,
              prediction: float | None, reason: str, fold: int | None) -> dict[str, Any]:
    permitted = data.ready(row)[arm == "XZ"]
    action = policy_action(prediction, h, assumptions) if permitted else 0
    result = economics(outcome(row, h), action, h, assumptions)
    if not action:
        if not permitted:
            reason = row.get("x_reason", "MISSING_X") if not data.ready(row)[0] else row.get("z_reason", "MISSING_Z")
            if reason == "READY":
                reason = "MISSING_X" if not data.ready(row)[0] else "MISSING_OR_INVALID_Z"
        elif prediction is not None:
            reason = "NO_FORECAST_EDGE"
        result["reason"] = reason
    result.update(t=row["t"], h=h, arm=arm, scenario=assumptions.name, fold=fold,
                  prediction=prediction, x_eligible=data.ready(row)[0],
                  z_eligible=data.ready(row)[1], raw_z_present=row.get("raw_z_present", False),
                  entry_t=row["t"] + 60, exit_t=row["t"] + 60 + h * 3600)
    return result


def capital_overlap(points: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    events = []
    for point in points:
        if point["action"]:
            # Exits precede entries at the same instant. Unresolved trades still occupy capital.
            events.extend(((point["entry_t"], 1), (point["exit_t"], -1)))
    active = maximum = 0
    for _, change in sorted(events):
        active += change
        maximum = max(maximum, active)
    data.require(maximum <= horizon, "CAPITAL_OVERLAP_EXCEEDS_FIXED_SLEEVES")
    return {"max_simultaneous_positions": maximum, "max_allocated_capital": maximum / horizon,
            "sleeve_capital": 1 / horizon, "leverage": 1, "reinvestment": False}


def cell_metrics(points: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    acted = [p for p in points if p["action"]]
    resolved = [p for p in acted if p["status"] == "RESOLVED"]
    unresolved = len(acted) - len(resolved)
    net = [p["net_return"] for p in resolved]
    utilities = [p["sleeve_pnl"] for p in points]
    common = [p["sleeve_pnl"] for p in points if p["z_eligible"]]
    gains, losses = [v for v in net if v > 0], [v for v in net if v < 0]
    total = None if unresolved else sum(utilities)
    mean = lambda a: float(np.mean(a)) if a else None
    return {
        "scheduled": len(points), "acted_on": len(acted), "resolved_acted_on": len(resolved),
        "unresolved_acted_on": unresolved, "no_action": len(points) - len(acted),
        "raw_Z_present": sum(p["raw_z_present"] for p in points),
        "X_eligible": sum(p["x_eligible"] for p in points),
        "feature_eligible_Z": sum(p["z_eligible"] for p in points),
        "net_win_rate": sum(v > 0 for v in net) / len(net) if net else None,
        "net_win_rate_denominator": len(net),
        "gross_win_rate": mean([float(p["gross_return"] > 0) for p in resolved]),
        "mean_gain": mean(gains), "mean_loss": mean(losses),
        "mean_net_trade_return": mean(net), "median_net_trade_return": float(np.median(net)) if net else None,
        "mean_net_utility_per_scheduled_origin": total / len(points) if total is not None and points else None,
        "aggregate_matured_sleeve_pnl": total,
        "resolved_only_sleeve_pnl_subtotal": sum(p["sleeve_pnl"] for p in resolved),
        "common_Z_mean_utility": mean(common) if common and all(v is not None for v in common) else None,
        "common_Z_denominator": len(common),
        "net_trade_p05": float(np.quantile(net, 0.05)) if net else None,
        "net_trade_expected_shortfall_05": mean(sorted(net)[:max(1, math.ceil(0.05 * len(net)))]) if net else None,
        "worst_net_trade_return": min(net) if net else None,
        "turnover_resolved_subtotal": sum(p["turnover"] for p in resolved),
        "turnover": None if unresolved else sum(p["turnover"] for p in resolved),
        "funding_drag_resolved_sleeve_subtotal": sum(p["funding_debit"] / horizon for p in resolved),
        "itemized_cost_resolved_sleeve_subtotals": {
            k: sum(p[k] / horizon for p in resolved) for k in (
                "entry_fee", "exit_fee", "entry_spread", "exit_spread", "entry_slippage", "exit_slippage")},
        "mean_break_even_cost_bp": mean([p["break_even_cost_bp"] for p in resolved]),
        "reason_counts": dict(Counter(p["reason"] for p in points)),
        "side_counts": {name: sum(p["action"] == side for p in points)
                        for name, side in (("LONG", 1), ("SHORT", -1), ("NO_ACTION", 0))},
        "capital": capital_overlap(points, horizon),
        "path_drawdown": None, "path_drawdown_status": "REQUIRES_CHRONOLOGICAL_MARK_TO_MARKET",
    }


def missingness(rows: list[dict[str, Any]], *, predictions: dict[int, float] | None = None) -> dict[str, Any]:
    groups: dict[str, dict[str, Counter]] = {k: defaultdict(Counter) for k in ("calendar_utc_day", "X_only_regime", "X_only_forecast_side")}
    for row in rows:
        xok, zok = data.ready(row)
        day = row["t"] // DAY
        regime = "X_UNAVAILABLE" if not xok else "RETURN_24H_POSITIVE" if row["x"][2] > 0 else "RETURN_24H_NONPOSITIVE"
        p = None if predictions is None else predictions.get(row["t"])
        side = "UNKNOWN" if p is None else "LONG" if p > 0 else "SHORT" if p < 0 else "FLAT"
        for field, key in (("calendar_utc_day", str(day)), ("X_only_regime", regime), ("X_only_forecast_side", side)):
            groups[field][key].update(scheduled=1, X_eligible=int(xok),
                                      raw_Z_present=int(row.get("raw_z_present", False)),
                                      feature_eligible_Z=int(zok), Z_unavailable_with_X=int(xok and not zok))
    return {field: {key: dict(value) for key, value in group.items()} for field, group in groups.items()}


def training_mde(train: list[dict[str, Any]], models: dict[str, RidgeModel], h: int,
                 start: int) -> dict[str, Any]:
    predictions = {arm: predict(model, train) for arm, model in models.items()}
    blocks = defaultdict(list)
    for i, row in enumerate(train):
        u = {arm: economics(outcome(row, h), policy_action(float(predictions[arm][i]), h), h)["sleeve_pnl"]
             for arm in ("X", "XZ")}
        if all(v is not None for v in u.values()):
            blocks[(row["t"] - start) // (7 * DAY)].append(u["XZ"] - u["X"])
    means = [float(np.mean(v)) for v in blocks.values() if len(v) == 7 * 24]
    variance = float(np.var(means, ddof=1)) if len(means) >= 2 else None
    z = NormalDist().inv_cdf(1 - PLAN["alpha"] / (2 * 8)) + NormalDist().inv_cdf(0.8)
    return {"status": "TRAINING_BLOCK_VARIANCE_ONLY_NOT_CALIBRATED_POWER", "training_week_blocks": len(means),
            "paired_training_block_variance": variance,
            "approximate_MDE_sleeve_mean_6_validation_blocks": None if variance is None else z * math.sqrt(variance / 6)}


def paired_inference(cells: list[dict[str, Any]], reps: int = 9999) -> list[dict[str, Any]]:
    """Paired day-aligned circular seven-day blocks; four B slots remain p=1."""
    rng = np.random.default_rng(SEED)
    results = []
    for h in HORIZONS:
        arms = {arm: [p for c in cells if c["h"] == h and c["arm"] == arm
                      and c["scenario"] == BASELINE.name for p in c["points"]] for arm in ("X", "XZ")}
        x, z = arms["X"], arms["XZ"]
        data.require([p["t"] for p in x] == [p["t"] for p in z], "UNPAIRED_ORIGINS")
        n = len(x)
        answer = {"mechanism": "A_POSITION_OVERHANG", "h": h, "primary": h == 8,
                  "p": 1.0, "week_blocks": n // 168, "power_sufficient": n // 168 >= 12,
                  "status": "INSUFFICIENT_SUPPORT", "all_origins": None, "common_Z": None}
        if not n or n % 24 or any(p["sleeve_pnl"] is None for p in x + z):
            answer["status"] = "UTILITY_UNRESOLVED" if n else "INSUFFICIENT_HISTORY"
            results.append(answer)
            continue
        data.require(all(b["t"] - a["t"] == 3600 for a, b in zip(x, x[1:])), "BOOTSTRAP_GRID_GAP")
        delta = np.asarray([b["sleeve_pnl"] - a["sleeve_pnl"] for a, b in zip(x, z)])
        ndays = n // 24
        starts = rng.integers(0, ndays, size=(reps, math.ceil(ndays / 7)))
        indices = ((starts[:, :, None] + np.arange(7)) % ndays).reshape(reps, -1)[:, :ndays]
        claims = []
        for weights in (np.ones(n), np.asarray([p["z_eligible"] for p in z], dtype=float)):
            if weights.sum() == 0:
                claims.append({"status": "NO_COMMON_Z", "p": 1.0})
                continue
            daily_sum = (delta * weights).reshape(ndays, 24).sum(axis=1)
            daily_count = weights.reshape(ndays, 24).sum(axis=1)
            denom = daily_count[indices].sum(axis=1)
            boots = daily_sum[indices].sum(axis=1)[denom > 0] / denom[denom > 0]
            observed = float(np.sum(delta * weights) / weights.sum())
            if len(boots) < reps * 0.99:
                claims.append({"status": "SPARSE_BLOCK_SUPPORT", "p": 1.0})
                continue
            tail = PLAN["alpha"] / (2 * 8)
            claims.append({"mean_delta": observed, "denominator": int(weights.sum()),
                           "bonferroni_simultaneous_CI": np.quantile(boots, [tail, 1 - tail]).tolist(),
                           "p": float((1 + np.sum(np.abs(boots - observed) >= abs(observed))) / (len(boots) + 1))})
        answer.update(all_origins=claims[0], common_Z=claims[1], p=max(c["p"] for c in claims),
                      draws=reps, seed=SEED, block_days=7)
        results.append(answer)
    results.extend({"mechanism": "B_RESERVED_NOT_ENABLED", "h": h, "p": 1.0,
                    "status": "RESERVED_NOT_ENABLED"} for h in HORIZONS)
    running = 0.0
    for rank, index in enumerate(sorted(range(8), key=lambda i: results[i]["p"])):
        running = max(running, min(1.0, (8 - rank) * results[index]["p"]))
        results[index]["holm_p_8_slots"] = running
    return results


def paired_diagnostics(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    """Separate stock-value increments from abstention on missing stock records."""
    reports = []
    for h in HORIZONS:
        models = {arm: [m for f in evaluation["folds"] for m in f["models"]
                        if m["h"] == h and m["arm"] == arm] for arm in ("X", "XZ")}
        for assumptions in SCENARIOS:
            points = {arm: [p for c in evaluation["cells"] if c["h"] == h
                            and c["arm"] == arm and c["scenario"] == assumptions.name
                            for p in c["points"]] for arm in ("X", "XZ")}
            x, z = points["X"], points["XZ"]
            data.require([p["t"] for p in x] == [p["t"] for p in z], "UNPAIRED_ORIGINS")
            pairs = list(zip(x, z))
            common = [(a, b) for a, b in pairs if b["z_eligible"]]
            def delta(population: list[tuple[dict[str, Any], dict[str, Any]]]) -> float | None:
                if not population or any(a["sleeve_pnl"] is None or b["sleeve_pnl"] is None for a, b in population):
                    return None
                return sum(b["sleeve_pnl"] - a["sleeve_pnl"] for a, b in population) / len(population)
            ablated = [a["sleeve_pnl"] if b["z_eligible"] else 0.0 for a, b in pairs]
            ablation_mean = float(np.mean(ablated)) if ablated and all(v is not None for v in ablated) else None
            weighted_loss = {}
            for arm in ("X", "XZ"):
                denominator = sum(m["prediction_mse_denominator"] for m in models[arm])
                weighted_loss[arm] = sum(m["common_Z_prediction_mse"] * m["prediction_mse_denominator"]
                                         for m in models[arm] if m["common_Z_prediction_mse"] is not None) / denominator if denominator else None
            reasons = []
            if weighted_loss["X"] is None or weighted_loss["XZ"] is None or weighted_loss["XZ"] >= weighted_loss["X"]:
                reasons.append("CONDITIONAL_PREDICTION_LOSS_NOT_IMPROVED")
            if not models["XZ"] or all(m["score_coefficient"] == 0 for m in models["XZ"]):
                reasons.append("SCORE_CONSTRAINT_COLLAPSED_OR_NOT_FITTED")
            for name, population in (("ALL_ORIGINS", pairs), ("COMMON_Z", common)):
                value = delta(population)
                if value is None or value <= 0:
                    reasons.append("PAIRED_UTILITY_NOT_POSITIVE_" + name)
            reports.append({"h": h, "primary": h == 8, "scenario": assumptions.name,
                            "all_origins_denominator": len(pairs), "common_Z_denominator": len(common),
                            "all_origins_mean_delta": delta(pairs), "common_Z_mean_delta": delta(common),
                            "common_Z_prediction_loss": weighted_loss,
                            "score_coefficients_by_fold": [m["score_coefficient"] for m in models["XZ"]],
                            "missingness_only_X_abstention_diagnostic_mean": ablation_mean,
                            "missingness_diagnostic_is_claim_slot": False,
                            "frozen_edge_failure_reasons": reasons,
                            "support": "INSUFFICIENT_SUPPORT_FEWER_THAN_12_WEEK_BLOCKS",
                            "alpha": "NO_ALPHA_ESTABLISHED"})
    return reports


def evaluate(rows: list[dict[str, Any]], start: int) -> dict[str, Any]:
    data.validate_grid(rows, start)
    result = {"status": "INSUFFICIENT_HISTORY", "cells": [], "folds": [], "records": {},
              "scheduled_feature_origins": len(rows), "origins_dropped": 0}
    if len(rows) < 84 * 24:
        result["inference"] = paired_inference([])
        return result
    for day in PLAN["outer_development_days"]:
        end = start + day * DAY
        val = [r for r in rows if end <= r["t"] < end + 14 * DAY]
        train = purge(rows, start, end)
        fold = {"development_end_day": day, "validation_start": end,
                "validation_end": end + 14 * DAY, "scheduled": len(val),
                "training_rows": len(train), "training_max_label_end": max((r["t"] + 60 + DAY for r in train), default=None),
                "models": [], "missingness": missingness(val)}
        result["folds"].append(fold)
        if len(train) < MIN_TRAIN or len(val) != 14 * 24:
            fold["status"] = "INSUFFICIENT_HISTORY"
            continue
        try:
            inner_splits(rows, start, end)
        except ValueError as exc:
            if str(exc) != "INSUFFICIENT_HISTORY":
                raise
            fold["status"] = "INSUFFICIENT_HISTORY"
            continue
        fold["status"] = "EXPOSED_DEVELOPMENT_FOLD"
        for h in HORIZONS:
            models = {}
            for full in (False, True):
                arm = "XZ" if full else "X"
                lam, scores = tune(rows, start, end, h, full)
                model = fit(train, h, lam, full)
                models[arm] = model
                eligible = [r for r in val if data.ready(r)[full]]
                predictions = dict(zip((r["t"] for r in eligible), map(float, predict(model, eligible))))
                common = [r for r in val if data.ready(r)[1] and finite(label_return(r, h))]
                common_pred = predict(model, common)
                mse = float(np.mean((common_pred - np.asarray([label_return(r, h) for r in common])) ** 2)) if common else None
                report = {"h": h, "arm": arm, **model.report(), "inner_scores": scores,
                          "common_Z_prediction_mse": mse, "prediction_mse_denominator": len(common),
                          "missingness": missingness(val, predictions=predictions if arm == "X" else None)}
                fold["models"].append(report)
                for assumptions in SCENARIOS:
                    points = [_decision(r, h, arm, assumptions, predictions.get(r["t"]),
                                        "INSUFFICIENT_HISTORY", day) for r in val]
                    cell = {"fold_day": day, "h": h, "arm": arm, "scenario": assumptions.name,
                            "points": points, **cell_metrics(points, h)}
                    result["cells"].append(cell)
                    for point in points:
                        result["records"][(point["t"], h, arm, assumptions.name)] = point
            data.require(models["X"].train_times_sha256 == models["XZ"].train_times_sha256,
                         "UNPAIRED_TRAINING_ROWS")
            fold.setdefault("training_MDE", {})[str(h)] = training_mde(train, models, h, start)
    result["status"] = "EVALUATED_OFFLINE" if all(f.get("status") == "EXPOSED_DEVELOPMENT_FOLD" for f in result["folds"]) else "INSUFFICIENT_HISTORY"
    result["inference"] = paired_inference(result["cells"])
    return result


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _write_json(root: Path, name: str, value: Any) -> None:
    with (root / name).open("xb") as stream:
        stream.write(_json_bytes(value))


def _default_reason(row: dict[str, Any], evaluation: dict[str, Any], start: int) -> str:
    if evaluation["status"] == "INSPECTION_ONLY":
        return "HISTORICAL_FEATURE_COVERAGE_ONLY"
    if evaluation["status"] == "INSUFFICIENT_HISTORY":
        return "INSUFFICIENT_HISTORY"
    return "DEVELOPMENT_TRAINING_ORIGIN" if row["t"] < start + 42 * DAY else "INSUFFICIENT_HISTORY"


def coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"scheduled_feature_origins": len(rows), "scheduled_origin_horizon_rows": len(rows) * 4,
            "X_eligible": sum(data.ready(r)[0] for r in rows),
            "raw_Z_present": sum(r.get("raw_z_present", False) for r in rows),
            "feature_eligible_Z": sum(data.ready(r)[1] for r in rows),
            "X_reason_counts": dict(Counter(r["x_reason"] for r in rows)),
            "Z_reason_counts": dict(Counter(r["z_reason"] for r in rows)),
            "missingness": missingness(rows), "origins_dropped": 0}


TRADE_FIELDS = (
    "t", "h", "arm", "scenario", "fold", "action", "status", "reason", "prediction",
    "entry_t", "exit_t", "entry_price", "exit_price", "capital_sleeve", "base_quantity",
    "gross_return", "entry_fee", "exit_fee", "entry_spread", "exit_spread", "entry_slippage",
    "exit_slippage", "total_cost", "funding_debit", "net_return", "sleeve_pnl",
    "break_even_cost_bp", "turnover", "funding_settlements_json", "funding_calendar_json",
    "funding_coverage_us_json", "mode", "labels",
)


def write_reports(root: Path, rows: list[dict[str, Any]], start: int,
                  inventory: dict[str, Any], evaluation: dict[str, Any], mode: str,
                  *, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    config = {**PLAN, "mode": mode, "historical_outcomes_evaluated": bool(evaluation["records"]) and mode == "HISTORICAL_OFFLINE / PIT_UNKNOWN",
              "exposure_authorization": authorization,
              "outcome_gate": "EXPOSED_DEV_NOT_AUTHORIZED" if mode.startswith("HISTORICAL") and authorization is None else "SYNTHETIC_ONLY" if mode == "DEV_SYNTHETIC_ONLY" else "EXPLICIT_EXPOSED_DEV_ONLY",
              "cost_assumptions": [asdict(c) for c in SCENARIOS], "maker": MAKER_SENSITIVITY,
              "real_funds_writes": 0, "execution_count": 0}
    _write_json(root, "run_config.json", config)
    _write_json(root, "source_inventory.json", inventory)
    trade_count = 0
    origin_count = 0
    with ((root / "origins.jsonl").open("x", encoding="utf-8") as origins,
          (root / "trades.csv").open("x", encoding="utf-8", newline="") as trades):
        writer = csv.DictWriter(trades, fieldnames=TRADE_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            for h in HORIZONS:
                decisions = {"NO_ACTION": {
                    "action": 0, "reason": "ALWAYS_NO_ACTION_CASH", "gross_return": 0.0,
                    "net_return": 0.0, "sleeve_pnl": 0.0, "capital_allocated": 0.0,
                    "benchmark": "FIXED_CASH", "claim_slot": False,
                }}
                for arm in ("X", "XZ"):
                    decisions[arm] = {}
                    for assumptions in SCENARIOS:
                        point = evaluation["records"].get((row["t"], h, arm, assumptions.name))
                        if point is None:
                            point = _decision(row, h, arm, assumptions, None,
                                              _default_reason(row, evaluation, start), None)
                        decisions[arm][assumptions.name] = point
                        if point["action"]:
                            label = outcome(row, h)
                            item = {k: point.get(k) for k in TRADE_FIELDS}
                            item.update(entry_price=label.entry_price if label else None,
                                        exit_price=label.exit_price if label else None,
                                        base_quantity=1 / h / label.entry_price if label and finite(label.entry_price) and label.entry_price > 0 else None,
                                        funding_settlements_json=json.dumps([asdict(s) for s in label.settlements], sort_keys=True, allow_nan=False) if label else None,
                                        funding_calendar_json=json.dumps(label.expected_settlements_us) if label else None,
                                        funding_coverage_us_json=json.dumps(label.funding_coverage_us) if label else None,
                                        mode=mode, labels="|".join(LABELS))
                            writer.writerow(item)
                            trade_count += 1
                item = {k: v for k, v in row.items() if k != "outcomes"}
                item.update(h=h, mode=mode, labels=list(LABELS), decisions=decisions)
                origins.write(json.dumps(item, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n")
                origin_count += 1
    aggregates = []
    for h in HORIZONS:
        for arm in ("X", "XZ"):
            for assumptions in SCENARIOS:
                points = [p for c in evaluation["cells"] if c["h"] == h and c["arm"] == arm
                          and c["scenario"] == assumptions.name for p in c["points"]]
                if points:
                    aggregates.append({"h": h, "arm": arm, "scenario": assumptions.name,
                                       **cell_metrics(points, h)})
    metrics = {
        "task": TASK, "mode": mode, "labels": list(LABELS), "status": evaluation["status"],
        "alpha": "NO_ALPHA_ESTABLISHED", "confirmatory": False,
        "outcome_gate": config["outcome_gate"], "coverage": coverage(rows),
        "history_support": "INSUFFICIENT_HISTORY" if len(rows) < 84 * 24 else "84_DAY_GRID_PRESENT_NOT_INDEPENDENT_SUPPORT",
        "origin_horizon_rows": origin_count, "trades_csv_rows": trade_count,
        "validation_feature_origins": sum(f["scheduled"] for f in evaluation["folds"]),
        "outcomes_evaluated": len(evaluation["records"]),
        "cells": [{k: v for k, v in c.items() if k != "points"} for c in evaluation["cells"]],
        "validation_aggregates": aggregates, "paired_diagnostics": paired_diagnostics(evaluation),
        "always_no_action_baseline": [{
            "h": h, "scheduled": len(rows), "no_action": len(rows),
            "validation_scheduled": sum(f["scheduled"] for f in evaluation["folds"]),
            "acted_on": 0, "gross_return": 0.0, "net_return": 0.0,
            "aggregate_matured_sleeve_pnl": 0.0,
            "mean_net_utility_per_scheduled_origin": 0.0,
            "benchmark": "FIXED_CASH", "claim_slot": False,
        } for h in HORIZONS],
        "folds": evaluation["folds"], "inference": evaluation["inference"],
        "claim_slots": 8, "reserved_B_slots": 4, "primary_horizon_h": 8,
        "common_Z_and_all_origin_conjunction_required": True,
        "missingness_only_X_baseline": "DIAGNOSTIC_ONLY_COVERAGE_STRATA_NO_EXTRA_STRATEGY_ARM",
        "capital_evaluations_are_separate": "DO_NOT_SUM_ACROSS_ARMS_HORIZONS_OR_COST_SCENARIOS",
        "maker": MAKER_SENSITIVITY, "execution_count": 0, "real_funds_writes": 0,
    }
    _write_json(root, "metrics.json", metrics)
    checks = contract_receipt(rows, evaluation, origin_count)
    _write_json(root, "test_receipt.json", {
        "scope": "BUILTIN_CONTRACT_CHECKS_NOT_A_PYTEST_RECEIPT", "status": "PASS",
        "checks": checks, "passed": len(checks), "seed": SEED,
        "artifact_sha256": {name: data.digest_file(root / name) for name in OUTPUT_FILES[:-1]},
        "labels": list(LABELS),
    })
    return {"mode": mode, "status": evaluation["status"], "labels": list(LABELS),
            "feature_origins": len(rows), "origin_horizon_rows": origin_count,
            "trades_csv_rows": trade_count, "cells": len(evaluation["cells"]),
            "source_objects": inventory.get("budget", {}).get("objects", 0),
            "outcome_gate": config["outcome_gate"], "contract_checks_passed": len(checks)}


def contract_receipt(rows: list[dict[str, Any]], evaluation: dict[str, Any], count: int) -> list[str]:
    checks = {
        "fixed_hourly_origins": all(r["t"] % 3600 == 60 for r in rows),
        "all_origin_horizons_retained": count == len(rows) * 4,
        "ten_frozen_X_controls": all(not data.ready(r)[0] or len(r["x"]) == 10 for r in rows),
        "strict_bar_cutoffs": all(not data.ready(r)[0] or r["x_end_us"] < (r["t"] - 60) * US for r in rows),
        "stock_sample_guard": all(not data.ready(r)[1] or r["t"] - 660 <= r["z_t"] <= r["t"] - 360 for r in rows),
        "nonpositive_score": all(m["score_coefficient"] is None or m["score_coefficient"] <= 0 for f in evaluation["folds"] for m in f["models"]),
        "worst_horizon_purge_and_embargo": all(f["training_max_label_end"] is None or f["training_max_label_end"] < f["validation_start"] - 3600 for f in evaluation["folds"]),
        "eight_claim_slots": len(evaluation["inference"]) == 8,
        "separate_sleeves_capital": all(c["capital"]["max_allocated_capital"] <= 1 for c in evaluation["cells"]),
    }
    for name, passed in checks.items():
        data.require(passed, "CONTRACT_CHECK_FAILED_" + name)
    return list(checks)


def run_demo(output_dir: Path) -> dict[str, Any]:
    root = data.prepare_output(output_dir)
    rows, start, inventory = synthetic_dataset()
    return write_reports(root, rows, start, inventory, evaluate(rows, start), "DEV_SYNTHETIC_ONLY")


def inspect_historical(binance_root: Path, okx_root: Path, output_dir: Path) -> dict[str, Any]:
    root = data.prepare_output(output_dir)
    rows, inventory = data.inspect_panel(binance_root, okx_root)
    evaluation = {"status": "INSPECTION_ONLY", "cells": [], "folds": [], "records": {},
                  "inference": paired_inference([])}
    return write_reports(root, rows, data.JULY_START, inventory, evaluation,
                         "HISTORICAL_OFFLINE_FEATURE_COVERAGE_ONLY")


def authorized_panel(input_path: Path, allowlist_path: Path | None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    # Reject before looking at any panel bytes, path aliases, or caller exposure labels.
    data.require(allowlist_path is not None, "EXPOSED_DEV_NOT_AUTHORIZED")
    allowlist = data.read_json(allowlist_path)
    data.require(type(allowlist) is dict and allowlist.get("schema") == "strategy_eval.exposed-dev.v1"
                 and allowlist.get("exposure") == "EXPOSED_DEV"
                 and type(allowlist.get("panels")) is list, "EXPOSED_DEV_NOT_AUTHORIZED")
    path = data.safe_file(input_path.parent, input_path.name, 32 * 1024**2)
    digest = data.digest_file(path)
    entries = [e for e in allowlist["panels"] if type(e) is dict and e.get("path") == str(path)
               and e.get("sha256") == digest]
    data.require(len(entries) == 1, "EXPOSED_DEV_NOT_AUTHORIZED")
    entry = entries[0]
    panel = data.read_json(path, 32 * 1024**2)
    data.require(type(panel) is dict and panel.get("schema") == "strategy_eval.normalized.v1"
                 and panel.get("label") == "HISTORICAL_OFFLINE / PIT_UNKNOWN"
                 and panel.get("exposure") == "EXPOSED_DEV", "NORMALIZED_PANEL_SCHEMA_INVALID")
    start, rows = panel.get("start_utc_s"), panel.get("rows")
    data.validate_grid(rows, start)
    data.require(type(entry.get("start_utc_s")) is int and type(entry.get("end_utc_s")) is int
                 and entry["start_utc_s"] == start and entry["end_utc_s"] == start + len(rows) * 3600,
                 "EXPOSED_DEV_NOT_AUTHORIZED")
    # Feature-window warmup and all outcomes, including maximum-horizon exits,
    # must remain inside the authorized panel interval. No adjacent protected read.
    for row in rows:
        if row["t"] - 60 - DAY - 60 < start:
            data.require(not data.ready(row)[0], "EXPOSURE_FEATURE_WINDOW_OUTSIDE_ALLOWLIST")
        supplied = row.get("outcomes", {})
        data.require(type(supplied) is dict and set(supplied).issubset({str(h) for h in HORIZONS}),
                     "OUTCOME_SCHEMA_INVALID")
        row["outcomes"] = {}
        for key, value in supplied.items():
            label = Outcome.from_dict(value)
            data.require(label.entry_t == row["t"] + 60 and label.exit_t == row["t"] + 60 + int(key) * 3600,
                         "OUTCOME_CLOCK_INVALID")
            data.require(start <= label.entry_t < label.exit_t <= entry["end_utc_s"],
                         "EXPOSURE_OUTCOME_OUTSIDE_ALLOWLIST")
            row["outcomes"][key] = label
    return rows, start, {"allowlist_sha256": data.digest_file(allowlist_path), "panel_sha256": digest,
                         "start_utc_s": start, "end_utc_s": entry["end_utc_s"], "exposure": "EXPOSED_DEV",
                         "authorization": "EXPLICIT_CALLER_ALLOWLIST_NOT_SOURCE_ADMISSION"}


def evaluate_historical(input_path: Path, allowlist_path: Path | None, output_dir: Path) -> dict[str, Any]:
    rows, start, authorization = authorized_panel(input_path, allowlist_path)
    root = data.prepare_output(output_dir)
    inventory = {"mode": "HISTORICAL_OFFLINE / PIT_UNKNOWN", "labels": list(LABELS),
                 "normalization": "EXPLICIT_NORMALIZED_PANEL_CLAIMS_NATIVE_ADAPTER_NOT_REATTESTED",
                 "authorization": authorization, "market_requests": 0, "ticks_l2_opened": 0}
    return write_reports(root, rows, start, inventory, evaluate(rows, start),
                         "HISTORICAL_OFFLINE / PIT_UNKNOWN", authorization=authorization)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="deterministic synthetic realized-price PnL only")
    demo.add_argument("--output-dir", type=Path, required=True)
    inspect = commands.add_parser("inspect-historical", help="bounded July BTC manifest/QC and features only")
    inspect.add_argument("--binance-root", type=Path, required=True)
    inspect.add_argument("--okx-root", type=Path, required=True)
    inspect.add_argument("--output-dir", type=Path, required=True)
    historical = commands.add_parser("evaluate-historical", help="explicitly allowlisted normalized EXPOSED_DEV panel only")
    historical.add_argument("--input", type=Path, required=True)
    historical.add_argument("--exposed-dev-allowlist", type=Path)
    historical.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo(args.output_dir)
        elif args.command == "inspect-historical":
            result = inspect_historical(args.binance_root, args.okx_root, args.output_dir)
        else:
            result = evaluate_historical(args.input, args.exposed_dev_allowlist, args.output_dir)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, BadZipFile, csv.Error) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "labels": list(LABELS)}, sort_keys=True), file=sys.stderr)
        return 2
if __name__ == "__main__":
    raise SystemExit(main())
