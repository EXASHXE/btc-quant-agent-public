"""Socket-free scripted interfaces. There is deliberately no live implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from .clocks import Capture
from .policy import Endpoint, Policy, SourceGrant


class NetworkDisabled(RuntimeError):
    pass


@dataclass(frozen=True)
class Frame:
    endpoint_id: str
    provider: str
    host: str
    market: str
    symbol: str
    payload_json: str
    capture: Capture
    native_units: tuple[tuple[str, str], ...]
    epoch: int = 0
    status: int = 200
    error: str | None = None
    exposure: str = "SYNTHETIC"

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def payload_sha256(self):
        return sha256(self.payload_json.encode()).hexdigest()


class Transport(Protocol):
    def receive(self, endpoint: Endpoint, symbol: str, now_ms: int) -> Frame: ...
    def close(self) -> None: ...


class DisabledPublicTransport:
    """Even a purported grant cannot enable Phase A network access."""

    def __init__(self, grant: SourceGrant | None = None):
        self.grant = grant

    def receive(self, endpoint: Endpoint, symbol: str, now_ms: int) -> Frame:
        raise NetworkDisabled("PHASE_A_NETWORK_DISABLED; real transport is not implemented")

    def close(self):
        return None


class ScriptedTransport:
    def __init__(self, frames: tuple[Frame, ...], policy: Policy):
        if any(f.exposure != "SYNTHETIC" for f in frames):
            raise ValueError("ONLY_FABRICATED_FRAMES_ALLOWED")
        self.frames, self.policy = frames, policy
        self.index, self.closed, self.receive_calls = 0, False, 0

    def receive(self, endpoint: Endpoint, symbol: str, now_ms: int) -> Frame:
        if now_ms >= self.policy.end_ms:
            self.close()
            raise NetworkDisabled("CANARY_UTC_END_REACHED")
        if self.closed or now_ms < self.policy.synthetic_start_ms:
            raise NetworkDisabled("CANARY_CLOSED_OR_NOT_STARTED")
        if self.index >= len(self.frames):
            raise EOFError("SCRIPTED_SOURCE_EXHAUSTED")
        f = self.frames[self.index]
        if f.endpoint_id != endpoint.id or f.symbol != symbol:
            raise ValueError("SCRIPTED_REQUEST_BINDING_MISMATCH")
        self.index += 1
        self.receive_calls += 1
        return f

    def close(self):
        self.closed = True
