# ruff: noqa: E402
# Source/bootstrap path is established before optional installed Quant imports.
"""Fail-closed WSL bundle verifier + unmodified S1/actionability/Program-C handoff engine."""

from __future__ import annotations

import argparse
from contextlib import closing
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any, Callable

_POC_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _POC_ROOT.parent
_PROGRAM_O_SRC = _REPO_ROOT / "lt-program-o-clock-remediation-01" / "src"

for _p in (str(_POC_ROOT), str(_PROGRAM_O_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from win_capture.bundle import canonical_bytes, canonical_digest
from win_capture.capture import (
    INTERVALS,
    SYMBOLS,
    metadata,
    parse_klines,
    project_qpc,
    reference,
    verify_observation,
)
from win_capture.transport import ALLOWED_HOST, ALLOWED_ROUTES, RESPONSE_BYTES_MAX, strict_json
from win_capture.win_clock import WindowsClockError, check_windows_pair_coherence

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.live.models import Receipt
from btc_quant_agent.platform.live.swing_review import actionability
from btc_quant_agent.platform.qualification.source import causal
from btc_quant_agent.platform.rc_models import STRATEGY_VERSION, frozen_contract
from btc_quant_agent.platform.rc_strategy import compile_s1
from btc_quant_agent.platform.swing import SwingPolicy
from program_c.integrity import digest as c_digest
from program_c.protocol import load_protocol
from program_c.validation import C_SCHEMA, validate as c_validate

BUNDLE_SCHEMA = "WIN_CAPTURE_HANDOFF_BUNDLE_V1"
HANDOFF_SCHEMA = "WSL_WINDOWS_BUNDLE_S1_HANDOFF_V1"
HANDOFF_PRODUCT = "WIN_WSL_FALLBACK_S1_V1"
ALLOWED_EVIDENCE_CLASSES = frozenset({"WIN_CAPTURE_PUBLIC_OPERATIONAL_V1", "WIN_CAPTURE_LOOPBACK_QA_V1"})


class HandoffError(ValueError):
    """Fail-closed verification / handoff error."""

    def __init__(self, message: str, status: str = "WSL_HANDOFF_REJECTED"):
        super().__init__(message)
        self.status = status


def _require(cond: bool, msg: str, status: str = "WSL_HANDOFF_REJECTED") -> None:
    if not cond:
        raise HandoffError(msg, status=status)


def _ensure_safe_dir_or_file(path: Path) -> Path:
    _require(".." not in path.parts, f"WSL_PARENT_TRAVERSAL_FORBIDDEN:{path}")
    resolved = path.absolute()
    for p in (resolved, *resolved.parents):
        if p.exists() and p.is_symlink():
            raise HandoffError(f"WSL_SYMLINK_FORBIDDEN:{p}")
    return resolved


def _ensure_safe_child(root: Path, rel: str) -> Path:
    _require(
        isinstance(rel, str) and bool(rel) and not rel.startswith("/") and "\\" not in rel,
        "WSL_INVALID_RELPATH",
    )
    rel_path = Path(rel)
    _require(".." not in rel_path.parts and not rel_path.is_absolute(), "WSL_RELPATH_TRAVERSAL_FORBIDDEN")
    candidate = root / rel_path
    _ensure_safe_dir_or_file(candidate)
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    _require(resolved_candidate.is_relative_to(resolved_root), "WSL_PATH_ESCAPE_FORBIDDEN")
    return candidate


def _write_atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_safe_dir_or_file(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=".part", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class _Timex(ctypes.Structure):
    _fields_ = [
        ("modes", ctypes.c_uint),
        ("offset", ctypes.c_long),
        ("freq", ctypes.c_long),
        ("maxerror", ctypes.c_long),
        ("esterror", ctypes.c_long),
        ("status", ctypes.c_int),
        ("constant", ctypes.c_long),
        ("precision", ctypes.c_long),
        ("tolerance", ctypes.c_long),
        ("time_sec", ctypes.c_long),
        ("time_usec", ctypes.c_long),
        ("tick", ctypes.c_long),
        ("ppsfreq", ctypes.c_long),
        ("jitter", ctypes.c_long),
        ("shift", ctypes.c_int),
        ("stabil", ctypes.c_long),
        ("jitcnt", ctypes.c_long),
        ("calcnt", ctypes.c_long),
        ("errcnt", ctypes.c_long),
        ("stbcnt", ctypes.c_long),
        ("tai", ctypes.c_int),
        ("_pad", ctypes.c_long * 11),
    ]


def probe_wsl_clock_readonly() -> dict[str, Any]:
    """Read-only WSL kernel timekeeping telemetry. NEVER used as capture/decision clock."""
    out: dict[str, Any] = {
        "authoritative_for_s1": False,
        "platform": sys.platform,
    }
    boot_path = Path("/proc/sys/kernel/random/boot_id")
    if boot_path.is_file():
        out["boot_id"] = boot_path.read_text(encoding="utf-8").strip()
    if hasattr(time, "CLOCK_MONOTONIC_RAW") and hasattr(time, "CLOCK_BOOTTIME"):
        mono_a = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        raw = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
        boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        rt = time.clock_gettime_ns(time.CLOCK_REALTIME)
        mono_b = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        mono_mid = (mono_a + mono_b) / 2.0
        out["clocks_ns"] = {
            "monotonic_before": mono_a,
            "monotonic_raw": raw,
            "boottime": boot,
            "realtime": rt,
            "monotonic_after": mono_b,
        }
        out["mono_minus_raw_ms"] = (mono_mid - raw) / 1_000_000.0
        out["wall_minus_mono_ms"] = (rt - mono_mid) / 1_000_000.0
    if sys.platform.startswith("linux"):
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            tx = _Timex()
            tx.modes = 0  # Read-only query
            rc = libc.adjtimex(ctypes.byref(tx))
            freq_ppm = tx.freq / 65536.0
            tick_ppm = (tx.tick - 10000) * 100.0
            out["adjtimex"] = {
                "rc": rc,
                "tick": tx.tick,
                "freq": tx.freq,
                "freq_ppm": freq_ppm,
                "tick_offset_ppm": tick_ppm,
                "total_slew_ppm": tick_ppm + freq_ppm,
                "offset": tx.offset,
                "status": tx.status,
            }
            out["defect_isolated"] = (tx.tick != 10000) or (abs(freq_ppm) > 500.0)
        except OSError as exc:
            out["adjtimex_error"] = str(exc)
            out["defect_isolated"] = True
    return out


class HandoffLedger:
    """Append-only hash-chained SQLite store for WSL S1 handoff decisions."""

    def __init__(self, directory: Path):
        self.directory = _ensure_safe_dir_or_file(directory)
        _require(not self.directory.exists(), "WSL_HANDOFF_OUTPUT_DIR_MUST_BE_UNUSED")
        self.directory.mkdir(parents=False, exist_ok=False)
        self.db_path = self.directory / "handoff_ledger.sqlite"
        with closing(self._connect()) as db:
            with db:
                db.execute(
                    """
                    CREATE TABLE events (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        prev_sha256 TEXT NOT NULL,
                        entry_sha256 TEXT NOT NULL
                    )
                    """
                )
        self.head_sha256 = "0" * 64
        self.append_event("HANDOFF_INIT", {"schema": HANDOFF_SCHEMA})

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def append_event(self, kind: str, payload: dict[str, Any]) -> str:
        payload_text = canonical_bytes(payload).decode("utf-8")
        entry_sha256 = canonical_digest({"kind": kind, "payload": payload, "prev_sha256": self.head_sha256})
        with closing(self._connect()) as db:
            with db:
                db.execute(
                    "INSERT INTO events(kind, payload_json, prev_sha256, entry_sha256) VALUES(?,?,?,?)",
                    (kind, payload_text, self.head_sha256, entry_sha256),
                )
        self.head_sha256 = entry_sha256
        return entry_sha256


def _verify_sqlite_ledger(
    ledger_path: Path, manifest: dict[str, Any]
) -> list[tuple[int, str, dict[str, Any]]]:
    _require(ledger_path.is_file(), "WSL_BUNDLE_LEDGER_MISSING")
    actual_sqlite_sha = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    _require(actual_sqlite_sha == manifest["ledger_sqlite_sha256"], "WSL_BUNDLE_LEDGER_FILE_SHA256_MISMATCH")

    events_out: list[tuple[int, str, dict[str, Any]]] = []
    with closing(sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        _require(integrity is not None and integrity[0] == "ok", "WSL_BUNDLE_SQLITE_INTEGRITY_FAILED")
        rows = db.execute(
            "SELECT seq, kind, payload_json, prev_sha256, entry_sha256 FROM events ORDER BY seq ASC"
        ).fetchall()

    _require(len(rows) >= 3, "WSL_BUNDLE_LEDGER_TOO_SHORT")
    expected_prev = "0" * 64
    for expected_seq, (seq, kind, payload_json, prev_sha, entry_sha) in enumerate(rows, start=1):
        _require(seq == expected_seq, "WSL_BUNDLE_LEDGER_SEQ_GAP")
        _require(prev_sha == expected_prev, "WSL_BUNDLE_LEDGER_PREV_HASH_BROKEN")
        payload = strict_json(payload_json.encode("utf-8"))
        computed = canonical_digest({"kind": kind, "payload": payload, "prev_sha256": prev_sha})
        _require(computed == entry_sha, "WSL_BUNDLE_LEDGER_ENTRY_HASH_MISMATCH")
        expected_prev = entry_sha
        events_out.append((seq, kind, payload))

    _require(expected_prev == manifest["ledger_head_sha256"], "WSL_BUNDLE_LEDGER_HEAD_MISMATCH")
    _require(
        not any(k == "SESSION_FAILED" for _, k, _ in events_out), "WSL_BUNDLE_SESSION_FAILED_NOT_ADMISSIBLE"
    )
    sealed = [p for _, k, p in events_out if k == "BUNDLE_SEALED"]
    _require(len(sealed) == 1 and events_out[-1][1] == "BUNDLE_SEALED", "WSL_BUNDLE_SEAL_EVENT_MISSING")
    s_payload = sealed[0]
    _require(
        s_payload.get("session") == manifest["session"]
        and s_payload.get("manifest_body_sha256") == manifest["manifest_body_sha256"]
        and s_payload.get("records_sha256") == canonical_digest(manifest["records"])
        and s_payload.get("responses_sha256") == canonical_digest(manifest["responses"]),
        "WSL_BUNDLE_SEAL_PAYLOAD_MISMATCH",
    )
    ledger_responses = [p for _, k, p in events_out if k == "HTTP_RESPONSE"]
    _require(ledger_responses == manifest["responses"], "WSL_BUNDLE_LEDGER_RESPONSES_MISMATCH")
    return events_out


def verify_and_load_bundle(
    bundle_dir: Path,
    *,
    exclusions: list[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    """Read-only verification of Windows bundle integrity, Windows dual-clock proof, and raw-to-bar lineage."""
    bundle_root = _ensure_safe_dir_or_file(Path(bundle_dir))
    _require(bundle_root.is_dir(), "WSL_BUNDLE_DIR_NOT_FOUND")

    manifest_path = _ensure_safe_child(bundle_root, "bundle_manifest.json")
    _require(manifest_path.is_file(), "WSL_BUNDLE_MANIFEST_MISSING")
    try:
        manifest = strict_json(manifest_path.read_bytes())
    except Exception as exc:
        raise HandoffError(f"WSL_BUNDLE_MANIFEST_INVALID_JSON:{exc}") from exc

    _require(isinstance(manifest, dict), "WSL_BUNDLE_MANIFEST_NOT_OBJECT")
    _require(manifest.get("schema") == BUNDLE_SCHEMA, "WSL_BUNDLE_SCHEMA_MISMATCH")
    _require(manifest.get("evidence_class") in ALLOWED_EVIDENCE_CLASSES, "WSL_BUNDLE_EVIDENCE_CLASS_INVALID")
    _require(
        manifest.get("strict_utc_qualified") is False
        and manifest.get("source_qualified") is False
        and manifest.get("economically_validated") is False
        and manifest.get("account") == "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        "WSL_BUNDLE_AUTHORITY_BOUNDARY_VIOLATED",
    )

    body_keys = [
        "schema",
        "session",
        "evidence_class",
        "strict_utc_qualified",
        "source_qualified",
        "economically_validated",
        "account",
        "grace_ms",
        "window_minutes",
        "reference_max_age_ms",
        "quote_max_age_ms",
        "requests",
        "request_weight",
        "response_bytes",
        "metadata_response_sha256",
        "instruments",
        "reference",
        "source_bounds",
        "review_bounds",
        "incomplete_rows_excluded",
        "records",
        "swing_market",
        "clock_guard",
        "responses",
    ]
    _require(
        all(
            k in manifest
            for k in (
                *body_keys,
                "manifest_body_sha256",
                "ledger_head_sha256",
                "ledger_sqlite_sha256",
                "bundle_sha256",
            )
        ),
        "WSL_BUNDLE_MISSING_FIELDS",
    )
    body = {k: manifest[k] for k in body_keys}
    _require(canonical_digest(body) == manifest["manifest_body_sha256"], "WSL_BUNDLE_BODY_SHA256_MISMATCH")
    without_bundle_hash = {k: v for k, v in manifest.items() if k != "bundle_sha256"}
    _require(canonical_digest(without_bundle_hash) == manifest["bundle_sha256"], "WSL_BUNDLE_SHA256_MISMATCH")

    # 1. Verify append-only hash-chained SQLite ledger
    ledger_path = _ensure_safe_child(bundle_root, "ledger.sqlite")
    _verify_sqlite_ledger(ledger_path, manifest)

    # 2. Verify Windows QPC vs UnbiasedInterruptTimePrecise coherence across ALL samples
    guard = manifest["clock_guard"]
    _require(
        guard.get("anchor_clock") == "WINDOWS_QPC_AND_UNBIASED_COHERENT", "WSL_WINDOWS_CLOCK_ANCHOR_INVALID"
    )
    max_span_ms = int(guard["max_span_ms"])
    max_divergence_ms = int(guard["max_divergence_ms"])
    _require(
        1 <= max_span_ms <= 5 and 1 <= max_divergence_ms <= 50, "WSL_WINDOWS_CLOCK_THRESHOLDS_OUT_OF_POLICY"
    )

    ordered_samples = [guard["first_sample"]]
    for resp in manifest["responses"]:
        ordered_samples.extend((resp["request_sample"], resp["receive_sample"], resp["durable_sample"]))
    ordered_samples.append(guard["last_sample"])
    anchor = ordered_samples[0]
    try:
        check_windows_pair_coherence(
            anchor, anchor, max_span_ms=max_span_ms, max_divergence_ms=max_divergence_ms
        )
        prev = anchor
        for cur in ordered_samples[1:]:
            check_windows_pair_coherence(
                prev, cur, max_span_ms=max_span_ms, max_divergence_ms=max_divergence_ms
            )
            check_windows_pair_coherence(
                anchor, cur, max_span_ms=max_span_ms, max_divergence_ms=max_divergence_ms
            )
            prev = cur
    except WindowsClockError as exc:
        raise HandoffError(
            f"WSL_BUNDLE_WINDOWS_CLOCK_FAILED:{exc}", status="WIN_CLOCK_DEGRADED_BLOCKED"
        ) from exc

    # 3. Verify every raw response .bin file, TLS provenance, and decode payload
    responses = manifest["responses"]
    _require(len(responses) == manifest["requests"] <= 24, "WSL_BUNDLE_REQUEST_COUNT_MISMATCH")
    decoded_by_ordinal: dict[int, tuple[Any, dict[str, Any]]] = {}
    total_bytes = 0
    for idx, wire in enumerate(responses, start=1):
        _require(
            wire.get("ordinal") == idx and wire.get("session") == manifest["session"],
            "WSL_BUNDLE_RESPONSE_ORDINAL_MISMATCH",
        )
        _require(
            wire.get("status") == 200 and wire.get("response_complete") is True,
            "WSL_BUNDLE_RESPONSE_STATUS_OR_COMPLETE",
        )
        _require(
            wire.get("route") in ALLOWED_ROUTES and wire.get("host") == ALLOWED_HOST,
            "WSL_BUNDLE_ROUTE_OR_HOST_INVALID",
        )
        tls = wire.get("tls", {})
        _require(
            tls.get("chain") == "CERT_REQUIRED"
            and tls.get("hostname_verified") is True
            and tls.get("sni") == ALLOWED_HOST,
            "WSL_BUNDLE_TLS_PROVENANCE_INVALID",
        )
        raw_path = _ensure_safe_child(bundle_root, wire["raw_path"])
        _require(raw_path.is_file(), "WSL_BUNDLE_RAW_FILE_MISSING")
        raw_bytes = raw_path.read_bytes()
        _require(len(raw_bytes) == wire["byte_len"] <= RESPONSE_BYTES_MAX, "WSL_BUNDLE_RAW_LEN_MISMATCH")
        _require(
            hashlib.sha256(raw_bytes).hexdigest() == wire["body_sha256"], "WSL_BUNDLE_RAW_SHA256_MISMATCH"
        )
        total_bytes += len(raw_bytes)
        decoded_by_ordinal[idx] = (strict_json(raw_bytes), wire)
    _require(total_bytes == manifest["response_bytes"], "WSL_BUNDLE_TOTAL_BYTES_MISMATCH")

    # 4. Re-derive instruments, historical time reference, completed bars, and current observations
    meta_candidates = [
        pair for pair in decoded_by_ordinal.values() if pair[1]["route"] == "/fapi/v1/exchangeInfo"
    ]
    _require(
        len(meta_candidates) == 1
        and meta_candidates[0][1]["body_sha256"] == manifest["metadata_response_sha256"],
        "WSL_BUNDLE_METADATA_PROBES_MISMATCH",
    )
    rebuilt_instruments = metadata(meta_candidates[0][0])
    _require(rebuilt_instruments == manifest["instruments"], "WSL_BUNDLE_INSTRUMENTS_LINEAGE_MISMATCH")

    by_hash = {pair[1]["body_sha256"]: pair for pair in decoded_by_ordinal.values()}
    by_session_ordinal = {
        (pair[1]["session"], pair[1]["ordinal"]): pair for pair in decoded_by_ordinal.values()
    }

    hist_time_hashes = manifest["reference"]["time_response_sha256"]
    _require(
        len(hist_time_hashes) == 2 and all(h in by_hash for h in hist_time_hashes),
        "WSL_BUNDLE_HIST_TIME_PROBES_MISSING",
    )
    hist_first, hist_last = by_hash[hist_time_hashes[0]], by_hash[hist_time_hashes[1]]
    _require(
        hist_first[1]["route"] == "/fapi/v1/time" and hist_last[1]["route"] == "/fapi/v1/time",
        "WSL_BUNDLE_HIST_TIME_ROUTE_INVALID",
    )
    rebuilt_hist_ref = reference(hist_first, hist_last)
    _require(rebuilt_hist_ref == manifest["reference"], "WSL_BUNDLE_HIST_REFERENCE_LINEAGE_MISMATCH")

    lower_approx = (
        hist_first[0]["serverTime"]
        - (hist_first[1]["receive_sample"]["qpc_after_ms"] - hist_first[1]["request_sample"]["qpc_before_ms"])
        - 1
    )
    grace_ms = int(manifest["grace_ms"])
    window_minutes = int(manifest["window_minutes"])
    _require(
        120_000 <= grace_ms <= 300_000 and 5 <= window_minutes <= 120, "WSL_BUNDLE_POLICY_BOUNDS_INVALID"
    )

    excl = list(exclusions or [])
    rebuilt_records: list[dict[str, Any]] = []
    rebuilt_incomplete = 0
    hist_kline_wires = [
        decoded_by_ordinal[o]
        for o in sorted(decoded_by_ordinal)
        if hist_first[1]["ordinal"] < o < hist_last[1]["ordinal"]
        and decoded_by_ordinal[o][1]["route"] == "/fapi/v1/klines"
    ]
    _require(len(hist_kline_wires) == len(SYMBOLS) * 2, "WSL_BUNDLE_HIST_KLINE_COUNT_MISMATCH")
    seen_pairs: set[tuple[str, str]] = set()
    for body_val, wire in hist_kline_wires:
        params = wire["params"]
        symbol = params["symbol"]
        interval = {"1d": "1D", "4h": "4H"}[params["interval"]]
        _require((symbol, interval) not in seen_pairs, "WSL_BUNDLE_DUPLICATE_HIST_BATCH")
        seen_pairs.add((symbol, interval))
        start = int(params["startTime"])
        end = int(params["endTime"]) + 1
        _require(not any(start < hi and end > lo for lo, hi in excl), "WSL_HOLDOUT_DATE_OVERLAP_FORBIDDEN")
        rows, excluded_count = parse_klines(
            body_val,
            symbol,
            interval,
            start=start,
            end=end,
            source_lower=lower_approx,
            grace_ms=grace_ms,
            wire=wire,
            ref=rebuilt_hist_ref,
            evidence_class=manifest["evidence_class"],
        )
        rebuilt_records.extend(rows)
        rebuilt_incomplete += excluded_count
    _require(
        rebuilt_records == manifest["records"] and rebuilt_incomplete == manifest["incomplete_rows_excluded"],
        "WSL_BUNDLE_RECORDS_RAW_LINEAGE_MISMATCH",
    )

    sm = manifest["swing_market"]
    _require(len(sm["time_responses"]) == 2, "WSL_BUNDLE_QUOTE_TIME_PROBES_INVALID")
    q_first = by_session_ordinal[tuple(sm["time_responses"][0])]
    q_last = by_session_ordinal[tuple(sm["time_responses"][1])]
    _require(
        q_first[1]["route"] == "/fapi/v1/time" and q_last[1]["route"] == "/fapi/v1/time",
        "WSL_BUNDLE_QUOTE_TIME_ROUTE_INVALID",
    )
    rebuilt_q_ref = reference(q_first, q_last)
    _require(rebuilt_q_ref == sm["reference"], "WSL_BUNDLE_QUOTE_REFERENCE_LINEAGE_MISMATCH")

    trigger = int(sm["trigger_ms"])
    _require(
        not any(trigger < hi and trigger + INTERVALS["4H"] > lo for lo, hi in excl),
        "WSL_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
    )
    rebuilt_observations: dict[str, dict[str, Any]] = {}
    for recorded in sm["observations"]:
        qb, qw = by_session_ordinal[tuple(recorded["wire_ref"])]
        _require(
            qw["route"] == "/fapi/v1/klines"
            and q_first[1]["durable_sample"]["qpc_after_ms"] <= qw["request_sample"]["qpc_before_ms"]
            and qw["durable_sample"]["qpc_after_ms"] <= q_last[1]["request_sample"]["qpc_before_ms"],
            "WSL_BUNDLE_OBSERVATION_NOT_BRACKETED",
        )
        rebuilt_obs = verify_observation(qb, qw, rebuilt_q_ref, trigger, recorded["symbol"])
        _require(
            rebuilt_obs == recorded and recorded["symbol"] not in rebuilt_observations,
            "WSL_BUNDLE_OBSERVATION_LINEAGE_MISMATCH",
        )
        rebuilt_observations[recorded["symbol"]] = rebuilt_obs
    _require(set(rebuilt_observations) == set(SYMBOLS), "WSL_BUNDLE_MISSING_SYMBOL_OBSERVATION")

    last_sample = guard["last_sample"]
    source_bounds = list(project_qpc(rebuilt_hist_ref, last_sample, int(manifest["reference_max_age_ms"])))
    quote_bounds = list(project_qpc(rebuilt_q_ref, last_sample, int(manifest["quote_max_age_ms"])))
    _require(
        source_bounds == manifest["source_bounds"] and quote_bounds == sm["quote_bounds"],
        "WSL_BUNDLE_BOUNDS_PROJECTION_MISMATCH",
    )

    review_lo = max(source_bounds[0], quote_bounds[0])
    review_hi = min(source_bounds[1], quote_bounds[1])
    _require(
        review_lo <= review_hi and [review_lo, review_hi] == manifest["review_bounds"],
        "WSL_BUNDLE_REVIEW_BOUNDS_INVALID",
    )
    _require(
        review_lo // INTERVALS["4H"] * INTERVALS["4H"] == trigger
        and review_hi // INTERVALS["4H"] * INTERVALS["4H"] == trigger,
        "WSL_BUNDLE_CYCLE_BOUNDARY_UNCERTAIN",
    )
    _require(
        trigger + max(120_000, grace_ms) <= review_lo <= review_hi <= trigger + window_minutes * 60_000,
        "WSL_BUNDLE_OUTSIDE_MANUAL_REVIEW_WINDOW",
    )
    for obs in rebuilt_observations.values():
        _require(
            obs["available_bounds_ms"][1] <= review_lo
            and 0 <= review_hi - obs["available_bounds_ms"][0] <= int(manifest["quote_max_age_ms"]),
            "WSL_BUNDLE_QUOTE_STALE_OR_NOT_CAUSAL",
        )

    return {
        "bundle_dir": str(bundle_root),
        "manifest": manifest,
        "receipts": [Receipt(r) for r in rebuilt_records],
        "observations": rebuilt_observations,
        "trigger_ms": trigger,
        "review_bounds": [review_lo, review_hi],
        "window_minutes": window_minutes,
    }


def compile_s1_from_verified(
    verified: dict[str, Any],
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    holding_hours: int = 24,
) -> dict[str, dict[str, Any]]:
    """Run unmodified rc_strategy.compile_s1 + swing_review.actionability purely on Windows-anchored UTC bounds."""
    _require(type(holding_hours) is int and 4 <= holding_hours <= 48, "WSL_HOLDING_HOURS_OUT_OF_RANGE")
    manifest = verified["manifest"]
    receipts = verified["receipts"]
    trigger = verified["trigger_ms"]
    review_lo, review_hi = verified["review_bounds"]
    observations = verified["observations"]
    window_minutes = verified["window_minutes"]

    bar_policy = SimpleNamespace(
        max_availability_delay_ms=window_minutes * 60_000,
        minimum_history_bars=60,
        next_review=SwingPolicy().next_review,
    )
    decisions: dict[str, dict[str, Any]] = {}
    costs_bps = frozen_contract()["strategy"]["costs_bps"]

    for symbol in symbols:
        _require(symbol in SYMBOLS, f"WSL_SYMBOL_OUT_OF_SCOPE:{symbol}")
        obs = observations[symbol]

        def decision_factory(**kw: Any) -> dict[str, Any]:
            state = kw["market_state"]
            reasons = list(kw["reasons"])
            diagnostics = dict(kw["diagnostics"])
            diagnostics.update(
                {
                    "hypothetical_costs_bps": costs_bps,
                    "windows_clock_anchor": manifest["clock_guard"]["anchor_clock"],
                    "actual_review_delay_ms": review_lo - trigger,
                    "signal_issued_at_close": False,
                    "review_window_minutes": window_minutes,
                }
            )
            opp = kw.get("opportunity")
            episode_id = kw.get("episode_id")
            eligible_r = list(kw.get("eligible_planned_r", ()))
            if opp is not None:
                _require(
                    opp.setup_close_ms == trigger
                    and opp.symbol == symbol
                    and opp.account_status == "UNKNOWN"
                    and opp.available_ms <= review_lo < kw["scheduled_review_ms"] < opp.expires_ms
                    and opp.planned_after_cost_r >= 2,
                    "WSL_S1_CAUSAL_GEOMETRY_INVALID",
                )
                expected_ep = fingerprint(
                    [HANDOFF_PRODUCT, STRATEGY_VERSION, symbol, trigger, kw["prefix_sha256"]]
                )
                _require(episode_id == expected_ep, "WSL_S1_EPISODE_ID_MISMATCH")
                gate_reason = actionability(opp, obs, review_hi)
                if gate_reason:
                    state = "NO_SETUP"
                    reasons.append(gate_reason)
                    opp_dump = None
                    episode_id = None
                    eligible_r = []
                    diagnostics["candidate_disposition"] = (
                        "EXPIRED" if "EXPIRED" in gate_reason else "NO_SETUP"
                    )
                else:
                    reasons.append("WIN_WSL_CURRENT_PATH_REVALIDATED_NO_CHASE")
                    opp_dump = opp.model_dump(mode="json")
                    diagnostics["candidate_disposition"] = state
            else:
                opp_dump = None
                diagnostics["candidate_disposition"] = state

            return {
                "schema_version": HANDOFF_SCHEMA,
                "product_version": HANDOFF_PRODUCT,
                "exposure": manifest["evidence_class"],
                "strategy": "trend_pullback",
                "strategy_version": STRATEGY_VERSION,
                "symbol": symbol,
                "market_state": state,
                "source_type": "WIN_CAPTURE_PUBLIC_REST_COMPLETED_CANDLES",
                "source_qualified": False,
                "shadow_advisory_qualified": False,
                "economically_validated": False,
                "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                "actionability": "HYPOTHETICAL_MARKET_SIDE_ONLY_ACCOUNT_VETO",
                "strict_utc_qualified": False,
                "windows_bundle_sha256": manifest["bundle_sha256"],
                "trigger_close_ms": kw["trigger_close_ms"],
                "decision_ms": kw["decision_ms"],
                "scheduled_review_ms": kw["scheduled_review_ms"],
                "review_source_bounds_ms": [review_lo, review_hi],
                "prefix_sha256": kw["prefix_sha256"],
                "receipt_ids": list(kw["receipt_ids"]),
                "reasons": reasons,
                "confidence": "RULE_EVIDENCE_ONLY_NOT_PROBABILITY",
                "diagnostics": diagnostics,
                "market_observation": obs,
                "opportunity": opp_dump,
                "episode_id": episode_id,
                "eligible_planned_r": eligible_r,
            }

        decisions[symbol] = compile_s1(
            symbol=symbol,
            trigger_ms=trigger,
            decision_ms=review_lo,
            receipts=receipts,
            holding_hours=holding_hours,
            asof_reader=causal,
            decision_factory=decision_factory,
            product_id=HANDOFF_PRODUCT,
            bar_policy=bar_policy,
            source_reason="WIN_QPC_BRACKETED_PUBLIC_HTTPS_NOT_STRICT_SOURCE_ACCOUNT_VETO",
            cost_label="HYPOTHETICAL_UNCALIBRATED_FEE_SPREAD_SLIPPAGE_FUNDING_NOT_FILL_OR_RETURN",
        )

    return decisions


def evaluate_program_c_boundary(
    manifest: dict[str, Any], decisions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Prove unchanged Program C validator rejects operational Windows bundle classes fail-closed."""
    protocol = load_protocol()
    gate = {
        "schema_version": C_SCHEMA,
        "protocol_sha256": protocol["protocol_sha256"],
        "source_kind": manifest["evidence_class"],
        "native_admission": None,
        "synthetic_manifest": None,
        "historical_bounded": False,
        "evaluation_asof_ms": max((d["decision_ms"] for d in decisions.values()), default=1),
        "episodes": [],
        "control_pool": [],
        "no_setup_decision_count": sum(1 for d in decisions.values() if d["market_state"] == "NO_SETUP"),
    }
    gate["export_sha256"] = c_digest(gate)
    raw = json.dumps(gate, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    try:
        c_validate(raw, protocol)
    except ValueError as exc:
        blocker = str(exc)
    else:
        raise HandoffError("C_PROTOCOL_CHANGED_MUST_REJECT_NON_STRICT_SOURCE")

    _require(blocker == "SOURCE_CLASS_INVALID", f"C_UNEXPECTED_GATE_ERROR:{blocker}")
    return {
        "schema": "WSL_WINDOWS_C_BOUNDARY_RESULT_V1",
        "scientific_decision": "INSUFFICIENT_SUPPORT",
        "evaluator_status": "SCHEMA_BLOCKED_WINDOWS_FALLBACK_CLASS",
        "actual_C_validator_error": blocker,
        "C_protocol_sha256": protocol["protocol_sha256"],
        "source_kind": manifest["evidence_class"],
        "source_relabeling": False,
        "C_economic_ledger_executed": False,
        "economically_validated": False,
        "gate_probe_sha256": gate["export_sha256"],
    }


def _process_bundle_audit(
    bundle_dir: Path,
    output_dir: Path,
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    holding_hours: int = 24,
    exclusions: list[tuple[int, int]] | None = None,
    telemetry_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """End-to-end read-only Windows bundle verification + WSL S1 compilation + immutable handoff output."""
    verified = verify_and_load_bundle(bundle_dir, exclusions=exclusions)
    wsl_telemetry = (telemetry_fn or probe_wsl_clock_readonly)()
    decisions = compile_s1_from_verified(verified, symbols=symbols, holding_hours=holding_hours)
    c_boundary = evaluate_program_c_boundary(verified["manifest"], decisions)

    ledger = HandoffLedger(Path(output_dir))
    manifest = verified["manifest"]
    ledger.append_event(
        "BUNDLE_VERIFIED",
        {
            "session": manifest["session"],
            "bundle_sha256": manifest["bundle_sha256"],
            "evidence_class": manifest["evidence_class"],
            "review_bounds": verified["review_bounds"],
            "wsl_clock_telemetry_non_authoritative": wsl_telemetry,
        },
    )
    for sym in symbols:
        ledger.append_event("S1_DECISION", decisions[sym])
    ledger.append_event("PROGRAM_C_BOUNDARY", c_boundary)

    output_obj = {
        "schema": HANDOFF_SCHEMA,
        "product": HANDOFF_PRODUCT,
        "bundle_session": manifest["session"],
        "bundle_sha256": manifest["bundle_sha256"],
        "evidence_class": manifest["evidence_class"],
        "strict_utc_qualified": False,
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        "s2_status": "RESEARCH_ONLY_DISABLED",
        "s3_status": "RESEARCH_ONLY_DISABLED",
        "trigger_ms": verified["trigger_ms"],
        "review_bounds": verified["review_bounds"],
        "decisions": decisions,
        "program_c_boundary": c_boundary,
        "wsl_clock_telemetry": wsl_telemetry,
        "ledger_head_sha256": ledger.head_sha256,
        "ledger_sqlite_sha256": hashlib.sha256(ledger.db_path.read_bytes()).hexdigest(),
    }
    output_obj["handoff_sha256"] = canonical_digest(output_obj)
    _write_atomic_bytes(ledger.directory / "handoff_decisions.json", canonical_bytes(output_obj) + b"\n")
    _write_atomic_bytes(ledger.directory / "c_boundary_status.json", canonical_bytes(c_boundary) + b"\n")
    return output_obj


def process_bundle_to_handoff(bundle_dir, output_dir, *, mode="HISTORY_AUDIT", **kwargs):
    # No caller JSON/WSL time is accepted as an independent current-review anchor.
    _require(mode == "HISTORY_AUDIT", "CURRENT_REVIEW_ANCHOR_UNAVAILABLE", "SOURCE_BLOCKED")
    from .safe_audit import frozen_copy

    output_dir = Path(output_dir)
    _require(not output_dir.exists(), "WSL_HANDOFF_OUTPUT_DIR_MUST_BE_UNUSED_REPEATED_IMPORT")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    frozen, pinned = frozen_copy(bundle_dir, output_dir.parent)
    result = _process_bundle_audit(frozen, output_dir, **kwargs)
    _require(result["bundle_sha256"] == pinned, "AUDIT_BUNDLE_REPLACEMENT")
    result.update(
        mode="HISTORY_AUDIT",
        current_actionability="SOURCE_BLOCKED",
        historical_only=True,
        audit_policy_version="S_HISTORY_NON_ACTIONABLE_V1",
        was_prospectively_issued=False,
        issue_UTC=None,
        raw_copy_provenance={
            "class": "SYNTHETIC_ONLY",
            "source": str(bundle_dir),
            "frozen_copy": str(frozen),
            "real_payload": False,
        },
        current_recommendations={
            sym: {"status": "SOURCE_BLOCKED", "reason": "NO_INDEPENDENT_CURRENT_REVIEW_ANCHOR"}
            for sym in symbols_or_default(kwargs)
        },
    )
    for d in result["decisions"].values():
        d.update(
            current_actionability="SOURCE_BLOCKED",
            historical_only=True,
            evidence_label="SYNTHETIC",
            was_prospectively_issued=False,
            hypothetical_review_at_capture=True,
        )
    result.pop("handoff_sha256", None)
    result["handoff_sha256"] = canonical_digest(result)
    _write_atomic_bytes(output_dir / "handoff_decisions.json", canonical_bytes(result) + b"\n")
    compact = {
        "mode": "HISTORY_AUDIT",
        "evidence": "SYNTHETIC",
        "current_actionability": "SOURCE_BLOCKED",
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        "cards": [
            {
                "symbol": sym,
                "historical_state": d["market_state"],
                "source_time": d["review_source_bounds_ms"],
                "capture_time_unqualified_local_ms": verified_capture_time(frozen),
                "plan": d.get("opportunity"),
                "reasons": d["reasons"],
            }
            for sym, d in result["decisions"].items()
        ],
    }
    _write_atomic_bytes(output_dir / "operator.json", canonical_bytes(compact) + b"\n")
    text = "HISTORY_AUDIT — SYNTHETIC — NON-ACTIONABLE\n" + json.dumps(compact, ensure_ascii=False, indent=2)
    _write_atomic_bytes(output_dir / "operator.md", text.encode())
    from btc_quant_agent.platform.reporting import table

    rows = [
        {
            "symbol": sym,
            "historical_S1_state": d["market_state"],
            "current_actionability": "SOURCE_BLOCKED",
            "plan": json.dumps(d.get("opportunity"), ensure_ascii=False),
            "source_time": d["review_source_bounds_ms"],
            "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        }
        for sym, d in result["decisions"].items()
    ]
    _write_atomic_bytes(
        output_dir / "operator.html",
        (
            "<!doctype html><meta charset=utf-8><h1>HISTORY AUDIT / SYNTHETIC / SOURCE BLOCKED</h1>"
            + table(rows)
        ).encode(),
    )
    return result


def verified_capture_time(frozen):
    return strict_json((Path(frozen) / "bundle_manifest.json").read_bytes())["clock_guard"]["last_sample"][
        "win_utc_ms"
    ]


def symbols_or_default(kwargs):
    return kwargs.get("symbols", SYMBOLS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Windows fallback bundle and compile S1 in WSL (read-only on bundle)."
    )
    parser.add_argument("--bundle", type=Path, required=True, help="Sealed Windows capture bundle directory.")
    parser.add_argument(
        "--output", type=Path, required=True, help="Unused output directory for handoff ledger."
    )
    parser.add_argument("--holding-hours", type=int, default=24)
    parser.add_argument("--mode", choices=["HISTORY_AUDIT", "CURRENT_MANUAL_REVIEW"], default="HISTORY_AUDIT")
    args = parser.parse_args(argv)
    result = process_bundle_to_handoff(
        args.bundle, args.output, mode=args.mode, holding_hours=args.holding_hours
    )
    print(
        canonical_bytes(
            {
                "bundle_sha256": result["bundle_sha256"],
                "handoff_sha256": result["handoff_sha256"],
                "mode": result["mode"],
                "current_actionability": "SOURCE_BLOCKED",
                "historical_states": {s: d["market_state"] for s, d in result["decisions"].items()},
                "c_scientific_decision": result["program_c_boundary"]["scientific_decision"],
            }
        ).decode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
