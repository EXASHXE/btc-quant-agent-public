"""preregister/build/verify one offline feature-feasibility experiment."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

from scripts.research.bline_multiyear.coverage_extension import EventClusterer
from scripts.research.bline_r2_expanded_oi.pipeline import load_r1

from .adapter import aligned_window, displacement, load_month, month_bounds
from .contracts import (
    HOUR,
    LABELS,
    MINUTE,
    OI,
    OUTPUT,
    R1,
    R2,
    REPO,
    TASK,
    canonical,
    digest,
    freeze,
    immutable,
    iso,
    novelty,
    protected,
    registration,
)

PANEL_KEYS = {
    "schema",
    "origin_us",
    "origin_utc",
    "cutoff_us",
    "month",
    "year",
    "x_eligible",
    "log_return_4h",
    "x_end_us",
    "x_source_ids",
    "z_observable",
    "paired_eligible",
    "source_ids",
    "source_raw_sha256_pins",
    "native_window",
    "first_interval_open_us",
    "last_interval_end_us",
    "features",
    "X_condition",
    "Z_condition",
    "baseline_action",
    "candidate_action",
    "no_action",
    "no_action_reasons",
    "primary_no_action_reason",
    "protected_window",
    "source_status",
    "receiver_pit",
    "executable",
    "registration_sha256",
}


def read(path):
    return json.loads(path.read_text())


def assert_preserved(out):
    p = read(out / "preflight_receipt.json")
    if (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        != p["head"]
    ):
        raise ValueError("LOCAL_HEAD_CHANGED")
    if subprocess.check_output(["git", "show-ref"], cwd=REPO, text=True) != p["git_refs"]:
        raise ValueError("BRANCH_REFS_CHANGED")
    for name, expected in {
        **{str(REPO / k): v for k, v in p["owner_hashes"].items()},
        **p["old_research_hashes"],
    }.items():
        if digest(Path(name)) != expected:
            raise ValueError("OWNER_OR_R1_R2_CHANGED:" + name)
    binding = read(out / "input_binding.json")
    for name, item in binding["files"].items():
        if digest(Path(name)) != item["sha256"] or Path(name).stat().st_size != item["bytes"]:
            raise ValueError("INPUT_SHA_CHANGED:" + name)
    for name, expected in binding["authority_files"].items():
        if digest(out / name) != expected:
            raise ValueError("AUTHORITY_SHA_CHANGED")
    return {
        "owner_files_SHA_unchanged": len(p["owner_hashes"]),
        "old_research_files_SHA_unchanged": len(p["old_research_hashes"]),
        "input_file_hashes_verified": len(binding["files"]),
        "HEAD_and_refs_unchanged": True,
    }


def preregister(out):
    binding = {
        "input_binding_sha256": digest(out / "input_binding.json"),
        "preflight_sha256": digest(out / "preflight_receipt.json"),
    }
    value = registration(binding)
    h = freeze(out, value)
    receipt = read(out / "registration_freeze_receipt.json")
    if (
        receipt["registration_sha256"] != h
        or receipt["candidate_feature_values_read"]
        or receipt["candidate_specific_counts_calculated"]
        or receipt["new_signal_distributions_inspected"]
    ):
        raise ValueError("REGISTRATION_NOT_FROZEN_BEFORE_NEW_COUNTS")
    return h


def panel_row(origin, x, channels, conflicts, refs, reg_sha):
    if origin % HOUR != MINUTE:
        raise ValueError("FIXED_HH01_UTC_ORIGIN_REQUIRED")
    cutoff = origin - MINUTE
    excluded = protected(origin)
    reasons = ["KNOWN_EXCLUDED_FEATURE_WINDOW"] if excluded else []
    aligned = None
    if not excluded:
        aligned, missing = aligned_window(*channels, *conflicts, cutoff)
        reasons.extend(missing)
    x_ok = bool(
        x
        and x["x_eligible"]
        and not excluded
        and isinstance(x.get("x_end_us"), int)
        and x["x_end_us"] < cutoff
        and isinstance(x.get("log_return_4h"), (int, float))
        and math.isfinite(x["log_return_4h"])
    )
    if not x_ok:
        reasons.append("FROZEN_R1_X_UNAVAILABLE_OR_INCOMPLETE")
    features, z_reasons = displacement(*aligned) if aligned else (None, [])
    z_ok = aligned is not None
    paired = x_ok and z_ok
    x_condition = bool(x_ok and x["log_return_4h"] <= -0.01)
    z_condition = bool(features and features["Z_condition"])
    baseline = -int(paired and x_condition)
    action = baseline * int(z_condition)
    if x_ok and not x_condition:
        reasons.append("X_THRESHOLD_NOT_MET")
    reasons.extend(z_reasons)
    source_ids, raw_pins = {}, {}
    ends = [cutoff - (16 - j) * MINUTE for j in range(16)]
    for product, entries in zip(["SPOT", "USD_M_PERPETUAL"], refs):
        pairs = {item for t in ends for item in entries.get(t, set())} if not excluded else set()
        source_ids[product] = sorted({item[0] for item in pairs})
        raw_pins[product] = sorted({item[1] for item in pairs})
    row = {
        "schema": "bline-r3.feature-only.v1",
        "origin_us": origin,
        "origin_utc": iso(origin),
        "cutoff_us": cutoff,
        "month": iso(origin)[:7],
        "year": iso(origin)[:4],
        "x_eligible": x_ok,
        "log_return_4h": x["log_return_4h"] if x_ok else None,
        "x_end_us": x["x_end_us"] if x_ok else None,
        "x_source_ids": x["x_source_ids"] if x_ok else [],
        "z_observable": z_ok,
        "paired_eligible": paired,
        "source_ids": source_ids,
        "source_raw_sha256_pins": raw_pins,
        "native_window": {
            "expected_closes_per_source": 16,
            "first_endpoint_us": ends[0],
            "last_endpoint_us": ends[-1],
            "interval": "1m",
            "timestamp_semantics": "native open; canonical end=open+1m; event=end",
        },
        "first_interval_open_us": ends[0] - MINUTE,
        "last_interval_end_us": ends[-1],
        "features": features,
        "X_condition": x_condition,
        "Z_condition": z_condition,
        "baseline_action": baseline,
        "candidate_action": action,
        "no_action": action == 0,
        "no_action_reasons": sorted(set(reasons)),
        "primary_no_action_reason": reasons[0] if action == 0 and reasons else None,
        "protected_window": excluded,
        "source_status": "SOURCE_NOT_ADMITTED",
        "receiver_pit": "PIT_UNKNOWN",
        "executable": False,
        "registration_sha256": reg_sha,
    }
    validate_panel(row)
    return row


def validate_panel(row):
    if set(row) != PANEL_KEYS or row["schema"] != "bline-r3.feature-only.v1" or row["executable"]:
        raise ValueError("NO_OUTCOME_OUTPUT_SCHEMA_REQUIRED")
    if row["features"] is not None and set(row["features"]) != {
        "spot_log_displacement",
        "perp_log_displacement",
        "first_spot_cross_index",
        "first_perp_cross_index",
        "initial_relative_displacement",
        "remaining_fraction",
        "Z_condition",
    }:
        raise ValueError("NO_OUTCOME_NESTED_OUTPUT_SCHEMA_REQUIRED")
    if row["last_interval_end_us"] >= row["cutoff_us"]:
        raise ValueError("OUTPUT_FUTURE_BAR_LEAK")
    if row["protected_window"] and (
        row["paired_eligible"] or row["candidate_action"] or row["features"] is not None
    ):
        raise ValueError("PROTECTED_FEATURE_ACCESS")


def summarize(rows):
    c = Counter(scheduled_origins=len(rows))
    reasons, primary = Counter(), Counter()
    for r in rows:
        for field in [
            "x_eligible",
            "z_observable",
            "paired_eligible",
            "protected_window",
            "no_action",
        ]:
            c[field] += int(r[field])
        c["baseline_trigger_hours"] += r["baseline_action"] != 0
        c["candidate_trigger_hours"] += r["candidate_action"] != 0
        c["source_ineligible_origins"] += not r["z_observable"]
        reasons.update(r["no_action_reasons"])
        if r["no_action"]:
            primary[r["primary_no_action_reason"]] += 1
    return {
        **dict(c),
        "source_ineligibility_proportion": c["source_ineligible_origins"] / len(rows)
        if rows
        else None,
        "paired_eligibility_proportion": c["paired_eligible"] / len(rows) if rows else None,
        "no_action_reasons_nonexclusive": dict(sorted(reasons.items())),
        "primary_no_action_reasons_exclusive": dict(sorted(primary.items())),
    }


def episodes(rows, arm, horizon):
    triggers = [{"t": r["origin_us"] // 1_000_000} for r in rows if r[arm + "_action"]]
    clusters = EventClusterer.cluster(triggers, horizon)
    starts = [e.start_utc for e in clusters]
    by_year, by_month = Counter(s[:4] for s in starts), Counter(s[:7] for s in starts)
    weeks = sorted({f"{e.iso_year_week[0]}-W{e.iso_year_week[1]:02}" for e in clusters})
    eligible = sum(r["paired_eligible"] for r in rows)
    by_trigger_year = Counter(r["year"] for r in rows if r[arm + "_action"])
    return {
        "arm": arm,
        "horizon_hours": horizon,
        "trigger_hours": len(triggers),
        "nonoverlap_episodes": len(clusters),
        "episode_start_ISO_weeks": weeks,
        "weekly_blocks": len(weeks),
        "paired_eligible_hourly_origins": eligible,
        "trigger_hours_per_eligible_48h": 48 * len(triggers) / eligible if eligible else None,
        "episodes_per_eligible_48h": 48 * len(clusters) / eligible if eligible else None,
        "by_year_episodes": dict(sorted(by_year.items())),
        "by_month_episodes": dict(sorted(by_month.items())),
        "by_year_triggers": dict(sorted(by_trigger_year.items())),
        "maximum_year_trigger_share": max(by_trigger_year.values(), default=0) / len(triggers)
        if triggers
        else None,
        "episode_coverage_trigger_hours": sum(e.trigger_count for e in clusters),
        "episodes": [
            {
                "start_us": e.start_t * 1_000_000,
                "end_exclusive_us": e.end_t * 1_000_000,
                "start_utc": e.start_utc,
                "end_exclusive_utc": e.end_utc,
                "ISO_week": f"{e.iso_year_week[0]}-W{e.iso_year_week[1]:02}",
                "trigger_origins_us": [r["t"] * 1_000_000 for r in e.triggers],
            }
            for e in clusters
        ],
        "interpretation": "Nonoverlap calendar blocks only, NOT proven independent events, effective statistical N, power or returns",
    }


def feasibility(summary, ep, definition):
    g = definition["gate"]
    conditions = {
        "paired_physical_coverage": summary["paired_eligibility_proportion"]
        >= g["minimum_paired_fraction"],
        "minimum_trigger_hours": ep["trigger_hours"] >= g["minimum_trigger_hours"],
        "minimum_nonoverlap_8h_episodes": ep["nonoverlap_episodes"]
        >= g["minimum_nonoverlap_8h_episodes"],
        "minimum_episode_start_weeks": ep["weekly_blocks"] >= g["minimum_episode_start_weeks"],
        "calendar_year_coverage": len(ep["by_year_episodes"]) >= g["minimum_years_with_episodes"],
        "year_concentration": ep["maximum_year_trigger_share"] is not None
        and ep["maximum_year_trigger_share"] <= g["maximum_year_trigger_share"],
        "opportunity_density": ep["episodes_per_eligible_48h"] is not None
        and g["episodes_per_eligible_48h_range"][0]
        <= ep["episodes_per_eligible_48h"]
        <= g["episodes_per_eligible_48h_range"][1],
    }
    return {
        "status": "R3_MECHANISM_FEASIBILITY_READY"
        if all(conditions.values())
        else "R3_MECHANISM_FEASIBILITY_NO_GO",
        "checks": conditions,
        "exact_falsifiers": [k for k, v in conditions.items() if not v],
        "structural_novelty": "Distinct ordered minute observable; synthetic counterexample in tests",
        "causal_clock": "Native event-time only, all interval ends strictly before cutoff",
        "structural_causality_identified": False,
        "source_or_receiver_PIT_admitted": False,
        "labels": LABELS,
        "thresholds_changed_after_counts": False,
        "real_returns_read_or_computed": 0,
    }


def calculate(out, reg_sha):
    binding = read(out / "input_binding.json")
    receipts = binding["native_sources"]
    x = load_r1(R1 / "features-release/feature_panel.jsonl")
    rows, source_coverage = [], []
    carry, carry_conflicts, carry_refs = [{}, {}], [set(), set()], [{}, {}]
    for year in range(2021, 2025):
        for month_number in range(1, 13):
            month = f"{year}-{month_number:02}"
            left, right = month_bounds(month)
            channels, conflicts, references = [], [], []
            for i, product in enumerate(["SPOT", "USD_M_PERPETUAL"]):
                bars, bad, refs, source = load_month(receipts, product, month, left, right)
                source_coverage.append(source)
                channels.append({**carry[i], **bars})
                conflicts.append(carry_conflicts[i] | bad)
                references.append({**carry_refs[i], **refs})
                carry[i] = {t: b for t, b in bars.items() if t >= right - 17 * MINUTE}
                carry_conflicts[i] = {t for t in bad if t >= right - 17 * MINUTE}
                carry_refs[i] = {t: v for t, v in refs.items() if t >= right - 17 * MINUTE}
            for cutoff in range(left, right, HOUR):
                origin = cutoff + MINUTE
                rows.append(
                    panel_row(origin, x.get(origin), channels, conflicts, references, reg_sha)
                )
    yearly = [
        {"year": str(y), **summarize([r for r in rows if r["year"] == str(y)])}
        for y in range(2021, 2025)
    ]
    monthly = [
        {"month": f"{y}-{m:02}", **summarize([r for r in rows if r["month"] == f"{y}-{m:02}"])}
        for y in range(2021, 2025)
        for m in range(1, 13)
    ]
    episode = {
        arm: {str(h): episodes(rows, arm, h) for h in [4, 8, 12, 24]}
        for arm in ["baseline", "candidate"]
    }
    summary = summarize(rows)
    return rows, {"total": summary, "yearly": yearly, "monthly": monthly}, source_coverage, episode


def prior_comparison(summary, eps):
    # The R2 episode file contains the EXTENDED OI population (10/4/4).
    # Only the hash-pinned before_r1 snapshot describes frozen R1 (4/2/2).
    before = read(R2 / "before_after_eligibility.json")["before_r1"]
    old = {
        candidate: {
            "8h": {
                "total_trigger_hours": before[prefix + "_triggers"],
                "independent_episodes_count": before[prefix + "_independent_episodes_8h"],
                "weekly_blocks_count": before[prefix + "_weekly_blocks"],
            }
        }
        for candidate, prefix in [("candidate_funding", "funding"), ("candidate_oi", "oi")]
    }
    expanded = read(OI / "event_episodes.json")["C_EXPLORATORY_2021_2025"]["horizons"]["8"]
    counts = read(R1 / "completion-final/COMPLETION_RECEIPT.json")["BTC_binance"]
    if (
        before["funding_z_eligible"] != counts["funding_premium_eligible"]
        or before["oi_z_eligible"] != counts["OI_eligible"]
    ):
        raise ValueError("FROZEN_R1_REFERENCE_POPULATION_MISMATCH")
    population = read(OI / "origin_coverage_and_missingness.json")["by_population"][
        "C_EXPLORATORY_2021_2025"
    ]
    prior = []
    for name, item, denominator in [
        (
            "frozen_R1_funding_premium",
            old["candidate_funding"]["8h"],
            counts["funding_premium_eligible"],
        ),
        ("frozen_R1_OI", old["candidate_oi"]["8h"], counts["OI_eligible"]),
        ("registered_R2_expanded_OI_C", expanded, population["paired_xz_eligible"]),
    ]:
        n = item["independent_episodes_count"]
        prior.append(
            {
                "name": name,
                "trigger_hours": item["total_trigger_hours"],
                "nonoverlap_8h_episodes": n,
                "weekly_blocks": item["weekly_blocks_count"],
                "paired_origins": denominator,
                "episodes_per_eligible_48h": n * 48 / denominator,
            }
        )
    return {
        "R3_summary": summary["total"],
        "R3_exact_paired_comparator_8h": eps["baseline"]["8"],
        "R3_candidate_8h": eps["candidate"]["8"],
        "frozen_prior_reference": prior,
        "warning": "R1/R2 native source/date scopes differ; reference densities are not paired causal utility comparisons",
        "source_pins": {"R1": str(R1), "R2": str(R2), "R2_OI": str(OI)},
    }


def next_decision(verdict, eps):
    e = eps["candidate"]["8"]
    return (
        f"# {verdict['status']}\n\n"
        f"{e['paired_eligible_hourly_origins']} paired eligible hourly origins; {e['trigger_hours']} fixed-formula triggers; "
        f"{e['nonoverlap_episodes']} nonoverlapping 8h episodes; {e['weekly_blocks']} episode-start ISO weeks.\n\n"
        f"Episodes per eligible 48h: {e['episodes_per_eligible_48h']}; frozen band [0.5, 2.0]. "
        f"Exact failed feasibility checks: {verdict['exact_falsifiers']}.\n\n"
        "STOP this frozen candidate if any feasibility gate fails. Do not change its thresholds, clock, direction or exits "
        "to obtain a pass. A separate mechanism requires genuinely new observable evidence and a new registration. "
        "No outcome study or additional downloads are authorized.\n\n"
        "Spot-first native close crossings identify temporal order on an observed minute grid only. "
        "They do not identify a structural cause, receiver-first-known timing or 4–24h predictive utility. "
        "Exposed 2021–2024 data remain descriptive development.\n\n" + " / ".join(LABELS) + "\n"
    )


def code_hashes():
    paths = list(Path(__file__).parent.glob("*.py"))
    paths += list((REPO / "tests/research/bline_r3_price_discovery").glob("*.py"))
    paths += [
        REPO / p
        for p in [
            "scripts/research/bline_r2_expanded_oi/pipeline.py",
            "scripts/research/bline_r2_expanded_oi/contracts.py",
            "scripts/research/bline_multiyear/contracts.py",
            "scripts/research/bline_multiyear/coverage_extension.py",
            "scripts/data/catalog/normalize.py",
        ]
    ]
    return {str(p.relative_to(REPO)): digest(p) for p in sorted(paths)}


def write_csv(path, rows):
    fields = sorted({k for r in rows for k, v in r.items() if not isinstance(v, (dict, list))})
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(out):
    if (out / "manifest.json").exists():
        return verify(out)
    reg_sha = preregister(out)
    preservation = assert_preserved(out)
    rows, summary, coverage, episode = calculate(out, reg_sha)
    verdict = feasibility(
        summary["total"], episode["candidate"]["8"], read(out / "exploratory_registration.v1.json")
    )
    data = {
        "origin_coverage_and_missingness.json": summary,
        "source_month_coverage.json": coverage,
        "episode_tables.json": episode,
        "feasibility_verdict.json": verdict,
        "comparison_with_frozen_priors.json": prior_comparison(summary, episode),
        "evidence_vs_prior_novelty.json": novelty(),
    }
    with (out / "feature_panel.jsonl").open("xb") as stream:
        for row in rows:
            stream.write(canonical(row))
    for name, value in data.items():
        immutable(out / name, value)
    for name, table in [
        ("yearly_counts.csv", summary["yearly"]),
        ("monthly_counts.csv", summary["monthly"]),
    ]:
        write_csv(out / name, table)
    with (out / "NEXT_DECISION.md").open("x") as stream:
        stream.write(next_decision(verdict, episode))
    tests = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/research/bline_r3_price_discovery/",
        "-p",
        "no:cacheprovider",
        "--tb=short",
        "--basetemp=tests/research/bline_r3_price_discovery/.pytest-tmp",
    ]
    lint = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--no-cache",
        "scripts/research/bline_r3_price_discovery",
        "tests/research/bline_r3_price_discovery",
    ]
    receipts = []
    for command in [tests, lint]:
        import os

        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src:."}
        run = subprocess.run(
            command, cwd=REPO, env=env, text=True, capture_output=True, check=False
        )
        receipts.append(
            {
                "command": command,
                "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src:."},
                "exit_code": run.returncode,
                "stdout": run.stdout,
                "stderr": run.stderr,
            }
        )
        if run.returncode:
            raise ValueError("FOCUSED_VALIDATION_FAILED:" + run.stdout + run.stderr)
    immutable(out / "command_test_receipts.json", receipts)
    preservation = assert_preserved(out)
    immutable(
        out / "run_receipt.json",
        {
            "task": TASK,
            "registration_sha256": reg_sha,
            "labels": LABELS,
            "code_sha256": code_hashes(),
            "preservation": preservation,
            "network_downloads": 0,
            "protected_outcome_or_SQLite_payloads_read": 0,
            "real_return_labels_or_PnL_computed": 0,
            "threshold_search_budget_used": 0,
            "status": verdict["status"],
            "commands": [
                f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 -m scripts.research.bline_r3_price_discovery.pipeline {a} --output-root {out}"
                for a in ["preregister", "build", "verify"]
            ],
        },
    )
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json")
    immutable(
        out / "manifest.json",
        {
            "task": TASK,
            "registration_sha256": reg_sha,
            "artifacts": {
                str(p.relative_to(out)): {"sha256": digest(p), "bytes": p.stat().st_size}
                for p in files
            },
        },
    )
    return {
        "status": verdict["status"],
        "registration_sha256": reg_sha,
        "summary": summary,
        "primary_8h": {k: v for k, v in episode["candidate"]["8"].items() if k != "episodes"},
        "exact_falsifiers": verdict["exact_falsifiers"],
        "manifest_sha256": digest(out / "manifest.json"),
    }


def verify(out):
    m = read(out / "manifest.json")
    actual = {
        str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p.name != "manifest.json"
    }
    if actual != set(m["artifacts"]):
        raise ValueError("OUTPUT_FILE_SET_CHANGED")
    for name, item in m["artifacts"].items():
        p = out / name
        if (
            p.is_symlink()
            or not p.resolve().is_relative_to(out)
            or digest(p) != item["sha256"]
            or p.stat().st_size != item["bytes"]
        ):
            raise ValueError("OUTPUT_SHA_CHANGED:" + name)
    reg_sha = preregister(out)
    if reg_sha != m["registration_sha256"]:
        raise ValueError("FROZEN_REGISTRATION_SHA_CHANGED")
    preservation = assert_preserved(out)
    if read(out / "run_receipt.json")["code_sha256"] != code_hashes():
        raise ValueError("IMPLEMENTATION_OR_TEST_CODE_CHANGED")
    if any(r["exit_code"] for r in read(out / "command_test_receipts.json")):
        raise ValueError("FAILED_TEST_RECEIPT")
    rows, summary, coverage, episode = calculate(out, reg_sha)
    with (out / "feature_panel.jsonl").open("rb") as stream:
        for row in rows:
            if next(stream, None) != canonical(row):
                raise ValueError("PANEL_REPRODUCTION_MISMATCH")
        if next(stream, None) is not None:
            raise ValueError("EXTRA_PANEL_ROWS")
    verdict = feasibility(
        summary["total"], episode["candidate"]["8"], read(out / "exploratory_registration.v1.json")
    )
    for name, expected in [
        ("origin_coverage_and_missingness.json", summary),
        ("source_month_coverage.json", coverage),
        ("episode_tables.json", episode),
        ("feasibility_verdict.json", verdict),
        ("comparison_with_frozen_priors.json", prior_comparison(summary, episode)),
        ("evidence_vs_prior_novelty.json", novelty()),
    ]:
        if read(out / name) != expected:
            raise ValueError("DIAGNOSTIC_REPRODUCTION_MISMATCH:" + name)
    if (out / "NEXT_DECISION.md").read_text() != next_decision(verdict, episode):
        raise ValueError("NEXT_DECISION_CHANGED")
    return {
        "verified": True,
        "status": verdict["status"],
        "preservation": preservation,
        "registration_sha256": reg_sha,
        "manifest_sha256": digest(out / "manifest.json"),
        "summary": summary,
        "primary_8h": {k: v for k, v in episode["candidate"]["8"].items() if k != "episodes"},
        "exact_falsifiers": verdict["exact_falsifiers"],
        "labels": LABELS,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preregister", "build", "verify"])
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    out = args.output_root.absolute()
    if out != OUTPUT or out.resolve() != OUTPUT or out.is_symlink():
        raise ValueError("TASK_OWNED_OUTPUT_ROOT_ONLY")
    result = (
        {"registration_sha256": preregister(out)}
        if args.action == "preregister"
        else (build(out) if args.action == "build" else verify(out))
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
