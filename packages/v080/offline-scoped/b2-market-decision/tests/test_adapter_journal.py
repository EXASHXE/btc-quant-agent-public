from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from quant_personal_public_b1.store import encode as b1_encode
from quant_personal_public_b1.store import sha
from test_strategy import SYMBOL, after, system

from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
from quant_personal_decision_b2.fixtures import AFTER_TRIGGER
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import MINUTE, DecisionError, encode


def tamper(path, scan, fn):
    with sqlite3.connect(path) as db:
        raw = db.execute("SELECT payload FROM publications WHERE scan_id=?", (scan,)).fetchone()[0]
        item = json.loads(raw)
        fn(item)
        changed = b1_encode(item)
        db.execute("UPDATE publications SET payload=?,sha256=? WHERE scan_id=?", (changed, sha(changed.encode()), scan))


def test_accepted_b1_original_committed_demo_read_without_changes():
    work = Path(__file__).resolve().parents[1]
    from pathlib import Path as _Path
    override = os.environ.get("B2_ACCEPTED_B1_DB")
    root = _Path(override) if override else (
        work.parent / "lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01" / "evidence/demo/fixture.sqlite"
    )
    before = sha(root.read_bytes())
    adapter = MarketSnapshotAdapter(root, "fixture")
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        for scan in (1, 2):
            m = adapter.read(symbol, scan=scan)
            assert m.warm and m.source["source_scan_id"] == scan
            assert len(m.source["raw_receipts"]) >= 10
    assert sha(root.read_bytes()) == before


@pytest.mark.parametrize("name", ["quote", "mark", "depth", "oi"])
def test_a_later_committed_context_cannot_be_spliced_into_early_scan(tmp_path, name):
    source, engine = system(tmp_path)
    earlier = engine.adapter.read(SYMBOL)
    second = source.scan(AFTER_TRIGGER)
    later = second["markets"][SYMBOL]["context"][name]

    def mutate(raw):
        raw["markets"][SYMBOL]["context"][name] = later

    tamper(source.path, 1, mutate)
    with pytest.raises(DecisionError, match="LATE_SOURCE_SCAN"):
        engine.adapter.read(SYMBOL, scan=1, as_of_ms=earlier.evaluated_ms)


def test_asof_at_candle_cutoff_has_no_future_publication(tmp_path):
    source, engine = system(tmp_path)
    initial = engine.adapter.read(SYMBOL)
    assert initial.context["quote"]["received_venue_upper_ms"] > initial.cutoff_ms
    with pytest.raises(DecisionError, match="NO_DURABLE_PUBLICATION_AS_OF"):
        engine.adapter.read(SYMBOL, as_of_ms=initial.cutoff_ms)
    with pytest.raises(DecisionError, match="LATE_SOURCE_PUBLICATION"):
        engine.adapter.read(SYMBOL, scan=1, as_of_ms=initial.cutoff_ms)
    assert engine.adapter.read(SYMBOL, as_of_ms=initial.evaluated_ms) == initial
    missed = engine.evaluate(SYMBOL, as_of_ms=initial.cutoff_ms)
    assert missed["market_status"] == "SOURCE_BLOCKED" and missed["evaluation_receipt"] is None
    assert engine.evaluate(SYMBOL)["market_status"] == "WATCH"
    assert source.path.exists()


@pytest.mark.parametrize("fault,reason", [
    ("missing", "MISSING_FRAME"), ("gap", "CANDLE_GAP_OR_DUPLICATE"),
    ("duplicate", "CANDLE_GAP_OR_DUPLICATE"), ("forming", "CANDLE_NOT_FINAL"),
    ("ohlc", "CANDLE_RAW_MISMATCH"), ("clock", "CLOCK_RECONCILIATION_MISMATCH"),
    ("role", "UNQUALIFIED_SOURCE_STATE"), ("raw_quote", "CONTEXT_RAW_MISMATCH"),
    ("durable_quote", "SOURCE_DURABILITY_BINDING"), ("wire", "SOURCE_RECEIPT_BINDING"),
])
def test_adapter_does_not_trust_even_rehashed_snapshots(tmp_path, fault, reason):
    source, engine = system(tmp_path)

    def corrupt(item):
        m = item["markets"][SYMBOL]
        seq = m["frames"]["15m"]["completed"]
        if fault == "missing":
            m["frames"].pop("4h")
        elif fault == "gap":
            seq.pop(2)
        elif fault == "duplicate":
            seq[1] = seq[0]
        elif fault == "forming":
            seq[-1]["finality"] = "FORMING"
        elif fault == "ohlc":
            seq[-1]["close"] = "23"
        elif fault == "clock":
            r = item["clock"]["reconciled"]
            r["monotonic_ms"] += 1
        elif fault == "role":
            m["strategy_status"] = "NO_SETUP"
        elif fault == "raw_quote":
            m["context"]["quote"]["values"]["bidPrice"] = "123"
        elif fault == "durable_quote":
            m["context"]["quote"]["first_durable_availability"]["monotonic_ms"] -= 1
        elif fault == "wire":
            m["context"]["quote"]["receipt_id"] = m["context"]["mark"]["receipt_id"]
        else:
            raise AssertionError(fault)

    tamper(source.path, 1, corrupt)
    with pytest.raises(DecisionError, match=reason):
        engine.adapter.read(SYMBOL)


def test_replay_checks_age_at_requested_time_not_only_source_state(tmp_path):
    _, engine = system(tmp_path)
    snapshot = engine.adapter.read(SYMBOL)
    with pytest.raises(DecisionError, match="CONTEXT_STALE_OR_PARTIAL: quote"):
        engine.adapter.read(SYMBOL, scan=1, as_of_ms=snapshot.evaluated_ms + 6000)


