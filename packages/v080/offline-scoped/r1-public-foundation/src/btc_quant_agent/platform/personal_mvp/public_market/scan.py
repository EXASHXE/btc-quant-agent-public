"""One bounded offline scan, from venue clock witnesses to synchronized public inputs."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import normalize as n
from .adapter import PublicAdapter, PublicSession, Receipt, Transport
from .clock import Clock, VenueTime
from .policy import (
    DEPTH, FUNDING, INSTRUMENTS, INTERVALS, KLINES, MARK, OI, OI_HISTORY, QUOTE, SYMBOLS, TICKER, TIME,
    WEIGHTS_VERSION, Policy, SourceBlocked, require,
)
from .store import Cache, EVIDENCE_CLASS, FIXTURE_CLASS, SNAPSHOT_SCHEMA, ScanTransaction, encode

MANUAL_CHECK = "Manually verify real account exposure and protective orders. Account context is unavailable."


@dataclass(frozen=True)
class KlineBatch:
    start: int
    end: int
    receipt: Receipt


@dataclass(frozen=True)
class ContextInput:
    event_ms: int | None
    values: dict[str, object]
    receipt: Receipt


def witness(session: PublicSession, policy: Policy) -> tuple[VenueTime, int]:
    obs = session.get("GET", TIME, {})
    timestamp = n.integer(n.obj(obs.body).get("serverTime"), "serverTime", minimum=1)
    return VenueTime.bracket(obs.sent, obs.received, timestamp, policy), obs.seq


class Scanner:
    """Serial scanner. Reuse the instance to carry endpoint limits and cooldowns between invocations."""

    def __init__(self, path: Path, transport: Transport, clock: Clock, policy: Policy = Policy()) -> None:
        self.cache = Cache(path)
        self.adapter = PublicAdapter(transport, clock, policy)
        self.policy = policy

    def scan(self, symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")) -> dict[str, object]:
        require(bool(symbols) and set(symbols) <= SYMBOLS and len(set(symbols)) == len(symbols), "INVALID_SCAN_SYMBOLS")
        with self.cache.run(self.policy.max_body_bytes) as transaction:
            session = self.adapter.session(self.adapter.clock.sample(), transaction.audit)
            output: dict[str, object] = {
                "schema": SNAPSHOT_SCHEMA, "scan_id": transaction.scan_id, "mode": "PERSONAL_MVP",
                "evidence_class": EVIDENCE_CLASS, "data_origin": FIXTURE_CLASS, "weight_version": WEIGHTS_VERSION,
                "interval_order": list(INTERVALS), "symbols": list(symbols), "market_setup_status": "SOURCE_BLOCKED",
                "account_context_status": "UNAVAILABLE", "human_actionability": MANUAL_CHECK,
                "data_ready": False, "markets": {}, "clock": {}, "issue": None,
            }
            try:
                self.collect(session, transaction, symbols, output)
            except SourceBlocked as exc:
                output["issue"] = {"code": exc.code, "detail": exc.detail}
            output["request_attempts"] = session.count
            output["local_request_weight"] = session.weight
            return transaction.finish(output)

    def collect(self, session: PublicSession, transaction: ScanTransaction,
                symbols: tuple[str, ...], output: dict[str, object]) -> None:
        policy = self.policy
        first, first_seq = witness(session, policy)
        output["clock"] = {"first_receipt": first_seq, "first": first.evidence()}
        instrument_receipt = session.get("GET", INSTRUMENTS, {})
        instruments, limits = n.exchange_info(instrument_receipt.body, symbols)
        self.adapter.limits.configure(limits, instrument_receipt.received.mono_ms)
        batches, contexts = {}, {}
        for symbol in symbols:
            batches[symbol] = {interval: self.fetch_series(session, transaction, first, symbol, interval)
                               for interval in INTERVALS}
            contexts[symbol] = self.fetch_context(session, symbol)
            contexts[symbol]["instrument"] = ContextInput(None, instruments[symbol], instrument_receipt)
        last, last_seq = witness(session, policy)
        output["clock"] = {"first_receipt": first_seq, "first": first.evidence(),
                           "last_receipt": last_seq, "last": last.evidence()}
        final = first.reconcile(last, policy)
        final.check_width(policy)
        cutoff = first.lower_ms
        output["clock"] = {
            "first_receipt": first_seq, "first": first.evidence(), "last_receipt": last_seq,
            "last": last.evidence(), "reconciled": final.evidence(), "bar_cutoff_venue_ms": cutoff,
        }

        entries: list[tuple[str, str, int, int, dict[str, object]]] = []
        markets = {}
        ready = True
        for symbol in symbols:
            series = {interval: self.normalize_series(transaction, symbol, interval, batch,
                                                      first, final, entries)
                      for interval, batch in batches[symbol].items()}
            values = {name: n.observation(name, ctx.event_ms, ctx.values, ctx.receipt, final, final, policy)
                      for name, ctx in contexts[symbol].items()}
            values["rpi_depth"] = {"status": "DISABLED", "values": None}
            symbol_ready = (all(frame["status"] == "CURRENT" for frame in series.values())
                            and all(obs["status"] == "CURRENT" for name, obs in values.items()
                                    if name != "rpi_depth"))
            markets[symbol] = {"series": series, "context": values, "data_ready": symbol_ready,
                               "market_setup_status": "NO_SETUP" if symbol_ready else "SOURCE_BLOCKED"}
            ready = ready and symbol_ready
        transaction.persist_candles(entries)
        output["markets"] = markets
        output["data_ready"] = ready
        output["market_setup_status"] = "NO_SETUP" if ready else "SOURCE_BLOCKED"
        if not ready:
            output["issue"] = {"code": "MARKET_INPUTS_NOT_CURRENT", "detail": "See per-observation statuses."}

    def fetch_series(self, session: PublicSession, transaction: ScanTransaction,
                     first: VenueTime, symbol: str, interval: str) -> KlineBatch:
        width = INTERVALS[interval]
        policy = self.policy
        cutoff = first.lower_ms
        end = cutoff // width * width
        expected_end = (cutoff - policy.close_grace_ms) // width * width
        start = expected_end - policy.history_bars * width
        tail = transaction.candle_tail(symbol, interval, max(policy.history_bars, policy.revision_overlap))
        if tail:
            last = n.integer(tail[-1]["open_ms"], "cached open_ms")
            require(last + width <= expected_end, "CACHE_AHEAD_OF_SCAN", f"{symbol}/{interval}")
            review_start = n.integer(tail[-policy.revision_overlap:][0]["open_ms"], "cached open_ms")
            oldest = n.integer(tail[0]["open_ms"], "cached open_ms")
            # Re-fetch the revision overlap and extend backwards only if more history is requested.
            start = review_start if start >= oldest else min(start, review_start)
        count = (end - start) // width + 1
        require(start >= 0 and count <= policy.kline_limit, "BOUNDED_KLINE_CATCHUP_EXCEEDED",
                f"{symbol}/{interval}: {count} slots")
        return KlineBatch(start, end, session.get("GET", KLINES, {
            "symbol": symbol, "interval": interval, "startTime": start, "endTime": end, "limit": count,
        }))

    def normalize_series(self, transaction: ScanTransaction, symbol: str, interval: str, batch: KlineBatch,
                         first: VenueTime, final: VenueTime,
                         entries: list[tuple[str, str, int, int, dict[str, object]]]) -> dict[str, object]:
        policy = self.policy
        receipt = batch.receipt
        at_send = first.projected(receipt.sent, policy)
        at_receive = final.projected(receipt.received, policy)
        at_send.check_width(policy)
        at_receive.check_width(policy)
        cutoff = min(first.lower_ms, at_send.lower_ms)
        closed: dict[int, dict[str, object]] = {
            n.integer(item["open_ms"], "open_ms"): item
            for item in transaction.candle_tail(symbol, interval, policy.history_bars)
        }
        context = []
        parsed = n.candles(receipt.body, interval, batch.start, batch.end)
        for candle, raw in zip(parsed, n.rows(receipt.body), strict=True):
            require(candle.open_ms <= at_receive.upper_ms, "FUTURE_KLINE", f"{symbol}/{interval}")
            digest = hashlib.sha256(encode(raw).encode()).hexdigest()
            value = {**candle.values(), "source_publication": "UNKNOWN",
                     "observed_at_wall_ms": receipt.received.wall_ms, "observed_at_monotonic_ms": receipt.received.mono_ms,
                     "observed_venue_lower_ms": at_receive.lower_ms, "observed_venue_upper_ms": at_receive.upper_ms,
                     "source_row_sha256": digest, "receipt": {"scan_id": transaction.scan_id, "sequence": receipt.seq}}
            if candle.end_ms_exclusive + policy.close_grace_ms > cutoff:
                context.append({**value, "finality": ("FORMING" if candle.end_ms_exclusive > at_receive.upper_ms
                                                     else "CLOSE_UNCONFIRMED")})
                continue
            previous = transaction.prior(symbol, interval, candle.open_ms)
            if previous:
                if previous["source_row_sha256"] != digest:
                    raise SourceBlocked("KLINE_REVISION", f"{symbol}/{interval}/{candle.open_ms}: "
                                        f"{previous['source_row_sha256']} -> {digest}; response {receipt.seq}")
                closed[candle.open_ms] = previous
                continue
            value["finality"] = "COMPLETE"
            closed[candle.open_ms] = value
            entries.append((symbol, interval, candle.open_ms, receipt.seq, value))
        width = INTERVALS[interval]
        expected_end = (cutoff - policy.close_grace_ms) // width * width
        opens = list(range(expected_end - policy.history_bars * width, expected_end, width))
        missing = [opened for opened in opens if opened not in closed]
        require(not missing, "KLINE_CONFIRMED_WINDOW_GAP", f"{symbol}/{interval}: {missing}")
        completed = [closed[opened] for opened in opens]
        require(all(n.integer(item["observed_venue_upper_ms"], "observed_venue_upper_ms") <= final.lower_ms
                    for item in completed), "CACHED_CANDLE_NOT_YET_OBSERVED", f"{symbol}/{interval}")
        age = final.upper_ms - expected_end
        status = "CURRENT" if age <= policy.candle_freshness_ms[interval] + policy.close_grace_ms else "STALE"
        return {"status": status, "completed": completed, "context": context,
                "latest_completed_end_ms": expected_end, "age_upper_ms": age}

    def fetch_context(self, session: PublicSession, symbol: str) -> dict[str, ContextInput]:
        policy = self.policy
        normalize: dict[str, tuple[str, dict[str, str | int], Callable[
            [object], tuple[int | None, dict[str, object]]
        ]]] = {
            "ticker": (TICKER, {}, lambda body: n.ticker(body, symbol)),
            "book_ticker": (QUOTE, {}, lambda body: n.quote(body, symbol)),
            "depth": (DEPTH, {"limit": policy.depth_limit}, lambda body: n.depth(body, policy.depth_limit)),
            "open_interest": (OI, {}, lambda body: n.open_interest(body, symbol)),
            "open_interest_history": (
                OI_HISTORY, {"limit": policy.history_limit, "period": "5m"},
                lambda body: n.history(body, symbol, policy.history_limit),
            ),
            "funding_history": (FUNDING, {"limit": policy.history_limit},
                                lambda body: n.history(body, symbol, policy.history_limit, funding=True)),
            "mark_funding": (MARK, {}, lambda body: n.mark(body, symbol)),
        }
        observations = {}
        for name, (route, params, parse) in normalize.items():
            receipt = session.get("GET", route, {**params, "symbol": symbol})
            event, values = parse(receipt.body)
            observations[name] = ContextInput(event, values, receipt)
        return observations
