from dataclasses import replace

import pytest

from btc_quant_agent.platform.bridge.adapters import PublicPayloadAdapter
from btc_quant_agent.platform.bridge.admission import compile_snapshot
from btc_quant_agent.platform.bridge.contracts import PublicSource, Receipt, ActivationDenied
from btc_quant_agent.platform.bridge.fixtures import OfflineFixtureProvider
from btc_quant_agent.platform.core import Status, dec


@pytest.mark.parametrize("provider", ["binance", "okx"])
def test_provider_payloads_normalize_units_clocks_and_all_factor_dependencies(config, provider):
    c = config.model_copy(update={"provider": provider})
    batch = OfflineFixtureProvider(c).snapshot(50)
    snapshot = PublicPayloadAdapter(provider, "PERPETUAL", 60).normalize(batch, c.platform.universe)
    a = compile_snapshot(snapshot, c)
    assert set(a.events) == set(c.platform.universe)
    for symbol, event in a.events.items():
        assert not a.admission[symbol].reasons
        assert event.spec.provider == provider and event.quote.bid < event.quote.ask
        assert event.candle.available_at_ms == event.provenance.available_ts
        assert event.provenance.received_ts > event.candle.close_time_ms
        assert event.derivatives.oi_unit == "BASE" and event.derivatives.open_interest > 0
        assert (
            event.derivatives.field_clock("funding_rate").source_id
            != event.derivatives.field_clock("open_interest").source_id
        )
        for id in ("EMA", "ADX", "FUNDING", "OI_CHANGE", "SPOT_PERP_RETURN"):
            assert a.pipeline.result(symbol, id, a.indices[symbol], batch.decision_ts).status == Status.OK, id
        for id in ("CVD", "ORDERBOOK_IMBALANCE", "DEPTH_CHANGE"):
            r = a.pipeline.result(symbol, id, a.indices[symbol], batch.decision_ts)
            assert r.status == Status.MISSING and r.value is None
        if provider == "okx":
            assert event.spec.multiplier == dec(".01")


@pytest.mark.parametrize(
    "scenario,reason", [("stale_quote", "STALE"), ("clock_error", "SOURCE_CLOCK_ORDER_INVALID")]
)
def test_quote_faults_do_not_relabel_a_closed_candle_as_executable(config, scenario, reason):
    b = OfflineFixtureProvider(config, scenario).snapshot(50)
    s = PublicPayloadAdapter("binance", "PERPETUAL", 60).normalize(b, config.platform.universe)
    if scenario == "clock_error":
        assert all(x.quote is None and any(reason in issue for issue in x.issues) for x in s.symbols)
    else:
        assert all(reason in x.quote.reason(x.instrument.spec, b.decision_ts) for x in s.symbols)


def test_missing_event_or_receive_time_is_unknown_not_synthesized(config):
    batch = OfflineFixtureProvider(config).snapshot(50)
    r = next(r for r in batch.receipts if r.channel == "quote")
    d = r.payload
    d.pop("time")
    no_time = Receipt.make(
        r.provider, r.channel, r.instrument_id, r.received_ts, r.available_ts, d, exposure="SYNTHETIC"
    )
    adapter = PublicPayloadAdapter("binance", "PERPETUAL", 60)
    record = adapter.instrument(
        next(x for x in batch.receipts if x.channel == "instrument"), config.platform.universe[0]
    )
    with pytest.raises(ValueError, match="EVENT_TIME_UNKNOWN"):
        adapter.quote(no_time, record)
    with pytest.raises(ValueError, match="RECEIVER_OR_AVAILABILITY_TIME_UNKNOWN"):
        adapter.quote(replace(r, received_ts=None), record)


def test_derivative_failure_does_not_crash_price_analysis_or_impute_zero(config):
    b = OfflineFixtureProvider(config, "derivative_failure").snapshot(50)
    s = PublicPayloadAdapter("binance", "PERPETUAL", 60).normalize(b, config.platform.universe)
    a = compile_snapshot(s, config)
    for symbol in a.events:
        for id in ("FUNDING", "OI_LEVEL", "OI_CHANGE", "LIQUIDATION_SHOCK"):
            result = a.pipeline.result(symbol, id, a.indices[symbol], b.decision_ts)
            assert result.value is None and result.status == Status.MISSING
        assert a.pipeline.result(symbol, "EMA", a.indices[symbol], b.decision_ts).value is not None
        assert "FUNDING_MISSING_OR_STALE" in a.admission[symbol].reasons


