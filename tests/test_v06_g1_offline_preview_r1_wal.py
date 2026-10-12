"""Isolated durability, idempotency and no-network negative witnesses."""

from __future__ import annotations

import ast
import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.g1_offline_preview_r1.fixtures import make_fixture
from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.storage import Engine, strict_json


def init():
    return initial_state(make_fixture()["trusted_approvals"])


def one():
    return make_fixture()["events"][0]


@pytest.mark.parametrize("edge", ["before_append", "after_append", "after_fsync", "after_snapshot"])
def test_crash_boundaries_replay_once(tmp_path, edge):
    def die(actual, event):
        if actual == edge:
            raise RuntimeError("synthetic process interruption")

    with Engine(tmp_path, init(), temporary=True) as engine, pytest.raises(RuntimeError):
        engine.apply(one(), hook=die)
    with Engine(tmp_path, init(), temporary=True) as engine:
        engine.apply(one())
        assert engine.seq == 1 and len(engine.state["used_event_ids"]) == 1


def test_duplicate_same_event_no_wal_cash_change(tmp_path):
    with Engine(tmp_path, init(), temporary=True) as e:
        e.apply(one())
        before = (e.wal.read_bytes(), digest(e.state))
        assert e.apply(one()) == "IDEMPOTENT_DUPLICATE"
        assert (e.wal.read_bytes(), digest(e.state)) == before


def test_reused_id_changed_body_fails(tmp_path):
    with Engine(tmp_path, init(), temporary=True) as e:
        e.apply(one())
        bad = copy.deepcopy(one())
        bad["payload"]["mark_close"] = "30008"
        before = e.wal.read_bytes()
        with pytest.raises(SafetyViolation, match="EVENT_REUSE_DRIFT"):
            e.apply(bad)
        assert e.wal.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    ["truncated", "malformed", "hash", "sequence", "state", "genesis", "duplicatekey", "nonfinite"],
)
def test_wal_tamper_quarantine_no_ready_state(tmp_path, damage):
    with Engine(tmp_path, init(), temporary=True) as e:
        e.apply(one())
    p = tmp_path / "events.wal.jsonl"
    lines = p.read_text().splitlines()
    if damage == "truncated":
        p.write_text("\n".join(lines) + '\n{"')
    elif damage == "malformed":
        p.write_text(lines[0] + "\nnot-json\n")
    elif damage == "duplicatekey":
        p.write_text(lines[0] + '\n{"seq":1,"seq":2}\n')
    elif damage == "nonfinite":
        p.write_text(lines[0] + '\n{"seq":NaN}\n')
    elif damage == "genesis":
        p.write_text('{"format":"G1_OFFLINE_WAL_V1","genesis_hash":"tampered"}\n')
    else:
        record = json.loads(lines[1])
        field = {"hash": "record_hash", "sequence": "seq", "state": "state_hash"}[damage]
        record[field] = 99 if field == "seq" else "bad"
        p.write_text(lines[0] + "\n" + json.dumps(record) + "\n")
    with pytest.raises(SafetyViolation):
        Engine(tmp_path, init(), temporary=True)
    assert list((tmp_path / "quarantine").glob("*.json"))


def test_checkpoint_mutation_rejected(tmp_path):
    with Engine(tmp_path, init(), temporary=True) as e:
        e.apply(one())
        e.checkpoint()
    q = next((tmp_path / "checkpoints").glob("checkpoint-*.json"))
    q.chmod(0o600)
    data = json.loads(q.read_text())
    data["state"]["cash"] = "2000"
    q.write_text(json.dumps(data))
    with pytest.raises(SafetyViolation, match="CHECKPOINT_IDENTITY"):
        Engine(tmp_path, init(), temporary=True)


def test_checkpoint_ahead_of_wal_rejected(tmp_path):
    with Engine(tmp_path, init(), temporary=True) as e:
        e.apply(one())
        e.checkpoint()
    p = tmp_path / "events.wal.jsonl"
    p.write_text(p.read_text().splitlines()[0] + "\n")
    with pytest.raises(SafetyViolation, match="CHECKPOINT_AHEAD"):
        Engine(tmp_path, init(), temporary=True)


