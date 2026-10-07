#!/usr/bin/env python3
"""Authoritative Final Validation Runner for RC2 Holdout R3.

Frozen Policy SHA: 10be512f2cf4d7eccdc8a9849c925b5f73c568fd
Config Hash: bba61849e64f37f9
Controller Dispatch SHA: 2898f21a358177a02cb7e7f8812cec6984885388
Target Universe (Names Only until Execution):
  COMPUSDT, SANDUSDT, MANAUSDT, ALGOUSDT, EGLDUSDT, GALAUSDT, THETAUSDT, APTUSDT
Context-Only References:
  BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, SUIUSDT, XRPUSDT, DOGEUSDT, BNBUSDT

Two phases:
1. PRE-OUTCOME Phase:
   - Exact branch and git HEAD identity check
   - src/** equality to frozen policy SHA 10be512f...
   - Runner and normalizer SHA256 capture
   - Source and cache identity setup
   - Target / reference role separation verification
   - >=320 closed 4h, >=1280 closed 1h, >=5120 closed 15m before first decision step
   - Reference context smoke (all snapshots available, 0 PIT violations, 0 ordinary warmup drops)
   - Target authentic 1m completeness check (availability/coverage only, NO outcome metrics computed)
   - Fail closed before outcome aggregation on any preflight failure.
2. OUTCOME Phase:
   - Aggregate outcomes for R3 protected targets only (references remain context-only)
   - Exactly two identical-manifest replays
   - Evaluate frozen decision quality gates
   - Emit manifests, rolling OOS, aggregate metrics, and EVIDENCE.json
   - Post-execution runner identity assertion.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from btc_quant_agent.market_watch.config import (
    MarketWatchConfig,
    compute_market_watch_config_hash,
)
from btc_quant_agent.market_watch.domain import TACTICAL_POLICY_VERSION
from btc_quant_agent.market_watch.replay import (
    DeterministicTacticalReplayRunner,
    HistoricalReplayClient,
    OOSPartitionSpec,
    ReplayDataset,
    _InMemoryReplayStateStore,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from scripts.rc2.validation.source_normalizer import (
    capture_execution_identity,
    compute_cache_identity,
    normalize_metrics_rows,
    save_authorized_cache,
    validate_and_load_cache,
    verify_execution_identity,
)

# Hard-coded Frozen Constants
TASK_ID = "RC2_HOLDOUT_R3_EXECUTION"
CONSTRUCTION_TASK_ID = "RC2_HOLDOUT_R3_RUNNER_CONSTRUCTION_FREEZE"
BRANCH = "validation/b-line-rc2-holdout-r3-runner"
START_SHA = "cbc903d9ba448059121db96c3572a2677d5b53f8"
FROZEN_POLICY_SHA = "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
CONTROLLER_DISPATCH_SHA = "2898f21a358177a02cb7e7f8812cec6984885388"
CONFIG_HASH = "bba61849e64f37f9"
ACCEPTED_NORMALIZER_SHA256 = "4191922d1e85ad30b079633323836a817bf0506d223eb2365b2a4d3d25f52a16"

# Protected targets: Names only during construction; outcomes resolved only during execution.
TARGETS = (
    "COMPUSDT",
    "SANDUSDT",
    "MANAUSDT",
    "ALGOUSDT",
    "EGLDUSDT",
    "GALAUSDT",
    "THETAUSDT",
    "APTUSDT",
)

# Context-only references: Never evaluated for target outcomes.
REFERENCES = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
)

ALL_SYMBOLS = TARGETS + REFERENCES

# Frozen Temporal Windows and Partitions
FIRST_STEP = 1_788_717_599_999
LAST_STEP = 1_791_136_799_999
DATA_END = 1_791_223_199_999
ONE_MIN_START = 1_788_716_700_000
P1 = (1_788_890_399_999, 1_789_639_199_999)
P2 = (1_789_639_199_999, 1_790_387_999_999)
P3 = (1_790_387_999_999, 1_791_136_799_999)

# Frozen Friction
MAKER_FEE_RATE = 0.0002
TAKER_FEE_RATE = 0.0005
SLIPPAGE_BPS_PER_SIDE = 2.0

EVIDENCE_DIR = ROOT / "evidence/v0.5.5/tactical-policy/RC2/HOLDOUT_R3"
SOURCE_CACHE_DIR = Path("/tmp/rc2_r3_source_cache")
CACHE_PATH = Path("/tmp/rc2_r3_raw.json.gz")
BASE_URL = "https://data.binance.vision/data/futures/um"
SOURCE_HASHES: dict[str, str] = {}

VALIDATION_SCRIPTS = [
    ROOT / "scripts/rc2/validation/source_normalizer.py",
    ROOT / "scripts/rc2/validation/run_holdout_r3.py",
]


class ArchiveNotFoundError(RuntimeError):
    """Raised when an official archive URL returns HTTP 404."""


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _download(url: str) -> bytes:
    cached = SOURCE_CACHE_DIR / hashlib.sha256(url.encode()).hexdigest()
    if cached.exists():
        payload = cached.read_bytes()
        SOURCE_HASHES[url] = hashlib.sha256(payload).hexdigest()
        return payload
    req = urllib.request.Request(url, headers={"User-Agent": "rc2-holdout-r3-runner/1.0"})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                payload = response.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ArchiveNotFoundError(
                    f"official archive unavailable for {url}: HTTP 404"
                ) from exc
            last_error = exc
            if attempt == 3:
                raise RuntimeError(f"archive fetch failed for {url}: HTTP {exc.code}") from exc
            time.sleep(2**attempt)
        except Exception as exc:
            last_error = exc
            if attempt == 3:
                raise RuntimeError(
                    f"archive fetch failed for {url}: {type(exc).__name__}: {exc}"
                ) from exc
            time.sleep(2**attempt)
    else:
        raise RuntimeError(f"archive fetch failed for {url}: {last_error}")
    SOURCE_HASHES[url] = hashlib.sha256(payload).hexdigest()
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(payload)
    return payload


def _zip_csv(url: str) -> list[list[str]]:
    archive = zipfile.ZipFile(io.BytesIO(_download(url)))
    member = next(name for name in archive.namelist() if name.endswith(".csv"))
    return list(csv.reader(io.StringIO(archive.read(member).decode("utf-8-sig"))))


def _date_range(start_ms: int, end_ms: int) -> list[str]:
    start = datetime.fromtimestamp(start_ms / 1000, UTC).date()
    end = datetime.fromtimestamp(end_ms / 1000, UTC).date()
    days: list[str] = []
    while start <= end:
        days.append(start.isoformat())
        start = start.fromordinal(start.toordinal() + 1)
    return days


def _klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    dataset: str = "klines",
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    cur = datetime.fromtimestamp(start_ms / 1000, UTC).date().replace(day=1)
    last = datetime.fromtimestamp(end_ms / 1000, UTC).date().replace(day=1)
    while cur <= last:
        month = cur.strftime("%Y-%m")
        if dataset == "klines":
            url = f"{BASE_URL}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
        else:
            url = f"{BASE_URL}/monthly/{dataset}/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
        try:
            rows.extend(_zip_csv(url))
        except ArchiveNotFoundError:
            month_start = datetime(cur.year, cur.month, 1, tzinfo=UTC)
            if cur.month == 12:
                next_month = datetime(cur.year + 1, 1, 1, tzinfo=UTC)
            else:
                next_month = datetime(cur.year, cur.month + 1, 1, tzinfo=UTC)
            days = _date_range(
                int(month_start.timestamp() * 1000), int(next_month.timestamp() * 1000) - 1
            )
            for day in days:
                day_ms = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
                day_end = day_ms + 86_400_000 - 1
                if day_end < start_ms or day_ms > end_ms:
                    continue
                if dataset == "klines":
                    daily_url = (
                        f"{BASE_URL}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{day}.zip"
                    )
                else:
                    daily_url = (
                        f"{BASE_URL}/daily/{dataset}/{symbol}/{interval}/{symbol}-{interval}-{day}.zip"
                    )
                rows.extend(_zip_csv(daily_url))
        cur = cur.replace(
            year=cur.year + (cur.month == 12), month=1 if cur.month == 12 else cur.month + 1
        )
    return [
        r
        for r in rows
        if len(r) >= 7 and r[0].strip().isdigit() and start_ms <= int(r[6]) <= end_ms
    ]


def _daily_records(dataset: str, symbol: str, start_ms: int, end_ms: int) -> list[list[str]]:
    days = _date_range(start_ms, end_ms)

    def load_day(day: str) -> list[list[str]]:
        return _zip_csv(f"{BASE_URL}/daily/{dataset}/{symbol}/{symbol}-{dataset}-{day}.zip")

    with ThreadPoolExecutor(max_workers=6) as pool:
        groups = list(pool.map(load_day, days))
    rows = [row for group in groups for row in group]
    headers = [row for row in rows if row and row[0].lower() in {"create_time", "calc_time"}]
    records = [row for row in rows if row and row[0].lower() not in {"create_time", "calc_time"}]
    return ([headers[0]] if headers else []) + records


def _funding_records(symbol: str, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cur = datetime.fromtimestamp(start_ms / 1000, UTC).date().replace(day=1)
    last = datetime.fromtimestamp(end_ms / 1000, UTC).date().replace(day=1)
    while cur <= last:
        month = cur.strftime("%Y-%m")
        url = f"{BASE_URL}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
        try:
            archive_rows = _zip_csv(url)
            rows.extend(
                {"funding_time_ms": int(row[0]), "funding_rate": float(row[2]), "mark_price": None}
                for row in archive_rows[1:]
                if len(row) > 2 and start_ms <= int(row[0]) <= end_ms
            )
        except ArchiveNotFoundError:
            query = urllib.parse.urlencode(
                {
                    "symbol": symbol,
                    "startTime": max(
                        start_ms,
                        int(datetime(cur.year, cur.month, 1, tzinfo=UTC).timestamp() * 1000),
                    ),
                    "endTime": end_ms,
                    "limit": 1000,
                }
            )
            payload = json.loads(_download(f"https://fapi.binance.com/fapi/v1/fundingRate?{query}"))
            rows.extend(
                {
                    "funding_time_ms": int(item["fundingTime"]),
                    "funding_rate": float(item["fundingRate"]),
                    "mark_price": None,
                }
                for item in payload
            )
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    sorted_rows = sorted(rows, key=lambda row: row["funding_time_ms"])
    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in sorted_rows:
        if item["funding_time_ms"] not in seen:
            seen.add(item["funding_time_ms"])
            deduped.append(item)
    return deduped


def _fetch_symbol_entry(
    symbol: str, tf_start: int, *, is_target: bool
) -> tuple[str, dict[str, Any]]:
    entry: dict[str, Any] = {}
    for interval in ("15m", "1h", "4h"):
        entry[f"klines_{interval}"] = _klines(symbol, interval, tf_start, DATA_END)
    # Target 1m is source-coverage input only during preflight; references never have 1m
    entry["klines_1m"] = _klines(symbol, "1m", ONE_MIN_START, DATA_END) if is_target else []

    metrics = _daily_records("metrics", symbol, tf_start, DATA_END)
    if not metrics:
        raise RuntimeError(f"missing official metrics archive rows for {symbol}")
    header = metrics[0]
    metric_rows = [row for row in metrics[1:] if row and row[0].lower() != "create_time"]

    norm = normalize_metrics_rows(metric_rows, header, tf_start, DATA_END)
    entry["oi_hist"] = norm["oi_hist"]
    entry["taker_hist"] = norm["taker_hist"]
    entry["gls_hist"] = norm["gls_hist"]
    entry["top_pos_hist"] = norm["top_pos_hist"]
    entry["top_acc_hist"] = norm["top_acc_hist"]

    premium: list[dict[str, Any]] = []
    for row in _klines(symbol, "5m", tf_start, DATA_END, dataset="premiumIndexKlines"):
        premium.append({"timestamp": int(row[6]), "basisRate": float(row[4])})
    premium.sort(key=lambda item: item["timestamp"])
    deduped_basis: list[dict[str, Any]] = []
    seen_basis: set[int] = set()
    for item in premium:
        if item["timestamp"] not in seen_basis:
            seen_basis.add(item["timestamp"])
            deduped_basis.append(item)
    entry["basis_hist"] = deduped_basis

    entry["funding_rates"] = _funding_records(symbol, tf_start, DATA_END)
    return symbol, entry


def fetch_raw_dataset(
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Fetch or load raw market and archive data under cache identity binding."""
    tf_start = FIRST_STEP - 320 * 4 * 3_600_000
    all_symbols = target_symbols + reference_symbols

    raw: dict[str, Any] = {
        "symbols": list(all_symbols),
        "anchor_end_ms": DATA_END,
        "data": {},
        "source_archives": [],
    }

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(_fetch_symbol_entry, s, tf_start, is_target=(s in target_symbols))
            for s in all_symbols
        ]
        for f in futures:
            s, entry = f.result()
            raw["data"][s] = entry
            gc.collect()

    raw["source_archives"] = [
        {"url": url, "sha256": digest} for url, digest in sorted(SOURCE_HASHES.items())
    ]
    return raw


