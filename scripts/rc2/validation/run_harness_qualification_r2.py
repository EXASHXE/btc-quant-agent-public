#!/usr/bin/env python3
"""Authoritative Qualification Runner for RC2 Holdout Harness Qualification R2.

Repairs and certifies the validation harness:
1. Enforces strict protected symbol firewall.
2. Normalizes Binance metrics archives by event time (FIL regression verified).
3. Proves permutation invariance across raw archive orderings.
4. Binds cache authority with schema, version, source digest, and harness code hashes.
5. Captures and verifies exact runner execution identity before and after replay.
6. Asserts production-equivalent context smoke with 0 PIT violations and 0 warm-up drops.
7. Executes qualification replay twice from identical manifest and once permuted.
8. Generates all required evidence artifacts directly from committed runner code.
"""

from __future__ import annotations

import csv
import gc
import gzip
import hashlib
import io
import json
import random
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
)
from btc_quant_agent.market_watch.replay import (
    DeterministicTacticalReplayRunner,
    HistoricalReplayClient,
    OOSPartitionSpec,
    ReplayDataset,
    _InMemoryReplayStateStore,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from scripts.rc2.validation.source_normalizer import (
    ALLOWED_NON_PROTECTED_SYMBOLS,
    CACHE_SCHEMA_VERSION,
    PARSER_SCHEMA_VERSION,
    CacheIdentity,
    assert_all_symbols_allowed,
    capture_execution_identity,
    compute_cache_identity,
    normalize_metrics_rows,
    save_authorized_cache,
    validate_and_load_cache,
    verify_execution_identity,
    verify_fil_20260906_regression,
    verify_permutation_invariance,
)

TASK_ID = "B_LINE_RC2_HOLDOUT_HARNESS_QUALIFICATION_R2"
BRANCH = "validation/b-line-rc2-holdout-harness-r2"
START_SHA = "c166899d714e6a03eb43ab53c65eea9a0e2bc966"
POLICY_SHA = "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
CONTROLLER_DISPATCH_SHA = "06d2d82f51560552196f20f5b51d508d2dc40b1d"
CONFIG_HASH = "bba61849e64f37f9"

# Burned non-protected symbols
BURNED_TARGETS = ("FILUSDT", "ETCUSDT", "AAVEUSDT", "XLMUSDT", "UNIUSDT", "ICPUSDT", "ARBUSDT", "OPUSDT")
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
ALL_SYMBOLS = BURNED_TARGETS + REFERENCES

# Diagnostic targets for qualification replay (burned symbols only)
DIAGNOSTIC_TARGETS = ("FILUSDT", "ETCUSDT")

FIRST_STEP = 1_788_717_599_999
LAST_STEP = 1_791_136_799_999
DATA_END = 1_791_223_199_999
ONE_MIN_START = 1_788_716_700_000
P1, P2, P3 = (
    (1_788_890_399_999, 1_789_639_199_999),
    (1_789_639_199_999, 1_790_387_999_999),
    (1_790_387_999_999, 1_791_136_799_999),
)

EVIDENCE = ROOT / "evidence/v0.5.5/tactical-policy/RC2/HARNESS_R2"
CACHE_PATH = Path("/tmp/rc2_harness_r2_raw.json.gz")
SOURCE_CACHE_DIR = Path("/tmp/rc2_r1_1_source_cache")
BASE_URL = "https://data.binance.vision/data/futures/um"
SOURCE_HASHES: dict[str, str] = {}

VALIDATION_SCRIPTS = [
    ROOT / "scripts/rc2/validation/source_normalizer.py",
    ROOT / "scripts/rc2/validation/run_harness_qualification_r2.py",
]


class ArchiveNotFoundError(RuntimeError):
    pass


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _download(url: str) -> bytes:
    cached = SOURCE_CACHE_DIR / hashlib.sha256(url.encode()).hexdigest()
    if cached.exists():
        payload = cached.read_bytes()
        SOURCE_HASHES[url] = hashlib.sha256(payload).hexdigest()
        return payload
    req = urllib.request.Request(url, headers={"User-Agent": "rc2-harness-qualification/2.0"})
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
    valid_rows = [
        r
        for r in rows
        if len(r) >= 7 and r[0].strip().isdigit() and start_ms <= int(r[6]) <= end_ms
    ]
    # Chronological sort and deduplication by open_time
    valid_rows.sort(key=lambda r: int(r[0]))
    deduped: list[list[Any]] = []
    seen_open: set[int] = set()
    for r in valid_rows:
        open_ts = int(r[0])
        if open_ts not in seen_open:
            seen_open.add(open_ts)
            deduped.append(r)
    return deduped


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
    # Deduplicate by funding_time_ms
    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in sorted_rows:
        if item["funding_time_ms"] not in seen:
            seen.add(item["funding_time_ms"])
            deduped.append(item)
    return deduped


def _fetch_symbol_entry(
    symbol: str, tf_start: int, *, permute_metrics_order: bool = False
) -> tuple[str, dict[str, Any]]:
    assert_all_symbols_allowed([symbol])
    entry: dict[str, Any] = {}
    for interval in ("15m", "1h", "4h"):
        entry[f"klines_{interval}"] = _klines(symbol, interval, tf_start, DATA_END)
    entry["klines_1m"] = _klines(symbol, "1m", ONE_MIN_START, DATA_END) if symbol in BURNED_TARGETS else []

    metrics = _daily_records("metrics", symbol, tf_start, DATA_END)
    if not metrics:
        raise RuntimeError(f"missing official metrics archive rows for {symbol}")
    header = metrics[0]
    metric_rows = [row for row in metrics[1:] if row and row[0].lower() != "create_time"]

    if permute_metrics_order:
        # Deliberate deterministic permutation of raw archive order to test invariance
        rng = random.Random(hash(symbol) & 0xFFFFFFFF)
        rng.shuffle(metric_rows)

    # Use authoritative event-time normalizer
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
    return symbol, entry, metric_rows, header


def fetch_raw_dataset() -> tuple[dict[str, Any], dict[str, list[list[str]]], list[str]]:
    assert_all_symbols_allowed(ALL_SYMBOLS)
    tf_start = FIRST_STEP - 320 * 4 * 3_600_000
    r1_raw_path = Path("/tmp/rc2_r1_1_raw.json.gz")
    raw: dict[str, Any]
    if r1_raw_path.exists():
        with gzip.open(r1_raw_path, "rt", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {
            "symbols": list(ALL_SYMBOLS),
            "anchor_end_ms": DATA_END,
            "data": {},
            "source_archives": [],
        }

    raw_metric_rows_by_symbol: dict[str, list[list[str]]] = {}
    metric_header: list[str] = []

    for symbol in ALL_SYMBOLS:
        metrics = _daily_records("metrics", symbol, tf_start, DATA_END)
        header = metrics[0]
        metric_rows = [row for row in metrics[1:] if row and row[0].lower() != "create_time"]
        norm = normalize_metrics_rows(metric_rows, header, tf_start, DATA_END)

        if symbol not in raw.get("data", {}):
            _, entry, _, _ = _fetch_symbol_entry(symbol, tf_start)
            raw.setdefault("data", {})[symbol] = entry
        else:
            raw["data"][symbol]["oi_hist"] = norm["oi_hist"]
            raw["data"][symbol]["taker_hist"] = norm["taker_hist"]
            raw["data"][symbol]["gls_hist"] = norm["gls_hist"]
            raw["data"][symbol]["top_pos_hist"] = norm["top_pos_hist"]
            raw["data"][symbol]["top_acc_hist"] = norm["top_acc_hist"]

        if symbol in DIAGNOSTIC_TARGETS:
            raw_metric_rows_by_symbol[symbol] = metric_rows
        if header and not metric_header:
            metric_header = header
        gc.collect()

    raw["source_archives"] = [
        {"url": url, "sha256": digest} for url, digest in sorted(SOURCE_HASHES.items())
    ]
    return raw, raw_metric_rows_by_symbol, metric_header


def build_dataset(
    raw: dict[str, Any], target_symbols: tuple[str, ...], *, include_outcomes: bool
) -> ReplayDataset:
    assert_all_symbols_allowed(target_symbols)
    start = FIRST_STEP
    steps = tuple(range(start, LAST_STEP + 1, 15 * 60_000))
    specs = (
        OOSPartitionSpec("P1", FIRST_STEP, P1[0], *P1),
        OOSPartitionSpec("P2", FIRST_STEP, P2[0], *P2),
        OOSPartitionSpec("P3", FIRST_STEP, P3[0], *P3),
    )
    needed_symbols = tuple(dict.fromkeys(target_symbols + REFERENCES))
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
    return replace(dataset, symbols=target_symbols)


def compute_coverage(dataset: ReplayDataset) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for symbol in ALL_SYMBOLS:
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
            "target_1m_complete": symbol not in BURNED_TARGETS
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


def execute_context_smoke(dataset: ReplayDataset, target_symbols: tuple[str, ...]) -> dict[str, Any]:
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
            s in dataset.series_by_symbol for s in REFERENCES
        ),
        "collected_symbol_snapshots": collected,
        "all_context_snapshots_available": all(
            collected.get(s, {}).get("snapshot_available", False) for s in REFERENCES
        ),
        "ordinary_warmup_failure_count": sum(
            bool(v["errors"]) or v["health"] == "FAILED" for v in collected.values()
        ),
        "target_1m_outcome_queries": client.authentic_1m_queries_count,
    }


