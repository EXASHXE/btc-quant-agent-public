"""R7 durable analysis admission and terminal authority regressions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_live_v1_position_supervisor import NOW, market_case, observation

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import (
    PositionEventV1,
    PositionSupervisor,
    position_case_from_event,
)
from btc_quant_agent.position_supervisor.models import position_authority_key

AUTHORITY_FIELDS = (
    "event_hash", "symbol", "environment", "credential_namespace",
    "account_id", "position_side", "position_authority_key",
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _worker(path, *, on_fresh=None, on_analysis=None, lease_clock_ms=None):
    calls = []
    fresh_symbols = []

    class Analysis:
        async def analyze_case(self, case):
            calls.append(case)
            if on_analysis is not None:
                await on_analysis(case)

    def fresh(symbol):
        fresh_symbols.append(symbol)
        if on_fresh is not None:
            on_fresh(symbol)
        return market_case()

    return (PositionSupervisor(path, analysis_service=Analysis(), fresh_market_case=fresh,
                               lease_clock_ms=lease_clock_ms), calls, fresh_symbols)


def _drop_dispatch_fence(db):
    db.execute("DROP TRIGGER IF EXISTS trg_live_position_dispatches_immutable_authority")
    db.execute("DROP TRIGGER IF EXISTS trg_live_position_dispatch_admission_immutable")


def _drop_event_fence(db):
    db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")


def _coherent_replacement(path, event, field=None):
    """Replace one authority class, or all of them, with valid archival data."""
    values = event.model_dump(mode="json", exclude={"event_hash"})
    changes = {
        "symbol": "ETHUSDT", "environment": "PAPER", "credential_namespace": "OTHER",
        "account_id": "other-account", "position_side": "SHORT",
    }
    if field is None:
        values.update(changes)
    elif field == "event_hash":
        values["details"] = {**values["details"], "archival_revision": 1}
    elif field == "position_authority_key":
        values["account_id"] = changes["account_id"]
    else:
        values[field] = changes[field]
    values["position_authority_key"] = position_authority_key(
        values["environment"], values["credential_namespace"], values["account_id"],
        values["symbol"], values["position_side"],
    )
    replacement = PositionEventV1.build(**values)
    if field is not None:
        assert getattr(replacement, field) != getattr(event, field)
    with connection(path) as db:
        _drop_event_fence(db)
        _drop_dispatch_fence(db)
        db.execute(
            "UPDATE live_position_events SET event_hash=?, symbol=?, environment=?, "
            "credential_namespace=?, account_id=?, position_side=?, position_authority_key=?, "
            "payload=? WHERE event_id=?",
            (replacement.event_hash, replacement.symbol, replacement.environment,
             replacement.credential_namespace, replacement.account_id,
             replacement.position_side, replacement.position_authority_key,
             replacement.canonical_json(), event.event_id),
        )
        db.execute(
            "UPDATE live_position_case_dispatches SET event_hash=?, symbol=? WHERE event_id=?",
            (replacement.event_hash, replacement.symbol, event.event_id),
        )
    return replacement


def _expected_capsule(event, receipt, lease_token):
    return {
        "schema_version": "POSITION_DISPATCH_AUTHORITY_V1",
        "event_id": event.event_id,
        "event_hash": event.event_hash,
        "symbol": event.symbol,
        "environment": event.environment,
        "credential_namespace": event.credential_namespace,
        "account_id": event.account_id,
        "position_side": event.position_side,
        "position_authority_key": event.position_authority_key,
        "position_case_id": receipt["position_case_id"],
        "position_case_hash": receipt["position_case_hash"],
        "lease_token": lease_token,
    }


def _assert_receipt_identity(event, receipt, case, lease_token):
    capsule = _expected_capsule(event, receipt, lease_token)
    assert receipt["dispatch_authority_json"] == _canonical(capsule)
    assert receipt["dispatch_authority_hash"] == _sha(capsule)
    assert receipt["analysis_admission_hash"] == _sha({
        "schema_version": "POSITION_ANALYSIS_ADMISSION_V1",
        "dispatch_authority_hash": receipt["dispatch_authority_hash"],
    })
    assert receipt["position_case_id"] == case.case_id
    assert receipt["position_case_hash"] == case.case_hash
    assert receipt["position_case_json"] == case.canonical_json()


@pytest.mark.parametrize("field", AUTHORITY_FIELDS)
def test_final_clock_event_authority_corruption_cannot_reach_done(tmp_path, field):
    path = tmp_path / "live.db"
    calls = []
    event_id = None
    clock_calls = 0

    class Analysis:
        async def analyze_case(self, case):
            calls.append(case)

    def clock():
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 4:
            with connection(path) as db:
                db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")
                db.execute(
                    f"UPDATE live_position_events SET {field}=? WHERE event_id=?",
                    ("corrupted", event_id),
                )
        return NOW

    worker = PositionSupervisor(
        path, analysis_service=Analysis(), fresh_market_case=lambda _: market_case(),
        lease_clock_ms=clock,
    )
    event = worker.evaluate(observation(), NOW)[0]
    event_id = event.event_id

    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert len(calls) == 1
    receipt = worker.get_dispatch(event_id)
    assert receipt["state"] != "DONE"
    assert receipt["analysis_admission_hash"]
    assert receipt["analysis_completed"] == 0


def test_unknown_provider_completion_is_never_called_a_second_time(tmp_path):
    path = tmp_path / "live.db"
    calls = []

    class Analysis:
        async def analyze_case(self, case):
            calls.append(case.case_hash)
            raise RuntimeError("provider completion unknown")

    worker = PositionSupervisor(
        path, analysis_service=Analysis(), fresh_market_case=lambda _: market_case(),
    )
    event = worker.evaluate(observation(), NOW)[0]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert len(calls) == 1
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["analysis_admission_hash"]
    assert receipt["state"] == "FAILED_CLOSED"

    restarted = PositionSupervisor(
        path, analysis_service=Analysis(), fresh_market_case=lambda _: market_case(),
    )
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 60_000)) == ()
    assert len(calls) == 1


def test_crash_after_persisted_admission_before_provider_fails_closed_on_restart(tmp_path, monkeypatch):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    mint = worker._mint_analysis_admission

    def crash_after_mint(*args, **kwargs):
        admission = mint(*args, **kwargs)
        assert admission.admission_hash
        raise asyncio.CancelledError("process stopped after durable admission")

    monkeypatch.setattr(worker, "_mint_analysis_admission", crash_after_mint)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker.drain_pending_dispatches(NOW))
    assert calls == []
    admitted = worker.get_dispatch(event.event_id)
    assert admitted["state"] == "DISPATCHING"
    assert admitted["analysis_admission_hash"]
    assert admitted["analysis_completed"] == 0
    identity = (admitted["dispatch_authority_json"], admitted["dispatch_authority_hash"],
                admitted["analysis_admission_hash"])

    restarted, replay_calls, replay_fresh = _worker(path)
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 60_000)) == ()
    final = restarted.get_dispatch(event.event_id)
    assert final["state"] == "FAILED_CLOSED"
    assert (final["dispatch_authority_json"], final["dispatch_authority_hash"],
            final["analysis_admission_hash"]) == identity
    assert replay_calls == replay_fresh == []


def test_normal_sqlite_cannot_fabricate_analysis_completion_after_mint(tmp_path, monkeypatch):
    path = tmp_path / "live.db"
    worker, provider_calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    mint = worker._mint_analysis_admission
    normal_update_rejected = []

    def crash_after_attempted_fabrication(*args, **kwargs):
        admission = mint(*args, **kwargs)
        assert admission.admission_hash
        try:
            with connection(path) as db:
                db.execute(
                    "UPDATE live_position_case_dispatches SET analysis_completed=1 WHERE event_id=?",
                    (event.event_id,),
                )
        except sqlite3.DatabaseError:
            normal_update_rejected.append(True)
        else:
            normal_update_rejected.append(False)
        raise asyncio.CancelledError("process stopped before provider call")

    monkeypatch.setattr(worker, "_mint_analysis_admission", crash_after_attempted_fabrication)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker.drain_pending_dispatches(NOW))
    assert provider_calls == []
    admitted = worker.get_dispatch(event.event_id)
    assert admitted["analysis_admission_hash"]
    admission_hash = admitted["analysis_admission_hash"]

    restarted, replay_calls, replay_fresh = _worker(path)
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 60_000)) == ()
    final = restarted.get_dispatch(event.event_id)
    assert normal_update_rejected == [True]
    assert final["state"] == "FAILED_CLOSED"
    assert final["analysis_completed"] == 0
    assert final["analysis_admission_hash"] == admission_hash
    assert replay_calls == replay_fresh == []


@pytest.mark.parametrize("field", AUTHORITY_FIELDS)
def test_coherent_event_authority_replacement_before_admission_has_no_provider_call(tmp_path, field):
    path = tmp_path / "live.db"
    event = None

    def replace(_symbol):
        _coherent_replacement(path, event, field)

    worker, calls, _ = _worker(path, on_fresh=replace)
    event = worker.evaluate(observation(), NOW)[0]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["state"] != "DONE"
    assert receipt["analysis_admission_hash"] == ""
    assert calls == []


@pytest.mark.parametrize("field", AUTHORITY_FIELDS)
def test_replacement_after_last_pre_admission_check_is_rejected_by_mint(tmp_path, monkeypatch, field):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    original = worker._mint_analysis_admission

    def replace_just_before_mint(*args, **kwargs):
        _coherent_replacement(path, event, field)
        return original(*args, **kwargs)

    monkeypatch.setattr(worker, "_mint_analysis_admission", replace_just_before_mint)
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert calls == []
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["state"] != "DONE"
    assert receipt["analysis_admission_hash"] == ""


def test_archival_replacement_after_mint_preserves_provider_case_and_blocks_done(tmp_path, monkeypatch):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    expected_case = position_case_from_event(market_case(), event)
    original = worker._mint_analysis_admission

    def replace_after_mint(*args, **kwargs):
        admission = original(*args, **kwargs)
        _coherent_replacement(path, event)
        return admission

    monkeypatch.setattr(worker, "_mint_analysis_admission", replace_after_mint)
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert [case.canonical_json() for case in calls] == [expected_case.canonical_json()]
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["analysis_admission_hash"]
    assert receipt["state"] != "DONE"
    assert receipt["analysis_completed"] == 0


def test_archival_replacement_during_analysis_preserves_provider_case_and_blocks_done(tmp_path):
    path = tmp_path / "live.db"
    event = None

    async def replace_during_analysis(_case):
        _coherent_replacement(path, event)

    worker, calls, _ = _worker(path, on_analysis=replace_during_analysis)
    event = worker.evaluate(observation(), NOW)[0]
    expected_case = position_case_from_event(market_case(), event)
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert [case.canonical_json() for case in calls] == [expected_case.canonical_json()]
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["analysis_admission_hash"]
    assert receipt["state"] != "DONE"
    assert receipt["analysis_completed"] == 0


@pytest.mark.parametrize("field", [
    "dispatch_authority_json", "dispatch_authority_hash", "analysis_admission_hash",
    "position_case_id", "position_case_hash", "position_case_json", "case_hash",
])
def test_admitted_receipt_fields_are_immutable_in_normal_sqlite(tmp_path, field):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    assert len(asyncio.run(worker.drain_pending_dispatches(NOW))) == 1
    assert len(calls) == 1
    with connection(path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            f"UPDATE live_position_case_dispatches SET {field}=? WHERE event_id=?",
            ("tampered", event.event_id),
        )
    with connection(path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM live_position_case_dispatches WHERE event_id=?", (event.event_id,))


@pytest.mark.parametrize("field", [
    "dispatch_authority_json", "dispatch_authority_hash", "analysis_admission_hash",
    "position_case_id", "position_case_json", "position_case_hash", "case_hash",
])
def test_bypassed_admission_or_case_tamper_cannot_reach_done(tmp_path, field):
    path = tmp_path / "live.db"
    event = None

    async def tamper_during_provider(_case):
        with connection(path) as db:
            _drop_dispatch_fence(db)
            changed = db.execute(
                f"UPDATE live_position_case_dispatches SET {field}=? WHERE event_id=?",
                ("tampered", event.event_id),
            )
            assert changed.rowcount == 1
            assert db.execute(
                f"SELECT {field} FROM live_position_case_dispatches WHERE event_id=?",
                (event.event_id,),
            ).fetchone()[field] == "tampered"

    worker, calls, _ = _worker(path, on_analysis=tamper_during_provider)
    event = worker.evaluate(observation(), NOW)[0]
    expected_case = position_case_from_event(market_case(), event)
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert [case.canonical_json() for case in calls] == [expected_case.canonical_json()]
    receipt = worker.get_dispatch(event.event_id)
    assert receipt[field] == "tampered"
    assert receipt["state"] != "DONE"
    assert receipt["analysis_completed"] == 0


def test_bypassed_case_substitution_after_mint_cannot_change_provider_input(tmp_path, monkeypatch):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    original_case = position_case_from_event(market_case(), event)
    base_values = market_case().model_dump(mode="python", exclude={"case_hash"})
    base_values["evidence_id"] = "e" * 64
    alternate_case = position_case_from_event(CasePackageV1.build(**base_values), event)
    assert alternate_case.case_hash != original_case.case_hash
    mint = worker._mint_analysis_admission

    def substitute_after_mint(*args, **kwargs):
        admission = mint(*args, **kwargs)
        with connection(path) as db:
            _drop_dispatch_fence(db)
            changed = db.execute(
                "UPDATE live_position_case_dispatches SET position_case_id=?, position_case_hash=?, "
                "position_case_json=?, case_hash=? WHERE event_id=?",
                (alternate_case.case_id, alternate_case.case_hash,
                 alternate_case.canonical_json(), alternate_case.case_hash, event.event_id),
            )
            assert changed.rowcount == 1
            assert db.execute(
                "SELECT position_case_json FROM live_position_case_dispatches WHERE event_id=?",
                (event.event_id,),
            ).fetchone()["position_case_json"] == alternate_case.canonical_json()
        return admission

    monkeypatch.setattr(worker, "_mint_analysis_admission", substitute_after_mint)
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert all(case.canonical_json() == original_case.canonical_json() for case in calls)
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["position_case_json"] == alternate_case.canonical_json()
    assert receipt["state"] != "DONE"
    assert receipt["analysis_completed"] == 0


def test_normal_admission_is_canonical_and_exactly_once(tmp_path):
    path = tmp_path / "live.db"
    admitting_tokens = []
    async def capture_lease(_case):
        with connection(path) as db:
            admitting_tokens.append(db.execute(
                "SELECT lease_token FROM live_position_case_dispatches WHERE event_id=?",
                (event.event_id,),
            ).fetchone()["lease_token"])

    worker, calls, fresh = _worker(path, on_analysis=capture_lease)
    event = worker.evaluate(observation(), NOW)[0]
    completed = asyncio.run(worker.drain_pending_dispatches(NOW))
    assert len(completed) == 1
    assert len(calls) == 1
    assert fresh == [event.symbol]
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["state"] == "DONE"
    assert receipt["analysis_completed"] == 1
    assert len(admitting_tokens) == 1 and admitting_tokens[0]
    _assert_receipt_identity(event, receipt, calls[0], admitting_tokens[0])
    identity = (receipt["dispatch_authority_json"], receipt["dispatch_authority_hash"],
                receipt["analysis_admission_hash"])
    assert asyncio.run(worker.drain_pending_dispatches(NOW + 1000)) == ()
    assert len(calls) == 1
    later = worker.get_dispatch(event.event_id)
    assert identity == (later["dispatch_authority_json"], later["dispatch_authority_hash"],
                        later["analysis_admission_hash"])


def test_terminal_update_abort_rolls_back_done_and_completion_marker(tmp_path):
    path = tmp_path / "live.db"
    event = None

    async def abort_after_terminal_update(_case):
        with connection(path) as db:
            db.execute("""
                CREATE TRIGGER abort_r7_terminal_update
                AFTER UPDATE ON live_position_case_dispatches
                FOR EACH ROW WHEN NEW.event_id = OLD.event_id
                    AND NEW.state = 'DONE' AND NEW.analysis_completed = 1
                BEGIN
                    SELECT RAISE(ABORT, 'R7_SIMULATED_TERMINAL_ABORT');
                END
            """)

    worker, provider_calls, _ = _worker(path, on_analysis=abort_after_terminal_update)
    event = worker.evaluate(observation(), NOW)[0]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert len(provider_calls) == 1
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["analysis_admission_hash"]
    assert receipt["state"] == "FAILED_CLOSED"
    assert receipt["analysis_completed"] == 0
    with connection(path) as db:
        row = db.execute(
            "SELECT state, analysis_completed FROM live_position_case_dispatches WHERE event_id=?",
            (event.event_id,),
        ).fetchone()
        assert tuple(row) == ("FAILED_CLOSED", 0)


def test_stale_unexpired_lease_does_not_create_admission_or_call(tmp_path):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute(
            "UPDATE live_position_case_dispatches SET state='DISPATCHING', lease_token='other', "
            "lease_expires_at_ms=? WHERE event_id=?", (NOW + 60_000, event.event_id),
        )
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert calls == []
    assert worker.get_dispatch(event.event_id)["analysis_admission_hash"] == ""


def test_superseded_admitted_lease_cannot_complete_or_create_another_admission(tmp_path):
    path = tmp_path / "live.db"
    event = None

    async def supersede_during_provider(_case):
        with connection(path) as db:
            db.execute(
                "UPDATE live_position_case_dispatches SET lease_token='superseding-owner', "
                "lease_expires_at_ms=? WHERE event_id=?",
                (NOW - 1, event.event_id),
            )

    worker, calls, _ = _worker(path, on_analysis=supersede_during_provider)
    event = worker.evaluate(observation(), NOW)[0]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert len(calls) == 1
    first = worker.get_dispatch(event.event_id)
    assert first["state"] != "DONE"
    assert first["analysis_admission_hash"]
    assert first["analysis_completed"] == 0
    restarted, retry_calls, _ = _worker(path)
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 1)) == ()
    final = restarted.get_dispatch(event.event_id)
    assert final["state"] == "FAILED_CLOSED"
    assert final["analysis_admission_hash"] == first["analysis_admission_hash"]
    assert final["analysis_completed"] == 0
    assert retry_calls == []


def test_unadmitted_frozen_retry_uses_original_case_and_single_admission(tmp_path):
    path = tmp_path / "live.db"
    admitting_tokens = []
    async def capture_lease(_case):
        with connection(path) as db:
            admitting_tokens.append(db.execute(
                "SELECT lease_token FROM live_position_case_dispatches WHERE event_id=?",
                (event.event_id,),
            ).fetchone()["lease_token"])

    worker, calls, fresh = _worker(path, on_analysis=capture_lease)
    event = worker.evaluate(observation(), NOW)[0]
    frozen = position_case_from_event(market_case(), event)
    with connection(path) as db:
        db.execute(
            "UPDATE live_position_case_dispatches SET position_case_id=?, position_case_hash=?, "
            "position_case_json=?, case_hash=? WHERE event_id=?",
            (frozen.case_id, frozen.case_hash, frozen.canonical_json(), frozen.case_hash,
             event.event_id),
        )
    assert len(asyncio.run(worker.drain_pending_dispatches(NOW))) == 1
    assert fresh == []
    assert [case.canonical_json() for case in calls] == [frozen.canonical_json()]
    receipt = worker.get_dispatch(event.event_id)
    assert receipt["state"] == "DONE"
    assert len(admitting_tokens) == 1 and admitting_tokens[0]
    _assert_receipt_identity(event, receipt, frozen, admitting_tokens[0])


def test_completed_receipt_replay_preserves_admission_without_provider_recall(tmp_path):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    assert len(asyncio.run(worker.drain_pending_dispatches(NOW))) == 1
    assert len(calls) == 1
    original = worker.get_dispatch(event.event_id)
    assert original["analysis_completed"] == 1
    with connection(path) as db:
        db.execute(
            "UPDATE live_position_case_dispatches SET state='DISPATCHING', "
            "lease_token='expired-replay', lease_expires_at_ms=? WHERE event_id=?",
            (NOW - 1, event.event_id),
        )
    restarted, replay_calls, replay_fresh = _worker(path)
    completed = asyncio.run(restarted.drain_pending_dispatches(NOW + 1))
    assert len(completed) == 1
    assert replay_calls == replay_fresh == []
    receipt = restarted.get_dispatch(event.event_id)
    assert receipt["state"] == "DONE"
    assert receipt["analysis_completed"] == 1
    for field in ("dispatch_authority_json", "dispatch_authority_hash", "analysis_admission_hash",
                  "position_case_json"):
        assert receipt[field] == original[field]


@pytest.mark.parametrize("round_number", range(20))
def test_concurrent_r6_to_r7_constructors_upgrade_once(tmp_path, round_number):
    path = tmp_path / "live.db"
    PositionSupervisor(path)
    with connection(path) as db:
        db.execute("DROP TRIGGER trg_live_position_dispatch_admission_immutable")
        db.execute("DROP TRIGGER trg_live_position_analysis_completion_guard")
        db.execute("DROP TRIGGER trg_live_position_dispatch_blank_insert")
        db.execute("DROP TRIGGER trg_live_position_dispatch_done_requires_completion")
        for column in ("analysis_completed", "analysis_admission_hash",
                       "dispatch_authority_hash", "dispatch_authority_json"):
            db.execute(f"ALTER TABLE live_position_case_dispatches DROP COLUMN {column}")

    start = threading.Barrier(12)

    def start_supervisor(_number):
        start.wait(timeout=10)
        PositionSupervisor(path)

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(start_supervisor, number) for number in range(12)]
        errors = [future.exception(timeout=20) for future in futures]

    assert errors == [None] * 12
    with connection(path) as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(live_position_case_dispatches)")}
    assert {"dispatch_authority_json", "dispatch_authority_hash",
            "analysis_admission_hash", "analysis_completed"} <= columns
