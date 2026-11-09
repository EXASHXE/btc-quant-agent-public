from copy import deepcopy
from dataclasses import replace

import pytest

from q0b.examples import SETUP_END, modify_bar, snapshot
from q0b.schema import MINUTE, Policy, STATES
from q0b.strategy import Engine, PairedComparison


def watched(**kwargs):
    engine = Engine()
    assert engine.review(snapshot(0, include_15m=False, **kwargs)).state == "WATCH"
    return engine


def test_finished_hourly_setup_survives_absent_15m():
    engine = watched()
    card = engine.review(snapshot(15, include_15m=False))
    assert card.state == "WATCH"
    assert card.plan["hard_stop"] < card.plan["structural_invalidation"]
    assert len(card.plan["targets"]) >= 2
    assert card.plan["target_evidence"]
    assert all(p["available_ms"] <= card.asof_ms for p in card.plan["target_evidence"])


def test_positive_confirmation_requires_preexisting_watch():
    late_start = Engine().review(snapshot(15))
    assert late_start.state == "WATCH"
    engine = watched()
    card = engine.review(snapshot(15))
    assert card.state == "ENTRY_READY"
    assert card.plan["review_actionability"]["respond_by_ms"] <= card.plan["review_actionability"]["ready_valid_until_ms"]
    assert card.realized_r is None


def test_false_15m_trigger_cannot_upgrade():
    card = watched().review(snapshot(15, false_15m=True))
    assert card.state == "WATCH"
    assert "15M_FALSE_TRIGGER" in card.reasons[0]


def test_four_hour_conflict_vetoes_ready_but_preserves_watch():
    card = watched(four_down=True).review(snapshot(15, four_down=True))
    assert card.state == "WATCH"
    assert card.reasons == ("FOUR_HOUR_CONFLICT_VETO_READY",)


def test_daily_countertrend_is_permitted_with_smaller_paper_risk():
    baseline = watched().review(snapshot(15))
    card = watched(daily_down=True).review(snapshot(15, daily_down=True))
    assert card.state == "ENTRY_READY"
    assert "DAILY_COUNTERTREND_RISK" in card.plan["warnings"]
    assert card.plan["economics"]["paper_risk_budget"] == baseline.plan["economics"]["paper_risk_budget"] / 2


@pytest.mark.parametrize("interval,expected", [("4H", "WATCH"), ("1D", "ENTRY_READY")])
def test_late_context_receipt_refreshes_risk_for_existing_setup(interval, expected):
    initial = snapshot(0, include_15m=False)
    # At the first few seconds of a boundary, the most recent context receipt may be late.
    groups = []
    for b in initial.batches:
        if b.interval == interval:
            rows = b.bars[:-1]
            b = replace(b, bars=rows, requested_end_ms=rows[-1].end_ms)
        groups.append(b)
    engine = Engine()
    watch = engine.review(replace(initial, batches=tuple(groups)))
    assert watch.state == "WATCH"
    followup = modify_bar(snapshot(15), interval, open=90, high=91, low=89, close=90)
    card = engine.review(followup)
    assert card.state == expected
    assert card.candidate_id == watch.candidate_id
    assert card.plan["hard_stop"] == watch.plan["hard_stop"]
    if interval == "4H":
        assert card.reasons == ("FOUR_HOUR_CONFLICT_VETO_READY",)
    else:
        assert card.plan["economics"]["paper_risk_budget"] == watch.plan["economics"]["paper_risk_budget"] / 2


@pytest.mark.parametrize("touch", ["stop", "target"])
def test_touch_kills_setup_without_resurrection(touch):
    engine = watched()
    initial = engine.candidates["BTCUSDT"].plan
    s = snapshot(15)
    s = modify_bar(s, "15m", **({"low": initial["hard_stop"]} if touch == "stop"
                               else {"high": initial["targets"][0]}))
    card = engine.review(s)
    assert card.state == "INVALIDATED"
    # Repeat the same immutable receipts with a fresh quote; terminal state remains.
    repeated = engine.review(replace(s, quote=snapshot(16).quote, asof_ms=snapshot(16).asof_ms,
                                     clock=snapshot(16).clock))
    assert repeated.state == "INVALIDATED"
    assert repeated.candidate_id == card.candidate_id


def test_expiry_separate_from_hold_lifetime_and_no_old_ready():
    engine = watched()
    ready = engine.review(snapshot(15))
    expired = engine.review(snapshot(45))
    assert ready.state == "ENTRY_READY"
    assert expired.state == "EXPIRED"
    assert expired.plan["entry_expires_ms"] == SETUP_END + 45 * MINUTE
    assert expired.plan["holding_hours_from_hypothetical_fill"] == 6
    assert expired.plan["absolute_holding_deadline_ms"] is None
    assert engine.review(snapshot(46)).state == "EXPIRED"


