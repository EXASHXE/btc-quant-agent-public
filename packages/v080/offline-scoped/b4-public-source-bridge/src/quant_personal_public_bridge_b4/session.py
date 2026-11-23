"""B4 request session using the accepted B1 durable budget and clock primitives."""

from dataclasses import replace

from quant_personal_public_b1.budget import Budget, retry_after
from quant_personal_public_b1.clock import VenueTime
from quant_personal_public_b1.normalize import integer, obj
from quant_personal_public_b1.policy import Policy, SourceBlocked, require
from quant_personal_public_b1.session import GlobalStop, Session as B1Session
from quant_personal_public_b1.wire import Receipt, WireFailure, audit_headers, json_body

from .routes import TIME, Request
from .source import Ledger

POLICY = Policy(max_requests=48, max_weight=64, bootstrap_weight_limit=120,
                scan_timeout_ms=60_000, request_timeout_ms=1500)
LOCAL_LIMITS = {("REQUEST_WEIGHT", 60_000): 120, ("RAW_REQUESTS", 60_000): 96}


class Session(B1Session):
    def __init__(self, scan, clock, identity, transport, ledger: Ledger, started):
        self.ledger = ledger
        budget = Budget(ledger.store, bootstrap=POLICY.bootstrap_weight_limit)
        budget.configure(LOCAL_LIMITS)
        super().__init__(scan, clock, identity, transport, budget, POLICY, started)

    def get(self, route, params) -> Receipt:
        return self.request(Request(route, params))

    def request(self, request: Request) -> Receipt:
        require(type(request) is Request, "INVALID_BRIDGE_REQUEST")
        weight, _ = request.validate()
        self.logical += 1
        for retry in (0, 1):
            issued = self.clock.sample()
            self.time_left(issued)
            if self.count >= self.policy.max_requests or self.weight + weight > self.policy.max_weight:
                raise GlobalStop("LOCAL_SCAN_BUDGET")
            try:
                ident = self.budget.reserve(self.scan, self.logical, retry, request, self.identity.stamp(issued))
            except SourceBlocked as exc:
                raise GlobalStop(exc.code, exc.detail) from exc
            self.count += 1
            self.weight += weight
            sent = self.clock.sample()
            timeout = min(self.time_left(sent), self.policy.request_timeout_ms)
            self.ledger.sent(ident, self.identity, sent)
            try:
                request.validate()
                reply = self.transport.send(request, timeout)
            except (SourceBlocked, OSError) as exc:
                received = self.clock.sample()
                transient = (isinstance(exc, WireFailure) and exc.retryable) or isinstance(exc, TimeoutError)
                code = exc.code if isinstance(exc, SourceBlocked) else "TRANSPORT_FAILURE"
                self.budget.settle(ident, self.identity.stamp(received), None, code)
                self.check_response_time(sent, received, timeout)
                if transient and retry == 0:
                    continue
                if transient:
                    raise SourceBlocked(code) from exc
                raise GlobalStop(code) from exc

            received = self.clock.sample()
            headers = audit_headers(list(reply.headers.items()))
            if reply.status == 429 and retry_after(headers, received.wall_ms) < 1000:
                headers["retry-after"] = "1"
            reply = replace(reply, headers=headers)
            if len(reply.body) > self.policy.max_body_bytes:
                reply = replace(reply, body=b"", encoded_body=None, complete=False, issue="DECODED_PAYLOAD_TOO_LARGE")
            stop = self.budget.settle(ident, self.identity.stamp(received), reply)
            if stop:
                raise GlobalStop(stop)
            self.check_response_time(sent, received, timeout)
            if 300 <= reply.status < 400:
                raise GlobalStop("HTTP_REDIRECT")
            if not reply.complete:
                raise GlobalStop(reply.issue or "INCOMPLETE_REPLY")
            if reply.status in {408, 500, 502, 503, 504}:
                if retry == 0:
                    continue
                raise SourceBlocked("TRANSIENT_HTTP_EXHAUSTED", str(reply.status))
            if reply.status != 200:
                if reply.status == 400 and "symbol" in request.params:
                    raise SourceBlocked("SYMBOL_REQUEST_REJECTED")
                raise GlobalStop(f"HTTP_{reply.status}")
            media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            require(media == "application/json", "UNEXPECTED_CONTENT_TYPE")
            return Receipt(ident, sent, received, json_body(reply.body))
        raise AssertionError("retry loop exhausted")

    def check_response_time(self, sent, received, timeout):
        self.time_left(received)
        self.last = received
        if received.mono_ms - sent.mono_ms > timeout:
            raise GlobalStop("REQUEST_DEADLINE")

    def witness(self) -> tuple[VenueTime, int]:
        receipt = self.get(TIME, {})
        venue_ms = integer(obj(receipt.body).get("serverTime"), "serverTime", minimum=1)
        bracket = VenueTime.bracket(receipt.sent, receipt.received, venue_ms, self.policy)
        require(abs(venue_ms - receipt.received.wall_ms) <= 300_000, "VENUE_CLOCK_OFFSET_UNBOUNDED")
        return bracket, receipt.seq

    def check_budget(self) -> None:
        # The last response can also exhaust the weight window. A zero-debit check
        # reconciles it against every discovered weight ceiling before publication.
        sample = self.clock.sample()
        with self.ledger.store.connect(write=True) as db:
            epoch = self.budget.epoch(db, self.identity.stamp(sample))
            rules = {(kind, window): cap for kind, window, cap in db.execute("SELECT * FROM rules")
                     if kind == "REQUEST_WEIGHT"}
            blocked = self.budget.check_windows(db, epoch["last_mono"], rules, 0)
        if blocked:
            raise GlobalStop(blocked)
