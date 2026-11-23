"""Bounded closed-bar bootstrap and overlap refresh under one egress lock."""

from __future__ import annotations

from pathlib import Path

from quant_personal_public_b1.clock import SystemClock
from quant_personal_public_b1.fixture import FixtureClock, FixtureTransport
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.runtime import checked_projection, run_identity
from quant_personal_public_b1.session import GlobalStop
from quant_personal_public_b1.store import sha

from . import normalize as norm
from .fixtures import usd_m_fixture
from .live import open_live
from .routes import (
    CONTRACT, DEPTH, FUNDING, FUNDING_LIMIT, FUNDING_WINDOW_MS, INSTRUMENTS, INTERVALS, KLINES,
    OI_HISTORY, OI_LIMIT, OI_PERIOD_MS, SYMBOLS, Request,
)
from .session import POLICY, Session
from .source import SCHEMA, Ledger, digest
from .transport import FIXTURE, GENUINE, LOOPBACK, WARNINGS, LoopbackHTTPS

WARM_BARS = 32
OVERLAP = 2
MAX_PAGE = 96


def completed_end(frame: str, cutoff: int) -> int:
    width = INTERVALS[frame]
    return (cutoff - POLICY.close_grace_ms) // width * width


def bar_window(session, symbol, frame, first):
    width = INTERVALS[frame]
    end = completed_end(frame, first.lower_ms)
    start = end - WARM_BARS * width
    ledger = session.ledger
    cache = ledger.tail(symbol, frame, start, end)
    if len(cache) == WARM_BARS:
        # Refresh only when a new completed candle arrives.
        return [cache[t] for t in range(start, end, width)], []
    if cache:
        fetch_start = max(start, max(cache) - (OVERLAP - 1) * width)
        if any(t not in cache for t in range(start, fetch_start, width)):
            fetch_start = start
    else:
        fetch_start = start
    params = {"symbol": symbol, "interval": frame, "startTime": fetch_start,
              "endTime": end - width, "limit": (end - fetch_start) // width}
    require(1 <= params["limit"] <= MAX_PAGE, "KLINE_CATCHUP_BOUND")
    got = session.get(KLINES, params)
    sent = checked_projection(first, got.sent, session.policy)
    require(end + POLICY.close_grace_ms <= sent.lower_ms, "KLINE_NOT_CLOSED_AT_REQUEST")
    receipt_hash = sha(ledger.store.raw(got.seq))
    updates = []
    for opened, (bar, row_sha) in norm.pages(Request(KLINES, params), got.body).items():
        previous = cache.get(opened)
        if previous and previous["source_row_sha256"] == row_sha:
            continue
        proof = norm.bar_ref(got.seq, session.scan, receipt_hash, bar, row_sha, previous)
        cache[opened] = proof
        updates.append((symbol, frame, proof))
    require(sorted(cache) == list(range(start, end, width)), "KLINE_WARMUP_WINDOW_GAP", frame)
    return [cache[t] for t in range(start, end, width)], updates


def observation_query(name, symbol, cutoff):
    route = norm.OBSERVATIONS[name]
    params = {"symbol": symbol}
    if route == INSTRUMENTS:
        params = {}
    elif route == DEPTH:
        params["limit"] = 5
    elif route == FUNDING:
        params.update(startTime=cutoff - FUNDING_WINDOW_MS, endTime=cutoff, limit=FUNDING_LIMIT)
    elif route == OI_HISTORY:
        end = cutoff
        params.update(startTime=end - OI_LIMIT * OI_PERIOD_MS + 1, endTime=end, limit=OI_LIMIT, period="5m")
    return Request(route, params)


def read_observations(session, symbol, first, previous, meta):
    records = {}
    for name, route in norm.OBSERVATIONS.items():
        prior = previous.get(name)
        if prior and name in norm.REFRESH_MS:
            recent = first.upper_ms - prior["received_venue_lower_ms"] <= norm.REFRESH_MS[name]
            try:
                norm.validate_age(name, prior, first.upper_ms)
            except SourceBlocked:
                recent = False
            if recent and (name != "instrument" or meta is None):
                records[name] = prior
                continue
        request = observation_query(name, symbol, first.lower_ms)
        got = meta if route == INSTRUMENTS else session.request(request)
        require(got is not None, "METADATA_RECEIPT_REQUIRED")
        seen = checked_projection(first, got.received, session.policy)
        raw_sha = sha(session.ledger.store.raw(got.seq))
        ref, _ = norm.observation_ref(got.seq, session.scan, raw_sha, request, got.body, symbol, seen)
        records[name] = ref
    return records


class Collector:
    def __init__(self, path: Path, transport, clock=None, identity=None, *, origin: str = FIXTURE):
        if origin == GENUINE:
            open_live()
        require((origin == LOOPBACK and type(transport) is LoopbackHTTPS)
                or (origin == FIXTURE and type(transport) is FixtureTransport), "UNQUALIFIED_TRANSPORT")
        self.ledger = Ledger(path, origin, create=True)
        self.transport = transport
        self.clock = clock or SystemClock()
        self.identity = identity or run_identity()

    @classmethod
    def fixture(cls, path: Path, clock: FixtureClock, transport: FixtureTransport | None = None, identity=None):
        return cls(path, transport or FixtureTransport(clock, mutate=usd_m_fixture), clock, identity)

    def scan(self, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), *, after_stage=None):
        require(bool(symbols) and set(symbols) <= SYMBOLS and len(set(symbols)) == len(symbols), "UNQUALIFIED_SYMBOL")
        with self.ledger.store.collector():
            return self._collect(symbols, after_stage)

    def _collect(self, symbols, after_stage):
        started = self.clock.sample()
        scan = self.ledger.start(self.identity.stamp(started))
        session = Session(scan, self.clock, self.identity, self.transport, self.ledger, started)
        stage = {"markets": {}, "issue": None, "clock": None, "symbols": list(symbols)}
        updates = []
        reference = None
        try:
            first, first_id = session.witness()
            previous = {symbol: self.ledger.prior_observations(symbol) for symbol in symbols}
            need_meta = any("instrument" not in old
                            or first.upper_ms - old["instrument"]["received_venue_lower_ms"]
                            > norm.REFRESH_MS["instrument"] for old in previous.values())
            meta = session.get(INSTRUMENTS, {}) if need_meta else None
            if meta:
                session.budget.configure(norm.venue_limits(meta.body))
            staged_updates = {}
            # Complete the slower bar reads first; then fetch fast observations per symbol.
            for symbol in symbols:
                data = stage["markets"][symbol] = {"frames": {}, "observations": {}, "issue": None}
                staged_updates[symbol] = []
                for frame in INTERVALS:
                    try:
                        rows, edits = bar_window(session, symbol, frame, first)
                        data["frames"][frame] = rows
                        staged_updates[symbol].extend(edits)
                    except GlobalStop:
                        raise
                    except SourceBlocked as exc:
                        data["issue"] = {"code": exc.code, "detail": frame}
                        break
            for symbol, data in stage["markets"].items():
                if data["issue"]:
                    continue
                try:
                    data["observations"] = read_observations(session, symbol, first, previous[symbol], meta)
                except GlobalStop:
                    raise
                except SourceBlocked as exc:
                    data["issue"] = {"code": exc.code, "detail": exc.detail}
            last, last_id = session.witness()
            reference = first.reconcile(last, POLICY)
            stage["clock"] = {"first_id": first_id, "last_id": last_id, "first": first.evidence(),
                              "last": last.evidence(), "reconciled": reference.evidence()}
            session.check_budget()
            cut = reference.upper_ms
            for symbol, data in stage["markets"].items():
                if data["issue"]:
                    continue
                try:
                    for name, ref in data["observations"].items():
                        norm.validate_age(name, ref, cut)
                    updates.extend(staged_updates[symbol])
                except SourceBlocked as exc:
                    data["issue"] = {"code": exc.code, "detail": exc.detail}
        except SourceBlocked as exc:
            stage.update(issue={"code": exc.code, "detail": exc.detail}, markets={})
            reference, updates = None, []
        stage_stamp = self.clock.sample()
        if reference is not None:
            session.time_left(stage_stamp)
        self.ledger.store.stage(scan, stage, updates)
        committed = self.clock.sample()
        if after_stage is not None:
            after_stage()
        published = self.clock.sample()
        if reference is not None:
            session.time_left(published)
        durable = checked_projection(reference, committed, POLICY) if reference else None
        visible = checked_projection(reference, published, POLICY) if reference else None
        payload = {"schema": SCHEMA, "origin": self.ledger.origin, "warnings": list(WARNINGS),
                   "lineage": self.ledger.lineage, "contract": CONTRACT, "scan_id": scan,
                   "stage_sha256": digest(stage), "stage": stage,
                   "stage_start": self.identity.stamp(stage_stamp).data(),
                   "commit_observed": self.identity.stamp(committed).data(),
                   "publication_started": self.identity.stamp(published).data(),
                   "durable_venue_upper_ms": durable.upper_ms if durable else None,
                   "visible_venue_upper_ms": visible.upper_ms if visible else None}
        self.ledger.store.publish(scan, payload, self.identity.stamp(published), payload["visible_venue_upper_ms"])
        observed = self.clock.sample()
        if reference is not None:
            session.time_left(observed)
        upper = checked_projection(reference, observed, POLICY).upper_ms if reference else None
        self.ledger.record_visibility(scan, self.identity.stamp(observed), upper)
        return self.ledger.publication(scan)[0]
