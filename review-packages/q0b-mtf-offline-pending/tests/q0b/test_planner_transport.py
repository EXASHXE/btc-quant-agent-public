from dataclasses import replace

import pytest

from q0b.examples import SETUP_END, snapshot
from q0b.planner import (LIMIT, MAX_NEW_BARS, OVERLAP_BARS, REQUEST_BUDGET, RESERVE_FRACTION,
                         WEIGHT_BUDGET, OfflineCollector, OfflineStub, Request, plan_collection)
from q0b.schema import HOUR, INTERVALS, MINUTE
from q0b.source import SourceError, SourceLedger
from q0b.transport import decode_fixture


@pytest.mark.parametrize("count,requests,weight", [(3, 20, 23), (10, 62, 72), (50, 302, 352)])
def test_predeclared_multisymbol_budget(count, requests, weight):
    symbols = [f"COIN{i:02}USDT" for i in range(count)]
    p = plan_collection(SETUP_END+5_000, symbols)
    d = p.to_dict()
    assert not p.source_veto
    assert d["request_count"] == requests
    assert d["request_weight"] == weight
    assert requests <= REQUEST_BUDGET * (1-RESERVE_FRACTION)
    assert weight <= WEIGHT_BUDGET * (1-RESERVE_FRACTION)
    assert p.universe == tuple(sorted(symbols))
    assert d["universe_denominator"] == count
    assert all(r.params["endTime"] < p.asof_ms and r.params["limit"] == LIMIT
               for r in p.requests if r.interval)


def test_incremental_bounds_overlap_and_no_open_bar_requests():
    asof = SETUP_END + HOUR + 5_000
    watermarks = {("BTCUSDT", i): SETUP_END for i in INTERVALS}
    p = plan_collection(asof, ["BTCUSDT"], watermarks)
    bars = [r for r in p.requests if r.interval]
    assert {r.interval for r in bars} == {"1H", "15m", "5m"}
    for r in bars:
        step = INTERVALS[r.interval]
        assert r.params["startTime"] == SETUP_END - OVERLAP_BARS * step
        assert (r.params["endTime"]+1-r.params["startTime"]) // step <= MAX_NEW_BARS+OVERLAP_BARS
        assert r.params["endTime"] < asof


def test_catchup_excess_is_quarantined_not_silently_truncated():
    p = plan_collection(SETUP_END+5_000, watermarks={("BTCUSDT", "15m"): SETUP_END-40*15*MINUTE})
    assert p.quarantine["BTCUSDT"] == "BOUNDED_CATCHUP_EXCEEDED_NO_SILENT_TRUNCATION"
    assert p.to_dict()["universe_denominator"] == 3
    assert not any(r.symbol == "BTCUSDT" for r in p.requests)
    assert any(r.symbol == "ETHUSDT" for r in p.requests)


@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError, OSError])
def test_individual_failure_quarantine_retains_denominator(failure):
    p = plan_collection(SETUP_END+5_000)
    responses = {r.identity: {"synthetic": True} for r in p.requests}
    failing = next(r for r in p.requests if r.symbol == "BTCUSDT")
    responses[failing.identity] = failure("synthetic failure")
    transport = OfflineStub(responses)
    result = OfflineCollector(transport).collect(p)
    assert result["quarantine"] == {"BTCUSDT": failure.__name__}
    assert result["universe_denominator"] == 3
    assert result["responses"]["BTCUSDT"] == []
    assert result["responses"]["ETHUSDT"]
    assert result["source_veto"] is None
    assert result["network_calls"] == 0
    assert len(transport.calls) < len(p.requests)


def test_global_endpoint_failure_vetoes_all_symbols():
    p = plan_collection(SETUP_END+5_000)
    responses = {r.identity: {} for r in p.requests}
    responses[p.requests[0].identity] = TimeoutError("no exchange time proof")
    transport = OfflineStub(responses)
    result = OfflineCollector(transport).collect(p)
    assert result["source_veto"] == "GLOBAL_ENDPOINT_FAILURE:TimeoutError"
    assert not any(result["responses"].values())
    assert len(transport.calls) == 1


