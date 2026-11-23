from __future__ import annotations

from dataclasses import replace
from decimal import Context, localcontext

import pytest

from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
from quant_personal_decision_b2.engine import Engine, market_card
from quant_personal_decision_b2.fixtures import (
    AFTER_TRIGGER,
    EARLY,
    INITIAL,
    PULLBACK,
    SIGNAL_END,
    FabricatedMarket,
)
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import (
    DEFAULT_POLICY,
    MINUTE,
    Bar,
    D,
    DecisionError,
    encode,
)
from quant_personal_decision_b2.strategy import pivots

SYMBOL = "BTCUSDT"


def system(tmp, family=PULLBACK, direction="LONG", policy=DEFAULT_POLICY, **opts):
    source = FabricatedMarket(tmp / "source.sqlite", family, direction, **opts)
    source.scan(INITIAL)
    adapter = MarketSnapshotAdapter(source.path, "fixture")
    journal = Journal(tmp / "journal.sqlite", create=True, policy=policy)
    return source, Engine(adapter, journal, policy)


def after(source, engine, delay=0, variant="inside", episode=None):
    snapshot = source.scan(AFTER_TRIGGER + delay * MINUTE + (1000 if delay else 0), variant)
    return engine.evaluate(SYMBOL, scan=snapshot["scan_id"], as_of_ms=snapshot["decision_as_of_venue_ms"],
                           reprice_minutes=delay or None, episode_id=episode)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("family", [PULLBACK, EARLY])
def test_both_families_and_directions_from_two_publications(tmp_path, direction, family):
    source, engine = system(tmp_path, family, direction)
    watch = engine.evaluate(SYMBOL)
    assert watch["market_status"] == "WATCH" and watch["watch_near_confirmation"]
    epi = watch["episode"]
    assert epi["direction"] == direction and epi["family"] == family
    assert epi["frozen_at_ms"] < epi["earliest_trigger_open_ms"]
    assert epi["features"] == "B2_EMA_ATR_PIVOT_V1"
    assert epi["obstacles"]["4h"] and epi["obstacles"]["1d"]
    if family == EARLY:
        assert D(epi["feature_diagnostics"]["signal_1h"]["retracement_atr"]) < D("0.85")
    card = after(source, engine)
    assert card["episode"] == watch["episode"]
    assert card["market_status"] == "EXECUTABLE"
    assert card["strategy_evaluated"] and card["data_ready"]
    assert card["trigger"]["open_ms"] == epi["earliest_trigger_open_ms"]
    assert card["trigger"]["end_ms"] == SIGNAL_END + 30 * MINUTE
    assert card["trigger"]["source"]["source_available_venue_ms"] <= card["evaluated_ms"]
    assert len(card["frame_end_ms"]) == 5
    assert card["evidence"] == "SYNTHETIC_QA_ONLY" and card["account_context_status"] == "UNAVAILABLE"
    assert [row["kind"] for row in engine.journal.events()] == [
        "OBSERVATION", "CANDIDATE", "PUBLICATION", "OBSERVATION", "TRIGGER", "PUBLICATION",
    ]
    assert engine.evaluate(SYMBOL) == card
    assert engine.journal.read(as_of_ms=watch["evaluated_ms"], episode_id=card["episode_id"]) == watch


def test_same_quarter_and_forming_bar_never_confirm(tmp_path):
    source, engine = system(tmp_path)
    initial = engine.evaluate(SYMBOL)
    second = source.scan(17 * MINUTE)
    assert second["markets"][SYMBOL]["frames"]["15m"]["context"][-1]["finality"] == "FORMING"
    # First quarter closes above the line before the permissible window.
    frame = second["markets"][SYMBOL]["frames"]["15m"]["completed"][-1]
    assert D(frame["close"]) > D(initial["episode"]["confirmation_line"])
    card = engine.evaluate(SYMBOL)
    assert card["market_status"] == "WATCH"
    assert card["trigger"] is None and card["reasons"] == ["INDEPENDENT_15M_PENDING"]
    assert after(source, engine)["market_status"] == "EXECUTABLE"


