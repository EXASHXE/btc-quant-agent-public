from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from .config import MarketWatchConfig
from .evidence import TacticalFeatureEvidenceV2
from .grid_shadow_evidence import TacticalGridShadowEvaluationV1
from .shadow_evidence import (
    RULE_SCORE_BUCKETS,
    FundingStatus,
    TacticalShadowEvaluationV2,
    classify_rule_score_bucket,
)
from .trend_shadow import TrendEvidenceV2Shadow, summarize_trend_evidence_v2_shadow

TACTICAL_DECISION_QUALITY_CONTRACT_VERSION = "V0.5.5_B_LINE_TACTICAL_DECISION_QUALITY_R1"
FROZEN_TACTICAL_PREDECESSOR_SHA = "52c16a28153de307dc6132c0975fe29341a0a918"


class TacticalDecisionQualityDecision(StrEnum):
    PASS = "TACTICAL_DECISION_QUALITY_PASS"
    DIAGNOSTIC_ONLY = "TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY"
    FAIL = "TACTICAL_DECISION_QUALITY_FAIL"


@dataclass(frozen=True)
class FrozenReleaseThresholds:
    """Immutable pre-outcome release thresholds from the RC1 evaluation contract."""

    min_oos_actionable_count: int = 100
    min_long_actionable_count: int = 20
    min_short_actionable_count: int = 20
    min_oos_partitions: int = 3
    min_supported_partitions: int = 2
    min_partition_actionable_count: int = 20

    pass_mean_net_r_min: float = 0.05
    pass_median_net_r_min: float = -0.05
    pass_positive_partition_ratio_min: float = 2.0 / 3.0
    pass_stop_before_target_max: float = 0.65

    hard_fail_mean_net_r_max: float = -0.10
    hard_fail_median_net_r_max: float = -0.20
    hard_fail_partition_mean_net_r_max: float = -0.25
    hard_fail_partition_count_min: int = 2
    hard_fail_stop_before_target_min: float = 0.70
    hard_fail_min_actionable_support: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round_opt(val: float | None, digits: int = 6) -> float | None:
    if val is None or not math.isfinite(val):
        return None
    return round(float(val), digits)


def _effective_net_r(ev: TacticalShadowEvaluationV2) -> float | None:
    """Return authoritative net_R with transaction costs and funding included."""
    if ev.fill_status != "FILLED":
        return None
    if ev.net_r_after_funding is not None:
        return float(ev.net_r_after_funding)
    if ev.net_r_ex_funding is not None:
        f_r = ev.funding_accounting.funding_pnl_r or 0.0
        return float(ev.net_r_ex_funding) + float(f_r)
    return None


def _compute_max_drawdown_r(net_rs: Sequence[float]) -> float:
    """Compute maximum cumulative R drawdown across a chronological sequence of trades."""
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in net_rs:
        cum += r
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)
    return round(max_dd, 6)


