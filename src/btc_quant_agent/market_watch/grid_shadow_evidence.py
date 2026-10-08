from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast

from .domain import GridDecision
from .evidence import (
    GridPlanEvidence,
    TacticalFeatureEvidenceV2,
    canonical_json_dump,
)

# ==============================================================================
# Frozen Version Identities
# ==============================================================================

TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION = "TACTICAL_GRID_SHADOW_EVALUATION_V1"
GRID_OUTCOME_PROFILE_VERSION = "GRID_OUTCOME_PROFILE_V1"
GRID_PATH_MODEL_VERSION = "GRID_1M_CONSERVATIVE_TWO_PATH_V1"
GRID_ACCOUNTING_VERSION = "NORMALIZED_GRID_ACCOUNTING_V1"

TACTICAL_GRID_SHADOW_EVALUATION_V1 = TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION
GRID_OUTCOME_PROFILE_V1 = GRID_OUTCOME_PROFILE_VERSION
GRID_1M_CONSERVATIVE_TWO_PATH_V1 = GRID_PATH_MODEL_VERSION
NORMALIZED_GRID_ACCOUNTING_V1 = GRID_ACCOUNTING_VERSION

GRID_HORIZON_HOURS = 24
GRID_HORIZON_BARS_15M = 96
GRID_HORIZON_MS = 86_400_000  # 24 * 3600 * 1000


# ==============================================================================
# Domain Taxonomy & Exceptions
# ==============================================================================

class TacticalGridShadowEvaluationError(Exception):
    """Base exception for B2B grid shadow evaluation failures."""


class TacticalGridShadowEvaluationIdentityError(TacticalGridShadowEvaluationError):
    """Raised when evaluation identity is malformed, missing, or tampered."""


class TacticalGridShadowEvaluationConflictError(TacticalGridShadowEvaluationError):
    """Raised on divergent replay under identical natural key."""


class TacticalGridShadowEvaluationValidationError(TacticalGridShadowEvaluationError):
    """Raised when an evaluation artifact violates semantic invariants."""


class GridEligibilityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    NOT_ACTIVE_PAUSE = "NOT_ACTIVE_PAUSE"
    PENDING_HORIZON = "PENDING_HORIZON"
    PENDING_DATA_GAP = "PENDING_DATA_GAP"
    RESOLVED = "RESOLVED"


