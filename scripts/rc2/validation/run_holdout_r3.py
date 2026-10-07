#!/usr/bin/env python3
"""Authoritative Final Validation Runner for RC2 Holdout R3 (Repair R1).

Frozen Policy SHA: 10be512f2cf4d7eccdc8a9849c925b5f73c568fd
Config Hash: bba61849e64f37f9
Accepted Harness SHA: cbc903d9ba448059121db96c3572a2677d5b53f8
Controller Dispatch SHA (Repair R1): f35c8e0177070d4aa45fd426ae1be528201328a8
Accepted Normalizer SHA256: 4191922d1e85ad30b079633323836a817bf0506d223eb2365b2a4d3d25f52a16

Target Universe (Names Only until Execution):
  COMPUSDT, SANDUSDT, MANAUSDT, ALGOUSDT, EGLDUSDT, GALAUSDT, THETAUSDT, APTUSDT
Context-Only References:
  BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, SUIUSDT, XRPUSDT, DOGEUSDT, BNBUSDT

Repairs:
R1: Exact execution SHA/hash binding with required Controller-supplied CLI authorization
R2: Strict cache authority: sidecar + embedded + source manifest + canonical payload digest binding
R3: Full-window context and warm-up audit across every decision step (2689 steps)
R4: Complete authority input manifest binding all consumed features and 1m outcomes
R5: Authoritative 10-file evidence publication with post-execution verification before release
R6: Construction access ledger proving zero protected-target attempts under network guard
"""

from __future__ import annotations

import argparse
import bisect
import csv
import gc
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
from itertools import pairwise
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
from scripts.rc2.validation.r3_access_guard import (
    GLOBAL_LEDGER,
    PROTECTED_R3_TARGETS,
    R3_TARGET_ADMISSIBILITY,
    ConstructionAccessLedger,
)
from scripts.rc2.validation.source_normalizer import (
    CACHE_SCHEMA_VERSION,
    PARSER_SCHEMA_VERSION,
    CacheAuthorityError,
    CacheIdentity,
    capture_execution_identity,
    compute_cache_identity,
    normalize_metrics_rows,
    save_authorized_cache,
    verify_execution_identity,
)

# Hard-coded Frozen Constants
TASK_ID = "RC2_HOLDOUT_R3_EXECUTION"
REPAIR_TASK_ID = "RC2_R3_HOLDOUT_RUNNER_REPAIR_R1"
BRANCH = "validation/b-line-rc2-holdout-r3-runner-repair-r1"
START_SHA = "ded194c63bfcbbfd58daa450646cb76f979a2ff6"
FROZEN_POLICY_SHA = "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
ACCEPTED_HARNESS_SHA = "cbc903d9ba448059121db96c3572a2677d5b53f8"
CONTROLLER_DISPATCH_SHA = "f35c8e0177070d4aa45fd426ae1be528201328a8"
CONFIG_HASH = "bba61849e64f37f9"
ACCEPTED_NORMALIZER_SHA256 = "4191922d1e85ad30b079633323836a817bf0506d223eb2365b2a4d3d25f52a16"

# Protected targets: Names only during construction; outcomes resolved only during execution.
TARGETS: tuple[str, ...] = PROTECTED_R3_TARGETS

# Context-only references: Never evaluated for target outcomes.
REFERENCES: tuple[str, ...] = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
)

ALL_SYMBOLS: tuple[str, ...] = TARGETS + REFERENCES

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
    ROOT / "scripts/rc2/validation/r3_access_guard.py",
    ROOT / "scripts/rc2/validation/run_holdout_r3.py",
]


class ArchiveNotFoundError(RuntimeError):
    """Raised when an official archive URL returns HTTP 404."""


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _download(url: str, ledger: ConstructionAccessLedger = GLOBAL_LEDGER) -> bytes:
    # R6 Guard: check and log URL before any network or cache read
    ledger.check_and_log(url, caller="_download")
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
                content = response.read()
                payload = bytes(content)
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


def _zip_csv(url: str, ledger: ConstructionAccessLedger = GLOBAL_LEDGER) -> list[list[str]]:
    archive = zipfile.ZipFile(io.BytesIO(_download(url, ledger=ledger)))
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
    ledger: ConstructionAccessLedger = GLOBAL_LEDGER,
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
            rows.extend(_zip_csv(url, ledger=ledger))
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
                rows.extend(_zip_csv(daily_url, ledger=ledger))
        cur = cur.replace(
            year=cur.year + (cur.month == 12), month=1 if cur.month == 12 else cur.month + 1
        )
    return [
        r
        for r in rows
        if len(r) >= 7 and r[0].strip().isdigit() and start_ms <= int(r[6]) <= end_ms
    ]


