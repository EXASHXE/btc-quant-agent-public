from dataclasses import replace

import pytest

from btc_quant_agent.platform.core import Status
from btc_quant_agent.platform.factors import REGISTRY as FACTORS
from btc_quant_agent.platform.strategies import REGISTRY as STRATEGIES
from btc_quant_agent.platform.selection.fixtures import BASE, bar, history, observation
from btc_quant_agent.platform.selection.selector import (
    Policy,
    Setup,
    advance_regime,
    group_confirmations,
    metrics,
    ranks,
    resolve_setups,
    scan,
)
from btc_quant_agent.platform.selection.sources import MINUTE, STRUCTURE, aggregate_five_minutes


def changed_last(corpus, field, mutate):
    policy, bars, h = corpus
    end = h.universe.cutoff
    changed = tuple(
        replace(b, fields=tuple(mutate(o) if o.field == field else o for o in b.fields))
        if b.spec.symbol == "ETHUSDT" and b.end == end
        else b
        for b in bars
    )
    return history(changed, end, policy)


@pytest.mark.parametrize(
    "fault", ["stale", "wrong_provider", "wrong_symbol", "wrong_units", "delayed", "clock"]
)
def test_price_cannot_launder_oi(corpus, fault):
    def mutate(o):
        p = o.provenance
        if fault == "stale":
            p = replace(
                p,
                exchange_event_ts=p.exchange_event_ts - 900_000,
                received_ts=p.received_ts - 900_000,
                available_ts=p.available_ts - 900_000,
            )
        if fault == "wrong_provider":
            p = replace(p, provider="other_provider")
        if fault == "delayed":
            p = replace(p, received_ts=p.exchange_event_ts + 2000, available_ts=p.exchange_event_ts + 3000)
        if fault == "clock":
            p = replace(p, received_ts=p.exchange_event_ts - 1)
        return replace(
            o,
            provenance=p,
            symbol="WRONG" if fault == "wrong_symbol" else o.symbol,
            unit="CONTRACTS" if fault == "wrong_units" else o.unit,
        )

    h = changed_last(corpus, "open_interest", mutate)
    i = len(h.frames["ETHUSDT"]) - 1
    assert h.pipeline.result("ETHUSDT", "OI_CHANGE", i, h.universe.cutoff + 1000).status != Status.OK
    assert h.pipeline.result("ETHUSDT", "EMA", i, h.universe.cutoff + 1000).status == Status.OK
    assert metrics(h, "ETHUSDT")["usable"]
    assert metrics(h, "ETHUSDT")["oi_change"] is None


def test_optional_field_availability_does_not_delay_independent_price_factor(corpus):
    h = changed_last(
        corpus,
        "open_interest",
        lambda o: replace(
            o, provenance=replace(o.provenance, available_ts=o.provenance.exchange_event_ts + 900)
        ),
    )
    i = len(h.frames["ETHUSDT"]) - 1
    now = h.universe.cutoff + 500
    assert h.pipeline.result("ETHUSDT", "EMA", i, now).status == Status.OK
    assert h.pipeline.result("ETHUSDT", "OI_LEVEL", i, now).status == Status.INADMISSIBLE


def test_missing_volume_keeps_price_watch_evidence(corpus):
    policy, bars, h = corpus
    modified = tuple(
        replace(b, fields=tuple(o for o in b.fields if o.field not in {"volume", "quote_volume"}))
        if b.spec.symbol == "ETHUSDT" and b.end == h.universe.cutoff
        else b
        for b in bars
    )
    new = history(modified, h.universe.cutoff, policy)
    i = len(new.frames["ETHUSDT"]) - 1
    assert new.pipeline.result("ETHUSDT", "EMA", i, h.universe.cutoff + 1000).status == Status.OK
    assert new.pipeline.result("ETHUSDT", "RELATIVE_VOLUME", i, h.universe.cutoff + 1000).value is None
    assert metrics(new, "ETHUSDT")["usable"]


