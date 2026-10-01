"""Data models for lightweight Live V1 market stream."""

from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import Field, ValidationInfo, model_validator

from ..decision.models import ImmutableModel, content_hash


class MarketObservationV1(ImmutableModel):
    symbol: str
    mark_price: Annotated[float, Field(gt=0)]
    best_bid: Annotated[float, Field(gt=0)]
    best_ask: Annotated[float, Field(gt=0)]
    kline_1m_close: Annotated[float, Field(gt=0)]
    kline_1m_open_time_ms: Annotated[int, Field(ge=0)]
    kline_1m_close_time_ms: Annotated[int, Field(ge=0)]
    source_timestamp_ms: Annotated[int, Field(ge=0)]
    receipt_timestamp_ms: Annotated[int, Field(ge=0)]
    spread_bps: Annotated[float, Field(ge=0)]
    observation_hash: str = ""

    @model_validator(mode="after")
    def validate_identity(self, info: ValidationInfo) -> Self:
        if self.best_bid > self.best_ask:
            raise ValueError("best_bid exceeds best_ask")
        expected = content_hash(self.model_dump(mode="json", exclude={"observation_hash"}))
        if info.context and info.context.get("build") and not self.observation_hash:
            object.__setattr__(self, "observation_hash", expected)
        elif self.observation_hash != expected:
            raise ValueError("market observation hash mismatch")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        return cls.model_validate(values, context={"build": True})

    def is_stale(self, now_ms: int, max_age_ms: int = 10_000) -> bool:
        return (now_ms - self.receipt_timestamp_ms) > max_age_ms
