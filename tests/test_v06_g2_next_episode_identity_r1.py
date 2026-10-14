"""Invented clocks, causal structures and zone ticks only; no market/outcome data."""

import sys
from dataclasses import replace
from itertools import permutations
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_next_episode_identity_r1 import (
    HOUR,
    Alert,
    Clock,
    Seed,
    count_episodes,
)

DAY = 24 * HOUR
CLOCK = Clock(0, 3 * DAY, known_at=0)


def seed(name="structure-A", **changes):
    return replace(Seed(name, 12 * HOUR, "synthetic-source-hash", 0, 3 * DAY, 10, 20), **changes)


def bar_witness(decision_at: int, minutes: int) -> dict:
    duration = minutes * 60
    bar_end = decision_at - decision_at % duration
    bar_start = bar_end - duration
    return {
        "confirmation_bar_start": bar_start,
        "confirmation_bar_end": bar_end,
        "confirmation_received_at": bar_end,
        "confirmation_receiver_witnessed": True,
        "price_window_start": bar_start,
        "price_window_end": bar_end,
    }


def alert(s=None, **changes):
    decision = changes.pop("decision_at", 12 * HOUR + 5 * 60)
    minutes = changes.pop("confirmation_minutes", 5)
    oi_event = changes.pop("oi_event_at", 12 * HOUR)
    oi_received = changes.pop("oi_received_at", 12 * HOUR + 60)
    quote = changes.get("quote_screen_passed", False)
    window = bar_witness(decision, minutes)
    witness = {
        **window,
        "decision_at": decision,
        "confirmation_minutes": minutes,
        "oi_event_at": oi_event,
        "oi_received_at": oi_received,
        "oi_source_status": "COMPLETE",
        "oi_window_start": oi_event - 60,
        "oi_window_end": oi_event,
        "state_known_at": window["confirmation_received_at"],
    }
    if quote:
        witness.update({
            "quote_window_start": decision - 60,
            "quote_window_end": decision,
            "quote_known_at": decision,
        })
    witness.update(changes)
    return replace(
        Alert(
            seed() if s is None else s,
            decision,
            minutes,
            "LONG",
            15,
            "epoch-1",
        ),
        **witness,
    )


def count(rows, **changes):
    return count_episodes(
        rows,
        **{
            "clock": CLOCK,
            "as_of": 3 * DAY,
            "max_oi_age_seconds": HOUR,
            **changes,
        },
    )


def conserve(result):
    assert result.raw_alert == len(result.decisions)
    assert result.episode <= result.raw_alert - result.duplicate_alert - result.unknown_alert
    assert (
        0
        <= result.hypothetical_portfolio_admitted
        <= result.quote_screened_conditional
        <= result.pit_qualified
        <= result.episode
    )
    assert result.rate_status == "RATE_NOT_ADMITTED"


def test_1205_1215_1230_same_original_seed():
    a = alert(quote_screen_passed=True, hypothetical_admission_requested=True)
    rows = [
        a,
        alert(a.seed, decision_at=12 * HOUR + 15 * 60, confirmation_minutes=15,
              quote_screen_passed=True, hypothetical_admission_requested=True),
        alert(a.seed, decision_at=12 * HOUR + 30 * 60, confirmation_minutes=30,
              quote_screen_passed=True, hypothetical_admission_requested=True),
    ]
    r = count(rows)
    assert (
        r.raw_alert,
        r.episode,
        r.pit_qualified,
        r.quote_screened_conditional,
        r.hypothetical_portfolio_admitted,
    ) == (3, 1, 1, 1, 1)
    conserve(r)


def test_reconnect_replay_permutation_and_stable_ids():
    a = alert()
    rows = [
        a,
        replace(a, connection_epoch="epoch-2"),
        alert(a.seed, confirmation_minutes=15, decision_at=12 * HOUR + 900),
    ]
    expected = count(rows)
    for order in permutations(rows):
        assert count(order) == expected
    replay = count(rows + rows)
    assert replay.episode_ids == expected.episode_ids
    assert replay.pit_qualified == 1
    assert replay.duplicate_alert == 4
    conserve(replay)


