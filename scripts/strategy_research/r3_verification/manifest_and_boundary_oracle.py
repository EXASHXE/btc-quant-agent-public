"""Independent Static Manifest Schema Checker & Source/Holdout Boundary Verifier."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.strategy_research.r3_verification.oracle_specs import (
    ALLOWLISTED_MANIFEST_MARKETS,
    ALLOWLISTED_SYMBOLS,
    ONE_MINUTE_MS,
    R3_PROPOSED_DEV_WINDOWS_MS,
    R3_PROPOSED_WARMUP_WINDOW_MS,
    RC2_PROTECTED_SYMBOLS,
    REQUIRED_SOURCE_DATA_GRADE,
    V03_BTC_FINAL_HOLDOUT_END_MS,
    V03_BTC_FINAL_HOLDOUT_START_MS,
)

EXPECTED_BTC_MANIFEST_RELPATH = (
    "artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json"
)
EXPECTED_BTC_DATASET_SHA256 = (
    "82d058b2e9e5bfbd20bf36026abec045fb778ddb72582277e0dac00846ae9901"
)
EXPECTED_BTC_FUNDING_SHA256 = (
    "4fd56440f275c351e521f483309b8a368ab8da66b5b6e070e164f985fc0e6ba3"
)
EXPECTED_BTC_ROW_COUNT = 2_934_720
EXPECTED_BTC_MONTH_COUNT = 67
EXPECTED_BTC_FUNDING_ROW_COUNT = 6_114
EXPECTED_BTC_ZERO_VOLUME_COUNT = 367
EXPECTED_DAILY_MARK_ARCHIVE_COUNT = 9

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

DENYLIST_PATH_TOKENS: tuple[str, ...] = (
    "final_holdout",
    "final-holdout",
    "data/forward",
    "h39_validation",
    "h40",
    "h41",
    "a_line",
    "a-line",
    "var/quant.db",
    "rc2",
    "g2-overnight-discovery-a",
)

FORBIDDEN_FILE_EXTENSIONS: tuple[str, ...] = (
    ".parquet",
    ".zip",
    ".csv",
    ".feather",
    ".arrow",
    ".db",
    ".sqlite",
)

FORBIDDEN_NETWORK_HOSTS: tuple[str, ...] = (
    "api.binance.com",
    "fapi.binance.com",
    "dapi.binance.com",
    "testnet.binancefuture.com",
    "testnet.binance.vision",
    "stream.binance.com",
    "fstream.binance.com",
)


def _expected_months_2021_01_to_2026_07() -> list[str]:
    months: list[str] = []
    for year in range(2021, 2027):
        max_m = 7 if year == 2026 else 12
        for month in range(1, max_m + 1):
            months.append(f"{year:04d}-{month:02d}")
    return months


@dataclass(frozen=True)
class ManifestVerificationResult:
    """Result of static metadata verification of BTC `data_manifest.json`."""

    valid: bool
    manifest_relpath: str
    symbol: str
    market: str
    timeframe: str
    month_count: int
    row_count: int
    expected_bars: int
    missing_count: int
    duplicate_count: int
    out_of_order_count: int
    invalid_ohlc_count: int
    negative_volume_count: int
    known_gaps_count: int
    largest_gap_missing_bars: int
    zero_volume_count: int
    dataset_checksum_sha256: str
    funding_checksum_sha256: str
    funding_row_count: int
    funding_missing_mark_prices: int
    funding_mark_price_semantics: str
    monthly_kline_archive_count: int
    monthly_mark_archive_count: int
    monthly_funding_archive_count: int
    daily_mark_archive_count: int
    source_data_grade: str
    prior_exposures_remain_exposed: bool
    blind_oos_claim_permitted: bool
    parquet_or_zip_reads: int
    errors: tuple[str, ...]


def verify_static_btc_data_manifest(
    manifest_data_or_path: dict[str, Any] | Path | str,
    *,
    declared_source_grade: str = REQUIRED_SOURCE_DATA_GRADE,
    claim_blind_oos: bool = False,
) -> ManifestVerificationResult:
    """Verify public static `data_manifest.json` without touching any Parquet or ZIP body."""
    errors: list[str] = []
    manifest_relpath = EXPECTED_BTC_MANIFEST_RELPATH

    if isinstance(manifest_data_or_path, (str, Path)):
        raw_str = str(manifest_data_or_path).replace("\\", "/")
        if any(raw_str.lower().endswith(ext) for ext in FORBIDDEN_FILE_EXTENSIONS):
            raise ValueError(f"FORBIDDEN_RAW_DATA_BODY_PATH:{raw_str}")
        if any(tok in raw_str.lower() for tok in DENYLIST_PATH_TOKENS):
            raise ValueError(f"FORBIDDEN_DENYLIST_PATH:{raw_str}")
        p = Path(manifest_data_or_path)
        data = json.loads(p.read_text(encoding="utf-8"))
    else:
        data = manifest_data_or_path

    symbol = str(data.get("symbol", ""))
    market = str(data.get("market", ""))
    timeframe = str(data.get("timeframe", ""))
    timezone = str(data.get("timezone", ""))
    start_ms = int(data.get("start_ms", 0))
    end_ms_exclusive = int(data.get("end_ms_exclusive", 0))
    expected_bars = int(data.get("expected_bars", -1))
    row_count = int(data.get("row_count", -1))
    missing_count = int(data.get("missing_count", -1))
    duplicate_count = int(data.get("duplicate_count", -1))
    out_of_order_count = int(data.get("out_of_order_count", -1))
    invalid_ohlc_count = int(data.get("invalid_ohlc_count", -1))
    negative_volume_count = int(data.get("negative_volume_count", -1))
    synthetic_rows = int(data.get("synthetic_rows", -1))
    zero_volume_count = int(data.get("zero_volume_count", -1))
    largest_gap = int(data.get("largest_gap_missing_bars", -1))
    known_gaps = data.get("known_gaps", None)
    dataset_sha = str(data.get("checksum_sha256", ""))

    if symbol != "BTCUSDT":
        errors.append(f"UNEXPECTED_SYMBOL:{symbol}")
    if market != "USD-M PERPETUAL":
        errors.append(f"UNEXPECTED_MARKET:{market}")
    if timeframe != "1m":
        errors.append(f"UNEXPECTED_TIMEFRAME:{timeframe}")
    if timezone != "UTC":
        errors.append(f"UNEXPECTED_TIMEZONE:{timezone}")
    if start_ms != 1_609_459_200_000 or end_ms_exclusive != 1_785_542_400_000:
        errors.append(f"UNEXPECTED_SPAN_MS:{start_ms}..{end_ms_exclusive}")

    span_minutes = (end_ms_exclusive - start_ms) // ONE_MINUTE_MS
    if (
        expected_bars != EXPECTED_BTC_ROW_COUNT
        or row_count != EXPECTED_BTC_ROW_COUNT
        or span_minutes != EXPECTED_BTC_ROW_COUNT
    ):
        errors.append(
            f"ROW_COUNT_MISMATCH:row_count={row_count}:expected_bars={expected_bars}:span={span_minutes}"
        )

    if (
        missing_count != 0
        or duplicate_count != 0
        or out_of_order_count != 0
        or invalid_ohlc_count != 0
        or negative_volume_count != 0
        or synthetic_rows != 0
        or largest_gap != 0
        or known_gaps != []
    ):
        errors.append("NON_ZERO_GAP_OR_CORRUPTION_COUNTERS")

    if zero_volume_count != EXPECTED_BTC_ZERO_VOLUME_COUNT:
        errors.append(f"UNEXPECTED_ZERO_VOLUME_COUNT:{zero_volume_count}")

    if dataset_sha != EXPECTED_BTC_DATASET_SHA256 or not HEX64_RE.match(dataset_sha):
        errors.append(f"DATASET_SHA256_MISMATCH:{dataset_sha}")

    # Verify 67 monthly partition checksums
    part_checksums = data.get("partition_checksums", {})
    if not isinstance(part_checksums, dict):
        errors.append("INVALID_PARTITION_CHECKSUMS_TYPE")
        part_checksums = {}

    expected_months = _expected_months_2021_01_to_2026_07()
    expected_part_keys = [
        f"1m/year={ym[:4]}/month={ym[5:7]}/data.parquet" for ym in expected_months
    ]
    if sorted(part_checksums.keys()) != expected_part_keys:
        errors.append(f"PARTITION_KEYS_MISMATCH:count={len(part_checksums)}")
    for k, v in part_checksums.items():
        if not isinstance(v, str) or not HEX64_RE.match(v):
            errors.append(f"INVALID_PARTITION_SHA256:{k}")

    # Verify funding section
    funding = data.get("funding", {})
    if not isinstance(funding, dict):
        errors.append("INVALID_FUNDING_SECTION")
        funding = {}
    f_sha = str(funding.get("checksum_sha256", ""))
    f_rows = int(funding.get("row_count", -1))
    f_dups = int(funding.get("duplicate_count", -1))
    f_missing_mark = int(funding.get("missing_mark_prices", -1))
    f_semantics = str(funding.get("mark_price_semantics", ""))
    f_start = int(funding.get("start_ms", 0))
    f_end = int(funding.get("end_ms", 0))

    if f_sha != EXPECTED_BTC_FUNDING_SHA256 or not HEX64_RE.match(f_sha):
        errors.append(f"FUNDING_SHA256_MISMATCH:{f_sha}")
    if f_rows != EXPECTED_BTC_FUNDING_ROW_COUNT:
        errors.append(f"FUNDING_ROW_COUNT_MISMATCH:{f_rows}")
    if f_dups != 0 or f_missing_mark != 0:
        errors.append("FUNDING_DUPLICATE_OR_MISSING_MARK")
    if (
        f_semantics
        != "official 1m mark-price candle open for the UTC minute containing the settlement timestamp"
    ):
        errors.append(f"UNEXPECTED_FUNDING_MARK_SEMANTICS:{f_semantics}")
    if f_start != 1_609_459_200_002 or f_end != 1_785_513_600_000:
        errors.append(f"UNEXPECTED_FUNDING_SPAN:{f_start}..{f_end}")

    # Verify official_archive_checksums (klines, markPriceKlines, fundingRate)
    archives = data.get("official_archive_checksums", {})
    if not isinstance(archives, dict):
        errors.append("INVALID_OFFICIAL_ARCHIVE_CHECKSUMS")
        archives = {}

    kline_urls = [
        f"https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-{ym}.zip"
        for ym in expected_months
    ]
    mark_monthly_urls = [
        f"https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-{ym}.zip"
        for ym in expected_months
    ]
    funding_urls = [
        f"https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{ym}.zip"
        for ym in expected_months
    ]

    found_klines = sum(1 for u in kline_urls if u in archives)
    found_mark_monthly = sum(1 for u in mark_monthly_urls if u in archives)
    found_funding = sum(1 for u in funding_urls if u in archives)
    found_mark_daily = sum(
        1
        for u in archives
        if u.startswith(
            "https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/"
        )
    )

    if found_klines != EXPECTED_BTC_MONTH_COUNT:
        errors.append(f"MONTHLY_KLINE_ARCHIVE_COUNT_MISMATCH:{found_klines}")
    if found_mark_monthly != EXPECTED_BTC_MONTH_COUNT:
        errors.append(f"MONTHLY_MARK_ARCHIVE_COUNT_MISMATCH:{found_mark_monthly}")
    if found_funding != EXPECTED_BTC_MONTH_COUNT:
        errors.append(f"MONTHLY_FUNDING_ARCHIVE_COUNT_MISMATCH:{found_funding}")
    if found_mark_daily != EXPECTED_DAILY_MARK_ARCHIVE_COUNT:
        errors.append(f"DAILY_MARK_ARCHIVE_COUNT_MISMATCH:{found_mark_daily}")

    for u, sha in archives.items():
        if not isinstance(sha, str) or not HEX64_RE.match(sha):
            errors.append(f"INVALID_ARCHIVE_SHA256:{u}")

    if declared_source_grade != REQUIRED_SOURCE_DATA_GRADE:
        errors.append(f"INVALID_DECLARED_SOURCE_GRADE:{declared_source_grade}")
    if claim_blind_oos:
        errors.append("FORBIDDEN_BLIND_OOS_CLAIM_ON_EXPOSED_HISTORIC_DATA")

    return ManifestVerificationResult(
        valid=(len(errors) == 0),
        manifest_relpath=manifest_relpath,
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        month_count=len(part_checksums),
        row_count=row_count,
        expected_bars=expected_bars,
        missing_count=missing_count,
        duplicate_count=duplicate_count,
        out_of_order_count=out_of_order_count,
        invalid_ohlc_count=invalid_ohlc_count,
        negative_volume_count=negative_volume_count,
        known_gaps_count=len(known_gaps) if isinstance(known_gaps, list) else -1,
        largest_gap_missing_bars=largest_gap,
        zero_volume_count=zero_volume_count,
        dataset_checksum_sha256=dataset_sha,
        funding_checksum_sha256=f_sha,
        funding_row_count=f_rows,
        funding_missing_mark_prices=f_missing_mark,
        funding_mark_price_semantics=f_semantics,
        monthly_kline_archive_count=found_klines,
        monthly_mark_archive_count=found_mark_monthly,
        monthly_funding_archive_count=found_funding,
        daily_mark_archive_count=found_mark_daily,
        source_data_grade=declared_source_grade,
        prior_exposures_remain_exposed=True,
        blind_oos_claim_permitted=False,
        parquet_or_zip_reads=0,
        errors=tuple(errors),
    )


@dataclass(frozen=True)
class HoldoutConflictReport:
    """Report on v0.3 BTC final holdout conflict with R3 proposed Feb-Apr 2026 development windows."""

    conflict_detected: bool
    status: str
    v03_holdout_start_ms: int
    v03_holdout_end_ms: int
    overlapping_r3_folds: tuple[dict[str, object], ...]
    total_overlapping_minutes_per_symbol: int
    silent_reclassification_permitted: bool
    return_based_date_selection_permitted: bool
    eligible_exposed_pre2026_btc_months: tuple[str, ...]
    proposed_calendar_only_substitute_options: tuple[dict[str, object], ...]


def check_HoldoutWindowOverlap(
    proposed_windows_ms: tuple[tuple[int, int], ...] = R3_PROPOSED_DEV_WINDOWS_MS,
    warmup_window_ms: tuple[int, int] = R3_PROPOSED_WARMUP_WINDOW_MS,
) -> HoldoutConflictReport:
    """Verify whether proposed development/warmup windows overlap v0.3 holdout [2026-02-01, 2026-08-01)."""
    overlapping: list[dict[str, object]] = []
    total_overlap_min = 0

    all_to_check = [("WARMUP", warmup_window_ms)] + [
        (f"DEV_FOLD_{idx + 1}", w) for idx, w in enumerate(proposed_windows_ms)
    ]

    for label, (w_start, w_end) in all_to_check:
        ov_start = max(w_start, V03_BTC_FINAL_HOLDOUT_START_MS)
        ov_end = min(w_end, V03_BTC_FINAL_HOLDOUT_END_MS)
        if ov_end > ov_start:
            ov_min = (ov_end - ov_start) // ONE_MINUTE_MS
            total_overlap_min += ov_min
            overlapping.append(
                {
                    "fold_label": label,
                    "window_start_ms": w_start,
                    "window_end_ms": w_end,
                    "overlap_start_ms": ov_start,
                    "overlap_end_ms": ov_end,
                    "overlap_minutes": ov_min,
                    "reason": "OVERLAPS_V03_BTC_FINAL_HOLDOUT_2026_02_TO_2026_08",
                }
            )

    pre2026_months = tuple(
        f"{y:04d}-{m:02d}" for y in range(2021, 2026) for m in range(1, 13)
    )

    # Calendar-only candidate substitute windows from pre-2026 exposed history (never chosen by returns)
    substitute_options = (
        {
            "option_id": "CALENDAR_OPTION_A_2025_Q4",
            "warmup_month": "2025-09",
            "development_folds": ["2025-10", "2025-11", "2025-12"],
            "exposure_grade": "HISTORICAL_EXPOSED_DEVELOPMENT",
            "source_data_grade": REQUIRED_SOURCE_DATA_GRADE,
            "v03_holdout_overlap_minutes": 0,
            "selection_basis": "MOST_RECENT_CONTIGUOUS_PRE_2026_QUARTER_CALENDAR_ONLY",
            "requires_controller_method_amendment": True,
            "requires_eth_sol_archive_admission": True,
            "returns_inspected": False,
        },
        {
            "option_id": "CALENDAR_OPTION_B_2025_Q2",
            "warmup_month": "2025-03",
            "development_folds": ["2025-04", "2025-05", "2025-06"],
            "exposure_grade": "HISTORICAL_EXPOSED_DEVELOPMENT",
            "source_data_grade": REQUIRED_SOURCE_DATA_GRADE,
            "v03_holdout_overlap_minutes": 0,
            "selection_basis": "CONTIGUOUS_PRE_2026_H1_CALENDAR_ONLY",
            "requires_controller_method_amendment": True,
            "requires_eth_sol_archive_admission": True,
            "returns_inspected": False,
        },
        {
            "option_id": "CALENDAR_OPTION_C_2024_Q4",
            "warmup_month": "2024-09",
            "development_folds": ["2024-10", "2024-11", "2024-12"],
            "exposure_grade": "HISTORICAL_EXPOSED_DEVELOPMENT",
            "source_data_grade": REQUIRED_SOURCE_DATA_GRADE,
            "v03_holdout_overlap_minutes": 0,
            "selection_basis": "CONTIGUOUS_2024_Q4_CALENDAR_ONLY",
            "requires_controller_method_amendment": True,
            "requires_eth_sol_archive_admission": True,
            "returns_inspected": False,
        },
    )

    conflict = len(overlapping) > 0
    return HoldoutConflictReport(
        conflict_detected=conflict,
        status="HOLDOUT_OVERLAP_BLOCKED" if conflict else "NO_V03_HOLDOUT_OVERLAP",
        v03_holdout_start_ms=V03_BTC_FINAL_HOLDOUT_START_MS,
        v03_holdout_end_ms=V03_BTC_FINAL_HOLDOUT_END_MS,
        overlapping_r3_folds=tuple(overlapping),
        total_overlapping_minutes_per_symbol=total_overlap_min,
        silent_reclassification_permitted=False,
        return_based_date_selection_permitted=False,
        eligible_exposed_pre2026_btc_months=pre2026_months,
        proposed_calendar_only_substitute_options=substitute_options,
    )


@dataclass(frozen=True)
class BoundaryCheckResult:
    """Result of lexical/metadata boundary check for sources, symbols, products, and dates."""

    allowed: bool
    status: str
    violations: tuple[str, ...]


def check_source_and_product_boundary(
    *,
    symbol: str,
    market_product: str,
    source_path_or_url: str = "",
    window_start_ms: int | None = None,
    window_end_ms: int | None = None,
    source_grade: str = REQUIRED_SOURCE_DATA_GRADE,
    is_blind_oos_claim: bool = False,
) -> BoundaryCheckResult:
    """Reject protected symbols, wrong products, denylist paths, network endpoints, and v0.3 holdout dates."""
    violations: list[str] = []

    norm_sym = symbol.strip().upper()
    if norm_sym in RC2_PROTECTED_SYMBOLS:
        violations.append(f"RC2_PROTECTED_SYMBOL_FORBIDDEN:{norm_sym}")
    elif norm_sym not in ALLOWLISTED_SYMBOLS:
        violations.append(f"UNALLOWLISTED_SYMBOL:{norm_sym}")

    norm_market = market_product.strip().upper()
    if norm_market not in ALLOWLISTED_MANIFEST_MARKETS:
        violations.append(f"WRONG_PRODUCT_OR_MARKET:{market_product}")

    if source_path_or_url:
        norm_src = source_path_or_url.strip().replace("\\", "/").lower()
        for tok in DENYLIST_PATH_TOKENS:
            if tok in norm_src:
                violations.append(f"SOURCE_DENYLIST_PATH:{tok}")
        for ext in FORBIDDEN_FILE_EXTENSIONS:
            if norm_src.endswith(ext):
                violations.append(f"FORBIDDEN_RAW_DATA_BODY_EXTENSION:{ext}")
        for host in FORBIDDEN_NETWORK_HOSTS:
            if host in norm_src:
                violations.append(f"FORBIDDEN_LIVE_OR_TESTNET_HOST:{host}")
        if norm_src.startswith(("http://", "https://", "wss://", "ws://")):
            violations.append("FORBIDDEN_EXTERNAL_NETWORK_READ_AT_P0")

    if window_start_ms is not None and window_end_ms is not None:
        if window_end_ms <= window_start_ms:
            violations.append("INVALID_WINDOW_RANGE")
        else:
            ov_start = max(window_start_ms, V03_BTC_FINAL_HOLDOUT_START_MS)
            ov_end = min(window_end_ms, V03_BTC_FINAL_HOLDOUT_END_MS)
            if ov_end > ov_start:
                violations.append(
                    f"V03_PROTECTED_HOLDOUT_DATE_OVERLAP:{ov_start}..{ov_end}"
                )

    if source_grade != REQUIRED_SOURCE_DATA_GRADE:
        violations.append(f"INVALID_SOURCE_GRADE:{source_grade}")

    if is_blind_oos_claim:
        violations.append("FORBIDDEN_BLIND_OOS_CLAIM")

    return BoundaryCheckResult(
        allowed=(len(violations) == 0),
        status="BOUNDARY_OK" if not violations else "BOUNDARY_BLOCKED",
        violations=tuple(violations),
    )
