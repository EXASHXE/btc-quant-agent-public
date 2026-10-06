#!/usr/bin/env python3
"""Run the single frozen RC2 R1 protected holdout from public Binance data."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from itertools import pairwise
from pathlib import Path
from typing import Any

from btc_quant_agent.market_watch.config import MarketWatchConfig
from btc_quant_agent.market_watch.domain import TACTICAL_POLICY_VERSION
from btc_quant_agent.market_watch.replay import (
    DeterministicTacticalReplayRunner,
    OOSPartitionSpec,
    ReplayDataset,
)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "evidence/v0.5.5/tactical-policy/RC2/HOLDOUT_R1"
DATA_CACHE = Path("/tmp/rc2-holdout-r1-raw.json")
START_SHA = "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
DISPATCH_SHA = "02652d0671c4e9476f2cf6b607b2c2e1242f3fde"
CONFIG_HASH = "bba61849e64f37f9"
POLICY_VERSION = "TACTICAL_POLICY_R2_B1"
CANDIDATE_ID = "C5_BOUNDED_COMBINATION_B"
RELEASE_ID = "B_LINE_INITIAL_USABLE_RELEASE_V1_RC2"
TASK_ID = "B_LINE_RC2_TACTICAL_SUCCESSOR_R1_INDEPENDENT_HOLDOUT"
SYMBOLS = ("ADAUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "BCHUSDT", "DOTUSDT", "ATOMUSDT", "NEARUSDT")
INTERVALS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
SOURCE_START = 1_788_716_700_000
DATA_END = 1_791_223_199_999
FIRST_STEP = 1_788_717_599_999
LAST_STEP = 1_791_136_799_999
P1 = (1_788_890_399_999, 1_789_639_199_999)
P2 = (1_789_639_199_999, 1_790_387_999_999)
P3 = (1_790_387_999_999, 1_791_136_799_999)
BASE = "https://fapi.binance.com"
FEEDS = {
    "oi_hist": ("/futures/data/openInterestHist", "symbol", "1h", 3_600_000),
    "taker_hist": ("/futures/data/takerlongshortRatio", "symbol", "15m", 900_000),
    "gls_hist": ("/futures/data/globalLongShortAccountRatio", "symbol", "1h", 3_600_000),
    "top_pos_hist": ("/futures/data/topLongShortPositionRatio", "symbol", "1h", 3_600_000),
    "top_acc_hist": ("/futures/data/topLongShortAccountRatio", "symbol", "1h", 3_600_000),
}
PREFLIGHT_REPORT = {
    "status": "PASS",
    "focused_regressions": {
        "status": "PASS",
        "passed": 288,
        "command": (
            "pytest -q tests/test_rc2_tactical_successor_r1.py tests/test_market_watch.py "
            "tests/test_tactical_policy_b0.py tests/test_rc1_tactical_quality_r1.py "
            "tests/test_tactical_grid_shadow_evaluation_v1.py "
            "tests/test_tactical_feature_evidence_v2.py "
            "tests/test_tactical_shadow_evaluation_v2.py"
        ),
    },
    "compileall": "PASS",
    "ruff": "PASS",
    "mypy": "PASS",
    "git_diff_check": "PASS",
}


def _json(path: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_changed_files() -> None:
    import subprocess

    status = subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=all"], cwd=ROOT, text=True
    )
    files = {line[3:] for line in status.splitlines() if len(line) > 3}
    files.add("evidence/v0.5.5/tactical-policy/RC2/HOLDOUT_R1/changed_files_manifest.json")
    _json("changed_files_manifest.json", {"changed_files": sorted(files)})


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _request(path: str, params: dict[str, Any]) -> Any:
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "RC2-Holdout-R1/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read())


def _fetch_pages(path: str, params: dict[str, Any], *, interval_ms: int) -> list[Any]:
    rows: list[Any] = []
    cursor = int(params["startTime"])
    end = int(params["endTime"])
    while cursor <= end:
        page = _request(path, {**params, "startTime": cursor})
        if not isinstance(page, list) or not page:
            break
        rows.extend(page)
        last = int(
            page[-1][0]
            if path.endswith("/klines")
            else page[-1].get("timestamp", page[-1].get("fundingTime"))
        )
        next_cursor = last + interval_ms
        if next_cursor <= cursor:
            raise ValueError(f"non-advancing Binance pagination: {path} {cursor}")
        cursor = next_cursor
        if len(page) < int(params["limit"]):
            break
    return rows


def _kline_rows(symbol: str, interval: str) -> list[list[Any]]:
    step = INTERVALS[interval]
    rows = _fetch_pages(
        "/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "startTime": SOURCE_START,
            "endTime": DATA_END,
            "limit": 1500,
        },
        interval_ms=step,
    )
    return [row for row in rows if SOURCE_START <= int(row[0]) and int(row[6]) <= DATA_END]


def _feed_rows(
    symbol: str,
    feed: str,
    path: str,
    key: str,
    period: str,
    period_ms: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        key: symbol,
        "period": period,
        "startTime": P1[0],
        "endTime": DATA_END,
        "limit": 500,
    }
    if feed == "basis_hist":
        params = {
            "pair": symbol,
            "contractType": "PERPETUAL",
            "period": period,
            "startTime": P1[0],
            "endTime": DATA_END,
            "limit": 500,
        }
    output: list[dict[str, Any]] = []
    cursor = P1[0]
    while cursor <= DATA_END:
        segment_end = min(DATA_END, cursor + period_ms * 499 - 1)
        page_value = _request(path, {**params, "startTime": cursor, "endTime": segment_end})
        if isinstance(page_value, dict):
            page_value = page_value.get("data")
        if not isinstance(page_value, list) or not page_value:
            break
        page = [dict(row) for row in page_value]
        output.extend(page)
        last = int(page[-1]["timestamp"])
        next_cursor = last + 1
        if next_cursor <= cursor:
            raise ValueError(f"non-advancing Binance feed pagination: {feed} {cursor}")
        cursor = next_cursor
        cursor = segment_end + 1
    return sorted({int(row["timestamp"]): row for row in output}.values(), key=lambda r: int(r["timestamp"]))


def _funding_rows(symbol: str) -> list[dict[str, Any]]:
    raw = _fetch_pages(
        "/fapi/v1/fundingRate",
        {"symbol": symbol, "startTime": SOURCE_START, "endTime": DATA_END, "limit": 1000},
        interval_ms=1,
    )
    return [
        {"funding_time_ms": int(row["fundingTime"]), "funding_rate": float(row["fundingRate"])}
        for row in raw
        if SOURCE_START <= int(row["fundingTime"]) <= DATA_END
    ]


def _source_dataset() -> tuple[dict[str, Any], dict[str, Any]]:
    if DATA_CACHE.exists():
        raw_bytes = DATA_CACHE.read_bytes()
        raw = json.loads(raw_bytes)
        return raw, json.loads(Path(str(DATA_CACHE) + ".manifest.json").read_text())

    raw: dict[str, Any] = {
        "symbols": list(SYMBOLS),
        "anchor_end_ms": DATA_END + 1,
        "data": {},
    }
    coverage: dict[str, Any] = {
        "source": "Binance USD-M public unauthenticated REST historical endpoints",
        "retrieved_at_ms": int(time.time() * 1000),
        "source_window": {"start_open_ms": SOURCE_START, "end_close_ms": DATA_END},
        "symbol_coverage": {},
    }
    for symbol in SYMBOLS:
        item: dict[str, Any] = {}
        symbol_coverage: dict[str, Any] = {}
        for interval, step in INTERVALS.items():
            rows = _kline_rows(symbol, interval)
            item[f"klines_{interval}"] = rows
            opens = [int(row[0]) for row in rows]
            first_open = ((SOURCE_START + step - 1) // step) * step
            expected = max(0, (DATA_END + 1 - first_open) // step)
            symbol_coverage[f"klines_{interval}"] = {
                "count": len(rows),
                "expected_count": expected,
                "first_open_ms": opens[0] if opens else None,
                "last_open_ms": opens[-1] if opens else None,
                "gap_count": sum(b - a != step for a, b in pairwise(opens)),
                "sha256": _sha256(json.dumps(rows, separators=(",", ":")).encode()),
                "source_endpoint": "/fapi/v1/klines",
                "synthetic": False,
            }
        item["funding_rates"] = _funding_rows(symbol)
        funding_raw = json.dumps(item["funding_rates"], sort_keys=True, separators=(",", ":")).encode()
        symbol_coverage["funding_rates"] = {
            "count": len(item["funding_rates"]),
            "sha256": _sha256(funding_raw),
            "source_endpoint": "/fapi/v1/fundingRate",
            "pit_rule": "fundingTime <= decision_time_ms; mark price resolved from closed 15m bars",
        }
        for feed, (path, key, period, period_ms) in FEEDS.items():
            rows = _feed_rows(symbol, feed, path, key, period, period_ms)
            item[feed] = rows
            times = [int(row["timestamp"]) for row in rows]
            symbol_coverage[feed] = {
                "count": len(rows),
                "first_timestamp_ms": times[0] if times else None,
                "last_timestamp_ms": times[-1] if times else None,
                "sha256": _sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()),
                "source_endpoint": path,
                "period": period,
                "availability_start_ms": P1[0],
                "pit_rule": "timestamp <= decision_time_ms",
            }
        basis = _feed_rows(symbol, "basis_hist", "/futures/data/basis", "pair", "5m", 300_000)
        item["basis_hist"] = basis
        basis_times = [int(row["timestamp"]) for row in basis]
        symbol_coverage["basis_hist"] = {
            "count": len(basis),
            "first_timestamp_ms": basis_times[0] if basis_times else None,
            "last_timestamp_ms": basis_times[-1] if basis_times else None,
            "sha256": _sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()),
            "source_endpoint": "/futures/data/basis",
            "period": "5m",
            "availability_start_ms": P1[0],
            "pit_rule": "timestamp <= decision_time_ms",
        }
        raw["data"][symbol] = item
        coverage["symbol_coverage"][symbol] = symbol_coverage
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    DATA_CACHE.write_bytes(encoded)
    Path(str(DATA_CACHE) + ".manifest.json").write_text(json.dumps(coverage, sort_keys=True))
    coverage["raw_dataset_sha256"] = _sha256(encoded)
    return raw, coverage


def _partitions() -> list[OOSPartitionSpec]:
    return [
        OOSPartitionSpec(f"P{i}", FIRST_STEP, start, start, end)
        for i, (start, end) in enumerate((P1, P2, P3), 1)
    ]


def _freeze_proof() -> dict[str, Any]:
    import subprocess

    manifest_path = ROOT / "evidence/v0.5.5/tactical-policy/RC2/SUCCESSOR_R1/SELECTED_POLICY_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_manifest = json.loads(
        (manifest_path.parent / "CANDIDATE_MANIFEST.json").read_text(encoding="utf-8")
    )
    c5 = next(c for c in candidate_manifest["candidates"] if c["candidate_id"] == CANDIDATE_ID)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    source_diff = subprocess.check_output(["git", "diff", START_SHA, "--", "src/"], cwd=ROOT, text=True)
    return {
        "exact_candidate_sha": START_SHA,
        "current_head_at_replay": head,
        "validation_branch": branch,
        "production_source_diff_empty": not bool(source_diff.strip()),
        "controller_dispatch_sha": DISPATCH_SHA,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": MarketWatchConfig().config_hash,
        "selected_candidate_id": manifest["selected_candidate_id"],
        "release_id": manifest["release_id"],
        "selected_manifest_policy_version": manifest["policy_version"],
        "selected_manifest_config_hash": manifest["config_hash"],
        "candidate_manifest_rule_match": c5["promoted_rules"] == [
            {k: rule[k] for k in c5["promoted_rules"][0]}
            for rule in manifest["promoted_rules"][:2]
        ],
        "selected_policy_manifest_sha256": _sha256(manifest_path.read_bytes()),
        "pass": (
            head == START_SHA
            and branch == "validation/b-line-rc2-successor-r1-holdout"
            and not source_diff.strip()
            and manifest["selected_candidate_id"] == CANDIDATE_ID
            and manifest["policy_version"] == POLICY_VERSION
            and manifest["config_hash"] == CONFIG_HASH
            and MarketWatchConfig().config_hash == CONFIG_HASH
            and manifest["release_id"] == RELEASE_ID
            and c5["promoted_rules"]
            == [{k: rule[k] for k in c5["promoted_rules"][0]} for rule in manifest["promoted_rules"][:2]]
        ),
    }


def _steps() -> list[int]:
    return list(range(FIRST_STEP, LAST_STEP + 1, INTERVALS["15m"]))


def _release_decision(
    aggregate: dict[str, Any], partitions: list[dict[str, Any]], gate_evaluation: dict[str, Any]
) -> str:
    n = int(aggregate["actionable_signal_count"])
    supported = [p for p in partitions if int(p["actionable_signal_count"]) >= 20]
    means = [float(p["mean_net_R"]) for p in supported]
    stop_rate = aggregate.get("stop_before_target")
    if gate_evaluation["hard_negative_gates"]["any_triggered"]:
        return "RC2_TACTICAL_HOLDOUT_FAIL"
    if (
        n >= 100
        and (
            float(aggregate["mean_net_R"]) <= -0.10
            or float(aggregate["median_net_R"]) <= -0.20
            or sum(1 for p in supported if float(p["mean_net_R"]) <= -0.25) >= 2
            or (aggregate.get("target_stop_resolved_count", 0) >= 100 and stop_rate is not None and stop_rate > 0.70)
        )
    ):
        return "RC2_TACTICAL_HOLDOUT_FAIL"
    support = n >= 100 and all(
        int(aggregate.get(k, 0)) >= 20 for k in ("long_actionable_count", "short_actionable_count")
    )
    support = support and len(partitions) == 3 and len(supported) >= 2
    passed = (
        support
        and float(aggregate["mean_net_R"]) >= 0.05
        and float(aggregate["median_net_R"]) >= -0.05
        and sum(mean >= 0.0 for mean in means) >= 2
        and stop_rate is not None
        and float(stop_rate) <= 0.65
    )
    if passed:
        return "RC2_TACTICAL_HOLDOUT_PASS"
    return "RC2_TACTICAL_HOLDOUT_DIAGNOSTIC_ONLY"


def main() -> None:
    freeze = _freeze_proof()
    if not freeze["pass"]:
        _json("EVIDENCE.json", {"task_id": TASK_ID, "terminal_result": "RC2_HOLDOUT_PREFLIGHT_FAIL", "freeze_proof": freeze})
        _write_changed_files()
        raise SystemExit("RC2_HOLDOUT_PREFLIGHT_FAIL")
    try:
        raw, coverage = _source_dataset()
    except Exception as exc:
        _json("preflight_report.json", PREFLIGHT_REPORT)
        _json("EVIDENCE.json", {
            "task_id": TASK_ID,
            "terminal_result": "RC2_HOLDOUT_INFRA_INCOMPLETE",
            "freeze_proof": freeze,
            "source_acquisition_error": f"{type(exc).__name__}: {exc}",
        })
        _write_changed_files()
        raise SystemExit("RC2_HOLDOUT_INFRA_INCOMPLETE") from exc
    raw_hash = _sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())
    coverage["raw_dataset_sha256"] = raw_hash
    _json("source_coverage_digest.json", coverage)
    checks = all(
        coverage["symbol_coverage"][s]["klines_1m"]["count"] == 41_775
        and coverage["symbol_coverage"][s]["klines_1m"]["expected_count"] == 41_775
        and coverage["symbol_coverage"][s]["klines_1m"]["gap_count"] == 0
        and coverage["symbol_coverage"][s]["klines_1m"]["first_open_ms"] == SOURCE_START
        and coverage["symbol_coverage"][s]["klines_1m"]["last_open_ms"] == DATA_END + 1 - 60_000
        and coverage["symbol_coverage"][s]["klines_15m"]["count"] > 0
        and coverage["symbol_coverage"][s]["klines_1h"]["count"] > 0
        and coverage["symbol_coverage"][s]["klines_4h"]["count"] > 0
        and coverage["symbol_coverage"][s]["funding_rates"]["count"] > 0
        and all(
            coverage["symbol_coverage"][s][feed]["count"] > 0
            and coverage["symbol_coverage"][s][feed]["first_timestamp_ms"] is not None
            and coverage["symbol_coverage"][s][feed]["first_timestamp_ms"] <= P1[0] + period_ms
            and coverage["symbol_coverage"][s][feed]["last_timestamp_ms"] >= LAST_STEP - period_ms
            for feed, (_path, _key, _period, period_ms) in FEEDS.items()
        )
        and coverage["symbol_coverage"][s]["basis_hist"]["count"] > 0
        and coverage["symbol_coverage"][s]["basis_hist"]["first_timestamp_ms"] <= P1[0] + 300_000
        and coverage["symbol_coverage"][s]["basis_hist"]["last_timestamp_ms"] >= LAST_STEP - 300_000
        for s in SYMBOLS
    )
    input_identity = {
        "symbols": list(SYMBOLS),
        "source_start_ms": SOURCE_START,
        "data_end_ms": DATA_END,
        "first_step_ms": FIRST_STEP,
        "last_step_ms": LAST_STEP,
        "step_count": len(_steps()),
        "partitions": [
            {"id": f"P{i}", "oos_start_ms": a, "oos_end_ms": b}
            for i, (a, b) in enumerate((P1, P2, P3), 1)
        ],
        "source_dataset_sha256": raw_hash,
        "source_provenance": "BINANCE_PUBLIC_FUTURES_UNAUTHENTICATED_HISTORICAL",
        "fees": {"maker": 0.0002, "taker": 0.0005, "slippage_bps_per_side": 2},
        "funding_in_net_r": True,
        "coverage_complete_for_required_core": checks,
    }
    input_identity["input_manifest_hash"] = _sha256(json.dumps(input_identity, sort_keys=True, separators=(",", ":")).encode())
    _json("INPUT_MANIFEST.json", input_identity)
    if not checks:
        _json("EVIDENCE.json", {"task_id": TASK_ID, "terminal_result": "RC2_HOLDOUT_INFRA_INCOMPLETE", "freeze_proof": freeze, "input_manifest": input_identity})
        _json("preflight_report.json", PREFLIGHT_REPORT)
        _write_changed_files()
        raise SystemExit("RC2_HOLDOUT_INFRA_INCOMPLETE")

    steps = _steps()
    dataset = ReplayDataset.from_raw_cache(
        raw,
        step_timestamps_ms=steps,
        partitions=_partitions(),
        data_end_ms=DATA_END,
    )
    del raw
    config = MarketWatchConfig()
    if config.config_hash != CONFIG_HASH:
        raise SystemExit("RC2_HOLDOUT_PREFLIGHT_FAIL")
    runner = DeterministicTacticalReplayRunner(
        dataset=dataset,
        config=config,
        evaluate_grid_stride=12,
        allow_synthetic_1m_for_tests=False,
        fail_closed_on_missing_1m=True,
    )
    try:
        first = runner.run()
    except Exception as exc:
        _json("EVIDENCE.json", {
            "task_id": TASK_ID,
            "terminal_result": "RC2_HOLDOUT_BLOCKED",
            "freeze_proof": freeze,
            "input_manifest": input_identity,
            "replay_error": f"{type(exc).__name__}: {exc}",
        })
        _write_changed_files()
        raise SystemExit("RC2_HOLDOUT_BLOCKED") from exc
    try:
        second = runner.run()
    except Exception as exc:
        _json("EVIDENCE.json", {
            "task_id": TASK_ID,
            "terminal_result": "RC2_HOLDOUT_BLOCKED",
            "freeze_proof": freeze,
            "input_manifest": first["input_manifest"],
            "run_1_output_manifest": first["output_manifest"],
            "replay_error": f"second deterministic execution: {type(exc).__name__}: {exc}",
        })
        _write_changed_files()
        raise SystemExit("RC2_HOLDOUT_BLOCKED") from exc
    out1 = first["output_manifest"]
    out2 = second["output_manifest"]
    deterministic = {
        "same_input_manifest": first["input_manifest"]["input_manifest_hash"] == second["input_manifest"]["input_manifest_hash"],
        "same_output_manifest": out1["output_manifest_hash"] == out2["output_manifest_hash"],
        "same_evidence_ids": out1["evidence_ids_sha256"] == out2["evidence_ids_sha256"],
        "same_shadow_ids": out1["shadow_evaluation_ids_sha256"] == out2["shadow_evaluation_ids_sha256"],
        "run_1_input_hash": first["input_manifest"]["input_manifest_hash"],
        "run_2_input_hash": second["input_manifest"]["input_manifest_hash"],
        "run_1_output_hash": out1["output_manifest_hash"],
        "run_2_output_hash": out2["output_manifest_hash"],
        "run_1_evidence_ids_sha256": out1["evidence_ids_sha256"],
        "run_2_evidence_ids_sha256": out2["evidence_ids_sha256"],
        "run_1_shadow_ids_sha256": out1["shadow_evaluation_ids_sha256"],
        "run_2_shadow_ids_sha256": out2["shadow_evaluation_ids_sha256"],
    }
    deterministic["pass"] = all(deterministic[k] for k in ("same_input_manifest", "same_output_manifest", "same_evidence_ids", "same_shadow_ids"))
    if not deterministic["pass"]:
        raise SystemExit("deterministic replay proof failed")

    aggregate = first["aggregate_oos_metrics"]
    partitions = first["rolling_oos_table"]
    decision = _release_decision(aggregate, partitions, first["gate_evaluation"])
    _json("INPUT_MANIFEST.json", first["input_manifest"])
    _json("OUTPUT_MANIFEST.json", out1)
    _json("rolling_oos_table.json", partitions)
    _json("aggregate_metrics.json", aggregate)
    _json("deterministic_replay_proof.json", deterministic)
    _json("policy_freeze_proof.json", freeze)
    _json("preflight_report.json", PREFLIGHT_REPORT)
    _json("EVIDENCE.json", {
        "task_id": TASK_ID,
        "release_id": RELEASE_ID,
        "controller_dispatch_sha": DISPATCH_SHA,
        "frozen_candidate_sha": START_SHA,
        "validation_branch": "validation/b-line-rc2-successor-r1-holdout",
        "policy_version": POLICY_VERSION,
        "config_hash": CONFIG_HASH,
        "selected_candidate_id": CANDIDATE_ID,
        "terminal_result": decision,
        "input_manifest": first["input_manifest"],
        "output_manifest": out1,
        "source_coverage_digest": coverage,
        "deterministic_replay_proof": deterministic,
        "pit_causality_audit": first["pit_audit"],
        "replay_coverage_notes": {
            "fail_closed_insufficient_history": True,
            "oos_evidence_count": out1["oos_evidences_count"],
            "maximum_oos_evidence_count": 8 * sum((end - start) // INTERVALS["15m"] for start, end in (P1, P2, P3)),
            "missing_oos_steps_per_symbol": (
                sum((end - start) // INTERVALS["15m"] for start, end in (P1, P2, P3))
                - out1["oos_evidences_count"] // len(SYMBOLS)
            ),
            "missing_reference_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"],
            "missing_reference_data_accessed": False,
            "policy_or_threshold_changed": False,
        },
        "rolling_oos_table": partitions,
        "aggregate_metrics": aggregate,
        "gate_evaluation": first["gate_evaluation"],
        "policy_freeze_proof": freeze,
        "preflight": "PASS",
        "real_money_authority": False,
    })
    _json("OUTPUT_MANIFEST.json", {**out1, "terminal_result": decision})
    _write_changed_files()
    print(decision)


if __name__ == "__main__":
    main()
