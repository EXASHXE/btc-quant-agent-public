"""Read B4 publications through raw receipts before constructing a B2 Market."""

from __future__ import annotations

import ipaddress
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quant_personal_decision_b2.model import Bar, DecisionError, Market, integer
from quant_personal_public_b1.clock import Sample, VenueTime, check_elapsed
from quant_personal_public_b1.normalize import obj
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.store import encode, sha
from quant_personal_public_b1.wire import HOST, json_body

from . import normalize as norm
from .collector import WARM_BARS, completed_end
from .live import open_live
from .routes import CONTRACT, INTERVALS, KLINES, SYMBOLS, TIME, Request
from .session import POLICY
from .source import RECEIPT, Ledger, digest
from .transport import FIXTURE, GENUINE, LOOPBACK, WARNINGS

ADAPTER = "B4_TO_B2_CAUSAL_ADAPTER_V1"
HEX_SHA = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Attempt:
    seq: int
    scan: int
    request: Request
    raw: object
    proof: dict


def ms(stamp: dict) -> Sample:
    return Sample(integer(stamp["wall_ms"], "wall_ms", minimum=1),
                  integer(stamp["monotonic_ms"], "monotonic_ms"))


def chronology(*stamps: dict) -> None:
    first = stamps[0]
    require(isinstance(first.get("boot"), str) and bool(first["boot"])
            and isinstance(first.get("session"), str) and bool(first["session"]), "SOURCE_CLOCK_DOMAIN")
    for prior, after in zip(stamps, stamps[1:]):
        require((first["boot"], first["session"]) == (after["boot"], after["session"]), "SOURCE_CLOCK_DOMAIN")
        check_elapsed(ms(prior), ms(after), POLICY)


def project(bracket: VenueTime, stamp: dict) -> VenueTime:
    projected = bracket.projected(ms(stamp), POLICY)
    projected.check_width(POLICY)
    return projected


