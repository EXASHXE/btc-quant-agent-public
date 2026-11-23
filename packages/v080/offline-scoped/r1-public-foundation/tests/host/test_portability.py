from __future__ import annotations

import hashlib
import base64
import io
import json
import socket
import zipfile
from types import SimpleNamespace

import pytest

from deployment import admission_check, bundle, host_check


@pytest.mark.parametrize(
    "field,value",
    [("system", "Windows"), ("machine", "aarch64"), ("python", "3.12.3"), ("libc_version", "2.38")],
)
def test_unsupported_ABI_cannot_be_promoted(field, value):
    info = dict(
        system="Linux",
        machine="x86_64",
        implementation="CPython",
        python="3.13.13",
        libc="glibc",
        libc_version="2.39",
    )
    info[field] = value
    with pytest.raises(ValueError, match="UNSUPPORTED_HOST"):
        host_check.compatibility(info)


def profile(step=0, span=0):
    return {
        "samples": [
            {"wall_ns": 1000000000, "mono_before_ns": 1000000000, "mono_after_ns": 1000000000},
            {
                "wall_ns": 31000000000 + step,
                "mono_before_ns": 31000000000,
                "mono_after_ns": 31000000000 + span,
            },
        ],
        "elapsed_seconds": 30,
        "cross_process_mono_order_valid": True,
    }


def test_stability_never_substitutes_for_independent_UTC():
    value = host_check.stability(profile())
    assert value["status"] == "BOUNDED_STABILITY_ONLY" and not value["qualified"]


@pytest.mark.parametrize(
    "step,span,reason",
    [(1722000000, 0, "CLOCK_50MS_DISCONTINUITY"), (0, 100000000, "CLOCK_BRACKET_UNCERTAIN")],
)
def test_same_accepted_sticky_policy_retains_step_and_uncertainty(step, span, reason):
    value = host_check.stability(profile(step, span))
    assert value["reason"] == reason and value["epoch_resets"] == 0


def test_cross_process_domain_and_duration_are_required():
    data = profile()
    data["cross_process_mono_order_valid"] = False
    with pytest.raises(ValueError, match="CROSS_PROCESS"):
        host_check.stability(data)
    data = profile()
    data["elapsed_seconds"] = 15
    with pytest.raises(ValueError, match="COVERAGE"):
        host_check.stability(data)


def test_actual_fsync_atomic_replace_SQLite_crash_and_exclusion(tmp_path):
    value = host_check.filesystem(tmp_path / "fs")
    assert value["status"].startswith("PASS_LOCAL") and value["crash_child_exit"] == 73
    assert value["power_loss_hardware_qualification"] == "NOT_ESTABLISHED"
    with pytest.raises(FileExistsError):
        host_check.filesystem(tmp_path / "fs")


@pytest.mark.parametrize("failure", ["before_write", "before_fsync", "before_replace"])
def test_interrupted_durability_never_claims_pass(tmp_path, failure):
    def fault(point):
        if point == failure:
            raise OSError(28, "SYNTHETIC_DISK_FULL_OR_INTERRUPTED_WRITE")

    with pytest.raises(OSError):
        host_check.filesystem(tmp_path / "failed", fault)
    assert not (tmp_path / "failed/committed").exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "x/../escape", "C:\\keys", "./ambiguous"])
def test_bundle_path_escape_rejected_before_materialization(tmp_path, name):
    archive = tmp_path / "bad.zip"
    row = {"path": name, "sha256": hashlib.sha256(b"a").hexdigest(), "bytes": 1}
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("bundle_manifest.json", json.dumps({"files": [row]}))
        z.writestr(name, b"a")
    with pytest.raises(ValueError, match="UNSAFE_BUNDLE_PATH"):
        bundle.materialize(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_bundle_hash_tamper_and_unlisted_code_are_blocked(tmp_path):
    (tmp_path / "deployment").mkdir()
    file = tmp_path / "deployment/probe.py"
    file.write_bytes(b"safe")
    (tmp_path / "bundle_manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {"path": "deployment/probe.py", "bytes": 4, "sha256": hashlib.sha256(b"safe").hexdigest()}
                ]
            }
        )
    )
    assert bundle.verify(tmp_path)["host_qualified"] is False
    file.write_bytes(b"evil")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        bundle.verify(tmp_path)
    file.write_bytes(b"safe")
    (tmp_path / "deployment/unlisted.py").write_bytes(b"evil")
    with pytest.raises(ValueError, match="UNLISTED"):
        bundle.verify(tmp_path)


def test_unlisted_wheel_payload_fails_RECORD_coverage():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("q-1.dist-info/RECORD", "q-1.dist-info/RECORD,,\n")
        z.writestr("unhashed.py", "evil")
    with pytest.raises(ValueError, match="RECORD_COVERAGE"):
        bundle.wheel_record(b.getvalue())


def test_vendored_RECORD_is_hashed_payload_not_the_outer_wheel_index():
    files = {
        "q-1.dist-info/METADATA": b"Name: q\nVersion: 1\n",
        "q/_vendor/x-1.dist-info/RECORD": b"vendored metadata\n",
    }
    rows = []
    for name, raw in files.items():
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
        rows.append(f"{name},sha256={encoded},{len(raw)}\n")
    files["q-1.dist-info/RECORD"] = ("".join(rows) + "q-1.dist-info/RECORD,,\n").encode()
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    bundle.wheel_record(data.getvalue())


def test_production_authority_intake_records_block_before_socket_or_reservation(tmp_path, monkeypatch):
    attempts = []

    def deny(*args, **kw):
        attempts.append(True)
        raise AssertionError("NO_NETWORK")

    monkeypatch.setattr(socket.socket, "connect", deny)
    argv = []
    for name in ("grant", "audit", "config", "wheel", "rights", "host-certificate", "registry", "report"):
        argv += ["--" + name, str(tmp_path / name)]
    assert admission_check.main(argv) == 2
    value = json.loads((tmp_path / "report").read_text())
    assert value["reason"] == "INDEPENDENT_TRUST_REQUIRED" and value["native_requests"] == 0
    assert not attempts and not (tmp_path / "registry").exists()


@pytest.mark.parametrize(
    "field",
    [
        "region_eligibility",
        "prospective_capture",
        "retention",
        "endpoints",
        "streams",
        "retention_seconds_max",
    ],
)
def test_unsigned_test_dossier_never_overrides_scope(field):
    grant = SimpleNamespace(
        venue="SYNTHETIC_ONLY",
        endpoint="wss://invalid.example",
        clock_endpoint="https://invalid.example/time",
        streams=["synthetic@kline_4h"],
        retention_seconds=30,
    )
    d = {
        "schema": "G_INDEPENDENT_RIGHTS_DOSSIER_V1",
        "independent_reference": "FABRICATED_TEST_ONLY",
        "venue": grant.venue,
        "endpoints": [grant.endpoint, grant.clock_endpoint],
        "streams": grant.streams,
        "retention_seconds_max": 60,
    }
    for k in (
        "venue_eligibility",
        "region_eligibility",
        "public_access",
        "noncommercial_research",
        "prospective_capture",
        "local_cache",
        "retention",
    ):
        d[k] = "INDEPENDENTLY_ESTABLISHED"
    d[field] = (
        [] if field in ("endpoints", "streams") else 0 if field == "retention_seconds_max" else "UNKNOWN"
    )
    with pytest.raises(ValueError, match="RIGHTS"):
        admission_check.rights_scope(d, grant)
