from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from ..domain import Direction


class ExecutionMode(StrEnum):
    DISABLED = "disabled"
    PAPER = "paper"
    TESTNET = "testnet"
    LIVE = "live"


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    signal_id: str
    symbol: str
    direction: Direction
    mode: ExecutionMode
    order_type: str
    quantity: float
    entry_price: float
    stop_price: float
    take_profit_price: float
    notional_usdt: float
    leverage: int
    validation_status: str
    created_at_ms: int
    expires_at_ms: int
    signal_expires_at_ms: int
    plan_hash: str

    def unsigned_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["direction"] = self.direction.value
        payload["mode"] = self.mode.value
        payload.pop("plan_hash", None)
        return payload

    def calculated_hash(self) -> str:
        canonical = json.dumps(self.unsigned_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "plan_hash": self.plan_hash}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ExecutionPlan:
        values = dict(payload)
        values["direction"] = Direction(values["direction"])
        values["mode"] = ExecutionMode(values["mode"])
        return cls(**values)


@dataclass(frozen=True)
class ClosePlan:
    plan_id: str
    symbol: str
    mode: ExecutionMode
    side: str
    quantity: float
    created_at_ms: int
    expires_at_ms: int
    plan_hash: str

    def unsigned_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload.pop("plan_hash", None)
        return payload

    def calculated_hash(self) -> str:
        canonical = json.dumps(self.unsigned_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {**self.unsigned_dict(), "plan_hash": self.plan_hash}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ClosePlan:
        values = dict(payload)
        values["mode"] = ExecutionMode(values["mode"])
        return cls(**values)


@dataclass(frozen=True)
class OrderReceipt:
    plan_id: str
    role: str
    order_id: str
    status: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