class Reader:
    def __init__(self, ledger: Ledger, db: sqlite3.Connection):
        self.ledger, self.db = ledger, db
        self.attempts: dict[int, Attempt] = {}
        self.publications: dict[int, tuple[dict, str, VenueTime]] = {}
        self.pages: dict[int, dict] = {}
        self.used: dict[int, dict] = {}

    def attempt(self, ident, scan, route) -> Attempt:
        integer(ident, "receipt", minimum=1)
        if ident not in self.attempts:
            row = self.db.execute(
                """SELECT a.*,x.stamp AS sent,s.starting FROM attempts a
                   JOIN b4_sends x ON x.attempt=a.id JOIN scans s ON s.id=a.scan_id
                   WHERE a.id=?""", (ident,),
            ).fetchone()
            require(row is not None and row["raw"] is not None and row["response"] is not None,
                    "SOURCE_RECEIPT_MISSING")
            raw, reply = row["raw"], json.loads(row["response"])
            require(len(raw) <= POLICY.max_body_bytes and reply["status"] == 200
                    and reply["body_sha256"] == sha(raw)
                    and reply["headers"].get("content-type", "").split(";", 1)[0].strip().lower()
                    == "application/json" and not reply["error"], "SOURCE_RAW_DIGEST_OR_STATUS")
            if row["encoded"] is not None:
                require(sha(row["encoded"]) == reply["encoded_sha256"], "SOURCE_ENCODED_DIGEST")
            else:
                require(reply["encoded_sha256"] is None, "SOURCE_ENCODED_DIGEST")
            req = Request(row["route"], **json.loads(row["request"]))
            require(req.validate()[0] == row["weight"] and row["egress"] == self.ledger.store.egress,
                    "SOURCE_REQUEST_BINDING")
            proof = reply["tls"]
            if self.ledger.origin == LOOPBACK:
                require(proof is not None and ipaddress.ip_address(proof["peer"]).is_loopback
                        and proof["sni"] == HOST and proof["protocol"] in {"TLSv1.2", "TLSv1.3"}
                        and HEX_SHA.fullmatch(proof["certificate_sha256"])
                        and proof["verification"] == "CERT_REQUIRED_AND_HOSTNAME", "SOURCE_TLS_ORIGIN")
            else:
                require(proof is None, "SOURCE_FIXTURE_ORIGIN")
            start, reserved, sent, received = (json.loads(row["starting"]), json.loads(row["reserved"]),
                                               json.loads(row["sent"]), reply["receipt"])
            chronology(start, reserved, sent, received)
            require(ms(received).mono_ms - ms(sent).mono_ms <= POLICY.request_timeout_ms,
                    "SOURCE_REQUEST_DEADLINE")
            meta = {"schema": RECEIPT, "receipt_id": ident, "source_scan_id": row["scan_id"],
                    "origin": self.ledger.origin, "route": row["route"], "request": req.data(),
                    "raw_sha256": reply["body_sha256"], "reply_headers": reply["headers"],
                    "reservation": reserved, "request_start": sent, "receive": received, "tls": proof}
            self.attempts[ident] = Attempt(ident, row["scan_id"], req, json_body(raw), meta)
        result = self.attempts[ident]
        require((result.scan, result.request.route) == (scan, route), "SOURCE_RECEIPT_BINDING")
        return result

    def publication(self, scan) -> tuple[dict, str, VenueTime]:
        if scan not in self.publications:
            found = self.ledger.publication(scan, db=self.db)
            require(found is not None, "SOURCE_PUBLICATION_MISSING")
            data, publication_sha = found
            stage = data["stage"]
            require(not stage["issue"] and data["visible_venue_upper_ms"] is not None,
                    "SOURCE_RUN_BLOCKED", str(stage.get("issue")))
            clock = stage["clock"]
            points = []
            witnesses = []
            for name in ("first", "last"):
                receipt = self.attempt(clock[name + "_id"], scan, TIME)
                seen = receipt.proof
                venue = integer(obj(receipt.raw).get("serverTime"), "serverTime", minimum=1)
                require(abs(venue - ms(seen["receive"]).wall_ms) <= 300_000, "VENUE_CLOCK_OFFSET_UNBOUNDED")
                point = VenueTime.bracket(ms(seen["request_start"]), ms(seen["receive"]), venue, POLICY)
                require(point.evidence() == clock[name], "SOURCE_CLOCK_DIGEST")
                points.append(point)
                witnesses.append(receipt)
            require(witnesses[0].seq < witnesses[1].seq, "CLOCK_WITNESS_ORDER")
            first, last = points
            ref = first.reconcile(last, POLICY)
            require(ref.evidence() == clock["reconciled"], "SOURCE_CLOCK_DIGEST")
            chronology(witnesses[0].proof["receive"], witnesses[1].proof["request_start"],
                       witnesses[1].proof["receive"], data["stage_start"], data["commit_observed"],
                       data["publication_started"], data["published"])
            require(project(ref, data["commit_observed"]).upper_ms == data["durable_venue_upper_ms"]
                    and project(ref, data["published"]).upper_ms == data["visible_venue_upper_ms"],
                    "SOURCE_CLOCK_PUBLICATION_BINDING")
            self.publications[scan] = data, publication_sha, first
        data, publication_sha, first = self.publications[scan]
        for key in ("first_id", "last_id"):
            ident = data["stage"]["clock"][key]
            self.used[ident] = self.attempts[ident].proof
        return data, publication_sha, first

    def timing(self, ref, route, scan, as_of):
        original_scan = integer(ref["source_scan_id"], "source_scan_id", minimum=1)
        require(original_scan <= scan, "LATE_SOURCE_SCAN")
        own, publication_sha, first = self.publication(original_scan)
        visible = own["visible_venue_upper_ms"]
        require(visible <= as_of, "LATE_SOURCE_PUBLICATION")
        got = self.attempt(ref["receipt_id"], original_scan, route)
        require(own["stage"]["clock"]["first_id"] < got.seq < own["stage"]["clock"]["last_id"],
                "SOURCE_RECEIPT_OUTSIDE_CLOCK_BRACKET")
        first_receipt = self.attempts[own["stage"]["clock"]["first_id"]]
        chronology(first_receipt.proof["receive"], got.proof["request_start"], got.proof["receive"], own["stage_start"])
        started = project(first, got.proof["request_start"])
        seen = project(first, got.proof["receive"])
        require(got.proof["raw_sha256"] == ref["raw_sha256"]
                and seen.upper_ms <= own["durable_venue_upper_ms"], "RECEIPT_PUBLICATION_BINDING")
        proof = {**got.proof, "source_publication_sha256": publication_sha,
                 "first_durable_availability": own["commit_observed"],
                 "first_eligible_venue_ms": visible, "first_local_publication": own["published"],
                 "received_venue_lower_ms": seen.lower_ms, "received_venue_upper_ms": seen.upper_ms}
        self.used[got.seq] = proof
        return got, started, seen, proof, first

    def frame(self, symbol, frame, refs, scan, cutoff, as_of):
        width = INTERVALS[frame]
        end = completed_end(frame, cutoff)
        expected = range(end - WARM_BARS * width, end, width)
        require(isinstance(refs, list) and len(refs) == WARM_BARS, "CANDLE_WINDOW_INCOMPLETE", frame)
        require(0 <= as_of - end <= width + POLICY.close_grace_ms, "STALE_CANDLE_WINDOW", frame)
        out = []
        for opened, ref in zip(expected, refs, strict=True):
            got, started, _, proof, first = self.timing(ref, KLINES, scan, as_of)
            p = got.request.params
            require(p["symbol"] == symbol and p["interval"] == frame, "SOURCE_CANDLE_ROUTE_BINDING")
            if got.seq not in self.pages:
                self.pages[got.seq] = norm.pages(got.request, got.raw)
            parsed = self.pages[got.seq].get(opened)
            require(parsed is not None and opened == ref["open_ms"], "SOURCE_CANDLE_RAW_MISSING")
            candle, row_sha = parsed
            require(candle.end_ms_exclusive + POLICY.close_grace_ms <= min(first.lower_ms, started.lower_ms, cutoff),
                    "SOURCE_CANDLE_NOT_FINAL")
            archived = self.db.execute(
                """SELECT b.hash,b.version,b.data FROM bars b JOIN b4_visibility p ON p.scan_id=b.scan_id
                   WHERE b.symbol=? AND b.frame=? AND b.open_ms=? AND b.scan_id<=?
                     AND p.upper_ms IS NOT NULL
                   ORDER BY b.scan_id DESC LIMIT 2""", (symbol, frame, opened, got.scan),
            ).fetchall()
            previous = json.loads(archived[1]["data"]) if len(archived) > 1 else None
            rebuilt = norm.bar_ref(got.seq, got.scan, proof["raw_sha256"], candle, row_sha, previous)
            require(rebuilt == ref and archived and archived[0]["version"] == rebuilt["revision"]
                    and archived[0]["hash"] == row_sha and json.loads(archived[0]["data"]) == rebuilt,
                    "SOURCE_CANDLE_DIGEST_OR_REVISION")
            newest = self.db.execute(
                """SELECT MAX(b.scan_id) FROM bars b JOIN b4_visibility p ON p.scan_id=b.scan_id
                   WHERE b.symbol=? AND b.frame=? AND b.open_ms=? AND b.scan_id<=?
                     AND p.upper_ms IS NOT NULL""", (symbol, frame, opened, scan),
            ).fetchone()[0]
            require(newest == got.scan, "SOURCE_CANDLE_REVISION_SUPERSEDED")
            out.append(Bar(opened, candle.end_ms_exclusive, candle.open, candle.high, candle.low, candle.close,
                           candle.base_volume, {**proof, **rebuilt}))
        return tuple(out)

    def market(self, symbol, scan, requested_as_of, publication_sha=None):
        data, actual_sha, first = self.publication(scan)
        require(publication_sha is None or publication_sha == actual_sha, "PUBLICATION_DIGEST_MISMATCH")
        visible = data["visible_venue_upper_ms"]
        as_of = visible if requested_as_of is None else requested_as_of
        require(as_of >= visible, "LATE_SOURCE_PUBLICATION")
        if as_of > visible:
            newer = self.db.execute(
                """SELECT 1 FROM b4_visibility v JOIN publications p ON p.scan_id=v.scan_id
                   WHERE v.scan_id>? AND (v.upper_ms IS NULL OR (v.upper_ms<=? AND
                      json_type(p.payload,?) IS NOT NULL)) LIMIT 1""",
                (scan, as_of, f"$.stage.markets.{symbol}"),
            ).fetchone()
            require(newer is None, "SOURCE_PUBLICATION_SUPERSEDED")
        market = data["stage"]["markets"].get(symbol)
        require(market is not None and not market["issue"], "SYMBOL_INPUT_BLOCKED",
                str(market.get("issue") if market else None))
        frames = market["frames"]
        require(frames.keys() == INTERVALS.keys(), "MISSING_FRAME")
        result = {name: self.frame(symbol, name, rows, scan, first.lower_ms, as_of) for name, rows in frames.items()}
        refs = market["observations"]
        require(refs.keys() == norm.OBSERVATIONS.keys(), "MISSING_CONTEXT")
        context = {}
        for name, route in norm.OBSERVATIONS.items():
            ref = refs[name]
            got, _, seen, proof, _ = self.timing(ref, route, scan, as_of)
            original, _, _ = self.publication(got.scan)
            require(original["stage"]["markets"][symbol]["observations"].get(name) == ref,
                    "CONTEXT_FIRST_PUBLICATION_BINDING")
            rebuilt, values = norm.observation_ref(got.seq, got.scan, proof["raw_sha256"], got.request,
                                                     got.raw, symbol, seen)
            require(rebuilt == ref, "SOURCE_CONTEXT_DIGEST")
            norm.validate_age(name, rebuilt, as_of)
            relevant = rebuilt["source_event_ms"]
            if relevant is None:
                relevant = rebuilt["received_venue_lower_ms"]
            context[name] = {**proof, **rebuilt, "age_upper_ms": as_of - relevant, "values": json.loads(encode(values))}
        norm.coherent(context)
        proof = {"schema": RECEIPT, "adapter": ADAPTER, "source_origin": self.ledger.origin,
                 "source_lineage": digest([self.ledger.origin, self.ledger.lineage]), "warnings": list(WARNINGS),
                 "evidence": WARNINGS[0], "contract": CONTRACT, "source_scan_id": scan,
                 "source_publication_sha256": actual_sha, "source_published_venue_ms": visible,
                 "evaluation_venue_ms": as_of, "bar_cutoff_venue_ms": first.lower_ms,
                 "source_clock": data["stage"]["clock"], "source_published": data["published"],
                 "source_durable_availability": data["commit_observed"],
                 "normalized_symbol_sha256": digest(market),
                 "raw_receipts": [self.used[k] for k in sorted(self.used)]}
        return Market(symbol, as_of, first.lower_ms, proof, result, context, True)


