import json
from dataclasses import replace
import pytest
from btc_quant_agent.platform.canary.admission import admit, bind_instrument, decode
from btc_quant_agent.platform.canary.clocks import NativeClock, Probe, estimate_clock, qualify_clock
from btc_quant_agent.platform.canary.fixtures import bbo, candle_frame, capture, clock_for, metadata
from btc_quant_agent.platform.canary.runtime import monitor_from_admitted
from btc_quant_agent.platform.selection.sources import FrozenUniverse, SourceHistory, STRUCTURE


def receive(f, catalog, binding, policy, store):
    return admit(f, catalog[f.endpoint_id], binding, policy, clock_for(f.capture), store)


@pytest.mark.parametrize(
    "fault",
    [
        "missing_timestamp",
        "wrong_symbol",
        "wrong_market",
        "wrong_provider",
        "wrong_host",
        "wrong_units",
        "invalid_tick",
        "stale",
        "future",
        "wall_jump",
        "sync_failure",
        "timeout",
        "disconnect",
        "429",
        "418",
    ],
)
def test_quote_fault_never_actionable(fault, catalog, binding, policy, store):
    f = bbo(catalog["binance_usdm_bbo_ws"], "BTCUSDT", policy.synthetic_start_ms + 1000, fault=fault)
    r = receive(f, catalog, binding[1], policy, store)
    assert not r["action_source_ready"] and r["reasons"] and r["status"] == "WATCH"
    assert not r.get("decoded") or r["decoded"].quote is None
    assert not r["native_source_qualified"]


def test_native_event_transaction_and_elapsed_distinct(catalog, binding, policy, store):
    e = catalog["binance_usdm_bbo_ws"]
    for i in range(2):
        f = bbo(e, "BTCUSDT", policy.synthetic_start_ms + 1000 + i * 1000, sequence=100 + i * 50)
        r = receive(f, catalog, binding[1], policy, store)
    assert r["action_source_ready"]
    clock = r["decoded"].clock_report
    assert clock["native"].transaction_ms != clock["native"].value_ms
    assert clock["elapsed"]["measurement"] == "measured_local_elapsed"
    assert not clock["one_way_latency_proven"]
    assert clock["event_to_receive_estimate_bounds_ms"] == (19, 41)


def test_duplicate_and_out_of_order_cannot_renew(catalog, binding, policy, store):
    e = catalog["binance_usdm_bbo_ws"]
    f = bbo(e, "BTCUSDT", policy.synthetic_start_ms + 1000, sequence=90)
    receive(f, catalog, binding[1], policy, store)
    prior = store.source(e.id, f.symbol)
    r = receive(
        replace(f, capture=capture(policy.synthetic_start_ms + 2000)), catalog, binding[1], policy, store
    )
    assert r["reasons"] == ["DUPLICATE_DISCARDED"]
    assert store.source(e.id, f.symbol)["last_receive_ms"] == prior["last_receive_ms"]
    r = receive(
        bbo(e, f.symbol, policy.synthetic_start_ms + 2100, sequence=80), catalog, binding[1], policy, store
    )
    assert r["reasons"] == ["OUT_OF_ORDER_DISCARDED"]


def test_equivocation_downgrades(catalog, binding, policy, store):
    e = catalog["binance_usdm_bbo_ws"]
    t = policy.synthetic_start_ms + 1000
    receive(bbo(e, "BTCUSDT", t), catalog, binding[1], policy, store)
    r = receive(bbo(e, "BTCUSDT", t, bid="99.99"), catalog, binding[1], policy, store)
    assert r["reasons"] == ["SOURCE_EQUIVOCATION"]
    assert store.source(e.id, "BTCUSDT")["status"] == "DEGRADED"


def test_reconnect_requires_new_fragment(catalog, binding, policy, store):
    e = catalog["binance_usdm_bbo_ws"]
    t = policy.synthetic_start_ms + 1000
    state = store.reconnect(e.id, "BTCUSDT", t)
    with pytest.raises(ValueError, match="INSUFFICIENT"):
        store.recover_quote_fragment(e.id, "BTCUSDT")
    for i in range(2):
        r = receive(
            bbo(e, "BTCUSDT", t + 100 + 100 * i, sequence=i + 1, epoch=state["epoch"]),
            catalog,
            binding[1],
            policy,
            store,
        )
        assert not r["action_source_ready"]
    recovered = store.recover_quote_fragment(e.id, "BTCUSDT")
    assert recovered["status"] == "OFFLINE_STABLE" and not recovered["earlier_fragment_continuity"]


