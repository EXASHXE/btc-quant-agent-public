from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

import numpy as np
import pyarrow.dataset as ds

from btc_quant_agent.data.binance_archive import _download_verified, _sha256
from btc_quant_agent.data.binance_market_archive import (
    OFFICIAL_SPECS,
    parse_agg_trades,
    probe_official_archives,
    read_zip_sample,
)
from btc_quant_agent.symbolic_alpha.dsl import Operator
from btc_quant_agent.symbolic_alpha.evaluate import (
    EvaluationFirewall,
    block_hours_to_events,
    evaluate_formula,
    forward_returns,
)
from btc_quant_agent.symbolic_alpha.proposal import (
    ProposalConstraints,
    RandomGrammarProposalEngine,
)
from btc_quant_agent.symbolic_alpha.registry import (
    FeatureDefinition,
    formula_entry,
    write_registry,
)
from btc_quant_agent.symbolic_alpha.search import run_discovery_search
from btc_quant_agent.symbolic_alpha.vm import FormulaVM, Series

HOUR_MS = 3_600_000
HOLDOUT_START_MS = 1_769_904_000_000


def _timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000)


def _range(text: str) -> tuple[int, int]:
    left, right = text[1:-1].split(", ")
    return _timestamp(left), _timestamp(right)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rolling(values: Series, window: int, mode: str) -> Series:
    output: Series = [None] * len(values)
    for index in range(window - 1, len(values)):
        block = values[index - window + 1 : index + 1]
        if any(value is None for value in block):
            continue
        clean = [float(value) for value in block if value is not None]
        if mode == "mean":
            output[index] = fmean(clean)
        elif mode == "z":
            mean = fmean(clean)
            deviation = math.sqrt(fmean([(value - mean) ** 2 for value in clean]))
            output[index] = None if deviation <= 1e-15 else (clean[-1] - mean) / deviation
        elif mode == "rv":
            output[index] = math.sqrt(sum(value * value for value in clean))
    return output


def _hourly_market(
    root: Path, start_ms: int, end_ms: int, spot: bool
) -> dict[str, np.ndarray[Any, Any]]:
    hours = (end_ms - start_ms) // HOUR_MS
    count = np.zeros(hours, dtype=np.int16)
    open_value = np.full(hours, np.nan)
    high = np.full(hours, np.nan)
    low = np.full(hours, np.nan)
    close = np.full(hours, np.nan)
    volume = np.zeros(hours)
    quote = np.zeros(hours)
    taker = np.zeros(hours)
    trades = np.zeros(hours)
    dataset = ds.dataset(str(root / "1m"), format="parquet", partitioning="hive")
    columns = ["open_time_ms", "volume", "taker_buy_base_volume"]
    if not spot:
        columns.extend(["open", "high", "low", "close", "quote_volume", "trades"])
    condition = (ds.field("open_time_ms") >= start_ms) & (ds.field("open_time_ms") < end_ms)
    for batch in dataset.to_batches(columns=columns, filter=condition, batch_size=131_072):
        rows = batch.to_pydict()
        for row_index, timestamp in enumerate(rows["open_time_ms"]):
            hour = (int(timestamp) - start_ms) // HOUR_MS
            count[hour] += 1
            volume[hour] += float(rows["volume"][row_index])
            taker[hour] += float(rows["taker_buy_base_volume"][row_index])
            if not spot:
                price_open = float(rows["open"][row_index])
                price_high = float(rows["high"][row_index])
                price_low = float(rows["low"][row_index])
                price_close = float(rows["close"][row_index])
                if math.isnan(open_value[hour]):
                    open_value[hour] = price_open
                    high[hour] = price_high
                    low[hour] = price_low
                high[hour] = max(high[hour], price_high)
                low[hour] = min(low[hour], price_low)
                close[hour] = price_close
                quote[hour] += float(rows["quote_volume"][row_index])
                trades[hour] += float(rows["trades"][row_index])
    invalid = count != 60
    for array in (volume, taker):
        array[invalid] = np.nan
    if not spot:
        for array in (open_value, high, low, close, quote, trades):
            array[invalid] = np.nan
    return {
        "count": count,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "quote": quote,
        "taker": taker,
        "trades": trades,
    }


def _series(values: np.ndarray[Any, Any]) -> Series:
    return [None if not math.isfinite(float(value)) else float(value) for value in values]


