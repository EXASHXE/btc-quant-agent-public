from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from quant_personal_public_b1.archive import view_v1
from quant_personal_public_b1.fixture import (
    FixtureClock,
    FixtureTransport,
    fixture_reply,
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
    QUOTE,
    TICKER,
    TIME,
    Policy,
    SourceBlocked,
)
from quant_personal_public_b1.runtime import Config, Runtime
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_b1.store import Stamp, Store, encode, sha
from quant_personal_public_b1.wire import FIXTURE, GENUINE, LOOPBACK

BTC = ("BTCUSDT",)


def test_three_symbol_incremental_restart_replay(tmp_path):
    clock = FixtureClock()
    path = tmp_path / "market.sqlite"
    first = Runtime.fixtures(path, clock, identity=RunIdentity("test-boot", "initial"))
    a = first.scan()
    assert a["data_ready"] and a["feature_warmup_ready"]
    assert a["strategy_status"] == "NOT_EVALUATED" and not a["strategy_evaluated"]
    assert a["account_context_status"] == "UNAVAILABLE"
    assert a["frame_order"] == list(INTERVALS)
    assert len(a["markets"]) == 3
    assert a["clock"]["bar_cutoff_venue_ms"] < a["decision_as_of_venue_ms"]
    original = first.store.snapshot(scan=1)
    assert original == a
    before = a["clock"]["bar_cutoff_venue_ms"]
    assert first.store.snapshot(as_of_ms=before) is None
    assert first.store.snapshot(as_of_ms=a["decision_as_of_venue_ms"] - 1) is None
    for symbol, market in a["markets"].items():
        assert market["data_ready"] and market["feature_warmup_ready"]
        assert market["context"]["instrument"]["values"]["symbol"] == symbol
        for name in ("quote", "mark", "depth", "oi"):
            item = market["context"][name]
            assert item["received_venue_upper_ms"] > before
            assert item["status"] == "CURRENT"
            assert item["source_event_ms"] <= a["decision_as_of_venue_ms"]
            assert item["first_request"]["monotonic_ms"] < item["first_receipt"]["monotonic_ms"]
            assert item["first_receipt"]["monotonic_ms"] < item["first_durable_availability"]["monotonic_ms"]
        frame = market["frames"]["5m"]
        candle = frame["completed"][-1]
        assert candle["end_ms_exclusive"] == candle["close_ms_inclusive"] + 1
        assert candle["source_event_ms"] is None and candle["source_publication"] == "UNKNOWN"
        assert frame["context"][-1]["finality"] == "FORMING"
    old_receipts = a["markets"]["BTCUSDT"]["context"]
    clock.advance(300_000)
    runtime = Runtime.fixtures(path, clock, identity=RunIdentity("test-boot", "refresh"))
    b = runtime.scan()
    assert b["data_ready"]
    assert runtime.store.snapshot(scan=1) == original
    assert runtime.store.snapshot(as_of_ms=a["decision_as_of_venue_ms"]) == original
    assert runtime.store.snapshot() == b
    new = b["markets"]["BTCUSDT"]
    assert new["frames"]["5m"]["completed"][-1]["open_ms"] == a["markets"]["BTCUSDT"]["frames"]["5m"]["context"][-1]["open_ms"]
    assert new["context"]["quote"]["receipt_id"] != old_receipts["quote"]["receipt_id"]
    assert new["context"]["funding"]["receipt_id"] == old_receipts["funding"]["receipt_id"]
    assert new["context"]["funding"]["first_durable_availability"] == old_receipts["funding"]["first_durable_availability"]
    assert new["context"]["quote"]["first_durable_availability"]["session"] == "refresh"
    assert b["request_count"] < a["request_count"]
    for receipt in runtime.budget.evidence(2):
        assert receipt["request"]["method"] == "GET"
        assert sha(runtime.store.raw(receipt["receipt_id"])) == receipt["response"]["body_sha256"]


def test_required_ready_data_is_independent_from_indicator_warmup(tmp_path):
    clock = FixtureClock()
    config = Config(policy=replace(Policy(), history_bars=3))
    payload = Runtime.fixtures(tmp_path / "market", clock, config=config).scan(BTC)
    assert payload["data_ready"]
    assert not payload["feature_warmup_ready"] and not payload["strategy_evaluated"]
    assert payload["strategy_status"] == "NOT_EVALUATED"
    assert [dep["completed_bars"] for dep in payload["feature_dependencies"]] == [15, 30]
    assert "NO_SETUP" not in encode(payload)