def test_opposite_side_never_adds_an_episode():
    a = alert()
    r = count([a, replace(a, side="SHORT")])
    assert r.episode == 1 and r.pit_qualified == 0
    assert {d.reason for d in r.decisions} == {"SIDE_CONFLICT"}
    later = count([a, replace(a, side="SHORT", decision_at=a.decision_at + 60)])
    assert later.pit_qualified == 1
    assert later.decisions[-1].reason == "SIDE_CONFLICT"
    conserve(later)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"oi_received_at": 13 * HOUR}, "OI_NOT_PIT"),
        ({"oi_event_at": 10 * HOUR, "oi_received_at": 13 * HOUR}, "OI_NOT_PIT"),
        ({"oi_event_at": 10 * HOUR, "oi_received_at": 11 * HOUR}, "OI_NOT_PIT"),
        ({"oi_event_at": 13 * HOUR, "oi_received_at": 12 * HOUR}, "OI_NOT_PIT"),
        ({"state_known_at": 13 * HOUR}, "FUTURE_STATE"),
        ({"source_gap": True}, "SOURCE_GAP"),
        ({"state": "PROVISIONAL"}, "PROVISIONAL"),
        ({"zone_tick": 20}, "OUTSIDE_PRECOMMITTED_EQUIVALENCE"),
    ],
)
def test_pit_and_equivalence_negative_cases(changes, reason):
    r = count([alert(**changes)])
    assert r.pit_qualified == 0
    assert r.decisions[0].reason == reason
    conserve(r)


def test_missing_or_future_seed_is_unknown_not_window_inference():
    a = alert()
    r = count([replace(a, seed=None), replace(a, seed=seed(first_known_at=13 * HOUR))])
    assert (r.unknown_alert, r.episode, r.pit_qualified) == (2, 0, 0)
    conserve(r)


def test_temporal_zone_equivalence_requires_original_seed_and_source():
    a = alert()
    r = count([a, alert(seed("structure-B")), alert(seed(source_identity_hash="other-source"))])
    assert r.episode == 3  # Identical timestamps/zones do not merge distinct causal seeds.
    assert count([replace(a, seed=seed(window_end=a.decision_at))]).pit_qualified == 0
    assert seed().episode_id == seed(zone_low=9).episode_id
    with pytest.raises(ValueError, match="conflicting precommitted"):
        count([a, alert(seed(zone_low=9), confirmation_minutes=15)])


def test_invalidation_latches_and_genuine_rearm_after_cooldown():
    original = seed()
    a = alert(original)
    invalid = replace(a, state="INVALIDATED", decision_at=13 * HOUR, state_known_at=13 * HOUR)
    reused = replace(a, decision_at=14 * HOUR, oi_event_at=14 * HOUR, oi_received_at=14 * HOUR)
    new = seed(
        first_known_at=15 * HOUR, parent_episode_id=original.episode_id, cooldown_seconds=2 * HOUR
    )
    rearm = alert(
        new,
        decision_at=15 * HOUR,
        state_known_at=15 * HOUR,
        oi_event_at=15 * HOUR,
        oi_received_at=15 * HOUR,
    )
    r = count([rearm, reused, invalid, a])
    assert r.episode == 2 and r.pit_qualified == 2
    assert r.decisions[2].reason == "INVALIDATED"
    for order in permutations([a, invalid, reused, rearm]):
        assert count(order) == r
    conserve(r)


@pytest.mark.parametrize("first,parent", [(14 * HOUR, True), (15 * HOUR, False)])
def test_cooldown_and_rearm_cannot_be_bypassed(first, parent):
    old = seed()
    invalid = alert(old, state="INVALIDATED", decision_at=13 * HOUR)
    new = seed(
        first_known_at=first,
        parent_episode_id=old.episode_id if parent else None,
        cooldown_seconds=2 * HOUR,
    )
    r = count([invalid, alert(new, decision_at=first)])
    assert r.decisions[-1].reason == "REARM_NOT_CAUSAL"
    assert r.pit_qualified == 0


