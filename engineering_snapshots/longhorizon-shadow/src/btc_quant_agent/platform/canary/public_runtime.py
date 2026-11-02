"""Finite native canary and local-only L23 WATCH/risk shadow; no order or sender API."""

from __future__ import annotations

from collections import Counter, deque
from contextlib import contextmanager
from functools import wraps
from dataclasses import replace
import html
import json
import hashlib
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time
import resource

from ..core import Candle, InstrumentSpec, MarketEvent, fingerprint, primitive, dec
from ..position_management import supervise
from ..selection.lifecycle import Monitor, advance
from ..selection.management import ExitPolicy
from ..selection.selector import Policy as SelectorPolicy, scan
from ..selection.sources import FrozenUniverse, SourceHistory, STRUCTURE, MINUTE
from .clocks import ClockEstimate, Probe, estimate_clock
from .control import BudgetGuard, CanaryStore
from .public_data import normalize, bar_from_record, quote_from_record
from .public_io import PublicTransport, Wire
from .public_journal import PublicJournal
from .public_policy import (
    END,
    START,
    OUTPUT,
    SYMBOLS,
    PublicStop,
    SystemClock,
    preflight,
    current_source_hashes,
)
from .warmup import assess
from . import clock_domain as domain


def clocked(method):
    """Bind each V2 decision to a newly bracketed local epoch sample."""

    @wraps(method)
    def run(self, *args, **kwargs):
        if not hasattr(self.clock, "sample"):
            return method(self, *args, **kwargs)
        wall, _, sample = domain.capture(self.clock)
        if sample is None:
            raise PublicStop("CLOCK_BRACKET_MISSING")
        if reason := domain.sample_reason(sample):
            self.invalidate_clock(reason, sample)
        with domain.decision_clock(sample, self.scope.hash):
            return method(self, *args, **kwargs)

    return run


class FastAdmission(CanaryStore):
    """Reuse the existing sequence/gap state machine in RAM; checkpoint after durable chunks."""

    def __init__(self, durable):
        self.memory = sqlite3.connect(":memory:")
        super().__init__(":memory:")
        self.durable = durable
        with durable._connect() as db:
            rows = db.execute("SELECT feed,symbol,value FROM canary_sources").fetchall()
        with self.memory:
            self.memory.executemany("INSERT OR REPLACE INTO canary_sources VALUES(?,?,?)", rows)

    def _connect(self):
        return self.memory

    def checkpoint(self):
        rows = self.memory.execute("SELECT feed,symbol,value FROM canary_sources").fetchall()
        with self.durable._connect() as db:
            db.executemany("INSERT OR REPLACE INTO canary_sources VALUES(?,?,?)", rows)


