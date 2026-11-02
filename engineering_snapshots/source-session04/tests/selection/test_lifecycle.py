from dataclasses import replace

import pytest

from btc_quant_agent.platform.core import UserReportedFill, dec
from btc_quant_agent.platform.selection.fixtures import SYMBOLS, monitor
from btc_quant_agent.platform.selection.selector import Policy
from btc_quant_agent.platform.selection.lifecycle import (
    advance,
    place_resting_limit,
    record_user_fill,
    simulated_fill,
)
from btc_quant_agent.platform.selection.sources import MINUTE
from btc_quant_agent.platform.selection.store import Capital


def trigger(store, setup, policy, *, notify=True):
    a = setup.anchors
    store.create_episode(a, a["setup_ts"] + 1000)
    end = 3 if a["strategy"] == "breakout_retest" else 2
    for i in range(1, end + 1):
        e = advance(store, a["id"], monitor(a, i), policy)
    assert e["state"]["status"] == "ARMED" and len(e["state"]["trigger_ids"]) == 2
    if notify:
        store.notify_episode(a["id"], monitor(a, end).now, lambda wire: None)
    return end


def response(store, setup, delay, *, fault=None, price=None, mode="normal"):
    a = setup.anchors
    end = 3 if a["strategy"] == "breakout_retest" else 2
    notice = store.episode(a["id"])["state"]["notification_event"]
    delivered = monitor(a, end).now
    store.delivery(notice, delivered_ts=delivered, acknowledged_ts=delivered + delay * MINUTE)
    for minute in range(end + 1, end + delay):
        advance(store, a["id"], monitor(a, minute), Policy(symbols=SYMBOLS), require_ack=True)
    m = monitor(a, end + delay, fault=fault, price=price, mode=mode)
    q = m.quote
    if q:
        p = q.provenance
        q = replace(
            q,
            provenance=replace(
                p,
                exchange_event_ts=p.exchange_event_ts + 1000,
                received_ts=p.received_ts + 1000,
                available_ts=p.available_ts + 1000,
            ),
        )
    return replace(m, now=m.now + 1000, quote=q)


