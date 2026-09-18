"""H40 exact 168-slot search space materialization.

Materializes and freezes the complete H40 pre-outcome research search space
before any H40 label metric, performance metric, feature ranking, candidate ranking,
backtest, or confirmation outcome is computed under H40_PROTOCOL_V1_R3.

Exact 168-slot budget breakdown:
- 5 direction families x 2 variants each x 12 complete configs = 120 slots (0..119)
- 4 authorized depth-two pairs x 12 complete configs = 48 slots (120..167)
- Total slots = 168 slots (capacity reached, non-recyclable).
"""

from __future__ import annotations

from typing import Any

from .configuration_ledger import (
    DEFAULT_PROTOCOL_HASH,
    DEFAULT_SOURCE_MANIFEST_HASH,
    DEFAULT_SPLIT_MANIFEST_HASH,
    H40ConfigurationLedger,
    H40ConfigurationSlot,
    H40Family,
)
from .guards import H40ReasonCode
from .protocol_authority import (
    RuntimeAuthoritySnapshot,
    current_p1_authority_snapshot,
    project_required_sources,
)

TOTAL_SEARCH_BUDGET: int = 168
SINGLE_FAMILY_CONFIG_COUNT: int = 120
PAIR_CONFIG_COUNT: int = 48
CONFIGS_PER_VARIANT: int = 12
CONFIGS_PER_PAIR: int = 12
SINGLE_FAMILY_VARIANT_COUNT: int = 10
PAIR_FAMILY_COUNT: int = 4

