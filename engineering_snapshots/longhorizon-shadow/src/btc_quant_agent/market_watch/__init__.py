"""Isolated operational multi-asset market watch and trading policy subsystem."""

from typing import TYPE_CHECKING, Any

from .config import MarketWatchConfig
from .domain import (
    DIRECTIONAL_OUTCOME_PROFILE_VERSION,
    FUNDING_ACCOUNTING_VERSION,
    GRID_ACCOUNTING_VERSION,
    GRID_OUTCOME_PROFILE_VERSION,
    GRID_PATH_MODEL_VERSION,
    RULE_SCORE_BUCKETS_VERSION,
    STANDARD_DIAGNOSTIC_CHECKPOINTS_VERSION,
    TACTICAL_COHORT_SUMMARY_VERSION,
    TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION,
    TACTICAL_SHADOW_EVALUATION_SCHEMA_VERSION,
    AlertSeverity,
    BenchmarkContext,
    ConfidenceBand,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    GridDecision,
    GridPlan,
    MarketSnapshot,
    MarketWatchAlert,
    PlaybookType,
    PriceMetrics,
    RelativePerformance,
    ScanHealth,
    SignalLifecycleState,
    SymbolAssessment,
    TimeframeSnapshot,
)
from .grid_shadow_evidence import (
    GridEligibilityStatus,
    GridTerminalReason,
    TacticalGridShadowEvaluationConflictError,
    TacticalGridShadowEvaluationError,
    TacticalGridShadowEvaluationIdentityError,
    TacticalGridShadowEvaluationV1,
    TacticalGridShadowEvaluationValidationError,
    canonical_grid_shadow_evaluation_json,
    compute_anchor_index,
    construct_grid_levels,
    deserialize_tactical_grid_shadow_evaluation,
    resolve_reference_price,
    validate_tactical_grid_shadow_evaluation,
    verify_tactical_grid_shadow_evaluation_identity,
)
from .shadow_evidence import (
    AttributionProjectionEvidence,
    FundingAccountingEvidence,
    FundingSettlementEvidence,
    OutcomeCheckpointEvidence,
    OutcomeCoverageEvidence,
    TacticalShadowAttributionConflictError,
    TacticalShadowEvaluationConflictError,
    TacticalShadowEvaluationError,
    TacticalShadowEvaluationIdentityError,
    TacticalShadowEvaluationV2,
    TacticalShadowEvaluationValidationError,
    TacticalShadowProfileConflictError,
    build_tactical_shadow_evaluation_v2,
    canonical_shadow_evaluation_json,
    classify_rule_score_bucket,
    compute_tactical_cohort_summary_v1,
    deserialize_tactical_shadow_evaluation,
    get_playbook_evaluation_profile,
    validate_tactical_shadow_evaluation,
    verify_shadow_evaluation_identity,
)

if TYPE_CHECKING:
    from .grid_shadow import (
        GridShadowEvaluationManager,
        evaluate_grid_shadow_episode,
    )
    from .scanner import MarketWatchScanner
    from .service import MarketWatchService


def __getattr__(name: str) -> Any:
    if name == "MarketWatchScanner":
        from .scanner import MarketWatchScanner
        return MarketWatchScanner
    if name == "MarketWatchService":
        from .service import MarketWatchService
        return MarketWatchService
    if name == "GridShadowEvaluationManager":
        from .grid_shadow import GridShadowEvaluationManager
        return GridShadowEvaluationManager
    if name == "evaluate_grid_shadow_episode":
        from .grid_shadow import evaluate_grid_shadow_episode
        return evaluate_grid_shadow_episode
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "DIRECTIONAL_OUTCOME_PROFILE_VERSION",
    "FUNDING_ACCOUNTING_VERSION",
    "GRID_ACCOUNTING_VERSION",
    "GRID_OUTCOME_PROFILE_VERSION",
    "GRID_PATH_MODEL_VERSION",
    "RULE_SCORE_BUCKETS_VERSION",
    "STANDARD_DIAGNOSTIC_CHECKPOINTS_VERSION",
    "TACTICAL_COHORT_SUMMARY_VERSION",
    "TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION",
    "TACTICAL_SHADOW_EVALUATION_SCHEMA_VERSION",
    "AlertSeverity",
    "AttributionProjectionEvidence",
    "BenchmarkContext",
    "ConfidenceBand",
    "DerivativesMetrics",
    "DerivativesRegime",
    "DirectionalDecision",
    "DirectionalPlan",
    "EntryQuality",
    "ExhaustionMetrics",
    "ExhaustionState",
    "FundingAccountingEvidence",
    "FundingSettlementEvidence",
    "GridDecision",
    "GridEligibilityStatus",
    "GridPlan",
    "GridShadowEvaluationManager",
    "GridTerminalReason",
    "MarketSnapshot",
    "MarketWatchAlert",
    "MarketWatchConfig",
    "MarketWatchScanner",
    "MarketWatchService",
    "OutcomeCheckpointEvidence",
    "OutcomeCoverageEvidence",
    "PlaybookType",
    "PriceMetrics",
    "RelativePerformance",
    "ScanHealth",
    "SignalLifecycleState",
    "SymbolAssessment",
    "TacticalGridShadowEvaluationConflictError",
    "TacticalGridShadowEvaluationError",
    "TacticalGridShadowEvaluationIdentityError",
    "TacticalGridShadowEvaluationV1",
    "TacticalGridShadowEvaluationValidationError",
    "TacticalShadowAttributionConflictError",
    "TacticalShadowEvaluationConflictError",
    "TacticalShadowEvaluationError",
    "TacticalShadowEvaluationIdentityError",
    "TacticalShadowEvaluationV2",
    "TacticalShadowEvaluationValidationError",
    "TacticalShadowProfileConflictError",
    "TimeframeSnapshot",
    "build_tactical_shadow_evaluation_v2",
    "canonical_grid_shadow_evaluation_json",
    "canonical_shadow_evaluation_json",
    "classify_rule_score_bucket",
    "compute_anchor_index",
    "compute_tactical_cohort_summary_v1",
    "construct_grid_levels",
    "deserialize_tactical_grid_shadow_evaluation",
    "deserialize_tactical_shadow_evaluation",
    "evaluate_grid_shadow_episode",
    "get_playbook_evaluation_profile",
    "resolve_reference_price",
    "validate_tactical_grid_shadow_evaluation",
    "validate_tactical_shadow_evaluation",
    "verify_shadow_evaluation_identity",
    "verify_tactical_grid_shadow_evaluation_identity",
]

