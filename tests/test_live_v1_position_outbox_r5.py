from __future__ import annotations

import asyncio

import pytest
from test_live_v1_position_supervisor import NOW, market_case, observation

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import PositionSupervisor
from btc_quant_agent.position_supervisor.supervisor import position_case_from_event


def _worker(path):
    analyzed = []
    market_symbols = []

    class Analysis:
        async def analyze_case(self, case):
            analyzed.append(case)

    def fresh(symbol):
        market_symbols.append(symbol)
        return market_case()

    return PositionSupervisor(path, analysis_service=Analysis(), fresh_market_case=fresh), analyzed, market_symbols


def _freeze(db, event, case):
    db.execute(
        "UPDATE live_position_case_dispatches SET position_case_id=?, position_case_hash=?, "
        "position_case_json=?, case_hash=? WHERE event_id=?",
        (case.case_id, case.case_hash, case.canonical_json(), case.case_hash, event.event_id),
    )


def test_corrupt_dispatch_symbol_fails_closed_before_market_or_analysis(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute("UPDATE live_position_case_dispatches SET symbol='ETHUSDT' WHERE event_id=?", (event.event_id,))
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


def test_corrupt_event_row_symbol_fails_closed_before_market_or_analysis(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute("UPDATE live_position_events SET symbol='ETHUSDT' WHERE event_id=?", (event.event_id,))
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


@pytest.mark.parametrize("field", ["account_id", "environment", "credential_namespace", "position_side"])
def test_corrupt_optional_dispatch_authority_fails_closed(field, tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute(f"ALTER TABLE live_position_case_dispatches ADD COLUMN {field} TEXT")
        db.execute(f"UPDATE live_position_case_dispatches SET {field}='other' WHERE event_id=?", (event.event_id,))
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


def test_present_dispatch_authority_column_cannot_be_null(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute("ALTER TABLE live_position_case_dispatches ADD COLUMN account_id TEXT")
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


def test_frozen_wrong_symbol_fails_closed_without_market_or_analysis(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    values = market_case().model_dump(mode="python", exclude={"case_hash"})
    values["symbol"] = "ETHUSDT"
    frozen = position_case_from_event(CasePackageV1.build(**values), event)
    with connection(path) as db:
        _freeze(db, event, frozen)
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


def test_frozen_case_hash_denormalization_fails_closed(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    frozen = position_case_from_event(market_case(), event)
    with connection(path) as db:
        _freeze(db, event, frozen)
        db.execute("UPDATE live_position_case_dispatches SET case_hash='wrong' WHERE event_id=?", (event.event_id,))
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


def test_fresh_wrong_symbol_cannot_be_frozen_or_analyzed(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    values = market_case().model_dump(mode="python", exclude={"case_hash"})
    values["symbol"] = "ETHUSDT"
    wrong = CasePackageV1.build(**values)
    worker.fresh_market_case = lambda symbol: (market_symbols.append(symbol), wrong)[1]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert market_symbols == [event.symbol]
    assert analyzed == []
    assert worker.get_dispatch(event.event_id)["position_case_json"] == ""
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"


def test_valid_dispatch_stays_done_after_restart(tmp_path):
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == (event,)
    restarted, second_analysis, second_market = _worker(path)
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 1)) == ()
    assert len(analyzed) == 1
    assert market_symbols == [event.symbol]
    assert second_analysis == second_market == []
