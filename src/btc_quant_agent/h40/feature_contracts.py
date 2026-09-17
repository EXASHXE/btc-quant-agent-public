"""H40 feature contracts and semantic owner specifications.

Freezes semantic feature contracts for regime, opportunity, direction, geometry,
and calibration policies under H40_PROTOCOL_V1_R2 strictly prior to outcome evaluation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..research_contract.canonical import (
    FrozenDict,
    canonical_sha256,
    thaw_json,
)
from .guards import H40GuardError, H40ProtectedSurfaceGuard, H40ReasonCode

# Forbidden tokens / substrings in feature definitions
FORBIDDEN_OUTCOME_TOKENS: frozenset[str] = frozenset({
    "return",
    "forward_return",
    "pnl",
    "label",
    "sharpe",
    "profit_factor",
    "mfe",
    "mae",
    "drawdown",
    "win_rate",
    "precision",
    "expectancy",
    "brier",
    "ece",
    "p_value",
    "hac",
    "bootstrap",
    "future",
    "h39",
    "final_holdout",
})


class RegimeFamily(str, Enum):
    """Authorized regime families from BASE Section 5.1."""

    R_VOL_RANGE = "R_VOL_RANGE"
    R_TREND_RANGE = "R_TREND_RANGE"
    R_LIQ_ACTIVITY = "R_LIQ_ACTIVITY"
    R_CROSS_ASSET = "R_CROSS_ASSET"
    R_FUNDING_CROWDING = "R_FUNDING_CROWDING"


class OpportunityFamily(str, Enum):
    """Authorized opportunity families from BASE Section 5.2."""

    O_RANGE_EXPANSION = "O_RANGE_EXPANSION"
    O_COMPRESSION_RELEASE = "O_COMPRESSION_RELEASE"
    O_BREAKOUT_DISTANCE = "O_BREAKOUT_DISTANCE"
    O_EXPECTED_EXCURSION = "O_EXPECTED_EXCURSION"
    O_TPBR_MAGNITUDE = "O_TPBR_MAGNITUDE"


class CalibrationMethod(str, Enum):
    """Authorized calibration policies from BASE Section 5.5."""

    LOGISTIC = "LOGISTIC"
    ISOTONIC = "ISOTONIC"


@dataclass(frozen=True)
class H40FeatureContract:
    """Deterministic pre-outcome semantic specification for an H40 feature."""

    feature_id: str
    version: str
    owner_family: str
    required_inputs: tuple[str, ...]
    lookback_hours: int
    timestamp_rule: str
    closed_bar_rule: str
    missing_data_behavior: str
    transform_parameters: FrozenDict
    product_scope: tuple[str, ...]
    requires_cross_asset: bool
    requires_funding_authority: bool
    output_schema: FrozenDict

    def __post_init__(self) -> None:
        # Check forbidden tokens in feature_id and owner_family
        fid_lower = self.feature_id.lower()
        for token in FORBIDDEN_OUTCOME_TOKENS:
            if token in fid_lower:
                # Allowed exception for standard lookback phrases if they don't indicate future returns
                if token in {"return"} and ("forward" in fid_lower or "target" in fid_lower):
                    raise H40GuardError(
                        H40ReasonCode.PROTECTED_SURFACE_DENIED,
                        f"Forbidden outcome reference '{token}' in feature ID '{self.feature_id}'.",
                    )
                if token in {"future", "h39", "final_holdout", "sharpe", "pnl", "mfe", "mae"}:
                    raise H40GuardError(
                        H40ReasonCode.PROTECTED_SURFACE_DENIED,
                        f"Forbidden outcome reference '{token}' in feature ID '{self.feature_id}'.",
                    )

        # Check protected surface locators
        for inp in self.required_inputs:
            H40ProtectedSurfaceGuard.assert_path_allowed(inp)
            inp_lower = inp.lower()
            for token in ("h39", "final_holdout"):
                if token in inp_lower:
                    raise H40GuardError(
                        H40ReasonCode.PROTECTED_SURFACE_DENIED,
                        f"Feature required input '{inp}' violates protected surface guard.",
                    )

        # Lookback must be strictly positive
        if self.lookback_hours <= 0:
            raise H40GuardError(
                H40ReasonCode.PIT_UNAVAILABLE,
                f"Lookback hours ({self.lookback_hours}) must be positive and non-zero.",
            )

        # Closed-bar causality rule must be strict: close_time < decision_t (strictly less than, never <=)
        if "<" not in self.closed_bar_rule or "<=" in self.closed_bar_rule:
            raise H40GuardError(
                H40ReasonCode.PIT_UNAVAILABLE,
                f"Closed bar rule '{self.closed_bar_rule}' violates strict point-in-time causality (must be strictly '<').",
            )

        # TP/BR magnitude rule: TP/BR is strictly opportunity evidence, NEVER direction
        if "TPBR" in self.owner_family or "TPBR" in self.feature_id:
            if "D" in self.owner_family and ("D1" in self.owner_family or "D2" in self.owner_family or "D3" in self.owner_family or "D4" in self.owner_family or "D5" in self.owner_family):
                raise H40GuardError(
                    H40ReasonCode.UNAUTHORIZED_FAMILY,
                    "TP/BR remains magnitude/opportunity evidence only; directional side is discarded.",
                )

        # Check transform parameters for outcome metrics
        for k in self.transform_parameters:
            if k.lower() in FORBIDDEN_OUTCOME_TOKENS:
                raise H40GuardError(
                    H40ReasonCode.PROTECTED_SURFACE_DENIED,
                    f"Forbidden transform parameter '{k}' in feature contract.",
                )

    @property
    def content_hash(self) -> str:
        """Returns deterministic content hash of the feature contract specification."""
        payload = {
            "feature_id": self.feature_id,
            "version": self.version,
            "owner_family": self.owner_family,
            "required_inputs": sorted(self.required_inputs),
            "lookback_hours": self.lookback_hours,
            "timestamp_rule": self.timestamp_rule,
            "closed_bar_rule": self.closed_bar_rule,
            "missing_data_behavior": self.missing_data_behavior,
            "transform_parameters": thaw_json(self.transform_parameters),
            "product_scope": sorted(self.product_scope),
            "requires_cross_asset": self.requires_cross_asset,
            "requires_funding_authority": self.requires_funding_authority,
            "output_schema": thaw_json(self.output_schema),
        }
        return canonical_sha256(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serializes feature contract to dictionary."""
        return {
            "feature_id": self.feature_id,
            "version": self.version,
            "owner_family": self.owner_family,
            "required_inputs": list(self.required_inputs),
            "lookback_hours": self.lookback_hours,
            "timestamp_rule": self.timestamp_rule,
            "closed_bar_rule": self.closed_bar_rule,
            "missing_data_behavior": self.missing_data_behavior,
            "transform_parameters": thaw_json(self.transform_parameters),
            "product_scope": list(self.product_scope),
            "requires_cross_asset": self.requires_cross_asset,
            "requires_funding_authority": self.requires_funding_authority,
            "output_schema": thaw_json(self.output_schema),
            "content_hash": self.content_hash,
        }

    @classmethod
    def create(
        cls,
        feature_id: str,
        version: str,
        owner_family: str,
        required_inputs: tuple[str, ...] | list[str],
        lookback_hours: int,
        timestamp_rule: str = "CLOSED_BAR_PRE_DECISION",
        closed_bar_rule: str = "close_time < decision t",
        missing_data_behavior: str = "FAIL_CLOSED_NO_TRADE",
        transform_parameters: Mapping[str, Any] | None = None,
        product_scope: tuple[str, ...] | list[str] = ("BTCUSDT", "ETHUSDT"),
        requires_cross_asset: bool = False,
        requires_funding_authority: bool = False,
        output_schema: Mapping[str, Any] | None = None,
    ) -> H40FeatureContract:
        """Factory creating frozen feature contract."""
        return cls(
            feature_id=feature_id,
            version=version,
            owner_family=owner_family,
            required_inputs=tuple(required_inputs),
            lookback_hours=lookback_hours,
            timestamp_rule=timestamp_rule,
            closed_bar_rule=closed_bar_rule,
            missing_data_behavior=missing_data_behavior,
            transform_parameters=FrozenDict(transform_parameters or {}),
            product_scope=tuple(product_scope),
            requires_cross_asset=requires_cross_asset,
            requires_funding_authority=requires_funding_authority,
            output_schema=FrozenDict(output_schema or {"dtype": "float64", "shape": [1]}),
        )


