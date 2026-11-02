"""Data models for Live V1 Position Supervisor and Kill Switch."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from ..decision.models import ImmutableModel, content_hash


class SupervisorPolicyV1(ImmutableModel):
    daily_loss_cap_usdt: float = 25.0
    drawdown_cap_pct: float = 0.05
    unreconciled_timeout_ms: int = 60_000
    order_conflicts_max: int = 2
    protective_missing_grace_ms: int = 10_000
    stale_partial_fill_ms: int = 30_000
    stop_near_pct: float = 0.02
    tp_near_pct: float = 0.02
    oi_shock_pct: float = 0.20
    funding_shock_rate: float = 0.0015
    volatility_spike_percentile: float = 0.90
    liquidity_deterioration_bps: float = 10.0
    cooldown_ms: int = 60_000


class KillObservationV1(ImmutableModel):
    account_snapshot_hash: str
    environment: str
    credential_namespace: str
    rest_url: str
    observed_at_ms: Annotated[int, Field(ge=0)]
    last_reconciled_at_ms: Annotated[int, Field(ge=0)]
    reconciled: bool
    equity_usdt: float
    daily_loss_usdt: float
    drawdown_pct: float
    order_conflicts: int
    protective_missing_since_ms: int | None = None


class PositionObservationV1(ImmutableModel):
    account_snapshot_hash: str
    market_source_hash: str
    environment: Literal["DRY_RUN", "TESTNET"]
    credential_namespace: Annotated[str, Field(min_length=1)]
    symbol: str
    account_id: str = "DEFAULT_ACCOUNT"
    position_side: Literal["BOTH"] = "BOTH"
    observed_at_ms: Annotated[int, Field(ge=0)]
    quantity: float
    previous_quantity: float
    entry_price: float
    mark_price: float
    unrealized_pnl_usdt: float
    realized_pnl_usdt: float
    margin_usdt: float
    stop_price: float
    take_profit_price: float
    funding_rate: float | None = None
    oi_change_pct: float | None = None
    volatility_percentile: float | None = None
    spread_bps: float | None = None
    tactical_regime: str | None = None
    grid_boundary_breached: bool = False
    order_status: str
    order_filled_quantity: float
    order_observed_at_ms: Annotated[int, Field(ge=0)]
    evidence_id: str | None = None
    signal_identity: str | None = None
    prior_evidence_ids: tuple[str, ...] = ()
    prior_signal_identities: tuple[str, ...] = ()
    add_opportunity: bool = False
    observation_hash: str = ""

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        if (self.environment == "DRY_RUN" and self.credential_namespace != "NONE") or (
            self.environment == "TESTNET" and self.credential_namespace == "NONE"
        ):
            raise ValueError("position observation account authority mismatch")
        expected = content_hash(self.model_dump(mode="json", exclude={"observation_hash"}))
        if info is not None and info.context and info.context.get("build") and not self.observation_hash:
            object.__setattr__(self, "observation_hash", expected)
        elif self.observation_hash != expected:
            raise ValueError("observation hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})

    def verify(self) -> None:
        self.model_validate_json(self.canonical_json())


class PositionEventV1(ImmutableModel):
    schema_version: Literal["POSITION_EVENT_V1"] = "POSITION_EVENT_V1"
    event_id: str
    event_hash: str = ""
    trigger: str
    symbol: str
    source_hash: str
    environment: str | None = None
    credential_namespace: str | None = None
    account_id: str | None = None
    position_side: str | None = None
    position_authority_key: str | None = None
    observed_at_ms: Annotated[int, Field(ge=0)]
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        authority_fields = {"environment", "credential_namespace", "account_id",
                            "position_side", "position_authority_key"}
        present = [getattr(self, field) is not None for field in authority_fields]
        if any(present) and not all(present):
            raise ValueError("position event authority incomplete")
        if all(present):
            expected_key = position_authority_key(
                self.environment or "", self.credential_namespace or "",
                self.account_id or "", self.symbol, self.position_side or "")
            if self.position_authority_key != expected_key:
                raise ValueError("position event authority mismatch")
        expected = content_hash(self.model_dump(
            mode="json", exclude={"event_hash"} | (set() if all(present) else authority_fields)))
        if info.context and info.context.get("build") and not self.event_hash:
            object.__setattr__(self, "event_hash", expected)
        elif self.event_hash != expected:
            raise ValueError("event hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        required_authority = ("environment", "credential_namespace", "account_id",
                              "position_side", "position_authority_key")
        if not all(values.get(field) for field in required_authority):
            raise ValueError("position event authority incomplete")
        return cls.model_validate(values, context={"build": True})

    def verify(self) -> None:
        self.model_validate_json(self.canonical_json())


def position_authority_key(
    environment: str, credential_namespace: str, account_id: str,
    symbol: str, position_side: str,
) -> str:
    if not all((environment, credential_namespace, account_id, symbol, position_side)):
        raise ValueError("position authority incomplete")
    return content_hash({
        "environment": environment,
        "credential_namespace": credential_namespace,
        "account_id": account_id,
        "symbol": symbol,
        "position_side": position_side,
    })
