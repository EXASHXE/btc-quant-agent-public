from __future__ import annotations

import math
from typing import Annotated, Self

from pydantic import Field, model_validator

from .models import (
    AnalysisResultV1,
    CasePackageV1,
    ImmutableModel,
    Nonnegative,
    Positive,
    TradeProposalV1,
    content_hash,
)

Fraction = Annotated[float, Field(gt=0, le=1)]


class RiskPolicyV1(ImmutableModel):
    simulation_equity_usdt: Positive = 1000.0
    max_trade_risk_usdt: Positive = 10.0
    max_trade_risk_pct: Fraction = 0.01
    max_symbol_exposure_pct: Fraction = 0.2
    max_portfolio_exposure_pct: Fraction = 0.5
    max_notional_usdt: Positive = 1000.0
    max_leverage: Annotated[int, Field(ge=1, le=125)] = 5
    configured_leverage: Annotated[int, Field(ge=1, le=125)] = 2
    max_margin_utilization: Fraction = 0.5
    max_simultaneous_positions: Annotated[int, Field(gt=0)] = 5
    max_daily_loss_pct: Fraction = 0.03
    drawdown_kill_pct: Fraction = 0.1
    max_staleness_ms: Annotated[int, Field(gt=0)] = 120000
    max_spread_bps: Positive = 5.0
    min_liquidity_usdt: Positive = 10000.0
    max_liquidity_fraction: Fraction = 0.01
    proposal_ttl_ms: Annotated[int, Field(gt=0)] = 60000
    allowed_price_drift_bps: Nonnegative = 20.0
    round_trip_fee_bps: Nonnegative = 8.0
    slippage_bps: Nonnegative = 4.0
    funding_buffer_bps: Nonnegative = 1.0
    reduced_risk_fraction: Fraction = 0.5

    @model_validator(mode="after")
    def validate_leverage(self) -> Self:
        if self.configured_leverage > self.max_leverage:
            raise ValueError("configured leverage exceeds maximum")
        return self

    @property
    def policy_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class RiskCompilerV1:
    """Deterministic simulation sizing. Model advice can only reduce or block risk."""

    def __init__(self, policy: RiskPolicyV1) -> None:
        self.policy = policy

    def compile(
        self, case: CasePackageV1, analysis: AnalysisResultV1, *, now_ms: int,
        analysis_result_hashes: tuple[str, ...] | None = None,
        requires_manual_review: bool = False,
    ) -> TradeProposalV1:
        case.verify()
        analysis.verify_case(case)
        p = self.policy
        if (now_ms < case.created_at_ms or now_ms >= case.expires_at_ms
                or now_ms - case.observed_at_ms > p.max_staleness_ms):
            raise ValueError("STALE_CASE")
        account = case.account
        equity = account.equity_usdt if account else p.simulation_equity_usdt
        reasons: list[str] = []
        if case.data_quality != "OK" or case.source_errors or case.veto_reasons:
            reasons.append("DATA_QUALITY")
        if case.spread_bps is None or case.spread_bps > p.max_spread_bps:
            reasons.append("SPREAD_CAP")
        if case.liquidity_usdt is None:
            reasons.append("LIQUIDITY_MISSING")
        elif case.liquidity_usdt < p.min_liquidity_usdt:
            reasons.append("LIQUIDITY_CAP")
        if analysis.risk_modifier == "BLOCK":
            reasons.append("MODEL_BLOCK")
        if analysis.requires_manual_review or requires_manual_review:
            reasons.append("MANUAL_REVIEW")
        if analysis.action not in ("OPEN_LONG", "OPEN_SHORT", "ADD"):
            reasons.append("NON_ENTRY_ACTION")
        expected = "SHORT" if analysis.action == "OPEN_SHORT" else "LONG"
        if analysis.action == "ADD":
            expected = case.direction
            if (not account or not account.prior_signal_identities or not account.prior_evidence_ids
                    or case.signal_identity in account.prior_signal_identities
                    or case.evidence_id in account.prior_evidence_ids):
                reasons.append("ADD_FRESH_EVIDENCE_REQUIRED")
        if case.direction != expected or analysis.strategy_data_disagreement:
            reasons.append("STRATEGY_DATA_DISAGREEMENT")
        if account:
            if (account.observed_at_ms > now_ms
                    or now_ms - account.observed_at_ms > p.max_staleness_ms):
                reasons.append("STALE_ACCOUNT")
            if account.daily_loss_usdt >= equity * p.max_daily_loss_pct:
                reasons.append("DAILY_LOSS_CAP")
            if account.drawdown_pct >= p.drawdown_kill_pct:
                reasons.append("DRAWDOWN_KILL_SWITCH")
            if (analysis.action != "ADD"
                    and account.simultaneous_positions >= p.max_simultaneous_positions):
                reasons.append("POSITION_CAP")
        long = case.direction == "LONG"
        geometry = (
            0 < case.stop_loss < case.entry_low <= case.entry_high
            < case.take_profit_1 <= case.take_profit_2
        ) if long else (
            0 < case.take_profit_2 <= case.take_profit_1 < case.entry_low
            <= case.entry_high < case.stop_loss
        )
        if not geometry:
            reasons.append("INVALID_GEOMETRY")
        entry = case.entry_high if long else case.entry_low
        # All costs are adverse, including funding; rebates never expand risk.
        funding_rate = max(p.funding_buffer_bps / 10000, abs(case.funding_rate or 0))
        loss_rate = (
            abs(entry - case.stop_loss) / entry if entry > 0 else 1.0
        ) + p.round_trip_fee_bps / 10000 + p.slippage_bps / 10000 + funding_rate
        risk = min(p.max_trade_risk_usdt, equity * p.max_trade_risk_pct)
        if account:
            remaining_daily = max(0.0, equity * p.max_daily_loss_pct - account.daily_loss_usdt)
            remaining_drawdown = max(
                0.0, equity / (1 - account.drawdown_pct)
                * (p.drawdown_kill_pct - account.drawdown_pct),
            ) if account.drawdown_pct < p.drawdown_kill_pct else 0.0
            risk = min(risk, remaining_daily, remaining_drawdown)
        if analysis.risk_modifier == "REDUCE":
            risk *= p.reduced_risk_fraction
        leverage = p.configured_leverage
        symbol_used = account.symbol_exposure_usdt if account else 0.0
        portfolio_used = account.portfolio_exposure_usdt if account else 0.0
        margin_used = account.margin_used_usdt if account else 0.0
        notional = max(0.0, min(
            risk / loss_rate,
            p.max_notional_usdt,
            equity * p.max_symbol_exposure_pct - symbol_used,
            equity * p.max_portfolio_exposure_pct - portfolio_used,
            (equity * p.max_margin_utilization - margin_used) * leverage,
            (case.liquidity_usdt or 0) * p.max_liquidity_fraction,
        ))
        notional = math.floor(notional * 100) / 100
        if notional == 0 and not reasons:
            reasons.append("EXPOSURE_CAP")
        if reasons:
            notional = 0.0
            risk = 0.0
        hashes = analysis_result_hashes or (analysis.result_hash,)
        if analysis.result_hash not in hashes:
            raise ValueError("selected analysis hash missing")
        proposal_id = content_hash({
            "case": case.case_hash, "analyses": hashes, "policy": p.policy_hash, "now": now_ms,
        })
        return TradeProposalV1.build(
            proposal_id=proposal_id, case_id=case.case_id, case_hash=case.case_hash,
            analysis_result_hashes=hashes, risk_policy_hash=p.policy_hash,
            symbol=case.symbol, action=analysis.action, entry_low=case.entry_low,
            entry_high=case.entry_high, stop_loss=case.stop_loss,
            take_profit_1=case.take_profit_1, take_profit_2=case.take_profit_2,
            risk_budget_usdt=risk, recommended_notional_usdt=notional,
            margin_usdt=notional / leverage, leverage=leverage,
            fee_estimate_usdt=notional * p.round_trip_fee_bps / 10000,
            slippage_estimate_usdt=notional * p.slippage_bps / 10000,
            funding_estimate_usdt=notional * funding_rate, max_loss_usdt=notional * loss_rate,
            created_at_ms=now_ms,
            expires_at_ms=min(case.expires_at_ms, now_ms + p.proposal_ttl_ms),
            allowed_price_drift_bps=p.allowed_price_drift_bps,
            requires_manual_review=(requires_manual_review or analysis.requires_manual_review
                                    or analysis.action == "ADD" or bool(reasons)),
            blocked_reasons=tuple(reasons),
        )