def test_parent_must_actually_be_invalidated():
    old = seed()
    new = seed(first_known_at=15 * HOUR, parent_episode_id=old.episode_id)
    r = count([alert(old), alert(new, decision_at=15 * HOUR)])
    assert r.decisions[-1].reason == "REARM_NOT_CAUSAL"


def test_future_rows_do_not_change_prefix_and_late_oi_never_backfills():
    a = alert(oi_received_at=14 * HOUR)
    cutoff = 13 * HOUR
    future = alert(seed("future", first_known_at=15 * HOUR), decision_at=16 * HOUR)
    assert count([a], as_of=cutoff) == count([future, a], as_of=cutoff)
    assert count([a], as_of=18 * HOUR).pit_qualified == 0
    assert count([a], as_of=cutoff).episode_ids == (seed().episode_id,)


def test_missing_censored_and_precommitted_24h_occupancy_denominators():
    clock = Clock(
        0,
        3 * DAY,
        0,
        missing=((0, 2 * HOUR), (HOUR, 3 * HOUR)),
        censored=((2 * HOUR, 4 * HOUR),),
        occupied=((DAY, 2 * DAY),),
    )
    r = count([], clock=clock)
    assert (r.calendar_clock_hours, r.eligible_clock_hours) == (72, 44)
    a = alert(
        decision_at=DAY,
        oi_event_at=DAY,
        oi_received_at=DAY,
        quote_screen_passed=True,
        hypothetical_admission_requested=True,
    )
    r = count([a], clock=clock)
    assert r.quote_screened_conditional == 1 and r.hypothetical_portfolio_admitted == 0
    assert r.decisions[0].reason == "PORTFOLIO_OCCUPIED"
    gap = replace(clock, missing=((12 * HOUR, 13 * HOUR),))
    assert count([alert()], clock=gap).decisions[0].reason == "SOURCE_GAP"
    censored = replace(clock, censored=((12 * HOUR, 13 * HOUR),))
    assert count([alert()], clock=censored).pit_qualified == 0
    conserve(r)


def test_overlapping_4_to_24h_holds_and_stable_tie_breaker():
    rows = [
        alert(
            seed(name, planned_hold_seconds=hours * HOUR),
            quote_screen_passed=True,
            hypothetical_admission_requested=True,
        )
        for name, hours in [("A", 4), ("B", 12), ("C", 24)]
    ]
    expected = count(rows)
    assert expected.quote_screened_conditional == 3
    assert expected.hypothetical_portfolio_admitted == 1
    assert len(expected.planned_holds) == 1
    assert [d.reason for d in expected.decisions].count("PORTFOLIO_OCCUPIED") == 2
    for order in permutations(rows):
        assert count(order) == expected
    _, _, end = expected.planned_holds[0]
    next_alert = alert(
        seed("next", first_known_at=end),
        decision_at=end,
        state_known_at=end,
        oi_event_at=end,
        oi_received_at=end,
        quote_screen_passed=True,
        hypothetical_admission_requested=True,
    )
    assert count(rows + [next_alert]).hypothetical_portfolio_admitted == 2
    conserve(expected)


def test_quote_screen_is_conditional_and_admission_requires_every_stage():
    a = alert(hypothetical_admission_requested=True)
    assert count([a]).hypothetical_portfolio_admitted == 0
    r = count([replace(a, quote_screen_passed=True, source_gap=True)])
    assert r.quote_screened_conditional == r.hypothetical_portfolio_admitted == 0
    assert "fill" not in r.__dataclass_fields__


