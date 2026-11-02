import json
from dataclasses import replace

import pytest

from btc_quant_agent.platform.core import DerivativeSnapshot, TradeObservation, UserReportedFill, dec
from btc_quant_agent.platform.data import frame
from btc_quant_agent.platform.selection.evaluation import evaluate
from btc_quant_agent.platform.selection.fixtures import market_event, monitor
from btc_quant_agent.platform.selection.lifecycle import advance
from btc_quant_agent.platform.selection.sources import (
    FrozenUniverse,
    SourceHistory,
    aggregate_five_minutes,
    from_bridge_snapshot,
)
from btc_quant_agent.platform.selection.store import Capital
from test_lifecycle import response, trigger


@pytest.mark.parametrize("fault", ["symbol", "provider", "stale", "partial_tape"])
def test_actual_trade_observation_identity_in_shared_frame(setup, fault):
    event = market_event(monitor(setup.anchors, 1))
    p = event.provenance
    good = TradeObservation(event.spec.symbol, dec(100), dec(2), "BUY", p)
    bad = good
    if fault == "symbol" or fault == "partial_tape":
        bad = replace(bad, symbol="OTHER")
    if fault == "provider":
        bad = replace(bad, provenance=replace(p, provider="OTHER"))
    if fault == "stale":
        bad = replace(
            bad,
            provenance=replace(
                p,
                exchange_event_ts=p.exchange_event_ts - 120000,
                received_ts=p.received_ts - 120000,
                available_ts=p.available_ts - 120000,
            ),
        )
    event = replace(event, trades=(good, bad) if fault == "partial_tape" else (bad,))
    df = frame([event], event.decision_ts)
    assert "aggressive_delta" not in df and len(df) == 1


def test_shared_history_retains_historical_oi_without_refreshing_stale_current_oi(setup):
    events = []
    for minute in range(1, 7):
        event = market_event(monitor(setup.anchors, minute))
        events.append(
            replace(event, derivatives=DerivativeSnapshot(event.provenance, open_interest=1000 + minute))
        )
    now = events[-1].decision_ts
    events = [replace(event, decision_ts=now) for event in events]
    # A common replay decision time does not make previously fresh historical rows stale.
    values = frame(events, now)
    assert list(values.open_interest) == list(range(1001, 1007))
    old = events[-1].provenance
    stale = replace(
        old,
        exchange_event_ts=old.exchange_event_ts - 900000,
        received_ts=old.received_ts - 900000,
        available_ts=old.available_ts - 900000,
    )
    events[-1] = replace(events[-1], derivatives=DerivativeSnapshot(stale, open_interest=999))
    values = frame(events, now)
    assert values.open_interest.iloc[-1] != values.open_interest.iloc[-1]  # Explicit missing NaN, never zero.
    assert values.close.notna().all() and values.open_interest.iloc[-2] == 1005


