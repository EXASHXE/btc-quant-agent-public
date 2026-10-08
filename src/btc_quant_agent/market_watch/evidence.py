from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from btc_quant_agent.domain import Candle

from .config import (
    MarketWatchConfig,
    compute_market_watch_config_hash_from_payload,
    market_watch_config_hash_payload,
)
from .domain import (
    ACTIVE_PLAYBOOKS,
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    MARKET_WATCH_EVIDENCE_VERSION,
    PLAYBOOK_SELECTION_VERSION,
    REFERENCE_UNIVERSE_VERSION,
    RETURN_FEATURE_SEMANTICS_VERSION,
    RULE_SCORE_SEMANTICS_VERSION,
    SEMANTIC_IDENTITY_VERSION,
    TACTICAL_FEATURE_EVIDENCE_SCHEMA_VERSION,
    TACTICAL_POLICY_VERSION,
    PlaybookCandidate,
    StrategyStatus,
    SymbolAssessment,
    TacticalSemanticIdentity,
)
from .snapshot import ReturnObservation

# ==============================================================================
# Exceptions
# ==============================================================================

class TacticalEvidenceError(Exception):
    """Base exception for tactical feature evidence failures."""


class TacticalCausalityError(TacticalEvidenceError):
    """Raised when decision-time causality or point-in-time invariant is violated."""


class TacticalEvidenceValidationError(TacticalEvidenceError):
    """Raised when evidence content validation fails (e.g. NaN/Inf or schema violation)."""


class TacticalEvidenceIdentityError(TacticalEvidenceError):
    """Raised when evidence_id format is invalid or recomputed ID does not match stored ID."""


class TacticalEvidenceConflictError(TacticalEvidenceError):
    """Raised when different evidence content is presented for an existing natural key."""


class TacticalEvidenceLinkageError(TacticalEvidenceError):
    """Raised when a shadow or assessment record links to a non-existent evidence_id."""


EVIDENCE_ID_REGEX = re.compile(r"^[0-9a-f]{64}$")


# ==============================================================================
# Evidence Sub-components (All Deeply Immutable)
# ==============================================================================

@dataclass(frozen=True)
class RuleScoreBreakdown:
    effective_direction: str
    adx_score: float
    ema_slope_score: float
    trend_quality: float
    structure_quality: float
    entry_quality_score: float
    derivatives_confirmation_score: float
    volume_z_score: float
    taker_score: float
    participation_quality: float
    relative_strength_score: float
    net_rr_score: float
    weighted_base: float
    crowding_penalty: float
    overextension_penalty: float
    benchmark_penalty: float
    low_liquidity_penalty: float
    total_penalty: float
    pre_wait_adjustment_score: float
    wait_adjustment_applied: bool
    final_rule_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_direction": self.effective_direction,
            "adx_score": self.adx_score,
            "ema_slope_score": self.ema_slope_score,
            "trend_quality": self.trend_quality,
            "structure_quality": self.structure_quality,
            "entry_quality_score": self.entry_quality_score,
            "derivatives_confirmation_score": self.derivatives_confirmation_score,
            "volume_z_score": self.volume_z_score,
            "taker_score": self.taker_score,
            "participation_quality": self.participation_quality,
            "relative_strength_score": self.relative_strength_score,
            "net_rr_score": self.net_rr_score,
            "weighted_base": self.weighted_base,
            "crowding_penalty": self.crowding_penalty,
            "overextension_penalty": self.overextension_penalty,
            "benchmark_penalty": self.benchmark_penalty,
            "low_liquidity_penalty": self.low_liquidity_penalty,
            "total_penalty": self.total_penalty,
            "pre_wait_adjustment_score": self.pre_wait_adjustment_score,
            "wait_adjustment_applied": self.wait_adjustment_applied,
            "final_rule_score": self.final_rule_score,
        }


@dataclass(frozen=True)
class PolicyGateStageTrace:
    stage_name: str
    input_decision: str
    output_decision: str
    new_reason_codes: tuple[str, ...] = ()
    new_risk_codes: tuple[str, ...] = ()
    veto_flag: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "input_decision": self.input_decision,
            "output_decision": self.output_decision,
            "new_reason_codes": list(self.new_reason_codes),
            "new_risk_codes": list(self.new_risk_codes),
            "veto_flag": self.veto_flag,
        }


@dataclass(frozen=True)
class PolicyDecisionTrace:
    selected_candidate_decision: str
    after_entry_quality_gate: PolicyGateStageTrace
    after_benchmark_gate: PolicyGateStageTrace
    after_derivatives_gate: PolicyGateStageTrace
    after_fatal_veto: PolicyGateStageTrace
    final_directional_decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_decision": self.selected_candidate_decision,
            "after_entry_quality_gate": self.after_entry_quality_gate.to_dict(),
            "after_benchmark_gate": self.after_benchmark_gate.to_dict(),
            "after_derivatives_gate": self.after_derivatives_gate.to_dict(),
            "after_fatal_veto": self.after_fatal_veto.to_dict(),
            "final_directional_decision": self.final_directional_decision,
        }


@dataclass(frozen=True)
class SourceProvenanceEvidence:
    closed_bar_watermark_15m: int
    closed_bar_watermark_1h: int
    closed_bar_watermark_4h: int
    returns: tuple[ReturnObservation, ...]
    derivatives_observed_at_ms: int | None = None
    funding_time_ms: int | None = None  # Legacy alias for premium_index_time_ms (premium["time"])
    premium_index_time_ms: int | None = None
    next_funding_time_ms: int | None = None
    open_interest_time_ms: int | None = None
    long_short_time_ms: int | None = None
    taker_time_ms: int | None = None
    basis_time_ms: int | None = None
    ticker_receipt_ms: int | None = None
    oi_hist_receipt_ms: int | None = None
    top_pos_receipt_ms: int | None = None
    top_acc_receipt_ms: int | None = None
    server_time_receipt_ms: int | None = None
    field_availability: tuple[tuple[str, bool], ...] = ()
    endpoint_errors: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "closed_bar_watermark_15m": self.closed_bar_watermark_15m,
            "closed_bar_watermark_1h": self.closed_bar_watermark_1h,
            "closed_bar_watermark_4h": self.closed_bar_watermark_4h,
            "returns": [
                {
                    "horizon_ms": r.horizon_ms,
                    "value": r.value,
                    "availability": r.availability,
                    "anchor_close_time_ms": r.anchor_close_time_ms,
                    "latest_close_time_ms": r.latest_close_time_ms,
                    "source_interval": r.source_interval,
                    "semantics_version": r.semantics_version,
                }
                for r in self.returns
            ],
            "derivatives_observed_at_ms": self.derivatives_observed_at_ms,
            "funding_time_ms": self.funding_time_ms,
            "premium_index_time_ms": self.premium_index_time_ms,
            "next_funding_time_ms": self.next_funding_time_ms,
            "open_interest_time_ms": self.open_interest_time_ms,
            "long_short_time_ms": self.long_short_time_ms,
            "taker_time_ms": self.taker_time_ms,
            "basis_time_ms": self.basis_time_ms,
            "ticker_receipt_ms": self.ticker_receipt_ms,
            "oi_hist_receipt_ms": self.oi_hist_receipt_ms,
            "top_pos_receipt_ms": self.top_pos_receipt_ms,
            "top_acc_receipt_ms": self.top_acc_receipt_ms,
            "server_time_receipt_ms": self.server_time_receipt_ms,
            "field_availability": [[k, v] for k, v in self.field_availability],
            "endpoint_errors": [[k, v] for k, v in self.endpoint_errors],
        }


@dataclass(frozen=True)
class ClosedBarEvidence:
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int

    @classmethod
    def from_candle(cls, candle: Candle) -> ClosedBarEvidence:
        return cls(
            open_time_ms=candle.open_time_ms,
            close_time_ms=candle.close_time_ms,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            quote_volume=candle.quote_volume,
            trades=candle.trades,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "trades": self.trades,
        }


@dataclass(frozen=True)
class TimeframeFeaturesEvidence:
    interval: str
    closed_bar_end_time_ms: int
    latest_closed_bar: ClosedBarEvidence
    close: float
    ema_fast: float
    ema_mid: float
    ema_slow: float | None
    ema_slow_status: str
    ema_fast_slope: float
    ema_mid_slope: float
    atr: float
    atr_percentile: float
    adx: float
    rsi: float
    roc_12bars: float
    volume: float
    volume_z: float
    bb_width: float
    bb_width_percentile: float
    is_volatility_compressed: bool
    is_volatility_expanded: bool
    has_prior_compression_window: bool
    recent_swing_high: float | None
    recent_swing_low: float | None
    supports: tuple[float, ...]
    resistances: tuple[float, ...]
    structure: str
    regime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval": self.interval,
            "closed_bar_end_time_ms": self.closed_bar_end_time_ms,
            "latest_closed_bar": self.latest_closed_bar.to_dict(),
            "close": self.close,
            "ema_fast": self.ema_fast,
            "ema_mid": self.ema_mid,
            "ema_slow": self.ema_slow,
            "ema_slow_status": self.ema_slow_status,
            "ema_fast_slope": self.ema_fast_slope,
            "ema_mid_slope": self.ema_mid_slope,
            "atr": self.atr,
            "atr_percentile": self.atr_percentile,
            "adx": self.adx,
            "rsi": self.rsi,
            "roc_12bars": self.roc_12bars,
            "volume": self.volume,
            "volume_z": self.volume_z,
            "bb_width": self.bb_width,
            "bb_width_percentile": self.bb_width_percentile,
            "is_volatility_compressed": self.is_volatility_compressed,
            "is_volatility_expanded": self.is_volatility_expanded,
            "has_prior_compression_window": self.has_prior_compression_window,
            "recent_swing_high": self.recent_swing_high,
            "recent_swing_low": self.recent_swing_low,
            "supports": list(self.supports),
            "resistances": list(self.resistances),
            "structure": self.structure,
            "regime": self.regime,
        }