def test_wrong_symbol_aggressive_trades_disable_only_cvd(corpus):
    policy, bars, h = corpus
    last = next(b for b in bars if b.spec.symbol == "ETHUSDT" and b.end == h.universe.cutoff)
    trade = observation(last.spec, "cvd", 123, last.end, symbol="BTCUSDT")
    modified = tuple(replace(b, fields=b.fields + (trade,)) if b is last else b for b in bars)
    new = history(modified, h.universe.cutoff, policy)
    i = len(new.frames["ETHUSDT"]) - 1
    assert new.pipeline.result("ETHUSDT", "CVD", i, h.universe.cutoff + 1000).value is None
    assert new.pipeline.result("ETHUSDT", "ATR", i, h.universe.cutoff + 1000).status == Status.OK


@pytest.mark.parametrize("fault", ["future", "missing", "interval", "incomplete"])
def test_frozen_membership_never_shrinks_to_hide_bad_reference(corpus, fault):
    policy, bars, h = corpus
    changed = []
    for b in bars:
        if b.spec.symbol == policy.benchmark and b.end == h.universe.cutoff:
            if fault == "missing":
                continue
            if fault == "future":
                b = replace(
                    b,
                    fields=tuple(
                        replace(
                            o,
                            provenance=replace(
                                o.provenance, received_ts=b.end + 3000, available_ts=b.end + 4000
                            ),
                        )
                        for o in b.fields
                    ),
                )
            elif fault == "interval":
                b = replace(b, interval_ms=MINUTE)
            else:
                b = replace(b, closed=False)
        changed.append(b)
    new = history(tuple(changed), h.universe.cutoff, policy)
    assert len(new.universe.members) == 12 and not new.synchronized()
    r = new.pipeline.result(
        "ETHUSDT", "RELATIVE_STRENGTH", len(new.frames["ETHUSDT"]) - 1, h.universe.cutoff + 1000
    )
    assert r.status == Status.INADMISSIBLE
    assert ranks(new, "LONG", policy)["ETHUSDT"]["opportunity"] is None


def test_structural_aggregation_requires_five_completed_distinct_minutes(corpus):
    _, bars, _ = corpus
    spec = bars[0].spec
    minutes = tuple(bar(spec, BASE + i * MINUTE, 100, 101, 99, 100, interval=MINUTE) for i in range(5))
    combined = aggregate_five_minutes(minutes, BASE + STRUCTURE + 1000)
    assert len(combined) == 1 and combined[0].interval_ms == STRUCTURE
    assert len(combined[0].fields[0].dependencies) == 5
    assert not aggregate_five_minutes(minutes[:-1], BASE + STRUCTURE + 1000)
    assert not aggregate_five_minutes(
        minutes[:-1] + (replace(minutes[-1], closed=False),), BASE + STRUCTURE + 1000
    )
    assert not aggregate_five_minutes(minutes + (minutes[-1],), BASE + STRUCTURE + 1000)


def evidence(**kwargs):
    return {
        "usable": True,
        "adx": 30,
        "T": 0.8,
        "slope": 0.1,
        "ER": 0.5,
        "range_intact": True,
        "z_return": 0.5,
        "oi_change": None,
        "rvol": 1,
        "high_volatility_proxy": False,
        **kwargs,
    }


def test_hysteresis_unknown_source_override_and_restart(store):
    old = store.regime("ETHUSDT")
    first = advance_regime(old, evidence(), 1)
    assert first["state"] == "UNKNOWN"
    store.save_regime("ETHUSDT", first)
    restarted = type(store)(store.db_path)
    second = advance_regime(restarted.regime("ETHUSDT"), evidence(), 2)
    assert second["state"] == "TREND_UP"
    assert advance_regime(second, evidence(), 2) == second
    bad = advance_regime(second, {"usable": False, "reason": "SOURCE_OUTAGE"}, 3)
    assert bad["state"] == "UNKNOWN"
    ambiguity = advance_regime(bad, evidence(adx=21, T=0.3, ER=0.3), 4)
    assert ambiguity["state"] == "UNKNOWN"