def test_repeated_15m_cannot_reissue_ready_or_extend_window():
    engine = watched()
    first = engine.review(snapshot(15))
    again = engine.review(snapshot(16))
    assert first.state == "ENTRY_READY"
    assert again.state == "WATCH"
    assert again.reasons == ("NO_NEW_MATCHING_15M_CONFIRMATION",)
    assert "review_actionability" not in again.plan


def test_new_15m_can_confirm_same_still_valid_setup():
    engine = watched()
    first = engine.review(snapshot(15))
    second = engine.review(snapshot(30))
    assert first.state == second.state == "ENTRY_READY"
    assert first.candidate_id == second.candidate_id
    assert second.plan["entry_expires_ms"] == first.plan["entry_expires_ms"]


def test_stale_5m_refuses_actionability_without_changing_direction():
    card = watched(quote=False).review(snapshot(15, quote=False, five_lag_minutes=10))
    assert card.state == "WATCH"
    assert card.reasons == ("STALE_OR_MISSING_5M_ACTIONABILITY",)
    assert card.plan["direction"] == "LONG"


def test_stale_quote_does_not_fall_back_to_more_favorable_5m():
    s = snapshot(15)
    s = replace(s, quote=replace(s.quote, exchange_ms=s.asof_ms - 2 * MINUTE))
    assert watched().review(s).reasons == ("STALE_VENUE_QUOTE",)


@pytest.mark.parametrize("response", [5, 10])
def test_declared_human_response_window(response):
    engine = Engine(Policy(response_minutes=response))
    engine.review(snapshot(0, include_15m=False))
    ready = engine.review(snapshot(15))
    action = ready.plan["review_actionability"]
    assert ready.state == "ENTRY_READY"
    assert action["respond_by_ms"] - ready.asof_ms == response * MINUTE
    assert action["ready_valid_until_ms"] - ready.asof_ms >= response * MINUTE


def test_insufficient_window_refused_at_review():
    engine = watched()
    # Near 45m expiry a new confirmation has just closed, but ten minutes no longer remain.
    s = snapshot(30)
    s = replace(s, asof_ms=SETUP_END + 36 * MINUTE,
                clock=replace(s.clock, sampled_ms=SETUP_END + 36 * MINUTE - 100,
                              exchange_lower_ms=SETUP_END + 36 * MINUTE - 50,
                              exchange_upper_ms=SETUP_END + 36 * MINUTE + 50))
    card = engine.review(s)
    assert card.state == "WATCH"
    assert card.reasons == ("CONFIRMATION_TOO_OLD_FOR_NEW_READY",)


@pytest.mark.parametrize("minute,expected", [(34, "ENTRY_READY"), (36, "WATCH")])
def test_control_enforces_remaining_response_time(minute, expected):
    engine = Engine(arm="CONTROL_1H_ONLY")
    engine.review(snapshot(0, include_15m=False))
    card = engine.review(snapshot(minute, include_15m=False))
    assert card.state == expected
    if minute == 36:
        assert card.reasons == ("INSUFFICIENT_5_TO_10_MINUTE_RESPONSE_WINDOW",)


def test_no_primary_setup_is_not_rescued_by_positive_15m():
    s = modify_bar(snapshot(15), "1H", close=99.5)
    assert Engine().review(s).state == "NO_SETUP"


def test_no_chase_even_with_favorable_5m():
    s = snapshot(15)
    s = replace(s, quote=replace(s.quote, bid=102, ask=102.1))
    card = watched().review(s)
    assert card.state == "WATCH"
    assert card.reasons == ("NO_CHASE_PRICE_OUTSIDE_1H_ZONE",)


def test_5m_is_price_only_and_can_have_opposite_candle_direction():
    s = modify_bar(snapshot(15, quote=False), "5m", open=100.8)
    card = watched(quote=False).review(s)
    assert card.state == "ENTRY_READY"
    assert card.plan["direction"] == "LONG"
    assert card.plan["economics"]["capacity_quantity_bound"] is None


def test_costs_gross_scenarios_and_realized_are_separate():
    card = watched().review(snapshot(15))
    e = card.plan["economics"]
    gross = e["planned_gross_r_by_tp"]
    normal = e["scenarios"]["conservative"]["planned_after_cost_r_by_tp"]
    stress = e["scenarios"]["stress"]["planned_after_cost_r_by_tp"]
    assert all(g > n > s for g, n, s in zip(gross, normal, stress))
    assert e["realized_r"] is card.realized_r is None
    assert e["paper_quantity_upper_bound"] <= e["capacity_quantity_bound"]
    assert e["execution_claim"] is False


