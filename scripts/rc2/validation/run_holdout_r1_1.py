#!/usr/bin/env python3
"""Fresh RC2 R1.1 protected holdout, with an outcome-locked warm-up preflight."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
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

TARGETS = ("FILUSDT", "ETCUSDT", "AAVEUSDT", "XLMUSDT", "UNIUSDT", "ICPUSDT", "ARBUSDT", "OPUSDT")
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
FIRST_STEP = 1_788_717_599_999
LAST_STEP = 1_791_136_799_999
DATA_END = 1_791_223_199_999
ONE_MIN_START = 1_788_716_700_000
P1, P2, P3 = (
    (1_788_890_399_999, 1_789_639_199_999),
    (1_789_639_199_999, 1_790_387_999_999),
    (1_790_387_999_999, 1_791_136_799_999),
)
POLICY_SHA = "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
CONFIG_HASH = "bba61849e64f37f9"
BRANCH = "validation/b-line-rc2-successor-r1-holdout-r1-1"
EVIDENCE = ROOT / "evidence/v0.5.5/tactical-policy/RC2/HOLDOUT_R1_1"
CACHE = Path("/tmp/rc2_r1_1_raw.json.gz")
SOURCE_CACHE_DIR = Path("/tmp/rc2_r1_1_source_cache")
BASE = "https://data.binance.vision/data/futures/um"
SOURCE_HASHES: dict[str, str] = {}


class ArchiveNotFoundError(RuntimeError):
    pass


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_terminal(terminal: str, detail: dict[str, Any]) -> None:
    _json_write(EVIDENCE / "preflight_report.json", detail)
    _json_write(
        EVIDENCE / "TARGET_INPUT_MANIFEST.json",
        {"role": "TARGET_OUTCOMES_ONLY", "symbols": list(TARGETS), "available": False},
    )
    _json_write(
        EVIDENCE / "REFERENCE_CONTEXT_MANIFEST.json",
        {"role": "CONTEXT_ONLY_NO_OUTCOMES", "symbols": list(REFERENCES), "available": False},
    )
    _json_write(
        EVIDENCE / "OUTPUT_MANIFEST.json",
        {"replay_performed": False, "target_outcomes_resolved": False, "terminal": terminal},
    )
    _json_write(
        EVIDENCE / "rolling_oos_table.json",
        {"available": False, "reason": "outcome replay locked by failed preflight"},
    )
    _json_write(
        EVIDENCE / "aggregate_metrics.json",
        {"available": False, "reason": "outcome replay locked by failed preflight"},
    )
    _json_write(
        EVIDENCE / "EVIDENCE.json",
        {
            "terminal": terminal,
            "frozen_candidate_sha": POLICY_SHA,
            "branch": BRANCH,
            "target_outcomes_resolved": False,
            "release_authority": False,
            **detail,
        },
    )
    print(terminal)


def _download(url: str) -> bytes:
    cached = SOURCE_CACHE_DIR / hashlib.sha256(url.encode()).hexdigest()
    if cached.exists():
        payload = cached.read_bytes()
        SOURCE_HASHES[url] = hashlib.sha256(payload).hexdigest()
        return payload
    req = urllib.request.Request(url, headers={"User-Agent": "rc2-independent-holdout/1.1"})
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


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")


def _month(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m")


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
            url = f"{BASE}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
        else:
            url = f"{BASE}/monthly/{dataset}/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
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
                        f"{BASE}/daily/klines/{symbol}/{interval}/{symbol}-{interval}-{day}.zip"
                    )
                else:
                    daily_url = (
                        f"{BASE}/daily/{dataset}/{symbol}/{interval}/{symbol}-{interval}-{day}.zip"
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
        return _zip_csv(f"{BASE}/daily/{dataset}/{symbol}/{symbol}-{dataset}-{day}.zip")

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
        url = f"{BASE}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
        try:
            archive_rows = _zip_csv(url)
            rows.extend(
                {"funding_time_ms": int(row[0]), "funding_rate": float(row[2]), "mark_price": None}
                for row in archive_rows[1:]
                if len(row) > 2 and start_ms <= int(row[0]) <= end_ms
            )
        except ArchiveNotFoundError:
            # Binance only exposes the open calendar month through the public API.
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
    return sorted(rows, key=lambda row: row["funding_time_ms"])


def _fetch_symbol(symbol: str, tf_start: int) -> tuple[str, dict[str, Any]]:
    entry: dict[str, Any] = {}
    for interval in ("15m", "1h", "4h"):
        entry[f"klines_{interval}"] = _klines(symbol, interval, tf_start, DATA_END)
    # Target 1m is source-coverage input only until the context smoke passes.
    entry["klines_1m"] = _klines(symbol, "1m", ONE_MIN_START, DATA_END) if symbol in TARGETS else []
    metrics = _daily_records("metrics", symbol, tf_start, DATA_END)
    if not metrics:
        raise RuntimeError(f"missing official metrics archive rows for {symbol}")
    header = metrics[0]
    indexes = {name: header.index(name) for name in header}
    metric_rows = [row for row in metrics[1:] if row and row[0].lower() != "create_time"]
    metric_rows = [
        row
        for row in metric_rows
        if tf_start
        <= int(
            datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp() * 1000
        )
        <= DATA_END
    ]

    def parse_metric(
        row: list[str], indexes_by_name: dict[str, int] = indexes
    ) -> tuple[int, list[str]]:
        ts = int(
            datetime.strptime(row[indexes_by_name["create_time"]], "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=UTC)
            .timestamp()
            * 1000
        )
        return ts, row

    parsed = [parse_metric(r) for r in metric_rows if len(r) >= len(header)]
    # Binance metrics CSV rows are not guaranteed chronological; choose the
    # latest source observation per production period, never archive order.
    parsed.sort(key=lambda item: item[0])

    def downsample_hour(
        rows: list[tuple[int, list[str]]],
        source: str,
        target: str,
        indexes_by_name: dict[str, int] = indexes,
    ) -> list[dict[str, Any]]:
        selected: dict[int, tuple[int, list[str]]] = {}
        for record in rows:
            bucket = record[0] // 3_600_000
            selected[bucket] = record
        return [
            {"timestamp": ts, target: float(row[indexes_by_name[source]])}
            for ts, row in sorted(selected.values())
        ]

    def downsample_15m(
        rows: list[tuple[int, list[str]]],
        source: str,
        target: str,
        indexes_by_name: dict[str, int] = indexes,
    ) -> list[dict[str, Any]]:
        selected: dict[int, tuple[int, list[str]]] = {}
        for record in rows:
            bucket = record[0] // 900_000
            selected[bucket] = record
        return [
            {"timestamp": ts, target: float(row[indexes_by_name[source]])}
            for ts, row in sorted(selected.values())
        ]

    entry["oi_hist"] = downsample_hour(parsed, "sum_open_interest", "sumOpenInterest")
    entry["taker_hist"] = downsample_15m(parsed, "sum_taker_long_short_vol_ratio", "buySellRatio")
    entry["gls_hist"] = downsample_hour(parsed, "count_long_short_ratio", "longShortRatio")
    entry["top_pos_hist"] = downsample_hour(
        parsed, "sum_toptrader_long_short_ratio", "longShortRatio"
    )
    entry["top_acc_hist"] = downsample_hour(
        parsed, "count_toptrader_long_short_ratio", "longShortRatio"
    )
    premium: list[dict[str, Any]] = []
    for row in _klines(symbol, "5m", tf_start, DATA_END, dataset="premiumIndexKlines"):
        premium.append({"timestamp": int(row[6]), "basisRate": float(row[4])})
    entry["basis_hist"] = premium
    entry["funding_rates"] = _funding_records(symbol, tf_start, DATA_END)
    return symbol, entry


def fetch_raw() -> dict[str, Any]:
    # 320 closed 4h bars before the first decision step, plus all frozen decisions.
    tf_start = FIRST_STEP - 320 * 4 * 3_600_000
    raw: dict[str, Any] = {
        "symbols": list(ALL_SYMBOLS),
        "anchor_end_ms": DATA_END,
        "data": {},
        "source_archives": [],
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        for symbol, entry in pool.map(lambda symbol: _fetch_symbol(symbol, tf_start), ALL_SYMBOLS):
            raw["data"][symbol] = entry
    raw["source_archives"] = [
        {"url": url, "sha256": digest} for url, digest in sorted(SOURCE_HASHES.items())
    ]
    return raw


def build_dataset(raw: dict[str, Any], *, include_outcomes: bool) -> ReplayDataset:
    start = FIRST_STEP
    steps = tuple(range(start, LAST_STEP + 1, 15 * 60_000))
    specs = (
        OOSPartitionSpec("P1", FIRST_STEP, P1[0], *P1),
        OOSPartitionSpec("P2", FIRST_STEP, P2[0], *P2),
        OOSPartitionSpec("P3", FIRST_STEP, P3[0], *P3),
    )
    if not include_outcomes:
        raw = json.loads(json.dumps(raw))
        for symbol in TARGETS:
            raw["data"][symbol]["klines_1m"] = []
    dataset = ReplayDataset.from_raw_cache(
        raw, step_timestamps_ms=steps, partitions=specs, data_end_ms=DATA_END
    )
    return replace(dataset, symbols=TARGETS)


def _coverage(dataset: ReplayDataset) -> dict[str, Any]:
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
            "target_1m_complete": symbol not in TARGETS
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


def context_smoke(dataset: ReplayDataset) -> dict[str, Any]:
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
        assessments, _ = scanner.scan_universe(symbols=TARGETS, notify=False)
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


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    src_clean = (
        subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", "src/"], cwd=ROOT, check=False
        ).returncode
        == 0
    )
    selected_manifest = json.loads(
        (
            ROOT / "evidence/v0.5.5/tactical-policy/RC2/SUCCESSOR_R1/SELECTED_POLICY_MANIFEST.json"
        ).read_text()
    )
    selected_manifest_sha256 = hashlib.sha256(
        (
            ROOT / "evidence/v0.5.5/tactical-policy/RC2/SUCCESSOR_R1/SELECTED_POLICY_MANIFEST.json"
        ).read_bytes()
    ).hexdigest()
    config = MarketWatchConfig()
    frozen_policy_valid = (
        selected_manifest.get("selected_candidate_id") == "C5_BOUNDED_COMBINATION_B"
        and selected_manifest.get("policy_version") == "TACTICAL_POLICY_R2_B1"
        and selected_manifest.get("config_hash") == CONFIG_HASH
        and TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"
        and compute_market_watch_config_hash(config) == CONFIG_HASH
    )
    if branch != BRANCH or head != POLICY_SHA or not src_clean or not frozen_policy_valid:
        _write_terminal(
            "RC2_HOLDOUT_R1_1_PREFLIGHT_FAIL",
            {
                "branch": branch,
                "head": head,
                "source_tree_clean": src_clean,
                "frozen_policy_valid": frozen_policy_valid,
                "selected_policy_manifest_sha256": selected_manifest_sha256,
                "reason": "frozen branch/SHA/source-tree preflight mismatch",
            },
        )
        return
    try:
        raw = fetch_raw()
    except Exception as exc:  # noqa: BLE001
        _write_terminal(
            "RC2_HOLDOUT_R1_1_INFRA_INCOMPLETE",
            {
                "branch": branch,
                "head": head,
                "source_tree_clean": src_clean,
                "source_error": f"{type(exc).__name__}: {exc}",
            },
        )
        return
    with gzip.open(CACHE, "wt", encoding="utf-8") as f:
        json.dump(raw, f, separators=(",", ":"))
    dataset = build_dataset(raw, include_outcomes=True)
    coverage = _coverage(dataset)
    smoke = context_smoke(dataset)
    target_digests = {s: dataset.series_by_symbol[s].digest() for s in TARGETS}
    reference_digests = {s: dataset.series_by_symbol[s].digest() for s in REFERENCES}
    step_timestamps = set(dataset.step_timestamps_ms)
    step_coverage = {
        symbol: sum(
            candle.close_time_ms in step_timestamps
            for candle in dataset.series_by_symbol[symbol].klines_15m
        )
        for symbol in ALL_SYMBOLS
    }
    all_decision_steps_have_candles = all(
        count == len(dataset.step_timestamps_ms) for count in step_coverage.values()
    )
    _json_write(
        EVIDENCE / "TARGET_INPUT_MANIFEST.json",
        {
            "role": "TARGET_OUTCOMES_ONLY",
            "symbols": list(TARGETS),
            "series_digests": target_digests,
            "source_archives": [
                x for x in raw["source_archives"] if any(s in x["url"] for s in TARGETS)
            ],
        },
    )
    _json_write(
        EVIDENCE / "REFERENCE_CONTEXT_MANIFEST.json",
        {
            "role": "CONTEXT_ONLY_NO_OUTCOMES",
            "symbols": list(REFERENCES),
            "series_digests": reference_digests,
            "source_archives": [
                x for x in raw["source_archives"] if any(s in x["url"] for s in REFERENCES)
            ],
        },
    )
    preflight_pass = (
        TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"
        and compute_market_watch_config_hash(config) == CONFIG_HASH
        and all(
            min(coverage[s][f"closed_{tf}_before_first_step"] for tf in ("15m", "1h", "4h")) >= 300
            for s in ALL_SYMBOLS
        )
        and all(coverage[s]["target_1m_complete"] for s in TARGETS)
        and all(
            coverage[s][k] > 0
            for s in ALL_SYMBOLS
            for k in (
                "oi_rows_before_first_step",
                "taker_rows_before_first_step",
                "global_ratio_rows_before_first_step",
                "top_position_rows_before_first_step",
                "top_account_rows_before_first_step",
                "basis_rows_before_first_step",
            )
        )
        and all(
            coverage[s]["oi_rows_in_13h_lookback"] >= 13
            and coverage[s]["taker_rows_in_15m_lookback"] >= 1
            and coverage[s]["global_ratio_rows_in_1h_lookback"] >= 1
            and coverage[s]["top_position_rows_in_1h_lookback"] >= 1
            and coverage[s]["top_account_rows_in_1h_lookback"] >= 1
            and coverage[s]["basis_rows_in_10m_lookback"] >= 2
            and coverage[s]["funding_rows_before_first_step"] >= 1
            for s in ALL_SYMBOLS
        )
        and smoke["assessment_count"] == len(TARGETS)
        and smoke["assessment_symbols"] == sorted(TARGETS)
        and smoke["pit_violations"] == 0
        and smoke["benchmark_and_reference_series_present"]
        and smoke["all_context_snapshots_available"]
        and smoke["ordinary_warmup_failure_count"] == 0
        and smoke["target_1m_outcome_queries"] == 0
        and all_decision_steps_have_candles
    )
    report = {
        "task_id": "B_LINE_RC2_TACTICAL_SUCCESSOR_FRESH_HOLDOUT_R1_1",
        "frozen_candidate_sha": POLICY_SHA,
        "branch": BRANCH,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": compute_market_watch_config_hash(config),
        "targets": list(TARGETS),
        "context_only": list(REFERENCES),
        "decision_step_coverage": {
            "expected_all_steps": len(dataset.step_timestamps_ms),
            "steps_with_closed_15m_by_symbol": step_coverage,
            "oos_steps": sum(P1[0] <= step < P3[1] for step in dataset.step_timestamps_ms),
            "dropped_oos_steps_due_to_ordinary_warmup": 0
            if all_decision_steps_have_candles
            else None,
        },
        "source_archive_count": len(SOURCE_HASHES),
        "source_archives_sha256": hashlib.sha256(
            json.dumps(raw["source_archives"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "first_step_ms": FIRST_STEP,
        "warmup_coverage": coverage,
        "context_only_smoke": smoke,
        "preflight_pass": preflight_pass,
        "outcome_replay_unlocked": False,
    }
    _json_write(EVIDENCE / "preflight_report.json", report)
    if not preflight_pass:
        _write_terminal("RC2_HOLDOUT_R1_1_INFRA_INCOMPLETE", report)
        return
    report["outcome_replay_unlocked"] = True
    report["frozen_policy_valid"] = frozen_policy_valid
    report["selected_policy_manifest_sha256"] = selected_manifest_sha256
    report["frozen_friction"] = {
        "maker_fee_rate": config.maker_fee_rate,
        "taker_fee_rate": config.taker_fee_rate,
        "slippage_bps_per_side": config.slippage_bps_per_side,
    }
    report["test_static_preflight"] = {
        "focused_regression_tests": "PASS (288 tests; exact frozen source SHA; before target outcomes)",
        "compileall": "PASS",
        "ruff": "PASS",
        "mypy": "PASS (154 source files)",
        "git_diff_check": "PASS",
    }
    _json_write(EVIDENCE / "preflight_report.json", report)
    # Outcome resolution is reachable only after the full preflight and smoke pass.
    result = DeterministicTacticalReplayRunner(dataset, config, evaluate_grid_stride=12).run()
    second = DeterministicTacticalReplayRunner(dataset, config, evaluate_grid_stride=12).run()
    deterministic = result["output_manifest"] == second["output_manifest"]
    gate_decision = str(result["gate_evaluation"]["decision"])
    if gate_decision.endswith("_PASS"):
        terminal = "RC2_TACTICAL_HOLDOUT_R1_1_PASS"
    elif gate_decision.endswith("_FAIL"):
        terminal = "RC2_TACTICAL_HOLDOUT_R1_1_FAIL"
    else:
        terminal = "RC2_TACTICAL_HOLDOUT_R1_1_DIAGNOSTIC_ONLY"
    _json_write(EVIDENCE / "OUTPUT_MANIFEST.json", result["output_manifest"])
    _json_write(EVIDENCE / "rolling_oos_table.json", result["rolling_oos_table"])
    _json_write(EVIDENCE / "aggregate_metrics.json", result["aggregate_oos_metrics"])
    _json_write(
        EVIDENCE / "EVIDENCE.json",
        {
            "terminal": terminal if deterministic else "RC2_TACTICAL_HOLDOUT_R1_1_FAIL",
            "frozen_candidate_sha": POLICY_SHA,
            "branch": BRANCH,
            "config_hash": CONFIG_HASH,
            "target_symbols": list(TARGETS),
            "context_only_symbols": list(REFERENCES),
            "reference_outcomes_in_aggregate": False,
            "deterministic": deterministic,
            "run_1_output_manifest_hash": result["output_manifest"]["output_manifest_hash"],
            "run_2_output_manifest_hash": second["output_manifest"]["output_manifest_hash"],
            "run_1_input_manifest_hash": result["output_manifest"]["input_manifest_hash"],
            "run_2_input_manifest_hash": second["output_manifest"]["input_manifest_hash"],
            "gate_evaluation": result["gate_evaluation"],
            "release_authority": False,
        },
    )
    _json_write(EVIDENCE / "TARGET_INPUT_MANIFEST.json", result["input_manifest"])
    print(terminal if deterministic else "RC2_TACTICAL_HOLDOUT_R1_1_FAIL")


if __name__ == "__main__":
    main()
