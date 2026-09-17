"""168-slot configuration ledger for H40.

Enforces strict D1–D5 family authority, depth-two pair restrictions,
and an append-only, content-addressed 168-slot budget cap under H40_PROTOCOL_V1_R2.
Binds protocol hash, source manifest hash, split manifest hash, and frozen kernel SHA.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from ..research_contract.canonical import (
    FrozenDict,
    canonical_json,
    canonical_sha256,
    thaw_json,
)
from .guards import H40GuardError, H40ProtectedSurfaceGuard, H40ReasonCode
from .protocol import (
    DEFAULT_ACTION,
    FROZEN_KERNEL_SHA,
    H40ProtocolIdentity,
)

MAX_CONFIGURATION_SLOTS: int = 168
ALLOWED_PRIMARY_HORIZONS: frozenset[str] = frozenset({"4h", "8h", "12h"})
ALLOWED_ACTION_THRESHOLDS: frozenset[float] = frozenset({0.55, 0.60, 0.65})
ALLOWED_ASSETS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT"})
ALLOWED_SCOPES: frozenset[str] = frozenset({"BTC_ONLY", "ETH_ONLY", "POOLED_BTC_ETH"})

P1_CODE_BASELINE_SHA: str = "3fc89541ed0965fc0e2972af310e34ae1b838168"
LEDGER_SCHEMA_VERSION: str = "H40_LEDGER_V1"
DEFAULT_PROTOCOL_HASH: str = H40ProtocolIdentity.default().protocol_hash

# Default reference manifest hashes (pre-outcome reference schedule)
DEFAULT_SOURCE_MANIFEST_HASH: str = "af7fe2c187dcd503ba27a3f24ba6347cb3c619a63662106e85c6343eda90a74c"
DEFAULT_SPLIT_MANIFEST_HASH: str = "6e3ed51b4139c7822343752e29b6d8b2e94f9fadf0def38f2101a444b1da62e9"

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
    "mfe",
    "mae",
    "precision",
    "expectancy",
    "brier",
    "ece",
    "p_value",
    "hac",
    "bootstrap",
    "calibration_score",
    "forward_return",
    "target_label",
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
    hyperparameters: FrozenDict = field(default_factory=FrozenDict)
    scope: str = "BTC_ONLY"
    direction_variant: str = ""
    regime_contract_id: str = "R_VOL_RANGE_V1_24H"
    opportunity_contract_id: str = "O_RANGE_EXPANSION_V1_24H"
    direction_contract_id: str = ""
    geometry_contract_id: str = "GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1"
    calibration_contract_id: str = "CALIBRATION_LOGISTIC_V1"
    abstention_policy: str = DEFAULT_ACTION
    required_feature_ids: tuple[str, ...] = ()
    feature_params: FrozenDict = field(default_factory=FrozenDict)
    lookback_windows: FrozenDict = field(default_factory=FrozenDict)
    availability_rule: str = "CLOSED_BAR_STRICT"
    cost_proxy_id: str = "COST_PROXY_12BPS_V1"
    mechanical_refit_policy: str = "REFIT_CHRONOLOGICAL_PAST_ONLY_V1"
    protocol_hash: str = DEFAULT_PROTOCOL_HASH
    source_manifest_hash: str = DEFAULT_SOURCE_MANIFEST_HASH
    split_manifest_hash: str = DEFAULT_SPLIT_MANIFEST_HASH
    ledger_schema_version: str = LEDGER_SCHEMA_VERSION
    frozen_kernel_sha: str = FROZEN_KERNEL_SHA
    p1_code_baseline_sha: str = P1_CODE_BASELINE_SHA
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

        # TP/BR cannot become directional owner
        for fam in self.family_combination:
            if "TPBR" in fam.value:
                raise H40GuardError(
                    H40ReasonCode.UNAUTHORIZED_FAMILY,
                    "TP/BR cannot become a directional owner.",
                )

        # D5 requires a base directional owner in {D1, D2, D3}
        if H40Family.D5_FUNDING_DIRECTION_INTERACTION in self.family_combination:
            if depth == 1:
                # Standalone D5 without base direction is strictly prohibited
                # Unless specified via direction_contract_id or notes indicating base owner
                base_owner = self.feature_params.get("base_directional_owner", "")
                if base_owner not in {"D1_TREND_CONTINUATION", "D2_BREAKOUT_CONTINUATION", "D3_FAILED_MOVE_REVERSAL"}:
                    raise H40GuardError(
                        H40ReasonCode.UNAUTHORIZED_FAMILY,
                        "D5 requires a base directional family in {D1, D2, D3}; funding alone is strictly non-directional.",
                    )
            elif depth == 2:
                # Pair must include D1 or D3
                other_fams = {f for f in self.family_combination if f != H40Family.D5_FUNDING_DIRECTION_INTERACTION}
                allowed_bases = {H40Family.D1_TREND_CONTINUATION, H40Family.D3_FAILED_MOVE_REVERSAL}
                if not (other_fams & allowed_bases):
                    raise H40GuardError(
                        H40ReasonCode.UNAUTHORIZED_FAMILY,
                        "D5 pair requires a base directional family in {D1, D3}.",
                    )

        # Validate primary horizon
        if self.primary_horizon not in ALLOWED_PRIMARY_HORIZONS:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"Primary horizon '{self.primary_horizon}' invalid. Must be one of {sorted(ALLOWED_PRIMARY_HORIZONS)}.",
            )

        # Validate action threshold
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

        # Validate scope
        if self.scope not in ALLOWED_SCOPES:
            raise H40GuardError(
                H40ReasonCode.PRODUCT_MISMATCH,
                f"Scope '{self.scope}' invalid. Must be one of {sorted(ALLOWED_SCOPES)}.",
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

        # Validate availability rule for strict PIT closed bar
        if "CLOSED_BAR" not in self.availability_rule and "<" not in self.availability_rule:
            raise H40GuardError(
                H40ReasonCode.PIT_UNAVAILABLE,
                f"Availability rule '{self.availability_rule}' violates strict closed-bar semantics.",
            )

        # Check protected surface locators across fields
        for field_val in (self.notes, self.regime_contract_id, self.direction_contract_id):
            H40ProtectedSurfaceGuard.assert_path_allowed(field_val)

        # Validate hyperparameters, feature_params, lookback_windows for forbidden performance/outcome keys
        all_dicts = (self.hyperparameters, self.feature_params, self.lookback_windows)
        for d in all_dicts:
            for key in d:
                if key.lower() in FORBIDDEN_PERF_KEYS:
                    raise H40GuardError(
                        H40ReasonCode.PROTECTED_SURFACE_DENIED,
                        f"Forbidden outcome or performance metric '{key}' in pre-outcome configuration.",
                    )

    @property
    def config_id(self) -> str:
        """Returns deterministic content-addressed identifier for the configuration."""
        semantic_payload = {
            "scope": self.scope,
            "primary_horizon": self.primary_horizon,
            "family_combination": [f.value for f in self.family_combination],
            "direction_variant": self.direction_variant,
            "regime_contract_id": self.regime_contract_id,
            "opportunity_contract_id": self.opportunity_contract_id,
            "direction_contract_id": self.direction_contract_id,
            "geometry_contract_id": self.geometry_contract_id,
            "calibration_contract_id": self.calibration_contract_id,
            "action_threshold": round(self.action_threshold, 4),
            "abstention_policy": self.abstention_policy,
            "required_feature_ids": sorted(self.required_feature_ids),
            "feature_params": thaw_json(self.feature_params),
            "lookback_windows": thaw_json(self.lookback_windows),
            "availability_rule": self.availability_rule,
            "cost_proxy_id": self.cost_proxy_id,
            "mechanical_refit_policy": self.mechanical_refit_policy,
            "protocol_hash": self.protocol_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "ledger_schema_version": self.ledger_schema_version,
            "frozen_kernel_sha": self.frozen_kernel_sha,
            "p1_code_baseline_sha": self.p1_code_baseline_sha,
            "asset_scope": sorted(self.asset_scope),
            "hyperparameters": thaw_json(self.hyperparameters),
        }
        return canonical_sha256(semantic_payload)

    def to_dict(self) -> dict[str, Any]:
        """Serializes slot to dictionary."""
        return {
            "slot_index": self.slot_index,
            "config_id": self.config_id,
            "scope": self.scope,
            "primary_horizon": self.primary_horizon,
            "family_combination": [f.value for f in self.family_combination],
            "direction_variant": self.direction_variant,
            "regime_contract_id": self.regime_contract_id,
            "opportunity_contract_id": self.opportunity_contract_id,
            "direction_contract_id": self.direction_contract_id,
            "geometry_contract_id": self.geometry_contract_id,
            "calibration_contract_id": self.calibration_contract_id,
            "action_threshold": self.action_threshold,
            "abstention_policy": self.abstention_policy,
            "required_feature_ids": list(self.required_feature_ids),
            "feature_params": thaw_json(self.feature_params),
            "lookback_windows": thaw_json(self.lookback_windows),
            "availability_rule": self.availability_rule,
            "cost_proxy_id": self.cost_proxy_id,
            "mechanical_refit_policy": self.mechanical_refit_policy,
            "protocol_hash": self.protocol_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "split_manifest_hash": self.split_manifest_hash,
            "ledger_schema_version": self.ledger_schema_version,
            "frozen_kernel_sha": self.frozen_kernel_sha,
            "p1_code_baseline_sha": self.p1_code_baseline_sha,
            "asset_scope": list(self.asset_scope),
            "hyperparameters": thaw_json(self.hyperparameters),
            "status": self.status,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ConfigurationSlot:
        """Deserializes slot from mapping."""
        fams = tuple(H40Family(f) for f in data["family_combination"])
        asset_scope = tuple(str(a) for a in data["asset_scope"])
        scope = str(data.get("scope", "BTC_ONLY"))
        rc_val = data.get("reason_code")
        rc = H40ReasonCode(rc_val) if rc_val else None

        return cls(
            slot_index=int(data["slot_index"]),
            family_combination=fams,
            asset_scope=asset_scope,
            primary_horizon=str(data["primary_horizon"]),
            action_threshold=float(data["action_threshold"]),
            hyperparameters=FrozenDict(data.get("hyperparameters", {})),
            scope=scope,
            direction_variant=str(data.get("direction_variant", "")),
            regime_contract_id=str(data.get("regime_contract_id", "R_VOL_RANGE_V1_24H")),
            opportunity_contract_id=str(data.get("opportunity_contract_id", "O_RANGE_EXPANSION_V1_24H")),
            direction_contract_id=str(data.get("direction_contract_id", "")),
            geometry_contract_id=str(data.get("geometry_contract_id", "GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1")),
            calibration_contract_id=str(data.get("calibration_contract_id", "CALIBRATION_LOGISTIC_V1")),
            abstention_policy=str(data.get("abstention_policy", DEFAULT_ACTION)),
            required_feature_ids=tuple(str(fid) for fid in data.get("required_feature_ids", ())),
            feature_params=FrozenDict(data.get("feature_params", {})),
            lookback_windows=FrozenDict(data.get("lookback_windows", {})),
            availability_rule=str(data.get("availability_rule", "CLOSED_BAR_STRICT")),
            cost_proxy_id=str(data.get("cost_proxy_id", "COST_PROXY_12BPS_V1")),
            mechanical_refit_policy=str(data.get("mechanical_refit_policy", "REFIT_CHRONOLOGICAL_PAST_ONLY_V1")),
            protocol_hash=str(data.get("protocol_hash", DEFAULT_PROTOCOL_HASH)),
            source_manifest_hash=str(data.get("source_manifest_hash", DEFAULT_SOURCE_MANIFEST_HASH)),
            split_manifest_hash=str(data.get("split_manifest_hash", DEFAULT_SPLIT_MANIFEST_HASH)),
            ledger_schema_version=str(data.get("ledger_schema_version", LEDGER_SCHEMA_VERSION)),
            frozen_kernel_sha=str(data.get("frozen_kernel_sha", FROZEN_KERNEL_SHA)),
            p1_code_baseline_sha=str(data.get("p1_code_baseline_sha", P1_CODE_BASELINE_SHA)),
            status=str(data.get("status", "REGISTERED")),
            reason_code=rc,
            notes=str(data.get("notes", "")),
        )

    @classmethod
    def create(
        cls,
        slot_index: int,
        family_combination: tuple[H40Family, ...] | list[H40Family],
        asset_scope: tuple[str, ...] | list[str],
        primary_horizon: str,
        action_threshold: float,
        hyperparameters: Mapping[str, Any] | None = None,
        scope: str | None = None,
        direction_variant: str = "",
        regime_contract_id: str = "R_VOL_RANGE_V1_24H",
        opportunity_contract_id: str = "O_RANGE_EXPANSION_V1_24H",
        direction_contract_id: str = "",
        geometry_contract_id: str = "GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1",
        calibration_contract_id: str = "CALIBRATION_LOGISTIC_V1",
        abstention_policy: str = DEFAULT_ACTION,
        required_feature_ids: tuple[str, ...] | list[str] = (),
        feature_params: Mapping[str, Any] | None = None,
        lookback_windows: Mapping[str, Any] | None = None,
        availability_rule: str = "CLOSED_BAR_STRICT",
        cost_proxy_id: str = "COST_PROXY_12BPS_V1",
        mechanical_refit_policy: str = "REFIT_CHRONOLOGICAL_PAST_ONLY_V1",
        protocol_hash: str = DEFAULT_PROTOCOL_HASH,
        source_manifest_hash: str = DEFAULT_SOURCE_MANIFEST_HASH,
        split_manifest_hash: str = DEFAULT_SPLIT_MANIFEST_HASH,
        ledger_schema_version: str = LEDGER_SCHEMA_VERSION,
        frozen_kernel_sha: str = FROZEN_KERNEL_SHA,
        p1_code_baseline_sha: str = P1_CODE_BASELINE_SHA,
        status: str = "REGISTERED",
        reason_code: H40ReasonCode | None = None,
        notes: str = "",
    ) -> H40ConfigurationSlot:
        """Factory creating a slot with frozen parameters and canonical defaults."""
        fams = tuple(family_combination)
        assets = tuple(asset_scope)

        # Derive scope if omitted
        if scope is None:
            if set(assets) == {"BTCUSDT"}:
                scope = "BTC_ONLY"
            elif set(assets) == {"ETHUSDT"}:
                scope = "ETH_ONLY"
            elif set(assets) == {"BTCUSDT", "ETHUSDT"}:
                scope = "POOLED_BTC_ETH"
            else:
                scope = "BTC_ONLY"

        # Derive direction variant if omitted
        if not direction_variant and fams:
            direction_variant = f"{fams[0].value}_V1"

        if not direction_contract_id and fams:
            direction_contract_id = fams[0].value

        params_dict = dict(feature_params) if feature_params is not None else {}
        if H40Family.D5_FUNDING_DIRECTION_INTERACTION in fams and "base_directional_owner" not in params_dict:
            params_dict["base_directional_owner"] = "D1_TREND_CONTINUATION"

        return cls(
            slot_index=slot_index,
            family_combination=fams,
            asset_scope=assets,
            primary_horizon=primary_horizon,
            action_threshold=action_threshold,
            hyperparameters=FrozenDict(hyperparameters or {}),
            scope=scope,
            direction_variant=direction_variant,
            regime_contract_id=regime_contract_id,
            opportunity_contract_id=opportunity_contract_id,
            direction_contract_id=direction_contract_id,
            geometry_contract_id=geometry_contract_id,
            calibration_contract_id=calibration_contract_id,
            abstention_policy=abstention_policy,
            required_feature_ids=tuple(required_feature_ids),
            feature_params=FrozenDict(params_dict),
            lookback_windows=FrozenDict(lookback_windows or {}),
            availability_rule=availability_rule,
            cost_proxy_id=cost_proxy_id,
            mechanical_refit_policy=mechanical_refit_policy,
            protocol_hash=protocol_hash,
            source_manifest_hash=source_manifest_hash,
            split_manifest_hash=split_manifest_hash,
            ledger_schema_version=ledger_schema_version,
            frozen_kernel_sha=frozen_kernel_sha,
            p1_code_baseline_sha=p1_code_baseline_sha,
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
            scope=cur.scope,
            direction_variant=cur.direction_variant,
            regime_contract_id=cur.regime_contract_id,
            opportunity_contract_id=cur.opportunity_contract_id,
            direction_contract_id=cur.direction_contract_id,
            geometry_contract_id=cur.geometry_contract_id,
            calibration_contract_id=cur.calibration_contract_id,
            abstention_policy=cur.abstention_policy,
            required_feature_ids=cur.required_feature_ids,
            feature_params=cur.feature_params,
            lookback_windows=cur.lookback_windows,
            availability_rule=cur.availability_rule,
            cost_proxy_id=cur.cost_proxy_id,
            mechanical_refit_policy=cur.mechanical_refit_policy,
            protocol_hash=cur.protocol_hash,
            source_manifest_hash=cur.source_manifest_hash,
            split_manifest_hash=cur.split_manifest_hash,
            ledger_schema_version=cur.ledger_schema_version,
            frozen_kernel_sha=cur.frozen_kernel_sha,
            p1_code_baseline_sha=cur.p1_code_baseline_sha,
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

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40ConfigurationLedger:
        """Deserializes ledger from dictionary."""
        ledger = cls()
        for slot_data in data["slots"]:
            slot = H40ConfigurationSlot.from_dict(slot_data)
            idx = slot.slot_index
            if idx != len(ledger._slots):
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"Corrupted slot index ordering in ledger serialized data: expected {len(ledger._slots)}, got {idx}.",
                )
            cid = slot.config_id
            if cid in ledger._id_to_index:
                raise H40GuardError(
                    H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                    f"Duplicate config ID {cid} in ledger serialized data.",
                )
            ledger._slots.append(slot)
            ledger._id_to_index[cid] = idx
        return ledger

    def canonical_json(self) -> str:
        """Returns deterministic RFC-8259 canonical JSON."""
        return canonical_json(self.to_dict())

    @property
    def ledger_hash(self) -> str:
        """Returns SHA-256 hash over canonical ledger content."""
        return canonical_sha256(self.to_dict())
