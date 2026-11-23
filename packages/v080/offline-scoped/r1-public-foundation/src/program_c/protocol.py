"""Protocol fixed before constructing any Program C QA path or economic scenario."""

from __future__ import annotations

from .integrity import PINS, RESOURCE_ROOT, digest, parse, require, without

HOUR = 3_600_000
DAY = 24 * HOUR
WEEK = 7 * DAY
SEED = 70001
OUTCOMES = (
    "TARGET_FIRST", "STOP_FIRST", "TIME_STOP", "NO_FILL", "MISSED_ENTRY",
    "AMBIGUOUS_OHLC_ORDER_UNKNOWN", "MISSING_COVERAGE", "RIGHT_CENSORED",
    "INSUFFICIENT_FUTURE_HORIZON", "SOURCE_UNQUALIFIED",
)
FLAGS = {
    "source_qualified": False, "shadow_advisory_qualified": False,
    "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO", "economically_validated": False,
    "native_market_requests": 0, "new_primary_experiments": 0,
    "protected_historical_or_holdout_reads": 0, "actual_trading_orders_or_alerts": 0,
    "real_opportunity_episode_count": 0, "synthetic_B_opportunity_episode_count": 1,
    "S2": "RESEARCH_ONLY_DISABLED", "S3": "RESEARCH_ONLY_DISABLED",
}
COST_CASES: dict[str, list[float]] = {
    "BASE": [1, 1, 1, 1, 1, 0],
    "ADVERSE": [1.5, 1.5, 1.5, 1.5, 2, 25],
    "DOUBLE_SPREAD_SLIPPAGE": [1, 2, 2, 1, 1, 0],
    "DOUBLE_FEE_CARRY": [2, 1, 1, 2, 1, 0],
    "COMBINED": [2, 2, 2, 2, 2, 50],
    "JUMP_RISK": [2, 3, 3, 2, 3, 100],
}