def test_contract_change_needs_fresh_metadata(catalog, binding, policy, store):
    e = catalog["binance_usdm_bbo_ws"]
    t = policy.synthetic_start_ms + 1000
    receive(bbo(e, "BTCUSDT", t), catalog, binding[1], policy, store)
    mf, new = metadata(catalog["binance_usdm_exchange_info"], "BTCUSDT", t + 200, tick="0.1")
    r = receive(bbo(e, "BTCUSDT", t + 1000, sequence=2, ask="100.10"), catalog, new, policy, store)
    assert r["reasons"] == ["CONTRACT_CHANGE_REVALIDATION_REQUIRED"]
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRED"):
        store.revalidate_contract(e.id, "BTCUSDT", new.hash, "missing", t + 1000)
    store.set_value(
        "instrument:review",
        dict(
            instrument_hash=new.hash,
            symbol="BTCUSDT",
            provider="binance",
            available_ms=mf.capture.available_wall_ms,
        ),
    )
    store.revalidate_contract(e.id, "BTCUSDT", new.hash, "review", t + 1000)
    assert store.source(e.id, "BTCUSDT")["status"] == "RECOVERING"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"offset_low_ms": -501, "offset_high_ms": 501}, "EXCEEDS_LEASE"),
        ({"available_mono_ms": 0}, "ESTIMATE_STALE"),
        ({"rtt_ms": ()}, "INVALID_OR_FUTURE"),
        ({"offset_low_ms": float("nan")}, "INVALID_OR_FUTURE"),
    ],
)
def test_clock_fail_closed(change, reason, policy):
    c = capture(policy.synthetic_start_ms + 1000)
    native = NativeClock("E", c.request_wall_ms + 20, "EVENT_TIME", "official-doc")
    assert reason in qualify_clock(native, c, replace(clock_for(c), **change), 5000)["reason"]


def test_clock_offset_cannot_make_unknown_native(policy):
    c = capture(policy.synthetic_start_ms + 1000)
    for native in (
        NativeClock(None, None, "UNKNOWN", ""),
        NativeClock("time", c.request_wall_ms, "UNKNOWN", "doc"),
    ):
        assert (
            qualify_clock(native, c, clock_for(c), 5000)["reason"] == "NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN"
        )


def test_probe_jitter_and_wall_drift(policy):
    t = policy.synthetic_start_ms
    p = Probe(t, t + 20, 1000, 1020, t + 10)
    wide = replace(p, receive_wall_ms=t + 80, receive_mono_ms=1080)
    assert estimate_clock((p, wide)).uncertainty_ms > estimate_clock((p,)).uncertainty_ms
    with pytest.raises(ValueError, match="DRIFT"):
        estimate_clock((replace(p, receive_wall_ms=t + 1000),))


def test_stale_oi_does_not_poison_fresh_price(catalog, binding, policy, store):
    e = catalog["binance_usdm_oi"]
    t = policy.synthetic_start_ms + 300_100
    f = bbo(catalog["binance_usdm_bbo_ws"], "BTCUSDT", t)
    oi = replace(
        f,
        endpoint_id=e.id,
        host=e.host,
        payload_json=json.dumps(dict(symbol="BTCUSDT", time=t - 150_000, openInterest="1000")),
        native_units=(("open_interest", "BASE"),),
    )
    assert not receive(oi, catalog, binding[1], policy, store)["action_source_ready"]
    price = candle_frame(
        catalog["binance_usdm_klines_rest"], binding[1], policy.synthetic_start_ms, interval=STRUCTURE
    )
    r = receive(price, catalog, binding[1], policy, store)
    assert len(r["decoded"].bars) == 1 and r["decoded"].quote is None
    assert not r["decoded"].bars[0].values(price.capture.decision_wall_ms)[1]
    premium = catalog["binance_usdm_premium"]
    funding = replace(
        oi,
        endpoint_id=premium.id,
        payload_json=json.dumps(
            dict(symbol="BTCUSDT", time=t, lastFundingRate="0.0001", nextFundingTime=t + 10000)
        ),
    )
    result = receive(funding, catalog, binding[1], policy, store)
    assert "NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN" in result["reasons"]


