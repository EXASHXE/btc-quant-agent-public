"""TEST_ONLY_SYNTHETIC P3 panel -> actual frozen P1 full-fold evaluation."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.cross_venue.pipeline import prepare_output
from scripts.research.strategy_eval import HORIZONS, PLAN, SEED
from scripts.research.strategy_eval import pipeline as p1

from . import LABELS, checked_path
from .archive_adapter import matched_population
from .synthetic_contract import write_json


def run_fullfold(output_dir: Path) -> dict[str, Any]:
    """Reuse P1's seeded native-minute generator; never open an archive."""
    started = time.monotonic()
    output = prepare_output(checked_path(output_dir))
    rows, start, inventory = p1.synthetic_dataset()
    end = start + len(rows) * 3600
    n.require(len(rows) >= 84 * 24, "SYNTHETIC_FULL_FOLD_GRID_TOO_SHORT")
    missing = {str(h): 0 for h in HORIZONS}
    for row in rows:
        supplied = row["outcomes"]
        row["outcomes"] = {key: value.to_dict() for key, value in supplied.items()
                           if value.exit_t <= end}
        for h in HORIZONS:
            if str(h) not in row["outcomes"]:
                missing[str(h)] += 1
        row.update(test_only=True, data_kind="TEST_ONLY_SYNTHETIC", receiver_pit="PIT_UNKNOWN",
                   outcome_reasons={str(h): ("RESOLVED" if str(h) in row["outcomes"] else
                                              "OUTCOME_BEYOND_SYNTHETIC_RIGHT_EDGE") for h in HORIZONS})
    panel_path = output / "normalized_panel.json"
    panel_sha = write_json(output, panel_path.name, {
        "schema": "strategy_eval.normalized.v1", "exposure": "EXPOSED_DEV",
        "label": "HISTORICAL_OFFLINE / PIT_UNKNOWN", "test_only": True,
        "data_kind": "TEST_ONLY_SYNTHETIC", "start_utc_s": start, "rows": rows})
    allowlist_path = output / "p1_synthetic_integrity_allowlist.json"
    allowlist_sha = write_json(output, allowlist_path.name, {
        "schema": "strategy_eval.exposed-dev.v1", "exposure": "EXPOSED_DEV",
        "test_only": True, "data_kind": "TEST_ONLY_SYNTHETIC",
        "binding_kind": "DERIVED_INTEGRITY_NOT_OWNER_AUTHORIZATION",
        "authority": "TEST_FIXTURE_NOT_OWNER_AUTHORIZATION", "panels": [{
            "path": str(panel_path), "sha256": panel_sha,
            "start_utc_s": start, "end_utc_s": end}]})
    parsed, parsed_start, binding = p1.authorized_panel(panel_path, allowlist_path)
    common = matched_population(parsed)
    evaluation = p1.evaluate(common, parsed_start)
    report_root = p1.data.prepare_output(output / "p1_evaluation")
    p1_receipt = p1.write_reports(report_root, common, parsed_start, inventory,
                                  evaluation, "DEV_SYNTHETIC_ONLY")
    folds = [{"development_end_day": f["development_end_day"], "status": f["status"],
              "scheduled_validation": f["scheduled"], "training_rows": f["training_rows"],
              "model_count": len(f["models"]), "validation_start_utc_s": f["validation_start"],
              "training_max_label_end_utc_s": f["training_max_label_end"]}
             for f in evaluation["folds"]]
    executed = [f for f in folds if f["status"] == "EXPOSED_DEVELOPMENT_FOLD"]
    status = ("P4_S0_SYNTHETIC_FULLFOLD_AND_TWO_PHASE_READY" if len(executed) == 3
              else "P4_S0_PARTIAL")
    fold_summary = {"status": status, "data_kind": "TEST_ONLY_SYNTHETIC",
        "alpha": "NO_ALPHA_ESTABLISHED", "origin_count": len(common),
        "origin_horizon_denominators": {str(h): len(common) for h in HORIZONS},
        "no_action_or_feature_unavailable_origins": sum(not p1.data.ready(r)[1] for r in common),
        "sparse_missing_outcomes": missing, "outer_fold_boundaries_days": PLAN["outer_development_days"],
        "executed_outer_folds": len(executed), "folds": folds,
        "evaluation_status": evaluation["status"], "cell_count": len(evaluation["cells"]),
        "decision_record_count": len(evaluation["records"]),
        "p1_report": p1_receipt, "real_outcome_labels_read": 0,
        "real_historical_outcomes_evaluated": 0, "labels": list(LABELS)}
    fold_sha = write_json(output, "fold_summary.json", fold_summary)
    provenance_sha = write_json(output, "provenance.json", {
        "data_kind": "TEST_ONLY_SYNTHETIC", "seed": SEED, "source": "P1_SEEDED_NATIVE_MINUTE_GENERATOR",
        "adapter": "P3_SPARSE_OUTCOME_NORMALIZED_PANEL_TO_P1_AUTHORIZED_PANEL",
        "panel_sha256": panel_sha, "allowlist_sha256": allowlist_sha,
        "p1_parser_binding": binding, "real_source_paths": [], "real_outcome_labels_read": 0,
        "frozen_plan": PLAN, "labels": list(LABELS)})
    checks = {"all_three_outer_folds_executed": len(executed) == 3,
        "matched_population_retained": len(common) == len(rows),
        "all_horizons_and_cost_cells": len(evaluation["cells"]) == 3 * len(HORIZONS) * 2 * 2,
        "sparse_missing_outcomes_not_zero": all(missing.values()),
        "no_real_outcome_read": True}
    write_json(output, "test_receipt.json", {
        "status": status, "test_only": True, "checks": checks,
        "artifact_sha256": {"normalized_panel.json": panel_sha,
            "p1_synthetic_integrity_allowlist.json": allowlist_sha,
            "fold_summary.json": fold_sha, "provenance.json": provenance_sha,
            "p1_evaluation/metrics.json": hashlib.sha256((report_root / "metrics.json").read_bytes()).hexdigest()},
        "elapsed_wall_s": round(time.monotonic() - started, 3),
        "real_outcome_labels_read": 0})
    return fold_summary
