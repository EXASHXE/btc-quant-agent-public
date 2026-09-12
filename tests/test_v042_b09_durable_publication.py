from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from btc_quant_agent import publication as pub
from btc_quant_agent.research_contract.registry import (
    RegistryCorruptionError,
    ResearchContractRegistry,
)


@pytest.mark.parametrize("stage", ["write", "flush", "file_fsync", "before_replace", "replace"])
def test_precommit_failure_preserves_exact_prior_bytes(tmp_path, monkeypatch, stage):
    target = tmp_path / "committed.json"
    old = b'{"committed":1}\n'
    target.write_bytes(old)
    real_fdopen = pub.os.fdopen

    class Handle:
        def __init__(self, descriptor, mode):
            self.real = real_fdopen(descriptor, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.real.__exit__(*args)

        def write(self, value):
            if stage == "write":
                self.real.write(value[:3])
                raise OSError("synthetic write fault")
            return self.real.write(value)

        def flush(self):
            if stage == "flush":
                raise OSError("synthetic flush fault")
            return self.real.flush()

        def fileno(self):
            return self.real.fileno()

    def fault(*args):
        raise OSError("synthetic publication fault")

    monkeypatch.setattr(pub.os, "fdopen", Handle)
    if stage == "file_fsync":
        monkeypatch.setattr(pub.os, "fsync", fault)
    if stage == "replace":
        monkeypatch.setattr(pub.os, "replace", fault)
    with pytest.raises(OSError, match="synthetic"):
        pub.publish_bytes(target, b'{"committed":2}\n',
                          before_replace=fault if stage == "before_replace" else None)
    assert target.read_bytes() == old
    assert list(tmp_path.glob("*.tmp")) == []


def test_directory_failure_surfaces_committed_uncertainty(tmp_path, monkeypatch):
    target = tmp_path / "committed.json"
    target.write_bytes(b"old")

    def fault(directory):
        raise OSError("synthetic directory fault")

    monkeypatch.setattr(pub, "fsync_directory", fault)
    with pytest.raises(pub.PublicationUncertain, match="durability unconfirmed"):
        pub.publish_bytes(target, b'{"complete":true}\n')
    assert json.loads(target.read_bytes()) == {"complete": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_publication_order_and_reentrant_ownership(tmp_path, monkeypatch):
    events = []
    replace = pub.os.replace
    fsync = pub.os.fsync

    def file_sync(descriptor):
        events.append("file_fsync")
        fsync(descriptor)

    def cutover(source, target):
        assert Path(source).parent == Path(target).parent
        events.append("replace")
        replace(source, target)

    monkeypatch.setattr(pub.os, "fsync", file_sync)
    monkeypatch.setattr(pub.os, "replace", cutover)
    monkeypatch.setattr(pub, "fsync_directory", lambda directory: events.append("dir_fsync"))
    target = tmp_path / "out.json"
    with pub.publication_lock(target):
        pub.publish_bytes(target, b"{}\n", before_replace=lambda path: events.append("prepared"))
    assert events == ["file_fsync", "prepared", "replace", "dir_fsync"]
    assert target.read_bytes() == b"{}\n"


def test_two_same_generation_publishers_only_one_commits(tmp_path):
    target = tmp_path / "committed.json"
    barrier = Barrier(2)

    def writer(number):
        barrier.wait(timeout=2)
        try:
            pub.publish_bytes(target, json.dumps({"owner": number}).encode(), expected_sha256=None)
            return "committed"
        except pub.PublicationConflict:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, [1, 2]))
    assert sorted(results) == ["committed", "stale"]
    assert json.loads(target.read_bytes())["owner"] in (1, 2)
    original = target.read_bytes()
    with pytest.raises(pub.PublicationConflict):
        pub.publish_bytes(target, b"invalid", expected_sha256=None)
    assert target.read_bytes() == original


def test_truncated_registry_not_authority_and_orphan_not_committed(tmp_path):
    target = tmp_path / "registry.json"
    (tmp_path / ".registry.json.orphan.tmp").write_bytes(b"{}")
    assert ResearchContractRegistry(target).generation == 0
    target.write_bytes(b'{"generation":1')
    with pytest.raises(RegistryCorruptionError):
        ResearchContractRegistry(target)


def test_normalization_does_not_probe_committed_target(tmp_path, monkeypatch):
    target = tmp_path / "committed.json"
    target.write_bytes(b"old")
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == target:
            raise AssertionError("unexpected target metadata probe")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    pub.publish_bytes(target, b"{}\n")
    assert target.read_bytes() == b"{}\n"
