"""Invented R4 witnesses: receipt ordering, economic exposure, cash WAL and ACK."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.g1_offline_preview_r1 import model as g1_model
from scripts.g1_offline_preview_r1.fixtures import bar, make_fixture
from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.g1_offline_preview_r1.storage import Engine
from scripts.g1g3_offline_ports_r1.durable_supervisor import DurableSidecarSupervisor
from scripts.g1g3_offline_ports_r1.market_pit_port import (
    MarketPitPort,
    calculate_settled_funding_cash_flow,
    make_synthetic_funding_envelope,
)

ROOT = Path(g1_model.__file__).resolve().parents[2]


def _initial(side="LONG"):
    return initial_state(make_fixture(side)["trusted_approvals"], causal_funding=True)


def _seed(engine, side="LONG", *, acknowledge=False, executed_quantity="0.004"):
    for event in make_fixture(side)["events"]:
        if event["at"] <= 120004:
            engine.apply(event)
    for index in (2, 3):
        b = bar(index, side)
        if index == 3:
            price = 30305 if side == "LONG" else 29695
            b.update(
                last_open=str(price),
                last_close=str(price),
                last_high=str(price + 5),
                last_low=str(price - 5),
                mark_close=str(price),
            )
        engine.apply(
            {"id": f"R4-BAR-{index}", "kind": "BAR", "at": b["available_at"], "payload": b}
        )
    engine.apply(
        {
            "id": "R4-partial",
            "kind": "TP1",
            "at": 239999,
            "payload": {"fill_id": "r4-exit", "executed_quantity": executed_quantity},
        }
    )
    b = bar(4, side)
    engine.apply({"id": "R4-BAR-4", "kind": "BAR", "at": b["available_at"], "payload": b})
    if acknowledge:
        engine.apply(_ack(engine, 300000))


def _ack(engine, at):
    return {
        "id": "r4-exit-ack",
        "kind": "ACK",
        "at": at,
        "payload": {"ack_id": "r4-ack", "order_id": engine.state["order_id"], "fill_id": "r4-exit"},
    }


def _envelope(settlement_at=200000, *, receipt_at=360000, rate="0.0001", sequence=1):
    env = make_synthetic_funding_envelope(
        settlement_id="r4-settlement",
        event_id="r4-funding",
        settlement_at_ms=settlement_at,
        mark_price="60000",
        rate_fraction=rate,
        available_at_ms=receipt_at,
        observed_wall_utc_ms=receipt_at,
        sequence=sequence,
        monotonic_ns=sequence * 1000000,
    )
    p = env["payload"]
    p.update(
        contract_version="SYNTHETIC_CAUSAL_R4",
        mark_witness={
            "at": settlement_at,
            "known_at": receipt_at,
            "source": "SYNTHETIC_SETTLEMENT_MARK",
        },
        rate_witness={
            "at": settlement_at,
            "known_at": receipt_at,
            "source": "SYNTHETIC_SETTLED_RATE",
        },
        fill_coverage={
            "from_at": 0,
            "through_at": settlement_at,
            "known_at": receipt_at,
            "source": "G1_SYNTHETIC_WAL",
        },
    )
    env["payload_sha256"] = digest(p)
    return env


def _rows(engine):
    return [r for r in engine.state["journal"] if r["key"] == "funding:r4-settlement"]


@pytest.mark.parametrize(
    "side,rate,expected",
    [
        ("LONG", "0.0001", "-0.0600"),
        ("SHORT", "0.0001", "0.0600"),
        ("LONG", "-0.0002", "0.1200"),
        ("SHORT", "-0.0002", "-0.1200"),
    ],
)
@pytest.mark.parametrize("acknowledge", [False, True])
def test_late_receipt_cash_uses_pre_settlement_fills_without_decision_leak(
    tmp_path, side, rate, expected, acknowledge
):
    init = _initial(side)
    with Engine(tmp_path / "g1", init, temporary=True) as engine:
        _seed(engine, side, acknowledge=acknowledge)
        before = copy.deepcopy(engine.state)
        before_hash = digest(before)
        assert engine.state["remaining_qty"] == "0.006"
        supervisor = DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True)
        ack = supervisor.apply_funding_envelope(engine, _envelope(rate=rate))
        row = _rows(engine)[0]
        assert ack["status"] == "COMMITTED"
        assert row["at"] == row["receipt_at"] == engine.state["last_at"] == 360000
        assert row["settlement_at"] == 200000
        assert Decimal(row["cash_delta"]) == Decimal(expected)
        assert Decimal(engine.state["cash"]) == Decimal(before["cash"]) + Decimal(expected)
        assert abs(Decimal(row["signed_exposure"])) == Decimal("0.010")
        assert row["witnesses"]["mark_price"] == "60000"
        assert before_hash == digest(before) and not any(
            r["kind"] == "FUNDING_RECEIPT" for r in before["journal"]
        )
        for key in (
            "proposal",
            "analysis",
            "analysis_at",
            "approval",
            "pending_cash",
            "pending_release",
            "reserved_notional",
        ):
            assert engine.state[key] == before[key]
        assert engine.state["trace"][: len(before["trace"])] == before["trace"]
        if not acknowledge:
            engine.apply(_ack(engine, 360001))
            assert engine.state["pending_cash"] == {}
    with Engine(tmp_path / "g1", init, temporary=True) as recovered:
        assert len(_rows(recovered)) == 1
        assert recovered.state["last_at"] >= 360000


@pytest.mark.parametrize("side,expected", [("LONG", "-0.0360"), ("SHORT", "0.0360")])
def test_pre_settlement_partial_uses_residual_exposure(tmp_path, side, expected):
    with Engine(tmp_path / "g1", _initial(side), temporary=True) as engine:
        _seed(engine, side)
        DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
            engine, _envelope(280000)
        )
        assert Decimal(_rows(engine)[0]["cash_delta"]) == Decimal(expected)


@pytest.mark.parametrize("offset", [-15000, -1000, 0, 1000, 15000])
def test_uncertain_fill_membership_quarantines_without_cash(tmp_path, offset):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        _seed(engine)
        before = digest(engine.state)
        with pytest.raises(SafetyViolation, match="AMBIGUOUS_SETTLEMENT_BOUNDARY"):
            DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
                engine, _envelope(239999 + offset)
            )
        assert digest(engine.state) == before and not _rows(engine)


@pytest.mark.parametrize(
    "missing", ["mark_price", "rate_fraction", "mark_witness", "rate_witness", "fill_coverage"]
)
def test_missing_witness_is_rejected_even_for_zero_rate(tmp_path, missing):
    env = _envelope(rate="0")
    del env["payload"][missing]
    env["payload_sha256"] = digest(env["payload"])
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        with pytest.raises(SafetyViolation):
            DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
                engine, env
            )
        assert engine.state["cash"] == "1000" and not _rows(engine)


@pytest.mark.parametrize("rate", ["0", "0.0001"])
def test_complete_flat_witness_posts_explicit_zero(tmp_path, rate):
    with Engine(tmp_path / "g1", initial_state([], causal_funding=True), temporary=True) as engine:
        DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
            engine, _envelope(rate=rate)
        )
        assert Decimal(_rows(engine)[0]["cash_delta"]) == 0
        assert engine.state["cash"] == "1000.00000000"


def test_complete_zero_rate_for_nonzero_settlement_exposure(tmp_path):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        _seed(engine)
        before = Decimal(engine.state["cash"])
        DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
            engine, _envelope(rate="0")
        )
        assert Decimal(_rows(engine)[0]["signed_exposure"]) == Decimal("0.010")
        assert Decimal(engine.state["cash"]) == before


@pytest.mark.parametrize(
    "key,field,value",
    [
        ("mark_witness", "at", 200001),
        ("mark_witness", "source", "UNVERIFIED_MARK"),
        ("rate_witness", "known_at", 360001),
        ("fill_coverage", "from_at", 60000),
        ("fill_coverage", "through_at", 200001),
        ("fill_coverage", "known_at", 360001),
        ("fill_coverage", "source", "UNVERIFIED_FILLS"),
    ],
)
def test_invalid_or_future_witness_never_completes_cash(tmp_path, key, field, value):
    env = _envelope(rate="0")
    env["payload"][key][field] = value
    env["payload_sha256"] = digest(env["payload"])
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        with pytest.raises(SafetyViolation, match="COST_INCOMPLETE"):
            DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
                engine, env
            )
        assert engine.seq == 0 and not _rows(engine)


@pytest.mark.parametrize("economic_at,expected", [(200000, "-0.0600"), (450000, "0")])
def test_flat_at_receipt_preserves_historical_executed_exposure(tmp_path, economic_at, expected):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        _seed(engine)
        b = bar(5)
        b.update(
            last_open="29690",
            last_close="29690",
            last_high="29695",
            last_low="29685",
            mark_close="29690",
        )
        engine.apply({"id": "r4-stop-bar", "kind": "BAR", "at": 359999, "payload": b})
        engine.apply(
            {"id": "r4-stop", "kind": "STOP", "at": 359999, "payload": {"fill_id": "r4-final"}}
        )
        engine.apply(_ack(engine, 420000))
        engine.apply(
            {
                "id": "r4-final-ack",
                "kind": "ACK",
                "at": 420001,
                "payload": {
                    "ack_id": "r4-final-ack",
                    "order_id": engine.state["order_id"],
                    "fill_id": "r4-final",
                },
            }
        )
        assert engine.state["phase"] == "CLOSED" and Decimal(engine.state["remaining_qty"]) == 0
        DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
            engine, _envelope(economic_at, receipt_at=480000)
        )
        assert Decimal(_rows(engine)[0]["cash_delta"]) == Decimal(expected)
        assert engine.state["phase"] == "CLOSED"


def test_explicit_partial_quantity_cannot_exceed_existing_tp1_tier(tmp_path):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        with pytest.raises(SafetyViolation, match="PARTIAL_LOT_OR_MIN_NOTIONAL"):
            _seed(engine, executed_quantity="0.006")
        assert engine.state["remaining_qty"] == "0.01"
        assert len(engine.state["fill_history"]) == 1


@pytest.mark.parametrize(
    "field,value",
    [("mark_price", "65000"), ("rate_fraction", "0.0002"), ("event_id", "revised-id")],
)
def test_conflicting_economics_on_new_transport_rejected_after_restart(tmp_path, field, value):
    init = _initial()
    with Engine(tmp_path / "g1", init, temporary=True) as engine:
        _seed(engine)
        DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
            engine, _envelope()
        )
    env = _envelope(receipt_at=380000, sequence=2)
    env["payload"][field] = value
    env["payload_sha256"] = digest(env["payload"])
    with Engine(tmp_path / "g1", init, temporary=True) as engine:
        before = digest(engine.state)
        with pytest.raises(SafetyViolation, match="FUNDING_SETTLEMENT_CONFLICT"):
            DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True).apply_funding_envelope(
                engine, env
            )
        assert digest(engine.state) == before and len(_rows(engine)) == 1


def test_same_port_retry_after_receipt_before_cash_append_is_not_lost(tmp_path):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        _seed(engine)
        supervisor = DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True)

        def fail(edge, _):
            if edge == "before_append":
                raise RuntimeError("synthetic delivery interruption")

        with pytest.raises(RuntimeError):
            supervisor.apply_funding_envelope(engine, _envelope(), hook=fail)
        assert not _rows(engine)
        assert supervisor.apply_funding_envelope(engine, _envelope())["status"] == "COMMITTED"
        assert (
            supervisor.apply_funding_envelope(engine, _envelope())["status"]
            == "IDEMPOTENT_DUPLICATE"
        )
        assert len(_rows(engine)) == 1


def test_new_transport_duplicate_is_semantic_not_receipt_clock_identity(tmp_path):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        _seed(engine)
        supervisor = DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True)
        supervisor.apply_funding_envelope(engine, _envelope())
        before = digest(engine.state)
        assert (
            supervisor.apply_funding_envelope(engine, _envelope(receipt_at=380000, sequence=2))[
                "status"
            ]
            == "IDEMPOTENT_DUPLICATE"
        )
        assert digest(engine.state) == before


def test_missing_internal_fill_history_rejects_claimed_complete_coverage(tmp_path):
    with Engine(tmp_path / "g1", _initial(), temporary=True) as engine:
        _seed(engine)
        # Corruption witness only, never an accepted state or modified WAL.
        broken = copy.deepcopy(engine.state)
        broken["fill_history"].pop()
        event = MarketPitPort().ingest_envelope(_envelope())["g1_event"]
        with pytest.raises(SafetyViolation, match="COST_INCOMPLETE"):
            transition(broken, event)
        with pytest.raises(SafetyViolation, match="EVENT_REORDERED"):
            transition(engine.state, {**event, "at": 200000})


def test_precision_and_legacy_contract_boundaries(tmp_path):
    results = []
    for precision in (6, 28):
        with localcontext() as context:
            context.prec = precision
            with Engine(tmp_path / str(precision), _initial(), temporary=True) as engine:
                _seed(engine)
                DurableSidecarSupervisor(
                    tmp_path / f"sidecar-{precision}", temporary=True
                ).apply_funding_envelope(engine, _envelope())
                results.append(digest(engine.state))
    assert results[0] == results[1]
    env = make_synthetic_funding_envelope(mark_price="60000")
    legacy = MarketPitPort().ingest_envelope(env)["g1_event"]
    assert legacy["kind"] == "FUNDING" and legacy["at"] == 480000
    assert set(legacy["payload"]) == {"settlement_id", "settlement_at", "rate_fraction"}
    with pytest.raises(SafetyViolation, match="LEGACY_FUNDING_REQUIRES_LEGACY_GENESIS"):
        transition(initial_state([], causal_funding=True), legacy)
    with pytest.raises(SafetyViolation, match="COST_INCOMPLETE"):
        transition(initial_state([]), MarketPitPort().ingest_envelope(_envelope())["g1_event"])
    with pytest.raises(SafetyViolation, match="POSITION_SIDE_QUANTITY_CONTRADICTION"):
        calculate_settled_funding_cash_flow(
            side="LONG",
            quantity="-0.010",
            mark_price="60000",
            rate_fraction="0.0001",
            funding_coverage_complete=True,
        )
    assert (
        calculate_settled_funding_cash_flow(
            side="LONG", quantity="0.010", mark_price="60000", rate_fraction="0"
        )["status"]
        == "COST_INCOMPLETE"
    )


def test_legacy_wal_cannot_be_silently_opted_into_new_genesis(tmp_path):
    root = tmp_path / "g1"
    with Engine(root, initial_state([]), temporary=True) as engine:
        b = bar(0)
        engine.apply({"id": "legacy-bar", "kind": "BAR", "at": b["available_at"], "payload": b})
        original_hash = digest(engine.state)
        original_wal = engine.wal.read_bytes()
    with pytest.raises(SafetyViolation, match="WAL_GENESIS_MISMATCH"):
        Engine(root, initial_state([], causal_funding=True), temporary=True)
    with Engine(root, initial_state([]), temporary=True) as recovered:
        assert digest(recovered.state) == original_hash
        assert recovered.wal.read_bytes() == original_wal


def _crash_child(folder, edge):
    root = Path(folder)
    supervisor = DurableSidecarSupervisor(root / "sidecar", temporary=True)
    with Engine(root / "g1", _initial(), temporary=True) as engine:
        _seed(engine)

        def crash(name, _):
            if name == edge:
                os._exit(91)

        supervisor.apply_funding_envelope(engine, _envelope(), hook=crash)


@pytest.mark.parametrize(
    "edge",
    [
        "before_receipt",
        "after_receipt",
        "before_append",
        "after_append",
        "after_fsync",
        "before_snapshot",
        "after_snapshot",
        "before_receipt_ack",
        "after_receipt_ack",
    ],
)
def test_real_process_crash_replay_cash_exactly_once_with_chronological_ack(tmp_path, edge):
    code = "import importlib.util, sys; s=importlib.util.spec_from_file_location('r4_test',sys.argv[3]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m._crash_child(sys.argv[1],sys.argv[2])"
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), edge, __file__],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 91, result.stderr[-1000:]
    init = _initial()
    with Engine(tmp_path / "g1", init, temporary=True) as recovered:
        before_rows = len(_rows(recovered))
        assert before_rows == (
            0 if edge in ("before_receipt", "after_receipt", "before_append") else 1
        )
        supervisor = DurableSidecarSupervisor(tmp_path / "sidecar", temporary=True)
        ack = supervisor.apply_funding_envelope(recovered, _envelope())
        assert ack["status"] == ("COMMITTED" if not before_rows else "IDEMPOTENT_DUPLICATE")
        assert len(_rows(recovered)) == 1
        assert Decimal(_rows(recovered)[0]["cash_delta"]) == Decimal("-0.0600")
        assert recovered.state["last_at"] == 360000
        recovered.apply(_ack(recovered, 360001))
        assert recovered.state["pending_cash"] == {}
        snapshot = digest(recovered.state)
    with Engine(tmp_path / "g1", init, temporary=True) as restarted:
        assert digest(restarted.state) == snapshot and len(_rows(restarted)) == 1
        records = [json.loads(line) for line in restarted.wal.read_text().splitlines()[1:]]
        assert sum(r["event"]["kind"] == "FUNDING_RECEIPT" for r in records) == 1
