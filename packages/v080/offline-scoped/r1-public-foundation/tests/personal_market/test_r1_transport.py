import json
import ssl
from dataclasses import replace

import pytest

from btc_quant_agent.platform.personal_mvp.public_market import Policy, Scanner
from btc_quant_agent.platform.personal_mvp.public_market.adapter import PublicAdapter, Reply
from btc_quant_agent.platform.personal_mvp.public_market.fixture import FixtureClock, FixtureTransport, fixture_reply
from btc_quant_agent.platform.personal_mvp.public_market.policy import (
    DEPTH, FUNDING, INSTRUMENTS, KLINES, OI_HISTORY, QUOTE, RPI, TIME, TRADES, SourceBlocked, request_weight,
)


@pytest.fixture
def adapter():
    clock = FixtureClock()
    transport = FixtureTransport(clock)
    audit = []
    public = PublicAdapter(transport, clock, Policy())
    return public, transport, clock, audit


def open_session(adapter):
    public, _, clock, audit = adapter
    return public.session(clock.sample(), lambda *args: audit.append(args) or len(audit))


@pytest.mark.parametrize("method,route,params,reason", [
    ("POST", TIME, {}, "FORBIDDEN_ROUTE"),
    ("PUT", TIME, {}, "FORBIDDEN_ROUTE"),
    ("DELETE", TIME, {}, "FORBIDDEN_ROUTE"),
    ("get", TIME, {}, "FORBIDDEN_ROUTE"),
    ("GET", "/fapi/v3/account", {}, "FORBIDDEN_ROUTE"),
    ("GET", "/fapi/v1/order", {}, "FORBIDDEN_ROUTE"),
    ("GET", "/fapi/v1/time/", {}, "FORBIDDEN_ROUTE"),
    ("GET", "https://fapi.binance.com/fapi/v1/time", {}, "FORBIDDEN_ROUTE"),
    ("GET", RPI, {"symbol": "BTCUSDT", "limit": 1000}, "FORBIDDEN_ROUTE"),
    ("GET", TRADES, {"symbol": "BTCUSDT"}, "FORBIDDEN_ROUTE"),
    ("GET", TIME, {"apiKey": "fabricated"}, "FORBIDDEN_QUERY"),
    ("GET", TIME, {"X-MBX-APIKEY": "fabricated"}, "FORBIDDEN_QUERY"),
    ("GET", TIME, {"signature": "fabricated", "timestamp": 1}, "FORBIDDEN_QUERY"),
    ("GET", TIME, {"recvWindow": 5000}, "FORBIDDEN_QUERY"),
    ("GET", QUOTE, {}, "FORBIDDEN_QUERY"),
    ("GET", QUOTE, {"symbol": "DOGEUSDT"}, "FORBIDDEN_SYMBOL"),
    ("GET", DEPTH, {"symbol": "BTCUSDT", "limit": 6}, "FORBIDDEN_DEPTH_LIMIT"),
    ("GET", OI_HISTORY, {"symbol": "BTCUSDT", "period": "1m", "limit": 5}, "FORBIDDEN_OI_PERIOD"),
    ("GET", KLINES, {"symbol": "BTCUSDT", "interval": "1m", "startTime": 0, "endTime": 0, "limit": 1},
     "FORBIDDEN_INTERVAL"),
    ("GET", KLINES, {"symbol": "BTCUSDT", "interval": "5m", "startTime": 0, "endTime": 1, "limit": 1},
     "FORBIDDEN_KLINE_WINDOW"),
])
def test_allowlist_before_transport(adapter, method, route, params, reason):
    with pytest.raises(SourceBlocked, match=reason):
        open_session(adapter).get(method, route, params)
    assert not adapter[1].calls
    assert not adapter[3]


@pytest.mark.parametrize("limit,cost", [(5, 2), (10, 2), (20, 2), (50, 2), (100, 5), (500, 10), (1000, 20)])
def test_depth_weights(limit, cost):
    assert request_weight("GET", DEPTH, {"symbol": "BTCUSDT", "limit": limit}) == cost


@pytest.mark.parametrize("limit,cost", [(99, 1), (100, 2), (499, 2), (500, 5), (1000, 5), (1001, 10), (1500, 10)])
def test_kline_weights(limit, cost):
    assert request_weight("GET", KLINES, {
        "symbol": "BTCUSDT", "interval": "5m", "startTime": 0, "endTime": 0, "limit": limit,
    }) == cost


