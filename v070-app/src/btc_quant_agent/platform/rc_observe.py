"""Later synthetic first-passage observations, separate from fills and economics."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .core import fingerprint
from .rc_models import RCDecision
from .swing import Contract, INTERVALS, timestamp

OUTCOMES = (
    "TARGET_FIRST",
    "STOP_FIRST",
    "TIME_STOP",
    "NO_FILL",
    "MISSED_ENTRY",
    "AMBIGUOUS_OHLC_ORDER_UNKNOWN",
    "MISSING_COVERAGE",
    "RIGHT_CENSORED",
    "INSUFFICIENT_FUTURE_HORIZON",
)


class Observation(Contract):
    schema_version: Literal["PROGRAM_A_SYNTHETIC_OBSERVATION_V1"] = "PROGRAM_A_SYNTHETIC_OBSERVATION_V1"
    exposure: Literal["SYNTHETIC"] = "SYNTHETIC"
    account: Literal["ACCOUNT_UNKNOWN/ACCOUNT_VETO"] = "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    episode_id: str
    decision_digest: str
    asof_ms: int
    observation_window_start_ms: int
    coverage_end_ms: int
    required_end_ms: int
    right_censored: bool
    outcome: Literal[
        "TARGET_FIRST",
        "STOP_FIRST",
        "TIME_STOP",
        "NO_FILL",
        "MISSED_ENTRY",
        "AMBIGUOUS_OHLC_ORDER_UNKNOWN",
        "MISSING_COVERAGE",
        "RIGHT_CENSORED",
        "INSUFFICIENT_FUTURE_HORIZON",
    ]
    entry_condition_observed: bool
    entry_condition_ms: int | None
    first_event_ms: int | None
    future_receipt_ids: tuple[str, ...]
    future_prefix_sha256: str
    reasons: tuple[str, ...]
    actual_fill: Literal[False] = False
    execution_inferred: Literal[False] = False
    economic_evidence: Literal[False] = False

    @model_validator(mode="after")
    def clocks(self):
        for t in (self.asof_ms, self.observation_window_start_ms, self.coverage_end_ms, self.required_end_ms):
            timestamp(t)
        if self.coverage_end_ms > self.asof_ms or (
            self.future_receipt_ids and self.coverage_end_ms < self.observation_window_start_ms
        ):
            raise ValueError("OBSERVATION_COVERAGE_CLOCK_INVALID")
        for event_t in (self.entry_condition_ms, self.first_event_ms):
            if (
                event_t is not None
                and not self.observation_window_start_ms <= event_t <= self.coverage_end_ms
            ):
                raise ValueError("OBSERVATION_EVENT_CLOCK_INVALID")
        return self


def observe(decision, receipts, *, asof_ms, right_censored=False):
    return observe_path(decision, receipts, asof_ms=asof_ms, right_censored=right_censored)


def observe_path(
    decision,
    receipts,
    *,
    asof_ms,
    right_censored=False,
    decision_parser=RCDecision.model_validate_json,
    observation_factory=Observation,
    evidence_reason="CONDITIONAL_SYNTHETIC_PRICE_PATH_NOT_EXECUTION_OR_PNL",
):
    """Shared immutable first-passage mathematics, with explicit result provenance."""
    d = decision_parser(decision.model_dump_json())
    if d.opportunity is None or d.episode_id is None:
        raise ValueError("OBSERVATION_REQUIRES_FROZEN_S1_EPISODE")
    timestamp(asof_ms)
    if asof_ms < d.decision_ms:
        raise ValueError("OBSERVATION_PRECEDES_DECISION")
    hour, o = INTERVALS["1H"], d.opportunity
    start = ((d.decision_ms + hour - 1) // hour) * hour
    seen: dict[str, str]
    rows, seen = [], {}
    for r in receipts:
        b, c = r.bar, r.bar.candle
        if (
            c.symbol != d.symbol
            or c.interval != "1H"
            or c.open_time_ms < start
            or b.durable_ms > asof_ms
            or b.end_ms > asof_ms
        ):
            continue
        if r.identity in seen:
            if seen[r.identity] != r.raw_sha256:
                raise ValueError("OBSERVATION_RECEIPT_CONFLICT")
            continue
        seen[r.identity] = r.raw_sha256
        rows.append(r)
    end = rows[-1].bar.end_ms if rows else min(start, asof_ms)
    entry_ms, event_ms = None, None
    required = max(start, o.expires_ms)
    outcome = None
    expected_open = start
    reasons = [evidence_reason, "INITIAL_PARTIAL_HOUR_EXCLUDED_NO_EARLIER_ENTRY_ASSUMED"]
    missed = False
    sign = 1 if o.direction == "LONG" else -1
    stop = o.buffered_stop
    target = min(o.target_zones) if sign == 1 else max(o.target_zones)
    # A newly visible correction anywhere in the supplied path requires requalification,
    # even if an earlier pass would have stopped scanning at its first price barrier.
    if any(r.bar.revision for r in rows):
        outcome = "MISSING_COVERAGE"
        reasons.append("VISIBLE_OBSERVATION_REVISION_UNRESOLVED")
    for r in rows:
        if outcome is not None:
            break
        b, c = r.bar, r.bar.candle
        if c.open_time_ms != expected_open or b.revision:
            outcome = "MISSING_COVERAGE"
            reasons.append("GAP_UNSORTED_OR_REVISED_OBSERVATION_PATH")
            break
        expected_open = b.end_ms
        touched_entry = c.low <= o.entry_region[1] and c.high >= o.entry_region[0]
        stop_hit = c.low <= stop if sign == 1 else c.high >= stop
        target_hit = c.high >= target if sign == 1 else c.low <= target
        if entry_ms is None:
            if c.open_time_ms >= o.expires_ms:
                break
            if touched_entry:
                entry_ms = b.end_ms
                required = entry_ms + o.holding_hours * hour
                if stop_hit or target_hit:
                    outcome, event_ms = "AMBIGUOUS_OHLC_ORDER_UNKNOWN", b.end_ms
                    reasons.append("ENTRY_AND_EXIT_CONDITIONS_SHARE_UNORDERED_BAR")
                    break
            else:
                missed |= c.low > o.entry_region[1] if sign == 1 else c.high < o.entry_region[0]
        elif c.open_time_ms < required:
            if stop_hit and target_hit:
                outcome, event_ms = "AMBIGUOUS_OHLC_ORDER_UNKNOWN", b.end_ms
                reasons.append("STOP_AND_TARGET_SHARE_UNORDERED_BAR")
                break
            if stop_hit or target_hit:
                outcome, event_ms = ("STOP_FIRST" if stop_hit else "TARGET_FIRST"), b.end_ms
                break
        elif c.open_time_ms >= required:
            break
    if outcome is None:
        if right_censored and end < required:
            outcome = "RIGHT_CENSORED"
        elif end < required:
            outcome = "INSUFFICIENT_FUTURE_HORIZON"
        elif entry_ms is None:
            outcome = "MISSED_ENTRY" if missed else "NO_FILL"
            reasons.append("NO_MODELED_ENTRY_CONDITION_IN_DECLARED_WINDOW_NO_ACTUAL_FILL_PROOF")
        else:
            outcome = "TIME_STOP"
            event_ms = required
    return observation_factory(
        episode_id=d.episode_id,
        decision_digest=fingerprint(d.model_dump(mode="json")),
        asof_ms=asof_ms,
        observation_window_start_ms=start,
        coverage_end_ms=end,
        required_end_ms=required,
        right_censored=right_censored,
        outcome=outcome,
        entry_condition_observed=entry_ms is not None,
        entry_condition_ms=entry_ms,
        first_event_ms=event_ms,
        future_receipt_ids=tuple(r.identity for r in rows),
        future_prefix_sha256=fingerprint([r.model_dump(mode="json") for r in rows]),
        reasons=tuple(reasons),
    )


def advance_episode(store, identity, *, now_ms, decision_parser=RCDecision.model_validate_json):
    """Revalidate original age, source and frozen levels without manufacturing a fill."""
    e = store.episode(identity)
    d = decision_parser(__import__("json").dumps(e["anchors"]["decision"]))
    o = d.opportunity
    if now_ms < e["updated_ms"]:
        raise ValueError("EPISODE_TIME_REGRESSION")
    state, reason = e["state"]["status"], "UNCHANGED"
    revisions = [
        r
        for r in store.receipts()
        if r.bar.revision
        and r.bar.durable_ms <= now_ms
        and r.bar.candle.symbol == d.symbol
        and r.bar.end_ms <= d.trigger_close_ms
    ]
    if store.stopped() or revisions:
        state, reason = "CANCELED", "SOURCE_STOP_OR_VISIBLE_REVISION_REQUALIFICATION_REQUIRED"
    elif now_ms >= o.expires_ms or now_ms > o.review_deadline_ms:
        state, reason = "EXPIRED", "ORIGINAL_ENTRY_VALIDITY_ELAPSED_NO_AGE_RESET"
    else:
        future = [
            r.bar
            for r in store.receipts()
            if r.bar.candle.symbol == d.symbol
            and r.bar.candle.interval == "1H"
            and r.bar.candle.open_time_ms >= d.decision_ms
            and r.bar.durable_ms <= now_ms
        ]
        if future:
            if any(
                (
                    b.candle.low <= o.buffered_stop
                    if o.direction == "LONG"
                    else b.candle.high >= o.buffered_stop
                )
                for b in future
            ):
                state, reason = "INVALIDATED", "LATER_SYNTHETIC_CANDLE_CROSSED_FROZEN_STOP"
            elif (
                future[-1].candle.close > o.entry_region[1]
                if o.direction == "LONG"
                else future[-1].candle.close < o.entry_region[0]
            ):
                state, reason = "NO_CHASE", "LATER_ENTRY_REGION_LOST_NO_FILL_ASSUMED"
    return store.transition(identity, e["revision"], state, now_ms, reason)