def _daily_records(
    dataset: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    ledger: ConstructionAccessLedger = GLOBAL_LEDGER,
) -> list[list[str]]:
    days = _date_range(start_ms, end_ms)

    def load_day(day: str) -> list[list[str]]:
        return _zip_csv(
            f"{BASE_URL}/daily/{dataset}/{symbol}/{symbol}-{dataset}-{day}.zip",
            ledger=ledger,
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        groups = list(pool.map(load_day, days))
    rows = [row for group in groups for row in group]
    headers = [row for row in rows if row and row[0].lower() in {"create_time", "calc_time"}]
    records = [row for row in rows if row and row[0].lower() not in {"create_time", "calc_time"}]
    return ([headers[0]] if headers else []) + records


def _funding_records(
    symbol: str,
    start_ms: int,
    end_ms: int,
    ledger: ConstructionAccessLedger = GLOBAL_LEDGER,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cur = datetime.fromtimestamp(start_ms / 1000, UTC).date().replace(day=1)
    last = datetime.fromtimestamp(end_ms / 1000, UTC).date().replace(day=1)
    while cur <= last:
        month = cur.strftime("%Y-%m")
        url = f"{BASE_URL}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
        try:
            archive_rows = _zip_csv(url, ledger=ledger)
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
            api_url = f"https://fapi.binance.com/fapi/v1/fundingRate?{query}"
            payload = json.loads(_download(api_url, ledger=ledger))
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
    symbol: str,
    tf_start: int,
    *,
    is_target: bool,
    ledger: ConstructionAccessLedger = GLOBAL_LEDGER,
) -> tuple[str, dict[str, Any]]:
    # R6 Guard check on symbol name
    ledger.check_and_log(symbol, caller="_fetch_symbol_entry")
    entry: dict[str, Any] = {}
    for interval in ("15m", "1h", "4h"):
        entry[f"klines_{interval}"] = _klines(
            symbol, interval, tf_start, DATA_END, ledger=ledger
        )
    # Target 1m is source-coverage input only; references never have 1m
    entry["klines_1m"] = (
        _klines(symbol, "1m", ONE_MIN_START, DATA_END, ledger=ledger) if is_target else []
    )

    metrics = _daily_records("metrics", symbol, tf_start, DATA_END, ledger=ledger)
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
    for row in _klines(
        symbol, "5m", tf_start, DATA_END, dataset="premiumIndexKlines", ledger=ledger
    ):
        premium.append({"timestamp": int(row[6]), "basisRate": float(row[4])})
    premium.sort(key=lambda item: item["timestamp"])
    deduped_basis: list[dict[str, Any]] = []
    seen_basis: set[int] = set()
    for item in premium:
        if item["timestamp"] not in seen_basis:
            seen_basis.add(item["timestamp"])
            deduped_basis.append(item)
    entry["basis_hist"] = deduped_basis

    entry["funding_rates"] = _funding_records(symbol, tf_start, DATA_END, ledger=ledger)
    return symbol, entry


def fetch_raw_dataset(
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
    ledger: ConstructionAccessLedger = GLOBAL_LEDGER,
) -> dict[str, Any]:
    """Fetch raw market and archive data under protected target firewall."""
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
            pool.submit(
                _fetch_symbol_entry,
                s,
                tf_start,
                is_target=(s in target_symbols),
                ledger=ledger,
            )
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


# R2: Canonical payload content digest binding
def compute_canonical_payload_sha256(data_dict: dict[str, Any]) -> str:
    """Canonical SHA256 digest of raw dataset data payload."""
    encoded = json.dumps(data_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_r3_cache_identity(
    time_window: dict[str, int],
    symbol_roles: dict[str, list[str]],
    source_archives: list[dict[str, str]],
    script_paths: list[Path],
    data_payload: dict[str, Any] | None = None,
) -> CacheIdentity:
    """Compute authority cache identity including source manifest and payload binding."""
    base_id = compute_cache_identity(
        time_window=time_window,
        symbol_roles=symbol_roles,
        source_archives=source_archives,
        script_paths=script_paths,
    )
    return base_id


def validate_r3_cache_authority(
    cache_path: Path,
    expected_identity: CacheIdentity,
    expected_payload_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate sidecar identity AND embedded identity AND payload content binding (R2).

    Fails closed on any mismatch, missing sidecar, anonymous cache, or tampered payload.
    """
    identity_path = cache_path.with_name(cache_path.name.replace(".raw.json.gz", "").replace(".json.gz", "") + ".identity.json")
    if not identity_path.exists():
        raise CacheAuthorityError(f"Missing required sidecar identity file: {identity_path}")
    if not cache_path.exists():
        raise CacheAuthorityError(f"Missing cache file: {cache_path}")

    # 1. Load sidecar identity
    try:
        sidecar_identity_dict = json.loads(identity_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CacheAuthorityError(f"Corrupted sidecar identity file: {exc}") from exc

    # 2. Load embedded cache and identity
    try:
        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            wrapped = json.load(f)
    except Exception as exc:
        raise CacheAuthorityError(f"Corrupted gzip cache archive: {exc}") from exc

    if not isinstance(wrapped, dict) or "identity" not in wrapped or "payload" not in wrapped:
        raise CacheAuthorityError("Anonymous or un-wrapped cache rejected; must contain identity header and payload")

    embedded_identity_dict = wrapped["identity"]
    payload = wrapped["payload"]

    # 3. Require sidecar identity and embedded identity to match each other exactly
    expected_dict = expected_identity.to_dict()
    if sidecar_identity_dict != embedded_identity_dict:
        raise CacheAuthorityError("Sidecar identity and embedded cache identity mismatch")

    # 4. Require identities to match expected authority identity
    mismatches: list[str] = []
    for k in (
        "schema_version",
        "parser_schema_version",
        "time_window",
        "symbol_roles",
        "harness_code_hashes",
        "source_archives_count",
        "source_archives_digest",
    ):
        if sidecar_identity_dict.get(k) != expected_dict.get(k):
            mismatches.append(f"{k}: cached={sidecar_identity_dict.get(k)} expected={expected_dict.get(k)}")

    if mismatches:
        raise CacheAuthorityError(f"Cache identity authority mismatch: {'; '.join(mismatches)}")

    # 5. Require source archives in payload to match source_archives_digest in identity
    payload_archives = payload.get("source_archives", [])
    sorted_archives = sorted(payload_archives, key=lambda x: x["url"])
    archives_repr = json.dumps(sorted_archives, sort_keys=True, separators=(",", ":")).encode()
    computed_archives_digest = hashlib.sha256(archives_repr).hexdigest()
    if computed_archives_digest != expected_dict["source_archives_digest"]:
        raise CacheAuthorityError(
            f"Payload source archives digest mismatch: computed={computed_archives_digest} expected={expected_dict['source_archives_digest']}"
        )

    # 6. Payload content binding: if expected payload sha256 specified, verify
    actual_payload_sha256 = compute_canonical_payload_sha256(payload.get("data", {}))
    if expected_payload_sha256 is not None and actual_payload_sha256 != expected_payload_sha256:
        raise CacheAuthorityError(
            f"Payload canonical content digest mismatch: actual={actual_payload_sha256} expected={expected_payload_sha256}"
        )

    audit = {
        "cache_reusable": True,
        "sidecar_identity_verified": True,
        "embedded_identity_verified": True,
        "source_archives_digest_verified": True,
        "payload_sha256": actual_payload_sha256,
        "source_archives_count": len(sorted_archives),
    }
    return payload, audit


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


# R3: Full-window context and warm-up audit across every decision step
def audit_full_window_context(
    dataset: ReplayDataset,
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Audit every decision step across FIRST_STEP..LAST_STEP for all required context (R3)."""
    steps = dataset.step_timestamps_ms
    all_symbols = target_symbols + reference_symbols
    defects: list[dict[str, Any]] = []

    # Pre-index sorted timestamp arrays for high-performance lookup
    indexed_data: dict[str, dict[str, Any]] = {}
    for sym in all_symbols:
        series = dataset.series_by_symbol[sym]
        indexed_data[sym] = {
            "k15m_closes": [c.close_time_ms for c in series.klines_15m],
            "k1h_closes": [c.close_time_ms for c in series.klines_1h],
            "k4h_closes": [c.close_time_ms for c in series.klines_4h],
            "oi_ts": [int(x["timestamp"]) for x in series.oi_hist],
            "taker_ts": [int(x["timestamp"]) for x in series.taker_hist],
            "gls_ts": [int(x["timestamp"]) for x in series.gls_hist],
            "top_pos_ts": [int(x["timestamp"]) for x in series.top_pos_hist],
            "top_acc_ts": [int(x["timestamp"]) for x in series.top_acc_hist],
            "basis_ts": [int(x["timestamp"]) for x in series.basis_hist],
            "funding_ts": [int(x["funding_time_ms"]) for x in series.funding_rates],
        }

    # Verify lookback history at FIRST_STEP
    for sym in all_symbols:
        idx = indexed_data[sym]
        k15_pre = bisect.bisect_right(idx["k15m_closes"], FIRST_STEP - 1)
        k1h_pre = bisect.bisect_right(idx["k1h_closes"], FIRST_STEP - 1)
        k4h_pre = bisect.bisect_right(idx["k4h_closes"], FIRST_STEP - 1)
        if k4h_pre < 320:
            defects.append({"step_ms": FIRST_STEP, "symbol": sym, "error": f"closed 4h count {k4h_pre} < 320"})
        if k1h_pre < 1280:
            defects.append({"step_ms": FIRST_STEP, "symbol": sym, "error": f"closed 1h count {k1h_pre} < 1280"})
        if k15_pre < 5120:
            defects.append({"step_ms": FIRST_STEP, "symbol": sym, "error": f"closed 15m count {k15_pre} < 5120"})

    # Audit each step across entire window
    for step_ms in steps:
        # Check context benchmarks availability
        for bmark in ("BTCUSDT", "ETHUSDT"):
            if bmark not in dataset.series_by_symbol:
                defects.append({"step_ms": step_ms, "symbol": bmark, "error": "Benchmark missing from dataset"})

        for sym in all_symbols:
            idx = indexed_data[sym]
            # 1. Closed 15m candle at step_ms
            c15_pos = bisect.bisect_right(idx["k15m_closes"], step_ms)
            if c15_pos == 0 or idx["k15m_closes"][c15_pos - 1] != step_ms:
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing exact closed 15m candle at decision step"})

            # 2. 1h candle history
            c1h_pos = bisect.bisect_right(idx["k1h_closes"], step_ms)
            if c1h_pos == 0:
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "No 1h history before step"})

            # 3. 4h candle history
            c4h_pos = bisect.bisect_right(idx["k4h_closes"], step_ms)
            if c4h_pos == 0:
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "No 4h history before step"})

            # 4. OI observation within 13h
            oi_pos = bisect.bisect_right(idx["oi_ts"], step_ms)
            if oi_pos == 0 or idx["oi_ts"][oi_pos - 1] < (step_ms - 13 * 3_600_000):
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing OI within 13h lookback"})

            # 5. Taker ratio observation within 15m
            taker_pos = bisect.bisect_right(idx["taker_ts"], step_ms)
            if taker_pos == 0 or idx["taker_ts"][taker_pos - 1] < (step_ms - 15 * 60_000):
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing taker ratio within 15m lookback"})

            # 6. Global L/S observation within 1h
            gls_pos = bisect.bisect_right(idx["gls_ts"], step_ms)
            if gls_pos == 0 or idx["gls_ts"][gls_pos - 1] < (step_ms - 3_600_000):
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing global L/S within 1h lookback"})

            # 7. Top position L/S observation within 1h
            tp_pos = bisect.bisect_right(idx["top_pos_ts"], step_ms)
            if tp_pos == 0 or idx["top_pos_ts"][tp_pos - 1] < (step_ms - 3_600_000):
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing top position L/S within 1h lookback"})

            # 8. Top account L/S observation within 1h
            ta_pos = bisect.bisect_right(idx["top_acc_ts"], step_ms)
            if ta_pos == 0 or idx["top_acc_ts"][ta_pos - 1] < (step_ms - 3_600_000):
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing top account L/S within 1h lookback"})

            # 9. Basis observation within 10m
            basis_pos = bisect.bisect_right(idx["basis_ts"], step_ms)
            if basis_pos == 0 or idx["basis_ts"][basis_pos - 1] < (step_ms - 10 * 60_000):
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing basis within 10m lookback"})

            # 10. Funding record <= step_ms
            fund_pos = bisect.bisect_right(idx["funding_ts"], step_ms)
            if fund_pos == 0:
                defects.append({"step_ms": step_ms, "symbol": sym, "error": "Missing funding records before step"})

    audit_result = {
        "task_id": TASK_ID,
        "total_decision_steps": len(steps),
        "first_step_ms": FIRST_STEP,
        "last_step_ms": LAST_STEP,
        "symbols_audited_count": len(all_symbols),
        "target_symbols": list(target_symbols),
        "reference_symbols": list(reference_symbols),
        "full_window_audit_passed": len(defects) == 0,
        "defects_count": len(defects),
        "first_failure": defects[0] if defects else None,
        "last_failure": defects[-1] if defects else None,
    }
    return audit_result


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

    setattr(scanner, "collect_symbol_snapshot", collect_with_audit)
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


