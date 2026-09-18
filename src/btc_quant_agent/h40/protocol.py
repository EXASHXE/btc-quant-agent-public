"""H40 Protocol Identity definition and canonical hashing.

Binds immutable preregistration metadata under schema H40_PROTOCOL_V1_R3.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..research_contract.canonical import (
    FrozenDict,
    canonical_json,
    canonical_sha256,
    thaw_json,
)

SCHEMA_NAME: str = "H40_PROTOCOL_V1_R3"
FROZEN_KERNEL_SHA: str = "6838e9db8d5c369b5da87354821d9c8e79c2a879"
BASE_PREREG_COMMIT: str = "8b36cfde2ac14a37ed4eb244a8b5ae88882765b4"
AMENDMENT_R1_COMMIT: str = "59e9fe0ba361557c5df56f0d8f8afaa781cf0071"
AMENDMENT_R2_COMMIT: str = "4bdeb1a0102b3cb374e8ec7d01b41a79dcc8b021"
SOL_ACCEPTANCE_COMMIT: str = "b9c8531e719fd4f10cf27301719c9e066b95be13"
P1_CODE_BASELINE_COMMIT: str = "3fc89541ed0965fc0e2972af310e34ae1b838168"
P1_FINAL_ACCEPTANCE_COMMIT: str = "95ab819d5300312b4d493b9585b4b369621504b6"
R3_AMENDMENT_COMMIT: str = "e45899bb0118b14127bc765f49315109cfd94ff0"
R3R1_AMENDMENT_COMMIT: str = "3f1bf28dc810ca4fd1bfd2bef566033cd15550fa"
R3R2_AMENDMENT_COMMIT: str = "77601342ac9055b5c0bb47639d4c8ef7d83da154"
R3R3_AMENDMENT_COMMIT: str = "f01062b4b1a20d12f93ee1351bfda67e19401f25"
R3R4_AMENDMENT_COMMIT: str = "7520a62d0516ee097c276451b9f8df5924c6408f"
R3R4_ACCEPTANCE_COMMIT: str = "cf69d5295e2b0227920e265d9afe7dcf831af44e"

PRODUCTS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
CADENCE: str = "1h"
PRIMARY_HORIZONS: tuple[str, ...] = ("4h", "8h", "12h")
DIAGNOSTIC_HORIZONS: tuple[str, ...] = ("24h",)
SEARCH_BUDGET: int = 168
CONFIRMATION_INTERVAL: dict[str, str] = {
    "start_utc": "2025-02-01T00:00:00Z",
    "end_utc": "2026-02-01T00:00:00Z",
}
COST_PROXY_BPS: int = 12
ACTION_SPACE: tuple[str, ...] = ("LONG", "SHORT", "NO_TRADE")
DEFAULT_ACTION: str = "NO_TRADE"


@dataclass(frozen=True)
class H40ProtocolIdentity:
    """Immutable protocol identity specification for H40."""

    schema_name: str
    frozen_kernel_sha: str
    base_prereg_commit: str
    amendment_r1_commit: str
    amendment_r2_commit: str
    sol_acceptance_commit: str
    products: tuple[str, ...]
    cadence: str
    primary_horizons: tuple[str, ...]
    diagnostic_horizons: tuple[str, ...]
    search_budget: int
    confirmation_interval: FrozenDict
    cost_proxy_bps: int
    action_space: tuple[str, ...]
    default_action: str

    def __init__(
        self,
        schema_name: str = SCHEMA_NAME,
        frozen_kernel_sha: str = FROZEN_KERNEL_SHA,
        base_prereg_commit: str = BASE_PREREG_COMMIT,
        amendment_r1_commit: str = AMENDMENT_R1_COMMIT,
        amendment_r2_commit: str = AMENDMENT_R2_COMMIT,
        sol_acceptance_commit: str = SOL_ACCEPTANCE_COMMIT,
        products: tuple[str, ...] | list[str] = PRODUCTS,
        cadence: str = CADENCE,
        primary_horizons: tuple[str, ...] | list[str] = PRIMARY_HORIZONS,
        diagnostic_horizons: tuple[str, ...] | list[str] = DIAGNOSTIC_HORIZONS,
        search_budget: int = SEARCH_BUDGET,
        confirmation_interval: Mapping[str, str] | None = None,
        cost_proxy_bps: int = COST_PROXY_BPS,
        action_space: tuple[str, ...] | list[str] = ACTION_SPACE,
        default_action: str = DEFAULT_ACTION,
    ) -> None:
        object.__setattr__(self, "schema_name", schema_name)
        object.__setattr__(self, "frozen_kernel_sha", frozen_kernel_sha)
        object.__setattr__(self, "base_prereg_commit", base_prereg_commit)
        object.__setattr__(self, "amendment_r1_commit", amendment_r1_commit)
        object.__setattr__(self, "amendment_r2_commit", amendment_r2_commit)
        object.__setattr__(self, "sol_acceptance_commit", sol_acceptance_commit)
        object.__setattr__(self, "products", tuple(products))
        object.__setattr__(self, "cadence", cadence)
        object.__setattr__(self, "primary_horizons", tuple(primary_horizons))
        object.__setattr__(self, "diagnostic_horizons", tuple(diagnostic_horizons))
        object.__setattr__(self, "search_budget", int(search_budget))
        c_interval = (
            dict(confirmation_interval)
            if confirmation_interval is not None
            else dict(CONFIRMATION_INTERVAL)
        )
        object.__setattr__(self, "confirmation_interval", FrozenDict(c_interval))
        object.__setattr__(self, "cost_proxy_bps", int(cost_proxy_bps))
        object.__setattr__(self, "action_space", tuple(action_space))
        object.__setattr__(self, "default_action", default_action)

    @classmethod
    def default(cls) -> H40ProtocolIdentity:
        """Returns the canonical preregistered H40 protocol identity."""
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Serializes the protocol identity to a standard dictionary."""
        return {
            "schema_name": self.schema_name,
            "frozen_kernel_sha": self.frozen_kernel_sha,
            "base_prereg_commit": self.base_prereg_commit,
            "amendment_r1_commit": self.amendment_r1_commit,
            "amendment_r2_commit": self.amendment_r2_commit,
            "sol_acceptance_commit": self.sol_acceptance_commit,
            "products": list(self.products),
            "cadence": self.cadence,
            "primary_horizons": list(self.primary_horizons),
            "diagnostic_horizons": list(self.diagnostic_horizons),
            "search_budget": self.search_budget,
            "confirmation_interval": thaw_json(self.confirmation_interval),
            "cost_proxy_bps": self.cost_proxy_bps,
            "action_space": list(self.action_space),
            "default_action": self.default_action,
        }

    def canonical_json(self) -> str:
        """Returns deterministic RFC-8259 canonical JSON representation."""
        return canonical_json(self.to_dict())

    @property
    def protocol_hash(self) -> str:
        """Returns SHA-256 hash over canonical JSON identity."""
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ProtocolIdentity:
        """Deserializes from a mapping preserving canonical identity."""
        return cls(
            schema_name=str(data["schema_name"]),
            frozen_kernel_sha=str(data["frozen_kernel_sha"]),
            base_prereg_commit=str(data["base_prereg_commit"]),
            amendment_r1_commit=str(data["amendment_r1_commit"]),
            amendment_r2_commit=str(data["amendment_r2_commit"]),
            sol_acceptance_commit=str(data["sol_acceptance_commit"]),
            products=tuple(data["products"]),
            cadence=str(data["cadence"]),
            primary_horizons=tuple(data["primary_horizons"]),
            diagnostic_horizons=tuple(data["diagnostic_horizons"]),
            search_budget=int(data["search_budget"]),
            confirmation_interval=data["confirmation_interval"],
            cost_proxy_bps=int(data["cost_proxy_bps"]),
            action_space=tuple(data["action_space"]),
            default_action=str(data["default_action"]),
        )