def test_changed_initial_policy_fail_closed(tmp_path):
    with Engine(tmp_path, init(), temporary=True) as e:
        e.apply(one())
    bad = init()
    bad["trusted_approvals"] = {}
    with pytest.raises(SafetyViolation, match="WAL_GENESIS"):
        Engine(tmp_path, bad, temporary=True)


def test_single_writer_lock(tmp_path):
    with (
        Engine(tmp_path, init(), temporary=True),
        pytest.raises(SafetyViolation, match="SINGLE_WRITER"),
    ):
        Engine(tmp_path, init(), temporary=True)


def test_symlink_output_refused_before_follow(tmp_path):
    dest = tmp_path / "real"
    dest.mkdir()
    link = tmp_path / "link"
    link.symlink_to(dest, target_is_directory=True)
    with pytest.raises(SafetyViolation, match="PATH_SYMLINK"):
        Engine(link, init(), temporary=True)
    assert not list(dest.iterdir())


def test_invalid_event_not_durable_transaction(tmp_path):
    with Engine(tmp_path, init(), temporary=True) as e:
        before = e.wal.read_bytes()
        state = digest(e.state)
        with pytest.raises(SafetyViolation):
            e.apply({"id": "unapproved", "kind": "PLACE", "at": 0, "payload": {}})
        assert e.wal.read_bytes() == before and digest(e.state) == state


@pytest.mark.parametrize("bad", ['{"x":1,"x":2}', '{"a":NaN}', '{"a":Infinity}', "{", "[1,"])
def test_strict_json_rejects(bad):
    with pytest.raises(SafetyViolation):
        strict_json(bad)


def test_import_surface_sealed():
    root = Path(__file__).resolve().parents[1] / "scripts/g1_offline_preview_r1"
    deny = {
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "websockets",
        "binance",
        "openai",
        "google",
        "subprocess",
    }
    for p in root.glob("*.py"):
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [x.name for x in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                assert not any(
                    n.split(".")[0] in deny or n.startswith("btc_quant_agent") for n in names
                ), p.name
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "system",
                    "popen",
                    "connect",
                    "place_order",
                    "cancel_order",
                }, p.name


def test_actual_network_monkeypatch_zero(tmp_path, monkeypatch):
    import socket

    calls = []

    def deny(*args, **kwargs):
        calls.append(True)
        raise AssertionError("network is forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    with Engine(tmp_path, init(), temporary=True) as e:
        for event in make_fixture()["events"][:8]:
            e.apply(event)
    assert calls == []


def test_required_exit_cannot_be_skipped_durably(tmp_path):
    from tests.test_v06_g1_offline_preview_r1_core import ev, next_bar, open_position

    state = next_bar(open_position(), last="100", high="101", low="94")
    with Engine(tmp_path, state, temporary=True) as engine:
        wal = engine.wal.read_bytes()
        before = digest(engine.state)
        with pytest.raises(SafetyViolation, match="REQUIRED_EXIT_UNHANDLED"):
            engine.apply(ev("BAR", state["last_at"] + 60000, {}))
        assert engine.wal.read_bytes() == wal and digest(engine.state) == before
        engine.apply(ev("STOP", state["last_at"], {"fill_id": "flat"}))
        assert Decimal(engine.state["remaining_qty"]) == 0


def test_trace_links_log_state_and_local_outbox(tmp_path):
    fixture = make_fixture()
    with Engine(tmp_path, initial_state(fixture["trusted_approvals"]), temporary=True) as engine:
        for event in fixture["events"][:2]:
            engine.apply(event)
        engine.deliver()
        log = json.loads((tmp_path / "events.log.jsonl").read_text().splitlines()[-1])
        delivery = json.loads((tmp_path / "outbox_delivery.jsonl").read_text().splitlines()[-1])
        assert log["trace_id"] == delivery["trace_id"] == engine.state["outbox"][-1]["trace_id"]
        assert log["span_id"] and delivery["span_id"]
