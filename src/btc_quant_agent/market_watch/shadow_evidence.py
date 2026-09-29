from __future__ import annotations

import hashlib
import json
import logging
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, cast

from btc_quant_agent.domain import Candle

from .domain import (
    DIRECTIONAL_OUTCOME_PROFILE_VERSION,
    FUNDING_ACCOUNTING_VERSION,
    MARKET_WATCH_EVIDENCE_VERSION,
    TACTICAL_COHORT_SUMMARY_VERSION,
    TACTICAL_SHADOW_EVALUATION_SCHEMA_VERSION,
    validate_time_coverage,
)
from .evidence import (
    TacticalFeatureEvidenceV2,
    validate_tactical_feature_evidence,
    verify_tactical_evidence_identity,
)

logger = logging.getLogger(__name__)

# ==============================================================================
# Exceptions
# ==============================================================================


class TacticalShadowEvaluationError(Exception):
    """Base exception for tactical shadow evaluation failures."""


class TacticalShadowEvaluationIdentityError(TacticalShadowEvaluationError):
    """Raised when evaluation_id format is invalid or recomputed ID does not match stored ID."""


class TacticalShadowEvaluationConflictError(TacticalShadowEvaluationError):
    """Raised when conflicting evaluation content is presented for the same natural key."""


class TacticalShadowEvaluationValidationError(TacticalShadowEvaluationError):
    """Raised when evaluation content validation fails (e.g. non-finite numbers, missing required fields)."""


class TacticalShadowAttributionConflictError(TacticalShadowEvaluationConflictError):
    """Raised when shadow record fields conflict with authoritative linked FeatureEvidenceV2."""


class TacticalShadowProfileConflictError(TacticalShadowEvaluationError):
    """Raised when shadow evaluation profile or horizon attributes conflict with frozen authority."""


# ==============================================================================
# Enums and Taxonomy
# ==============================================================================


class FundingStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    COMPLETE = "COMPLETE"
    AMBIGUOUS_FILL_BOUNDARY = "AMBIGUOUS_FILL_BOUNDARY"
    INCOMPLETE_HISTORY = "INCOMPLETE_HISTORY"
    INCOMPLETE_MARK_PRICE = "INCOMPLETE_MARK_PRICE"
    FETCH_ERROR = "FETCH_ERROR"


class EvaluationTerminalStatus(StrEnum):
    FILLED = "FILLED"
    NO_FILL = "NO_FILL"
    PENDING_DATA_GAP = "PENDING_DATA_GAP"
    INELIGIBLE_DATA_GAP = "INELIGIBLE_DATA_GAP"


# ==============================================================================
# Playbook Profiles & Rule Score Buckets
# ==============================================================================

PLAYBOOK_EVALUATION_PROFILES: dict[str, dict[str, int]] = {
    "TREND_PULLBACK": {"horizon_hours": 12, "horizon_bars": 48, "horizon_ms": 12 * 3600 * 1000},
    "BREAKOUT_RETEST": {"horizon_hours": 12, "horizon_bars": 48, "horizon_ms": 12 * 3600 * 1000},
    "FAILED_BREAKOUT": {"horizon_hours": 8, "horizon_bars": 32, "horizon_ms": 8 * 3600 * 1000},
    "FAILED_BREAKDOWN": {"horizon_hours": 8, "horizon_bars": 32, "horizon_ms": 8 * 3600 * 1000},
    "VOLATILITY_EXPANSION": {"horizon_hours": 8, "horizon_bars": 32, "horizon_ms": 8 * 3600 * 1000},
}

DEFAULT_PLAYBOOK_PROFILE: dict[str, int] = {
    "horizon_hours": 12,
    "horizon_bars": 48,
    "horizon_ms": 12 * 3600 * 1000,
}


def get_playbook_evaluation_profile(playbook: str) -> dict[str, int]:
    """Retrieve the frozen evaluation profile for a directional playbook."""
    pb_clean = str(playbook).strip().upper()
    if pb_clean.startswith("PLAYBOOKTYPE."):
        pb_clean = pb_clean.split(".", 1)[1]
    return dict(PLAYBOOK_EVALUATION_PROFILES.get(pb_clean, DEFAULT_PLAYBOOK_PROFILE))


RULE_SCORE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0–39.999", 0.0, 40.0),
    ("40–59.999", 40.0, 60.0),
    ("60–74.999", 60.0, 75.0),
    ("75–89.999", 75.0, 90.0),
    ("90–100", 90.0, 100.0001),
)


def classify_rule_score_bucket(score: float | None) -> str:
    """Classify a continuous Rule Score into frozen descriptive buckets (RULE_SCORE_BUCKETS_V1)."""
    if score is None:
        return "UNKNOWN"
    val = float(score)
    for label, low, high in RULE_SCORE_BUCKETS:
        if low <= val < high:
            return label
    if val >= 100.0:
        return "90–100"
    if val < 0.0:
        return "0–39.999"
    return "UNKNOWN"


def sample_size_label(n: int) -> str:
    """Classify sample size display label according to frozen Section 36 rules."""
    if n < 10:
        return "VERY_LOW_SAMPLE"
    if n < 30:
        return "LOW_SAMPLE"
    return "OBSERVED_SAMPLE"


# ==============================================================================
# Immutable Sub-Components
# ==============================================================================


@dataclass(frozen=True)
class FundingSettlementEvidence:
    funding_time_ms: int
    funding_rate: float
    mark_price: float | None
    funding_cash: float | None
    funding_r: float | None
    is_settlement_open: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "funding_time_ms": self.funding_time_ms,
            "funding_rate": self.funding_rate,
            "mark_price": self.mark_price,
            "funding_cash": self.funding_cash,
            "funding_r": self.funding_r,
            "is_settlement_open": self.is_settlement_open,
            "status": self.status,
        }


@dataclass(frozen=True)
class FundingAccountingEvidence:
    accounting_version: str = FUNDING_ACCOUNTING_VERSION
    funding_status: str = FundingStatus.NOT_APPLICABLE.value
    settlements_count: int = 0
    settlements: tuple[FundingSettlementEvidence, ...] = ()
    funding_pnl_r: float | None = None
    funding_cash_total: float | None = None
    initial_risk: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accounting_version": self.accounting_version,
            "funding_status": self.funding_status,
            "settlements_count": self.settlements_count,
            "settlements": [s.to_dict() for s in self.settlements],
            "funding_pnl_r": self.funding_pnl_r,
            "funding_cash_total": self.funding_cash_total,
            "initial_risk": self.initial_risk,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class OutcomeCheckpointEvidence:
    checkpoint_horizon_hours: int
    checkpoint_horizon_ms: int
    target_time_ms: int
    status: str
    mark_price: float | None = None
    mark_to_market_gross_r: float | None = None
    mfe_r_to_checkpoint: float | None = None
    mae_r_to_checkpoint: float | None = None
    barrier_status: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_horizon_hours": self.checkpoint_horizon_hours,
            "checkpoint_horizon_ms": self.checkpoint_horizon_ms,
            "target_time_ms": self.target_time_ms,
            "status": self.status,
            "mark_price": self.mark_price,
            "mark_to_market_gross_r": self.mark_to_market_gross_r,
            "mfe_r_to_checkpoint": self.mfe_r_to_checkpoint,
            "mae_r_to_checkpoint": self.mae_r_to_checkpoint,
            "barrier_status": self.barrier_status,
        }


@dataclass(frozen=True)
class OutcomeCoverageEvidence:
    coverage_status: str
    entry_coverage_complete: bool
    outcome_coverage_complete: bool
    start_coverage_ms: int
    end_coverage_ms: int
    expected_15m_bars: int = 0
    observed_15m_bars: int = 0
    expected_1m_bars: int = 0
    observed_1m_bars: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_status": self.coverage_status,
            "entry_coverage_complete": self.entry_coverage_complete,
            "outcome_coverage_complete": self.outcome_coverage_complete,
            "start_coverage_ms": self.start_coverage_ms,
            "end_coverage_ms": self.end_coverage_ms,
            "expected_15m_bars": self.expected_15m_bars,
            "observed_15m_bars": self.observed_15m_bars,
            "expected_1m_bars": self.expected_1m_bars,
            "observed_1m_bars": self.observed_1m_bars,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AttributionProjectionEvidence:
    selected_playbook: str
    direction: str
    regime_1h: str
    regime_4h: str
    entry_quality: str
    derivatives_regime: str
    benchmark_context: str
    reference_universe_status: str
    rule_score: float
    rule_score_bucket: str
    rule_score_components: tuple[tuple[str, float], ...] = ()
    exhaustion_state: str = "NEUTRAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_playbook": self.selected_playbook,
            "direction": self.direction,
            "regime_1h": self.regime_1h,
            "regime_4h": self.regime_4h,
            "entry_quality": self.entry_quality,
            "derivatives_regime": self.derivatives_regime,
            "benchmark_context": self.benchmark_context,
            "reference_universe_status": self.reference_universe_status,
            "rule_score": self.rule_score,
            "rule_score_bucket": self.rule_score_bucket,
            "rule_score_components": [[k, v] for k, v in self.rule_score_components],
            "exhaustion_state": self.exhaustion_state,
        }


# ==============================================================================
# Top-Level Immutable TacticalShadowEvaluationV2
# ==============================================================================


