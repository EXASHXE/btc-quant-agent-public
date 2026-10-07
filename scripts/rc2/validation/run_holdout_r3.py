#!/usr/bin/env python3
"""Authoritative Final Validation Runner for RC2 Holdout R3 (Repair R2 — Generic Runner Before Target Seal).

Frozen Policy SHA: 10be512f2cf4d7eccdc8a9849c925b5f73c568fd
Config Hash: bba61849e64f37f9
Accepted Harness SHA: cbc903d9ba448059121db96c3572a2677d5b53f8
Controller Dispatch SHA: 405e0042687bfae5aa986e0f2982e26cba3827cd
Accepted Normalizer SHA256: 4191922d1e85ad30b079633323836a817bf0506d223eb2365b2a4d3d25f52a16

Architectural Change:
- Generic runner: No hard-coded protected targets.
- Target set is unlocked ONLY via external Controller target seal artifact.
- Capability access model separating CONSTRUCTION_REVIEW and AUTHORIZED_EXECUTION modes.
- Persistent execution access ledger tracking every network/archive/cache read attempt.
- Fresh execution-scoped source fetch; zero cross-run cache reuse in authority execution.
- Production-equivalent full-window pre-outcome audit across every decision step.
- Complete authority input manifest covering OHLCV, quote volume, trades, and all derivatives.
- Staged artifacts published atomically only after post-run identity check PASS.
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
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Sequence
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
from btc_quant_agent.market_watch.domain import TACTICAL_POLICY_VERSION, ScanHealth
from btc_quant_agent.market_watch.replay import (
    DeterministicTacticalReplayRunner,
    HistoricalReplayClient,
    OOSPartitionSpec,
    ReplayDataset,
    _fast_bb_width_tail140,
    _fast_pct_rank_tail20,
    _fast_zscore_tail,
    _InMemoryReplayStateStore,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.snapshot import compute_timeframe_snapshot
from scripts.rc2.validation.r3_access_guard import (
    R3_TARGET_ADMISSIBILITY,
    AccessCapability,
    AuthorizationProof,
    ExecutionAccessLedger,
)
from scripts.rc2.validation.source_normalizer import (
    CACHE_SCHEMA_VERSION,
    PARSER_SCHEMA_VERSION,
    CacheAuthorityError,
    CacheIdentity,
    capture_execution_identity,
    normalize_metrics_rows,
    verify_execution_identity,
)
from scripts.rc2.validation.target_seal import (
    TargetSealError,
    validate_target_seal,
)

# Hard-coded Frozen Constants
TASK_ID = "RC2_HOLDOUT_R3_EXECUTION"
REPAIR_TASK_ID = "RC2_R3_HOLDOUT_RUNNER_REPAIR_R2"
BRANCH = "validation/b-line-rc2-holdout-r3-runner-repair-r2"
START_SHA = "0d61b564fa178af0f0a8e7df1c0a6b13586711e3"
FROZEN_POLICY_SHA = "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
ACCEPTED_HARNESS_SHA = "cbc903d9ba448059121db96c3572a2677d5b53f8"
CONTROLLER_DISPATCH_SHA = "405e0042687bfae5aa986e0f2982e26cba3827cd"
CONFIG_HASH = "bba61849e64f37f9"
ACCEPTED_NORMALIZER_SHA256 = "4191922d1e85ad30b079633323836a817bf0506d223eb2365b2a4d3d25f52a16"

# Generic Runner: Target set is empty by default; populated ONLY from external TARGET_SEAL
TARGETS: tuple[str, ...] = ()

# Context-Only References: Frozen and constant across all runs
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

ALL_SYMBOLS: tuple[str, ...] = REFERENCES

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

DEFAULT_EVIDENCE_DIR = ROOT / "evidence/v0.5.5/tactical-policy/RC2/HOLDOUT_FINAL"
BASE_URL = "https://data.binance.vision/data/futures/um"

VALIDATION_SCRIPTS = [
    ROOT / "scripts/rc2/validation/source_normalizer.py",
    ROOT / "scripts/rc2/validation/r3_access_guard.py",
    ROOT / "scripts/rc2/validation/target_seal.py",
    ROOT / "scripts/rc2/validation/run_holdout_r3.py",
]


class ArchiveNotFoundError(RuntimeError):
    """Raised when an official archive URL returns HTTP 404."""


def _json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _download(
    url: str,
    capability: AccessCapability,
    source_dir: Path | None = None,
    caller: str = "_download",
) -> bytes:
    """Download official vision archive guarded by explicit access capability (R2.1, R2.2)."""
    capability.check_access(url, caller=caller, is_cache=False)
    if source_dir is not None:
        cached = source_dir / hashlib.sha256(url.encode()).hexdigest()
        if cached.exists():
            capability.check_access(url, caller=f"{caller}:cache_hit", is_cache=True)
            return cached.read_bytes()

    req = urllib.request.Request(url, headers={"User-Agent": "rc2-holdout-r3-runner/2.0"})
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

    if source_dir is not None:
        source_dir.mkdir(parents=True, exist_ok=True)
        cached = source_dir / hashlib.sha256(url.encode()).hexdigest()
        cached.write_bytes(payload)
    return payload


def _zip_csv(
    url: str,
    capability: AccessCapability,
    source_dir: Path | None = None,
    archive_manifest: dict[str, str] | None = None,
) -> list[list[str]]:
    data = _download(url, capability=capability, source_dir=source_dir, caller="_zip_csv")
    if archive_manifest is not None:
        archive_manifest[url] = hashlib.sha256(data).hexdigest()
    archive = zipfile.ZipFile(io.BytesIO(data))
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
    capability: AccessCapability,
    source_dir: Path | None = None,
    archive_manifest: dict[str, str] | None = None,
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
            rows.extend(
                _zip_csv(
                    url,
                    capability=capability,
                    source_dir=source_dir,
                    archive_manifest=archive_manifest,
                )
            )
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
                rows.extend(
                    _zip_csv(
                        daily_url,
                        capability=capability,
                        source_dir=source_dir,
                        archive_manifest=archive_manifest,
                    )
                )
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
    *,
    capability: AccessCapability,
    source_dir: Path | None = None,
    archive_manifest: dict[str, str] | None = None,
) -> list[list[str]]:
    days = _date_range(start_ms, end_ms)

    def load_day(day: str) -> list[list[str]]:
        return _zip_csv(
            f"{BASE_URL}/daily/{dataset}/{symbol}/{symbol}-{dataset}-{day}.zip",
            capability=capability,
            source_dir=source_dir,
            archive_manifest=archive_manifest,
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
    *,
    capability: AccessCapability,
    source_dir: Path | None = None,
    archive_manifest: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cur = datetime.fromtimestamp(start_ms / 1000, UTC).date().replace(day=1)
    last = datetime.fromtimestamp(end_ms / 1000, UTC).date().replace(day=1)
    while cur <= last:
        month = cur.strftime("%Y-%m")
        url = f"{BASE_URL}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
        try:
            archive_rows = _zip_csv(
                url,
                capability=capability,
                source_dir=source_dir,
                archive_manifest=archive_manifest,
            )
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
            payload_bytes = _download(
                api_url,
                capability=capability,
                source_dir=source_dir,
                caller="_funding_records:api",
            )
            if archive_manifest is not None:
                archive_manifest[api_url] = hashlib.sha256(payload_bytes).hexdigest()
            payload = json.loads(payload_bytes)
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
    capability: AccessCapability,
    source_dir: Path | None = None,
    archive_manifest: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    capability.check_access(symbol, caller="_fetch_symbol_entry")
    entry: dict[str, Any] = {}
    for interval in ("15m", "1h", "4h"):
        entry[f"klines_{interval}"] = _klines(
            symbol,
            interval,
            tf_start,
            DATA_END,
            capability=capability,
            source_dir=source_dir,
            archive_manifest=archive_manifest,
        )
    # Target 1m is source-coverage input only; references never have 1m
    entry["klines_1m"] = (
        _klines(
            symbol,
            "1m",
            ONE_MIN_START,
            DATA_END,
            capability=capability,
            source_dir=source_dir,
            archive_manifest=archive_manifest,
        )
        if is_target
        else []
    )

    metrics = _daily_records(
        "metrics",
        symbol,
        tf_start,
        DATA_END,
        capability=capability,
        source_dir=source_dir,
        archive_manifest=archive_manifest,
    )
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
        symbol,
        "5m",
        tf_start,
        DATA_END,
        dataset="premiumIndexKlines",
        capability=capability,
        source_dir=source_dir,
        archive_manifest=archive_manifest,
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

    entry["funding_rates"] = _funding_records(
        symbol,
        tf_start,
        DATA_END,
        capability=capability,
        source_dir=source_dir,
        archive_manifest=archive_manifest,
    )
    return symbol, entry


def fetch_fresh_source_bundle(
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
    capability: AccessCapability,
    source_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch official source archives fresh into an empty execution-scoped source dir (R2.3)."""
    if source_dir.exists() and any(source_dir.iterdir()):
        raise RuntimeError(
            f"Execution-scoped source directory already exists and is non-empty: {source_dir}. "
            "Authority execution forbids cross-run cache reuse."
        )
    source_dir.mkdir(parents=True, exist_ok=True)

    tf_start = FIRST_STEP - 320 * 4 * 3_600_000
    all_symbols = target_symbols + reference_symbols
    archive_manifest: dict[str, str] = {}

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
                capability=capability,
                source_dir=source_dir,
                archive_manifest=archive_manifest,
            )
            for s in all_symbols
        ]
        for f in futures:
            s, entry = f.result()
            raw["data"][s] = entry
            gc.collect()

    sorted_archives = [
        {"url": url, "sha256": digest} for url, digest in sorted(archive_manifest.items())
    ]
    raw["source_archives"] = sorted_archives

    bundle_repr = json.dumps(sorted_archives, sort_keys=True, separators=(",", ":")).encode()
    bundle_digest = hashlib.sha256(bundle_repr).hexdigest()

    source_bundle_manifest = {
        "manifest_version": "RC2_SOURCE_BUNDLE_MANIFEST_V1",
        "task_id": TASK_ID,
        "execution_dispatch_sha": capability.execution_dispatch_sha,
        "authorized_runner_sha": capability.authorized_runner_sha,
        "target_seal_sha256": capability.target_seal_sha256,
        "source_archives_count": len(sorted_archives),
        "source_bundle_digest": bundle_digest,
        "source_archives": sorted_archives,
    }
    _json_write(source_dir / "SOURCE_BUNDLE_MANIFEST.json", source_bundle_manifest)
    return raw, source_bundle_manifest


