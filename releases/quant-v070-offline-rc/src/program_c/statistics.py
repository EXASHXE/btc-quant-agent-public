"""Matched controls, conservative dependence groups, honest support and prospective power."""

from __future__ import annotations

import math
from typing import Sequence
import random
from collections import Counter, defaultdict

from .costs import cost_projection
from .engine import LedgerRow, first_passage, geometry
from .integrity import digest, require
from .protocol import DAY, HOUR, SEED, WEEK


def ideal_no_edge_probability(target_r: float) -> float:
    require(target_r > 0 and math.isfinite(target_r), "TARGET_R_INVALID")
    return 1 / (1 + target_r)


def cluster_episodes(episodes: list[dict]) -> tuple[dict[str, str], list[dict]]:
    windows = []
    for row in episodes:
        start = row["trigger_close_ms"]
        end = row["expiry_ms"] + row["holding_horizon_hours"] * HOUR
        # Monday-UTC week grouping, conservatively extended over the whole follow-up.
        first_week = (start + 3 * DAY) // WEEK
        last_week = (end - 1 + 3 * DAY) // WEEK
        windows.append((first_week * WEEK - 3 * DAY, (last_week + 1) * WEEK - 3 * DAY, row["episode_id"]))
    groups: list[dict] = []
    for start, end, identity in sorted(windows):
        if groups and start < groups[-1]["block_end_ms"]:
            groups[-1]["block_end_ms"] = max(end, groups[-1]["block_end_ms"])
            groups[-1]["episode_ids"].append(identity)
        else:
            groups.append({"cluster_id": f"C{len(groups) + 1:06d}", "block_start_ms": start,
                           "block_end_ms": end, "episode_ids": [identity]})
    mapping = {identity: group["cluster_id"] for group in groups for identity in group["episode_ids"]}
    return mapping, groups


def kish_effective_clusters(weights: Sequence[float]) -> float:
    require(all(w > 0 and math.isfinite(w) for w in weights), "CLUSTER_WEIGHTS_INVALID")
    return sum(weights) ** 2 / sum(w * w for w in weights) if weights else 0.0


def bootstrap_interval(cluster_differences: list[float], alpha: float = 0.05,
                       seed: int = SEED, repetitions: int = 2000) -> dict:
    require(0 < alpha < 1 and repetitions >= 100, "BOOTSTRAP_PARAMETERS_INVALID")
    n = len(cluster_differences)
    if n < 40:
        return {"status": "INSUFFICIENT_CLUSTERS", "interval": None, "clusters": n}
    rng = random.Random(seed)
    samples = sorted(sum(rng.choices(cluster_differences, k=n)) / n for _ in range(repetitions))
    return {"status": "DESCRIPTIVE_CLUSTER_BOOTSTRAP_ONLY", "clusters": n,
            "interval": [samples[int(alpha / 2 * repetitions)], samples[min(repetitions - 1, int((1 - alpha / 2) * repetitions))]],
            "seed": seed, "repetitions": repetitions,
            "assumption": "Independent cluster units; no missing or ambiguous paired values; not a small-n guarantee"}


def bounded_interval(cluster_means: list[float], protocol: dict, bounds_verified: bool = False) -> dict:
    stats = protocol["statistics"]
    lower, upper = stats["paired_cluster_difference_bounds_R"]
    if not bounds_verified or not cluster_means or any(not lower <= x <= upper for x in cluster_means):
        return {"status": "BOUNDS_OR_SAMPLES_UNVERIFIED", "interval": None}
    alpha = stats["familywise_alpha"] / stats["reserved_confirmatory_families"]
    radius = (upper - lower) * math.sqrt(math.log(2 / alpha) / (2 * len(cluster_means)))
    center = sum(cluster_means) / len(cluster_means)
    return {"status": "CONDITIONAL_HOEFFDING_FAMILYWISE_INTERVAL", "mean": center,
            "interval": [max(lower, center - radius), min(upper, center + radius)],
            "radius": radius, "per_family_alpha": alpha,
            "assumption": "Independent equal-weight bounded cluster means; bounds verified prospectively"}


