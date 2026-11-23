"""Pinned synthetic cases derived from official public endpoint schemas."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from quant_personal_public_b1 import normalize as n
from quant_personal_public_b1.compat import (
    FUNDING_LIMIT,
    funding_payload,
    funding_query,
    oi_payload,
)
from quant_personal_public_b1.policy import (
    DEPTH,
    FUNDING,
    INSTRUMENTS,
    INTERVALS,
    KLINES,
    MARK,
    OI,
    OI_HISTORY,
    PARAMS,
    QUOTE,
    TICKER,
    TIME,
    WEIGHTS_VERSION,
    SourceBlocked,
)
from quant_personal_public_b1.store import sha
from quant_personal_public_b1.wire import Request

PATH = Path(__file__).resolve().parents[1] / "evidence/fixtures/public_endpoints_20261118.json"
PIN = "0a1043ade431e9af6ab6100913889d5f73918b562cfd784c945934f7ecf907ac"
EXAMPLES = json.loads(PATH.read_bytes())


def normalize(route, params, body):
    if route == TIME:
        return n.integer(n.obj(body).get("serverTime"), "serverTime", minimum=1)
    if route == INSTRUMENTS:
        return n.exchange_info(body, ("BTCUSDT",))
    if route == KLINES:
        return n.candles(body, params["interval"], params["startTime"], params["endTime"])
    if route == DEPTH:
        return n.depth(body, params["limit"])
    if route == FUNDING:
        return funding_payload(body, params)
    if route == OI_HISTORY:
        return oi_payload(body, params["symbol"], params["limit"])
    parse = {TICKER: n.ticker, QUOTE: n.quote, OI: n.open_interest, MARK: n.mark}
    return parse[route](body, params["symbol"])


def negative(route, body):
    if route == TIME:
        body["serverTime"] = "not integer"
    elif route == INSTRUMENTS:
        body["symbols"] = {"BTCUSDT": {}}
    elif route == KLINES:
        body[0][6] += 1
    elif route == TICKER:
        body["lastPrice"] = "-1"
    elif route == QUOTE:
        body["askPrice"] = "3.9"
    elif route == DEPTH:
        body["T"] = body["E"] + 1
    elif route == OI:
        body["openInterest"] = "NaN"
    elif route == OI_HISTORY:
        body.insert(1, copy.deepcopy(body[0]))
    elif route == FUNDING:
        body[-1]["fundingTime"] += 9 * 86_400_000
    elif route == MARK:
        body["nextFundingTime"] = body["time"] - 1
    else:
        raise AssertionError(route)
    return body


def test_pinned_examples_exact_endpoint_set_and_provenance():
    assert sha(PATH.read_bytes()) == PIN
    assert EXAMPLES["version"] == WEIGHTS_VERSION and EXAMPLES["venue_requests"] == 0
    assert {item["path"] for item in EXAMPLES["examples"]} == PARAMS.keys()
    assert all(item["official_source"].startswith("https://developers.binance.com/")
               for item in EXAMPLES["examples"])


@pytest.mark.parametrize("item", EXAMPLES["examples"], ids=lambda item: item["path"])
def test_document_derived_examples_validate_and_reject_malformed_each_route(item):
    route, params, body = item["path"], item["query"], item["body"]
    weight, wire = Request(route, params).validate()
    assert weight >= 0 and wire.startswith(b"GET ")
    assert normalize(route, params, body)
    with pytest.raises(SourceBlocked):
        normalize(route, params, negative(route, copy.deepcopy(body)))


def test_funding_documented_200_without_time_accepts_long_response_without_truncation():
    limit = 5
    params = {"symbol": "BTCUSDT", "limit": limit}
    assert Request(FUNDING, params).validate()[0] == 1
    result = [{"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingTime": 1 + i, "markPrice": "1"}
              for i in range(200)]
    latest, normalized = funding_payload(result, params)
    assert latest == 200
    assert len(normalized["rows"]) == 200 and normalized["response_count"] == 200
    assert normalized["query_semantics"] == "DOCUMENTED_MOST_RECENT_200"
    with pytest.raises(SourceBlocked, match="FUNDING_RESPONSE_EXCEEDS_DOCUMENTED_BOUND"):
        funding_payload(result + [result[-1]], params)


def test_funding_bounded_query_accepts_both_inclusive_edges_and_refuses_saturated_window():
    params = funding_query("BTCUSDT", 1_735_689_720_000)
    def engine(t):
        return {"symbol": "BTCUSDT", "fundingRate": "-0.0001", "fundingTime": t, "markPrice": "20"}
    start, end = params["startTime"], params["endTime"]
    assert isinstance(start, int) and isinstance(end, int)
    assert Request(FUNDING, params).validate()[0] == 1
    row_a, row_b = engine(start), engine(end)
    assert funding_payload([row_a, row_b], params)[0] == end
    assert funding_payload([row_a, {**row_a, "fundingRateType": "Special"}, row_b], params)[1]["response_count"] == 3
    with pytest.raises(SourceBlocked, match="HISTORY_DUPLICATE"):
        funding_payload([row_a, row_a], params)
    saturated = [engine(start + i) for i in range(FUNDING_LIMIT)]
    with pytest.raises(SourceBlocked, match="FUNDING_WINDOW_SATURATED"):
        funding_payload(saturated, params)
    with pytest.raises(SourceBlocked, match="FUNDING_OUTSIDE_REQUEST_WINDOW"):
        funding_payload([engine(start - 1)], params)
    with pytest.raises(SourceBlocked, match="FORBIDDEN_QUERY"):
        Request(FUNDING, {"symbol": "BTCUSDT", "limit": 5, "startTime": start}).validate()


def test_open_interest_retention_and_venue_omitted_periods():
    first = 1_735_689_000_000
    example = {"symbol":"BTCUSDT", "sumOpenInterest":"10000.0", "sumOpenInterestValue":"301.01"}
    times = (first, first + 300_000, first + 1_200_000)
    stamp, values = oi_payload([{**example, "timestamp": t, "newVenueField": "preserved in raw"} for t in times],
                               "BTCUSDT", 5)
    assert stamp == times[-1] and len(values["rows"]) == 3
    assert values["omitted_periods"] == [{"after_ms": times[1], "before_ms": times[2], "missing_periods": 2}]
    assert values["documented_retention"] == "LATEST_ONE_MONTH"


@pytest.mark.parametrize("frame", list(INTERVALS))
def test_each_kline_inclusive_close_contract(frame):
    duration = INTERVALS[frame]
    row = [0, "10", "11", "9", "10", "21", duration - 1, "42", 3, "5", "7", "0"]
    assert n.candles([row], frame, 0, 0)[0].end_ms_exclusive == duration
    row[6] = duration
    with pytest.raises(SourceBlocked, match="KLINE_BOUNDARY"):
        n.candles([row], frame, 0, 0)