@pytest.mark.parametrize("delay", [1, 3, 5])
def test_eligible_new_quote_and_no_actual_position(store, setup, corpus, delay):
    p = corpus[0]
    trigger(store, setup, p)
    m = response(store, setup, delay)
    e = advance(store, setup.anchors["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert e["state"]["status"] == "ENTRY_ELIGIBLE", e["state"]["reasons"]
    fill = simulated_fill(store, setup.anchors["id"], m, p)
    assert fill and fill["source"] == "SIMULATED"
    with pytest.raises(KeyError):
        store.position(fill["id"])
    assert simulated_fill(store, setup.anchors["id"], m, p) is None


@pytest.mark.parametrize("delay", [1, 3, 5])
def test_lost_entry_at_response_cancels_irreversibly(store, setup, corpus, delay):
    p, a = corpus[0], setup.anchors
    trigger(store, setup, p)
    m = response(store, setup, delay, price=float(a["chase_cap"]) + 0.1)
    e = advance(store, a["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert e["state"]["status"] == "CANCELLED"
    assert e["state"]["reasons"] == ["CHASE_CAP_EXCEEDED"]
    assert advance(store, a["id"], monitor(a, 10), p) == e


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("stale_quote", "QUOTE"),
        ("invalid_authority", "AUTHORITY"),
        ("high_spread", "SPREAD"),
        ("source_clock", "QUOTE"),
        ("funding_unknown", "FUNDING"),
        ("outage", "SOURCE"),
    ],
)
def test_transient_readiness_revocation_retains_episode(store, setup, corpus, fault, reason):
    p, a = corpus[0], setup.anchors
    trigger(store, setup, p)
    ready = response(store, setup, 1)
    e = advance(store, a["id"], ready, p, require_ack=True, capital=Capital(10000, 10000, ready.now))
    assert e["state"]["status"] == "ENTRY_ELIGIBLE"
    bad = monitor(a, 4, fault=fault)
    e = advance(store, a["id"], bad, p, require_ack=True, capital=Capital(10000, 10000, bad.now))
    # High spread may also cross the cap: raw spread is a veto before any quote-based price cancellation.
    assert e["state"]["status"] == "ARMED", e
    assert any(reason in r for r in e["state"]["reasons"])
    good = monitor(a, 5)
    e = advance(store, a["id"], good, p, require_ack=True, capital=Capital(10000, 10000, good.now))
    if fault == "outage":
        assert store.regime(a["symbol"])["state"] == "UNKNOWN"
        assert e["state"]["status"] == "ARMED" and e["state"]["reasons"] == ["REGIME_REVOKES_READINESS"]
        return
    assert e["state"]["status"] == "ENTRY_ELIGIBLE", e


def test_missing_quote_preserves_watch_then_armed_and_risk(store, setup, corpus):
    p, a = corpus[0], setup.anchors
    store.create_episode(a, a["setup_ts"] + 1000)
    m = monitor(a, 1, quote=False)
    assert advance(store, a["id"], m, p)["state"]["status"] == "WATCH"
    m = monitor(a, 2, quote=False)
    e = advance(store, a["id"], m, p)
    assert e["state"]["status"] == "ARMED" and "MISSING_EXECUTABLE_QUOTE" in e["state"]["reasons"]
    gap = monitor(a, 3, mode="gap", quote=False)
    assert advance(store, a["id"], gap, p)["state"]["reasons"] == ["FROZEN_STRUCTURE_BREACHED"]


def test_elapsed_time_and_repeated_same_bar_never_confirm(store, setup, corpus):
    p, a = corpus[0], setup.anchors
    store.create_episode(a, a["setup_ts"] + 1000)
    m = monitor(a, 1)
    e = advance(store, a["id"], m, p)
    for delta in (1, 10, 100):
        e = advance(store, a["id"], replace(m, now=m.now + delta), p)
    assert len(e["state"]["confirmation_ids"]) == 1 and not e["state"]["trigger_ids"]
    later = replace(m, now=a["expiry"])
    e = advance(store, a["id"], later, p)
    assert e["state"]["status"] == "EXPIRED"


def test_expiry_equality_and_late_user_report_do_not_reopen(store, setup, corpus):
    p, a = corpus[0], setup.anchors
    trigger(store, setup, p)
    m = replace(monitor(a, 15), now=a["expiry"])
    terminal = advance(store, a["id"], m, p)
    assert terminal["state"]["status"] == "EXPIRED"
    fill = UserReportedFill(
        "late",
        "user-position",
        a["symbol"],
        a["side"],
        dec(a["anchor"]),
        dec(1),
        a["expiry"] + 1,
        a["expiry"] + 10,
    )
    pos, evidence = record_user_fill(store, a["id"], fill, m.bar.spec)
    assert pos.source == "USER_REPORTED" and evidence["requires_reconciliation"]
    assert store.episode(a["id"]) == terminal
    below = replace(fill, report_id="gap", position_id="gap-position", price=dec(a["stop"]) - dec(1))
    pos, _ = record_user_fill(store, a["id"], below, m.bar.spec)
    assert pos.status == "STOP_BREACHED"


def test_delivery_is_unknown_until_separate_assumption_and_new_quote(store, setup, corpus):
    p, a = corpus[0], setup.anchors
    trigger(store, setup, p)
    event = store.episode(a["id"])["state"]["notification_event"]
    assert store.get_notification(event)["status"] == "SENDER_ACCEPTED"
    assert store.delivery(event)["delivery"] == "UNKNOWN"
    m = monitor(a, 3)
    e = advance(store, a["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert "ACTUAL_DELIVERY_OR_ACK_UNKNOWN" in e["state"]["reasons"]
    store.delivery(event, delivered_ts=monitor(a, 2).now, acknowledged_ts=m.now)
    e = advance(store, a["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert "NEW_POST_ACK_QUOTE_REQUIRED" in e["state"]["reasons"]


def test_later_strict_quote_cross_positive_limit_fill_and_candle_touch_no_fill(store, resting_setup, corpus):
    p, a = corpus[0], resting_setup.anchors
    trigger(store, resting_setup, p)
    m = response(store, resting_setup, 1)
    e = advance(store, a["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert e["state"]["status"] == "ENTRY_ELIGIBLE", e
    place_resting_limit(store, a["id"], m.now)
    assert simulated_fill(store, a["id"], m, p) is None
    touch = monitor(a, 5, price=float(a["anchor"]) + 0.01)
    touch = replace(
        touch,
        bar=replace(
            touch.bar,
            fields=tuple(
                replace(o, value=float(a["anchor"]) - 0.01) if o.field == "low" else o
                for o in touch.bar.fields
            ),
        ),
    )
    advance(store, a["id"], touch, p, require_ack=True, capital=Capital(10000, 10000, touch.now))
    # Its candle spans the limit, while executable ask remains above it.
    assert float(a["anchor"]) >= dict((o.field, o.value) for o in touch.bar.fields)["low"]
    assert simulated_fill(store, a["id"], touch, p) is None
    cross = monitor(a, 6, price=float(a["anchor"]) - 0.04)
    e = advance(store, a["id"], cross, p, require_ack=True, capital=Capital(10000, 10000, cross.now))
    assert e["state"]["status"] == "ENTRY_ELIGIBLE", e
    fill = simulated_fill(store, a["id"], cross, p)
    assert fill and fill["price"] == a["anchor"] and fill["source"] == "SIMULATED"


def test_bad_source_price_cannot_cancel_good_episode(store, setup, corpus):
    p, a = corpus[0], setup.anchors
    trigger(store, setup, p)
    bad = monitor(a, 3, mode="gap", quote=False)
    bad = replace(bad, bar=replace(bad.bar, fields=tuple(replace(o, symbol="OTHER") for o in bad.bar.fields)))
    e = advance(store, a["id"], bad, p)
    assert e["state"]["status"] == "ARMED"


def test_anchor_mutation_and_terminal_mutation_rejected(store, setup, corpus):
    a = setup.anchors
    store.create_episode(a, a["setup_ts"] + 1000)
    with pytest.raises(ValueError, match="IMMUTABLE_SETUP"):
        store.create_episode({**a, "expiry": a["expiry"] + MINUTE}, a["setup_ts"] + 2000)
    e = advance(store, a["id"], replace(monitor(a, 15), now=a["expiry"]), corpus[0])
    with pytest.raises(ValueError, match="TERMINAL"):
        store.transition(a["id"], e["revision"], {**e["state"], "status": "ARMED"}, a["expiry"] + 1)


def test_frozen_trigger_and_notification_identity_enforced_by_store(store, setup, corpus):
    trigger(store, setup, corpus[0])
    a = setup.anchors
    e = store.episode(a["id"])
    with pytest.raises(ValueError, match="TRIGGER_BAR_IDS_IMMUTABLE"):
        store.transition(
            a["id"], e["revision"], {**e["state"], "trigger_ids": ["rewritten"]}, e["updated_ts"] + 1
        )
    with pytest.raises(ValueError, match="NOTIFICATION_IDENTITY_IMMUTABLE"):
        store.transition(
            a["id"], e["revision"], {**e["state"], "notification_event": "rewritten"}, e["updated_ts"] + 1
        )


def test_late_clock_cannot_mutate_regime_or_create_notification(store, setup, corpus):
    trigger(store, setup, corpus[0])
    a = setup.anchors
    before = store.regime(a["symbol"])
    late = replace(monitor(a, 1), healthy=False)
    with pytest.raises(ValueError, match="TIME_REGRESSION"):
        advance(store, a["id"], late, corpus[0])
    assert store.regime(a["symbol"]) == before
    with pytest.raises(ValueError, match="NOTIFICATION_BEFORE"):
        store.notify_episode(a["id"], late.now, lambda wire: None)


def test_duplicate_user_report_after_close_cannot_reopen(store, setup):
    a = setup.anchors
    store.create_episode(a, a["setup_ts"] + 1000)
    spec = monitor(a, 1).bar.spec
    fill = UserReportedFill(
        "report-open",
        "actual",
        a["symbol"],
        a["side"],
        dec(a["anchor"]),
        dec(1),
        a["setup_ts"] + MINUTE,
        a["setup_ts"] + MINUTE + 1000,
    )
    record_user_fill(store, a["id"], fill, spec)
    close = replace(
        fill,
        report_id="report-close",
        operation="CLOSE",
        user_action_ts=fill.user_action_ts + MINUTE,
        received_ts=fill.received_ts + MINUTE,
    )
    assert record_user_fill(store, a["id"], close, spec)[0].status == "CLOSED"
    assert record_user_fill(store, a["id"], fill, spec)[0].version == 1
    assert store.position("actual").status == "CLOSED" and store.position("actual").version == 2