def build_dataset(
    raw: dict[str, Any],
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
    *,
    include_outcomes: bool,
) -> ReplayDataset:
    """Build PIT replay dataset where outcome resolution applies only to target symbols."""
    start = FIRST_STEP
    steps = tuple(range(start, LAST_STEP + 1, 15 * 60_000))
    specs = (
        OOSPartitionSpec("P1", FIRST_STEP, P1[0], *P1),
        OOSPartitionSpec("P2", FIRST_STEP, P2[0], *P2),
        OOSPartitionSpec("P3", FIRST_STEP, P3[0], *P3),
    )
    needed_symbols = tuple(dict.fromkeys(target_symbols + reference_symbols))
    filtered_data: dict[str, Any] = {}
    for s in needed_symbols:
        s_data = dict(raw["data"][s])
        if not include_outcomes or s not in target_symbols:
            s_data["klines_1m"] = []
        filtered_data[s] = s_data

    filtered_raw = {
        "symbols": list(needed_symbols),
        "anchor_end_ms": raw.get("anchor_end_ms", DATA_END),
        "data": filtered_data,
        "source_archives": raw.get("source_archives", []),
    }
    dataset = ReplayDataset.from_raw_cache(
        filtered_raw, step_timestamps_ms=steps, partitions=specs, data_end_ms=DATA_END
    )
    # symbols must contain ONLY targets to ensure references are context-only
    return replace(dataset, symbols=target_symbols)