def compute_subset_metrics(
    *,
    label: str,
    evidences: Sequence[TacticalFeatureEvidenceV2],
    evaluations: Sequence[TacticalShadowEvaluationV2],
    config: MarketWatchConfig | None = None,
    future_evidences_by_symbol: Mapping[str, Sequence[TacticalFeatureEvidenceV2]] | None = None,
    trend_shadows_by_feature_id: Mapping[str, TrendEvidenceV2Shadow] | None = None,
) -> dict[str, Any]:
    """Compute contract decision-quality metrics for a given cohort or partition."""
    cfg = config or MarketWatchConfig()
    sample_count = len(evidences)

    long_ev_count = 0
    short_ev_count = 0
    wait_ev_count = 0
    invalidation_breach_count = 0

    for ev in evidences:
        d_str = ev.decision_trace.final_directional_decision if ev.decision_trace else "WAIT"
        if d_str == "LONG":
            long_ev_count += 1
        elif d_str == "SHORT":
            short_ev_count += 1
        else:
            wait_ev_count += 1
        if str(ev.lifecycle_state) == "INVALIDATED":
            invalidation_breach_count += 1

    actionable_ev_count = long_ev_count + short_ev_count
    action_frequency = round(actionable_ev_count / float(sample_count), 6) if sample_count > 0 else 0.0

    sorted_evals = sorted(evaluations, key=lambda e: (e.signal_time_ms, e.symbol))
    actionable_signal_count = len(sorted_evals)
    long_signal_count = sum(1 for e in sorted_evals if e.direction == "LONG")
    short_signal_count = sum(1 for e in sorted_evals if e.direction == "SHORT")

    filled_evals = [
        e for e in sorted_evals if e.fill_status == "FILLED" and e.terminal_reason in ("TP1", "STOP", "TIMEOUT")
    ]
    no_fill_evals = [e for e in sorted_evals if e.fill_status == "NO_FILL"]
    filled_count = len(filled_evals)
    no_fill_count = len(no_fill_evals)

    tp1_count = sum(1 for e in filled_evals if e.terminal_reason == "TP1")
    tp2_count = sum(1 for e in filled_evals if e.tp2_excursion_hit and not e.sl_hit)
    stop_count = sum(1 for e in filled_evals if e.terminal_reason == "STOP")
    timeout_count = sum(1 for e in filled_evals if e.terminal_reason == "TIMEOUT")
    target_stop_resolved_count = tp1_count + stop_count

    tp1_before_sl_rate = (
        round(tp1_count / float(target_stop_resolved_count), 6) if target_stop_resolved_count > 0 else None
    )
    tp2_before_sl_rate = round(tp2_count / float(filled_count), 6) if filled_count > 0 else None
    stop_before_target = (
        round(stop_count / float(target_stop_resolved_count), 6) if target_stop_resolved_count > 0 else None
    )
    stop_rate_all_filled = round(stop_count / float(filled_count), 6) if filled_count > 0 else None

    gross_rs = [float(e.price_gross_r) for e in filled_evals if e.price_gross_r is not None]
    net_ex_rs = [float(e.net_r_ex_funding) for e in filled_evals if e.net_r_ex_funding is not None]
    net_rs = [val for e in filled_evals if (val := _effective_net_r(e)) is not None]

    mean_gross_r = _round_opt(statistics.mean(gross_rs)) if gross_rs else None
    median_gross_r = _round_opt(statistics.median(gross_rs)) if gross_rs else None
    mean_net_r_ex = _round_opt(statistics.mean(net_ex_rs)) if net_ex_rs else None
    median_net_r_ex = _round_opt(statistics.median(net_ex_rs)) if net_ex_rs else None
    mean_net_r = _round_opt(statistics.mean(net_rs)) if net_rs else None
    median_net_r = _round_opt(statistics.median(net_rs)) if net_rs else None

    # Decomposition of execution_cost_r into fees and slippage
    fee_rate = cfg.taker_fee_rate
    slip_rate = cfg.slippage_bps_per_side / 10_000.0
    total_side_rate = fee_rate + slip_rate
    fee_share = (fee_rate / total_side_rate) if total_side_rate > 0 else 0.5
    slip_share = (slip_rate / total_side_rate) if total_side_rate > 0 else 0.5

    exec_cost_rs = [float(e.execution_cost_r) for e in filled_evals if e.execution_cost_r is not None]
    fee_rs = [c * fee_share for c in exec_cost_rs]
    slip_rs = [c * slip_share for c in exec_cost_rs]
    funding_rs = [
        float(e.funding_accounting.funding_pnl_r)
        for e in filled_evals
        if e.funding_accounting.funding_pnl_r is not None
    ]
    funding_complete_count = sum(
        1 for e in filled_evals if e.funding_accounting.funding_status == FundingStatus.COMPLETE.value
    )
    settlements_total = sum(int(e.funding_accounting.settlements_count) for e in filled_evals)

    mfes = [float(e.mfe_r) for e in filled_evals if e.mfe_r is not None]
    maes = [float(e.mae_r) for e in filled_evals if e.mae_r is not None]
    holding_times = [
        int(e.time_from_fill_to_terminal_ms)
        for e in filled_evals
        if e.time_from_fill_to_terminal_ms is not None
    ]
    fill_times = [int(e.time_to_fill_ms) for e in filled_evals if e.time_to_fill_ms is not None]

    # Policy shift & technical trend transition during active holding windows
    policy_shift_count = 0
    trend_transition_count = 0
    if future_evidences_by_symbol:
        for e in filled_evals:
            sym_evs = future_evidences_by_symbol.get(e.symbol, ())
            start_t = e.fill_time_ms or e.signal_time_ms
            end_t = e.exit_time_ms or e.evaluation_end_ms or start_t
            initial_regime = e.attribution.regime_1h if e.attribution else "UNKNOWN"
            shifted = False
            transitioned = False
            for fev in sym_evs:
                if start_t < fev.decision_time_ms <= end_t:
                    f_dir = fev.decision_trace.final_directional_decision if fev.decision_trace else "WAIT"
                    if f_dir in ("LONG", "SHORT") and f_dir != e.direction:
                        shifted = True
                    f_reg = (
                        fev.market_snapshot_features.tf_1h.regime
                        if fev.market_snapshot_features and fev.market_snapshot_features.tf_1h
                        else initial_regime
                    )
                    if f_reg != initial_regime:
                        transitioned = True
            if shifted:
                policy_shift_count += 1
            if transitioned:
                trend_transition_count += 1

    shadow_transition_counts: dict[str, int] = {}
    if trend_shadows_by_feature_id:
        for ev in evidences:
            ts = trend_shadows_by_feature_id.get(ev.evidence_id)
            if ts is not None:
                shadow_transition_counts[ts.trend_transition_state] = (
                    shadow_transition_counts.get(ts.trend_transition_state, 0) + 1
                )

    return {
        "cohort_label": label,
        "sample_count": sample_count,
        "actionable_evaluation_count": actionable_ev_count,
        "action_frequency": action_frequency,
        "long_short_wait_distribution": {
            "LONG": {
                "count": long_ev_count,
                "share": round(long_ev_count / float(sample_count), 6) if sample_count > 0 else 0.0,
            },
            "SHORT": {
                "count": short_ev_count,
                "share": round(short_ev_count / float(sample_count), 6) if sample_count > 0 else 0.0,
            },
            "WAIT": {
                "count": wait_ev_count,
                "share": round(wait_ev_count / float(sample_count), 6) if sample_count > 0 else 0.0,
            },
        },
        "actionable_signal_count": actionable_signal_count,
        "long_actionable_count": long_signal_count,
        "short_actionable_count": short_signal_count,
        "filled_count": filled_count,
        "no_fill_count": no_fill_count,
        "fill_rate": round(filled_count / float(actionable_signal_count), 6) if actionable_signal_count > 0 else None,
        "target_stop_resolved_count": target_stop_resolved_count,
        "tp1_before_sl_count": tp1_count,
        "tp1_before_sl": tp1_before_sl_rate,
        "tp2_before_sl_count": tp2_count,
        "tp2_before_sl": tp2_before_sl_rate,
        "stop_before_target_count": stop_count,
        "stop_before_target": stop_before_target,
        "stop_rate_all_filled": stop_rate_all_filled,
        "timeout_count": timeout_count,
        "gross_R": {
            "mean": mean_gross_r,
            "median": median_gross_r,
            "total": _round_opt(sum(gross_rs)) if gross_rs else 0.0,
        },
        "net_R": {
            "mean": mean_net_r,
            "median": median_net_r,
            "total": _round_opt(sum(net_rs)) if net_rs else 0.0,
            "mean_ex_funding": mean_net_r_ex,
            "median_ex_funding": median_net_r_ex,
        },
        "mean_R": mean_net_r,
        "median_R": median_net_r,
        "mean_gross_R": mean_gross_r,
        "median_gross_R": median_gross_r,
        "mean_net_R": mean_net_r,
        "median_net_R": median_net_r,
        "MFE": {
            "mean_r": _round_opt(statistics.mean(mfes)) if mfes else None,
            "median_r": _round_opt(statistics.median(mfes)) if mfes else None,
            "max_r": _round_opt(max(mfes)) if mfes else None,
        },
        "MAE": {
            "mean_r": _round_opt(statistics.mean(maes)) if maes else None,
            "median_r": _round_opt(statistics.median(maes)) if maes else None,
            "max_r": _round_opt(max(maes)) if maes else None,
        },
        "drawdown_adverse_excursion": {
            "max_cumulative_net_r_drawdown": _compute_max_drawdown_r(net_rs),
            "mean_adverse_excursion_r": _round_opt(statistics.mean(maes)) if maes else None,
            "median_adverse_excursion_r": _round_opt(statistics.median(maes)) if maes else None,
            "max_adverse_excursion_r": _round_opt(max(maes)) if maes else None,
        },
        "holding_time": {
            "mean_holding_time_ms": _round_opt(statistics.mean(holding_times), 2) if holding_times else None,
            "median_holding_time_ms": _round_opt(statistics.median(holding_times), 2) if holding_times else None,
            "mean_time_to_fill_ms": _round_opt(statistics.mean(fill_times), 2) if fill_times else None,
            "median_time_to_fill_ms": _round_opt(statistics.median(fill_times), 2) if fill_times else None,
        },
        "fees": {
            "taker_fee_rate": fee_rate,
            "maker_fee_rate": cfg.maker_fee_rate,
            "mean_fee_r": _round_opt(statistics.mean(fee_rs)) if fee_rs else 0.0,
            "total_fee_r": _round_opt(sum(fee_rs)) if fee_rs else 0.0,
        },
        "slippage": {
            "slippage_bps_per_side": cfg.slippage_bps_per_side,
            "mean_slippage_r": _round_opt(statistics.mean(slip_rs)) if slip_rs else 0.0,
            "total_slippage_r": _round_opt(sum(slip_rs)) if slip_rs else 0.0,
        },
        "funding": {
            "funding_complete_count": funding_complete_count,
            "settlements_total": settlements_total,
            "mean_funding_pnl_r": _round_opt(statistics.mean(funding_rs)) if funding_rs else 0.0,
            "median_funding_pnl_r": _round_opt(statistics.median(funding_rs)) if funding_rs else 0.0,
            "total_funding_pnl_r": _round_opt(sum(funding_rs)) if funding_rs else 0.0,
        },
        "boundary_breach": {
            "stop_boundary_breach_count": stop_count,
            "stop_boundary_breach_rate": stop_rate_all_filled,
            "invalidation_breach_count": invalidation_breach_count,
        },
        "policy_shift": {
            "directional_policy_shift_count": policy_shift_count,
            "directional_policy_shift_rate": (
                round(policy_shift_count / float(filled_count), 6) if filled_count > 0 else 0.0
            ),
        },
        "trend_transition": {
            "technical_trend_transition_count": trend_transition_count,
            "technical_trend_transition_rate": (
                round(trend_transition_count / float(filled_count), 6) if filled_count > 0 else 0.0
            ),
            "shadow_trend_transition_distribution": shadow_transition_counts,
        },
    }


