"""H40 protocol authority hash tree and canonical semantic-root contracts.

Implements the frozen R3R2 Section 9.3 hash-tree preimages, extended cumulatively
through R3R3 (calibration content hashes) and R3R4 (8 statistical-decision contracts),
using repository ``canonical_json`` / ``canonical_sha256`` semantics exactly.

All computation functions derive their return values from canonical preimages; none
returns a hard-coded constant.  Oracle constants are provided solely as expected-value
references for tests.

Strictly pre-outcome: no labels, forward returns, MFE/MAE, metrics, or outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .guards import H40ReasonCode

from ..research_contract.canonical import (
    FrozenDict,
    canonical_sha256,
)

# ---------------------------------------------------------------------------
# Authority chain constants (Git commit object IDs — opaque exact strings)
# ---------------------------------------------------------------------------

FROZEN_KERNEL: str = "6838e9db8d5c369b5da87354821d9c8e79c2a879"
BASE_AUTHORITY: str = "8b36cfde2ac14a37ed4eb244a8b5ae88882765b4"
R1_AUTHORITY: str = "59e9fe0ba361557c5df56f0d8f8afaa781cf0071"
R2_AUTHORITY: str = "4bdeb1a0102b3cb374e8ec7d01b41a79dcc8b021"
R2_ACCEPTANCE: str = "b9c8531e719fd4f10cf27301719c9e066b95be13"
P1_CODE_BASELINE: str = "3fc89541ed0965fc0e2972af310e34ae1b838168"
P1_FINAL_ACCEPTANCE: str = "95ab819d5300312b4d493b9585b4b369621504b6"
R3_AMENDMENT: str = "e45899bb0118b14127bc765f49315109cfd94ff0"
R3R1_AMENDMENT: str = "3f1bf28dc810ca4fd1bfd2bef566033cd15550fa"
R3R2_AMENDMENT: str = "77601342ac9055b5c0bb47639d4c8ef7d83da154"
R3R3_AMENDMENT: str = "f01062b4b1a20d12f93ee1351bfda67e19401f25"
R3R4_AMENDMENT: str = "7520a62d0516ee097c276451b9f8df5924c6408f"

SCHEMA_ID: str = "H40_PROTOCOL_V1_R3"

# ---------------------------------------------------------------------------
# Oracle constants (expected values for tests — NOT return values of functions)
# ---------------------------------------------------------------------------

EXPECTED_PROTOCOL_AUTHORITY_HASH: str = (
    "a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce"
)
EXPECTED_SEMANTIC_ROOT_HASH: str = (
    "71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1"
)
EXPECTED_STRUCTURAL_LEDGER_HASH: str = (
    "483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f"
)

# ---------------------------------------------------------------------------
# Protocol authority hash
# ---------------------------------------------------------------------------


def compute_protocol_authority_hash() -> str:
    """Compute the cumulative protocol authority hash from the accepted chain.

    Preimage: 13-key dict of Git commit object IDs + schema_id, canonicalised via
    ``canonical_sha256``.  No self-reference; computed from immutable inputs only.
    """
    authority: dict[str, str] = {
        "schema_id": SCHEMA_ID,
        "frozen_kernel": FROZEN_KERNEL,
        "base_authority": BASE_AUTHORITY,
        "r1_authority": R1_AUTHORITY,
        "r2_authority": R2_AUTHORITY,
        "r2_acceptance": R2_ACCEPTANCE,
        "p1_code_baseline": P1_CODE_BASELINE,
        "p1_final_acceptance": P1_FINAL_ACCEPTANCE,
        "r3_amendment": R3_AMENDMENT,
        "r3r1_amendment": R3R1_AMENDMENT,
        "r3r2_amendment": R3R2_AMENDMENT,
        "r3r3_amendment": R3R3_AMENDMENT,
        "r3r4_amendment": R3R4_AMENDMENT,
    }
    return canonical_sha256(authority)


# ---------------------------------------------------------------------------
# Canonical contract object helpers
# ---------------------------------------------------------------------------


def _contract_hash(family: str, contract_id: str, version: str = "V1") -> str:
    """Content hash of a canonical contract object."""
    return canonical_sha256(
        {"family": family, "contract_id": contract_id, "version": version}
    )


# --- Active feature registry (12 features, sorted by feature_id) ----------

_ACTIVE_FEATURE_CONTRACTS: tuple[tuple[str, str], ...] = (
    ("D1_TREND_CONTINUATION", "D1_V1_RETURN_4H"),
    ("D1_TREND_CONTINUATION", "D1_V2_RETURN_12H"),
    ("D2_BREAKOUT_CONTINUATION", "D2_V1_BREAKOUT_24H"),
    ("D2_BREAKOUT_CONTINUATION", "D2_V2_BREAKOUT_72H"),
    ("D3_FAILED_MOVE_REVERSAL", "D3_V1_FAILED_BREAK_24H"),
    ("D3_FAILED_MOVE_REVERSAL", "D3_V2_FAILED_BREAK_72H"),
    ("D4_BTC_ETH_CONFIRM_DIVERGE", "D4_V1_CONFIRMATION_4H"),
    ("D4_BTC_ETH_CONFIRM_DIVERGE", "D4_V2_DIVERGENCE_8H"),
    ("D5_FUNDING_DIRECTION_INTERACTION", "D5_V1_CROWDING_Q10_D1"),
    ("D5_FUNDING_DIRECTION_INTERACTION", "D5_V2_CROWDING_Q20_D2"),
    ("R_VOL_RANGE", "R_VOL_RANGE_V1"),
    ("O_RANGE_EXPANSION", "O_RANGE_EXPANSION_V1"),
)

_FEATURE_FAMILY_MAP: dict[str, str] = {
    "D1_V1_RETURN_4H": "D1_TREND_CONTINUATION",
    "D1_V2_RETURN_12H": "D1_TREND_CONTINUATION",
    "D2_V1_BREAKOUT_24H": "D2_BREAKOUT_CONTINUATION",
    "D2_V2_BREAKOUT_72H": "D2_BREAKOUT_CONTINUATION",
    "D3_V1_FAILED_BREAK_24H": "D3_FAILED_MOVE_REVERSAL",
    "D3_V2_FAILED_BREAK_72H": "D3_FAILED_MOVE_REVERSAL",
    "D4_V1_CONFIRMATION_4H": "D4_BTC_ETH_CONFIRM_DIVERGE",
    "D4_V2_DIVERGENCE_8H": "D4_BTC_ETH_CONFIRM_DIVERGE",
    "D5_V1_CROWDING_Q10_D1": "D5_FUNDING_DIRECTION_INTERACTION",
    "D5_V2_CROWDING_Q20_D2": "D5_FUNDING_DIRECTION_INTERACTION",
    "R_VOL_RANGE_V1_24H": "R_VOL_RANGE",
    "O_RANGE_EXPANSION_V1_24H": "O_RANGE_EXPANSION",
}


def _active_feature_registry_hash() -> str:
    return canonical_sha256(
        sorted(
            [
                _contract_hash(family, contract_id)
                for family, contract_id in _ACTIVE_FEATURE_CONTRACTS
            ]
        )
    )


# --- Active direction registry (10 single-family + 4 pair, sorted) ---------

_ACTIVE_DIRECTION_IDS: tuple[str, ...] = (
    "D1_V1_RETURN_4H",
    "D1_V2_RETURN_12H",
    "D2_V1_BREAKOUT_24H",
    "D2_V2_BREAKOUT_72H",
    "D3_V1_FAILED_BREAK_24H",
    "D3_V2_FAILED_BREAK_72H",
    "D4_V1_CONFIRMATION_4H",
    "D4_V2_DIVERGENCE_8H",
    "D5_V1_CROWDING_Q10_D1",
    "D5_V2_CROWDING_Q20_D2",
)

_PAIR_DIRECTION_IDS: tuple[str, ...] = (
    "PAIR_D1_D4_V1",
    "PAIR_D1_D5_V1",
    "PAIR_D2_D4_V1",
    "PAIR_D3_D5_V1",
)

_PAIR_FAMILY_MAP: dict[str, str] = {
    "PAIR_D1_D4_V1": "D1_TREND_CONTINUATION",
    "PAIR_D1_D5_V1": "D1_TREND_CONTINUATION",
    "PAIR_D2_D4_V1": "D2_BREAKOUT_CONTINUATION",
    "PAIR_D3_D5_V1": "D3_FAILED_MOVE_REVERSAL",
}


def _active_direction_registry_hash() -> str:
    return canonical_sha256(
        sorted(
            [
                _contract_hash(_FEATURE_FAMILY_MAP[did], did)
                for did in _ACTIVE_DIRECTION_IDS
            ]
            + [
                _contract_hash(_PAIR_FAMILY_MAP[pid], pid)
                for pid in _PAIR_DIRECTION_IDS
            ]
        )
    )


# --- Active gate registry (R_VOL_RANGE_V1, O_RANGE_EXPANSION_V1) -----------

def _active_gate_registry_hash() -> str:
    return canonical_sha256(
        sorted(
            [
                _contract_hash("R_VOL_RANGE", "R_VOL_RANGE_V1"),
                _contract_hash("O_RANGE_EXPANSION", "O_RANGE_EXPANSION_V1"),
            ]
        )
    )


# --- Geometry contract ----------------------------------------------------

def _geometry_contract_hash() -> str:
    return _contract_hash(
        "GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1",
        "GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1",
    )


# --- Calibration contracts (content hashes, not textual IDs) --------------

def _calibration_contract_hashes() -> list[str]:
    return sorted(
        [
            _contract_hash(
                "CALIBRATION_PLATT_LOGISTIC", "CALIBRATION_PLATT_LOGISTIC_V1"
            ),
            _contract_hash(
                "CALIBRATION_ISOTONIC_IF_ELIGIBLE",
                "CALIBRATION_ISOTONIC_IF_ELIGIBLE_V1",
            ),
        ]
    )


# --- Availability / refit / reserved family vocabulary --------------------

def _availability_contract_hash() -> str:
    return _contract_hash(
        "AVAILABILITY_CLOSED_BAR_STRICT", "AVAILABILITY_CLOSED_BAR_STRICT_V1"
    )


def _refit_policy_hash() -> str:
    return _contract_hash(
        "REFIT_CHRONOLOGICAL_PAST_ONLY", "REFIT_CHRONOLOGICAL_PAST_ONLY_V1"
    )


_RESERVED_FAMILY_VOCABULARY: tuple[str, ...] = (
    "R_TREND_RANGE",
    "R_LIQ_ACTIVITY",
    "R_CROSS_ASSET",
    "R_FUNDING_CROWDING",
    "O_COMPRESSION_RELEASE",
    "O_BREAKOUT_DISTANCE",
    "O_EXPECTED_EXCURSION",
    "O_TPBR_MAGNITUDE",
)


def _reserved_family_vocabulary_hash() -> str:
    return canonical_sha256(sorted(_RESERVED_FAMILY_VOCABULARY))


# --- R3R4 statistical-decision contracts (8 content hashes) --------------

def _side_preserving_action_contract_hash() -> str:
    return _contract_hash("ACTION_SIDE_PRESERVING", "ACTION_SIDE_PRESERVING_V1")


def _isotonic_prediction_map_contract_hash() -> str:
    return _contract_hash(
        "ISOTONIC_CLIPPED_LEFT_STEP", "ISOTONIC_PREDICTION_MAP_V1"
    )


def _ece_contract_hash() -> str:
    return _contract_hash("ECE_ADAPTIVE_BIN", "ECE_ADAPTIVE_BIN_V1")


def _discovery_selection_correction_contract_hash() -> str:
    return _contract_hash("DISCOVERY_SELECTION", "DISCOVERY_SELECTION_V1")


def _p0_context_contract_hash() -> str:
    return _contract_hash("P0_CONTEXT", "P0_CONTEXT_V1")


def _training_sample_floor_population_contract_hash() -> str:
    return _contract_hash("TRAINING_SAMPLE_FLOOR", "TRAINING_SAMPLE_FLOOR_V1")


def _random_matched_benchmark_contract_hash() -> str:
    return _contract_hash("RANDOM_MATCHED", "RANDOM_MATCHED_V1")


def _side_specific_neff_contract_hash() -> str:
    return _contract_hash("SIDE_SPECIFIC_NEFF", "SIDE_SPECIFIC_NEFF_V1")


# ---------------------------------------------------------------------------
# Semantic root hash
# ---------------------------------------------------------------------------


def compute_semantic_root_hash() -> str:
    """Compute the semantic root hash from all child content hashes.

    Preimage: dict of 16 child content-hash values, canonicalised via
    ``canonical_sha256``.
    """
    root: dict[str, Any] = {
        "active_feature_registry_hash": _active_feature_registry_hash(),
        "active_direction_registry_hash": _active_direction_registry_hash(),
        "active_gate_registry_hash": _active_gate_registry_hash(),
        "geometry_contract_hash": _geometry_contract_hash(),
        "calibration_contract_hashes": _calibration_contract_hashes(),
        "availability_contract_hash": _availability_contract_hash(),
        "refit_policy_hash": _refit_policy_hash(),
        "reserved_family_vocabulary_hash": _reserved_family_vocabulary_hash(),
        "side_preserving_action_contract_hash": _side_preserving_action_contract_hash(),
        "isotonic_prediction_map_contract_hash": _isotonic_prediction_map_contract_hash(),
        "ece_contract_hash": _ece_contract_hash(),
        "discovery_selection_correction_contract_hash": _discovery_selection_correction_contract_hash(),
        "p0_context_contract_hash": _p0_context_contract_hash(),
        "training_sample_floor_population_contract_hash": _training_sample_floor_population_contract_hash(),
        "random_matched_benchmark_contract_hash": _random_matched_benchmark_contract_hash(),
        "side_specific_neff_contract_hash": _side_specific_neff_contract_hash(),
    }
    return canonical_sha256(root)


# ---------------------------------------------------------------------------
# Structural configuration / slot / ledger hashes
# ---------------------------------------------------------------------------


def compute_structural_configuration_hash(
    *,
    protocol_authority_hash: str,
    semantic_root_hash: str,
    family_combination: tuple[str, ...] | list[str],
    primary_horizon: str,
    scope: str,
    action_threshold: float,
    calibration_contract_id: str,
    abstention_policy: str = "NO_TRADE",
) -> str:
    """Compute the structural configuration hash for one row.

    Binds protocol authority + semantic root + row semantic fields.
    Excludes ``slot_index``, ``status``, ``reason_code``, ``notes``
    (those are runtime, not structural).
    """
    payload: dict[str, Any] = {
        "protocol_authority_hash": protocol_authority_hash,
        "semantic_root_hash": semantic_root_hash,
        "family_combination": list(family_combination),
        "primary_horizon": primary_horizon,
        "scope": scope,
        "action_threshold": action_threshold,
        "calibration_contract_id": calibration_contract_id,
        "abstention_policy": abstention_policy,
    }
    return canonical_sha256(payload)


def compute_slot_hash(slot_index: int, structural_configuration_hash: str) -> str:
    """Compute the slot hash (includes ``slot_index``; configuration hash excludes it)."""
    return canonical_sha256(
        {
            "slot_index": slot_index,
            "structural_configuration_hash": structural_configuration_hash,
        }
    )


def compute_structural_ledger_hash(slot_hashes: list[str]) -> str:
    """Compute the structural ledger hash over the ordered 168 slot hashes."""
    return canonical_sha256(slot_hashes)


# ---------------------------------------------------------------------------
# Runtime authority snapshot (separate from structural identity)
# ---------------------------------------------------------------------------

# Accepted P1 production authority states (canonical, immutable)
P1_SOURCE_AUTHORITY_STATES: dict[str, str] = {
    "BTCUSDT_USD_M_1H": "NOT_TESTABLE",
    "ETHUSDT_USD_M_1H": "VERIFIED",
    "BTCUSDT_OFFICIAL_DERIVATIVES": "NOT_TESTABLE",
    "BTCUSDT_SPOT_FLOW": "NOT_TESTABLE",
    "ETHUSDT_DERIVATIVES_FLOW": "NOT_TESTABLE",
}


@dataclass(frozen=True)
class RuntimeAuthoritySnapshot:
    """Runtime source-authority snapshot, separate from structural configuration identity.

    Binds per-source ``production_authority_state`` and a snapshot identity.
    A source promotion changes this snapshot but must not mutate any structural
    configuration or ledger identity.
    """

    snapshot_id: str
    per_source_states: FrozenDict = field(default_factory=lambda: FrozenDict())

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError("RuntimeAuthoritySnapshot requires a non-empty snapshot_id")

    @property
    def runtime_authority_snapshot_hash(self) -> str:
        return canonical_sha256(
            {
                "snapshot_id": self.snapshot_id,
                "per_source_states": {
                    k: v for k, v in sorted(self.per_source_states.items())
                },
            }
        )

    def derive_slot_status(
        self, required_source_ids: tuple[str, ...]
    ) -> tuple[str, H40ReasonCode | None]:
        """Derive (status, reason_code) for a slot from its required source set.

        Returns ``("REGISTERED", None)`` iff every required source is production
        VERIFIED; ``("NOT_TESTABLE", H40ReasonCode.NOT_TESTABLE)`` otherwise.
        """
        from .guards import H40ReasonCode

        for source_id in required_source_ids:
            state = self.per_source_states.get(source_id, "NOT_TESTABLE")
            if state != "VERIFIED":
                return ("NOT_TESTABLE", H40ReasonCode.NOT_TESTABLE)
        return ("REGISTERED", None)


def current_p1_authority_snapshot() -> RuntimeAuthoritySnapshot:
    """Build the current accepted P1 authority snapshot."""
    return RuntimeAuthoritySnapshot(
        snapshot_id="P1_ACCEPTED_3fc89541",
        per_source_states=FrozenDict(P1_SOURCE_AUTHORITY_STATES),
    )


@dataclass(frozen=True)
class MaterializedRunAuthority:
    """Binds structural ledger identity + runtime authority snapshot.

    Changing runtime authority without changing science changes this identity
    but must not mutate ``structural_ledger_hash``.
    """

    structural_ledger_hash: str
    runtime_authority_snapshot_hash: str

    @property
    def materialized_run_authority_hash(self) -> str:
        return canonical_sha256(
            {
                "structural_ledger_hash": self.structural_ledger_hash,
                "runtime_authority_snapshot_hash": self.runtime_authority_snapshot_hash,
            }
        )


# ---------------------------------------------------------------------------
# Source-projection rule (per-scope → required source set)
# ---------------------------------------------------------------------------

def project_required_sources(
    scope: str,
    requires_cross_asset: bool,
    requires_funding: bool,
) -> tuple[str, ...]:
    """Project the required source IDs for a row at a given scope.

    Implements the R3R2 Section 4.1 source-projection rule:
    - OWN_ASSET_BY_SCOPE: BTC_ONLY→{BTCUSDT_USD_M_1H}, ETH_ONLY→{ETHUSDT_USD_M_1H},
      POOLED→own product source (both for pooled).
    - CROSS_ASSET_ALWAYS: always requires both BTC + ETH 1h sources.
    - FUNDING_OWN_PRODUCT: adds own-product funding source.
    """
    sources: list[str] = []
    if requires_cross_asset:
        sources.extend(["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"])
    else:
        if scope in ("BTC_ONLY", "POOLED_BTC_ETH"):
            sources.append("BTCUSDT_USD_M_1H")
        if scope in ("ETH_ONLY", "POOLED_BTC_ETH"):
            sources.append("ETHUSDT_USD_M_1H")
    if requires_funding:
        if scope in ("BTC_ONLY", "POOLED_BTC_ETH"):
            sources.append("BTCUSDT_OFFICIAL_DERIVATIVES")
        if scope in ("ETH_ONLY", "POOLED_BTC_ETH"):
            sources.append("ETHUSDT_DERIVATIVES_FLOW")
    return tuple(sorted(set(sources)))


# ---------------------------------------------------------------------------
# Hash receipt (deterministic artifact for tests/verification)
# ---------------------------------------------------------------------------


def build_hash_receipt(slot_hashes: list[str]) -> dict[str, Any]:
    """Build a deterministic hash receipt over the full semantic tree + 168 slots.

    Contains no market outcomes.  Used by tests to verify transitive content
    binding and ledger reproduction.
    """
    pah = compute_protocol_authority_hash()
    srh = compute_semantic_root_hash()
    return {
        "protocol_authority_hash": pah,
        "semantic_root_hash": srh,
        "slot_hashes": slot_hashes,
        "structural_ledger_hash": compute_structural_ledger_hash(slot_hashes),
    }