@dataclass(frozen=True)
class DerivativesFeaturesEvidence:
    mark_price: float | None
    index_price: float | None
    funding_rate: float | None
    funding_time_ms: int | None  # Legacy alias for premium_index_time_ms
    premium_index_time_ms: int | None = None
    next_funding_time_ms: int | None = None
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
    basis_bps: float | None = None
    basis_time_ms: int | None = None
    spread_bps: float | None = None
    order_book_imbalance: float | None = None
    derivatives_regime: str = "NEUTRAL"
    reasons: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    field_availability: tuple[tuple[str, bool], ...] = ()
    endpoint_errors: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mark_price": self.mark_price,
            "index_price": self.index_price,
            "funding_rate": self.funding_rate,
            "funding_time_ms": self.funding_time_ms,
            "premium_index_time_ms": self.premium_index_time_ms,
            "next_funding_time_ms": self.next_funding_time_ms,
            "current_open_interest": self.current_open_interest,
            "open_interest_time_ms": self.open_interest_time_ms,
            "oi_1h_change": self.oi_1h_change,
            "oi_4h_change": self.oi_4h_change,
            "oi_12h_change": self.oi_12h_change,
            "global_account_long_short_ratio": self.global_account_long_short_ratio,
            "long_short_time_ms": self.long_short_time_ms,
            "top_trader_position_ratio": self.top_trader_position_ratio,
            "top_trader_account_ratio": self.top_trader_account_ratio,
            "taker_buy_sell_ratio": self.taker_buy_sell_ratio,
            "taker_time_ms": self.taker_time_ms,
            "basis_rate": self.basis_rate,
            "basis_bps": self.basis_bps,
            "basis_time_ms": self.basis_time_ms,
            "spread_bps": self.spread_bps,
            "order_book_imbalance": self.order_book_imbalance,
            "derivatives_regime": self.derivatives_regime,
            "reasons": list(self.reasons),
            "risks": list(self.risks),
            "field_availability": [[k, v] for k, v in self.field_availability],
            "endpoint_errors": [[k, v] for k, v in self.endpoint_errors],
        }


@dataclass(frozen=True)
class MarketSnapshotFeaturesEvidence:
    tf_15m: TimeframeFeaturesEvidence
    tf_1h: TimeframeFeaturesEvidence
    tf_4h: TimeframeFeaturesEvidence
    derivatives: DerivativesFeaturesEvidence
    last_price: float
    mark_price: float | None
    change_24h_pct: float
    high_24h: float
    low_24h: float
    quote_volume_24h: float
    benchmark_context: str
    return_1h: float | None
    return_4h: float | None
    return_12h: float | None
    return_1h_status: str
    return_4h_status: str
    return_12h_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tf_15m": self.tf_15m.to_dict(),
            "tf_1h": self.tf_1h.to_dict(),
            "tf_4h": self.tf_4h.to_dict(),
            "derivatives": self.derivatives.to_dict(),
            "last_price": self.last_price,
            "mark_price": self.mark_price,
            "change_24h_pct": self.change_24h_pct,
            "high_24h": self.high_24h,
            "low_24h": self.low_24h,
            "quote_volume_24h": self.quote_volume_24h,
            "benchmark_context": self.benchmark_context,
            "return_1h": self.return_1h,
            "return_4h": self.return_4h,
            "return_12h": self.return_12h,
            "return_1h_status": self.return_1h_status,
            "return_4h_status": self.return_4h_status,
            "return_12h_status": self.return_12h_status,
        }


@dataclass(frozen=True)
class ReferenceUniverseEvidence:
    version: str
    status: str
    expected_members: tuple[str, ...]
    available_members: tuple[str, ...]
    missing_members: tuple[str, ...]
    incomplete_return_members: tuple[str, ...]
    perf_1h: float | None
    perf_4h: float | None
    perf_12h: float | None
    rel_to_btc_1h: float | None
    rel_to_eth_1h: float | None
    rel_to_median_1h: float | None
    multi_tf_excess: float
    score: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "expected_members": list(self.expected_members),
            "available_members": list(self.available_members),
            "missing_members": list(self.missing_members),
            "incomplete_return_members": list(self.incomplete_return_members),
            "perf_1h": self.perf_1h,
            "perf_4h": self.perf_4h,
            "perf_12h": self.perf_12h,
            "rel_to_btc_1h": self.rel_to_btc_1h,
            "rel_to_eth_1h": self.rel_to_eth_1h,
            "rel_to_median_1h": self.rel_to_median_1h,
            "multi_tf_excess": self.multi_tf_excess,
            "score": self.score,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class PlaybookCandidateEvidence:
    playbook: str
    candidate_status: str
    strategy_status: str
    decision: str
    entry_low: float | None
    entry_high: float | None
    stop_loss: float | None
    take_profit_1: float | None
    take_profit_2: float | None
    invalidation: float | None
    structural_anchor_id: str | None
    reason_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    setup_creation_bar_end_ms: int | None
    breakout_state: str
    breakout_level: float | None
    breakout_direction: str | None
    breakout_bar_end_ms: int | None
    failed_level: float | None
    confidence_band: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook": self.playbook,
            "candidate_status": self.candidate_status,
            "strategy_status": self.strategy_status,
            "decision": self.decision,
            "entry_low": self.entry_low,
            "entry_high": self.entry_high,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "invalidation": self.invalidation,
            "structural_anchor_id": self.structural_anchor_id,
            "reason_codes": list(self.reason_codes),
            "risk_codes": list(self.risk_codes),
            "setup_creation_bar_end_ms": self.setup_creation_bar_end_ms,
            "breakout_state": self.breakout_state,
            "breakout_level": self.breakout_level,
            "breakout_direction": self.breakout_direction,
            "breakout_bar_end_ms": self.breakout_bar_end_ms,
            "failed_level": self.failed_level,
            "confidence_band": self.confidence_band,
        }


@dataclass(frozen=True)
class ExhaustionEvidence:
    state: str
    distance_from_ema20_atr: float
    distance_from_ema50_atr: float
    distance_to_support_atr: float
    distance_to_resistance_atr: float
    recent_extension_atr: float
    multi_bar_extension_atr: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "distance_from_ema20_atr": self.distance_from_ema20_atr,
            "distance_from_ema50_atr": self.distance_from_ema50_atr,
            "distance_to_support_atr": self.distance_to_support_atr,
            "distance_to_resistance_atr": self.distance_to_resistance_atr,
            "recent_extension_atr": self.recent_extension_atr,
            "multi_bar_extension_atr": self.multi_bar_extension_atr,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class DirectionalPlanEvidence:
    decision: str
    setup: str
    regime: str
    entry_quality: str
    entry_low: float
    entry_high: float
    add_level: float | None
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    invalidation_level: float
    gross_rr: float
    net_rr: float
    derivatives_regime: str
    benchmark_context: str
    reason_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    breakout_state: str
    breakout_level: float | None
    breakout_direction: str | None
    breakout_bar_end_ms: int | None
    rule_score: float
    heuristic_quality_band_semantics: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "setup": self.setup,
            "regime": self.regime,
            "entry_quality": self.entry_quality,
            "entry_low": self.entry_low,
            "entry_high": self.entry_high,
            "add_level": self.add_level,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "invalidation_level": self.invalidation_level,
            "gross_rr": self.gross_rr,
            "net_rr": self.net_rr,
            "derivatives_regime": self.derivatives_regime,
            "benchmark_context": self.benchmark_context,
            "reason_codes": list(self.reason_codes),
            "risk_codes": list(self.risk_codes),
            "breakout_state": self.breakout_state,
            "breakout_level": self.breakout_level,
            "breakout_direction": self.breakout_direction,
            "breakout_bar_end_ms": self.breakout_bar_end_ms,
            "rule_score": self.rule_score,
            "heuristic_quality_band_semantics": self.heuristic_quality_band_semantics,
        }


@dataclass(frozen=True)
class GridPlanEvidence:
    decision: str
    lower_bound: float | None
    upper_bound: float | None
    grid_count: int
    estimated_grid_pct: float | None
    trigger_price: float | None
    stop_loss: float | None
    take_profit: float | None
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "grid_count": self.grid_count,
            "estimated_grid_pct": self.estimated_grid_pct,
            "trigger_price": self.trigger_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class DecisionConfigEvidence:
    canonical_json: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> DecisionConfigEvidence:
        return cls(canonical_json=canonical_json_dump(dict(payload)))

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.canonical_json))


