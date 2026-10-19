"""Offline native-metrics join. No price loading, outcomes, fitting or network code."""

from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import math
import os
import shlex
import subprocess
import sys
import time
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from scripts.data.bline_r2.quality import epoch_us, scan_archive
from scripts.data.bline_r2.report import FIELDS, native_coverage, positive, state_at_origin
from scripts.research.bline_multiyear.contracts import X_NAMES
from scripts.research.bline_multiyear.coverage_extension import EventClusterer
from tools.data.qc import BINANCE_METRICS_SCHEMA

from .contracts import LABELS, PERIODS, TASK, canonical, digest, freeze, registration

US = 1_000_000
HOUR = 3600 * US
KEY = ("binance", "BTCUSDT", "USD_M_PERPETUAL")
REPO = Path(__file__).resolve().parents[3]
R1_KEYS = {
    "action",
    "asset",
    "clock",
    "cutoff",
    "data_kind",
    "derivatives",
    "entry_t",
    "flow_clock",
    "funding_clock",
    "oi_clock",
    "oi_native_samples",
    "raw_z_present",
    "receiver_gate",
    "receiver_pit",
    "schema",
    "signed_flow",
    "source_ids",
    "t",
    "venue",
    "x",
    "x_complete",
    "x_end_us",
    "x_names",
    "x_reason",
    "z",
    "z_4h_exact",
    "z_reason",
    "z_status",
    "z_t",
}
NATIVE_COLUMNS = {
    "native_label_us",
    "native_create_time",
    "content_upper_us_conservative",
    *FIELDS,
    "valid_oi_position",
    "archive_sha256",
    "native_symbol",
}
PANEL_KEYS = {
    "population",
    "origin_utc",
    "origin_us",
    "cutoff_us",
    "expected_native_label_us",
    "selected_native_label_us",
    "native_create_time",
    "content_upper_us",
    "predecessor_label_us",
    "predecessor_native_create_time",
    "predecessor_content_upper_us",
    "native_archive_sha256",
    "predecessor_archive_sha256",
    "base_open_interest",
    "predecessor_base_open_interest",
    "sum_toptrader_long_short_ratio",
    "log_oi_4h",
    "log_top_position_ratio",
    "log_return_4h",
    "x_source_ids",
    "x_end_us",
    "x_eligible",
    "native_oi_present",
    "native_ratio_present",
    "exact_4h_predecessor",
    "boundary_rejected",
    "conflicting_label",
    "oi_only_eligible",
    "z_eligible",
    "paired_xz_eligible",
    "x_condition",
    "z_condition",
    "paired_baseline_action",
    "trigger",
    "diagnostic_action",
    "no_action_reasons",
    "protected_window",
    "receiver_pit",
    "source_status",
    "executable",
    "registration_sha256",
}


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    data = canonical(value)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("REFUSE_OVERWRITE_CHANGED_ARTIFACT:" + str(path))
    else:
        path.write_bytes(data)


