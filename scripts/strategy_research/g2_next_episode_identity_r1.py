"""Synthetic-only causal episode accounting; no feeds, outcomes, fills or rate inference.

Times are integer seconds on an invented clock; zone coordinates are invented ticks.
Intervals are half-open. Seed windows/zones, cooldown and holds are precommitted
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

    def __post_init__(self) -> None:
        if not 4 * HOUR <= self.planned_hold_seconds <= 24 * HOUR:
            raise ValueError("4h–24h planned hold required")
        if self.plan_known_at > self.first_known_at:
            raise ValueError("hold must be precommitted by seed first-known")
        if not self.structure_id or not self.source_identity_hash:
            raise ValueError("original causal structure and source identity required")
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

    def __post_init__(self) -> None:
        if self.confirmation_minutes not in (5, 15, 30):
            raise ValueError("unsupported confirmation")
        if self.side not in ("LONG", "SHORT"):
            raise ValueError("invalid side")
        if self.state not in ("PROVISIONAL", "CONFIRMED", "INVALIDATED"):
            raise ValueError("invalid state")
        if not self.connection_epoch:
            raise ValueError("connection epoch required")

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
            seeds[eid] = seed
            parent = seed.parent_episode_id
            family = (seed.source_identity_hash, seed.structure_id)
            previous = lineage.get(family)
            lineage.setdefault(family, eid)
            if a.state_known_at > a.decision_at:
                reason = "FUTURE_STATE"
            elif (previous is not None and previous != eid and parent != previous) or (
                parent is not None
                and (
                    parent not in invalidated
                    or seed.first_known_at < invalidated[parent] + seed.cooldown_seconds
                    or parent == eid
                )
            ):
                reason = "REARM_NOT_CAUSAL"
            elif a.state == "INVALIDATED":
                lineage[family] = eid
                invalidated.setdefault(eid, a.decision_at)
                reason = "INVALIDATED"
            elif eid in invalidated:
                reason = "INVALIDATED"
            elif a.state == "PROVISIONAL":
                lineage[family] = eid
                reason = "PROVISIONAL"
            elif not (
                seed.window_start <= a.decision_at < seed.window_end
                and seed.zone_low <= a.zone_tick < seed.zone_high
            ):
                reason = "OUTSIDE_PRECOMMITTED_EQUIVALENCE"
            elif len(simultaneous.get((eid, a.decision_at), set())) > 1 or (
                eid in sides and sides[eid] != a.side
            ):
                reason = "SIDE_CONFLICT"
            else:
                lineage[family] = eid
                sides[eid] = a.side
                if a.source_gap or _overlap(
                    a.decision_at, a.decision_at + 1, clock.missing + clock.censored
                ):
                    reason = "SOURCE_GAP"
                elif not (
                    a.oi_event_at <= a.oi_received_at <= a.decision_at
                    and 0 <= a.decision_at - a.oi_event_at <= max_oi_age_seconds
                ):
                    reason = "OI_NOT_PIT"
                else:
                    pit.add(eid)
                    reason = "PIT_QUALIFIED"
                    if a.quote_screen_passed and a.quote_known_at > a.decision_at:
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