def test_prior_user_position_cannot_be_ignored_for_new_capacity(store, setup, corpus):
    a, p = setup.anchors, corpus[0]
    trigger(store, setup, p)
    m = response(store, setup, 1)
    spec = replace(m.bar.spec, symbol="OTHERUSDT")
    fill = UserReportedFill(
        "unbound-fill", "old", "OTHERUSDT", "LONG", dec(100), dec(100), a["setup_ts"] + 1, a["setup_ts"] + 2
    )
    store.report(fill, spec, stop=dec(90))
    e = advance(store, a["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert e["state"]["status"] == "ARMED"
    assert e["state"]["reasons"] == ["EXISTING_POSITION_VALUATION_OR_BETA_UNKNOWN"]


@pytest.mark.parametrize("fault", ["beta", "beta_stale", "cadence_provenance", "next_time_provenance"])
def test_incomplete_essential_risk_evidence_blocks_action(store, setup, corpus, fault):
    p, a = corpus[0], setup.anchors
    trigger(store, setup, p)
    m = response(store, setup, 1)
    if fault == "beta":
        m = replace(m, beta=None)
    if fault == "beta_stale":
        m = replace(m, beta_available_ts=m.now - 600001)
    if fault == "cadence_provenance":
        m = replace(m, cadence_evidence=None)
    if fault == "next_time_provenance":
        m = replace(m, next_funding_evidence=None)
    e = advance(store, a["id"], m, p, require_ack=True, capital=Capital(10000, 10000, m.now))
    assert e["state"]["status"] == "ARMED" and e["state"]["reasons"]


def test_episode_history_is_immutable_and_gaps_do_not_count_as_confirmation(store, setup, corpus):
    a, p = setup.anchors, corpus[0]
    store.create_episode(a, a["setup_ts"] + 1000)
    m = monitor(a, 1)
    advance(store, a["id"], m, p)
    with pytest.raises(ValueError, match="IMMUTABLE_MONITOR"):
        advance(store, a["id"], replace(m, bar=replace(m.bar, closed=False), now=m.now + 1), p)
    e = advance(store, a["id"], monitor(a, 3), p)
    assert e["state"]["status"] == "CANCELLED" and e["state"]["reasons"] == ["UNOBSERVED_ENTRY_PATH"]


def test_bridge_contract_requires_explicit_identity_binding(corpus):
    from btc_quant_agent.platform.bridge.contracts import (
        CandleRecord,
        FieldObservation,
        InstrumentRecord,
        NormalizedSnapshot,
        NormalizedSymbol,
    )

    p, _, _ = corpus
    # Use existing adapter output contracts, preserving original clocks and source IDs.
    from btc_quant_agent.platform.selection.selector import make_setup, ranks

    h = corpus[2]
    setup = make_setup(h, "ETHUSDT", "trend_pullback", "TREND_UP", p, ranks(h, "LONG", p)["ETHUSDT"])
    m = monitor(setup.anchors, 1)
    event = market_event(m)
    field = FieldObservation("open_interest", 1000, "BASE", event.provenance)
    instrument = InstrumentRecord(
        event.spec, event.spec.symbol, True, m.now - 50, m.now - 20, "fake", "SYNTHETIC"
    )
    symbol = NormalizedSymbol(
        event.spec.symbol,
        instrument,
        (CandleRecord(event.candle, event.provenance),),
        event.quote,
        (field,),
        (),
    )
    snapshot = NormalizedSnapshot(
        "fake", event.spec.provider, m.now, "SYNTHETIC", "fixture", (symbol,), ("fake",)
    )
    bars = from_bridge_snapshot(snapshot, field_bindings={})
    assert "open_interest" not in {o.field for o in bars[0].fields}
    bars = from_bridge_snapshot(snapshot, field_bindings={event.provenance.source_id: ("WRONG", 60000)})
    assert bars[0].values(m.now)[1]["open_interest"] == "FIELD_SYMBOL_MISMATCH"
    with pytest.raises(ValueError, match="BLOCKED_PENDING_OWNER_AUTH"):
        from_bridge_snapshot(replace(snapshot, exposure="FORWARD"), field_bindings={})


@pytest.mark.parametrize("provider", ["binance", "okx"])
def test_actual_reused_provider_decoder_to_completed_feature_history(provider):
    from btc_quant_agent.platform.bridge.adapters import PublicPayloadAdapter
    from btc_quant_agent.platform.bridge.config import load
    from btc_quant_agent.platform.bridge.fixtures import OfflineFixtureProvider

    config = load("configs/bridge/offline.yaml").model_copy(update={"provider": provider})
    batch = OfflineFixtureProvider(config).snapshot(95)
    snapshot = PublicPayloadAdapter(provider, "PERPETUAL", 60).normalize(batch, config.platform.universe)
    bindings = {o.provenance.source_id: (s.symbol, 60000) for s in snapshot.symbols for o in s.observations}
    minute_bars = from_bridge_snapshot(snapshot, field_bindings=bindings)
    assert minute_bars and all(b.interval_ms == 60000 for b in minute_bars)
    five = aggregate_five_minutes(minute_bars, snapshot.decision_ts)
    assert five
    members = tuple(sorted(s.symbol for s in snapshot.symbols))
    end = max(b.end for b in five)
    h = SourceHistory(five, FrozenUniverse(members, members[0], end, decision_ts=snapshot.decision_ts))
    for symbol in members:
        result = h.pipeline.result(symbol, "EMA", len(h.frames[symbol]) - 1, snapshot.decision_ts)
        assert str(result.status) == "OK"


def test_complete_episode_evaluation_and_matched_comparison(corpus, tmp_path):
    report = evaluate(corpus[0], tmp_path / "evaluation")
    assert report["transport_attempts"] == 0 and report["threshold_fitting_runs"] == 0
    assert report["funnel"]["discovered"] == 26
    assert report["funnel"]["modeled_fill"] + report["funnel"]["NO_FILL"] == 26
    standard = [
        r
        for r in report["runs"]
        if r["delay_minutes"] in (1, 3, 5) and not r["fault"] and "lost-" not in r["database"]
    ]
    assert len(standard) == 9 and all(r["fill"] for r in standard)
    assert {r["strategy"] for r in standard} == {"trend_pullback", "breakout_retest", "bollinger_reversion"}
    assert all(r["management"]["funding_status"].startswith("NO_SETTLEMENT") for r in standard)
    assert all(r["occupied_risk"] == 0 for r in standard)
    assert report["selector_comparison"]["cost_hash"]
    failure_slates = report["selector_comparison"]["controlled_failure_slates"]
    assert failure_slates[0]["previous_ids"] and not failure_slates[0]["v1_ids"]
    assert not failure_slates[1]["previous_ids"] and failure_slates[1]["v1_ids"]
    assert report["entry_filter_comparison"] and report["exit_management_comparison"]
    assert json.loads((tmp_path / "evaluation/episodes.json").read_text())["source"] == "OFFLINE_SYNTHETIC"
    assert "OFFLINE SYNTHETIC" in (tmp_path / "evaluation/episodes.html").read_text()


def test_cli_resume_does_not_replay_a_past_snapshot_into_future_state(tmp_path, capsys):
    from btc_quant_agent.platform.cli import main
    from btc_quant_agent.platform.selection.store import SelectorStore

    args = ["selector", "scan", "--config", "configs/selector/v1.yaml", "--output", str(tmp_path / "scan")]
    main(args)
    first = json.loads(capsys.readouterr().out)
    main(args)
    second = json.loads(capsys.readouterr().out)
    assert first == second
    store = SelectorStore(tmp_path / "scan/scan.sqlite")
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM selector_episodes").fetchone()[0] == 3
