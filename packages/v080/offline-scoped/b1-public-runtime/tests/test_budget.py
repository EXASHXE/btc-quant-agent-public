from __future__ import annotations

import multiprocessing as mp
import os
from dataclasses import replace
from pathlib import Path

import pytest

from quant_personal_public_b1.budget import Budget
from quant_personal_public_b1.fixture import (
    FixtureClock,
    FixtureTransport,
    fixture_reply,
)
from quant_personal_public_b1.policy import (
    FUNDING,
    OI_HISTORY,
    QUOTE,
    TIME,
    Policy,
    SourceBlocked,
)
from quant_personal_public_b1.runtime import Config, Runtime
from quant_personal_public_b1.store import Stamp, Store
from quant_personal_public_b1.wire import FIXTURE, Request


def stamp(ms, boot="boot"):
    return Stamp(boot, "budget-test", 1_800_000_000_000 + ms, ms)


def opened(path, ceiling=3):
    s = Store(path, FIXTURE, "fixture-local", create=True)
    return s, Budget(s, bootstrap=ceiling)


def reserve_then_exit(filename, scan):
    store = Store(Path(filename), FIXTURE, "fixture-local")
    Budget(store, bootstrap=1).reserve(scan, 1, 0, Request(TIME, {}), stamp(1000))
    os._exit(23)


def simultaneous(filename, scan, barrier, queue):
    store = Store(Path(filename), FIXTURE, "fixture-local")
    budget = Budget(store, bootstrap=1)
    barrier.wait(timeout=5)
    try:
        queue.put(budget.reserve(scan, 1, 0, Request(TIME, {}), stamp(1000)))
    except SourceBlocked as exc:
        queue.put(exc.code)


def test_crash_after_reservation_cannot_release_weight(tmp_path):
    path = tmp_path / "budget"
    store, budget = opened(path, 1)
    scan = store.start(stamp(0))
    ctx = mp.get_context("spawn")
    process = ctx.Process(target=reserve_then_exit, args=(str(path), scan))
    process.start()
    process.join(10)
    assert process.exitcode == 23
    assert budget.evidence(scan)[0]["response"] is None
    next_scan = store.start(stamp(1001))
    with pytest.raises(SourceBlocked, match="VENUE_WEIGHT_LIMIT"):
        budget.reserve(next_scan, 1, 0, Request(TIME, {}), stamp(1001))
    assert budget.reserve(next_scan, 1, 0, Request(TIME, {}), stamp(61_001)) > 0


def test_independent_processes_cannot_double_spend(tmp_path):
    path = tmp_path / "budget"
    store, _ = opened(path, 1)
    scans = [store.start(stamp(0)), store.start(stamp(0))]
    ctx = mp.get_context("spawn")
    barrier, queue = ctx.Barrier(2), ctx.Queue()
    children = [ctx.Process(target=simultaneous, args=(str(path), scan, barrier, queue)) for scan in scans]
    for p in children:
        p.start()
    values = [queue.get(timeout=10), queue.get(timeout=10)]
    for p in children:
        p.join(10)
        assert p.exitcode == 0
    assert "VENUE_WEIGHT_LIMIT" in values and any(type(value) is int for value in values)


def test_single_collector_lock_is_orthogonal_to_reservations(tmp_path):
    path = tmp_path / "budget"
    one, _ = opened(path)
    two, _ = opened(path)
    with one.collector(), pytest.raises(SourceBlocked, match="COLLECTOR_ALREADY_RUNNING"), two.collector():
        pytest.fail("a competing collector acquired the lock")
    with two.collector():
        assert two.start(stamp(0)) == 1


@pytest.mark.parametrize("code", [403, 418, 451])
def test_hard_stop_persists_over_restart_and_boot_change(tmp_path, code):
    path = tmp_path / "budget"
    store, budget = opened(path)
    scan = store.start(stamp(0))
    req = Request(TIME, {})
    ident = budget.reserve(scan, 1, 0, req, stamp(0))
    assert budget.settle(ident, stamp(1), fixture_reply({}, status=code)) == f"HTTP_{code}"
    store, budget = opened(path, 9999)
    for time, boot in ((9_000_000, "boot"), (0, "different")):
        with pytest.raises(SourceBlocked, match=f"HTTP_{code}"):
            budget.reserve(scan, 2, 0, req, stamp(time, boot))


def test_restart_after_429_conservative_across_a_new_boot(tmp_path):
    path = tmp_path / "budget"
    store, budget = opened(path)
    scan = store.start(stamp(0))
    req = Request(TIME, {})
    ident = budget.reserve(scan, 1, 0, req, stamp(0))
    budget.settle(ident, stamp(1), fixture_reply({}, status=429, headers={"retry-after": "5"}))
    store, budget = opened(path)
    for elapsed, boot in ((1000, "boot"), (2, "reboot"), (5001, "reboot")):
        with pytest.raises(SourceBlocked, match="RETRY_AFTER_ACTIVE"):
            budget.reserve(scan, 2, 0, req, stamp(elapsed, boot))
    assert budget.reserve(scan, 2, 0, req, stamp(5002, "reboot"))
    assert budget.evidence(scan)[0]["response"]["status"] == 429


def test_explicit_region_deny_persisted_even_under_nonstandard_status(tmp_path):
    path = tmp_path / "budget"
    store, budget = opened(path)
    scan = store.start(stamp(5))
    req = Request(TIME, {})
    attempt = budget.reserve(scan, 1, 0, req, stamp(5))
    assert budget.settle(attempt, stamp(6), fixture_reply({"msg": "not available in your region"},
                                                         status=400)) == "VENUE_RESTRICTED"
    _, after_restart = opened(path)
    with pytest.raises(SourceBlocked, match="VENUE_RESTRICTED"):
        after_restart.reserve(scan, 2, 0, req, stamp(7))