@dataclass(frozen=True)
class PolicyStateInputEvidence:
    previous_setup: str | None = None
    previous_breakout_state: str = "NONE"
    previous_breakout_level: float | None = None
    previous_breakout_direction: str | None = None
    previous_breakout_bar_end_ms: int | None = None
    previous_recent_failed_breakout: float | None = None
    previous_recent_failed_breakout_ms: int | None = None
    previous_recent_failed_breakdown: float | None = None
    previous_recent_failed_breakdown_ms: int | None = None
    previous_grid_decision: str = "PAUSE"
    previous_grid_lower_bound: float | None = None
    previous_grid_upper_bound: float | None = None
    previous_recent_support: float | None = None
    previous_recent_resistance: float | None = None
    previous_lifecycle_state: str = "CANDIDATE"
    previous_signal_identity: str | None = None
    previous_setup_key: str | None = None
    previous_created_bar_end_ms: int | None = None
    previous_armed_bar_end_ms: int | None = None
    previous_triggered_bar_end_ms: int | None = None
    previous_age_bars: int = 0
    previous_setup_instance_started_bar_end_ms: int | None = None

    @classmethod
    def from_prev_state(cls, prev: Mapping[str, Any] | None) -> PolicyStateInputEvidence:
        """Construct from raw state-store runtime dictionary (keys without previous_ prefix)."""
        if not prev:
            return cls()
        return cls(
            previous_setup=prev.get("setup"),
            previous_breakout_state=str(prev.get("breakout_state", "NONE")),
            previous_breakout_level=prev.get("breakout_level"),
            previous_breakout_direction=prev.get("breakout_direction"),
            previous_breakout_bar_end_ms=prev.get("breakout_bar_end_ms"),
            previous_recent_failed_breakout=prev.get("recent_failed_breakout"),
            previous_recent_failed_breakout_ms=prev.get("recent_failed_breakout_ms"),
            previous_recent_failed_breakdown=prev.get("recent_failed_breakdown"),
            previous_recent_failed_breakdown_ms=prev.get("recent_failed_breakdown_ms"),
            previous_grid_decision=str(prev.get("grid_decision", "PAUSE")),
            previous_grid_lower_bound=prev.get("grid_lower_bound"),
            previous_grid_upper_bound=prev.get("grid_upper_bound"),
            previous_recent_support=prev.get("recent_support"),
            previous_recent_resistance=prev.get("recent_resistance"),
            previous_lifecycle_state=str(prev.get("lifecycle_state", "CANDIDATE")),
            previous_signal_identity=prev.get("signal_identity"),
            previous_setup_key=prev.get("setup_key"),
            previous_created_bar_end_ms=prev.get("created_bar_end_ms"),
            previous_armed_bar_end_ms=prev.get("armed_bar_end_ms"),
            previous_triggered_bar_end_ms=prev.get("triggered_bar_end_ms"),
            previous_age_bars=int(prev.get("age_bars", 0)),
            previous_setup_instance_started_bar_end_ms=prev.get("setup_instance_started_bar_end_ms"),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> PolicyStateInputEvidence:
        """Construct from canonical serialized dictionary (exact previous_* fields)."""
        if not data:
            return cls()
        return cls(
            previous_setup=data.get("previous_setup"),
            previous_breakout_state=str(data.get("previous_breakout_state", "NONE")),
            previous_breakout_level=data.get("previous_breakout_level"),
            previous_breakout_direction=data.get("previous_breakout_direction"),
            previous_breakout_bar_end_ms=data.get("previous_breakout_bar_end_ms"),
            previous_recent_failed_breakout=data.get("previous_recent_failed_breakout"),
            previous_recent_failed_breakout_ms=data.get("previous_recent_failed_breakout_ms"),
            previous_recent_failed_breakdown=data.get("previous_recent_failed_breakdown"),
            previous_recent_failed_breakdown_ms=data.get("previous_recent_failed_breakdown_ms"),
            previous_grid_decision=str(data.get("previous_grid_decision", "PAUSE")),
            previous_grid_lower_bound=data.get("previous_grid_lower_bound"),
            previous_grid_upper_bound=data.get("previous_grid_upper_bound"),
            previous_recent_support=data.get("previous_recent_support"),
            previous_recent_resistance=data.get("previous_recent_resistance"),
            previous_lifecycle_state=str(data.get("previous_lifecycle_state", "CANDIDATE")),
            previous_signal_identity=data.get("previous_signal_identity"),
            previous_setup_key=data.get("previous_setup_key"),
            previous_created_bar_end_ms=data.get("previous_created_bar_end_ms"),
            previous_armed_bar_end_ms=data.get("previous_armed_bar_end_ms"),
            previous_triggered_bar_end_ms=data.get("previous_triggered_bar_end_ms"),
            previous_age_bars=int(data.get("previous_age_bars", 0)),
            previous_setup_instance_started_bar_end_ms=data.get("previous_setup_instance_started_bar_end_ms"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_setup": self.previous_setup,
            "previous_breakout_state": self.previous_breakout_state,
            "previous_breakout_level": self.previous_breakout_level,
            "previous_breakout_direction": self.previous_breakout_direction,
            "previous_breakout_bar_end_ms": self.previous_breakout_bar_end_ms,
            "previous_recent_failed_breakout": self.previous_recent_failed_breakout,
            "previous_recent_failed_breakout_ms": self.previous_recent_failed_breakout_ms,
            "previous_recent_failed_breakdown": self.previous_recent_failed_breakdown,
            "previous_recent_failed_breakdown_ms": self.previous_recent_failed_breakdown_ms,
            "previous_grid_decision": self.previous_grid_decision,
            "previous_grid_lower_bound": self.previous_grid_lower_bound,
            "previous_grid_upper_bound": self.previous_grid_upper_bound,
            "previous_recent_support": self.previous_recent_support,
            "previous_recent_resistance": self.previous_recent_resistance,
            "previous_lifecycle_state": self.previous_lifecycle_state,
            "previous_signal_identity": self.previous_signal_identity,
            "previous_setup_key": self.previous_setup_key,
            "previous_created_bar_end_ms": self.previous_created_bar_end_ms,
            "previous_armed_bar_end_ms": self.previous_armed_bar_end_ms,
            "previous_triggered_bar_end_ms": self.previous_triggered_bar_end_ms,
            "previous_age_bars": self.previous_age_bars,
            "previous_setup_instance_started_bar_end_ms": self.previous_setup_instance_started_bar_end_ms,
        }


# ==============================================================================
# Top-Level TacticalFeatureEvidenceV2 Contract
# ==============================================================================

@dataclass(frozen=True)
class TacticalFeatureEvidenceV2:
    evidence_schema_version: str
    evidence_id: str
    symbol: str
    decision_time_ms: int
    observed_at_ms: int
    exchange_time_ms: int
    collection_started_at_ms: int
    collection_completed_at_ms: int
    snapshot_hash: str
    policy_version: str
    config_hash: str
    decision_config: DecisionConfigEvidence
    policy_state_before: PolicyStateInputEvidence
    semantic_identity: TacticalSemanticIdentity
    strategy_status: str
    source_provenance: SourceProvenanceEvidence
    market_snapshot_features: MarketSnapshotFeaturesEvidence
    reference_universe_evidence: ReferenceUniverseEvidence
    playbook_candidates: tuple[PlaybookCandidateEvidence, ...]
    selected_playbook: str | None
    selection_method: str
    selection_version: str
    eligible_playbooks: tuple[str, ...]
    actionable_playbooks: tuple[str, ...]
    decision_trace: PolicyDecisionTrace
    rule_score: float
    rule_score_semantics: str
    rule_score_breakdown: RuleScoreBreakdown
    entry_quality: str
    exhaustion: ExhaustionEvidence
    directional_risk_plan: DirectionalPlanEvidence | None
    grid_advisory_plan: GridPlanEvidence | None
    lifecycle_state: str
    signal_identity: str | None
    setup_key: str | None
    reason_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    veto_reasons: tuple[str, ...]


# ==============================================================================
# Canonical Serialization and Content Hashing
# ==============================================================================

def canonical_evidence_payload(evidence: TacticalFeatureEvidenceV2) -> dict[str, Any]:
    """Convert TacticalFeatureEvidenceV2 to a canonical dictionary excluding evidence_id and persistence metadata."""
    payload: dict[str, Any] = {
        "evidence_schema_version": evidence.evidence_schema_version,
        "symbol": evidence.symbol,
        "decision_time_ms": evidence.decision_time_ms,
        "observed_at_ms": evidence.observed_at_ms,
        "exchange_time_ms": evidence.exchange_time_ms,
        "collection_started_at_ms": evidence.collection_started_at_ms,
        "collection_completed_at_ms": evidence.collection_completed_at_ms,
        "snapshot_hash": evidence.snapshot_hash,
        "policy_version": evidence.policy_version,
        "config_hash": evidence.config_hash,
        "decision_config": evidence.decision_config.to_dict(),
        "policy_state_before": evidence.policy_state_before.to_dict(),
        "semantic_identity": evidence.semantic_identity.to_dict(),
        "strategy_status": evidence.strategy_status,
        "source_provenance": evidence.source_provenance.to_dict(),
        "market_snapshot_features": evidence.market_snapshot_features.to_dict(),
        "reference_universe_evidence": evidence.reference_universe_evidence.to_dict(),
        "playbook_candidates": [c.to_dict() for c in evidence.playbook_candidates],
        "selected_playbook": evidence.selected_playbook,
        "selection_method": evidence.selection_method,
        "selection_version": evidence.selection_version,
        "eligible_playbooks": list(evidence.eligible_playbooks),
        "actionable_playbooks": list(evidence.actionable_playbooks),
        "decision_trace": evidence.decision_trace.to_dict(),
        "rule_score": evidence.rule_score,
        "rule_score_semantics": evidence.rule_score_semantics,
        "rule_score_breakdown": evidence.rule_score_breakdown.to_dict(),
        "entry_quality": evidence.entry_quality,
        "exhaustion": evidence.exhaustion.to_dict(),
        "directional_risk_plan": evidence.directional_risk_plan.to_dict() if evidence.directional_risk_plan else None,
        "grid_advisory_plan": evidence.grid_advisory_plan.to_dict() if evidence.grid_advisory_plan else None,
        "lifecycle_state": evidence.lifecycle_state,
        "signal_identity": evidence.signal_identity,
        "setup_key": evidence.setup_key,
        "reason_codes": list(evidence.reason_codes),
        "risk_codes": list(evidence.risk_codes),
        "veto_reasons": list(evidence.veto_reasons),
    }
    return payload


def canonical_json_dump(payload: dict[str, Any]) -> str:
    """Deterministic, compact, sorted-key UTF-8 JSON serialization rejecting non-finite numbers."""
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except ValueError as e:
        raise TacticalEvidenceValidationError(f"Invalid non-finite number in evidence payload: {e}") from e


def compute_evidence_id(payload_or_evidence: dict[str, Any] | TacticalFeatureEvidenceV2) -> str:
    """Compute the immutable 64-character SHA-256 content identity from canonical payload or evidence."""
    if isinstance(payload_or_evidence, TacticalFeatureEvidenceV2):
        payload = canonical_evidence_payload(payload_or_evidence)
    else:
        payload = payload_or_evidence
    raw = canonical_json_dump(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_evidence_json(evidence: TacticalFeatureEvidenceV2) -> str:
    """Serialize full evidence to canonical JSON including evidence_id."""
    payload = canonical_evidence_payload(evidence)
    payload["evidence_id"] = evidence.evidence_id
    return canonical_json_dump(payload)


def verify_tactical_evidence_identity(evidence: TacticalFeatureEvidenceV2) -> None:
    """Verify evidence_id matches canonical content SHA-256 and has valid 64-char hex format."""
    if not isinstance(evidence.evidence_id, str) or not EVIDENCE_ID_REGEX.match(evidence.evidence_id):
        raise TacticalEvidenceIdentityError(
            f"Malformed evidence_id format (must be 64 lowercase hex chars): {evidence.evidence_id!r}"
        )
    payload = canonical_evidence_payload(evidence)
    expected_id = compute_evidence_id(payload)
    if evidence.evidence_id != expected_id:
        raise TacticalEvidenceIdentityError(
            f"Evidence identity verification failed: stored={evidence.evidence_id}, expected={expected_id}"
        )


# ==============================================================================
# Validation & Causality Assertion
# ==============================================================================

def _assert_finite_number(val: Any, path: str) -> None:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if math.isnan(val) or math.isinf(val):
            raise TacticalEvidenceValidationError(f"Invalid non-finite number at {path}: {val}")
    elif isinstance(val, dict):
        for k, v in val.items():
            _assert_finite_number(v, f"{path}.{k}")
    elif isinstance(val, (list, tuple)):
        for i, item in enumerate(val):
            _assert_finite_number(item, f"{path}[{i}]")


def validate_tactical_feature_evidence(evidence: TacticalFeatureEvidenceV2) -> None:
    """Validate deep immutability, causality invariants, schema authority, and mathematical finiteness."""
    # 0. Mathematical finiteness check (Section 15: no NaN / Infinity)
    payload = canonical_evidence_payload(evidence)
    _assert_finite_number(payload, "evidence")

    dec_t = evidence.decision_time_ms

    # 1. Schema, Policy version, and Semantics authority invariants (Sections 26 & 3)
    if evidence.evidence_schema_version != TACTICAL_FEATURE_EVIDENCE_SCHEMA_VERSION:
        raise TacticalEvidenceValidationError(
            f"evidence_schema_version {evidence.evidence_schema_version!r} != {TACTICAL_FEATURE_EVIDENCE_SCHEMA_VERSION!r}"
        )
    if evidence.policy_version != TACTICAL_POLICY_VERSION:
        raise TacticalEvidenceValidationError(
            f"policy_version {evidence.policy_version!r} != {TACTICAL_POLICY_VERSION!r}"
        )
    if evidence.rule_score_semantics != RULE_SCORE_SEMANTICS_VERSION:
        raise TacticalEvidenceValidationError(
            f"rule_score_semantics {evidence.rule_score_semantics!r} != {RULE_SCORE_SEMANTICS_VERSION!r}"
        )

    sem = evidence.semantic_identity
    if sem.semantic_identity_version != SEMANTIC_IDENTITY_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity_version {sem.semantic_identity_version!r} != {SEMANTIC_IDENTITY_VERSION!r}"
        )
    if sem.tactical_policy_version != TACTICAL_POLICY_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity tactical_policy_version {sem.tactical_policy_version!r} != {TACTICAL_POLICY_VERSION!r}"
        )
    if sem.snapshot_schema_version != MARKET_SNAPSHOT_SCHEMA_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity snapshot_schema_version {sem.snapshot_schema_version!r} != {MARKET_SNAPSHOT_SCHEMA_VERSION!r}"
        )
    if sem.return_feature_semantics_version != RETURN_FEATURE_SEMANTICS_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity return_feature_semantics_version {sem.return_feature_semantics_version!r} != {RETURN_FEATURE_SEMANTICS_VERSION!r}"
        )
    if sem.playbook_selection_version != PLAYBOOK_SELECTION_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity playbook_selection_version {sem.playbook_selection_version!r} != {PLAYBOOK_SELECTION_VERSION!r}"
        )
    if sem.reference_universe_version != REFERENCE_UNIVERSE_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity reference_universe_version {sem.reference_universe_version!r} != {REFERENCE_UNIVERSE_VERSION!r}"
        )
    if sem.rule_score_semantics_version != RULE_SCORE_SEMANTICS_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity rule_score_semantics_version {sem.rule_score_semantics_version!r} != {RULE_SCORE_SEMANTICS_VERSION!r}"
        )
    if sem.forward_evidence_version != MARKET_WATCH_EVIDENCE_VERSION:
        raise TacticalEvidenceValidationError(
            f"semantic_identity forward_evidence_version {sem.forward_evidence_version!r} != {MARKET_WATCH_EVIDENCE_VERSION!r}"
        )
    if sem.config_hash and sem.config_hash != evidence.config_hash:
        raise TacticalEvidenceValidationError(
            f"semantic_identity.config_hash ({sem.config_hash}) != evidence.config_hash ({evidence.config_hash})"
        )

    # Decision config hash self-containment & reproducibility (Section 7, 26, 33)
    recomputed_config_hash = compute_market_watch_config_hash_from_payload(evidence.decision_config.to_dict())
    if recomputed_config_hash != evidence.config_hash:
        raise TacticalEvidenceValidationError(
            f"Recomputed config hash ({recomputed_config_hash}) != evidence.config_hash ({evidence.config_hash})"
        )

    # 2. Causality invariants (Sections 15, 23, 24, 25)
    sp = evidence.source_provenance
    if sp.closed_bar_watermark_15m > dec_t:
        raise TacticalCausalityError(
            f"15m closed-bar watermark ({sp.closed_bar_watermark_15m}) > decision_time_ms ({dec_t})"
        )
    if sp.closed_bar_watermark_1h > dec_t:
        raise TacticalCausalityError(
            f"1h closed-bar watermark ({sp.closed_bar_watermark_1h}) > decision_time_ms ({dec_t})"
        )
    if sp.closed_bar_watermark_4h > dec_t:
        raise TacticalCausalityError(
            f"4h closed-bar watermark ({sp.closed_bar_watermark_4h}) > decision_time_ms ({dec_t})"
        )

    for r in sp.returns:
        if r.availability == "AVAILABLE":
            if r.value is None:
                raise TacticalCausalityError(
                    f"Return horizon {r.horizon_ms} is AVAILABLE but value is None"
                )
            if r.anchor_close_time_ms is None or r.latest_close_time_ms is None:
                raise TacticalCausalityError(
                    f"Return horizon {r.horizon_ms} is AVAILABLE but anchor/latest close time is None"
                )
            if r.anchor_close_time_ms > r.latest_close_time_ms:
                raise TacticalCausalityError(
                    f"Return horizon {r.horizon_ms} anchor time ({r.anchor_close_time_ms}) > latest time ({r.latest_close_time_ms})"
                )
            if r.latest_close_time_ms > dec_t:
                raise TacticalCausalityError(
                    f"Return horizon {r.horizon_ms} latest close time ({r.latest_close_time_ms}) > decision_time_ms ({dec_t})"
                )
            if r.latest_close_time_ms - r.anchor_close_time_ms != r.horizon_ms:
                raise TacticalCausalityError(
                    f"Return horizon {r.horizon_ms} span ({r.latest_close_time_ms - r.anchor_close_time_ms}) != horizon_ms ({r.horizon_ms})"
                )
        else:
            if r.value is not None:
                raise TacticalCausalityError(
                    f"Return horizon {r.horizon_ms} is unavailable ({r.availability}) but value is not None ({r.value})"
                )

    # Receipt timestamps (RECEIPT_TIME <= decision_time_ms)
    receipt_fields = [
        ("derivatives_observed_at_ms", sp.derivatives_observed_at_ms),
        ("ticker_receipt_ms", sp.ticker_receipt_ms),
        ("oi_hist_receipt_ms", sp.oi_hist_receipt_ms),
        ("top_pos_receipt_ms", sp.top_pos_receipt_ms),
        ("top_acc_receipt_ms", sp.top_acc_receipt_ms),
        ("server_time_receipt_ms", sp.server_time_receipt_ms),
    ]
    for name, ts in receipt_fields:
        if ts is not None:
            if not isinstance(ts, (int, float)) or isinstance(ts, bool):
                continue
            if ts > dec_t:
                raise TacticalCausalityError(f"Receipt timestamp {name} ({ts}) > decision_time_ms ({dec_t})")

    # Past event timestamps (PAST_EVENT_TIME <= decision_time_ms)
    past_event_fields = [
        ("open_interest_time_ms", sp.open_interest_time_ms),
        ("long_short_time_ms", sp.long_short_time_ms),
        ("taker_time_ms", sp.taker_time_ms),
        ("basis_time_ms", sp.basis_time_ms),
        ("premium_index_time_ms", sp.premium_index_time_ms),
        ("funding_time_ms", sp.funding_time_ms),
    ]
    for name, ts in past_event_fields:
        if ts is not None:
            if not isinstance(ts, (int, float)) or isinstance(ts, bool):
                continue
            if ts > dec_t:
                raise TacticalCausalityError(f"Source event timestamp {name} ({ts}) > decision_time_ms ({dec_t})")

    if (
        sp.funding_time_ms is not None
        and sp.premium_index_time_ms is not None
        and sp.funding_time_ms != sp.premium_index_time_ms
    ):
        raise TacticalEvidenceValidationError(
            f"Contradictory funding_time_ms ({sp.funding_time_ms}) != premium_index_time_ms ({sp.premium_index_time_ms})"
        )

    # Note: next_funding_time_ms is KNOWN_FUTURE_SCHEDULE_TIME (Binance nextFundingTime), legitimately allowed to be > dec_t

    if evidence.collection_started_at_ms > evidence.collection_completed_at_ms:
        raise TacticalCausalityError(
            f"collection_started_at_ms ({evidence.collection_started_at_ms}) > collection_completed_at_ms ({evidence.collection_completed_at_ms})"
        )
    if evidence.collection_completed_at_ms > dec_t:
        raise TacticalCausalityError(
            f"collection_completed_at_ms ({evidence.collection_completed_at_ms}) > decision_time_ms ({dec_t})"
        )

    if evidence.observed_at_ms > dec_t:
        raise TacticalCausalityError(
            f"observed_at_ms ({evidence.observed_at_ms}) > decision_time_ms ({dec_t})"
        )

    # 3. Cross-field identity invariants (Section 27)
    if not math.isclose(evidence.rule_score, evidence.rule_score_breakdown.final_rule_score, abs_tol=1e-6):
        raise TacticalEvidenceValidationError(
            f"evidence.rule_score ({evidence.rule_score}) != rule_score_breakdown.final_rule_score ({evidence.rule_score_breakdown.final_rule_score})"
        )

    if (
        evidence.directional_risk_plan is not None
        and evidence.decision_trace.final_directional_decision != evidence.directional_risk_plan.decision
    ):
        raise TacticalEvidenceValidationError(
            f"decision_trace.final_directional_decision ({evidence.decision_trace.final_directional_decision}) "
            f"!= directional_risk_plan.decision ({evidence.directional_risk_plan.decision})"
        )

    # 4. Playbook candidate completeness (Section 29)
    expected_playbooks = tuple(p.value for p in ACTIVE_PLAYBOOKS)
    actual_playbooks = tuple(c.playbook for c in evidence.playbook_candidates)
    if actual_playbooks != expected_playbooks:
        raise TacticalEvidenceValidationError(
            f"playbook_candidates order/content mismatch: expected {expected_playbooks}, got {actual_playbooks}"
        )
    if any(c.playbook == "RANGE_MEAN_REVERSION" for c in evidence.playbook_candidates):
        raise TacticalEvidenceValidationError(
            "RANGE_MEAN_REVERSION must not appear in evaluated playbook_candidates"
        )

    if evidence.selected_playbook is not None and evidence.selected_playbook not in expected_playbooks:
        raise TacticalEvidenceValidationError(
            f"selected_playbook {evidence.selected_playbook!r} not in active playbooks {expected_playbooks}"
        )
    if evidence.decision_trace.final_directional_decision in ("LONG", "SHORT") and not evidence.selected_playbook:
        raise TacticalEvidenceValidationError(
            f"Directional decision is {evidence.decision_trace.final_directional_decision} but selected_playbook is None"
        )


