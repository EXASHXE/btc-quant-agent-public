"""Synthetic-only causal episode accounting; no feeds, outcomes, fills or rate inference.

Times are integer seconds on an invented clock; zone coordinates are invented ticks.
Intervals are half-open. R2 requires explicit invented receiver/closed-bar and
feature-window evidence, never inferring confirmation from a state label.
Legacy source_identity_hash is a SYNTHETIC_OPAQUE_ID, not a verified hash. Seed windows/zones, cooldown and holds are precommitted
inputs, never inferred from confirmations. Replay a prefix with ``as_of`` to audit PIT.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from hashlib import sha256

HOUR = 3600


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Seed:
    structure_id: str
    first_known_at: int
    source_identity_hash: str
    window_start: int
    window_end: int
    zone_low: int
    zone_high: int
    parent_episode_id: str | None = None
    cooldown_seconds: int = 0
    planned_hold_seconds: int = 4 * HOUR
    plan_known_at: int = 0
    source_identity_kind: str = "SYNTHETIC_OPAQUE_ID"

    def __post_init__(self) -> None:
        if not 4 * HOUR <= self.planned_hold_seconds <= 24 * HOUR:
            raise ValueError("4h–24h planned hold required")
        if self.plan_known_at > self.first_known_at:
            raise ValueError("hold must be precommitted by seed first-known")
        if not self.structure_id or not self.source_identity_hash:
            raise ValueError("original causal structure and synthetic source ID required")
        if self.source_identity_kind != "SYNTHETIC_OPAQUE_ID":
            raise ValueError("source-qualified identity requires an external admitted contract")
        if not self.window_start <= self.first_known_at < self.window_end:
            raise ValueError("seed first-known must lie in its precommitted window")
        if self.zone_low >= self.zone_high or self.cooldown_seconds < 0:
            raise ValueError("invalid precommitted zone/cooldown")

    @property
    def episode_id(self) -> str:
        # Neither confirmation time, side, reconnect epoch nor later evidence belongs here.
        return _digest([self.source_identity_hash, self.structure_id, self.first_known_at])


@dataclass(frozen=True)
class Alert:
    seed: Seed | None
    decision_at: int
    confirmation_minutes: int
    side: str
    zone_tick: int
    connection_epoch: str
    state: str = "CONFIRMED"
    state_known_at: int = 0
    oi_event_at: int = 0
    oi_received_at: int = 0
    source_gap: bool = False
    quote_screen_passed: bool = False
    quote_known_at: int = 0
    hypothetical_admission_requested: bool = False
    admission_known_at: int = 0
    # V2 explicit synthetic receipt witnesses; None is never positive evidence.
    confirmation_bar_start: int | None = None
    confirmation_bar_end: int | None = None
    confirmation_received_at: int | None = None
    confirmation_receiver_witnessed: bool = False
    price_window_start: int | None = None
    price_window_end: int | None = None
    oi_source_status: str = "UNKNOWN"
    oi_window_start: int | None = None
    oi_window_end: int | None = None
    quote_window_start: int | None = None
    quote_window_end: int | None = None

    def __post_init__(self) -> None:
        if self.confirmation_minutes not in (5, 15, 30):
            raise ValueError("unsupported confirmation")
        if self.side not in ("LONG", "SHORT"):
            raise ValueError("invalid side")
        if self.state not in ("PROVISIONAL", "CONFIRMED", "INVALIDATED"):
            raise ValueError("invalid state")
        if not self.connection_epoch:
            raise ValueError("connection epoch required")
        if self.oi_source_status not in ("UNKNOWN", "COMPLETE"):
            raise ValueError("OI source status must be explicit")


    @property
    def replay_key(self) -> str:
        payload = asdict(self)
        payload.pop("connection_epoch")
        return _digest(payload)


@dataclass(frozen=True)
class Clock:
    start: int
    end: int
    known_at: int
    missing: tuple[tuple[int, int], ...] = ()
    censored: tuple[tuple[int, int], ...] = ()
    occupied: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        if self.start >= self.end or self.known_at > self.start:
            raise ValueError("clock/occupancy must be precommitted by window start")
        if any(a >= b for a, b in self.missing + self.censored + self.occupied):
            raise ValueError("invalid clock interval")


def _overlap(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(start < b and a < end for a, b in spans)


def _union_seconds(start: int, end: int, spans: Iterable[tuple[int, int]]) -> int:
    total, cursor = 0, start
    for a, b in sorted(spans):
        a, b = max(start, a), min(end, b)
        if b > max(a, cursor):
            total += b - max(a, cursor)
            cursor = b
    return total


@dataclass(frozen=True)
class Decision:
    alert_key: str
    episode_id: str | None
    reason: str


@dataclass(frozen=True)
class Accounting:
    raw_alert: int
    duplicate_alert: int
    unknown_alert: int
    episode: int
    pit_qualified: int
    quote_screened_conditional: int
    hypothetical_portfolio_admitted: int
    episode_ids: tuple[str, ...]
    decisions: tuple[Decision, ...]
    planned_holds: tuple[tuple[str, int, int], ...]
    calendar_clock_hours: float
    eligible_clock_hours: float
    rate_status: str = "RATE_NOT_ADMITTED"
    contract_version: str = "SYNTHETIC_EPISODE_CAUSAL_V2"
    source_qualified: int = 0
    source_status: str = "SOURCE_IDENTITY_UNVERIFIED"



def _complete_span(start: int | None, end: int | None, *, latest: int) -> bool:
    return start is not None and end is not None and start < end <= latest


def _confirmed_bar_pit(a: Alert) -> bool:
    duration = a.confirmation_minutes * 60
    start, end, received = (
        a.confirmation_bar_start, a.confirmation_bar_end, a.confirmation_received_at
    )
    return bool(
        a.confirmation_receiver_witnessed
        and start is not None
        and end is not None
        and received is not None
        and end - start == duration
        and start % duration == 0
        and end <= received <= a.decision_at
        and a.state_known_at >= received
    )


def _contributing_windows(a: Alert) -> tuple[tuple[int, int], ...] | None:
    """Every required feature is a closed, bounded, predecision invented span."""
    if not _complete_span(
        a.price_window_start, a.price_window_end, latest=a.decision_at
    ):
        return None
    if not _confirmed_bar_pit(a):
        return None
    assert a.confirmation_bar_start is not None
    assert a.confirmation_bar_end is not None
    assert a.price_window_start is not None
    assert a.price_window_end is not None
    spans = [
        (a.price_window_start, a.price_window_end),
        (a.confirmation_bar_start, a.confirmation_bar_end),
    ]
    # The price feature must include the entire confirmation bar.
    if (
        a.price_window_start > a.confirmation_bar_start
        or a.price_window_end < a.confirmation_bar_end
    ):
        return None
    if a.oi_source_status == "COMPLETE":
        if (
            not _complete_span(a.oi_window_start, a.oi_window_end, latest=a.decision_at)
            or a.oi_window_end != a.oi_event_at
        ):
            return None
        assert a.oi_window_start is not None and a.oi_window_end is not None
        spans.append((a.oi_window_start, a.oi_window_end))
    if a.quote_screen_passed:
        if not _complete_span(
            a.quote_window_start, a.quote_window_end, latest=a.decision_at
        ):
            return None
        assert a.quote_window_start is not None and a.quote_window_end is not None
        spans.append((a.quote_window_start, a.quote_window_end))
    return tuple(spans)


def count_episodes(
    alerts: Iterable[Alert], *, clock: Clock, as_of: int, max_oi_age_seconds: int
) -> Accounting:
    """Count nested stage sets, using a stable causal sort and single-slot portfolio.

    An opposite side never creates an extra episode. Simultaneous opposing alerts
    both fail; later opposition cannot erase an earlier qualification. Invalidations
    latch. Re-arm requires a distinct original seed naming an invalidated parent.
    Quote screens remain conditional and admitted holds remain hypothetical.
    Missing/censored time removes source eligibility; precommitted occupancy removes
    portfolio eligibility. Dynamic hypothetical holds do not change denominators.
    """
    if not clock.start <= as_of <= clock.end or max_oi_age_seconds < 0:
        raise ValueError("invalid as-of or freshness limit")
    rows = sorted(
        (a for a in alerts if clock.start <= a.decision_at <= as_of and a.decision_at < clock.end),
        key=lambda a: (a.decision_at, a.state != "INVALIDATED", a.replay_key),
    )
    seen: set[str] = set()
    seeds: dict[str, Seed] = {}
    sides: dict[str, str] = {}
    lineage: dict[tuple[str, str], str] = {}
    invalidated: dict[str, int] = {}
    pit: set[str] = set()
    quotes: set[str] = set()
    admitted: set[str] = set()
    holds: list[tuple[str, int, int]] = []
    decisions: list[Decision] = []
    duplicates = unknown = 0
    simultaneous: dict[tuple[str, int], set[str]] = {}
    for a in rows:
        if (
            a.seed
            and a.seed.first_known_at <= a.decision_at
            and a.state_known_at <= a.decision_at
            and a.state == "CONFIRMED"
        ):
            simultaneous.setdefault((a.seed.episode_id, a.decision_at), set()).add(a.side)
    for a in rows:
        key = a.replay_key
        eid = a.seed.episode_id if a.seed else None
        reason = "UNKNOWN"
        if key in seen:
            duplicates += 1
            reason = "DUPLICATE"
        elif a.seed is None or a.seed.first_known_at > a.decision_at:
            unknown += 1
        else:
            seed = a.seed
            assert eid is not None
            if eid in seeds and seeds[eid] != seed:
                raise ValueError("same causal seed has conflicting precommitted definitions")
            parent = seed.parent_episode_id
            family = (seed.source_identity_hash, seed.structure_id)
            previous = lineage.get(family)
            if a.state_known_at > a.decision_at:
                # Neither cohort nor lineage may be reserved by invalid future evidence.
                reason = "FUTURE_STATE"
                unknown += 1
            elif (previous is not None and previous != eid and parent != previous) or (
                parent is not None
                and (
                    parent not in invalidated
                    or seed.first_known_at < invalidated[parent] + seed.cooldown_seconds
                    or parent == eid
                )
            ):
                seeds[eid] = seed
                lineage.setdefault(family, eid)
                reason = "REARM_NOT_CAUSAL"
            elif a.state == "INVALIDATED":
                seeds[eid] = seed
                lineage[family] = eid
                invalidated.setdefault(eid, a.decision_at)
                reason = "INVALIDATED"
            elif eid in invalidated:
                seeds[eid] = seed
                reason = "INVALIDATED"
            elif a.state == "PROVISIONAL":
                seeds[eid] = seed
                lineage[family] = eid
                reason = "PROVISIONAL"
            elif not (
                seed.window_start <= a.decision_at < seed.window_end
                and seed.zone_low <= a.zone_tick < seed.zone_high
            ):
                seeds[eid] = seed
                lineage.setdefault(family, eid)
                reason = "OUTSIDE_PRECOMMITTED_EQUIVALENCE"
            elif len(simultaneous.get((eid, a.decision_at), set())) > 1 or (
                eid in sides and sides[eid] != a.side
            ):
                seeds[eid] = seed
                lineage.setdefault(family, eid)
                reason = "SIDE_CONFLICT"
            else:
                seeds[eid] = seed
                lineage[family] = eid
                sides[eid] = a.side
                spans = _contributing_windows(a)
                if a.source_gap:
                    reason = "SOURCE_GAP"
                elif not _confirmed_bar_pit(a):
                    reason = "CONFIRMATION_NOT_PIT"
                elif not _complete_span(
                    a.price_window_start, a.price_window_end, latest=a.decision_at
                ):
                    reason = "PRICE_EVIDENCE_UNKNOWN"
                elif a.oi_source_status != "COMPLETE":
                    reason = "OI_UNKNOWN"
                elif not (
                    a.oi_event_at <= a.oi_received_at <= a.decision_at
                    and 0 <= a.decision_at - a.oi_event_at <= max_oi_age_seconds
                ):
                    reason = "OI_NOT_PIT"
                elif spans is None or any(
                    start < clock.start or end > clock.end for start, end in spans
                ):
                    reason = "SOURCE_EVIDENCE_UNKNOWN"
                elif any(_overlap(start, end, clock.missing + clock.censored)
                         for start, end in spans):
                    reason = "SOURCE_GAP"
                else:
                    pit.add(eid)
                    reason = "PIT_QUALIFIED"
                    if a.quote_screen_passed and (
                        a.quote_known_at > a.decision_at
                        or a.quote_window_end is None
                        or a.quote_known_at < a.quote_window_end
                    ):
                        reason = "QUOTE_NOT_PIT"
                    elif a.quote_screen_passed:
                        quotes.add(eid)
                        reason = "QUOTE_SCREENED_CONDITIONAL"
                        if a.hypothetical_admission_requested and eid not in admitted:
                            end = a.decision_at + seed.planned_hold_seconds
                            if a.admission_known_at > a.decision_at:
                                reason = "ADMISSION_NOT_PIT"
                            elif _overlap(a.decision_at, end, clock.occupied) or _overlap(
                                a.decision_at, end, ((s, e) for _, s, e in holds)
                            ):
                                reason = "PORTFOLIO_OCCUPIED"
                            else:
                                admitted.add(eid)
                                holds.append((eid, a.decision_at, end))
                                reason = "HYPOTHETICAL_PORTFOLIO_ADMITTED"
        seen.add(key)
        decisions.append(Decision(key, eid, reason))
    excluded = _union_seconds(clock.start, as_of, clock.missing + clock.censored + clock.occupied)
    return Accounting(
        raw_alert=len(rows),
        duplicate_alert=duplicates,
        unknown_alert=unknown,
        episode=len(seeds),
        pit_qualified=len(pit),
        quote_screened_conditional=len(quotes),
        hypothetical_portfolio_admitted=len(admitted),
        episode_ids=tuple(sorted(seeds)),
        decisions=tuple(decisions),
        planned_holds=tuple(holds),
        calendar_clock_hours=(as_of - clock.start) / HOUR,
        eligible_clock_hours=(as_of - clock.start - excluded) / HOUR,
    )
