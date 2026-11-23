"""Frozen conditional geometry and conservative, coverage-first OHLC first passage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .costs import cost_projection
from .protocol import HOUR


@dataclass(frozen=True)
class PathResult:
    outcome: str
    reasons: tuple[str, ...]
    conditional_entry: bool = False
    entry_ms: int | None = None
    event_ms: int | None = None
    required_end_ms: int | None = None
    conditional_exit_price: float | None = None
    gap_stop: bool = False


@dataclass
class LedgerRow:
    schema_version: str
    episode_id: str
    input_row_sha256: str
    decision_digest: str
    source_class: str
    symbol: str
    direction: str
    strategy_version: str
    horizon_hours: int
    target_geometry: str
    cost_case: str
    delay_ms: int
    planned_R: float
    frozen_worst_entry: float
    frozen_stop: float
    frozen_target: float
    original_risk_per_base: float
    outcome: str
    outcome_confidence: str
    conditional_entry: bool
    entry_ms: int | None
    event_ms: int | None
    required_end_ms: int | None
    reasons: list[str]
    modeled_target_after_cost_R: float | None
    modeled_path_after_cost_R: float | None
    modeled_payoff_bounds_R: list[float | None]
    cost_components: dict | None
    executable_R: float | None = None
    executable_R_status: str = "UNKNOWN"
    execution_cost_status: str = "EXE_COST_UNVERIFIED"
    realized_R: float | None = None
    actual_fill: bool = False
    evidence_grade: str = "SYNTHETIC_CONDITIONAL_PREMISE_NOT_FILL"
    event_time_semantics: str = "BAR_END_UPPER_BOUND_EXCEPT_PRECISE_TIME_STOP"
    producer_outcome: str | None = None
    producer_projected_after_cost_R: float | None = None
    producer_projected_after_cost_R_semantics: str | None = None
    cluster_id: str | None = None
    matched_controls: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def geometry(row: dict, target_geometry: str | int = "FROZEN") -> tuple[float, float, float, float]:
    sign = 1 if row["direction"] == "LONG" else -1
    entry = row["entry_region"][1 if sign == 1 else 0]
    stop = row["structural_stop"]  # B stop already includes volatility/execution buffers.
    risk = abs(entry - stop)
    target = (min(row["fixed_preobservable_target_zones"]) if sign == 1 else
              max(row["fixed_preobservable_target_zones"])) if target_geometry == "FROZEN" else (
                  entry + sign * int(target_geometry) * risk)
    return entry, stop, target, risk


def first_passage(row: dict, target_geometry: str | int = "FROZEN", delay_ms: int = 0,
                  control_sign: int | None = None) -> PathResult:
    if row["source_kind"] != "SOURCE_SYNTHETIC":
        return PathResult("SOURCE_UNQUALIFIED", ("EXTERNAL_NATIVE_ADMISSION_REQUIRED",))
    if row["reviewed_ms"] is None:
        return PathResult("MISSING_COVERAGE", ("ACTUAL_REVIEW_UNKNOWN", "NO_INDEPENDENT_ORDERED_PRICE_PATH"))
    review = row["reviewed_ms"] + delay_ms
    if review >= row["expiry_ms"]:
        return PathResult("MISSED_ENTRY", ("REVIEW_AT_OR_AFTER_EXPIRY_NO_CHASE",))
    entry, stop, target, risk = geometry(row, target_geometry)
    sign = 1 if row["direction"] == "LONG" else -1
    barrier_sign = sign if control_sign is None else control_sign
    if control_sign is not None:
        stop = entry - barrier_sign * risk
        target = entry + barrier_sign * abs(target - entry)
    bars = [b for b in row["path"] if b["end_ms"] > review]
    required = max(review + row["holding_horizon_hours"] * HOUR, row["expiry_ms"])
    if not bars:
        return PathResult("RIGHT_CENSORED" if row["right_censored"] else "INSUFFICIENT_FUTURE_HORIZON",
                          ("NO_FUTURE_BARS",), required_end_ms=required)
    if bars[0]["open_ms"] < review:
        return PathResult("AMBIGUOUS_OHLC_ORDER_UNKNOWN", ("REVIEW_INSIDE_UNORDERED_BAR",), required_end_ms=required)
    if bars[0]["open_ms"] != review:
        return PathResult("MISSING_COVERAGE", ("INITIAL_REVIEW_INTERVAL_MISSING",), required_end_ms=required)
    low_entry, high_entry = row["entry_region"]
    first = bars[0]["open"]
    nonentry_reason = None
    if (sign == 1 and (first > high_entry or first <= row["structural_stop"])) or (
            sign == -1 and (first < low_entry or first >= row["structural_stop"])):
        nonentry_reason = "PRICE_OUTSIDE_REVIEW_NO_CHASE_OR_INVALIDATED"
    entry_ms, entry_index, entry_at_open = None, None, False
    if nonentry_reason is None:
        for index, bar in enumerate(bars):
            if bar["open_ms"] >= row["expiry_ms"]:
                break
            touch_entry = bar["low"] <= high_entry and bar["high"] >= low_entry
            if touch_entry:
                entry_ms, entry_index = bar["open_ms"], index
                entry_at_open = low_entry <= bar["open"] <= high_entry
                break
            invalidated = (bar["low"] <= row["structural_stop"] if sign == 1 else
                           bar["high"] >= row["structural_stop"])
            if invalidated:
                nonentry_reason = "STRUCTURAL_INVALIDATION_BEFORE_CONDITIONAL_ENTRY"
                break
    entered = entry_ms is not None
    # Expiry governs entry eligibility; it must not extend an entrant's holding period.
    required = entry_ms + row["holding_horizon_hours"] * HOUR if entered else required
    relevant = [b for b in bars if b["open_ms"] < required]
    if any(a["end_ms"] != b["open_ms"] for a, b in zip(relevant, relevant[1:])):
        return PathResult("MISSING_COVERAGE", ("MISSING_INTERVAL",), entered, entry_ms, required_end_ms=required)
    if row["coverage_end_ms"] < required:
        return PathResult("RIGHT_CENSORED" if row["right_censored"] else "INSUFFICIENT_FUTURE_HORIZON",
                          ("COMPLETE_DECLARED_HORIZON_REQUIRED",), entered, entry_ms, required_end_ms=required)
    if not any(b["end_ms"] == required for b in relevant):
        return PathResult("MISSING_COVERAGE", ("HORIZON_BOUNDARY_INSIDE_UNORDERED_BAR",), entered, entry_ms,
                          required_end_ms=required)
    if nonentry_reason is not None:
        return PathResult("MISSED_ENTRY", (nonentry_reason,), required_end_ms=required)
    if not entered:
        return PathResult("NO_FILL", ("NO_CONDITIONAL_ENTRY_IN_COMPLETE_EXPIRY_WINDOW",), required_end_ms=required)
    assert entry_index is not None  # entered implies an identified entry bar
    for index, bar in enumerate(bars):
        if index < entry_index:
            continue
        if bar["open_ms"] >= required:
            break
        hit_stop = bar["low"] <= stop if barrier_sign == 1 else bar["high"] >= stop
        hit_target = bar["high"] >= target if barrier_sign == 1 else bar["low"] <= target
        original_invalidation = (bar["low"] <= row["structural_stop"] if sign == 1 else
                                 bar["high"] >= row["structural_stop"])
        if index == entry_index and not entry_at_open and (hit_stop or hit_target or original_invalidation):
            return PathResult("AMBIGUOUS_OHLC_ORDER_UNKNOWN", ("ENTRY_EXIT_SAME_BAR_ORDER_UNKNOWN",),
                              True, entry_ms, bar["end_ms"], required)
        if hit_stop and hit_target:
            return PathResult("AMBIGUOUS_OHLC_ORDER_UNKNOWN", ("BOTH_BARRIERS_SAME_BAR",),
                              True, entry_ms, bar["end_ms"], required)
        if hit_stop:
            gap = (bar["open"] < stop if barrier_sign == 1 else bar["open"] > stop)
            return PathResult("STOP_FIRST", ("STOP_GAP_EXECUTION_UNKNOWN",) if gap else (
                "CONDITIONAL_STOP_FIRST_NOT_EXECUTED",), True, entry_ms, bar["end_ms"], required,
                None if gap else stop, gap)
        if hit_target:
            return PathResult("TARGET_FIRST", ("CONDITIONAL_TARGET_FIRST_NOT_EXECUTED",),
                              True, entry_ms, bar["end_ms"], required, target)
    terminal = next((b for b in bars if b["end_ms"] == required), None)
    if terminal is None:
        return PathResult("MISSING_COVERAGE", ("PRECISE_TIME_STOP_PRICE_NOT_COVERED",), True, entry_ms,
                          required_end_ms=required)
    return PathResult("TIME_STOP", ("FULL_HORIZON_CONDITIONAL_CLOSE_NOT_EXECUTED",), True, entry_ms,
                      required, required, terminal["close"])


def scenario(row: dict, target_geometry: str | int, cost_case: str, delay_ms: int) -> LedgerRow:
    entry, stop, target, risk = geometry(row, target_geometry)
    planned_r = abs(target - entry) / risk
    path = first_passage(row, target_geometry, delay_ms)
    costs = cost_projection(entry, target, row["holding_horizon_hours"], row["costs"], cost_case)
    cost = costs["total_per_base"]
    target_net = None if cost is None else planned_r - cost / risk
    path_net = None
    bounds: list[float | None] = [None, None]
    if path.conditional_exit_price is not None and cost is not None:
        sign = 1 if row["direction"] == "LONG" else -1
        exit_costs = cost_projection(entry, path.conditional_exit_price, row["holding_horizon_hours"], row["costs"], cost_case)
        path_net = (sign * (path.conditional_exit_price - entry) - exit_costs["total_per_base"]) / risk
        bounds = [path_net, path_net]
    elif path.outcome == "AMBIGUOUS_OHLC_ORDER_UNKNOWN" and cost is not None and path.entry_ms is not None:
        stop_costs = cost_projection(entry, stop, row["holding_horizon_hours"], row["costs"], cost_case)
        bounds = [-1 - stop_costs["total_per_base"] / risk, target_net]
    elif path.gap_stop:
        bounds = [None, -1.0]  # No finite lower execution bound for an uncapped gap.
    return LedgerRow(
        schema_version="C_TYPED_SCENARIO_LEDGER_V1", episode_id=row["episode_id"], input_row_sha256=row["row_sha256"],
        decision_digest=row["decision_digest"], source_class=row["source_kind"], symbol=row["symbol"],
        direction=row["direction"], strategy_version=row["strategy_version"], horizon_hours=row["holding_horizon_hours"],
        target_geometry=str(target_geometry), cost_case=cost_case, delay_ms=delay_ms, planned_R=planned_r,
        frozen_worst_entry=entry, frozen_stop=stop, frozen_target=target, original_risk_per_base=risk,
        outcome=path.outcome, outcome_confidence="UNKNOWN" if path.conditional_exit_price is None else
        "CONDITIONAL_SYNTHETIC_COMPLETE_OHLC_PATH", conditional_entry=path.conditional_entry,
        entry_ms=path.entry_ms, event_ms=path.event_ms, required_end_ms=path.required_end_ms,
        reasons=list(path.reasons), modeled_target_after_cost_R=target_net, modeled_path_after_cost_R=path_net,
        modeled_payoff_bounds_R=bounds, cost_components=costs["components_per_base"],
        producer_outcome=row.get("producer_outcome"),
        producer_projected_after_cost_R=row.get("producer_projected_after_cost_R"),
        producer_projected_after_cost_R_semantics=row.get("producer_projected_after_cost_R_semantics"),
    )


def ledger(envelope: dict, protocol: dict) -> list[LedgerRow]:
    return [scenario(row, target, case, delay)
            for row in sorted(envelope["episodes"], key=lambda r: r["episode_id"])
            for target in protocol["target_geometries"] for case in protocol["cost_cases"]
            for delay in protocol["review_delay_scenarios_ms"]]