def utc(t):
    return datetime.fromtimestamp(t // US, UTC).isoformat()


def contained(path, root):
    return path.resolve().is_relative_to(root.resolve())


def output_guard(output, roots):
    for root in roots:
        if contained(output, root) or contained(root, output):
            raise ValueError("OUTPUT_INPUT_OVERLAP")
    output.mkdir(parents=True, exist_ok=True)


def identities(r1, r2, old):
    delivery = read_json(r2 / "DELIVERY_RECEIPT.json")
    report = Path(delivery["completion_receipt"]).parent
    if not contained(report, r2 / "reports"):
        raise ValueError("REPORT_OUTSIDE_EXPLICIT_R2_ROOT")
    paths = [r2 / "DELIVERY_RECEIPT.json"]
    paths += sorted((r1 / "preregister").glob("*.json"))
    paths += sorted((r1 / "features-release").iterdir())
    paths += sorted(old.glob("*.json"))
    paths += [
        report / n
        for n in (
            "COMPLETION_RECEIPT.json",
            "verified_archive_inventory.json",
            "normalized_metrics_sha_manifest.json",
            "comparison_with_BLINE_R1.json",
            "source_timestamp_contract.json",
            "sha_manifest.json",
        )
    ]
    identity = {
        str(p.resolve()): {"sha256": digest(p), "bytes": p.stat().st_size}
        for p in paths
        if p.is_file()
    }
    receipt = read_json(r1 / "features-release/run_receipt.json")
    for name, expected in receipt["artifacts_sha256"].items():
        p = r1 / "features-release" / name
        if identity[str(p.resolve())]["sha256"] != expected:
            raise ValueError("FROZEN_R1_RECEIPT_HASH_MISMATCH:" + name)
    if digest(report / "COMPLETION_RECEIPT.json") != delivery["completion_receipt_sha256"]:
        raise ValueError("R2_DELIVERY_RECEIPT_HASH_MISMATCH")
    completion = read_json(report / "COMPLETION_RECEIPT.json")
    for path in paths:
        if (
            path.parent == report
            and path.name != "COMPLETION_RECEIPT.json"
            and digest(path) != completion["artifact_sha256"][path.name]
        ):
            raise ValueError("R2_REPORT_ARTIFACT_HASH_MISMATCH:" + path.name)
    old_receipt = read_json(old / "run_receipt.json")
    for name, expected in old_receipt["artifacts_sha256"].items():
        if digest(old / name) != expected:
            raise ValueError("EXISTING_R2_ARTIFACT_HASH_MISMATCH:" + name)
    return report, identity


def load_r1(path):
    rows = {}
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            if set(row) - R1_KEYS:
                raise ValueError("NO_OUTCOME_SCHEMA_VIOLATION:" + str(sorted(set(row) - R1_KEYS)))
            if row.get("venue") != "binance" or row.get("asset") != "BTC":
                continue
            if row["data_kind"] != "HISTORICAL_FEATURE_ONLY":
                raise ValueError("NO_OUTCOME_DATA_KIND_REQUIRED")
            t = row["t"] * US
            if t in rows:
                raise ValueError("DUPLICATE_FROZEN_X_ORIGIN")
            if row["cutoff"] * US != t - 60 * US or t % HOUR != 60 * US:
                raise ValueError("FROZEN_X_ORIGIN_CLOCK_MISMATCH")
            if row["x_names"] != X_NAMES:
                raise ValueError("FROZEN_X_SCHEMA_MISMATCH")
            x = row["x"]
            valid = (
                row["x_complete"]
                and x is not None
                and len(x) == len(X_NAMES)
                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in x)
                and isinstance(row.get("x_end_us"), int)
                and row["x_end_us"] < row["cutoff"] * US
            )
            rows[t] = {
                "t": t // US,
                "x_eligible": bool(valid),
                "log_return_4h": x[1] if valid else None,
                "x_end_us": row.get("x_end_us"),
                "x_source_ids": row.get("source_ids", {}).get("X", []),
                "z": row["z"],
                "z_status": row["z_status"],
            }
    return rows


def add_native(states, refs, strings, conflicts, t, values, archive_sha, native_text):
    duplicate = t in states
    if duplicate and states[t] != values:
        conflicts.add(t)
    elif not duplicate:
        states[t] = values
        strings[t] = native_text
    refs.setdefault(t, set()).add(archive_sha)
    return duplicate


def eligible_source(rec):
    return (
        (rec.get("venue"), rec.get("symbol"), rec.get("product")) == KEY
        and rec.get("family") == "metrics"
        and rec.get("interval") == "5m"
        and rec.get("status") in ("DOWNLOADED_VERIFIED", "REUSED_VERIFIED")
    )


