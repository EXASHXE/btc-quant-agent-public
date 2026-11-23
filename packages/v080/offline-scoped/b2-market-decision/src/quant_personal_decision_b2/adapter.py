"""Read-only B1 V2 compatibility boundary with raw, normalized, and availability checks."""

from __future__ import annotations

import ipaddress
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quant_personal_public_b1 import normalize as n
from quant_personal_public_b1.compat import funding_payload, oi_payload
from quant_personal_public_b1.policy import (
    DEPTH,
    FRESHNESS,
    FUNDING,
    INSTRUMENTS,
    INTERVALS,
    KLINES,
    MARK,
    OI,
    OI_HISTORY,
    QUOTE,
    SYMBOLS,
    TICKER,
    TIME,
)
from quant_personal_public_b1.policy import SourceBlocked as B1Blocked
from quant_personal_public_b1.store import Store
from quant_personal_public_b1.store import encode as b1_encode
from quant_personal_public_b1.store import sha as raw_sha
from quant_personal_public_b1.wire import FIXTURE, HOST, LOOPBACK, Request, json_body

from .model import (
    ADAPTER,
    RECEIPT,
    SYNTHETIC,
    Bar,
    DecisionError,
    Market,
    check,
    digest,
    integer,
)

ORIGINS = {"fixture": (FIXTURE, "fixture-local"), "loopback": (LOOPBACK, "loopback-qa")}
OBSERVATIONS = {
    "instrument": (INSTRUMENTS, "instrument"), "ticker": (TICKER, "ticker"),
    "quote": (QUOTE, "book_ticker"), "depth": (DEPTH, "depth"), "oi": (OI, "open_interest"),
    "oi_history": (OI_HISTORY, "open_interest_history"), "funding": (FUNDING, "funding_history"),
    "mark": (MARK, "mark_funding"),
}
SOURCE_VERSION = "PERSONAL_PUBLIC_MARKET_SNAPSHOT_V2"
CONTRACT = "USD-M-2026-11-18-B1"
WARMUP = {"1d": 12, "4h": 30, "1h": 30, "15m": 15, "5m": 15}
MAX_BARS = 1500
MAX_RAW_BYTES = 4_000_000
CLOSE_GRACE_MS = 2000