class GridTerminalReason(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    HORIZON = "HORIZON"


# ==============================================================================
# Deterministic Level and Reference Price Helpers
# ==============================================================================

def construct_grid_levels(lower_bound: float, upper_bound: float, grid_count: int) -> tuple[float, ...]:
    """Construct N+1 deterministic monotonic arithmetic levels from bounds using string Decimal arithmetic."""
    if lower_bound <= 0:
        raise TacticalGridShadowEvaluationValidationError("lower_bound must be positive")
    if upper_bound <= lower_bound:
        raise TacticalGridShadowEvaluationValidationError("upper_bound must exceed lower_bound")
    if grid_count < 3:
        raise TacticalGridShadowEvaluationValidationError("grid_count must be at least 3")

    l_dec = Decimal(str(lower_bound))
    u_dec = Decimal(str(upper_bound))
    n_dec = Decimal(grid_count)
    step = (u_dec - l_dec) / n_dec

    levels: list[float] = []
    for i in range(grid_count + 1):
        lvl = float(l_dec + Decimal(i) * step)
        levels.append(lvl)

    return tuple(levels)


def compute_anchor_index(levels: Sequence[float], reference_price: float) -> int:
    """Select the nearest level index to the reference price. Tie breaks to lower index."""
    if not levels:
        raise TacticalGridShadowEvaluationValidationError("Cannot anchor empty levels")
    ref = Decimal(str(reference_price))
    return min(range(len(levels)), key=lambda i: (abs(Decimal(str(levels[i])) - ref), i))


def resolve_reference_price(grid_plan: GridPlanEvidence, evidence: TacticalFeatureEvidenceV2) -> float:
    """Resolve decision-time reference price following strict precedence."""
    if (
        grid_plan.trigger_price is not None
        and math.isfinite(grid_plan.trigger_price)
        and grid_plan.trigger_price > 0
        and grid_plan.lower_bound is not None
        and grid_plan.upper_bound is not None
        and grid_plan.lower_bound <= grid_plan.trigger_price <= grid_plan.upper_bound
    ):
        return float(grid_plan.trigger_price)

    close_15m = getattr(evidence.market_snapshot_features.tf_15m, "close", None)
    if close_15m is not None and math.isfinite(close_15m) and close_15m > 0:
        return float(close_15m)

    raise TacticalGridShadowEvaluationValidationError("MISSING_REFERENCE_PRICE")


# ==============================================================================
# Immutable Artifact Data Structure
# ==============================================================================

@dataclass(frozen=True)
class TacticalGridShadowEvaluationV1:
    """Immutable evaluation artifact for B2B Grid Shadow Evaluation V1."""

    # Schema & Profile Identity
    evaluation_schema_version: str
    evaluation_id: str
    evaluation_profile_version: str
    grid_path_model_version: str
    grid_accounting_version: str

    # Source Linkage
    feature_evidence_id: str
    symbol: str
    decision_time_ms: int
    snapshot_hash: str
    policy_version: str
    config_hash: str
    semantic_identity: dict[str, Any]

    # Decision-time Frozen Plan & Geometry
    grid_decision: str
    frozen_grid_plan: dict[str, Any]
    reference_price: float | None
    anchor_index: int | None
    grid_levels: tuple[float, ...]

    # Horizon & Outcome Timing
    evaluation_start_ms: int
    evaluation_end_ms: int
    terminal_time_ms: int | None
    terminal_reason: str | None
    eligibility_status: str

    # Coverage & Ambiguity Status
    market_path_coverage: str
    funding_coverage: str
    future_assessment_diagnostic_status: str
    ambiguity_events: tuple[dict[str, Any], ...]

    # Primary PnL Metrics (Normalized return relative to 1.0 capital)
    paired_cycle_count: int
    paired_gross_pnl: float
    paired_maker_fees: float
    paired_net_pnl: float
    terminal_unpaired_gross_pnl: float
    terminal_taker_fee: float
    terminal_slippage_cost: float
    gross_pnl_before_costs: float
    total_trading_fees: float
    total_slippage_cost: float
    funding_pnl: float | None
    net_pnl_after_fees_slippage: float
    net_pnl_after_funding: float | None

    # Inventory / Utilization Metrics
    max_abs_inventory_notional: float
    mean_abs_inventory_notional_time_weighted: float
    max_open_lot_count: int
    long_inventory_peak: float
    short_inventory_peak: float
    peak_capital_utilization: float
    mean_capital_utilization: float

    # Equity / Underwater / Drawdown Metrics
    min_marked_equity: float
    maximum_underwater: float
    max_drawdown_from_prior_peak: float

    # Boundary Metrics
    lower_boundary_breached: bool
    upper_boundary_breached: bool
    first_lower_boundary_breach_ms: int | None
    first_upper_boundary_breach_ms: int | None
    boundary_breach_count: int

    # Policy / Shift / Trend Diagnostics
    grid_shift_count: int | None
    grid_shift_frequency_per_day: float | None
    first_grid_shift_ms: int | None
    first_policy_pause_ms: int | None
    first_technical_trend_transition_ms: int | None
    net_equity_at_first_trend_transition: float | None
    post_transition_net_pnl_delta: float | None
    trend_transition_loss: float | None

    # Persistence Metadata
    persisted_at_ms: int | None = None

    def to_canonical_payload(self) -> dict[str, Any]:
        """Convert evaluation to canonical JSON dictionary excluding evaluation_id and persisted_at_ms."""
        return {
            "evaluation_schema_version": self.evaluation_schema_version,
            "evaluation_profile_version": self.evaluation_profile_version,
            "grid_path_model_version": self.grid_path_model_version,
            "grid_accounting_version": self.grid_accounting_version,
            "feature_evidence_id": self.feature_evidence_id,
            "symbol": self.symbol,
            "decision_time_ms": self.decision_time_ms,
            "snapshot_hash": self.snapshot_hash,
            "policy_version": self.policy_version,
            "config_hash": self.config_hash,
            "semantic_identity": self.semantic_identity,
            "grid_decision": self.grid_decision,
            "frozen_grid_plan": self.frozen_grid_plan,
            "reference_price": round(self.reference_price, 8) if self.reference_price is not None else None,
            "anchor_index": self.anchor_index,
            "grid_levels": [round(lvl, 8) for lvl in self.grid_levels],
            "evaluation_start_ms": self.evaluation_start_ms,
            "evaluation_end_ms": self.evaluation_end_ms,
            "terminal_time_ms": self.terminal_time_ms,
            "terminal_reason": self.terminal_reason,
            "eligibility_status": self.eligibility_status,
            "market_path_coverage": self.market_path_coverage,
            "funding_coverage": self.funding_coverage,
            "future_assessment_diagnostic_status": self.future_assessment_diagnostic_status,
            "ambiguity_events": list(self.ambiguity_events),
            "paired_cycle_count": self.paired_cycle_count,
            "paired_gross_pnl": round(self.paired_gross_pnl, 8),
            "paired_maker_fees": round(self.paired_maker_fees, 8),
            "paired_net_pnl": round(self.paired_net_pnl, 8),
            "terminal_unpaired_gross_pnl": round(self.terminal_unpaired_gross_pnl, 8),
            "terminal_taker_fee": round(self.terminal_taker_fee, 8),
            "terminal_slippage_cost": round(self.terminal_slippage_cost, 8),
            "gross_pnl_before_costs": round(self.gross_pnl_before_costs, 8),
            "total_trading_fees": round(self.total_trading_fees, 8),
            "total_slippage_cost": round(self.total_slippage_cost, 8),
            "funding_pnl": round(self.funding_pnl, 8) if self.funding_pnl is not None else None,
            "net_pnl_after_fees_slippage": round(self.net_pnl_after_fees_slippage, 8),
            "net_pnl_after_funding": round(self.net_pnl_after_funding, 8) if self.net_pnl_after_funding is not None else None,
            "max_abs_inventory_notional": round(self.max_abs_inventory_notional, 8),
            "mean_abs_inventory_notional_time_weighted": round(self.mean_abs_inventory_notional_time_weighted, 8),
            "max_open_lot_count": self.max_open_lot_count,
            "long_inventory_peak": round(self.long_inventory_peak, 8),
            "short_inventory_peak": round(self.short_inventory_peak, 8),
            "peak_capital_utilization": round(self.peak_capital_utilization, 8),
            "mean_capital_utilization": round(self.mean_capital_utilization, 8),
            "min_marked_equity": round(self.min_marked_equity, 8),
            "maximum_underwater": round(self.maximum_underwater, 8),
            "max_drawdown_from_prior_peak": round(self.max_drawdown_from_prior_peak, 8),
            "lower_boundary_breached": self.lower_boundary_breached,
            "upper_boundary_breached": self.upper_boundary_breached,
            "first_lower_boundary_breach_ms": self.first_lower_boundary_breach_ms,
            "first_upper_boundary_breach_ms": self.first_upper_boundary_breach_ms,
            "boundary_breach_count": self.boundary_breach_count,
            "grid_shift_count": self.grid_shift_count,
            "grid_shift_frequency_per_day": round(self.grid_shift_frequency_per_day, 8) if self.grid_shift_frequency_per_day is not None else None,
            "first_grid_shift_ms": self.first_grid_shift_ms,
            "first_policy_pause_ms": self.first_policy_pause_ms,
            "first_technical_trend_transition_ms": self.first_technical_trend_transition_ms,
            "net_equity_at_first_trend_transition": round(self.net_equity_at_first_trend_transition, 8) if self.net_equity_at_first_trend_transition is not None else None,
            "post_transition_net_pnl_delta": round(self.post_transition_net_pnl_delta, 8) if self.post_transition_net_pnl_delta is not None else None,
            "trend_transition_loss": round(self.trend_transition_loss, 8) if self.trend_transition_loss is not None else None,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to complete dictionary including evaluation_id and persisted_at_ms."""
        data = self.to_canonical_payload()
        data["evaluation_id"] = self.evaluation_id
        data["persisted_at_ms"] = self.persisted_at_ms
        return data

    def recompute_evaluation_id(self) -> str:
        """Deterministically calculate evaluation_id from canonical payload."""
        payload = self.to_canonical_payload()
        dumped = canonical_json_dump(payload)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

    def as_canonical_json(self) -> str:
        """Output complete JSON representation with embedded evaluation_id."""
        data = self.to_dict()
        return canonical_json_dump(data)


# ==============================================================================
# Hashing & Serialization Functions
# ==============================================================================

def compute_grid_evaluation_id(payload_or_eval: dict[str, Any] | TacticalGridShadowEvaluationV1) -> str:
    """Compute deterministic SHA-256 evaluation_id from canonical payload."""
    if isinstance(payload_or_eval, TacticalGridShadowEvaluationV1):
        payload = payload_or_eval.to_canonical_payload()
    else:
        payload = dict(payload_or_eval)
        payload.pop("evaluation_id", None)
        payload.pop("persisted_at_ms", None)

    canonical = canonical_json_dump(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_grid_shadow_evaluation_json(evaluation: TacticalGridShadowEvaluationV1) -> str:
    """Return canonical JSON representation of the evaluation artifact."""
    return evaluation.as_canonical_json()


def verify_grid_shadow_evaluation_identity(evaluation: TacticalGridShadowEvaluationV1) -> None:
    """Verify that evaluation.evaluation_id exactly matches its canonical content hash."""
    expected_id = evaluation.recompute_evaluation_id()
    if evaluation.evaluation_id != expected_id:
        raise TacticalGridShadowEvaluationIdentityError(
            f"B2B_EVALUATION_ID_MISMATCH: evaluation_id '{evaluation.evaluation_id}' "
            f"does not match computed hash '{expected_id}'"
        )


verify_tactical_grid_shadow_evaluation_identity = verify_grid_shadow_evaluation_identity


def validate_tactical_grid_shadow_evaluation(evaluation: TacticalGridShadowEvaluationV1) -> None:
    """Validate all structural and semantic invariants of TacticalGridShadowEvaluationV1."""
    if evaluation.evaluation_schema_version != TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION:
        raise TacticalGridShadowEvaluationValidationError(
            f"Invalid schema version: expected {TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION}, got {evaluation.evaluation_schema_version}"
        )
    if evaluation.evaluation_profile_version != GRID_OUTCOME_PROFILE_VERSION:
        raise TacticalGridShadowEvaluationValidationError(
            f"Invalid profile version: expected {GRID_OUTCOME_PROFILE_VERSION}, got {evaluation.evaluation_profile_version}"
        )
    if evaluation.grid_path_model_version != GRID_PATH_MODEL_VERSION:
        raise TacticalGridShadowEvaluationValidationError(
            f"Invalid path model version: expected {GRID_PATH_MODEL_VERSION}, got {evaluation.grid_path_model_version}"
        )
    if evaluation.grid_accounting_version != GRID_ACCOUNTING_VERSION:
        raise TacticalGridShadowEvaluationValidationError(
            f"Invalid accounting version: expected {GRID_ACCOUNTING_VERSION}, got {evaluation.grid_accounting_version}"
        )

    verify_grid_shadow_evaluation_identity(evaluation)

    if not evaluation.feature_evidence_id:
        raise TacticalGridShadowEvaluationValidationError("Missing feature_evidence_id")
    if not evaluation.symbol:
        raise TacticalGridShadowEvaluationValidationError("Missing symbol")

    # Horizon arithmetic check
    expected_horizon_end = evaluation.evaluation_start_ms + GRID_HORIZON_MS
    if evaluation.evaluation_end_ms != expected_horizon_end:
        raise TacticalGridShadowEvaluationValidationError(
            f"evaluation_end_ms mismatch: start={evaluation.evaluation_start_ms}, end={evaluation.evaluation_end_ms}, expected={expected_horizon_end}"
        )

    # Check non-finite float fields
    for field_name, val in [
        ("paired_gross_pnl", evaluation.paired_gross_pnl),
        ("paired_maker_fees", evaluation.paired_maker_fees),
        ("paired_net_pnl", evaluation.paired_net_pnl),
        ("terminal_unpaired_gross_pnl", evaluation.terminal_unpaired_gross_pnl),
        ("terminal_taker_fee", evaluation.terminal_taker_fee),
        ("terminal_slippage_cost", evaluation.terminal_slippage_cost),
        ("gross_pnl_before_costs", evaluation.gross_pnl_before_costs),
        ("total_trading_fees", evaluation.total_trading_fees),
        ("total_slippage_cost", evaluation.total_slippage_cost),
        ("net_pnl_after_fees_slippage", evaluation.net_pnl_after_fees_slippage),
        ("max_abs_inventory_notional", evaluation.max_abs_inventory_notional),
        ("peak_capital_utilization", evaluation.peak_capital_utilization),
        ("mean_capital_utilization", evaluation.mean_capital_utilization),
        ("min_marked_equity", evaluation.min_marked_equity),
        ("maximum_underwater", evaluation.maximum_underwater),
        ("max_drawdown_from_prior_peak", evaluation.max_drawdown_from_prior_peak),
    ]:
        if not math.isfinite(val):
            raise TacticalGridShadowEvaluationValidationError(f"Field {field_name} has non-finite value: {val}")

    if evaluation.funding_pnl is not None and not math.isfinite(evaluation.funding_pnl):
        raise TacticalGridShadowEvaluationValidationError(f"funding_pnl has non-finite value: {evaluation.funding_pnl}")
    if evaluation.net_pnl_after_funding is not None and not math.isfinite(evaluation.net_pnl_after_funding):
        raise TacticalGridShadowEvaluationValidationError(f"net_pnl_after_funding has non-finite value: {evaluation.net_pnl_after_funding}")

    # Maximum underwater is min(0.0, min_marked_equity)
    expected_underwater = min(0.0, evaluation.min_marked_equity)
    if not math.isclose(evaluation.maximum_underwater, expected_underwater, rel_tol=1e-6, abs_tol=1e-6):
        raise TacticalGridShadowEvaluationValidationError(
            f"maximum_underwater {evaluation.maximum_underwater} does not equal min(0.0, min_marked_equity) {expected_underwater}"
        )

    # Drawdown must be <= 0
    if evaluation.max_drawdown_from_prior_peak > 1e-6:
        raise TacticalGridShadowEvaluationValidationError(
            f"max_drawdown_from_prior_peak must be non-positive: {evaluation.max_drawdown_from_prior_peak}"
        )

    # Capital utilization cap
    if evaluation.peak_capital_utilization > 1.0 + 1e-5:
        raise TacticalGridShadowEvaluationValidationError(
            f"peak_capital_utilization {evaluation.peak_capital_utilization} exceeds 1.0 normalized reference capital"
        )

    # Paired cycles
    if evaluation.paired_cycle_count < 0:
        raise TacticalGridShadowEvaluationValidationError("paired_cycle_count cannot be negative")

    # Inactive / PAUSE plan invariants
    if evaluation.grid_decision == GridDecision.PAUSE.value:
        if evaluation.eligibility_status != GridEligibilityStatus.NOT_ACTIVE_PAUSE.value:
            raise TacticalGridShadowEvaluationValidationError("PAUSE plan must have eligibility_status NOT_ACTIVE_PAUSE")
        if evaluation.paired_cycle_count != 0 or evaluation.paired_gross_pnl != 0.0:
            raise TacticalGridShadowEvaluationValidationError("PAUSE plan cannot have simulated fills or paired profit")
        if evaluation.max_open_lot_count != 0 or evaluation.peak_capital_utilization != 0.0:
            raise TacticalGridShadowEvaluationValidationError("PAUSE plan cannot accumulate inventory")
        if evaluation.terminal_reason is not None:
            raise TacticalGridShadowEvaluationValidationError("PAUSE plan cannot have a terminal trigger reason")

    # Active plan invariants
    if evaluation.grid_decision in (GridDecision.LONG_BIAS.value, GridDecision.SHORT_BIAS.value, GridDecision.NEUTRAL.value):
        levels = evaluation.grid_levels
        if len(levels) < 4:  # N >= 3 means at least 4 levels
            raise TacticalGridShadowEvaluationValidationError(f"Grid levels count must be at least 4 (N+1 where N>=3), got {len(levels)}")
        # Check strict monotonicity
        for i in range(len(levels) - 1):
            if levels[i] >= levels[i + 1]:
                raise TacticalGridShadowEvaluationValidationError(f"Grid levels are not strictly monotonic: levels[{i}]={levels[i]} >= levels[{i+1}]={levels[i+1]}")

        if evaluation.reference_price is None or evaluation.reference_price <= 0:
            raise TacticalGridShadowEvaluationValidationError("Active evaluation must have valid positive reference_price")
        if evaluation.anchor_index is None or not (0 <= evaluation.anchor_index < len(levels)):
            raise TacticalGridShadowEvaluationValidationError("Active evaluation must have anchor_index within valid levels range")

        if evaluation.eligibility_status == GridEligibilityStatus.RESOLVED.value:
            if evaluation.terminal_reason not in [
                GridTerminalReason.STOP_LOSS.value,
                GridTerminalReason.TAKE_PROFIT.value,
                GridTerminalReason.HORIZON.value,
            ]:
                raise TacticalGridShadowEvaluationValidationError(
                    f"Resolved active evaluation must have valid terminal_reason, got {evaluation.terminal_reason}"
                )
            if evaluation.terminal_time_ms is None or not (
                evaluation.evaluation_start_ms <= evaluation.terminal_time_ms <= evaluation.evaluation_end_ms
            ):
                raise TacticalGridShadowEvaluationValidationError(
                    f"terminal_time_ms {evaluation.terminal_time_ms} must lie within [{evaluation.evaluation_start_ms}, {evaluation.evaluation_end_ms}]"
                )

    # Funding consistency
    if evaluation.funding_coverage != "COMPLETE":
        if evaluation.funding_pnl is not None:
            raise TacticalGridShadowEvaluationValidationError(
                f"funding_pnl must be None when funding_coverage is {evaluation.funding_coverage}"
            )
        if evaluation.net_pnl_after_funding is not None:
            raise TacticalGridShadowEvaluationValidationError(
                f"net_pnl_after_funding must be None when funding_coverage is {evaluation.funding_coverage}"
            )

    # Policy diagnostics consistency
    if evaluation.future_assessment_diagnostic_status != "COMPLETE":
        for metric_name, metric_val in [
            ("grid_shift_count", evaluation.grid_shift_count),
            ("grid_shift_frequency_per_day", evaluation.grid_shift_frequency_per_day),
            ("first_grid_shift_ms", evaluation.first_grid_shift_ms),
            ("first_policy_pause_ms", evaluation.first_policy_pause_ms),
            ("first_technical_trend_transition_ms", evaluation.first_technical_trend_transition_ms),
            ("net_equity_at_first_trend_transition", evaluation.net_equity_at_first_trend_transition),
            ("post_transition_net_pnl_delta", evaluation.post_transition_net_pnl_delta),
            ("trend_transition_loss", evaluation.trend_transition_loss),
        ]:
            if metric_val is not None:
                raise TacticalGridShadowEvaluationValidationError(
                    f"{metric_name} must be None when future_assessment_diagnostic_status is {evaluation.future_assessment_diagnostic_status}"
                )


def deserialize_tactical_grid_shadow_evaluation(
    raw_json_or_dict: str | Mapping[str, Any],
    *,
    verify_identity: bool = True,
    require_embedded_identity: bool = True,
) -> TacticalGridShadowEvaluationV1:
    """Deserialize JSON or dictionary into TacticalGridShadowEvaluationV1."""
    if isinstance(raw_json_or_dict, str):
        data = cast(dict[str, Any], json.loads(raw_json_or_dict))
    else:
        data = dict(raw_json_or_dict)

    if require_embedded_identity and ("evaluation_id" not in data or not data["evaluation_id"]):
        raise TacticalGridShadowEvaluationIdentityError("missing mandatory embedded evaluation_id")

    levels = tuple(float(x) for x in data.get("grid_levels", []))
    ambiguity_events = tuple(dict(e) for e in data.get("ambiguity_events", []))

    eval_obj = TacticalGridShadowEvaluationV1(
        evaluation_schema_version=str(data["evaluation_schema_version"]),
        evaluation_id=str(data["evaluation_id"]),
        evaluation_profile_version=str(data["evaluation_profile_version"]),
        grid_path_model_version=str(data["grid_path_model_version"]),
        grid_accounting_version=str(data["grid_accounting_version"]),
        feature_evidence_id=str(data["feature_evidence_id"]),
        symbol=str(data["symbol"]),
        decision_time_ms=int(data["decision_time_ms"]),
        snapshot_hash=str(data["snapshot_hash"]),
        policy_version=str(data["policy_version"]),
        config_hash=str(data["config_hash"]),
        semantic_identity=dict(data["semantic_identity"]),
        grid_decision=str(data["grid_decision"]),
        frozen_grid_plan=dict(data["frozen_grid_plan"]),
        reference_price=float(data["reference_price"]) if data.get("reference_price") is not None else None,
        anchor_index=int(data["anchor_index"]) if data.get("anchor_index") is not None else None,
        grid_levels=levels,
        evaluation_start_ms=int(data["evaluation_start_ms"]),
        evaluation_end_ms=int(data["evaluation_end_ms"]),
        terminal_time_ms=int(data["terminal_time_ms"]) if data.get("terminal_time_ms") is not None else None,
        terminal_reason=str(data["terminal_reason"]) if data.get("terminal_reason") is not None else None,
        eligibility_status=str(data["eligibility_status"]),
        market_path_coverage=str(data["market_path_coverage"]),
        funding_coverage=str(data["funding_coverage"]),
        future_assessment_diagnostic_status=str(data["future_assessment_diagnostic_status"]),
        ambiguity_events=ambiguity_events,
        paired_cycle_count=int(data["paired_cycle_count"]),
        paired_gross_pnl=float(data["paired_gross_pnl"]),
        paired_maker_fees=float(data["paired_maker_fees"]),
        paired_net_pnl=float(data["paired_net_pnl"]),
        terminal_unpaired_gross_pnl=float(data["terminal_unpaired_gross_pnl"]),
        terminal_taker_fee=float(data["terminal_taker_fee"]),
        terminal_slippage_cost=float(data["terminal_slippage_cost"]),
        gross_pnl_before_costs=float(data["gross_pnl_before_costs"]),
        total_trading_fees=float(data["total_trading_fees"]),
        total_slippage_cost=float(data["total_slippage_cost"]),
        funding_pnl=float(data["funding_pnl"]) if data.get("funding_pnl") is not None else None,
        net_pnl_after_fees_slippage=float(data["net_pnl_after_fees_slippage"]),
        net_pnl_after_funding=float(data["net_pnl_after_funding"]) if data.get("net_pnl_after_funding") is not None else None,
        max_abs_inventory_notional=float(data["max_abs_inventory_notional"]),
        mean_abs_inventory_notional_time_weighted=float(data["mean_abs_inventory_notional_time_weighted"]),
        max_open_lot_count=int(data["max_open_lot_count"]),
        long_inventory_peak=float(data["long_inventory_peak"]),
        short_inventory_peak=float(data["short_inventory_peak"]),
        peak_capital_utilization=float(data["peak_capital_utilization"]),
        mean_capital_utilization=float(data["mean_capital_utilization"]),
        min_marked_equity=float(data["min_marked_equity"]),
        maximum_underwater=float(data["maximum_underwater"]),
        max_drawdown_from_prior_peak=float(data["max_drawdown_from_prior_peak"]),
        lower_boundary_breached=bool(data["lower_boundary_breached"]),
        upper_boundary_breached=bool(data["upper_boundary_breached"]),
        first_lower_boundary_breach_ms=int(data["first_lower_boundary_breach_ms"]) if data.get("first_lower_boundary_breach_ms") is not None else None,
        first_upper_boundary_breach_ms=int(data["first_upper_boundary_breach_ms"]) if data.get("first_upper_boundary_breach_ms") is not None else None,
        boundary_breach_count=int(data["boundary_breach_count"]),
        grid_shift_count=int(data["grid_shift_count"]) if data.get("grid_shift_count") is not None else None,
        grid_shift_frequency_per_day=float(data["grid_shift_frequency_per_day"]) if data.get("grid_shift_frequency_per_day") is not None else None,
        first_grid_shift_ms=int(data["first_grid_shift_ms"]) if data.get("first_grid_shift_ms") is not None else None,
        first_policy_pause_ms=int(data["first_policy_pause_ms"]) if data.get("first_policy_pause_ms") is not None else None,
        first_technical_trend_transition_ms=int(data["first_technical_trend_transition_ms"]) if data.get("first_technical_trend_transition_ms") is not None else None,
        net_equity_at_first_trend_transition=float(data["net_equity_at_first_trend_transition"]) if data.get("net_equity_at_first_trend_transition") is not None else None,
        post_transition_net_pnl_delta=float(data["post_transition_net_pnl_delta"]) if data.get("post_transition_net_pnl_delta") is not None else None,
        trend_transition_loss=float(data["trend_transition_loss"]) if data.get("trend_transition_loss") is not None else None,
        persisted_at_ms=int(data["persisted_at_ms"]) if data.get("persisted_at_ms") is not None else None,
    )

    if verify_identity:
        validate_tactical_grid_shadow_evaluation(eval_obj)
    return eval_obj
