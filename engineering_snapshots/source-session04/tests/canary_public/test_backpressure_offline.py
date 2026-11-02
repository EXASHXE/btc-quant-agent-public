"""Offline serializer, real queue exhaustion and durable partial-output regressions."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

import pytest

from btc_quant_agent.platform.canary.control import CircuitOpen
from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.canary.public_journal import PublicJournal
from btc_quant_agent.platform.canary.public_runtime import PublicEngine
from btc_quant_agent.platform.canary.storage import StorageBlocked, encode
from btc_quant_agent.platform.core import primitive
from .fixtures import Clock, meta_payload, wire
from .test_transport_scope import transport


@pytest.mark.parametrize("value", [None, True, False, 0, 2**100, -3, 0.0, -0.0, "", "original evidence \u2603"])
def test_scalar_identity_and_type_are_preserved(value):
    result = primitive(value)
    assert result is value and type(result) is type(value)


def test_nested_contract_serialization_preserves_extensions_and_exact_bytes():
    @dataclass
    class Item:
        amount: Decimal
        count: int

    class State(StrEnum):
        READY = "READY"

    class ExtendedString(str):
        def model_dump(self, mode):
            assert mode == "json"
            return "extension"

    value = {"state": State.READY, "items": (Item(Decimal("0.010"), 3), None, False),
             "extended": ExtendedString("original")}
    assert encode(value) == b'{"extended":"extension","items":[{"amount":"0.010","count":3},null,false],"state":"READY"}'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_values_still_fail_journal_encoding(value):
    with pytest.raises(ValueError):
        encode({"observed": value})


@pytest.mark.parametrize("race_after_guard", [False, True])
def test_actual_128_queue_pending_guard_and_queue_full_both_hard_stop(scope, tmp_path, race_after_guard):
    t = transport(scope, tmp_path)
    count = 127 if race_after_guard else 128
    for index in range(count):
        t.queue.put_nowait(index)
    if race_after_guard:
        original = t.guard.data_message

        def race(mono, pending):
            original(mono, pending)
            t.queue.put_nowait(127)

        t.guard.data_message = race
    try:
        t.open_group("public")
        t.threads[0].join(timeout=2)
        assert not t.threads[0].is_alive()
        assert t.error == "BACKPRESSURE_BLOCKED" and t.queue.qsize() == t.queue.maxsize == 128
        assert t.metrics["ws_raw_messages"] == 1
        assert t.metrics["ws_frames"] == int(race_after_guard)
        circuit = t.guard.store.get_value("circuit")
        assert (circuit is None) if race_after_guard else circuit == {"reason": "BACKPRESSURE_BLOCKED"}
        assert [t.next(0) for _ in range(128)] == list(range(128))
        if not race_after_guard:
            with pytest.raises(CircuitOpen, match="BACKPRESSURE_BLOCKED"):
                t.guard.data_message(t.clock.mono(), 0)
        with pytest.raises(RuntimeError, match="BACKPRESSURE_BLOCKED"):
            t.active()
    finally:
        t.close()
    assert not t.backend.calls and not t.connections


def test_partial_normalized_failure_reuses_raw_chunk_once_and_preserves_pending(scope, tmp_path):
    t = transport(scope, tmp_path)
    clock = Clock()
    journal = PublicJournal(tmp_path / "offline", t.guard.store, clock, exposure="SYNTHETIC", reserve=0)
    engine = PublicEngine(scope, clock, t.guard.store, journal, "SYNTHETIC")
    real_write = journal.write

    def fail_normalized(kind, *args, **kwargs):
        if kind == "normalized":
            raise StorageBlocked("INJECTED_NORMALIZED_FAILURE")
        return real_write(kind, *args, **kwargs)

    journal.write = fail_normalized
    with pytest.raises(StorageBlocked, match="INJECTED_NORMALIZED_FAILURE"):
        engine.ingest(wire("binance_usdm_exchange_info", meta_payload(), clock.wall()))
    assert len(engine.pending) == 1 and engine.pending_raw_sha is not None
    assert engine.counts["received"] == 0
    incomplete = journal.audit_replay(normalize)
    assert incomplete["status"] == "INCOMPLETE" and incomplete["unpaired_raw_chunks"] == 1
    journal.write = real_write
    engine.flush()
    engine.flush()
    assert [r[3] for r in journal.rows()] == ["raw", "normalized"]
    assert engine.counts["received"] == 1 and not engine.pending
    assert journal.audit_replay(normalize)["status"] == "PARITY_VERIFIED"


def test_partial_file_refuses_recovery_without_relabel_or_delete(scope, tmp_path):
    t = transport(scope, tmp_path)
    root = tmp_path / "partial"
    journal = PublicJournal(root, t.guard.store, Clock(), exposure="SYNTHETIC", reserve=0)
    partial = journal.root / "raw" / "interrupted.part"
    partial.write_bytes(b"partial-offline-fixture")
    with pytest.raises(StorageBlocked, match="INCOMPLETE_CHUNK_REQUIRES_OPERATOR_RECONCILIATION"):
        PublicJournal(root, t.guard.store, Clock(), exposure="SYNTHETIC", reserve=0)
    assert partial.read_bytes() == b"partial-offline-fixture" and not journal.rows()
