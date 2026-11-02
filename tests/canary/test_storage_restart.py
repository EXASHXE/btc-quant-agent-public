import json
import os
import subprocess
import sys
import pytest
from btc_quant_agent.platform.canary.policy import ROOT, StoragePolicy
from btc_quant_agent.platform.canary.storage import ReceiptStorage, StorageBlocked

REC = {"exposure": "SYNTHETIC", "value": 1}


def storage(tmp_path, store, **kw):
    return ReceiptStorage(tmp_path, store, StoragePolicy(**kw))


def test_hash_dedup_and_real_normalization_replay(tmp_path, store):
    s = storage(tmp_path, store)
    raw = s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)
    assert raw == s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)
    s.write("NORMALIZED", "BTCUSDT", ({"exposure": "SYNTHETIC", "double": 2},), 1000, 2000, raw_sha=raw)
    assert s.audit()["manifest_chunks"] == 2
    r = s.replay_crosscheck(lambda r: {"exposure": r["exposure"], "double": r["value"] * 2})
    assert r["complete_raw_replay"] and r["replayed_pairs"] == 1
    with pytest.raises(StorageBlocked, match="MISMATCH"):
        s.replay_crosscheck(lambda r: REC)


@pytest.mark.parametrize("kind", ["RAW", "NORMALIZED", "DIAGNOSTIC"])
def test_quota_never_silently_discards_essential(kind, tmp_path, store):
    s = storage(tmp_path, store, chunk_bytes=50)
    if kind == "DIAGNOSTIC":
        assert s.write(kind, "BTCUSDT", (REC,), 1000, 2000, optional_diagnostic=True) is None
        assert store.get_value("diagnostics_shed") == 1
    else:
        with pytest.raises(StorageBlocked, match="STORAGE_BLOCKED"):
            s.write(kind, "BTCUSDT", (REC,), 1000, 2000)
    assert s.audit()["manifest_chunks"] == 0


@pytest.mark.parametrize("hours", [24, 36])
def test_retention_at_26h_honestly_labels_earliest_raw(hours, tmp_path, store):
    s = storage(tmp_path, store, raw_retention_hours=hours)
    raw = s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)
    s.write("NORMALIZED", "BTCUSDT", (REC,), 1000, 2000, raw_sha=raw)
    s.expire(2000 + 26 * 3_600_000)
    a = s.audit()
    if hours == 24:
        assert not a["full_raw_replay_available"] and a["limitations"] == ["EARLIEST_RAW_NOT_RETAINED"]
        assert s.replay_crosscheck(lambda r: r)["raw_expired_pairs_not_replayed"] == 1
    else:
        assert a["full_raw_replay_available"] and not a["limitations"]


@pytest.mark.parametrize("fault", ["bytes", "missing", "part", "symlink"])
def test_corrupt_or_incomplete_evidence_blocks_replay(fault, tmp_path, store):
    s = storage(tmp_path, store)
    raw = s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)
    p = s.chunks / (raw + ".json")
    if fault == "bytes":
        p.write_text("{}")
    elif fault == "missing":
        p.unlink()
    elif fault == "part":
        (s.chunks / "orphan.part").write_text("partial")
    else:
        p.unlink()
        p.symlink_to(tmp_path / "absent")
    with pytest.raises(StorageBlocked):
        s.replay_crosscheck(lambda r: r)


def child(mode, path):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/canary_worker.py"), mode, str(path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_genuine_process_crash_after_rename_and_recovery(tmp_path):
    crash = child("chunk-crash", tmp_path)
    assert crash.returncode == 67, crash.stderr
    recovered = child("recover", tmp_path)
    assert recovered.returncode == 0, recovered.stderr
    a = json.loads(recovered.stdout)
    assert a["manifest_chunks"] == 1 and a["status"] == "INTEGRITY_OK"
    assert json.loads(child("recover", tmp_path).stdout)["manifest_chunks"] == 1


def test_genuine_source_process_restart_deduplicates(tmp_path):
    a = child("source", tmp_path)
    b = child("source", tmp_path)
    assert a.returncode == b.returncode == 0
    assert json.loads(a.stdout)["reason"] is None
    assert json.loads(b.stdout)["reason"] == "DUPLICATE_DISCARDED"
    assert json.loads(b.stdout)["state"]["last_receive_ms"] == 1100


def test_genuine_competing_processes_cannot_overspend(tmp_path):
    # Initialize DDL before concurrent workers; the production claims still contend on SQLite.
    assert child("recover", tmp_path).returncode == 0
    procs = [
        subprocess.Popen(
            [sys.executable, str(ROOT / "tools/canary_worker.py"), "budget", str(tmp_path)],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    outputs = [p.communicate(timeout=30) for p in procs]
    assert all(p.returncode == 0 for p in procs), outputs
    assert sum(out.strip() == "ACCEPT" for out, err in outputs) == 2
    assert sum(out.strip() == "BLOCK" for out, err in outputs) == 2


def test_manifest_header_tampering_is_detected(tmp_path, store):
    s = storage(tmp_path, store)
    raw = s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)
    with store._connect() as db:
        db.execute("UPDATE canary_chunks SET symbol=? WHERE sha=?", ("OTHERUSDT", raw))
    assert any("MANIFEST_HEADER_MISMATCH" in e for e in s.audit()["errors"])


def test_unregistered_raw_reference_is_not_misreported_as_expired(tmp_path, store):
    s = storage(tmp_path, store)
    s.write("NORMALIZED", "BTCUSDT", (REC,), 1000, 2000, raw_sha="0" * 64)
    with pytest.raises(StorageBlocked, match="RAW_REFERENCE"):
        s.replay_crosscheck(lambda r: r)


def test_dedup_does_not_hide_missing_evidence(tmp_path, store):
    s = storage(tmp_path, store)
    raw = s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)
    (s.chunks / (raw + ".json")).unlink()
    with pytest.raises(StorageBlocked, match="INTEGRITY"):
        s.write("RAW", "BTCUSDT", (REC,), 1000, 2000)


def test_sqlite_evidence_headroom_checked_before_state_write(tmp_path, store):
    s = storage(tmp_path, store)
    current = s._disk_bytes()
    s.policy = s.policy.model_copy(
        update={"total_disk_quota_bytes": current + s.policy.metadata_base_reserve + 65535}
    )
    with pytest.raises(StorageBlocked, match="ADMISSION_HEADROOM"):
        s.reserve_admission_capacity(REC)
    assert not store.get_value("last_receipt")