def test_wick_and_later_trigger_revision_are_ineligible(tmp_path):
    source, engine = system(tmp_path)
    watch = engine.evaluate(SYMBOL)
    seen = after(source, engine, variant="wick")
    assert seen["market_status"] == "WATCH" and seen["reasons"] == ["WICK_ONLY_BREAKOUT"]
    source.scan(AFTER_TRIGGER + 4 * MINUTE, "inside")
    revised = engine.evaluate(SYMBOL)
    assert revised["reasons"] == ["REVISED_TRIGGER_WITHHELD"]
    assert revised["episode_id"] == watch["episode_id"]
    assert engine.journal.read(card_id=seen["card_id"]) == seen


def test_confirmed_trigger_revision_suspends_current_card_only(tmp_path):
    source, engine = system(tmp_path)
    engine.evaluate(SYMBOL)
    card = after(source, engine)
    latest = after(source, engine, 5, "revision_after", card["episode_id"])
    assert latest["market_status"] == "WATCH" and latest["reasons"] == ["TRIGGER_REVISION_CHANGED"]
    assert latest["trigger"] == card["trigger"]
    assert engine.journal.read(card_id=card["card_id"]) == card


@pytest.mark.parametrize("setup", ["chop", "contradict"])
def test_no_setup_only_when_fully_evaluated(tmp_path, setup):
    _, engine = system(tmp_path, setup=setup)
    data = market_card(engine.adapter.read(SYMBOL))
    assert data["data_ready"] and data["market_status"] == "NOT_EVALUATED"
    assert not data["strategy_evaluated"]
    no_setup = engine.evaluate(SYMBOL)
    assert no_setup["market_status"] == "NO_SETUP" and no_setup["strategy_evaluated"]
    assert no_setup["episode_id"] is None


def test_three_bars_not_evaluated(tmp_path):
    _, engine = system(tmp_path, history=3)
    card = engine.evaluate(SYMBOL)
    assert card["data_ready"] and not card["feature_warmup_ready"]
    assert card["market_status"] == "NOT_EVALUATED" and card["reasons"] == ["FEATURE_WARMUP"]
    assert not card["strategy_evaluated"]


def test_two_simultaneous_families_group_to_single_stable_episode(tmp_path):
    source, engine = system(tmp_path, EARLY, setup="overlap")
    cc = engine.evaluate(SYMBOL)
    assert cc["episode"]["overlap_families"] == [PULLBACK, EARLY]
    assert cc["episode"]["family"] == PULLBACK
    now = after(source, engine)
    assert now["episode_id"] == cc["episode_id"]
    with engine.journal.connect() as db:
        assert db.execute("SELECT count(*) FROM episodes").fetchone()[0] == 1


@pytest.mark.parametrize("variant,status,reason", [
    ("inside", "EXECUTABLE", "MARKET_SIDE_ELIGIBLE_SYNTHETIC"),
    ("chase", "INVALID", "MISSED_NO_CHASE"),
    ("target_hit", "INVALID", "MISSED_NO_CHASE"),
    ("invalid", "INVALID", "STRUCTURAL_INVALIDATION"),
    ("spread", "WATCH", "TP1_AFTER_COST_R_INSUFFICIENT"),
    ("stale", "SOURCE_BLOCKED", "SYMBOL_INPUT_BLOCKED"),
])
def test_action_time_reprice_scenarios(tmp_path, variant, status, reason):
    source, engine = system(tmp_path)
    engine.evaluate(SYMBOL)
    first = after(source, engine)
    current = after(source, engine, 5, variant, first["episode_id"])
    assert current["market_status"] == status and reason in current["reasons"]
    assert current["episode"] == first["episode"]
    assert current["trigger"] == first["trigger"]
    assert current["reprice"]["requested_delay_minutes"] == 5
    later = after(source, engine, 10, "inside", first["episode_id"])
    if status == "INVALID":
        assert later["market_status"] == "INVALID" and later["reasons"] == ["TERMINAL_EPISODE"]
    else:
        assert later["market_status"] == "EXECUTABLE"
    assert later["reprice"]["requested_delay_minutes"] == 10
    assert encode(engine.journal.read(card_id=first["card_id"])) == encode(first)


