"""Versioned offline swing contracts. This module acquires no data and emits no trades."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from math import isclose
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .core import Candle, fingerprint

PRODUCT: Final = "V070_SWING_ADVISORY_V1"
SCHEMA: Final = "V070_SWING_SNAPSHOT_V1"
INTERVALS = {"1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000}
ACTIVE_STRATEGIES = frozenset({"trend_pullback"})
FILTERS = frozenset({"EMA", "ADX", "ATR", "RELATIVE_VOLUME", "QUOTE_SPREAD"})


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


def require_active_strategy(identity: str) -> None:
    if identity not in ACTIVE_STRATEGIES:
        raise ValueError("STRATEGY_OUT_OF_ACTIVE_SCOPE:" + identity)


def timestamp(value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError("UTC_MILLISECONDS_REQUIRED")


class SwingPolicy(Contract):
    version: Literal["V070_SWING_ADVISORY_V1"] = PRODUCT
    market_timeframes: tuple[Literal["1H", "4H", "1D"], ...] = ("1H", "4H", "1D")
    decision_timeframes: tuple[Literal["4H", "1D"], ...] = ("4H", "1D")
    review_hours_utc: tuple[int, ...] = (0, 12)
    minimum_history_bars: int = Field(default=60, ge=40)
    max_availability_delay_ms: int = Field(default=300_000, gt=0, le=300_000)
    one_hour_role: Literal["OPTIONAL_NON_URGENT_CONFIRMATION"] = "OPTIONAL_NON_URGENT_CONFIRMATION"
    source_gate: Literal["LOW_RATE_CLOSED_BAR_V1"] = "LOW_RATE_CLOSED_BAR_V1"
    native_acquisition: Literal[False] = False
    orders: Literal[False] = False
    private_accounts: Literal[False] = False
    notifications: Literal[False] = False

    @model_validator(mode="after")
    def fixed_scope(self) -> Self:
        if self.market_timeframes != ("1H", "4H", "1D") or self.decision_timeframes != ("4H", "1D"):
            raise ValueError("FIXED_CLOSED_BAR_SCOPE")
        hours = self.review_hours_utc
        if (len(hours) not in (1, 2) or tuple(sorted(set(hours))) != hours
                or any(type(h) is not int or not 0 <= h < 24 for h in hours)):
            raise ValueError("ONE_OR_TWO_PREDECLARED_DAILY_REVIEWS_REQUIRED")
        if len(hours) == 2 and hours[1] - hours[0] != 12:
            raise ValueError("TWICE_DAILY_REVIEWS_MUST_BE_TWELVE_HOURS_APART")
        return self

    def next_review(self, now_ms: int) -> int:
        timestamp(now_ms)
        day = now_ms // INTERVALS["1D"] * INTERVALS["1D"]
        return min(day + d * INTERVALS["1D"] + h * INTERVALS["1H"]
                   for d in (0, 1) for h in self.review_hours_utc
                   if day + d * INTERVALS["1D"] + h * INTERVALS["1H"] > now_ms)


class State(StrEnum):
    NO_SETUP = "NO_SETUP"
    WATCH = "WATCH"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    ENTRY_ZONE_ACTIVE = "ENTRY_ZONE_ACTIVE"
    MISSED_OR_NO_CHASE = "MISSED_OR_NO_CHASE"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    ACCOUNT_UNKNOWN = "ACCOUNT_UNKNOWN"
    VETO = "VETO"


class ClosedBar(Contract):
    """Shared Candle uses inclusive close=end-1; clocks below use half-open end."""

    candle: Candle
    source_id: str = Field(min_length=1)
    source_event_ms: int
    received_ms: int
    available_ms: int
    durable_ms: int
    revision: int = Field(default=0, ge=0)
    exposure: Literal["OFFLINE_FIXTURE"] = "OFFLINE_FIXTURE"

    @property
    def end_ms(self) -> int:
        return self.candle.close_time_ms + 1

    def reason(self, cutoff_ms: int, policy: SwingPolicy) -> str | None:
        c = self.candle
        size = INTERVALS.get(c.interval)
        if size is None:
            return "TIMEFRAME_OUT_OF_SCOPE"
        if type(c.open_time_ms) is not int or type(c.close_time_ms) is not int:
            return "BAR_TIMESTAMP_TYPE_INVALID"
        if c.open_time_ms % size or self.end_ms - c.open_time_ms != size:
            return "BAR_BOUNDARY_INVALID"
        if not c.closed:
            return "BAR_NOT_EXPLICITLY_COMPLETED"
        clocks = (self.end_ms, self.source_event_ms, self.received_ms,
                  self.available_ms, self.durable_ms, cutoff_ms)
        if any(type(t) is not int or t <= 0 for t in clocks) or list(clocks) != sorted(clocks):
            return "CAUSAL_CLOCK_ORDER_INVALID"
        if c.available_at_ms != self.available_ms:
            return "AVAILABILITY_BINDING_MISMATCH"
        if self.available_ms - self.end_ms > policy.max_availability_delay_ms:
            return "AVAILABILITY_SLA_MISSED"
        if min(c.open, c.high, c.low, c.close) <= 0:
            return "NONPOSITIVE_PRICE"
        return None


def closed_bar_errors(
    bars: Sequence[ClosedBar], *, symbol: str, decision_ms: int, trigger_close_ms: int,
    policy: SwingPolicy,
) -> tuple[str, ...]:
    """Validate an as-of prefix, latest expected closes, continuity and dual regime inputs."""
    timestamp(decision_ms)
    timestamp(trigger_close_ms)
    if trigger_close_ms % INTERVALS["4H"] or trigger_close_ms > decision_ms:
        return ("DECISION_REQUIRES_COMPLETED_4H_OR_1D_TRIGGER",)
    if decision_ms - trigger_close_ms > policy.max_availability_delay_ms:
        return ("STALE_DECISION_TRIGGER",)
    errors = []
    for bar in bars:
        if bar.candle.symbol != symbol:
            errors.append("SYMBOL_MISMATCH")
        reason = bar.reason(decision_ms, policy)
        if reason:
            errors.append(reason)
    # 1H is deliberately optional: its absence cannot create an urgent confirmation requirement.
    for timeframe in ("4H", "1D"):
        members = [b for b in bars if b.candle.interval == timeframe and b.candle.symbol == symbol]
        ends = [b.end_ms for b in members]
        expected_end = trigger_close_ms // INTERVALS[timeframe] * INTERVALS[timeframe]
        if len(ends) < policy.minimum_history_bars:
            errors.append("INSUFFICIENT_COMPLETED_HISTORY:" + timeframe)
        if not ends or ends[-1] != expected_end:
            errors.append("LATEST_COMPLETED_BAR_MISSING:" + timeframe)
        if len(set(ends)) != len(ends):
            errors.append("DUPLICATE_OR_UNRESOLVED_REVISION:" + timeframe)
        if any(b - a != INTERVALS[timeframe] for a, b in zip(ends, ends[1:])):
            errors.append("GAP_OR_UNSORTED_PREFIX:" + timeframe)
    return tuple(dict.fromkeys(errors))


class Opportunity(Contract):
    """Ex-ante contract only; a caller cannot activate another strategy or assert a fill."""

    strategy: Literal["trend_pullback"] = "trend_pullback"
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    direction: Literal["LONG", "SHORT"]
    regime: Literal["TREND_UP", "TREND_DOWN"]
    setup_close_ms: int
    available_ms: int
    structural_observed_ms: int
    entry_region: tuple[float, float]
    structural_invalidation: float = Field(gt=0)
    atr_buffer: float = Field(gt=0)
    execution_buffer: float = Field(gt=0)
    target_zones: tuple[float, ...]
    planned_after_cost_r: float = Field(gt=0)
    planned_cost_per_unit: float = Field(ge=0)
    cost_assumption: str = Field(min_length=1)
    holding_hours: int = Field(default=24, ge=8, le=120)
    review_deadline_ms: int
    expires_ms: int
    risk_factors: tuple[str, ...] = ("PLANNED_PAYOFF_IS_NOT_EXECUTABLE_OR_REALIZED",)
    account_status: Literal["UNKNOWN", "VETO", "NOT_REQUESTED"] = "UNKNOWN"

    @model_validator(mode="after")
    def causal_structure(self) -> Self:
        for t in (self.setup_close_ms, self.available_ms, self.structural_observed_ms,
                  self.review_deadline_ms, self.expires_ms):
            timestamp(t)
        if self.setup_close_ms % INTERVALS["4H"]:
            raise ValueError("SETUP_REQUIRES_COMPLETED_DECISION_BAR")
        if not self.structural_observed_ms <= self.setup_close_ms <= self.available_ms:
            raise ValueError("STRUCTURE_MUST_BE_PREOBSERVABLE")
        if not self.available_ms < self.review_deadline_ms <= self.expires_ms:
            raise ValueError("INVALID_REVIEW_OR_EXPIRY_ORDER")
        if self.expires_ms - self.setup_close_ms > 120 * INTERVALS["1H"]:
            raise ValueError("VALIDITY_EXCEEDS_FIVE_DAYS")
        low, high = self.entry_region
        if not 0 < low <= high or not self.target_zones:
            raise ValueError("ENTRY_OR_TARGET_REGION_INVALID")
        stop = self.buffered_stop
        if self.direction == "LONG":
            if self.regime != "TREND_UP" or not 0 < stop < low or min(self.target_zones) <= high:
                raise ValueError("LONG_STRUCTURE_INVALID")
        elif self.regime != "TREND_DOWN" or stop <= high or max(self.target_zones) >= low:
            raise ValueError("SHORT_STRUCTURE_INVALID")
        if any(t <= 0 for t in self.target_zones):
            raise ValueError("TARGET_PRICE_INVALID")
        entry = high if self.direction == "LONG" else low
        nearest = min(self.target_zones) if self.direction == "LONG" else max(self.target_zones)
        planned_r = (abs(nearest - entry) - self.planned_cost_per_unit) / (
            abs(entry - stop) + self.planned_cost_per_unit)
        if not isclose(self.planned_after_cost_r, planned_r, rel_tol=1e-6):
            raise ValueError("PLANNED_R_DOES_NOT_MATCH_WORST_REGION_ENTRY_AND_COST_ASSUMPTION")
        return self

    @property
    def buffered_stop(self) -> float:
        sign = -1 if self.direction == "LONG" else 1
        return self.structural_invalidation + sign * (self.atr_buffer + self.execution_buffer)


class AdvisorySnapshot(Contract):
    schema_version: Literal["V070_SWING_SNAPSHOT_V1"] = SCHEMA
    product_version: Literal["V070_SWING_ADVISORY_V1"] = PRODUCT
    state: State
    setup_status: Literal["NO_SETUP", "CONTRACT_CANDIDATE"]
    actionability: Literal["NOT_ACTIONABLE", "REVIEW_ONLY"]
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    decision_ms: int
    trigger_close_ms: int
    next_review_ms: int
    bar_prefix_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reasons: tuple[str, ...]
    opportunity: Opportunity | None = None
    source_qualified: Literal[False] = False
    shadow_qualified: Literal[False] = False
    evidence_tier: Literal["OFFLINE_CONTRACT_ONLY"] = "OFFLINE_CONTRACT_ONLY"
    integration_status: Literal["LT_B_INTEGRATION_PENDING"] = "LT_B_INTEGRATION_PENDING"

    @model_validator(mode="after")
    def consistent(self) -> Self:
        timestamp(self.decision_ms)
        timestamp(self.trigger_close_ms)
        timestamp(self.next_review_ms)
        if self.next_review_ms <= self.decision_ms:
            raise ValueError("NEXT_SCHEDULED_REVIEW_MUST_BE_FUTURE")
        ready = self.state in (State.READY_FOR_REVIEW, State.ENTRY_ZONE_ACTIVE)
        if (self.actionability == "REVIEW_ONLY") != ready:
            raise ValueError("STATE_ACTIONABILITY_MISMATCH")
        if ready:
            opportunity = self.opportunity
            if opportunity is None or opportunity.expires_ms <= self.next_review_ms:
                raise ValueError("OPPORTUNITY_UNAVAILABLE_AT_SCHEDULED_REVIEW")
            if opportunity.review_deadline_ms < self.next_review_ms:
                raise ValueError("OPPORTUNITY_UNAVAILABLE_AT_SCHEDULED_REVIEW")
            if (self.trigger_close_ms % INTERVALS["4H"]
                    or not 0 <= self.decision_ms - self.trigger_close_ms <= 300_000
                    or opportunity.available_ms > self.decision_ms
                    or opportunity.setup_close_ms > self.trigger_close_ms):
                raise ValueError("REVIEW_STATE_REQUIRES_CAUSAL_COMPLETED_DECISION_BAR")
            if opportunity.account_status != "NOT_REQUESTED":
                raise ValueError("ACCOUNT_UNKNOWN_OR_VETO_CANNOT_BE_REVIEW_READY")
        if self.opportunity and self.opportunity.symbol != self.symbol:
            raise ValueError("OPPORTUNITY_SYMBOL_MISMATCH")
        if (self.setup_status == "CONTRACT_CANDIDATE") != (self.opportunity is not None):
            raise ValueError("SETUP_STATUS_MISMATCH")
        return self


def decide(
    *, symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"], decision_ms: int, trigger_close_ms: int,
    bars: Sequence[ClosedBar] = (), opportunity: Opportunity | None = None,
    policy: SwingPolicy | None = None, source_blocked: bool = False,
) -> AdvisorySnapshot:
    """Offline lifecycle transition; only completed decision bars may make review states."""
    policy = policy or SwingPolicy()
    next_review = policy.next_review(decision_ms)
    errors = closed_bar_errors(bars, symbol=symbol, decision_ms=decision_ms,
                               trigger_close_ms=trigger_close_ms, policy=policy)
    reasons: tuple[str, ...]
    state, reasons = State.NO_SETUP, ("NO_SCIENTIFICALLY_EVALUATED_SETUP_PRODUCED",)
    if source_blocked:
        state, reasons = State.SOURCE_BLOCKED, ("SOURCE_AUTHORIZATION_OR_QUALITY_BLOCKED",)
    elif errors:
        state, reasons = State.DATA_UNAVAILABLE, errors
    elif opportunity is not None:
        o = opportunity
        closed = next(b.candle for b in reversed(bars) if b.candle.interval == "4H")
        if o.symbol != symbol or o.available_ms > decision_ms or o.setup_close_ms > trigger_close_ms:
            state, reasons = State.SOURCE_BLOCKED, ("OPPORTUNITY_CAUSAL_IDENTITY_INVALID",)
        elif (decision_ms >= o.expires_ms or o.expires_ms <= next_review
              or o.review_deadline_ms < next_review):
            state, reasons = State.EXPIRED, ("EXPIRES_OR_REQUIRES_REVIEW_BEFORE_NEXT_SCHEDULED_CHECK",)
        elif ((o.direction == "LONG" and closed.low <= o.buffered_stop)
              or (o.direction == "SHORT" and closed.high >= o.buffered_stop)):
            state, reasons = State.INVALIDATED, ("CLOSED_BAR_CROSSED_STRUCTURAL_INVALIDATION",)
        elif ((o.direction == "LONG" and closed.close > o.entry_region[1])
              or (o.direction == "SHORT" and closed.close < o.entry_region[0])):
            state, reasons = State.MISSED_OR_NO_CHASE, ("ENTRY_REGION_LOST_NO_FILL_ASSUMED",)
        elif o.account_status in ("UNKNOWN", "VETO"):
            state = State.ACCOUNT_UNKNOWN if o.account_status == "UNKNOWN" else State.VETO
            reasons = ("ACCOUNT_NOT_VERIFIED_NO_ACCOUNT_API_USED",)
        elif o.entry_region[0] <= closed.close <= o.entry_region[1]:
            state, reasons = State.ENTRY_ZONE_ACTIVE, ("OFFLINE_REVIEW_CONTRACT_ONLY_NO_EXECUTION_PERMISSION",)
        else:
            state, reasons = State.READY_FOR_REVIEW, ("WAIT_FOR_REGION_AT_SCHEDULED_REVIEW",)
    return AdvisorySnapshot(
        state=state, setup_status="CONTRACT_CANDIDATE" if opportunity else "NO_SETUP",
        actionability="REVIEW_ONLY" if state in (State.READY_FOR_REVIEW, State.ENTRY_ZONE_ACTIVE)
        else "NOT_ACTIONABLE", symbol=symbol, decision_ms=decision_ms,
        trigger_close_ms=trigger_close_ms, next_review_ms=next_review,
        bar_prefix_hash=fingerprint([b.model_dump(mode="json") for b in bars]),
        reasons=reasons, opportunity=opportunity,
    )
