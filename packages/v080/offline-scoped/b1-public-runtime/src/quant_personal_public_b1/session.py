"""One bounded, auditable unsigned scan session."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .budget import Budget
from .clock import Clock, Sample, VenueTime, check_elapsed
from .normalize import integer, obj
from .policy import TIME, Policy, SourceBlocked, require
from .store import Stamp
from .wire import (
    Params,
    Receipt,
    Request,
    Transport,
    WireFailure,
    audit_headers,
    json_body,
)


class GlobalStop(SourceBlocked):
    """The entire collection is invalid, regardless of previously read symbols."""


@dataclass(frozen=True)
class RunIdentity:
    boot: str
    session: str

    def stamp(self, sample: Sample) -> Stamp:
        return Stamp.capture(self.boot, self.session, sample)


class Session:
    def __init__(self, scan: int, clock: Clock, identity: RunIdentity, transport: Transport,
                 budget: Budget, policy: Policy, started: Sample) -> None:
        self.scan = scan
        self.clock = clock
        self.identity = identity
        self.transport = transport
        self.budget = budget
        self.policy = policy
        self.started = self.last = started
        self.count = self.weight = self.logical = 0

    def time_left(self, now: Sample) -> int:
        try:
            check_elapsed(self.started, now, self.policy)
            check_elapsed(self.last, now, self.policy)
        except SourceBlocked as exc:
            raise GlobalStop(exc.code) from exc
        left = self.policy.scan_timeout_ms - (now.mono_ms - self.started.mono_ms)
        if left <= 0:
            raise GlobalStop("SCAN_DEADLINE")
        return left

    def get(self, route: str, params: Params) -> Receipt:
        request = Request(route, params)
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
            try:
                reply = self.transport.send(request, timeout)
            except (WireFailure, OSError) as exc:
                received = self.clock.sample()
                transient = (exc.retryable if isinstance(exc, WireFailure)
                             else isinstance(exc, (TimeoutError, ConnectionResetError, ConnectionAbortedError)))
                reason = exc.code if isinstance(exc, WireFailure) else (
                    "TRANSIENT_WIRE_FAILURE" if transient else "TRANSPORT_UNAVAILABLE")
                self.budget.settle(ident, self.identity.stamp(received), None, reason)
                self.time_left(received)
                self.last = received
                if transient and retry == 0:
                    continue
                if transient:
                    raise SourceBlocked(reason) from exc
                raise GlobalStop(reason) from exc
            except SourceBlocked as exc:
                received = self.clock.sample()
                self.budget.settle(ident, self.identity.stamp(received), None, exc.code)
                self.time_left(received)
                self.last = received
                raise GlobalStop(exc.code) from exc

            received = self.clock.sample()
            reply = replace(reply, headers=audit_headers(list(reply.headers.items())))
            if len(reply.body) > self.policy.max_body_bytes:
                reply = replace(reply, body=b"", encoded_body=None, complete=False, issue="DECODED_PAYLOAD_TOO_LARGE")
            stop = self.budget.settle(ident, self.identity.stamp(received), reply)
            self.time_left(received)
            self.last = received
            if stop:
                raise GlobalStop(stop)
            if not reply.complete:
                raise GlobalStop(reply.issue or ("HTTP_REDIRECT" if 300 <= reply.status < 400 else "INCOMPLETE_REPLY"))
            if received.mono_ms - sent.mono_ms > timeout:
                raise GlobalStop("REQUEST_DEADLINE")
            if reply.status in {500, 502, 503, 504}:
                if retry == 0:
                    continue
                raise SourceBlocked("TRANSIENT_HTTP_EXHAUSTED", str(reply.status))
            if reply.status == 400 and "symbol" in params and reply.body:
                try:
                    invalid = obj(json_body(reply.body)).get("code") == -1121
                except SourceBlocked:
                    invalid = False
                if invalid:
                    raise SourceBlocked("INSTRUMENT_VENUE_REJECTED", str(params["symbol"]))
            if reply.status != 200:
                raise GlobalStop(f"HTTP_{reply.status}")
            media = reply.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            require(media == "application/json", "UNEXPECTED_CONTENT_TYPE")
            return Receipt(ident, sent, received, json_body(reply.body))
        raise AssertionError("retry loop exhausted")

    def witness(self) -> tuple[VenueTime, int]:
        receipt = self.get(TIME, {})
        venue_ms = integer(obj(receipt.body).get("serverTime"), "serverTime", minimum=1)
        return VenueTime.bracket(receipt.sent, receipt.received, venue_ms, self.policy), receipt.seq