def compute_coverage(
    dataset: ReplayDataset,
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Compute warm-up candle and derivative series coverage before the first step."""
    all_symbols = target_symbols + reference_symbols
    result: dict[str, Any] = {}
    for symbol in all_symbols:
        series = dataset.series_by_symbol[symbol]
        result[symbol] = {
            "closed_15m_before_first_step": sum(
                c.close_time_ms < FIRST_STEP for c in series.klines_15m
            ),
            "closed_1h_before_first_step": sum(
                c.close_time_ms < FIRST_STEP for c in series.klines_1h
            ),
            "closed_4h_before_first_step": sum(
                c.close_time_ms < FIRST_STEP for c in series.klines_4h
            ),
            "oi_rows_before_first_step": sum(
                int(x["timestamp"]) <= FIRST_STEP for x in series.oi_hist
            ),
            "oi_rows_in_13h_lookback": sum(
                FIRST_STEP - 13 * 3_600_000 < int(x["timestamp"]) <= FIRST_STEP
                for x in series.oi_hist
            ),
            "taker_rows_before_first_step": sum(
                int(x["timestamp"]) <= FIRST_STEP for x in series.taker_hist
            ),
            "taker_rows_in_15m_lookback": sum(
                FIRST_STEP - 15 * 60_000 < int(x["timestamp"]) <= FIRST_STEP
                for x in series.taker_hist
            ),
            "global_ratio_rows_before_first_step": sum(
                int(x["timestamp"]) <= FIRST_STEP for x in series.gls_hist
            ),
            "global_ratio_rows_in_1h_lookback": sum(
                FIRST_STEP - 3_600_000 < int(x["timestamp"]) <= FIRST_STEP for x in series.gls_hist
            ),
            "top_position_rows_before_first_step": sum(
                int(x["timestamp"]) <= FIRST_STEP for x in series.top_pos_hist
            ),
            "top_position_rows_in_1h_lookback": sum(
                FIRST_STEP - 3_600_000 < int(x["timestamp"]) <= FIRST_STEP
                for x in series.top_pos_hist
            ),
            "top_account_rows_before_first_step": sum(
                int(x["timestamp"]) <= FIRST_STEP for x in series.top_acc_hist
            ),
            "top_account_rows_in_1h_lookback": sum(
                FIRST_STEP - 3_600_000 < int(x["timestamp"]) <= FIRST_STEP
                for x in series.top_acc_hist
            ),
            "basis_rows_before_first_step": sum(
                int(x["timestamp"]) <= FIRST_STEP for x in series.basis_hist
            ),
            "basis_rows_in_10m_lookback": sum(
                FIRST_STEP - 10 * 60_000 < int(x["timestamp"]) <= FIRST_STEP
                for x in series.basis_hist
            ),
            "funding_rows_before_first_step": sum(
                int(x["funding_time_ms"]) <= FIRST_STEP for x in series.funding_rates
            ),
            "target_1m_count": len(series.klines_1m),
            "target_1m_complete": symbol not in target_symbols
            or (
                len(series.klines_1m) == 41_775
                and series.klines_1m[0].open_time_ms == ONE_MIN_START
                and series.klines_1m[-1].close_time_ms == DATA_END
                and all(
                    b.open_time_ms - a.open_time_ms == 60_000
                    for a, b in zip(series.klines_1m, series.klines_1m[1:])
                )
            ),
        }
    return result


def context_smoke(
    dataset: ReplayDataset,
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Execute smoke scan ensuring benchmark / context availability and zero PIT violations."""
    client = HistoricalReplayClient(dataset, FIRST_STEP, allow_synthetic_1m_for_tests=False)
    scanner = MarketWatchScanner(MarketWatchConfig(), client, _InMemoryReplayStateStore())
    collected: dict[str, dict[str, Any]] = {}
    original_collect = scanner.collect_symbol_snapshot

    def collect_with_audit(symbol: str, now_ms: int) -> Any:
        snap, health, errors = original_collect(symbol, now_ms)
        collected[symbol] = {
            "snapshot_available": snap is not None,
            "health": str(getattr(health, "value", health)),
            "errors": dict(errors),
        }
        return snap, health, errors

    scanner.collect_symbol_snapshot = collect_with_audit  # type: ignore[method-assign]
    import unittest.mock

    with unittest.mock.patch(
        "btc_quant_agent.market_watch.scanner.time.time", return_value=FIRST_STEP / 1000
    ):
        assessments, _ = scanner.scan_universe(symbols=target_symbols, notify=False)

    return {
        "assessment_symbols": sorted(a.symbol for a in assessments),
        "assessment_count": len(assessments),
        "pit_violations": client.pit_violations_count,
        "max_candle_close_ms": client.max_returned_candle_close_ms,
        "benchmark_and_reference_series_present": all(
            s in dataset.series_by_symbol for s in reference_symbols
        ),
        "collected_symbol_snapshots": collected,
        "all_context_snapshots_available": all(
            collected.get(s, {}).get("snapshot_available", False) for s in reference_symbols
        ),
        "ordinary_warmup_failure_count": sum(
            bool(v["errors"]) or v["health"] == "FAILED" for v in collected.values()
        ),
        "target_1m_outcome_queries": client.authentic_1m_queries_count,
    }


def write_preflight_failure(
    terminal: str,
    detail: dict[str, Any],
    evidence_dir: Path = EVIDENCE_DIR,
) -> None:
    """Fail closed when preflight verification rejects environment, data, or smoke."""
    _json_write(evidence_dir / "preflight_report.json", detail)
    _json_write(
        evidence_dir / "TARGET_INPUT_MANIFEST.json",
        {"role": "TARGET_OUTCOMES_ONLY", "symbols": list(TARGETS), "available": False},
    )
    _json_write(
        evidence_dir / "REFERENCE_CONTEXT_MANIFEST.json",
        {"role": "CONTEXT_ONLY_NO_OUTCOMES", "symbols": list(REFERENCES), "available": False},
    )
    _json_write(
        evidence_dir / "OUTPUT_MANIFEST.json",
        {"replay_performed": False, "target_outcomes_resolved": False, "terminal": terminal},
    )
    _json_write(
        evidence_dir / "rolling_oos_table.json",
        {"available": False, "reason": "outcome replay locked by failed preflight"},
    )
    _json_write(
        evidence_dir / "aggregate_metrics.json",
        {"available": False, "reason": "outcome replay locked by failed preflight"},
    )
    _json_write(
        evidence_dir / "EVIDENCE.json",
        {
            "task_id": TASK_ID,
            "terminal": terminal,
            "frozen_candidate_sha": FROZEN_POLICY_SHA,
            "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
            "branch": BRANCH,
            "target_outcomes_resolved": False,
            "release_authority": False,
            **detail,
        },
    )
    print(terminal)


def verify_freeze_identity(root: Path = ROOT) -> dict[str, Any]:
    """Verify runner freeze integrity and output construction freeze identity."""
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    diff_to_policy = subprocess.run(
        ["git", "diff", "--quiet", FROZEN_POLICY_SHA, "--", "src/"], cwd=root, check=False
    ).returncode
    src_matches_policy = diff_to_policy == 0

    diff_working_src = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "src/"], cwd=root, check=False
    ).returncode
    src_clean = diff_working_src == 0

    runner_path = root / "scripts/rc2/validation/run_holdout_r3.py"
    normalizer_path = root / "scripts/rc2/validation/source_normalizer.py"

    runner_sha256 = (
        hashlib.sha256(runner_path.read_bytes()).hexdigest() if runner_path.exists() else "MISSING"
    )
    normalizer_sha256 = (
        hashlib.sha256(normalizer_path.read_bytes()).hexdigest()
        if normalizer_path.exists()
        else "MISSING"
    )

    config = MarketWatchConfig()
    config_hash = compute_market_watch_config_hash(config)

    normalizer_match = normalizer_sha256 == ACCEPTED_NORMALIZER_SHA256
    policy_version_match = TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"
    config_hash_match = config_hash == CONFIG_HASH

    disjoint_roles = set(TARGETS).isdisjoint(set(REFERENCES))
    correct_target_count = len(TARGETS) == 8
    correct_ref_count = len(REFERENCES) == 8

    freeze_ok = (
        src_matches_policy
        and src_clean
        and normalizer_match
        and policy_version_match
        and config_hash_match
        and disjoint_roles
        and correct_target_count
        and correct_ref_count
    )

    return {
        "task_id": CONSTRUCTION_TASK_ID,
        "terminal": "RC2_HOLDOUT_R3_RUNNER_FROZEN_PENDING_EXECUTION"
        if freeze_ok
        else "RC2_HOLDOUT_R3_FREEZE_CHECK_FAIL",
        "branch": branch,
        "head": head,
        "start_sha": START_SHA,
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "config_hash": config_hash,
        "expected_config_hash": CONFIG_HASH,
        "policy_version": TACTICAL_POLICY_VERSION,
        "src_clean": src_clean,
        "src_matches_frozen_policy": src_matches_policy,
        "runner_sha256": runner_sha256,
        "normalizer_sha256": normalizer_sha256,
        "accepted_normalizer_sha256": ACCEPTED_NORMALIZER_SHA256,
        "normalizer_sha256_matches_accepted": normalizer_match,
        "targets": list(TARGETS),
        "references": list(REFERENCES),
        "target_reference_roles_disjoint": disjoint_roles,
        "time_window": {
            "first_step": FIRST_STEP,
            "last_step": LAST_STEP,
            "data_end": DATA_END,
            "one_min_start": ONE_MIN_START,
        },
        "friction": {
            "maker_fee_rate": MAKER_FEE_RATE,
            "taker_fee_rate": TAKER_FEE_RATE,
            "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
        },
        "protected_target_network_access_count": 0,
        "freeze_verified": freeze_ok,
    }


