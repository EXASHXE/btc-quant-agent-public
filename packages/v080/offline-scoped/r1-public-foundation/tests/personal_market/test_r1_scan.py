import base64
import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from btc_quant_agent.platform.live.models import POLICY as STRICT_POLICY
from btc_quant_agent.platform.personal_mvp.public_market import Cache, Policy, Scanner, SystemClock
from btc_quant_agent.platform.personal_mvp.public_market.fixture import FixtureClock, FixtureTransport
from btc_quant_agent.platform.personal_mvp.public_market.policy import (
    DEPTH, FUNDING, INSTRUMENTS, INTERVALS, KLINES, MARK, OI_HISTORY, QUOTE, SYMBOLS, TIME,
)
from btc_quant_agent.platform.qualified_source import NativeQuarantineRecord
from program_c.integrity import ContractError, digest
from program_c.protocol import load_protocol
from program_c.validation import C_SCHEMA, validate_c


@pytest.fixture
def setup_scan(tmp_path):
    clock = FixtureClock()
    transport = FixtureTransport(clock)
    return tmp_path / "test.sqlite", clock, transport


def only_btc(setup, mutate=None, policy=Policy()):
    path, clock, transport = setup
    transport.mutate = mutate
    return Scanner(path, transport, clock, policy).scan(("BTCUSDT",))


def count_bars(path):
    with Cache(path).connect() as db:
        return db.execute("SELECT COUNT(*) FROM candles").fetchone()[0]


def test_full_incremental_scan_all_symbols_preserve_provenance(setup_scan):
    path, clock, transport = setup_scan
    first = Scanner(path, transport, clock).scan()
    assert first["account_context_status"] == "UNAVAILABLE"
    assert "protective orders" in first["human_actionability"]
    assert first["market_setup_status"] == "NO_SETUP"
    assert first["evidence_class"] == "PERSONAL_PUBLIC_MARKET"
    assert first["data_origin"] == "DETERMINISTIC_OFFLINE_FIXTURE"
    assert first["data_ready"]
    assert set(first["markets"]) == SYMBOLS
    assert first["request_attempts"] == 39  # 3 clock/metadata calls + 12 calls per instrument.
    total_kline_rows = sum(p["limit"] for route, p, _ in transport.calls if route == KLINES)
    assert total_kline_rows == 60
    assert count_bars(path) == 45
    for symbol, market in first["markets"].items():
        assert market["market_setup_status"] == "NO_SETUP"
        assert first["interval_order"] == list(INTERVALS)
        assert set(market["series"]) == INTERVALS.keys()
        for interval, width in INTERVALS.items():
            series = market["series"][interval]
            assert series["status"] == "CURRENT"
            assert len(series["completed"]) == 3
            for bar in series["completed"]:
                assert bar["finality"] == "COMPLETE"
                assert bar["source_publication"] == "UNKNOWN"
                assert bar["end_ms_exclusive"] == bar["close_ms_inclusive"] + 1 == bar["open_ms"] + width
                assert bar["observed_at_wall_ms"] != bar["end_ms_exclusive"]
            assert [bar["finality"] for bar in series["context"]] == ["FORMING"]
        context = market["context"]
        assert {v["status"] for k, v in context.items() if k != "rpi_depth"} == {"CURRENT"}
        assert context["instrument"]["values"]["symbol"] == symbol
        assert context["instrument"]["source_event_ms"] is None
        assert context["instrument"]["values"]["filters"]["LOT_SIZE"]["stepSize"] == "0.001"
        assert context["ticker"]["values"]["lastPrice"]
        assert context["depth"]["values"]["capped_side"] is True
        assert context["depth"]["values"]["execution_guaranteed"] is False
        assert context["depth"]["values"]["rpi_included"] is False
        assert context["book_ticker"]["values"]["spread"] == "0.02"
        assert context["open_interest"]["values"]["openInterest"] == "10001.123"
        assert context["open_interest_history"]["values"]["rows"][-1]["sumOpenInterestValue"] == "999999.01"
        assert context["funding_history"]["values"]["rows"][-1]["fundingRate"] == "-0.00001"
        assert context["mark_funding"]["values"]["lastFundingRate"] == "0.00001"
        assert context["mark_funding"]["values"]["markPrice"] != context["mark_funding"]["values"]["indexPrice"]
        assert context["rpi_depth"] == {"status": "DISABLED", "values": None}
    first_btc = first["markets"]["BTCUSDT"]
    cache = Cache(path)
    assert cache.load_snapshot(1) == first
    receipts = cache.load_receipts(1)
    for seq, receipt in enumerate(receipts, 1):
        assert receipt["sequence"] == seq
        assert receipt["method"] == "GET"
        assert receipt["http_status"] == 200
        assert receipt["request"]["mono_ms"] <= receipt["receive"]["mono_ms"]
        assert receipt["raw_complete"]
        assert hashlib.sha256(base64.b64decode(receipt["raw_base64"])).hexdigest() == receipt["raw_sha256"]
    assert {item["endpoint"] for item in receipts} == {route for route, _, _ in transport.calls}
    clock.advance(300_000)
    transport.calls.clear()
    second = Scanner(path, transport, clock).scan()
    assert cache.load_snapshot(2) == second
    assert cache.load_snapshot(1) == first
    assert second["data_ready"]
    assert sum(p["limit"] for route, p, _ in transport.calls if route == KLINES) < total_kline_rows
    assert count_bars(path) == 48
    second_btc = second["markets"]["BTCUSDT"]
    assert second_btc["series"]["1h"]["completed"] == first_btc["series"]["1h"]["completed"]
    assert second_btc["context"]["ticker"]["values"]["lastPrice"] != first_btc["context"]["ticker"]["values"]["lastPrice"]
    bar = second_btc["series"]["5m"]["completed"][-1]
    assert bar["open_ms"] == first_btc["series"]["5m"]["context"][-1]["open_ms"]
    assert bar["receipt"]["scan_id"] == 2  # A completed observation must be obtained again after closure.


