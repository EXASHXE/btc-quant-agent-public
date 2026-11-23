"""One bounded public collection phase. Reuses the pinned B4 candle and context routines."""

from __future__ import annotations

import json
import re
from dataclasses import replace

from quant_personal_public_b1.budget import retry_after
from quant_personal_public_b1.policy import SourceBlocked, require
from quant_personal_public_b1.runtime import checked_projection
from quant_personal_public_b1.session import GlobalStop, Session as B1Session
from quant_personal_public_b1.store import sha
from quant_personal_public_b1.wire import Receipt, Reply, WireFailure, audit_headers, json_body
from quant_personal_public_bridge_b4 import normalize as norm
from quant_personal_public_bridge_b4.collector import bar_window, read_observations
from quant_personal_public_bridge_b4.session import POLICY, Session as CausalSession

from .contract import (
    CONTRACT, GENUINE, GENUINE_RECEIPT, INTERVALS, QA_RECEIPT, SYMBOL_ORDER, PublicRequest, RouteRequest, digest,
)
from .egress import PhysicalProof, PhysicalTransport, check_local_route
from .ledger import Active

from quant_personal_public_bridge_b4.routes import INSTRUMENTS, QUOTE, TIME

MILLISECONDS = {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
HINT = re.compile(r"x-mbx-used-weight-([0-9]{1,4})([smhd])")


def issue_of(exc):
    category = "CLOCK_BLOCKED" if any(s in exc.code for s in ("CLOCK", "MONOTONIC")) else "SOURCE_BLOCKED"
    return {"category": category, "code": exc.code, "detail": exc.detail}


class WeightWitness:
    def __init__(self):
        self.previous = {}
        self.required_windows = None

    @staticmethod
    def counters(reply):
        return {int(match[1])*MILLISECONDS[match[2]]: int(value) for name, value in reply.headers.items()
                if (match := HINT.fullmatch(name)) and 0 < int(match[1])*MILLISECONDS[match[2]] <= 86_400_000}

    def learn(self, rules):
        self.required_windows = {window for kind, window in rules if kind == "REQUEST_WEIGHT"}
        require(self.required_windows <= self.previous.keys(), "VENUE_LIMIT_HEADER_WINDOW_UNOBSERVED")

    def observe(self, route, reply, spent, venue_bounds):
        if route == QUOTE:
            return
        counts = self.counters(reply)
        require(bool(counts) and (self.required_windows is None or self.required_windows <= counts.keys()),
                "TRUSTED_WEIGHT_HEADER_MISSING")
        for window, used in counts.items():
            previous = self.previous.get(window)
            current_slot = (venue_bounds or (None, None))
            if previous:
                older, old_spent, old_slot = previous
                require(used-older <= spent-old_spent, "SHARED_EGRESS_WEIGHT_JUMP")
                if None not in (*current_slot, *old_slot):
                    stable = len({x // window for x in (*current_slot, *old_slot)}) == 1
                    require(not stable or used >= older, "VENUE_WEIGHT_COUNTER_REGRESSED")
            self.previous[window] = (used, spent, current_slot)


class Session(CausalSession):
    def __init__(self, active, phase, scan, started, transport):
        self.active, self.phase, self.ledger = active, phase, active.ledger
        B1Session.__init__(self, scan, active.clock, active.identity, transport, active.budget, POLICY, started)
        self.headers = WeightWitness()
        self.first_clock = None

    def get(self, route, params):
        return self.request(RouteRequest(route, params, funding_debit=self.active.approval.scope.funding_debit))

    def request(self, request):
        require(type(request) in (RouteRequest, PublicRequest), "INVALID_B5_REQUEST")
        # B4 observation_query returns a B4 Request. Always reconstruct B5's
        # immutable route request with the reviewed debit.
        request = RouteRequest(request.route, request.params, request.method, request.host, request.port,
                               self.active.approval.scope.funding_debit)
        weight, wire = request.validate()
        self.logical += 1
        plan = self.active.approval.scope.stage_plan
        retry_allowed = plan is None or (self.logical > 2 and plan.market_retry_limit == 1)
        attempts = (0,1) if retry_allowed else (0,)
        for retry in attempts:
            now = self.clock.sample()
            self.time_left(now)
            try:
                if self.ledger.origin == GENUINE:
                    check_local_route(self.active.approval.scope.route)
                ident = self.active.reserve(self.phase, self.scan, self.logical, retry, request, now)
            except SourceBlocked as exc:
                raise GlobalStop(exc.code, exc.detail) from exc
            self.count += 1
            self.weight += weight
            sent = self.clock.sample()
            left = min(self.time_left(sent), self.policy.request_timeout_ms)
            self.ledger.sent(ident, self.identity, sent)
            physical = None
            try:
                self.active.assert_pending(ident, request)
                if self.ledger.origin == GENUINE:
                    require(type(self.transport) is PhysicalTransport, "PRODUCTION_TRANSPORT_REQUIRED")
                    result = self.transport.send(request, left, ident)
                    require(type(result) is PhysicalProof and result.reservation == ident
                            and result.wire_sha == sha(wire), "UNQUALIFIED_PHYSICAL_PROOF")
                    physical = result
                    reply = result.response
                    require(reply.tls is not None, "UNQUALIFIED_PHYSICAL_PROOF")
                else:
                    reply = self.transport.send(request, left)
                require(type(reply) is Reply, "INVALID_TRANSPORT_REPLY")
            except (SourceBlocked, OSError) as exc:
                received = self.clock.sample()
                reason = exc.code if isinstance(exc, SourceBlocked) else "TRANSPORT_FAILED"
                self.budget.settle(ident, self.identity.stamp(received), None, reason)
                self.check_response_time(sent, received, left)
                if isinstance(exc, WireFailure) and exc.retryable and retry == 0 and retry_allowed:
                    continue
                raise GlobalStop(reason) from exc

            received = self.clock.sample()
            headers = audit_headers(list(reply.headers.items()))
            if reply.status == 429 and retry_after(headers, received.wall_ms) < 1000:
                headers["retry-after"] = "1"
            reply = replace(reply, headers=headers)
            if len(reply.body) > self.policy.max_body_bytes:
                reply = replace(reply, body=b"", encoded_body=None, complete=False, issue="DECODED_PAYLOAD_TOO_LARGE")
            stop = self.budget.settle(ident, self.identity.stamp(received), reply)
            proof = {"schema": GENUINE_RECEIPT if self.ledger.origin == GENUINE else QA_RECEIPT,
                     "origin": self.ledger.origin, "run_id": self.ledger.run_id, "phase": self.phase,
                     "scan_id": self.scan, "attempt": ident, "request": request.data(), "url": request.url,
                     "wire_sha256": sha(wire), "planned_weight": weight,
                     "signed_sha256": self.ledger.signed_sha, "status": reply.status,
                     "headers": dict(reply.headers), "tls": reply.tls,
                     "raw_sha256": sha(reply.body) if reply.complete else None,
                     "encoded_sha256": sha(reply.encoded_body) if reply.encoded_body is not None else None,
                     "wire_bytes": reply.wire_bytes, "issue": reply.issue,
                     "request_start": self.identity.stamp(sent).data(), "receive": self.identity.stamp(received).data()}
            self.ledger._record_receipt(ident, proof, physical)
            if stop:
                raise GlobalStop(stop)
            self.check_response_time(sent, received, left)
            if 300 <= reply.status < 400:
                raise GlobalStop("HTTP_REDIRECT")
            if not reply.complete:
                raise GlobalStop(reply.issue or "HTTP_BODY_INCOMPLETE")
            if reply.status in {408, 500, 502, 503, 504}:
                if retry == 0 and retry_allowed:
                    continue
                raise GlobalStop("TRANSIENT_HTTP_EXHAUSTED", str(reply.status))
            if reply.status == 400 and "symbol" in request.params:
                raise SourceBlocked("SYMBOL_REQUEST_REJECTED")
            if reply.status != 200:
                raise GlobalStop(f"HTTP_{reply.status}")
            bounds = None
            if self.first_clock is not None:
                seen = checked_projection(self.first_clock, received, self.policy)
                bounds = (seen.lower_ms, seen.upper_ms)
            elif request.route == TIME:
                reported = norm.n.integer(norm.n.obj(json_body(reply.body)).get("serverTime"), "serverTime", minimum=1)
                bounds = (reported-1, reported+(received.mono_ms-sent.mono_ms)+2)
            try:
                self.headers.observe(request.route, reply, self.weight, bounds)
            except SourceBlocked as exc:
                raise GlobalStop(exc.code, exc.detail) from exc
            require(headers.get("content-type", "").split(";",1)[0].strip().lower() == "application/json",
                    "UNEXPECTED_CONTENT_TYPE")
            return Receipt(ident, sent, received, json_body(reply.body))
        raise AssertionError("retry loop exhausted")

    def check_headroom(self):
        sample = self.clock.sample()
        with self.ledger.store.connect(write=True) as db:
            epoch = self.budget.epoch(db, self.identity.stamp(sample))
            rules = {(kind, window): cap-self.active.approval.scope.headroom_weight
                     for kind, window, cap in db.execute("SELECT * FROM rules") if kind == "REQUEST_WEIGHT"}
            blocked = self.budget.check_windows(db, epoch["last_mono"], rules, 0)
        if blocked:
            raise GlobalStop(blocked)


def _take_sources(session, first, first_id, symbols, stage, *, bootstrap, notify_stage):
    ledger = session.ledger
    previous = {symbol: ledger.prior_observations(symbol) for symbol in symbols}
    need_meta = bootstrap or any(
        "instrument" not in old or first.upper_ms-old["instrument"]["received_venue_lower_ms"]
        > norm.REFRESH_MS["instrument"] for old in previous.values()
    )
    meta = session.get(INSTRUMENTS,{}) if need_meta else None
    if meta:
        limits = norm.venue_limits(meta.body)
        session.headers.learn(limits)
        session.budget.configure(limits)
        session.check_headroom()
        if bootstrap:
            # Validate the canary before issuing any candle or fast GET.
            norm.n.exchange_info(meta.body, symbols)
        plan = session.active.approval.scope.stage_plan
        if plan is not None:
            stage["activation_gate"] = session.active.pass_canary(session.scan,first_id,meta.seq,first.evidence())
            if not plan.market_allowed:
                stage["market_status"] = "NOT_EVALUATED"
                return {}
            if notify_stage is not None:
                notify_stage()
    else:
        with ledger.store.connect() as db:
            native = db.execute("SELECT payload FROM b5_receipts a JOIN attempts t ON t.id=a.attempt "
                                "WHERE t.route=? AND t.raw IS NOT NULL AND t.response IS NOT NULL "
                                "AND json_extract(a.payload,'$.status')=200 ORDER BY t.id DESC LIMIT 1",
                                (INSTRUMENTS,)).fetchone()
        require(native is not None, "EXCHANGE_INFO_REQUIRED")
        meta_receipt = json.loads(native["payload"])["attempt"]
        session.headers.learn(norm.venue_limits(json_body(ledger.store.raw(meta_receipt))))
    edits = {}
    for symbol in symbols:
        market = stage["markets"][symbol] = {"frames": {}, "observations": {}, "issue": None}
        edits[symbol] = []
        for frame in INTERVALS:
            try:
                market["frames"][frame], revised = bar_window(session, symbol, frame, first)
                edits[symbol].extend(revised)
            except GlobalStop:
                raise
            except SourceBlocked as exc:
                market["issue"] = issue_of(exc)
                break
    for symbol, market in stage["markets"].items():
        if not market["issue"]:
            try:
                market["observations"] = read_observations(session, symbol, first, previous[symbol], meta)
            except GlobalStop:
                raise
            except SourceBlocked as exc:
                market["issue"] = issue_of(exc)
    return edits


def collect(active: Active, phase, transport, symbols=SYMBOL_ORDER, *, notify_stage=None):
    require(type(active) is Active, "ACTIVE_REQUIRED")
    if active.ledger.origin == GENUINE:
        require(type(transport) is PhysicalTransport and transport.active is active
                and symbols == SYMBOL_ORDER, "PRODUCTION_TRANSPORT_REQUIRED")
    scan, start = active.begin_phase(phase)
    session = Session(active, phase, scan, start, transport)
    stage = {"markets": {}, "issue": None, "clock": None, "symbols": list(symbols), "stats": {}}
    ref, changes = None, []
    try:
        first, first_id = session.witness()
        session.first_clock = first
        edits = _take_sources(session, first, first_id, symbols, stage, bootstrap=phase == "bootstrap",
                              notify_stage=notify_stage)
        if stage.get("market_status") == "NOT_EVALUATED":
            stage["clock"] = {"first_id": first_id, "first": first.evidence()}
        else:
            last, last_id = session.witness()
            ref = first.reconcile(last, POLICY)
            stage["clock"] = {"first_id": first_id, "last_id": last_id, "first": first.evidence(),
                              "last": last.evidence(), "reconciled": ref.evidence()}
            session.check_headroom()
            for symbol, market in stage["markets"].items():
                if not market["issue"]:
                    try:
                        for name, observation in market["observations"].items():
                            norm.validate_age(name, observation, ref.upper_ms)
                        changes.extend(edits[symbol])
                    except SourceBlocked as exc:
                        market["issue"] = issue_of(exc)
    except SourceBlocked as exc:
        ref, changes = None, []
        stage.update(issue=issue_of(exc), markets={})
    stage["stats"] = {"reserved_requests": session.count, "reserved_weight": session.weight,
                      "trusted_headers": {str(w): info[0] for w, info in session.headers.previous.items()}}
    ledger, clock, identity = active.ledger, active.clock, active.identity
    staged = clock.sample()
    if ref is not None:
        session.time_left(staged)
    ledger.store.stage(scan, stage, changes)
    commit = clock.sample()
    started = clock.sample()
    if ref is not None:
        session.time_left(started)
    durable_upper = checked_projection(ref, commit, POLICY).upper_ms if ref else None
    publishing_upper = checked_projection(ref, started, POLICY).upper_ms if ref else None
    payload = {"schema": ledger.schema, "origin": ledger.origin, "contract": CONTRACT, "warnings": ledger.warnings,
               "run_id": ledger.run_id, "signed_sha256": ledger.signed_sha,
               "lineage": ledger.lineage, "scan_id": scan, "phase": phase, "stage_sha256": digest(stage), "stage": stage,
               "stage_start": identity.stamp(staged).data(), "commit_observed": identity.stamp(commit).data(),
               "publication_started": identity.stamp(started).data(), "durable_venue_upper_ms": durable_upper,
               "visible_venue_upper_ms": publishing_upper}
    ledger.store.publish(scan, payload, identity.stamp(started), publishing_upper)
    published = clock.sample()
    if ref is not None:
        session.time_left(published)
    upper = checked_projection(ref, published, POLICY).upper_ms if ref else None
    ledger.record_visibility(scan, identity.stamp(published), upper)
    if stage["issue"]:
        active.close(reason=stage["issue"]["code"])
    return ledger.publication(scan)[0]