class MarketAdapter:
    def __init__(self, path: Path, origin: str = FIXTURE):
        if origin == GENUINE:
            open_live()
        try:
            self.ledger = Ledger(path, origin)
        except (SourceBlocked, sqlite3.Error, OSError) as exc:
            raise DecisionError("UNQUALIFIED_SOURCE_LEDGER", str(exc)) from exc

    def read(self, symbol, *, scan=None, as_of_ms=None, publication_sha=None):
        if symbol not in SYMBOLS:
            raise DecisionError("UNQUALIFIED_SYMBOL", str(symbol))
        if scan is not None:
            integer(scan, "scan", minimum=1)
        if as_of_ms is not None:
            integer(as_of_ms, "as_of_ms", minimum=1)
        try:
            with self.ledger.store.connect() as db:
                db.execute("BEGIN")
                if scan is None:
                    latest = self.ledger.publication(db=db)
                    require(latest is not None, "NO_DURABLE_PUBLICATION_AS_OF")
                    require(latest[0]["visible_venue_upper_ms"] is not None, "LATEST_SOURCE_RUN_BLOCKED")
                found = self.ledger.publication(scan, as_of_ms if scan is None else None, db=db)
                require(found is not None, "NO_DURABLE_PUBLICATION_AS_OF")
                return Reader(self.ledger, db).market(symbol, found[0]["scan_id"], as_of_ms, publication_sha)
        except SourceBlocked as exc:
            raise DecisionError(exc.code, exc.detail) from exc
        except (sqlite3.Error, KeyError, TypeError, AttributeError, ValueError, RecursionError, OverflowError) as exc:
            if isinstance(exc, DecisionError):
                raise
            raise DecisionError("SOURCE_EVIDENCE_INVALID", type(exc).__name__) from exc

    def rejected_reference(self, *, scan, as_of_ms):
        try:
            found = self.ledger.publication(scan, as_of_ms if scan is None else None)
            if found:
                publication, sha = found
                return {"source_origin": self.ledger.origin, "source_scan_id": publication["scan_id"],
                        "source_publication_sha256": sha, "usable_for_evaluation": False}
        except (ValueError, sqlite3.Error, KeyError, TypeError):
            pass
        return None