def obj(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionError("INPUT_SCHEMA")
    return value


def normalized(value: object) -> Any:
    return json.loads(b1_encode(value))


def stamp(value: object) -> dict[str, Any]:
    row = obj(value)
    check(isinstance(row.get("boot"), str) and bool(row["boot"])
          and isinstance(row.get("session"), str) and bool(row["session"]), "INPUT_STAMP")
    integer(row.get("wall_ms"), "wall_ms", minimum=1)
    integer(row.get("monotonic_ms"), "monotonic_ms")
    return row


def chronological(*stamps: object) -> None:
    parsed = [stamp(value) for value in stamps]
    for prior, after in zip(parsed, parsed[1:], strict=False):
        check(prior["boot"] == after["boot"] and prior["session"] == after["session"], "INPUT_CLOCK_DOMAIN")
        check(prior["monotonic_ms"] <= after["monotonic_ms"], "INPUT_TIME_ORDER")


class MarketSnapshotAdapter:
    def __init__(self, path: Path, mode: str) -> None:
        check(mode in ORIGINS, "UNQUALIFIED_SOURCE_ORIGIN")
        self.origin, egress = ORIGINS[mode]
        try:
            self.store = Store(path, self.origin, egress)
        except (ValueError, sqlite3.Error, OSError) as exc:
            raise DecisionError("UNQUALIFIED_SOURCE_STORE", str(exc)) from exc

    def rejected_reference(self, *, scan: int | None, as_of_ms: int) -> dict[str, Any] | None:
        # Diagnostic only. A rejected publication is never exposed as a usable market snapshot.
        try:
            snapshot = self.store.snapshot(scan=scan, as_of_ms=None if scan is not None else as_of_ms)
            if snapshot is None:
                return None
            return {"source_origin": self.origin, "source_scan_id": snapshot["scan_id"],
                    "source_publication_sha256": raw_sha(b1_encode(snapshot).encode()),
                    "source_status": snapshot.get("source_status"),
                    "source_published_venue_ms": snapshot.get("decision_as_of_venue_ms"),
                    "usable_for_evaluation": False}
        except (B1Blocked, KeyError, TypeError, sqlite3.Error):
            return None

    def read(self, symbol: str, *, scan: int | None = None, as_of_ms: int | None = None) -> Market:
        check(symbol in SYMBOLS, "UNQUALIFIED_SYMBOL", symbol)
        if as_of_ms is not None:
            integer(as_of_ms, "as_of_ms", minimum=1)
        try:
            snapshot = self.store.snapshot(scan=scan, as_of_ms=None if scan is not None else as_of_ms)
            if snapshot is None:
                raise DecisionError("NO_DURABLE_PUBLICATION_AS_OF")
            # B1 reads through its accepted API. The read-only SQL extension binds raw and original publication rows.
            with self.store.connect() as conn:
                reader = BoundRead(conn, self.origin)
                return reader.market(snapshot, symbol, as_of_ms)
        except DecisionError:
            raise
        except (B1Blocked, KeyError, TypeError, sqlite3.Error, RecursionError, OverflowError) as exc:
            raise DecisionError("SOURCE_EVIDENCE_INVALID", str(exc)) from exc


class BoundRead:
    def __init__(self, db: sqlite3.Connection, origin: str) -> None:
        self.db = db
        self.origin = origin
        self.publications: dict[int, tuple[dict[str, Any], str, int | None]] = {}
        self.attempts: dict[int, tuple[dict[str, Any], dict[str, Any], object]] = {}
        self.references: dict[int, dict[str, Any]] = {}

    def publication(self, scan: int) -> tuple[dict[str, Any], str, int | None]:
        if scan not in self.publications:
            row = self.db.execute("SELECT payload,sha256,visible_venue_upper_ms,published_wall_ms FROM publications "
                                  "WHERE scan_id=?", (scan,)).fetchone()
            if row is None:
                raise DecisionError("SOURCE_PUBLICATION_MISSING", str(scan))
            check(raw_sha(row["payload"].encode()) == row["sha256"], "SOURCE_PUBLICATION_DIGEST")
            value = obj(json.loads(row["payload"]))
            check(value.get("schema") == SOURCE_VERSION and value.get("source_origin") == self.origin
                  and value.get("evidence_class") == "PERSONAL_PUBLIC_MARKET" and value.get("scan_id") == scan
                  and value.get("endpoint_contract") == CONTRACT, "UNQUALIFIED_SOURCE_PUBLICATION")
            upper = row["visible_venue_upper_ms"]
            check(upper == value.get("decision_as_of_venue_ms") and row["published_wall_ms"]
                  == stamp(value.get("published"))["wall_ms"], "SOURCE_PUBLICATION_CLOCK")
            self.publications[scan] = value, row["sha256"], upper
        return self.publications[scan]

    def attempt(self, ident: int, route: str, scan: int) -> tuple[dict[str, Any], dict[str, Any], Any]:
        if ident not in self.attempts:
            row = self.db.execute(
                "SELECT id,scan_id,route,request,reserved,response,raw FROM attempts WHERE id=?", (ident,)
            ).fetchone()
            if row is None or row["raw"] is None or row["response"] is None:
                raise DecisionError("SOURCE_RECEIPT_MISSING", str(ident))
            res = obj(json.loads(row["response"]))
            req = obj(json.loads(row["request"]))
            reserved = obj(json.loads(row["reserved"]))
            check(len(row["raw"]) <= MAX_RAW_BYTES and res.get("status") == 200
                  and res.get("body_sha256") == raw_sha(row["raw"]), "SOURCE_RAW_DIGEST")
            check(req.get("method") == "GET", "SOURCE_METHOD")
            Request(row["route"], req["params"], req["method"], req["host"], req["port"]).validate()
            if self.origin == LOOPBACK:
                proof = obj(res.get("tls"))
                peer = proof.get("peer")
                if not isinstance(peer, str):
                    raise DecisionError("SOURCE_TLS_ORIGIN")
                try:
                    local = ipaddress.ip_address(peer).is_loopback
                except ValueError as exc:
                    raise DecisionError("SOURCE_TLS_ORIGIN") from exc
                check(local and proof.get("verification") == "CERT_REQUIRED_AND_HOSTNAME"
                      and proof.get("sni") == HOST and len(proof.get("certificate_sha256", "")) == 64,
                      "SOURCE_TLS_ORIGIN")
            else:
                check(res.get("tls") is None, "SOURCE_FIXTURE_ORIGIN")
            data = {"receipt_id": ident, "source_scan_id": row["scan_id"], "path": row["route"],
                    "raw_sha256": res["body_sha256"], "request": req, "reserved": reserved,
                    "receipt": res["receipt"], "tls": res.get("tls")}
            self.attempts[ident] = data, req, json_body(row["raw"])
        meta, req, body = self.attempts[ident]
        check((meta["path"], meta["source_scan_id"]) == (route, scan), "SOURCE_RECEIPT_BINDING")
        self.references[ident] = meta
        return meta, req, body

    def timing(self, value: dict[str, Any], route: str, as_of: int,
               max_scan: int) -> tuple[dict[str, Any], dict[str, Any], Any]:
        ident = integer(value.get("receipt_id"), "receipt_id", minimum=1)
        scan = integer(value.get("source_scan_id"), "source_scan_id", minimum=1)
        check(scan <= max_scan, "LATE_SOURCE_SCAN")
        source, publication_hash, upper = self.publication(scan)
        check(upper is not None and upper <= as_of, "LATE_SOURCE_PUBLICATION")
        meta, req, raw = self.attempt(ident, route, scan)
        durable = value.get("first_durable_availability")
        check(durable == source["durable_availability"] and value.get("first_receipt") == meta["receipt"],
              "SOURCE_DURABILITY_BINDING")
        chronological(meta["reserved"], value.get("first_request"), meta["receipt"],
                      value.get("first_observation"), durable, source["published"])
        lo, hi = self.bounds(value, "received_venue_lower_ms", "received_venue_upper_ms")
        check(upper is not None and hi <= as_of and lo <= upper, "LATE_RECEIPT")
        first = obj(obj(source["clock"])["first"])
        # B1 projects receipts from the first bracket with <=1000ppm drift. Verify clock-domain relation.
        delta = meta["receipt"]["monotonic_ms"] - first["monotonic_ms"]
        allowance = (abs(delta) + 999) // 1000
        check(value["first_request"]["monotonic_ms"] >= first["monotonic_ms"], "SOURCE_REQUEST_BEFORE_WITNESS")
        check(delta >= 0 and first["venue_lower_ms"] + delta - allowance <= lo
              <= first["venue_lower_ms"] + delta and first["venue_upper_ms"] + delta <= hi
              <= first["venue_upper_ms"] + delta + allowance, "SOURCE_RECEIPT_VENUE_CLOCK")
        ref = {"receipt_id": ident, "source_scan_id": scan, "source_publication_sha256": publication_hash,
               "source_available_venue_ms": upper, "raw_sha256": meta["raw_sha256"],
               "received_venue_lower_ms": lo, "received_venue_upper_ms": hi,
               "first_request": value["first_request"], "first_receipt": value["first_receipt"],
               "first_observation": value["first_observation"], "first_durable_availability": durable,
               "source_publication": value.get("source_publication")}
        return ref, req, raw

    @staticmethod
    def bounds(value: dict[str, Any], lower: str, upper: str) -> tuple[int, int]:
        lo, hi = (integer(value.get(key), key, minimum=1) for key in (lower, upper))
        check(0 <= hi - lo <= 300, "CLOCK_UNCERTAIN")
        return lo, hi

    def clock(self, snapshot: dict[str, Any], scan: int) -> tuple[int, int]:
        clock = obj(snapshot.get("clock"))
        cutoff = integer(clock.get("bar_cutoff_venue_ms"), "bar_cutoff", minimum=1)
        lo, hi = self.bounds(snapshot, "decision_venue_lower_ms", "decision_as_of_venue_ms")
        dur = integer(snapshot.get("durable_venue_upper_ms"), "durable_venue_upper_ms", minimum=1)
        check(cutoff <= lo <= hi and cutoff <= dur <= hi, "SOURCE_PUBLICATION_CLOCK")
        for label in ("first", "last", "reconciled"):
            point = obj(clock[label])
            a, z = self.bounds(point, "venue_lower_ms", "venue_upper_ms")
            check(point["uncertainty_ms"] == (z - a + 1) // 2, "CLOCK_UNCERTAIN")
            if label == "reconciled":
                continue
            ident = integer(clock.get(label + "_receipt_id"), "clock_receipt", minimum=1)
            meta, _, body = self.attempt(ident, TIME, scan)
            reported = integer(obj(body).get("serverTime"), "serverTime", minimum=1)
            elapsed = z - reported - 2
            chronological(meta["reserved"], meta["receipt"], snapshot["durable_availability"], snapshot["published"])
            check(0 <= elapsed <= meta["receipt"]["monotonic_ms"] - meta["reserved"]["monotonic_ms"],
                  "CLOCK_WITNESS_MISMATCH")
            check(a == reported - 1 and a <= reported <= z
                  and point["monotonic_ms"] == meta["receipt"]["monotonic_ms"]
                  and point["wall_ms"] == meta["receipt"]["wall_ms"], "CLOCK_WITNESS_MISMATCH")
        check(cutoff == clock["first"]["venue_lower_ms"], "CLOCK_CUTOFF_MISMATCH")
        first, last, rec = (clock[name] for name in ("first", "last", "reconciled"))
        rec_lo, rec_hi = rec["venue_lower_ms"], rec["venue_upper_ms"]
        span = last["monotonic_ms"] - first["monotonic_ms"]
        drift = (span + 999) // 1000
        check(span >= 0 and rec["monotonic_ms"] == last["monotonic_ms"]
              and last["venue_lower_ms"] <= rec_lo <= rec_hi <= last["venue_upper_ms"]
              and first["venue_lower_ms"] + span - drift <= rec_lo <= rec_hi <= first["venue_upper_ms"] + span + drift,
              "CLOCK_RECONCILIATION_MISMATCH")
        durable, output = snapshot["durable_availability"], snapshot["published"]
        chronological(durable, output)
        for key, point in (("durable", durable), ("published", output)):
            elapsed = point["monotonic_ms"] - rec["monotonic_ms"]
            drift = (elapsed + 999) // 1000
            projected_upper = dur if key == "durable" else hi
            check(elapsed >= 0 and rec_hi + elapsed <= projected_upper <= rec_hi + elapsed + drift
                  and (key == "durable" or rec_lo + elapsed - drift <= lo <= rec_lo + elapsed),
                  "SOURCE_PUBLICATION_CLOCK")
        return cutoff, hi

    def market(self, snapshot: dict[str, Any], symbol: str, evaluated: int | None) -> Market:
        scan = integer(snapshot.get("scan_id"), "scan_id", minimum=1)
        published, publication_hash, upper = self.publication(scan)
        check(published == snapshot, "SOURCE_PUBLICATION_MISMATCH")
        if upper is None:
            raise DecisionError("SOURCE_BLOCKED", str(obj(snapshot.get("issue") or {}).get("code", "NO_CLOCK")))
        as_of = upper if evaluated is None else evaluated
        check(upper <= as_of, "LATE_SOURCE_PUBLICATION")
        cutoff, published_time = self.clock(snapshot, scan)
        market = obj(obj(snapshot.get("markets")).get(symbol) or {})
        if not market.get("data_ready"):
            detail = market.get("issue") or {k: obj(v).get("status") for k, v in
                                             obj(market.get("context") or {}).items()
                                             if obj(v).get("status") != "CURRENT"}
            raise DecisionError("SYMBOL_INPUT_BLOCKED", json.dumps(detail, sort_keys=True))
        check(market.get("strategy_evaluated") is False and market.get("strategy_status") == "NOT_EVALUATED",
              "UNQUALIFIED_SOURCE_STATE")
        frames = obj(market.get("frames"))
        check(set(frames) == INTERVALS.keys(), "MISSING_FRAME")
        result = {frame: self.frame(symbol, frame, obj(frames[frame]), scan, cutoff, as_of) for frame in INTERVALS}
        inputs = obj(market.get("context"))
        check(set(inputs) == OBSERVATIONS.keys(), "MISSING_CONTEXT")
        context = {name: self.observation(symbol, name, obj(inputs[name]), scan, as_of) for name in OBSERVATIONS}
        for row in self.references.values():
            row["receipt_origin"] = self.origin
        initial = self.db.execute("SELECT scan_id FROM publications ORDER BY scan_id LIMIT 1").fetchone()
        check(initial is not None, "SOURCE_PUBLICATION_MISSING")
        _, initial_hash, _ = self.publication(initial[0])
        receipt = {"source_lineage": digest([self.origin, initial_hash]), "schema": RECEIPT, "adapter": ADAPTER, "source_origin": self.origin, "evidence": SYNTHETIC,
                   "source_scan_id": scan, "source_publication_sha256": publication_hash,
                   "source_published_venue_ms": published_time, "evaluation_venue_ms": as_of, "bar_cutoff_venue_ms": cutoff,
                   "source_clock": snapshot["clock"], "source_published": snapshot["published"],
                   "source_durable_availability": snapshot["durable_availability"],
                   "normalized_symbol_sha256": digest(market),
                   "raw_receipts": [self.references[k] for k in sorted(self.references)]}
        warm = all(len(result[frame]) >= count for frame, count in WARMUP.items())
        return Market(symbol, as_of, cutoff, receipt, result, context, warm)

    def frame(self, symbol: str, frame: str, value: dict[str, Any], scan: int, cutoff: int,
              as_of: int) -> tuple[Bar, ...]:
        rows = value.get("completed")
        if not isinstance(rows, list) or not 0 < len(rows) <= MAX_BARS:
            raise DecisionError("MISSING_COMPLETED_FRAME", frame)
        check(value.get("status") == "CURRENT", "STALE_FRAME", frame)
        width = INTERVALS[frame]
        result: list[Bar] = []
        raw_pages: dict[int, dict[int, tuple[n.Candle, str]]] = {}
        for raw in rows:
            item = obj(raw)
            lo = integer(item.get("open_ms"), "open_ms", minimum=1)
            hi = integer(item.get("end_ms_exclusive"), "end_ms_exclusive", minimum=1)
            check(item.get("finality") == "COMPLETE" and hi == lo + width and hi + CLOSE_GRACE_MS <= cutoff
                  and item.get("close_ms_inclusive") == hi - 1, "CANDLE_NOT_FINAL", frame)
            check(not result or result[-1].end_ms == lo, "CANDLE_GAP_OR_DUPLICATE", frame)
            ref, req, body = self.timing(item, KLINES, as_of, scan)
            p = req["params"]
            check(p.get("interval") == frame and p.get("symbol") == symbol, "CANDLE_ROUTE_BINDING")
            ident = ref["receipt_id"]
            if ident not in raw_pages:
                parsed = n.candles(body, frame, p["startTime"], p["endTime"])
                raw_pages[ident] = {c.open_ms: (c, raw_sha(b1_encode(r).encode()))
                                    for c, r in zip(parsed, body, strict=True)}
            match = raw_pages[ident].get(lo)
            if match is None:
                raise DecisionError("CANDLE_RAW_MISSING", frame)
            bar, raw_hash = match
            check(raw_hash == item.get("source_row_sha256")
                  and all(item.get(k) == v for k, v in normalized(bar.values()).items()), "CANDLE_RAW_MISMATCH", frame)
            rev = integer(item.get("revision"), "revision", minimum=1)
            original, _, _ = self.publication(ref["source_scan_id"])
            check(hi + CLOSE_GRACE_MS <= original["clock"]["bar_cutoff_venue_ms"], "SOURCE_CANDLE_NO_FINALITY")
            persisted = self.db.execute("SELECT data,version,hash FROM bars WHERE scan_id=? "
                                        "AND symbol=? AND frame=? AND open_ms=?",
                                        (ref["source_scan_id"], symbol, frame, lo)).fetchone()
            check(persisted is not None and persisted["version"] == rev and persisted["hash"] == raw_hash
                  and all(item.get(k) == v for k, v in json.loads(persisted["data"]).items()),
                  "CANDLE_DURABILITY_MISMATCH", frame)
            check(rev == 1 or isinstance(item.get("previous_revision_sha256"), str), "CANDLE_REVISION_UNBOUND")
            result.append(Bar(lo, hi, bar.open, bar.high, bar.low, bar.close, bar.base_volume,
                              {**ref, "revision": rev, "source_row_sha256": raw_hash,
                               "previous_receipt_id": item.get("previous_receipt_id")}))
        cutoff_end = (cutoff - CLOSE_GRACE_MS) // width * width
        check(result[-1].end_ms == cutoff_end == value.get("latest_completed_end_ms")
              and as_of - result[-1].end_ms <= width + CLOSE_GRACE_MS, "STALE_FRAME", frame)
        return tuple(result)

    def observation(self, symbol: str, name: str, value: dict[str, Any], scan: int, as_of: int) -> dict[str, Any]:
        route, freshness = OBSERVATIONS[name]
        ref, req, raw = self.timing(value, route, as_of, scan)
        params = req["params"]
        check(route == INSTRUMENTS or params.get("symbol") == symbol, "CONTEXT_SYMBOL_MISMATCH", name)
        parse: dict[str, Callable[[object, str], tuple[int, dict[str, object]]]] = {
            "ticker": n.ticker, "quote": n.quote, "oi": n.open_interest, "mark": n.mark,
        }
        if name == "instrument":
            event, data = None, n.exchange_info(raw, (symbol,))[0][symbol]
        elif name == "depth":
            event, data = n.depth(raw, params["limit"])
        elif name == "funding":
            event, data = funding_payload(raw, params)
        elif name == "oi_history":
            event, data = oi_payload(raw, symbol, params["limit"])
        else:
            event, data = parse[name](raw, symbol)
        check(event == value.get("source_event_ms") and normalized(data) == value.get("values"),
              "CONTEXT_RAW_MISMATCH", name)
        seen = ref["received_venue_lower_ms"] if event is None else event
        event_upper = data.get("event_ms", seen)
        check(type(event_upper) is int and event_upper <= min(as_of, ref["received_venue_upper_ms"]),
              "LATE_CONTEXT", name)
        check(value.get("status") == "CURRENT" and as_of - seen <= FRESHNESS[freshness],
              "CONTEXT_STALE_OR_PARTIAL", name)
        return {**ref, "source_event_ms": event, "age_upper_ms": as_of - seen, "values": normalized(data)}
