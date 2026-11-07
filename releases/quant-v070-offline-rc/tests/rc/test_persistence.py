from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.rc_dashboard import snapshot, write_snapshot
from btc_quant_agent.platform.rc_fixture import DECISION, TRIGGER, future_fixture, wire
from btc_quant_agent.platform.rc_observe import advance_episode
from btc_quant_agent.platform.rc_operator import recover
from btc_quant_agent.platform.rc_source import admit_stream, normalize
from btc_quant_agent.platform.rc_store import InjectedCrash, RCStore, TERMINAL
from btc_quant_agent.platform.swing import INTERVALS


def test_idempotent_replay_and_readonly_restart_preserve_terminal_status(stored, positive):
    digest = stored.commit(positive)
    stored.transition(positive.episode_id, 0, "EXPIRED", DECISION + 86400000, "ORIGINAL_EXPIRY")
    before = hashlib.sha256(stored.path.read_bytes()).hexdigest()
    assert stored.commit(positive) == digest
    assert hashlib.sha256(stored.path.read_bytes()).hexdigest() == before
    restarted = RCStore(stored.path, readonly=True)
    assert restarted.verify() == {"receipts": 164, "decisions": 1, "episodes": 1, "observations": 0, "stops": []}
    assert restarted.episode(positive.episode_id)["state"]["status"] == "EXPIRED"
    assert fingerprint(restarted.decisions()[0].model_dump(mode="json")) == digest
    assert hashlib.sha256(stored.path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("terminal", sorted(TERMINAL))
def test_terminal_lifecycle_is_immutable_without_age_reset(terminal, stored, positive):
    identity = positive.episode_id
    e = stored.transition(identity, 0, terminal, DECISION + 1000, terminal)
    assert e["revision"] == 1
    with pytest.raises(ValueError, match="TERMINAL"):
        stored.transition(identity, 1, "ARMED", DECISION + 2000, "REACTIVATE")
    assert stored.commit(positive)
    assert stored.episode(identity) == e


def test_lifecycle_cas_time_and_direction_do_not_regress(stored, positive):
    with pytest.raises(ValueError, match="REVISION"):
        stored.transition(positive.episode_id, 5, "EXPIRED", DECISION, "STALE_WRITER")
    with pytest.raises(ValueError, match="TIME_REGRESSION"):
        stored.transition(positive.episode_id, 0, "EXPIRED", DECISION - 1, "OLD_CLOCK")
    with pytest.raises(ValueError, match="TRANSITION"):
        stored.transition(positive.episode_id, 0, "WATCH", DECISION, "DOWNGRADE")


def test_revision_cancels_open_episode_and_cannot_rewrite_decision(stored, positive, btc_rows):
    r = next(r for r in reversed(btc_rows) if r.bar.candle.interval == "4H")
    revised = normalize(wire(replace(r.bar.candle, high=r.bar.candle.high + 1), revision=1,
                             at_ms=DECISION + 1000))
    stored.admit([revised])
    assert stored.episode(positive.episode_id)["state"]["status"] == "CANCELED"
    e = advance_episode(stored, positive.episode_id, now_ms=DECISION + 2000)
    assert e["state"]["status"] == "CANCELED"
    assert stored.decisions() == (positive,)
    assert stored.commit(positive)
    assert stored.episode(positive.episode_id) == e


def test_later_stop_no_chase_and_expiry_are_explicit(tmp_path, btc_rows, positive):
    for scenario, expected in [("stop", "INVALIDATED"), ("missed", "NO_CHASE"), ("time", "EXPIRED")]:
        store = RCStore(tmp_path / (scenario + ".sqlite"))
        store.admit(btc_rows)
        store.commit(positive)
        hours = 25 if scenario == "time" else 10
        store.admit(future_fixture(positive, scenario=scenario, hours=hours))
        now = DECISION + hours * INTERVALS["1H"]
        assert advance_episode(store, positive.episode_id, now_ms=now)["state"]["status"] == expected


@pytest.mark.parametrize("kind", ["receipt", "decision"])
@pytest.mark.parametrize("when", ["before", "after"])
def test_real_subprocess_crash_at_durable_boundaries(kind, when, tmp_path):
    path = tmp_path / "crash.sqlite"
    script = "\n".join([
        "from btc_quant_agent.platform.rc_fixture import fixture,TRIGGER,DECISION",
        "from btc_quant_agent.platform.rc_store import RCStore",
        "rows=tuple(r for r in fixture() if r.bar.candle.symbol=='BTCUSDT')",
        f"store=RCStore({str(path)!r})",
        f"store.admit(rows,crash={'kill_'+when+'_receipt_commit' if kind == 'receipt' else None!r})",
        "d=store.compile('BTCUSDT',TRIGGER,DECISION)",
        f"store.commit(d,crash={'kill_'+when+'_decision_commit' if kind == 'decision' else None!r})",
    ])
    package_path = str(Path(__file__).resolve().parents[2] / "src")
    child_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                 "PYTHONPATH": package_path + os.pathsep + os.environ.get("PYTHONPATH", "")}
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env=child_env, timeout=30)
    assert result.returncode == 73, result.stderr
    recovered = RCStore(path)
    counts = recovered.verify()
    assert counts["receipts"] == (0 if kind == "receipt" and when == "before" else 164)
    assert counts["decisions"] == (1 if kind == "decision" and when == "after" else 0)
    rows = tuple(r for r in __import__("btc_quant_agent.platform.rc_fixture", fromlist=["fixture"]).fixture()
                 if r.bar.candle.symbol == "BTCUSDT")
    recovered.admit(rows)
    d = recovered.compile("BTCUSDT", TRIGGER, DECISION)
    digest = recovered.commit(d)
    assert recovered.commit(d) == digest
    assert recovered.verify()["decisions"] == 1