def power_plan(protocol: dict) -> dict:
    s = protocol["statistics"]
    width = s["paired_cluster_difference_bounds_R"][1] - s["paired_cluster_difference_bounds_R"][0]
    alpha = s["familywise_alpha"] / s["reserved_confirmatory_families"]
    beta = 1 - s["power"]
    delta, precision = s["practical_effect_R"], s["uncertainty_half_width_R"]
    # Distribution-free prospective sufficient n. Test rejects only if the simultaneous
    # Hoeffding lower bound is >0; lower-tail Hoeffding ensures power >=1-beta.
    n_power = math.ceil(width ** 2 / (2 * delta ** 2)
                        * (math.sqrt(math.log(2 / alpha)) + math.sqrt(math.log(1 / beta))) ** 2)
    n_precision = math.ceil(width ** 2 * math.log(2 / alpha) / (2 * precision ** 2))
    final_n = max(s["cluster_floor_per_strategy_horizon"], n_power, n_precision)
    return {
        "schema_version": "C_SUPPORT_POWER_PLAN_V1", "status": "CONDITIONAL_PROSPECTIVE_METHODOLOGY_ONLY",
        "method": "Independent bounded equal-weight paired cluster means; Hoeffding test and simultaneous interval",
        "familywise_alpha": s["familywise_alpha"], "confirmatory_families_reserved": s["reserved_confirmatory_families"],
        "per_family_alpha": alpha, "target_power": s["power"], "practical_effect_R": delta,
        "uncertainty_half_width_R": precision, "paired_difference_bounds_R": s["paired_cluster_difference_bounds_R"],
        "required_independent_clusters_power_per_family": n_power,
        "required_independent_clusters_precision_per_family": n_precision,
        "minimum_independent_clusters_per_family": s["cluster_floor_per_strategy_horizon"],
        "minimum_independent_clusters_per_symbol_direction_cell": s["cell_cluster_floor"],
        "minimum_independent_utc_weeks": s["independent_utc_weeks_floor"],
        "required_independent_clusters_per_family_under_assumptions": final_n,
        "formula_power": "ceil(W^2/(2*delta^2)*(sqrt(log(2/alpha_family))+sqrt(log(1/beta)))^2)",
        "formula_precision": "ceil(W^2*log(2/alpha_family)/(2*halfwidth^2))",
        "mde_R_at_200_clusters": width / math.sqrt(2 * 200) * (
            math.sqrt(math.log(2 / alpha)) + math.sqrt(math.log(1 / beta))),
        "assumptions_currently_satisfied": False,
        "bounds_gate": s["bounded_payoff_condition"],
        "unbounded_or_unknown_cost_payoffs": "NO_VALID_FINITE_POWER_CLAIM; prospectively revise bounds and refreeze method before trial",
        "cell_and_week_gates": "Measured per declared family/cell; three symbols do not imply fifty independent clusters per cell. Overlapping weeks are not independent weeks.",
        "frequency_and_timeline": "UNKNOWN; requires genuine authorized forward denominators",
        "native_effective_samples_now": 0, "scientific_decision": "INSUFFICIENT_SUPPORT",
        "synthetic_data_is_never_native_support": True,
    }


def _conditional_control_payoff(row: dict, sign: int) -> dict:
    result = first_passage(row, control_sign=sign)
    entry, _, _, risk = geometry(row)
    net = None
    if result.conditional_exit_price is not None and row["costs"] is not None:
        costs = cost_projection(entry, result.conditional_exit_price, row["holding_horizon_hours"], row["costs"], "BASE")
        net = (sign * (result.conditional_exit_price - entry) - costs["total_per_base"]) / risk
    return {"sign": sign, "weight": 0.5, "outcome": result.outcome,
            "conditional_after_cost_R": net, "reasons": list(result.reasons)}


