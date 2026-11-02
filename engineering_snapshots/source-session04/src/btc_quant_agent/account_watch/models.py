from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from ..decision.models import AccountContextV1, ImmutableModel, content_hash

Nonnegative = Annotated[float, Field(ge=0)]


class PositionV1(ImmutableModel):
    symbol: str
    quantity: float
    entry_price: Nonnegative
    mark_price: Nonnegative
    unrealized_pnl_usdt: float
    leverage: Annotated[int, Field(ge=1)]
    liquidation_price: Nonnegative | None
    margin_type: str
    observed_at_ms: Annotated[int, Field(ge=0)]


OrderSide = Literal["BUY", "SELL"]
OrderStatus = Literal["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "REJECTED"]


class OrderV1(ImmutableModel):
    symbol: str
    order_id: str
    client_order_id: str
    side: OrderSide
    status: OrderStatus
    order_type: str
    quantity: Nonnegative
    filled_quantity: Nonnegative
    price: Nonnegative
    average_price: Nonnegative
    reduce_only: bool
    stop_price: Nonnegative | None
    observed_at_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_fill(self) -> Self:
        if self.filled_quantity > self.quantity:
            raise ValueError("filled quantity exceeds order quantity")
        return self


class AccountSnapshotV1(ImmutableModel):
    schema_version: Literal["ACCOUNT_SNAPSHOT_V1"] = "ACCOUNT_SNAPSHOT_V1"
    snapshot_hash: str = ""
    account_id: Annotated[str, Field(min_length=1, max_length=128)]
    environment: Literal["DRY_RUN", "TESTNET"]
    credential_namespace: Literal["NONE", "BINANCE_TESTNET"]
    rest_base_url: str
    observed_at_ms: Annotated[int, Field(ge=0)]
    last_rest_at_ms: Annotated[int, Field(ge=0)]
    stream_connected: bool
    reconciled: bool
    conflict_count: Annotated[int, Field(ge=0)]
    equity_usdt: Nonnegative
    available_balance_usdt: Nonnegative
    wallet_balance_usdt: Nonnegative
    margin_used_usdt: Nonnegative
    daily_loss_usdt: Nonnegative
    drawdown_pct: Annotated[float, Field(ge=0, le=1)]
    peak_equity_usdt: Nonnegative
    positions: tuple[PositionV1, ...]
    orders: tuple[OrderV1, ...]
    quality: Literal["OK", "STALE", "CONFLICT"]

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        if self.environment == "TESTNET":
            if (self.credential_namespace != "BINANCE_TESTNET"
                    or self.rest_base_url.rstrip("/") != "https://testnet.binancefuture.com"):
                raise ValueError("testnet account authority mismatch")
        elif self.credential_namespace != "NONE":
            raise ValueError("dry-run account must have no credential namespace")
        if self.last_rest_at_ms > self.observed_at_ms:
            raise ValueError("account chronology invalid")
        expected = content_hash(self.model_dump(mode="json", exclude={"snapshot_hash"}))
        if info.context and info.context.get("build") and not self.snapshot_hash:
            object.__setattr__(self, "snapshot_hash", expected)
        elif self.snapshot_hash != expected:
            raise ValueError("account snapshot hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})

    def verify(self) -> None:
        self.model_validate_json(self.canonical_json())

    def account_context(
        self, symbol: str, prior_signal_identities: tuple[str, ...] = (),
        prior_evidence_ids: tuple[str, ...] = (),
    ) -> AccountContextV1:
        self.verify()
        if self.quality != "OK" or not self.reconciled:
            raise ValueError("account snapshot is not reconciled")
        return AccountContextV1(
            equity_usdt=self.equity_usdt,
            symbol_exposure_usdt=sum(abs(p.quantity * p.mark_price) for p in self.positions if p.symbol == symbol),
            portfolio_exposure_usdt=sum(abs(p.quantity * p.mark_price) for p in self.positions),
            margin_used_usdt=self.margin_used_usdt,
            simultaneous_positions=sum(p.quantity != 0 for p in self.positions),
            daily_loss_usdt=self.daily_loss_usdt,
            drawdown_pct=self.drawdown_pct,
            observed_at_ms=self.observed_at_ms,
            prior_signal_identities=prior_signal_identities,
            prior_evidence_ids=prior_evidence_ids,
        )
