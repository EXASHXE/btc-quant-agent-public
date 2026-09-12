from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from test_v041_p5_protocol_evidence_persistence import FIXED_TIME, _protocol

from btc_quant_agent import microstructure as micro
from btc_quant_agent import publication as pub
from btc_quant_agent.microstructure_research import H39BlindLedger
from btc_quant_agent.research_contract.registry import ResearchContractRegistry


def store(root):
    return micro.MicrostructureStore(root, "hardening-synthetic", 0)


def trade(number=1, timestamp=100):
    return micro.AggTrade(timestamp, number, 100.0, 1.0, False, "BUY", timestamp, timestamp + 20, number)


def test_two_finalizers_stale_mutation_and_idempotent_reopen(tmp_path):
    first = store(tmp_path)
    assert first.append_trade(trade())
    second = store(tmp_path)
    barrier = Barrier(2)

    def finalize(owner):
        barrier.wait(timeout=2)
        try:
            owner.finalize_partitions(90_000_000)
            return "committed", owner
        except pub.PublicationConflict:
            return "stale", owner

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finalize, [first, second]))
    assert sorted(result[0] for result in results) == ["committed", "stale"]
    stale = next(owner for state, owner in results if state == "stale")
    partition = tmp_path / "microstructure-1970-01-01.sqlite3"
    previous = partition.read_bytes()
    with pytest.raises(pub.PublicationConflict):
        stale.append_trade(trade(2))
    with pytest.raises(pub.PublicationConflict):
        stale.heartbeat(200, "stale-process")
    assert partition.read_bytes() == previous
    manifest = first.finalized_manifest_path.read_bytes()
    reopened = store(tmp_path)
    assert len(reopened.finalize_partitions(90_000_000)) == 1
    assert reopened.finalized_manifest_path.read_bytes() == manifest
    assert partition.read_bytes() == previous


def test_finalization_after_cutover_fault_reopens_once(tmp_path, monkeypatch):
    owner = store(tmp_path)
    owner.append_trade(trade())
    original = pub.fsync_directory

    def fault(directory):
        raise OSError("synthetic directory failure")

    monkeypatch.setattr(pub, "fsync_directory", fault)
    with pytest.raises(pub.PublicationUncertain):
        owner.finalize_partitions(90_000_000)
    committed = owner.finalized_manifest_path.read_bytes()
    monkeypatch.setattr(pub, "fsync_directory", original)
    assert len(store(tmp_path).finalize_partitions(90_000_000)) == 1
    assert len(owner.finalize_partitions(90_000_000)) == 1
    assert owner.finalized_manifest_path.read_bytes() == committed


def test_finalization_before_cutover_keeps_prior_manifest(tmp_path, monkeypatch):
    owner = store(tmp_path)
    owner.append_trade(trade())
    owner.finalize_partitions(90_000_000)
    old = owner.finalized_manifest_path.read_bytes()
    owner.append_trade(trade(2, 86_400_100))
    original = micro.publish_bytes

    def fault(path):
        raise OSError("synthetic before cutover")

    def publish(path, encoded, **kwargs):
        return original(path, encoded, before_replace=fault, **kwargs)

    monkeypatch.setattr(micro, "publish_bytes", publish)
    with pytest.raises(OSError, match="before cutover"):
        owner.finalize_partitions(180_000_000)
    assert owner.finalized_manifest_path.read_bytes() == old
    assert len(store(tmp_path)._manifest()) == 1
    monkeypatch.setattr(micro, "publish_bytes", original)
    assert len(owner.finalize_partitions(180_000_000)) == 2


def test_open_session_not_finalized(tmp_path):
    owner = store(tmp_path)
    owner.session_start(100, "aggTrade", "synthetic-process")
    assert owner.finalize_partitions(90_000_000) == {}
    assert not owner.finalized_manifest_path.exists()


def test_busy_wal_checkpoint_refuses_finalization_then_retry_succeeds(tmp_path, monkeypatch):
    owner = store(tmp_path)
    owner.append_trade(trade())
    partition = tmp_path / "microstructure-1970-01-01.sqlite3"
    reader = sqlite3.connect(partition)
    reader.execute("BEGIN")
    reader.execute("SELECT price FROM agg_trades").fetchone()
    owner.append_trade(trade(2))
    original = sqlite3.connect

    def fast_connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.execute("PRAGMA busy_timeout=10")
        return connection

    monkeypatch.setattr(micro.sqlite3, "connect", fast_connect)
    try:
        with pytest.raises(RuntimeError, match="checkpoint busy"):
            owner.finalize_partitions(90_000_000)
        assert not owner.finalized_manifest_path.exists()
    finally:
        reader.close()
    assert len(owner.finalize_partitions(90_000_000)) == 1


def test_registry_postcommit_reconciliation_preserves_append_only_history(tmp_path, monkeypatch):
    path = tmp_path / "registry.json"
    registry = ResearchContractRegistry(path)
    registry.register_experiment(_protocol(), registered_at_utc=FIXED_TIME)
    old_payload = registry.to_dict()
    next_protocol = replace(_protocol(), experiment_id="EXP-SYNTHETIC-SECOND")
    original = pub.fsync_directory

    def fault(directory):
        raise OSError("synthetic postcommit")

    monkeypatch.setattr(pub, "fsync_directory", fault)
    with pytest.raises(pub.PublicationUncertain):
        registry.register_experiment(next_protocol, registered_at_utc=FIXED_TIME)
    assert registry.generation == 2
    committed = path.read_bytes()
    monkeypatch.setattr(pub, "fsync_directory", original)
    reopened = ResearchContractRegistry(path)
    assert reopened.generation == 2
    reopened.register_experiment(next_protocol, registered_at_utc=FIXED_TIME)
    assert path.read_bytes() == committed
    assert reopened.to_dict()["decision_events"][:1] == old_payload["decision_events"]


def test_blind_source_finalized_flag_cannot_downgrade(tmp_path):
    source = tmp_path / "synthetic-source.sqlite3"
    source.write_bytes(b"synthetic partition")
    path = tmp_path / "blind-ledger.sqlite3"
    ledger = H39BlindLedger(path)
    ledger.record_or_verify_source_partition(source, finalized=True)
    with pytest.raises(RuntimeError, match="cannot downgrade"):
        ledger.record_or_verify_source_partition(source, finalized=False)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT finalized FROM h39_source_partitions").fetchone()[0] == 1
    assert ledger.record_or_verify_source_partition(source, finalized=True)["finalized"] is True


def test_blind_source_competing_finalizers_cannot_overwrite_sealed_hash(tmp_path):
    sources = []
    for number in (1, 2):
        root = tmp_path / str(number)
        root.mkdir()
        source = root / "synthetic-source.sqlite3"
        source.write_bytes(f"synthetic partition {number}".encode())
        sources.append(source)
    path = tmp_path / "blind-ledger.sqlite3"
    H39BlindLedger(path).record_or_verify_source_partition(sources[0], finalized=False)
    owners = [H39BlindLedger(path), H39BlindLedger(path)]
    barrier = Barrier(2)

    def finalize(number):
        barrier.wait(timeout=2)
        try:
            owners[number].record_or_verify_source_partition(sources[number], finalized=True)
            return "committed"
        except RuntimeError as exc:
            assert "SOURCE_PARTITION_MUTATION" in str(exc)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(finalize, [0, 1])) == ["committed", "stale"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM h39_source_partitions WHERE finalized=1").fetchone()[0] == 1