def load_native(r2, report):
    """Rehash verified objects and reuse native CSV validation; inspect actual parquet schema."""
    manifest = {x["path"]: x for x in read_json(report / "normalized_metrics_sha_manifest.json")}
    verified_paths = {
        (str(Path(path).resolve()), item["sha256"])
        for item in read_json(report / "sha_manifest.json")
        if item["publisher_verified"]
        for path in [item["canonical_path"], *item["aliases"]]
    }
    states, refs, strings, conflicts = {}, {}, {}, set()
    sources, source_identity = [], {}
    duplicates = 0
    for rec in read_json(report / "verified_archive_inventory.json"):
        if not eligible_source(rec):
            continue
        p, raw = Path(rec["normalized_metrics_path"]), Path(rec["path"])
        # Reused verified archives retain their original read-only paths. Require
        # their exact path/hash in the delivered manifest and a native metrics ZIP.
        if (
            not contained(p, r2 / "normalized_metrics/BTCUSDT")
            or (str(raw.resolve()), rec["sha256"]) not in verified_paths
            or raw.name != f"BTCUSDT-metrics-{rec['period']}.zip"
        ):
            raise ValueError("NATIVE_LINEAGE_OUTSIDE_EXPLICIT_R2_ROOT")
        expected = manifest.get(str(p))
        if not expected or digest(p) != expected["sha256"] or p.stat().st_size != expected["bytes"]:
            raise ValueError("NORMALIZED_SHA_MISMATCH:" + str(p))
        if digest(raw) != rec["sha256"] or rec.get("publisher_sha256") != rec["sha256"]:
            raise ValueError("VERIFIED_NATIVE_ARCHIVE_SHA_MISMATCH:" + str(raw))
        qc = scan_archive(raw, rec, rec["sha256"])
        if not qc["zip_crc_full_stream_verified"] or qc["rows"] != rec["qc"]["rows"]:
            raise ValueError("NATIVE_QC_CHANGED")
        table = pq.ParquetFile(p).read()
        if set(table.column_names) != NATIVE_COLUMNS:
            raise ValueError("NO_OUTCOME_NATIVE_SCHEMA_MISMATCH")
        # Validate the native field mapping against an actual raw archive row.
        with zipfile.ZipFile(raw) as archive, archive.open(archive.namelist()[0]) as stream:
            reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
            if next(reader) != BINANCE_METRICS_SCHEMA:
                raise ValueError("NATIVE_HEADER_MISMATCH")
            first = next(reader)
        first_normalized = table.slice(0, 1).to_pylist()[0]
        if (
            table.num_rows != qc["rows"]
            or first_normalized["native_create_time"] != first[0]
            or first_normalized["native_label_us"] != epoch_us(first[0])
        ):
            raise ValueError("RAW_NORMALIZED_ROW_OR_CLOCK_MISMATCH")
        for i, name in enumerate(FIELDS, 2):
            try:
                v = float(first[i])
            except ValueError:
                v = None
            v = v if positive(v) else None
            if first_normalized[name] != v:
                raise ValueError("RAW_NORMALIZED_FIELD_MAPPING_MISMATCH:" + name)
        data = table.to_pydict()
        for i, t in enumerate(data["native_label_us"]):
            if (
                data["archive_sha256"][i] != rec["sha256"]
                or data["native_symbol"][i] != "BTCUSDT"
                or epoch_us(data["native_create_time"][i]) != t
                or data["content_upper_us_conservative"][i] != t + 300 * US
            ):
                raise ValueError("NATIVE_PARQUET_LINEAGE_OR_CLOCK_MISMATCH")
            values = tuple(data[f][i] for f in FIELDS)
            if any(v is not None and not positive(v) for v in values):
                raise ValueError("INVALID_NORMALIZED_NATIVE_VALUE")
            duplicates += add_native(
                states,
                refs,
                strings,
                conflicts,
                t,
                values,
                rec["sha256"],
                data["native_create_time"][i],
            )
        for path, sha in [(p, expected["sha256"]), (raw, rec["sha256"])]:
            source_identity[str(path)] = {"sha256": sha, "bytes": path.stat().st_size}
        sources.append(
            {
                "archive_sha256": rec["sha256"],
                "period": rec["period"],
                "venue": rec["venue"],
                "symbol": rec["symbol"],
                "product": rec["product"],
                "family": rec["family"],
                "interval": rec["interval"],
                "archive_path": str(raw),
                "normalized_path": str(p),
                "normalized_sha256": expected["sha256"],
                "source_url": rec["url"],
                "http_last_modified": rec.get("last_modified"),
                "http_etag": rec.get("etag"),
                "downloaded_at_utc": rec.get("downloaded_at_utc"),
                "receiver_first_known": None,
                "receiver_pit": "PIT_UNKNOWN",
                "observed_label_pattern": qc["observed_label_pattern"],
                "rows": qc["rows"],
                "missing_oi_rows": qc["missing_base_oi_rows"],
                "missing_ratio_rows": qc["missing_top_position_ratio_rows"],
            }
        )
    if not states:
        raise ValueError("NO_VERIFIED_NATIVE_BTC_METRICS")
    native = {
        "states": states,
        "refs": refs,
        "strings": strings,
        "conflicts": conflicts,
        "times": sorted(states),
    }
    monthly, yearly = native_coverage({KEY: states}, {KEY: conflicts})
    return (
        native,
        {
            "sources": sources,
            "monthly": monthly,
            "yearly": [r for r in yearly if r["venue"] == "binance"],
            "duplicate_identical_or_conflicting_rows": duplicates,
            "conflicting_unique_labels": len(conflicts),
        },
        source_identity,
    )


def protected(t):
    # Match the existing R2 exclusion and its warmup; H39 is handled by registered periods.
    c = t - 60 * US
    return max(c - 86400 * US - 120 * US, epoch_us("2025-02-01T00:00:00Z")) < min(
        c, epoch_us("2026-02-01T00:00:00Z")
    )


def signal(x, log_oi, ratio):
    return x <= -0.01 and log_oi <= -0.02 and ratio >= 1.5


