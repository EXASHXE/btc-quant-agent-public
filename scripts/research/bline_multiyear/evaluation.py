"""Synthetic adapter -> frozen P1; deterministic candidate economics."""
from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime, timedelta

import numpy as np

from scripts.research.exposed_dev_bridge.archive_adapter import matched_population
from scripts.research.strategy_eval import DAY, HORIZONS, PLAN, SEED
from scripts.research.strategy_eval import pipeline as p1
from scripts.research.strategy_eval.costs import SCENARIOS, US, Outcome, Settlement, economics

from .contracts import X_NAMES, canonical, registration, signals
from .panel import Channel, build_rows


def synthetic_rows() -> tuple[list[dict], int]:
    """Independent synthetic native inputs through the SAME historical feature adapter."""
    start = 1704067200
    rng = np.random.default_rng(SEED)
    minutes = np.arange(85*1440+1)
    hour = minutes/60
    price = 42000*np.exp(np.cumsum((-.004*np.sin(hour/11)+.002*np.sin(hour/79))/60
                                  + rng.normal(0, .0001, len(minutes))))
    cash_basis = .0008+.0006*np.sin(hour/17)
    premium = .0008+.0007*np.sin(hour/19)
    volume = 10+3*np.sin(hour/9)
    oi = 100000*np.exp(.3*np.sin(hour/31))
    ratio = np.exp(.8*np.sin(hour/11))
    def native(t: int, product: str, kind: str) -> dict:
        dt = datetime.fromtimestamp(t, UTC)
        return {"exchange": "binance", "native_symbol": "BTCUSDT", "product_type": product,
                "interval_start_utc": dt, "interval_end_utc": dt+timedelta(minutes=1),
                "event_ts_utc": dt+timedelta(minutes=1), "source_id": "SYNTHETIC_"+kind,
                "raw_sha256": "a"*64, "interval": "1m", "source_native_ts": str(t*1000),
                "source_time_unit": "ms"}
    result = []
    # Monthly-size bounded memory, plus the exact causal lookback.
    for first_day in range(0, 84, 7):
        left = max(0, first_day*1440-1442)
        right = min(84*1440, (first_day+7)*1440)
        records = {k: [] for k in ("perp", "spot", "mark", "index", "premium", "oi",
                                     "funding", "flow_perp", "flow_spot")}
        for i in range(left, right):
            t = start+i*60
            for kind in ("perp", "spot", "mark", "index", "premium"):
                if kind == "perp" and i == 44*1440+180:
                    continue
                p = (price[i+1] if kind == "perp" else
                     price[i+1]/math.exp(cash_basis[i]) if kind == "spot" else
                     price[i+1]*math.exp(premium[i]) if kind == "mark" else
                     price[i+1] if kind == "index" else premium[i])
                r = native(t, "SPOT" if kind == "spot" else "USD_M_PERPETUAL", kind)
                r.update(close=float(p), high=float(p*1.0002), low=float(p*.9998),
                         base_volume=float(volume[i]), quote_volume=float(volume[i]*price[i]))
                records[kind].append(r)
            if i % 5 == 0 and i not in (45*1440+235, 45*1440+230):
                r = native(t, "USD_M_PERPETUAL", "oi")
                r.update(event_ts_utc=r["interval_start_utc"], interval="5m",
                         base_open_interest=float(oi[i]), top_position_long_short_ratio=float(ratio[i]))
                records["oi"].append(r)
            if i % 480 == 0:
                r = native(t, "USD_M_PERPETUAL", "funding")
                r.update(event_ts_utc=r["interval_start_utc"],
                         funding_rate=float(.00012*math.cos(hour[i]/37)))
                records["funding"].append(r)
            for kind in ("flow_perp", "flow_spot"):
                if i == 47*1440+359:
                    continue
                r = native(t, "SPOT" if kind == "flow_spot" else "USD_M_PERPETUAL", kind)
                r.update(volume_quote=float(volume[i]*price[i]),
                         signed_flow_quote=float(.2*np.sin(hour[i]/11)*volume[i]*price[i]))
                records[kind].append(r)
        fields = {"perp": ("close", "high", "low", "base_volume", "quote_volume"),
                  "oi": ("base_open_interest", "top_position_long_short_ratio"),
                  "funding": ("funding_rate",),
                  "flow_perp": ("volume_quote", "signed_flow_quote"),
                  "flow_spot": ("volume_quote", "signed_flow_quote")}
        channels = {k: Channel(v, fields.get(k, ("close",)), event=k=="funding")
                    for k, v in records.items()}
        result += build_rows(start+first_day*DAY, start+(first_day+7)*DAY, channels)
    end = start+84*DAY
    calendar = tuple((start+i*8*3600)*US for i in range(85*3+1))
    for row in result:
        entry = row["entry_t"]
        row["outcomes"] = {}
        for h in HORIZONS:
            exit_t = entry+h*3600
            if exit_t >= end:
                continue
            settlements = tuple(Settlement(t, .00012*math.cos((t//US-start)/3600/37),
                                           float(price[(t//US-start)//60])*1.0001)
                                for t in calendar if entry*US < t <= exit_t*US)
            row["outcomes"][str(h)] = Outcome(entry, exit_t, float(price[(entry-start)//60]),
                float(price[(exit_t-start)//60]), settlements, tuple(s.t_us for s in settlements),
                (entry*US, exit_t*US))
        row.update(test_only=True, data_kind="TEST_ONLY_SYNTHETIC")
    return result, start


def candidate_economics(rows: list[dict], start: int) -> list[dict]:
    """Apply frozen policies, retaining NO_ACTION and unresolved outcomes in every cell."""
    cells = []
    for candidate in registration()["candidates"]:
        for day in PLAN["outer_development_days"]:
            val = [r for r in rows if start+day*DAY <= r["t"] < start+(day+14)*DAY]
            for h in HORIZONS:
                for cost in SCENARIOS:
                    points = {"X": [], "XZ": []}
                    eligible = 0
                    for row in val:
                        a, b, paired = signals(row, candidate["id"])
                        eligible += paired
                        for arm, action in (("X", a), ("XZ", b)):
                            points[arm].append(economics(row.get("outcomes", {}).get(str(h)),
                                                         action, h, cost))
                    metrics = {}
                    for arm, ps in points.items():
                        unresolved = sum(p["status"] == "UTILITY_UNRESOLVED" for p in ps)
                        metrics[arm] = {
                            "scheduled": len(val), "paired_eligible": eligible,
                            "acted": sum(bool(p["action"]) for p in ps),
                            "no_action": sum(not p["action"] for p in ps), "unresolved": unresolved,
                            "net_utility_per_scheduled": None if unresolved or not val else
                                sum(p["sleeve_pnl"] for p in ps)/len(val),
                            "funding_debit_sleeves": sum(p["funding_debit"]/h for p in ps
                                                        if p["status"] == "RESOLVED"),
                            "cost_sleeves": sum(p["total_cost"]/h for p in ps
                                               if p["status"] == "RESOLVED")}
                    x, z = (metrics[a]["net_utility_per_scheduled"] for a in ("X", "XZ"))
                    cells.append({"candidate": candidate["id"], "fold_day": day, "h": h,
                                  "scenario": cost.name, "arms": metrics,
                                  "paired_increment": None if x is None or z is None else z-x})
    return cells


def run_synthetic(output) -> dict:
    import hashlib
    rows, start = synthetic_rows()
    panel = {"schema": "strategy_eval.normalized.v1", "exposure": "EXPOSED_DEV",
             "label": "HISTORICAL_OFFLINE / PIT_UNKNOWN", "test_only": True,
             "data_kind": "TEST_ONLY_SYNTHETIC", "x_names": X_NAMES,
             "start_utc_s": start, "rows": [
                 {**r, "outcomes": {k: v.to_dict() for k, v in r["outcomes"].items()}} for r in rows]}
    panel_path = output/"synthetic_normalized_panel.json"
    raw = canonical(panel)
    panel_path.write_bytes(raw)
    allowlist = {"schema": "strategy_eval.exposed-dev.v1", "exposure": "EXPOSED_DEV",
                 "test_only": True, "data_kind": "TEST_ONLY_SYNTHETIC",
                 "authority": "TEST_FIXTURE_NOT_OWNER_AUTHORIZATION", "panels": [
                     {"path": str(panel_path), "sha256": hashlib.sha256(raw).hexdigest(),
                      "start_utc_s": start, "end_utc_s": start+84*DAY}]}
    allow_path = output/"synthetic_integrity_allowlist.json"
    allow_path.write_bytes(canonical(allowlist))
    parsed, parsed_start, binding = p1.authorized_panel(panel_path, allow_path)
    common = matched_population(parsed)
    evaluation = p1.evaluate(common, parsed_start)
    p1_cells = [{k: v for k, v in cell.items() if k != "points"} for cell in evaluation["cells"]]
    candidates = candidate_economics(parsed, start)
    checks = {
        "84d_hourly": len(rows) == 84*24,
        "three_outer_folds": len(evaluation["folds"]) == 3 and all(
            f["status"] == "EXPOSED_DEVELOPMENT_FOLD" for f in evaluation["folds"]),
        "48_p1_cells": len(p1_cells) == 48,
        "48_fixed_candidate_cells": len(candidates) == 48,
        "no_dropped_origins": len(common) == len(rows),
        "paired_training": all(len({m["train_times_sha256"] for m in f["models"]}) == 1
                               for f in evaluation["folds"]),
        "purge_embargo": all(f["training_max_label_end"] < f["validation_start"]-3600
                             for f in evaluation["folds"]),
        "missing_oi_retained": any(r["x_complete"] and r["z_status"] != "OBSERVED" for r in rows),
        "funding_nonzero": any(c["arms"]["X"]["funding_debit_sleeves"] != 0 for c in candidates),
        "all_scheduled_denominators": all(c["scheduled"] == 336 for c in p1_cells),
        "paired_candidate_denominators": all(c["arms"]["X"]["scheduled"] ==
                                              c["arms"]["XZ"]["scheduled"] == 336 for c in candidates)}
    summary = {"status": "PASS" if all(checks.values()) else "FAIL",
               "data_kind": "TEST_ONLY_SYNTHETIC", "alpha": "NO_ALPHA_ESTABLISHED",
               "adapter": "SAME_C1_C2_C3_FEATURE_ADAPTER_SYNTHETIC_NATIVE_INPUTS",
               "p1_model_note": "Frozen P1 increasing-OI model is a plumbing check, not the two fixed policies",
               "baseline_x_names": X_NAMES, "checks": checks, "origins": len(rows),
               "unavailable_reasons": dict(Counter(r["x_reason"] for r in rows)),
               "p1_binding": binding, "folds": evaluation["folds"], "p1_cells": p1_cells,
               "p1_inference": evaluation["inference"], "candidate_cells": candidates,
               "real_historical_outcomes_evaluated": 0, "real_outcome_labels_read": 0}
    return summary
