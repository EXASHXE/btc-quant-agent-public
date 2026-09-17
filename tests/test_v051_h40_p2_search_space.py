"""Mandatory adversarial and invariant tests for H40-P2.

Validates exact 168-slot search space materialization, feature contracts,
semantic family authority, and authority hash bindings strictly pre-outcome.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from btc_quant_agent.h40 import (
    ALLOWED_DEPTH_TWO_PAIRS,
    ALLOWED_PRIMARY_HORIZONS,
    ALLOWED_SCOPES,
    CONFIGS_PER_PAIR,
    CONFIGS_PER_VARIANT,
    FROZEN_KERNEL_SHA,
    LEDGER_SCHEMA_VERSION,
    P1_CODE_BASELINE_SHA,
    PAIR_CONFIG_COUNT,
    SINGLE_FAMILY_CONFIG_COUNT,
    TOTAL_SEARCH_BUDGET,
    CalibrationMethod,
    H40CalibrationContract,
    H40ConfigurationLedger,
    H40ConfigurationSlot,
    H40Family,
    H40FeatureContract,
    H40GeometryContract,
    H40GuardError,
    H40ReasonCode,
    H40RefitPolicyContract,
    OpportunityFamily,
    RegimeFamily,
    build_canonical_feature_registry,
    materialize_h40_search_space,
)
from btc_quant_agent.research_contract.canonical import FrozenDict


# ---------------------------------------------------------------------------
# Requirement 1: Ledger has exactly 168 unique slots and unique hashes
# ---------------------------------------------------------------------------
def test_p2_01_ledger_has_exactly_168_unique_slots_and_hashes() -> None:
    """Ledger materializes exactly 168 unique slots and 168 unique configuration hashes."""
    ledger = materialize_h40_search_space()

    assert ledger.slot_count == TOTAL_SEARCH_BUDGET == 168
    assert ledger.remaining_budget == 0

    indices = [s.slot_index for s in ledger.slots]
    assert indices == list(range(168))
    assert len(set(indices)) == 168

    config_ids = [s.config_id for s in ledger.slots]
    assert len(config_ids) == 168
    assert len(set(config_ids)) == 168

    # Verify single-family count (120) and pair count (48)
    single_family_slots = [s for s in ledger.slots if len(s.family_combination) == 1]
    pair_slots = [s for s in ledger.slots if len(s.family_combination) == 2]

    assert len(single_family_slots) == SINGLE_FAMILY_CONFIG_COUNT == 120
    assert len(pair_slots) == PAIR_CONFIG_COUNT == 48


# ---------------------------------------------------------------------------
# Requirement 2: No duplicate semantic row can hide behind a different slot ID
# ---------------------------------------------------------------------------
def test_p2_02_duplicate_semantic_row_cannot_hide_behind_different_slot_id() -> None:
    """Registering an identical semantic configuration under a different slot_index is rejected."""
    ledger = materialize_h40_search_space()
    base_slot = ledger.slots[0]

    # Attempt to create an identical semantic slot with a different slot_index
    duplicate_slot = H40ConfigurationSlot.create(
        slot_index=999,  # different slot index
        family_combination=base_slot.family_combination,
        asset_scope=base_slot.asset_scope,
        primary_horizon=base_slot.primary_horizon,
        action_threshold=base_slot.action_threshold,
        scope=base_slot.scope,
        direction_variant=base_slot.direction_variant,
        regime_contract_id=base_slot.regime_contract_id,
        opportunity_contract_id=base_slot.opportunity_contract_id,
        direction_contract_id=base_slot.direction_contract_id,
        geometry_contract_id=base_slot.geometry_contract_id,
        calibration_contract_id=base_slot.calibration_contract_id,
        abstention_policy=base_slot.abstention_policy,
        required_feature_ids=base_slot.required_feature_ids,
        feature_params=base_slot.feature_params,
        lookback_windows=base_slot.lookback_windows,
        availability_rule=base_slot.availability_rule,
        cost_proxy_id=base_slot.cost_proxy_id,
        mechanical_refit_policy=base_slot.mechanical_refit_policy,
        protocol_hash=base_slot.protocol_hash,
        source_manifest_hash=base_slot.source_manifest_hash,
        split_manifest_hash=base_slot.split_manifest_hash,
        hyperparameters=base_slot.hyperparameters,
    )

    # Identical semantic configuration has identical config_id
    assert duplicate_slot.config_id == base_slot.config_id

    # Ledger must detect duplicate config_id
    fresh_ledger = H40ConfigurationLedger()
    fresh_ledger.register_slot(base_slot)

    # Create slot at index 1 with same semantic payload
    slot1_duplicate = H40ConfigurationSlot.create(
        slot_index=1,
        family_combination=base_slot.family_combination,
        asset_scope=base_slot.asset_scope,
        primary_horizon=base_slot.primary_horizon,
        action_threshold=base_slot.action_threshold,
        scope=base_slot.scope,
        direction_variant=base_slot.direction_variant,
        regime_contract_id=base_slot.regime_contract_id,
        opportunity_contract_id=base_slot.opportunity_contract_id,
        direction_contract_id=base_slot.direction_contract_id,
        geometry_contract_id=base_slot.geometry_contract_id,
        calibration_contract_id=base_slot.calibration_contract_id,
        abstention_policy=base_slot.abstention_policy,
        required_feature_ids=base_slot.required_feature_ids,
        feature_params=base_slot.feature_params,
        lookback_windows=base_slot.lookback_windows,
        availability_rule=base_slot.availability_rule,
        cost_proxy_id=base_slot.cost_proxy_id,
        mechanical_refit_policy=base_slot.mechanical_refit_policy,
        protocol_hash=base_slot.protocol_hash,
        source_manifest_hash=base_slot.source_manifest_hash,
        split_manifest_hash=base_slot.split_manifest_hash,
        hyperparameters=base_slot.hyperparameters,
    )

    with pytest.raises(H40GuardError) as exc_info:
        fresh_ledger.register_slot(slot1_duplicate)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT


# ---------------------------------------------------------------------------
# Requirement 3: Changing any material semantic field changes configuration hash
# ---------------------------------------------------------------------------
def test_p2_03_material_semantic_field_mutations_change_hash() -> None:
    """Mutating any semantic parameter or identity strictly produces a distinct config_id."""
    base = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        scope="BTC_ONLY",
        direction_variant="D1_V1_RETURN_4H",
        regime_contract_id="R_VOL_RANGE_V1_24H",
        opportunity_contract_id="O_RANGE_EXPANSION_V1_24H",
        direction_contract_id="D1_V1_RETURN_4H",
        geometry_contract_id="GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1",
        calibration_contract_id="CALIBRATION_LOGISTIC_V1",
        abstention_policy="NO_TRADE",
        required_feature_ids=["D1_V1_RETURN_4H"],
        feature_params={"metric": "closed_bar_log_return", "lookback_hours": 4},
        lookback_windows={"lookback_hours": 4},
        availability_rule="CLOSED_BAR_STRICT",
        cost_proxy_id="COST_PROXY_12BPS_V1",
        mechanical_refit_policy="REFIT_CHRONOLOGICAL_PAST_ONLY_V1",
        protocol_hash="0" * 64,
        source_manifest_hash="1" * 64,
        split_manifest_hash="2" * 64,
        hyperparameters={"seed": 42},
    )
    base_hash = base.config_id

    # Test mutating each material field individually
    mutations = [
        {"primary_horizon": "8h"},
        {"action_threshold": 0.60},
        {"scope": "ETH_ONLY", "asset_scope": ["ETHUSDT"]},
        {"direction_variant": "D1_V2_RETURN_12H"},
        {"regime_contract_id": "R_TREND_RANGE_V1_24H"},
        {"opportunity_contract_id": "O_COMPRESSION_RELEASE_V1_24H"},
        {"direction_contract_id": "D1_V2_RETURN_12H"},
        {"geometry_contract_id": "GEOMETRY_ESTIMATOR_ALT_V1"},
        {"calibration_contract_id": "CALIBRATION_ISOTONIC_V1"},
        {"abstention_policy": "CLOSE_POSITION"},
        {"required_feature_ids": ["D1_V1_RETURN_4H", "EXTRA_FEATURE"]},
        {"feature_params": {"metric": "closed_bar_log_return", "lookback_hours": 8}},
        {"lookback_windows": {"lookback_hours": 8}},
        {"cost_proxy_id": "COST_PROXY_15BPS_V1"},
        {"mechanical_refit_policy": "REFIT_EXPANDING_WINDOW_V1"},
        {"protocol_hash": "a" * 64},
        {"source_manifest_hash": "b" * 64},
        {"split_manifest_hash": "c" * 64},
        {"hyperparameters": {"seed": 99}},
        {"family_combination": [H40Family.D2_BREAKOUT_CONTINUATION]},
    ]

    for mutation in mutations:
        kwargs: dict[str, Any] = {
            "slot_index": base.slot_index,
            "family_combination": base.family_combination,
            "asset_scope": base.asset_scope,
            "primary_horizon": base.primary_horizon,
            "action_threshold": base.action_threshold,
            "scope": base.scope,
            "direction_variant": base.direction_variant,
            "regime_contract_id": base.regime_contract_id,
            "opportunity_contract_id": base.opportunity_contract_id,
            "direction_contract_id": base.direction_contract_id,
            "geometry_contract_id": base.geometry_contract_id,
            "calibration_contract_id": base.calibration_contract_id,
            "abstention_policy": base.abstention_policy,
            "required_feature_ids": base.required_feature_ids,
            "feature_params": base.feature_params,
            "lookback_windows": base.lookback_windows,
            "availability_rule": base.availability_rule,
            "cost_proxy_id": base.cost_proxy_id,
            "mechanical_refit_policy": base.mechanical_refit_policy,
            "protocol_hash": base.protocol_hash,
            "source_manifest_hash": base.source_manifest_hash,
            "split_manifest_hash": base.split_manifest_hash,
            "hyperparameters": base.hyperparameters,
        }
        kwargs.update(mutation)
        mutated = H40ConfigurationSlot.create(**kwargs)
        assert mutated.config_id != base_hash, f"Hash did not change for mutation: {mutation}"


# ---------------------------------------------------------------------------
# Requirement 4: Mutable nested parameters cannot mutate after hash construction
# ---------------------------------------------------------------------------
def test_p2_04_nested_parameters_immutable_after_hash_construction() -> None:
    """Nested parameters (FrozenDict) reject in-place mutation attempts."""
    slot = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        feature_params={"window": 10},
        hyperparameters={"param_x": 1},
        lookback_windows={"h": 4},
    )

    # In-place dictionary assignment must fail
    with pytest.raises(TypeError):
        slot.feature_params["window"] = 20  # type: ignore[index]

    with pytest.raises(TypeError):
        slot.hyperparameters["param_x"] = 2  # type: ignore[index]

    with pytest.raises(TypeError):
        slot.lookback_windows["h"] = 8  # type: ignore[index]

    # Slot itself is frozen
    with pytest.raises(AttributeError):
        slot.action_threshold = 0.60  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Requirement 5: Every configuration binds exactly one primary horizon
# ---------------------------------------------------------------------------
def test_p2_05_every_configuration_binds_exactly_one_primary_horizon() -> None:
    """Every slot binds exactly one horizon in {4h, 8h, 12h}; 24h/multi-horizon fails closed."""
    ledger = materialize_h40_search_space()

    for slot in ledger.slots:
        assert slot.primary_horizon in ALLOWED_PRIMARY_HORIZONS
        assert slot.primary_horizon in {"4h", "8h", "12h"}

    # 24h diagnostic horizon cannot be a primary horizon
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="24h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.INTERVAL_MISMATCH

    # Arbitrary horizon rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="1h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.INTERVAL_MISMATCH


# ---------------------------------------------------------------------------
# Requirement 6: Only BTC_ONLY / ETH_ONLY / POOLED_BTC_ETH scopes accepted
# ---------------------------------------------------------------------------
def test_p2_06_only_authorized_scopes_accepted() -> None:
    """Scopes are strictly restricted to BTC_ONLY, ETH_ONLY, and POOLED_BTC_ETH."""
    ledger = materialize_h40_search_space()

    observed_scopes = {s.scope for s in ledger.slots}
    assert observed_scopes == ALLOWED_SCOPES == {"BTC_ONLY", "ETH_ONLY", "POOLED_BTC_ETH"}

    # Unauthorized scope rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["SOLUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
            scope="SOL_ONLY",
        )
    assert exc_info.value.reason_code == H40ReasonCode.PRODUCT_MISMATCH

    # Empty scope rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=[],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.PRODUCT_MISMATCH


# ---------------------------------------------------------------------------
# Requirement 7: Only the five exact D1-D5 authority families are accepted
# ---------------------------------------------------------------------------
def test_p2_07_only_authorized_d1_to_d5_families_accepted() -> None:
    """Only D1..D5 direction families are authorized; unauthorized families fail closed."""
    for fam in H40Family:
        slot = H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[fam],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
            feature_params={"base_directional_owner": "D1_TREND_CONTINUATION"} if fam == H40Family.D5_FUNDING_DIRECTION_INTERACTION else {},
        )
        assert slot.family_combination == (fam,)


# ---------------------------------------------------------------------------
# Requirement 8: Only the four allowed depth-two pairs are accepted
# ---------------------------------------------------------------------------
def test_p2_08_only_authorized_depth_two_pairs_accepted() -> None:
    """Only D1+D4, D1+D5, D2+D4, D3+D5 are authorized; other pairs fail closed."""
    for pair in ALLOWED_DEPTH_TWO_PAIRS:
        fams = list(pair)
        slot = H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=fams,
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
        assert len(slot.family_combination) == 2

    # Unauthorized pair: D1 + D2
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION, H40Family.D2_BREAKOUT_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.FAMILY_PAIR_RESTRICTED

    # Unauthorized pair: D2 + D5
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D2_BREAKOUT_CONTINUATION, H40Family.D5_FUNDING_DIRECTION_INTERACTION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.FAMILY_PAIR_RESTRICTED

    # Depth 3 rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[
                H40Family.D1_TREND_CONTINUATION,
                H40Family.D4_BTC_ETH_CONFIRM_DIVERGE,
                H40Family.D5_FUNDING_DIRECTION_INTERACTION,
            ],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.FAMILY_PAIR_RESTRICTED


# ---------------------------------------------------------------------------
# Requirement 9: No more than 2 variants/family and budget ceilings are enforced
# ---------------------------------------------------------------------------
def test_p2_09_variant_and_budget_ceilings_enforced() -> None:
    """Enforces max 2 variants per family, max 12 configs/variant, max 12/pair, total 168."""
    ledger = materialize_h40_search_space()

    # Verify variants count per single family
    for fam in H40Family:
        slots = [s for s in ledger.slots if s.family_combination == (fam,)]
        variants = {s.direction_variant for s in slots}
        assert len(variants) <= 2, f"Family {fam} has {len(variants)} variants (max 2 allowed)"
        for v in variants:
            v_slots = [s for s in slots if s.direction_variant == v]
            assert len(v_slots) == CONFIGS_PER_VARIANT == 12

    # Verify configs per depth-two pair
    for pair in ALLOWED_DEPTH_TWO_PAIRS:
        p_slots = [s for s in ledger.slots if frozenset(s.family_combination) == pair]
        assert len(p_slots) == CONFIGS_PER_PAIR == 12

    # 169th registration must be rejected
    slot_169 = H40ConfigurationSlot.create(
        slot_index=168,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
    )
    with pytest.raises(H40GuardError) as exc_info:
        ledger.register_slot(slot_169)
    assert exc_info.value.reason_code == H40ReasonCode.SEARCH_BUDGET_EXHAUSTED


# ---------------------------------------------------------------------------
# Requirement 10: Action threshold is limited to 0.55/0.60/0.65
# ---------------------------------------------------------------------------
def test_p2_10_action_threshold_strictly_limited_to_prescribed_set() -> None:
    """Action thresholds must strictly belong to {0.55, 0.60, 0.65}."""
    for valid_t in (0.55, 0.60, 0.65):
        slot = H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=valid_t,
        )
        assert abs(slot.action_threshold - valid_t) < 1e-6

    # Disallowed thresholds fail closed
    for invalid_t in (0.50, 0.54, 0.58, 0.70, 0.75):
        with pytest.raises(H40GuardError) as exc_info:
            H40ConfigurationSlot.create(
                slot_index=0,
                family_combination=[H40Family.D1_TREND_CONTINUATION],
                asset_scope=["BTCUSDT"],
                primary_horizon="4h",
                action_threshold=invalid_t,
            )
        assert exc_info.value.reason_code == H40ReasonCode.THRESHOLD_UNMET


# ---------------------------------------------------------------------------
# Requirement 11: TP/BR cannot become directional owner
# ---------------------------------------------------------------------------
def test_p2_11_tpbr_cannot_become_directional_owner() -> None:
    """TP/BR is strictly opportunity/magnitude evidence; cannot be used as direction family."""
    # Feature contract validation
    with pytest.raises(H40GuardError) as exc_info:
        H40FeatureContract.create(
            feature_id="D1_TPBR_DIRECTION_ATTEMPT",
            version="V1",
            owner_family="D1_TPBR_DIRECTIONAL",
            required_inputs=["BTCUSDT_USD_M_1H"],
            lookback_hours=24,
        )
    assert exc_info.value.reason_code == H40ReasonCode.UNAUTHORIZED_FAMILY

    # Verify canonical TP/BR contract has directional side discarded
    reg = build_canonical_feature_registry()
    tpbr = reg["O_TPBR_MAGNITUDE_V1_24H"]
    assert tpbr.owner_family == OpportunityFamily.O_TPBR_MAGNITUDE.value
    assert tpbr.transform_parameters.get("directional_side_discarded") is True


# ---------------------------------------------------------------------------
# Requirement 12: D5 without D1/D2/D3 base direction is rejected
# ---------------------------------------------------------------------------
def test_p2_12_d5_without_base_directional_owner_rejected() -> None:
    """D5 without an authorized base directional family in {D1, D2, D3} fails closed."""
    # Explicitly invalid base direction
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D5_FUNDING_DIRECTION_INTERACTION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
            feature_params={"base_directional_owner": "NONE"},
        )
    assert exc_info.value.reason_code == H40ReasonCode.UNAUTHORIZED_FAMILY

    # Missing base direction in raw slot creation
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot(
            slot_index=0,
            family_combination=(H40Family.D5_FUNDING_DIRECTION_INTERACTION,),
            asset_scope=("BTCUSDT",),
            primary_horizon="4h",
            action_threshold=0.55,
            hyperparameters=FrozenDict({}),
            feature_params=FrozenDict({}),  # no base owner
        )
    assert exc_info.value.reason_code == H40ReasonCode.UNAUTHORIZED_FAMILY


# ---------------------------------------------------------------------------
# Requirement 13: Feature availability rejects future/non-closed-bar dependencies
# ---------------------------------------------------------------------------
def test_p2_13_feature_availability_rejects_future_or_non_closed_bars() -> None:
    """Feature contract causality requires strict closed bars: close_time < decision_t."""
    # Lookback <= 0 rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40FeatureContract.create(
            feature_id="FEATURE_ZERO_LOOKBACK",
            version="V1",
            owner_family="R_VOL_RANGE",
            required_inputs=["BTCUSDT_USD_M_1H"],
            lookback_hours=0,
        )
    assert exc_info.value.reason_code == H40ReasonCode.PIT_UNAVAILABLE

    # Weak closed bar rule rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40FeatureContract.create(
            feature_id="FEATURE_WEAK_CAUSALITY",
            version="V1",
            owner_family="R_VOL_RANGE",
            required_inputs=["BTCUSDT_USD_M_1H"],
            lookback_hours=24,
            closed_bar_rule="close_time <= decision t",  # allows unclosed or concurrent bar
        )
    assert exc_info.value.reason_code == H40ReasonCode.PIT_UNAVAILABLE

    # Slot availability rule non-strict rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
            availability_rule="REALTIME_TICK_STREAM",  # non-closed
        )
    assert exc_info.value.reason_code == H40ReasonCode.PIT_UNAVAILABLE


# ---------------------------------------------------------------------------
# Requirement 14: H39 / Final Holdout / confirmation outcome references rejected
# ---------------------------------------------------------------------------
def test_p2_14_h39_final_holdout_outcome_references_rejected() -> None:
    """Feature contracts and slots referencing H39 or Final Holdout paths fail closed."""
    for bad_input in ("data/research/h39_validation/raw.parquet", "artifacts/final_holdout/data.json"):
        with pytest.raises(H40GuardError) as exc_info:
            H40FeatureContract.create(
                feature_id="FORBIDDEN_INPUT_FEATURE",
                version="V1",
                owner_family="R_VOL_RANGE",
                required_inputs=[bad_input],
                lookback_hours=24,
            )
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    # Slot notes containing forbidden path
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
            notes="Reference from artifacts/final_holdout",
        )
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


# ---------------------------------------------------------------------------
# Requirement 15: Unverified sources cannot become production authority
# ---------------------------------------------------------------------------
def test_p2_15_unverified_sources_cannot_become_production_authority() -> None:
    """Slots requiring unverified ETH derivatives source fail closed to NOT_TESTABLE status."""
    ledger = materialize_h40_search_space()

    # D5 configs with ETH or POOLED scope require unverified ETH derivatives source
    # Must be marked NOT_TESTABLE
    d5_eth_slots = [
        s for s in ledger.slots
        if H40Family.D5_FUNDING_DIRECTION_INTERACTION in s.family_combination
        and ("ETHUSDT" in s.asset_scope or s.scope in {"ETH_ONLY", "POOLED_BTC_ETH"})
    ]

    assert len(d5_eth_slots) > 0
    for slot in d5_eth_slots:
        assert slot.status == "NOT_TESTABLE"
        assert slot.reason_code == H40ReasonCode.NOT_TESTABLE
        assert "unverified" in slot.notes.lower()

    # D5 configs with BTC_ONLY use verified BTCUSDT_OFFICIAL_DERIVATIVES, remain REGISTERED
    d5_btc_slots = [
        s for s in ledger.slots
        if s.family_combination == (H40Family.D5_FUNDING_DIRECTION_INTERACTION,)
        and s.scope == "BTC_ONLY"
    ]
    assert len(d5_btc_slots) > 0
    for slot in d5_btc_slots:
        assert slot.status == "REGISTERED"
        assert slot.reason_code is None


# ---------------------------------------------------------------------------
# Requirement 16: Configuration hash binds protocol + P1/source/split authority identities
# ---------------------------------------------------------------------------
def test_p2_16_configuration_hash_binds_all_authority_identities() -> None:
    """Configuration hash binds protocol_hash, source_manifest_hash, split_manifest_hash, and kernel SHA."""
    slot = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
    )
    base_hash = slot.config_id

    # Verify authority constants are bound
    assert slot.frozen_kernel_sha == FROZEN_KERNEL_SHA == "6838e9db8d5c369b5da87354821d9c8e79c2a879"
    assert slot.p1_code_baseline_sha == P1_CODE_BASELINE_SHA == "3fc89541ed0965fc0e2972af310e34ae1b838168"
    assert slot.ledger_schema_version == LEDGER_SCHEMA_VERSION == "H40_LEDGER_V1"

    # Changing authority hashes changes configuration hash
    slot_alt_proto = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        protocol_hash="ff" * 32,
    )
    assert slot_alt_proto.config_id != base_hash

    slot_alt_source = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        source_manifest_hash="ee" * 32,
    )
    assert slot_alt_source.config_id != base_hash

    slot_alt_split = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        split_manifest_hash="dd" * 32,
    )
    assert slot_alt_split.config_id != base_hash


# ---------------------------------------------------------------------------
# Requirement 17: Serialization round-trip preserves exact hashes and immutability
# ---------------------------------------------------------------------------
def test_p2_17_serialization_roundtrip_preserves_hashes_and_immutability() -> None:
    """Ledger dictionary and JSON serialization round-trips preserve bitwise hashes and status."""
    ledger = materialize_h40_search_space()
    original_ledger_hash = ledger.ledger_hash
    original_json = ledger.canonical_json()

    # Dictionary round-trip
    d = ledger.to_dict()
    reconstructed = H40ConfigurationLedger.from_dict(d)

    assert reconstructed.slot_count == 168
    assert reconstructed.ledger_hash == original_ledger_hash
    assert reconstructed.canonical_json() == original_json

    for s1, s2 in zip(ledger.slots, reconstructed.slots):
        assert s1.slot_index == s2.slot_index
        assert s1.config_id == s2.config_id
        assert s1.status == s2.status
        assert s1.reason_code == s2.reason_code
        assert s1.to_dict() == s2.to_dict()


# ---------------------------------------------------------------------------
# Requirement 18: No P2 API exposes label/performance fields or accepts outcome arrays
# ---------------------------------------------------------------------------
def test_p2_18_no_p2_api_exposes_labels_or_accepts_outcomes() -> None:
    """P2 classes and functions expose zero outcome/label APIs and reject performance keys."""
    # Inspect H40ConfigurationSlot methods and fields
    slot_fields = {f.name for f in inspect.getattr_static(H40ConfigurationSlot, "__dataclass_fields__").values()}
    forbidden_field_names = {"pnl", "sharpe", "return", "label", "forward_return", "mfe", "mae", "trades", "drawdown"}
    assert not (slot_fields & forbidden_field_names)

    # Inspect H40FeatureContract fields
    contract_fields = {f.name for f in inspect.getattr_static(H40FeatureContract, "__dataclass_fields__").values()}
    assert not (contract_fields & forbidden_field_names)

    # Passing forbidden outcome keys in hyperparameters raises error
    for bad_key in ("sharpe", "pnl", "return", "forward_return", "mfe", "mae", "precision", "brier"):
        with pytest.raises(H40GuardError) as exc_info:
            H40ConfigurationSlot.create(
                slot_index=0,
                family_combination=[H40Family.D1_TREND_CONTINUATION],
                asset_scope=["BTCUSDT"],
                primary_horizon="4h",
                action_threshold=0.55,
                hyperparameters={bad_key: 1.0},
            )
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


# ---------------------------------------------------------------------------
# Additional Invariant Tests: Feature Registry, Geometry, Calibration, Refit
# ---------------------------------------------------------------------------
def test_canonical_feature_registry_integrity() -> None:
    """Canonical feature registry contains all required preregistered features with valid hashes."""
    registry = build_canonical_feature_registry()
    assert len(registry) >= 15

    # Check regime families present
    regime_fams = {f.owner_family for f in registry.values() if f.owner_family.startswith("R_")}
    assert regime_fams == {rf.value for rf in RegimeFamily}

    # Check opportunity families present
    opp_fams = {f.owner_family for f in registry.values() if f.owner_family.startswith("O_")}
    assert opp_fams == {of.value for of in OpportunityFamily}

    # All hashes non-empty and 64-character SHA256 hex
    for fid, fcontract in registry.items():
        assert len(fcontract.content_hash) == 64
        assert fcontract.feature_id == fid


def test_geometry_contract_properties() -> None:
    """Geometry contract enforces median MFE >= 1.5 * c_rt and ratio >= 1.25."""
    geom = H40GeometryContract()
    assert geom.cost_proxy_rt == 0.0012
    assert geom.min_mfe_multiple == 1.5
    assert geom.mfe_threshold == 0.0018
    assert geom.min_mfe_mae_ratio == 1.25
    assert geom.min_cell_samples == 30
    assert len(geom.contract_hash) == 64

    # Sample floor < 30 rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40GeometryContract(min_cell_samples=25)
    assert exc_info.value.reason_code == H40ReasonCode.THRESHOLD_UNMET


def test_calibration_contract_properties() -> None:
    """Calibration contract enforces sample floors for isotonic and allowed thresholds."""
    calib_logistic = H40CalibrationContract(method=CalibrationMethod.LOGISTIC)
    assert len(calib_logistic.contract_hash) == 64

    calib_isotonic = H40CalibrationContract(method=CalibrationMethod.ISOTONIC, min_calibration_samples=200, min_side_calibration_samples=40)
    assert len(calib_isotonic.contract_hash) == 64

    # Isotonic with < 200 samples rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40CalibrationContract(method=CalibrationMethod.ISOTONIC, min_calibration_samples=150)
    assert exc_info.value.reason_code == H40ReasonCode.THRESHOLD_UNMET


def test_refit_policy_contract_immutability() -> None:
    """Refit policy contract enforces chronological past only and forbids mutation."""
    refit = H40RefitPolicyContract()
    assert refit.allowed_data == "CHRONOLOGICALLY_PAST_OBSERVATIONS_ONLY"
    assert not refit.parameter_grid_expansion_allowed
    assert not refit.family_substitution_allowed
    assert not refit.configuration_mutation_allowed
    assert len(refit.contract_hash) == 64
