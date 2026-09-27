from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ..domain import Candle, Regime

MARKET_WATCH_POLICY_VERSION: str = "0.5.0-market-watch-forward-v1"
MARKET_WATCH_EVIDENCE_VERSION: str = "FORWARD_EVIDENCE_V1"


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


class ShadowObservationType(StrEnum):
    SETUP_ARMED = "SETUP_ARMED"
    ACTIONABLE_TRIGGERED = "ACTIONABLE_TRIGGERED"


class ShadowFillStatus(StrEnum):
    WAITING_FOR_FILL = "WAITING_FOR_FILL"
    FILLED = "FILLED"
    NO_FILL = "NO_FILL"
    RESOLVED = "RESOLVED"


class ShadowPathResolution(StrEnum):
    ONE_MINUTE_CHRONOLOGICAL = "ONE_MINUTE_CHRONOLOGICAL"
    FIFTEEN_MINUTE_STOP_FIRST = "FIFTEEN_MINUTE_STOP_FIRST"
    ONE_MINUTE_FILL_BAR_STOP_FIRST = "ONE_MINUTE_FILL_BAR_STOP_FIRST"
    ONE_MINUTE_AMBIGUOUS_STOP_FIRST = "ONE_MINUTE_AMBIGUOUS_STOP_FIRST"


class ShadowExecutionPathModel(StrEnum):
    PARTIAL_FIRST_BAR_1M_THEN_15M = "PARTIAL_FIRST_BAR_1M_THEN_15M"


class ShadowTerminalReason(StrEnum):
    STOP = "STOP"
    TP1 = "TP1"
    TIMEOUT = "TIMEOUT"
    NO_FILL = "NO_FILL"
    INELIGIBLE_DATA_GAP = "INELIGIBLE_DATA_GAP"
    LEGACY_INELIGIBLE = "LEGACY_INELIGIBLE"
    PENDING_DATA_GAP = "PENDING_DATA_GAP"


@dataclass(frozen=True)
class CoverageStatus:
    complete: bool
    start_covered: bool
    end_covered: bool
    internal_gap_count: int
    first_available_ms: int | None
    last_available_ms: int | None


@dataclass(frozen=True)
class ShadowFillResult:
    status: ShadowFillStatus
    fill_price: float | None = None
    fill_time_ms: int | None = None
    fill_candle_open_ms: int | None = None
    fill_candle_close_ms: int | None = None
    source_interval: str = "15m"
    path_resolution: str = "FIFTEEN_MINUTE_STOP_FIRST"

    def __iter__(self) -> Any:
        return iter((self.status, self.fill_price, self.fill_time_ms))


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
    collection_started_at_ms: int = 0
    collection_completed_at_ms: int = 0


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
    breakout_direction: str | None = None
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


def validate_time_coverage(
    candles: Sequence[Candle],
    start_ms: int,
    end_ms: int,
    interval_ms: int,
    allowed_gap_ms: int | None = None,
) -> CoverageStatus:
    """Validate chronological time coverage across a required window.

    Requirements:
    - Candles sorted chronologically.
    - start_covered: first candle open <= start_ms.
    - end_covered: last candle close covers end_ms (under inclusive-close: last candle close >= end_ms - 1 or last candle close >= end_ms).
    - internal continuity: expected_next_open = previous.open_time_ms + interval_ms.
      Tolerates up to tolerance_ms (default 1ms for inclusive-close timestamps).
    - complete: start_covered and end_covered and internal_gap_count == 0.
    """
    valid_candles = [c for c in candles if isinstance(c, Candle)]
    if not valid_candles:
        return CoverageStatus(
            complete=False,
            start_covered=False,
            end_covered=False,
            internal_gap_count=0,
            first_available_ms=None,
            last_available_ms=None,
        )

    valid_candles.sort(key=lambda c: c.open_time_ms)
    first_open = valid_candles[0].open_time_ms
    last_close = valid_candles[-1].close_time_ms
    start_covered = (first_open <= start_ms)
    # Under Binance inclusive-close semantics (e.g. close = open + interval - 1),
    # the last candle covering an end_ms boundary has close_time_ms == end_ms - 1.
    end_covered = (last_close >= end_ms - 1) if end_ms > start_ms else (last_close >= end_ms)

    tolerance_ms = allowed_gap_ms if allowed_gap_ms is not None else 1
    internal_gap_count = 0
    for i in range(len(valid_candles) - 1):
        expected_next_open = valid_candles[i].open_time_ms + interval_ms
        if abs(valid_candles[i + 1].open_time_ms - expected_next_open) > tolerance_ms:
            internal_gap_count += 1

    complete = start_covered and end_covered and (internal_gap_count == 0)
    return CoverageStatus(
        complete=complete,
        start_covered=start_covered,
        end_covered=end_covered,
        internal_gap_count=internal_gap_count,
        first_available_ms=first_open,
        last_available_ms=last_close,
    )


def normalize_price_level(price: float | None, tick_size: float | None = None) -> str:
    """Deterministic, scale-aware normalization of price level without fixed-decimal collisions."""
    if price is None or price <= 0:
        return "0"
    if tick_size is not None and tick_size > 0:
        tick_str = f"{tick_size:.10f}".rstrip("0")
        decimals = len(tick_str.split(".")[1]) if "." in tick_str else 0
        norm_val = round(price / tick_size) * tick_size
        return f"{norm_val:.{decimals}f}"

    abs_p = abs(price)
    if abs_p >= 1000.0:
        return f"{price:.2f}"
    elif abs_p >= 10.0:
        return f"{price:.3f}"
    elif abs_p >= 0.1:
        return f"{price:.6f}"
    elif abs_p >= 0.001:
        return f"{price:.7f}"
    else:
        return f"{price:.8f}"