@dataclass(frozen=True)
class TacticalShadowEvaluationV2:
    evaluation_schema_version: str
    evaluation_id: str

    feature_evidence_id: str
    shadow_record_id: int

    symbol: str
    signal_identity: str
    setup_key: str

    playbook: str
    direction: str

    signal_time_ms: int

    entry_window_start_ms: int
    entry_window_end_ms: int

    fill_status: str
    fill_time_ms: int | None
    fill_price: float | None

    evaluation_profile_version: str
    evaluation_horizon_bars: int
    evaluation_horizon_ms: int

    evaluation_start_ms: int | None
    evaluation_end_ms: int | None

    terminal_status: str
    terminal_reason: str | None

    exit_time_ms: int | None
    exit_price: float | None

    tp1_hit: bool
    tp2_excursion_hit: bool
    sl_hit: bool

    time_to_fill_ms: int | None
    time_from_fill_to_terminal_ms: int | None

    mfe_r: float | None
    mae_r: float | None

    price_gross_r: float | None
    execution_cost_r: float | None
    net_r_ex_funding: float | None

    funding_accounting: FundingAccountingEvidence

    net_r_after_funding: float | None

    coverage: OutcomeCoverageEvidence

    path_resolution: str
    execution_path_model: str

    outcome_checkpoints: tuple[OutcomeCheckpointEvidence, ...] = ()

    attribution: AttributionProjectionEvidence | None = None

    fill_interval_start_ms: int | None = None
    fill_interval_end_ms: int | None = None
    fill_time_resolution: str | None = None

    feature_evidence_hash: str = ""
    policy_version: str = ""
    config_hash: str = ""
    forward_evidence_version: str = MARKET_WATCH_EVIDENCE_VERSION

    persisted_at_ms: int | None = None

    def to_canonical_payload(self) -> dict[str, Any]:
        """Produce the deterministic canonical dictionary excluding evaluation_id and persisted_at_ms."""
        return {
            "attribution": self.attribution.to_dict() if self.attribution is not None else None,
            "config_hash": self.config_hash,
            "coverage": self.coverage.to_dict(),
            "direction": self.direction,
            "entry_window_end_ms": self.entry_window_end_ms,
            "entry_window_start_ms": self.entry_window_start_ms,
            "evaluation_end_ms": self.evaluation_end_ms,
            "evaluation_horizon_bars": self.evaluation_horizon_bars,
            "evaluation_horizon_ms": self.evaluation_horizon_ms,
            "evaluation_profile_version": self.evaluation_profile_version,
            "evaluation_schema_version": self.evaluation_schema_version,
            "evaluation_start_ms": self.evaluation_start_ms,
            "execution_cost_r": self.execution_cost_r,
            "execution_path_model": self.execution_path_model,
            "exit_price": self.exit_price,
            "exit_time_ms": self.exit_time_ms,
            "feature_evidence_hash": self.feature_evidence_hash,
            "feature_evidence_id": self.feature_evidence_id,
            "fill_interval_end_ms": self.fill_interval_end_ms,
            "fill_interval_start_ms": self.fill_interval_start_ms,
            "fill_price": self.fill_price,
            "fill_status": self.fill_status,
            "fill_time_ms": self.fill_time_ms,
            "fill_time_resolution": self.fill_time_resolution,
            "forward_evidence_version": self.forward_evidence_version,
            "funding_accounting": self.funding_accounting.to_dict(),
            "mae_r": self.mae_r,
            "mfe_r": self.mfe_r,
            "net_r_after_funding": self.net_r_after_funding,
            "net_r_ex_funding": self.net_r_ex_funding,
            "outcome_checkpoints": [cp.to_dict() for cp in self.outcome_checkpoints],
            "path_resolution": self.path_resolution,
            "playbook": self.playbook,
            "policy_version": self.policy_version,
            "price_gross_r": self.price_gross_r,
            "setup_key": self.setup_key,
            "shadow_record_id": self.shadow_record_id,
            "signal_identity": self.signal_identity,
            "signal_time_ms": self.signal_time_ms,
            "sl_hit": self.sl_hit,
            "symbol": self.symbol,
            "terminal_reason": self.terminal_reason,
            "terminal_status": self.terminal_status,
            "time_from_fill_to_terminal_ms": self.time_from_fill_to_terminal_ms,
            "time_to_fill_ms": self.time_to_fill_ms,
            "tp1_hit": self.tp1_hit,
            "tp2_excursion_hit": self.tp2_excursion_hit,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert full evaluation to dictionary including evaluation_id and persisted_at_ms."""
        res = self.to_canonical_payload()
        res["evaluation_id"] = self.evaluation_id
        res["persisted_at_ms"] = self.persisted_at_ms
        return res

    def recompute_evaluation_id(self) -> str:
        """Compute the content-addressed SHA-256 evaluation identity."""
        return compute_evaluation_id(self)

    def as_canonical_json(self) -> str:
        """Dump full evaluation to canonical JSON."""
        return canonical_shadow_evaluation_json(self)


# ==============================================================================
# Canonical JSON & ID Utilities
# ==============================================================================


def canonical_shadow_evaluation_dump(payload: dict[str, Any]) -> str:
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
        raise TacticalShadowEvaluationValidationError(
            f"Invalid non-finite number in shadow evaluation payload: {e}"
        ) from e


def compute_evaluation_id(payload_or_eval: dict[str, Any] | TacticalShadowEvaluationV2) -> str:
    """Compute the immutable 64-character SHA-256 evaluation identity."""
    if isinstance(payload_or_eval, TacticalShadowEvaluationV2):
        payload = payload_or_eval.to_canonical_payload()
    else:
        payload = dict(payload_or_eval)
        payload.pop("evaluation_id", None)
        payload.pop("persisted_at_ms", None)
    raw = canonical_shadow_evaluation_dump(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_shadow_evaluation_json(evaluation: TacticalShadowEvaluationV2) -> str:
    """Serialize full evaluation to canonical JSON including evaluation_id and persisted_at_ms."""
    payload = evaluation.to_canonical_payload()
    payload["evaluation_id"] = evaluation.evaluation_id
    payload["persisted_at_ms"] = evaluation.persisted_at_ms
    return canonical_shadow_evaluation_dump(payload)


def verify_shadow_evaluation_identity(evaluation: TacticalShadowEvaluationV2) -> None:
    """Verify that evaluation_id matches content-addressed SHA-256 and conforms to format."""
    import re
    if not re.match(r"^[0-9a-f]{64}$", evaluation.evaluation_id):
        raise TacticalShadowEvaluationIdentityError(
            f"Invalid evaluation_id format (must be 64-char lowercase hex): {evaluation.evaluation_id}"
        )
    expected = evaluation.recompute_evaluation_id()
    if evaluation.evaluation_id != expected:
        raise TacticalShadowEvaluationIdentityError(
            f"evaluation_id mismatch: stored {evaluation.evaluation_id} != computed {expected}"
        )


def validate_tactical_shadow_evaluation(evaluation: TacticalShadowEvaluationV2) -> None:
    """Validate all fields, non-finite values, and identity of a TacticalShadowEvaluationV2."""
    if evaluation.evaluation_schema_version != TACTICAL_SHADOW_EVALUATION_SCHEMA_VERSION:
        raise TacticalShadowEvaluationValidationError(
            f"Invalid evaluation schema version: {evaluation.evaluation_schema_version}"
        )
    if not evaluation.feature_evidence_id:
        raise TacticalShadowEvaluationValidationError("feature_evidence_id is mandatory")
    if not evaluation.symbol:
        raise TacticalShadowEvaluationValidationError("symbol is mandatory")
    if evaluation.direction not in ("LONG", "SHORT"):
        raise TacticalShadowEvaluationValidationError(f"Invalid direction: {evaluation.direction}")
    if evaluation.forward_evidence_version != MARKET_WATCH_EVIDENCE_VERSION:
        raise TacticalShadowEvaluationValidationError(
            f"Invalid forward evidence version: {evaluation.forward_evidence_version}"
        )
    if evaluation.funding_accounting.accounting_version != FUNDING_ACCOUNTING_VERSION:
        raise TacticalShadowEvaluationValidationError(
            f"Invalid funding accounting version: {evaluation.funding_accounting.accounting_version}"
        )

    # Check profile version & horizon mapping
    if evaluation.evaluation_profile_version != DIRECTIONAL_OUTCOME_PROFILE_VERSION:
        raise TacticalShadowEvaluationValidationError(
            f"Invalid evaluation profile version: {evaluation.evaluation_profile_version}"
        )
    if evaluation.evaluation_horizon_bars <= 0:
        raise TacticalShadowEvaluationValidationError(
            f"evaluation_horizon_bars must be positive, got: {evaluation.evaluation_horizon_bars}"
        )
    if evaluation.evaluation_horizon_ms != evaluation.evaluation_horizon_bars * 900_000:
        raise TacticalShadowEvaluationValidationError(
            f"Horizon invariant violated: {evaluation.evaluation_horizon_ms} != {evaluation.evaluation_horizon_bars} * 900_000"
        )
    prof = get_playbook_evaluation_profile(evaluation.playbook)
    if evaluation.evaluation_horizon_bars != prof["horizon_bars"]:
        raise TacticalShadowEvaluationValidationError(
            f"evaluation_horizon_bars ({evaluation.evaluation_horizon_bars}) does not match playbook "
            f"{evaluation.playbook} profile ({prof['horizon_bars']})"
        )
    if evaluation.evaluation_horizon_ms != prof["horizon_ms"]:
        raise TacticalShadowEvaluationValidationError(
            f"evaluation_horizon_ms ({evaluation.evaluation_horizon_ms}) does not match playbook "
            f"{evaluation.playbook} profile ({prof['horizon_ms']})"
        )

    # Check non-finite numbers in numeric attributes
    for attr in (
        "fill_price", "exit_price", "mfe_r", "mae_r", "price_gross_r",
        "execution_cost_r", "net_r_ex_funding", "net_r_after_funding"
    ):
        val = getattr(evaluation, attr)
        if val is not None and (math.isnan(val) or math.isinf(val)):
            raise TacticalShadowEvaluationValidationError(f"Non-finite float in {attr}: {val}")

    # Temporal ordering
    if evaluation.signal_time_ms > evaluation.entry_window_start_ms or evaluation.entry_window_start_ms > evaluation.entry_window_end_ms:
        raise TacticalShadowEvaluationValidationError(
            f"Invalid entry window temporal ordering: signal={evaluation.signal_time_ms}, "
            f"start={evaluation.entry_window_start_ms}, end={evaluation.entry_window_end_ms}"
        )

    # Terminal status semantics
    if evaluation.terminal_status == EvaluationTerminalStatus.NO_FILL.value:
        if evaluation.fill_status != "NO_FILL":
            raise TacticalShadowEvaluationValidationError(
                f"NO_FILL terminal_status requires fill_status='NO_FILL', got {evaluation.fill_status}"
            )
        if evaluation.terminal_reason != "NO_FILL":
            raise TacticalShadowEvaluationValidationError(
                f"NO_FILL terminal_status requires terminal_reason='NO_FILL', got {evaluation.terminal_reason}"
            )
        if evaluation.fill_time_ms is not None or evaluation.fill_price is not None:
            raise TacticalShadowEvaluationValidationError(
                "NO_FILL evaluation must have fill_time_ms and fill_price set to None"
            )
        if (
            evaluation.price_gross_r is not None
            or evaluation.execution_cost_r is not None
            or evaluation.net_r_ex_funding is not None
            or evaluation.net_r_after_funding is not None
        ):
            raise TacticalShadowEvaluationValidationError(
                "NO_FILL evaluation must have all R metrics set to None"
            )
        if evaluation.funding_accounting.funding_status != FundingStatus.NOT_APPLICABLE.value:
            raise TacticalShadowEvaluationValidationError(
                f"NO_FILL evaluation requires funding_status='NOT_APPLICABLE', got {evaluation.funding_accounting.funding_status}"
            )
        if evaluation.fill_interval_start_ms is not None or evaluation.fill_interval_end_ms is not None:
            raise TacticalShadowEvaluationValidationError(
                "NO_FILL evaluation must not have fill_interval bounds"
            )

    elif evaluation.terminal_status == EvaluationTerminalStatus.FILLED.value:
        if evaluation.fill_status != "FILLED":
            raise TacticalShadowEvaluationValidationError(
                f"FILLED terminal_status requires fill_status='FILLED', got {evaluation.fill_status}"
            )
        if evaluation.fill_price is None or evaluation.fill_price <= 0.0:
            raise TacticalShadowEvaluationValidationError(
                f"FILLED evaluation requires positive fill_price, got {evaluation.fill_price}"
            )
        if evaluation.fill_time_ms is None:
            raise TacticalShadowEvaluationValidationError("FILLED evaluation requires fill_time_ms")
        if evaluation.fill_interval_start_ms is None or evaluation.fill_interval_end_ms is None:
            raise TacticalShadowEvaluationValidationError("FILLED evaluation requires fill_interval bounds")
        if not (evaluation.fill_interval_start_ms <= evaluation.fill_time_ms <= evaluation.fill_interval_end_ms):
            raise TacticalShadowEvaluationValidationError(
                f"fill_time_ms {evaluation.fill_time_ms} outside fill interval [{evaluation.fill_interval_start_ms}, {evaluation.fill_interval_end_ms}]"
            )
        if evaluation.fill_interval_start_ms < evaluation.signal_time_ms:
            raise TacticalShadowEvaluationValidationError(
                f"Fill interval starts before signal_time: {evaluation.fill_interval_start_ms} < {evaluation.signal_time_ms}"
            )
        if evaluation.terminal_reason not in ("TP1", "STOP", "TIMEOUT"):
            raise TacticalShadowEvaluationValidationError(
                f"FILLED evaluation terminal_reason must be TP1, STOP, or TIMEOUT, got: {evaluation.terminal_reason}"
            )
        if evaluation.exit_time_ms is None:
            raise TacticalShadowEvaluationValidationError("FILLED evaluation requires exit_time_ms")
        if evaluation.exit_price is None or evaluation.exit_price <= 0.0:
            raise TacticalShadowEvaluationValidationError(
                f"FILLED evaluation requires positive exit_price, got {evaluation.exit_price}"
            )
        if evaluation.exit_time_ms < evaluation.fill_interval_end_ms:
            raise TacticalShadowEvaluationValidationError(
                f"Exit time {evaluation.exit_time_ms} is before fill_interval_end_ms {evaluation.fill_interval_end_ms}"
            )

        # Planned horizon
        if evaluation.evaluation_start_ms is None or evaluation.evaluation_start_ms != evaluation.fill_time_ms:
            raise TacticalShadowEvaluationValidationError(
                f"evaluation_start_ms ({evaluation.evaluation_start_ms}) must equal fill_time_ms ({evaluation.fill_time_ms})"
            )
        if evaluation.evaluation_end_ms is None:
            raise TacticalShadowEvaluationValidationError("evaluation_end_ms is required for FILLED evaluation")
        expected_eval_end = evaluation.evaluation_start_ms + evaluation.evaluation_horizon_ms
        if evaluation.evaluation_end_ms != expected_eval_end:
            raise TacticalShadowEvaluationValidationError(
                f"evaluation_end_ms ({evaluation.evaluation_end_ms}) != evaluation_start_ms + horizon_ms ({expected_eval_end})"
            )

        # Planned horizon vs early terminal & TIMEOUT
        if evaluation.terminal_reason == "TIMEOUT":
            if abs(evaluation.exit_time_ms - evaluation.evaluation_end_ms) > 900_000:
                raise TacticalShadowEvaluationValidationError(
                    f"TIMEOUT exit_time_ms ({evaluation.exit_time_ms}) diverges from evaluation_end_ms ({evaluation.evaluation_end_ms})"
                )
            if evaluation.tp1_hit or evaluation.sl_hit:
                raise TacticalShadowEvaluationValidationError("TIMEOUT terminal cannot have tp1_hit or sl_hit")
        elif evaluation.terminal_reason == "TP1":
            if not evaluation.tp1_hit or evaluation.sl_hit:
                raise TacticalShadowEvaluationValidationError("TP1 terminal requires tp1_hit=True and sl_hit=False")
            if evaluation.exit_time_ms > evaluation.evaluation_end_ms + 900_000:
                raise TacticalShadowEvaluationValidationError("TP1 exit cannot occur after planned evaluation end")
        elif evaluation.terminal_reason == "STOP":
            if not evaluation.sl_hit or evaluation.tp1_hit:
                raise TacticalShadowEvaluationValidationError("STOP terminal requires sl_hit=True and tp1_hit=False")
            if evaluation.exit_time_ms > evaluation.evaluation_end_ms + 900_000:
                raise TacticalShadowEvaluationValidationError("STOP exit cannot occur after planned evaluation end")

        # Net R arithmetic
        if evaluation.price_gross_r is None or evaluation.execution_cost_r is None or evaluation.net_r_ex_funding is None:
            raise TacticalShadowEvaluationValidationError("Missing R-multiple calculations on FILLED evaluation")
        expected_net_ex = evaluation.price_gross_r - evaluation.execution_cost_r
        if not math.isclose(evaluation.net_r_ex_funding, expected_net_ex, rel_tol=1e-5, abs_tol=1e-5):
            raise TacticalShadowEvaluationValidationError(
                f"Net R ex-funding mismatch: stored {evaluation.net_r_ex_funding} != expected {expected_net_ex}"
            )
        f_st = evaluation.funding_accounting.funding_status
        if f_st == FundingStatus.COMPLETE.value:
            if evaluation.funding_accounting.funding_pnl_r is None:
                raise TacticalShadowEvaluationValidationError("COMPLETE funding requires funding_pnl_r")
            if evaluation.net_r_after_funding is None:
                raise TacticalShadowEvaluationValidationError("COMPLETE funding requires net_r_after_funding")
            expected_net_after = expected_net_ex + evaluation.funding_accounting.funding_pnl_r
            if not math.isclose(evaluation.net_r_after_funding, expected_net_after, rel_tol=1e-5, abs_tol=1e-5):
                raise TacticalShadowEvaluationValidationError(
                    f"Net R after funding mismatch: stored {evaluation.net_r_after_funding} != expected {expected_net_after}"
                )
        else:
            if evaluation.net_r_after_funding is not None:
                raise TacticalShadowEvaluationValidationError(
                    f"net_r_after_funding must be None when funding_status is {f_st}"
                )

    else:
        raise TacticalShadowEvaluationValidationError(
            f"Invalid terminal_status: {evaluation.terminal_status}. Only FILLED or NO_FILL allowed as sealed evaluation."
        )

    # Checkpoints schema
    if len(evaluation.outcome_checkpoints) != 4:
        raise TacticalShadowEvaluationValidationError(
            f"outcome_checkpoints must contain exactly 4 checkpoints, got {len(evaluation.outcome_checkpoints)}"
        )
    expected_hours = (4, 8, 12, 24)
    for idx, cp in enumerate(evaluation.outcome_checkpoints):
        if cp.checkpoint_horizon_hours != expected_hours[idx]:
            raise TacticalShadowEvaluationValidationError(
                f"Checkpoint {idx} has invalid horizon hours: {cp.checkpoint_horizon_hours} != {expected_hours[idx]}"
            )

    # Attribution presence
    if evaluation.attribution is None:
        raise TacticalShadowEvaluationValidationError("attribution projection is mandatory")

    verify_shadow_evaluation_identity(evaluation)


# ==============================================================================
# Attribution Extraction & Cross-Check (Section 9 & 30)
# ==============================================================================


def extract_attribution_projection(feature_evidence: TacticalFeatureEvidenceV2) -> AttributionProjectionEvidence:
    """Extract a lightweight, immutable attribution projection from authoritative FeatureEvidenceV2."""
    rule_score_comps: tuple[tuple[str, float], ...] = ()
    if feature_evidence.rule_score_breakdown is not None:
        b = feature_evidence.rule_score_breakdown
        rule_score_comps = (
            ("adx_score", b.adx_score),
            ("ema_slope_score", b.ema_slope_score),
            ("trend_quality", b.trend_quality),
            ("structure_quality", b.structure_quality),
            ("entry_quality_score", b.entry_quality_score),
            ("derivatives_confirmation_score", b.derivatives_confirmation_score),
            ("volume_z_score", b.volume_z_score),
            ("taker_score", b.taker_score),
            ("relative_strength_score", b.relative_strength_score),
            ("net_rr_score", b.net_rr_score),
            ("total_penalty", b.total_penalty),
        )

    # Derive exhaustion state if available
    exhaustion_state = "NEUTRAL"
    if feature_evidence.exhaustion:
        exhaustion_state = str(getattr(feature_evidence.exhaustion, "state", getattr(feature_evidence.exhaustion, "exhaustion_state", "NEUTRAL")))

    score_val = feature_evidence.rule_score
    bucket = classify_rule_score_bucket(score_val)

    ms_feat = feature_evidence.market_snapshot_features
    regime_1h = ms_feat.tf_1h.regime if ms_feat and ms_feat.tf_1h else "UNKNOWN"
    regime_4h = ms_feat.tf_4h.regime if ms_feat and ms_feat.tf_4h else "UNKNOWN"
    entry_qual = feature_evidence.entry_quality or "UNKNOWN"
    deriv_regime = (
        ms_feat.derivatives.derivatives_regime
        if ms_feat and ms_feat.derivatives
        else "UNKNOWN"
    )
    bench_ctx = ms_feat.benchmark_context if ms_feat else "UNKNOWN"
    ref_status = (
        getattr(feature_evidence.reference_universe_evidence, "status", getattr(feature_evidence.reference_universe_evidence, "reference_universe_status", "UNKNOWN"))
        if feature_evidence.reference_universe_evidence
        else "UNKNOWN"
    )
    direction = (
        feature_evidence.decision_trace.final_directional_decision
        if feature_evidence.decision_trace
        else "UNKNOWN"
    )

    return AttributionProjectionEvidence(
        selected_playbook=str(feature_evidence.selected_playbook or "NO_TRADE"),
        direction=direction,
        regime_1h=regime_1h,
        regime_4h=regime_4h,
        entry_quality=entry_qual,
        derivatives_regime=deriv_regime,
        benchmark_context=bench_ctx,
        reference_universe_status=ref_status,
        rule_score=score_val,
        rule_score_bucket=bucket,
        rule_score_components=rule_score_comps,
        exhaustion_state=exhaustion_state,
    )


def validate_attribution_crosscheck(
    feature_evidence: TacticalFeatureEvidenceV2,
    shadow_record: Mapping[str, Any],
) -> None:
    """Cross-check shadow operational row against authoritative FeatureEvidenceV2. Fail closed on conflict."""
    # 1. Symbol (Section 22, 24)
    sh_sym = str(shadow_record.get("symbol") or "").strip().upper()
    ev_sym = str(feature_evidence.symbol or "").strip().upper()
    if sh_sym != ev_sym:
        raise TacticalShadowAttributionConflictError(
            f"Symbol conflict: shadow={sh_sym} vs feature_evidence={ev_sym}"
        )

    # 2. Signal time / Decision time (Section 22, 24)
    sh_sig_t = int(shadow_record.get("signal_time_ms") or shadow_record.get("timestamp_ms") or 0)
    ev_dec_t = int(feature_evidence.decision_time_ms)
    if sh_sig_t != ev_dec_t:
        raise TacticalShadowAttributionConflictError(
            f"Signal time conflict: shadow={sh_sig_t} vs feature_evidence={ev_dec_t}"
        )

    # 3. Feature evidence ID (Section 22, 24)
    sh_ev_id = str(shadow_record.get("feature_evidence_id") or "").strip()
    ev_id = str(feature_evidence.evidence_id).strip()
    if sh_ev_id != ev_id:
        raise TacticalShadowAttributionConflictError(
            f"Feature evidence ID conflict: shadow={sh_ev_id} vs feature_evidence={ev_id}"
        )

    # 4. Playbook
    sh_setup = str(shadow_record.get("agent_setup") or "").strip().upper()
    if sh_setup.startswith("PLAYBOOKTYPE."):
        sh_setup = sh_setup.split(".", 1)[1]
    ev_pb = str(feature_evidence.selected_playbook or "").strip().upper()
    if ev_pb.startswith("PLAYBOOKTYPE."):
        ev_pb = ev_pb.split(".", 1)[1]
    if sh_setup != ev_pb:
        raise TacticalShadowAttributionConflictError(
            f"Playbook conflict: shadow={sh_setup} vs feature_evidence={ev_pb}"
        )

    # 5. Direction
    sh_dir = str(shadow_record.get("direction") or "").strip().upper()
    ev_dir = (
        str(feature_evidence.decision_trace.final_directional_decision or "").strip().upper()
        if feature_evidence.decision_trace
        else ""
    )
    if sh_dir != ev_dir:
        raise TacticalShadowAttributionConflictError(
            f"Direction conflict: shadow={sh_dir} vs feature_evidence={ev_dir}"
        )

    # 6. Signal Identity
    sh_sig = str(shadow_record.get("signal_identity") or "").strip()
    ev_sig = str(feature_evidence.signal_identity or "").strip()
    if sh_sig != ev_sig:
        raise TacticalShadowAttributionConflictError(
            f"Signal identity conflict: shadow={sh_sig} vs feature_evidence={ev_sig}"
        )

    # 7. Setup Key
    sh_key = str(shadow_record.get("setup_key") or "").strip()
    ev_key = str(feature_evidence.setup_key or "").strip()
    if sh_key != ev_key:
        raise TacticalShadowAttributionConflictError(
            f"Setup key conflict: shadow={sh_key} vs feature_evidence={ev_key}"
        )

    # 8. Snapshot Hash
    sh_snap = str(shadow_record.get("snapshot_hash") or "").strip()
    ev_snap = str(feature_evidence.snapshot_hash or "").strip()
    if sh_snap != ev_snap:
        raise TacticalShadowAttributionConflictError(
            f"Snapshot hash conflict: shadow={sh_snap} vs feature_evidence={ev_snap}"
        )

    # 9. Policy Version
    sh_pol = str(shadow_record.get("policy_version") or "").strip()
    ev_pol = str(feature_evidence.policy_version or "").strip()
    if sh_pol != ev_pol:
        raise TacticalShadowAttributionConflictError(
            f"Policy version conflict: shadow={sh_pol} vs feature_evidence={ev_pol}"
        )

    # 10. Config Hash
    sh_cfg = str(shadow_record.get("config_hash") or "").strip()
    ev_cfg = str(feature_evidence.config_hash or "").strip()
    if sh_cfg != ev_cfg:
        raise TacticalShadowAttributionConflictError(
            f"Config hash conflict: shadow={sh_cfg} vs feature_evidence={ev_cfg}"
        )

    # 11. Risk-plan cross-check (Section 23, 24)
    rp = feature_evidence.directional_risk_plan
    if rp is None:
        raise TacticalShadowAttributionConflictError(
            "FeatureEvidenceV2 is missing directional_risk_plan"
        )

    ev_rp_dir = str(rp.decision).strip().upper()
    if sh_dir != ev_rp_dir:
        raise TacticalShadowAttributionConflictError(
            f"Direction conflict with risk plan: shadow={sh_dir} vs risk_plan={ev_rp_dir}"
        )

    sh_entry_low = float(shadow_record.get("entry_zone_low") or 0.0)
    sh_entry_high = float(shadow_record.get("entry_zone_high") or 0.0)
    sh_sl = float(shadow_record.get("stop_loss") or 0.0)
    sh_tp1 = float(shadow_record.get("tp1") or 0.0)
    sh_tp2 = float(shadow_record.get("tp2") or 0.0)

    if not math.isclose(sh_entry_low, rp.entry_low, rel_tol=1e-12, abs_tol=1e-12):
        raise TacticalShadowAttributionConflictError(
            f"Entry zone low conflict: shadow={sh_entry_low} vs risk_plan={rp.entry_low}"
        )
    if not math.isclose(sh_entry_high, rp.entry_high, rel_tol=1e-12, abs_tol=1e-12):
        raise TacticalShadowAttributionConflictError(
            f"Entry zone high conflict: shadow={sh_entry_high} vs risk_plan={rp.entry_high}"
        )
    if not math.isclose(sh_sl, rp.stop_loss, rel_tol=1e-12, abs_tol=1e-12):
        raise TacticalShadowAttributionConflictError(
            f"Stop loss conflict: shadow={sh_sl} vs risk_plan={rp.stop_loss}"
        )
    if not math.isclose(sh_tp1, rp.take_profit_1, rel_tol=1e-12, abs_tol=1e-12):
        raise TacticalShadowAttributionConflictError(
            f"TP1 conflict: shadow={sh_tp1} vs risk_plan={rp.take_profit_1}"
        )
    if not math.isclose(sh_tp2, rp.take_profit_2, rel_tol=1e-12, abs_tol=1e-12):
        raise TacticalShadowAttributionConflictError(
            f"TP2 conflict: shadow={sh_tp2} vs risk_plan={rp.take_profit_2}"
        )


# ==============================================================================
# Funding Accounting Evaluator (Section 20-25)
# ==============================================================================


def evaluate_funding_accounting(
    direction: str,
    fill_price: float | None,
    stop_loss: float | None,
    fill_time_ms: int | None,
    exit_time_ms: int | None,
    funding_records: Sequence[dict[str, Any]] | None,
    fetch_error: bool = False,
    fill_interval_start_ms: int | None = None,
    fill_interval_end_ms: int | None = None,
) -> FundingAccountingEvidence:
    """Evaluate realized funding settlements causally within the filled holding interval."""
    if fill_time_ms is None or exit_time_ms is None or fill_price is None or stop_loss is None:
        return FundingAccountingEvidence(
            funding_status=FundingStatus.NOT_APPLICABLE.value,
            notes="Position not filled or missing price boundaries",
        )

    initial_risk = abs(fill_price - stop_loss)
    if initial_risk <= 0.0:
        return FundingAccountingEvidence(
            funding_status=FundingStatus.NOT_APPLICABLE.value,
            notes="Zero initial risk distance",
        )

    if fetch_error:
        return FundingAccountingEvidence(
            funding_status=FundingStatus.FETCH_ERROR.value,
            initial_risk=initial_risk,
            notes="Funding history fetch error",
        )

    if funding_records is None:
        return FundingAccountingEvidence(
            funding_status=FundingStatus.INCOMPLETE_HISTORY.value,
            initial_risk=initial_risk,
            notes="Funding records not supplied",
        )

    # Establish authoritative fill uncertainty interval
    start_int = fill_interval_start_ms if fill_interval_start_ms is not None else (fill_time_ms - 60_000)
    end_int = fill_interval_end_ms if fill_interval_end_ms is not None else fill_time_ms

    is_long = direction.upper() == "LONG"
    applicable_settlements: list[FundingSettlementEvidence] = []
    has_ambiguity = False
    has_missing_mark = False

    # Standard Binance funding interval is every 8 hours: 00:00, 08:00, 16:00 UTC
    for rec in funding_records:
        f_time = int(rec["funding_time_ms"])
        f_rate = float(rec["funding_rate"])
        mp_val = rec.get("mark_price")
        mark_price = float(mp_val) if mp_val is not None else None

        # Section 20: Settlement before fill interval: not applicable
        if f_time < start_int:
            continue

        # Section 18: Ambiguous fill boundary: fill ordering vs funding cannot be proven
        if start_int <= f_time <= end_int:
            has_ambiguity = True
            applicable_settlements.append(
                FundingSettlementEvidence(
                    funding_time_ms=f_time,
                    funding_rate=f_rate,
                    mark_price=mark_price,
                    funding_cash=None,
                    funding_r=None,
                    is_settlement_open=False,
                    status=FundingStatus.AMBIGUOUS_FILL_BOUNDARY.value,
                )
            )
            continue

        # Section 19: Proven open across settlement
        if f_time > end_int and f_time <= exit_time_ms:
            if mark_price is None or mark_price <= 0.0:
                has_missing_mark = True
                applicable_settlements.append(
                    FundingSettlementEvidence(
                        funding_time_ms=f_time,
                        funding_rate=f_rate,
                        mark_price=None,
                        funding_cash=None,
                        funding_r=None,
                        is_settlement_open=True,
                        status=FundingStatus.INCOMPLETE_MARK_PRICE.value,
                    )
                )
                continue

            # Normalized 1-unit funding cash formula (Section 22)
            # LONG: funding_cash = -mark_price * funding_rate
            # SHORT: funding_cash = +mark_price * funding_rate
            funding_cash = (-mark_price * f_rate) if is_long else (mark_price * f_rate)
            funding_r = funding_cash / initial_risk

            applicable_settlements.append(
                FundingSettlementEvidence(
                    funding_time_ms=f_time,
                    funding_rate=f_rate,
                    mark_price=mark_price,
                    funding_cash=funding_cash,
                    funding_r=funding_r,
                    is_settlement_open=True,
                    status="SETTLED",
                )
            )

    if has_ambiguity:
        return FundingAccountingEvidence(
            funding_status=FundingStatus.AMBIGUOUS_FILL_BOUNDARY.value,
            settlements_count=len(applicable_settlements),
            settlements=tuple(applicable_settlements),
            funding_pnl_r=None,
            funding_cash_total=None,
            initial_risk=initial_risk,
            notes="Funding settlement timestamp falls within ambiguous fill boundary",
        )

    if has_missing_mark:
        return FundingAccountingEvidence(
            funding_status=FundingStatus.INCOMPLETE_MARK_PRICE.value,
            settlements_count=len(applicable_settlements),
            settlements=tuple(applicable_settlements),
            funding_pnl_r=None,
            funding_cash_total=None,
            initial_risk=initial_risk,
            notes="Applicable funding settlement lacks authoritative mark price",
        )

    # Complete funding accounting
    if not applicable_settlements:
        # No settlements occurred during position hold
        return FundingAccountingEvidence(
            funding_status=FundingStatus.COMPLETE.value,
            settlements_count=0,
            settlements=(),
            funding_pnl_r=0.0,
            funding_cash_total=0.0,
            initial_risk=initial_risk,
            notes="No scheduled funding settlements within filled holding window",
        )

    total_cash = sum(s.funding_cash for s in applicable_settlements if s.funding_cash is not None)
    total_pnl_r = sum(s.funding_r for s in applicable_settlements if s.funding_r is not None)

    return FundingAccountingEvidence(
        funding_status=FundingStatus.COMPLETE.value,
        settlements_count=len(applicable_settlements),
        settlements=tuple(applicable_settlements),
        funding_pnl_r=total_pnl_r,
        funding_cash_total=total_cash,
        initial_risk=initial_risk,
        notes="All applicable funding settlements causally verified and settled",
    )


# Section 22 alias
evaluate_tactical_funding_v1 = evaluate_funding_accounting


# ==============================================================================
# Diagnostic Checkpoints Evaluator (Section 16 & 44)
# ==============================================================================


def compute_diagnostic_checkpoints(
    direction: str,
    fill_price: float | None,
    stop_loss: float | None,
    fill_time_ms: int | None,
    exit_time_ms: int | None,
    terminal_reason: str | None,
    candles_15m: Sequence[Candle],
) -> tuple[OutcomeCheckpointEvidence, ...]:
    """Compute standard 4h, 8h, 12h, 24h descriptive diagnostic checkpoints."""
    standard_horizons_hours = (4, 8, 12, 24)
    checkpoints: list[OutcomeCheckpointEvidence] = []

    if fill_time_ms is None or fill_price is None or stop_loss is None:
        for h in standard_horizons_hours:
            h_ms = h * 3600 * 1000
            checkpoints.append(
                OutcomeCheckpointEvidence(
                    checkpoint_horizon_hours=h,
                    checkpoint_horizon_ms=h_ms,
                    target_time_ms=0,
                    status="NOT_APPLICABLE",
                    barrier_status="NOT_FILLED",
                )
            )
        return tuple(checkpoints)

    initial_risk = abs(fill_price - stop_loss)
    if initial_risk <= 0.0:
        initial_risk = 1.0
    is_long = direction.upper() == "LONG"

    # Section 35: Never inspect post-terminal candles!
    if exit_time_ms is not None:
        eligible_candles = [c for c in candles_15m if isinstance(c, Candle) and c.close_time_ms <= exit_time_ms]
    else:
        eligible_candles = [c for c in candles_15m if isinstance(c, Candle)]

    for h in standard_horizons_hours:
        h_ms = h * 3600 * 1000
        target_t = fill_time_ms + h_ms

        # Section 35: Check if trade terminated before or at checkpoint
        if exit_time_ms is not None and exit_time_ms <= target_t:
            term_status = f"TERMINATED_{terminal_reason or 'EXIT'}"
            checkpoints.append(
                OutcomeCheckpointEvidence(
                    checkpoint_horizon_hours=h,
                    checkpoint_horizon_ms=h_ms,
                    target_time_ms=target_t,
                    status="TERMINATED_BEFORE_CHECKPOINT",
                    mark_price=None,
                    mark_to_market_gross_r=None,
                    mfe_r_to_checkpoint=None,
                    mae_r_to_checkpoint=None,
                    barrier_status=term_status,
                )
            )
            continue

        # Trade active at checkpoint target time: find candles strictly in observation window
        relevant_candles = [
            c for c in eligible_candles
            if c.close_time_ms > fill_time_ms and c.close_time_ms <= target_t
        ]
        relevant_candles.sort(key=lambda c: c.open_time_ms)

        if not relevant_candles:
            checkpoints.append(
                OutcomeCheckpointEvidence(
                    checkpoint_horizon_hours=h,
                    checkpoint_horizon_ms=h_ms,
                    target_time_ms=target_t,
                    status="INSUFFICIENT_COVERAGE",
                    barrier_status="ACTIVE",
                )
            )
            continue

        # Section 34 & 36: Prove complete chronological 15m coverage before marking OBSERVED
        cov = validate_time_coverage(
            relevant_candles,
            start_ms=fill_time_ms,
            end_ms=target_t,
            interval_ms=15 * 60 * 1000,
        )

        if not cov.complete:
            checkpoints.append(
                OutcomeCheckpointEvidence(
                    checkpoint_horizon_hours=h,
                    checkpoint_horizon_ms=h_ms,
                    target_time_ms=target_t,
                    status="INSUFFICIENT_COVERAGE",
                    mark_price=None,
                    mark_to_market_gross_r=None,
                    mfe_r_to_checkpoint=None,
                    mae_r_to_checkpoint=None,
                    barrier_status="ACTIVE",
                )
            )
            continue

        last_cand = relevant_candles[-1]
        mark_p = last_cand.close
        gross_pnl = (mark_p - fill_price) if is_long else (fill_price - mark_p)
        mtm_r = round(gross_pnl / initial_risk, 4)

        if is_long:
            max_h = max(c.high for c in relevant_candles)
            min_l = min(c.low for c in relevant_candles)
            mfe_r = round((max_h - fill_price) / initial_risk, 4)
            mae_r = round((fill_price - min_l) / initial_risk, 4)
        else:
            max_h = max(c.high for c in relevant_candles)
            min_l = min(c.low for c in relevant_candles)
            mfe_r = round((fill_price - min_l) / initial_risk, 4)
            mae_r = round((max_h - fill_price) / initial_risk, 4)

        checkpoints.append(
            OutcomeCheckpointEvidence(
                checkpoint_horizon_hours=h,
                checkpoint_horizon_ms=h_ms,
                target_time_ms=target_t,
                status="OBSERVED",
                mark_price=mark_p,
                mark_to_market_gross_r=mtm_r,
                mfe_r_to_checkpoint=mfe_r,
                mae_r_to_checkpoint=mae_r,
                barrier_status="ACTIVE",
            )
        )

    return tuple(checkpoints)


# ==============================================================================
# Public Funding History Fetcher (Section 20)
# ==============================================================================


def fetch_public_funding_history(
    client: Any,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
) -> list[dict[str, Any]]:
    """Fetch public Binance USDT-M funding rate history using public client or fallback."""
    if hasattr(client, "funding_rate_history"):
        try:
            return cast(list[dict[str, Any]], client.funding_rate_history(symbol, start_time_ms, end_time_ms))
        except Exception as e:
            logger.warning("Error fetching funding history via client: %s", e)
            raise

    # Direct fallback via public REST endpoint
    import urllib.parse
    import urllib.request
    params = urllib.parse.urlencode({
        "symbol": symbol.upper(),
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": 1000,
    })
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "btc-quant-agent/0.5.1"})
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, list):
            return []
        records = []
        for item in data:
            if isinstance(item, dict):
                mp_raw = item.get("markPrice")
                mark_price = float(mp_raw) if mp_raw is not None and str(mp_raw).strip() != "" else None
                records.append({
                    "symbol": str(item.get("symbol", "")),
                    "funding_time_ms": int(item["fundingTime"]),
                    "funding_rate": float(item["fundingRate"]),
                    "mark_price": mark_price,
                })
        return records


# ==============================================================================
# Evaluation Builder (Section 8, 9, 11, 18, 19, 24)
# ==============================================================================


def build_tactical_shadow_evaluation_v2(
    shadow_record: Mapping[str, Any],
    feature_evidence: TacticalFeatureEvidenceV2,
    candles_15m: Sequence[Candle] = (),
    funding_records: Sequence[dict[str, Any]] | None = None,
    funding_fetch_error: bool = False,
    override_profile_version: str | None = None,
) -> TacticalShadowEvaluationV2:
    """Construct, cross-check, and seal an immutable TacticalShadowEvaluationV2."""
    # Section 25: B1 authority verification
    validate_tactical_feature_evidence(feature_evidence)
    verify_tactical_evidence_identity(feature_evidence)

    # Section 12, 13, 14: Profile version check - missing profile_version => reject as PRE_B2A_HORIZON / ineligible
    raw_prof_ver = override_profile_version or shadow_record.get("evaluation_profile_version")
    if not raw_prof_ver or str(raw_prof_ver).strip() != DIRECTIONAL_OUTCOME_PROFILE_VERSION:
        raise TacticalShadowEvaluationValidationError(
            f"Record is ineligible for B2A materialization: evaluation_profile_version must be "
            f"{DIRECTIONAL_OUTCOME_PROFILE_VERSION}, got {raw_prof_ver!r} (classified as PRE_B2A_HORIZON)"
        )
    profile_ver = str(raw_prof_ver).strip()

    # Section 22, 23, 24: Cross-check attribution
    validate_attribution_crosscheck(feature_evidence, shadow_record)

    rec_id = int(shadow_record["id"])
    symbol = str(shadow_record["symbol"]).upper()
    sig_identity = str(shadow_record.get("signal_identity") or feature_evidence.signal_identity or "")
    setup_key = str(shadow_record.get("setup_key") or feature_evidence.setup_key or "")
    playbook = str(feature_evidence.selected_playbook or "NO_TRADE")
    direction = (
        feature_evidence.decision_trace.final_directional_decision
        if feature_evidence.decision_trace
        else "UNKNOWN"
    )

    signal_t = int(shadow_record.get("signal_time_ms") or shadow_record["timestamp_ms"])
    entry_w_start = int(shadow_record.get("entry_window_start_ms") or signal_t)
    entry_w_end = int(
        shadow_record.get("entry_window_end_ms") or (signal_t + (int(shadow_record.get("entry_window_bars") or 4) * 15 * 60 * 1000))
    )

    profile_info = get_playbook_evaluation_profile(playbook)
    raw_bars = shadow_record.get("evaluation_horizon_bars")
    raw_ms = shadow_record.get("evaluation_horizon_ms")
    eval_horizon_bars = int(raw_bars) if raw_bars is not None else profile_info["horizon_bars"]
    eval_horizon_ms = int(raw_ms) if raw_ms is not None else profile_info["horizon_ms"]

    if eval_horizon_bars != profile_info["horizon_bars"] or eval_horizon_ms != profile_info["horizon_ms"]:
        raise TacticalShadowProfileConflictError(
            f"Horizon conflict: record bars={eval_horizon_bars}, ms={eval_horizon_ms} does not match profile "
            f"for {playbook} (bars={profile_info['horizon_bars']}, ms={profile_info['horizon_ms']})"
        )
    if eval_horizon_ms != eval_horizon_bars * 900_000:
        raise TacticalShadowProfileConflictError(
            f"Horizon invariant violated: ms={eval_horizon_ms} != bars={eval_horizon_bars} * 900_000"
        )

    fill_st = str(shadow_record.get("fill_status") or "WAITING_FOR_FILL")
    fill_p = float(shadow_record["fill_price"]) if shadow_record.get("fill_price") is not None else None
    fill_t = int(shadow_record["fill_time_ms"]) if shadow_record.get("fill_time_ms") is not None else None
    stop_loss = float(shadow_record.get("stop_loss") or 0.0)

    fill_int_start = int(shadow_record["fill_interval_start_ms"]) if shadow_record.get("fill_interval_start_ms") is not None else None
    fill_int_end = int(shadow_record["fill_interval_end_ms"]) if shadow_record.get("fill_interval_end_ms") is not None else None
    fill_time_res = str(shadow_record["fill_time_resolution"]) if shadow_record.get("fill_time_resolution") is not None else None

    time_to_fill_ms = (fill_t - signal_t) if (fill_t is not None and fill_t >= signal_t) else None

    # Handle NO_FILL outcome
    is_no_fill = fill_st == "NO_FILL" or str(shadow_record.get("terminal_reason")) == "NO_FILL"
    if is_no_fill:
        terminal_st = EvaluationTerminalStatus.NO_FILL.value
        terminal_rs = "NO_FILL"
        fill_st = "NO_FILL"
        eval_start_ms = None
        eval_end_ms = entry_w_end
        exit_t = entry_w_end
        exit_p = None
        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        time_from_fill = None
        mfe_r = None
        mae_r = None
        gross_r = None
        exec_cost_r = None
        net_r_ex = None
        net_r_after = None
        funding_acct = FundingAccountingEvidence(
            funding_status=FundingStatus.NOT_APPLICABLE.value,
            notes="Position not filled",
        )
        cov_status = str(shadow_record.get("coverage_status") or "COMPLETE")
        coverage = OutcomeCoverageEvidence(
            coverage_status=cov_status,
            entry_coverage_complete=True,
            outcome_coverage_complete=False,
            start_coverage_ms=entry_w_start,
            end_coverage_ms=entry_w_end,
        )
        checkpoints = compute_diagnostic_checkpoints(
            direction=direction,
            fill_price=None,
            stop_loss=None,
            fill_time_ms=None,
            exit_time_ms=None,
            terminal_reason="NO_FILL",
            candles_15m=candles_15m,
        )
    else:
        # Filled outcome
        terminal_st = EvaluationTerminalStatus.FILLED.value
        terminal_rs = str(shadow_record.get("terminal_reason") or "UNKNOWN")
        eval_start_ms = int(shadow_record.get("evaluation_start_ms") or (fill_t or signal_t))
        eval_end_ms = int(shadow_record.get("evaluation_end_ms") or (eval_start_ms + eval_horizon_ms))
        exit_t = int(shadow_record["exit_time_ms"]) if shadow_record.get("exit_time_ms") is not None else eval_end_ms
        exit_p = float(shadow_record["exit_price"]) if shadow_record.get("exit_price") is not None else None
        tp1_hit = bool(shadow_record.get("tp1_hit", False))
        tp2_hit = bool(shadow_record.get("tp2_hit", False))
        sl_hit = bool(shadow_record.get("sl_hit", False))
        time_from_fill = (exit_t - fill_t) if (fill_t is not None and exit_t >= fill_t) else None
        mfe_r = float(shadow_record["future_mfe"]) if shadow_record.get("future_mfe") is not None else None
        mae_r = float(shadow_record["future_mae"]) if shadow_record.get("future_mae") is not None else None

        # Gross R calculation (Section 18)
        initial_risk = abs(fill_p - stop_loss) if (fill_p is not None and stop_loss > 0) else 1.0
        if initial_risk <= 0.0:
            initial_risk = 1.0
        if exit_p is not None and fill_p is not None:
            price_pnl = (exit_p - fill_p) if direction == "LONG" else (fill_p - exit_p)
            gross_r = price_pnl / initial_risk
        else:
            gross_r = float(shadow_record["gross_r"]) if shadow_record.get("gross_r") is not None else None

        # Execution cost R (Section 19)
        exec_cost_r = float(shadow_record["friction_r"]) if shadow_record.get("friction_r") is not None else 0.0
        net_r_ex = (gross_r - exec_cost_r) if gross_r is not None else None

        # Funding Accounting (Section 20-25)
        funding_acct = evaluate_funding_accounting(
            direction=direction,
            fill_price=fill_p,
            stop_loss=stop_loss,
            fill_time_ms=fill_t,
            exit_time_ms=exit_t,
            funding_records=funding_records,
            fetch_error=funding_fetch_error,
            fill_interval_start_ms=fill_int_start,
            fill_interval_end_ms=fill_int_end,
        )

        if funding_acct.funding_status == FundingStatus.COMPLETE.value and funding_acct.funding_pnl_r is not None and net_r_ex is not None:
            net_r_after = net_r_ex + funding_acct.funding_pnl_r
        else:
            net_r_after = None

        cov_status = str(shadow_record.get("coverage_status") or "COMPLETE")
        coverage = OutcomeCoverageEvidence(
            coverage_status=cov_status,
            entry_coverage_complete=True,
            outcome_coverage_complete=(cov_status == "COMPLETE"),
            start_coverage_ms=entry_w_start,
            end_coverage_ms=exit_t or eval_end_ms,
        )
        checkpoints = compute_diagnostic_checkpoints(
            direction=direction,
            fill_price=fill_p,
            stop_loss=stop_loss,
            fill_time_ms=fill_t,
            exit_time_ms=exit_t,
            terminal_reason=terminal_rs,
            candles_15m=candles_15m,
        )

    attribution = extract_attribution_projection(feature_evidence)
    path_res = str(shadow_record.get("path_resolution") or "FIFTEEN_MINUTE_STOP_FIRST")
    exec_model = str(shadow_record.get("execution_path_model") or "PARTIAL_FIRST_BAR_1M_THEN_15M")
    pol_ver = str(shadow_record.get("policy_version") or feature_evidence.policy_version)
    cfg_hash = str(shadow_record.get("config_hash") or feature_evidence.config_hash)

    # Initial dummy evaluation to compute content-addressed SHA-256 identity
    temp_eval = TacticalShadowEvaluationV2(
        evaluation_schema_version=TACTICAL_SHADOW_EVALUATION_SCHEMA_VERSION,
        evaluation_id="",
        feature_evidence_id=feature_evidence.evidence_id,
        shadow_record_id=rec_id,
        symbol=symbol,
        signal_identity=sig_identity,
        setup_key=setup_key,
        playbook=playbook,
        direction=direction,
        signal_time_ms=signal_t,
        entry_window_start_ms=entry_w_start,
        entry_window_end_ms=entry_w_end,
        fill_status=fill_st,
        fill_time_ms=fill_t,
        fill_price=fill_p,
        fill_interval_start_ms=fill_int_start,
        fill_interval_end_ms=fill_int_end,
        fill_time_resolution=fill_time_res,
        evaluation_profile_version=profile_ver,
        evaluation_horizon_bars=eval_horizon_bars,
        evaluation_horizon_ms=eval_horizon_ms,
        evaluation_start_ms=eval_start_ms,
        evaluation_end_ms=eval_end_ms,
        terminal_status=terminal_st,
        terminal_reason=terminal_rs,
        exit_time_ms=exit_t,
        exit_price=exit_p,
        tp1_hit=tp1_hit,
        tp2_excursion_hit=tp2_hit,
        sl_hit=sl_hit,
        time_to_fill_ms=time_to_fill_ms,
        time_from_fill_to_terminal_ms=time_from_fill,
        mfe_r=mfe_r,
        mae_r=mae_r,
        price_gross_r=gross_r,
        execution_cost_r=exec_cost_r,
        net_r_ex_funding=net_r_ex,
        funding_accounting=funding_acct,
        net_r_after_funding=net_r_after,
        coverage=coverage,
        path_resolution=path_res,
        execution_path_model=exec_model,
        outcome_checkpoints=checkpoints,
        attribution=attribution,
        feature_evidence_hash=feature_evidence.evidence_id,
        policy_version=pol_ver,
        config_hash=cfg_hash,
        forward_evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
        persisted_at_ms=None,
    )

    ev_id = compute_evaluation_id(temp_eval)
    final_eval = cast(TacticalShadowEvaluationV2, dataclass_replace(temp_eval, evaluation_id=ev_id))
    validate_tactical_shadow_evaluation(final_eval)
    return final_eval


def dataclass_replace(instance: Any, **changes: Any) -> Any:
    """Helper to shallow-replace fields on a frozen dataclass."""
    from dataclasses import fields
    kwargs = {f.name: getattr(instance, f.name) for f in fields(instance)}
    kwargs.update(changes)
    return type(instance)(**kwargs)


# ==============================================================================
# Cohort Summary Engine (Section 32, 33, 35)
# ==============================================================================


@dataclass(frozen=True)
class TacticalCohortMetrics:
    cohort_name: str
    signal_count: int
    fill_count: int
    no_fill_count: int
    resolved_filled_count: int
    tp1_count: int
    stop_count: int
    timeout_count: int
    sample_fill_rate: float | None
    sample_tp1_rate_given_fill: float | None
    sample_stop_rate_given_fill: float | None
    sample_timeout_rate_given_fill: float | None
    median_time_to_fill_ms: float | None
    median_time_fill_to_terminal_ms: float | None
    mean_price_gross_r: float | None
    median_price_gross_r: float | None
    mean_net_r_ex_funding: float | None
    median_net_r_ex_funding: float | None
    funding_complete_count: int
    mean_funding_pnl_r: float | None
    mean_net_r_after_funding: float | None
    median_net_r_after_funding: float | None
    median_mfe_r: float | None
    median_mae_r: float | None
    sample_mean_net_r_per_signal_ex_funding: float | None
    sample_mean_net_r_per_signal_after_funding: float | None
    sample_label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_single_cohort_metrics(
    cohort_name: str,
    evals: Sequence[TacticalShadowEvaluationV2],
) -> TacticalCohortMetrics:
    """Compute descriptive statistics for a single evaluation cohort."""
    signal_count = len(evals)
    fill_count = sum(1 for e in evals if e.fill_status == "FILLED")
    no_fill_count = sum(1 for e in evals if e.fill_status == "NO_FILL")

    resolved_filled = [
        e for e in evals
        if e.fill_status == "FILLED" and e.terminal_reason in ("TP1", "STOP", "TIMEOUT")
    ]
    resolved_filled_count = len(resolved_filled)

    tp1_count = sum(1 for e in resolved_filled if e.terminal_reason == "TP1")
    stop_count = sum(1 for e in resolved_filled if e.terminal_reason == "STOP")
    timeout_count = sum(1 for e in resolved_filled if e.terminal_reason == "TIMEOUT")

    sample_fill_rate = (fill_count / signal_count) if signal_count > 0 else None
    sample_tp1_rate = (tp1_count / resolved_filled_count) if resolved_filled_count > 0 else None
    sample_stop_rate = (stop_count / resolved_filled_count) if resolved_filled_count > 0 else None
    sample_timeout_rate = (timeout_count / resolved_filled_count) if resolved_filled_count > 0 else None

    # Time to fill
    times_to_fill = [e.time_to_fill_ms for e in evals if e.time_to_fill_ms is not None]
    median_time_to_fill = statistics.median(times_to_fill) if times_to_fill else None

    # Time fill to terminal
    times_fill_term = [e.time_from_fill_to_terminal_ms for e in resolved_filled if e.time_from_fill_to_terminal_ms is not None]
    median_time_fill_term = statistics.median(times_fill_term) if times_fill_term else None

    # Gross R
    gross_rs = [e.price_gross_r for e in resolved_filled if e.price_gross_r is not None]
    mean_gross_r = statistics.mean(gross_rs) if gross_rs else None
    median_gross_r = statistics.median(gross_rs) if gross_rs else None

    # Net R ex-funding
    net_ex_rs = [e.net_r_ex_funding for e in resolved_filled if e.net_r_ex_funding is not None]
    mean_net_ex = statistics.mean(net_ex_rs) if net_ex_rs else None
    median_net_ex = statistics.median(net_ex_rs) if net_ex_rs else None

    # Funding P&L R
    funding_complete_trades = [
        e for e in resolved_filled
        if e.funding_accounting.funding_status == FundingStatus.COMPLETE.value
    ]
    funding_complete_count = len(funding_complete_trades)

    funding_pnls = [
        e.funding_accounting.funding_pnl_r for e in funding_complete_trades
        if e.funding_accounting.funding_pnl_r is not None
    ]
    mean_funding_pnl = statistics.mean(funding_pnls) if funding_pnls else None

    # Net R after funding
    net_after_rs = [e.net_r_after_funding for e in funding_complete_trades if e.net_r_after_funding is not None]
    mean_net_after = statistics.mean(net_after_rs) if net_after_rs else None
    median_net_after = statistics.median(net_after_rs) if net_after_rs else None

    # MFE / MAE
    mfes = [e.mfe_r for e in resolved_filled if e.mfe_r is not None]
    maes = [e.mae_r for e in resolved_filled if e.mae_r is not None]
    median_mfe = statistics.median(mfes) if mfes else None
    median_mae = statistics.median(maes) if maes else None

    # Signal-level net R sample (Section 33)
    # NO_FILL = 0 trading R; FILLED resolved = net_r_ex_funding
    # Denominator is resolved_filled_count + no_fill_count
    signal_denom = resolved_filled_count + no_fill_count
    if signal_denom > 0:
        total_r_ex = sum(e.net_r_ex_funding for e in resolved_filled if e.net_r_ex_funding is not None)
        sample_mean_net_r_per_signal_ex = total_r_ex / signal_denom
    else:
        sample_mean_net_r_per_signal_ex = None

    # After funding signal expectancy: only compute if ALL resolved filled trades have complete funding
    if signal_denom > 0 and funding_complete_count == resolved_filled_count:
        total_r_after = sum(e.net_r_after_funding for e in funding_complete_trades if e.net_r_after_funding is not None)
        sample_mean_net_r_per_signal_after = total_r_after / signal_denom
    else:
        sample_mean_net_r_per_signal_after = None

    label = sample_size_label(signal_count)

    return TacticalCohortMetrics(
        cohort_name=cohort_name,
        signal_count=signal_count,
        fill_count=fill_count,
        no_fill_count=no_fill_count,
        resolved_filled_count=resolved_filled_count,
        tp1_count=tp1_count,
        stop_count=stop_count,
        timeout_count=timeout_count,
        sample_fill_rate=sample_fill_rate,
        sample_tp1_rate_given_fill=sample_tp1_rate,
        sample_stop_rate_given_fill=sample_stop_rate,
        sample_timeout_rate_given_fill=sample_timeout_rate,
        median_time_to_fill_ms=median_time_to_fill,
        median_time_fill_to_terminal_ms=median_time_fill_term,
        mean_price_gross_r=mean_gross_r,
        median_price_gross_r=median_gross_r,
        mean_net_r_ex_funding=mean_net_ex,
        median_net_r_ex_funding=median_net_ex,
        funding_complete_count=funding_complete_count,
        mean_funding_pnl_r=mean_funding_pnl,
        mean_net_r_after_funding=mean_net_after,
        median_net_r_after_funding=median_net_after,
        median_mfe_r=median_mfe,
        median_mae_r=median_mae,
        sample_mean_net_r_per_signal_ex_funding=sample_mean_net_r_per_signal_ex,
        sample_mean_net_r_per_signal_after_funding=sample_mean_net_r_per_signal_after,
        sample_label=label,
    )


def compute_tactical_cohort_summary_v1(
    evaluations: Sequence[TacticalShadowEvaluationV2],
    stratification_dimension: str | None = None,
) -> dict[str, Any]:
    """Pure summary API over sealed B2A evaluations and linked feature attribution."""
    overall = _compute_single_cohort_metrics("OVERALL", evaluations)

    cohorts_map: dict[str, Any] = {"OVERALL": overall.to_dict()}

    if stratification_dimension is not None and evaluations:
        dim = stratification_dimension.lower()
        groups: dict[str, list[TacticalShadowEvaluationV2]] = {}

        for e in evaluations:
            key = "UNKNOWN"
            attr = e.attribution
            if attr is not None:
                if dim == "playbook":
                    key = attr.selected_playbook
                elif dim == "direction":
                    key = attr.direction
                elif dim in ("playbook_direction", "playbook_x_direction"):
                    key = f"{attr.selected_playbook}_{attr.direction}"
                elif dim == "regime_1h":
                    key = attr.regime_1h
                elif dim == "regime_4h":
                    key = attr.regime_4h
                elif dim == "entry_quality":
                    key = attr.entry_quality
                elif dim == "derivatives_regime":
                    key = attr.derivatives_regime
                elif dim == "benchmark_context":
                    key = attr.benchmark_context
                elif dim == "reference_universe_status":
                    key = attr.reference_universe_status
                elif dim == "rule_score_bucket":
                    key = attr.rule_score_bucket
                else:
                    key = getattr(attr, dim, "UNKNOWN")
            else:
                if dim == "playbook":
                    key = e.playbook
                elif dim == "direction":
                    key = e.direction

            groups.setdefault(key, []).append(e)

        stratified_results: dict[str, Any] = {}
        for group_key, group_evals in sorted(groups.items()):
            stratified_results[group_key] = _compute_single_cohort_metrics(group_key, group_evals).to_dict()

        cohorts_map["stratification_dimension"] = dim
        cohorts_map["stratified_cohorts"] = stratified_results

    return {
        "summary_schema_version": TACTICAL_COHORT_SUMMARY_VERSION,
        "evaluation_count": len(evaluations),
        "cohorts": cohorts_map,
    }


def deserialize_tactical_shadow_evaluation(
    raw_json: str | dict[str, Any],
    verify_identity: bool = True,
) -> TacticalShadowEvaluationV2:
    """Deserialize JSON payload into frozen TacticalShadowEvaluationV2 and verify identity."""
    if isinstance(raw_json, str):
        payload = json.loads(raw_json)
    else:
        payload = dict(raw_json)

    # Reconstruct sub-components
    funding_data = payload.get("funding_accounting") or {}
    settlements_list = []
    for s_dict in funding_data.get("settlements", []):
        settlements_list.append(
            FundingSettlementEvidence(
                funding_time_ms=int(s_dict["funding_time_ms"]),
                funding_rate=float(s_dict["funding_rate"]),
                mark_price=float(s_dict["mark_price"]) if s_dict.get("mark_price") is not None else None,
                funding_cash=float(s_dict["funding_cash"]) if s_dict.get("funding_cash") is not None else None,
                funding_r=float(s_dict["funding_r"]) if s_dict.get("funding_r") is not None else None,
                is_settlement_open=bool(s_dict.get("is_settlement_open", True)),
                status=str(s_dict.get("status", "SETTLED")),
            )
        )
    funding_acct = FundingAccountingEvidence(
        accounting_version=str(funding_data.get("accounting_version", FUNDING_ACCOUNTING_VERSION)),
        funding_status=str(funding_data.get("funding_status", FundingStatus.NOT_APPLICABLE.value)),
        settlements_count=int(funding_data.get("settlements_count", len(settlements_list))),
        settlements=tuple(settlements_list),
        funding_pnl_r=float(funding_data["funding_pnl_r"]) if funding_data.get("funding_pnl_r") is not None else None,
        funding_cash_total=float(funding_data["funding_cash_total"]) if funding_data.get("funding_cash_total") is not None else None,
        initial_risk=float(funding_data["initial_risk"]) if funding_data.get("initial_risk") is not None else None,
        notes=str(funding_data.get("notes", "")),
    )

    cov_data = payload.get("coverage") or {}
    coverage = OutcomeCoverageEvidence(
        coverage_status=str(cov_data.get("coverage_status", "COMPLETE")),
        entry_coverage_complete=bool(cov_data.get("entry_coverage_complete", True)),
        outcome_coverage_complete=bool(cov_data.get("outcome_coverage_complete", True)),
        start_coverage_ms=int(cov_data.get("start_coverage_ms", 0)),
        end_coverage_ms=int(cov_data.get("end_coverage_ms", 0)),
        expected_15m_bars=int(cov_data.get("expected_15m_bars", 0)),
        observed_15m_bars=int(cov_data.get("observed_15m_bars", 0)),
        expected_1m_bars=int(cov_data.get("expected_1m_bars", 0)),
        observed_1m_bars=int(cov_data.get("observed_1m_bars", 0)),
        notes=str(cov_data.get("notes", "")),
    )

    checkpoints_list = []
    for cp_dict in payload.get("outcome_checkpoints", []):
        checkpoints_list.append(
            OutcomeCheckpointEvidence(
                checkpoint_horizon_hours=int(cp_dict["checkpoint_horizon_hours"]),
                checkpoint_horizon_ms=int(cp_dict["checkpoint_horizon_ms"]),
                target_time_ms=int(cp_dict["target_time_ms"]),
                status=str(cp_dict["status"]),
                mark_price=float(cp_dict["mark_price"]) if cp_dict.get("mark_price") is not None else None,
                mark_to_market_gross_r=float(cp_dict["mark_to_market_gross_r"]) if cp_dict.get("mark_to_market_gross_r") is not None else None,
                mfe_r_to_checkpoint=float(cp_dict["mfe_r_to_checkpoint"]) if cp_dict.get("mfe_r_to_checkpoint") is not None else None,
                mae_r_to_checkpoint=float(cp_dict["mae_r_to_checkpoint"]) if cp_dict.get("mae_r_to_checkpoint") is not None else None,
                barrier_status=str(cp_dict.get("barrier_status", "ACTIVE")),
            )
        )

    attribution = None
    if "attribution" in payload and payload["attribution"] is not None:
        at_dict = payload["attribution"]
        comps = tuple(tuple(item) for item in at_dict.get("rule_score_components", []))
        attribution = AttributionProjectionEvidence(
            selected_playbook=str(at_dict.get("selected_playbook", "")),
            direction=str(at_dict.get("direction", "")),
            regime_1h=str(at_dict.get("regime_1h", "")),
            regime_4h=str(at_dict.get("regime_4h", "")),
            entry_quality=str(at_dict.get("entry_quality", "")),
            derivatives_regime=str(at_dict.get("derivatives_regime", "")),
            benchmark_context=str(at_dict.get("benchmark_context", "")),
            reference_universe_status=str(at_dict.get("reference_universe_status", "")),
            rule_score=float(at_dict.get("rule_score", 0.0)),
            rule_score_bucket=str(at_dict.get("rule_score_bucket", "")),
            rule_score_components=comps,
            exhaustion_state=str(at_dict.get("exhaustion_state", "NEUTRAL")),
        )

    evaluation = TacticalShadowEvaluationV2(
        evaluation_schema_version=str(payload["evaluation_schema_version"]),
        evaluation_id=str(payload.get("evaluation_id") or compute_evaluation_id(payload)),
        feature_evidence_id=str(payload["feature_evidence_id"]),
        shadow_record_id=int(payload["shadow_record_id"]),
        symbol=str(payload["symbol"]),
        signal_identity=str(payload.get("signal_identity", "")),
        setup_key=str(payload.get("setup_key", "")),
        playbook=str(payload["playbook"]),
        direction=str(payload["direction"]),
        signal_time_ms=int(payload["signal_time_ms"]),
        entry_window_start_ms=int(payload["entry_window_start_ms"]),
        entry_window_end_ms=int(payload["entry_window_end_ms"]),
        fill_status=str(payload["fill_status"]),
        fill_time_ms=int(payload["fill_time_ms"]) if payload.get("fill_time_ms") is not None else None,
        fill_price=float(payload["fill_price"]) if payload.get("fill_price") is not None else None,
        fill_interval_start_ms=int(payload["fill_interval_start_ms"]) if payload.get("fill_interval_start_ms") is not None else None,
        fill_interval_end_ms=int(payload["fill_interval_end_ms"]) if payload.get("fill_interval_end_ms") is not None else None,
        fill_time_resolution=str(payload["fill_time_resolution"]) if payload.get("fill_time_resolution") is not None else None,
        evaluation_profile_version=str(payload["evaluation_profile_version"]),
        evaluation_horizon_bars=int(payload.get("evaluation_horizon_bars", 0)),
        evaluation_horizon_ms=int(payload["evaluation_horizon_ms"]),
        evaluation_start_ms=int(payload["evaluation_start_ms"]) if payload.get("evaluation_start_ms") is not None else None,
        evaluation_end_ms=int(payload["evaluation_end_ms"]) if payload.get("evaluation_end_ms") is not None else None,
        terminal_status=str(payload["terminal_status"]),
        terminal_reason=str(payload["terminal_reason"]) if payload.get("terminal_reason") is not None else None,
        exit_time_ms=int(payload["exit_time_ms"]) if payload.get("exit_time_ms") is not None else None,
        exit_price=float(payload["exit_price"]) if payload.get("exit_price") is not None else None,
        tp1_hit=bool(payload.get("tp1_hit", False)),
        tp2_excursion_hit=bool(payload.get("tp2_excursion_hit", False)),
        sl_hit=bool(payload.get("sl_hit", False)),
        time_to_fill_ms=int(payload["time_to_fill_ms"]) if payload.get("time_to_fill_ms") is not None else None,
        time_from_fill_to_terminal_ms=int(payload["time_from_fill_to_terminal_ms"]) if payload.get("time_from_fill_to_terminal_ms") is not None else None,
        mfe_r=float(payload["mfe_r"]) if payload.get("mfe_r") is not None else None,
        mae_r=float(payload["mae_r"]) if payload.get("mae_r") is not None else None,
        price_gross_r=float(payload["price_gross_r"]) if payload.get("price_gross_r") is not None else None,
        execution_cost_r=float(payload["execution_cost_r"]) if payload.get("execution_cost_r") is not None else None,
        net_r_ex_funding=float(payload["net_r_ex_funding"]) if payload.get("net_r_ex_funding") is not None else None,
        funding_accounting=funding_acct,
        net_r_after_funding=float(payload["net_r_after_funding"]) if payload.get("net_r_after_funding") is not None else None,
        coverage=coverage,
        path_resolution=str(payload.get("path_resolution", "")),
        execution_path_model=str(payload.get("execution_path_model", "")),
        outcome_checkpoints=tuple(checkpoints_list),
        attribution=attribution,
        feature_evidence_hash=str(payload.get("feature_evidence_hash", "")),
        policy_version=str(payload.get("policy_version", "")),
        config_hash=str(payload.get("config_hash", "")),
        forward_evidence_version=str(payload.get("forward_evidence_version", MARKET_WATCH_EVIDENCE_VERSION)),
        persisted_at_ms=int(payload["persisted_at_ms"]) if payload.get("persisted_at_ms") is not None else None,
    )

    if verify_identity:
        validate_tactical_shadow_evaluation(evaluation)
    return evaluation
