from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class Regime(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    TRANSITION = "TRANSITION"


class Setup(StrEnum):
    TREND_PULLBACK = "TREND_PULLBACK"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"


class SignalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    RESOLVED_WIN = "RESOLVED_WIN"
    RESOLVED_LOSS = "RESOLVED_LOSS"
    RESOLVED_TIMEOUT = "RESOLVED_TIMEOUT"


class UserDecision(StrEnum):
    ACCEPT = "ACCEPT"
    IGNORE = "IGNORE"


class RuntimeStage(StrEnum):
    NO_OPPORTUNITY = "NO_OPPORTUNITY"
    OPPORTUNITY_ONLY = "OPPORTUNITY_ONLY"
    DIRECTION_CANDIDATE = "DIRECTION_CANDIDATE"
    TRADEABLE_CANDIDATE = "TRADEABLE_CANDIDATE"
    ACTIONABLE_SIGNAL = "ACTIONABLE_SIGNAL"


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0
    taker_buy_base_volume: float = 0.0
    trades: int = 0
    closed: bool = True
    available_at_ms: int | None = None

    def __post_init__(self) -> None:
        if type(self.closed) is not bool:
            raise TypeError("closed must be a boolean")
        if self.close_time_ms <= self.open_time_ms:
            raise ValueError("close_time_ms must be after open_time_ms")
        for name in (
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "taker_buy_base_volume",
        ):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("invalid OHLC bounds")
        if (
            self.low > self.high
            or min(self.volume, self.quote_volume, self.taker_buy_base_volume) < 0
        ):
            raise ValueError("invalid candle")
        if self.available_at_ms is not None and (
            type(self.available_at_ms) is not int or self.available_at_ms <= 0
        ):
            raise ValueError("available_at_ms must be a positive integer when provided")


@dataclass(frozen=True)
class DerivativesSnapshot:
    observed_at_ms: int
    mark_price: float | None = None
    funding_rate: float | None = None
    funding_time_ms: int | None = None
    open_interest: float | None = None
    open_interest_time_ms: int | None = None
    taker_buy_sell_ratio: float | None = None
    taker_time_ms: int | None = None
    index_price: float | None = None
    premium_bps: float | None = None
    basis_rate: float | None = None
    basis_time_ms: int | None = None
    open_interest_change_pct: float | None = None
    long_short_account_ratio: float | None = None
    long_short_time_ms: int | None = None
    order_book_imbalance: float | None = None
    spread_bps: float | None = None
    order_book_time_ms: int | None = None


@dataclass(frozen=True)
class Pivot:
    kind: str
    pivot_index: int
    confirmed_index: int
    price: float
    open_time_ms: int


@dataclass(frozen=True)
class TimeframeFeatures:
    close: float
    ema_fast: float
    ema_mid: float
    ema_slow: float
    ema_mid_slope: float
    ema_slow_slope: float
    atr: float
    atr_percentile: float
    adx: float
    volume_z: float
    rsi: float
    roc: float
    bb_width_percentile: float
    cvd_slope: float
    cvd_available: bool
    last_swing_high: float | None
    previous_swing_high: float | None
    last_swing_low: float | None
    previous_swing_low: float | None
    structure: str
    bar_open_time_ms: int
    bar_close_time_ms: int


@dataclass(frozen=True)
class Candidate:
    direction: Direction
    setup: Setup
    entry_low: float
    entry_high: float
    invalidation_level: float
    target_level: float
    pattern_score: int
    structure_id: str
    reasons: tuple[str, ...]
    risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionPlan:
    entry_reference: float
    stop_loss: float
    take_profit: float
    rr_gross: float
    rr_net: float
    risk_usdt: float
    recommended_notional: float
    required_margin: float
    estimated_fee_usdt: float
    estimated_slippage_usdt: float
    estimated_funding_usdt: float


@dataclass(frozen=True)
class OpportunityEvidence:
    opportunity_id: str
    symbol: str
    detector_id: str
    setup: Setup
    detected_at_ms: int
    data_timestamp_ms: int
    expires_at_ms: int
    regime: Regime
    research_status: str
    runtime_eligibility: str
    movement_evidence: tuple[str, ...]
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    legacy_pattern_side: Direction
    legacy_side_is_actionable: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("setup", "regime", "legacy_pattern_side"):
            payload[key] = str(payload[key])
        return payload


@dataclass
class Signal:
    signal_id: str
    fingerprint: str
    strategy_version: str
    feature_version: str
    model_version: str | None
    config_hash: str
    validation_status: str
    symbol: str
    direction: Direction
    setup: Setup
    regime: Regime
    status: SignalStatus
    data_timestamp_ms: int
    created_at_ms: int
    expires_at_ms: int
    entry_low: float
    entry_high: float
    stop_loss: float
    invalidation_level: float
    take_profit: float
    rr_gross: float
    rr_net: float
    pattern_score: int | None
    factor_score: float
    p_win: float | None
    expected_r: float | None
    recommended_notional: float
    margin_at_leverage: float
    display_leverage: float
    max_loss_usdt: float
    estimated_fee_usdt: float
    estimated_slippage_usdt: float
    estimated_funding_usdt: float
    support: list[float] = field(default_factory=list)
    resistance: list[float] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    factor_scores: dict[str, float] = field(default_factory=dict)
    factor_evidence: list[str] = field(default_factory=list)
    positive_factor_groups: int = 0
    macro_4h: dict[str, Any] = field(default_factory=dict)
    structure_15m: str = "UNCONFIRMED"
    data_health: str = "OK"
    invalidation_reason: str | None = None
    notified_at_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("direction", "setup", "regime", "status"):
            payload[key] = str(payload[key])
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Signal:
        values = dict(payload)
        legacy_score = values.pop("setup_score", None)
        values.setdefault("factor_score", float(legacy_score or 0.0))
        values.setdefault("pattern_score", None)
        values.setdefault("invalidation_level", values.get("stop_loss"))
        values.setdefault("macro_4h", {})
        values.setdefault("structure_15m", "UNCONFIRMED")
        values.setdefault("data_health", "OK")
        values.setdefault("invalidation_reason", None)
        values.setdefault("notified_at_ms", None)
        values["direction"] = Direction(values["direction"])
        values["setup"] = Setup(values["setup"])
        values["regime"] = Regime(values["regime"])
        values["status"] = SignalStatus(values["status"])
        return cls(**values)


@dataclass(frozen=True)
class ScanResult:
    action: str
    health: str
    reason: str
    signal: Signal | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    reason_code: str = "UNSPECIFIED"
    opportunity: OpportunityEvidence | None = None
    runtime_stage: RuntimeStage = RuntimeStage.NO_OPPORTUNITY
    registry_snapshot: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "health": self.health,
            "reason": self.reason,
            "signal": self.signal.as_dict() if self.signal else None,
            "diagnostics": self.diagnostics,
            "reason_code": self.reason_code,
            "opportunity": self.opportunity.as_dict() if self.opportunity else None,
            "runtime_stage": self.runtime_stage.value,
            "registry_snapshot": self.registry_snapshot,
        }