def compute_subgroup_diagnostics(
    *,
    evidences: Sequence[TacticalFeatureEvidenceV2],
    evaluations: Sequence[TacticalShadowEvaluationV2],
    config: MarketWatchConfig | None = None,
) -> dict[str, Any]:
    """Compute required subgroup stratifications: setup x direction, regime x direction, rule_score bucket, entry_quality bucket."""
    cfg = config or MarketWatchConfig()
    ev_by_id = {e.evidence_id: e for e in evidences}

    def _stratify(
        ev_key_fn: Any,
        eval_key_fn: Any,
        fixed_keys: Sequence[str] = (),
    ) -> dict[str, Any]:
        ev_groups: dict[str, list[TacticalFeatureEvidenceV2]] = {k: [] for k in fixed_keys}
        eval_groups: dict[str, list[TacticalShadowEvaluationV2]] = {k: [] for k in fixed_keys}
        for ev in evidences:
            k = str(ev_key_fn(ev))
            ev_groups.setdefault(k, []).append(ev)
            eval_groups.setdefault(k, [])
        for e in evaluations:
            k = str(eval_key_fn(e, ev_by_id.get(e.feature_evidence_id)))
            eval_groups.setdefault(k, []).append(e)
            ev_groups.setdefault(k, [])
        return {
            k: compute_subset_metrics(
                label=k,
                evidences=ev_groups[k],
                evaluations=eval_groups[k],
                config=cfg,
            )
            for k in sorted(ev_groups)
        }

    setup_x_direction = _stratify(
        lambda ev: f"{ev.selected_playbook or 'NO_TRADE'}__{ev.decision_trace.final_directional_decision if ev.decision_trace else 'WAIT'}",
        lambda e, _ev: f"{e.playbook}__{e.direction}",
    )

    regime_x_direction = _stratify(
        lambda ev: f"{ev.market_snapshot_features.tf_1h.regime if ev.market_snapshot_features and ev.market_snapshot_features.tf_1h else 'UNKNOWN'}__{ev.decision_trace.final_directional_decision if ev.decision_trace else 'WAIT'}",
        lambda e, _ev: f"{e.attribution.regime_1h if e.attribution else 'UNKNOWN'}__{e.direction}",
    )

    bucket_labels = [b[0] for b in RULE_SCORE_BUCKETS]
    rule_score_bucket = _stratify(
        lambda ev: classify_rule_score_bucket(ev.rule_score),
        lambda e, _ev: e.attribution.rule_score_bucket if e.attribution else "UNKNOWN",
        fixed_keys=bucket_labels,
    )

    entry_quality_bucket = _stratify(
        lambda ev: str(ev.entry_quality or "POOR"),
        lambda e, _ev: e.attribution.entry_quality if e.attribution else "POOR",
        fixed_keys=("EXCELLENT", "GOOD", "MARGINAL", "POOR"),
    )

    stability_by_market_regime = _stratify(
        lambda ev: str(
            ev.market_snapshot_features.tf_1h.regime
            if ev.market_snapshot_features and ev.market_snapshot_features.tf_1h
            else "UNKNOWN"
        ),
        lambda e, _ev: str(e.attribution.regime_1h if e.attribution else "UNKNOWN"),
        fixed_keys=("TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION", "HIGH_VOLATILITY"),
    )

    return {
        "setup_x_direction": setup_x_direction,
        "regime_x_direction": regime_x_direction,
        "rule_score_bucket": rule_score_bucket,
        "entry_quality_bucket": entry_quality_bucket,
        "stability_by_market_regime": stability_by_market_regime,
    }


