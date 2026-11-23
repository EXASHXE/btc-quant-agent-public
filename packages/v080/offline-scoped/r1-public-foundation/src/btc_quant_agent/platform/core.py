"""Immutable domain contracts; milliseconds UTC and quote-currency economics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol

from btc_quant_agent.decision.models import content_hash
from btc_quant_agent.domain import Candle  # One shared candle contract, not another OHLCV type.
from btc_quant_agent.market_watch.domain import InputClock
from btc_quant_agent.market_watch.foundation import clock_reason


def primitive(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return primitive(asdict(value))
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(x) for x in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return str(value)
    return value


def fingerprint(value: Any) -> str:
    return content_hash(primitive(value))


def dec(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("INVALID_DECIMAL") from exc
    if not result.is_finite():
        raise ValueError("NONFINITE_DECIMAL")
    return result


def quantize(value: Any, step: Any, *, up: bool = False) -> Decimal:
    amount, quantum = dec(value), dec(step)
    if amount <= 0 or quantum <= 0:
        raise ValueError("NONPOSITIVE_INCREMENT")
    result = (amount / quantum).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * quantum
    if result <= 0:
        raise ValueError("INCREMENT_ROUNDS_TO_ZERO")
    return result


class EvidenceTier(StrEnum):
    IMPLEMENTED_UNTESTED = "IMPLEMENTED_UNTESTED"
    SYNTHETIC_VALIDATED = "SYNTHETIC_VALIDATED"
    HISTORICAL_EXPLORATORY = "HISTORICAL_EXPLORATORY"
    FORWARD_PAPER = "FORWARD_PAPER"
    ECONOMICALLY_VALIDATED = "ECONOMICALLY_VALIDATED"


class Status(StrEnum):
    OK = "OK"
    MISSING = "MISSING"
    INADMISSIBLE = "INADMISSIBLE"
    WARMUP = "WARMUP"


class Lifecycle(StrEnum):
    DISCOVERED = "DISCOVERED"
    WATCH = "WATCH"
    ARMED = "ARMED"
    ENTRY_ELIGIBLE = "ENTRY_ELIGIBLE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


def lifecycle_path(start: Lifecycle, end: Lifecycle) -> tuple[Lifecycle, ...]:
    """Record every traversed state even when the gates complete at one observation."""
    if start == end:
        return (start,)
    if start in (Lifecycle.EXPIRED, Lifecycle.CANCELLED):
        return (start,)  # Terminal candidates never reopen.
    if end in (Lifecycle.EXPIRED, Lifecycle.CANCELLED):
        return (start, end)
    order = [Lifecycle.DISCOVERED, Lifecycle.WATCH, Lifecycle.ARMED, Lifecycle.ENTRY_ELIGIBLE]
    if order.index(end) < order.index(start):
        raise ValueError("LIFECYCLE_REGRESSION")
    return tuple(order[order.index(start) : order.index(end) + 1])


@dataclass(frozen=True)
class DataProvenance:
    provider: str
    source_id: str
    exchange_event_ts: int
    received_ts: int
    available_ts: int
    exposure: str = "SYNTHETIC"
    admissible: bool = True

    def reason(self, decision_ts: int, max_age_ms: int) -> str | None:
        if not self.admissible:
            return "SOURCE_NOT_ADMITTED"
        if self.exposure == "PUBLIC_CANARY":
            # NativeProvenance supplies the independently audited clock proof.
            # The legacy synthetic wall-order contract remains unchanged.
            return "PUBLIC_CLOCK_EVIDENCE_MISSING"
        return clock_reason(
            InputClock(self.exchange_event_ts, self.received_ts, self.available_ts), decision_ts, max_age_ms
        )


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    market: str = "PERPETUAL"
    provider: str = "synthetic"
    quote_currency: str = "USDT"
    tick_size: Decimal = Decimal("0.01")
    quantity_step: Decimal = Decimal("0.001")
    multiplier: Decimal = Decimal("1")
    min_notional: Decimal = Decimal("5")
    max_leverage: float = 5.0
    maintenance_margin_rate: float = 0.005
    session: str = "24x7"
    adjusted: bool = False
    funding_interval_hours: int | None = 8  # Synthetic baseline; adapters must supply or mark unknown.

    def __post_init__(self) -> None:
        for name in ("tick_size", "quantity_step", "multiplier", "min_notional"):
            object.__setattr__(self, name, dec(getattr(self, name)))
        if not self.symbol or self.market not in ("SPOT", "PERPETUAL", "EQUITY", "ETF"):
            raise ValueError("UNSUPPORTED_INSTRUMENT")
        if any(dec(v) <= 0 for v in (self.tick_size, self.quantity_step, self.multiplier)):
            raise ValueError("INVALID_INSTRUMENT_PRECISION")
        if self.max_leverage < 1 or not 0 <= self.maintenance_margin_rate < 1:
            raise ValueError("INVALID_MARGIN_SPEC")


@dataclass(frozen=True)
class ExecutableQuote:
    symbol: str
    bid: Decimal
    ask: Decimal
    provenance: DataProvenance
    bid_quantity: Decimal | None = None
    ask_quantity: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("bid", "ask", "bid_quantity", "ask_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, dec(value))

    def reason(self, spec: InstrumentSpec, decision_ts: int, max_age_ms: int = 5000) -> str | None:
        reason = self.provenance.reason(decision_ts, max_age_ms)
        if reason:
            return "QUOTE_" + reason
        if self.provenance.provider != spec.provider:
            return "QUOTE_PROVIDER_MISMATCH"
        if self.symbol != spec.symbol or not 0 < self.bid <= self.ask:
            return "QUOTE_INVALID"
        if self.bid % spec.tick_size or self.ask % spec.tick_size:
            return "QUOTE_TICK_INVALID"
        if any(v is not None and v < 0 for v in (self.bid_quantity, self.ask_quantity)):
            return "QUOTE_SIZE_INVALID"
        return None


@dataclass(frozen=True)
class TradeObservation:
    symbol: str
    price: Decimal
    quantity: Decimal
    aggressive_side: str
    provenance: DataProvenance


@dataclass(frozen=True)
class DerivativeSnapshot:
    provenance: DataProvenance
    open_interest: float | None = None
    oi_unit: str = "BASE"
    funding_rate: float | None = None
    funding_settlement: bool = False
    basis: float | None = None
    premium: float | None = None
    taker_buy: float | None = None
    taker_sell: float | None = None
    spot_close: float | None = None
    mark_price: float | None = None
    field_provenance: tuple[tuple[str, DataProvenance], ...] = ()

    def field_clock(self, name: str) -> DataProvenance | None:
        if not self.field_provenance:
            return self.provenance
        return dict(self.field_provenance).get(name)

    def field_reason(self, name: str, decision_ts: int, max_age_ms: int) -> str | None:
        if getattr(self, name, None) is None:
            return "MISSING"
        p = self.field_clock(name)
        return "FIELD_CLOCK_UNKNOWN" if p is None else p.reason(decision_ts, max_age_ms)


@dataclass(frozen=True)
class MarketEvent:
    spec: InstrumentSpec
    candle: Candle
    provenance: DataProvenance
    decision_ts: int
    quote: ExecutableQuote | None = None
    derivatives: DerivativeSnapshot | None = None
    trades: tuple[TradeObservation, ...] = ()

    def __post_init__(self) -> None:
        if self.candle.symbol != self.spec.symbol:
            raise ValueError("EVENT_SYMBOL_MISMATCH")

    def reason(self, max_age_ms: int) -> str | None:
        reason = self.provenance.reason(self.decision_ts, max_age_ms)
        if reason:
            return reason
        if self.provenance.provider != self.spec.provider:
            return "PROVIDER_MISMATCH"
        c = self.candle
        from .canary.clock_domain import NativeProvenance, native_before

        if isinstance(self.provenance, NativeProvenance):
            if not c.closed or not native_before(self.provenance, c.close_time_ms + 1, self.decision_ts):
                return "CANDLE_UNCLOSED"
            if (
                c.available_at_ms != self.provenance.available_ts
                or c.close_time_ms != self.provenance.exchange_event_ts
            ):
                return "CANDLE_CLOCK_PROOF_BINDING_MISMATCH"
            return None  # Freshness/causality were checked in the proof's monotonic domain.
        if not c.closed or c.close_time_ms > self.decision_ts:
            return "CANDLE_UNCLOSED"
        if c.available_at_ms is None or c.available_at_ms > self.decision_ts:
            return "CANDLE_AVAILABILITY_UNKNOWN_OR_FUTURE"
        if c.close_time_ms > self.provenance.received_ts or c.available_at_ms < self.provenance.received_ts:
            return "CANDLE_CLOCK_ORDER_INVALID"
        if self.decision_ts - c.close_time_ms > max_age_ms:
            return "CANDLE_STALE"
        return None


@dataclass(frozen=True)
class SourceAdmission:
    """Bound evidence, not a user-supplied allow-live switch."""

    event_hash: str
    config_hash: str
    decision_ts: int
    reasons: tuple[str, ...]
    mode: str = "OFFLINE_FIXTURE"

    def vetoes(self, event: MarketEvent, config_hash: str) -> tuple[str, ...]:
        if (
            self.event_hash != fingerprint(event)
            or self.config_hash != config_hash
            or self.decision_ts != event.decision_ts
        ):
            return ("SOURCE_ADMISSION_BINDING_MISMATCH",)
        if self.mode != "OFFLINE_FIXTURE" or event.provenance.exposure != "SYNTHETIC":
            return ("REAL_MARKET_SOURCE_NOT_AUTHORIZED",)
        return self.reasons


@dataclass(frozen=True)
class FactorDefinition:
    id: str
    version: str
    formula: str
    required_fields: tuple[str, ...]
    parameter_schema: tuple[str, ...] = ("period",)
    parameter_defaults: tuple[tuple[str, int], ...] = (("period", 14),)
    supported_markets: tuple[str, ...] = ("SPOT", "PERPETUAL", "EQUITY", "ETF")
    sampling_interval: str = "configured completed candle"
    available_time_rule: str = "all dependencies available <= decision; trailing windows only"
    missing_behavior: str = "MISSING, INADMISSIBLE or WARMUP; never substituted zero"
    warmup_rule: str = "period observations; indicator-specific extra history"
    implementation_status: str = "WORKING_BASELINE"


@dataclass(frozen=True)
class FactorResult:
    factor_id: str
    value: float | None
    status: Status
    available_ts: int | None
    reason: str | None = None


@dataclass(frozen=True)
class RegimeResult:
    state: str
    evidence: tuple[tuple[str, float], ...]
    decision_ts: int


@dataclass(frozen=True)
class StrategyDefinition:
    id: str
    version: str
    description: str
    required_features: tuple[str, ...]
    mechanism: str
    supported_markets: tuple[str, ...] = ("SPOT", "PERPETUAL", "EQUITY", "ETF")
    parameters: tuple[str, ...] = ("period", "fast", "slow", "threshold", "lookback")
    horizon: str = "intraday/swing; interval-dependent"
    entry_rules: str = "completed-bar setup followed by confirmation and independent risk gates"
    invalidation_rules: str = "observed trailing structure breached or plan expired"
    exit_policy: str = "observed reference mean for reversion, otherwise open-ended trailing"
    execution_assumptions: str = "next available quote after manual latency; no same-bar hindsight fill"
    limitations: str = "synthetic engineering evidence only; no established economic edge"
    evidence_tier: EvidenceTier = EvidenceTier.IMPLEMENTED_UNTESTED
    status: str = "WORKING_BASELINE"
    sampling_interval: str = "configured completed candle"
    warmup: int = 40
    available_time_rule: str = "feature and source available <= decision_ts"
    missing_behavior: str = "no setup from missing required inputs"


@dataclass(frozen=True)
class StrategyCandidate:
    id: str
    symbol: str
    direction: str
    strategy_id: str
    strategy_version: str
    decision_ts: int
    state: Lifecycle
    opportunity_score: float
    evidence_json: str
    confirmation: tuple[str, ...]
    entry_low: Decimal
    entry_high: Decimal
    max_entry_price: Decimal
    expires_ts: int
    invalidation: Decimal
    stop: Decimal
    target: Decimal | None
    exit_policy: str
    regime: str
    provenance: DataProvenance
    veto_reasons: tuple[str, ...] = ()
    evidence_tier: EvidenceTier = EvidenceTier.IMPLEMENTED_UNTESTED


@dataclass(frozen=True)
class RiskPlan:
    quantity: Decimal
    budget: float
    modeled_loss: float
    notional: float
    leverage: float
    liquidation_price_proxy: float | None
    friction_per_unit: float
    funding_projection: float | None
    limitations: tuple[str, ...] = ("Liquidation proxy excludes exchange-specific tiers and cross margin.",)


@dataclass(frozen=True)
class EntryPlan:
    candidate: StrategyCandidate
    state: Lifecycle
    action: str
    risk: RiskPlan | None
    entry_price: Decimal | None
    veto_reasons: tuple[str, ...]
    decision_ts: int
    config_hash: str
    lifecycle_transitions: tuple[Lifecycle, ...] = ()


@dataclass(frozen=True)
class SimulatedFill:
    id: str
    plan_id: str
    symbol: str
    direction: str
    price: Decimal
    quantity: Decimal
    available_ts: int
    fees: float
    slippage: float
    source: str = "SIMULATED"


@dataclass(frozen=True)
class UserReportedFill:
    report_id: str
    position_id: str
    symbol: str
    direction: str
    price: Decimal
    quantity: Decimal
    user_action_ts: int
    received_ts: int
    leverage: float = 1.0
    margin_mode: str = "ISOLATED"
    operation: str = "OPEN"
    source: str = "USER_REPORTED"


@dataclass(frozen=True)
class PositionState:
    id: str
    symbol: str
    direction: str
    entry: Decimal
    quantity: Decimal
    stop: Decimal
    initial_stop: Decimal
    leverage: float
    margin_mode: str
    version: int
    status: str
    source: str
    updated_ts: int
    funding: float = 0.0
    partial_closes: int = 0


@dataclass(frozen=True)
class ManagementAction:
    position_id: str
    action: str
    reason: str
    decision_ts: int
    suggested_stop: Decimal | None = None
    fraction: float | None = None
    execution_status: str = "UNCONFIRMED"


@dataclass(frozen=True)
class BacktestRun:
    run_id: str
    config_hash: str
    source_hash: str
    dataset_hash: str
    exposure: str
    metrics: dict[str, Any]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ModelManifest:
    model_id: str
    family: str
    version: str
    features: tuple[str, ...]
    target: str
    seed: int
    dataset_hash: str
    training_period: tuple[int, int]
    validation_period: tuple[int, int]
    metrics: dict[str, Any]
    artifact: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    config_hash: str
    source_identity: str
    dataset_range: tuple[int, int]
    exposure: str
    metrics: dict[str, Any]
    warnings: tuple[str, ...]
    artifacts: tuple[str, ...]


class Clock(Protocol):
    def now_ms(self) -> int: ...