def build_features(
    perp_root: Path, spot_root: Path
) -> tuple[list[int], dict[str, Series], Series, dict[str, Any]]:
    start_ms = _timestamp("2021-01-01T00:00:00Z")
    end_ms = HOLDOUT_START_MS
    timestamps = list(range(start_ms, end_ms, HOUR_MS))
    perp = _hourly_market(perp_root, start_ms, end_ms, False)
    spot = _hourly_market(spot_root, start_ms, end_ms, True)
    close = _series(perp["close"])
    volume = _series(perp["volume"])
    quote = _series(perp["quote"])
    taker = _series(perp["taker"])
    trades = _series(perp["trades"])
    spot_volume = _series(spot["volume"])
    spot_taker = _series(spot["taker"])
    ret1: Series = [None] * len(close)
    ret4: Series = [None] * len(close)
    atr_component: Series = [None] * len(close)
    for index, current in enumerate(close):
        if index >= 1 and current and close[index - 1]:
            ret1[index] = math.log(current / float(close[index - 1]))
        if index >= 4 and current and close[index - 4]:
            ret4[index] = math.log(current / float(close[index - 4]))
        if (
            current
            and math.isfinite(float(perp["high"][index]))
            and math.isfinite(float(perp["low"][index]))
        ):
            atr_component[index] = (
                float(perp["high"][index]) - float(perp["low"][index])
            ) / current
    perp_imbalance: Series = [
        None if base is None or base <= 0 or buy is None else 2 * buy / base - 1
        for base, buy in zip(volume, taker, strict=True)
    ]
    spot_imbalance: Series = [
        None if base is None or base <= 0 or buy is None else 2 * buy / base - 1
        for base, buy in zip(spot_volume, spot_taker, strict=True)
    ]
    spread: Series = [
        None if left is None or right is None else left - right
        for left, right in zip(spot_imbalance, perp_imbalance, strict=True)
    ]
    funding_events: list[tuple[int, float]] = []
    with (perp_root / "funding_events.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            timestamp = int(row["timestamp_ms"])
            if timestamp < HOLDOUT_START_MS:
                funding_events.append((timestamp, float(row["funding_rate"])))
    funding: Series = [None] * len(timestamps)
    event_index = 0
    current_funding: float | None = None
    for index, hour in enumerate(timestamps):
        decision_close = hour + HOUR_MS
        while (
            event_index < len(funding_events) and funding_events[event_index][0] <= decision_close
        ):
            current_funding = funding_events[event_index][1]
            event_index += 1
        funding[index] = current_funding
    features = {
        "LOG_RETURN_1H": ret1,
        "LOG_RETURN_4H": ret4,
        "REALIZED_VOL_24H": _rolling(ret1, 24, "rv"),
        "ATR_24H": _rolling(atr_component, 24, "mean"),
        "QUOTE_VOLUME_Z_24H": _rolling(quote, 24, "z"),
        "TAKER_BUY_IMBALANCE_1H": perp_imbalance,
        "TRADE_COUNT_Z_24H": _rolling(trades, 24, "z"),
        "SPOT_TAKER_BUY_IMBALANCE_1H": spot_imbalance,
        "SPOT_PERP_FLOW_SPREAD": spread,
        "FUNDING_LEVEL": funding,
    }
    audit = {
        "hour_count": len(timestamps),
        "perp_complete_hours": int(np.sum(perp["count"] == 60)),
        "perp_incomplete_hours": int(np.sum(perp["count"] != 60)),
        "spot_complete_hours": int(np.sum(spot["count"] == 60)),
        "spot_incomplete_hours": int(np.sum(spot["count"] != 60)),
        "synthetic_hours": 0,
        "holdout_rows_loaded": 0,
        "feature_available_counts": {
            name: sum(value is not None for value in values) for name, values in features.items()
        },
        "funding_asof_rule": "last settled funding event at or before decision close",
    }
    return timestamps, features, close, audit


def _indices(timestamps: list[int], window: str, horizon: int) -> range:
    start, end = _range(window)
    first = (start - timestamps[0]) // HOUR_MS
    stop = (end - timestamps[0]) // HOUR_MS - horizon
    offset = (-first) % horizon
    return range(first + offset, stop, horizon)


def _metrics(metrics: Any) -> dict[str, Any]:
    return asdict(metrics)


def _multiple_testing(
    formulas: list[Any],
    features: dict[str, Series],
    returns: Series,
    indices: range,
    seed: int,
    *,
    block_hours: int = 168,
    sample_step_hours: int = 8,
    permutations: int = 200,
) -> dict[str, Any]:
    rows = list(indices)
    outcomes = np.array([returns[index] or 0.0 for index in rows])
    signs: list[list[float]] = []
    vm = FormulaVM()
    for formula in formulas:
        result = vm.execute(formula, features)
        assert result.values is not None and result.failure is None
        signs.append(
            [
                0.0
                if result.values[index] in (None, 0)
                else (1.0 if result.values[index] > 0 else -1.0)
                for index in rows
            ]
        )
    matrix = np.asarray(signs)
    counts = np.sum(matrix != 0, axis=1)
    eligible = counts > 1
    if not np.any(eligible):
        raise ValueError("multiple-testing audit has no formula with at least two events")
    excluded_count = int(np.sum(~eligible))
    matrix = matrix[eligible]
    counts = counts[eligible]
    observed_pnl = matrix * outcomes
    observed_mean = np.sum(observed_pnl, axis=1) / counts
    observed_variance = np.maximum(
        np.sum(observed_pnl * observed_pnl, axis=1) / counts - observed_mean**2, 1e-18
    )
    observed = observed_mean / np.sqrt(observed_variance / counts)
    observed_best = float(np.max(observed))
    rng = np.random.default_rng(seed)
    null_best: list[float] = []
    block = block_hours_to_events(block_hours, sample_step_hours)
    for _ in range(permutations):
        shift = int(rng.integers(1, max(2, len(rows) // block))) * block
        permuted = np.roll(outcomes, shift)
        pnl = matrix * permuted
        means = np.sum(pnl, axis=1) / counts
        variances = np.maximum(np.sum(pnl * pnl, axis=1) / counts - means**2, 1e-18)
        scores = means / np.sqrt(variances / counts)
        null_best.append(float(np.max(scores)))
    adjusted_p = (1 + sum(value >= observed_best for value in null_best)) / (permutations + 1)
    return {
        "procedure": "EMPIRICAL_BEST_SCORE_CIRCULAR_BLOCK_PERMUTATION",
        "permutations": permutations,
        "sample_step_hours": sample_step_hours,
        "block_hours": block_hours,
        "block_events": block,
        "observed_best_t_stat": observed_best,
        "null_best_t_stat_p95": float(np.quantile(null_best, 0.95)),
        "familywise_adjusted_p_value": adjusted_p,
        "passed_0_05": adjusted_p <= 0.05,
        "zero_or_single_event_formulas_excluded": excluded_count,
    }


def _compact_forward(raw: dict[str, Any]) -> dict[str, Any]:
    derivatives = raw["derivatives"]["successor_v0316"]
    opportunity = raw["opportunity_forward"]["successor_h36"]
    micro = raw["microstructure_forward"]
    return {
        "captured_at_ms": int(time.time() * 1000),
        "derivatives_v0316": {
            key: derivatives[key]
            for key in (
                "expected_scheduled_slots",
                "recorded_scheduled_slots",
                "fully_available_scheduled_slots",
                "partial_slots",
                "failed_slots",
                "missing_slots",
                "max_consecutive_bad_or_missing_slots",
                "required_field_coverage",
                "terminal_failure",
                "scheduler_active",
                "scheduler_enabled",
            )
        },
        "opportunity_h36": {
            "campaign_id": opportunity["campaign_id"],
            "campaign_age_days": opportunity["campaign_age_days"],
            "successful_scan_ratio": opportunity["data_quality_gate"][
                "successful_scheduled_scan_ratio"
            ],
            "expected_slots": opportunity["data_quality_gate"]["expected_scheduled_slots"],
            "missed_slots": opportunity["data_quality_gate"]["total_missed_slots"],
            "max_miss_streak": opportunity["data_quality_gate"][
                "max_consecutive_missed_decision_slots"
            ],
            "opportunity_count": opportunity["opportunity_count"],
            "resolved_4h": opportunity["resolved_4h_opportunity_count"],
            "resolved_8h": opportunity["resolved_8h_opportunity_count"],
            "terminal_failure": opportunity["data_quality_gate"]["terminal_failure"],
            "scheduler_active": opportunity["scheduler_active"],
            "resolver_scheduler_active": opportunity["resolver_scheduler_active"],
        },
        "microstructure_v0315": {
            key: micro[key]
            for key in (
                "campaign_age_seconds",
                "agg_trade_events",
                "depth_events",
                "book_samples",
                "uptime_ratio",
                "depth_sequence_continuity_ratio",
                "gap_count",
                "resync_count",
                "orphan_instance_count",
                "heartbeat_age_seconds",
                "partition_integrity",
                "rolling_reliability",
                "service",
                "state",
            )
        },
        "execution": raw["execution"],
        "final_holdout": raw["final_holdout"],
        "alpha_interpretation": raw["alpha_interpretation"],
    }


def _forward_snapshot() -> dict[str, Any]:
    command = [str(Path(".venv/bin/quantctl")), "forward-evidence", "status"]
    raw = json.loads(subprocess.check_output(command, text=True))
    health_process = subprocess.run(
        [str(Path(".venv/bin/quantctl")), "forward-evidence", "health"],
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "status": _compact_forward(raw),
        "health": json.loads(health_process.stdout),
        "health_exit_code": health_process.returncode,
    }


def run(root: Path, artifact: Path, preregistration_sha: str) -> dict[str, Any]:
    protocol_path = root / "configs/research/v0.3.18_historical_symbolic_protocol.json"
    protocol = json.loads(protocol_path.read_text())
    artifact.mkdir(parents=True, exist_ok=True)
    start_forward = _forward_snapshot()
    archive_probe = probe_official_archives(["2021-01", "2024-01", "2025-01"])
    raw_root = root / "data/research/v0.3.18_official_samples"
    sample_audits: list[dict[str, Any]] = []
    for name in ("spot_aggTrades", "perp_aggTrades"):
        spec = OFFICIAL_SPECS[name]
        url = spec.daily_url("2024-01-01")
        target = raw_root / name / Path(url).name
        checksum = _download_verified(url, target)
        _, audit = parse_agg_trades(read_zip_sample(target, 10_000), market=spec.market_path)
        sample_audits.append(
            {
                "dataset": name,
                "url": url,
                "sample_rows_parsed": 10_000,
                "official_sha256": checksum,
                "local_sha256": _sha256(target),
                "audit": audit,
            }
        )
    timestamps, features, close, feature_audit = build_features(
        root / "data/research/BTCUSDT", root / "data/research/BTCUSDT_SPOT"
    )
    returns = forward_returns(close, 8)
    feature_definitions = {
        name: FeatureDefinition(
            name,
            "CANONICAL_HISTORICAL",
            {
                "LOG_RETURN_1H": 1,
                "LOG_RETURN_4H": 4,
                "REALIZED_VOL_24H": 24,
                "ATR_24H": 24,
                "QUOTE_VOLUME_Z_24H": 23,
                "TAKER_BUY_IMBALANCE_1H": 0,
                "TRADE_COUNT_Z_24H": 23,
                "SPOT_TAKER_BUY_IMBALANCE_1H": 0,
                "SPOT_PERP_FLOW_SPREAD": 0,
                "FUNDING_LEVEL": 0,
            }[name],
            "available after the source hour is fully closed; unavailable rows remain masked",
        )
        for name in features
    }
    search_config = protocol["formula_search"]
    constraints = ProposalConstraints(
        maximum_tokens=search_config["maximum_postfix_tokens"],
        maximum_lookback=search_config["maximum_total_lookback_hours"],
        windows=tuple(search_config["allowed_window_parameters"]),
        operators=tuple(Operator(name) for name in search_config["allowed_operators"]),
    )
    discovery_indices = _indices(timestamps, protocol["scope"]["discovery_window"], 8)
    validation_indices = _indices(timestamps, protocol["scope"]["validation_window"], 8)
    pseudo_indices = _indices(timestamps, protocol["scope"]["pseudo_forward_window"], 8)
    search = run_discovery_search(
        RandomGrammarProposalEngine(),
        search_config["valid_unique_formula_budget"],
        {name: item.base_lookback_hours for name, item in feature_definitions.items()},
        search_config["seed"],
        constraints,
        features,
        returns,
        discovery_indices,
        search_config["complexity_penalty_per_operator"],
    )
    top_validation = list(search.ranked[: search_config["top_k_selected_for_validation"]])
    cost_rate = (
        protocol["provisional_candidate_gate"]["fees_bps_round_trip"]
        + protocol["provisional_candidate_gate"]["slippage_bps_round_trip"]
    ) / 10_000
    validation_rows: list[dict[str, Any]] = []
    for item in top_validation:
        metrics = evaluate_formula(
            item.formula,
            features,
            returns,
            validation_indices,
            cost_rate=cost_rate,
            bootstrap_seed=search_config["seed"],
            bootstrap_resamples=1_000,
            sample_step_hours=8,
        )
        validation_rows.append(
            {"formula": item.formula, "discovery": item.metrics, "validation": metrics}
        )
    validation_rows.sort(
        key=lambda row: (-(row["validation"].net_mean_return or -1e9), row["formula"].formula_hash)
    )
    frozen = validation_rows[: search_config["top_k_frozen_before_pseudo_forward"]]
    firewall = EvaluationFirewall()
    frozen_hashes = firewall.freeze_top_k([row["formula"] for row in frozen])
    _json(
        artifact / "pseudo_forward_top_k_freeze.json",
        {
            "preregistration_sha": preregistration_sha,
            "formula_hashes": frozen_hashes,
            "selection_rule": "top validation net mean after frozen cost; no pseudo-forward viewed",
            "pseudo_forward_touches_before_freeze": 0,
        },
    )
    for row in frozen:
        firewall.authorize_pseudo_forward(row["formula"])
        row["pseudo_forward"] = evaluate_formula(
            row["formula"],
            features,
            returns,
            pseudo_indices,
            cost_rate=cost_rate,
            bootstrap_seed=search_config["seed"] + 1,
            bootstrap_resamples=1_000,
            sample_step_hours=8,
        )
    multiple_testing = _multiple_testing(
        [item.formula for item in search.ranked],
        features,
        returns,
        discovery_indices,
        search_config["seed"],
    )
    gate = protocol["provisional_candidate_gate"]
    candidates: list[dict[str, Any]] = []
    for row in frozen:
        discovery = row["discovery"]
        validation = row["validation"]
        pseudo = row["pseudo_forward"]
        checks = {
            "multiple_testing": multiple_testing["passed_0_05"],
            "discovery_events": discovery.event_count >= gate["minimum_discovery_events"],
            "validation_events": validation.event_count >= gate["minimum_validation_events"],
            "pseudo_forward_events": pseudo.event_count >= gate["minimum_pseudo_forward_events"],
            "long_balance": pseudo.long_fraction is not None
            and gate["minimum_long_fraction"]
            <= pseudo.long_fraction
            <= gate["maximum_long_fraction"],
            "discovery_net": (discovery.net_mean_return or -1)
            >= gate["minimum_discovery_net_mean_return_8h"],
            "validation_net": (validation.net_mean_return or -1)
            >= gate["minimum_validation_net_mean_return_8h"],
            "pseudo_forward_net": (pseudo.net_mean_return or -1)
            >= gate["minimum_pseudo_forward_net_mean_return_8h"],
            "validation_ci": (validation.bootstrap_ci_low or -1)
            >= gate["minimum_validation_bootstrap_ci_low"],
            "pseudo_forward_ci": (pseudo.bootstrap_ci_low or -1)
            >= gate["minimum_pseudo_forward_bootstrap_ci_low"],
            "positive_validation_folds": sum(
                value is not None and value > 0 for value in validation.chronological_fold_means
            )
            >= gate["minimum_positive_chronological_folds"],
            "positive_pseudo_forward_folds": sum(
                value is not None and value > 0 for value in pseudo.chronological_fold_means
            )
            >= gate["minimum_positive_chronological_folds"],
        }
        candidates.append(
            {
                "formula_hash": row["formula"].formula_hash,
                "canonical_formula": json.loads(row["formula"].canonical_json()),
                "discovery": _metrics(discovery),
                "validation": _metrics(validation),
                "pseudo_forward": _metrics(pseudo),
                "gate_checks": checks,
                "passed_all_frozen_gates": all(checks.values()),
            }
        )
    candidate_exists = any(row["passed_all_frozen_gates"] for row in candidates)
    registry_entries = []
    metrics_by_hash = {row["formula_hash"]: row for row in candidates}
    for rank, item in enumerate(search.ranked[:20], 1):
        candidate = metrics_by_hash.get(item.formula.formula_hash)
        passed = bool(candidate and candidate["passed_all_frozen_gates"])
        registry_entries.append(
            formula_entry(
                item.formula,
                feature_definitions,
                formula_id=f"V0318_RANDOM_{rank:03d}",
                proposal_engine="RANDOM_GRAMMAR_SEARCH",
                search_run_id=artifact.name,
                search_seed=search_config["seed"],
                search_budget=search_config["valid_unique_formula_budget"],
                discovery_window=protocol["scope"]["discovery_window"],
                validation_window=protocol["scope"]["validation_window"],
                pseudo_forward_window=protocol["scope"]["pseudo_forward_window"],
                metrics_by_fold=(candidate or {"discovery": _metrics(item.metrics)}),
                correlation_to_existing_candidates=None,
                status="PROVISIONAL_SANDBOX_CANDIDATE" if passed else "FAILED_VALIDATION",
                research_eligibility=passed,
            )
        )
    registry_path = root / "configs/formula_registry.json"
    write_registry(registry_path, registry_entries)
    end_forward = _forward_snapshot()
    archive_audit = {
        **archive_probe,
        "daily_aggtrade_schema_samples": sample_audits,
        "large_raw_data_gitignored": True,
        "no_gap_fill": True,
        "synthetic_trades": 0,
        "archive_path_patterns_tested": sorted(
            {item["url"].rsplit("/", 1)[0] for item in archive_probe["requests"]}
        ),
    }
    search_audit = {
        "preregistration_sha": preregistration_sha,
        "protocol_sha256": _digest(protocol_path),
        "proposal_engine": "RANDOM_GRAMMAR_SEARCH",
        "external_llm_api_used": False,
        "search": search.audit_dict(),
        "validation_candidates": len(top_validation),
        "top_k_frozen_before_pseudo_forward": len(frozen),
        "frozen_formula_hashes": list(frozen_hashes),
        "pseudo_forward_touches": firewall.pseudo_forward_touches,
        "multiple_testing": multiple_testing,
        "candidate_results": candidates,
        "candidate_exists": candidate_exists,
        "provisional_shadow_started": False,
        "recommendation": (
            "START_PROVISIONAL_CANDIDATE_FORWARD_SHADOW"
            if candidate_exists
            else "CONTINUE_SYMBOLIC_DISCOVERY_NO_CANDIDATE"
        ),
    }
    provenance = {
        "feature_data_audit": feature_audit,
        "perp_manifest_sha256": _digest(root / "data/research/BTCUSDT/data_manifest.json"),
        "spot_manifest_sha256": _digest(root / "data/research/BTCUSDT_SPOT/data_manifest.json"),
        "roles": {
            "official_archive": "OFFICIAL_HISTORICAL_TIMESTAMPED",
            "existing_checksum_verified_klines": "CANONICAL_HISTORICAL",
            "vendor_imports": "VENDOR_RECORDED_HISTORICAL_PIT_PROXY",
            "local_running_collectors": "TRUE_FORWARD_LOCAL_PIT",
            "historical_l2_without_vendor": "UNAVAILABLE_OR_UNTRUSTWORTHY",
            "existing_microstructure": "FORWARD_PIT_ONLY",
        },
        "historical_l2_synthesized": False,
        "final_holdout_rows_loaded": 0,
    }
    forward = {"start": start_forward, "end": end_forward, "historical_writes_to_forward_stores": 0}
    _json(artifact / "protocol.json", protocol)
    _json(artifact / "historical_data_provenance_audit.json", provenance)
    _json(artifact / "binance_official_archive_audit.json", archive_audit)
    _json(artifact / "symbolic_search_audit.json", search_audit)
    _json(artifact / "formula_registry_snapshot.json", json.loads(registry_path.read_text()))
    _json(artifact / "forward_campaigns_status.json", forward)
    manifest = {
        "run_id": artifact.name,
        "created_at": datetime.now(UTC).isoformat(),
        "preregistration_sha": preregistration_sha,
        "artifacts": {path.name: _digest(path) for path in sorted(artifact.glob("*.json"))},
        "raw_data": {
            str(path.relative_to(root)): _sha256(path) for path in sorted(raw_root.rglob("*.zip"))
        },
        "safety": protocol["safety"],
    }
    _json(artifact / "artifact_manifest.json", manifest)
    return {
        "artifact": str(artifact),
        "manifest_sha256": _digest(artifact / "artifact_manifest.json"),
        "candidate_exists": candidate_exists,
        "recommendation": search_audit["recommendation"],
        "multiple_testing": multiple_testing,
        "top_candidate": candidates[0] if candidates else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--preregistration-sha", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.root.resolve(), args.artifact.resolve(), args.preregistration_sha), indent=2
        )
    )


if __name__ == "__main__":
    main()
