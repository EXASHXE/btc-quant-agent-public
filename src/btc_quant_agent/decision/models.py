from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
Action = Literal[
    "NO_ACTION", "OPEN_LONG", "OPEN_SHORT", "HOLD", "REDUCE", "CLOSE", "ADD",
    "MOVE_STOP", "TAKE_PARTIAL", "PAUSE_GRID", "GRID_REVIEW",
]
RiskModifier = Literal["BLOCK", "REDUCE", "STANDARD"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    def canonical_json(self) -> str:
        return canonical_json(self.model_dump(mode="json"))


class AccountContextV1(ImmutableModel):
    equity_usdt: Positive
    symbol_exposure_usdt: Nonnegative
    portfolio_exposure_usdt: Nonnegative
    margin_used_usdt: Nonnegative
    simultaneous_positions: Annotated[int, Field(ge=0)]
    daily_loss_usdt: Nonnegative
    drawdown_pct: Annotated[float, Field(ge=0, le=1)]
    observed_at_ms: Annotated[int, Field(ge=0)]
    prior_signal_identities: tuple[str, ...] = ()
    prior_evidence_ids: tuple[str, ...] = ()


class CalibrationV1(ImmutableModel):
    authority_hash: Hash
    authoritative: Literal[True]
    p_win: Annotated[float, Field(ge=0, le=1)]
    expected_r: float


class CasePackageV1(ImmutableModel):
    schema_version: Literal["CASE_PACKAGE_V1"] = "CASE_PACKAGE_V1"
    case_id: Annotated[str, Field(min_length=1, max_length=128)]
    case_hash: str = ""
    created_at_ms: Annotated[int, Field(ge=0)]
    observed_at_ms: Annotated[int, Field(ge=0)]
    expires_at_ms: Annotated[int, Field(gt=0)]
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9]{3,20}$")]
    trigger: str
    strategy: str
    strategy_version: str
    direction: Literal["LONG", "SHORT", "WAIT"]
    evidence_id: Hash
    snapshot_hash: Annotated[str, Field(min_length=1)]
    signal_identity: Annotated[str, Field(min_length=1)]
    source: Literal["MARKET_WATCH", "POSITION_SUPERVISOR"] = "MARKET_WATCH"
    source_receipts: tuple[tuple[str, int], ...] = ()
    base_case_hash: Hash | None = None
    position_event_hash: Hash | None = None
    price: Positive
    entry_low: Nonnegative
    entry_high: Nonnegative
    stop_loss: Nonnegative
    take_profit_1: Nonnegative
    take_profit_2: Nonnegative
    supports: tuple[float, ...] = ()
    resistances: tuple[float, ...] = ()
    atr: Nonnegative
    volatility_percentile: float | None = None
    volume: Nonnegative = 0.0
    regime_15m: str = "UNKNOWN"
    regime_1h: str = "UNKNOWN"
    regime_4h: str = "UNKNOWN"
    funding_rate: float | None = None
    open_interest: float | None = None
    oi_1h_change: float | None = None
    oi_4h_change: float | None = None
    oi_12h_change: float | None = None
    basis_rate: float | None = None
    taker_ratio: float | None = None
    global_account_ratio: float | None = None
    top_trader_position_ratio: float | None = None
    top_trader_account_ratio: float | None = None
    spread_bps: Nonnegative | None = None
    book_imbalance: float | None = None
    liquidity_usdt: Nonnegative | None = None
    liquidity_measure: Literal["UNKNOWN", "QUOTE_VOLUME_24H_PROXY", "ORDER_BOOK_DEPTH"] = "UNKNOWN"
    reason_codes: tuple[str, ...] = ()
    risk_codes: tuple[str, ...] = ()
    veto_reasons: tuple[str, ...] = ()
    entry_quality: str = "UNKNOWN"
    grid_state: str = "UNKNOWN"
    calibration: CalibrationV1 | None = None
    account: AccountContextV1 | None = None
    data_quality: Literal["OK", "DEGRADED", "FAILED"]
    missing_fields: tuple[str, ...] = ()
    source_errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        if not self.observed_at_ms <= self.created_at_ms < self.expires_at_ms:
            raise ValueError("invalid case chronology")
        if self.entry_low > self.entry_high:
            raise ValueError("invalid entry range")
        expected = content_hash(self.model_dump(mode="json", exclude={"case_hash"}))
        if info.context and info.context.get("build") and not self.case_hash:
            object.__setattr__(self, "case_hash", expected)
        elif self.case_hash != expected:
            raise ValueError("case hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})

    def verify(self) -> None:
        self.model_validate_json(self.canonical_json())


class AnalysisResultV1(ImmutableModel):
    backend: str
    model: str
    provider_request_id: str | None
    case_id: str
    case_hash: Hash
    action: Action
    confidence: Annotated[float, Field(ge=0, le=1)]
    entry_quality: str
    thesis_strength: Annotated[float, Field(ge=0, le=1)]
    supporting_factors: tuple[str, ...]
    risk_factors: tuple[str, ...]
    invalidation_factors: tuple[str, ...]
    risk_modifier: RiskModifier
    requires_secondary_review: bool
    requires_manual_review: bool
    strategy_data_disagreement: bool
    narrative: Annotated[str, Field(max_length=6000)]

    @property
    def result_hash(self) -> str:
        return content_hash(self.model_dump(mode="json"))

    def verify_case(self, case: CasePackageV1) -> None:
        self.model_validate_json(self.canonical_json())
        if self.case_hash != case.case_hash or self.case_id != case.case_id:
            raise ValueError("analysis case identity mismatch")

    @classmethod
    def fail_closed(cls, case: CasePackageV1, backend: str, model: str,
                    reason: str) -> Self:
        return cls(
            backend=backend, model=model, provider_request_id=None, case_id=case.case_id,
            case_hash=case.case_hash, action="NO_ACTION", confidence=0.0,
            entry_quality="UNKNOWN", thesis_strength=0.0, supporting_factors=(),
            risk_factors=(reason,), invalidation_factors=(), risk_modifier="BLOCK",
            requires_secondary_review=False, requires_manual_review=True,
            strategy_data_disagreement=False, narrative=reason,
        )


class TradeProposalV1(ImmutableModel):
    schema_version: Literal["TRADE_PROPOSAL_V1"] = "TRADE_PROPOSAL_V1"
    proposal_id: str
    proposal_hash: str = ""
    case_id: str
    case_hash: Hash
    analysis_result_hashes: tuple[Hash, ...]
    risk_policy_hash: Hash
    symbol: str
    action: Action
    account_authority: Literal["DRY_RUN"] = "DRY_RUN"
    entry_low: Nonnegative
    entry_high: Nonnegative
    stop_loss: Nonnegative
    take_profit_1: Nonnegative
    take_profit_2: Nonnegative
    risk_budget_usdt: Nonnegative
    recommended_notional_usdt: Nonnegative
    margin_usdt: Nonnegative
    leverage: Annotated[int, Field(ge=1)]
    fee_estimate_usdt: Nonnegative
    slippage_estimate_usdt: Nonnegative
    funding_estimate_usdt: Nonnegative
    max_loss_usdt: Nonnegative
    created_at_ms: int
    expires_at_ms: int
    allowed_price_drift_bps: Nonnegative
    requires_manual_review: bool
    blocked_reasons: tuple[str, ...]

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        expected = content_hash(self.model_dump(mode="json", exclude={"proposal_hash"}))
        if info.context and info.context.get("build") and not self.proposal_hash:
            object.__setattr__(self, "proposal_hash", expected)
        elif self.proposal_hash != expected:
            raise ValueError("proposal hash mismatch")
        if self.created_at_ms >= self.expires_at_ms:
            raise ValueError("invalid proposal chronology")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})

    def verify(self) -> None:
        self.model_validate_json(self.canonical_json())