def test_revision_append_only_and_backdated_boot_blocked(tmp_path):
    path = tmp_path / "market"
    clock = FixtureClock()
    fixture = FixtureTransport(clock)
    a = Runtime.fixtures(path, clock, fixture, identity=RunIdentity("boot-a", "a")).scan(BTC)
    old = a["markets"]["BTCUSDT"]["frames"]["5m"]["completed"][-1]
    clock.advance(30_000)

    def mutate(route, params, payload):
        if route == KLINES and params["interval"] == "5m":
            for row in payload:
                if row[0] == old["open_ms"]:
                    row[5] = "12.35"
        return payload

    fixture.mutate = mutate
    instance = Runtime.fixtures(path, clock, fixture, identity=RunIdentity("boot-a", "b"))
    b = instance.scan(BTC)
    revised = b["markets"]["BTCUSDT"]["frames"]["5m"]["completed"][-1]
    assert revised["revision"] == 2 and revised["previous_receipt_id"] == old["receipt_id"]
    assert revised["first_durable_availability"] != old["first_durable_availability"]
    assert instance.store.snapshot(as_of_ms=a["decision_as_of_venue_ms"]) == a
    past = Runtime.fixtures(path, FixtureClock(), identity=RunIdentity("boot-b", "past"))
    c = past.scan(BTC)
    assert c["source_status"] == "SOURCE_BLOCKED"
    assert c["issue"]["code"] == "VENUE_TIME_REGRESSION"
    assert past.store.snapshot() == c
    assert past.store.snapshot(as_of_ms=b["decision_as_of_venue_ms"]) == b


def test_staged_crash_is_invisible_and_recovery_leaves_audit(tmp_path):
    clock = FixtureClock()
    instance = Runtime.fixtures(tmp_path / "market", clock, identity=RunIdentity("boot", "crashed"))
    stamp = instance.identity.stamp(clock.sample())
    with instance.store.collector():
        incomplete = instance.store.start(stamp)
        instance.store.stage(incomplete, {"never": "published"}, [])
    assert instance.store.snapshot(scan=incomplete) is None
    clock.advance(300_000)
    final = instance.scan(BTC)
    assert final["scan_id"] == 2 and final["data_ready"]
    with instance.store.connect() as db:
        assert db.execute("SELECT abandoned FROM scans WHERE id=1").fetchone()[0] is not None
    assert instance.store.snapshot(scan=incomplete) is None


@pytest.mark.parametrize("route", [TIME, INSTRUMENTS])
def test_global_bad_time_or_exchange_info(tmp_path, route):
    clock = FixtureClock()
    fixture = FixtureTransport(clock, mutate=lambda path, *_: {} if path == route else _[-1])
    output = Runtime.fixtures(tmp_path / "market", clock, fixture).scan()
    assert output["source_status"] == "SOURCE_BLOCKED"
    assert not output["markets"] and output["issue"]


@pytest.mark.parametrize("fault", ["inactive", "invalid_symbol", "gap", "stale_quote", "depth_partial"])
def test_bad_symbol_does_not_block_other_symbols(tmp_path, fault):
    clock = FixtureClock()

    def mutate(route, params, body):
        if route == INSTRUMENTS and fault == "inactive":
            body["symbols"][0]["status"] = "BREAK"
        if params.get("symbol") != "BTCUSDT":
            return body
        if fault == "invalid_symbol" and route == KLINES:
            return fixture_reply({"code": -1121}, status=400)
        if fault == "gap" and route == KLINES:
            body.pop(0)
        if fault == "stale_quote" and route == QUOTE:
            body["time"] -= 50_000
        if fault == "depth_partial" and route == DEPTH:
            body["asks"].pop()
        return body

    run = Runtime.fixtures(tmp_path / "market", clock, FixtureTransport(clock, mutate=mutate))
    output = run.scan(("BTCUSDT", "ETHUSDT"))
    assert output["source_status"] == "PARTIAL"
    assert output["markets"]["ETHUSDT"]["data_ready"]
    assert not output["markets"]["BTCUSDT"]["data_ready"]
    assert output["markets"]["BTCUSDT"]["strategy_status"] == "NOT_EVALUATED"


def test_restriction_kills_whole_result_even_after_valid_first_symbol(tmp_path):
    clock = FixtureClock()

    def mutate(route, params, body):
        if params.get("symbol") == "ETHUSDT" and route == MARK:
            return fixture_reply({"message": "Service unavailable from a restricted location"}, status=400)
        return body

    runtime = Runtime.fixtures(tmp_path / "market", clock, FixtureTransport(clock, mutate=mutate))
    blocked = runtime.scan(("BTCUSDT", "ETHUSDT"))
    assert blocked["issue"]["code"] == "VENUE_RESTRICTED"
    assert not blocked["markets"] and not blocked["data_ready"]
    with runtime.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM bars").fetchone()[0] == 0