def test_individual_field_availability_cannot_be_laundered_by_fresh_funding(config):
    b = OfflineFixtureProvider(config).snapshot(50)
    receipts = []
    for r in b.receipts:
        if r.channel == "open_interest":
            r = replace(r, available_ts=b.decision_ts + 1)
        receipts.append(r)
    a = compile_snapshot(
        PublicPayloadAdapter("binance", "PERPETUAL", 60).normalize(
            replace(b, receipts=tuple(receipts)), config.platform.universe
        ),
        config,
    )
    symbol = config.platform.benchmark
    assert a.pipeline.result(symbol, "FUNDING", a.indices[symbol], b.decision_ts).value is not None
    assert a.pipeline.result(symbol, "OI_LEVEL", a.indices[symbol], b.decision_ts).value is None


def test_zero_open_interest_is_an_observation_and_inverse_contract_is_rejected(config):
    b = OfflineFixtureProvider(config).snapshot(50)
    adapter = PublicPayloadAdapter("binance", "PERPETUAL", 60)
    meta = next(r for r in b.receipts if r.channel == "instrument")
    record = adapter.instrument(meta, "BTCUSDT")
    r = next(r for r in b.receipts if r.channel == "open_interest")
    d = r.payload
    d["openInterest"] = "0"
    zero = Receipt.make(
        r.provider, r.channel, r.instrument_id, r.received_ts, r.available_ts, d, exposure="SYNTHETIC"
    )
    assert adapter.fields(zero, record)[0].value == 0
    d = meta.payload
    d["marginAsset"] = "BTC"
    with pytest.raises(ValueError, match="INVERSE"):
        adapter.instrument(
            Receipt.make(
                meta.provider,
                meta.channel,
                meta.instrument_id,
                meta.received_ts,
                meta.available_ts,
                d,
                exposure="SYNTHETIC",
            ),
            "BTCUSDT",
        )


def test_payload_admitted_flag_is_not_authority_and_live_transport_is_blocked(config):
    b = OfflineFixtureProvider(config).snapshot(50)
    receipts = tuple(replace(r, exposure="CALLER_SUPPLIED_UNVERIFIED") for r in b.receipts)
    s = PublicPayloadAdapter("binance", "PERPETUAL", 60).normalize(
        replace(b, receipts=receipts, fixture_id=None), config.platform.universe
    )
    a = compile_snapshot(s, config)
    assert not a.events
    with pytest.raises(ActivationDenied, match="SEPARATE_ACCESS_AUTHORIZATION"):
        PublicSource("binance").snapshot(50)


def test_unknown_funding_cadence_and_bad_quote_precision_are_explicit_vetoes(config, tmp_path):
    from btc_quant_agent.platform.bridge.runtime import BridgeStore, ReadOnlyScanner

    source = OfflineFixtureProvider(config)
    scanner = ReadOnlyScanner(config, BridgeStore(tmp_path / "cadence.sqlite"))

    def batch(bar):
        b = source.snapshot(bar)
        receipts = []
        for r in b.receipts:
            if r.channel == "instrument":
                payload = r.payload
                payload.pop("fundingIntervalHours")
                r = Receipt.make(
                    r.provider,
                    r.channel,
                    r.instrument_id,
                    r.received_ts,
                    r.available_ts,
                    payload,
                    exposure="SYNTHETIC",
                )
            receipts.append(r)
        return replace(b, receipts=tuple(receipts))

    scanner.scan(batch(50))
    r = scanner.scan(batch(51))
    row = next(x for x in r["records"] if x["symbol"] == "BTCUSDT")
    assert "FUNDING_INTERVAL_UNKNOWN" in row["veto_reasons"] and row["plan"]["risk"] is None
    b = source.snapshot(50)
    quote = next(x for x in b.receipts if x.channel == "quote")
    payload = quote.payload
    payload["bidPrice"] = str(dec(payload["bidPrice"]) + dec(".001"))
    bad = Receipt.make(
        quote.provider,
        quote.channel,
        quote.instrument_id,
        quote.received_ts,
        quote.available_ts,
        payload,
        exposure="SYNTHETIC",
    )
    s = PublicPayloadAdapter("binance", "PERPETUAL", 60).normalize(
        replace(b, receipts=tuple(bad if x.id == quote.id else x for x in b.receipts)),
        config.platform.universe,
    )
    assert s.symbols[0].quote.reason(s.symbols[0].instrument.spec, b.decision_ts) == "QUOTE_TICK_INVALID"