def compute_setup_key(
    symbol: str,
    playbook: PlaybookType | str,
    intended_direction: str,
    structural_anchor_id: str | float | None,
    tick_size: float | None = None,
) -> str:
    """Stable identity for the ongoing market setup independent of minor drift."""
    sym = symbol.upper()
    pb_str = playbook.value if isinstance(playbook, PlaybookType) else str(playbook)
    dir_str = intended_direction.upper()

    if isinstance(structural_anchor_id, (int, float)):
        anchor_str = normalize_price_level(float(structural_anchor_id), tick_size)
    elif structural_anchor_id:
        anchor_str = str(structural_anchor_id)
    else:
        anchor_str = "0"
    return f"{sym}:{pb_str}:{dir_str}:{anchor_str}"


def compute_signal_identity(
    symbol: str,
    playbook: PlaybookType | str,
    intended_direction: str,
    structural_anchor_id: str | float | None,
    setup_creation_bar_end_ms: int = 0,
    tick_size: float | None = None,
) -> str:
    """Unique identity for one actionable setup instance."""
    setup_key = compute_setup_key(symbol, playbook, intended_direction, structural_anchor_id, tick_size)
    bar_str = str(setup_creation_bar_end_ms) if setup_creation_bar_end_ms > 0 else "0"
    return f"{setup_key}:{bar_str}"


def extract_setup_key(
    symbol: str,
    directional: DirectionalPlan,
    snapshot: MarketSnapshot | None = None,
    tick_size: float | None = None,
) -> str:
    """Extract setup_key from DirectionalPlan and structural snapshot anchors."""
    d = directional
    if str(d.decision.value) in ("LONG", "SHORT"):
        intended_dir = str(d.decision.value)
    elif d.breakout_direction:
        intended_dir = str(d.breakout_direction)
    elif str(d.setup.value) == "FAILED_BREAKOUT":
        intended_dir = "SHORT"
    elif str(d.setup.value) == "FAILED_BREAKDOWN":
        intended_dir = "LONG"
    elif d.take_profit_1 > 0 and d.stop_loss > 0:
        intended_dir = "LONG" if d.take_profit_1 > d.stop_loss else "SHORT"
    elif d.take_profit_1 > 0 and d.entry_low > 0:
        intended_dir = "LONG" if d.take_profit_1 > d.entry_low else "SHORT"
    else:
        intended_dir = "NONE"

    setup_str = d.setup.value if isinstance(d.setup, PlaybookType) else str(d.setup)
    if setup_str == "BREAKOUT_RETEST":
        anchor_id = f"BO_{normalize_price_level(d.breakout_level, tick_size)}"
    elif setup_str == "FAILED_BREAKOUT":
        sw_high = (snapshot.tf_1h.recent_swing_high if snapshot else None) or d.entry_high
        anchor_id = f"FBO_{normalize_price_level(sw_high, tick_size)}"
    elif setup_str == "FAILED_BREAKDOWN":
        sw_low = (snapshot.tf_1h.recent_swing_low if snapshot else None) or d.entry_low
        anchor_id = f"FBD_{normalize_price_level(sw_low, tick_size)}"
    elif setup_str == "TREND_PULLBACK":
        if intended_dir == "LONG":
            sw_low = (
                (snapshot.tf_1h.recent_swing_low if snapshot else None)
                or (snapshot.tf_4h.recent_swing_low if snapshot else None)
                or d.entry_low
            )
            anchor_id = f"SWL_{normalize_price_level(sw_low, tick_size)}"
        else:
            sw_high = (
                (snapshot.tf_1h.recent_swing_high if snapshot else None)
                or (snapshot.tf_4h.recent_swing_high if snapshot else None)
                or d.entry_high
            )
            anchor_id = f"SWH_{normalize_price_level(sw_high, tick_size)}"
    elif setup_str in ("VOLATILITY_EXPANSION", "RANGE_MEAN_REVERSION"):
        anchor = (
            (snapshot.tf_1h.recent_swing_high if intended_dir == "SHORT" and snapshot else None)
            or (snapshot.tf_1h.recent_swing_low if intended_dir == "LONG" and snapshot else None)
            or d.breakout_level
            or (d.entry_low if intended_dir == "LONG" else d.entry_high)
        )
        anchor_id = f"VE_{normalize_price_level(anchor, tick_size)}"
    else:
        lvl = d.breakout_level or (d.entry_low if intended_dir == "LONG" else d.entry_high) or d.stop_loss
        anchor_id = f"LVL_{normalize_price_level(lvl, tick_size)}"

    return compute_setup_key(symbol, d.setup, intended_dir, anchor_id, tick_size)


def extract_signal_identity(
    symbol: str,
    directional: DirectionalPlan,
    snapshot: MarketSnapshot | None = None,
    created_bar_end_ms: int = 0,
    tick_size: float | None = None,
) -> str:
    """Extract or compute deterministic signal identity from DirectionalPlan."""
    setup_key = extract_setup_key(symbol, directional, snapshot, tick_size)
    bar_str = str(created_bar_end_ms) if created_bar_end_ms > 0 else "0"
    return f"{setup_key}:{bar_str}"


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
    signal_identity: str = ""
    setup_key: str = ""

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
            "signal_identity": self.signal_identity,
            "setup_key": self.setup_key,
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