def specification() -> dict:
    return {
        "schema_version": "C_FROZEN_PROTOCOL_V1",
        "status": "PROSPECTIVE_TEST_READY_METHOD",
        "freeze_sequence": "C0 before C fixtures/scenarios; B producer outcome already known, no preregistration claim",
        "source_neutral_schema": "C_SOURCE_NEUTRAL_EPISODE_EXPORT_V1",
        "evaluator_classification_version": "C_OUTCOME_CLASSIFICATION_V1",
        "outcomes": list(OUTCOMES),
        "new_status": {"SOURCE_UNQUALIFIED": "Evaluator-only authority gate; never edits B row"},
        "input_pins": PINS,
        "source_classes": ["SOURCE_SYNTHETIC", "NATIVE_UNQUALIFIED", "NATIVE_QUALIFIED"],
        "trusted_native_admission_roots": [],
        "native_admission": "Disabled until external Controller-pinned independently verified admissions; strings confer no authority",
        "strategy": "trend_pullback", "strategy_version": "PROGRAM_A_S1_CAUSAL_V1",
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "directions": ["LONG", "SHORT"],
        "price_unit": "USDT_PER_BASE", "risk_unit": "INITIAL_PRICE_RISK_PER_BASE",
        "instrument_scope": "Linear quote/base conditional model only; inverse/quanto require a new version",
        "review_utc_hours": [0, 12], "max_clock_drift_ms": 1000,
        "maximum_observation_staleness_ms": 300_000,
        "bar_interval_convention": "UTC half-open [open,end); close_time_ms=end-1",
        "coverage_intervals_hours": [1, 4, 24],
        "primary_horizons_hours": [24, 120],
        "descriptive_horizons_hours": [4, 8, 12, 24, 48, 72, 120],
        "target_geometries": ["FROZEN", 2, 3, 4],
        "geometry_rule": "Alternative barriers from original worst entry and original buffered stop, before future access; all retained",
        "risk_rule": "Structural stop in B is already buffered; never subtract buffers twice. Freeze abs(worst_entry-stop). C net-R uses that original price risk; preserve B cost-in-denominator projection separately.",
        "entry_model": "Conditional premise only: zone at actual review open, or later touch before expiry. Touch is never a fill. Beyond adverse invalidation or favorable boundary at review means MISSED_ENTRY/no chase. Intra-bar entry and exit order unresolved means UNKNOWN.",
        "review_delay_scenarios_ms": [0, 300_000, HOUR],
        "delay_rule": "Offsets to evidenced review; an unobserved actual review stays unknown. Partial unordered review bars cannot prove entry.",
        "horizon_rule": "Require contiguous completed bars for full declared period even after early barrier. Late entrants need entry+holding horizon; no-fill needs expiry plus declared follow-up. No 3-minute surrogate.",
        "stop_rule": "Gap stop is price-uncertain; observed modeled payoff unknown without independently bounded execution. No finite lower payoff bound for uncapped jumps.",
        "cost_cases": COST_CASES,
        "cost_multiplier_columns": ["fees", "spread", "slippage", "funding_carry", "impact", "jump_bps"],
        "uncalibrated_B_defaults_bps": {"fee_each_side": 5.0, "slippage_each_side": 5.0,
                                       "spread_round_trip": 4.0, "funding_and_carry_per_day": 3.0},
        "cost_rule": "No positive funding credit; charge ceiling of holding/cadence. Maker and taker fees separate. Synthetic default decomposes combined 3 bps/day as funding=3, carrying=financing=0 solely for QA; actual components unknown. Impact/size has explicit QA coefficient, no liquidity calibration.",
        "execution_rule": "EXE_COST_UNVERIFIED; executable_R and realized_R UNKNOWN for synthetic/unqualified inputs. Future verified quote-capacity and venue evidence needed; executed fills require separate independent verification.",
        "episode_identity": "symbol/strategy_version/trigger/causal-prefix; B preserves its PRODUCT-prefixed identity. Never count cost, target, delay, bar or control alternatives independently.",
        "null": {
            "same_path_control": "Equal-weight random direction first passage at same conditional entry anchor; identical barrier distances, costs, horizon, delay, volatility, path and censoring. Both directions retained, no favorable ordering.",
            "analytical_reference": "p=1/(1+R) only for continuous zero-drift martingale with exact complete barriers, no costs/jumps/censoring; not empirical p",
            "timing_control": "Fixed-seed uniform choice from sorted ex-ante eligible same-source-path/symbol/regime/volatility/horizon/interval/cost/admin-censor strata; never select on outcomes. Empty pool => UNKNOWN. Preserve cluster pairing.",
            "seed": SEED,
        },
        "clustering": "Connected overlapping episode follow-up windows AND common Monday-UTC week blocks across BTC/ETH/SOL. Union cross-week overlaps. Equal cluster weights; residual dependence invalidates inference.",
        "statistics": {
            "cluster_floor_per_strategy_horizon": 200, "cell_cluster_floor": 50,
            "independent_utc_weeks_floor": 40, "familywise_alpha": 0.05,
            "reserved_confirmatory_families": 6, "power": 0.8,
            "practical_effect_R": 0.25, "uncertainty_half_width_R": 0.25,
            "paired_cluster_difference_bounds_R": [-6.0, 6.0],
            "bounded_payoff_condition": "Prospectively enforce individual payoff envelope [-2,4] R including verified costs/gaps before use; missing/uncapped outcomes invalidate finite power/CI. QA does not establish this condition.",
            "interval": "Hoeffding simultaneous 95% family-wise interval for independent bounded cluster means; fixed-seed percentile cluster bootstrap descriptive only at >=40 clusters, never resolves missing outcomes",
            "multiplicity": "Bonferroni six reserved strategy x horizon families. Only frozen geometry/base cost/evidenced review confirmatory; all alternatives descriptive, no selection or new trials. S2/S3 disabled.",
            "stopping": "Single frozen final analysis after all support/power/coverage gates. No repeated efficacy looks; stop for authority/coverage failure or invalid payoff bounds. No trial starts here.",
        },
        "evidence_rule": "Synthetic QA and frozen B example contribute zero native economic samples, including any fabricated weeks",
        "opportunity_frequency": "UNKNOWN_UNTIL_AUTHORIZED_FORWARD_RECORDS",
        "sample_accumulation_timeline": "UNKNOWN",
        "flags": FLAGS,
    }


def frozen_protocol() -> dict:
    obj = specification()
    return {**obj, "protocol_sha256": digest(obj)}


def load_protocol(raw: bytes | None = None) -> dict:
    obj = parse(raw if raw is not None else (RESOURCE_ROOT / "frozen_protocol.json").read_bytes())
    require(obj.get("protocol_sha256") == digest(without(obj, "protocol_sha256")), "PROTOCOL_SELF_HASH")
    require(obj == frozen_protocol(), "PROTOCOL_CHANGED_OR_UNTRUSTED")
    return obj


def next_review(decision_ms: int) -> int:
    return ((decision_ms + 12 * HOUR - 1) // (12 * HOUR)) * (12 * HOUR)