def test_regime_checkpoint_cannot_leak_into_a_past_decision(store):
    first = advance_regime(store.regime("BTCUSDT"), evidence(), 1)
    second = advance_regime(first, evidence(), 2)
    store.save_regime("BTCUSDT", second)
    with pytest.raises(ValueError, match="PRECEDES_CHECKPOINT"):
        advance_regime(second, evidence(), 1)
    with pytest.raises(ValueError, match="CHECKPOINT_ADVANCED"):
        store.save_regime("BTCUSDT", first)


@pytest.mark.parametrize(
    "name,m",
    [
        ("TREND_DOWN", evidence(T=-0.8, slope=-0.1)),
        ("RANGE", evidence(adx=15, T=0.1, slope=0, ER=0.1)),
        ("HIGH_VOLATILITY", evidence(high_volatility_proxy=True)),
        ("DELEVERAGING_SHOCK", evidence(z_return=-4, oi_change=-0.05, rvol=3)),
    ],
)
def test_all_regimes_have_explicit_persistable_state(name, m):
    state = advance_regime({"state": "UNKNOWN"}, m, 1)
    state = advance_regime(state, m, 2)
    assert state["state"] == name


def test_duplicate_momentum_indicators_do_not_gain_votes():
    p = Policy()
    one = group_confirmations({"EMA": True}, p)
    three = group_confirmations({"EMA": True, "ADX": True, "MACD_HIST": True}, p)
    assert one["independent_votes"] == three["independent_votes"] == 1
    assert one["score"] == three["score"]


def test_veto_before_opposition_and_no_direction_vote_counting(setup):
    other = Setup({**setup.anchors, "id": "short", "side": "SHORT"}, setup.ranking)
    picked, rejected = resolve_setups([setup, other])
    assert not picked and {r["reasons"][0] for r in rejected} == {"UNRESOLVED_OPPOSING_SETUPS"}
    picked, rejected = resolve_setups([setup, replace(other, vetoes=("STALE_SOURCE",))])
    assert picked == [setup] and rejected[0]["reasons"] == ["STALE_SOURCE"]
    picked, _ = resolve_setups([setup, setup, replace(setup, anchors={**setup.anchors, "id": "clone"})])
    assert len(picked) == 1


def test_metadata_is_preserved_and_not_promoted():
    assert len(FACTORS) == 69 and len(STRATEGIES) == 28
    assert sum(str(s.evidence_tier) == "SYNTHETIC_VALIDATED" for s in STRATEGIES.values()) == 3
    assert str(STRATEGIES["trend_pullback"].evidence_tier) == "IMPLEMENTED_UNTESTED"


def test_scan_uses_frozen_universe_and_actual_regimes(corpus, store):
    policy, bars, h = corpus
    previous = history(bars, h.universe.cutoff - STRUCTURE, policy)
    scan(previous, store, policy)
    result = scan(h, store, policy)
    assert result["regimes"]["ETHUSDT"]["state"] == "TREND_UP"
    assert result["regimes"]["ADAUSDT"]["state"] == "RANGE"
    strategies = {x["anchors"]["strategy"] for x in result["candidates"]}
    assert {"trend_pullback", "breakout_retest", "bollinger_reversion"} <= strategies
    assert result["selected"]
    assert scan(h, store, policy)["selected"] == result["selected"]


def test_unsupported_policy_and_context_weights_do_not_become_trades():
    with pytest.raises(ValueError, match="ONLY_THREE"):
        Policy(enabled=("shock_reversal",))
    with pytest.raises(ValueError, match="INTERVAL"):
        Policy(structural_interval_ms=MINUTE)
    assert group_confirmations({"ATR": True}, Policy())["independent_votes"] == 0
