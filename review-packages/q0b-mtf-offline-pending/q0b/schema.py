"""Versioned values; no platform imports, wall clock, transport, or account access."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import isfinite

from . import VERSION

MINUTE = 60_000
HOUR = 60 * MINUTE
INTERVALS = {"1D": 24 * HOUR, "4H": 4 * HOUR, "1H": HOUR, "15m": 15 * MINUTE, "5m": 5 * MINUTE}
STATES = ("NO_SETUP", "WATCH", "ENTRY_READY", "INVALIDATED", "EXPIRED", "SOURCE_BLOCKED",
          "DATA_UNAVAILABLE", "UNKNOWN")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def finite(*values):
    return all(type(v) in (int, float) and isfinite(v) for v in values)


@dataclass(frozen=True)
class ClockProof:
    """Synthetic exchange-time uncertainty interval, NOT a Strict-clock replacement."""
    exchange_lower_ms: int
    exchange_upper_ms: int
    sampled_ms: int
    strict_ok: bool = True
    authority: str = "SYNTHETIC_STRICT_FIXTURE"


@dataclass(frozen=True)
class Bar:
    symbol: str
    interval: str
    open_ms: int
    end_ms: int  # exclusive; exchange closeTime must equal end_ms - 1
    exchange_close_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    available_ms: int
    received_ms: int
    exchange_observed_lower_ms: int
    closed: bool = True
    revision: int = 0
    provenance: str = "SYNTHETIC_Q0B_V2"
    venue: str = "BINANCE_USDM_OFFLINE"

    @property
    def key(self):
        return self.symbol, self.interval, self.open_ms


@dataclass(frozen=True)
class Batch:
    symbol: str
    interval: str
    bars: tuple[Bar, ...]
    requested_start_ms: int
    requested_end_ms: int
    provenance: str = "SYNTHETIC_Q0B_V2"


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    exchange_ms: int
    available_ms: int
    received_ms: int
    provenance: str = "SYNTHETIC_Q0B_V2"
    venue: str = "BINANCE_USDM_OFFLINE"


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    asof_ms: int
    clock: ClockProof
    batches: tuple[Batch, ...]
    quote: Quote | None = None
    source_veto: bool = False


@dataclass(frozen=True)
class Policy:
    holding_hours: int = 6
    planned_extension_hours: int | None = None
    response_minutes: int = 10
    entry_lifetime_minutes: int = 45
    atr_buffer: float = 0.20
    entry_atr_fraction: float = 0.15
    paper_equity: float = 10_000
    risk_fraction: float = 0.0025
    paper_notional_cap: float = 1_000

    def __post_init__(self):
        if type(self.holding_hours) is not int or not 2 <= self.holding_hours <= 12:
            raise ValueError("HOLD_REQUIRES_2_TO_12_HOURS")
        if (self.planned_extension_hours is not None
                and (type(self.planned_extension_hours) is not int
                     or not self.holding_hours < self.planned_extension_hours <= 24)):
            raise ValueError("EXTENSION_MUST_BE_PREDECLARED_AND_AT_MOST_24H")
        if type(self.response_minutes) is not int or not 5 <= self.response_minutes <= 10:
            raise ValueError("HUMAN_RESPONSE_REQUIRES_5_TO_10_MINUTES")
        # Fixed methodology, not an optimization surface.
        if (self.entry_lifetime_minutes != 45 or self.atr_buffer != 0.20
                or self.entry_atr_fraction != 0.15):
            raise ValueError("FROZEN_V2_GEOMETRY_POLICY")
        if not finite(self.paper_equity, self.risk_fraction, self.paper_notional_cap):
            raise ValueError("FINITE_PAPER_BUDGET_REQUIRED")
        if not (self.paper_equity > 0 and 0 < self.risk_fraction <= 0.01 and self.paper_notional_cap > 0):
            raise ValueError("INVALID_PAPER_BUDGET")


@dataclass(frozen=True)
class Card:
    symbol: str
    asof_ms: int
    arm: str
    state: str
    reasons: tuple[str, ...]
    candidate_id: str | None = None
    plan: dict | None = None
    diagnostics: dict | None = None
    schema: str = VERSION
    synthetic_only: bool = True
    realized_r: None = None

    def to_dict(self):
        return asdict(self)
