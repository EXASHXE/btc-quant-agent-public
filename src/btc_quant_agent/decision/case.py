from __future__ import annotations

from ..market_watch.domain import SymbolAssessment
from ..market_watch.evidence import (
    TacticalEvidenceError,
    TacticalFeatureEvidenceV2,
    validate_tactical_feature_evidence,
    verify_tactical_evidence_identity,
)
from .models import AccountContextV1, CasePackageV1, content_hash


def case_from_assessment(
    assessment: SymbolAssessment, *, ttl_ms: int,
    account: AccountContextV1 | None = None,
) -> CasePackageV1:
    """Project only verified, allowlisted market evidence; never project runtime config."""
    evidence = assessment.feature_evidence
    if not isinstance(evidence, TacticalFeatureEvidenceV2):
        raise TypeError("SOURCE_EVIDENCE_REQUIRED")
    try:
        verify_tactical_evidence_identity(evidence)
        validate_tactical_feature_evidence(evidence)
    except TacticalEvidenceError:
        raise ValueError("SOURCE_EVIDENCE_INVALID") from None
    if (assessment.feature_evidence_id != evidence.evidence_id
            or assessment.snapshot.snapshot_hash != evidence.snapshot_hash
            or assessment.symbol != evidence.symbol):
        raise ValueError("SOURCE_EVIDENCE_LINKAGE")
    plan = evidence.directional_risk_plan
    if plan is None:
        raise ValueError("SOURCE_EVIDENCE_PLAN_REQUIRED")
    if ttl_ms <= 0:
        raise ValueError("case TTL must be positive")
    market = evidence.market_snapshot_features
    derivative = market.derivatives
    created = max(evidence.decision_time_ms, evidence.observed_at_ms,
                  evidence.collection_completed_at_ms)
    receipts = evidence.source_provenance
    receipt_fields = (
        "derivatives_observed_at_ms", "ticker_receipt_ms", "oi_hist_receipt_ms",
        "top_pos_receipt_ms", "top_acc_receipt_ms", "server_time_receipt_ms",
    )
    missing = tuple(name for name, available in derivative.field_availability if not available)
    # Preserve source failure occurrence without copying provider exception text.
    errors = tuple(f"SOURCE_ERROR_{i}" for i, _ in enumerate(receipts.endpoint_errors))
    identity = evidence.signal_identity or f"evidence:{evidence.evidence_id}"
    case_id = content_hash({"evidence": evidence.evidence_id, "trigger": "MARKET_WATCH"})
    return CasePackageV1.build(
        case_id=case_id, created_at_ms=created, observed_at_ms=evidence.observed_at_ms,
        expires_at_ms=created + ttl_ms, symbol=evidence.symbol, trigger="MARKET_WATCH",
        strategy=plan.setup, strategy_version=evidence.policy_version, direction=plan.decision,
        evidence_id=evidence.evidence_id, snapshot_hash=evidence.snapshot_hash,
        signal_identity=identity,
        source_receipts=tuple((name, value) for name in receipt_fields
                              if isinstance(value := getattr(receipts, name), int)),
        price=market.last_price, entry_low=plan.entry_low, entry_high=plan.entry_high,
        stop_loss=plan.stop_loss, take_profit_1=plan.take_profit_1,
        take_profit_2=plan.take_profit_2, supports=market.tf_1h.supports,
        resistances=market.tf_1h.resistances, atr=market.tf_1h.atr,
        volatility_percentile=market.tf_1h.atr_percentile, volume=market.tf_1h.volume,
        regime_15m=market.tf_15m.regime, regime_1h=market.tf_1h.regime,
        regime_4h=market.tf_4h.regime, funding_rate=derivative.funding_rate,
        open_interest=derivative.current_open_interest, oi_1h_change=derivative.oi_1h_change,
        oi_4h_change=derivative.oi_4h_change, oi_12h_change=derivative.oi_12h_change,
        basis_rate=derivative.basis_rate, taker_ratio=derivative.taker_buy_sell_ratio,
        global_account_ratio=derivative.global_account_long_short_ratio,
        top_trader_position_ratio=derivative.top_trader_position_ratio,
        top_trader_account_ratio=derivative.top_trader_account_ratio,
        spread_bps=derivative.spread_bps, book_imbalance=derivative.order_book_imbalance,
        liquidity_usdt=market.quote_volume_24h, liquidity_measure="QUOTE_VOLUME_24H_PROXY",
        reason_codes=evidence.reason_codes, risk_codes=evidence.risk_codes,
        veto_reasons=evidence.veto_reasons, entry_quality=evidence.entry_quality,
        grid_state=evidence.grid_advisory_plan.decision if evidence.grid_advisory_plan else "UNKNOWN",
        account=account, data_quality="DEGRADED" if errors or evidence.veto_reasons else "OK",
        missing_fields=missing, source_errors=errors,
    )