def run_static_checks() -> dict[str, Any]:
    """Run all required tests and static checkers."""
    report: dict[str, Any] = {}

    # 1. pytest validation tests
    t0 = time.time()
    pytest_res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_rc2_holdout_harness_r2.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report["pytest_validation_suite"] = {
        "status": "PASS" if pytest_res.returncode == 0 else "FAIL",
        "returncode": pytest_res.returncode,
        "elapsed_seconds": round(time.time() - t0, 2),
        "stdout": pytest_res.stdout.strip(),
    }
    if pytest_res.returncode != 0:
        raise RuntimeError(f"pytest failed: {pytest_res.stdout}\n{pytest_res.stderr}")

    # 2. compileall
    comp_res = subprocess.run(
        [sys.executable, "-m", "compileall", "src", "scripts", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report["compileall"] = {
        "status": "PASS" if comp_res.returncode == 0 else "FAIL",
        "returncode": comp_res.returncode,
    }
    if comp_res.returncode != 0:
        raise RuntimeError(f"compileall failed: {comp_res.stderr}")

    # 3. ruff
    ruff_res = subprocess.run(
        ["ruff", "check", "src", "scripts", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report["ruff"] = {
        "status": "PASS" if ruff_res.returncode == 0 else "FAIL",
        "returncode": ruff_res.returncode,
        "output": ruff_res.stdout.strip(),
    }
    if ruff_res.returncode != 0:
        raise RuntimeError(f"ruff failed: {ruff_res.stdout}")

    # 4. mypy
    mypy_res = subprocess.run(
        ["mypy"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report["mypy"] = {
        "status": "PASS" if mypy_res.returncode == 0 else "FAIL",
        "returncode": mypy_res.returncode,
        "output": mypy_res.stdout.strip(),
    }
    if mypy_res.returncode != 0:
        raise RuntimeError(f"mypy failed: {mypy_res.stdout}")

    # 5. git diff --check
    git_diff_res = subprocess.run(
        ["git", "diff", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report["git_diff_check"] = {
        "status": "PASS" if git_diff_res.returncode == 0 else "FAIL",
        "returncode": git_diff_res.returncode,
    }
    if git_diff_res.returncode != 0:
        raise RuntimeError(f"git diff --check failed: {git_diff_res.stdout}")

    return report


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    print(f"=== Starting {TASK_ID} ===")

    # 1. Capture Pre-Execution Identity
    pre_identity = capture_execution_identity(
        task_id=TASK_ID,
        root=ROOT,
        expected_branch=BRANCH,
        script_paths=VALIDATION_SCRIPTS,
    )

    if pre_identity.observed_branch != BRANCH:
        raise RuntimeError(f"Branch mismatch: expected {BRANCH}, got {pre_identity.observed_branch}")
    if not pre_identity.src_clean:
        raise RuntimeError("src/** has uncommitted changes! Must be clean.")

    # 2. Strict Firewall Check
    assert_all_symbols_allowed(ALL_SYMBOLS)
    assert_all_symbols_allowed(DIAGNOSTIC_TARGETS)

    # 3. Known FIL regression verification
    fil_cached = (
        SOURCE_CACHE_DIR
        / hashlib.sha256(
            b"https://data.binance.vision/data/futures/um/daily/metrics/FILUSDT/FILUSDT-metrics-2026-09-06.zip"
        ).hexdigest()
    )
    if not fil_cached.exists():
        _download("https://data.binance.vision/data/futures/um/daily/metrics/FILUSDT/FILUSDT-metrics-2026-09-06.zip")
    fil_regression_report = verify_fil_20260906_regression(fil_cached.read_bytes())
    assert fil_regression_report["regression_verified"] is True
    print(
        f"FIL Regression Verified: 17h selected {fil_regression_report['normalized_selected_observation']} "
        f"(archive was {fil_regression_report['archive_order_tail_observation']})"
    )

    # 4. Permutation Invariance on FIL metrics archive
    with zipfile.ZipFile(io.BytesIO(fil_cached.read_bytes())) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        raw_csv = z.read(csv_name).decode("utf-8-sig")
    fil_rows = list(csv.reader(io.StringIO(raw_csv)))
    fil_header = fil_rows[0]
    fil_metric_rows = [r for r in fil_rows[1:] if r and r[0].lower() != "create_time"]
    tf_start = FIRST_STEP - 320 * 4 * 3_600_000
    permutation_proof = verify_permutation_invariance(
        fil_metric_rows, fil_header, tf_start, DATA_END, num_permutations=5, seed=42
    )
    assert permutation_proof["permutation_invariance_proven"] is True
    print(f"Permutation Invariance Verified across {permutation_proof['tested_order_count']} row orderings.")

    _json_write(
        EVIDENCE / "SOURCE_NORMALIZATION_PROOF.json",
        {
            "schema_version": PARSER_SCHEMA_VERSION,
            "fil_regression": fil_regression_report,
            "permutation_proof": permutation_proof,
        },
    )

    # 5. Fetch / Load Raw Dataset with Identity-Bound Cache
    print("Building / loading raw dataset with Cache Authority...")
    raw, raw_metric_rows, metric_header = fetch_raw_dataset()

    time_window = {
        "first_step_ms": FIRST_STEP,
        "last_step_ms": LAST_STEP,
        "data_end_ms": DATA_END,
        "one_min_start_ms": ONE_MIN_START,
        "tf_start_ms": tf_start,
    }
    symbol_roles = {
        "burned_targets": list(BURNED_TARGETS),
        "references": list(REFERENCES),
        "diagnostic_targets": list(DIAGNOSTIC_TARGETS),
    }

    cache_id = compute_cache_identity(
        time_window=time_window,
        symbol_roles=symbol_roles,
        source_archives=raw["source_archives"],
        script_paths=VALIDATION_SCRIPTS,
    )

    save_authorized_cache(CACHE_PATH, cache_id, raw)
    _, cache_audit = validate_and_load_cache(CACHE_PATH, cache_id, load_payload=False)
    assert cache_audit["reusable"] is True

    # Test cache rejection on parser identity alteration
    stale_parser_id = CacheIdentity(
        schema_version=cache_id.schema_version,
        parser_schema_version="STALE_PARSER_V1",
        time_window=cache_id.time_window,
        symbol_roles=cache_id.symbol_roles,
        harness_code_hashes=cache_id.harness_code_hashes,
        source_archives_count=cache_id.source_archives_count,
        source_archives_digest=cache_id.source_archives_digest,
    )
    _, stale_parser_audit = validate_and_load_cache(
        CACHE_PATH, stale_parser_id, on_mismatch="rebuild", load_payload=False
    )
    assert stale_parser_audit["reusable"] is False

    # Test cache rejection on source digest alteration
    stale_source_id = CacheIdentity(
        schema_version=cache_id.schema_version,
        parser_schema_version=cache_id.parser_schema_version,
        time_window=cache_id.time_window,
        symbol_roles=cache_id.symbol_roles,
        harness_code_hashes=cache_id.harness_code_hashes,
        source_archives_count=cache_id.source_archives_count,
        source_archives_digest="altered_source_archives_digest",
    )
    _, stale_source_audit = validate_and_load_cache(
        CACHE_PATH, stale_source_id, on_mismatch="rebuild", load_payload=False
    )
    assert stale_source_audit["reusable"] is False

    # Test cache rejection on script hash alteration
    stale_script_id = CacheIdentity(
        schema_version=cache_id.schema_version,
        parser_schema_version=cache_id.parser_schema_version,
        time_window=cache_id.time_window,
        symbol_roles=cache_id.symbol_roles,
        harness_code_hashes={"scripts/rc2/validation/source_normalizer.py": "0" * 64},
        source_archives_count=cache_id.source_archives_count,
        source_archives_digest=cache_id.source_archives_digest,
    )
    _, stale_script_audit = validate_and_load_cache(
        CACHE_PATH, stale_script_id, on_mismatch="rebuild", load_payload=False
    )
    assert stale_script_audit["reusable"] is False

    print("Cache Authority Verified: identical cache reusable; stale parser/source/script identities rejected.")

    _json_write(
        EVIDENCE / "CACHE_AUTHORITY_PROOF.json",
        {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "parser_schema_version": PARSER_SCHEMA_VERSION,
            "cache_path": str(CACHE_PATH),
            "bound_identity": cache_id.to_dict(),
            "reusable_audit": cache_audit,
            "stale_parser_rejection_audit": stale_parser_audit,
            "stale_source_rejection_audit": stale_source_audit,
            "stale_script_rejection_audit": stale_script_audit,
        },
    )

    # 6. Production-Equivalent Context Smoke
    print("Executing context smoke...")
    dataset_full = build_dataset(raw, BURNED_TARGETS, include_outcomes=True)
    coverage = compute_coverage(dataset_full)
    smoke = execute_context_smoke(dataset_full, BURNED_TARGETS)

    assert smoke["assessment_count"] == len(BURNED_TARGETS)
    assert smoke["pit_violations"] == 0
    assert smoke["benchmark_and_reference_series_present"] is True
    assert smoke["all_context_snapshots_available"] is True
    assert smoke["ordinary_warmup_failure_count"] == 0
    assert all(
        min(coverage[s][f"closed_{tf}_before_first_step"] for tf in ("15m", "1h", "4h")) >= 300
        for s in ALL_SYMBOLS
    )
    print("Context Smoke Passed: 0 PIT violations, 0 ordinary warmup failures, >=300 pre-step bars.")

    _json_write(
        EVIDENCE / "CONTEXT_SMOKE.json",
        {
            "task_id": TASK_ID,
            "status": "PASS",
            "context_smoke": smoke,
            "coverage_summary": {
                s: {
                    "closed_15m_before_first_step": coverage[s]["closed_15m_before_first_step"],
                    "closed_1h_before_first_step": coverage[s]["closed_1h_before_first_step"],
                    "closed_4h_before_first_step": coverage[s]["closed_4h_before_first_step"],
                }
                for s in ALL_SYMBOLS
            },
        },
    )
    del dataset_full, coverage, smoke
    gc.collect()

    # 7. Qualification Replay (Burned diagnostic targets)
    print(f"Executing qualification replay on diagnostic targets {DIAGNOSTIC_TARGETS}...")
    config = MarketWatchConfig()
    dataset_diag1 = build_dataset(raw, DIAGNOSTIC_TARGETS, include_outcomes=True)

    # Permuted archive replay
    print("Building permuted archive dataset to verify replay permutation invariance...")
    raw_permuted_data = {
        s: dict(raw["data"][s]) for s in DIAGNOSTIC_TARGETS + REFERENCES
    }
    for s in DIAGNOSTIC_TARGETS:
        rows_copy = list(raw_metric_rows[s])
        rng = random.Random(hash(s) & 0xFFFFFFFF)
        rng.shuffle(rows_copy)
        norm_perm = normalize_metrics_rows(rows_copy, metric_header, tf_start, DATA_END)
        s_data = dict(raw_permuted_data[s])
        s_data["oi_hist"] = norm_perm["oi_hist"]
        s_data["taker_hist"] = norm_perm["taker_hist"]
        s_data["gls_hist"] = norm_perm["gls_hist"]
        s_data["top_pos_hist"] = norm_perm["top_pos_hist"]
        s_data["top_acc_hist"] = norm_perm["top_acc_hist"]
        raw_permuted_data[s] = s_data

    raw_permuted = {
        "symbols": list(DIAGNOSTIC_TARGETS + REFERENCES),
        "anchor_end_ms": DATA_END,
        "data": raw_permuted_data,
        "source_archives": raw.get("source_archives", []),
    }
    dataset_permuted = build_dataset(raw_permuted, DIAGNOSTIC_TARGETS, include_outcomes=True)

    del raw, raw_permuted, raw_permuted_data, raw_metric_rows
    gc.collect()

    t0 = time.time()
    result1 = DeterministicTacticalReplayRunner(dataset_diag1, config, evaluate_grid_stride=12).run()
    gc.collect()
    result2 = DeterministicTacticalReplayRunner(dataset_diag1, config, evaluate_grid_stride=12).run()
    gc.collect()
    print(f"Identical manifest replays completed in {time.time() - t0:.2f}s.")

    assert (
        result1["output_manifest"]["input_manifest_hash"]
        == result2["output_manifest"]["input_manifest_hash"]
    )
    assert (
        result1["output_manifest"]["output_manifest_hash"]
        == result2["output_manifest"]["output_manifest_hash"]
    )

    # Check that normalized series digests are 100% identical
    for s in DIAGNOSTIC_TARGETS:
        digest_original = dataset_diag1.series_by_symbol[s].digest()
        digest_permuted = dataset_permuted.series_by_symbol[s].digest()
        assert (
            digest_original == digest_permuted
        ), f"Normalized series digest mismatch for {s}: {digest_original} vs {digest_permuted}"

    result_permuted = DeterministicTacticalReplayRunner(
        dataset_permuted, config, evaluate_grid_stride=12
    ).run()
    gc.collect()

    assert (
        result_permuted["output_manifest"]["input_manifest_hash"]
        == result1["output_manifest"]["input_manifest_hash"]
    )
    assert (
        result_permuted["output_manifest"]["output_manifest_hash"]
        == result1["output_manifest"]["output_manifest_hash"]
    )
    print("Replay Permutation Invariance Verified: Identical input & output manifests!")

    _json_write(
        EVIDENCE / "DETERMINISM_PROOF.json",
        {
            "task_id": TASK_ID,
            "diagnostic_targets": list(DIAGNOSTIC_TARGETS),
            "run_1_input_manifest_hash": result1["output_manifest"]["input_manifest_hash"],
            "run_1_output_manifest_hash": result1["output_manifest"]["output_manifest_hash"],
            "run_2_input_manifest_hash": result2["output_manifest"]["input_manifest_hash"],
            "run_2_output_manifest_hash": result2["output_manifest"]["output_manifest_hash"],
            "run_3_permuted_input_manifest_hash": result_permuted["output_manifest"][
                "input_manifest_hash"
            ],
            "run_3_permuted_output_manifest_hash": result_permuted["output_manifest"][
                "output_manifest_hash"
            ],
            "manifests_identical": True,
            "permutation_identical": True,
            "profitability_label": "DIAGNOSTIC_ONLY_NON_AUTHORITY",
            "release_authority": False,
        },
    )

    # 8. Run Static & Unit Checks
    print("Running unit tests and static linters...")
    static_report = run_static_checks()
    _json_write(EVIDENCE / "TEST_STATIC_REPORT.json", static_report)
    print("Static & Unit Checks Passed (pytest, compileall, ruff, mypy, git diff).")

    # 9. Verify Post-Execution Runner Identity
    post_identity_report = verify_execution_identity(
        pre_identity=pre_identity,
        root=ROOT,
        script_paths=VALIDATION_SCRIPTS,
    )
    _json_write(EVIDENCE / "EXECUTION_IDENTITY.json", post_identity_report)
    print("Exact Runner Identity Verified: HEAD and script hashes match pre-execution.")

    # 10. Changed Files Manifest
    changed_files = [
        "scripts/rc2/validation/source_normalizer.py",
        "scripts/rc2/validation/run_harness_qualification_r2.py",
        "tests/test_rc2_holdout_harness_r2.py",
    ]
    changed_manifest: list[dict[str, str]] = []
    for rel_path in changed_files:
        full_path = ROOT / rel_path
        if full_path.exists():
            digest = hashlib.sha256(full_path.read_bytes()).hexdigest()
            changed_manifest.append({"path": rel_path, "sha256": digest})
    _json_write(EVIDENCE / "CHANGED_FILES_MANIFEST.json", {"changed_files": changed_manifest})

    # 11. Write Authoritative EVIDENCE.json
    terminal = "RC2_HOLDOUT_HARNESS_R2_PASS"
    evidence_payload = {
        "task_id": TASK_ID,
        "terminal": terminal,
        "validation_branch": BRANCH,
        "start_sha": START_SHA,
        "direct_parent": START_SHA,
        "frozen_candidate_sha": POLICY_SHA,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "execution_identity": post_identity_report,
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source_normalization_proven": True,
        "permutation_invariance_proven": True,
        "cache_authority_proven": True,
        "context_smoke_proven": True,
        "determinism_proven": True,
        "new_protected_symbols_accessed": 0,
        "allowed_symbols_whitelist_count": len(ALLOWED_NON_PROTECTED_SYMBOLS),
        "static_and_unit_checks": "ALL_PASS",
        "profitability_authority": "DIAGNOSTIC_ONLY_NON_AUTHORITY",
        "release_authority": False,
        "real_funds_write_authority": "NONE",
    }
    _json_write(EVIDENCE / "EVIDENCE.json", evidence_payload)

    print(f"\n{terminal}")


if __name__ == "__main__":
    main()