def compute_grid_diagnostic_metrics(
    grid_evaluations: Sequence[TacticalGridShadowEvaluationV1],
) -> dict[str, Any]:
    """Compute contract-required grid-plan diagnostics (DIAGNOSTIC_ONLY authority for RC1)."""
    total_episodes = len(grid_evaluations)
    active_resolved = [e for e in grid_evaluations if e.eligibility_status == "RESOLVED"]
    pause_episodes = [e for e in grid_evaluations if e.eligibility_status == "NOT_ACTIVE_PAUSE"]
    active_count = len(active_resolved)

    if active_count == 0:
        return {
            "authority": "DIAGNOSTIC_ONLY",
            "total_episodes": total_episodes,
            "active_resolved_episodes": 0,
            "inactive_pause_episodes": len(pause_episodes),
            "paired_profit": {
                "total_paired_cycles": 0,
                "mean_paired_gross_pnl": 0.0,
                "mean_paired_net_pnl": 0.0,
                "total_paired_net_pnl": 0.0,
            },
            "inventory_excursion": {
                "mean_max_abs_inventory_notional": 0.0,
                "max_abs_inventory_notional": 0.0,
                "mean_time_weighted_abs_inventory": 0.0,
                "mean_long_inventory_peak": 0.0,
                "mean_short_inventory_peak": 0.0,
            },
            "underwater_duration": {
                "underwater_episode_count": 0,
                "underwater_episode_rate": 0.0,
                "mean_underwater_duration_ms": 0.0,
                "mean_maximum_underwater": 0.0,
                "worst_drawdown_from_prior_peak": 0.0,
            },
            "capital_utilization": {
                "mean_capital_utilization": 0.0,
                "peak_capital_utilization": 0.0,
            },
            "boundary_breach": {
                "lower_boundary_breach_count": 0,
                "upper_boundary_breach_count": 0,
                "any_boundary_breach_rate": 0.0,
                "total_boundary_breach_events": 0,
            },
            "policy_shift": {
                "mean_grid_shift_count": 0.0,
                "mean_grid_shift_frequency_per_day": 0.0,
                "policy_pause_transition_count": 0,
            },
            "trend_transition": {
                "trend_transition_episode_count": 0,
                "mean_net_equity_at_first_trend_transition": None,
                "mean_post_transition_net_pnl_delta": None,
                "mean_trend_transition_loss": None,
            },
        }

    underwater_eps = [e for e in active_resolved if e.maximum_underwater < 0.0]
    underwater_durations = [
        float((e.terminal_time_ms or e.evaluation_end_ms) - e.evaluation_start_ms)
        * min(1.0, abs(e.maximum_underwater) / max(abs(e.min_marked_equity) + 1e-8, 1e-4))
        if e.maximum_underwater < 0.0
        else 0.0
        for e in active_resolved
    ]

    shift_counts = [float(e.grid_shift_count) for e in active_resolved if e.grid_shift_count is not None]
    shift_freqs = [
        float(e.grid_shift_frequency_per_day)
        for e in active_resolved
        if e.grid_shift_frequency_per_day is not None
    ]
    pause_trans = sum(1 for e in active_resolved if e.first_policy_pause_ms is not None)

    trend_trans_eps = [e for e in active_resolved if e.first_technical_trend_transition_ms is not None]
    eq_at_trans = [
        float(e.net_equity_at_first_trend_transition)
        for e in trend_trans_eps
        if e.net_equity_at_first_trend_transition is not None
    ]
    post_deltas = [
        float(e.post_transition_net_pnl_delta)
        for e in trend_trans_eps
        if e.post_transition_net_pnl_delta is not None
    ]
    trans_losses = [
        float(e.trend_transition_loss)
        for e in trend_trans_eps
        if e.trend_transition_loss is not None
    ]

    any_breach = sum(1 for e in active_resolved if e.lower_boundary_breached or e.upper_boundary_breached)

    return {
        "authority": "DIAGNOSTIC_ONLY",
        "total_episodes": total_episodes,
        "active_resolved_episodes": active_count,
        "inactive_pause_episodes": len(pause_episodes),
        "paired_profit": {
            "total_paired_cycles": sum(e.paired_cycle_count for e in active_resolved),
            "mean_paired_gross_pnl": _round_opt(statistics.mean(e.paired_gross_pnl for e in active_resolved)),
            "mean_paired_net_pnl": _round_opt(statistics.mean(e.paired_net_pnl for e in active_resolved)),
            "total_paired_net_pnl": _round_opt(sum(e.paired_net_pnl for e in active_resolved)),
            "mean_net_pnl_after_fees_slippage": _round_opt(
                statistics.mean(e.net_pnl_after_fees_slippage for e in active_resolved)
            ),
            "mean_net_pnl_after_funding": _round_opt(
                statistics.mean(
                    e.net_pnl_after_funding
                    if e.net_pnl_after_funding is not None
                    else e.net_pnl_after_fees_slippage
                    for e in active_resolved
                )
            ),
        },
        "inventory_excursion": {
            "mean_max_abs_inventory_notional": _round_opt(
                statistics.mean(e.max_abs_inventory_notional for e in active_resolved)
            ),
            "max_abs_inventory_notional": _round_opt(max(e.max_abs_inventory_notional for e in active_resolved)),
            "mean_time_weighted_abs_inventory": _round_opt(
                statistics.mean(e.mean_abs_inventory_notional_time_weighted for e in active_resolved)
            ),
            "mean_long_inventory_peak": _round_opt(statistics.mean(e.long_inventory_peak for e in active_resolved)),
            "mean_short_inventory_peak": _round_opt(statistics.mean(e.short_inventory_peak for e in active_resolved)),
        },
        "underwater_duration": {
            "underwater_episode_count": len(underwater_eps),
            "underwater_episode_rate": round(len(underwater_eps) / float(active_count), 6),
            "mean_underwater_duration_ms": _round_opt(statistics.mean(underwater_durations), 2),
            "mean_maximum_underwater": _round_opt(statistics.mean(e.maximum_underwater for e in active_resolved)),
            "worst_drawdown_from_prior_peak": _round_opt(
                min(e.max_drawdown_from_prior_peak for e in active_resolved)
            ),
        },
        "capital_utilization": {
            "mean_capital_utilization": _round_opt(
                statistics.mean(e.mean_capital_utilization for e in active_resolved)
            ),
            "peak_capital_utilization": _round_opt(max(e.peak_capital_utilization for e in active_resolved)),
        },
        "boundary_breach": {
            "lower_boundary_breach_count": sum(1 for e in active_resolved if e.lower_boundary_breached),
            "upper_boundary_breach_count": sum(1 for e in active_resolved if e.upper_boundary_breached),
            "any_boundary_breach_rate": round(any_breach / float(active_count), 6),
            "total_boundary_breach_events": sum(e.boundary_breach_count for e in active_resolved),
        },
        "policy_shift": {
            "mean_grid_shift_count": _round_opt(statistics.mean(shift_counts)) if shift_counts else 0.0,
            "mean_grid_shift_frequency_per_day": _round_opt(statistics.mean(shift_freqs)) if shift_freqs else 0.0,
            "policy_pause_transition_count": pause_trans,
        },
        "trend_transition": {
            "trend_transition_episode_count": len(trend_trans_eps),
            "mean_net_equity_at_first_trend_transition": (
                _round_opt(statistics.mean(eq_at_trans)) if eq_at_trans else None
            ),
            "mean_post_transition_net_pnl_delta": (
                _round_opt(statistics.mean(post_deltas)) if post_deltas else None
            ),
            "mean_trend_transition_loss": (
                _round_opt(statistics.mean(trans_losses)) if trans_losses else None
            ),
        },
    }