def test_explicit_global_source_veto_never_invokes_transport():
    p = plan_collection(SETUP_END+5_000, overall_source_veto=True)
    transport = OfflineStub({})
    assert OfflineCollector(transport).collect(p)["source_veto"] == "OVERALL_SOURCE_VETO"
    assert transport.calls == []


def test_all_quarantined_is_global_veto():
    p = plan_collection(SETUP_END+5_000, quarantined={s: "GAP" for s in
                                                   ("BTCUSDT", "ETHUSDT", "SOLUSDT")})
    assert p.source_veto == "ALL_SYMBOLS_QUARANTINED"
    assert p.requests == ()


def test_protected_collection_window_is_excluded_without_transport():
    p = plan_collection(1_770_000_000_000)
    assert p.source_veto == "ALL_SYMBOLS_QUARANTINED"
    assert p.requests == ()


@pytest.mark.parametrize("symbols", [["BTCUSDT", "BTCUSDT"], [], [f"T{i}USDT" for i in range(51)]])
def test_invalid_universe_not_silently_changed(symbols):
    with pytest.raises(ValueError):
        plan_collection(SETUP_END+5_000, symbols)


def test_universe_order_is_deterministic():
    assert plan_collection(SETUP_END+5_000, ["ETHUSDT", "BTCUSDT"]).to_dict() == plan_collection(
        SETUP_END+5_000, ["BTCUSDT", "ETHUSDT"]).to_dict()


def test_transport_rejects_any_nonstub_implementation():
    with pytest.raises(TypeError, match="OFFLINE_STUB_ONLY"):
        OfflineCollector(object())


def test_wire_bar_decoder_and_admission_are_separate():
    s = snapshot()
    original = s.batches[2]
    request = Request("/fapi/v1/klines", {"symbol": s.symbol, "interval": "1h",
                      "startTime": original.requested_start_ms, "endTime": original.requested_end_ms-1,
                      "limit": LIMIT}, s.symbol, "1H")
    wire = [[b.open_ms, str(b.open), str(b.high), str(b.low), str(b.close), str(b.volume),
             b.exchange_close_ms, "0", 1, "0", "0", "0"] for b in original.bars]
    decoded, receipt = decode_fixture(request, wire, received_ms=s.asof_ms-100,
                                      available_ms=s.asof_ms, exchange_lower_ms=s.asof_ms-200)
    assert receipt["request_id"] == request.identity
    assert len(receipt["response_sha256"]) == 64
    assert receipt["live_time_authority"] is False
    groups = list(s.batches)
    groups[2] = decoded
    assert SourceLedger().admit(replace(s, batches=tuple(groups)))["1H"]
    # Decoder cannot promote incomplete wire rows to closed source evidence.
    wire[-1][6] += HOUR
    bad, _ = decode_fixture(request, wire, received_ms=s.asof_ms-100,
                            available_ms=s.asof_ms, exchange_lower_ms=s.asof_ms-200)
    groups[2] = bad
    with pytest.raises(SourceError):
        SourceLedger().admit(replace(s, batches=tuple(groups)))


def test_quote_wire_identity_cannot_cross_symbols():
    request = Request("/fapi/v1/ticker/bookTicker", {"symbol": "BTCUSDT"}, "BTCUSDT")
    wire = {"symbol": "ETHUSDT", "bidPrice": "100", "askPrice": "101", "bidQty": "10",
            "askQty": "10", "time": SETUP_END}
    with pytest.raises(ValueError, match="QUOTE_WIRE_SCHEMA_OR_IDENTITY"):
        decode_fixture(request, wire, received_ms=SETUP_END+100, available_ms=SETUP_END+200,
                       exchange_lower_ms=SETUP_END)