def execute_holdout(
    *,
    evidence_dir: Path = EVIDENCE_DIR,
    cache_path: Path = CACHE_PATH,
    root: Path = ROOT,
) -> None:
    """Execute the full two-phase R3 holdout validation under execution authorization."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Starting {TASK_ID} ===")

    # 1. Capture Pre-Execution Identity
    pre_identity = capture_execution_identity(
        task_id=TASK_ID,
        root=root,
        expected_branch=BRANCH,
        script_paths=VALIDATION_SCRIPTS,
    )

    # 2. Pre-Outcome Phase: Exact branch, clean src, frozen policy equality
    branch = pre_identity.observed_branch
    head = pre_identity.git_head
    src_clean = pre_identity.src_clean

    diff_to_policy = subprocess.run(
        ["git", "diff", "--quiet", FROZEN_POLICY_SHA, "--", "src/"], cwd=root, check=False
    ).returncode
    src_matches_policy = diff_to_policy == 0

    normalizer_hash = pre_identity.script_hashes.get(
        "scripts/rc2/validation/source_normalizer.py"
    ) or pre_identity.script_hashes.get("source_normalizer.py")
    normalizer_ok = normalizer_hash == ACCEPTED_NORMALIZER_SHA256

    config = MarketWatchConfig()
    config_hash = compute_market_watch_config_hash(config)
    policy_ok = (
        TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"
        and config_hash == CONFIG_HASH
        and config.maker_fee_rate == MAKER_FEE_RATE
        and config.taker_fee_rate == TAKER_FEE_RATE
        and config.slippage_bps_per_side == SLIPPAGE_BPS_PER_SIDE
    )

    if (
        branch != BRANCH
        or not src_clean
        or not src_matches_policy
        or not normalizer_ok
        or not policy_ok
    ):
        write_preflight_failure(
            "RC2_HOLDOUT_R3_PREFLIGHT_FAIL",
            {
                "branch": branch,
                "head": head,
                "src_clean": src_clean,
                "src_matches_policy": src_matches_policy,
                "normalizer_ok": normalizer_ok,
                "policy_ok": policy_ok,
                "reason": "Pre-outcome execution identity / environment mismatch",
            },
            evidence_dir,
        )
        return

    # 3. Source & Cache Identity Setup
    time_window = {
        "first_step": FIRST_STEP,
        "last_step": LAST_STEP,
        "data_end": DATA_END,
        "one_min_start": ONE_MIN_START,
    }
    symbol_roles = {
        "targets": list(TARGETS),
        "references": list(REFERENCES),
    }

    raw: dict[str, Any]
    try:
        # Check if cache exists and matches
        dummy_identity = compute_cache_identity(
            time_window=time_window,
            symbol_roles=symbol_roles,
            source_archives=[],
            script_paths=VALIDATION_SCRIPTS,
        )
        cached_data, _ = validate_and_load_cache(
            cache_path, dummy_identity, on_mismatch="rebuild", load_payload=True
        )
        if cached_data is not None:
            raw = cached_data
            print("Loaded validated cache matching identity.")
        else:
            print("Cache mismatch or not found; fetching official Binance Vision archives...")
            raw = fetch_raw_dataset(TARGETS, REFERENCES)
            cache_identity = compute_cache_identity(
                time_window=time_window,
                symbol_roles=symbol_roles,
                source_archives=raw["source_archives"],
                script_paths=VALIDATION_SCRIPTS,
            )
            save_authorized_cache(cache_path, cache_identity, raw)
            print("Saved authorized cache bound to identity.")
    except Exception as exc:  # noqa: BLE001
        write_preflight_failure(
            "RC2_HOLDOUT_R3_INFRA_INCOMPLETE",
            {
                "branch": branch,
                "head": head,
                "source_error": f"{type(exc).__name__}: {exc}",
                "reason": "Official archive retrieval failed",
            },
            evidence_dir,
        )
        return

    # 4. Build Dataset for Preflight (Outcomes locked)
    dataset_preflight = build_dataset(raw, TARGETS, REFERENCES, include_outcomes=False)
    coverage = compute_coverage(dataset_preflight, TARGETS, REFERENCES)
    smoke = context_smoke(dataset_preflight, TARGETS, REFERENCES)

    target_digests = {s: dataset_preflight.series_by_symbol[s].digest() for s in TARGETS}
    reference_digests = {s: dataset_preflight.series_by_symbol[s].digest() for s in REFERENCES}

    step_timestamps = set(dataset_preflight.step_timestamps_ms)
    step_coverage = {
        symbol: sum(
            candle.close_time_ms in step_timestamps
            for candle in dataset_preflight.series_by_symbol[symbol].klines_15m
        )
        for symbol in ALL_SYMBOLS
    }
    all_decision_steps_have_candles = all(
        count == len(dataset_preflight.step_timestamps_ms) for count in step_coverage.values()
    )

    # 5. Verify Preflight Gates
    warmup_4h_ok = all(coverage[s]["closed_4h_before_first_step"] >= 320 for s in ALL_SYMBOLS)
    warmup_1h_ok = all(coverage[s]["closed_1h_before_first_step"] >= 1280 for s in ALL_SYMBOLS)
    warmup_15m_ok = all(coverage[s]["closed_15m_before_first_step"] >= 5120 for s in ALL_SYMBOLS)
    lookback_ok = all(
        coverage[s]["oi_rows_in_13h_lookback"] >= 13
        and coverage[s]["taker_rows_in_15m_lookback"] >= 1
        and coverage[s]["global_ratio_rows_in_1h_lookback"] >= 1
        and coverage[s]["top_position_rows_in_1h_lookback"] >= 1
        and coverage[s]["top_account_rows_in_1h_lookback"] >= 1
        and coverage[s]["basis_rows_in_10m_lookback"] >= 2
        and coverage[s]["funding_rows_before_first_step"] >= 1
        for s in ALL_SYMBOLS
    )
    targets_1m_coverage_ok = all(
        raw["data"][s]["klines_1m"]
        and len(raw["data"][s]["klines_1m"]) == 41_775
        and int(raw["data"][s]["klines_1m"][0][0]) == ONE_MIN_START
        and int(raw["data"][s]["klines_1m"][-1][6]) == DATA_END
        for s in TARGETS
    )

    smoke_ok = (
        smoke["assessment_count"] == len(TARGETS)
        and smoke["assessment_symbols"] == sorted(TARGETS)
        and smoke["pit_violations"] == 0
        and smoke["benchmark_and_reference_series_present"]
        and smoke["all_context_snapshots_available"]
        and smoke["ordinary_warmup_failure_count"] == 0
        and smoke["target_1m_outcome_queries"] == 0
    )

    preflight_pass = (
        warmup_4h_ok
        and warmup_1h_ok
        and warmup_15m_ok
        and lookback_ok
        and targets_1m_coverage_ok
        and smoke_ok
        and all_decision_steps_have_candles
    )

    report: dict[str, Any] = {
        "task_id": TASK_ID,
        "frozen_candidate_sha": FROZEN_POLICY_SHA,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "branch": branch,
        "head": head,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": config_hash,
        "targets": list(TARGETS),
        "context_only": list(REFERENCES),
        "decision_step_coverage": {
            "expected_all_steps": len(dataset_preflight.step_timestamps_ms),
            "steps_with_closed_15m_by_symbol": step_coverage,
            "oos_steps": sum(
                P1[0] <= step < P3[1] for step in dataset_preflight.step_timestamps_ms
            ),
            "dropped_oos_steps_due_to_ordinary_warmup": 0
            if all_decision_steps_have_candles
            else None,
        },
        "source_archive_count": len(SOURCE_HASHES),
        "first_step_ms": FIRST_STEP,
        "warmup_coverage": coverage,
        "context_only_smoke": smoke,
        "preflight_pass": preflight_pass,
        "outcome_replay_unlocked": False,
    }
    _json_write(evidence_dir / "preflight_report.json", report)

    if not preflight_pass:
        write_preflight_failure("RC2_HOLDOUT_R3_PREFLIGHT_FAIL", report, evidence_dir)
        return

    # Clean preflight dataset to conserve memory
    del dataset_preflight, smoke
    gc.collect()

    # 6. Outcome Phase: Build Dataset with Target Outcomes Only
    print("Preflight gates passed. Unlocking outcome replay for protected targets...")
    report["outcome_replay_unlocked"] = True
    report["frozen_friction"] = {
        "maker_fee_rate": MAKER_FEE_RATE,
        "taker_fee_rate": TAKER_FEE_RATE,
        "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
    }
    _json_write(evidence_dir / "preflight_report.json", report)

    dataset_outcomes = build_dataset(raw, TARGETS, REFERENCES, include_outcomes=True)
    del raw
    gc.collect()

    # Run replay twice to guarantee determinism
    t0 = time.time()
    result1 = DeterministicTacticalReplayRunner(
        dataset_outcomes, config, evaluate_grid_stride=12
    ).run()
    gc.collect()
    result2 = DeterministicTacticalReplayRunner(
        dataset_outcomes, config, evaluate_grid_stride=12
    ).run()
    gc.collect()
    print(f"Replay completed in {time.time() - t0:.2f}s.")

    deterministic = (
        result1["output_manifest"]["input_manifest_hash"]
        == result2["output_manifest"]["input_manifest_hash"]
        and result1["output_manifest"]["output_manifest_hash"]
        == result2["output_manifest"]["output_manifest_hash"]
    )

    gate_decision = str(result1["gate_evaluation"]["decision"])
    if deterministic and gate_decision.endswith("_PASS"):
        terminal = "RC2_HOLDOUT_R3_PASS"
    elif deterministic and gate_decision.endswith("_FAIL"):
        terminal = "RC2_HOLDOUT_R3_FAIL"
    else:
        terminal = "RC2_HOLDOUT_R3_FAIL"

    # Manifests
    _json_write(
        evidence_dir / "TARGET_INPUT_MANIFEST.json",
        {
            "role": "TARGET_OUTCOMES_ONLY",
            "symbols": list(TARGETS),
            "series_digests": target_digests,
            "input_manifest_hash": result1["output_manifest"]["input_manifest_hash"],
        },
    )
    _json_write(
        evidence_dir / "REFERENCE_CONTEXT_MANIFEST.json",
        {
            "role": "CONTEXT_ONLY_NO_OUTCOMES",
            "symbols": list(REFERENCES),
            "series_digests": reference_digests,
        },
    )
    _json_write(evidence_dir / "OUTPUT_MANIFEST.json", result1["output_manifest"])
    _json_write(evidence_dir / "rolling_oos_table.json", result1["rolling_oos_table"])
    _json_write(evidence_dir / "aggregate_metrics.json", result1["aggregate_oos_metrics"])

    # Verify Post-Execution Runner Identity
    post_identity = verify_execution_identity(
        pre_identity=pre_identity,
        root=root,
        script_paths=VALIDATION_SCRIPTS,
    )
    _json_write(evidence_dir / "EXECUTION_IDENTITY.json", post_identity)

    # Write authoritative EVIDENCE.json
    evidence_payload = {
        "task_id": TASK_ID,
        "terminal": terminal,
        "frozen_candidate_sha": FROZEN_POLICY_SHA,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "branch": BRANCH,
        "config_hash": CONFIG_HASH,
        "target_symbols": list(TARGETS),
        "context_only_symbols": list(REFERENCES),
        "reference_outcomes_in_aggregate": False,
        "deterministic": deterministic,
        "run_1_output_manifest_hash": result1["output_manifest"]["output_manifest_hash"],
        "run_2_output_manifest_hash": result2["output_manifest"]["output_manifest_hash"],
        "run_1_input_manifest_hash": result1["output_manifest"]["input_manifest_hash"],
        "run_2_input_manifest_hash": result2["output_manifest"]["input_manifest_hash"],
        "gate_evaluation": result1["gate_evaluation"],
        "execution_identity": post_identity,
        "release_authority": terminal == "RC2_HOLDOUT_R3_PASS",
    }
    _json_write(evidence_dir / "EVIDENCE.json", evidence_payload)
    print(terminal)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RC2 Holdout R3 Authoritative Runner / Freeze Verifier"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize and execute the R3 holdout (requires execution dispatch)",
    )
    parser.add_argument(
        "--verify-freeze",
        action="store_true",
        help="Verify runner construction freeze without executing holdout",
    )
    args = parser.parse_args()

    # Execution authorization check
    env_authorized = os.environ.get("RC2_HOLDOUT_R3_EXECUTE") == "1"
    if args.execute or env_authorized:
        execute_holdout()
    else:
        # Freeze verification mode
        info = verify_freeze_identity()
        terminal = str(info["terminal"])
        print(f"=== {CONSTRUCTION_TASK_ID} ===")
        print(f"Branch: {info['branch']}")
        print(f"Head: {info['head']}")
        print(f"Start SHA: {info['start_sha']}")
        print(f"Frozen Policy SHA: {info['frozen_policy_sha']}")
        print(f"Runner SHA256: {info['runner_sha256']}")
        print(f"Normalizer SHA256: {info['normalizer_sha256']}")
        print(f"Protected target network accesses: {info['protected_target_network_access_count']}")
        print(f"Freeze Verified: {info['freeze_verified']}")
        print(f"\n{terminal}")
        if not info["freeze_verified"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