def evaluate_decision_quality_gates(
    *,
    integrity_checks: Mapping[str, bool],
    aggregate_oos: Mapping[str, Any],
    partition_oos_list: Sequence[Mapping[str, Any]],
    thresholds: FrozenReleaseThresholds | None = None,
    long_enabled: bool = True,
    short_enabled: bool = True,
) -> dict[str, Any]:
    """Mechanically apply the frozen pre-outcome release thresholds.

    No subgroup mining may rescue an aggregate hard FAIL or integrity violation.
    """
    th = thresholds or FrozenReleaseThresholds()

    # 1. Integrity Gates (mandatory PASS; any violation => FAIL)
    req_integrity_keys = (
        "pit_chronology_manifest_integrity",
        "transaction_costs_included_in_net_r",
        "no_outcome_informed_policy_retuning",
        "no_protected_a_line_outcomes_accessed",
        "deterministic_manifest_replay_identical",
    )
    integrity_gate_map = {k: bool(integrity_checks.get(k, False)) for k in req_integrity_keys}
    integrity_all_passed = all(integrity_gate_map.values())

    # Extract OOS numbers
    actionable_oos_count = int(aggregate_oos.get("actionable_signal_count", 0))
    long_oos_count = int(aggregate_oos.get("long_actionable_count", 0))
    short_oos_count = int(aggregate_oos.get("short_actionable_count", 0))
    target_stop_resolved_count = int(aggregate_oos.get("target_stop_resolved_count", 0))

    mean_net_r = aggregate_oos.get("mean_net_R")
    median_net_r = aggregate_oos.get("median_net_R")
    mean_gross_r = aggregate_oos.get("mean_gross_R")
    stop_before_target = aggregate_oos.get("stop_before_target")

    # Supported partitions (actionable_signal_count >= 20)
    supported_partitions = [
        p for p in partition_oos_list if int(p.get("actionable_signal_count", 0)) >= th.min_partition_actionable_count
    ]
    supported_count = len(supported_partitions)
    positive_supported_count = sum(
        1
        for p in supported_partitions
        if p.get("mean_net_R") is not None and float(p["mean_net_R"]) >= 0.0
    )
    severe_negative_supported_count = sum(
        1
        for p in supported_partitions
        if p.get("mean_net_R") is not None and float(p["mean_net_R"]) <= th.hard_fail_partition_mean_net_r_max
    )

    # 2. Hard Negative Gates (any with adequate support => FAIL)
    costs_included = integrity_gate_map["transaction_costs_included_in_net_r"]
    # Systematic cost omission check: if costs were omitted (or fee/slippage == 0 on filled trades when gross > 0 > true net)
    filled_count = int(aggregate_oos.get("filled_count", 0))
    mean_fee_r = float((aggregate_oos.get("fees") or {}).get("mean_fee_r", 0.0) or 0.0)
    mean_slip_r = float((aggregate_oos.get("slippage") or {}).get("mean_slippage_r", 0.0) or 0.0)
    cost_omission_detected = (not costs_included) or (
        filled_count > 0 and (mean_fee_r + mean_slip_r) <= 0.0
    )
    gross_to_net_sign_flip = (
        mean_gross_r is not None
        and mean_net_r is not None
        and float(mean_gross_r) > 0.0
        and float(mean_net_r) < 0.0
    )
    systematic_cost_omission_sign_flip = cost_omission_detected and (
        gross_to_net_sign_flip or not costs_included
    )

    hard_negative_gates = {
        "mean_net_r_le_minus_0_10_with_100_actionable": bool(
            actionable_oos_count >= th.hard_fail_min_actionable_support
            and mean_net_r is not None
            and float(mean_net_r) <= th.hard_fail_mean_net_r_max
        ),
        "median_net_r_le_minus_0_20_with_100_actionable": bool(
            actionable_oos_count >= th.hard_fail_min_actionable_support
            and median_net_r is not None
            and float(median_net_r) <= th.hard_fail_median_net_r_max
        ),
        "two_supported_partitions_mean_net_r_le_minus_0_25": bool(
            severe_negative_supported_count >= th.hard_fail_partition_count_min
        ),
        "stop_before_target_gt_0_70_with_100_resolved": bool(
            target_stop_resolved_count >= th.hard_fail_min_actionable_support
            and stop_before_target is not None
            and float(stop_before_target) > th.hard_fail_stop_before_target_min
        ),
        "systematic_cost_omission_sign_flip": bool(systematic_cost_omission_sign_flip),
    }
    any_hard_negative = any(hard_negative_gates.values())

    # 3. Evidence Support Gates (required for full PASS)
    support_gates = {
        "oos_partitions_ge_3": len(partition_oos_list) >= th.min_oos_partitions,
        "oos_actionable_count_ge_100": actionable_oos_count >= th.min_oos_actionable_count,
        "long_actionable_count_ge_20": (not long_enabled) or (long_oos_count >= th.min_long_actionable_count),
        "short_actionable_count_ge_20": (not short_enabled) or (short_oos_count >= th.min_short_actionable_count),
        "supported_partitions_ge_2": supported_count >= th.min_supported_partitions,
    }
    support_all_passed = all(support_gates.values())

    # 4. Outcome Quality — PASS Band Gates
    positive_partition_ratio = (
        round(positive_supported_count / float(supported_count), 6) if supported_count > 0 else 0.0
    )
    pass_band_gates = {
        "mean_net_r_ge_plus_0_05": bool(mean_net_r is not None and float(mean_net_r) >= th.pass_mean_net_r_min),
        "median_net_r_ge_minus_0_05": bool(
            median_net_r is not None and float(median_net_r) >= th.pass_median_net_r_min
        ),
        "supported_partitions_non_negative_ge_2_of_3": bool(
            supported_count >= th.min_supported_partitions
            and (positive_supported_count / float(supported_count)) >= (th.pass_positive_partition_ratio_min - 1e-9)
        ),
        "stop_before_target_le_0_65": bool(
            stop_before_target is not None and float(stop_before_target) <= th.pass_stop_before_target_max
        ),
    }
    pass_band_all_passed = all(pass_band_gates.values())

    # Mechanical terminal decision
    reasons: list[str] = []
    if not integrity_all_passed:
        decision = TacticalDecisionQualityDecision.FAIL
        failed_int = [k for k, v in integrity_gate_map.items() if not v]
        reasons.append(f"INTEGRITY_GATE_VIOLATION:{','.join(failed_int)}")
    elif any_hard_negative:
        decision = TacticalDecisionQualityDecision.FAIL
        triggered_hn = [k for k, v in hard_negative_gates.items() if v]
        reasons.append(f"HARD_NEGATIVE_GATE_TRIGGERED:{','.join(triggered_hn)}")
    elif not support_all_passed:
        decision = TacticalDecisionQualityDecision.DIAGNOSTIC_ONLY
        missing_sup = [k for k, v in support_gates.items() if not v]
        reasons.append(f"INSUFFICIENT_EVIDENCE_SUPPORT:{','.join(missing_sup)}")
    elif pass_band_all_passed:
        decision = TacticalDecisionQualityDecision.PASS
        reasons.append("ALL_INTEGRITY_SUPPORT_AND_PASS_BAND_GATES_SATISFIED")
    else:
        decision = TacticalDecisionQualityDecision.DIAGNOSTIC_ONLY
        missed_pass = [k for k, v in pass_band_gates.items() if not v]
        reasons.append(f"INTERMEDIATE_QUALITY_DIAGNOSTIC_BAND:{','.join(missed_pass)}")

    return {
        "contract_version": TACTICAL_DECISION_QUALITY_CONTRACT_VERSION,
        "decision": decision.value,
        "reasons": reasons,
        "thresholds": th.to_dict(),
        "subgroup_rescue_permitted": False,
        "subgroup_rescue_applied": False,
        "integrity_gates": {
            **integrity_gate_map,
            "all_passed": integrity_all_passed,
        },
        "hard_negative_gates": {
            **hard_negative_gates,
            "any_triggered": any_hard_negative,
        },
        "support_gates": {
            **support_gates,
            "oos_partitions_count": len(partition_oos_list),
            "actionable_oos_count": actionable_oos_count,
            "long_actionable_count": long_oos_count,
            "short_actionable_count": short_oos_count,
            "supported_partitions_count": supported_count,
            "all_passed": support_all_passed,
        },
        "pass_band_gates": {
            **pass_band_gates,
            "positive_supported_partitions_count": positive_supported_count,
            "supported_partitions_count": supported_count,
            "positive_supported_partition_ratio": positive_partition_ratio,
            "all_passed": pass_band_all_passed,
        },
        "stability_gate": {
            "status": (
                "PASS"
                if (
                    support_gates["oos_partitions_ge_3"]
                    and support_gates["supported_partitions_ge_2"]
                    and pass_band_gates["supported_partitions_non_negative_ge_2_of_3"]
                    and not hard_negative_gates["two_supported_partitions_mean_net_r_le_minus_0_25"]
                )
                else (
                    "FAIL"
                    if hard_negative_gates["two_supported_partitions_mean_net_r_le_minus_0_25"]
                    else "DIAGNOSTIC_ONLY"
                )
            ),
            "oos_partitions": len(partition_oos_list),
            "supported_partitions": supported_count,
            "positive_mean_net_r_partitions": positive_supported_count,
            "severe_negative_partitions": severe_negative_supported_count,
        },
        "gross_to_net_sign_flip_observed": gross_to_net_sign_flip,
    }


def canonical_json_hash(payload: Mapping[str, Any], exclude_keys: Sequence[str] = ()) -> str:
    """Compute deterministic SHA-256 hash of a mapping serialized as canonical sorted-key JSON."""
    clean = {k: v for k, v in payload.items() if k not in exclude_keys}
    raw = json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "FROZEN_TACTICAL_PREDECESSOR_SHA",
    "TACTICAL_DECISION_QUALITY_CONTRACT_VERSION",
    "FrozenReleaseThresholds",
    "TacticalDecisionQualityDecision",
    "canonical_json_hash",
    "compute_grid_diagnostic_metrics",
    "compute_subgroup_diagnostics",
    "compute_subset_metrics",
    "evaluate_decision_quality_gates",
    "summarize_trend_evidence_v2_shadow",
]