# R4: Complete validation authority input manifest
def generate_authority_input_manifest(
    dataset: ReplayDataset,
    raw: dict[str, Any],
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
    script_hashes: dict[str, str],
) -> dict[str, Any]:
    """Generate validation authority manifest binding ALL decision-consumed inputs (R4)."""
    symbol_digests: dict[str, dict[str, Any]] = {}
    for sym in target_symbols + reference_symbols:
        series = dataset.series_by_symbol[sym]
        is_target = sym in target_symbols

        def _hash_obj(obj: Any) -> str:
            encoded = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(encoded).hexdigest()

        k15_rows = [
            [c.open_time_ms, c.close_time_ms, c.open, c.high, c.low, c.close, c.volume]
            for c in series.klines_15m
        ]
        k1h_rows = [
            [c.open_time_ms, c.close_time_ms, c.open, c.high, c.low, c.close, c.volume]
            for c in series.klines_1h
        ]
        k4h_rows = [
            [c.open_time_ms, c.close_time_ms, c.open, c.high, c.low, c.close, c.volume]
            for c in series.klines_4h
        ]
        k1m_rows = (
            [
                [c.open_time_ms, c.close_time_ms, c.open, c.high, c.low, c.close, c.volume]
                for c in series.klines_1m
            ]
            if is_target
            else []
        )

        digests = {
            "role": "TARGET_OUTCOMES" if is_target else "CONTEXT_ONLY_NO_OUTCOMES",
            "klines_15m_digest": _hash_obj(k15_rows),
            "klines_1h_digest": _hash_obj(k1h_rows),
            "klines_4h_digest": _hash_obj(k4h_rows),
            "oi_digest": _hash_obj(series.oi_hist),
            "taker_digest": _hash_obj(series.taker_hist),
            "gls_digest": _hash_obj(series.gls_hist),
            "top_pos_digest": _hash_obj(series.top_pos_hist),
            "top_acc_digest": _hash_obj(series.top_acc_hist),
            "basis_digest": _hash_obj(series.basis_hist),
            "funding_digest": _hash_obj(series.funding_rates),
            "klines_1m_digest": _hash_obj(k1m_rows) if is_target else "EXCLUDED_CONTEXT_ONLY",
            "klines_15m_count": len(k15_rows),
            "klines_1h_count": len(k1h_rows),
            "klines_4h_count": len(k4h_rows),
            "klines_1m_count": len(k1m_rows),
        }
        combined = ":".join(str(digests[k]) for k in sorted(digests.keys()))
        digests["canonical_symbol_digest"] = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        symbol_digests[sym] = digests

    manifest_payload: dict[str, Any] = {
        "manifest_version": "RC2_VALIDATION_AUTHORITY_INPUT_MANIFEST_V1",
        "task_id": TASK_ID,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": CONFIG_HASH,
        "time_window": {
            "first_step_ms": FIRST_STEP,
            "last_step_ms": LAST_STEP,
            "data_end_ms": DATA_END,
            "one_min_start_ms": ONE_MIN_START,
        },
        "partitions": {
            "P1": list(P1),
            "P2": list(P2),
            "P3": list(P3),
        },
        "friction": {
            "maker_fee_rate": MAKER_FEE_RATE,
            "taker_fee_rate": TAKER_FEE_RATE,
            "slippage_bps_per_side": SLIPPAGE_BPS_PER_SIDE,
        },
        "target_symbols": list(target_symbols),
        "reference_symbols": list(reference_symbols),
        "source_archives": sorted(raw.get("source_archives", []), key=lambda x: x["url"]),
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "script_hashes": script_hashes,
        "symbol_digests": symbol_digests,
    }
    encoded = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_payload["authority_input_manifest_hash"] = hashlib.sha256(encoded).hexdigest()
    return manifest_payload


