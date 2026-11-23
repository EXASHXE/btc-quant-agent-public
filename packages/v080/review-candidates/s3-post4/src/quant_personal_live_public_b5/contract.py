"""Pinned public route and release contracts shared by the B5 boundaries."""

import re
from dataclasses import dataclass

from quant_personal_public_b1.policy import require
from quant_personal_public_bridge_b4.routes import (
    FUNDING, HOST, INTERVALS, PORT, ROUTES, SYMBOLS, Request as PublicRequest,
)
from quant_personal_public_b1.store import encode, sha

TASK = "V080-PERSONAL-MVP-LIVE-PUBLIC-B5-01"
AUTHORITY = "https://fapi.binance.com:443"
CONTRACT = "USD-M-2026-11-20-B5-V1"
SYMBOL_ORDER = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
SCOPE_SCHEMA = "B5_OWNER_PUBLIC_SCOPE_V1"
APPROVAL_SCHEMA = "B5_DUAL_APPROVAL_V1"
READY = "READY_FOR_ACTIVATION_REVIEW"
DISABLED = "LIVE_CAPABILITY_NOT_ACTIVATED"
GENUINE = "PERSONAL_PUBLIC_MARKET_GENUINE"
QA = "SYNTHETIC_QA_ONLY"
QA_WARNINGS = [QA, "NOT_GENUINE_MARKET"]
GENUINE_RECEIPT = "B5_PUBLIC_GENUINE_RECEIPT_V1"
GENUINE_PUBLICATION = "B5_PUBLIC_GENUINE_PUBLICATION_V1"
QA_RECEIPT = "B5_PUBLIC_QA_RECEIPT_V1"
QA_PUBLICATION = "B5_PUBLIC_QA_PUBLICATION_V1"
ROLLING_MS = 60_000
BASE_MAX_REQUESTS = 48
BASE_MAX_WEIGHT = 64
PRODUCTION_CA = "/etc/ssl/certs/ca-certificates.crt"


def digest(value):
    return sha(encode(value).encode("ascii"))


def sha_text(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def bounded_int(value, lower, upper):
    return type(value) is int and lower <= value <= upper


@dataclass(frozen=True)
class RouteRequest(PublicRequest):
    funding_debit: int | None = None

    def validate(self):
        debit, wire = super().validate()
        if self.route == FUNDING:
            require(bounded_int(self.funding_debit, 0, BASE_MAX_WEIGHT),
                    "FUNDING_WEIGHT_UNRESOLVED")
            debit = self.funding_debit
        return debit, wire

    @property
    def url(self):
        target = self.validate()[1].split(b" ", 2)[1].decode("ascii")
        return AUTHORITY + target
