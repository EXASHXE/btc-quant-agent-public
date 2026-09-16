"""168-slot configuration ledger scaffold for H40.

Enforces strict D1–D5 family authority, depth-two pair restrictions,
and an append-only, content-addressed 168-slot budget cap under H40_PROTOCOL_V1_R2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from ..research_contract.canonical import (
    FrozenDict,
    canonical_json,
    canonical_sha256,
    thaw_json,
)
from .guards import H40GuardError, H40ReasonCode

MAX_CONFIGURATION_SLOTS: int = 168
ALLOWED_PRIMARY_HORIZONS: frozenset[str] = frozenset({"4h", "8h", "12h"})
ALLOWED_ACTION_THRESHOLDS: frozenset[float] = frozenset({0.55, 0.60, 0.65})
ALLOWED_ASSETS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT"})
FORBIDDEN_PERF_KEYS: frozenset[str] = frozenset({
    "sharpe",
    "profit_factor",
    "return",
    "pnl",
    "drawdown",
    "win_rate",
    "trades",
    "cagr",
    "sortino",
    "calmar",
    "alpha",
})


class H40Family(str, Enum):
    """Authorized candidate direction families from BASE Section 5.3."""

    D1_TREND_CONTINUATION = "D1_TREND_CONTINUATION"
    D2_BREAKOUT_CONTINUATION = "D2_BREAKOUT_CONTINUATION"
    D3_FAILED_MOVE_REVERSAL = "D3_FAILED_MOVE_REVERSAL"
    D4_BTC_ETH_CONFIRM_DIVERGE = "D4_BTC_ETH_CONFIRM_DIVERGE"
    D5_FUNDING_DIRECTION_INTERACTION = "D5_FUNDING_DIRECTION_INTERACTION"


# Exactly the 4 authorized depth-two combinations
ALLOWED_DEPTH_TWO_PAIRS: frozenset[frozenset[H40Family]] = frozenset({
    frozenset({H40Family.D1_TREND_CONTINUATION, H40Family.D4_BTC_ETH_CONFIRM_DIVERGE}),
    frozenset({H40Family.D1_TREND_CONTINUATION, H40Family.D5_FUNDING_DIRECTION_INTERACTION}),
    frozenset({H40Family.D2_BREAKOUT_CONTINUATION, H40Family.D4_BTC_ETH_CONFIRM_DIVERGE}),
    frozenset({H40Family.D3_FAILED_MOVE_REVERSAL, H40Family.D5_FUNDING_DIRECTION_INTERACTION}),
})


@dataclass(frozen=True)
class H40ConfigurationSlot:
    """Pre-outcome specification and identity for a candidate configuration."""

    slot_index: int
    family_combination: tuple[H40Family, ...]
    asset_scope: tuple[str, ...]
    primary_horizon: str
    action_threshold: float
    hyperparameters: FrozenDict
    status: str = "REGISTERED"
    reason_code: H40ReasonCode | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        # Validate families
        if not self.family_combination:
            raise H40GuardError(
                H40ReasonCode.UNAUTHORIZED_FAMILY,
                "Configuration must specify at least one direction family.",
            )

        for fam in self.family_combination:
            if not isinstance(fam, H40Family):
                raise H40GuardError(
                    H40ReasonCode.UNAUTHORIZED_FAMILY,
                    f"Unauthorized family '{fam}'. Must be one of D1..D5.",
                )

        depth = len(self.family_combination)
        if depth == 1:
            pass  # Single family in D1..D5 is authorized
        elif depth == 2:
            pair = frozenset(self.family_combination)
            if pair not in ALLOWED_DEPTH_TWO_PAIRS:
                names = "+".join(f.name for f in self.family_combination)
                raise H40GuardError(
                    H40ReasonCode.FAMILY_PAIR_RESTRICTED,
                    f"Depth-two combination '{names}' is not authorized. Allowed pairs: D1+D4, D1+D5, D2+D4, D3+D5.",
                )
        else:
            raise H40GuardError(
                H40ReasonCode.FAMILY_PAIR_RESTRICTED,
                f"Configuration depth {depth} exceeds authorized maximum depth 2.",
            )

        # Validate primary horizon
        if self.primary_horizon not in ALLOWED_PRIMARY_HORIZONS:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"Primary horizon '{self.primary_horizon}' invalid. Must be one of {sorted(ALLOWED_PRIMARY_HORIZONS)}.",
            )

        # Validate action threshold
        # Account for potential float representation differences
        matched_threshold = False
        for allowed in ALLOWED_ACTION_THRESHOLDS:
            if abs(self.action_threshold - allowed) < 1e-6:
                matched_threshold = True
                break
        if not matched_threshold:
            raise H40GuardError(
                H40ReasonCode.THRESHOLD_UNMET,
                f"Action threshold {self.action_threshold} invalid. Must be one of {sorted(ALLOWED_ACTION_THRESHOLDS)}.",
            )

        # Validate asset scope
        if not self.asset_scope:
            raise H40GuardError(
                H40ReasonCode.PRODUCT_MISMATCH,
                "Asset scope cannot be empty.",
            )
        for asset in self.asset_scope:
            if asset not in ALLOWED_ASSETS:
                raise H40GuardError(
                    H40ReasonCode.PRODUCT_MISMATCH,
                    f"Asset '{asset}' outside authorized scope {sorted(ALLOWED_ASSETS)}.",
                )

        # Validate hyperparameters for forbidden performance/outcome keys
        for key in self.hyperparameters:
            if key.lower() in FORBIDDEN_PERF_KEYS:
                raise H40GuardError(
                    H40ReasonCode.PROTECTED_SURFACE_DENIED,
                    f"Forbidden outcome or performance metric '{key}' in pre-outcome hyperparameters.",
                )

    @property
    def config_id(self) -> str:
        """Returns deterministic content-addressed identifier for the configuration."""
        semantic_payload = {
            "family_combination": [f.value for f in self.family_combination],
            "asset_scope": list(self.asset_scope),
            "primary_horizon": self.primary_horizon,
            "action_threshold": round(self.action_threshold, 4),
            "hyperparameters": thaw_json(self.hyperparameters),
        }
        return canonical_sha256(semantic_payload)

    def to_dict(self) -> dict[str, Any]:
        """Serializes slot to dictionary."""
        return {
            "slot_index": self.slot_index,
            "config_id": self.config_id,
            "family_combination": [f.value for f in self.family_combination],
            "asset_scope": list(self.asset_scope),
            "primary_horizon": self.primary_horizon,
            "action_threshold": self.action_threshold,
            "hyperparameters": thaw_json(self.hyperparameters),
            "status": self.status,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "notes": self.notes,
        }

    @classmethod
    def create(
        cls,
        slot_index: int,
        family_combination: tuple[H40Family, ...] | list[H40Family],
        asset_scope: tuple[str, ...] | list[str],
        primary_horizon: str,
        action_threshold: float,
        hyperparameters: Mapping[str, Any] | None = None,
        status: str = "REGISTERED",
        reason_code: H40ReasonCode | None = None,
        notes: str = "",
    ) -> H40ConfigurationSlot:
        """Factory creating a slot with frozen hyperparameters."""
        frozen_params = FrozenDict(hyperparameters or {})
        return cls(
            slot_index=slot_index,
            family_combination=tuple(family_combination),
            asset_scope=tuple(asset_scope),
            primary_horizon=primary_horizon,
            action_threshold=action_threshold,
            hyperparameters=frozen_params,
            status=status,
            reason_code=reason_code,
            notes=notes,
        )


class H40ConfigurationLedger:
    """Content-addressed append-only configuration ledger capped at 168 slots."""

    MAX_CAPACITY: ClassVar[int] = MAX_CONFIGURATION_SLOTS

    def __init__(self) -> None:
        self._slots: list[H40ConfigurationSlot] = []
        self._id_to_index: dict[str, int] = {}

    @property
    def slots(self) -> tuple[H40ConfigurationSlot, ...]:
        return tuple(self._slots)

    @property
    def slot_count(self) -> int:
        return len(self._slots)

    @property
    def remaining_budget(self) -> int:
        return self.MAX_CAPACITY - len(self._slots)

    def register_slot(self, slot: H40ConfigurationSlot) -> int:
        """Appends a new configuration slot to the ledger.

        Enforces strict capacity of 168 slots and detects configuration identity conflicts.
        """
        if len(self._slots) >= self.MAX_CAPACITY:
            raise H40GuardError(
                H40ReasonCode.SEARCH_BUDGET_EXHAUSTED,
                f"Cannot register slot: search budget exhausted ({self.MAX_CAPACITY}/{self.MAX_CAPACITY} consumed).",
            )

        if slot.slot_index != len(self._slots):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"Slot index {slot.slot_index} does not match current append position {len(self._slots)}.",
            )

        cid = slot.config_id
        if cid in self._id_to_index:
            existing_idx = self._id_to_index[cid]
            existing_slot = self._slots[existing_idx]
            if existing_slot.to_dict() != slot.to_dict():
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"Conflicting payload for existing configuration ID {cid} at slot {existing_idx}.",
                )
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                f"Duplicate registration of config ID {cid} at slot {existing_idx}.",
            )

        assigned_index = len(self._slots)
        self._slots.append(slot)
        self._id_to_index[cid] = assigned_index
        return assigned_index

    def drop_slot(self, slot_index: int, reason_code: H40ReasonCode, notes: str = "") -> None:
        """Marks a slot as DROPPED without recycling its slot index or budget."""
        if slot_index < 0 or slot_index >= len(self._slots):
            raise IndexError(f"Slot index {slot_index} out of range (0..{len(self._slots)-1}).")

        cur = self._slots[slot_index]
        dropped_slot = H40ConfigurationSlot(
            slot_index=cur.slot_index,
            family_combination=cur.family_combination,
            asset_scope=cur.asset_scope,
            primary_horizon=cur.primary_horizon,
            action_threshold=cur.action_threshold,
            hyperparameters=cur.hyperparameters,
            status="DROPPED",
            reason_code=reason_code,
            notes=notes or cur.notes,
        )
        self._slots[slot_index] = dropped_slot

    def to_dict(self) -> dict[str, Any]:
        """Serializes ledger to dictionary."""
        return {
            "capacity": self.MAX_CAPACITY,
            "consumed": len(self._slots),
            "slots": [s.to_dict() for s in self._slots],
        }

    def canonical_json(self) -> str:
        """Returns deterministic RFC-8259 canonical JSON."""
        return canonical_json(self.to_dict())

    @property
    def ledger_hash(self) -> str:
        """Returns SHA-256 hash over canonical ledger content."""
        return canonical_sha256(self.to_dict())