def test_zero_events_and_no_forced_frequency():
    r = count([])
    assert (r.raw_alert, r.episode, r.pit_qualified, r.hypothetical_portfolio_admitted) == (
        0,
        0,
        0,
        0,
    )
    assert r.calendar_clock_hours == r.eligible_clock_hours == 72
    assert count([], as_of=0).eligible_clock_hours == 0
    assert count([], clock=replace(CLOCK, occupied=((0, 3 * DAY),))).eligible_clock_hours == 0
    conserve(r)


@pytest.mark.parametrize(
    "changes",
    [
        {"structure_id": ""},
        {"source_identity_hash": ""},
        {"zone_high": 10},
        {"cooldown_seconds": -1},
        {"planned_hold_seconds": HOUR},
        {"planned_hold_seconds": 25 * HOUR},
        {"plan_known_at": 13 * HOUR},
    ],
)
def test_invalid_precommitments_fail_closed(changes):
    with pytest.raises(ValueError):
        seed(**changes)


def test_provisional_seed_cannot_be_relabelled_with_a_new_first_known():
    old = seed()
    new = seed(first_known_at=13 * HOUR)
    r = count([alert(old, state="PROVISIONAL"), alert(new, decision_at=13 * HOUR)])
    assert r.pit_qualified == 0
    assert r.decisions[-1].reason == "REARM_NOT_CAUSAL"


def test_simultaneous_invalidation_precedes_confirmation():
    a = alert()
    invalid = replace(a, state="INVALIDATED")
    assert count([a, invalid]) == count([invalid, a])
    assert count([a, invalid]).pit_qualified == 0


def test_future_evidence_changes_never_change_canonical_seed_identity():
    a = alert(oi_received_at=14 * HOUR)
    b = replace(a, oi_received_at=20 * HOUR, state_known_at=18 * HOUR)
    assert count([a]).episode_ids == (seed().episode_id,)
    assert count([b]).episode_ids == ()  # FUTURE_STATE cannot reserve a cohort.
    assert count([a]).pit_qualified == count([b]).pit_qualified == 0


@pytest.mark.parametrize("stage", ["quote", "admission"])
def test_downstream_stage_evidence_cannot_backfill_decision(stage):
    a = alert(quote_screen_passed=True, hypothetical_admission_requested=True)
    a = replace(a, **{f"{stage}_known_at": a.decision_at + 60})
    r = count([a], as_of=a.decision_at)
    assert r.pit_qualified == 1
    assert r.quote_screened_conditional == (stage == "admission")
    assert r.hypothetical_portfolio_admitted == 0
    assert r.decisions[0].reason == f"{stage.upper()}_NOT_PIT"
    assert count([a], as_of=a.decision_at + HOUR).hypothetical_portfolio_admitted == 0
    conserve(r)


# R2 independently falsifiable invented-clock regressions (E01-E04).
def test_r2_e01_unclosed_30m_confirmation_must_not_be_pit() -> None:
    a = alert(
        confirmation_minutes=30,
        confirmation_bar_start=12 * HOUR,
        confirmation_bar_end=12 * HOUR + 30 * 60,
        confirmation_received_at=12 * HOUR + 30 * 60,
        confirmation_receiver_witnessed=True,
    )
    r = count([a])
    assert r.pit_qualified == 0
    assert r.decisions[0].reason == "CONFIRMATION_NOT_PIT"


def test_r2_e02_future_state_must_not_poison_later_valid_seed() -> None:
    old = seed()
    future = alert(old, state_known_at=14 * HOUR)
    new = seed(first_known_at=12 * HOUR + 10 * 60)
    valid = alert(
        new, decision_at=12 * HOUR + 15 * 60,
        state_known_at=12 * HOUR + 15 * 60,
        oi_event_at=12 * HOUR + 10 * 60,
        oi_received_at=12 * HOUR + 11 * 60,
    )
    assert count([valid]).pit_qualified == 1
    observed = count([future, valid])
    assert [d.reason for d in observed.decisions] == [
        "FUTURE_STATE", "PIT_QUALIFIED"
    ]
    assert observed.episode == 1 and observed.pit_qualified == 1


