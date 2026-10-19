"""Deterministic TEST-ONLY parser/funding/cost demonstration, never authority."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.cross_venue.pipeline import prepare_output
from scripts.research.strategy_eval import DAY, HORIZONS, PLAN, SEED
from scripts.research.strategy_eval import pipeline as p1
from scripts.research.strategy_eval.costs import SCENARIOS

from . import LABELS, checked_path
from .archive_adapter import matched_population
from .outcome_adapter import (TASK, build_panel_row, evaluate_panel_economics,
                              generate_synthetic_fixture_data, validate_horizon_limits)


def write_json(root: Path, name: str, value: Any) -> str:
    raw = n.canonical_bytes(value)
    with n.directory_fd(root) as directory:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def run_demo(output_dir: Path, n_hours: int = 120, seed: int = SEED,
             embargo_offset_h: int = 24) -> dict[str, Any]:
    n.require(type(n_hours) is int and 1 <= n_hours <= 168, "BOUNDED_SYNTHETIC_HOURS_REQUIRED")
    n.require(type(embargo_offset_h) is int and 0 <= embargo_offset_h <= n_hours,
              "SYNTHETIC_EMBARGO_INVALID")
    output = prepare_output(checked_path(output_dir))
    start = 1704067200  # fixed, unambiguously synthetic 2024 fixture epoch
    fixtures = generate_synthetic_fixture_data(start, n_hours, seed, inject_mark_gap=True)
    end = start + n_hours * 3600
    embargo = (end - embargo_offset_h * 3600) * n.US
    rows = []
    for cutoff in range(start, end, 3600):
        row = build_panel_row(cutoff + 60, fixtures["perp_1m_bars"], fixtures["spot_1m_bars"],
            fixtures["mark_prices"], fixtures["metrics_5m"], fixtures["funding_rates"],
            (start * n.US, end * n.US), embargo, fixtures["known_mark_gaps"])
        if cutoff - DAY - 60 < start:
            row.update(x=None, x_complete=False, x_reason="WARMUP_X_24H", native_feature_ready=False)
        row.update(test_only=True, data_kind="TEST_ONLY_SYNTHETIC", receiver_pit="PIT_UNKNOWN")
        rows.append(row)
    # P1 requires these literal schema labels, so carry conspicuous independent
    # TEST-ONLY metadata on both files. Real dual-gate validation rejects them.
    panel = {"schema": "strategy_eval.normalized.v1", "exposure": "EXPOSED_DEV",
             "label": "HISTORICAL_OFFLINE / PIT_UNKNOWN", "test_only": True,
             "data_kind": "TEST_ONLY_SYNTHETIC", "start_utc_s": start, "rows": rows}
    hashes = {}
    hashes["synthetic_scope.json"] = write_json(output, "synthetic_scope.json", {
        "schema": "exposed_dev_bridge.synthetic-scope.v1", "test_only": True,
        "data_kind": "TEST_ONLY_SYNTHETIC", "authority": "FIXTURE_GENERATOR_NOT_OWNER",
        "seed": seed, "start_utc_s": start, "end_utc_s": end,
        "real_source_paths": [], "real_input_permission": "NONE"})
    hashes["normalized_panel.json"] = write_json(output, "normalized_panel.json", panel)
    fixture = {"schema": "strategy_eval.exposed-dev.v1", "exposure": "EXPOSED_DEV",
        "test_only": True, "data_kind": "TEST_ONLY_SYNTHETIC", "usable_for_real_inputs": False,
        "authority": "TEST_FIXTURE_NOT_OWNER_AUTHORIZATION", "panels": [{
            "path": str(output / "normalized_panel.json"), "sha256": hashes["normalized_panel.json"],
            "start_utc_s": start, "end_utc_s": end}]}
    hashes["p1_synthetic_allowlist.json"] = write_json(output, "p1_synthetic_allowlist.json", fixture)
    parsed, parsed_start, binding = p1.authorized_panel(output / "normalized_panel.json",
                                                      output / "p1_synthetic_allowlist.json")
    parsed = matched_population(parsed)
    economics = {scenario.name: {str(h): evaluate_panel_economics(parsed, h, assumptions=scenario)
                                  for h in HORIZONS} for scenario in SCENARIOS}
    ledger = {"task": TASK, "test_only": True, "data_kind": "TEST_ONLY_SYNTHETIC", "seed": seed,
        "real_sources_opened": 0, "real_historical_outcomes_evaluated": 0, "real_outcome_labels_read": 0,
        "generated_channels": ["BTCUSDT USD-M 1m", "BTCUSDT spot 1m", "mark 1m", "OI 5m", "funding 8h"],
        "native_clock": "GENERATED_UTC_SECONDS", "receiver_pit": "PIT_UNKNOWN",
        "synthetic_mark_gap_utc_us": fixtures["known_mark_gaps"],
        "outcome_reasons": {str(h): dict(sorted(Counter(r["outcome_reasons"][str(h)] for r in rows).items()))
                            for h in HORIZONS}, "p1_parser_binding": binding,
        "frozen_plan": PLAN, "cost_round_trip_bp_assumptions": [s.nominal_round_trip_bp for s in SCENARIOS],
        "purge_max_horizon_h": PLAN["purge_max_horizon_h"], "additional_p1_embargo_s": PLAN["embargo_s"],
        "no_real_owner_scope_created": True}
    hashes["provenance_ledger.json"] = write_json(output, "provenance_ledger.json", ledger)
    summary = {"task": TASK, "status": "P3_R3_E2E_DEV_READY", "access_status": "P3_ACCESS_SCOPE_HOLD",
        "test_only": True, "origins_scheduled": len(rows), "origins_dropped": 0,
        "native_feature_ready_origins": sum(r["native_feature_ready"] for r in rows),
        "horizon_denominators": {str(h): len(rows) for h in HORIZONS},
        "horizon_limits": validate_horizon_limits([r["t"] for r in rows], embargo),
        "p1_authorized_panel_called": True, "p1_economics_called": True,
        "p1_economics_delegation": economics["baseline_16bp"]["8"], "economics": economics,
        "full_fold_status": "FULL_FOLD_SYNTHETIC_NOT_RUN",
        "full_fold_reason": "BOUNDED_SHORT_SOURCE_FIXTURE_DEMO_NO_84_DAY_FOLD_OR_ALPHA_CLAIM",
        "real_historical_outcomes_evaluated": 0, "real_outcome_labels_read": 0,
        "external_step": "PREEXISTING_OWNER_V2_SCOPE_WITH_PRIVATE_PARTITION_ATTESTATIONS_AND_PINNED_P1_ALLOWLIST",
        "future_command": "python3 -m scripts.research.exposed_dev_bridge.pipeline materialize --scope OWNER_V2.json --p1-allowlist P1_V1.json --output-dir /tmp/OWNER_PINNED_FRESH_DIR --evaluate",
        "labels": list(LABELS), "exit_code": 0}
    hashes["summary.json"] = write_json(output, "summary.json", summary)
    checks = {"actual_p1_parser": parsed_start == start and len(parsed) == n_hours,
        "sparse_outcomes": all(v is not None for r in rows for v in r["outcomes"].values()),
        "fixed_horizon_denominators": all(e["total_origins"] == n_hours
                                         for scenario in economics.values() for e in scenario.values()),
        "matched_x_xz_population": all(p1.data.ready(r)[0] == p1.data.ready(r)[1] for r in parsed),
        "unresolved_not_zero_pnl": all(e["sleeve_pnl_sum"] is None for scenario in economics.values()
                                      for e in scenario.values() if e["unresolved_origins"]),
        "real_historical_outcomes_zero": True, "no_owner_authorization_created": True}
    n.require(all(checks.values()), "SYNTHETIC_CONTRACT_CHECK_FAILED")
    write_json(output, "test_receipt.json", {"task": TASK, "status": summary["status"],
        "test_only": True, "receipt_kind": "RUNTIME_CONTRACT_CHECKS_NOT_PYTEST", "pytest": "NOT_RUN_BY_CLI",
        "checks": checks, "artifact_sha256": hashes, "real_outcome_labels_read": 0,
        "full_fold_status": summary["full_fold_status"]})
    return summary
