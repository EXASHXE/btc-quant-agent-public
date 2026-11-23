"""Explicit offline composition and the causal PERSONAL_MVP V2 market view."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import normalize as n
from .budget import Budget
from .clock import Clock, Sample, SystemClock, VenueTime
from .compat import funding_payload, funding_query, oi_payload
from .fixture import FixtureClock, FixtureTransport
from .policy import (
    DEPTH,
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
    WEIGHTS_VERSION,
    Policy,
    SourceBlocked,
    require,
)
from .session import GlobalStop, RunIdentity, Session
from .store import Store, encode, sha
from .wire import FIXTURE, LOOPBACK, HttpsTransport, Receipt, Transport, json_body

SCHEMA = "PERSONAL_PUBLIC_MARKET_SNAPSHOT_V2"
FEATURES: tuple[dict[str, Any], ...] = (
    {"indicator": "ATR14", "interval": "1h", "completed_bars": 15},
    {"indicator": "EMA30", "interval": "1h", "completed_bars": 30},
)
SLOW_REFRESH_MS = {"instrument": 20_000, "ticker": 20_000, "oi_history": 120_000, "funding": 900_000}
FRESHNESS_KEYS = {
    "instrument": "instrument", "ticker": "ticker", "quote": "book_ticker", "depth": "depth",
    "oi": "open_interest", "oi_history": "open_interest_history", "funding": "funding_history", "mark": "mark_funding",
}
ACCOUNT = {"account_context_status": "UNAVAILABLE",
           "human_actionability": "Manually verify real exposure and protective orders."}


@dataclass(frozen=True)
class Config:
    policy: Policy = field(default_factory=Policy)
    page_rows: int = 96
    max_kline_pages: int = 8

    def __post_init__(self) -> None:
        if not (type(self.page_rows) is int and 1 <= self.page_rows <= self.policy.kline_limit
                and type(self.max_kline_pages) is int and 1 <= self.max_kline_pages <= 32):
            raise ValueError("invalid pagination bounds")


DEFAULT_CONFIG = Config()


def boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() or uuid.uuid4().hex
    except OSError:
        return uuid.uuid4().hex


def run_identity() -> RunIdentity:
    return RunIdentity(boot_id(), uuid.uuid4().hex)


def initial_snapshot(origin: str, scan: int, symbols: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema": SCHEMA, "source_origin": origin, "evidence_class": "PERSONAL_PUBLIC_MARKET", "scan_id": scan,
        "data_ready": False, "feature_warmup_ready": False, "strategy_evaluated": False,
        "strategy_status": "NOT_EVALUATED", "source_status": "SOURCE_BLOCKED", **ACCOUNT,
        "symbols": list(symbols), "frame_order": list(INTERVALS), "markets": {}, "clock": {}, "issue": None,
        "feature_dependencies": list(FEATURES), "endpoint_contract": WEIGHTS_VERSION,
    }


def issue(exc: SourceBlocked) -> dict[str, str]:
    return {"code": exc.code, "detail": exc.detail}


def checked_projection(reference: VenueTime, sample: Sample, policy: Policy) -> VenueTime:
    point = reference.projected(sample, policy)
    try:
        point.check_width(policy)
    except SourceBlocked as exc:
        raise GlobalStop(exc.code) from exc
    return point


def received_record(receipt: Receipt, session: Session, reference: VenueTime) -> dict[str, Any]:
    seen = checked_projection(reference, receipt.received, session.policy)
    return {
        "receipt_id": receipt.seq, "source_scan_id": session.scan,
        "first_request": session.identity.stamp(receipt.sent).data(),
        "first_receipt": session.identity.stamp(receipt.received).data(),
        "first_observation": session.identity.stamp(session.clock.sample()).data(),
        "received_venue_lower_ms": seen.lower_ms, "received_venue_upper_ms": seen.upper_ms,
        "source_publication": "UNKNOWN",
    }


def collect_bars(session: Session, store: Store, config: Config, symbol: str,
                 frame: str, reference: VenueTime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    policy = config.policy
    width = INTERVALS[frame]
    cutoff = reference.lower_ms
    last_complete_end = (cutoff - policy.close_grace_ms) // width * width
    earliest_needed = last_complete_end - policy.history_bars * width
    last_open = cutoff // width * width
    tail = store.tail(symbol, frame, max(policy.history_bars, policy.revision_overlap))
    previous = {obj["open_ms"]: obj for obj in tail}
    closed = dict(previous)
    context = []
    start = earliest_needed
    if tail:
        require(tail[-1]["end_ms_exclusive"] <= last_complete_end, "CACHE_AHEAD_OF_SCAN", frame)
        overlap = tail[-policy.revision_overlap:][0]["open_ms"]
        start = overlap if earliest_needed >= tail[0]["open_ms"] else min(earliest_needed, overlap)
    count = (last_open - start) // width + 1
    require(start >= 0 and count <= config.max_kline_pages * config.page_rows, "KLINE_CATCHUP_BOUND", frame)
    updates = []
    for page_start in range(start, last_open + 1, width * config.page_rows):
        page_end = min(last_open, page_start + width * (config.page_rows - 1))
        receipt = session.get(KLINES, {"symbol": symbol, "interval": frame, "startTime": page_start,
                                      "endTime": page_end, "limit": (page_end - page_start) // width + 1})
        proof = received_record(receipt, session, reference)
        sent = checked_projection(reference, receipt.sent, policy)
        parsed = n.candles(receipt.body, frame, page_start, page_end)
        for candle, raw in zip(parsed, n.rows(receipt.body), strict=True):
            require(candle.open_ms <= proof["received_venue_upper_ms"], "KLINE_FUTURE_OPEN", frame)
            digest = sha(encode(raw).encode())
            existing = previous.get(candle.open_ms)
            value = {**candle.values(), **proof, "source_event_ms": None, "source_row_sha256": digest}
            if candle.end_ms_exclusive + policy.close_grace_ms > min(cutoff, sent.lower_ms):
                finality = ("FORMING" if candle.end_ms_exclusive > proof["received_venue_upper_ms"] else "CLOSE_UNCONFIRMED")
                context.append({**value, "finality": finality})
            elif not existing or digest != existing["source_row_sha256"]:
                value.update(finality="COMPLETE", revision=1 if not existing else existing["revision"] + 1,
                             previous_revision_sha256=None if not existing else existing["source_row_sha256"],
                             previous_receipt_id=None if not existing else existing["receipt_id"])
                closed[candle.open_ms] = value
                updates.append(value)
    keys = range(earliest_needed, last_complete_end, width)
    require(all(stamp in closed for stamp in keys), "KLINE_WARMUP_WINDOW_GAP", frame)
    return {"completed": [closed[stamp] for stamp in keys], "context": context,
            "latest_completed_end_ms": last_complete_end}, updates


def fetch_observation(name: str, session: Session, first: VenueTime, symbol: str) -> dict[str, Any]:
    policy = session.policy
    spec: dict[str, tuple[str, dict[str, str | int]]] = {
        "ticker": (TICKER, {"symbol": symbol}), "quote": (QUOTE, {"symbol": symbol}),
        "depth": (DEPTH, {"symbol": symbol, "limit": policy.depth_limit}), "oi": (OI, {"symbol": symbol}),
        "oi_history": (OI_HISTORY, {"symbol": symbol, "period": "5m", "limit": policy.history_limit}),
        "funding": (FUNDING, funding_query(symbol, first.lower_ms)), "mark": (MARK, {"symbol": symbol}),
    }
    route, params = spec[name]
    receipt = session.get(route, params)
    event: int | None
    if name == "depth":
        event, values = n.depth(receipt.body, policy.depth_limit)
    elif name == "oi_history":
        event, values = oi_payload(receipt.body, symbol, policy.history_limit)
    elif name == "funding":
        event, values = funding_payload(receipt.body, params)
    else:
        normalize = {"ticker": n.ticker, "quote": n.quote, "oi": n.open_interest, "mark": n.mark}[name]
        event, values = normalize(receipt.body, symbol)
    return {"source_event_ms": event, "values": values, **received_record(receipt, session, first)}


def reusable(record: dict[str, Any], name: str, cutoff: int) -> bool:
    return (name in SLOW_REFRESH_MS and isinstance(record.get("received_venue_lower_ms"), int)
            and record["received_venue_upper_ms"] <= cutoff
            and cutoff - record["received_venue_lower_ms"] < SLOW_REFRESH_MS[name])


def observation_status(name: str, record: dict[str, Any], upper: int, lower: int, policy: Policy) -> tuple[str, int | None]:
    event = record["source_event_ms"]
    latest_event = record["values"].get("event_ms", event) if name == "depth" else event
    if latest_event is not None and latest_event > record["received_venue_upper_ms"]:
        return "FUTURE_EVENT", None
    if record["received_venue_upper_ms"] > upper or (latest_event is not None and latest_event > lower):
        return "TIME_UNCERTAIN", None
    freshness = record["received_venue_lower_ms"] if name == "instrument" else event
    if freshness is None:
        return "MISSING", None
    age = max(0, upper - freshness)
    status = "STALE" if age > policy.freshness_ms[FRESHNESS_KEYS[name]] else "CURRENT"
    if status == "CURRENT" and name == "depth" and record["values"]["short_side"]:
        status = "PARTIAL"
    return status, age


class Runtime:
    """Construct through the explicit fixture or loopback composition. Genuine mode is dormant."""

    def __init__(self, store: Store, transport: Transport, clock: Clock, identity: RunIdentity, config: Config) -> None:
        valid = ((store.origin == FIXTURE and type(transport) is FixtureTransport)
                 or (store.origin == LOOPBACK and type(transport) is HttpsTransport))
        require(valid and store.origin == transport.origin, "COMPOSITION_ORIGIN_MISMATCH")
        self.store, self.transport, self.clock, self.identity, self.config = store, transport, clock, identity, config
        self.budget = Budget(store, bootstrap=config.policy.bootstrap_weight_limit)

    @classmethod
    def fixtures(cls, path: Path, clock: FixtureClock, transport: FixtureTransport | None = None,
                 *, identity: RunIdentity | None = None, config: Config = DEFAULT_CONFIG) -> Runtime:
        require(transport is None or isinstance(transport, FixtureTransport), "FIXTURE_TRANSPORT_REQUIRED")
        require(transport is None or transport.clock is clock, "FIXTURE_CLOCK_MISMATCH")
        return cls(Store(path, FIXTURE, "fixture-local", create=True), transport or FixtureTransport(clock),
                   clock, identity or run_identity(), config)

    @classmethod
    def loopback(cls, path: Path, transport: HttpsTransport, *, clock: Clock | None = None,
                 identity: RunIdentity | None = None, config: Config = DEFAULT_CONFIG) -> Runtime:
        require(isinstance(transport, HttpsTransport), "LOOPBACK_HTTPS_REQUIRED")
        transport.target.validate()
        return cls(Store(path, LOOPBACK, "loopback-qa", create=True), transport,
                   clock or SystemClock(), identity or run_identity(), config)

    def scan(self, symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")) -> dict[str, Any]:
        require(bool(symbols) and set(symbols) <= SYMBOLS and len(set(symbols)) == len(symbols), "INVALID_SCAN_SYMBOLS")
        with self.store.collector():
            started = self.clock.sample()
            scan = self.store.start(self.identity.stamp(started))
            session = Session(scan, self.clock, self.identity, self.transport, self.budget, self.config.policy, started)
            output = initial_snapshot(self.store.origin, scan, symbols)
            entries: list[tuple[str, str, dict[str, Any]]] = []
            final = None
            first = None
            try:
                first, receipt = session.witness()
                output["clock"] = {"first": first.evidence(), "first_receipt_id": receipt}
                markets, meta, entries = self.collect(session, first, symbols)
                last, last_id = session.witness()
                output["clock"].update(last=last.evidence(), last_receipt_id=last_id)
                final = first.reconcile(last, self.config.policy)
                final.check_width(self.config.policy)
                previous_venue = self.store.last_venue_upper()
                require(previous_venue is None or final.upper_ms >= previous_venue, "VENUE_TIME_REGRESSION")
                output["clock"].update(reconciled=final.evidence(), bar_cutoff_venue_ms=first.lower_ms)
                output["markets"], output["metadata_cache"] = markets, meta
            except SourceBlocked as exc:
                final = None
                entries = []
                output["issue"] = issue(exc)
            output["request_count"], output["request_weight"] = session.count, session.weight
            self.store.stage(scan, output, entries)
            durable = self.clock.sample()
            proposed = self.clock.sample()
            upper = None
            if final is not None:
                try:
                    session.time_left(proposed)
                    decision = final.projected(proposed, self.config.policy)
                    decision.check_width(self.config.policy)
                    durable_bounds = final.projected(durable, self.config.policy)
                    output["durable_venue_upper_ms"] = durable_bounds.upper_ms
                    output["decision_as_of_venue_ms"] = decision.upper_ms
                    output["decision_venue_lower_ms"] = decision.lower_ms
                    self.finish_markets(output, decision, self.identity.stamp(durable).data())
                    upper = decision.upper_ms
                except SourceBlocked as exc:
                    output["issue"], output["markets"] = issue(exc), {}
            output["durable_availability"] = self.identity.stamp(durable).data()
            output["published"] = self.identity.stamp(proposed).data()
            return self.store.publish(scan, output, self.identity.stamp(proposed), upper)

    def collect(self, session: Session, first: VenueTime, symbols: tuple[str, ...]) -> tuple[
        dict[str, Any], dict[str, Any], list[tuple[str, str, dict[str, Any]]]
    ]:
        prior = self.store.last_comparable()
        old_meta = prior.get("metadata_cache", {})
        if reusable(old_meta, "instrument", first.lower_ms):
            meta = old_meta
            exchange_body = json_body(self.store.raw(meta["receipt_id"]))
        else:
            exchange = session.get(INSTRUMENTS, {})
            meta = received_record(exchange, session, first)
            exchange_body = exchange.body
            self.budget.configure(n.exchange_limits(n.obj(exchange_body)))
        markets: dict[str, Any] = {}
        entries: list[tuple[str, str, dict[str, Any]]] = []
        for symbol in symbols:
            try:
                instruments, _ = n.exchange_info(exchange_body, (symbol,))
                frames = {}
                bars: list[tuple[str, str, dict[str, Any]]] = []
                for frame in INTERVALS:
                    frames[frame], changes = collect_bars(session, self.store, self.config, symbol, frame, first)
                    bars.extend((symbol, frame, row) for row in changes)
                old_values = prior.get("markets", {}).get(symbol, {}).get("context", {})
                values = {"instrument": {**meta, "source_event_ms": None, "values": instruments[symbol]}}
                for name in ("funding", "oi_history", "ticker", "oi", "mark", "quote", "depth"):
                    record = old_values.get(name, {})
                    values[name] = (record if reusable(record, name, first.lower_ms)
                                    else fetch_observation(name, session, first, symbol))
                markets[symbol] = {"frames": frames, "context": values, "issue": None}
                entries.extend(bars)
            except GlobalStop:
                raise
            except SourceBlocked as exc:
                markets[symbol] = {"frames": {}, "context": {}, "issue": issue(exc)}
        return markets, meta, entries

    def finish_markets(self, output: dict[str, Any], decision: VenueTime, durable: dict[str, str | int]) -> None:
        policy = self.config.policy
        for market in output["markets"].values():
            frames, context = market["frames"], market["context"]
            for name, frame in frames.items():
                frame["age_upper_ms"] = decision.upper_ms - frame["latest_completed_end_ms"]
                frame["status"] = ("CURRENT" if frame["age_upper_ms"]
                                   <= policy.candle_freshness_ms[name] + policy.close_grace_ms else "STALE")
                for bar in frame["completed"] + frame["context"]:
                    bar.setdefault("first_durable_availability", durable)
                    if bar["received_venue_upper_ms"] > decision.upper_ms:
                        frame["status"] = "TIME_UNCERTAIN"
            for name, value in context.items():
                value.setdefault("first_durable_availability", durable)
                value["status"], value["age_upper_ms"] = observation_status(
                    name, value, decision.upper_ms, decision.lower_ms, policy)
            current = bool(frames and context) and all(frame["status"] == "CURRENT" for frame in frames.values())
            current = current and all(value["status"] == "CURRENT" for value in context.values())
            market["data_ready"] = current
            market["source_status"] = "DATA_READY" if current else "SOURCE_BLOCKED"
            market["feature_warmup_ready"] = current and all(
                len(frames[str(dep["interval"])]["completed"]) >= int(dep["completed_bars"]) for dep in FEATURES
            )
            market.update(strategy_evaluated=False, strategy_status="NOT_EVALUATED",
                          rpi_depth="DISABLED", **ACCOUNT)
        values = list(output["markets"].values())
        output["data_ready"] = bool(values) and all(value["data_ready"] for value in values)
        output["feature_warmup_ready"] = bool(values) and all(value["feature_warmup_ready"] for value in values)
        output["source_status"] = ("DATA_READY" if output["data_ready"] else
                                   "PARTIAL" if any(v["data_ready"] for v in values) else "SOURCE_BLOCKED")
