from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ..domain import Candle, Regime

MARKET_WATCH_POLICY_VERSION = "0.5.0-r1"


class DirectionalDecision(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"


class GridDecision(StrEnum):
    PAUSE = "PAUSE"
    NEUTRAL = "NEUTRAL"
    LONG_BIAS = "LONG_BIAS"
    SHORT_BIAS = "SHORT_BIAS"


class EntryQuality(StrEnum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    MARGINAL = "MARGINAL"
    POOR = "POOR"


class BreakoutState(StrEnum):
    NONE = "NONE"
    BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
    RETEST_CONFIRMED = "RETEST_CONFIRMED"


class DerivativesRegime(StrEnum):
    HEALTHY_LONG_BUILD = "HEALTHY_LONG_BUILD"
    HEALTHY_SHORT_BUILD = "HEALTHY_SHORT_BUILD"
    SHORT_COVERING = "SHORT_COVERING"
    LONG_LIQUIDATION = "LONG_LIQUIDATION"
    LONG_CROWDING = "LONG_CROWDING"
    SHORT_CROWDING = "SHORT_CROWDING"
    LEVERAGE_BUILD_NO_DIRECTION = "LEVERAGE_BUILD_NO_DIRECTION"
    DELEVERAGING = "DELEVERAGING"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class BenchmarkContext(StrEnum):
    MARKET_RISK_ON = "MARKET_RISK_ON"
    MARKET_RISK_OFF = "MARKET_RISK_OFF"
    BENCHMARK_NEUTRAL = "BENCHMARK_NEUTRAL"
    BTC_VOLATILITY_SHOCK = "BTC_VOLATILITY_SHOCK"
    ETH_VOLATILITY_SHOCK = "ETH_VOLATILITY_SHOCK"


class SignalLifecycleState(StrEnum):
    CANDIDATE = "CANDIDATE"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class AlertSeverity(StrEnum):
    INFO = "INFO"
    WATCH = "WATCH"
    ACTION = "ACTION"
    RISK = "RISK"


class ScanHealth(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class PlaybookType(StrEnum):
    TREND_PULLBACK = "TREND_PULLBACK"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    FAILED_BREAKDOWN = "FAILED_BREAKDOWN"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    RANGE_MEAN_REVERSION = "RANGE_MEAN_REVERSION"
    NO_TRADE = "NO_TRADE"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ExhaustionState(StrEnum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class TimeframeSnapshot:
    interval: str
    latest_bar: Candle
    latest_closed_bar: Candle
    closed_bar_end_time_ms: int
    close: float
    ema_fast: float
    ema_mid: float
    ema_fast_slope: float
    ema_mid_slope: float
    atr: float
    atr_percentile: float
    adx: float
    rsi: float
    roc: float
    volume: float
    volume_z: float
    bb_width: float
    bb_width_percentile: float
    recent_swing_high: float | None
    recent_swing_low: float | None
    supports: tuple[float, ...]
    resistances: tuple[float, ...]
    structure: str
    regime: Regime
    is_volatility_compressed: bool = False
    is_volatility_expanded: bool = False
    has_prior_compression_window: bool = False


@dataclass(frozen=True)
class DerivativesMetrics:
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    funding_time_ms: int | None = None
    current_open_interest: float | None = None
    open_interest_time_ms: int | None = None
    oi_1h_change: float | None = None
    oi_4h_change: float | None = None
    oi_12h_change: float | None = None
    global_account_long_short_ratio: float | None = None
    long_short_time_ms: int | None = None
    top_trader_position_ratio: float | None = None
    top_trader_account_ratio: float | None = None
    taker_buy_sell_ratio: float | None = None
    taker_time_ms: int | None = None
    basis_rate: float | None = None
    basis_time_ms: int | None = None
    basis_bps: float | None = None
    spread_bps: float | None = None
    order_book_imbalance: float | None = None
    regime: DerivativesRegime = DerivativesRegime.NEUTRAL
    reasons: tuple[str, ...] = ()
    field_availability: dict[str, bool] = field(default_factory=dict)
    endpoint_errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PriceMetrics:
    last_price: float
    mark_price: float | None = None
    change_24h_pct: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    quote_volume_24h: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    decision_time_ms: int
    observed_at_ms: int
    exchange_time_ms: int
    price: PriceMetrics
    tf_15m: TimeframeSnapshot
    tf_1h: TimeframeSnapshot
    tf_4h: TimeframeSnapshot
    derivatives: DerivativesMetrics
    snapshot_hash: str
    health: ScanHealth = ScanHealth.OK
    health_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelativePerformance:
    symbol: str
    perf_15m: float
    perf_1h: float
    perf_4h: float
    rel_to_btc_1h: float
    rel_to_eth_1h: float
    rel_to_median_1h: float
    score: float
    multi_tf_excess: float = 0.0
    rank: int = 0


@dataclass(frozen=True)
class ExhaustionMetrics:
    state: ExhaustionState
    distance_from_ema20_atr: float = 0.0
    distance_from_ema50_atr: float = 0.0
    distance_to_support_atr: float = 0.0
    distance_to_resistance_atr: float = 0.0
    recent_extension_atr: float = 0.0
    multi_bar_extension_atr: float = 0.0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectionalPlan:
    symbol: str
    decision: DirectionalDecision
    setup: PlaybookType
    regime: Regime
    entry_quality: EntryQuality
    entry_low: float
    entry_high: float
    add_level: float | None = None
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    invalidation_level: float = 0.0
    gross_rr: float = 0.0
    net_rr: float = 0.0
    confidence_band: ConfidenceBand = ConfidenceBand.LOW
    opportunity_score: float = 0.0
    reason_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    derivatives_regime: DerivativesRegime = DerivativesRegime.NEUTRAL
    benchmark_context: BenchmarkContext = BenchmarkContext.BENCHMARK_NEUTRAL
    breakout_state: BreakoutState = BreakoutState.NONE
    breakout_level: float | None = None
    breakout_bar_end_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "decision",
            "setup",
            "regime",
            "entry_quality",
            "confidence_band",
            "derivatives_regime",
            "benchmark_context",
            "breakout_state",
        ):
            payload[key] = str(payload[key])
        return payload


@dataclass(frozen=True)
class GridPlan:
    symbol: str
    decision: GridDecision
    lower_bound: float | None = None
    upper_bound: float | None = None
    grid_count: int = 0
    estimated_grid_pct: float | None = None
    trigger_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = str(payload["decision"])
        return payload


@dataclass(frozen=True)
class SymbolAssessment:
    symbol: str
    snapshot: MarketSnapshot
    directional: DirectionalPlan
    grid: GridPlan
    opportunity_score: float
    relative_performance: RelativePerformance | None
    exhaustion: ExhaustionMetrics
    rank: int = 0
    veto_reasons: tuple[str, ...] = ()
    alert_fingerprint: str = ""
    lifecycle_state: SignalLifecycleState = SignalLifecycleState.CANDIDATE
    policy_version: str = MARKET_WATCH_POLICY_VERSION
    config_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "opportunity_score": round(self.opportunity_score, 2),
            "rank": self.rank,
            "policy_version": self.policy_version,
            "config_hash": self.config_hash,
            "lifecycle_state": str(self.lifecycle_state),
            "directional": self.directional.as_dict(),
            "grid": self.grid.as_dict(),
            "veto_reasons": list(self.veto_reasons),
            "alert_fingerprint": self.alert_fingerprint,
        }


@dataclass(frozen=True)
class MarketWatchAlert:
    symbol: str
    severity: AlertSeverity
    title: str
    directional: DirectionalPlan
    grid: GridPlan
    fingerprint: str
    evidence: tuple[str, ...]
    risks: tuple[str, ...]
    alert_time_ms: int
    last_price: float = 0.0
    change_24h_pct: float = 0.0
    atr: float = 0.0
    key_support: float | None = None
    key_resistance: float | None = None
    funding_rate: float | None = None
    oi_1h_change: float | None = None
    oi_12h_change: float | None = None
    regime_1h: str = ""
