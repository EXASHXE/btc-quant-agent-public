"""Lease ownership at the PositionCase analysis boundary."""

from __future__ import annotations

import asyncio
import threading

from test_live_v1_position_supervisor import NOW, market_case, observation

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import PositionSupervisor


def test_expired_worker_does_not_analyze_after_another_worker_freezes_case(tmp_path):
    path = tmp_path / "live.db"
    seed = PositionSupervisor(path)
    event = seed.evaluate(observation(), NOW)[0]
    entered = threading.Event()
    release = threading.Event()
    calls_a: list[str] = []
    calls_b: list[str] = []
    errors: list[Exception] = []

    class Spy:
        def __init__(self, calls: list[str]) -> None:
            self.calls = calls

        async def analyze_case(self, case: CasePackageV1) -> None:
            self.calls.append(case.case_hash)

    def slow_market_case(_symbol: str) -> CasePackageV1:
        entered.set()
        assert release.wait(5)
        return market_case()

    changed = market_case().model_dump(mode="python", exclude={"case_hash"})
    changed["price"] = 102.0
    second_case = CasePackageV1.build(**changed)
    first = PositionSupervisor(path, analysis_service=Spy(calls_a),
                               fresh_market_case=slow_market_case)
    second = PositionSupervisor(path, analysis_service=Spy(calls_b),
                                fresh_market_case=lambda _symbol: second_case)

    def first_worker() -> None:
        try:
            asyncio.run(first.drain_pending_dispatches(NOW, lease_ms=1000))
        except Exception as exc:  # noqa: BLE001 - relay worker failure to the test thread
            errors.append(exc)

    thread = threading.Thread(target=first_worker)
    thread.start()
    try:
        assert entered.wait(5)
        asyncio.run(second.drain_pending_dispatches(NOW + 1001, lease_ms=1000))
    finally:
        release.set()
        thread.join(5)

    assert not thread.is_alive()
    assert not errors
    assert calls_a == []
    assert len(calls_b) == 1
    dispatch = seed.get_dispatch(event.event_id)
    assert dispatch is not None
    assert dispatch["state"] == "DONE"
    assert dispatch["position_case_hash"] == calls_b[0]


def test_lease_expiry_after_freeze_blocks_analysis(tmp_path):
    path = tmp_path / "live.db"
    seed = PositionSupervisor(path)
    event = seed.evaluate(observation(), NOW)[0]
    clock_reads = iter((NOW, NOW + 400, NOW + 1001))
    calls: list[str] = []

    class Spy:
        async def analyze_case(self, case: CasePackageV1) -> None:
            calls.append(case.case_hash)

    worker = PositionSupervisor(path, analysis_service=Spy(),
                                fresh_market_case=lambda _symbol: market_case(),
                                lease_clock_ms=lambda: next(clock_reads, NOW + 1001))
    asyncio.run(worker.drain_pending_dispatches(NOW, lease_ms=1000))

    assert calls == []
    dispatch = seed.get_dispatch(event.event_id)
    assert dispatch is not None
    assert dispatch["state"] == "DISPATCHING"
    assert dispatch["position_case_json"]


def test_stale_worker_cannot_report_done_after_analysis_loses_lease(tmp_path):
    path = tmp_path / "live.db"
    seed = PositionSupervisor(path)
    event = seed.evaluate(observation(), NOW)[0]
    calls: list[str] = []

    class LoseLease:
        async def analyze_case(self, case: CasePackageV1) -> None:
            calls.append(case.case_hash)
            with connection(path) as db:
                db.execute("UPDATE live_position_case_dispatches SET lease_token='new-owner' "
                           "WHERE event_id=?", (event.event_id,))

    worker = PositionSupervisor(path, analysis_service=LoseLease(),
                                fresh_market_case=lambda _symbol: market_case())
    done = asyncio.run(worker.drain_pending_dispatches(NOW))

    assert len(calls) == 1
    assert done == ()
    dispatch = seed.get_dispatch(event.event_id)
    assert dispatch is not None
    assert dispatch["state"] == "DISPATCHING"
    assert dispatch["lease_token"] == "new-owner"
