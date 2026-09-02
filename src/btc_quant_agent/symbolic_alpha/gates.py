from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class GateResult:
    key: str
    status: GateStatus
    observed: Any
    required: Any
    reason: str | None = None


@dataclass(frozen=True)
class CandidateGateConfig:
    candidate_must_pass_all: bool
    minimum_discovery_events: int
    minimum_validation_events: int
    minimum_pseudo_forward_events: int
    minimum_long_fraction: float
    maximum_long_fraction: float
    minimum_discovery_net_mean_return_8h: float
    minimum_validation_net_mean_return_8h: float
    minimum_pseudo_forward_net_mean_return_8h: float
    minimum_validation_bootstrap_ci_low: float
    minimum_pseudo_forward_bootstrap_ci_low: float
    chronological_fold_count: int
    minimum_positive_validation_folds: int
    minimum_positive_pseudo_forward_folds: int
    required_multiple_testing_adjusted_pass: bool
    maximum_pairwise_candidate_correlation: float
    minimum_sandbox_trade_count: int
    minimum_net_profit_factor: float
    maximum_drawdown_r: float
    maximum_losing_streak: int
    minimum_positive_sandbox_folds: int
    fees_bps_round_trip: float
    slippage_bps_round_trip: float
    funding_included: bool
    cost_stress_multiplier: float
    minimum_cost_stress_net_r: float
    sandbox_not_applicable_rule: str
    unknown_or_unused_key_rule: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CandidateGateConfig:
        expected = set(cls.__dataclass_fields__)
        actual = set(raw)
        if actual != expected:
            unknown = sorted(actual - expected)
            missing = sorted(expected - actual)
            raise ValueError(f"candidate gate schema mismatch unknown={unknown} missing={missing}")
        config = cls(**raw)
        if not config.candidate_must_pass_all:
            raise ValueError("formal candidate gate requires candidate_must_pass_all=true")
        if config.unknown_or_unused_key_rule != "FORMAL_RUN_FAILS_CLOSED":
            raise ValueError("unknown gate policy must fail closed")
        return config


@dataclass(frozen=True)
class FormulaGateEvidence:
    discovery_events: int
    validation_events: int
    pseudo_forward_events: int
    long_fraction: float | None
    discovery_net_mean_return_8h: float | None
    validation_net_mean_return_8h: float | None
    pseudo_forward_net_mean_return_8h: float | None
    validation_bootstrap_ci_low: float | None
    pseudo_forward_bootstrap_ci_low: float | None
    positive_validation_folds: int
    positive_pseudo_forward_folds: int
    multiple_testing_adjusted_pass: bool
    maximum_pairwise_candidate_correlation: float | None


@dataclass(frozen=True)
class SandboxGateEvidence:
    trade_count: int
    net_profit_factor: float | None
    max_drawdown_r: float | None
    maximum_losing_streak: int | None
    positive_folds: int
    fees_applied: bool
    slippage_applied: bool
    funding_applied: bool
    cost_stress_net_r: float | None


@dataclass(frozen=True)
class CandidateGateAudit:
    results: tuple[GateResult, ...]
    consumed_protocol_keys: tuple[str, ...]
    passed_all: bool


def _minimum(key: str, observed: float | None, required: float) -> GateResult:
    passed = observed is not None and observed >= required
    return GateResult(key, GateStatus.PASS if passed else GateStatus.FAIL, observed, required)


def _maximum(key: str, observed: float | None, required: float) -> GateResult:
    passed = observed is not None and observed <= required
    return GateResult(key, GateStatus.PASS if passed else GateStatus.FAIL, observed, required)