# ==============================================================================
# Pure Deterministic Evidence Builder (Section 7, 11, 21)
# ==============================================================================

def build_tactical_feature_evidence(
    *,
    assessment: SymbolAssessment,
    playbook_candidates: Sequence[PlaybookCandidate],
    decision_trace: PolicyDecisionTrace,
    rule_score_breakdown: RuleScoreBreakdown,
    config: MarketWatchConfig,
    policy_state_before: PolicyStateInputEvidence | Mapping[str, Any] | None = None,
) -> TacticalFeatureEvidenceV2:
    """Pure deterministic construction of immutable TacticalFeatureEvidenceV2."""
    snap = assessment.snapshot
    tf_15m = snap.tf_15m
    tf_1h = snap.tf_1h
    tf_4h = snap.tf_4h
    d_metrics = snap.derivatives

    # 1. Source Provenance
    watermark_15m = snap.closed_bar_watermarks.get("15m", tf_15m.closed_bar_end_time_ms)
    watermark_1h = snap.closed_bar_watermarks.get("1h", tf_1h.closed_bar_end_time_ms)
    watermark_4h = snap.closed_bar_watermarks.get("4h", tf_4h.closed_bar_end_time_ms)

    returns_obs: list[ReturnObservation] = []
    if snap.return_observations:
        returns_obs = list(snap.return_observations)
    else:
        # Fallback constructor if return_observations not explicitly attached to mock snapshot
        for horizon_ms, r_val, r_stat in [
            (3_600_000, snap.return_1h, snap.return_1h_status),
            (14_400_000, snap.return_4h, snap.return_4h_status),
            (43_200_000, snap.return_12h, snap.return_12h_status),
        ]:
            if r_val is None:
                actual_stat = "UNAVAILABLE" if r_stat == "AVAILABLE" else r_stat
                anchor_t = None
                actual_val = None
            else:
                actual_stat = r_stat
                anchor_t = (tf_15m.closed_bar_end_time_ms - horizon_ms) if actual_stat == "AVAILABLE" else None
                actual_val = r_val
            returns_obs.append(
                ReturnObservation(
                    horizon_ms=horizon_ms,
                    value=actual_val,
                    availability=actual_stat,
                    anchor_close_time_ms=anchor_t,
                    latest_close_time_ms=tf_15m.closed_bar_end_time_ms,
                    source_interval="15m",
                    semantics_version="ELAPSED_TIME_RETURNS_V1",
                )
            )

    p_idx_t = getattr(d_metrics, "premium_index_time_ms", None)
    if p_idx_t is None:
        p_idx_t = d_metrics.funding_time_ms
    f_t = d_metrics.funding_time_ms if d_metrics.funding_time_ms is not None else p_idx_t
    n_funding_t = getattr(d_metrics, "next_funding_time_ms", None)

    receipt_ts = snap.source_receipt_timestamps or {}
    source_prov = SourceProvenanceEvidence(
        closed_bar_watermark_15m=watermark_15m,
        closed_bar_watermark_1h=watermark_1h,
        closed_bar_watermark_4h=watermark_4h,
        returns=tuple(returns_obs),
        derivatives_observed_at_ms=receipt_ts.get("deriv_observed_at_ms"),
        funding_time_ms=f_t,
        premium_index_time_ms=p_idx_t,
        next_funding_time_ms=n_funding_t,
        open_interest_time_ms=d_metrics.open_interest_time_ms,
        long_short_time_ms=d_metrics.long_short_time_ms,
        taker_time_ms=d_metrics.taker_time_ms,
        basis_time_ms=d_metrics.basis_time_ms,
        ticker_receipt_ms=receipt_ts.get("ticker_receipt_ms"),
        oi_hist_receipt_ms=receipt_ts.get("oi_hist_receipt_ms"),
        top_pos_receipt_ms=receipt_ts.get("top_pos_receipt_ms"),
        top_acc_receipt_ms=receipt_ts.get("top_acc_receipt_ms"),
        server_time_receipt_ms=receipt_ts.get("server_time_receipt_ms"),
        field_availability=tuple(sorted(d_metrics.field_availability.items())),
        endpoint_errors=tuple(sorted(d_metrics.endpoint_errors.items())),
    )

    # 2. Timeframe features with latest confirmed bar & volatility-state completeness
    def _make_tf_feat(tf: Any) -> TimeframeFeaturesEvidence:
        lcb = getattr(tf, "latest_closed_bar", None)
        if isinstance(lcb, Candle):
            closed_bar_ev = ClosedBarEvidence.from_candle(lcb)
        elif isinstance(lcb, ClosedBarEvidence):
            closed_bar_ev = lcb
        elif lcb is not None and hasattr(lcb, "open") and hasattr(lcb, "close"):
            closed_bar_ev = ClosedBarEvidence(
                open_time_ms=getattr(lcb, "open_time_ms", tf.closed_bar_end_time_ms - 900_000),
                close_time_ms=getattr(lcb, "close_time_ms", tf.closed_bar_end_time_ms),
                open=lcb.open,
                high=lcb.high,
                low=lcb.low,
                close=lcb.close,
                volume=lcb.volume,
                quote_volume=getattr(lcb, "quote_volume", lcb.volume * lcb.close),
                trades=getattr(lcb, "trades", 0),
            )
        else:
            closed_bar_ev = ClosedBarEvidence(
                open_time_ms=tf.closed_bar_end_time_ms - 900_000,
                close_time_ms=tf.closed_bar_end_time_ms,
                open=tf.close,
                high=tf.close,
                low=tf.close,
                close=tf.close,
                volume=tf.volume,
                quote_volume=tf.volume * tf.close,
                trades=0,
            )
        return TimeframeFeaturesEvidence(
            interval=tf.interval,
            closed_bar_end_time_ms=tf.closed_bar_end_time_ms,
            latest_closed_bar=closed_bar_ev,
            close=tf.close,
            ema_fast=tf.ema_fast,
            ema_mid=tf.ema_mid,
            ema_slow=getattr(tf, "ema_slow", None),
            ema_slow_status=getattr(tf, "ema_slow_status", "AVAILABLE" if getattr(tf, "ema_slow", None) is not None else "UNAVAILABLE"),
            ema_fast_slope=tf.ema_fast_slope,
            ema_mid_slope=tf.ema_mid_slope,
            atr=tf.atr,
            atr_percentile=tf.atr_percentile,
            adx=tf.adx,
            rsi=tf.rsi,
            roc_12bars=getattr(tf, "roc_12bars", getattr(tf, "roc", 0.0)),
            volume=tf.volume,
            volume_z=tf.volume_z,
            bb_width=tf.bb_width,
            bb_width_percentile=tf.bb_width_percentile,
            is_volatility_compressed=bool(getattr(tf, "is_volatility_compressed", False)),
            is_volatility_expanded=bool(getattr(tf, "is_volatility_expanded", False)),
            has_prior_compression_window=bool(getattr(tf, "has_prior_compression_window", False)),
            recent_swing_high=tf.recent_swing_high,
            recent_swing_low=tf.recent_swing_low,
            supports=tuple(tf.supports),
            resistances=tuple(tf.resistances),
            structure=str(tf.structure),
            regime=str(tf.regime),
        )

    # Derivative risks vs reasons completeness (Section 22)
    deriv_risks = getattr(d_metrics, "risk_codes", ())
    deriv_feat = DerivativesFeaturesEvidence(
        mark_price=d_metrics.mark_price,
        index_price=d_metrics.index_price,
        funding_rate=d_metrics.funding_rate,
        funding_time_ms=f_t,
        premium_index_time_ms=p_idx_t,
        next_funding_time_ms=n_funding_t,
        current_open_interest=d_metrics.current_open_interest,
        open_interest_time_ms=d_metrics.open_interest_time_ms,
        oi_1h_change=d_metrics.oi_1h_change,
        oi_4h_change=d_metrics.oi_4h_change,
        oi_12h_change=d_metrics.oi_12h_change,
        global_account_long_short_ratio=d_metrics.global_account_long_short_ratio,
        long_short_time_ms=d_metrics.long_short_time_ms,
        top_trader_position_ratio=d_metrics.top_trader_position_ratio,
        top_trader_account_ratio=d_metrics.top_trader_account_ratio,
        taker_buy_sell_ratio=d_metrics.taker_buy_sell_ratio,
        taker_time_ms=d_metrics.taker_time_ms,
        basis_rate=d_metrics.basis_rate,
        basis_bps=d_metrics.basis_bps,
        basis_time_ms=d_metrics.basis_time_ms,
        spread_bps=d_metrics.spread_bps,
        order_book_imbalance=d_metrics.order_book_imbalance,
        derivatives_regime=str(d_metrics.regime),
        reasons=tuple(d_metrics.reasons),
        risks=tuple(deriv_risks),
        field_availability=tuple(sorted(d_metrics.field_availability.items())),
        endpoint_errors=tuple(sorted(d_metrics.endpoint_errors.items())),
    )

    p_metrics = snap.price
    snap_feat = MarketSnapshotFeaturesEvidence(
        tf_15m=_make_tf_feat(tf_15m),
        tf_1h=_make_tf_feat(tf_1h),
        tf_4h=_make_tf_feat(tf_4h),
        derivatives=deriv_feat,
        last_price=p_metrics.last_price,
        mark_price=p_metrics.mark_price,
        change_24h_pct=p_metrics.change_24h_pct,
        high_24h=p_metrics.high_24h,
        low_24h=p_metrics.low_24h,
        quote_volume_24h=p_metrics.quote_volume_24h,
        benchmark_context=str(assessment.directional.benchmark_context),
        return_1h=snap.return_1h,
        return_4h=snap.return_4h,
        return_12h=snap.return_12h,
        return_1h_status="UNAVAILABLE" if snap.return_1h is None and snap.return_1h_status == "AVAILABLE" else snap.return_1h_status,
        return_4h_status="UNAVAILABLE" if snap.return_4h is None and snap.return_4h_status == "AVAILABLE" else snap.return_4h_status,
        return_12h_status="UNAVAILABLE" if snap.return_12h is None and snap.return_12h_status == "AVAILABLE" else snap.return_12h_status,
    )

    # 3. Reference Universe Evidence
    rp = assessment.relative_performance
    ref_univ = ReferenceUniverseEvidence(
        version="TACTICAL_RS_UNIVERSE_V1",
        status=assessment.reference_universe_status,
        expected_members=tuple(config.relative_strength_universe),
        available_members=tuple(rp.available_members) if rp else (),
        missing_members=tuple(rp.missing_members) if rp else tuple(config.relative_strength_universe),
        incomplete_return_members=tuple(rp.incomplete_return_members) if rp else (),
        perf_1h=rp.perf_1h if rp else None,
        perf_4h=rp.perf_4h if rp else None,
        perf_12h=rp.perf_12h if rp else None,
        rel_to_btc_1h=rp.rel_to_btc_1h if rp else None,
        rel_to_eth_1h=rp.rel_to_eth_1h if rp else None,
        rel_to_median_1h=rp.rel_to_median_1h if rp else None,
        multi_tf_excess=rp.multi_tf_excess if rp else 0.0,
        score=rp.score if rp else 0.0,
        rank=rp.rank if rp else 0,
    )

    # 4. Playbook Candidates Evidence (Strict Frozen Registry Order, Section 21 & 29)
    cand_by_pb = {c.playbook: c for c in playbook_candidates}
    pb_evidences: list[PlaybookCandidateEvidence] = []
    for pb in ACTIVE_PLAYBOOKS:
        cand = cand_by_pb.get(pb)
        if cand is not None:
            c_status = cand.candidate_status.value if hasattr(cand.candidate_status, "value") else str(cand.candidate_status)
            c_dec = cand.decision.value if hasattr(cand.decision, "value") else str(cand.decision)
            c_conf = cand.confidence.value if hasattr(cand.confidence, "value") else str(cand.confidence)
            c_bo_state = cand.breakout_state.value if hasattr(cand.breakout_state, "value") else str(cand.breakout_state)
            pb_evidences.append(
                PlaybookCandidateEvidence(
                    playbook=pb.value,
                    candidate_status=c_status,
                    strategy_status=StrategyStatus.EXPERIMENTAL.value,
                    decision=c_dec,
                    entry_low=cand.entry_low,
                    entry_high=cand.entry_high,
                    stop_loss=cand.stop_loss,
                    take_profit_1=cand.take_profit_1,
                    take_profit_2=cand.take_profit_2,
                    invalidation=cand.invalidation,
                    structural_anchor_id=cand.structural_anchor_id,
                    reason_codes=tuple(cand.reason_codes),
                    risk_codes=tuple(cand.risk_codes),
                    setup_creation_bar_end_ms=cand.setup_creation_bar_end_ms,
                    breakout_state=c_bo_state,
                    breakout_level=cand.breakout_level,
                    breakout_direction=cand.breakout_direction,
                    breakout_bar_end_ms=cand.breakout_bar_end_ms,
                    failed_level=cand.failed_level,
                    confidence_band=c_conf,
                )
            )
        else:
            pb_evidences.append(
                PlaybookCandidateEvidence(
                    playbook=pb.value,
                    candidate_status="ABSENT",
                    strategy_status=StrategyStatus.EXPERIMENTAL.value,
                    decision="WAIT",
                    entry_low=None,
                    entry_high=None,
                    stop_loss=None,
                    take_profit_1=None,
                    take_profit_2=None,
                    invalidation=None,
                    structural_anchor_id=None,
                    reason_codes=("NO_CANDIDATE_EMITTED",),
                    risk_codes=(),
                    setup_creation_bar_end_ms=0,
                    breakout_state="NONE",
                    breakout_level=None,
                    breakout_direction=None,
                    breakout_bar_end_ms=None,
                    failed_level=None,
                    confidence_band="LOW",
                )
            )

    # 5. Exhaustion
    exh = assessment.exhaustion
    exh_ev = ExhaustionEvidence(
        state=exh.state.value if hasattr(exh.state, "value") else str(exh.state),
        distance_from_ema20_atr=exh.distance_from_ema20_atr,
        distance_from_ema50_atr=exh.distance_from_ema50_atr,
        distance_to_support_atr=exh.distance_to_support_atr,
        distance_to_resistance_atr=exh.distance_to_resistance_atr,
        recent_extension_atr=exh.recent_extension_atr,
        multi_bar_extension_atr=exh.multi_bar_extension_atr,
        reasons=tuple(exh.reasons),
    )

    # 6. Directional Risk Plan
    d_plan = assessment.directional
    d_ev = DirectionalPlanEvidence(
        decision=d_plan.decision.value if hasattr(d_plan.decision, "value") else str(d_plan.decision),
        setup=d_plan.setup.value if hasattr(d_plan.setup, "value") else str(d_plan.setup),
        regime=d_plan.regime.value if hasattr(d_plan.regime, "value") else str(d_plan.regime),
        entry_quality=d_plan.entry_quality.value if hasattr(d_plan.entry_quality, "value") else str(d_plan.entry_quality),
        entry_low=d_plan.entry_low,
        entry_high=d_plan.entry_high,
        add_level=d_plan.add_level,
        stop_loss=d_plan.stop_loss,
        take_profit_1=d_plan.take_profit_1,
        take_profit_2=d_plan.take_profit_2,
        invalidation_level=d_plan.invalidation_level,
        gross_rr=d_plan.gross_rr,
        net_rr=d_plan.net_rr,
        derivatives_regime=d_plan.derivatives_regime.value if hasattr(d_plan.derivatives_regime, "value") else str(d_plan.derivatives_regime),
        benchmark_context=d_plan.benchmark_context.value if hasattr(d_plan.benchmark_context, "value") else str(d_plan.benchmark_context),
        reason_codes=tuple(d_plan.reason_codes),
        risk_codes=tuple(d_plan.risk_codes),
        breakout_state=d_plan.breakout_state.value if hasattr(d_plan.breakout_state, "value") else str(d_plan.breakout_state),
        breakout_level=d_plan.breakout_level,
        breakout_direction=d_plan.breakout_direction,
        breakout_bar_end_ms=d_plan.breakout_bar_end_ms,
        rule_score=d_plan.rule_score,
        heuristic_quality_band_semantics=d_plan.heuristic_quality_band_semantics,
    )

    # 7. Grid Advisory Plan
    g_plan = assessment.grid
    g_ev = GridPlanEvidence(
        decision=g_plan.decision.value if hasattr(g_plan.decision, "value") else str(g_plan.decision),
        lower_bound=g_plan.lower_bound,
        upper_bound=g_plan.upper_bound,
        grid_count=g_plan.grid_count,
        estimated_grid_pct=g_plan.estimated_grid_pct,
        trigger_price=g_plan.trigger_price,
        stop_loss=g_plan.stop_loss,
        take_profit=g_plan.take_profit,
        reason_codes=tuple(g_plan.reason_codes),
    )

    # 8. Immutable Decision Config (Section 5 & 6)
    cfg_payload = market_watch_config_hash_payload(config)
    decision_config = DecisionConfigEvidence.from_payload(cfg_payload)

    # 9. Pre-decision policy state evidence (Section 20 & 21)
    if isinstance(policy_state_before, PolicyStateInputEvidence):
        pol_state_before = policy_state_before
    else:
        pol_state_before = PolicyStateInputEvidence.from_prev_state(policy_state_before)

    # 10. Assemble intermediate object to compute content hash
    provisional_evidence = TacticalFeatureEvidenceV2(
        evidence_schema_version=TACTICAL_FEATURE_EVIDENCE_SCHEMA_VERSION,
        evidence_id="",
        symbol=assessment.symbol,
        decision_time_ms=snap.decision_time_ms,
        observed_at_ms=snap.observed_at_ms,
        exchange_time_ms=snap.exchange_time_ms,
        collection_started_at_ms=snap.collection_started_at_ms,
        collection_completed_at_ms=snap.collection_completed_at_ms,
        snapshot_hash=snap.snapshot_hash,
        policy_version=assessment.policy_version,
        config_hash=assessment.config_hash,
        decision_config=decision_config,
        policy_state_before=pol_state_before,
        semantic_identity=assessment.semantic_identity,
        strategy_status=StrategyStatus.EXPERIMENTAL.value,
        source_provenance=source_prov,
        market_snapshot_features=snap_feat,
        reference_universe_evidence=ref_univ,
        playbook_candidates=tuple(pb_evidences),
        selected_playbook=(assessment.selected_playbook if assessment.selected_playbook not in ("NO_TRADE", "NONE", "", None) else None),
        selection_method=assessment.selection_method,
        selection_version=assessment.selection_version,
        eligible_playbooks=tuple(assessment.eligible_playbooks),
        actionable_playbooks=tuple(assessment.actionable_playbooks),
        decision_trace=decision_trace,
        rule_score=rule_score_breakdown.final_rule_score,
        rule_score_semantics=RULE_SCORE_SEMANTICS_VERSION,
        rule_score_breakdown=rule_score_breakdown,
        entry_quality=assessment.directional.entry_quality.value if hasattr(assessment.directional.entry_quality, "value") else str(assessment.directional.entry_quality),
        exhaustion=exh_ev,
        directional_risk_plan=d_ev,
        grid_advisory_plan=g_ev,
        lifecycle_state=assessment.lifecycle_state.value if hasattr(assessment.lifecycle_state, "value") else str(assessment.lifecycle_state),
        signal_identity=assessment.signal_identity or None,
        setup_key=assessment.setup_key or None,
        reason_codes=tuple(assessment.directional.reason_codes),
        risk_codes=tuple(assessment.directional.risk_codes),
        veto_reasons=tuple(assessment.veto_reasons),
    )

    validate_tactical_feature_evidence(provisional_evidence)
    payload = canonical_evidence_payload(provisional_evidence)
    evidence_id = compute_evidence_id(payload)

    final_evidence = TacticalFeatureEvidenceV2(
        evidence_schema_version=provisional_evidence.evidence_schema_version,
        evidence_id=evidence_id,
        symbol=provisional_evidence.symbol,
        decision_time_ms=provisional_evidence.decision_time_ms,
        observed_at_ms=provisional_evidence.observed_at_ms,
        exchange_time_ms=provisional_evidence.exchange_time_ms,
        collection_started_at_ms=provisional_evidence.collection_started_at_ms,
        collection_completed_at_ms=provisional_evidence.collection_completed_at_ms,
        snapshot_hash=provisional_evidence.snapshot_hash,
        policy_version=provisional_evidence.policy_version,
        config_hash=provisional_evidence.config_hash,
        decision_config=provisional_evidence.decision_config,
        policy_state_before=provisional_evidence.policy_state_before,
        semantic_identity=provisional_evidence.semantic_identity,
        strategy_status=provisional_evidence.strategy_status,
        source_provenance=provisional_evidence.source_provenance,
        market_snapshot_features=provisional_evidence.market_snapshot_features,
        reference_universe_evidence=provisional_evidence.reference_universe_evidence,
        playbook_candidates=provisional_evidence.playbook_candidates,
        selected_playbook=provisional_evidence.selected_playbook,
        selection_method=provisional_evidence.selection_method,
        selection_version=provisional_evidence.selection_version,
        eligible_playbooks=provisional_evidence.eligible_playbooks,
        actionable_playbooks=provisional_evidence.actionable_playbooks,
        decision_trace=provisional_evidence.decision_trace,
        rule_score=provisional_evidence.rule_score,
        rule_score_semantics=provisional_evidence.rule_score_semantics,
        rule_score_breakdown=provisional_evidence.rule_score_breakdown,
        entry_quality=provisional_evidence.entry_quality,
        exhaustion=provisional_evidence.exhaustion,
        directional_risk_plan=provisional_evidence.directional_risk_plan,
        grid_advisory_plan=provisional_evidence.grid_advisory_plan,
        lifecycle_state=provisional_evidence.lifecycle_state,
        signal_identity=provisional_evidence.signal_identity,
        setup_key=provisional_evidence.setup_key,
        reason_codes=provisional_evidence.reason_codes,
        risk_codes=provisional_evidence.risk_codes,
        veto_reasons=provisional_evidence.veto_reasons,
    )

    validate_tactical_feature_evidence(final_evidence)
    verify_tactical_evidence_identity(final_evidence)
    return final_evidence


