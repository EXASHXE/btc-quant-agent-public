"""B4's physical adapter is restricted to an injected local TLS test listener."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from quant_personal_public_b1.policy import require
from quant_personal_public_b1.wire import HttpsTransport, LoopbackTarget, Reply, WireLimits

from .routes import Request

FIXTURE = "FIXTURE"
LOOPBACK = "LOOPBACK_HTTPS_QA"
GENUINE = "GENUINE_PUBLIC_MARKET"
WARNINGS = ("SYNTHETIC_QA_ONLY", "NOT_GENUINE_MARKET")


class Adapter(Protocol):
    def send(self, request: Request, timeout_ms: int) -> Reply: ...


@dataclass(frozen=True)
class LoopbackHTTPS:
    port: int
    qa_ca_file: Path

    def send(self, request: Request, timeout_ms: int) -> Reply:
        require(type(request) is Request, "INVALID_BRIDGE_REQUEST")
        request.validate()
        target = LoopbackTarget("127.0.0.1", self.port, self.qa_ca_file)
        # B1 validates this target again before opening a socket. SNI is pinned even in QA.
        return HttpsTransport(target, WireLimits()).send(request, timeout_ms)
