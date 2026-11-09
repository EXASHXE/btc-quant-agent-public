"""Windows-native finite capture orchestrator emitting QPC-bracketed S1 handoff bundles."""

from __future__ import annotations

import argparse
from contextlib import closing
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
import time
from typing import Any, Callable
import uuid

from .bundle import BundleLedger, canonical_bytes, canonical_digest, write_atomic_bytes
from .transport import CaptureError, RESPONSE_BYTES_MAX, WindowsHttpsTransport, strict_json
from .win_clock import DualWindowsClockMonitor

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
INTERVALS = {"1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000}
MANDATORY_BARS = {"1D": 80, "4H": 100}
REQUEST_COUNT_MAX = 24
REQUEST_WEIGHT_MAX = 40
SESSION_SECONDS_MAX = 120
SESSION_BYTES_MAX = 8_388_608
REQUEST_TIMEOUT_SECONDS = 8.0
REFERENCE_WIDTH_MS_MAX = 5000


def _ensure(cond: bool, msg: str, status: str = "WIN_CAPTURE_BLOCKED") -> None:
    if not cond:
        raise CaptureError(msg, status=status)


def metadata(value: Any) -> dict[str, Any]:
    _ensure(isinstance(value, dict) and isinstance(value.get("symbols"), list), "WIN_EXCHANGE_INFO_SCHEMA")
    wanted: dict[str, Any] = {}
    for item in value["symbols"]:
        symbol = item.get("symbol")
        if symbol not in SYMBOLS:
            continue
        _ensure(symbol not in wanted, "WIN_DUPLICATE_SYMBOL_METADATA")
        _ensure(
            item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
            and item.get("marginAsset") == "USDT"
            and item.get("status") == "TRADING"
            and item.get("baseAsset") == symbol[:-4]
            and item.get("pair", symbol) == symbol,
            "WIN_WRONG_INSTRUMENT_OR_INACTIVE_SYMBOL",
        )
        wanted[symbol] = item
    _ensure(set(wanted) == set(SYMBOLS), "WIN_SYMBOL_METADATA_MISSING")
    limits = value.get("rateLimits", [])
    weights = [
        r
        for r in limits
        if r.get("rateLimitType") == "REQUEST_WEIGHT"
        and r.get("interval") == "MINUTE"
        and r.get("intervalNum") == 1
    ]
    _ensure(
        len(weights) == 1
        and type(weights[0].get("limit")) is int
        and weights[0]["limit"] >= REQUEST_WEIGHT_MAX,
        "WIN_RATE_LIMIT_METADATA_UNUSABLE",
    )
    return wanted


def reference(
    first: tuple[dict[str, Any], dict[str, Any]], last: tuple[dict[str, Any], dict[str, Any]]
) -> dict[str, Any]:
    """Compute Binance serverTime vs Windows QPC monotonic bounds (never wall clock)."""
    probes = [first, last]
    times = [p[0].get("serverTime") if isinstance(p[0], dict) else None for p in probes]
    _ensure(
        all(type(t) is int and t > 0 for t in times) and times[1] >= times[0], "WIN_SERVER_TIME_REGRESSION"
    )
    lo = max(v["serverTime"] - r["receive_sample"]["qpc_after_ms"] - 1 for v, r in probes)
    hi = min(v["serverTime"] - r["request_sample"]["qpc_before_ms"] + 1 for v, r in probes)
    _ensure(
        0 <= hi - lo <= REFERENCE_WIDTH_MS_MAX
        and first[1]["receive_sample"]["boot_session_id"] == last[1]["receive_sample"]["boot_session_id"]
        and first[1]["receive_sample"]["qpc_after_ms"] <= last[1]["request_sample"]["qpc_before_ms"],
        "WIN_TIME_BRACKETS_UNRECONCILABLE",
    )
    return {
        "offset_lower_ms": lo,
        "offset_upper_ms": hi,
        "width_ms": hi - lo,
        "at_qpc_ms": last[1]["receive_sample"]["qpc_after_ms"],
        "boot_session_id": last[1]["receive_sample"]["boot_session_id"],
        "time_response_sha256": [r["body_sha256"] for _, r in probes],
        "anchor_clock": "WINDOWS_QPC_AND_UNBIASED_COHERENT",
        "strict_utc_qualified": False,
    }


def project_qpc(ref: dict[str, Any], now: dict[str, Any], max_age_ms: int = 120_000) -> tuple[int, int]:
    _ensure(
        ref["boot_session_id"] == now["boot_session_id"]
        and 0 <= now["qpc_before_ms"] - ref["at_qpc_ms"] <= max_age_ms,
        "WIN_TIME_REFERENCE_STALE_OR_BOOT_CHANGED",
    )
    return (ref["offset_lower_ms"] + now["qpc_before_ms"], ref["offset_upper_ms"] + now["qpc_after_ms"])


def parse_klines(
    rows: Any,
    symbol: str,
    interval: str,
    *,
    start: int,
    end: int,
    source_lower: int,
    grace_ms: int,
    wire: dict[str, Any],
    ref: dict[str, Any],
    evidence_class: str,
) -> tuple[list[dict[str, Any]], int]:
    _ensure(isinstance(rows, list) and len(rows) <= MANDATORY_BARS[interval] + 1, "WIN_KLINE_RESPONSE_SCHEMA")
    size = INTERVALS[interval]
    output: list[dict[str, Any]] = []
    seen: set[int] = set()
    incomplete = 0
    for row in rows:
        _ensure(isinstance(row, list) and len(row) == 12, "WIN_KLINE_ROW_SCHEMA")
        opening, closing = row[0], row[6]
        _ensure(
            type(opening) is int
            and type(closing) is int
            and opening > 0
            and opening % size == 0
            and closing + 1 - opening == size,
            "WIN_KLINE_ALIGNMENT",
        )
        _ensure(opening not in seen, "WIN_DUPLICATE_CANDLE")
        seen.add(opening)
        try:
            _ensure(
                all(type(row[i]) in (str, int, float) for i in (1, 2, 3, 4, 5, 7, 9, 10)),
                "WIN_KLINE_NUMERIC_TYPES",
            )
            numbers = [Decimal(str(row[i])) for i in (1, 2, 3, 4, 5, 7, 9, 10)]
            _ensure(all(v.is_finite() and math.isfinite(float(v)) for v in numbers), "WIN_KLINE_NONFINITE")
            o, h, low, c, vol, quote, buy, buy_quote = numbers
            _ensure(
                min(o, h, low, c) > 0
                and low <= min(o, c) <= max(o, c) <= h
                and min(vol, quote, buy, buy_quote) >= 0
                and type(row[8]) is int
                and row[8] >= 0,
                "WIN_INVALID_OHLCV",
            )
        except InvalidOperation as exc:
            raise CaptureError("WIN_INVALID_DECIMAL") from exc

        if closing + 1 + grace_ms > source_lower:
            incomplete += 1
            continue
        _ensure(start <= opening and closing < end, "WIN_RESPONSE_OUTSIDE_OPERATIONAL_SCOPE")
        receive_ms = ref["offset_upper_ms"] + wire["receive_sample"]["qpc_after_ms"]
        durable_ms = ref["offset_upper_ms"] + wire["durable_sample"]["qpc_after_ms"]
        content = [symbol, interval, opening, closing, *[str(v.normalize()) for v in numbers]]
        source_id = hashlib.sha256(
            canonical_bytes(["BINANCE_USDM_PERPETUAL_TRADE_PRICE", symbol, interval, opening])
        ).hexdigest()
        output.append(
            {
                "schema": "WIN_REST_COMPLETED_RECEIPT_V1",
                "evidence_class": evidence_class,
                "identity": source_id,
                "source_id": source_id,
                "content_sha256": canonical_digest(content),
                "response_sha256": wire["body_sha256"],
                "session": wire["session"],
                "ordinal": wire["ordinal"],
                "route": wire["route"],
                "raw_row": row,
                "candle": {
                    "symbol": symbol,
                    "interval": interval,
                    "open_time_ms": opening,
                    "close_time_ms": closing,
                    "open": float(o),
                    "high": float(h),
                    "low": float(low),
                    "close": float(c),
                    "volume": float(vol),
                    "quote_volume": float(quote),
                    "closed": True,
                    "available_at_ms": durable_ms,
                },
                "source_event_ms": None,
                "source_publication_ms": None,
                "view": {
                    "source_id": source_id,
                    "received_ms": receive_ms,
                    "available_ms": durable_ms,
                    "durable_ms": durable_ms,
                    "revision": 0,
                },
            }
        )
    _ensure(len(output) >= 60, "WIN_NOT_ENOUGH_COMPLETED_BARS")
    _ensure(
        output[-1]["candle"]["close_time_ms"] + 1 == end
        and [r["candle"]["open_time_ms"] for r in output]
        == list(range(output[0]["candle"]["open_time_ms"], end, size)),
        "WIN_GAP_UNSORTED_OR_STALE_SERIES",
    )
    return output, incomplete


def verify_observation(
    body: Any, wire: dict[str, Any], ref: dict[str, Any], trigger: int, symbol: str
) -> dict[str, Any]:
    _ensure(
        wire["params"]
        == {
            "symbol": symbol,
            "interval": "4h",
            "startTime": trigger,
            "endTime": trigger + INTERVALS["4H"] - 1,
            "limit": 1,
        },
        "WIN_CURRENT_OBSERVATION_SCOPE",
    )
    _ensure(
        isinstance(body, list) and len(body) == 1 and len(body[0]) == 12, "WIN_CURRENT_OBSERVATION_MISSING"
    )
    row = body[0]
    _ensure(
        type(row[0]) is int
        and type(row[6]) is int
        and row[0] == trigger
        and row[6] + 1 == trigger + INTERVALS["4H"],
        "WIN_CURRENT_OBSERVATION_INTERVAL",
    )
    try:
        _ensure(
            all(type(row[i]) in (str, int, float) for i in (1, 2, 3, 4, 5, 7, 9, 10)),
            "WIN_CURRENT_NUMERIC_TYPES",
        )
        vals = [Decimal(str(row[i])) for i in (1, 2, 3, 4, 5, 7, 9, 10)]
        _ensure(all(v.is_finite() and math.isfinite(float(v)) for v in vals), "WIN_CURRENT_NONFINITE")
        o, h, low, c, vol, quote, buy, buy_quote = vals
        _ensure(
            0 < low <= min(o, c) <= max(o, c) <= h
            and min(vol, quote, buy, buy_quote) >= 0
            and type(row[8]) is int
            and row[8] >= 0,
            "WIN_CURRENT_OHLC_INVALID",
        )
    except InvalidOperation as exc:
        raise CaptureError("WIN_CURRENT_DECIMAL_INVALID") from exc
    stamp = wire["durable_sample"]
    _ensure(
        stamp["boot_session_id"] == ref["boot_session_id"]
        and 0 <= ref["at_qpc_ms"] - stamp["qpc_before_ms"] <= 120_000,
        "WIN_OBSERVATION_OUTSIDE_TIME_PROBE_BRACKET",
    )
    lower = ref["offset_lower_ms"] + stamp["qpc_before_ms"]
    upper = ref["offset_upper_ms"] + stamp["qpc_after_ms"]
    _ensure(trigger + 120_000 <= lower <= upper < row[6] + 1, "WIN_CURRENT_OBSERVATION_NOT_CURRENT")
    return {
        "symbol": symbol,
        "cycle_open_ms": trigger,
        "open": float(o),
        "high": float(h),
        "low": float(low),
        "price": float(c),
        "available_bounds_ms": [lower, upper],
        "wire_ref": [wire["session"], wire["ordinal"]],
        "response_sha256": wire["body_sha256"],
        "source_event_ms": None,
        "source_publication_ms": None,
        "kind": "CURRENT_PARTIAL_4H_NOT_A_COMPLETED_SIGNAL_BAR",
    }


class WindowsCollector:
    """Finite Windows capture controller using QPC deadlines & dual QPC/Unbiased guards."""

    def __init__(
        self,
        ledger: BundleLedger,
        *,
        transport: WindowsHttpsTransport,
        clock_monitor: DualWindowsClockMonitor,
        exclusions: list[tuple[int, int]] | None = None,
        grace_ms: int = 120_000,
        max_age_ms: int = 120_000,
        window_minutes: int = 120,
    ):
        _ensure(
            120_000 <= grace_ms <= 300_000 and 30_000 <= max_age_ms <= 120_000, "WIN_FRESHNESS_OUTSIDE_BOUNDS"
        )
        _ensure(5 <= window_minutes <= 120, "WIN_REVIEW_WINDOW_REQUIRES_5_TO_120_MINUTES")
        self.ledger = ledger
        self.transport = transport
        self.clock = clock_monitor
        self.exclusions = list(exclusions or [])
        self.grace_ms = grace_ms
        self.max_age_ms = max_age_ms
        self.window_minutes = window_minutes
        self.session = uuid.uuid4().hex
        self.start = self.clock.anchor
        self.deadline_qpc_ms = self.start["qpc_before_ms"] + SESSION_SECONDS_MAX * 1000
        self.requests = 0
        self.weight = 0
        self.bytes_total = 0

    def get(self, route: str, params: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        now = self.clock.sample()
        remaining_s = (self.deadline_qpc_ms - now["qpc_after_ms"]) / 1000.0
        weight = 2 if int(params.get("limit", 0)) >= 100 else 1
        _ensure(
            remaining_s > 0.3
            and self.requests < REQUEST_COUNT_MAX
            and self.weight + weight <= REQUEST_WEIGHT_MAX
            and self.bytes_total + RESPONSE_BYTES_MAX <= SESSION_BYTES_MAX,
            "WIN_FINITE_REQUEST_BUDGET_OR_DEADLINE",
        )
        self.requests += 1
        self.weight += weight
        self.ledger.append_event(
            "REQUEST_ADMITTED",
            {
                "session": self.session,
                "ordinal": self.requests,
                "route": route,
                "params": params,
                "charged_weight": weight,
                "qpc_before_ms": now["qpc_before_ms"],
            },
        )
        wire = self.transport.get(route, params, min(REQUEST_TIMEOUT_SECONDS, remaining_s - 0.2), self.clock)
        record = self.ledger.persist_response(self.session, self.requests, wire, self.clock.sample)
        self.ledger.append_event(
            "RESPONSE_JOURNAL_ACK",
            {"ordinal": self.requests, "sample": self.clock.sample(), "body_sha256": record["body_sha256"]},
        )
        if self.transport.qa is None:
            self.transport.admission.check(route, params)
        self.bytes_total += record["byte_len"]
        _ensure(record["response_complete"], "WIN_RESPONSE_SIZE_LIMIT_TRUNCATED_RECEIPT")
        _ensure(self.bytes_total <= SESSION_BYTES_MAX, "WIN_RESPONSE_BYTE_BUDGET")
        _ensure(
            record["status"] == 200,
            f"WIN_HTTP_DENIED_OR_LIMITED_{record['status']}_NO_RETRY",
        )
        _ensure("application/json" in record["headers"].get("content-type", ""), "WIN_NON_JSON_RESPONSE")
        used = record["headers"].get("x-mbx-used-weight-1m")
        _ensure(used is None or (used.isdigit() and int(used) <= 2000), "WIN_SHARED_RATE_BUDGET_UNCERTAIN")
        parsed = strict_json(wire["raw_bytes"])
        return parsed, record

    def run(self) -> dict[str, Any]:
        self.ledger.append_event(
            "SESSION_START",
            {
                "session": self.session,
                "evidence_class": self.ledger.evidence_class,
                "start_sample": self.start,
                "w32tm_readonly": self.clock.w32tm_snapshot,
                "grace_ms": self.grace_ms,
                "window_minutes": self.window_minutes,
            },
        )
        try:
            info_body, meta_wire = self.get("/fapi/v1/exchangeInfo", {})
            instruments = metadata(info_body)
            first = self.get("/fapi/v1/time", {})
            _ensure(
                isinstance(first[0], dict) and type(first[0].get("serverTime")) is int,
                "WIN_SERVER_TIME_SCHEMA",
            )
            lower_approx = (
                first[0]["serverTime"]
                - (first[1]["receive_sample"]["qpc_after_ms"] - first[1]["request_sample"]["qpc_before_ms"])
                - 1
            )
            batches = []
            for symbol in SYMBOLS:
                for interval, count in MANDATORY_BARS.items():
                    length = INTERVALS[interval]
                    end = (lower_approx - self.grace_ms) // length * length
                    start = end - count * length
                    _ensure(
                        not any(start < hi and end > lo for lo, hi in self.exclusions),
                        "WIN_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
                    )
                    params = {
                        "symbol": symbol,
                        "interval": {"1D": "1d", "4H": "4h"}[interval],
                        "startTime": start,
                        "endTime": end - 1,
                        "limit": count,
                    }
                    body, wire = self.get("/fapi/v1/klines", params)
                    batches.append((body, symbol, interval, start, end, wire))
            last = self.get("/fapi/v1/time", {})
            hist_ref = reference(first, last)
            records: list[dict[str, Any]] = []
            partial = 0
            for body, symbol, interval, start, end, wire in batches:
                rows, excluded = parse_klines(
                    body,
                    symbol,
                    interval,
                    start=start,
                    end=end,
                    source_lower=lower_approx,
                    grace_ms=self.grace_ms,
                    wire=wire,
                    ref=hist_ref,
                    evidence_class=self.ledger.evidence_class,
                )
                records.extend(rows)
                partial += excluded

            # Current 4H partial observation bracketed by fresh serverTime pair
            q_first = self.get("/fapi/v1/time", {})
            _ensure(
                isinstance(q_first[0], dict) and type(q_first[0].get("serverTime")) is int,
                "WIN_SERVER_TIME_SCHEMA",
            )
            trigger = q_first[0]["serverTime"] // INTERVALS["4H"] * INTERVALS["4H"]
            q_batches = []
            for symbol in SYMBOLS:
                _ensure(
                    not any(trigger < hi and trigger + INTERVALS["4H"] > lo for lo, hi in self.exclusions),
                    "WIN_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
                )
                qb, qw = self.get(
                    "/fapi/v1/klines",
                    {
                        "symbol": symbol,
                        "interval": "4h",
                        "startTime": trigger,
                        "endTime": trigger + INTERVALS["4H"] - 1,
                        "limit": 1,
                    },
                )
                q_batches.append((qb, qw, symbol))
            q_last = self.get("/fapi/v1/time", {})
            q_ref = reference(q_first, q_last)
            observations = [verify_observation(qb, qw, q_ref, trigger, s) for qb, qw, s in q_batches]

            final_sample = self.clock.sample()
            source_bounds = list(project_qpc(hist_ref, final_sample, self.max_age_ms))
            quote_bounds = list(project_qpc(q_ref, final_sample, 30_000))
            min_ready_utc = max(
                max(r["candle"]["available_at_ms"] for r in records),
                max(o["available_bounds_ms"][1] for o in observations),
            )
            min_bounds_lo = min(source_bounds[0], quote_bounds[0])
            if min_bounds_lo < min_ready_utc:
                wait_ms = min_ready_utc - min_bounds_lo + 1
                _ensure(wait_ms <= REFERENCE_WIDTH_MS_MAX, "WIN_CAUSAL_DURABILITY_WAIT_EXCEEDED")
                time.sleep(wait_ms / 1000.0)
                final_sample = self.clock.sample()
                source_bounds = list(project_qpc(hist_ref, final_sample, self.max_age_ms))
                quote_bounds = list(project_qpc(q_ref, final_sample, 30_000))

            _ensure(final_sample["qpc_after_ms"] <= self.deadline_qpc_ms, "WIN_SESSION_DURATION_EXCEEDED")
            _ensure(
                max(source_bounds[0], quote_bounds[0]) <= min(source_bounds[1], quote_bounds[1]),
                "WIN_VENUE_TIME_REFERENCES_DISAGREE",
            )
            review_lo = max(source_bounds[0], quote_bounds[0])
            review_hi = min(source_bounds[1], quote_bounds[1])
            _ensure(
                review_lo // INTERVALS["4H"] * INTERVALS["4H"] == trigger
                and review_hi // INTERVALS["4H"] * INTERVALS["4H"] == trigger
                and all(
                    max(
                        r["candle"]["close_time_ms"] + 1
                        for r in records
                        if r["candle"]["symbol"] == sym and r["candle"]["interval"] == "4H"
                    )
                    == trigger
                    for sym in SYMBOLS
                )
                and all(
                    max(
                        r["candle"]["close_time_ms"] + 1
                        for r in records
                        if r["candle"]["symbol"] == sym and r["candle"]["interval"] == "1D"
                    )
                    == trigger // INTERVALS["1D"] * INTERVALS["1D"]
                    for sym in SYMBOLS
                ),
                "WIN_CYCLE_OR_COMPLETED_BAR_BOUNDARY_MISMATCH",
            )
            _ensure(
                trigger + max(120_000, self.grace_ms) <= review_lo
                and review_hi <= trigger + self.window_minutes * 60_000,
                "WIN_OUTSIDE_MANUAL_REVIEW_WINDOW",
            )

            responses = [json_row for json_row in self._all_response_records()]
            manifest_body = {
                "schema": "WIN_CAPTURE_HANDOFF_BUNDLE_V1",
                "session": self.session,
                "evidence_class": self.ledger.evidence_class,
                "strict_utc_qualified": False,
                "source_qualified": False,
                "economically_validated": False,
                "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                "grace_ms": self.grace_ms,
                "window_minutes": self.window_minutes,
                "reference_max_age_ms": self.max_age_ms,
                "quote_max_age_ms": 30_000,
                "requests": self.requests,
                "request_weight": self.weight,
                "response_bytes": self.bytes_total,
                "metadata_response_sha256": meta_wire["body_sha256"],
                "instruments": instruments,
                "reference": hist_ref,
                "source_bounds": source_bounds,
                "review_bounds": [review_lo, review_hi],
                "incomplete_rows_excluded": partial,
                "records": records,
                "swing_market": {
                    "trigger_ms": trigger,
                    "reference": q_ref,
                    "time_responses": [
                        [q_first[1]["session"], q_first[1]["ordinal"]],
                        [q_last[1]["session"], q_last[1]["ordinal"]],
                    ],
                    "observations": observations,
                    "quote_bounds": quote_bounds,
                },
                "clock_guard": {
                    "anchor_clock": "WINDOWS_QPC_AND_UNBIASED_COHERENT",
                    "max_span_ms": self.clock.max_span_ms,
                    "max_divergence_ms": self.clock.max_divergence_ms,
                    "samples_count": len(self.clock.samples),
                    "first_sample": self.clock.samples[0],
                    "last_sample": final_sample,
                    "wall_jumps_observed": self.clock.wall_jumps_observed,
                    "w32tm_readonly": self.clock.w32tm_snapshot,
                },
                "responses": responses,
            }
            if self.transport.qa is None:
                self.transport.admission.check("/fapi/v1/time", {})
            manifest_body_sha256 = canonical_digest(manifest_body)
            self.ledger.append_event(
                "BUNDLE_SEALED",
                {
                    "session": self.session,
                    "manifest_body_sha256": manifest_body_sha256,
                    "records_sha256": canonical_digest(records),
                    "responses_sha256": canonical_digest(responses),
                    "requests": self.requests,
                    "weight": self.weight,
                },
            )
            manifest = {
                **manifest_body,
                "manifest_body_sha256": manifest_body_sha256,
                "ledger_head_sha256": self.ledger.head_sha256,
                "ledger_sqlite_sha256": hashlib.sha256(self.ledger.db_path.read_bytes()).hexdigest(),
            }
            manifest["bundle_sha256"] = canonical_digest(manifest)
            write_atomic_bytes(
                self.ledger.directory / "bundle_manifest.json", canonical_bytes(manifest) + b"\n"
            )
            return manifest
        except BaseException as exc:
            self.ledger.append_event("SESSION_FAILED", {"session": self.session, "reason": str(exc)})
            raise

    def _all_response_records(self) -> list[dict[str, Any]]:
        import json as _json

        with closing(self.ledger._connect()) as db:
            rows = db.execute(
                "SELECT payload_json FROM events WHERE kind='HTTP_RESPONSE' ORDER BY seq ASC"
            ).fetchall()
        return [_json.loads(r[0]) for r in rows]


def capture_session(
    output_dir: Path,
    *,
    qa: dict[str, Any] | None = None,
    clock_sampler: Callable[[], dict[str, Any]] | None = None,
    exclusions: list[tuple[int, int]] | None = None,
    grace_ms: int = 120_000,
    max_age_ms: int = 120_000,
    window_minutes: int = 120,
    access_path: Path | None = None,
    authorization_path: Path | None = None,
) -> dict[str, Any]:
    """Run one finite Windows-native capture and seal a handoff bundle."""
    evidence_class = "WIN_CAPTURE_LOOPBACK_QA_V1" if qa is not None else "WIN_CAPTURE_PUBLIC_OPERATIONAL_V1"
    if qa is None and (access_path is None or authorization_path is None or clock_sampler is not None):
        raise CaptureError("WIN_REAL_ACCESS_OWNER_SCOPE_AND_NATIVE_CLOCK_REQUIRED")
    monitor = DualWindowsClockMonitor(sampler=clock_sampler)
    admission = None
    if qa is None:
        from .access import Admission

        admission = Admission(access_path, authorization_path, output_dir, monitor)
        exclusions = admission.exclusions
    transport = WindowsHttpsTransport(
        qa=qa, proxy=admission.access["proxy"] if admission else None, admission=admission
    )
    ledger = BundleLedger(output_dir, evidence_class=evidence_class)
    try:
        if admission:
            ledger.append_event("S_ACCESS_CONSUMED", admission.receipt)
        collector = WindowsCollector(
            ledger,
            transport=transport,
            clock_monitor=monitor,
            exclusions=exclusions,
            grace_ms=grace_ms,
            max_age_ms=max_age_ms,
            window_minutes=window_minutes,
        )
        if admission:
            collector.session = admission.grant["session"]
        return collector.run()
    finally:
        ledger.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quant v0.7.0 Windows-native fallback capture CLI (no live default)."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-live-public-https", action="store_true", help="Explicit owner gate for real Binance GET."
    )
    parser.add_argument("--access", type=Path)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args(argv)
    if not args.allow_live_public_https:
        raise SystemExit("BLOCKED_LIVE_NETWORK_REQUIRES_EXPLICIT_OWNER_APPROVAL")
    if args.access is None or args.authorization is None:
        raise SystemExit("BLOCKED_HASH_BOUND_ACCESS_AND_NEW_OWNER_SCOPE_REQUIRED")
    manifest = capture_session(args.output, access_path=args.access, authorization_path=args.authorization)
    print(
        canonical_bytes({"session": manifest["session"], "bundle_sha256": manifest["bundle_sha256"]}).decode(
            "utf-8"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
