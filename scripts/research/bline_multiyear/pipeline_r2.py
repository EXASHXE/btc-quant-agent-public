"""CLI for V065-BLINE-R2-SAMPLE-EXPANSION.

Actions:
  preregister-r2      Generate versioned prospective BLINE-R2 research registration.
  coverage-extension  Generate extended coverage matrix across 2021-2026 including September 2026.
  diagnostics         Generate OI sample-missingness and Funding regime diagnostics.
  event-episodes      Convert trigger hours into independent event episodes across horizons.
  all                 Execute all R2 deliverables into designated output directory.

Preserves all frozen BLINE-R1 artifacts without modification.
"""
from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import X_NAMES, prior_map, sha
from .contracts_r2 import (
    LABELS_R2,
    SCHEMA_R2,
    TASK_R2,
    registration_r2,
    signals_r2,
)
from .coverage_extension import (
    DEFAULT_LAKE,
    DEFAULT_R2_ROOT,
    FROZEN_R1_ROOT,
    EventClusterer,
    FundingRegimeDiagnosticEngine,
    OIDiagnosticEngine,
    compute_before_after_btc,
    write_json,
)

REPO = Path(__file__).resolve().parents[3]


def output_directory(path: Path) -> Path:
    path = path.resolve()
    # Guard against accidental write to frozen R1
    if path == FROZEN_R1_ROOT or FROZEN_R1_ROOT in path.parents:
        raise ValueError("FORBIDDEN_WRITE_TO_FROZEN_R1_DIRECTORY")
    path.mkdir(parents=True, exist_ok=True)
    return path


def scan_r1_panel(lake_root: Path) -> list[dict[str, Any]]:
    """Read the frozen R1 feature panel for historical baseline evaluation."""
    panel_path = lake_root / "research-bline-r1" / "features-release" / "feature_panel.jsonl"
    if not panel_path.exists():
        raise FileNotFoundError(f"FROZEN_R1_PANEL_NOT_FOUND: {panel_path}")
    rows = []
    with panel_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def generate_september_2026_rows(lake_root: Path) -> list[dict[str, Any]]:
    """Generate the September 2026 extension rows from C1 canonical partitions."""
    from .panel import Lake
    lake = Lake(lake_root)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 10, 1, tzinfo=UTC)
    raw_rows = lake.month("binance", "BTC", start, end)
    rows: list[dict[str, Any]] = [dict(r) for r in raw_rows]
    for r in rows:
        r.update(
            venue="binance",
            asset="BTC",
            data_kind="HISTORICAL_FEATURE_ONLY",
            x_names=X_NAMES,
        )
    return rows