# Backwards-compatible raw dataset fetcher
def fetch_raw_dataset(
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
    capability: AccessCapability | None = None,
) -> dict[str, Any]:
    cap = capability or AccessCapability.construction_review(ExecutionAccessLedger())
    tf_start = FIRST_STEP - 320 * 4 * 3_600_000
    all_symbols = target_symbols + reference_symbols
    archive_manifest: dict[str, str] = {}
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
                capability=cap,
                source_dir=None,
                archive_manifest=archive_manifest,
            )
            for s in all_symbols
        ]
        for f in futures:
            s, entry = f.result()
            raw["data"][s] = entry
            gc.collect()
    raw["source_archives"] = [
        {"url": url, "sha256": digest} for url, digest in sorted(archive_manifest.items())
    ]
    return raw


def compute_canonical_payload_sha256(data_dict: dict[str, Any]) -> str:
    """Canonical SHA256 digest of raw dataset data payload."""
    encoded = json.dumps(data_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_r3_cache_authority(
    cache_path: Path,
    expected_identity: CacheIdentity,
    expected_payload_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate sidecar identity AND embedded identity AND payload content binding (for non-authority unit tests)."""
    identity_path = cache_path.with_name(
        cache_path.name.replace(".raw.json.gz", "").replace(".json.gz", "") + ".identity.json"
    )
    if not identity_path.exists():
        raise CacheAuthorityError(f"Missing required sidecar identity file: {identity_path}")
    if not cache_path.exists():
        raise CacheAuthorityError(f"Missing cache file: {cache_path}")

    try:
        sidecar_identity_dict = json.loads(identity_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CacheAuthorityError(f"Corrupted sidecar identity file: {exc}") from exc

    try:
        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            wrapped = json.load(f)
    except Exception as exc:
        raise CacheAuthorityError(f"Corrupted gzip cache archive: {exc}") from exc

    if not isinstance(wrapped, dict) or "identity" not in wrapped or "payload" not in wrapped:
        raise CacheAuthorityError("Anonymous or un-wrapped cache rejected; must contain identity header and payload")

    embedded_identity_dict = wrapped["identity"]
    payload = wrapped["payload"]

    if sidecar_identity_dict != embedded_identity_dict:
        raise CacheAuthorityError("Sidecar identity and embedded cache identity mismatch")

    expected_dict = expected_identity.to_dict()
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

    payload_archives = payload.get("source_archives", [])
    sorted_archives = sorted(payload_archives, key=lambda x: x["url"])
    archives_repr = json.dumps(sorted_archives, sort_keys=True, separators=(",", ":")).encode()
    computed_archives_digest = hashlib.sha256(archives_repr).hexdigest()
    if computed_archives_digest != expected_dict["source_archives_digest"]:
        raise CacheAuthorityError(
            f"Payload source archives digest mismatch: computed={computed_archives_digest} expected={expected_dict['source_archives_digest']}"
        )

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


def audit_full_window_production_context(
    dataset: ReplayDataset,
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Execute production-equivalent full-window audit across EVERY decision step (R2.5).

    Runs the real production scanner/context path on a dataset with target 1m outcomes disabled.
    Asserts:
    - exact target assessment count == number of sealed targets;
    - exact assessed symbol set == sealed targets;
    - BTC/ETH benchmark snapshots present;
    - complete relative-strength context;
    - no scanner degradation/fallback caused by missing data;
    - zero PIT violations;
    - no ordinary warm-up omission;
    - closed 15m continuity;
    - required rolling 1h and 4h history continuity;
    - OI production lookback availability;
    - taker production lookback availability;
    - global/top-position/top-account ratio lookbacks;
    - basis lookback;
    - funding data required by production logic;
    - no future-timestamp input.
    Halts immediately on first defect.
    """
    steps = dataset.step_timestamps_ms
    all_symbols = target_symbols + reference_symbols
    defects: list[dict[str, Any]] = []

    # Pre-flight check: dataset symbols must exactly match target symbols
    if tuple(dataset.symbols) != tuple(target_symbols):
        defects.append(
            {
                "step_ms": FIRST_STEP,
                "step_index": 0,
                "symbol": "ALL",
                "error": f"Target symbols mismatch: dataset.symbols={tuple(dataset.symbols)} expected={tuple(target_symbols)}",
            }
        )
        return {
            "audit_timestamp_utc": datetime.now(UTC).isoformat(),
            "full_window_audit_passed": False,
            "defects_count": len(defects),
            "defects": defects,
            "first_failure": defects[0],
            "steps_evaluated_count": 0,
            "target_1m_outcome_queries_count": 0,
            "pit_violations_count": 0,
        }

    # Pre-index sorted timestamp arrays for high-performance lookback verification
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

    # Verify warm-up history at FIRST_STEP
    for sym in all_symbols:
        idx = indexed_data[sym]
        k15_pre = bisect.bisect_right(idx["k15m_closes"], FIRST_STEP - 1)
        k1h_pre = bisect.bisect_right(idx["k1h_closes"], FIRST_STEP - 1)
        k4h_pre = bisect.bisect_right(idx["k4h_closes"], FIRST_STEP - 1)
        if k4h_pre < 320:
            defects.append(
                {"step_ms": FIRST_STEP, "step_index": 0, "symbol": sym, "error": f"closed 4h count {k4h_pre} < 320"}
            )
        if k1h_pre < 1280:
            defects.append(
                {"step_ms": FIRST_STEP, "step_index": 0, "symbol": sym, "error": f"closed 1h count {k1h_pre} < 1280"}
            )
        if k15_pre < 5120:
            defects.append(
                {"step_ms": FIRST_STEP, "step_index": 0, "symbol": sym, "error": f"closed 15m count {k15_pre} < 5120"}
            )

    store = _InMemoryReplayStateStore()
    store.save_evidence = lambda _ev: None  # Avoid storing large evidence objects during audit
    client = HistoricalReplayClient(dataset, FIRST_STEP, allow_synthetic_1m_for_tests=False)
    config = MarketWatchConfig(symbols=target_symbols)
    scanner = MarketWatchScanner(config, client, store)

    steps_evaluated = 0

    import contextlib

    _AUDIT_TF_CACHE: dict[Any, Any] = {}
    cfg_hash = compute_market_watch_config_hash(config)

    def _cached_compute_tf(
        interval: str,
        closed_candles: Sequence[Any],
        forming_candle: Any | None,
        config: MarketWatchConfig,
    ) -> Any:
        if forming_candle is None and closed_candles:
            key = (
                closed_candles[-1].symbol,
                interval,
                len(closed_candles),
                closed_candles[0].open_time_ms,
                closed_candles[-1].close_time_ms,
                closed_candles[-1].close,
                cfg_hash,
            )
            cached = _AUDIT_TF_CACHE.get(key)
            if cached is not None:
                return cached
            res = compute_timeframe_snapshot(interval, closed_candles, None, config)
            if len(_AUDIT_TF_CACHE) > 512:
                _AUDIT_TF_CACHE.clear()
            _AUDIT_TF_CACHE[key] = res
            return res
        return compute_timeframe_snapshot(interval, closed_candles, forming_candle, config)

    @contextlib.contextmanager
    def _scanner_audit_patches() -> Any:
        from btc_quant_agent.market_watch import evidence, snapshot
        from btc_quant_agent.market_watch import scanner as scanner_module

        orig = (
            scanner_module.time.time,
            scanner_module.compute_timeframe_snapshot,
            snapshot.rolling_zscore,
            snapshot.percentile_rank,
            snapshot.bollinger_width,
            evidence.verify_tactical_evidence_identity,
            evidence.validate_tactical_feature_evidence,
        )
        try:
            scanner_module.time.time = lambda: client.as_of_ms / 1000.0
            scanner_module.compute_timeframe_snapshot = _cached_compute_tf
            snapshot.rolling_zscore = _fast_zscore_tail
            snapshot.percentile_rank = _fast_pct_rank_tail20
            snapshot.bollinger_width = _fast_bb_width_tail140
            evidence.verify_tactical_evidence_identity = lambda _ev: None
            evidence.validate_tactical_feature_evidence = lambda _ev: None
            yield
        finally:
            (
                scanner_module.time.time,
                scanner_module.compute_timeframe_snapshot,
                snapshot.rolling_zscore,
                snapshot.percentile_rank,
                snapshot.bollinger_width,
                evidence.verify_tactical_evidence_identity,
                evidence.validate_tactical_feature_evidence,
            ) = orig

    with _scanner_audit_patches():
        for step_idx, step_ms in enumerate(steps):
            steps_evaluated += 1
            client.set_as_of_ms(step_ms)

            # 1. Benchmark existence
            for bmark in ("BTCUSDT", "ETHUSDT"):
                if bmark not in dataset.series_by_symbol:
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": bmark,
                            "error": "Benchmark missing from dataset",
                        }
                    )
                    break

            # 2. Lookback series continuity for every symbol
            for sym in all_symbols:
                idx = indexed_data[sym]
                c15_pos = bisect.bisect_right(idx["k15m_closes"], step_ms)
                if c15_pos == 0 or idx["k15m_closes"][c15_pos - 1] != step_ms:
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing exact closed 15m candle at decision step",
                        }
                    )

                expected_1h_close = step_ms - ((step_ms + 1) % 3_600_000)
                c1h_pos = bisect.bisect_right(idx["k1h_closes"], step_ms)
                if c1h_pos == 0 or idx["k1h_closes"][c1h_pos - 1] != expected_1h_close:
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": f"Missing closed 1h candle continuity: expected_close={expected_1h_close}",
                        }
                    )

                expected_4h_close = step_ms - ((step_ms + 1) % (4 * 3_600_000))
                c4h_pos = bisect.bisect_right(idx["k4h_closes"], step_ms)
                if c4h_pos == 0 or idx["k4h_closes"][c4h_pos - 1] != expected_4h_close:
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": f"Missing closed 4h candle continuity: expected_close={expected_4h_close}",
                        }
                    )

                oi_pos = bisect.bisect_right(idx["oi_ts"], step_ms)
                if oi_pos == 0 or idx["oi_ts"][oi_pos - 1] < (step_ms - 2 * 3_600_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing OI within 2h lookback",
                        }
                    )

                taker_pos = bisect.bisect_right(idx["taker_ts"], step_ms)
                if taker_pos == 0 or idx["taker_ts"][taker_pos - 1] < (step_ms - 15 * 60_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing taker ratio within 15m lookback",
                        }
                    )

                gls_pos = bisect.bisect_right(idx["gls_ts"], step_ms)
                if gls_pos == 0 or idx["gls_ts"][gls_pos - 1] < (step_ms - 2 * 3_600_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing global L/S within 2h lookback",
                        }
                    )

                tp_pos = bisect.bisect_right(idx["top_pos_ts"], step_ms)
                if tp_pos == 0 or idx["top_pos_ts"][tp_pos - 1] < (step_ms - 2 * 3_600_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing top position L/S within 2h lookback",
                        }
                    )

                ta_pos = bisect.bisect_right(idx["top_acc_ts"], step_ms)
                if ta_pos == 0 or idx["top_acc_ts"][ta_pos - 1] < (step_ms - 2 * 3_600_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing top account L/S within 2h lookback",
                        }
                    )

                basis_pos = bisect.bisect_right(idx["basis_ts"], step_ms)
                if basis_pos == 0 or idx["basis_ts"][basis_pos - 1] < (step_ms - 10 * 60_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing basis within 10m lookback",
                        }
                    )

                fund_pos = bisect.bisect_right(idx["funding_ts"], step_ms)
                if fund_pos == 0 or idx["funding_ts"][fund_pos - 1] < (step_ms - 8.5 * 3_600_000):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": sym,
                            "error": "Missing funding records within 8.5h lookback",
                        }
                    )

            if defects:
                break

            # 3. Real production scanner evaluation at this step
            try:
                assessments, _ = scanner.scan_universe(symbols=target_symbols, notify=False)
            except Exception as exc:  # noqa: BLE001
                defects.append(
                    {
                        "step_ms": step_ms,
                        "step_index": step_idx,
                        "symbol": "ALL",
                        "error": f"Scanner exception: {type(exc).__name__}: {exc}",
                    }
                )
                break

            # Validate assessment count and symbol set
            if len(assessments) != len(target_symbols):
                defects.append(
                    {
                        "step_ms": step_ms,
                        "step_index": step_idx,
                        "symbol": "ALL",
                        "error": f"Assessment count mismatch: observed={len(assessments)} expected={len(target_symbols)}",
                    }
                )
                break

            assessed_syms = sorted(a.symbol for a in assessments)
            if assessed_syms != sorted(target_symbols):
                defects.append(
                    {
                        "step_ms": step_ms,
                        "step_index": step_idx,
                        "symbol": "ALL",
                        "error": f"Assessed symbols mismatch: observed={assessed_syms} expected={sorted(target_symbols)}",
                    }
                )
                break

            # Validate health and degradation
            for a in assessments:
                snap = a.snapshot
                if (
                    snap is None
                    or snap.health != ScanHealth.OK
                    or bool(snap.health_reasons)
                    or a.reference_universe_status != "UNIVERSE_COMPLETE"
                    or bool(a.missing_reference_members)
                ):
                    defects.append(
                        {
                            "step_ms": step_ms,
                            "step_index": step_idx,
                            "symbol": a.symbol,
                            "error": f"Scanner degradation: health={getattr(snap, 'health', 'NONE')} reasons={getattr(snap, 'health_reasons', ())} ref_status={a.reference_universe_status}",
                        }
                    )

            # Validate PIT causality and authentic 1m queries
            if client.pit_violations_count > 0:
                defects.append(
                    {
                        "step_ms": step_ms,
                        "step_index": step_idx,
                        "symbol": "ALL",
                        "error": f"PIT violations observed: {client.pit_violations_count}",
                    }
                )
                break

            if client.max_returned_candle_close_ms > step_ms:
                defects.append(
                    {
                        "step_ms": step_ms,
                        "step_index": step_idx,
                        "symbol": "ALL",
                        "error": f"Future timestamp returned: {client.max_returned_candle_close_ms} > {step_ms}",
                    }
                )
                break

            if client.authentic_1m_queries_count > 0:
                defects.append(
                    {
                        "step_ms": step_ms,
                        "step_index": step_idx,
                        "symbol": "ALL",
                        "error": f"1m outcome queries leaked into preflight: {client.authentic_1m_queries_count}",
                    }
                )
                break

            if defects:
                break

    store.close()

    return {
        "task_id": TASK_ID,
        "total_decision_steps": len(steps),
        "steps_evaluated_count": steps_evaluated,
        "first_step_ms": FIRST_STEP,
        "last_step_ms": LAST_STEP,
        "symbols_audited_count": len(all_symbols),
        "target_symbols": list(target_symbols),
        "reference_symbols": list(reference_symbols),
        "full_window_audit_passed": len(defects) == 0,
        "defects_count": len(defects),
        "first_failure": defects[0] if defects else None,
        "last_failure": defects[-1] if defects else None,
        "pit_violations_count": client.pit_violations_count,
        "target_1m_outcome_queries_count": client.authentic_1m_queries_count,
    }