def origin_row(t, population, x, native, reg_sha):
    cutoff = t - 60 * US
    expected = cutoff - 600 * US
    states, conflicts, times = native["states"], native["conflicts"], native["times"]
    idx = bisect.bisect_right(times, expected) - 1
    label = times[idx] if idx >= 0 else None
    boundary = label != expected
    pred = label - 4 * HOUR if label is not None else None
    current, previous = states.get(label), states.get(pred)
    conflict = label in conflicts or pred in conflicts
    exact = previous is not None
    oi_present = current is not None and positive(current[0])
    ratio_present = current is not None and positive(current[3])
    is_protected = protected(t)
    oi_eligible = not is_protected and state_at_origin(states, times, conflicts, t, joint=False)
    z_eligible = not is_protected and state_at_origin(states, times, conflicts, t)
    x_eligible = bool(x and x["x_eligible"] and not is_protected)
    log_oi = math.log(current[0] / previous[0]) if oi_eligible else None
    ratio = current[3] if z_eligible else None
    paired = x_eligible and z_eligible
    x_condition = x["log_return_4h"] <= -0.01 if x_eligible else None
    z_condition = log_oi <= -0.02 and ratio >= 1.5 if z_eligible else None
    trigger = bool(paired and signal(x["log_return_4h"], log_oi, ratio))
    reasons = []
    if is_protected:
        reasons.append("KNOWN_EXCLUDED_FEATURE_WINDOW")
    if not x_eligible:
        reasons.append("FROZEN_R1_X_UNAVAILABLE_OR_INCOMPLETE")
    if boundary:
        reasons.append("SOURCE_CONTENT_GUARD_REJECTED_MISSING_OR_STALE_LABEL")
    if conflict:
        reasons.append("CONFLICTING_NATIVE_LABEL")
    if not oi_present:
        reasons.append("NATIVE_BASE_OI_MISSING")
    if not exact:
        reasons.append("EXACT_4H_PREDECESSOR_MISSING")
    elif not positive(previous[0]):
        reasons.append("PREDECESSOR_BASE_OI_MISSING")
    if not ratio_present:
        reasons.append("NATIVE_TOP_POSITION_RATIO_MISSING")
    if paired and not x_condition:
        reasons.append("X_THRESHOLD_NOT_MET")
    if paired and not z_condition:
        reasons.append("Z_THRESHOLD_NOT_MET")
    # Preserve raw timestamps and lineage even for rejected samples. Protected origins expose no values.
    row = {
        "population": population,
        "origin_utc": utc(t),
        "origin_us": t,
        "cutoff_us": cutoff,
        "expected_native_label_us": expected,
        "selected_native_label_us": label,
        "native_create_time": native["strings"].get(label),
        "content_upper_us": label + 300 * US if label is not None else None,
        "predecessor_label_us": pred,
        "predecessor_native_create_time": native["strings"].get(pred),
        "predecessor_content_upper_us": pred + 300 * US if exact else None,
        "native_archive_sha256": sorted(native["refs"].get(label, [])),
        "predecessor_archive_sha256": sorted(native["refs"].get(pred, [])),
        "base_open_interest": current[0] if current and not is_protected else None,
        "predecessor_base_open_interest": previous[0] if previous and not is_protected else None,
        "sum_toptrader_long_short_ratio": current[3] if current and not is_protected else None,
        "log_oi_4h": log_oi,
        "log_top_position_ratio": math.log(ratio) if ratio else None,
        "log_return_4h": x["log_return_4h"] if x_eligible else None,
        "x_source_ids": x["x_source_ids"] if x else [],
        "x_end_us": x["x_end_us"] if x else None,
        "x_eligible": x_eligible,
        "native_oi_present": bool(oi_present),
        "native_ratio_present": bool(ratio_present),
        "exact_4h_predecessor": exact,
        "boundary_rejected": boundary,
        "conflicting_label": conflict,
        "oi_only_eligible": bool(oi_eligible),
        "z_eligible": bool(z_eligible),
        "paired_xz_eligible": paired,
        "x_condition": x_condition,
        "z_condition": z_condition,
        "paired_baseline_action": "SHORT" if paired and x_condition else "NO_ACTION",
        "trigger": trigger,
        "diagnostic_action": "SHORT" if trigger else "NO_ACTION",
        "no_action_reasons": [] if trigger else reasons,
        "protected_window": is_protected,
        "receiver_pit": "PIT_UNKNOWN",
        "source_status": "SOURCE_NOT_ADMITTED",
        "executable": False,
        "registration_sha256": reg_sha,
    }
    validate_panel_row(row)
    return row


def validate_panel_row(row):
    if set(row) != PANEL_KEYS or row["executable"] is not False:
        raise ValueError("NO_OUTCOME_PANEL_SCHEMA_VIOLATION")
    if row["trigger"] and not row["paired_xz_eligible"]:
        raise ValueError("TRIGGER_WITHOUT_PAIRED_ELIGIBILITY")


COUNT_FIELDS = [
    "x_eligible",
    "native_oi_present",
    "native_ratio_present",
    "exact_4h_predecessor",
    "boundary_rejected",
    "conflicting_label",
    "oi_only_eligible",
    "z_eligible",
    "paired_xz_eligible",
    "trigger",
    "protected_window",
]