class PublicEngine:
    def __init__(self, scope, clock, store, journal, exposure):
        self.scope, self.clock, self.store, self.journal, self.exposure = (
            scope,
            clock,
            store,
            journal,
            exposure,
        )
        self.memory = FastAdmission(store)
        self.metadata = None
        self.probes: deque[Probe] = deque(maxlen=16)
        self.native_probes: deque[dict] = deque(maxlen=16)
        previous_fault = store.get_value("clock_epoch_invalidation")
        self.clock_fault = previous_fault["reason"] if previous_fault else None
        self.estimate = None
        self.pending = []
        self.pending_raw_sha = None
        self.last_flush = clock.mono()
        self.quote = {}
        self.quote_native_sizes = {}
        self.bars = {}
        self.episodes = {}
        self.policy = SelectorPolicy.model_validate({"symbols": SYMBOLS})
        self.counts: Counter[str] = Counter()
        self.reasons: Counter[str] = Counter()
        self.feed: Counter[str] = Counter()
        self.samples: deque[tuple[float, float]] = deque(maxlen=4096)
        self.first_received = None
        self.last_received = None
        self.quote_counts: Counter[str] = Counter()
        self.advisory_enabled = self.clock_fault is None
        self.scans = 0
        self.last_cutoff = None
        self.last_scan = None
        self.response = []
        self.management = []
        self.repairs: deque[tuple[str, int, int, int]] = deque(maxlen=32)

    def ingest(self, wire, *, replay_record=None):
        now, mono, sample = domain.capture(self.clock)
        if replay_record is None and wire.clock_samples is not None and self.native_probes:
            self.native_probes = deque(
                (
                    p
                    for p in self.native_probes
                    if mono - p["available"]["mono_before_ms"] <= domain.MAX_PROBE_AGE_MS
                ),
                maxlen=16,
            )
            self.estimate = (
                domain.estimate(list(self.native_probes), self.scope.hash, self.exposure)
                if len(self.native_probes) >= 2
                else None
            )
        record = replay_record or {
            "exposure": self.exposure,
            "received_wall_ms": wire.receive_wall,
            "symbol": wire.symbol,
            "wire": wire.record(),
            "decision_wall_ms": now,
            "decision_mono_ms": mono,
            "metadata": self.metadata,
            "clock": primitive(self.estimate) if self.estimate else None,
            "scope_hash": self.scope.hash,
            "receiver_utc_sync_evidence": getattr(
                self.clock, "sync_evidence", {"status": "SYNTHETIC_CLOCK_FIXTURE"}
            ),
        }
        if replay_record is None and wire.clock_samples is not None:
            record.update(clock_contract_version=domain.VERSION, decision_sample=sample)
            if hasattr(self.scope, "start_ms"):
                record["scope_window_ms"] = [self.scope.start_ms, self.scope.end_ms]
            if getattr(self.scope, "run_profile", None) == "L4_LONGHORIZON_V1":
                record["source_contract_version"] = "L4_LONGHORIZON_V1"
        result = normalize(record)
        if replay_record is None:
            ready_wall, ready_mono, ready_sample = domain.capture(self.clock)
            record["normalization_available_wall_ms"] = ready_wall
            record["normalization_available_mono_ms"] = ready_mono
            decision_wall, decision_mono, decision_sample = domain.capture(self.clock)
            record["decision_wall_ms"], record["decision_mono_ms"] = decision_wall, decision_mono
            if wire.clock_samples is not None:
                record.update(normalization_sample=ready_sample, decision_sample=decision_sample)
            result = normalize(record)
        self.pending.append((record, result))
        critical = (
            bool(result.get("bars"))
            or wire.endpoint_id in ("binance_usdm_exchange_info", "binance_usdm_server_time")
            or wire.error
            or wire.status != 200
        )
        if critical or len(self.pending) >= 64 or mono - self.last_flush >= 2000:
            self.flush()
        return result

    def flush(self):
        if not self.pending:
            return
        raw, normal = zip(*self.pending)
        if self.pending_raw_sha is None:
            self.pending_raw_sha, _ = self.journal.write("raw", list(raw))
        _, commit = self.journal.write("normalized", list(normal), raw_sha=self.pending_raw_sha)
        ready = self.pending
        self.current_raw_sha = self.pending_raw_sha
        self.pending = []
        self.pending_raw_sha = None
        for record, result in ready:
            self.apply(record, result, commit)
        self.memory.checkpoint()
        self.last_flush = self.clock.mono()

    def invalidate_clock(self, reason, sample):
        if self.clock_fault:
            return
        self.clock_fault = reason
        self.reasons[reason] += 1
        self.quote.clear()
        self.estimate = None
        self.advisory_enabled = False
        self.store.invalidate_clock_epoch(sample, self.scope.hash)
        for id, e in self.episodes.items():
            if e["last_status"] not in ("CANCELLED", "EXPIRED"):
                e["last_status"] = self.store.episode(id)["state"]["status"]

    @clocked
    def apply(self, record, result, commit):
        w = Wire(**record["wire"])
        now = max(record["decision_wall_ms"], commit)
        if context := domain.current_decision():
            now = context[0]["wall_ms"]
        self.counts["received"] += 1
        if w.payload_text is not None and w.status == 200:
            self.first_received = (
                w.receive_wall if self.first_received is None else min(self.first_received, w.receive_wall)
            )
            self.last_received = (
                w.receive_wall if self.last_received is None else max(self.last_received, w.receive_wall)
            )
            self.counts["payloads_received"] += 1
        self.feed[w.endpoint_id] += 1
        self.reasons.update(result["reasons"])
        if result["status"] == "ADMITTED_OBSERVATION":
            self.counts["admitted"] += 1
        report = result.get("clock", {})
        if report.get("event_to_receive_estimate_bounds_ms") is not None:
            self.samples.append(report["event_to_receive_estimate_bounds_ms"])
        if self.clock_fault:
            # Already-sealed pre-step observations remain facts, but cannot feed
            # a decision after epoch invalidation. No automatic recovery/rebase.
            self.reasons["CLOCK_EPOCH_INVALID"] += 1
            return
        if result.get("instruments"):
            projected = dict(record["wire"])
            projected["payload_text"] = json.dumps(
                {"symbols": [x for x in w.payload["symbols"] if x.get("symbol") in SYMBOLS]}, sort_keys=True
            )
            self.metadata = {
                "wire": projected,
                "projection_source_wire_sha": fingerprint(record["wire"]),
                "source_raw_chunk_sha": self.current_raw_sha,
                "projection_note": "Lossless selected-instrument projection; complete native metadata remains in referenced immutable raw chunk",
                "normalization_available_wall_ms": record.get(
                    "normalization_available_wall_ms", w.available_wall
                ),
                "normalization_available_mono_ms": record.get(
                    "normalization_available_mono_ms", w.available_mono
                ),
            }
        if result.get("serverTime") is not None and not w.error:
            if w.request_wall is None or w.request_mono is None:
                raise PublicStop("SERVER_PROBE_REQUEST_CLOCK_MISSING")
            if record.get("clock_contract_version") == domain.VERSION:
                samples = w.clock_samples or {}
                request, received = samples.get("request"), samples.get("receive")
                available = record.get("normalization_sample", samples.get("available"))
                if (
                    request is None
                    or request["wall_ms"] != w.request_wall
                    or request["mono_after_ms"] != w.request_mono
                ):
                    raise PublicStop("SERVER_PROBE_REQUEST_CLOCK_MISSING")
                probe = {
                    "request": request,
                    "receive": received,
                    "available": available,
                    "server_ms": result["serverTime"],
                    "scope_hash": self.scope.hash,
                    "wire_id": fingerprint(record["wire"]),
                    "exposure": self.exposure,
                }
                self.native_probes = deque(
                    (
                        p
                        for p in self.native_probes
                        if available["mono_after_ms"] - p["available"]["mono_before_ms"]
                        <= domain.MAX_PROBE_AGE_MS
                    ),
                    maxlen=16,
                )
                self.native_probes.append(probe)
                if len(self.native_probes) >= 2:
                    try:
                        self.estimate = domain.estimate(
                            list(self.native_probes), self.scope.hash, self.exposure
                        )
                    except ValueError as exc:
                        self.estimate = None
                        self.reasons[str(exc)] += 1
                else:
                    self.reasons["MULTIPLE_INDEPENDENT_CLOCK_PROBES_REQUIRED"] += 1
            else:
                self.update_legacy_probe(w, record, result)
        if w.endpoint_id == "binance_usdm_bbo_ws" and not result.get("quote"):
            self.quote.pop(w.symbol, None)
            self.memory.fault(w.endpoint_id, w.symbol, "|".join(result["reasons"]))
        q = quote_from_record(result.get("quote"))
        if (
            q
            and isinstance(q.provenance, domain.NativeProvenance)
            and q.reason(InstrumentSpec(**result["instrument_spec"]), now, 5000)
        ):
            self.quote.pop(w.symbol, None)
            self.reasons["QUOTE_NOT_ADMISSIBLE_AT_COMMIT_DECISION"] += 1
            q = None
        if q:
            self.apply_quote(w, record, result, q, now)
        for rawbar in result.get("bars", []):
            self.apply_bar(rawbar, now)
        if self.advisory_enabled:
            self.discover(now)

    def update_legacy_probe(self, w, record, result):
        self.probes.append(
            Probe(
                w.request_wall,
                w.receive_wall,
                w.request_mono,
                w.receive_mono,
                result["serverTime"],
                exposure=self.exposure,
            )
        )
        self.estimate = estimate_clock(tuple(self.probes), allowed_exposure=self.exposure)
        self.estimate = replace(
            self.estimate,
            available_wall_ms=max(
                self.estimate.available_wall_ms,
                record.get("normalization_available_wall_ms", w.available_wall),
            ),
            available_mono_ms=max(
                self.estimate.available_mono_ms,
                record.get("normalization_available_mono_ms", w.available_mono),
            ),
        )

    def apply_quote(self, w, record, result, q, now):
        state, reason = self.memory.accept(
            w.endpoint_id,
            w.symbol,
            epoch=w.epoch,
            sequence=result["sequence"],
            native_ms=q.provenance.exchange_event_ts,
            payload_hash=fingerprint(w.payload),
            receive_ms=w.receive_wall,
            instrument_hash=fingerprint(result["instrument_spec"]),
        )
        if reason:
            self.reasons[reason] += 1
            if reason in (
                "SOURCE_EQUIVOCATION",
                "CONTRACT_CHANGE_REVALIDATION_REQUIRED",
                "RECEIVE_TIME_REGRESSION",
            ):
                self.quote.pop(w.symbol, None)
            if reason == "CONTRACT_CHANGE_REVALIDATION_REQUIRED":
                raise PublicStop(reason)
        elif state["status"] == "OFFLINE_STABLE":
            self.counts["distinct_qualified_quotes"] += 1
            self.quote_counts[w.symbol] += 1
            self.quote[w.symbol] = q
            self.quote_native_sizes[w.symbol] = result.get("native_sizes")
        elif state.get("gap") and len(state.get("recovery_native_times", [])) >= 2:
            self.memory.recover_quote_fragment(w.endpoint_id, w.symbol)
            self.quote[w.symbol] = q
            self.quote_native_sizes[w.symbol] = result.get("native_sizes")
        # Raw/normalized evidence precedes all local delayed revalidation decisions.
        if self.advisory_enabled and not reason and w.symbol in self.quote:
            minutes = self.bars.get((w.symbol, MINUTE), {})
            if minutes:
                self.monitor(minutes[max(minutes)], now, include_risk=False)
            self.revalidate(w.symbol, now)

    def apply_bar(self, rawbar, now):
        bar = bar_from_record(rawbar)
        key = (bar.spec.symbol, bar.interval_ms)
        values, errors = bar.values(bar.end + 1000)
        if not all(f in values for f in ("open", "high", "low", "close")):
            self.reasons.update(errors.values())
            return
        history = self.bars.setdefault(key, {})
        if bar.start in history:
            previous = history[bar.start]
            if [o.value for o in previous.fields] != [o.value for o in bar.fields]:
                raise PublicStop("IMMUTABLE_CLOSED_BAR_CONFLICT")
            return
        if history:
            last = max(history) + bar.interval_ms
            if bar.start > last:
                self.reasons["CLOSED_BAR_GAP"] += 1
                self.repairs.append((bar.spec.symbol, bar.interval_ms, last, bar.start - 1))
        history[bar.start] = bar
        if len(history) > getattr(self, "bar_history_cap", 2000):
            del history[min(history)]
        if self.advisory_enabled and bar.interval_ms == MINUTE:
            self.monitor(bar, now)

    @clocked
    def outage(self, group, now):
        context = domain.current_decision()
        native_now = None
        if context:
            now = context[0]["wall_ms"]
            if isinstance(self.estimate, dict):
                native_now = context[0]["mono_before_ms"] + self.estimate["native_minus_monotonic_low_ms"]
        if group == "public":
            self.quote.clear()
            for symbol in SYMBOLS:
                self.memory.reconnect("binance_usdm_bbo_ws", symbol, now)
        else:
            for symbol in SYMBOLS:
                self.store.revoke_regime(symbol, now, 0)
                for interval in (MINUTE, STRUCTURE):
                    history = self.bars.get((symbol, interval), {})
                    if history:
                        last = max(history) + interval
                        # Repair only bars certainly completed in both the
                        # native envelope and the unchanged local grant window.
                        safe_now = min(now, native_now) if native_now is not None else now
                        end = (safe_now // interval) * interval - 1
                        if end >= last:
                            self.repairs.append((symbol, interval, last, end))
        self.reasons["WS_RECONNECT_GAP"] += 1

    def contiguous(self, symbol, interval, end=None):
        history = self.bars.get((symbol, interval), {})
        if not history:
            return []
        cursor = (max(history) + interval if end is None else end) - interval
        result = []
        while cursor in history:
            result.append(history[cursor])
            cursor -= interval
        return list(reversed(result))

    def check_aux_headroom(self, evidence):
        from .storage import encode, StorageBlocked

        reserve = 65536 + 32 * len(encode(evidence))
        if self.journal.used()["auxiliary"] + reserve > self.journal.aux_cap:
            raise StorageBlocked("AUXILIARY_DECISION_CAPACITY_BLOCKED")

    def discover(self, now):
        structures = [self.bars.get((s, STRUCTURE), {}) for s in SYMBOLS]
        if not all(structures):
            return
        end = min(max(v) + STRUCTURE for v in structures)
        if end == self.last_cutoff or not all(end - STRUCTURE in v for v in structures):
            return
        allbars = tuple(b for symbol in SYMBOLS for b in self.contiguous(symbol, STRUCTURE, end))
        h = SourceHistory(allbars, FrozenUniverse(tuple(sorted(SYMBOLS)), "BTCUSDT", end, decision_ts=now))
        if not h.synchronized():
            return
        result = scan(h, self.store, self.policy)
        self.last_cutoff = end
        self.last_scan = result
        self.scans += 1
        self.readiness = assess(h)
        for c in result["candidates"]:
            a = c["anchors"]
            id = a["id"]
            if id in self.episodes:
                continue
            a = {**a}
            a.setdefault("known_at_ts", now)
            a.setdefault("owner_scope_hash", self.scope.hash)
            context = domain.current_decision()
            if context and isinstance(self.estimate, dict) and "known_clock_sample" not in a:
                a.update(
                    known_clock_sample=context[0],
                    clock_epoch_id=context[0]["epoch_id"],
                    expiry_mono_ms=a["expiry"] - self.estimate["native_minus_monotonic_high_ms"],
                )
            self.check_aux_headroom(a)
            self.store.create_episode(a, now)
            # Local outbox: persistence only. No sender dispatch and no claim of delivery.
            decision = self.store.commit_decision(
                {"candidate": c, "owner_scope_hash": self.scope.hash, "exposure": self.exposure},
                now,
                now,
                origin=fingerprint([id, "PUBLIC_WATCH"]),
            )
            event = self.store.prepare(decision, a["symbol"], now)
            self.episodes[id] = {
                "anchors": a,
                "known_at": a["known_at_ts"],
                "event": event,
                "responses": {},
                "last_status": "WATCH",
                "known_mono": a["known_clock_sample"]["mono_after_ms"]
                if a.get("known_clock_sample")
                else None,
            }

    def monitor(self, bar, now, *, include_risk=True):
        history = self.bars[(bar.spec.symbol, MINUTE)]
        previous = history.get(bar.start - MINUTE)
        for id, e in self.episodes.items():
            a = e["anchors"]
            if a["symbol"] != bar.spec.symbol or e["last_status"] in ("CANCELLED", "EXPIRED"):
                continue
            q = self.quote.get(bar.spec.symbol)
            m = Monitor(
                bar,
                now,
                q,
                "PUBLIC_READONLY_TOP_OF_BOOK"
                if self.exposure == "PUBLIC_CANARY"
                else "OFFLINE_EXECUTABLE_TOP_OF_BOOK",
                previous_bar=previous,
                healthy=True,
                regime=self.store.regime(a["symbol"])["state"],
                beta=a.get("beta"),
                beta_available_ts=e["known_at"],
                entry_vetoes=(
                    "RANK_COVERAGE_BELOW_TEN_WATCH_ONLY",
                    "CURRENT_CAPITAL_AND_MARGIN_NOT_VERIFIED",
                    "NATIVE_FUNDING_EVIDENCE_INCOMPLETE",
                ),
                setup_known_ts=e["known_at"],
            )
            value = advance(self.store, id, m, self.policy)
            e["last_status"] = value["state"]["status"]
        if include_risk:
            self.risk(bar, now)

    def revalidate(self, symbol, now):
        q = self.quote.get(symbol)
        for id, e in self.episodes.items():
            a = e["anchors"]
            if a["symbol"] != symbol:
                continue
            for minute in (1, 3, 5):
                if str(minute) in e["responses"]:
                    continue
                ack = e["known_at"] + minute * MINUTE
                context = domain.current_decision()
                ack_mono = e["known_mono"] + minute * MINUTE if e.get("known_mono") is not None else None
                elapsed = context[0]["mono_after_ms"] if ack_mono is not None and context else now
                deadline = ack_mono if ack_mono is not None else ack
                if elapsed < deadline:
                    continue
                if q and isinstance(q.provenance, domain.NativeProvenance) and ack_mono is not None:
                    evidence = q.provenance.clock_evidence
                    post_ack = (
                        evidence["receive"]["mono_before_ms"] > ack_mono
                        and domain.native_bounds(q.provenance, q.provenance.exchange_event_ts)[0] >= ack_mono
                    )
                    clock_ok = q.reason(InstrumentSpec(**a["contract"]), now, 5000) is None
                else:
                    post_ack = bool(
                        q
                        and q.provenance.exchange_event_ts >= ack
                        and q.provenance.received_ts > ack
                        and ack <= q.provenance.available_ts <= now
                    )
                    clock_ok = bool(
                        q
                        and isinstance(self.estimate, ClockEstimate)
                        and self.estimate.interval(q.provenance.exchange_event_ts, now)[1] <= 5000
                    )
                if (
                    q is not None
                    and post_ack
                    and q.reason(InstrumentSpec(**a["contract"]), now, 5000) is None
                    and clock_ok
                ):
                    reason = q.reason(InstrumentSpec(**a["contract"]), now, 5000)
                    status = "EXPIRED" if domain.expired(a, now) else e["last_status"]
                    reasons = (
                        [reason]
                        if reason
                        else [
                            "RANK_COVERAGE_BELOW_TEN_WATCH_ONLY",
                            "FUNDING_CAPITAL_OR_MARGIN_INCOMPLETE",
                            "ACTUAL_DELIVERY_AND_USER_ACK_UNKNOWN",
                        ]
                    )
                    item = {
                        "episode": id,
                        "response_minutes": minute,
                        "assumed_delivery_ts": e["known_at"],
                        "modeled_ack_ts": ack,
                        "modeled_ack_mono_ms": ack_mono,
                        "revalidated_ts": now,
                        "subsequently_received_quote_ts": q.provenance.received_ts,
                        "quote_id": fingerprint(q),
                        "quote_size_native": self.quote_native_sizes.get(symbol),
                        "state": status,
                        "vetoes": reasons,
                        "actual_delivery_or_ack": False,
                        "modeled_fill": False,
                        "assumption": "SYNTHETIC_HUMAN_RESPONSE_SCENARIO_ON_OBSERVED_SOURCE"
                        if self.exposure == "PUBLIC_CANARY"
                        else "FULLY_FABRICATED_SCENARIO",
                    }
                    e["responses"][str(minute)] = item
                    self.response.append(item)
                elif elapsed >= deadline + 5000:
                    item = {
                        "episode": id,
                        "response_minutes": minute,
                        "modeled_ack_ts": ack,
                        "state": "NO_VALID_QUOTE/UNKNOWN",
                        "vetoes": ["NEW_POST_ACK_QUOTE_REQUIRED"],
                        "actual_delivery_or_ack": False,
                        "modeled_fill": False,
                    }
                    e["responses"][str(minute)] = item
                    self.response.append(item)

    @clocked
    def tick(self, now):
        if context := domain.current_decision():
            now = context[0]["wall_ms"]
        for e in self.episodes.values():
            if domain.expired(e["anchors"], now) and e["last_status"] not in ("CANCELLED", "EXPIRED"):
                e["last_status"] = "EXPIRED"
                current = self.store.episode(e["anchors"]["id"])
                state = {**current["state"], "status": "EXPIRED", "reasons": ["ORIGINAL_EXPIRY_REACHED"]}
                self.store.transition(e["anchors"]["id"], current["revision"], state, now)
                self.reasons["ORIGINAL_EXPIRY_REACHED"] += 1
        for s in SYMBOLS:
            self.revalidate(s, now)

    def risk(self, bar, now):
        with self.store._connect() as db:
            rows = db.execute("SELECT DISTINCT id FROM platform_position_versions").fetchall()
        values, _ = bar.values(min(now, bar.end + 1000))
        if not all(k in values for k in ("open", "high", "low", "close")):
            return
        candle = Candle(
            bar.spec.symbol,
            "1m",
            bar.start,
            bar.end - 1,
            **{
                k: values[k]
                for k in ("open", "high", "low", "close", "volume", "quote_volume")
                if k in values
            },
            available_at_ms=max(o.provenance.available_ts for o in bar.fields),
        )
        p = next(o.provenance for o in bar.fields if o.field == "close")
        event = MarketEvent(bar.spec, candle, p, now, self.quote.get(bar.spec.symbol))
        for (id,) in rows:
            position = self.store.position(id)
            if position.symbol != bar.spec.symbol or position.status == "CLOSED":
                continue
            with self.store._connect() as db:
                binding = db.execute(
                    "SELECT episode_id FROM selector_position_bindings WHERE position_id=?", (id,)
                ).fetchone()
            if binding:
                a = self.store.episode(binding[0])["anchors"]
                action = supervise(
                    position,
                    event,
                    episode_policy=ExitPolicy(atr=a["atr"], target=dec(a["target"]) if a["target"] else None),
                )
            else:
                action = supervise(position, event)
            # Recommendations never update/close a real user-reported position.
            self.check_aux_headroom(action)
            self.management.append(primitive(action))
            decision = self.store.commit_decision(action, now, now, origin=fingerprint([id, bar.id, "RISK"]))
            self.store.prepare(decision, bar.spec.symbol, now)

    @clocked
    def report(self):
        rows = {
            s: {
                "completed_5m_bars": len(self.bars.get((s, STRUCTURE), {})),
                "completed_1m_bars": len(self.bars.get((s, MINUTE), {})),
                "quote_present": s in self.quote,
                "current_contiguous_5m_bars": len(self.contiguous(s, STRUCTURE)),
                "structural_warmup": len(self.contiguous(s, STRUCTURE)) >= 66,
                "beta_bar_count_minimum": len(self.contiguous(s, STRUCTURE)) >= 201,
            }
            for s in SYMBOLS
        }
        context = domain.current_decision()
        current = context[0]["wall_ms"] if context else min(self.clock.wall(), getattr(self.scope, "end_ms", END) - 1)
        price_slices = {}
        for symbol in SYMBOLS:
            q = self.quote.get(symbol)
            v2 = isinstance(self.estimate, dict)
            clock_ok = (
                bool(
                    not self.clock_fault
                    and self.estimate
                    and context
                    and context[0]["mono_after_ms"] - self.estimate["available"]["mono_before_ms"]
                    <= domain.MAX_PROBE_AGE_MS
                    and self.estimate["uncertainty_ms"] <= domain.MAX_UNCERTAINTY_MS
                )
                if v2
                else bool(
                    self.estimate
                    and 0 <= self.clock.mono() - self.estimate.available_mono_ms <= 300000
                    and self.estimate.uncertainty_ms <= 100
                )
            )
            quote_ok = bool(
                q
                and clock_ok
                and self.estimate is not None
                and q.provenance.reason(current, 5000) is None
                and self.quote_counts[symbol] >= 1
                and (v2 or self.estimate.interval(q.provenance.exchange_event_ts, current)[1] <= 5000)
            )
            intervals = {}
            for interval in (MINUTE, STRUCTURE):
                history = self.bars.get((symbol, interval), {})
                starts = sorted(history)
                contiguous = bool(starts) and all(b - a == interval for a, b in zip(starts, starts[1:]))
                native_lower = (
                    context[0]["mono_before_ms"] + self.estimate["native_minus_monotonic_low_ms"]
                    if isinstance(self.estimate, dict) and context
                    else current
                )
                expected = (native_lower // interval) * interval
                fresh = bool(starts) and max(starts) + interval >= expected
                intervals[str(interval)] = {
                    "count": len(starts),
                    "contiguous": contiguous,
                    "latest_completed_bar_current": fresh,
                    "trailing_contiguous_count": len(self.contiguous(symbol, interval)),
                    "observed_start_ms": starts[0] if starts else None,
                    "observed_end_ms": starts[-1] + interval if starts else None,
                    "full_fragment_missing_bars": (starts[-1] - starts[0]) // interval + 1 - len(starts)
                    if starts
                    else None,
                }
            price_slices[symbol] = {
                "quote_prices": quote_ok,
                "intervals": intervals,
                "price_slice_qualified": bool(
                    self.exposure == "PUBLIC_CANARY"
                    and self.metadata
                    and 0 <= current - self.metadata["wire"]["available_wall"] <= 3600000
                    and self.estimate
                    and len(self.native_probes if v2 else self.probes) >= 2
                    and quote_ok
                    and all(
                        int(v["trailing_contiguous_count"] or 0) >= 2 and v["latest_completed_bar_current"]
                        for v in intervals.values()
                    )
                ),
                "quantity_base_unit_qualified": False,
                "funding_action_qualified": False,
                "oi_base_unit_qualified": False,
            }
        core_qualified = all(v["price_slice_qualified"] for v in price_slices.values())
        return {
            "exposure": self.exposure,
            "first_market_receive_wall_ms": self.first_received,
            "last_market_receive_wall_ms": self.last_received,
            "source_qualified_slices": price_slices,
            "source_qualified_scope": "Current trailing contiguous core price/closed-bar/static-instrument slice only; full-window gaps remain explicit. No derivative/quantity/account qualification.",
            "counts": dict(self.counts),
            "feed_counts": dict(self.feed),
            "reasons": dict(self.reasons),
            "symbols": rows,
            "clock_estimate": primitive(self.estimate),
            "clock_epoch_failure": self.clock_fault,
            "event_to_receive_estimate_bounds_samples": list(self.samples),
            "clock_sample_note": "At most 4096 most recent bounds, not an exhaustive latency distribution or proven one-way latency",
            "L23_scan_count": self.scans,
            "latest_scan": primitive(self.last_scan),
            "feature_readiness": getattr(self, "readiness", None),
            "candidate_states": {id: e["last_status"] for id, e in self.episodes.items()},
            "response_sensitivity": self.response,
            "risk_recommendations": self.management,
            "ranking_qualified": False,
            "ranking_veto": "THREE_MEMBERS_BELOW_REQUIRED_TEN",
            "source_qualified": core_qualified,
            "source_qualification_note": "Per-field native source criteria and units must be assessed from actual receipts; transport success alone does not qualify every field",
            "shadow_advisory_qualified": core_qualified and self.scans > 0,
            "shadow_scope": "WATCH/RISK only; source/funding/rank/current capital veto all actionable entries",
            "economically_validated": False,
            "actual_user_actions_or_fills": 0,
            "external_sends": 0,
        }


@contextmanager
def own_signals(stop_event):
    prior = {}
    if threading.current_thread() is threading.main_thread():
        for s in (signal.SIGINT, signal.SIGTERM):
            prior[s] = signal.getsignal(s)

            def handler(signum, frame):
                stop_event.set()
                raise PublicStop("EMERGENCY_STOP_SIGNAL")

            signal.signal(s, handler)
    try:
        yield
    finally:
        for s, h in prior.items():
            signal.signal(s, h)


def save_reports(root, value):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    text = json.dumps(primitive(value), sort_keys=True, indent=2, allow_nan=False)
    documents = {
        "report.json": text + "\n",
        "report.html": (
            "<!doctype html><html lang='en'><meta charset='utf-8'><title>L4 finite public canary</title><h1>L4 source and local shadow evidence</h1><p>No economic validation or observed execution claim.</p><pre>"
            + html.escape(text)
            + "</pre></html>"
        ),
    }
    documents["replay_manifest.json"] = json.dumps(value["replay"], sort_keys=True, indent=2) + "\n"
    seal = {name: hashlib.sha256(content.encode()).hexdigest() for name, content in documents.items()}
    for name in ("started.json", "source_grant.json", "endpoint_policy.json", "source_sha256.json",
                 "owner_signed_grant.json", "clock_qualification_receipt.json",
                 "dashboard_final.html", "latest.json", "dashboard.html"):
        if (root / name).is_file():
            seal[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    documents["receipt_seal.json"] = json.dumps(seal, sort_keys=True, indent=2) + "\n"
    for name, content in documents.items():
        target = root / name
        if target.exists():
            raise PublicStop("IMMUTABLE_REPORT_ALREADY_EXISTS")
        temporary = root / (name + ".part")
        with temporary.open("x") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        temporary.rename(target)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def terminal_qualification(model, replay, reason, errors, exposure, shutdown_ok, pending):
    """A recent good cache cannot hide a failed source, clock, shutdown or receipt audit."""
    clean_stop = reason in {
        "AUTHORIZED_UTC_END",
        "GRANT_WINDOW_EXPIRED",
        "EMERGENCY_STOP",
        "EMERGENCY_STOP_SIGNAL",
    }
    safe = bool(
        clean_stop
        and not errors
        and shutdown_ok
        and not pending
        and replay.get("status") == "PARITY_VERIFIED"
        and exposure == "PUBLIC_CANARY"
    )
    return {
        "source_qualified": safe and bool(model["source_qualified"]),
        "shadow_advisory_qualified": safe and bool(model["shadow_advisory_qualified"]),
        "safe_terminal_evidence": safe,
        "economically_validated": False,
    }


def run_public(scope, *, enabled=False, clock=None, backend=None, output=None, verify_docs=True):
    if not enabled:
        raise PublicStop("PUBLIC_NETWORK_DEFAULT_DISABLED")
    clock = clock or SystemClock()
    synthetic = backend is not None and backend.exposure == "SYNTHETIC"
    clock_only = getattr(scope, "run_profile", None) == "CLOCK_VALIDATION_ONLY"
    long_duration = getattr(scope, "run_profile", None) == "L4_LONGHORIZON_V1"
    bound_scope = clock_only or long_duration
    start_ms = scope.start_ms if bound_scope else START
    end_ms = scope.end_ms if bound_scope else END
    if bound_scope and not hasattr(clock, "sample"):
        raise PublicStop("SESSION02_CLOCK_DOMAIN_V2_REQUIRED")
    if not synthetic and not verify_docs:
        raise PublicStop("NATIVE_DOCUMENT_BASELINE_REQUIRED")
    # Check all non-network gates and the exact window BEFORE creating a client, store or thread.
    check = (
        scope.preflight(clock, native=not synthetic)
        if bound_scope
        else preflight(scope, clock, native=not synthetic)
    )
    if check["window_status"] != "OPEN":
        raise PublicStop("|".join([check["window_status"], *check["reasons"]]))
    if check["reasons"]:
        raise PublicStop("|".join(check["reasons"]))
    from .public_policy import Window

    window = scope.make_window(clock) if bound_scope else Window(clock)
    window.check()
    expected_root = scope.output_path if bound_scope else OUTPUT / "run"
    root = Path(output) if output is not None else expected_root
    if not synthetic and root.resolve() != expected_root:
        raise PublicStop("EXACT_OUTPUT_REQUIRED")
    if bound_scope:
        if long_duration:
            root.parent.mkdir(parents=True, exist_ok=True)
        try:
            root.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            raise PublicStop("SESSION02_ALREADY_CLAIMED_NEVER_RESET") from None
    else:
        root.mkdir(parents=True, exist_ok=True)
    if (root / "report.json").exists() or (root / "started.json").exists():
        raise PublicStop("RUN_ALREADY_EXISTS_REPLAY_OR_RECONCILE; no implicit second session")
    # Native process lock also rejects competing operators. It is released on crash/exit.
    import fcntl

    lock = (root / "operator.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise PublicStop("CONFLICTING_CANARY_OPERATOR") from None
    try:
        started = clock.wall()
        started_mono = clock.mono()
        cpu_started = time.process_time()
        store = CanaryStore(root / "state.sqlite", clock_ms=clock.wall)
        guard = BudgetGuard(store, scope.budget_policy())
        transport = PublicTransport(scope, clock, guard, enabled=True, backend=backend)
        journal = PublicJournal(
            root,
            store,
            clock,
            exposure=transport.exposure,
            raw_cap=scope.raw["storage"]["raw_bytes"],
            aux_cap=scope.raw["storage"]["auxiliary_bytes"],
            reserve=scope.raw["storage"]["reserve_bytes"],
        )
        engine: PublicEngine
        long_engine = None
        if long_duration:
            from .longhorizon_runtime import LongEngine

            long_engine = LongEngine(scope, clock, store, journal, transport.exposure)
            engine = long_engine
        else:
            engine = PublicEngine(scope, clock, store, journal, transport.exposure)
        if clock_only:
            engine.advisory_enabled = False
        stop = threading.Event()
        reason = "AUTHORIZED_UTC_END"
        documentation = []
        transport.stop_check = lambda: stop.is_set() or (root / "STOP").exists()
        started_value = json.dumps(
            {
                "owner": scope.grant.grant_id,
                "scope_hash": scope.hash,
                "started_wall_ms": started,
                "late_start_ms": max(0, started - start_ms),
                "end_unchanged": end_ms,
                **({"session_id": scope.raw["session_id"], "run_profile": scope.run_profile,
                    "started_mono_ms": started_mono, "owner_authorization_digest": scope.authorization_digest}
                   if long_duration else {}),
                **(
                    {
                        "session_id": scope.raw["session_id"],
                        "absolute_outer_end_ms": END,
                        "run_profile": "CLOCK_VALIDATION_ONLY",
                        "started_mono_ms": started_mono,
                        "owner_authorization_digest": scope.authorization_digest,
                    }
                    if clock_only
                    else {}
                ),
                "exposure": transport.exposure,
                "egress_route": transport.metrics.get("egress_route", {"egress_mode": "DIRECT"}),
            }
        )
        with (root / "started.json").open("x" if bound_scope else "w") as f:
            f.write(started_value)
            f.flush()
            os.fsync(f.fileno())
        if long_duration:
            for directory in (root, root.parent):
                fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            (root / "owner_signed_grant.json").write_text(scope.authorization.model_dump_json(indent=2) + "\n")
            if scope.clock_receipt:
                (root / "clock_qualification_receipt.json").write_bytes(scope.clock_receipt.read_bytes())
        # Freeze the exact loaded grant, matrix and executable source before native I/O.
        (root / "source_grant.json").write_text(
            json.dumps(scope.grant.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        )
        (root / "endpoint_policy.json").write_text(json.dumps(scope.raw, sort_keys=True, indent=2) + "\n")
        if long_duration:
            from .longhorizon import source_hashes

            hashes = source_hashes()
        else:
            hashes = current_source_hashes()
        (root / "source_sha256.json").write_text(json.dumps(hashes, sort_keys=True, indent=2) + "\n")
    except BaseException:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
        raise

    def call(id, params):
        for attempt in range(4):
            if stop.is_set() or (root / "STOP").exists():
                raise PublicStop("EMERGENCY_STOP")
            if long_duration and id == "binance_usdm_klines_rest":
                guard.charge((("LONGHORIZON_REPAIR", 60000, 6, 1),), clock.mono())
            wire = transport.request(id, params, retry=attempt > 0)
            normalized = engine.ingest(wire)
            engine.flush()
            if (
                wire.status == 200
                and not wire.error
                and id in ("binance_usdm_exchange_info", "binance_usdm_server_time")
                and normalized["status"] == "INADMISSIBLE"
            ):
                raise PublicStop("ESSENTIAL_NATIVE_SCHEMA_UNQUALIFIED:" + "|".join(normalized["reasons"]))
            if transport.error:
                raise PublicStop(transport.error)
            if wire.status == 200 and not wire.error:
                if long_duration:
                    store.set_value("retry_attempt", 0)
                    store.set_value("next_allowed_mono", 0)
                return wire
            if wire.status not in (0, 408, 500, 502, 503, 504):
                raise PublicStop("HTTP_SOURCE_FAILURE_" + str(wire.status))
            while clock.mono() < store.get_value("next_allowed_mono", 0):
                transport.active()
                if stop.is_set() or (root / "STOP").exists():
                    raise PublicStop("EMERGENCY_STOP")
                clock.sleep(min(0.2, (store.get_value("next_allowed_mono") - clock.mono()) / 1000))
        raise PublicStop("RETRY_EXHAUSTED")

    try:
        with own_signals(stop):
            transport.start_watchdog()
            if verify_docs:
                documentation = transport.verify_documents()
            meta = call("binance_usdm_exchange_info", {})
            caps = [
                int(x["limit"])
                for x in meta.payload.get("rateLimits", [])
                if x.get("rateLimitType") == "REQUEST_WEIGHT"
                and x.get("interval") == "MINUTE"
                and x.get("intervalNum") == 1
                and type(x.get("limit")) is int
            ]
            if not caps or min(caps) <= 10:
                raise PublicStop("NATIVE_IP_CEILING_UNQUALIFIED_OR_TOO_LOW")
            effective = min(60, min(caps))
            guard.policy = guard.policy.model_copy(update={"ip_weight_per_minute": effective})
            store.set_value(
                "native_ip_weight_ceiling",
                {"venue": min(caps), "effective": effective, "bootstrap_weight": 1},
            )
            call("binance_usdm_server_time", {})
            if hasattr(clock, "sample"):
                # Two independently timed probes; each is charged to the same
                # aggregate/endpoint budget, including failures and retries.
                clock.sleep(0.01)
                call("binance_usdm_server_time", {})
            if bound_scope and (
                not isinstance(engine.estimate, dict)
                or len(engine.native_probes) < 2
                or engine.estimate["uncertainty_ms"] > domain.MAX_UNCERTAINTY_MS
            ):
                raise PublicStop("SESSION02_STARTUP_CLOCK_PROBES_UNQUALIFIED")
            if bound_scope and (
                engine.native_probes[1]["request"]["mono_before_ms"]
                - engine.native_probes[0]["available"]["mono_after_ms"]
                < 10
            ):
                raise PublicStop("SESSION02_PROBE_SEPARATION_BELOW_10MS")
            transport.open_group("public")
            # Two bounded startup control messages already consumed in the first second.
            for _ in range(6):
                transport.active()
                clock.sleep(0.2)
            if not clock_only:
                transport.open_group("market")
            now = clock.mono()
            due = {
                "metadata": now + 3500000,
                "time": now + 120000,
                "funding": now,
                "oi": now,
                "premium": now,
                "turnover": now,
            }
            if clock_only:
                due = {"time": now + 120000}
            turnover_index = 0
            opened = now
            while True:
                remaining = transport.active()
                if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 > 1024**3:
                    raise PublicStop("PROCESS_MEMORY_CAP_EXCEEDED")
                if remaining <= 0.6:
                    break
                if stop.is_set() or (root / "STOP").exists():
                    raise PublicStop("EMERGENCY_STOP")
                item = transport.next(0.05)
                if item:
                    engine.ingest(item)
                    if item.endpoint_id == "source_failure":
                        if item.error != "WS_DISCONNECT":
                            raise PublicStop(item.error or "WS_SOURCE_FAULT")
                        engine.outage(item.symbol, clock.wall())
                        transport.close_group(item.symbol)
                        # A bounded native reconnect. Unknown transport failures never imply terms denial.
                        for _ in range(6):
                            transport.active()
                            clock.sleep(0.2)
                        transport.open_group(item.symbol, reconnect=True)
                engine.tick(clock.wall())
                if clock.mono() - engine.last_flush >= 2000:
                    engine.flush()
                if long_engine is not None:
                    long_engine.maintenance()
                now = clock.mono()
                if now - opened >= 23 * 3600000:
                    for group in ("public",) if clock_only else ("public", "market"):
                        engine.outage(group, clock.wall())
                        transport.close_group(group)
                        for _ in range(6):
                            transport.active()
                            clock.sleep(0.2)
                        transport.open_group(group, reconnect=True)
                    opened = clock.mono()
                for name in tuple(due):
                    if now < due[name]:
                        continue
                    if name == "metadata":
                        call("binance_usdm_exchange_info", {})
                        due[name] = now + 3500000
                    elif name == "time":
                        call("binance_usdm_server_time", {})
                        due[name] = now + 120000
                    elif name == "funding":
                        call("binance_usdm_funding_info", {})
                        due[name] = now + 300000
                    elif name in ("oi", "premium"):
                        for symbol in SYMBOLS:
                            call("binance_usdm_" + name, {"symbol": symbol})
                        due[name] = now + 60000
                    else:
                        call("binance_usdm_turnover", {"symbol": SYMBOLS[turnover_index % 3]})
                        turnover_index += 1
                        due[name] = now + 100000
                if engine.repairs and not clock_only and (long_engine is None or long_engine.repair_ready()):
                    symbol, interval, start, end = engine.repairs.popleft()
                    end = min(end, (clock.wall() // interval) * interval - 1, end_ms - 1)
                    if start <= end:
                        # Repair only this granted future window, in bounded closed-bar batches.
                        finish = min(end, start + 99 * interval - 1)
                        call(
                            "binance_usdm_klines_rest",
                            {
                                "symbol": symbol,
                                "interval": "1m" if interval == MINUTE else "5m",
                                "startTime": max(start_ms, start),
                                "endTime": finish,
                                "limit": 99,
                            },
                        )
                        if finish < end:
                            engine.repairs.appendleft((symbol, interval, finish + 1, end))
                if item is None:
                    clock.sleep(min(0.05, max(0, remaining - 0.6)))
    except Exception as exc:
        reason = str(exc) if isinstance(exc, (PublicStop, ValueError, RuntimeError)) else type(exc).__name__
        if long_duration and any(x in reason for x in ("CLOCK", "EPOCH")):
            engine.invalidate_clock(reason, domain.capture(clock)[2])
    finally:
        engine.advisory_enabled = False
        finalization_errors = []
        try:
            transport.close()
        except Exception as exc:
            finalization_errors.append("SHUTDOWN_INCOMPLETE:" + str(exc))
            reason += "|SHUTDOWN_INCOMPLETE"
        # Persist already received frames after acquisition closes; do not publish new actionable advice.
        try:
            while True:
                item = transport.next(0)
                if item is None:
                    break
                engine.ingest(item)
            engine.flush()
        except Exception as exc:
            finalization_errors.append(str(exc))
            reason += "|RECEIPT_FINALIZATION_INCOMPLETE"
        ended = clock.wall()
        capture_cpu = time.process_time() - cpu_started
        replay_cpu_start = time.process_time()
        try:
            replay = journal.audit_replay(normalize)
        except Exception as exc:
            replay = {"status": "INTEGRITY_FAILED", "error": str(exc)}
            reason = reason + "|FINALIZATION_INTEGRITY_FAILED"
        model = engine.report()
        shutdown_ok = not transport.connections and all(not t.is_alive() for t in transport.threads)
        qualification = terminal_qualification(
            model, replay, reason, finalization_errors, transport.exposure, shutdown_ok, len(engine.pending)
        )
        result = {
            "status": "BLOCKED"
            if reason in ("VENUE_ACCESS_DENIED", "TERMS_CONFLICT", "RATE_LIMIT_CIRCUIT_OPEN")
            else "SOURCE_QUALIFIED"
            if qualification["source_qualified"]
            else "PARTIAL",
            "stop_reason": reason,
            "owner": scope.grant.grant_id,
            "scope_hash": scope.hash,
            "started_wall_ms": started,
            "stopped_wall_ms": ended,
            "authorized_start_ms": start_ms,
            "authorized_end_exclusive_ms": end_ms,
            "late_start_ms": max(0, started - start_ms),
            "shortened_coverage": started > start_ms,
            "operator_process_elapsed_ms": max(0, ended - started),
            "actual_receive_span_ms": engine.last_received - engine.first_received
            if engine.first_received is not None
            else None,
            "exposure": transport.exposure,
            "documentation_recheck": documentation,
            "documentation_validation_mode": "LOCAL_REVIEWED_BASELINE",
            "transport_metrics": transport.metrics,
            "transport_count_semantics": "REST calls are attempts charged before I/O; successful responses and WS upgrades are counted separately. Control counts are attempted protocol messages, not delivery acknowledgements.",
            "native_market_requests": transport.metrics["rest_requests"]
            if transport.exposure == "PUBLIC_CANARY"
            else 0,
            "model": model,
            "replay": replay,
            "storage_usage": journal.used(),
            "resource_usage": {
                "capture_process_cpu_seconds": capture_cpu,
                "final_replay_cpu_seconds": time.process_time() - replay_cpu_start,
                "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "memory_cap_bytes": 1024**3,
                "scope": "Current finite process; synthetic in-process tests also include test harness RSS",
            },
            "finalization_errors": finalization_errors,
            "uncommitted_or_unapplied_frames": len(engine.pending),
            "sockets_closed": not transport.connections,
            "receiver_threads_stopped": all(not t.is_alive() for t in transport.threads),
            **qualification,
            "operator_expiry_cleanup_required": True,
            "external_notifications": 0,
            "account_or_order_operations": 0,
        }
        if clock_only:
            clock_status = (
                "BLOCKED"
                if reason in ("VENUE_ACCESS_DENIED", "TERMS_CONFLICT", "RATE_LIMIT_CIRCUIT_OPEN")
                else ("SYNTHETIC_REPLAY_VERIFIED" if synthetic else "CLOCK_VALIDATION_ONLY")
                if reason in ("AUTHORIZED_UTC_END", "GRANT_WINDOW_EXPIRED", "SESSION02_GRANT_EXPIRED")
                and not finalization_errors
                else "PARTIAL"
            )
            result.update(
                session_id=scope.raw["session_id"],
                run_profile="CLOCK_VALIDATION_ONLY",
                operator_monotonic_elapsed_ms=clock.mono() - started_mono,
                absolute_outer_end_unchanged_ms=END,
                actionable_quotes=0,
                source_qualified=False,
                shadow_advisory_qualified=False,
                economically_validated=False,
                status=clock_status,
                clock_validation_evidence={
                    "independent_probes": len(engine.native_probes),
                    "distinct_qualified_quotes": dict(engine.quote_counts),
                    "clock_fault": engine.clock_fault,
                    "not_a_strategy_or_full_source_qualification": True,
                },
            )
        if long_duration:
            from .longhorizon_acceptance import tier_outcomes, replay_outcomes

            model["three_tier_acceptance"] = tier_outcomes(model, replay)
            model["storage"].update(replay_outcomes(replay))
            result.update(session_id=scope.raw["session_id"], run_profile=scope.run_profile,
                          operator_monotonic_elapsed_ms=clock.mono() - started_mono)
        try:
            if long_duration:
                from .longhorizon_runtime import save_dashboard

                save_dashboard(root, result, producer=engine)
            save_reports(root, result)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
    return result