@pytest.mark.parametrize("misleading", ["0", "999999"])
def test_trustworthy_header_and_bookticker_exclusion_survive_restart(tmp_path, misleading):
    path = tmp_path / "budget"
    store, budget = opened(path, 10)
    scan = store.start(stamp(0))
    clock_request = Request(TIME, {})
    a = budget.reserve(scan, 1, 0, clock_request, stamp(0))
    budget.settle(a, stamp(1), fixture_reply({}, headers={"x-mbx-used-weight-1m": "7"}))
    b = budget.reserve(scan, 2, 0, Request(QUOTE, {"symbol": "BTCUSDT"}), stamp(2))
    budget.settle(b, stamp(3), fixture_reply({}, headers={"x-mbx-used-weight-1m": misleading}))
    _, budget = opened(path, 10)
    assert budget.reserve(scan, 3, 0, clock_request, stamp(4))
    with pytest.raises(SourceBlocked, match="VENUE_WEIGHT_LIMIT"):
        budget.reserve(scan, 4, 0, clock_request, stamp(5))


@pytest.mark.parametrize("route,cap,params", [
    (FUNDING, 500, {"symbol": "BTCUSDT", "limit": 5}),
    (OI_HISTORY, 1000, {"symbol": "BTCUSDT", "period": "5m", "limit": 5}),
])
def test_shared_family_caps_and_zero_weight(tmp_path, route, cap, params):
    path = tmp_path / "budget"
    store, budget = opened(path, 2000)
    scan = store.start(stamp(0))
    req = Request(route, params)
    for i in range(cap):
        budget.reserve(scan, i + 1, 0, req, stamp(0))
    _, second = opened(path, 2000)
    with pytest.raises(SourceBlocked, match="ENDPOINT_FAMILY_LIMIT"):
        second.reserve(scan, cap + 1, 0, req, stamp(1))
    assert second.reserve(scan, cap + 1, 0, req, stamp(300_001))
    if route == OI_HISTORY:
        assert sum(row["weight"] for row in second.evidence(scan)) == 0


def test_exchange_raw_request_limits_even_for_zero_weight(tmp_path):
    store, budget = opened(tmp_path / "budget")
    budget.configure({("RAW_REQUESTS", 1000): 1, ("REQUEST_WEIGHT", 60_000): 100})
    scan = store.start(stamp(0))
    req = Request(OI_HISTORY, {"symbol": "BTCUSDT", "period": "5m", "limit": 1})
    budget.reserve(scan, 1, 0, req, stamp(0))
    with pytest.raises(SourceBlocked, match="VENUE_RAW_LIMIT"):
        budget.reserve(scan, 2, 0, req, stamp(1))


@pytest.mark.parametrize("success", [True, False])
def test_one_retry_per_logical_request_and_local_charge(tmp_path, success):
    clock = FixtureClock()
    count = 0

    def transient(route, _, body):
        nonlocal count
        if route == TIME:
            count += 1
            if count == 1 or not success:
                return fixture_reply({}, status=502)
        return body

    runtime = Runtime.fixtures(tmp_path / "budget", clock, FixtureTransport(clock, mutate=transient))
    outcome = runtime.scan(("BTCUSDT",))
    receipts = runtime.budget.evidence(outcome["scan_id"])
    assert [row["retry"] for row in receipts[:2]] == [0, 1]
    assert sum(row["weight"] for row in receipts) == outcome["request_weight"]
    assert outcome["data_ready"] is success
    if not success:
        assert len(receipts) == 2 and outcome["issue"]["code"] == "TRANSIENT_HTTP_EXHAUSTED"


def test_local_attempt_budget_limits_retries(tmp_path):
    clock = FixtureClock()
    fixture = FixtureTransport(clock, mutate=lambda *_: fixture_reply({}, status=502))
    config = Config(policy=replace(Policy(), max_requests=1))
    out = Runtime.fixtures(tmp_path / "budget", clock, fixture, config=config).scan(("BTCUSDT",))
    assert out["issue"]["code"] == "LOCAL_SCAN_BUDGET"
    assert out["request_count"] == 1 and len(fixture.calls) == 1


def test_larger_bootstrap_cannot_expand_shared_remaining_budget(tmp_path):
    path = tmp_path / "budget"
    store, budget = opened(path, 1)
    scan = store.start(stamp(1))
    budget.reserve(scan, 1, 0, Request(TIME, {}), stamp(1))
    _, restarted = opened(path, 900)
    with pytest.raises(SourceBlocked, match="VENUE_WEIGHT_LIMIT"):
        restarted.reserve(scan, 2, 0, Request(TIME, {}), stamp(2))


def test_denial_is_retained_if_clock_regresses_while_recording_reply(tmp_path):
    store, budget = opened(tmp_path / "budget")
    scan = store.start(stamp(1000))
    attempt = budget.reserve(scan, 1, 0, Request(TIME, {}), stamp(1000))
    assert budget.settle(attempt, stamp(998), fixture_reply({}, status=418)) == "HTTP_418"
    assert budget.evidence(scan)[0]["response"]["receipt"]["monotonic_ms"] == 998
    with pytest.raises(SourceBlocked, match="HTTP_418"):
        budget.reserve(scan, 2, 0, Request(TIME, {}), stamp(1001))