def test_repeated_scan_deduplicates_and_is_deterministic(setup_scan, tmp_path):
    path, clock, transport = setup_scan
    scanner = Scanner(path, transport, clock)
    first = scanner.scan()
    other_clock = FixtureClock()
    other = Scanner(tmp_path / "replay.sqlite", FixtureTransport(other_clock), other_clock).scan()
    assert other == first
    for _ in range(2):
        assert scanner.scan()["data_ready"]
    assert count_bars(path) == 45


def test_forming_and_grace_boundary(setup_scan):
    path, _, _ = setup_scan
    boundary = (FixtureClock().venue_ms // INTERVALS["15m"] + 1) * INTERVALS["15m"]
    clock = FixtureClock(boundary + 500)
    scanner = Scanner(path, FixtureTransport(clock), clock)
    first = scanner.scan(("BTCUSDT",))
    for interval in ("15m", "5m"):
        series = first["markets"]["BTCUSDT"]["series"][interval]
        assert series["latest_completed_end_ms"] < boundary
        assert [bar["finality"] for bar in series["context"]] == ["CLOSE_UNCONFIRMED", "FORMING"]
        assert all(bar["end_ms_exclusive"] < boundary for bar in series["completed"])
    clock.advance(2_000)
    second = scanner.scan(("BTCUSDT",))
    for interval in ("15m", "5m"):
        series = second["markets"]["BTCUSDT"]["series"][interval]
        assert series["completed"][-1]["end_ms_exclusive"] == boundary
        assert series["completed"][-1]["receipt"]["scan_id"] == 2
        assert len(series["context"]) == 1


@pytest.mark.parametrize("fault,expected", [
    ("bad_end", "KLINE_BOUNDARY"), ("bad_alignment", "KLINE_BOUNDARY"),
    ("drop", "KLINE_GAP"), ("duplicate", "KLINE_DUPLICATE"), ("reorder", "KLINE_REORDERED"),
    ("future", "KLINE_OUTSIDE_WINDOW"), ("nan", "INVALID_DECIMAL"), ("float", "INVALID_DECIMAL"),
    ("huge", "INVALID_DECIMAL"), ("negative", "DECIMAL_RANGE"), ("bad_ohlc", "KLINE_INVALID_OHLC"),
    ("bad_volume", "KLINE_INVALID_VOLUME"), ("wrong_length", "KLINE_FIELD_COUNT"),
])
def test_invalid_candle_quarantines_scan(setup_scan, fault, expected):
    def change(route, params, value):
        if route != KLINES or params["interval"] != "5m":
            return value
        if fault == "bad_end":
            value[0][6] += 1
        elif fault == "bad_alignment":
            value[0][0] += 1
        elif fault == "drop":
            value.pop(1)
        elif fault == "duplicate":
            value.insert(0, value[0].copy())
        elif fault == "reorder":
            value[0], value[1] = value[1], value[0]
        elif fault == "future":
            value[-1][0] += INTERVALS["5m"]
            value[-1][6] += INTERVALS["5m"]
        elif fault in ("nan", "float", "huge"):
            value[0][1] = {"nan": "NaN", "float": 10.0, "huge": "1e10000000"}[fault]
        elif fault == "negative":
            value[0][5] = "-1"
        elif fault == "bad_ohlc":
            value[0][2] = "1"
        elif fault == "bad_volume":
            value[0][9] = "999"
        else:
            value[0].pop()
        return value

    outcome = only_btc(setup_scan, change)
    assert outcome["market_setup_status"] == "SOURCE_BLOCKED"
    assert outcome["issue"]["code"] == expected
    assert count_bars(setup_scan[0]) == 0
    assert Cache(setup_scan[0]).load_receipts(1)


def test_completed_revision_is_audited_and_cannot_overwrite(setup_scan):
    path, clock, transport = setup_scan
    scanner = Scanner(path, transport, clock)
    accepted = scanner.scan(("BTCUSDT",))
    assert accepted["data_ready"]
    clock.advance(300_000)

    def revise(route, params, value):
        if route == KLINES and params["interval"] == "5m":
            value[0][5] = "13"
        return value

    transport.mutate = revise
    rejected = scanner.scan(("BTCUSDT",))
    assert rejected["issue"]["code"] == "KLINE_REVISION"
    assert "BTCUSDT/5m/" in rejected["issue"]["detail"]
    assert count_bars(path) == 15
    assert Cache(path).load_snapshot(1) == accepted
    with Cache(path).connect() as db:
        assert {row[0] for row in db.execute("SELECT DISTINCT scan_id FROM candles")} == {1}
    transport.mutate = None
    reopened = scanner.scan(("BTCUSDT",))
    assert reopened["data_ready"]
    assert count_bars(path) == 16


@pytest.mark.parametrize("field,bad", [
    ("contractType", "CURRENT_QUARTER"), ("status", "BREAK"),
    ("quoteAsset", "BUSD"), ("marginAsset", "USDC"), ("baseAsset", "ETH"), ("symbol", "ADAUSDT"),
])
def test_ineligible_instrument_rejected_before_klines(setup_scan, field, bad):
    def mutate(route, _, value):
        if route == INSTRUMENTS:
            value["symbols"][0][field] = bad
        return value

    output = only_btc(setup_scan, mutate)
    assert output["issue"]["code"].startswith("INSTRUMENT_")
    assert [route for route, _, _ in setup_scan[2].calls] == [TIME, INSTRUMENTS]


@pytest.mark.parametrize("field,bad", [("tickSize", "0"), ("minPrice", "-1"), ("maxPrice", "Infinity")])
def test_invalid_filters(setup_scan, field, bad):
    def mutate(route, _, value):
        if route == INSTRUMENTS:
            value["symbols"][0]["filters"][0][field] = bad
        return value

    assert not only_btc(setup_scan, mutate)["data_ready"]


@pytest.mark.parametrize("route,event,obs", [(QUOTE, "time", "book_ticker"), (DEPTH, "T", "depth")])
def test_stale_liquidity_explicit_and_non_actionable(setup_scan, route, event, obs):
    def mutate(candidate, _, value):
        if candidate == route:
            value[event] -= 6000
        return value

    snap = only_btc(setup_scan, mutate)
    assert snap["market_setup_status"] == "SOURCE_BLOCKED"
    assert snap["markets"]["BTCUSDT"]["context"][obs]["status"] == "STALE"


def test_candle_freshness_is_configurable(setup_scan):
    milliseconds = dict(INTERVALS)
    milliseconds["5m"] = 1
    snap = only_btc(setup_scan, policy=replace(Policy(), candle_freshness_ms=milliseconds))
    assert snap["markets"]["BTCUSDT"]["series"]["5m"]["status"] == "STALE"
    assert not snap["data_ready"]


@pytest.mark.parametrize("variant,status", [("short_depth", "PARTIAL"), ("missing_oi", "MISSING")])
def test_partial_or_missing_market_values(setup_scan, variant, status):
    def mutate(route, _, value):
        if route == DEPTH and variant == "short_depth":
            value["asks"].pop()
        if route == OI_HISTORY and variant == "missing_oi":
            return []
        return value

    snap = only_btc(setup_scan, mutate)
    context = snap["markets"]["BTCUSDT"]["context"]
    name = "depth" if status == "PARTIAL" else "open_interest_history"
    assert context[name]["status"] == status
    assert not snap["data_ready"]


def test_special_and_regular_funding_at_same_exchange_timestamp(setup_scan):
    def mutate(route, _, value):
        if route == FUNDING:
            value.append({**value[-1], "fundingRateType": "Special"})
        return value

    snap = only_btc(setup_scan, mutate)
    values = snap["markets"]["BTCUSDT"]["context"]["funding_history"]["values"]["rows"]
    assert snap["data_ready"]
    assert [row["fundingRateType"] for row in values[-2:]] == ["Regular", "Special"]
    assert values[-2]["source_ms"] == values[-1]["source_ms"]


def test_future_context_is_quarantined(setup_scan):
    def mutate(route, _, value):
        if route == MARK:
            value["time"] += 1000
        return value

    assert only_btc(setup_scan, mutate)["issue"]["code"] == "FUTURE_OBSERVATION"


def test_clock_bracket_and_no_50ms_veto(setup_scan):
    path, clock, transport = setup_scan

    def wall_step(route, _, value):
        if route == INSTRUMENTS:
            clock.wall_ms += 65
        return value

    transport.mutate = wall_step
    snap = Scanner(path, transport, clock).scan(("BTCUSDT",))
    assert snap["data_ready"]
    first = snap["clock"]["first"]
    assert first["wall_offset_lower_ms"] <= 350 <= first["wall_offset_upper_ms"]
    final = snap["clock"]["reconciled"]
    assert final["wall_offset_lower_ms"] <= 285 <= final["wall_offset_upper_ms"]
    assert final["uncertainty_ms"] <= Policy().max_clock_uncertainty_ms
    now = SystemClock()
    assert now.sample().mono_ms <= now.sample().mono_ms


@pytest.mark.parametrize("fault,code", [("rtt", "CLOCK_UNCERTAIN"), ("witness", "CLOCK_BRACKETS_DISAGREE")])
def test_clock_quarantine_and_reacquire(setup_scan, fault, code):
    path, clock, transport = setup_scan

    def mutate(route, _, value):
        if route == TIME and fault == "rtt":
            clock.advance(400)
        if route == TIME and fault == "witness" and len(transport.calls) > 1:
            value["serverTime"] += 2500
        return value

    transport.mutate = mutate
    scanner = Scanner(path, transport, clock)
    assert scanner.scan(("BTCUSDT",))["issue"]["code"] == code
    assert count_bars(path) == 0
    transport.mutate = None
    assert scanner.scan(("BTCUSDT",))["data_ready"]


def test_reject_nonpersonal_database(setup_scan):
    path, _, _ = setup_scan
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (name TEXT)")
    with pytest.raises(ValueError, match="CACHE_WRONG_SCHEMA"):
        only_btc(setup_scan)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM sqlite_master").fetchall() == [("unrelated",)]


def test_fixture_evidence_cannot_enter_strict_contracts(setup_scan):
    snapshot = only_btc(setup_scan)
    assert set(STRICT_POLICY["routes"]) == {TIME, INSTRUMENTS, KLINES}
    assert snapshot["schema"] == "PERSONAL_PUBLIC_MARKET_SNAPSHOT_V1"
    with pytest.raises(ValidationError):
        NativeQuarantineRecord.model_validate(snapshot)
    protocol = load_protocol(Path("frozen_protocol.json").read_bytes())
    envelope = {
        "schema_version": C_SCHEMA, "protocol_sha256": protocol["protocol_sha256"],
        "source_kind": snapshot["evidence_class"], "native_admission": None, "synthetic_manifest": {},
        "evaluation_asof_ms": 1, "historical_bounded": False, "episodes": [], "control_pool": [],
        "no_setup_decision_count": 0,
    }
    with pytest.raises(ContractError, match="SOURCE_CLASS_INVALID"):
        validate_c({**envelope, "export_sha256": digest(envelope)}, protocol)
    mislabeled = {**envelope, "source_kind": "NATIVE_QUALIFIED", "native_admission": snapshot}
    with pytest.raises(ContractError, match="NATIVE_ADMISSION_UNAVAILABLE"):
        validate_c({**mislabeled, "export_sha256": digest(mislabeled)}, protocol)


def test_reload_can_backfill_more_history_within_bounds(setup_scan):
    path, clock, transport = setup_scan
    assert Scanner(path, transport, clock).scan(("BTCUSDT",))["data_ready"]
    clock.advance(300_000)
    outcome = Scanner(path, transport, clock, replace(Policy(), history_bars=5)).scan(("BTCUSDT",))
    assert outcome["data_ready"]
    assert all(len(series["completed"]) == 5 for series in outcome["markets"]["BTCUSDT"]["series"].values())
    assert count_bars(path) == 25


def test_cache_observations_do_not_leak_into_backdated_scan(setup_scan):
    path, clock, transport = setup_scan
    clock.advance(30_000)
    assert Scanner(path, transport, clock).scan(("BTCUSDT",))["data_ready"]
    past = FixtureClock()
    result = Scanner(path, FixtureTransport(past), past).scan(("BTCUSDT",))
    assert result["issue"]["code"] == "CACHED_CANDLE_NOT_YET_OBSERVED"
    assert count_bars(path) == 15