def test_reprice_expiry_and_early_call(tmp_path):
    policy = replace(DEFAULT_POLICY, expiry_minutes=40, trigger_minutes=35)
    source, engine = system(tmp_path, policy=policy)
    engine.evaluate(SYMBOL)
    first = after(source, engine)
    source.scan(AFTER_TRIGGER + MINUTE)
    with pytest.raises(DecisionError, match="REPRICE_BEFORE_TARGET_TIME"):
        engine.evaluate(SYMBOL, reprice_minutes=5, episode_id=first["episode_id"])
    interim = after(source, engine, 5, "inside", first["episode_id"])
    final = after(source, engine, 10, "inside", first["episode_id"])
    assert interim["market_status"] == "EXECUTABLE"
    assert final["market_status"] == "INVALID" and final["reasons"] == ["EPISODE_EXPIRED"]
    assert final["episode"]["expires_at_ms"] == first["episode"]["expires_at_ms"]


def test_nearby_first_obstacle_refuses_distant_target(tmp_path):
    source, engine = system(tmp_path, setup="tight")
    engine.evaluate(SYMBOL)
    card = after(source, engine)
    assert card["market_status"] == "WATCH"
    assert "FIRST_OBSTACLE_ROOM_INSUFFICIENT" in card["reasons"]
    assert card["plan"]["obstacles"]["first"]["frame"] == "4h"
    assert all(row["price"] is None and row["reason"] == "TARGET_BEYOND_FIRST_OBSTACLE"
               for row in card["plan"]["targets"])


def test_reset_boot_and_historical_terminal_immutability(tmp_path):
    source, engine = system(tmp_path)
    a = engine.evaluate(SYMBOL)
    first = after(source, engine)
    source.boot = "B2-FIXTURE-BOOT-B"
    block = after(source, engine, 5, "invalid", first["episode_id"])
    assert block["market_status"] == "INVALID"
    assert block["evaluation_receipt"]["source_published"]["boot"] == source.boot
    restored = Journal(engine.journal.path)
    assert restored.read(as_of_ms=a["evaluated_ms"]) == a
    assert restored.read() == block
    with pytest.raises(DecisionError, match="BACKDATED_OR_CONFLICTING_EVALUATION"):
        engine.evaluate(SYMBOL, as_of_ms=first["evaluated_ms"] - 1)


def test_pivot_disappears_until_both_right_bars_close():
    sample = tuple(Bar(i * 60, (i + 1) * 60, D(1), D(peak), D(1), D(1), D(2), {"receipt_id": i + 1})
                   for i, peak in enumerate((2, 3, 9, 4, 5)))
    assert not pivots(sample[:-1], highs=True)
    found, = pivots(sample, highs=True)
    assert (found.price, found.candle_end_ms, found.confirmed_ms) == (D(9), 180, 300)


def test_decision_math_stable_under_ambient_decimal_precision(tmp_path):
    source, first_engine = system(tmp_path)
    other = Journal(tmp_path / "other.sqlite", create=True, policy=DEFAULT_POLICY)
    second_engine = Engine(first_engine.adapter, other)
    a = first_engine.evaluate(SYMBOL)
    with localcontext(Context(prec=12)):
        b = second_engine.evaluate(SYMBOL)
    assert a["episode"] == b["episode"]
    source.scan(AFTER_TRIGGER)
    a = first_engine.evaluate(SYMBOL)
    with localcontext(Context(prec=12)):
        b = second_engine.evaluate(SYMBOL)
    assert a["plan"] == b["plan"]
