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
    rounded_rr_net: float
    estimated_max_loss_usdt: float
    plan_hash: str
    execution_environment_id: str = "local_paper"
    credential_namespace_id: str = "NONE"
    account_authority_id: str = "DEFAULT_PAPER_ACCOUNT"

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
        values.setdefault("rounded_rr_net", 0.0)
        values.setdefault("estimated_max_loss_usdt", 0.0)
        values["direction"] = Direction(values["direction"])
        mode = ExecutionMode(values["mode"])
        values["mode"] = mode
        if "execution_environment_id" not in values:
            if mode == ExecutionMode.PAPER:
                values["execution_environment_id"] = "local_paper"
                values["credential_namespace_id"] = "NONE"
                values["account_authority_id"] = "DEFAULT_PAPER_ACCOUNT"
            else:
                values["execution_environment_id"] = ""
                values["credential_namespace_id"] = ""
                values["account_authority_id"] = ""
        else:
            values.setdefault("credential_namespace_id", "NONE" if mode == ExecutionMode.PAPER else "")
            values.setdefault("account_authority_id", "DEFAULT_PAPER_ACCOUNT" if mode == ExecutionMode.PAPER else "")
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
    execution_environment_id: str = "local_paper"
    credential_namespace_id: str = "NONE"
    account_authority_id: str = "DEFAULT_PAPER_ACCOUNT"

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
        mode = ExecutionMode(values["mode"])
        values["mode"] = mode
        if "execution_environment_id" not in values:
            if mode == ExecutionMode.PAPER:
                values["execution_environment_id"] = "local_paper"
                values["credential_namespace_id"] = "NONE"
                values["account_authority_id"] = "DEFAULT_PAPER_ACCOUNT"
            else:
                values["execution_environment_id"] = ""
                values["credential_namespace_id"] = ""
                values["account_authority_id"] = ""
        else:
            values.setdefault("credential_namespace_id", "NONE" if mode == ExecutionMode.PAPER else "")
            values.setdefault("account_authority_id", "DEFAULT_PAPER_ACCOUNT" if mode == ExecutionMode.PAPER else "")
        return cls(**values)


@dataclass(frozen=True)
class OrderReceipt:
    plan_id: str
    role: str
    order_id: str
    status: str
    raw: dict[str, Any]
    plan_hash: str = ""
    mode: ExecutionMode = ExecutionMode.PAPER
    execution_environment_id: str = "local_paper"
    credential_namespace_id: str = "NONE"
    account_authority_id: str = "DEFAULT_PAPER_ACCOUNT"
    symbol: str = "BTCUSDT"
    submitted_at_ms: int = 0
    client_order_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value if isinstance(self.mode, ExecutionMode) else str(self.mode)
        payload["exchange_order_id"] = self.order_id
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> OrderReceipt:
        values = dict(payload)
        mode_val = values.get("mode", "paper")
        mode = ExecutionMode(mode_val) if isinstance(mode_val, str) else mode_val
        values["mode"] = mode
        if "order_id" not in values and "exchange_order_id" in values:
            values["order_id"] = values["exchange_order_id"]
        values.setdefault("raw", {})
        values.setdefault("status", "NEW")
        if "execution_environment_id" not in values:
            if mode == ExecutionMode.PAPER:
                values.setdefault("execution_environment_id", "local_paper")
                values.setdefault("credential_namespace_id", "NONE")
                values.setdefault("account_authority_id", "DEFAULT_PAPER_ACCOUNT")
                values.setdefault("symbol", "BTCUSDT")
            else:
                values.setdefault("execution_environment_id", "")
                values.setdefault("credential_namespace_id", "")
                values.setdefault("account_authority_id", "")
                values.setdefault("symbol", "")
        values.setdefault("plan_hash", "")
        values.setdefault("submitted_at_ms", 0)
        values.setdefault("client_order_id", "")
        valid_keys = {
            "plan_id",
            "role",
            "order_id",
            "status",
            "raw",
            "plan_hash",
            "mode",
            "execution_environment_id",
            "credential_namespace_id",
            "account_authority_id",
            "symbol",
            "submitted_at_ms",
            "client_order_id",
        }
        filtered = {k: v for k, v in values.items() if k in valid_keys}
        return cls(**filtered)
