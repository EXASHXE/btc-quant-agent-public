from dataclasses import replace
import json
import pytest

from btc_quant_agent.platform.canary.public_data import normalize, bar_from_record
from btc_quant_agent.platform.canary.public_policy import START, END
from btc_quant_agent.platform.canary.public_runtime import run_public, terminal_qualification
from .fixtures import Clock, Backend, wire, record, quote, candle, meta_payload


def metadata(t=START + 100, exposure="SYNTHETIC"):
    return wire("binance_usdm_exchange_info", meta_payload(), t, exposure=exposure)


def test_native_shape_quote_has_separate_event_transaction_and_clock_bounds(scope):
    q = quote(START + 1000)
    r = normalize(record(scope, q, metadata()))
    assert r["status"] == "ADMITTED_OBSERVATION", r
    assert r["quote"]["provenance"]["exposure"] == "SYNTHETIC"
    assert r["clock"]["event_to_receive_estimate_bounds_ms"] == [19, 41] or r["clock"][
        "event_to_receive_estimate_bounds_ms"
    ] == (19, 41)
    assert r["native_transaction_ms"] != r["clock"]["native_event_or_snapshot_ms"]
    assert not r["clock"]["one_way_latency_proven"]
    assert "unverified" in r["native_sizes"]["unit"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_event",
        "future",
        "stale",
        "wrong_symbol",
        "coin_m",
        "invalid_tick",
        "bad_update",
        "bad_transaction",
        "no_clock",
        "metadata_future",
        "nonfinite",
    ],
)
def test_invalid_native_quote_blocked(scope, fault):
    q = quote(START + 10000)
    body = q.payload
    data = body["data"]
    m = metadata()
    use_clock = True
    if fault == "missing_event":
        data.pop("E")
    elif fault == "future":
        data["E"] += 100000
        data["T"] += 100000
    elif fault == "stale":
        data["E"] -= 6000
        data["T"] -= 6000
    elif fault == "wrong_symbol":
        data["s"] = "ETHUSDT"
    elif fault == "coin_m":
        data["st"] = 2
    elif fault == "invalid_tick":
        data["b"] = "100.001"
    elif fault == "bad_update":
        data["u"] = None
    elif fault == "bad_transaction":
        data["T"] = data["E"] + 1
    elif fault == "no_clock":
        use_clock = False
    elif fault == "metadata_future":
        m = metadata(START + 20000)
    else:
        data["b"] = "NaN"
    q = replace(q, payload_text=json.dumps(body))
    r = normalize(record(scope, q, m, clock=use_clock))
    assert r["quote"] is None and r["reasons"], r


@pytest.mark.parametrize("closed", [True, False])
def test_closed_candle_never_creates_quote(scope, closed):
    c = candle(START, closed=closed)
    r = normalize(record(scope, c, metadata()))
    assert r["quote"] is None
    if closed:
        assert len(r["bars"]) == 1, r
        b = bar_from_record(r["bars"][0])
        assert b.interval_ms == 60000
        assert b.fields[0].provenance.available_ts == c.available_wall
    else:
        assert r["status"] == "INCOMPLETE_BAR_IGNORED"


def test_funding_unknown_time_and_missing_cadence_never_substitute_default(scope):
    t = START + 10000
    m = metadata()
    w = wire(
        "binance_usdm_premium",
        {
            "symbol": "BTCUSDT",
            "time": t,
            "markPrice": "100",
            "indexPrice": "100",
            "lastFundingRate": "0.001",
            "nextFundingTime": t + 3600000,
        },
        t,
        "BTCUSDT",
    )
    r = normalize(record(scope, w, m))
    assert r["status"] == "WATCH_CONTEXT_ONLY"
    assert "NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN" in r["reasons"] and not r["fields"]
    w = wire("binance_usdm_funding_info", [], t)
    r = normalize(record(scope, w, m))
    assert r["cadence_hours"] == {} and any("ABSENCE" in s for s in r["reasons"])


def test_short_finite_run_closes_every_socket_and_replays_fabricated_receipts(scope, tmp_path):
    clock = Clock(END - 6000)
    backend = Backend(scope, clock)
    r = run_public(scope, enabled=True, clock=clock, backend=backend, output=tmp_path / "run")
    assert r["exposure"] == "SYNTHETIC" and r["native_market_requests"] == 0
    assert r["sockets_closed"] and r["receiver_threads_stopped"] and backend.closed
    assert all(c.closed for c in backend.connections)
    assert r["replay"]["status"] == "PARITY_VERIFIED", r
    assert r["stopped_wall_ms"] <= END + 50, r
    assert r["authorized_end_exclusive_ms"] == END and r["late_start_ms"] > 0
    assert not r["source_qualified"] and not r["shadow_advisory_qualified"]
    assert (tmp_path / "run/report.html").is_file()


@pytest.mark.parametrize("status,expected", [(403, "VENUE_ACCESS_DENIED"), (429, "RATE_LIMIT")])
def test_finite_run_stops_on_bootstrap_denial_and_keeps_real_response_shape(
    scope, tmp_path, status, expected
):
    clock = Clock()
    backend = Backend(scope, clock, {"exchangeInfo": (status, {"msg": "denied"})})
    r = run_public(scope, enabled=True, clock=clock, backend=backend, output=tmp_path / "run")
    assert expected in r["stop_reason"]
    assert r["replay"]["checked_pairs"] == 1
    assert r["sockets_closed"] and len([u for u, p in backend.calls if "fapi.binance.com" in u]) == 1


def test_semantic_availability_not_backdated_to_receive(scope):
    q = quote(START + 10000)
    r = record(scope, q, metadata())
    r["normalization_available_wall_ms"] = q.receive_wall + 1000
    r["normalization_available_mono_ms"] = q.receive_mono + 1000
    r["decision_wall_ms"] = q.receive_wall + 1100
    r["decision_mono_ms"] = q.receive_mono + 1100
    n = normalize(r)
    assert n["quote"]["provenance"]["available_ts"] == q.receive_wall + 1000
    assert n["quote"]["provenance"]["available_ts"] > q.available_wall


def test_bad_optional_volume_keeps_valid_price_fields(scope):
    c = candle(
        START, values={"open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 1000, "quote_volume": 1}
    )
    n = normalize(record(scope, c, metadata()))
    assert n["bars"] and n["volume_unit_qualification"] == "UNVERIFIED"
    fields = {o["field"] for o in n["bars"][0]["fields"]}
    assert {"open", "high", "low", "close"} <= fields and "volume" not in fields
    assert not n["quote"]


@pytest.mark.parametrize("fault", ["venue", "clock", "storage", "replay", "shutdown", "pending", "synthetic"])
def test_good_recent_cache_cannot_override_failed_terminal_evidence(fault):
    reason = {
        "venue": "VENUE_ACCESS_DENIED",
        "clock": "CLOCK_SYNC_UNVERIFIED",
        "storage": "STORAGE_BLOCKED",
    }.get(fault, "AUTHORIZED_UTC_END")
    result = terminal_qualification(
        {"source_qualified": True, "shadow_advisory_qualified": True},
        {"status": "INCOMPLETE" if fault == "replay" else "PARITY_VERIFIED"},
        reason,
        [],
        "SYNTHETIC" if fault == "synthetic" else "PUBLIC_CANARY",
        fault != "shutdown",
        int(fault == "pending"),
    )
    assert not result["source_qualified"] and not result["shadow_advisory_qualified"]
    assert not result["economically_validated"]