def test_partial_snapshot_and_orphan_temp_recover_from_durable_state(stored, tmp_path):
    value = snapshot(stored, now_ms=DECISION)
    with pytest.raises(InjectedCrash):
        write_snapshot(tmp_path, value, crash="after_snapshot_json")
    assert (tmp_path / "latest.json").exists() and not (tmp_path / "latest.html").exists()
    (tmp_path / ".latest.json.orphan.part").write_text('{"torn":')
    result = recover(tmp_path)
    assert result["snapshot_sha256"] == value["snapshot_sha256"]
    assert value["snapshot_sha256"] in (tmp_path / "latest.html").read_text()
    assert json.loads((tmp_path / "latest.json").read_text()) == value
    assert (tmp_path / ".latest.json.orphan.part").exists()  # Preserve fault evidence.


def test_queue128_overflow_stops_without_admitted_loss(tmp_path, btc_rows):
    store = RCStore(tmp_path / "queue.sqlite")
    with pytest.raises(ValueError, match="QUEUE128"):
        admit_stream(store, btc_rows, burst=129)
    assert store.verify()["receipts"] == 0
    assert store.stopped() == ("QUEUE128_EXHAUSTED_STICKY",)
    assert store.compile("BTCUSDT", TRIGGER, DECISION).market_state == "SOURCE_BLOCKED"
    with pytest.raises(ValueError, match="STICKY"):
        store.admit(btc_rows)


def test_conflicting_identity_and_out_of_order_admission_fail_closed(tmp_path, btc_rows):
    store = RCStore(tmp_path / "conflict.sqlite")
    store.admit(btc_rows)
    r = btc_rows[0]
    changed = normalize(wire(replace(r.bar.candle, high=r.bar.candle.high + 1)))
    with pytest.raises(ValueError, match="CONFLICT"):
        store.admit([changed])
    assert store.verify()["receipts"] == len(btc_rows)
    assert store.stopped()
    other = RCStore(tmp_path / "order.sqlite")
    with pytest.raises(ValueError, match="OUT_OF_ORDER"):
        other.admit(list(reversed(btc_rows)))
    assert other.verify()["receipts"] == 0