def test_bookticker_bad_header_cannot_reduce_or_raise_used_weight(adapter):
    public, transport, clock, _ = adapter
    public.limits.configure({("REQUEST_WEIGHT", 60_000): 10}, clock.monotonic_ms)

    def mutate(route, _, value):
        used = {TIME: "7", QUOTE: "0"}
        return fixture_reply(value, headers={"X-MBX-USED-WEIGHT-1M": used.get(route, "0")})

    transport.mutate = mutate
    session = open_session(adapter)
    session.get("GET", TIME, {})
    session.get("GET", QUOTE, {"symbol": "BTCUSDT"})
    session.get("GET", TIME, {})
    assert session.weight == 4  # The trusted high header, plus local charges, reached the venue cap of ten.
    with pytest.raises(SourceBlocked, match="VENUE_WEIGHT_LIMIT"):
        session.get("GET", TIME, {})
    assert len(transport.calls) == 3
    clock.advance(60_020)
    transport.mutate = lambda route, params, value: fixture_reply(value, headers={"X-MBX-USED-WEIGHT-1M": "9999"})
    session = open_session(adapter)
    session.get("GET", QUOTE, {"symbol": "BTCUSDT"})
    session.get("GET", QUOTE, {"symbol": "BTCUSDT"})
    assert session.weight == 4


def test_exchange_info_dynamic_limits_and_local_budget(tmp_path):
    clock = FixtureClock()

    def mutate(route, _, value):
        if route == INSTRUMENTS:
            value["rateLimits"] = [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE",
                                    "intervalNum": 1, "limit": 2}]
        return value

    fixture = FixtureTransport(clock, mutate=mutate)
    outcome = Scanner(tmp_path / "ceiling.sqlite", fixture, clock).scan(("BTCUSDT",))
    assert outcome["issue"]["code"] == "VENUE_WEIGHT_LIMIT"
    assert len(fixture.calls) == 2
    fixture.mutate = None
    bounded = Scanner(tmp_path / "local.sqlite", fixture, clock, replace(Policy(), max_requests=3))
    assert bounded.scan(("BTCUSDT",))["issue"]["code"] == "LOCAL_SCAN_BUDGET"


def test_raw_requests_and_zero_weight_oihistory(adapter):
    public, transport, clock, _ = adapter
    public.limits.configure({("RAW_REQUESTS", 60_000): 1}, clock.monotonic_ms)
    session = open_session(adapter)
    params = {"symbol": "BTCUSDT", "period": "5m", "limit": 5}
    session.get("GET", OI_HISTORY, params)
    assert session.weight == 0
    with pytest.raises(SourceBlocked, match="VENUE_REQUEST_LIMIT"):
        session.get("GET", OI_HISTORY, params)
    assert len(transport.calls) == 1


def test_shared_funding_quota_cannot_be_bypassed_by_low_weight(adapter):
    public, _, clock, _ = adapter
    public.limits.configure({("REQUEST_WEIGHT", 60_000): 10000}, clock.monotonic_ms)
    for _ in range(500):
        public.limits.charge(FUNDING, 1, clock.monotonic_ms)
    with pytest.raises(SourceBlocked, match="ENDPOINT_REQUEST_LIMIT"):
        open_session(adapter).get("GET", FUNDING, {"symbol": "BTCUSDT", "limit": 5})


@pytest.mark.parametrize("status", [418, 403, 451])
def test_permanent_http_block_for_adapter_session(adapter, status):
    adapter[1].mutate = lambda *_: fixture_reply({}, status=status)
    with pytest.raises(SourceBlocked, match=f"HTTP_{status}"):
        open_session(adapter).get("GET", TIME, {})
    with pytest.raises(SourceBlocked, match=f"HTTP_{status}"):
        open_session(adapter).get("GET", TIME, {})
    assert len(adapter[1].calls) == 1


@pytest.mark.parametrize("status", [400, 503])
def test_region_restriction_in_payload_is_never_retried(adapter, status):
    adapter[1].mutate = lambda *_: fixture_reply({"msg": "Service unavailable from a restricted location"},
                                                   status=status)
    with pytest.raises(SourceBlocked, match="VENUE_RESTRICTED"):
        open_session(adapter).get("GET", TIME, {})
    assert len(adapter[1].calls) == 1