def summarize(rows):
    counts = Counter({"scheduled_origins": len(rows), **{k: 0 for k in COUNT_FIELDS}})
    reasons = Counter()
    for row in rows:
        counts.update({k: int(row[k]) for k in COUNT_FIELDS})
        reasons.update(row["no_action_reasons"])
    counts["paired_baseline_acted_hours"] = sum(
        r["paired_baseline_action"] == "SHORT" for r in rows
    )
    return {
        **dict(counts),
        "missing_x": len(rows) - counts["x_eligible"],
        "missing_native_oi": len(rows) - counts["native_oi_present"],
        "missing_native_ratio": len(rows) - counts["native_ratio_present"],
        "missing_exact_predecessor": len(rows) - counts["exact_4h_predecessor"],
        "no_action_reasons_nonexclusive": dict(sorted(reasons.items())),
    }


def episodes(rows):
    triggers = [{"t": r["origin_us"] // US} for r in rows if r["trigger"]]
    horizons = {}
    for h in (4, 8, 12, 24):
        m = EventClusterer.metrics(triggers, horizon_hours=h)
        # Do not repeat the existing helper's claim that non-overlap proves independence.
        m.pop("effective_sample_size", None)
        m.pop("decision", None)
        m["nonoverlap_episode_count"] = m["independent_episodes_count"]
        m["effective_weekly_blocks_count"] = m["weekly_blocks_count"]
        m["acted_origin_feasibility_floor_passed"] = (
            len(triggers) >= 30 and m["weekly_blocks_count"] >= 12
        )
        m["conservative_episode_floor_passed"] = m.pop("frozen_minimum_passed")
        m["meets_30_nonoverlap_episode_threshold"] = m.pop("meets_minimum_acted_origins")
        horizons[str(h)] = m
    primary = EventClusterer.cluster(triggers, horizon_hours=8)
    detail = [
        {
            "start_utc": e.start_utc,
            "end_utc": e.end_utc,
            "trigger_hours": e.trigger_count,
            "trigger_origins_utc": [utc(t["t"] * US) for t in e.triggers],
            "iso_week": f"{e.iso_year_week[0]}-W{e.iso_year_week[1]:02d}",
        }
        for e in primary
    ]
    year_triggers = Counter(utc(r["t"] * US)[:4] for r in triggers)
    year_episodes = Counter(e.start_utc[:4] for e in primary)
    weekly_triggers = Counter()
    for r in triggers:
        dt = datetime.fromtimestamp(r["t"], UTC).isocalendar()
        weekly_triggers[f"{dt.year}-W{dt.week:02d}"] += 1
    weekly_episodes = Counter(f"{e.iso_year_week[0]}-W{e.iso_year_week[1]:02d}" for e in primary)
    regime = Counter()
    regimes = registration({})["episodes"]["regime_proxies"]
    for year, count in year_triggers.items():
        regime[regimes.get(year, year + "_calendar")] += count
    return {
        "horizons": horizons,
        "primary_8h_episodes": detail,
        "trigger_hours_by_year": dict(sorted(year_triggers.items())),
        "episodes_by_year": dict(sorted(year_episodes.items())),
        "trigger_hours_by_iso_week": dict(sorted(weekly_triggers.items())),
        "episodes_by_iso_week": dict(sorted(weekly_episodes.items())),
        "effective_weekly_blocks_by_iso_year": dict(
            sorted(Counter(w[:4] for w in weekly_episodes).items())
        ),
        "trigger_hours_by_fixed_calendar_regime_proxy": dict(sorted(regime.items())),
        "max_year_trigger_share": max(year_triggers.values(), default=0) / len(triggers)
        if triggers
        else None,
        "interpretation": "Non-overlapping episodes and weekly block counts are descriptive feasibility diagnostics, not independence or statistical-power proof.",
    }


def calculate(r1_rows, native, reg_sha):
    panels, summaries, episode_reports = {}, {}, {}
    monthly, yearly = [], []
    for population in ("A_R1_2026_REPRODUCTION", "C_EXPLORATORY_2021_2025"):
        left, right = map(epoch_us, PERIODS[population])
        rows = [
            origin_row(c + 60 * US, population, r1_rows.get(c + 60 * US), native, reg_sha)
            for c in range(left, right, HOUR)
        ]
        panels[population] = rows
        summaries[population] = summarize(rows)
        episode_reports[population] = episodes(rows)
        for width, output in [(7, monthly), (4, yearly)]:
            groups = defaultdict(list)
            for row in rows:
                groups[row["origin_utc"][:width]].append(row)
            output.extend(
                {"population": population, "period": period, **summarize(items)}
                for period, items in sorted(groups.items())
            )
    return (
        panels,
        {"by_population": summaries, "monthly": monthly, "yearly": yearly},
        episode_reports,
    )


def frozen_reproduction(r1_rows):
    left, right = map(epoch_us, PERIODS["A_R1_2026_REPRODUCTION"])
    z_rows, triggers = [], []
    for t, r in r1_rows.items():
        if not left <= t < right or not r["x_eligible"] or r["z_status"] != "OBSERVED":
            continue
        z_rows.append(r)
        if r["log_return_4h"] <= -0.01 and r["z"][0] <= -0.02 and r["z"][1] >= math.log(1.5):
            triggers.append({"t": t // US})
    return {
        "paired_eligible_origins": len(z_rows),
        "trigger_hours": len(triggers),
        "episodes_8h": len(EventClusterer.cluster(triggers, horizon_hours=8)),
        "weekly_blocks_8h": EventClusterer.metrics(triggers, horizon_hours=8)[
            "weekly_blocks_count"
        ],
    }


def reconciliation(r1_rows, native, report):
    eligible = [t for t, row in r1_rows.items() if row["x_eligible"] and not protected(t)]
    counts = {
        "X_available": len(eligible),
        "oi_only_conservative": sum(
            state_at_origin(native["states"], native["times"], native["conflicts"], t, joint=False)
            for t in eligible
        ),
        "joint_conservative": sum(
            state_at_origin(native["states"], native["times"], native["conflicts"], t)
            for t in eligible
        ),
    }
    reference = read_json(report / "comparison_with_BLINE_R1.json")["R2_matched_existing_X"]
    if any(reference[k] != v for k, v in counts.items()):
        raise ValueError("DELIVERY_ELIGIBILITY_RECONCILIATION_FAILED:" + str(counts))
    return {
        "recomputed_from_frozen_X_and_verified_native_metrics": counts,
        "delivery_reference": reference,
        "scope_explanation": "33036 joint and 40700 OI-only are multi-year frozen-X eligibility denominators, not trigger counts. 4387 is the old R2 2026-focused Z denominator from its frozen-R1-plus-September panel. Different populations are not a data-integrity failure.",
    }


def code_identity():
    paths = list(Path(__file__).parent.glob("*.py"))
    paths += list((REPO / "tests/research/bline_r2_expanded_oi").glob("*.py"))
    paths += [
        REPO / p
        for p in [
            "scripts/data/bline_r2/quality.py",
            "scripts/data/bline_r2/report.py",
            "tools/data/qc.py",
            "scripts/research/bline_multiyear/coverage_extension.py",
            "scripts/research/bline_multiyear/contracts.py",
        ]
    ]
    return {str(p): {"sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(paths)}


def storage(root):
    paths = [p for p in root.rglob("*") if p.is_file()]
    return {
        "logical_bytes": sum(p.stat().st_size for p in paths),
        "allocated_bytes": sum(p.stat().st_blocks * 512 for p in paths),
        "files": len(paths),
    }


def run_tests(output):
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/research/bline_r2_expanded_oi/",
        "-p",
        "no:cacheprovider",
        "--tb=short",
        f"--junitxml={output / 'focused_tests.xml'}",
    ]
    env = {**os.environ, "PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(cmd, cwd=REPO, env=env, text=True, capture_output=True, check=False)
    write_json(
        output / "focused_test_receipt.json",
        {
            "command": shlex.join(cmd),
            "environment": {"PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1"},
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "junit_sha256": digest(output / "focused_tests.xml")
            if (output / "focused_tests.xml").exists()
            else None,
        },
    )
    if result.returncode:
        raise ValueError("FOCUSED_TESTS_FAILED:" + result.stdout[-3000:])


def comparison_report(r1_rows, native, coverage, episode_report, old, report):
    frozen = frozen_reproduction(r1_rows)
    published = read_json(old / "before_after_eligibility.json")
    expected = published["before_r1"]
    if (frozen["paired_eligible_origins"], frozen["trigger_hours"], frozen["episodes_8h"]) != (
        expected["oi_z_eligible"],
        expected["oi_triggers"],
        expected["oi_independent_episodes_8h"],
    ):
        raise ValueError("ORIGINAL_R1_REPRODUCTION_MISMATCH")
    return {
        "A_original_frozen_R1_reproduced": frozen,
        "A_new_native_Z_on_identical_frozen_X": {
            **coverage["by_population"]["A_R1_2026_REPRODUCTION"],
            "episodes_8h": episode_report["A_R1_2026_REPRODUCTION"]["horizons"]["8"],
        },
        "B_existing_R2_report_reference_only": published["after_r2"],
        "B_limitation": "September X is not in frozen R1; existing R2 reference is hash-bound but not independently rebuilt here. No new X or outcomes accessed.",
        "C_new_exploratory_extension": {
            **coverage["by_population"]["C_EXPLORATORY_2021_2025"],
            "episodes_8h": episode_report["C_EXPLORATORY_2021_2025"]["horizons"]["8"],
        },
        "delivery_reconciliation": reconciliation(r1_rows, native, report),
    }


def decision_text(coverage, episode_report):
    primary = episode_report["C_EXPLORATORY_2021_2025"]["horizons"]["8"]
    return (
        f"R2_OI_EXPANDED_SAMPLE_READY\n\n"
        f"The exploratory 2021–2025 schedule contains {coverage['by_population']['C_EXPLORATORY_2021_2025']['paired_xz_eligible']} paired X/Z origins, "
        f"{primary['total_trigger_hours']} frozen-formula trigger hours, "
        f"{primary['nonoverlap_episode_count']} non-overlapping 8h episodes and "
        f"{primary['weekly_blocks_count']} episode-start ISO weekly blocks.\n\n"
        f"30 acted-origin / 12 weekly-block floor: {primary['acted_origin_feasibility_floor_passed']}. "
        f"Additional conservative 30 episode / 12 block floor: {primary['conservative_episode_floor_passed']}. "
        "Neither floor establishes independence, power, utility or alpha. Calendar concentration and the missing 2022 ratios must remain visible. "
        "February–December 2025 has no frozen X and remains excluded.\n\n"
        "Next measurable decision: independently audit the hash-bound source mapping, 8h episode list, year/weekly concentration and paired missingness. "
        "Before any outcome scope, resolve receiver-first-known PIT and source admission with evidence; require a separate authorization and registration for any later study. "
        "No threshold, direction, horizon or exit change is supported by these counts.\n\n"
        + " / ".join(LABELS)
        + "\n"
    )


def build(args):
    began = time.monotonic()
    r1, r2, out = args.r1_root.resolve(), args.r2_root.resolve(), args.output_root.resolve()
    old = (
        args.existing_r2_root.resolve()
        if args.existing_r2_root
        else r1.parent / "research-bline-r2"
    )
    output_guard(out, [r1, r2, old])
    if (out / "manifest.json").exists():
        return verify(argparse.Namespace(output_root=out))
    before = storage(out)
    report, identity = identities(r1, r2, old)
    # Must precede load_r1, load_native, reproduction and ALL new trigger calculations.
    reg = registration(identity)
    reg_sha = freeze(out, reg)
    freeze_receipt = out / "registration_freeze_receipt.json"
    if freeze_receipt.exists():
        if read_json(freeze_receipt)["registration_sha256"] != reg_sha:
            raise ValueError("FREEZE_RECEIPT_REGISTRATION_MISMATCH")
    else:
        write_json(
            freeze_receipt,
            {
                "registration_sha256": reg_sha,
                "frozen_at_utc": datetime.now(UTC).isoformat(),
                "trigger_features_read_before_freeze": False,
                "new_trigger_counts_calculated_before_freeze": False,
            },
        )
    r1_rows = load_r1(r1 / "features-release/feature_panel.jsonl")
    native, native_report, source_identity = load_native(r2, report)
    write_json(out / "source_coverage_and_lineage.json", native_report)
    panels, coverage, episode_report = calculate(r1_rows, native, reg_sha)
    for population, rows in panels.items():
        with (out / (population + ".jsonl")).open("xb") as stream:
            for row in rows:
                stream.write(canonical(row))
    write_json(out / "origin_coverage_and_missingness.json", coverage)
    write_json(out / "event_episodes.json", episode_report)
    write_json(
        out / "before_after_comparison.json",
        comparison_report(r1_rows, native, coverage, episode_report, old, report),
    )
    # Rehash every identity at the end to prove inputs did not change during the join.
    all_inputs = {**identity, **source_identity, **code_identity()}
    for p, item in all_inputs.items():
        if digest(Path(p)) != item["sha256"]:
            raise ValueError("INPUT_CHANGED_DURING_BUILD:" + p)
    write_json(
        out / "input_identity.json",
        {
            "r1_root": str(r1),
            "r2_root": str(r2),
            "existing_r2_root": str(old),
            "report_root": str(report),
            "files": all_inputs,
            "preservation": "All used frozen R1/R2 artifacts and verified BTC metrics rehashed unchanged; source roots opened read-only.",
        },
    )
    run_tests(out)
    (out / "NEXT_DECISION.md").write_text(decision_text(coverage, episode_report))
    after = storage(out)
    write_json(
        out / "run_receipt.json",
        {
            "task": TASK,
            "status": "R2_OI_EXPANDED_SAMPLE_READY",
            "labels": LABELS,
            "registration_sha256": reg_sha,
            "elapsed_seconds": round(time.monotonic() - began, 3),
            "commands": [
                shlex.join(
                    [
                        sys.executable,
                        "-m",
                        "scripts.research.bline_r2_expanded_oi.pipeline",
                        *sys.argv[1:],
                    ]
                ),
                f"python3 -m scripts.research.bline_r2_expanded_oi.pipeline verify --output-root {shlex.quote(str(out))}",
            ],
            "storage_before": before,
            "storage_after_data_tests_before_receipt_and_manifest": after,
            "storage_delta_logical_bytes_at_snapshot": after["logical_bytes"]
            - before["logical_bytes"],
            "real_outcomes_computed": 0,
            "downloads": 0,
            "protected_databases_opened": 0,
            "R1_and_used_R2_inputs_unchanged": True,
        },
    )
    write_json(
        out / "manifest.json",
        {
            "schema": "bline-r2-expanded-oi.sha256.v1",
            "registration_sha256": reg_sha,
            "artifacts": {
                p.name: {"sha256": digest(p), "bytes": p.stat().st_size}
                for p in sorted(out.iterdir())
                if p.is_file() and p.name != "manifest.json"
            },
        },
    )
    return verify(argparse.Namespace(output_root=out))


def verify(args):
    out = args.output_root.resolve()
    manifest = read_json(out / "manifest.json")
    actual = {p.name for p in out.iterdir() if p.is_file() and p.name != "manifest.json"}
    if actual != set(manifest["artifacts"]):
        raise ValueError("OUTPUT_FILE_SET_CHANGED")
    for name, identity in manifest["artifacts"].items():
        path = out / name
        if (
            Path(name).name != name
            or digest(path) != identity["sha256"]
            or path.stat().st_size != identity["bytes"]
        ):
            raise ValueError("OUTPUT_SHA_MISMATCH:" + name)
    identity = read_json(out / "input_identity.json")
    for p, item in identity["files"].items():
        if digest(Path(p)) != item["sha256"] or Path(p).stat().st_size != item["bytes"]:
            raise ValueError("INPUT_SHA_MISMATCH:" + p)
    reg = read_json(out / "exploratory_registration.v1.json")
    if (
        reg != registration(reg["input_binding"])
        or digest(out / "exploratory_registration.v1.json") != manifest["registration_sha256"]
    ):
        raise ValueError("FROZEN_REGISTRATION_MISMATCH")
    # Independently rebuild all native joins and event counts from the explicit inputs.
    native, source_report, _ = load_native(Path(identity["r2_root"]), Path(identity["report_root"]))
    r1_rows = load_r1(Path(identity["r1_root"]) / "features-release/feature_panel.jsonl")
    panels, coverage, episode_report = calculate(r1_rows, native, manifest["registration_sha256"])
    for population, rows in panels.items():
        with (out / (population + ".jsonl")).open("rb") as stream:
            for expected in rows:
                raw = next(stream, None)
                if raw != canonical(expected):
                    raise ValueError("PANEL_REPRODUCTION_MISMATCH:" + population)
            if next(stream, None) is not None:
                raise ValueError("EXTRA_PANEL_ROWS")
    for name, expected in [
        ("origin_coverage_and_missingness.json", coverage),
        ("event_episodes.json", episode_report),
        ("source_coverage_and_lineage.json", source_report),
        (
            "before_after_comparison.json",
            comparison_report(
                r1_rows,
                native,
                coverage,
                episode_report,
                Path(identity["existing_r2_root"]),
                Path(identity["report_root"]),
            ),
        ),
    ]:
        if read_json(out / name) != expected:
            raise ValueError("DIAGNOSTIC_REPRODUCTION_MISMATCH:" + name)
    if (out / "NEXT_DECISION.md").read_text() != decision_text(coverage, episode_report):
        raise ValueError("NEXT_DECISION_REPRODUCTION_MISMATCH")
    if read_json(out / "focused_test_receipt.json")["exit_code"] != 0:
        raise ValueError("MISSING_PASSING_TEST_RECEIPT")
    result = {
        "status": "R2_OI_EXPANDED_SAMPLE_READY",
        "verified": True,
        "registration_sha256": manifest["registration_sha256"],
        "exploratory": coverage["by_population"]["C_EXPLORATORY_2021_2025"],
        "primary_8h": episode_report["C_EXPLORATORY_2021_2025"]["horizons"]["8"],
        "storage_current": storage(out),
        "labels": LABELS,
    }
    print(json.dumps(result, sort_keys=True))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--r1-root", required=True, type=Path)
    b.add_argument("--r2-root", required=True, type=Path)
    b.add_argument("--existing-r2-root", type=Path)
    b.add_argument("--output-root", required=True, type=Path)
    v = sub.add_parser("verify")
    v.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        (build if args.command == "build" else verify)(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {"status": "R2_OI_EXPANDED_SAMPLE_BLOCKED", "error": str(exc), "labels": LABELS}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