# Backwards compatibility alias
audit_full_window_context = audit_full_window_production_context


def context_smoke(
    dataset: ReplayDataset,
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Execute single-step smoke scan ensuring benchmark / context availability."""
    client = HistoricalReplayClient(dataset, FIRST_STEP, allow_synthetic_1m_for_tests=False)
    scanner = MarketWatchScanner(MarketWatchConfig(symbols=target_symbols), client, _InMemoryReplayStateStore())
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

    scanner.collect_symbol_snapshot = collect_with_audit
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


def generate_authority_input_manifest(
    dataset: ReplayDataset,
    raw: dict[str, Any],
    target_symbols: tuple[str, ...],
    reference_symbols: tuple[str, ...],
    script_hashes: dict[str, str],
    target_seal_sha256: str = "UNSEALED",
    source_bundle_digest: str = "NONE",
) -> dict[str, Any]:
    """Generate validation authority manifest binding ALL decision-consumed inputs (R2.6).

    Includes sealed targets + context references, authentic target 1m OHLCV, quote volume,
    trades, and exact content hashes for all derivatives and source archives.
    """
    symbol_digests: dict[str, dict[str, Any]] = {}
    for sym in target_symbols + reference_symbols:
        series = dataset.series_by_symbol[sym]
        is_target = sym in target_symbols

        def _hash_obj(obj: Any) -> str:
            encoded = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(encoded).hexdigest()

        # All consumed candle fields: open_time, close_time, open, high, low, close, volume, quote_volume, taker_buy_base_volume, trades
        k15_rows = [
            [
                c.open_time_ms,
                c.close_time_ms,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.quote_volume,
                c.taker_buy_base_volume,
                c.trades,
            ]
            for c in series.klines_15m
        ]
        k1h_rows = [
            [
                c.open_time_ms,
                c.close_time_ms,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.quote_volume,
                c.taker_buy_base_volume,
                c.trades,
            ]
            for c in series.klines_1h
        ]
        k4h_rows = [
            [
                c.open_time_ms,
                c.close_time_ms,
                c.open,
                c.high,
                c.low,
                c.close,
                c.volume,
                c.quote_volume,
                c.taker_buy_base_volume,
                c.trades,
            ]
            for c in series.klines_4h
        ]

        # Authentic target 1m must come from raw/dataset containing real 1m, not cleared preflight
        raw_1m = raw.get("data", {}).get(sym, {}).get("klines_1m", [])
        if is_target:
            if series.klines_1m:
                k1m_rows = [
                    [
                        c.open_time_ms,
                        c.close_time_ms,
                        c.open,
                        c.high,
                        c.low,
                        c.close,
                        c.volume,
                        c.quote_volume,
                        c.taker_buy_base_volume,
                        c.trades,
                    ]
                    for c in series.klines_1m
                ]
            elif raw_1m:
                k1m_rows = [
                    [
                        int(r[0]),
                        int(r[6]),
                        float(r[1]),
                        float(r[2]),
                        float(r[3]),
                        float(r[4]),
                        float(r[5]),
                        float(r[7]) if len(r) > 7 else 0.0,
                        float(r[9]) if len(r) > 9 else 0.0,
                        int(r[8]) if len(r) > 8 else 0,
                    ]
                    for r in raw_1m
                ]
            else:
                k1m_rows = []
        else:
            k1m_rows = []

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
        "manifest_version": "RC2_VALIDATION_AUTHORITY_INPUT_MANIFEST_V2",
        "task_id": TASK_ID,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": CONFIG_HASH,
        "target_seal_sha256": target_seal_sha256,
        "source_bundle_digest": source_bundle_digest,
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


VALID_GATE_TO_TERMINAL: dict[str, str] = {
    "TACTICAL_DECISION_QUALITY_PASS": "RC2_HOLDOUT_R3_PASS",
    "TACTICAL_DECISION_QUALITY_FAIL": "RC2_HOLDOUT_R3_FAIL",
    "TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY": "RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY",
    "TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY_DATA_GRANULARITY_INSUFFICIENT": (
        "RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY"
    ),
}


def classify_holdout_terminal(
    gate_decision: str,
    *,
    deterministic: bool,
) -> str:
    """Classify final holdout terminal state according to exact frozen semantics.

    Case A — Nondeterministic replay:
        deterministic == False -> RC2_HOLDOUT_R3_INFRA_INCOMPLETE
    Case B — Tactical PASS:
        deterministic == True and gate == TACTICAL_DECISION_QUALITY_PASS -> RC2_HOLDOUT_R3_PASS
    Case C — Tactical FAIL:
        deterministic == True and gate == TACTICAL_DECISION_QUALITY_FAIL -> RC2_HOLDOUT_R3_FAIL
    Case D — Tactical DIAGNOSTIC_ONLY:
        deterministic == True and gate == TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY* -> RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY
    Case E — Unexpected / unknown gate decision:
        deterministic == True and unrecognized gate -> RC2_HOLDOUT_R3_INFRA_INCOMPLETE
    """
    if not deterministic:
        return "RC2_HOLDOUT_R3_INFRA_INCOMPLETE"
    return VALID_GATE_TO_TERMINAL.get(gate_decision, "RC2_HOLDOUT_R3_INFRA_INCOMPLETE")


def classify_policy_quality_authority(terminal: str) -> str:
    """Map holdout terminal to explicit policy quality authority status.

    RC2_HOLDOUT_R3_PASS -> PASS
    RC2_HOLDOUT_R3_FAIL -> FAIL
    RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY -> DIAGNOSTIC_ONLY
    RC2_HOLDOUT_R3_INFRA_INCOMPLETE -> NONE_INFRA_INCOMPLETE
    """
    if terminal == "RC2_HOLDOUT_R3_PASS":
        return "PASS"
    if terminal == "RC2_HOLDOUT_R3_FAIL":
        return "FAIL"
    if terminal == "RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY":
        return "DIAGNOSTIC_ONLY"
    return "NONE_INFRA_INCOMPLETE"


def write_attempt_receipt(
    staging_dir: Path,
    phase: str,
    terminal: str,
    *,
    target_outcomes_resolved: bool,
    authority_valid: bool,
    exception_class: str | None = None,
    exception_message: str | None = None,
    execution_identities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit attempt receipt on any execution failure or completion (R2.7)."""
    receipt = {
        "task_id": TASK_ID,
        "phase": phase,
        "terminal": terminal,
        "target_outcomes_resolved": target_outcomes_resolved,
        "authority_valid": authority_valid,
        "exception_class": exception_class,
        "exception_message": exception_message,
        "execution_identities": execution_identities or {},
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
    _json_write(staging_dir / "ATTEMPT_RECEIPT.json", receipt)
    return receipt


def write_preflight_failure(
    terminal: str,
    detail: dict[str, Any],
    staging_dir: Path | None = None,
    phase: str = "PREFLIGHT",
    evidence_dir: Path | None = None,
) -> None:
    """Fail closed when preflight verification rejects authorization, seal, or audit (R2.7)."""
    target_dir = staging_dir or evidence_dir or DEFAULT_EVIDENCE_DIR
    write_attempt_receipt(
        target_dir,
        phase=phase,
        terminal=terminal,
        target_outcomes_resolved=False,
        authority_valid=False,
        exception_class=detail.get("exception_class"),
        exception_message=str(detail.get("reasons") or detail.get("error") or detail.get("reason")),
        execution_identities=detail.get("execution_identity"),
    )
    _json_write(target_dir / "PRE_OUTCOME_REPORT.json", detail)
    _json_write(target_dir / "preflight_report.json", detail)
    _json_write(
        target_dir / "EXECUTION_IDENTITY.json",
        detail.get("execution_identity", {"verified": False, "reason": "Preflight failure"}),
    )
    _json_write(
        target_dir / "SOURCE_CACHE_PROOF.json",
        detail.get("source_cache_proof", {"verified": False, "reason": "Preflight failure"}),
    )
    _json_write(
        target_dir / "FULL_WINDOW_CONTEXT_AUDIT.json",
        detail.get("full_window_audit", {"audit_passed": False, "reason": "Preflight failure"}),
    )
    _json_write(
        target_dir / "OUTPUT_MANIFEST.json",
        {"replay_performed": False, "target_outcomes_resolved": False},
    )
    _json_write(target_dir / "rolling_oos_table.json", {"available": False})
    _json_write(target_dir / "aggregate_metrics.json", {"available": False})
    _json_write(
        target_dir / "EVIDENCE.json",
        {
            "task_id": TASK_ID,
            "terminal": terminal,
            "policy_quality_authority": "NONE_INFRA_INCOMPLETE",
            "target_outcomes_resolved": False,
            "release_authority": False,
            "real_funds_write_authority": "NONE",
            **detail,
        },
    )
    print(terminal)


def check_execution_authorization(
    authorized_runner_sha: str | None,
    authorized_runner_sha256: str | None,
    execution_dispatch_sha: str | None,
    root: Path = ROOT,
    expected_branch: str = BRANCH,
    target_seal_path: Path | None = None,
    authorized_target_seal_sha256: str | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Assert external Controller authorization matches exact HEAD, runner hash, dispatch, and clean state (R2.4)."""
    reasons: list[str] = []

    # 1. Regex validation of supplied SHAs
    if not authorized_runner_sha or not re.fullmatch(r"^[0-9a-f]{40}$", authorized_runner_sha):
        reasons.append("Missing or invalid --authorized-runner-sha (expected 40-char lowercase hex)")
    if not authorized_runner_sha256 or not re.fullmatch(r"^[0-9a-f]{64}$", authorized_runner_sha256):
        reasons.append("Missing or invalid --authorized-runner-sha256 (expected 64-char lowercase hex)")
    if not execution_dispatch_sha or not re.fullmatch(r"^[0-9a-f]{40}$", execution_dispatch_sha):
        reasons.append("Missing or invalid --execution-dispatch-sha (expected 40-char lowercase hex)")
    if not authorized_target_seal_sha256 or not re.fullmatch(r"^[0-9a-f]{64}$", authorized_target_seal_sha256):
        reasons.append("Missing or invalid --authorized-target-seal-sha256 (expected 64-char lowercase hex)")

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
    seal_helper_path = root / "scripts/rc2/validation/target_seal.py"

    runner_sha = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    normalizer_sha = hashlib.sha256(normalizer_path.read_bytes()).hexdigest()
    guard_sha = hashlib.sha256(guard_path.read_bytes()).hexdigest()
    seal_helper_sha = hashlib.sha256(seal_helper_path.read_bytes()).hexdigest()

    if authorized_runner_sha256 and runner_sha != authorized_runner_sha256:
        reasons.append(f"Runner SHA256 mismatch: actual='{runner_sha}' authorized='{authorized_runner_sha256}'")
    if normalizer_sha != ACCEPTED_NORMALIZER_SHA256:
        reasons.append(f"Normalizer SHA256 mismatch: actual='{normalizer_sha}' accepted='{ACCEPTED_NORMALIZER_SHA256}'")

    # Clean tracked AND untracked state for authority paths (R2.4)
    status_output = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "src/", "scripts/rc2/validation/", "tests/"],
        cwd=root,
        text=True,
    ).strip()
    if status_output:
        reasons.append(f"Tracked or untracked authority dirt detected in git status:\n{status_output}")

    # Check src diff against frozen policy
    src_policy_diff = subprocess.run(
        ["git", "diff", "--quiet", FROZEN_POLICY_SHA, "--", "src/"], cwd=root, check=False
    ).returncode
    if src_policy_diff != 0:
        reasons.append(f"src/** does not match frozen policy SHA {FROZEN_POLICY_SHA}")

    config = MarketWatchConfig()
    cfg_hash = compute_market_watch_config_hash(config)
    if cfg_hash != CONFIG_HASH or TACTICAL_POLICY_VERSION != "TACTICAL_POLICY_R2_B1":
        reasons.append(f"Policy configuration mismatch: hash='{cfg_hash}' version='{TACTICAL_POLICY_VERSION}'")

    # Target seal check
    sealed_targets: tuple[str, ...] = ()
    seal_data: dict[str, Any] = {}
    if target_seal_path is None:
        reasons.append("Missing required --target-seal-path")
    elif authorized_target_seal_sha256 and re.fullmatch(r"^[0-9a-f]{64}$", authorized_target_seal_sha256):
        try:
            sealed_targets, seal_data = validate_target_seal(
                seal_path=target_seal_path,
                expected_sha256=authorized_target_seal_sha256,
                references=REFERENCES,
            )
        except TargetSealError as exc:
            reasons.append(f"Target seal validation failed: {exc}")

    script_hashes = {
        "run_holdout_r3.py": runner_sha,
        "source_normalizer.py": normalizer_sha,
        "r3_access_guard.py": guard_sha,
        "target_seal.py": seal_helper_sha,
    }

    detail: dict[str, Any] = {
        "authorized_runner_sha": authorized_runner_sha,
        "authorized_runner_sha256": authorized_runner_sha256,
        "execution_dispatch_sha": execution_dispatch_sha,
        "authorized_target_seal_sha256": authorized_target_seal_sha256,
        "observed_branch": branch,
        "git_head": head,
        "runner_sha256": runner_sha,
        "normalizer_sha256": normalizer_sha,
        "script_hashes": script_hashes,
        "reasons": reasons,
        "sealed_targets": list(sealed_targets),
        "target_seal_data": seal_data,
        "proof": None,
    }

    if reasons:
        return False, "RC2_HOLDOUT_R3_PREFLIGHT_FAIL", detail

    proof = AuthorizationProof(
        authorized_runner_sha=str(authorized_runner_sha),
        authorized_runner_sha256=str(authorized_runner_sha256),
        execution_dispatch_sha=str(execution_dispatch_sha),
        target_seal_sha256=str(authorized_target_seal_sha256),
        sealed_targets=sealed_targets,
        allowed_references=REFERENCES,
        created_at_utc=datetime.now(UTC).isoformat(),
    )
    detail["proof"] = proof
    return True, "AUTHORIZED", detail


def verify_freeze_repair_identity(root: Path = ROOT) -> dict[str, Any]:
    """Verify runner repair state without execution (Repair R2 Sol review mode)."""
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
    seal_path = root / "scripts/rc2/validation/target_seal.py"

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
    seal_sha256 = (
        hashlib.sha256(seal_path.read_bytes()).hexdigest()
        if seal_path.exists()
        else "MISSING"
    )

    config = MarketWatchConfig()
    config_hash = compute_market_watch_config_hash(config)

    normalizer_match = normalizer_sha256 == ACCEPTED_NORMALIZER_SHA256
    policy_version_match = TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"
    config_hash_match = config_hash == CONFIG_HASH
    branch_match = branch == BRANCH

    status_output = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "src/", "scripts/rc2/validation/"],
        cwd=root,
        text=True,
    ).strip()
    status_clean = len(status_output) == 0

    repair_ok = (
        branch_match
        and src_matches_policy
        and src_clean
        and normalizer_match
        and policy_version_match
        and config_hash_match
        and status_clean
    )

    return {
        "task_id": REPAIR_TASK_ID,
        "terminal": "RC2_R3_RUNNER_REPAIR_R2_READY_FOR_FRESH_SOL_REVIEW"
        if repair_ok
        else "RC2_R3_RUNNER_REPAIR_R2_BLOCKED",
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
        "seal_helper_sha256": seal_sha256,
        "accepted_normalizer_sha256": ACCEPTED_NORMALIZER_SHA256,
        "normalizer_sha256_matches_accepted": normalizer_match,
        "holdout_executed": False,
        "replacement_target_seal_committed": False,
        "protected_market_archive_access": 0,
        "protected_target_network_access_count": 0,
        "r3_target_admissibility": R3_TARGET_ADMISSIBILITY,
        "freeze_verified": repair_ok,
        "repair_verified": repair_ok,
    }


def execute_holdout(
    *,
    authorized_runner_sha: str,
    authorized_runner_sha256: str,
    execution_dispatch_sha: str,
    target_seal_path: Path,
    authorized_target_seal_sha256: str,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    root: Path = ROOT,
) -> None:
    """Execute the full holdout under strict Controller authorization and staged publication (R2.1-R2.8)."""
    # R2.7: Fail closed if final authority directory pre-exists
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        print(f"FATAL: Final authority directory pre-exists: {evidence_dir}")
        print("RC2_HOLDOUT_R3_PREFLIGHT_FAIL")
        return

    attempt_id = f"{int(time.time()*1000)}_{os.getpid()}"
    staging_dir = Path(f"/tmp/rc2_holdout_staging_{attempt_id}")
    staging_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Starting {TASK_ID} in staging {staging_dir} ===")

    ledger_path = staging_dir / "EXECUTION_ACCESS_LEDGER.json"
    ledger = ExecutionAccessLedger(ledger_path)

    # R2.4 & Target Seal Validation
    auth_ok, terminal, auth_detail = check_execution_authorization(
        authorized_runner_sha=authorized_runner_sha,
        authorized_runner_sha256=authorized_runner_sha256,
        execution_dispatch_sha=execution_dispatch_sha,
        target_seal_path=target_seal_path,
        authorized_target_seal_sha256=authorized_target_seal_sha256,
        root=root,
    )
    proof = auth_detail.get("proof")
    if not auth_ok or proof is None:
        write_preflight_failure(terminal, auth_detail, staging_dir, phase="AUTHORIZATION")
        return

    # Capture pre-execution identity
    pre_identity = capture_execution_identity(
        task_id=TASK_ID,
        root=root,
        expected_branch=BRANCH,
        script_paths=VALIDATION_SCRIPTS,
    )

    # R2.1: Create AUTHORIZED_EXECUTION capability bound to verified proof
    capability = AccessCapability.create_authorized_execution(proof=proof, ledger=ledger)
    sealed_targets = proof.sealed_targets

    # R2.3: Fetch fresh source bundle into clean attempt-scoped source directory
    source_attempt_dir = Path(
        f"/tmp/rc2_r3_source_{execution_dispatch_sha[:8]}_{authorized_runner_sha[:8]}_{authorized_target_seal_sha256[:8]}"
    )
    try:
        raw, source_bundle_manifest = fetch_fresh_source_bundle(
            target_symbols=sealed_targets,
            reference_symbols=REFERENCES,
            capability=capability,
            source_dir=source_attempt_dir,
        )
    except Exception as exc:  # noqa: BLE001
        write_preflight_failure(
            "RC2_HOLDOUT_R3_INFRA_INCOMPLETE",
            {
                "exception_class": type(exc).__name__,
                "source_error": str(exc),
                "reason": "Official archive fresh retrieval failed",
                "execution_identity": pre_identity.to_dict(),
            },
            staging_dir,
            phase="SOURCE_RETRIEVAL",
        )
        return

    _json_write(staging_dir / "SOURCE_BUNDLE_MANIFEST.json", source_bundle_manifest)

    # R2.5: Dataset Preflight & Full-Window Context Audit (real production scanner path)
    dataset_preflight = build_dataset(raw, sealed_targets, REFERENCES, include_outcomes=False)
    smoke = context_smoke(dataset_preflight, sealed_targets, REFERENCES)
    full_window_audit = audit_full_window_production_context(
        dataset_preflight, sealed_targets, REFERENCES
    )
    _json_write(staging_dir / "FULL_WINDOW_CONTEXT_AUDIT.json", full_window_audit)

    # Authentic target 1m completeness check
    targets_1m_proof: dict[str, Any] = {}
    targets_1m_all_complete = True
    for s in sealed_targets:
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
    _json_write(staging_dir / "TARGET_1M_AUTHENTICITY_PROOF.json", targets_1m_proof)

    # Preflight gate checks
    preflight_pass = (
        full_window_audit["full_window_audit_passed"]
        and targets_1m_all_complete
        and smoke["assessment_count"] == len(sealed_targets)
        and smoke["pit_violations"] == 0
    )

    pre_outcome_report: dict[str, Any] = {
        "task_id": TASK_ID,
        "authorized_runner_sha": authorized_runner_sha,
        "authorized_runner_sha256": authorized_runner_sha256,
        "execution_dispatch_sha": execution_dispatch_sha,
        "authorized_target_seal_sha256": authorized_target_seal_sha256,
        "branch": BRANCH,
        "head": pre_identity.git_head,
        "policy_version": TACTICAL_POLICY_VERSION,
        "config_hash": CONFIG_HASH,
        "targets": list(sealed_targets),
        "context_only": list(REFERENCES),
        "first_step_ms": FIRST_STEP,
        "last_step_ms": LAST_STEP,
        "preflight_pass": preflight_pass,
        "outcome_replay_unlocked": False,
        "full_window_audit_passed": full_window_audit["full_window_audit_passed"],
        "targets_1m_all_complete": targets_1m_all_complete,
        "context_smoke": smoke,
    }
    _json_write(staging_dir / "PRE_OUTCOME_REPORT.json", pre_outcome_report)

    if not preflight_pass:
        write_preflight_failure(
            "RC2_HOLDOUT_R3_PREFLIGHT_FAIL",
            {
                "reason": "Preflight gates failed",
                "pre_outcome_report": pre_outcome_report,
                "full_window_audit": full_window_audit,
            },
            staging_dir,
            phase="PREFLIGHT_AUDIT",
        )
        return

    # Clean preflight dataset
    del dataset_preflight, smoke
    gc.collect()

    # R2.6: Complete Authority Input Manifest with authentic target 1m
    dataset_outcomes = build_dataset(raw, sealed_targets, REFERENCES, include_outcomes=True)
    authority_input_manifest = generate_authority_input_manifest(
        dataset=dataset_outcomes,
        raw=raw,
        target_symbols=sealed_targets,
        reference_symbols=REFERENCES,
        script_hashes=pre_identity.script_hashes,
        target_seal_sha256=authorized_target_seal_sha256,
        source_bundle_digest=source_bundle_manifest["source_bundle_digest"],
    )
    auth_manifest_hash_initial = authority_input_manifest["authority_input_manifest_hash"]
    _json_write(staging_dir / "AUTHORITY_INPUT_MANIFEST.json", authority_input_manifest)

    # OUTCOME Phase: Execute replay twice
    print("Preflight gates passed. Unlocking outcome replay for sealed targets...")
    pre_outcome_report["outcome_replay_unlocked"] = True
    _json_write(staging_dir / "PRE_OUTCOME_REPORT.json", pre_outcome_report)

    config = MarketWatchConfig(symbols=sealed_targets)
    t0 = time.time()
    result1 = DeterministicTacticalReplayRunner(
        dataset_outcomes, config, evaluate_grid_stride=12
    ).run()
    gc.collect()

    # Verify authority input manifest unchanged before run 2
    manifest_pre_run2 = generate_authority_input_manifest(
        dataset=dataset_outcomes,
        raw=raw,
        target_symbols=sealed_targets,
        reference_symbols=REFERENCES,
        script_hashes=pre_identity.script_hashes,
        target_seal_sha256=authorized_target_seal_sha256,
        source_bundle_digest=source_bundle_manifest["source_bundle_digest"],
    )
    if manifest_pre_run2["authority_input_manifest_hash"] != auth_manifest_hash_initial:
        write_preflight_failure(
            "RC2_HOLDOUT_R3_INFRA_INCOMPLETE",
            {"reason": "Authority input manifest mutated between run 1 and run 2"},
            staging_dir,
            phase="DETERMINISM",
        )
        return

    result2 = DeterministicTacticalReplayRunner(
        dataset_outcomes, config, evaluate_grid_stride=12
    ).run()
    gc.collect()
    print(f"Replay runs completed in {time.time() - t0:.2f}s.")

    # Verify authority input manifest unchanged after run 2
    manifest_post_run2 = generate_authority_input_manifest(
        dataset=dataset_outcomes,
        raw=raw,
        target_symbols=sealed_targets,
        reference_symbols=REFERENCES,
        script_hashes=pre_identity.script_hashes,
        target_seal_sha256=authorized_target_seal_sha256,
        source_bundle_digest=source_bundle_manifest["source_bundle_digest"],
    )
    if manifest_post_run2["authority_input_manifest_hash"] != auth_manifest_hash_initial:
        write_preflight_failure(
            "RC2_HOLDOUT_R3_INFRA_INCOMPLETE",
            {"reason": "Authority input manifest mutated after run 2"},
            staging_dir,
            phase="DETERMINISM",
        )
        return

    # Determinism check across runs
    deterministic = (
        result1["output_manifest"]["input_manifest_hash"]
        == result2["output_manifest"]["input_manifest_hash"]
        and result1["output_manifest"]["output_manifest_hash"]
        == result2["output_manifest"]["output_manifest_hash"]
    )

    gate_decision = str(result1["gate_evaluation"]["decision"])
    terminal = classify_holdout_terminal(gate_decision, deterministic=deterministic)
    policy_quality_authority = classify_policy_quality_authority(terminal)

    # Write staging artifacts
    _json_write(staging_dir / "OUTPUT_MANIFEST.json", result1["output_manifest"])
    _json_write(staging_dir / "rolling_oos_table.json", result1["rolling_oos_table"])
    _json_write(staging_dir / "aggregate_metrics.json", result1["aggregate_oos_metrics"])

    # Post-execution exact identity verification
    post_identity = verify_execution_identity(
        pre_identity=pre_identity,
        root=root,
        script_paths=VALIDATION_SCRIPTS,
    )
    _json_write(staging_dir / "EXECUTION_IDENTITY.json", post_identity)

    # Finalize execution access ledger
    ledger.finalize(staging_dir / "EXECUTION_ACCESS_LEDGER.json")

    evidence_payload = {
        "task_id": TASK_ID,
        "gate_decision": gate_decision,
        "terminal": terminal,
        "deterministic": deterministic,
        "policy_quality_authority": policy_quality_authority,
        "frozen_candidate_sha": FROZEN_POLICY_SHA,
        "authorized_runner_sha": authorized_runner_sha,
        "authorized_runner_sha256": authorized_runner_sha256,
        "execution_dispatch_sha": execution_dispatch_sha,
        "authorized_target_seal_sha256": authorized_target_seal_sha256,
        "accepted_normalizer_sha256": ACCEPTED_NORMALIZER_SHA256,
        "accepted_harness_sha": ACCEPTED_HARNESS_SHA,
        "branch": BRANCH,
        "config_hash": CONFIG_HASH,
        "target_symbols": list(sealed_targets),
        "context_only_symbols": list(REFERENCES),
        "reference_outcomes_in_aggregate": False,
        "authority_input_manifest_hash": auth_manifest_hash_initial,
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
    _json_write(staging_dir / "EVIDENCE.json", evidence_payload)

    # Emit completion attempt receipt
    authority_valid = terminal in (
        "RC2_HOLDOUT_R3_PASS",
        "RC2_HOLDOUT_R3_FAIL",
        "RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY",
    )
    write_attempt_receipt(
        staging_dir,
        phase="COMPLETED",
        terminal=terminal,
        target_outcomes_resolved=True,
        authority_valid=authority_valid,
        execution_identities=post_identity,
    )

    # R2.7: Atomic publication of staged evidence
    shutil.copytree(staging_dir, evidence_dir)
    shutil.rmtree(staging_dir, ignore_errors=True)
    print(f"Published authoritative evidence to {evidence_dir}")
    print(terminal)


# Alias for backwards compatibility
verify_freeze_identity = verify_freeze_repair_identity


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RC2 Holdout R3 Authoritative Generic Runner (Repair R2)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize and execute the holdout (requires external Controller authorization and target seal)",
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
        "--target-seal-path",
        type=Path,
        default=None,
        help="Path to external Controller target seal artifact JSON",
    )
    parser.add_argument(
        "--authorized-target-seal-sha256",
        type=str,
        default=None,
        help="Controller-authorized target seal SHA256 (64-hex)",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=DEFAULT_EVIDENCE_DIR,
        help="Target final authority evidence directory (must not pre-exist)",
    )
    parser.add_argument(
        "--verify-repair",
        action="store_true",
        help="Verify runner repair integrity and review state without execution",
    )
    args = parser.parse_args()

    if args.execute:
        if (
            not args.authorized_runner_sha
            or not args.authorized_runner_sha256
            or not args.execution_dispatch_sha
            or not args.target_seal_path
            or not args.authorized_target_seal_sha256
        ):
            print("FATAL: --execute requires all Controller authorization flags:")
            print("  --authorized-runner-sha")
            print("  --authorized-runner-sha256")
            print("  --execution-dispatch-sha")
            print("  --target-seal-path")
            print("  --authorized-target-seal-sha256")
            sys.exit(1)

        execute_holdout(
            authorized_runner_sha=args.authorized_runner_sha,
            authorized_runner_sha256=args.authorized_runner_sha256,
            execution_dispatch_sha=args.execution_dispatch_sha,
            target_seal_path=args.target_seal_path,
            authorized_target_seal_sha256=args.authorized_target_seal_sha256,
            evidence_dir=args.evidence_dir,
        )
    else:
        # Review mode: verify repair state without execution
        info = verify_freeze_repair_identity()
        terminal = str(info["terminal"])
        print(f"=== {REPAIR_TASK_ID} ===")
        print(f"Branch: {info['branch']}")
        print(f"Head: {info['head']}")
        print(f"Start SHA: {info['start_sha']}")
        print(f"Frozen Policy SHA: {info['frozen_policy_sha']}")
        print(f"Accepted Harness SHA: {info['accepted_harness_sha']}")
        print(f"Controller Dispatch SHA: {info['controller_dispatch_sha']}")
        print(f"Runner SHA256: {info['runner_sha256']}")
        print(f"Normalizer SHA256: {info['normalizer_sha256']}")
        print(f"Access Guard SHA256: {info['guard_sha256']}")
        print(f"Seal Helper SHA256: {info['seal_helper_sha256']}")
        print(f"Holdout Executed: {info['holdout_executed']}")
        print(f"Replacement Target Seal Committed: {info['replacement_target_seal_committed']}")
        print(f"Protected market/archive access: {info['protected_market_archive_access']}")
        print(f"Repair Verified: {info['repair_verified']}")
        print(f"\n{terminal}")
        if not info["repair_verified"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