def test_bar_gap_repair_keeps_actual_late_availability(catalog, binding, policy, store):
    e = catalog["binance_usdm_klines_rest"]
    t = policy.synthetic_start_ms
    receive(candle_frame(e, binding[1], t), catalog, binding[1], policy, store)
    receive(candle_frame(e, binding[1], t + 120_000), catalog, binding[1], policy, store)
    with pytest.raises(ValueError, match="MISSING"):
        store.repair_bar_gap(e.id + ":60000", "BTCUSDT")
    r = receive(
        candle_frame(e, binding[1], t + 60_000, end_receive_ms=t + 180_100),
        catalog,
        binding[1],
        policy,
        store,
    )
    store.repair_bar_gap(e.id + ":60000", "BTCUSDT")
    h = SourceHistory(
        r["decoded"].bars, FrozenUniverse(("BTCUSDT",), "BTCUSDT", t + 120_000, decision_ts=t + 180_200)
    )
    assert h.frames["BTCUSDT"].empty


@pytest.mark.parametrize("case", ["unclosed", "interval", "future_metadata", "metadata_host"])
def test_schema_metadata_failures(case, catalog, binding, policy, store):
    e = catalog["binance_usdm_klines_ws"]
    f = candle_frame(e, binding[1], policy.synthetic_start_ms, closed=case != "unclosed")
    if case == "interval":
        body = f.payload
        body["k"]["i"] = "3m"
        f = replace(f, payload_json=json.dumps(body))
    if case == "metadata_host":
        with pytest.raises(ValueError, match="UNQUALIFIED"):
            bind_instrument(replace(binding[0], host="https://dapi.binance.com"), "BTCUSDT")
        return
    b = binding[1]
    if case == "future_metadata":
        b = metadata(catalog["binance_usdm_exchange_info"], "BTCUSDT", f.capture.decision_wall_ms + 100)[1]
    r = receive(f, catalog, b, policy, store)
    assert r["reasons"] and not r["action_source_ready"]


def test_monitor_uses_no_vetoed_quote_or_fake_funding(catalog, binding, policy, store):
    e = catalog["binance_usdm_bbo_ws"]
    result = receive(bbo(e, "BTCUSDT", policy.synthetic_start_ms + 1000), catalog, binding[1], policy, store)
    f = candle_frame(catalog["binance_usdm_klines_rest"], binding[1], policy.synthetic_start_ms)
    bar = decode(f, catalog[f.endpoint_id], binding[1], policy, clock_for(f.capture)).bars[0]
    m = monitor_from_admitted(bar, None, result, bar.end + 1000)
    assert m.quote is None and m.funding is None and m.funding_cadence_ms is None


def test_one_and_five_minute_streams_have_independent_cursors(catalog, binding, policy, store):
    e = catalog["binance_usdm_klines_rest"]
    start = policy.synthetic_start_ms
    a = receive(candle_frame(e, binding[1], start + 240_000), catalog, binding[1], policy, store)
    b = receive(candle_frame(e, binding[1], start, interval=STRUCTURE), catalog, binding[1], policy, store)
    assert not a["reasons"] and not b["reasons"]
    assert store.source(e.id + ":60000", "BTCUSDT")["last_sequence"] == start + 240_000
    assert store.source(e.id + ":300000", "BTCUSDT")["last_sequence"] == start


def test_second_gap_cannot_erase_first_unrepaired_gap(catalog, binding, policy, store):
    e = catalog["binance_usdm_klines_rest"]
    t = policy.synthetic_start_ms
    for i in (0, 2, 4):
        receive(candle_frame(e, binding[1], t + i * 60_000), catalog, binding[1], policy, store)
    feed = e.id + ":60000"
    receive(
        candle_frame(e, binding[1], t + 3 * 60_000, end_receive_ms=t + 310_000),
        catalog,
        binding[1],
        policy,
        store,
    )
    with pytest.raises(ValueError, match="MISSING"):
        store.repair_bar_gap(feed, "BTCUSDT")
    receive(
        candle_frame(e, binding[1], t + 60_000, end_receive_ms=t + 320_000),
        catalog,
        binding[1],
        policy,
        store,
    )
    assert not store.repair_bar_gap(feed, "BTCUSDT")["gap"]