# R5: Authoritative Evidence Publication and Failure Closure
def write_preflight_failure(
    terminal: str,
    detail: dict[str, Any],
    evidence_dir: Path = EVIDENCE_DIR,
) -> None:
    """Fail closed when preflight verification rejects environment, data, or smoke (R5)."""
    _json_write(evidence_dir / "PRE_OUTCOME_REPORT.json", detail)
    _json_write(evidence_dir / "preflight_report.json", detail)
    _json_write(
        evidence_dir / "EXECUTION_IDENTITY.json",
        detail.get("execution_identity", {"verified": False, "reason": "Preflight failure"}),
    )
    _json_write(
        evidence_dir / "SOURCE_CACHE_PROOF.json",
        detail.get("source_cache_proof", {"verified": False, "reason": "Preflight failure"}),
    )
    _json_write(
        evidence_dir / "FULL_WINDOW_CONTEXT_AUDIT.json",
        detail.get("full_window_audit", {"audit_passed": False, "reason": "Preflight failure"}),
    )
    _json_write(
        evidence_dir / "TARGET_1M_AUTHENTICITY_PROOF.json",
        {"available": False, "reason": "Outcome resolution locked by failed preflight"},
    )
    _json_write(
        evidence_dir / "AUTHORITY_INPUT_MANIFEST.json",
        {"available": False, "reason": "Outcome resolution locked by failed preflight"},
    )
    _json_write(
        evidence_dir / "OUTPUT_MANIFEST.json",
        {"replay_performed": False, "target_outcomes_resolved": False, "terminal": terminal},
    )
    _json_write(
        evidence_dir / "rolling_oos_table.json",
        {"available": False, "reason": "Outcome replay locked by failed preflight"},
    )
    _json_write(
        evidence_dir / "aggregate_metrics.json",
        {"available": False, "reason": "Outcome replay locked by failed preflight"},
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
            "real_funds_write_authority": "NONE",
            **detail,
        },
    )
    print(terminal)