@pytest.mark.parametrize("headers,delay", [
    ({"Retry-After": "5"}, 5000),
    ({"Retry-After": "Sun, 06 Nov 1994 08:49:42 GMT", "Date": "Sun, 06 Nov 1994 08:49:37 GMT"}, 6000),
    ({"Retry-After": "bad"}, 60_000),
])
def test_retry_after_blocks_until_expiry(adapter, headers, delay):
    _, transport, clock, _ = adapter
    transport.mutate = lambda *_: fixture_reply({}, status=429, headers=headers)
    with pytest.raises(SourceBlocked, match="HTTP_429"):
        open_session(adapter).get("GET", TIME, {})
    clock.advance(delay - 1)
    with pytest.raises(SourceBlocked, match="RETRY_AFTER_ACTIVE"):
        open_session(adapter).get("GET", TIME, {})
    assert len(transport.calls) == 1
    clock.advance(1)
    transport.mutate = None
    assert open_session(adapter).get("GET", TIME, {}).body
    assert len(transport.calls) == 2


@pytest.mark.parametrize("kind", ["timeout", "502"])
@pytest.mark.parametrize("recover", [True, False])
def test_one_bounded_retry_charged_for_each_attempt(adapter, kind, recover):
    _, transport, _, audit = adapter

    def mutate(_, __, value):
        if len(transport.calls) == 2 and recover:
            return value
        if kind == "timeout":
            raise TimeoutError()
        return fixture_reply({}, status=502)

    transport.mutate = mutate
    session = open_session(adapter)
    if recover:
        assert session.get("GET", TIME, {}).body
    else:
        with pytest.raises(SourceBlocked, match="TRANSIENT_TRANSPORT_FAILURE|HTTP_502"):
            session.get("GET", TIME, {})
    assert session.count == session.weight == len(audit) == len(transport.calls) == 2


@pytest.mark.parametrize("tls", ["untrusted certificate", "hostname mismatch"])
def test_tls_failure_is_fail_closed_without_retry(adapter, tls):
    def mutate(*_):
        raise ssl.SSLCertVerificationError(tls)

    _, transport, _, audit = adapter
    transport.mutate = mutate
    with pytest.raises(SourceBlocked, match="TLS_VERIFICATION_FAILED"):
        open_session(adapter).get("GET", TIME, {})
    with pytest.raises(SourceBlocked, match="TLS_VERIFICATION_FAILED"):
        open_session(adapter).get("GET", TIME, {})
    assert len(transport.calls) == 1
    assert audit[0][-1] == "TLS_VERIFICATION_FAILED"


@pytest.mark.parametrize("raw,reason", [(b"{not_json}", "MALFORMED_JSON"), (b'{"x":1,"x":2}', "DUPLICATE_JSON_KEY"),
                                          (b'{"x":Infinity}', "NONFINITE_JSON_NUMBER"),
                                          (b'{"x":1e10000}', "JSON_NUMBER_RANGE")])
def test_malformed_json_is_not_retried(adapter, raw, reason):
    adapter[1].mutate = lambda *_: Reply(200, {}, raw)
    with pytest.raises(SourceBlocked, match=reason):
        open_session(adapter).get("GET", TIME, {})
    assert len(adapter[1].calls) == 1


def test_malformed_schema_is_not_retried(tmp_path):
    clock = FixtureClock()
    fixture = FixtureTransport(clock, mutate=lambda *_: json.loads('{"serverTime":"not-an-int"}'))
    blocked = Scanner(tmp_path / "bad.sqlite", fixture, clock).scan(("BTCUSDT",))
    assert blocked["issue"]["code"] == "INVALID_INTEGER"
    assert len(fixture.calls) == 1


def test_transport_auth_interface_absent(adapter):
    with pytest.raises(TypeError):
        adapter[1].get(TIME, {}, 1, signer=object())
    assert not adapter[1].calls


def test_elapsed_scan_budget_limits_timeout_and_new_dispatch(tmp_path):
    clock = FixtureClock()
    transport = FixtureTransport(clock)
    config = replace(Policy(), scan_timeout_ms=25, request_timeout_ms=100)
    scan = Scanner(tmp_path / "deadline.sqlite", transport, clock, config).scan(("BTCUSDT",))
    assert scan["issue"]["code"] == "REQUEST_DEADLINE"
    assert [timeout for _, _, timeout in transport.calls] == [25, 15, 5]