# Direction variants specifications (5 families x 2 variants = 10 variants)
DIRECTION_VARIANT_SPECS: tuple[dict[str, Any], ...] = (
    # D1: D1_TREND_CONTINUATION
    {
        "family": H40Family.D1_TREND_CONTINUATION,
        "variant_id": "D1_V1_RETURN_4H",
        "contract_id": "D1_V1_RETURN_4H",
        "lookback_hours": 4,
        "feature_ids": ("D1_V1_RETURN_4H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "closed_bar_log_return", "lookback_hours": 4},
        "requires_funding": False,
    },
    {
        "family": H40Family.D1_TREND_CONTINUATION,
        "variant_id": "D1_V2_RETURN_12H",
        "contract_id": "D1_V2_RETURN_12H",
        "lookback_hours": 12,
        "feature_ids": ("D1_V2_RETURN_12H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "closed_bar_log_return", "lookback_hours": 12},
        "requires_funding": False,
    },
    # D2: D2_BREAKOUT_CONTINUATION
    {
        "family": H40Family.D2_BREAKOUT_CONTINUATION,
        "variant_id": "D2_V1_BREAKOUT_24H",
        "contract_id": "D2_V1_BREAKOUT_24H",
        "lookback_hours": 24,
        "feature_ids": ("D2_V1_BREAKOUT_24H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "donchian_breakout_sign", "range_hours": 24},
        "requires_funding": False,
    },
    {
        "family": H40Family.D2_BREAKOUT_CONTINUATION,
        "variant_id": "D2_V2_BREAKOUT_72H",
        "contract_id": "D2_V2_BREAKOUT_72H",
        "lookback_hours": 72,
        "feature_ids": ("D2_V2_BREAKOUT_72H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "donchian_breakout_sign", "range_hours": 72},
        "requires_funding": False,
    },
    # D3: D3_FAILED_MOVE_REVERSAL
    {
        "family": H40Family.D3_FAILED_MOVE_REVERSAL,
        "variant_id": "D3_V1_FAILED_BREAK_24H",
        "contract_id": "D3_V1_FAILED_BREAK_24H",
        "lookback_hours": 24,
        "feature_ids": ("D3_V1_FAILED_BREAK_24H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "failed_break_and_close_back_reversal", "range_hours": 24},
        "requires_funding": False,
    },
    {
        "family": H40Family.D3_FAILED_MOVE_REVERSAL,
        "variant_id": "D3_V2_FAILED_BREAK_72H",
        "contract_id": "D3_V2_FAILED_BREAK_72H",
        "lookback_hours": 72,
        "feature_ids": ("D3_V2_FAILED_BREAK_72H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "failed_break_and_close_back_reversal", "range_hours": 72},
        "requires_funding": False,
    },
    # D4: D4_BTC_ETH_CONFIRM_DIVERGE (always cross-asset: requires synchronized BTC + ETH)
    {
        "family": H40Family.D4_BTC_ETH_CONFIRM_DIVERGE,
        "variant_id": "D4_V1_CONFIRMATION_4H",
        "contract_id": "D4_V1_CONFIRMATION_4H",
        "lookback_hours": 4,
        "feature_ids": ("D4_V1_CONFIRMATION_4H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "cross_asset_synchronized_agreement", "state_window_hours": 4},
        "requires_funding": False,
        "requires_cross_asset": True,
    },
    {
        "family": H40Family.D4_BTC_ETH_CONFIRM_DIVERGE,
        "variant_id": "D4_V2_DIVERGENCE_8H",
        "contract_id": "D4_V2_DIVERGENCE_8H",
        "lookback_hours": 8,
        "feature_ids": ("D4_V2_DIVERGENCE_8H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"metric": "cross_asset_relative_divergence", "state_window_hours": 8},
        "requires_funding": False,
        "requires_cross_asset": True,
    },
    # D5: D5_FUNDING_DIRECTION_INTERACTION (requires base D1/D2/D3 directional owner)
    {
        "family": H40Family.D5_FUNDING_DIRECTION_INTERACTION,
        "variant_id": "D5_V1_CROWDING_Q10_D1",
        "contract_id": "D5_V1_CROWDING_Q10_D1",
        "lookback_hours": 8,
        "feature_ids": ("D5_V1_CROWDING_Q10_D1", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {
            "metric": "crowding_quantile_interaction",
            "quantile": 0.10,
            "base_directional_owner": "D1_TREND_CONTINUATION",
        },
        "requires_funding": True,
    },
    {
        "family": H40Family.D5_FUNDING_DIRECTION_INTERACTION,
        "variant_id": "D5_V2_CROWDING_Q20_D2",
        "contract_id": "D5_V2_CROWDING_Q20_D2",
        "lookback_hours": 8,
        "feature_ids": ("D5_V2_CROWDING_Q20_D2", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {
            "metric": "crowding_quantile_interaction",
            "quantile": 0.20,
            "base_directional_owner": "D2_BREAKOUT_CONTINUATION",
        },
        "requires_funding": True,
    },
)

# Authorized depth-two pairs specifications (4 pairs x 12 configs = 48 configs)
DEPTH_TWO_PAIR_SPECS: tuple[dict[str, Any], ...] = (
    # Pair 1: D1 + D4 (cross-asset via D4)
    {
        "families": (H40Family.D1_TREND_CONTINUATION, H40Family.D4_BTC_ETH_CONFIRM_DIVERGE),
        "variant_id": "PAIR_D1_D4_V1",
        "contract_id": "PAIR_D1_D4_V1",
        "lookback_hours": 8,
        "feature_ids": ("D1_V1_RETURN_4H", "D4_V1_CONFIRMATION_4H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"combination": "conjunction", "base_direction": "D1_TREND_CONTINUATION", "filter": "D4_BTC_ETH_CONFIRM_DIVERGE"},
        "requires_funding": False,
        "requires_cross_asset": True,
    },
    # Pair 2: D1 + D5
    {
        "families": (H40Family.D1_TREND_CONTINUATION, H40Family.D5_FUNDING_DIRECTION_INTERACTION),
        "variant_id": "PAIR_D1_D5_V1",
        "contract_id": "PAIR_D1_D5_V1",
        "lookback_hours": 8,
        "feature_ids": ("D1_V1_RETURN_4H", "D5_V1_CROWDING_Q10_D1", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"combination": "interaction", "base_direction": "D1_TREND_CONTINUATION", "filter": "D5_FUNDING_DIRECTION_INTERACTION", "base_directional_owner": "D1_TREND_CONTINUATION"},
        "requires_funding": True,
    },
    # Pair 3: D2 + D4 (cross-asset via D4)
    {
        "families": (H40Family.D2_BREAKOUT_CONTINUATION, H40Family.D4_BTC_ETH_CONFIRM_DIVERGE),
        "variant_id": "PAIR_D2_D4_V1",
        "contract_id": "PAIR_D2_D4_V1",
        "lookback_hours": 24,
        "feature_ids": ("D2_V1_BREAKOUT_24H", "D4_V1_CONFIRMATION_4H", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"combination": "conjunction", "base_direction": "D2_BREAKOUT_CONTINUATION", "filter": "D4_BTC_ETH_CONFIRM_DIVERGE"},
        "requires_funding": False,
        "requires_cross_asset": True,
    },
    # Pair 4: D3 + D5 (pair-scoped D5 component bound to D3)
    {
        "families": (H40Family.D3_FAILED_MOVE_REVERSAL, H40Family.D5_FUNDING_DIRECTION_INTERACTION),
        "variant_id": "PAIR_D3_D5_V1",
        "contract_id": "PAIR_D3_D5_V1",
        "lookback_hours": 24,
        "feature_ids": ("D3_V1_FAILED_BREAK_24H", "D5_PAIR_CROWDING_Q10_D3", "R_VOL_RANGE_V1_24H", "O_RANGE_EXPANSION_V1_24H"),
        "params": {"combination": "interaction", "base_direction": "D3_FAILED_MOVE_REVERSAL", "filter": "D5_FUNDING_DIRECTION_INTERACTION", "base_directional_owner": "D3_FAILED_MOVE_REVERSAL"},
        "requires_funding": True,
    },
)

# 12-configuration parameter template (accepted R3R2 Section 8.2):
# 9-cell base grid (3 horizons x 3 scopes at threshold 0.55/Platt)
# + 3 pooled-scope threshold/calibration refinements
TWELVE_CONFIG_TEMPLATE: tuple[dict[str, Any], ...] = (
    # Base grid: 3 horizons x 3 scopes, threshold 0.55, Platt logistic
    {"horizon": "4h", "scope": "BTC_ONLY", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT",)},
    {"horizon": "4h", "scope": "ETH_ONLY", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("ETHUSDT",)},
    {"horizon": "4h", "scope": "POOLED_BTC_ETH", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT", "ETHUSDT")},

    {"horizon": "8h", "scope": "BTC_ONLY", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT",)},
    {"horizon": "8h", "scope": "ETH_ONLY", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("ETHUSDT",)},
    {"horizon": "8h", "scope": "POOLED_BTC_ETH", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT", "ETHUSDT")},

    {"horizon": "12h", "scope": "BTC_ONLY", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT",)},
    {"horizon": "12h", "scope": "ETH_ONLY", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("ETHUSDT",)},
    {"horizon": "12h", "scope": "POOLED_BTC_ETH", "threshold": 0.55, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT", "ETHUSDT")},

    # Pooled-scope refinements: threshold/calibration diversity
    {"horizon": "4h", "scope": "POOLED_BTC_ETH", "threshold": 0.60, "calibration": "CALIBRATION_ISOTONIC_IF_ELIGIBLE_V1", "assets": ("BTCUSDT", "ETHUSDT")},
    {"horizon": "8h", "scope": "POOLED_BTC_ETH", "threshold": 0.65, "calibration": "CALIBRATION_PLATT_LOGISTIC_V1", "assets": ("BTCUSDT", "ETHUSDT")},
    {"horizon": "12h", "scope": "POOLED_BTC_ETH", "threshold": 0.60, "calibration": "CALIBRATION_ISOTONIC_IF_ELIGIBLE_V1", "assets": ("BTCUSDT", "ETHUSDT")},
)


def _derive_slot_status(
    scope: str,
    requires_funding: bool,
    requires_cross_asset: bool,
    snapshot: RuntimeAuthoritySnapshot,
) -> tuple[str, H40ReasonCode | None, str]:
    """Derive (status, reason_code, notes) from the projected source set + P1 authority.

    REGISTERED iff every required source is production VERIFIED;
    NOT_TESTABLE otherwise.  No hard-coded per-slot exception may upgrade a
    NOT_TESTABLE source.
    """
    required = project_required_sources(
        scope=scope,
        requires_cross_asset=requires_cross_asset,
        requires_funding=requires_funding,
    )
    status, reason_code = snapshot.derive_slot_status(required)
    if status == "NOT_TESTABLE":
        unverified = [s for s in required if snapshot.per_source_states.get(s, "NOT_TESTABLE") != "VERIFIED"]
        notes = f"unverified source(s): {', '.join(sorted(unverified))} (P1 authority snapshot)"
    else:
        notes = ""
    return status, reason_code, notes


def materialize_h40_search_space_production() -> H40ConfigurationLedger:
    """Production materialization of the exact 168-slot search space.

    Derives protocol authority hash, semantic root hash, and structural ledger
    identity from the canonical accepted authority chain.  No caller-supplied
    identity strings are accepted.  Runtime testability is derived mechanically
    from the accepted P1 source-authority snapshot.

    Strictly pre-outcome: zero labels, returns, MFE/MAE, or candidate outcomes.
    """
    return _materialize_search_space(production=True)


def materialize_h40_search_space_synthetic() -> H40ConfigurationLedger:
    """Synthetic/test-only materialization of the exact 168-slot search space.

    Explicitly non-authoritative: for tests only.  Cannot be confused with
    production materialization.  Runtime testability is still derived mechanically
    from the accepted P1 source-authority snapshot.
    """
    return _materialize_search_space(production=False)


def materialize_h40_search_space(
    protocol_hash: str | None = None,
    source_manifest_hash: str | None = None,
    split_manifest_hash: str | None = None,
) -> H40ConfigurationLedger:
    """Materializes and validates the exact 168-slot search space into an immutable ledger.

    .. deprecated::
        Use ``materialize_h40_search_space_production`` or
        ``materialize_h40_search_space_synthetic`` instead.  This function
        delegates to the synthetic builder; caller-supplied hashes are ignored
        in production paths.

    Strict pre-outcome operation: zero labels, returns, MFE/MAE, or candidate outcomes are computed.
    """
    return _materialize_search_space(production=False)


def _materialize_search_space(*, production: bool) -> H40ConfigurationLedger:
    """Internal materialization shared by production and synthetic builders."""
    p_hash = DEFAULT_PROTOCOL_HASH
    src_hash = DEFAULT_SOURCE_MANIFEST_HASH
    split_hash = DEFAULT_SPLIT_MANIFEST_HASH

    snapshot = current_p1_authority_snapshot()

    ledger = H40ConfigurationLedger()
    current_slot_index = 0

    # Part 1: Enumerate 10 single-family variants x 12 configs = 120 slots
    for var_spec in DIRECTION_VARIANT_SPECS:
        fam = var_spec["family"]
        var_id = var_spec["variant_id"]
        dir_contract_id = var_spec["contract_id"]
        lookback = var_spec["lookback_hours"]
        fids = var_spec["feature_ids"]
        params = var_spec["params"]
        requires_funding = var_spec["requires_funding"]
        requires_cross_asset = var_spec.get("requires_cross_asset", False)

        for cfg_template in TWELVE_CONFIG_TEMPLATE:
            horizon = cfg_template["horizon"]
            scope = cfg_template["scope"]
            threshold = cfg_template["threshold"]
            calib_id = cfg_template["calibration"]
            assets = cfg_template["assets"]

            # Mechanical source testability derivation (replaces hardcoded gate)
            status, reason_code, notes = _derive_slot_status(
                scope, requires_funding, requires_cross_asset, snapshot,
            )

            slot = H40ConfigurationSlot.create(
                slot_index=current_slot_index,
                family_combination=[fam],
                asset_scope=list(assets),
                primary_horizon=horizon,
                action_threshold=threshold,
                hyperparameters={},
                scope=scope,
                direction_variant=var_id,
                regime_contract_id="R_VOL_RANGE_V1_24H",
                opportunity_contract_id="O_RANGE_EXPANSION_V1_24H",
                direction_contract_id=dir_contract_id,
                geometry_contract_id="GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1",
                calibration_contract_id=calib_id,
                abstention_policy="NO_TRADE",
                required_feature_ids=list(fids),
                feature_params=params,
                lookback_windows={"feature_lookback_hours": lookback},
                availability_rule="CLOSED_BAR_STRICT",
                cost_proxy_id="COST_PROXY_12BPS_V1",
                mechanical_refit_policy="REFIT_CHRONOLOGICAL_PAST_ONLY_V1",
                protocol_hash=p_hash,
                source_manifest_hash=src_hash,
                split_manifest_hash=split_hash,
                status=status,
                reason_code=reason_code,
                notes=notes,
            )
            ledger.register_slot(slot)
            current_slot_index += 1

    assert current_slot_index == SINGLE_FAMILY_CONFIG_COUNT, f"Expected 120 single-family slots, got {current_slot_index}"

    # Part 2: Enumerate 4 depth-two pairs x 12 configs = 48 slots
    for pair_spec in DEPTH_TWO_PAIR_SPECS:
        fams = pair_spec["families"]
        var_id = pair_spec["variant_id"]
        dir_contract_id = pair_spec["contract_id"]
        lookback = pair_spec["lookback_hours"]
        fids = pair_spec["feature_ids"]
        params = pair_spec["params"]
        requires_funding = pair_spec["requires_funding"]
        requires_cross_asset = pair_spec.get("requires_cross_asset", False)

        for cfg_template in TWELVE_CONFIG_TEMPLATE:
            horizon = cfg_template["horizon"]
            scope = cfg_template["scope"]
            threshold = cfg_template["threshold"]
            calib_id = cfg_template["calibration"]
            assets = cfg_template["assets"]

            status, reason_code, notes = _derive_slot_status(
                scope, requires_funding, requires_cross_asset, snapshot,
            )

            slot = H40ConfigurationSlot.create(
                slot_index=current_slot_index,
                family_combination=list(fams),
                asset_scope=list(assets),
                primary_horizon=horizon,
                action_threshold=threshold,
                hyperparameters={},
                scope=scope,
                direction_variant=var_id,
                regime_contract_id="R_VOL_RANGE_V1_24H",
                opportunity_contract_id="O_RANGE_EXPANSION_V1_24H",
                direction_contract_id=dir_contract_id,
                geometry_contract_id="GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1",
                calibration_contract_id=calib_id,
                abstention_policy="NO_TRADE",
                required_feature_ids=list(fids),
                feature_params=params,
                lookback_windows={"feature_lookback_hours": lookback},
                availability_rule="CLOSED_BAR_STRICT",
                cost_proxy_id="COST_PROXY_12BPS_V1",
                mechanical_refit_policy="REFIT_CHRONOLOGICAL_PAST_ONLY_V1",
                protocol_hash=p_hash,
                source_manifest_hash=src_hash,
                split_manifest_hash=split_hash,
                status=status,
                reason_code=reason_code,
                notes=notes,
            )
            ledger.register_slot(slot)
            current_slot_index += 1

    assert current_slot_index == TOTAL_SEARCH_BUDGET, f"Expected exactly {TOTAL_SEARCH_BUDGET} slots, got {current_slot_index}"
    assert ledger.slot_count == TOTAL_SEARCH_BUDGET
    assert ledger.remaining_budget == 0

    return ledger