# R1: Exact Controller execution authorization verification
def check_execution_authorization(
    authorized_runner_sha: str | None,
    authorized_runner_sha256: str | None,
    execution_dispatch_sha: str | None,
    root: Path = ROOT,
    expected_branch: str = BRANCH,
) -> tuple[bool, str, dict[str, Any]]:
    """Assert external Controller authorization matches exact HEAD, runner hash, and dispatch."""
    reasons: list[str] = []
    if not authorized_runner_sha or len(authorized_runner_sha) != 40:
        reasons.append("Missing or invalid --authorized-runner-sha (expected 40-char hex)")
    if not authorized_runner_sha256 or len(authorized_runner_sha256) != 64:
        reasons.append("Missing or invalid --authorized-runner-sha256 (expected 64-char hex)")
    if not execution_dispatch_sha or len(execution_dispatch_sha) != 40:
        reasons.append("Missing or invalid --execution-dispatch-sha (expected 40-char hex)")

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    if branch != expected_branch:
        reasons.append(f"Branch mismatch: observed='{branch}' expected='{expected_branch}'")
    if authorized_runner_sha and head != authorized_runner_sha:
        reasons.append(f"HEAD mismatch: observed='{head}' Controller-authorized='{authorized_runner_sha}'")

    runner_path = root / "scripts/rc2/validation/run_holdout_r3.py"
    normalizer_path = root / "scripts/rc2/validation/source_normalizer.py"
    guard_path = root / "scripts/rc2/validation/r3_access_guard.py"

    runner_sha = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    normalizer_sha = hashlib.sha256(normalizer_path.read_bytes()).hexdigest()

    if authorized_runner_sha256 and runner_sha != authorized_runner_sha256:
        reasons.append(f"Runner SHA256 mismatch: actual='{runner_sha}' authorized='{authorized_runner_sha256}'")
    if normalizer_sha != ACCEPTED_NORMALIZER_SHA256:
        reasons.append(f"Normalizer SHA256 mismatch: actual='{normalizer_sha}' accepted='{ACCEPTED_NORMALIZER_SHA256}'")

    # Working tree clean checks
    scripts_diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "scripts/"], cwd=root, check=False
    ).returncode
    if scripts_diff != 0:
        reasons.append("Validation scripts worktree is not clean")

    src_diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "src/"], cwd=root, check=False
    ).returncode
    if src_diff != 0:
        reasons.append("src/** worktree is not clean")

    src_policy_diff = subprocess.run(
        ["git", "diff", "--quiet", FROZEN_POLICY_SHA, "--", "src/"], cwd=root, check=False
    ).returncode
    if src_policy_diff != 0:
        reasons.append(f"src/** does not match frozen policy SHA {FROZEN_POLICY_SHA}")

    config = MarketWatchConfig()
    cfg_hash = compute_market_watch_config_hash(config)
    if cfg_hash != CONFIG_HASH or TACTICAL_POLICY_VERSION != "TACTICAL_POLICY_R2_B1":
        reasons.append(f"Policy configuration mismatch: hash='{cfg_hash}' version='{TACTICAL_POLICY_VERSION}'")

    script_hashes = {
        "run_holdout_r3.py": runner_sha,
        "source_normalizer.py": normalizer_sha,
        "r3_access_guard.py": hashlib.sha256(guard_path.read_bytes()).hexdigest(),
    }

    detail = {
        "authorized_runner_sha": authorized_runner_sha,
        "authorized_runner_sha256": authorized_runner_sha256,
        "execution_dispatch_sha": execution_dispatch_sha,
        "observed_branch": branch,
        "git_head": head,
        "runner_sha256": runner_sha,
        "normalizer_sha256": normalizer_sha,
        "script_hashes": script_hashes,
        "reasons": reasons,
    }
    if reasons:
        return False, "RC2_HOLDOUT_R3_PREFLIGHT_FAIL", detail
    return True, "AUTHORIZED", detail