def deserialize_tactical_feature_evidence(
    raw: str | dict[str, Any],
    *,
    verify_identity: bool = True,
) -> TacticalFeatureEvidenceV2:
    """Deserialize canonical or database JSON / dictionary into immutable TacticalFeatureEvidenceV2 with verification."""
    data: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw

    ev_id = data.get("evidence_id")
    if not ev_id or not isinstance(ev_id, str):
        raise TacticalEvidenceIdentityError("Missing or invalid evidence_id in serialized evidence data")

    sp_data = data["source_provenance"]
    returns_obs = tuple(
        ReturnObservation(
            horizon_ms=r["horizon_ms"],
            value=r["value"],
            availability=r["availability"],
            anchor_close_time_ms=r.get("anchor_close_time_ms"),
            latest_close_time_ms=r.get("latest_close_time_ms"),
            source_interval=r.get("source_interval", "15m"),
            semantics_version=r.get("semantics_version", "ELAPSED_TIME_RETURNS_V1"),
        )
        for r in sp_data["returns"]
    )
    source_prov = SourceProvenanceEvidence(
        closed_bar_watermark_15m=sp_data["closed_bar_watermark_15m"],
        closed_bar_watermark_1h=sp_data["closed_bar_watermark_1h"],
        closed_bar_watermark_4h=sp_data["closed_bar_watermark_4h"],
        returns=returns_obs,
        derivatives_observed_at_ms=sp_data.get("derivatives_observed_at_ms"),
        funding_time_ms=sp_data.get("funding_time_ms"),
        premium_index_time_ms=sp_data.get("premium_index_time_ms"),
        next_funding_time_ms=sp_data.get("next_funding_time_ms"),
        open_interest_time_ms=sp_data.get("open_interest_time_ms"),
        long_short_time_ms=sp_data.get("long_short_time_ms"),
        taker_time_ms=sp_data.get("taker_time_ms"),
        basis_time_ms=sp_data.get("basis_time_ms"),
        ticker_receipt_ms=sp_data.get("ticker_receipt_ms"),
        oi_hist_receipt_ms=sp_data.get("oi_hist_receipt_ms"),
        top_pos_receipt_ms=sp_data.get("top_pos_receipt_ms"),
        top_acc_receipt_ms=sp_data.get("top_acc_receipt_ms"),
        server_time_receipt_ms=sp_data.get("server_time_receipt_ms"),
        field_availability=tuple((k, v) for k, v in sp_data.get("field_availability", [])),
        endpoint_errors=tuple((k, v) for k, v in sp_data.get("endpoint_errors", [])),
    )

    def _parse_tf(t_data: dict[str, Any]) -> TimeframeFeaturesEvidence:
        lcb_data = t_data.get("latest_closed_bar")
        if lcb_data:
            latest_closed_bar = ClosedBarEvidence(
                open_time_ms=lcb_data["open_time_ms"],
                close_time_ms=lcb_data["close_time_ms"],
                open=lcb_data["open"],
                high=lcb_data["high"],
                low=lcb_data["low"],
                close=lcb_data["close"],
                volume=lcb_data["volume"],
                quote_volume=lcb_data["quote_volume"],
                trades=lcb_data["trades"],
            )
        else:
            latest_closed_bar = ClosedBarEvidence(
                open_time_ms=t_data["closed_bar_end_time_ms"] - 900_000,
                close_time_ms=t_data["closed_bar_end_time_ms"],
                open=t_data["close"],
                high=t_data["close"],
                low=t_data["close"],
                close=t_data["close"],
                volume=t_data["volume"],
                quote_volume=t_data["volume"] * t_data["close"],
                trades=0,
            )
        return TimeframeFeaturesEvidence(
            interval=t_data["interval"],
            closed_bar_end_time_ms=t_data["closed_bar_end_time_ms"],
            latest_closed_bar=latest_closed_bar,
            close=t_data["close"],
            ema_fast=t_data["ema_fast"],
            ema_mid=t_data["ema_mid"],
            ema_slow=t_data.get("ema_slow"),
            ema_slow_status=t_data.get("ema_slow_status", "AVAILABLE"),
            ema_fast_slope=t_data["ema_fast_slope"],
            ema_mid_slope=t_data["ema_mid_slope"],
            atr=t_data["atr"],
            atr_percentile=t_data["atr_percentile"],
            adx=t_data["adx"],
            rsi=t_data["rsi"],
            roc_12bars=t_data["roc_12bars"],
            volume=t_data["volume"],
            volume_z=t_data["volume_z"],
            bb_width=t_data["bb_width"],
            bb_width_percentile=t_data["bb_width_percentile"],
            is_volatility_compressed=t_data.get("is_volatility_compressed", False),
            is_volatility_expanded=t_data.get("is_volatility_expanded", False),
            has_prior_compression_window=t_data.get("has_prior_compression_window", False),
            recent_swing_high=t_data.get("recent_swing_high"),
            recent_swing_low=t_data.get("recent_swing_low"),
            supports=tuple(t_data.get("supports", [])),
            resistances=tuple(t_data.get("resistances", [])),
            structure=t_data["structure"],
            regime=t_data["regime"],
        )

    deriv_data = data["market_snapshot_features"]["derivatives"]
    deriv_feat = DerivativesFeaturesEvidence(
        mark_price=deriv_data.get("mark_price"),
        index_price=deriv_data.get("index_price"),
        funding_rate=deriv_data.get("funding_rate"),
        funding_time_ms=deriv_data.get("funding_time_ms"),
        premium_index_time_ms=deriv_data.get("premium_index_time_ms"),
        next_funding_time_ms=deriv_data.get("next_funding_time_ms"),
        current_open_interest=deriv_data.get("current_open_interest"),
        open_interest_time_ms=deriv_data.get("open_interest_time_ms"),
        oi_1h_change=deriv_data.get("oi_1h_change"),
        oi_4h_change=deriv_data.get("oi_4h_change"),
        oi_12h_change=deriv_data.get("oi_12h_change"),
        global_account_long_short_ratio=deriv_data.get("global_account_long_short_ratio"),
        long_short_time_ms=deriv_data.get("long_short_time_ms"),
        top_trader_position_ratio=deriv_data.get("top_trader_position_ratio"),
        top_trader_account_ratio=deriv_data.get("top_trader_account_ratio"),
        taker_buy_sell_ratio=deriv_data.get("taker_buy_sell_ratio"),
        taker_time_ms=deriv_data.get("taker_time_ms"),
        basis_rate=deriv_data.get("basis_rate"),
        basis_bps=deriv_data.get("basis_bps"),
        basis_time_ms=deriv_data.get("basis_time_ms"),
        spread_bps=deriv_data.get("spread_bps"),
        order_book_imbalance=deriv_data.get("order_book_imbalance"),
        derivatives_regime=deriv_data["derivatives_regime"],
        reasons=tuple(deriv_data.get("reasons", [])),
        risks=tuple(deriv_data.get("risks", [])),
        field_availability=tuple((k, v) for k, v in deriv_data.get("field_availability", [])),
        endpoint_errors=tuple((k, v) for k, v in deriv_data.get("endpoint_errors", [])),
    )

    snap_data = data["market_snapshot_features"]
    snap_feat = MarketSnapshotFeaturesEvidence(
        tf_15m=_parse_tf(snap_data["tf_15m"]),
        tf_1h=_parse_tf(snap_data["tf_1h"]),
        tf_4h=_parse_tf(snap_data["tf_4h"]),
        derivatives=deriv_feat,
        last_price=snap_data["last_price"],
        mark_price=snap_data.get("mark_price"),
        change_24h_pct=snap_data["change_24h_pct"],
        high_24h=snap_data["high_24h"],
        low_24h=snap_data["low_24h"],
        quote_volume_24h=snap_data["quote_volume_24h"],
        benchmark_context=snap_data["benchmark_context"],
        return_1h=snap_data.get("return_1h"),
        return_4h=snap_data.get("return_4h"),
        return_12h=snap_data.get("return_12h"),
        return_1h_status=snap_data["return_1h_status"],
        return_4h_status=snap_data["return_4h_status"],
        return_12h_status=snap_data["return_12h_status"],
    )

    ru_data = data["reference_universe_evidence"]
    ref_univ = ReferenceUniverseEvidence(
        version=ru_data["version"],
        status=ru_data["status"],
        expected_members=tuple(ru_data.get("expected_members", [])),
        available_members=tuple(ru_data.get("available_members", [])),
        missing_members=tuple(ru_data.get("missing_members", [])),
        incomplete_return_members=tuple(ru_data.get("incomplete_return_members", [])),
        perf_1h=ru_data.get("perf_1h"),
        perf_4h=ru_data.get("perf_4h"),
        perf_12h=ru_data.get("perf_12h"),
        rel_to_btc_1h=ru_data.get("rel_to_btc_1h"),
        rel_to_eth_1h=ru_data.get("rel_to_eth_1h"),
        rel_to_median_1h=ru_data.get("rel_to_median_1h"),
        multi_tf_excess=ru_data.get("multi_tf_excess", 0.0),
        score=ru_data.get("score", 0.0),
        rank=ru_data.get("rank", 0),
    )

    candidates = tuple(
        PlaybookCandidateEvidence(
            playbook=c["playbook"],
            candidate_status=c["candidate_status"],
            strategy_status=c["strategy_status"],
            decision=c["decision"],
            entry_low=c.get("entry_low"),
            entry_high=c.get("entry_high"),
            stop_loss=c.get("stop_loss"),
            take_profit_1=c.get("take_profit_1"),
            take_profit_2=c.get("take_profit_2"),
            invalidation=c.get("invalidation"),
            structural_anchor_id=c.get("structural_anchor_id"),
            reason_codes=tuple(c.get("reason_codes", [])),
            risk_codes=tuple(c.get("risk_codes", [])),
            setup_creation_bar_end_ms=c.get("setup_creation_bar_end_ms", 0),
            breakout_state=c.get("breakout_state", "NONE"),
            breakout_level=c.get("breakout_level"),
            breakout_direction=c.get("breakout_direction"),
            breakout_bar_end_ms=c.get("breakout_bar_end_ms"),
            failed_level=c.get("failed_level"),
            confidence_band=c.get("confidence_band", "LOW"),
        )
        for c in data["playbook_candidates"]
    )

    def _parse_stage(s_data: dict[str, Any]) -> PolicyGateStageTrace:
        return PolicyGateStageTrace(
            stage_name=s_data["stage_name"],
            input_decision=s_data["input_decision"],
            output_decision=s_data["output_decision"],
            new_reason_codes=tuple(s_data.get("new_reason_codes", [])),
            new_risk_codes=tuple(s_data.get("new_risk_codes", [])),
            veto_flag=s_data.get("veto_flag", False),
        )

    dt_data = data["decision_trace"]
    decision_trace = PolicyDecisionTrace(
        selected_candidate_decision=dt_data["selected_candidate_decision"],
        after_entry_quality_gate=_parse_stage(dt_data["after_entry_quality_gate"]),
        after_benchmark_gate=_parse_stage(dt_data["after_benchmark_gate"]),
        after_derivatives_gate=_parse_stage(dt_data["after_derivatives_gate"]),
        after_fatal_veto=_parse_stage(dt_data["after_fatal_veto"]),
        final_directional_decision=dt_data["final_directional_decision"],
    )

    rsb_data = data["rule_score_breakdown"]
    rule_score_breakdown = RuleScoreBreakdown(
        effective_direction=rsb_data["effective_direction"],
        adx_score=rsb_data["adx_score"],
        ema_slope_score=rsb_data["ema_slope_score"],
        trend_quality=rsb_data["trend_quality"],
        structure_quality=rsb_data["structure_quality"],
        entry_quality_score=rsb_data["entry_quality_score"],
        derivatives_confirmation_score=rsb_data["derivatives_confirmation_score"],
        volume_z_score=rsb_data["volume_z_score"],
        taker_score=rsb_data["taker_score"],
        participation_quality=rsb_data["participation_quality"],
        relative_strength_score=rsb_data["relative_strength_score"],
        net_rr_score=rsb_data["net_rr_score"],
        weighted_base=rsb_data["weighted_base"],
        crowding_penalty=rsb_data["crowding_penalty"],
        overextension_penalty=rsb_data["overextension_penalty"],
        benchmark_penalty=rsb_data["benchmark_penalty"],
        low_liquidity_penalty=rsb_data["low_liquidity_penalty"],
        total_penalty=rsb_data["total_penalty"],
        pre_wait_adjustment_score=rsb_data["pre_wait_adjustment_score"],
        wait_adjustment_applied=rsb_data["wait_adjustment_applied"],
        final_rule_score=rsb_data["final_rule_score"],
    )

    exh_data = data["exhaustion"]
    exhaustion = ExhaustionEvidence(
        state=exh_data["state"],
        distance_from_ema20_atr=exh_data["distance_from_ema20_atr"],
        distance_from_ema50_atr=exh_data["distance_from_ema50_atr"],
        distance_to_support_atr=exh_data["distance_to_support_atr"],
        distance_to_resistance_atr=exh_data["distance_to_resistance_atr"],
        recent_extension_atr=exh_data["recent_extension_atr"],
        multi_bar_extension_atr=exh_data["multi_bar_extension_atr"],
        reasons=tuple(exh_data.get("reasons", [])),
    )

    d_ev = None
    if data.get("directional_risk_plan"):
        dp_data = data["directional_risk_plan"]
        d_ev = DirectionalPlanEvidence(
            decision=dp_data["decision"],
            setup=dp_data["setup"],
            regime=dp_data["regime"],
            entry_quality=dp_data["entry_quality"],
            entry_low=dp_data["entry_low"],
            entry_high=dp_data["entry_high"],
            add_level=dp_data.get("add_level"),
            stop_loss=dp_data["stop_loss"],
            take_profit_1=dp_data["take_profit_1"],
            take_profit_2=dp_data["take_profit_2"],
            invalidation_level=dp_data["invalidation_level"],
            gross_rr=dp_data["gross_rr"],
            net_rr=dp_data["net_rr"],
            derivatives_regime=dp_data["derivatives_regime"],
            benchmark_context=dp_data["benchmark_context"],
            reason_codes=tuple(dp_data.get("reason_codes", [])),
            risk_codes=tuple(dp_data.get("risk_codes", [])),
            breakout_state=dp_data["breakout_state"],
            breakout_level=dp_data.get("breakout_level"),
            breakout_direction=dp_data.get("breakout_direction"),
            breakout_bar_end_ms=dp_data.get("breakout_bar_end_ms"),
            rule_score=dp_data["rule_score"],
            heuristic_quality_band_semantics=dp_data["heuristic_quality_band_semantics"],
        )

    g_ev = None
    if data.get("grid_advisory_plan"):
        gp_data = data["grid_advisory_plan"]
        g_ev = GridPlanEvidence(
            decision=gp_data["decision"],
            lower_bound=gp_data.get("lower_bound"),
            upper_bound=gp_data.get("upper_bound"),
            grid_count=gp_data["grid_count"],
            estimated_grid_pct=gp_data.get("estimated_grid_pct"),
            trigger_price=gp_data.get("trigger_price"),
            stop_loss=gp_data.get("stop_loss"),
            take_profit=gp_data.get("take_profit"),
            reason_codes=tuple(gp_data.get("reason_codes", [])),
        )

    sem_id = TacticalSemanticIdentity(**data["semantic_identity"])

    cfg_data = data["decision_config"]
    if isinstance(cfg_data, dict):
        decision_config = DecisionConfigEvidence.from_payload(cfg_data)
    elif isinstance(cfg_data, DecisionConfigEvidence):
        decision_config = cfg_data
    elif isinstance(cfg_data, str):
        decision_config = DecisionConfigEvidence(canonical_json=cfg_data)
    else:
        decision_config = DecisionConfigEvidence.from_payload(dict(cfg_data))

    pol_state_before = PolicyStateInputEvidence.from_dict(data.get("policy_state_before"))

    evidence = TacticalFeatureEvidenceV2(
        evidence_schema_version=data["evidence_schema_version"],
        evidence_id=ev_id,
        symbol=data["symbol"],
        decision_time_ms=data["decision_time_ms"],
        observed_at_ms=data["observed_at_ms"],
        exchange_time_ms=data["exchange_time_ms"],
        collection_started_at_ms=data["collection_started_at_ms"],
        collection_completed_at_ms=data["collection_completed_at_ms"],
        snapshot_hash=data["snapshot_hash"],
        policy_version=data["policy_version"],
        config_hash=data["config_hash"],
        decision_config=decision_config,
        policy_state_before=pol_state_before,
        semantic_identity=sem_id,
        strategy_status=data["strategy_status"],
        source_provenance=source_prov,
        market_snapshot_features=snap_feat,
        reference_universe_evidence=ref_univ,
        playbook_candidates=candidates,
        selected_playbook=(data.get("selected_playbook") if data.get("selected_playbook") not in ("NO_TRADE", "NONE", "", None) else None),
        selection_method=data["selection_method"],
        selection_version=data["selection_version"],
        eligible_playbooks=tuple(data.get("eligible_playbooks", [])),
        actionable_playbooks=tuple(data.get("actionable_playbooks", [])),
        decision_trace=decision_trace,
        rule_score=data["rule_score"],
        rule_score_semantics=data["rule_score_semantics"],
        rule_score_breakdown=rule_score_breakdown,
        entry_quality=data["entry_quality"],
        exhaustion=exhaustion,
        directional_risk_plan=d_ev,
        grid_advisory_plan=g_ev,
        lifecycle_state=data["lifecycle_state"],
        signal_identity=data.get("signal_identity"),
        setup_key=data.get("setup_key"),
        reason_codes=tuple(data.get("reason_codes", [])),
        risk_codes=tuple(data.get("risk_codes", [])),
        veto_reasons=tuple(data.get("veto_reasons", [])),
    )

    if verify_identity:
        verify_tactical_evidence_identity(evidence)
        validate_tactical_feature_evidence(evidence)

    return evidence