def test_tp3_is_omitted_when_only_two_observable_levels_exist():
    def two_levels(s):
        groups = []
        for group in s.batches:
            if group.interval == "1H":
                rows = tuple(replace(b, open=min(b.open, 104), high=min(b.high, 104),
                                     low=min(b.low, 104), close=min(b.close, 104)) for b in group.bars)
                group = replace(group, bars=rows)
            groups.append(group)
        return replace(s, batches=tuple(groups))
    engine = Engine()
    assert engine.review(two_levels(snapshot())).state == "WATCH"
    card = engine.review(two_levels(snapshot(15)))
    assert card.state == "ENTRY_READY"
    assert len(card.plan["targets"]) == 2
    assert card.plan["tp3_optional"] is False
    assert set(card.plan["targets"]) <= {p["price"] for p in card.plan["target_evidence"]}


def test_adverse_visible_spread_can_refuse_otherwise_valid_confirmation():
    s = snapshot(15)
    s = replace(s, quote=replace(s.quote, bid=97.3))
    card = watched().review(s)
    assert card.state == "WATCH"
    assert card.reasons == ("NONPOSITIVE_STRESS_PLANNED_R",)
    assert card.plan["economics"]["scenarios"]["stress"]["planned_after_cost_r_by_tp"][0] <= 0


def test_short_hold_still_charges_one_full_adverse_funding_window():
    engine = Engine(Policy(holding_hours=2))
    engine.review(snapshot())
    card = engine.review(snapshot(15))
    assert card.plan["economics"]["scenarios"]["conservative"]["adverse_funding_windows"] == 1


def test_predeclared_extension_increases_planned_funding_no_realized_r():
    engine = Engine(Policy(planned_extension_hours=24))
    engine.review(snapshot(0))
    extended = engine.review(snapshot(15))
    baseline = watched().review(snapshot(15))
    a = extended.plan["economics"]["scenarios"]["stress"]["cost_per_unit_by_tp"]
    b = baseline.plan["economics"]["scenarios"]["stress"]["cost_per_unit_by_tp"]
    assert all(x > y for x, y in zip(a, b))
    assert extended.plan["planned_extension_hours"] == 24


@pytest.mark.parametrize("kwargs", [{"holding_hours": 1}, {"holding_hours": 13},
                                    {"planned_extension_hours": 25}, {"response_minutes": 4},
                                    {"response_minutes": 11}, {"atr_buffer": 0.1}])
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ValueError):
        Policy(**kwargs)


def test_1h_only_control_ready_without_15m_and_deterministic_pairing():
    first, replay = PairedComparison(), PairedComparison()
    for s in (snapshot(0, include_15m=False), snapshot(15, include_15m=False)):
        result = first.review(s)
        assert result == replay.review(s)
        assert result["same_candidate"]
        assert result["forward_outcomes"] is result["realized_r_delta"] is None
    assert result["mtf"]["state"] == "WATCH"
    assert result["control"]["state"] == "ENTRY_READY"
    assert first.review(snapshot(16, include_15m=False))["control"]["state"] == "WATCH"


def test_short_side_is_symmetric_synthetic_geometry():
    def mirror(s):
        batches = []
        for group in s.batches:
            rows = tuple(replace(b, open=200-b.open, high=200-b.low,
                                 low=200-b.high, close=200-b.close) for b in group.bars)
            batches.append(replace(group, bars=rows))
        q = replace(s.quote, bid=200-s.quote.ask, ask=200-s.quote.bid)
        return replace(s, batches=tuple(batches), quote=q)
    engine = Engine()
    assert engine.review(mirror(snapshot(0))).state == "WATCH"
    ready = engine.review(mirror(snapshot(15)))
    assert ready.state == "ENTRY_READY"
    assert ready.plan["direction"] == "SHORT"
    assert ready.plan["hard_stop"] > ready.plan["structural_invalidation"]
    assert ready.plan["targets"] == sorted(ready.plan["targets"], reverse=True)


def test_cards_do_not_mutate_engine_state():
    engine = watched()
    ready = engine.review(snapshot(15))
    original = deepcopy(engine.candidates["BTCUSDT"].plan)
    ready.plan["targets"].clear()
    assert engine.candidates["BTCUSDT"].plan == original


def test_unknown_schema_is_never_ready():
    card = Engine().review(None)
    assert card.state == "UNKNOWN"
    assert card.state in STATES