def test_real_origin_and_wrong_schema_database_are_rejected(tmp_path):
    src, _ = system(tmp_path)
    with pytest.raises(DecisionError, match="UNQUALIFIED_SOURCE_ORIGIN"):
        MarketSnapshotAdapter(src.path, "genuine")
    with pytest.raises(DecisionError, match="UNQUALIFIED_SOURCE_STORE"):
        MarketSnapshotAdapter(src.path, "loopback")
    tamper(src.path, 1, lambda v: v.update(source_origin="GENUINE_PUBLIC_V2"))
    with pytest.raises(DecisionError, match="SOURCE_EVIDENCE_INVALID"):
        MarketSnapshotAdapter(src.path, "fixture").read(SYMBOL)


def test_manual_idempotence_and_no_fill_claim(tmp_path):
    _, engine = system(tmp_path)
    a = engine.evaluate(SYMBOL)
    args = dict(card_id=a["card_id"], operator_id="op_01", action="INTENDED_ACTION", time_ms=a["evaluated_ms"] + 10,
                note="Fixture-only intention.")
    manual = engine.journal.manual(**args)
    reopened = Journal(engine.journal.path)
    assert reopened.manual(**args) == manual
    assert manual["evidence"] == "OWNER_ENTERED" and manual["exchange_fill_status"] == "UNKNOWN"
    assert [e["evidence"] for e in reopened.events() if e["kind"] == "MANUAL"] == ["OWNER_ENTERED"]
    with pytest.raises(DecisionError, match="OPERATOR_IDEMPOTENCY_CONFLICT"):
        reopened.manual(**{**args, "note": "different"})
    with pytest.raises(DecisionError, match="INVALID_OPERATOR_EVENT"):
        reopened.manual(**{**args, "action": "FILL"})
    with reopened.connect(write=True) as db, pytest.raises(sqlite3.IntegrityError, match="B2_APPEND_ONLY"):
        db.execute("DELETE FROM cards")
    assert encode(reopened.read(card_id=a["card_id"])) == encode(a)


def test_child_crash_after_staging_rolls_back_and_restart_replays(tmp_path):
    source, engine = system(tmp_path)
    first = engine.evaluate(SYMBOL)
    source.scan(AFTER_TRIGGER)
    child = """
import os,sys
from pathlib import Path
from quant_personal_decision_b2.model import DEFAULT_POLICY
from quant_personal_decision_b2.engine import Engine
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
a=MarketSnapshotAdapter(Path(sys.argv[1]),'fixture')
j=Journal(Path(sys.argv[2]),create=True,policy=DEFAULT_POLICY)
Engine(a,j).evaluate('BTCUSDT',before_commit=lambda:os._exit(63))
"""
    result = subprocess.run([sys.executable, "-B", "-c", child, str(source.path), str(engine.journal.path)],
                            capture_output=True, check=False, timeout=20)
    assert result.returncode == 63, result.stderr.decode()
    reopened = Journal(engine.journal.path)
    assert reopened.read() == first and len(reopened.events()) == 3
    new = engine.evaluate(SYMBOL)
    assert new["market_status"] == "EXECUTABLE"
    assert new["episode_id"] == first["episode_id"]
    assert reopened.read(card_id=new["card_id"]) == new
    assert len(reopened.events()) == 6
    if dest := os.environ.get("B2_CRASH_EVIDENCE"):
        Path(dest).write_text(json.dumps({
            "synthetic": True, "controlled_process_exit": 63, "rollback_previous_card": first["card_id"],
            "prior_event_count": 3, "restart_event_count": 6, "new_card": new["card_id"],
            "same_episode": True, "reopen_match": True, "no_duplicate_trigger": True,
        }, indent=2) + "\n")


def test_venue_restriction_is_global_overlay_without_erasing_structure(tmp_path):
    from quant_personal_public_b1.fixture import fixture_reply
    from quant_personal_public_b1.policy import TIME

    source, engine = system(tmp_path)
    engine.evaluate(SYMBOL)
    first = after(source, engine)
    original = source.transport.mutate

    def reject(route, params, value):
        if route == TIME:
            return fixture_reply({"msg": "restricted location"}, status=451)
        return original(route, params, value)

    source.transport.mutate = reject
    snapshot = source.scan(AFTER_TRIGGER + 5 * MINUTE + 1000)
    now = first["evaluated_ms"] + 5 * MINUTE + 1000
    blocked = engine.evaluate(SYMBOL, scan=snapshot["scan_id"], as_of_ms=now, reprice_minutes=5,
                              episode_id=first["episode_id"])
    assert blocked["market_status"] == "SOURCE_BLOCKED" and blocked["source_issue"]["detail"] == "HTTP_451"
    assert blocked["trigger"] == first["trigger"] and blocked["episode_state"] == first["episode_state"]
    assert not blocked["rejected_publication"]["usable_for_evaluation"]
    assert engine.journal.read(card_id=first["card_id"]) == first


def test_genuine_b1_gate_remains_dormant_under_synthetic_env(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANT_LIVE", "1")
    monkeypatch.setenv("ENABLE_TRADE", "1")
    monkeypatch.setenv("BINANCE_API_KEY", "synthetic")
    proc = subprocess.run([sys.executable, "-B", "-m", "quant_personal_public_b1", "live"],
                          capture_output=True, check=False, timeout=15)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["error"] == "LIVE_CAPABILITY_DORMANT"
    assert not list(tmp_path.iterdir())