def evaluate_candidate_gates(
    config: CandidateGateConfig,
    formula: FormulaGateEvidence,
    sandbox: SandboxGateEvidence | None,
) -> CandidateGateAudit:
    results = [
        _minimum(
            "minimum_discovery_events", formula.discovery_events, config.minimum_discovery_events
        ),
        _minimum(
            "minimum_validation_events", formula.validation_events, config.minimum_validation_events
        ),
        _minimum(
            "minimum_pseudo_forward_events",
            formula.pseudo_forward_events,
            config.minimum_pseudo_forward_events,
        ),
        _minimum("minimum_long_fraction", formula.long_fraction, config.minimum_long_fraction),
        _maximum("maximum_long_fraction", formula.long_fraction, config.maximum_long_fraction),
        _minimum(
            "minimum_discovery_net_mean_return_8h",
            formula.discovery_net_mean_return_8h,
            config.minimum_discovery_net_mean_return_8h,
        ),
        _minimum(
            "minimum_validation_net_mean_return_8h",
            formula.validation_net_mean_return_8h,
            config.minimum_validation_net_mean_return_8h,
        ),
        _minimum(
            "minimum_pseudo_forward_net_mean_return_8h",
            formula.pseudo_forward_net_mean_return_8h,
            config.minimum_pseudo_forward_net_mean_return_8h,
        ),
        _minimum(
            "minimum_validation_bootstrap_ci_low",
            formula.validation_bootstrap_ci_low,
            config.minimum_validation_bootstrap_ci_low,
        ),
        _minimum(
            "minimum_pseudo_forward_bootstrap_ci_low",
            formula.pseudo_forward_bootstrap_ci_low,
            config.minimum_pseudo_forward_bootstrap_ci_low,
        ),
        GateResult(
            "chronological_fold_count",
            GateStatus.PASS if config.chronological_fold_count > 0 else GateStatus.FAIL,
            config.chronological_fold_count,
            ">0",
        ),
        _minimum(
            "minimum_positive_validation_folds",
            formula.positive_validation_folds,
            config.minimum_positive_validation_folds,
        ),
        _minimum(
            "minimum_positive_pseudo_forward_folds",
            formula.positive_pseudo_forward_folds,
            config.minimum_positive_pseudo_forward_folds,
        ),
        GateResult(
            "required_multiple_testing_adjusted_pass",
            GateStatus.PASS if formula.multiple_testing_adjusted_pass else GateStatus.FAIL,
            formula.multiple_testing_adjusted_pass,
            config.required_multiple_testing_adjusted_pass,
        ),
        _maximum(
            "maximum_pairwise_candidate_correlation",
            formula.maximum_pairwise_candidate_correlation,
            config.maximum_pairwise_candidate_correlation,
        ),
    ]
    upstream_passed = all(item.status == GateStatus.PASS for item in results)
    sandbox_keys = (
        "minimum_sandbox_trade_count",
        "minimum_net_profit_factor",
        "maximum_drawdown_r",
        "maximum_losing_streak",
        "minimum_positive_sandbox_folds",
        "fees_bps_round_trip",
        "slippage_bps_round_trip",
        "funding_included",
        "cost_stress_multiplier",
        "minimum_cost_stress_net_r",
    )
    if not upstream_passed:
        results.extend(
            GateResult(
                key,
                GateStatus.NOT_APPLICABLE,
                None,
                getattr(config, key),
                "UPSTREAM_FORMULA_GATE_FAILED",
            )
            for key in sandbox_keys
        )
    elif sandbox is None:
        results.extend(
            GateResult(
                key,
                GateStatus.FAIL,
                None,
                getattr(config, key),
                "MISSING_REQUIRED_SANDBOX_EVIDENCE",
            )
            for key in sandbox_keys
        )
    else:
        results.extend(
            [
                _minimum(
                    "minimum_sandbox_trade_count",
                    sandbox.trade_count,
                    config.minimum_sandbox_trade_count,
                ),
                _minimum(
                    "minimum_net_profit_factor",
                    sandbox.net_profit_factor,
                    config.minimum_net_profit_factor,
                ),
                _maximum("maximum_drawdown_r", sandbox.max_drawdown_r, config.maximum_drawdown_r),
                _maximum(
                    "maximum_losing_streak",
                    sandbox.maximum_losing_streak,
                    config.maximum_losing_streak,
                ),
                _minimum(
                    "minimum_positive_sandbox_folds",
                    sandbox.positive_folds,
                    config.minimum_positive_sandbox_folds,
                ),
                GateResult(
                    "fees_bps_round_trip",
                    GateStatus.PASS if sandbox.fees_applied else GateStatus.FAIL,
                    sandbox.fees_applied,
                    config.fees_bps_round_trip,
                ),
                GateResult(
                    "slippage_bps_round_trip",
                    GateStatus.PASS if sandbox.slippage_applied else GateStatus.FAIL,
                    sandbox.slippage_applied,
                    config.slippage_bps_round_trip,
                ),
                GateResult(
                    "funding_included",
                    GateStatus.PASS
                    if sandbox.funding_applied == config.funding_included
                    else GateStatus.FAIL,
                    sandbox.funding_applied,
                    config.funding_included,
                ),
                GateResult(
                    "cost_stress_multiplier",
                    GateStatus.PASS if config.cost_stress_multiplier >= 1 else GateStatus.FAIL,
                    config.cost_stress_multiplier,
                    ">=1",
                ),
                _minimum(
                    "minimum_cost_stress_net_r",
                    sandbox.cost_stress_net_r,
                    config.minimum_cost_stress_net_r,
                ),
            ]
        )
    results.extend(
        [
            GateResult(
                "candidate_must_pass_all", GateStatus.PASS, config.candidate_must_pass_all, True
            ),
            GateResult(
                "sandbox_not_applicable_rule",
                GateStatus.PASS,
                config.sandbox_not_applicable_rule,
                "FROZEN",
            ),
            GateResult(
                "unknown_or_unused_key_rule",
                GateStatus.PASS,
                config.unknown_or_unused_key_rule,
                "FORMAL_RUN_FAILS_CLOSED",
            ),
        ]
    )
    consumed = tuple(item.key for item in results)
    expected = tuple(config.__dataclass_fields__)
    if set(consumed) != set(expected) or len(consumed) != len(set(consumed)):
        raise RuntimeError("candidate gate evaluator did not consume every key exactly once")
    passed = all(item.status in {GateStatus.PASS, GateStatus.NOT_APPLICABLE} for item in results)
    passed = passed and upstream_passed and (sandbox is not None)
    return CandidateGateAudit(tuple(results), consumed, passed)