def test_r2_e03_missing_confirmation_feature_window_blocks_pit() -> None:
    a = alert()
    unavailable = replace(
        CLOCK, missing=((12 * HOUR, 12 * HOUR + 5 * 60),)
    )
    r = count([a], clock=unavailable)
    assert r.pit_qualified == 0
    assert r.decisions[0].reason == "SOURCE_GAP"


def test_r2_e04_opaque_source_id_cannot_be_source_qualified() -> None:
    a = alert()
    assert a.seed is not None
    assert a.seed.source_identity_kind == "SYNTHETIC_OPAQUE_ID"
    r = count([a])
    assert r.source_qualified == 0
    assert r.source_status == "SOURCE_IDENTITY_UNVERIFIED"
    assert r.rate_status == "RATE_NOT_ADMITTED"


def test_r2_e01_prior_closed_30m_witness_qualifies_at_1205():
    a = alert(
        confirmation_minutes=30,
        confirmation_bar_start=11 * HOUR + 30 * 60,
        confirmation_bar_end=12 * HOUR,
        confirmation_received_at=12 * HOUR + 2 * 60,
        confirmation_receiver_witnessed=True,
        state_known_at=12 * HOUR + 2 * 60,
        price_window_start=11 * HOUR + 30 * 60,
        price_window_end=12 * HOUR,
    )
    assert count([a]).pit_qualified == 1


def test_r2_e01_missing_bar_or_receiver_proof_stays_unqualified():
    a = alert()
    for changed in (
        {"confirmation_receiver_witnessed": False},
        {"confirmation_received_at": None},
        {"confirmation_bar_end": None},
        {"confirmation_bar_start": None},
    ):
        assert count([replace(a, **changed)]).pit_qualified == 0


def test_r2_e02_authentic_provisional_reservation_is_not_lost():
    original = seed()
    other = seed(first_known_at=13 * HOUR)
    rows = [alert(original, state="PROVISIONAL"), alert(other, decision_at=13 * HOUR)]
    r = count(rows)
    assert r.decisions[-1].reason == "REARM_NOT_CAUSAL"
    assert r.pit_qualified == 0


@pytest.mark.parametrize("stage", ["price", "confirmation", "quote", "oi"])
def test_r2_e03_each_required_window_gap_blocks(stage):
    a = alert(quote_screen_passed=True, hypothetical_admission_requested=True)
    intervals = {
        "price": (a.price_window_start, a.price_window_end),
        "confirmation": (a.confirmation_bar_start, a.confirmation_bar_end),
        "quote": (a.quote_window_start, a.quote_window_end),
        "oi": (a.oi_window_start, a.oi_window_end),
    }
    start, end = intervals[stage]
    assert start is not None and end is not None
    assert count([a], clock=replace(CLOCK, censored=((start, end),))).pit_qualified == 0


def test_r2_e03_unknown_oi_is_not_complete_oi():
    a = alert(oi_source_status="UNKNOWN")
    r = count([a])
    assert r.pit_qualified == 0 and r.decisions[0].reason == "OI_UNKNOWN"


def test_r2_e04_source_qualified_identity_cannot_be_forged_by_string():
    s = seed(source_identity_hash="a" * 64)
    assert count([alert(s)]).source_qualified == 0
    with pytest.raises(ValueError, match="external admitted contract"):
        seed(source_identity_kind="SHA256_VERIFIED")


def test_r2_quote_receiver_clock_must_follow_quote_window():
    a = alert(quote_screen_passed=True, quote_known_at=12 * HOUR)
    r = count([a])
    assert r.pit_qualified == 1
    assert r.quote_screened_conditional == 0
    assert r.decisions[0].reason == "QUOTE_NOT_PIT"


def test_r2_required_feature_window_cannot_precede_clock_coverage():
    a = alert()
    r = count([a], clock=Clock(12 * HOUR, 3 * DAY, known_at=12 * HOUR))
    assert r.pit_qualified == 0
    assert r.decisions[0].reason == "SOURCE_EVIDENCE_UNKNOWN"
