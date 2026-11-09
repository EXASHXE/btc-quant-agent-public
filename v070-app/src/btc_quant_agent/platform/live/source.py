"""Bounded operational rolling candles, immutable response and clock lineage."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import ipaddress
import math
import uuid
from typing import Any

from ..native.contract import digest, strict
from ..swing import INTERVALS
from .models import Access, POLICY, POLICY_HASH, PUBLIC, QA, Blocked, ensure, offset_step, sample
from .rest import Transport


def metadata(value):
    ensure(isinstance(value, dict) and isinstance(value.get("symbols"), list), "LIVE_EXCHANGE_INFO_SCHEMA")
    wanted = {}
    for item in value["symbols"]:
        symbol = item.get("symbol")
        if symbol not in POLICY["symbols"]:
            continue
        ensure(symbol not in wanted, "LIVE_DUPLICATE_SYMBOL_METADATA")
        ensure(
            item.get("contractType") == "PERPETUAL"
            and item.get("quoteAsset") == "USDT"
            and item.get("marginAsset") == "USDT"
            and item.get("status") == "TRADING"
            and item.get("baseAsset") == symbol[:-4]
            and item.get("pair", symbol) == symbol,
            "LIVE_WRONG_INSTRUMENT_OR_INACTIVE_SYMBOL",
        )
        wanted[symbol] = item
    ensure(set(wanted) == set(POLICY["symbols"]), "LIVE_SYMBOL_METADATA_MISSING")
    limits = value.get("rateLimits", [])
    weights = [
        r
        for r in limits
        if r.get("rateLimitType") == "REQUEST_WEIGHT"
        and r.get("interval") == "MINUTE"
        and r.get("intervalNum") == 1
    ]
    ensure(
        len(weights) == 1
        and type(weights[0].get("limit")) is int
        and weights[0]["limit"] >= POLICY["request_weight_max"],
        "LIVE_RATE_LIMIT_METADATA_UNUSABLE",
    )
    return wanted


def reference(first, last):
    probes = [first, last]
    times = [p[0]["serverTime"] for p in probes]
    ensure(
        all(type(t) is int and t > 0 for t in times) and times[1] >= times[0],
        "LIVE_SERVER_TIME_REGRESSION",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    lo = max(v["serverTime"] - r["receive_sample"]["mono_after_ms"] - 1 for v, r in probes)
    hi = min(v["serverTime"] - r["request_sample"]["mono_before_ms"] + 1 for v, r in probes)
    ensure(
        0 <= hi - lo <= POLICY["reference_width_ms_max"]
        and first[1]["receive_sample"]["boot_id"] == last[1]["receive_sample"]["boot_id"]
        and first[1]["receive_sample"]["mono_after_ms"] <= last[1]["request_sample"]["mono_before_ms"],
        "LIVE_TIME_BRACKETS_UNRECONCILABLE",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    return {
        "offset_lower_ms": lo,
        "offset_upper_ms": hi,
        "at_mono_ms": last[1]["receive_sample"]["mono_after_ms"],
        "boot_id": last[1]["receive_sample"]["boot_id"],
        "time_response_sha256": [r["body_sha256"] for _, r in probes],
        "UTC_qualification": "OPERATIONAL_SINGLE_VENUE_HTTPS_SERVER_TIME_NOT_STRICT",
    }


def project(ref, now, max_age=120000):
    ensure(
        ref["boot_id"] == now["boot_id"] and 0 <= now["mono_before_ms"] - ref["at_mono_ms"] <= max_age,
        "LIVE_TIME_REFERENCE_STALE_OR_BOOT_CHANGED",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    return (ref["offset_lower_ms"] + now["mono_before_ms"], ref["offset_upper_ms"] + now["mono_after_ms"])


def parse_rows(rows, symbol, interval, *, start, end, source_lower, grace_ms, wire, ref, exposure):
    ensure(isinstance(rows, list) and len(rows) <= POLICY["bars"][interval] + 1, "LIVE_KLINE_RESPONSE_SCHEMA")
    output, seen, incomplete = [], set(), 0
    size = INTERVALS[interval]
    for row in rows:
        ensure(isinstance(row, list) and len(row) == 12, "LIVE_KLINE_ROW_SCHEMA")
        opening, closing = row[0], row[6]
        ensure(
            type(opening) is int
            and type(closing) is int
            and opening > 0
            and opening % size == 0
            and closing + 1 - opening == size,
            "LIVE_KLINE_ALIGNMENT",
        )
        ensure(opening not in seen, "LIVE_DUPLICATE_CANDLE")
        seen.add(opening)
        try:
            ensure(
                all(type(row[i]) in (str, int, float) for i in (1, 2, 3, 4, 5, 7, 9, 10)),
                "LIVE_KLINE_NUMERIC_TYPES",
            )
            numbers = [Decimal(str(row[i])) for i in (1, 2, 3, 4, 5, 7, 9, 10)]
            ensure(all(v.is_finite() for v in numbers), "LIVE_NONFINITE_OHLCV")
            ensure(
                all(math.isfinite(float(v)) for v in numbers) and all(float(v) > 0 for v in numbers[:4]),
                "LIVE_FLOAT_RANGE_INVALID",
            )
            o, high, low, c, volume, quote, buy, buy_quote = numbers
            ensure(
                min(o, high, low, c) > 0
                and low <= min(o, c) <= max(o, c) <= high
                and min(volume, quote, buy, buy_quote) >= 0
                and type(row[8]) is int
                and row[8] >= 0,
                "LIVE_INVALID_OHLCV",
            )
        except InvalidOperation as e:
            raise Blocked("LIVE_INVALID_DECIMAL") from e
        if closing + 1 + grace_ms > source_lower:
            incomplete += 1
            continue
        ensure(start <= opening and closing < end, "LIVE_RESPONSE_OUTSIDE_OPERATIONAL_SCOPE")
        receive = ref["offset_upper_ms"] + wire["receive_sample"]["mono_after_ms"]
        durable = ref["offset_upper_ms"] + wire["durable_sample"]["mono_after_ms"]
        content = [symbol, interval, opening, closing, *[str(v.normalize()) for v in numbers]]
        source_id = digest(["BINANCE_USDM_PERPETUAL_TRADE_PRICE", symbol, interval, opening])
        candle = dict(
            symbol=symbol,
            interval=interval,
            open_time_ms=opening,
            close_time_ms=closing,
            open=float(o),
            high=float(high),
            low=float(low),
            close=float(c),
            volume=float(volume),
            quote_volume=float(quote),
            closed=True,
            available_at_ms=durable,
        )
        output.append(
            {
                "schema": "J_REST_COMPLETED_RECEIPT_V1",
                "evidence_class": exposure,
                "identity": source_id,
                "source_id": source_id,
                "content_sha256": digest(content),
                "response_sha256": wire["body_sha256"],
                "session": wire["session"],
                "ordinal": wire["ordinal"],
                "route": wire["route"],
                "raw_row": row,
                "candle": candle,
                "source_event_ms": None,
                "source_publication_ms": None,
                "receive_sample": wire["receive_sample"],
                "durable_sample": wire["durable_sample"],
                "view": {
                    "source_id": source_id,
                    "received_ms": receive,
                    "available_ms": durable,
                    "durable_ms": durable,
                    "revision": 0,
                },
            }
        )
    ensure(
        len(output) >= (60 if interval in ("1D", "4H") else 2),
        "LIVE_NOT_ENOUGH_COMPLETED_BARS",
        "LIVE_WARMUP_INSUFFICIENT",
    )
    ensure(
        output[-1]["candle"]["close_time_ms"] + 1 == end
        and [r["candle"]["open_time_ms"] for r in output]
        == list(range(output[0]["candle"]["open_time_ms"], end, size)),
        "LIVE_GAP_UNSORTED_OR_STALE_SERIES",
        "LIVE_WARMUP_INSUFFICIENT",
    )
    return output, incomplete


class Collector:
    bars = POLICY["bars"]

    def finish_snapshot(self, result):
        """Version-specific operational admission hook; V1 performs no extra requests."""
        return result

    def __init__(self, store, access_file=None, *, grace_ms=120000, max_age_ms=120000, _qa=None):
        ensure(
            60000 <= grace_ms <= 300000 and 30000 <= max_age_ms <= 300000,
            "LIVE_FRESHNESS_POLICY_OUTSIDE_BOUNDS",
        )
        self.store, self.access_file, self.qa = store, access_file, _qa
        self.grace, self.max_age = grace_ms, max_age_ms
        self.exposure = QA if _qa else PUBLIC
        ensure(store.meta["evidence_class"] == self.exposure, "LIVE_EVIDENCE_CLASS_MIXING")
        self.access = None
        self.exclusions: dict[str, Any] = {"excluded_UTC_ms_ranges": []}
        if _qa:
            ensure(ipaddress.ip_address(_qa["host"]).is_loopback, "LIVE_QA_LOOPBACK_ONLY")
        else:
            self.access, self.exclusions = Access.load(access_file)
        self.transport = Transport(access_file, _qa)
        self.start, self.session = sample(), uuid.uuid4().hex
        self.deadline = self.start["mono_before_ms"] + POLICY["session_seconds_max"] * 1000
        self.requests, self.weight, self.size = 0, 0, 0
        self.last = self.start
        self.jumped = False

    def get(self, route, params):
        now = sample()
        self.jumped |= offset_step(self.last, now)
        self.last = now
        remaining = (self.deadline - now["mono_after_ms"]) / 1000
        weight = 2 if params.get("limit", 0) >= 100 else 1
        ensure(
            remaining > 0.3
            and self.requests < POLICY["request_count_max"]
            and self.weight + weight <= POLICY["request_weight_max"]
            and self.size + POLICY["response_bytes_max"] <= POLICY["session_bytes_max"],
            "LIVE_FINITE_REQUEST_BUDGET",
        )
        self.store.capacity()
        self.requests += 1
        self.weight += weight
        self.store.events.append(
            "REQUEST_ADMITTED",
            {
                "session": self.session,
                "ordinal": self.requests,
                "route": route,
                "params": params,
                "charged_weight": weight,
                "sample": now,
            },
        )
        wire = self.transport.request(route, params, min(POLICY["request_timeout_seconds"], remaining - 0.2))
        self.jumped |= offset_step(now, wire["receive_sample"])
        raw, record = self.store.persist_response(self.session, self.requests, wire)
        self.size += len(raw)
        ensure(record.get("response_complete", True), "LIVE_RESPONSE_SIZE_LIMIT_TRUNCATED_RECEIPT")
        ensure(self.size <= POLICY["session_bytes_max"], "LIVE_RESPONSE_BYTE_BUDGET")
        ensure(
            record["status"] == 200,
            "LIVE_HTTP_DENIED_OR_LIMITED_" + str(record["status"]) + "_NO_RETRY_OR_GEO_BYPASS",
        )
        ensure("application/json" in record["headers"].get("content-type", ""), "LIVE_NON_JSON_RESPONSE")
        used = record["headers"].get("x-mbx-used-weight-1m")
        ensure(used is None or (used.isdigit() and int(used) <= 2000), "LIVE_SHARED_RATE_BUDGET_UNCERTAIN")
        self.last = record["durable_sample"]
        # Reuse the original duplicate-key/nonfinite JSON checks for REST arrays.
        parsed = strict(b'{"response":' + raw + b"}")
        ensure(set(parsed) == {"response"}, "LIVE_JSON_TRAILING_OR_MULTIPLE_VALUES")
        return parsed["response"], record

    def batch(self):
        first = self.get("/fapi/v1/time", {})
        ensure(
            isinstance(first[0], dict) and type(first[0].get("serverTime")) is int,
            "LIVE_SERVER_TIME_SCHEMA",
            "LIVE_CLOCK_DEGRADED_BLOCKED",
        )
        lower = (
            first[0]["serverTime"]
            - (first[1]["receive_sample"]["mono_after_ms"] - first[1]["request_sample"]["mono_before_ms"])
            - 1
        )
        batches = []
        for symbol in POLICY["symbols"]:
            for interval, count in self.bars.items():
                length = INTERVALS[interval]
                end = (lower - self.grace) // length * length
                start = end - count * length
                ensure(
                    not any(start < hi and end > lo for lo, hi in self.exclusions["excluded_UTC_ms_ranges"]),
                    "LIVE_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
                )
                params = {
                    "symbol": symbol,
                    "interval": {"1D": "1d", "4H": "4h", "1H": "1h"}[interval],
                    "startTime": start,
                    "endTime": end - 1,
                    "limit": count,
                }
                body, wire = self.get("/fapi/v1/klines", params)
                batches.append((body, symbol, interval, start, end, wire))
        last = self.get("/fapi/v1/time", {})
        ref = reference(first, last)
        records, partial = [], 0
        for body, symbol, interval, start, end, wire in batches:
            rows, excluded = parse_rows(
                body,
                symbol,
                interval,
                start=start,
                end=end,
                source_lower=lower,
                grace_ms=self.grace,
                wire=wire,
                ref=ref,
                exposure=self.exposure,
            )
            records.extend(rows)
            partial += excluded
        return records, ref, partial

    def run(self):
        self.store.recover()
        self.store.events.append(
            "SESSION_START",
            {
                "session": self.session,
                "sample": self.start,
                "exposure": self.exposure,
                "access_sha256": digest(self.access.model_dump(mode="json")) if self.access else None,
                "policy_sha256": POLICY_HASH,
                "grace_ms": self.grace,
            },
        )
        try:
            ensure(
                not self.store.events.values("SOURCE_STOP"),
                "LIVE_SOURCE_REVISION_REQUIRES_NEW_REVIEWED_VERSION",
            )
            info, meta_wire = self.get("/fapi/v1/exchangeInfo", {})
            instruments = metadata(info)
            records, ref, partial = self.batch()
            previous = self.store.snapshots()
            known_wsl = "microsoft" in __import__("platform").release().lower()
            hold = self.jumped or (not previous and known_wsl)
            states = self.store.events.values("CLOCK_STATE")
            if states:
                hold |= states[-1]["held"] or states[-1]["session"] not in {p["session"] for p in previous}
            if previous:
                hold |= offset_step(previous[-1]["last_sample"], self.start)
                prior_ref = previous[-1]["reference"]
                if prior_ref["boot_id"] == ref["boot_id"]:
                    hold |= (
                        ref["offset_lower_ms"] - prior_ref["offset_upper_ms"] > 5000
                        or prior_ref["offset_lower_ms"] - ref["offset_upper_ms"] > 5000
                    )
                ensure(
                    ref["offset_upper_ms"] + self.last["mono_after_ms"] >= previous[-1]["source_bounds"][0],
                    "LIVE_SOURCE_TIME_REGRESSION",
                    "LIVE_CLOCK_DEGRADED_BLOCKED",
                )
            if hold:
                self.store.events.append("CLOCK_STATE", {"session": self.session, "held": True})
                self.store.events.append(
                    "CLOCK_HOLD",
                    {
                        "session": self.session,
                        "reason": "WALL_STEP_OR_BOOT_OR_KNOWN_WSL_HISTORY",
                        "sample": self.last,
                    },
                )
                # A separate complete read, new HTTPS connections, new clock probes.
                self.jumped = False
                witness, second, partial2 = self.batch()
                old = {r["identity"]: r["content_sha256"] for r in records}
                ensure(
                    all(old.get(r["identity"]) == r["content_sha256"] for r in witness)
                    and len(witness) == len(records)
                    and not self.jumped,
                    "LIVE_REACQUISITION_DISAGREES_OR_CLOCK_STILL_UNSTABLE",
                    "LIVE_CLOCK_DEGRADED_BLOCKED",
                )
                self.store.events.append(
                    "CLOCK_RECONCILIATION",
                    {
                        "session": self.session,
                        "first_prefix_sha256": digest(records),
                        "witness_prefix_sha256": digest(witness),
                        "reference": second,
                        "strict_UTC_qualified": False,
                    },
                )
                records, ref, partial = witness, second, partial + partial2
            prior_records = {r["identity"]: r for r in self.store.records()}
            for row in records:
                earlier = prior_records.get(row["identity"])
                ensure(
                    earlier is None or earlier["content_sha256"] == row["content_sha256"],
                    "LIVE_UNRESOLVED_CANDLE_REVISION",
                    "LIVE_WARMUP_INSUFFICIENT",
                )
            # Existing committed rows retain their first observed receipt/availability.
            records = [prior_records.get(r["identity"], r) for r in records]
            now = sample()
            ensure(now["mono_after_ms"] <= self.deadline, "LIVE_SESSION_DURATION_EXCEEDED")
            ensure(
                not offset_step(self.last, now),
                "LIVE_CLOCK_STEP_BEFORE_COMMIT",
                "LIVE_CLOCK_DEGRADED_BLOCKED",
            )
            bounds = project(ref, now, self.max_age)
            result = {
                "schema": "J_OPERATIONAL_SNAPSHOT_V1",
                "session": self.session,
                "exposure": self.exposure,
                "records": records,
                "reference": ref,
                "source_bounds": list(bounds),
                "last_sample": now,
                "grace_ms": self.grace,
                "reference_max_age_ms": self.max_age,
                "instruments": instruments,
                "metadata_response_sha256": meta_wire["body_sha256"],
                "incomplete_rows_excluded": partial,
                "requests": self.requests,
                "request_weight": self.weight,
                "response_bytes": self.size,
                "clock": "CLOCK_DEGRADED_RECONCILED"
                if hold or any(p["clock"] == "CLOCK_DEGRADED_RECONCILED" for p in previous)
                else "OPERATIONAL_SERVER_TIME_UNQUALIFIED",
                "retention_days": self.access.retention_days if self.access else 1,
            }
            result = self.finish_snapshot(result)
            self.store.events.append("SNAPSHOT", result)
            self.store.events.append(
                "SESSION_TERMINAL",
                {
                    "session": self.session,
                    "status": "COMPLETE",
                    "snapshot_sha256": digest(result),
                    "requests": self.requests,
                    "weight": self.weight,
                    "response_bytes": self.size,
                    "sample": sample(),
                },
            )
            self.store.events.append("CLOCK_STATE", {"session": self.session, "held": False})
            return result
        except BaseException as error:
            if "REVISION" in str(error) and not self.store.events.values("SOURCE_STOP"):
                self.store.events.append(
                    "SOURCE_STOP",
                    {"session": self.session, "reason": str(error), "original_plans_immutable": True},
                )
            if self.jumped or (isinstance(error, Blocked) and error.status == "LIVE_CLOCK_DEGRADED_BLOCKED"):
                self.store.events.append("CLOCK_STATE", {"session": self.session, "held": True})
            self.store.events.append(
                "SESSION_TERMINAL",
                {
                    "session": self.session,
                    "status": "FAILED",
                    "reason": str(error),
                    "requests": self.requests,
                    "weight": self.weight,
                    "response_bytes": self.size,
                },
            )
            raise