def timing_stratum(row: dict) -> tuple:
    costs = row["costs"]
    cost_hash = digest({k: v for k, v in costs.items() if k != "known_at_ms"}) if costs else "UNKNOWN"
    admin = row["administrative_censor_ms"]
    review = row["reviewed_ms"]
    admin_offset = None if admin is None or review is None else admin - review
    return (row["source_kind"], row["source_path_id"], row["symbol"], row["direction"], row["regime"],
            row["volatility_bucket"], row["holding_horizon_hours"], row["interval_hours"], cost_hash,
            None if review is None else review - row["scheduled_review_ms"], admin_offset)


def matched_controls(row: dict, pool: list[dict]) -> dict:
    same_path = [_conditional_control_payoff(row, sign) for sign in [-1, 1]]
    values = [x["conditional_after_cost_R"] for x in same_path]
    mean = sum(values) / 2 if all(x is not None for x in values) else None
    candidates = sorted((p for p in pool if timing_stratum(p) == timing_stratum(row)), key=lambda p: p["episode_id"])
    timing: dict = {"status": "NO_ADMISSIBLE_MATCHED_TIMING_POOL", "candidate_count": len(candidates), "payoff_R": None}
    if candidates:
        rng = random.Random(SEED + int(row["episode_id"][:16], 16))
        selected = rng.choice(candidates)
        sign = 1 if selected["direction"] == "LONG" else -1
        result = _conditional_control_payoff(selected, sign)
        timing = {"status": "FABRICATED_QA_MATCHED_TIMING_ONLY", "candidate_count": len(candidates),
                  "selected_episode_id": selected["episode_id"], "selected_review_ms": selected["reviewed_ms"],
                  "outcome": result["outcome"], "payoff_R": result["conditional_after_cost_R"],
                  "seed": SEED, "future_outcomes_used_in_selection": False}
    return {"same_path_random_direction": same_path, "same_path_null_mean_R": mean, "randomized_timing": timing,
            "control_denominator": {"same_path_alternatives": 2, "independent_additional_episodes": 0,
                                    "timing_candidate_opportunities": len(candidates)},
            "authority": "SYNTHETIC_QA_ONLY; conditional entry, not a no-edge market assertion"}


