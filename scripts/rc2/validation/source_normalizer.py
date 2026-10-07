"""Validation harness source normalizer and cache authority for RC2.

Provides:
- Strict protected symbol firewall
- Event-time normalization of Binance metrics archives
- Deterministic deduplication and permutation invariance
- Identity-bound cache authority
- Pre/post execution runner identity assertions
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import random
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Whitelist of non-protected/already-exposed symbols authorized for validation qualification.
ALLOWED_NON_PROTECTED_SYMBOLS: frozenset[str] = frozenset(
    {
        # Burned R1 targets
        "ADAUSDT",
        "AVAXUSDT",
        "LTCUSDT",
        "TRXUSDT",
        "BCHUSDT",
        "DOTUSDT",
        "ATOMUSDT",
        "NEARUSDT",
        "ADA",
        "AVAX",
        "LTC",
        "TRX",
        "BCH",
        "DOT",
        "ATOM",
        "NEAR",
        # Burned R1.1 targets
        "FILUSDT",
        "ETCUSDT",
        "AAVEUSDT",
        "XLMUSDT",
        "UNIUSDT",
        "ICPUSDT",
        "ARBUSDT",
        "OPUSDT",
        "FIL",
        "ETC",
        "AAVE",
        "XLM",
        "UNI",
        "ICP",
        "ARB",
        "OP",
        # Development / Context benchmarks
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "LINKUSDT",
        "SUIUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "BNBUSDT",
        "BTC",
        "ETH",
        "SOL",
        "LINK",
        "SUI",
        "XRP",
        "DOGE",
        "BNB",
    }
)

PARSER_SCHEMA_VERSION = "RC2_METRICS_EVENT_TIME_NORMALIZER_V2"
CACHE_SCHEMA_VERSION = "RC2_CACHE_AUTHORITY_V2"


class ProtectedSymbolFirewallViolation(PermissionError):
    """Raised when an unexposed or protected symbol is accessed."""


class CacheAuthorityError(RuntimeError):
    """Raised when cache identity check fails closed."""


class RunnerIdentityMismatchError(RuntimeError):
    """Raised when git HEAD or script hashes change during execution."""


def assert_symbol_allowed(symbol: str) -> None:
    """Enforce that symbol is in the allowed non-protected set."""
    clean = symbol.strip().upper()
    if clean not in ALLOWED_NON_PROTECTED_SYMBOLS:
        raise ProtectedSymbolFirewallViolation(
            f"Symbol '{clean}' is protected or unauthorized! Only burned/development symbols allowed."
        )


def assert_all_symbols_allowed(symbols: Iterable[str]) -> None:
    """Enforce that all symbols in collection are authorized."""
    for s in symbols:
        assert_symbol_allowed(s)


def parse_event_timestamp(ts_val: str | int) -> int:
    """Parse create_time / event timestamp explicitly to UTC millisecond epoch."""
    if isinstance(ts_val, int):
        return ts_val
    s = ts_val.strip()
    if s.isdigit():
        return int(s)
    # Binance metrics CSV standard format: 'YYYY-MM-DD HH:MM:SS'
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def normalize_metrics_rows(
    rows: list[list[str]],
    header: list[str],
    tf_start: int,
    data_end: int,
) -> dict[str, Any]:
    """Normalize Binance metrics archive rows into chronological derivative series.

    Guarantees:
    1. Event timestamp parsed explicitly from create_time.
    2. Stable-sorted by (timestamp, tuple(row)) for canonical ordering.
    3. Deterministically deduplicated on equal timestamps.
    4. Hourly series choose max event timestamp inside each UTC hour bucket.
    5. 15m series choose max event timestamp inside each UTC 15m bucket.
    6. Row order in archive has ZERO influence on normalized output.
    """
    indexes = {name: header.index(name) for name in header}
    create_time_idx = indexes["create_time"]
    oi_idx = indexes["sum_open_interest"]
    taker_idx = indexes["sum_taker_long_short_vol_ratio"]
    gls_idx = indexes["count_long_short_ratio"]
    top_pos_idx = indexes["sum_toptrader_long_short_ratio"]
    top_acc_idx = indexes["count_toptrader_long_short_ratio"]

    parsed_records: list[tuple[int, list[str]]] = []
    for r in rows:
        if not r or len(r) < len(header):
            continue
        if r[create_time_idx].lower() in {"create_time", "calc_time"}:
            continue
        ts = parse_event_timestamp(r[create_time_idx])
        if tf_start <= ts <= data_end:
            parsed_records.append((ts, r))

    # 1. Deterministic sort by (timestamp, tuple(row))
    sorted_records = sorted(parsed_records, key=lambda item: (item[0], tuple(item[1])))

    # 2. Deterministic deduplication for equal timestamps
    deduped_records: list[tuple[int, list[str]]] = []
    seen_ts: set[int] = set()
    for ts, r in sorted_records:
        if ts not in seen_ts:
            seen_ts.add(ts)
            deduped_records.append((ts, r))

    # 3. Downsample hourly (oi, gls, top_pos, top_acc) - select max event timestamp in bucket
    hourly_selected: dict[int, tuple[int, list[str]]] = {}
    for ts, r in deduped_records:
        bucket = ts // 3_600_000
        # Since deduped_records is strictly increasing in ts, replacing ensures max ts in bucket
        hourly_selected[bucket] = (ts, r)

    hourly_sorted = [hourly_selected[b] for b in sorted(hourly_selected.keys())]

    oi_hist = [
        {"timestamp": ts, "sumOpenInterest": float(r[oi_idx])} for ts, r in hourly_sorted
    ]
    gls_hist = [
        {"timestamp": ts, "longShortRatio": float(r[gls_idx])} for ts, r in hourly_sorted
    ]
    top_pos_hist = [
        {"timestamp": ts, "longShortRatio": float(r[top_pos_idx])} for ts, r in hourly_sorted
    ]
    top_acc_hist = [
        {"timestamp": ts, "longShortRatio": float(r[top_acc_idx])} for ts, r in hourly_sorted
    ]

    # 4. Downsample 15m (taker) - select max event timestamp in bucket
    taker_selected: dict[int, tuple[int, list[str]]] = {}
    for ts, r in deduped_records:
        bucket = ts // 900_000
        taker_selected[bucket] = (ts, r)

    taker_sorted = [taker_selected[b] for b in sorted(taker_selected.keys())]
    taker_hist = [
        {"timestamp": ts, "buySellRatio": float(r[taker_idx])} for ts, r in taker_sorted
    ]

    return {
        "oi_hist": oi_hist,
        "taker_hist": taker_hist,
        "gls_hist": gls_hist,
        "top_pos_hist": top_pos_hist,
        "top_acc_hist": top_acc_hist,
        "raw_record_count": len(rows),
        "in_scope_record_count": len(parsed_records),
        "deduped_record_count": len(deduped_records),
        "hourly_buckets_count": len(hourly_sorted),
        "taker_buckets_count": len(taker_sorted),
    }


def compute_series_digests(normalized: dict[str, Any]) -> dict[str, str]:
    """Compute sha256 digests of all normalized derivative series."""
    digests: dict[str, str] = {}
    for series_name in ("oi_hist", "taker_hist", "gls_hist", "top_pos_hist", "top_acc_hist"):
        encoded = json.dumps(normalized[series_name], sort_keys=True, separators=(",", ":")).encode()
        digests[series_name] = hashlib.sha256(encoded).hexdigest()
    combined = ":".join(digests[k] for k in sorted(digests.keys()))
    digests["combined"] = hashlib.sha256(combined.encode()).hexdigest()
    return digests


def verify_permutation_invariance(
    rows: list[list[str]],
    header: list[str],
    tf_start: int,
    data_end: int,
    num_permutations: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    """Test and prove permutation invariance across original, reverse, and N permutations."""
    # 1. Original order
    norm_original = normalize_metrics_rows(rows, header, tf_start, data_end)
    digests_original = compute_series_digests(norm_original)

    # 2. Reverse order
    reversed_rows = list(reversed(rows))
    norm_reversed = normalize_metrics_rows(reversed_rows, header, tf_start, data_end)
    digests_reversed = compute_series_digests(norm_reversed)

    assert digests_reversed == digests_original, (
        f"Reversed order digests mismatch: original={digests_original} reversed={digests_reversed}"
    )

    permutations_results: list[dict[str, Any]] = []
    # 3. N deterministic permutations
    for i in range(num_permutations):
        rng = random.Random(seed + i * 1000 + 7)
        permuted_rows = list(rows)
        rng.shuffle(permuted_rows)
        norm_perm = normalize_metrics_rows(permuted_rows, header, tf_start, data_end)
        digests_perm = compute_series_digests(norm_perm)
        assert digests_perm == digests_original, (
            f"Permutation {i + 1} digest mismatch: {digests_perm} vs {digests_original}"
        )
        permutations_results.append(
            {
                "permutation_index": i + 1,
                "seed": seed + i * 1000 + 7,
                "first_three_create_times": [r[0] for r in permuted_rows[:3] if r],
                "digests_match": True,
                "combined_digest": digests_perm["combined"],
            }
        )

    return {
        "permutation_invariance_proven": True,
        "tested_order_count": 2 + num_permutations,
        "original_combined_digest": digests_original["combined"],
        "reversed_combined_digest": digests_reversed["combined"],
        "series_digests": digests_original,
        "permutations": permutations_results,
    }


def verify_fil_20260906_regression(archive_bytes: bytes) -> dict[str, Any]:
    """Verify the known FILUSDT-metrics-2026-09-06.zip archive regression."""
    import zipfile

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        raw_csv = z.read(csv_name).decode("utf-8-sig")

    rows = list(csv.reader(io.StringIO(raw_csv)))
    header = rows[0]
    metric_rows = [r for r in rows[1:] if r and r[0].lower() != "create_time"]

    # Locate 17h UTC bucket rows
    rows_17h = [r for r in metric_rows if "2026-09-06 17:" in r[0]]
    archive_order_last_17h = rows_17h[-1] if rows_17h else None

    # Full day range
    tf_start = int(datetime(2026, 9, 6, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    data_end = int(datetime(2026, 9, 6, 23, 59, 59, tzinfo=UTC).timestamp() * 1000)

    normalized = normalize_metrics_rows(metric_rows, header, tf_start, data_end)

    # Find the 17h observation in oi_hist
    target_17h_start = int(datetime(2026, 9, 6, 17, 0, 0, tzinfo=UTC).timestamp() * 1000)
    target_17h_end = int(datetime(2026, 9, 6, 17, 59, 59, tzinfo=UTC).timestamp() * 1000)
    selected_17h = next(
        (x for x in normalized["oi_hist"] if target_17h_start <= x["timestamp"] <= target_17h_end),
        None,
    )

    assert selected_17h is not None, "Missing 17h bucket in normalized oi_hist"
    selected_dt = datetime.fromtimestamp(selected_17h["timestamp"] / 1000, UTC).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Must be 17:55:00, NOT 17:35:00
    expected_event_time = "2026-09-06 17:55:00"
    flawed_archive_time = archive_order_last_17h[0] if archive_order_last_17h else "UNKNOWN"

    assert selected_dt == expected_event_time, (
        f"FIL regression failed: selected {selected_dt}, expected {expected_event_time}"
    )
    assert flawed_archive_time == "2026-09-06 17:35:00", (
        f"Archive order last row expected 17:35:00, got {flawed_archive_time}"
    )

    return {
        "regression_verified": True,
        "archive_order_tail_observation": flawed_archive_time,
        "normalized_selected_observation": selected_dt,
        "expected_selected_observation": expected_event_time,
        "archive_flaw_discrepancy_minutes": 20,
        "selected_timestamp_ms": selected_17h["timestamp"],
        "selected_sum_open_interest": selected_17h["sumOpenInterest"],
    }


@dataclass(frozen=True)
class CacheIdentity:
    schema_version: str
    parser_schema_version: str
    time_window: dict[str, int]
    symbol_roles: dict[str, list[str]]
    harness_code_hashes: dict[str, str]
    source_archives_count: int
    source_archives_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheIdentity:
        return cls(
            schema_version=data["schema_version"],
            parser_schema_version=data["parser_schema_version"],
            time_window=dict(data["time_window"]),
            symbol_roles={k: list(v) for k, v in data["symbol_roles"].items()},
            harness_code_hashes=dict(data["harness_code_hashes"]),
            source_archives_count=int(data["source_archives_count"]),
            source_archives_digest=str(data["source_archives_digest"]),
        )


def compute_cache_identity(
    time_window: dict[str, int],
    symbol_roles: dict[str, list[str]],
    source_archives: list[dict[str, str]],
    script_paths: list[Path],
) -> CacheIdentity:
    """Compute identity object bound to schemas, time window, roles, scripts, and source archives."""
    code_hashes: dict[str, str] = {}
    for p in sorted(script_paths):
        code_hashes[str(p.name)] = hashlib.sha256(p.read_bytes()).hexdigest()

    sorted_archives = sorted(source_archives, key=lambda x: x["url"])
    archives_repr = json.dumps(sorted_archives, sort_keys=True, separators=(",", ":")).encode()
    archives_digest = hashlib.sha256(archives_repr).hexdigest()

    return CacheIdentity(
        schema_version=CACHE_SCHEMA_VERSION,
        parser_schema_version=PARSER_SCHEMA_VERSION,
        time_window=time_window,
        symbol_roles={k: sorted(v) for k, v in symbol_roles.items()},
        harness_code_hashes=code_hashes,
        source_archives_count=len(sorted_archives),
        source_archives_digest=archives_digest,
    )


def _identity_path_for(cache_path: Path) -> Path:
    # If cache_path is /tmp/foo.json.gz, identity_path is /tmp/foo.identity.json
    name = cache_path.name
    for ext in (".gz", ".json"):
        name = name.removesuffix(ext)
    return cache_path.with_name(name + ".identity.json")


def save_authorized_cache(
    cache_path: Path,
    identity: CacheIdentity,
    raw_data: dict[str, Any],
) -> None:
    """Save raw data wrapped with identity header and companion identity file."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path = _identity_path_for(cache_path)
    identity_dict = identity.to_dict()
    identity_path.write_text(json.dumps(identity_dict, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    payload = {
        "identity": identity_dict,
        "payload": raw_data,
    }
    with gzip.open(cache_path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))


def validate_and_load_cache(
    cache_path: Path,
    expected_identity: CacheIdentity,
    on_mismatch: str = "fail_closed",
    *,
    load_payload: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Validate cache identity and load if matching.

    on_mismatch: 'fail_closed' raises CacheAuthorityError; 'rebuild' returns (None, audit).
    load_payload: If False, validates identity without loading large dataset into memory.
    """
    identity_path = _identity_path_for(cache_path)
    audit: dict[str, Any] = {
        "cache_path": str(cache_path),
        "cache_exists": cache_path.exists(),
        "identity_file_exists": identity_path.exists(),
        "reusable": False,
        "mismatch_reasons": [],
    }
    if not cache_path.exists():
        audit["mismatch_reasons"].append("CACHE_NOT_FOUND")
        if on_mismatch == "fail_closed":
            raise CacheAuthorityError("Cache does not exist")
        return None, audit

    cached_identity: dict[str, Any] | None = None
    if identity_path.exists():
        try:
            cached_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached_identity = None

    if cached_identity is None:
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as f:
                wrapped = json.load(f)
            if isinstance(wrapped, dict) and "identity" in wrapped:
                cached_identity = wrapped["identity"]
        except Exception as exc:
            audit["mismatch_reasons"].append(f"CACHE_CORRUPTED: {exc}")
            if on_mismatch == "fail_closed":
                raise CacheAuthorityError(f"Cache corrupted: {exc}") from exc
            return None, audit

    if not isinstance(cached_identity, dict):
        audit["mismatch_reasons"].append("ANONYMOUS_UNWRAPPED_CACHE")
        if on_mismatch == "fail_closed":
            raise CacheAuthorityError("Anonymous unwrapped cache rejected")
        return None, audit

    expected_dict = expected_identity.to_dict()
    mismatches: list[str] = []
    if cached_identity.get("schema_version") != expected_dict["schema_version"]:
        mismatches.append(
            f"SCHEMA_VERSION: cached={cached_identity.get('schema_version')} expected={expected_dict['schema_version']}"
        )
    if cached_identity.get("parser_schema_version") != expected_dict["parser_schema_version"]:
        mismatches.append(
            f"PARSER_SCHEMA_VERSION: cached={cached_identity.get('parser_schema_version')} expected={expected_dict['parser_schema_version']}"
        )
    if cached_identity.get("source_archives_digest") != expected_dict["source_archives_digest"]:
        mismatches.append(
            f"SOURCE_ARCHIVES_DIGEST: cached={cached_identity.get('source_archives_digest')} expected={expected_dict['source_archives_digest']}"
        )
    if cached_identity.get("harness_code_hashes") != expected_dict["harness_code_hashes"]:
        mismatches.append(
            f"HARNESS_CODE_HASHES: cached={cached_identity.get('harness_code_hashes')} expected={expected_dict['harness_code_hashes']}"
        )
    if cached_identity.get("symbol_roles") != expected_dict["symbol_roles"]:
        mismatches.append(
            f"SYMBOL_ROLES: cached={cached_identity.get('symbol_roles')} expected={expected_dict['symbol_roles']}"
        )
    if cached_identity.get("time_window") != expected_dict["time_window"]:
        mismatches.append(
            f"TIME_WINDOW: cached={cached_identity.get('time_window')} expected={expected_dict['time_window']}"
        )

    if mismatches:
        audit["mismatch_reasons"] = mismatches
        if on_mismatch == "fail_closed":
            raise CacheAuthorityError(f"Cache identity mismatch: {'; '.join(mismatches)}")
        return None, audit

    audit["reusable"] = True
    audit["matched_identity"] = cached_identity

    if not load_payload:
        return None, audit

    try:
        with gzip.open(cache_path, "rt", encoding="utf-8") as f:
            wrapped = json.load(f)
        payload = wrapped.get("payload") if isinstance(wrapped, dict) else None
        return payload, audit
    except Exception as exc:
        audit["mismatch_reasons"].append(f"PAYLOAD_READ_FAILED: {exc}")
        audit["reusable"] = False
        if on_mismatch == "fail_closed":
            raise CacheAuthorityError(f"Payload read failed: {exc}") from exc
        return None, audit


@dataclass(frozen=True)
class ExecutionIdentity:
    task_id: str
    expected_branch: str
    observed_branch: str
    git_head: str
    src_clean: bool
    script_hashes: dict[str, str]
    timestamp_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_execution_identity(
    task_id: str,
    root: Path,
    expected_branch: str,
    script_paths: list[Path],
) -> ExecutionIdentity:
    """Capture pre-execution environment identity."""
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    src_diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "src/"], cwd=root, check=False
    ).returncode
    src_clean = src_diff == 0

    hashes: dict[str, str] = {}
    for p in sorted(script_paths):
        key = str(p.relative_to(root)) if p.is_relative_to(root) else str(p.name)
        hashes[key] = hashlib.sha256(p.read_bytes()).hexdigest()

    return ExecutionIdentity(
        task_id=task_id,
        expected_branch=expected_branch,
        observed_branch=branch,
        git_head=head,
        src_clean=src_clean,
        script_hashes=hashes,
        timestamp_utc=datetime.now(UTC).isoformat(),
    )


def verify_execution_identity(
    pre_identity: ExecutionIdentity,
    root: Path,
    script_paths: list[Path],
) -> dict[str, Any]:
    """Verify post-execution exact match against pre-execution identity.

    Fails closed if branch, HEAD, clean status, or any script hash changed.
    """
    post_identity = capture_execution_identity(
        pre_identity.task_id,
        root,
        pre_identity.expected_branch,
        script_paths,
    )

    mismatches: list[str] = []
    if post_identity.observed_branch != pre_identity.expected_branch:
        mismatches.append(
            f"BRANCH_MISMATCH: observed={post_identity.observed_branch} expected={pre_identity.expected_branch}"
        )
    if post_identity.git_head != pre_identity.git_head:
        mismatches.append(
            f"GIT_HEAD_MISMATCH: pre={pre_identity.git_head} post={post_identity.git_head}"
        )
    if not post_identity.src_clean:
        mismatches.append("SRC_TREE_NOT_CLEAN")
    if post_identity.script_hashes != pre_identity.script_hashes:
        mismatches.append(
            f"SCRIPT_HASHES_MISMATCH: pre={pre_identity.script_hashes} post={post_identity.script_hashes}"
        )

    if mismatches:
        raise RunnerIdentityMismatchError(
            f"Post-execution identity assertion failed: {'; '.join(mismatches)}"
        )

    return {
        "exact_runner_identity_verified": True,
        "branch": post_identity.observed_branch,
        "git_head": post_identity.git_head,
        "src_clean": post_identity.src_clean,
        "script_hashes": post_identity.script_hashes,
        "pre_timestamp_utc": pre_identity.timestamp_utc,
        "post_timestamp_utc": post_identity.timestamp_utc,
    }