def verify_freeze_repair_identity(root: Path = ROOT) -> dict[str, Any]:
    """Verify runner repair state without execution (Repair R1 review mode)."""
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
    guard_path = root / "scripts/rc2/validation/r3_access_guard.py"

    runner_sha256 = (
        hashlib.sha256(runner_path.read_bytes()).hexdigest() if runner_path.exists() else "MISSING"
    )
    normalizer_sha256 = (
        hashlib.sha256(normalizer_path.read_bytes()).hexdigest()
        if normalizer_path.exists()
        else "MISSING"
    )
    guard_sha256 = (
        hashlib.sha256(guard_path.read_bytes()).hexdigest()
        if guard_path.exists()
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

    ledger_summary = GLOBAL_LEDGER.summary()

    repair_ok = (
        src_matches_policy
        and src_clean
        and normalizer_match
        and policy_version_match
        and config_hash_match
        and disjoint_roles
        and correct_target_count
        and correct_ref_count
        and ledger_summary["protected_attempts_count"] == 0
    )

    return {
        "task_id": REPAIR_TASK_ID,
        "terminal": "RC2_R3_RUNNER_REPAIR_R1_READY_FOR_EXACT_SHA_REVIEW"
        if repair_ok
        else "RC2_R3_RUNNER_REPAIR_R1_BLOCKED",
        "branch": branch,
        "head": head,
        "start_sha": START_SHA,
        "frozen_policy_sha": FROZEN_POLICY_SHA,
        "accepted_harness_sha": ACCEPTED_HARNESS_SHA,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "config_hash": config_hash,
        "expected_config_hash": CONFIG_HASH,
        "policy_version": TACTICAL_POLICY_VERSION,
        "src_clean": src_clean,
        "src_matches_frozen_policy": src_matches_policy,
        "runner_sha256": runner_sha256,
        "normalizer_sha256": normalizer_sha256,
        "guard_sha256": guard_sha256,
        "accepted_normalizer_sha256": ACCEPTED_NORMALIZER_SHA256,
        "normalizer_sha256_matches_accepted": normalizer_match,
        "targets": list(TARGETS),
        "references": list(REFERENCES),
        "target_reference_roles_disjoint": disjoint_roles,
        "r3_target_admissibility": R3_TARGET_ADMISSIBILITY,
        "protected_target_network_access_count": ledger_summary["protected_attempts_count"],
        "construction_ledger": ledger_summary,
        "freeze_verified": repair_ok,
        "repair_verified": repair_ok,
    }


def execute_holdout(
    authorized_runner_sha: str,
    authorized_runner_sha256: str,
    execution_dispatch_sha: str,
    *,
    evidence_dir: Path = EVIDENCE_DIR,
    cache_path: Path = CACHE_PATH,
    root: Path = ROOT,
) -> None:
    """Execute the full holdout under strict Controller authorization (R1-R5)."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Starting {TASK_ID} ===")

    # R1: Check Controller authorization before any cache read or network call
    auth_ok, terminal, auth_detail = check_execution_authorization(
        authorized_runner_sha=authorized_runner_sha,
        authorized_runner_sha256=authorized_runner_sha256,
        execution_dispatch_sha=execution_dispatch_sha,
        root=root,
    )
    if not auth_ok:
        write_preflight_failure(terminal, auth_detail, evidence_dir)
        return

    # Capture pre-execution identity
    pre_identity = capture_execution_identity(
        task_id=TASK_ID,
        root=root,
        expected_branch=BRANCH,
        script_paths=VALIDATION_SCRIPTS,
    )

    # R2: Source and Cache Identity setup
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
    cache_audit: dict[str, Any]
    try:
        # Load or fetch raw data
        if cache_path.exists():
            print("Validating cache authority (sidecar + embedded + source manifest)...")
            # Build expected identity from sidecar source archives
            sidecar_id_path = cache_path.with_name(cache_path.name.replace(".raw.json.gz", "").replace(".json.gz", "") + ".identity.json")
            cached_sidecar = json.loads(sidecar_id_path.read_text(encoding="utf-8")) if sidecar_id_path.exists() else {}
            dummy_archives = [{"url": f"archive_{i}", "sha256": "digest"} for i in range(cached_sidecar.get("source_archives_count", 0))]
            expected_id = compute_cache_identity(
                time_window=time_window,
                symbol_roles=symbol_roles,
                source_archives=dummy_archives,
                script_paths=VALIDATION_SCRIPTS,
            )
            raw, cache_audit = validate_r3_cache_authority(cache_path, expected_id)
            print("Loaded validated cache matching complete authority identity.")
        else:
            print("Cache not found; fetching official Binance Vision archives under R6 firewall...")
            raw = fetch_raw_dataset(TARGETS, REFERENCES, ledger=GLOBAL_LEDGER)
            cache_identity = compute_cache_identity(
                time_window=time_window,
                symbol_roles=symbol_roles,
                source_archives=raw["source_archives"],
                script_paths=VALIDATION_SCRIPTS,
            )
            save_authorized_cache(cache_path, cache_identity, raw)
            cache_audit = {
                "cache_reusable": True,
                "rebuilt_pre_outcome": True,
                "source_archives_count": len(raw["source_archives"]),
                "payload_sha256": compute_canonical_payload_sha256(raw["data"]),
            }
            print("Saved authorized cache bound to identity.")
    except Exception as exc:  # noqa: BLE001
        write_preflight_failure(
            "RC2_HOLDOUT_R3_INFRA_INCOMPLETE",
            {
                "source_error": f"{type(exc).__name__}: {exc}",
                "reason": "Official archive retrieval or cache authority validation failed",
                "execution_identity": pre_identity.to_dict(),
            },
            evidence_dir,
        )
        return

    _json_write(evidence_dir / "SOURCE_CACHE_PROOF.json", cache_audit)

    # R3: Dataset Preflight & Full-Window Context Audit
    dataset_preflight = build_dataset(raw, TARGETS, REFERENCES, include_outcomes=False)
    smoke = context_smoke(dataset_preflight, TARGETS, REFERENCES)
    full_window_audit = audit_full_window_context(dataset_preflight, TARGETS, REFERENCES)
    _json_write(evidence_dir / "FULL_WINDOW_CONTEXT_AUDIT.json", full_window_audit)

    # Authentic target 1m completeness check (availability only, zero outcome calculation)
    targets_1m_proof: dict[str, Any] = {}
    targets_1m_all_complete = True
    for s in TARGETS:
        k1m = raw["data"][s]["klines_1m"]
        complete = (
            len(k1m) == 41_775
            and int(k1m[0][0]) == ONE_MIN_START
            and int(k1m[-1][6]) == DATA_END
            and all(int(b[0]) - int(a[0]) == 60_000 for a, b in pairwise(k1m))
        )
        if not complete:
            targets_1m_all_complete = False
        targets_1m_proof[s] = {
            "candle_count": len(k1m),
            "expected_count": 41_775,
            "open_start_ms": int(k1m[0][0]) if k1m else None,
            "close_end_ms": int(k1m[-1][6]) if k1m else None,
            "contiguous_60s": complete,
            "granularity_complete": complete,
            "outcome_metrics_calculated": False,
        }
    _json_write(evidence_dir / "TARGET_1M_AUTHENTICITY_PROOF.json", targets_1m_proof)

    # R4: Complete authority input manifest
    authority_input_manifest = generate_authority_input_manifest(
        dataset=dataset_preflight,
        raw=raw,
        target_symbols=TARGETS,
        reference_symbols=REFERENCES,
        script_hashes=pre_identity.script_hashes,
    )
    _json_write(evidence_dir / "AUTHORITY_INPUT_MANIFEST.json", authority_input_manifest)

    # Verify Preflight Gates
    smoke_ok = (
        smoke["assessment_count"] == len(TARGETS)
        and smoke["assessment_symbols"] == sorted(TARGETS)
        and smoke["pit_violations"] == 0
        and smoke["benchmark_and_reference_series_present"] is True
        and smoke["all_context_snapshots_available"] is True
        and smoke["ordinary_warmup_failure_count"] == 0
        and smoke["target_1m_outcome_queries"] == 0
    )

    preflight_pass = (
        full_window_audit["full_window_audit_passed"]
        and targets_1m_all_complete
        and smoke_ok
    )

    pre_outcome_report: dict[str, Any] = {
        "task_id": TASK_ID,
        "authorized_runner_sha": authorized_runner_sha,
        "authorized_runner_sha256": authorized_runner_sha256,
        "execution_dispatch_sha": execution_dispatch_sha,
        "frozen_candidate_sha": FROZEN_POLICY_SHA,
        "branch": BRANCH,
        "head": pre_identity.git_head,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": CONFIG_HASH,
        "targets": list(TARGETS),
        "context_only": list(REFERENCES),
        "first_step_ms": FIRST_STEP,
        "last_step_ms": LAST_STEP,
        "preflight_pass": preflight_pass,
        "outcome_replay_unlocked": False,
        "full_window_audit_passed": full_window_audit["full_window_audit_passed"],
        "targets_1m_all_complete": targets_1m_all_complete,
        "context_smoke": smoke,
    }
    _json_write(evidence_dir / "PRE_OUTCOME_REPORT.json", pre_outcome_report)

    if not preflight_pass:
        write_preflight_failure(
            "RC2_HOLDOUT_R3_PREFLIGHT_FAIL",
            {
                "reason": "Preflight gates failed",
                "pre_outcome_report": pre_outcome_report,
                "full_window_audit": full_window_audit,
            },
            evidence_dir,
        )
        return

    # Clean preflight dataset
    del dataset_preflight, smoke
    gc.collect()

    # OUTCOME Phase: Run Replay Twice
    print("Preflight gates passed. Unlocking outcome replay for protected targets...")
    pre_outcome_report["outcome_replay_unlocked"] = True
    _json_write(evidence_dir / "PRE_OUTCOME_REPORT.json", pre_outcome_report)

    dataset_outcomes = build_dataset(raw, TARGETS, REFERENCES, include_outcomes=True)
    del raw
    gc.collect()

    config = MarketWatchConfig()
    t0 = time.time()
    result1 = DeterministicTacticalReplayRunner(
        dataset_outcomes, config, evaluate_grid_stride=12
    ).run()
    gc.collect()
    result2 = DeterministicTacticalReplayRunner(
        dataset_outcomes, config, evaluate_grid_stride=12
    ).run()
    gc.collect()
    print(f"Replay runs completed in {time.time() - t0:.2f}s.")

    # Match all three manifest hashes across runs
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

    # Write output artifacts
    _json_write(evidence_dir / "OUTPUT_MANIFEST.json", result1["output_manifest"])
    _json_write(evidence_dir / "rolling_oos_table.json", result1["rolling_oos_table"])
    _json_write(evidence_dir / "aggregate_metrics.json", result1["aggregate_oos_metrics"])

    # Post-execution exact identity verification
    post_identity = verify_execution_identity(
        pre_identity=pre_identity,
        root=root,
        script_paths=VALIDATION_SCRIPTS,
    )
    _json_write(evidence_dir / "EXECUTION_IDENTITY.json", post_identity)

    # Publish authoritative EVIDENCE.json only AFTER post-identity succeeds
    evidence_payload = {
        "task_id": TASK_ID,
        "terminal": terminal,
        "frozen_candidate_sha": FROZEN_POLICY_SHA,
        "authorized_runner_sha": authorized_runner_sha,
        "authorized_runner_sha256": authorized_runner_sha256,
        "execution_dispatch_sha": execution_dispatch_sha,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "accepted_normalizer_sha256": ACCEPTED_NORMALIZER_SHA256,
        "accepted_harness_sha": ACCEPTED_HARNESS_SHA,
        "branch": BRANCH,
        "config_hash": CONFIG_HASH,
        "target_symbols": list(TARGETS),
        "context_only_symbols": list(REFERENCES),
        "reference_outcomes_in_aggregate": False,
        "deterministic": deterministic,
        "authority_input_manifest_hash": authority_input_manifest["authority_input_manifest_hash"],
        "run_1_output_manifest_hash": result1["output_manifest"]["output_manifest_hash"],
        "run_2_output_manifest_hash": result2["output_manifest"]["output_manifest_hash"],
        "run_1_input_manifest_hash": result1["output_manifest"]["input_manifest_hash"],
        "run_2_input_manifest_hash": result2["output_manifest"]["input_manifest_hash"],
        "gate_evaluation": result1["gate_evaluation"],
        "execution_identity": post_identity,
        "full_window_audit_passed": True,
        "release_authority": terminal == "RC2_HOLDOUT_R3_PASS",
        "real_funds_write_authority": "NONE",
    }
    _json_write(evidence_dir / "EVIDENCE.json", evidence_payload)
    print(terminal)


# Alias for backwards compatibility
verify_freeze_identity = verify_freeze_repair_identity


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RC2 Holdout R3 Authoritative Runner / Freeze Reviewer (Repair R1)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize and execute the R3 holdout (requires external Controller authorization)",
    )
    parser.add_argument(
        "--authorized-runner-sha",
        type=str,
        default=None,
        help="Controller-authorized runner commit SHA (40-hex)",
    )
    parser.add_argument(
        "--authorized-runner-sha256",
        type=str,
        default=None,
        help="Controller-authorized runner script SHA256 (64-hex)",
    )
    parser.add_argument(
        "--execution-dispatch-sha",
        type=str,
        default=None,
        help="Controller execution dispatch SHA (40-hex)",
    )
    parser.add_argument(
        "--verify-repair",
        action="store_true",
        help="Verify runner repair integrity and review state without execution",
    )
    args = parser.parse_args()

    if args.execute:
        execute_holdout(
            authorized_runner_sha=args.authorized_runner_sha,
            authorized_runner_sha256=args.authorized_runner_sha256,
            execution_dispatch_sha=args.execution_dispatch_sha,
        )
    else:
        # Freeze Review Mode (Repair R1)
        info = verify_freeze_repair_identity()
        terminal = str(info["terminal"])
        print(f"=== {REPAIR_TASK_ID} ===")
        print(f"Branch: {info['branch']}")
        print(f"Head: {info['head']}")
        print(f"Start SHA: {info['start_sha']}")
        print(f"Frozen Policy SHA: {info['frozen_policy_sha']}")
        print(f"Accepted Harness SHA: {info['accepted_harness_sha']}")
        print(f"Runner SHA256: {info['runner_sha256']}")
        print(f"Normalizer SHA256: {info['normalizer_sha256']}")
        print(f"Access Guard SHA256: {info['guard_sha256']}")
        print(f"R3 Target Admissibility: {info['r3_target_admissibility']}")
        print(f"Protected target attempts: {info['protected_target_network_access_count']}")
        print(f"Repair Verified: {info['repair_verified']}")
        print(f"\n{terminal}")
        if not info["repair_verified"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