def summarize(envelope: dict, rows: list[LedgerRow], protocol: dict) -> dict:
    base = [r for r in rows if r.target_geometry == "FROZEN" and r.cost_case == "BASE" and r.delay_ms == 0]
    mapping, clusters = cluster_episodes(envelope["episodes"])
    by_id = {r["episode_id"]: r for r in envelope["episodes"]}
    for row in rows:
        row.cluster_id = mapping[row.episode_id]
    paired = defaultdict(list)
    for row in base:
        row.matched_controls = matched_controls(by_id[row.episode_id], envelope["control_pool"])
        control = row.matched_controls["same_path_null_mean_R"]
        if row.modeled_path_after_cost_R is not None and control is not None:
            paired[row.cluster_id].append(row.modeled_path_after_cost_R - control)
    cluster_differences = [sum(v) / len(v) for _, v in sorted(paired.items())]
    n = len(base)
    counts = Counter(r.outcome for r in base)
    unknown_names = {"AMBIGUOUS_OHLC_ORDER_UNKNOWN", "MISSING_COVERAGE", "RIGHT_CENSORED",
                     "INSUFFICIENT_FUTURE_HORIZON", "SOURCE_UNQUALIFIED"}
    unknown = sum(counts[x] for x in unknown_names)
    censored = counts["RIGHT_CENSORED"] + counts["INSUFFICIENT_FUTURE_HORIZON"]
    incomplete_payoffs = sum(r.modeled_path_after_cost_R is None for r in base)
    known_sum = sum(r.modeled_path_after_cost_R for r in base if r.modeled_path_after_cost_R is not None)
    modeled_mean = known_sum / n if n and not incomplete_payoffs else None
    targets = counts["TARGET_FIRST"]
    # Non-entrants have no return; retain them as unidentified for payoff purposes.
    unidentified_hit = unknown + counts["NO_FILL"] + counts["MISSED_ENTRY"]
    no_setup = envelope["no_setup_decision_count"]
    cluster_weights = [len(g["episode_ids"]) for g in clusters]
    return {
        "schema_version": "C_SCIENTIFIC_SUMMARY_V1", "scientific_decision": "INSUFFICIENT_SUPPORT",
        "method_status": "METHOD_IMPLEMENTED_SYNTHETICALLY_TESTED",
        "empirical_status": "EMPIRICAL_SUPPORT_INSUFFICIENT", "source_class": envelope["source_kind"],
        "denominators": {
            "all_candidate_trigger_decisions": n + no_setup, "NO_SETUP_decisions": no_setup,
            "eligible_setup_episodes": n, "actually_actionable_at_review": 0,
            "conditionally_review_eligible_QA": sum(r.conditional_entry or r.outcome == "NO_FILL" for r in base),
            "modeled_entrants_QA": sum(r.conditional_entry for r in base), "no_fill": counts["NO_FILL"],
            "missed_entry": counts["MISSED_ENTRY"], "unknown_path": unknown, "censored_or_short_followup": censored,
            "observed_terminal_conditional_paths_QA": sum(counts[x] for x in ["TARGET_FIRST", "STOP_FIRST", "TIME_STOP"]),
            "independent_clusters_QA": len(clusters), "independent_native_clusters": 0,
            "real_market_observations": 0, "scenario_rows": len(rows),
            "matched_timing_pool_opportunities_QA": len(envelope["control_pool"]),
        },
        "outcome_counts_QA": dict(sorted(counts.items())),
        "unknown_path_fraction": unknown / n if n else None,
        "censored_fraction": censored / n if n else None,
        "effective_sample_size": {"native_economic": 0, "QA_equal_cluster_weights": float(len(clusters)),
                                  "QA_episode_weighted_Kish_clusters": kish_effective_clusters(cluster_weights)},
        "clusters_QA": clusters, "independent_native_UTC_weeks": 0,
        "per_cell_native_clusters": {f"{symbol}/{direction}/{horizon}h": 0 for symbol in protocol["symbols"]
                                     for direction in protocol["directions"] for horizon in protocol["primary_horizons_hours"]},
        "target_event_identification_bounds_per_setup_QA": [targets / n, (targets + unidentified_hit) / n] if n else None,
        "target_event_bounds_semantics": "Not an executable win probability; non-entry and unresolved paths never become wins or zero-loss returns",
        "modeled_mean_R_all_setups": modeled_mean,
        "all_setup_payoff_identification": {"unidentified_episodes": incomplete_payoffs,
                                             "bounds_R": [None, None] if incomplete_payoffs else [modeled_mean, modeled_mean]},
        "matched_paired_clusters_QA": len(cluster_differences),
        "paired_cluster_difference_mean_QA": sum(cluster_differences) / len(cluster_differences) if cluster_differences else None,
        "paired_difference_semantics": "Complete-pair QA diagnostic only; no empirical inference or complete-case population mean",
        "bootstrap_QA": bootstrap_interval(cluster_differences),
        "uncertainty_native": bounded_interval([], protocol),
        "support_gates": {"native_authority": False, "clusters_200_per_family": False,
                          "clusters_50_per_cell": False, "independent_weeks_40": False,
                          "valid_80_percent_power": False, "95_percent_uncertainty_target": False},
        "source_economic_gate": "SOURCE_SYNTHETIC/NATIVE_UNQUALIFIED provides no native economic support",
        "actual_fills": 0, "executable_R": None, "realized_R": None,
        "ideal_arithmetic_only": {"2R": ideal_no_edge_probability(2), "3R": ideal_no_edge_probability(3),
                                  "4R": ideal_no_edge_probability(4),
                                  "condition": "zero cost, mutually exclusive complete exact executable barriers; strict p greater than threshold for positive expectancy; not empirical evidence"},
    }