def test_injected_storage_write_denial_rolls_back_and_stops(tmp_path, btc_rows, monkeypatch):
    store = RCStore(tmp_path / "write_denied.sqlite")
    original = store.connect

    @contextmanager
    def denied_receipt_insert():
        with original() as db:
            db.set_authorizer(lambda action, table, *_: sqlite3.SQLITE_DENY
                              if action == sqlite3.SQLITE_INSERT and table == "rc_receipts" else sqlite3.SQLITE_OK)
            yield db

    monkeypatch.setattr(store, "connect", denied_receipt_insert)
    with pytest.raises(sqlite3.DatabaseError):
        store.admit(btc_rows)
    assert store.verify()["receipts"] == 0 and store.stopped()


def test_queue_and_sqlite_contention_preserve_all_unique_admissions(tmp_path, btc_rows):
    store = RCStore(tmp_path / "contention.sqlite")
    locked, release = threading.Event(), threading.Event()

    def writer():
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            locked.set()
            release.wait(2)

    thread = threading.Thread(target=writer)
    thread.start()
    assert locked.wait(2)
    timer = threading.Timer(0.03, release.set)
    timer.start()
    started = time.perf_counter()
    assert admit_stream(store, btc_rows) == len(btc_rows)
    elapsed = time.perf_counter() - started
    thread.join(2)
    timer.join(2)
    assert elapsed >= 0.025
    assert admit_stream(store, btc_rows) == 0
    assert store.verify()["receipts"] == len(btc_rows)


@pytest.mark.parametrize("target", ["receipt", "decision", "watermark", "episode", "transition"])
def test_persisted_evidence_tampering_is_detected(target, stored, positive):
    queries = {"receipt": "UPDATE rc_receipts SET digest='tampered'",
               "decision": "UPDATE rc_decisions SET digest='tampered'",
               "watermark": "UPDATE rc_watermarks SET prefix_digest='tampered'",
               "episode": "UPDATE rc_episodes SET digest='tampered'",
               "transition": "UPDATE rc_transitions SET digest='tampered'"}
    with stored.connect() as db:
        db.execute(queries[target])
    with pytest.raises(ValueError):
        stored.verify()


def test_readonly_store_cannot_mutate(stored):
    readonly = RCStore(stored.path, readonly=True)
    with pytest.raises(ValueError, match="READ_ONLY"):
        readonly.stop("NO_WRITE")


def test_sqlite_page_ceiling_covers_every_write_and_full_quota_fails_closed(tmp_path, btc_rows, monkeypatch):
    store = RCStore(tmp_path / "quota.sqlite")
    with store.connect() as db:
        limit = db.execute("PRAGMA max_page_count").fetchone()[0]
        size = db.execute("PRAGMA page_size").fetchone()[0]
        assert limit * size <= 67108864
    original = store.connect

    @contextmanager
    def full_quota():
        with original() as db:
            current = db.execute("PRAGMA page_count").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={current}")
            yield db

    monkeypatch.setattr(store, "connect", full_quota)
    # Valid JSON whitespace enlarges a legal immutable raw receipt without inventing fields.
    large = normalize(" " * 200000 + btc_rows[0].raw)
    with pytest.raises(sqlite3.OperationalError) as error:
        store.admit([large])
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_FULL
    assert store.verify()["receipts"] == 0 and store.stopped()


def test_restart_reconciles_revision_committed_before_lifecycle_crash(stored, positive, btc_rows, tmp_path):
    r = next(r for r in reversed(btc_rows) if r.bar.candle.interval == "4H")
    revision = normalize(wire(replace(r.bar.candle, high=r.bar.candle.high + 1), revision=1,
                              at_ms=DECISION + 1000))
    with pytest.raises(InjectedCrash):
        stored.admit([revision], crash="after_receipt_commit")
    value = snapshot(stored, now_ms=DECISION + 2000)
    assert "SOURCE_BLOCKED" in __import__("btc_quant_agent.platform.ui", fromlist=["page"]).page(value, now_ms=DECISION + 2000)
    recover(tmp_path)
    assert RCStore(stored.path, readonly=True).episode(positive.episode_id)["state"]["status"] == "CANCELED"
