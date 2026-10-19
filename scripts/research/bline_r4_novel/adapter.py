"""Deterministic feature-only adapter for B-line R4 Trapped Leverage Overhang mechanism."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.dataset as ds

from scripts.research.bline_multiyear.contracts import X_NAMES

from .contracts import (
    COVERAGE_PERIOD_UTC,
    H39_FORWARD,
    H40_EXCLUSION,
    sha256_digest,
)

US = 1_000_000
MINUTE_US = 60 * US
HOUR_US = 3600 * US
DAY_US = 24 * HOUR_US

R1_REQUIRED_KEYS = {
    "action",
    "asset",
    "cutoff",
    "data_kind",
    "entry_t",
    "receiver_pit",
    "schema",
    "source_ids",
    "t",
    "venue",
    "x",
    "x_complete",
    "x_end_us",
    "x_names",
    "x_reason",
}


def parse_iso_epoch(iso_str: str) -> int:
    dt = datetime.fromisoformat(iso_str)
    return int(dt.timestamp())


START_EPOCH = parse_iso_epoch(COVERAGE_PERIOD_UTC[0])
END_EPOCH = parse_iso_epoch(COVERAGE_PERIOD_UTC[1])
H40_START = parse_iso_epoch(H40_EXCLUSION[0])
H40_END = parse_iso_epoch(H40_EXCLUSION[1])
H39_START = parse_iso_epoch(H39_FORWARD)


def is_protected_epoch(t: int) -> bool:
    """Check if origin falls in protected or heldout windows."""
    return (H40_START <= t < H40_END) or (t >= H39_START)


def load_r1_frozen_x(r1_panel_path: Path) -> dict[int, dict[str, Any]]:
    """Load authoritative frozen baseline X controls from R1 feature panel."""
    if not r1_panel_path.exists():
        raise FileNotFoundError(f"Missing R1 panel: {r1_panel_path}")

    import json

    rows: dict[int, dict[str, Any]] = {}
    with r1_panel_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("venue") != "binance" or row.get("asset") != "BTC":
                continue
            if row.get("data_kind") != "HISTORICAL_FEATURE_ONLY":
                continue

            t = row["t"]
            if not (START_EPOCH <= t < END_EPOCH):
                continue

            if t in rows:
                raise ValueError(f"DUPLICATE_FROZEN_X_ORIGIN: {t}")

            cutoff = row["cutoff"]
            if cutoff != t - 60 or t % 3600 != 60:
                raise ValueError(f"FROZEN_X_ORIGIN_CLOCK_MISMATCH: {t}")

            if row.get("x_names") != X_NAMES:
                raise ValueError("FROZEN_X_SCHEMA_MISMATCH")

            x = row.get("x")
            x_end_us = row.get("x_end_us")
            cutoff_us = cutoff * US

            valid = (
                bool(row.get("x_complete"))
                and x is not None
                and len(x) == len(X_NAMES)
                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in x)
                and isinstance(x_end_us, int)
                and x_end_us < cutoff_us
            )

            rows[t] = {
                "t": t,
                "cutoff": cutoff,
                "x_eligible": valid,
                "log_return_4h": x[1] if valid else None,
                "log_return_24h": x[2] if valid else None,
                "rv_24h": x[4] if valid else None,
                "x_end_us": x_end_us,
                "source_ids": row.get("source_ids", {}).get("X", []),
            }

    return rows


def load_native_open_interest(
    metrics_dir: Path,
) -> tuple[dict[int, float], dict[int, str], dict[str, dict[str, Any]]]:
    """Load native Binance USD-M 5m base_open_interest from normalized metrics dataset."""
    if not metrics_dir.exists():
        raise FileNotFoundError(f"Missing metrics dir: {metrics_dir}")

    dataset = ds.dataset(str(metrics_dir), format="parquet")
    table = dataset.to_table(
        columns=["native_label_us", "base_open_interest", "archive_sha256"]
    )

    labels = table["native_label_us"].to_numpy()
    ois = table["base_open_interest"].to_numpy()
    shas = table["archive_sha256"].to_numpy()

    oi_map: dict[int, float] = {}
    sha_map: dict[int, str] = {}
    archive_manifest: dict[str, dict[str, Any]] = {}

    for i in range(len(labels)):
        l = int(labels[i])
        val = ois[i]
        sha = str(shas[i])
        if val is not None and not math.isnan(val) and val > 0:
            oi_map[l] = float(val)
            sha_map[l] = sha

    parquet_files = sorted(metrics_dir.glob("*.parquet"))
    for pf in parquet_files:
        archive_manifest[str(pf)] = {
            "sha256": sha256_digest(pf),
            "bytes": pf.stat().st_size,
        }

    return oi_map, sha_map, archive_manifest


def evaluate_origin_feature(
    t: int,
    x_info: dict[str, Any] | None,
    oi_map: dict[int, float],
    sha_map: dict[int, str],
    registration_sha: str,
) -> dict[str, Any]:
    """Deterministic evaluation of a single scheduled origin under strict causal clocks."""
    cutoff = t - 60
    cutoff_us = cutoff * US
    origin_utc = datetime.fromtimestamp(t, UTC).isoformat()

    expected_native_label_us = cutoff_us - 10 * MINUTE_US  # HH:50:00 UTC
    content_upper_us = expected_native_label_us + 5 * MINUTE_US  # HH:55:00 UTC < cutoff_us
    pred_24h_label_us = expected_native_label_us - DAY_US
    pred_4h_label_us = expected_native_label_us - 4 * HOUR_US

    is_protected = is_protected_epoch(t)

    reasons: list[str] = []
    if is_protected:
        reasons.append("PROTECTED_HOLDOUT_WINDOW")

    x_eligible = False
    x_ret4h = None
    if x_info is not None and not is_protected:
        x_eligible = bool(x_info.get("x_eligible", False))
        x_ret4h = x_info.get("log_return_4h")
        if not x_eligible:
            reasons.append("X_INCOMPLETE_OR_UNAVAILABLE")
    else:
        if not is_protected:
            reasons.append("X_MISSING_ORIGIN")

    cur_oi = oi_map.get(expected_native_label_us) if not is_protected else None
    oi_24h = oi_map.get(pred_24h_label_us) if not is_protected else None
    oi_4h = oi_map.get(pred_4h_label_us) if not is_protected else None

    if cur_oi is None:
        reasons.append("NATIVE_BASE_OI_MISSING_AT_CUTOFF_GUARD")
    if oi_24h is None:
        reasons.append("PREDECESSOR_24H_BASE_OI_MISSING")
    if oi_4h is None:
        reasons.append("PREDECESSOR_4H_BASE_OI_MISSING")

    z_eligible = (
        (not is_protected)
        and (cur_oi is not None)
        and (oi_24h is not None)
        and (oi_4h is not None)
    )

    delta_log_oi_24h = None
    delta_log_oi_4h = None
    z_condition = False

    if z_eligible and cur_oi and oi_24h and oi_4h:
        delta_log_oi_24h = math.log(cur_oi / oi_24h)
        delta_log_oi_4h = math.log(cur_oi / oi_4h)
        z_condition = (delta_log_oi_24h >= 0.015) and (delta_log_oi_4h >= -0.005)

    x_condition = False
    if x_eligible and x_ret4h is not None:
        x_condition = x_ret4h <= -0.01

    paired_xz_eligible = x_eligible and z_eligible

    if paired_xz_eligible:
        if not x_condition:
            reasons.append("X_THRESHOLD_NOT_MET")
        if not z_condition:
            reasons.append("Z_THRESHOLD_NOT_MET")

    trigger = paired_xz_eligible and x_condition and z_condition

    return {
        "origin_utc": origin_utc,
        "t": t,
        "cutoff": cutoff,
        "cutoff_us": cutoff_us,
        "expected_native_label_us": expected_native_label_us,
        "content_upper_us": content_upper_us,
        "pred_24h_label_us": pred_24h_label_us,
        "pred_4h_label_us": pred_4h_label_us,
        "archive_sha256": sha_map.get(expected_native_label_us),
        "x_eligible": x_eligible,
        "z_eligible": z_eligible,
        "paired_xz_eligible": paired_xz_eligible,
        "log_return_4h": x_ret4h,
        "base_open_interest": cur_oi,
        "pred_24h_base_open_interest": oi_24h,
        "pred_4h_base_open_interest": oi_4h,
        "delta_log_oi_24h": delta_log_oi_24h,
        "delta_log_oi_4h": delta_log_oi_4h,
        "x_condition": x_condition,
        "z_condition": z_condition,
        "paired_baseline_action": "SHORT" if (paired_xz_eligible and x_condition) else "NO_ACTION",
        "trigger": trigger,
        "action": "SHORT" if trigger else "NO_ACTION",
        "no_action_reasons": [] if trigger else reasons,
        "receiver_pit": "PIT_UNKNOWN",
        "source_status": "SOURCE_NOT_ADMITTED",
        "registration_sha256": registration_sha,
    }
