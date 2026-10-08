"""G2 R3 Independent PIT, Fill, Cost, Risk & Manifest Verification Oracle (Role B / GEMINI_B).

Offline/synthetic P0 verification package authorized under Controller dispatch
56f8a9faa1a4539124ab006b49bf42b6e7c997e3. Zero raw market price/mark/funding body reads,
zero external network calls, and zero execution authority.
"""

from __future__ import annotations

from scripts.strategy_research.r3_verification.a_impl_static_auditor import (
    AImplAuditResult,
    audit_remote_a_impl_commit,
    resolve_remote_a_impl_sha,
)
from scripts.strategy_research.r3_verification.manifest_and_boundary_oracle import (
    BoundaryCheckResult,
    HoldoutConflictReport,
    ManifestVerificationResult,
    check_HoldoutWindowOverlap,
    check_source_and_product_boundary,
    verify_static_btc_data_manifest,
)
from scripts.strategy_research.r3_verification.oracle_specs import (
    ALLOWLISTED_MARKET,
    ALLOWLISTED_SYMBOLS,
    BASE_COST_SCENARIO,
    CANDIDATE_REGISTRY_IDS,
    CONTROLLER_DISPATCH_SHA,
    FROZEN_CODE_BASE_SHA,
    METHOD_ADDENDUM_HEAD_SHA,
    ORIGINAL_DESIGN_SHA,
    SOURCE_AUDIT_SHA,
    STRESS_COST_SCENARIO,
    CostScenario,
    decimal_context,
    round_ledger_usdt,
)
from scripts.strategy_research.r3_verification.pit_bar_and_signal_oracle import (
    Bar1m,
    ClosedRetestEvent,
    HigherTimeframeBar,
    SignalDecisionResult,
    StressGeometryResult,
    aggregate_completed_bars,
    compute_atr20,
    compute_ema_series,
    compute_er12,
    evaluate_closed_retest_candidate,
    evaluate_stress_cost_geometry,
    evaluate_structural_continuation_candidate,
)
from scripts.strategy_research.r3_verification.two_clock_accounting_oracle import (
    IndependentBookOracle,
    MarketBarMessage,
    MatchedEpisodeOracle,
    OracleMessage,
    OrderRequest,
    PositionRecord,
    ReserveRecord,
    SettlementWindow,
    TradeOutcomeSummary,
)

__all__ = [
    "ALLOWLISTED_MARKET",
    "ALLOWLISTED_SYMBOLS",
    "BASE_COST_SCENARIO",
    "CANDIDATE_REGISTRY_IDS",
    "CONTROLLER_DISPATCH_SHA",
    "FROZEN_CODE_BASE_SHA",
    "METHOD_ADDENDUM_HEAD_SHA",
    "ORIGINAL_DESIGN_SHA",
    "SOURCE_AUDIT_SHA",
    "STRESS_COST_SCENARIO",
    "AImplAuditResult",
    "Bar1m",
    "BoundaryCheckResult",
    "ClosedRetestEvent",
    "CostScenario",
    "HigherTimeframeBar",
    "HoldoutConflictReport",
    "IndependentBookOracle",
    "ManifestVerificationResult",
    "MarketBarMessage",
    "MatchedEpisodeOracle",
    "OracleMessage",
    "OrderRequest",
    "PositionRecord",
    "ReserveRecord",
    "SettlementWindow",
    "SignalDecisionResult",
    "StressGeometryResult",
    "TradeOutcomeSummary",
    "aggregate_completed_bars",
    "audit_remote_a_impl_commit",
    "check_HoldoutWindowOverlap",
    "check_source_and_product_boundary",
    "compute_atr20",
    "compute_ema_series",
    "compute_er12",
    "decimal_context",
    "evaluate_closed_retest_candidate",
    "evaluate_stress_cost_geometry",
    "evaluate_structural_continuation_candidate",
    "resolve_remote_a_impl_sha",
    "round_ledger_usdt",
    "verify_static_btc_data_manifest",
]