def test_slow_refresh_and_metadata_rechecks_lifecycle(tmp_path):
    clock = FixtureClock()
    fixture = FixtureTransport(clock)
    runtime = Runtime.fixtures(tmp_path / "market", clock, fixture)
    assert runtime.scan(BTC)["data_ready"]
    clock.advance(5000)
    fixture.calls.clear()
    assert runtime.scan(BTC)["data_ready"]
    routes = {route for route, _, _ in fixture.calls}
    assert {QUOTE, DEPTH, MARK, OI} <= routes
    assert not {INSTRUMENTS, TICKER, OI_HISTORY, FUNDING} & routes

    def delisted(route, params, body):
        if route == INSTRUMENTS:
            body["symbols"][0]["status"] = "SETTLING"
        return body

    fixture.mutate = delisted
    clock.advance(20_000)
    output = runtime.scan(BTC)
    assert output["markets"]["BTCUSDT"]["issue"]["code"] == "INSTRUMENT_INELIGIBLE"


def test_paginated_warmup_catchup_and_bound_per_symbol(tmp_path):
    clock = FixtureClock()
    transport = FixtureTransport(clock)
    config = Config(page_rows=12, max_kline_pages=5)
    instance = Runtime.fixtures(tmp_path / "market", clock, transport, config=config)
    assert instance.scan(BTC)["data_ready"]
    clock.advance(4 * 3_600_000)
    transport.calls.clear()
    caught = instance.scan(BTC)
    assert caught["data_ready"]
    pages = [p for path, p, _ in transport.calls if path == KLINES and p["interval"] == "5m"]
    assert 1 < len(pages) <= 5
    assert all(a["endTime"] + INTERVALS["5m"] == b["startTime"] for a, b in zip(pages, pages[1:], strict=False))
    clock.advance(24 * 3_600_000)
    blocked = instance.scan(("BTCUSDT", "ETHUSDT"))
    assert blocked["markets"]["BTCUSDT"]["issue"]["code"] == "KLINE_CATCHUP_BOUND"
    assert blocked["markets"]["ETHUSDT"]["data_ready"]


def test_new_boot_uses_new_witness_without_cross_comparing_mono(tmp_path):
    path = tmp_path / "market"
    first = FixtureClock()
    a = Runtime.fixtures(path, first, identity=RunIdentity("old", "one")).scan(BTC)
    second = FixtureClock(first.venue_ms + 300_000)
    second.monotonic_ms = 1
    b = Runtime.fixtures(path, second, identity=RunIdentity("new", "two")).scan(BTC)
    assert b["data_ready"]
    assert b["published"]["boot"] == "new" and b["published"]["monotonic_ms"] < a["published"]["monotonic_ms"]
    assert b["decision_as_of_venue_ms"] > a["decision_as_of_venue_ms"]


def test_origin_db_and_sealed_archive(tmp_path):
    fixture_path = tmp_path / "fixture"
    clock = FixtureClock()
    runtime = Runtime.fixtures(fixture_path, clock)
    runtime.scan(BTC)
    for forbidden in (GENUINE, LOOPBACK):
        with pytest.raises(SourceBlocked, match="DB_ORIGIN_MISMATCH"):
            Store(fixture_path, forbidden, "fixture-local")
    with pytest.raises(SourceBlocked, match="LIVE_CAPABILITY_DORMANT"):
        Store(tmp_path / "genuine", GENUINE, "genuine", create=True)
    assert not (tmp_path / "genuine").exists()
    path = Path(__file__).resolve().parents[1] / "evidence/r1_input/scan_1.json"
    raw = path.read_bytes()
    pin = json.loads((path.parent / "pin.json").read_bytes())["sha256"]
    v2 = view_v1(raw, pin, Stamp("test", "archive", 10, 20))
    assert v2["data_ready"] and not v2["feature_warmup_ready"]
    assert v2["strategy_status"] == "NOT_EVALUATED"
    assert v2["durable_availability"] is None and not v2["historical_replay_eligible"]
    assert v2["source_origin"] == FIXTURE
    with pytest.raises(SourceBlocked, match="R1_INPUT_DIGEST_MISMATCH"):
        view_v1(raw + b" ", pin, Stamp("test", "archive", 10, 20))


def test_projection_uncertainty_within_symbol_is_a_venue_wide_stop(tmp_path):
    clock = FixtureClock()

    def delayed(route, params, body):
        if route == KLINES and params["symbol"] == "BTCUSDT":
            clock.advance(1500)
        return body

    target = FixtureTransport(clock, mutate=delayed)
    config = Config(policy=replace(Policy(), max_clock_uncertainty_ms=8, max_clock_drift_ppm=1000,
                                   request_timeout_ms=2000))
    result = Runtime.fixtures(tmp_path / "market", clock, target, config=config).scan(("BTCUSDT", "ETHUSDT"))
    assert result["issue"]["code"] == "CLOCK_UNCERTAIN"
    assert not result["markets"]
    assert not any(p.get("symbol") == "ETHUSDT" for _, p, _ in target.calls)