@dataclass(frozen=True)
class H40GeometryContract:
    """Pre-outcome specification for excursion and geometry screening gates.

    Enforces BASE Section 3.3 and 5.4:
    - estimated median MFE >= 1.5 * c_rt (where c_rt = 0.0012)
    - estimated median MFE / max(estimated median MAE, c_rt) >= 1.25
    - sample floor >= 30 training observations in estimation cell; otherwise INSUFFICIENT_CELL_N / NO_TRADE
    """

    cost_proxy_rt: float = 0.0012
    min_mfe_multiple: float = 1.5
    min_mfe_mae_ratio: float = 1.25
    min_cell_samples: int = 30
    estimator_id: str = "GEOMETRY_ESTIMATOR_WF1_CELL_MEDIAN_V1"
    fallback_behavior: str = "FAIL_CLOSED_NO_TRADE"
    reason_code_insufficient: H40ReasonCode = H40ReasonCode.NOT_TESTABLE

    def __post_init__(self) -> None:
        if self.cost_proxy_rt <= 0.0:
            raise H40GuardError(
                H40ReasonCode.THRESHOLD_UNMET,
                f"Geometry screening cost proxy must be positive, got {self.cost_proxy_rt}.",
            )
        if self.min_cell_samples < 30:
            raise H40GuardError(
                H40ReasonCode.THRESHOLD_UNMET,
                f"Geometry gate sample floor cannot be lower than 30 observations, got {self.min_cell_samples}.",
            )

    @property
    def mfe_threshold(self) -> float:
        """Returns the minimum estimated median MFE threshold."""
        return round(self.min_mfe_multiple * self.cost_proxy_rt, 6)

    @property
    def contract_hash(self) -> str:
        """Deterministic canonical hash for geometry contract."""
        payload = {
            "cost_proxy_rt": round(self.cost_proxy_rt, 6),
            "min_mfe_multiple": self.min_mfe_multiple,
            "min_mfe_mae_ratio": self.min_mfe_mae_ratio,
            "min_cell_samples": self.min_cell_samples,
            "estimator_id": self.estimator_id,
            "fallback_behavior": self.fallback_behavior,
            "reason_code_insufficient": self.reason_code_insufficient.value,
        }
        return canonical_sha256(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serializes geometry contract to dictionary."""
        return {
            "cost_proxy_rt": self.cost_proxy_rt,
            "min_mfe_multiple": self.min_mfe_multiple,
            "min_mfe_mae_ratio": self.min_mfe_mae_ratio,
            "min_cell_samples": self.min_cell_samples,
            "estimator_id": self.estimator_id,
            "fallback_behavior": self.fallback_behavior,
            "reason_code_insufficient": self.reason_code_insufficient.value,
            "contract_hash": self.contract_hash,
        }


@dataclass(frozen=True)
class H40CalibrationContract:
    """Pre-outcome specification for probability calibration and action decision policies.

    Enforces BASE Section 5.5:
    - Logistic (Platt) or Isotonic
    - Isotonic requires >= 200 calibration obs and >= 40 per predicted side
    - Action thresholds strictly in {0.55, 0.60, 0.65}
    - Adaptive-bin ECE <= 0.05 with min 20 obs/bin
    """

    method: CalibrationMethod
    min_calibration_samples: int = 200
    min_side_calibration_samples: int = 40
    allowed_thresholds: tuple[float, ...] = (0.55, 0.60, 0.65)
    max_ece: float = 0.05
    min_bin_samples: int = 20
    action_decision_rule: str = "LONG if p_up >= q; SHORT if p_up <= 1 - q; else NO_TRADE"
    abstention_policy: str = "DEFAULT_NO_TRADE"

    def __post_init__(self) -> None:
        if self.method == CalibrationMethod.ISOTONIC:
            if self.min_calibration_samples < 200:
                raise H40GuardError(
                    H40ReasonCode.THRESHOLD_UNMET,
                    f"Isotonic calibration requires >= 200 total calibration samples, got {self.min_calibration_samples}.",
                )
            if self.min_side_calibration_samples < 40:
                raise H40GuardError(
                    H40ReasonCode.THRESHOLD_UNMET,
                    f"Isotonic calibration requires >= 40 samples per predicted side, got {self.min_side_calibration_samples}.",
                )

    @property
    def contract_hash(self) -> str:
        """Deterministic canonical hash for calibration contract."""
        payload = {
            "method": self.method.value,
            "min_calibration_samples": self.min_calibration_samples,
            "min_side_calibration_samples": self.min_side_calibration_samples,
            "allowed_thresholds": list(self.allowed_thresholds),
            "max_ece": self.max_ece,
            "min_bin_samples": self.min_bin_samples,
            "action_decision_rule": self.action_decision_rule,
            "abstention_policy": self.abstention_policy,
        }
        return canonical_sha256(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serializes calibration contract to dictionary."""
        return {
            "method": self.method.value,
            "min_calibration_samples": self.min_calibration_samples,
            "min_side_calibration_samples": self.min_side_calibration_samples,
            "allowed_thresholds": list(self.allowed_thresholds),
            "max_ece": self.max_ece,
            "min_bin_samples": self.min_bin_samples,
            "action_decision_rule": self.action_decision_rule,
            "abstention_policy": self.abstention_policy,
            "contract_hash": self.contract_hash,
        }


@dataclass(frozen=True)
class H40RefitPolicyContract:
    """Pre-outcome specification for chronological mechanical refits."""

    policy_id: str = "REFIT_CHRONOLOGICAL_PAST_ONLY_V1"
    allowed_data: str = "CHRONOLOGICALLY_PAST_OBSERVATIONS_ONLY"
    parameter_grid_expansion_allowed: bool = False
    family_substitution_allowed: bool = False
    configuration_mutation_allowed: bool = False

    @property
    def contract_hash(self) -> str:
        """Deterministic canonical hash for mechanical refit policy."""
        payload = {
            "policy_id": self.policy_id,
            "allowed_data": self.allowed_data,
            "parameter_grid_expansion_allowed": self.parameter_grid_expansion_allowed,
            "family_substitution_allowed": self.family_substitution_allowed,
            "configuration_mutation_allowed": self.configuration_mutation_allowed,
        }
        return canonical_sha256(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serializes refit policy contract to dictionary."""
        return {
            "policy_id": self.policy_id,
            "allowed_data": self.allowed_data,
            "parameter_grid_expansion_allowed": self.parameter_grid_expansion_allowed,
            "family_substitution_allowed": self.family_substitution_allowed,
            "configuration_mutation_allowed": self.configuration_mutation_allowed,
            "contract_hash": self.contract_hash,
        }


def build_canonical_feature_registry() -> dict[str, H40FeatureContract]:
    """Materializes and freezes the canonical preregistered H40 feature contracts."""
    registry: dict[str, H40FeatureContract] = {}

    # --- Regime Family Contracts ---
    # R1: R_VOL_RANGE_V1 (trailing 24h realized volatility / true range percentile)
    r1 = H40FeatureContract.create(
        feature_id="R_VOL_RANGE_V1_24H",
        version="V1",
        owner_family=RegimeFamily.R_VOL_RANGE.value,
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "realized_volatility_percentile", "window_hours": 24},
    )
    registry[r1.feature_id] = r1

    # R2: R_TREND_RANGE_V1 (trailing efficiency / trend strength over 24h, 72h, 168h)
    for w in (24, 72, 168):
        fid = f"R_TREND_RANGE_V1_{w}H"
        r2 = H40FeatureContract.create(
            feature_id=fid,
            version="V1",
            owner_family=RegimeFamily.R_TREND_RANGE.value,
            required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
            lookback_hours=w,
            transform_parameters={"metric": "trend_efficiency_ratio", "window_hours": w},
        )
        registry[fid] = r2

    # R3: R_LIQ_ACTIVITY_V1 (quote volume / activity percentile over 24h)
    r3 = H40FeatureContract.create(
        feature_id="R_LIQ_ACTIVITY_V1_24H",
        version="V1",
        owner_family=RegimeFamily.R_LIQ_ACTIVITY.value,
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "quote_volume_percentile", "window_hours": 24},
    )
    registry[r3.feature_id] = r3

    # R4: R_CROSS_ASSET_V1 (synchronized BTC/ETH relative volatility/trend state)
    r4 = H40FeatureContract.create(
        feature_id="R_CROSS_ASSET_V1_24H",
        version="V1",
        owner_family=RegimeFamily.R_CROSS_ASSET.value,
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        requires_cross_asset=True,
        transform_parameters={"metric": "relative_volatility_spread", "window_hours": 24},
    )
    registry[r4.feature_id] = r4

    # R5: R_FUNDING_CROWDING_V1 (last-settled funding / crowding state)
    r5 = H40FeatureContract.create(
        feature_id="R_FUNDING_CROWDING_V1_8H",
        version="V1",
        owner_family=RegimeFamily.R_FUNDING_CROWDING.value,
        required_inputs=["BTCUSDT_OFFICIAL_DERIVATIVES"],
        lookback_hours=8,
        requires_funding_authority=True,
        transform_parameters={"metric": "last_settled_funding_rate", "window_hours": 8},
    )
    registry[r5.feature_id] = r5

    # --- Opportunity Family Contracts ---
    # O1: O_RANGE_EXPANSION_V1 (lagged range expansion)
    o1 = H40FeatureContract.create(
        feature_id="O_RANGE_EXPANSION_V1_24H",
        version="V1",
        owner_family=OpportunityFamily.O_RANGE_EXPANSION.value,
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "true_range_expansion", "window_hours": 24},
    )
    registry[o1.feature_id] = o1

    # O2: O_COMPRESSION_RELEASE_V1 (compression state followed by expansion)
    for w in (24, 72):
        fid = f"O_COMPRESSION_RELEASE_V1_{w}H"
        o2 = H40FeatureContract.create(
            feature_id=fid,
            version="V1",
            owner_family=OpportunityFamily.O_COMPRESSION_RELEASE.value,
            required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
            lookback_hours=w,
            transform_parameters={"metric": "bollinger_bandwidth_release", "window_hours": w},
        )
        registry[fid] = o2

    # O3: O_BREAKOUT_DISTANCE_V1 (absolute distance from prior range boundary)
    for w in (24, 72, 168):
        fid = f"O_BREAKOUT_DISTANCE_V1_{w}H"
        o3 = H40FeatureContract.create(
            feature_id=fid,
            version="V1",
            owner_family=OpportunityFamily.O_BREAKOUT_DISTANCE.value,
            required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
            lookback_hours=w,
            transform_parameters={"metric": "donchian_boundary_distance", "window_hours": w},
        )
        registry[fid] = o3

    # O4: O_EXPECTED_EXCURSION_V1 (training-only magnitude estimate)
    o4 = H40FeatureContract.create(
        feature_id="O_EXPECTED_EXCURSION_V1_24H",
        version="V1",
        owner_family=OpportunityFamily.O_EXPECTED_EXCURSION.value,
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "cell_conditional_atr", "window_hours": 24},
    )
    registry[o4.feature_id] = o4

    # O5: O_TPBR_MAGNITUDE_V1 (unprotected, independently versioned TP/BR magnitude flag; directional side discarded)
    o5 = H40FeatureContract.create(
        feature_id="O_TPBR_MAGNITUDE_V1_24H",
        version="V1",
        owner_family=OpportunityFamily.O_TPBR_MAGNITUDE.value,
        required_inputs=["BTCUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "tpbr_envelope_magnitude", "directional_side_discarded": True},
    )
    registry[o5.feature_id] = o5

    # --- Direction Family Contracts ---
    # D1: D1_TREND_CONTINUATION (lookbacks: 4h, 8h, 12h, 24h; 2 variants)
    d1_v1 = H40FeatureContract.create(
        feature_id="D1_V1_RETURN_4H",
        version="V1",
        owner_family="D1_TREND_CONTINUATION",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=4,
        transform_parameters={"metric": "closed_bar_log_return", "lookback_hours": 4},
    )
    registry[d1_v1.feature_id] = d1_v1

    d1_v2 = H40FeatureContract.create(
        feature_id="D1_V2_RETURN_12H",
        version="V1",
        owner_family="D1_TREND_CONTINUATION",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=12,
        transform_parameters={"metric": "closed_bar_log_return", "lookback_hours": 12},
    )
    registry[d1_v2.feature_id] = d1_v2

    # D2: D2_BREAKOUT_CONTINUATION (lookbacks: 24h, 72h, 168h; 2 variants)
    d2_v1 = H40FeatureContract.create(
        feature_id="D2_V1_BREAKOUT_24H",
        version="V1",
        owner_family="D2_BREAKOUT_CONTINUATION",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "donchian_breakout_sign", "range_hours": 24},
    )
    registry[d2_v1.feature_id] = d2_v1

    d2_v2 = H40FeatureContract.create(
        feature_id="D2_V2_BREAKOUT_72H",
        version="V1",
        owner_family="D2_BREAKOUT_CONTINUATION",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=72,
        transform_parameters={"metric": "donchian_breakout_sign", "range_hours": 72},
    )
    registry[d2_v2.feature_id] = d2_v2

    # D3: D3_FAILED_MOVE_REVERSAL (lookbacks: 24h, 72h; 2 variants)
    d3_v1 = H40FeatureContract.create(
        feature_id="D3_V1_FAILED_BREAK_24H",
        version="V1",
        owner_family="D3_FAILED_MOVE_REVERSAL",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=24,
        transform_parameters={"metric": "failed_break_and_close_back_reversal", "range_hours": 24},
    )
    registry[d3_v1.feature_id] = d3_v1

    d3_v2 = H40FeatureContract.create(
        feature_id="D3_V2_FAILED_BREAK_72H",
        version="V1",
        owner_family="D3_FAILED_MOVE_REVERSAL",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=72,
        transform_parameters={"metric": "failed_break_and_close_back_reversal", "range_hours": 72},
    )
    registry[d3_v2.feature_id] = d3_v2

    # D4: D4_BTC_ETH_CONFIRM_DIVERGE (windows: 4h, 8h, 12h; 2 variants: confirmation and divergence)
    d4_v1 = H40FeatureContract.create(
        feature_id="D4_V1_CONFIRMATION_4H",
        version="V1",
        owner_family="D4_BTC_ETH_CONFIRM_DIVERGE",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=4,
        requires_cross_asset=True,
        transform_parameters={"metric": "cross_asset_synchronized_agreement", "state_window_hours": 4},
    )
    registry[d4_v1.feature_id] = d4_v1

    d4_v2 = H40FeatureContract.create(
        feature_id="D4_V2_DIVERGENCE_8H",
        version="V1",
        owner_family="D4_BTC_ETH_CONFIRM_DIVERGE",
        required_inputs=["BTCUSDT_USD_M_1H", "ETHUSDT_USD_M_1H"],
        lookback_hours=8,
        requires_cross_asset=True,
        transform_parameters={"metric": "cross_asset_relative_divergence", "state_window_hours": 8},
    )
    registry[d4_v2.feature_id] = d4_v2

    # D5: D5_FUNDING_DIRECTION_INTERACTION (quantiles: 0.10, 0.20; requires base D1/D2/D3 directional owner)
    d5_v1 = H40FeatureContract.create(
        feature_id="D5_V1_CROWDING_Q10_D1",
        version="V1",
        owner_family="D5_FUNDING_DIRECTION_INTERACTION",
        required_inputs=["BTCUSDT_OFFICIAL_DERIVATIVES", "BTCUSDT_USD_M_1H"],
        lookback_hours=8,
        requires_funding_authority=True,
        transform_parameters={"metric": "crowding_quantile_interaction", "quantile": 0.10, "base_directional_owner": "D1_TREND_CONTINUATION"},
    )
    registry[d5_v1.feature_id] = d5_v1

    d5_v2 = H40FeatureContract.create(
        feature_id="D5_V2_CROWDING_Q20_D1",
        version="V1",
        owner_family="D5_FUNDING_DIRECTION_INTERACTION",
        required_inputs=["BTCUSDT_OFFICIAL_DERIVATIVES", "BTCUSDT_USD_M_1H"],
        lookback_hours=8,
        requires_funding_authority=True,
        transform_parameters={"metric": "crowding_quantile_interaction", "quantile": 0.20, "base_directional_owner": "D1_TREND_CONTINUATION"},
    )
    registry[d5_v2.feature_id] = d5_v2

    return registry