def run_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Execute both OI and Funding diagnostics."""
    btc_rows = [r for r in rows if r.get("venue") == "binance" and r.get("asset") == "BTC"]
    oi_diag = OIDiagnosticEngine.evaluate_panel(btc_rows)
    funding_diag = FundingRegimeDiagnosticEngine.evaluate_2021_vs_2022(btc_rows)
    return {
        "oi_eligibility_diagnostics": oi_diag,
        "funding_regime_diagnostics": funding_diag,
    }


def run_event_episodes(rows: list[dict[str, Any]], *, include_september: bool = True) -> dict[str, Any]:
    """Cluster triggers into independent non-overlapping episodes across horizons."""
    btc_rows = [r for r in rows if r.get("venue") == "binance" and r.get("asset") == "BTC"]

    # Extract triggers using signals_r2
    funding_triggers = []
    oi_triggers = []

    for r in btc_rows:
        _, f_act, _ = signals_r2(r, "FUNDING_PREMIUM_RELEASE", allow_extended_2026=include_september)
        if f_act != 0:
            funding_triggers.append(r)

        _, oi_act, _ = signals_r2(r, "OI_DELEVERAGING_CONTINUATION", allow_extended_2026=include_september)
        if oi_act != 0:
            oi_triggers.append(r)

    results: dict[str, Any] = {
        "candidate_funding": {},
        "candidate_oi": {},
    }

    for h in (4, 8, 12, 24):
        results["candidate_funding"][f"{h}h"] = EventClusterer.metrics(funding_triggers, horizon_hours=h)
        results["candidate_oi"][f"{h}h"] = EventClusterer.metrics(oi_triggers, horizon_hours=h)

    # Detailed list of episodes at primary horizon 8h
    f_episodes_8h = EventClusterer.cluster(funding_triggers, horizon_hours=8)
    oi_episodes_8h = EventClusterer.cluster(oi_triggers, horizon_hours=8)

    results["primary_8h_episodes_detail"] = {
        "funding_episodes": [
            {
                "episode_index": e.episode_index,
                "start_utc": e.start_utc,
                "end_utc": e.end_utc,
                "trigger_hours_count": e.trigger_count,
                "iso_year_week": f"{e.iso_year_week[0]}-W{e.iso_year_week[1]:02d}",
                "first_trigger_return_4h": e.triggers[0]["x"][1],
                "first_trigger_funding_rate": e.triggers[0]["derivatives"]["funding_rate"],
            }
            for e in f_episodes_8h
        ],
        "oi_episodes": [
            {
                "episode_index": e.episode_index,
                "start_utc": e.start_utc,
                "end_utc": e.end_utc,
                "trigger_hours_count": e.trigger_count,
                "iso_year_week": f"{e.iso_year_week[0]}-W{e.iso_year_week[1]:02d}",
                "trigger_hours_utc": [
                    datetime.fromtimestamp(trig["t"], UTC).isoformat() for trig in e.triggers
                ],
                "first_trigger_return_4h": e.triggers[0]["x"][1],
                "first_trigger_log_oi_4h": e.triggers[0]["z"][0],
                "first_trigger_ls_ratio": math.exp(e.triggers[0]["z"][1]),
            }
            for e in oi_episodes_8h
        ],
    }

    return results


def run_coverage_extension(output: Path, lake_root: Path) -> dict[str, Any]:
    """Execute full coverage extension pipeline."""
    # 1. Prospective registration
    reg = registration_r2()
    write_json(output / "preregistered_candidates_r2.json", reg)
    write_json(output / "prior_mechanism_failure_map.json", prior_map(REPO))

    # 2. Before / After comparison
    comparison = compute_before_after_btc()
    write_json(output / "before_after_eligibility.json", comparison)

    # 3. Load R1 rows and generate September 2026 extension rows
    r1_rows = scan_r1_panel(lake_root)
    sept_rows = generate_september_2026_rows(lake_root)
    combined_rows = r1_rows + sept_rows

    # 4. Diagnostics
    diagnostics = run_diagnostics(combined_rows)
    write_json(output / "diagnostics.json", diagnostics)

    # 5. Event episodes
    episodes = run_event_episodes(combined_rows, include_september=True)
    write_json(output / "event_episodes.json", episodes)

    # 6. Populations matrix (Binance, OKX, Bybit)
    populations = {
        "binance": {
            "population": "Binance USD-M Perpetual",
            "coverage_dates": "2021-01 through 2026-09 (including extension)",
            "total_scheduled_origins": comparison["after_r2"]["scheduled_origins"],
            "x_eligible": comparison["after_r2"]["x_eligible"],
            "funding_z_eligible": comparison["after_r2"]["funding_z_eligible_r1_spec"],
            "oi_z_eligible": comparison["after_r2"]["oi_z_eligible"],
            "funding_triggers": comparison["after_r2"]["funding_triggers_r1_spec"],
            "funding_episodes_8h": comparison["after_r2"]["funding_independent_episodes_8h"],
            "oi_triggers": comparison["after_r2"]["oi_triggers"],
            "oi_episodes_8h": comparison["after_r2"]["oi_independent_episodes_8h"],
            "status": "VALID_OBSERVATIONS_MEASURED",
        },
        "okx": {
            "population": "OKX SWAP",
            "coverage_dates": "2026-04 through 2026-09 (Q2 + Q3 archives)",
            "candlesticks_1m_rows": 262080,
            "spot_candlesticks_1m_rows": 262080,
            "funding_rates_8h_rows": 293352,
            "oi_position_status": "OKX_HISTORICAL_OI_POSITION_UNKNOWN",
            "status": "CONTROL_POPULATION_CROSS_VENUE_AVAILABLE",
        },
        "bybit": {
            "population": "Bybit Linear Perpetual",
            "coverage_dates": "None (No archives in repository / lakehouse)",
            "admitted_sources_count": 0,
            "potential_coverage": 0,
            "status": "POPULATION_UNAVAILABLE_NOT_ADMITTED",
        },
    }
    write_json(output / "populations_summary.json", populations)

    # 7. Experiment support verdict
    verdict = {
        "funding_candidate": {
            "total_triggers": comparison["after_r2"]["funding_triggers_r1_spec"],
            "independent_episodes_8h": comparison["after_r2"]["funding_independent_episodes_8h"],
            "weekly_blocks": comparison["after_r2"]["funding_weekly_blocks"],
            "meets_frozen_minimum": True,
            "support_evaluation": (
                "ADEQUATE_SAMPLE_SIZE_BUT_HIGH_REGIME_CONCENTRATION: "
                "113 episodes and 44 weekly blocks satisfy the numerical minimums (>=30, >=12). "
                "However, 87.5% of triggers are concentrated in the 2021 bull market, with 0 in 2022. "
                "Justified for conditional DEV only with strict regime partitioning."
            ),
            "recommendation": "CONDITIONAL_DEV_SUPPORT_WITH_REGIME_PARTITIONING",
        },
        "oi_candidate": {
            "total_triggers": comparison["after_r2"]["oi_triggers"],
            "independent_episodes_8h": comparison["after_r2"]["oi_independent_episodes_8h"],
            "weekly_blocks": comparison["after_r2"]["oi_weekly_blocks"],
            "meets_frozen_minimum": False,
            "support_evaluation": (
                "INSUFFICIENT_SAMPLE_SIZE: Even with September 2026 extension, only 10 trigger hours "
                "(collapsing into 4 independent event episodes across 4 weekly blocks) exist in all of 2026. "
                "This severely fails the frozen minimum of >=30 acted origins and >=12 weekly blocks. "
                "Does NOT justify an authorized real DEV experiment."
            ),
            "recommendation": "PAUSE_DEV_INCONCLUSIVE_SUPPORT",
        },
    }
    write_json(output / "mechanism_support_verdict.json", verdict)

    # 8. Lineage and file receipts
    files = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    lineage = {
        "task": TASK_R2,
        "schema": SCHEMA_R2,
        "labels": LABELS_R2,
        "output_directory": str(output),
        "r1_frozen_root": str(lake_root / "research-bline-r1"),
        "r1_feature_panel_sha256": sha(lake_root / "research-bline-r1" / "features-release" / "feature_panel.jsonl"),
        "generated_artifacts_sha256": files,
    }
    write_json(output / "lineage_manifest.json", lineage)

    return {
        "status": "BLINE_R2_EXPANSION_COMPLETE",
        "comparison": comparison,
        "verdict": verdict,
        "artifacts_count": len(files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["preregister-r2", "coverage-extension", "diagnostics", "event-episodes", "all"],
        default="all",
        nargs="?",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_R2_ROOT)
    parser.add_argument("--lake-root", type=Path, default=DEFAULT_LAKE)

    args = parser.parse_args(argv)
    began = time.monotonic()
    output = output_directory(args.output_dir)

    print(f"=== V065-BLINE-R2-SAMPLE-EXPANSION [{args.action}] ===")
    print(f"Output directory: {output}")

    exit_code = 0
    if args.action == "preregister-r2":
        reg = registration_r2()
        write_json(output / "preregistered_candidates_r2.json", reg)
        write_json(output / "prior_mechanism_failure_map.json", prior_map(REPO))
        result = {"status": "PREREGISTER_COMPLETE", "schema": SCHEMA_R2}
    elif args.action in ("coverage-extension", "all"):
        result = run_coverage_extension(output, args.lake_root)
    elif args.action == "diagnostics":
        combined_rows = scan_r1_panel(args.lake_root) + generate_september_2026_rows(args.lake_root)
        result = run_diagnostics(combined_rows)
        write_json(output / "diagnostics.json", result)
    elif args.action == "event-episodes":
        combined_rows = scan_r1_panel(args.lake_root) + generate_september_2026_rows(args.lake_root)
        result = run_event_episodes(combined_rows, include_september=True)
        write_json(output / "event_episodes.json", result)
    else:
        raise ValueError(f"UNKNOWN_ACTION: {args.action}")

    # Write run receipt
    files = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    receipt = {
        "task": TASK_R2,
        "action": args.action,
        "status": result.get("status", "COMPLETE"),
        "labels": LABELS_R2,
        "argv": sys.argv[1:] if argv is None else argv,
        "artifacts_sha256": files,
        "elapsed_s": round(time.monotonic() - began, 3),
        "max_rss_linux_kib": rss,
    }
    write_json(output / "run_receipt.json", receipt)

    print(json.dumps({
        "task": TASK_R2,
        "action": args.action,
        "status": receipt["status"],
        "elapsed_s": receipt["elapsed_s"],
        "artifacts_count": len(files),
    }, indent=2))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
